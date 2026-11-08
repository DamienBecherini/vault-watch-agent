"""Deterministic access to the vault: French pages, search, excerpts, edits.

The model never touches files. It proposes a replacement; these functions
check that the quoted text exists exactly once and apply it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Folders that are not French content pages (en/ is the mirror, kept in sync later).
SKIPPED_DIRS = {
    ".git", ".github", ".agents", ".obsidian", "node_modules", "build", "public",
    "assets", "docs", "scripts", "en", "_private", "_templates",
}
SKIPPED_ROOT_FILES = {"README.md", "CLAUDE.md", "AGENTS.md", "LICENSE", "LICENSE-CODE"}

FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
LAST_MODIFIED = re.compile(r'^(last_modified:\s*)"?\d{4}-\d{2}-\d{2}"?\s*$', re.M)


@dataclass(frozen=True)
class Excerpt:
    page: str
    text: str


def read(path: Path) -> str:
    # newline="" keeps the file's own line endings when it is written back.
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def french_pages(vault: Path) -> list[Path]:
    pages = []
    for path in vault.rglob("*.md*"):
        rel = path.relative_to(vault)
        # Dot folders are tooling, never content (.claude/skills, .cursor/plans were read as pages)
        if path.suffix not in (".md", ".mdx") or rel.parts[0] in SKIPPED_DIRS or rel.parts[0].startswith("."):
            continue
        if len(rel.parts) == 1 and rel.name in SKIPPED_ROOT_FILES:
            continue
        pages.append(path)
    return sorted(pages)


def corpus(vault: Path) -> str:
    """Every French page, whole, in a stable order (the prompt cache needs identical bytes)."""
    return "\n".join(
        f"<page path=\"{p.relative_to(vault).as_posix()}\">\n{read(p).replace(chr(13), '')}\n</page>"
        for p in french_pages(vault)
    )


def _paragraphs(text: str) -> list[str]:
    body = FRONTMATTER.sub("", text.replace("\r\n", "\n"))
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def search(vault: Path, terms: list[str], max_pages: int = 4, max_chars: int = 8000) -> list[Excerpt]:
    """Paragraphs of the French pages that name one of the terms, best pages first.

    A page scores one point per distinct term it contains, then by number of
    hits. Terms shorter than three characters are ignored (too noisy).
    """
    needles = sorted({t.lower() for t in terms if len(t.strip()) >= 3})
    if not needles:
        return []
    scored = []
    for path in french_pages(vault):
        low = read(path).lower()
        distinct = sum(1 for n in needles if n in low)
        if distinct:
            scored.append((distinct, sum(low.count(n) for n in needles), path))
    scored.sort(key=lambda s: (-s[0], -s[1], str(s[2])))

    excerpts: list[Excerpt] = []
    budget = max_chars
    for _, _, path in scored[:max_pages]:
        rel = path.relative_to(vault).as_posix()
        for para in _paragraphs(read(path)):
            if budget <= 0:
                return excerpts
            if any(n in para.lower() for n in needles):
                excerpts.append(Excerpt(rel, para[:budget]))
                budget -= len(para)
    return excerpts


def check(vault: Path, page: str, current: str) -> str:
    """'ok' when `current` occurs exactly once in the page, else why not."""
    path = vault / page
    if not path.is_file():
        return "page-not-found"
    count = read(path).replace("\r\n", "\n").count(current.replace("\r\n", "\n"))
    return {0: "text-not-found", 1: "ok"}.get(count, "ambiguous")


def date_bump_only(current: str, proposed: str) -> bool:
    """An edit of the `last_modified` line alone: `apply` already bumps it, so the edit is redundant
    (and its quote is gone once another edit of the same page has been applied)."""
    return all(LAST_MODIFIED.fullmatch(t.strip()) for t in (current, proposed))


def apply(vault: Path, page: str, current: str, proposed: str, today: str) -> None:
    """Replace the single occurrence and bump `last_modified` in the frontmatter."""
    path = vault / page
    text = read(path)
    crlf = "\r\n" in text
    text = text.replace("\r\n", "\n")
    if text.count(current) != 1:
        raise ValueError(f"{page}: the quoted text is no longer unique or present")
    text = text.replace(current, proposed)
    fm = FRONTMATTER.match(text)
    if fm and LAST_MODIFIED.search(fm.group(0)):
        head = LAST_MODIFIED.sub(lambda m: f'{m.group(1)}"{today}"', fm.group(0), count=1)
        text = head + text[fm.end():]
    write(path, text.replace("\n", "\r\n") if crlf else text)
