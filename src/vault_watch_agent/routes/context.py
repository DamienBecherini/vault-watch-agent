"""What the routers of the web interface share: the settings of the server, the background work in progress, the
checkpoints and the graph that reads them, and the helpers more than one area of the page needs (a run's summary,
the state of a pull request, the steps a page chose, the pause a run waits at). web.create_app makes one per app."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException
from langgraph.checkpoint.sqlite import SqliteSaver

from .. import config as user_settings
from .. import forge, llm, prices, steps, store, vault
from .. import watches as watches_mod
from ..graph import Deps, build
from ..guide import Guide

if TYPE_CHECKING:  # langgraph's own dependency: named for the types only
    from langchain_core.runnables import RunnableConfig

# What the forge says is kept this many seconds: the state of an open pull request, the list of the watch issues
FORGE_FRESH = 20


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


def write_json(path: Path, data: dict) -> None:
    """Writes a file the page reads while a check runs: aside, then put in place in one go, so a read never finds
    it empty or half written. Windows refuses the swap while a reader holds the file: tried again for a moment."""
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    for _ in range(39):
        try:
            os.replace(partial, path)
            return
        except PermissionError:
            time.sleep(0.05)
    os.replace(partial, path)  # the last try: its error is the caller's


def read_json(path: Path) -> dict:
    """Reads a file `write_json` may be putting in place at that moment: Windows refuses to open it during the swap
    (PermissionError), tried again for a moment. A file that is not there is still an error at once."""
    for _ in range(39):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except PermissionError:
            time.sleep(0.05)
    return json.loads(path.read_text(encoding="utf-8"))  # the last try: its error is the caller's


def thread_config(thread: str) -> RunnableConfig:
    """The graph's configuration for a run: its checkpoints, and at most four of its jobs at once."""
    return {"configurable": {"thread_id": thread}, "max_concurrency": 4}


def interrupts(snapshot) -> list[dict]:
    """What a run's snapshot waits for: the values of its pauses (the first one is where it stands)."""
    return [i.value for t in snapshot.tasks for i in t.interrupts]


def run_status(snapshot, job: Job | None) -> str:
    """Where a run stands, from its last checkpoint and its background work."""
    if job and not job.done:
        return "running"
    v = snapshot.values
    if not v:
        return "new"
    pending = interrupts(snapshot)
    if pending:
        return pending[0]["step"]  # review or publish
    if snapshot.next:
        return "stopped"  # an error interrupted it; resume continues after the last finished step
    if v.get("pr_url"):
        return "published"
    if not v.get("accepted") and v.get("mode") != "mirror":  # a mirror run has no correction to accept
        return "nothing-applied"
    return "not-published"


def gh_pr_state(url: str) -> str:
    return forge.get().pull_request_state(url)


@dataclass
class AppContext:
    """The state of one app, given to each router (routes/*.py) instead of the closures of a single function."""
    settings: Settings
    app: FastAPI  # its `state` holds the time of the last request (serve --idle-exit) and the jobs
    guide: Guide  # the guide as the server started: its repository, site and forge
    cfg_home: Path  # the user's settings
    db: Path  # the checkpoints of the runs
    saver: SqliteSaver
    viewer: Any  # the graph that reads checkpoints, never calls the model
    jobs: dict[str, Job] = field(default_factory=dict)  # the background work of this server, by thread
    lock: threading.Lock = field(default_factory=threading.Lock)
    # Said when background work stops (notices.announce, set by web.create_app)
    announce: Callable[[Job], None] = field(default=lambda job: None)
    notices: list[dict] = field(default_factory=list)  # one per background work that stopped with something to say
    # What the forge says, kept so that a page does not wait for it at every display (each question is a call to
    # `gh` over the network, half a second or more). The state of a pull request: merged and closed are final and
    # written to the disk (a server just started does not ask again for every past run); open is asked again, at
    # most once in FORGE_FRESH seconds. The list of the watch issues: kept FORGE_FRESH seconds too. The tests give
    # their own answers (settings.pr_state, settings.list_issues): nothing is kept then, each call asks.
    pr_states: dict[str, str] = field(default_factory=dict)
    pr_asked: dict[str, float] = field(default_factory=dict)
    listed: dict = field(default_factory=dict)  # the watches of the forge: {"at": when asked, "found": the list}
    seen: dict[str, tuple[str, dict]] = field(default_factory=dict)  # thread -> (its last checkpoint, what a list shows)

    @classmethod
    def create(cls, settings: Settings, app: FastAPI) -> AppContext:
        """The context of a new app: the guide read, its forge chosen, the checkpoints opened and tidied."""
        guide = vault.guide_of(settings.vault)  # the repository and the site shown, unless given
        settings.repo, settings.site = settings.repo or guide.repository, settings.site or guide.site
        forge.use(forge.for_guide(guide))  # GitHub, or the Gitea server the manifest names
        settings.home.mkdir(parents=True, exist_ok=True)
        db = settings.home / "checkpoints.sqlite"
        saver = SqliteSaver(sqlite3.connect(db, check_same_thread=False))
        store.tidy(db)  # the copies of past runs that nothing reads any more (again each time a run pauses or ends)
        ctx = cls(settings=settings, app=app, guide=guide, cfg_home=settings.config_home or settings.home, db=db, saver=saver,
                  viewer=build(settings.make_deps("", "view"), saver))
        ctx.pr_states = ctx._known_pr_states()
        return ctx

    # -- paths ---------------------------------------------------------------------------------
    @property
    def pr_file(self) -> Path:
        return self.settings.home / "pr-states.json"

    @property
    def verifs(self) -> Path:
        """The health checks of the guide (verify.py): one JSON file per verification."""
        return self.settings.home / "verifications"

    # -- idle time, for `serve --idle-exit`: requests count, the health probe of a supervisor does not --
    def touch(self) -> None:
        self.app.state.last_activity = time.time()

    def idle_seconds(self) -> float:
        if any(not j.done for j in list(self.jobs.values())):
            self.touch()  # the delay runs from the end of the work
            return 0.0
        return time.time() - self.app.state.last_activity

    # -- background runs ---------------------------------------------------------------------
    def graph_for(self, thread: str, kind: str):
        return build(self.settings.make_deps(thread, kind), self.saver)

    def start(self, thread: str, action: str, kind: str, work: Callable[[Any, Job], None]) -> Job:
        """Runs `work` (with a graph whose model clients are this run's) in a thread of its own; 409 while the same
        thread is running."""
        with self.lock:
            if thread in self.jobs and not self.jobs[thread].done:
                raise HTTPException(409, f"{thread} is already running")
            job = self.jobs[thread] = Job(thread, action)

        def target():
            try:
                work(self.graph_for(thread, kind), job)
            except Exception as e:  # shown on the page; the checkpoint keeps the last finished step
                job.error = f"{type(e).__name__}: {e}"
            finally:
                job.done = True
                self.touch()
                store.tidy(self.db)  # paused or over: only its last checkpoint is needed from here
                try:
                    self.announce(job)
                except Exception:  # a notification never breaks a run
                    pass

        threading.Thread(target=target, daemon=True, name=f"vault-watch {thread}").start()
        return job

    def follow(self, graph, job: Job, value) -> None:
        """Streams the graph from `value` (a run to start, a Command to resume it), one event per finished step."""
        cost = worth = 0.0
        for chunk in graph.stream(value, thread_config(job.thread), stream_mode="updates"):
            for node, update in chunk.items():
                if node == "__interrupt__":
                    job.events.append({"t": time.time(), "node": "pause"})
                    continue
                for u in (update or {}).get("usage", []) if isinstance(update, dict) else []:
                    cost += u.get("cost_usd", 0.0)
                    worth += 0.0 if u.get("cost_usd") else (u.get("list_usd") or 0.0)
                job.events.append({"t": time.time(), "node": node.split(":")[0], "cost": round(cost, 2),
                                   "unbilled": round(worth, 2)})

    def resume_with(self, thread: str, action: str, value) -> dict:
        """Resumes a paused run with the answer to its pause, in the background."""
        self.start(thread, action, "watch", lambda g, job: self.follow(g, job, value))
        return {"thread": thread}

    def busy(self, thread: str) -> bool:
        job = self.jobs.get(thread)
        return bool(job and not job.done)

    # -- the pause a run waits at --------------------------------------------------------------
    def values(self, thread: str) -> dict:
        """A run's state at its last checkpoint ({} when it has none)."""
        return self.viewer.get_state(thread_config(thread)).values

    def pause_step(self, thread: str) -> str:
        """The step a run is paused at ("" when it is not paused)."""
        pending = interrupts(self.viewer.get_state(thread_config(thread)))
        return pending[0].get("step", "") if pending else ""

    def paused_at(self, thread: str, steps: tuple[str, ...] = ("retouch",)) -> dict:
        """The state of a run paused at the retouches (or at one of `steps`); 409 otherwise."""
        snapshot = self.viewer.get_state(thread_config(thread))
        pending = interrupts(snapshot)
        if not pending or pending[0].get("step") not in steps:
            raise HTTPException(409, f"{thread} is not paused at the {' or '.join(steps)}")
        return snapshot.values

    # -- the state of pull requests, from the forge ------------------------------------------------
    def _known_pr_states(self) -> dict[str, str]:
        try:
            return {u: s for u, s in json.loads(self.pr_file.read_text(encoding="utf-8")).items() if s in ("merged", "closed")}
        except (OSError, ValueError, AttributeError):
            return {}

    def pr_due(self, url: str) -> bool:
        if self.pr_states.get(url) in ("merged", "closed"):
            return False
        return self.settings.pr_state is not None or time.time() - self.pr_asked.get(url, 0) > FORGE_FRESH

    def pr_state(self, url: str) -> str:
        if not self.pr_due(url):
            return self.pr_states.get(url, "")
        try:
            self.pr_states[url] = (self.settings.pr_state or gh_pr_state)(url)
        except Exception:  # gh missing or offline: the run still shows as published
            return ""
        self.pr_asked[url] = time.time()
        if self.pr_states[url] in ("merged", "closed"):
            try:
                self.settings.home.mkdir(parents=True, exist_ok=True)
                write_json(self.pr_file, {u: s for u, s in self.pr_states.items() if s in ("merged", "closed")})
            except OSError:
                pass  # asked again after the next start, nothing more
        return self.pr_states.get(url, "")

    def warm(self, names: dict[str, str]) -> None:
        """Asks the forge at once, side by side, for the pull requests of these runs whose state may have moved: a
        page that lists ten runs waits for one answer, not ten in a row."""
        urls = {self.core(t, names[t])["pr_url"] for t in names}
        due = [u for u in urls if u and self.pr_due(u)]
        if len(due) > 1:
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(self.pr_state, due))

    # -- the watches of the guide --------------------------------------------------------------
    def watch_source(self) -> watches_mod.WatchSource:
        """The guide's watch source (manifest [watch]); the tests give their own list of issues."""
        return watches_mod.of(vault.guide_of(self.settings.vault), self.settings.home, self.settings.list_issues)

    def list_watches(self) -> list[dict]:
        src = self.watch_source()
        if src.kind != "issue" or self.settings.list_issues is not None:
            return src.list()  # files of the machine, or the list of a test: read each time
        if time.time() - self.listed.get("at", 0) > FORGE_FRESH:
            self.listed.update(found=src.list(), at=time.time())
        return self.listed["found"]

    # -- views of a run ----------------------------------------------------------------------
    def core(self, thread: str, stamp: str = "") -> dict:
        """What a list shows of a run, from its state. With `stamp` (its last checkpoint, from `stamped`) the state
        is read again only when the run has moved: a page that lists two hundred past runs reads none of them, it
        asks the database for one line per run. Without it (one run looked at), the state is read."""
        known = self.seen.get(thread)
        if stamp and known and known[0] == stamp:
            return known[1]
        snapshot = self.viewer.get_state(thread_config(thread))
        v = snapshot.values
        made = {"status": run_status(snapshot, None), "source": v.get("source", ""),
                "as_of": v.get("as_of", ""), "pr_url": v.get("pr_url", ""),
                "cost": round(sum(u.get("cost_usd", 0.0) for u in v.get("usage", [])), 2),
                "unbilled_usd": round(sum(u.get("list_usd") or 0.0 for u in v.get("usage", []) if not u.get("cost_usd")), 2),
                "corrections": len(v.get("corrections", [])), "applied": len(v.get("applied", []))}
        if stamp:
            self.seen[thread] = (stamp, made)
        return made

    def summary(self, thread: str, stamp: str = "") -> dict:
        c, job = self.core(thread, stamp), self.jobs.get(thread)
        st = "running" if job and not job.done else c["status"]
        if st == "published":
            st = {"merged": "merged", "open": "pr-open", "closed": "pr-closed"}.get(self.pr_state(c["pr_url"]), st)
        return {"thread": thread, **c, "status": st, "error": job.error if job else ""}

    def checkpoints(self) -> list[tuple[str, str]]:
        """Each thread of the database with its last checkpoint, as SQLite gives them ([] before the first run)."""
        if not self.db.exists():
            return []
        with sqlite3.connect(self.db) as c:
            try:
                return c.execute("SELECT thread_id, MAX(checkpoint_id) FROM checkpoints GROUP BY thread_id").fetchall()
            except sqlite3.OperationalError:
                return []

    def stamped(self) -> dict[str, str]:
        """The runs kept here, the newest first, each with its last checkpoint (what says whether it has moved)."""
        rows = self.checkpoints()
        return {t: stamp for t, stamp in sorted(rows, key=lambda r: r[1], reverse=True) if not t.startswith("eval-")}

    def threads(self) -> list[str]:
        return list(self.stamped())

    @staticmethod
    def run_name(kind: str) -> str:
        """A run's name from its kind and the time it starts, local: `add-2026-11-25-2130`. The time tells apart
        two runs of the same day; free_thread still adds -2 to a second one in the same minute."""
        return f"{kind}-{datetime.now():%Y-%m-%d-%H%M}"

    def free_thread(self, base: str) -> str:
        """`base`, or `base-2`, `base-3`… the first name no run of this guide has (a run just started has no
        checkpoint yet: the jobs count too)."""
        existing = set(self.threads()) | set(self.jobs)
        return next(t for t in (base, *(f"{base}-{n}" for n in range(2, 100))) if t not in existing)

    # -- the user's settings (config.py) and the steps a page chose ------------------------------------
    def engine_now(self) -> str:
        """The engine the next run would use; "" when the settings cannot be read (the Settings page says why)."""
        try:
            return llm.engine(user_settings.load(self.cfg_home)["engine"])
        except (user_settings.ConfigError, llm.ModelError):
            return ""

    def billing_now(self) -> str:
        """How the next run is paid, without making a client: token, subscription, or none (a local model)."""
        try:
            cfg = user_settings.load(self.cfg_home)
            return llm.billing_of(cfg, llm.engine(cfg["engine"]))
        except (user_settings.ConfigError, llm.ModelError):
            return "token"

    @staticmethod
    def own_steps(text: str) -> dict:
        """What a page chose for the steps of the run it is about to start (`steps`, as JSON in a query): checked."""
        try:
            return user_settings.check_steps(json.loads(text) if text else {})
        except ValueError as e:  # ConfigError is one
            raise HTTPException(400, f"steps: {e}") from e

    def with_steps(self, steps_json: str = "") -> dict:
        """The user's settings with what a page chose for the steps of one run laid over them."""
        cfg = user_settings.load(self.cfg_home)
        cfg["steps"] = user_settings.over(cfg["steps"], self.own_steps(steps_json))
        return cfg

    def keep_steps(self, thread: str, given: dict) -> None:
        """Keeps what a run sets for its own steps, before it starts (cli.make_deps reads it for each of its jobs)."""
        try:
            user_settings.save_run_steps(self.settings.home, thread, given)
        except ValueError as e:
            raise HTTPException(400, f"steps: {e}") from e

    @staticmethod
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

    def price_table(self, cfg: dict | None = None) -> prices.Prices:
        return prices.Prices.of_home(self.cfg_home, cfg if cfg is not None else user_settings.load(self.cfg_home))

