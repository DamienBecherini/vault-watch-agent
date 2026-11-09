"""Deterministic access to the vault: French pages, search, excerpts, edits.

The model never touches files. It proposes a replacement; these functions
check that the quoted text exists exactly once and apply it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import inputs

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


_VERSION = re.compile(r"(?<![\w.])v?(\d+)\.(\d+)(?:\.\d+)*(?:\.x|rc\d+)?(?!\w)")
_PRODUCT_MAJOR = re.compile(r"\b([A-Z][A-Za-z]+) ([1-9]\d*)(?:\.\d+)+")  # "CUDA 12.9" also stands for "CUDA 12"
_IDENTIFIER = re.compile(r"(?<![\w.-])-?([a-z]+\d+[a-z\d]*)(?![\w.])")  # cu129, -cu129
_FLAG = re.compile(r"--[a-z][a-z-]+")
_FOOTNOTE_MARK = re.compile(r"\[\^([^\]]+)\](?!:)")
MAX_LEFTOVERS = 80  # lines handed to the model and listed in the report


def _versions(text: str) -> set[str]:
    """Versions reduced to major.minor: "0.33.0", "v0.33.0rc3" and "0.33" are one value."""
    return {f"{m[1]}.{m[2]}" for m in _VERSION.finditer(text)}


def _tokens(text: str) -> set[str]:
    return (_versions(text) | {f"{m[1]} {m[2]}" for m in _PRODUCT_MAJOR.finditer(text)}
            | set(_IDENTIFIER.findall(text)) | set(_FLAG.findall(text)))


def _needle(token: str) -> re.Pattern:
    if re.fullmatch(r"\d+\.\d+", token):
        major, minor = token.split(".")
        return re.compile(rf"(?<![\w.])v?{major}\.{minor}(?!\d)")
    return re.compile(rf"(?<!\w){re.escape(token)}(?!\w)")


def _valid_french(corrections: list[dict]) -> list[dict]:
    return [c for c in corrections if c["check"] == "ok" and not c["page"].startswith("en/")]


def leftovers(vault: Path, corrections: list[dict], limit: int = MAX_LEFTOVERS) -> list[dict]:
    """Where the values these corrections remove (a version, a flag, a package variant) still appear.

    Text the corrections replace is skipped, and so are footnote definitions, which
    record what a past source said. A hit is not an error: "fixed in 0.31.0" stays true.
    """
    valid = _valid_french(corrections)
    needles = {t: _needle(t) for c in valid for t in sorted(_tokens(c["current"]) - _tokens(c["proposed"]))}
    if not needles:
        return []
    hits: list[dict] = []
    for path in french_pages(vault):
        rel = path.relative_to(vault).as_posix()
        text = read(path).replace("\r\n", "\n")
        for c in valid:
            if c["page"] == rel:
                current = c["current"].replace("\r\n", "\n")
                text = text.replace(current, re.sub(r"[^\n]", " ", current))  # blanked: line numbers stay right
        for number, line in enumerate(text.split("\n"), start=1):
            if line.startswith("[^"):
                continue
            found = {t: m.start() for t, n in needles.items() if (m := n.search(line))}
            if found:
                at = min(found.values())
                hits.append({"page": rel, "line": number, "tokens": sorted(found),
                             "text": line[max(0, at - 160):at + 160].strip()})
    return hits[:limit]


def unsourced_versions(vault: Path, corrections: list[dict]) -> dict[str, str]:
    """Corrections whose text adds a version that none of the footnotes it cites mentions.

    Footnotes are read as they will be once every valid correction of the page applies.
    A passage citing no footnote is left alone: there is nothing that could contradict it.
    """
    out: dict[str, str] = {}
    valid = _valid_french(corrections)
    for page in sorted({c["page"] for c in valid}):
        on_page = [c for c in valid if c["page"] == page]
        before = read(vault / page).replace("\r\n", "\n")
        after = before
        for c in on_page:
            after = after.replace(c["current"].replace("\r\n", "\n"), c["proposed"].replace("\r\n", "\n"))
        for c in on_page:
            current = c["current"].replace("\r\n", "\n")
            added = _versions(c["proposed"]) - _versions(current)
            if not added or current.lstrip().startswith("[^"):
                continue
            start = before.find(current)
            end = before.find("\n", start + len(current))
            passage = before[before.rfind("\n", 0, start) + 1: end if end >= 0 else len(before)]
            marks = sorted(set(_FOOTNOTE_MARK.findall(passage)) | set(_FOOTNOTE_MARK.findall(c["proposed"])))
            if not marks:
                continue
            cited: set[str] = set()
            for mark in marks:
                definition = re.search(rf"^\[\^{re.escape(mark)}\]:.*$", after, re.M)
                if definition:
                    cited |= _versions(definition.group(0))
            missing = sorted(added - cited)
            if missing:
                out[c["id"]] = (f"adds {', '.join(missing)}, which the footnotes it cites "
                                f"({', '.join(f'[^{m}]' for m in marks)}) do not mention")
    return out


def date_bump_only(current: str, proposed: str) -> bool:
    """An edit of the `last_modified` line alone: `apply` already bumps it, so the edit is redundant
    (and its quote is gone once another edit of the same page has been applied)."""
    return all(LAST_MODIFIED.fullmatch(t.strip()) for t in (current, proposed))


def sync(vault: Path, base: str = "main") -> None:
    """Fast-forward the local `base` to origin before a run: proposals quote the pages as they are
    on `base`, and the run's branch starts from it (a stale base gave PR #59 merge conflicts)."""
    if "origin" not in inputs.run(["git", "remote"], cwd=vault).split():
        return
    inputs.run(["git", "fetch", "-q", "origin", base], cwd=vault)
    if inputs.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=vault).strip() == base:
        inputs.run(["git", "merge", "-q", "--ff-only", f"origin/{base}"], cwd=vault)
    else:
        inputs.run(["git", "fetch", "-q", "origin", f"{base}:{base}"], cwd=vault)  # fast-forward only


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
