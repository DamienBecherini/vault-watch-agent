"""Dead links (ROADMAP E7): the probe from this machine crossed with the weekly report of the guide's CI, a site that
fails only from the CI's runners told apart; the replacement opens the dead address first."""

import json
from pathlib import Path

import pytest

from vault_watch_agent import forge, guide, verify

MANIFEST = """schema = 1
[guide]
name = "Test"
repository = "me/guide"
[content]
language = "fr"
[checks]
sources = "node audit.mjs --json={out}"
"""

PAGE = "# Page\n\nVoir [A](https://a.example/doc), [B](https://b.example/doc), [C](https://c.example/doc), [D](https://d.example/doc).\n"


def report(statuses: dict[str, str]) -> dict:
    return {"sources": [{"url": url, "probe": {"status": s, "code": 404 if s == "dead" else 403 if s == "blocked" else 200},
                         "citations": [{"page": "page.md", "line": 3}]} for url, s in statuses.items()]}


LOCAL = report({"https://a.example/doc": "dead", "https://b.example/doc": "ok", "https://c.example/doc": "blocked",
                "https://d.example/doc": "dead"})
WEEKLY = report({"https://a.example/doc": "dead", "https://b.example/doc": "dead", "https://c.example/doc": "ok",
                 "https://d.example/doc": "ok"})


class Forge:
    name = "GitHub"

    def __init__(self, fail: bool = False):
        self.fail, self.downloads = fail, []

    def latest_artifact(self, repo, name):
        if self.fail:
            raise RuntimeError("gh: signed in nowhere")
        assert (repo, name) == ("me/guide", "freshness-report")
        return {"run_id": "99", "created": "2026-11-23"}

    def download_artifact(self, repo, run_id, name, dest):
        self.downloads.append(run_id)
        (Path(dest) / "sources.json").write_text(json.dumps(WEEKLY), encoding="utf-8")


@pytest.fixture
def guide_dir(tmp_path, monkeypatch):
    root = tmp_path / "guide"
    root.mkdir()
    (root / "vault-watch.toml").write_text(MANIFEST + 'sources_weekly = "freshness-report/sources.json"\n', encoding="utf-8")
    (root / "page.md").write_text(PAGE, encoding="utf-8")

    def check(key, cwd, out=None):  # the guide's own probe, as it would write its report
        assert key == "sources"
        out.write_text(json.dumps(LOCAL), encoding="utf-8")
        return ""

    monkeypatch.setattr(verify.inputs, "check", check)
    return root


def test_the_probe_is_crossed_with_the_weekly_report_of_the_ci(guide_dir, tmp_path, monkeypatch):
    fake = Forge()
    monkeypatch.setattr(forge, "get", lambda: fake)
    work = tmp_path / "work"
    work.mkdir()
    r = verify.run_sources(guide_dir, work, {}, None)
    # A: dead from both. D: dead from here only (still to look at). B: dead from the runners only, answers here.
    assert [(d["url"], d.get("weekly")) for d in r["dead"]] == [("https://a.example/doc", "dead"), ("https://d.example/doc", "ok")]
    assert [d["url"] for d in r["runners_only"]] == ["https://b.example/doc"]
    assert [d["url"] for d in r["blocked"]] == ["https://c.example/doc"]
    assert r["summary"] == ("4 sources: 2 not answering, 1 blocked by anti-bot protections (usually fine in a browser); "
                            "crossed with the weekly report of 2026-11-23 (run 99): 1 dead from its runners too, 1 failing "
                            "only from them (sites that refuse data-centre addresses)")
    assert len(r["findings"]) == 2
    verify.run_sources(guide_dir, work, {}, None)
    assert fake.downloads == ["99"]  # the artifact of a run is downloaded once


def test_a_weekly_report_that_cannot_be_read_is_said_and_the_probe_stands(guide_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(forge, "get", lambda: Forge(fail=True))
    r = verify.run_sources(guide_dir, tmp_path, {}, None)
    assert r["summary"].endswith("; the weekly report could not be read: gh: signed in nowhere")
    assert [d["url"] for d in r["dead"]] == ["https://a.example/doc", "https://d.example/doc"] and r["runners_only"] == []


def test_without_the_key_nothing_is_downloaded(guide_dir, tmp_path, monkeypatch):
    (guide_dir / "vault-watch.toml").write_text(MANIFEST, encoding="utf-8")
    monkeypatch.setattr(forge, "get", lambda: pytest.fail("the forge is not asked"))
    r = verify.run_sources(guide_dir, tmp_path, {}, None)
    assert r["summary"].endswith("(usually fine in a browser)") and r["weekly"] == ""


def test_the_key_names_an_artifact_and_a_json_file(tmp_path):
    for bad in ('"sources.json"', '"freshness-report/"', "3"):
        (tmp_path / "vault-watch.toml").write_text(MANIFEST + f"sources_weekly = {bad}\n", encoding="utf-8")
        with pytest.raises(guide.GuideError, match="sources_weekly"):
            guide.load(tmp_path)


def test_the_replacement_opens_the_dead_address_first(guide_dir, tmp_path):
    class LLM:
        def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
            self.system, self.prompt, self.web = system, prompt, web
            return verify.Findings(findings=[verify.Finding(pages=["page.md"], severity="Minor",
                                                            problem="https://a.example/doc moved to https://a.example/new.")]), {"cost_usd": 0.2}

    llm = LLM()
    dead = [{"url": "https://a.example/doc", "status": "dead", "code": 404, "pages": ["page.md"]},
            {"url": "https://d.example/doc", "status": "dead", "code": 404, "pages": ["page.md"]}]
    r = verify.run_deadlinks(guide_dir, tmp_path, {"sources": {"dead": dead}}, llm)
    assert llm.web and "first open the dead URL itself" in llm.system and "report no finding for it" in llm.system
    assert r["summary"] == "2 dead sources, 1 to replace (the others opened and still say what the guide cites them for)"
