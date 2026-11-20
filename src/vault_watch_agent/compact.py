"""Compaction: keep a guide from growing heavy.

A watch only adds: « since » notes, footnotes stacked on footnotes, one warning copied into three pages, versions
kept « for the record ». Compaction is a run of its own, apart from the watches, in three parts:

1. the sizes (`sizes.py`, no model): each page against its budget, where the weight is;
2. the report (`REPORT`, one call that reads the whole guide, run as a check of `verify.py`): what is repeated,
   what is piled-up history, which sections are longer than what they say. It edits nothing;
3. the trims (`propose`): for the findings the editor keeps, targeted edits (current text, proposed text, reason),
   which enter the graph like the corrections of a fix run: cross-check (`CROSSCHECK`: nothing lost), review,
   mirrors, the guide's audits, pull request.

What the code checks itself, because a model must not be trusted with it: a note left without a sentence citing
it is removed with the trim (`with_orphan_notes`), a trim that would leave a sentence citing a removed note is
refused (`mark_dangling`), and each trim lists the values that no page states any more once it applies
(`vault.lost`).
"""

from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from . import fix, quotes, reading, steps, vault
from .llm import LLM, ModelError

REPORT = """You look for what makes <<GUIDE>> heavier than it needs to be. The whole guide is above, one <page> per
file. A guide kept up to date by a watch only grows: notes are added beside older ones, the same warning is copied
into several pages, superseded versions stay « for the record ». List what a careful editor would trim, the
heaviest first:
- repeated: the same fact, explanation, warning or table stated at length in several pages. Say in `keep_in` which
  page should keep the full statement (the page whose subject it is); the others shorten it and link there. A short
  reminder that links to the full statement is not a repetition, and neither is a figure two pages both need.
- history: what is superseded and still stands beside the current fact: successive « since » or « previously »
  notes, versions or prices kept for the record, advisories fixed long ago in versions below the minimum the guide
  now requires, « new in » remarks about releases that are no longer new.
- long: a section that takes much more room than what it says needs. Say what makes it long (an introduction that
  restates the page, a list that repeats the table beside it, examples that add nothing). The heaviest pages are
  listed below with their heaviest sections: look there first.
Do not report an error of fact or a contradiction (another check does), style, or a missing topic. Never propose
to remove the only statement of a fact, a caveat or a source. Skip what would save less than a sentence or two.
List at most <<MAX>> findings, those that save the most: the editor acts on them, then asks again.
Each finding names the pages, quotes the passages, and says what to trim and where the reader still finds the
information, so that someone who has not read the guide can act on it. Write the findings in English."""

EXCERPTS = ("\nIn `excerpts`, copy each passage in question verbatim from its page (one sentence or one table row, "
            "not a paragraph; for a repetition, one from each page; three passages at most): the reviewer reads it "
            "without opening the page.")

MAX_FINDINGS = 30  # a report an editor can act on; the answer also stays far from the model's output limit
KINDS = {"repeated": "Repeated", "history": "History", "long": "Long"}


class Trim(BaseModel):
    kind: Literal["repeated", "history", "long"]
    pages: list[str] = Field(description="Vault-relative paths of the pages concerned; for a repetition, every page "
                             "that states it, the one that keeps it included.")
    problem: str = Field(description="One self-contained line, in English: what weighs, quoting the passages, what "
                         "to trim and where the reader still finds the information.")
    keep_in: str = Field(default="", description="For a repetition: the page that keeps the full statement.")
    excerpts: list[quotes.Quote] = Field(default_factory=list)


class Trims(BaseModel):
    findings: list[Trim]


def line(t: Trim) -> str:
    """A finding as the one line the editor keeps, dismisses or sends to a compaction run."""
    keep = f" Keep the full statement in {t.keep_in}." if t.keep_in and t.keep_in not in t.problem else ""
    return f"[{KINDS[t.kind]}] {', '.join(t.pages)}: {t.problem}{keep}"


PROPOSE = """You trim <<GUIDE>> so that it weighs less without saying less. <<ABOVE>> Each finding (F1…) names
something that makes the guide heavy: the same fact stated at length in several pages, history piled up beside the
current fact, a section longer than what it says needs.

For each one:
- Check it against the pages above. If it is wrong, or the passage is needed where it is (a page a reader lands on
  directly must still tell them what they need to act), give an outcome with no_change_reason.
- Otherwise propose targeted edits, never a page or a section rewritten whole:
  - a repetition: the page the finding names keeps the full statement, with its source and footnote; in the other
    pages, shorten the passage to what that page needs and link to the page that keeps it, written the way the
    guide links its pages. Do not remove a repetition without leaving that link, unless the text around already
    links there.
  - piled-up history: state the current fact and remove what is superseded (« previously » and « since » notes,
    versions kept for the record, advisories fixed long ago in versions below the minimum the guide now requires).
    Keep an old value only when the reader needs it to act (a version below which a flaw applies, a migration from
    the old behaviour).
  - a long section: remove what repeats, restates the page or duplicates the table beside it; keep every fact,
    figure, caveat and source.
- Never remove the only statement of a fact, a figure, a caveat or a source: it counts as stated elsewhere only
  when you read it in a page above. Move it (two edits with the same `group`: one removes it here, the other adds
  it where it belongs) or leave it.
- Answer the findings given here and nothing else: a run may handle other findings in other calls at the same
  time.
- Footnotes: when an edit removes the last sentence that cites a note, the program removes that note's definition
  itself; never leave a sentence citing a note you remove. A fact that moves to another page takes its note with
  it, defined there under a marker that page does not use yet.
- No new fact and no rewording for style: every `proposed` says the same as its `current`, or less.

`current` is copied verbatim from one page above and occurs once in it: a sentence, a list item, a table row or a short
paragraph (several edits for a longer passage). `proposed` replaces it, in <<LANG>> and in the page's style; leave
it empty to remove `current` whole. `item_ids` lists the findings the edit answers. `source_url` is the path of the
page where the reader still finds the information (the edited page itself for history and length). `severity` is
Minor. `rationale` says in one line what goes and where the reader still finds it. Edits that only make sense
together share a `group` label. One outcome per finding."""

CROSSCHECK = """You review trims proposed for <<GUIDE>>.
The whole guide is above, one <page> per file. Each trim removes or shortens a passage so that the guide weighs
less without saying less. For each one, judge it against the guide:
- nothing lost: every fact, figure, caveat and source the removed text carried is still stated once all the trims
  apply (in the page its rationale names), or was history a reader no longer needs to act. Two trims must not
  remove both statements of the same thing.
- still readable: the page reads on at that place (no sentence left pointing at what is gone, no list or table left
  broken, no heading left without content), and a link that replaces a repetition points to a page that exists,
  written like the guide's other links.
- worth it: the page is lighter and no less useful to a reader who lands on it directly.

Verdict keep, revise (give the full revised <<LANG>> text that would replace `current`) or reject. Reject a trim
that removes the only statement of something a reader needs; revise one that is right but cuts a word too many
or leaves a broken sentence.
Then list the other passages that must change so the guide stays consistent once the trims apply (a sentence that
refers to the removed section, a summary that announces it). Quote `current` verbatim from one page, short, give
the <<LANG>> replacement in the page's own style, and put in `related_to` the ids of the trims that require it. Only
list what the trims make wrong, not other improvements. The program removes by itself the definition of a note no
sentence cites any more: do not list it. Finally, note in one line each any contradiction or factual doubt you
noticed elsewhere in the guide while reading, without proposing a fix, and copy the passages in question verbatim
into its `excerpts`."""


# What is above the findings, per way of reading (`propose`)
ABOVE = {"guide": "The whole guide is above, one <page> per file.",
         "pages": "The pages the findings name are above, each whole, one <page> per file; the guide has other pages, "
                  "which you do not see (the review that follows your trims reads them all)."}

# What one call is asked: a finding weighs the pages it names (two at least: a long section takes several edits).
# The trims of thirty findings in one answer would not fit under the output limit of a model that thinks much
# (the report alone wrote 48 k tokens on Fable 5.2 at effort high), and an answer cut at the limit is billed and lost.
BATCH_LOAD = 30
BATCH_BYTES = 600_000  # of pages given to one call (about 190 k tokens)
PARALLEL = 4
NARROW_PARALLEL = 8  # calls that each write their own pages to the cache: not thirty at once


def named(finding: str, sources: set[str]) -> list[str]:
    """The source pages of the guide a finding names, in its order."""
    out: list[str] = []
    for m in fix.PAGE_PATH.finditer(finding):
        if m.group(0) in sources and m.group(0) not in out:
            out.append(m.group(0))
    return out


def batches(pages: list[list[str]], size: dict[str, int]) -> list[list[int]]:
    """The findings (by index) grouped for one call each. A batch takes the first finding left, then those that
    share the most pages with it while it holds: the trims asked of one page are then written together, and the
    call reads fewer pages."""
    left, out = list(range(len(pages))), []
    load = lambda i: max(2, len(pages[i]))  # noqa: E731
    while left:
        batch = [left.pop(0)]
        seen, total = set(pages[batch[0]]), load(batch[0])
        while True:
            fits = [i for i in left if total + load(i) <= BATCH_LOAD
                    and sum(size[p] for p in seen | set(pages[i])) <= BATCH_BYTES]
            if not fits:
                break
            best = max(fits, key=lambda i: (len(seen & set(pages[i])), -i))
            left.remove(best)
            batch.append(best)
            seen |= set(pages[best])
            total += load(best)
        out.append(sorted(batch))
    return out


def propose(vault_dir: Path, findings: list[str], llm: LLM,
            excerpts: dict[str, list[dict]] | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """The trims for the findings the editor kept: (items, proposals, usages), one proposal and one usage per call.
    Without the web, in several calls when the findings are many (`batches`). Two ways of reading:
    - the whole guide for every call, when the engine caches it and says when its answer begins (the Claude API)
      and the guide fits the model: the first call writes the cache, the others start once it has begun to answer
      and read it (started together, each would pay for writing it);
    - else the pages the findings of the call name, whole: a finding names every page it is about, the cross-check
      that follows reads the whole guide, and the code lists what no page states any more. The findings that name
      no page of the guide (a line typed by hand) then go together with the whole guide.
    A call that fails leaves its findings without a trim, said in their outcome; the others go on."""
    texts = {p.relative_to(vault_dir).as_posix(): vault.read(p).replace("\r", "") for p in vault.pages(vault_dir)}
    pages = [named(f, set(texts)) for f in findings]
    size = {p: len(t.encode("utf-8")) for p, t in texts.items()}
    with_pages = [i for i, ps in enumerate(pages) if ps]
    groups = [[with_pages[i] for i in b] for b in batches([pages[i] for i in with_pages], size)]
    without = [i for i, ps in enumerate(pages) if not ps]
    if without:
        groups.append(without)
    return in_calls(vault_dir, findings, llm, excerpts, groups, pages=pages, texts=texts, step="compact",
                    system=PROPOSE, web=False, what=("Findings", "finding"))


def in_calls(vault_dir: Path, findings: list[str], llm: LLM, excerpts: dict[str, list[dict]] | None,
             groups: list[list[int]], *, pages: list[list[str]], texts: dict[str, str], step: str, system: str,
             web: bool, what: tuple[str, str], whole: bool = False, above: dict[str, str] | None = None,
             headings: list[tuple[str, str]] | None = None, narrow: bool = False,
             before: str = "") -> tuple[list[dict], list[dict], list[dict]]:
    """The proposals of a run made in several calls: (items, proposals, usages), one proposal and one usage per call.
    `groups`: the findings of each call, by index; `pages`: the pages each finding names; `system`: the instructions,
    with <<ABOVE>> where they say what the call reads (`above`, by default `ABOVE`); `step`: the step, which names
    the calls; `what`: how the findings are called in the request (its heading, the tag of each), or per call in
    `headings` (the instructions stay the same for every call: they are what the calls share in the cache).
    What a call reads:
    - the whole guide, cached, when the engine says when its answer begins (the Claude API) and the guide fits the
      model: one call leads and writes the cache, the others start once it has begun to answer (`_after_the_first`);
    - with another engine, the whole guide all the same when `whole` is asked and it fits, one call after the other
      (an engine that caches reads it again; a local model takes one call at a time anyway);
    - else the pages the findings of the call name, whole, with the question; a group that names none reads the guide.
    `narrow`: the pages the findings name even when the guide could be shared, after `before` (the plan of the
    guide), cached for the call alone (a call with the web reads what it was given again at each round of search);
    `above` then says it under "plan". These calls share nothing: they run together, `NARROW_PARALLEL` at a time.
    A call that fails leaves its findings without a proposal, said in their outcome; the others go on."""
    client = llm.for_step(step) if hasattr(llm, "for_step") else llm
    fits = reading.plan(vault_dir, llm, step=step).mode == "whole"
    shared = bool(getattr(client, "signals_start", False)) and fits
    everything = (shared or (whole and fits)) and not narrow
    named = lambda n: sorted({p for i in groups[n] for p in pages[i]})  # noqa: E731

    def one(n: int, started=None) -> tuple[list[dict], dict, dict | None]:
        group = groups[n]
        ids, lines = [f"F{i + 1}" for i in group], [findings[i] for i in group]
        given = [] if everything else named(n)
        context = (before if narrow else "") + "<pages>\n" + "\n".join(f'<page path="{p}">\n{texts[p]}\n</page>' for p in given) + "\n</pages>"
        said = (above or ABOVE)["guide" if not given else "plan" if narrow else "pages"]
        try:
            return fix.propose(vault_dir, lines, llm, system=system.replace("<<ABOVE>>", said),
                               effort=steps.effort(step), web=web,
                               node=step if len(groups) == 1 else f"{step} {n + 1}/{len(groups)}",
                               excerpts=excerpts, what=headings[n] if headings else what, ids=ids,
                               context=context if given else None, cached=narrow or not given, started=started)
        except ModelError as e:
            failed = {"item_ids": ids, "corrections": [], "error": str(e),
                      "outcomes": [{"item_id": i, "event": "", "no_change_reason": f"not handled, the call failed: {e}"}
                                   for i in ids]}
            return fix.items_of(lines, excerpts, ids), failed, e.usage
    if len(groups) == 1:
        results = [one(0)]
    elif narrow:
        # The calls that have their own pages run together. Those whose findings name no page read the guide: on an
        # engine that shares it in the cache one leads and the others follow, else one after the other.
        rest = [n for n in range(len(groups)) if not named(n)]
        with ThreadPoolExecutor(max_workers=NARROW_PARALLEL) as pool:
            own = {n: pool.submit(one, n) for n in range(len(groups)) if n not in rest}
            if shared and fits and len(rest) > 1:
                guide = dict(zip(rest, _after_the_first(len(rest), lambda k, started=None: one(rest[k], started))))
            else:
                guide = {n: one(n) for n in rest}
            results = [own[n].result() if n in own else guide[n] for n in range(len(groups))]
    elif shared:
        results = _after_the_first(len(groups), one)
    elif everything:
        results = [one(n) for n in range(len(groups))]
    else:
        with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
            results = list(pool.map(one, range(len(groups))))
    if results and all(p.get("error") for _, p, _ in results):
        raise ModelError(results[0][1]["error"])
    items = sorted((i for its, _, _ in results for i in its), key=lambda i: int(i["id"][1:]))
    return items, [p for _, p, _ in results], [u for _, _, u in results if u]


def _after_the_first(n: int, one) -> list:
    """`one(i, started)` for i < n, for calls that share a cached context: one call leads, the others start together
    once it has begun to answer. A leader that ends without having begun (it failed) gives its place to the next.
    All the others at once, without a ceiling: one that waited for a free place would start after the cache has
    expired (five minutes after the last call that read it started)."""
    with ThreadPoolExecutor(max_workers=n) as pool:
        futures = []
        while len(futures) < n:
            begun = threading.Event()
            futures.append(pool.submit(one, len(futures), begun.set))
            while not begun.is_set() and not futures[-1].done():
                begun.wait(0.2)
            if begun.is_set():
                break
        futures += [pool.submit(one, i) for i in range(len(futures), n)]
        return [f.result() for f in futures]


# -- what the code checks itself: footnotes ------------------------------------------------------------------
NOTE_DEF = re.compile(r"^\[\^([^\]]+)\]:", re.M)


def _notes(text: str) -> tuple[set[str], set[str]]:
    """(the notes cited in the text, the notes defined in it)."""
    return set(vault._FOOTNOTE_MARK.findall(text)), set(NOTE_DEF.findall(text))


def _by_group(vault_dir: Path, corrections: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """The valid edits of the source pages, per (group, page): a group is applied whole."""
    out: dict[tuple[str, str], list[dict]] = {}
    for c in corrections:
        if c["check"] == "ok" and not vault.in_mirror(vault_dir, c["page"]):
            out.setdefault((c.get("group") or c["id"], c["page"]), []).append(c)
    return out


def _both(vault_dir: Path, page: str, edits: list[dict]) -> tuple[str, str]:
    """The page as it is, and as it would be with `edits` applied."""
    before = vault.read(vault_dir / page).replace("\r\n", "\n")
    after = before
    for c in edits:
        after = vault.replaced(after, c["current"], c["proposed"])
    return before, after


def _definition(text: str, note: str) -> str:
    """The definition of a note as it is in the page: its line and the indented lines that continue it."""
    m = re.search(rf"^\[\^{re.escape(note)}\]:.*(?:\n(?:    |\t).*)*", text, re.M)
    return m.group(0) if m else ""


def with_orphan_notes(vault_dir: Path, corrections: list[dict]) -> list[dict]:
    """The corrections, plus the removal of each note definition that a group leaves without a sentence citing it
    (in the same group: accepted or refused with the trim that orphans it). Seen per group: a note that two groups
    orphan together stays, which is harmless."""
    out = list(corrections)
    n = len(out)
    handled = {(c["page"], note) for c in out for note in NOTE_DEF.findall(c["current"])}
    for (group, page), edits in _by_group(vault_dir, corrections).items():
        before, after = _both(vault_dir, page, edits)
        (cited_b, defined_b), (cited_a, defined_a) = _notes(before), _notes(after)
        for note in sorted((defined_a - cited_a) - (defined_b - cited_b)):
            current = _definition(after, note)
            if not current or (page, note) in handled:
                continue
            handled.add((page, note))
            n += 1
            ref = edits[0]
            out.append({
                "id": f"C{n}", "item_id": ref["item_id"], "item_ids": ref["item_ids"], "proposal": ref["proposal"],
                "page": page, "current": current, "proposed": "", "source_url": ref["source_url"],
                "severity": "Minor", "group": group, "check": vault.check(vault_dir, page, current),
                "rationale": f"Note [^{note}] is no longer cited once {', '.join(c['id'] for c in edits)} "
                             f"{'applies' if len(edits) == 1 else 'apply'}.",
                "review": "added by the program: a note no sentence cites any more", "auto": True,
            })
    return out


def mark_dangling(vault_dir: Path, corrections: list[dict]) -> None:
    """Refuse the edits of a group that would leave a sentence citing a note whose definition is gone."""
    for (_, page), edits in _by_group(vault_dir, corrections).items():
        before, after = _both(vault_dir, page, edits)
        (cited_b, defined_b), (cited_a, defined_a) = _notes(before), _notes(after)
        dangling = (cited_a - defined_a) - (cited_b - defined_b)
        if not dangling:
            continue
        guilty = [c for c in edits if set(NOTE_DEF.findall(c["current"])) & dangling] or edits
        for c in guilty:
            c["check"] = "leaves " + ", ".join(f"[^{n}]" for n in sorted(dangling)) + " cited without its note"


def weight(vault_dir: Path, pages: list[str]) -> int:
    """Bytes of the given pages (line breaks as \\n), for the pull request: what the trims saved."""
    return sum(len(vault.read(vault_dir / p).replace("\r\n", "\n").encode("utf-8")) for p in pages
               if (vault_dir / p).is_file())
