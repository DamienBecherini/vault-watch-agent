"""Shared fixtures: the sample guide of examples/ in a throwaway git repository."""

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# The report of the suite, .pytest-report.md, and its history (report.py): hooks of pytest, imported to be found here
from report import pytest_runtest_logreport, pytest_sessionstart, pytest_terminal_summary  # noqa: F401

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample-guide"

_get = TestClient.get


@pytest.fixture(autouse=True)
def page_reads_with_its_header(monkeypatch):
    """The tests read the API as the page does: every GET carries X-Vault-Watch (web.local_only refuses the API
    without it), unless a test sets the header itself, to check a refusal."""
    def get(self, url, *args, headers=None, **kwargs):
        headers = dict(headers or {})
        if not any(k.lower() == "x-vault-watch" for k in headers):
            headers["X-Vault-Watch"] = "1"
        return _get(self, url, *args, headers=headers, **kwargs)
    monkeypatch.setattr(TestClient, "get", get)


@pytest.fixture(autouse=True)
def no_network_for_enrich(monkeypatch):
    """A candidate is read on Hugging Face and GitHub when it is added (enrich.py): never in the tests, which give
    their own reader when they test it."""
    from vault_watch_agent import enrich

    def offline(url, **kw):
        raise RuntimeError("no network in the tests")
    monkeypatch.setattr(enrich, "GET", offline)


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def sample_guide(tmp_path: Path):
    """(guide, watch.json): the sample guide committed on `main` of a new repository, its watch beside it."""
    guide = tmp_path / "guide"
    shutil.copytree(SAMPLE, guide, ignore=shutil.ignore_patterns("watch.json"))
    _git("init", "-q", "-b", "main", cwd=guide)
    _git("config", "user.name", "t", cwd=guide)
    _git("config", "user.email", "t@t", cwd=guide)
    _git("add", ".", cwd=guide)
    _git("commit", "-qm", "init", cwd=guide)
    watch = tmp_path / "watch.json"
    shutil.copy(SAMPLE / "watch.json", watch)
    return guide, watch
