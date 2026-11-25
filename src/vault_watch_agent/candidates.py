"""The discovery registry (ROADMAP D3, decided with the user on 2026-11-25): what the agent found that the guide does
not cover yet, followed over time instead of triaged once.

A candidate is a model, a tool, a piece of hardware or something else, known by its name and by the addresses where
it was seen. It moves through states, each change kept in its history:

    lead → watching → confirmed → proposed → added          or dismissed, with a reason and a date to look again

The registry is a JSON file of the guide, the one its manifest names (`[watch] candidates`), so that the weekly
collection, which runs where the guide is (its CI), knows it too: it drops the addresses of the candidates it
tracks (as it drops those of `seen`) and lists those whose date to look again has passed (collect.py).

    reg = Registry.load(path)
    c, new = reg.note("Reflection Beam 501B", "https://…", origin="watch issue-30", seen="2026-10-10", kind="model")
    reg.move(c["id"], "watching", reason="weights announced for later", recheck="2026-12-01", today="2026-11-25")
    reg.save()

No model here: a name is matched by its normalised form, an address by its canonical form.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

SCHEMA = 1
STATES = ("lead", "watching", "confirmed", "proposed", "added", "dismissed")
KINDS = ("model", "tool", "hardware", "other")
LOOK_AGAIN = ("watching", "dismissed")  # the states a date to look again applies to
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class RegistryError(ValueError):
    """The registry cannot be read or a change to it is refused: said to the editor as it is."""


def key(name: str) -> str:
    """The normalised form of a name: « Reflection Beam 501B-A23B » and « reflection-beam-501b-a23b » are one."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def canonical(url: str) -> str:
    """An address as the registry compares it: no scheme case, no « www. », no trailing slash, no fragment; the query
    kept (a page may be one by its query)."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    return urlunsplit((parts.scheme.lower() or "https", host, parts.path.rstrip("/"), parts.query, ""))


def _date(value: str, what: str) -> str:
    if not _DATE.fullmatch(value or ""):
        raise RegistryError(f"{what}: a date as YYYY-MM-DD, not {value!r}")
    return value


@dataclass
class Registry:
    path: Path
    candidates: list[dict] = field(default_factory=list)

    # -- the file -------------------------------------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path) -> Registry:
        """The registry of `path`; empty when the file does not exist yet."""
        if not path.is_file():
            return cls(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise RegistryError(f"{path.name}: {e}") from e
        if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("candidates"), list):
            raise RegistryError(f"{path.name}: not a registry of candidates (schema {SCHEMA}, a list `candidates`)")
        return cls(path, data["candidates"])

    def save(self) -> None:
        """Written sorted by state then name, two spaces, one line per source: a diff a reviewer can read."""
        order = {s: i for i, s in enumerate(STATES)}
        self.candidates.sort(key=lambda c: (order.get(c.get("state") or "", 99), key(c.get("name", ""))))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"schema": SCHEMA, "candidates": self.candidates}, ensure_ascii=False, indent=2)
        self.path.write_text(text + "\n", encoding="utf-8", newline="\n")

    # -- reading --------------------------------------------------------------------------------------------------
    def get(self, cid: str) -> dict:
        for c in self.candidates:
            if c["id"] == cid:
                return c
        raise RegistryError(f"no candidate {cid!r}")

    def find(self, name: str = "", url: str = "") -> dict | None:
        """The candidate seen at `url`, else the one of that name (normalised), else None."""
        if url:
            where = canonical(url)
            for c in self.candidates:
                if any(canonical(s["url"]) == where for s in c.get("sources", [])):
                    return c
        k = key(name) if name else ""
        return next((c for c in self.candidates if k and c["id"] == k), None)

    def urls(self) -> set[str]:
        """Every address a candidate was seen at, canonical: what the collection no longer proposes."""
        return {canonical(s["url"]) for c in self.candidates for s in c.get("sources", [])}

    def due(self, today: str) -> list[dict]:
        """The candidates whose date to look again has come, the oldest date first."""
        return sorted((c for c in self.candidates if c.get("state") in LOOK_AGAIN and c.get("recheck")
                       and c["recheck"] <= today), key=lambda c: c["recheck"])

    # -- changes --------------------------------------------------------------------------------------------------
    def note(self, name: str, url: str = "", *, origin: str, seen: str, kind: str = "other",
             title: str = "") -> tuple[dict, bool]:
        """A candidate seen once more: its source added (an address not known yet) and its last date moved, or a new
        candidate in state `lead`. (candidate, True when it is new)."""
        _date(seen, "seen")
        if kind not in KINDS:
            raise RegistryError(f"kind {kind!r}: one of {', '.join(KINDS)}")
        found = self.find(name, url)
        source = {"url": url, "seen": seen, "origin": origin, **({"title": title} if title else {})}
        if found:
            known = {canonical(s["url"]) for s in found.get("sources", [])}
            if url and canonical(url) not in known:
                found.setdefault("sources", []).append(source)
            found["last_seen"] = max(found.get("last_seen", seen), seen)
            return found, False
        cid = key(name)
        if not cid:
            raise RegistryError("a candidate needs a name")
        if any(c["id"] == cid for c in self.candidates):  # pragma: no cover - find() matched it by name
            raise RegistryError(f"{cid!r} already exists")
        c = {"id": cid, "name": name.strip(), "kind": kind, "state": "lead", "reason": "", "recheck": "",
             "first_seen": seen, "last_seen": seen, "sources": [source] if url else [],
             "history": [{"date": seen, "state": "lead", "note": f"seen: {origin}"}]}
        self.candidates.append(c)
        return c, True

    def move(self, cid: str, state: str, *, today: str, reason: str = "", recheck: str = "") -> dict:
        """A candidate to another state. Dismissing needs a reason; a date to look again applies to `watching` and
        `dismissed` only, and is cleared by any other state."""
        if state not in STATES:
            raise RegistryError(f"state {state!r}: one of {', '.join(STATES)}")
        _date(today, "today")
        if state == "dismissed" and not reason.strip():
            raise RegistryError("a dismissed candidate needs a reason")
        if recheck:
            if state not in LOOK_AGAIN:
                raise RegistryError(f"a date to look again applies to {' or '.join(LOOK_AGAIN)}, not {state}")
            if _date(recheck, "recheck") <= today:
                raise RegistryError(f"the date to look again ({recheck}) is not after today ({today})")
        c = self.get(cid)
        c["state"], c["reason"] = state, reason.strip() or (c.get("reason", "") if state == c.get("state") else "")
        c["recheck"] = recheck if state in LOOK_AGAIN else ""
        c.setdefault("history", []).append({"date": today, "state": state, "note": reason.strip(),
                                            **({"recheck": recheck} if recheck else {})})
        return c
