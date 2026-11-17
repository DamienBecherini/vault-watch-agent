"""The settings of the user: which engine calls the model, where the API key is, which models.

One JSON file, `settings.json` in the home of the agent (`.vault-watch/`), written by the Settings page of the
web interface or by hand. A missing file or a missing field means the default.

    {"engine": "",                               "" (automatic), "claude-code" or "api" (llm.engine)
     "key": "env:ANTHROPIC_API_KEY",             where the API key is: a reference, never the key itself
     "models": {"reasoning": "claude-opus-5-5", "translator": "claude-sonnet-5-5"}}

The key is never stored here. The field takes a reference to where it lives:
    env:NAME            an environment variable (injected by sops, for instance)
    sops:file#NAME      a field of a file encrypted with sops, decrypted when the key is needed
    file:path           a file that holds the key alone
A plain value is refused twice: when the settings are saved, and when the key is read (a file edited by hand).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

FILE = "settings.json"
ENGINES = ("", "claude-code", "api")  # "": Claude Code when it is signed in with a subscription, otherwise the API
REFERENCES = ("env:", "file:", "sops:")
KEY_FORMS = "env:NAME, sops:file#NAME or file:path"
# The models offered for each role, the ones `llm.PRICES` knows the price of; the first of a role is its default.
MODELS = {
    "reasoning": ("claude-opus-5-5", "claude-sonnet-5-5"),  # triage, proposals, cross-check, checks of the guide
    "translator": ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"),  # English mirror, translation checks
}
DEFAULTS = {"engine": "", "key": "env:ANTHROPIC_API_KEY", "models": {role: names[0] for role, names in MODELS.items()}}
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: no console window when the server has none


class ConfigError(ValueError):
    pass


def check(cfg: dict) -> dict:
    """The settings with every field present and valid, or ConfigError; unknown fields are dropped."""
    if not isinstance(cfg, dict):
        raise ConfigError("the settings must be a JSON object")
    engine = str(cfg.get("engine", DEFAULTS["engine"]) or "").strip().lower()
    if engine not in ENGINES:
        raise ConfigError(f"engine: {engine!r} is not one of automatic (empty), claude-code, api")
    key = str(cfg.get("key", DEFAULTS["key"]) or "").strip()
    if key and not key.startswith(REFERENCES):
        raise ConfigError(f"key: give a reference to where the key is ({KEY_FORMS}), never the key itself")
    given = cfg.get("models") or {}
    if not isinstance(given, dict):
        raise ConfigError("models must be an object")
    models = {}
    for role, names in MODELS.items():
        models[role] = str(given.get(role) or names[0]).strip()
        if models[role] not in names:
            raise ConfigError(f"models.{role}: {models[role]!r} is not one of {', '.join(names)}")
    return {"engine": engine, "key": key, "models": models}


def load(home: Path) -> dict:
    """The settings, defaults where the file says nothing. A file that cannot be read is an error, not a silent default."""
    path = home / FILE
    if not path.is_file():
        return check({})
    try:
        return check(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:  # ConfigError is a ValueError
        raise ConfigError(f"{path}: {e}") from e


def save(home: Path, cfg: dict) -> dict:
    cfg = check(cfg)
    home.mkdir(parents=True, exist_ok=True)
    # Written aside, then put in place in one go: a server stopped midway never leaves half a file.
    partial = home / (FILE + ".partial")
    partial.write_text(json.dumps(cfg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(partial, home / FILE)
    return cfg


def resolve_key(reference: str) -> str:
    """Value of a key from its reference ("" for no reference or an unset variable). Never logged by the callers."""
    reference = (reference or "").strip()
    if not reference:
        return ""
    if reference.startswith("env:"):
        return os.environ.get(reference[4:], "").strip()
    if reference.startswith("file:"):
        path = Path(os.path.expanduser(reference[5:]))
        try:
            return path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError) as e:
            raise ConfigError(f"key file {path} cannot be read ({type(e).__name__})") from e
    if reference.startswith("sops:"):
        file, _, name = reference[5:].partition("#")
        if not name:
            raise ConfigError("sops reference without a field name: expected sops:file#NAME")
        sops = shutil.which("sops")
        if not sops:
            raise ConfigError("sops is not installed (or not in the PATH)")
        try:
            r = subprocess.run([sops, "-d", "--extract", f'["{name}"]', file], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60, stdin=subprocess.DEVNULL,
                               creationflags=_NO_WINDOW)
        except (OSError, subprocess.SubprocessError) as e:
            raise ConfigError(f"sops could not be run ({type(e).__name__})") from e
        if r.returncode != 0:
            raise ConfigError(f"sops could not read {name} in {file}: {r.stderr.strip()[-200:]}")
        return r.stdout.strip()
    raise ConfigError(f"a key in plain text is refused: give a reference ({KEY_FORMS})")


def key_status(reference: str) -> dict:
    """{found, error}: whether the reference gives a key, without the key."""
    try:
        return {"found": bool(resolve_key(reference)), "error": ""}
    except ConfigError as e:
        return {"found": False, "error": str(e)}
