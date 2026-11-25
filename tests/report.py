"""The report of a test suite, asked for by the user (2026-11-25) to spot a test that fails once in a while.

At the end of each suite, pytest writes `.pytest-report.md` at the root of the repository (not versioned): what
failed, with the first line of its error, the slowest tests, and the tests that failed in one of the last suites;
each suite is also added to `.pytest-history.jsonl` (the last 50). The end of the terminal output says the same in a
few lines, above all « failed before, passed now »: a test that is not stable shows itself even when the next run
passes. conftest.py imports these hooks.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

REPORT = ".pytest-report.md"
HISTORY = ".pytest-history.jsonl"
KEEP = 50  # suites kept in the history
SLOWEST = 10

_start = 0.0
_durations: dict[str, float] = {}  # test: its setup, call and teardown


def pytest_sessionstart(session):
    global _start
    _start = time.time()
    _durations.clear()


def pytest_runtest_logreport(report):
    _durations[report.nodeid] = _durations.get(report.nodeid, 0.0) + report.duration


def _why(rep) -> str:
    """The first line of what made a test fail: the message of its crash, else the last line of its report; and where
    it was raised (file:line), so that an assertion that fails once in a while can be found again."""
    crash = getattr(getattr(rep, "longrepr", None), "reprcrash", None)
    text = getattr(crash, "message", "") or (str(rep.longrepr).strip().splitlines() or [""])[-1]
    line = text.strip().splitlines()[0] if text.strip() else ""
    where = f" (at {Path(crash.path).name}:{crash.lineno})" if getattr(crash, "path", "") and getattr(crash, "lineno", 0) else ""
    return line[:240] + where


def _read_history(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    stats = terminalreporter.stats
    root = Path(config.rootpath)
    counts = {k: len(stats.get(k, [])) for k in ("passed", "failed", "error", "skipped", "deselected")}
    failed = [(r.nodeid, r.when, _why(r)) for k in ("failed", "error") for r in stats.get(k, [])]
    if not (sum(counts.values()) or failed):
        return  # nothing ran (a collection that failed is said by pytest itself)
    now = datetime.now()
    took = time.time() - _start if _start else 0.0
    marks = config.getoption("markexpr", "") or ""
    suite = {"at": now.isoformat(timespec="seconds"), "marks": marks, "seconds": round(took, 1),
             "counts": counts, "failed": sorted({n for n, _, _ in failed})}
    history_path = root / HISTORY
    before = _read_history(history_path)
    try:
        lines = [json.dumps(s, ensure_ascii=False) for s in [*before, suite][-KEEP:]]
        history_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass

    # The tests that failed in one of the previous suites (of the same markers), and passed now
    same = [s for s in before if s.get("marks", "") == marks]
    seen: dict[str, list[str]] = {}
    for s in same:
        for n in s.get("failed", []):
            seen.setdefault(n, []).append(s["at"])
    now_failed = set(suite["failed"])
    ran = {r.nodeid for r in stats.get("passed", [])}
    flaky = sorted((n, at) for n, at in seen.items() if n not in now_failed and n in ran)
    slow = sorted(((d, n) for n, d in _durations.items()), reverse=True)[:SLOWEST]

    said = ", ".join(f"{v} {k}" for k, v in counts.items() if v)
    md = [f"# Test report, {now:%Y-%m-%d %H:%M:%S}", "",
          f"{said} in {took:.1f} s{f' (markers: {marks})' if marks else ''}; compared with the {len(same)} previous "
          f"suites of these markers kept in `{HISTORY}`.", ""]
    if failed:
        md += [f"## Failed ({len(failed)})", ""]
        for n, when, why in failed:
            times = len(seen.get(n, []))
            md.append(f"- `{n}` ({when}): {why}" + (f" (failed in {times} of the last {len(same)} suites too)" if times else ""))
        md.append("")
    if flaky:
        md += ["## Failed before, passed now (not stable?)", ""]
        md += [f"- `{n}`: failed {len(at)} time(s) in the last {len(same)} suites, the last on {at[-1]}" for n, at in flaky]
        md.append("")
    md += [f"## The {len(slow)} slowest (setup, test and teardown)", "", "| s | test |", "| --: | :-- |"]
    md += [f"| {d:.2f} | `{n}` |" for d, n in slow]
    try:
        (root / REPORT).write_text("\n".join(md) + "\n", encoding="utf-8")
    except OSError:
        return

    tr = terminalreporter
    tr.section("report", sep="-")
    for n, when, why in failed:
        times = len(seen.get(n, []))
        tr.write_line(f"FAILED {n} ({when}): {why}" + (f"  [failed in {times} of the last {len(same)} suites too]" if times else ""))
    for n, at in flaky:
        tr.write_line(f"failed before, passed now: {n} ({len(at)} time(s) in the last {len(same)} suites, last {at[-1]})")
    if slow:
        tr.write_line(f"slowest: {slow[0][1]} ({slow[0][0]:.1f} s)")
    tr.write_line(f"written to {REPORT} (history: {HISTORY})")
