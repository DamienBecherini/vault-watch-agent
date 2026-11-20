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
    vault-watch news                           # what a reader would look for and not find: leads, nothing edited

The run is checkpointed in SQLite: each command is a separate process, and a
paused run waits as long as needed.

The guide: --guide, else VAULT_PATH, else the current folder when it holds a vault-watch.toml, else
../ia-on-prem-vault (the folder the agent was written for, kept so that existing set-ups go on working). Each guide
has its working folder under the agent's folder (default_home: VAULT_WATCH_HOME, ./.vault-watch, ~/.vault-watch; see
guide.working_folder); the settings are shared.
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



def default_home() -> Path:
    """The agent's folder (settings, the runs of each guide, the cost journal): VAULT_WATCH_HOME, else a
    `.vault-watch` in the current folder when there is one (how the agent ran before 1.0, from its own clone),
    else `~/.vault-watch`: never a new folder inside the guide the command is run from."""
    if os.environ.get("VAULT_WATCH_HOME"):
        return Path(os.environ["VAULT_WATCH_HOME"]).expanduser().resolve()
    here = Path(".vault-watch")
    return here.resolve() if here.is_dir() else (Path.home() / ".vault-watch").resolve()


def default_journal(home: Path) -> Path:
    """One line per model call with its cost: VAULT_WATCH_JOURNAL, else `metrics/usage.jsonl` in the current folder
    when it exists (the agent's clone, where it is versioned), else `usage.jsonl` in the agent's folder."""
    if os.environ.get("VAULT_WATCH_JOURNAL"):
        return Path(os.environ["VAULT_WATCH_JOURNAL"]).expanduser().resolve()
    here = Path("metrics/usage.jsonl")
    return here.resolve() if here.is_file() else home / "usage.jsonl"


CONFIG_HOME = default_home()  # settings, shared by the guides
VAULT = Path(".").resolve()  # the guide, and its working folder: set by use_guide() from --guide
HOME = CONFIG_HOME
LEGACY_FOLDER = "../ia-on-prem-vault"
JOURNAL = default_journal(CONFIG_HOME)


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
    from . import forge

    forge.use(forge.for_guide(guide))  # GitHub, or the Gitea server the manifest names
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


def run_eval(args, deps: Deps, saver, judge) -> None:
    """`judge`: the model that scores the proposals, a Claude one whatever model ran the watch (`evaluate.judge_engine`),
    so that the scores of two models are comparable."""
    import dataclasses

    from . import evaluate
    from .inputs import run

    wt = HOME / "eval" / args.at[:10]
    if not wt.exists():
        run(["git", "worktree", "add", "--detach", str(wt), args.at], cwd=VAULT)
    thread = f"eval-{args.issue}-{args.variant}{args.tag}"
    for model in (deps.llm, deps.translator, judge):
        model.run = thread
    graph = build(dataclasses.replace(deps, vault=wt, crosscheck=args.variant == "full"), saver)
    config = {"configurable": {"thread_id": thread}, "max_concurrency": 4}
    if not graph.get_state(config).values:
        graph.invoke({"issue": args.issue, "source": f"issue #{args.issue} (replay at {args.at[:10]})",
                      "branch_name": f"eval/issue{args.issue}-{args.variant}"}, config)
    values = graph.get_state(config).values
    hunks = evaluate.truth_hunks(VAULT, *args.truth.split("..")) if args.truth else []
    reviewed = evaluate.reviewable(values.get("corrections", []))
    judgement, usage = evaluate.judge(hunks, reviewed, judge, VAULT)
    ran = sorted({(u.get("engine", ""), u.get("model", "")) for u in values.get("usage", []) if u.get("model")})
    result = {
        "issue": args.issue, "variant": args.variant, "vault_commit": args.at, "truth": args.truth,
        "run_models": [f"{e}:{m}" for e, m in ran], "judge": f"{usage.get('engine', '')}:{usage.get('model', '')}",
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
    print(json.dumps({k: result[k] for k in ("issue", "variant", "run_models", "judge", "scores", "run_cost_usd",
                                             "judge_cost_usd")}, indent=2))


def collect_command(args) -> None:
    """The watch of the window from the guide's feeds: the JSON to a file, the Markdown on stdout. Free (no model)."""
    from . import collect, watches

    # The watched pages are compared with what the last watch saw: the one given, else those kept on this machine
    known = [args.previous] if args.previous else [HOME / watches.Collected.FOLDER, HOME / "downloads"]
    try:
        collector = collect.Collector.of_guide(vault.guide_of(VAULT), triage_on=not args.no_triage,
                                               previous=collect.previous_pages(known))
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


def compact_command(args) -> None:
    """What the guide weighs, page by page (no model). With --report: what could be trimmed, one model call that
    reads the whole guide and edits nothing; its cost is said first, and asked for unless --yes. The findings go
    to a file, one per line: the lines kept there make a compaction run (`fix <thread> --findings … --compact`)."""
    from . import sizes

    print(sizes.table(sizes.report(VAULT)))
    if not args.report:
        print("\nvault-watch: `compact --report` lists what could be trimmed (one model call that reads the whole guide).",
              file=sys.stderr)
        return
    from . import verify

    _paid_check(args, "compaction", "compact", "The report", "--compact",
                lambda work, llm: verify.run_compaction(VAULT, work, {"sizes": verify.run_sizes(VAULT, work, {}, None)}, llm))


def news_command(args) -> None:
    """What a reader would look for in the guide and not find: one model call that reads the whole guide and what
    past watches set aside, verifies nothing and edits nothing; its cost is said first, and asked for unless --yes.
    The leads go to a file, one per line: the lines kept there make an addition run (`fix <thread> --findings … --add`),
    which checks each one on the web."""
    from . import verify

    if not args.explore:
        _paid_check(args, "news", "add", "The list of leads", "--add", lambda work, llm: verify.run_news(VAULT, work, {}, llm))
        return
    # The other way: the web explored chapter by chapter (news.explore), each chapter a call with the web
    import tempfile

    from . import news

    from . import chapters as split

    known = news.explorable(VAULT)
    chapters = [c.strip() for c in (args.chapters or "").split(",") if c.strip()] or [
        c for c in split.default_explored(VAULT) if c in known]
    unknown = [c for c in chapters if c not in known]
    if unknown:
        sys.exit(f"vault-watch: no such chapter to explore: {', '.join(unknown)} (the guide has: {', '.join(known)})")

    def run(work: Path, llm) -> dict:
        with tempfile.TemporaryDirectory() as folder:  # what the check reads its chapters from (verify.options)
            (Path(folder) / "options.json").write_text(json.dumps({"chapters": chapters}), encoding="utf-8")
            return verify.run_explore(VAULT, Path(folder), {}, llm)

    _paid_check(args, "explore", "add", f"The exploration of {len(chapters)} chapter(s), one call each with the web,", "--add",
                run, each=("usd_chapter", len(chapters)))


def chapters_command(args) -> None:
    """The chapters of the guide as the agent has them; --propose: a model's split from the outline of the guide
    (its cost said first, asked for unless --yes), printed as the lines of the manifest, written there with --write;
    --automatic: the declared chapters removed from the manifest."""
    from datetime import date

    from . import chapters, config, verify
    from .guide import GuideError
    from .llm import create, step_model

    def table(view: dict, why: dict | None = None) -> None:
        print(f"{'chapter':<52}{'pages':>6}{'KB':>8}  explored  from")
        for c in view["chapters"]:
            print(f"{c['name'][:50]:<52}{c['pages']:>6}{c['kb']:>8.0f}  {'yes' if c['explore'] else 'no':<8}  "
                  f"{'manifest' if c['declared'] else 'automatic'}"
                  + (f"\n    {why[c['name']]}" if why and why.get(c["name"]) else ""))
        for note in view["notes"]:
            print(f"! {note}")

    try:
        if args.automatic:
            changed = chapters.write(VAULT, [])
            print("vault-watch: the manifest declares no chapter any more (review with git diff, then commit)." if changed
                  else "vault-watch: the manifest declares no chapter: nothing to change.")
            return
        if not args.propose:
            table(chapters.view(VAULT))
            return
        settings = config.load(CONFIG_HOME)
        prices = Prices.of_home(CONFIG_HOME, settings)
        llm = create("reasoning", JOURNAL, settings, prices)
        client = llm.for_step("chapters") if hasattr(llm, "for_step") else llm
        billing = client.capabilities().billing if hasattr(client, "capabilities") else "token"
        usd = verify.chapters_usd(VAULT, step_model(settings, "chapters"), prices)
        paid = {"subscription": "taken from the subscription, not billed", "none": "a local model, not billed"}.get(
            billing, f"≈ {usd:.2f} $")
        print(f"A model reads the outline of the guide (titles, headings, weights; not the text) and proposes chapters: {paid}.")
        if not (args.yes or _confirm("Run it? [y/N] ")):
            print("vault-watch: nothing run.")
            return
        llm.run, llm.kind = f"chapters-{date.today().isoformat()}", "verify"
        declared, why, usage = chapters.propose(VAULT, llm)
        if not declared:
            sys.exit("vault-watch: the model proposed no chapter that names a page of the guide")
        table(chapters.view(VAULT, declared), why)
        print(f"\n(≈ {(usage or {}).get('cost_usd', 0):.2f} $) The lines of the manifest:\n\n{chapters.toml(declared)}")
        if args.write:
            chapters.write(VAULT, declared)
            print(f"vault-watch: written to {VAULT / 'vault-watch.toml'}. Review with git diff, then commit it as any change of the guide.")
        else:
            print("Nothing is written. Paste these lines at the end of the manifest, or run again with --write.")
    except GuideError as e:
        sys.exit(f"vault-watch: {e}")


def _paid_check(args, check: str, prefix: str, what: str, flag: str, run, each: tuple[str, int] | None = None) -> None:
    """A check that reads the whole guide, from the command line: its estimate, the question, the call
    (`run(work, llm)`), the findings to a file and how to send those kept to a run (`fix <thread> --findings … <flag>`).
    `each`: a part of the estimate that is counted several times (its key, how many: a chapter explored)."""
    from datetime import date

    from . import config, verify
    from .llm import create

    settings = config.load(CONFIG_HOME)
    table = Prices.of_home(CONFIG_HOME, settings)
    llm = create("reasoning", JOURNAL, settings, table)
    apart = {step: own["model"] for step, own in settings["steps"].items() if own.get("model")}
    estimate = verify.estimates(VAULT, {}, settings["models"], table, apart)[check]
    billing = llm.capabilities().billing if hasattr(llm, "capabilities") else "token"
    usd = estimate["usd"] + (estimate[each[0]] * each[1] if each else 0)
    paid = {"subscription": "taken from the subscription, not billed", "none": "a local model, not billed"}.get(
        billing, f"≈ {usd:.2f} $")
    print(f"\n{what} reads the whole guide (≈ {estimate['tokens']:,} tokens): {paid}.")
    if not (args.yes or _confirm("Run it? [y/N] ")):
        print("vault-watch: nothing run.")
        return
    today = date.today().isoformat()
    llm.run, llm.kind = f"{prefix}-{today}", "verify"
    work = HOME / "reports"
    work.mkdir(parents=True, exist_ok=True)
    result = run(work, llm)
    out = args.out or work / f"{prefix}-{today}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(f"{f}\n" for f in result["findings"]), encoding="utf-8")
    for n, finding in enumerate(result["findings"], start=1):
        print(f"{n}. {finding}")
    cost = sum(u.get("cost_usd", 0) for u in result.get("usage", []))
    print(f"\nvault-watch: {result['summary']} (≈ {cost:.2f} $): {out}")
    if result["findings"]:
        print(f"Keep in that file the lines to act on, then: vault-watch fix {prefix}-{today} --findings {out} {flag}")


def make_deps(thread: str, kind: str) -> Deps:
    """Model clients labelled with the run, so the cost journal says which run paid for what.
    `view` builds a graph that only reads checkpoints: no client, no API key needed."""
    from . import config
    from .llm import create

    if kind == "view":
        return Deps(vault=VAULT, home=HOME, llm=None)
    vault.sync(VAULT)
    settings = config.load(CONFIG_HOME)  # read for each run: a change in the Settings page applies to the next one
    # What this run set for its own steps (an engine, a model, an effort chosen when it was started), over the settings
    settings["steps"] = config.over(settings["steps"], config.run_steps(HOME, thread))
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
    kind = f.add_mutually_exclusive_group()
    kind.add_argument("--translation", action="store_true",
                      help="translation divergences: fix the mirror pages against the source ones (no web, no cross-check)")
    kind.add_argument("--compact", action="store_true",
                      help="findings of `compact --report`: trims instead of corrections (no web, their own cross-check)")
    kind.add_argument("--add", action="store_true",
                      help="leads of `news`: each one checked on the web, then written where it belongs; a line of "
                      "the file that begins with ! is dug deeper, in a call of its own")
    nw = sub.add_parser("news", help="what a reader would look for in the guide and not find: a list of leads, nothing "
                        "verified or edited (one model call that reads the whole guide)")
    nw.add_argument("--out", type=Path, help="where to write the leads, one per line (default: reports/ of the guide's "
                    "working folder)")
    nw.add_argument("--yes", action="store_true", help="run the model call without asking")
    nw.add_argument("--explore", action="store_true", help="the other way to find leads: the web explored chapter by "
                    "chapter, one call each (it costs more, and finds what nobody thought to ask)")
    nw.add_argument("--chapters", help="--explore: the chapters to explore, e.g. 02-materiel,03-stack (default: all, "
                    "except those the manifest declares with explore = false; `vault-watch chapters` lists them)")
    ch = sub.add_parser("chapters", help="the chapters the agent works on (exploration of the web, check of the "
                        "translations, reading by chapter); --propose asks a model for a split")
    ch.add_argument("--propose", action="store_true", help="one model call reads the outline of the guide (titles, "
                    "headings, weights) and proposes chapters; nothing is written without --write")
    ch.add_argument("--write", action="store_true", help="--propose: put the proposal in the manifest of the guide's "
                    "folder (review it with git diff, commit it as any change of the guide)")
    ch.add_argument("--automatic", action="store_true", help="remove the chapters the manifest declares: back to the "
                    "automatic rule")
    ch.add_argument("--yes", action="store_true", help="--propose: run the model call without asking")
    cp = sub.add_parser("compact", help="what the guide weighs, page by page (no model); --report lists what could be trimmed")
    cp.add_argument("--report", action="store_true", help="one model call reads the whole guide and lists what weighs; "
                    "nothing is edited")
    cp.add_argument("--out", type=Path, help="--report: where to write the findings, one per line (default: reports/ of "
                    "the guide's working folder)")
    cp.add_argument("--yes", action="store_true", help="--report: run the model call without asking")
    e = sub.add_parser("eval", help="replay a past watch on the vault as it was, score it against the merged PR")
    e.add_argument("--issue", type=int, required=True)
    e.add_argument("--at", required=True, help="vault commit to replay on (before the human's PR)")
    e.add_argument("--truth", help="base..head of the human's PR; omit when the human applied nothing")
    e.add_argument("--variant", choices=["keyword", "full"], required=True,
                   help="keyword: excerpts only; full: plus the cross-check on the whole vault")
    e.add_argument("--tag", default="", help="suffix of the run label, to replay again after a change (e.g. -v2)")
    e.add_argument("--judge", choices=["api", "claude-code"],
                   help="the engine of the judge (its reasoning model, a Claude one): by default the watch's engine when it "
                        "is a Claude one, otherwise Claude Code when signed in with a subscription, otherwise the API")
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
    co.add_argument("--previous", type=Path, help="the previous watch (a watch.json, or a folder of them): what the "
                    "watched pages said then (default: the watches kept in the working folder)")
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
    if args.cmd == "compact":
        HOME.mkdir(parents=True, exist_ok=True)
        compact_command(args)
        return
    if args.cmd == "news":
        HOME.mkdir(parents=True, exist_ok=True)
        news_command(args)
        return
    if args.cmd == "chapters":
        chapters_command(args)
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
            from . import evaluate, llm

            judge = create("reasoning", JOURNAL, settings, Prices.of_home(CONFIG_HOME, settings),
                           name=evaluate.judge_engine(args.judge, llm.engine(settings["engine"])))
            judge.kind = "eval"
            run_eval(args, deps, saver, judge)
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
            elif args.compact:
                from . import compact

                items, proposal, usage = compact.propose(VAULT, findings, deps.llm, excerpts)
            elif args.add:
                from . import news

                # A line that begins with « ! » is a lead to dig deeper: a call of its own
                deep = {f[1:].strip() for f in findings if f.startswith("!")}
                findings = [f[1:].strip() if f.startswith("!") else f for f in findings]
                items, proposal, usage = news.propose(VAULT, findings, deps.llm, excerpts, deep=deep)
            else:
                items, proposal, usage = fix.propose(VAULT, findings, deps.llm, excerpts=excerpts)
            mode = "translation" if args.translation else "compact" if args.compact else "add" if args.add else "fix"
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
