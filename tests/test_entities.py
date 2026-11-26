"""Candidates grouped by entity and scored (ROADMAP D2): no model, the guide's tiers."""

import pytest

from vault_watch_agent import candidates, entities

TIERS = """# Source tiers

Text before the lists: not a domain.

## Tier A

- huggingface.co
- github.com
- qwenlm.github.io

## Tier B

- `simonwillison.net`
- servethehome.com

## Tier C

- reddit.com

## Notes

- example.org
"""


@pytest.mark.parametrize("name, fam", [
    ("Qwen3-235B-A22B-Instruct-2507", "qwen3"),
    ("Qwen3 30B-A3B", "qwen3"),
    ("qwen3 GGUF", "qwen3"),
    ("Qwen3-Coder-480B-A35B", "qwen3-coder"),
    ("Mistral Small 3.2 24B Instruct 2506", "mistral-small-3-2"),
    ("Llama-4-Scout-17B-16E-Instruct", "llama-4-scout"),
    ("NVIDIA RTX PRO 6000", "nvidia-rtx-pro-6000"),
    ("GeForce RTX 5090", "geforce-rtx-5090"),
    ("Mixtral 8x7B", "mixtral"),
    ("7B", "7b"),  # nothing left: the name as it is
])
def test_the_family_of_a_name_leaves_out_what_tells_one_release_from_another(name, fam):
    assert entities.family(name) == fam


@pytest.mark.parametrize("url, who", [
    ("https://docs.vllm.ai/en/latest/", "vllm.ai"),
    ("https://blog.vllm.ai/2026/11/01/x.html", "vllm.ai"),
    ("https://huggingface.co/Qwen/Qwen3-30B-A3B", "huggingface.co/qwen"),
    ("https://github.com/QwenLM/Qwen3", "github.com/qwenlm"),
    ("https://www.reddit.com/r/LocalLLaMA/comments/abc", "reddit.com/r/localllama"),
    ("https://old.reddit.com/r/LocalLLaMA/", "reddit.com/r/localllama"),
    ("https://www.bbc.co.uk/news/tech", "bbc.co.uk"),
    ("https://www.cnil.gouv.fr/fr/ia", "cnil.gouv.fr"),
    ("", ""),
])
def test_a_publisher_is_the_site_or_the_account_on_a_site_where_anyone_publishes(url, who):
    assert entities.publisher(url) == who


def test_the_tiers_are_read_from_the_guides_file(tmp_path):
    md = tmp_path / "source-tiers.md"
    md.write_text(TIERS, encoding="utf-8")
    tiers = entities.load_tiers(md)
    assert tiers == {"huggingface.co": "A", "github.com": "A", "qwenlm.github.io": "A", "simonwillison.net": "B",
                     "servethehome.com": "B", "reddit.com": "C"}
    assert entities.tier_of("https://www.servethehome.com/x", tiers) == "B"
    assert entities.tier_of("https://qwenlm.github.io/blog/qwen3/", tiers) == "A"  # the nearest listed
    assert entities.tier_of("https://example.org/", tiers) == ""
    js = tmp_path / "tiers.json"
    js.write_text('{"A": ["www.nist.gov"], "B": ["lwn.net"], "C": 3}', encoding="utf-8")
    assert entities.load_tiers(js) == {"nist.gov": "A", "lwn.net": "B"}
    assert entities.load_tiers(tmp_path / "none.md") == {} and entities.load_tiers(None) == {}


def _cand(name, *sources, first="", last=""):
    days = [d for _, d in sources] or [first]
    return {"id": candidates.key(name), "name": name, "state": "lead", "first_seen": first or min(days),
            "last_seen": last or max(days), "sources": [{"url": u, "seen": d, "origin": "test"} for u, d in sources]}


def test_the_score_counts_independent_publishers_by_tier_times_the_weeks_seen():
    tiers = {"huggingface.co": "A", "simonwillison.net": "B", "servethehome.com": "B", "reddit.com": "C"}
    a = _cand("Qwen3-235B-A22B", ("https://huggingface.co/Qwen/Qwen3-235B-A22B", "2026-11-02"),
              ("https://huggingface.co/Qwen/Qwen3-235B-A22B-GGUF", "2026-11-03"))  # one publisher, twice
    b = _cand("Qwen3 30B", ("https://www.reddit.com/r/LocalLLaMA/comments/1", "2026-11-10"),
              ("https://simonwillison.net/2026/Nov/10/qwen3/", "2026-11-11"))
    other = _cand("Gemma 4", ("https://servethehome.com/gemma", "2026-11-10"))
    out = entities.view([a, b, other], tiers)
    assert out[a["id"]]["family"] == out[b["id"]]["family"] == "qwen3"
    assert out[a["id"]]["group"] == [b["id"]] and out[b["id"]]["group"] == [a["id"]]
    # Hugging Face/Qwen A 3 + Simon Willison B 2 + r/LocalLLaMA C 1 = 6, seen in two weeks
    assert (out[a["id"]]["score"], out[a["id"]]["weeks"]) == (12, 2)
    assert out[a["id"]]["corroborated"]  # two publishers of tier A or B
    assert [p["publisher"] for p in out[a["id"]]["publishers"]] == ["huggingface.co/qwen", "simonwillison.net", "reddit.com/r/localllama"]
    assert out[other["id"]] == {"family": "gemma-4", "group": [], "score": 2, "weeks": 1, "corroborated": False,
                                "publishers": [{"publisher": "servethehome.com", "tier": "B"}]}
    # Without the guide's tiers every source counts 1, nothing is corroborated by its tier
    assert entities.score([a, b], {})["score"] == 6 and not entities.score([a, b], {})["corroborated"]
    # A candidate without a source: its days only
    assert entities.score([_cand("Bare", first="2026-11-10")], tiers) == {"score": 0, "weeks": 1, "publishers": [], "corroborated": False}


def test_two_candidates_of_one_entity_are_merged(tmp_path):
    reg = candidates.Registry(tmp_path / "c.json")
    a, _ = reg.note("Qwen3-235B-A22B", "https://huggingface.co/Qwen/Qwen3-235B-A22B", origin="watch issue-30", seen="2026-11-02", kind="model")
    b, _ = reg.note("Qwen3 30B", "https://www.reddit.com/r/LocalLLaMA/comments/1", origin="hand", seen="2026-11-10")
    reg.note("Qwen3 30B", "https://huggingface.co/Qwen/Qwen3-235B-A22B", origin="hand", seen="2026-11-11")  # known address: goes to a
    reg.move(b["id"], "watching", today="2026-11-12", reason="no measure yet", recheck="2026-12-01")
    b["facts"] = [{"url": "https://www.reddit.com/r/LocalLLaMA/comments/1", "source": "x"}]
    base = [dict(c) for c in reg.candidates]
    merged = reg.merge(a["id"], b["id"], today="2026-11-26")
    assert [c["id"] for c in reg.candidates] == [a["id"]] and merged is a
    assert [s["url"] for s in a["sources"]] == ["https://huggingface.co/Qwen/Qwen3-235B-A22B", "https://www.reddit.com/r/LocalLLaMA/comments/1"]
    assert (a["state"], a["first_seen"], a["last_seen"], a["aka"]) == ("lead", "2026-11-02", "2026-11-11", ["Qwen3 30B"])
    assert a["facts"] == b["facts"]
    assert [h["note"] for h in a["history"]] == ["seen: watch issue-30", "Qwen3 30B: seen: hand", "Qwen3 30B: no measure yet",
                                                 "merged: Qwen3 30B (watching)"]
    # Noted again under its other name, it comes to the merged candidate
    c, new = reg.note("qwen3-30b", "https://example.org/qwen3-30b", origin="hand", seen="2026-11-27")
    assert c is a and not new
    assert candidates.changes(base, reg.candidates)[-1] == {"what": "merged", "name": "Qwen3 30B", "into": "Qwen3-235B-A22B"}
    assert candidates.said({"what": "merged", "name": "Qwen3 30B", "into": "Qwen3-235B-A22B"}) == \
        "**Qwen3 30B** merged into **Qwen3-235B-A22B** (one entity)"
    with pytest.raises(candidates.RegistryError):
        reg.merge(a["id"], a["id"], today="2026-11-26")
    with pytest.raises(candidates.RegistryError):
        reg.merge(a["id"], "nobody", today="2026-11-26")
