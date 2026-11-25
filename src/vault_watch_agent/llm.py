"""The only place that calls Claude.

Every call returns a validated Pydantic object (structured outputs), so the
graph never parses free text. Tests swap these classes for a fake with the same
`parse` method.

Engines share that method (`Engine`, docs/write-an-engine.md):
- `Claude`: the Claude API through the official SDK, billed per token (API key);
- `ClaudeCode`: Claude Code of this machine, signed in with a Claude subscription
  and run once per call without a terminal (`claude -p`). No API key, nothing
  billed: the usage counts in the limits of the subscription;
- `OpenAICompatible` (openai_compat.py): any OpenAI-compatible server, hosted or local;
- any engine another package installs (entry point group `vault_watch_agent.engines`).
`create` picks one (see `engine` and `engines`).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import entry_points
from pathlib import Path
from typing import Protocol, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from . import config
from .prices import Prices

T = TypeVar("T", bound=BaseModel)

# Verification needs judgement: Opus. Mechanical work (translation, day 2): Sonnet. Defaults of the settings (config.MODELS).
MODEL = "claude-opus-5-5"
TRANSLATOR = "claude-sonnet-5-5"
MAX_CONTINUATIONS = 5  # server-side tool loops resumed after pause_turn
# The most one request may write, thinking included: what the model accepts (`max_output`). It was 32 000 until
# 1.1.0, and the whole-guide checks wrote 27 to 29 k on Opus 5.5 at effort high. A cut answer is billed and lost:
# on 20/11/2026 the first compaction report on Fable 5.2 at effort high was cut at 64 000, most of it thinking.
MAX_TOKENS = 128_000  # the current Claude models
OUTPUTS: dict[str, int] = {}  # model id -> the most it writes, as the Models API gave it (list_models fills it)


def max_output(model: str) -> int:
    """The output limit of `model`: from the Models API when it was read, else what the agent knows."""
    return OUTPUTS.get(model) or (64_000 if model.startswith("claude-haiku-4") else MAX_TOKENS)


class ModelError(RuntimeError):
    """`usage`: what the failed call was billed all the same, when the engine knows it (a cut answer)."""
    usage: dict | None = None


class LLM(Protocol):
    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str,
              context: str | None = None) -> tuple[T, dict]: ...


class Engine(Protocol):
    """What the graph needs from a model client (docs/write-an-engine.md; tests/engine_contract.py checks it).

    `parse` returns the answer validated against `schema` and the usage of the call, and writes that usage to the
    journal (`_Journal.record`). It raises ModelError for a refusal, a cut answer, an answer not in the shape, a
    server that cannot be reached. `context` is a long text shared by several calls (the guide): the engine caches it
    when it can. `web`: the model may search the web and read pages. `count_tokens` is optional."""
    model: str
    run: str
    kind: str
    effort_step: int

    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str,
              context: str | None = None, web: bool = False) -> tuple[T, dict]: ...

    def capabilities(self) -> Capabilities: ...


USAGE_KEYS = ("node", "model", "engine", "effort", "input", "output", "cache_read", "cache_write", "web_searches",
              "cost_usd")  # every usage an engine returns has them (the journal and costs.py read them)


EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")  # accepted by the API and by Claude Code (--effort)
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


def shift_effort(effort: str, step: int) -> str:
    """The effort a step asks for, moved `step` levels, within low…max (medium + 1 = high, high + 1 = xhigh)."""
    i = EFFORT_LEVELS.index(effort) + step
    return EFFORT_LEVELS[max(0, min(len(EFFORT_LEVELS) - 1, i))]


class _Journal:
    """What both engines share: the model, the effort of its role, the labels of the run and the call journal."""

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


class Claude(_Journal):
    """The Claude API, billed per token."""

    def capabilities(self) -> Capabilities:
        # The API hands the fetched page to the model, and counts tokens exactly (messages.count_tokens).
        return Capabilities(context=context_of(self.model), exact_count=True)

    def count_tokens(self, text: str) -> int | None:
        """The tokens of `text` for this model (Token Counting API, not billed); None when it cannot be asked."""
        try:
            return self.client.messages.count_tokens(
                model=self.model, messages=[{"role": "user", "content": text}]).input_tokens
        except Exception:  # noqa: BLE001 - any failure: the caller estimates instead
            return None

    def __init__(self, model: str = MODEL, client: anthropic.Anthropic | None = None, journal: Path | None = None):
        super().__init__(model, journal)
        # Reads ANTHROPIC_API_KEY from the environment (injected by sops, never stored here).
        self.client = client or anthropic.Anthropic()

    signals_start = True  # `parse` takes `started` (optional, outside the engine protocol)

    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str,
              context: str | None = None, web: bool = False,
              started: Callable[[], None] | None = None) -> tuple[T, dict]:
        """`context` (the whole vault, for instance) goes first and is cached, so the next calls
        within five minutes read it at the cache price instead of the full input price.
        `web` lets the model search the web and open sources (server-side tools run by the API).
        `started` is called once the answer has begun: the cache of `context` can then be read, so calls that
        share it are started after that, not together (each would pay for writing it)."""
        effort = shift_effort(effort, self.effort_step)
        blocks = system
        if context:
            blocks = [{"type": "text", "text": context, "cache_control": {"type": "ephemeral"}},
                      {"type": "text", "text": system}]
        extra = {}
        if web:
            extra["tools"] = [
                {"type": "web_search_20260209", "name": "web_search", "max_uses": 20},
                {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 30},
            ]
        messages: list = [{"role": "user", "content": prompt}]
        totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "web_searches": 0}
        limit = max_output(self.model)
        for _ in range(MAX_CONTINUATIONS):
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=limit,
                system=blocks,
                messages=messages,
                output_format=schema,
                output_config={"effort": effort},
                # On a policy decline, the API re-runs the request on a fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **extra,
            ) as stream:
                try:
                    if started:
                        for event in stream:  # the first content: the answer has begun, the cache is written
                            if getattr(event, "type", "").startswith("content_block"):
                                break
                        started()
                        started = None
                    message = stream.get_final_message()
                except ValidationError as e:
                    # The SDK reads the JSON when its block ends: an answer cut at the limit is not JSON. The call is
                    # billed: it goes to the journal with what is known (the input as counted, the output at the limit).
                    u = stream.current_message_snapshot.usage
                    usage = {"node": node, "model": self.model, "engine": "api", "effort": effort, "cut": True,
                             "input": totals["input"] + u.input_tokens, "output": totals["output"] + limit,
                             "cache_read": totals["cache_read"] + (u.cache_read_input_tokens or 0),
                             "cache_write": totals["cache_write"] + (u.cache_creation_input_tokens or 0),
                             "web_searches": totals["web_searches"]}
                    usd, price = self.prices.cost(usage)
                    usage.update(cost_usd=round(usd, 6), price=price.rates() if price else None,
                                 price_origin=price.label if price else "no price")
                    self.record(usage)
                    error = ModelError(f"{node}: the answer was cut before its end (the limit of {limit:,} output tokens, "
                                       f"thinking included): billed ≈ {usd:.2f} $ and lost. Lower the effort of this step "
                                       "or ask it for less.")
                    error.usage = usage
                    raise error from e
            u = message.usage
            totals["input"] += u.input_tokens
            totals["output"] += u.output_tokens
            totals["cache_read"] += u.cache_read_input_tokens or 0
            totals["cache_write"] += u.cache_creation_input_tokens or 0
            stu = getattr(u, "server_tool_use", None)
            totals["web_searches"] += (getattr(stu, "web_search_requests", 0) or 0) if stu else 0
            if message.stop_reason != "pause_turn":
                break
            # The server-side tool loop paused: send its turn back and it resumes where it stopped.
            messages = [messages[0], {"role": "assistant", "content": message.content}]
        if message.stop_reason == "refusal":
            category = message.stop_details.category if message.stop_details else None
            raise ModelError(f"{node}: refused ({category})")
        if message.stop_reason == "max_tokens":
            raise ModelError(f"{node}: output truncated at max_tokens")
        parsed = message.parsed_output
        if parsed is None:
            raise ModelError(f"{node}: no structured output")
        usage = {"node": node, "model": message.model, "engine": "api", "effort": effort, **totals}
        usd, price = self.prices.cost(usage)
        # The price the call was counted at, kept with it: a past cost is never recomputed with today's prices.
        usage.update(cost_usd=round(usd, 6), price=price.rates() if price else None,
                     price_origin=price.label if price else "no price")
        self.record(usage)
        return parsed, usage


CLAUDE_CODE_TIMEOUT = 3600  # seconds for one call; a cross-check of the whole guide with the web takes minutes
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: no console window when the server has none
_status: tuple[float, dict] | None = None  # (time, claude_code_status()), asked again after a minute


def claude_code_program() -> str:
    """Path of Claude Code on this machine, "" if it is not installed: VAULT_WATCH_CLAUDE, otherwise `claude` in the PATH."""
    return shutil.which(os.environ.get("VAULT_WATCH_CLAUDE") or "claude") or ""


FETCH_TOOL_NAME = "mcp__vw__web_fetch"  # the agent's page reader, as Claude Code names a tool of the MCP server « vw »


def fetch_server(folder: Path) -> Path:
    """The MCP configuration that gives Claude Code the agent's page reader (mcp_fetch), run by this Python with
    this very package; written in the call's temporary folder."""
    config = folder / "mcp.json"
    package_root = str(Path(__file__).resolve().parent.parent)
    config.write_text(json.dumps({"mcpServers": {"vw": {
        "command": sys.executable, "args": ["-m", "vault_watch_agent.mcp_fetch"],
        "env": {"PYTHONPATH": package_root, "PYTHONIOENCODING": "utf-8"}}}}), encoding="utf-8")
    return config


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
    if not program:
        status = {"installed": False, "signed_in": False, "subscription": ""}
    else:
        try:
            r = subprocess.run([program, "auth", "status", "--json"], capture_output=True, timeout=30,
                               env=_claude_code_env(), stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
            d = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
        except (OSError, subprocess.SubprocessError, ValueError):
            d = {}
        if not isinstance(d, dict):
            d = {}
        with_plan = d.get("loggedIn") is True and d.get("authMethod") == "claude.ai"
        status = {"installed": True, "signed_in": d.get("loggedIn") is True,
                  "subscription": str(d.get("subscriptionType") or "claude.ai") if with_plan else ""}
    _status = (time.monotonic(), status)
    return status


class ClaudeCode(_Journal):
    """Claude Code of this machine on the Claude subscription of its user, one `claude -p` per call.

    It runs bare: none of the user's instructions, hooks, skills or MCP servers (--safe-mode), no conversation kept,
    and no tool but the web search and fetch when the call asks for the web. Refused when Claude Code is not signed
    in with a subscription: it would then spend on an API without a question."""

    def __init__(self, model: str = MODEL, journal: Path | None = None):
        super().__init__(model, journal)
        self.checked = False

    def capabilities(self) -> Capabilities:
        # Pages are read by the agent's own reader (mcp_fetch), whose text the model reads itself; it cannot count
        # tokens before a call.
        return Capabilities(context=context_of(self.model), web_reading="page", billing="subscription")

    def prepare(self) -> None:
        if self.checked:
            return
        status = claude_code_status(fresh=True)
        if not status["installed"]:
            raise ModelError("Claude Code is not installed on this machine (or not in the PATH)")
        if not status["signed_in"]:
            raise ModelError("Claude Code is not signed in: run `claude` once and sign in")
        if not status["subscription"]:
            raise ModelError("Claude Code is not signed in with a Claude subscription: its calls would be billed, "
                             "use the API engine instead")
        self.checked = True

    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str,
              context: str | None = None, web: bool = False) -> tuple[T, dict]:
        """Same contract as `Claude.parse`. The system prompt goes through a file and the prompt through the standard
        input (no limit of length, no quoting); the JSON shape is checked by Claude Code itself (--json-schema).
        `web`: its own WebSearch and WebFetch tools, allowed without a question.

        Claude Code caches its system prompt as one block. With a `context`, the system prompt is that context alone
        and the instructions open the prompt: calls that share the context (same tools and schema) then read it from
        the cache whatever their instructions (measured 17/11/2026: instructions after the context in the system
        prompt, even with --append-system-prompt, wrote the whole context to the cache again)."""
        self.prepare()
        effort = shift_effort(effort, self.effort_step)
        if context:
            system, prompt = context, f"<instructions>\n{system}\n</instructions>\n\n{prompt}"
        with tempfile.TemporaryDirectory(prefix="vault-watch-claude-") as folder:
            instructions = Path(folder) / "instructions.txt"
            instructions.write_text(system, encoding="utf-8")
            # Bare: --safe-mode (no instructions, hooks, skills, plugins nor MCP server of the user). With the web, safe
            # mode would also turn off the agent's own MCP page reader: no setting source is loaded instead (the
            # user's settings, hooks and plugins stay out; measured 2026-11-22: no CLAUDE.md read either), and the
            # only MCP server is the agent's (--strict-mcp-config).
            bare = ["--setting-sources", ""] if web else ["--safe-mode"]
            command = [claude_code_program(), "-p", *bare, "--strict-mcp-config", "--no-session-persistence",
                       "--disable-slash-commands", "--model", self.model, "--effort", effort,
                       "--output-format", "json", "--system-prompt-file", str(instructions),
                       "--json-schema", json.dumps(schema.model_json_schema(), ensure_ascii=True)]
            if web:  # its WebSearch, and the agent's page reader in place of its WebFetch, which reads the LAN (mcp_fetch)
                command += ["--tools", "WebSearch", "--mcp-config", str(fetch_server(Path(folder))),
                            "--allowedTools", f"WebSearch,{FETCH_TOOL_NAME}", "--disallowedTools", "WebFetch"]
            else:
                command += ["--tools", ""]
            try:
                r = subprocess.run(command, input=prompt.encode("utf-8"), capture_output=True, timeout=CLAUDE_CODE_TIMEOUT,
                                   cwd=folder, env=_claude_code_env(), creationflags=_NO_WINDOW)
            except subprocess.TimeoutExpired as e:
                raise ModelError(f"{node}: Claude Code did not answer in {CLAUDE_CODE_TIMEOUT // 60} min") from e
            except OSError as e:
                raise ModelError(f"{node}: Claude Code could not be run ({e})") from e
        out = r.stdout.decode("utf-8", "replace").strip()
        try:
            d = json.loads(out)
        except ValueError:
            d = None
        if not isinstance(d, dict):
            raise ModelError(f"{node}: Claude Code failed ({(r.stderr.decode('utf-8', 'replace').strip() or out)[:300]})")
        if d.get("is_error") or d.get("subtype") not in (None, "success"):
            # A limit of the subscription reached arrives here, with the time it resets in the message.
            raise ModelError(f"{node}: Claude Code: {str(d.get('result') or d.get('subtype') or '?')[:300]}")
        if d.get("stop_reason") == "refusal":
            raise ModelError(f"{node}: refused")
        data = d.get("structured_output")
        if data is None:
            try:
                data = json.loads(str(d.get("result") or ""))
            except ValueError as e:
                raise ModelError(f"{node}: no structured output") from e
        try:
            parsed = schema.model_validate(data)
        except ValidationError as e:
            raise ModelError(f"{node}: answer not in the expected shape ({e.error_count()} errors)") from e
        u, models = d.get("usage") or {}, d.get("modelUsage") or {}
        usage = {
            "node": node, "model": self.model, "engine": "claude-code", "effort": effort,
            "input": int(u.get("input_tokens") or 0), "output": int(u.get("output_tokens") or 0),
            "cache_read": int(u.get("cache_read_input_tokens") or 0),
            "cache_write": int(u.get("cache_creation_input_tokens") or 0),
            "web_searches": sum(int(m.get("webSearchRequests") or 0) for m in models.values() if isinstance(m, dict)),
            "cost_usd": 0.0,  # nothing billed: the usage counts in the limits of the subscription
            # What Claude Code says the same call would cost on the API (the small model that reads web pages included).
            "list_usd": round(float(d.get("total_cost_usd") or 0.0), 6),
        }
        self.record(usage)
        return parsed, usage


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


def _make_api(role: str, journal: Path | None, settings: dict) -> Engine:
    return Claude(settings["models"][role], api_client(settings["key"]), journal)


def _make_claude_code(role: str, journal: Path | None, settings: dict) -> Engine:
    return ClaudeCode(settings["models"][role], journal)


def _make_openai(role: str, journal: Path | None, settings: dict) -> Engine:
    from .openai_compat import OpenAICompatible

    options = (settings.get("engines") or {}).get("openai") or {}
    return OpenAICompatible((options.get("models") or {}).get(role, ""), options, journal)


def _openai_kind() -> EngineKind:
    from . import openai_compat as oc

    return EngineKind(
        "openai", "OpenAI-compatible server", _make_openai,
        models=lambda settings: oc.list_models((settings.get("engines") or {}).get("openai") or {}),
        check=oc.check_options,
        model_of=lambda settings, role: ((settings.get("engines") or {}).get("openai") or {}).get("models", {}).get(role, ""),
        options=oc.OPTIONS)


ENGINE_ERRORS: dict[str, str] = {}  # entry point -> why it could not be loaded (shown in the Settings)
_engines: dict[str, EngineKind] | None = None


def engines() -> dict[str, EngineKind]:
    """The engines installed: the three of the agent, then those of other packages (entry point group
    `vault_watch_agent.engines`, each pointing to an EngineKind). Read once per process."""
    global _engines
    if _engines is None:
        found = {k.name: k for k in (
            EngineKind("claude-code", "Claude Code (subscription)", _make_claude_code),
            EngineKind("api", "Claude API", _make_api, models=lambda settings: list_models(settings["key"])),
            _openai_kind(),
        )}
        for point in entry_points(group="vault_watch_agent.engines"):
            try:
                kind = point.load()
                if not isinstance(kind, EngineKind):
                    raise TypeError("not an EngineKind")
                if kind.protocol != ENGINE_PROTOCOL:
                    raise TypeError(f"it implements the engine protocol {kind.protocol}, this vault-watch-agent the "
                                    f"protocol {ENGINE_PROTOCOL}: update the one that is behind")
                found.setdefault(kind.name, kind)
            except Exception as e:  # noqa: BLE001 - a broken plug-in is reported, the agent goes on
                ENGINE_ERRORS[point.name] = f"{type(e).__name__}: {e}"
        _engines = found
    return _engines


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
        engine_of_step = step_engine(settings, step, name)
        its = {**settings, "engine": engine_of_step}
        try:
            other = engines()[engine_of_step].make(
                role, journal, _with_model(its, engine_of_step, role, own["model"]) if own.get("model") else its)
        except Exception as e:  # noqa: BLE001 - its engine cannot be set up (no key…): said when the step is asked
            other = _Unavailable(own.get("model") or "", f"{step}: the engine {engine_of_step} of this step cannot be used ({e})")
        other.effort_step = 0 if own.get("effort") else client.effort_step
        other.prices = client.prices
        by_step[step] = other
        if own.get("effort"):
            efforts[step] = own["effort"]
    return Routed(client, by_step, efforts)


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

    def __init__(self, default: Engine, by_step: dict[str, Engine], efforts: dict[str, str]):
        self.__dict__.update(default=default, by_step=by_step, efforts=efforts)

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


def api_client(reference: str) -> anthropic.Anthropic:
    try:
        key = config.resolve_key(reference)
    except config.ConfigError as e:
        raise ModelError(f"API key: {e}") from e
    # No key from the reference: the SDK reads ANTHROPIC_API_KEY itself, and says so when there is none.
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()


MIN_CONTEXT = 1_000_000  # the window of the current models: the whole guide in one call (a smaller one: by chapter)
_models: dict[str, tuple[float, list[dict]]] = {}  # reference of the key -> (time, models), asked again after 10 min


def list_models(reference: str, client: anthropic.Anthropic | None = None, prices: Prices | None = None) -> list[dict]:
    """The Claude models the API key of `reference` can use (Models API, GET /v1/models), newest first:
    {id, name, context, priced}; `priced`: the price table knows its price, so the journal and the estimates count it.
    Every current model, whatever its window: what a smaller one changes (the guide read by chapter) is the
    business of the steps (Capabilities), not of this list. The windows read here are kept for `context_of`.
    ModelError when the API cannot be asked (no key, network, refused)."""
    cached = _models.get(reference)
    if cached and time.monotonic() - cached[0] < 600 and client is None:
        return cached[1]
    try:
        found = list((client or api_client(reference)).models.list(limit=100))
    except anthropic.APIError as e:
        raise ModelError(f"the list of the models could not be read: {e.message if hasattr(e, 'message') else e}") from e
    except (anthropic.AnthropicError, TypeError) as e:  # no key at all (the SDK raises TypeError when it sends)
        raise ModelError(f"the list of the models could not be read: {e}") from e
    models = [{"id": m.id, "name": m.display_name or m.id, "context": m.max_input_tokens,
               "priced": price_of(m.id, prices) is not None}
              for m in sorted(found, key=lambda m: m.created_at, reverse=True)
              if m.id.startswith("claude-") and not getattr(m, "deprecated_at", None)]
    CONTEXTS.update({m["id"]: m["context"] for m in models if m["context"]})
    OUTPUTS.update({m.id: m.max_tokens for m in found if getattr(m, "max_tokens", None)})
    _models[reference] = (time.monotonic(), models)
    return models


def price_of(model: str, prices: Prices | None = None) -> tuple | None:
    """The four rates of a model (input, output, cache read, cache write; USD per million tokens) in `prices`
    (the defaults shipped when omitted), None when no source knows it. Where it comes from: `prices.of(model)`."""
    price = (prices or Prices()).of(model)
    return (price.input, price.output, price.cache_read, price.cache_write) if price else None
