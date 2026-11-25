"""The `api` engine: the Claude API through the official SDK, billed per token (an API key, injected by sops, never
stored here). Prompt caching of a shared context, the server-side web search and fetch, the output limits read from
the Models API."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import anthropic
from anthropic.types.beta import BetaTextBlockParam
from pydantic import ValidationError

from .. import config
from ..llm import CONTEXTS, MODEL, Capabilities, EngineKind, ModelError, T, _Journal, context_of, price_of, shift_effort
from ..prices import Prices

MAX_CONTINUATIONS = 5  # server-side tool loops resumed after pause_turn
# The most one request may write, thinking included: what the model accepts (`max_output`). It was 32 000 until
# 1.1.0, and the whole-guide checks wrote 27 to 29 k on Opus 5.5 at effort high. A cut answer is billed and lost:
# on 20/11/2026 the first compaction report on Fable 5.2 at effort high was cut at 64 000, most of it thinking.
MAX_TOKENS = 128_000  # the current Claude models
OUTPUTS: dict[str, int] = {}  # model id -> the most it writes, as the Models API gave it (list_models fills it)


def max_output(model: str) -> int:
    """The output limit of `model`: from the Models API when it was read, else what the agent knows."""
    return OUTPUTS.get(model) or (64_000 if model.startswith("claude-haiku-4") else MAX_TOKENS)


class Claude(_Journal):
    """The Claude API, billed per token."""

    def capabilities(self) -> Capabilities:
        # The API hands the fetched page to the model, and counts tokens exactly (messages.count_tokens).
        return Capabilities(context=context_of(self.model), exact_count=True)

    def count_tokens(self, text: str) -> int | None:
        """The tokens of `text` for this model (Token Counting API, not billed); None when it cannot be asked."""
        try:
            return self.client.messages.count_tokens(
                model=self.model, messages=[{"role": "user", "content": text}]).input_tokens
        except Exception:  # noqa: BLE001 - any failure: the caller estimates instead
            return None

    def __init__(self, model: str = MODEL, client: anthropic.Anthropic | None = None, journal: Path | None = None):
        super().__init__(model, journal)
        # Reads ANTHROPIC_API_KEY from the environment (injected by sops, never stored here).
        self.client = client or anthropic.Anthropic()

    signals_start = True  # `parse` takes `started` (optional, outside the engine protocol)

    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str,
              context: str | None = None, web: bool = False,
              started: Callable[[], None] | None = None) -> tuple[T, dict]:
        """`context` (the whole vault, for instance) goes first and is cached, so the next calls
        within five minutes read it at the cache price instead of the full input price.
        `web` lets the model search the web and open sources (server-side tools run by the API).
        `started` is called once the answer has begun: the cache of `context` can then be read, so calls that
        share it are started after that, not together (each would pay for writing it)."""
        level = shift_effort(effort, self.effort_step)
        blocks: str | list[BetaTextBlockParam] = system
        if context:
            blocks = [{"type": "text", "text": context, "cache_control": {"type": "ephemeral"}},
                      {"type": "text", "text": system}]
        extra = {}
        if web:
            extra["tools"] = [
                {"type": "web_search_20260209", "name": "web_search", "max_uses": 20},
                {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 30},
            ]
        messages: list = [{"role": "user", "content": prompt}]
        totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "web_searches": 0}
        limit = max_output(self.model)
        for _ in range(MAX_CONTINUATIONS):
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=limit,
                system=blocks,
                messages=messages,
                output_format=schema,
                output_config={"effort": level},
                # On a policy decline, the API re-runs the request on a fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **extra,
            ) as stream:
                try:
                    if started:
                        for event in stream:  # the first content: the answer has begun, the cache is written
                            if getattr(event, "type", "").startswith("content_block"):
                                break
                        started()
                        started = None
                    message = stream.get_final_message()
                except ValidationError as e:
                    raise self._cut(node, level, limit, totals, stream.current_message_snapshot.usage) from e
            u = message.usage
            totals["input"] += u.input_tokens
            totals["output"] += u.output_tokens
            totals["cache_read"] += u.cache_read_input_tokens or 0
            totals["cache_write"] += u.cache_creation_input_tokens or 0
            stu = getattr(u, "server_tool_use", None)
            totals["web_searches"] += (getattr(stu, "web_search_requests", 0) or 0) if stu else 0
            if message.stop_reason != "pause_turn":
                break
            # The server-side tool loop paused: send its turn back and it resumes where it stopped.
            messages = [messages[0], {"role": "assistant", "content": message.content}]
        if message.stop_reason == "refusal":
            category = message.stop_details.category if message.stop_details else None
            raise ModelError(f"{node}: refused ({category})")
        if message.stop_reason == "max_tokens":
            raise ModelError(f"{node}: output truncated at max_tokens")
        parsed = message.parsed_output
        if parsed is None:
            raise ModelError(f"{node}: no structured output")
        usage = {"node": node, "model": message.model, "engine": "api", "effort": level, **totals}
        self._priced(usage)
        self.record(usage)
        return parsed, usage

    def _priced(self, usage: dict) -> float:
        """The cost of a call added to its usage, with the price it was counted at: a past cost is never computed
        again with today's prices."""
        usd, price = self.prices.cost(usage)
        usage.update(cost_usd=round(usd, 6), price=price.rates() if price else None,
                     price_origin=price.label if price else "no price")
        return usd

    def _cut(self, node: str, effort: str, limit: int, totals: dict, u) -> ModelError:
        """An answer cut at the output limit. The SDK reads the JSON when its block ends: a cut answer is not JSON.
        The call is billed: it goes to the journal with what is known (the input as counted, the output at the
        limit), and the error carries it."""
        usage = {"node": node, "model": self.model, "engine": "api", "effort": effort, "cut": True,
                 "input": totals["input"] + u.input_tokens, "output": totals["output"] + limit,
                 "cache_read": totals["cache_read"] + (u.cache_read_input_tokens or 0),
                 "cache_write": totals["cache_write"] + (u.cache_creation_input_tokens or 0),
                 "web_searches": totals["web_searches"]}
        usd = self._priced(usage)
        self.record(usage)
        error = ModelError(f"{node}: the answer was cut before its end (the limit of {limit:,} output tokens, "
                           f"thinking included): billed ≈ {usd:.2f} $ and lost. Lower the effort of this step "
                           "or ask it for less.")
        error.usage = usage
        return error


def api_client(reference: str) -> anthropic.Anthropic:
    try:
        key = config.resolve_key(reference)
    except config.ConfigError as e:
        raise ModelError(f"API key: {e}") from e
    # No key from the reference: the SDK reads ANTHROPIC_API_KEY itself, and says so when there is none.
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()


_models: dict[str, tuple[float, list[dict]]] = {}  # reference of the key -> (time, models), asked again after 10 min


def list_models(reference: str, client: anthropic.Anthropic | None = None, prices: Prices | None = None) -> list[dict]:
    """The Claude models the API key of `reference` can use (Models API, GET /v1/models), newest first:
    {id, name, context, priced}; `priced`: the price table knows its price, so the journal and the estimates count it.
    Every current model, whatever its window: what a smaller one changes (the guide read by chapter) is the
    business of the steps (Capabilities), not of this list. The windows read here are kept for `context_of`.
    ModelError when the API cannot be asked (no key, network, refused)."""
    cached = _models.get(reference)
    if cached and time.monotonic() - cached[0] < 600 and client is None:
        return cached[1]
    try:
        found = list((client or api_client(reference)).models.list(limit=100))
    except anthropic.APIError as e:
        raise ModelError(f"the list of the models could not be read: {e.message if hasattr(e, 'message') else e}") from e
    except (anthropic.AnthropicError, TypeError) as e:  # no key at all (the SDK raises TypeError when it sends)
        raise ModelError(f"the list of the models could not be read: {e}") from e
    models: list[dict] = [{"id": m.id, "name": m.display_name or m.id, "context": m.max_input_tokens,
                           "priced": price_of(m.id, prices) is not None}
                          for m in sorted(found, key=lambda m: m.created_at, reverse=True)
                          if m.id.startswith("claude-") and not getattr(m, "deprecated_at", None)]
    CONTEXTS.update({m["id"]: m["context"] for m in models if m["context"]})
    OUTPUTS.update({m.id: most for m in found if (most := getattr(m, "max_tokens", None))})
    _models[reference] = (time.monotonic(), models)
    return models


def _make(role: str, journal: Path | None, settings: dict) -> Claude:
    return Claude(settings["models"][role], api_client(settings["key"]), journal)


KIND = EngineKind("api", "Claude API", _make, models=lambda settings: list_models(settings["key"]))
