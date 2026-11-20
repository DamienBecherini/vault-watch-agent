"""Look for what is new: what a reader would expect of the guide and does not find.

A watch follows the sources it already knows; what none of them announces stays out of the guide, and what it sets
aside as a possible addition is never written. This is a run of its own, apart from the watches, in two parts:

1. the leads (`LEADS`, one call that reads the whole guide, without the web, run as a check of `verify.py`): what
   the guide presents as current and has probably moved on, the subjects a reader would expect and no page covers,
   and what past watches set aside (`candidates`, read from their reports, no model). A lead is a question: nothing
   is verified and nothing is edited;
2. the additions (`propose`): for the leads the editor keeps, calls that read the whole guide and the web. Each lead
   is checked on primary sources, then added where it belongs, or left with the reason. The result enters the graph
   like the corrections of a fix run: cross-check, review, mirrors, the guide's audits, pull request.

The web is asked in the second part only, a few leads per call: each round of search re-reads what the call has
gathered so far, so a long call costs much more than several short ones.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from . import compact, quotes, vault
from .llm import LLM

LEADS = """You look for what a reader would expect to find in <<GUIDE>> and does not. The whole guide is above, one <page> per
file. Today is <<TODAY>>. A guide kept up to date by a watch follows the sources it already knows: what none of them
announces stays out, and what a watch sets aside as a possible addition is never written. List the leads worth
checking on the web, the most useful to a reader first:
- newer: something the guide presents as current that has probably moved on since: a product generation, a model
  family, a major version, a price list, a rule in force. Say what the guide states and of which date, and what to
  look for.
- missing: a subject, a tool, a model, a piece of hardware, a risk or an obligation that a guide on this subject owes
  its readers and that no page covers. Say which decision of the reader it would change and where it would go: the
  page and its section, or that it needs a page of its own.
- candidate: an item of the list below, which past watches set aside as possible additions without writing them.
  Keep those the guide still does not cover and that would change a decision of the reader; leave out the others.
A lead is a question, not a fact: you verify nothing here, and what you know may be out of date. Say what to check
and on which kind of primary source (the vendor's page, the release notes, the model card, the official text); never
write a figure, a version or a date as if it were established. Do not report an error, a contradiction, style or
length (other checks do). Do not list what the guide already covers, even briefly, unless what it says has probably
been superseded. Follow the guide's own threshold for additions, in its contract below. List at most <<MAX>> leads:
the editor keeps some, then a run checks each one on the web and proposes where to write it.
Each lead names the pages concerned (where the addition would go, or the page that states the older fact; none for
a subject that fits no page), so that someone who has not read the guide can act on it. In `excerpts`, copy verbatim
the passage of the guide a lead is about when there is one (what it says today: one sentence or one table row, two
passages at most); none for a subject no page covers. Write the leads in English.<<BRIEF>>"""

MAX_LEADS = 30  # a list an editor can go through; each lead kept is then a few searches on the web
KINDS = {"newer": "Newer", "missing": "Missing", "candidate": "Seen by the watch"}
NO_PAGE = "no page yet"


class Lead(BaseModel):
    kind: Literal["newer", "missing", "candidate"]
    pages: list[str] = Field(description="Vault-relative paths of the pages concerned: where the addition would go, or "
                             "the page that states the older fact. Empty for a subject that fits no page.")
    problem: str = Field(description="One self-contained line, in English: what to look for and on which kind of "
                         "source, what the guide says today, and which decision of the reader it would change.")
    excerpts: list[quotes.Quote] = Field(default_factory=list)


class Leads(BaseModel):
    findings: list[Lead]


def line(lead: Lead) -> str:
    """A lead as the one line the editor keeps, dismisses or sends to an addition run."""
    return f"[{KINDS[lead.kind]}] {', '.join(lead.pages) or NO_PAGE}: {lead.problem}"


# -- what past watches set aside ------------------------------------------------------------------------------
CANDIDATE_DAYS = 120  # a lead older than that was either written since or is no longer news
MAX_CANDIDATES = 60
_SECTION = re.compile(r"^## Addition candidates[^\n]*\n(.*?)(?=^## |\Z)", re.S | re.M)
_CANDIDATE = re.compile(r"^- \S+ \[(?P<title>.+)\]\((?P<url>https?://[^)\s]+)\): (?P<why>.*)$", re.M)
_DATED = re.compile(r"\d{4}-\d{2}-\d{2}")


def reports_of(work: Path) -> Path:
    """The folder of the run reports, from the folder a check works in (`<home>/verifications/<id>` for the server,
    `<home>/reports` for the command line)."""
    return work if work.name == "reports" else work.parent.parent / "reports"


def candidates(reports: Path, today: date, days: int = CANDIDATE_DAYS, most: int = MAX_CANDIDATES) -> list[dict]:
    """What the watches of the last `days` days set aside as possible additions: [{date, title, url, why}], the most
    recent first, each address once. Read from the reports of the runs (their section « Addition candidates »): no
    model, no network. The replays of an evaluation (`eval-…`) repeat a watch and are skipped."""
    since, found = (today - timedelta(days=days)).isoformat(), {}
    if not reports.is_dir():
        return []
    for path in sorted(reports.glob("*.md")):
        dated = _DATED.search(path.name)
        if path.name.startswith("eval-") or not dated or not since <= dated.group(0) <= today.isoformat():
            continue
        try:
            section = _SECTION.search(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
        except OSError:
            continue
        for m in _CANDIDATE.finditer(section.group(1) if section else ""):
            known = found.get(m["url"])
            if not known or known["date"] < dated.group(0):
                found[m["url"]] = {"date": dated.group(0), "title": m["title"].strip(), "url": m["url"], "why": m["why"].strip()}
    return sorted(found.values(), key=lambda c: (c["date"], c["url"]), reverse=True)[:most]


def listing(found: list[dict]) -> str:
    """The candidates as the model reads them, or the sentence that says there is none."""
    if not found:
        return "Past watches set nothing aside (or their reports are not on this machine)."
    return "What past watches set aside as possible additions (the date of the watch, the item, why):\n" + "\n".join(
        f"- {c['date']}: {c['title']} <{c['url']}> — {c['why']}" for c in found)


# -- the additions: a run of the graph ------------------------------------------------------------------------
ADD = """You look for what is new for <<GUIDE>> and write it where it belongs. <<ABOVE>> Today is <<TODAY>>. Each lead (F1…) is a
question, not a fact: something the guide presents as current that may have moved on, a subject a reader would
expect and no page covers, or an item that past watches set aside. A lead may be wrong or out of date: it says
where to look.

For each one:
- Search the web and open primary sources: the vendor's page, the release notes, the model card, the official text,
  the repository (use web_search and web_fetch). Never rely on memory, nor on the lead itself, for a figure, a
  version, a price or a date. A newsletter, a video or a forum tells where to look; it is never the source.
- If you find nothing new, nothing a primary source establishes, something the guide already covers, or something
  below the guide's threshold for additions (its contract below), give an outcome with no_change_reason: one line a
  reviewer can check.
- Otherwise give the verified fact as the outcome's `event`, with its date, and propose the smallest edits that give
  it to the reader:
  - the guide states something superseded: correct it where it is stated, in every page that states it.
    <<REPLACE>>
  - the guide lacks it: add it where a reader would look for it: a sentence in the paragraph it belongs to, a row
    in the table that lists such things, an item in a list, a short paragraph under the right heading. Say what it
    changes for the reader (sizing, the choice of a tool, security, cost), not merely that it exists.
  - it would need a page of its own: do not write the page. Give an outcome whose no_change_reason begins with
    « needs a page: » and says what the page would hold and where it would sit; you may still add one sentence
    where the guide lists such things.
- An addition is an edit like any other: `current` is the passage it follows or completes (a sentence, a table row,
  a list item, the last line of a section), copied verbatim from one page above and occurring once in it; `proposed`
  is that passage, followed or completed by the new text. Never a page or a section rewritten whole.
- A fact you add carries its source the way the page cites its sources. When the page uses footnotes: a marker the
  page does not use yet, and its definition in a second edit with the same `group` (`current` is the last footnote
  definition of the page, `proposed` is that definition, a line break, then the new one, written like the others).
- Answer the leads given here and nothing else: a run may handle other leads in other calls at the same time.

Edits follow the guide's style: <<LANG>>, the same Markdown, wiki links [[...]] and footnote markers kept, dated wording
for facts that move. `item_ids` lists the leads an edit answers; `source_url` is the primary source you opened;
`severity` is Major when the edit changes a decision of the reader, Minor otherwise; `rationale` says in one line
what is new and why it belongs there. Edits that only make sense together share a `group` label. One outcome per
lead.<<BRIEF>>"""

# What is above the leads, per way of reading (`compact.in_calls`)
ABOVE = {"guide": "The whole guide is above, one <page> per file.",
         "pages": "The pages the leads name are above, each whole, one <page> per file; the guide has other pages, "
                  "which you do not see: when you cannot tell whether the guide already covers a lead, say so in "
                  "its outcome (the review that follows reads every page)."}

PER_CALL = 4  # leads per call: each one is a few rounds of search, and each round re-reads what the call gathered


def batches(pages: list[list[str]], most: int = PER_CALL) -> list[list[int]]:
    """The leads (by index) grouped for one call each, `most` at the most. A call takes the first lead left, then
    those that share the most pages with it, then chapters: the additions to one page are written together, so they
    do not collide."""
    left, out = list(range(len(pages))), []
    tops = lambda found: {p.split("/")[0] for p in found}  # noqa: E731
    while left:
        batch = [left.pop(0)]
        while left and len(batch) < most:
            seen = {p for i in batch for p in pages[i]}
            best = max(left, key=lambda i: (len(seen & set(pages[i])), len(tops(seen) & tops(pages[i])), -i))
            left.remove(best)
            batch.append(best)
        out.append(sorted(batch))
    return out


def propose(vault_dir: Path, leads: list[str], llm: LLM,
            excerpts: dict[str, list[dict]] | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """The additions for the leads the editor kept: (items, proposals, usages), one proposal and one usage per call.
    Every call reads the whole guide when it fits the model (`compact.in_calls`: cached and shared on the Claude
    API, one call after the other elsewhere) and the web. A call that fails leaves its leads without an addition,
    said in their outcome; the others go on."""
    texts = {p.relative_to(vault_dir).as_posix(): vault.read(p).replace("\r", "") for p in vault.pages(vault_dir)}
    pages = [compact.named(lead, set(texts)) for lead in leads]
    return compact.in_calls(vault_dir, leads, llm, excerpts, batches(pages), pages=pages, texts=texts, step="add",
                            system=ADD, web=True, what=("Leads", "lead"), whole=True, above=ABOVE)
