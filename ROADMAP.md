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
- [ ] **Publication.** Every push to `main` on Gitea reaches the public GitHub repository through the push mirror,
  at once. To publish only stable versions, see the options in the project notes (work on a branch kept off the
  mirror, or sync the mirror by hand).
