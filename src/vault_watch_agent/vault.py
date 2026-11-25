"""Deterministic access to the guide: its pages, search, excerpts, edits.

What the pages are (folders, language, mirrors, the date an edit bumps) comes from the guide's manifest, read by
`guide_of`: `vault-watch.toml`, or the IA on-prem layout for a guide without one (guide.legacy).

The model never touches files. It proposes a replacement; these functions
check that the quoted text exists exactly once and apply it.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import inputs
from .guide import MANIFEST, Guide, legacy, load

FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
_guides: dict[Path, tuple[float, Guide]] = {}


def guide_of(root: Path) -> Guide:
    """The guide at `root` (the guide's folder, a run's worktree or the reading copy): its manifest, read again
    when it changes, or the IA on-prem layout when it has none. A wrong manifest raises GuideError."""
    manifest = root / MANIFEST
    stamp = manifest.stat().st_mtime if manifest.is_file() else 0.0
    known = _guides.get(root)
    if known and known[0] == stamp:
        return known[1]
    guide = load(root) if stamp else legacy(root)
    _guides[root] = (stamp, guide)
    return guide


def _date_line(field: str) -> re.Pattern:
    return re.compile(rf'^({re.escape(field)}:\s*)"?\d{{4}}-\d{{2}}-\d{{2}}"?\s*$', re.M)


def in_mirror(root: Path, page: str) -> bool:
    """Whether `page` (relative to the guide) is in one of its mirrors, not a page of the source language."""
    return any(page.startswith(folder) for folder in guide_of(root).mirrors.values())


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


def pages(vault: Path) -> list[Path]:
    """The pages of the guide in its own language (not its mirrors, not its tooling), sorted."""
    return guide_of(vault).pages()


french_pages = pages  # its name before manifests (the source language of the IA on-prem guide)


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


def with_changes_page(vault: Path, excerpts: list[dict]) -> list[dict]:
    """The excerpts of a proposal step, with the manifest's changes page ([watch] changes_page) added whole when they
    lack it: the page where a watch adds dated lines must be there whatever the item's keywords found."""
    page = guide_of(vault).watch.changes_page
    if not page or not (vault / page).is_file() or any(e["page"] == page for e in excerpts):
        return excerpts
    return [*excerpts, {"page": page, "text": read(vault / page)[:CHANGES_PAGE_CHARS]}]


def is_page(vault: Path, page: str) -> bool:
    """Whether `page` names a content page of the guide, or its copy in a mirror: a relative path with /, inside the
    guide, a Markdown file of `include`. What a model writes as the page of a correction comes from what it read
    (a web page, a PDF, a video can say anything): never the guide's scripts, its manifest, a dot folder, nor a file
    outside the guide, which the agent would then run or overwrite."""
    if not _page_like(vault, page):
        return False
    guide = guide_of(vault)
    source = next((page[len(f):] for f in guide.mirrors.values() if page.startswith(f)), page)
    return any(p.relative_to(vault).as_posix() == source for p in guide.pages())


def _page_like(vault: Path, page: str) -> bool:
    """A relative Markdown path with /, inside the guide, outside the dot folders; whether it exists or not."""
    rel = PurePosixPath(page)
    if (not page or "\\" in page or ":" in page or rel.is_absolute() or rel.suffix not in (".md", ".mdx")
            or any(part in ("", "..") or part.startswith(".") for part in page.split("/"))):
        return False
    return (vault / page).resolve().is_relative_to(vault.resolve())


def check(vault: Path, page: str, current: str) -> str:
    """'ok' when `current` occurs exactly once in the page, else why not (a read-only page is never edited; a file
    that is not a page of the guide is never touched: `not-a-page`)."""
    path = vault / page
    if _page_like(vault, page) and not path.is_file():
        return "page-not-found"
    if not is_page(vault, page):
        return "not-a-page"
    if guide_of(vault).is_readonly(page):
        return "read-only"
    count = read(path).replace("\r\n", "\n").count(current.replace("\r\n", "\n"))
    return {0: "text-not-found", 1: "ok"}.get(count, "ambiguous")


_VERSION = re.compile(r"(?<![\w.])v?(\d+)\.(\d+)(?:\.\d+)*(?:\.x|rc\d+)?(?!\w)")
_PRODUCT_MAJOR = re.compile(r"\b([A-Z][A-Za-z]+) ([1-9]\d*)(?:\.\d+)+")  # "CUDA 12.9" also stands for "CUDA 12"
_IDENTIFIER = re.compile(r"(?<![\w.-])-?([a-z]+\d+[a-z\d]*)(?![\w.])")  # cu129, -cu129
_FLAG = re.compile(r"--[a-z][a-z-]+")
_FOOTNOTE_MARK = re.compile(r"\[\^([^\]]+)\](?!:)")
MAX_LEFTOVERS = 80  # lines handed to the model and listed in the report
CHANGES_PAGE_CHARS = 6000  # of the manifest's changes_page, added to every proposal step's excerpts


# -- footnotes: a note cited by no sentence, cited without a definition, defined twice ---------------------------
_NOTE_DEF = re.compile(r"^\[\^([^\]]+)\]:", re.M)
_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)  # a regular expression in code is no footnote


def _note_parts(text: str) -> tuple[set[str], list[str]]:
    """(the notes the text cites, the notes it defines, in order, a note defined twice listed twice)."""
    text = _CODE.sub("", text.replace("\r\n", "\n"))
    defined = _NOTE_DEF.findall(text)
    return set(_FOOTNOTE_MARK.findall(_NOTE_DEF.sub("", text))), defined


def footnote_problems(text: str) -> dict[str, list[str]]:
    """{never_cited, undefined, twice}: the notes of a page that a reader would find broken, each list sorted."""
    cited, defined = _note_parts(text)
    return {"never_cited": sorted(set(defined) - cited), "undefined": sorted(cited - set(defined)),
            "twice": sorted({n for n in defined if defined.count(n) > 1})}


def drop_orphan_notes(before: str, after: str) -> tuple[str, list[str]]:
    """`after` without the definitions of the notes that `before` cited and `after` no longer does (the last sentence
    citing them was removed), and those notes. A note already uncited in `before` is left as it was: not this
    edit's doing. A definition goes with its continuation lines (indented) and the blank line after it."""
    cited_before, _ = _note_parts(before)
    cited_after, defined_after = _note_parts(after)
    orphans = sorted((cited_before - cited_after) & set(defined_after))
    crlf = "\r\n" in after
    text = after.replace("\r\n", "\n")
    for note in orphans:
        text = re.sub(rf"^\[\^{re.escape(note)}\]:.*(?:\n(?:    |\t).*)*\n?(?:\n(?=\S))?", "", text, count=1, flags=re.M)
    return (text.replace("\n", "\r\n") if crlf else text), orphans


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


def _valid_source(vault: Path, corrections: list[dict]) -> list[dict]:
    return [c for c in corrections if c["check"] == "ok" and not in_mirror(vault, c["page"])]


def leftovers(vault: Path, corrections: list[dict], limit: int = MAX_LEFTOVERS) -> list[dict]:
    """Where the values these corrections remove (a version, a flag, a package variant) still appear.

    Text the corrections replace is skipped, and so are footnote definitions, which
    record what a past source said, and the front matter (`verified_by: "Fable 5.1"` is not a
    price list to update: 33 of the 35 hits of add-2026-11-20). A hit is not an error: "fixed in
    0.31.0" stays true.
    """
    valid = _valid_source(vault, corrections)
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
        head = FRONTMATTER.match(text)
        skipped = head.group(0).count("\n") if head else 0  # the front matter: who verified the page, with what
        for number, line in enumerate(text.split("\n"), start=1):
            if number <= skipped or line.startswith("[^"):
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
    valid = _valid_source(vault, corrections)
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


def date_bump_only(current: str, proposed: str, field: str | None = "last_modified") -> bool:
    """An edit of the modified-date line alone (`field` of the manifest): `apply` already bumps it, so the edit is
    redundant (and its quote is gone once another edit of the same page has been applied)."""
    return bool(field) and all(_date_line(field).fullmatch(t.strip()) for t in (current, proposed))


# One git operation at a time on the guide's repository: two runs started together (a fix pass and a translation
# pass, 18/11/2026) both fetched and reset the reading copy, and the second one failed on git's index.lock.
_GIT = threading.RLock()


def sync(vault: Path, base: str = "main") -> None:
    """Fast-forward the local `base` to origin before a run: proposals quote the pages as they are
    on `base`, and the run's branch starts from it (a stale base gave PR #59 merge conflicts)."""
    with _GIT:
        _sync(vault, base)


def _sync(vault: Path, base: str) -> None:
    if "origin" not in inputs.run(["git", "remote"], cwd=vault).split():
        return
    inputs.run(["git", "fetch", "-q", "origin", base], cwd=vault)
    if inputs.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=vault).strip() == base:
        settle(vault, f"origin/{base}")
        inputs.run(["git", "merge", "-q", "--ff-only", f"origin/{base}"], cwd=vault)
    else:
        inputs.run(["git", "fetch", "-q", "origin", f"{base}:{base}"], cwd=vault)  # fast-forward only


PR_NUMBER = re.compile(r"\(#(\d+)\)\s*$")


def folder_state(vault: Path, base: str = "main", fetch: bool = True) -> dict:
    """Where the guide's folder stands against its origin, for the page of the agent: `branch` ("" when detached),
    `base`, `behind` (the commits of origin's `base` that the local `base` lacks, newest first: {sha, title, pr},
    `pr` the number a squash merge writes at the end of its title), `changes` (files changed or new, not committed),
    `updated` (when the local `base` last moved, from git's reflog) and `offline` (why origin could not be asked;
    `behind` is then what was known at the last fetch). No origin: nothing is behind."""
    with _GIT:
        out = {"branch": "", "base": base, "behind": [], "changes": [], "updated": "", "offline": "", "origin": False}
        branch = inputs.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=vault).strip()
        out["branch"] = "" if branch == "HEAD" else branch
        out["changes"] = [line[3:].strip().strip('"') for line in
                          inputs.run(["git", "status", "--porcelain"], cwd=vault).splitlines() if line.strip()]
        try:
            out["updated"] = inputs.run(["git", "reflog", "show", "--date=iso-strict", "--format=%gd", "-n", "1", base],
                                        cwd=vault).strip().partition("@{")[2].rstrip("}")
        except RuntimeError:
            pass
        if "origin" not in inputs.run(["git", "remote"], cwd=vault).split():
            return out
        out["origin"] = True
        if fetch:
            try:
                inputs.run(["git", "fetch", "-q", "origin", base], cwd=vault)
            except RuntimeError as e:
                out["offline"] = str(e)[-300:]
        try:
            log = inputs.run(["git", "log", "--format=%H%x09%s", f"{base}..origin/{base}"], cwd=vault)
        except RuntimeError:
            return out
        for line in log.splitlines():
            sha, _, title = line.partition("\t")
            number = PR_NUMBER.search(title)
            out["behind"].append({"sha": sha[:7], "title": PR_NUMBER.sub("", title).strip(),
                                  "pr": int(number.group(1)) if number else None})
        return out


def update_folder(vault: Path, base: str = "main") -> dict:
    """« Update my folder »: the local `base` moves forward to origin's, as before a run (fast-forward only; what
    is not committed stays, a file the merge already says the same is put back first). The checked-out branch is
    never changed: on another branch, `base` alone moves. Returns {ok, from, to, files (how many changed), kept (the
    files not committed, left as they were), branch}; when git refuses, {ok: False, why, files (those in the way)}
    and nothing has moved."""
    with _GIT:
        before = inputs.run(["git", "rev-parse", base], cwd=vault).strip()
        try:
            _sync(vault, base)
        except RuntimeError as e:
            said = str(e)
            in_way = [line.strip() for line in said.splitlines() if line.startswith(("\t", "        "))]
            return {"ok": False, "why": said[-400:], "files": in_way}
        after = inputs.run(["git", "rev-parse", base], cwd=vault).strip()
        changed = inputs.run(["git", "diff", "--name-only", before, after], cwd=vault).splitlines() if before != after else []
        kept = [line[3:].strip().strip('"') for line in inputs.run(["git", "status", "--porcelain"], cwd=vault).splitlines() if line.strip()]
        branch = inputs.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=vault).strip()
        return {"ok": True, "from": before[:7], "to": after[:7], "files": len(changed), "kept": kept,
                "branch": "" if branch == "HEAD" else branch}


def settle(vault: Path, target: str) -> list[str]:
    """The files changed in the folder and not committed whose text is already the one of `target`: put back to
    their last commit, so that moving to `target` can go on (git refuses to overwrite a local change, even one that
    says the same). A page edited by hand and sent by « Sync the languages » is such a file once its pull request is
    merged. Any other local change is left as it is. Returns the files put back."""
    back = []
    for name in inputs.run(["git", "diff", "--name-only", "HEAD"], cwd=vault).splitlines():
        try:
            merged = inputs.run(["git", "show", f"{target}:{name}"], cwd=vault)
        except RuntimeError:
            continue  # not in target
        path = vault / name
        if path.is_file() and read(path).replace("\r\n", "\n") == merged.replace("\r\n", "\n"):
            back.append(name)
    if back:
        inputs.run(["git", "checkout", "-q", "--", *back], cwd=vault)
    return back


def reading_copy(vault: Path, home: Path, base: str = "main") -> Path:
    """The guide as it is on `base`, up to date with origin, for what reads the pages without changing them (a
    verification, the proposals for reported errors). The folder of the guide may be on another branch, or hold work
    in progress: reading it gave findings on text already corrected on `base` (17/11/2026, after the merge of #78).
    A worktree of the agent, detached at `base`, reset at each call."""
    with _GIT:
        return _reading_copy(vault, home, base)


def _reading_copy(vault: Path, home: Path, base: str) -> Path:
    sync(vault, base)
    copy = home / "worktrees" / f"read-{base}"
    if not (copy / ".git").exists():
        copy.parent.mkdir(parents=True, exist_ok=True)
        inputs.run(["git", "worktree", "prune"], cwd=vault)  # a copy deleted by hand is still registered
        inputs.run(["git", "worktree", "add", "-q", "--detach", str(copy), base], cwd=vault)
    else:
        inputs.run(["git", "checkout", "-q", "--detach", "--force", base], cwd=copy)
        inputs.run(["git", "clean", "-q", "-fd"], cwd=copy)
    return copy


def replaced(text: str, current: str, proposed: str) -> str:
    """`text` (line breaks as \\n) with `current` replaced by `proposed`. An empty `proposed` removes the passage
    cleanly: lines removed whole go with their line break (a table keeps its rows together, a list its items), a
    paragraph removed whole does not leave two blank lines, a sentence removed inside a line no double space."""
    current, proposed = current.replace("\r\n", "\n"), proposed.replace("\r\n", "\n")
    if proposed.strip():
        return text.replace(current, proposed)
    start = text.find(current)
    if start < 0:
        return text
    end = start + len(current)
    before, after = text[:start], text[end:]
    if (not before or before.endswith("\n")) and (not after or after.startswith("\n")):
        after = after[1:]  # whole lines: their line break goes too
        if before.endswith("\n\n") and after.startswith("\n"):
            after = after[1:]
    elif before.endswith(" ") and after.startswith(" "):
        after = after[1:]
    return before + after


_FULL_VERSION = re.compile(r"(?<![\w.])v?(\d+(?:\.\d+)+)(?:\.x|rc\d+)?(?!\w)")
_URL = re.compile(r"https?://[^\s<>\[\]()\"'|]+")
_ADVISORY = re.compile(r"\b(?:CVE-\d{4}-\d{3,}|GHSA(?:-[0-9a-z]{4}){3})\b")
_AMOUNT = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s?(%|€|\$|k€|M€|[GMTk]o|[GMTK]i?B|k?Wh?|ms|tokens?/s|tok/s|t/s)(?!\w)")


def _facts(text: str) -> set[str]:
    """What a passage states that can be looked for elsewhere: versions (whole: 0.33.1 is not 0.33.0), advisory
    ids, URLs, amounts with their unit (« 3,19 $ », « 48 Go »), package variants and flags."""
    return ({m[1] for m in _FULL_VERSION.finditer(text)} | set(_ADVISORY.findall(text))
            | {u.rstrip(".,;:") for u in _URL.findall(text)} | {f"{n} {unit}" for n, unit in _AMOUNT.findall(text)}
            | set(_IDENTIFIER.findall(text)) | set(_FLAG.findall(text)))


def lost(vault: Path, corrections: list[dict]) -> dict[str, list[str]]:
    """Per correction, the values it removes (in its `current`, not in its `proposed`) that no page of the guide
    states any more once every valid correction applies. For a trim: a repetition removed leaves the value in the
    page that keeps it, and is not listed; the only statement of a version, a price or a source is. A signal for
    the reviewer, not a refusal: history is removed on purpose."""
    valid = _valid_source(vault, corrections)
    by_page: dict[str, list[dict]] = {}
    for c in valid:
        by_page.setdefault(c["page"], []).append(c)
    kept: set[str] = set()
    for path in french_pages(vault):
        text = read(path).replace("\r\n", "\n")
        for c in by_page.get(path.relative_to(vault).as_posix(), []):
            text = replaced(text, c["current"], c["proposed"])
        kept |= _facts(text)
    out = {}
    for c in valid:
        gone = sorted(_facts(c["current"]) - _facts(c["proposed"]) - kept)
        if gone:
            out[c["id"]] = gone
    return out


def apply(vault: Path, page: str, current: str, proposed: str, today: str) -> None:
    """Replace the single occurrence and bump the modified date of the front matter (the manifest's
    `modified_field`; none when the guide has no such field). An empty `proposed` removes the passage (`replaced`)."""
    if not is_page(vault, page):
        raise ValueError(f"{page}: not a page of the guide")
    path = vault / page
    text = read(path)
    crlf = "\r\n" in text
    text = text.replace("\r\n", "\n")
    if text.count(current) != 1:
        raise ValueError(f"{page}: the quoted text is no longer unique or present")
    text = replaced(text, current, proposed)
    fm = FRONTMATTER.match(text)
    field = guide_of(vault).modified_field
    if fm and field and _date_line(field).search(fm.group(0)):
        head = _date_line(field).sub(lambda m: f'{m.group(1)}"{today}"', fm.group(0), count=1)
        text = head + text[fm.end():]
    write(path, text.replace("\n", "\r\n") if crlf else text)
