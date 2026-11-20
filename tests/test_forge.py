"""The forges (forge.py): the manifest's choice, and Gitea against a fake server (no network, no token)."""

import io
import json
import zipfile

import httpx
import pytest

from vault_watch_agent import forge
from vault_watch_agent.forge import ForgeError, GitHub, Gitea, for_guide
from vault_watch_agent.guide import GuideError, parse

URL = "http://gitea.test:3100"


def minimal(**guide) -> dict:
    return {"guide": {"name": "G", **guide}, "content": {"language": "en"}}


class FakeGitea:
    """Records each request and answers like Gitea 1.25 for one repository, owner/guide."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.issues = [
            {"number": 3, "title": "Veille 2", "state": "open", "created_at": "2026-11-15T08:00:00Z",
             "labels": [{"name": "veille"}], "body": "run https://g/owner/guide/actions/runs/41"},
            {"number": 1, "title": "Veille 1", "state": "closed", "created_at": "2026-11-01T08:00:00Z",
             "labels": [{"name": "veille"}], "body": None},
        ]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        self.calls.append((request.method, path, body))
        if request.headers.get("Authorization") != "token secret-value":
            return httpx.Response(401, json={"message": "token is required"})
        repo = "/api/v1/repos/owner/guide"
        if path == repo:
            return httpx.Response(200, json={"full_name": "owner/guide"})
        if path == f"{repo}/issues" and request.method == "GET":
            assert request.url.params["labels"] == "veille" and request.url.params["type"] == "issues"
            return httpx.Response(200, json=list(reversed(self.issues)))  # oldest first: the forge sorts them
        if path == f"{repo}/issues/3" and request.method == "GET":
            return httpx.Response(200, json=self.issues[0])
        if path == f"{repo}/issues/3/comments":
            return httpx.Response(201, json={"id": 9})
        if path == f"{repo}/issues/3" and request.method == "PATCH":
            return httpx.Response(201, json={**self.issues[0], "state": "closed"})
        if path == f"{repo}/pulls" and request.method == "POST":
            return httpx.Response(201, json={"number": 7, "html_url": f"{URL}/owner/guide/pulls/7"})
        if path == f"{repo}/pulls/7":
            return httpx.Response(200, json={"state": "closed", "merged": True})
        if path == f"{repo}/pulls/8":
            return httpx.Response(200, json={"state": "open", "merged": False})
        if path == f"{repo}/actions/runs/41/artifacts":
            return httpx.Response(200, json={"artifacts": [{"id": 5, "name": "other"}, {"id": 6, "name": "weekly-watch"}]})
        if path == f"{repo}/actions/artifacts/6/zip":
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("watch.json", '{"schema": 1}')
            return httpx.Response(200, content=buf.getvalue())
        return httpx.Response(404, json={"message": "not found"})


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("TEST_GITEA_TOKEN", "secret-value")
    fake = FakeGitea()
    return fake, Gitea(URL + "/", "env:TEST_GITEA_TOKEN", client=httpx.Client(transport=httpx.MockTransport(fake)))


def test_the_manifest_chooses_the_forge(tmp_path):
    g = parse(minimal(repository="owner/guide"), tmp_path)
    assert (g.forge, g.forge_url, g.forge_token) == ("github", "", "")
    assert isinstance(for_guide(g), GitHub)
    g = parse(minimal(repository="owner/guide", forge="gitea", forge_url=URL + "/"), tmp_path)
    assert (g.forge, g.forge_url, g.forge_token) == ("gitea", URL, "env:GITEA_TOKEN")
    chosen = for_guide(g)
    assert isinstance(chosen, Gitea) and chosen.url == URL and chosen.token_ref == "env:GITEA_TOKEN"
    g = parse(minimal(forge="gitea", forge_url=URL, forge_token="sops:secrets/gitea.env#TOKEN"), tmp_path)
    assert g.forge_token == "sops:secrets/gitea.env#TOKEN"
    assert g.summary()["forge"] == "gitea" and g.summary()["forge_url"] == URL
    assert "forge_token" not in g.summary()  # the reference stays out of the interface


@pytest.mark.parametrize("values, says", [
    ({"forge": "gitlab"}, "one of github, gitea"),
    ({"forge": "gitea"}, "needs forge_url"),
    ({"forge": "gitea", "forge_url": "gitea.local"}, "needs forge_url"),
    ({"forge": "gitea", "forge_url": URL, "forge_token": "abcdef123"}, "never the token itself"),
    ({"forge_url": URL}, "are for a Gitea forge"),
])
def test_a_wrong_forge_is_refused(tmp_path, values, says):
    with pytest.raises(GuideError, match=says):
        parse(minimal(**values), tmp_path)


def test_gitea_reads_the_repository_and_its_issues(server):
    fake, gitea = server
    assert gitea.can_read("owner/guide") == (True, f"owner/guide on {URL}")
    ok, detail = gitea.can_read("owner/missing")
    assert not ok and "404" in detail
    found = gitea.issues("owner/guide", "veille")
    assert [i["number"] for i in found] == [3, 1]  # newest first
    assert found[0] == {"number": 3, "title": "Veille 2", "state": "open", "date": "2026-11-15", "labels": ["veille"],
                        "body": "run https://g/owner/guide/actions/runs/41"}
    assert found[1]["body"] == ""
    assert gitea.issue_body("owner/guide", 3).endswith("/actions/runs/41")


def test_gitea_closes_an_issue_with_a_comment(server):
    fake, gitea = server
    gitea.close_issue("owner/guide", 3, "Handled by vault-watch")
    assert fake.calls[-2:] == [("POST", "/api/v1/repos/owner/guide/issues/3/comments", {"body": "Handled by vault-watch"}),
                               ("PATCH", "/api/v1/repos/owner/guide/issues/3", {"state": "closed"})]


def test_gitea_opens_a_pull_request_and_reads_its_state(server, tmp_path):
    fake, gitea = server
    url = gitea.open_pull_request("owner/guide", base="main", head="chore/watch-3", title="Watch 3", body="Body",
                                  cwd=tmp_path)
    assert url == f"{URL}/owner/guide/pulls/7"
    assert fake.calls[-1] == ("POST", "/api/v1/repos/owner/guide/pulls",
                              {"base": "main", "head": "chore/watch-3", "title": "Watch 3", "body": "Body"})
    assert gitea.pull_request_state(url) == "merged"
    assert gitea.pull_request_state(f"{URL}/owner/guide/pulls/8") == "open"
    with pytest.raises(ForgeError, match="not a pull request address"):
        gitea.pull_request_state(f"{URL}/owner/guide/issues/3")


def test_github_gets_a_long_description_in_a_file(tmp_path, monkeypatch):
    """As an argument, a description over 32 767 characters is refused by Windows before gh runs (20/11/2026: the
    193 trims of a compaction run, 117 000 characters, and nothing happened on the publish screen)."""
    seen = {}

    def run(command, cwd=None):
        seen.update(command=command, cwd=cwd, body=open(command[command.index("--body-file") + 1], encoding="utf-8").read())
        return "https://github.com/owner/guide/pull/12\n"

    monkeypatch.setattr(forge.inputs, "run", run)
    body = "| C1 | Minor | `a.md` | « é » |\n" * 4000  # 120 000 characters
    url = GitHub().open_pull_request("owner/guide", base="main", head="compact/x", title="T", body=body, cwd=tmp_path)
    assert url == "https://github.com/owner/guide/pull/12" and seen["body"] == body and seen["cwd"] == tmp_path
    assert "--body" not in seen["command"] and max(len(a) for a in seen["command"]) < 300  # nothing long on the command line
    import os

    assert not os.path.exists(seen["command"][seen["command"].index("--body-file") + 1])  # the file is gone


def test_gitea_downloads_the_artifact_of_a_run(server, tmp_path):
    fake, gitea = server
    gitea.download_artifact("owner/guide", "41", "weekly-watch", tmp_path / "run-41")
    assert (tmp_path / "run-41" / "watch.json").read_text() == '{"schema": 1}'
    with pytest.raises(ForgeError, match="no artifact 'missing'"):
        gitea.download_artifact("owner/guide", "41", "missing", tmp_path / "x")


def test_a_wrong_or_missing_token_says_where_to_look(monkeypatch):
    monkeypatch.delenv("TEST_GITEA_TOKEN", raising=False)
    gitea = Gitea(URL, "env:TEST_GITEA_TOKEN", client=httpx.Client(transport=httpx.MockTransport(FakeGitea())))
    with pytest.raises(ForgeError, match=r"401 token is required \(check the token: \[guide\] forge_token\)"):
        gitea.issues("owner/guide", "veille")


def test_an_unreachable_server_is_a_forge_error(monkeypatch):
    def down(request):
        raise httpx.ConnectError("refused")

    monkeypatch.setenv("TEST_GITEA_TOKEN", "secret-value")
    gitea = Gitea(URL, "env:TEST_GITEA_TOKEN", client=httpx.Client(transport=httpx.MockTransport(down)))
    ok, detail = gitea.can_read("owner/guide")
    assert not ok and "cannot be reached" in detail and "secret-value" not in detail


def test_the_command_line_uses_the_guide_s_forge(tmp_path, monkeypatch):
    from vault_watch_agent import cli

    (tmp_path / "vault-watch.toml").write_text(
        f'schema = 1\n[guide]\nname = "G"\nrepository = "owner/guide"\nforge = "gitea"\nforge_url = "{URL}"\n'
        '[content]\nlanguage = "en"\n', encoding="utf-8")
    monkeypatch.setattr(cli, "CONFIG_HOME", tmp_path / "home")
    before = forge.get()
    try:
        cli.use_guide(str(tmp_path))
        assert isinstance(forge.get(), Gitea) and forge.get().url == URL
    finally:
        forge.use(before)
