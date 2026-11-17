# Watch brief (the agent's default)

The rules for the items of a watch, used when the guide gives no brief of its own (`[rules] brief` in its
manifest). A guide replaces it with its own, written for its subject.

## What a kept item can lead to

1. **Nothing.** It changes no sentence of the guide: say why in one line.
2. **A correction.** A sentence, a table row or a footnote of the guide is now wrong or outdated.
3. **An addition.** The guide does not cover it and it crosses the addition threshold below.

A new release is not by itself a reason to edit: the guide must say something the release changes (a version, a
flag, a default, a price, a date, a recommendation, a security floor).

## Sources

- **Tier A**: the primary source. Release notes, official documentation, the vendor's page, the advisory itself,
  the paper.
- **Tier B**: reputable secondary sources that cite their own evidence (established technical press, a maintainer's
  post).
- **Tier C**: forums, social posts, videos, aggregators. A lead only, never a citation.

A correction rests on one tier A source, or two independent tier B sources, with the date of the fact. Use the
item's cached notes first; never rely on memory for a figure, a version or a date. When the evidence does not
establish the fact, propose nothing and say so.

## Corrections

- The smallest change that makes the guide true: one sentence or one table row, copied verbatim as it is now.
- In the language and register of the page, same Markdown; wiki links `[[...]]` and footnote markers `[^n]` kept.
  Inside a table, write the alias separator of a wiki link as `\|`: a bare `|` ends the cell.
- Dated wording for facts that move ("since version 0.33", "as of Q4 2026").
- The footnote that supports a changed fact is updated with it, in the same group.

**Severity.** Critical: security, or a wrong recommendation that could cause harm. Major: a fact that changes a
decision (version, price, availability, support, compatibility). Minor: wording or a detail.

## Additions

Only when the item is backed by tier A (or two tier B) sources **and** changes a decision a reader of the guide
makes. A paragraph before a new page; a new page is a note for the editor, never written without their go-ahead.
Third-party repacks, rumours and benchmark curiosities never qualify.
