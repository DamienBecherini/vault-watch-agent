"""What a candidate is, read where it lives, no model (ROADMAP D1): the public API of Hugging Face for a model page
(licence, parameters, context, GGUF, downloads, dates), the one of GitHub for a repository (licence, stars, latest
release, contributors, last push). Read when a candidate is added and when the editor asks again (« Read again »
on the page), kept in the candidate (`facts`, one entry per address read, with the day it was read), so that the
editor and the reviewer of the registry see what it is without opening it.

    errors = enrich(candidate, today="2026-11-26", readers=("huggingface", "github"))
    # candidate["facts"] = [{url, read, source, licence, …}]

Only the readers the guide names are used (`[watch] candidate_readers`, none by default: a guide of cooking has no
use for Hugging Face); each is an entry of READERS. An address none of them can tell about is not read. A failure (a
gated or removed model, GitHub's limit of 60 requests an hour without a token) is said, and the facts read before
are kept.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from . import collect

# The reader of an address (collect.http_get): replaced in the tests, which never reach the network
GET: Callable = collect.http_get
_HF = re.compile(r"^/(?!datasets/|spaces/|docs/|blog/|papers/|collections/|models/|api/)([^/]+/[^/]+?)/?$")
_GH = re.compile(r"^/([^/]+)/([^/]+?)(?:\.git)?(?:/.*)?$")
_GH_NOT_REPOS = ("orgs", "users", "topics", "search", "marketplace", "sponsors", "features", "settings", "apps")


def huggingface(repo: str, get: Callable | None = None) -> dict:
    """A model of Hugging Face as its API says it; its context from its config.json when it is readable."""
    get = get or GET
    m = get(f"https://huggingface.co/api/models/{repo}", as_json=True)
    tags = m.get("tags") or []
    card = m.get("cardData") or {}
    out = {"source": "huggingface", "repo": m.get("id") or repo,
           "licence": card.get("license") or next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), ""),
           "params": (m.get("safetensors") or {}).get("total"),
           "gguf": "gguf" in tags or any(str(s.get("rfilename", "")).endswith(".gguf") for s in m.get("siblings") or []),
           "task": m.get("pipeline_tag") or "", "downloads": m.get("downloads"), "likes": m.get("likes"),
           "gated": bool(m.get("gated")), "created": (m.get("createdAt") or "")[:10],
           "updated": (m.get("lastModified") or "")[:10]}
    if not out["gated"]:
        try:
            cfg = get(f"https://huggingface.co/{repo}/resolve/main/config.json", as_json=True)
            text = cfg.get("text_config") or {}
            out["context"] = cfg.get("max_position_embeddings") or text.get("max_position_embeddings")
        except (RuntimeError, ValueError, AttributeError):
            pass  # no config.json (a GGUF-only repository): no context said
    return {k: v for k, v in out.items() if v not in (None, "", False)}


def github(repo: str, get: Callable | None = None, token: str = "") -> dict:
    """A repository of GitHub as its API says it: licence, stars, its latest release, its contributors (100 at most
    counted: « 100+ » beyond), its last push, archived or not."""
    get = get or GET
    api = f"https://api.github.com/repos/{repo}"
    r = get(api, as_json=True, github=True, token=token)
    out = {"source": "github", "repo": r.get("full_name") or repo, "licence": (r.get("license") or {}).get("spdx_id") or "",
           "stars": r.get("stargazers_count"), "archived": bool(r.get("archived")),
           "description": (r.get("description") or "")[:200], "created": (r.get("created_at") or "")[:10],
           "pushed": (r.get("pushed_at") or "")[:10]}
    try:
        rel = get(f"{api}/releases/latest", as_json=True, github=True, token=token)
        out["release"], out["released"] = rel.get("tag_name") or "", (rel.get("published_at") or "")[:10]
    except (RuntimeError, ValueError):
        pass  # no release (HTTP 404)
    try:
        people = get(f"{api}/contributors?per_page=100", as_json=True, github=True, token=token)
        out["contributors"] = "100+" if len(people) >= 100 else len(people)
    except (RuntimeError, ValueError, TypeError):
        pass
    return {k: v for k, v in out.items() if v not in (None, "", False)}


@dataclass(frozen=True)
class Reader:
    """A place a candidate can be read (asked by the user, 2026-11-26: Hugging Face and GitHub fit a guide of AI or
    software, not every guide; a guide names the readers it wants, `[watch] candidate_readers`)."""
    label: str                                         # as the page names it
    place: Callable[[str], str | None]                 # what it reads at an address (its id there), or None
    read: Callable[[str, Callable | None, str | None], dict]  # (id, get, token): the facts
    kind: str                                          # the kind its addresses are, when the guide has it


def _hf_place(url: str) -> str | None:
    parts = urlsplit(url or "")
    m = _HF.match(parts.path) if parts.netloc.lower().removeprefix("www.") in ("huggingface.co", "hf.co") else None
    return m.group(1) if m else None


def _gh_place(url: str) -> str | None:
    parts = urlsplit(url or "")
    m = _GH.match(parts.path) if parts.netloc.lower().removeprefix("www.") == "github.com" else None
    return f"{m.group(1)}/{m.group(2)}" if m and m.group(1) not in _GH_NOT_REPOS else None


# The readers a guide can name, in the order it names them. Another one (PyPI, npm, Docker Hub…) is an entry here
READERS: dict[str, Reader] = {
    "huggingface": Reader("Hugging Face", _hf_place, lambda repo, get, token: huggingface(repo, get), "model"),
    "github": Reader("GitHub", _gh_place,
                     lambda repo, get, token: github(repo, get, collect.github_token() if token is None else token),
                     "tool"),
}


def readers_of(watch) -> tuple[str, ...]:
    """The readers a guide names ([watch] candidate_readers); none when it names none: nothing is read."""
    return tuple(getattr(watch, "candidate_readers", ()) or ())


def where(url: str, readers: tuple[str, ...] | list[str] = tuple(READERS)) -> tuple[str, str] | None:
    """(reader, id) for an address one of `readers` can tell about, as ("huggingface", "org/model") or ("github",
    "owner/repo"); else None."""
    for name in readers:
        if name in READERS and (found := READERS[name].place(url)):
            return name, found
    return None


def guess_kind(url: str, kinds: tuple[str, ...], readers: tuple[str, ...]) -> str:
    """The kind an address says, among the guide's, through its readers: a Hugging Face model page a model, a GitHub
    repository a tool; else « other » (the editor corrects it on the page)."""
    place = where(url, readers)
    kind = READERS[place[0]].kind if place else ""
    return kind if kind in kinds else "other"


def read(place: tuple[str, str], get: Callable | None, token: str | None) -> dict:
    """The facts of one address `where` placed; the token of GitHub found only when GitHub is asked."""
    return READERS[place[0]].read(place[1], get, token)


def enrich(candidate: dict, *, today: str, readers: tuple[str, ...], get: Callable | None = None,
           token: str | None = None, at: str = "") -> list[str]:
    """The facts of each address of `candidate` that one of the guide's `readers` can tell about, read again
    (`facts`, in the order of its sources; what could not be read, or no reader of the guide reads any more, keeps its
    facts of before), each with when it was read (`read`: `today` and the time, or `at`). Returns what failed, as
    « address: why »."""
    stamp = at or f"{today} {datetime.now():%H:%M}"
    known = {f["url"]: f for f in candidate.get("facts", [])}
    facts, errors = [], []
    for s in candidate.get("sources", []):
        url = s.get("url", "")
        if any(f["url"] == url for f in facts):
            continue
        place = where(url, readers)
        if not place:
            if url in known:
                facts.append(known[url])
            continue
        try:
            facts.append({"url": url, "read": stamp, **read(place, get, token)})
        except (RuntimeError, ValueError, AttributeError) as e:
            errors.append(f"{url}: {e}")
            if url in known:
                facts.append(known[url])
    if facts or "facts" in candidate:
        candidate["facts"] = facts
    return errors
