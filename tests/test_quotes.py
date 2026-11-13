"""The passage a finding is about is looked up in the page: exact, else the closest passage, else not found."""

from pathlib import Path

from vault_watch_agent import quotes
from vault_watch_agent.graph import pr_body

PAGE = """---
title: Moteurs
---

Introduction.

vLLM 0.31 est la version **minimale** recommandée[^1], d’après l’éditeur.

| Moteur | Version |
| :-- | :-- |
| vLLM | 0.31 |

[^1]: vLLM, notes de version 0.31.
"""


def vault(tmp_path: Path) -> Path:
    (tmp_path / "03-stack").mkdir()
    (tmp_path / "03-stack" / "engines.md").write_text(PAGE, encoding="utf-8")
    (tmp_path / "secret.txt").write_text("not a page", encoding="utf-8")
    return tmp_path


def test_an_exact_quote_is_marked_in_its_line_with_the_nearest_line_around(tmp_path):
    e = quotes.locate(vault(tmp_path), "03-stack/engines.md", "version **minimale** recommandée")
    assert e["match"] == "exact" and e["line"] == 7
    assert [l["n"] for l in e["lines"]] == [5, 7, 9]  # the nearest non-blank lines
    hit = next(l for l in e["lines"] if l["hit"])
    assert hit["parts"] == ["vLLM 0.31 est la ", "version **minimale** recommandée", "[^1], d’après l’éditeur."]


def test_a_quote_the_model_retyped_finds_the_page_text(tmp_path):
    # Straight apostrophe, no Markdown emphasis: the page's own line is shown, flagged as approximate
    e = quotes.locate(vault(tmp_path), "03-stack/engines.md",
                      "vLLM 0.31 est la version minimale recommandée, d'après l'éditeur.")
    assert e["match"] == "approx" and e["line"] == 7
    assert next(l for l in e["lines"] if l["hit"])["text"].startswith("vLLM 0.31 est la version **minimale**")


def test_a_table_row_retyped_without_its_wiki_link(tmp_path):
    (tmp_path / "p.md").write_text("| PME, 5–20 utilisateurs | [[04-blueprints/b\\|Blueprint B]] + Open WebUI |\n",
                                   encoding="utf-8")
    assert quotes.locate(tmp_path, "p.md", "| PME, 5-20 utilisateurs | Blueprint B + Open WebUI |")["match"] == "approx"


def test_a_table_row_spanning_quote_and_a_typo(tmp_path):
    e = quotes.locate(vault(tmp_path), "03-stack/engines.md", "| vLLM | 0.32 |")
    assert e["match"] == "approx" and e["line"] == 11


def test_an_invented_quote_is_not_found(tmp_path):
    v = vault(tmp_path)
    assert quotes.locate(v, "03-stack/engines.md", "SGLang est plus rapide que tout le reste.")["match"] == "missing"
    assert quotes.locate(v, "03-stack/absent.md", "Introduction.")["match"] == "missing"
    assert quotes.locate(v, "../outside.md", "Introduction.")["match"] == "missing"
    assert quotes.locate(v, "secret.txt", "not a page")["match"] == "missing"  # pages only


def test_a_long_line_is_cut_around_the_quote(tmp_path):
    (tmp_path / "long.md").write_text("a" * 1000 + " LA PHRASE " + "b" * 1000 + "\n", encoding="utf-8")
    e = quotes.locate(tmp_path, "long.md", "LA PHRASE")
    before, quote, after = e["lines"][0]["parts"]
    assert quote == "LA PHRASE" and before.startswith("…") and after.endswith("…")
    assert len(before) + len(quote) + len(after) < 400


def test_excerpts_reach_the_pull_request_of_a_fix_run(tmp_path):
    found = [quotes.locate(vault(tmp_path), "03-stack/engines.md", "| vLLM | 0.31 |"),
             quotes.locate(tmp_path, "03-stack/engines.md", "nowhere")]
    state = {"source": "errors reported", "issue": None, "audit_ok": True, "applied": ["C1"],
             "items": [{"id": "F1", "domain": "fix", "title": "table and text disagree", "excerpts": found},
                       {"id": "F2", "domain": "fix", "title": "not applied", "excerpts": []}],
             "corrections": [{"id": "C1", "item_id": "F1", "item_ids": ["F1"], "severity": "Minor",
                              "page": "03-stack/engines.md", "rationale": "r", "source_url": "u"}]}
    body = pr_body(state)
    assert "- F1: table and text disagree" in body and "F2" not in body
    assert "`03-stack/engines.md:11`" in body and "    > → | vLLM | 0.31 |" in body
    assert "excerpt not found in the page" in body
