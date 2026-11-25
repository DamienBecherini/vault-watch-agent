"""The `claude-code` engine: Claude Code of this machine, signed in with a Claude subscription and run once per call
without a terminal (`claude -p`). No API key, nothing billed: the usage counts in the limits of the subscription.

Whether Claude Code is installed and signed in (`llm.claude_code_status`) stays in `llm.py`: the automatic choice of
the engine needs it before any client is made. This module reads it, and the path of `claude`, through `llm`."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from pydantic import ValidationError

from .. import llm
from ..llm import MODEL, Capabilities, EngineKind, ModelError, T, _Journal, context_of, shift_effort

CLAUDE_CODE_TIMEOUT = 3600  # seconds for one call; a cross-check of the whole guide with the web takes minutes
FETCH_TOOL_NAME = "mcp__vw__web_fetch"  # the agent's page reader, as Claude Code names a tool of the MCP server « vw »


def fetch_server(folder: Path) -> Path:
    """The MCP configuration that gives Claude Code the agent's page reader (mcp_fetch), run by this Python with
    this very package; written in the call's temporary folder."""
    config = folder / "mcp.json"
    package_root = str(Path(__file__).resolve().parent.parent.parent)
    config.write_text(json.dumps({"mcpServers": {"vw": {
        "command": sys.executable, "args": ["-m", "vault_watch_agent.mcp_fetch"],
        "env": {"PYTHONPATH": package_root, "PYTHONIOENCODING": "utf-8"}}}}), encoding="utf-8")
    return config


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
        status = llm.claude_code_status(fresh=True)
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
            command = self._command(schema, effort, instructions, web, Path(folder))
            try:
                r = subprocess.run(command, input=prompt.encode("utf-8"), capture_output=True, timeout=CLAUDE_CODE_TIMEOUT,
                                   cwd=folder, env=llm._claude_code_env(), creationflags=llm._NO_WINDOW)
            except subprocess.TimeoutExpired as e:
                raise ModelError(f"{node}: Claude Code did not answer in {CLAUDE_CODE_TIMEOUT // 60} min") from e
            except OSError as e:
                raise ModelError(f"{node}: Claude Code could not be run ({e})") from e
        d = _answer(node, r)
        try:
            parsed = schema.model_validate(_structured(node, d))
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

    def _command(self, schema: type[T], effort: str, instructions: Path, web: bool, folder: Path) -> list[str]:
        """The command of one call. Bare: --safe-mode (no instructions, hooks, skills, plugins nor MCP server of the
        user). With the web, safe mode would also turn off the agent's own MCP page reader: no setting source is
        loaded instead (the user's settings, hooks and plugins stay out; measured 2026-11-22: no CLAUDE.md read
        either), and the only MCP server is the agent's (--strict-mcp-config)."""
        bare = ["--setting-sources", ""] if web else ["--safe-mode"]
        command = [llm.claude_code_program(), "-p", *bare, "--strict-mcp-config", "--no-session-persistence",
                   "--disable-slash-commands", "--model", self.model, "--effort", effort,
                   "--output-format", "json", "--system-prompt-file", str(instructions),
                   "--json-schema", json.dumps(schema.model_json_schema(), ensure_ascii=True)]
        if not web:
            return command + ["--tools", ""]
        # its WebSearch, and the agent's page reader in place of its WebFetch, which reads the LAN (mcp_fetch)
        return command + ["--tools", "WebSearch", "--mcp-config", str(fetch_server(folder)),
                          "--allowedTools", f"WebSearch,{FETCH_TOOL_NAME}", "--disallowedTools", "WebFetch"]


def _answer(node: str, r: subprocess.CompletedProcess) -> dict:
    """What `claude -p --output-format json` answered, or ModelError: no JSON, an error (a limit of the subscription
    reached arrives here, with the time it resets in the message), a refusal."""
    out = r.stdout.decode("utf-8", "replace").strip()
    try:
        d = json.loads(out)
    except ValueError:
        d = None
    if not isinstance(d, dict):
        raise ModelError(f"{node}: Claude Code failed ({(r.stderr.decode('utf-8', 'replace').strip() or out)[:300]})")
    if d.get("is_error") or d.get("subtype") not in (None, "success"):
        raise ModelError(f"{node}: Claude Code: {str(d.get('result') or d.get('subtype') or '?')[:300]}")
    if d.get("stop_reason") == "refusal":
        raise ModelError(f"{node}: refused")
    return d


def _structured(node: str, d: dict):
    """The structured answer: Claude Code's `structured_output`, else its `result` read as JSON."""
    data = d.get("structured_output")
    if data is not None:
        return data
    try:
        return json.loads(str(d.get("result") or ""))
    except ValueError as e:
        raise ModelError(f"{node}: no structured output") from e


def _make(role: str, journal: Path | None, settings: dict) -> ClaudeCode:
    return ClaudeCode(settings["models"][role], journal)


KIND = EngineKind("claude-code", "Claude Code (subscription)", _make)
