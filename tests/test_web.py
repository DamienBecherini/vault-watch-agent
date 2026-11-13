"""The web interface drives the same graph: start a run, review, then decline to publish, all through the API."""

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
