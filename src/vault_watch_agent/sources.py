"""The sources of a guide's watch, judged over time: what each feed brought and what became of it.

No model and no network: the table is computed from what is already on the machine, the watches the agent has
read (`watch.json` files, each item naming its feed) and the runs made from them (the triage of the model, the
corrections the reviewer accepted).

    rows = table(feeds(guide), watches(guide, home), runs)     # one row per feed, with its verdict
    summary(guide, home, runs)                                  # the same, with the period, for the interface

`runs` are the states of the watch runs, each reduced by `run_outcomes` to what happened to every item: dropped
by the model, kept for a correction or an addition, cited by a proposed correction, by an accepted one.

A verdict is a rule anyone can check, never a judgement of the model:
  error    the collector could not read the feed in the latest watch
  useful   an item of the feed led to a proposed correction, or the model listed one as an addition candidate
  leads    the model kept items of the feed for a correction, and no correction came out of them
  noise    the model judged at least NOISE_MIN of its items, at most one in ten kept, nothing proposed
  silent   no item over the whole period (the feed may be dead, or its subject may publish nothing: only the
           source itself can tell)
  quiet    a few items, none kept yet: too little to say
A feed of security advisories is insurance: silence is good news, and it is never called noise.
"""

from __future__ import annotations

import json
from pathlib import Path

from .guide import Guide

NOISE_MIN = 10          # items judged by the model: below that, too few to call a feed noise
NOISE_SHARE = 0.1       # at most that share of them kept by the model
INSURANCE = ("github-advisories",)  # judged on its health, never on what it yields
# What happened to an item, from least to most: the best outcome over the runs of a watch counts.
OUTCOMES = ("drop", "addition", "correct", "proposed", "accepted")


def feeds(guide: Guide) -> list[dict]:
    """The feeds of the manifest's feeds.json, [] when the guide declares none or the file cannot be read."""
    if not guide.watch.feeds:
        return []
    try:
        config = json.loads((guide.root / guide.watch.feeds).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [f for f in config.get("feeds", []) if isinstance(f, dict) and f.get("id")]


def target(feed: dict) -> tuple[str, str]:
    """(what the feed follows, in a few words; its web address when there is one)."""
    kind = feed.get("type", "")
    if feed.get("repo"):
        return feed["repo"], f"https://github.com/{feed['repo']}"
    if feed.get("author"):
        return feed["author"], f"https://huggingface.co/{feed['author']}"
    if feed.get("url"):
        return feed["url"], feed["url"]
    if kind == "youtube":
        return feed.get("name") or feed.get("channelId", ""), (
            f"https://www.youtube.com/channel/{feed['channelId']}" if feed.get("channelId") else "")
    return feed.get("name") or feed.get("query") or kind, ""


def watches(guide: Guide, home: Path) -> list[dict]:
    """The watches found on this machine, oldest first: the artifacts downloaded from the forge's issues, the ones
    the agent collected, the manifest's own file or folder. A file that cannot be read is skipped."""
    paths = [*sorted((home / "downloads").glob("run-*/watch.json")), *sorted((home / "watches").glob("*.json"))]
    if guide.watch.source == "file" and guide.watch.path:
        given = guide.root / guide.watch.path
        paths += sorted(given.glob("*.json")) if given.is_dir() else [given] if given.is_file() else []
    found, seen = [], set()
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("items"), list) or not data.get("until"):
            continue
        key = (data.get("since"), data["until"], len(data["items"]))  # the same watch downloaded twice
        if key in seen:
            continue
        seen.add(key)
        found.append({"since": data.get("since") or "", "until": data["until"],
                      "items": [i for i in data["items"] if isinstance(i, dict) and i.get("url")],
                      "errors": data.get("errors") or []})
    return sorted(found, key=lambda w: (w["until"], w["since"]))


def run_outcomes(state: dict) -> dict[str, str]:
    """{item url: outcome} of one watch run: what the model decided for each item, and whether a correction that
    cites it was proposed, then accepted by the reviewer. {} for a run that is not a watch (a fix run)."""
    decisions = state.get("decisions") or []
    if not decisions:
        return {}
    url = {i["id"]: i.get("url", "") for i in state.get("items", [])}
    out = {url[d["item_id"]]: d["action"] for d in decisions if url.get(d["item_id"])}
    applied = set(state.get("applied") or [])
    for c in state.get("corrections") or []:
        outcome = "accepted" if c.get("id") in applied else "proposed"
        for item_id in c.get("item_ids") or []:
            u = url.get(item_id)
            if u and OUTCOMES.index(outcome) > OUTCOMES.index(out.get(u, "drop")):
                out[u] = outcome
    return out


def table(feed_list: list[dict], watch_list: list[dict], runs: list[dict[str, str]]) -> list[dict]:
    """One row per feed: what it brought over the watches, what became of it, and the verdict (see the module)."""
    best: dict[str, str] = {}  # url -> best outcome over the runs (a watch may have been run several times)
    for outcomes in runs:
        for u, o in outcomes.items():
            if OUTCOMES.index(o) > OUTCOMES.index(best.get(u, "drop")) or u not in best:
                best[u] = o
    latest_errors = _error_feeds(watch_list[-1]["errors"]) if watch_list else set()
    rows = []
    for feed in feed_list:
        fid = feed["id"]
        items: dict[str, dict] = {}  # url -> item; windows overlap, an item is counted once
        with_items = 0
        for w in watch_list:
            mine = [i for i in w["items"] if i.get("feed") == fid]
            with_items += bool(mine)
            for i in mine:
                kept_before = items.get(i["url"], {}).get("triage") == "keep"
                items[i["url"]] = {**i, "triage": "keep" if kept_before else i.get("triage", "")}
        kept = [u for u, i in items.items() if i["triage"] == "keep"]
        judged = [u for u in kept if u in best]
        count = lambda *names, judged=judged: sum(1 for u in judged if best[u] in names)
        name, link = target(feed)
        row = {
            "id": fid, "type": feed.get("type", ""), "domain": feed.get("domain", ""), "tier": feed.get("tier", ""),
            "target": name, "url": link, "insurance": feed.get("type") in INSURANCE,
            "last_item": max(((i.get("date") or "")[:10] for i in items.values()), default=""),
            "watches": with_items, "collected": len(items), "kept": len(kept), "judged": len(judged),
            "useful": count("addition", "correct", "proposed", "accepted"), "additions": count("addition"),
            "proposed": count("proposed", "accepted"), "accepted": count("accepted"),
            "error": fid in latest_errors,
        }
        row["verdict"] = verdict(row)
        rows.append(row)
    return rows


def verdict(row: dict) -> str:
    if row["error"]:
        return "error"
    if row["proposed"] or row["additions"]:
        return "useful"
    if not row["collected"]:
        return "silent"
    if row["judged"] >= NOISE_MIN and not row["insurance"] and row["useful"] <= NOISE_SHARE * row["judged"]:
        return "noise"
    return "leads" if row["useful"] else "quiet"


def summary(guide: Guide, home: Path, runs: list[dict[str, str]]) -> dict:
    """What the interface shows: the period the watches cover, the feeds with their rows, and the items whose feed
    the feeds.json no longer lists."""
    feed_list, watch_list = feeds(guide), watches(guide, home)
    known = {f["id"] for f in feed_list}
    gone: dict[str, int] = {}
    for w in watch_list:
        for i in w["items"]:
            if i.get("feed") and i["feed"] not in known:
                gone[i["feed"]] = gone.get(i["feed"], 0) + 1
    return {
        "file": guide.watch.feeds or "",
        "period": {"since": min((w["since"] for w in watch_list if w["since"]), default=""),
                   "until": watch_list[-1]["until"] if watch_list else "", "watches": len(watch_list)},
        "runs": sum(1 for r in runs if r),
        "noise_min": NOISE_MIN, "noise_share": NOISE_SHARE,
        "feeds": table(feed_list, watch_list, runs),
        "removed": [{"id": k, "items": n} for k, n in sorted(gone.items())],
    }


def _error_feeds(errors: list) -> set[str]:
    """The feeds a watch could not read: {"feed": id, "error": …} as both collectors write them."""
    return {e["feed"] for e in errors if isinstance(e, dict) and e.get("feed")}
