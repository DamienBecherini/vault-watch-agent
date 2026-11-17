from vault_watch_agent import costs
from vault_watch_agent.llm import cost

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
