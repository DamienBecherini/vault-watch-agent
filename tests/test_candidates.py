"""The registry of discovery (ROADMAP D3.1): candidates followed over time, the collection that drops what they track
and lists what is due, the manifest's [watch] candidates."""

import json

import pytest
from test_collect import NOW, collector

from vault_watch_agent import collect, guide
from vault_watch_agent.candidates import Registry, RegistryError, canonical, key


def test_names_and_addresses_are_compared_in_one_form():
    assert key("Reflection Beam 501B-A23B") == key("reflection-beam 501b a23b") == "reflection-beam-501b-a23b"
    assert canonical("HTTPS://www.Example.org/Models/beam/#card") == "https://example.org/Models/beam"
    assert canonical("https://example.org/a?b=1") == "https://example.org/a?b=1"  # a page may be one by its query


def test_a_candidate_seen_again_gathers_its_sources(tmp_path):
    reg = Registry.load(tmp_path / "candidates.json")  # no file yet: an empty registry
    beam, new = reg.note("Reflection Beam 501B", "https://latent.space/p/beam", origin="watch issue-30", seen="2026-10-10",
                         kind="model")
    assert new and beam["state"] == "lead" and beam["first_seen"] == beam["last_seen"] == "2026-10-10"
    # The same address elsewhere written, or the same name: one candidate, its source kept once
    again, new = reg.note("reflection beam 501b", "https://www.latent.space/p/beam/", origin="verif", seen="2026-11-02")
    assert not new and again is beam and len(beam["sources"]) == 1 and beam["last_seen"] == "2026-11-02"
    _, new = reg.note("Another name", "https://huggingface.co/reflection/beam", origin="collect", seen="2026-11-20")
    assert new  # a new address and a new name: a new candidate (grouping by entity is D2)
    same, new = reg.note("Reflection Beam 501B", "https://huggingface.co/reflection/beam-501b", origin="hand", seen="2026-11-21")
    assert not new and len(same["sources"]) == 2
    with pytest.raises(RegistryError, match="kind"):
        reg.note("x", origin="hand", seen="2026-11-21", kind="person")
    with pytest.raises(RegistryError, match="YYYY-MM-DD"):
        reg.note("x", origin="hand", seen="21/11/2026")


def test_its_states_their_rules_and_what_is_due(tmp_path):
    reg = Registry.load(tmp_path / "candidates.json")
    c, _ = reg.note("Reflection Beam 501B", "https://latent.space/p/beam", origin="watch", seen="2026-10-10", kind="model")
    with pytest.raises(RegistryError, match="needs a reason"):
        reg.move(c["id"], "dismissed", today="2026-11-25")
    with pytest.raises(RegistryError, match="applies to watching or dismissed"):
        reg.move(c["id"], "confirmed", today="2026-11-25", recheck="2026-12-01")
    with pytest.raises(RegistryError, match="not after today"):
        reg.move(c["id"], "watching", today="2026-11-25", recheck="2026-11-25")
    with pytest.raises(RegistryError, match="state 'gone'"):
        reg.move(c["id"], "gone", today="2026-11-25")
    reg.move(c["id"], "watching", today="2026-11-25", reason="weights announced for later", recheck="2026-12-01")
    assert (c["state"], c["reason"], c["recheck"]) == ("watching", "weights announced for later", "2026-12-01")
    assert reg.due("2026-11-30") == [] and reg.due("2026-12-01") == [c]
    reg.move(c["id"], "confirmed", today="2026-12-02")  # another state: no date to look again, no old reason
    assert (c["state"], c["reason"], c["recheck"]) == ("confirmed", "", "")
    assert [h["state"] for h in c["history"]] == ["lead", "watching", "confirmed"]


def test_the_file_is_written_in_a_stable_order_and_read_back(tmp_path):
    path = tmp_path / "vault" / "candidates.json"
    reg = Registry.load(path)
    reg.note("Zeta tool", origin="hand", seen="2026-11-25", kind="tool")
    b, _ = reg.note("Alpha model", "https://example.org/alpha", origin="hand", seen="2026-11-25", kind="model")
    reg.move(b["id"], "dismissed", today="2026-11-25", reason="no weights")
    reg.save()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == 1 and [c["id"] for c in data["candidates"]] == ["zeta-tool", "alpha-model"]  # lead first
    assert Registry.load(path).candidates == data["candidates"]
    path.write_text('{"items": []}', encoding="utf-8")
    with pytest.raises(RegistryError, match="not a registry"):
        Registry.load(path)


def test_the_collection_drops_what_the_registry_tracks_and_lists_what_is_due(tmp_path):
    reg = Registry.load(tmp_path / "candidates.json")
    c, _ = reg.note("Base 7B", "https://huggingface.co/acme/Base-7B", origin="collect", seen="2026-10-01", kind="model")
    reg.move(c["id"], "watching", today="2026-11-01", reason="no benchmark yet", recheck="2026-11-15")
    col = collector()
    col.seen |= reg.urls()
    col.due = reg.due(NOW.strftime("%Y-%m-%d"))
    watch = col.collect(days=8)
    item = next(i for i in watch["items"] if i["title"] == "acme/Base-7B")
    assert (item["triage"], item["reason"]) == ("drop", "already seen")
    assert watch["recheck"] == [{"id": "base-7b", "name": "Base 7B", "kind": "model", "state": "watching",
                                 "reason": "no benchmark yet", "recheck": "2026-11-15", "first_seen": "2026-10-01",
                                 "url": "https://huggingface.co/acme/Base-7B"}]
    md = collect.markdown(watch, col)
    assert "## Candidates to look at again (1)" in md and "| 2026-10-01 | [Base 7B](https://huggingface.co/acme/Base-7B) |" in md
    assert "recheck" not in collector().collect(days=8)  # no registry: the watch as before


def test_the_manifest_names_a_registry_that_may_not_exist_yet(sample_guide):
    root, _ = sample_guide
    manifest = root / "vault-watch.toml"
    text = manifest.read_text(encoding="utf-8")
    assert "[watch]" in text
    manifest.write_text(text.replace("[watch]\n", '[watch]\ncandidates = ".agents/candidates.json"\n', 1), encoding="utf-8")
    assert guide.load(root).watch.candidates == ".agents/candidates.json"
    # The collection of that guide reads it: its addresses are seen, its candidates due are listed
    reg = Registry.load(root / ".agents" / "candidates.json")
    c, _ = reg.note("Memos AI", "https://example.org/memos-ai", origin="hand", seen="2026-11-01", kind="tool")
    reg.move(c["id"], "dismissed", today="2026-11-01", reason="closed beta", recheck="2026-11-10")
    reg.save()
    col = collect.Collector.of_guide(guide.load(root), now=lambda: NOW)
    assert canonical("https://example.org/memos-ai") in col.seen and [d["id"] for d in col.due] == ["memos-ai"]
    (root / ".agents" / "candidates.json").write_text("{", encoding="utf-8")
    with pytest.raises(collect.CollectError, match=r"\[watch\] candidates"):
        collect.Collector.of_guide(guide.load(root), now=lambda: NOW)
    manifest.write_text(text.replace("[watch]\n", '[watch]\ncandidates = "../outside.json"\n', 1), encoding="utf-8")
    with pytest.raises(guide.GuideError, match="must stay inside the guide"):
        guide.load(root)
