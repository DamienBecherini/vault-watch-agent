"""Where the guide's repository lives: issues, workflow artifacts, pull requests. Two forges: GitHub (through the
`gh` command line) and Gitea (through its REST API, with a token). The manifest chooses (`[guide] forge`); another
forge (GitLab…) is a class with the same methods.

    use(for_guide(guide))                           # the guide's forge, for the rest of the process
    forge = get()
    forge.issues("owner/guide", label="veille")     # the watch issues, newest first
    forge.open_pull_request("owner/guide", base="main", head="chore/watch-x", title=..., body=..., cwd=worktree)

The branch itself is pushed by git (`git push origin`), with the user's own access (ssh key or credential helper):
the forge only opens the pull request.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

from . import inputs

FORGES = ("github", "gitea")


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
        # The description in a file: as an argument, a long one is refused by Windows before gh runs (a command
        # line holds 32 767 characters; the 193 trims of 20/11/2026 made 117 000)
        with tempfile.TemporaryDirectory(prefix="vault-watch-pr-") as folder:
            text = Path(folder) / "body.md"
            text.write_text(body, encoding="utf-8", newline="\n")
            return inputs.run(["gh", "pr", "create", "--repo", repo, "--base", base, "--head", head,
                               "--title", title, "--body-file", str(text)], cwd=cwd).strip()

    def pull_request_state(self, url: str) -> str:
        """open, merged or closed."""
        return inputs.run(["gh", "pr", "view", url, "--json", "state", "--jq", ".state"]).strip().lower()


class ForgeError(RuntimeError):
    pass


class Gitea:
    """A Gitea server through its REST API (`/api/v1`). The token is given by reference (env:NAME, sops:file#NAME or
    file:path, as the API key of the settings) and read on the first call; it needs the repository scope in writing
    (pull requests) and the issue scope in writing (to close a watch issue), on the guide's repository only if the
    account allows it (a dedicated account, collaborator of that repository alone)."""

    name = "Gitea"

    def __init__(self, url: str, token: str = "env:GITEA_TOKEN", client=None):
        self.url = url.rstrip("/")
        self.token_ref = token
        self._token: str | None = None
        self._client = client  # an httpx.Client (tests give one with a mock transport)

    # -- HTTP

    def _http(self):
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=60, follow_redirects=True)
        return self._client

    def _headers(self) -> dict:
        if self._token is None:
            from .config import ConfigError, resolve_key

            try:
                self._token = resolve_key(self.token_ref)
            except ConfigError as e:
                raise ForgeError(f"Gitea token ({self.token_ref}): {e}") from e
        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        return headers

    def _call(self, method: str, path: str, *, json_body: dict | None = None, params: dict | None = None,
              raw: bool = False) -> Any:
        url = f"{self.url}/api/v1{path}"
        try:
            r = self._http().request(method, url, headers=self._headers(), json=json_body, params=params)
        except Exception as e:  # httpx.HTTPError, an unreachable server
            raise ForgeError(f"Gitea {self.url} cannot be reached ({type(e).__name__})") from e
        if r.status_code >= 400:
            detail = ""
            try:
                detail = str(r.json().get("message") or "")
            except ValueError:
                pass
            hint = " (check the token: [guide] forge_token)" if r.status_code in (401, 403) else ""
            raise ForgeError(f"Gitea {method} {path}: {r.status_code} {detail[:300]}{hint}".rstrip())
        if raw:
            return r.content
        return r.json() if r.content else None

    @staticmethod
    def _repo(repo: str) -> str:
        owner, _, name = repo.partition("/")
        return f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"

    # -- Forge

    def can_read(self, repo: str) -> tuple[bool, str]:
        try:
            self._call("GET", self._repo(repo))
        except ForgeError as e:
            return False, f"{e} (check [guide] repository, forge_url and forge_token)"
        return True, f"{repo} on {self.url}"

    def issues(self, repo: str, label: str, limit: int = 12) -> list[dict]:
        """{number, title, state (open|closed), date, labels, body}, newest first."""
        found = self._call("GET", f"{self._repo(repo)}/issues",
                           params={"state": "all", "type": "issues", "labels": label, "limit": limit}) or []
        found = sorted(found, key=lambda i: i.get("created_at") or "", reverse=True)[:limit]
        return [{"number": i["number"], "title": i["title"], "state": (i.get("state") or "").lower(),
                 "date": (i.get("created_at") or "")[:10], "labels": [lab["name"] for lab in i.get("labels") or []],
                 "body": i.get("body") or ""} for i in found]

    def issue_body(self, repo: str, number: int) -> str:
        return (self._call("GET", f"{self._repo(repo)}/issues/{int(number)}") or {}).get("body") or ""

    def close_issue(self, repo: str, number: int, comment: str) -> None:
        self._call("POST", f"{self._repo(repo)}/issues/{int(number)}/comments", json_body={"body": comment})
        self._call("PATCH", f"{self._repo(repo)}/issues/{int(number)}", json_body={"state": "closed"})

    def download_artifact(self, repo: str, run_id: str, name: str, dest: Path) -> None:
        """The artifact `name` of the Actions run `run_id`, unzipped into `dest` (Gitea 1.23 or later)."""
        listed = self._call("GET", f"{self._repo(repo)}/actions/runs/{int(run_id)}/artifacts") or {}
        match = [a for a in listed.get("artifacts") or [] if a.get("name") == name]
        if not match:
            raise ForgeError(f"Gitea: no artifact {name!r} in the run {run_id} of {repo}")
        data = self._call("GET", f"{self._repo(repo)}/actions/artifacts/{int(match[0]['id'])}/zip", raw=True)
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for member in z.infolist():
                target = (dest / member.filename).resolve()
                if not target.is_relative_to(dest.resolve()):  # a name with ../ never writes outside dest
                    raise ForgeError(f"Gitea: the artifact {name!r} holds a path outside its folder")
            z.extractall(dest)

    def open_pull_request(self, repo: str, *, base: str, head: str, title: str, body: str, cwd: Path) -> str:
        pr = self._call("POST", f"{self._repo(repo)}/pulls",
                        json_body={"base": base, "head": head, "title": title, "body": body})
        return pr.get("html_url") or f"{self.url}/{repo}/pulls/{pr['number']}"

    def pull_request_state(self, url: str) -> str:
        """open, merged or closed, from the pull request's web address (…/owner/name/pulls/N)."""
        m = re.search(r"/([^/]+)/([^/]+)/pulls/(\d+)/?$", urlsplit(url).path)
        if not m:
            raise ForgeError(f"Gitea: {url} is not a pull request address")
        pr = self._call("GET", f"{self._repo(m.group(1) + '/' + m.group(2))}/pulls/{m.group(3)}") or {}
        if pr.get("merged"):
            return "merged"
        return (pr.get("state") or "").lower()


def for_guide(guide) -> Forge:
    """The forge the manifest names ([guide] forge, forge_url, forge_token): GitHub unless it says gitea."""
    if getattr(guide, "forge", "github") == "gitea":
        return Gitea(guide.forge_url, guide.forge_token or "env:GITEA_TOKEN")
    return GitHub()


_forge: Forge = GitHub()


def get() -> Forge:
    return _forge


def use(forge: Forge) -> None:
    """Replaces the forge (tests, or another forge than GitHub)."""
    global _forge
    _forge = forge
