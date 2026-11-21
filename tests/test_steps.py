"""A step set apart from its role: its own model, its own effort (`steps` of the settings)."""

import re
from pathlib import Path

import pytest

from vault_watch_agent import config, llm, reading, steps, verify
from vault_watch_agent.prices import Prices

SRC = Path(__file__).resolve().parent.parent / "src" / "vault_watch_agent"


def test_the_settings_keep_what_a_step_sets_and_refuse_the_rest():
    cfg = config.check({"steps": {"compaction": {"model": " claude-fable-5-2 ", "effort": "HIGH"},
                                  "compact": {"model": "claude-fable-5-2"}, "mirror": {"effort": "low"},
                                  "triage": {"model": "", "effort": ""}}})
    assert cfg["steps"] == {"compaction": {"model": "claude-fable-5-2", "effort": "high"},
                            "compact": {"model": "claude-fable-5-2"}, "mirror": {"effort": "low"}}  # nothing set: dropped
    assert config.check({})["steps"] == {}
    for wrong, word in (({"compactage": {"model": "claude-fable-5-2"}}, "is not a step"),
                        ({"judge": {"model": "claude-fable-5-2"}}, "is not a step"),  # not a step of the Settings
                        ({"compact": {"effort": "higher"}}, "is not one of low"),
                        ({"compact": {"model": "a model"}}, "not a model id"),
                        ({"compact": "claude-fable-5-2"}, "must be an object")):
        with pytest.raises(config.ConfigError, match=word):
            config.check({"steps": wrong})


def test_every_call_of_the_code_belongs_to_a_step():
    """The `node` of each call names its step: a call the table does not know would silently run on the role's model."""
    cases = {"triage": "triage", "propose W1+W2": "proposals", "crosscheck": "crosscheck", "crosscheck 03-stack": "crosscheck",
             "sweep": "crosscheck", "fix": "fix", "fix translation": "fix-translation", "compact": "compact",
             "mirror en/03-stack/engines.md": "mirror", "verify coherence": "coherence", "verify coherence 03-stack": "coherence",
             "verify compaction": "compaction", "verify translation 03-stack en": "translation", "verify claims": "claims",
             "verify deadlinks": "deadlinks", "judge": "judge", "": "", "something else": ""}
    assert {node: steps.of_node(node) for node in cases} == cases
    # The first word of every node written in the code is known (f-strings and defaults included)
    found = set()
    for path in SRC.glob("*.py"):
        if path.name in ("llm.py", "openai_compat.py", "steps.py"):
            continue  # docstring examples, the engines themselves
        found |= {m.split()[0] for m in re.findall(r'(?<![a-z_])node(?:: str)? ?= ?f?"([a-z][^"{]*)', path.read_text(encoding="utf-8"))}
    assert found and found <= set(steps.NODES) | {"verify"}, found - set(steps.NODES)


class Recorder:
    """An engine that says which client answered."""

    def __init__(self, model):
        self.model, self.run, self.kind, self.effort_step, self.calls = model, "", "", 0, []

    def capabilities(self):
        return llm.Capabilities(context=1_000_000 if "fable" in self.model else 50_000)

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
        self.calls.append((node, llm.shift_effort(effort, self.effort_step)))
        return None, {"model": self.model}


@pytest.fixture
def recorder(monkeypatch):
    monkeypatch.delenv("VAULT_WATCH_ENGINE", raising=False)
    kind = llm.EngineKind("api", "fake", lambda role, journal, settings: Recorder(settings["models"][role]))
    monkeypatch.setattr(llm, "_engines", {"api": kind})


def call(client, node, effort="high"):
    return client.parse(system="", prompt="", schema=None, effort=effort, node=node)[1]["model"]


def test_a_step_set_apart_runs_on_its_model_and_the_others_on_the_role(recorder, tmp_path):
    settings = config.check({"engine": "api", "effort": {"reasoning": "lower"},
                             "steps": {"compaction": {"model": "claude-fable-5-2"},
                                       "compact": {"model": "claude-fable-5-2", "effort": "xhigh"},
                                       "crosscheck": {"effort": "max"}, "mirror": {"model": "claude-haiku-5-5"}}})
    client = llm.create("reasoning", None, settings)
    assert isinstance(client, llm.Routed) and client.model == "claude-opus-5-5"  # what it shows is the role's
    assert call(client, "verify compaction") == call(client, "compact") == "claude-fable-5-2"
    assert call(client, "triage", "medium") == call(client, "crosscheck 03-stack") == call(client, "sweep") == "claude-opus-5-5"
    efforts = {node: effort for c in (client.default, *client.by_step.values()) for node, effort in c.calls}
    assert efforts == {"verify compaction": "medium",  # its model alone: the role's « lower » still moves it
                       "compact": "xhigh", "crosscheck 03-stack": "max", "sweep": "max",  # an effort set: taken as it is
                       "triage": "low"}
    client.run, client.kind = "compact-test", "fix"  # the labels of the run reach every client
    assert {(c.run, c.kind) for c in (client.default, *client.by_step.values())} == {("compact-test", "fix")}
    # The other role keeps its own steps; a role without a step set apart is its plain client
    translator = llm.create("translator", None, settings)
    assert call(translator, "mirror en/a.md") == "claude-haiku-5-5" and call(translator, "verify translation a") == "claude-sonnet-5-5"
    assert isinstance(llm.create("reasoning", None, config.check({"engine": "api"})), Recorder)
    assert llm.step_model(settings, "compact") == "claude-fable-5-2" and llm.step_model(settings, "fix") == "claude-opus-5-5"
    # The plan of a whole-guide step is made for the model that will read (here the role's window is too small)
    (tmp_path / "vault-watch.toml").write_text('[guide]\nname = "T"\n[content]\nlanguage = "fr"\n', encoding="utf-8")
    (tmp_path / "a.md").write_text("mot " * 60_000, encoding="utf-8")
    assert reading.plan(tmp_path, client, step="compaction").mode == "whole"
    assert reading.plan(tmp_path, client, step="coherence").mode == "chapters"


def test_the_settings_of_another_engine_take_the_model_where_it_reads_it():
    settings = {"models": {"reasoning": "a", "translator": "b"},
                "engines": {"openai": {"base_url": "http://x/v1", "models": {"reasoning": "qwen", "translator": "qwen"}}}}
    out = llm._with_model(settings, "openai", "reasoning", "big")
    assert out["engines"]["openai"]["models"] == {"reasoning": "big", "translator": "qwen"} and out["models"]["reasoning"] == "big"
    assert settings["engines"]["openai"]["models"]["reasoning"] == "qwen"  # the settings themselves are not touched


def test_an_estimate_is_priced_with_the_model_of_its_step(tmp_path):
    (tmp_path / "vault-watch.toml").write_text('[guide]\nname = "T"\n[content]\nlanguage = "fr"\n', encoding="utf-8")
    (tmp_path / "a.md").write_text("mot " * 5000, encoding="utf-8")
    plain = verify.estimates(tmp_path, {}, None, Prices())
    apart = verify.estimates(tmp_path, {}, None, Prices(), {"compaction": "claude-fable-5-2", "compact": "claude-fable-5-2"})
    assert apart["compaction"]["usd"] == pytest.approx(2 * plain["compaction"]["usd"])  # Fable 5.2: twice Opus 5.5
    assert plain["compact-run"]["usd"] < apart["compact-run"]["usd"] < 2 * plain["compact-run"]["usd"]  # its cross-check stays on the role
    assert plain["compact-run"]["usd_each"] < apart["compact-run"]["usd_each"] < 2 * plain["compact-run"]["usd_each"]
    assert apart["coherence"] == plain["coherence"]
