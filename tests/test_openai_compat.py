"""The OpenAI-compatible engine and the web tools it runs, against fake servers (httpx.MockTransport)."""

import json

import httpx
import pytest
from pydantic import BaseModel

from vault_watch_agent import config, llm, webtools
from vault_watch_agent.openai_compat import OpenAICompatible, check_options, json_of, list_models


class Answer(BaseModel):
    facts: list[str]


def server(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://server.test/v1")


def completion(content, prompt=100, cached=0):
    return {"model": "m", "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": 10, "prompt_tokens_details": {"cached_tokens": cached}}}


def test_a_server_without_json_schema_gets_the_schema_in_the_instructions_from_then_on(tmp_path):
    seen = []

    def handle(request):
        body = json.loads(request.content)
        seen.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": "response_format json_schema is not supported"})
        return httpx.Response(200, json=completion('Sure! {"facts": ["a"]}'))

    engine = OpenAICompatible("m", {"base_url": "http://server.test/v1"}, tmp_path / "u.jsonl", http=server(handle))
    answer, _ = engine.parse(system="S", prompt="P", schema=Answer, effort="high", node="triage")
    assert answer.facts == ["a"] and engine.structured == "instruction"
    assert "Answer with one JSON object" in seen[-1]["messages"][0]["content"]
    engine.parse(system="S", prompt="P", schema=Answer, effort="high", node="triage")
    assert "response_format" not in seen[-1]  # not asked again


def test_the_context_opens_the_system_message_and_the_cache_is_counted_apart(tmp_path):
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=completion('{"facts": []}', prompt=1000, cached=800))

    engine = OpenAICompatible("m", {"base_url": "http://server.test/v1", "effort": True}, None, http=server(handle))
    _, usage = engine.parse(system="Instructions", prompt="P", schema=Answer, effort="max", node="crosscheck",
                            context="<guide>…</guide>")
    assert seen[0]["messages"][0]["content"].startswith("<guide>…</guide>\n\nInstructions")
    assert seen[0]["reasoning_effort"] == "high" and seen[0]["response_format"]["type"] == "json_schema"
    assert (usage["input"], usage["cache_read"], usage["engine"]) == (200, 800, "openai")
    assert usage["price_origin"] == "no price"  # a hosted model without a price in the table: counted 0, said so


@pytest.mark.parametrize("text", ['{"facts": ["a"]}', '<think>hmm {"x": 1}</think>\n{"facts": ["a"]}',
                                  'Here:\n```json\n{"facts": ["a"]}\n```', 'The answer is {"facts": ["a"]}. Done.'])
def test_an_answer_written_as_text_is_read(text):
    assert json_of(text) == {"facts": ["a"]}


def test_the_options_are_checked():
    assert check_options({"base_url": "http://127.0.0.1:8080/v1/", "models": {"reasoning": "Qwen/Qwen3.6:q4"}})["base_url"] \
        == "http://127.0.0.1:8080/v1"
    for wrong, word in (({"key": "sk-plain"}, "never the key"), ({"structured": "xml"}, "structured"),
                        ({"context": 10}, "context"), ({"base_url": "server:8080"}, "base_url"), ({"nope": 1}, "unknown")):
        with pytest.raises(config.ConfigError, match=word):
            check_options(wrong)
    saved = config.check({"engine": "openai", "engines": {"openai": {"base_url": "http://h/v1"}}})
    assert saved["engine"] == "openai" and saved["engines"]["openai"]["context"] == 131072


def test_the_models_and_their_window_come_from_the_server():
    def handle(request):
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": "qwen3.6", "max_model_len": 65536}, {"id": "other"}]})

    models = list_models({"base_url": "http://server.test/v1", "context": 32768}, http=server(handle))
    assert [(m["id"], m["context"]) for m in models] == [("qwen3.6", 65536), ("other", 32768)]


def test_the_registry_and_the_settings_choose_the_engine(monkeypatch):
    monkeypatch.delenv("VAULT_WATCH_ENGINE", raising=False)
    assert {"api", "claude-code", "openai"} <= set(llm.engines())
    settings = config.check({"engine": "openai", "engines": {"openai": {"base_url": "http://h/v1",
                                                                        "models": {"reasoning": "big", "translator": "small"}}}})
    assert llm.model_of(settings, "translator") == "small"
    client = llm.create("reasoning", None, settings)
    assert isinstance(client, OpenAICompatible) and client.model == "big"
    with pytest.raises(config.ConfigError, match="engine"):
        config.check({"engine": "gpt"})


# -- web tools ---------------------------------------------------------------------------------------------------

def test_a_private_or_local_address_is_never_read():
    for url in ("http://127.0.0.1:4430/api/settings", "http://localhost/", "http://10.0.0.1/", "file:///etc/passwd",
                "http://169.254.169.254/latest/meta-data/"):
        with pytest.raises(webtools.WebError):
            webtools.public(url)


def test_a_page_is_read_as_text_after_its_redirections_each_one_checked():
    checked = []

    def handle(request):
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=(
            "<html><head><title>v0.33.1</title><script>track()</script></head><body><nav>menu</nav>"
            "<h2>Security</h2><p>Fixes CVE-2026-1234 &amp; more.</p><ul><li>one</li></ul>"
            "<ul><li><svg></svg></li><li><svg></svg></li></ul><h3><svg></svg></h3></body></html>"))

    tools = webtools.WebTools(client=httpx.Client(transport=httpx.MockTransport(handle)),
                              check_address=checked.append)
    page = tools.fetch("https://example.org/old")
    assert checked == ["https://example.org/old", "https://example.org/new"]
    assert page.startswith("Source: https://example.org/new\nTitle: v0.33.1")
    assert "## Security" in page and "Fixes CVE-2026-1234 & more." in page and "- one" in page
    assert "track()" not in page and "menu" not in page
    assert page.rstrip().endswith("- one")  # the empty items and heading left by icons are dropped


def test_a_redirection_to_the_local_network_is_refused():
    def handle(request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1:4430/api/settings"})

    tools = webtools.WebTools(client=httpx.Client(transport=httpx.MockTransport(handle)),
                              check_address=lambda url: webtools.public(url) if "127.0.0.1" in url else None)
    budget = webtools.Budget()
    assert budget.run(tools, "web_fetch", {"url": "https://example.org/"}).startswith("Error: 127.0.0.1")


def test_search_through_searxng_and_the_limits_of_one_answer():
    def handle(request):
        assert request.url.params["format"] == "json"
        return httpx.Response(200, json={"results": [{"title": "vLLM v0.33.1", "url": "https://github.com/x",
                                                      "content": "Fixes  CVE", "publishedDate": "2026-11-12T00:00:00"}]})

    tools = webtools.WebTools("http://searx.test", client=httpx.Client(transport=httpx.MockTransport(handle)))
    budget = webtools.Budget(max_searches=1)
    assert budget.run(tools, "web_search", {"query": "vllm"}) == \
        "1. vLLM v0.33.1 (2026-11-12)\n   https://github.com/x\n   Fixes CVE"
    assert budget.run(tools, "web_search", {"query": "again"}).startswith("Limit reached")
    assert [t["function"]["name"] for t in budget.tools(tools)] == ["web_search", "web_fetch"]
    assert [t["function"]["name"] for t in budget.tools(webtools.WebTools())] == ["web_fetch"]  # no search engine set


def test_the_claude_list_without_a_key_is_an_error_not_a_crash():
    """The SDK raises TypeError (not one of its errors) when no key is set: the Settings got an HTTP 500 for it."""
    from types import SimpleNamespace

    def no_key(limit=100):
        raise TypeError("Could not resolve authentication method")

    with pytest.raises(llm.ModelError, match="could not be read"):
        llm.list_models("env:NOTHING", client=SimpleNamespace(models=SimpleNamespace(list=no_key)))


def test_a_hosted_model_is_billed_its_tokens_not_the_searches_of_the_agent(tmp_path):
    """The searches go through SearXNG: counted in the journal, not priced as the Claude API's web search."""
    from vault_watch_agent.prices import Prices

    calls = []

    def handle(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            call = {"id": "c1", "type": "function", "function": {"name": "web_search", "arguments": '{"query": "x"}'}}
            return httpx.Response(200, json={"model": "m", "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0},
                                             "choices": [{"message": {"role": "assistant", "content": "",
                                                                      "tool_calls": [call]}, "finish_reason": "tool_calls"}]})
        return httpx.Response(200, json=completion('{"facts": ["a"]}', prompt=0))

    class Web:
        can_search = True

        def search(self, q):
            return "1. result"

    engine = OpenAICompatible("m", {"base_url": "http://server.test/v1"}, None, http=server(handle), web=Web())
    engine.prices = Prices({"m": {"input": 2.0, "output": 10.0, "cache_read": 0.2, "cache_write": 2.5}})
    _, usage = engine.parse(system="S", prompt="P", schema=Answer, effort="high", node="crosscheck", web=True)
    assert usage["web_searches"] == 1 and usage["cost_usd"] == pytest.approx(2.0 + 10 * 10 / 1e6)


def test_the_judge_of_an_eval_is_a_claude_model_whatever_model_ran_the_watch(monkeypatch, tmp_path):
    """Qwen scoring its own proposals: the scores of two models would not compare."""
    from vault_watch_agent import evaluate

    monkeypatch.setattr(llm, "claude_code_status", lambda fresh=False: {"subscription": "max"})
    assert evaluate.judge_engine(None, "openai") == "claude-code"
    assert evaluate.judge_engine(None, "api") == "api" and evaluate.judge_engine("api", "openai") == "api"
    monkeypatch.setattr(llm, "claude_code_status", lambda fresh=False: {"subscription": None})
    assert evaluate.judge_engine(None, "openai") == "api"
    monkeypatch.setenv("VAULT_WATCH_ENGINE", "openai")  # forces the watch's engine, not the judge's
    settings = config.check({"engine": "openai", "engines": {"openai": {"base_url": "http://h/v1"}}})
    judge = llm.create("reasoning", None, settings, name="api")
    assert type(judge).__name__ != "OpenAICompatible" and judge.model == settings["models"]["reasoning"]
