*[Version française](write-an-engine.fr.md)*

# Write an engine

An engine is what calls a model for the agent. The agent ships three:

| Name | What it calls |
| :-- | :-- |
| `api` | the Claude API, billed per token |
| `claude-code` | Claude Code on a Claude subscription |
| `openai` | any OpenAI-compatible server, hosted or on your machine |

To reach another model, you can write an engine in a package of your own. The agent finds it when it is installed,
and its Settings then offer it like the others.

## What the graph asks of an engine

One method, `parse`, called once per step. It returns the model's answer as an object of the step's schema, and the
usage of the call.

```python
answer, usage = engine.parse(system=..., prompt=..., schema=Triage, effort="medium", node="triage",
                             context=None, web=False)
```

| Argument | What it is |
| :-- | :-- |
| `system`, `prompt` | The instructions and the request. |
| `schema` | A Pydantic model. The answer must validate against it: the graph never reads free text. |
| `effort` | `low` … `max`, as the step asks. Move it by `self.effort_step` with `shift_effort` (the role's effort in the Settings). |
| `node` | The step's name. Every error message starts with it. |
| `context` | A long text shared by several calls (the guide). Put it first so that a cache can reuse it. |
| `web` | The model may search the web and read pages before answering. |

The protocol is `llm.Engine`, and the contract below checks it. `parse` must:

- **Return** `(object, usage)`. `usage` holds at least `llm.USAGE_KEYS`: `node`, `model`, `engine`, `effort`, the
  tokens `input`, `output`, `cache_read` and `cache_write`, `web_searches` and `cost_usd` (0.0 when nothing is
  billed).
- **Write** that usage to the journal with `self.record(usage)`, through the `_Journal` base class. The Costs page
  and `vault-watch costs` read it.
- **Raise `llm.ModelError`**, never return half an answer, when:
  - the answer does not fit the schema;
  - the model refused, or its answer was cut;
  - the server cannot be reached.

`capabilities()` says what the steps can rely on. It returns an `llm.Capabilities`:

| Field | Values |
| :-- | :-- |
| `context` | The tokens a call can read. A guide bigger than this, less a reserve, is cross-checked chapter by chapter. |
| `structured` | `native` (the server enforces the schema) or `instruction` (the schema is in the prompt). |
| `web` | `native` (the provider's own tools), `tools` (the agent's search and page reading), `fetch` (pages only) or `none`. The steps that check on the web say what they lack. |
| `efforts` | The effort levels the engine sends; `()` when it sends none. |
| `billing` | `token`, `subscription` or `none` (a local model). The page shows the cost of an action accordingly. |
| `exact_count` | `True` when `count_tokens(text)` counts exactly; else the agent estimates. |

An engine without web of its own can still offer the web: `webtools.WebTools` and `webtools.Budget` give the search,
the page reading, the limits and the tool definitions. `openai_compat.py` shows the loop.

## Declaring it

An `llm.EngineKind` tells the agent how to make the engine and what it offers:

| Field | What it is |
| :-- | :-- |
| `name`, `label` | The name in `settings.json` (`"engine": "ollama"`) and the label in the Settings. |
| `make(role, journal, settings)` | The client of a role (`reasoning` or `translator`), on the model `settings` gives that role. It is called once more for each step the user set apart, with that step's model in place of the role's (in `settings["models"][role]`, and in your engine's own `models` option when it has one). |
| `models(settings)` | Optional. The models it offers: `[{id, name, context, priced}]`. |
| `check(options)` | Optional. It checks the engine's options (`settings["engines"]["<name>"]`), fills the defaults and raises on a wrong one. |
| `model_of(settings, role)` | The model of a role. |
| `options` | The defaults of its options. |
| `protocol` | The version of the engine protocol it implements: `1` (the default, `llm.ENGINE_PROTOCOL`). An engine of another protocol is not loaded ([compatibility.md](compatibility.md)). |

Point an entry point of the group `vault_watch_agent.engines` to it, in your package's `pyproject.toml`:

```toml
[project.entry-points."vault_watch_agent.engines"]
ollama = "ollama_engine:KIND"
```

`llm.engines()` loads it at start. If an engine cannot be loaded, the Settings report it and the agent goes on
without it.

## The example: Ollama's own API

[`examples/engines/ollama_engine.py`](../examples/engines/ollama_engine.py) is a whole engine in 90 lines, for
`POST /api/chat`:
- the schema goes in `format`, which Ollama enforces;
- the context opens the system message;
- the usage is read from `prompt_eval_count` and `eval_count`;
- it has no web, and nothing is billed.

It is an example: Ollama also speaks the OpenAI protocol, so the `openai` engine already reaches it.

## The contract tests

[`tests/engine_contract.py`](../tests/engine_contract.py) checks an engine against recorded answers, with no
network and no model:

| Scenario | What the engine must do |
| :-- | :-- |
| valid | Return the object, and the usage with its keys in the journal. |
| invalid | Raise `ModelError` naming the step, for an answer that does not fit the schema. |
| refusal | Raise `ModelError` naming the step. |
| truncated | Raise `ModelError` naming the step, for an answer cut at the output limit. |
| web | Offer the web only when asked, and count the searches. Skipped for an engine whose `web` is `none`. |

For a refusal, a server that signals it (a stop reason, a `refusal` field) gets an error saying so. Otherwise the
refusal arrives as text, which does not fit the schema.

Write an adapter that replays your server's answers, then call `check_engine`:

```python
from engine_contract import check_engine

class MyAdapter:
    def make(self, scenario, journal):      # the engine, its transport replaying `scenario`
        ...
    def saw_web(self):                      # whether the last call offered the model the web
        ...

def test_my_engine(tmp_path):
    check_engine(MyAdapter(), tmp_path)
```

[`tests/test_engine_contract.py`](../tests/test_engine_contract.py) has the adapters of the agent's engines and of
the example. They replace:
- the SDK client, for `api`;
- `claude -p`, for `claude-code`;
- the HTTP transport (`httpx.MockTransport`), for `openai` and the Ollama example.
