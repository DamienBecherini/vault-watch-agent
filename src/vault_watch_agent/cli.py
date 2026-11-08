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
    st = sub.add_parser("status")
    st.add_argument("thread")
    x = sub.add_parser("crosscheck", help="re-read the paused run's corrections against the whole French vault")
    x.add_argument("thread")
    f = sub.add_parser("fix", help="turn errors reported in the vault into reviewed corrections (same review and PR flow)")
    f.add_argument("thread")
    found = f.add_mutually_exclusive_group(required=True)
    found.add_argument("--findings", type=Path, help="text file, one reported error per line")
    found.add_argument("--from-threads", help="collect the cross-check findings of these runs, e.g. issue-50e,issue-49")
    c = sub.add_parser("costs", help="what the upkeep costs, from the call journal")
    c.add_argument("--by", choices=["month", "year", "run", "step"], default="month")
    args = p.parse_args(argv)

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
                model.run, model.kind = thread, {"crosscheck": "crosscheck", "fix": "fix"}.get(args.cmd, "watch")
        graph = build(deps, saver)
        if args.cmd == "fix":
            from . import fix

            if args.findings:
                findings = [l.strip() for l in args.findings.read_text(encoding="utf-8").splitlines() if l.strip()]
                label = args.findings.stem
            else:
                runs = args.from_threads.split(",")
                findings = [x for r in runs for x in graph.get_state(
                    {"configurable": {"thread_id": r}}).values.get("findings", [])]
                label = "cross-checks of " + ", ".join(runs)
            config = {"configurable": {"thread_id": thread}, "max_concurrency": 4}
            items, proposal, usage = fix.propose(VAULT, findings, deps.llm)
            # Enter the graph as if the proposals had just been made: numbering, cross-check, review…
            graph.update_state(config, fix.initial_state(label, items, proposal, usage), as_node="propose")
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
            if args.cmd == "resume":
                if args.accept is not None:
                    value = args.accept if args.accept in ("all", "none") else args.accept.split(",")
                else:
                    value = args.publish == "yes"
                graph.invoke(Command(resume=value), config)
        show(graph, config)


if __name__ == "__main__":
    main()
