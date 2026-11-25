"""Page « Languages »: « Sync the languages », the mirrors following the source pages (mirrors.py), and the editor's
edits checked before the sync (H4.2, proofread.py); with what each would cost."""

from __future__ import annotations

import re
import time
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import guide as guide_mod
from .. import llm, mirrors, prices, proofread, vault, verify
from .context import AppContext, Job, read_json, thread_config, write_json


class Accept(BaseModel):
    ids: list[str]  # the fixes to apply in the guide's folder
    edits: dict[str, str] = {}  # the editor's own text for a fix: {id: text}


class MirrorCheck(BaseModel):
    """The editor's edits checked before a sync (proofread.py): the pages as GET /api/mirrors offers them."""
    pages: list[str] = []
    hand: list[str] = []
    checks: list[str]  # spelling, facts, consistency
    steps: dict = {}


class MirrorSync(BaseModel):
    pages: list[str] = []  # source pages ahead of their mirror on the base branch (mirrors.behind)
    hand: list[str] = []  # source pages edited in the guide's folder and not committed (mirrors.folder_changes)
    steps: dict = {}  # for this run alone: {step: {engine, model, effort}}


# -- what the translation and the checks would cost ---------------------------------------------------------------
def translation_usd(model: str, table: prices.Prices, size: int, changed: list[tuple[str, str]]) -> float:
    """What translating the changed passages of a page costs, into a mirror of `size` bytes (not rounded)."""
    moved = sum(len(o.encode("utf-8")) + len(n.encode("utf-8")) for o, n in changed)
    return verify._usd(model, tokens_in=int((size + moved) / verify.BYTES_PER_TOKEN) + 1500,
                       tokens_out=int(moved / verify.BYTES_PER_TOKEN * 0.7) + 300, table=table)


def page_check_usd(cfg: dict, table: prices.Prices, tree: Path, page: str, changed: list[tuple[str, str]]) -> dict:
    """What the spelling (the translation model, the passages) and the facts (the reasoning model, the passages,
    the page and about ten pages of the web) cost for the passages changed in one page."""
    moved = sum(len(n.encode("utf-8")) for _, n in changed)
    size = (tree / page).stat().st_size if (tree / page).is_file() else 0
    b = verify.BYTES_PER_TOKEN
    return {"spelling": round(verify._usd(llm.step_model(cfg, "proofread"), tokens_in=int(moved / b) + 900,
                                          tokens_out=int(moved / b * 0.3) + 200, table=table), 4),
            "facts": round(verify._usd(llm.step_model(cfg, "factcheck"), tokens_in=int((size + moved) / b) + 25_000,
                                       tokens_out=2_000, table=table), 4)}


def consistency_usd(cfg: dict, table: prices.Prices, tree: Path) -> float:
    """The consistency reads the whole guide once (its cache written), whatever the pages."""
    return round(verify._usd(llm.step_model(cfg, "crosscheck"), tokens_out=3_000,
                             cache_write=verify._tokens(vault.pages(tree)), table=table), 2)


def edits_usd(ctx: AppContext, tree: Path, changes: list[tuple[str, list[tuple[str, str]]]], steps: str = "") -> dict:
    """What each check would cost on these edits of the editor ([(page, [(old, new)])]), in `tree`."""
    cfg = ctx.with_steps(steps)
    table = ctx.price_table()
    per_page = [page_check_usd(cfg, table, tree, p, changed) for p, changed in changes]
    return {"spelling": round(sum(x["spelling"] for x in per_page), 4), "facts": round(sum(x["facts"] for x in per_page), 4),
            "consistency": consistency_usd(cfg, table, tree)}


# -- the checks of the editor's edits (proofread.py): one JSON file each --------------------------------------------
def checks_dir(ctx: AppContext) -> Path:
    return ctx.settings.home / "proofread"


def proofread_file(ctx: AppContext, cid: str) -> Path:
    if not re.fullmatch(r"proofread-[\d-]+", cid):
        raise HTTPException(404, f"no check {cid}")
    return checks_dir(ctx) / f"{cid}.json"


def latest_check(ctx: AppContext) -> dict | None:
    """The last check of the edits, while some of its fixes are still to decide (else None)."""
    folder = checks_dir(ctx)
    files = sorted(folder.glob("proofread-*.json")) if folder.is_dir() else []
    if not files:
        return None
    data = read_json(files[-1])
    data["running"] = ctx.busy(data["id"])
    return None if data.get("closed") else data


def mirror_plan(ctx: AppContext, steps: str = "") -> dict:
    """What can be synced: the source pages ahead of their mirror on the base branch, and those edited in the
    guide's folder and not committed, each with its passages and its estimate. A page of the folder is offered
    only when its committed text is the merged one: copied onto a branch of the base, a page of another branch
    or of an older base would undo what the base has since."""
    folder = ctx.settings.vault
    found = mirrors.plan(folder, ctx.settings.home)
    if not found["languages"]:
        return {"languages": [], "ahead": [], "hand": [], "elsewhere": [], "base": found["base"]}
    copy = found["copy"]
    cfg = ctx.with_steps(steps)
    model, table = llm.step_model(cfg, "mirror"), ctx.price_table()

    def usd(page: str, changed: list[tuple[str, str]]) -> float:
        total = 0.0
        for lang_folder in found["languages"].values():
            mirror = copy / f"{lang_folder}{page}"
            total += translation_usd(model, table, mirror.stat().st_size if mirror.is_file() else 0, changed)
        return round(total, 4)

    def costs(page: str, changed: list[tuple[str, str]]) -> dict:
        return {"usd": usd(page, changed), "check_usd": page_check_usd(cfg, table, folder, page, changed)}

    field = vault.guide_of(folder).modified_field
    # Each page with its changed zones, two lines around each: what the translation will follow, read before
    ahead = []
    for p, n in found["ahead"].items():
        since = found["since"][p]
        ahead.append({"page": p, "since": since, "passages": n, **costs(p, mirrors.edits_of_commit(copy, p, since)),
                      "hunks": mirrors.hunks(mirrors.show(copy, since, p), mirrors.show(copy, "HEAD", p), field)})
    hand = []
    for p, n in found["hand"].items():
        current = vault.read(folder / p) if (folder / p).is_file() else ""
        hand.append({"page": p, "passages": n, **costs(p, mirrors.edits_of(folder, p, "HEAD")),
                     "hunks": mirrors.hunks(mirrors.show(folder, "HEAD", p), current, field)})
    return {"languages": [{"code": c, "name": guide_mod.language_name(c), "folder": f} for c, f in found["languages"].items()],
            "ahead": ahead, "hand": hand, "elsewhere": found["elsewhere"], "model": model, "base": found["base"],
            "consistency_usd": consistency_usd(cfg, table, folder), "check": latest_check(ctx)}


def offered(plan: dict, pages: list[str], hand: list[str], what: str) -> dict[str, str]:
    """The pages chosen, when the plan offers them all: {source page ahead: the commit its mirror follows}; 400 for
    a page not offered, or for none."""
    ahead = {a["page"]: a["since"] for a in plan["ahead"]}
    in_folder = {h["page"] for h in plan["hand"]}
    unknown = [p for p in pages if p not in ahead] + [p for p in hand if p not in in_folder]
    if unknown or not (pages or hand):
        raise HTTPException(400, f"nothing to {what}, or pages not offered: {unknown}")
    return ahead


def run_proofread(ctx: AppContext, job: Job, body: MirrorCheck, asked: list[str], ahead: dict[str, str], path: Path, data: dict) -> None:
    """Proofreads the editor's edits, then writes what was found (or why it failed) to the check's file."""
    settings = ctx.settings
    deps = settings.make_deps(data["id"], "proofread")
    try:
        # The passages as the folder holds them: what the editor wrote, committed or not
        copy = vault.reading_copy(settings.vault, settings.home) if body.pages else None
        changes = [(p, mirrors.edits_of(settings.vault, p, "HEAD")) for p in body.hand]
        if copy is not None:
            changes += [(p, mirrors.edits_of_commit(copy, p, ahead[p])) for p in body.pages]
        found = proofread.run(settings.vault, changes, set(asked), deps.translator or deps.llm, deps.llm)
        data.update(fixes=found["fixes"], notes=found["notes"],
                    cost=round(sum(u.get("cost_usd", 0) for u in found["usage"]), 2),
                    # on a subscription: what its calls are worth at list price, shown struck through
                    unbilled_usd=round(sum(u.get("list_usd") or 0.0 for u in found["usage"] if not u.get("cost_usd")), 2))
    except Exception as e:  # shown on the page, the edits untouched
        data["error"] = f"{type(e).__name__}: {e}"[:500]
        billed = getattr(e, "usage", None)
        if billed:
            data["cost"] = round(data["cost"] + billed.get("cost_usd", 0), 2)
    finally:
        data["done"] = True
        write_json(path, data)
        job.events.append({"t": time.time(), "node": "proofread", "cost": data["cost"]})


def router(ctx: AppContext) -> APIRouter:
    api = APIRouter()
    settings = ctx.settings

    @api.get("/api/mirrors")
    def mirrors_view(steps: str = ""):
        return mirror_plan(ctx, steps)

    @api.post("/api/mirrors/check")
    def mirrors_check(body: MirrorCheck):
        asked = [c for c in proofread.CHECKS if c in body.checks]
        if not asked or set(body.checks) - set(proofread.CHECKS):
            raise HTTPException(400, f"checks: some of {', '.join(proofread.CHECKS)}")
        ahead = offered(mirror_plan(ctx), body.pages, body.hand, "check")
        cid = time.strftime("proofread-%Y-%m-%d-%H%M%S")
        ctx.keep_steps(cid, body.steps)
        checks_dir(ctx).mkdir(parents=True, exist_ok=True)
        path = checks_dir(ctx) / f"{cid}.json"
        data = {"id": cid, "started": time.time(), "checks": asked, "pages": [*body.hand, *body.pages],
                "fixes": [], "notes": [], "cost": 0.0, "done": False, "error": "", "applied": [], "failed": {}}
        write_json(path, data)
        ctx.start(cid, "proofread", "proofread", lambda graph, job: run_proofread(ctx, job, body, asked, ahead, path, data))
        return {"id": cid}

    @api.get("/api/mirrors/check/{cid}")
    def mirrors_check_view(cid: str):
        data = read_json(proofread_file(ctx, cid))
        data["running"] = ctx.busy(cid)
        return data

    @api.post("/api/mirrors/check/{cid}/accept")
    def mirrors_check_accept(cid: str, body: Accept):
        """The fixes accepted, applied in the guide's folder as if typed there; the others left. The check is then
        closed: the page « Languages » shows the pages as they now are, to sync."""
        path = proofread_file(ctx, cid)
        if ctx.busy(cid):
            raise HTTPException(409, "the check is still running")
        data = read_json(path)
        done = proofread.accept(settings.vault, data["fixes"], body.ids, body.edits, date.today().isoformat())
        data.update(applied=done["applied"], failed=done["failed"], closed=True)
        write_json(path, data)
        return done

    @api.post("/api/mirrors")
    def mirrors_start(body: MirrorSync):
        plan = mirror_plan(ctx)
        ahead = offered(plan, body.pages, body.hand, "sync")
        thread = ctx.free_thread(f"mirror-{date.today().isoformat()}")
        branch = f"i18n/{thread}"
        ctx.keep_steps(thread, body.steps)

        def work(graph, job: Job):
            worktree = mirrors.prepare(settings.vault, settings.home, plan["base"], branch, body.hand)
            graph.update_state(thread_config(thread), mirrors.initial_state(
                thread, branch, worktree, {p: ahead[p] for p in body.pages}, body.hand, date.today().isoformat()),
                as_node="apply")
            ctx.follow(graph, job, None)

        ctx.start(thread, "mirror", "mirror", work)
        pending = latest_check(ctx)
        if pending and not pending["running"]:  # a check left undecided: the sync goes without its fixes
            write_json(proofread_file(ctx, pending["id"]), {**{k: v for k, v in pending.items() if k != "running"}, "closed": True})
        return {"thread": thread}

    return api
