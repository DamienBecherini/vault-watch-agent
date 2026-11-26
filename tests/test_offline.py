"""The tests never reach the network (conftest.no_network, asked by the user on 2026-11-26): what the guard refuses
and what it lets through."""

import shutil
import socket
import subprocess

import pytest


def test_a_connection_outside_this_machine_is_refused():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s, pytest.raises(RuntimeError, match="no network"):
        s.connect(("93.184.215.14", 443))


def test_this_machine_is_reachable():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.create_connection(server.getsockname(), timeout=2):
            pass


def test_gh_is_signed_in_nowhere():
    for program in ("gh", shutil.which("gh") or "C:/tools/gh.exe"):
        done = subprocess.run([program, "auth", "token"], capture_output=True, text=True, check=False)
        assert (done.returncode, done.stdout) == (4, "") and "no network in the tests" in done.stderr
    from vault_watch_agent import collect
    assert collect.github_token() == ""  # never the token of the machine's gh
