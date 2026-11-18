"""Where the guide's repository lives: issues, workflow artifacts, pull requests. Only GitHub is written (through
the `gh` command line); a Gitea or GitLab forge is a class with the same methods.

    forge = get()                                   # GitHub through gh
    forge.issues("owner/guide", label="veille")     # the watch issues, newest first
    forge.open_pull_request("owner/guide", base="main", head="chore/watch-x", title=..., body=..., cwd=worktree)
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from . import inputs


class Forge(Protocol):
    name: str

    def can_read(self, repo: str) -> tuple[bool, str]: ...
    def issues(self, repo: str, label: str, limit: int = 12) -> list[dict]: ...
    def issue_body(self, repo: str, number: int) -> str: ...
    def close_issue(self, repo: str, number: int, comment: str) -> None: ...
    def download_artifact(self, repo: str, run_id: str, name: str, dest: Path) -> None: ...
    def open_pull_request(self, repo: str, *, base: str, head: str, title: str, body: str, cwd: Path) -> str: ...
    def pull_request_state(self, url: str) -> str: ...


class GitHub:
    """GitHub through `gh`, authenticated by the user (`gh auth login`)."""

    name = "GitHub"

    def can_read(self, repo: str) -> tuple[bool, str]:
        """Whether gh is there and can read `repo`, with what to do when it cannot."""
        program = shutil.which("gh")
        if not program:
            return False, "gh is not installed: it opens the pull requests and reads the issues"
        try:
            r = subprocess.run([program, "repo", "view", repo, "--json", "name"], capture_output=True, timeout=60,
                               stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return False, "gh could not be run"
        return (True, repo) if r.returncode == 0 else (False, f"gh cannot read {repo} (`gh auth login`, or check [guide] repository)")

    def issues(self, repo: str, label: str, limit: int = 12) -> list[dict]:
        """{number, title, state (open|closed), date, labels, body}, newest first."""
        out = inputs.run(["gh", "issue", "list", "--repo", repo, "--label", label, "--state", "all",
                          "--limit", str(limit), "--json", "number,title,state,createdAt,labels,body"])
        return [{"number": i["number"], "title": i["title"], "state": i["state"].lower(), "date": i["createdAt"][:10],
                 "labels": [lab["name"] for lab in i["labels"]], "body": i.get("body") or ""} for i in json.loads(out)]

    def issue_body(self, repo: str, number: int) -> str:
        return inputs.run(["gh", "issue", "view", str(number), "--repo", repo, "--json", "body", "--jq", ".body"])

    def close_issue(self, repo: str, number: int, comment: str) -> None:
        inputs.run(["gh", "issue", "close", str(number), "--repo", repo, "--comment", comment])

    def download_artifact(self, repo: str, run_id: str, name: str, dest: Path) -> None:
        inputs.run(["gh", "run", "download", run_id, "--repo", repo, "-n", name, "-D", str(dest)])

    def open_pull_request(self, repo: str, *, base: str, head: str, title: str, body: str, cwd: Path) -> str:
        return inputs.run(["gh", "pr", "create", "--repo", repo, "--base", base, "--head", head,
                           "--title", title, "--body", body], cwd=cwd).strip()

    def pull_request_state(self, url: str) -> str:
        """open, merged or closed."""
        return inputs.run(["gh", "pr", "view", url, "--json", "state", "--jq", ".state"]).strip().lower()


_forge: Forge = GitHub()


def get() -> Forge:
    return _forge


def use(forge: Forge) -> None:
    """Replaces the forge (tests, or another forge than GitHub)."""
    global _forge
    _forge = forge
