"""The other way to look for what is new: the web explored chapter by chapter (leads that come with their sources),
a lead dug deeper in a call of its own, and what an addition run left without an edit."""

import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vault_watch_agent import news, steps, verify
from vault_watch_agent.crosscheck import CorrectionReview, CrossCheck
from vault_watch_agent.graph import Deps
from vault_watch_agent.llm import ModelError
from vault_watch_agent.state import ClusterProposal, Correction, ItemOutcome

MANIFEST = """schema = 1
[guide]
name = "Test"
[content]
language = "fr"
readonly = ["projet/**"]
"""
PAGES = {
    "vault-watch.toml": MANIFEST,
    "02-materiel/cards.md": "# Cartes\n\nLa génération actuelle est la série 50 (janvier 2025).\n",
    "03-stack/engines.md": "# Moteurs\n\n| Outil | Version |\n| :-- | :-- |\n| vLLM | 0.33 |\n",
    "03-stack/models.md": "# Modèles\n\nLe modèle de référence est Alpha 3.\n",
    "projet/changelog.md": "# Journal\n\nUne longue histoire.\n",
}


def sh(*cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def guide(tmp_path: Path, monkeypatch) -> Path:
    from vault_watch_agent import chapters

    monkeypatch.setattr(chapters, "SMALL_KB", 0)  # one chapter per folder, however light (the automatic rule gathers them)
    repo = tmp_path / "guide"
    for rel, text in PAGES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8", newline="\n")
    sh("git", "init", "-q", "-b", "main", cwd=repo)
    sh("git", "config", "user.name", "t", cwd=repo)
    sh("git", "config", "user.email", "t@t", cwd=repo)
    sh("git", "add", ".", cwd=repo)
    sh("git", "commit", "-qm", "init", cwd=repo)
    return repo


def found(problem, pages, *sources):
    return news.Lead(kind="found", pages=list(pages), problem=problem, sources=list(sources))


FOUND = {
    "02-materiel": [found("the 60 series shipped on 2026-10-02; the guide still presents the 50 series as current.",
                          ["02-materiel/cards.md"], "https://example.org/series-60")],
    "03-stack": [found("Alpha 4 was released on 2026-11-03 with open weights.", ["03-stack/models.md"], "https://example.org/alpha-4"),
                 # the same source as the first chapter's lead: one lead, with the pages of both
                 found("the 60 series needs engine 0.40.", ["03-stack/engines.md"], "https://example.org/series-60")],
}


class Api:
    """As llm.Claude: it says when its answer begins, so the first call writes the cache and the others wait for it."""
    signals_start = True

    def __init__(self, fail=()):
        self.lock, self.order, self.begun, self.fail = threading.Lock(), [], threading.Event(), set(fail)

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False, started=None):
        chapter = prompt.split("Chapter to explore: ")[1].split("\n")[0]
        assert schema is news.Leads and web and effort == "high" and node == f"verify explore {chapter}"
        assert context.startswith("<guide>") and "projet/changelog.md" in context  # the whole guide, whatever the chapter
        assert "You explore the web" in system and "about 12 searches and 15 pages" in system and "<vault_contract" in system
        assert "<<" not in system.split("<vault_contract")[0]
        with self.lock:
            self.order.append((chapter, started is not None, self.begun.is_set()))
        if chapter in self.fail:
            raise ModelError(f"{node}: overloaded")
        if started:
            self.begun.set()
            started()
        return news.Leads(findings=FOUND[chapter]), {"node": node, "cost_usd": 2.0}


def test_the_web_is_explored_one_call_per_chapter_with_the_whole_guide(guide):
    assert news.explorable(guide) == {"02-materiel": ["02-materiel/cards.md"],
                                      "03-stack": ["03-stack/engines.md", "03-stack/models.md"]}  # not the read-only chapter
    api = Api()
    leads, usages, failed = news.explore(guide, api)
    assert api.order == [("02-materiel", True, False), ("03-stack", False, True)] and not failed and len(usages) == 2
    assert [lead.problem[:12] for lead in leads] == ["the 60 serie", "Alpha 4 was "]
    assert leads[0].pages == ["02-materiel/cards.md", "03-stack/engines.md"]  # merged on their common source
    assert news.line(leads[1]) == ("[Found on the web] 03-stack/models.md: Alpha 4 was released on 2026-11-03 with open "
                                   "weights. Sources: https://example.org/alpha-4")
    # Only the chapters asked; a chapter that is not one of the guide's is ignored
    only = Api()
    leads, _, _ = news.explore(guide, only, ["03-stack", "nowhere"])
    assert [c for c, _, _ in only.order] == ["03-stack"] and len(leads) == 2
    assert news.explore(guide, Api(), ["nowhere"]) == ([], [], {})


def test_a_chapter_whose_call_fails_is_said_and_the_others_go_on(guide, tmp_path):
    work = tmp_path / "verif"
    work.mkdir()
    result = verify.run_explore(guide, work, {}, Api(fail={"02-materiel"}))
    assert result["summary"].startswith("2 leads from 1 chapter(s); not explored, the call failed: 02-materiel (verify explore")
    assert result["ok"] is False and result["chapters"] == ["03-stack"] and len(result["usage"]) == 1
    with pytest.raises(ModelError, match="overloaded"):  # every call failed: the check says it could not run
        verify.run_explore(guide, work, {}, Api(fail={"02-materiel", "03-stack"}))
    (work / "options.json").write_text('{"chapters": ["02-materiel"]}', encoding="utf-8")
    result = verify.run_explore(guide, work, {}, Api())
    assert result["summary"] == "1 leads from 1 chapter(s)" and result["chapters"] == ["02-materiel"]
    assert result["findings"][0].endswith("Sources: https://example.org/series-60")
    assert verify.options(tmp_path / "nowhere") == {} and verify.BY_ID["explore"].fix_mode == "add"
    assert steps.of_node("verify explore 03-stack") == "explore" and steps.STEPS["explore"].needs == ("web", "whole_guide")
    estimate = verify.estimates(guide, {})
    assert estimate["explore"]["usd"] > 0 and estimate["explore"]["usd_chapter"] > estimate["add-run"]["usd_each"]
    assert estimate["add-run"]["usd_deep"] > estimate["add-run"]["usd_each"]


def test_another_engine_explores_one_chapter_after_the_other(guide):
    seen = []

    class Other:
        def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
            seen.append(node)
            return news.Leads(findings=[]), {"node": node, "cost_usd": 0.0}

    assert news.explore(guide, Other()) == ([], [{"node": "verify explore 02-materiel", "cost_usd": 0.0},
                                                 {"node": "verify explore 03-stack", "cost_usd": 0.0}], {})
    assert seen == ["verify explore 02-materiel", "verify explore 03-stack"]


def test_a_lead_dug_deeper_has_a_call_of_its_own(guide):
    leads = [f"[Found on the web] 03-stack/models.md: lead {n}. Sources: https://example.org/{n}" for n in range(1, 7)]
    calls = {}

    class Llm:
        def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
            ids = [part.split('"')[0] for part in prompt.split('<lead id="')[1:]]
            calls[node] = (prompt.split(":")[0], ids)
            assert "« Lead to dig deeper »" in system and "start from those addresses" in system  # the same for every call
            return ClusterProposal(outcomes=[ItemOutcome(item_id=i, event="", no_change_reason="-") for i in ids],
                                   corrections=[]), {"node": node, "cost_usd": 1.0}

    items, proposals, _ = news.propose(guide, leads, Llm(), deep={leads[1], "a lead that is not in the run"})
    assert calls == {"add 1/3": ("Leads", ["F1", "F3", "F4", "F5"]), "add 2/3": ("Leads", ["F6"]),
                     "add 3/3": ("Lead to dig deeper", ["F2"])}
    assert [i["id"] for i in items] == ["F1", "F2", "F3", "F4", "F5", "F6"]
    calls.clear()
    news.propose(guide, leads[:2], Llm())
    assert calls == {"add": ("Leads", ["F1", "F2"])}


class RunLLM:
    """The exploration, the additions and their cross-check, as a model would answer them."""

    def __init__(self):
        self.calls = []

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
        self.calls.append((node, prompt.split(":")[0]))
        usage = {"node": node, "model": "fake", "input": 10, "output": 5, "cache_read": 0, "cost_usd": 1.0}
        if schema is news.Leads:
            return news.Leads(findings=FOUND[prompt.split("Chapter to explore: ")[1].split("\n")[0]][:1]), usage
        if schema is CrossCheck:
            return CrossCheck(reviews=[CorrectionReview(id="C1", verdict="keep", reason="the vendor's page says so", revised="")],
                              consistency_edits=[], other_findings=[]), usage
        if prompt.startswith("Lead to dig deeper"):
            return ClusterProposal(outcomes=[ItemOutcome(item_id="F1", event="2026-10-02: the 60 series shipped", no_change_reason="")],
                                   corrections=[Correction(
                                       item_ids=["F1"], page="02-materiel/cards.md", severity="Major", group="",
                                       current="La génération actuelle est la série 50 (janvier 2025).",
                                       proposed="La génération actuelle est la série 60 (octobre 2026).",
                                       source_url="https://example.org/series-60", rationale="superseded")]), usage
        return ClusterProposal(outcomes=[ItemOutcome(item_id="F2", event="", no_change_reason="Alpha 4 is a preview: no weights yet")],
                               corrections=[]), usage


def test_the_leads_of_an_exploration_go_to_an_addition_run(guide, tmp_path):
    from vault_watch_agent.web import Settings, create_app

    llm = RunLLM()
    deps = Deps(vault=guide, home=tmp_path / "home", llm=llm, today="2026-11-20")
    act = {"X-Vault-Watch": "1"}
    c = TestClient(create_app(Settings(vault=guide, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    options = {o["id"]: o for o in c.get("/api/verifications/options").json()}
    assert options["explore"]["chapters"] == [{"id": "02-materiel", "pages": 1, "kb": 0.1, "explore": True},
                                              {"id": "03-stack", "pages": 2, "kb": 0.1, "explore": True}]
    assert options["explore"]["usd_chapter"] > 0 and options["explore"]["run_usd_deep"] > options["explore"]["run_usd_each"]
    assert "chapters" not in options["news"] and "never writes a new page" in options["explore"]["limit"]["en"]
    vid = c.post("/api/verifications", json={"checks": ["explore"], "chapters": ["02-materiel", "03-stack"]}, headers=act).json()["id"]
    for _ in range(200):
        v = c.get(f"/api/verifications/{vid}").json()
        if not v["running"]:
            break
        time.sleep(0.05)
    leads = v["results"]["explore"]["findings"]
    assert len(leads) == 2 and v["results"]["explore"]["mode"] == "add" and v["results"]["explore"]["chapters"] == ["02-materiel", "03-stack"]
    thread = c.post("/api/fix", json={"text": "\n".join(leads), "verification": vid, "mode": "add", "deep": [leads[0]]},
                    headers=act).json()["thread"]
    for _ in range(200):
        run = c.get(f"/api/runs/{thread}").json()
        if run["status"] != "running":
            break
        time.sleep(0.05)
    assert run["status"] == "review" and [x["id"] for x in run["corrections"]] == ["C1"]
    assert ("add 2/2", "Lead to dig deeper") in llm.calls and ("add 1/2", "Leads") in llm.calls
    # What the search found without writing anything is shown at the review, not only in the report
    assert run["unchanged"] == [{"id": "F2", "lead": leads[1], "why": "Alpha 4 is a preview: no weights yet"}]
    assert run["pages_to_write"] == []


def test_the_lists_show_the_newest_runs_and_give_the_older_ones_on_request(guide, tmp_path):
    from vault_watch_agent.web import Settings, create_app

    deps = Deps(vault=guide, home=tmp_path / "home", llm=RunLLM(), today="2026-11-20")
    act = {"X-Vault-Watch": "1"}
    c = TestClient(create_app(Settings(vault=guide, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    threads = []
    for _ in range(3):
        thread = c.post("/api/fix", json={"text": news.line(FOUND["02-materiel"][0]), "mode": "add"}, headers=act).json()["thread"]
        for _ in range(200):
            if c.get(f"/api/runs/{thread}").json()["status"] != "running":
                break
            time.sleep(0.05)
        threads.append(thread)
    every = c.get("/api/runs").json()
    assert [r["thread"] for r in every] == threads[::-1] and {r["status"] for r in every} == {"review"}  # the newest first
    assert [r["thread"] for r in c.get("/api/runs", params={"limit": 2}).json()] == threads[:0:-1]
    # Asked again: the same answer, from what the first reading kept of each run; a run that moves is read again
    assert c.get("/api/runs").json() == every
    c.post(f"/api/runs/{threads[0]}/review", json={"accept": "none"}, headers=act)
    for _ in range(200):
        if c.get(f"/api/runs/{threads[0]}").json()["status"] != "running":
            break
        time.sleep(0.05)
    assert {r["thread"]: r["status"] for r in c.get("/api/runs").json()}[threads[0]] == "nothing-applied"
    assert c.get("/api/verifications", params={"limit": 1}).json() == []

