"""Shared fixtures: the sample guide of examples/ in a throwaway git repository."""

import shutil
import subprocess
from pathlib import Path

import pytest

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample-guide"

# What the agent still requires of a guide until M1 makes these parts optional: the list of watchlist claims due.
FRESHNESS_STUB = (
    "import { writeFileSync } from 'node:fs';\n"
    "const out = process.argv.find(a => a.startsWith('--json=')).slice(7);\n"
    "writeFileSync(out, JSON.stringify({claimsDue: []}));\n"
)


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def sample_guide(tmp_path: Path):
    """(guide, watch.json): the sample guide committed on `main` of a new repository, its watch beside it."""
    guide = tmp_path / "guide"
    shutil.copytree(SAMPLE, guide, ignore=shutil.ignore_patterns("watch.json"))
    (guide / "scripts").mkdir()
    (guide / "scripts" / "audit-freshness.mjs").write_text(FRESHNESS_STUB, encoding="utf-8")
    _git("init", "-q", "-b", "main", cwd=guide)
    _git("config", "user.name", "t", cwd=guide)
    _git("config", "user.email", "t@t", cwd=guide)
    _git("add", ".", cwd=guide)
    _git("commit", "-qm", "init", cwd=guide)
    watch = tmp_path / "watch.json"
    shutil.copy(SAMPLE / "watch.json", watch)
    return guide, watch
