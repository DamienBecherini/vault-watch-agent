"""vault-watch collect: the feeds read from fixtures (no network), the rules of the pre-triage, the watch it writes."""

import json
from datetime import datetime, timezone

import pytest

from vault_watch_agent import collect, inputs, watches
from vault_watch_agent.collect import Collector

NOW = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>1</id><updated>2026-11-16T10:00:00Z</updated>
  <link rel="alternate" type="text/html" href="https://github.com/acme/notes/releases/tag/v2.4.0"/>
  <title>v2.4.0</title><content type="html">&lt;p&gt;New export &amp;amp; import&lt;/p&gt;</content></entry>
<entry><id>2</id><updated>2026-11-15T10:00:00Z</updated>
  <link rel="alternate" type="text/html" href="https://github.com/acme/notes/releases/tag/v2.3.2"/>
  <title>v2.3.2</title><content type="html">Bug fixes</content></entry>
<entry><id>3</id><updated>2026-11-14T10:00:00Z</updated>
  <link rel="alternate" type="text/html" href="https://github.com/acme/notes/releases/tag/v2.3.1"/>
  <title>v2.3.1</title><content type="html">Fixes CVE-2026-1234 in the login form</content></entry>
<entry><id>4</id><updated>2026-11-13T10:00:00Z</updated>
  <link rel="alternate" type="text/html" href="https://github.com/acme/notes/releases/tag/v2.4.0-rc.1"/>
  <title>v2.4.0-rc.1</title><content type="html">Release candidate</content></entry>
<entry><id>5</id><updated>2026-10-01T10:00:00Z</updated>
  <link rel="alternate" type="text/html" href="https://github.com/acme/notes/releases/tag/v2.2.0"/>
  <title>v2.2.0</title><content type="html">Out of the window</content></entry>
</feed>"""

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title><![CDATA[Debian 14 point release]]></title><link>https://news.example/debian</link>
  <pubDate>Mon, 16 Nov 2026 09:00:00 +0000</pubDate><description>Routine</description></item>
<item><title>IA locale : un avis</title><link>https://news.example/ia</link>
  <pubDate>Tue, 17 Nov 2026 09:00:00 GMT</pubDate><description>&lt;b&gt;Avis&lt;/b&gt; &#233;mis</description></item>
<item><title>Seen before</title><link>https://news.example/seen/</link>
  <pubDate>Tue, 17 Nov 2026 10:00:00 GMT</pubDate><description>x</description></item>
</channel></rss>"""


def advisory(ghsa, severity, rng, patched, published="2026-11-16T12:00:00Z", package="notes"):
    return {"ghsa_id": ghsa, "cve_id": None, "severity": severity, "summary": f"{ghsa} summary",
            "html_url": f"https://github.com/acme/notes/security/advisories/{ghsa}", "published_at": published,
            "description": "Details.", "vulnerabilities": [
                {"package": {"name": package}, "vulnerable_version_range": rng, "patched_versions": patched}]}


ADVISORIES = [
    advisory("GHSA-low", "low", "< 2.3.1", "2.3.1"),
    advisory("GHSA-fixed", "high", "< 2.1.0", "2.1.0"),              # the floor 2.3.0 is outside the range
    advisory("GHSA-open", "critical", ">= 2.0.0, < 2.3.1", "2.3.1"),  # the floor is inside: urgent
    advisory("GHSA-mod", "moderate", "< 2.5.0", "2.5.0"),             # kept, not urgent
    {**advisory("GHSA-line", "high", "< 2.3.0", "2.3.0"), "vulnerabilities": [  # backported: fixed on the floor's line
        {"package": {"name": ""}, "vulnerable_version_range": "< 2.3.0", "patched_versions": "2.3.0"},
        {"package": {"name": ""}, "vulnerable_version_range": ">= 2.4.0, < 2.4.2", "patched_versions": "2.4.2"}]},
]

HF = [
    {"id": "acme/Base-7B", "createdAt": "2026-11-16T00:00:00.000Z", "pipeline_tag": "text-generation",
     "tags": ["license:apache-2.0"]},
    {"id": "acme/Base-7B-GGUF", "createdAt": "2026-11-16T00:00:00.000Z", "tags": []},
    {"id": "acme/Base-7B-lora", "createdAt": "2026-11-16T00:00:00.000Z", "tags": ["base_model:adapter:acme/Base-7B"]},
]

FEEDS = [
    {"id": "notes", "domain": "releases", "type": "github-releases", "repo": "acme/notes", "tier": "A"},
    {"id": "adv-notes", "domain": "security", "type": "github-advisories", "repo": "acme/notes", "tier": "A"},
    {"id": "news", "domain": "news", "type": "rss", "url": "https://news.example/rss", "tier": "B",
     "keywords": ["IA", "seen"]},
    {"id": "hf-acme", "domain": "models", "type": "huggingface-author", "author": "acme", "tier": "A"},
    {"id": "broken", "domain": "news", "type": "rss", "url": "https://down.example/rss", "tier": "C"},
]


def fake_get(url, as_json=False, github=False, token=""):
    if url == "https://github.com/acme/notes/releases.atom":
        return ATOM
    if "repos/acme/notes/security-advisories" in url:
        assert github
        return ADVISORIES
    if url == "https://news.example/rss":
        return RSS
    if "huggingface.co/api/models?author=acme" in url:
        return HF
    raise RuntimeError("HTTP 503")


def collector(**kw) -> Collector:
    return Collector(feeds=[dict(f) for f in FEEDS], floors={"adv-notes": "2.3.0"},
                     seen={"https://news.example/seen"}, get=fake_get, now=lambda: NOW, **kw)


def by_title(watch):
    return {i["title"]: i for i in watch["items"]}


def test_a_watch_of_the_window_with_the_rules_of_the_pre_triage():
    watch = collector().collect(days=8)
    items = by_title(watch)
    assert watch["since"] == "2026-11-10" and watch["until"] == "2026-11-18"
    # releases: a minor kept with its notes, a routine patch dropped, a security patch kept, a pre-release dropped,
    # the release out of the window not listed
    assert items["acme/notes v2.4.0"]["triage"] == "keep" and items["acme/notes v2.4.0"]["notes"] == "New export & import"
    assert (items["acme/notes v2.3.2"]["triage"], items["acme/notes v2.3.2"]["reason"]) == ("drop", "patch release")
    assert "notes" not in items["acme/notes v2.3.2"]  # notes are cached for kept items only
    assert items["acme/notes v2.3.1"]["reason"] == "patch release, notes mention a security fix"
    assert items["acme/notes v2.4.0-rc.1"]["reason"] == "pre-release"
    assert "acme/notes v2.2.0" not in items
    # advisories against the floor 2.3.0
    adv = {i["title"].split()[1]: i for i in watch["items"] if i["feed"] == "adv-notes"}
    assert adv["GHSA-low"]["reason"] == "low severity"
    assert adv["GHSA-fixed"]["reason"] == "covered by floor 2.3.0"
    assert adv["GHSA-line"]["reason"] == "covered by floor 2.3.0"
    assert adv["GHSA-open"]["triage"] == "keep" and adv["GHSA-open"]["urgent"] and adv["GHSA-open"]["severity"] == "critical"
    assert adv["GHSA-mod"]["triage"] == "keep" and not adv["GHSA-mod"]["urgent"]
    assert adv["GHSA-open"]["notes"].startswith("notes: vulnerable >= 2.0.0, < 2.3.1, patched 2.3.1\n")
    # RSS: keywords at the start of a word ("IA" does not hit "Debian"), the seen URL dropped, entities decoded
    assert "Debian 14 point release" not in items
    assert items["IA locale : un avis"]["notes"] == "Avis émis"  # escaped HTML to text (the summary is decoded once, as in JS)
    assert items["IA locale : un avis"]["date"] == "2026-11-17T09:00:00.000Z"
    assert items["Seen before"]["reason"] == "already seen"
    # Hugging Face: the base kept, its quantized variant and its adapter dropped
    assert items["acme/Base-7B"]["triage"] == "keep" and items["acme/Base-7B"]["summary"] == "text-generation · license:apache-2.0"
    assert items["acme/Base-7B-GGUF"]["reason"] == "quantized variant"
    assert items["acme/Base-7B-lora"]["reason"] == "adapter (LoRA)"
    # a feed that cannot be read is reported, the others go on
    assert watch["errors"] == [{"feed": "broken", "error": "HTTP 503"}]
    assert watch["urgent"] == 1 and watch["kept"] == len([i for i in watch["items"] if i["triage"] == "keep"])
    # what the agent reads: the contract of docs/watch-format.md
    assert inputs.check_watch(json.loads(json.dumps(watch)))["schema"] == 1


def test_no_triage_keeps_everything_and_since_sets_the_window():
    watch = collector(triage_on=False).collect(since="2026-09-01")
    assert all(i["triage"] == "keep" for i in watch["items"])
    assert "acme/notes v2.2.0" in by_title(watch)


def test_a_chatty_feed_collapses_into_one_line_and_a_minimum_level_drops_minors():
    feeds = [{"id": "notes", "domain": "releases", "type": "github-releases", "repo": "acme/notes", "collapse": True},
             {"id": "notes2", "domain": "releases", "type": "github-releases", "repo": "acme/notes", "minLevel": "major"}]
    c = Collector(feeds=feeds, get=fake_get, now=lambda: NOW)
    items = c.collect(days=8)["items"]
    collapsed = [i for i in items if i["feed"] == "notes"]
    assert len(collapsed) == 1 and collapsed[0]["title"] == "acme/notes v2.4.0 (+3 more in window)"
    assert collapsed[0]["triage"] == "keep" and "CVE-2026-1234" in collapsed[0]["notes"]  # rescued by a security fix
    major_only = {i["title"]: i["reason"] for i in items if i["feed"] == "notes2"}
    assert major_only["acme/notes v2.4.0"] == "minor release"


@pytest.mark.parametrize("floor, vulns, covered", [
    ("0.33.0", [{"range": ">= 0.10.0, < 0.32.0", "patched": "0.32.0"}], True),
    ("0.33.0", [{"range": "< 0.34.0", "patched": "0.34.0"}], False),
    ("1.103.12", [{"range": "< 1.103.10", "patched": "1.103.10"}, {"range": ">= 1.104.0, < 1.104.8", "patched": "1.104.8"}], True),
    ("0.33.0", [{"range": "", "patched": ""}], False),  # no usable data: the model decides
])
def test_version_floors(floor, vulns, covered):
    assert (all(collect.floor_covers(floor, v) for v in vulns) or collect.floor_fixed_on_its_line(floor, vulns)) is covered


def test_versions_and_text_as_the_javascript_collector():
    assert collect.parse_version("v0.31.1rc0") == [0, 31, 1, 0]
    assert [collect.release_level(v) for v in ("2.0.0", "2.4.0", "2.4.1", "nightly")] == ["major", "minor", "patch", None]
    assert collect.in_range("1.2.3", ">= 1.0.0, < 1.3") and not collect.in_range("1.3.0", ">= 1.0.0, < 1.3")
    assert collect.cut("ab🚀cd", 3) == "ab" and collect.cut("ab🚀cd", 4) == "ab🚀"  # UTF-16 units, as slice()
    assert collect.parse_date("not a date") is None


def test_the_feeds_file_is_checked(tmp_path):
    bad = tmp_path / "feeds.json"
    bad.write_text(json.dumps({"feeds": [{"id": "x", "domain": "d", "type": "github-releases"}]}), encoding="utf-8")
    with pytest.raises(collect.CollectError, match="feed x .github-releases. needs repo"):
        Collector.from_files(bad)
    bad.write_text(json.dumps({"feeds": [{"id": "x", "domain": "d", "type": "mastodon", "url": "u"}]}), encoding="utf-8")
    with pytest.raises(collect.CollectError, match="type 'mastodon'"):
        Collector.from_files(bad)


def test_the_markdown_report_has_the_urgent_advisories_first_and_the_domains_in_order():
    c = collector()
    c.domains = {"security": "Security", "releases": "Releases"}
    md = collect.markdown(c.collect(days=8), c)
    assert md.index("## Urgent (1)") < md.index("## Security (2)") < md.index("## Releases (2)") < md.index("## News (1)")
    assert "## Dropped by pre-triage" in md and "- `broken`: HTTP 503" in md


def test_the_sample_guide_collects_from_its_feeds(sample_guide, tmp_path, monkeypatch):
    from vault_watch_agent.vault import guide_of

    guide, _ = sample_guide
    monkeypatch.setattr(collect, "http_get", fake_get)  # its four feeds answer 503: reported, not fatal
    c = Collector.of_guide(guide_of(guide))
    assert [f["id"] for f in c.feeds] == ["memos", "adv-memos", "caddy", "postgresql-news"]
    assert c.floors == {"adv-memos": "26.11.0"}
    watch = c.collect()
    assert watch["items"] == [] and len(watch["errors"]) == 4

    # source = "feeds": the interface lists the watches collected in the guide's working folder
    manifest = guide / "vault-watch.toml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace('source = "file"', 'source = "feeds"'), encoding="utf-8")
    src = watches.of(guide_of(guide), tmp_path / "home")
    assert src.kind == "feeds" and src.list() == []
    monkeypatch.setattr(collect, "http_get", lambda url, **kw: ATOM if "memos" in url else fake_get(url, **kw))
    first, second = src.collect(since="2026-09-01"), src.collect(since="2026-09-01")  # never over the first
    assert first.name.startswith("watch-") and second.name == f"{first.stem}-2.json"
    listed = src.list()
    assert [w["thread"] for w in listed] == [second.stem, first.stem] and listed[0]["kind"] == "feeds"
    assert listed[0]["items"] == 3  # v2.4.0, the security fix v2.3.1, v2.2.0
    assert src.fetch(listed[0]["id"]) == second.resolve()


def test_a_feeds_source_needs_its_feeds(tmp_path):
    from vault_watch_agent.guide import GuideError, parse

    with pytest.raises(GuideError, match='source = "feeds" needs feeds'):
        parse({"guide": {"name": "g"}, "content": {"language": "en"}, "watch": {"source": "feeds"}}, tmp_path)
    with pytest.raises(GuideError, match="feeds = 'nope.json': no such file"):
        parse({"guide": {"name": "g"}, "content": {"language": "en"}, "watch": {"feeds": "nope.json"}}, tmp_path)


def test_the_interface_collects_a_watch_when_the_guide_says_so(sample_guide, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from test_web import ACT

    from vault_watch_agent.web import Settings, create_app

    guide, _ = sample_guide
    monkeypatch.setattr(collect, "http_get", lambda url, **kw: ATOM if "memos" in url else fake_get(url, **kw))
    app = create_app(Settings(vault=guide, home=tmp_path / "home", journal=tmp_path / "usage.jsonl",
                              make_deps=lambda thread, kind: None))
    c = TestClient(app)
    assert c.post("/api/collect", json={}, headers=ACT).status_code == 400  # source = "file": its watch is given
    manifest = guide / "vault-watch.toml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace('source = "file"', 'source = "feeds"'), encoding="utf-8")
    app = create_app(Settings(vault=guide, home=tmp_path / "home", journal=tmp_path / "usage.jsonl",
                              make_deps=lambda thread, kind: None))
    c = TestClient(app)
    assert c.get("/api/info").json()["watch_source"] == "feeds"
    made = c.post("/api/collect", json={}, headers=ACT).json()
    assert made["kind"] == "feeds" and made["thread"].startswith("watch-")
    assert [w["thread"] for w in c.get("/api/watches").json()] == [made["thread"]]
    assert c.get("/api/runs").json() == []  # its runs will count under the watch, not in "other runs"


def test_a_moving_tag_is_dropped_the_real_release_kept():
    """n8n publishes `stable`, `latest` and `v1` as releases beside n8n@3.3.0: the moving ones say nothing new."""
    c, feed = collector(), {"id": "n8n", "type": "github-releases", "repo": "n8n-io/n8n"}
    for tag in ("stable", "latest", "v1", "next"):
        item = {"title": f"n8n-io/n8n {tag}", "url": f"https://github.com/n8n-io/n8n/releases/tag/{tag}"}
        assert c.triage(feed, item)[:2] == ("drop", "moving tag")
    real = {"title": "n8n-io/n8n n8n@3.3.0", "url": "https://github.com/n8n-io/n8n/releases/tag/n8n%403.3.0"}
    assert c.triage(feed, real)[0] == "keep"
