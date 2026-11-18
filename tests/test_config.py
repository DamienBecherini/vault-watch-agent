"""The settings of the user: defaults, what is refused, and a key that is only ever a reference."""

import json

import pytest

from vault_watch_agent import config, llm


def test_defaults_when_there_is_no_file(tmp_path):
    assert config.load(tmp_path) == {"engine": "", "key": "env:ANTHROPIC_API_KEY",
                                     "models": {"reasoning": "claude-opus-5-5", "translator": "claude-sonnet-5-5"},
                                     "effort": {"reasoning": "normal", "translator": "normal"}, "prices": {}, "engines": {}}


def test_saved_settings_are_read_back_and_unknown_fields_dropped(tmp_path):
    saved = config.save(tmp_path, {"engine": "API", "key": " sops:secrets.env#ANTHROPIC_API_KEY ",
                                   "models": {"translator": "claude-haiku-5-5", "reasoning": "claude-fable-5-2"},
                                   "effort": {"reasoning": "Higher"}, "theme": "dark"})
    assert saved == {"engine": "api", "key": "sops:secrets.env#ANTHROPIC_API_KEY",
                     "models": {"reasoning": "claude-fable-5-2", "translator": "claude-haiku-5-5"},
                     "effort": {"reasoning": "higher", "translator": "normal"}, "prices": {}, "engines": {}}
    assert config.load(tmp_path) == saved
    assert not (tmp_path / "settings.json.partial").exists()


@pytest.mark.parametrize("settings, word", [
    ({"key": "sk-ant-api03-not-a-reference"}, "never the key itself"),
    ({"engine": "gpt"}, "engine"),
    ({"models": {"reasoning": "gpt-5"}}, "not a Claude model id"),
    ({"effort": {"translator": "max"}}, "effort.translator"),
    ({"models": "opus"}, "models must be an object"),
])
def test_settings_that_are_refused(tmp_path, settings, word):
    with pytest.raises(config.ConfigError, match=word):
        config.save(tmp_path, settings)
    assert not (tmp_path / "settings.json").exists()


def test_a_plain_key_written_by_hand_is_refused_when_read(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"key": "sk-ant-api03-by-hand"}), encoding="utf-8")
    with pytest.raises(config.ConfigError, match="never the key itself"):
        config.load(tmp_path)
    with pytest.raises(config.ConfigError, match="plain text is refused"):
        config.resolve_key("sk-ant-api03-by-hand")


def test_a_reference_gives_the_key(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCH_KEY", " from-env ")
    monkeypatch.delenv("NO_SUCH_KEY", raising=False)
    (tmp_path / "key.txt").write_text("from-file\n", encoding="utf-8")
    assert config.resolve_key("env:WATCH_KEY") == "from-env"
    assert config.resolve_key("env:NO_SUCH_KEY") == "" and config.resolve_key("") == ""
    assert config.resolve_key(f"file:{tmp_path / 'key.txt'}") == "from-file"
    with pytest.raises(config.ConfigError, match="cannot be read"):
        config.resolve_key(f"file:{tmp_path / 'missing.txt'}")
    with pytest.raises(config.ConfigError, match="sops:file#NAME"):
        config.resolve_key("sops:secrets.env")


def test_the_status_of_a_key_never_holds_the_key(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCH_KEY", "secret-value")
    assert config.key_status("env:WATCH_KEY") == {"found": True, "error": ""}
    assert config.key_status("env:NO_SUCH_KEY_AT_ALL") == {"found": False, "error": ""}
    status = config.key_status(f"file:{tmp_path / 'missing.txt'}")
    assert not status["found"] and "cannot be read" in status["error"]


def test_the_clients_follow_the_settings(monkeypatch):
    monkeypatch.delenv("VAULT_WATCH_ENGINE", raising=False)
    monkeypatch.setenv("WATCH_KEY", "from-env")
    settings = config.check({"engine": "api", "key": "env:WATCH_KEY", "models": {"translator": "claude-haiku-5-5"},
                             "effort": {"reasoning": "lower"}})
    reasoning, translator = llm.create("reasoning", None, settings), llm.create("translator", None, settings)
    assert isinstance(reasoning, llm.Claude) and reasoning.model == "claude-opus-5-5" and reasoning.client.api_key == "from-env"
    assert translator.model == "claude-haiku-5-5"
    assert (reasoning.effort_step, translator.effort_step) == (-1, 0)
    code = llm.create("translator", None, {**settings, "engine": "claude-code"})
    assert isinstance(code, llm.ClaudeCode) and code.model == "claude-haiku-5-5"
    monkeypatch.setenv("VAULT_WATCH_ENGINE", "claude-code")  # one command: the variable wins over the settings
    assert isinstance(llm.create("reasoning", None, settings), llm.ClaudeCode)
    with pytest.raises(llm.ModelError, match="API key"):
        monkeypatch.setenv("VAULT_WATCH_ENGINE", "api")
        llm.create("reasoning", None, {**settings, "key": "file:/no/such/key"})
