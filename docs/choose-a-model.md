*[Version française](choose-a-model.fr.md)*

# Choose a model

Since 0.6.0 the agent runs on any engine: the Claude API, Claude Code, or any server of the OpenAI chat API, hosted
or local ([Write an engine](write-an-engine.md)). Running is not doing the work well. This page says which models
the agent is used with, what was tried beyond them, and why nothing more is promised.

## The models the IA on-prem guide uses

The agent keeps the guide [Zero to Hero: IA on-premise](https://github.com/DamienBecherini/ia-on-prem-vault) up to
date with:

| Role | Steps | Model |
| :-- | :-- | :-- |
| reasoning | triage of the watch, proposals, cross-check against the whole guide, sweep | Claude Opus 5.5 |
| translator | the English mirror of the corrected pages | Claude Sonnet 5.5 |

through the Claude API (billed per token) or Claude Code (the subscription). Every correction goes through the review
screen and a pull request a human merges: that review, not a score, is what the guide relies on.

These are the only models the project commits to. With any other one the engine works (it passes the
[contract tests](../tests/engine_contract.py)), the quality of the corrections is not measured, and you should check
its proposals before trusting a watch that says « nothing to change ».

## What each step asks of a model

- **Triage**: read the watch's items and keep those that may touch the guide. Short calls; a modest model does it.
- **Proposals**: decide, for each kept item and its excerpts of the guide, whether a sentence is now wrong and how
  to write it. The judgement step: a model that is too cautious answers « no change » and the watch looks clean.
- **Cross-check and sweep**: read the corrections against the whole guide, with the web, and find the other pages
  that state the same fact. The longest step, and where most corrections come from (7 of the 11 of watch #77). A
  window smaller than the guide makes the agent read it by chapter: more calls, and a fact stated in two chapters is
  no longer seen in one read.
- **Mirror**: translate the corrected passages. A good translation model is enough.

## A model for one step

The Settings give a model and an effort to two roles: reasoning (triage, proposals, cross-check, the checks of the
guide, the compaction) and translation (the mirror, the translation checks). A step can be set apart from its
role: « Models and effort », then « Set a step apart » under the role. It then runs on the model chosen for it,
and at the effort chosen for it when one is: that effort applies as it is, where the role's « lower » and
« higher » move every other step one level. Everything else follows the role.

The use this was made for: the [compaction](compact.md) on the strongest model, a few times a year, while the
weekly watches stay on the model measured here. The estimates and the cost journal follow the model of each step.
In `settings.json`: `"steps": {"compaction": {"model": "claude-fable-5-2", "effort": "high"}}`.

## What was tried

**A local model on a laptop.** Qwen3.6-35B-A3B (llama.cpp, quantized, 64k window) on an 8 GB laptop GPU. It runs
every step in the schema; on the sample guide, read whole in one call, its cross-check found the contradiction
planted between two chapters. On watch #77 replayed by excerpts (no
cross-check), it kept the right item, a LiteLLM security advisory, saw that the guide's minimum version was below
the advisory's, then declined to change the sentence: no proposal, where Claude Opus 5.5 made three, all right. One
run on one watch: a sign, not a measure.

Models able to do the proposal step locally need far more memory: a graphics card of 32 GB or more, or an engine that
streams a large model from the SSD (InferSSD or the like) on such a card. The project has none, so no local model is
recommended.

**A hosted model through the OpenAI-compatible engine.** Claude Haiku 5.5 through Anthropic's OpenAI layer, on the
sample guide only, to try the engine itself (schema in the instructions, web search through SearXNG, per-token
billing). It says nothing of other hosted models: for a Claude model, use the Claude API engine.

## Measuring your own model

`vault-watch eval` replays a past watch on the guide as it was, up to the review, and compares the proposals with
the pull request a human merged after it:

```bash
vault-watch eval --issue 77 --at <commit before the PR> --truth <base>..<head> --variant keyword --judge claude-code
```

`keyword` stops before the cross-check (minutes); `full` runs it (the whole guide, much longer on a local model). Read
the result with its limits:

- **The judge is a model.** It pairs each proposal with the hunks of the merged diff. By default it is a Claude
  model (`--judge api|claude-code`), so that a local model does not score itself; but Claude judging Claude's
  proposals is not neutral either. Read the pairing in the result file, not only the figures.
- **The truth is what the human merged.** For watch #77 that pull request was itself a run of the agent on Claude
  Opus, checked and merged by a human: replaying Opus measures how well it repeats a reviewed run, not an
  independent truth. A watch the human processed by hand (as #30) is a fairer test.
- **One watch is one case.** Several watches, of several kinds (security, releases, prices), before deciding.

The result files of the runs above are in [`metrics/eval/`](../metrics/eval/).
