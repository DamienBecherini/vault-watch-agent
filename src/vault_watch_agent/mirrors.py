"""What changed in a source page, as edits a translator can carry to its mirror: paragraph by paragraph, from git.

The mirror step used to translate correction by correction (`current` → `proposed`), so it could not follow an edit
made by hand. It now reads the page as it was and as it is, and hands the translator what differs:

    changes(old, new)                      # [(old passage, new passage), …]: a paragraph, a table row, a list line
    changed_pages(worktree, since)         # the source pages that differ from `since` (a commit or a branch)
    edits_of(worktree, page, since)        # changes() of one page between `since` and the working tree
    behind(guide)                          # the source pages ahead of their mirror, and since which commit

A passage is a block of the page: lines between blank lines, a fenced code block whole. A block changed into one
block of several lines (a table, a list) is compared line by line, so one row changed is one row to translate. A
block added comes with the block before it (the translator finds where to write it); a block removed has an empty
new text (the translator removes the matching passage).
"""

from __future__ import annotations

import difflib
import re
import subprocess
from pathlib import Path

from . import vault

_FENCE = re.compile(r"^\s*(```|~~~)")


def blocks(text: str) -> list[str]:
    """The blocks of a page: lines between blank lines; a fenced code block is one block, blank lines included."""
    out, current, fenced = [], [], False
    for line in text.replace("\r\n", "\n").split("\n"):
        if _FENCE.match(line):
            fenced = not fenced
        if not line.strip() and not fenced:
            if current:
                out.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        out.append("\n".join(current))
    return out


def _lines(old: str, new: str) -> list[tuple[str, str]]:
    """One block changed into one block, compared line by line (a table, a list, a front matter)."""
    a, b = old.split("\n"), new.split("\n")
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag == "insert":  # anchored on the line before (or after, at the top of the block)
            if i1 > 0:
                out.append((a[i1 - 1], "\n".join([a[i1 - 1], *b[j1:j2]])))
            else:
                out.append((a[0], "\n".join([*b[j1:j2], a[0]])))
        else:
            out.append(("\n".join(a[i1:i2]), "\n".join(b[j1:j2])))
    return out


def changes(old: str, new: str) -> list[tuple[str, str]]:
    """What differs between two versions of a page: [(old passage, new passage)], in the order of the page."""
    a, b = blocks(old), blocks(new)
    out: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag == "insert":
            added = "\n\n".join(b[j1:j2])
            if i1 > 0:
                out.append((a[i1 - 1], f"{a[i1 - 1]}\n\n{added}"))
            elif a:
                out.append((a[0], f"{added}\n\n{a[0]}"))
            else:
                out.append(("", added))
        elif tag == "replace" and i2 - i1 == j2 - j1:  # as many blocks on each side: each one with its own
            for old_block, new_block in zip(a[i1:i2], b[j1:j2]):
                if "\n" in old_block and "\n" in new_block:
                    out += _lines(old_block, new_block)
                else:
                    out.append((old_block, new_block))
        else:
            out.append(("\n\n".join(a[i1:i2]), "\n\n".join(b[j1:j2])))
    return out


def hunks(old: str, new: str, field: str | None = None, context: int = 2) -> list[dict]:
    """What changed between two versions of a page, line by line, to be read before a sync: each changed zone with
    `context` lines above and below, {above: [lines], old: text, new: text, below: [lines]}. A change of the date line
    alone is left out (`apply` bumps it)."""
    a, b = old.replace("\r\n", "\n").split("\n"), new.replace("\r\n", "\n").split("\n")
    out = []
    for group in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_grouped_opcodes(context):
        first, last = group[0], group[-1]
        above = a[first[1]:first[2]] if first[0] == "equal" else []
        below = a[last[1]:last[2]] if last[0] == "equal" else []
        middle = [op for op in group if op not in (first, last) or op[0] != "equal"]
        if not middle:  # the two versions are the same
            continue
        old_zone = "\n".join(a[middle[0][1]:middle[-1][2]])
        new_zone = "\n".join(b[middle[0][3]:middle[-1][4]])
        if field and vault.date_bump_only(old_zone, new_zone, field):
            continue
        out.append({"above": above, "old": old_zone, "new": new_zone, "below": below})
    return out


def git(worktree: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=worktree, check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout


def show(worktree: Path, since: str, page: str) -> str:
    """The page as it was at `since`; "" when it did not exist then."""
    try:
        return git(worktree, "show", f"{since}:{page}")
    except subprocess.CalledProcessError:
        return ""


def changed_pages(worktree: Path, since: str) -> list[str]:
    """The source pages (not the mirrors) whose text differs between `since` and the working tree, sorted."""
    names = git(worktree, "diff", "--name-only", since, "--", "*.md", "*.mdx").splitlines()
    sources = {p.relative_to(worktree).as_posix() for p in vault.pages(worktree)}
    return sorted(n for n in names if n in sources)


def edits_of(worktree: Path, page: str, since: str) -> list[tuple[str, str]]:
    """The changes of a source page since `since`, without those of its date line alone (`apply` bumps it)."""
    field = vault.guide_of(worktree).modified_field
    now = vault.read(worktree / page) if (worktree / page).is_file() else ""
    return [(o, n) for o, n in changes(show(worktree, since, page), now)
            if not vault.date_bump_only(o, n, field) and not _front_matter_date_only(o, n, field)]


def _front_matter_date_only(old: str, new: str, field: str | None) -> bool:
    """A front matter whose only change is its date line (the block compared whole when it has no other change)."""
    if not field or not old.startswith("---"):
        return False
    date = re.compile(rf"^{re.escape(field)}\s*:.*$", re.M)
    return date.sub("", old) == date.sub("", new) and old != new


def behind(guide: Path, language: str) -> dict[str, str]:
    """The source pages ahead of their mirror in `language`: {page: the commit to translate from}. That commit is
    the last one that touched the mirror page: the two were in step then (or as close as the mirror got). A page whose
    mirror does not exist is left to the translation check, which reports it."""
    g = vault.guide_of(guide)
    folder = g.mirrors.get(language)
    if not folder:
        return {}
    last: dict[str, str] = {}
    commit = ""
    for line in git(guide, "log", "--format=@%H", "--name-only", "--", f"{folder}*").splitlines():
        if line.startswith("@"):
            commit = line[1:]
        elif line and line not in last:
            last[line] = commit
    by_since: dict[str, list[str]] = {}
    for page in (p.relative_to(guide).as_posix() for p in g.pages()):
        since = last.get(f"{folder}{page}")
        if since:
            by_since.setdefault(since, []).append(page)
    out = {}
    for since, pages in by_since.items():  # one diff per commit, then a closer look at the pages it names
        moved = set(git(guide, "diff", "--name-only", since, "HEAD", "--", *pages).splitlines())
        out.update({page: since for page in pages if page in moved and edits_of_commit(guide, page, since)})
    return dict(sorted(out.items()))


def edits_of_commit(guide: Path, page: str, since: str) -> list[tuple[str, str]]:
    """edits_of() between `since` and HEAD (not the working tree): what is committed only."""
    field = vault.guide_of(guide).modified_field
    return [(o, n) for o, n in changes(show(guide, since, page), show(guide, "HEAD", page))
            if not vault.date_bump_only(o, n, field) and not _front_matter_date_only(o, n, field)]


def folder_changes(folder: Path) -> dict[str, int]:
    """The source pages changed in the guide's folder and not committed (edited by hand in Obsidian, say), each with
    the number of passages that differ from its last commit. A new page, not committed yet, has no mirror to follow."""
    names = git(folder, "diff", "--name-only", "HEAD", "--", "*.md", "*.mdx").splitlines()
    sources = {p.relative_to(folder).as_posix() for p in vault.pages(folder)}
    found = {name: len(edits_of(folder, name, "HEAD")) for name in names if name in sources}
    return {name: n for name, n in sorted(found.items()) if n}


def prepare(folder: Path, home: Path, base: str, branch: str, hand: list[str]) -> Path:
    """The worktree of a « Sync the languages » run: `branch` made from `base`, with the pages of `hand` copied from
    the guide's folder as they are there (edited by hand, not committed) and committed as such. The folder itself is
    not touched: its copies stay as they were, and match what is merged (vault.sync puts them in line then)."""
    worktree = home / "worktrees" / branch.replace("/", "-")
    with vault._GIT:
        if worktree.exists():
            git(worktree, "checkout", "-q", "-B", branch, base)
            git(worktree, "clean", "-q", "-fd")
        else:
            worktree.parent.mkdir(parents=True, exist_ok=True)
            git(folder, "worktree", "prune")
            git(folder, "worktree", "add", "-q", "-B", branch, str(worktree), base)
    for page in hand:
        (worktree / page).write_bytes((folder / page).read_bytes())
    if hand:
        git(worktree, "add", "--", *hand)
        git(worktree, "commit", "-q", "-m", "docs: edits by hand\n\n" + "\n".join(hand))
    return worktree


def initial_state(thread: str, branch: str, worktree: Path, since: dict[str, str], hand: list[str], today: str) -> dict:
    """The state a « Sync the languages » run enters the graph with, as if `apply` had just run: the mirror step
    translates what changed, from `since` for the pages ahead of their mirror, from the base for the pages edited
    by hand; then the guide's checks, the links and the pause before the pull request."""
    return {
        "source": "the source pages ahead of their mirrors", "issue": None, "as_of": today, "mode": "mirror",
        "title": "chore(i18n): the mirrors follow the source pages" + (" edited by hand" if hand else ""),
        "branch_name": branch, "branch": branch, "worktree": str(worktree),
        "items": [], "claims_due": [], "decisions": [], "evidence": {}, "proposals": [], "usage": [],
        "corrections": [], "accepted": [], "applied": [], "mirror_since": dict(since), "hand_pages": list(hand),
        "report_path": "",
    }


def plan(folder: Path, home: Path) -> dict:
    """What can be synced, for the page and the command line: the source pages ahead of their mirror on the base
    branch (`since`: the commit to translate each from, `ahead`: its passages changed), those edited in the guide's
    folder and not committed (`hand`), and those of the folder not offered (`elsewhere`): a page whose committed
    text is not the merged one, copied onto a branch of the base, would undo what the base received since.
    `copy`: the guide as merged (vault.reading_copy), where the pages ahead were read."""
    g = vault.guide_of(folder)
    out = {"base": g.base_branch, "languages": dict(sorted(g.mirrors.items())), "since": {}, "ahead": {}, "hand": {},
           "elsewhere": [], "copy": None}
    if not g.mirrors:
        return out
    copy = out["copy"] = vault.reading_copy(folder, home, g.base_branch)
    for code in sorted(g.mirrors):
        for page, commit in behind(copy, code).items():
            out["since"].setdefault(page, commit)
    out["ahead"] = {page: len(edits_of_commit(copy, page, commit)) for page, commit in sorted(out["since"].items())}
    for page, n in folder_changes(folder).items():
        if show(folder, "HEAD", page) != show(copy, "HEAD", page):
            out["elsewhere"].append(page)
        else:
            out["hand"][page] = n
    return out
