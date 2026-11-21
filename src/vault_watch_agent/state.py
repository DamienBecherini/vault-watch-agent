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
        description="Tool, model, flag or version names to grep in the pages of the guide (empty when dropped)."
    )


class TriageResult(BaseModel):
    decisions: list[TriageDecision]


class Correction(BaseModel):
    item_ids: list[str] = Field(description="Ids of the watch items that support this correction (W1…).")
    page: str = Field(description="Path of the page relative to the guide, as given in the excerpts.")
    current: str = Field(description="The exact current text, copied verbatim from one excerpt, one sentence or table row.")
    proposed: str = Field(description="The replacement, in the page's language, with dated wording (in French: « au T4 2026 », « depuis la v0.33 »).")
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
    current: str = Field(description="The exact text of the mirror page that corresponds to the source text being replaced, copied verbatim.")
    proposed: str = Field(description="Its faithful translation of the new source text, in the mirror's language.")


class MirrorResult(BaseModel):
    edits: list[MirrorEdit]
    problem: str = Field(description="Empty, or why the mirror page cannot be updated faithfully (passage missing, page diverged).")


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
    reading: dict  # how the cross-check read the guide: whole or by chapter (reading.Plan.summary)
    # Review
    mode: str  # "translation": a fix run on mirror pages (no cross-check); "compact": trims (compact.py); else absent
    weight: dict  # bytes of the changed pages before and after apply: {before, after} (shown for trims)
    corrections: list[dict]  # numbered C1, C2… with their deterministic check
    findings: list[str]  # doubts the cross-check noticed elsewhere in the vault, not proposed
    finding_excerpts: dict[str, list[dict]]  # finding -> the passages it is about, found in the pages (quotes.locate)
    leftovers: list[dict]  # lines that still hold a value the corrections remove: {page, line, tokens, text}
    report_path: str
    accepted: list[str]
    # Apply and publish
    branch: str
    worktree: str
    applied: list[str]
    mirror_since: dict[str, str]  # source page -> commit to translate it from (a page ahead of its mirror); else the base
    hand_pages: list[str]  # a « Sync the languages » run: the pages copied from the guide's folder, edited by hand
    retouch_offered: bool  # the run stops after apply for the editor's retouches (runs from 1.6.0 on)
    applied_tip: str  # the commit of the corrections, before the retouches
    retouched: list[str]  # the files the editor retouched at the pause
    mirror_pairs: list[dict]  # per mirror page: {page, mirror, source: [[old, new]], target: [[current, proposed, (the translator's)]], problem}
    translation_retouched: list[str]  # the mirror pages whose translation the editor retouched
    mirrored: list[str]  # EN pages updated
    mirror_problems: list[str]
    link_problems: list[str] | None  # external sources of the changed pages that do not answer; None: not checked
    audit_ok: bool
    audit_log: str
    pr_url: str
