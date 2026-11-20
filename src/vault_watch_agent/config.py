"""The settings of the user: which engine calls the model, where the API key is, which models.

One JSON file, `settings.json` in the home of the agent (`.vault-watch/`), written by the Settings page of the
web interface or by hand. A missing file or a missing field means the default.

    {"schema": 1,                                the version of this format (SCHEMA); a file without it is older
                                                 than 1.0 and is read as schema 1, the same fields
     "engine": "",                               "" (automatic), "claude-code", "api", "openai" or an installed
                                                 engine (llm.engines)
     "key": "env:ANTHROPIC_API_KEY",             where the API key is: a reference, never the key itself
     "models": {"reasoning": "claude-opus-5-5", "translator": "claude-sonnet-5-5"},   the Claude engines' models
     "effort": {"reasoning": "normal", "translator": "normal"},   lower, normal or higher: one level for every step
     "steps": {"compaction": {"model": "claude-fable-5-2", "effort": "high"}},   a step set apart from its role:
                                                 its own engine, its own model, its own effort (low … max), or
                                                 any of them (steps.py)
     "engines": {"openai": {"base_url": "http://127.0.0.1:8080/v1", "models": {...}, ...}}}   the options of the
                                                 other engines, each checked by its engine (openai_compat.OPTIONS)

The effort of each call is set per step in the code (the triage at medium, the proposals and the cross-check at
high…); the effort of a role moves every step of that role one level down or up (llm.shift_effort). A step listed
in `steps` runs on the model given there instead of its role's, and at the effort given there as it is (the role's
« lower » or « higher » does not move it): the compaction on the strongest model, the watches unchanged. A step
may also name its own engine (the leads of what is new through a subscription, the rest on the API).

A run can set its steps for itself alone, without touching this file: `run_steps` (the same shape as `steps`, kept
in `runs/<thread>.json` of the guide's working folder), laid over the settings when the clients of that run are made.

The key is never stored here. The field takes a reference to where it lives:
    env:NAME            an environment variable (injected by sops, for instance)
    sops:file#NAME      a field of a file encrypted with sops, decrypted when the key is needed
    file:path           a file that holds the key alone
A plain value is refused twice: when the settings are saved, and when the key is read (a file edited by hand).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from .prices import check_rates

FILE = "settings.json"
SCHEMA = 1  # the version of the settings format; a change of format is a new number and an entry in MIGRATIONS
# schema n -> n+1, applied in order to a file written by an older agent, before it is checked. A file written by a
# newer agent (a higher number) is refused: an older agent would drop the fields it does not know when it saves.
MIGRATIONS: dict[int, "Callable[[dict], dict]"] = {}
ENGINE_NAME = re.compile(r"[a-z][a-z0-9-]{1,40}")  # "": Claude Code on a subscription, otherwise the API
REFERENCES = ("env:", "file:", "sops:")
KEY_FORMS = "env:NAME, sops:file#NAME or file:path"
# The models offered for each role when the list of the API cannot be read; the first of a role is its default.
# Any Claude model id is accepted (the Settings page offers the list of the API, llm.list_models).
MODELS = {
    "reasoning": ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2"),  # triage, proposals, cross-check, checks
    "translator": ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"),  # English mirror, translation checks
}
MODEL_ID = re.compile(r"claude-[a-z0-9][a-z0-9.-]{1,60}")  # the Claude engines' models
ANY_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,159}")  # another engine's: qwen3.6, org/model:tag…
EFFORTS = ("lower", "normal", "higher")  # relative to the effort the code gives each step
DEFAULTS = {"schema": SCHEMA, "engine": "", "key": "env:ANTHROPIC_API_KEY", "models": {role: names[0] for role, names in MODELS.items()},
            "effort": {role: "normal" for role in MODELS}, "steps": {}, "prices": {}, "engines": {}}
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: no console window when the server has none


class ConfigError(ValueError):
    pass


def check(cfg: dict) -> dict:
    """The settings with every field present and valid, or ConfigError; unknown fields are dropped."""
    if not isinstance(cfg, dict):
        raise ConfigError("the settings must be a JSON object")
    cfg = migrate(cfg)
    from . import llm  # the installed engines (llm imports this module)

    engine = str(cfg.get("engine", DEFAULTS["engine"]) or "").strip().lower()
    if engine and engine not in llm.engines():
        raise ConfigError(f"engine: {engine!r} is not one of automatic (empty), {', '.join(llm.engines())}")
    key = str(cfg.get("key", DEFAULTS["key"]) or "").strip()
    if key and not key.startswith(REFERENCES):
        raise ConfigError(f"key: give a reference to where the key is ({KEY_FORMS}), never the key itself")
    given = cfg.get("models") or {}
    if not isinstance(given, dict):
        raise ConfigError("models must be an object")
    models = {}
    for role, names in MODELS.items():
        models[role] = str(given.get(role) or names[0]).strip()
        if not MODEL_ID.fullmatch(models[role]):
            raise ConfigError(f"models.{role}: {models[role]!r} is not a Claude model id (claude-…)")
    given = cfg.get("effort") or {}
    if not isinstance(given, dict):
        raise ConfigError("effort must be an object")
    effort = {}
    for role in MODELS:
        effort[role] = str(given.get(role) or "normal").strip().lower()
        if effort[role] not in EFFORTS:
            raise ConfigError(f"effort.{role}: {effort[role]!r} is not one of {', '.join(EFFORTS)}")
    own = check_steps(cfg.get("steps") or {})
    given = cfg.get("prices") or {}
    if not isinstance(given, dict):
        raise ConfigError("prices must be an object: model id -> its rates")
    prices = {}
    for model, rates in given.items():
        if not ANY_MODEL_ID.fullmatch(str(model)):
            raise ConfigError(f"prices: {model!r} is not a model id")
        try:
            prices[model] = check_rates(rates, f"prices.{model}")
        except ValueError as e:
            raise ConfigError(str(e)) from e
    given = cfg.get("engines") or {}
    if not isinstance(given, dict) or not all(isinstance(v, dict) for v in given.values()):
        raise ConfigError("engines must be an object: engine name -> its options")
    engines = {}
    for name, options in given.items():
        kind = llm.engines().get(name)
        engines[name] = kind.check(options) if kind and kind.check else dict(options)  # an engine not installed: kept
    return {"schema": SCHEMA, "engine": engine, "key": key, "models": models, "effort": effort, "steps": own,
            "prices": prices, "engines": engines}


RUN_STEPS = "runs"  # the folder, in a guide's working folder, of what each run set for itself (`<thread>.json`)
_THREAD = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}")


def over(steps: dict, own: dict) -> dict:
    """`steps` with what `own` sets for each step laid over it, field by field (an engine set for one run keeps the
    model the settings give that step)."""
    return {step: {**steps.get(step, {}), **own.get(step, {})} for step in {**steps, **own}}


def run_steps(home: Path, thread: str) -> dict:
    """What the run `thread` set for its own steps ({} when nothing): read each time its clients are made, so the
    steps that come after a pause (the mirrors, after the review) follow it too."""
    path = home / RUN_STEPS / f"{thread}.json"
    if not _THREAD.fullmatch(thread) or not path.is_file():
        return {}
    try:
        return check_steps(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):  # a file edited by hand: the settings apply, as if the run had set nothing
        return {}


def save_run_steps(home: Path, thread: str, given: dict) -> dict:
    """Keeps what a run sets for its own steps (checked like `steps`; nothing set: no file)."""
    own = check_steps(given or {})
    if not _THREAD.fullmatch(thread):
        raise ConfigError(f"{thread!r} is not the name of a run")
    if own:
        (home / RUN_STEPS).mkdir(parents=True, exist_ok=True)
        (home / RUN_STEPS / f"{thread}.json").write_text(json.dumps(own, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return own


def check_steps(given) -> dict:
    """The steps set apart from their role: {step: {engine, model and/or effort}}; an entry that sets nothing is
    dropped."""
    from . import llm, steps

    if not isinstance(given, dict) or not all(isinstance(v, dict) for v in given.values()):
        raise ConfigError("steps must be an object: step -> {engine, model, effort}")
    known = [s.id for s in steps.STEPS.values() if s.shown]
    out = {}
    for step, own in given.items():
        if step not in known:
            raise ConfigError(f"steps: {step!r} is not a step (one of {', '.join(known)})")
        model, effort = str(own.get("model") or "").strip(), str(own.get("effort") or "").strip().lower()
        engine = str(own.get("engine") or "").strip().lower()
        if engine and engine not in llm.engines():
            raise ConfigError(f"steps.{step}.engine: {engine!r} is not one of {', '.join(llm.engines())}")
        if model and not ANY_MODEL_ID.fullmatch(model):
            raise ConfigError(f"steps.{step}.model: {model!r} is not a model id")
        if effort and effort not in llm.EFFORT_LEVELS:
            raise ConfigError(f"steps.{step}.effort: {effort!r} is not one of {', '.join(llm.EFFORT_LEVELS)}")
        if engine or model or effort:
            out[step] = {k: v for k, v in (("engine", engine), ("model", model), ("effort", effort)) if v}
    return out


def migrate(cfg: dict) -> dict:
    """The settings brought to SCHEMA: no number is a file of before 1.0 (the fields of schema 1)."""
    schema = cfg.get("schema", 1)
    if not isinstance(schema, int) or isinstance(schema, bool) or schema < 1:
        raise ConfigError(f"schema = {schema!r}: a whole number, 1 or more")
    if schema > SCHEMA:
        raise ConfigError(f"schema {schema}: these settings were written by a newer vault-watch-agent (this one reads "
                          f"schema {SCHEMA}); update the agent")
    while schema < SCHEMA:
        cfg, schema = MIGRATIONS[schema](dict(cfg)), schema + 1
    return cfg


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
