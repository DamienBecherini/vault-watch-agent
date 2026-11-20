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

The web is asked in the second part only, one lead per call. The web of a call has a ceiling (20 searches, 30
pages), and leads that shared a call shared it too: on 2026-11-20 a lead about six price lists took all of it and
left its three neighbours unchecked. The calls share the guide in the cache and run together; what two of them add
to one page is put together by the program (`merge`).

A second way to find leads starts from the web instead of the guide (`explore`, the check « explore »): one call per
chapter reads the whole guide and searches freely what moved on the chapter's subjects. It finds what nobody thought
to ask, and its leads come with the sources that establish them; it pays for the web before the editor has seen
anything. Its leads go to the same addition run, where the editor may ask that one be dug deeper (`propose`, `deep`):
its call is asked for a fuller look, on several independent sources, and may write on several pages.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from . import compact, prompts, quotes, reading, steps, vault, webtools
from .llm import LLM, ModelError

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
a subject that fits no page), so that someone who has not read the guide can act on it. In `read`, list the other
pages one must have read to write it well, since the run that checks a lead may be given these pages only: every
page that states the same fact or figure, the lexicon entry of the subject, a page whose advice would change with
it (<<READ>> at the most; none when the pages concerned are enough). In `excerpts`, copy verbatim
the passage of the guide a lead is about when there is one (what it says today: one sentence or one table row, two
passages at most); none for a subject no page covers. Write the leads in English.<<BRIEF>>"""

MAX_LEADS = 30  # a list an editor can go through; each lead kept is then a few searches on the web
MAX_READ = 6  # pages a lead asks to read besides those it concerns
READ_ALSO = "Read also: "
KINDS = {"newer": "Newer", "missing": "Missing", "candidate": "Seen by the watch", "found": "Found on the web"}
NO_PAGE = "no page yet"


class Lead(BaseModel):
    kind: Literal["newer", "missing", "candidate", "found"]
    pages: list[str] = Field(description="Vault-relative paths of the pages concerned: where the addition would go, or "
                             "the page that states the older fact. Empty for a subject that fits no page.")
    problem: str = Field(description="One self-contained line, in English: what to look for and on which kind of "
                         "source, what the guide says today, and which decision of the reader it would change.")
    read: list[str] = Field(default_factory=list, description="Vault-relative paths of the other pages one must have "
                            "read to write this lead well: every page that states the same fact or figure, the lexicon "
                            "entry of the subject, a page whose advice would change with it. Not the pages of `pages`.")
    excerpts: list[quotes.Quote] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list, description="For a lead found on the web: the addresses of the "
                               "primary sources you opened that establish it. Empty for a question.")


class Leads(BaseModel):
    findings: list[Lead]


def line(lead: Lead) -> str:
    """A lead as the one line the editor keeps, dismisses or sends to an addition run. The pages it asks to read
    are in the line (« Read also: … »): they go with it wherever it goes (the interface, a file of findings), and
    the run finds them there (`compact.named`)."""
    sources = f" Sources: {', '.join(lead.sources)}" if lead.sources else ""
    more = list(dict.fromkeys(p for p in lead.read if p not in lead.pages))[:MAX_READ]
    read = f" {READ_ALSO}{', '.join(more)}." if more else ""
    return f"[{KINDS[lead.kind]}] {', '.join(lead.pages) or NO_PAGE}: {lead.problem}{read}{sources}"


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


# -- the other way to find leads: the web explored, one call per chapter ------------------------------------
EXPLORE = """You explore the web for what is new on the subjects of one chapter of <<GUIDE>>. The whole guide is above, one <page>
per file. Today is <<TODAY>>. The request names the chapter to explore and its pages. A watch already follows the
sources the guide knows, week after week: look where it does not, for what appeared or changed in the last months
and that no page of the guide reflects.

How to look:
- From the pages of the chapter, take the subjects that move: products and their generations, models, tools and
  their major versions, prices, rules in force, security. Search the web for each (web_search and web_fetch) and open
  primary sources: the vendor's or the project's own page, release notes, a model card, an official text. Follow
  what you find: a release note that names something the guide ignores is a lead.
- You have about <<SEARCHES>> searches and <<PAGES>> pages for this chapter: spread them over its subjects rather than
  exhausting one.
- A newsletter, a video or a forum tells where to look; a lead needs a primary source you opened.

What to keep:
- Compare each thing found with the whole guide above, not with the chapter alone: keep it when no page says it, or
  when a page still states what it supersedes. Leave out what the guide already covers.
- Follow the guide's own threshold for additions, in its contract below: keep what would change a decision of the
  reader, not everything that is new.
- At most <<MAX>> leads, the most useful to a reader first; none when you found nothing that qualifies.

Each lead is a fact you read on a primary source, not a guess: say what is new and its date, what the guide says
today when it says something, which decision of the reader it changes, and what remains to be checked. `kind` is
`found`. `pages` names the pages concerned (where it would go, or the page that states the older fact; none when it
fits no page). `read` lists the other pages one must have read to write it well, since the run that checks a lead
may be given these pages only: every page that states the same fact or figure, the lexicon entry of the subject, a
page whose advice would change with it (<<READ>> at the most). `sources` lists the addresses you opened that
establish it. In `excerpts`, copy verbatim the passage
of the guide the lead is about when there is one (one sentence or one table row). Do not report an error, a
contradiction, style or length (other checks do). Write the leads in English.<<BRIEF>>"""

EXPLORE_SEARCHES, EXPLORE_PAGES = 12, 15  # asked of the model, per chapter: the web is what such a call costs
MAX_PER_CHAPTER = 8


def explorable(vault_dir: Path) -> dict[str, list[str]]:
    """The chapters a call can explore, with their pages: every chapter that has a page the agent may edit."""
    guide = vault.guide_of(vault_dir)
    found = {name: [p.relative_to(vault_dir).as_posix() for p in pages] for name, pages in reading.chapters(vault_dir).items()}
    return {name: pages for name, pages in found.items() if not all(guide.is_readonly(p) for p in pages)}


def explore(vault_dir: Path, llm: LLM, chapters: list[str] | None = None) -> tuple[list[Lead], list[dict], dict[str, str]]:
    """What the web says that the guide does not, chapter by chapter: (leads, usages, {chapter not explored: why}).
    One call per chapter (`chapters`: those asked, all of them otherwise), each with the web and the whole guide:
    cached and shared on the Claude API (one call leads and writes the cache, `compact._after_the_first`), one call
    after the other with another engine; a guide too large for the model gives each call its chapter alone. A lead
    whose source another chapter already gave is merged with it. A call that fails leaves its chapter unexplored,
    said in the result; when every call fails the error is raised."""
    known = explorable(vault_dir)
    wanted = [c for c in known if not chapters or c in chapters]
    if not wanted:
        return [], [], {}
    client = llm.for_step("explore") if hasattr(llm, "for_step") else llm
    fits = reading.plan(vault_dir, llm, step="explore").mode == "whole"
    shared = bool(getattr(client, "signals_start", False)) and fits
    system = prompts.fill(EXPLORE.replace("<<SEARCHES>>", str(EXPLORE_SEARCHES)).replace("<<PAGES>>", str(EXPLORE_PAGES))
                          .replace("<<READ>>", str(MAX_READ))
                          .replace("<<MAX>>", str(MAX_PER_CHAPTER)), vault_dir)
    whole = f"<guide>\n{vault.corpus(vault_dir)}\n</guide>" if fits else ""

    def one(n: int, started=None) -> tuple[str, list[Lead], dict | None, str]:
        chapter = wanted[n]
        alone = "" if fits else f"<guide>\n{reading.corpus_of(vault_dir, reading.chapters(vault_dir)[chapter])}\n</guide>"
        asked = system if fits else system.replace(
            "The whole guide is above", f"One chapter of the guide ({chapter}) is above, the others are not shown", 1)
        prompt = f"Chapter to explore: {chapter}\nIts pages:\n" + "\n".join(f"- {p}" for p in known[chapter]) + "\n\nList the leads."
        try:
            result, usage = llm.parse(system=asked, prompt=prompt, schema=Leads, effort=steps.effort("explore"),
                                      node=f"verify explore {chapter}", context=whole or alone, web=True,
                                      **({"started": started} if started else {}))
        except ModelError as e:
            return chapter, [], getattr(e, "usage", None), str(e)
        return chapter, list(result.findings)[:MAX_PER_CHAPTER], usage, ""
    if len(wanted) == 1:
        results = [one(0)]
    elif shared:
        results = compact._after_the_first(len(wanted), one)
    else:
        results = [one(n) for n in range(len(wanted))]
    failed = {chapter: why for chapter, _, _, why in results if why}
    if len(failed) == len(wanted):
        raise ModelError(next(iter(failed.values())))
    leads, by_source = [], {}
    for _, found, _, _ in results:
        for lead in found:
            first = next((by_source[s] for s in lead.sources if s in by_source), None)
            if first is not None:  # the same source, seen from another chapter: one lead, with the pages of both
                first.pages += [p for p in lead.pages if p not in first.pages]
                first.read += [p for p in lead.read if p not in first.read]
                continue
            leads.append(lead)
            by_source.update({s: lead for s in lead.sources})
    return leads, [u for _, _, u, _ in results if u], failed


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
- A lead that names its sources was found on the web: start from those addresses, open them again, and look further
  only for what they leave open.
- A lead given under the heading « Lead to dig deeper » was chosen by the editor for a fuller look: read several
  independent primary sources, and establish what it replaces, how mature and available it is (its licence, the
  hardware it needs, its known limits), and what it changes for each kind of reader of the guide. Its addition
  may then span several pages. Say what you established in its outcome's `event`, in three sentences at the most.
- A call has about <<SEARCHES>> searches and <<PAGES>> pages on the web: open the primary sources first. When they
  run out before a lead is checked, give it an outcome whose no_change_reason begins with « not checked: » and says
  what is left to open; never fill the gap from memory.
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
                  "its outcome (the review that follows reads every page).",
         "plan": "Above are the plan of the guide (every page: its path, its weight, its title and its headings), "
                 "then the pages the lead names or asks to read, each whole, one <page> per file. The guide has other "
                 "pages, which you do not see: edit only the pages given. When the plan shows that another page "
                 "probably states the same fact or already covers the subject, name that page in the lead's outcome "
                 "(in `event`, or in no_change_reason when you edit nothing) instead of guessing what it says: the "
                 "review that follows reads every page, and completes or corrects."}
CONTEXTS = ("guide", "pages")  # what each call of an addition run reads: the whole guide, or the lead's pages and the plan
# The default since the run of 2026-11-20 that compared them: half the price, and every place that stated the older
# values was reached (the cross-check, which reads every page, wrote those the calls had not seen)
CONTEXT = "pages"

_NEEDS_PAGE = re.compile(r"^\W*needs a page\W*", re.I)


def pages_to_write(state: dict) -> list[dict]:
    """The leads an addition run answered « needs a page »: [{id, lead, what}]. The run never writes a new page; these
    are shown apart, at the top of the review, of the report and of the pull request, so that they are not missed
    among the leads without change."""
    titles = {i["id"]: i["title"] for i in state.get("items", [])}
    return [{"id": o["item_id"], "lead": titles.get(o["item_id"], ""), "what": _NEEDS_PAGE.sub("", o["no_change_reason"]).strip()}
            for p in state.get("proposals", []) for o in p.get("outcomes", [])
            if _NEEDS_PAGE.match(o.get("no_change_reason") or "")]


NO_NEW_PAGE = "This run adds to existing pages only: it never writes a new page."


def unchanged(state: dict) -> list[dict]:
    """The leads an addition run left without an edit, and why: [{id, lead, why}], those that need a page apart
    (`pages_to_write`). What the search found is as much a result as an edit: the review shows it."""
    titles = {i["id"]: i["title"] for i in state.get("items", [])}
    used = {i for c in state.get("corrections", []) for i in c.get("item_ids", [c.get("item_id")])}
    return [{"id": o["item_id"], "lead": titles.get(o["item_id"], ""), "why": o.get("no_change_reason") or o.get("event") or ""}
            for p in state.get("proposals", []) for o in p.get("outcomes", [])
            if o["item_id"] not in used and not _NEEDS_PAGE.match(o.get("no_change_reason") or "")]

PER_CALL = 1  # leads per call: the web of a call has a ceiling, which leads in one call take from one another
NOT_CHECKED = re.compile(r"^\W*not (checked|handled)\b", re.I)  # a lead its call could not look at: to send again


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


def propose(vault_dir: Path, leads: list[str], llm: LLM, excerpts: dict[str, list[dict]] | None = None,
            deep: set[str] | list[str] | None = None, context: str = CONTEXT) -> tuple[list[dict], list[dict], list[dict]]:
    """The additions for the leads the editor kept: (items, proposals, usages), one proposal and one usage per call.
    Every call reads the whole guide when it fits the model (`compact.in_calls`: cached and shared on the Claude
    API, one call after the other elsewhere) and the web. A call that fails leaves its leads without an addition,
    said in their outcome; the others go on.
    One lead per call (`PER_CALL`), so that each has the whole web of a call. `deep`: the leads to dig deeper,
    headed as such (`ADD` says what that asks).
    `context`: "guide", every call reads the whole guide; "pages", a call reads the plan of the guide
    (`chapters.outline`) and the pages its lead names, those it asks to read included (« Read also: »), cached for
    that call alone: a call re-reads what it was given at each round of search, and the guide is twelve times the
    pages of a lead. A lead that names no page reads the guide all the same. What a call did not see is the business
    of the cross-check, which reads every page."""
    from . import chapters  # here: chapters.py is read by the checks, which this module serves

    if context not in CONTEXTS:
        raise ValueError(f"context: {context!r} is not one of {', '.join(CONTEXTS)}")
    narrow = context == "pages"
    texts = {p.relative_to(vault_dir).as_posix(): vault.read(p).replace("\r", "") for p in vault.pages(vault_dir)}
    pages = [compact.named(lead, set(texts)) for lead in leads]
    dug = [i for i, lead in enumerate(leads) if lead in set(deep or [])]
    usual = [i for i in range(len(leads)) if i not in dug]
    groups = [[usual[i] for i in batch] for batch in batches([pages[i] for i in usual])] + [[i] for i in dug]
    headings = [("Leads", "lead")] * (len(groups) - len(dug)) + [("Lead to dig deeper", "lead")] * len(dug)
    return compact.in_calls(vault_dir, leads, llm, excerpts, groups, pages=pages, texts=texts, step="add",
                            system=ADD.replace("<<SEARCHES>>", str(webtools.MAX_SEARCHES)).replace("<<PAGES>>", str(webtools.MAX_PAGES)),
                            web=True, what=("Leads", "lead"), whole=True, above=ABOVE, headings=headings, narrow=narrow,
                            before=f"<plan>\n{chapters.outline(vault_dir)}\n</plan>\n" if narrow else "")


_NOTE_DEF = re.compile(r"^\[\^([^\]\s]+)\]:", re.M)


def merge(vault_dir: Path, corrections: list[dict]) -> None:
    """What several calls add to one page, made to fit together (in place). Each call saw the page as it is, so two
    of them give their new footnote the same free marker: the later call's marker is renamed, in every edit that
    call makes to the page, to one neither the page nor an earlier call uses. Two edits that only append to the
    same passage (two definitions after the last footnote, two rows after the same row) both apply: `appends`."""
    taken: dict[str, set[str]] = {}   # page -> markers defined in it, or given to a call already
    for call in sorted({c["proposal"] for c in corrections}):
        mine = [c for c in corrections if c["proposal"] == call]
        for page in sorted({c["page"] for c in mine}):
            path = vault_dir / page
            used = taken.setdefault(page, set(_NOTE_DEF.findall(vault.read(path).replace("\r", ""))) if path.is_file() else set())
            edits = [c for c in mine if c["page"] == page]
            new = sorted({m for c in edits for m in _NOTE_DEF.findall(c["proposed"])}
                         - {m for c in edits for m in _NOTE_DEF.findall(c["current"])}, key=lambda m: (len(m), m))
            for marker in new:
                name = marker
                if marker in used:
                    numbers = [int(m) for m in used | set(new) if m.isdigit()]
                    name = str(max(numbers) + 1) if numbers else f"{marker}-2"
                    while name in used or name in new:
                        name = f"{name}-2"
                    for c in edits:
                        c["proposed"] = c["proposed"].replace(f"[^{marker}]", f"[^{name}]")
                used.add(name)


def appends(c: dict) -> bool:
    """An edit that keeps its passage and writes after it: two of them at the same place do not collide."""
    return c["proposed"].startswith(c["current"]) and len(c["proposed"]) > len(c["current"])


def ordered(corrections: list[dict]) -> list[dict]:
    """The order to apply edits in. Those that write after the same passage go last first: each one inserts right
    after the passage, so the first proposed ends first in the page (note [^24], then [^25])."""
    out, places = list(corrections), {}
    for n, c in enumerate(corrections):
        if appends(c):
            places.setdefault((c["page"], c["current"]), []).append(n)
    for at in places.values():
        for n, m in zip(at, reversed(at)):
            out[n] = corrections[m]
    return out
