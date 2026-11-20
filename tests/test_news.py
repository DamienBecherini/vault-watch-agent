"""Look for what is new: the leads (one call that reads the guide and what past watches set aside, nothing verified),
then the additions as a run of the graph (each lead checked on the web, a few per call)."""

import subprocess
import threading
import time
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vault_watch_agent import fix, news, steps, verify
from vault_watch_agent.crosscheck import CorrectionReview, CrossCheck
from vault_watch_agent.graph import Deps
from vault_watch_agent.quotes import Quote
from vault_watch_agent.state import ClusterProposal, Correction, ItemOutcome

MANIFEST = """schema = 1
[guide]
name = "Test"
description = "running AI models on one's own servers"
[content]
language = "fr"
readonly = ["projet/**"]
"""

ENGINES = """---
title: Moteurs
last_modified: "2026-06-10"
---

# Moteurs

vLLM 0.33 est la version minimale recommandée au T2 2026[^1].

| Outil | Version |
| :-- | :-- |
| vLLM | 0.33 |

[^1]: vLLM, notes de version 0.33, <https://example.org/vllm-033>.
"""

HARDWARE = """# Matériel

La génération actuelle de cartes est la série 50 (janvier 2025).
"""

REPORT_OLD = """# Watch report — 2026-10-26

## Addition candidates (not written, opportunity notes need a go-ahead)

- W2 [Speech models in Ollama](https://ollama.com/blog/speech-models): Ollama now runs speech models locally.
- W9 [[AINews] It's Swapping Season](https://latent.space/p/swapping/): reports an open-weight release; verify.

## Noticed elsewhere in the vault by the cross-check (not proposed)

- W1 [not a candidate](https://example.org/no): another section.
"""

REPORT_NEW = """# Watch report — 2026-11-09

## Addition candidates (not written, opportunity notes need a go-ahead)

- W48 [Build specialized models with LFM3](https://huggingface.co/blog/LiquidAI/lfm3): no page names it.
- W50 [Speech models in Ollama](https://ollama.com/blog/speech-models): seen again, with word-level timestamps.
"""

LEADS = ["[Newer] 02-materiel/cards.md: the guide presents the 50 series (January 2025) as current; check the vendor's "
         "page for a newer generation.",
         "[Seen by the watch] 03-stack/engines.md: Ollama runs speech models locally; check its release notes and "
         "whether the engines table should say so.",
         f"[Missing] {news.NO_PAGE}: nothing on the EU obligations for a model served in-house; check the official text."]


def sh(*cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


class FakeLLM:
    """The leads, the additions and the cross-check of a run, as a model would answer them."""

    def __init__(self):
        self.calls, self.prompts = [], {}

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
        self.calls.append((node, web))
        self.prompts[node] = (system, prompt)
        usage = {"node": node, "model": "fake", "input": 10, "output": 5, "cache_read": 0, "cost_usd": 1.0}
        if schema is news.Leads:
            assert not web and '<page path="03-stack/engines.md">' in context
            return news.Leads(findings=[
                news.Lead(kind="newer", pages=["02-materiel/cards.md"], problem=LEADS[0].split(": ", 1)[1],
                          excerpts=[Quote(page="02-materiel/cards.md",
                                          quote="La génération actuelle de cartes est la série 50 (janvier 2025).")]),
                news.Lead(kind="candidate", pages=["03-stack/engines.md"], problem=LEADS[1].split(": ", 1)[1]),
                news.Lead(kind="missing", pages=[], problem=LEADS[2].split(": ", 1)[1]),
                news.Lead(kind="newer", pages=["projet/changelog.md"], problem="a read-only page."),
            ]), usage
        if schema is CrossCheck:
            assert web and "You review proposed corrections" in system
            return CrossCheck(reviews=[CorrectionReview(id="C1", verdict="keep", reason="the release notes say so", revised="")],
                              consistency_edits=[], other_findings=[]), usage
        assert node == "add" and web and "Leads:" in prompt and '<lead id="F2">' in prompt
        return ClusterProposal(
            outcomes=[ItemOutcome(item_id="F1", event="", no_change_reason="the vendor's page shows no newer generation"),
                      ItemOutcome(item_id="F2", event="2026-10-20: Ollama 0.14 runs speech models", no_change_reason=""),
                      ItemOutcome(item_id="F3", event="", no_change_reason="needs a page: the obligations, under 06-ops")],
            corrections=[Correction(item_ids=["F2"], page="03-stack/engines.md", current="| vLLM | 0.33 |",
                                    proposed="| vLLM | 0.33 |\n| Ollama (voix) | 0.14 |", severity="Major", group="",
                                    source_url="https://example.org/ollama-014", rationale="speech models, new in 0.14")],
        ), usage


@pytest.fixture
def setup(tmp_path: Path):
    repo = tmp_path / "guide"
    for rel, text in {"vault-watch.toml": MANIFEST, "03-stack/engines.md": ENGINES, "02-materiel/cards.md": HARDWARE,
                      "projet/changelog.md": "# Journal\n\nUne longue histoire.\n"}.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8", newline="\n")
    sh("git", "init", "-q", "-b", "main", cwd=repo)
    sh("git", "config", "user.name", "t", cwd=repo)
    sh("git", "config", "user.email", "t@t", cwd=repo)
    sh("git", "add", ".", cwd=repo)
    sh("git", "commit", "-qm", "init", cwd=repo)
    home = tmp_path / "home"
    (home / "reports").mkdir(parents=True)
    today = date.today().isoformat()
    (home / "reports" / f"watch-{today}-issue9.md").write_text(REPORT_NEW, encoding="utf-8")
    llm = FakeLLM()
    return Deps(vault=repo, home=home, llm=llm, today=today), llm


# -- what past watches set aside ----------------------------------------------------------------------------------
def test_the_candidates_are_read_from_the_reports_of_the_watches(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "watch-2026-10-26-issue49.md").write_text(REPORT_OLD, encoding="utf-8")
    (reports / "chore-watch-2026-11-09.md").write_text(REPORT_NEW, encoding="utf-8", newline="\r\n")
    (reports / "eval-issue49-full.md").write_text(REPORT_OLD.replace("ollama.com", "replay.example"), encoding="utf-8")
    (reports / "watch-2026-03-01-issue3.md").write_text(REPORT_OLD.replace("ollama.com", "old.example"), encoding="utf-8")
    (reports / "fix-fix-2026-11-08.md").write_text("# Fix\n\n## Addition candidates (not written)\n\nNone.\n", encoding="utf-8")
    found = news.candidates(reports, date(2026, 11, 20))
    # The most recent first; an address seen twice keeps its latest watch; a title may hold brackets
    assert [(c["date"], c["url"]) for c in found] == [
        ("2026-11-09", "https://ollama.com/blog/speech-models"), ("2026-11-09", "https://huggingface.co/blog/LiquidAI/lfm3"),
        ("2026-10-26", "https://latent.space/p/swapping/")]
    assert found[0]["why"] == "seen again, with word-level timestamps." and found[2]["title"] == "[AINews] It's Swapping Season"
    assert not any("example" in c["url"] for c in found)  # a replay, a watch too old, another section
    assert news.candidates(tmp_path / "nowhere", date(2026, 11, 20)) == []
    assert news.listing(found).count("\n") == 3 and "2026-11-09: Build specialized models with LFM3 <https://" in news.listing(found)
    assert "nothing aside" in news.listing([])
    assert news.reports_of(tmp_path / "home" / "verifications" / "verif-1") == tmp_path / "home" / "reports"
    assert news.reports_of(reports) == reports


# -- the leads ----------------------------------------------------------------------------------------------------
def test_the_leads_read_the_guide_and_the_candidates_and_verify_nothing(setup):
    deps, llm = setup
    result = verify.run_news(deps.vault, deps.home / "verifications" / "verif-1", {}, llm)
    system, prompt = llm.prompts["verify news"]
    assert llm.calls == [("verify news", False)]  # one call, without the web
    assert "what a reader would expect to find" in system and f"Today is {date.today().isoformat()}" in system
    assert "running AI models on one's own servers" in system and "read-only" in system  # the guide, from its manifest
    assert "<vault_contract" in system and system.rstrip().endswith("</vault_contract>")  # its threshold for additions, last
    assert "<<" not in system and "at most 30 leads" in system
    assert "Build specialized models with LFM3 <https://huggingface.co/blog/LiquidAI/lfm3>" in prompt and prompt.endswith("List the leads.")
    assert result["findings"] == LEADS and result["ok"] is False  # the lead about a read-only page alone is left out
    assert result["summary"] == "3 leads, 2 item(s) set aside by past watches read"
    assert result["excerpts"][LEADS[0]][0]["match"] == "exact" and LEADS[2] not in result["excerpts"]
    assert verify.BY_ID["news"].fix_mode == "add" and verify.plan(["news"]) == ["news"]
    estimate = verify.estimates(deps.vault, {})
    assert estimate["news"]["usd"] > 0 and estimate["add-run"]["usd"] > 0 and estimate["add-run"]["usd_each"] > 0
    assert steps.STEPS["add"].needs == ("web", "whole_guide") and steps.of_node("add 2/3") == "add" and steps.of_node("verify news") == "news"
    assert subprocess.run(["git", "status", "--porcelain"], cwd=deps.vault, capture_output=True, text=True).stdout == ""


# -- the additions: a run of the graph -------------------------------------------------------------------------------
def test_the_leads_are_grouped_a_few_per_call_by_the_pages_they_share():
    #                       0           1      2           3      4       5
    pages = [["a/x.md", "b/y.md"], ["c/z.md"], ["b/y.md"], [], ["a/w.md"], ["c/z.md"]]
    assert news.batches(pages, 3) == [[0, 2, 4], [1, 3, 5]]  # the same page first, then the same chapter
    assert news.batches(pages, 4) == [[0, 1, 2, 4], [3, 5]] and news.batches([], 4) == []
    assert [len(b) for b in news.batches([[]] * 9)] == [4, 4, 1]


def test_every_call_reads_the_whole_guide_and_the_web(setup):
    from vault_watch_agent.llm import ModelError

    deps, _ = setup
    leads = [*LEADS, LEADS[0] + " Again.", LEADS[1] + " Again."]
    lock, order, begun = threading.Lock(), [], threading.Event()

    class Api:
        signals_start = True  # as llm.Claude: the first call writes the cache, the others wait for its answer to begin

        def parse(self, *, system, prompt, schema, effort, node, context=None, web=False, started=None):
            assert web and effort == "high" and context.startswith("<guide>") and "projet/changelog.md" in context
            assert "You look for what is new" in system and "The whole guide is above" in system and "<<" not in system
            assert "Replace, do not pile up" in system and "<vault_contract" in system
            with lock:
                order.append((node, started is not None, begun.is_set()))
            if started:
                begun.set()
                started()
            ids = [part.split('"')[0] for part in prompt.split('<lead id="')[1:]]
            if node == "add 2/2":
                error = ModelError("add: the answer was cut before its end")
                error.usage = {"node": node, "cost_usd": 2.0, "cut": True}
                raise error
            return ClusterProposal(outcomes=[ItemOutcome(item_id=i, event="", no_change_reason="nothing new") for i in ids],
                                   corrections=[]), {"node": node, "cost_usd": 1.0}

    items, proposals, usages = news.propose(deps.vault, leads, Api())
    assert order == [("add 1/2", True, False), ("add 2/2", False, True)]
    assert [i["id"] for i in items] == ["F1", "F2", "F3", "F4", "F5"] and len(proposals[0]["item_ids"]) == 4
    assert "the call failed" in proposals[1]["outcomes"][0]["no_change_reason"] and sum(u["cost_usd"] for u in usages) == 3.0

    seen = []

    class Other:  # an engine that does not say when its answer begins: the whole guide all the same, one call at a time
        def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
            assert web and context.startswith("<guide>") and "<pages>" not in prompt
            seen.append(node)
            ids = [part.split('"')[0] for part in prompt.split('<lead id="')[1:]]
            return ClusterProposal(outcomes=[ItemOutcome(item_id=i, event="", no_change_reason="-") for i in ids],
                                   corrections=[]), {"node": node, "cost_usd": 1.0}

    news.propose(deps.vault, leads, Other())
    assert seen == ["add 1/2", "add 2/2"]
    state = fix.initial_state("add-2026-11-20", items, proposals, usages, "add-2026-11-20", "add")
    assert state["mode"] == "add" and state["branch_name"] == "feat/add-2026-11-20"
    assert state["title"] == "feat(content): reviewed additions to the guide (add-2026-11-20)"


def test_the_leads_of_the_check_go_to_an_addition_run(setup, tmp_path):
    from vault_watch_agent.web import Settings, create_app

    deps, llm = setup
    act = {"X-Vault-Watch": "1"}
    c = TestClient(create_app(Settings(vault=deps.vault, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    options = {o["id"]: o for o in c.get("/api/verifications/options").json()}
    assert options["news"]["usd"] > 0 and options["news"]["run_usd"] > 0 and options["news"]["run_usd_each"] > 0
    vid = c.post("/api/verifications", json={"checks": ["news"]}, headers=act).json()["id"]
    for _ in range(200):
        v = c.get(f"/api/verifications/{vid}").json()
        if not v["running"]:
            break
        time.sleep(0.05)
    assert v["checks"] == ["news"] and v["results"]["news"]["mode"] == "add" and v["results"]["news"]["findings"] == LEADS
    thread = c.post("/api/fix", json={"text": "\n".join(LEADS), "verification": vid, "mode": "add"}, headers=act).json()["thread"]
    assert thread.startswith("add-")
    for _ in range(200):
        run = c.get(f"/api/runs/{thread}").json()
        if run["status"] != "running":
            break
        time.sleep(0.05)
    assert run["status"] == "review" and run["mode"] == "add"
    assert [(x["id"], x["page"], x["check"]) for x in run["corrections"]] == [("C1", "03-stack/engines.md", "ok")]
    assert ("add", True) in llm.calls and ("crosscheck", True) in llm.calls  # the web for the additions and their review
    assert c.get(f"/api/verifications/{vid}").json()["counts"] == {"open": 0, "fix": 3, "dismissed": 0}
    report = (deps.home / "reports" / f"feat-{thread}.md").read_text(encoding="utf-8")
    assert "needs a page: the obligations, under 06-ops" in report and "| Ollama (voix) | 0.14 |" in report
    # The run writes no new page: said before the corrections, with the page its lead would need
    assert run["pages_to_write"] == [{"id": "F3", "lead": LEADS[2], "what": "the obligations, under 06-ops"}]
    assert "never writes a new page" in options["news"]["what"]["en"] and "jamais de nouvelle page" in options["news"]["what"]["fr"]
    top = report.split("## Corrections")[0]
    assert "## New pages: not written" in top and "1 lead(s) would need a page of their own" in top
    assert "- **F3** the obligations, under 06-ops" in top


def test_the_pull_request_of_an_addition_run_says_what_it_did_not_write():
    from vault_watch_agent.graph import pr_body, render_report

    correction = {"id": "C1", "item_id": "F1", "item_ids": ["F1"], "page": "a.md", "severity": "Major", "group": "C1",
                  "rationale": "new in 0.14", "source_url": "https://example.org/a", "current": "x", "proposed": "x\ny",
                  "check": "ok", "proposal": 0}
    state = {"mode": "add", "source": "what a reader would look for and not find (add-1)", "as_of": "2026-11-20",
             "corrections": [correction], "applied": ["C1"], "decisions": [], "audit_ok": True, "mirrored": [], "issue": None,
             "items": [{"id": "F1", "domain": "fix", "url": "", "title": "[Newer] a.md: check the release notes."},
                       {"id": "F2", "domain": "fix", "url": "", "title": "[Missing] no page yet: the obligations."}],
             "proposals": [{"item_ids": ["F1", "F2"], "corrections": [correction], "outcomes": [
                 {"item_id": "F1", "event": "2026-10-20: 0.14", "no_change_reason": ""},
                 {"item_id": "F2", "event": "", "no_change_reason": "« Needs a page: » the obligations, under 06-ops"}]}]}
    body = pr_body(state)
    assert body.startswith("Additions from what a reader would look for and not find (add-1), each checked on primary sources")
    assert "Not written: 1 subject(s) that would need a page of their own" in body and "- the obligations, under 06-ops\n" in body
    assert "Leads:\n\n- F1: [Newer] a.md" in body and "Reported errors" not in body
    assert news.pages_to_write({**state, "proposals": [{"outcomes": [{"item_id": "F1", "no_change_reason": "nothing new"}]}]}) == []
    none = render_report({**state, "proposals": [{"item_ids": ["F1"], "corrections": [correction], "outcomes": state["proposals"][0]["outcomes"][:1]}]},
                         [], [correction])
    assert "never writes a new page. None of its leads asked for one." in none
    assert "## New pages" not in render_report({**state, "mode": "fix"}, state["proposals"], [correction])  # an addition run only
