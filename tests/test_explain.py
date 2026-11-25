"""The explanations of a pause in the page's language (explain.py, /api/explain): one call for the lines not
translated yet, each line kept; nothing in English; a model that fails leaves the English."""


from fastapi.testclient import TestClient
from test_graph import setup  # noqa: F401  (fixture: throwaway guide, fake model, watch file)

from vault_watch_agent import explain, llm, steps
from vault_watch_agent.web import Settings, create_app

ACT = {"X-Vault-Watch": "1"}
WHY = "The M4 Max row is a generation old."
DOUBT = "00-lexique/npu.md: « seul Core ML » is too absolute."


class Translator:
    """Translates each line it gets, by a mark: what was asked is kept, to see what a second ask sends."""

    def __init__(self, fail=False):
        self.asked, self.fail = [], fail

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
        if self.fail:
            raise llm.ModelError("limit reached")
        assert schema is explain.Lines and node == "explain" and effort == steps.effort("explain") and "French" in system
        ids = [part.split('"')[1] for part in prompt.split("<line id=")[1:]]
        texts = [part.split("\n")[1] for part in prompt.split("<line id=")[1:]]
        self.asked.append(texts)
        return explain.Lines(lines=[explain.Line(id=i, text=f"FR {t}") for i, t in zip(ids, texts)]), {"node": node}


def test_the_lines_translated_once_then_kept(tmp_path):
    model = Translator()
    found, usage = explain.lines([WHY, DOUBT, WHY, ""], "fr", model, tmp_path)
    assert found == {WHY: f"FR {WHY}", DOUBT: f"FR {DOUBT}"} and len(usage) == 1
    assert model.asked == [[WHY, DOUBT]]  # each line once, the empty one left
    again, usage = explain.lines([DOUBT, "A new doubt."], "fr", model, tmp_path)
    assert again == {DOUBT: f"FR {DOUBT}", "A new doubt.": "FR A new doubt."} and model.asked[-1] == ["A new doubt."]
    assert explain.lines([WHY], "fr", Translator(fail=True), tmp_path)[0] == {WHY: f"FR {WHY}"}  # kept: no call


def test_nothing_translated_in_english_or_without_a_model(tmp_path):
    model = Translator()
    assert explain.lines([WHY], "en", model, tmp_path) == ({}, []) and explain.lines([WHY], "", model, tmp_path) == ({}, [])
    assert explain.lines([WHY], "fr", None, tmp_path) == ({}, []) and model.asked == []


def test_one_ask_holds_so_many_lines_the_rest_next(tmp_path, monkeypatch):
    monkeypatch.setattr(explain, "MAX_LINES", 2)
    model = Translator()
    found, _ = explain.lines(["a", "b", "c"], "fr", model, tmp_path)
    assert list(found) == ["a", "b"]
    found, _ = explain.lines(["a", "b", "c"], "fr", model, tmp_path)
    assert len(found) == 3 and model.asked[-1] == ["c"]


def test_the_page_asks_and_a_model_that_fails_leaves_the_english(setup, tmp_path):  # noqa: F811
    deps, _, _ = setup
    deps.translator = Translator()
    asked = []

    def make_deps(thread, kind):
        if kind != "view":  # the app makes its reader of checkpoints when it starts
            asked.append((thread, kind))
        return deps

    c = TestClient(create_app(Settings(vault=deps.vault, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=make_deps, list_issues=lambda: [])))
    r = c.post("/api/explain", json={"texts": [WHY], "lang": "fr", "thread": "fix-2026-11-25"}, headers=ACT).json()
    assert r == {"lines": {WHY: f"FR {WHY}"}} and asked == [("fix-2026-11-25", "explain")]
    assert c.post("/api/explain", json={"texts": [WHY], "lang": "en"}, headers=ACT).json() == {"lines": {}}
    assert len(asked) == 1  # English: no model client made
    assert c.post("/api/explain", json={"texts": [WHY], "lang": "fr", "thread": "../x y"}, headers=ACT).json()["lines"]
    assert asked[-1] == ("explain", "explain")  # a label that is not a run's: the journal says « explain »
    deps.translator = Translator(fail=True)
    r = c.post("/api/explain", json={"texts": ["Another line."], "lang": "fr"}, headers=ACT).json()
    assert r["lines"] == {} and "limit reached" in r["error"]
    assert c.post("/api/explain", json={"texts": [WHY], "lang": "fr"}).status_code == 403  # an action: the header
