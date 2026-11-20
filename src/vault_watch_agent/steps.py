"""The steps that call the model: the role whose model runs them, the effort they ask for, what they need.

One table, read by the call sites (the effort of a call), by the Settings (what each step runs at, and the warning
when a model lacks what a step needs) and by `reading` (the steps that read the whole guide).

    steps.STEPS["crosscheck"].effort          # "high"
    steps.lacks(steps.STEPS["claims"], caps)  # ["web"] when the engine has no web
"""

from __future__ import annotations

from dataclasses import dataclass

NEEDS = ("web", "whole_guide")  # web: search and fetch; whole_guide: the guide in one call (else by chapter)


@dataclass(frozen=True)
class Step:
    id: str
    role: str  # reasoning | translator: the model of the role in the Settings runs it
    effort: str  # the level the step asks for, before the role's shift (llm.shift_effort)
    needs: tuple[str, ...] = ()
    shown: bool = True  # listed in the Settings (the evaluation judge is not)


STEPS: dict[str, Step] = {s.id: s for s in (
    Step("triage", "reasoning", "medium"),
    Step("proposals", "reasoning", "high"),
    Step("crosscheck", "reasoning", "high", ("web", "whole_guide")),
    Step("fix", "reasoning", "high", ("web", "whole_guide")),
    Step("coherence", "reasoning", "high", ("whole_guide",)),
    Step("compaction", "reasoning", "high", ("whole_guide",)),  # the report: what weighs in the guide
    Step("compact", "reasoning", "high", ("whole_guide",)),  # the trims for the findings kept
    Step("claims", "reasoning", "high", ("web",)),
    Step("deadlinks", "reasoning", "medium", ("web",)),
    Step("mirror", "translator", "medium"),
    Step("translation", "translator", "medium"),
    Step("fix-translation", "translator", "medium"),
    Step("judge", "reasoning", "high", shown=False),
)}


def effort(step: str) -> str:
    return STEPS[step].effort


def of_role(role: str) -> list[Step]:
    """The steps of a role shown in the Settings, in the order of a run."""
    return [s for s in STEPS.values() if s.role == role and s.shown]


def lacks(step: Step, caps) -> list[str]:
    """What `step` needs that an engine with `caps` (llm.Capabilities) does not give: "web" when it has none, "search"
    when it only reads pages (an OpenAI-compatible engine without a search engine set). The whole guide is never
    lacking: a window too small reads it by chapter (reading.py), said in the report."""
    if "web" not in step.needs:
        return []
    return {"none": ["web"], "fetch": ["search"]}.get(caps.web, [])
