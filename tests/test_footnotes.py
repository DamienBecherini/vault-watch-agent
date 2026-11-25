"""Footnotes left without a sentence citing them (asked by the user, 2026-11-25: [^22] and [^23] of the IA guide's
security page stayed after the compaction of 2026-11-20, two groups having each removed one citation): removed at
apply with their last citation, whatever the run; and the broken notes of the changed pages said before publishing."""

import subprocess
from pathlib import Path

from test_graph import setup  # noqa: F401  (fixture: throwaway vault, fake model, watch file)

from vault_watch_agent import graph_publish, graph_review, vault

PAGE = """---
title: Notes
last_modified: "2026-11-01"
---

# Notes

LiteLLM a eu une faille critique[^1] en juin.

Une seconde faille[^1] a suivi en septembre[^2].

Un exemple de code : `re.compile(r"[^a-z]")` et

```
[^x]: pas une note
```

[^1]: BerriAI, avis GHSA-1, 2026.
    suite indentée de la note 1.

[^2]: BerriAI, avis GHSA-2, 2026.

[^3]: Une note que rien n'appelait déjà.
"""


def test_the_broken_notes_of_a_page_are_found_code_aside():
    assert vault.footnote_problems(PAGE) == {"never_cited": ["3"], "undefined": [], "twice": []}
    broken = PAGE + "\nVoir aussi[^4].\n\n[^2]: doublon.\n"
    assert vault.footnote_problems(broken) == {"never_cited": ["3"], "undefined": ["4"], "twice": ["2"]}


def test_a_note_goes_with_its_last_citation_only():
    # One citation of [^1] removed: another sentence still cites it, nothing goes
    one = PAGE.replace("LiteLLM a eu une faille critique[^1] en juin.\n\n", "")
    assert vault.drop_orphan_notes(PAGE, one) == (one, [])
    # Both removed (as two groups would): its definition goes, with its indented line and the blank line after it;
    # [^3], already uncited before, is left as it was
    both = one.replace("Une seconde faille[^1] a suivi en septembre[^2].", "Une seconde faille a suivi en septembre[^2].")
    kept, gone = vault.drop_orphan_notes(PAGE, both)
    assert gone == ["1"] and "[^1]:" not in kept and "suite indentée" not in kept
    assert kept.endswith("""```

[^2]: BerriAI, avis GHSA-2, 2026.

[^3]: Une note que rien n'appelait déjà.
""")
    crlf, gone = vault.drop_orphan_notes(PAGE.replace("\n", "\r\n"), both.replace("\n", "\r\n"))
    assert gone == ["1"] and crlf == kept.replace("\n", "\r\n")


def test_apply_removes_a_note_two_groups_orphan_together(setup):  # noqa: F811
    deps, _, _ = setup
    (deps.vault / "03-stack" / "notes.md").write_text(PAGE, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=deps.vault, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "notes"], cwd=deps.vault, check=True, capture_output=True)
    base = {"page": "03-stack/notes.md", "check": "ok", "severity": "Minor", "rationale": "r", "source_url": "x"}
    corrections = [
        {**base, "id": "C1", "group": "C1", "current": "LiteLLM a eu une faille critique[^1] en juin.", "proposed": ""},
        {**base, "id": "C2", "group": "C2", "current": "Une seconde faille[^1] a suivi", "proposed": "Une seconde faille a suivi"},
    ]
    state = {"corrections": corrections, "accepted": ["C1", "C2"], "branch_name": "fix/notes", "title": "fix: notes"}
    out = graph_review.apply(deps, state)  # type: ignore[arg-type]
    page = (Path(out["worktree"]) / "03-stack" / "notes.md").read_text(encoding="utf-8")
    assert out["notes_removed"] == ["03-stack/notes.md [^1]"] and "[^1]" not in page and "[^2]: BerriAI" in page
    # Before publishing: [^3] (never cited, already before this run) is said; the notes removed are not
    said = graph_publish.footnote_problems(deps, Path(out["worktree"]))
    assert said == ["03-stack/notes.md: never cited [^3]"]
