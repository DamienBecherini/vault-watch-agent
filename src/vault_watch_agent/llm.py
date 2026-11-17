"""The only place that calls Claude.

Every call returns a validated Pydantic object (structured outputs), so the
graph never parses free text. Tests swap these classes for a fake with the same
`parse` method.

Two engines share that method:
- `Claude`: the Claude API through the official SDK, billed per token (API key);
- `ClaudeCode`: Claude Code of this machine, signed in with a Claude subscription
  and run once per call without a terminal (`claude -p`). No API key, nothing
  billed: the usage counts in the limits of the subscription.
`create` picks one (see `engine`).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from . import config

T = TypeVar("T", bound=BaseModel)

# Verification needs judgement: Opus. Mechanical work (translation, day 2): Sonnet. Defaults of the settings (config.MODELS).
MODEL = "claude-opus-5-5"
TRANSLATOR = "claude-sonnet-5-5"
MAX_CONTINUATIONS = 5  # server-side tool loops resumed after pause_turn
WEB_SEARCH_USD = 0.01  # 10 $ per 1,000 searches


class ModelError(RuntimeError):
    pass


class LLM(Protocol):
    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str,
              context: str | None = None) -> tuple[T, dict]: ...


class _Journal:
    """What both engines share: the model, the labels of the run and the call journal."""

    def __init__(self, model: str, journal: Path | None):
        self.model = model
        self.journal = journal  # one JSON line per call with its cost, for spend tracking
        self.run = ""  # run label written with each call (thread id), set by the caller
        self.kind = ""  # what the run does: watch, crosscheck…

    def record(self, usage: dict) -> None:
        if not self.journal:
            return
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        with open(self.journal, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "tool": "vault-watch-agent", "run": self.run, "kind": self.kind,
                                **usage}) + "\n")


class Claude(_Journal):
    """The Claude API, billed per token."""

    def __init__(self, model: str = MODEL, client: anthropic.Anthropic | None = None, journal: Path | None = None):
        super().__init__(model, journal)
        # Reads ANTHROPIC_API_KEY from the environment (injected by sops, never stored here).
        self.client = client or anthropic.Anthropic()

    def parse(self, *, system: str, prompt: str, schema: type[T], effort: str, node: str,
              context: str | None = None, web: bool = False) -> tuple[T, dict]:
        """`context` (the whole vault, for instance) goes first and is cached, so the next calls
        within five minutes read it at the cache price instead of the full input price.
        `web` lets the model search the web and open sources (server-side tools run by the API)."""
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
        for _ in range(MAX_CONTINUATIONS):
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=32000,
                system=blocks,
                messages=messages,
                output_format=schema,
                output_config={"effort": effort},
                # On a policy decline, the API re-runs the request on a fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **extra,
            ) as stream:
                message = stream.get_final_message()
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
        usage = {"node": node, "model": message.model, "engine": "api", **totals}
        usage["cost_usd"] = round(cost(usage), 6)
        self.record(usage)
        return parsed, usage


ENGINES = ("claude-code", "api")
CLAUDE_CODE_TIMEOUT = 3600  # seconds for one call; a cross-check of the whole guide with the web takes minutes
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
        if context:
            system, prompt = context, f"<instructions>\n{system}\n</instructions>\n\n{prompt}"
        with tempfile.TemporaryDirectory(prefix="vault-watch-claude-") as folder:
            instructions = Path(folder) / "instructions.txt"
            instructions.write_text(system, encoding="utf-8")
            command = [claude_code_program(), "-p", "--safe-mode", "--strict-mcp-config", "--no-session-persistence",
                       "--disable-slash-commands", "--model", self.model, "--effort", effort,
                       "--output-format", "json", "--system-prompt-file", str(instructions),
                       "--json-schema", json.dumps(schema.model_json_schema(), ensure_ascii=True)]
            command += ["--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch,WebFetch"] if web else ["--tools", ""]
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
            "node": node, "model": self.model, "engine": "claude-code",
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


def engine(choice: str = "") -> str:
    """The engine of the model calls: VAULT_WATCH_ENGINE (`claude-code` or `api`, for one command), otherwise `choice`
    (the settings of the user). Without a choice, Claude Code when it is signed in with a subscription (nothing
    billed), otherwise the API."""
    forced = os.environ.get("VAULT_WATCH_ENGINE", "").strip().lower()
    if forced and forced not in ENGINES:
        raise ModelError(f"VAULT_WATCH_ENGINE={forced}: expected one of {', '.join(ENGINES)}")
    wanted = forced or choice
    if wanted in ENGINES:
        return wanted
    return "claude-code" if claude_code_status()["subscription"] else "api"


def create(role: str = "reasoning", journal: Path | None = None, settings: dict | None = None) -> Claude | ClaudeCode:
    """The model client of a role (`reasoning` or `translator`) under the settings of the user (`config.load`):
    their engine, their model for that role and, for the API, the key their reference gives."""
    settings = settings or config.check({})
    model = settings["models"][role]
    if engine(settings["engine"]) == "claude-code":
        return ClaudeCode(model, journal)
    try:
        key = config.resolve_key(settings["key"])
    except config.ConfigError as e:
        raise ModelError(f"API key: {e}") from e
    # No key from the reference: the SDK reads ANTHROPIC_API_KEY itself, and says so when there is none.
    return Claude(model, anthropic.Anthropic(api_key=key) if key else None, journal)


# List prices, USD per million tokens: input, output, cache read, cache write (5-minute TTL = 1.25 × input).
PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.5),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}


def cost(usage: dict) -> float:
    model = next((m for m in PRICES if usage["model"].startswith(m)), None)
    if model is None:
        return 0.0
    p_in, p_out, p_read, p_write = PRICES[model]
    tokens = (usage["input"] * p_in + usage["output"] * p_out
              + usage.get("cache_read", 0) * p_read + usage.get("cache_write", 0) * p_write) / 1e6
    return tokens + usage.get("web_searches", 0) * WEB_SEARCH_USD  # web fetch is not billed beyond tokens
