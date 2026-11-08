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

    def parse(self, *, system, prompt, schema, effort, node):
        self.calls.append(node)
        usage = {"node": node, "model": "fake", "input": 10, "output": 5, "cache_read": 0}
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
    assert checks == {"C1": "ok", "C2": "text-not-found", "C3": "ok", "C4": "conflict with C1"}
    groups = {c["id"]: c.get("group") for c in first["corrections"]}
    assert groups == {"C1": "C1", "C2": None, "C3": "C1", "C4": None}  # sentence + footnote travel together
    assert llm.calls == ["triage", "propose W1"]  # W2 dropped, W3 not in the vault
    decisions = {d["item_id"]: d for d in graph.get_state(config).values["decisions"]}
    assert decisions["W3"]["action"] == "addition"  # unlocated item becomes an addition candidate
    report = Path(first["report"]).read_text(encoding="utf-8")
    assert "text-not-found" in report and "2026-10-24" in report and "LFM3" in report
    assert "0.31" in (deps.vault / "03-stack" / "engines.md").read_text(encoding="utf-8")  # untouched

    graph.invoke(Command(resume=["C1"]), config)  # naming C1 accepts its group (C3)
    second = graph.get_state(config).tasks[0].interrupts[0].value
    assert second["step"] == "publish" and second["audit_ok"] and second["mirror_problems"] == []
    state = graph.get_state(config).values
    assert state["applied"] == ["C1", "C3"]
    wt = Path(state["worktree"])
    edited = (wt / "03-stack" / "engines.md").read_text(encoding="utf-8")
    assert "vLLM 0.33 est la version minimale" in edited and "notes de version 0.33" in edited
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
