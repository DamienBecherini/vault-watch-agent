"""The chapters of a guide: the automatic rule, those the manifest declares, a model's proposal, the manifest
rewritten on a branch, and what the server and the command line show of them."""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vault_watch_agent import chapters, news, reading, vault, verify
from vault_watch_agent.graph import Deps
from vault_watch_agent.guide import Chapter, GuideError, load, under

MANIFEST = 'schema = 1\n[guide]\nname = "T"\n[content]\nlanguage = "fr"\n'
KB = 1024


def make(root: Path, pages: dict[str, int], manifest: str = MANIFEST) -> Path:
    """A guide whose pages weigh what is asked (bytes)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "vault-watch.toml").write_text(manifest, encoding="utf-8", newline="\n")
    for rel, size in pages.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        head = f"# {Path(rel).stem}\n\n## Part one\n\n"
        (root / rel).write_text(head + "x" * max(0, size - len(head)), encoding="utf-8", newline="\n")
    return root


def names(root: Path) -> dict[str, list[str]]:
    return {c.name: [p.relative_to(root).as_posix() for p in c.pages] for c in chapters.of(root)}


def git(root: Path) -> None:
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "config", "user.name", "t"], ["git", "config", "user.email", "t@t"],
                ["git", "add", "."], ["git", "commit", "-qm", "init"]):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)


def test_the_automatic_rule_splits_what_is_heavy_and_gathers_what_is_light(tmp_path):
    root = make(tmp_path / "g", {
        "index.md": 4 * KB, "about/team.md": 6 * KB,                                      # light: gathered
        "01-basics/a.md": 40 * KB, "01-basics/b.md": 30 * KB,                             # one folder, one chapter
        "02-agents/index.md": 3 * KB, "02-agents/keepers/a.md": 90 * KB, "02-agents/keepers/b.md": 20 * KB,
        "02-agents/helpers/a.md": 70 * KB, "02-agents/shared/a.md": 5 * KB,             # heavy, with subfolders
        **{f"03-glossary/t{n:02}.md": 30 * KB for n in range(10)},                        # heavy and flat: slices
    })
    found = names(root)
    assert list(found) == ["01-basics", "02-agents/helpers", "02-agents (rest)", "02-agents/keepers",
                           "03-glossary 1/2", "03-glossary 2/2", "about + (root)"]
    assert found["about + (root)"] == ["about/team.md", "index.md"]
    assert found["02-agents (rest)"] == ["02-agents/index.md", "02-agents/shared/a.md"]  # the folder's own pages, the light subfolder
    assert [len(found[f"03-glossary {n}/2"]) for n in (1, 2)] == [5, 5]
    assert reading.chapters(root).keys() == found.keys()  # what the steps read by chapter
    # Light folders are gathered in bundles that stay light: twelve of 15 KB make three chapters, not one of 180 KB
    many = make(tmp_path / "many", {f"f{n:02}/a.md": 15 * KB for n in range(12)})
    assert [len(pages) for pages in names(many).values()] == [5, 5, 2] and "f00 + 4 others" in names(many)
    # One light folder alone keeps its name; a guide of one folder is one chapter
    assert list(names(make(tmp_path / "one", {"notes/a.md": KB, "big/a.md": 30 * KB}))) == ["big", "notes"]


def test_the_manifest_declares_chapters_and_the_rule_takes_the_rest(tmp_path):
    pages = {"index.md": KB, "hard/gpu.md": 30 * KB, "hard/cpu.md": 30 * KB, "soft/engines.md": 30 * KB,
             "soft/models.md": 30 * KB, "glossary/a.md": 30 * KB, "glossary/b.md": 30 * KB}
    root = make(tmp_path / "g", pages, MANIFEST + '''
[[chapter]]
name = "Models"
paths = ["soft/models.md", "hard/gpu.md"]

[[chapter]]
name = "Machines"
paths = ["hard/"]

[[chapter]]
name = "Words"
paths = ["glossary/**"]
explore = false

[[chapter]]
name = "Nothing"
paths = ["nowhere/", "hard/gpu.md"]
''')
    guide = load(root)
    assert guide.chapters[2] == Chapter("Words", ("glossary/**",), False) and guide.summary()["chapters"][0]["name"] == "Models"
    found = names(root)
    # A page goes to the first chapter that takes it; the pages no chapter takes follow the automatic rule
    assert found == {"Words": ["glossary/a.md", "glossary/b.md"], "Machines": ["hard/cpu.md"],
                     "Models": ["hard/gpu.md", "soft/models.md"], "(root)": ["index.md"], "soft": ["soft/engines.md"]}
    assert chapters.default_explored(root) == ["Machines", "Models", "(root)", "soft"]
    view = chapters.view(root)
    by = {c["name"]: c for c in view["chapters"]}
    assert view["source"] == "manifest" and by["Words"] == {
        "name": "Words", "pages": 2, "kb": 60.0, "first": "glossary/a.md", "last": "glossary/b.md", "explore": False,
        "declared": True, "paths": ["glossary/**"], "cover": ["glossary/**"], "readonly": False}
    assert by["soft"]["cover"] == ["soft/engines.md"] and by["(root)"]["cover"] == ["index.md"] and not by["soft"]["declared"]
    assert len(view["notes"]) == 1 and "« Nothing » takes no page (nowhere/, hard/gpu.md)" in view["notes"][0]
    # As another split would give them, nothing written
    other = chapters.view(root, [Chapter("All", ("**",))])
    assert [(c["name"], c["pages"]) for c in other["chapters"]] == [("All", 7)] and chapters.view(root)["source"] == "manifest"
    assert chapters.view(make(tmp_path / "plain", pages))["source"] == "automatic"
    assert under("a/b/c.md", "a/") and under("a/b/c.md", "a/b") and under("a/b.md", "a/*.md") and not under("ab/c.md", "a")

    for wrong, said in (('[[chapter]]\nname = "A"\n', "paths is a list"), ('[[chapter]]\nname = "A, B"\npaths = ["a/"]\n', "without comma"),
                        ('[[chapter]]\nname = "A"\npaths = ["a/"]\n[[chapter]]\nname = "A"\npaths = ["b/"]\n', "used twice"),
                        ('[[chapter]]\nname = "A"\npaths = ["a/"]\nexplore = "no"\n', "explore is true or false"),
                        ('[[chapter]]\nname = "A"\npaths = ["a/"]\npages = 3\n', "unknown key pages"),
                        ('[chapter]\nname = "A"\n', "a list of tables")):
        (root / "vault-watch.toml").write_text(MANIFEST + wrong, encoding="utf-8")
        with pytest.raises(GuideError, match=said):
            load(root)


def test_the_manifest_is_rewritten_with_the_chapters_and_nothing_else_moves(tmp_path):
    text = ('# My guide\nschema = 1\n[guide]\nname = "T"   # its name\n\n[[chapter]]\nname = "Old"\npaths = [\n  "a/",\n]\n\n'
            '[content]\nlanguage = "fr"\n')
    declared = [Chapter("Les « machines »", ("hard/", "soft/*.md")), Chapter("Words", ("glossary/",), False)]
    new = chapters.rewrite(text, declared)
    assert new.startswith('# My guide\nschema = 1\n[guide]\nname = "T"   # its name\n\n[content]\nlanguage = "fr"\n\n# Chapters:')
    assert new.endswith('[[chapter]]\nname = "Les « machines »"\npaths = ["hard/", "soft/*.md"]\n\n[[chapter]]\nname = "Words"\n'
                        'paths = ["glossary/"]\nexplore = false\n')
    assert "Old" not in new and chapters.rewrite(new, declared) == new  # written twice: the same file
    assert chapters.rewrite(new, []) == '# My guide\nschema = 1\n[guide]\nname = "T"   # its name\n\n[content]\nlanguage = "fr"\n'
    # In the folder: the file's own line endings are kept, and nothing is written when it already says so
    root = make(tmp_path / "g", {"hard/a.md": KB, "glossary/a.md": KB}, text.replace("\n", "\r\n"))
    assert chapters.write(root, declared) and not chapters.write(root, declared)
    raw = vault.read(root / "vault-watch.toml")
    assert "\r\n" in raw and "\n" not in raw.replace("\r\n", "") and [c.name for c in load(root).chapters] == ["Les « machines »", "Words"]
    (tmp_path / "bare").mkdir()
    with pytest.raises(GuideError, match="no vault-watch.toml"):
        chapters.write(tmp_path / "bare", declared)


class Splitter:
    """A model that answers a split, and keeps what it was asked."""

    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
        self.asked.append({"system": system, "schema": schema, "effort": effort, "node": node, "context": context, "web": web})
        return self.answer, {"node": node, "model": "fake", "cost_usd": 0.12}


ANSWER = chapters.Split(chapters=[
    chapters.Proposed(name='Machines, "hard"', paths=["hard/", " soft/engines.md ", "nowhere/"], explore=True, why="The hardware."),
    chapters.Proposed(name="Words", paths=["glossary/**"], explore=False, why="Definitions follow the other chapters."),
    chapters.Proposed(name="Words", paths=["index.md"], explore=False, why="The home page."),
    chapters.Proposed(name="Ghost", paths=["nowhere/"], explore=True, why="Names no page."),
])


def test_a_model_proposes_a_split_from_the_outline_of_the_guide(tmp_path):
    root = make(tmp_path / "g", {"index.md": KB, "hard/gpu.md": 30 * KB, "soft/engines.md": 30 * KB, "glossary/a.md": 2 * KB})
    (root / "hard/gpu.md").write_text('---\ntitle: "Les cartes"\n---\n\n# Ignored\n\n## Mémoire\n\n```\n## not a heading\n```\n\n## Prix\n',
                                      encoding="utf-8")
    outline = chapters.outline(root)
    assert "- hard/gpu.md (0.1 KB): Les cartes\n    ## Mémoire\n    ## Prix\n" in outline and "not a heading" not in outline
    assert "- glossary/a.md (2.0 KB): a\n    ## Part one" in outline
    llm = Splitter(ANSWER)
    declared, why, usage = chapters.propose(root, llm)
    # Checked as a manifest would be: a path that names no page is dropped, a chapter without a path too, a name is
    # cleaned and made unique
    assert declared == [Chapter("Machines   hard", ("hard/", "soft/engines.md")), Chapter("Words", ("glossary/**",), False),
                        Chapter("Words (2)", ("index.md",), False)]
    assert why["Words"] == "Definitions follow the other chapters." and usage["cost_usd"] == 0.12
    asked = llm.asked[0]
    assert asked["node"] == "chapters" and asked["effort"] == "medium" and not asked["web"] and asked["schema"] is chapters.Split
    assert asked["context"] == f"<outline>\n{outline}\n</outline>" and "150 KB" in asked["system"] and "French" in asked["system"]
    assert chapters.rewrite(MANIFEST, declared)  # what it proposes can be written
    assert verify.chapters_usd(root, "claude-opus-5-5") > 0


def test_the_exploration_leaves_out_what_the_manifest_says_not_to_explore(tmp_path):
    root = make(tmp_path / "g", {"hard/gpu.md": 30 * KB, "soft/engines.md": 30 * KB, "glossary/a.md": 30 * KB},
                MANIFEST + '[[chapter]]\nname = "Words"\npaths = ["glossary/"]\nexplore = false\n')

    class Explorer:
        def __init__(self):
            self.seen = []

        def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
            self.seen.append(node)
            return news.Leads(findings=[]), {"node": node, "model": "fake"}

    llm = Explorer()
    result = verify.run_explore(root, tmp_path / "work", {}, llm)  # nothing chosen: the guide's defaults
    assert llm.seen == ["verify explore hard", "verify explore soft"] and result["chapters"] == ["hard", "soft"]
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "options.json").write_text('{"chapters": ["Words"]}', encoding="utf-8")
    llm = Explorer()
    assert verify.run_explore(root, tmp_path / "work", {}, llm)["chapters"] == ["Words"]  # asked for: explored


def test_the_server_shows_the_chapters_and_declares_them_on_a_branch(tmp_path):
    from vault_watch_agent import config
    from vault_watch_agent.web import Settings, create_app

    root = make(tmp_path / "g", {"index.md": KB, "hard/gpu.md": 30 * KB, "soft/engines.md": 30 * KB, "glossary/a.md": 30 * KB})
    git(root)
    home = tmp_path / "home"
    config.save(home, {"engine": "api"})
    llm = Splitter(ANSWER)
    deps = Deps(vault=root, home=home, llm=llm, today="2026-11-20")
    c = TestClient(create_app(Settings(vault=root, home=home, config_home=home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    act = {"X-Vault-Watch": "1"}
    now = c.get("/api/chapters").json()
    assert now["source"] == "automatic" and [x["name"] for x in now["chapters"]] == ["glossary", "hard", "(root)", "soft"]
    assert now["toml"] == "" and now["pending"] == {} and not now["has_repo"] and now["from_manifest"] and now["usd"] > 0
    assert (now["step"]["step"], now["step"]["effort"], now["step"]["billing"]) == ("chapters", "medium", "token")
    assert c.get("/api/chapters", params={"steps": '{"chapters": {"effort": "low"}}'}).json()["step"]["effort"] == "low"
    explore = next(o for o in c.get("/api/verifications/options").json() if o["id"] == "explore")
    assert explore["chapters"][0] == {"id": "glossary", "pages": 1, "kb": 30.0, "explore": True}

    # A model's proposal: reviewed on the page, nothing written
    proposed = c.post("/api/chapters/propose", json={"steps": {"chapters": {"effort": "low"}}}, headers=act).json()
    assert [(x["name"], x["declared"], x["explore"]) for x in proposed["chapters"]] == [
        ("Words", True, False), ("Machines   hard", True, True), ("Words (2)", True, False)]
    assert proposed["cost"] == 0.12 and proposed["why"]["Words (2)"] == "The home page." and "[[chapter]]" in proposed["toml"]
    assert vault.read(root / "vault-watch.toml") == MANIFEST

    rows = [{"name": "Machines", "paths": ["hard/", "soft/"], "explore": True}, {"name": "Words", "paths": ["glossary/"], "explore": False}]
    seen = c.post("/api/chapters/preview", json={"chapters": rows}, headers=act).json()
    assert [(x["name"], x["pages"], x["declared"]) for x in seen["chapters"]] == [("Words", 1, True), ("Machines", 2, True), ("(root)", 1, False)]
    assert seen["toml"].endswith('[[chapter]]\nname = "Words"\npaths = ["glossary/"]\nexplore = false\n')
    assert c.post("/api/chapters/preview", json={"chapters": [{"name": "A, B", "paths": ["a/"]}]}, headers=act).status_code == 400

    # Saved: a branch of the guide holds the manifest, its folder is not touched (a guide without a repository)
    done = c.post("/api/chapters", json={"chapters": rows}, headers=act).json()
    assert done["branch"].startswith("chore/chapters-") and (done["pr_url"], done["base"]) == ("", "main")
    show = lambda ref: subprocess.run(["git", "show", ref], cwd=root, check=True, capture_output=True, text=True, encoding="utf-8").stdout  # noqa: E731
    assert show(f"{done['branch']}:vault-watch.toml") == MANIFEST + "\n" + seen["toml"]
    assert vault.read(root / "vault-watch.toml") == MANIFEST and not (home / "worktrees" / done["branch"].replace("/", "-")).exists()
    # Merged by its editor: the page shows the split; saving the same again changes nothing and leaves no branch
    subprocess.run(["git", "merge", "-q", "--ff-only", done["branch"]], cwd=root, check=True, capture_output=True)
    now = c.get("/api/chapters").json()
    assert now["source"] == "manifest" and [x["name"] for x in now["chapters"]] == ["Words", "Machines", "(root)"]
    explore = next(o for o in c.get("/api/verifications/options").json() if o["id"] == "explore")
    assert [(x["id"], x["explore"]) for x in explore["chapters"]] == [("Words", False), ("Machines", True), ("(root)", True)]
    again = c.post("/api/chapters", json={"chapters": rows}, headers=act)
    assert again.status_code == 409 and "nothing to change" in again.json()["detail"]
    branches = subprocess.run(["git", "branch", "--format=%(refname:short)"], cwd=root, check=True, capture_output=True, text=True).stdout.split()
    assert sorted(branches) == [done["branch"], "main"]
    # Back to the automatic rule: another branch, the tables gone
    back = c.post("/api/chapters", json={"chapters": []}, headers=act).json()
    assert back["branch"] == done["branch"] + "-2" and show(f"{back['branch']}:vault-watch.toml") == MANIFEST


def test_a_guide_with_a_repository_gets_a_pull_request_for_its_chapters(tmp_path):
    root = make(tmp_path / "g", {"hard/gpu.md": 30 * KB, "glossary/a.md": 30 * KB},
                MANIFEST.replace('name = "T"', 'name = "T"\nrepository = "me/guide"'))
    git(root)
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True, capture_output=True)
    for cmd in (["git", "remote", "add", "origin", str(origin)], ["git", "push", "-q", "-u", "origin", "main"]):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)
    opened = {}

    def open_pull_request(repo, *, base, head, title, body, cwd):
        opened.update(repo=repo, base=base, head=head, title=title, body=body)
        return "https://forge.example/me/guide/pull/7"

    declared = [Chapter("Words", ("glossary/",), False)]
    done = chapters.publish(load(root), tmp_path / "home", declared, today="2026-11-20", open_pull_request=open_pull_request)
    assert done == {"branch": "chore/chapters-2026-11-20", "pr_url": "https://forge.example/me/guide/pull/7"}
    assert opened["title"] == "chore(watch): chapters of the guide" and (opened["repo"], opened["base"], opened["head"]) == (
        "me/guide", "main", "chore/chapters-2026-11-20")
    assert "| Words | 1 | 30 KB | no | declared |" in opened["body"] and "| hard | 1 | 30 KB | yes | automatic rule |" in opened["body"]
    pushed = subprocess.run(["git", "log", "-1", "--format=%s", "chore/chapters-2026-11-20"], cwd=origin, check=True,
                            capture_output=True, text=True).stdout.strip()
    assert pushed == "chore(watch): chapters of the guide (1 declared)"


def test_the_command_line_lists_the_chapters(tmp_path, monkeypatch, capsys):
    from vault_watch_agent import cli

    root = make(tmp_path / "g", {"hard/gpu.md": 30 * KB, "glossary/a.md": 30 * KB},
                MANIFEST + '[[chapter]]\nname = "Words"\npaths = ["glossary/", "nowhere/"]\nexplore = false\n')
    monkeypatch.setenv("VAULT_WATCH_HOME", str(tmp_path / "home"))
    cli.main(["--guide", str(root), "chapters"])
    out = capsys.readouterr().out
    assert "Words" in out and "manifest" in out and "automatic" in out and "no " in out
    from vault_watch_agent import onboard

    said = [str(line) for line in onboard.diagnose(root, tmp_path / "home", gh_check=False)]
    assert any("chapters: 2 (1 declared in the manifest, the others by the automatic rule)" in line and "✓" in line for line in said)
    cli.main(["--guide", str(root), "chapters", "--automatic"])
    assert "declares no chapter any more" in capsys.readouterr().out and vault.read(root / "vault-watch.toml") == MANIFEST
