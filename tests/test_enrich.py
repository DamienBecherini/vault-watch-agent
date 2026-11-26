"""What a candidate is, read on Hugging Face and GitHub without a model (ROADMAP D1), with answers recorded here: the
tests never reach the network. Only the readers the guide names read (`[watch] candidate_readers`, none by default)."""

import re

from test_candidates_page import ACT, page  # noqa: F401  (fixture: the page on the sample guide)

from vault_watch_agent import enrich, vault

HF_MODEL = {"id": "acme/Base-7B", "tags": ["transformers", "gguf", "license:apache-2.0"], "cardData": {"license": "apache-2.0"},
            "safetensors": {"total": 7_615_616_512}, "pipeline_tag": "text-generation", "downloads": 1_234_567, "likes": 89,
            "gated": False, "createdAt": "2026-09-01T10:00:00.000Z", "lastModified": "2026-10-02T08:00:00.000Z",
            "siblings": [{"rfilename": "config.json"}]}
GH_REPO = {"full_name": "acme/runner", "license": {"spdx_id": "MIT"}, "stargazers_count": 12400, "archived": False,
           "description": "Runs models", "created_at": "2025-01-01T00:00:00Z", "pushed_at": "2026-11-20T12:00:00Z"}


def answers(table: dict):
    """A reader that answers from `table` ({url: JSON}), and says HTTP 404 for any other address; the calls kept."""
    calls = []

    def get(url, **kw):
        calls.append((url, kw.get("token", "")))
        if url not in table:
            raise RuntimeError("HTTP 404")
        return table[url]
    get.calls = calls
    return get


def test_the_addresses_it_can_tell_about():
    assert enrich.where("https://huggingface.co/acme/Base-7B") == ("huggingface", "acme/Base-7B")
    assert enrich.where("https://hf.co/acme/Base-7B/") == ("huggingface", "acme/Base-7B")
    assert enrich.where("https://huggingface.co/datasets/acme/set") is None
    assert enrich.where("https://huggingface.co/acme/Base-7B/tree/main") is None  # a page of the repository, not it
    assert enrich.where("https://github.com/acme/runner/releases/tag/v1.2") == ("github", "acme/runner")
    assert enrich.where("https://github.com/orgs/acme") is None and enrich.where("https://example.org/x") is None
    # Only the readers named
    assert enrich.where("https://huggingface.co/acme/Base-7B", ("github",)) is None
    assert enrich.where("https://github.com/acme/runner", ()) is None


def test_the_kind_an_address_says_through_the_guides_readers():
    kinds, both = ("model", "tool", "hardware", "other"), ("huggingface", "github")
    assert enrich.guess_kind("https://huggingface.co/acme/Base-7B", kinds, both) == "model"
    assert enrich.guess_kind("https://huggingface.co/datasets/acme/set", kinds, both) == "other"
    assert enrich.guess_kind("https://github.com/acme/runner", kinds, both) == "tool"
    assert enrich.guess_kind("https://github.com/acme", kinds, both) == "other"
    assert enrich.guess_kind("https://example.org/news", kinds, both) == "other"
    assert enrich.guess_kind("https://huggingface.co/acme/Base-7B", ("software", "other"), both) == "other"  # not its kind
    assert enrich.guess_kind("https://huggingface.co/acme/Base-7B", kinds, ()) == "other"  # no reader named


def test_a_model_and_a_repository_read_without_a_model():
    get = answers({"https://huggingface.co/api/models/acme/Base-7B": HF_MODEL,
                   "https://huggingface.co/acme/Base-7B/resolve/main/config.json": {"max_position_embeddings": 32768},
                   "https://api.github.com/repos/acme/runner": GH_REPO,
                   "https://api.github.com/repos/acme/runner/releases/latest": {"tag_name": "v1.2", "published_at": "2026-11-01T00:00:00Z"},
                   "https://api.github.com/repos/acme/runner/contributors?per_page=100": [{}] * 100})
    c = {"sources": [{"url": "https://huggingface.co/acme/Base-7B"}, {"url": "https://github.com/acme/runner"},
                     {"url": "https://example.org/news"}]}
    assert enrich.enrich(c, today="2026-11-26", readers=("huggingface", "github"), get=get, token="t0k", at="2026-11-26") == []
    model, repo = c["facts"]
    assert model == {"url": "https://huggingface.co/acme/Base-7B", "read": "2026-11-26", "source": "huggingface",
                     "repo": "acme/Base-7B", "licence": "apache-2.0", "params": 7_615_616_512, "gguf": True,
                     "task": "text-generation", "downloads": 1_234_567, "likes": 89, "created": "2026-09-01",
                     "updated": "2026-10-02", "context": 32768}
    assert repo == {"url": "https://github.com/acme/runner", "read": "2026-11-26", "source": "github", "repo": "acme/runner",
                    "licence": "MIT", "stars": 12400, "description": "Runs models", "created": "2025-01-01",
                    "pushed": "2026-11-20", "release": "v1.2", "released": "2026-11-01", "contributors": "100+"}
    # The token of GitHub goes to GitHub only
    assert {u for u, t in get.calls if t} == {u for u, _ in get.calls if u.startswith("https://api.github.com/")}


def test_what_cannot_be_read_is_said_and_keeps_what_was_read_before():
    c = {"sources": [{"url": "https://huggingface.co/acme/Gone"}, {"url": "https://huggingface.co/acme/Base-7B"}],
         "facts": [{"url": "https://huggingface.co/acme/Base-7B", "read": "2026-11-01", "source": "huggingface", "likes": 3}]}
    errors = enrich.enrich(c, today="2026-11-26", readers=("huggingface", "github"), get=answers({}))
    assert errors == ["https://huggingface.co/acme/Gone: HTTP 404", "https://huggingface.co/acme/Base-7B: HTTP 404"]
    assert c["facts"] == [{"url": "https://huggingface.co/acme/Base-7B", "read": "2026-11-01", "source": "huggingface", "likes": 3}]
    # A gated model: its config.json is not asked
    gated = answers({"https://huggingface.co/api/models/acme/Base-7B": {**HF_MODEL, "gated": "manual"}})
    c = {"sources": [{"url": "https://huggingface.co/acme/Base-7B"}]}
    assert enrich.enrich(c, today="2026-11-26", readers=("huggingface", "github"), get=gated) == [] and c["facts"][0]["gated"] is True
    assert [u for u, _ in gated.calls] == ["https://huggingface.co/api/models/acme/Base-7B"]


def test_a_guide_that_names_no_reader_reads_nothing_and_keeps_what_was_read():
    get = answers({"https://huggingface.co/api/models/acme/Base-7B": HF_MODEL})
    old = {"url": "https://huggingface.co/acme/Base-7B", "read": "2026-11-01", "source": "huggingface", "likes": 3}
    c = {"sources": [{"url": "https://huggingface.co/acme/Base-7B"}], "facts": [old]}
    assert enrich.enrich(c, today="2026-11-26", readers=(), get=get) == [] and get.calls == []
    assert c["facts"] == [old]  # a reader dropped from the manifest since: what it read stays
    assert enrich.enrich(c, today="2026-11-26", readers=("github",), get=get) == [] and get.calls == []


def test_a_candidate_added_on_the_page_is_read_and_can_be_read_again(page, monkeypatch):  # noqa: F811
    c, root, _, _ = page
    table = {"https://huggingface.co/api/models/acme/Base-7B": HF_MODEL}
    monkeypatch.setattr(enrich, "GET", answers(table))
    # The guide names no reader: added, not read, no « Read again »
    plain = c.post("/api/candidates", json={"name": "Plain", "url": "https://huggingface.co/acme/Plain"}, headers=ACT).json()
    assert plain["readers"] == [] and plain["readable"] == [] and "facts" not in plain["candidates"][0]
    assert enrich.GET.calls == []
    assert plain["reader_labels"] == {"huggingface": "Hugging Face", "github": "GitHub"}
    manifest = root / "vault-watch.toml"
    vault.write(manifest, vault.read(manifest).replace("[watch]\n", '[watch]\ncandidate_readers = ["huggingface"]\n', 1))
    added = c.post("/api/candidates", json={"name": "Base 7B", "url": "https://huggingface.co/acme/Base-7B", "kind": "model"},
                   headers=ACT).json()
    base = next(x for x in added["candidates"] if x["id"] == "base-7b")
    assert added["readers"] == ["huggingface"] and set(added["readable"]) == {"base-7b", "plain"}
    assert added["errors"] == [] and base["facts"][0]["licence"] == "apache-2.0" and "context" not in base["facts"][0]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", base["facts"][0]["read"])  # the day and the time it was read
    # The same address again, under another name: nothing added (said so on the page), nor read again
    same = c.post("/api/candidates", json={"name": "Base", "url": "https://huggingface.co/acme/Base-7B"}, headers=ACT).json()
    assert (same["new"], same["source_added"], len(same["candidates"])) == (False, False, 2)
    table["https://huggingface.co/acme/Base-7B/resolve/main/config.json"] = {"text_config": {"max_position_embeddings": 131072}}
    again = c.post("/api/candidates/base-7b/enrich", headers=ACT).json()
    assert again["errors"] == [] and next(x for x in again["candidates"] if x["id"] == "base-7b")["facts"][0]["context"] == 131072
    monkeypatch.setattr(enrich, "GET", answers({}))
    failed = c.post("/api/candidates/base-7b/enrich", headers=ACT).json()
    kept = next(x for x in failed["candidates"] if x["id"] == "base-7b")
    assert failed["errors"] == ["https://huggingface.co/acme/Base-7B: HTTP 404"] and kept["facts"][0]["context"] == 131072
