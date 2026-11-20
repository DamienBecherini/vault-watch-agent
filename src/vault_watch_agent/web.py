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
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import BaseModel

from . import __version__
from . import config as user_settings  # `config` is a helper of create_app
from . import compact, costs, fix, forge, inputs, llm, news, prices, sourcecheck, sources, steps, vault, verify
from . import watches as watches_mod
from .graph import Deps, build, usage_line

STATIC = Path(__file__).parent / "static"
AGENT_REPO = "https://github.com/DamienBecherini/vault-watch-agent"
# Steps shown while a run goes; a fix run starts at "number".
STEPS = ["collect", "triage", "locate", "propose", "number", "crosscheck", "report", "review",
         "apply", "mirror", "audits", "links", "publish"]
# What a running job is doing, in the health response.
# The effort each step of a role asks for in the code (graph.py, crosscheck.py, fix.py, verify.py), for the Settings
# page: what "lower" and "higher" make of them. To keep in step with the code when an effort changes there.
# What each step of a role runs at, shown in the Settings: read from the one table of the steps (steps.py)
STEP_EFFORTS = {role: [(s.id, s.effort) for s in steps.of_role(role)] for role in ("reasoning", "translator")}
ACTIVITIES = {"run": "analysing", "review": "applying the review", "publish": "publishing", "fix": "fixing", "resume": "resuming",
              "sources": "checking the sources"}


def write_json(path: Path, data: dict) -> None:
    """Writes a file the page reads while a check runs: aside, then put in place in one go, so a read never finds
    it empty or half written. Windows refuses the swap while a reader holds the file: tried again for a moment."""
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    for attempt in range(40):
        try:
            os.replace(partial, path)
            return
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.05)


def read_json(path: Path):
    """Reads a file `write_json` may be putting in place at that moment: Windows refuses to open it during the swap
    (PermissionError), tried again for a moment. A file that is not there is still an error at once."""
    for attempt in range(40):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.05)


def _version() -> str:
    """The version of the code that runs (the source, not the copy an install may have left in site-packages)."""
    return __version__


@dataclass
class Settings:
    vault: Path
    home: Path  # the guide's working folder: checkpoints, verifications, worktrees
    journal: Path
    make_deps: Callable[[str, str], Deps]  # (thread, kind) -> Deps with its own model clients
    list_issues: Callable[[], list[dict]] | None = None  # watch issues; default: gh
    pr_state: Callable[[str], str] | None = None  # "open", "merged" or "closed" for a PR url; default: gh
    repo: str = ""  # "" = the manifest's [guide] repository (and "" there: a local guide, no issue to list)
    site: str = ""  # "" = the manifest's [guide] site
    notifier: Callable[[str, str, str], object] | None = None  # (title, body, url to open): notify.toast with --notify
    notify_lang: str = "en"
    base_url: str = "http://127.0.0.1:4430/"
    idle_exit: int = 0  # seconds of inactivity before `serve --idle-exit` stops the server (0: never)
    config_home: Path | None = None  # where the user's settings are (shared by the guides); None: `home`


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
    watch: str | None = None  # the id of a watch of the guide's source (a file of the guide)
    steps: dict = {}  # for this run alone: {step: {engine, model, effort}} (config.run_steps)


class Review(BaseModel):
    accept: list[str] | str  # "all", "none" or ids


class Publish(BaseModel):
    go: bool


class Report(BaseModel):
    text: str  # one reported error per line
    verification: str | None = None  # the check these findings come from, to mark them as sent
    # translation: fix the mirror pages against the source ones; compact: trims for what weighs (compact.py);
    # add: what is new, checked on the web and written where it belongs (news.py)
    mode: Literal["fix", "translation", "compact", "add"] = "fix"
    deep: list[str] = []  # an addition run: the leads to dig deeper, each in a call of its own (news.propose)
    steps: dict = {}  # for this run alone: {step: {engine, model, effort}} (config.run_steps)


class Handle(BaseModel):
    findings: list[str]
    status: Literal["dismissed", "open"]


class Changes(BaseModel):
    ids: list[str]  # the proposals of the last source check to apply (S1, S4…)


class Later(BaseModel):
    ids: list[str]  # the proposals of the last source check to put off until the next one
    on: bool = True  # False: decide them now after all


class Verification(BaseModel):
    checks: list[str]  # ids of verify.CHECKS
    chapters: list[str] = []  # the check « explore »: the chapters to explore (all of them when empty)
    steps: dict = {}  # for this verification alone: {step: {engine, model, effort}} (config.run_steps)


class UserSettings(BaseModel):  # config.py: the key is a reference to where it is, never the key
    engine: str = ""
    key: str = ""
    models: dict[str, str] = {}
    effort: dict[str, str] = {}
    steps: dict[str, dict] | None = None  # the steps set apart from their role; None: keep those already set
    prices: dict[str, dict] | None = None  # None: keep the prices already set (a page that does not show them)
    engines: dict[str, dict] | None = None  # the other engines' options; None: keep those already set


def create_app(settings: Settings) -> FastAPI:
    guide = vault.guide_of(settings.vault)  # the repository and the site shown, unless given
    settings.repo, settings.site = settings.repo or guide.repository, settings.site or guide.site
    forge.use(forge.for_guide(guide))  # GitHub, or the Gitea server the manifest names
    settings.home.mkdir(parents=True, exist_ok=True)
    cfg_home = settings.config_home or settings.home  # the user's settings
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
    app.state.jobs = jobs

    def idle_seconds() -> float:
        if any(not j.done for j in list(jobs.values())):
            app.state.last_activity = time.time()  # the delay runs from the end of the work
            return 0.0
        return time.time() - app.state.last_activity

    app.state.idle_seconds = idle_seconds

    # -- local only ----------------------------------------------------------------------------
    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost", "testserver"):
            return JSONResponse({"detail": "local access only"}, status_code=403)
        if request.method != "GET" and request.headers.get("x-vault-watch") != "1":
            return JSONResponse({"detail": "missing X-Vault-Watch header"}, status_code=403)
        if request.url.path not in ("/api/health", "/api/notices"):  # probes: a page left open is not someone using it
            app.state.last_activity = time.time()
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            # The page and its scripts go together: the browser asks again each time (a 304 when nothing changed),
            # so an update never leaves an old page with new scripts.
            response.headers["Cache-Control"] = "no-cache"
        return response

    # -- notifications when background work stops: what the human has to do next. On the desktop with
    #    `serve --notify` (settings.notifier), and in the browser of a page whose bell is on (GET /api/notices) --
    MESSAGES = {
        "fr": {"review": ("Relecture à faire", "{n} correction(s) proposée(s) : à toi de trancher."),
               "publish": ("Publication à valider", "Corrections appliquées et contrôlées : la PR attend ton feu vert."),
               "pr": ("Pull request ouverte", "À relire et fusionner sur {forge}."),
               "nothing-applied": ("Passage clos", "Aucune correction appliquée."),
               "error": ("Passage interrompu", "Erreur : {error}"),
               "verif": ("Vérification terminée", "{n} piste(s) à traiter."), "verif-error": ("Vérification interrompue", "{error}")},
        "en": {"review": ("Review pending", "{n} correction(s) proposed: your call."),
               "publish": ("Publish pending", "Corrections applied and checked: the PR waits for your go-ahead."),
               "pr": ("Pull request opened", "To review and merge on {forge}."),
               "nothing-applied": ("Run closed", "No correction applied."),
               "error": ("Run stopped", "Error: {error}"),
               "verif": ("Check finished", "{n} lead(s) to handle."), "verif-error": ("Check stopped", "{error}")},
    }

    notices: list[dict] = []  # one per background work that stopped with something to say, since the server started

    def announce(job: Job) -> None:
        if job.thread.startswith("verif-"):
            v = verif_view(verif_path(job.thread))
            key, n, page = ("verif-error" if job.error else "verif"), v["counts"]["open"], f"#/check/{job.thread}"
        else:
            s = summary(job.thread)
            key = ("error" if job.error else "pr" if s["pr_url"] else s["status"])
            n, page = s["corrections"], f"#/run/{job.thread}"
        if key not in MESSAGES["en"]:
            return
        texts = {lang: {"title": f"vault-watch · {job.thread} · {m[key][0]}", "body": m[key][1].format(n=n, error=job.error[:150], forge=forge.get().name)}
                 for lang, m in MESSAGES.items()}
        with lock:
            notices.append({"id": len(notices) + 1, "t": time.time(), "thread": job.thread, "key": key, "page": page, **texts})
        if settings.notifier:
            mine = texts.get(settings.notify_lang, texts["en"])
            settings.notifier(mine["title"], mine["body"], settings.base_url + page)

    @app.get("/api/notices")
    def notices_view(since: int = -1):
        """What stopped since the notice `since`, for the notifications of the page, in both languages. A page that
        just opened asks without `since`: it gets the last id only, and is told of what happens from then on."""
        with lock:
            return {"last": len(notices), "notices": [n for n in notices if n["id"] > since] if since >= 0 else []}

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
                app.state.last_activity = time.time()
                try:
                    announce(job)
                except Exception:  # a notification never breaks a run
                    pass

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

    # What the forge says, kept so that a page does not wait for it at every display (each question is a call to
    # `gh` over the network, half a second or more). The state of a pull request: merged and closed are final and
    # written to the disk (a server just started does not ask again for every past run); open is asked again, at
    # most once in FORGE_FRESH seconds. The list of the watch issues: kept FORGE_FRESH seconds too. The tests give
    # their own answers (settings.pr_state, settings.list_issues): nothing is kept then, each call asks.
    FORGE_FRESH = 20
    pr_file = settings.home / "pr-states.json"
    try:
        pr_states: dict[str, str] = {u: s for u, s in json.loads(pr_file.read_text(encoding="utf-8")).items()
                                     if s in ("merged", "closed")}
    except (OSError, ValueError, AttributeError):
        pr_states = {}
    pr_asked: dict[str, float] = {}

    def pr_due(url: str) -> bool:
        if pr_states.get(url) in ("merged", "closed"):
            return False
        return settings.pr_state is not None or time.time() - pr_asked.get(url, 0) > FORGE_FRESH

    def pr_state(url: str) -> str:
        if pr_due(url):
            try:
                pr_states[url] = (settings.pr_state or gh_pr_state)(url)
            except Exception:  # gh missing or offline: the run still shows as published
                return ""
            pr_asked[url] = time.time()
            if pr_states[url] in ("merged", "closed"):
                try:
                    settings.home.mkdir(parents=True, exist_ok=True)
                    write_json(pr_file, {u: s for u, s in pr_states.items() if s in ("merged", "closed")})
                except OSError:
                    pass  # asked again after the next start, nothing more
        return pr_states.get(url, "")

    def warm(names: list[str]) -> None:
        """Asks the forge at once, side by side, for the pull requests of these runs whose state may have moved: a
        page that lists ten runs waits for one answer, not ten in a row."""
        urls = {viewer.get_state(config(t)).values.get("pr_url") for t in names}
        due = [u for u in urls if u and pr_due(u)]
        if len(due) > 1:
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(pr_state, due))

    listed: dict = {}  # the watches of the forge: {"at": when asked, "found": the list}

    def list_watches() -> list[dict]:
        src = watch_source()
        if src.kind != "issue" or settings.list_issues is not None:
            return src.list()  # files of the machine, or the list of a test: read each time
        if time.time() - listed.get("at", 0) > FORGE_FRESH:
            listed.update(found=src.list(), at=time.time())
        return listed["found"]

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

    @app.get("/api/health")
    def health():
        """The "local service" contract (v2) shared with the launcher: state, busy or not, idle countdown."""
        running = [j for j in list(jobs.values()) if not j.done]
        idle = app.state.idle_seconds()
        remaining = None if running or not settings.idle_exit else round(max(0.0, settings.idle_exit - idle), 1)
        return {"state": "ready", "contract": 2, "service": "vault-watch", "version": _version(),
                "busy": bool(running), "activity": ACTIVITIES.get(running[0].action, running[0].action) if running else "",
                "remaining_work_s": None, "idle": {"timeout_s": settings.idle_exit, "remaining_s": remaining}}

    def engine_now() -> str:
        """The engine the next run would use; "" when the settings cannot be read (the Settings page says why)."""
        try:
            return llm.engine(user_settings.load(cfg_home)["engine"])
        except (user_settings.ConfigError, llm.ModelError):
            return ""

    def billing_now() -> str:
        """How the next run is paid, without making a client: token, subscription, or none (a local model)."""
        try:
            cfg = user_settings.load(cfg_home)
            return llm.billing_of(cfg, llm.engine(cfg["engine"]))
        except (user_settings.ConfigError, llm.ModelError):
            return "token"

    def own_steps(text: str) -> dict:
        """What a page chose for the steps of the run it is about to start (`steps`, as JSON in a query): checked."""
        try:
            return user_settings.check_steps(json.loads(text) if text else {})
        except ValueError as e:  # ConfigError is one
            raise HTTPException(400, f"steps: {e}") from e

    def keep_steps(thread: str, given: dict) -> None:
        """Keeps what a run sets for its own steps, before it starts (cli.make_deps reads it for each of its jobs)."""
        try:
            user_settings.save_run_steps(settings.home, thread, given)
        except ValueError as e:
            raise HTTPException(400, f"steps: {e}") from e

    def steps_view(cfg: dict) -> list[dict]:
        """Each step as it would run with `cfg`: its engine, model, effort, and how its calls are paid."""
        out = []
        for s in steps.STEPS.values():
            if not s.shown:
                continue
            name = llm.step_engine(cfg, s.id)
            out.append({"step": s.id, "role": s.role, "engine": name, "engine_label": llm.engines()[name].label,
                        "model": llm.step_model(cfg, s.id), "effort": llm.step_effort(cfg, s.id),
                        "billing": llm.billing_of(cfg, name), "own": s.id in cfg["steps"]})
        return out

    @app.get("/api/steps")
    def steps_now(steps: str = ""):
        """How each step would run now: with the settings, and with what the page chose for one run laid over them
        (`steps`). With it, what a page needs to offer another choice: the engines, the efforts."""
        cfg = user_settings.load(cfg_home)
        cfg["steps"] = user_settings.over(cfg["steps"], own_steps(steps))
        return {"steps": steps_view(cfg), "efforts": list(llm.EFFORT_LEVELS),
                "engines": [{"name": k.name, "label": k.label} for k in llm.engines().values()],
                "forced": os.environ.get("VAULT_WATCH_ENGINE", "").strip().lower()}

    def forge_repo_url() -> str:
        """The repository's web page on its forge ("" for a local guide)."""
        if not settings.repo:
            return ""
        base = guide.forge_url if guide.forge == "gitea" else "https://github.com"
        return f"{base}/{settings.repo}"

    @app.get("/api/info")
    def info():
        return {"repo": settings.repo, "site": settings.site, "agent": AGENT_REPO, "engine": engine_now(),
                "billing": billing_now(),
                "guide": guide.name, "watch_source": guide.watch.source, "forge": forge.get().name,
                "repo_url": forge_repo_url(),
                "version": _version()}

    # -- settings of the user (config.py): engine, reference to the API key, models -----------------
    def price_table(cfg: dict | None = None) -> prices.Prices:
        return prices.Prices.of_home(cfg_home, cfg if cfg is not None else user_settings.load(cfg_home))

    def prices_view(cfg: dict) -> dict:
        """Each priced model (the ones in use first) with its rates and where they come from, and the fetched list."""
        try:
            current = [llm.model_of(cfg, role) for role in user_settings.MODELS] + [
                own["model"] for own in cfg["steps"].values() if own.get("model")]
        except llm.ModelError:
            current = []
        table, in_use = price_table(cfg), [m for m in dict.fromkeys(current + list(cfg["models"].values())) if m]
        without = price_table({**cfg, "prices": {}})  # what a model costs when the user sets no price of their own
        rows = []
        for model in list(dict.fromkeys(in_use + list(cfg["prices"]) + table.known())):
            p, b = table.of(model), without.of(model)
            rows.append({"id": model, "in_use": model in in_use, "rates": p.rates() if p else None, "date": p.date if p else "",
                         "origin": p.origin if p else "", "label": p.label if p else "no price",
                         "base": {"rates": b.rates(), "origin": b.origin, "date": b.date} if b else None})
        fetched = next(((date, len(t)) for o, date, t in table.sources if o == "fetched" and t), None)
        return {"models": rows, "fetched": {"date": fetched[0], "models": fetched[1]} if fetched else None,
                "source": prices.LITELLM, "web_search_usd": table.web_search_usd}

    def settings_view(cfg: dict) -> dict:
        """The settings with what the page shows beside them: the engine in use, Claude Code on this machine,
        whether the reference gives a key (never the key), the models offered when the API cannot list them, the
        efforts of a role and the level each step of that role then runs at."""
        return {**cfg, "engine_now": llm.engine(cfg["engine"]),
                "engine_forced": os.environ.get("VAULT_WATCH_ENGINE", "").strip().lower(),
                "claude_code": llm.claude_code_status(), "key_status": user_settings.key_status(cfg["key"]),
                "key_forms": user_settings.KEY_FORMS,
                "engines_installed": [{"name": k.name, "label": k.label} for k in llm.engines().values()],
                "engine_options": {k.name: k.options for k in llm.engines().values() if k.options},
                "engine_errors": llm.ENGINE_ERRORS,
                "guide": vault.guide_of(settings.vault).summary(),  # read-only: from its manifest
                "price_table": prices_view(cfg),
                "choices": {"models": user_settings.MODELS, "effort": user_settings.EFFORTS,
                            "levels": list(llm.EFFORT_LEVELS),  # what a step set apart may run at
                            "steps": {role: [{"step": step, "effort": effort,
                                              "levels": {e: llm.shift_effort(effort, llm.EFFORT_STEPS[e]) for e in user_settings.EFFORTS}}
                                             for step, effort in steps]
                                      for role, steps in STEP_EFFORTS.items()}}}

    @app.get("/api/models")
    def models_view(key: str = "", engine: str = "", base_url: str = ""):
        """The Claude models the API key can use, read from the Models API (`key`: a reference to try before saving
        it, else the one of the settings); without a key that answers, the models known to the agent and why.
        `engine`: another engine's models (the OpenAI-compatible server's: `base_url` and `key` tried before saving)."""
        if engine and engine not in ("api", "claude-code"):
            cfg, kind = user_settings.load(cfg_home), llm.engines().get(engine)
            if not kind or not kind.models:
                return {"source": "none", "models": [], "error": f"{engine}: no list of models"}
            options = {**(cfg["engines"].get(engine) or {}), **({"base_url": base_url} if base_url else {}),
                       **({"key": key} if key else {})}
            try:
                return {"source": engine, "models": kind.models({**cfg, "engines": {**cfg["engines"], engine: options}}),
                        "error": ""}
            except (llm.ModelError, user_settings.ConfigError) as e:
                return {"source": engine, "models": [], "error": str(e)}
        reference = key or user_settings.load(cfg_home)["key"]
        try:
            return {"source": "api", "models": llm.list_models(reference, prices=price_table()), "error": ""}
        except (llm.ModelError, user_settings.ConfigError) as e:
            known = dict.fromkeys(m for names in user_settings.MODELS.values() for m in names)
            return {"source": "known", "error": str(e),
                    "models": [{"id": m, "name": m, "context": None, "priced": price_table().of(m) is not None} for m in known]}

    @app.get("/api/settings")
    def settings_get():
        try:
            return settings_view(user_settings.load(cfg_home))
        except (user_settings.ConfigError, llm.ModelError) as e:
            raise HTTPException(500, str(e)) from e

    pending: dict = {}  # the list fetched last, until the user applies it or fetches again

    @app.post("/api/prices/fetch")
    def prices_fetch():
        """Reads LiteLLM's public list and says what it would change; nothing is replaced before /apply."""
        from datetime import date

        try:
            fetched = prices.fetch(date.today().isoformat())
        except ValueError as e:
            raise HTTPException(502, str(e)) from e
        pending.clear()
        pending.update(fetched)
        return {"date": fetched["date"], "models": len(fetched["models"]), "estimated": fetched["estimated"],
                "changes": prices.diff(price_table(), fetched)}

    @app.post("/api/prices/apply")
    def prices_apply():
        if not pending:
            raise HTTPException(409, "fetch the list first")
        prices.save(cfg_home, dict(pending))
        pending.clear()
        return settings_view(user_settings.load(cfg_home))

    @app.post("/api/settings")
    def settings_save(body: UserSettings):
        try:
            given = body.model_dump()
            for kept in ("prices", "steps", "engines"):  # a page that does not show them does not erase them
                if given[kept] is None:
                    given[kept] = user_settings.load(cfg_home)[kept]
            return settings_view(user_settings.save(cfg_home, given))
        except (user_settings.ConfigError, llm.ModelError) as e:
            raise HTTPException(400, str(e)) from e

    def run_of(watch: dict, known: list[str]) -> dict:
        """The run that counts for a watch: the published one, else the latest (re-runs are named issue-50b…)."""
        runs = [summary(t) for t in known if re.fullmatch(rf"{re.escape(watch['thread'])}[a-z]?", t)]
        if runs:
            return next((r for r in runs if r["pr_url"]), runs[0])
        new = summary(watch["thread"])
        if watch["state"] == "closed":
            new["status"] = "closed"  # handled by hand, before the agent or without it
        return new

    def watch_source():
        """The guide's watch source (manifest [watch]); the tests give their own list of issues."""
        return watches_mod.of(vault.guide_of(settings.vault), settings.home, settings.list_issues)

    @app.get("/api/watches")
    def watches():
        found, known = list_watches(), threads()
        warm(known)
        return [{**w, "run": run_of(w, known)} for w in found]

    @app.get("/api/runs")
    def runs():
        """Runs that are not a watch's (fix runs, files of another folder), newest first."""
        src = watch_source()
        mine = {w["thread"] for w in src.list()} if src.kind in ("file", "feeds") else set()
        warm(threads())
        return [summary(t) for t in threads()
                if not re.fullmatch(r"issue-\d+[a-z]?", t) and re.sub(r"[a-z]$", "", t) not in mine and t not in mine]

    @app.get("/api/runs/{thread}")
    def run_view(thread: str):
        snapshot = viewer.get_state(config(thread))
        v, job = snapshot.values, jobs.get(thread)
        if not v and not job:
            raise HTTPException(404, f"no run {thread}")
        pending = [i.value for t in snapshot.tasks for i in t.interrupts]
        items = {i["id"]: {"id": i["id"], "title": i["title"], "url": i["url"]} for i in v.get("items", [])}
        decisions = v.get("decisions", [])
        usage = v.get("usage", [])
        return {
            **summary(thread),
            "pause": pending[0] if pending else None,
            # Made so far without a bill (a subscription, a local model) while the settings now name a billed
            # engine: the steps left (the translation) would be billed. The review page says so before the click.
            "billed_next": bool(usage) and not any(u.get("cost_usd") for u in usage) and billing_now() == "token",
            "job": {"action": job.action, "started": job.started, "events": job.events, "done": job.done,
                    "error": job.error} if job else None,
            "triage": {a: sum(1 for d in decisions if d["action"] == a) for a in ("correct", "addition", "drop")},
            "items": items,
            "corrections": v.get("corrections", []),
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
            "link_problems": v.get("link_problems", []), "audit_ok": v.get("audit_ok"),
            "audit_log": v.get("audit_log", ""), "report_path": v.get("report_path", ""),
            "steps": STEPS,
        }

    @app.get("/api/runs/{thread}/report", response_class=PlainTextResponse)
    def report(thread: str):
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
    @app.post("/api/collect")
    def collect_now():
        """A new watch from the guide's feeds (`[watch] source = "feeds"`): no model, nothing billed."""
        from . import collect

        src = watch_source()
        if src.kind != "feeds":
            raise HTTPException(400, 'the guide\'s watches do not come from its feeds ([watch] source = "feeds")')
        try:
            path = src.collect()
        except collect.CollectError as e:
            raise HTTPException(400, str(e)) from e
        return next(w for w in src.list() if w["thread"] == path.stem)

    @app.post("/api/analyses")
    def analyse(body: Analyse):
        if body.watch:  # a watch of the guide's own source
            try:
                body.watch_json = str(watch_source().fetch(body.watch))
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
        if not body.issue and not body.watch_json:
            raise HTTPException(400, "issue, watch or watch_json")
        thread = f"issue-{body.issue}" if body.issue else Path(body.watch_json).stem
        if viewer.get_state(config(thread)).values:
            raise HTTPException(409, f"{thread} already has a run")
        source = f"issue #{body.issue}" if body.issue else body.watch_json
        keep_steps(thread, body.steps)
        start(thread, "run", "watch", lambda g, job: follow(g, job, {"issue": body.issue, "source": source}))
        return {"thread": thread}

    @app.post("/api/runs/{thread}/review")
    def review(thread: str, body: Review):
        # "all", "none", or ids: a list, or one string "C1,C3" (sent as such on 17/11/2026, it was read as a set of
        # characters and the run ended with nothing applied)
        accept = body.accept.strip() if isinstance(body.accept, str) else body.accept
        answer = accept if accept in ("all", "none") else [
            i.strip() for i in (accept.split(",") if isinstance(accept, str) else accept) if i.strip()]
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
        existing = set(threads()) | set(jobs)  # a run just started has no checkpoint yet
        base = f"{body.mode if body.mode in ('compact', 'add') else 'fix'}-{date.today().isoformat()}"
        thread = next(t for t in (base, *(f"{base}-{n}" for n in range(2, 100))) if t not in existing)
        # Findings of a check keep the passages found when it ran; a line typed by hand has none
        excerpts = {}
        if body.verification:
            results = read_json(verif_path(body.verification))["results"]
            excerpts = {f: e for r in results.values() for f, e in r.get("excerpts", {}).items() if f in findings}

        def work(graph, job: Job):
            deps = settings.make_deps(thread, "fix")
            guide = vault.reading_copy(settings.vault, settings.home)  # main up to date, whatever the folder holds
            if body.mode == "translation":
                items, proposal, usage = fix.propose_translation(guide, findings, deps.translator or deps.llm,
                                                                 excerpts)
                label = "translation divergences reported in the interface"
            elif body.mode == "compact":
                items, proposal, usage = compact.propose(guide, findings, deps.llm, excerpts)
                label = thread
            elif body.mode == "add":
                items, proposal, usage = news.propose(guide, findings, deps.llm, excerpts, deep=body.deep)
                label = thread
            else:
                items, proposal, usage = fix.propose(guide, findings, deps.llm, excerpts=excerpts)
                label = "errors reported in the interface"
            spent = sum(u.get("cost_usd", 0.0) for u in (usage if isinstance(usage, list) else [usage]))
            job.events.append({"t": time.time(), "node": "propose", "cost": round(spent, 2)})
            graph.update_state(config(thread), fix.initial_state(label, items, proposal, usage, thread, body.mode),
                               as_node="propose")
            follow(graph, job, None)

        keep_steps(thread, body.steps)
        if body.verification:  # the findings of a check, sent here: they are handled
            mark(body.verification, findings, {"status": "fix", "thread": thread})
        start(thread, "fix", "fix", work)
        return {"thread": thread}

    @app.get("/api/costs")
    def costs_view():
        entries = costs.load(settings.journal)
        return {**{by: costs.rows(entries, by) for by in ("month", "run")}, "origins": costs.origins(entries)}

    # -- the sources of the watch (sources.py): what each feed brought, from the watches and runs kept here ----
    outcomes: dict[str, tuple[str, dict]] = {}  # thread -> (its last checkpoint, what became of each item)

    def watch_outcomes() -> list[dict]:
        """What became of the items of each watch run; a run is read again only when it has moved."""
        if not db.exists():
            return []
        with sqlite3.connect(db) as c:
            try:
                rows = c.execute("SELECT thread_id, MAX(checkpoint_id) FROM checkpoints GROUP BY thread_id").fetchall()
            except sqlite3.OperationalError:
                return []
        found = []
        for thread, last in rows:
            if thread.startswith("eval-"):  # a replay of a watch already counted
                continue
            if outcomes.get(thread, ("",))[0] != last:
                outcomes[thread] = (last, sources.run_outcomes(viewer.get_state(config(thread)).values))
            found.append(outcomes[thread][1])
        return found

    check_file = settings.home / "sources-check.json"  # the last check: what each source answered, the proposals
    CHECK = "sources-check"  # its job, for the page that follows it and for /api/health

    def last_check() -> dict | None:
        try:
            return read_json(check_file)
        except (OSError, ValueError):
            return None

    def settle(check: dict) -> dict:
        """What became of the pull requests opened from the page. Merged: their proposals are done, and the copy
        of the guide the page reads is brought up to date (the list now holds the change). Closed without a
        merge: their proposals are to decide again. Read from the forge until it is one or the other."""
        moved = False
        for done in check.get("applied", []):
            if not done.get("pr_url") or done.get("state") in ("merged", "closed"):
                continue
            state = pr_state(done["pr_url"])
            if state not in ("merged", "closed"):
                continue
            done["state"], moved = state, True
            for p in check["proposals"]:
                if p["id"] in done["ids"]:
                    if state == "merged":
                        p["merged"] = True
                    else:
                        p.pop("applied", None)
            if state == "merged":
                try:
                    vault.reading_copy(settings.vault, settings.home)
                except RuntimeError:  # offline: the next check of the sources does it
                    pass
        if moved:
            with lock:
                write_json(check_file, check)
        return check

    def merged_guide():
        """The guide as merged, for the list of its feeds: the copy the checks keep up to date, else its folder."""
        guide = vault.guide_of(settings.vault)
        copy = settings.home / "worktrees" / f"read-{guide.base_branch}"
        return vault.guide_of(copy) if (copy / ".git").exists() and (copy / guide.watch.feeds).is_file() else guide

    @app.get("/api/sources")
    def sources_view():
        job, check = jobs.get(CHECK), last_check()
        if check:
            check = settle(check)
        data = sources.summary(merged_guide(), settings.home, watch_outcomes())
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

    @app.post("/api/sources/check")
    def sources_check():
        """Asks every source and reads the guide (network, no model, nothing billed); followed by GET /api/sources."""
        with lock:
            if CHECK in jobs and not jobs[CHECK].done:
                raise HTTPException(409, "the sources are already being checked")
            job = jobs[CHECK] = Job(CHECK, "sources")

        def work():
            try:
                guide = vault.guide_of(vault.reading_copy(settings.vault, settings.home))  # the guide as merged
                result = sourcecheck.check(guide, settings.home, watch_outcomes(),
                                           progress=lambda fid: job.events.append({"t": time.time(), "node": fid}))
                write_json(check_file, {**result, "applied": []})
            except Exception as e:  # noqa: BLE001 - shown on the page
                job.error = f"{type(e).__name__}: {e}"[:500]
            finally:
                job.done = True
                app.state.last_activity = time.time()

        threading.Thread(target=work, daemon=True, name="vault-watch sources").start()
        return {"started": True}

    @app.post("/api/sources/apply")
    def sources_apply(body: Changes):
        """The chosen proposals on a branch of the guide, and a pull request when it has a repository."""
        check = last_check()
        chosen = [p for p in (check or {}).get("proposals", []) if p["id"] in body.ids and not p.get("applied")]
        if not chosen:
            raise HTTPException(400, "none of these proposals is to apply (check the sources again)")
        guide = vault.guide_of(settings.vault)
        try:
            done = sourcecheck.publish(guide, settings.home, chosen, today=date.today().isoformat(),
                                       open_pull_request=forge.get().open_pull_request)
        except (RuntimeError, ValueError) as e:  # git, the forge, or a file that changed since the check
            raise HTTPException(409, str(e)[:500]) from e
        with lock:
            check = last_check() or check
            for p in check["proposals"]:
                if p["id"] in {c["id"] for c in chosen}:
                    p["applied"] = done
            check.setdefault("applied", []).append({**done, "ids": [c["id"] for c in chosen], "t": time.time()})
            write_json(check_file, check)
        return done

    @app.post("/api/sources/later")
    def sources_later(body: Later):
        """Put proposals off until the next check: they leave the list to decide, nothing changes in the guide. The
        next check writes its own proposals: what is still true then comes back."""
        with lock:
            check = last_check()
            chosen = [p for p in (check or {}).get("proposals", []) if p["id"] in body.ids and not p.get("applied")]
            if not chosen:
                raise HTTPException(400, "none of these proposals is to decide (check the sources again)")
            for p in chosen:
                if body.on:
                    p["later"] = time.time()
                else:
                    p.pop("later", None)
            write_json(check_file, check)
        return {"later": [p["id"] for p in check["proposals"] if p.get("later")]}

    # -- health check of the guide (verify.py): one JSON file per verification ---------------------
    verifs = settings.home / "verifications"

    def verif_files() -> list[Path]:
        return sorted(verifs.glob("verif-*.json"), reverse=True) if verifs.is_dir() else []

    def verif_view(path: Path) -> dict:
        """The verification with what became of its findings: open, sent to a fix run, or dismissed."""
        data = read_json(path)
        job = jobs.get(data["id"])
        data["running"] = bool(job and not job.done)
        # Stopped before its last check (the server was closed meanwhile): what it found stays usable, the checks
        # it did not reach are listed, and nothing will ever finish it.
        data["interrupted"] = not data.get("done") and not data["running"]
        data["missing"] = [c for c in data.get("checks", []) if c not in data["results"]] if data["interrupted"] else []
        # The check being run: the last one started (the page marks it « running » instead of « waiting »)
        started = [e["node"][6:] for e in (job.events if data["running"] else []) if e.get("node", "").startswith("start:")]
        data["current"] = started[-1] if started else ""
        data["error"] = (job.error if job else "") or data.get("error", "")
        handled = data.setdefault("handled", {})
        every = [f for r in data["results"].values() for f in r.get("findings", [])]
        counts = {"open": 0, "fix": 0, "dismissed": 0}
        for f in every:
            counts[handled.get(f, {}).get("status", "open")] += 1
        data["counts"] = counts
        for step, r in data["results"].items():  # per check: findings still open, and where they can go
            r["open"] = sum(1 for f in r.get("findings", []) if f not in handled)
            if step in verify.BY_ID:  # as the check is now, not as it was when this verification ran
                r["fixable"], r["mode"] = verify.BY_ID[step].fixable, verify.BY_ID[step].fix_mode
        # The fix runs the findings went to, with where they stand (review, publish, PR to merge, merged)
        data["runs"] = {}
        for h in handled.values():
            if h.get("status") == "fix" and h["thread"] not in data["runs"]:
                s = summary(h["thread"])
                data["runs"][h["thread"]] = {"status": s["status"], "pr_url": s["pr_url"]}
        data["status"] = ("running" if data["running"] else "to-handle" if counts["open"]
                          else "handled" if every else "clear")
        return data

    def verif_path(vid: str) -> Path:
        path = verifs / f"{vid}.json"
        if not re.fullmatch(r"verif-[\d-]+", vid) or not path.is_file():
            raise HTTPException(404, f"no verification {vid}")
        return path

    def busy(vid: str) -> bool:
        job = jobs.get(vid)
        return bool(job and not job.done)

    def mark(vid: str, findings: list[str], entry: dict | None) -> None:
        """Record what became of findings (None: back to open). Not while the check still writes its file: a job
        of this server is running it. A check a stopped server left unfinished is handled like a finished one."""
        path = verif_path(vid)
        with lock:
            data = read_json(path)
            if busy(vid):
                raise HTTPException(409, "the check is still running")
            handled = data.setdefault("handled", {})
            for f in findings:
                if entry:
                    handled[f] = {**entry, "t": time.time()}
                else:
                    handled.pop(f, None)
            write_json(path, data)

    @app.post("/api/verifications/{vid}/leads")
    def verif_handle(vid: str, body: Handle):
        mark(vid, body.findings, {"status": "dismissed"} if body.status == "dismissed" else None)
        return verif_view(verif_path(vid))["counts"]

    @app.post("/api/verifications/{vid}/delete")
    def verif_delete(vid: str):
        """Removes a check and its working files; the fix runs it started stay. Not while it runs."""
        path = verif_path(vid)
        if busy(vid):
            raise HTTPException(409, "the check is still running")
        with lock:
            path.unlink()
            shutil.rmtree(verifs / vid, ignore_errors=True)
        return {"deleted": vid}

    @app.get("/api/verifications/options")
    def verif_options(steps: str = ""):
        """`steps`: what the page chose for the steps of the verification it is about to start (JSON), laid over the
        settings: the estimates and the way each check is paid follow it."""
        known = {}
        for p in verif_files():  # counts from the last checks that measured them, for the paid follow-ups
            r = read_json(p).get("results", {})
            if "dead" not in known and "sources" in r:
                known["dead"] = len(r["sources"].get("dead", []))
            if "claims" not in known and "freshness" in r:
                known["claims"] = len(r["freshness"].get("claims", []))
        cfg = user_settings.load(cfg_home)
        cfg["steps"] = user_settings.over(cfg["steps"], own_steps(steps))
        models = cfg["models"]  # the models of the user's settings, shown and priced
        # a step's own model, or the model of its role with its own engine
        apart = {step: llm.step_model(cfg, step) for step, own in cfg["steps"].items() if own.get("model") or own.get("engine")}
        how = {s["step"]: s for s in steps_view(cfg)}  # the engine, the effort and the billing of each step
        table = price_table()
        est = verify.estimates(settings.vault, known, models, table, apart)
        name = {verify.MODEL: models["reasoning"], verify.TRANSLATOR: models["translator"]}
        def origin(model):  # where the price of the estimate comes from, said when it is not set or fetched
            p = table.of(model) if model else None
            return "" if not model else "no price" if p is None else "" if p.origin in ("set", "fetched") else p.label

        model = lambda c: apart.get(c.id) or name.get(c.model, c.model) if c.model else None  # noqa: E731
        return [{"id": c.id, "title": c.title, "what": c.what, "model": model(c), "needs": list(c.needs),
                 "fixable": c.fixable, "price_origin": origin(model(c)), "limit": c.limit, **est[c.id],
                 # a check that calls the model is a step: the engine and the effort it runs at, how it is paid
                 **({k: how[c.id][k] for k in ("engine", "engine_label", "effort", "billing")} if c.id in how else {}),
                 # what a run made from this check's leads costs, when the agent can estimate it (a compaction run)
                 "run_usd": est.get(f"{c.fix_mode}-run", {}).get("usd"),
                 "run_usd_each": est.get(f"{c.fix_mode}-run", {}).get("usd_each"),
                 "run_usd_deep": est.get(f"{c.fix_mode}-run", {}).get("usd_deep"),  # a lead dug deeper, in a call of its own
                 # the chapters a call can explore, each with its number of pages
                 **({"chapters": [{"id": name, "pages": len(pages)} for name, pages in news.explorable(settings.vault).items()]}
                    if c.id == "explore" else {})}
                for c in verify.CHECKS]

    @app.get("/api/verifications")
    def verif_list():
        return [{k: v for k, v in verif_view(p).items() if k not in ("results", "handled")} for p in verif_files()[:20]]

    @app.get("/api/verifications/{vid}")
    def verif_get(vid: str):
        return verif_view(verif_path(vid))

    @app.post("/api/verifications")
    def verif_start(body: Verification):
        unknown = set(body.checks) - set(verify.BY_ID)
        if not body.checks or unknown:
            raise HTTPException(400, f"unknown or no checks: {sorted(unknown)}")
        vid = time.strftime("verif-%Y-%m-%d-%H%M%S")
        keep_steps(vid, body.steps)
        steps = verify.plan(body.checks)
        verifs.mkdir(parents=True, exist_ok=True)
        path, work_dir = verifs / f"{vid}.json", verifs / vid
        data = {"id": vid, "started": time.time(), "checks": steps, "asked": body.checks, "results": {},
                "cost": 0.0, "done": False}
        write_json(path, data)

        def work(graph, job: Job):
            deps = settings.make_deps(vid, "verify")
            work_dir.mkdir(exist_ok=True)
            if body.chapters:  # read by the check that takes them (verify.options)
                write_json(work_dir / "options.json", {"chapters": body.chapters})
            # The guide as merged (main, up to date with origin), not the folder: it may be on another branch
            guide = vault.reading_copy(settings.vault, settings.home)
            data["commit"] = inputs.run(["git", "rev-parse", "--short", "HEAD"], cwd=guide).strip()
            try:
                for step in steps:
                    check = verify.BY_ID[step]
                    model = None if not check.model else (deps.translator or deps.llm) if check.model == verify.TRANSLATOR else deps.llm
                    job.events.append({"t": time.time(), "node": f"start:{step}"})
                    try:
                        result = verify.RUNNERS[step](guide, work_dir, data["results"], model)
                    except Exception as e:  # one check failing does not stop the others
                        result = {"ok": False, "summary": f"could not run: {type(e).__name__}: {e}"[:500], "findings": []}
                        if getattr(e, "usage", None):  # billed all the same (an answer cut at the output limit)
                            result["usage"] = [e.usage]
                    result["fixable"] = check.fixable
                    data["cost"] = round(data["cost"] + sum(u.get("cost_usd", 0) for u in result.get("usage", [])), 2)
                    data["results"][step] = result
                    write_json(path, data)
                    job.events.append({"t": time.time(), "node": step, "cost": data["cost"]})
            finally:
                data["done"] = True
                write_json(path, data)

        start(vid, "verify", "verify", work)
        return {"id": vid}

    # -- page ------------------------------------------------------------------------------------
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        """The page, its scripts, style and icon named with a version (?v=…) that changes with any of them: a
        browser that kept an older copy (served before Cache-Control: no-cache) cannot mix it with the new page."""
        files = sorted(p for p in STATIC.iterdir() if p.is_file())
        version = hashlib.sha1("".join(f"{p.name}{p.stat().st_mtime_ns}{p.stat().st_size}" for p in files).encode()).hexdigest()[:10]
        page = (STATIC / "index.html").read_text(encoding="utf-8")
        page = re.sub(r'((?:src|href)="/static/[^"?]+)"', rf'\1?v={version}"', page)
        return HTMLResponse(page)

    return app


def gh_pr_state(url: str) -> str:
    return forge.get().pull_request_state(url)


def list_issues(repo: str, label: str = "veille") -> Callable[[], list[dict]]:
    """Watch issues of the guide (the manifest's [watch] label), newest first, from the forge (watches.Issues)."""
    return lambda: watches_mod.Issues(repo, label, "", Path(".")).list()
