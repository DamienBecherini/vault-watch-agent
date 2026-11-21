"""Compaction: the report of what weighs, the trims as a run of the graph, and what the code checks itself
(passages removed cleanly, notes left without a sentence, values no page states any more)."""

import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from vault_watch_agent import compact, fix, vault, verify
from vault_watch_agent.crosscheck import CorrectionReview, CrossCheck
from vault_watch_agent.graph import Deps, build, pr_body
from vault_watch_agent.quotes import Quote
from vault_watch_agent.state import ClusterProposal, Correction, ItemOutcome, MirrorEdit, MirrorResult

MANIFEST = """schema = 1
[guide]
name = "Test"
[content]
language = "fr"
mirrors = { en = "en/" }
modified_field = "last_modified"
readonly = ["projet/**"]
[budget]
page_kb = 1
"""

PADDING = "Un moteur d'inférence sert un modèle sur le réseau. " * 20  # the page is over its budget of 1 KB

ENGINES = """---
title: Moteurs
last_modified: "2026-06-10"
---

# Moteurs

PADDING

vLLM 0.33 est la version minimale recommandée[^1].

Auparavant, la version 0.31.2 suffisait[^2].

Le port 8000 doit rester fermé, voir la page sécurité.

| Outil | Version |
| :-- | :-- |
| vLLM | 0.33 |
| Ancien | 0.29 |

[^1]: vLLM, notes de version 0.33, https://example.org/vllm-033.
[^2]: vLLM, notes de version 0.31.2, https://example.org/vllm-031.
""".replace("PADDING", PADDING)

ENGINES_EN = """---
title: Engines
last_modified: "2026-06-10"
---

# Engines

vLLM 0.33 is the recommended minimum version[^1].

Previously, version 0.31.2 was enough[^2].

Port 8000 must stay closed, see the security page.

| Tool | Version |
| :-- | :-- |
| vLLM | 0.33 |
| Old | 0.29 |

[^1]: vLLM, 0.33 release notes, https://example.org/vllm-033.
[^2]: vLLM, 0.31.2 release notes, https://example.org/vllm-031.
"""

SECURITY = """---
title: Sécurité
last_modified: "2026-06-10"
---

# Sécurité

vLLM 0.33 est la version minimale recommandée, car elle corrige une faille.

N'exposez jamais le port 8000 sans authentification.
"""

SECURITY_EN = """---
title: Security
last_modified: "2026-06-10"
---

# Security

vLLM 0.33 is the recommended minimum version, because it fixes a flaw.

Never expose port 8000 without authentication.
"""

FINDINGS = ["[History] 03-stack/engines.md: « Auparavant, la version 0.31.2 suffisait » is superseded by the 0.33 floor.",
            "[Repeated] 03-stack/engines.md, 06-ops/security.md: the 0.33 floor is stated twice. Keep the full "
            "statement in 03-stack/engines.md."]


def trim(current, proposed, items, page="03-stack/engines.md", group=""):
    return Correction(item_ids=items, page=page, current=current, proposed=proposed, source_url="03-stack/engines.md",
                      severity="Minor", rationale="superseded", group=group)


class FakeLLM:
    def __init__(self):
        self.calls, self.prompts = [], {}

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
        self.calls.append(node)
        self.prompts[node] = (system, prompt)
        usage = {"node": node, "model": "fake", "input": 10, "output": 5, "cache_read": 0}
        if schema is compact.Trims:
            assert not web and '<page path="03-stack/engines.md">' in context and "en/03-stack" not in context
            return compact.Trims(findings=[
                compact.Trim(kind="history", pages=["03-stack/engines.md"], problem="the 0.31.2 note is superseded.",
                             excerpts=[Quote(page="03-stack/engines.md", quote="Auparavant, la version 0.31.2 suffisait[^2].")]),
                compact.Trim(kind="repeated", pages=["03-stack/engines.md", "06-ops/security.md"],
                             problem="the 0.33 floor is stated twice.", keep_in="03-stack/engines.md"),
                compact.Trim(kind="long", pages=["projet/changelog.md"], problem="a long history."),
            ]), usage
        if schema is CrossCheck:
            assert not web and "You review trims" in system and '<page path="06-ops/security.md">' in context
            assert 'id="C4"' in prompt and 'id="C5"' not in prompt  # the program's own removals are not judged
            return CrossCheck(reviews=[
                CorrectionReview(id="C1", verdict="keep", reason="history", revised=""),
                CorrectionReview(id="C2", verdict="revise", reason="say which page",
                                 revised="Version minimale de vLLM : voir [[03-stack/engines|Moteurs]]."),
                CorrectionReview(id="C3", verdict="keep", reason="an old row", revised=""),
            ], consistency_edits=[], other_findings=[]), usage
        if schema is MirrorResult and "en/03-stack/engines.md" in prompt:
            assert "A passage whose new text is empty was removed" in prompt
            return MirrorResult(problem="", edits=[
                MirrorEdit(current="Previously, version 0.31.2 was enough[^2].", proposed=""),
                MirrorEdit(current="| Old | 0.29 |", proposed=""),
                MirrorEdit(current="[^2]: vLLM, 0.31.2 release notes, https://example.org/vllm-031.", proposed=""),
            ]), usage
        if schema is MirrorResult:
            assert "An edit whose new text is empty" not in prompt  # nothing removed whole on this page
            return MirrorResult(problem="", edits=[
                MirrorEdit(current="vLLM 0.33 is the recommended minimum version, because it fixes a flaw.",
                           proposed="Minimum version of vLLM: see [[03-stack/engines|Engines]]."),
            ]), usage
        assert node == "compact" and not web and "Findings:" in prompt and '<finding id="F1">' in prompt
        # The pages the findings name, with the question (no other call reads them), not the whole guide
        assert "You trim" in system and context is None and "projet/changelog.md" not in prompt
        assert '<page path="03-stack/engines.md">' in prompt and '<page path="06-ops/security.md">' in prompt
        return ClusterProposal(
            outcomes=[ItemOutcome(item_id="F1", event="", no_change_reason=""),
                      ItemOutcome(item_id="F2", event="", no_change_reason="")],
            corrections=[
                trim("Auparavant, la version 0.31.2 suffisait[^2].", "", ["F1"]),
                trim("vLLM 0.33 est la version minimale recommandée, car elle corrige une faille.",
                     "Version minimale de vLLM : voir la page des moteurs.", ["F2"], page="06-ops/security.md"),
                trim("| Ancien | 0.29 |", "", ["F1"]),
                # Removes a note a sentence still cites: refused by the program
                trim("[^1]: vLLM, notes de version 0.33, https://example.org/vllm-033.", "", ["F1"]),
            ],
        ), usage


def sh(*cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def setup(tmp_path: Path):
    repo = tmp_path / "guide"
    for rel, text in {"vault-watch.toml": MANIFEST, "03-stack/engines.md": ENGINES, "en/03-stack/engines.md": ENGINES_EN,
                      "06-ops/security.md": SECURITY, "en/06-ops/security.md": SECURITY_EN,
                      "projet/changelog.md": "# Journal\n\nUne longue histoire.\n"}.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8", newline="\n")
    sh("git", "init", "-q", "-b", "main", cwd=repo)
    sh("git", "config", "user.name", "t", cwd=repo)
    sh("git", "config", "user.email", "t@t", cwd=repo)
    sh("git", "add", ".", cwd=repo)
    sh("git", "commit", "-qm", "init", cwd=repo)
    llm = FakeLLM()
    return Deps(vault=repo, home=tmp_path / "home", llm=llm, today="2026-11-20"), llm


# -- what the code does itself ---------------------------------------------------------------------------------
def test_a_passage_removed_whole_leaves_no_hole():
    text = "A.\n\nB.\n\nC.\n\n| x |\n| y |\n| z |\n"
    assert vault.replaced(text, "B.", "") == "A.\n\nC.\n\n| x |\n| y |\n| z |\n"  # a paragraph: one blank line stays
    assert vault.replaced(text, "| y |", "") == "A.\n\nB.\n\nC.\n\n| x |\n| z |\n"  # a table row: the table holds
    assert vault.replaced("One. Two. Three.\n", "Two. ", "") == "One. Three.\n"
    assert vault.replaced("One. Two. Three.\n", " Two.", "") == "One. Three.\n"
    assert vault.replaced("One. Two. Three.\n", "Two.", "") == "One. Three.\n"  # no double space left
    assert vault.replaced(text, "B.", "B2.") == text.replace("B.", "B2.")  # a replacement is a replacement
    assert vault.replaced("A.\n\nlast\n", "last", "") == "A.\n\n"


def test_lost_lists_what_no_page_states_any_more(setup):
    deps, _ = setup
    cs = [{"id": "C1", "page": "03-stack/engines.md", "check": "ok", "proposed": "",
           "current": "Auparavant, la version 0.31.2 suffisait[^2]."},
          {"id": "C2", "page": "06-ops/security.md", "check": "ok", "proposed": "Voir la page des moteurs.",
           "current": "vLLM 0.33 est la version minimale recommandée, car elle corrige une faille."}]
    assert vault.lost(deps.vault, cs) == {}  # 0.31.2 still in its note, 0.33 still in the page that keeps it
    cs.append({"id": "C3", "page": "03-stack/engines.md", "check": "ok", "proposed": "",
               "current": "[^2]: vLLM, notes de version 0.31.2, https://example.org/vllm-031."})
    assert vault.lost(deps.vault, cs) == {"C1": ["0.31.2"], "C3": ["0.31.2", "https://example.org/vllm-031"]}
    amounts = vault._facts("3,19 $ de l'heure, 48 Go, 12 %, CVE-2026-53998, --max-model-len, 12 pages")
    assert amounts == {"3,19 $", "48 Go", "12 %", "CVE-2026-53998", "--max-model-len"}


def test_a_note_left_without_a_sentence_goes_with_the_trim_that_orphans_it(setup):
    deps, _ = setup
    base = {"item_id": "F1", "item_ids": ["F1"], "proposal": 0, "source_url": "x", "severity": "Minor", "rationale": "r"}
    cs = [{**base, "id": "C1", "group": "C1", "page": "03-stack/engines.md", "check": "ok", "proposed": "",
           "current": "Auparavant, la version 0.31.2 suffisait[^2]."}]
    out = compact.with_orphan_notes(deps.vault, cs)
    assert [(c["id"], c["group"], c["check"], c.get("auto")) for c in out] == [("C1", "C1", "ok", None), ("C2", "C1", "ok", True)]
    assert out[1]["current"] == "[^2]: vLLM, notes de version 0.31.2, https://example.org/vllm-031." and out[1]["proposed"] == ""
    assert compact.with_orphan_notes(deps.vault, out) == out  # once: a second pass adds nothing
    # A sentence still citing a note whose definition goes: refused
    bad = [{**base, "id": "C1", "group": "C1", "page": "03-stack/engines.md", "check": "ok", "proposed": "",
            "current": "[^1]: vLLM, notes de version 0.33, https://example.org/vllm-033."}]
    compact.mark_dangling(deps.vault, bad)
    assert bad[0]["check"] == "leaves [^1] cited without its note"
    compact.mark_dangling(deps.vault, out)
    assert [c["check"] for c in out] == ["ok", "ok"]


def test_a_finding_is_one_line_with_the_page_that_keeps_the_statement():
    t = compact.Trim(kind="repeated", pages=["a.md", "b.md"], problem="stated twice.", keep_in="a.md")
    assert compact.line(t) == "[Repeated] a.md, b.md: stated twice. Keep the full statement in a.md."
    t = compact.Trim(kind="history", pages=["a.md"], problem="old note; keep a.md as it is.", keep_in="a.md")
    assert compact.line(t) == "[History] a.md: old note; keep a.md as it is."


# -- the report (a check of « Check the guide ») --------------------------------------------------------------------
def test_the_report_reads_the_guide_with_its_heaviest_pages_and_edits_nothing(setup):
    deps, llm = setup
    results = {"sizes": verify.run_sizes(deps.vault, deps.home, {}, None)}
    assert results["sizes"]["ok"] is False and "1 page(s) over their budget: 03-stack/engines.md" in results["sizes"]["summary"]
    result = verify.run_compaction(deps.vault, deps.home, results, llm)
    system, prompt = llm.prompts["verify compaction"]
    assert "heavier than it needs to be" in system and "read-only" in system  # the manifest's read-only pages
    assert "The heaviest pages:\n- 03-stack/engines.md: " in prompt and "over its budget" in prompt
    assert "projet/changelog.md" in prompt and "— read-only" in prompt
    assert result["findings"] == [
        "[History] 03-stack/engines.md: the 0.31.2 note is superseded.",
        "[Repeated] 03-stack/engines.md, 06-ops/security.md: the 0.33 floor is stated twice. Keep the full statement in "
        "03-stack/engines.md."]
    assert result["summary"] == "2 findings, 1 about read-only pages left out"
    assert result["excerpts"][result["findings"][0]][0]["match"] == "exact"
    assert verify.plan(["compaction"]) == ["sizes", "compaction"] and verify.BY_ID["compaction"].fix_mode == "compact"
    estimate = verify.estimates(deps.vault, {})
    assert estimate["sizes"]["usd"] == 0 and estimate["compaction"]["usd"] > 0
    assert subprocess.run(["git", "status", "--porcelain"], cwd=deps.vault, capture_output=True, text=True).stdout == ""


# -- the trims: a run of the graph ---------------------------------------------------------------------------------
def test_a_compaction_run_trims_on_a_branch_after_the_review(setup):
    deps, llm = setup
    graph = build(deps, InMemorySaver())
    config = {"configurable": {"thread_id": "compact-test"}}
    items, proposal, usage = compact.propose(deps.vault, FINDINGS, llm)
    assert [i["id"] for i in items] == ["F1", "F2"] and len(proposal) == len(usage) == 1
    graph.update_state(config, fix.initial_state("compact-test", items, proposal, usage, "compact-test", "compact"),
                       as_node="propose")
    graph.invoke(None, config)
    paused = graph.get_state(config)
    assert paused.tasks[0].interrupts[0].value["step"] == "review"
    assert llm.calls == ["compact", "crosscheck"]  # no sweep: a repetition removed leaves its values elsewhere
    cs = {c["id"]: c for c in paused.values["corrections"]}
    assert [(i, c["check"], c["group"]) for i, c in cs.items()] == [
        ("C1", "ok", "C1"), ("C2", "ok", "C2"), ("C3", "ok", "C3"),
        ("C4", "leaves [^1] cited without its note", "C4"), ("C5", "ok", "C1")]
    assert cs["C5"]["current"].startswith("[^2]:") and cs["C5"]["review"].startswith("added by the program")
    assert cs["C2"]["proposed"] == "Version minimale de vLLM : voir [[03-stack/engines|Moteurs]]."  # revised
    assert [cs[i]["lost"] for i in cs] == [["0.31.2"], [], ["0.29"], [], ["0.31.2", "https://example.org/vllm-031"]]
    report = Path(paused.values["report_path"]).read_text(encoding="utf-8")
    assert "No page states any more: 0.31.2, https://example.org/vllm-031." in report
    assert sh("git", "diff", "--quiet", cwd=deps.vault) is None  # nothing touched before the review

    graph.invoke(Command(resume=["C1", "C2", "C3", "C4"]), config)  # C1 takes C5 with it; C4 cannot apply
    graph.invoke(Command(resume="skip"), config)  # the pause to retouch (H3): nothing retouched
    state = graph.get_state(config).values
    assert state["applied"] == ["C1", "C2", "C3", "C5"] and state["branch"] == "compact/compact-test"
    wt = Path(state["worktree"])
    assert (wt / "03-stack/engines.md").read_text(encoding="utf-8") == """---
title: Moteurs
last_modified: "2026-11-20"
---

# Moteurs

PADDING

vLLM 0.33 est la version minimale recommandée[^1].

Le port 8000 doit rester fermé, voir la page sécurité.

| Outil | Version |
| :-- | :-- |
| vLLM | 0.33 |

[^1]: vLLM, notes de version 0.33, https://example.org/vllm-033.
""".replace("PADDING", PADDING)
    english =(wt / "en/03-stack/engines.md").read_text(encoding="utf-8")
    assert "0.31.2" not in english and "| Old |" not in english and "| vLLM | 0.33 |\n\n[^1]:" in english
    assert "see [[03-stack/engines|Engines]]" in (wt / "en/06-ops/security.md").read_text(encoding="utf-8")
    assert state["mirrored"] == ["en/03-stack/engines.md", "en/06-ops/security.md"]
    assert state["weight"]["after"] < state["weight"]["before"]
    assert state["weight"]["pages"][0][0] == "03-stack/engines.md" and state["weight"]["pages"][0][1] < 0  # per page, largest first
    assert sum(d for _, d in state["weight"]["pages"]) == state["weight"]["after"] - state["weight"]["before"]
    assert "| Weight, if every valid correction is applied | -0." in report and "Most: `03-stack/engines.md`" in report
    assert state["title"] == "chore(content): reviewed trims of the guide (compact-test)"
    body = pr_body(state)
    assert body.startswith("Trims of what weighs in the guide (compact-test), reviewed before apply")
    assert "KB before and" in body and "What weighed:\n\n- F1: [History]" in body
    from vault_watch_agent.graph import expected_weight, weight_line

    # A description too long for the forge loses, in this order: the passages under the findings, the end of the
    # « Why » cells, the last rows of the table; under the limit it is whole
    many = {**state, "applied": [f"C{n}" for n in range(1, 401)], "corrections": [
        {**state["corrections"][0], "id": f"C{n}", "rationale": "Superseded by the floor stated in the next sentence. " * 6}
        for n in range(1, 401)], "items": [{**i, "excerpts": [{"page": "a.md", "line": 3, "match": "exact",
                                                                 "lines": [{"hit": True, "text": "x" * 300}]}] * 4}
                                                 for i in state["items"]]}
    whole, short = pr_body(many, limit=10**9), pr_body(many)
    assert len(whole) > 150_000 and "    > → xxx" in whole and "shortened" not in whole
    assert len(short) <= 60_000 and "    > → xxx" not in short and "… | 03-stack/engines.md |" in short
    assert "This description is shortened to fit" in short and "- F1: [History]" in short and "Guide audits: " in short
    kept = short.count("| Minor |")
    assert 0 < kept < 400 and f"{400 - kept} more, C{kept + 1} to C400: the commit message of the branch names every one." in short
    assert pr_body(state) == pr_body(state, limit=10**9)  # an ordinary run: nothing cut

    # Every run says it, not only the trims: a fix run that adds to a page
    assert pr_body({**state, "mode": "fix", "weight": {"before": 10240, "after": 12288, "pages": [["a.md", 2048]]}}).startswith(
        "Corrections from what weighs in the guide (compact-test), reviewed before apply.\n\n"
        "The pages changed weigh 10.0 KB before and 12.0 KB after (+2.0 KB), mirrors not counted. Most: `a.md` +2.0 KB.")
    assert weight_line({"before": 1000, "after": 1100, "pages": [["a.md", 100]]}).endswith("mirrors not counted.")  # too small to name
    grown = expected_weight([{"check": "ok", "page": "a.md", "current": "x", "proposed": "x" * 2049},
                             {"check": "not found", "page": "b.md", "current": "", "proposed": "y" * 9000}])
    assert grown == {"total": 2048, "pages": [["a.md", 2048]]}
    assert "0.31.2" in ENGINES and (deps.vault / "03-stack/engines.md").read_text(encoding="utf-8") == ENGINES  # main untouched


def test_the_findings_are_grouped_by_the_pages_they_share(monkeypatch):
    size = {p: 1000 for p in "abcdefgh"}
    monkeypatch.setattr(compact, "BATCH_LOAD", 6)
    #                          0           1      2           3      4
    assert compact.batches([["a", "b"], ["c"], ["b", "d"], ["c"], ["a"]], size) == [[0, 2, 4], [1, 3]]
    assert compact.batches([list("abcdefgh")], size) == [[0]]  # heavier than a batch: alone
    monkeypatch.setattr(compact, "BATCH_BYTES", 2500)
    assert compact.batches([["a", "b"], ["c"], ["b"]], size) == [[0, 2], [1]]  # the pages of a call have a ceiling
    sources = {"03-stack/engines.md", "06-ops/security.md"}
    assert compact.named("[Repeated] 03-stack/engines.md, 06-ops/security.md, en/x.md, ../secret.md: 03-stack/engines.md",
                         sources) == ["03-stack/engines.md", "06-ops/security.md"]


def test_a_run_takes_several_calls_and_goes_on_when_one_fails(setup, monkeypatch):
    from vault_watch_agent.llm import ModelError

    deps, _ = setup
    monkeypatch.setattr(compact, "BATCH_LOAD", 2)  # one finding per call
    seen = {}

    class Llm:
        def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
            seen[node] = (prompt, context)
            if "by hand" in prompt:  # names no page: the whole guide, cached
                assert context and "projet/changelog.md" in context and "<guide>" in context
                return ClusterProposal(outcomes=[ItemOutcome(item_id="F3", event="", no_change_reason="vague")],
                                       corrections=[]), {"node": node, "cost_usd": 0.5}
            if '<finding id="F2">' in prompt:
                error = ModelError("compact: the answer was cut before its end")
                error.usage = {"node": node, "cost_usd": 2.0, "cut": True}
                raise error
            assert '<finding id="F1">' in prompt and "06-ops/security.md" not in prompt
            proposal = ClusterProposal(
                outcomes=[ItemOutcome(item_id="F1", event="", no_change_reason="")],
                corrections=[trim("Auparavant, la version 0.31.2 suffisait[^2].", "", ["F1"], group="g")])
            return proposal, {"node": node, "cost_usd": 1.0}

    items, proposals, usages = compact.propose(deps.vault, [*FINDINGS, "typed by hand, no page"], Llm())
    assert sorted(seen) == ["compact 1/3", "compact 2/3", "compact 3/3"]
    assert [i["id"] for i in items] == ["F1", "F2", "F3"] and [p["item_ids"] for p in proposals] == [["F1"], ["F2"], ["F3"]]
    assert proposals[1]["corrections"] == [] and "the call failed" in proposals[1]["outcomes"][0]["no_change_reason"]
    assert sum(u["cost_usd"] for u in usages) == 3.5  # the cut call is counted
    state = fix.initial_state("t", items, proposals, usages, "t", "compact")
    assert state["proposals"] == proposals and state["usage"] == usages

    class Down:
        def parse(self, **kw):
            raise ModelError("no credit")

    with pytest.raises(ModelError, match="no credit"):  # every call failed: the run stops there
        compact.propose(deps.vault, FINDINGS, Down())


def test_on_the_claude_api_every_call_reads_the_guide_the_first_one_cached(setup, monkeypatch):
    import threading

    from vault_watch_agent.llm import ModelError

    deps, _ = setup
    monkeypatch.setattr(compact, "BATCH_LOAD", 2)  # one finding per call
    findings = [FINDINGS[0], FINDINGS[1], FINDINGS[0].replace("0.31.2", "0.31"), FINDINGS[1] + " Again."]
    lock, order, leader_begun = threading.Lock(), [], threading.Event()

    class Api:
        signals_start = True  # as llm.Claude: `started` is called when the answer begins

        def parse(self, *, system, prompt, schema, effort, node, context=None, web=False, started=None):
            assert "The whole guide is above" in system and context.startswith("<guide>") and "projet/changelog.md" in context
            with lock:
                order.append((node, started is not None, leader_begun.is_set()))
            if node == "compact 1/4":  # the first leader fails before it answers: the next one leads
                raise ModelError("overloaded")
            if started:
                leader_begun.set()
                started()
            n = prompt.split('<finding id="')[1].split('"')[0]
            return ClusterProposal(outcomes=[ItemOutcome(item_id=n, event="", no_change_reason="kept")], corrections=[]), \
                {"node": node, "cost_usd": 1.0}

    items, proposals, usages = compact.propose(deps.vault, findings, Api())
    assert order[0] == ("compact 1/4", True, False) and order[1] == ("compact 2/4", True, False)
    assert sorted(order[2:]) == [("compact 3/4", False, True), ("compact 4/4", False, True)]  # after the leader began
    assert [p["item_ids"] for p in proposals] == [["F1"], ["F2"], ["F3"], ["F4"]] and len(usages) == 3
    assert "overloaded" in proposals[0]["outcomes"][0]["no_change_reason"]


def test_other_runs_still_refuse_an_edit_that_drops_a_note():
    from vault_watch_agent.graph import mark_unsafe

    cs = [{"id": "C1", "group": "C1", "check": "ok", "current": "[^2]: old.", "proposed": ""}]
    mark_unsafe(cs)
    assert cs[0]["check"] == "drops footnote [^2]"
    cs[0]["check"] = "ok"
    mark_unsafe(cs, trims=True)
    assert cs[0]["check"] == "ok"


# -- from the interface ----------------------------------------------------------------------------------------------
def test_the_leads_of_the_check_go_to_a_compaction_run(setup, tmp_path):
    from vault_watch_agent.web import Settings, create_app

    deps, llm = setup
    act = {"X-Vault-Watch": "1"}
    c = TestClient(create_app(Settings(vault=deps.vault, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    options = {o["id"]: o for o in c.get("/api/verifications/options").json()}
    assert options["compaction"]["needs"] == ["sizes"] and options["sizes"]["model"] is None
    assert options["compaction"]["run_usd"] > 0 and options["compaction"]["run_usd_each"] > 0  # the cross-check, then per finding
    assert options["coherence"]["run_usd"] is None  # a fix run: no estimate from the server
    vid = c.post("/api/verifications", json={"checks": ["compaction"]}, headers=act).json()["id"]
    for _ in range(200):
        v = c.get(f"/api/verifications/{vid}").json()
        if not v["running"]:
            break
        time.sleep(0.05)
    assert v["checks"] == ["sizes", "compaction"] and v["results"]["compaction"]["mode"] == "compact"
    assert v["results"]["sizes"]["sizes"]["over"] == 1 and v["results"]["sizes"]["sizes"]["heaviest"][0]["page"] == "03-stack/engines.md"
    leads = v["results"]["compaction"]["findings"]
    thread = c.post("/api/fix", json={"text": "\n".join(leads), "verification": vid, "mode": "compact"}, headers=act).json()["thread"]
    assert thread.startswith("compact-")
    for _ in range(200):
        run = c.get(f"/api/runs/{thread}").json()
        if run["status"] != "running":
            break
        time.sleep(0.05)
    assert run["status"] == "review" and run["mode"] == "compact"
    assert [x["id"] for x in run["corrections"]] == ["C1", "C2", "C3", "C4", "C5"] and run["corrections"][4]["lost"]
    assert c.get(f"/api/verifications/{vid}").json()["counts"] == {"open": 0, "fix": 2, "dismissed": 0}
