from vault_watch_agent import costs
from vault_watch_agent.prices import Prices


def cost(usage):
    return Prices().cost(usage)[0]

ENTRIES = [
    {"ts": "2026-11-08T10:00:00+00:00", "run": "issue-50", "kind": "watch", "node": "triage", "model": "claude-opus-5-5",
     "input": 1000, "output": 100, "cache_read": 0, "cache_write": 0, "cost_usd": 0.006},
    {"ts": "2026-11-08T10:01:00+00:00", "run": "issue-50", "kind": "watch", "node": "propose W1+W2", "model": "claude-opus-5-5",
     "input": 2000, "output": 200, "cache_read": 0, "cache_write": 0, "cost_usd": 0.012},
    {"ts": "2026-12-01T09:00:00+00:00", "run": "issue-52", "kind": "crosscheck", "node": "crosscheck", "model": "claude-opus-5-5",
     "input": 100, "output": 10, "cache_read": 400000, "cache_write": 0, "cost_usd": 0.0806},
]


def test_cost_counts_cache_and_web_searches():
    u = {"model": "claude-opus-5-5", "input": 1_000_000, "output": 0, "cache_read": 1_000_000, "cache_write": 1_000_000,
         "web_searches": 10}
    assert round(cost(u), 2) == round(4.0 + 0.20 + 5.0 + 0.10, 2)


def test_tables_by_month_and_step():
    month = costs.table(ENTRIES, "month")
    assert "2026-11" in month and "2026-12" in month and "0.10" in month.splitlines()[-1]
    step = costs.table(ENTRIES, "step")
    assert "watch / propose" in step and "crosscheck / crosscheck" in step
    assert "not billed" not in month  # no call on a subscription: the table keeps its columns


def test_subscription_calls_cost_nothing_and_are_counted_apart():
    entries = ENTRIES + [
        {"ts": "2026-12-02T09:00:00+00:00", "run": "issue-53", "kind": "watch", "node": "triage", "model": "claude-opus-5-5",
         "engine": "claude-code", "input": 1000, "output": 100, "cache_read": 0, "cache_write": 0, "cost_usd": 0.0,
         "list_usd": 0.5},
    ]
    december = next(r for r in costs.rows(entries, "month") if r["key"] == "2026-12")
    assert december == {"key": "2026-12", "runs": 2, "calls": 2, "in": 401100, "out": 110, "cost": 0.08,
                        "subscription": 1, "spared": 0.5}
    last = costs.table(entries, "month").splitlines()[-1]
    assert "not billed $" in costs.table(entries, "month").splitlines()[0] and last.endswith("0.50") and "0.10" in last


def test_prices_are_found_by_exact_id_then_by_dated_id_never_by_a_shorter_model():
    from vault_watch_agent.llm import price_of

    assert price_of("claude-opus-5-5") == (4.0, 20.0, 0.20, 5.0)
    assert price_of("claude-opus-5")[0] == 5.0  # not Opus 5.5's
    assert price_of("claude-sonnet-4-6-20260101")[0] == 3.0
    assert price_of("claude-mythos-6") is None
    assert cost({"model": "claude-mythos-6", "input": 1_000_000, "output": 0}) == 0.0


def test_prices_come_from_the_settings_then_the_fetched_list_then_the_defaults(tmp_path):
    import json

    from vault_watch_agent.prices import Prices

    rates = {"input": 1.0, "output": 2.0, "cache_read": 0.1, "cache_write": 1.25}
    (tmp_path / "prices.json").write_text(json.dumps({"date": "2026-12-01", "models": {
        "claude-opus-5-5": {**rates, "input": 3.0}, "claude-sonnet-5-5": rates}}), encoding="utf-8")
    table = Prices.of_home(tmp_path, {"prices": {"claude-opus-5-5": rates}})
    assert table.of("claude-opus-5-5").origin == "set" and table.of("claude-opus-5-5").input == 1.0
    assert table.of("claude-opus-5-5").label == "set in the Settings"
    fetched = table.of("claude-sonnet-5-5-20261201")  # a dated id takes the price of its model
    assert fetched.origin == "fetched" and fetched.label == "fetched of 2026-12-01"
    default = table.of("claude-haiku-5-5")
    assert default.origin == "default" and default.label == "default of 2026-11" and default.input == 0.10
    assert table.of("claude-mythos-6") is None


def test_a_damaged_fetched_list_falls_back_to_the_defaults(tmp_path):
    from vault_watch_agent.prices import Prices

    (tmp_path / "prices.json").write_text("{not json", encoding="utf-8")
    assert Prices.of_home(tmp_path).of("claude-opus-5-5").origin == "default"


def test_the_settings_refuse_a_wrong_price():
    import pytest

    from vault_watch_agent import config

    ok = config.check({"prices": {"claude-opus-5-5": {"input": 4, "output": 20, "cache_read": 0.2, "cache_write": 5}}})
    assert ok["prices"]["claude-opus-5-5"]["input"] == 4.0
    with pytest.raises(config.ConfigError, match="prices.claude-opus-5-5.output"):
        config.check({"prices": {"claude-opus-5-5": {"input": 4, "output": -1, "cache_read": 0.2, "cache_write": 5}}})
    with pytest.raises(config.ConfigError, match="prices.claude-opus-5-5"):
        config.check({"prices": {"claude-opus-5-5": {"input": 4}}})
    with pytest.raises(config.ConfigError, match="not a Claude model id"):
        config.check({"prices": {"gpt-9": {"input": 1, "output": 1, "cache_read": 1, "cache_write": 1}}})


def test_an_api_call_keeps_the_price_it_was_counted_at(tmp_path):
    import json
    from types import SimpleNamespace

    from vault_watch_agent.llm import Claude
    from vault_watch_agent.prices import Prices
    from vault_watch_agent.state import TriageResult

    usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=0, cache_read_input_tokens=0,
                            cache_creation_input_tokens=0, server_tool_use=None)
    message = SimpleNamespace(usage=usage, stop_reason="end_turn", model="claude-opus-5-5",
                              parsed_output=TriageResult(decisions=[]))

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return message

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=lambda **k: Stream())))
    journal = tmp_path / "usage.jsonl"
    claude = Claude("claude-opus-5-5", client, journal)
    claude.prices = Prices({"claude-opus-5-5": {"input": 1.5, "output": 0, "cache_read": 0, "cache_write": 0}})
    claude.parse(system="s", prompt="p", schema=TriageResult, effort="medium", node="triage")
    line = json.loads(journal.read_text(encoding="utf-8"))
    assert line["cost_usd"] == 1.5 and line["price_origin"] == "set in the Settings"
    assert line["price"] == {"input": 1.5, "output": 0.0, "cache_read": 0.0, "cache_write": 0.0}
