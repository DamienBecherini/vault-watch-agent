"""The only place that calls Claude: the contract every engine keeps, and the choice of the engine.

Every call returns a validated Pydantic object (structured outputs), so the
graph never parses free text. Tests swap these classes for a fake with the same
`parse` method.

Engines share that method (`Engine`, docs/write-an-engine.md), each in its own module:
- `Claude` (engines/api.py): the Claude API through the official SDK, billed per token (API key);
- `ClaudeCode` (engines/claude_code.py): Claude Code of this machine, signed in with a Claude subscription
  and run once per call without a terminal (`claude -p`). No API key, nothing
  billed: the usage counts in the limits of the subscription;
- `OpenAICompatible` (openai_compat.py): any OpenAI-compatible server, hosted or local;
- any engine another package installs (entry point group `vault_watch_agent.engines`).
`create` picks one (see `engine` and `engines`).

This module holds what they share: the protocols, `ModelError`, the usage keys, the efforts, the capabilities, the
call journal (`_Journal`), the windows of the models, `EngineKind` and the engines installed, and whether Claude Code
can be used on this machine (the automatic choice needs it before any client is made). The engines' own names are
imported back at the end, so that `llm.Claude`, `llm.list_models` and the like still answer.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import entry_points
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, Self, TypeVar, cast

from pydantic import BaseModel

from . import config
from .prices import Prices

T = TypeVar("T", bound=BaseModel)

# Verification needs judgement: Opus. Mechanical work (translation, day 2): Sonnet. Defaults of the settings (config.MODELS).
MODEL = "claude-opus-5-5"
TRANSLATOR = "claude-sonnet-5-5"


class ModelError(RuntimeError):
    """`usage`: what the failed call was billed all the same, when the engine knows it (a cut answer)."""
    usage: dict | None = None


class LLM(Protocol):
    """What the steps call (`Deps.llm`, the client a step is given): `parse`, the labels of the run written with each
    call, and `for_step`, the client that runs a step (the role's own, or another one for a step set apart: `Routed`)."""
    run: str
    kind: str

    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str,
              context: str | None = None, web: bool = False) -> tuple[T, dict]: ...

    def for_step(self, step: str) -> LLM: ...


class Engine(Protocol):
    """What the graph needs from a model client (docs/write-an-engine.md; tests/engine_contract.py checks it).

    `parse` returns the answer validated against `schema` and the usage of the call, and writes that usage to the
    journal (`_Journal.record`). It raises ModelError for a refusal, a cut answer, an answer not in the shape, a
    server that cannot be reached. `context` is a long text shared by several calls (the guide): the engine caches it
    when it can. `web`: the model may search the web and read pages. `count_tokens` is optional. `prices` and
    `for_step` come with `_Journal`."""
    model: str
    run: str
    kind: str
    effort_step: int
    prices: Prices

    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str,
              context: str | None = None, web: bool = False) -> tuple[T, dict]: ...

    def capabilities(self) -> Capabilities: ...

    def for_step(self, step: str) -> Engine: ...


USAGE_KEYS = ("node", "model", "engine", "effort", "input", "output", "cache_read", "cache_write", "web_searches",
              "cost_usd")  # every usage an engine returns has them (the journal and costs.py read them)


Effort = Literal["low", "medium", "high", "xhigh", "max"]
EFFORT_LEVELS: tuple[Effort, ...] = ("low", "medium", "high", "xhigh", "max")  # accepted by the API and by Claude Code (--effort)
EFFORT_STEPS = {"lower": -1, "normal": 0, "higher": 1}  # the effort of a role in the settings (config.EFFORTS)

# The input window of a model when the engine cannot ask it: the current Claude models read 1M tokens; a model the
# agent does not know is taken at the smaller window of the older ones, so the guide is never sent whole to a model
# that cannot hold it.
KNOWN_CONTEXT = 1_000_000
UNKNOWN_CONTEXT = 200_000
CONTEXTS: dict[str, int] = {}  # model id -> its window, as the Models API gave it (list_models fills it)


def context_of(model: str) -> int:
    """The input window of `model`: from the Models API when it was read, else what the agent knows."""
    if model in CONTEXTS:
        return CONTEXTS[model]
    known = {m for names in config.MODELS.values() for m in names} | set(Prices().known())
    base = next((k for k in sorted(known, key=len, reverse=True) if model == k or model.startswith(k + "-")), None)
    return KNOWN_CONTEXT if base else UNKNOWN_CONTEXT


@dataclass(frozen=True)
class Capabilities:
    """What a call through an engine can rely on. The steps check it before they ask (T2.6); a missing
    capability changes how a step runs or turns it off, never silently."""
    context: int  # tokens a call can read (the model's input window)
    structured: str = "native"  # native: the engine checks the JSON shape; instruction: the prompt asks for it
    web: str = "native"  # native: by the model's provider; tools: search and fetch run by the agent; fetch: pages only; none
    web_reading: str = "page"  # page: the model reads the fetched page itself; summary: a smaller model reports on it
    efforts: tuple = EFFORT_LEVELS
    caching: bool = True  # a context shared by several calls is read from a cache at a lower price
    billing: str = "token"  # token: each call is billed; subscription: within the limits of a plan; none: local
    exact_count: bool = False  # the engine counts the tokens of a text before sending it (else an estimate)

    def summary(self) -> dict:
        return {"context": self.context, "structured": self.structured, "web": self.web,
                "web_reading": self.web_reading, "efforts": list(self.efforts), "caching": self.caching,
                "billing": self.billing, "exact_count": self.exact_count}


def shift_effort(effort: str, step: int) -> Effort:
    """The effort a step asks for, moved `step` levels, within low…max (medium + 1 = high, high + 1 = xhigh)."""
    i = EFFORT_LEVELS.index(effort) + step
    return EFFORT_LEVELS[max(0, min(len(EFFORT_LEVELS) - 1, i))]


class _Journal:
    """What every engine shares: the model, the effort of its role, the labels of the run and the call journal."""

    def __init__(self, model: str, journal: Path | None):
        self.model = model
        self.journal = journal  # one JSON line per call with its cost, for spend tracking
        self.run = ""  # run label written with each call (thread id), set by the caller
        self.kind = ""  # what the run does: watch, crosscheck…
        self.effort_step = 0  # -1, 0 or +1: the effort of the role in the settings, applied to every call
        self.prices = Prices()  # the user's price table (create() gives it); the defaults shipped otherwise

    def record(self, usage: dict) -> None:
        if not self.journal:
            return
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        with open(self.journal, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now(UTC).isoformat(timespec="seconds"),
                                "tool": "vault-watch-agent", "run": self.run, "kind": self.kind,
                                **usage}) + "\n")

    def for_step(self, step: str) -> Self:
        """The client that runs `step`: this one (a role whose steps are set apart has a `Routed` client instead)."""
        return self


# ---------------------------------------------------------------------------
# Claude Code on this machine: whether it can be used (engine() picks it without a choice, the Settings show it)
# ---------------------------------------------------------------------------

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: no console window when the server has none
_status: tuple[float, dict] | None = None  # (time, claude_code_status()), asked again after a minute


def claude_code_program() -> str:
    """Path of Claude Code on this machine, "" if it is not installed: VAULT_WATCH_CLAUDE, otherwise `claude` in the PATH."""
    return shutil.which(os.environ.get("VAULT_WATCH_CLAUDE") or "claude") or ""


def _claude_code_env() -> dict:
    """The environment given to Claude Code: without what would make it bill an API (a key, another provider) and
    without the variables of a Claude Code session this process was started from. Its sign-in is kept
    (CLAUDE_CONFIG_DIR)."""
    return {k: v for k, v in os.environ.items()
            if not (k.startswith("ANTHROPIC_") or k.startswith("CLAUDE_CODE_") or k in ("CLAUDECODE", "AWS_BEARER_TOKEN_BEDROCK"))}


def claude_code_status(fresh: bool = False) -> dict:
    """{installed, signed_in, subscription}: whether Claude Code is on this machine and signed in with a Claude
    subscription ("pro", "max"…; "" when it is signed in otherwise: a Console account, a key, another provider, which
    would be billed). Kept for a minute, unless `fresh`."""
    global _status
    if _status and not fresh and time.monotonic() - _status[0] < 60:
        return _status[1]
    program = claude_code_program()
    status = _signed_in(program) if program else {"installed": False, "signed_in": False, "subscription": ""}
    _status = (time.monotonic(), status)
    return status


def _signed_in(program: str) -> dict:
    """What `claude auth status` says of the sign-in of Claude Code, installed at `program`."""
    try:
        r = subprocess.run([program, "auth", "status", "--json"], capture_output=True, timeout=30,
                           env=_claude_code_env(), stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
        d = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    with_plan = d.get("loggedIn") is True and d.get("authMethod") == "claude.ai"
    return {"installed": True, "signed_in": d.get("loggedIn") is True,
            "subscription": str(d.get("subscriptionType") or "claude.ai") if with_plan else ""}


# ---------------------------------------------------------------------------
# The engines installed, and the client of a role
# ---------------------------------------------------------------------------

ENGINE_PROTOCOL = 1  # the version of llm.Engine and EngineKind; a plug-in says which one it implements


@dataclass(frozen=True)
class EngineKind:
    """An engine the agent can use. `make(role, journal, settings)` gives the client of a role; `models(settings)`
    the models it offers ([{id, name, context, priced}], ModelError when it cannot say); `check(options)` validates
    its options in the settings (`engines.<name>`, None: it has none); `model_of(settings, role)` the model of a role."""
    name: str
    label: str
    make: Callable[[str, Path | None, dict], Engine]
    models: Callable[[dict], list[dict]] | None = None
    check: Callable[[dict], dict] | None = None
    model_of: Callable[[dict, str], str] = lambda settings, role: settings["models"][role]
    options: dict = field(default_factory=dict)  # the defaults of its options, for the Settings page
    protocol: int = ENGINE_PROTOCOL  # the version of the engine protocol it implements (docs/write-an-engine.md)


ENGINE_ERRORS: dict[str, str] = {}  # entry point -> why it could not be loaded (shown in the Settings)
_engines: dict[str, EngineKind] | None = None


def engines() -> dict[str, EngineKind]:
    """The engines installed: the three of the agent, then those of other packages (entry point group
    `vault_watch_agent.engines`, each pointing to an EngineKind). Read once per process."""
    global _engines
    if _engines is not None:
        return _engines
    from . import openai_compat
    from .engines import api, claude_code

    found = {k.name: k for k in (claude_code.KIND, api.KIND, openai_compat.KIND)}
    for point in entry_points(group="vault_watch_agent.engines"):
        try:
            kind = _plug_in(point.load())
        except Exception as e:  # noqa: BLE001 - a broken plug-in is reported, the agent goes on
            ENGINE_ERRORS[point.name] = f"{type(e).__name__}: {e}"
            continue
        found.setdefault(kind.name, kind)
    _engines = found
    return _engines


def _plug_in(kind: object) -> EngineKind:
    """What an entry point gave, if it is an engine of this protocol; TypeError says why not."""
    if not isinstance(kind, EngineKind):
        raise TypeError("not an EngineKind")
    if kind.protocol != ENGINE_PROTOCOL:
        raise TypeError(f"it implements the engine protocol {kind.protocol}, this vault-watch-agent the "
                        f"protocol {ENGINE_PROTOCOL}: update the one that is behind")
    return kind


def engine(choice: str = "") -> str:
    """The engine of the model calls: VAULT_WATCH_ENGINE (an engine's name, for one command), otherwise `choice`
    (the settings of the user). Without a choice, Claude Code when it is signed in with a subscription (nothing
    billed), otherwise the API."""
    forced = os.environ.get("VAULT_WATCH_ENGINE", "").strip().lower()
    if forced and forced not in engines():
        raise ModelError(f"VAULT_WATCH_ENGINE={forced}: expected one of {', '.join(engines())}")
    wanted = forced or choice
    if wanted in engines():
        return wanted
    return "claude-code" if claude_code_status()["subscription"] else "api"


def create(role: str = "reasoning", journal: Path | None = None, settings: dict | None = None,
           prices: Prices | None = None, name: str = "") -> Engine:
    """The model client of a role (`reasoning` or `translator`) under the settings of the user (`config.load`):
    their engine, their model and effort for that role and, for the API, the key their reference gives. `prices`:
    the user's price table (`Prices.of_home`), the defaults shipped when omitted. `name`: this engine, whatever the
    settings and VAULT_WATCH_ENGINE say (the judge of `eval`, always the same one)."""
    settings = settings or config.check({})
    name = name or engine(settings["engine"])
    from . import steps

    settings = {**settings, "engine": name}
    client = engines()[name].make(role, journal, settings)
    client.effort_step = EFFORT_STEPS[settings["effort"][role]]
    client.prices = prices or Prices(settings.get("prices"))
    apart = {s: own for s, own in (settings.get("steps") or {}).items() if s in steps.STEPS and steps.STEPS[s].role == role}
    if not apart:
        return client
    by_step, efforts = {}, {}
    for step, own in apart.items():  # one client per step set apart: its engine, its model, its effort taken as it is
        other = _client_of_step(settings, role, journal, step, own, name)
        other.effort_step = 0 if own.get("effort") else client.effort_step
        other.prices = client.prices
        by_step[step] = other
        if own.get("effort"):
            efforts[step] = own["effort"]
    return Routed(client, by_step, efforts)


def _client_of_step(settings: dict, role: str, journal: Path | None, step: str, own: dict, name: str) -> Engine:
    """The client of a step set apart, on its own engine and model; when that engine cannot be set up (no key…),
    a stand-in that says so when the step is asked."""
    engine_of_step = step_engine(settings, step, name)
    its = {**settings, "engine": engine_of_step}
    try:
        return engines()[engine_of_step].make(
            role, journal, _with_model(its, engine_of_step, role, own["model"]) if own.get("model") else its)
    except Exception as e:  # noqa: BLE001 - its engine cannot be set up (no key…): said when the step is asked
        # It has no `capabilities`: the steps that ask for them (hasattr) take the defaults, and the call says why.
        return cast(Engine, _Unavailable(own.get("model") or "", f"{step}: the engine {engine_of_step} of this step cannot be used ({e})"))


class _Unavailable:
    """In place of the client of a step whose engine could not be set up (the API without a key, for instance): the
    error is raised when that step is asked, not for the runs that never reach it."""

    def __init__(self, model: str, error: str):
        self.model, self.error = model, error

    def parse(self, **_):
        raise ModelError(self.error)


class Routed:
    """The client of a role when some of its steps are set apart (`steps` of the settings): a call goes to the
    client of its step (another model, another effort), found from its `node` (steps.of_node), or to the role's.
    Everything else (the model, the capabilities, the token count) is the role's client's; `for_step` gives the
    client that will run a step, for what must know its model before the call (reading.plan)."""

    default: Engine
    by_step: dict[str, Engine]
    efforts: dict[str, str]
    # What an engine has besides: read from the role's client (__getattr__), written to every client (__setattr__)
    model: str
    run: str
    kind: str
    effort_step: int
    prices: Prices
    if TYPE_CHECKING:  # no method at run time: hasattr(routed, "capabilities") is the role's client's answer
        def capabilities(self) -> Capabilities: ...

    def __init__(self, default: Engine, by_step: dict[str, Engine], efforts: dict[str, str]):
        self.__dict__.update(default=default, by_step=by_step, efforts=efforts)  # its own: not through __setattr__

    def for_step(self, step: str) -> Engine:
        return self.by_step.get(step, self.default)

    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str,
              context: str | None = None, web: bool = False, **more) -> tuple[T, dict]:
        from . import steps

        step = steps.of_node(node)
        return self.for_step(step).parse(system=system, prompt=prompt, schema=schema, effort=self.efforts.get(step, effort),
                                         node=node, context=context, web=web, **more)

    def __getattr__(self, name: str):
        return getattr(self.default, name)

    def __setattr__(self, name: str, value) -> None:  # the labels of the run (run, kind) go to every client
        for client in (self.default, *self.by_step.values()):
            setattr(client, name, value)


def _with_model(settings: dict, name: str, role: str, model: str) -> dict:
    """The settings with `model` as the model of `role`, where the engine `name` reads it: `models`, and the
    engine's own options when they hold its models (the OpenAI-compatible server)."""
    out = {**settings, "models": {**settings["models"], role: model}}
    own = (settings.get("engines") or {}).get(name)
    if isinstance(own, dict) and isinstance(own.get("models"), dict):
        out["engines"] = {**settings["engines"], name: {**own, "models": {**own["models"], role: model}}}
    return out


def step_engine(settings: dict, step: str, name: str = "") -> str:
    """The engine that runs `step`: the one forced for the whole command (VAULT_WATCH_ENGINE), else its own (`steps`
    of the settings), else the engine of the settings (`name` when the caller already resolved it)."""
    forced = os.environ.get("VAULT_WATCH_ENGINE", "").strip().lower()
    own = ((settings.get("steps") or {}).get(step) or {}).get("engine")
    return (name or engine(settings["engine"])) if forced or not own else own


def step_model(settings: dict, step: str) -> str:
    """The model that runs `step`: its own (`steps` of the settings), else its role's with the engine of the step."""
    from . import steps

    name = step_engine(settings, step)
    return ((settings.get("steps") or {}).get(step) or {}).get("model") or engines()[name].model_of(
        {**settings, "engine": name}, steps.STEPS[step].role)


def step_effort(settings: dict, step: str) -> str:
    """The effort `step` runs at: its own, taken as it is, else what the code asks moved by the effort of its role."""
    from . import steps

    own = ((settings.get("steps") or {}).get(step) or {}).get("effort")
    return own or shift_effort(steps.effort(step), EFFORT_STEPS[settings["effort"][steps.STEPS[step].role]])


def billing_of(settings: dict, name: str) -> str:
    """How the calls of the engine `name` are paid, without making a client: token, subscription, or none (a local
    model)."""
    if name == "claude-code":
        return "subscription"
    if name == "openai":
        return "none" if ((settings.get("engines") or {}).get("openai") or {}).get("billing") == "local" else "token"
    return "token"


def model_of(settings: dict, role: str) -> str:
    """The model that runs `role` with the engine the settings give."""
    return engines()[engine(settings["engine"])].model_of(settings, role)


def price_of(model: str, prices: Prices | None = None) -> tuple | None:
    """The four rates of a model (input, output, cache read, cache write; USD per million tokens) in `prices`
    (the defaults shipped when omitted), None when no source knows it. Where it comes from: `prices.of(model)`."""
    price = (prices or Prices()).of(model)
    return (price.input, price.output, price.cache_read, price.cache_write) if price else None


# The engines of the agent, each in its own module (engines/): imported last, as they build on the contract above.
# Their names stay reachable here (llm.Claude, llm.list_models, llm.fetch_server…), where callers and tests find them.
from .engines.api import MAX_CONTINUATIONS, MAX_TOKENS, OUTPUTS, Claude, api_client, list_models, max_output  # noqa: E402
from .engines.claude_code import CLAUDE_CODE_TIMEOUT, FETCH_TOOL_NAME, ClaudeCode, fetch_server  # noqa: E402

__all__ = [  # the contract, and the names of the engines imported back above
    "CLAUDE_CODE_TIMEOUT", "CONTEXTS", "ENGINE_ERRORS", "ENGINE_PROTOCOL", "EFFORT_LEVELS", "EFFORT_STEPS", "FETCH_TOOL_NAME",
    "KNOWN_CONTEXT", "MAX_CONTINUATIONS", "MAX_TOKENS", "MODEL", "OUTPUTS", "TRANSLATOR", "UNKNOWN_CONTEXT", "USAGE_KEYS",
    "LLM", "Capabilities", "Claude", "ClaudeCode", "Effort", "Engine", "EngineKind", "ModelError", "Routed",
    "api_client", "billing_of", "claude_code_program", "claude_code_status", "context_of", "create", "engine", "engines",
    "fetch_server", "list_models", "max_output", "model_of", "price_of", "shift_effort", "step_effort", "step_engine",
    "step_model",
]
