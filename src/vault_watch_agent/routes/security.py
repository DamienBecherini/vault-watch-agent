"""Local only: who may use the server, and the headers of what it answers.

Only the page of the agent, in the editor's own browser, may use the server. Another site the editor visits (or a
note rendered by Obsidian) can make the browser send requests here: it is refused when the browser says so
(Sec-Fetch-Site, Origin), and every request of the API must carry X-Vault-Watch, a header no other site can set
without a preflight the server never answers. A GET included (an <img> once asked /api/models to try a key at an
address of its own: the key was sent there). Exempt: what the browser asks by itself, without a header: the probes,
the stream of a run (EventSource), the report opened in a tab.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse

from .context import AppContext

WITHOUT_HEADER = re.compile(r"/api/(health|notices|runs/[A-Za-z0-9._-]+/(events|report))")
PROBES = ("/api/health", "/api/notices")  # a page left open is not someone using it
STATIC = Path(__file__).resolve().parent.parent / "static"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def page_version() -> str:
    """The version of the page: it changes with any of its files (name, date, size). The page is served with it
    (web.index: ?v=… on its scripts, and a <meta>), and each answer of the API says it (X-Vault-Watch-Page): a page
    opened before the server was updated sees it and asks to be reloaded, instead of showing what its old scripts
    know (api.js)."""
    files = sorted(p for p in STATIC.iterdir() if p.is_file())
    return hashlib.sha1("".join(f"{p.name}{p.stat().st_mtime_ns}{p.stat().st_size}" for p in files).encode()).hexdigest()[:10]


def local_hosts() -> tuple[str, ...]:
    """The Host headers accepted (no DNS rebinding); the test client's too, under pytest."""
    return ("127.0.0.1", "localhost") + (("testserver",) if "PYTEST_CURRENT_TEST" in os.environ else ())


def refused(why: str) -> JSONResponse:
    return JSONResponse({"detail": why}, status_code=403)


def refusal(request: Request, hosts: tuple[str, ...]) -> str:
    """Why a request is refused ("" when it may go on)."""
    path = request.url.path
    if (request.headers.get("host") or "").split(":")[0] not in hosts:
        return "local access only"
    # The API only: the page itself may be opened from a link anywhere (a mail, a chat, Obsidian), which the
    # browser marks as coming from another site; opening it does nothing, and its scripts call the API from here
    if path.startswith("/api/") or request.method != "GET":
        if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
            return "a request from another site"
        origin = request.headers.get("origin")
        if origin and origin.split("://")[-1].split(":")[0] not in hosts:
            return "a request from another site"
    mine = request.headers.get("x-vault-watch") == "1"
    if not mine and (request.method != "GET" or path.startswith("/api/") and not WITHOUT_HEADER.fullmatch(path)):
        return "missing X-Vault-Watch header"
    return ""


def install(ctx: AppContext) -> None:
    """Puts the check of each request, and the headers of each answer, on the app."""
    hosts = local_hosts()

    @ctx.app.middleware("http")
    async def local_only(request: Request, call_next):
        why = refusal(request, hosts)
        if why:
            return refused(why)
        path = request.url.path
        if path not in PROBES:
            ctx.touch()
        response = await call_next(request)
        if path == "/" or path.startswith("/static/"):
            # The page and its scripts go together: the browser asks again each time (a 304 when nothing changed),
            # so an update never leaves an old page with new scripts.
            response.headers["Cache-Control"] = "no-cache"
        if path.startswith("/api/"):
            response.headers["X-Vault-Watch-Page"] = page_version()
        # Never in a frame of another site (a click lured onto « Publish »), only its own scripts, no sniffing
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = CSP
        return response
