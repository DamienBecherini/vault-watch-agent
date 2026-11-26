"""The candidates of the registry judged with the whole guide (ROADMAP D4): one call, a judgement per candidate kept
in the registry, the candidates to add as leads of an addition run."""

import json
import subprocess
from pathlib import Path

import pytest

from vault_watch_agent import candidates, news, opportunity, verify
from vault_watch_agent.quotes import Quote

MANIFEST = """schema = 1
[guide]
name = "Test"
description = "running AI models on one's own servers"
[content]
language = "fr"
exclude = ["watch/**", "tiers.md"]
[watch]
candidates = "watch/candidates.json"
source_tiers = "tiers.md"
"""

MODELS = """# Modèles

Pour un serveur de 48 Go, la famille Qwen3 en 30B-A3B est le choix par défaut.
"""


def sh(*cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def guide(tmp_path: Path):
    """A guide whose registry holds three open candidates and a dismissed one."""
    root = tmp_path / "guide"
    reg = candidates.Registry(root / "watch" / "candidates.json")
    reg.note("Larkdb 3", "https://github.com/lark/larkdb", origin="watch issue-30", seen="2026-11-02", kind="tool")
    reg.note("Qwen3.5 32B", "https://huggingface.co/Qwen/Qwen3.5-32B", origin="hand", seen="2026-11-10", kind="model")
    reg.note("Qwen3.5 32B", "https://simonwillison.net/2026/Nov/10/qwen35/", origin="watch issue-31", seen="2026-11-17")
    reg.note("Beam 501B", "", origin="hand", seen="2026-11-20")
    reg.move("beam-501b", "watching", today="2026-11-20", reason="weights announced for later", recheck="2026-12-20")
    reg.note("Old thing", "https://example.org/old", origin="hand", seen="2026-10-01")
    reg.move("old-thing", "dismissed", today="2026-10-01", reason="off topic")
    reg.save()
    for rel, text in {"vault-watch.toml": MANIFEST, "02-modeles/choix.md": MODELS,
                      "tiers.md": "## Tier A\n\n- huggingface.co\n- github.com\n\n## Tier B\n\n- simonwillison.net\n"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8", newline="\n")
    sh("git", "init", "-q", "-b", "main", cwd=root)
    sh("git", "config", "user.name", "t", cwd=root)
    sh("git", "config", "user.email", "t@t", cwd=root)
    sh("git", "add", "-A", cwd=root)
    sh("git", "commit", "-qm", "init", cwd=root)
    return root


class FakeLLM:
    def __init__(self):
        self.calls = []

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
        self.calls.append({"system": system, "prompt": prompt, "node": node, "web": web, "context": context})
        assert schema is opportunity.Judgements and not web and '<page path="02-modeles/choix.md">' in context
        usage = {"node": node, "model": "fake", "input": 10, "output": 5, "cache_read": 0, "cost_usd": 0.5}
        return opportunity.Judgements(findings=[
            opportunity.Judgement(id="qwen3-5-32b", verdict="add", pages=["02-modeles/choix.md"], title="Qwen3.5",
                                  problem="a successor of the default family; check the model card and whether the "
                                          "default for a 48 GB server changes.",
                                  excerpts=[Quote(page="02-modeles/choix.md", quote="Pour un serveur de 48 Go, la famille "
                                                  "Qwen3 en 30B-A3B est le choix par défaut.")],
                                  detail=news.LeadDetail(says="a", guide="b", check="c", matters="It may change the default model.")),
            opportunity.Judgement(id="beam-501b", verdict="watch", problem="no weights yet.", recheck="2026-12-20"),
            opportunity.Judgement(id="larkdb-3", verdict="dismiss", problem="a database: off the guide's subject."),
            opportunity.Judgement(id="larkdb-3", verdict="watch", problem="a second judgement of one candidate: ignored."),
            opportunity.Judgement(id="not-asked", verdict="add", problem="a candidate not listed: ignored."),
        ]), usage


def test_the_open_candidates_are_judged_with_the_whole_guide(guide, tmp_path):
    llm = FakeLLM()
    work = tmp_path / "verif"
    work.mkdir()
    result = verify.run_candidates(guide, work, {}, llm)  # no options: the registry the guide has (command line)
    call = llm.calls[0]
    assert len(llm.calls) == 1 and call["node"] == "verify candidates"
    # The open candidates, the most seen first; not the dismissed one. Their sources, state and score are read.
    asked = [c.split('"')[0] for c in call["prompt"].split('<candidate id="')[1:]]
    assert asked == ["qwen3-5-32b", "larkdb-3", "beam-501b"]
    assert "score 10 (huggingface.co/qwen A, simonwillison.net B; 2 week(s))" in call["prompt"]
    assert "state: watching (weights announced for later), look again on 2026-12-20" in call["prompt"]
    assert "Judge every candidate listed, once" in call["system"] and "<vault_contract" in call["system"]
    assert result["summary"] == "3 of 3 candidates judged: 1 to add, 1 to watch, 1 to dismiss"
    line = ("[Seen by the watch] 02-modeles/choix.md: Qwen3.5 32B: a successor of the default family; check the model "
            "card and whether the default for a 48 GB server changes. Sources: https://huggingface.co/Qwen/Qwen3.5-32B, "
            "https://simonwillison.net/2026/Nov/10/qwen35/")
    assert result["findings"] == [line] and result["details"][line]["title"] == "Qwen3.5 32B"
    assert result["excerpts"][line][0]["line"] == 3
    assert result["judgements"] == [
        {"id": "qwen3-5-32b", "verdict": "add", "why": "a successor of the default family; check the model card and "
         "whether the default for a 48 GB server changes.", "pages": ["02-modeles/choix.md"], "matters": "It may change the default model."},
        {"id": "larkdb-3", "verdict": "dismiss", "why": "a database: off the guide's subject."},
        {"id": "beam-501b", "verdict": "watch", "why": "no weights yet.", "recheck": "2026-12-20"}]
    assert [u["cost_usd"] for u in result["usage"]] == [0.5]


def test_no_open_candidate_no_call(guide, tmp_path):
    work = tmp_path / "verif"
    work.mkdir()
    (work / "options.json").write_text(json.dumps({"candidates": []}), encoding="utf-8")
    llm = FakeLLM()
    assert verify.run_candidates(guide, work, {}, llm)["summary"] == "no open candidate in the registry"
    assert llm.calls == []


def test_the_judgements_are_kept_in_the_draft_of_the_registry(guide, tmp_path):
    home = tmp_path / "home"
    g = candidates.guide_mod.load(guide)
    chosen = candidates.to_judge(g, home)
    assert [c["id"] for c in chosen] == ["qwen3-5-32b", "larkdb-3", "beam-501b"] and chosen[0]["score"]["corroborated"]
    assert [c["id"] for c in candidates.to_judge(g, home, ["old-thing"])] == ["old-thing"]  # named: whatever its state
    n = candidates.judged(g, home, [{"id": "beam-501b", "verdict": "watch", "why": "no weights yet.", "recheck": "2026-12-20"},
                                    {"id": "gone", "verdict": "add", "why": "x"}], check="verif-1", today="2026-11-26")
    assert n == 1
    draft = candidates.Registry.load(candidates.draft_path(home))
    beam = draft.get("beam-501b")
    assert beam["judgement"] == {"date": "2026-11-26", "check": "verif-1", "verdict": "watch", "why": "no weights yet.",
                                 "recheck": "2026-12-20"}
    assert beam["state"] == "watching" and beam["history"][-1]["note"] == "judged with the guide (verif-1): watch"
    base = candidates.Registry.load(guide / "watch" / "candidates.json")
    assert candidates.changes(base.candidates, draft.candidates) == [{"what": "judged", "name": "Beam 501B", "verdict": "watch"}]
    assert candidates.said({"what": "judged", "name": "Beam 501B", "verdict": "watch"}) == "**Beam 501B** judged with the guide: watch"


def test_the_server_judges_the_registry_as_the_page_shows_it_and_keeps_the_judgements(guide, tmp_path):
    import time

    from fastapi.testclient import TestClient

    from vault_watch_agent.graph import Deps
    from vault_watch_agent.web import Settings, create_app

    home = tmp_path / "home"
    deps = Deps(vault=guide, home=home, llm=FakeLLM(), today="2026-11-26")
    c = TestClient(create_app(Settings(vault=guide, home=home, config_home=home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    act = {"X-Vault-Watch": "1"}
    c.post("/api/candidates/larkdb-3", json={"state": "dismissed", "reason": "not for us"}, headers=act)  # in the draft only
    options = {o["id"]: o for o in c.get("/api/verifications/options").json()}
    assert "2 open candidate(s)" in options["candidates"]["note"]["en"]
    vid = c.post("/api/verifications", json={"checks": ["candidates"], "lang": "en"}, headers=act).json()["id"]
    for _ in range(200):
        v = c.get(f"/api/verifications/{vid}").json()
        if not v["running"]:
            break
        time.sleep(0.05)
    r = v["results"]["candidates"]
    assert r["mode"] == "add" and r["kept"] == 2 and len(r["findings"]) == 1  # larkdb-3, dismissed in the draft, not asked
    asked = [x["id"] for x in json.loads((home / "verifications" / vid / "options.json").read_text(encoding="utf-8"))["candidates"]]
    assert asked == ["qwen3-5-32b", "beam-501b"]
    page = {x["id"]: x for x in c.get("/api/candidates").json()["candidates"]}
    assert page["qwen3-5-32b"]["judgement"]["verdict"] == "add" and page["qwen3-5-32b"]["judgement"]["check"] == vid
    assert "judgement" not in page["larkdb-3"]


def test_the_check_is_priced_by_the_open_candidates(guide):
    est = verify.estimates(guide, {"candidates": 3})["candidates"]
    none = verify.estimates(guide, {})["candidates"]
    assert est["usd"] > none["usd"] > 0 and "3 open candidate(s)" in est["note"]["en"]
    assert verify.BY_ID["candidates"].fix_mode == "add" and verify.BY_ID["candidates"].kind == "news"
