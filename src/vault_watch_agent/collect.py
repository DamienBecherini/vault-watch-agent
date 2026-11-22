"""Collection of a watch by the agent: what changed in the guide's domain over a window, read from the feeds the
guide lists in a `feeds.json`, triaged by rules (no model), written as a `watch.json` (docs/watch-format.md).

    collector = Collector.of_guide(guide)           # feeds.json, version floors, seen list: from the manifest
    watch = collector.collect(days=8)               # {schema, since, until, kept, core, urgent, items, errors}
    print(markdown(watch, collector))               # the issue body of the weekly workflow

A port of `scripts/watch-feeds.mjs` of the IA on-prem guide, with the same feed types, the same rules and the same
output, so that a guide can use either. Feed types: github-releases, github-tags, github-advisories, rss (RSS 2.0 or
Atom), youtube, huggingface-author, and two discovery types, huggingface-trending and github-search
(docs/collect.md). The pre-triage, deterministic:
  - pre-releases (rc, beta, dev, nightly, proto-…) and releases below the feed's `minLevel` (default minor: patch
    releases dropped), unless their notes mention a security fix (security, CVE, GHSA, vulnerability);
  - `collapse` feeds (build-per-commit projects) are one routine line unless rescued the same way;
  - advisories of low severity, or already fixed at the guide's version floor (the floor outside the vulnerable
    range, or the lowest patched version at or below it, or the fix of its own release line);
  - Hugging Face quantized variants, adapters, and third-party fine-tunes found by discovery;
  - anything whose URL is in the guide's list of items already seen.
High and Critical advisories not covered by a floor are `urgent`. The notes of kept items (release notes, advisory
texts) are cached in the watch so that the model does not fetch them again; a kept item its feed gives without
text (a blog post, a press release, a model page) gets the start of its own page instead (`page_notes`).

Only the standard library to read the feeds; the pages of items without text are read with the agent's page reader
(`webtools`), installed with it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import cmp_to_key
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

from . import __version__

NOTES_MAX = 4000
TIMEOUT = 20
WORKERS = 6
UA = f"vault-watch-agent/{__version__} (+https://github.com/DamienBecherini/vault-watch-agent)"
FEED_TYPES = ("github-releases", "github-tags", "github-advisories", "rss", "youtube", "huggingface-author",
              "huggingface-trending", "github-search", "page")
# A watched page (type "page"): what is kept of it from one watch to the next
PAGE_VALUES = 500      # the values its `watch` expression finds, or its lines of text
PAGE_CHARS = 40_000    # of text kept, for a page watched whole
PAGE_CUMULATE = 30     # days: changes that close together are told as one, from what the page said before them
# Shown last, as leads: discovery feeds, and tier C sources (a lead, never a citation).
LEAD_DOMAINS = ("discovery", "signals")
PAGE_TEXT_MIN = 200    # characters: less is a page that could not be read (a sign-in wall, a script-only page)
SCRIPT_ONLY_HOSTS = ("youtube.com", "youtu.be", "m.youtube.com")  # pages whose text is drawn by scripts: menus only


class CollectError(ValueError):
    """The feeds file cannot be used; the message says where."""


# ---------------------------------------------------------------------------------------------------------------
# Reading feeds
# ---------------------------------------------------------------------------------------------------------------

def http_get(url: str, *, as_json: bool = False, github: bool = False, token: str = ""):
    """The body of `url` (text, or parsed JSON); an HTTP error raises with its status."""
    headers = {"User-Agent": UA}
    if github:
        headers["Accept"] = "application/vnd.github+json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, headers=headers), timeout=TIMEOUT) as res:
            body = res.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}") from e
    except URLError as e:
        raise RuntimeError(str(e.reason)) from e
    except TimeoutError as e:
        raise RuntimeError("timed out") from e
    return json.loads(body) if as_json else body


def github_token() -> str:
    """The token for GitHub's API: GITHUB_TOKEN or GH_TOKEN, else the one of `gh` when it is signed in on this
    machine, else none (60 requests an hour, and no advisories). It only ever goes to api.github.com."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token and shutil.which("gh"):
        try:
            done = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10,
                                  stdin=subprocess.DEVNULL)
            token = done.stdout.strip() if done.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            token = ""
    return token


def page_snapshot(html: str, watch: str = "") -> list[str]:
    """What a watched page says: the distinct matches of `watch` in its readable text, in their order (prices, for
    `\\$\\d+\\.\\d+`), else its lines of text. Menus, scripts and styles are not read."""
    from .webtools import readable

    text = readable(html)[1]
    found = ([m.group(0) for m in re.finditer(watch, text)] if watch
             else [ln.strip() for ln in text[:PAGE_CHARS].splitlines() if ln.strip()])
    return list(dict.fromkeys(found))[:PAGE_VALUES]


def page_change(before: list[str], now: list[str]) -> tuple[list[str], list[str]]:
    """(what the page no longer says, what it says and did not), each in the order of its page."""
    return [v for v in before if v not in set(now)], [v for v in now if v not in set(before)]


def previous_pages(paths: list[Path]) -> dict[str, dict]:
    """The watched pages as the most recent of these watches left them ({feed id: {snapshot, changed, before}});
    {} when none says anything about pages. A folder stands for the watch.json files under it."""
    files = [f for p in paths for f in (sorted(p.rglob("*.json")) if p.is_dir() else [p] if p.is_file() else [])]
    best: tuple[str, dict] = ("", {})
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("pages"), dict) and str(data.get("until") or "") >= best[0]:
            best = (str(data.get("until") or ""), data["pages"])
    return best[1]


def cut(s: str, n: int) -> str:
    """The first `n` UTF-16 units of `s`, as JavaScript's slice: both collectors give the same text (an emoji counts
    two); a character cut in half is left out."""
    if len(s) <= n // 2:
        return s
    return s.encode("utf-16-le")[: 2 * n].decode("utf-16-le", errors="ignore")


def _entity(m: re.Match) -> str:
    try:
        return chr(int(m.group(1)) & 0xFFFF)  # as String.fromCharCode
    except ValueError:
        return ""


def decode(s) -> str:
    """Markup of a feed to one line of text: CDATA unwrapped, tags removed, the common entities decoded."""
    s = re.sub(r"<!\[CDATA\[([\s\S]*?)\]\]>", r"\1", str(s or ""))
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    s = re.sub(r"&#0?39;|&apos;", "'", s)
    s = re.sub(r"&#(\d+);", _entity, s)
    return re.sub(r"\s+", " ", s).strip()


def html_text(s) -> str:
    """Escaped HTML (Atom <content type="html">) to plain text."""
    return decode(decode(s))


def tag(block: str, name: str) -> str:
    m = re.search(rf"<{name}(?:\s[^>]*)?>([\s\S]*?)</{name}>", block, re.I)
    return decode(m.group(1)) if m else ""


def atom_link(block: str) -> str:
    m = (re.search(r'<link[^>]*rel="alternate"[^>]*href="([^"]+)"', block, re.I)
         or re.search(r'<link[^>]*href="([^"]+)"', block, re.I))
    link = m.group(1) if m else tag(block, "link")
    return link if re.match(r"https?://", link.strip(), re.I) else ""  # a feed's own link: http(s), never « javascript: »


def parse_date(text) -> datetime | None:
    """An ISO 8601 or RFC 822 date, in UTC; a date without zone is taken as UTC. None when unreadable."""
    text = str(text or "").strip()
    if not text:
        return None
    try:
        d = datetime.fromisoformat(text)
    except ValueError:
        try:
            d = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def iso(d: datetime) -> str:
    """As JavaScript's toISOString: 2026-11-12T09:30:00.000Z."""
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"


def parse_feed(xml: str) -> list[dict]:
    """RSS 2.0 or Atom to [{title, url, date, summary, notes}]."""
    blocks = (re.findall(r"<item[\s>][\s\S]*?</item>", xml, re.I)
              or re.findall(r"<entry[\s>][\s\S]*?</entry>", xml, re.I))
    items = []
    for b in blocks:
        date = tag(b, "pubDate") or tag(b, "published") or tag(b, "updated") or tag(b, "dc:date")
        # The text of the item: its content, else its description; a YouTube video has it in media:description
        raw = (re.search(r"<content[^>]*>([\s\S]*?)</content>", b, re.I)
               or re.search(r"<description>([\s\S]*?)</description>", b, re.I)
               or re.search(r"<media:description[^>]*>([\s\S]*?)</media:description>", b, re.I))
        when = parse_date(date)
        items.append({
            "notes": cut(html_text(raw.group(1)), NOTES_MAX) if raw else "",
            "title": tag(b, "title") or tag(b, "media:title"),
            "url": atom_link(b),
            "date": iso(when) if when else None,
            "summary": cut(tag(b, "description") or tag(b, "summary") or tag(b, "media:description"), 220),
        })
    return items


def _or(value, default):
    """JavaScript's `??`: the default only for a missing value (an empty name stays empty)."""
    return default if value is None else value


def _pkg(vuln: dict):
    return (vuln.get("package") or {}).get("name")


def _hf_summary(m: dict) -> str:
    return " · ".join(x for x in [m.get("pipeline_tag"), *[t for t in m.get("tags") or [] if t.startswith("license:")]] if x)


# ---------------------------------------------------------------------------------------------------------------
# Pre-triage (deterministic rules)
# ---------------------------------------------------------------------------------------------------------------

RESCUE = re.compile(r"\b(security|CVE-\d{4}|GHSA-|vulnerab)", re.I)
PRE = re.compile(r"(^|[^a-z])(rc\d*|alpha|beta|dev\d*|nightly|preview|canary|snapshot)([^a-z]|$)|^proto-", re.I)
# A tag moved from release to release (n8n publishes stable, latest and v1 as releases): the real one is there too.
MOVING = re.compile(r"^(stable|latest|next|edge|current|v?\d+)$", re.I)
QUANT = re.compile(r"[-_.](gguf|awq|gptq|fp8|fp4|nvfp4|mxfp4|int4|int8|w4a16|w8a8|mlx|bnb|4bit|8bit|exl[23]|onnx)\b", re.I)
VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?")
FIXES = re.compile(r"\d+\.\d+(?:\.\d+)*")
LEVELS = {"major": 3, "minor": 2, "patch": 1}


def parse_version(v) -> list[int] | None:
    """"v0.31.1rc0" -> [0, 31, 1, 0]; None when there is no dotted version."""
    m = VERSION.search(str(v))
    return [int(n or 0) for n in m.groups()] if m else None


def cmp_version(a, b) -> int:
    x, y = parse_version(a) or [], parse_version(b) or []
    for i in range(max(len(x), len(y))):
        d = (x[i] if i < len(x) else 0) - (y[i] if i < len(y) else 0)
        if d:
            return 1 if d > 0 else -1
    return 0


def in_range(version: str, rng: str) -> bool:
    """Is `version` inside a GitHub range such as ">= 0.11.1, < 0.18.0"? An unknown constraint counts as inside."""
    for c in rng.split(","):
        m = re.match(r"^(<=|>=|<|>|=)?\s*v?(\S+)$", c.strip())
        if not m or not parse_version(m.group(2)):
            continue
        d = cmp_version(version, m.group(2))
        if not {"<": d < 0, "<=": d <= 0, ">": d > 0, ">=": d >= 0, "=": d == 0}[m.group(1) or "="]:
            return False
    return True


def floor_covers(floor: str, vuln: dict) -> bool:
    """The floor is safe when it is outside the vulnerable range, or when the lowest patched version (">= 0.31.0",
    "1.99.9, 1.100.4") is at or below it. No usable data: not covered, the model decides."""
    if vuln["range"] and not in_range(floor, vuln["range"]):
        return True
    fixes = sorted(FIXES.findall(vuln["patched"]), key=cmp_to_key(cmp_version))
    return bool(fixes) and cmp_version(fixes[0], floor) <= 0


def floor_fixed_on_its_line(floor: str, vulns: list[dict]) -> bool:
    """Backported fixes come as one entry per release line ("< 1.103.10", "< 1.104.8"…): a floor on an older line
    still falls inside the later ranges, and is safe when the fix of its own line (same major.minor) is at or below it."""
    line = lambda v: (parse_version(v) or [])[:2]  # noqa: E731
    return any(line(fix) == line(floor) and cmp_version(fix, floor) <= 0
               for v in vulns for fix in FIXES.findall(v["patched"]))


def release_level(v: str) -> str | None:
    """major for x.0.0, minor for x.y.0, patch otherwise."""
    p = parse_version(v)
    if not p:
        return None
    if any(p[2:]):
        return "patch"
    return "minor" if p[1] else "major"


# ---------------------------------------------------------------------------------------------------------------
# The collector
# ---------------------------------------------------------------------------------------------------------------

@dataclass
class Collector:
    feeds: list[dict]
    days: int = 8
    max_items: int = 15
    domains: dict[str, str] = field(default_factory=dict)  # domain -> title of its section, in order
    floors: dict[str, str] = field(default_factory=dict)   # advisory feed id -> lowest version the guide recommends
    seen: set[str] = field(default_factory=set)            # URLs already triaged by the editor
    token: str = ""
    previous: dict[str, dict] = field(default_factory=dict)  # the watched pages as the last watch left them
    pages: dict[str, dict] = field(default_factory=dict)     # as this collection leaves them (the watch's `pages`)
    triage_on: bool = True
    read_pages: bool = True  # a kept item whose feed gives no text: its own page is read, its start kept as notes
    get: Callable | None = None                             # (url, as_json=, github=, token=) -> text or JSON; http_get
    now: Callable[[], datetime] | None = None               # the clock (tests)

    @classmethod
    def from_files(cls, feeds: Path, floors: Path | None = None, seen: Path | None = None, **kw) -> Collector:
        """From a feeds.json, the version floors ({"floors": {feed id: version}}) and a file of seen URLs."""
        try:
            config = json.loads(feeds.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise CollectError(f"{feeds}: {e}") from e
        check(config, feeds.name)
        defaults = config.get("defaults", {})
        floor_map = json.loads(floors.read_text(encoding="utf-8")).get("floors", {}) if floors and floors.is_file() else {}
        seen_urls = set()
        if seen and seen.is_file():
            seen_urls = {u.rstrip("/") for u in re.findall(r"https?://[^\s)>\]|]+", seen.read_text(encoding="utf-8"))}
        kw.setdefault("token", github_token())
        return cls(feeds=config["feeds"], days=int(defaults.get("days", 8)), max_items=int(defaults.get("maxItemsPerFeed", 15)),
                   domains=dict(config.get("domains", {})), floors=floor_map, seen=seen_urls, **kw)

    @classmethod
    def of_guide(cls, guide, **kw) -> Collector:
        """From the manifest: [watch] feeds, seen and floors (else the file of [checks] version_floors)."""
        w = guide.watch
        if not w.feeds:
            raise CollectError('the manifest has no [watch] feeds (the feeds.json to read, see docs/collect.md)')
        floors = w.floors or (guide.version_floors.file if guide.version_floors else "")
        return cls.from_files(guide.root / w.feeds, guide.root / floors if floors else None,
                              guide.root / w.seen if w.seen else None, **kw)

    # -- reading ------------------------------------------------------------------------------------------------

    def _get(self, url: str, **kw):
        return (self.get or http_get)(url, **kw)

    def _now(self) -> datetime:
        return self.now() if self.now else datetime.now(timezone.utc)

    def _gh(self, url: str):
        return self._get(url, as_json=True, github=True, token=self.token)

    def read(self, feed: dict) -> list[dict]:
        kind, now = feed["type"], self._now()
        if kind == "github-releases":
            return [{**i, "title": f"{feed['repo']} {i['title']}"}
                    for i in parse_feed(self._get(f"https://github.com/{feed['repo']}/releases.atom"))]
        if kind == "github-tags":
            out = []
            for t in self._gh(f"https://api.github.com/repos/{feed['repo']}/tags?per_page=10")[:5]:
                c = self._gh(t["commit"]["url"]) or {}
                out.append({"title": f"{feed['repo']} {t['name']}",
                            "url": f"https://github.com/{feed['repo']}/releases/tag/{t['name']}",
                            "date": ((c.get("commit") or {}).get("committer") or {}).get("date"), "summary": ""})
            return out
        if kind == "github-advisories":
            out = []
            for a in self._gh(f"https://api.github.com/repos/{feed['repo']}/security-advisories?state=published"
                              "&sort=published&direction=desc&per_page=30"):
                vulns = a.get("vulnerabilities") or []
                cve = f" / {a['cve_id']}" if a.get("cve_id") else ""
                out.append({
                    "title": f"{feed['repo']} {a.get('ghsa_id')}{cve} [{a.get('severity') or '?'}] {a.get('summary')}",
                    "url": a.get("html_url"),
                    "date": a.get("published_at"),
                    "severity": a.get("severity"),
                    "vulns": [{"range": v.get("vulnerable_version_range") or "", "patched": v.get("patched_versions") or ""}
                              for v in vulns],
                    "notes": cut("\n".join([*(f"{_or(_pkg(v), '?')}: vulnerable "
                                          f"{v.get('vulnerable_version_range') or '?'}, patched {v.get('patched_versions') or 'none'}"
                                          for v in vulns), str(a.get("description") or "")]), NOTES_MAX),
                    "summary": cut("; ".join(f"{_or(_pkg(v), '')} patched: {v.get('patched_versions') or 'none'}"
                                         for v in vulns), 220),
                })
            return out
        if kind == "huggingface-author":
            author = quote(feed["author"], safe="-_.!~*'()")
            return [{"title": m["id"], "url": f"https://huggingface.co/{m['id']}", "date": m.get("createdAt"),
                     "tags": m.get("tags") or [], "summary": _hf_summary(m)}
                    for m in self._get(f"https://huggingface.co/api/models?author={author}&sort=createdAt&direction=-1&limit=40",
                                      as_json=True)]
        if kind == "huggingface-trending":  # discovery: trending models of publishers not already followed
            followed = {f["author"].lower() for f in self.feeds if f["type"] == "huggingface-author"}
            listed = self._get(f"https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit={feed.get('limit', 40)}",
                              as_json=True)
            return [{"title": f"{m['id']} (trending {_or(m.get('trendingScore'), '?')}, {m.get('likes') or 0} likes)",
                     "url": f"https://huggingface.co/{m['id']}", "date": m.get("createdAt"), "tags": m.get("tags") or [],
                     "summary": _hf_summary(m)}
                    for m in listed if str(m["id"]).split("/")[0].lower() not in followed]
        if kind == "github-search":  # discovery: young repositories that gained traction fast
            created = (now - timedelta(days=feed.get("maxAgeDays", 30))).strftime("%Y-%m-%d")
            q = f"{feed['query']} created:>{created} stars:>{feed.get('minStars', 500)}"
            res = self._gh(f"https://api.github.com/search/repositories?q={quote(q, safe='')}&sort=stars&order=desc"
                           f"&per_page={feed.get('limit', 10)}")
            return [{"title": cut(f"{r['full_name']} ({r['stargazers_count']} stars) — {r.get('description') or ''}", 200),
                     "url": r["html_url"], "date": r.get("created_at"), "summary": ", ".join(r.get("topics") or [])}
                    for r in res.get("items") or []]
        if kind == "page":
            return self._page(feed, now)
        if kind == "youtube":
            return [{**i, "title": f"{feed['name']}: {i['title']}"}
                    for i in parse_feed(self._get(f"https://www.youtube.com/feeds/videos.xml?channel_id={feed['channelId']}"))]
        return parse_feed(self._get(feed["url"]))  # rss

    def _page(self, feed: dict, now: datetime) -> list[dict]:
        """A watched page: one item when it no longer says what it said at the last watch. The day of the change
        and what the page said before it are kept in the watch (`pages`), so that a watch with a longer window
        tells a change a shorter one saw first. The first reading of a page is its reference: no item."""
        snapshot = page_snapshot(self._get(feed["url"]), feed.get("watch", ""))
        old = self.previous.get(feed["id"]) or {}
        state = {"url": feed["url"], "snapshot": snapshot}
        today = now.strftime("%Y-%m-%d")
        if old.get("snapshot") is not None and old["snapshot"] != snapshot:
            recent = old.get("changed", "") >= (now - timedelta(days=PAGE_CUMULATE)).strftime("%Y-%m-%d")
            state.update(changed=today, before=old["before"] if recent and old.get("before") else old["snapshot"])
        elif old.get("changed"):
            state.update(changed=old["changed"], before=old.get("before", []))
        self.pages[feed["id"]] = state
        if not state.get("changed"):
            return []
        gone, new = page_change(state["before"], snapshot)
        if not gone and not new:  # it changed, then came back to what it said
            return []
        name = feed.get("name") or feed["url"]
        notes = "\n".join([f"The page {feed['url']} changed (seen on {state['changed']})."]
                          + (["No longer on the page:", *(f"- {v}" for v in gone)] if gone else [])
                          + (["New on the page:", *(f"- {v}" for v in new)] if new else []))
        return [{"title": f"{name}: the page changed ({len(gone)} value(s) gone, {len(new)} new)",
                 "url": f"{feed['url']}#changed-{state['changed']}",  # one address per change: told once, not for ever
                 "date": f"{state['changed']}T00:00:00.000Z",
                 "summary": cut("gone: " + ", ".join(gone[:8]) + " · new: " + ", ".join(new[:8]), 220),
                 "notes": cut(notes, NOTES_MAX)}]

    # -- triage -------------------------------------------------------------------------------------------------

    def triage(self, feed: dict, item: dict) -> tuple[str, str, bool]:
        """(keep | drop, reason, urgent)."""
        if not self.triage_on:
            return "keep", "", False
        if str(item.get("url")).rstrip("/") in self.seen:
            return "drop", "already seen", False
        rescued = bool(RESCUE.search(f"{item.get('title')} {item.get('notes') or ''}"))
        kind = feed["type"]

        if kind in ("github-releases", "github-tags"):
            parts = str(item.get("url")).split("/releases/tag/")
            tag_name = unquote(parts[1]) if len(parts) > 1 else ""
            if PRE.search(tag_name):
                return "drop", "pre-release", False
            if MOVING.match(tag_name):
                return "drop", "moving tag", False
            if feed.get("collapse"):
                return ("keep", "notes mention a security fix", False) if rescued else ("drop", "routine build", False)
            level = release_level(tag_name)
            if level and LEVELS[level] < LEVELS[feed.get("minLevel", "minor")]:
                return ("keep", f"{level} release, notes mention a security fix", False) if rescued else ("drop", f"{level} release", False)
            return "keep", "", False

        if kind == "github-advisories":
            sev = str(item.get("severity") or "").lower()
            if sev == "low":
                return "drop", "low severity", False
            floor = self.floors.get(feed["id"])
            vulns = item.get("vulns") or []
            if floor and vulns and (all(floor_covers(floor, v) for v in vulns) or floor_fixed_on_its_line(floor, vulns)):
                return "drop", f"covered by floor {floor}", False
            return "keep", f"affects floor {floor}" if floor else "no floor in the guide", sev in ("high", "critical")

        if kind in ("huggingface-author", "huggingface-trending"):
            tags = item.get("tags") or []
            # A quant-suffixed repository is a variant of a base listed on its own; a quantized one without suffix
            # counts only when another publisher made it (an official FP8-only release stays).
            parts = str(item.get("url")).split("/")
            author = parts[3].lower() if len(parts) > 3 else ""
            other = lambda t: (t.split(":")[2].split("/")[0].lower() if len(t.split(":")) > 2 else "") != author  # noqa: E731
            if QUANT.search(str(item.get("url"))) or any(t.startswith("base_model:quantized:") and other(t) for t in tags):
                return "drop", "quantized variant", False
            if any(t.startswith("base_model:adapter:") for t in tags):
                return "drop", "adapter (LoRA)", False
            if feed.get("discovery") and any(re.match(r"^base_model:(finetune|merge):", t) and other(t) for t in tags):
                return "drop", "third-party fine-tune or merge", False
        return "keep", "", False

    # -- a whole watch ------------------------------------------------------------------------------------------

    def _matches(self, feed: dict, item: dict) -> bool:
        if feed.get("exclude") and re.search(feed["exclude"], item.get("title") or "", re.I):
            return False
        if not feed.get("keywords"):
            return True
        # A keyword matches at the start of a word: "IA" must not hit "Debian".
        hay = f"{item.get('title')} {item.get('summary')}"
        return any(re.search(rf"(?<![^\W_]){re.escape(k.strip())}", hay, re.I) for k in feed["keywords"])

    def _items(self, feed: dict, since: datetime) -> list[dict]:
        now = self._now()
        # Discovery feeds look at how young an item is (maxAgeDays), not at the window.
        start = now - timedelta(days=feed.get("maxAgeDays", 45)) if feed.get("discovery") else since
        fresh = [i for i in self.read(feed)
                 if (d := parse_date(i.get("date"))) and d >= start and self._matches(feed, i)]
        fresh.sort(key=lambda i: i.get("date") or "", reverse=True)
        total = len(fresh)
        if feed.get("collapse") and total > 1:
            notes = "\n".join(f"{i['title']}: {i.get('notes')}" for i in fresh if RESCUE.search(i.get("notes") or ""))
            fresh = [{**fresh[0], "title": f"{fresh[0]['title']} (+{total - 1} more in window)",
                      "notes": cut(notes or fresh[0].get("notes") or "", NOTES_MAX)}]
        out = []
        for i in fresh[: self.max_items]:
            verdict, reason, urgent = self.triage(feed, i)
            if verdict == "keep" and not (i.get("notes") or "").strip() and self.read_pages:
                i = {**i, "notes": self.page_notes(i.get("url"))}
            rest = {k: v for k, v in i.items() if k not in ("tags", "notes", "vulns")}
            out.append({"feed": feed["id"], "domain": "discovery" if feed.get("discovery") else feed["domain"],
                        **({"tier": feed["tier"]} if "tier" in feed else {}), **rest,
                        "triage": verdict, "reason": reason, "urgent": urgent,
                        **({"notes": i["notes"]} if verdict == "keep" and i.get("notes") else {})})
        return out

    def page_notes(self, url) -> str:
        """The start of the readable text of an item's own page, for an item its feed gives without text (a blog
        post, a press release, a model page): what the run reads instead of nothing, from the primary source and
        without a model. "" when the page cannot be read (an error, a private address, too little text)."""
        from . import webtools  # its page reader (httpx, installed with the agent): only when a page is read

        url = str(url or "")
        host = (urlsplit(url).hostname or "").removeprefix("www.")
        if host in SCRIPT_ONLY_HOSTS:
            return ""
        # A repository's page: its README as written, not the page around it (menus, file list)
        repo = re.fullmatch(r"https://github\.com/([\w.-]+)/([\w.-]+)/?", url)
        tries = [f"https://raw.githubusercontent.com/{repo[1]}/{repo[2]}/HEAD/README.md"] if repo else []
        body = ""
        for address in [*tries, url]:
            try:
                if self.get:  # the tests' reader
                    webtools.public(address)
                    body = self._get(address)
                else:  # each redirection checked public, and the address connected to (links.get)
                    from . import links
                    body = links.get(address)[2].decode("utf-8", errors="replace")
                break
            except Exception:  # noqa: BLE001 - the next address, else the item stays as its feed gave it
                continue
        if not body:
            return ""
        body = str(body).lstrip("\ufeff")  # a README saved with a byte order mark
        text = webtools.readable(body)[1] if "<" in body[:3000] else body.strip()
        return cut(f"(read from {url})\n{text}", NOTES_MAX) if len(text) >= PAGE_TEXT_MIN else ""

    def selected(self, only: set[str] | None = None) -> list[dict]:
        return [f for f in self.feeds if not only or f["domain"] in only]

    def collect(self, *, days: int | None = None, since: str | None = None, only: set[str] | None = None) -> dict:
        """The watch of the window (`since`, else the last `days` days, else the feeds file's default), in the
        format of docs/watch-format.md, with the counts the workflow reads and the feeds in error."""
        now = self._now()
        since = since or (now - timedelta(days=days if days is not None else self.days)).strftime("%Y-%m-%d")
        start = datetime.fromisoformat(f"{since}T00:00:00+00:00")
        feeds = self.selected(only)

        def one(feed):
            try:
                return self._items(feed, start), None
            except Exception as e:  # noqa: BLE001 - a feed in error is reported, the others go on
                if feed["type"] == "page" and feed["id"] in self.previous:
                    self.pages[feed["id"]] = self.previous[feed["id"]]  # not read today: what was known stays
                return [], {"feed": feed["id"], "error": str(e) or type(e).__name__}

        with ThreadPoolExecutor(WORKERS) as pool:
            done = list(pool.map(one, feeds))
        items = [i for found, _ in done for i in found]
        errors = [e for _, e in done if e]
        kept = [i for i in items if i["triage"] == "keep"]
        return {"schema": 1, "collector": f"vault-watch-agent {__version__}", "since": since,
                "until": now.strftime("%Y-%m-%d"), "kept": len(kept), "core": len([i for i in kept if not lead(i)]),
                "urgent": len([i for i in kept if i["urgent"]]), "feeds": len(feeds), "items": items, "errors": errors,
                **({"pages": {k: self.pages[k] for k in sorted(self.pages)}} if self.pages else {})}

    def domain_order(self, feeds: list[dict]) -> list[str]:
        """The sections of the report: the feeds file's `domains` in order, then the others as the feeds list them,
        security first and the leads last."""
        found = list(self.domains)
        for f in feeds:
            d = "discovery" if f.get("discovery") else f["domain"]
            if d not in found:
                found.append(d)
        if not self.domains:
            found.sort(key=lambda d: (d != "security", d in LEAD_DOMAINS))
        return found


def lead(item: dict) -> bool:
    """A lead to skim, not a fact to check: a discovery item or a tier C source."""
    return item.get("domain") in LEAD_DOMAINS or item.get("tier") == "C"


def check(config, where: str = "feeds.json") -> dict:
    """The feeds file as docs/collect.md describes it, or CollectError naming the first problem."""
    if not isinstance(config, dict) or not isinstance(config.get("feeds"), list):
        raise CollectError(f"{where}: an object with a list `feeds` is expected")
    needs = {"github-releases": "repo", "github-tags": "repo", "github-advisories": "repo", "rss": "url",
             "youtube": "channelId", "huggingface-author": "author", "github-search": "query", "page": "url"}
    ids = set()
    for n, f in enumerate(config["feeds"], start=1):
        if not isinstance(f, dict) or not f.get("id") or not f.get("domain"):
            raise CollectError(f"{where}: feed {n} needs an id and a domain")
        if f["id"] in ids:
            raise CollectError(f"{where}: feed id {f['id']!r} is used twice")
        ids.add(f["id"])
        kind = f.get("type", "rss")
        if kind not in FEED_TYPES:
            raise CollectError(f"{where}: feed {f['id']}: type {kind!r}, one of {', '.join(FEED_TYPES)}")
        f.setdefault("type", kind)
        if needs.get(kind) and not f.get(needs[kind]):
            raise CollectError(f"{where}: feed {f['id']} ({kind}) needs {needs[kind]}")
        if kind == "youtube" and not f.get("name"):
            raise CollectError(f"{where}: feed {f['id']} (youtube) needs name")
        if f.get("minLevel", "minor") not in LEVELS:
            raise CollectError(f"{where}: feed {f['id']}: minLevel is major, minor or patch")
        for key in ("exclude", "watch"):
            if f.get(key):
                try:
                    re.compile(f[key])
                except re.error as e:
                    raise CollectError(f"{where}: feed {f['id']}: {key} is not a valid regular expression ({e})") from e
    return config


# ---------------------------------------------------------------------------------------------------------------
# Markdown (the body of the watch issue)
# ---------------------------------------------------------------------------------------------------------------

def _cell(text: str) -> str:
    return cut(str(text).replace("|", "\\|"), 160)


def markdown(watch: dict, collector: Collector, only: set[str] | None = None) -> str:
    feeds = collector.selected(only)
    items, errors = watch["items"], watch["errors"]
    kept = [i for i in items if i["triage"] == "keep"]
    dropped = [i for i in items if i["triage"] == "drop"]
    urgent = [i for i in kept if i["urgent"]]
    md = [f"# Weekly watch — {watch['since']} → {watch['until']}\n",
          f"Sources: **{len(feeds)}** · items in window: **{len(items)}** · kept after pre-triage: **{len(kept)}** "
          f"(core **{watch['core']}**, leads **{len(kept) - watch['core']}**) · urgent: **{len(urgent)}** · sources in "
          f"error: **{len(errors)}**{'' if collector.token else ' · no GitHub token (advisories may fail)'}\n",
          "_Deterministic pre-triage only (rules of `vault-watch collect`). vault-watch-agent turns the kept items into "
          "dated events, verifies the primary source and maps them to the guide's pages. Release notes and advisory "
          "texts are cached in `watch.json` (run artifact). Tier C items are leads only._\n"]
    watched = [f for f in feeds if f["type"] == "page"]
    if watched:
        new = [f["id"] for f in watched if f["id"] in collector.pages and f["id"] not in collector.previous]
        md.append(f"Watched pages: **{len(watched)}**" + (
            f" · first reading of {', '.join(new)}: the reference for the next watch (no previous watch said what "
            "the page showed)" if new else "") + "\n")
    if urgent:
        md.append(f"## Urgent ({len(urgent)}) — High / Critical advisories not covered by a version floor\n")
        md += [f"- [{_cell(r['title'])}]({r['url']}) — {r['reason']}" for r in urgent]
        md.append("")
    in_feeds = {"discovery" if f.get("discovery") else f["domain"] for f in feeds}
    for d in collector.domain_order(feeds):
        listed = sorted([r for r in kept if r["domain"] == d], key=lambda r: r.get("date") or "", reverse=True)
        if not listed and d not in in_feeds:
            continue
        md.append(f"## {collector.domains.get(d, d.capitalize())} ({len(listed)})\n")
        if not listed:
            md.append("_Nothing new in the window._\n")
            continue
        md += ["| Date | Source | Item | Tier | Pre-triage |", "| :-- | :-- | :-- | :-- | :-- |"]
        md += [f"| {(r.get('date') or '')[:10]} | {r['feed']} | [{_cell(r['title'])}]({r['url']}) | {r.get('tier', '')} | {r['reason']} |"
               for r in listed]
        md.append("")
    if dropped:
        md.append(f"## Dropped by pre-triage ({len(dropped)})\n")
        md.append("<details><summary>Dropped by deterministic rules (run with <code>--no-triage</code> to keep everything)</summary>\n")
        by_reason: dict[str, list[dict]] = {}
        for r in dropped:
            by_reason.setdefault(r["reason"], []).append(r)
        for reason, listed in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
            names = ", ".join(cut(re.sub(r"\s*\(.*$", "", r["title"]).replace("|", "/"), 70) for r in listed)
            md.append(f"- **{reason}** ({len(listed)}): {cut(names, 600)}{' …' if len(names) > 600 else ''}")
        md.append("\n</details>\n")
    if errors:
        md.append(f"## Sources in error ({len(errors)})\n")
        md += [f"- `{e['feed']}`: {e['error']}" for e in errors]
        md.append("")
    return "\n".join(md)
