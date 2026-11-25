"""Desktop notifications for `serve --notify`: a run waits for the human, has finished, or failed.

Without any Python dependency, through what each system already has:

  - Windows: PowerShell shows a toast through the Windows Runtime, under the AppUserModelID of Windows PowerShell
    (no app to register); a click opens the page of the run in the default browser.
  - macOS: `terminal-notifier` when it is installed (a click opens the page), else `osascript` (`display
    notification`, which cannot open a page: the notification says where to look).
  - Linux and the other Unix desktops: `notify-send` (libnotify); when it supports actions, a button opens the page,
    else the address is in the notification's text.

Title and text are passed as arguments, never written into a script or a command line to interpret. When nothing
can notify, or anything fails, notifying is silently skipped: it is a convenience, never a reason to stop a run.
"""

from __future__ import annotations

import base64
import functools
import shutil
import subprocess
import sys
import threading
import webbrowser
from xml.sax.saxutils import escape, quoteattr

OPEN = "Ouvrir / Open"  # the label of the button that opens the page, in both languages like the rest of a toast

APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

SCRIPT = """
[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{xml}')))
$toast = [Windows.UI.Notifications.ToastNotification]::new($doc)
$toast.Group = 'vault-watch'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app}').Show($toast)
"""

# osascript reads the title and the text from its arguments: nothing to escape, nothing to inject
APPLESCRIPT = ["-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
               "-e", "end run"]


def toast_xml(title: str, body: str, url: str) -> str:
    return (f'<toast activationType="protocol" launch={quoteattr(url)}>'
            f'<visual><binding template="ToastGeneric"><text>{escape(title)}</text><text>{escape(body)}</text>'
            f'</binding></visual><actions><action activationType="protocol" arguments={quoteattr(url)} '
            f'content="{OPEN}"/></actions></toast>')


def toast(title: str, body: str, url: str) -> bool:
    """Show the notification; False when it could not be shown (no notifier on this system, an error)."""
    try:
        if sys.platform == "win32":
            return _windows(title, body, url)
        if sys.platform == "darwin":
            return _macos(title, body, url)
        return _linux(title, body, url)
    except (OSError, subprocess.SubprocessError):
        return False


def _windows(title: str, body: str, url: str) -> bool:
    xml = base64.b64encode(toast_xml(title, body, url).encode("utf-8")).decode()  # no quoting issue in the script
    script = SCRIPT.replace("{xml}", xml).replace("{app}", APP_ID)
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))  # Windows only
    return done.returncode == 0


def _macos(title: str, body: str, url: str) -> bool:
    notifier = shutil.which("terminal-notifier")
    if notifier:
        command = [notifier, "-title", title, "-message", body, "-open", url, "-group", "vault-watch"]
    else:
        command = ["osascript", *APPLESCRIPT, title, f"{body}\n{url}"]
    return subprocess.run(command, capture_output=True, timeout=20).returncode == 0


def _linux(title: str, body: str, url: str) -> bool:
    notifier = shutil.which("notify-send")
    if not notifier:
        return False
    base = [notifier, "--app-name=vault-watch"]
    if not has_actions(notifier):
        return subprocess.run([*base, "--", title, f"{body}\n{url}"], capture_output=True, timeout=20).returncode == 0
    # with a button, notify-send waits for the click (or the notification closing) and prints the action chosen:
    # a thread of its own waits, so that the run that announced itself goes on
    waiting = subprocess.Popen([*base, f"--action=open={OPEN}", "--wait", "--", title, body],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    threading.Thread(target=open_on_click, args=(waiting, url), daemon=True).start()
    return True


@functools.cache
def has_actions(notifier: str) -> bool:
    """notify-send of libnotify 0.7.9 and later takes --action; older ones refuse it."""
    try:
        shown = subprocess.run([notifier, "--help"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return "--action" in shown.stdout


def open_on_click(waiting: subprocess.Popen, url: str) -> None:
    out, _ = waiting.communicate()
    if (out or "").strip().splitlines()[-1:] == ["open"]:
        webbrowser.open(url)
