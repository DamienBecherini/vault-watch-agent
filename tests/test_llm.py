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
                           "schema": json.loads(option("--json-schema")), "tools": option("--tools"),
                           "mcp": json.loads(Path(option("--mcp-config")).read_text(encoding="utf-8")) if "--mcp-config" in command else None})
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
    # Its WebSearch, and the agent's page reader in place of its WebFetch (which reads the LAN): an MCP server of the agent
    assert call["schema"] == Answer.model_json_schema() and call["tools"] == "WebSearch"
    assert call["command"][call["command"].index("--disallowedTools") + 1] == "WebFetch"
    assert llm.FETCH_TOOL_NAME in call["command"][call["command"].index("--allowedTools") + 1]
    assert call["mcp"]["mcpServers"]["vw"]["args"] == ["-m", "vault_watch_agent.mcp_fetch"]
    for flag in ("-p", "--setting-sources", "--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"):
        assert flag in call["command"]
    assert call["command"][call["command"].index("--model") + 1] == "claude-opus-5-5"
    assert call["command"][call["command"].index("--effort") + 1] == "high"
    assert "ANTHROPIC_API_KEY" not in call["env"] and "CLAUDECODE" not in call["env"]  # nothing that would bill an API
    assert usage == {"node": "crosscheck", "model": "claude-opus-5-5", "engine": "claude-code", "effort": "high",
                     "input": 10, "output": 20,
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


@pytest.mark.parametrize("effort, step, expected", [
    ("medium", 0, "medium"), ("medium", 1, "high"), ("high", 1, "xhigh"), ("high", -1, "medium"),
    ("low", -1, "low"), ("max", 1, "max"),  # never beyond the ends
])
def test_the_effort_of_a_role_moves_each_step_one_level(effort, step, expected):
    assert llm.shift_effort(effort, step) == expected


def test_claude_code_runs_at_the_effort_of_its_role(claude):
    model = llm.ClaudeCode()
    model.effort_step = 1
    _, usage = ask(model)  # the step asks for high
    assert claude.calls[0]["command"][claude.calls[0]["command"].index("--effort") + 1] == "xhigh" and usage["effort"] == "xhigh"


class FakeModels:
    """Stands for `anthropic.Anthropic().models`: the Models API."""

    def __init__(self, error=None):
        self.error = error

    def list(self, limit=100):
        if self.error:
            raise self.error
        M = lambda id, name, day, deprecated=None: type("M", (), {"id": id, "display_name": name, "max_input_tokens": 1_000_000,
                                                                    "created_at": day, "deprecated_at": deprecated})()
        return [M("claude-haiku-5-5", "Claude Haiku 5.5", "2026-09-01"), M("claude-fable-5-2", "Claude Fable 5.2", "2026-10-20"),
                M("claude-sonnet-4-5", "Claude Sonnet 4.5", "2025-09-29", deprecated="2026-10-01"),
                M("claude-mythos-6", "Claude Mythos 6", "2026-11-10")]


def test_the_models_come_from_the_api_newest_first_with_their_price_known_or_not():
    client = type("C", (), {"models": FakeModels()})()
    models = llm.list_models("env:X", client)
    assert [m["id"] for m in models] == ["claude-mythos-6", "claude-fable-5-2", "claude-haiku-5-5"]  # the deprecated one left out
    assert [m["priced"] for m in models] == [False, True, True] and models[1]["name"] == "Claude Fable 5.2"


def test_engines_declare_what_they_can_do():
    llm.CONTEXTS.clear()
    api, cc = llm.Claude("claude-opus-5-5", client=object()), llm.ClaudeCode("claude-opus-5-5")
    assert (api.capabilities().context, api.capabilities().billing, api.capabilities().exact_count) == (1_000_000, "token", True)
    assert (cc.capabilities().billing, cc.capabilities().web_reading, cc.capabilities().exact_count) == ("subscription", "page", False)  # its pages through the agent's reader (mcp_fetch)
    assert llm.context_of("claude-mythos-7") == llm.UNKNOWN_CONTEXT  # unknown: the smaller window, never more
    assert llm.context_of("claude-sonnet-4-6-20260101") == llm.KNOWN_CONTEXT  # a dated id of a known model
    llm.CONTEXTS["claude-mythos-7"] = 2_000_000  # read from the Models API
    assert llm.Claude("claude-mythos-7", client=object()).capabilities().context == 2_000_000
    llm.CONTEXTS.clear()


def test_a_list_that_cannot_be_read_is_an_error():
    import anthropic

    client = type("C", (), {"models": FakeModels(anthropic.AnthropicError("no key"))})()
    with pytest.raises(llm.ModelError, match="could not be read"):
        llm.list_models("env:X", client)


def test_a_plug_in_engine_of_another_protocol_is_reported_not_loaded(monkeypatch):
    from types import SimpleNamespace

    from vault_watch_agent import llm as llm_mod

    good = llm_mod.EngineKind("mine", "Mine", lambda role, journal, settings: None)
    ahead = llm_mod.EngineKind("future", "Future", lambda role, journal, settings: None, protocol=2)
    points = [SimpleNamespace(name="mine", load=lambda: good), SimpleNamespace(name="future", load=lambda: ahead)]
    monkeypatch.setattr(llm_mod, "entry_points", lambda group: points)
    monkeypatch.setattr(llm_mod, "_engines", None)
    monkeypatch.setattr(llm_mod, "ENGINE_ERRORS", {})
    found = llm_mod.engines()
    assert "mine" in found and "future" not in found
    assert "engine protocol 2" in llm_mod.ENGINE_ERRORS["future"]
    monkeypatch.setattr(llm_mod, "_engines", None)  # the next test reads the real list again
