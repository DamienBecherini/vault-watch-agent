"""The pause to retouch the pages of a run's branch, before the mirrors (H3): in the editor's own Obsidian, on the
guide's folder lent to the run, or in the page of the agent.

The run's branch is checked out in the agent's worktree, and git refuses one branch in two places: the folder is
lent detached at the tip of the branch. The editor retouches there; « done » commits what changed in the folder (as
the editor: their own git identity), moves the branch forward to that commit, and gives the folder back to where it
was. What the folder held and was not committed is set aside first (a stash named after the run) and put back after.

    state(folder)                          # where the folder is, what it holds, whether it can be lent
    lend(folder, home, thread, tip, aside) # the folder, detached at `tip`; what was in it set aside if asked
    give_back(folder, home, thread, worktree, keep=True)   # commit the retouches (keep), move the branch, restore
    where(folder, home, thread, worktree)  # the tree the page's editor writes to: the folder lent, else the worktree
    pending(home)                          # what was set aside and not put back yet (a banner of the page)

A record per run, in the agent's home (`lent.json`), says what was lent and set aside: a server stopped in between
still knows what to put back.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

RECORD = "lent.json"
MESSAGE = "Retouches at the review"


class FolderError(RuntimeError):
    """The folder cannot be lent or given back as asked; the message says why and what to do."""


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise FolderError(f"git {' '.join(args[:3])}: {done.stderr.strip()[:400]}")
    return done.stdout


def _records(home: Path) -> dict:
    try:
        found = json.loads((home / RECORD).read_text(encoding="utf-8"))
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(home: Path, records: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / RECORD).write_text(json.dumps(records, indent=2), encoding="utf-8")


def state(folder: Path) -> dict:
    """Where the guide's folder is and whether it can be lent: `branch` ("" when detached), `head`, `changes` (the
    files changed or new, not committed; what git ignores, Obsidian's workspace among them, does not count),
    `blocked` (a merge or a rebase in progress: nothing can be set aside then)."""
    gitdir = Path(git(folder, "rev-parse", "--absolute-git-dir").strip())
    blocked = next((why for name, why in (("MERGE_HEAD", "a merge is in progress"), ("rebase-merge", "a rebase is in progress"),
                                          ("rebase-apply", "a rebase is in progress"), ("CHERRY_PICK_HEAD", "a cherry-pick is in progress"))
                    if (gitdir / name).exists()), "")
    changes = [line[3:].strip().strip('"') for line in git(folder, "status", "--porcelain").splitlines() if line.strip()]
    branch = git(folder, "rev-parse", "--abbrev-ref", "HEAD").strip()
    return {"branch": "" if branch == "HEAD" else branch, "head": git(folder, "rev-parse", "HEAD").strip(),
            "changes": changes, "blocked": blocked}


def lent_to(home: Path) -> str:
    """The run the folder is lent to, "" when it is not."""
    return next((t for t, r in _records(home).items() if r.get("lent")), "")


def lend(folder: Path, home: Path, thread: str, tip: str, set_aside: bool = False) -> dict:
    """Lends the guide's folder to `thread`: detached at `tip`, the last commit of the run's branch. Refused when the
    folder is lent to another run, when a merge or a rebase is in progress, or when it holds changes not committed
    and `set_aside` is not asked."""
    holder = lent_to(home)
    if holder and holder != thread:
        raise FolderError(f"the folder is lent to the run {holder}: finish its retouches first")
    if holder == thread:
        return _records(home)[thread]
    now = state(folder)
    if now["blocked"]:
        raise FolderError(f"{now['blocked']} in the guide's folder: finish it, or retouch in the page")
    if now["changes"] and not set_aside:
        raise FolderError("the guide's folder holds changes not committed: set them aside, or retouch in the page")
    record = {"lent": True, "back_to": now["branch"] or now["head"], "stash": "", "at": time.time(),
              "aside": now["changes"] if set_aside else []}
    records = _records(home)
    if now["changes"]:
        git(folder, "stash", "push", "-u", "-m", f"vault-watch {thread}")
        record["stash"] = git(folder, "rev-parse", "stash@{0}").strip()
    records[thread] = record
    _save(home, records)  # written before the switch: a failure below still knows what to put back
    try:
        git(folder, "checkout", "-q", "--detach", tip)
    except FolderError:
        _restore(folder, home, thread)
        raise
    return record


def where(folder: Path, home: Path, thread: str, worktree: Path) -> Path:
    """The tree the retouches are made in: the folder while it is lent to `thread`, else the run's worktree."""
    return folder if _records(home).get(thread, {}).get("lent") else worktree


def changed(tree: Path) -> list[str]:
    """The files changed or new in a tree, not committed (git's ignored files left out)."""
    return [line[3:].strip().strip('"') for line in git(tree, "status", "--porcelain").splitlines() if line.strip()]


def commit(tree: Path) -> str:
    """Commits what changed in `tree` as the retouches of the review; "" when nothing changed."""
    if not changed(tree):
        return ""
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", MESSAGE)
    return git(tree, "rev-parse", "HEAD").strip()


def give_back(folder: Path, home: Path, thread: str, worktree: Path, keep: bool = True) -> str:
    """Ends the retouches of `thread` in the folder: commits them (`keep`) or drops them, moves the run's branch to
    that commit, gives the folder back to where it was and puts back what was set aside. Returns the commit of the
    retouches, "" when there is none. Without the folder lent, it does the same in the worktree."""
    record = _records(home).get(thread, {})
    if not record.get("lent"):
        if not keep and changed(worktree):
            git(worktree, "checkout", "-q", "--", ".")
            git(worktree, "clean", "-q", "-fd")
        return commit(worktree) if keep else ""
    sha = ""
    if keep:
        sha = commit(folder)
    elif changed(folder):
        git(folder, "checkout", "-q", "--", ".")
        git(folder, "clean", "-q", "-fd")
    if sha:
        git(worktree, "merge", "-q", "--ff-only", sha)
    _restore(folder, home, thread)
    return sha


def _restore(folder: Path, home: Path, thread: str) -> None:
    """The folder back where it was, and what was set aside put back. Kept in the record (`stash` still set) when it
    cannot be put back, so that the page shows it until it is."""
    records = _records(home)
    record = records.get(thread)
    if not record:
        return
    git(folder, "checkout", "-q", record["back_to"])
    record["lent"] = False
    _save(home, records)
    put_back(folder, home, thread)


def put_back(folder: Path, home: Path, thread: str) -> None:
    """Puts back what was set aside for `thread` (the folder is no longer lent), then forgets the record."""
    records = _records(home)
    record = records.get(thread)
    if not record or record.get("lent"):
        return
    if record.get("stash"):
        git(folder, "stash", "apply", record["stash"])  # an error keeps the record: the banner stays
        listed = git(folder, "stash", "list", "--format=%H %gd").splitlines()
        ref = next((line.split()[1] for line in listed if line.split()[0] == record["stash"]), "")
        if ref:
            git(folder, "stash", "drop", "-q", ref)
    records.pop(thread, None)
    _save(home, records)


def pending(home: Path) -> list[dict]:
    """The runs whose retouches lent the folder or set something aside, not given back yet: {thread, lent, aside}."""
    return [{"thread": t, "lent": bool(r.get("lent")), "aside": r.get("aside", [])} for t, r in _records(home).items()]
