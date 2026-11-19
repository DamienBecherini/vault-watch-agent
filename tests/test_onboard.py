"""vault-watch init and doctor: the manifest proposed from a folder, and what doctor reports."""

import subprocess
from pathlib import Path

import pytest

from vault_watch_agent import cli, onboard
from vault_watch_agent.guide import MANIFEST, load


def _page(root: Path, rel: str, text: str, field: str = "last_modified") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {rel}\n{field}: 2026-06-01\n---\n\n{text}\n", encoding="utf-8")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """A French guide with an English mirror, private notes, templates and tooling, in its own repository."""
    root = tmp_path / "guide"
    fr = "Le serveur est installé dans une machine pour les équipes qui veulent garder les données sur place avec la base."
    en = "The server is installed on a machine for the teams that want to keep the data on site with the database."
    for rel in ("index.md", "01-bases/serveur.md", "02-usage/sauvegarde.md"):
        _page(root, rel, fr)
        _page(root, f"en/{rel}", en)
    _page(root, "_private/notes.md", fr)
    _page(root, "_templates/chapitre.md", fr)
    _page(root, "node_modules/pkg/readme.md", en)
    (root / "README.md").write_text("# Guide\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "remote", "add", "origin", "https://github.com/someone/notes-guide.git")
    return root


def test_proposed_manifest_reads_the_folder(folder):
    text = onboard.propose(folder)
    guide = onboard.load_text(text, folder)
    assert guide.language == "fr"
    assert guide.mirrors == {"en": "en/"}
    assert guide.modified_field == "last_modified"
    assert guide.repository == "someone/notes-guide"
    assert guide.base_branch == "main"
    pages = sorted(p.relative_to(folder).as_posix() for p in guide.pages())
    assert pages == ["01-bases/serveur.md", "02-usage/sauvegarde.md", "index.md"]  # no _private, _templates, tooling


def test_init_writes_once(folder):
    path = onboard.write(folder)
    assert load(folder).language == "fr" and path == folder / MANIFEST
    with pytest.raises(FileExistsError):
        onboard.write(folder)
    onboard.write(folder, force=True)


def test_a_folder_without_hints_gets_commented_defaults(tmp_path):
    (tmp_path / "page.md").write_text("plain text without front matter\n", encoding="utf-8")
    text = onboard.propose(tmp_path)
    guide = onboard.load_text(text, tmp_path)
    assert guide.repository == "" and guide.modified_field is None and guide.mirrors == {}
    assert '# repository = "owner/name"' in text and "# modified_field" in text


def test_doctor_on_the_sample_guide(sample_guide, tmp_path, monkeypatch):
    guide, _ = sample_guide
    monkeypatch.setenv("VAULT_WATCH_ENGINE", "api")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    lines = {line.label: line for line in onboard.diagnose(guide, tmp_path / "home", gh_check=False)}
    assert lines["manifest"].status == "ok" and lines["pages"].detail == "12 found"
    assert lines["git"].status == "ok"
    assert lines["GitHub"].status == "off" and lines["check audits"].status == "off"
    assert lines["watch"].status == "warn"  # watch.json is kept outside the copy
    assert lines["engine"].status == "fail" and "where vault-watch runs" in lines["engine"].detail


def test_doctor_names_a_wrong_manifest_and_a_subfolder(folder, tmp_path):
    (folder / MANIFEST).write_text('schema = 1\n[guide]\nname = "x"\nnmae = "typo"\n[content]\nlanguage = "fr"\n',
                                   encoding="utf-8")
    [line] = onboard.diagnose(folder, tmp_path / "home", gh_check=False)
    assert line.status == "fail" and "nmae" in line.detail

    sub = folder / "01-bases"
    lines = {line.label: line for line in onboard.diagnose(sub, tmp_path / "home", gh_check=False)}
    assert lines["git"].status == "fail" and "root of its own" in lines["git"].detail


def test_cli_init_and_doctor(folder, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "CONFIG_HOME", tmp_path / "home")
    monkeypatch.setenv("VAULT_WATCH_ENGINE", "api")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-value")
    monkeypatch.setattr(onboard.shutil, "which", lambda name: None if name == "gh" else name)
    cli.main(["--guide", str(folder), "init"])
    assert (folder / MANIFEST).is_file()
    with pytest.raises(SystemExit):
        cli.main(["--guide", str(folder), "init"])  # exists
    with pytest.raises(SystemExit) as stop:
        cli.main(["--guide", str(folder), "doctor"])  # repository named, gh missing
    assert stop.value.code == 1
    assert "gh is not installed" in capsys.readouterr().out


def test_doctor_names_a_gitea_forge(folder, tmp_path):
    (folder / MANIFEST).write_text('schema = 1\n[guide]\nname = "G"\nrepository = "owner/guide"\nforge = "gitea"\n'
                                   'forge_url = "http://gitea.test:3100"\n[content]\nlanguage = "fr"\n',
                                   encoding="utf-8")
    lines = {line.label: line for line in onboard.diagnose(folder, tmp_path / "home", gh_check=False)}
    assert "GitHub" not in lines  # gh is not needed
    assert lines["Gitea"].status == "ok" and lines["Gitea"].detail == "owner/guide on http://gitea.test:3100"


def test_the_agent_folder_is_never_created_inside_the_guide(tmp_path, monkeypatch):
    monkeypatch.delenv("VAULT_WATCH_HOME", raising=False)
    monkeypatch.delenv("VAULT_WATCH_JOURNAL", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "user")
    guide = tmp_path / "guide"
    guide.mkdir()
    monkeypatch.chdir(guide)
    assert cli.default_home() == (tmp_path / "user" / ".vault-watch").resolve()
    assert cli.default_journal(cli.default_home()) == (tmp_path / "user" / ".vault-watch" / "usage.jsonl").resolve()
    # The agent's own clone, as before 1.0: its .vault-watch and its versioned journal
    clone = tmp_path / "clone"
    (clone / ".vault-watch").mkdir(parents=True)
    (clone / "metrics").mkdir()
    (clone / "metrics" / "usage.jsonl").write_text("", encoding="utf-8")
    monkeypatch.chdir(clone)
    assert cli.default_home() == (clone / ".vault-watch").resolve()
    assert cli.default_journal(cli.default_home()) == (clone / "metrics" / "usage.jsonl").resolve()
    monkeypatch.setenv("VAULT_WATCH_HOME", str(tmp_path / "elsewhere"))
    assert cli.default_home() == (tmp_path / "elsewhere").resolve()
