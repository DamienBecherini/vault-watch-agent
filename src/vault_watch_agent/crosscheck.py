"""Second reading of a paused run's corrections against the whole French vault.

The proposals of the graph see excerpts found by keyword. This pass gives the
model every French page at once (≈ 400 k tokens, cached) and asks whether each
correction is right, worth it and consistent with the rest of the guide, and
which other passages must change with it. It only writes a report: the human
review decides, and every extra edit it suggests goes through the same exact
quote check as the corrections.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from . import quotes, vault
from .llm import LLM
from .quotes import Quote

SYSTEM = """You review proposed corrections to a French-language guide on running AI on-premise for SMEs.
The whole French guide is above, one <page> per file. For each correction, judge it against the guide and the
cited source:
- correct: open the cited source with web_fetch and check each fact against it (versions, dates, scope of an
  advisory). Use web_search to find the primary source when the cited one does not settle a fact. Do not
  overstate what the source says.
- relevant: is it worth a reader's attention in this guide, at this length and in this place?
- consistent: does it agree with what other pages say, and does it state the current fact instead of piling
  a new sentence on an old one?

Verdict keep, revise (give the full revised French text that would replace `current`) or reject.
Reject only a correction that is wrong in substance or not worth making. When the substance is right but a
detail is off (a date, a version number, a scope, a wording), revise it: fix the detail and keep the change.
Sources can disagree on a detail (a release tagged on one day and published on another): then state the date
the primary source shows, or drop the detail, rather than rejecting the correction.
Then list the other passages of the guide that must change so the guide stays consistent once the accepted
corrections apply (another page that states the old version floor, a summary table, an index that recommends
the tool). Quote `current` verbatim from one page, short, and give the French replacement in the page's own
style. Only list what the corrections make wrong or inconsistent, not general improvements. A new fact you add
in a consistency edit has consequences too: list what it makes wrong as well (a command, a table row, a
troubleshooting tip). If a reason you give says that another passage should change, that passage is a consistency
edit. Finally, note in one line each any contradiction or factual doubt you noticed elsewhere in the guide while
reading, without proposing a fix, and copy the passages in question verbatim into its `excerpts`; a problem that the
corrections or your edits cause never goes in this list, only a problem that exists regardless of them."""

SWEEP_SYSTEM = """You finish the review of corrections to a French-language guide on running AI on-premise for
SMEs. The whole French guide is above, one <page> per file. The corrections were already checked: do not judge
them again and leave `reviews` empty.

The corrections remove some values (a version, a flag, a package variant) that still appear elsewhere; you get
each remaining occurrence. For each one, decide:
- it states a current fact or recommendation that the corrections make wrong or inconsistent: give a consistency
  edit. This includes a sentence that still makes sense only with the old value, and advice about a version
  below the new minimum.
- it stays true (what a past version fixed, a constraint of an old version stated as such, an unrelated number
  that only looks the same): leave it, list nothing.
Then read what the corrections now assert and list any other passage that contradicts it, even without a listed
value (a table row whose argument no longer holds).

Quote `current` verbatim from one page, short, give the French replacement in the page's own style, and put in
`related_to` the ids of the corrections that require the edit. When an edit states a fact that the footnotes it
cites do not cover, add a consistency edit of the footnote too, from the sources of the corrections. Open a source
only for a fact the corrections do not give. `other_findings` is for problems unrelated to the corrections and is
usually empty."""


class CorrectionReview(BaseModel):
    id: str
    verdict: Literal["keep", "revise", "reject"]
    reason: str = Field(description="One or two sentences, in English.")
    revised: str = Field(description="Full revised French text replacing `current`, empty unless verdict is revise.")


class ConsistencyEdit(BaseModel):
    page: str
    current: str = Field(description="Exact text copied from the page, short.")
    proposed: str
    reason: str
    related_to: list[str] = Field(description="Ids of the corrections that make this edit necessary.")


class Noticed(BaseModel):
    problem: str = Field(description="The contradiction or factual doubt, one line, in English, naming the page.")
    excerpts: list[Quote] = Field(default_factory=list, description="The passages in question, each copied verbatim "
                                  "from its page, so the reviewer sees them without opening the page.")


class CrossCheck(BaseModel):
    reviews: list[CorrectionReview]
    consistency_edits: list[ConsistencyEdit]
    other_findings: list[Noticed] = Field(description="Contradictions or factual doubts noticed elsewhere.")


def noticed(vault_dir: Path, result: CrossCheck) -> tuple[list[str], dict[str, list[dict]]]:
    """The other findings as lines, and per line the passages found in the pages (`quotes.locate`)."""
    return ([f.problem for f in result.other_findings],
            {f.problem: quotes.locate_all(vault_dir, f.excerpts) for f in result.other_findings if f.excerpts})


def run(vault_dir: Path, corrections: list[dict], llm: LLM) -> tuple[CrossCheck, dict, list[str]]:
    listing = "\n\n".join(
        f"<correction id=\"{c['id']}\" page=\"{c['page']}\" severity=\"{c['severity']}\" group=\"{c['group']}\">\n"
        f"<current>\n{c['current']}\n</current>\n<proposed>\n{c['proposed']}\n</proposed>\n"
        f"<rationale>{c['rationale']}</rationale>\n<source>{c['source_url']}</source>\n</correction>"
        for c in corrections
    )
    result, usage = llm.parse(
        system=SYSTEM, prompt=f"Proposed corrections:\n\n{listing}", schema=CrossCheck, effort="high",
        node="crosscheck", context=_guide(vault_dir), web=True,
    )
    checks = [vault.check(vault_dir, e.page, e.current) for e in result.consistency_edits]
    return result, usage, checks


def _guide(vault_dir: Path) -> str:
    return f"<guide>\n{vault.corpus(vault_dir)}\n</guide>"


def sweep(vault_dir: Path, corrections: list[dict], llm: LLM) -> tuple[CrossCheck, dict, list[str]] | None:
    """Second pass, on what the corrections leave behind, the ones the cross-check added included.

    The code finds the values they remove that still appear elsewhere; the model only decides which of
    those occurrences are wrong. No occurrence, no call. Same guide, tools and schema as the cross-check,
    so this call reads its cache.
    """
    hits = vault.leftovers(vault_dir, corrections)
    if not hits:
        return None
    listing = "\n\n".join(
        f"<correction id=\"{c['id']}\" page=\"{c['page']}\">\n<current>\n{c['current']}\n</current>\n"
        f"<proposed>\n{c['proposed']}\n</proposed>\n<source>{c['source_url']}</source>\n</correction>"
        for c in corrections if c["check"] == "ok"
    )
    occurrences = "\n".join(f"- {h['page']}:{h['line']} ({', '.join(h['tokens'])}): {h['text']}" for h in hits)
    result, usage = llm.parse(
        system=SWEEP_SYSTEM, prompt=f"Corrections:\n\n{listing}\n\nRemaining occurrences:\n\n{occurrences}",
        schema=CrossCheck, effort="high", node="sweep", context=_guide(vault_dir), web=True,
    )
    return result, usage, [vault.check(vault_dir, e.page, e.current) for e in result.consistency_edits]


def amend(corrections: list[dict], result: CrossCheck, checks: list[str]) -> list[dict]:
    """Fold the cross-check into the list the human reviews.

    A revised correction keeps its id with the revised text; a rejected one is
    refused like a failed quote check; each consistency edit becomes a new
    correction in the group of the correction that requires it, so they are
    accepted or refused together.
    """
    reviews = {r.id: r for r in result.reviews}
    out = []
    for c in corrections:
        c = dict(c)
        r = reviews.get(c["id"])
        if r is None:
            c["review"] = "not reviewed"
        elif r.verdict == "revise" and r.revised.strip():
            c["proposed_initial"], c["proposed"] = c["proposed"], r.revised
            c["review"] = f"revised: {r.reason}"
        elif r.verdict == "reject":
            c["check"] = "rejected by the cross-check"
            c["review"] = f"rejected: {r.reason}"
        else:
            c["review"] = f"keep: {r.reason}"
        out.append(c)
    return add_edits(out, result, checks, "the cross-check")


def add_edits(corrections: list[dict], result: CrossCheck, checks: list[str], origin: str) -> list[dict]:
    """Turn consistency edits into corrections, in the group of the correction that requires them."""
    out = list(corrections)
    by_id = {c["id"]: c for c in out}
    known = {(c["page"], c["current"]) for c in out}
    n = len(out)
    for e, check in zip(result.consistency_edits, checks):
        ref = next((by_id[i] for i in e.related_to if i in by_id), None)
        if ref is None or (e.page, e.current) in known:
            continue
        n += 1
        known.add((e.page, e.current))
        out.append({
            "id": f"C{n}", "item_id": ref["item_id"], "item_ids": ref["item_ids"], "proposal": ref["proposal"],
            "page": e.page, "current": e.current, "proposed": e.proposed, "source_url": ref["source_url"],
            "severity": ref["severity"], "rationale": e.reason, "group": ref["group"], "check": check,
            "review": f"added by {origin} for {', '.join(e.related_to)}",
        })
    return out


def render(result: CrossCheck, checks: list[str], usage: dict, source: str) -> str:
    lines = [f"# Cross-check against the whole French vault — {source}", "",
             f"Model usage: {usage['input']:,} in + {usage.get('cache_write', 0):,} written to cache + "
             f"{usage.get('cache_read', 0):,} read from cache / {usage['output']:,} out, "
             f"{usage.get('web_searches', 0)} web searches, ≈ {usage.get('cost_usd', 0):.2f} $", "",
             "## Verdicts", "", "| Correction | Verdict | Why |", "| :-- | :-- | :-- |"]
    lines += [f"| {r.id} | **{r.verdict}** | {r.reason.replace('|', '/')} |" for r in result.reviews]
    for r in result.reviews:
        if r.verdict == "revise":
            lines += ["", f"### {r.id}, revised text", "", *[f"> {line}" for line in r.revised.splitlines()]]
    lines += ["", "## Other passages to change for consistency", ""]
    if not result.consistency_edits:
        lines.append("None.")
    for e, check in zip(result.consistency_edits, checks):
        flag = "" if check == "ok" else f" — ⚠️ {check}"
        lines += [f"### `{e.page}` (for {', '.join(e.related_to)}){flag}", "", e.reason, "", "Current:", "",
                  *[f"> {line}" for line in e.current.splitlines()], "", "Proposed:", "",
                  *[f"> {line}" for line in e.proposed.splitlines()], ""]
    lines += ["", "## Noticed elsewhere (not proposed)", ""]
    lines += [f"- {f.problem}" for f in result.other_findings] or ["None."]
    return "\n".join(lines) + "\n"
