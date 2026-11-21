"""The editor's edits checked before a sync (H4.2, proofread.py): spelling, facts on the web, consistency with the
rest of the guide; the fixes accepted applied in the guide's folder, the others left."""

import time

from fastapi.testclient import TestClient

from test_graph import setup  # noqa: F401  (fixture: throwaway guide with an English mirror)
from vault_watch_agent import proofread, vault
from vault_watch_agent.crosscheck import ConsistencyEdit, CorrectionReview, CrossCheck
from vault_watch_agent.web import Settings, create_app

ACT = {"X-Vault-Watch": "1"}
PAGE = "03-stack/engines.md"


class Checker:
    """Answers each check, and says what it was given."""
    def __init__(self):
        self.calls = {}

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
        self.calls[node] = (system, prompt, context, web)
        usage = {"node": node, "model": "fake", "input": 10, "output": 5, "cache_read": 0, "cost_usd": 0.01}
        if node == "proofread spelling":
            assert not web and "spelling" in system and "pour comencer." in prompt
            return proofread.Fixes(fixes=[
                proofread.Fix(page=PAGE, current="pour comencer.", proposed="pour commencer.", reason="typo"),
                proofread.Fix(page=PAGE, current="not in the page", proposed="x", reason="a quote that is not there"),
            ]), usage
        if node == "proofread facts":
            assert web and '<page path="03-stack/engines.md">' in prompt and "<after>" in prompt
            return proofread.Fixes(fixes=[], notes=["03-stack/engines.md: no source for « le plus simple »"]), usage
        assert schema is CrossCheck and "changed some passages by hand" in system
        assert '<page path="03-stack/engines.md">' in context and "pour comencer." in context  # the folder, edits included
        return CrossCheck(
            reviews=[CorrectionReview(id="E1", verdict="keep", reason="fine", revised="")],
            consistency_edits=[ConsistencyEdit(page=PAGE, current="vLLM 0.31 est la version minimale recommandée",
                                               proposed="vLLM 0.31 reste la version minimale recommandée",
                                               reason="say it is a floor", related_to=["E1"])],
            other_findings=[]), usage


def wait(c, cid):
    for _ in range(300):
        data = c.get(f"/api/mirrors/check/{cid}").json()
        if data["done"]:
            return data
        time.sleep(0.05)
    raise AssertionError("check still going")


def test_the_edits_are_checked_and_the_fixes_accepted_go_into_the_folder(setup, tmp_path):  # noqa: F811
    deps, _, _ = setup
    deps.llm = deps.translator = Checker()
    folder = deps.vault
    page = folder / PAGE
    vault.write(page, vault.read(page).replace("pour démarrer.", "pour comencer."))  # in Obsidian, with a typo
    c = TestClient(create_app(Settings(vault=folder, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    plan = c.get("/api/mirrors").json()
    assert set(plan["hand"][0]["check_usd"]) == {"spelling", "facts"} and plan["consistency_usd"] >= 0
    assert plan["check"] is None
    assert c.post("/api/mirrors/check", json={"hand": [PAGE], "checks": ["grammar"]}, headers=ACT).status_code == 400
    assert c.post("/api/mirrors/check", json={"hand": ["nope.md"], "checks": ["spelling"]}, headers=ACT).status_code == 400

    cid = c.post("/api/mirrors/check", json={"hand": [PAGE], "checks": ["spelling", "facts", "consistency"]},
                 headers=ACT).json()["id"]
    data = wait(c, cid)
    assert data["error"] == "" and data["cost"] == 0.03
    assert [(f["id"], f["kind"], f["check"]) for f in data["fixes"]] == [
        ("F1", "spelling", "ok"), ("F2", "spelling", "text-not-found"), ("F3", "consistency", "ok")]
    assert data["notes"] == ["03-stack/engines.md: no source for « le plus simple »"]
    assert c.get("/api/mirrors").json()["check"]["id"] == cid  # shown on the page until decided

    done = c.post(f"/api/mirrors/check/{cid}/accept", json={"ids": ["F1", "F3"], "edits": {"F3": "vLLM 0.31 est le minimum conseillé"}},
                  headers=ACT).json()
    assert done == {"applied": ["F1", "F3"], "failed": {}}
    assert "pour commencer." in vault.read(page)
    assert "vLLM 0.31 est le minimum conseillé[^1]." in vault.read(page)  # the editor's own text
    plan = c.get("/api/mirrors").json()
    assert plan["check"] is None and [h["page"] for h in plan["hand"]] == [PAGE] and plan["hand"][0]["passages"] == 2
