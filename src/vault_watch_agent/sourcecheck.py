"""Questioning the sources of a watch: is each one still there, does the list still fit the guide, what to change.

`sources.py` says what each feed brought, from the history on the machine. This module asks the sources themselves
(network, no model) and reads the guide, then proposes changes to the feeds file; the editor picks, and `edit`
rewrites the file for a pull request.

    result = check(guide, home, runs)          # {"probes": {feed id: …}, "proposals": [...], "checked": date}
    text = edit(feeds_text, chosen_proposals)  # the feeds.json with the chosen changes, its layout kept

Three questions, each answered by a rule:
  the source     unreachable; repository archived or renamed; nothing published for STALE_DAYS (said, never
                 proposed for removal: a tool that went quiet is a fact about the guide's subject, the page that
                 recommends it is what to look at)
  the guide      a repository or a Hugging Face publisher cited in at least MIN_PAGES pages and followed by no
                 feed; a feed whose subject no page names any more; a tool followed for its releases and not for
                 its security advisories
  the yield      the feeds `sources.table` calls noise

A proposal is `recommended` when a fact settles it (the source is gone, archived or moved); the others are
judgement calls, listed unticked.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import collect, sources
from .guide import Guide

STALE_DAYS = 180   # nothing published for that long: said on the page
MIN_PAGES = 2      # cited in at least that many pages to be proposed as a feed
MAX_ADDITIONS = 25  # the most cited ones; each costs a request or two to see how it publishes
WORKERS = 6
GITHUB = re.compile(r"github\.com/([A-Za-z0-9][\w.-]*)/([A-Za-z0-9][\w.-]*)")
HUGGINGFACE = re.compile(r"huggingface\.co/([A-Za-z0-9][\w.-]*)/([A-Za-z0-9][\w.-]*)")
# First path segments that are pages of the site, not an account
NOT_OWNERS = {"features", "orgs", "topics", "sponsors", "marketplace", "about", "collections", "settings", "apps",
              "user-attachments", "advisories", "login", "search", "security", "enterprise", "pricing", "readme"}
NOT_AUTHORS = {"docs", "blog", "spaces", "datasets", "api", "papers", "collections", "models", "learn", "tasks",
               "organizations", "join", "pricing", "posts", "chat", "settings", "login", "new"}
REPO_FEEDS = ("github-releases", "github-tags", "github-advisories")


# -- the source itself ------------------------------------------------------------------------------------------

def probe(feed: dict, collector: collect.Collector) -> dict:
    """What the source says today: {state, last, detail…}. `state`: ok, unreachable, archived, moved, empty (it
    answers and lists nothing), stale. A releases feed reads GitHub's releases.atom, which also lists the tags
    of a project that tags without releasing: nothing more to ask."""
    kind, out = feed.get("type", "rss"), {"state": "ok", "last": "", "error": ""}
    try:
        if kind in REPO_FEEDS:
            repo = collector._gh(f"https://api.github.com/repos/{feed['repo']}")
            name = str(repo.get("full_name") or "")
            if name and name.lower() != feed["repo"].lower():  # GitHub redirects a renamed repository
                out.update(state="moved", moved=name)
            if repo.get("archived"):
                out["state"] = "archived"
        items = collector.read(feed)
        dates = sorted(d for d in (collect.parse_date(i.get("date")) for i in items) if d)
        out["last"] = dates[-1].strftime("%Y-%m-%d") if dates else ""
        if out["state"] != "ok":
            return out
        if not items and kind in ("rss", "youtube", "huggingface-author"):
            out["state"] = "empty"
        elif _stale(out["last"], collector) and kind != "github-advisories":  # no advisory for months: good news
            out["state"] = "stale"
    except Exception as e:  # noqa: BLE001 - whatever the source answers, the check goes on with the others
        out.update(state="unreachable", error=(str(e) or type(e).__name__)[:200])
    return out


def _stale(day: str, collector: collect.Collector) -> bool:
    return bool(day) and day < (collector._now() - timedelta(days=STALE_DAYS)).strftime("%Y-%m-%d")


def publishes(repo: str, collector: collect.Collector) -> bool:
    """Whether a repository the guide cites is worth a releases feed: there, not archived, and a release or a tag
    in the last STALE_DAYS."""
    try:
        info = collector._gh(f"https://api.github.com/repos/{repo}")
        if info.get("archived") or str(info.get("full_name") or "").lower() != repo.lower():
            return False
        dates = [collect.parse_date(i.get("date")) for i in collect.parse_feed(
            collector._get(f"https://github.com/{repo}/releases.atom"))]
        last = max((d for d in dates if d), default=None)
        return bool(last) and not _stale(last.strftime("%Y-%m-%d"), collector)
    except Exception:  # noqa: BLE001
        return False


# -- the guide ----------------------------------------------------------------------------------------------------

def cited(guide: Guide) -> tuple[dict[str, dict], dict[str, dict], str]:
    """The GitHub repositories and the Hugging Face publishers the pages link to, each with its pages, and the
    text of all the pages in lower case (to look a name up): ({repo key: {name, pages}}, {author key: …}, text)."""
    repos: dict[str, dict] = {}
    authors: dict[str, dict] = {}
    texts = []
    for path in guide.pages():
        text = path.read_text(encoding="utf-8", errors="replace")
        texts.append(text.lower())
        rel = path.relative_to(guide.root).as_posix()
        for owner, name in set(GITHUB.findall(text)):
            name = name.removesuffix(".git").rstrip(".")
            if owner.lower() in NOT_OWNERS or not name:
                continue
            repos.setdefault(f"{owner}/{name}".lower(), {"name": f"{owner}/{name}", "pages": []})["pages"].append(rel)
        for author in {a for a, _ in HUGGINGFACE.findall(text)}:
            if author.lower() not in NOT_AUTHORS:
                authors.setdefault(author.lower(), {"name": author, "pages": []})["pages"].append(rel)
    return repos, authors, "\n".join(texts)


def named(feed: dict, text: str) -> bool:
    """Whether a page names what the feed follows: its repository, or the name of the project or the publisher."""
    subject = feed.get("repo") or feed.get("author") or ""
    names = {subject.lower(), subject.split("/")[-1].lower()}
    return any(n and re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text) for n in names)


# -- proposals ----------------------------------------------------------------------------------------------------

def propose(feed_list: list[dict], rows: list[dict], probes: dict[str, dict], guide: Guide,
            collector: collect.Collector) -> list[dict]:
    """The changes worth looking at, each {id, action (remove, change, add), feed, why, recommended, …}."""
    repos, authors, text = cited(guide)
    by_id = {f["id"]: f for f in feed_list}
    row = {r["id"]: r for r in rows}
    out: list[dict] = []

    def add(action: str, feed: dict, why: str, recommended: bool = False, **detail) -> None:
        out.append({"action": action, "feed": feed, "why": why, "recommended": recommended, **detail})

    for fid, p in probes.items():
        feed = by_id[fid]
        if p["state"] == "unreachable":
            add("remove", feed, "unreachable", recommended=_gone(p["error"]), error=p["error"])
        elif p["state"] == "archived":
            add("remove", feed, "archived", recommended=True)
        elif p["state"] == "moved":
            add("change", feed, "moved", recommended=True, new={**feed, "repo": p["moved"]})
        elif p["state"] == "empty":
            add("remove", feed, "empty")
    settled = {o["feed"]["id"] for o in out}
    for feed in feed_list:
        if feed["id"] in settled:
            continue
        r = row.get(feed["id"], {})
        if r.get("verdict") == "noise":
            add("remove", feed, "noise", judged=r["judged"], kept=r["useful"])
        elif (feed.get("repo") or feed.get("author")) and not feed.get("discovery") and not named(feed, text):
            add("remove", feed, "not-named")

    # What the guide cites and no feed follows, the most cited first
    followed = {f["repo"].lower() for f in feed_list if f.get("repo")}
    owner = guide.repository.lower().split("/")[0]  # the maintainer's own repositories are not a watch subject
    missing = sorted((r for key, r in repos.items() if key not in followed and key.split("/")[0] != owner
                      and len(r["pages"]) >= MIN_PAGES),
                     key=lambda r: (-len(r["pages"]), r["name"].lower()))[:MAX_ADDITIONS]
    with ThreadPoolExecutor(WORKERS) as pool:
        kinds = list(pool.map(lambda r: publishes(r["name"], collector), missing))
    taken = set(by_id)
    for r, alive in zip(missing, kinds):
        if alive:
            new = {"id": _new_id(r["name"].split("/")[-1], taken), "domain": _domain(r["pages"], repos, feed_list),
                   "type": "github-releases", "repo": r["name"], "tier": "A"}
            add("add", new, "cited", pages=len(r["pages"]), examples=r["pages"][:3])
    hf = {f["author"].lower() for f in feed_list if f.get("author")}
    model_domain = next((f["domain"] for f in feed_list if f.get("type") == "huggingface-author"), "")
    for key, a in sorted(authors.items(), key=lambda kv: (-len(kv[1]["pages"]), kv[0])):
        if key not in hf and len(a["pages"]) >= MIN_PAGES and model_domain:
            new = {"id": _new_id(f"hf-{a['name']}", taken), "domain": model_domain, "type": "huggingface-author",
                   "author": a["name"], "tier": "A"}
            add("add", new, "cited", pages=len(a["pages"]), examples=a["pages"][:3])
    # A tool followed for its releases and not for its advisories: the insurance is missing
    advised = {f["repo"].lower() for f in feed_list if f.get("type") == "github-advisories"}
    security = next((f["domain"] for f in feed_list if f.get("type") == "github-advisories"), "")
    for feed in feed_list:
        if feed.get("type") in ("github-releases", "github-tags") and feed["repo"].lower() not in advised and security \
                and probes.get(feed["id"], {}).get("state") in ("ok", "stale") and feed["id"] not in settled:
            new = {"id": _new_id(f"adv-{feed['id']}", taken), "domain": security, "type": "github-advisories",
                   "repo": feed["repo"], "tier": feed.get("tier", "A")}
            add("add", new, "no-advisories", of=feed["id"])
    for n, o in enumerate(out, start=1):
        o["id"] = f"S{n}"
    return out


def _gone(error: str) -> bool:
    """A source that answers « not found » is gone; one that times out or refuses may be back tomorrow."""
    return "404" in error or "410" in error


def _new_id(wanted: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9.]+", "-", wanted.lower()).strip("-") or "feed"
    name, n = base, 1
    while name in taken:
        n += 1
        name = f"{base}-{n}"
    taken.add(name)
    return name


def _domain(pages: list[str], repos: dict[str, dict], feed_list: list[dict]) -> str:
    """The domain of a new feed: the one of the feeds whose repositories are cited in the same pages, else the
    first of the file. The editor corrects it in the pull request if it is wrong."""
    where = set(pages)
    count: dict[str, int] = {}
    for f in feed_list:
        if f.get("type") in ("github-releases", "github-tags") and f.get("repo"):
            shared = len(where & set(repos.get(f["repo"].lower(), {}).get("pages", [])))
            if shared:
                count[f["domain"]] = count.get(f["domain"], 0) + shared
    return max(count, key=lambda domain: count[domain]) if count else feed_list[0]["domain"]


def check(guide: Guide, home: Path, runs: list[dict[str, str]], collector: collect.Collector | None = None,
          progress=None) -> dict:
    """Asks every source, reads the guide, and returns the probes and the proposals. No model; one or two requests
    per feed, a few more for the repositories the guide cites and no feed follows."""
    collector = collector or collect.Collector.of_guide(guide)
    feed_list = sources.feeds(guide)
    rows = sources.table(feed_list, sources.watches(guide, home), runs)

    def one(feed):
        result = probe(feed, collector)
        if progress:
            progress(feed["id"])
        return feed["id"], result

    with ThreadPoolExecutor(WORKERS) as pool:
        probes = dict(pool.map(one, feed_list))
    return {"checked": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "stale_days": STALE_DAYS,
            "min_pages": MIN_PAGES, "probes": probes,
            "proposals": propose(feed_list, rows, probes, guide, collector)}


# -- the feeds file -----------------------------------------------------------------------------------------------

def edit(text: str, proposals: list[dict]) -> str:
    """The feeds file with the proposals applied. A file with one feed per line (as the guides write them) keeps
    its layout: the lines of the feeds left alone are not touched, nor the blank lines between their groups, the
    comment and the other keys. Any other layout is written again from its data."""
    config = json.loads(text)
    layout = _one_per_line(text, config["feeds"])
    # The lines between the brackets, in order: (feed, its line as written) for a feed, (None, "") for a blank
    # line; a feed added or changed has no line yet (None) and is written at the end.
    if layout:
        feeds_left = iter(config["feeds"])
        entries: list[tuple[dict | None, str | None]] = [(dict(next(feeds_left)), line) if line else (None, "") for line in layout[1]]
    else:
        entries = [(dict(f), None) for f in config["feeds"]]
    position = lambda fid: next((n for n, (f, _) in enumerate(entries) if f and f.get("id") == fid), None)  # noqa: E731
    for p in proposals:
        fid = p["feed"]["id"]
        at = position(fid)
        if p["action"] == "add":
            if at is not None:
                raise ValueError(f"{fid}: a feed of that name is already in the file")
            same = [n for n, (f, _) in enumerate(entries) if f and f.get("type") == p["feed"].get("type")]
            entries.insert((same[-1] + 1) if same else len(entries), (dict(p["feed"]), None))  # with its kind
        elif at is None:
            raise ValueError(f"{fid}: no such feed in the file (it changed since the check)")
        elif p["action"] == "remove":
            del entries[at]
        else:
            entries[at] = (dict(p["new"]), None)
    feeds = [f for f, _ in entries if f]
    collect.check({**config, "feeds": [dict(f) for f in feeds]})
    if layout is None:
        return json.dumps({**config, "feeds": feeds}, ensure_ascii=False, indent=2) + "\n"
    head, _, indent, tail = layout
    # A group emptied by the removals leaves no double blank line, nor one at either end
    kept = [e for n, e in enumerate(entries) if e[0] or (0 < n < len(entries) - 1 and entries[n - 1][0])]
    while kept and not kept[-1][0]:
        kept.pop()
    last = max((n for n, (f, _) in enumerate(kept) if f), default=-1)
    lines = ["" if f is None else (line if line is not None else indent + _line(f)) + ("," if n < last else "")
             for n, (f, line) in enumerate(kept)]
    return head + "".join(f"{ln}\n" for ln in lines) + tail


def _line(feed: dict) -> str:
    return "{ " + ", ".join(f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in feed.items()) + " }"


def _one_per_line(text: str, feeds: list[dict]) -> tuple[str, list[str], str, str] | None:
    """(what is before the feeds, the lines between the brackets, each feed's without its comma and "" for a blank
    one, the indent of the feeds, what is after) when the file holds one feed per line."""
    m = re.search(r'"feeds"\s*:\s*\[[ \t]*\r?\n', text)
    if not m:
        return None
    rest = text[m.end():]
    end = re.search(r"^[ \t]*\]", rest, re.M)
    if not end:
        return None
    block = [ln.rstrip().removesuffix(",") for ln in rest[:end.start()].split("\n")[:-1]]
    written = [ln for ln in block if ln]
    try:
        if [json.loads(ln) for ln in written] != feeds:
            return None
    except ValueError:
        return None
    indent = written[0][:len(written[0]) - len(written[0].lstrip(" \t"))] if written else "    "
    return text[:m.end()], block, indent, rest[end.start():]



# -- the pull request ---------------------------------------------------------------------------------------------

def reason(p: dict) -> str:
    """Why a proposal, in a sentence, for the pull request (the interface has its own wording, in two languages)."""
    feed = p["feed"]
    return {
        "unreachable": lambda: f"the source does not answer ({p.get('error', '')})",
        "archived": lambda: "the repository is archived",
        "moved": lambda: f"the repository moved to {p['new']['repo']}",
        "empty": lambda: "the source answers and lists nothing",
        "noise": lambda: (f"{p['judged']} items judged by the model over the period, {p['kept']} kept, no correction "
                          "proposed"),
        "not-named": lambda: "no page of the guide names it any more",
        "cited": lambda: f"cited in {p['pages']} pages ({', '.join(p['examples'])}), followed by no feed",
        "no-advisories": lambda: f"{feed.get('repo')} is followed for its releases, not for its security advisories",
    }[p["why"]]()


def title(chosen: list[dict]) -> str:
    count = {a: sum(1 for p in chosen if p["action"] == a) for a in ("remove", "change", "add")}
    parts = [f"{n} {word}" for a, word in (("remove", "removed"), ("change", "changed"), ("add", "added")) if (n := count[a])]
    return f"chore(watch): sources of the watch ({', '.join(parts)})"


def body(chosen: list[dict], file: str) -> str:
    verb = {"remove": "Remove", "change": "Change", "add": "Add"}
    what = lambda p: p["feed"].get("repo") or p["feed"].get("author") or p["feed"].get("url") or p["feed"].get("name") or ""  # noqa: E731
    rows = "\n".join(f"- {verb[p['action']]} `{p['feed']['id']}` ({p['feed'].get('type', 'rss')}"
                     f"{', ' + what(p) if what(p) else ''}): {reason(p)}." for p in chosen)
    return ("## Summary\n"
            "Changes to the sources of the watch, chosen in vault-watch-agent's « Sources » page after a check of "
            "each source (is it still there, does the guide still cite it, what did it bring).\n\n"
            f"{rows}\n\n"
            f"## Files changed\n- `{file}`\n\n"
            "## Test plan\n- [x] The feeds file is read by the agent's collector (`vault-watch collect` accepts it)\n"
            "- [x] No content page changed\n")


def publish(guide: Guide, home: Path, chosen: list[dict], *, today: str, open_pull_request=None) -> dict:
    """The chosen proposals on a branch of the guide, from its base branch up to date: the feeds file edited and
    committed, the branch pushed and a pull request opened when the guide has a repository (`open_pull_request`,
    the forge's). Returns {branch, pr_url}; the branch stays local for a guide without a repository."""
    from . import inputs, vault

    file = guide.watch.feeds
    git = lambda *args, cwd, text=None: inputs.run(["git", *args], cwd=cwd, text=text)  # noqa: E731
    with vault._GIT:  # not while a run syncs the base or resets the reading copy
        vault._sync(guide.root, guide.base_branch)
        branch, n = f"chore/watch-sources-{today}", 1
        existing = git("branch", "--list", "--format=%(refname:short)", f"{branch}*", cwd=guide.root).split()
        while branch in existing:
            n += 1
            branch = f"chore/watch-sources-{today}-{n}"
        worktree = home / "worktrees" / branch.replace("/", "-")
        git("worktree", "add", "-q", "-B", branch, str(worktree), guide.base_branch, cwd=guide.root)
    try:
        path = worktree / file
        path.write_text(edit(path.read_text(encoding="utf-8"), chosen), encoding="utf-8", newline="\n")
        git("add", file, cwd=worktree)
        reasons = "\n".join(f"{p['action']} {p['feed']['id']}: {reason(p)}" for p in chosen)
        git("commit", "-q", "-F", "-", cwd=worktree, text=f"{title(chosen)}\n\n{reasons}\n")  # on stdin: it can be long
        url = ""
        if guide.repository and open_pull_request:
            git("push", "-q", "-u", "origin", branch, cwd=worktree)
            url = open_pull_request(guide.repository, base=guide.base_branch, head=branch, title=title(chosen),
                                    body=body(chosen, file), cwd=worktree)
    finally:
        with vault._GIT:  # the branch holds the commit; its folder is no longer needed
            try:
                git("worktree", "remove", "--force", str(worktree), cwd=guide.root)
            except RuntimeError:
                pass
    return {"branch": branch, "pr_url": url}
