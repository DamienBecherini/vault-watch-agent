"""Evaluation on past watches that a human already processed.

A past watch is replayed on the vault as it was then (a detached worktree at
the commit before the human's PR), up to the review pause: nothing is applied.
The ground truth is the diff of the PR the human merged (French pages only,
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

from . import inputs
from .llm import LLM

SKIP_TOP = ("en/", ".agents/", ".github/", "scripts/", "docs/", "_private/", "_templates/")
DATE_LINE = re.compile(r"^(last_modified|last_verified|verified_by|verified_hitl\w*):")


def truth_hunks(vault: Path, base: str, head: str) -> list[dict]:
    """Hunks of the French pages changed between two commits, without date-only frontmatter edits."""
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
        if not h["page"] or h["page"].startswith(SKIP_TOP) or "/" not in h["page"]:
            continue
        lines = h["removed"] + h["added"]
        if lines and all(DATE_LINE.match(l.strip()) for l in lines):
            continue
        out.append({"id": f"H{len(out) + 1}", **h})
    return out


class HunkMatch(BaseModel):
    hunk_id: str
    matched_by: list[str] = Field(description="Ids of the proposals that make the same factual change (wording may differ).")


class ProposalVerdict(BaseModel):
    id: str
    assessment: Literal["matches_truth", "valid_extra", "wrong", "unclear"]
    note: str = Field(description="One line, in English.")


class Judgement(BaseModel):
    hunks: list[HunkMatch]
    proposals: list[ProposalVerdict]


JUDGE = """You evaluate an agent that maintains a French guide on running AI on-premise. For one past ecosystem watch,
you get the changes a human reviewer actually merged (ground-truth hunks, French pages) and the corrections the
agent proposed. Match them on substance: a proposal matches a hunk when it makes the same factual change on the
same page (same new version, figure, recommendation), even with different wording or a different sentence boundary.

For each hunk, list the proposals that match it (often none). For each proposal, assess it:
- matches_truth: it matches at least one hunk;
- valid_extra: no hunk matches, but the change is correct and useful as far as the proposal's own source shows;
- wrong: it introduces an error, overstates its source, or edits text that should stay;
- unclear: you cannot tell.
Content changes count; a footnote that only supports a matched change matches too."""


def judge(hunks: list[dict], corrections: list[dict], llm: LLM) -> tuple[Judgement, dict]:
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
    return llm.parse(system=JUDGE, prompt=f"Ground truth:\n\n{truth}\n\nAgent proposals:\n\n{proposals}",
                     schema=Judgement, effort="high", node="judge")


def scores(hunks: list[dict], corrections: list[dict], j: Judgement) -> dict:
    found = sum(1 for h in j.hunks if h.matched_by)
    verdicts = [p.assessment for p in j.proposals]
    n = len(corrections)
    return {
        "truth_hunks": len(hunks),
        "proposals": n,
        "recall": round(found / len(hunks), 3) if hunks else None,
        "precision": round(verdicts.count("matches_truth") / n, 3) if n else None,
        "lenient_precision": round((verdicts.count("matches_truth") + verdicts.count("valid_extra")) / n, 3) if n else None,
        "verdicts": {k: verdicts.count(k) for k in ("matches_truth", "valid_extra", "wrong", "unclear")},
    }
