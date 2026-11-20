"""What the guide weighs, page by page: no model, no network.

A watch only adds; over months a guide grows heavy without anyone deciding it. This module says where to look
first: the pages that grew much against what they weighed some time ago (read from Git), the heaviest sections of
each page, what its footnotes weigh. A flagged page is a warning, never a failure: the compaction check (verify.py)
reads the guide with these figures and proposes what to trim.

    report = sizes.report(vault_dir)             # {"pages": [...], "total", "grew", "over", "chapters", "growth"}
    sizes.summary(report)                        # one line, for `doctor` and the check's card

A page « grew » when it gained `[budget] growth_kb` (5 KB by default) in 90 days, or `growth_percent` (25 %) of
what it weighed and 2 KB at least. How long a page should be depends on its subject, so there is no ceiling by
default; a guide that wants one sets `[budget] page_kb`, and `[budget.pages]` for the pages of a folder
(`"00-lexique/**" = 8`; the first pattern that matches wins). A page above its ceiling is « over ».
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
GROWTH_FLOOR = 2 * 1024  # a small page that doubles is not news: the share counts from this many bytes gained


def budget_of(guide, page: str) -> int:
    """The ceiling of `page` (relative to the guide), in KB; 0: none."""
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
    return {"page": rel, "bytes": size, "budget": budget, "over": bool(budget) and size > budget * 1024 and not readonly,
            "grew": False,  # set by `report`, which knows what the page weighed
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
    """Every page with its size, what it gained since `days` ago and its heaviest sections (heaviest page first),
    the total per top folder, and what the guide gained."""
    guide = vault.guide_of(vault_dir)
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
            gained = r["bytes"] - (r["before"] or 0)
            r["grew"] = bool(r["before"]) and not r["readonly"] and (
                gained >= guide.growth_kb * 1024
                or (gained >= GROWTH_FLOOR and gained * 100 >= r["before"] * guide.growth_percent))
        then = sum(r["before"] or 0 for r in rows)
        growth = {"date": before["date"], "commit": before["commit"], "days": days, "bytes": then,
                  "added": total - then, "new_pages": sum(1 for r in rows if r["before"] is None)}
    return {"pages": rows, "total": total, "over": sum(1 for r in rows if r["over"]),
            "grew": sum(1 for r in rows if r["grew"]),
            "chapters": sorted(chapters.values(), key=lambda c: c["chapter"]), "growth": growth}


def kb(size: int) -> str:
    return f"{size / 1024:.0f} KB" if size >= 10 * 1024 else f"{size / 1024:.1f} KB"


def gained(row: dict) -> str:
    """What a page gained since the earlier commit: « +5.2 KB, +31% », "new", or "" when unknown or unchanged."""
    if "before" not in row:
        return ""
    if row["before"] is None:
        return "new"
    added = row["bytes"] - row["before"]
    if not added:
        return ""
    return f"{added / 1024:+.1f} KB" + (f", {added / row['before']:+.0%}" if row["before"] else "")


def flagged(rep: dict) -> list[dict]:
    """The pages to look at first: those above a ceiling, then those that grew much (the largest gain first)."""
    over = [r for r in rep["pages"] if r["over"]]
    grew = sorted((r for r in rep["pages"] if r["grew"] and not r["over"]), key=lambda r: r["before"] - r["bytes"])
    return over + grew


def summary(rep: dict) -> str:
    """One line: the guide's weight, its growth, the pages that grew much and those over a ceiling (three named
    each, with what they weigh now)."""
    line = f"{len(rep['pages'])} pages, {kb(rep['total'])}"
    g = rep.get("growth")
    if g and g["bytes"]:
        line += f" ({g['added'] / g['bytes']:+.0%} in {g['days']} days)"
    over = [r for r in rep["pages"] if r["over"]]
    grew = [r for r in flagged(rep) if r["grew"]]
    if not over and not grew:
        return f"{line}; no page grew much" + ("" if g else " (no earlier commit to compare with)")
    parts = []
    if grew:
        named = ", ".join(f"{r['page']} {kb(r['bytes'])} ({gained(r)})" for r in grew[:3])
        parts.append(f"{len(grew)} page(s) grew much in {g['days']} days: {named}" + (" …" if len(grew) > 3 else ""))
    if over:
        named = ", ".join(f"{r['page']} {kb(r['bytes'])} for {r['budget']} KB" for r in over[:3])
        parts.append(f"{len(over)} page(s) over their budget: {named}" + (" …" if len(over) > 3 else ""))
    return f"{line}; " + "; ".join(parts)


def describe(row: dict) -> str:
    """One page for the compaction prompt: its weight, what it gained, where the weight is."""
    parts = [f"{row['page']}: {kb(row['bytes'])}" + (f" (budget {row['budget']} KB)" if row["budget"] else "")]
    if row.get("before"):
        parts.append(f"{kb(row['before'])} {SINCE_DAYS} days ago")
    if row["sections"]:
        parts.append("heaviest sections: " + ", ".join(f"« {s['title']} » {kb(s['bytes'])}" for s in row["sections"]))
    if row["footnotes"]["count"]:
        parts.append(f"{row['footnotes']['count']} footnotes ({kb(row['footnotes']['bytes'])})")
    return "; ".join(parts)


def table(rep: dict, limit: int = 15) -> str:
    """The report as text, for the command line: the flagged pages (over a ceiling, grew much), then the heaviest."""
    lines = [summary(rep), ""]
    first = flagged(rep)
    for r in first + [r for r in rep["pages"] if r not in first][:max(0, limit - len(first))]:
        flag = "over" if r["over"] else "grew" if r["grew"] else "    "
        ceiling = f" / {r['budget']:>3} KB" if r["budget"] else ""
        lines.append(f"{flag} {kb(r['bytes']):>8}{ceiling}  {gained(r):>16}  {r['page']}" + ("  (read-only)" if r["readonly"] else ""))
        lines += [f"{'':31}{kb(s['bytes']):>8}  {'#' * s['level']} {s['title']}" for s in r["sections"]]
    return "\n".join(lines)
