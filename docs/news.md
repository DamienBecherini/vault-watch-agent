*[Version française](news.fr.md)*

# Look for what is new: what a reader would look for and not find

A watch follows the sources it already knows. What none of them announces stays out of the guide: a new hardware
generation from a vendor nobody added to the feeds, a subject that became an obligation, a tool that appeared
since the guide was written. And what a watch does see but sets aside as a « possible addition » is never
written: it stays one line in a report. This run is apart from the watches. It looks for what is missing and
proposes to add it; nothing is written without your review, and an addition takes the path of a correction:
cross-check, review, mirrors, the guide's checks, pull request.

It has two parts. Both call the model and say their cost before they run. The leads can be found in two ways,
which answer two different questions; their leads go to the same run.

| Part | What it does | Web |
| :-- | :-- | :-- |
| Leads, from the guide | Reads the whole guide, and what past watches set aside, and lists what to go and check. Verifies nothing, edits nothing | no |
| Leads, from the web | For each chapter you choose, searches the web freely for what moved on its subjects and compares it with the whole guide. Edits nothing | yes |
| Additions | For the leads you keep: checks each one on primary sources, then proposes where to write it, or says why not | yes |

> **Limit.** This run adds to existing pages only: it never writes a new page. When a subject would need a page of
> its own, it says so, at the top of the review screen, of its report and of the pull request, and leaves the
> decision to you.

## The leads

```bash
vault-watch --guide ../my-guide news           # says its cost and asks before the call
```

In the interface: « Check the guide », check « What is new: what a reader would look for and not find ».

One call reads every page of the guide at once. It lists at most 30 leads, of three kinds:

| Kind | What it is |
| :-- | :-- |
| `Newer` | Something the guide presents as current that has probably moved on: a product generation, a model family, a major version, a price list, a rule in force |
| `Missing` | A subject, a tool, a model, a piece of hardware, a risk or an obligation the guide owes its readers and no page covers |
| `Seen by the watch` | An item past watches set aside as a possible addition, which the guide still does not cover |

A lead is a question, not a fact. The model verifies nothing at this stage, and what it knows may be older than
the guide: it is asked what to check and on which kind of primary source, never a figure, a version or a date.
The guide's own threshold for additions (its contract, `[rules] brief` of the manifest) is given to it.

The items set aside by past watches are read from the reports of the runs kept on the machine (their section
« Addition candidates »), over the last 120 days, each address once: no model and no network for that part.

Leads about read-only pages alone are left out. As with any check, you keep the leads you want, dismiss the
others, and send those kept to a run.

## The leads, from the web

```bash
vault-watch --guide ../my-guide news --explore                        # every chapter the guide explores by default
vault-watch --guide ../my-guide news --explore --chapters 02-hardware,03-stack
```

In the interface: the check « What is new: the web explored, chapter by chapter »; ticking it shows the chapters
with their weight, and the cost follows the chapters you keep. All are ticked, except those the guide declares
with `explore = false` (a glossary, the pages about the project). What a chapter is, and how to have a model
propose them: [`[[chapter]]` in the manifest](connect-your-guide.md#chapter).

One call per chapter. Each reads the whole guide and searches the web on the subjects of its chapter (about 12
searches and 15 pages), opens primary sources, and keeps what no page of the guide says, eight leads at the most
per chapter. A lead of this kind (`Found on the web`) is a fact read on a source, and it carries the addresses
that establish it. A lead two chapters found from the same source is listed once.

| | From the guide | From the web |
| :-- | :-- | :-- |
| Who decides what to look for | One call reads the guide and asks at most 30 questions | Each call searches freely on a chapter's subjects |
| What you tick | Questions, not verified yet | Facts already found, with their sources |
| When the web is paid for | After you chose, for the leads kept | Before you have seen anything, for each chapter |
| What it can miss | What nobody thought to ask | What a dozen searches per chapter did not come across |

The first answers « is this still current, is that known subject missing? »; the second is the only one that
finds what you did not know to ask. A chapter whose call fails is said in the result, and the others go on.

## An idea or a piece of news of your own

When you already know what to look at, skip the search for leads: « Report or suggest », tab « An idea or a piece
of news to dig into » (a link on « Check the guide » leads there). One subject per line, with an address if you
have one; a box asks that each be dug deeper. The subjects go straight to an addition run.

```bash
vault-watch --guide ../my-guide fix my-idea --findings idea.txt --add     # a line that begins with ! is dug deeper
```

## The additions

```bash
vault-watch --guide ../my-guide fix add-2026-11-20 --findings leads.txt --add
```

In the interface: tick the leads, then « Create an addition run »; the button shows an estimate that follows the
number of leads ticked.

For each lead, the model searches the web and opens primary sources, then decides:

- nothing new, nothing a primary source establishes, already covered, or below the guide's threshold: no edit,
  and the reason in one line, in the report of the run;
- the guide states something superseded: a correction where it is stated, the current fact in place of the old
  one;
- the guide lacks it: an addition where a reader would look for it (a sentence in its paragraph, a row in the
  table that lists such things, a short paragraph under the right heading), with its source cited the way the
  page cites its sources;
- it would need a page of its own: the page is not written. The report says « needs a page » with what it would
  hold and where; writing a new page stays your decision.

**Dig deeper.** Beside each lead, a box « dig deeper » (on the command line, a `!` at the start of its line in the
file). Its call is then asked for a fuller look: several independent sources, what it replaces, how mature and
available it is, what it changes for each kind of reader, on several pages if need be. It costs a little more
than a lead; keep it for the subjects that deserve it.

The review shows, above the corrections, the pages the run says would be needed, then the leads it left without
an edit and why: what a search found without writing anything is a result too.

The edits then go through the cross-check of a watch (the whole guide and the cited source opened again), your
review, the mirrors, the guide's checks and the pull request, on a branch `feat/<run>`.

## What each call reads, and what it costs

The leads take one call that reads the whole guide. The additions take one call per lead. The web of a call has
a ceiling (20 searches, 30 pages), and leads that shared a call took it from one another: on the first real run,
a lead about six price lists left its three neighbours unchecked. A lead its call could not look at is marked
« not checked by the run » on the verification, with a button that puts it back among the leads to handle. What
two calls add to the same page is put together by the program (a footnote marker both chose is renamed, two rows
after the same row both apply). Every call reads the whole guide. On the Claude API the first call writes it to
the prompt cache and the others read it from there; with another engine the calls follow one another.

The estimates below are for the IA on-prem guide (129 pages, about 430 000 tokens) with Opus 5.5 for the leads,
the additions and the cross-check. Unless said otherwise they are not measured yet: the constants are counted high and will be set
on the first real runs.

| | Estimate |
| :-- | :-- |
| The leads, from the guide | ≈ 2.40 $ (2.28 $ measured on 2026-11-20 for 28 leads) |
| The leads, from the web | ≈ 2 $, plus ≈ 4.75 $ per chapter explored |
| An addition run | ≈ 4.40 $, plus ≈ 2.90 $ per lead kept, or ≈ 3.70 $ for a lead dug deeper |

The addition run is set on two real runs (2026-11-20). The first: 11.01 $ for a lead about six price lists and a
lead dug deeper, 29 edits, mirrors included. The second: 12.78 $ before the mirrors for three leads (two security
floors to check, one subject to add), 14 edits, for 13.10 $ announced. A lead that checks one version is not
cheaper than another: 16 to 25 rounds of search each. Most of a lead's cost is the guide read again from the cache
at each round.

The steps « leads of what is new », « the web explored by chapter » and « additions checked on the web » appear in
the Settings, where each can run on a model of its own. With an engine paid by a subscription nothing is billed,
and these calls count in its limits.

## What it does not do

- It does not write a new page, nor a new lexicon entry in a file of its own: it says one is needed.
- It does not replace the watch: the watch reads what its sources publish every week, for a few cents; this run
  looks, now and then, for what no source announces.
- It does not check what the guide already says (the checks « Consistency of the whole guide » and « Re-check of
  dated claims » do).

## When

After a compaction rather than before: this run adds to the guide, and it reads it whole. Once a quarter is a
reasonable rhythm for a guide that a weekly watch already follows, or when a subject moves fast.
