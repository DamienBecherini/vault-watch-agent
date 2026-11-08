"""Desktop notifications for `serve --notify`: a run waits for the human, has finished, or failed.

Windows only, without any dependency: PowerShell shows a toast through the Windows Runtime, under the
AppUserModelID of Windows PowerShell (no app to register). A click opens the page of the run in the
default browser. Elsewhere, and when anything fails, notifying is silently skipped: it is a convenience,
never a reason to stop a run.
"""

from __future__ import annotations

import base64
import subprocess
import sys
from xml.sax.saxutils import escape, quoteattr

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


def toast_xml(title: str, body: str, url: str) -> str:
    return (f'<toast activationType="protocol" launch={quoteattr(url)}>'
            f'<visual><binding template="ToastGeneric"><text>{escape(title)}</text><text>{escape(body)}</text>'
            f'</binding></visual><actions><action activationType="protocol" arguments={quoteattr(url)} '
            f'content="Ouvrir / Open"/></actions></toast>')


def toast(title: str, body: str, url: str) -> bool:
    """Show the notification; False when it could not be shown (not Windows, PowerShell error)."""
    if sys.platform != "win32":
        return False
    xml = base64.b64encode(toast_xml(title, body, url).encode("utf-8")).decode()  # no quoting issue in the script
    script = SCRIPT.replace("{xml}", xml).replace("{app}", APP_ID)
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                              capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        return done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
