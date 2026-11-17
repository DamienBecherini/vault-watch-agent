"""Inputs of a run: the watch collected by the guide's own tooling, and its checks.

The guide's collector (for the IA on-prem guide, a weekly GitHub workflow) already did the deterministic
pre-triage and cached release notes and advisory texts in `watch.json`; its `claims_due` check lists the claims
past their "Recheck by" date. This module only fetches and normalises them, and runs the commands of `[checks]`.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path

NOTES_MAX = 4000  # the watch script already caps notes around this size


def run(cmd: list[str], cwd: Path | None = None) -> str:
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=False)
    if done.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed ({done.returncode}): {done.stderr.strip()[:500]}")
    return done.stdout


def download_watch(issue: int, repo: str, cache: Path, artifact: str = "weekly-watch") -> Path:
    """Find the workflow run linked at the bottom of the issue and download its artifact."""
    body = run(["gh", "issue", "view", str(issue), "--repo", repo, "--json", "body", "--jq", ".body"])
    match = re.search(r"/actions/runs/(\d+)", body)
    if not match:
        raise RuntimeError(f"issue #{issue}: no workflow run link in the body")
    target = cache / f"run-{match.group(1)}"
    if not (target / "watch.json").is_file():
        target.mkdir(parents=True, exist_ok=True)
        run(["gh", "run", "download", match.group(1), "--repo", repo, "-n", artifact, "-D", str(target)])
    return target / "watch.json"


def load_items(watch_json: Path) -> tuple[list[dict], str]:
    """Kept items with a run-local id, urgent advisories first; returns (items, window end)."""
    data = json.loads(watch_json.read_text(encoding="utf-8"))
    kept = [i for i in data["items"] if i.get("triage") == "keep"]
    kept.sort(key=lambda i: not i.get("urgent"))
    items = [
        {
            "id": f"W{n}",
            "domain": i.get("domain", ""),
            "tier": i.get("tier", ""),
            "title": i.get("title", ""),
            "url": i.get("url", ""),
            "date": (i.get("date") or "")[:10],
            "urgent": bool(i.get("urgent")),
            "severity": i.get("severity") or "",
            "notes": (i.get("notes") or i.get("summary") or "")[:NOTES_MAX],
        }
        for n, i in enumerate(kept, start=1)
    ]
    return items, data.get("until", "")


def check(key: str, cwd: Path, out: Path | None = None) -> str | None:
    """Run the guide's own command `key` of [checks] (audits, claims_due, sources) in `cwd`, a copy of the guide;
    `{out}` in it becomes `out`. None when the guide declares no such command: the step is not checked.
    RuntimeError when the command fails."""
    from .vault import guide_of  # vault imports this module

    command = getattr(guide_of(cwd), key)
    if not command:
        return None
    args = [a.replace("{out}", str(out)) for a in shlex.split(command)]
    args[0] = shutil.which(args[0]) or args[0]  # npm, npx are .cmd files on Windows
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
    return run(args, cwd=cwd)


def claims_due(vault: Path, out: Path) -> list[dict]:
    """Watchlist claims whose "Recheck by" date has passed (the guide's `claims_due`, no network); none when the
    guide has no such check."""
    if check("claims_due", vault, out) is None:
        return []
    return json.loads(out.read_text(encoding="utf-8")).get("claimsDue", [])
