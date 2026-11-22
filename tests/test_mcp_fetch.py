"""The page reader the agent gives Claude Code in place of its WebFetch (mcp_fetch): an MCP server over standard
input and output, which reads through webtools (public addresses only)."""

import json
import subprocess
import sys
from pathlib import Path

from vault_watch_agent import mcp_fetch


class Pages:
    def fetch(self, url):
        if "127.0.0.1" in url:
            raise mcp_fetch.WebError("127.0.0.1: a private or local address is not read")
        return f"Source: {url}\n\nThe page."


def test_it_answers_the_three_messages_of_mcp():
    init = mcp_fetch.answer({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}, Pages())
    assert init["result"]["capabilities"] == {"tools": {}} and init["result"]["protocolVersion"] == "2025-06-18"
    assert mcp_fetch.answer({"jsonrpc": "2.0", "method": "notifications/initialized"}, Pages()) is None
    listed = mcp_fetch.answer({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, Pages())["result"]["tools"]
    assert [t["name"] for t in listed] == ["web_fetch"] and listed[0]["inputSchema"]["required"] == ["url"]
    read = mcp_fetch.answer({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                             "params": {"name": "web_fetch", "arguments": {"url": "https://example.org/"}}}, Pages())["result"]
    assert read == {"content": [{"type": "text", "text": "Source: https://example.org/\n\nThe page."}], "isError": False}
    refused = mcp_fetch.answer({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                "params": {"name": "web_fetch", "arguments": {"url": "http://127.0.0.1/admin"}}}, Pages())["result"]
    assert refused["isError"] and "private or local" in refused["content"][0]["text"]
    assert "error" in mcp_fetch.answer({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "Bash"}}, Pages())


def test_the_server_runs_as_claude_code_starts_it(tmp_path):
    """As the configuration written by llm.fetch_server says: this Python, this package, one message a line."""
    from vault_watch_agent import llm
    server = json.loads(llm.fetch_server(tmp_path).read_text(encoding="utf-8"))["mcpServers"]["vw"]
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "web_fetch", "arguments": {"url": "http://127.0.0.1:9/"}}}]
    r = subprocess.run([server["command"], *server["args"]], input="\n".join(json.dumps(m) for m in lines) + "\n",
                       capture_output=True, text=True, encoding="utf-8", timeout=60,
                       env={**__import__("os").environ, **server["env"]})
    answers = [json.loads(line) for line in r.stdout.splitlines()]
    assert server["command"] == sys.executable and Path(server["env"]["PYTHONPATH"], "vault_watch_agent").is_dir()
    assert answers[0]["id"] == 1 and answers[1]["result"]["isError"]
    assert "private or local" in answers[1]["result"]["content"][0]["text"]
