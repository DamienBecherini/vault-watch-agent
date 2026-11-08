"""Fix run: errors noticed in the vault (by a cross-check, a reader, a review) become reviewed corrections.

There is no watch here: the model reads the whole French vault, checks each
reported error on primary sources (web search and fetch), and proposes exact
corrections. The result enters the same graph right after the proposals
(LangGraph `update_state(..., as_node="propose")`), so it goes through the same
numbering, cross-check, human review, apply, English mirror, audits and
go-ahead as a watch.
"""

from __future__ import annotations

import re
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


def propose(vault_dir: Path, findings: list[str], llm: LLM, system: str = SYSTEM, context: str | None = None,
            effort: str = "high", web: bool = True, node: str = "fix") -> tuple[list[dict], dict, dict]:
    items = [
        {"id": f"F{n}", "domain": "fix", "tier": "", "title": f, "url": "", "date": "", "urgent": False,
         "severity": "", "notes": ""}
        for n, f in enumerate(findings, start=1)
    ]
    listing = "\n".join(f"<error id=\"{i['id']}\">{i['title']}</error>" for i in items)
    result, usage = llm.parse(
        system=system, prompt=f"Reported errors:\n\n{listing}", schema=ClusterProposal, effort=effort,
        node=node, context=context or f"<guide>\n{vault.corpus(vault_dir)}\n</guide>", web=web,
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


TRANSLATION_SYSTEM = """You fix divergences between a French guide on running AI on-premise and its English translation.
The French page is the reference. For each reported divergence (F1…) you get, above, the French page and its English
mirror (`en/…`).

For each one:
- If it is not a real divergence (same meaning in other words, a cosmetic or `last_modified` difference, an alias or
  tag that is naturally in each language), give an outcome with no_change_reason.
- If the English page says something else, misses a passage, keeps untranslated French or misplaces a block, fix the
  English page (`page` = `en/…`): natural technical English, same Markdown, wiki link targets and footnote markers
  unchanged.
- If the French page itself is wrong (English left in the French text, an error both sides share because the
  French says it), fix the French page only: the English page will follow it automatically. Never fix both sides
  for the same passage.

`current` is copied verbatim from one page, short and unique in it; `proposed` is in the language of its page.
Never edit `last_modified`. `source_url` is the French page's path. One outcome per reported divergence."""

PAGE_PATH = re.compile(r"(?:en/)?((?:[\w.-]+/)*[\w.-]+\.mdx?)")


def pages_of(finding: str) -> list[str]:
    """The French page a translation finding is about, and its English mirror."""
    m = PAGE_PATH.search(finding)
    return [m.group(1), f"en/{m.group(1)}"] if m else []


def propose_translation(vault_dir: Path, findings: list[str], llm: LLM) -> tuple[list[dict], dict, dict]:
    """Same output as `propose`, from the French and English pages alone: no web, no whole guide."""
    pages = sorted({p for f in findings for p in pages_of(f) if (vault_dir / p).is_file()})
    context = "\n\n".join(f'<page path="{p}">\n{vault.read(vault_dir / p)}\n</page>' for p in pages)
    return propose(vault_dir, findings, llm, system=TRANSLATION_SYSTEM, context=context, effort="medium",
                   web=False, node="fix translation")


def initial_state(label: str, items: list[dict], proposal: dict, usage: dict, thread: str = "",
                  mode: str = "fix") -> dict:
    """`thread` names the branch (fix/<thread>): two fix runs on one day must not share a branch.
    `mode` "translation" skips the cross-check against the whole French guide."""
    today = date.today().isoformat()
    kind = "fix(i18n): reviewed translation fixes" if mode == "translation" else "fix(content): reviewed corrections"
    return {
        "source": f"errors reported in the vault ({label})",
        "issue": None,
        "as_of": today,
        "mode": mode,
        "title": f"{kind} of errors reported in the vault ({label})",
        "branch_name": f"fix/{thread or f'vault-errors-{today}'}",
        "items": items,
        "claims_due": [],
        "decisions": [],
        "evidence": {},
        "proposals": [proposal],
        "usage": [usage],
    }
