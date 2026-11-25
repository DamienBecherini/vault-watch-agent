"""Local web interface: the same graph as the command line, driven from a browser.

    vault-watch serve                 # http://127.0.0.1:4430/

Each pause of the graph is a screen: the watches, a run in progress, the review
(one card per correction), the publish step, then the pull request. Runs are
checkpointed in the same SQLite file as the CLI, so a run started here can be
resumed from the command line and the other way round.

Model calls take minutes: they run in a background thread per run, and the page
follows them through server-sent events. The server listens on 127.0.0.1 only;
requests that change something must carry the `X-Vault-Watch` header, which a
foreign web page cannot send without a CORS preflight this server never grants,
and the Host header must be local (no DNS rebinding).

This module makes the app; its routes are in routes/, one module per area of the
page, each given the app's context (routes/context.py) that they share.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import watches as watches_mod
from .routes import chapters, checks, languages, notices, pauses, runs, security, service, sources, todo
from .routes import settings as settings_routes
from .routes.chapters import Chapters, Propose
from .routes.checks import NOTE_CHARS, Handle, LeadNote, Verification
from .routes.context import AppContext, Job, Settings, gh_pr_state, read_json, write_json
from .routes.languages import Accept, MirrorCheck, MirrorSync
from .routes.pauses import Lend, PageText, Publish, Retouch, Retouched, Review, TranslationReview
from .routes.runs import STEPS, Analyse, Report
from .routes.service import ACTIVITIES, AGENT_REPO, FEEDBACK_EMAIL, Explain
from .routes.settings import STEP_EFFORTS, UserSettings
from .routes.sources import Changes, Later

STATIC = Path(__file__).parent / "static"

# The names this module had before its routes moved to routes/: still imported from here (cli.py, the tests)
__all__ = ["ACTIVITIES", "AGENT_REPO", "FEEDBACK_EMAIL", "NOTE_CHARS", "STATIC", "STEPS", "STEP_EFFORTS", "Accept", "Analyse",
           "Changes", "Chapters", "Explain", "Handle", "Job", "Later", "LeadNote", "Lend", "MirrorCheck", "MirrorSync", "PageText",
           "Propose", "Publish", "Report", "Retouch", "Retouched", "Review", "Settings", "TranslationReview", "UserSettings",
           "Verification", "create_app", "gh_pr_state", "list_issues", "read_json", "write_json"]


def index() -> HTMLResponse:
    """The page, its scripts, style and icon named with a version (?v=…) that changes with any of them: a
    browser that kept an older copy (served before Cache-Control: no-cache) cannot mix it with the new page."""
    files = sorted(p for p in STATIC.iterdir() if p.is_file())
    version = hashlib.sha1("".join(f"{p.name}{p.stat().st_mtime_ns}{p.stat().st_size}" for p in files).encode()).hexdigest()[:10]
    text = (STATIC / "index.html").read_text(encoding="utf-8")
    text = re.sub(r'((?:src|href)="/static/[^"?]+)"', rf'\1?v={version}"', text)
    return HTMLResponse(text)


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="vault-watch", docs_url=None, redoc_url=None)
    ctx = AppContext.create(settings, app)
    ctx.announce = partial(notices.announce, ctx)
    # For `serve --idle-exit` (cli.serve) and the tests: requests count, the health probe of a supervisor does not
    app.state.last_activity = time.time()
    app.state.jobs = ctx.jobs
    app.state.idle_seconds = ctx.idle_seconds
    security.install(ctx)
    for area in (notices, service, settings_routes, todo, runs, pauses, sources, checks, languages, chapters):
        app.include_router(area.router(ctx))
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.add_api_route("/", index, methods=["GET"])
    return app


def list_issues(repo: str, label: str = "veille") -> Callable[[], list[dict]]:
    """Watch issues of the guide (the manifest's [watch] label), newest first, from the forge (watches.Issues)."""
    return lambda: watches_mod.Issues(repo, label, "", Path(".")).list()
