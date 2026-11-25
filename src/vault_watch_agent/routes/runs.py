"""The runs: the list of those that are not a watch's, one run looked at (what each pause shows), its report, its
diff and the stream of its steps; and the actions that start one (a watch analysed, errors or leads sent to a fix
run) or resume it after an error."""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from .. import chapters as chapters_mod
from .. import compact, fix, inputs, llm, news, vault, verify
from .. import config as user_settings
from ..graph import Deps, retouchable, usage_line
from . import checks
from .context import AppContext, Job, interrupts, read_json, thread_config
from .languages import translation_usd

# Steps shown while a run goes; a fix run starts at "number".
STEPS = ["collect", "triage", "locate", "propose", "number", "crosscheck", "report", "review",
         "apply", "retouch", "proofread", "mirror", "translation", "audits", "links", "publish"]


class Analyse(BaseModel):
    issue: int | None = None
    watch_json: str | None = None
    watch: str | None = None  # the id of a watch of the guide's source (a file of the guide)
    steps: dict = {}  # for this run alone: {step: {engine, model, effort}} (config.run_steps)


class Report(BaseModel):
    text: str  # one reported error per line
    verification: str | None = None  # the check these findings come from, to mark them as sent
    # translation: fix the mirror pages against the source ones; compact: trims for what weighs (compact.py);
    # add: what is new, checked on the web and written where it belongs (news.py)
    mode: Literal["fix", "translation", "compact", "add"] = "fix"
    deep: list[str] = []  # an addition run: the leads to dig deeper, each in a call of its own (news.propose)
    # an addition run: what each call reads, the whole guide or its lead's pages and the plan of the guide
    context: Literal["guide", "pages"] = news.CONTEXT
    steps: dict = {}  # for this run alone: {step: {engine, model, effort}} (config.run_steps)


def lead_of(ctx: AppContext, thread: str, line: str) -> dict:
    """Where a lead of an addition run came from: {verification, n (its number on the check's page), name (the
    title written in the language of the interface, when the check wrote one), check}. Empty for an idea typed
    in the interface."""
    for path in checks.verif_files(ctx):
        data = read_json(path)
        if data.get("handled", {}).get(line, {}).get("thread") != thread:
            continue
        for c, r in data["results"].items():  # numbered as on the check's page: from 1 in each check
            for n, f in enumerate(r.get("findings", []), 1):
                if f == line:
                    return {"verification": data["id"], "n": n, "check": c,
                            "name": (r.get("details", {}).get(f) or {}).get("title", "")}
    return {}


def publish_extras(ctx: AppContext, v: dict) -> dict:
    """At the publish pause: the titles of the pages, the vault Obsidian opens, and what translating each changed
    page again from the start would cost (the page offers it)."""
    wt = Path(v.get("worktree") or "")
    if not wt.is_dir():
        return {}
    cfg = user_settings.load(ctx.cfg_home)
    model, table = llm.step_model(cfg, "mirror"), ctx.price_table()
    again = {}
    for pair in v.get("mirror_pairs", []):
        mirror = wt / pair["mirror"]
        size = mirror.stat().st_size if mirror.is_file() else 0
        again[pair["page"]] = round(translation_usd(model, table, size, pair["source"]), 4)
    return {"titles": chapters_mod.titles(wt), "vault_name": ctx.settings.vault.name, "retranslate_usd": again}


def run_page(ctx: AppContext, thread: str) -> dict:
    """One run as its page shows it: where it stands, its pause, its job, and what each pause shows."""
    snapshot = ctx.viewer.get_state(thread_config(thread))
    v, job = snapshot.values, ctx.jobs.get(thread)
    if not v and not job:
        raise HTTPException(404, f"no run {thread}")
    pending = interrupts(snapshot)
    items = {i["id"]: {"id": i["id"], "title": i["title"], "url": i["url"],
                       **({"editor_note": i["editor_note"]} if i.get("editor_note") else {})} for i in v.get("items", [])}
    if v.get("mode") == "add":
        items = {k: {**i, **lead_of(ctx, thread, i["title"])} for k, i in items.items()}
    decisions = v.get("decisions", [])
    usage = v.get("usage", [])
    return {
        **ctx.summary(thread),
        "pause": pending[0] if pending else None,
        # Made so far without a bill (a subscription, a local model) while the settings now name a billed
        # engine: the steps left (the translation) would be billed. The review page says so before the click.
        "billed_next": bool(usage) and not any(u.get("cost_usd") for u in usage) and ctx.billing_now() == "token",
        "job": {"action": job.action, "started": job.started, "events": job.events, "done": job.done,
                "error": job.error} if job else None,
        "triage": {a: sum(1 for d in decisions if d["action"] == a) for a in ("correct", "addition", "drop")},
        "items": items,
        # each with whether the editor can retouch its text (graph.retouchable)
        "corrections": [{**c, "retouchable": retouchable(c)} for c in v.get("corrections", [])],
        "additions": [{**items.get(d["item_id"], {}), "reason": d["reason"]} for d in decisions if d["action"] == "addition"],
        "findings": v.get("findings", []),
        "finding_excerpts": v.get("finding_excerpts", {}),
        "leftovers": v.get("leftovers", []),
        "reading": v.get("reading"),  # whole guide or by chapter (reading.Plan.summary)
        "mode": v.get("mode", ""), "weight": v.get("weight"),  # what the edits weigh, per page (after apply)
        # An addition run writes no new page: the ones its leads would need, shown at the top of the review
        "pages_to_write": news.pages_to_write(v) if v.get("mode") == "add" else [],
        "unchanged": news.unchanged(v) if v.get("mode") == "add" else [],  # its leads without an edit, and why
        "claims_due": v.get("claims_due", []),
        "usage": usage_line(v.get("usage", [])),
        "accepted": v.get("accepted", []), "applied": v.get("applied", []), "branch": v.get("branch", ""),
        "mirrored": v.get("mirrored", []), "mirror_problems": v.get("mirror_problems", []),
        "notes_removed": v.get("notes_removed", []),  # definitions removed with their last citation (apply)
        "retouched": v.get("retouched", []),
        # the editor's edits proofread: the fixes (accepted or not, once decided), the doubts, each proofreading
        "proofread_fixes": v.get("proofread_fixes", []), "proofread_notes": v.get("proofread_notes", []),
        "proofread_log": v.get("proofread_log", []),
        # what changed in each source page beside what the translator made of it (graph.mirror)
        "mirror_pairs": v.get("mirror_pairs", []), "translation_retouched": v.get("translation_retouched", []),
        "link_problems": v.get("link_problems", []), "audit_ok": v.get("audit_ok"),
        "audit_log": v.get("audit_log", ""), "report_path": v.get("report_path", ""),
        "steps": STEPS,
        # Paused at publishing: the titles of the pages, the vault Obsidian opens, and what translating each
        # changed page again from the start would cost (the page offers it)
        **(publish_extras(ctx, v) if pending and pending[0].get("step") == "publish" else {}),
    }


def from_check(ctx: AppContext, vid: str, findings: list[str]) -> tuple[dict, str, dict]:
    """What findings sent from a check bring with them: the passages found when it ran, what the leads came from
    (in words: « links to read whole », for the run's source and its pull request) and the editor's notes."""
    data = read_json(checks.verif_path(ctx, vid))
    results = data["results"]
    notes = {f: n for f, n in (data.get("notes") or {}).items() if f in findings and n}  # « What I already know »
    excerpts = {f: e for r in results.values() for f, e in r.get("excerpts", {}).items() if f in findings}
    origin = " + ".join(verify.short_title(verify.BY_ID[c]) for c, r in results.items()
                        if c in verify.BY_ID and set(r.get("findings", [])) & set(findings))
    return excerpts, origin, notes


def proposals(body: Report, guide: Path, findings: list[str], deps: Deps, excerpts: dict, notes: dict, thread: str):
    """The model's proposals for the findings, by the kind of run: (items, proposal, usage, the run's source)."""
    if body.mode == "translation":
        items, proposal, usage = fix.propose_translation(guide, findings, deps.translator or deps.llm, excerpts)
        return items, proposal, usage, "translation divergences reported in the interface"
    if body.mode == "compact":
        items, proposal, usage = compact.propose(guide, findings, deps.llm, excerpts, notes=notes)
        return items, proposal, usage, thread
    if body.mode == "add":
        items, proposal, usage = news.propose(guide, findings, deps.llm, excerpts, deep=body.deep, context=body.context, notes=notes)
        return items, proposal, usage, thread
    items, proposal, usage = fix.propose(guide, findings, deps.llm, excerpts=excerpts, notes=notes)
    return items, proposal, usage, "errors reported in the interface"


def router(ctx: AppContext) -> APIRouter:
    api = APIRouter()
    settings = ctx.settings

    @api.get("/api/runs")
    def runs(limit: int = 0):
        """Runs that are not a watch's (fix runs, files of another folder), newest first; `limit`: the newest ones
        only (the page asks for one more than it shows, to know whether older ones exist)."""
        src = ctx.watch_source()
        mine = {w["thread"] for w in src.list()} if src.kind in ("file", "feeds") else set()
        known = ctx.stamped()
        others = [t for t in known
                  if not re.fullmatch(r"issue-\d+[a-z]?", t) and re.sub(r"[a-z]$", "", t) not in mine and t not in mine]
        if limit > 0:
            others = others[:limit]
        ctx.warm({t: known[t] for t in others})
        # A run just created has no checkpoint before its proposals are made, which takes minutes: listed all the
        # same, first, so that one can come back to it (it was only reachable from its verification)
        starting = [t for t, job in ctx.jobs.items() if job.action in ("fix", "mirror") and not job.done and t not in known]
        return [ctx.summary(t) for t in starting] + [ctx.summary(t, known[t]) for t in others]

    @api.get("/api/runs/{thread}")
    def run_view(thread: str):
        return run_page(ctx, thread)

    @api.get("/api/runs/{thread}/report", response_class=PlainTextResponse)
    def report(thread: str):
        path = ctx.values(thread).get("report_path")
        if not path or not Path(path).is_file():
            raise HTTPException(404, "no report yet")
        return Path(path).read_text(encoding="utf-8")

    @api.get("/api/runs/{thread}/diff", response_class=PlainTextResponse)
    def diff(thread: str):
        v = ctx.values(thread)
        if not v.get("worktree") or not Path(v["worktree"]).is_dir():
            raise HTTPException(404, "nothing applied")
        return inputs.run(["git", "diff", "main...HEAD"], cwd=Path(v["worktree"]))

    @api.get("/api/runs/{thread}/events")
    async def events(thread: str):
        """Server-sent events: one per finished step, then `end` when the background work stops."""
        async def stream():
            sent = 0
            while True:
                job = ctx.jobs.get(thread)
                if job:
                    for e in job.events[sent:]:
                        yield f"data: {json.dumps(e)}\n\n"
                    sent = len(job.events)
                if not job or job.done:
                    yield f"event: end\ndata: {json.dumps({'error': job.error if job else ''})}\n\n"
                    return
                await asyncio.sleep(0.5)
        return StreamingResponse(stream(), media_type="text/event-stream")

    @api.post("/api/analyses")
    def analyse(body: Analyse):
        if body.watch:  # a watch of the guide's own source
            try:
                body.watch_json = str(ctx.watch_source().fetch(body.watch))
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
        if body.issue:
            thread, source = f"issue-{body.issue}", f"issue #{body.issue}"
        elif body.watch_json:
            thread, source = Path(body.watch_json).stem, body.watch_json
        else:
            raise HTTPException(400, "issue, watch or watch_json")
        if ctx.values(thread):
            raise HTTPException(409, f"{thread} already has a run")
        ctx.keep_steps(thread, body.steps)
        ctx.start(thread, "run", "watch", lambda g, job: ctx.follow(g, job, {"issue": body.issue, "source": source}))
        return {"thread": thread}

    @api.post("/api/runs/{thread}/resume")
    def resume(thread: str):
        """Continue a run stopped by an error, from its last finished step."""
        return ctx.resume_with(thread, "resume", None)

    @api.post("/api/fix")
    def report_errors(body: Report):
        findings = [line.strip() for line in body.text.splitlines() if line.strip()]
        if not findings:
            raise HTTPException(400, "no error reported")
        thread = ctx.free_thread(ctx.run_name(body.mode if body.mode in ("compact", "add") else "fix"))
        # Findings of a check keep the passages found when it ran; a line typed by hand has none
        excerpts, origin, notes = from_check(ctx, body.verification, findings) if body.verification else ({}, "", {})

        def work(graph, job: Job):
            deps = settings.make_deps(thread, "fix")
            guide = vault.reading_copy(settings.vault, settings.home)  # main up to date, whatever the folder holds
            items, proposal, usage, label = proposals(body, guide, findings, deps, excerpts, notes, thread)
            spent = sum(u.get("cost_usd", 0.0) for u in (usage if isinstance(usage, list) else [usage]))
            job.events.append({"t": time.time(), "node": "propose", "cost": round(spent, 2)})
            graph.update_state(thread_config(thread), fix.initial_state(label, items, proposal, usage, thread, body.mode, origin),
                               as_node="propose")
            ctx.follow(graph, job, None)

        ctx.keep_steps(thread, body.steps)
        if body.verification:  # the findings of a check, sent here: they are handled
            checks.mark(ctx, body.verification, findings, {"status": "fix", "thread": thread})
        ctx.start(thread, "fix", "fix", work)
        return {"thread": thread}

    return api
