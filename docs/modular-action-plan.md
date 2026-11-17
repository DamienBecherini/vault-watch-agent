# Action plan: a modular agent

The why and the design are in [modular-plan.md](modular-plan.md). This page is the work, in the order to do it:
six milestones, each one a version that leaves the IA on-prem guide working as it does today.

How to read it: a task is done when its test exists and passes; a milestone is done when its "Done when" list is
true, the version is tagged, and `main` receives it (work happens on the `dev` branch, see
[Working rules](#working-rules)).

| Milestone | Version | What someone else can do after it |
| :-- | :-- | :-- |
| M0. Ground | 0.2.0 | Clone, run the tests, try the agent on a sample guide |
| M1. Any guide | 0.3.0 | Point the agent at their own guide with a manifest |
| M2. Prices and capabilities | 0.4.0 | Trust the costs shown; see which steps a model can run |
| M3. Any watch | 0.5.0 | Get a watch without writing a collector |
| M4. Any model | 0.6.0 | Run the steps on an OpenAI-compatible model, local ones included |
| M5. Stable | 1.0.0 | Rely on the manifest and the engine protocol not changing under them |

## Decisions to take first

Each has a default, taken if nothing else is said.

| Decision | Default | Needed by |
| :-- | :-- | :-- |
| Format and place of the manifest | `vault-watch.toml` at the root of the guide (`tomllib` is in Python 3.11, no dependency) | M1 |
| Name of the thing watched, in code and docs | "guide" everywhere; `VAULT_PATH` kept as an alias of `--guide` | M1 |
| Second real guide to try the manifest on | To find: without one, the format stays "experimental" in 1.0 | M5 |
| Search API of the web tools | SearXNG first (self-hosted, no key), the port open to others | M4 |
| Public price list | LiteLLM's JSON, fetched on demand, never at start | M2 |
| First model of the OpenAI-compatible engine to publish scores for | One hosted (to choose) and one local on the homelab | M4 |

## M0. Ground (0.2.0)

Nothing visible changes; everything after depends on it.

- **T0.1 Baseline.** Run the suite and keep its count; copy the published `eval` scores of `metrics/eval/` in a
  table of the changelog: the figures every later milestone is compared with. Run watch #77 for real on the Claude
  Code engine once (first full run on the subscription, open since 2026-11-17) and note the usage it took.
- **T0.2 Version and changelog.** `CHANGELOG.md` (0.1.0 = the state of 2026-11-17: the two engines, the Settings,
  the header tools); the version read from one place (`pyproject.toml`), shown in the interface footer and in
  `/api/health` (already there).
- **T0.3 CI.** A workflow that runs `pytest` on every push and pull request (Python 3.11 and 3.12, Windows and
  Linux: the agent runs `claude`, `git`, `gh`, `node` as subprocesses, paths matter).
- **T0.4 Sample guide.** `examples/sample-guide/`: twelve pages in English in three chapters, one of them with a
  planted error per check (a stale version, a contradiction between two pages, a dead link), a `watch.json` of
  eight items, no script, no mirror. A fixture copies it into a temporary git repository; `test_graph.py` and
  `test_web.py` use it instead of building their own.
  Done 17/11 (`tests/conftest.py`, `tests/test_sample_guide.py`): a whole run with a fake model finds the planted
  version and port. The fixture still adds a stub `audit-freshness.mjs`, and the test pins what a guide without a
  mirror or scripts gets today (problems reported at the publish step). Moved to M1 (T1.2): `test_graph.py` and
  `test_web.py` on the sample guide, since they test the French source, the mirror and the scripts, which become
  optional there; the prompts also still say the guide is French.
- **T0.5 Contributor entry.** `CONTRIBUTING.md` (set up, tests, the sample guide, commit style, how a change is
  proposed); issue templates (bug, guide not supported, engine request).

Done when: a fresh clone passes the tests on both systems in CI; the sample guide goes through a run with the
fake model; the changelog holds the baseline.

## M1. Any guide (0.3.0)

- **T1.1 `guide.py`: the manifest.** Read `vault-watch.toml` with `tomllib`, validate it (unknown key: an error
  that names it; missing optional part: `None`), return a frozen `Guide` (name, repository, site, base branch,
  content language, include and exclude globs, mirrors, modified field, watch, rules, checks, budget, schema
  version). Tests: defaults, each refusal, the IA on-prem manifest, the sample one.
- **T1.2 The guide through the code.** `Deps` carries the `Guide` instead of a path. Replace, one module per
  commit: `vault.french_pages` and its skipped folders by the globs (`vault.pages`); `last_modified` by the
  manifest's field (no bump when absent); `en/` by the mirrors (`graph.mirror`, `verify`, `evaluate`); the
  repository and the site in `graph.py` and `web.py`; `prompts.py` by the manifest's rules. Test: no string of
  the IA on-prem guide left in `src/` (a test greps for it).
- **T1.3 Optional parts.** A step whose part is missing is skipped and says so in the run view and the report:
  no `[checks].audits` → no audit step and "not checked" in the publish screen; no mirror → no translation; no
  floors → no floor alignment; no `claims_due` → none listed. The interface shows what the guide provides
  (a "Guide" category in the Settings: read-only, from the manifest).
- **T1.4 Default rules.** A brief and a translation policy shipped with the agent (`src/…/defaults/`), written
  from the IA on-prem ones without what is specific to it; the prompts no longer assume French (the language of
  the manifest is named in them).
- **T1.5 Several guides.** `--guide <path>` on every command; the home of a guide is `.vault-watch/` under the
  agent's home, one folder per guide (the name of its repository); the web interface serves one guide per
  process, its name in the header. `VAULT_PATH` and the current `.vault-watch/` keep working (moved once, with a
  message).
- **T1.6 `vault-watch init`.** Looks at a repository (remote, default branch, folders, front matter, scripts) and
  writes a manifest with what it found and comments for what it did not; `vault-watch doctor` lists, step by
  step, what will run and what will be skipped, and what is missing on the machine (`gh`, `node`, `claude`).
- **T1.7 The manifest of the IA on-prem guide.** A pull request of the guide adding `vault-watch.toml`; in the
  same one, the lines of its `CLAUDE.md` and of the `vault-watch` skill that still say a run is billed.
- **T1.8 Docs.** "Connect your guide": the manifest key by key, what each optional part unlocks, the sample
  guide as the worked example.

Done when: the IA on-prem guide runs a real watch with its manifest and gives the same corrections as the
baseline run within the usual variation; the sample guide runs end to end; `init` on a repository it never saw
gives a manifest `doctor` accepts.

## M2. Prices and capabilities (0.4.0)

Two independent halves; the first is small and can ship alone.

**Prices**

- **T2.1 `prices.py`.** A price = (input, output, cache read, cache write, source, date). Sources in order: the
  Settings (`prices` in `settings.json`), the fetched list (cached in the home, with its date), the defaults
  shipped (moved out of `llm.PRICES` into a dated data file). `price_of(model)` returns the price and its origin.
- **T2.2 Fetching.** `vault-watch prices update` and a button in the Settings read LiteLLM's public list, keep
  the entries of the providers in use, and show a diff before replacing the cache. Never fetched without an
  action of the user; a list that cannot be read changes nothing.
- **T2.3 Shown everywhere.** The Settings get a "Prices" category (per model: the price, its origin, a field to
  set one, "back to default"); the Costs page and every estimate carry the origin when it is not a fetched or a
  set price ("default of 2026-11"); a model without a price is flagged as today.
- **T2.4 The journal.** Each line records the price used and its origin; `costs.py` never recomputes a past cost.
  The cache-read price of Sonnet 5.5 fixed on 2026-11-17 is noted in the changelog, the past lines left as they are.

**Capabilities**

- **T2.5 What an engine can do.** `Capabilities` on each engine: context window (from the Models API when there
  is one), structured output (native, by instruction), web (search and fetch: native, none), effort levels,
  caching, billing (per token, subscription). `Claude` and `ClaudeCode` declare theirs; the checks of
  `list_models` (1M context only) become a consequence of them.
- **T2.6 What a step needs.** Each call site names its needs (`needs=("web", "whole_guide")`) next to its effort;
  `STEP_EFFORTS` of `web.py` disappears into that one table, read by the Settings.
- **T2.7 The context decides the strategy.** The agent counts the guide once per run (exact count when the
  engine can count tokens, else an estimate with a margin) and compares it with the window minus the reserve for
  the answer and the web. Fits: the whole guide. Does not: the cross-check and the coherence check run chapter by
  chapter with the excerpts of the other chapters the corrections touch; the run view and the report say
  "by chapter: a contradiction between two chapters can be missed". `[budget].max_context_tokens` of the manifest
  caps what the agent will put in one call whatever the model.
- **T2.8 A role per step.** The Settings assign a model and an effort to each step (triage, proposals,
  cross-check, mirror, each check), with two presets that reproduce today's two roles; a step shows a warning
  when its model lacks something it needs.

Done when: every price on screen says where it comes from; the IA on-prem guide runs unchanged; the sample guide
runs "by chapter" when the window is forced small in a test, and the report says so.

## M3. Any watch (0.5.0)

- **T3.1 The contract.** `docs/watch-format.md`: `watch.json` field by field (items, triage, urgent, notes,
  window), versioned with a `schema` number; the loader refuses a newer major and says which.
- **T3.2 `WatchSource`.** A protocol (`list()` the watches, `fetch(id)` one) with three sources: `github-issue`
  (today's code, moved out of `inputs.py` and `web.py`), `file` (a folder of `watch.json`), `feeds` (T3.3). The
  manifest chooses; the list of watches of the interface comes from the source.
- **T3.3 Collection by the agent.** `vault-watch collect`: from a `feeds.json` (GitHub releases, GitHub security
  advisories, RSS and Atom), the items of a window, the notes cached, the routine releases dropped by rule. A port
  of what `watch-feeds.mjs` of the IA on-prem guide does, tested against its output on the same feeds.
- **T3.4 Collection in CI.** A reusable GitHub workflow in this repository that runs T3.3 weekly and opens the
  issue with the artifact: a guide adds a `feeds.json` and a ten-line workflow. The IA on-prem guide keeps its
  own collector as long as it wants; both give the same format.
- **T3.5 The forge.** `gh` calls gathered behind `Forge` (issues, artifacts, pull requests, their state). Only
  GitHub is implemented; the port is what a Gitea or GitLab contribution fills.

Done when: the sample guide gets a watch from `collect` and from the workflow; the IA on-prem guide runs on
either collector with the same items kept.

## M4. Any model (0.6.0)

- **T4.1 The engine protocol, written down.** `Engine`: `parse(...)`, `capabilities`, `models()`, `count_tokens`
  (optional). A registry (`engines = {"api": …, "claude-code": …}`) fed by entry points, so an engine can live in
  its own package. The Settings list the engines installed.
- **T4.2 Contract tests.** `tests/engine_contract.py`: what any engine must do, run against recorded answers
  (structured output valid and invalid, a refusal, a truncated answer, a web call, the usage and the cost
  reported). The two existing engines pass it first.
- **T4.3 Web tools.** `WebTools`: `search(query)` and `fetch(url)` returning plain text with its source, with a
  size cap and the redirections followed by the code, not the model. Implementations: SearXNG, and a plain HTTP
  fetch with extraction of the readable text. A tool loop in the engine base class runs them for the engines
  whose model has no web of its own, with the same limits as today (20 searches, 30 pages).
- **T4.4 The OpenAI-compatible engine.** Base URL, key by reference, models from `GET /v1/models`, structured
  output by `response_format` with a JSON schema (by instruction and a tolerant reading when the server has
  none), tools by function calling, the context window from the Settings when the server does not say it.
- **T4.5 Scores.** `vault-watch eval` on the published watches for: the baseline, one hosted model, one local
  model, each whole-guide and by chapter where it applies; the table in the README, the method next to it. An
  engine or a model is listed as "supported" only with a line in that table.
- **T4.6 Docs.** "Write an engine" (the protocol, the capabilities, the contract tests, a 100-line example);
  "Choose a model" (what each step needs, what by-chapter loses, the scores).

Done when: the sample guide and the IA on-prem guide run end to end on the OpenAI-compatible engine with a
hosted model; the triage, the proposals and the mirror run on a local model; the scores are published.

## M5. Stable (1.0.0)

- **T5.1 A second real guide.** The manifest tried on a guide that is not the IA on-prem one nor the sample;
  what it needed that the format did not have goes into the format before it is frozen.
- **T5.2 Freeze.** Manifest schema 1, `watch.json` schema 1, engine protocol 1: a change after that is a new
  schema number with a migration. The settings file gets its own number and its migrations.
- **T5.3 What a newcomer reads.** README rewritten around "your guide, your model" (the IA on-prem guide becomes
  the reference example); the architecture page current; a security page (keys as references, local server,
  what the model reads from the web is data, quotes checked by the code).
- **T5.4 Release.** Tag, release notes from the changelog, the package installable with `pipx`.

Done when: someone who is not the author connects a guide by following the docs alone.

## Order, and what can move

M0 → M1 are strictly first. After M1, the price half of M2 (T2.1 to T2.4) can ship at any time. M3 and M4 do not
depend on each other; M4 needs the capability half of M2 (T2.5 to T2.7). If time is short, the order that keeps
the most value is M0, M1, prices, M3, then M4.

## Working rules

- Work on the `dev` branch; `main` only receives a finished milestone (fast-forward, then a tag `vX.Y.Z`).
- One task, one commit or a few, the tests in the same commit as the code they cover.
- After each milestone: the whole suite, one real run on the IA on-prem guide, the changelog, the docs of the
  milestone. No milestone leaves the IA on-prem guide behind.
- What is found on the way and is not in the task goes to the roadmap, not into the commit.
