"""An engine for Ollama's own API (`POST /api/chat`), the example of docs/write-an-engine.md.

Ollama also speaks the OpenAI protocol, so the agent's `openai` engine already reaches it; this one exists to show
what an engine is, in one file. tests/test_engine_contract.py checks it like the agent's own engines.

Packaged on its own, it is declared to the agent in its pyproject.toml:

    [project.entry-points."vault_watch_agent.engines"]
    ollama = "ollama_engine:KIND"
"""

from __future__ import annotations

from pathlib import Path

import httpx
from pydantic import BaseModel, ValidationError

from vault_watch_agent.llm import Capabilities, EngineKind, ModelError, _Journal, shift_effort

OPTIONS = {"url": "http://127.0.0.1:11434", "models": {"reasoning": "", "translator": ""}, "context": 32768}


class Ollama(_Journal):  # _Journal: the model, the labels of the run, the effort shift, the call journal
    def __init__(self, model: str, options: dict, journal: Path | None = None, http: httpx.Client | None = None):
        super().__init__(model, journal)
        self.options = {**OPTIONS, **options}
        self.http = http or httpx.Client(base_url=self.options["url"], timeout=1800)

    def capabilities(self) -> Capabilities:
        # The schema is enforced by Ollama (`format`); no web, no effort levels, nothing billed.
        return Capabilities(context=self.options["context"], web="none", efforts=(), caching=False, billing="none")

    def parse(self, *, system: str, prompt: str, schema: type[BaseModel], effort: str, node: str,
              context: str | None = None, web: bool = False):
        effort = shift_effort(effort, self.effort_step)  # recorded; Ollama has no effort to send
        body = {
            "model": self.model, "stream": False,
            "format": schema.model_json_schema(),  # the answer is constrained to this JSON schema
            "options": {"num_ctx": self.options["context"]},
            "messages": [{"role": "system", "content": f"{context}\n\n{system}" if context else system},
                         {"role": "user", "content": prompt}],
        }
        try:
            r = self.http.post("/api/chat", json=body)
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ModelError(f"{node}: Ollama could not be reached ({type(e).__name__})") from e
        if r.status_code != 200:
            raise ModelError(f"{node}: Ollama answered HTTP {r.status_code}: {str(data.get('error'))[:200]}")
        if data.get("done_reason") == "length":
            raise ModelError(f"{node}: output truncated at the context size")
        try:
            parsed = schema.model_validate_json((data.get("message") or {}).get("content") or "")
        except ValidationError as e:  # a refusal written as text lands here too: Ollama has no refusal signal
            raise ModelError(f"{node}: answer not in the expected shape ({e.error_count()} errors)") from e
        usage = {"node": node, "model": data.get("model") or self.model, "engine": "ollama", "effort": effort,
                 "input": int(data.get("prompt_eval_count") or 0), "output": int(data.get("eval_count") or 0),
                 "cache_read": 0, "cache_write": 0, "web_searches": 0, "cost_usd": 0.0}
        self.record(usage)  # one line in the journal: what the Costs page and `vault-watch costs` read
        return parsed, usage


def _check(options: dict) -> dict:
    unknown = set(options) - set(OPTIONS)
    if unknown:
        raise ValueError(f"engines.ollama: unknown {', '.join(sorted(unknown))}")
    return {**OPTIONS, **options}


def _models(settings: dict) -> list[dict]:
    options = {**OPTIONS, **(settings.get("engines") or {}).get("ollama", {})}
    try:
        tags = httpx.get(f"{options['url']}/api/tags", timeout=10).json().get("models") or []
    except (httpx.HTTPError, ValueError) as e:
        raise ModelError(f"the list of the models could not be read ({type(e).__name__})") from e
    return [{"id": m["name"], "name": m["name"], "context": options["context"], "priced": True} for m in tags]


def _options(settings: dict) -> dict:
    return (settings.get("engines") or {}).get("ollama") or {}


KIND = EngineKind(
    name="ollama", label="Ollama (native API)",
    make=lambda role, journal, settings: Ollama(_options(settings).get("models", {}).get(role, ""), _options(settings), journal),
    models=_models, check=_check,
    model_of=lambda settings, role: _options(settings).get("models", {}).get(role, ""),
    options=OPTIONS,
)
