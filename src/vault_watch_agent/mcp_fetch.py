"""The agent's own page reader, offered to Claude Code as a local MCP tool (`web_fetch`) in place of its WebFetch.

Claude Code's WebFetch runs on the editor's machine and reads any address it is given, the machine itself and its
local network included (measured 2026-11-22: it connected to 127.0.0.1 and to the PC's LAN address). A page or a
transcript a run reads could ask for a router's or a NAS's admin page, and the run's next reads could carry it out.
This tool reads through `webtools.WebTools.fetch`: http(s) only, public addresses only (the one connected to as
well), redirections checked one by one, at most MAX_CHARS characters; the same reader as the OpenAI-compatible
engine. WebSearch stays Claude Code's own (a search sends no request to the address it finds).

A minimal MCP server over standard input and output (JSON-RPC 2.0, one message a line): `initialize`, `tools/list`,
`tools/call`. Started by llm.ClaudeCode with `python -m vault_watch_agent.mcp_fetch`, one per call.
"""

from __future__ import annotations

import json
import sys

from . import __version__
from .webtools import FETCH_TOOL, WebError, WebTools

PROTOCOL = "2025-06-18"
TOOL = {"name": "web_fetch", "description": FETCH_TOOL["function"]["description"],
        "inputSchema": FETCH_TOOL["function"]["parameters"]}


def answer(message: dict, tools: WebTools) -> dict | None:
    """The reply to one JSON-RPC message; None for a notification."""
    method, ident = message.get("method"), message.get("id")
    if ident is None:
        return None
    if method == "initialize":
        result = {"protocolVersion": message.get("params", {}).get("protocolVersion") or PROTOCOL,
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "vault-watch-fetch", "version": __version__}}
    elif method == "tools/list":
        result = {"tools": [TOOL]}
    elif method == "tools/call":
        params = message.get("params") or {}
        if params.get("name") != "web_fetch":
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32602, "message": f"unknown tool {params.get('name')}"}}
        try:
            text, failed = tools.fetch(str((params.get("arguments") or {}).get("url") or "")), False
        except WebError as e:
            text, failed = str(e), True
        except Exception as e:  # noqa: BLE001 - said to the model, which can try another page
            text, failed = f"could not be read ({type(e).__name__})", True
        result = {"content": [{"type": "text", "text": text}], "isError": failed}
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"no method {method}"}}
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def main() -> None:
    tools = WebTools()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            reply = answer(json.loads(line), tools)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "not JSON"}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
