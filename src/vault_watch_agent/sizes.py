"""What the guide weighs, page by page: no model, no network.

A watch only adds; over months a guide grows heavy without anyone deciding it. This module says where to look
first: each page against its budget, its heaviest sections, what its footnotes weigh, and what the guide weighed
some time ago (read from Git). A page over its budget is a warning, never a failure: the compaction check
(verify.py) reads the guide with these figures and proposes what to trim.

    report = sizes.report(vault_dir)             # {"pages": [...], "total", "over", "chapters", "growth"}
    sizes.summary(report)                        # one line, for `doctor` and the check's card

The budget of a page comes from the manifest: `[budget] page_kb` (default 30), and `[budget.pages]` for the pages
of a folder (`"00-lexique/**" = 8`); the first pattern that matches wins.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from . import inputs, vault
from .guide import matches

SINCE_DAYS = 90  # the guide is compared with what it weighed this long ago
SECTIONS = 3  # heaviest sections kept per page
HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
NOTE = re.compile(r"^\[\^[^\]]+\]:")


def budget_of(guide, page: str) -> int:
    """The budget of `page` (relative to the guide), in KB."""
    for pattern, kb in guide.page_budgets:
        if matches(page, pattern):
            return kb
    return guide.page_kb


def _size(text: str) -> int:
    return len(text.encode("utf-8"))


def sections(text: str) -> list[dict]:
    """The page cut at its headings of level 1 to 3 (a heading inside a code block is not one): {title, level,
    line, bytes}, the text before the first heading under an empty title."""
    out = [{"title": "", "level": 0, "line": 1, "bytes": 0}]
    fenced = False
    for n, line in enumerate(text.split("\n"), start=1):
        if FENCE.match(line):
            fenced = not fenced
        heading = None if fenced else HEADING.match(line)
        if heading:
            out.append({"title": heading.group(2), "level": len(heading.group(1)), "line": n, "bytes": 0})
        out[-1]["bytes"] += _size(line) + 1
    return [s for s in out if s["bytes"] > 1 or s["title"]]


def page(vault_dir: Path, path: Path) -> dict:
    guide = vault.guide_of(vault_dir)
    rel = path.relative_to(vault_dir).as_posix()
    text = vault.read(path).replace("\r\n", "\n")
    notes = [line for line in text.split("\n") if NOTE.match(line)]
    budget = budget_of(guide, rel)
    size = _size(text)
    heaviest = sorted((s for s in sections(text) if s["title"]), key=lambda s: -s["bytes"])[:SECTIONS]
    readonly = guide.is_readonly(rel)  # listed with its weight, never « over »: the agent does not edit it
    return {"page": rel, "bytes": size, "budget": budget, "over": size > budget * 1024 and not readonly,
            "readonly": readonly, "sections": heaviest,
            "footnotes": {"count": len(notes), "bytes": sum(_size(n) + 1 for n in notes)}}


def earlier(vault_dir: Path, days: int = SINCE_DAYS, today: str | None = None) -> dict | None:
    """What each file weighed `days` ago on the current branch: {"date", "commit", "sizes": {path: bytes}}; None
    when the guide is not in Git or has no commit that old."""
    day = (date.fromisoformat(today) if today else date.today()) - timedelta(days=days)
    try:
        commit = inputs.run(["git", "rev-list", "-1", f"--before={day.isoformat()}T23:59:59", "HEAD"], cwd=vault_dir).strip()
        if not commit:
            return None
        listing = inputs.run(["git", "ls-tree", "-r", "-l", "-z", commit], cwd=vault_dir)
    except (RuntimeError, OSError):
        return None
    found = {}
    for entry in listing.split("\0"):
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if path and len(parts) == 4 and parts[3].isdigit():
            found[path] = int(parts[3])
    return {"date": day.isoformat(), "commit": commit[:9], "sizes": found}


def report(vault_dir: Path, days: int = SINCE_DAYS, today: str | None = None) -> dict:
    """Every page with its size, budget and heaviest sections (heaviest page first), the total per top folder, and
    what the guide gained since `days` ago."""
    rows = sorted((page(vault_dir, p) for p in vault.pages(vault_dir)), key=lambda r: (-r["bytes"], r["page"]))
    chapters: dict[str, dict] = {}
    for r in rows:
        name = r["page"].split("/")[0] if "/" in r["page"] else "(root)"
        c = chapters.setdefault(name, {"chapter": name, "pages": 0, "bytes": 0})
        c["pages"] += 1
        c["bytes"] += r["bytes"]
    total = sum(r["bytes"] for r in rows)
    growth = None
    before = earlier(vault_dir, days, today)
    if before:
        for r in rows:
            r["before"] = before["sizes"].get(r["page"])  # None: the page did not exist
        then = sum(r["before"] or 0 for r in rows)
        growth = {"date": before["date"], "commit": before["commit"], "days": days, "bytes": then,
                  "added": total - then, "new_pages": sum(1 for r in rows if r["before"] is None)}
    return {"pages": rows, "total": total, "over": sum(1 for r in rows if r["over"]),
            "chapters": sorted(chapters.values(), key=lambda c: c["chapter"]), "growth": growth}


def kb(size: int) -> str:
    return f"{size / 1024:.0f} KB" if size >= 10 * 1024 else f"{size / 1024:.1f} KB"


def summary(rep: dict) -> str:
    """One line: the guide's weight, its growth, the pages over their budget (the three heaviest named)."""
    line = f"{len(rep['pages'])} pages, {kb(rep['total'])}"
    g = rep.get("growth")
    if g and g["bytes"]:
        line += f" ({g['added'] / g['bytes']:+.0%} in {g['days']} days)"
    over = [r for r in rep["pages"] if r["over"]]
    if not over:
        return f"{line}; no page over its budget"
    named = ", ".join(f"{r['page']} {kb(r['bytes'])} for {r['budget']} KB" for r in over[:3])
    return f"{line}; {len(over)} page(s) over their budget: {named}" + (" …" if len(over) > 3 else "")


def describe(row: dict) -> str:
    """One page for the compaction prompt: its weight, its budget, where the weight is."""
    parts = [f"{row['page']}: {kb(row['bytes'])} (budget {row['budget']} KB)"]
    if row.get("before"):
        parts.append(f"{kb(row['before'])} {SINCE_DAYS} days ago")
    if row["sections"]:
        parts.append("heaviest sections: " + ", ".join(f"« {s['title']} » {kb(s['bytes'])}" for s in row["sections"]))
    if row["footnotes"]["count"]:
        parts.append(f"{row['footnotes']['count']} footnotes ({kb(row['footnotes']['bytes'])})")
    return "; ".join(parts)


def table(rep: dict, limit: int = 15) -> str:
    """The report as text, for the command line: the pages over their budget, then the heaviest ones."""
    lines = [summary(rep), ""]
    over = [r for r in rep["pages"] if r["over"]]
    for r in over + [r for r in rep["pages"] if not r["over"]][:max(0, limit - len(over))]:
        grew = ""
        if r.get("before") is not None and r["bytes"] != r["before"]:
            grew = f"  {(r['bytes'] - r['before']) / 1024:+.1f} KB"
        elif "before" in r and r["before"] is None:
            grew = "  new"
        flag = "over" if r["over"] else "    "
        lines.append(f"{flag} {kb(r['bytes']):>8} / {r['budget']:>3} KB{grew:>10}  {r['page']}" + ("  (read-only)" if r["readonly"] else ""))
        lines += [f"{'':31}{kb(s['bytes']):>8}  {'#' * s['level']} {s['title']}" for s in r["sections"]]
    return "\n".join(lines)
