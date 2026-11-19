"""The sources of a watch judged over time (sources.py): what each feed brought, and the verdict of each rule."""

import json

from vault_watch_agent import sources
from vault_watch_agent.guide import parse

FEEDS = [
    {"id": "engine", "type": "github-releases", "repo": "acme/engine", "domain": "engines", "tier": "A"},
    {"id": "adv-engine", "type": "github-advisories", "repo": "acme/engine", "domain": "security", "tier": "A"},
    {"id": "blog", "type": "rss", "url": "https://blog.example/feed", "domain": "signals", "tier": "B"},
    {"id": "videos", "type": "youtube", "channelId": "UC1", "name": "Videos", "tier": "C"},
    {"id": "dead", "type": "github-releases", "repo": "acme/dead", "tier": "A"},
    {"id": "models", "type": "huggingface-author", "author": "acme", "tier": "A"},
]


def item(feed: str, n: int, triage: str = "keep", date: str = "2026-11-01") -> dict:
    return {"feed": feed, "url": f"https://x.example/{feed}/{n}", "title": f"{feed} {n}", "triage": triage, "date": date}


def state(decisions: dict[str, str], corrections: list[tuple[str, list[str]]] = (), applied: list[str] = ()) -> dict:
    """A run state: {url: action}, the corrections as (id, urls they cite), the ids the reviewer accepted."""
    ids = {u: f"W{n}" for n, u in enumerate(decisions, start=1)}
    return {"items": [{"id": i, "url": u} for u, i in ids.items()],
            "decisions": [{"item_id": ids[u], "action": a, "reason": ""} for u, a in decisions.items()],
            "corrections": [{"id": c, "item_ids": [ids[u] for u in urls]} for c, urls in corrections],
            "applied": list(applied)}


def test_what_became_of_each_item_of_a_run():
    a, b, c, d = (f"https://x.example/engine/{n}" for n in range(4))
    out = sources.run_outcomes(state({a: "correct", b: "correct", c: "addition", d: "drop"},
                                     corrections=[("C1", [a]), ("C2", [b])], applied=["C1"]))
    assert out == {a: "accepted", b: "proposed", c: "addition", d: "drop"}
    assert sources.run_outcomes({"items": [{"id": "F1", "url": ""}], "corrections": [{"id": "C1", "item_ids": ["F1"]}]}) == {}


def test_each_feed_gets_the_verdict_of_its_rule():
    watch_list = [
        {"since": "2026-10-01", "until": "2026-10-15", "errors": [], "items": [
            item("engine", 1), item("engine", 2, "drop"), item("adv-engine", 1),
            *[item("videos", n) for n in range(12)], *[item("blog", n, date="2026-10-10") for n in range(3)]]},
        {"since": "2026-10-10", "until": "2026-11-01", "errors": [{"feed": "models", "error": "HTTP 500"}], "items": [
            item("engine", 1), item("engine", 3, date="2026-11-02"),  # engine 1 again: the windows overlap
            *[item("adv-engine", n) for n in range(2, 14)]]},
    ]
    url = lambda feed, n: f"https://x.example/{feed}/{n}"  # noqa: E731
    first = sources.run_outcomes(state(
        {url("engine", 1): "correct", url("adv-engine", 1): "drop", url("blog", 0): "correct", url("blog", 1): "drop",
         **{url("videos", n): "drop" for n in range(12)}},
        corrections=[("C1", [url("engine", 1)])], applied=["C1"]))
    again = sources.run_outcomes(state({url("engine", 1): "drop"}))  # the same watch run a second time: the best counts
    second = sources.run_outcomes(state({url("adv-engine", n): "drop" for n in range(2, 14)}))
    rows = {r["id"]: r for r in sources.table(FEEDS, watch_list, [first, again, second, {}])}

    engine = rows["engine"]
    assert (engine["collected"], engine["kept"], engine["judged"], engine["proposed"], engine["accepted"]) == (3, 2, 1, 1, 1)
    assert engine["verdict"] == "useful" and engine["last_item"] == "2026-11-02" and engine["watches"] == 2
    assert engine["target"] == "acme/engine" and engine["url"] == "https://github.com/acme/engine"
    assert rows["videos"]["verdict"] == "noise" and rows["videos"]["judged"] == 12  # twelve judged, none kept
    assert rows["adv-engine"]["verdict"] == "quiet" and rows["adv-engine"]["insurance"]  # thirteen judged: never noise
    assert rows["blog"]["verdict"] == "leads" and rows["blog"]["useful"] == 1  # kept by the model, nothing proposed
    assert rows["dead"]["verdict"] == "silent" and rows["dead"]["last_item"] == ""
    assert rows["models"]["verdict"] == "error"  # the latest watch could not read it


def test_the_summary_reads_the_watches_kept_on_the_machine(tmp_path):
    guide_dir, home = tmp_path / "guide", tmp_path / "home"
    guide_dir.mkdir()
    (guide_dir / "feeds.json").write_text(json.dumps({"feeds": FEEDS[:2]}), encoding="utf-8")
    (guide_dir / "index.md").write_text("# Guide\n", encoding="utf-8")
    guide = parse({"guide": {"name": "G"}, "content": {"language": "en"},
                   "watch": {"source": "feeds", "feeds": "feeds.json"}}, guide_dir)
    assert sources.summary(guide, home, [])["period"] == {"since": "", "until": "", "watches": 0}

    watch = {"schema": 1, "since": "2026-10-01", "until": "2026-10-15",
             "items": [item("engine", 1), item("gone", 1), {"feed": "engine", "title": "no address"}]}
    for folder in ("downloads/run-1", "downloads/run-2", "watches"):  # the same watch downloaded twice, and collected
        (home / folder).mkdir(parents=True)
        (home / folder / ("watch.json" if "run" in folder else "watch-2026-10-15.json")).write_text(json.dumps(watch), encoding="utf-8")
    (home / "watches" / "broken.json").write_text("{", encoding="utf-8")
    s = sources.summary(guide, home, [])
    assert s["period"] == {"since": "2026-10-01", "until": "2026-10-15", "watches": 1} and s["file"] == "feeds.json"
    assert [(r["id"], r["collected"], r["verdict"]) for r in s["feeds"]] == [("engine", 1, "quiet"), ("adv-engine", 0, "silent")]
    assert s["removed"] == [{"id": "gone", "items": 1}]  # in the watches, no longer in feeds.json


def test_a_guide_without_feeds_has_no_sources(tmp_path):
    guide = parse({"guide": {"name": "G"}, "content": {"language": "en"}}, tmp_path)
    s = sources.summary(guide, tmp_path / "home", [])
    assert s["file"] == "" and s["feeds"] == []
