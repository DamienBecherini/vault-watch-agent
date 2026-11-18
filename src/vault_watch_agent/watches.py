"""Where a guide's watches come from, as its manifest says (`[watch] source`): GitHub issues, `watch.json` files, or
none. Each source lists its watches for the interface and fetches one as a local `watch.json` (docs/watch-format.md).

    src = watches.of(guide, home)
    src.list()            # [{id, thread, kind, title, date, state, urgent, items}], newest first
    src.fetch("77")       # Path of the watch.json of issue #77 (downloaded) or of a file of the guide
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Protocol

from . import forge, inputs
from .guide import Guide


class WatchSource(Protocol):
    kind: str

    def list(self) -> list[dict]: ...
    def fetch(self, watch_id: str) -> Path: ...


class Issues:
    """GitHub issues with the manifest's label; the watch is the artifact of the workflow run each one links to."""

    kind = "issue"

    def __init__(self, repo: str, label: str, artifact: str, cache: Path,
                 issues: Callable[[], list[dict]] | None = None):
        self.repo, self.label, self.artifact, self.cache = repo, label or "veille", artifact or "weekly-watch", cache
        self._issues = issues  # the interface's tests give their own list

    def list(self) -> list[dict]:
        if self._issues is not None:
            found = self._issues()
        elif not self.repo:
            found = []
        else:
            found = [{"number": i["number"], "title": i["title"], "state": i["state"], "date": i["date"],
                      "urgent": "urgent" in i["labels"],
                      "items": int(m.group(1)) if (m := re.search(r"(\d+) (?:éléments|items)\b", i["title"])) else None}
                     for i in forge.get().issues(self.repo, self.label)]
        return [{**i, "id": str(i["number"]), "thread": f"issue-{i['number']}", "kind": self.kind} for i in found]

    def fetch(self, watch_id: str) -> Path:
        return inputs.download_watch(int(watch_id), self.repo, self.cache, self.artifact)


class Files:
    """A `watch.json` of the guide, or a folder of them (one per watch, the newest window first)."""

    kind = "file"

    def __init__(self, root: Path, path: str):
        self.root, self.path = root, path

    def _files(self) -> list[Path]:
        target = self.root / self.path
        if target.is_dir():
            return sorted(target.glob("*.json"), key=lambda p: p.name, reverse=True)
        return [target] if target.is_file() else []

    def list(self) -> list[dict]:
        out = []
        for path in self._files():
            try:
                data = inputs.check_watch(json.loads(path.read_text(encoding="utf-8")), path.name)
            except (OSError, ValueError) as e:  # WatchError is a ValueError: listed, with what is wrong
                out.append({"id": path.relative_to(self.root).as_posix(), "thread": path.stem, "kind": self.kind,
                            "title": path.name, "date": "", "state": "open", "urgent": False, "items": None,
                            "error": str(e)})
                continue
            kept = [i for i in data["items"] if i.get("triage") == "keep"]
            out.append({"id": path.relative_to(self.root).as_posix(), "thread": path.stem, "kind": self.kind,
                        "title": f"{path.name} ({data.get('since', '…')} → {data['until']})", "date": data["until"],
                        "state": "open", "urgent": any(i.get("urgent") for i in kept), "items": len(kept)})
        return out

    def fetch(self, watch_id: str) -> Path:
        path = (self.root / watch_id).resolve()
        if self.root.resolve() not in path.parents or path not in [p.resolve() for p in self._files()]:
            raise ValueError(f"{watch_id}: not a watch of this guide")
        return path


class Nothing:
    kind = "none"

    def list(self) -> list[dict]:
        return []

    def fetch(self, watch_id: str) -> Path:
        raise ValueError("this guide declares no watch ([watch] source = \"none\")")


def of(guide: Guide, home: Path, issues: Callable[[], list[dict]] | None = None) -> WatchSource:
    """The source the manifest declares; `issues` replaces the forge's list (the interface's tests)."""
    w = guide.watch
    if w.source == "github-issue":
        return Issues(guide.repository, w.label, w.artifact, home / "downloads", issues)
    if w.source == "file":
        return Files(guide.root, w.path)
    return Nothing()
