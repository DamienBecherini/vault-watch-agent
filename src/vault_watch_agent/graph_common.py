"""What the nodes of the graph share: their dependencies (`Deps`), git in a worktree, the order of the proposals and
the branch of a run."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import inputs, vault
from .llm import LLM
from .state import WatchState


@dataclass
class Deps:
    vault: Path  # local clone of the vault (read-only until apply)
    home: Path  # working folder: downloads, reports, worktrees
    llm: LLM
    translator: LLM | None = None  # cheaper model for the English mirror; defaults to llm
    crosscheck: bool = True  # re-read the corrections against the whole guide before the review
    repo: str = ""  # owner/name on GitHub; "" = the manifest's ([guide] repository), "" there too = local only
    base: str = ""  # "" = the manifest's base branch
    today: str = field(default_factory=lambda: date.today().isoformat())

    def __post_init__(self):
        guide = vault.guide_of(self.vault)
        self.repo = self.repo or guide.repository
        self.base = self.base or guide.base_branch


def git(*args: str, cwd: Path, text: str | None = None) -> str:
    return inputs.run(["git", *args], cwd=cwd, text=text)


def sorted_proposals(state: WatchState) -> list[dict]:
    order = {i["id"]: n for n, i in enumerate(state["items"])}
    return sorted(state.get("proposals", []), key=lambda p: order[p["item_ids"][0]])


def watch_branch(state: WatchState) -> str:
    """The branch of a watch's run: `chore/watch-<as_of>`, then its issue (`-55`), or the name of its watch file
    when that name does not already say the date, so that two watches of the same day never share a branch."""
    name = f"chore/watch-{state['as_of']}"
    if state.get("issue"):
        return f"{name}-{state['issue']}"
    stem = Path(str(state.get("source") or "")).stem
    if not stem or state["as_of"] in stem:
        return name
    return f"{name}-{re.sub(r'[^A-Za-z0-9._-]+', '-', stem).strip('-.')}"
