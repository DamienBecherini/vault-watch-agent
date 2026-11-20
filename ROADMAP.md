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
- [x] **C2. Replace, do not pile up** (2026-11-19, `prompts.REPLACE` in the proposals and the fix runs). A page states the current fact; a correction replaces the old one,
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

- [x] **E1. Size per page** (2026-11-20, `sizes.py`, M6): a page is flagged when it grew much against itself in
  90 days (`[budget] growth_kb`, `growth_percent`), with its size now and what it gained; a ceiling is optional
  (`[budget] page_kb`, `[budget.pages]`), none by default: the first design had 30 KB for every page, which the
  user found arbitrary (how long a page should be depends on its subject). A warning of `doctor`, of
  `vault-watch compact` and of the « Size of the pages » check, never a failure, not checked in CI.
- [x] **E2. Compaction** (2026-11-20, `compact.py`, M6): a check lists what is repeated, piled-up history or longer
  than it needs; the findings kept go to a compaction run, reviewed like corrections. On demand rather than on a
  timer: the size check says when.
- [x] **E3. Feed coverage audit** (2026-11-19, in « Check the sources »). Every tool with a solution sheet has a release feed and an advisory feed
  (today advisories cover 9 tools out of about 25; Liquid AI, Microsoft, AllenAI, Aleph Alpha are not followed).
- [ ] **E4. Gap-driven discovery, quarterly.** With the whole vault in context, list what an SME on-prem AI
  guide should cover and does not. The model's knowledge only generates leads; each one goes through D1–D4.
- [x] **E6. External links of the changed pages checked before publish** (`links` node, the vault's
  `audit-sources.mjs`), listed in the publish pause and in the PR.
- [x] **E8. On-demand health check** (`verify.py`, « Vérifier le guide » page): free checks (audits, dead links, freshness) and paid ones (whole-guide consistency, translation fidelity, re-check of dated claims, replacement of dead links), each with its estimate; findings go to a fix run (translation findings to a cheaper translation run: Sonnet, the two pages only, no cross-check).
- [ ] **E7. Dead links fixed by a fix run.** The weekly source audit (warn-only today) feeds `vault-watch fix`:
  find the moved page or an equivalent primary source on the web; tell a real 404 from an anti-bot 403 with the
  API's web fetch. First case: the OpenHuman architecture README (404).
- [x] **E5. Yield per source** (2026-11-19: the « Sources » page, `sources.py`). From the watches and the runs
  kept on the machine, per feed: collected, kept by the rules, judged and kept by the model, corrections proposed
  and accepted, and a verdict by rule. Dropping a feed stays the editor's decision.
  Next, asked for on 2026-11-19 (the maintainer): question the sources over time from the interface.
  - [x] **« Check the sources »** (2026-11-19, `sourcecheck.py`): each source asked (there, archived, renamed,
    last publication), the guide read again (cited and not followed, followed and no longer named, releases
    without advisories, E3), proposals to remove, change or add, the ticked ones in one pull request on
    `feeds.json`. A source quiet for 180 days is said, never proposed for removal.
  - [x] **A « watched page » feed type** (2026-11-19, `type: "page"` in `collect.py`, state in the watch's `pages`): a page whose change is an event (a price list the guide cites). The
    Lambda prices of 16 November 2026 were not seen by any feed; the maintainer reported them by hand.
  - [x] **« Look for what is new »** (2026-11-20, `news.py`, on dev for 1.3.0; [docs/news.md](docs/news.md)): a check
    reads the whole guide and what past watches set aside, and lists what a reader would expect and does not find
    (leads: nothing verified); the leads kept go to an addition run, which checks each one on the web and writes it
    where it belongs. A second check finds leads from the web, one call per chapter, and a lead can be dug deeper in a
    call of its own (asked for on 2026-11-20). This is E4 in its first form. Still to do: the first real run on the IA on-prem guide
    (billed) to set the estimates; a new page written by the run (today it says one is needed); D1 to D4 below
    (enrichment without a model, candidates grouped and kept over time).

## Phase F — publication and interface

- [ ] Tools exposed through MCP (LangChain MCP adapters), so the same graph can be driven from Claude Code.
- [x] **OpenAI-compatible engine** (OpenAI, Mistral, a local model behind vLLM, llama.cpp or Ollama): a third class
  with the same `parse`, structured output by `response_format`, models listed by `GET /v1/models`, the key as a
  reference like the others. Two limits to solve before it can run every step: the web (the cross-check and the
  checks need a search and a page reader: the provider's own web tool where it has one, else tools the agent runs
  itself, a search API such as SearXNG, Brave or Tavily plus a fetch of the page) and the context (the
  cross-check holds the whole guide, about 430 k tokens: few models take it, almost no local one; it would need
  excerpts instead, as the proposals already use). The triage, the proposals and the English mirror need neither.
- [x] **Another guide than this one.** The agent is written for the IA on-prem guide: its path (`VAULT_PATH`) can
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
| M6. Compaction | 1.2.0 | Keep a guide from growing heavy: redundancies, piled-up history and long sections found and trimmed, reviewed like corrections |

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
  Done 2026-11-20 (dev, for 1.2.0), asked for with the compaction (Fable on its two steps, the watches on Opus):
  the two roles stay, and a step can be set apart from its role with its own model and effort (`steps` in the
  settings, `llm.Routed`). Not done: the warning when the model of a step lacks something it needs (the engine is
  the same for every step, so today's warnings per role still hold).

Done when: every price on screen says where it comes from; the IA on-prem guide runs unchanged; the sample guide
runs "by chapter" when the window is forced small in a test, and the report says so.

### M3. Any watch (0.5.0, done 2026-11-18)

- **T3.1 The contract.** `docs/watch-format.md`: `watch.json` field by field (items, triage, urgent, notes,
  window), versioned with a `schema` number; the loader refuses a newer major and says which.
  Done 2026-11-18 (`inputs.check_watch`; the six watches of the IA on-prem guide since 10 October pass it). `url`
  and `date` are expected, not required: a watch written by hand may lack them.
- **T3.2 `WatchSource`.** A protocol (`list()` the watches, `fetch(id)` one) with three sources: `github-issue`
  (today's code, moved out of `inputs.py` and `web.py`), `file` (a folder of `watch.json`), `feeds` (T3.3). The
  manifest chooses; the list of watches of the interface comes from the source.
  Done 2026-11-18 for `github-issue`, `file` (a file or a folder) and `none` (`watches.py`); `feeds` with T3.3
  (`watches.Collected`: the watches collected in the guide's working folder, and a « Collect a watch » button).
- **T3.3 Collection by the agent.** `vault-watch collect`: from a `feeds.json` (GitHub releases, GitHub security
  advisories, RSS and Atom), the items of a window, the notes cached, the routine releases dropped by rule. A port
  of what `watch-feeds.mjs` of the IA on-prem guide does, tested against its output on the same feeds.
  Done 2026-11-18 (`collect.py`, `docs/collect.md`), with every feed type of the IA on-prem guide (also tags,
  YouTube, Hugging Face and the two discovery types). On its 63 feeds, run back to back with the JS collector:
  the same 172 items and 105 kept since 3 November, the same 455 and 241 since 1 June, with the same reasons, notes
  and floors; the only differences were star counts that moved between the two runs. Text is cut in UTF-16 units,
  as JavaScript does, so that both give the same notes.
- **T3.4 Collection in CI.** A reusable GitHub workflow in this repository that runs T3.3 weekly and opens the
  issue with the artifact: a guide adds a `feeds.json` and a ten-line workflow. The IA on-prem guide keeps its
  own collector as long as it wants; both give the same format.
  Written 2026-11-18 (`.github/workflows/collect.yml`, and `sample-watch.yml` that runs it on the sample guide);
  its collect step checked locally and from a clean install of the package. Its first run on GitHub comes with the
  publication of 0.5.0 (the workflow installs the agent from its tag).
- **T3.5 The forge.** `gh` calls gathered behind `Forge` (issues, artifacts, pull requests, their state). Only
  GitHub is implemented; the port is what a Gitea or GitLab contribution fills.
  Done 2026-11-18 (`forge.py`: `Forge`, `GitHub`, `get`, `use`); no call to `gh` is left outside it.

Done when: the sample guide gets a watch from `collect` and from the workflow; the IA on-prem guide runs on
either collector with the same items kept.
Done 2026-11-18. The sample guide gets its watch from `collect` and, once 0.5.0 was published, from the workflow on
GitHub (`sample-watch.yml`, 18 s: 12 items, 11 kept, no feed in error, read by the agent). The IA on-prem guide gives
the same items with either collector; its manifest names its feeds since
[pull request #84 of the guide](https://github.com/DamienBecherini/ia-on-prem-vault/pull/84).

### M4. Any model (0.6.0, done 2026-11-18)

- **T4.1 The engine protocol, written down.** `Engine`: `parse(...)`, `capabilities`, `models()`, `count_tokens`
  (optional). A registry (`engines = {"api": …, "claude-code": …}`) fed by entry points, so an engine can live in
  its own package. The Settings list the engines installed.
  Done 2026-11-18 (`llm.Engine`, `llm.EngineKind`, `llm.engines()`; each engine's options checked by its own `check`).
- **T4.2 Contract tests.** `tests/engine_contract.py`: what any engine must do, run against recorded answers
  (structured output valid and invalid, a refusal, a truncated answer, a web call, the usage and the cost
  reported). The two existing engines pass it first.
  Done 2026-11-18 (`tests/engine_contract.py`, `tests/test_engine_contract.py`): the three engines pass it.
- **T4.3 Web tools.** `WebTools`: `search(query)` and `fetch(url)` returning plain text with its source, with a
  size cap and the redirections followed by the code, not the model. Implementations: SearXNG, and a plain HTTP
  fetch with extraction of the readable text. A tool loop in the engine base class runs them for the engines
  whose model has no web of its own, with the same limits as today (20 searches, 30 pages).
  Done 2026-11-18 (`webtools.py`), the loop in the OpenAI-compatible engine (the only one without web); public
  addresses only. Tried on 18/11/2026 against the SearXNG of the homelab (CT 107, `http://192.168.1.200:8888`,
  deployed the same day): 40 results from Brave and Google CSE (DuckDuckGo answers a CAPTCHA); reading a GitHub
  release page showed the empty items its icons leave, now dropped.
- **T4.4 The OpenAI-compatible engine.** Base URL, key by reference, models from `GET /v1/models`, structured
  output by `response_format` with a JSON schema (by instruction and a tolerant reading when the server has
  none), tools by function calling, the context window from the Settings when the server does not say it.
  output by `response_format` with a JSON schema (by instruction and a tolerant reading when the server has
  none), tools by function calling, the context window from the Settings when the server does not say it.
  Written 2026-11-18 (`openai_compat.py`, its Settings checked in the browser against a fake server). First real
  run the same day, the sample guide on Qwen3.6-35B-A3B (llama.cpp on the RTX 5070 of the PC, 64k window, key by
  sops reference): every model step answered in the schema, 1 min 19 s, nothing billed. It showed that the fixed
  reserve of 100k left a 64k window a negative budget (the guide read by chapter): the reserve is now a third of a
  window under 300k. Read whole, the cross-check found the port contradiction between two chapters.
  Hosted, the same day: the sample guide on Claude Haiku 5.5 through Anthropic's OpenAI-compatible layer (the API
  key by sops reference; the layer refuses non-strict schemas, so the schema went into the instructions), search by
  the homelab's SearXNG. 30 s, 0.006 $: the triage, the proposals and the cross-check answered; the cross-check
  searched three times and read the advisory's address (a 404: the guide is made up) and rejected the correction
  for lack of a source. Haiku missed the stale Python version the Claude Code run had found: a matter for T4.5.
  The run showed that the agent's own searches were priced as the Claude API's web search; they are not billed now.
- **T4.5 Scores.** `vault-watch eval` on the published watches for: the baseline, one hosted model, one local
  model, each whole-guide and by chapter where it applies; the table in the README, the method next to it. An
  engine or a model is listed as "supported" only with a line in that table.
  Replaced on 2026-11-18 by an honest statement (decision of the maintainer): no score table. Opus scored by an
  Opus judge against a PR that was itself an Opus run says little; a local model good enough for the proposals needs
  a 32 GB card the project does not have. The docs name the models the IA guide uses, what was tried, and how to
  measure one's own model with the limits of `eval`; nothing is promised for other models.
  2026-11-18: the judge is now a Claude model whatever model ran the watch (`--judge`). Reference by excerpts
  (`keyword`, no cross-check) on Claude Code, Opus 5.5, watch #77: 3 of 9 hunks, 3 proposals all right, 70 s, nothing
  billed (`metrics/eval/issue77-keyword-m4ref.json`). Of the 11 corrections of the whole-guide run (M1), 4 came from
  the proposals, 7 from the cross-check and 1 from the sweep: on this watch the recall is in the cross-check, the
  long part on a local model. The local replay starts with `keyword` (the proposals, a few minutes of GPU).
  Local, the same day: Qwen3.6-35B-A3B (llama.cpp, 64k window, RTX 5070 laptop), same watch, same Claude judge:
  0 proposals, 0 of 9 hunks, 5 min (GPU held 6 min). The triage kept the LiteLLM advisory (4 groups against 5);
  the proposal step saw that the guide's floor 1.106.5 was below the advisory's 1.106.9, then declined the change as
  "beyond the scope of the sentence" (`metrics/eval/issue77-keyword-m4qwen.json`). A judgement miss, not a format
  one: every answer fit the schema.
- **T4.6 Docs.** "Write an engine" (the protocol, the capabilities, the contract tests, a 100-line example);
  "Choose a model" (what each step needs, what by-chapter loses, the scores).
  "Write an engine" done 2026-11-18 (`docs/write-an-engine.md` and in French; the example, an engine for Ollama's own
  API in `examples/engines/`, passes the contract tests); "Choose a model" done the same day
  (`docs/choose-a-model.md` and in French): the models of the IA guide, what each step asks, what was tried, `eval`
  and its limits.

Done when: the sample guide and the IA on-prem guide run end to end on the OpenAI-compatible engine with a
hosted model; the triage, the proposals and the mirror run on a local model; the scores are published.
Revised on 2026-11-18: the engine runs on a hosted model (the sample guide) and on a local one (the sample guide,
watch #77 by excerpts); the docs say which models the project uses and commit to nothing else.
Done 2026-11-18, published as 0.6.0.

### M5. Stable (1.0.0, done 2026-11-19)

- **T5.1 A second real guide.** The manifest tried on a guide that is not the IA on-prem one nor the sample;
  what it needed that the format did not have goes into the format before it is frozen.
  Started 2026-11-19 on a private guide of the maintainer (French only, on a self-hosted Gitea, most of its pages
  first-hand accounts dated by when they were given): `vault-watch.toml`, `[rules] brief`, 7 feeds (releases and
  advisories of Claude Code, OpenCode, Obsidian, n8n, NocoDB). `doctor` accepts it (131 pages); `collect` kept 10
  items of 29, two n8n advisories rated high. No run yet. What the format lacked:
  - **Pages the agent reads but must not edit.** Most pages are generated by the guide's own scripts (a
    correction there is lost at the next rebuild), and the first-hand accounts report what people said at a date
    (never corrected). The brief can say so, the format cannot: `exclude` also removes a page from the reading.
    Wanted: `[content] readonly = [globs]`, or the front matter `generated: true` honoured.
  - **A page that collects the changes.** The brief sends every change to one hand-written page (« what changed
    since ») whose placeholder sentence the first correction replaces: a correction needs text to
    replace. Wanted: a declared target where the agent appends a dated line.
  - **A forge other than GitHub.** The guide lives on a private Gitea: without `repository` it is local (no issue,
    no pull request, the branch pushed by hand). A Gitea forge would need its own `forge.py`.
  - **Moving tags and monorepos in `github-releases`.** n8n publishes `stable`, `latest`, `beta` and `v1` as
    releases; OpenCode's repository also releases a `process-daemon`. `exclude` handles both, but it matches
    « owner/repo title », which `docs/collect.md` does not say. Wanted: moving tags skipped by default, the matched
    text documented.
  - To see in a run: whether the cross-check, which reads the whole guide, keeps to the brief and leaves the
    first-hand accounts alone.
  First run the same day (API engine, Opus 5.5, 23 s, 0.09 $): the triage kept the two high n8n advisories and
  dropped the rest as the brief says; the proposal step judged them outside the uses the guide describes (a
  single person's n8n, not a multi-user instance) and left the first-hand accounts alone. It also said why it could not
  have written a line anyway: `03-outils/depuis.md` was not among the excerpts, so it had no text to replace. That
  is the second gap above, seen in a run: a target page must reach the proposal step whatever the keywords say.
  No correction, so no cross-check: the first point stays to be seen.
  The first two gaps closed the same day: `[content] readonly` and `[watch] changes_page` (`b21ae7a`); the prompts
  of the IA on-prem guide, which declares neither, are byte for byte those of 0.6.1. Second run (2.81 $): one
  dated line in the changes page, which the cross-check tightened (only an instance shared with other accounts is
  exposed), applied on the local branch and merged by hand; no edit proposed on the 127 read-only pages. The
  cross-check also noticed two real errors of the guide's generated pages (a tool attached to the wrong
  account, a chronology given as a fact), fixed in the guide's sources.
  Cost: the cross-check read the whole guide, 461 k tokens: as large as the IA on-prem guide, 55 % of it the
  first-hand account pages, and French full of wiki links tokenizes at about 2.3 characters a token. The guide now
  excludes the first-hand accounts (about 210 k tokens). A read-only page is still read by the cross-check: a guide that
  wants it read only by the proposals has to exclude it; whether `readonly` should also mean « not in the
  cross-check » is to decide before the freeze. Decided 2026-11-19 (the maintainer): no, the cross-check keeps
  its full reading, coherence first; a guide that wants a lighter run excludes pages. Moving tags: dropped at
  pre-triage since `882aa4a`, `exclude` documented.
  The forge: Gitea written before the freeze (decided 2026-11-19), so that the manifest keys are in schema 1.
  `[guide] forge = "gitea"`, `forge_url`, `forge_token` (a reference: env:, sops:, file:); `Gitea` in `forge.py`
  implements the seven methods through the REST API (httpx), the branch still pushed by git. Tested against a fake
  server, and read on the maintainer's Gitea (the repository found; the issues refused to a token without the
  `issue` scope, with that message). A Gitea token is valid on every repository its account reaches (no
  per-repository token as in GitLab): the docs advise an account of its own for the agent.
  Then the second guide pointed at its Gitea (`adbd783`, token by sops reference): `doctor` reads the
  repository, and a real pull request was opened, read (open), closed (closed) through the forge, its throwaway
  branch deleted.
- **T5.2 Freeze.** Manifest schema 1, `watch.json` schema 1, engine protocol 1: a change after that is a new
  schema number with a migration. The settings file gets its own number and its migrations.
  Done 2026-11-19: `docs/compatibility.md` (EN, FR) gives the rules; `config.SCHEMA` and `config.MIGRATIONS`,
  `llm.ENGINE_PROTOCOL` checked when a plug-in loads; the source `github-issue` renamed `issues` before the freeze
  (old name still read). The IA on-prem guide's manifest keeps `github-issue`, read as before.
- **T5.3 What a newcomer reads.** README rewritten around "your guide, your model" (the IA on-prem guide becomes
  the reference example); the architecture page current; a security page (keys as references, local server,
  what the model reads from the web is data, quotes checked by the code).
  Done 2026-11-19: README and README.fr rewritten (quick start with pipx, the needs per part, the three engines, the
  forges; the IA on-prem guide as the reference example with its measures), `docs/security.md` (EN, FR),
  `docs/code.md` current. Found while writing the quick start: the agent's folder and the cost journal were
  created in the current folder, so a newcomer running from the guide would have written them into it; they now
  default to `~/.vault-watch/`, an existing `./.vault-watch` and `./metrics/usage.jsonl` still used (the
  maintainer's set-up unchanged). To check at the release: the pipx install from the tag, on a clean machine.
- **T5.4 Release.** Tag, release notes from the changelog, the package installable with `pipx`.
  Done 2026-11-19: `pipx install git+…` checked in a throwaway environment (the commands, the server, the page and
  its files, nothing written into the guide); version 1.0.0, `collect.yml` default `agent_ref` v1.0.0.

Done when: someone who is not the author connects a guide by following the docs alone.

### M6. Compaction (1.2.0)

A watch only adds: « since » notes, footnotes stacked on footnotes, one warning copied into three pages, versions
kept « for the record ». Over months a guide grows heavy without anyone deciding it. Runs of their own, apart from
the watches (the cross-check of a watch keeps its full reading: nothing here makes it lighter), find what weighs
and propose to trim it, through the same review as a correction. Asked for on 2026-11-19; it takes up E1, E2
and C2 below. After M5: a new function, not a change of format.

- **T6.1 Size per page.** A budget per page (the manifest can set it per folder; a default otherwise) shown by
  `doctor` and in the interface as a warning, never a failure: where to look first (E1).
- **T6.2 The report: `vault-watch compact`.** One call reads the whole guide (the cost of a cross-check: about
  2.5 to 3 $ on the IA on-prem guide) and lists, without editing anything: the same fact stated in several pages
  (which page should keep it, which should link to it), piled-up history (successive « since » notes, superseded
  versions, advisories fixed long ago below the version floor), sections over budget and what makes them long.
  Each finding quotes its passages, like the cross-check's findings. Read-only pages are listed, never proposed.
- **T6.3 Proposals for the chosen findings.** The editor picks findings in the report; the agent proposes
  targeted edits (current text, proposed text, reason), never a page rewritten whole; a fact moved keeps its
  source and its footnote, a repetition becomes a link rather than a deletion. Then the same cross-check, review,
  mirror and pull request as a watch.
- **T6.4 Replace, do not pile up (C2), at the source.** The proposal step of a watch is told to replace the old
  fact rather than add a « since » note beside it, history staying in Git: less to compact later.
- **T6.5 Rhythm.** Quarterly or on demand (a « Compact » action in the interface), the cost announced before.

Built on 2026-11-20 (dev), docs in [docs/compact.md](docs/compact.md):

- T6.1: `sizes.py`, `[budget] page_kb` and `[budget.pages]`; `vault-watch compact` (the table), a line of `doctor`,
  the check « Size of the pages »; the growth over 90 days read from Git. First reading of the IA on-prem guide:
  129 pages, 891 KB, +56 % in 90 days (572 KB on 22 August 2026), 3 pages over 30 KB, and in almost every heavy
  page the heaviest section is its references.
- T6.2: the check « Compaction: what makes the guide heavy » (`compact.REPORT`, run by `verify.py`; from the
  command line `vault-watch compact --report`): findings « repeated », « history », « long », each with its
  passages; findings about read-only pages alone are left out.
- T6.3: a compaction run (`compact.propose`, mode `compact` of the graph; `vault-watch fix … --compact`): trims
  as corrections, a cross-check written for them (nothing lost, still readable), no web, no sweep. The code
  removes the note a trim leaves without a sentence, refuses a trim that leaves a sentence citing a removed note,
  removes a passage whole without leaving a hole, and lists under each trim the values no page states any more.
  The first real report (20/11/2026, Fable 5.2 at effort high: 30 findings, 6.28 $, 48 k tokens written) showed
  that the trims of thirty findings would not fit in one answer: the proposals now take several calls
  (`compact.batches`), each reading the whole guide from the cache the first one wrote (the Claude API) or the
  pages its findings name (the other engines), and the estimate of a run follows the findings ticked.
- T6.4: done in 1.0.1 (C2).
- T6.5: on demand, from « Check the guide », with its estimate; the size check says when.

Done on 2026-11-20: the real report (30 findings) and a real compaction run on the IA on-prem guide (193 trims in
78 pages, 32 KB of 891; the guide's pull request 91), released as 1.2.0.

Done when: a compaction run on the IA on-prem guide (several months of watches) gives a report the editor finds
right, and the trims chosen from it are merged with the guide's checks passing. Try it there first: the
second guide, just generated, has nothing piled up yet.

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

- [x] **First real run on the subscription** (2026-11-19: fix run `fix-2026-11-19`, 8 reported points, 30
  corrections in 6 minutes, 2 Opus calls reading 4.9 M tokens of which 4.0 M from the cache, 8.95 $ at list price,
  nothing billed; its translation went to the API, 0.16 $, because the settings named it: the review now warns).
  Before that: No full run has used the Claude Code engine yet. Watch #77 of the
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
