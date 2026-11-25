"""Questioning the sources (sourcecheck.py): what each one answers, what the guide cites, the proposals, the edit of
the feeds file and the branch that carries it. A fake network and a throwaway git repository."""

import json
import subprocess
from datetime import UTC, datetime

import pytest

from vault_watch_agent import collect, sourcecheck
from vault_watch_agent.guide import parse

NOW = datetime(2026, 11, 19, tzinfo=UTC)


def atom(*dates: str) -> str:
    return "<feed>" + "".join(f"<entry><title>v{n}</title><link href='https://x.example/{n}'/><updated>{d}T00:00:00Z"
                              "</updated></entry>" for n, d in enumerate(dates)) + "</feed>"


REPOS = {  # repository -> what GitHub's API says of it
    "acme/engine": {"full_name": "acme/engine"}, "acme/old": {"full_name": "acme/old", "archived": True},
    "acme/renamed": {"full_name": "newco/renamed"}, "acme/quiet": {"full_name": "acme/quiet"},
    "acme/cited": {"full_name": "acme/cited"}, "acme/abandoned": {"full_name": "acme/abandoned"},
}
RELEASES = {"acme/engine": atom("2026-11-10", "2026-10-01"), "acme/old": atom("2025-01-01"),
            "acme/renamed": atom("2026-11-01"), "acme/quiet": atom("2026-02-12"), "acme/cited": atom("2026-11-15"),
            "acme/abandoned": atom("2024-06-01")}


def fake_get(url, as_json=False, github=False, token=""):
    for repo, info in REPOS.items():
        if url == f"https://api.github.com/repos/{repo}":
            return info
        if url == f"https://github.com/{repo}/releases.atom":
            return RELEASES[repo]
        if f"repos/{repo}/security-advisories" in url:
            return []
    if url == "https://blog.example/feed":
        return "<rss><channel></channel></rss>"
    if "huggingface.co/api/models?author=acme" in url:
        return [{"id": "acme/model", "createdAt": "2026-11-12T00:00:00Z"}]
    raise RuntimeError("HTTP 404")


FEEDS = [
    {"id": "engine", "domain": "engines", "type": "github-releases", "repo": "acme/engine", "tier": "A"},
    {"id": "adv-engine", "domain": "security", "type": "github-advisories", "repo": "acme/engine", "tier": "A"},
    {"id": "old", "domain": "engines", "type": "github-releases", "repo": "acme/old", "tier": "A"},
    {"id": "renamed", "domain": "agents", "type": "github-releases", "repo": "acme/renamed", "tier": "A"},
    {"id": "quiet", "domain": "agents", "type": "github-releases", "repo": "acme/quiet", "tier": "A"},
    {"id": "gone", "domain": "agents", "type": "github-releases", "repo": "acme/gone", "tier": "A"},
    {"id": "blog", "domain": "signals", "type": "rss", "url": "https://blog.example/feed", "tier": "B"},
    {"id": "hf-acme", "domain": "models", "type": "huggingface-author", "author": "acme", "tier": "A"},
]
FILE = ('{\n  "$comment": "kept as it is",\n  "defaults": { "days": 8 },\n  "feeds": [\n'
        + ",\n".join(("\n" if f["id"] in ("old", "blog") else "") + "    " + sourcecheck._line(f) for f in FEEDS)
        + "\n  ]\n}\n")


@pytest.fixture
def guide(tmp_path):
    root = tmp_path / "guide"
    (root / "tools").mkdir(parents=True)
    (root / "feeds.json").write_text(FILE, encoding="utf-8")
    page = ("# Engine\n[engine](https://github.com/acme/engine) and [old](https://github.com/acme/old), renamed, quiet, "
            "gone. Models of [acme](https://huggingface.co/acme/model). See https://github.com/acme/cited and "
            "https://github.com/acme/abandoned, https://github.com/features/actions, https://huggingface.co/other/m.\n")
    (root / "tools" / "a.md").write_text(page, encoding="utf-8")
    (root / "tools" / "b.md").write_text(page + "Also https://huggingface.co/other/n and https://github.com/me/guide.\n",
                                         encoding="utf-8")
    return parse({"guide": {"name": "G", "repository": "me/guide"}, "content": {"language": "en"},
                  "watch": {"source": "feeds", "feeds": "feeds.json"}}, root)


@pytest.fixture
def collector(guide):
    return collect.Collector.of_guide(guide, get=fake_get, now=lambda: NOW, token="")


def test_what_each_source_answers(collector):
    state = {f["id"]: sourcecheck.probe(f, collector) for f in FEEDS}
    assert state["engine"] == {"state": "ok", "last": "2026-11-10", "error": ""}
    assert state["adv-engine"]["state"] == "ok" and state["adv-engine"]["last"] == ""  # no advisory: good news
    assert state["old"]["state"] == "archived"
    assert state["renamed"]["state"] == "moved" and state["renamed"]["moved"] == "newco/renamed"
    assert state["quiet"]["state"] == "stale" and state["quiet"]["last"] == "2026-02-12"  # nothing for 180 days
    assert state["gone"]["state"] == "unreachable" and "404" in state["gone"]["error"]
    assert state["blog"]["state"] == "empty" and state["hf-acme"]["state"] == "ok"


def test_what_the_guide_cites(guide):
    repos, authors, text = sourcecheck.cited(guide)
    assert repos["acme/cited"] == {"name": "acme/cited", "pages": ["tools/a.md", "tools/b.md"]}
    assert "features/actions" not in repos and set(authors) == {"acme", "other"}  # a page of the site is not an account
    assert sourcecheck.named(FEEDS[0], text) and sourcecheck.named(FEEDS[4], text)  # by its repository, by its name
    assert not sourcecheck.named({"repo": "acme/unknown"}, text)
    assert not sourcecheck.named({"repo": "x/eng"}, text)  # « eng » is inside « engine », not a name of its own


def test_the_proposals_follow_the_rules(guide, collector, tmp_path):
    rows = [{"id": "blog", "verdict": "quiet"}, {"id": "hf-acme", "verdict": "noise", "judged": 14, "useful": 1}]
    probes = {f["id"]: sourcecheck.probe(f, collector) for f in FEEDS}
    proposals = sourcecheck.propose(FEEDS, rows, probes, guide, collector)
    got = {(p["action"], p["feed"]["id"]): p for p in proposals}
    assert [p["id"] for p in proposals] == [f"S{n}" for n in range(1, len(proposals) + 1)]
    assert got[("remove", "old")]["why"] == "archived" and got[("remove", "old")]["recommended"]
    assert got[("remove", "gone")]["why"] == "unreachable" and got[("remove", "gone")]["recommended"]  # a 404: gone
    assert got[("change", "renamed")]["new"]["repo"] == "newco/renamed" and got[("change", "renamed")]["recommended"]
    assert got[("remove", "blog")]["why"] == "empty" and not got[("remove", "blog")]["recommended"]
    assert got[("remove", "hf-acme")] | {"id": 0} == {"id": 0, "action": "remove", "feed": FEEDS[7], "why": "noise",
                                                       "recommended": False, "judged": 14, "kept": 1}
    assert ("remove", "quiet") not in got  # a tool that went quiet is said, never proposed for removal
    # Cited in two pages, alive, followed by no feed; its domain is the one of the feeds cited in the same pages
    cited = got[("add", "cited")]
    assert cited["feed"] == {"id": "cited", "domain": "engines", "type": "github-releases", "repo": "acme/cited", "tier": "A"}
    assert cited["pages"] == 2 and not cited["recommended"]
    assert ("add", "abandoned") not in got  # cited, but nothing published for years: nothing to follow
    assert ("add", "guide") not in got  # the maintainer's own repositories are not a watch subject
    assert got[("add", "hf-other")]["feed"]["author"] == "other" and got[("add", "hf-other")]["feed"]["domain"] == "models"
    # Followed for its releases, not for its advisories (engine already is; old, renamed and gone are settled)
    assert {p["feed"]["id"] for p in proposals if p["why"] == "no-advisories"} == {"adv-quiet"}
    assert got[("add", "adv-quiet")]["feed"]["domain"] == "security"


def test_the_feeds_file_keeps_its_layout(guide, collector):
    assert sourcecheck.edit(FILE, []) == FILE  # nothing chosen, nothing touched
    new = {"id": "cited", "domain": "engines", "type": "github-releases", "repo": "acme/cited", "tier": "A"}
    edited = sourcecheck.edit(FILE, [
        {"action": "remove", "feed": FEEDS[2]}, {"action": "remove", "feed": FEEDS[6]},
        {"action": "change", "feed": FEEDS[3], "new": {**FEEDS[3], "repo": "newco/renamed"}},
        {"action": "add", "feed": new}])
    data = json.loads(edited)
    assert [f["id"] for f in data["feeds"]] == ["engine", "adv-engine", "renamed", "quiet", "gone", "cited", "hf-acme"]
    assert data["$comment"] == "kept as it is" and data["feeds"][2]["repo"] == "newco/renamed"
    before, after = FILE.splitlines(), edited.splitlines()
    assert [ln for ln in after if '"engine"' in ln] == [ln for ln in before if '"engine"' in ln]  # untouched lines
    assert after[-3].endswith("}") and not after[-3].endswith(",") and "\n\n\n" not in edited  # commas, blank lines
    assert sum(1 for ln in after if not ln.strip()) == 2  # the two blank lines between the groups are still there
    # A group emptied by the removals takes its blank line with it
    emptied = sourcecheck.edit(FILE, [{"action": "remove", "feed": f} for f in FEEDS[2:6]])
    assert sum(1 for ln in emptied.splitlines() if not ln.strip()) == 1 and "\n\n\n" not in emptied
    with pytest.raises(ValueError, match="no such feed"):
        sourcecheck.edit(FILE, [{"action": "remove", "feed": {"id": "nope"}}])
    with pytest.raises(ValueError, match="already in the file"):
        sourcecheck.edit(FILE, [{"action": "add", "feed": FEEDS[0]}])
    # Another layout: written again from its data
    compact = json.dumps(json.loads(FILE))
    assert [f["id"] for f in json.loads(sourcecheck.edit(compact, [{"action": "remove", "feed": FEEDS[0]}]))["feeds"]][0] == "adv-engine"


def test_the_whole_check_and_its_pull_request(guide, collector, tmp_path):
    git = lambda *a, cwd=guide.root: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout  # noqa: E731
    git("init", "-q", "-b", "main")
    git("config", "user.name", "t")
    git("config", "user.email", "t@example.org")
    git("add", "-A")
    git("commit", "-qm", "init")
    seen = []
    result = sourcecheck.check(guide, tmp_path / "home", [], collector=collector, progress=seen.append)
    assert sorted(seen) == sorted(f["id"] for f in FEEDS) and set(result["probes"]) == set(seen)
    chosen = [p for p in result["proposals"] if p["recommended"]]
    assert {(p["action"], p["feed"]["id"]) for p in chosen} == {("remove", "old"), ("remove", "gone"), ("change", "renamed")}
    assert sourcecheck.title(chosen) == "chore(watch): sources of the watch (2 removed, 1 changed)"

    opened = {}

    def open_pull_request(repo, *, base, head, title, body, cwd):
        opened.update(repo=repo, base=base, head=head, title=title, body=body)
        return "https://forge.example/me/guide/pulls/3"

    # No remote in this repository: the push is what fails, after the commit; the branch stays, its folder goes
    with pytest.raises(RuntimeError, match="push"):
        sourcecheck.publish(guide, tmp_path / "home", chosen, today="2026-11-19", open_pull_request=open_pull_request)
    assert not (tmp_path / "home" / "worktrees" / "chore-watch-sources-2026-11-19").exists()
    committed = json.loads(git("show", "chore/watch-sources-2026-11-19:feeds.json"))
    assert [f["id"] for f in committed["feeds"]] == ["engine", "adv-engine", "renamed", "quiet", "blog", "hf-acme"]
    assert "remove old: the repository is archived" in git("log", "-1", "--format=%B", "chore/watch-sources-2026-11-19")
    assert json.loads((guide.root / "feeds.json").read_text(encoding="utf-8")) == json.loads(FILE)  # the folder is not touched

    # A guide without a repository: a second branch (the first name is taken), no push, no pull request
    local = parse({"guide": {"name": "G"}, "content": {"language": "en"}, "watch": {"source": "feeds", "feeds": "feeds.json"}},
                  guide.root)
    done = sourcecheck.publish(local, tmp_path / "home", chosen[:1], today="2026-11-19", open_pull_request=open_pull_request)
    assert done == {"branch": "chore/watch-sources-2026-11-19-2", "pr_url": ""} and not opened
    text = sourcecheck.body(chosen, "feeds.json")
    assert "- Remove `old` (github-releases, acme/old): the repository is archived." in text and "`feeds.json`" in text
