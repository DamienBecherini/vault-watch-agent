"""Graph state and the schemas the model must answer with.

The state holds plain dicts (JSON-serialisable) so the SQLite checkpointer can
store a paused run and resume it in another process. Pydantic models are used
only at the model boundary, as structured-output schemas.
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field

Severity = Literal["Critical", "Major", "Minor"]


# ---------------------------------------------------------------------------
# Structured outputs
# ---------------------------------------------------------------------------


class TriageDecision(BaseModel):
    item_id: str
    action: Literal["correct", "addition", "drop"] = Field(
        description="correct: may change an existing sentence of the vault; "
        "addition: the vault does not cover it yet and it may cross the addition threshold; "
        "drop: no effect on the vault."
    )
    reason: str = Field(description="One line, in English.")
    search_terms: list[str] = Field(
        description="Tool, model, flag or version names to grep in the French pages (empty when dropped)."
    )


class TriageResult(BaseModel):
    decisions: list[TriageDecision]


class Correction(BaseModel):
    item_ids: list[str] = Field(description="Ids of the watch items that support this correction (W1…).")
    page: str = Field(description="Vault-relative path of the French page, as given in the excerpts.")
    current: str = Field(description="The exact current text, copied verbatim from one excerpt, one sentence or table row.")
    proposed: str = Field(description="The replacement, in French, with dated wording (« au T4 2026 », « depuis la v0.33 »).")
    source_url: str
    severity: Severity
    rationale: str = Field(description="Why the current text is wrong or outdated, one line, in English.")
    group: str = Field(
        description="Corrections that only make sense together (a sentence and the footnote it cites) share the "
        "same short label, e.g. 'a'. Leave empty for a correction that stands alone."
    )


class ItemOutcome(BaseModel):
    item_id: str
    event: str = Field(description="The verified fact as a dated one-liner (YYYY-MM-DD: fact), or empty if nothing is verified.")
    no_change_reason: str = Field(description="Filled when no correction relies on this item: why the vault stays as is.")


class ClusterProposal(BaseModel):
    """One answer for a group of items that touch the same pages, so their edits never collide."""

    outcomes: list[ItemOutcome] = Field(description="One entry per item of the group.")
    corrections: list[Correction] = Field(
        description="At most one correction per passage of a page: merge what several items say about the same text."
    )


class MirrorEdit(BaseModel):
    current: str = Field(description="The exact text of the English page that corresponds to the French text being replaced, copied verbatim.")
    proposed: str = Field(description="Its faithful English translation of the new French text.")


class MirrorResult(BaseModel):
    edits: list[MirrorEdit]
    problem: str = Field(description="Empty, or why the English page cannot be updated faithfully (passage missing, page diverged).")


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------


class WatchState(TypedDict, total=False):
    # Inputs
    source: str  # where the watch came from: "issue #50" or a file path
    title: str  # commit and PR title (default: the watch's)
    branch_name: str  # branch of the apply step (default: chore/watch-<as_of>)
    issue: int | None
    as_of: str  # YYYY-MM-DD
    items: list[dict]  # kept watch items, each with a run-local id W1, W2…
    claims_due: list[dict]  # watchlist rows past their "Recheck by" date
    # Triage and retrieval
    decisions: list[dict]
    evidence: dict[str, list[dict]]  # item id -> [{page, text}]
    # Proposals, filled in parallel by one branch per item
    proposals: Annotated[list[dict], operator.add]
    usage: Annotated[list[dict], operator.add]
    # Review
    corrections: list[dict]  # numbered C1, C2… with their deterministic check
    findings: list[str]  # doubts the cross-check noticed elsewhere in the vault, not proposed
    report_path: str
    accepted: list[str]
    # Apply and publish
    branch: str
    worktree: str
    applied: list[str]
    mirrored: list[str]  # EN pages updated
    mirror_problems: list[str]
    link_problems: list[str]  # external sources of the changed pages that do not answer
    audit_ok: bool
    audit_log: str
    pr_url: str
