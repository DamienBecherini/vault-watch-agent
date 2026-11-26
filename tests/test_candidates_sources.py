"""Where the candidates come from (ROADMAP D3.3): the possible additions a watch run sets aside, the leads the editor
dismisses on a check; by hand on the page (test_candidates_page.py). Only for a guide that uses the registry."""

import json
import time

from langgraph.checkpoint.memory import InMemorySaver
from test_candidates_page import ACT, page  # noqa: F401  (fixture: the page on the sample guide)
from test_graph import setup  # noqa: F401  (fixture: throwaway guide, fake model, watch file)

from vault_watch_agent import inputs, news
from vault_watch_agent.candidates import Registry, draft_path
from vault_watch_agent.graph import build


def test_a_watch_run_notes_what_it_sets_aside_once_the_registry_is_used(setup, monkeypatch):  # noqa: F811
    deps, watch, _ = setup
    # The watch of « issue #30 » is the test's own: never the forge's (the CI has no gh signed in)
    monkeypatch.setattr(inputs, "download_watch", lambda *a, **k: watch)
    graph = build(deps, InMemorySaver())
    # A guide that does not use the registry: nothing is noted
    graph.invoke({"source": str(watch), "issue": None}, {"configurable": {"thread_id": "t1"}})
    assert not draft_path(deps.home).exists()
    # The editor started one (a draft): the next watch notes its possible addition, with its address and reason
    Registry(draft_path(deps.home)).save()
    config = {"configurable": {"thread_id": "t2"}}
    graph.invoke({"source": str(watch), "issue": 30}, config)
    run = graph.get_state(config).values
    items = {i["id"]: i for i in run["items"]}
    added = [items[d["item_id"]] for d in run["decisions"] if d["action"] == "addition"]
    found = Registry.load(draft_path(deps.home)).candidates
    assert len(added) == 1 and [c["name"] for c in found] == [added[0]["title"][:120]]
    lead = found[0]
    assert lead["state"] == "lead" and lead["sources"][0]["url"] == added[0]["url"]
    assert lead["sources"][0]["origin"] == "watch issue #30" and lead["history"][0]["note"].startswith("seen: watch issue #30: ")


def test_a_lead_dismissed_on_a_check_becomes_a_dismissed_candidate(page):  # noqa: F811
    c, root, _, _ = page
    found = "[Found on the web] no page yet: Larkdb 3 ships a sync protocol. Sources: https://example.org/larkdb-3"
    newer = "[Newer] 03-stack/db.md: Larkdb 2.4 is out. Sources: https://example.org/larkdb-2-4"
    assert news.parts(found) == {"kind": "Found on the web", "text": "Larkdb 3 ships a sync protocol.",
                                 "sources": ["https://example.org/larkdb-3"]}
    c.post("/api/candidates", json={"name": "Something", "kind": "tool"}, headers=ACT)  # the editor uses the registry
    draft = c.get("/api/candidates").json()
    assert draft["draft"]
    verifs = root.parent / "home" / "verifications"  # the home of the fixture
    verifs.mkdir(parents=True, exist_ok=True)
    (verifs / "verif-2026-11-26-090000.json").write_text(json.dumps({
        "id": "verif-2026-11-26-090000", "started": time.time() - 60, "checks": ["news"], "asked": ["news"], "cost": 0.0,
        "done": True, "results": {"news": {"ok": False, "summary": "2 leads", "findings": [found, newer], "excerpts": {},
                                           "details": {found: {"title": "Larkdb 3"}}, "fixable": True, "open": 2,
                                           "mode": "add"}}}), encoding="utf-8")
    c.post("/api/verifications/verif-2026-11-26-090000/leads", json={"findings": [found, newer], "status": "dismissed"},
           headers=ACT)
    by_id = {x["id"]: x for x in c.get("/api/candidates").json()["candidates"]}
    assert set(by_id) == {"something", "larkdb-3"}  # « Newer »: about what the guide covers, not a candidate
    lark = by_id["larkdb-3"]
    assert (lark["state"], lark["reason"]) == ("dismissed", "dismissed on the check verif-2026-11-26-090000")
    assert lark["sources"][0]["url"] == "https://example.org/larkdb-3" and lark["sources"][0]["origin"] == "check verif-2026-11-26-090000"


def test_a_lead_of_a_gap_search_can_be_followed_in_the_registry(page):  # noqa: F811
    """E4: a lead neither written nor dismissed becomes a candidate in state « lead », for D1 to D4."""
    c, root, _, _ = page
    found = "[Missing] no page yet: nothing on the EU obligations for a model served in-house; check the official text."
    verifs = root.parent / "home" / "verifications"
    verifs.mkdir(parents=True, exist_ok=True)
    assert c.get("/api/last-gap-search").json() == {}  # never searched
    vid = "verif-2026-11-26-100000"
    (verifs / f"{vid}.json").write_text(json.dumps({
        "id": vid, "started": 1_790_000_000, "checks": ["news"], "asked": ["news"], "cost": 0.0, "done": True,
        "results": {"news": {"ok": False, "summary": "1 lead", "findings": [found], "excerpts": {},
                             "details": {found: {"title": "EU AI Act obligations"}}, "fixable": True, "open": 1, "mode": "add"}}}),
        encoding="utf-8")
    assert c.get("/api/last-gap-search").json() == {"started": 1_790_000_000, "id": vid}
    # A guide that does not use the registry yet: refused, the lead stays open
    refused = c.post(f"/api/verifications/{vid}/leads", json={"findings": [found], "status": "tracked"}, headers=ACT)
    assert refused.status_code == 409 and c.get(f"/api/verifications/{vid}").json()["counts"]["open"] == 1
    c.post("/api/candidates", json={"name": "Something", "kind": "tool"}, headers=ACT)  # the editor uses the registry
    done = c.post(f"/api/verifications/{vid}/leads", json={"findings": [found], "status": "tracked"}, headers=ACT).json()
    assert done["noted"] == ["EU AI Act obligations"] and (done["open"], done["tracked"]) == (0, 1)
    eu = {x["id"]: x for x in c.get("/api/candidates").json()["candidates"]}["eu-ai-act-obligations"]
    assert (eu["state"], eu["sources"]) == ("lead", [])
    assert eu["history"][0]["note"].startswith(f"seen: check {vid}: nothing on the EU obligations")
    assert c.get(f"/api/verifications/{vid}").json()["status"] == "handled"


def test_a_lead_followed_is_named_after_the_product_it_is_about(page):  # noqa: F811
    """The candidate is the product (`subject`), not the headline of the lead (seen in the page on 2026-11-26)."""
    c, root, _, _ = page
    found = "[Missing] 03-stack/engines.md: SGLang is not presented beside vLLM. Sources: https://docs.sglang.ai/"
    verifs = root.parent / "home" / "verifications"
    verifs.mkdir(parents=True, exist_ok=True)
    vid = "verif-2026-11-26-110000"
    (verifs / f"{vid}.json").write_text(json.dumps({
        "id": vid, "started": 1_790_000_000, "checks": ["news"], "asked": ["news"], "cost": 0.0, "done": True,
        "results": {"news": {"ok": False, "summary": "1 lead", "findings": [found], "excerpts": {}, "fixable": True,
                             "details": {found: {"title": "SGLang absent des moteurs", "subject": "SGLang"}},
                             "open": 1, "mode": "add"}}}), encoding="utf-8")
    c.post("/api/candidates", json={"name": "Something", "kind": "tool"}, headers=ACT)
    done = c.post(f"/api/verifications/{vid}/leads", json={"findings": [found], "status": "tracked"}, headers=ACT).json()
    assert done["noted"] == ["SGLang"]
    sglang = {x["id"]: x for x in c.get("/api/candidates").json()["candidates"]}["sglang"]
    assert sglang["sources"][0]["url"] == "https://docs.sglang.ai/"
