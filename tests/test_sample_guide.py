"""A whole run on the sample guide (examples/sample-guide/) with a fake model.

It also pins what the agent still needs of a guide before M1 (the English mirror, the guide's own audit scripts):
those assertions are marked "until M1" and change when the parts become optional.
"""

import re
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from vault_watch_agent import vault
from vault_watch_agent.crosscheck import CrossCheck, CorrectionReview
from vault_watch_agent.graph import Deps, build
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
    assert len(vault.french_pages(guide)) == 12  # README.md and scripts/ are not pages


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
    # Until M1: a guide without an English mirror or audit scripts is reported as having problems
    assert all("no English mirror" in p for p in publish["mirror_problems"]) and publish["mirror_problems"]
    assert not publish["audit_ok"]
    assert publish["link_problems"] and "could not run" in publish["link_problems"][0]

    graph.invoke(Command(resume=False), config)  # no push
    assert not graph.get_state(config).next
