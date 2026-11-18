"""Fix run: errors noticed in the vault (by a cross-check, a reader, a review) become reviewed corrections.

There is no watch here: the model reads the whole guide, checks each
reported error on primary sources (web search and fetch), and proposes exact
corrections. The result enters the same graph right after the proposals
(LangGraph `update_state(..., as_node="propose")`), so it goes through the same
numbering, cross-check, human review, apply, mirrors, audits and
go-ahead as a watch.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import prompts, steps, vault
from .llm import LLM
from .state import ClusterProposal

SYSTEM = """You fix errors reported in <<GUIDE>>. The whole guide
is above, one <page> per file. Each reported error has an id (F1…).

For each one:
- Check it against the guide and against primary sources: vendor documentation, release notes, specifications,
  papers (use web_search and web_fetch). Never rely on memory for a figure, a version or a date.
- If the report is wrong or the guide is already right, give an outcome with no_change_reason.
- If it is right, propose the smallest corrections that make the guide true and consistent: every page that
  states the wrong fact, with the figure, sentence or table row fixed. Recompute numbers yourself (show the
  formula in the rationale) and keep them consistent with the pages that are already right.

Corrections follow the guide's style: <<LANG>>, same Markdown, wiki links [[...]] and footnote markers kept,
dated wording for facts that move. `current` is copied verbatim from one page, short; `item_ids` lists the
reported errors it fixes; `source_url` is the primary source you checked (or the page of the guide that is
right, for an internal inconsistency). Group with a shared `group` label the corrections that only make sense
together. One outcome per reported error."""


def _passages(item: dict) -> str:
    """The passages a reported error is about, as found in the pages when it was reported."""
    return "".join(f"\n<passage page=\"{e['page']}\" line=\"{e['line']}\">{e['quote']}</passage>"
                   for e in item.get("excerpts", []) if e["match"] == "exact")


def propose(vault_dir: Path, findings: list[str], llm: LLM, system: str = SYSTEM, context: str | None = None,
            effort: str = "", web: bool = True, node: str = "fix",
            excerpts: dict[str, list[dict]] | None = None) -> tuple[list[dict], dict, dict]:
    """`excerpts`: per finding, the passages found in the pages (`quotes.locate`), shown in the pull request."""
    if "<<" in system:  # written with the markers of prompts.fill
        system = prompts.fill(system, vault_dir)
    items = [
        {"id": f"F{n}", "domain": "fix", "tier": "", "title": f, "url": "", "date": "", "urgent": False,
         "severity": "", "notes": "", "excerpts": (excerpts or {}).get(f, [])}
        for n, f in enumerate(findings, start=1)
    ]
    listing = "\n".join(f"<error id=\"{i['id']}\">{i['title']}{_passages(i)}</error>" for i in items)
    result, usage = llm.parse(
        system=system, prompt=f"Reported errors:\n\n{listing}", schema=ClusterProposal, effort=effort or steps.effort("fix"),
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


TRANSLATION_SYSTEM = """You fix divergences between <<GUIDE>> and its <<MIRROR>> translation.
The <<LANG>> page is the reference. For each reported divergence (F1…) you get, above, the <<LANG>> page and its <<MIRROR>>
mirror (`<<MIRROR_DIR>>…`).

For each one:
- If it is not a real divergence (same meaning in other words, a cosmetic or `last_modified` difference, an alias or
  tag that is naturally in each language), give an outcome with no_change_reason.
- If the <<MIRROR>> page says something else, misses a passage, keeps untranslated <<LANG>> or misplaces a block, fix the
  <<MIRROR>> page (`page` = `<<MIRROR_DIR>>…`): natural technical <<MIRROR>>, same Markdown, wiki link targets and
  footnote markers unchanged.
- If the <<LANG>> page itself is wrong (<<MIRROR>> left in the <<LANG>> text, an error both sides share because the
  <<LANG>> says it), fix the <<LANG>> page only: the <<MIRROR>> page will follow it automatically. Never fix both sides
  for the same passage.

Fix every instance a report lists, not a sample: when it names several footnotes or lines, one correction per
footnote or line. To move a block (a footnote definition in the wrong place), use two corrections with the same
`group`: one removes it where it is, the other inserts it where it belongs (`current` = the line it must follow,
`proposed` = that line, a newline, then the block). A correction must change something.

`current` is copied verbatim from one page, short and unique in it; `proposed` is in the language of its page.
Never edit the date of the front matter. `source_url` is the <<LANG>> page's path. One outcome per reported
divergence."""

PAGE_PATH = re.compile(r"(?:[\w.-]+/)*[\w.-]+\.mdx?")


def pages_of(finding: str, vault_dir: Path) -> tuple[list[str], str | None]:
    """The source page a translation finding is about and its mirror page, and the mirror's language: the finding
    names the mirror page (`en/a/b.md`) or the source page."""
    m = PAGE_PATH.search(finding)
    if not m:
        return [], None
    path, guide = m.group(0), vault.guide_of(vault_dir)
    for code, folder in sorted(guide.mirrors.items()):
        if path.startswith(folder):
            return [path[len(folder):], path], code
    code = next(iter(sorted(guide.mirrors)), None)
    return ([path, guide.mirror_of(path, code)] if code else [path]), code


def propose_translation(vault_dir: Path, findings: list[str], llm: LLM,
                        excerpts: dict[str, list[dict]] | None = None) -> tuple[list[dict], dict, dict]:
    """Same output as `propose`, from the source and mirror pages alone: no web, no whole guide. The findings are
    about one mirror (a verification checks each mirror apart): the first one that names its mirror gives it."""
    found = [pages_of(f, vault_dir) for f in findings]
    mirror = next((code for _, code in found if code), None)
    pages = sorted({p for paths, _ in found for p in paths if (vault_dir / p).is_file()})
    context = "\n\n".join(f'<page path="{p}">\n{vault.read(vault_dir / p)}\n</page>' for p in pages)
    system = prompts.fill(TRANSLATION_SYSTEM, vault_dir, mirror) if mirror else prompts.fill(SYSTEM, vault_dir)
    return propose(vault_dir, findings, llm, system=system, context=context, effort=steps.effort("fix-translation"),
                   web=False, node="fix translation", excerpts=excerpts)


def initial_state(label: str, items: list[dict], proposal: dict, usage: dict, thread: str = "",
                  mode: str = "fix") -> dict:
    """`thread` names the branch (fix/<thread>): two fix runs on one day must not share a branch.
    `mode` "translation" skips the cross-check against the whole guide."""
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
