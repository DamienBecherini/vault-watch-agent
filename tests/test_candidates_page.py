"""The page « Candidates » (ROADMAP D3.2): the registry changed in a draft of the agent, never in the guide's folder,
then published by a pull request of the guide, which names it in its manifest when it does not yet."""

import subprocess

import pytest
from fastapi.testclient import TestClient

from vault_watch_agent import candidates, forge, vault
from vault_watch_agent.graph import Deps
from vault_watch_agent.web import Settings, create_app

ACT = {"X-Vault-Watch": "1"}


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8").stdout


class Forge:
    name = "GitHub"

    def __init__(self):
        self.opened = []

    def open_pull_request(self, repo, *, base, head, title, body, cwd):
        self.opened.append({"repo": repo, "base": base, "head": head, "title": title, "body": body})
        return f"https://forge.example/me/guide/pull/{len(self.opened)}"


@pytest.fixture
def page(sample_guide, tmp_path, monkeypatch):
    """(client, guide, forge, PR states): the sample guide with a repository, its origin a bare repository."""
    root, _ = sample_guide
    manifest = root / "vault-watch.toml"
    vault.write(manifest, vault.read(manifest).replace("[guide]\n", '[guide]\nrepository = "me/guide"\n', 1))
    git("commit", "-qam", "a repository", cwd=root)
    origin = tmp_path / "origin.git"
    git("init", "-q", "--bare", str(origin), cwd=tmp_path)
    git("remote", "add", "origin", str(origin), cwd=root)
    git("push", "-q", "-u", "origin", "main", cwd=root)
    fake = Forge()
    monkeypatch.setattr(forge, "get", lambda: fake)
    states: dict[str, str] = {}
    home = tmp_path / "home"
    deps = Deps(vault=root, home=home, llm=object(), today="2026-11-25")  # no model: a run started here stops at once
    c = TestClient(create_app(Settings(vault=root, home=home, config_home=home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [],
                                       pr_state=lambda url: states.get(url, "open"))))
    return c, root, fake, states


def test_the_registry_is_changed_in_a_draft_and_published_by_a_pull_request(page):
    c, root, fake, states = page
    manifest = vault.read(root / "vault-watch.toml")
    now = c.get("/api/candidates").json()
    assert (now["declared"], now["path"], now["draft"], now["candidates"], now["pending"]) == ("", "candidates.json", False, [], {})
    assert now["has_repo"] and now["needs"] == candidates.NEEDS and now["states"][0] == "lead"
    assert now["kinds"] == ["model", "tool", "hardware", "other"]  # the sample guide declares none

    # Added by hand; the same address under another name only adds nothing (one candidate)
    added = c.post("/api/candidates", json={"name": "Reflection Beam 501B", "url": "https://hf.co/reflection/beam",
                                            "kind": "model", "note": "seen on a forum"}, headers=ACT).json()
    assert added["new"] and added["id"] == "reflection-beam-501b" and added["draft"]
    beam = added["candidates"][0]
    assert beam["history"][0]["note"] == "seen: hand: seen on a forum"
    again = c.post("/api/candidates", json={"name": "Beam", "url": "https://www.hf.co/reflection/beam/"}, headers=ACT).json()
    assert not again["new"] and len(again["candidates"]) == 1
    refused = c.post("/api/candidates/reflection-beam-501b", json={"state": "dismissed"}, headers=ACT)
    assert refused.status_code == 400 and "needs a reason" in refused.json()["detail"]
    moved = c.post("/api/candidates/reflection-beam-501b", json={"state": "watching", "reason": "weights later",
                                                                 "recheck": "2999-01-01"}, headers=ACT).json()
    assert moved["changes"] == [{"what": "new", "name": "Reflection Beam 501B", "kind": "model", "state": "watching",
                                 "reason": "weights later", "recheck": "2999-01-01"}] and moved["unpublished"]
    assert vault.read(root / "vault-watch.toml") == manifest and not (root / "candidates.json").exists()  # the folder untouched

    # Published where the editor said: a branch with the registry and the manifest's key, a pull request
    bad = c.post("/api/candidates-draft/publish", json={"path": "../out.json"}, headers=ACT)
    assert bad.status_code == 400
    done = c.post("/api/candidates-draft/publish", json={"path": "watch/candidates.json"}, headers=ACT).json()
    branch = done["branch"]
    assert branch.startswith("chore/candidates-") and done["pr_url"] == "https://forge.example/me/guide/pull/1"
    assert 'candidates = "watch/candidates.json"' in git("show", f"{branch}:vault-watch.toml", cwd=root)
    on_branch = candidates.Registry.parse(git("show", f"{branch}:watch/candidates.json", cwd=root), root / "x.json")
    assert [c_["id"] for c_ in on_branch.candidates] == ["reflection-beam-501b"]
    pr = fake.opened[0]
    assert (pr["repo"], pr["base"], pr["head"], pr["title"]) == ("me/guide", "main", branch, candidates.TITLE)
    assert "**Reflection Beam 501B** (model) added, watching: weights later" in pr["body"] and candidates.NEEDS in pr["body"]
    assert done["pending"]["pr_url"] == done["pr_url"] and not done["unpublished"]
    assert vault.read(root / "vault-watch.toml") == manifest  # still untouched

    # One more change while it is open: a commit more on its branch, no second pull request
    c.post("/api/candidates", json={"name": "Memos AI", "kind": "tool"}, headers=ACT)
    assert c.get("/api/candidates").json()["unpublished"]
    more = c.post("/api/candidates-draft/publish", json={}, headers=ACT).json()
    assert more["branch"] == branch and more["pr_url"] == done["pr_url"] and len(fake.opened) == 1
    assert len(git("log", "--format=%s", f"main..{branch}", cwd=root).split("\n")) == 3  # two commits and a blank
    nothing = c.post("/api/candidates-draft/publish", json={}, headers=ACT)
    assert nothing.status_code == 409 and "nothing to publish" in nothing.json()["detail"]

    # Merged: the folder follows main, the draft goes (it held nothing more), the registry is the guide's
    git("push", "-q", "origin", f"{branch}:main", cwd=root)
    states[done["pr_url"]] = "merged"
    after = c.get("/api/candidates").json()
    assert (after["pending"], after["draft"], after["changes"], after["declared"]) == ({}, False, [], "watch/candidates.json")
    assert [x["id"] for x in after["candidates"]] == ["memos-ai", "reflection-beam-501b"]


def test_a_draft_can_be_dropped_and_a_proposed_candidate_names_its_run(page):
    c, root, _, _ = page
    c.post("/api/candidates", json={"name": "Larkdb 3", "url": "https://example.org/larkdb-3"}, headers=ACT)
    assert c.post("/api/candidates-draft/discard", headers=ACT).json()["candidates"] == []
    c.post("/api/candidates", json={"name": "Larkdb 3", "url": "https://example.org/larkdb-3"}, headers=ACT)
    # An addition run started for it (the page « Propose an addition », from the candidate): proposed, its run named
    thread = c.post("/api/fix", json={"text": "Larkdb 3: https://example.org/larkdb-3", "mode": "add",
                                      "candidate": "larkdb-3"}, headers=ACT).json()["thread"]
    lark = c.get("/api/candidates").json()["candidates"][0]
    assert (lark["state"], lark["reason"]) == ("proposed", f"run {thread}")
