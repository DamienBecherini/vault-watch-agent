# Changelog

Versions follow the milestones of [phase G of ROADMAP.md](ROADMAP.md#phase-g--a-modular-agent). The version is written
once, in `src/vault_watch_agent/__init__.py`; `/api/health`, `/api/info` and the page footer show it.

## Unreleased (0.4.0, M2: prices and capabilities)

- `prices.py`: a price is four rates (input, output, cache read, cache write) with its origin. Sources in order:
  the user's prices (`prices` in the Settings), a list fetched on request (`prices.json` of the home, with its
  date), the defaults shipped (`defaults/prices.json`, checked in November 2026; they were `llm.PRICES`). A dated
  model id takes the price of its model; a damaged fetched list is ignored, never read as a price.
- The journal records with each API call the price it was counted at and its origin (`price`, `price_origin`);
  `costs.py` adds up `cost_usd` as written and never recomputes a past cost. Since 0.2.0 (17 November 2026) the
  cache reads of Sonnet 5.5 count at 0.10 $ per million tokens (0.20 before); the lines written before stay as
  they are.
- Settings: `prices` (model id -> its four rates), checked when saved; a page that saves without them keeps them.
- `vault-watch prices show` lists the price of each model and its origin; `vault-watch prices update` reads
  LiteLLM's public list (the Claude models of Anthropic, USD per token turned into USD per million), shows what
  changes, and replaces the fetched list only on `--yes` or a yes typed at the prompt. A list that cannot be read,
  or holds no Claude model, changes nothing. Nothing is fetched without this command.
- Settings, a « Prices » category: each model's four rates and where they come from (set here, the list of a
  date, the default of 2026-11, no price), the models in use first; a price set here (checked: four numbers, 0 or
  more) and « back to the default price ». « Read the list » fetches LiteLLM's list and shows what it would change;
  « Replace with this list » puts it in place. Nothing is fetched without that click.
- Each engine declares what it can do (`llm.Capabilities`): the model's input window, structured output, web
  (and whether the model reads the page itself or a summary of it), effort levels, caching, billing, exact token
  count. The window comes from the Models API when it was read, else 1M for a model the agent knows and 200k for
  one it does not. The list of the models in the Settings no longer leaves out the models with a smaller window.
- The context decides how the guide is read (`reading.py`): the guide is counted once per run (exactly on the
  API, which counts tokens for free; else estimated from its size with a 15 % margin) and compared with the model's
  window minus a reserve of 100 k tokens, capped by `[budget] max_context_tokens`. Fits: the whole guide in one
  call, as before. Does not: the cross-check, its sweep and the coherence check run chapter by chapter (one top
  folder per call, with the pages the corrections change; a correction keeps the verdict of its own chapter), and
  the report, the review screen and the verification say « by chapter: a contradiction between two chapters can be
  missed ».
- The example manifest of the IA on-prem guide no longer sets `[budget] max_context_tokens` (it was 450 000, below
  the estimate of the guide with its margin, about 500 000 tokens: the cross-check would have gone by chapter).
- The estimates of the checks say where their price comes from when it is the default or none; the Costs page
  counts the API calls by the origin of their price (the lines before 0.4.0: « list prices of the time »).

## 0.3.2 (2026-11-18)

- READMEs: the review screen right after the introduction (a new capture, English and French, from the replay of
  watch #77), a « What this repository shows » section, and the pull requests of the guide as a count (twelve)
  instead of the first three.
- Interface: the colon follows the language (" : " in French, ": " in English) in the review
  cards, the addition leads and the applied corrections.

## 0.3.1 (2026-11-18)

- The runs made before 0.3.0 stay visible once the IA on-prem guide has its manifest: they belong to that guide
  whether it is read with its manifest or without one (0.3.0 gave a guide with a manifest a new, empty working
  folder).

## 0.3.0 (2026-11-18), M1: any guide

- `guide.py`: the manifest of a guide (`vault-watch.toml`): name, repository, site, base branch, language, pages
  (include and exclude globs), mirrors, modified field, watch, rules, checks, budget. An unknown key or a wrong value
  is an error that names the key. Two manifests in `examples/`: the sample guide's, and the IA on-prem guide's,
  which finds the same 129 pages as the agent does today.
- The pages, the mirrors and the date an edit bumps come from the manifest (`vault.guide_of`): a guide without
  mirror has all its pages read, one without `modified_field` keeps its dates. A guide without a manifest is read as
  the IA on-prem guide (French, `en/`, `last_modified`), as before.
- The prompts describe the guide from its manifest (name, language, `[guide] description`, mirrors) and read its
  rules from `[rules]`; the mirror step keeps every declared mirror in step, in its language (it assumed French to
  English under `en/`). A guide without a mirror no longer reports « no English mirror ».
- The guide's own checks are the commands of `[checks]` (audits, claims due, source audit, version floors), run in
  a copy of the guide, `{out}` replaced by the JSON file the agent reads. A check the guide does not declare is
  « not checked » in the verification and on the publish screen, not a failure.
- The repository, the site, the base branch, the label of the watch issues and the name of the watch artifact come
  from the manifest. A guide without repository is local: no issue listed, no link to GitHub in the header.
- Every prompt names the guide and its language from the manifest (`prompts.fill`): cross-check, fix, verification,
  evaluation judge. The translation check and the translation fixes work on each declared mirror, in its language;
  a guide without mirror skips the translation check. A test fails if a string of the IA on-prem guide comes back
  into the code (outside `guide.legacy`, and `cli.py` until `--guide`).
- Settings: a « Guide » category, read-only, from the manifest: name, subject, language and pages, repository, site,
  branch, and each part (mirror, modified date, watch, rules, checks, context budget) provided or missing, with what
  a missing one switches off. Without a manifest it says the guide is read as the IA on-prem guide.
- A check the guide does not declare reads « not checked » on the publish screen and in the pull request (audits
  and source audit), instead of « passed » or « all answer ».
- `vault-watch init` writes the manifest of a guide from what its folder shows: the GitHub repository of its
  remote, its branch, the language of its pages, the folders that mirror them, the date field of their front
  matter, the tooling and the `_` folders (private notes, templates) left out, its npm scripts as hints for
  `[checks]`; each guess is commented, and what it writes is loaded before it is written. `vault-watch doctor` lists
  what is ready and what is missing before a run: the manifest, the pages, each mirror, git (the guide must be the
  root of its repository), `gh` and the repository, the watch, each check and its program, the engine (Claude Code
  signed in with a subscription, or the API key found). Exit code 1 when something stops a run.
- A guide without repository: « publish » keeps the branch on the machine (no push, no pull request, no issue to
  close); the button says so. Found by running the sample guide end to end on Claude Code.
- Docs: « Connect your guide » (`docs/connect-your-guide.md`, in French `docs/connect-your-guide.fr.md`): the
  manifest key by key, the formats the checks and the watch must produce, what each optional part unlocks, the
  sample guide as the worked example. The overview (`docs/presentation*.md`) is up to date: twelve pull requests of
  the guide, the cost journal of 17 November, the Claude Code engine, phase G.
- Default rules shipped with the agent (`src/vault_watch_agent/defaults/`): a watch brief (sources by tier, what a
  correction and an addition are, severity) and a translation policy, written from the IA on-prem ones without what
  is specific to that guide. A guide without `[rules]` gets them.
- `--guide FOLDER` on every command. Without it: `VAULT_PATH`, then the current folder when it has a
  `vault-watch.toml`, then `../ia-on-prem-vault` as before. Each guide has its working folder (checkpoints,
  worktrees, verifications) under `.vault-watch/guides/<repository>/`; the runs made before stay in `.vault-watch/`
  for the guide they belong to (recorded in `.vault-watch/guide.json`, nothing moved); the settings are shared. The
  page shows the name of its guide in the header and the tab title. A wrong manifest stops the command with the key
  to fix.

## 0.2.1 (2026-11-17)

- The search for a replacement of a dead link gets what each page says with that source (the lines that cite it
  and, for a footnote, the lines that call it): it had only the URL, and said it could not open the pages.
- The review takes the ids as a list or as one string "C1,C3": a string was read letter by letter, and the run ended
  with nothing applied.
- One git operation at a time on the guide's repository: a fix pass and a translation pass started together
  failed on git's `index.lock` (both updated the reading copy of main at once).

## 0.2.0 (2026-11-17), M0: ground

- One version, read from `vault_watch_agent.__version__` by `pyproject.toml`, `/api/health`, `/api/info` and the page
  footer (an install left in `site-packages` no longer shows its own version when the source runs).
- A verification and the proposals for reported errors read the guide as merged: `main` brought up to date with
  origin, in a copy of the agent (`.vault-watch/worktrees/read-main`), whatever branch or work in progress the folder
  of the guide holds. They read that folder before: on 17/11, still on an old branch, it lacked the corrections just
  merged (#78). The page of a verification shows the commit it read, and which check is running.
- Header: a link « Claude API » to the billing page of the Claude Platform.
- CI: the tests on Linux and Windows, Python 3.11 and 3.12 (`.github/workflows/tests.yml`).
- Sample guide (`examples/sample-guide/`): twelve pages about a made-up notes server, planted errors, a watch of eight
  items; a run with a fake model goes through it (`tests/test_sample_guide.py`).

### Baseline

What every later milestone is compared with (2026-11-17).

| What | Value |
| :-- | :-- |
| Tests | 75 passing (Windows, Python 3.12) |
| First full run after the two engines (watch #77, API engine) | 11 corrections, all applied; $3.44; merged as #78 |

Published `eval` scores (`metrics/eval/`, model engine: API):

| Watch | Variant | Guide commit | Proposals | Recall | Recall (corrections) | Precision | Lenient precision | Run cost | Judge cost |
| :-- | :-- | :-- | --: | --: | --: | --: | --: | --: | --: |
| #30 | full | 7cb34a3 | 4 | 0.154 | n/a | 1.0 | 1.0 | $3.42 | $0.08 |
| #30 | full, v2 | 7cb34a3 | 2 | 0.115 | 0.200 | 1.0 | 1.0 | $3.30 | $0.08 |
| #30 | full, v3 | 7cb34a3 | 3 | 0.077 | 0.133 | 0.667 | 1.0 | $1.48 | $0.08 |
| #30 | keyword | 7cb34a3 | 1 | 0.038 | 0.067 | 1.0 | 1.0 | $0.66 | $0.07 |
| #47 | full | 4ca9e00 | 0 | n/a | n/a | n/a | n/a | $0.42 | $0.00 |
| #47 | keyword | 4ca9e00 | 0 | n/a | n/a | n/a | n/a | $0.42 | $0.00 |

Watch #30 has 26 changes in its reference (15 of them corrections); watch #47 has none, so only its cost counts.

## 0.1.0 (2026-11-17)

The state before the modular work: an agent for one guide, the IA on-prem vault.

- LangGraph graph: triage of the watch, proposals in parallel, cross-check, deterministic checks, dead links, two human
  pauses (review of the proposals, review of the pull request), translation of the English mirror, pull request.
- Local web page (FastAPI, `127.0.0.1:4430`): the watches, the review, a check of the whole guide, a report of an
  error, the costs.
- Two model engines: `claude-code` (`claude -p` on the Claude subscription of the machine, nothing billed) and `api`
  (Anthropic API). Without a choice, Claude Code when it is signed in with a subscription; never a silent fall back to
  the API.
- Settings window: engine, API key given by reference only (`env:`, `file:`, `sops:`), models read from the Models API
  (1M context only), effort per role.
- Header tools ported from dl-sub-dub: size of the text, light and dark, palettes with a contrast check, browser
  notifications, French and English.
- Costs per call in `.vault-watch/usage.jsonl` (cache reads and writes included), the engine and effort of each call,
  and what the subscription spared.
