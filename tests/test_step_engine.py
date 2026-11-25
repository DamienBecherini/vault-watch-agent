"""A step on its own engine (the Settings), and what one run sets for its own steps without touching the Settings."""

import subprocess

import pytest
from fastapi.testclient import TestClient

from vault_watch_agent import config, llm
from vault_watch_agent.graph import Deps


class Recorder:
    def __init__(self, engine, model):
        self.engine, self.model, self.calls, self.effort_step = engine, model, [], 0

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
        self.calls.append((node, effort))
        return None, {"node": node, "model": self.model, "engine": self.engine}


def refuse(role, journal, settings):
    raise llm.ModelError("API key: env:ANTHROPIC_API_KEY gives nothing")


@pytest.fixture
def engines(monkeypatch):
    monkeypatch.delenv("VAULT_WATCH_ENGINE", raising=False)
    made = {name: llm.EngineKind(name, label, lambda role, journal, settings, name=name: Recorder(name, settings["models"][role]))
            for name, label in (("api", "Claude API"), ("claude-code", "Claude Code (subscription)"))}
    made["openai"] = llm.EngineKind("openai", "A server", refuse)
    monkeypatch.setattr(llm, "_engines", made)


def where(client, node):
    usage = client.parse(system="", prompt="", schema=None, effort="high", node=node)[1]
    return usage["engine"], usage["model"]


def test_a_step_can_run_on_its_own_engine(engines, monkeypatch):
    settings = config.check({"engine": "api", "steps": {
        "news": {"engine": "claude-code"}, "add": {"engine": "claude-code", "model": "claude-sonnet-5-5", "effort": "medium"},
        "compaction": {"model": "claude-fable-5-2"}, "explore": {"engine": "openai"}}})
    assert settings["steps"]["news"] == {"engine": "claude-code"}
    client = llm.create("reasoning", None, settings)
    assert where(client, "verify news") == ("claude-code", "claude-opus-5-5")  # the role's model, with its own engine
    assert where(client, "add 1/2") == ("claude-code", "claude-sonnet-5-5")
    assert where(client, "verify compaction") == ("api", "claude-fable-5-2") and where(client, "crosscheck") == ("api", "claude-opus-5-5")
    assert llm.step_engine(settings, "news") == "claude-code" and llm.step_engine(settings, "fix") == "api"
    assert llm.step_model(settings, "add") == "claude-sonnet-5-5" and llm.step_effort(settings, "add") == "medium"
    assert llm.step_effort(settings, "news") == "high" and llm.step_effort(config.check({"effort": {"reasoning": "lower"}}), "news") == "medium"
    assert llm.billing_of(settings, "claude-code") == "subscription" and llm.billing_of(settings, "api") == "token"
    assert llm.billing_of({"engines": {"openai": {"billing": "local"}}}, "openai") == "none"
    # An engine that cannot be set up is said when its step is asked, not for the runs that never reach it
    with pytest.raises(llm.ModelError, match="explore: the engine openai of this step cannot be used .*gives nothing"):
        where(client, "verify explore 02-materiel")
    # An engine forced for the whole command wins over the steps' own
    monkeypatch.setenv("VAULT_WATCH_ENGINE", "api")
    assert where(llm.create("reasoning", None, settings), "verify news") == ("api", "claude-opus-5-5")
    assert llm.step_engine(settings, "news") == "api"
    with pytest.raises(config.ConfigError, match="steps.news.engine: 'nowhere' is not one of"):
        config.check({"steps": {"news": {"engine": "nowhere"}}})


def test_a_run_keeps_what_it_set_for_its_own_steps(engines, tmp_path):
    home = tmp_path / "home"
    assert config.run_steps(home, "add-2026-11-20") == {}
    kept = config.save_run_steps(home, "add-2026-11-20", {"add": {"engine": "claude-code", "effort": "medium"}, "mirror": {}})
    assert kept == {"add": {"engine": "claude-code", "effort": "medium"}} == config.run_steps(home, "add-2026-11-20")
    assert config.save_run_steps(home, "fix-1", {}) == {} and not (home / "runs" / "fix-1.json").exists()  # nothing set: no file
    # Laid over the settings field by field: the model the settings give that step stays
    settings = config.check({"engine": "api", "steps": {"add": {"model": "claude-fable-5-2"}, "news": {"effort": "max"}}})
    assert config.over(settings["steps"], kept) == {"add": {"model": "claude-fable-5-2", "engine": "claude-code", "effort": "medium"},
                                                    "news": {"effort": "max"}}
    for wrong in ("../settings", "a/b", ""):
        assert config.run_steps(home, wrong) == {}
        with pytest.raises(config.ConfigError):
            config.save_run_steps(home, wrong, {"add": {"effort": "low"}})
    (home / "runs" / "broken.json").write_text("{not json", encoding="utf-8")
    assert config.run_steps(home, "broken") == {}  # edited by hand and unreadable: the settings apply


def test_the_clients_of_a_run_follow_what_it_set(engines, tmp_path, monkeypatch):
    from vault_watch_agent import cli, vault

    home = tmp_path / "home"
    config.save(home, {"engine": "api"})
    config.save_run_steps(home, "add-1", {"add": {"engine": "claude-code", "model": "claude-sonnet-5-5"}})
    repo = tmp_path / "guide"
    repo.mkdir()
    (repo / "vault-watch.toml").write_text('schema = 1\n[guide]\nname = "T"\n[content]\nlanguage = "fr"\n', encoding="utf-8")
    monkeypatch.setattr(cli, "VAULT", repo)  # the guide of the command, whatever another test left there
    monkeypatch.setattr(cli, "CONFIG_HOME", home)
    monkeypatch.setattr(cli, "HOME", home)
    monkeypatch.setattr(vault, "sync", lambda *a, **k: None)
    deps = cli.make_deps("add-1", "fix")
    assert where(deps.llm, "add") == ("claude-code", "claude-sonnet-5-5") and where(deps.llm, "crosscheck") == ("api", "claude-opus-5-5")
    assert where(cli.make_deps("add-2", "fix").llm, "add") == ("api", "claude-opus-5-5")  # another run: the settings


def test_a_page_sees_how_each_step_would_run_and_keeps_its_choice(engines, tmp_path):
    from vault_watch_agent.web import Settings, create_app

    repo = tmp_path / "guide"
    repo.mkdir()
    (repo / "vault-watch.toml").write_text('schema = 1\n[guide]\nname = "T"\n[content]\nlanguage = "fr"\n', encoding="utf-8")
    (repo / "a.md").write_text("# A\n\nUne page.\n", encoding="utf-8")
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "config", "user.name", "t"], ["git", "config", "user.email", "t@t"],
                ["git", "add", "."], ["git", "commit", "-qm", "init"]):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)
    home = tmp_path / "home"
    config.save(home, {"engine": "api", "steps": {"compaction": {"model": "claude-fable-5-2"}}})

    class Llm:
        def parse(self, **kw):
            raise llm.ModelError("not asked in this test")

    deps = Deps(vault=repo, home=home, llm=Llm(), today="2026-11-20")
    c = TestClient(create_app(Settings(vault=repo, home=home, config_home=home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    act = {"X-Vault-Watch": "1"}
    now = c.get("/api/steps").json()
    by = {s["step"]: s for s in now["steps"]}
    assert by["news"] | {"own": False} == {"step": "news", "role": "reasoning", "engine": "api", "engine_label": "Claude API",
                                           "model": "claude-opus-5-5", "effort": "high", "billing": "token", "own": False}
    assert by["compaction"]["model"] == "claude-fable-5-2" and by["compaction"]["own"] and "judge" not in by
    assert [e["name"] for e in now["engines"]] == ["api", "claude-code", "openai"] and "xhigh" in now["efforts"] and now["forced"] == ""
    # What the page chose for one run, laid over the settings: shown, priced, and how it is paid
    own = '{"news": {"engine": "claude-code", "effort": "medium"}}'
    by = {s["step"]: s for s in c.get("/api/steps", params={"steps": own}).json()["steps"]}
    assert (by["news"]["engine"], by["news"]["effort"], by["news"]["billing"]) == ("claude-code", "medium", "subscription")
    options = {o["id"]: o for o in c.get("/api/verifications/options", params={"steps": own}).json()}
    assert options["news"]["billing"] == "subscription" and options["news"]["engine_label"] == "Claude Code (subscription)"
    assert options["coherence"]["billing"] == "token" and options["coherence"]["effort"] == "high" and "engine" not in options["sizes"]
    assert c.get("/api/steps", params={"steps": '{"news": {"engine": "nowhere"}}'}).status_code == 400
    assert c.get("/api/steps", params={"steps": "{not json"}).status_code == 400
    # A run started with its own choice keeps it under its name; the settings are not touched
    thread = c.post("/api/fix", json={"text": "a.md: an idea", "mode": "add", "steps": {"add": {"engine": "claude-code"}}},
                    headers=act).json()["thread"]
    assert config.run_steps(home, thread) == {"add": {"engine": "claude-code"}}
    assert config.load(home)["steps"] == {"compaction": {"model": "claude-fable-5-2"}}
    assert c.post("/api/fix", json={"text": "x", "steps": {"add": {"effort": "huge"}}}, headers=act).status_code == 400
    vid = c.post("/api/verifications", json={"checks": ["sizes"], "steps": {"coherence": {"effort": "low"}}}, headers=act).json()["id"]
    assert config.run_steps(home, vid) == {"coherence": {"effort": "low"}}
