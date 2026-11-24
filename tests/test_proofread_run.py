"""What the editor writes during a run, proofread when they ask (proofread.py inside the graph): their retouches before
the mirrors follow them, or what they corrected at the publish pause. The model is called once, before the pause on
its fixes; the fixes accepted are committed as the editor's; nothing asked, nothing called."""

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from test_graph import FakeLLM, setup  # noqa: F401  (fixture: throwaway guide, fake model, watch file)
from vault_watch_agent import proofread, vault
from vault_watch_agent.graph import build, pr_body
from vault_watch_agent.state import MirrorEdit, MirrorResult
from vault_watch_agent.web import Settings, create_app

PAGE = "03-stack/engines.md"
ACT = {"X-Vault-Watch": "1"}


class Proofreader(FakeLLM):
    """The fake model of the graph's tests, which also proofreads: a typo in what the editor wrote, a doubt."""

    def parse(self, *, system, prompt, schema, effort, node, context=None, web=False):
        usage = {"node": node, "model": "fake", "input": 10, "output": 5, "cache_read": 0, "cost_usd": 0.01}
        if schema is proofread.Fixes:
            self.calls.append(node)
            if node == "proofread spelling":
                assert "pour comencer" in prompt and "<after>" in prompt  # the editor's passage, as written now
                assert "0.31" not in prompt  # the corrections of the run (0.31 → 0.33) are not the editor's: not proofread
                return proofread.Fixes(fixes=[
                    proofread.Fix(page=PAGE, current="pour comencer", proposed="pour commencer", reason="typo")]), usage
            assert node == "proofread facts" and web
            return proofread.Fixes(fixes=[], notes=[f"{PAGE}: no source for « le plus simple »"]), usage
        if schema is MirrorResult and "0.33 is the recommended" in prompt:  # translated again, from the publish pause
            self.calls.append(node)
            return MirrorResult(problem="", edits=[MirrorEdit(current="Ollama remains the easiest way to start.",
                                                              proposed="Ollama remains the simplest way to begin.")]), usage
        return super().parse(system=system, prompt=prompt, schema=schema, effort=effort, node=node, context=context, web=web)


def git_out(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def at_retouch(deps, watch, thread):
    graph = build(deps, InMemorySaver())
    config = {"configurable": {"thread_id": thread}}
    graph.invoke({"source": str(watch), "issue": None}, config)
    graph.invoke(Command(resume=["C1"]), config)
    pause = graph.get_state(config).tasks[0].interrupts[0].value
    assert pause["step"] == "retouch"
    return graph, config, Path(pause["worktree"])


def with_typo(wt: Path) -> None:
    page = wt / PAGE
    vault.write(page, vault.read(page).replace("pour démarrer", "pour comencer"))


def pause_of(graph, config) -> dict:
    return graph.get_state(config).tasks[0].interrupts[0].value


def test_the_retouches_proofread_then_the_fixes_accepted_committed_as_the_editors(setup):  # noqa: F811
    deps, watch, _ = setup
    deps.llm = llm = Proofreader()
    graph, config, wt = at_retouch(deps, watch, "p1")
    with_typo(wt)
    graph.invoke(Command(resume={"action": "done", "proofread": ["spelling", "facts", "made-up"]}), config)
    pause = pause_of(graph, config)
    assert pause["step"] == "proofread" and [f["id"] for f in pause["fixes"]] == ["F1"]
    assert pause["notes"] == [f"{PAGE}: no source for « le plus simple »"]
    assert llm.calls.count("proofread spelling") == 1 and llm.calls.count("proofread facts") == 1
    assert not any(c.startswith("mirror") for c in llm.calls)  # the mirrors wait for the editor's answer

    graph.invoke(Command(resume=["F1"]), config)
    assert pause_of(graph, config)["step"] == "publish"
    assert llm.calls.count("proofread spelling") == 1  # not called again when the pause resumed
    assert "pour commencer" in vault.read(wt / PAGE)
    log = git_out(wt, "log", "--format=%s|%an", "-4").splitlines()
    assert "Proofread fixes accepted|t" in log and "Retouches at the review|t" in log  # the editor's own identity
    assert log.index("Proofread fixes accepted|t") < log.index("Retouches at the review|t")  # before the mirrors' commit
    state = graph.get_state(config).values
    assert state["proofread_log"] == [{"checks": ["spelling", "facts"], "fixes": 1, "applied": 1, "from": "retouch"}]
    assert "The editor's edits proofread (spelling, facts): 1 fix(es) proposed, 1 accepted." in pr_body(state)


def test_nothing_asked_or_nothing_retouched_calls_nothing(setup):  # noqa: F811
    deps, watch, _ = setup
    deps.llm = llm = Proofreader()
    graph, config, wt = at_retouch(deps, watch, "p2")
    graph.invoke(Command(resume={"action": "done", "proofread": ["spelling"]}), config)  # asked, nothing retouched
    assert pause_of(graph, config)["step"] == "publish"
    other = watch.with_name("watch-other.json")  # a run of its own, on a branch of its own
    other.write_text(watch.read_text(encoding="utf-8"), encoding="utf-8")
    graph2, config2, wt2 = at_retouch(deps, other, "p3")
    with_typo(wt2)
    graph2.invoke(Command(resume="done"), config2)  # retouched, nothing asked
    assert pause_of(graph2, config2)["step"] == "publish"
    assert not any(c.startswith("proofread") for c in llm.calls)


def test_at_the_publish_pause_what_was_corrected_is_proofread_then_translated_and_checked(setup):  # noqa: F811
    deps, watch, _ = setup
    deps.llm = llm = Proofreader()
    graph, config, wt = at_retouch(deps, watch, "p4")
    graph.invoke(Command(resume="skip"), config)
    assert pause_of(graph, config)["step"] == "publish"
    with_typo(wt)  # corrected on the page at the publish pause
    calls = len(llm.calls)
    graph.invoke(Command(resume={"action": "proofread", "checks": ["spelling"]}), config)
    assert pause_of(graph, config)["step"] == "proofread" and llm.calls[calls:] == ["proofread spelling"]
    graph.invoke(Command(resume={"accepted": ["F1"], "edits": {"F1": "pour bien commencer"}}), config)  # retouched
    pause = pause_of(graph, config)
    assert pause["step"] == "publish" and pause["audit_ok"]
    assert llm.calls[calls:] == ["proofread spelling", "mirror en/03-stack/engines.md"]  # the French changed: translated
    assert "pour bien commencer" in vault.read(wt / PAGE)
    assert "simplest way to begin" in vault.read(wt / "en" / PAGE)
    subjects = git_out(wt, "log", "--format=%s", "-4").splitlines()
    assert subjects[:3] == ["chore(i18n): sync the mirrors with the source pages", "Proofread fixes accepted",
                            "Corrected at the publish review"]


def test_a_fix_of_the_mirror_only_goes_straight_to_the_checks(setup):  # noqa: F811
    deps, watch, _ = setup
    deps.llm = llm = Proofreader()
    graph, config, wt = at_retouch(deps, watch, "p5")
    graph.invoke(Command(resume="skip"), config)
    english = wt / "en" / PAGE
    vault.write(english, vault.read(english).replace("easiest way", "easyest way"))  # the translation only
    calls = len(llm.calls)
    graph.invoke(Command(resume={"action": "proofread", "checks": ["spelling"]}), config)
    assert pause_of(graph, config)["step"] == "publish"  # no source page changed: nothing to proofread, nothing to translate
    assert llm.calls[calls:] == []


def test_the_server_offers_the_checks_and_takes_the_answer(setup, tmp_path):  # noqa: F811
    deps, watch, _ = setup
    deps.llm = Proofreader()
    c = TestClient(create_app(Settings(vault=deps.vault, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    from test_web import wait

    thread = c.post("/api/analyses", json={"watch_json": str(watch)}, headers=ACT).json()["thread"]
    wait(c, thread)
    assert c.get(f"/api/runs/{thread}/proofread/estimate").status_code == 409  # not at the retouches yet
    c.post(f"/api/runs/{thread}/review", json={"accept": ["C1"]}, headers=ACT)
    run = wait(c, thread)
    assert run["status"] == "retouch"
    none = c.get(f"/api/runs/{thread}/proofread/estimate").json()
    assert none["pages"] == [] and set(none["usd"]) == {"spelling", "facts", "consistency"}
    text = c.get(f"/api/runs/{thread}/page", params={"path": PAGE}).json()["text"]
    c.post(f"/api/runs/{thread}/page", json={"path": PAGE, "text": text.replace("pour démarrer", "pour comencer")}, headers=ACT)
    estimate = c.get(f"/api/runs/{thread}/proofread/estimate").json()
    assert estimate["pages"] == [PAGE] and estimate["usd"]["facts"] > estimate["usd"]["spelling"] > 0
    assert c.post(f"/api/runs/{thread}/retouched", json={"keep": True, "proofread": ["typos"]}, headers=ACT).status_code == 400
    c.post(f"/api/runs/{thread}/retouched", json={"keep": True, "proofread": ["spelling"]}, headers=ACT)
    run = wait(c, thread)
    assert run["status"] == "proofread" and [f["id"] for f in run["proofread_fixes"]] == ["F1"]
    assert run["proofread_fixes"][0]["current"] == "pour comencer"  # the page shows the fix whole
    assert c.post(f"/api/runs/{thread}/proofread", json={"ids": ["F1"]}, headers=ACT).status_code == 200
    run = wait(c, thread)
    assert run["status"] == "publish" and run["proofread_fixes"][0]["applied"]
    assert run["proofread_log"][0]["applied"] == 1
    assert "pour commencer" in c.get(f"/api/runs/{thread}/diff").text
    # At the publish pause: refused while nothing was corrected, or without a check
    assert c.post(f"/api/runs/{thread}/publish", json={"action": "proofread", "checks": ["spelling"]}, headers=ACT).status_code == 400
    text = c.get(f"/api/runs/{thread}/page", params={"path": PAGE}).json()["text"]
    c.post(f"/api/runs/{thread}/page", json={"path": PAGE, "text": text.replace("pour commencer", "pour comencer")}, headers=ACT)
    assert c.post(f"/api/runs/{thread}/publish", json={"action": "proofread", "checks": []}, headers=ACT).status_code == 400
    assert c.get(f"/api/runs/{thread}/proofread/estimate").json()["pages"] == [PAGE]
    assert c.post(f"/api/runs/{thread}/publish", json={"action": "proofread", "checks": ["spelling"]}, headers=ACT).status_code == 200
    assert wait(c, thread)["status"] == "proofread"
    assert c.post(f"/api/runs/{thread}/proofread", json={"ids": []}, headers=ACT).status_code == 200  # none accepted
    assert wait(c, thread)["status"] == "publish"
