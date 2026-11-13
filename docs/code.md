<div align="center">

# vault-watch-agent: how the code fits together

**A reading guide for developers: modules, the graph state, where the model is called, and how a paused run survives.**

**English** · [Français](code.fr.md) · [Overview](presentation.md) · [README](../README.md)

</div>

---

About 3,000 lines of Python in [`src/vault_watch_agent/`](../src/vault_watch_agent/), a static page without build step,
and tests that run the whole graph against a fake model and a throwaway git repository. Start with
[`graph.py`](../src/vault_watch_agent/graph.py): everything else either feeds it or drives it.

## Modules and their dependencies

```mermaid
flowchart TB
  subgraph entry["Entry points"]
    cli["cli.py<br/><i>command line</i>"]
    web["web.py<br/><i>FastAPI + static/</i>"]
  end
  subgraph runs["Kinds of run"]
    graphpy["graph.py<br/><i>the LangGraph graph</i>"]
    fix["fix.py<br/><i>reported errors → corrections</i>"]
    verify["verify.py<br/><i>on-demand check</i>"]
    evaluate["evaluate.py<br/><i>replay + judge</i>"]
  end
  subgraph steps["Graph helpers"]
    crosscheck["crosscheck.py<br/><i>whole-guide review</i>"]
    prompts["prompts.py<br/><i>system prompts</i>"]
    quotes["quotes.py<br/><i>find a passage</i>"]
  end
  subgraph base["Foundations"]
    state["state.py<br/><i>state + output schemas</i>"]
    llm["llm.py<br/><i>the only Claude caller</i>"]
    vault["vault.py<br/><i>pages, search, edits</i>"]
    inputs["inputs.py<br/><i>gh, watch, scripts</i>"]
    costs["costs.py"]
    notify["notify.py"]
  end
  cli --> graphpy & fix & evaluate & crosscheck & costs & notify & web
  web --> graphpy & fix & verify & costs
  graphpy --> crosscheck & prompts & quotes & state & llm & vault & inputs
  fix --> state & llm & vault
  verify --> quotes & llm & vault & inputs
  evaluate --> llm & inputs
  crosscheck --> quotes & llm & vault
  quotes --> vault
  vault --> inputs
  classDef model fill:#e2f1f6,stroke:#0a7ea4,color:#0b3a4a
  class llm model
```

Two rules shape this graph:

- **One door to the model.** Only [`llm.py`](../src/vault_watch_agent/llm.py) imports `anthropic`. Every other
  module receives an object with a `parse(system, prompt, schema, effort, node, context, web)` method (the `LLM`
  protocol), so the tests swap it for a fake.
- **One door to the guide.** Reading, searching and editing pages go through
  [`vault.py`](../src/vault_watch_agent/vault.py); calls to `git`, `gh` and the guide's own scripts go through
  [`inputs.py`](../src/vault_watch_agent/inputs.py). The model never touches a file.

| Module | Lines | Role |
| :-- | --: | :-- |
| `graph.py` | 606 | Builds the graph (`build(deps, checkpointer)`), one closure per node; report, PR title and body |
| `web.py` | 570 | `create_app(settings)`: REST routes, server-sent events, background jobs, the static page |
| `verify.py` | 315 | Catalogue of checks (`Check`), cost estimates, one `run_*` function per check |
| `cli.py` | 247 | `vault-watch run / resume / fix / eval / costs / serve`; wires the checkpointer and the dependencies |
| `vault.py` | 234 | French pages, keyword search with excerpts, exact-quote check, apply an edit, leftovers sweep |
| `crosscheck.py` | 211 | Second reading of the corrections with the whole guide cached in context, then the sweep |
| `quotes.py` | 158 | Locates the passage a finding talks about: exact match, else the closest window of lines on normalised text |
| `fix.py` | 135 | Turns findings into proposals, then into an initial state that enters the graph after `propose` |
| `evaluate.py` | 126 | Hunks of the human's merged diff vs. the agent's proposals, matched by a judge model |
| `llm.py` | 121 | Structured output, prompt caching, server-side web search and fetch, cost journal |
| `state.py` | 116 | `WatchState` and the Pydantic schemas the model must answer with |
| `prompts.py` | 79 | System prompts built from the guide's own editorial brief and translation policy |
| `inputs.py` | 65 | Watch issue and artifact (`gh`), items, freshness claims due |
| `costs.py` | 63 | Totals of `metrics/usage.jsonl` by month, year, run or step |
| `notify.py` | 47 | Windows toast notifications for `serve --notify` |

## The graph, node by node

```mermaid
flowchart TB
  subgraph g["graph.py · build(deps)"]
    direction TB
    collect --> triage --> locate
    locate -. "fan_out → Send" .-> propose
    propose --> number --> crosscheck --> report --> review
    review --> apply --> mirror --> audits --> links --> publish
  end
  collect -.-> I["inputs.download_watch<br/>inputs.load_items<br/>inputs.claims_due"]
  triage -.-> L1["llm.parse(TriageResult)<br/>prompts.triage"]
  locate -.-> V1["vault.search<br/>clusters()"]
  propose -.-> L2["llm.parse(ClusterProposal)<br/>prompts.propose"]
  number -.-> V2["vault.check<br/>mark_unsafe / mark_conflicts"]
  crosscheck -.-> C["crosscheck.run / sweep / amend<br/>vault.corpus · quotes.locate_all"]
  report -.-> R["render_report"]
  review -.-> P1["interrupt()"]
  apply -.-> V3["git worktree · vault.apply"]
  mirror -.-> L3["translator.parse(MirrorResult)<br/>prompts.mirror"]
  audits -.-> N["npm test (guide)"]
  links -.-> K["link_problems"]
  publish -.-> P2["interrupt() · git push · gh pr create"]
  classDef pause fill:#fff4d6,stroke:#a65f00,color:#3d2a00
  classDef model fill:#e2f1f6,stroke:#0a7ea4,color:#0b3a4a
  class review,publish,P1,P2 pause
  class triage,propose,crosscheck,mirror,L1,L2,L3,C model
```

`build(deps, checkpointer)` receives a `Deps` dataclass: the guide path, the model for the reasoning steps (`llm`),
the model for the English mirror (`translator`), whether to run the cross-check, the GitHub repository and base
branch, today's date. Nodes are closures over `deps`, so a test builds the same graph with fakes.

## The state that flows through it

`WatchState` ([`state.py`](../src/vault_watch_agent/state.py)) is a `TypedDict` of plain JSON values: a paused run is
serialised by the checkpointer as is. Each node returns only the keys it changes.

```mermaid
classDiagram
  direction LR
  class WatchState {
    <<TypedDict>>
    source, issue, as_of, items
    claims_due
    decisions, evidence
    proposals : list ⊕
    usage : list ⊕
    corrections, findings, leftovers
    report_path, accepted
    branch, worktree, applied, mirrored
    audit_ok, link_problems, pr_url
  }
  class TriageResult { decisions : TriageDecision[] }
  class TriageDecision { item_id, action, reason, search_terms }
  class ClusterProposal { outcomes : ItemOutcome[], corrections : Correction[] }
  class Correction { item_ids, page, current, proposed, source_url, severity, rationale, group }
  class CrossCheck { reviews : CorrectionReview[], consistency_edits : ConsistencyEdit[], other_findings : Noticed[] }
  class MirrorResult { edits : MirrorEdit[], problem }
  TriageResult *-- TriageDecision
  ClusterProposal *-- Correction
  WatchState ..> TriageResult : triage
  WatchState ..> ClusterProposal : propose
  WatchState ..> CrossCheck : crosscheck
  WatchState ..> MirrorResult : mirror
```

`⊕` marks the two keys with a reducer (`Annotated[list, operator.add]`): the parallel `propose` branches append their
proposals and their token usage instead of overwriting each other. The Pydantic classes are the `output_format` of
the model calls: an answer that does not validate is an error, not a guess.

## One model call, end to end

```mermaid
sequenceDiagram
  participant N as Node (e.g. propose)
  participant L as llm.Claude.parse
  participant A as Anthropic API
  participant J as metrics/usage.jsonl
  N->>L: system, prompt, schema=ClusterProposal, effort, node, context?, web?
  Note over L: context (whole guide) first,<br/>marked cache_control: ephemeral
  L->>A: messages.stream(output_format=schema, tools=[web_search, web_fetch]?)
  A-->>L: parsed output + usage (cache read / write, searches)
  loop server-side web tools paused (pause_turn), at most 5 times
    L->>A: continue the same message
  end
  Note over L: refusal or max_tokens → ModelError
  L->>J: one line: run, node, model, tokens, cost at list price
  L-->>N: (validated object, usage)
```

## How a run pauses and resumes

```mermaid
sequenceDiagram
  participant P1 as Process 1 (run)
  participant S as SqliteSaver<br/>checkpoints.sqlite
  participant P2 as Process 2 (days later)
  P1->>P1: graph.invoke(initial state, thread_id = "issue-69")
  P1->>S: checkpoint after every node
  P1->>P1: review node calls interrupt(report summary)
  P1-->>S: state + pending interrupt saved, process exits
  P2->>S: same thread_id
  P2->>P2: graph.invoke(Command(resume=["C1","C3"]))
  Note over P2: interrupt() returns the answer<br/>inside the review node
  P2->>P2: apply → mirror → audits → links → publish (second interrupt)
```

The CLI and the web page share the same SQLite file and the same thread ids, so a run started from one can be
finished from the other. The web server runs the graph in a background thread and streams
`graph.stream(stream_mode="updates")` to the page as server-sent events.

## Fix runs enter the graph in the middle

```mermaid
flowchart LR
  F["findings<br/>(reader, cross-check,<br/>on-demand check)"] --> FP["fix.propose /<br/>fix.propose_translation"]
  FP --> FS["fix.initial_state"]
  FS -->|"update_state(…, as_node='propose')"| number
  number --> crosscheck --> report --> review --> more["apply → … → publish"]
  classDef pause fill:#fff4d6,stroke:#a65f00,color:#3d2a00
  class review pause
```

A fix run makes its own proposals, then tells LangGraph they came out of `propose`: from `number` on, it is the same
graph, the same report, the same review and the same pull request as a watch. A translation fix sets
`mode = "translation"` and skips the French cross-check.

## Tests

| File | What it covers |
| :-- | :-- |
| [`tests/test_graph.py`](../tests/test_graph.py) | The whole graph with a `FakeLLM` answering per schema, on a throwaway git repository standing for the guide: both pauses, apply, mirror, PR text |
| [`tests/test_web.py`](../tests/test_web.py) | The FastAPI routes, background jobs, health contract |
| [`tests/test_quotes.py`](../tests/test_quotes.py) | Locating passages: exact match, closest window |
| [`tests/test_costs.py`](../tests/test_costs.py) | Cost journal totals |

No test calls the real API. `vault-watch eval` is the measure against real watches (results in
[`metrics/eval/`](../metrics/eval/)).

## Where to look first

1. [`state.py`](../src/vault_watch_agent/state.py): what a run knows at each step.
2. [`graph.py`](../src/vault_watch_agent/graph.py), `build()`: the nodes and the edges, then the node you care about.
3. [`llm.py`](../src/vault_watch_agent/llm.py): caching, web tools, cost journal, in about 120 lines.
4. [`vault.py`](../src/vault_watch_agent/vault.py), `check()` and `apply()`: why the model cannot damage a page.
5. [`web.py`](../src/vault_watch_agent/web.py) or [`cli.py`](../src/vault_watch_agent/cli.py): how runs are started,
   paused and resumed.

These pages also exist as HTML in `docs/`, to read a downloaded copy of the repository with its diagrams: they are
generated from the Markdown by [`docs/build_html.py`](build_html.py).
