# Roadmap

Measured on 2026-11-08 (first real run, issue #50 of the vault): 81 kept items → 8 corrections, 0.90 $;
French content 408 k tokens (exact count), English mirror 353 k; French content grew from 575 KB to 853 KB
between June and October 2026, the security page from 15.7 KB to 42.2 KB.

Phases are ordered by dependency: finish the loop, measure, then improve what the measure points at.

## Phase A — close the loop on issue #50 (done)

- [x] **A1. English mirror in the graph.** A translation node (Claude Sonnet 5.5) syncs the EN pages hunk by
  hunk before the audits; `i18n-strict` blocks the PR otherwise (it did on issue #50).
- [x] **A2. Grouped corrections.** Corrections that depend on each other (C2, a footnote, only makes sense
  with C1) are accepted or refused as one group.
- [x] **A3. One source of instructions.** Load the vault's `.agents/skills/vault-watch/brief.md` at run time
  instead of the condensed copy in `prompts.py`, which would drift.
- [x] **A4. Unlocated items become addition candidates.** An item triaged "correct" that no French page
  names (LFM3 in issue #50) is an addition lead, not a dead end.
- [x] Publish the PR of issue #50, then process issue #49 (guide PRs #51, #53, #54 merged on 2026-11-08).

## Phase B — measure before choosing

- [x] **B1. Evaluation on past watches** (done 2026-11-08 on #30 and #47, see the README; #26 has no artifact
  left). Next: score substantive changes apart from date-only edits, add the next human-reviewed watches.

- [ ] **B2. Compare models.** Replay the past watches with `vault-watch eval` on cheaper and local models, against the
  human decisions, before changing the model. Porting needs an equivalent for prompt caching, web search and
  structured output.

## Phase C — corrections

- [x] **C1. Whole French vault in context, with prompt caching** (done as the cross-check node). ≈ 2 $ to write the cache, ≈ 0.08 $ per call
  after; the model sees every page concerned, footnotes and cross-page inconsistencies. Vector RAG only
  becomes useful past the context budget. Re-run B1 to compare.
- [ ] **C2. Replace, do not pile up.** A page states the current fact; a correction replaces the old one,
  history stays in Git and in the source note. Say it in the instructions.
- [ ] **C3. Web verification when cached notes are empty** (vLLM 0.33 and Mistral Large 4 had none), with a
  web fetch tool limited to tier A domains; also re-checks the watchlist claims past their date (12 today).

## Phase D — discovery

Discovery becomes a tracker of candidates over time instead of a one-shot triage:
`lead → enriched → watching → confirmed → proposed → added`, or `dismissed` with a reason and a re-check date.

- [ ] **D1. Deterministic enrichment before any judgement.** Hugging Face: size, licence, context, GGUF
  availability, downloads. GitHub: licence, releases, contributors, README head.
- [ ] **D2. Group by entity across sources and weeks.** Normalise names (model family, tool), score =
  sources × tier × persistence. "Two independent tier B sources" becomes a computation.
- [ ] **D3. Candidate store with states and re-check dates**, replacing the flat `watch-seen.md`
  (handles "weights announced for later": Reflection Beam, Mistral Large 4).
- [ ] **D4. Relevance judged with the whole vault in context** (C1): where the addition fits and which
  decision it changes, which is the opportunity note.

## Phase E — keep the vault and the sources in shape

- [ ] **E1. Size budget per page, checked in CI** (e.g. 20 KB for a solution sheet, 35 KB for a reference
  page), warning first.
- [ ] **E2. Quarterly compaction graph.** Proposes shorter versions of sections over budget and removes
  advisories fixed more than six months ago below the version floor; human-reviewed diff as always.
- [ ] **E3. Feed coverage audit.** Every tool with a solution sheet has a release feed and an advisory feed
  (today advisories cover 9 tools out of about 25; Liquid AI, Microsoft, AllenAI, Aleph Alpha are not followed).
- [ ] **E4. Gap-driven discovery, quarterly.** With the whole vault in context, list what an SME on-prem AI
  guide should cover and does not. The model's knowledge only generates leads; each one goes through D1–D4.
- [x] **E6. External links of the changed pages checked before publish** (`links` node, the vault's
  `audit-sources.mjs`), listed in the publish pause and in the PR.
- [x] **E8. On-demand health check** (`verify.py`, « Vérifier le guide » page): free checks (audits, dead links, freshness) and paid ones (whole-guide consistency, translation fidelity, re-check of dated claims, replacement of dead links), each with its estimate; findings go to a fix run (translation findings to a cheaper translation run: Sonnet, the two pages only, no cross-check).
- [ ] **E7. Dead links fixed by a fix run.** The weekly source audit (warn-only today) feeds `vault-watch fix`:
  find the moved page or an equivalent primary source on the web; tell a real 404 from an anti-bot 403 with the
  API's web fetch. First case: the OpenHuman architecture README (404).
- [ ] **E5. Yield per source.** From past reports, leads per accepted addition; drop the feeds that never pay.

## Phase F — publication and interface

- [ ] Tools exposed through MCP (LangChain MCP adapters), so the same graph can be driven from Claude Code.
- [ ] **OpenAI-compatible engine** (OpenAI, Mistral, a local model behind vLLM, llama.cpp or Ollama): a third class
  with the same `parse`, structured output by `response_format`, models listed by `GET /v1/models`, the key as a
  reference like the others. Two limits to solve before it can run every step: the web (the cross-check and the
  checks need a search and a page reader: the provider's own web tool where it has one, else tools the agent runs
  itself, a search API such as SearXNG, Brave or Tavily plus a fetch of the page) and the context (the
  cross-check holds the whole guide, about 430 k tokens: few models take it, almost no local one; it would need
  excerpts instead, as the proposals already use). The triage, the proposals and the English mirror need neither.
- [ ] **Another guide than this one.** The agent is written for the IA on-prem guide: its path (`VAULT_PATH`) can
  change, but the GitHub repository and the site are fixed in the code, and it relies on what the guide provides:
  the watch issues (label `veille`) and their `weekly-watch` artifact, the brief `.agents/skills/vault-watch/brief.md`
  and the translation policy, `scripts/run-audits.mjs`, the version floors, the freshness watchlist, French pages
  mirrored in English under `en/`. Making it a setting (a guide = a path, a repository, a site) is short; another
  guide would also have to provide that contract, or the agent would have to make each part optional.
- [x] README with the measures of B1 and C1, MIT licence.
- [x] Public GitHub repository (source on Gitea, pushed to GitHub by a Gitea push mirror).
- [x] Web interface: `vault-watch serve` (FastAPI, server-sent events), one screen per pause of the graph.
- [x] Leads with their passage: a finding of a check of the guide or of the cross-check shows the sentence it is
  about, with its line number and the nearest lines, in the interface, the report and the fix run's pull request.
  The model quotes it, the code finds it in the page (exact, else the closest passage, flagged; else « not
  found »), so a quote the model got wrong is never shown as the guide's text.
- [ ] Blog article.
- [x] Claude Code as a model engine (2026-11-17): `claude -p` on a Claude subscription, nothing billed, chosen by
  default when a subscription is found; Settings page (engine, models, the API key as a reference only); header
  buttons after dl-sub-dub (size of the text, light or dark, palettes, browser notifications); icon.

## Phase G — a modular agent

Running on any guide, with any model that can do the work, with prices that say where they come from. It covers the
two items of phase F above (an OpenAI-compatible engine, another guide than this one).

The why and the design are in [docs/modular-plan.md](docs/modular-plan.md). Below is the work, in the order to do it:
six milestones, each one a version that leaves the IA on-prem guide working as it does today.

How to read it: a task is done when its test exists and passes; a milestone is done when its "Done when" list is
true, the version is tagged, and `main` receives it (work happens on the `dev` branch, see
[Working rules](#working-rules-of-phase-g)).

| Milestone | Version | What someone else can do after it |
| :-- | :-- | :-- |
| M0. Ground | 0.2.0 | Clone, run the tests, try the agent on a sample guide |
| M1. Any guide | 0.3.0 | Point the agent at their own guide with a manifest |
| M2. Prices and capabilities | 0.4.0 | Trust the costs shown; see which steps a model can run |
| M3. Any watch | 0.5.0 | Get a watch without writing a collector |
| M4. Any model | 0.6.0 | Run the steps on an OpenAI-compatible model, local ones included |
| M5. Stable | 1.0.0 | Rely on the manifest and the engine protocol not changing under them |

### Decisions to take first

Each has a default, taken if nothing else is said.

| Decision | Default | Needed by |
| :-- | :-- | :-- |
| Format and place of the manifest | `vault-watch.toml` at the root of the guide (`tomllib` is in Python 3.11, no dependency) | M1 |
| Name of the thing watched, in code and docs | "guide" everywhere; `VAULT_PATH` kept as an alias of `--guide` | M1 |
| Second real guide to try the manifest on | To find: without one, the format stays "experimental" in 1.0 | M5 |
| Search API of the web tools | SearXNG first (self-hosted, no key), the port open to others | M4 |
| Public price list | LiteLLM's JSON, fetched on demand, never at start | M2 |
| First model of the OpenAI-compatible engine to publish scores for | One hosted (to choose) and one local on the homelab | M4 |

### M0. Ground (0.2.0, done 2026-11-17)

Nothing visible changes; everything after depends on it.

- **T0.1 Baseline.** Run the suite and keep its count; copy the published `eval` scores of `metrics/eval/` in a
  table of the changelog: the figures every later milestone is compared with. Run watch #77 for real on the Claude
  Code engine once (first full run on the subscription, open since 2026-11-17) and note the usage it took.
  Done 17/11, on the API engine instead: 11 corrections, all applied, $3.44,
  merged as #78. The first full run on Claude Code is still to do; it moves to M2, where the costs of both engines
  are compared.
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

### M1. Any guide (0.3.0)

- **T1.1 `guide.py`: the manifest.** Read `vault-watch.toml` with `tomllib`, validate it (unknown key: an error
  that names it; missing optional part: `None`), return a frozen `Guide` (name, repository, site, base branch,
  content language, include and exclude globs, mirrors, modified field, watch, rules, checks, budget, schema
  version). Tests: defaults, each refusal, the IA on-prem manifest, the sample one.
  Done 2026-11-17 (`guide.py`, `examples/manifests/ia-on-prem-vault.toml`): the IA on-prem manifest finds the
  same 129 pages as the agent did without it.
- **T1.2 The guide through the code.** `Deps` carries the `Guide` instead of a path. Replace, one module per
  commit: `vault.french_pages` and its skipped folders by the globs (`vault.pages`); `last_modified` by the
  manifest's field (no bump when absent); `en/` by the mirrors (`graph.mirror`, `verify`, `evaluate`); the
  repository and the site in `graph.py` and `web.py`; `prompts.py` by the manifest's rules. Test: no string of
  the IA on-prem guide left in `src/` (a test greps for it).
  Done 2026-11-18, one module per commit: pages, mirrors and the modified date (`vault.guide_of`), prompts and
  mirrors, the checks of `[checks]`, repository and site, the remaining prompts, translation and evaluation. `Deps`
  keeps a path and reads the guide from it (`vault.guide_of`, cached, read again when the manifest changes): the
  worktree of a run and the reading copy carry their own manifest. Left for T1.5: the default folder in `cli.py`.
- **T1.3 Optional parts.** A step whose part is missing is skipped and says so in the run view and the report:
  no `[checks].audits` → no audit step and "not checked" in the publish screen; no mirror → no translation; no
  floors → no floor alignment; no `claims_due` → none listed. The interface shows what the guide provides
  (a "Guide" category in the Settings: read-only, from the manifest).
  Done 2026-11-18: the « Guide » category (checked in a page on the sample guide); « not checked » on the publish
  screen and in the pull request for audits and the source audit.
- **T1.4 Default rules.** A brief and a translation policy shipped with the agent (`src/…/defaults/`), written
  from the IA on-prem ones without what is specific to it; the prompts no longer assume French (the language of
  the manifest is named in them).
  Done 2026-11-18 (`defaults/brief.md`, `defaults/translation-policy.md`; the prompts name the guide's language
  since T1.2).
- **T1.5 Several guides.** `--guide <path>` on every command; the home of a guide is `.vault-watch/` under the
  agent's home, one folder per guide (the name of its repository); the web interface serves one guide per
  process, its name in the header. `VAULT_PATH` and the current `.vault-watch/` keep working (moved once, with a
  message).
  Done 2026-11-18, with one change: nothing is moved. The runs of before stay in `.vault-watch/` for the guide they
  belong to (`guide.json`), because their worktrees are registered in the guide's repository with their path.
- **T1.6 `vault-watch init`.** Looks at a repository (remote, default branch, folders, front matter, scripts) and
  writes a manifest with what it found and comments for what it did not; `vault-watch doctor` lists, step by
  step, what will run and what will be skipped, and what is missing on the machine (`gh`, `node`, `claude`).
  Done 2026-11-18 (`onboard.py`). Run on the IA on-prem guide, `init` finds its 129 pages, `en/`, `last_modified`
  and its repository; its watch, rules and checks are left for the editor to fill (T1.7 does it for that guide).
- **T1.7 The manifest of the IA on-prem guide.** A pull request of the guide adding `vault-watch.toml`; in the
  same one, the lines of its `CLAUDE.md` and of the `vault-watch` skill that still say a run is billed.
  Done 2026-11-18: [pull request #81 of the guide](https://github.com/DamienBecherini/ia-on-prem-vault/pull/81),
  the manifest of `examples/manifests/`, which gives the same pages, mirror, watch, rules and checks as the
  built-in layout; the lines now say what a run costs with each engine.
- **T1.8 Docs.** "Connect your guide": the manifest key by key, what each optional part unlocks, the sample
  guide as the worked example.
  Done 2026-11-18: `docs/connect-your-guide.md` and its French version (the commands of the sample guide tested as
  written), linked from the READMEs; `docs/presentation*.md` brought up to date (twelve pull requests, the cost
  journal of 17 November, the Claude Code engine, phase G) without repeating the README.

Done when: the IA on-prem guide runs a real watch with its manifest and gives the same corrections as the
baseline run within the usual variation; the sample guide runs end to end; `init` on a repository it never saw
gives a manifest `doctor` accepts.
Done 2026-11-18. Watch #77 replayed on the guide as it was before its pull request, with its manifest: recall 1.0
(the 11 corrections of PR #78 found), one valid extra, none wrong, 3.36 $ (`metrics/eval/issue77-full-m1.json`).
The sample guide ran end to end on the Claude Code engine (7 corrections, the two planted errors to fix found, the
other two noticed by the cross-check, nothing billed); it showed that publishing a guide without repository still
pushed, fixed. `init` on the IA on-prem guide gives its 129 pages, and on a new folder a manifest `doctor` accepts
(tests).

### M2. Prices and capabilities (0.4.0)

Two independent halves; the first is small and can ship alone.

**Prices**

- **T2.1 `prices.py`.** A price = (input, output, cache read, cache write, source, date). Sources in order: the
  Settings (`prices` in `settings.json`), the fetched list (cached in the home, with its date), the defaults
  shipped (moved out of `llm.PRICES` into a dated data file). `price_of(model)` returns the price and its origin.
  Done 2026-11-18 (`prices.py`, `defaults/prices.json`; `Prices.of(model)` gives a `Price` with `origin` and `label`).
- **T2.2 Fetching.** `vault-watch prices update` and a button in the Settings read LiteLLM's public list, keep
  the entries of the providers in use, and show a diff before replacing the cache. Never fetched without an
  action of the user; a list that cannot be read changes nothing.
  Done 2026-11-18 for the command line (`vault-watch prices update`); the button comes with T2.3. The first read
  of the real list differs from the defaults on one price: Fable 5.1 cache reads, 0.25 against 1.0 (to check on
  Anthropic's page before changing the defaults).
- **T2.3 Shown everywhere.** The Settings get a "Prices" category (per model: the price, its origin, a field to
  set one, "back to default"); the Costs page and every estimate carry the origin when it is not a fetched or a
  set price ("default of 2026-11"); a model without a price is flagged as today.
  Done 2026-11-18 (with the « Read the list » button of T2.2), checked in the browser: a price set, back to the
  default, the list read and its changes shown without being applied.
- **T2.4 The journal.** Each line records the price used and its origin; `costs.py` never recomputes a past cost.
  The cache-read price of Sonnet 5.5 fixed on 2026-11-17 is noted in the changelog, the past lines left as they are.
  Done 2026-11-18 with T2.1 (`price`, `price_origin` on each API line).

**Capabilities**

- **T2.5 What an engine can do.** `Capabilities` on each engine: context window (from the Models API when there
  is one), structured output (native, by instruction), web (search and fetch: native, none), effort levels,
  caching, billing (per token, subscription). `Claude` and `ClaudeCode` declare theirs; the checks of
  `list_models` (1M context only) become a consequence of them.
  Done 2026-11-18 (`llm.Capabilities`, `context_of`: the Models API's window when it was read, 1M for a model the
  agent knows, 200k for one it does not). `list_models` keeps every current model; T2.7 decides what a smaller
  window changes.
- **T2.6 What a step needs.** Each call site names its needs (`needs=("web", "whole_guide")`) next to its effort;
  `STEP_EFFORTS` of `web.py` disappears into that one table, read by the Settings.
  Done 2026-11-18 (`steps.py`: role, effort, needs per step; `steps.lacks` says what an engine lacks for a step).
- **T2.7 The context decides the strategy.** The agent counts the guide once per run (exact count when the
  engine can count tokens, else an estimate with a margin) and compares it with the window minus the reserve for
  the answer and the web. Fits: the whole guide. Does not: the cross-check and the coherence check run chapter by
  chapter with the excerpts of the other chapters the corrections touch; the run view and the report say
  "by chapter: a contradiction between two chapters can be missed". `[budget].max_context_tokens` of the manifest
  caps what the agent will put in one call whatever the model.
  Done 2026-11-18 (`reading.py`); the sample guide runs by chapter with a window forced small in a test, and its
  report says so.
- **T2.8 A role per step.** The Settings assign a model and an effort to each step (triage, proposals,
  cross-check, mirror, each check), with two presets that reproduce today's two roles; a step shows a warning
  when its model lacks something it needs.
  Moved out of 0.4.0 (decided 2026-11-18): the two roles serve the guides of today, and the criteria of M2 hold
  without it. `steps.py` (T2.6) already gives each step its role, effort and needs; this task builds on it later.

Done when: every price on screen says where it comes from; the IA on-prem guide runs unchanged; the sample guide
runs "by chapter" when the window is forced small in a test, and the report says so.

### M3. Any watch (0.5.0)

- **T3.1 The contract.** `docs/watch-format.md`: `watch.json` field by field (items, triage, urgent, notes,
  window), versioned with a `schema` number; the loader refuses a newer major and says which.
  Done 2026-11-18 (`inputs.check_watch`; the six watches of the IA on-prem guide since 10 October pass it). `url`
  and `date` are expected, not required: a watch written by hand may lack them.
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
  Done 2026-11-18 (`forge.py`: `Forge`, `GitHub`, `get`, `use`); no call to `gh` is left outside it.

Done when: the sample guide gets a watch from `collect` and from the workflow; the IA on-prem guide runs on
either collector with the same items kept.

### M4. Any model (0.6.0)

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

### M5. Stable (1.0.0)

- **T5.1 A second real guide.** The manifest tried on a guide that is not the IA on-prem one nor the sample;
  what it needed that the format did not have goes into the format before it is frozen.
- **T5.2 Freeze.** Manifest schema 1, `watch.json` schema 1, engine protocol 1: a change after that is a new
  schema number with a migration. The settings file gets its own number and its migrations.
- **T5.3 What a newcomer reads.** README rewritten around "your guide, your model" (the IA on-prem guide becomes
  the reference example); the architecture page current; a security page (keys as references, local server,
  what the model reads from the web is data, quotes checked by the code).
- **T5.4 Release.** Tag, release notes from the changelog, the package installable with `pipx`.

Done when: someone who is not the author connects a guide by following the docs alone.

### Order, and what can move

M0 → M1 are strictly first. After M1, the price half of M2 (T2.1 to T2.4) can ship at any time. M3 and M4 do not
depend on each other; M4 needs the capability half of M2 (T2.5 to T2.7). If time is short, the order that keeps
the most value is M0, M1, prices, M3, then M4.

### Working rules of phase G

- Work on the `dev` branch; `main` only receives a finished milestone (fast-forward, then a tag `vX.Y.Z`).
- One task, one commit or a few, the tests in the same commit as the code they cover.
- After each milestone: the whole suite, one real run on the IA on-prem guide, the changelog, the docs of the
  milestone. No milestone leaves the IA on-prem guide behind.
- What is found on the way and is not in the task goes to the roadmap, not into the commit.

## Known issues and checks to do

Left open when the Claude Code engine, the Settings and the header buttons came in (2026-11-17).

- [ ] **First real run on the subscription.** No full run has used the Claude Code engine yet. Watch #77 of the
  guide (urgent, one advisory) is a small first one: look at `/usage` in Claude Code after the cross-check, which
  reads the whole guide (about 430 k tokens) on Opus, against the limits of a Pro plan.
- [ ] **Web reading of Claude Code is less exact than the API's.** Its WebFetch has a small model (Haiku) read the
  page and report on it, where the API hands the page itself to the model: checking an exact version or date can
  be less sure. Compare with `vault-watch eval` (same past watches, both engines) before trusting the cross-check
  on the subscription.
- [x] **Effort per role** (2026-11-17): lower, normal or higher in the Settings moves every step of the role one
  level (the effort of each step stays set in the code); the cost estimates still assume the normal effort.
- [x] **Models read from the API** (2026-11-17): the Settings list the Claude models the key can use (Models API),
  those with a 1M-token context only; without a key that answers, the models the agent knows. A model without a
  price in `llm.PRICES` is counted at 0 $ and the page says so.
- [ ] **The guide's instructions still say a run is billed.** `CLAUDE.md` and the `vault-watch` skill of the guide
  ask before launching a run because it costs money; with the Claude Code engine it no longer does. Change them
  through a pull request of the guide (its `main` is protected).
- [ ] **Not checked yet in the interface:** the header and the Settings on a narrow window (phone); the browser
  notifications with the real permission of a browser (checked with a fake `Notification` only).
- [ ] **Running servers after an update.** A `vault-watch serve` started before an update keeps its old Python
  code: start it again. The page now names its files with a version (`?v=`), so a browser no longer mixes an old
  cached script with a new page, but a copy cached before that change needs one forced reload (Ctrl+Shift+R).
- [x] **Publication** (2026-11-17). `main` is what is published: every push to it reaches the public GitHub
  repository at once. Work happens on a `dev` branch kept in a separate, private repository, and `main` receives
  finished versions only.
