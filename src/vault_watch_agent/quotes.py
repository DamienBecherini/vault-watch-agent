"""The passage a finding is about, found in the page itself.

A finding (a doubt of the cross-check, a lead of a check of the guide) names a page and says what is wrong. The model
also quotes the passage; this module looks for it in the page, so the reviewer sees the sentence in question
without opening the page. What is shown always comes from the page, never from the model: an exact match, else the
closest passage of the page (an approximate match, flagged as such), else « excerpt not found ».
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from pydantic import BaseModel, Field

from . import vault

APPROX = 0.8  # similarity below which the closest passage is not shown: a wrong excerpt is worse than none
CONTEXT = 1  # non-blank lines shown before and after the passage
CLIP = 320  # characters kept of a long line, around the passage


class Quote(BaseModel):
    page: str = Field(description="Vault-relative path of the page the passage is in (en/… for the English mirror).")
    quote: str = Field(description="The passage in question, copied verbatim from that page (same accents, "
                       "punctuation and Markdown), short: one sentence or one table row.")


_PUNCT = str.maketrans({"’": "'", "‘": "'", "«": '"', "»": '"', "“": '"', "”": '"', " ": " ", " ": " ",
                        "–": "-", "—": "-"})


def _norm(text: str) -> str:
    """For the approximate match: case, typographic quotes, Markdown emphasis, wiki links (their label counts),
    footnote markers and spacing do not count."""
    text = unicodedata.normalize("NFC", text).translate(_PUNCT).lower()
    text = re.sub(r"\[\[(?:[^\]|]*?\\?\|)?([^\]]*)\]\]", r"\1", text)  # [[page\|label]] → label, [[page]] → page
    text = re.sub(r"\[\^[^\]]+\](?!:)", "", text)
    text = re.sub(r"[*_`]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _page(vault_dir: Path, page: str) -> Path | None:
    path = (vault_dir / page).resolve()
    root = vault_dir.resolve()
    if root not in path.parents or path.suffix not in (".md", ".mdx") or not path.is_file():
        return None
    return path


def locate(vault_dir: Path, page: str, quote: str, context: int = CONTEXT) -> dict:
    """{page, quote, match: exact | approx | missing, line, lines: [{n, text, hit}]}.

    `line` is the first line of the passage; `lines` adds `context` lines around it, `hit` marking the passage.
    """
    out = {"page": page, "quote": quote, "match": "missing", "line": None, "lines": []}
    path = _page(vault_dir, page)
    quote = quote.replace("\r\n", "\n").strip()
    if path is None or not quote:
        return out
    lines = vault.read(path).replace("\r\n", "\n").split("\n")
    text = "\n".join(lines)
    at = text.find(quote)
    if at >= 0:
        first = text.count("\n", 0, at)
        last = first + quote.count("\n")
        match = "exact"
    else:
        found = _closest(lines, quote)
        if found is None:
            return out
        first, last = found
        match = "approx"
    # Context: the nearest non-blank lines (Markdown paragraphs are separated by blank lines)
    before = [i for i in range(first - 1, -1, -1) if lines[i].strip()][:context]
    after = [i for i in range(last + 1, len(lines)) if lines[i].strip()][:context]
    shown = []
    for i in [*reversed(before), *range(first, last + 1), *after]:
        hit = first <= i <= last
        # A one-line exact quote is marked inside its line (a Markdown paragraph is one long line)
        mark = (at - (text.rfind("\n", 0, at) + 1), len(quote)) if match == "exact" and first == last == i else None
        shown.append({"n": i + 1, "hit": hit, **_clip(lines[i], mark if hit else None)})
    out.update(match=match, line=first + 1, lines=shown)
    return out


def _clip(line: str, mark: tuple[int, int] | None, width: int = CLIP) -> dict:
    """{text, parts}: a long line cut to `width` characters around the quote; `parts` = [before, quote, after]
    when the quote is marked inside the line (strings, not offsets: Python and JavaScript count characters
    differently)."""
    start, size = mark or (0, 0)
    lo, hi = 0, len(line)
    if len(line) > width:
        lo = max(0, min(start - max(0, width - size) // 2, len(line) - width, start)) if mark else 0
        hi = min(len(line), max(lo + width, start + size))
    head, tail = ("…" if lo else ""), ("…" if hi < len(line) else "")
    out = {"text": head + line[lo:hi] + tail, "parts": None}
    if mark:
        out["parts"] = [head + line[lo:start], line[start:start + size], line[start + size:hi] + tail]
    return out


def _closest(lines: list[str], quote: str) -> tuple[int, int] | None:
    """First and last line of the passage closest to the quote, if close enough.

    The quote is compared with each window of as many lines as it has, and inside a long line (a paragraph is one
    line in Markdown) with the stretch of the line it best matches.
    """
    q = _norm(quote)
    if not q:
        return None
    span = quote.count("\n") + 1
    best, where = 0.0, None
    for i in range(len(lines)):
        window = _norm(" ".join(lines[i:i + span]))
        if not window:
            continue
        if q in window:
            return i, min(len(lines), i + span) - 1
        ratio = _ratio(q, window)
        if ratio > best:
            best, where = ratio, (i, min(len(lines), i + span) - 1)
    return where if best >= APPROX else None


def _ratio(q: str, window: str) -> float:
    """Similarity of the quote with the window, or with the best stretch of a window longer than the quote."""
    matcher = SequenceMatcher(None, q, window, autojunk=False)
    if len(window) <= len(q) * 1.2:
        return matcher.ratio()
    if matcher.quick_ratio() * (len(q) + len(window)) / (2 * len(q)) < APPROX:
        return 0.0  # not enough shared characters for any stretch to match
    blocks = [b for b in matcher.get_matching_blocks() if b.size]
    if not blocks:
        return 0.0
    # Align the stretch on the longest shared block, then compare the quote with it
    b = max(blocks, key=lambda b: b.size)
    start = max(0, b.b - b.a)
    return SequenceMatcher(None, q, window[start:start + len(q)], autojunk=False).ratio()


def locate_all(vault_dir: Path, quotes: list[Quote]) -> list[dict]:
    return [locate(vault_dir, q.page, q.quote) for q in quotes]


def markdown(found: list[dict]) -> list[str]:
    """The excerpts as Markdown list items (report, pull request): the page lines, the passage marked with →."""
    out = []
    for e in found:
        if e["match"] == "missing":
            out.append(f"  - `{e['page']}`: excerpt not found in the page")
            continue
        flag = "" if e["match"] == "exact" else " (closest passage, not an exact quote)"
        out.append(f"  - `{e['page']}:{e['line']}`{flag}")
        out += [f"    > {'→ ' if l['hit'] else ''}{l['text']}" for l in e["lines"]]
    return out
