# Plan: from one guide to a modular agent

Status: proposal of 2026-11-17, nothing of it is built. The work, task by task, is in
[modular-action-plan.md](modular-action-plan.md). This page answers one question: what has to change for someone
else to run this agent on their own guide, with the model of their choice, and trust the costs it shows.

## Where the agent stands

It was written for one guide, [Zero to Hero: On-Premise AI](https://ia-on-prem.damien.becherini.fr/), and three
things are tied to it.

| Tied to | What is fixed today | Where |
| :-- | :-- | :-- |
| The guide | Its GitHub repository and its site; only the local path changes (`VAULT_PATH`) | `graph.py`, `web.py`, `cli.py` |
| The guide's own tooling | The watch issues (label `veille`) and their `weekly-watch` artifact, the brief and the translation policy under `.agents/`, `scripts/run-audits.mjs`, `scripts/audit-freshness.mjs`, the version floors, French pages mirrored under `en/`, `last_modified` in the front matter | `inputs.py`, `prompts.py`, `graph.py`, `vault.py`, `verify.py` |
| Claude | Two engines, the Claude API and Claude Code; the web search and fetch of each; a 1M-token context for the steps that read the whole guide | `llm.py` |

A guide built on the same site engine
([starlight-obsidian-engine](https://github.com/DamienBecherini/starlight-obsidian-engine)) would not be enough: the
engine builds and publishes the site (links, lexicon index, deploy). The watch, the audits and the editorial rules
are a second layer that lives in the guide's repository, and the agent talks to that layer.

## Principles

- **Ports where there is a second user, not before.** Each port below comes with a second implementation that
  proves it (a sample guide, an OpenAI-compatible engine). No adapter is written for a provider nobody runs.
- **Every part of the guide's layer is optional.** A guide without audits gets no audit step; a guide without a
  mirror gets no translation. The agent says what it skipped and why, it does not fail.
- **The model proposes, the code decides** stays the rule, whatever the model: quotes checked by the code, two
  human pauses, nothing written by the model.
- **A price shown says where it comes from.**

## Phase 0. Ground rules (small)

- A `dev` branch that the public mirror does not push, releases tagged from `main`, a `CHANGELOG.md`.
- A **sample guide** in the repository (`examples/sample-guide/`: a dozen pages, a watch file, no tooling): the
  second user of everything below, used by the tests instead of the throwaway repository they build today.
- Tests run in CI on every push.

## Phase 1. The guide as configuration (medium) — the one that opens the door

A manifest in the guide's repository, read by the agent (`vault-watch.toml` at its root), and one home per guide
on the machine, so the agent can serve several.

```toml
[guide]
name = "Zero to Hero: On-Premise AI"
repository = "DamienBecherini/ia-on-prem-vault"   # where issues and pull requests go
site = "https://ia-on-prem.damien.becherini.fr/"
base_branch = "main"

[content]
language = "fr"                 # the language the pages are written in
include = ["**/*.md", "**/*.mdx"]
exclude = ["en/**", "docs/**", "scripts/**"]
mirrors = { en = "en/" }        # optional: translated copies kept in step
modified_field = "last_modified"  # optional: front matter date bumped by an edit

[watch]
source = "github-issue"         # see phase 2
label = "veille"
artifact = "weekly-watch"

[rules]                         # optional: the agent ships defaults
brief = ".agents/skills/vault-watch/brief.md"
translation_policy = ".agents/skills/vault-translate-content/references/translation-policy.md"

[checks]                        # optional, each one
audits = "node scripts/run-audits.mjs"
claims_due = "node scripts/audit-freshness.mjs --due-only --json={out}"
version_floors = { script = "scripts/audit-version-floors.mjs", file = ".agents/vault-maintenance/version-floors.json" }

[budget]
max_context_tokens = 450000     # see phase 3
```

- `vault-watch init` writes a manifest by looking at the repository, and says what is missing for each step.
- Default brief and translation policy shipped with the agent, used when the guide has none.
- Done when: nothing in `src/` names the IA on-prem guide; the sample guide goes from a watch file to a pull
  request in the tests; the IA on-prem guide runs unchanged with its manifest.

## Phase 2. Where the watch comes from (medium)

Today the guide collects its own watch (a script and a weekly GitHub workflow) and the agent only downloads it. A
guide without that script has nothing to analyse.

- A `WatchSource` port with three implementations: the issue and its artifact (today), a local `watch.json`
  (exists, `--watch-json`), and a collection run by the agent from a `feeds.json` (releases, advisories, RSS).
- The collection published as a reusable GitHub workflow, so a guide gets a weekly watch with a `feeds.json` and
  ten lines of YAML.
- The format of `watch.json` documented and versioned: it is the contract between any collector and the agent.
- Later, the forge as a port too (`gh` only today; Gitea and GitLab have the same notions).

## Phase 3. Models through a port (large)

`llm.py` already has the shape: one `parse(system, prompt, schema, effort, node, context, web)` and two classes.
What is missing is saying what an engine can do, and adapting the steps to it.

- **Capabilities declared by each engine**: context window, structured output (native or by instruction),
  web search and page reading (the provider's, or none), effort levels, prompt caching, where its prices come from.
- **Needs declared by each step**: the triage and the mirror need structured output only; the proposals need
  excerpts; the cross-check and the checks need the web, and today the whole guide in context.
- **The context decides the strategy, not the other way round.** The agent measures the guide (it already counts
  its tokens) and compares it with the model's window minus a margin for the answer and the web. It fits: the
  whole guide, as today. It does not: the same step by chapter or by excerpts, said in the interface, with the
  loss it implies (a contradiction between two chapters can be missed). `max_context_tokens` in the manifest is
  the guide's own budget: a CI check of the guide can keep it under (roadmap E1), which keeps cheaper models usable.
- **Web tools as a second port** (`search`, `fetch`), for the engines that have none: a search API (SearXNG, Brave,
  Tavily) and a plain fetch run by the agent, with the model calling them as tools.
- **A third engine as the proof: OpenAI-compatible** (OpenAI, Mistral, a local server such as vLLM, llama.cpp or
  Ollama): base URL, key by reference, models from `GET /v1/models`.
- **A role per step** rather than two roles, so a small local model can sort and translate while a large one
  cross-checks.
- **For contributors**: a page "write an engine" (the protocol, the capabilities, an example of 100 lines) and a
  set of contract tests any engine must pass with recorded answers.
- **`vault-watch eval` as the acceptance test** of a model or an engine: the same past watches replayed, scored
  against what the human merged. An engine is "supported" when its scores are published.

## Phase 4. Prices that say where they come from (small to medium)

- Three sources, in this order: a price set in the Settings, a price fetched from a public source, the default
  shipped with the agent (dated).
- Each price shown carries its origin and its date ("default of 2026-11", "set by you", "fetched on …"), on the
  Costs page, on the estimates of the buttons and in the Settings.
- The journal keeps, for each call, the price used and its origin: the history does not change when a price does.
- What the providers offer, as checked on 2026-11-17: the Claude Models API gives the context window of a model,
  not its price; the public price list of LiteLLM (`model_prices_and_context_window.json`) gives prices per token
  and context sizes for many providers; OpenRouter's list is to check again (the check made returned no price
  field). So "automatic" means reading a public list, never a provider's own API, and the default must stay good.
- A model without any price is counted at 0 and flagged, as today.
- Calls on a subscription stay "not billed", with what they would have cost.

## Phase 5. What makes a project usable by others (small, all along)

- `CONTRIBUTING.md`, the architecture page kept current, "connect your guide" (the manifest, what each optional
  part unlocks), "write an engine", "write a watch source".
- The settings file versioned, with a migration when its shape changes.
- The interface in two languages already; the language of the guide's content no longer assumed (French today in
  the prompts, the diff cards and the checks).
- Security notes: keys only ever as references; the server local only; what is read from the web or from a watch is
  data for the model, and the code checks every quote before anything is applied.

## Order and size

| Phase | Size | Why this place |
| :-- | :-- | :-- |
| 0. Ground rules | small | Without a sample guide the rest cannot be tested by anyone else |
| 1. Guide as configuration | medium | Nobody can try the agent on their guide before it |
| 3a. Capabilities, context strategy | medium | Needed by any other model, and by a larger guide |
| 4. Prices | small to medium | Independent; can go in parallel |
| 2. Watch sources | medium | A second guide needs a watch; the local file covers the first tries |
| 3b. OpenAI-compatible engine, web tools | large | The proof of the port |
| 5. Documentation | small | With each phase, not at the end |

## Risks

- **Generalising from one example.** The sample guide helps, a second real guide helps more: the manifest should
  be tried on one before its format is announced as stable.
- **Quality with other models.** The measures published are those of Claude Opus on the whole guide. Another
  model, or the same step by excerpts, is another agent until `eval` says otherwise.
- **The web tools.** Reading a page exactly (a version, a date) is where the engines differ most; it already
  differs between the Claude API and Claude Code.
- **Size.** Phases 1 to 4 roughly double the code that is not the graph. Each phase has to leave the IA on-prem
  guide working as it does today.
