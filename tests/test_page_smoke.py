"""Every screen of the page drawn in a real browser, in French and in English, without a JavaScript error and
without « undefined », « NaN » or « [object Object] » shown: a smoke test of static/app.js, on the throwaway guide
of the tests and their fake model (nothing is billed, nothing real is touched).

The page is served by uvicorn on a free port; a headless Chrome is driven over the DevTools protocol. Chrome is
looked for where it is usually installed (or at $VW_CHROME); without it, or without `websockets`, the test is
skipped. A view that fails is caught by the router, which writes the error in the page and logs it with
console.error: both are collected here.
"""

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from test_graph import setup  # noqa: F401  (fixture: throwaway guide, fake model, watch file)
from vault_watch_agent.web import Settings, create_app

websockets = pytest.importorskip("websockets.sync.client")
uvicorn = pytest.importorskip("uvicorn")

ACT = {"X-Vault-Watch": "1"}
BAD_TEXT = ("undefined", "NaN", "[object Object]")


def find_chrome() -> str | None:
    candidates = [os.environ.get("VW_CHROME", ""), "C:/Program Files/Google/Chrome/Application/chrome.exe",
                  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    candidates += [shutil.which(n) or "" for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")]
    return next((c for c in candidates if c and Path(c).is_file()), None)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Tab:
    """One tab of the headless Chrome: calls of the DevTools protocol, and the errors it reports meanwhile."""

    def __init__(self, ws):
        self.ws, self.n, self.errors = ws, 0, []

    def note(self, message: dict) -> None:
        method, params = message.get("method"), message.get("params", {})
        if method == "Runtime.exceptionThrown":
            d = params.get("exceptionDetails", {})
            self.errors.append(f"uncaught: {(d.get('exception') or {}).get('description') or d.get('text')}"[:400])
        elif method == "Runtime.consoleAPICalled" and params.get("type") == "error":
            self.errors.append("console.error: " + " ".join(str(a.get("description") or a.get("value")) for a in params.get("args", []))[:400])

    def call(self, method: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == self.n:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})
            self.note(message)

    def js(self, expression: str):
        r = self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def settle(self, seconds: float) -> None:
        """Lets the page work for a while, collecting what it reports."""
        end = time.time() + seconds
        while time.time() < end:
            self.js("1")
            time.sleep(0.1)


@pytest.fixture
def served(setup, tmp_path):  # noqa: F811
    """The page on the throwaway guide, with a run paused at each of its steps and a check with leads to sort."""
    deps, watch, _ = setup
    app = create_app(Settings(vault=deps.vault, home=deps.home, journal=tmp_path / "usage.jsonl",
                              make_deps=lambda thread, kind: deps, list_issues=lambda: []))
    c = TestClient(app)

    def start(stop: str) -> str:
        mine = watch.with_name(f"watch-{stop}.json")  # a run is named after its watch: one copy per run
        mine.write_text(watch.read_text(encoding="utf-8"), encoding="utf-8")
        thread = c.post("/api/analyses", json={"watch_json": str(mine)}, headers=ACT).json()["thread"]
        wait(thread)
        if stop in ("retouch", "publish"):
            c.post(f"/api/runs/{thread}/review", json={"accept": ["C1"]}, headers=ACT)
            wait(thread)
        if stop == "publish":
            c.post(f"/api/runs/{thread}/retouched", json={"keep": True}, headers=ACT)
            wait(thread)
        return thread

    def wait(thread: str) -> dict:
        for _ in range(600):
            run = c.get(f"/api/runs/{thread}").json()
            if run["status"] != "running":
                return run
            time.sleep(0.05)
        raise AssertionError(f"{thread} still running")

    runs = {stop: start(stop) for stop in ("publish", "retouch", "review")}  # publish first: alone on the guide
    statuses = {stop: c.get(f"/api/runs/{t}").json() for stop, t in runs.items()}
    assert {s: r["status"] for s, r in statuses.items()} == {"review": "review", "retouch": "retouch", "publish": "publish"}, \
        {s: (r["status"], r["error"]) for s, r in statuses.items()}
    # A check of what is new, with one lead to sort
    verifs = deps.home / "verifications"
    verifs.mkdir(parents=True, exist_ok=True)
    lead = "[Newer] 03-stack/engines.md: vLLM 0.33 is now the recommended floor. Sources: https://example.org/vllm"
    (verifs / "verif-2026-11-22-120000.json").write_text(json.dumps({
        "id": "verif-2026-11-22-120000", "started": time.time() - 60, "checks": ["news"], "asked": ["news"], "cost": 0.0,
        "done": True, "results": {"news": {"ok": False, "summary": "1 lead", "findings": [lead], "excerpts": {},
                                           "fixable": True, "open": 1, "mode": "add"}}}), encoding="utf-8")

    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", runs
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def chrome(tmp_path):
    path = find_chrome()
    if not path:
        pytest.skip("no Chrome to drive (set VW_CHROME)")
    port = free_port()
    p = subprocess.Popen([path, "--headless=new", f"--remote-debugging-port={port}", "--remote-allow-origins=*",
                          f"--user-data-dir={tmp_path / 'chrome'}", "--no-first-run", "--no-default-browser-check",
                          "--window-size=1100,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                httpx.get(f"http://127.0.0.1:{port}/json/version", timeout=1)
                break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            pytest.skip("Chrome did not start")
        yield port
    finally:
        p.terminate()
        p.wait(timeout=10)


def screens(runs: dict) -> list[str]:
    return ["/", "/watches", "/runs", "/check", "/check?new", "/check/verif-2026-11-22-120000", "/sources", "/report",
            "/idea", "/links", "/languages", "/costs", "/chapters", "/settings",
            *(f"/run/{t}" for t in runs.values())]


def test_every_screen_is_drawn_without_a_javascript_error(served, chrome):
    base, runs = served
    target = httpx.put(f"http://127.0.0.1:{chrome}/json/new?about:blank").json()
    problems = []
    with websockets.connect(target["webSocketDebuggerUrl"], max_size=None) as ws:
        tab = Tab(ws)
        tab.call("Runtime.enable")
        tab.call("Page.enable")
        for lang in ("fr", "en"):
            for width in (1100, 390):  # a wide window, and a phone: the header folds under one button
                tab.call("Emulation.setDeviceMetricsOverride", width=width, height=900, deviceScaleFactor=1, mobile=width < 500)
                for screen in screens(runs):
                    tab.call("Page.navigate", url=f"{base}/?lang={lang}#{screen}")
                    tab.js(f"localStorage.setItem('vault-watch-lang', '{lang}')")
                    tab.call("Page.reload")
                    end = time.time() + 20
                    while time.time() < end and not tab.js(
                            "!!document.querySelector('#page h1, #page .error-text, dialog[open]')"
                            " && !document.querySelector('#page > p.muted:only-child')"):
                        time.sleep(0.1)
                    tab.settle(0.6)  # what a view draws after its first answer (the folder's box, a count)
                    where = f"{lang} {width}px #{screen}"
                    shown = tab.js("document.body.innerText") or ""
                    problems += [f"{where}: {e}" for e in tab.errors]
                    tab.errors.clear()
                    problems += [f"{where}: shows « {b} »" for b in BAD_TEXT if b in shown]
                    if not tab.js("!!document.querySelector('#page h1, dialog[open]')"):
                        problems.append(f"{where}: no title drawn: {shown[:200]!r}")
                # The menu « Watch » opened on a wide window
                if width > 500:
                    tab.js("document.querySelector('#watch-menu').open = true")
                    tab.settle(0.3)
                    problems += [f"{lang} menu: {e}" for e in tab.errors]
                    tab.errors.clear()
    httpx.get(f"http://127.0.0.1:{chrome}/json/close/{target['id']}")
    assert not problems, "\n".join(problems)
