"""Whether the whole guide fits in one call of the model, or must be read chapter by chapter.

The cross-check, its sweep and the coherence check read the whole guide in one call: a contradiction between two
pages far apart is found only that way. That needs a model whose window holds the guide plus what the call adds
(the instructions, the corrections, the pages read on the web, the answer). When it does not, these steps run
chapter by chapter, each call with one chapter and the pages the corrections change; the report and the run view
say so, because a contradiction between two chapters can then be missed.

    plan = reading.plan(vault_dir, llm)        # Plan(mode="whole" | "chapters", tokens, budget, exact)
    reading.chapters(vault_dir)               # {"01-basics": [Path, ...], "(root)": [...]}
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from . import vault

RESERVE = 100_000  # tokens kept for what a call adds to the guide: instructions, corrections, web pages, answer


def reserve(window: int) -> int:
    """What a call keeps beside the guide: 100k with the 1M windows, a third of a smaller one (a model of 64k tokens
    keeps about 21k), never less than 8k. A fixed 100k left a 64k window a negative budget: a guide of 2k tokens was
    read by chapter (seen 18/11/2026 on a local model)."""
    return max(8_192, min(RESERVE, window // 3))
BYTES_PER_TOKEN = 2.1  # measured on the IA on-prem guide (French, Markdown); see verify.py
MARGIN = 1.15  # an estimate is raised by 15 %: a guide in another language or with more code has more tokens per byte


@dataclass(frozen=True)
class Plan:
    mode: str  # whole | chapters
    tokens: int  # the guide, counted or estimated
    budget: int  # what a call may put of the guide: the window minus the reserve, capped by the manifest
    exact: bool  # counted by the engine (else estimated from the size of the pages)

    @property
    def note(self) -> str:
        """One line for the report and the run view."""
        size = f"{'' if self.exact else '≈ '}{self.tokens:,} tokens"
        if self.mode == "whole":
            return f"whole guide in one call ({size}, budget {self.budget:,})"
        return (f"by chapter: the guide ({size}) exceeds what one call may read ({self.budget:,}); "
                "a contradiction between two chapters can be missed")

    def summary(self) -> dict:
        return {**asdict(self), "note": self.note}


def chapters(vault_dir: Path) -> dict[str, list[Path]]:
    """The pages by top folder; the pages at the root (index, home) form one group."""
    groups: dict[str, list[Path]] = {}
    for p in vault.pages(vault_dir):
        parts = p.relative_to(vault_dir).parts
        groups.setdefault(parts[0] if len(parts) > 1 else "(root)", []).append(p)
    return groups


def plan(vault_dir: Path, llm, window: int | None = None) -> Plan:
    """How the steps that need the whole guide will read it with `llm` (its Capabilities, when it declares them;
    a model client without them, a test's fake for instance, reads the whole guide)."""
    caps = llm.capabilities() if hasattr(llm, "capabilities") else None
    window = window or (caps.context if caps else None)
    text = vault.corpus(vault_dir)
    tokens, exact = None, False
    if caps and caps.exact_count and hasattr(llm, "count_tokens"):
        tokens = llm.count_tokens(text)
        exact = tokens is not None
    if tokens is None:
        tokens = int(len(text.encode("utf-8")) / BYTES_PER_TOKEN * MARGIN)
    if window is None:
        return Plan("whole", tokens, 0, exact)
    budget = window - reserve(window)
    cap = vault.guide_of(vault_dir).max_context_tokens
    if cap:
        budget = min(budget, cap)
    return Plan("whole" if tokens <= budget else "chapters", tokens, budget, exact)


def corpus_of(vault_dir: Path, pages: list[Path]) -> str:
    """The given pages, in the guide's order (the same bytes for the same pages: the prompt cache needs them)."""
    keep = {p.resolve() for p in pages}
    return "\n".join(f"<page path=\"{p.relative_to(vault_dir).as_posix()}\">\n{vault.read(p).replace(chr(13), '')}\n</page>"
                     for p in vault.pages(vault_dir) if p.resolve() in keep)


def add_usage(usages: list[dict], node: str) -> dict:
    """Several calls of one step as one line of the run's usage (each call stays a line of the journal)."""
    total: dict = {"node": node, "model": usages[0].get("model", "") if usages else ""}
    for u in usages:
        for k, v in u.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                total[k] = round(total.get(k, 0) + v, 6)
        for k in ("engine", "effort"):
            if k in u:
                total[k] = u[k]
    return total
