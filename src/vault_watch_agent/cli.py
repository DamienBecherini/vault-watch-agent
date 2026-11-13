"""Command line: start a run, answer its pauses, show where it stands.

    vault-watch run --issue 50                 # stops at the review, prints the report path
    vault-watch run --watch-json path/watch.json
    vault-watch resume <thread> --accept all   # or none, or C1,C3
    vault-watch resume <thread> --publish yes  # second pause: push + pull request
    vault-watch status <thread>

The run is checkpointed in SQLite: each command is a separate process, and a
paused run waits as long as needed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from . import vault
from .graph import Deps, build, describe

HOME = Path(os.environ.get("VAULT_WATCH_HOME", ".vault-watch")).resolve()
VAULT = Path(os.environ.get("VAULT_PATH", "../ia-on-prem-vault")).resolve()
# One line per model call with its cost; versioned, it is the history of what the upkeep costs.
JOURNAL = Path(os.environ.get("VAULT_WATCH_JOURNAL", "metrics/usage.jsonl")).resolve()


def show(graph, config) -> None:
    snapshot = graph.get_state(config)
    pending = [i.value for t in snapshot.tasks for i in t.interrupts]
    if pending:
        print(json.dumps(pending[0], ensure_ascii=False, indent=2))
        print(f"\nThread {config['configurable']['thread_id']} is paused at « {pending[0]['step']} ».")
    else:
        print(describe(snapshot.values))
        print("\nRun finished." if not snapshot.next else f"\nNext: {snapshot.next}")


def run_eval(args, deps: Deps, saver) -> None:
    import dataclasses

    from . import evaluate
    from .inputs import run

    wt = HOME / "eval" / args.at[:10]
    if not wt.exists():
        run(["git", "worktree", "add", "--detach", str(wt), args.at], cwd=VAULT)
    thread = f"eval-{args.issue}-{args.variant}{args.tag}"
    for model in (deps.llm, deps.translator):
        model.run = thread
    graph = build(dataclasses.replace(deps, vault=wt, crosscheck=args.variant == "full"), saver)
    config = {"configurable": {"thread_id": thread}, "max_concurrency": 4}
    if not graph.get_state(config).values:
        graph.invoke({"issue": args.issue, "source": f"issue #{args.issue} (replay at {args.at[:10]})",
                      "branch_name": f"eval/issue{args.issue}-{args.variant}"}, config)
    values = graph.get_state(config).values
    hunks = evaluate.truth_hunks(VAULT, *args.truth.split("..")) if args.truth else []
    reviewed = evaluate.reviewable(values.get("corrections", []))
    judgement, usage = evaluate.judge(hunks, reviewed, deps.llm)
    result = {
        "issue": args.issue, "variant": args.variant, "vault_commit": args.at, "truth": args.truth,
        "scores": evaluate.scores(hunks, reviewed, judgement),
        "run_cost_usd": round(sum(u.get("cost_usd", 0) for u in values.get("usage", [])), 2),
        "judge_cost_usd": round(usage["cost_usd"], 2),
        "judgement": judgement.model_dump(),
        "truth_hunks": hunks,
        "proposals": [{k: c[k] for k in ("id", "page", "current", "proposed", "check")} for c in values.get("corrections", [])],
    }
    out = JOURNAL.parent / "eval" / f"issue{args.issue}-{args.variant}{args.tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("issue", "variant", "scores", "run_cost_usd", "judge_cost_usd")}, indent=2))


def make_deps(thread: str, kind: str) -> Deps:
    """Model clients labelled with the run, so the cost journal says which run paid for what.
    `view` builds a graph that only reads checkpoints: no client, no API key needed."""
    from .llm import TRANSLATOR, Claude

    if kind == "view":
        return Deps(vault=VAULT, home=HOME, llm=None)
    vault.sync(VAULT)
    llm, translator = Claude(journal=JOURNAL), Claude(model=TRANSLATOR, journal=JOURNAL)
    for model in (llm, translator):
        model.run, model.kind = thread, kind
    return Deps(vault=VAULT, home=HOME, llm=llm, translator=translator)


def serve(port: int, idle_exit: int = 0, notify_lang: str | None = None) -> None:
    """`idle_exit` seconds without a request and without a running analysis stop the server (0: never).
    A run paused for review or publish loses nothing: its state is in the checkpoints."""
    import threading
    import time

    import uvicorn

    from .notify import toast
    from .web import Settings, create_app

    app = create_app(Settings(vault=VAULT, home=HOME, journal=JOURNAL, make_deps=make_deps, idle_exit=idle_exit,
                              notifier=toast if notify_lang else None, notify_lang=notify_lang or "en",
                              base_url=f"http://127.0.0.1:{port}/"))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    if idle_exit:
        def watch_idle():
            while not server.should_exit:
                time.sleep(30)
                if app.state.idle_seconds() > idle_exit:
                    print(f"vault-watch: idle for {idle_exit // 60} min, stopping")
                    server.should_exit = True
        threading.Thread(target=watch_idle, daemon=True).start()
    print(f"vault-watch: http://127.0.0.1:{port}/" + (f" (stops after {idle_exit // 60} min idle)" if idle_exit else ""))
    server.run()


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="vault-watch")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    src = r.add_mutually_exclusive_group(required=True)
    src.add_argument("--issue", type=int)
    src.add_argument("--watch-json", type=Path)
    r.add_argument("--thread")
    s = sub.add_parser("resume")
    s.add_argument("thread")
    answer = s.add_mutually_exclusive_group(required=True)
    answer.add_argument("--accept", help="all, none, or ids like C1,C3")
    answer.add_argument("--publish", choices=["yes", "no"])
    answer.add_argument("--retry", action="store_true", help="a run stopped by an error: run again from its last finished step")
    st = sub.add_parser("status")
    st.add_argument("thread")
    x = sub.add_parser("crosscheck", help="re-read the paused run's corrections against the whole French vault")
    x.add_argument("thread")
    f = sub.add_parser("fix", help="turn errors reported in the vault into reviewed corrections (same review and PR flow)")
    f.add_argument("thread")
    found = f.add_mutually_exclusive_group(required=True)
    found.add_argument("--findings", type=Path, help="text file, one reported error per line")
    found.add_argument("--from-threads", help="collect the cross-check findings of these runs, e.g. issue-50e,issue-49")
    f.add_argument("--translation", action="store_true",
                   help="translation divergences: fix the English pages against the French ones (no web, no cross-check)")
    e = sub.add_parser("eval", help="replay a past watch on the vault as it was, score it against the merged PR")
    e.add_argument("--issue", type=int, required=True)
    e.add_argument("--at", required=True, help="vault commit to replay on (before the human's PR)")
    e.add_argument("--truth", help="base..head of the human's PR; omit when the human applied nothing")
    e.add_argument("--variant", choices=["keyword", "full"], required=True,
                   help="keyword: excerpts only; full: plus the cross-check on the whole vault")
    e.add_argument("--tag", default="", help="suffix of the run label, to replay again after a change (e.g. -v2)")
    c = sub.add_parser("costs", help="what the upkeep costs, from the call journal")
    c.add_argument("--by", choices=["month", "year", "run", "step"], default="month")
    w = sub.add_parser("serve", help="web interface on http://127.0.0.1:4430/ (same runs as the command line)")
    w.add_argument("--port", type=int, default=4430)
    w.add_argument("--idle-exit", type=int, default=0, metavar="SECONDS",
                   help="stop after this long without a request or a running analysis (0: never)")
    w.add_argument("--notify", choices=["fr", "en"], help="desktop notification (Windows) when a run waits for you, ends or fails")
    args = p.parse_args(argv)

    if args.cmd == "serve":
        serve(args.port, args.idle_exit, args.notify)
        return
    if args.cmd == "costs":
        from . import costs

        print(costs.table(costs.load(JOURNAL), args.by))
        return

    HOME.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(HOME / "checkpoints.sqlite")) as saver:
        # The model client is created lazily so `status` works without an API key.
        from .llm import TRANSLATOR, Claude

        live = args.cmd != "status"
        deps = Deps(
            vault=VAULT,
            home=HOME,
            llm=Claude(journal=JOURNAL) if live else None,
            translator=Claude(model=TRANSLATOR, journal=JOURNAL) if live else None,
        )
        thread = getattr(args, "thread", None) or (
            (f"issue-{args.issue}" if args.issue else args.watch_json.stem) if args.cmd == "run" else None
        )
        for model in (deps.llm, deps.translator):
            if model:
                model.run, model.kind = thread, {"crosscheck": "crosscheck", "fix": "fix", "eval": "eval"}.get(args.cmd, "watch")
        if args.cmd == "eval":
            run_eval(args, deps, saver)
            return
        graph = build(deps, saver)
        if args.cmd == "fix":
            from . import fix

            excerpts: dict[str, list[dict]] = {}
            if args.findings:
                findings = [l.strip() for l in args.findings.read_text(encoding="utf-8").splitlines() if l.strip()]
                label = args.findings.stem
            else:
                runs = args.from_threads.split(",")
                findings = []
                for r in runs:
                    values = graph.get_state({"configurable": {"thread_id": r}}).values
                    findings += values.get("findings", [])
                    excerpts.update(values.get("finding_excerpts", {}))
                label = "cross-checks of " + ", ".join(runs)
            config = {"configurable": {"thread_id": thread}, "max_concurrency": 4}
            if args.translation:
                items, proposal, usage = fix.propose_translation(VAULT, findings, deps.translator or deps.llm, excerpts)
            else:
                items, proposal, usage = fix.propose(VAULT, findings, deps.llm, excerpts=excerpts)
            mode = "translation" if args.translation else "fix"
            # Enter the graph as if the proposals had just been made: numbering, cross-check, review…
            graph.update_state(config, fix.initial_state(label, items, proposal, usage, thread, mode), as_node="propose")
            graph.invoke(None, config)
            show(graph, config)
            return
        if args.cmd == "run":
            config = {"configurable": {"thread_id": thread}, "max_concurrency": 4}
            start = {"issue": args.issue, "source": f"issue #{args.issue}" if args.issue else str(args.watch_json)}
            graph.invoke(start, config)
        else:
            config = {"configurable": {"thread_id": args.thread}, "max_concurrency": 4}
            if args.cmd == "crosscheck":
                from . import crosscheck

                values = graph.get_state(config).values
                result, usage, checks = crosscheck.run(VAULT, values["corrections"], deps.llm)
                out = Path(values["report_path"]).with_name(Path(values["report_path"]).stem + "-crosscheck.md")
                out.write_text(crosscheck.render(result, checks, usage, values["source"]), encoding="utf-8")
                print(f"Cross-check written to {out} (≈ {usage['cost_usd']:.2f} $)")
                return
            if args.cmd == "resume" and args.retry:
                graph.invoke(None, config)  # stopped by an error: run again from the last finished step
            elif args.cmd == "resume":
                if args.accept is not None:
                    value = args.accept if args.accept in ("all", "none") else args.accept.split(",")
                else:
                    value = args.publish == "yes"
                graph.invoke(Command(resume=value), config)
        show(graph, config)


if __name__ == "__main__":
    main()
