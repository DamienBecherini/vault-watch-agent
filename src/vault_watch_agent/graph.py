"""The graph: watch → triage → locate → propose (one branch per item) → report
→ human review → apply on a branch → vault audits → human go-ahead → pull request.

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

from . import inputs, prompts, vault
from .llm import LLM
from .state import ItemProposal, TriageResult, WatchState

TRIAGE_BATCH = 40  # items per triage call
TRIAGE_NOTES = 1200  # characters of cached notes shown at triage


@dataclass
class Deps:
    vault: Path  # local clone of the vault (read-only until apply)
    home: Path  # working folder: downloads, reports, worktrees
    llm: LLM
    repo: str = "DamienBecherini/ia-on-prem-vault"
    base: str = "main"
    today: str = field(default_factory=lambda: date.today().isoformat())


def git(*args: str, cwd: Path) -> str:
    return inputs.run(["git", *args], cwd=cwd)


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
                system=prompts.TRIAGE, prompt=listing, schema=TriageResult, effort="medium", node="triage"
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
        evidence = {}
        for d in state["decisions"]:
            if d["action"] == "correct":
                excerpts = vault.search(deps.vault, d["search_terms"])
                evidence[d["item_id"]] = [{"page": e.page, "text": e.text} for e in excerpts]
        return {"evidence": evidence}

    def fan_out(state: WatchState):
        by_id = {i["id"]: i for i in state["items"]}
        sends = [
            Send("propose", {"item": by_id[item_id], "excerpts": excerpts})
            for item_id, excerpts in state["evidence"].items()
            if excerpts
        ]
        return sends or "report"

    # -- propose (one branch per item, run in parallel) ----------------------
    def propose(payload: dict) -> dict:
        item, excerpts = payload["item"], payload["excerpts"]
        prompt = (
            f"Item {item['id']}: {item['title']}\nurl: {item['url']}\ndate: {item['date']} tier: {item['tier']}"
            f"{' URGENT advisory' if item['urgent'] else ''}\n\nCached notes:\n{item['notes'] or '(none)'}\n\n"
            "Vault excerpts (French pages):\n\n"
            + "\n\n".join(f"<excerpt page=\"{e['page']}\">\n{e['text']}\n</excerpt>" for e in excerpts)
        )
        result, u = deps.llm.parse(
            system=prompts.PROPOSE, prompt=prompt, schema=ItemProposal, effort="high", node=f"propose {item['id']}"
        )
        corrections = [
            {**c.model_dump(), "check": vault.check(deps.vault, c.page, c.current)} for c in result.corrections
        ]
        proposal = {
            "item_id": item["id"],
            "event": result.event,
            "no_change_reason": result.no_change_reason,
            "corrections": corrections,
        }
        return {"proposals": [proposal], "usage": [u]}

    # -- report ---------------------------------------------------------------
    def report(state: WatchState) -> dict:
        order = {i["id"]: n for n, i in enumerate(state["items"])}
        proposals = sorted(state.get("proposals", []), key=lambda p: order[p["item_id"]])
        corrections = [
            {"id": f"C{n}", "item_id": p["item_id"], **c}
            for n, (p, c) in enumerate(((p, c) for p in proposals for c in p["corrections"]), start=1)
        ]
        name = f"watch-{state['as_of']}" + (f"-issue{state['issue']}" if state.get("issue") else "") + ".md"
        path = deps.home / "reports" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_report(state, proposals, corrections), encoding="utf-8")
        return {"corrections": corrections, "report_path": str(path)}

    # -- review (interrupt 1) -------------------------------------------------
    def review(state: WatchState) -> dict:
        valid = [c for c in state["corrections"] if c["check"] == "ok"]
        answer = interrupt(
            {
                "step": "review",
                "report": state["report_path"],
                "corrections": [
                    {"id": c["id"], "severity": c["severity"], "page": c["page"], "check": c["check"]}
                    for c in state["corrections"]
                ],
                "question": "Which corrections to apply? 'all' (valid ones), 'none', or ids like C1,C3.",
            }
        )
        valid_ids = [c["id"] for c in valid]
        if answer == "all":
            accepted = valid_ids
        elif answer == "none" or not answer:
            accepted = []
        else:
            accepted = [i for i in answer if i in valid_ids]
        return {"accepted": accepted}

    # -- apply ----------------------------------------------------------------
    def apply(state: WatchState) -> dict:
        branch = f"chore/watch-{deps.today}"
        worktree = deps.home / "worktrees" / branch.replace("/", "-")
        if not worktree.exists():
            git("worktree", "add", "-B", branch, str(worktree), deps.base, cwd=deps.vault)
        chosen = [c for c in state["corrections"] if c["id"] in state["accepted"]]
        for c in chosen:
            vault.apply(worktree, c["page"], c["current"], c["proposed"], deps.today)
        pages = sorted({c["page"] for c in chosen})
        git("add", *pages, cwd=worktree)
        summary = ", ".join(f"{c['id']} {c['page']}" for c in chosen)
        git("commit", "-m", f"chore(watch): apply reviewed corrections of the watch of {state['as_of']}",
            "-m", summary, cwd=worktree)
        return {"branch": branch, "worktree": str(worktree), "applied": [c["id"] for c in chosen]}

    # -- audits (the vault's own checks, no model) ------------------------------
    def audits(state: WatchState) -> dict:
        try:
            log = inputs.run(["node", "scripts/run-audits.mjs"], cwd=Path(state["worktree"]))  # = npm test
            return {"audit_ok": True, "audit_log": log[-3000:]}
        except RuntimeError as e:
            return {"audit_ok": False, "audit_log": str(e)[-3000:]}

    # -- publish (interrupt 2) -------------------------------------------------
    def publish(state: WatchState) -> dict:
        diffstat = git("diff", "--stat", f"{deps.base}...HEAD", cwd=Path(state["worktree"]))
        go = interrupt(
            {
                "step": "publish",
                "branch": state["branch"],
                "audit_ok": state["audit_ok"],
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
             "--title", f"chore(watch): reviewed corrections, watch of {state['as_of']}", "--body", body],
            cwd=wt,
        ).strip()
        return {"pr_url": url}

    g = StateGraph(WatchState)
    for name, fn in [("collect", collect), ("triage", triage), ("locate", locate), ("propose", propose),
                     ("report", report), ("review", review), ("apply", apply), ("audits", audits),
                     ("publish", publish)]:
        g.add_node(name, fn)
    g.add_edge(START, "collect")
    g.add_edge("collect", "triage")
    g.add_edge("triage", "locate")
    g.add_conditional_edges("locate", fan_out, ["propose", "report"])
    g.add_edge("propose", "report")
    g.add_edge("report", "review")
    g.add_conditional_edges("review", lambda s: "apply" if s.get("accepted") else END, ["apply", END])
    g.add_edge("apply", "audits")
    g.add_edge("audits", "publish")
    g.add_edge("publish", END)
    return g.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


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
    for c in corrections:
        item = items[c["item_id"]]
        check = "" if c["check"] == "ok" else f" — ⚠️ **{c['check']}**: cannot be applied as is"
        lines += [
            f"### {c['id']} · {c['severity']} · `{c['page']}`{check}",
            "",
            f"From {c['item_id']} [{item['title']}]({item['url']}). {c['rationale']}",
            "",
            "Current:",
            "",
            *[f"> {line}" for line in c["current"].splitlines()],
            "",
            "Proposed:",
            "",
            *[f"> {line}" for line in c["proposed"].splitlines()],
            "",
            f"Source: {c['source_url']}",
            "",
        ]
    lines += ["## Events and items without change", "", "| Item | Event | Why no change |", "| :-- | :-- | :-- |"]
    for p in proposals:
        if not p["corrections"]:
            lines.append(f"| {p['item_id']} {_cell(items[p['item_id']]['title'])} | {_cell(p['event'])} | {_cell(p['no_change_reason'])} |")
    located = state.get("evidence", {})
    for d in decisions:
        if d["action"] == "correct" and not located.get(d["item_id"]):
            lines.append(f"| {d['item_id']} {_cell(items[d['item_id']]['title'])} | | no French page names it ({', '.join(d['search_terms'])}) |")
    lines += ["", "## Addition candidates (not written, opportunity notes need a go-ahead)", ""]
    adds = [d for d in decisions if d["action"] == "addition"]
    lines += [f"- {d['item_id']} [{items[d['item_id']]['title']}]({items[d['item_id']]['url']}): {d['reason']}" for d in adds] or ["None."]
    lines += ["", "## Claims due for re-check", ""]
    for claim in state.get("claims_due", []):
        lines.append(f"- {claim.get('recheckBy', '')} `{claim.get('page', '')}`: {_cell(str(claim.get('claim', '')))}")
    if not state.get("claims_due"):
        lines.append("None.")
    lines += ["", "## Dropped at triage", ""]
    lines += [f"- {d['item_id']} {items[d['item_id']]['title']}: {d['reason']}" for d in decisions if d["action"] == "drop"]
    return "\n".join(lines) + "\n"


# Opus 5.5 / Sonnet 5.5 list prices, USD per million tokens (input, output).
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0)}


def usage_line(usage: list[dict]) -> str:
    tokens_in = sum(u["input"] for u in usage)
    tokens_out = sum(u["output"] for u in usage)
    cost = sum(
        u["input"] / 1e6 * PRICES.get(u["model"], (0, 0))[0] + u["output"] / 1e6 * PRICES.get(u["model"], (0, 0))[1]
        for u in usage
    )
    return f"{len(usage)} calls, {tokens_in:,} in / {tokens_out:,} out, ≈ {cost:.2f} $"


def pr_body(state: WatchState) -> str:
    applied = [c for c in state["corrections"] if c["id"] in state.get("applied", [])]
    rows = "\n".join(f"| {c['id']} | {c['severity']} | `{c['page']}` | {_cell(c['rationale'])} | {c['source_url']} |" for c in applied)
    return (
        f"Corrections from the ecosystem watch of {state['as_of']} ({state['source']}), reviewed before apply.\n\n"
        "| # | Severity | Page | Why | Source |\n| :-- | :-- | :-- | :-- | :-- |\n"
        f"{rows}\n\n"
        f"Vault audits (`npm test`): {'passed' if state.get('audit_ok') else 'FAILED, see the log below'}.\n\n"
        "EN mirrors are not updated in this PR yet.\n"
        + ("" if state.get("audit_ok") else f"\n```\n{state.get('audit_log', '')}\n```\n")
    )


def describe(state: WatchState) -> str:
    """Short JSON view of a paused run for the CLI."""
    keep = {k: state.get(k) for k in ("source", "as_of", "report_path", "accepted", "branch", "audit_ok", "pr_url")}
    return json.dumps(keep, ensure_ascii=False, indent=2)
