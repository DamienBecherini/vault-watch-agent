# Changelog

Versions follow the milestones of [phase G of ROADMAP.md](ROADMAP.md#phase-g--a-modular-agent). The version is written
once, in `src/vault_watch_agent/__init__.py`; `/api/health`, `/api/info` and the page footer show it.

## Unreleased (0.3.0, M1: any guide)

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
