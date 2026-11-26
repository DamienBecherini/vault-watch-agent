"""A proposal retouched in the review (H2): the editor's text applied, the model's kept beside it, the free checks run
again on it, the report and the pull request saying so; the server checks a retouch before the review is sent."""

from pathlib import Path

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from test_graph import setup  # noqa: F401  (fixture: throwaway guide, fake model, watch file)

from vault_watch_agent.graph import build, pr_body, retouchable, retouched
from vault_watch_agent.web import Settings, create_app

MINE = "vLLM 0.33 est désormais la version minimale recommandée (novembre 2026)[^1]."


def paused(deps, watch, thread="r1"):
    graph = build(deps, InMemorySaver())
    config = {"configurable": {"thread_id": thread}}
    graph.invoke({"source": str(watch), "issue": None}, config)
    return graph, config


def test_a_retouched_proposal_is_applied_and_the_models_text_kept(setup):  # noqa: F811
    deps, watch, llm = setup
    graph, config = paused(deps, watch)
    model_text = next(c for c in graph.get_state(config).values["corrections"] if c["id"] == "C1")["proposed"]

    graph.invoke(Command(resume={"accepted": ["C1"], "edits": {"C1": MINE}}), config)
    state = graph.get_state(config).values
    c1 = next(c for c in state["corrections"] if c["id"] == "C1")
    assert c1["edited"] and c1["proposed"] == MINE and c1["proposed_model"] == model_text and c1["check"] == "ok"
    assert state["applied"] == ["C1", "C3", "C5"]  # its group goes with it, as before
    page = (Path(state["worktree"]) / "03-stack" / "engines.md").read_text(encoding="utf-8")
    assert MINE in page and model_text not in page
    report = Path(state["report_path"]).read_text(encoding="utf-8")
    assert "## Retouched at the review" in report and MINE in report and model_text in report
    body = pr_body(state)
    assert "| C1 ✍️ |" in body and "1 correction(s) retouched by the editor" in body
    assert "| C3 |" in body  # not retouched: no mark


def test_the_free_checks_run_again_on_a_retouch(setup):  # noqa: F811
    deps, watch, _ = setup
    graph, config = paused(deps, watch, "r2")
    corrections = graph.get_state(config).values["corrections"]
    c1 = next(c for c in corrections if c["id"] == "C1")
    c3 = next(c for c in corrections if c["id"] == "C3")
    c2 = next(c for c in corrections if c["id"] == "C2")
    assert retouchable(c1) and not retouchable(c2)  # C2's quote is not in the page: no text mends that

    same = retouched(deps.vault, corrections, {"C1": c1["current"]})
    assert next(c for c in same if c["id"] == "C1")["check"] == "no change"
    dropped = retouched(deps.vault, corrections, {"C3": ""})  # removes the footnote definition: its group does not put it back
    assert next(c for c in dropped if c["id"] == "C3")["check"].startswith("drops footnote")
    ignored = retouched(deps.vault, corrections, {"C2": "whatever", "C1": c1["proposed"]})
    assert ignored == [dict(c) for c in corrections]  # not retouchable, or the same text: nothing changes
    sourced = retouched(deps.vault, corrections, {"C1": "vLLM 0.35 est la version minimale recommandée[^1]."})
    assert "0.35" in next(c for c in sourced if c["id"] == "C1")["warning"]  # a version none of its footnotes mentions
    assert c3["check"] == "ok" and "edited" not in c1  # the state itself is not changed by a check


def test_the_server_checks_a_retouch_then_sends_it(setup, tmp_path):  # noqa: F811
    deps, watch, _ = setup
    c = TestClient(create_app(Settings(vault=deps.vault, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    act = {"X-Vault-Watch": "1"}
    thread = c.post("/api/analyses", json={"watch_json": str(watch)}, headers=act).json()["thread"]
    from test_web import wait

    run = wait(c, thread)
    flags = {x["id"]: x["retouchable"] for x in run["corrections"]}
    assert flags["C1"] and not flags["C2"] and not flags["C4"]  # C4: in conflict with C1
    checked = c.post(f"/api/runs/{thread}/retouch", json={"edits": {"C1": "vLLM 0.31 est la version minimale recommandée[^1]."}},
                     headers=act).json()
    assert checked == {"C1": {"check": "no change", "warning": ""}}  # the page already says that
    c.post(f"/api/runs/{thread}/review", json={"accept": ["C1"], "edits": {"C1": MINE}}, headers=act)
    run = wait(c, thread)
    c.post(f"/api/runs/{thread}/retouched", json={"keep": False}, headers=act)  # H3: nothing more retouched
    run = wait(c, thread)
    assert run["status"] == "publish" and MINE in c.get(f"/api/runs/{thread}/diff").text
    assert next(x for x in run["corrections"] if x["id"] == "C1")["edited"]


# -- H3: the pause to retouch the pages of the branch, before the mirrors -------------------------------------

import subprocess  # noqa: E402

from vault_watch_agent import vault  # noqa: E402

BY_HAND = "Ollama reste le plus simple pour démarrer, sur un poste seul."


def git_out(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def test_retouched_in_the_worktree_then_the_mirror_follows(setup):  # noqa: F811
    deps, watch, llm = setup
    graph, config = paused(deps, watch, "r3")
    graph.invoke(Command(resume=["C1"]), config)
    pause = graph.get_state(config).tasks[0].interrupts[0].value
    assert pause["step"] == "retouch"
    page = Path(pause["worktree"]) / "03-stack" / "engines.md"
    text = vault.read(page)
    vault.write(page, text.replace(text[text.index("Ollama reste"):text.index("\n", text.index("Ollama reste"))].rstrip("\r"),
                                   BY_HAND))
    graph.invoke(Command(resume="done"), config)
    state = graph.get_state(config).values
    assert state["retouched"] == ["03-stack/engines.md"]
    assert git_out(Path(state["worktree"]), "log", "--format=%s", "-3").splitlines()[1] == "Retouches at the review"
    assert BY_HAND in vault.read(Path(state["worktree"]) / "03-stack" / "engines.md")
    assert "Retouched by the editor before the mirrors: `03-stack/engines.md`" in pr_body(state)
    assert "0.31" in vault.read(deps.vault / "03-stack" / "engines.md")  # the guide's folder: untouched


def test_the_folder_lent_with_a_draft_set_aside_and_put_back(setup, tmp_path):  # noqa: F811
    deps, watch, _ = setup
    folder = deps.vault
    (folder / "brouillon.md").write_text("une idée pas finie\n", encoding="utf-8")  # a draft of the editor, new
    c = TestClient(create_app(Settings(vault=folder, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    act = {"X-Vault-Watch": "1"}
    from test_web import wait

    thread = c.post("/api/analyses", json={"watch_json": str(watch)}, headers=act).json()["thread"]
    wait(c, thread)
    c.post(f"/api/runs/{thread}/review", json={"accept": ["C1"]}, headers=act)
    assert wait(c, thread)["status"] == "retouch"
    seen = c.get(f"/api/runs/{thread}/folder").json()
    assert seen["branch"] == "main" and seen["changes"] == ["brouillon.md"] and seen["lent_to"] == ""
    assert c.post(f"/api/runs/{thread}/folder", json={}, headers=act).status_code == 409  # a draft: not without asking
    assert c.post(f"/api/runs/{thread}/folder", json={"set_aside": True}, headers=act).status_code == 200
    assert not (folder / "brouillon.md").exists()  # set aside
    assert "vLLM 0.33" in vault.read(folder / "03-stack" / "engines.md")  # the folder shows the branch, as Obsidian will
    assert c.get("/api/folder/aside").json() == [{"thread": thread, "lent": True, "aside": ["brouillon.md"]}]

    # Retouched in Obsidian (the folder), and in the page of the agent: both land in the folder
    page = folder / "03-stack" / "engines.md"
    vault.write(page, vault.read(page).replace("Ollama reste le plus simple pour démarrer", "Ollama reste le plus simple"))
    read = c.get(f"/api/runs/{thread}/page", params={"path": "03-stack/engines.md"}).json()
    assert read["in"] == "folder" and "Ollama reste le plus simple (" in read["text"]
    c.post(f"/api/runs/{thread}/page", json={"path": "03-stack/engines.md",
                                             "text": read["text"].replace("Ollama reste le plus simple", BY_HAND[:-1])}, headers=act)
    assert c.post(f"/api/runs/{thread}/page", json={"path": "../x.md", "text": "x"}, headers=act).status_code == 400
    assert c.get(f"/api/runs/{thread}/page", params={"path": "scripts/run-audits.mjs"}).status_code == 400

    c.post(f"/api/runs/{thread}/retouched", json={"keep": True}, headers=act)
    run = wait(c, thread)
    assert run["status"] == "publish" and run["retouched"] == ["03-stack/engines.md"]
    assert git_out(folder, "rev-parse", "--abbrev-ref", "HEAD") == "main"  # given back
    assert (folder / "brouillon.md").read_text(encoding="utf-8") == "une idée pas finie\n"  # put back, untouched
    assert c.get("/api/folder/aside").json() == [] and git_out(folder, "stash", "list") == ""
    assert "0.31" in vault.read(folder / "03-stack" / "engines.md")  # main itself: unchanged until the merge
    log = git_out(folder, "log", "--format=%s|%an", f"main..{run['branch']}").splitlines()
    assert "Retouches at the review|t" in log  # as the editor: the folder's own identity
    assert BY_HAND[:-1] in c.get(f"/api/runs/{thread}/diff").text


def test_the_folder_taken_back_keeps_its_retouches_and_can_be_lent_again(setup, tmp_path):  # noqa: F811
    deps, watch, _ = setup
    folder = deps.vault
    c = TestClient(create_app(Settings(vault=folder, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    act = {"X-Vault-Watch": "1"}
    from test_web import wait

    thread = c.post("/api/analyses", json={"watch_json": str(watch)}, headers=act).json()["thread"]
    wait(c, thread)
    c.post(f"/api/runs/{thread}/review", json={"accept": ["C1"]}, headers=act)
    wait(c, thread)
    assert c.post(f"/api/runs/{thread}/folder/back", json={}, headers=act).status_code == 409  # not lent
    assert c.post(f"/api/runs/{thread}/folder", json={}, headers=act).status_code == 200
    page = folder / "03-stack" / "engines.md"
    vault.write(page, vault.read(page).replace("Ollama reste le plus simple pour démarrer", "Ollama reste le plus simple"))
    assert c.post(f"/api/runs/{thread}/folder/back", json={}, headers=act).json()["commit"]
    assert git_out(folder, "rev-parse", "--abbrev-ref", "HEAD") == "main" and c.get(f"/api/runs/{thread}").json()["status"] == "retouch"
    assert "plus simple pour démarrer" in vault.read(page)  # main, as it was
    read = c.get(f"/api/runs/{thread}/page", params={"path": "03-stack/engines.md"}).json()
    assert read["in"] == "worktree" and "Ollama reste le plus simple (" in read["text"]  # kept on the run's branch
    assert c.post(f"/api/runs/{thread}/folder", json={}, headers=act).status_code == 200  # lent again, retouch included
    assert "Ollama reste le plus simple (" in vault.read(page)
    c.post(f"/api/runs/{thread}/retouched", json={"keep": True}, headers=act)
    run = wait(c, thread)
    assert run["status"] == "publish" and run["retouched"] == ["03-stack/engines.md"]
    assert git_out(folder, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_skipped_after_the_folder_was_taken_back_drops_its_retouches(setup, tmp_path):  # noqa: F811
    deps, watch, _ = setup
    folder = deps.vault
    c = TestClient(create_app(Settings(vault=folder, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    act = {"X-Vault-Watch": "1"}
    from test_web import wait

    thread = c.post("/api/analyses", json={"watch_json": str(watch)}, headers=act).json()["thread"]
    wait(c, thread)
    c.post(f"/api/runs/{thread}/review", json={"accept": ["C1"]}, headers=act)
    wait(c, thread)
    c.post(f"/api/runs/{thread}/folder", json={}, headers=act)
    page = folder / "03-stack" / "engines.md"
    vault.write(page, vault.read(page).replace("Ollama", "Olama"))  # a slip, committed when the folder is taken back
    c.post(f"/api/runs/{thread}/folder/back", json={}, headers=act)
    c.post(f"/api/runs/{thread}/retouched", json={"keep": False}, headers=act)
    run = wait(c, thread)
    assert run["status"] == "publish" and run["retouched"] == []
    assert "Olama" not in c.get(f"/api/runs/{thread}/diff").text


def test_skipped_retouches_are_dropped_and_the_folder_given_back(setup, tmp_path):  # noqa: F811
    deps, watch, _ = setup
    folder = deps.vault
    c = TestClient(create_app(Settings(vault=folder, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    act = {"X-Vault-Watch": "1"}
    from test_web import wait

    thread = c.post("/api/analyses", json={"watch_json": str(watch)}, headers=act).json()["thread"]
    wait(c, thread)
    c.post(f"/api/runs/{thread}/review", json={"accept": ["C1"]}, headers=act)
    wait(c, thread)
    assert c.post(f"/api/runs/{thread}/folder", json={}, headers=act).status_code == 200  # clean: lent at once
    page = folder / "03-stack" / "engines.md"
    vault.write(page, vault.read(page).replace("Ollama", "Olama"))  # a slip
    c.post(f"/api/runs/{thread}/retouched", json={"keep": False}, headers=act)
    run = wait(c, thread)
    assert run["status"] == "publish" and run["retouched"] == []
    assert git_out(folder, "status", "--porcelain") == "" and git_out(folder, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert "Olama" not in c.get(f"/api/runs/{thread}/diff").text


def test_at_the_publish_pause_a_page_is_corrected_checked_again_and_translated_again(setup, tmp_path):  # noqa: F811
    deps, watch, llm = setup
    c = TestClient(create_app(Settings(vault=deps.vault, home=deps.home, journal=tmp_path / "usage.jsonl",
                                       make_deps=lambda thread, kind: deps, list_issues=lambda: [])))
    act = {"X-Vault-Watch": "1"}
    from test_web import wait

    thread = c.post("/api/analyses", json={"watch_json": str(watch)}, headers=act).json()["thread"]
    wait(c, thread)
    c.post(f"/api/runs/{thread}/review", json={"accept": ["C1"]}, headers=act)
    wait(c, thread)
    c.post(f"/api/runs/{thread}/retouched", json={"keep": False}, headers=act)
    run = wait(c, thread)
    assert run["status"] == "publish"
    # What the page shows there: the titles of the pages, and what translating a page again would cost
    assert run["titles"]["03-stack/engines.md"] == "Moteurs d'inférence" and set(run["retranslate_usd"]) == {"03-stack/engines.md"}
    assert c.post(f"/api/runs/{thread}/publish", json={"action": "retranslate", "pages": []}, headers=act).status_code == 400

    # A sentence corrected on the page, then checked again: committed as the editor's, back at the same pause
    page = "03-stack/engines.md"
    text = c.get(f"/api/runs/{thread}/page", params={"path": page}).json()["text"]
    c.post(f"/api/runs/{thread}/page", json={"path": page, "text": text.replace("Ollama reste le plus simple",
                                                                               "Ollama reste vraiment le plus simple")}, headers=act)
    c.post(f"/api/runs/{thread}/publish", json={"action": "recheck"}, headers=act)
    run = wait(c, thread)
    # Once in the whole suite (2026-11-26), back at « publish » with no pause: the job's error says why, if it failed
    assert run["status"] == "publish" and run["pause"], (run.get("error"), (run.get("job") or {}).get("events", [])[-3:])
    assert run["pause"]["audit_ok"]
    assert "vraiment" in c.get(f"/api/runs/{thread}/diff").text
    assert "Corrected at the publish review" in git_out(Path(run["pause"]["worktree"]) if run["pause"].get("worktree")
                                                         else deps.vault, "log", "--format=%s", f"main..{run['branch']}")

    # The English page started over: translated again from the base, one call, back at the same pause
    calls = len(llm.calls)
    c.post(f"/api/runs/{thread}/publish", json={"action": "retranslate", "pages": [page], "fresh": True}, headers=act)
    run = wait(c, thread)
    assert run["status"] == "publish" and llm.calls[calls:] == ["mirror en/03-stack/engines.md"]
    assert "vLLM 0.33 is the recommended minimum version (November 2026)" in c.get(f"/api/runs/{thread}/diff").text
    assert run["mirrored"] == ["en/03-stack/engines.md"] and len(run["mirror_pairs"]) == 1
