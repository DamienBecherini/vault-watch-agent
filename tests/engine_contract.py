"""What any engine must do (llm.Engine), checked against recorded answers: no network, no model.

An engine's tests give an adapter: `make(scenario, journal)` returns the engine whose transport replays the recorded
answer of `scenario`, and `saw_web()` says whether the last call offered the model the web. Then:

    from engine_contract import check_engine
    check_engine(MyAdapter())

Scenarios: valid (the answer in the schema), invalid (an answer that is not), refusal, truncated (cut at the output
limit), web (the model searched before answering: at least one search counted). docs/write-an-engine.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import pytest
from pydantic import BaseModel

from vault_watch_agent import llm

SCENARIOS = ("valid", "invalid", "refusal", "truncated", "web")
FACTS = ["vLLM 0.33.1 fixes CVE-2026-1234", "released on 2026-11-12"]  # what every valid recorded answer says


class Answer(BaseModel):
    facts: list[str]


class Adapter(Protocol):
    def make(self, scenario: str, journal: Path) -> llm.Engine: ...
    def saw_web(self) -> bool: ...


def ask(engine: llm.Engine, web: bool = False):
    return engine.parse(system="Report the facts.", prompt="vLLM 0.33.1 release notes", schema=Answer, effort="high",
                        node="contract", web=web)


def check_engine(adapter: Adapter, tmp_path: Path) -> None:
    """Every rule of the contract, one scenario after the other."""
    journal = tmp_path / "usage.jsonl"

    # A valid answer: the object of the schema, and the usage of the call in the journal.
    engine = adapter.make("valid", journal)
    engine.run, engine.kind = "issue-1", "watch"
    answer, usage = ask(engine)
    assert isinstance(answer, Answer) and answer.facts == FACTS
    missing = [k for k in llm.USAGE_KEYS if k not in usage]
    assert not missing, f"usage lacks {missing}"
    assert usage["node"] == "contract" and usage["effort"] in llm.EFFORT_LEVELS
    assert isinstance(usage["cost_usd"], float) and usage["cost_usd"] >= 0
    assert all(isinstance(usage[k], int) and usage[k] >= 0 for k in ("input", "output", "cache_read", "cache_write"))
    lines = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1 and lines[0]["run"] == "issue-1" and lines[0]["kind"] == "watch"
    assert not adapter.saw_web()

    # What it says it can do.
    caps = engine.capabilities()
    assert isinstance(caps, llm.Capabilities) and caps.context > 0
    assert caps.web in ("native", "tools", "fetch", "none") and caps.billing in ("token", "subscription", "none")
    assert caps.structured in ("native", "instruction")

    # Wrong answers are errors that name the step, never a half-read object.
    for scenario, words in (("invalid", ()), ("refusal", ("refus",)), ("truncated", ())):
        with pytest.raises(llm.ModelError) as e:
            ask(adapter.make(scenario, journal))
        assert "contract" in str(e.value), f"{scenario}: the error does not name the step: {e.value}"
        assert all(w in str(e.value).lower() for w in words), f"{scenario}: {e.value}"

    # The web: offered only when asked, and the searches counted.
    answer, usage = ask(adapter.make("web", journal), web=True)
    assert answer.facts == FACTS and adapter.saw_web() and usage["web_searches"] >= 1
