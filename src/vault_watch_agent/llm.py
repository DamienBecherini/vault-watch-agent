"""The only place that calls Claude.

Every call returns a validated Pydantic object (structured outputs), so the
graph never parses free text. Tests swap this class for a fake with the same
`parse` method.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, TypeVar

import anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Verification needs judgement: Opus. Mechanical work (translation, day 2): Sonnet.
MODEL = "claude-opus-5-5"
TRANSLATOR = "claude-sonnet-5-5"
MAX_CONTINUATIONS = 5  # server-side tool loops resumed after pause_turn
WEB_SEARCH_USD = 0.01  # 10 $ per 1,000 searches


class ModelError(RuntimeError):
    pass


class LLM(Protocol):
    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str,
              context: str | None = None) -> tuple[T, dict]: ...


class Claude:
    def __init__(self, model: str = MODEL, client: anthropic.Anthropic | None = None, journal: Path | None = None):
        self.model = model
        self.journal = journal  # one JSON line per call with its cost, for spend tracking
        self.run = ""  # run label written with each call (thread id), set by the caller
        self.kind = ""  # what the run does: watch, crosscheck…
        # Reads ANTHROPIC_API_KEY from the environment (injected by sops, never stored here).
        self.client = client or anthropic.Anthropic()

    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str,
              context: str | None = None, web: bool = False) -> tuple[T, dict]:
        """`context` (the whole vault, for instance) goes first and is cached, so the next calls
        within five minutes read it at the cache price instead of the full input price.
        `web` lets the model search the web and open sources (server-side tools run by the API)."""
        blocks = system
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
        for _ in range(MAX_CONTINUATIONS):
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=32000,
                system=blocks,
                messages=messages,
                output_format=schema,
                output_config={"effort": effort},
                # On a policy decline, the API re-runs the request on a fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **extra,
            ) as stream:
                message = stream.get_final_message()
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
        usage = {"node": node, "model": message.model, **totals}
        usage["cost_usd"] = round(cost(usage), 6)
        if self.journal:
            self.journal.parent.mkdir(parents=True, exist_ok=True)
            with open(self.journal, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                    "tool": "vault-watch-agent", "run": self.run, "kind": self.kind,
                                    **usage}) + "\n")
        return parsed, usage


# List prices, USD per million tokens: input, output, cache read, cache write (5-minute TTL = 1.25 × input).
PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.5),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}


def cost(usage: dict) -> float:
    model = next((m for m in PRICES if usage["model"].startswith(m)), None)
    if model is None:
        return 0.0
    p_in, p_out, p_read, p_write = PRICES[model]
    tokens = (usage["input"] * p_in + usage["output"] * p_out
              + usage.get("cache_read", 0) * p_read + usage.get("cache_write", 0) * p_write) / 1e6
    return tokens + usage.get("web_searches", 0) * WEB_SEARCH_USD  # web fetch is not billed beyond tokens
