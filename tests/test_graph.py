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
from vault_watch_agent.graph import Deps, build, pr_body
from vault_watch_agent.verify import Finding, Findings
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
        if schema is CrossCheck and node == "sweep":
            assert web and '<page path="03-stack/engines.md">' in context  # same prefix as the cross-check: cached
            assert "03-stack/engines.md:" in prompt and "Déployez vLLM 0.31" in prompt
            return CrossCheck(reviews=[], other_findings=["a sweep doubt"], consistency_edits=[
                ConsistencyEdit(page="03-stack/engines.md", current="Déployez vLLM 0.31 en production.",
                                proposed="Déployez vLLM 0.33 en production.", reason="old minimum", related_to=["C1"]),
            ]), {**usage, "node": "sweep"}
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
        if schema is Findings:
            assert "<page path=" in (context or "") or "<pair page=" in prompt
            return Findings(findings=[Finding(pages=["03-stack/engines.md"], problem="floor differs from another page",
                                              severity="Major")]), usage
        if node == "fix translation":
            assert not web and '<page path="03-stack/engines.md">' in context
            assert '<page path="en/03-stack/engines.md">' in context  # the pair, not the whole guide
            return ClusterProposal(
                outcomes=[ItemOutcome(item_id="F1", event="", no_change_reason=""),
                          ItemOutcome(item_id="F2", event="", no_change_reason="same meaning")],
                corrections=[correction("Ollama remains the easiest way to start.",
                                        "Ollama is still the simplest way to get started.", page="en/03-stack/engines.md")],
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


def test_translation_run_edits_the_english_page_without_crosscheck_or_mirror(setup):
    from vault_watch_agent import fix

    deps, _, llm = setup
    graph = build(deps, InMemorySaver())
    config = {"configurable": {"thread_id": "fix-tr"}}
    findings = ["[Minor] en/03-stack/engines.md: the Ollama sentence drifts from the French.",
                "[Minor] 03-stack/engines.md: footnote wording differs."]
    items, proposal, usage = fix.propose_translation(deps.vault, findings, llm)
    graph.update_state(config, fix.initial_state("test", items, proposal, usage, "fix-tr", "translation"),
                       as_node="propose")
    graph.invoke(None, config)
    first = graph.get_state(config).tasks[0].interrupts[0].value
    assert first["step"] == "review" and [c["check"] for c in first["corrections"]] == ["ok"]
    assert llm.calls == ["fix translation"]  # no cross-check against the whole French guide

    graph.invoke(Command(resume="all"), config)
    state = graph.get_state(config).values
    assert llm.calls == ["fix translation"]  # nothing to mirror: the English page was the one fixed
    wt = Path(state["worktree"])
    assert "simplest way to get started" in (wt / "en" / "03-stack" / "engines.md").read_text(encoding="utf-8")
    assert "0.31" in (wt / "03-stack" / "engines.md").read_text(encoding="utf-8")  # French untouched
    assert state["title"].startswith("fix(i18n)") and state["branch"] == "fix/fix-tr"


def test_unsafe_edits_are_refused():
    from vault_watch_agent.graph import mark_unsafe

    note = "[^11]: vLLM, release v0.31."
    cs = [
        {"id": "C1", "group": "C1", "check": "ok", "current": f"{note}\n\n| metric |", "proposed": "\n| metric |"},
        {"id": "C2", "group": "C1", "check": "ok", "current": "[^10]: vLLM, metrics.", "proposed": "[^10]: vLLM, metrics."},
        {"id": "C3", "group": "C3", "check": "ok", "current": f"{note}\n| a |", "proposed": "| a |"},
        {"id": "C4", "group": "C3", "check": "ok", "current": "[^10]: x.", "proposed": f"[^10]: x.\n{note}"},
    ]
    mark_unsafe(cs)
    assert [c["check"] for c in cs] == ["drops footnote [^11]", "no change", "ok", "ok"]  # C3 + C4: a real move


def test_link_problems_put_new_broken_links_first_and_blocked_last():
    from vault_watch_agent.graph import link_problems

    src = lambda url, status, page="p.md": {"url": url, "probe": {"status": status, "code": 404}, "citations": [{"page": page}]}
    report = {"sources": [src("https://old/dead", "dead"), src("https://site/403", "blocked"),
                          src("https://new/dead", "dead"), src("https://fine", "ok"), src("https://far", "dead", "q.md")]}
    rows = link_problems(report, {"p.md"}, "+ see https://new/dead")
    assert rows[0].startswith("NEW dead 404: https://new/dead")
    assert rows[1].startswith("dead 404: https://old/dead")
    assert "anti-bot" in rows[2] and len(rows) == 3


def test_clusters_give_each_item_its_share_of_excerpts():
    from vault_watch_agent.graph import ITEM_EXCERPTS, clusters

    big = lambda tag, n: [{"page": "hub.md", "text": f"{tag} {k} " + "x" * 2000} for k in range(n)]
    evidence = {"W1": big("first", 20), "W2": big("second", 3) + [{"page": "dgx.md", "text": "DGX Spark price"}]}
    [(ids, excerpts)] = clusters(evidence, {"W1": ["Spark"], "W2": ["Spark"]})
    texts = [e["text"] for e in excerpts]
    assert any(t == "DGX Spark price" for t in texts)  # the last item is not crowded out
    assert sum(len(t) for t in texts if t.startswith("first")) <= ITEM_EXCERPTS + 2100


def test_pr_closes_the_watch_issue():
    state = {"source": "issue #55", "issue": 55, "corrections": [], "applied": [], "audit_ok": True}
    assert pr_body(state).rstrip().endswith("Closes #55.")
    assert "Closes" not in pr_body({**state, "issue": None})  # fix runs have no issue


def test_sync_fast_forwards_main_before_a_run(setup):
    deps, _, _ = setup
    origin = deps.vault.parent / "origin.git"
    sh("git", "clone", "-q", "--bare", str(deps.vault), str(origin), cwd=deps.vault.parent)
    sh("git", "remote", "add", "origin", str(origin), cwd=deps.vault)
    other = deps.vault.parent / "other"
    sh("git", "clone", "-q", str(origin), str(other), cwd=deps.vault.parent)
    (other / "merged.md").write_text("merged elsewhere\n", encoding="utf-8")
    sh("git", "add", ".", cwd=other)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "merged PR", cwd=other)
    sh("git", "push", "-q", "origin", "main", cwd=other)

    vault.sync(deps.vault)
    assert (deps.vault / "merged.md").is_file()  # checked-out main fast-forwarded

    sh("git", "checkout", "-q", "-b", "elsewhere", cwd=deps.vault)
    (other / "merged.md").write_text("merged again\n", encoding="utf-8")
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "second PR", cwd=other)
    sh("git", "push", "-q", "origin", "main", cwd=other)
    vault.sync(deps.vault)  # main not checked out: updated in place
    log = subprocess.run(["git", "log", "-1", "--format=%s", "main"], cwd=deps.vault,
                         capture_output=True, text=True, check=True).stdout
    assert log.strip() == "second PR"


def commit_page(deps, text):
    (deps.vault / "03-stack" / "engines.md").write_text(text, encoding="utf-8")
    sh("git", "add", ".", cwd=deps.vault)
    sh("git", "commit", "-qm", "page", cwd=deps.vault)


def test_the_sweep_turns_remaining_values_into_corrections(setup):
    deps, watch, llm = setup
    commit_page(deps, PAGE.replace("Ollama reste", "Déployez vLLM 0.31 en production.\n\n"
                                                   "La 0.31 a corrigé une faille.\n\nOllama reste"))
    graph = build(deps, InMemorySaver())
    config = {"configurable": {"thread_id": "sweep"}}
    graph.invoke({"source": str(watch), "issue": None}, config)
    assert llm.calls == ["triage", "propose W1", "crosscheck", "sweep"]
    values = graph.get_state(config).values
    added = next(c for c in values["corrections"] if c["current"] == "Déployez vLLM 0.31 en production.")
    assert added["group"] == "C1" and added["review"] == "added by the sweep for C1"
    # The sweep did not erase the verdicts of the cross-check
    assert next(c for c in values["corrections"] if c["id"] == "C1")["review"].startswith("revised")
    assert "a doubt elsewhere" in values["findings"] and "a sweep doubt" in values["findings"]
    assert [h["line"] for h in values["leftovers"]] == [10]  # history: the model left it, the reviewer sees it
    report = Path(values["report_path"]).read_text(encoding="utf-8")
    assert "Removed values still present" in report and "03-stack/engines.md:10" in report


def test_leftovers_find_variants_and_skip_replaced_text_and_footnotes(tmp_path):
    page = """---
title: x
---

Installez la roue cu129 si besoin.

Le pilote CUDA 12 reste accepté.

CUDA 13 suffit, Qwen3.31 aussi, et 10.31 n'a rien à voir.

Sur 0.31.x, fixez `--old-flag`.

Ancien texte en 0.31.0 avec CUDA 12.9 et -cu129 et --old-flag.

[^1]: Notes de la 0.31.0.
"""
    (tmp_path / "p.md").write_text(page, encoding="utf-8")
    c = {"id": "C1", "page": "p.md", "check": "ok", "proposed": "Nouveau texte en 0.33.0.",
         "current": "Ancien texte en 0.31.0 avec CUDA 12.9 et -cu129 et --old-flag."}
    hits = {h["line"]: h["tokens"] for h in vault.leftovers(tmp_path, [c])}
    assert hits == {5: ["cu129"], 7: ["CUDA 12"], 11: ["--old-flag", "0.31"]}
    assert vault.leftovers(tmp_path, [{**c, "check": "text-not-found"}]) == []  # an invalid edit removes nothing


def test_a_value_the_replacement_keeps_is_not_a_leftover(tmp_path):
    (tmp_path / "p.md").write_text("Texte A en 0.31.\n\nAilleurs 0.31.\n", encoding="utf-8")
    c = {"id": "C1", "page": "p.md", "check": "ok", "current": "Texte A en 0.31.", "proposed": "Texte B, avant la 0.31.0."}
    assert vault.leftovers(tmp_path, [c]) == []


def test_unsourced_versions_read_the_footnotes_as_they_will_be(tmp_path):
    page = """Déployez la 0.31[^1].

Le plancher est 0.31 selon la note[^2].

Case à cocher 0.31 sans note.

[^1]: Notes de la 0.31.
[^2]: Notes de la 0.31.
"""
    (tmp_path / "p.md").write_text(page, encoding="utf-8")
    cs = [
        {"id": "C1", "page": "p.md", "check": "ok", "current": "Déployez la 0.31", "proposed": "Déployez la 0.33"},
        {"id": "C2", "page": "p.md", "check": "ok", "current": "Le plancher est 0.31", "proposed": "Le plancher est 0.33"},
        {"id": "C3", "page": "p.md", "check": "ok", "current": "[^2]: Notes de la 0.31.", "proposed": "[^2]: Notes de la v0.33.0rc3."},
        {"id": "C4", "page": "p.md", "check": "ok", "current": "Case à cocher 0.31", "proposed": "Case à cocher 0.33"},
    ]
    assert vault.unsourced_versions(tmp_path, cs) == {"C1": "adds 0.33, which the footnotes it cites ([^1]) do not mention"}


def test_the_warning_reaches_the_report(setup):
    deps, watch, _ = setup
    commit_page(deps, PAGE.replace("[^1]: vLLM, notes de version 0.31.", "[^1]: vLLM, notes de version 0.31 (bis)."))
    graph = build(deps, InMemorySaver())
    config = {"configurable": {"thread_id": "warn"}}
    graph.invoke({"source": str(watch), "issue": None}, config)
    values = graph.get_state(config).values
    # The footnote edit no longer matches, so nothing brings 0.33 into [^1]
    assert "do not mention" in next(c for c in values["corrections"] if c["id"] == "C1")["warning"]
    assert "⚠️ Source: adds 0.33" in Path(values["report_path"]).read_text(encoding="utf-8")


def test_apply_commits_the_floors_the_guide_script_aligns(setup):
    deps, watch, _ = setup
    floors = deps.vault / ".agents" / "vault-maintenance"
    floors.mkdir(parents=True)
    (floors / "version-floors.json").write_text('{"floors": {"adv-vllm": "0.31.0"}}\n', encoding="utf-8")
    (deps.vault / "scripts" / "audit-version-floors.mjs").write_text(
        "import { writeFileSync } from 'node:fs';\n"
        "if (process.argv.includes('--write')) writeFileSync('.agents/vault-maintenance/version-floors.json', "
        "'{\"floors\": {\"adv-vllm\": \"0.33.0\"}}\\n');\n",
        encoding="utf-8",
    )
    sh("git", "add", ".", cwd=deps.vault)
    sh("git", "commit", "-qm", "floors", cwd=deps.vault)
    graph = build(deps, InMemorySaver())
    config = {"configurable": {"thread_id": "floors"}}
    graph.invoke({"source": str(watch), "issue": None}, config)
    graph.invoke(Command(resume=["C1"]), config)
    wt = Path(graph.get_state(config).values["worktree"])
    shown = subprocess.run(["git", "show", "HEAD~1:.agents/vault-maintenance/version-floors.json"], cwd=wt,
                           capture_output=True, text=True, check=True).stdout
    assert "0.33.0" in shown  # in the commit of the corrections, the mirror commit comes after


def test_a_date_bump_alone_is_left_to_apply():
    assert vault.date_bump_only('last_modified: "2026-10-10"', 'last_modified: "2026-11-08"')
    assert not vault.date_bump_only("vLLM 0.31", "vLLM 0.33")
