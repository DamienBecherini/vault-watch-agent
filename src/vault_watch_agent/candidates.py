"""The discovery registry (ROADMAP D3, decided with the user on 2026-11-25): what the agent found that the guide does
not cover yet, followed over time instead of triaged once.

A candidate is a model, a tool, a piece of hardware or something else, known by its name and by the addresses where
it was seen. It moves through states, each change kept in its history:

    lead → watching → confirmed → proposed → added          or dismissed, with a reason and a date to look again

The registry is a JSON file of the guide, the one its manifest names (`[watch] candidates`), so that the weekly
collection, which runs where the guide is (its CI), knows it too: it drops the addresses of the candidates it
tracks (as it drops those of `seen`) and lists those whose date to look again has passed (collect.py).

    reg = Registry.load(path)
    c, new = reg.note("Reflection Beam 501B", "https://…", origin="watch issue-30", seen="2026-10-10", kind="model")
    reg.move(c["id"], "watching", reason="weights announced for later", recheck="2026-12-01", today="2026-11-25")
    reg.save()

No model here: a name is matched by its normalised form, an address by its canonical form.

The page « Candidates » (routes/candidates.py, D3.2) changes a draft of the registry kept by the agent, never the
guide's folder; `publish` writes it on a branch of the guide and opens the pull request (and adds the key to the
manifest when it has none yet). What the agent finds feeds the same draft (D3.3, `note_all`): the possible additions
a watch run sets aside, the leads the editor dismisses on a check.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit

from . import guide as guide_mod
from . import inputs, vault

SCHEMA = 1
STATES = ("lead", "watching", "confirmed", "proposed", "added", "dismissed")
KINDS = ("model", "tool", "hardware", "other")  # the kinds of a guide whose manifest declares none
LOOK_AGAIN = ("watching", "dismissed")  # the states a date to look again applies to
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class RegistryError(ValueError):
    """The registry cannot be read or a change to it is refused: said to the editor as it is."""


def kinds_of(watch) -> tuple[str, ...]:
    """The kinds of candidates of a guide: those its manifest declares ([watch] candidate_kinds), else KINDS; « other »
    always, last."""
    declared = tuple(getattr(watch, "candidate_kinds", ()) or ())
    return tuple(dict.fromkeys((*(declared or KINDS), "other")))


def key(name: str) -> str:
    """The normalised form of a name: « Reflection Beam 501B-A23B » and « reflection-beam-501b-a23b » are one."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def canonical(url: str) -> str:
    """An address as the registry compares it: no scheme case, no « www. », no trailing slash, no fragment; the query
    kept (a page may be one by its query)."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    return urlunsplit((parts.scheme.lower() or "https", host, parts.path.rstrip("/"), parts.query, ""))


def _date(value: str, what: str) -> str:
    if not _DATE.fullmatch(value or ""):
        raise RegistryError(f"{what}: a date as YYYY-MM-DD, not {value!r}")
    return value


@dataclass
class Registry:
    path: Path
    candidates: list[dict] = field(default_factory=list)
    kinds: tuple[str, ...] = KINDS  # those `note` accepts (kinds_of the guide); a candidate keeps a kind removed since

    # -- the file -------------------------------------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path, kinds: tuple[str, ...] = KINDS) -> Registry:
        """The registry of `path`; empty when the file does not exist yet."""
        if not path.is_file():
            return cls(path, kinds=kinds)
        try:
            return cls.parse(path.read_text(encoding="utf-8"), path, kinds)
        except OSError as e:
            raise RegistryError(f"{path.name}: {e}") from e

    @classmethod
    def parse(cls, text: str, path: Path, kinds: tuple[str, ...] = KINDS) -> Registry:
        """The registry written in `text` (a file, or the file as a branch of the guide has it), saved at `path`."""
        try:
            data = json.loads(text)
        except ValueError as e:
            raise RegistryError(f"{path.name}: {e}") from e
        if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("candidates"), list):
            raise RegistryError(f"{path.name}: not a registry of candidates (schema {SCHEMA}, a list `candidates`)")
        return cls(path, data["candidates"], kinds)

    def text(self) -> str:
        """Sorted by state then name, two spaces, one line per source: a diff a reviewer can read."""
        order = {s: i for i, s in enumerate(STATES)}
        self.candidates.sort(key=lambda c: (order.get(c.get("state") or "", 99), key(c.get("name", ""))))
        return json.dumps({"schema": SCHEMA, "candidates": self.candidates}, ensure_ascii=False, indent=2) + "\n"

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self.text(), encoding="utf-8", newline="\n")

    # -- reading --------------------------------------------------------------------------------------------------
    def get(self, cid: str) -> dict:
        for c in self.candidates:
            if c["id"] == cid:
                return c
        raise RegistryError(f"no candidate {cid!r}")

    def find(self, name: str = "", url: str = "") -> dict | None:
        """The candidate seen at `url`, else the one of that name (normalised), else None."""
        if url:
            where = canonical(url)
            for c in self.candidates:
                if any(canonical(s["url"]) == where for s in c.get("sources", [])):
                    return c
        k = key(name) if name else ""
        return next((c for c in self.candidates if k and (c["id"] == k or k in map(key, c.get("aka", [])))), None)

    def urls(self) -> set[str]:
        """Every address a candidate was seen at, canonical: what the collection no longer proposes."""
        return {canonical(s["url"]) for c in self.candidates for s in c.get("sources", [])}

    def due(self, today: str) -> list[dict]:
        """The candidates whose date to look again has come, the oldest date first."""
        return sorted((c for c in self.candidates if c.get("state") in LOOK_AGAIN and c.get("recheck")
                       and c["recheck"] <= today), key=lambda c: c["recheck"])

    # -- changes --------------------------------------------------------------------------------------------------
    def note(self, name: str, url: str = "", *, origin: str, seen: str, kind: str = "other",
             title: str = "", note: str = "") -> tuple[dict, bool]:
        """A candidate seen once more: its source added (an address not known yet) and its last date moved, or a new
        candidate in state `lead`. (candidate, True when it is new)."""
        _date(seen, "seen")
        if kind not in self.kinds:
            raise RegistryError(f"kind {kind!r}: one of {', '.join(self.kinds)}")
        found = self.find(name, url)
        source = {"url": url, "seen": seen, "origin": origin, **({"title": title} if title else {})}
        if found:
            known = {canonical(s["url"]) for s in found.get("sources", [])}
            if url and canonical(url) not in known:
                found.setdefault("sources", []).append(source)
            found["last_seen"] = max(found.get("last_seen", seen), seen)
            return found, False
        cid = key(name)
        if not cid:
            raise RegistryError("a candidate needs a name")
        if any(c["id"] == cid for c in self.candidates):  # pragma: no cover - find() matched it by name
            raise RegistryError(f"{cid!r} already exists")
        c = {"id": cid, "name": name.strip(), "kind": kind, "state": "lead", "reason": "", "recheck": "",
             "first_seen": seen, "last_seen": seen, "sources": [source] if url else [],
             "history": [{"date": seen, "state": "lead", "note": f"seen: {origin}" + (f": {note.strip()}" if note.strip() else "")}]}
        self.candidates.append(c)
        return c, True

    def move(self, cid: str, state: str, *, today: str, reason: str = "", recheck: str = "") -> dict:
        """A candidate to another state. Dismissing needs a reason; a date to look again applies to `watching` and
        `dismissed` only, and is cleared by any other state."""
        if state not in STATES:
            raise RegistryError(f"state {state!r}: one of {', '.join(STATES)}")
        _date(today, "today")
        if state == "dismissed" and not reason.strip():
            raise RegistryError("a dismissed candidate needs a reason")
        if recheck:
            if state not in LOOK_AGAIN:
                raise RegistryError(f"a date to look again applies to {' or '.join(LOOK_AGAIN)}, not {state}")
            if _date(recheck, "recheck") <= today:
                raise RegistryError(f"the date to look again ({recheck}) is not after today ({today})")
        c = self.get(cid)
        c["state"], c["reason"] = state, reason.strip() or (c.get("reason", "") if state == c.get("state") else "")
        c["recheck"] = recheck if state in LOOK_AGAIN else ""
        c.setdefault("history", []).append({"date": today, "state": state, "note": reason.strip(),
                                            **({"recheck": recheck} if recheck else {})})
        return c

    def merge(self, into: str, other: str, *, today: str) -> dict:
        """Two candidates that are one entity (D2: « Qwen3-235B » and « Qwen3 30B »), made one: `into` keeps its
        name and state, takes the sources and the facts of `other` it does not have, its days seen, its history, and
        its name as another name (`aka`: noted again under it, it comes here); `other` is gone."""
        _date(today, "today")
        if into == other:
            raise RegistryError("a candidate cannot be merged into itself")
        a, b = self.get(into), self.get(other)
        known = {canonical(s["url"]) for s in a.get("sources", [])}
        a.setdefault("sources", []).extend(s for s in b.get("sources", []) if canonical(s["url"]) not in known)
        facts = {f["url"] for f in a.get("facts", [])}
        if b.get("facts"):
            a.setdefault("facts", []).extend(f for f in b["facts"] if f["url"] not in facts)
        a["first_seen"] = min(filter(None, (a.get("first_seen"), b.get("first_seen"))), default=today)
        a["last_seen"] = max(filter(None, (a.get("last_seen"), b.get("last_seen"))), default=today)
        a["aka"] = list(dict.fromkeys([*a.get("aka", []), b["name"], *b.get("aka", [])]))
        a.setdefault("history", []).extend({**h, "note": f"{b['name']}: {h.get('note', '')}".rstrip(": ")}
                                           for h in b.get("history", []))
        a["history"].append({"date": today, "state": a["state"], "note": f"merged: {b['name']} ({b['state']})"})
        a["history"].sort(key=lambda h: h.get("date", ""))
        self.candidates.remove(b)
        return a


# -- the draft the agent keeps (D3.2), and what feeds it (D3.3) ---------------------------------------------------
DRAFT = "candidates-draft.json"  # in the agent's home: the registry as changed, until merged
PENDING = "candidates-pr.json"   # in the agent's home: the pull request of the registry, while it is open
LOCK = threading.Lock()          # one change of the draft at a time (the page, a run, a check)


def draft_path(home: Path) -> Path:
    return home / DRAFT


def place(guide, home: Path) -> tuple[str, str]:
    """(the path the manifest names, "" when none; the path the registry has or will have: the manifest's, else the
    one its open pull request gives it, else one beside the watch's files)."""
    if guide.watch.candidates:
        return guide.watch.candidates, guide.watch.candidates
    try:
        opened = json.loads((home / PENDING).read_text(encoding="utf-8")).get("path", "")
    except (OSError, ValueError):
        opened = ""
    return "", opened or default_path(guide.watch)


def followed(guide, home: Path) -> bool:
    """Whether the guide uses the registry: its manifest names one, or the editor started a draft. Else what the
    agent finds is not noted (a guide that does not want it is left as it was)."""
    return bool(guide.watch.candidates) or draft_path(home).is_file()


def base_of(guide, home: Path, rel: str) -> Registry:
    """The registry as the base branch of the guide's folder has it (git show: the folder's own files and branch do
    not matter); empty when it has none yet. Saved, it becomes the draft."""
    kinds = kinds_of(guide.watch)
    try:
        text = inputs.run(["git", "show", f"{guide.base_branch}:{rel}"], cwd=guide.root)
    except RuntimeError:
        return Registry(draft_path(home), kinds=kinds)
    return Registry.parse(text, draft_path(home), kinds)


def working(guide, home: Path, rel: str) -> tuple[Registry, Registry]:
    """(the registry as it is changed: the draft, else the base's; the base's)."""
    base = base_of(guide, home, rel)
    if draft_path(home).is_file():
        return Registry.load(draft_path(home), base.kinds), base
    return Registry(draft_path(home), [dict(c) for c in base.candidates], base.kinds), base


def note_all(guide, home: Path, found: list[dict], *, origin: str, seen: str) -> list[str]:
    """What the agent found, noted in the draft: each {name, url, why?, dismiss?} becomes a candidate (or a source
    more of one already followed), dismissed with the reason `dismiss` when it is new or still a lead. Nothing when
    the guide does not use the registry. Its kind is guessed from its address and a new candidate not dismissed is
    read, through the readers the guide names (enrich.py, D1; a failure leaves it as it is). Returns the names of the
    new candidates."""
    from . import enrich  # enrich reads through collect, which imports this module

    if not found or not followed(guide, home):
        return []
    readers = enrich.readers_of(guide.watch)
    _, rel = place(guide, home)
    new_names = []
    with LOCK:
        reg, _ = working(guide, home, rel)
        for f in found:
            name, url = (f.get("name") or "").strip(), (f.get("url") or "").strip()
            if not name:
                continue
            c, new = reg.note(name[:120], url, origin=origin, seen=seen, kind=enrich.guess_kind(url, reg.kinds, readers),
                              note=(f.get("why") or "")[:300])
            if new:
                new_names.append(c["name"])
            if f.get("dismiss") and (new or c["state"] == "lead"):
                reg.move(c["id"], "dismissed", today=seen, reason=f["dismiss"])
            elif new:
                enrich.enrich(c, today=seen, readers=readers)
        reg.save()
    return new_names


def to_judge(guide, home: Path, ids: list[str] | tuple = ()) -> list[dict]:
    """The candidates a check « candidates » judges with the whole guide (opportunity.py, D4), each with the score
    of its entity (entities.py): those named, else the open ones, from the registry as the page shows it. [] when the
    guide does not use the registry."""
    from . import entities, opportunity

    if not followed(guide, home):
        return []
    _, rel = place(guide, home)
    reg, _ = working(guide, home, rel)
    tiers = entities.load_tiers(guide.root / guide.watch.source_tiers if guide.watch.source_tiers else None)
    scores = entities.view(reg.candidates, tiers)
    return [{**c, "score": scores[c["id"]]} for c in opportunity.chosen(reg.candidates, list(ids), scores)]


def judged(guide, home: Path, judgements: list[dict], *, check: str, today: str) -> int:
    """The judgements of a check « candidates » kept in their candidates (`judgement`: verdict, why, pages, date to
    look again, the check and its day), and a line in their history; the state is the editor's to change. Returns
    how many were kept (a candidate gone from the draft meanwhile is skipped)."""
    if not judgements or not followed(guide, home):
        return 0
    _, rel = place(guide, home)
    n = 0
    with LOCK:
        reg, _ = working(guide, home, rel)
        for j in judgements:
            try:
                c = reg.get(j.get("id", ""))
            except RegistryError:
                continue
            c["judgement"] = {"date": today, "check": check, **{k: v for k, v in j.items() if k not in ("id", "name")}}
            c.setdefault("history", []).append({"date": today, "state": c["state"],
                                                "note": f"judged with the guide ({check}): {j.get('verdict', '')}"})
            n += 1
        if n:
            reg.save()
    return n


# -- the pull request of the registry (D3.2) -----------------------------------------------------------------------
TITLE = "chore(watch): the registry of candidates"
NEEDS = "1.7.0"  # the agent that knows `[watch] candidates`: an older one refuses the manifest (unknown key)


def changes(before: list[dict], after: list[dict]) -> list[dict]:
    """What `after` changes in `before`, one change each, by name: {what: new | state | sources | removed, name, …}."""
    old = {c["id"]: c for c in before}
    out: list[dict] = []
    for c in sorted(after, key=lambda c: key(c.get("name", ""))):
        o = old.pop(c["id"], None)
        if o is None:
            out.append({"what": "new", "name": c["name"], "kind": c.get("kind", ""), "state": c.get("state", ""),
                        "reason": c.get("reason", ""), "recheck": c.get("recheck", "")})
            continue
        if any(o.get(k, "") != c.get(k, "") for k in ("state", "reason", "recheck")):
            out.append({"what": "state", "name": c["name"], "from": o.get("state", ""), "state": c.get("state", ""),
                        "reason": c.get("reason", ""), "recheck": c.get("recheck", "")})
        added = len(c.get("sources", [])) - len(o.get("sources", []))
        if added > 0:
            out.append({"what": "sources", "name": c["name"], "n": added})
        if c.get("judgement") and c["judgement"] != o.get("judgement"):
            out.append({"what": "judged", "name": c["name"], "verdict": c["judgement"].get("verdict", "")})
    into = {key(n): c["name"] for c in after for n in c.get("aka", [])}  # a candidate merged into another (D2)
    out += [{"what": "merged", "name": o["name"], "into": into[o["id"]]} if o["id"] in into
            else {"what": "removed", "name": o["name"]} for o in old.values()]
    return out


def said(change: dict) -> str:
    """A change in English, for the pull request."""
    name, what = change["name"], change["what"]
    why = (f": {change['reason']}" if change.get("reason") else "") + (f", look again on {change['recheck']}" if change.get("recheck") else "")
    if what == "new":
        return f"**{name}** ({change['kind']}) added, {change['state']}{why}"
    if what == "state":
        return f"**{name}**: {change['from']} → {change['state']}{why}"
    if what == "sources":
        return f"**{name}**: {change['n']} source(s) added"
    if what == "judged":
        return f"**{name}** judged with the guide: {change['verdict']}"
    if what == "merged":
        return f"**{name}** merged into **{change['into']}** (one entity)"
    return f"**{name}** removed"


def default_path(watch) -> str:
    """Where a guide whose manifest names no registry keeps it: beside its seen file or its feeds, else watch/."""
    beside = watch.seen or watch.feeds
    return str(PurePosixPath(beside).parent / "candidates.json") if beside else "watch/candidates.json"


def valid_path(rel: str) -> str:
    """A path for the registry, relative to the guide and inside it, a .json file; else RegistryError."""
    rel = rel.strip().replace("\\", "/")
    parts = PurePosixPath(rel).parts
    if not rel.endswith(".json") or rel.startswith("/") or ":" in rel or ".." in parts or not parts:
        raise RegistryError(f"{rel!r}: a .json file of the guide, its path relative to the guide (watch/candidates.json)")
    return rel


def with_key(raw: str, rel: str) -> str:
    """The manifest `raw` naming the registry `rel` in its [watch] section (the section added when it has none)."""
    lines = raw.replace("\r\n", "\n").rstrip("\n").split("\n")
    entry = f'candidates = "{rel}"'
    try:
        i = next(n for n, line in enumerate(lines) if line.strip() == "[watch]")
    except StopIteration:
        lines += ["", "[watch]", entry]
    else:
        j = i + 1
        while j < len(lines) and not lines[j].lstrip().startswith("["):
            j += 1
        while j > i + 1 and not lines[j - 1].strip():
            j -= 1
        lines.insert(j, entry)
    text = "\n".join(lines) + "\n"
    return text.replace("\n", "\r\n") if "\r\n" in raw else text


def pull_request_body(found: list[dict], rel: str, key_added: bool) -> str:
    lines = [f"The registry of discovery (`{rel}`): what the agent found that the guide does not cover yet, followed "
             "over time. Changed from the page « Candidates » of vault-watch-agent. No page of the guide changes.", ""]
    lines += [f"- {said(c)}" for c in found] or ["- (the file as the agent keeps it)"]
    if key_added:
        lines += ["", f"The manifest now names it (`[watch] candidates`): this needs vault-watch-agent {NEEDS} or newer "
                  "wherever the guide is read, the workflow that collects its watch included; an older agent refuses the "
                  "manifest (unknown key). Update those before merging."]
    return "\n".join(lines) + "\n"


def publish(guide, home: Path, text: str, rel: str, found: list[dict], *, stamp: str, branch: str = "",
            pr_url: str = "", open_pull_request=None) -> dict:
    """The registry `text` written at `rel` on a branch of the guide, in a worktree of the agent, from its base branch
    up to date; the manifest names it when it does not yet. `branch` (with its `pr_url`): the branch of a pull request
    still open, which gets one more commit. Committed, then pushed with a pull request when the guide has a
    repository (`open_pull_request`, the forge's). Returns {branch, pr_url}. The guide's folder is not touched.
    RegistryError when the branch already holds this registry."""
    from . import inputs

    git = lambda *args, cwd: inputs.run(["git", *args], cwd=cwd)  # noqa: E731
    with vault._GIT:  # not while a run syncs the base or resets the reading copy
        vault._sync(guide.root, guide.base_branch)
        existing = git("branch", "--list", "--format=%(refname:short)", "chore/candidates*", cwd=guide.root).split()
        again = bool(branch) and branch in existing
        if not again:
            branch, n, pr_url = f"chore/candidates-{stamp}", 1, ""
            while branch in existing:
                n += 1
                branch = f"chore/candidates-{stamp}-{n}"
        worktree = home / "worktrees" / branch.replace("/", "-")
        git("worktree", "prune", cwd=guide.root)
        if again:
            git("worktree", "add", "-q", str(worktree), branch, cwd=guide.root)
        else:
            git("worktree", "add", "-q", "-B", branch, str(worktree), guide.base_branch, cwd=guide.root)
    committed, url = False, pr_url
    try:
        target = worktree / rel
        changed = [rel] if not target.is_file() or target.read_text(encoding="utf-8") != text else []
        if changed:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
        manifest = worktree / guide_mod.MANIFEST
        key_added = manifest.is_file() and not guide_mod.load(worktree).watch.candidates
        if key_added:
            vault.write(manifest, with_key(vault.read(manifest), rel))
            changed.append(guide_mod.MANIFEST)
        if not changed:
            raise RegistryError(f"nothing to publish: {branch if again else guide.base_branch} already holds this registry")
        git("add", *changed, cwd=worktree)
        git("commit", "-q", "-m", f"{TITLE} ({len(found)} change(s))", cwd=worktree)
        committed = True
        if guide.repository and open_pull_request:
            git("push", "-q", "-u", "origin", branch, cwd=worktree)
            if not url:
                url = open_pull_request(guide.repository, base=guide.base_branch, head=branch, title=TITLE,
                                        body=pull_request_body(found, rel, key_added), cwd=worktree)
    finally:
        with vault._GIT:  # the branch holds the commit; its folder is no longer needed
            for args in (["worktree", "remove", "--force", str(worktree)],
                         *([] if committed or again else [["branch", "-q", "-D", branch]])):
                try:
                    git(*args, cwd=guide.root)
                except RuntimeError:
                    pass
    return {"branch": branch, "pr_url": url}
