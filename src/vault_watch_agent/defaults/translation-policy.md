# Translation policy (the agent's default)

How a mirror follows the pages of the guide, used when the guide gives no policy of its own
(`[rules] translation_policy` in its manifest).

## Fidelity over fluency

- Translate the meaning faithfully; do not restructure the argument, add or drop a nuance.
- Keep tables, lists, headings and callouts aligned with the source page, in the same order.
- Use the terms the mirror already uses elsewhere, for consistency.

## What stays as it is

- Wiki link targets (`[[folder/page]]`), footnote markers (`[^1]`) and URLs.
- Code blocks, commands, file names, environment variables, product and model names.
- Inside a table, the alias separator of a wiki link is written `\|`: a bare `|` ends the cell.

## Front matter

Translate `title` and `description`; copy every other field from the source page, the modified date included.

## Only what changed

When the source page is edited, translate the edited passage only and leave the rest of the mirror page as it is.
If the mirror page has no passage that matches the edit, say so rather than guess.
