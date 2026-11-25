"""What a candidate is, read where it lives, no model (ROADMAP D1): the public API of Hugging Face for a model page
(licence, parameters, context, GGUF, downloads, dates), the one of GitHub for a repository (licence, stars, latest
release, contributors, last push). Read when a candidate is added and when the editor asks again (« Read again »
on the page), kept in the candidate (`facts`, one entry per address read, with the day it was read), so that the
editor and the reviewer of the registry see what it is without opening it.

    errors = enrich(candidate, today="2026-11-26")   # candidate["facts"] = [{url, read, source, licence, …}]

An address that is neither a Hugging Face model nor a GitHub repository is not read. A failure (a gated or removed
model, GitHub's limit of 60 requests an hour without a token) is said, and the facts read before are kept.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlsplit

from . import collect

# The reader of an address (collect.http_get): replaced in the tests, which never reach the network
GET: Callable = collect.http_get
_HF = re.compile(r"^/(?!datasets/|spaces/|docs/|blog/|papers/|collections/|models/|api/)([^/]+/[^/]+?)/?$")
_GH = re.compile(r"^/([^/]+)/([^/]+?)(?:\.git)?(?:/.*)?$")
_GH_NOT_REPOS = ("orgs", "users", "topics", "search", "marketplace", "sponsors", "features", "settings", "apps")


def where(url: str) -> tuple[str, str] | None:
    """("huggingface", "org/model") or ("github", "owner/repo") for an address these two can tell about; else None."""
    parts = urlsplit(url or "")
    host = parts.netloc.lower().removeprefix("www.")
    if host in ("huggingface.co", "hf.co") and (m := _HF.match(parts.path)):
        return "huggingface", m.group(1)
    if host == "github.com" and (m := _GH.match(parts.path)) and m.group(1) not in _GH_NOT_REPOS:
        return "github", f"{m.group(1)}/{m.group(2)}"
    return None


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


def read(place: tuple[str, str], get: Callable | None, token: str | None) -> dict:
    """The facts of one address `where` placed; the token of GitHub found only when GitHub is asked."""
    if place[0] == "huggingface":
        return huggingface(place[1], get)
    return github(place[1], get, collect.github_token() if token is None else token)


def enrich(candidate: dict, *, today: str, get: Callable | None = None, token: str | None = None,
           at: str = "") -> list[str]:
    """The facts of each address of `candidate` that Hugging Face or GitHub can tell about, read again (`facts`, in
    the order of its sources; what could not be read keeps its facts of before), each with when it was read (`read`:
    `today` and the time, or `at`). Returns what failed, as « address: why »."""
    stamp = at or f"{today} {datetime.now():%H:%M}"
    known = {f["url"]: f for f in candidate.get("facts", [])}
    facts, errors = [], []
    for s in candidate.get("sources", []):
        url, place = s.get("url", ""), where(s.get("url", ""))
        if not place or any(f["url"] == url for f in facts):
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
