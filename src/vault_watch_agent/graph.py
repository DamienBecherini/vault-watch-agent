"""The graph: watch → triage → locate → propose (one branch per item) → report
→ human review → apply on a branch → English mirror → vault audits → human
go-ahead → pull request.

Two interrupts keep a human in the loop: nothing touches the vault before the
review, and nothing leaves the machine before the second go-ahead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from . import crosscheck, inputs, prompts, vault
from .llm import LLM
from .state import ClusterProposal, MirrorResult, TriageResult, WatchState

TRIAGE_BATCH = 40  # items per triage call
TRIAGE_NOTES = 1200  # characters of cached notes shown at triage


@dataclass
class Deps:
    vault: Path  # local clone of the vault (read-only until apply)
    home: Path  # working folder: downloads, reports, worktrees
    llm: LLM
    translator: LLM | None = None  # cheaper model for the English mirror; defaults to llm
    crosscheck: bool = True  # re-read the corrections against the whole French vault before the review
    repo: str = "DamienBecherini/ia-on-prem-vault"
    base: str = "main"
    today: str = field(default_factory=lambda: date.today().isoformat())


def git(*args: str, cwd: Path) -> str:
    return inputs.run(["git", *args], cwd=cwd)


def sorted_proposals(state: WatchState) -> list[dict]:
    order = {i["id"]: n for n, i in enumerate(state["items"])}
    return sorted(state.get("proposals", []), key=lambda p: order[p["item_ids"][0]])


def build(deps: Deps, checkpointer=None):
    # -- collect ------------------------------------------------------------
    def collect(state: WatchState) -> dict:
        if state.get("issue"):
            watch_json = inputs.download_watch(state["issue"], deps.repo, deps.home / "downloads")
        else:
            watch_json = Path(state["source"])
        items, until = inputs.load_items(watch_json)
        claims = inputs.claims_due(deps.vault, deps.home / "downloads" / f"freshness-{deps.today}.json")
        return {"items": items, "as_of": until or deps.today, "claims_due": claims}

    # -- triage -------------------------------------------------------------
    def triage(state: WatchState) -> dict:
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
                system=prompts.triage(deps.vault), prompt=listing, schema=TriageResult, effort="medium", node="triage"
            )
            decisions.update({d.item_id: d.model_dump() for d in result.decisions})
            usage.append(u)
        missing = {"action": "drop", "reason": "no decision returned", "search_terms": []}
        return {
            "decisions": [decisions.get(i["id"], {**missing, "item_id": i["id"]}) for i in items],
            "usage": usage,
        }

    # -- locate -------------------------------------------------------------
    def locate(state: WatchState) -> dict:
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

    # -- propose (one branch per group of items sharing pages, in parallel) ----
    def propose(payload: dict) -> dict:
        items, excerpts = payload["items"], payload["excerpts"]
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
            system=prompts.propose(deps.vault), prompt=prompt, schema=ClusterProposal, effort="high",
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
    def number(state: WatchState) -> dict:
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
        mark_conflicts(deps.vault, corrections)
        return {"corrections": corrections}

    # -- crosscheck: every correction re-read against the whole French vault -----
    def crosscheck_node(state: WatchState) -> dict:
        corrections = state.get("corrections", [])
        if not deps.crosscheck or not corrections:
            return {}
        result, usage, checks = crosscheck.run(deps.vault, corrections, deps.llm)
        amended = crosscheck.amend(corrections, result, checks)
        mark_conflicts(deps.vault, amended)
        return {"corrections": amended, "findings": result.other_findings, "usage": [usage]}

    # -- report ---------------------------------------------------------------
    def report(state: WatchState) -> dict:
        name = (state["branch_name"].replace("/", "-") + ".md" if state.get("branch_name") else
                f"watch-{state['as_of']}" + (f"-issue{state['issue']}" if state.get("issue") else "") + ".md")
        path = deps.home / "reports" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_report(state, sorted_proposals(state), state.get("corrections", [])), encoding="utf-8")
        return {"report_path": str(path)}

    # -- review (interrupt 1) -------------------------------------------------
    def review(state: WatchState) -> dict:
        corrections = state["corrections"]
        answer = interrupt(
            {
                "step": "review",
                "report": state["report_path"],
                "corrections": [
                    {"id": c["id"], "severity": c["severity"], "page": c["page"], "check": c["check"],
                     **({"group": c["group"]} if c["group"] != c["id"] or _has_members(corrections, c) else {})}
                    for c in corrections
                ],
                "question": "Which corrections to apply? 'all' (valid ones), 'none', or ids like C1,C3. "
                "A group is applied whole: naming one member accepts the others.",
            }
        )
        if answer == "all":
            asked = {c["id"] for c in corrections}
        elif answer == "none" or not answer:
            asked = set()
        else:
            asked = set(answer)
        groups = {c["group"] for c in corrections if c["id"] in asked}
        # A group with one member that fails the check cannot be applied consistently.
        broken = {c["group"] for c in corrections if c["check"] != "ok"}
        accepted = [c["id"] for c in corrections if c["group"] in groups - broken]
        return {"accepted": accepted}

    # -- apply ----------------------------------------------------------------
    def apply(state: WatchState) -> dict:
        # One branch per run: a watch is named after its window, a fix run after its own label.
        branch = state.get("branch_name") or f"chore/watch-{state['as_of']}"
        worktree = deps.home / "worktrees" / branch.replace("/", "-")
        if not worktree.exists():
            git("worktree", "add", "-B", branch, str(worktree), deps.base, cwd=deps.vault)
        chosen = [c for c in state["corrections"] if c["id"] in state["accepted"]]
        for c in chosen:
            vault.apply(worktree, c["page"], c["current"], c["proposed"], deps.today)
        pages = sorted({c["page"] for c in chosen})
        git("add", *pages, cwd=worktree)
        summary = ", ".join(f"{c['id']} {c['page']}" for c in chosen)
        git("commit", "-m", pr_title(state),
            "-m", summary, cwd=worktree)
        return {"branch": branch, "worktree": str(worktree), "applied": [c["id"] for c in chosen]}

    # -- mirror (English pages follow the French edits) --------------------------
    def mirror(state: WatchState) -> dict:
        wt = Path(state["worktree"])
        translator = deps.translator or deps.llm
        chosen = [c for c in state["corrections"] if c["id"] in state["applied"]]
        mirrored, problems, usage = [], [], []
        for page in sorted({c["page"] for c in chosen}):
            en = f"en/{page}"
            if not (wt / en).is_file():
                problems.append(f"{en}: no English mirror")
                continue
            edits = "\n\n".join(
                f"<edit>\n<old_french>\n{c['current']}\n</old_french>\n<new_french>\n{c['proposed']}\n</new_french>\n</edit>"
                for c in chosen if c["page"] == page
            )
            prompt = f"English page `{en}`:\n\n<english_page>\n{vault.read(wt / en)}\n</english_page>\n\nFrench edits:\n\n{edits}"
            result, u = translator.parse(
                system=prompts.mirror(deps.vault), prompt=prompt, schema=MirrorResult, effort="medium",
                node=f"mirror {en}",
            )
            usage.append(u)
            if result.problem:
                problems.append(f"{en}: {result.problem}")
            done = 0
            for e in result.edits:
                if vault.check(wt, en, e.current) == "ok":
                    vault.apply(wt, en, e.current, e.proposed, deps.today)
                    done += 1
                else:
                    problems.append(f"{en}: quoted English text not found exactly once, edit skipped")
            if done:
                mirrored.append(en)
        if mirrored:
            git("add", *mirrored, cwd=wt)
            git("commit", "-m", "chore(i18n): sync the English mirrors of the reviewed corrections", cwd=wt)
        return {"mirrored": mirrored, "mirror_problems": problems, "usage": usage}

    # -- audits (the vault's own checks, no model) ------------------------------
    def audits(state: WatchState) -> dict:
        try:
            log = inputs.run(["node", "scripts/run-audits.mjs"], cwd=Path(state["worktree"]))  # = npm test
            return {"audit_ok": True, "audit_log": log[-3000:]}
        except RuntimeError as e:
            return {"audit_ok": False, "audit_log": str(e)[-3000:]}

    # -- links: the external sources of the changed pages still answer (vault script, no model) --
    def links(state: WatchState) -> dict:
        wt = Path(state["worktree"])
        out = deps.home / "downloads" / f"sources-{state['branch'].replace('/', '-')}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            inputs.run(["node", "scripts/audit-sources.mjs", "--concurrency=8", "--timeout=15000", f"--json={out}"], cwd=wt)
        except RuntimeError as e:
            return {"link_problems": [f"source audit could not run: {str(e)[:200]}"]}
        added = git("diff", "-U0", f"{deps.base}...HEAD", cwd=wt)
        added = "\n".join(line for line in added.splitlines() if line.startswith("+"))
        return {"link_problems": link_problems(json.loads(out.read_text(encoding="utf-8")),
                                               {c["page"] for c in state["corrections"] if c["id"] in state["applied"]},
                                               added)}

    # -- publish (interrupt 2) -------------------------------------------------
    def publish(state: WatchState) -> dict:
        diffstat = git("diff", "--stat", f"{deps.base}...HEAD", cwd=Path(state["worktree"]))
        go = interrupt(
            {
                "step": "publish",
                "branch": state["branch"],
                "audit_ok": state["audit_ok"],
                "mirror_problems": state.get("mirror_problems", []),
                "link_problems": state.get("link_problems", []),
                "diffstat": diffstat,
                "question": "Push the branch and open the pull request? yes / no",
            }
        )
        if go is not True:
            return {}
        wt = Path(state["worktree"])
        git("push", "-u", "origin", state["branch"], cwd=wt)
        body = pr_body(state)
        url = inputs.run(
            ["gh", "pr", "create", "--repo", deps.repo, "--base", deps.base, "--head", state["branch"],
             "--title", pr_title(state), "--body", body],
            cwd=wt,
        ).strip()
        return {"pr_url": url}

    g = StateGraph(WatchState)
    for name, fn in [("collect", collect), ("triage", triage), ("locate", locate), ("propose", propose),
                     ("number", number), ("crosscheck", crosscheck_node), ("report", report),
                     ("review", review), ("apply", apply), ("mirror", mirror), ("audits", audits),
                     ("links", links), ("publish", publish)]:
        g.add_node(name, fn)
    g.add_edge(START, "collect")
    g.add_edge("collect", "triage")
    g.add_edge("triage", "locate")
    g.add_conditional_edges("locate", fan_out, ["propose", "number"])
    g.add_edge("propose", "number")
    g.add_edge("number", "crosscheck")
    g.add_edge("crosscheck", "report")
    g.add_edge("report", "review")
    g.add_conditional_edges("review", lambda s: "apply" if s.get("accepted") else END, ["apply", END])
    g.add_edge("apply", "mirror")
    g.add_edge("mirror", "audits")
    g.add_edge("audits", "links")
    g.add_edge("links", "publish")
    g.add_edge("publish", END)
    return g.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


HUB_ITEMS = 4  # a page cited for more items than this is a hub: it does not merge groups
GROUP_EXCERPTS = 16000  # characters of excerpts per group


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
    out = []
    for ids in groups.values():
        seen, excerpts, budget = set(), [], GROUP_EXCERPTS
        for i in ids:
            for e in evidence[i]:
                key = (e["page"], e["text"])
                if key not in seen and budget > 0:
                    seen.add(key)
                    excerpts.append(e)
                    budget -= len(e["text"])
        out.append((ids, excerpts))
    return out


def mark_conflicts(vault_dir: Path, corrections: list[dict]) -> None:
    """Two corrections that edit overlapping text of a page cannot both apply: the later one is refused."""
    spans: dict[str, list[tuple[int, int, str]]] = {}
    for c in corrections:
        if c["check"] != "ok":
            continue
        text = vault.read(vault_dir / c["page"]).replace("\r\n", "\n")
        start = text.find(c["current"].replace("\r\n", "\n"))
        end = start + len(c["current"])
        clash = next((cid for s, e, cid in spans.get(c["page"], []) if start < e and s < end), None)
        if clash:
            c["check"] = f"conflict with {clash}"
        else:
            spans.setdefault(c["page"], []).append((start, end, c["id"]))


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _has_members(corrections: list[dict], c: dict) -> bool:
    return any(o["group"] == c["id"] and o["id"] != c["id"] for o in corrections)


def render_report(state: WatchState, proposals: list[dict], corrections: list[dict]) -> str:
    items = {i["id"]: i for i in state["items"]}
    decisions = state["decisions"]
    count = {a: sum(1 for d in decisions if d["action"] == a) for a in ("correct", "addition", "drop")}
    sev = {s: sum(1 for c in corrections if c["severity"] == s) for s in ("Critical", "Major", "Minor")}
    lines = [
        f"# Watch report — {state['as_of']}",
        "",
        f"Source: {state['source']}. Generated by vault-watch-agent. **Read-only: no page modified** "
        "until the review.",
        "",
        "| Step | Result |",
        "| :-- | :-- |",
        f"| Triage | {len(items)} items → correct {count['correct']} · addition {count['addition']} · drop {count['drop']} |",
        f"| Proposals | Critical {sev['Critical']} · Major {sev['Major']} · Minor {sev['Minor']} |",
        f"| Claims past « Recheck by » | {len(state.get('claims_due', []))} (listed below, not re-checked yet) |",
        f"| Model usage | {usage_line(state.get('usage', []))} |",
        "",
        "## Corrections",
        "",
    ]
    if not corrections:
        lines.append("None.")
    # Members of a group side by side, including the ones the cross-check added
    num = lambda cid: int(cid[1:])
    for c in sorted(corrections, key=lambda c: (num(c["group"]), num(c["id"]))):
        item = items[c["item_id"]]
        check = "" if c["check"] == "ok" else f" — ⚠️ **{c['check']}**: cannot be applied as is"
        grouped = c["group"] != c["id"] or _has_members(corrections, c)
        group = f" · group {c['group']} (applied whole)" if grouped else ""
        lines += [
            f"### {c['id']} · {c['severity']} · `{c['page']}`{group}{check}",
            "",
            f"From {', '.join(c['item_ids'])} [{item['title']}]({item['url']}). {c['rationale']}",
            "",
            *([f"Cross-check: {c['review']}", ""] if c.get("review") else []),
            "Current:",
            "",
            *[f"> {line}" for line in c["current"].splitlines()],
            "",
            "Proposed (revised by the cross-check):" if c.get("proposed_initial") else "Proposed:",
            "",
            *[f"> {line}" for line in c["proposed"].splitlines()],
            "",
            f"Source: {c['source_url']}",
            "",
        ]
    lines += ["## Events and items without change", "", "| Item | Event | Why no change |", "| :-- | :-- | :-- |"]
    used = {i for c in corrections for i in c["item_ids"]}
    for p in proposals:
        for o in p["outcomes"]:
            if o["item_id"] not in used:
                lines.append(f"| {o['item_id']} {_cell(items[o['item_id']]['title'])} | {_cell(o['event'])} | {_cell(o['no_change_reason'])} |")
    lines += ["", "## Addition candidates (not written, opportunity notes need a go-ahead)", ""]
    adds = [d for d in decisions if d["action"] == "addition"]
    lines += [f"- {d['item_id']} [{items[d['item_id']]['title']}]({items[d['item_id']]['url']}): {d['reason']}" for d in adds] or ["None."]
    lines += ["", "## Noticed elsewhere in the vault by the cross-check (not proposed)", ""]
    lines += [f"- {f}" for f in state.get("findings", [])] or ["None."]
    lines += ["", "## Claims due for re-check", ""]
    for claim in state.get("claims_due", []):
        lines.append(f"- {claim.get('recheckBy', '')} `{claim.get('page', '')}`: {_cell(str(claim.get('claim', '')))}")
    if not state.get("claims_due"):
        lines.append("None.")
    lines += ["", "## Dropped at triage", ""]
    lines += [f"- {d['item_id']} {items[d['item_id']]['title']}: {d['reason']}" for d in decisions if d["action"] == "drop"]
    return "\n".join(lines) + "\n"


def usage_line(usage: list[dict]) -> str:
    tokens_in = sum(u["input"] + u.get("cache_read", 0) + u.get("cache_write", 0) for u in usage)
    tokens_out = sum(u["output"] for u in usage)
    cache = sum(u.get("cache_read", 0) for u in usage)
    cost = sum(u.get("cost_usd", 0.0) for u in usage)
    return f"{len(usage)} calls, {tokens_in:,} in ({cache:,} from cache) / {tokens_out:,} out, ≈ {cost:.2f} $"


BROKEN = {"dead", "server-error", "network-error", "timeout"}


def link_problems(report: dict, pages: set[str], added: str) -> list[str]:
    """Sources of the changed pages that do not answer, new ones (added by this run) first.

    `blocked` (403 from anti-bot protections) is listed apart: the page usually opens in a browser.
    """
    rows = []
    for s in report.get("sources", []):
        status = (s.get("probe") or {}).get("status")
        cited = sorted({c["page"] for c in s.get("citations", []) if c["page"] in pages})
        if not cited or status not in BROKEN | {"blocked"}:
            continue
        new = s["url"] in added
        code = (s.get("probe") or {}).get("code") or ""
        label = "blocked by the site (anti-bot?), check in a browser" if status == "blocked" else f"{status} {code}".strip()
        rows.append((status == "blocked", not new, f"{'NEW ' if new else ''}{label}: {s['url']} ({', '.join(cited)})"))
    return [r[2] for r in sorted(rows)]


def pr_title(state: WatchState) -> str:
    return state.get("title") or f"chore(watch): reviewed corrections, watch of {state['as_of']}"


def pr_body(state: WatchState) -> str:
    applied = [c for c in state["corrections"] if c["id"] in state.get("applied", [])]
    rows = "\n".join(f"| {c['id']} | {c['severity']} | `{c['page']}` | {_cell(c['rationale'])} | {c['source_url']} |" for c in applied)
    return (
        f"Corrections from {state['source']}, reviewed before apply.\n\n"
        "| # | Severity | Page | Why | Source |\n| :-- | :-- | :-- | :-- | :-- |\n"
        f"{rows}\n\n"
        f"Vault audits (`npm test`): {'passed' if state.get('audit_ok') else 'FAILED, see the log below'}.\n\n"
        f"English mirrors updated: {', '.join(f'`{p}`' for p in state.get('mirrored', [])) or 'none'}.\n"
        + "".join(f"- ⚠️ {p}\n" for p in state.get("mirror_problems", []))
        + "\nExternal sources of the changed pages (`scripts/audit-sources.mjs`): "
        + ("all answer.\n" if not state.get("link_problems") else
           "\n" + "".join(f"- {p}\n" for p in state["link_problems"]))
        +("" if state.get("audit_ok") else f"\n```\n{state.get('audit_log', '')}\n```\n")
    )


def describe(state: WatchState) -> str:
    """Short JSON view of a paused run for the CLI."""
    keep = {k: state.get(k) for k in ("source", "as_of", "report_path", "accepted", "branch", "audit_ok", "pr_url")}
    return json.dumps(keep, ensure_ascii=False, indent=2)
