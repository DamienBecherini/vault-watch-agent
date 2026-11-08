"""Fix run: errors noticed in the vault (by a cross-check, a reader, a review) become reviewed corrections.

There is no watch here: the model reads the whole French vault, checks each
reported error on primary sources (web search and fetch), and proposes exact
corrections. The result enters the same graph right after the proposals
(LangGraph `update_state(..., as_node="propose")`), so it goes through the same
numbering, cross-check, human review, apply, English mirror, audits and
go-ahead as a watch.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from . import vault
from .llm import LLM
from .state import ClusterProposal

SYSTEM = """You fix errors reported in a French-language guide on running AI on-premise for SMEs. The whole French guide
is above, one <page> per file. Each reported error has an id (F1…).

For each one:
- Check it against the guide and against primary sources: vendor documentation, release notes, specifications,
  papers (use web_search and web_fetch). Never rely on memory for a figure, a version or a date.
- If the report is wrong or the guide is already right, give an outcome with no_change_reason.
- If it is right, propose the smallest corrections that make the guide true and consistent: every page that
  states the wrong fact, with the figure, sentence or table row fixed. Recompute numbers yourself (show the
  formula in the rationale) and keep them consistent with the pages that are already right.

Corrections follow the guide's style: French, same Markdown, wiki links [[...]] and footnote markers kept,
dated wording for facts that move. `current` is copied verbatim from one page, short; `item_ids` lists the
reported errors it fixes; `source_url` is the primary source you checked (or the page of the guide that is
right, for an internal inconsistency). Group with a shared `group` label the corrections that only make sense
together. One outcome per reported error."""


def propose(vault_dir: Path, findings: list[str], llm: LLM) -> tuple[list[dict], dict, dict]:
    items = [
        {"id": f"F{n}", "domain": "fix", "tier": "", "title": f, "url": "", "date": "", "urgent": False,
         "severity": "", "notes": ""}
        for n, f in enumerate(findings, start=1)
    ]
    listing = "\n".join(f"<error id=\"{i['id']}\">{i['title']}</error>" for i in items)
    result, usage = llm.parse(
        system=SYSTEM, prompt=f"Reported errors:\n\n{listing}", schema=ClusterProposal, effort="high",
        node="fix", context=f"<guide>\n{vault.corpus(vault_dir)}\n</guide>", web=True,
    )
    ids = [i["id"] for i in items]
    corrections = [
        {**c.model_dump(), "item_ids": [i for i in c.item_ids if i in ids] or ids[:1],
         "check": vault.check(vault_dir, c.page, c.current)}
        for c in result.corrections
    ]
    outcomes = {o.item_id: o for o in result.outcomes}
    proposal = {
        "item_ids": ids,
        "outcomes": [{"item_id": i, "event": outcomes[i].event if i in outcomes else "",
                      "no_change_reason": outcomes[i].no_change_reason if i in outcomes else "no outcome returned"}
                     for i in ids],
        "corrections": corrections,
    }
    return items, proposal, usage


def initial_state(label: str, items: list[dict], proposal: dict, usage: dict) -> dict:
    today = date.today().isoformat()
    return {
        "source": f"errors reported in the vault ({label})",
        "issue": None,
        "as_of": today,
        "title": f"fix(content): reviewed corrections of errors reported in the vault ({label})",
        "branch_name": f"fix/vault-errors-{today}",
        "items": items,
        "claims_due": [],
        "decisions": [],
        "evidence": {},
        "proposals": [proposal],
        "usage": [usage],
    }
