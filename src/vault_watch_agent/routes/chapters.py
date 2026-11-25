"""Page « Chapters »: the chapters of the guide (chapters.py), as the agent sees them, proposed by a model, and declared
in the guide's manifest through a pull request."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import chapters as chapters_mod
from .. import forge, llm, vault, verify
from .. import guide as guide_mod
from .context import AppContext, read_json, write_json


class Chapters(BaseModel):
    chapters: list[dict] = []  # the chapters to declare: {name, paths, explore}; none: back to the automatic rule


class Propose(BaseModel):
    steps: dict = {}  # for this call alone: {"chapters": {engine, model, effort}}


def pending_file(ctx: AppContext) -> Path:
    """The pull request of the last split, until it is merged."""
    return ctx.settings.home / "chapters-pr.json"


def declared_of(rows: list[dict]) -> list:
    try:
        return list(guide_mod.chapters_of([{k: r[k] for k in ("name", "paths", "explore") if k in r} for r in rows]))
    except guide_mod.GuideError as e:
        raise HTTPException(400, str(e)) from e


def pending_split(ctx: AppContext) -> dict:
    """The pull request that declares the chapters, while it is open. Merged: the guide's folder follows its
    base branch, so that this page shows the split at once; merged or closed: forgotten."""
    try:
        pending = read_json(pending_file(ctx))
    except (OSError, ValueError):
        return {}
    state = ctx.pr_state(pending.get("pr_url", ""))
    if state not in ("merged", "closed"):
        return pending
    if state == "merged":
        try:
            vault.sync(ctx.settings.vault, ctx.guide.base_branch)
        except RuntimeError:
            pass  # the folder is not on its base branch, or offline: it follows at the next run
    pending_file(ctx).unlink(missing_ok=True)
    return {}


def router(ctx: AppContext) -> APIRouter:
    api = APIRouter()
    settings = ctx.settings

    @api.get("/api/chapters")
    def chapters_get(steps: str = ""):
        """The chapters as the agent has them now, with what a page needs to change them: what a model's proposal
        costs and runs on (`steps`: what the page chose for it), the open pull request of the last split."""
        cfg = ctx.with_steps(steps)
        pending = pending_split(ctx)
        now = vault.guide_of(settings.vault)
        return {**chapters_mod.view(settings.vault), "toml": chapters_mod.toml(now.chapters), "pending": pending,
                "usd": verify.chapters_usd(settings.vault, llm.step_model(cfg, "chapters"), ctx.price_table(cfg)),
                "step": next(s for s in ctx.steps_view(cfg) if s["step"] == "chapters"),
                "has_repo": bool(now.repository), "forge": forge.get().name, "from_manifest": now.from_manifest,
                "manifest": guide_mod.MANIFEST, "base": now.base_branch, "needs": chapters_mod.NEEDS}

    @api.post("/api/chapters/preview")
    def chapters_preview(body: Chapters):
        """What the chapters would be with these declared, and the lines of the manifest that say so. Nothing is
        written."""
        declared = declared_of(body.chapters)
        return {**chapters_mod.view(settings.vault, declared), "toml": chapters_mod.toml(declared)}

    @api.post("/api/chapters/propose")
    def chapters_propose(body: Propose):
        """A split by a model, from the outline of the guide (one call, paid): to review, nothing is written."""
        thread = time.strftime("chapters-%Y-%m-%d-%H%M%S")
        ctx.keep_steps(thread, body.steps)
        deps = settings.make_deps(thread, "verify")
        try:
            declared, why, usage = chapters_mod.propose(settings.vault, deps.llm)
        except llm.ModelError as e:
            raise HTTPException(502, str(e)[:600]) from e
        if not declared:
            raise HTTPException(502, "the model proposed no chapter that names a page of the guide")
        return {**chapters_mod.view(settings.vault, declared), "toml": chapters_mod.toml(declared), "why": why,
                "cost": round((usage or {}).get("cost_usd", 0.0), 2)}

    @api.post("/api/chapters")
    def chapters_save(body: Chapters):
        """Declares these chapters in the guide's manifest, on a branch of its own: pushed with its pull request when
        the guide has a repository, left on this machine otherwise. The guide's folder is not touched."""
        declared = declared_of(body.chapters)
        pending = pending_split(ctx)
        if pending:
            raise HTTPException(409, f"a pull request already declares chapters: {pending['pr_url']} (merge or close it first)")
        if not vault.guide_of(settings.vault).from_manifest:
            raise HTTPException(409, f"the guide has no {guide_mod.MANIFEST}: `vault-watch init` writes one, the chapters go there")
        now = vault.guide_of(settings.vault)
        try:
            done = chapters_mod.publish(now, settings.home, declared, today=date.today().isoformat(),
                                        open_pull_request=forge.get().open_pull_request)
        except (guide_mod.GuideError, RuntimeError) as e:  # nothing to change, git, or the forge
            raise HTTPException(409, str(e)[:600]) from e
        if done["pr_url"]:
            write_json(pending_file(ctx), {**done, "t": time.time()})
        return {**done, "base": now.base_branch}

    return api
