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
