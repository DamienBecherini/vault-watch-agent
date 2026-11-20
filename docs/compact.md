*[Version française](compact.fr.md)*

# Compaction: keep a guide from growing heavy

A watch only adds. A « since » note beside the old sentence, a footnote under the footnotes, the same warning
copied into three pages, a version kept « for the record »: each edit is right, and after a few months the guide
weighs half as much again without anyone having decided it. Compaction is a run of its own, apart from the watches,
that finds what weighs and proposes to trim it. Nothing is removed without your review: a trim goes through the
same cross-check, review, mirrors, audits and pull request as a correction.

It has three parts. The first is free; the other two call the model and say what they cost before they run.

| Part | What it does | Model |
| :-- | :-- | :-- |
| Sizes | Each page against its budget, its heaviest sections, what its footnotes weigh, what the guide gained in 90 days | none |
| Report | Reads the whole guide and lists what is repeated, what is piled-up history, which sections are longer than what they say. Edits nothing | one call (the cost of a cross-check) |
| Trims | For the findings you keep: targeted edits (current text, proposed text, reason), then cross-check, review, mirrors and pull request | a run |

## Sizes

```bash
vault-watch --guide ../my-guide compact        # the pages over their budget, then the heaviest; no model
vault-watch --guide ../my-guide doctor         # one line: the guide's weight, its growth, the pages over budget
```

In the interface: « Check the guide », the check « Size of the pages » (free, ticked by default).

The budget is a size in KB above which a page is flagged. It is 30 KB unless the manifest says otherwise:

```toml
[budget]
page_kb = 30                  # every page
[budget.pages]                # the pages of a folder; the first pattern that matches wins
"00-lexicon/**" = 8
"05-solutions/**" = 20
```

A page over its budget is a warning, never a failure: it says where to look first. The growth is read from Git
(what each page weighed 90 days ago on the current branch); a guide outside Git has sizes and no growth. A
read-only page (`[content] readonly`) is listed with its weight and never flagged: the agent does not edit it.

## The report

```bash
vault-watch --guide ../my-guide compact --report     # says the cost, asks, then lists the findings
```

In the interface: « Check the guide », the check « Compaction: what makes the guide heavy », with its estimate.

One call reads every page of the guide at once, with the heaviest pages and their heaviest sections named, and
lists three kinds of findings, the heaviest first:

- **Repeated**: the same fact, explanation, warning or table stated at length in several pages. The finding says
  which page should keep the full statement; the others shorten it and link there. A short reminder with a link is
  not a repetition.
- **History**: what is superseded and still stands beside the current fact: successive « since » notes, versions
  or prices kept for the record, advisories fixed long ago in versions below the minimum the guide requires.
- **Long**: a section that takes much more room than what it says needs, and what makes it long.

Each finding quotes its passages, found again in the pages by the code. The report edits nothing. A guide too
large for the model's window is read chapter by chapter, and the report says so: a repetition between two chapters
is then missed.

## The trims

Tick the findings you want acted on and create a compaction run (from the command line:
`vault-watch fix <thread> --findings findings.txt --compact`, one finding per line). The model reads the whole
guide again and proposes targeted edits, never a page rewritten whole:

- a repetition is shortened and linked to the page that keeps the full statement, with its source;
- piled-up history gives way to the current fact;
- a long section loses what repeats, never a fact, a figure, a caveat or a source.

Then the run takes the path of any other: a cross-check written for trims (is anything lost? does the page still
read on at that place? does the link point to a page that exists?), your review card by card, the mirrors, the
guide's audits, the pull request. Its branch is `compact/<thread>`, and the pull request says what the changed
pages weighed before and after.

## Which model

The report and the trims run on the reasoning model of the Settings, at effort `high`. Deciding what can go
without the guide saying less is a judgement on the whole guide: use the strongest model you have for these two
steps, and do not lower their effort.

They can have a model of their own, the watches keeping theirs: in the Settings, « Models and effort », « Set a
step apart », choose a model (and an effort if you want it fixed) for « what makes the guide heavy » (the report)
and « trims proposed » (the trims). The cross-check of the trims is the step « cross-check », shared with the
watches: it follows the role unless you set it apart too. See
[Choose a model](choose-a-model.md#a-model-for-one-step).

The estimates shown before each part follow the price of the model of each step. On the IA on-prem guide (about
434 k tokens), at the list prices of November 2026: about 3.4 $ for the report and 6.1 $ for a run of trims
with Claude Opus 5.5; with Claude Fable 5.2 on the two compaction steps, about 6.7 $ and 9.4 $. A run pays
for reading the guide twice: its proposals and its cross-check do not share the cache. These are estimates, counted
high, to be replaced by measures after the first real runs.

What a model thinks is billed as output and counts in the limit of what one call may write. The report lists at
most 30 findings so that its answer stays far from that limit; an answer cut at the limit is billed and lost, which
the journal and the check's cost then show.

## What the code checks itself

A model must not be trusted with what a program can verify:

- **A passage removed whole leaves no hole.** An empty proposed text removes the lines with their line break: a
  table keeps its rows together, a paragraph does not leave two blank lines.
- **A note no sentence cites any more goes with the trim.** When a trim removes the last sentence citing a
  footnote, the program adds the removal of its definition to the same group: accepted or refused together.
- **A sentence never keeps a note that is gone.** A trim that removes a footnote definition while a sentence still
  cites it cannot be applied.
- **What no page states any more is said.** Under each trim, the review lists the versions, advisory ids, amounts
  and links that its text holds and that no page of the guide will state once the trims apply. Removing a
  repetition lists nothing, since the page that keeps the fact still states it; removing the only mention of a
  price does. It is a signal, not a refusal: history is removed on purpose.

## At the source

The proposal step of a watch is told to replace the old fact rather than add a note beside it (« Replace, do not
pile up », since 1.0.1): history stays in Git and in the source. Less is piled up, so there is less to compact.

## When

On demand: after a few months of watches, or when `doctor` shows pages over their budget and a guide that grew
fast. Try the free part first. Quarterly is a sensible rhythm for a guide watched every week.
