"""Page « Sources »: the sources of the watch (sources.py), what each feed brought from the watches and runs kept here,
what each answered at the last check (sourcecheck.py), and the proposals of that check: applied on a branch of the
guide, or put off until the next one."""

from __future__ import annotations

import threading
import time
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import forge, sourcecheck, sources, vault
from .context import AppContext, Job, read_json, thread_config, write_json

CHECK = "sources-check"  # the job of a check, for the page that follows it and for /api/health


class Changes(BaseModel):
    ids: list[str]  # the proposals of the last source check to apply (S1, S4…)


class Later(BaseModel):
    ids: list[str]  # the proposals of the last source check to put off until the next one
    on: bool = True  # False: decide them now after all


def check_file(ctx: AppContext) -> Path:
    """The last check: what each source answered, the proposals."""
    return ctx.settings.home / "sources-check.json"


def last_check(ctx: AppContext) -> dict | None:
    try:
        return read_json(check_file(ctx))
    except (OSError, ValueError):
        return None


def to_decide(check: dict | None, ids: list[str]) -> list[dict]:
    """The proposals of the check among `ids` that are not applied yet."""
    return [p for p in (check or {}).get("proposals", []) if p["id"] in ids and not p.get("applied")]


def settle(ctx: AppContext, check: dict) -> dict:
    """What became of the pull requests opened from the page. Merged: their proposals are done, and the copy
    of the guide the page reads is brought up to date (the list now holds the change). Closed without a
    merge: their proposals are to decide again. Read from the forge until it is one or the other."""
    moved = False
    for done in check.get("applied", []):
        if not done.get("pr_url") or done.get("state") in ("merged", "closed"):
            continue
        state = ctx.pr_state(done["pr_url"])
        if state not in ("merged", "closed"):
            continue
        done["state"], moved = state, True
        for p in check["proposals"]:
            if p["id"] not in done["ids"]:
                continue
            if state == "merged":
                p["merged"] = True
            else:
                p.pop("applied", None)
        if state == "merged":
            try:
                vault.reading_copy(ctx.settings.vault, ctx.settings.home)
            except RuntimeError:  # offline: the next check of the sources does it
                pass
    if moved:
        with ctx.lock:
            write_json(check_file(ctx), check)
    return check


def merged_guide(ctx: AppContext):
    """The guide as merged, for the list of its feeds: the copy the checks keep up to date, else its folder."""
    guide = vault.guide_of(ctx.settings.vault)
    copy = ctx.settings.home / "worktrees" / f"read-{guide.base_branch}"
    return vault.guide_of(copy) if (copy / ".git").exists() and (copy / guide.watch.feeds).is_file() else guide


def router(ctx: AppContext) -> APIRouter:
    api = APIRouter()
    settings = ctx.settings
    outcomes: dict[str, tuple[str, dict]] = {}  # thread -> (its last checkpoint, what became of each item)

    def watch_outcomes() -> list[dict]:
        """What became of the items of each watch run; a run is read again only when it has moved."""
        found = []
        for thread, last in ctx.checkpoints():
            if thread.startswith("eval-"):  # a replay of a watch already counted
                continue
            if outcomes.get(thread, ("",))[0] != last:
                outcomes[thread] = (last, sources.run_outcomes(ctx.viewer.get_state(thread_config(thread)).values))
            found.append(outcomes[thread][1])
        return found

    @api.get("/api/sources")
    def sources_view():
        job, check = ctx.jobs.get(CHECK), last_check(ctx)
        if check:
            check = settle(ctx, check)
        data = sources.summary(merged_guide(ctx), settings.home, watch_outcomes())
        known = {f["id"] for f in data["feeds"]}
        if check:  # what each source answered, beside what it brought
            for f in data["feeds"]:
                f["probe"] = check["probes"].get(f["id"])
            # Done: merged, or about a feed the list no longer holds (removed) or already holds (added) since
            check["proposals"] = [p for p in check["proposals"] if not p.get("merged")
                                  and ((p["feed"]["id"] in known) != (p["action"] == "add") or p.get("applied"))]
        data["check"] = check
        data["checking"] = {"running": bool(job and not job.done), "done": len(job.events) if job else 0,
                            "total": len(data["feeds"]), "error": job.error if job else ""}
        data["repository"] = settings.repo
        return data

    @api.post("/api/sources/check")
    def sources_check():
        """Asks every source and reads the guide (network, no model, nothing billed); followed by GET /api/sources."""
        with ctx.lock:
            if ctx.busy(CHECK):
                raise HTTPException(409, "the sources are already being checked")
            job = ctx.jobs[CHECK] = Job(CHECK, "sources")

        def work():
            try:
                guide = vault.guide_of(vault.reading_copy(settings.vault, settings.home))  # the guide as merged
                result = sourcecheck.check(guide, settings.home, watch_outcomes(),
                                           progress=lambda fid: job.events.append({"t": time.time(), "node": fid}))
                write_json(check_file(ctx), {**result, "applied": []})
            except Exception as e:  # noqa: BLE001 - shown on the page
                job.error = f"{type(e).__name__}: {e}"[:500]
            finally:
                job.done = True
                ctx.touch()

        threading.Thread(target=work, daemon=True, name="vault-watch sources").start()
        return {"started": True}

    @api.post("/api/sources/apply")
    def sources_apply(body: Changes):
        """The chosen proposals on a branch of the guide, and a pull request when it has a repository."""
        check = last_check(ctx)
        chosen = to_decide(check, body.ids)
        if not check or not chosen:
            raise HTTPException(400, "none of these proposals is to apply (check the sources again)")
        guide = vault.guide_of(settings.vault)
        try:
            done = sourcecheck.publish(guide, settings.home, chosen, today=date.today().isoformat(),
                                       open_pull_request=forge.get().open_pull_request)
        except (RuntimeError, ValueError) as e:  # git, the forge, or a file that changed since the check
            raise HTTPException(409, str(e)[:500]) from e
        with ctx.lock:
            check = last_check(ctx) or check
            for p in check["proposals"]:
                if p["id"] in {c["id"] for c in chosen}:
                    p["applied"] = done
            check.setdefault("applied", []).append({**done, "ids": [c["id"] for c in chosen], "t": time.time()})
            write_json(check_file(ctx), check)
        return done

    @api.post("/api/sources/later")
    def sources_later(body: Later):
        """Put proposals off until the next check: they leave the list to decide, nothing changes in the guide. The
        next check writes its own proposals: what is still true then comes back."""
        with ctx.lock:
            check = last_check(ctx)
            chosen = to_decide(check, body.ids)
            if not check or not chosen:
                raise HTTPException(400, "none of these proposals is to decide (check the sources again)")
            for p in chosen:
                if body.on:
                    p["later"] = time.time()
                else:
                    p.pop("later", None)
            write_json(check_file(ctx), check)
        return {"later": [p["id"] for p in check["proposals"] if p.get("later")]}

    return api
