<div align="center">

<img src="src/vault_watch_agent/static/icon.svg" alt="" width="96" height="96">

# vault-watch-agent

**Keep a Markdown guide up to date with what changes in its field: a LangGraph agent proposes sourced corrections, you review them, it opens the pull request.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![Claude](https://img.shields.io/badge/Claude-API%20or%20subscription-D97757?logo=anthropic&logoColor=white)](docs/choose-a-model.md)
[![FastAPI](https://img.shields.io/badge/FastAPI-web%20UI-009688?logo=fastapi&logoColor=white)](#the-web-interface)
[![Human in the loop](https://img.shields.io/badge/human-in%20the%20loop-FFC107)](#principles)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**English** · [Français](README.fr.md)

**[All the documentation](docs/README.md)** · [Connect your guide](docs/connect-your-guide.md) · [A run, step by step](docs/run.md) · [Check the guide](docs/check.md) · [Collecting a watch](docs/collect.md) · [Compaction](docs/compact.md) · [What is new](docs/news.md) · [Chapters](docs/chapters.md) · [Choose a model](docs/choose-a-model.md) · [Costs](docs/costs.md) · [Security](docs/security.md) · [What stays stable](docs/compatibility.md) · [Overview with diagrams](docs/presentation.md) · [How the code fits together](docs/code.md)

</div>

---

A technical guide goes stale one release at a time: a version number, a flag that was renamed, a security advisory
that changes a recommendation. vault-watch-agent reads what changed in your guide's field (release notes,
advisories, feeds), finds the sentences of the guide that are now wrong, and proposes corrections that quote the
current text, give the new one and cite a source. It re-reads them with the whole guide in context, waits for your
review, applies what you accepted on a branch, translates the changes into the guide's mirrors, runs the guide's
own checks and, after a second yes, opens the pull request.

**The idea.** Three pieces, each in its own repository. You write a technical guide in
[Obsidian](https://obsidian.md), as plain Markdown notes in a git repository. An engine,
[starlight-obsidian-engine](https://github.com/DamienBecherini/starlight-obsidian-engine), publishes the vault on the
web as an [Astro Starlight](https://starlight.astro.build) site (wiki links, Mermaid diagrams, both languages, a
« Give my opinion » window), rebuilt by the guide's CI at each merge. And this agent takes the upkeep off your hands:
a guide on a fast-moving field goes stale faster than one person can follow it.

```mermaid
flowchart LR
  you(["You"]) -->|write| vault["Obsidian vault<br/>Markdown, wiki links,<br/>French + English"]
  vault -->|"merge on main"| engine["starlight-obsidian-engine<br/>builds the site"]
  engine --> site["The guide on the web"]
  field["What changes in the field<br/>releases, advisories, prices"] --> agent["vault-watch-agent<br/>keeps it true"]
  agent -->|"pull request,<br/>after your review"| vault
  classDef person fill:#fff4d6,stroke:#a65f00,color:#3d2a00
  class you person
```

**Your guide.** Any Markdown guide in a git repository, described by a small manifest (`vault-watch.toml`): where the
pages are, in which language, which folders mirror them, where its watch comes from, which of its own checks to run.
Hosted on GitHub, on a Gitea server, or kept local. The agent edits the Markdown and stops at the pull request: if
the guide is published as a site, its own chain rebuilds it after the merge, whatever that chain is.

**Your model.** Claude through Claude Code on a Claude subscription (nothing billed per call) or through the API;
or any OpenAI-compatible server, local or hosted. The project measures and commits to Claude Opus 5.5 and Sonnet
5.5 only: see [Choose a model](docs/choose-a-model.md).

**Your decision.** The model never writes a file. Nothing is applied before your review, nothing is pushed before
your go-ahead, and the pull request is merged by you.

![The review screen: one block per item of the watch (here a vLLM release), its related corrections ticked together by one box, each card with its severity, its page, the cross-check's verdict, a word-level diff, its source and « Retouch »](docs/images/review.png)

*The review screen on a test watch (`watch.json`): a vLLM release that changes a sentence and its footnote, ticked together.*

## Quick start

```bash
pipx install git+https://github.com/DamienBecherini/vault-watch-agent@v1.4.3

cd my-guide                 # the root of the guide's git repository
vault-watch init            # writes vault-watch.toml from what the folder shows; read it, adjust it
vault-watch doctor          # what is ready, what is missing before a first run
vault-watch collect         # optional: what the feeds the manifest lists say, without a model
vault-watch serve           # http://127.0.0.1:4430/: watches, review, publish, settings
```

`init` guesses the language, the mirrors, the GitHub repository of the `origin` remote (a Gitea one is three lines to add) and the guide's own scripts; every
key of the manifest, and what each optional part unlocks, is in [Connect your guide](docs/connect-your-guide.md).
A sample guide in [`examples/`](examples/) shows the fewest parts.

What you need:

| For | What |
| :-- | :-- |
| every guide | Python 3.11+, git |
| the model | one engine: Claude Code signed in with a Claude subscription, a Claude API key, or an OpenAI-compatible server ([settings](#the-model)) |
| a guide on GitHub | the GitHub CLI `gh`, signed in (`gh auth login`) |
| a guide on Gitea | a Gitea token, given by reference ([Connect your guide](docs/connect-your-guide.md), [Security](docs/security.md)) |
| the guide's checks | whatever they run (Node.js for an `npm test`, for instance) |

## How a run goes

```mermaid
flowchart TD
  collect --> triage --> locate
  locate -->|"Send: one branch per group"| propose --> number
  locate -->|nothing to check| number
  number --> crosscheck --> report --> review{{"⏸ human review"}}
  review -->|accepted| apply --> retouch{{"⏸ your retouches (optional)"}} --> mirror --> audits --> links --> publish{{"⏸ push + PR?"}}
  review -->|none| stop((end))
  publish --> stop
  classDef human fill:#fff4d6,stroke:#a65f00,color:#3d2a00
  class review,retouch,publish human
```

| Step | What it does |
| :-- | :-- |
| `collect` | Reads the watch the manifest names: a `watch.json` file, a forge issue and the artifact of its workflow run, or the agent's own collection from the guide's feeds ([watch format](docs/watch-format.md)) |
| `triage` | The model sorts the items: correction, addition candidate, or nothing for the guide (the guide's brief says what matters) |
| `locate` | Finds the pages concerned and groups the items that touch the same pages or the same tool |
| `propose` | One parallel branch per group: corrections that quote the current text, give the new text and a source |
| `number` | Numbers the corrections (C1, C2…), checks each quote, flags overlapping edits |
| `crosscheck` | Re-reads every correction with the whole guide in context (prompt caching, or chapter by chapter when it does not fit the model's window) and the web: keep, revise or reject, plus consistency edits on other pages. Then a sweep: the values the corrections remove that still appear elsewhere |
| `report` | Writes the report you review |
| `review` | ⏸ Pause: you accept all, none, or a list |
| `apply` | Applies the accepted corrections on a git worktree of a new branch and bumps the pages' date field |
| `retouch` | ⏸ Optional pause: you read and retouch the pages of the branch, in your Obsidian (the guide's folder is lent to the run, what it held set aside and put back after) or in the page, or you skip; your retouches are committed as yours ([A run, step by step](docs/run.md#the-pause-to-retouch-the-pages)) |
| `mirror` | Translates into the guide's mirrors (an English copy under `en/`, for instance) what changed in each source page on the branch, passage by passage: the corrections, and any edit by hand |
| `audits` | Runs the guide's own checks, if the manifest declares them |
| `links` | Checks the external links of the changed pages |
| `publish` | ⏸ Pause: the pages and their translation can still be corrected or translated again, then checked again; on a yes, pushes the branch and opens the pull request (a local guide keeps the branch) |

What decides at each step, an example with its cost, the screens where you decide (the review, the retouches, the
publish step) and how your folder gets the pull request once merged: [A run, step by step](docs/run.md).

Two more kinds of run use the same review and pull request: a **fix run** turns reported errors (a reader's, a
check's) into checked corrections, and a **check of the guide**, on demand, looks for what is wrong or
inconsistent in the whole guide. A **compaction run** keeps the guide from growing heavy: a watch only adds, so a
check lists what is repeated, piled up or longer than it needs, and the trims you keep are reviewed like corrections
([Compaction](docs/compact.md)). An **addition run** looks for what no source of the watch announces: a check lists
what a reader would look for and not find, and each lead you keep is checked on the web, then written where it
belongs ([What is new](docs/news.md)).

## Principles

- **The model proposes, the code decides.** Each correction quotes the current text; a deterministic check
  refuses it unless the quote occurs exactly once in the page. Pages declared read-only are never edited.
- **Human in the loop, writing.** The run stops after the report (LangGraph `interrupt`), where each proposal can
  be retouched; again after the corrections are applied, to retouch the pages themselves if you want; and before
  anything leaves the machine, where the pages and their translation can still be corrected. A paused run is checkpointed in SQLite and resumed later, from another process,
  days later if needed.
- **Evidence, not memory.** Proposals rely on the release notes and advisories of the watch, and the cross-check
  on primary sources read on the web, never on the model's memory alone.
- **The guide's rules.** The editorial brief and the translation policy live in the guide and are read at each
  run; the agent has defaults for a guide without them.

## The model

| Engine | What runs | What it costs |
| :-- | :-- | :-- |
| `claude-code` | [Claude Code](https://claude.com/claude-code) on this machine, signed in with a Claude subscription, run once per call (`claude -p`) | Nothing billed: the usage counts in the subscription's limits |
| `api` | The Claude API through the official SDK | Per token, at list price |
| `openai` | Any OpenAI-compatible server: llama.cpp, vLLM, Ollama, a hosted service; web search through SearXNG | Your server's |

Without a choice, the agent uses Claude Code when it finds it signed in with a subscription, otherwise the API.
The engine, the model and the effort of each role (reasoning, translation) are chosen in the Settings of the web
interface (the gear), which writes `~/.vault-watch/settings.json`; `VAULT_WATCH_ENGINE` forces one engine for a
command. The agent never falls back to a billed engine on its own: when a subscription limit is reached, the run
stops and can be resumed later (`resume --retry`) or with another engine.

Keys are never stored: the settings take a reference, `env:NAME`, `sops:file#NAME` (a file encrypted with
[sops](https://github.com/getsops/sops)) or `file:path`, and refuse a key in plain text. Another engine can be
added as a package ([Write an engine](docs/write-an-engine.md)).

## The web interface

```bash
vault-watch serve                     # http://127.0.0.1:4430/
vault-watch serve --idle-exit 3600    # stops after 1 h without a visit or a running analysis
vault-watch serve --notify en         # Windows notification when a run waits for you, ends or fails
```

One screen per step of a run: a run in progress (each finished step streamed to the page), the review (one block per
item or lead, one card per correction with a word-level diff, its source and the cross-check's verdict), the
retouches (your folder lent to Obsidian, or an editor in the page), the publish step (« Before publishing »: the
guide's checks, the translation, the links to check yourself; then each page changed beside its translation, still
correctable), then the pull request. Around them:

![« To handle », the first page: no run paused, three checks whose leads are to sort, and what can be started](docs/images/todo.png)

| Page | What it is for |
| :-- | :-- |
| Watch › To handle | The first page: everything that waits for you, wherever it comes from: a run paused for your review, a watch to start, the checks whose leads are to sort, and your guide's folder when it lacks pull requests merged, with « Update my folder »; the menu « Watch » shows how many |
| Watch › Automatic watch | The watches with their status and a button to analyse one |
| Watch › Every run | Every run, newest first: the watches', and those started from a check, from « Report or suggest » or from « Languages » |
| Watch › Sources followed | What each source of the watch brought and what became of it, and a check of the sources themselves, whose changes go to a pull request ([which sources earn their place](docs/collect.md#which-sources-earn-their-place)) |
| Watch › Check the guide | Checks on demand, of three kinds shown in colour (guide health, lighter guide, what is new), the free ones and the paid ones with their estimate: audits, links, freshness, consistency, translations, what makes the guide heavy, what is new. Their leads are sorted, then sent to a run ([Check the guide](docs/check.md)) |
| Report or suggest | Errors to fix, an idea or a piece of news to check and write, or links to read whole (an article, a page, a PDF, a video) for the leads they hold; what you type is kept as a draft, one per tab |
| Languages | The pages ahead of their mirror, and those you changed in your folder without committing: what changed is translated, then the usual checks and pull request ([A run, step by step](docs/run.md#sync-the-languages)) |
| Chapters | In the menu under the guide's name: the chapters the agent works on, proposed by a model or written by hand: why and how, [Chapters](docs/chapters.md) |
| Costs | What the upkeep costs, by month and by run ([Costs](docs/costs.md)) |
| Settings | The gear: engine, model and effort of each role or of one step, prices and where they come from, what the guide provides |
| Give my opinion | A note, a bug, an idea: you send it yourself, as a GitHub issue or an e-mail; the agent sends nothing |

![The leads of what is new: a lead unfolded, what the source says beside the passage of the guide it is about, what to check, what it changes for the reader, « Dig deeper into this lead », « What I already know », its sources and the pages to read also](docs/images/leads.png)

*A lead of « Links to read whole » on the reference guide, unfolded; nothing is ticked yet, so the button asks to
tick leads.*

Every screen that starts a paid step says what it will cost (on a subscription, what it is worth at list price,
struck through) and what will run it (engine, model, effort) before the click. The interface is in English or French, light or dark, with palettes and a text size of your choice. A
run started here can be resumed from the command line, and the reverse. The server listens on 127.0.0.1 only
([Security](docs/security.md)).

## The command line

```bash
vault-watch run --watch-json watch.json     # or --issue 50 for a forge issue; stops at the review
vault-watch resume <run> --accept C1,C3     # or all / none; applies, translates, checks, stops again
                     --edit C3=my-text.md   # a proposal retouched by you before it applies
vault-watch resume <run> --publish yes      # push the branch and open the pull request
vault-watch status <run>
vault-watch fix <run> --findings errors.txt # reported errors → checked corrections, same review and PR
vault-watch collect --json watch.json       # the watch from the guide's feeds, no model
vault-watch compact                         # what each page weighs and gained, no model; --report: what to trim
vault-watch news                            # leads: what a reader would look for and not find; --explore: the web
vault-watch chapters                        # the chapters the agent works on; --propose: a model's split
vault-watch mirror                          # the pages ahead of their mirror; --yes: translate what changed
vault-watch costs --by month                # or year, run, step
vault-watch --guide ../other-guide doctor   # any command on another guide
```

## The reference guide

The agent was built for [Zero to Hero: On-Premise AI](https://ia-on-prem.damien.becherini.fr/)
([repository](https://github.com/DamienBecherini/ia-on-prem-vault)), about 400 k tokens of French content mirrored
in English, whose biweekly watch is collected by a GitHub workflow. It is the guide whose results are measured
below. A second guide, private, written in French only and hosted on a self-hosted Gitea, checked that the manifest
and the forges work on a guide the agent was not written for.

**How it is made.** An Obsidian vault: Markdown pages, wiki links and footnotes, French at the root and English
under `en/`, readable in Obsidian as it is. The guide's CI rebuilds the site with starlight-obsidian-engine at each
merge on `main` that changes a page. The agent knows nothing of the engine: it reads and edits the vault's
Markdown, runs the guide's own checks, and opens a pull request; the merge then redeploys the site.

**Produced.** Nineteen pull requests of the guide made by the agent and merged after review (as of 20 November
2026), for example [#78](https://github.com/DamienBecherini/ia-on-prem-vault/pull/78) (a watch),
[#79](https://github.com/DamienBecherini/ia-on-prem-vault/pull/79) (30 corrections from a check of the whole guide),
[#91](https://github.com/DamienBecherini/ia-on-prem-vault/pull/91) (a compaction) and
[#98](https://github.com/DamienBecherini/ia-on-prem-vault/pull/98) (additions checked on the web).

**Evaluated.** `vault-watch eval` replays a past watch on the guide as it was and has a judge model (always Claude)
match each proposal with the diff the human merged ([`metrics/eval/`](metrics/eval/)). On 18 November 2026 the
replay of watch #77 found the 11 corrections of #78, none wrong. On watch #30, no proposal that reached the review
was wrong; most misses changed only a date that the release page itself made misleading.

**Cost.** Every model call is logged in a journal (here [`metrics/usage.jsonl`](metrics/usage.jsonl), for you `~/.vault-watch/usage.jsonl`); `vault-watch costs` totals
it, with the calls made on a subscription apart (0 billed, and what they would have cost on the API). Measured in
November 2026 on the API at list price, Opus 5.5 for reasoning and Sonnet 5.5 for the English mirror:

| Run | Cost |
| :-- | --: |
| Watch with excerpts only (81 items kept, 8 corrections) | 0.90 $ |
| Full watch with the whole-guide cross-check | 2.95 – 4.45 $ |
| Fix run on reported errors | 5.60 – 8.15 $ |
| Translation-only fix run (Sonnet) | 0.35 $ |
| On-demand check of the guide (audits, links, consistency, translations, dated claims) | 7.25 – 10.85 $ |
| Compaction: the report, then a run of trims on 30 findings (Fable 5.2 on these two steps) | 6.28 $, then 18.87 $ |
| What is new: the leads, then an addition run on 2 to 5 leads | 2.28 $, then 8.70 – 12.95 $ |

The cross-check dominates: writing 400 k tokens to the prompt cache costs about 2 $, a later call on the same cache
about 0.08 $. Two full watches a month come to about 100 $ a year; a guide half the size costs about half. On
Claude Code with a subscription, nothing is billed, but a cross-check weighs on the subscription's limits.

These amounts are indicative: they are what the calls are worth at the API's list price. The author's calls went
through the API access of his Claude subscription: he paid his subscription and nothing more. With a key billed
per token, they are what you would pay. What makes the price, how the estimates are made, and the journal:
[Costs](docs/costs.md).

## What this repository shows

| LangGraph feature | Where | What for |
| :-- | :-- | :-- |
| `StateGraph` over a `TypedDict` state | [`graph.py`](src/vault_watch_agent/graph.py), [`state.py`](src/vault_watch_agent/state.py) | One node per step; the state holds plain JSON so a paused run can be stored |
| Reducers (`Annotated[list, operator.add]`) | `state.py` | Parallel branches append their proposals and their usage without overwriting each other |
| `Send` fan-out from a conditional edge | `fan_out` in `graph.py` | One `propose` branch per group of items, run in parallel |
| `interrupt()` and `Command(resume=…)` | `review` and `publish` nodes | The two human pauses; your answer is the value `interrupt()` returns |
| `SqliteSaver` checkpointer, one thread per run | [`cli.py`](src/vault_watch_agent/cli.py), [`web.py`](src/vault_watch_agent/web.py) | `run` and `resume` are separate processes, days apart; the web page and the command line share the runs |
| `update_state(…, as_node="propose")` | [`fix.py`](src/vault_watch_agent/fix.py) | A fix run makes its own proposals, then enters the graph as if `propose` had run |
| `stream(stream_mode="updates")` | `web.py` | Each finished step is pushed to the page (server-sent events) |

Every model call answers into a Pydantic model (structured output). More than 270 tests (pytest) run the whole graph against
a fake model and a throwaway git repository; an engine contract checks any engine. How the modules fit together:
[docs/code.md](docs/code.md).

## Design choices

- **LangGraph for the orchestration, each engine's own client for the model.** The graph needs state, parallel
  branches, pauses and a checkpointer; the model calls need structured output, prompt caching, web search and the
  exact usage of each call. No LangChain chat-model wrapper sits in between.
- **No vector RAG.** A guide that fits the model's window is read whole, with prompt caching: the model sees
  footnotes and inconsistencies between pages that retrieval would cut. A guide that does not fit is read chapter
  by chapter. One exception, chosen by the editor: a call that checks one lead on the web, over many rounds of
  search, may read the pages its lead names and the plan of the guide. The pages are named by a call that had the
  whole guide before it, and the cross-check that follows reads every page.
- **A watch corrects, the editor decides what is added.** A watch lists additions (a new model, a new tool) as
  candidates in its report and writes none. Writing them is a run of its own, on the leads the editor keeps.

## Limits

- **Markdown in git.** Pages in another format, or a guide that is a subfolder of a larger repository, are not
  supported.
- **No new page.** An addition run writes in the pages that exist; when a subject needs a page of its own, it
  says so and what the page would hold, and writing it stays with the editor.
- **Dates are hard.** A release has a creation date, a tag date and a publication date; when its sources do not
  settle one, the agent declines rather than guesses.
- **Measured on Claude only.** Another model runs, but the quality of its corrections is not measured: review its
  « nothing to change » with care ([Choose a model](docs/choose-a-model.md)).

## Repository layout

```
src/vault_watch_agent/
  graph.py       the graph: nodes, edges, the two pauses, report and pull request text
  state.py       graph state and the structured outputs the model must answer with (Pydantic)
  guide.py       the guide as its manifest describes it (vault-watch.toml)
  vault.py       pages: search, exact-quote check, apply an edit, the whole guide for the cross-check
  chapters.py    the chapters of a guide; reading.py the guide read whole, or chapter by chapter
  llm.py         the engines (Claude API, Claude Code, plug-ins); openai_compat.py the OpenAI-compatible one
  webtools.py    web search and page reading for the engines without a web of their own, and for Claude Code (mcp_fetch.py)
  steps.py       each step that calls the model: its role, its effort, what it needs
  forge.py       GitHub (gh) and Gitea (API): issues, artifacts, pull requests
  watches.py     where the watches come from; collect.py the agent's own collection; inputs.py the watch format
  sources.py     what each source of the watch brought; sourcecheck.py the sources themselves, checked
  crosscheck.py  whole-guide cross-check; fix.py fix runs; verify.py checks of the guide; evaluate.py replays
  sizes.py       what each page weighs and gained; compact.py compaction: what weighs, the trims
  news.py        what a reader would look for and not find: the leads, the additions checked on the web
  prompts.py     system prompts, from the guide's brief and translation policy
  config.py      the user's settings; prices.py, costs.py what the calls cost
  store.py       the runs database kept light; notify.py desktop notifications
  onboard.py     init and doctor; cli.py the command line; web.py the server, static/ its page (no build step)
tests/           fake model, throwaway git repository, engine contract
examples/        a sample guide and its manifest
metrics/         the reference guide's cost journal and evaluation results
docs/            the documentation (index: docs/README.md), in French in docs/fr/, screenshots in docs/images/
```

Next steps: [ROADMAP.md](ROADMAP.md). Changes: [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE)
