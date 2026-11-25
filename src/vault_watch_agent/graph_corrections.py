"""The free checks of the corrections, before the review and after a retouch: an edit that changes nothing, a footnote
lost, two edits of the same passage; and the editor's retouches at the review."""

from __future__ import annotations

import re
from pathlib import Path

from . import compact, news, vault

FOOTNOTE_DEF = re.compile(r"^\[\^([^\]]+)\]:", re.M)


def mark_unsafe(corrections: list[dict], trims: bool = False) -> None:
    """Refuse an edit that changes nothing, or that deletes a footnote definition its group does not put back
    elsewhere (a "move" done as a deletion left a dangling [^11] in fix-2026-11-08-6). `trims`: a compaction run
    removes definitions on purpose; what it must not do is checked on the page itself (compact.mark_dangling)."""
    added: dict[str, set[str]] = {}
    for c in corrections:
        added.setdefault(c.get("group") or c["id"], set()).update(FOOTNOTE_DEF.findall(c["proposed"]))
    for c in corrections:
        if c["check"] != "ok":
            continue
        if c["current"].strip() == c["proposed"].strip():
            c["check"] = "no change"
            continue
        lost = set() if trims else set(FOOTNOTE_DEF.findall(c["current"])) - added[c.get("group") or c["id"]]
        if lost:
            c["check"] = "drops footnote " + ", ".join(f"[^{n}]" for n in sorted(lost))


def mark_conflicts(vault_dir: Path, corrections: list[dict], trims: bool = False) -> None:
    """Two corrections that edit overlapping text of a page cannot both apply: the later one is refused. Except two
    that only write after the same passage (`news.appends`: each still finds it once the other is applied)."""
    mark_unsafe(corrections, trims)
    if trims:
        compact.mark_dangling(vault_dir, corrections)
    spans: dict[str, list[tuple[int, int, str, bool]]] = {}  # page -> (start, end, id, appends) of the edits kept
    for c in corrections:
        if c["check"] != "ok":
            continue
        text = vault.read(vault_dir / c["page"]).replace("\r\n", "\n")
        start = text.find(c["current"].replace("\r\n", "\n"))
        end = start + len(c["current"])
        after = news.appends(c)
        clash = next((cid for s, e, cid, also in spans.get(c["page"], [])
                      if start < e and s < end and not (after and also and (s, e) == (start, end))), None)
        if clash:
            c["check"] = f"conflict with {clash}"
        else:
            spans.setdefault(c["page"], []).append((start, end, c["id"], after))


RETOUCHABLE = ("ok", "no change")  # and « drops footnote … »: what the text proposed decides, not where it applies


def retouchable(c: dict) -> bool:
    """A correction whose text the editor can retouch: one that applies, or that fails on its new text only. A quote
    not found, a conflict, a rejection by the cross-check are about where it applies or whether: no text mends them."""
    return c["check"] in RETOUCHABLE or c["check"].startswith("drops footnote")


def retouched(vault_dir: Path, corrections: list[dict], edits: dict[str, str], mode: str | None = None) -> list[dict]:
    """The corrections with the texts the editor retouched at the review. Each retouched one keeps the model's text
    (`proposed_model`, its first one), takes the editor's as `proposed`, and goes through the free checks again: the
    quote still found once (it is unchanged), a text that changes something, the footnotes it removes put back
    elsewhere in its group (for trims, the notes left without a sentence), a version none of its footnotes mentions.
    The others are left as they were. A text identical to the proposal is no retouch."""
    out = [dict(c) for c in corrections]
    changed = []
    for c in out:
        text = (edits.get(c["id"]) or "").replace("\r\n", "\n")
        if c["id"] not in edits or not retouchable(c) or text == c["proposed"]:
            continue
        c.setdefault("proposed_model", c["proposed"])
        c["proposed"], c["edited"] = text, True
        c["check"] = vault.check(vault_dir, c["page"], c["current"])
        changed.append(c)
    if not changed:
        return out
    mark_conflicts(vault_dir, out, mode == "compact")
    if mode not in ("compact", "translation"):
        unsourced = vault.unsourced_versions(vault_dir, out)
        for c in changed:
            c["warning"] = unsourced.get(c["id"], "")
    return out


def note_retouches(report: str, corrections: list[dict]) -> None:
    """The report of the run, written before the review, gets the corrections retouched there: the model's text and
    the editor's, side by side."""
    done = [c for c in corrections if c.get("edited")]
    if not report or not done or not Path(report).is_file():
        return
    lines = ["", "## Retouched at the review", ""]
    for c in done:
        lines += [f"### {c['id']} `{c['page']}` ({c['check']})", "", "Proposed:", "",
                  *[f"> {line}" for line in c["proposed_model"].splitlines()], "", "Retouched:", "",
                  *[f"> {line}" for line in c["proposed"].splitlines()], ""]
    with open(report, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))
