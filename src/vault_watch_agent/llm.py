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


class ModelError(RuntimeError):
    pass


class LLM(Protocol):
    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str) -> tuple[T, dict]: ...


class Claude:
    def __init__(self, model: str = MODEL, client: anthropic.Anthropic | None = None, journal: Path | None = None):
        self.model = model
        self.journal = journal  # one JSON line per call with its cost, for spend tracking
        # Reads ANTHROPIC_API_KEY from the environment (injected by sops, never stored here).
        self.client = client or anthropic.Anthropic()

    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str) -> tuple[T, dict]:
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=32000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
            output_config={"effort": effort},
            # On a policy decline, the API re-runs the request on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            message = stream.get_final_message()
        if message.stop_reason == "refusal":
            category = message.stop_details.category if message.stop_details else None
            raise ModelError(f"{node}: refused ({category})")
        if message.stop_reason == "max_tokens":
            raise ModelError(f"{node}: output truncated at max_tokens")
        parsed = message.parsed_output
        if parsed is None:
            raise ModelError(f"{node}: no structured output")
        u = message.usage
        usage = {
            "node": node,
            "model": message.model,
            "input": u.input_tokens,
            "output": u.output_tokens,
            "cache_read": u.cache_read_input_tokens or 0,
            "cache_write": u.cache_creation_input_tokens or 0,
        }
        usage["cost_usd"] = round(cost(usage), 6)
        if self.journal:
            self.journal.parent.mkdir(parents=True, exist_ok=True)
            with open(self.journal, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                    "tool": "vault-watch-agent", **usage}) + "\n")
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
    return (usage["input"] * p_in + usage["output"] * p_out
            + usage.get("cache_read", 0) * p_read + usage.get("cache_write", 0) * p_write) / 1e6
