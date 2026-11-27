"""The guide's watchlist follows the edits of a run (watchlist.py), through the IA on-prem guide's own script
(tests/guide_scripts: a copy of its scripts/audit-watchlist-quotes.mjs, the contract the agent relies on)."""

import shutil
from pathlib import Path

import pytest

from vault_watch_agent import graph_text, vault, watchlist
from vault_watch_agent.guide import Quotes, parse

SCRIPTS = Path(__file__).resolve().parent / "guide_scripts"
FOLDER = ".agents/vault-maintenance/watchlist"
SPEC = Quotes("scripts/audit-watchlist-quotes.mjs", FOLDER)

PAGE = """---
title: Sécurité
last_modified: "2026-11-01"
---

Au T4 2026, déployez vLLM ≥ 0.33.0 (publiée le 2 novembre 2026).

Les pilotes CUDA 12 restent pris en charge jusqu'en décembre 2026.

Open WebUI | 3000 | toutes interfaces
"""

HEAD = ("| Page | Claim | Type | Value in page | Source | Source date | Checked | Status | Note | Recheck by |\n"
        "| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |\n")
ROWS = [
    "| `p.md` | « déployez vLLM ≥ 0.33.0 (publiée le 2 novembre 2026) » | version | ≥ 0.33.0 | [^1] | 2026-11-02 "
    "| 2026-11-09 | current | plancher | 2026-12-01 |",
    "| `p.md` | « Ollama ≥ 0.31.2 » | version | ≥ 0.31.2 | [^2] | 2026-09-29 | 2026-10-10 | current | déjà ancien | 2026-11-10 |",
    "| `p.md` | « Les pilotes CUDA 12 restent pris en charge jusqu'en décembre 2026 » | availability | CUDA 12 | [^3] | 2026-10 | 2026-10-10 | current | | |",
    "| `p.md` | « Open WebUI \\| 3000 \\| toutes interfaces » | spec | 3000 | [^4] | 2026-10 | 2026-10-09 | current | port | |",
]


class FakeLLM:
    def __init__(self, rows):
        self.rows, self.asked = rows, []

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
        self.asked.append({"system": system, "prompt": prompt, "effort": effort, "node": node})
        return schema(rows=self.rows), {"node": node, "model": "fake", "cost_usd": 0.01}


@pytest.fixture
def guide(tmp_path: Path) -> Path:
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    root = tmp_path / "guide"
    shutil.copytree(SCRIPTS, root / "scripts")
    (root / FOLDER).mkdir(parents=True)
    (root / FOLDER / "06.md").write_text("# Watchlist\n\n" + HEAD + "\n".join(ROWS) + "\n", encoding="utf-8")
    (root / "p.md").write_text(PAGE, encoding="utf-8")
    (root / "vault-watch.toml").write_text('[guide]\nname = "G"\n[content]\nlanguage = "fr"\n', encoding="utf-8")
    return root


def edit(root: Path, current: str, proposed: str) -> dict:
    text = vault.read(root / "p.md")
    vault.write(root / "p.md", text.replace(current, proposed))
    return {"page": "p.md", "current": current, "proposed": proposed}


def rows_of(root: Path) -> list[str]:
    return [line for line in vault.read(root / FOLDER / "06.md").splitlines() if line.startswith("| `")]


def test_the_script_lists_the_rows_whose_quote_the_page_no_longer_has(guide):
    drifted = watchlist.drifted(guide, SPEC)
    assert [(r["line"], r["claim"]) for r in drifted] == [(6, "« Ollama ≥ 0.31.2 »")]
    assert drifted[0]["value"] == "≥ 0.31.2" and drifted[0]["page"] == "p.md"


def test_the_rows_the_edits_made_drift_are_requoted_or_removed_the_others_left(guide):
    before = watchlist.drifted(guide, SPEC)
    chosen = [edit(guide, "déployez vLLM ≥ 0.33.0 (publiée le 2 novembre 2026)",
                   "déployez vLLM ≥ 0.34.0 (publiée le 16 novembre 2026)"),
              edit(guide, "Les pilotes CUDA 12 restent pris en charge jusqu'en décembre 2026.", "")]
    llm = FakeLLM([
        {"row": 1, "action": "requote", "claim": "« déployez vLLM ≥ 0.34.0 (publiée le 16 novembre 2026) »",
         "value": "≥ 0.34.0", "note": "plancher 0.33.0 → 0.34.0"},
        {"row": 2, "action": "remove", "note": "phrase retirée"},
    ])
    done = watchlist.follow(guide, SPEC, chosen, before, llm, label="chore/watch-2026-11-30", today="2026-11-30")
    assert [(r["action"], r["ok"]) for r in done["rows"]] == [("requote", True), ("remove", True)]
    assert done["usage"] == [{"node": "watchlist p.md", "model": "fake", "cost_usd": 0.01}]
    assert llm.asked[0]["effort"] == "low" and "≥ 0.34.0" in llm.asked[0]["prompt"]
    rows = rows_of(guide)
    assert len(rows) == 3  # the CUDA 12 row is gone with its sentence
    assert rows[0].startswith("| `p.md` | « déployez vLLM ≥ 0.34.0 (publiée le 16 novembre 2026) » | version | ≥ 0.34.0 |")
    # Checked, Status and Recheck by stay: they move only after a check on the web
    assert "| 2026-11-09 | current | plancher ; chore/watch-2026-11-30 2026-11-30 : plancher 0.33.0 → 0.34.0 | 2026-12-01 |" in rows[0]
    assert rows[1] == ROWS[1] and rows[2] == ROWS[3]  # drifting before the run, and untouched: not this run's
    assert [r["claim"] for r in watchlist.drifted(guide, SPEC)] == ["« Ollama ≥ 0.31.2 »"]


def test_a_quote_the_page_does_not_have_is_left_to_the_editor(guide):
    before = watchlist.drifted(guide, SPEC)
    chosen = [edit(guide, "vLLM ≥ 0.33.0", "vLLM ≥ 0.34.0")]
    llm = FakeLLM([{"row": 1, "action": "requote", "claim": "« déployez vLLM 0.34 dès maintenant »", "note": "x"}])
    done = watchlist.follow(guide, SPEC, chosen, before, llm, label="b", today="2026-11-30")
    assert [(r["action"], r["ok"]) for r in done["rows"]] == [("requote", False)]
    body = graph_text.watchlist_lines({"watchlist": done["rows"]})
    assert "Watchlist: 0 row(s) follow" in body and "to requote by hand (1)" in body and "line 5" in body


def test_a_claim_with_a_pipe_is_written_escaped(guide):
    before = watchlist.drifted(guide, SPEC)
    chosen = [edit(guide, "Open WebUI | 3000 |", "Open WebUI | 8080 |")]
    llm = FakeLLM([{"row": 1, "action": "requote", "claim": "« Open WebUI | 8080 | toutes interfaces »",
                    "value": "8080", "note": "port"}])
    done = watchlist.follow(guide, SPEC, chosen, before, llm, label="b", today="2026-11-30")
    assert done["rows"][0]["ok"]
    assert "| « Open WebUI \\| 8080 \\| toutes interfaces » | spec | 8080 |" in rows_of(guide)[3]


def test_no_drift_no_call(guide):
    before = watchlist.drifted(guide, SPEC)
    chosen = [edit(guide, "Sécurité", "Sécurité locale")]
    llm = FakeLLM([])
    assert watchlist.follow(guide, SPEC, chosen, before, llm, label="b", today="2026-11-30") == {"rows": [], "usage": []}
    assert llm.asked == []


def test_a_keep_or_a_requote_without_a_quote_is_left_to_the_editor(guide):
    before = watchlist.drifted(guide, SPEC)
    chosen = [edit(guide, "vLLM ≥ 0.33.0", "vLLM ≥ 0.34.0")]
    llm = FakeLLM([{"row": 1, "action": "requote", "claim": "déployez vLLM ≥ 0.34.0"}])
    done = watchlist.follow(guide, SPEC, chosen, before, llm, label="b", today="2026-11-30")
    assert [(r["action"], r["ok"]) for r in done["rows"]] == [("keep", False)]
    assert rows_of(guide)[0] == ROWS[0]  # nothing written


def test_the_manifest_declares_the_script_and_its_folder(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "q.mjs").write_text("", encoding="utf-8")
    base = {"guide": {"name": "G"}, "content": {"language": "en"}}
    g = parse({**base, "checks": {"watchlist_quotes": {"script": "scripts/q.mjs", "folder": "wl/"}}}, tmp_path)
    assert (g.watchlist_quotes.script, g.watchlist_quotes.folder) == ("scripts/q.mjs", "wl")
    assert g.summary()["checks"]["watchlist_quotes"] == "scripts/q.mjs"
    with pytest.raises(Exception, match="a table with script and folder"):
        parse({**base, "checks": {"watchlist_quotes": {"script": "scripts/q.mjs"}}}, tmp_path)
