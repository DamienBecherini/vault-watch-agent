"""The Claude Code engine, with `claude` replaced by a fake: the command it runs, what it reads back, what it refuses."""

import json
import subprocess
from pathlib import Path

import pytest
from pydantic import BaseModel

from vault_watch_agent import llm


class Answer(BaseModel):
    facts: list[str]


SUBSCRIPTION = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "pro"}
RESULT = {
    "type": "result", "subtype": "success", "is_error": False, "stop_reason": "tool_use", "total_cost_usd": 0.25,
    "structured_output": {"facts": ["a", "b"]}, "result": "{}",
    "usage": {"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 300, "cache_creation_input_tokens": 4000},
    "modelUsage": {"claude-opus-5-5": {"webSearchRequests": 2}, "claude-haiku-5-5": {"webSearchRequests": 0}},
}


class FakeClaude:
    """Stands for `subprocess.run`: answers `auth status` with `status`, a call with `result`, and keeps what it saw."""

    def __init__(self, status=SUBSCRIPTION, result=RESULT, stderr=""):
        self.status, self.result, self.stderr = status, result, stderr
        self.calls: list[dict] = []

    def __call__(self, command, **kw):
        if command[1:3] == ["auth", "status"]:
            return subprocess.CompletedProcess(command, 0, json.dumps(self.status).encode(), b"")
        option = lambda name: command[command.index(name) + 1]
        self.calls.append({"command": command, "env": kw["env"], "prompt": kw["input"].decode("utf-8"),
                           "instructions": Path(option("--system-prompt-file")).read_text(encoding="utf-8"),
                           "schema": json.loads(option("--json-schema")), "tools": option("--tools")})
        out = self.result if isinstance(self.result, str) else json.dumps(self.result)
        return subprocess.CompletedProcess(command, 0, out.encode(), self.stderr.encode())


@pytest.fixture
def claude(monkeypatch):
    fake = FakeClaude()
    monkeypatch.setattr(llm.subprocess, "run", fake)
    monkeypatch.setattr(llm, "claude_code_program", lambda: "claude")
    monkeypatch.setattr(llm, "_status", None)
    monkeypatch.delenv("VAULT_WATCH_ENGINE", raising=False)
    return fake


def ask(model=None, **kw):
    model = model or llm.ClaudeCode()
    return model.parse(system="Be exact.", prompt="Check « é ».", schema=Answer, effort="high", node="crosscheck", **kw)


def test_a_call_runs_claude_bare_and_reads_the_structured_answer(claude, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "would-be-billed")
    monkeypatch.setenv("CLAUDECODE", "1")
    model = llm.ClaudeCode(journal=tmp_path / "usage.jsonl")
    model.run, model.kind = "issue-70", "watch"
    parsed, usage = ask(model, context="<guide>…</guide>", web=True)
    assert parsed.facts == ["a", "b"]
    call = claude.calls[0]
    # The guide alone is the system prompt (one cached block); the instructions open the prompt.
    assert call["instructions"] == "<guide>…</guide>"
    assert call["prompt"] == "<instructions>\nBe exact.\n</instructions>\n\nCheck « é »."
    assert call["schema"] == Answer.model_json_schema() and call["tools"] == "WebSearch,WebFetch"
    for flag in ("-p", "--safe-mode", "--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"):
        assert flag in call["command"]
    assert call["command"][call["command"].index("--model") + 1] == "claude-opus-5-5"
    assert call["command"][call["command"].index("--effort") + 1] == "high"
    assert "ANTHROPIC_API_KEY" not in call["env"] and "CLAUDECODE" not in call["env"]  # nothing that would bill an API
    assert usage == {"node": "crosscheck", "model": "claude-opus-5-5", "engine": "claude-code", "input": 10, "output": 20,
                     "cache_read": 300, "cache_write": 4000, "web_searches": 2, "cost_usd": 0.0, "list_usd": 0.25}
    line = json.loads((tmp_path / "usage.jsonl").read_text(encoding="utf-8"))
    assert line["run"] == "issue-70" and line["kind"] == "watch" and line["cost_usd"] == 0.0 and line["engine"] == "claude-code"


def test_without_the_web_claude_code_has_no_tool(claude):
    ask()
    call = claude.calls[0]
    assert call["tools"] == "" and "--allowedTools" not in call["command"]
    assert call["instructions"] == "Be exact." and call["prompt"] == "Check « é »."  # no context: a plain system prompt


@pytest.mark.parametrize("status, word", [
    ({"loggedIn": False}, "not signed in"),
    ({"loggedIn": True, "authMethod": "console"}, "would be billed"),  # a Console account: refused, it would spend
])
def test_refused_unless_signed_in_with_a_subscription(claude, status, word):
    claude.status = status
    with pytest.raises(llm.ModelError, match=word):
        ask()
    assert claude.calls == []


@pytest.mark.parametrize("result, word", [
    ({**RESULT, "is_error": True, "result": "Claude AI usage limit reached|1763400000"}, "usage limit reached"),
    ({**RESULT, "subtype": "error_max_turns", "result": None}, "error_max_turns"),
    ({**RESULT, "stop_reason": "refusal"}, "refused"),
    ({**RESULT, "structured_output": None, "result": "not json"}, "no structured output"),
    ({**RESULT, "structured_output": {"facts": "one"}}, "expected shape"),
    ("claude: command crashed", "Claude Code failed"),
])
def test_a_failed_call_is_an_error_with_its_reason(claude, result, word):
    claude.result = result
    with pytest.raises(llm.ModelError, match=word):
        ask()


def test_an_answer_given_as_text_is_read_too(claude):
    claude.result = {**RESULT, "structured_output": None, "result": '{"facts": ["c"]}'}
    assert ask()[0].facts == ["c"]


def test_the_engine_is_claude_code_on_a_subscription_unless_told(claude, monkeypatch):
    assert llm.engine() == "claude-code" and isinstance(llm.create(), llm.ClaudeCode)
    monkeypatch.setenv("VAULT_WATCH_ENGINE", "api")
    assert llm.engine() == "api"
    monkeypatch.setenv("VAULT_WATCH_ENGINE", "gpt")
    with pytest.raises(llm.ModelError, match="expected one of"):
        llm.engine()


def test_without_a_subscription_the_engine_is_the_api(claude, monkeypatch):
    claude.status = {"loggedIn": True, "authMethod": "console"}
    assert llm.engine() == "api"
    monkeypatch.setenv("VAULT_WATCH_ENGINE", "claude-code")  # asked for anyway: the call itself refuses
    assert llm.engine() == "claude-code"
