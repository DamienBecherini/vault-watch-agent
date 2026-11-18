"""The OpenAI-compatible engine: any server that speaks `POST /v1/chat/completions` (a hosted provider, or a model on
your own machine with llama.cpp, vLLM, Ollama, LM Studio).

    client = OpenAICompatible("qwen3.6", options, journal)   # options: the Settings' engines.openai (OPTIONS below)
    answer, usage = client.parse(system=..., prompt=..., schema=Triage, effort="medium", node="triage")

Structured output: `response_format` with the JSON schema when the server takes it, else the schema in the
instructions and a tolerant reading of the answer (`structured = "auto"` tries the first and falls back for good).
Web: the model has none of its own; with `web=True` it calls `web_search` and `web_fetch`, which the agent runs
(webtools.py), within the same limits as the API engine. The answer is then asked as JSON without the tools, so that
a server that cannot mix a grammar and tool calls still gives it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from . import config
from .llm import Capabilities, ModelError, _Journal, shift_effort
from .webtools import Budget, WebTools

T = TypeVar("T", bound=BaseModel)

NAME = "openai"
OPTIONS = {
    "base_url": "",            # e.g. http://127.0.0.1:8080/v1 (llama.cpp), https://openrouter.ai/api/v1
    "key": "",                 # a reference (env:, sops:, file:), "" for a server without a key
    "models": {"reasoning": "", "translator": ""},
    "context": 131072,         # the model's input window, when the server does not say it
    "max_output": 16384,       # tokens of an answer
    "structured": "auto",      # auto | native (response_format) | instruction (the schema in the prompt)
    "billing": "token",        # token: priced by the price table (set the model's price); local: nothing billed
    "effort": False,           # send reasoning_effort (low, medium, high): only for the models that take it
    "timeout": 1800,           # seconds for one request
    "searxng": "",             # the SearXNG address for web_search; without it the model only reads pages
}
STRUCTURED = ("auto", "native", "instruction")
BILLING = ("token", "local")
MAX_ROUNDS = 80  # tool calls answered in one parse, a guard against a model that never stops


def check_options(given) -> dict:
    """The options of the engine with every key, or ConfigError naming the wrong one."""
    if given is None:
        given = {}
    if not isinstance(given, dict):
        raise config.ConfigError("engines.openai must be an object")
    unknown = set(given) - set(OPTIONS)
    if unknown:
        raise config.ConfigError(f"engines.openai: unknown {', '.join(sorted(unknown))}")
    out = {**OPTIONS, **{k: v for k, v in given.items() if v is not None}}
    out["base_url"] = str(out["base_url"] or "").strip().rstrip("/")
    if out["base_url"] and not re.match(r"https?://", out["base_url"]):
        raise config.ConfigError("engines.openai.base_url: an http(s) address, such as http://127.0.0.1:8080/v1")
    out["key"] = str(out["key"] or "").strip()
    if out["key"] and not out["key"].startswith(config.REFERENCES):
        raise config.ConfigError(f"engines.openai.key: a reference ({config.KEY_FORMS}), never the key itself")
    models = out["models"] if isinstance(out["models"], dict) else {}
    out["models"] = {role: str(models.get(role) or "").strip() for role in ("reasoning", "translator")}
    for role, model in out["models"].items():
        if model and not config.ANY_MODEL_ID.fullmatch(model):
            raise config.ConfigError(f"engines.openai.models.{role}: {model!r} is not a model id")
    for key, low in (("context", 4096), ("max_output", 256), ("timeout", 10)):
        if isinstance(out[key], bool) or not isinstance(out[key], int) or out[key] < low:
            raise config.ConfigError(f"engines.openai.{key}: a whole number, {low} or more")
    if out["structured"] not in STRUCTURED:
        raise config.ConfigError(f"engines.openai.structured: one of {', '.join(STRUCTURED)}")
    if out["billing"] not in BILLING:
        raise config.ConfigError(f"engines.openai.billing: one of {', '.join(BILLING)}")
    out["effort"] = bool(out["effort"])
    out["searxng"] = str(out["searxng"] or "").strip().rstrip("/")
    if out["searxng"] and not re.match(r"https?://", out["searxng"]):
        raise config.ConfigError("engines.openai.searxng: an http(s) address")
    return out


def _client(options: dict, http: httpx.Client | None) -> httpx.Client:
    """The HTTP client of the server, its key from its reference; the tests give theirs (with a base_url)."""
    if http is not None:
        return http
    headers = {}
    try:
        key = config.resolve_key(options["key"])
    except config.ConfigError as e:
        raise ModelError(f"key of the OpenAI-compatible server: {e}") from e
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return httpx.Client(base_url=options["base_url"], headers=headers, timeout=options["timeout"])


def json_of(text: str):
    """The JSON object of an answer given as text: as it is, or inside a ``` block, or the first {...} of it."""
    text = (text or "").strip()
    text = re.sub(r"^<think>[\s\S]*?</think>\s*", "", text)  # reasoning models that write their thoughts first
    for candidate in (text, *(m.group(1) for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text))):
        try:
            return json.loads(candidate)
        except ValueError:
            pass
    start = text.find("{")
    while start != -1:
        depth, in_str, escape = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                escape = c == "\\" and not escape
                if c == '"' and not escape:
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except ValueError:
                        break
        start = text.find("{", start + 1)
    raise ValueError("no JSON object in the answer")


class OpenAICompatible(_Journal):
    """A model behind an OpenAI-compatible server."""

    def __init__(self, model: str, options: dict, journal: Path | None = None, http: httpx.Client | None = None,
                 web: WebTools | None = None):
        super().__init__(model, journal)
        self.options = check_options(options)
        if not self.options["base_url"] and http is None:
            raise ModelError("the OpenAI-compatible engine has no server address (Settings, engine)")
        if not model:
            raise ModelError("the OpenAI-compatible engine has no model for this role (Settings, engine)")
        self.http = _client(self.options, http)
        self.web = web or WebTools(self.options["searxng"])
        self.structured = self.options["structured"]  # auto becomes native or instruction at the first answer

    def capabilities(self) -> Capabilities:
        return Capabilities(
            context=self.options["context"],
            structured="instruction" if self.structured == "instruction" else "native",
            web="tools" if self.web.can_search else "fetch",
            web_reading="page",
            efforts=("low", "medium", "high") if self.options["effort"] else (),
            caching=False,
            billing="none" if self.options["billing"] == "local" else "token",
        )

    # -- one request ----------------------------------------------------------------------------------------------

    def _post(self, body: dict, node: str) -> dict:
        try:
            r = self.http.post("/chat/completions", json=body)
        except httpx.TimeoutException as e:
            raise ModelError(f"{node}: the server did not answer in {self.options['timeout']} s") from e
        except httpx.HTTPError as e:
            raise ModelError(f"{node}: the server could not be reached ({type(e).__name__})") from e
        if r.status_code != 200:
            raise _HTTPError(r.status_code, r.text[:500])
        try:
            return r.json()
        except ValueError as e:
            raise ModelError(f"{node}: the server did not answer JSON") from e

    def _schema_format(self, schema: type[BaseModel]) -> dict:
        return {"type": "json_schema", "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema(),
                                                       "strict": False}}

    def _ask(self, body: dict, schema: type[BaseModel], node: str, with_format: bool) -> dict:
        """One request; with `with_format` and the server refusing response_format (auto), falls back to the schema
        in the instructions for this client's life."""
        if with_format and self.structured != "instruction":
            body = {**body, "response_format": self._schema_format(schema)}
        try:
            return self._post(body, node)
        except _HTTPError as e:
            # Any refusal of a request with a schema, in auto: the schema goes into the instructions (servers word it
            # their own way; Anthropic's OpenAI layer only takes strict schemas). Another cause fails again below.
            if with_format and self.structured == "auto" and e.status in (400, 422, 501):
                self.structured = "instruction"
                body = {k: v for k, v in body.items() if k != "response_format"}
                body["messages"] = _with_schema(body["messages"], schema)
                return self._post(body, node)
            raise ModelError(f"{node}: the server answered HTTP {e.status}: {e.text[:300]}") from e

    # -- the protocol ---------------------------------------------------------------------------------------------

    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str,
              context: str | None = None, web: bool = False) -> tuple[T, dict]:
        """Same contract as `Claude.parse`. `context` opens the system message (servers that cache a prompt's prefix
        read it from their cache on the next calls); the instructions follow it."""
        effort = shift_effort(effort, self.effort_step)
        system_text = f"{context}\n\n{system}" if context else system
        messages: list[dict] = [{"role": "system", "content": system_text}, {"role": "user", "content": prompt}]
        if self.structured == "instruction" or web:
            messages = _with_schema(messages, schema)
        body: dict = {"model": self.model, "max_tokens": self.options["max_output"]}
        if self.options["effort"]:
            body["reasoning_effort"] = {"xhigh": "high", "max": "high"}.get(effort, effort)
        totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "web_searches": 0, "web_fetches": 0}
        budget = Budget()

        if web:  # the model reads the web through the agent, then answers
            tools = budget.tools(self.web)
            for _ in range(MAX_ROUNDS):
                data = self._ask({**body, "messages": messages, "tools": tools}, schema, node, with_format=False)
                choice = self._count(data, totals, node)
                calls = (choice.get("message") or {}).get("tool_calls") or []
                if not calls:
                    break
                messages.append({"role": "assistant", "content": choice["message"].get("content") or "",
                                 "tool_calls": calls})
                for call in calls:
                    fn = call.get("function") or {}
                    try:
                        arguments = json.loads(fn.get("arguments") or "{}")
                    except ValueError:
                        arguments = {}
                    messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                     "content": budget.run(self.web, fn.get("name", ""), arguments)})
            else:
                raise ModelError(f"{node}: more than {MAX_ROUNDS} rounds of tool calls")
            totals["web_searches"], totals["web_fetches"] = budget.searches, budget.pages
            text = (choice.get("message") or {}).get("content") or ""
            parsed = self._read(text, schema)
            if parsed is None:  # its answer was not the JSON: ask for it, without the tools
                messages += [{"role": "assistant", "content": text},
                             {"role": "user", "content": "Give your final answer now: one JSON object that follows "
                                                         "the schema, nothing else."}]
                data = self._ask({**body, "messages": messages}, schema, node, with_format=True)
                choice = self._count(data, totals, node)
                parsed = self._read((choice.get("message") or {}).get("content") or "", schema)
        else:
            data = self._ask({**body, "messages": messages}, schema, node, with_format=True)
            choice = self._count(data, totals, node)
            parsed = self._read((choice.get("message") or {}).get("content") or "", schema)
        if parsed is None:
            raise ModelError(f"{node}: answer not in the expected shape")
        if self.structured == "auto":
            self.structured = "native"

        usage = {"node": node, "model": data.get("model") or self.model, "engine": NAME, "effort": effort, **totals}
        if self.options["billing"] == "local":
            usage.update(cost_usd=0.0, price=None, price_origin="local")
        else:
            usd, price = self.prices.cost({**usage, "model": self.model})
            usage.update(cost_usd=round(usd, 6), price=price.rates() if price else None,
                         price_origin=price.label if price else "no price")
        self.record(usage)
        return parsed, usage

    def _count(self, data: dict, totals: dict, node: str) -> dict:
        """Adds the usage of a response to `totals` and returns its first choice; ModelError for a refusal or a cut."""
        u = data.get("usage") or {}
        cached = int(((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0)
        totals["input"] += max(0, int(u.get("prompt_tokens") or 0) - cached)
        totals["cache_read"] += cached
        totals["output"] += int(u.get("completion_tokens") or 0)
        choices = data.get("choices") or []
        if not choices:
            raise ModelError(f"{node}: the server gave no answer")
        choice = choices[0]
        message = choice.get("message") or {}
        if message.get("refusal") or choice.get("finish_reason") == "content_filter":
            raise ModelError(f"{node}: refused ({str(message.get('refusal') or 'content filter')[:200]})")
        if choice.get("finish_reason") == "length":
            raise ModelError(f"{node}: output truncated at max_tokens ({self.options['max_output']})")
        return choice

    @staticmethod
    def _read(text: str, schema: type[T]) -> T | None:
        try:
            return schema.model_validate(json_of(text))
        except (ValueError, ValidationError):
            return None


class _HTTPError(Exception):
    def __init__(self, status: int, text: str):
        super().__init__(f"HTTP {status}")
        self.status, self.text = status, text


def _with_schema(messages: list[dict], schema: type[BaseModel]) -> list[dict]:
    """The schema in the system message: the answer is one JSON object that follows it."""
    first = messages[0]
    if "Answer with one JSON object" in first["content"]:
        return messages
    rule = ("\n\nAnswer with one JSON object only, no text around it, that follows this JSON schema:\n"
            + json.dumps(schema.model_json_schema(), ensure_ascii=False))
    return [{**first, "content": first["content"] + rule}, *messages[1:]]


def list_models(options: dict, http: httpx.Client | None = None) -> list[dict]:
    """The models of the server (GET /models): {id, name, context, priced}. The window when the server gives it
    (vLLM max_model_len, OpenRouter context_length), else the Settings' `context`. ModelError when it cannot be read."""
    options = check_options(options)
    if not options["base_url"] and http is None:
        raise ModelError("no server address")
    client = _client(options, http)
    try:
        r = client.get("/models")
        found = r.json().get("data") if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError) as e:
        raise ModelError(f"the list of the models could not be read ({type(e).__name__})") from e
    if not isinstance(found, list):
        raise ModelError(f"the list of the models could not be read (HTTP {r.status_code})")
    return [{"id": m["id"], "name": m.get("name") or m["id"],
             "context": m.get("max_model_len") or m.get("context_length") or options["context"],
             "priced": options["billing"] == "local"}
            for m in found if isinstance(m, dict) and m.get("id")]

