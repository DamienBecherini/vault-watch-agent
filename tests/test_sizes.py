"""What the guide weighs: budgets from the manifest, sections, footnotes, growth read from Git. No model."""

import os
import subprocess
from pathlib import Path

import pytest

from vault_watch_agent import sizes, vault
from vault_watch_agent.guide import GuideError, parse

MANIFEST = """schema = 1
[guide]
name = "Test"
[content]
language = "fr"
mirrors = { en = "en/" }
[budget]
page_kb = 1
[budget.pages]
"00-lexique/**" = 2
"""

LONG = """---
title: Sécurité
---

# Sécurité

Intro.

## Ports

""" + "Le port 8000 reste fermé. " * 30 + """

```bash
## not a heading: a comment in a code block
```

## Références

[^1]: Source un, https://example.org/1.
[^2]: Source deux, https://example.org/2.
"""


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def git(*args, cwd: Path, when: str | None = None) -> None:
    env = {**os.environ, **({"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when} if when else {})}
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


@pytest.fixture
def guide(tmp_path: Path) -> Path:
    root = tmp_path / "guide"
    write(root, "vault-watch.toml", MANIFEST)
    write(root, "06-ops/security.md", "# Sécurité\n\nCourt.\n")
    write(root, "00-lexique/port.md", "# Port\n\n" + "Définition. " * 120 + "\n")
    write(root, "en/06-ops/security.md", "# Security\n\nShort.\n")
    git("init", "-q", "-b", "main", cwd=root)
    git("config", "user.name", "t", cwd=root)
    git("config", "user.email", "t@t", cwd=root)
    git("add", ".", cwd=root)
    git("commit", "-qm", "old", cwd=root, when="2026-01-01T12:00:00")
    write(root, "06-ops/security.md", LONG)
    write(root, "06-ops/new.md", "# Nouveau\n\nPage ajoutée.\n")
    git("add", ".", cwd=root)
    git("commit", "-qm", "now", cwd=root, when="2026-05-20T12:00:00")
    return root


def test_a_page_has_the_budget_of_the_first_pattern_that_matches(guide):
    g = vault.guide_of(guide)
    assert (g.page_kb, g.page_budgets) == (1, (("00-lexique/**", 2),))
    assert sizes.budget_of(g, "00-lexique/port.md") == 2 and sizes.budget_of(g, "06-ops/security.md") == 1


def test_the_report_names_the_pages_over_their_budget_and_where_the_weight_is(guide):
    rep = sizes.report(guide, today="2026-06-01")
    rows = {r["page"]: r for r in rep["pages"]}
    assert set(rows) == {"06-ops/security.md", "06-ops/new.md", "00-lexique/port.md"}  # the mirror is not counted
    heavy = rows["06-ops/security.md"]
    assert heavy["over"] and not rows["00-lexique/port.md"]["over"]  # 1.4 KB for a budget of 2
    assert [s["title"] for s in heavy["sections"]] == ["Ports", "Références", "Sécurité"]  # heaviest first
    assert heavy["footnotes"]["count"] == 2
    assert rep["over"] == 1 and rep["pages"][0]["page"] in ("00-lexique/port.md", "06-ops/security.md")
    assert [c["chapter"] for c in rep["chapters"]] == ["00-lexique", "06-ops"]
    assert "1 page(s) over their budget: 06-ops/security.md" in sizes.summary(rep)
    assert "over" in sizes.table(rep) and "## Ports" in sizes.table(rep)


def test_without_a_ceiling_a_page_is_flagged_when_it_grew_much(tmp_path):
    """No ceiling by default: how long a page should be depends on its subject. What is flagged is a page that
    gained much against what it weighed, shown with its new size."""
    root = tmp_path / "guide"
    write(root, "vault-watch.toml", 'schema = 1\n[guide]\nname = "T"\n[content]\nlanguage = "fr"\nreadonly = ["projet/**"]\n')
    para = "Une phrase de contenu, assez longue pour peser. " * 20  # about 1 KB
    for name, n in (("long.md", 40), ("small.md", 1), ("steady.md", 30), ("projet/log.md", 2)):
        write(root, name, f"# {name}\n\n" + para * n)
    git("init", "-q", "-b", "main", cwd=root)
    git("config", "user.name", "t", cwd=root)
    git("config", "user.email", "t@t", cwd=root)
    git("add", ".", cwd=root)
    git("commit", "-qm", "old", cwd=root, when="2026-01-01T12:00:00")
    for name, n in (("long.md", 46), ("small.md", 4), ("steady.md", 31), ("projet/log.md", 20)):
        write(root, name, f"# {name}\n\n" + para * n)
    write(root, "tiny.md", "# tiny\n\n" + para)  # new
    rep = sizes.report(root, today="2026-04-15")
    rows = {r["page"]: r for r in rep["pages"]}
    assert vault.guide_of(root).page_kb == 0 and rep["over"] == 0 and all(r["budget"] == 0 for r in rep["pages"])
    # +6 KB (over the 5 KB); +3 KB on 1 KB (over 25 % and 2 KB); +1 KB on 30 (neither); read-only and new: never
    assert {p: r["grew"] for p, r in rows.items()} == {"long.md": True, "small.md": True, "steady.md": False,
                                                       "projet/log.md": False, "tiny.md": False}
    assert rep["grew"] == 2 and [r["page"] for r in sizes.flagged(rep)] == ["long.md", "small.md"]  # the largest gain first
    line = sizes.summary(rep)
    assert "2 page(s) grew much in 90 days: long.md 43 KB (+5.6 KB, +15%), small.md 3.8 KB (+2.8 KB, +296%)" in line and "budget" not in line
    table = sizes.table(rep)
    assert table.splitlines()[2].startswith("grew    43 KB") and "new  tiny.md" in table and " / " not in table
    assert "budget" not in sizes.describe(rows["long.md"]) and "KB 90 days ago" in sizes.describe(rows["long.md"])
    assert sizes.gained(rows["tiny.md"]) == "new" and sizes.gained(rows["steady.md"]).startswith("+0.9 KB, +3%")
    # the thresholds are the guide's
    write(root, "vault-watch.toml", 'schema = 1\n[guide]\nname = "T"\n[content]\nlanguage = "fr"\nreadonly = ["projet/**"]\n[budget]\ngrowth_kb = 50\ngrowth_percent = 400\n')
    assert sizes.report(root, today="2026-04-15")["grew"] == 0


def test_growth_is_read_from_git(guide):
    rep = sizes.report(guide, days=90, today="2026-06-01")  # 90 days before: 3 March, the commit of January
    g, rows = rep["growth"], {r["page"]: r for r in rep["pages"]}
    assert g["date"] == "2026-03-03" and g["new_pages"] == 1
    assert rows["06-ops/new.md"]["before"] is None and rows["06-ops/security.md"]["before"] == len("# Sécurité\n\nCourt.\n".encode())
    assert g["added"] == rep["total"] - g["bytes"] > 0
    assert "in 90 days" in sizes.summary(rep)
    assert sizes.report(guide, today="2025-06-01")["growth"] is None  # no commit that old


def test_a_guide_outside_git_has_sizes_and_no_growth(tmp_path):
    write(tmp_path, "vault-watch.toml", MANIFEST)
    write(tmp_path, "a.md", "# A\n\nTexte.\n")
    rep = sizes.report(tmp_path)
    assert rep["growth"] is None and rep["over"] == rep["grew"] == 0
    assert sizes.summary(rep).endswith("no page grew much (no earlier commit to compare with)")


def test_a_heading_in_a_code_block_is_not_a_section():
    found = sizes.sections("# T\n\n```\n## no\n```\n\n## Yes\n\nx\n")
    assert [s["title"] for s in found] == ["T", "Yes"]


@pytest.mark.parametrize("budget, message", [
    ({"page_kb": 0}, "page_kb"),
    ({"page_kb": "30"}, "page_kb"),
    ({"pages": {"a/**": "big"}}, "[budget.pages]"),
    ({"pages": ["a/**"]}, "[budget.pages]"),
])
def test_a_wrong_budget_is_refused_with_its_key(tmp_path, budget, message):
    with pytest.raises(GuideError, match=message.replace("[", r"\[").replace("]", r"\]")):
        parse({"guide": {"name": "T"}, "content": {"language": "fr"}, "budget": budget}, tmp_path)


def test_doctor_warns_about_the_pages_over_their_budget(guide):
    from vault_watch_agent import onboard

    line = next(l for l in onboard.diagnose(guide, guide / ".home", gh_check=False) if l.label == "size")
    assert line.status == "warn" and "06-ops/security.md" in line.detail
