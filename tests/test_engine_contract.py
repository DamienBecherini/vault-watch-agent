"""The three engines of the agent against the contract (engine_contract.py), each with its recorded answers."""

import json
import subprocess
from types import SimpleNamespace

import httpx
from engine_contract import FACTS, Answer, check_engine

from vault_watch_agent import llm
from vault_watch_agent.openai_compat import OpenAICompatible

# -- the Claude API: a fake SDK client replaying a final message per scenario ------------------------------------


def _message(scenario: str):
    usage = SimpleNamespace(input_tokens=1200, output_tokens=300, cache_read_input_tokens=0, cache_creation_input_tokens=0,
                            server_tool_use=SimpleNamespace(web_search_requests=3 if scenario == "web" else 0))
    stop = {"refusal": "refusal", "truncated": "max_tokens"}.get(scenario, "end_turn")
    parsed = None if scenario == "invalid" else Answer(facts=FACTS)
    return SimpleNamespace(stop_reason=stop, stop_details=SimpleNamespace(category="cyber"), parsed_output=parsed,
                           model="claude-opus-5-5", content=[], usage=usage)


class ApiAdapter:
    def __init__(self):
        self.request: dict = {}

    def make(self, scenario, journal):
        adapter = self

        class Stream:
            def __init__(self, **kw):
                adapter.request = kw

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get_final_message(self):
                return _message(scenario)

        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: Stream(**kw))))
        return llm.Claude("claude-opus-5-5", client, journal)

    def saw_web(self):
        return bool(self.request.get("tools"))


def test_the_api_engine_keeps_the_contract(tmp_path):
    check_engine(ApiAdapter(), tmp_path)


def test_an_answer_cut_at_the_output_limit_is_counted_and_said(tmp_path):
    """The SDK fails while reading a JSON cut at the limit (20/11/2026, Fable 5.2 at effort high): the call is
    billed, so it goes to the journal, and the error says what it cost."""
    import pytest
    from pydantic import TypeAdapter, ValidationError

    request = {}

    class Stream:
        current_message_snapshot = SimpleNamespace(usage=SimpleNamespace(
            input_tokens=300, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=400_000))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            TypeAdapter(Answer).validate_json('{"facts": ["a", ')  # what the SDK does with the cut text

    def stream(**kw):
        request.update(kw)
        return Stream()

    journal = tmp_path / "usage.jsonl"
    client = llm.Claude("claude-fable-5-2", SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream))), journal)
    with pytest.raises(llm.ModelError, match="cut before its end .*128,000 output tokens") as caught:
        client.parse(system="s", prompt="p", schema=Answer, effort="high", node="verify compaction")
    assert not isinstance(caught.value, ValidationError) and request["max_tokens"] == 128_000  # the model's own limit
    line = json.loads(journal.read_text(encoding="utf-8"))
    assert line["cut"] and line["output"] == 128_000 and line["cache_write"] == 400_000
    assert line["cost_usd"] == caught.value.usage["cost_usd"] == pytest.approx(400_000 * 10 / 1e6 + 128_000 * 40 / 1e6 + 300 * 8 / 1e6)
    assert llm.max_output("claude-haiku-4-5") == 64_000 and llm.max_output("claude-opus-5-5") == 128_000
    llm.OUTPUTS["claude-opus-5-5"] = 96_000  # read from the Models API: it wins
    try:
        assert llm.max_output("claude-opus-5-5") == 96_000
    finally:
        del llm.OUTPUTS["claude-opus-5-5"]


def test_the_api_engine_says_when_its_answer_begins(tmp_path):
    """Calls that share a cached context wait for this before they start (compact.propose)."""
    seen = []

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def __iter__(self):
            for kind in ("message_start", "content_block_start", "content_block_delta", "message_stop"):
                seen.append(kind)
                yield SimpleNamespace(type=kind)

        def get_final_message(self):
            seen.append("final")
            return _message("valid")

    client = llm.Claude("claude-opus-5-5", SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: Stream()))),
                        tmp_path / "usage.jsonl")
    answer, usage = client.parse(system="s", prompt="p", schema=Answer, effort="high", node="compact 1/2", context="guide",
                                 started=lambda: seen.append("started"))
    assert seen == ["message_start", "content_block_start", "started", "final"] and answer.facts == FACTS
    assert llm.Claude.signals_start and not getattr(llm.ClaudeCode, "signals_start", False)


# -- Claude Code: `claude -p` replaced by a fake replaying its JSON result per scenario ---------------------------

SUBSCRIPTION = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"}


def _result(scenario: str) -> dict:
    out = {"type": "result", "subtype": "success", "is_error": False, "stop_reason": "end_turn", "total_cost_usd": 0.4,
           "structured_output": {"facts": FACTS}, "result": "",
           "usage": {"input_tokens": 1200, "output_tokens": 300, "cache_read_input_tokens": 0,
                     "cache_creation_input_tokens": 0},
           "modelUsage": {"claude-opus-5-5": {"webSearchRequests": 2 if scenario == "web" else 0}}}
    if scenario == "invalid":
        out.update(structured_output={"facts": "not a list"})
    elif scenario == "refusal":
        out.update(stop_reason="refusal")
    elif scenario == "truncated":
        out.update(is_error=True, subtype="error_during_execution",
                   result="Claude's response exceeded the 32000 output token maximum")
    return out


class ClaudeCodeAdapter:
    def __init__(self, monkeypatch):
        self.monkeypatch, self.tools = monkeypatch, ""
        monkeypatch.setattr(llm, "claude_code_program", lambda: "claude")
        monkeypatch.setattr(llm, "_status", None)

    def make(self, scenario, journal):
        def run(command, **kw):
            if command[1:3] == ["auth", "status"]:
                return subprocess.CompletedProcess(command, 0, json.dumps(SUBSCRIPTION).encode(), b"")
            self.tools = command[command.index("--tools") + 1]
            return subprocess.CompletedProcess(command, 0, json.dumps(_result(scenario)).encode(), b"")

        self.monkeypatch.setattr(llm.subprocess, "run", run)
        return llm.ClaudeCode("claude-opus-5-5", journal)

    def saw_web(self):
        return "WebSearch" in self.tools


def test_the_claude_code_engine_keeps_the_contract(tmp_path, monkeypatch):
    check_engine(ClaudeCodeAdapter(monkeypatch), tmp_path)


# -- an OpenAI-compatible server: an HTTP transport replaying /chat/completions per scenario ----------------------

def _completion(content="", finish="stop", tool_calls=None, refusal=None, prompt=1200, cached=0):
    message = {"role": "assistant", "content": content, "refusal": refusal}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"id": "x", "model": "qwen3.6", "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": 300, "prompt_tokens_details": {"cached_tokens": cached}}}


class FakeWeb:
    can_search = True

    def __init__(self):
        self.searches = []

    def search(self, query):
        self.searches.append(query)
        return "1. vLLM v0.33.1\n   https://github.com/vllm-project/vllm/releases/tag/v0.33.1\n   Fixes CVE-2026-1234"

    def fetch(self, url):
        return f"Source: {url}\n\nRelease notes"


class OpenAIAdapter:
    def __init__(self):
        self.requests: list[dict] = []

    def make(self, scenario, journal):
        answer = json.dumps({"facts": FACTS})

        def handle(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            self.requests.append(body)
            if scenario == "web" and not any(m["role"] == "tool" for m in body["messages"]):
                call = {"id": "c1", "type": "function",
                        "function": {"name": "web_search", "arguments": json.dumps({"query": "vLLM 0.33.1"})}}
                return httpx.Response(200, json=_completion(finish="tool_calls", tool_calls=[call]))
            return httpx.Response(200, json={
                "valid": _completion(answer), "web": _completion(f"Here it is:\n```json\n{answer}\n```"),
                "invalid": _completion('{"facts": "not a list"}'),
                "refusal": _completion(refusal="I can't help with that."),
                "truncated": _completion('{"facts": ["vLLM', finish="length"),
            }[scenario])

        self.requests = []
        http = httpx.Client(transport=httpx.MockTransport(handle), base_url="http://server.test/v1")
        return OpenAICompatible("qwen3.6", {"base_url": "http://server.test/v1", "models": {"reasoning": "qwen3.6"},
                                            "billing": "local"}, journal, http=http, web=FakeWeb())

    def saw_web(self):
        return any(r.get("tools") for r in self.requests)


def test_the_openai_compatible_engine_keeps_the_contract(tmp_path):
    check_engine(OpenAIAdapter(), tmp_path)


# -- the example of docs/write-an-engine.md: Ollama's own API ----------------------------------------------------

def _ollama(scenario: str) -> dict:
    content = {"valid": json.dumps({"facts": FACTS}), "invalid": '{"facts": "not a list"}',
               "refusal": "I can't help with that.", "truncated": '{"facts": ["vLLM'}[scenario]
    return {"model": "qwen3.6", "message": {"role": "assistant", "content": content}, "done": True,
            "done_reason": "length" if scenario == "truncated" else "stop", "prompt_eval_count": 1200, "eval_count": 300}


class OllamaAdapter:
    def __init__(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).parents[1] / "examples" / "engines" / "ollama_engine.py"
        spec = importlib.util.spec_from_file_location("ollama_engine", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def make(self, scenario, journal):
        def handle(request):
            assert request.url.path == "/api/chat" and json.loads(request.content)["format"]["type"] == "object"
            return httpx.Response(200, json=_ollama(scenario))

        http = httpx.Client(transport=httpx.MockTransport(handle), base_url="http://ollama.test")
        return self.module.Ollama("qwen3.6", {}, journal, http=http)

    def saw_web(self):
        return False


def test_the_example_engine_of_the_docs_keeps_the_contract(tmp_path):
    adapter = OllamaAdapter()
    check_engine(adapter, tmp_path)
    assert adapter.module.KIND.name == "ollama" and adapter.module.KIND.check({})["context"] == 32768
