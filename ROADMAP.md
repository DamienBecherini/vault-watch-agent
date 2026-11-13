# Roadmap

Measured on 2026-11-08 (first real run, issue #50 of the vault): 81 kept items → 8 corrections, 0.90 $;
French content 408 k tokens (exact count), English mirror 353 k; French content grew from 575 KB to 853 KB
between June and October 2026, the security page from 15.7 KB to 42.2 KB. Architecture and analysis:
[docs/presentation.html](docs/presentation.html).

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
- [x] README with the measures of B1 and C1, MIT licence.
- [x] Public GitHub repository (source on Gitea, pushed to GitHub by a Gitea push mirror).
- [x] Web interface: `vault-watch serve` (FastAPI, server-sent events), one screen per pause of the graph.
- [x] Leads with their passage: a finding of a check of the guide or of the cross-check shows the sentence it is
  about, with its line number and the nearest lines, in the interface, the report and the fix run's pull request.
  The model quotes it, the code finds it in the page (exact, else the closest passage, flagged; else « not
  found »), so a quote the model got wrong is never shown as the guide's text.
- [ ] Blog article.
