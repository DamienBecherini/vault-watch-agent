"""End-to-end run of the graph on a throwaway vault, with a fake model.

Checks the two human pauses, the deterministic check of quoted text, and that
the vault is only modified on a branch, after the review.
"""

import json
import subprocess
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from vault_watch_agent import vault
from vault_watch_agent.graph import Deps, build
from vault_watch_agent.state import Correction, ItemProposal, TriageDecision, TriageResult

PAGE = """---
title: Moteurs d'inférence
last_modified: "2026-06-10"
---

vLLM 0.31 est la version minimale recommandée.

Ollama reste le plus simple pour démarrer.
"""


class FakeLLM:
    def __init__(self):
        self.calls = []

    def parse(self, *, system, prompt, schema, effort, node):
        self.calls.append(node)
        usage = {"node": node, "model": "fake", "input": 10, "output": 5, "cache_read": 0}
        if schema is TriageResult:
            return TriageResult(decisions=[
                TriageDecision(item_id="W1", action="correct", reason="new minimum", search_terms=["vLLM"]),
                TriageDecision(item_id="W2", action="drop", reason="noise", search_terms=[]),
            ]), usage
        assert "vLLM 0.31 est la version minimale" in prompt  # the excerpt reached the model
        return ItemProposal(
            event="2026-11-01: vLLM 0.33 fixes a high advisory",
            no_change_reason="",
            corrections=[
                Correction(page="03-stack/engines.md", current="vLLM 0.31 est la version minimale recommandée.",
                           proposed="vLLM 0.33 est la version minimale recommandée (novembre 2026).",
                           source_url="https://example.org/vllm", severity="Major", rationale="floor moved"),
                Correction(page="03-stack/engines.md", current="texte inventé par le modèle",
                           proposed="x", source_url="https://example.org", severity="Minor", rationale="hallucinated"),
            ],
        ), usage


def sh(*cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def setup(tmp_path: Path):
    repo = tmp_path / "vault"
    (repo / "03-stack").mkdir(parents=True)
    (repo / "03-stack" / "engines.md").write_text(PAGE, encoding="utf-8")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "audit-freshness.mjs").write_text(
        "import { writeFileSync } from 'node:fs';\n"
        "const out = process.argv.find(a => a.startsWith('--json=')).slice(7);\n"
        "writeFileSync(out, JSON.stringify({claimsDue: [{page: '03-stack/engines.md', claim: 'x', recheckBy: '2026-10-24'}]}));\n",
        encoding="utf-8",
    )
    (repo / "scripts" / "run-audits.mjs").write_text("console.log('audits ok')\n", encoding="utf-8")
    sh("git", "init", "-q", "-b", "main", cwd=repo)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "add", ".", cwd=repo)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init", cwd=repo)
    sh("git", "config", "user.name", "t", cwd=repo)
    sh("git", "config", "user.email", "t@t", cwd=repo)

    watch = tmp_path / "watch.json"
    watch.write_text(json.dumps({"until": "2026-11-02", "items": [
        {"title": "vllm v0.33.0", "url": "https://example.org/vllm", "triage": "keep", "notes": "floor"},
        {"title": "some blog post", "url": "https://example.org/blog", "triage": "keep"},
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
    paused = graph.get_state(config)
    first = paused.tasks[0].interrupts[0].value
    assert first["step"] == "review"
    checks = {c["id"]: c["check"] for c in first["corrections"]}
    assert checks == {"C1": "ok", "C2": "text-not-found"}
    assert llm.calls == ["triage", "propose W1"]  # W2 dropped, never sent to propose
    report = Path(first["report"]).read_text(encoding="utf-8")
    assert "text-not-found" in report and "2026-10-24" in report
    assert "0.31" in (deps.vault / "03-stack" / "engines.md").read_text(encoding="utf-8")  # untouched

    graph.invoke(Command(resume="all"), config)  # "all" = valid ones: C2 is refused
    second = graph.get_state(config).tasks[0].interrupts[0].value
    assert second["step"] == "publish" and second["audit_ok"]
    state = graph.get_state(config).values
    assert state["applied"] == ["C1"]
    edited = (Path(state["worktree"]) / "03-stack" / "engines.md").read_text(encoding="utf-8")
    assert "vLLM 0.33 est la version minimale" in edited and 'last_modified: "2026-11-08"' in edited
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
