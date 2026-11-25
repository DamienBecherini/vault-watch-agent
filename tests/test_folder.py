"""The guide's folder against origin, and « Update my folder » (vault.folder_state, vault.update_folder, /api/folder)."""

from pathlib import Path

from fastapi.testclient import TestClient
from test_graph import setup, sh  # noqa: F401  (fixture: throwaway guide, fake model, watch file)

from vault_watch_agent import retouch, vault
from vault_watch_agent.web import Settings, create_app

HEADERS = {"X-Vault-Watch": "1"}


def with_origin(deps) -> Path:
    """The guide's folder gets an origin, and a clone of it that merges pull requests; returns the clone."""
    origin = deps.vault.parent / "origin.git"
    sh("git", "clone", "-q", "--bare", str(deps.vault), str(origin), cwd=deps.vault.parent)
    sh("git", "remote", "add", "origin", str(origin), cwd=deps.vault)
    sh("git", "fetch", "-q", "origin", cwd=deps.vault)
    other = deps.vault.parent / "other"
    sh("git", "clone", "-q", str(origin), str(other), cwd=deps.vault.parent)
    return other


def merge(other: Path, name: str, text: str, title: str) -> None:
    (other / name).write_text(text, encoding="utf-8")
    sh("git", "add", ".", cwd=other)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", title, cwd=other)
    sh("git", "push", "-q", "origin", "main", cwd=other)


def client(deps, tmp_path):
    return TestClient(create_app(Settings(vault=deps.vault, home=deps.home, journal=tmp_path / "usage.jsonl",
                                          make_deps=lambda thread, kind: deps, list_issues=lambda: [])))


def test_the_folder_says_the_pull_requests_it_lacks_and_moves_forward_keeping_what_is_not_committed(setup, tmp_path):  # noqa: F811
    deps, _, _ = setup
    other = with_origin(deps)
    c = client(deps, tmp_path)
    assert c.get("/api/folder").json()["behind"] == []

    merge(other, "merged.md", "merged\n", "feat(content): reviewed additions (#109)")
    (deps.vault / "notes.md").write_text("mine, not committed\n", encoding="utf-8")
    now = c.get("/api/folder", params={"fresh": True}).json()
    assert [(b["title"], b["pr"]) for b in now["behind"]] == [("feat(content): reviewed additions", 109)]
    assert now["branch"] == "main" and now["changes"] == ["notes.md"] and now["lent_to"] == ""
    assert now["path"] == str(deps.vault)

    done = c.post("/api/folder/update", headers=HEADERS).json()
    assert done["ok"] and done["files"] == 1 and done["kept"] == ["notes.md"] and done["from"] != done["to"]
    assert (deps.vault / "merged.md").is_file()
    assert (deps.vault / "notes.md").read_text(encoding="utf-8") == "mine, not committed\n"
    assert c.get("/api/folder").json()["behind"] == []  # asked again after an update, without waiting a minute


def test_a_change_in_the_way_moves_nothing_and_is_named(setup, tmp_path):  # noqa: F811
    deps, _, _ = setup
    other = with_origin(deps)
    merge(other, "03-stack/engines.md", "the merged text\n", "fix(content): engines (#110)")
    (deps.vault / "03-stack" / "engines.md").write_text("my own edit\n", encoding="utf-8")
    before = vault.folder_state(deps.vault)
    assert before["behind"][0]["pr"] == 110

    done = vault.update_folder(deps.vault)
    assert not done["ok"] and "03-stack/engines.md" in done["files"]
    assert (deps.vault / "03-stack" / "engines.md").read_text(encoding="utf-8") == "my own edit\n"  # untouched
    assert vault.folder_state(deps.vault, fetch=False)["behind"]  # still behind


def test_the_same_text_as_the_merge_does_not_stand_in_the_way(setup, tmp_path):  # noqa: F811
    deps, _, _ = setup
    other = with_origin(deps)
    merge(other, "03-stack/engines.md", "the merged text\n", "fix(content): engines (#111)")
    (deps.vault / "03-stack" / "engines.md").write_text("the merged text\n", encoding="utf-8")  # sent, then merged
    assert vault.update_folder(deps.vault)["ok"]
    assert vault.folder_state(deps.vault, fetch=False)["changes"] == []


def test_on_another_branch_only_main_moves_and_a_lent_folder_is_refused(setup, tmp_path):  # noqa: F811
    deps, _, _ = setup
    other = with_origin(deps)
    sh("git", "checkout", "-q", "-b", "trial", cwd=deps.vault)
    merge(other, "merged.md", "merged\n", "feat: x (#112)")
    c = client(deps, tmp_path)
    assert c.get("/api/folder", params={"fresh": True}).json()["branch"] == "trial"
    done = c.post("/api/folder/update", headers=HEADERS).json()
    assert done["ok"] and done["branch"] == "trial" and not (deps.vault / "merged.md").exists()  # still on trial
    assert c.get("/api/folder", params={"fresh": True}).json()["behind"] == []  # main has moved

    retouch._save(deps.home, {"add-1": {"lent": True}})
    refused = c.post("/api/folder/update", headers=HEADERS)
    assert refused.status_code == 409 and "add-1" in refused.json()["detail"]


def test_a_folder_without_origin_is_never_behind(setup):  # noqa: F811
    deps, _, _ = setup
    now = vault.folder_state(deps.vault)
    assert now["origin"] is False and now["behind"] == [] and now["branch"] == "main"
