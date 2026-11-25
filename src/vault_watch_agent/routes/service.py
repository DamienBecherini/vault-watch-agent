"""The server itself: its health for the launcher, what the page shows of the agent and the guide (and sends with
« Give my opinion »), the costs of the runs, and the explanations of a pause in the page's language."""

from __future__ import annotations

import platform
import re

from fastapi import APIRouter
from pydantic import BaseModel

from .. import __version__, costs, explain, forge, llm
from .. import config as user_settings
from .context import AppContext

AGENT_REPO = "https://github.com/DamienBecherini/vault-watch-agent"
# Where « Give my opinion » sends a mail (the reader's own mail program does; no account needed). Empty: the window
# offers the issue and the copy only.
FEEDBACK_EMAIL = "vault-watch@damien.becherini.fr"
# What a running job is doing, in the health response.
ACTIVITIES = {"run": "analysing", "review": "applying the review", "publish": "publishing", "fix": "fixing", "resume": "resuming",
              "sources": "checking the sources", "mirror": "syncing the languages", "retouch": "after the retouches",
              "translation": "after the review of the translation", "proofread": "proofreading the edits",
              "proofread-review": "after the review of the proofreading"}


class Explain(BaseModel):
    texts: list[str]  # the English lines a pause shows: the models' explanations, the checks' findings
    lang: str  # the language of the page
    thread: str = ""  # the run (or check) they belong to: its line in the cost journal


def version() -> str:
    """The version of the code that runs (the source, not the copy an install may have left in site-packages)."""
    return __version__


def forge_repo_url(ctx: AppContext) -> str:
    """The repository's web page on its forge ("" for a local guide)."""
    if not ctx.settings.repo:
        return ""
    base = ctx.guide.forge_url if ctx.guide.forge == "gitea" else "https://github.com"
    return f"{base}/{ctx.settings.repo}"


def router(ctx: AppContext) -> APIRouter:
    api = APIRouter()
    settings = ctx.settings

    @api.get("/api/health")
    def health():
        """The "local service" contract (v2) shared with the launcher: state, busy or not, idle countdown."""
        running = [j for j in list(ctx.jobs.values()) if not j.done]
        idle = ctx.app.state.idle_seconds()
        remaining = None if running or not settings.idle_exit else round(max(0.0, settings.idle_exit - idle), 1)
        return {"state": "ready", "contract": 2, "service": "vault-watch", "version": version(),
                "busy": bool(running), "activity": ACTIVITIES.get(running[0].action, running[0].action) if running else "",
                "remaining_work_s": None, "idle": {"timeout_s": settings.idle_exit, "remaining_s": remaining}}

    @api.get("/api/info")
    def info():
        return {"repo": settings.repo, "site": settings.site, "agent": AGENT_REPO, "engine": ctx.engine_now(),
                # for a report sent from the page (« Give my opinion »): nothing of the guide, nothing of the machine
                "system": platform.system(), "python": platform.python_version(), "feedback_email": FEEDBACK_EMAIL,
                "billing": ctx.billing_now(),
                "guide": ctx.guide.name, "watch_source": ctx.guide.watch.source, "forge": forge.get().name,
                "repo_url": forge_repo_url(ctx),
                "version": version()}

    @api.get("/api/costs")
    def costs_view():
        entries = costs.load(settings.journal)
        return {**{by: costs.rows(entries, by) for by in ("month", "run")}, "origins": costs.origins(entries)}

    @api.post("/api/explain")
    def explain_lines(body: Explain):
        """The explanations of a pause in the page's language (explain.py): {lines: {english: translated}}. One call
        of the translator's model for the lines not translated yet; none in English. A model that fails leaves the
        lines in English (`error`): the pause works the same."""
        lang = body.lang.lower() if re.fullmatch(r"[a-zA-Z]{2}", body.lang or "") else ""
        if lang in ("", "en") or not body.texts:
            return {"lines": {}}
        label = body.thread if re.fullmatch(r"[\w.-]{1,80}", body.thread or "") else "explain"
        try:
            deps = settings.make_deps(label, "explain")
            found, _ = explain.lines([t[:2000] for t in body.texts[:200]], lang, deps.translator or deps.llm, settings.home)
        except (user_settings.ConfigError, llm.ModelError) as e:
            return {"lines": {}, "error": f"{type(e).__name__}: {e}"[:300]}
        return {"lines": found}

    return api
