"""The graph: watch → triage → locate → propose (one branch per group) → cross-check
→ report → human review → apply on a branch → the editor's retouches → their
proofreading, if asked → mirrors → vault audits → link checks → human go-ahead →
pull request.

Interrupts keep a human in the loop: nothing touches the vault before the review
(where a proposal can be retouched), the pages of the branch can be retouched
before the mirrors follow them, what the editor wrote can be proofread and its
fixes chosen, a « Sync the languages » run shows its translation, and nothing
leaves the machine before the last go-ahead.

This module wires the nodes; each node is a function of its dependencies and the state, in the module of its part
of the run:
- graph_proposals.py: collect → triage → locate → propose → number → crosscheck → report (read-only);
- graph_review.py: review → apply → retouch → proofread → proofread_review;
- graph_publish.py: mirror → translation → audits → links → publish;
- graph_corrections.py: the free checks of the corrections, and the editor's retouches at the review;
- graph_text.py: the report, the usage line, the pull request's title and description;
- graph_common.py: `Deps`, git in a worktree, the branch of a run.
"""

from __future__ import annotations

import json
from functools import partial

from langgraph.graph import END, START, StateGraph

from .graph_common import Deps, git, sorted_proposals, watch_branch
from .graph_corrections import FOOTNOTE_DEF, RETOUCHABLE, mark_conflicts, mark_unsafe, note_retouches, retouchable, retouched
from .graph_proposals import (
    GROUP_EXCERPTS,
    HUB_ITEMS,
    ITEM_EXCERPTS,
    TRIAGE_BATCH,
    TRIAGE_NOTES,
    clusters,
    collect,
    crosscheck_node,
    fan_out,
    locate,
    number,
    propose,
    report,
    triage,
)
from .graph_publish import BROKEN, MIRROR_NOTES, audits, correct_again, link_problems, links, mirror, publish, translation
from .graph_review import apply, proofread_node, proofread_review, retouch_node, review
from .graph_text import PR_BODY_MAX, expected_weight, pr_body, pr_title, render_report, usage_line, weight_line
from .state import WatchState

__all__ = [  # what other modules and the tests import from here, wherever it is written
    "BROKEN", "FOOTNOTE_DEF", "GROUP_EXCERPTS", "HUB_ITEMS", "ITEM_EXCERPTS", "MIRROR_NOTES", "PR_BODY_MAX", "RETOUCHABLE",
    "TRIAGE_BATCH", "TRIAGE_NOTES", "Deps", "build", "clusters", "correct_again", "describe", "expected_weight", "git",
    "link_problems", "mark_conflicts", "mark_unsafe", "note_retouches", "pr_body", "pr_title", "render_report",
    "retouchable", "retouched", "sorted_proposals", "usage_line", "watch_branch", "weight_line",
]


def build(deps: Deps, checkpointer=None):
    g = StateGraph(WatchState)
    for name, fn in [("collect", collect), ("triage", triage), ("locate", locate), ("propose", propose),
                     ("number", number), ("crosscheck", crosscheck_node), ("report", report),
                     ("review", review), ("apply", apply), ("retouch", retouch_node), ("proofread", proofread_node),
                     ("proofread_review", proofread_review), ("mirror", mirror), ("translation", translation),
                     ("audits", audits), ("links", links), ("publish", publish)]:
        g.add_node(name, partial(fn, deps))
    g.add_edge(START, "collect")
    g.add_edge("collect", "triage")
    g.add_edge("triage", "locate")
    g.add_conditional_edges("locate", fan_out, ["propose", "number"])
    g.add_edge("propose", "number")
    g.add_edge("number", "crosscheck")
    g.add_edge("crosscheck", "report")
    g.add_edge("report", "review")
    g.add_conditional_edges("review", lambda s: "apply" if s.get("accepted") else END, ["apply", END])
    g.add_edge("apply", "retouch")
    g.add_edge("retouch", "proofread")
    g.add_edge("proofread", "proofread_review")
    # after the retouches, the mirrors; from the publish pause, the mirrors or the checks (proofread_review says)
    g.add_conditional_edges("proofread_review", lambda s: "audits" if s.get("recheck") == "audits" else "mirror",
                            ["mirror", "audits"])
    g.add_edge("mirror", "translation")
    g.add_edge("translation", "audits")
    g.add_edge("audits", "links")
    g.add_edge("links", "publish")
    g.add_conditional_edges("publish", lambda s: s.get("recheck") or END, ["mirror", "audits", "proofread", END])
    return g.compile(checkpointer=checkpointer)


def describe(state: WatchState) -> str:
    """Short JSON view of a paused run for the CLI."""
    keep = {k: state.get(k) for k in ("source", "as_of", "report_path", "accepted", "branch", "worktree", "audit_ok", "pr_url")}
    return json.dumps(keep, ensure_ascii=False, indent=2)
