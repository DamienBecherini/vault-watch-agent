"""The health checks of the guide (verify.py), page « Checks »: one JSON file per verification, what became of each of
its findings (open, sent to a fix run, dismissed), the editor's notes on its leads, and what a new one would cost."""

from __future__ import annotations

import re
import shutil
import time
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import candidates, inputs, links, llm, news, vault, verify, videos
from .. import chapters as chapters_mod
from .. import config as user_settings
from .context import AppContext, Job, read_json, write_json

NOTE_CHARS = 4000  # « What I already know » on a lead: what the editor wrote, at most


class Handle(BaseModel):
    findings: list[str]
    status: Literal["dismissed", "open"]


class LeadNote(BaseModel):
    finding: str  # the lead's line, as the check wrote it
    text: str = ""  # what the editor already knows of it; empty: the note is removed


class Verification(BaseModel):
    checks: list[str]  # ids of verify.CHECKS
    chapters: list[str] = []  # the check « explore »: the chapters to explore (all of them when empty)
    links: list[str] = []  # the check « links »: the addresses to read (links.py)
    lang: str = ""  # the language of the interface: the leads are explained in it (news.in_language)
    steps: dict = {}  # for this verification alone: {step: {engine, model, effort}} (config.run_steps)


def verif_files(ctx: AppContext) -> list[Path]:
    return sorted(ctx.verifs.glob("verif-*.json"), reverse=True) if ctx.verifs.is_dir() else []


def verif_path(ctx: AppContext, vid: str) -> Path:
    path = ctx.verifs / f"{vid}.json"
    if not re.fullmatch(r"verif-[\d-]+", vid) or not path.is_file():
        raise HTTPException(404, f"no verification {vid}")
    return path


def verif_view(ctx: AppContext, path: Path, detail: bool = False) -> dict:
    """The verification with what became of its findings: open, sent to a fix run, or dismissed. `detail` (one
    verification looked at, not a list): the leads an addition run could not look at, read from its state."""
    data = read_json(path)
    job = ctx.jobs.get(data["id"])
    data["running"] = bool(job and not job.done)
    # Stopped before its last check (the server was closed meanwhile): what it found stays usable, the checks
    # it did not reach are listed, and nothing will ever finish it.
    data["interrupted"] = not data.get("done") and not data["running"]
    data["missing"] = [c for c in data.get("checks", []) if c not in data["results"]] if data["interrupted"] else []
    # The check being run: the last one started (the page marks it « running » instead of « waiting »)
    started = [e["node"][6:] for e in (job.events if job and data["running"] else []) if e.get("node", "").startswith("start:")]
    data["current"] = started[-1] if started else ""
    data["error"] = (job.error if job else "") or data.get("error", "")
    handled = data.setdefault("handled", {})
    every = [f for r in data["results"].values() for f in r.get("findings", [])]
    counts = {"open": 0, "fix": 0, "dismissed": 0}
    for f in every:
        counts[handled.get(f, {}).get("status", "open")] += 1
    data["counts"] = counts
    usage = [u for r in data["results"].values() for u in (r.get("usage") or []) if isinstance(u, dict)]
    data["unbilled_usd"] = round(sum(u.get("list_usd") or 0.0 for u in usage if not u.get("cost_usd")), 2)
    for step, r in data["results"].items():  # per check: findings still open, and where they can go
        r["open"] = sum(1 for f in r.get("findings", []) if f not in handled)
        if step in verify.BY_ID:  # as the check is now, not as it was when this verification ran
            r["fixable"], r["mode"] = verify.BY_ID[step].fixable, verify.BY_ID[step].fix_mode
    # The fix runs the findings went to, with where they stand (review, publish, PR to merge, merged)
    data["runs"] = {}
    for h in handled.values():
        if h.get("status") == "fix" and h["thread"] not in data["runs"]:
            s = ctx.summary(h["thread"])
            data["runs"][h["thread"]] = {"status": s["status"], "pr_url": s["pr_url"]}
    data["unchecked"] = unchecked_leads(ctx, data["runs"], handled) if detail else {}
    data["status"] = ("running" if data["running"] else "to-handle" if counts["open"]
                      else "handled" if every else "clear")
    if detail:  # what the page links a lead to: the titles of the pages, and the vault Obsidian opens them in
        data["titles"], data["vault_name"] = chapters_mod.titles(ctx.settings.vault), ctx.settings.vault.name
    return data


def unchecked_leads(ctx: AppContext, runs: dict[str, dict], handled: dict) -> dict[str, str]:
    """The leads their addition run could not look at (the web of its call ran out, the call failed): {lead: why}.
    The page says so on the lead and offers to put it back among those to handle."""
    found: dict[str, str] = {}
    for thread, run in runs.items():
        values = ctx.values(thread) if run["status"] != "running" else {}
        if values.get("mode") != "add":
            continue
        found.update({u["lead"]: u["why"] for u in news.unchanged(values)
                      if news.NOT_CHECKED.match(u["why"]) and handled.get(u["lead"], {}).get("thread") == thread})
    return found


def mark(ctx: AppContext, vid: str, findings: list[str], entry: dict | None) -> None:
    """Record what became of findings (None: back to open). Not while the check still writes its file: a job
    of this server is running it. A check a stopped server left unfinished is handled like a finished one."""
    path = verif_path(ctx, vid)
    with ctx.lock:
        data = read_json(path)
        if ctx.busy(vid):
            raise HTTPException(409, "the check is still running")
        handled = data.setdefault("handled", {})
        for f in findings:
            if entry:
                handled[f] = {**entry, "t": time.time()}
            else:
                handled.pop(f, None)
        write_json(path, data)


def dismissed_to_registry(ctx: AppContext, vid: str, findings: list[str]) -> list[str]:
    """Leads of an addition check that the editor dismissed: dismissed candidates of the registry (D3.3), so that
    the next watches and checks do not bring them back. Not a lead « Newer » (about what the guide covers already).
    Nothing when the guide does not use the registry; a registry that cannot be read leaves the dismissal as it is."""
    data = read_json(verif_path(ctx, vid))
    found = []
    for result in data.get("results", {}).values():
        if result.get("mode") != "add":
            continue
        for f in findings:
            p = news.parts(f)
            if f not in result.get("findings", []) or p["kind"] == news.KINDS["newer"]:
                continue
            title = (result.get("details", {}).get(f) or {}).get("title") or re.split(r"(?<=\.)\s", p["text"])[0][:140]
            found.append({"name": title, "url": (p["sources"] or [""])[0], "why": p["text"],
                          "dismiss": f"dismissed on the check {vid}"})
    try:
        return candidates.note_all(vault.guide_of(ctx.settings.vault), ctx.settings.home, found, origin=f"check {vid}",
                                   seen=date.today().isoformat())
    except (candidates.RegistryError, OSError, RuntimeError):
        return []


def verif_card(ctx: AppContext, path: Path) -> dict:
    """What the list of the checks shows of one: its kinds (verify.KINDS), the links it read (or was given, while
    it reads them). What its calls on a subscription are worth at list price is in verif_view (`unbilled_usd`)."""
    data = verif_view(ctx, path)
    out = {k: v for k, v in data.items() if k not in ("results", "handled")}
    out["kinds"] = [k for k in verify.KINDS if any(verify.BY_ID[c].kind == k for c in data.get("checks", []) if c in verify.BY_ID)]
    read = data["results"].get("links", {}).get("links")
    if read is None and "links" in data.get("checks", []):
        options = path.with_suffix("") / "options.json"
        given = read_json(options).get("links", []) if options.is_file() else []
        read = [{"url": u, "kind": "pdf" if u.lower().endswith(".pdf") else "", "title": ""} for u in given]
    out["links"] = [{"url": x["url"], "kind": x.get("kind", ""), "title": links.title_of(x), "error": bool(x.get("error"))}
                    for x in read or []]
    return out


def explorable_view(ctx: AppContext) -> list[dict]:
    """The chapters a call can explore: its pages, its weight, and whether it is ticked when the page opens."""
    by = {c["name"]: c for c in chapters_mod.view(ctx.settings.vault)["chapters"]}
    return [{"id": name, "pages": len(pages), "kb": by[name]["kb"], "explore": by[name]["explore"]}
            for name, pages in news.explorable(ctx.settings.vault).items()]


def measured(ctx: AppContext) -> dict[str, int]:
    """Counts from the last checks that measured them, for the paid follow-ups: dead links, claims due."""
    known: dict[str, int] = {}
    for p in verif_files(ctx):
        r = read_json(p).get("results", {})
        if "dead" not in known and "sources" in r:
            known["dead"] = len(r["sources"].get("dead", []))
        if "claims" not in known and "freshness" in r:
            known["claims"] = len(r["freshness"].get("claims", []))
    return known


def run_checks(ctx: AppContext, job: Job, body: Verification, plan: list[str], path: Path, data: dict) -> None:
    """Runs the checks of a verification one after the other, writing its file after each (the page follows it)."""
    vid, settings = data["id"], ctx.settings
    deps = settings.make_deps(vid, "verify")
    work_dir = ctx.verifs / vid
    work_dir.mkdir(exist_ok=True)
    if body.chapters or body.links or body.lang:  # read by the checks that take them (verify.options)
        write_json(work_dir / "options.json", {"chapters": body.chapters, "links": body.links,
                                               "lang": body.lang if re.fullmatch(r"[a-z]{2}", body.lang) else "",
                                               # dl-sub-dub for the videos: the reference of its token, not the token
                                               "videos": user_settings.load(ctx.cfg_home)["videos"] if body.links else {}})
    # The guide as merged (main, up to date with origin), not the folder: it may be on another branch
    guide = vault.reading_copy(settings.vault, settings.home)
    data["commit"] = inputs.run(["git", "rev-parse", "--short", "HEAD"], cwd=guide).strip()
    try:
        for step in plan:
            check = verify.BY_ID[step]
            model = None if not check.model else (deps.translator or deps.llm) if check.model == verify.TRANSLATOR else deps.llm
            job.events.append({"t": time.time(), "node": f"start:{step}"})
            try:
                result = verify.RUNNERS[step](guide, work_dir, data["results"], model)
            except Exception as e:  # one check failing does not stop the others
                result = {"ok": False, "summary": f"could not run: {type(e).__name__}: {e}"[:500], "findings": []}
                billed = getattr(e, "usage", None)
                if billed:  # billed all the same (an answer cut at the output limit)
                    result["usage"] = [billed]
            result["fixable"] = check.fixable
            data["cost"] = round(data["cost"] + sum(u.get("cost_usd", 0) for u in result.get("usage", [])), 2)
            data["results"][step] = result
            write_json(path, data)
            job.events.append({"t": time.time(), "node": step, "cost": data["cost"]})
    finally:
        data["done"] = True
        write_json(path, data)


def router(ctx: AppContext) -> APIRouter:
    api = APIRouter()

    @api.post("/api/verifications/{vid}/note")
    def verif_note(vid: str, body: LeadNote):
        """« What I already know » on a lead: kept with the check, sent with the lead to its run (marked as the
        editor's, unpublished, a check, never cited: fix.EDITOR_NOTE). An empty text removes it."""
        path = verif_path(ctx, vid)
        with ctx.lock:
            data = read_json(path)
            if ctx.busy(vid):
                raise HTTPException(409, "the check is still running")
            if not any(body.finding in r.get("findings", []) for r in data["results"].values()):
                raise HTTPException(404, "no such lead in this check")
            notes = data.setdefault("notes", {})
            text = body.text.strip()[:NOTE_CHARS]
            if text:
                notes[body.finding] = text
            else:
                notes.pop(body.finding, None)
            write_json(path, data)
        return {"notes": notes}

    @api.post("/api/verifications/{vid}/leads")
    def verif_handle(vid: str, body: Handle):
        mark(ctx, vid, body.findings, {"status": "dismissed"} if body.status == "dismissed" else None)
        if body.status == "dismissed":
            dismissed_to_registry(ctx, vid, body.findings)
        return verif_view(ctx, verif_path(ctx, vid))["counts"]

    @api.post("/api/verifications/{vid}/delete")
    def verif_delete(vid: str):
        """Removes a check and its working files; the fix runs it started stay. Not while it runs."""
        path = verif_path(ctx, vid)
        if ctx.busy(vid):
            raise HTTPException(409, "the check is still running")
        with ctx.lock:
            path.unlink()
            shutil.rmtree(ctx.verifs / vid, ignore_errors=True)
        return {"deleted": vid}

    @api.get("/api/verifications/options")
    def verif_options(steps: str = ""):
        """`steps`: what the page chose for the steps of the verification it is about to start (JSON), laid over the
        settings: the estimates and the way each check is paid follow it."""
        known = measured(ctx)
        cfg = ctx.with_steps(steps)
        models = cfg["models"]  # the models of the user's settings, shown and priced
        # a step's own model, or the model of its role with its own engine
        apart = {step: llm.step_model(cfg, step) for step, own in cfg["steps"].items() if own.get("model") or own.get("engine")}
        how = {s["step"]: s for s in ctx.steps_view(cfg)}  # the engine, the effort and the billing of each step
        table = ctx.price_table()
        est = verify.estimates(ctx.settings.vault, known, models, table, apart)
        name = {verify.MODEL: models["reasoning"], verify.TRANSLATOR: models["translator"]}

        def origin(model: str | None) -> str:  # where the price of the estimate comes from, said when it is not set or fetched
            p = table.of(model) if model else None
            return "" if not model else "no price" if p is None else "" if p.origin in ("set", "fetched") else p.label

        def model(c) -> str | None:
            return (apart.get(c.id) or name.get(c.model, c.model)) if c.model else None

        return [{"id": c.id, "title": c.title, "what": c.what, "model": model(c), "needs": list(c.needs), "kind": c.kind,
                 "fixable": c.fixable, "price_origin": origin(model(c)), "limit": c.limit, **est[c.id],
                 # a check that calls the model is a step: the engine and the effort it runs at, how it is paid
                 **({k: how[c.id][k] for k in ("engine", "engine_label", "effort", "billing")} if c.id in how else {}),
                 # what a run made from this check's leads costs, when the agent can estimate it (a compaction run)
                 "run_usd": est.get(f"{c.fix_mode}-run", {}).get("usd"),
                 "run_usd_each": est.get(f"{c.fix_mode}-run", {}).get("usd_each"),
                 "run_usd_deep": est.get(f"{c.fix_mode}-run", {}).get("usd_deep"),  # a lead dug deeper, in a call of its own
                 # an addition run whose calls read their lead's pages and the plan, not the whole guide
                 **{f"run_{k}": est.get(f"{c.fix_mode}-run", {}).get(k) for k in ("usd_pages", "usd_each_pages", "usd_deep_pages")},
                 # the chapters a call can explore, each with its number of pages
                 **({"chapters": explorable_view(ctx)} if c.id == "explore" else {}),
                 **({"links_max": links.MAX_LINKS} if c.id == "links" else {})}
                for c in verify.CHECKS]

    @api.get("/api/videos")
    def videos_view():
        """Whether the videos of the check « links » can be read: dl-sub-dub set in the Settings, answering, with
        its route « text of a video » and a token. {set, ready, why}; never the token."""
        reader = videos.Videos.of(user_settings.load(ctx.cfg_home))
        if not reader:
            return {"set": False, "ready": False, "why": "dl-sub-dub is not set (settings.json: videos)"}
        return {"set": True, **reader.status()}

    @api.get("/api/verifications")
    def verif_list(limit: int = 20):
        """The newest verifications (`limit`; the page asks for one more than it shows, to offer the older ones)."""
        return [verif_card(ctx, p) for p in verif_files(ctx)[:max(1, limit)]]

    @api.get("/api/verifications/{vid}")
    def verif_get(vid: str):
        return verif_view(ctx, verif_path(ctx, vid), detail=True)

    @api.post("/api/verifications")
    def verif_start(body: Verification):
        unknown = set(body.checks) - set(verify.BY_ID)
        if not body.checks or unknown:
            raise HTTPException(400, f"unknown or no checks: {sorted(unknown)}")
        if "links" in body.checks:
            body.links = links.addresses("\n".join(body.links))
            if not body.links:
                raise HTTPException(400, "the check « links » needs at least one http(s) address")
            if len(body.links) > links.MAX_LINKS:
                raise HTTPException(400, f"at most {links.MAX_LINKS} links per check")
        vid = time.strftime("verif-%Y-%m-%d-%H%M%S")
        ctx.keep_steps(vid, body.steps)
        plan = verify.plan(body.checks)
        ctx.verifs.mkdir(parents=True, exist_ok=True)
        path = ctx.verifs / f"{vid}.json"
        data = {"id": vid, "started": time.time(), "checks": plan, "asked": body.checks, "results": {},
                "cost": 0.0, "done": False}
        write_json(path, data)
        ctx.start(vid, "verify", "verify", lambda graph, job: run_checks(ctx, job, body, plan, path, data))
        return {"id": vid}

    return api

