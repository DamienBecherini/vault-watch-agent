"""A whole run on the sample guide (examples/sample-guide/) with a fake model.

The sample guide has a manifest with no mirror and no check of its own: the run reports them as not checked.
"""

import re
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from vault_watch_agent import vault
from vault_watch_agent.crosscheck import CrossCheck, CorrectionReview
from vault_watch_agent.graph import Deps, build, pr_body
from vault_watch_agent.state import ClusterProposal, Correction, ItemOutcome, TriageDecision, TriageResult

# The planted errors of the sample guide and what a good run proposes for them: search term, page, current, proposed
FIXES = [
    ("Python 3.9", "02-install/requirements.md", "Quillnote needs Python 3.9 or later[^1]",
     "Quillnote 5.0 needs Python 3.11 or later (October 2026)[^1]"),
    ("7400", "02-install/configuration.md", "Larkdb listens on\nport 7400 by default.",
     "Larkdb listens on\nport 7300 by default."),
]


class SampleLLM:
    """Keeps the stale version and the port, drops the rest; proposes the fixes of FIXES; the cross-check keeps them."""

    def __init__(self):
        self.calls = []

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
        self.calls.append(node)
        usage = {"node": node, "model": "fake", "input": 10, "output": 5, "cache_read": 0}
        if schema is TriageResult:  # an item is kept when its title or notes name a planted error
            terms = {"Quillnote 5.0": ["Python 3.9"], "default port": ["7400"]}
            decisions = []
            for i in dict.fromkeys(re.findall(r"\b(W\d+)\b", prompt)):
                after = prompt.split(i, 1)[1][:300]
                hit = next((t for k, t in terms.items() if k in after), None)
                decisions.append(TriageDecision(item_id=i, action="correct" if hit else "drop",
                                                reason="planted" if hit else "noise", search_terms=hit or []))
            return TriageResult(decisions=decisions), usage
        if schema is ClusterProposal:
            ids = list(dict.fromkeys(re.findall(r"\b(W\d+)\b", prompt)))
            corrections = [Correction(item_ids=ids[:1], page=page, current=current, proposed=proposed,
                                      source_url="https://example.org/quillnote", severity="Major",
                                      rationale="planted error", group="")
                           for term, page, current, proposed in FIXES if current.split("\n")[0] in prompt]
            return ClusterProposal(outcomes=[ItemOutcome(item_id=i, event="2026-10-28: planted", no_change_reason="")
                                             for i in ids], corrections=corrections), usage
        if schema is CrossCheck:
            assert '<page path="02-install/requirements.md">' in context  # the whole guide
            ids = list(dict.fromkeys(re.findall(r"\b(C\d+)\b", prompt)))
            return CrossCheck(reviews=[CorrectionReview(id=i, verdict="keep", reason="ok", revised="") for i in ids],
                              consistency_edits=[], other_findings=[]), usage
        raise AssertionError(f"unexpected call {node} ({schema.__name__})")


def test_the_sample_guide_has_twelve_pages(sample_guide):
    guide, _ = sample_guide
    assert len(vault.french_pages(guide)) == 12  # README.md is excluded by the manifest


def test_a_run_on_the_sample_guide_finds_the_planted_errors(sample_guide, tmp_path):
    guide, watch = sample_guide
    llm = SampleLLM()
    deps = Deps(vault=guide, home=tmp_path / "home", llm=llm, today="2026-11-17")
    graph = build(deps, InMemorySaver())
    config = {"configurable": {"thread_id": "sample"}}

    graph.invoke({"source": str(watch), "issue": None}, config)
    review = graph.get_state(config).tasks[0].interrupts[0].value
    assert review["step"] == "review"
    found = {c["page"]: c["check"] for c in review["corrections"]}
    assert found == {"02-install/requirements.md": "ok", "02-install/configuration.md": "ok"}
    assert llm.calls[0] == "triage" and llm.calls[-1] == "crosscheck"

    graph.invoke(Command(resume=[c["id"] for c in review["corrections"]]), config)
    publish = graph.get_state(config).tasks[0].interrupts[0].value
    assert publish["step"] == "publish"
    wt = Path(graph.get_state(config).values["worktree"])
    edited = (wt / "02-install" / "requirements.md").read_text(encoding="utf-8")
    assert "Python 3.11" in edited and 'last_modified: "2026-11-17"' in edited
    assert publish["mirror_problems"] == [] and graph.get_state(config).values["mirrored"] == []  # no mirror declared
    # No [checks] in its manifest: not checked, which is not a failure
    assert publish["audit_ok"] is None and publish["link_problems"] is None
    body = pr_body(graph.get_state(config).values)
    assert "Guide audits: not checked" in body and "not checked (the guide declares no source audit)" in body
    # No repository: « yes » keeps the branch on the machine, nothing is pushed
    assert publish["local"] is True and "no repository" in publish["question"]
    graph.invoke(Command(resume=True), config)
    assert not graph.get_state(config).next and not graph.get_state(config).values.get("pr_url")

    graph.invoke(Command(resume=False), config)  # no push
    assert not graph.get_state(config).next


def test_a_window_too_small_for_the_guide_reads_it_chapter_by_chapter_and_the_report_says_so(sample_guide, tmp_path):
    from vault_watch_agent import reading
    from vault_watch_agent.llm import Capabilities

    class SmallWindow(SampleLLM):  # a model whose window holds a chapter, not the guide
        def capabilities(self):
            return Capabilities(context=8_192 + 1_000)  # the smallest reserve, 8k, leaves 1,000

    guide, watch = sample_guide
    assert reading.plan(guide, SampleLLM()).mode == "whole"  # no capabilities declared: the whole guide
    plan = reading.plan(guide, SmallWindow())
    assert plan.mode == "chapters" and plan.tokens > plan.budget == 1_000 and not plan.exact
    llm = SmallWindow()
    graph = build(Deps(vault=guide, home=tmp_path / "home", llm=llm, today="2026-11-17"), InMemorySaver())
    config = {"configurable": {"thread_id": "small"}}
    graph.invoke({"source": str(watch), "issue": None}, config)
    review = graph.get_state(config).tasks[0].interrupts[0].value
    assert {c["page"]: c["check"] for c in review["corrections"]} == {"02-install/requirements.md": "ok",
                                                                       "02-install/configuration.md": "ok"}
    assert {c for c in llm.calls if c.startswith("crosscheck")} == {f"crosscheck {ch}" for ch in reading.chapters(guide)}
    values = graph.get_state(config).values
    assert all(c["review"].startswith("keep") for c in values["corrections"])  # the verdict of the page's own chapter
    assert values["reading"]["mode"] == "chapters"
    text = Path(values["report_path"]).read_text(encoding="utf-8")
    assert "| Cross-check | by chapter:" in text and "a contradiction between two chapters can be missed" in text


def test_the_manifest_budget_caps_what_one_call_reads(sample_guide):
    from vault_watch_agent import reading
    from vault_watch_agent.llm import Capabilities

    class Big(SampleLLM):
        def capabilities(self):
            return Capabilities(context=1_000_000)

    guide, _ = sample_guide
    assert reading.plan(guide, Big()).mode == "whole"
    manifest = guide / "vault-watch.toml"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n[budget]\nmax_context_tokens = 1000\n", encoding="utf-8")
    plan = reading.plan(guide, Big())
    assert (plan.mode, plan.budget) == ("chapters", 1000)


def test_the_reserve_beside_the_guide_follows_the_window():
    """100k with a 1M window; a third of a smaller one; a 64k local model reads a small guide whole."""
    from vault_watch_agent import reading

    assert [reading.reserve(w) for w in (1_000_000, 300_000, 200_000, 65_536, 16_384)] ==         [100_000, 100_000, 66_666, 21_845, 8_192]
