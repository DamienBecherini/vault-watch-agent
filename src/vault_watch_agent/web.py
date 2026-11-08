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
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import BaseModel

from . import costs, fix, inputs
from .graph import Deps, build, usage_line

STATIC = Path(__file__).parent / "static"
AGENT_REPO = "https://github.com/DamienBecherini/vault-watch-agent"
# Steps shown while a run goes; a fix run starts at "number".
STEPS = ["collect", "triage", "locate", "propose", "number", "crosscheck", "report", "review",
         "apply", "mirror", "audits", "links", "publish"]


@dataclass
class Settings:
    vault: Path
    home: Path
    journal: Path
    make_deps: Callable[[str, str], Deps]  # (thread, kind) -> Deps with its own model clients
    list_issues: Callable[[], list[dict]] | None = None  # watch issues; default: gh
    pr_state: Callable[[str], str] | None = None  # "open", "merged" or "closed" for a PR url; default: gh
    repo: str = "DamienBecherini/ia-on-prem-vault"
    site: str = "https://ia-on-prem.damien.becherini.fr/"


@dataclass
class Job:
    thread: str
    action: str  # run, review, publish, fix, resume
    started: float = field(default_factory=time.time)
    events: list[dict] = field(default_factory=list)
    done: bool = False
    error: str = ""


class Analyse(BaseModel):
    issue: int | None = None
    watch_json: str | None = None


class Review(BaseModel):
    accept: list[str] | str  # "all", "none" or ids


class Publish(BaseModel):
    go: bool


class Report(BaseModel):
    text: str  # one reported error per line


def create_app(settings: Settings) -> FastAPI:
    settings.home.mkdir(parents=True, exist_ok=True)
    db = settings.home / "checkpoints.sqlite"
    saver = SqliteSaver(sqlite3.connect(db, check_same_thread=False))
    jobs: dict[str, Job] = {}
    lock = threading.Lock()
    app = FastAPI(title="vault-watch", docs_url=None, redoc_url=None)

    def graph_for(thread: str, kind: str):
        return build(settings.make_deps(thread, kind), saver)

    viewer = build(settings.make_deps("", "view"), saver)  # reads checkpoints, never calls the model

    def config(thread: str) -> dict:
        return {"configurable": {"thread_id": thread}, "max_concurrency": 4}

    # -- idle time, for `serve --idle-exit`: requests count, the health probe of a supervisor does not --
    app.state.last_activity = time.time()
    app.state.idle_seconds = lambda: 0.0 if any(not j.done for j in jobs.values()) else time.time() - app.state.last_activity

    # -- local only ----------------------------------------------------------------------------
    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost", "testserver"):
            return JSONResponse({"detail": "local access only"}, status_code=403)
        if request.method != "GET" and request.headers.get("x-vault-watch") != "1":
            return JSONResponse({"detail": "missing X-Vault-Watch header"}, status_code=403)
        if request.url.path != "/api/sante":
            app.state.last_activity = time.time()
        return await call_next(request)

    # -- background runs ---------------------------------------------------------------------
    def start(thread: str, action: str, kind: str, work: Callable[[object, Job], None]) -> Job:
        with lock:
            if thread in jobs and not jobs[thread].done:
                raise HTTPException(409, f"{thread} is already running")
            job = jobs[thread] = Job(thread, action)

        def target():
            try:
                work(graph_for(thread, kind), job)
            except Exception as e:  # shown on the page; the checkpoint keeps the last finished step
                job.error = f"{type(e).__name__}: {e}"
            finally:
                job.done = True

        threading.Thread(target=target, daemon=True, name=f"vault-watch {thread}").start()
        return job

    def follow(graph, job: Job, value) -> None:
        cost = 0.0
        for chunk in graph.stream(value, config(job.thread), stream_mode="updates"):
            for node, update in chunk.items():
                if node == "__interrupt__":
                    job.events.append({"t": time.time(), "node": "pause"})
                    continue
                for u in (update or {}).get("usage", []) if isinstance(update, dict) else []:
                    cost += u.get("cost_usd", 0.0)
                job.events.append({"t": time.time(), "node": node.split(":")[0], "cost": round(cost, 2)})

    # -- views of a run ----------------------------------------------------------------------
    def status(snapshot, job: Job | None) -> str:
        if job and not job.done:
            return "running"
        v = snapshot.values
        if not v:
            return "new"
        pending = [i.value for t in snapshot.tasks for i in t.interrupts]
        if pending:
            return pending[0]["step"]  # review or publish
        if snapshot.next:
            return "stopped"  # an error interrupted it; resume continues after the last finished step
        if v.get("pr_url"):
            return "published"
        if not v.get("accepted"):
            return "nothing-applied"
        return "not-published"

    pr_states: dict[str, str] = {}  # merged and closed are final, open is read again

    def pr_state(url: str) -> str:
        if pr_states.get(url) not in ("merged", "closed"):
            try:
                pr_states[url] = (settings.pr_state or gh_pr_state)(url)
            except Exception:  # gh missing or offline: the run still shows as published
                return ""
        return pr_states[url]

    def summary(thread: str) -> dict:
        snapshot = viewer.get_state(config(thread))
        v, job = snapshot.values, jobs.get(thread)
        st = status(snapshot, job)
        if st == "published":
            st = {"merged": "merged", "open": "pr-open", "closed": "pr-closed"}.get(pr_state(v["pr_url"]), st)
        return {
            "thread": thread, "status": st, "source": v.get("source", ""),
            "as_of": v.get("as_of", ""), "pr_url": v.get("pr_url", ""),
            "cost": round(sum(u.get("cost_usd", 0.0) for u in v.get("usage", [])), 2),
            "corrections": len(v.get("corrections", [])), "applied": len(v.get("applied", [])),
            "error": job.error if job else "",
        }

    def threads() -> list[str]:
        if not db.exists():
            return []
        with sqlite3.connect(db) as c:
            try:
                rows = c.execute("SELECT thread_id, MAX(checkpoint_id) FROM checkpoints GROUP BY thread_id").fetchall()
            except sqlite3.OperationalError:
                return []
        return [t for t, _ in sorted(rows, key=lambda r: r[1], reverse=True) if not t.startswith("eval-")]

    @app.get("/api/sante")
    def sante():
        return {"ok": True, "service": "vault-watch"}

    @app.get("/api/infos")
    def infos():
        return {"repo": settings.repo, "site": settings.site, "agent": AGENT_REPO}

    def run_of(issue: dict, known: list[str]) -> dict:
        """The run that counts for a watch: the published one, else the latest (re-runs are named issue-50b…)."""
        runs = [summary(t) for t in known if re.fullmatch(rf"issue-{issue['number']}[a-z]?", t)]
        if runs:
            return next((r for r in runs if r["pr_url"]), runs[0])
        new = summary(f"issue-{issue['number']}")
        if issue["state"] == "closed":
            new["status"] = "closed"  # handled by hand, before the agent or without it
        return new

    @app.get("/api/veilles")
    def veilles():
        issues, known = (settings.list_issues or list_issues(settings.repo))(), threads()
        return [{**i, "run": run_of(i, known)} for i in issues]

    @app.get("/api/runs")
    def runs():
        """Runs that are not a watch's (fix runs, files), newest first."""
        return [summary(t) for t in threads() if not re.fullmatch(r"issue-\d+[a-z]?", t)]

    @app.get("/api/runs/{thread}")
    def run_view(thread: str):
        snapshot = viewer.get_state(config(thread))
        v, job = snapshot.values, jobs.get(thread)
        if not v and not job:
            raise HTTPException(404, f"no run {thread}")
        pending = [i.value for t in snapshot.tasks for i in t.interrupts]
        items = {i["id"]: {"id": i["id"], "title": i["title"], "url": i["url"]} for i in v.get("items", [])}
        decisions = v.get("decisions", [])
        return {
            **summary(thread),
            "pause": pending[0] if pending else None,
            "job": {"action": job.action, "started": job.started, "events": job.events, "done": job.done,
                    "error": job.error} if job else None,
            "triage": {a: sum(1 for d in decisions if d["action"] == a) for a in ("correct", "addition", "drop")},
            "items": items,
            "corrections": v.get("corrections", []),
            "additions": [{**items.get(d["item_id"], {}), "reason": d["reason"]} for d in decisions if d["action"] == "addition"],
            "findings": v.get("findings", []),
            "claims_due": v.get("claims_due", []),
            "usage": usage_line(v.get("usage", [])),
            "accepted": v.get("accepted", []), "applied": v.get("applied", []), "branch": v.get("branch", ""),
            "mirrored": v.get("mirrored", []), "mirror_problems": v.get("mirror_problems", []),
            "link_problems": v.get("link_problems", []), "audit_ok": v.get("audit_ok"),
            "audit_log": v.get("audit_log", ""), "report_path": v.get("report_path", ""),
            "steps": STEPS,
        }

    @app.get("/api/runs/{thread}/rapport", response_class=PlainTextResponse)
    def rapport(thread: str):
        path = viewer.get_state(config(thread)).values.get("report_path")
        if not path or not Path(path).is_file():
            raise HTTPException(404, "no report yet")
        return Path(path).read_text(encoding="utf-8")

    @app.get("/api/runs/{thread}/diff", response_class=PlainTextResponse)
    def diff(thread: str):
        v = viewer.get_state(config(thread)).values
        if not v.get("worktree") or not Path(v["worktree"]).is_dir():
            raise HTTPException(404, "nothing applied")
        return inputs.run(["git", "diff", "main...HEAD"], cwd=Path(v["worktree"]))

    @app.get("/api/runs/{thread}/events")
    async def events(thread: str):
        """Server-sent events: one per finished step, then `end` when the background work stops."""
        async def stream():
            sent = 0
            while True:
                job = jobs.get(thread)
                if job:
                    for e in job.events[sent:]:
                        yield f"data: {json.dumps(e)}\n\n"
                    sent = len(job.events)
                if not job or job.done:
                    yield f"event: end\ndata: {json.dumps({'error': job.error if job else ''})}\n\n"
                    return
                await asyncio.sleep(0.5)
        return StreamingResponse(stream(), media_type="text/event-stream")

    # -- actions -------------------------------------------------------------------------------
    @app.post("/api/analyses")
    def analyse(body: Analyse):
        if not body.issue and not body.watch_json:
            raise HTTPException(400, "issue or watch_json")
        thread = f"issue-{body.issue}" if body.issue else Path(body.watch_json).stem
        if viewer.get_state(config(thread)).values:
            raise HTTPException(409, f"{thread} already has a run")
        source = f"issue #{body.issue}" if body.issue else body.watch_json
        start(thread, "run", "watch", lambda g, job: follow(g, job, {"issue": body.issue, "source": source}))
        return {"thread": thread}

    @app.post("/api/runs/{thread}/review")
    def review(thread: str, body: Review):
        answer = body.accept if isinstance(body.accept, str) else [i.strip() for i in body.accept if i.strip()]
        start(thread, "review", "watch", lambda g, job: follow(g, job, Command(resume=answer)))
        return {"thread": thread}

    @app.post("/api/runs/{thread}/publish")
    def publish(thread: str, body: Publish):
        start(thread, "publish", "watch", lambda g, job: follow(g, job, Command(resume=body.go)))
        return {"thread": thread}

    @app.post("/api/runs/{thread}/resume")
    def resume(thread: str):
        """Continue a run stopped by an error, from its last finished step."""
        start(thread, "resume", "watch", lambda g, job: follow(g, job, None))
        return {"thread": thread}

    @app.post("/api/fix")
    def report_errors(body: Report):
        findings = [line.strip() for line in body.text.splitlines() if line.strip()]
        if not findings:
            raise HTTPException(400, "no error reported")
        existing = set(threads())
        base = f"fix-{date.today().isoformat()}"
        thread = next(t for t in (base, *(f"{base}-{n}" for n in range(2, 100))) if t not in existing)

        def work(graph, job: Job):
            deps = settings.make_deps(thread, "fix")
            items, proposal, usage = fix.propose(settings.vault, findings, deps.llm)
            job.events.append({"t": time.time(), "node": "propose", "cost": round(usage.get("cost_usd", 0.0), 2)})
            graph.update_state(config(thread), fix.initial_state("errors reported in the interface", items, proposal, usage),
                               as_node="propose")
            follow(graph, job, None)

        start(thread, "fix", "fix", work)
        return {"thread": thread}

    @app.get("/api/couts")
    def couts():
        entries = costs.load(settings.journal)
        return {by: costs.rows(entries, by) for by in ("month", "run")}

    # -- page ------------------------------------------------------------------------------------
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app


def gh_pr_state(url: str) -> str:
    return inputs.run(["gh", "pr", "view", url, "--json", "state", "--jq", ".state"]).strip().lower()


def list_issues(repo: str) -> Callable[[], list[dict]]:
    """Watch issues of the vault (label « veille »), newest first, from gh."""
    def fetch() -> list[dict]:
        out = inputs.run(["gh", "issue", "list", "--repo", repo, "--label", "veille", "--state", "all",
                          "--limit", "12", "--json", "number,title,state,createdAt,labels"])
        return [{"number": i["number"], "title": i["title"], "state": i["state"].lower(), "date": i["createdAt"][:10],
                 "urgent": any(l["name"] == "urgent" for l in i["labels"]),
                 "items": int(m.group(1)) if (m := re.search(r"(\d+) éléments", i["title"])) else None}
                for i in json.loads(out)]
    return fetch
