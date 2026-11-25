"""The editor's edits checked before the other languages follow them (H4.2): an option of the page « Languages ».

The editor writes in the guide's language, in Obsidian, then asks the page « Languages » for the mirrors to follow.
Before that, three checks can be ticked, each with its estimate, on the passages that changed (mirrors.changes):

  - spelling: spelling, grammar, typos, by the translation model, on the passages alone;
  - facts: the facts the passages state, true, current and relevant to their page, by the reasoning model with the
    web, each page given whole for its context;
  - consistency: the rest of the guide against the passages, by the cross-check (crosscheck.run, the whole guide in
    its cache): what the edits contradict or make outdated elsewhere, and an edit the guide contradicts.

Each finding is a fix: a short quote of the page as it is in the folder, its replacement, the reason (and the
source for a fact); a doubt without a fix is a note. Nothing changes until the editor accepts a fix: it is then
applied in the guide's folder, as if typed there (vault.apply, the quote found once), and the sync carries it with
the rest. A fix of another page (consistency) makes that page one more to sync.

    found = run(folder, [("03-stack/engines.md", [(old, new)])], {"spelling"}, translator, llm)
    applied = accept(folder, found["fixes"], ["F1"], {}, today)
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from . import crosscheck, prompts, reading, steps, vault
from .llm import LLM

CHECKS = ("spelling", "facts", "consistency")


class Fix(BaseModel):
    page: str = Field(description="The page, as given.")
    current: str = Field(description="Exact text copied from the passage as written now, short: a few words to one "
                                     "sentence, found once in the page.")
    proposed: str = Field(description="The same text with the fix, nothing else changed.")
    reason: str = Field(description="One sentence, in English.")
    source_url: str = Field(default="", description="The primary source that settles a fact; empty for a spelling fix.")


class Fixes(BaseModel):
    fixes: list[Fix]
    notes: list[str] = Field(default_factory=list, description="Doubts without a fix, one line each, naming the page.")


SPELLING = """You proofread passages that the editor of <<GUIDE>> has just written or changed.
Fix only what is wrong in <<LANG>>: spelling, grammar, agreement, conjugation, a typo, a missing or doubled word,
wrong punctuation. Never the style, the wording or the length of a correct sentence, never a fact, never the
Markdown, the links ([[wiki links]], [^notes]) or the code. Quote `current` verbatim from the new text of a passage,
as short as the fix allows, and give `proposed` with the fix alone. No fix: an empty list. `notes` stays empty."""

FACTS = """You check the facts of passages that the editor of <<GUIDE>> has just written or changed. Each passage
comes with its whole page, for its context; judge the new text of the passages only.
For each fact a passage states (a version, a date, a figure, a price, a name, what a product can do), search the
web for its primary source (the vendor, the project, the standard) and check it:
- true and current: say nothing;
- wrong or outdated, and a primary source shows the right value: a fix, quoting `current` verbatim from the new
  text (short), with `proposed` stating the current fact in the page's style, the reason and the `source_url`;
- doubtful, with no source to settle it, or not relevant to its page: a note, not a fix.
A video, a forum or a blog that only repeats a vendor is a lead, never a source. Never fix the style or the
spelling. <<REPLACE>>"""

CONSISTENCY = """You read <<GUIDE>> after its editor changed some passages by hand. The whole guide is above, one
<page> per file, already with the editor's changes: each change below gives the passage before and after.
- reviews: for each change, keep it, or revise it only if the rest of the guide or a primary source shows that its
  new text is wrong (give the full revised text that would replace the new text). Never reject: the text is the
  editor's.
- consistency_edits: the other passages of the guide that the changes make wrong, outdated or contradictory (another
  page that states the old value, a summary table, a recommendation that no longer holds). Quote `current` verbatim
  from one page, short, give the replacement in the page's style, and put in `related_to` the ids of the changes.
  Only what the changes require, not general improvements.
- other_findings: usually empty."""


def _passages(changes: list[tuple[str, list[tuple[str, str]]]]) -> str:
    out = []
    for page, pairs in changes:
        for n, (old, new) in enumerate(pairs, start=1):
            out.append(f"<passage page=\"{page}\" n=\"{n}\">\n<before>\n{old}\n</before>\n<after>\n{new}\n</after>\n</passage>")
    return "\n\n".join(out)


def _fixes(folder: Path, kind: str, found: list[Fix], start: int) -> list[dict]:
    return [{"id": f"F{start + n}", "kind": kind, "page": f.page, "current": f.current, "proposed": f.proposed,
             "reason": f.reason, "source_url": f.source_url, "check": vault.check(folder, f.page, f.current)}
            for n, f in enumerate(found, start=1) if f.current.strip() and f.proposed != f.current]


def run(folder: Path, changes: list[tuple[str, list[tuple[str, str]]]], checks: set[str], translator: LLM,
        llm: LLM) -> dict:
    """The checks asked, on the passages changed of each page ([(page, [(old, new)])]), the folder as it is now.
    → {fixes: [{id, kind, page, current, proposed, reason, source_url, check}], notes: [...], usage: [...]}"""
    fixes, notes, usage = [], [], []
    changes = [(page, [(o, n) for o, n in pairs if n.strip()]) for page, pairs in changes]
    changes = [(page, pairs) for page, pairs in changes if pairs]  # a passage removed has nothing to check
    if not changes:
        return {"fixes": [], "notes": [], "usage": []}
    listing = _passages(changes)
    if "spelling" in checks:
        result, u = translator.parse(system=prompts.fill(SPELLING, folder), prompt=f"Passages:\n\n{listing}",
                                     schema=Fixes, effort=steps.effort("proofread"), node="proofread spelling")
        fixes += _fixes(folder, "spelling", result.fixes, len(fixes))
        usage.append(u)
    if "facts" in checks:
        pages = "\n\n".join(f"<page path=\"{page}\">\n{vault.read(folder / page)}\n</page>"
                            for page, _ in changes if (folder / page).is_file())
        result, u = llm.parse(system=prompts.fill(FACTS, folder), prompt=f"Passages:\n\n{listing}\n\nTheir pages:\n\n{pages}",
                              schema=Fixes, effort=steps.effort("factcheck"), node="proofread facts", web=True)
        fixes += _fixes(folder, "facts", result.fixes, len(fixes))
        notes += result.notes
        usage.append(u)
    if "consistency" in checks:
        edits = [{"id": f"E{n}", "page": page, "current": old, "proposed": new, "severity": "Minor", "group": f"E{n}",
                  "rationale": "written by the editor, already in the page", "source_url": ""}
                 for n, (page, old, new) in enumerate(((p, o, n) for p, pairs in changes for o, n in pairs), start=1)]
        plan = reading.plan(folder, llm, step="crosscheck")
        result, u, checked = crosscheck.run(folder, edits, llm, plan, system=CONSISTENCY)
        by_id = {e["id"]: e for e in edits}
        found = [Fix(page=by_id[r.id]["page"], current=by_id[r.id]["proposed"], proposed=r.revised, reason=r.reason)
                 for r in result.reviews if r.verdict == "revise" and r.revised.strip() and r.id in by_id]
        found += [Fix(page=e.page, current=e.current, proposed=e.proposed, reason=e.reason)
                  for e, check in zip(result.consistency_edits, checked)]
        fixes += _fixes(folder, "consistency", found, len(fixes))
        notes += [f.problem for f in result.other_findings]
        usage.append(u)
    return {"fixes": overlapping(fixes), "notes": notes, "usage": usage}


def overlapping(fixes: list[dict]) -> list[dict]:
    """A fix whose quote holds another fix's quote, or is held by it, on the same page, says so (`overlaps`: the
    earlier ones): once one is applied, the other's quote is gone. The cross-check often revises a whole passage
    the spelling and the facts already fixed in parts; the page offers the first ones ticked, the others to choose."""
    out = []
    for f in fixes:
        same = [g["id"] for g in out if g["page"] == f["page"] and g["check"] == "ok" and f["check"] == "ok"
                and (g["current"] in f["current"] or f["current"] in g["current"])]
        out.append({**f, "overlaps": same})
    return out


def accept(folder: Path, fixes: list[dict], ids: list[str], edits: dict[str, str], today: str) -> dict:
    """The fixes accepted, applied in the guide's folder, in the order of the pages (each quote found once, as any
    edit; `edits`: the editor's own text for a fix, {id: text}). → {applied: [ids], failed: {id: why}}"""
    applied, failed = [], {}
    for f in fixes:
        if f["id"] not in ids:
            continue
        proposed = edits[f["id"]] if f["id"] in edits else f["proposed"]
        if vault.check(folder, f["page"], f["current"]) != "ok":
            failed[f["id"]] = "its text is no longer found once in the page (changed since the check?)"
            continue
        vault.apply(folder, f["page"], f["current"], proposed, today)
        applied.append(f["id"])
    return {"applied": applied, "failed": failed}
