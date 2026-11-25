"""Evaluation on past watches that a human already processed.

A past watch is replayed on the vault as it was then (a detached worktree at
the commit before the human's PR), up to the review pause: nothing is applied.
The ground truth is the diff of the PR the human merged (pages of the guide only, no mirror,
frontmatter dates left out), or nothing at all when the human decided to apply
nothing. A judge model matches each proposal with the hunks of that diff.

    recall    = ground-truth hunks the agent found / ground-truth hunks
    precision = proposals that match the ground truth / proposals
    lenient   = (matches + valid extras) / proposals

A "valid extra" is a correct change the human did not make: the human is not
an oracle, so it is reported apart instead of being counted as an error.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from . import inputs, prompts, steps
from . import vault as vault_mod  # `vault` is the name of a parameter here
from .guide import matches
from .llm import LLM

DATE_LINE = re.compile(r"^(last_modified|last_verified|verified_by|verified_hitl\w*):")


def truth_hunks(vault: Path, base: str, head: str) -> list[dict]:
    """Hunks of the guide's pages changed between two commits, without date-only frontmatter edits. Its pages:
    the manifest's include and exclude, no mirror, no dot folder, and not at the root (the home page is left out of
    the scores, as it was before manifests)."""
    guide = vault_mod.guide_of(vault)
    diff = inputs.run(["git", "diff", "-U0", f"{base}..{head}", "--", "*.md", "*.mdx"], cwd=vault)
    hunks, page, cur = [], None, None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            page = line[6:]
        elif line.startswith("@@"):
            cur = {"page": page, "removed": [], "added": []}
            hunks.append(cur)
        elif cur is not None and line.startswith("-") and not line.startswith("---"):
            cur["removed"].append(line[1:])
        elif cur is not None and line.startswith("+") and not line.startswith("+++"):
            cur["added"].append(line[1:])
    out = []
    for h in hunks:
        page = h["page"] or ""
        if ("/" not in page or page.startswith(".") or vault_mod.in_mirror(vault, page)
                or not any(matches(page, p) for p in guide.include) or any(matches(page, p) for p in guide.exclude)):
            continue
        lines = h["removed"] + h["added"]
        if lines and all(DATE_LINE.match(line.strip()) for line in lines):
            continue
        out.append({"id": f"H{len(out) + 1}", **h})
    return out


class HunkMatch(BaseModel):
    hunk_id: str
    kind: Literal["correction", "addition"] = Field(
        description="correction: changes or updates a fact already in the page (or the footnote that supports it); "
        "addition: brings a subject the page did not cover (a new tool, model, paragraph, pitfall)."
    )
    matched_by: list[str] = Field(description="Ids of the proposals that make the same factual change (wording may differ).")


class ProposalVerdict(BaseModel):
    id: str
    assessment: Literal["matches_truth", "valid_extra", "wrong", "unclear"]
    note: str = Field(description="One line, in English.")


class Judgement(BaseModel):
    hunks: list[HunkMatch]
    proposals: list[ProposalVerdict]


JUDGE = """You evaluate an agent that maintains <<GUIDE>>. For one past ecosystem watch,
you get the changes a human reviewer actually merged (ground-truth hunks, <<LANG>> pages) and the corrections the
agent proposed. Match them on substance: a proposal matches a hunk when it makes the same factual change on the
same page (same new version, figure, recommendation), even with different wording or a different sentence boundary.

For each hunk, list the proposals that match it (often none). For each proposal, assess it:
- matches_truth: it matches at least one hunk;
- valid_extra: no hunk matches, but the change is correct and useful as far as the proposal's own source shows;
- wrong: it introduces an error, overstates its source, or edits text that should stay;
- unclear: you cannot tell.
Content changes count; a footnote that only supports a matched change matches too."""


CLAUDE_ENGINES = ("api", "claude-code")


def judge_engine(chosen: str | None, watch_engine: str) -> str:
    """The engine of the judge: the one chosen, otherwise the watch's when it runs a Claude model, otherwise Claude
    Code when signed in with a subscription (nothing billed), otherwise the API. Never the watch's model when it is
    another one: a model scoring its own proposals, the scores of two models would not compare."""
    if chosen:
        return chosen
    if watch_engine in CLAUDE_ENGINES:
        return watch_engine
    from .llm import claude_code_status

    return "claude-code" if claude_code_status()["subscription"] else "api"


def judge(hunks: list[dict], corrections: list[dict], llm: LLM, vault: Path) -> tuple[Judgement, dict]:
    truth = "\n\n".join(
        f"<hunk id=\"{h['id']}\" page=\"{h['page']}\">\n<removed>\n" + "\n".join(h["removed"])
        + "\n</removed>\n<added>\n" + "\n".join(h["added"]) + "\n</added>\n</hunk>"
        for h in hunks
    ) or "(none: the human applied no change for this watch)"
    proposals = "\n\n".join(
        f"<proposal id=\"{c['id']}\" page=\"{c['page']}\" check=\"{c['check']}\">\n<current>\n{c['current']}\n</current>\n"
        f"<proposed>\n{c['proposed']}\n</proposed>\n<source>{c['source_url']}</source>\n</proposal>"
        for c in corrections
    ) or "(none)"
    return llm.parse(system=prompts.fill(JUDGE, vault), prompt=f"Ground truth:\n\n{truth}\n\nAgent proposals:\n\n{proposals}",
                     schema=Judgement, effort=steps.effort("judge"), node="judge")


def reviewable(corrections: list[dict]) -> list[dict]:
    """Only what reaches the human review counts: refused proposals (quote not found, conflict, rejected by
    the cross-check) never reach the vault."""
    return [c for c in corrections if c["check"] == "ok"]


def scores(hunks: list[dict], corrections: list[dict], j: Judgement) -> dict:
    found = sum(1 for h in j.hunks if h.matched_by)
    fixes = [h for h in j.hunks if h.kind == "correction"]
    verdicts = [p.assessment for p in j.proposals]
    n = len(corrections)
    return {
        "truth_hunks": len(hunks),
        "truth_corrections": len(fixes),
        "proposals": n,
        "recall": round(found / len(hunks), 3) if hunks else None,
        # Additions are only listed as candidates by design (no page is written without a go-ahead)
        "recall_corrections": round(sum(1 for h in fixes if h.matched_by) / len(fixes), 3) if fixes else None,
        "precision": round(verdicts.count("matches_truth") / n, 3) if n else None,
        "lenient_precision": round((verdicts.count("matches_truth") + verdicts.count("valid_extra")) / n, 3) if n else None,
        "verdicts": {k: verdicts.count(k) for k in ("matches_truth", "valid_extra", "wrong", "unclear")},
    }
