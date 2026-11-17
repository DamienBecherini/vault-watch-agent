"""What the vault's upkeep costs: totals of the call journal by month, year, run or step.

The journal (`metrics/usage.jsonl`, versioned) has one line per model call with
its tokens and its cost. A call to the API costs its tokens at list price,
computed from the usage the API returns: an estimate of the bill, the Console
stays the reference, and a monthly check against it is worth doing
(`_outils/commun/credits-claude.py --releve`). A call through Claude Code on a
subscription (`engine: claude-code`) is not billed: its cost is 0 and the
journal keeps what it would have cost on the API (`list_usd`), shown apart.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def load(journal: Path) -> list[dict]:
    if not journal.exists():
        return []
    return [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line.strip()]


def key(entry: dict, by: str) -> str:
    if by == "month":
        return entry["ts"][:7]
    if by == "year":
        return entry["ts"][:4]
    if by == "run":
        return f"{entry['ts'][:10]} {entry.get('run') or '(unlabelled)'}"
    if by == "step":
        # "propose W4+W5" and "mirror en/…" are one step each
        return f"{entry.get('kind') or 'watch'} / {entry['node'].split(' ')[0]}"
    raise ValueError(by)


def totals(entries: list[dict], by: str) -> dict[str, dict]:
    """`cost`: what was billed; `subscription`: the calls made on a subscription, `spared` what they would have cost."""
    rows: dict[str, dict] = defaultdict(lambda: {"calls": 0, "runs": set(), "in": 0, "out": 0, "cost": 0.0,
                                                 "subscription": 0, "spared": 0.0})
    for e in entries:
        r = rows[key(e, by)]
        r["calls"] += 1
        r["runs"].add(e.get("run") or e["ts"][:10])
        r["in"] += e["input"] + e.get("cache_read", 0) + e.get("cache_write", 0)
        r["out"] += e["output"]
        r["cost"] += e.get("cost_usd", 0.0)
        if e.get("engine") == "claude-code":
            r["subscription"] += 1
            r["spared"] += e.get("list_usd", 0.0)
    return rows


def rows(entries: list[dict], by: str) -> list[dict]:
    """The same totals as `table`, as JSON rows for the web interface."""
    return [{"key": k, "runs": len(r["runs"]), "calls": r["calls"], "in": r["in"], "out": r["out"],
             "cost": round(r["cost"], 2), "subscription": r["subscription"], "spared": round(r["spared"], 2)}
            for k, r in sorted(totals(entries, by).items())]


def table(entries: list[dict], by: str) -> str:
    rows = totals(entries, by)
    label = {"month": "Month", "year": "Year", "run": "Run", "step": "Step"}[by]
    width = max([len(label), *(len(k) for k in rows)])
    spared = any(r["subscription"] for r in rows.values())  # the column shows up with the first subscription call
    extra = f"  {'subscription: calls':>19}  {'not billed $':>12}" if spared else ""
    lines = [f"{label:<{width}}  {'runs':>4}  {'calls':>5}  {'tokens in':>11}  {'out':>9}  {'cost $':>8}{extra}"]
    for k in sorted(rows):
        r = rows[k]
        extra = f"  {r['subscription']:>19}  {r['spared']:>12.2f}" if spared else ""
        lines.append(f"{k:<{width}}  {len(r['runs']):>4}  {r['calls']:>5}  {r['in']:>11,}  {r['out']:>9,}  {r['cost']:>8.2f}{extra}")
    total = sum(r["cost"] for r in rows.values())
    extra = (f"  {sum(r['subscription'] for r in rows.values()):>19}  {sum(r['spared'] for r in rows.values()):>12.2f}"
             if spared else "")
    lines.append(f"{'total':<{width}}  {'':>4}  {sum(r['calls'] for r in rows.values()):>5}  {'':>11}  {'':>9}  {total:>8.2f}{extra}")
    return "\n".join(lines)
