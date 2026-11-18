"""Connecting a guide: `vault-watch init` writes its manifest from what the folder shows, `vault-watch doctor` says
what is ready and what is missing before a first run.

    text = propose(Path("../my-guide"))       # a vault-watch.toml to review, every guess commented
    for line in diagnose(Path("../my-guide"), home): print(line)

Nothing here calls a model or the network, except `gh` when the guide names a GitHub repository.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import config, llm
from .guide import LANGUAGES, MANIFEST, GuideError, Guide, legacy, load, matches

# Folders and files that are tooling, not pages, when the guide has them.
TOOLING = ("node_modules/**", "build/**", "dist/**", "public/**", "scripts/**", "docs/**", "assets/**")
NOT_PAGES = ("README.md", "CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md", "CHANGELOG.md", "LICENSE.md")
DATE_FIELDS = ("last_modified", "lastUpdated", "last_updated", "updated", "modified", "date_modified")
STOPWORDS = {
    "en": "the and of to is in that for with are this you can",
    "fr": "le la les des est une pour que dans qui sur avec",
    "de": "der die das und ist nicht mit auf für ein eine sich",
    "es": "el los las que del una para con por está como pero",
    "it": "il che della per una con non sono gli delle anche",
    "pt": "que não uma para com dos das como mais pelo pela",
}


# -- init ---------------------------------------------------------------------------------------------------
def propose(root: Path) -> str:
    """A manifest for the guide in `root`, from what the folder shows; each guess says where it comes from."""
    pages = _markdown(root)
    mirrors = _mirrors(root, pages)
    sources = [p for p in pages if not any(p.startswith(m) for m in mirrors.values())]
    language, why_language = _language(root, sources)
    field, why_field = _date_field(root, sources)
    repository = _github_repository(root)
    exclude = ([f"{d}/**" for d in _underscored(root)] + [t for t in TOOLING if (root / t.split("/")[0]).is_dir()]
               + [f for f in NOT_PAGES if (root / f).is_file()])
    own_repository = Path(_git(root, "rev-parse", "--show-toplevel") or "/nowhere").resolve() == root.resolve()
    branch = (_git(root, "symbolic-ref", "--short", "HEAD") if own_repository else "") or "main"

    q = json.dumps  # TOML basic strings are JSON strings
    lines = [
        "# Manifest of the guide, written by `vault-watch init`: check each line, then `vault-watch doctor`.",
        "# Format: docs/connect-your-guide.md (in the vault-watch-agent repository).",
        "schema = 1",
        "",
        "[guide]",
        f"name = {q(_title(root, sources))}",
        '# description = "what the guide is about, in one sentence (it goes into the prompts)"',
        (f"repository = {q(repository)}   # from the git remote: watch issues and pull requests go there"
         if repository else "# repository = \"owner/name\"   # none found: a local guide (no issue, no pull request)"),
        "# site = \"https://...\"",
        f"base_branch = {q(branch)}",
        "",
        "[content]",
        f"language = {q(language)}   # {why_language}",
        'include = ["**/*.md", "**/*.mdx"]',
        (f"exclude = [{', '.join(q(e) for e in exclude)}]   # tooling, and folders starting with _ (private notes, templates)"
         if exclude else "exclude = []"),
        (f"mirrors = {{ {', '.join(f'{c} = {q(f)}' for c, f in sorted(mirrors.items()))} }}   # folders that repeat the pages in another language"
         if mirrors else "# mirrors = { de = \"de/\" }   # none found: a folder per language that repeats the pages"),
        (f"modified_field = {q(field)}   # {why_field}" if field else f"# modified_field = \"last_modified\"   # {why_field}"),
        "",
        "[watch]",
        'source = "none"   # or "github-issue" (with label, artifact) or "file" (with path to a watch.json)',
        "",
        "# Optional: [rules] brief, translation_policy (files of the guide; the agent has defaults),",
        "# [checks] audits, claims_due, sources, version_floors (the guide's own commands; undeclared = not checked),",
        "# [budget] max_context_tokens.",
        *_script_hints(root),
        "",
    ]
    return "\n".join(lines)


def _script_hints(root: Path) -> list[str]:
    """The guide's npm scripts, as comments: some of them may be its [checks] (a test run, a link audit...)."""
    try:
        scripts = json.loads((root / "package.json").read_text(encoding="utf-8")).get("scripts", {})
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(scripts, dict) or not scripts:
        return []
    return ["#", "# Scripts of package.json that may be [checks] (audits: exit code; the others write JSON to {out}):",
            *(f"#   npm run {name}" for name in sorted(scripts, key=lambda n: (n != "test", n))[:20])]


def write(root: Path, force: bool = False) -> Path:
    """Writes the proposed manifest to `root`; FileExistsError when there is one, unless `force`."""
    path = root / MANIFEST
    if path.exists() and not force:
        raise FileExistsError(f"{path} exists (--force to replace it)")
    text = propose(root)
    load_text(text, root)  # what init writes must load
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def load_text(text: str, root: Path) -> Guide:
    import tomllib

    from .guide import parse

    return parse(tomllib.loads(text), root)


def _underscored(root: Path) -> list[str]:
    """Top folders whose name starts with _: private notes, templates, drafts. Never pages by default."""
    return sorted(d.name for d in root.iterdir() if d.is_dir() and d.name.startswith("_"))


def _markdown(root: Path) -> list[str]:
    hidden = tuple(f"{d}/" for d in _underscored(root))
    found = []
    for path in root.rglob("*.md*"):
        rel = path.relative_to(root).as_posix()
        if path.suffix in (".md", ".mdx") and path.is_file() and not any(p.startswith(".") for p in rel.split("/")) \
                and not any(matches(rel, t) for t in TOOLING) and rel not in NOT_PAGES and not rel.startswith(hidden):
            found.append(rel)
    return sorted(found)


def _mirrors(root: Path, pages: list[str]) -> dict[str, str]:
    """Top folders named after a language whose pages repeat, for the most part, paths found outside them."""
    mirrors = {}
    for code in LANGUAGES:
        folder = f"{code}/"
        inside = {p[len(folder):] for p in pages if p.startswith(folder)}
        outside = {p for p in pages if "/" not in p or not p.split("/")[0] in LANGUAGES}
        if inside and len(inside & outside) >= max(1, len(inside) // 2):
            mirrors[code] = folder
    return mirrors


def _language(root: Path, pages: list[str]) -> tuple[str, str]:
    counts: Counter = Counter()
    for rel in pages[:60]:
        words = re.findall(r"[a-zà-ÿ]+", (root / rel).read_text(encoding="utf-8", errors="replace").lower())
        for code, stop in STOPWORDS.items():
            counts[code] += sum(1 for w in words if w in stop.split())
    if not counts or counts.most_common(1)[0][1] == 0:
        return "en", "guessed: no text to read, change it if needed"
    code = counts.most_common(1)[0][0]
    return code, f"guessed from the pages ({LANGUAGES[code]}), change it if needed"


def _date_field(root: Path, pages: list[str]) -> tuple[str, str]:
    seen: Counter = Counter()
    for rel in pages:
        head = (root / rel).read_text(encoding="utf-8", errors="replace")
        if not head.startswith("---"):
            continue
        front = head.split("---", 2)[1] if head.count("---") >= 2 else ""
        for name in DATE_FIELDS:
            if re.search(rf"^{name}:\s*\S", front, re.M):
                seen[name] += 1
    if not seen:
        return "", "no date field found in the front matter: the dates of the pages will not change"
    name, n = seen.most_common(1)[0]
    return name, f"found in {n} of {len(pages)} pages: an edit sets it to the day's date"


def _title(root: Path, pages: list[str]) -> str:
    for rel in ("index.md", "README.md", *pages[:1]):
        path = root / rel
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^title:\s*\"?(.+?)\"?\s*$", text, re.M) or re.search(r"^#\s+(.+)$", text, re.M)
            if m:
                return m.group(1).strip()
    return root.resolve().name


def _github_repository(root: Path) -> str:
    url = _git(root, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$", url)
    return m.group(1) if m else ""


def _git(root: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


# -- doctor -------------------------------------------------------------------------------------------------
@dataclass
class Line:
    status: str  # ok | warn | fail | off
    label: str
    detail: str = ""

    def __str__(self) -> str:
        mark = {"ok": "✓", "warn": "!", "fail": "✗", "off": "–"}[self.status]
        return f"  {mark} {self.label}" + (f": {self.detail}" if self.detail else "")


def diagnose(root: Path, home: Path, gh_check: bool = True) -> list[Line]:
    """What is ready for a run on the guide in `root`, with the settings in `home`. A `fail` line stops a run."""
    out: list[Line] = []
    if not (root / MANIFEST).is_file():
        out.append(Line("warn", "manifest", f"no {MANIFEST}: the guide is read as the IA on-prem guide "
                                            "(`vault-watch init` writes one)"))
        guide = legacy(root)
    else:
        try:
            guide = load(root)
        except GuideError as e:
            return [Line("fail", "manifest", str(e))]
        out.append(Line("ok", "manifest", f"{guide.name} ({guide.language})"))

    pages = guide.pages()
    out.append(Line("ok" if pages else "fail", "pages", f"{len(pages)} found" if pages else
                    "none: check [content] include and exclude"))
    for code, folder in sorted(guide.mirrors.items()):
        missing = [p for p in pages if not (root / folder / p.relative_to(root)).is_file()]
        if not (root / folder).is_dir():
            out.append(Line("fail", f"mirror {code}", f"no folder {folder}"))
        else:
            out.append(Line("warn" if missing else "ok", f"mirror {code}",
                            f"{len(missing)} page(s) without a copy under {folder}" if missing else f"every page has a copy under {folder}"))
    if not guide.mirrors:
        out.append(Line("off", "mirrors", "none: no translation step"))

    top = _git(root, "rev-parse", "--show-toplevel")
    if not top:
        out.append(Line("fail", "git", "the guide is not a git repository: runs work on branches of it"))
    elif Path(top).resolve() != root.resolve():
        out.append(Line("fail", "git", f"the guide is a folder of the repository {top}: it must be the root of its own"))
    elif not _git(root, "rev-parse", "--verify", "--quiet", guide.base_branch):
        out.append(Line("fail", "git", f"no branch {guide.base_branch} ([guide] base_branch)"))
    else:
        out.append(Line("ok", "git", f"branch {guide.base_branch}"))

    needs_gh = bool(guide.repository) or guide.watch.source == "github-issue"
    if needs_gh:
        if not shutil.which("gh"):
            out.append(Line("fail", "GitHub", "gh is not installed: it opens the pull requests and reads the issues"))
        elif gh_check:
            from . import forge

            ok, detail = forge.get().can_read(guide.repository)
            out.append(Line("ok" if ok else "fail", forge.get().name, detail))
    else:
        out.append(Line("off", "GitHub", "no repository: a local guide, no pull request"))

    w = guide.watch
    if w.source == "file":
        found = (root / w.path).is_file()
        out.append(Line("ok" if found else "warn", "watch", f"file {w.path}" + ("" if found else " (not there yet)")))
    elif w.source == "github-issue":
        out.append(Line("ok" if guide.repository else "fail", "watch", f"issues labelled {w.label or 'veille'}"
                        if guide.repository else "github-issue needs [guide] repository"))
    else:
        out.append(Line("off", "watch", "none: checks and reported errors only"))

    for key in ("audits", "claims_due", "sources"):
        command = getattr(guide, key)
        if not command:
            out.append(Line("off", f"check {key}", "not declared: not checked"))
            continue
        program = shlex.split(command)[0]
        out.append(Line("ok" if shutil.which(program) else "fail", f"check {key}",
                        command if shutil.which(program) else f"{program} is not installed (or not in the PATH)"))
    if guide.version_floors:
        out.append(Line("ok", "check version_floors", guide.version_floors.script))

    out.extend(_engine(home))
    return out


def _engine(home: Path) -> list[Line]:
    try:
        settings = config.load(home)
    except config.ConfigError as e:
        return [Line("fail", "settings", str(e))]
    try:
        engine = llm.engine(settings["engine"])
    except llm.ModelError as e:
        return [Line("fail", "engine", str(e))]
    if engine == "claude-code":
        s = llm.claude_code_status(fresh=True)
        if not s["installed"]:
            return [Line("fail", "engine", "Claude Code is not installed (or choose the API in the settings)")]
        if not s["subscription"]:
            return [Line("fail" if not s["signed_in"] else "warn", "engine",
                         "Claude Code is not signed in: run `claude` once" if not s["signed_in"] else
                         "Claude Code is signed in without a subscription: its calls are billed")]
        return [Line("ok", "engine", f"Claude Code, {s['subscription']} subscription")]
    k = config.key_status(settings["key"])
    return [Line("ok" if k["found"] else "fail", "engine",
                 f"API, key from {settings['key'].split(':')[0]}" if k["found"] else
                 f"API, no key: {k['error'] or settings['key'] + ' gives nothing'}"
                 + (" (the variable must be set where vault-watch runs)" if settings["key"].startswith("env:") and not k["error"] else ""))]

