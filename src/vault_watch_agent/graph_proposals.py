"""The nodes before the review, read-only: collect the watch → triage → locate → propose (one branch per group of
items, in parallel) → number → cross-check → report. Nothing here touches the guide."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from langgraph.types import Send

from . import candidates, compact, crosscheck, inputs, news, prompts, reading, steps, vault
from .graph_common import sorted_proposals
from .graph_corrections import mark_conflicts
from .graph_text import render_report
from .state import ClusterProposal, TriageResult, WatchState

if TYPE_CHECKING:
    from .graph_common import Deps

TRIAGE_BATCH = 40  # items per triage call
TRIAGE_NOTES = 1200  # characters of cached notes shown at triage


# -- collect ------------------------------------------------------------
def collect(deps: Deps, state: WatchState) -> dict:
    issue = state.get("issue")
    if issue:
        watch_json = inputs.download_watch(issue, deps.repo, deps.home / "downloads",
                                           vault.guide_of(deps.vault).watch.artifact or "weekly-watch")
    else:
        watch_json = Path(state["source"])
    items, until = inputs.load_items(watch_json)
    claims = inputs.claims_due(deps.vault, deps.home / "downloads" / f"freshness-{deps.today}.json")
    return {"items": items, "as_of": until or deps.today, "claims_due": claims, "retouch_offered": True}


# -- triage -------------------------------------------------------------
def triage(deps: Deps, state: WatchState) -> dict:
    items = state["items"]
    decisions, usage = {}, []
    for start in range(0, len(items), TRIAGE_BATCH):
        batch = items[start : start + TRIAGE_BATCH]
        listing = "\n\n".join(
            f"[{i['id']}] {i['title']}\ndomain={i['domain']} tier={i['tier']} date={i['date']}"
            f"{' URGENT' if i['urgent'] else ''} url={i['url']}\nnotes: {i['notes'][:TRIAGE_NOTES] or '(none)'}"
            for i in batch
        )
        result, u = deps.llm.parse(
            system=prompts.triage(deps.vault), prompt=listing, schema=TriageResult, effort=steps.effort("triage"), node="triage"
        )
        decisions.update({d.item_id: d.model_dump() for d in result.decisions})
        usage.append(u)
    missing = {"action": "drop", "reason": "no decision returned", "search_terms": []}
    return {
        "decisions": [decisions.get(i["id"], {**missing, "item_id": i["id"]}) for i in items],
        "usage": usage,
    }


# -- locate -------------------------------------------------------------
def locate(deps: Deps, state: WatchState) -> dict:
    evidence, decisions = {}, []
    for d in state["decisions"]:
        if d["action"] == "correct":
            excerpts = vault.search(deps.vault, d["search_terms"])
            if excerpts:
                evidence[d["item_id"]] = [{"page": e.page, "text": e.text} for e in excerpts]
            else:
                # Nothing to correct if no page names it: the vault may be missing the subject.
                d = {**d, "action": "addition",
                     "reason": f"no French page names it ({', '.join(d['search_terms'])}); {d['reason']}"}
        decisions.append(d)
    return {"evidence": evidence, "decisions": decisions}


def fan_out(state: WatchState):
    by_id = {i["id"]: i for i in state["items"]}
    sends = [
        Send("propose", {"items": [by_id[i] for i in ids], "excerpts": excerpts})
        for ids, excerpts in clusters(
            state["evidence"], {d["item_id"]: d["search_terms"] for d in state["decisions"]}
        )
    ]
    return sends or "number"


HUB_ITEMS = 4  # a page cited for more items than this is a hub: it does not merge groups
GROUP_EXCERPTS = 16000  # characters of excerpts per group, shared between its items…
ITEM_EXCERPTS = 6000  # …but never less than this per item


def clusters(evidence: dict[str, list[dict]], terms: dict[str, list[str]] | None = None) -> list[tuple[list[str], list[dict]]]:
    """Group items about the same tool or the same pages, so one call sees every edit of a page.

    Items sharing a search term (the tool name: seven Jan advisories) always merge.
    Items sharing a page merge too, except through hub pages (a security overview
    cited for many tools); the conflict check in `mark_conflicts` still catches two
    edits of the same passage.
    """
    pages_of = {i: {e["page"] for e in ex} for i, ex in evidence.items() if ex}
    for i, ts in (terms or {}).items():
        if i in pages_of:
            pages_of[i] |= {f"term:{t.strip().lower()}" for t in ts if len(t.strip()) >= 3}
    count: dict[str, int] = {}
    for pages in pages_of.values():
        for p in pages:
            count[p] = count.get(p, 0) + 1
    parent = {i: i for i in pages_of}

    def root(i: str) -> str:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[str, str] = {}
    for i, pages in pages_of.items():
        for p in pages:
            if count[p] > HUB_ITEMS and not p.startswith("term:"):
                continue
            if p in owner:
                parent[root(i)] = root(owner[p])
            else:
                owner[p] = i
    groups: dict[str, list[str]] = {}
    for i in pages_of:
        groups.setdefault(root(i), []).append(i)
    # Each item gets its own share: a shared budget let the first items of a group crowd out the last ones.
    return [(ids, _shared_excerpts(evidence, ids, max(ITEM_EXCERPTS, GROUP_EXCERPTS // len(ids)))) for ids in groups.values()]


def _shared_excerpts(evidence: dict[str, list[dict]], ids: list[str], share: int) -> list[dict]:
    """The excerpts of a group: each item's, up to `share` characters each, an excerpt two items share given once."""
    seen, excerpts = set(), []
    for i in ids:
        budget = share
        for e in evidence[i]:
            key = (e["page"], e["text"])
            if key in seen:
                continue
            if budget <= 0:
                break
            seen.add(key)
            excerpts.append(e)
            budget -= len(e["text"])
    return excerpts


# -- propose (one branch per group of items sharing pages, in parallel) ----
def propose(deps: Deps, payload: dict) -> dict:
    items, excerpts = payload["items"], payload["excerpts"]
    excerpts = vault.with_changes_page(deps.vault, excerpts)
    listing = "\n\n".join(
        f"<item id=\"{i['id']}\">\n{i['title']}\nurl: {i['url']}\ndate: {i['date']} tier: {i['tier']}"
        f"{' URGENT advisory' if i['urgent'] else ''}\nCached notes:\n{i['notes'] or '(none)'}\n</item>"
        for i in items
    )
    prompt = (
        f"Watch items:\n\n{listing}\n\nVault excerpts (French pages):\n\n"
        + "\n\n".join(f"<excerpt page=\"{e['page']}\">\n{e['text']}\n</excerpt>" for e in excerpts)
    )
    ids = [i["id"] for i in items]
    result, u = deps.llm.parse(
        system=prompts.propose(deps.vault), prompt=prompt, schema=ClusterProposal, effort=steps.effort("proposals"),
        node=f"propose {'+'.join(ids)}",
    )
    corrections = [
        {**c.model_dump(), "item_ids": [i for i in c.item_ids if i in ids] or ids[:1],
         "check": vault.check(deps.vault, c.page, c.current)}
        for c in result.corrections
    ]
    outcomes = {o.item_id: o for o in result.outcomes}
    proposal = {
        "item_ids": ids,
        "outcomes": [
            {"item_id": i, "event": outcomes[i].event if i in outcomes else "",
             "no_change_reason": outcomes[i].no_change_reason if i in outcomes else "no outcome returned"}
            for i in ids
        ],
        "corrections": corrections,
    }
    return {"proposals": [proposal], "usage": [u]}


# -- number: C1, C2… groups, conflicts --------------------------------------
def number(deps: Deps, state: WatchState) -> dict:
    proposals = sorted_proposals(state)
    corrections = [
        {"id": f"C{n}", "item_id": c["item_ids"][0], "proposal": pi, **c}
        for n, (pi, c) in enumerate(((pi, c) for pi, p in enumerate(proposals) for c in p["corrections"]), start=1)
    ]
    # A group is named after its first correction: "C1" for C1 + C2.
    first: dict[str, str] = {}
    for c in corrections:
        key = f"{c['proposal']}/{c['group']}" if c.get("group") else c["id"]
        c["group"] = first.setdefault(key, c["id"])
    trims = state.get("mode") == "compact"
    if state.get("mode") == "add":  # one call per lead: what two calls add to one page is made to fit
        news.merge(deps.vault, corrections)
    if trims:  # a note the trims leave without a sentence citing it goes with them
        corrections = compact.with_orphan_notes(deps.vault, corrections)
    mark_conflicts(deps.vault, corrections, trims)
    return {"corrections": corrections}


# -- crosscheck: every correction re-read against the whole French vault -----
def crosscheck_node(deps: Deps, state: WatchState) -> dict:
    corrections = state.get("corrections", [])
    if not deps.crosscheck or not corrections or state.get("mode") == "translation":
        return {}
    plan = reading.plan(deps.vault, deps.llm, step="crosscheck")  # the whole guide in one call, or by chapter
    if state.get("mode") == "compact":
        return _crosscheck_trims(deps, corrections, plan)
    result, usage, checks = crosscheck.run(deps.vault, corrections, deps.llm, plan)
    amended = crosscheck.amend(corrections, result, checks)
    mark_conflicts(deps.vault, amended)
    findings, excerpts = crosscheck.noticed(deps.vault, result)
    usages = [usage]
    swept = crosscheck.sweep(deps.vault, amended, deps.llm, plan)
    if swept:
        result, usage, checks = swept
        amended = crosscheck.add_edits(amended, result, checks, "the sweep")
        mark_conflicts(deps.vault, amended)
        more, found = crosscheck.noticed(deps.vault, result)
        findings += more
        excerpts.update(found)
        usages.append(usage)
    return {"corrections": amended, "findings": findings, "finding_excerpts": excerpts, "usage": usages,
            "leftovers": vault.leftovers(deps.vault, amended), "reading": plan.summary()}


def _crosscheck_trims(deps: Deps, corrections: list[dict], plan: reading.Plan) -> dict:
    """Trims: judged on what they lose, without the web; no sweep (a repetition removed leaves its values elsewhere
    on purpose), and the notes the revised trims orphan are removed with them."""
    corrections = [c for c in corrections if not c.get("auto")]  # the program's own removals: computed again below
    result, usage, checks = crosscheck.run(deps.vault, corrections, deps.llm, plan, system=compact.CROSSCHECK, web=False)
    amended = compact.with_orphan_notes(deps.vault, crosscheck.amend(corrections, result, checks))
    mark_conflicts(deps.vault, amended, True)
    findings, excerpts = crosscheck.noticed(deps.vault, result)
    return {"corrections": amended, "findings": findings, "finding_excerpts": excerpts, "usage": [usage],
            "leftovers": [], "reading": plan.summary()}


# -- report ---------------------------------------------------------------
def report(deps: Deps, state: WatchState) -> dict:
    name = (state["branch_name"].replace("/", "-") + ".md" if state.get("branch_name") else
            f"watch-{state['as_of']}" + (f"-issue{state['issue']}" if state.get("issue") else "") + ".md")
    path = deps.home / "reports" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    corrections = state.get("corrections", [])
    if state.get("mode") == "compact":  # what each trim removes that no page states any more
        gone = vault.lost(deps.vault, corrections)
        corrections = [{**c, "lost": gone.get(c["id"], [])} for c in corrections]
    elif state.get("mode") != "translation":
        unsourced = vault.unsourced_versions(deps.vault, corrections)
        corrections = [{**c, "warning": unsourced.get(c["id"], "")} for c in corrections]
    path.write_text(render_report(state, sorted_proposals(state), corrections), encoding="utf-8")
    note_additions(deps, state)
    return {"report_path": str(path), "corrections": corrections}


def note_additions(deps: Deps, state: WatchState) -> list[str]:
    """What a watch run set aside as possible additions (its report's « Addition candidates »): leads of the registry
    of candidates (D3.3), with the item's address and the reason, instead of a line forgotten in a report. Nothing
    when the guide does not use the registry; a registry that cannot be read leaves the run as it is."""
    items = {i["id"]: i for i in state.get("items", [])}
    found = [{"name": items[d["item_id"]]["title"], "url": items[d["item_id"]]["url"], "why": d.get("reason", "")}
             for d in state.get("decisions", []) if d.get("action") == "addition" and d.get("item_id") in items]
    origin = f"watch issue #{state['issue']}" if state.get("issue") else f"watch {state.get('as_of', deps.today)}"
    try:
        return candidates.note_all(vault.guide_of(deps.vault), deps.home, found, origin=origin, seen=deps.today)
    except (candidates.RegistryError, OSError, RuntimeError):
        return []
