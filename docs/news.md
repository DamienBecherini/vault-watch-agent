*[Version française](news.fr.md)*

# Look for what is new: what a reader would look for and not find

A watch follows the sources it already knows. What none of them announces stays out of the guide: a new hardware
generation from a vendor nobody added to the feeds, a subject that became an obligation, a tool that appeared
since the guide was written. And what a watch does see but sets aside as a « possible addition » is never
written: it stays one line in a report. This run is apart from the watches. It looks for what is missing and
proposes to add it; nothing is written without your review, and an addition takes the path of a correction:
cross-check, review, mirrors, the guide's checks, pull request.

It has two parts. Both call the model and say their cost before they run.

| Part | What it does | Web |
| :-- | :-- | :-- |
| Leads | Reads the whole guide, and what past watches set aside, and lists what to go and check. Verifies nothing, edits nothing | no |
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

The edits then go through the cross-check of a watch (the whole guide and the cited source opened again), your
review, the mirrors, the guide's checks and the pull request, on a branch `feat/<run>`.

## What each call reads, and what it costs

The leads take one call that reads the whole guide. The additions take several calls, four leads each, grouped by
the pages they name: every round of search re-reads what the call has gathered so far, so one long call costs
much more than several short ones. Every call reads the whole guide. On the Claude API the first call writes it
to the prompt cache and the others read it from there; with another engine the calls follow one another.

The estimates below are for the IA on-prem guide (129 pages, about 430 000 tokens) with Opus 5.5 for the leads,
the additions and the cross-check. They are not measured yet: the constants are counted high and will be set
on the first real runs.

| | Estimate |
| :-- | :-- |
| The leads | ≈ 2.80 $ |
| An addition run | ≈ 4.40 $, plus ≈ 0.75 $ per lead kept |

The steps « leads of what is new » and « additions checked on the web » appear in the Settings, where each can run
on a model of its own.

## What it does not do

- It does not write a new page, nor a new lexicon entry in a file of its own: it says one is needed.
- It does not replace the watch: the watch reads what its sources publish every week, for a few cents; this run
  looks, now and then, for what no source announces.
- It does not check what the guide already says (the checks « Consistency of the whole guide » and « Re-check of
  dated claims » do).

## When

After a compaction rather than before: this run adds to the guide, and it reads it whole. Once a quarter is a
reasonable rhythm for a guide that a weekly watch already follows, or when a subject moves fast.
