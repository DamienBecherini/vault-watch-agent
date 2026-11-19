# Changelog

Versions follow the milestones of [phase G of ROADMAP.md](ROADMAP.md#phase-g--a-modular-agent). The version is written
once, in `src/vault_watch_agent/__init__.py`; `/api/health`, `/api/info` and the page footer show it.

## Unreleased

- A check of the guide that a stopped server left unfinished could not be handled: dismissing its leads or sending
  them to a fix run answered « the check is still running », for ever. Its leads are now handled like those of a
  finished check; the page says it was interrupted and which checks it did not reach; a check can be deleted.
- Replace, do not pile up (C2): the steps that write a correction (proposals of a watch, fix runs) are told to state
  the current fact in place of the old one, the history staying in Git; an old value is kept only when the reader
  needs it to act. The cross-check already judged it. This changes the prompts of every guide.
- The review page warns when a run made so far without a bill (a subscription, a local model) would continue on a
  billed engine, because the settings changed or another server resumes it. Seen on 19 November 2026: a fix run
  started on Claude Code had its translation billed to the API (0.16 $), the settings naming the API.

## 1.0.0 (2026-11-19)

M5: stable. The manifest, `watch.json`, the engine protocol and the settings are frozen at version 1
([docs/compatibility.md](docs/compatibility.md)); a guide can live on Gitea; the docs are written for someone who
is not the author.

- What a newcomer reads (T5.3): the README (EN, FR) rewritten around « your guide, your model, your decision »,
  with a quick start, what each part needs, the three engines and the forges; the IA on-prem guide is now the
  reference example, with its measures. `docs/security.md` (EN, FR): keys as references, what the model can and
  cannot do, what it reads is data, the local server, what to know before connecting a guide. `docs/code.md`
  brought up to date (three engines and plug-ins, two forges, the two modules it missed).
- The agent's folder (settings, the runs of each guide) and the cost journal are no longer created in the current
  folder: `~/.vault-watch/` and `~/.vault-watch/usage.jsonl` by default, so that a command run from a guide's folder
  writes nothing into it. A `.vault-watch` folder and a `metrics/usage.jsonl` already in the current folder (how the
  agent ran before, from its own clone) are still used; `VAULT_WATCH_HOME` and `VAULT_WATCH_JOURNAL` still win.
- Freeze (T5.2): the manifest, `watch.json`, the engine protocol and the settings each carry a version number, all
  `1`; `docs/compatibility.md` says what may change within a number (additions only) and how a new number comes
  (refused when newer than the agent, migrated when older). The settings get `"schema": 1` and their migrations
  (`config.MIGRATIONS`; a file without the number is read as 1); `EngineKind.protocol` (an engine package of
  another protocol is reported, not loaded). The watch source `github-issue` is now `issues` (a Gitea forge has
  issues too); the old name is still read.
- Gitea forge: a guide on a Gitea server says so in its manifest (`[guide] forge = "gitea"`, `forge_url`, and
  `forge_token`, a reference to the token: `env:GITEA_TOKEN` by default, or `sops:file#NAME`, `file:path`). The
  agent then reads the watch issues, downloads the Actions artifacts (Gitea 1.23 or later), opens the pull request
  and follows its state through the Gitea API; the branch is pushed by git as before. `doctor` checks the
  repository with the token; the interface names the forge and links the repository on it. GitHub is unchanged.
- Manifest: `[content] readonly`, pages the agent reads but never edits (generated pages, dated statements): a
  correction on one is refused (`read-only`), whatever step proposes it (proposals, cross-check, sweep, fixes), and
  every prompt is told. `[watch] changes_page`, a page where a watch records changes as dated lines: every proposal
  step sees it whole, whatever the keywords found. `doctor` lists both. Found on the second real guide (T5.1).
- The workflows use the actions that run on Node 24 (`setup-python@v7`, `checkout@v7`).
- `vault-watch collect`: a moving tag published as a release (`stable`, `latest`, `next`, `v1`…) is dropped at
  pre-triage, the real release kept; `docs/collect.md` says that `exclude` matches « owner/repo title ». The IA
  on-prem guide's collection is unchanged (166 items, 104 kept, both versions).

## 0.6.1 (2026-11-18)

- Python 3.11 works again: 0.6.0 stopped at its start on 3.11 (a backslash in an f-string's expression in
  `webtools.py`, which only 3.12 accepts; the engines' registry loads that module). A test now finds the f-strings
  3.11 refuses, whatever Python runs the tests.

## 0.6.0 (2026-11-18), M4: any model

- Engines are a protocol (`llm.Engine`: `parse`, `capabilities`, optional `count_tokens`) and a registry
  (`llm.engines()`): the Claude API, Claude Code, the OpenAI-compatible server, and any engine another package
  declares (entry point group `vault_watch_agent.engines`, an `EngineKind`). The Settings list the engines installed.
  `USAGE_KEYS`: what every usage returned holds.
- Contract tests (`tests/engine_contract.py`): what any engine must do, against recorded answers (a valid answer and
  its usage in the journal, an answer out of the schema, a refusal, a cut answer, a call with the web). The three
  engines pass it.
- The OpenAI-compatible engine (`openai_compat.py`): any server of `/v1/chat/completions`, hosted or local (llama.cpp,
  vLLM, Ollama, LM Studio). Its address, a key by reference, a model per role (the server's list offered), its
  window, structured output by `response_format` with the JSON schema or, when the server refuses it, the schema in
  the instructions and a tolerant reading of the answer; billed per token through the price table, or local and not
  billed. The context opens the system message, so that a server that caches a prompt's prefix (OpenAI, vLLM,
  llama.cpp, DeepSeek… automatically) reads the guide from its cache; the tokens it served are counted apart
  (`cache_read`). Anthropic's OpenAI layer has no cache: the engine says so in its capabilities.
- Web tools for a model without web of its own (`webtools.py`): search through SearXNG and page reading, run by the
  agent within the API engine's limits (20 searches, 30 pages per call). Only public addresses are read (never the
  machine itself or the local network, checked again after each redirection), the readable text of a page is cut at
  30,000 characters, a PDF is not read. Without a SearXNG address the model reads pages but cannot search, and the
  steps that check on the web say so (`steps.lacks`: « search »).
  Those searches are counted in the journal (`web_searches`) but not priced: they cost nothing.
  The page's text leaves out the empty items, headings and cells that icon menus leave (GitHub pages had dozens).
- Settings: the engine « OpenAI-compatible server » and its options; the cost shown before an action says « local
  model, not billed » or « billed by your provider » instead of a Claude estimate. Model ids of any form can be priced.
- What a call keeps beside the guide follows the model's window: 100k tokens with a window of 300k or more, a third
  of a smaller one (8k at least). A fixed 100k left a model of 64k tokens a negative budget, and even a small guide
  was cross-checked chapter by chapter (seen on the first run on a local model).
- The OpenAI-compatible engine, in `structured = "auto"`, puts the schema in the instructions whenever the server
  refuses a request carrying one (servers word that refusal their own way; Anthropic's OpenAI layer only takes strict
  schemas).
- `docs/write-an-engine.md` (and in French): the protocol, the capabilities, declaring an engine, the contract tests;
  its example, an engine for Ollama's own API in 90 lines (`examples/engines/ollama_engine.py`), passes them.
- The list of Claude models no longer fails with an HTTP 500 when no API key is set (the SDK raises a TypeError
  there): the Settings say why and offer the models the agent knows. The « Guide » category names the `feeds` watch
  source (missing since 0.5.0).
- `vault-watch eval`: the judge is a Claude model whatever model ran the watch (`--judge api|claude-code`; by default
  the watch's engine when it is a Claude one, otherwise Claude Code with a subscription, otherwise the API), so that
  a local model does not score its own proposals. The result names the models of the run and the judge.
- `docs/choose-a-model.md` (and in French): the models the IA on-prem guide uses (Claude Opus 5.5 for reasoning,
  Sonnet 5.5 for the mirror), what each step asks of a model, what was tried beyond them (Qwen3.6-35B-A3B on an
  8 GB laptop GPU: no proposal on watch #77, where Opus made three), and `vault-watch eval` with its limits. No
  other model is promised.

## 0.5.0 (2026-11-18), M3: any watch

- The watch format is a contract: `docs/watch-format.md` (and in French) describes `watch.json` key by key, with a
  `schema` number. The loader checks it: a newer schema is refused with « update vault-watch-agent », an item
  without `title` or `triage`, a `triage` other than keep or drop, a watch without `until` or a file that is not
  JSON are refused with what is wrong and where. Every watch of the IA on-prem guide since October follows it; the
  sample guide's watch now dates its two dropped items and declares `schema = 1`.
- Watch sources (`watches.py`): the manifest's `[watch] source` gives the watches of the interface. `github-issue`:
  the issues with its label, as before. `file`: a `watch.json` of the guide or a folder of them, listed with their
  window and items kept, started from the page; a file that breaks the format is listed with what is wrong. `none`:
  no watch. The page shows an issue's number only for an issue.
- The forge (`forge.py`): the calls to `gh` (watch issues, their body, closing one, the workflow artifact, opening a
  pull request, its state, whether the repository can be read) are the methods of `GitHub`, behind a `Forge`
  interface a Gitea or GitLab forge can fill. The number of items is read from an issue title in French or
  English (« 73 éléments », « 73 items »).
- `vault-watch collect` (`collect.py`): the agent collects a watch itself from the guide's `feeds.json` (manifest
  `[watch] feeds`, with `floors` and `seen`), without a model. Feed types: GitHub releases, tags and security
  advisories, RSS and Atom, YouTube, Hugging Face authors and trending models, GitHub search. The rules drop
  pre-releases, routine patches (unless their notes mention a security fix), advisories of low severity or already
  fixed at the guide's floor, quantized variants and adapters, and items already seen; a High or Critical advisory
  the floor does not cover is urgent. A port of the IA on-prem guide's `watch-feeds.mjs`: on its 63 feeds and the
  same window, both give the same items, the same triage and the same notes (455 items, 241 kept, since 1 June).
  Only the standard library. `docs/collect.md` (and in French).
- `source = "feeds"`: the interface lists the watches collected in the guide's working folder and has a « Collect
  a watch » button (free); a second collection the same day never overwrites the first. `doctor` checks the feeds
  file. The sample guide has a `feeds.json` (real projects of the kind it describes) and a floors file.
- The reusable workflow `.github/workflows/collect.yml`: a guide calls it from a ten-line workflow; it collects every
  week, keeps `watch.json` as an artifact and opens the issue the `github-issue` source reads (label, artifact,
  window, urgent-only runs as inputs). `sample-watch.yml` runs it on the sample guide by hand.
- `docs/code.md` lists every module again, with its size.

## 0.4.1 (2026-11-18)

- A verification's file is written aside then put in place in one go: the page, which reads it every few seconds
  while the checks run, could read it empty in the middle of a write (seen as a test failing once on GitHub).

## 0.4.0 (2026-11-18), M2: prices and capabilities

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
- One table of the steps that call the model (`steps.py`): for each, the role whose model runs it, the effort it
  asks for and what it needs (the web, the whole guide). The call sites read their effort from it, and the Settings
  list each step of a role from it (`STEP_EFFORTS` of `web.py` is derived from it).
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
