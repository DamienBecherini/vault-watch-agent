"""The manifest of a guide (guide.py): defaults, refusals, the two manifests of examples/."""

import os
import shutil
import tomllib
from pathlib import Path

import pytest

from vault_watch_agent import vault
from vault_watch_agent.guide import GuideError, legacy, load, matches, parse

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
# The real guide when it is checked out: VAULT_PATH, else beside the agent's folder
IA_ON_PREM = Path(os.environ.get("VAULT_PATH") or Path(__file__).resolve().parent.parent.parent / "ia-on-prem-vault")


def minimal(**tables) -> dict:
    data = {"guide": {"name": "G"}, "content": {"language": "en"}}
    for table, values in tables.items():
        data.setdefault(table, {}).update(values)
    return data


def test_defaults_of_a_minimal_manifest(tmp_path):
    g = parse(minimal(), tmp_path)
    assert (g.name, g.language, g.repository, g.base_branch) == ("G", "en", "", "main")
    assert g.include == ("**/*.md", "**/*.mdx") and g.exclude == () and g.mirrors == {}
    assert g.modified_field is None and g.watch.source == "none"
    assert (g.brief, g.audits, g.claims_due, g.sources, g.version_floors, g.max_context_tokens) == (None,) * 6


@pytest.mark.parametrize("data, says", [
    ({"guide": {"name": "G"}, "content": {"language": "en", "langauge": "fr"}}, "unknown key langauge in [content]"),
    ({"guide": {"name": "G"}, "content": {"language": "en"}, "extra": {}}, "unknown key extra in the top level"),
    ({"guide": {}, "content": {"language": "en"}}, "[guide] name is required"),
    ({"guide": {"name": "G"}}, "[content] language is required"),
    (minimal(guide={"repository": "just-a-name"}), "expected owner/name"),
    (minimal(content={"mirrors": {"fr": "fr"}}), "the folder ends with /"),
    (minimal(content={"mirrors": {"en": "en/"}}), "is the language of the pages"),
    (minimal(content={"exclude": "en/**"}), "a list of glob patterns"),
    (minimal(watch={"source": "rss"}), "one of none, github-issue, file"),
    (minimal(watch={"source": "file"}), "needs path"),
    (minimal(rules={"brief": "missing.md"}), "no such file in the guide"),
    (minimal(rules={"brief": "../outside.md"}), "must stay inside the guide"),
    (minimal(checks={"claims_due": "node x.mjs"}), "must write its JSON to {out}"),
    (minimal(checks={"version_floors": {"script": "x.mjs"}}), "a table with script and file"),
    (minimal(budget={"max_context_tokens": "450k"}), "a positive whole number"),
    ({**minimal(), "schema": 2}, "reads schema 1"),
])
def test_each_mistake_is_refused_with_its_key(tmp_path, data, says):
    with pytest.raises(GuideError) as e:
        parse(data, tmp_path)
    assert says in str(e.value)


def test_no_manifest_and_bad_toml(tmp_path):
    with pytest.raises(GuideError, match="vault-watch init"):
        load(tmp_path)
    (tmp_path / "vault-watch.toml").write_text("[guide\nname = 1", encoding="utf-8")
    with pytest.raises(GuideError, match="not valid TOML"):
        load(tmp_path)


@pytest.mark.parametrize("path, pattern, expected", [
    ("en/a/b.md", "en/**", True), ("index.md", "en/**", False), ("README.md", "README.md", True),
    ("x/README.md", "README.md", False), ("a/draft-1.md", "**/draft-*.md", True), ("draft-1.md", "**/draft-*.md", True),
    ("a/b/c.md", "a/*.md", False), ("a/c.md", "a/*.md", True),
])
def test_globs(path, pattern, expected):
    assert matches(path, pattern) is expected


def test_the_sample_manifest(tmp_path):
    root = tmp_path / "guide"
    shutil.copytree(EXAMPLES / "sample-guide", root)
    (root / ".agents").mkdir()
    (root / ".agents" / "note.md").write_text("tooling\n", encoding="utf-8")
    g = load(root)
    assert (g.name, g.language, g.repository, g.watch.source, g.watch.path) == (
        "Self-hosted notes server", "en", "", "file", "watch.json")
    assert len(g.pages()) == 12 and root / "README.md" not in g.pages()  # nor the dot folder


def test_the_ia_on_prem_manifest(tmp_path):
    for rel in (".agents/skills/vault-watch/brief.md",
                ".agents/skills/vault-translate-content/references/translation-policy.md",
                "scripts/audit-version-floors.mjs", "03-stack/engines.md", "en/03-stack/engines.md", "README.md"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x\n", encoding="utf-8")
    g = parse(tomllib.loads((EXAMPLES / "manifests" / "ia-on-prem-vault.toml").read_text(encoding="utf-8")), tmp_path)
    assert (g.language, g.mirrors, g.modified_field, g.watch.label) == ("fr", {"en": "en/"}, "last_modified", "veille")
    assert g.pages() == [tmp_path / "03-stack" / "engines.md"]  # not its mirror, not the README
    assert g.mirror_of("03-stack/engines.md", "en") == "en/03-stack/engines.md" and g.mirror_of("a.md", "de") is None
    assert g.brief == tmp_path / ".agents/skills/vault-watch/brief.md" and g.max_context_tokens == 450000
    assert "{out}" in g.claims_due and g.version_floors.file.endswith("version-floors.json")
    assert legacy(tmp_path).pages() == g.pages()  # the manifest says what the agent assumed


@pytest.mark.skipif(not (IA_ON_PREM / "00-index.md").is_file(), reason="the IA on-prem guide is not checked out here")
def test_the_ia_on_prem_manifest_finds_the_same_pages_as_before():
    g = parse(tomllib.loads((EXAMPLES / "manifests" / "ia-on-prem-vault.toml").read_text(encoding="utf-8")), IA_ON_PREM)
    assert g.pages() == vault.french_pages(IA_ON_PREM)
