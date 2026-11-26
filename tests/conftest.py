"""Shared fixtures: the sample guide of examples/ in a throwaway git repository."""

import ipaddress
import shutil
import socket
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


_run = subprocess.run
_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex


def _local(address) -> bool:
    """A loopback address (the test servers, Chrome's debugging port) or a Unix socket."""
    if not isinstance(address, tuple):
        return True  # AF_UNIX: a path
    try:
        return ipaddress.ip_address(str(address[0]).split("%")[0]).is_loopback
    except ValueError:
        return str(address[0]).lower() == "localhost"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test reaches the network (asked by the user, 2026-11-26, after 1.7.0's CI failed on a test that read a real
    GitHub issue through `gh`, signed in on the author's machine only): a connection to anything but this machine
    is refused, and `gh` runs as on the CI, signed in nowhere (no token, an empty configuration). A test that needs
    an answer from the web gives its own reader."""
    def connect(self, address):
        if not _local(address):
            raise RuntimeError(f"no network in the tests: connection to {address} refused (give the test its own reader)")
        return _connect(self, address)

    def connect_ex(self, address):
        if not _local(address):
            raise RuntimeError(f"no network in the tests: connection to {address} refused (give the test its own reader)")
        return _connect_ex(self, address)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    # `gh` answers as on the CI, signed in nowhere (its token on Windows is in the credential store, which an empty
    # GH_CONFIG_DIR does not hide): every call fails, exit 4, whoever makes it (the forge, collect.github_token…)
    def run(args, *a, **kw):
        program = args[0] if isinstance(args, (list, tuple)) and args else str(args).split(" ")[0]
        if Path(str(program)).stem.lower() == "gh":
            return subprocess.CompletedProcess(args, 4, "" if kw.get("text") or kw.get("encoding") else b"",
                                               "gh: signed in nowhere (no network in the tests)" if kw.get("text") or kw.get("encoding") else b"")
        return _run(args, *a, **kw)
    monkeypatch.setattr(subprocess, "run", run)


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
