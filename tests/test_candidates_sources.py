"""Where the candidates come from (ROADMAP D3.3): the possible additions a watch run sets aside, the leads the editor
dismisses on a check; by hand on the page (test_candidates_page.py). Only for a guide that uses the registry."""

import json
import time

from langgraph.checkpoint.memory import InMemorySaver
from test_candidates_page import ACT, page  # noqa: F401  (fixture: the page on the sample guide)
from test_graph import setup  # noqa: F401  (fixture: throwaway guide, fake model, watch file)

from vault_watch_agent import news
from vault_watch_agent.candidates import Registry, draft_path, guess_kind
from vault_watch_agent.graph import build


def test_the_kind_an_address_says():
    kinds = ("model", "tool", "hardware", "other")
    assert guess_kind("https://huggingface.co/acme/Base-7B", kinds) == "model"
    assert guess_kind("https://huggingface.co/datasets/acme/set", kinds) == "other"
    assert guess_kind("https://github.com/acme/runner", kinds) == "tool"
    assert guess_kind("https://github.com/acme", kinds) == "other"
    assert guess_kind("https://example.org/news", kinds) == "other"
    assert guess_kind("https://huggingface.co/acme/Base-7B", ("software", "other")) == "other"  # not a kind of this guide


def test_a_watch_run_notes_what_it_sets_aside_once_the_registry_is_used(setup):  # noqa: F811
    deps, watch, _ = setup
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
