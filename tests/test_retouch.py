"""A proposal retouched in the review (H2): the editor's text applied, the model's kept beside it, the free checks run
again on it, the report and the pull request saying so; the server checks a retouch before the review is sent."""

from pathlib import Path

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from test_graph import setup  # noqa: F401  (fixture: throwaway guide, fake model, watch file)
from vault_watch_agent.graph import build, pr_body, retouchable, retouched
from vault_watch_agent.web import Settings, create_app

MINE = "vLLM 0.33 est désormais la version minimale recommandée (novembre 2026)[^1]."


def paused(deps, watch, thread="r1"):
    graph = build(deps, InMemorySaver())
    config = {"configurable": {"thread_id": thread}}
    graph.invoke({"source": str(watch), "issue": None}, config)
    return graph, config


def test_a_retouched_proposal_is_applied_and_the_models_text_kept(setup):  # noqa: F811
    deps, watch, llm = setup
    graph, config = paused(deps, watch)
    model_text = next(c for c in graph.get_state(config).values["corrections"] if c["id"] == "C1")["proposed"]

    graph.invoke(Command(resume={"accepted": ["C1"], "edits": {"C1": MINE}}), config)
    state = graph.get_state(config).values
    c1 = next(c for c in state["corrections"] if c["id"] == "C1")
    assert c1["edited"] and c1["proposed"] == MINE and c1["proposed_model"] == model_text and c1["check"] == "ok"
    assert state["applied"] == ["C1", "C3", "C5"]  # its group goes with it, as before
    page = (Path(state["worktree"]) / "03-stack" / "engines.md").read_text(encoding="utf-8")
    assert MINE in page and model_text not in page
    report = Path(state["report_path"]).read_text(encoding="utf-8")
    assert "## Retouched at the review" in report and MINE in report and model_text in report
    body = pr_body(state)
    assert "| C1 ✍️ |" in body and "1 correction(s) retouched by the editor" in body
    assert "| C3 |" in body  # not retouched: no mark


def test_the_free_checks_run_again_on_a_retouch(setup):  # noqa: F811
    deps, watch, _ = setup
    graph, config = paused(deps, watch, "r2")
    corrections = graph.get_state(config).values["corrections"]
    c1 = next(c for c in corrections if c["id"] == "C1")
    c3 = next(c for c in corrections if c["id"] == "C3")
    c2 = next(c for c in corrections if c["id"] == "C2")
    assert retouchable(c1) and not retouchable(c2)  # C2's quote is not in the page: no text mends that

    same = retouched(deps.vault, corrections, {"C1": c1["current"]})
    assert next(c for c in same if c["id"] == "C1")["check"] == "no change"
    dropped = retouched(deps.vault, corrections, {"C3": ""})  # removes the footnote definition: its group does not put it back
    assert next(c for c in dropped if c["id"] == "C3")["check"].startswith("drops footnote")
    ignored = retouched(deps.vault, corrections, {"C2": "whatever", "C1": c1["proposed"]})
    assert ignored == [dict(c) for c in corrections]  # not retouchable, or the same text: nothing changes
    sourced = retouched(deps.vault, corrections, {"C1": "vLLM 0.35 est la version minimale recommandée[^1]."})
    assert "0.35" in next(c for c in sourced if c["id"] == "C1")["warning"]  # a version none of its footnotes mentions
    assert c3["check"] == "ok" and "edited" not in c1  # the state itself is not changed by a check


def test_the_server_checks_a_retouch_then_sends_it(setup, tmp_path):  # noqa: F811
    deps, watch, _ = setup
    c = TestClient(create_app(Settings(vault=deps.vault, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    act = {"X-Vault-Watch": "1"}
    thread = c.post("/api/analyses", json={"watch_json": str(watch)}, headers=act).json()["thread"]
    from test_web import wait

    run = wait(c, thread)
    flags = {x["id"]: x["retouchable"] for x in run["corrections"]}
    assert flags["C1"] and not flags["C2"] and not flags["C4"]  # C4: in conflict with C1
    checked = c.post(f"/api/runs/{thread}/retouch", json={"edits": {"C1": "vLLM 0.31 est la version minimale recommandée[^1]."}},
                     headers=act).json()
    assert checked == {"C1": {"check": "no change", "warning": ""}}  # the page already says that
    c.post(f"/api/runs/{thread}/review", json={"accept": ["C1"], "edits": {"C1": MINE}}, headers=act)
    run = wait(c, thread)
    assert run["status"] == "publish" and MINE in c.get(f"/api/runs/{thread}/diff").text
    assert next(x for x in run["corrections"] if x["id"] == "C1")["edited"]
