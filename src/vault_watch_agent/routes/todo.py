"""Page « To handle »: the watches of the guide with the run that counts for each, a new watch collected from the
guide's feeds, and the guide's folder (« Update my folder », what was set aside from it and not put back yet)."""

from __future__ import annotations

import re
import time

from fastapi import APIRouter, HTTPException

from .. import retouch, vault
from .. import watches as watches_mod
from .context import AppContext


def run_of(ctx: AppContext, watch: dict, known: dict[str, str]) -> dict:
    """The run that counts for a watch: the published one, else the latest (re-runs are named issue-50b…)."""
    runs = [ctx.summary(t, known[t]) for t in known if re.fullmatch(rf"{re.escape(watch['thread'])}[a-z]?", t)]
    if runs:
        return next((r for r in runs if r["pr_url"]), runs[0])
    new = ctx.summary(watch["thread"])
    if watch["state"] == "closed":
        new["status"] = "closed"  # handled by hand, before the agent or without it
    return new


def router(ctx: AppContext) -> APIRouter:
    api = APIRouter()
    settings = ctx.settings
    # The guide's folder against origin (« Update my folder »): origin is asked at most once a minute, the pages that
    # show it (« To handle », a run merged, the menu's count) asking often
    folder_seen: dict = {}

    @api.get("/api/watches")
    def watches():
        found, known = ctx.list_watches(), ctx.stamped()
        ctx.warm(known)
        return [{**w, "run": run_of(ctx, w, known)} for w in found]

    @api.post("/api/collect")
    def collect_now():
        """A new watch from the guide's feeds (`[watch] source = "feeds"`): no model, nothing billed."""
        from .. import collect

        src = ctx.watch_source()
        if not isinstance(src, watches_mod.Collected):  # the one source of kind "feeds"
            raise HTTPException(400, 'the guide\'s watches do not come from its feeds ([watch] source = "feeds")')
        try:
            path = src.collect()
        except collect.CollectError as e:
            raise HTTPException(400, str(e)) from e
        return next(w for w in src.list() if w["thread"] == path.stem)

    @api.get("/api/folder")
    def folder_now(fresh: bool = False):
        """The guide's folder: its path, branch, the merged commits it lacks (`behind`, with their pull request), its
        changes not committed, when its base last moved, the run it is lent to."""
        base = vault.guide_of(settings.vault).base_branch
        fetch = fresh or time.time() - folder_seen.get("at", 0) > 60
        try:
            now = vault.folder_state(settings.vault, base, fetch=fetch)
        except RuntimeError as e:
            raise HTTPException(409, f"the guide's folder: {e}") from e
        if fetch:
            folder_seen["at"] = time.time()
        return {**now, "path": str(settings.vault), "lent_to": retouch.lent_to(settings.home)}

    @api.post("/api/folder/update")
    def folder_update():
        """« Update my folder »: its base moves forward to origin's (fast-forward only, nothing not committed is lost,
        the branch checked out is not changed). Refused while the folder is lent to a run."""
        lent = retouch.lent_to(settings.home)
        if lent:
            raise HTTPException(409, f"the guide's folder is lent to the run {lent}: end its retouches or take it back first")
        done = vault.update_folder(settings.vault, vault.guide_of(settings.vault).base_branch)
        folder_seen.clear()
        return done

    @api.get("/api/folder/aside")
    def folder_aside():
        """What was set aside from the guide's folder and not put back yet, for a banner of the page."""
        return retouch.pending(settings.home)

    @api.post("/api/folder/aside/{thread}")
    def folder_put_back(thread: str):
        try:
            retouch.put_back(settings.vault, settings.home, thread)
        except retouch.FolderError as e:
            raise HTTPException(409, str(e)) from e
        return retouch.pending(settings.home)

    return api
