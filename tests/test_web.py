"""The web interface drives the same graph: start a run, review, then decline to publish, all through the API."""

import time

import pytest
from fastapi.testclient import TestClient

from test_graph import setup  # noqa: F401  (fixture: throwaway vault, fake model, watch file)
from vault_watch_agent.web import Settings, create_app

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
    assert c.get("/api/sante").json()["ok"]
    assert c.post("/api/analyses", json={"watch_json": str(watch)}).status_code == 403  # no header, no action
    thread = c.post("/api/analyses", json={"watch_json": str(watch)}, headers=ACT).json()["thread"]

    run = wait(c, thread)
    assert run["status"] == "review"
    assert [x["id"] for x in run["corrections"]] == ["C1", "C2", "C3", "C4", "C5"]
    assert run["triage"] == {"correct": 1, "addition": 1, "drop": 1}
    assert {e["node"] for e in run["job"]["events"]} >= {"collect", "triage", "propose", "crosscheck", "report", "pause"}
    assert "Watch report" in c.get(f"/api/runs/{thread}/rapport").text
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
    c.get("/api/sante")  # a supervisor polling the health endpoint is not someone using the page
    assert app.state.idle_seconds() > 7000
    c.get("/api/runs")
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
    assert len(v["results"]["freshness"]["claims"]) == 1
    assert [p["id"] for p in c.get("/api/verifications").json()] == [vid]
    assert c.post("/api/verifications", json={"checks": ["nope"]}, headers=ACT).status_code == 400
