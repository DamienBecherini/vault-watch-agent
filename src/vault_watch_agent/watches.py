"""Where a guide's watches come from, as its manifest says (`[watch] source`): GitHub issues, `watch.json` files, the
agent's own collection from the guide's feeds, or none. Each source lists its watches for the interface and fetches
one as a local `watch.json` (docs/watch-format.md).

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
            return sorted(target.glob("*.json"), key=lambda p: p.stem, reverse=True)  # watch-x-2 after watch-x
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


class Collected(Files):
    """The watches `vault-watch collect` wrote in the guide's working folder (`watches/`), from its feeds.json."""

    kind = "feeds"
    FOLDER = "watches"

    def __init__(self, guide: Guide, home: Path):
        super().__init__(home, self.FOLDER)
        self.guide = guide

    def collect(self, **kw) -> Path:
        """Reads the feeds now and writes the watch (`watches/watch-<until>.json`, `-2`… when one is already there)."""
        from . import collect

        watch = collect.Collector.of_guide(self.guide).collect(**kw)
        return write(watch, self.root / self.FOLDER)


def write(watch: dict, folder: Path) -> Path:
    """`watch-<until>.json` in `folder`, never over an existing one (a run may have read it)."""
    folder.mkdir(parents=True, exist_ok=True)
    path, n = folder / f"watch-{watch['until']}.json", 1
    while path.exists():
        n += 1
        path = folder / f"watch-{watch['until']}-{n}.json"
    path.write_text(json.dumps(watch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
    if w.source == "issues":
        return Issues(guide.repository, w.label, w.artifact, home / "downloads", issues)
    if w.source == "file":
        return Files(guide.root, w.path)
    if w.source == "feeds":
        return Collected(guide, home)
    return Nothing()
