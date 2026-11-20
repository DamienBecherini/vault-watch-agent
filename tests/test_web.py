"""The web interface drives the same graph: start a run, review, then decline to publish, all through the API."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from test_graph import setup  # noqa: F401  (fixture: throwaway vault, fake model, watch file)
from vault_watch_agent.web import Job, Settings, create_app

ACT = {"X-Vault-Watch": "1"}


@pytest.fixture
def client(setup, tmp_path):  # noqa: F811
    deps, watch, llm = setup
    app = create_app(Settings(vault=deps.vault, home=deps.home, journal=tmp_path / "usage.jsonl",
                              make_deps=lambda thread, kind: deps, list_issues=lambda: []))
    return TestClient(app), watch


def wait(client, thread):
    for _ in range(200):
        run = client.get(f"/api/runs/{thread}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.05)
    raise AssertionError("run still going")


def test_review_and_publish_from_the_api(client):
    c, watch = client
    assert c.get("/api/health").json()["state"] == "ready"
    assert c.post("/api/analyses", json={"watch_json": str(watch)}).status_code == 403  # no header, no action
    thread = c.post("/api/analyses", json={"watch_json": str(watch)}, headers=ACT).json()["thread"]

    run = wait(c, thread)
    assert run["status"] == "review"
    assert [x["id"] for x in run["corrections"]] == ["C1", "C2", "C3", "C4", "C5"]
    assert run["triage"] == {"correct": 1, "addition": 1, "drop": 1}
    assert {e["node"] for e in run["job"]["events"]} >= {"collect", "triage", "propose", "crosscheck", "report", "pause"}
    assert "Watch report" in c.get(f"/api/runs/{thread}/report").text
    assert c.post("/api/analyses", json={"watch_json": str(watch)}, headers=ACT).status_code == 409  # one run per watch

    c.post(f"/api/runs/{thread}/review", json={"accept": ["C3"]}, headers=ACT)  # a group member: C1, C3, C5 go together
    run = wait(c, thread)
    assert run["status"] == "publish" and run["applied"] == ["C1", "C3", "C5"]
    assert "vLLM 0.33" in c.get(f"/api/runs/{thread}/diff").text

    c.post(f"/api/runs/{thread}/publish", json={"go": False}, headers=ACT)
    assert wait(c, thread)["status"] == "not-published"
    assert [r["thread"] for r in c.get("/api/runs").json()] == [thread]


def test_idle_time_ignores_the_health_probe(client):
    c, _ = client
    c.get("/api/runs")
    app = c.app
    app.state.last_activity -= 7200
    c.get("/api/health")  # a supervisor polling the health endpoint is not someone using the page
    assert app.state.idle_seconds() > 7000
    c.get("/api/runs")
    assert app.state.idle_seconds() < 5


def test_health_follows_the_local_service_contract(client):
    c, _ = client
    d = c.get("/api/health").json()
    assert (d["state"], d["contract"], d["service"]) == ("ready", 2, "vault-watch")
    assert d["busy"] is False and d["activity"] == "" and d["remaining_work_s"] is None
    assert d["idle"] == {"timeout_s": 0, "remaining_s": None}


def test_idle_delay_runs_from_the_end_of_the_work(client):
    c, _ = client
    app = c.app
    job = app.state.jobs["t"] = Job("t", "run")
    app.state.last_activity -= 7200
    assert app.state.idle_seconds() == 0
    d = c.get("/api/health").json()
    assert d["busy"] and d["activity"] == "analysing"
    job.done = True
    assert app.state.idle_seconds() < 5


def test_foreign_host_is_refused(client):
    c, _ = client
    assert c.get("/api/runs", headers={"Host": "evil.example"}).status_code == 403


def test_check_of_the_guide_runs_what_its_checks_need(client):
    c, _ = client
    options = {o["id"]: o for o in c.get("/api/verifications/options").json()}
    assert options["audits"]["usd"] == 0 and options["coherence"]["usd"] > 0 and options["coherence"]["tokens"] > 0
    assert options["claims"]["needs"] == ["freshness"]
    vid = c.post("/api/verifications", json={"checks": ["coherence", "claims"]}, headers=ACT).json()["id"]
    for _ in range(200):
        v = c.get(f"/api/verifications/{vid}").json()
        if not v["running"] and v["done"]:
            break
        time.sleep(0.05)
    assert v["checks"] == ["freshness", "coherence", "claims"]  # claims needs the freshness script first
    assert v["current"] == "" and len(v["commit"]) >= 7  # nothing running any more; the commit of main it read
    assert v["results"]["coherence"]["findings"] == ["[Major] 03-stack/engines.md: floor differs from another page"]
    exact, invented = v["results"]["coherence"]["excerpts"][v["results"]["coherence"]["findings"][0]]
    assert exact["match"] == "exact" and exact["line"] == 6 and invented["match"] == "missing"
    assert len(v["results"]["freshness"]["claims"]) == 1
    assert [p["id"] for p in c.get("/api/verifications").json()] == [vid]
    assert c.post("/api/verifications", json={"checks": ["nope"]}, headers=ACT).status_code == 400
    finding = v["results"]["coherence"]["findings"][0]
    assert v["status"] == "to-handle" and v["counts"]["open"] == 1
    act = lambda status: c.post(f"/api/verifications/{vid}/leads", json={"findings": [finding], "status": status}, headers=ACT)
    assert act("dismissed").json() == {"open": 0, "fix": 0, "dismissed": 1}
    assert c.get(f"/api/verifications/{vid}").json()["status"] == "handled"
    assert act("open").json()["open"] == 1
    thread = c.post("/api/fix", json={"text": finding, "verification": vid}, headers=ACT).json()["thread"]
    assert c.get(f"/api/verifications/{vid}").json()["handled"][finding]["thread"] == thread  # linked to its fix run


def test_the_sources_page_counts_what_a_run_did_with_the_items(client):
    c, watch = client
    s = c.get("/api/sources").json()
    assert s["file"] == "" and s["feeds"] == []  # the test guide declares no feeds: the page says so
    thread = c.post("/api/analyses", json={"watch_json": str(watch)}, headers=ACT).json()["thread"]
    wait(c, thread)
    assert c.get("/api/sources").json()["runs"] == 1  # the run is read; a second call reads it from memory
    assert c.get("/api/sources").json()["runs"] == 1


def test_the_review_says_when_the_rest_of_a_free_run_would_be_billed(client, monkeypatch):
    c, watch = client
    monkeypatch.setenv("VAULT_WATCH_ENGINE", "api")  # the settings now name a billed engine
    thread = c.post("/api/analyses", json={"watch_json": str(watch)}, headers=ACT).json()["thread"]
    wait(c, thread)
    view = c.get(f"/api/runs/{thread}").json()
    assert view["pause"]["step"] == "review"
    assert view["billed_next"] is True  # the fake model costs nothing: as a subscription would


def test_a_check_a_stopped_server_left_unfinished_can_be_handled_and_deleted(client, setup):  # noqa: F811
    c, home = client[0], setup[0].home
    verifs = home / "verifications"
    verifs.mkdir(parents=True, exist_ok=True)
    (verifs / "verif-2026-11-17-194034").mkdir()
    (verifs / "verif-2026-11-17-194034.json").write_text(json.dumps({
        "id": "verif-2026-11-17-194034", "started": 1.0, "checks": ["sources", "coherence"], "asked": ["sources", "coherence"],
        "results": {"sources": {"ok": False, "summary": "1 not answering", "findings": ["a dead link"]}},
        "cost": 0.0, "done": False}), encoding="utf-8")
    v = c.get("/api/verifications/verif-2026-11-17-194034").json()
    assert v["interrupted"] and not v["running"] and v["missing"] == ["coherence"] and v["status"] == "to-handle"
    r = c.post("/api/verifications/verif-2026-11-17-194034/leads", json={"findings": ["a dead link"], "status": "dismissed"},
               headers=ACT)
    assert r.status_code == 200 and r.json() == {"open": 0, "fix": 0, "dismissed": 1}  # was a 409 « still running »
    assert c.post("/api/verifications/verif-2026-11-17-194034/delete", json={}, headers=ACT).json() == {
        "deleted": "verif-2026-11-17-194034"}
    assert not (verifs / "verif-2026-11-17-194034.json").exists() and not (verifs / "verif-2026-11-17-194034").exists()
    assert c.get("/api/verifications/verif-2026-11-17-194034").status_code == 404


def test_a_notification_says_what_waits_for_the_human(setup, tmp_path):  # noqa: F811
    deps, watch, llm = setup
    sent = []
    app = create_app(Settings(vault=deps.vault, home=deps.home, journal=tmp_path / "usage.jsonl",
                              make_deps=lambda thread, kind: deps, list_issues=lambda: [],
                              notifier=lambda *a: sent.append(a), notify_lang="fr"))
    c = TestClient(app)
    thread = c.post("/api/analyses", json={"watch_json": str(watch)}, headers=ACT).json()["thread"]
    wait(c, thread)
    for _ in range(100):  # the notification follows the end of the background work
        if sent:
            break
        time.sleep(0.05)
    title, body, url = sent[0]
    assert "Relecture à faire" in title and "5 correction(s)" in body and url.endswith(f"#/run/{thread}")


def test_settings_keep_a_reference_to_the_key_never_the_key(client, monkeypatch):
    from vault_watch_agent import llm as engines

    c, _ = client
    monkeypatch.delenv("VAULT_WATCH_ENGINE", raising=False)
    monkeypatch.setenv("WATCH_KEY", "secret-value")
    signed = {"installed": True, "signed_in": True, "subscription": "pro"}
    monkeypatch.setattr(engines, "claude_code_status", lambda fresh=False: signed)
    s = c.get("/api/settings").json()
    assert (s["engine"], s["engine_now"], s["key"]) == ("", "claude-code", "env:ANTHROPIC_API_KEY")  # a subscription: preferred
    assert s["claude_code"] == signed and s["choices"]["models"]["reasoning"][0] == s["models"]["reasoning"]
    g = s["guide"]  # read-only, from the manifest; the test vault has none: the IA on-prem layout
    assert (g["from_manifest"], g["language"], g["mirrors"][0]["folder"], g["pages"]) == (False, "fr", "en/", 1)
    assert c.get("/api/info").json()["engine"] == "claude-code"
    from vault_watch_agent import __version__
    assert c.get("/api/info").json()["version"] == c.get("/api/health").json()["version"] == __version__
    # What « Give my opinion » may attach (the system and Python), and where its mail goes
    about = c.get("/api/info").json()
    assert about["system"] and about["python"] and about["feedback_email"].startswith("vault-watch@")

    plain = c.post("/api/settings", json={"engine": "api", "key": "sk-ant-api03-plain"}, headers=ACT)
    assert plain.status_code == 400 and "never the key itself" in plain.json()["detail"]
    assert c.post("/api/settings", json={"engine": "api", "key": "env:WATCH_KEY"}).status_code == 403  # no header, no change

    saved = c.post("/api/settings", json={"engine": "api", "key": "env:WATCH_KEY",
                                          "models": {"translator": "claude-haiku-5-5"}}, headers=ACT)
    assert saved.status_code == 200 and "secret-value" not in saved.text
    s = saved.json()
    assert (s["engine"], s["engine_now"], s["key_status"]) == ("api", "api", {"found": True, "error": ""})
    assert c.get("/api/settings").json()["models"]["translator"] == "claude-haiku-5-5"
    options = {o["id"]: o for o in c.get("/api/verifications/options").json()}
    assert options["translation"]["model"] == "claude-haiku-5-5"  # the check names and prices the model of the settings


def test_the_page_and_its_scripts_are_asked_again_each_time(client):
    c, _ = client
    for path in ("/", "/static/app.js", "/static/boot.js", "/static/themes.js", "/static/notify.js", "/static/settings.js"):
        r = c.get(path)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache", path
    assert "cache-control" not in c.get("/api/health").headers


def test_notices_tell_a_page_what_stopped_without_counting_as_activity(client):
    c, watch = client
    assert c.get("/api/notices").json() == {"last": 0, "notices": []}
    thread = c.post("/api/analyses", json={"watch_json": str(watch)}, headers=ACT).json()["thread"]
    wait(c, thread)
    for _ in range(100):  # the notice follows the end of the background work
        if c.get("/api/notices").json()["last"]:
            break
        time.sleep(0.05)
    assert c.get("/api/notices").json() == {"last": 1, "notices": []}  # a page that just opened: only what comes next
    (n,) = c.get("/api/notices?since=0").json()["notices"]
    assert (n["id"], n["thread"], n["key"], n["page"]) == (1, thread, "review", f"#/run/{thread}")
    assert "Relecture à faire" in n["fr"]["title"] and "5 correction(s)" in n["fr"]["body"] and "Review pending" in n["en"]["title"]
    assert c.get("/api/notices?since=1").json()["notices"] == []
    c.app.state.last_activity -= 7200
    c.get("/api/notices?since=1")  # a page left open with its bell on is not someone using it
    assert c.app.state.idle_seconds() > 7000


def test_the_feedback_window_fills_in_the_fields_the_issue_form_has():
    """« Give my opinion » fills the issue form in by its address: the ids it sends are the ids of the form."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    form = (root / ".github" / "ISSUE_TEMPLATE" / "feedback.yml").read_text(encoding="utf-8")
    script = (root / "src" / "vault_watch_agent" / "static" / "feedback.js").read_text(encoding="utf-8")
    ids = re.findall(r"^\s+id: (\w+)$", form, re.M)
    assert ids == ["rating", "type", "message", "version", "environment"]
    assert all(re.search(rf"out\.{i} = ", script) for i in ids) and 'template: "feedback.yml"' in script
    assert "labels: [feedback]" in form and 'labels: "feedback"' in script
    assert "/static/feedback.js" in (root / "src" / "vault_watch_agent" / "static" / "index.html").read_text(encoding="utf-8")


def test_the_page_names_its_files_with_a_version(client):
    c, _ = client
    page = c.get("/").text
    assert 'src="/static/app.js?v=' in page and 'href="/static/style.css?v=' in page and 'href="/static/icon.svg?v=' in page
    version = page.split("app.js?v=")[1].split('"')[0]
    assert c.get(f"/static/app.js?v={version}").status_code == 200


def test_settings_carry_the_effort_of_each_role_and_its_steps(client, monkeypatch):
    c, _ = client
    s = c.get("/api/settings").json()
    assert s["effort"] == {"reasoning": "normal", "translator": "normal"} and s["choices"]["effort"] == ["lower", "normal", "higher"]
    triage = s["choices"]["steps"]["reasoning"][0]
    assert triage == {"step": "triage", "effort": "medium", "levels": {"lower": "low", "normal": "medium", "higher": "high"}}
    saved = c.post("/api/settings", json={"effort": {"translator": "higher"}}, headers=ACT).json()
    assert saved["effort"] == {"reasoning": "normal", "translator": "higher"}
    # Prices: set when given, kept when a page saves without them
    rates = {"input": 1.0, "output": 2.0, "cache_read": 0.1, "cache_write": 1.25}
    saved = c.post("/api/settings", json={"prices": {"claude-opus-5-5": rates}}, headers=ACT).json()
    assert saved["prices"] == {"claude-opus-5-5": rates}
    assert c.post("/api/settings", json={"effort": {}}, headers=ACT).json()["prices"] == {"claude-opus-5-5": rates}


def test_models_come_from_the_api_or_from_what_the_agent_knows(client, monkeypatch):
    from vault_watch_agent import llm as engines

    c, _ = client
    monkeypatch.setattr(engines, "list_models", lambda ref, prices=None: [{"id": "claude-mythos-6", "name": "Claude Mythos 6", "context": 1, "priced": False}])
    assert c.get("/api/models").json()["source"] == "api"

    def refuse(ref, prices=None):
        raise engines.ModelError("no key")
    monkeypatch.setattr(engines, "list_models", refuse)
    r = c.get("/api/models").json()
    assert r["source"] == "known" and r["error"] == "no key" and "claude-fable-5-2" in [m["id"] for m in r["models"]]


def test_the_search_for_a_dead_link_gets_what_the_page_says_with_it(tmp_path):
    from vault_watch_agent.verify import citing
    (tmp_path / "p.md").write_text("Intro.\n\nLe MI350X a 288 Go de HBM3E[^2].\n\nAutre.\n\n"
                                   "[^1]: Ailleurs, https://example.org/a\n[^2]: AMD, fiche, https://example.org/dead\n",
                                   encoding="utf-8")
    shown = citing(tmp_path, "p.md", "https://example.org/dead")
    assert "3: Le MI350X a 288 Go de HBM3E[^2]." in shown and "8: [^2]: AMD, fiche" in shown
    assert "Intro" not in shown and "example.org/a" not in shown
    assert "(not found)" in citing(tmp_path, "absent.md", "https://example.org/dead")


def test_prices_are_read_on_request_applied_on_a_second_click_and_their_origin_shown(client, monkeypatch):
    from vault_watch_agent import prices

    c, _ = client
    rates = {"input": 1.0, "output": 2.0, "cache_read": 0.1, "cache_write": 1.25}
    monkeypatch.setattr(prices, "fetch", lambda today: {"date": "2026-11-18", "source": "x", "estimated": [],
                                                        "models": {"claude-opus-5-5": rates}})
    table = c.get("/api/settings").json()["price_table"]
    opus = next(m for m in table["models"] if m["id"] == "claude-opus-5-5")
    assert (opus["in_use"], opus["origin"], opus["date"], table["fetched"]) == (True, "default", "2026-11", None)
    assert c.post("/api/prices/apply", headers=ACT).status_code == 409  # nothing read yet
    read = c.post("/api/prices/fetch", headers=ACT).json()
    assert read["changes"] == ["~ claude-opus-5-5: 4 / 20 / 0.2 / 5 (default of 2026-11) -> 1 / 2 / 0.1 / 1.25"]
    assert c.get("/api/settings").json()["price_table"]["fetched"] is None  # not applied by reading it
    applied = c.post("/api/prices/apply", headers=ACT).json()["price_table"]
    opus = next(m for m in applied["models"] if m["id"] == "claude-opus-5-5")
    assert (opus["origin"], opus["rates"], applied["fetched"]["date"]) == ("fetched", rates, "2026-11-18")
    options = {o["id"]: o for o in c.get("/api/verifications/options").json()}
    assert options["coherence"]["price_origin"] == ""  # a fetched price is not flagged
    assert options["translation"]["price_origin"] == "default of 2026-11"  # Sonnet 5.5: still the default
    assert "origins" in c.get("/api/costs").json()


def test_the_watch_issues_and_the_pull_requests_go_through_the_forge(monkeypatch):
    from vault_watch_agent import forge, web

    class Fake:
        name = "Fake"

        def issues(self, repo, label, limit=12):
            assert (repo, label) == ("owner/guide", "watch")
            return [{"number": 9, "title": "Watch — 2026-11-16 (73 items)", "state": "open", "date": "2026-11-16",
                     "labels": ["watch", "urgent"], "body": ""}]

        def pull_request_state(self, url):
            return "merged"

    before = forge.get()
    forge.use(Fake())
    try:
        [issue] = web.list_issues("owner/guide", "watch")()
        assert (issue["number"], issue["urgent"], issue["items"]) == (9, True, 73)
        assert web.gh_pr_state("https://example/pr/1") == "merged"
        assert web.list_issues("", "watch")() == []  # a local guide has no issue
    finally:
        forge.use(before)


def test_a_guide_whose_watches_are_files_lists_them_and_starts_from_one(sample_guide, tmp_path):
    import json

    from fastapi.testclient import TestClient

    from vault_watch_agent import watches
    from vault_watch_agent.vault import guide_of

    guide, watch = sample_guide
    folder = guide / "watches"
    folder.mkdir()
    data = json.loads(watch.read_text(encoding="utf-8"))
    (folder / "2026-11-02.json").write_text(json.dumps(data), encoding="utf-8")
    (folder / "2026-11-16.json").write_text(json.dumps({**data, "since": "2026-11-03", "until": "2026-11-16"}), encoding="utf-8")
    (folder / "broken.json").write_text(json.dumps({"items": [{"title": "x"}]}), encoding="utf-8")
    manifest = guide / "vault-watch.toml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace('path = "watch.json"', 'path = "watches"'), encoding="utf-8")

    src = watches.of(guide_of(guide), tmp_path / "home")
    listed = src.list()
    assert [w["id"] for w in listed] == ["watches/broken.json", "watches/2026-11-16.json", "watches/2026-11-02.json"]
    assert listed[1]["items"] == 5 and listed[1]["urgent"] and listed[1]["thread"] == "2026-11-16"
    assert "lacks triage" in listed[0]["error"]
    assert src.fetch("watches/2026-11-02.json").name == "2026-11-02.json"
    with pytest.raises(ValueError, match="not a watch of this guide"):
        src.fetch("../outside.json")

    app = create_app(Settings(vault=guide, home=tmp_path / "home", journal=tmp_path / "usage.jsonl",
                              make_deps=lambda thread, kind: None))
    c = TestClient(app)
    assert [w["kind"] for w in c.get("/api/watches").json()] == ["file"] * 3
    assert c.post("/api/analyses", json={"watch": "vault-watch.toml"}, headers=ACT).status_code == 400


def test_the_sources_page_shows_the_last_check_and_applies_what_is_chosen(setup, tmp_path, monkeypatch):  # noqa: F811
    from vault_watch_agent import sourcecheck

    deps, home, states = setup[0], setup[0].home, {}
    c = TestClient(create_app(Settings(vault=deps.vault, home=home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [],
                                       pr_state=lambda url: states.get(url, "open"))))
    assert c.get("/api/sources").json()["check"] is None
    assert c.post("/api/sources/apply", json={"ids": ["S1"]}, headers=ACT).status_code == 400  # nothing was checked
    proposals = [{"id": "S1", "action": "add", "why": "cited", "recommended": False, "pages": 2, "examples": ["a.md"],
                  "feed": {"id": "new", "domain": "engines", "type": "github-releases", "repo": "acme/new", "tier": "A"}},
                 {"id": "S2", "action": "remove", "why": "archived", "recommended": True, "feed": {"id": "gone-since"}}]
    (home / "sources-check.json").write_text(json.dumps(
        {"checked": "2026-11-19T22:00:00Z", "stale_days": 180, "min_pages": 2, "probes": {}, "proposals": proposals,
         "applied": []}), encoding="utf-8")
    shown = c.get("/api/sources").json()["check"]["proposals"]
    assert [p["id"] for p in shown] == ["S1"]  # a removal of a feed the file no longer lists is done: not shown
    asked = {}

    def publish(guide, home, chosen, *, today, open_pull_request):
        asked.update(ids=[p["id"] for p in chosen], today=today)
        return {"branch": "chore/watch-sources-x", "pr_url": "https://forge.example/pulls/9"}

    monkeypatch.setattr(sourcecheck, "publish", publish)
    # Put off until the next check: marked, still there, and taken back at will; the guide is not touched
    assert c.post("/api/sources/later", json={"ids": ["S1", "S9"]}, headers=ACT).json() == {"later": ["S1"]}
    assert c.get("/api/sources").json()["check"]["proposals"][0]["later"] > 0 and not asked
    assert c.post("/api/sources/later", json={"ids": ["S1"], "on": False}, headers=ACT).json() == {"later": []}
    assert "later" not in c.get("/api/sources").json()["check"]["proposals"][0]
    assert c.post("/api/sources/later", json={"ids": ["S9"]}, headers=ACT).status_code == 400
    done = c.post("/api/sources/apply", json={"ids": ["S1", "S9"]}, headers=ACT).json()
    assert done == {"branch": "chore/watch-sources-x", "pr_url": "https://forge.example/pulls/9"} and asked["ids"] == ["S1"]
    check = c.get("/api/sources").json()["check"]
    assert check["proposals"][0]["applied"]["pr_url"].endswith("/9") and check["applied"][0]["ids"] == ["S1"]
    assert c.post("/api/sources/apply", json={"ids": ["S1"]}, headers=ACT).status_code == 400  # already applied
    # The pull request is merged on the forge: its proposals are done, and no longer listed
    assert c.get("/api/sources").json()["check"]["applied"][0].get("state") is None  # still open: asked again each time
    states["https://forge.example/pulls/9"] = "merged"
    after = c.get("/api/sources").json()["check"]
    assert after["proposals"] == [] and after["applied"][0]["state"] == "merged"


def test_the_texts_of_the_interface_name_every_step_and_write_no_key_twice():
    """A key written twice in one object silently loses the first: on 2026-11-20 a second `steps` hid the names of
    the steps, shown as « undefined » while a run applied its corrections."""
    import re
    from collections import Counter
    from pathlib import Path

    from vault_watch_agent import web

    lines = (Path(web.__file__).parent / "static" / "app.js").read_text(encoding="utf-8").split("\n")
    starts = [n for n, line in enumerate(lines) if line in ("  fr: {", "  en: {")]
    assert len(starts) == 2
    end = next(n for n in range(starts[1], len(lines)) if lines[n] == "};")
    for first, last in ((starts[0], starts[1]), (starts[1], end)):
        keys = Counter(m.group(1) for line in lines[first:last] if (m := re.match(r"    (\w+): ", line)))
        assert len(keys) > 40 and [k for k, n in keys.items() if n > 1] == []
        names = "\n".join(lines[first:last]).split("\n    steps: {")[1].split("\n    },")[0]
        assert [s for s in web.STEPS if not re.search(rf'\b{s}: "', names)] == []
