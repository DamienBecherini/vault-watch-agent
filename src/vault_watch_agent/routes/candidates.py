"""Page « Candidates » (ROADMAP D3.2): the registry of discovery (candidates.py) as the editor sees and changes it.

The changes go to a draft the agent keeps (`candidates-draft.json` of its home), never to the guide's folder: the
registry is a file of the guide, read by its weekly collection, so it changes through a pull request. « Publish the
registry » writes the draft on a branch of the guide and opens it; while it is open, publishing again adds a commit
to it. Merged: the folder follows the base branch, and the draft goes when it holds nothing more.
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import candidates as cand
from .. import forge, vault
from .. import guide as guide_mod
from .context import AppContext, read_json, write_json


class Add(BaseModel):
    name: str
    url: str = ""
    kind: str = "other"
    note: str = ""  # why it is added, kept in its history


class Move(BaseModel):
    state: str
    reason: str = ""
    recheck: str = ""  # YYYY-MM-DD, for watching or dismissed


class PublishBody(BaseModel):
    path: str = ""  # the manifest names no registry yet: where the guide keeps it


def draft_file(ctx: AppContext) -> Path:
    return cand.draft_path(ctx.settings.home)


def pending_file(ctx: AppContext) -> Path:
    """The pull request of the registry, until it is merged or closed: {branch, pr_url, path, published (the text)}."""
    return ctx.settings.home / cand.PENDING


def where(ctx: AppContext) -> tuple[str, str]:
    return cand.place(vault.guide_of(ctx.settings.vault), ctx.settings.home)


def pending(ctx: AppContext) -> dict:
    """The open pull request of the registry. Merged: the folder follows its base branch, and the draft goes if it
    holds nothing more than what was published; merged or closed: forgotten (a closed one leaves the draft)."""
    try:
        done = read_json(pending_file(ctx))
    except (OSError, ValueError):
        return {}
    state = ctx.pr_state(done.get("pr_url", "")) if done.get("pr_url") else ""
    if state not in ("merged", "closed"):
        return done
    if state == "merged":
        try:
            vault.sync(ctx.settings.vault, ctx.guide.base_branch)
        except RuntimeError:
            pass  # not on its base branch, or offline: it follows at the next run
        try:
            if draft_file(ctx).read_text(encoding="utf-8") == done.get("published"):
                draft_file(ctx).unlink()
        except OSError:
            pass
    pending_file(ctx).unlink(missing_ok=True)
    return {}


def current(ctx: AppContext, rel: str) -> tuple[cand.Registry, cand.Registry]:
    """(the registry as the page shows and changes it: the draft, else the base's; the base's)."""
    try:
        return cand.working(vault.guide_of(ctx.settings.vault), ctx.settings.home, rel)
    except cand.RegistryError as e:
        raise HTTPException(409, str(e)) from e


def mark_proposed(ctx: AppContext, cid: str, thread: str) -> None:
    """The candidate an addition run was started for (/api/fix `candidate`): proposed, the run named."""
    _, rel = where(ctx)
    with cand.LOCK:
        reg, _ = current(ctx, rel)
        try:
            reg.move(cid, "proposed", today=date.today().isoformat(), reason=f"run {thread}")
        except cand.RegistryError:
            return  # gone from the draft meanwhile: the run goes on
        reg.save()


def router(ctx: AppContext) -> APIRouter:
    api = APIRouter()

    def view() -> dict:
        open_pr = pending(ctx)  # first: a pull request merged moves the folder forward, and may drop the draft
        declared, rel = where(ctx)
        reg, base = current(ctx, rel)
        today = date.today().isoformat()
        now = vault.guide_of(ctx.settings.vault)
        found = cand.changes(base.candidates, reg.candidates)
        return {"declared": declared, "path": rel, "draft": draft_file(ctx).is_file(), "changes": found,
                # what the draft holds that the open pull request does not (all of it when none is open)
                "unpublished": bool(found) and reg.text() != open_pr.get("published"),
                "pending": {k: v for k, v in open_pr.items() if k != "published"},
                "candidates": reg.candidates, "due": [c["id"] for c in reg.due(today)], "today": today,
                "states": list(cand.STATES), "kinds": list(reg.kinds), "look_again": list(cand.LOOK_AGAIN),
                "has_repo": bool(now.repository), "forge": forge.get().name, "base": now.base_branch,
                "manifest": guide_mod.MANIFEST, "needs": cand.NEEDS}

    def change(do) -> dict:
        _, rel = where(ctx)
        with cand.LOCK:
            reg, _ = current(ctx, rel)
            try:
                out = do(reg)
            except cand.RegistryError as e:
                raise HTTPException(400, str(e)) from e
            reg.save()
        return {**view(), **(out or {})}

    @api.get("/api/candidates")
    def candidates_get():
        """The registry as the page shows it (the draft when there is one), what the draft changes, the pull request
        still open."""
        return view()

    @api.post("/api/candidates")
    def candidates_add(body: Add):
        """A candidate added by hand (a lead, origin « hand »); a name or an address already known adds its source."""
        def do(reg):
            c, new = reg.note(body.name, body.url.strip(), origin="hand", seen=date.today().isoformat(), kind=body.kind,
                              note=body.note)
            return {"id": c["id"], "new": new}
        return change(do)

    @api.post("/api/candidates/{cid}")
    def candidates_move(cid: str, body: Move):
        """A candidate to another state: dismissed needs a reason; a date to look again for watching or dismissed."""
        return change(lambda reg: reg.move(cid, body.state, today=date.today().isoformat(), reason=body.reason,
                                           recheck=body.recheck) and None)

    @api.post("/api/candidates-draft/discard")
    def candidates_discard():
        """The draft dropped: the registry as the base branch has it again."""
        with cand.LOCK:
            draft_file(ctx).unlink(missing_ok=True)
        return view()

    @api.post("/api/candidates-draft/publish")
    def candidates_publish(body: PublishBody):
        """The draft written on a branch of the guide (with the manifest's key when it names no registry yet), pushed
        with its pull request when the guide has a repository; an open one gets a commit more. The folder is not
        touched."""
        declared, rel = where(ctx)
        if not declared and body.path.strip() and not pending(ctx):  # an open pull request keeps the path it gave
            try:
                rel = cand.valid_path(body.path)
            except cand.RegistryError as e:
                raise HTTPException(400, str(e)) from e
        now = vault.guide_of(ctx.settings.vault)
        if not now.from_manifest:
            raise HTTPException(409, f"the guide has no {guide_mod.MANIFEST}: `vault-watch init` writes one, the registry is named there")
        with cand.LOCK:
            reg, base = current(ctx, rel)
            text, found = reg.text(), cand.changes(base.candidates, reg.candidates)
            open_pr = pending(ctx)
            try:
                done = cand.publish(now, ctx.settings.home, text, rel, found, stamp=time.strftime("%Y-%m-%d-%H%M"),
                                    branch=open_pr.get("branch", ""), pr_url=open_pr.get("pr_url", ""),
                                    open_pull_request=forge.get().open_pull_request)
            except (cand.RegistryError, guide_mod.GuideError, RuntimeError) as e:  # nothing to change, git, the forge
                raise HTTPException(409, str(e)[:600]) from e
            reg.save()  # the draft as published: it goes when the pull request is merged
            if done["pr_url"]:
                write_json(pending_file(ctx), {**done, "path": rel, "published": text, "t": time.time()})
        return {**view(), **done}

    return api
