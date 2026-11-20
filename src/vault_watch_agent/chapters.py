"""The chapters of a guide: the pages the agent works on together.

Three steps work chapter by chapter: the exploration of the web (one call per chapter, the costly one), the check of
the translations (one call per chapter), and every step that reads the whole guide when the model's window is too
small for it (reading.py). Where the chapters come from, the most particular first:

1. the manifest of the guide (`[[chapter]]`: a name, paths, and `explore = false` for a chapter left unticked when
   the web is explored), written by hand or from a model's proposal (`propose`), reviewed either way;
2. for the pages no declared chapter takes, and for a guide that declares none, the automatic rule: one chapter per
   top folder, a folder heavier than BIG_KB split along its subfolders (in slices of pages when it has none), the
   top folders lighter than SMALL_KB gathered (in bundles that stay under half of BIG_KB).

    chapters.of(vault_dir)                    # [Group(name, pages, explore, declared, paths)], in the guide's order
    chapters.view(vault_dir)                  # the same for a screen: weights, where each comes from, what is off
    chapters.propose(vault_dir, llm)          # a model's split from the outline of the guide: (declared, usage)
    chapters.rewrite(manifest_text, declared) # the manifest with its [[chapter]] tables replaced
"""

from __future__ import annotations

import json
import math
import re
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from pydantic import BaseModel, Field

from . import guide as guide_mod
from . import prompts, steps, vault
from .guide import Chapter, Guide, GuideError

BIG_KB = 150   # a folder heavier than this is split
SMALL_KB = 20  # top folders lighter than this are gathered into one chapter
ROOT = "(root)"  # the pages at the root of the guide
NEEDS = "1.3.0"  # the first agent that reads [[chapter]]: an older one refuses the manifest (unknown key)


@dataclass(frozen=True)
class Group:
    name: str
    pages: list[Path]
    explore: bool = True       # ticked by default when the web is explored chapter by chapter
    declared: bool = False     # from the manifest (else the automatic rule)
    paths: tuple[str, ...] = ()


def _bytes(pages: list[Path]) -> int:
    return sum(p.stat().st_size for p in pages)


# -- the automatic rule ---------------------------------------------------------------------------------------
def automatic(root: Path, pages: list[Path]) -> list[tuple[str, list[Path]]]:
    """`pages` (sorted) grouped without a manifest: [(name, pages)]."""
    top: dict[str, list[Path]] = {}
    for p in pages:
        parts = p.relative_to(root).parts
        top.setdefault(parts[0] if len(parts) > 1 else ROOT, []).append(p)
    light = [name for name, group in top.items() if _bytes(group) < SMALL_KB * 1024]
    out: list[tuple[str, list[Path]]] = []
    # A home page, an « about » folder: gathered, not a call each; a bundle stays under half of BIG_KB
    bundles: list[list[str]] = []
    weight = 0
    for name in light:
        size = _bytes(top[name])
        if not bundles or weight + size > BIG_KB * 1024 / 2:
            bundles.append([])
            weight = 0
        bundles[-1].append(name)
        weight += size
    for names in bundles:
        if len(names) > 1:
            name = " + ".join(names) if len(names) <= 3 else f"{names[0]} + {len(names) - 1} others"
            out.append((name, sorted(p for n in names for p in top[n])))
            top = {n: g for n, g in top.items() if n not in names}
    for name, group in top.items():
        out += [(name, group)] if name == ROOT else _split(root, name, group, 1)
    return sorted(out, key=lambda g: g[1][0])


def _split(root: Path, name: str, pages: list[Path], depth: int) -> list[tuple[str, list[Path]]]:
    """A folder as one chapter, or several when it is heavier than BIG_KB: one per subfolder (each split again if
    need be, the light ones gathered with the pages of the folder itself), or slices of pages of similar weight
    when it has no subfolder."""
    if _bytes(pages) <= BIG_KB * 1024:
        return [(name, pages)]
    sub: dict[str, list[Path]] = {}
    for p in pages:
        parts = p.relative_to(root).parts
        sub.setdefault(parts[depth] if len(parts) > depth + 1 else "", []).append(p)
    if len(sub) < 2:
        only = next(iter(sub))
        return _split(root, f"{name}/{only}", pages, depth + 1) if only else _slices(name, pages)
    pieces: list[tuple[str, list[Path]]] = []
    rest: list[Path] = sub.pop("", [])
    for folder, group in sub.items():
        if _bytes(group) < SMALL_KB * 1024:
            rest += group
        else:
            pieces += _split(root, f"{name}/{folder}", group, depth + 1)
    if rest:
        pieces.append((f"{name} (rest)" if pieces else name, sorted(rest)))
    return pieces


def _slices(name: str, pages: list[Path]) -> list[tuple[str, list[Path]]]:
    """Pages in order, cut into slices of similar weight, none heavier than BIG_KB unless one page is."""
    total = _bytes(pages)
    target = total / math.ceil(total / (BIG_KB * 1024))
    slices: list[list[Path]] = [[]]
    weight = 0
    for p in pages:
        size = p.stat().st_size
        if slices[-1] and weight + size / 2 > target:
            slices.append([])
            weight = 0
        slices[-1].append(p)
        weight += size
    if len(slices) == 1:
        return [(name, pages)]
    return [(f"{name} {n}/{len(slices)}", group) for n, group in enumerate(slices, start=1)]


# -- the chapters of a guide ----------------------------------------------------------------------------------
def resolve(guide: Guide) -> list[Group]:
    """The chapters of `guide`: those it declares (a page goes to the first that takes it; one that takes no page is
    left out), then the automatic rule for the pages left. In the order of the guide's pages."""
    left = guide.pages()
    rel = lambda p: p.relative_to(guide.root).as_posix()  # noqa: E731
    groups: list[Group] = []
    for c in guide.chapters:
        mine = [p for p in left if c.takes(rel(p))]
        if mine:
            taken = set(mine)
            left = [p for p in left if p not in taken]
            groups.append(Group(c.name, mine, c.explore, True, c.paths))
    names = {g.name for g in groups}
    for name, pages in automatic(guide.root, left):
        groups.append(Group(f"{name} (auto)" if name in names else name, pages))
    return sorted(groups, key=lambda g: g.pages[0])


def of(vault_dir: Path) -> list[Group]:
    return resolve(vault.guide_of(vault_dir))


def view(vault_dir: Path, declared: list[Chapter] | tuple[Chapter, ...] | None = None) -> dict:
    """The chapters for a screen or the command line, as the guide has them or as `declared` would give them:
    {source, chapters: [{name, pages, kb, first, last, explore, declared, paths, cover, readonly}], notes}. `notes`
    says what is off, in English: a declared chapter that takes no page, one much heavier than BIG_KB."""
    guide = vault.guide_of(vault_dir)
    if declared is not None:
        guide = replace(guide, chapters=tuple(declared))
    groups = resolve(guide)
    rel = lambda p: p.relative_to(guide.root).as_posix()  # noqa: E731
    every = {rel(p) for g in groups for p in g.pages}
    rows = [{"name": g.name, "pages": len(g.pages), "kb": round(_bytes(g.pages) / 1024, 1), "first": rel(g.pages[0]),
             "last": rel(g.pages[-1]), "explore": g.explore, "declared": g.declared, "paths": list(g.paths),
             # the paths that would declare this chapter as it is (a screen starts an edit from them)
             "cover": list(g.paths) if g.declared else _cover([rel(p) for p in g.pages], every),
             "readonly": all(guide.is_readonly(rel(p)) for p in g.pages)} for g in groups]
    found = {g.name for g in groups}
    notes = [f"« {c.name} » takes no page ({', '.join(c.paths)}): another chapter before it takes them, or the paths "
             "match nothing" for c in guide.chapters if c.name not in found]
    notes += [f"« {r['name']} » weighs {r['kb']:.0f} KB: above {BIG_KB} KB, a call on it reads and writes a lot"
              for r in rows if r["declared"] and r["kb"] > BIG_KB * 1.5]
    return {"source": "manifest" if guide.chapters else "automatic", "chapters": rows, "notes": notes,
            "big_kb": BIG_KB, "small_kb": SMALL_KB}


def _cover(group: list[str], every: set[str]) -> list[str]:
    """The shortest paths that name exactly the pages of `group`: a folder when every page of the guide under it is
    in the group, the page itself otherwise."""
    mine, out, done = set(group), [], set()
    for page in group:
        if page in done:
            continue
        parts = page.split("/")[:-1]
        for depth in range(1, len(parts) + 1):
            folder = "/".join(parts[:depth]) + "/"
            under = {p for p in every if p.startswith(folder)}
            if under <= mine:
                out.append(folder)
                done |= under
                break
        else:
            out.append(page)
            done.add(page)
    return out


def default_explored(vault_dir: Path) -> list[str]:
    """The chapters explored when none is named: all of them, except those the manifest declares `explore = false`."""
    return [g.name for g in of(vault_dir) if g.explore]


# -- a model's proposal ---------------------------------------------------------------------------------------
PROPOSE = """You group the pages of <<GUIDE>> into chapters, for the agent that keeps it up to date. The agent \
works chapter by chapter in three places: it explores the web for what is new, one call per chapter (the costly \
one: each chapter explored is a paid call); it checks the translations, one call per chapter; and with a model \
whose window is too small for the guide, it reads the guide chapter by chapter. Above: the outline of the guide, \
every page with its path, its weight, its title and its headings (not its text).

A chapter is a set of pages a reader would look up together and that the same news would change: one subject, one \
audience.

- Every page belongs to one chapter. A page goes to the first chapter whose paths take it, so list the particular \
before the general. A page you leave out is grouped by an automatic rule (its top folder): leave none out.
- paths: a folder ending with / (everything under it), a glob (* within a folder, ** across folders), or the path \
of one page, all relative to the guide. Prefer folders. Name pages one by one only when a folder mixes subjects and \
has no subfolder.
- Weight: a chapter of 40 to <<BIG>> KB is comfortable. Split a heavier folder along its subfolders or its \
subjects when they differ. Gather light neighbours (a home page, an « about » folder) into one chapter. Do not \
split one subject only to even out the weights: a glossary stays one chapter, however heavy.
- Most guides need 4 to 12 chapters. Follow the structure the guide already has when it is sound; you are not \
asked to reorganise it.
- explore: false for a chapter where the web has nothing new to bring by itself: a glossary or lexicon (its \
definitions follow the other chapters), the pages about the guide or its project, indexes, legal notices, \
changelogs. true for the others.
- name: short, in <<LANG>>, as a reader would call the chapter; no comma, no quotation mark.
- why: one sentence in English: what holds these pages together, and why it is explored or not."""


class Proposed(BaseModel):
    name: str = Field(description="Short name of the chapter, in the guide's language; no comma, no quotation mark")
    paths: list[str] = Field(description="Folders ending with /, globs or page paths, relative to the guide")
    explore: bool = Field(description="False when the web has nothing new to bring to this chapter by itself")
    why: str = Field(description="One sentence in English: what holds these pages together, why explored or not")


class Split(BaseModel):
    chapters: list[Proposed]


_TITLE = re.compile(r"^title:\s*(.+?)\s*$", re.M)
_HEADING = re.compile(r"^(#{1,2})\s+(.+?)\s*#*\s*$")


def outline(vault_dir: Path) -> str:
    """Every page of the guide in a few lines: path, weight, title (front matter, else its first heading), and its
    headings of level 2 (a heading inside a code block is not one). What a split is decided on."""
    out = []
    for p in vault.pages(vault_dir):
        text = vault.read(p).replace("\r\n", "\n")
        front = vault.FRONTMATTER.match(text)
        title = _TITLE.search(front.group(0)) if front else None
        title = title.group(1).strip("\"'") if title else ""
        headings, fenced = [], False
        for line in text[front.end() if front else 0:].split("\n"):
            if line.lstrip().startswith(("```", "~~~")):
                fenced = not fenced
            found = None if fenced else _HEADING.match(line)
            if found and len(found.group(1)) == 1:
                title = title or found.group(2)
            elif found:
                headings.append(found.group(2))
        out.append(f"- {p.relative_to(vault_dir).as_posix()} ({p.stat().st_size / 1024:.1f} KB): {title or p.stem}"
                   + "".join(f"\n    ## {h}" for h in headings))
    return "\n".join(out)


def propose(vault_dir: Path, llm) -> tuple[list[Chapter], dict[str, str], dict]:
    """A split of the guide by a model, from its outline: (chapters to declare, {name: why}, usage). Checked as a
    manifest would be: a path that names no page is dropped, a chapter left without a path too, a name is cleaned
    (no comma, no quote) and made unique. Nothing is written: the editor reviews it (`view(vault_dir, declared)`)."""
    system = prompts.fill(PROPOSE.replace("<<BIG>>", str(BIG_KB)), vault_dir)
    result, usage = llm.parse(system=system, prompt="Propose the chapters of this guide.", schema=Split,
                              effort=steps.effort("chapters"), node="chapters",
                              context=f"<outline>\n{outline(vault_dir)}\n</outline>")
    pages = [p.relative_to(vault_dir).as_posix() for p in vault.pages(vault_dir)]
    declared, why = [], {}
    for c in (result.chapters if result else []):
        name = re.sub(r'[,"\r\n]+', " ", c.name).strip()[:80] or "?"
        while any(name == d.name for d in declared):
            name += " (2)"
        paths = tuple(dict.fromkeys(p.strip() for p in c.paths
                                    if p.strip() and any(guide_mod.under(page, p.strip()) for page in pages)))
        if paths:
            declared.append(Chapter(name, paths, bool(c.explore)))
            why[name] = c.why.strip()
    return declared, why, usage


# -- the manifest ---------------------------------------------------------------------------------------------
HEAD = ("# Chapters: the pages the agent works on together (exploration of the web, check of the translations,\n"
        "# reading by chapter). A page goes to the first chapter that takes it; the pages none takes follow the\n"
        "# automatic rule. Written from the interface (« Chapters ») or by `vault-watch chapters`; editable by hand.\n")


def toml(declared: list[Chapter] | tuple[Chapter, ...]) -> str:
    """The [[chapter]] tables of a manifest ("" when there is none)."""
    q = lambda text: json.dumps(text, ensure_ascii=False)  # a TOML basic string is a JSON string  # noqa: E731
    blocks = [f"[[chapter]]\nname = {q(c.name)}\npaths = [{', '.join(q(p) for p in c.paths)}]\n"
              + ("" if c.explore else "explore = false\n") for c in declared]
    return (HEAD + "\n".join(blocks)) if blocks else ""


def rewrite(text: str, declared: list[Chapter] | tuple[Chapter, ...]) -> str:
    """The manifest `text` with its [[chapter]] tables (and their heading comment) replaced by `declared`, put at
    its end; the rest is kept as it is, comments included. The result is read back: GuideError when it is not a
    manifest any more (it never should)."""
    head = set(HEAD.splitlines())
    kept, inside = [], False
    for line in text.replace("\r\n", "\n").split("\n"):
        bare = line.strip()
        if bare.startswith("["):
            inside = bare.split("#")[0].strip() == "[[chapter]]"
        if not inside and line not in head:
            kept.append(line)
    body = "\n".join(kept).rstrip("\n") + "\n"
    new = body + (("\n" + toml(declared)) if declared else "")
    try:
        found = guide_mod.chapters_of(tomllib.loads(new).get("chapter", []))
    except tomllib.TOMLDecodeError as e:
        raise GuideError(f"the manifest would not be valid TOML any more ({e})") from e
    if [(c.name, c.paths, c.explore) for c in found] != [(c.name, tuple(c.paths), c.explore) for c in declared]:
        raise GuideError("the manifest read back does not give the chapters asked")
    return new


def write(folder: Path, declared: list[Chapter] | tuple[Chapter, ...]) -> bool:
    """Puts `declared` in the manifest of `folder` (the file's own line endings kept). False when it already says
    so; GuideError when the folder has no manifest (the chapters of a guide without one cannot be declared)."""
    manifest = folder / guide_mod.MANIFEST
    if not manifest.is_file():
        raise GuideError(f"no {guide_mod.MANIFEST} in {folder}: `vault-watch init` writes one, the chapters go there")
    raw = vault.read(manifest)
    new = rewrite(raw, declared)
    if "\r\n" in raw:
        new = new.replace("\n", "\r\n")
    if new == raw:
        return False
    vault.write(manifest, new)
    return True


TITLE = "chore(watch): chapters of the guide"


def publish(guide: Guide, home: Path, declared: list[Chapter] | tuple[Chapter, ...], *, today: str,
            open_pull_request=None) -> dict:
    """`declared` written to the manifest on a branch of the guide (chore/chapters-<date>), from its base branch up
    to date, in a worktree of the agent: committed, then pushed with a pull request when the guide has a repository
    (`open_pull_request`, the forge's). Returns {branch, pr_url}; the branch stays local for a guide without a
    repository. The guide's folder is not touched. GuideError when the manifest already declares these chapters
    (nothing is left behind); when the push or the pull request fails, the commit stays on its branch."""
    from . import inputs

    git = lambda *args, cwd: inputs.run(["git", *args], cwd=cwd)  # noqa: E731
    with vault._GIT:  # not while a run syncs the base or resets the reading copy
        vault._sync(guide.root, guide.base_branch)
        branch, n = f"chore/chapters-{today}", 1
        existing = git("branch", "--list", "--format=%(refname:short)", f"{branch}*", cwd=guide.root).split()
        while branch in existing:
            n += 1
            branch = f"chore/chapters-{today}-{n}"
        worktree = home / "worktrees" / branch.replace("/", "-")
        git("worktree", "prune", cwd=guide.root)
        git("worktree", "add", "-q", "-B", branch, str(worktree), guide.base_branch, cwd=guide.root)
    committed = False
    try:
        if not write(worktree, declared):
            raise GuideError(f"nothing to change: the manifest on {guide.base_branch} already declares these chapters")
        git("add", guide_mod.MANIFEST, cwd=worktree)
        what = f"{len(declared)} declared" if declared else "back to the automatic rule"
        git("commit", "-q", "-m", f"{TITLE} ({what})", cwd=worktree)
        committed = True
        url = ""
        if guide.repository and open_pull_request:
            git("push", "-q", "-u", "origin", branch, cwd=worktree)
            url = open_pull_request(guide.repository, base=guide.base_branch, head=branch, title=TITLE,
                                    body=pull_request_body(worktree, declared), cwd=worktree)
    finally:
        with vault._GIT:  # the branch holds the commit; its folder is no longer needed
            for args in (["worktree", "remove", "--force", str(worktree)], *([] if committed else [["branch", "-q", "-D", branch]])):
                try:
                    git(*args, cwd=guide.root)
                except RuntimeError:
                    pass
    return {"branch": branch, "pr_url": url}


def pull_request_body(vault_dir: Path, declared: list[Chapter] | tuple[Chapter, ...]) -> str:
    """What the pull request of a split says: the chapters it gives, with their weight."""
    rows = view(vault_dir, declared)["chapters"]
    lines = ["The chapters the agent works on (exploration of the web, check of the translations, reading by "
             f"chapter), declared in `{guide_mod.MANIFEST}`. No page changes.", "",
             "| Chapter | Pages | Weight | Explored by default | From |", "| :-- | --: | --: | :-- | :-- |"]
    lines += [f"| {r['name']} | {r['pages']} | {r['kb']:.0f} KB | {'yes' if r['explore'] else 'no'} | "
              f"{'declared' if r['declared'] else 'automatic rule'} |" for r in rows]
    if not declared:
        lines.insert(2, "No chapter is declared any more: the automatic rule groups every page.")
    else:
        lines += ["", f"`[[chapter]]` needs vault-watch-agent {NEEDS} or newer wherever this guide is read, a workflow that "
                  "collects its watch included: an older agent refuses the manifest (unknown key). Update those before "
                  "merging."]
    return "\n".join(lines) + "\n"
