"""End-to-end run of the graph on a throwaway vault, with a fake model.

Checks the two human pauses, the deterministic check of quoted text, groups
of corrections, the English mirror, and that the vault is only modified on a
branch, after the review.
"""

import json
import subprocess
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from vault_watch_agent import vault
from vault_watch_agent.crosscheck import ConsistencyEdit, CorrectionReview, CrossCheck
from vault_watch_agent.graph import Deps, build
from vault_watch_agent.state import (
    Correction,
    ClusterProposal,
    ItemOutcome,
    MirrorEdit,
    MirrorResult,
    TriageDecision,
    TriageResult,
)

PAGE = """---
title: Moteurs d'inférence
last_modified: "2026-06-10"
---

vLLM 0.31 est la version minimale recommandée[^1].

Ollama reste le plus simple pour démarrer.

[^1]: vLLM, notes de version 0.31.
"""

PAGE_EN = """---
title: Inference engines
last_modified: "2026-06-10"
---

vLLM 0.31 is the recommended minimum version[^1].

Ollama remains the easiest way to start.

[^1]: vLLM, 0.31 release notes.
"""


def correction(current, proposed, severity="Major", group="", page="03-stack/engines.md"):
    return Correction(item_ids=["W1"], page=page, current=current, proposed=proposed, source_url="https://example.org/vllm",
                      severity=severity, rationale="floor moved", group=group)


class FakeLLM:
    def __init__(self):
        self.calls = []

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
        self.calls.append(node)
        usage = {"node": node, "model": "fake", "input": 10, "output": 5, "cache_read": 0}
        if schema is CrossCheck:
            assert web and '<page path="03-stack/engines.md">' in context  # the whole vault, sources online
            return CrossCheck(
                reviews=[
                    CorrectionReview(id="C1", verdict="revise", reason="say the month",
                                     revised="vLLM 0.33 est la version minimale recommandée depuis novembre 2026[^1]."),
                    CorrectionReview(id="C3", verdict="keep", reason="matches the release", revised=""),
                ],
                consistency_edits=[
                    ConsistencyEdit(page="03-stack/engines.md", current="Ollama reste le plus simple pour démarrer.",
                                    proposed="Ollama reste le plus simple pour démarrer (vLLM 0.33 ensuite).",
                                    reason="same floor elsewhere", related_to=["C1"]),
                ],
                other_findings=["a doubt elsewhere"],
            ), usage
        if schema is TriageResult:
            assert "vault_contract" in system  # the vault's own brief is loaded at run time
            return TriageResult(decisions=[
                TriageDecision(item_id="W1", action="correct", reason="new minimum", search_terms=["vLLM"]),
                TriageDecision(item_id="W2", action="drop", reason="noise", search_terms=[]),
                TriageDecision(item_id="W3", action="correct", reason="new model", search_terms=["LFM3"]),
            ]), usage
        if schema is MirrorResult:
            assert "vLLM 0.31 is the recommended minimum version" in prompt
            return MirrorResult(problem="", edits=[
                MirrorEdit(current="vLLM 0.31 is the recommended minimum version[^1].",
                           proposed="vLLM 0.33 is the recommended minimum version (November 2026)[^1]."),
                MirrorEdit(current="[^1]: vLLM, 0.31 release notes.", proposed="[^1]: vLLM, 0.33 release notes."),
            ]), usage
        assert "vLLM 0.31 est la version minimale" in prompt  # the excerpt reached the model
        return ClusterProposal(
            outcomes=[ItemOutcome(item_id="W1", event="2026-11-01: vLLM 0.33 fixes a high advisory", no_change_reason="")],
            corrections=[
                correction("vLLM 0.31 est la version minimale recommandée[^1].",
                           "vLLM 0.33 est la version minimale recommandée (novembre 2026)[^1].", group="a"),
                correction("texte inventé par le modèle", "x", severity="Minor"),
                correction("[^1]: vLLM, notes de version 0.31.", "[^1]: vLLM, notes de version 0.33.",
                           severity="Minor", group="a"),
                # Same passage as C1, from a parallel line of thought: refused by the conflict check.
                correction("vLLM 0.31 est la version minimale", "vLLM 0.32 est la version minimale", severity="Minor"),
            ],
        ), usage


def sh(*cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def setup(tmp_path: Path):
    repo = tmp_path / "vault"
    (repo / "03-stack").mkdir(parents=True)
    (repo / "03-stack" / "engines.md").write_text(PAGE, encoding="utf-8")
    (repo / "en" / "03-stack").mkdir(parents=True)
    (repo / "en" / "03-stack" / "engines.md").write_text(PAGE_EN, encoding="utf-8")
    (repo / ".agents" / "skills" / "vault-watch").mkdir(parents=True)
    (repo / ".agents" / "skills" / "vault-watch" / "brief.md").write_text("# Watch brief\n", encoding="utf-8")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "audit-freshness.mjs").write_text(
        "import { writeFileSync } from 'node:fs';\n"
        "const out = process.argv.find(a => a.startsWith('--json=')).slice(7);\n"
        "writeFileSync(out, JSON.stringify({claimsDue: [{page: '03-stack/engines.md', claim: 'x', recheckBy: '2026-10-24'}]}));\n",
        encoding="utf-8",
    )
    (repo / "scripts" / "run-audits.mjs").write_text("console.log('audits ok')\n", encoding="utf-8")
    (repo / "scripts" / "audit-sources.mjs").write_text(
        "import { writeFileSync } from 'node:fs';\n"
        "const out = process.argv.find(a => a.startsWith('--json=')).slice(7);\n"
        "writeFileSync(out, JSON.stringify({sources: [\n"
        "  {url: 'https://example.org/gone', probe: {status: 'dead', code: 404}, citations: [{page: '03-stack/engines.md'}]},\n"
        "  {url: 'https://example.org/vllm', probe: {status: 'ok', code: 200}, citations: [{page: '03-stack/engines.md'}]},\n"
        "  {url: 'https://example.org/other', probe: {status: 'dead', code: 404}, citations: [{page: 'elsewhere.md'}]},\n"
        "]}));\n",
        encoding="utf-8",
    )
    sh("git", "init", "-q", "-b", "main", cwd=repo)
    sh("git", "config", "user.name", "t", cwd=repo)
    sh("git", "config", "user.email", "t@t", cwd=repo)
    sh("git", "add", ".", cwd=repo)
    sh("git", "commit", "-qm", "init", cwd=repo)

    watch = tmp_path / "watch.json"
    watch.write_text(json.dumps({"until": "2026-11-02", "items": [
        {"title": "vllm v0.33.0", "url": "https://example.org/vllm", "triage": "keep", "notes": "floor"},
        {"title": "some blog post", "url": "https://example.org/blog", "triage": "keep"},
        {"title": "LFM3 released", "url": "https://example.org/lfm3", "triage": "keep"},
        {"title": "dropped by the script", "url": "https://example.org/x", "triage": "drop"},
    ]}), encoding="utf-8")
    llm = FakeLLM()
    deps = Deps(vault=repo, home=tmp_path / "home", llm=llm, today="2026-11-08")
    return deps, watch, llm


def test_run_pauses_twice_and_applies_only_accepted(setup):
    deps, watch, llm = setup
    graph = build(deps, InMemorySaver())
    config = {"configurable": {"thread_id": "t1"}}

    graph.invoke({"source": str(watch), "issue": None}, config)
    first = graph.get_state(config).tasks[0].interrupts[0].value
    assert first["step"] == "review"
    checks = {c["id"]: c["check"] for c in first["corrections"]}
    assert checks == {"C1": "ok", "C2": "text-not-found", "C3": "ok", "C4": "conflict with C1", "C5": "ok"}
    groups = {c["id"]: c.get("group") for c in first["corrections"]}
    assert groups == {"C1": "C1", "C2": None, "C3": "C1", "C4": None, "C5": "C1"}  # footnote and cross-check edit join C1
    assert llm.calls == ["triage", "propose W1", "crosscheck"]  # W2 dropped, W3 not in the vault
    decisions = {d["item_id"]: d for d in graph.get_state(config).values["decisions"]}
    assert decisions["W3"]["action"] == "addition"  # unlocated item becomes an addition candidate
    report = Path(first["report"]).read_text(encoding="utf-8")
    assert "text-not-found" in report and "2026-10-24" in report and "LFM3" in report
    assert "revised by the cross-check" in report and "a doubt elsewhere" in report
    assert "0.31" in (deps.vault / "03-stack" / "engines.md").read_text(encoding="utf-8")  # untouched

    graph.invoke(Command(resume=["C1"]), config)  # naming C1 accepts its group (C3, C5)
    second = graph.get_state(config).tasks[0].interrupts[0].value
    assert second["step"] == "publish" and second["audit_ok"] and second["mirror_problems"] == []
    # Only the sources of the changed pages, and only those that do not answer
    assert second["link_problems"] == ["dead 404: https://example.org/gone (03-stack/engines.md)"]
    state = graph.get_state(config).values
    assert state["applied"] == ["C1", "C3", "C5"]
    wt = Path(state["worktree"])
    edited = (wt / "03-stack" / "engines.md").read_text(encoding="utf-8")
    assert "0.33 est la version minimale recommandée depuis novembre 2026" in edited and "notes de version 0.33" in edited
    assert "(vLLM 0.33 ensuite)" in edited
    assert 'last_modified: "2026-11-08"' in edited
    english = (wt / "en" / "03-stack" / "engines.md").read_text(encoding="utf-8")
    assert "vLLM 0.33 is the recommended" in english and 'last_modified: "2026-11-08"' in english
    assert state["mirrored"] == ["en/03-stack/engines.md"]
    assert "0.31" in (deps.vault / "03-stack" / "engines.md").read_text(encoding="utf-8")  # main untouched

    graph.invoke(Command(resume=False), config)  # no push
    assert not graph.get_state(config).next
    assert "pr_url" not in graph.get_state(config).values


def test_review_none_ends_without_branch(setup):
    deps, watch, _ = setup
    graph = build(deps, InMemorySaver())
    config = {"configurable": {"thread_id": "t2"}}
    graph.invoke({"source": str(watch), "issue": None}, config)
    graph.invoke(Command(resume="none"), config)
    assert not graph.get_state(config).next
    assert not (deps.home / "worktrees").exists()


def test_check_and_apply_keep_crlf(tmp_path):
    page = tmp_path / "p.md"
    page.write_bytes(PAGE.replace("\n", "\r\n").encode("utf-8"))
    assert vault.check(tmp_path, "p.md", "Ollama reste") == "ok"
    assert vault.check(tmp_path, "p.md", "absent") == "text-not-found"
    vault.apply(tmp_path, "p.md", "Ollama reste", "Ollama demeure", "2026-11-08")
    raw = page.read_bytes().decode("utf-8")
    assert "Ollama demeure" in raw and "\r\n" in raw and "\n" not in raw.replace("\r\n", "")


def test_clusters_merge_items_sharing_a_page_but_not_through_a_hub():
    from vault_watch_agent.graph import clusters

    ex = lambda *pages: [{"page": p, "text": f"text of {p}"} for p in pages]
    evidence = {"W1": ex("jan.md", "security.md"), "W2": ex("jan.md"), "W3": ex("litellm.md", "security.md"),
                "W4": ex("security.md"), "W5": ex("security.md"), "W6": ex("security.md")}
    groups = sorted(sorted(ids) for ids, _ in clusters(evidence))
    # security.md is cited for 5 items: a hub, it does not merge Jan with LiteLLM
    assert groups == [["W1", "W2"], ["W3"], ["W4"], ["W5"], ["W6"]]
    # The same tool merges whatever the pages: five Jan advisories make a hub of jan.md otherwise
    jan = {f"J{n}": ex("jan.md") for n in range(6)}
    assert len(clusters(jan)) == 6
    assert len(clusters(jan, {i: ["Jan"] for i in jan})) == 1


def test_fix_run_enters_the_graph_after_the_proposals(setup):
    from vault_watch_agent import fix

    deps, _, llm = setup
    graph = build(deps, InMemorySaver())
    config = {"configurable": {"thread_id": "fix"}}
    item = {"id": "F1", "domain": "fix", "tier": "", "title": "vLLM floor outdated", "url": "", "date": "",
            "urgent": False, "severity": "", "notes": ""}
    proposal = {"item_ids": ["F1"], "outcomes": [{"item_id": "F1", "event": "", "no_change_reason": ""}],
                "corrections": [{**correction("vLLM 0.31 est la version minimale recommandée[^1].",
                                              "vLLM 0.33 est la version minimale recommandée[^1].").model_dump(),
                                 "item_ids": ["F1"], "check": "ok"}]}
    state = fix.initial_state("test", [item], proposal, {"node": "fix", "model": "fake", "input": 1, "output": 1})
    graph.update_state(config, state, as_node="propose")
    graph.invoke(None, config)
    paused = graph.get_state(config)
    assert paused.tasks[0].interrupts[0].value["step"] == "review"
    assert llm.calls == ["crosscheck"]  # straight to numbering and cross-check, no triage
    assert Path(paused.values["report_path"]).name.startswith("fix-vault-errors-")


def test_link_problems_put_new_broken_links_first_and_blocked_last():
    from vault_watch_agent.graph import link_problems

    src = lambda url, status, page="p.md": {"url": url, "probe": {"status": status, "code": 404}, "citations": [{"page": page}]}
    report = {"sources": [src("https://old/dead", "dead"), src("https://site/403", "blocked"),
                          src("https://new/dead", "dead"), src("https://fine", "ok"), src("https://far", "dead", "q.md")]}
    rows = link_problems(report, {"p.md"}, "+ see https://new/dead")
    assert rows[0].startswith("NEW dead 404: https://new/dead")
    assert rows[1].startswith("dead 404: https://old/dead")
    assert "anti-bot" in rows[2] and len(rows) == 3
