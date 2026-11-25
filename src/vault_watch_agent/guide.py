"""The guide the agent maintains, as its manifest describes it (`vault-watch.toml` at the root of the guide).

Everything the agent needs to know about a guide comes from here: where its pages are, in which language, which
folders mirror them in another one, which front matter date an edit bumps, where its watch comes from, which of its
own rules and checks it provides. A part the guide does not have is `None` (or empty), and the steps that need it are
skipped. An unknown key is an error that names it: a typo must not silently switch a part off.

    guide = load(Path("../ia-on-prem-vault"))      # reads vault-watch.toml, raises GuideError
    guide.pages()                                   # the content pages (include minus exclude)

Format: docs/connect-your-guide.md. Without a manifest, `legacy()` describes the IA on-prem guide as the agent
assumed it before manifests (French source, English mirror under en/, its scripts).
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

MANIFEST = "vault-watch.toml"
SCHEMA = 1  # version of the manifest format this code reads
WATCH_SOURCES = ("none", "issues", "file", "feeds")
SOURCE_NAMES = {"github-issue": "issues"}  # the names of before 1.0, still read (a Gitea forge has issues too)
CHECK_COMMANDS = ("audits", "claims_due", "sources")  # shell commands; {out} = a JSON file the agent reads after
LANGUAGES = {"fr": "French", "en": "English", "de": "German", "es": "Spanish", "it": "Italian", "pt": "Portuguese",
             "nl": "Dutch", "pl": "Polish", "ja": "Japanese", "zh": "Chinese", "ko": "Korean", "ru": "Russian"}


def language_name(code: str) -> str:
    """The name of a language for the prompts ("fr" -> "French"); an unknown code is given as it is."""
    return LANGUAGES.get(code.split("-")[0].lower(), code)


class GuideError(ValueError):
    """The manifest cannot be used; the message names the key and says what is expected."""


@dataclass(frozen=True)
class Watch:
    source: str = "none"    # none | issues | file | feeds
    label: str = ""         # issues: label of the watch issues
    artifact: str = ""      # issues: workflow artifact holding watch.json
    path: str = ""          # file: watch.json, relative to the guide
    feeds: str = ""         # feeds.json read by `vault-watch collect` (any source; required by "feeds")
    seen: str = ""          # collect: a file whose URLs are dropped (items the editor already triaged)
    floors: str = ""        # collect: version floors ({"floors": {feed id: version}}); default [checks] version_floors
    changes_page: str = ""  # a page where a watch adds dated lines; shown to every proposal step


@dataclass(frozen=True)
class Floors:
    script: str
    file: str


@dataclass(frozen=True)
class Chapter:
    """A chapter the manifest declares ([[chapter]]): the pages the agent works on together (chapters.py)."""
    name: str
    paths: tuple[str, ...]  # a folder ("02-hardware/"), a glob or a page; a page goes to the first chapter that takes it
    explore: bool = True    # ticked by default when the web is explored chapter by chapter

    def takes(self, page: str) -> bool:
        return any(under(page, path) for path in self.paths)


@dataclass(frozen=True)
class Guide:
    root: Path
    name: str
    language: str
    repository: str = ""            # owner/name on the forge: issues and pull requests; "" = local only
    forge: str = "github"           # where the repository is: github (through gh) or gitea (its API)
    forge_url: str = ""             # the Gitea server (http(s)://host[:port]); "" for GitHub
    forge_token: str = ""           # Gitea: where its token is, a reference (env:NAME, sops:file#NAME, file:path)
    description: str = ""           # what the guide is about, one sentence, for the prompts
    site: str = ""
    base_branch: str = "main"
    include: tuple[str, ...] = ("**/*.md", "**/*.mdx")
    exclude: tuple[str, ...] = ()
    readonly: tuple[str, ...] = ()  # pages read (excerpts, cross-check) but never edited: generated, or dated statements
    mirrors: dict[str, str] = field(default_factory=dict)  # language -> folder ("en/")
    modified_field: str | None = None
    watch: Watch = Watch()
    brief: Path | None = None
    translation_policy: Path | None = None
    audits: str | None = None
    claims_due: str | None = None
    sources: str | None = None
    version_floors: Floors | None = None
    max_context_tokens: int | None = None
    page_kb: int = 0                # a ceiling for every page, in KB (sizes.py); 0: none. A warning, never a failure
    page_budgets: tuple[tuple[str, int], ...] = ()  # (glob, KB): a ceiling for the pages of a folder; the first match wins
    growth_kb: int = 5              # a page that gained this much in 90 days is flagged…
    growth_percent: int = 25        # …or this share of what it weighed (and 2 KB at least)
    chapters: tuple[Chapter, ...] = ()  # the chapters declared; the pages none takes follow the automatic rule
    schema: int = SCHEMA
    from_manifest: bool = True

    def pages(self) -> list[Path]:
        """The content pages, in the source language: matched by `include`, not by `exclude`, outside the mirrors
        and the dot folders (tooling: .git, .agents, .claude…)."""
        skipped = tuple(self.exclude) + tuple(f"{folder}**" for folder in self.mirrors.values())
        found = set()
        for pattern in self.include:
            for path in self.root.glob(pattern):
                rel = PurePosixPath(path.relative_to(self.root).as_posix())
                if not path.is_file() or any(part.startswith(".") for part in rel.parts):
                    continue
                if any(matches(rel.as_posix(), p) for p in skipped):
                    continue
                found.add(path)
        return sorted(found)

    def is_readonly(self, page: str) -> bool:
        """Whether `page` (relative to the guide, with /) is one the agent reads but never edits."""
        return any(matches(page, p) for p in self.readonly)

    def summary(self) -> dict:
        """What the guide provides, for the interface (read-only): its parts, and the ones it lacks."""
        rel = lambda p: p.relative_to(self.root).as_posix() if p and p.is_relative_to(self.root) else (str(p) if p else "")  # noqa: E731
        return {"name": self.name, "description": self.description, "language": self.language,
                "language_name": language_name(self.language), "repository": self.repository, "forge": self.forge,
                "forge_url": self.forge_url, "site": self.site, "base_branch": self.base_branch,
                "pages": len(self.pages()),
                "mirrors": [{"language": c, "language_name": language_name(c), "folder": f}
                            for c, f in sorted(self.mirrors.items())],
                "modified_field": self.modified_field or "", "readonly": list(self.readonly),
                "watch": {"source": self.watch.source, "label": self.watch.label, "artifact": self.watch.artifact,
                          "path": self.watch.path, "feeds": self.watch.feeds, "changes_page": self.watch.changes_page},
                "rules": {"brief": rel(self.brief), "translation_policy": rel(self.translation_policy)},
                "checks": {"audits": self.audits or "", "claims_due": self.claims_due or "", "sources": self.sources or "",
                           "version_floors": self.version_floors.script if self.version_floors else ""},
                "max_context_tokens": self.max_context_tokens, "page_kb": self.page_kb,
                "page_budgets": [list(b) for b in self.page_budgets], "growth_kb": self.growth_kb,
                "growth_percent": self.growth_percent, "from_manifest": self.from_manifest,
                "chapters": [{"name": c.name, "paths": list(c.paths), "explore": c.explore} for c in self.chapters],
                "manifest": MANIFEST}

    def mirror_of(self, page: str, language: str) -> str | None:
        """Path of the copy of `page` in `language`, or None when the guide has no mirror in it."""
        folder = self.mirrors.get(language)
        return f"{folder}{page}" if folder else None


_KEYS = {
    "": {"schema", "guide", "content", "watch", "rules", "checks", "budget", "chapter"},
    "guide": {"name", "description", "repository", "forge", "forge_url", "forge_token", "site", "base_branch"},
    "content": {"language", "include", "exclude", "readonly", "mirrors", "modified_field"},
    "watch": {"source", "label", "artifact", "path", "feeds", "seen", "floors", "changes_page"},
    "rules": {"brief", "translation_policy"},
    "checks": {"audits", "claims_due", "sources", "version_floors"},
    "budget": {"max_context_tokens", "page_kb", "pages", "growth_kb", "growth_percent"},
}


def load(root: Path) -> Guide:
    """The guide at `root`, from its manifest. GuideError when there is none or it is wrong."""
    path = root / MANIFEST
    if not path.is_file():
        raise GuideError(f"no {MANIFEST} in {root} (`vault-watch init` writes one)")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise GuideError(f"{MANIFEST}: not valid TOML ({e})") from e
    return parse(data, root)


def parse(data: dict, root: Path) -> Guide:
    for table, keys in _KEYS.items():
        values = data if not table else data.get(table, {})
        if table and not isinstance(values, dict):
            raise GuideError(f"[{table}] must be a table")
        unknown = set(values) - keys - (set(_KEYS) - {""} if not table else set())
        if unknown:
            where = f"[{table}]" if table else "the top level"
            raise GuideError(f"unknown key {', '.join(sorted(unknown))} in {where} (known: {', '.join(sorted(keys))})")

    schema = data.get("schema", SCHEMA)
    if schema != SCHEMA:
        raise GuideError(f"schema = {schema!r}: this version of the agent reads schema {SCHEMA}")
    g, c, w = data.get("guide", {}), data.get("content", {}), data.get("watch", {})
    rules, checks, budget = data.get("rules", {}), data.get("checks", {}), data.get("budget", {})

    name = _text(g, "guide", "name", required=True)
    language = _text(c, "content", "language", required=True)
    repository = _text(g, "guide", "repository")
    if repository and repository.count("/") != 1:
        raise GuideError(f"[guide] repository = {repository!r}: expected owner/name")
    forge, forge_url, forge_token = _forge(g)
    mirrors = c.get("mirrors", {})
    if not isinstance(mirrors, dict) or not all(isinstance(v, str) and v.endswith("/") for v in mirrors.values()):
        raise GuideError('[content] mirrors: a table of language = "folder/" (the folder ends with /)')
    if language in mirrors:
        raise GuideError(f"[content] mirrors: {language!r} is the language of the pages, not a mirror")

    source = _text(w, "watch", "source") or "none"
    source = SOURCE_NAMES.get(source, source)
    if source not in WATCH_SOURCES:
        raise GuideError(f"[watch] source = {source!r}: one of {', '.join(WATCH_SOURCES)}")
    watch = Watch(source=source, label=_text(w, "watch", "label"), artifact=_text(w, "watch", "artifact"),
                  path=_text(w, "watch", "path"),
                  **{k: _file(root, "watch", k, w[k]).as_posix() for k in ("feeds", "seen", "floors", "changes_page")
                     if k in w})
    if source == "file" and not watch.path:
        raise GuideError('[watch] source = "file" needs path (the watch.json to read)')
    if source == "feeds" and not watch.feeds:
        raise GuideError('[watch] source = "feeds" needs feeds (the feeds.json that `vault-watch collect` reads)')

    floors = checks.get("version_floors")
    if floors is not None:
        if not isinstance(floors, dict) or set(floors) != {"script", "file"}:
            raise GuideError("[checks] version_floors: a table with script and file")
        floors = Floors(script=_file(root, "checks", "version_floors.script", floors["script"]).as_posix(),
                        file=floors["file"])
    tokens = budget.get("max_context_tokens")
    if tokens is not None and (not isinstance(tokens, int) or isinstance(tokens, bool) or tokens <= 0):
        raise GuideError("[budget] max_context_tokens: a positive whole number")
    whole = lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0  # noqa: E731
    page_kb = budget.get("page_kb", 0)
    if "page_kb" in budget and not whole(page_kb):
        raise GuideError("[budget] page_kb: a positive whole number (KB above which a page is flagged)")
    growth = {}
    for key, default in (("growth_kb", 5), ("growth_percent", 25)):
        growth[key] = budget.get(key, default)
        if not whole(growth[key]):
            raise GuideError(f"[budget] {key}: a positive whole number (what a page gains in 90 days before it is flagged)")
    budgets = budget.get("pages", {})
    if not isinstance(budgets, dict) or not all(isinstance(k, str) and k and whole(v) for k, v in budgets.items()):
        raise GuideError('[budget.pages]: a table of "glob pattern" = KB (a positive whole number)')

    readonly = _globs(c, "readonly", ())
    if watch.changes_page and any(matches(watch.changes_page, p) for p in readonly):
        raise GuideError(f"[watch] changes_page = {watch.changes_page!r} is read-only ([content] readonly): the watch "
                         "could not write to it")
    return Guide(
        root=root, name=name, language=language, repository=repository, forge=forge, forge_url=forge_url,
        forge_token=forge_token, site=_text(g, "guide", "site"), description=_text(g, "guide", "description"),
        base_branch=_branch(_text(g, "guide", "base_branch") or "main"),
        include=_globs(c, "include", ("**/*.md", "**/*.mdx")), exclude=_globs(c, "exclude", ()), readonly=readonly,
        mirrors=dict(mirrors), modified_field=_text(c, "content", "modified_field") or None, watch=watch,
        brief=_rule(root, rules, "brief"), translation_policy=_rule(root, rules, "translation_policy"),
        **{k: _command(checks, k) for k in CHECK_COMMANDS}, version_floors=floors, max_context_tokens=tokens,
        page_kb=page_kb, page_budgets=tuple(budgets.items()), **growth, schema=schema,
        chapters=chapters_of(data.get("chapter", [])),
    )


def chapters_of(given) -> tuple[Chapter, ...]:
    """The [[chapter]] tables of a manifest, checked: each a name (unique, no comma: the command line lists chapters
    with commas) and paths; `explore = false` leaves it unticked when the web is explored."""
    if not isinstance(given, list) or not all(isinstance(c, dict) for c in given):
        raise GuideError("[[chapter]]: a list of tables, each with name and paths")
    out: list[Chapter] = []
    for n, c in enumerate(given, start=1):
        unknown = set(c) - {"name", "paths", "explore"}
        if unknown:
            raise GuideError(f"[[chapter]] {n}: unknown key {', '.join(sorted(unknown))} (known: explore, name, paths)")
        name = c.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ch in name for ch in ',"\n\r'):
            raise GuideError(f"[[chapter]] {n}: name is a text of 80 characters at most, without comma or quote")
        name = name.strip()
        if any(name == other.name for other in out):
            raise GuideError(f"[[chapter]] {n}: the name {name!r} is used twice")
        paths = c.get("paths")
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p.strip() for p in paths):
            raise GuideError(f"[[chapter]] {name}: paths is a list of folders (\"02-hardware/\"), globs or pages")
        explore = c.get("explore", True)
        if not isinstance(explore, bool):
            raise GuideError(f"[[chapter]] {name}: explore is true or false")
        out.append(Chapter(name, tuple(p.strip() for p in paths), explore))
    return tuple(out)


LEGACY_REPOSITORY = "DamienBecherini/ia-on-prem-vault"
# What tells the IA on-prem guide without its manifest: its watch brief and its audits script
LEGACY_MARKS = (".agents/skills/vault-watch/brief.md", "scripts/run-audits.mjs")


def no_manifest(root: Path) -> str:
    """What is said of a folder that has no manifest and is not the IA on-prem guide."""
    return (f"no {MANIFEST} in {root}: this folder is not set up as a guide yet. Run `vault-watch init` there: it "
            f"writes one from what it finds (the pages, their language, the mirrors, the repository), to read over; "
            f"then `vault-watch doctor`. The format: docs/connect-your-guide.md")


def is_legacy(root: Path) -> bool:
    """Whether a folder without manifest is the IA on-prem guide (the layout the agent was written for)."""
    return all((root / mark).is_file() for mark in LEGACY_MARKS)


def legacy(root: Path) -> Guide:
    """The IA on-prem guide as the agent assumed it before manifests: kept for that guide without one. Any other
    folder without a manifest is refused (GuideError, with what to do): it would be taken for that guide, its
    repository, its site and its scripts."""
    if not is_legacy(root):
        raise GuideError(no_manifest(root))
    rel = lambda p: (root / p) if (root / p).is_file() else None  # noqa: E731
    return Guide(
        root=root, name="Zero to Hero: On-Premise AI", language="fr", repository=LEGACY_REPOSITORY,
        description="running AI on-premise for SMEs (hardware sizing, inference engines, models, agents, security)",
        site="https://ia-on-prem.damien.becherini.fr/", base_branch="main",
        exclude=("en/**", "assets/**", "docs/**", "scripts/**", "_private/**", "_templates/**", "build/**",
                 "public/**", "node_modules/**", "README.md", "CLAUDE.md", "AGENTS.md"),
        mirrors={"en": "en/"}, modified_field="last_modified",
        watch=Watch(source="issues", label="veille", artifact="weekly-watch"),
        brief=rel(".agents/skills/vault-watch/brief.md"),
        translation_policy=rel(".agents/skills/vault-translate-content/references/translation-policy.md"),
        audits="node scripts/run-audits.mjs",
        claims_due="node scripts/audit-freshness.mjs --due-only --json={out}",
        sources="node scripts/audit-sources.mjs --concurrency=8 --timeout=15000 --json={out}",
        version_floors=Floors("scripts/audit-version-floors.mjs", ".agents/vault-maintenance/version-floors.json"),
        from_manifest=False,
    )


def matches(path: str, pattern: str) -> bool:
    """Whether a path relative to the guide (with /) matches a glob: `*` and `?` within one folder, `**` across
    folders (`en/**`, `**/draft-*.md`). PurePath.full_match does this from Python 3.13 only."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.fullmatch(out, path) is not None


def under(page: str, path: str) -> bool:
    """Whether `page` (relative to the guide, with /) is what `path` names: a folder (with or without its final /)
    and everything under it, a glob (`matches`), or the page itself."""
    folder = path.rstrip("/")
    return page == path or page.startswith(folder + "/") or (not path.endswith("/") and matches(page, path))


def working_folder(home: Path, guide: Guide) -> Path:
    """Where the agent keeps the runs of `guide` (checkpoints, worktrees, verifications, downloads): a folder of its
    own under `home`, named after its repository (or its folder). The settings (engine, models) stay in `home`,
    shared by every guide.

    The runs made before manifests are in `home` itself: they stay there for the guide they belong to, recorded in
    `home/guide.json`. That guide is the IA on-prem guide, the only one the agent knew: read without a manifest, or
    with one that names its repository (it has one since 0.3.0). Nothing is moved: the worktrees of those runs are
    registered in the guide's repository with their path."""
    import json

    marker, root = home / "guide.json", str(guide.root.resolve())
    if marker.is_file():
        if json.loads(marker.read_text(encoding="utf-8")).get("root") == root:
            return home
    elif (home / "checkpoints.sqlite").is_file() and (
            not guide.from_manifest or guide.repository == LEGACY_REPOSITORY):
        marker.write_text(json.dumps({"root": root}), encoding="utf-8")
        return home
    name = guide.repository.replace("/", "-") or guide.root.resolve().name
    return home / "guides" / re.sub(r"[^\w.-]+", "-", name).strip("-")


# -- helpers ------------------------------------------------------------------------------------------------
def _forge(g: dict) -> tuple[str, str, str]:
    """[guide] forge, forge_url, forge_token, checked: a Gitea forge needs its address; a token is a reference."""
    from .forge import FORGES

    forge = (_text(g, "guide", "forge") or "github").lower()
    if forge not in FORGES:
        raise GuideError(f"[guide] forge = {forge!r}: one of {', '.join(FORGES)}")
    url, token = _text(g, "guide", "forge_url").rstrip("/"), _text(g, "guide", "forge_token")
    if forge == "github":
        if url or token:
            raise GuideError("[guide] forge_url and forge_token are for a Gitea forge (forge = \"gitea\"): GitHub "
                             "goes through gh, authenticated by `gh auth login`")
        return forge, "", ""
    if not re.fullmatch(r"https?://[^\s/]+(/[^\s]*)?", url):
        raise GuideError('[guide] forge = "gitea" needs forge_url, the address of the server (http(s)://host[:port])')
    if token and not token.startswith(("env:", "sops:", "file:")):
        raise GuideError("[guide] forge_token: a reference to where the token is (env:NAME, sops:file#NAME or "
                         "file:path), never the token itself")
    return forge, url, token or "env:GITEA_TOKEN"


def _branch(name: str) -> str:
    """The guide's base branch, as git takes it: a name of letters, digits, « . _ / - », never read as an option."""
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._/-]*", name) or ".." in name or name.endswith((".", "/", ".lock")):
        raise GuideError(f"[guide] base_branch = {name!r}: not a branch name")
    return name


def _text(table: dict, name: str, key: str, required: bool = False) -> str:
    value = table.get(key, "")
    if not isinstance(value, str):
        raise GuideError(f"[{name}] {key}: a string")
    if required and not value.strip():
        raise GuideError(f"[{name}] {key} is required")
    return value.strip()


def _globs(table: dict, key: str, default: tuple) -> tuple[str, ...]:
    value = table.get(key, list(default))
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise GuideError(f"[content] {key}: a list of glob patterns")
    return tuple(value)


def _file(root: Path, table: str, key: str, value) -> Path:
    if not isinstance(value, str) or not value:
        raise GuideError(f"[{table}] {key}: a path in the guide")
    path = (root / value).resolve()
    if root.resolve() not in path.parents:
        raise GuideError(f"[{table}] {key} = {value!r}: must stay inside the guide")
    if not path.is_file():
        raise GuideError(f"[{table}] {key} = {value!r}: no such file in the guide")
    return PurePosixPath(value)


def _rule(root: Path, rules: dict, key: str) -> Path | None:
    return root / _file(root, "rules", key, rules[key]) if key in rules else None


def _command(checks: dict, key: str) -> str | None:
    value = checks.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise GuideError(f"[checks] {key}: a command line")
    if key != "audits" and "{out}" not in value:
        raise GuideError(f"[checks] {key}: the command must write its JSON to {{out}}")
    return value.strip()
