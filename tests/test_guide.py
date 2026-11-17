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


def _guide(root: Path, content: str) -> Path:
    (root / "vault-watch.toml").write_text('[guide]\nname = "G"\n[content]\nlanguage = "de"\n' + content, encoding="utf-8")
    for rel in ("a.md", "es/a.md", "notes/b.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("---\nupdated: \"2026-01-01\"\nlast_modified: \"2026-01-01\"\n---\n\nAlt 1.0.\n",
                                encoding="utf-8")
    return root


def test_the_edits_follow_the_manifest(tmp_path):
    root = _guide(tmp_path, 'mirrors = { es = "es/" }\nmodified_field = "updated"\nexclude = ["notes/**"]\n')
    assert vault.pages(root) == [root / "a.md"] and vault.in_mirror(root, "es/a.md") and not vault.in_mirror(root, "a.md")
    vault.apply(root, "a.md", "Alt 1.0.", "Neu 2.0.", "2026-11-18")
    text = (root / "a.md").read_text(encoding="utf-8")
    assert 'updated: "2026-11-18"' in text and 'last_modified: "2026-01-01"' in text  # only the manifest's field
    assert vault.date_bump_only('updated: "2026-01-01"', 'updated: "2026-11-18"', "updated")
    assert not vault.date_bump_only('updated: "2026-01-01"', 'updated: "2026-11-18"', None)


def test_a_guide_without_a_modified_field_keeps_its_dates(tmp_path):
    root = _guide(tmp_path, "")
    vault.apply(root, "a.md", "Alt 1.0.", "Neu 2.0.", "2026-11-18")
    assert "2026-11-18" not in (root / "a.md").read_text(encoding="utf-8")
    assert vault.pages(root) == [root / "a.md", root / "es" / "a.md", root / "notes" / "b.md"]  # no mirror declared


def test_a_changed_manifest_is_read_again(tmp_path):
    root = _guide(tmp_path, "")
    assert len(vault.pages(root)) == 3
    import os
    import time
    (root / "vault-watch.toml").write_text('[guide]\nname = "G"\n[content]\nlanguage = "de"\nexclude = ["es/**"]\n',
                                          encoding="utf-8")
    later = time.time() + 5
    os.utime(root / "vault-watch.toml", (later, later))
    assert len(vault.pages(root)) == 2


def test_the_checks_of_the_manifest_run_with_their_output_file(tmp_path):
    from vault_watch_agent import inputs
    root = _guide(tmp_path, '[checks]\nclaims_due = "node due.mjs --json={out} --due-only"\n')
    (root / "due.mjs").write_text(
        "import { writeFileSync } from 'node:fs';\n"
        "const out = process.argv.find(a => a.startsWith('--json=')).slice(7);\n"
        "writeFileSync(out, JSON.stringify({claimsDue: [{page: 'a.md', claim: 'x'}]}));\n", encoding="utf-8")
    out = tmp_path / "work dir" / "due.json"  # a space in the path: one argument all the same
    assert inputs.claims_due(root, out) == [{"page": "a.md", "claim": "x"}]
    assert inputs.check("audits", root) is None  # not declared: not checked


def test_the_prompts_and_translation_follow_the_manifest(tmp_path):
    from vault_watch_agent import crosscheck, fix, prompts, verify
    root = _guide(tmp_path, 'mirrors = { es = "es/" }\n')
    for text in (crosscheck.SYSTEM, crosscheck.SWEEP_SYSTEM, fix.SYSTEM, verify.COHERENCE, verify.CLAIMS, verify.DEAD_LINKS):
        filled = prompts.fill(text, root)
        assert "German" in filled and "French" not in filled and "on-premise" not in filled
    for text in (fix.TRANSLATION_SYSTEM, verify.TRANSLATION):
        filled = prompts.fill(text, root, "es")
        assert "Spanish" in filled and "es/" in filled and "English mirror" not in filled and "en/" not in filled
    assert fix.pages_of("[Minor] es/notes/b.md: a row is missing", root) == (["notes/b.md", "es/notes/b.md"], "es")
    assert fix.pages_of("[Minor] notes/b.md: differs", root) == (["notes/b.md", "es/notes/b.md"], "es")
    assert verify.mirror_pages(root) == [root / "es" / "a.md"]  # notes/b.md has no copy in es/


def test_no_string_of_the_ia_on_prem_guide_left_in_the_code():
    """What is specific to one guide is in its manifest (or guide.legacy, for a guide without one)."""
    src = Path(__file__).resolve().parent.parent / "src" / "vault_watch_agent"
    for path in src.glob("*.py"):
        if path.name == "guide.py":  # its legacy() describes the IA on-prem guide, for a guide without a manifest
            continue
        if path.name == "cli.py":  # until T1.5 (--guide): its default guide folder is ../ia-on-prem-vault
            continue
        text = path.read_text(encoding="utf-8")
        for needle in ("ia-on-prem-vault", "ia-on-prem.damien", "French-language guide", "on-premise for SMEs",
                       '"en/', "scripts/run-audits", "scripts/audit-"):
            assert needle not in text, f"{path.name}: {needle}"


def test_a_guide_without_rules_gets_the_agent_defaults(tmp_path):
    from vault_watch_agent import prompts
    root = _guide(tmp_path, 'mirrors = { es = "es/" }\n')
    assert 'path="vault-watch default: brief.md"' in prompts.triage(root) and "Tier A" in prompts.propose(root)
    assert 'path="vault-watch default: translation-policy.md"' in prompts.mirror(root, "es")
    (root / "rules.md").write_text("# Our own brief\n", encoding="utf-8")
    (root / "vault-watch.toml").write_text('[guide]\nname = "G"\n[content]\nlanguage = "de"\n[rules]\nbrief = "rules.md"\n',
                                          encoding="utf-8")
    import os
    import time
    later = time.time() + 5
    os.utime(root / "vault-watch.toml", (later, later))
    assert 'path="rules.md"' in prompts.triage(root) and "Our own brief" in prompts.triage(root)


def test_each_guide_has_its_working_folder_and_the_old_runs_stay_where_they_are(tmp_path):
    from vault_watch_agent.guide import working_folder
    home = tmp_path / "home"
    home.mkdir()
    (home / "checkpoints.sqlite").write_text("", encoding="utf-8")  # runs made before manifests
    old = legacy(tmp_path / "ia-on-prem-vault")
    assert working_folder(home, old) == home  # claimed once, recorded in guide.json
    assert working_folder(home, old) == home and (home / "guide.json").is_file()
    sample = parse(minimal(guide={"repository": "someone/notes-guide"}), tmp_path / "notes")
    assert working_folder(home, sample) == home / "guides" / "someone-notes-guide"
    local = parse(minimal(), tmp_path / "my guide")
    assert working_folder(home, local) == home / "guides" / "my-guide"

    # The IA on-prem guide with its manifest (0.3.0) keeps the runs of before
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    (fresh / "checkpoints.sqlite").write_text("", encoding="utf-8")
    manifest = parse(minimal(guide={"repository": legacy(tmp_path).repository}), tmp_path / "ia-on-prem-vault")
    assert working_folder(fresh, manifest) == fresh and (fresh / "guide.json").is_file()


def test_the_command_line_finds_the_guide(tmp_path, monkeypatch):
    from vault_watch_agent import cli
    guide = tmp_path / "g"
    guide.mkdir()
    (guide / "vault-watch.toml").write_text('[guide]\nname = "G"\n[content]\nlanguage = "en"\n', encoding="utf-8")
    monkeypatch.delenv("VAULT_PATH", raising=False)
    monkeypatch.chdir(guide)
    assert cli.find_guide(None) == guide.resolve()  # the current folder, with its manifest
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    assert cli.find_guide(None) == tmp_path.resolve() and cli.find_guide(str(guide)) == guide.resolve()
    monkeypatch.setattr(cli, "CONFIG_HOME", tmp_path / "home")
    cli.use_guide(str(guide))
    assert cli.VAULT == guide.resolve() and cli.HOME == tmp_path / "home" / "guides" / "g"
    (guide / "vault-watch.toml").write_text('[guide]\nname = "G"\n', encoding="utf-8")
    import os
    import time
    later = time.time() + 5
    os.utime(guide / "vault-watch.toml", (later, later))
    with pytest.raises(SystemExit, match="language is required"):
        cli.use_guide(str(guide))
