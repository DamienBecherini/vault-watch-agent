"""The mirrors follow the diff of the source pages (mirrors.py): the passages that changed, a paragraph, a table row or
a list line at a time; the pages ahead of their mirror, from git."""

import subprocess
from pathlib import Path

import pytest

from vault_watch_agent import mirrors

MANIFEST = """schema = 1
[guide]
name = "Test"
[content]
language = "fr"
mirrors = { en = "en/" }
modified_field = "last_modified"
"""

PAGE = """---
title: Moteurs
last_modified: "2026-06-10"
---

vLLM 0.31 est la version minimale.

Ollama reste le plus simple.

| Outil | Version |
| :-- | :-- |
| vLLM | 0.31 |
| Ollama | 0.6 |

- un point
- un autre point
"""

PAGE_EN = PAGE.replace("Moteurs", "Engines").replace("est la version minimale", "is the minimum version") \
    .replace("Ollama reste le plus simple", "Ollama remains the simplest").replace("un point", "a point") \
    .replace("un autre point", "another point")


def test_blocks_keep_a_fenced_code_block_whole():
    text = "Avant.\n\n```bash\nvllm serve\n\n--port 8000\n```\n\nAprès.\n"
    assert mirrors.blocks(text) == ["Avant.", "```bash\nvllm serve\n\n--port 8000\n```", "Après."]


def test_a_paragraph_replaced_added_and_removed():
    old = "Un.\n\nDeux.\n\nTrois.\n"
    assert mirrors.changes(old, "Un.\n\nDeux bis.\n\nTrois.\n") == [("Deux.", "Deux bis.")]
    assert mirrors.changes(old, "Un.\n\nDeux.\n\nNouveau.\n\nTrois.\n") == [("Deux.", "Deux.\n\nNouveau.")]  # after the block before
    assert mirrors.changes(old, "Zéro.\n\nUn.\n\nDeux.\n\nTrois.\n") == [("Un.", "Zéro.\n\nUn.")]  # at the top: before the first
    assert mirrors.changes(old, "Un.\n\nTrois.\n") == [("Deux.", "")]  # removed: an empty new text
    assert mirrors.changes(old, old) == []


def test_a_table_row_and_a_list_line_are_compared_line_by_line():
    new = PAGE.replace("| vLLM | 0.31 |", "| vLLM | 0.33 |").replace("- un autre point", "- un autre point\n- un troisième")
    assert mirrors.changes(PAGE, new) == [("| vLLM | 0.31 |", "| vLLM | 0.33 |"),
                                         ("- un autre point", "- un autre point\n- un troisième")]


def sh(*cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def guide(tmp_path: Path) -> Path:
    root = tmp_path / "guide"
    (root / "03-stack").mkdir(parents=True)
    (root / "en" / "03-stack").mkdir(parents=True)
    (root / "vault-watch.toml").write_text(MANIFEST, encoding="utf-8")
    (root / "03-stack" / "engines.md").write_text(PAGE, encoding="utf-8")
    (root / "en" / "03-stack" / "engines.md").write_text(PAGE_EN, encoding="utf-8")
    sh("git", "init", "-q", "-b", "main", cwd=root)
    sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "add", ".", cwd=root)
    sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init", cwd=root)
    return root


def commit(root: Path, message: str):
    sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", message, cwd=root)


def test_the_source_pages_changed_and_their_edits_without_the_date(guide: Path):
    page = guide / "03-stack" / "engines.md"
    page.write_text(PAGE.replace("2026-06-10", "2026-11-21").replace("vLLM 0.31 est", "vLLM 0.33 est"), encoding="utf-8")
    (guide / "en" / "03-stack" / "engines.md").write_text(PAGE_EN.replace("0.31", "0.32"), encoding="utf-8")
    assert mirrors.changed_pages(guide, "HEAD") == ["03-stack/engines.md"]  # not the mirror
    assert mirrors.edits_of(guide, "03-stack/engines.md", "HEAD") == [
        ("vLLM 0.31 est la version minimale.", "vLLM 0.33 est la version minimale.")]  # the date line left to apply
    page.write_text(PAGE.replace("2026-06-10", "2026-11-21"), encoding="utf-8")
    assert mirrors.edits_of(guide, "03-stack/engines.md", "HEAD") == []  # a date alone is nothing to translate


def test_a_page_ahead_of_its_mirror_since_the_mirror_last_moved(guide: Path):
    assert mirrors.behind(guide, "en") == {}
    in_step = subprocess.run(["git", "rev-parse", "HEAD"], cwd=guide, capture_output=True, text=True).stdout.strip()
    page = guide / "03-stack" / "engines.md"
    page.write_text(PAGE.replace("2026-06-10", "2026-07-01"), encoding="utf-8")
    commit(guide, "a date alone")
    assert mirrors.behind(guide, "en") == {}
    page.write_text(PAGE.replace("Ollama reste le plus simple.", "Ollama reste le plus simple pour démarrer."), encoding="utf-8")
    commit(guide, "edited by hand")
    assert mirrors.behind(guide, "en") == {"03-stack/engines.md": in_step}
    assert mirrors.edits_of_commit(guide, "03-stack/engines.md", in_step) == [
        ("Ollama reste le plus simple.", "Ollama reste le plus simple pour démarrer.")]
    mirror = guide / "en" / "03-stack" / "engines.md"
    mirror.write_text(PAGE_EN.replace("Ollama remains the simplest.", "Ollama remains the simplest to start with."),
                      encoding="utf-8")
    commit(guide, "the mirror follows")
    assert mirrors.behind(guide, "en") == {}  # in step again
    assert mirrors.behind(guide, "de") == {}  # no such mirror


# -- « Sync the languages » through the server, on the guide of test_graph ------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from test_graph import setup  # noqa: E402,F401  (fixture: throwaway guide with an English mirror)
from vault_watch_agent import vault  # noqa: E402
from vault_watch_agent.state import MirrorEdit, MirrorResult  # noqa: E402
from vault_watch_agent.web import Settings, create_app  # noqa: E402

ACT = {"X-Vault-Watch": "1"}


class Translator:
    """Carries the edit made by hand in the French page to the English one, and checks what it was given."""
    def __init__(self):
        self.prompts = []

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
        assert schema is MirrorResult and node == "mirror en/03-stack/engines.md"
        self.prompts.append(prompt)
        return MirrorResult(problem="", edits=[MirrorEdit(current="Ollama remains the easiest way to start.",
                                                          proposed="Ollama remains the easiest way to begin.")]), \
            {"node": node, "model": "fake", "input": 10, "output": 5, "cache_read": 0}


def wait(client, thread):
    import time
    for _ in range(300):
        run = client.get(f"/api/runs/{thread}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.05)
    raise AssertionError("run still going")


def test_sync_the_languages_of_a_page_edited_by_hand(setup, tmp_path):  # noqa: F811
    deps, _, _ = setup
    deps.llm = Translator()
    folder = deps.vault
    page = folder / "03-stack" / "engines.md"
    vault.write(page, vault.read(page).replace("pour démarrer.", "pour commencer."))  # in Obsidian
    c = TestClient(create_app(Settings(vault=folder, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    plan = c.get("/api/mirrors").json()
    assert plan["ahead"] == [] and plan["elsewhere"] == []
    assert [h["page"] for h in plan["hand"]] == ["03-stack/engines.md"] and plan["hand"][0]["passages"] == 1
    assert c.post("/api/mirrors", json={"hand": ["nope.md"]}, headers=ACT).status_code == 400

    thread = c.post("/api/mirrors", json={"hand": ["03-stack/engines.md"]}, headers=ACT).json()["thread"]
    run = wait(c, thread)
    assert run["status"] == "translation" and run["mode"] == "mirror", run  # the translation beside its source
    assert run["mirrored"] == ["en/03-stack/engines.md"] and run["mirror_problems"] == []
    pair = run["mirror_pairs"][0]
    assert pair["mirror"] == "en/03-stack/engines.md" and pair["source"] == [["Ollama reste le plus simple pour démarrer.",
                                                                              "Ollama reste le plus simple pour commencer."]]
    assert pair["target"] == [["Ollama remains the easiest way to start.", "Ollama remains the easiest way to begin."]]
    c.post(f"/api/runs/{thread}/translation", json={"edits": {"en/03-stack/engines.md#0": "Ollama is still the easiest way to begin."}},
           headers=ACT)
    run = wait(c, thread)
    assert run["status"] == "publish" and run["translation_retouched"] == ["en/03-stack/engines.md"]
    assert run["mirror_pairs"][0]["target"][0] == ["Ollama remains the easiest way to start.", "Ollama is still the easiest way to begin.",
                                                   "Ollama remains the easiest way to begin."]  # the translator's kept
    prompt = deps.llm.prompts[0]
    assert "pour démarrer." in prompt and "pour commencer." in prompt and "vLLM 0.31 est" not in prompt  # what changed only
    diff = c.get(f"/api/runs/{thread}/diff").text
    assert "pour commencer." in diff and "Ollama is still the easiest way to begin." in diff
    log = subprocess.run(["git", "log", "--format=%s", f"main..{run['branch']}"], cwd=folder, capture_output=True,
                         text=True).stdout
    assert log.splitlines() == ["chore(i18n): the translation retouched at the review",
                                "chore(i18n): sync the mirrors with the source pages", "docs: edits by hand"]
    assert "pour commencer." in vault.read(page)  # the folder keeps its copy, untouched

    c.post(f"/api/runs/{thread}/publish", json={"go": False}, headers=ACT)
    assert wait(c, thread)["status"] == "not-published"


def test_a_page_committed_ahead_of_its_mirror_is_offered_from_where_they_parted(setup, tmp_path):  # noqa: F811
    deps, _, _ = setup
    folder = deps.vault
    parted = subprocess.run(["git", "rev-parse", "HEAD"], cwd=folder, capture_output=True, text=True).stdout.strip()
    page = folder / "03-stack" / "engines.md"
    vault.write(page, vault.read(page).replace("pour démarrer.", "pour commencer."))
    sh("git", "commit", "-qam", "edited on main", cwd=folder)
    c = TestClient(create_app(Settings(vault=folder, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    plan = c.get("/api/mirrors").json()
    assert [(a["page"], a["since"], a["passages"]) for a in plan["ahead"]] == [("03-stack/engines.md", parted, 1)]
    assert plan["hand"] == [] and plan["languages"][0]["code"] == "en"


def test_a_page_of_another_branch_is_not_offered(setup, tmp_path):  # noqa: F811
    deps, _, _ = setup
    folder = deps.vault
    sh("git", "checkout", "-q", "-b", "draft", cwd=folder)
    page = folder / "03-stack" / "engines.md"
    vault.write(page, vault.read(page).replace("vLLM 0.31", "vLLM 0.32"))
    sh("git", "commit", "-qam", "a draft", cwd=folder)
    vault.write(page, vault.read(page).replace("pour démarrer.", "pour commencer."))
    c = TestClient(create_app(Settings(vault=folder, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    plan = c.get("/api/mirrors").json()
    assert plan["hand"] == [] and plan["elsewhere"] == ["03-stack/engines.md"]  # copied onto main, it would undo nothing safely


def test_settle_puts_back_a_local_copy_identical_to_what_is_merged(tmp_path):
    root = tmp_path / "g"
    root.mkdir()
    (root / "a.md").write_text("un\n", encoding="utf-8")
    (root / "b.md").write_text("deux\n", encoding="utf-8")
    sh("git", "init", "-q", "-b", "main", cwd=root)
    sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "add", ".", cwd=root)
    sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i", cwd=root)
    sh("git", "checkout", "-q", "-b", "merged", cwd=root)
    (root / "a.md").write_text("un bis\n", encoding="utf-8")
    sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "m", cwd=root)
    sh("git", "checkout", "-q", "main", cwd=root)
    (root / "a.md").write_text("un bis\n", encoding="utf-8")  # the same text, not committed
    (root / "b.md").write_text("deux, un brouillon\n", encoding="utf-8")  # another change: left alone
    assert vault.settle(root, "merged") == ["a.md"]
    sh("git", "merge", "-q", "--ff-only", "merged", cwd=root)
    assert (root / "a.md").read_text(encoding="utf-8") == "un bis\n"
    assert (root / "b.md").read_text(encoding="utf-8") == "deux, un brouillon\n"
