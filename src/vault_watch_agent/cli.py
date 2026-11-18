"""Command line: start a run, answer its pauses, show where it stands.

    vault-watch --guide ../my-guide init       # write the guide's vault-watch.toml from what its folder shows
    vault-watch --guide ../my-guide doctor     # what is ready for a run, what is missing
    vault-watch --guide ../my-guide run --issue 50   # any command: --guide names the guide
    vault-watch run --issue 50                 # stops at the review, prints the report path
    vault-watch run --watch-json path/watch.json
    vault-watch resume <thread> --accept all   # or none, or C1,C3
    vault-watch resume <thread> --publish yes  # second pause: push + pull request
    vault-watch status <thread>
    vault-watch collect --json watch.json      # a watch from the guide's feeds.json (no model), Markdown on stdout

The run is checkpointed in SQLite: each command is a separate process, and a
paused run waits as long as needed.

The guide: --guide, else VAULT_PATH, else the current folder when it holds a vault-watch.toml, else
../ia-on-prem-vault (the folder the agent was written for, kept so that existing set-ups go on working). Each guide
has its working folder under VAULT_WATCH_HOME (default .vault-watch, see guide.working_folder); the settings are
shared.
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
from .prices import Prices
from .graph import Deps, build, describe

CONFIG_HOME = Path(os.environ.get("VAULT_WATCH_HOME", ".vault-watch")).resolve()  # settings, shared by the guides
VAULT = Path(".").resolve()  # the guide, and its working folder: set by use_guide() from --guide
HOME = CONFIG_HOME
LEGACY_FOLDER = "../ia-on-prem-vault"
# One line per model call with its cost; versioned, it is the history of what the upkeep costs.
JOURNAL = Path(os.environ.get("VAULT_WATCH_JOURNAL", "metrics/usage.jsonl")).resolve()


def find_guide(option: str | None) -> Path:
    """The guide's folder: --guide, VAULT_PATH, the current folder with a manifest, or the folder of before."""
    from .guide import MANIFEST

    if option or os.environ.get("VAULT_PATH"):
        return Path(option or os.environ["VAULT_PATH"]).resolve()
    if (Path.cwd() / MANIFEST).is_file():
        return Path.cwd().resolve()
    legacy = Path(LEGACY_FOLDER).resolve()
    if legacy.is_dir():
        return legacy
    sys.exit("vault-watch: which guide? Give --guide <folder> (or VAULT_PATH), or run it from a guide's folder.")


def use_guide(option: str | None) -> None:
    """Sets VAULT and HOME for the commands; a wrong manifest stops here, with what to fix."""
    global VAULT, HOME
    from .guide import GuideError, working_folder

    VAULT = find_guide(option)
    if not VAULT.is_dir():
        sys.exit(f"vault-watch: {VAULT} is not a folder")
    try:
        guide = vault.guide_of(VAULT)
    except GuideError as e:
        sys.exit(f"vault-watch: {e}")
    CONFIG_HOME.mkdir(parents=True, exist_ok=True)
    HOME = working_folder(CONFIG_HOME, guide)


def prices_command(args) -> None:
    """show: the price of each model and its origin. update: reads LiteLLM's public list, shows what changes, and
    replaces the fetched list on --yes (or a yes typed at the prompt). Nothing is fetched otherwise."""
    from datetime import date

    from . import config, prices

    table = Prices.of_home(CONFIG_HOME, config.load(CONFIG_HOME))
    if args.action == "show":
        for model in table.known():
            p = table.of(model)
            print(f"{model:28} {p.input:>8g} {p.output:>8g} {p.cache_read:>8g} {p.cache_write:>8g}   {p.label}")
        print("USD per million tokens: input, output, cache read, cache write.")
        return
    try:
        fetched = prices.fetch(date.today().isoformat())
    except ValueError as e:
        sys.exit(f"vault-watch: {e}")
    changes = prices.diff(table, fetched)
    new = [c for c in changes if c.startswith("+ ")]
    for line in [c for c in changes if not c.startswith("+ ")]:
        print(line)
    if new:
        print(f"+ {len(new)} model(s) the agent had no price for: "
              + ", ".join(c[2:].split(":")[0] for c in new[:12]) + (" ..." if len(new) > 12 else ""))
    if fetched["estimated"]:
        print(f"  cache prices estimated (0.1 x and 1.25 x input) for: {', '.join(fetched['estimated'][:8])}")
    if not changes:
        print("vault-watch: the fetched list changes no price.")
    if not (args.yes or _confirm("Replace the fetched list? [y/N] ")):
        print("vault-watch: nothing replaced.")
        return
    print(f"vault-watch: wrote {prices.save(CONFIG_HOME, fetched)} ({len(fetched['models'])} models, {fetched['date']}).")


def _confirm(question: str) -> bool:
    """A yes typed at a terminal; no terminal, or nothing typed: no."""
    if not sys.stdin.isatty():
        return False
    try:
        return input(question).strip().lower() in ("y", "yes", "o", "oui")
    except EOFError:
        return False


def onboarding(args) -> None:
    """init and doctor: they work on a guide that has no manifest yet, or a wrong one, so they do not go through
    use_guide(). The guide is --guide, VAULT_PATH or the current folder (never the folder of before)."""
    from . import onboard

    root = Path(args.guide or os.environ.get("VAULT_PATH") or ".").resolve()
    if not root.is_dir():
        sys.exit(f"vault-watch: {root} is not a folder")
    if args.cmd == "init":
        if args.print:
            print(onboard.propose(root), end="")
            return
        try:
            path = onboard.write(root, force=args.force)
        except (FileExistsError, ValueError) as e:
            sys.exit(f"vault-watch: {e}")
        print(f"vault-watch: wrote {path}. Check each line, then run `vault-watch --guide {root} doctor`.")
        return
    lines = onboard.diagnose(root, CONFIG_HOME)
    print(f"vault-watch doctor: {root}")
    for line in lines:
        print(line)
    failed = sum(line.status == "fail" for line in lines)
    print("Ready for a run." if not failed else f"{failed} problem(s) to fix before a run.")
    if failed:
        sys.exit(1)


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
    judgement, usage = evaluate.judge(hunks, reviewed, deps.llm, VAULT)
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


def collect_command(args) -> None:
    """The watch of the window from the guide's feeds: the JSON to a file, the Markdown on stdout. Free (no model)."""
    from . import collect, watches

    try:
        collector = collect.Collector.of_guide(vault.guide_of(VAULT), triage_on=not args.no_triage)
    except collect.CollectError as e:
        sys.exit(f"vault-watch: {e}")
    only = set(args.only.split(",")) if args.only else None
    watch = collector.collect(days=args.days, since=args.since, only=only)
    report = collect.markdown(watch, collector, only)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(watch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        path = args.json
    else:
        path = watches.write(watch, HOME / watches.Collected.FOLDER)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"vault-watch: {watch['kept']} item(s) kept of {len(watch['items'])}, {watch['urgent']} urgent, "
          f"{len(watch['errors'])} feed(s) in error: {path}", file=sys.stderr)


def make_deps(thread: str, kind: str) -> Deps:
    """Model clients labelled with the run, so the cost journal says which run paid for what.
    `view` builds a graph that only reads checkpoints: no client, no API key needed."""
    from . import config
    from .llm import create

    if kind == "view":
        return Deps(vault=VAULT, home=HOME, llm=None)
    vault.sync(VAULT)
    settings = config.load(CONFIG_HOME)  # read for each run: a change in the Settings page applies to the next one
    table = Prices.of_home(CONFIG_HOME, settings)  # the user's prices, the fetched list, the defaults
    llm, translator = create("reasoning", JOURNAL, settings, table), create("translator", JOURNAL, settings, table)
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

    app = create_app(Settings(vault=VAULT, home=HOME, config_home=CONFIG_HOME, journal=JOURNAL, make_deps=make_deps,
                              idle_exit=idle_exit,
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
    p.add_argument("--guide", metavar="FOLDER", help="the guide's folder (default: VAULT_PATH, or the current folder "
                   "when it has a vault-watch.toml)")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="write vault-watch.toml in the guide's folder (--guide, or the current folder)")
    i.add_argument("--force", action="store_true", help="replace an existing vault-watch.toml")
    i.add_argument("--print", action="store_true", help="print the manifest instead of writing it")
    sub.add_parser("doctor", help="check the guide, its manifest and the engine before a first run")
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
    x = sub.add_parser("crosscheck", help="re-read the paused run's corrections against the whole guide")
    x.add_argument("thread")
    f = sub.add_parser("fix", help="turn errors reported in the vault into reviewed corrections (same review and PR flow)")
    f.add_argument("thread")
    found = f.add_mutually_exclusive_group(required=True)
    found.add_argument("--findings", type=Path, help="text file, one reported error per line")
    found.add_argument("--from-threads", help="collect the cross-check findings of these runs, e.g. issue-50e,issue-49")
    f.add_argument("--translation", action="store_true",
                   help="translation divergences: fix the mirror pages against the source ones (no web, no cross-check)")
    e = sub.add_parser("eval", help="replay a past watch on the vault as it was, score it against the merged PR")
    e.add_argument("--issue", type=int, required=True)
    e.add_argument("--at", required=True, help="vault commit to replay on (before the human's PR)")
    e.add_argument("--truth", help="base..head of the human's PR; omit when the human applied nothing")
    e.add_argument("--variant", choices=["keyword", "full"], required=True,
                   help="keyword: excerpts only; full: plus the cross-check on the whole vault")
    e.add_argument("--tag", default="", help="suffix of the run label, to replay again after a change (e.g. -v2)")
    pr = sub.add_parser("prices", help="the prices of the models and where each comes from; update fetches the public list")
    pr.add_argument("action", choices=["show", "update"])
    pr.add_argument("--yes", action="store_true", help="update: replace the fetched list without asking")
    co = sub.add_parser("collect", help="read the guide's feeds ([watch] feeds) and write a watch.json, no model")
    co.add_argument("--days", type=int, help="the window, in days back from today (default: the feeds file's)")
    co.add_argument("--since", help="the start of the window, YYYY-MM-DD (instead of --days)")
    co.add_argument("--only", help="some domains only, e.g. engines,security")
    co.add_argument("--json", type=Path, help="where to write the watch (default: watches/ of the guide's working folder)")
    co.add_argument("--markdown", type=Path, help="also write the Markdown report there (it is printed anyway)")
    co.add_argument("--no-triage", action="store_true", help="keep every item of the window")
    c = sub.add_parser("costs", help="what the upkeep costs, from the call journal")
    c.add_argument("--by", choices=["month", "year", "run", "step"], default="month")
    w = sub.add_parser("serve", help="web interface on http://127.0.0.1:4430/ (same runs as the command line)")
    w.add_argument("--port", type=int, default=4430)
    w.add_argument("--idle-exit", type=int, default=0, metavar="SECONDS",
                   help="stop after this long without a request or a running analysis (0: never)")
    w.add_argument("--notify", choices=["fr", "en"], help="desktop notification (Windows) when a run waits for you, ends or fails")
    args = p.parse_args(argv)

    if args.cmd in ("init", "doctor"):
        onboarding(args)
        return
    if args.cmd == "prices":
        prices_command(args)
        return
    if args.cmd != "costs":
        use_guide(args.guide)
    if args.cmd == "serve":
        serve(args.port, args.idle_exit, args.notify)
        return
    if args.cmd == "collect":
        collect_command(args)
        return
    if args.cmd == "costs":
        from . import costs

        print(costs.table(costs.load(JOURNAL), args.by))
        return

    HOME.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(HOME / "checkpoints.sqlite")) as saver:
        # The model client is created lazily so `status` works without an API key.
        from . import config
        from .llm import create

        live = args.cmd != "status"
        settings = config.load(CONFIG_HOME) if live else None
        deps = Deps(
            vault=VAULT,
            home=HOME,
            llm=create("reasoning", JOURNAL, settings, Prices.of_home(CONFIG_HOME, settings)) if live else None,
            translator=create("translator", JOURNAL, settings, Prices.of_home(CONFIG_HOME, settings)) if live else None,
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
