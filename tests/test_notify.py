"""Desktop notifications on each system: the command each one runs, the click that opens the page, nothing to inject.
No notification is shown: every command is caught."""

from __future__ import annotations

import subprocess
import sys

import pytest

from vault_watch_agent import notify

TITLE, BODY, URL = 'vault-watch · add-1 · Review pending', '3 correction(s) "proposed": your call.', "http://127.0.0.1:4430/#/run/add-1"


class Done:
    def __init__(self, code=0, stdout=""):
        self.returncode, self.stdout = code, stdout


class Calls(list):
    """The commands run, and the tools which() finds (`found`)."""

    def __init__(self):
        super().__init__()
        self.found: set[str] = set()


@pytest.fixture
def ran(monkeypatch):
    """Every command run, and a which() that finds only the tools named in `ran.found`."""
    calls = Calls()

    def run(command, **kw):
        calls.append(command)
        return Done(0, "Usage: notify-send [OPTION…] <SUMMARY> [BODY]\n  -A, --action=[NAME=]Text…" if "--help" in command else "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(notify.shutil, "which", lambda name: f"/usr/bin/{name}" if name in calls.found else None)
    notify.has_actions.cache_clear()
    return calls


def test_linux_without_notify_send_says_so(monkeypatch, ran):
    monkeypatch.setattr(sys, "platform", "linux")
    assert notify.toast(TITLE, BODY, URL) is False
    assert ran == []


def test_linux_button_opens_the_page_when_clicked(monkeypatch, ran):
    monkeypatch.setattr(sys, "platform", "linux")
    ran.found.add("notify-send")
    started, opened = [], []

    class Waiting:
        def __init__(self, command, **kw):
            started.append(command)

        def communicate(self):
            return "open\n", ""

    monkeypatch.setattr(subprocess, "Popen", Waiting)
    monkeypatch.setattr(notify.webbrowser, "open", opened.append)
    monkeypatch.setattr(notify.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda self: target(*args)})())
    assert notify.toast(TITLE, BODY, URL) is True
    command = started[0]
    assert command[:3] == ["/usr/bin/notify-send", "--app-name=vault-watch", "--action=open=Ouvrir / Open"]
    assert command[-3:] == ["--", TITLE, BODY]  # as arguments, after "--": a text starting with « - » is no option
    assert opened == [URL]


def test_linux_notification_closed_opens_nothing(monkeypatch, ran):
    monkeypatch.setattr(sys, "platform", "linux")
    ran.found.add("notify-send")
    opened = []
    waiting = type("W", (), {"communicate": lambda self: ("", "")})()
    monkeypatch.setattr(notify.webbrowser, "open", opened.append)
    notify.open_on_click(waiting, URL)
    assert opened == []


def test_linux_old_notify_send_puts_the_address_in_the_text(monkeypatch, ran):
    monkeypatch.setattr(sys, "platform", "linux")
    ran.found.add("notify-send")
    monkeypatch.setattr(notify, "has_actions", lambda notifier: False)
    assert notify.toast(TITLE, BODY, URL) is True
    assert ran[-1] == ["/usr/bin/notify-send", "--app-name=vault-watch", "--", TITLE, f"{BODY}\n{URL}"]


def test_macos_terminal_notifier_opens_the_page(monkeypatch, ran):
    monkeypatch.setattr(sys, "platform", "darwin")
    ran.found.add("terminal-notifier")
    assert notify.toast(TITLE, BODY, URL) is True
    assert ran[-1] == ["/usr/bin/terminal-notifier", "-title", TITLE, "-message", BODY, "-open", URL, "-group", "vault-watch"]


def test_macos_osascript_reads_the_texts_as_arguments(monkeypatch, ran):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert notify.toast(TITLE, BODY, URL) is True
    command = ran[-1]
    assert command[0] == "osascript" and command[-2:] == [TITLE, f"{BODY}\n{URL}"]
    script = " ".join(command[1:-2])
    assert '"' not in script and TITLE not in script  # the quotes of the text cannot close a string of the script


def test_a_failing_notifier_is_skipped(monkeypatch, ran):
    monkeypatch.setattr(sys, "platform", "darwin")

    def broken(command, **kw):
        raise OSError("no osascript")

    monkeypatch.setattr(subprocess, "run", broken)
    assert notify.toast(TITLE, BODY, URL) is False


def test_windows_toast_escapes_the_texts():
    xml = notify.toast_xml("a <b> & c", 'd "e"', "http://127.0.0.1:4430/#/run/x?a=1&b=2")
    assert "<b>" not in xml and "a &lt;b&gt; &amp; c" in xml
    assert 'launch="http://127.0.0.1:4430/#/run/x?a=1&amp;b=2"' in xml
