"""The guide's watchlist follows the edits of a run (1.9.0).

A guide can keep a list of dated claims, each quoting the sentence of its page that states it (a version, a price, a
date), so that the claim can be found and re-checked when it is due. The agent edits pages: a correction rewrites a
sentence, a trim shortens it, an addition moves it. Until 1.9.0 the list kept quoting the old wording: the re-check
of the due claims sent that wording, and on 2026-11-26 four claims were reported as outdated when their pages were
already current. 173 of the 765 rows of the IA on-prem guide quoted wording their page no longer had (27/11/2026).

The list's format stays the guide's ([checks] watchlist_quotes, guide.Quotes): its script lists the rows whose quote
their page no longer has (`--json`) and rewrites the rows it is given (`--write`). The agent decides what to write:
after the corrections are applied, the rows that drift because of them (not those that drifted before) go to the
translation model, page by page, with the page as it reads now and the edits made to it; it requotes each row, or
removes it when its sentence is gone, or leaves it to the editor. Checked, Status and Recheck by are never touched:
they move only after a check on the web.

    before = drifted(worktree, spec)                   # before the edits
    ...                                                # the corrections applied
    done = follow(worktree, spec, chosen, before, llm, label="chore/watch-2026-11-30")
    done["rows"]  # [{page, file, line, action, old, new, value, note, ok}]
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from . import prompts, steps, vault
from .guide import Quotes
from .llm import LLM


class Row(BaseModel):
    row: int = Field(description="The number of the row, as given.")
    action: Literal["requote", "remove", "keep"] = Field(
        description="requote: the page still states the claim, worded otherwise; remove: the page no longer states it "
                    "at all; keep: you cannot tell, the editor will look.")
    claim: str = Field(default="", description="For requote: the new Claim cell. The passage copied verbatim from the "
                                               "page as it reads now, between « and », cut with … to stay short; the "
                                               "context the old cell had after its closing » kept.")
    value: str = Field(default="", description="For requote: the value as the page now states it (a version, a price, "
                                               "a date), in the old cell's form; empty when it did not change.")
    note: str = Field(default="", description="One short line in the guide's language: what changed in the sentence.")


class Rows(BaseModel):
    rows: list[Row]


FOLLOW = """<<GUIDE>> keeps a watchlist: rows of dated claims, each quoting between « and » the sentence of its page
that states the claim, so that it can be found with a text search and re-checked when it is due.
The pages below were just edited, and the rows listed under each one quote wording the page no longer has. For each
row decide:
- requote: the page still states the claim, reworded, shortened or with a new value. Give the new Claim cell: the
  passage copied character for character from the page as it reads now, between « and », cut with … where it is
  long (keep the part that carries the claim, a sentence at most); keep any context the old cell had after its
  closing ». Give `value` when the value the row tracks changed (« ≥ 0.34.0 », « 6 950 $ »), else leave it empty.
- remove: the page no longer states the claim anywhere (its sentence was deleted, not moved or reworded).
- keep: you cannot tell.
`note`: one short line in <<LANG>> saying what changed (« plancher 0.33.0 → 0.34.0 », « phrase raccourcie »).
Never write a quote that is not in the page, never correct a fact: the edits were reviewed, the rows only follow."""


def usable(worktree: Path, spec: Quotes | None) -> bool:
    return bool(spec) and (worktree / spec.script).is_file() and (worktree / spec.folder).is_dir()


def _node(worktree: Path, spec: Quotes, flag: str) -> subprocess.CompletedProcess:
    return subprocess.run(["node", spec.script, flag], cwd=worktree, capture_output=True, text=True,
                          encoding="utf-8", check=False)


def drifted(worktree: Path, spec: Quotes) -> list[dict]:
    """The rows whose quote their page no longer has, from the guide's script: [{file, line, page, claim, value,
    missing, …}]. RuntimeError when the script fails."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "quotes.json"
        done = _node(worktree, spec, f"--json={out}")
        if done.returncode != 0 or not out.is_file():
            raise RuntimeError(f"{spec.script} --json failed ({done.returncode}): {done.stderr.strip()[:300]}")
        return json.loads(out.read_text(encoding="utf-8")).get("drifted", [])


def _key(row: dict) -> tuple[str, str]:
    return row["file"], row["claim"]


def _prompt(worktree: Path, page: str, edits: list[dict], rows: list[dict]) -> str:
    listing = "\n".join(f"[{n}] Claim: {r['claim']}\n    Value: {r.get('value', '')}\n"
                        f"    No longer in the page: {' / '.join(r.get('missing') or [])}" for n, r in enumerate(rows, 1))
    changes = "\n".join(f"- « {c['current'].strip()} »\n  → « {c['proposed'].strip() or '(removed)'} »" for c in edits)
    return (f"Page `{page}`, as it reads now:\n\n{vault.read(worktree / page)}\n\n"
            f"The edits just made to it:\n{changes}\n\nThe rows:\n{listing}")


def follow(worktree: Path, spec: Quotes, chosen: list[dict], before: list[dict], llm: LLM, *, label: str,
           today: str) -> dict:
    """The rows the edits `chosen` made drift, requoted or removed by the guide's script after the model decided:
    {rows: [{page, file, line, action, old, new, value, note, ok}], usage: [...]}. `ok` is False for a row the script
    refused, or whose new quote its page still does not have (shown to the editor in the pull request)."""
    touched = {c["page"] for c in chosen}
    known = {_key(r) for r in before}
    fresh = [r for r in drifted(worktree, spec) if r["page"] in touched and _key(r) not in known]
    if not fresh:
        return {"rows": [], "usage": []}
    usage, decided, updates = [], [], []
    for page in sorted({r["page"] for r in fresh}):
        rows = [r for r in fresh if r["page"] == page]
        answer, u = llm.parse(system=prompts.fill(FOLLOW, worktree), prompt=_prompt(worktree, page,
                              [c for c in chosen if c["page"] == page], rows), schema=Rows,
                              effort=steps.effort("watchlist"), node=f"watchlist {page}")
        usage.append(u)
        by = {d.row: d for d in answer.rows}
        for n, r in enumerate(rows, 1):
            d = by.get(n)
            act = d.action if d and (d.action != "requote" or "«" in d.claim) else "keep"
            note = f"{label} {today} : {d.note}".strip(" :") if d and d.note else f"{label} {today}"
            entry = {"page": page, "file": r["file"], "line": r["line"], "action": act, "old": r["claim"],
                     "new": d.claim.strip() if act == "requote" and d else "", "value": (d.value.strip() if d else ""),
                     "note": note, "ok": act != "keep"}
            decided.append(entry)
            if act == "requote":
                updates.append({"file": r["file"], "line": r["line"], "claim": r["claim"], "new_claim": entry["new"],
                                **({"new_value": entry["value"]} if entry["value"] else {}), "note": note})
            elif act == "remove":
                updates.append({"file": r["file"], "line": r["line"], "claim": r["claim"], "remove": True})
    if updates:
        with tempfile.TemporaryDirectory() as tmp:
            given = Path(tmp) / "updates.json"
            given.write_text(json.dumps({"updates": updates}, ensure_ascii=False), encoding="utf-8")
            done = _node(worktree, spec, f"--write={given}")
        try:
            refused = {(x["file"], x["line"]) for x in json.loads(done.stdout or "{}").get("refused", [])}
        except json.JSONDecodeError as e:
            raise RuntimeError(f"{spec.script} --write: {done.stderr.strip()[:300] or e}") from e
        still = {r["claim"] for r in drifted(worktree, spec) if r["page"] in touched}
        for e in decided:
            written = re.sub(r"(?<!\\)\|", r"\\|", " ".join(e["new"].split()))  # as the script writes the cell
            if (e["file"], e["line"]) in refused or (e["action"] == "requote" and written in still):
                e["ok"] = False
    return {"rows": decided, "usage": usage}
