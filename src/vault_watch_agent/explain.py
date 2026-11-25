"""What the models explain to the editor, in the language of the page: the pauses of a run shown in another language
than English (asked by the user, 2026-11-25).

The checks write their explanations in English (the « why » of a correction, the cross-check's verdict, the reason of
a fix, a doubt, what the translator or the audits found): it is what the report and the pull request quote, tooling
being written in English. A page shown in French asks for them in French when it shows a pause: one call of the
translator's model for the lines not translated yet, at low effort; each line is kept, so a pause shown again, or the
same line elsewhere, costs nothing more. On a subscription the call is not billed; on the API it is in the journal
like any other (step `explain`).

    explain.lines(["The M4 Max row is a generation old."], "fr", llm, home)
    # -> ({"The M4 Max row is a generation old.": "La ligne du M4 Max date d'une génération."}, [usage])
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

from . import steps
from .guide import language_name
from .llm import LLM

MAX_LINES, MAX_CHARS = 60, 4000  # what one call translates at most (a pause rarely has more than 20 lines)

SYSTEM = """You translate, for the editor of a Markdown guide, the explanations an agent wrote in English about the
guide's pages: why a correction is proposed, a reviewer's verdict, a doubt, what a check found. Translate each line
into <<LANG>>, faithfully and plainly, in the same tone, without adding or dropping anything. Keep as they are: page
paths, quoted passages (between « », " " or ' ' and in the guide's own language), wiki links, footnote marks ([^1]),
URLs, code, versions, figures and names of products. Address the editor as the page does: informally, with « tu »
in French (« Cite une source », never « Citez »). Give one translation per id, in the same order."""


class Line(BaseModel):
    id: str
    text: str = Field(description="The line translated.")


class Lines(BaseModel):
    lines: list[Line]


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _store(home: Path, lang: str) -> Path:
    return home / "explained" / f"{lang}.json"


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def lines(texts: list[str], lang: str, llm: LLM | None, home: Path) -> tuple[dict[str, str], list[dict]]:
    """The lines in `lang`: {english: translated}, those kept from before and those translated now (one call, for
    MAX_LINES lines and MAX_CHARS characters at most: the rest is translated on the next ask). English, an empty
    line, or no model: nothing to translate."""
    wanted = list(dict.fromkeys(t for t in texts if t and t.strip()))
    if not wanted or lang in ("", "en") or not llm:
        return {}, []
    path = _store(home, lang)
    kept = _read(path)
    out = {t: kept[_key(t)] for t in wanted if _key(t) in kept}
    missing, size = [], 0
    for t in (t for t in wanted if t not in out):
        if len(missing) >= MAX_LINES or (missing and size + len(t) > MAX_CHARS):
            break
        missing.append(t)
        size += len(t)
    if not missing:
        return out, []
    listing = "\n\n".join(f"<line id=\"L{n}\">\n{t}\n</line>" for n, t in enumerate(missing, start=1))
    result, usage = llm.parse(system=SYSTEM.replace("<<LANG>>", language_name(lang)), prompt=listing, schema=Lines,
                              effort=steps.effort("explain"), node="explain")
    by_id = {x.id: x.text.strip() for x in result.lines if x.text.strip()}
    for n, t in enumerate(missing, start=1):
        if f"L{n}" in by_id:
            out[t] = kept[_key(t)] = by_id[f"L{n}"]
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(kept, ensure_ascii=False, indent=0), encoding="utf-8")
    try:
        os.replace(partial, path)
    except OSError:  # Windows: another request is writing it; the lines are kept the next time
        pass
    return out, [usage]
