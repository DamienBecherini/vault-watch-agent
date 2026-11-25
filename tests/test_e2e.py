"""The editor's journeys through the page, clicked in a real browser by Playwright (asked by the user, 2026-11-22 and
2026-11-25): review and apply, retouch a correction, correct a page at the publish pause, the leads of a check turned
into a run, the Settings, the language. On the throwaway guide of the tests and their fake model: nothing is billed,
nothing real is touched.

Marked `e2e`: left out of `pytest` by default (pyproject.toml), run with `pytest -m e2e`. They drive the Chrome
installed on the machine (or $VW_CHROME) and need the extra `e2e` (`pip install -e ".[e2e]"`); without either, they
are skipped. test_page_smoke.py draws every screen once; these click through them."""

import json
import re
import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_graph import setup  # noqa: F401  (fixture: throwaway guide, fake model, watch file)
from test_page_smoke import find_chrome, free_port

from vault_watch_agent import explain
from vault_watch_agent.web import Settings, create_app

pytestmark = pytest.mark.e2e
sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

ACT = {"X-Vault-Watch": "1"}
PAGE = "03-stack/engines.md"
LEAD = "[Newer] 03-stack/engines.md: vLLM 0.33 is now the recommended floor. Sources: https://example.org/vllm"


class Site:
    """The page served on a free port, its API for what a journey does not click, and a browser tab on it."""

    def __init__(self, base: str, client: TestClient, watch: Path, page, vault: Path):
        self.base, self.c, self.watch, self.page, self.vault = base, client, watch, page, vault

    def run(self, stop: str = "review") -> str:
        """A watch run of the fake model, paused at `stop` (review, retouch or publish)."""
        mine = self.watch.with_name(f"watch-{stop}-{time.monotonic_ns()}.json")
        mine.write_text(self.watch.read_text(encoding="utf-8"), encoding="utf-8")
        thread = self.c.post("/api/analyses", json={"watch_json": str(mine)}, headers=ACT).json()["thread"]
        self.wait(thread)
        if stop in ("retouch", "publish"):
            self.c.post(f"/api/runs/{thread}/review", json={"accept": ["C1"]}, headers=ACT)
            self.wait(thread)
        if stop == "publish":
            self.c.post(f"/api/runs/{thread}/retouched", json={"keep": True}, headers=ACT)
            self.wait(thread)
        return thread

    def wait(self, thread: str, until: str | None = None) -> dict:
        """The run once it no longer runs (or once its status is `until`)."""
        for _ in range(1200):
            run = self.c.get(f"/api/runs/{thread}").json()
            if (run["status"] == until) if until else run["status"] != "running":
                return run
            time.sleep(0.05)
        raise AssertionError(f"{thread}: {run['status']} {run.get('error')}")

    def open(self, screen: str) -> None:
        self.page.goto(f"{self.base}/#{screen}")
        self.page.wait_for_selector("#page h1")


@pytest.fixture
def site(setup, tmp_path, monkeypatch):  # noqa: F811
    path = find_chrome()
    if not path:
        pytest.skip("no Chrome to drive (set VW_CHROME)")
    deps, watch, _ = setup
    # The explanations of a pause in French are a model call the fake model does not answer (test_explain.py tests
    # them): here the lines stay in English, as when the model fails
    monkeypatch.setattr(explain, "lines", lambda texts, lang, llm, home: ({}, []))
    app = create_app(Settings(vault=deps.vault, home=deps.home, journal=tmp_path / "usage.jsonl",
                              make_deps=lambda thread, kind: deps, list_issues=lambda: []))
    verifs = deps.home / "verifications"
    verifs.mkdir(parents=True, exist_ok=True)
    (verifs / "verif-2026-11-25-120000.json").write_text(json.dumps({
        "id": "verif-2026-11-25-120000", "started": time.time() - 60, "checks": ["news"], "asked": ["news"], "cost": 0.0,
        "done": True, "results": {"news": {"ok": False, "summary": "1 lead", "findings": [LEAD], "excerpts": {},
                                           "fixable": True, "open": 1, "mode": "add"}}}), encoding="utf-8")
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    runner = threading.Thread(target=server.run, daemon=True)
    runner.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    errors: list[str] = []
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=path, headless=True)
        context = browser.new_context(viewport={"width": 1100, "height": 900}, locale="fr-FR")
        context.add_init_script("try { localStorage.setItem('vault-watch-lang', 'fr'); } catch (e) {}")
        page = context.new_page()
        page.set_default_timeout(20_000)
        page.on("pageerror", lambda e: errors.append(f"uncaught: {e}"))
        page.on("console", lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)
        page.on("dialog", lambda d: d.accept())  # « Are you sure? »: yes
        yield Site(f"http://127.0.0.1:{port}", TestClient(app), watch, page, deps.vault)
        browser.close()
    server.should_exit = True
    runner.join(timeout=10)
    assert not errors, errors


def test_review_apply_skip_the_retouches_and_decline_to_publish(site):
    thread = site.run("review")
    site.open(f"/run/{thread}")
    p = site.page
    p.wait_for_selector("input[data-id]", state="attached")
    # What the editor clicks: a group's own box (the boxes of its corrections are hidden), or a correction's alone
    boxes = [b for b in p.locator("[data-group-box], input[data-id]").all() if b.is_visible() and b.is_enabled()]
    assert boxes
    for box in boxes:
        box.uncheck()
    assert p.locator("#apply").is_disabled()  # nothing ticked: nothing to apply
    group = p.locator('[data-group-box="C1"]')
    (group if group.count() else p.locator('input[data-id="C1"]')).check()
    ticked = p.locator("input[data-id]:checked").count()
    assert ticked >= 1 and re.search(rf"\b{ticked}\b", p.locator("#apply").inner_text())
    p.click("#apply")
    p.wait_for_selector("#skip")  # the pause to retouch the pages
    p.click("#skip")
    site.wait(thread, "publish")
    p.reload()
    p.wait_for_selector("#yes")
    checks = p.locator(".pub-checks").inner_text()
    assert "Contrôles du guide" in checks and "Notes de bas de page" in checks
    p.click("#no")  # confirm() accepted by the fixture
    assert site.wait(thread)["status"] == "not-published"


def test_a_correction_retouched_at_the_review_is_what_is_applied(site):
    thread = site.run("review")
    site.open(f"/run/{thread}")
    p = site.page
    p.locator('[data-retouch-open="C1"]').click()
    box = p.locator('textarea[data-text="C1"]')
    box.wait_for()
    text = box.input_value() + " Retouché à la main."
    box.fill(text)
    p.wait_for_function("() => document.querySelector('[data-diff=\"C1\"]').textContent.includes('Retouché à la main')")
    p.click("#apply")
    p.wait_for_selector("#skip")
    page_text = site.c.get(f"/api/runs/{thread}/page", params={"path": PAGE}).json()["text"]
    assert "Retouché à la main." in page_text


def test_a_page_corrected_at_the_publish_pause_is_committed_and_checked_again(site):
    thread = site.run("publish")
    site.open(f"/run/{thread}")
    p = site.page
    p.wait_for_selector("#yes")
    p.locator("[data-correct]").first.click()
    source = p.locator('textarea[data-text-of="0"]')
    source.wait_for()
    source.fill(source.input_value().rstrip("\n") + "\n\nCorrigé à la publication.\n")
    mirror = p.locator('textarea[data-text-of="1"]')
    if mirror.count():
        mirror.fill(mirror.input_value().rstrip("\n") + "\n\nCorrected at the publish pause.\n")
    p.locator("[data-save]").first.click()
    p.locator("[data-check-only]").click()
    run = site.wait(thread, "publish")
    log = subprocess.run(["git", "log", "-3", "--format=%s", run["branch"]], cwd=site.vault, capture_output=True, text=True).stdout
    assert "Corrected at the publish review" in log


def test_a_lead_ticked_on_a_check_becomes_an_addition_run(site):
    site.open("/check/verif-2026-11-25-120000")
    p = site.page
    lead = p.locator("input[data-lead]").first
    lead.check()
    fix = p.locator("#fix")
    p.wait_for_function("() => !document.querySelector('#fix').disabled")
    assert "$" in fix.inner_text() or "€" in fix.inner_text()  # its estimate
    fix.click()
    p.wait_for_url(re.compile(r"#/run/add-\d{4}-\d{2}-\d{2}-\d{4}"))
    thread = p.url.split("#/run/")[1]
    assert site.c.get(f"/api/runs/{thread}").json()["thread"] == thread


def test_a_candidate_added_dismissed_with_its_reason_then_proposed(site):
    site.open("/candidates")
    p = site.page
    p.fill("#c-name", "Larkdb 3")
    p.fill("#c-url", "https://example.org/larkdb-3")
    p.select_option("#c-kind", "tool")
    p.click("#c-add")
    p.wait_for_selector("[data-card='larkdb-3']")
    assert "Larkdb 3" in p.inner_text("#draft")  # a change to publish
    # Dismissed: refused without a reason, kept with one and a date to look again
    p.click("[data-card='larkdb-3'] [data-act='dismissed']")
    p.click("[data-card='larkdb-3'] [data-f='ok']")
    p.wait_for_function("() => document.querySelector(\"[data-card='larkdb-3'] [data-f='error']\").textContent.includes('raison')")
    p.fill("[data-card='larkdb-3'] [data-f='reason']", "closed beta")
    p.fill("[data-card='larkdb-3'] [data-f='recheck']", "2999-01-01")
    p.click("[data-card='larkdb-3'] [data-f='ok']")
    p.wait_for_selector("[data-card='larkdb-3'] .badge >> text=Écarté")
    assert "closed beta" in p.inner_text("[data-card='larkdb-3']")
    # Proposed: « Propose an addition » with its line, the run started marks it proposed
    p.click("[data-propose='larkdb-3']")
    p.wait_for_url(re.compile(r"#/idea$"))
    p.wait_for_selector("#for-candidate")
    assert "https://example.org/larkdb-3" in p.input_value("#text")
    p.click("#send")
    p.wait_for_url(re.compile(r"#/run/add-"))
    thread = p.url.split("#/run/")[1]
    lark = next(c for c in site.c.get("/api/candidates").json()["candidates"] if c["id"] == "larkdb-3")
    assert (lark["state"], lark["reason"]) == ("proposed", f"run {thread}")


def test_the_settings_open_save_and_the_language_switches(site):
    site.open("/")
    p = site.page
    p.locator('[data-tool="settings"]').first.click()
    p.wait_for_selector("#settings-dialog[open]")
    p.wait_for_selector("#settings-save")
    assert p.locator("#settings-save").is_disabled()  # nothing changed: nothing to save
    p.click("#settings-cancel")
    p.wait_for_selector("#settings-dialog[open]", state="detached")
    p.locator('button[data-lang="en"]').first.click()
    p.wait_for_function("() => document.documentElement.lang === 'en'")
    assert p.evaluate("localStorage.getItem('vault-watch-lang')") == "en"
