"""The nodes of the review and of the branch: the human review (interrupt) → apply on a branch → the editor's
retouches (interrupt) → their proofreading, if asked (the model calls, then the pause on what they found).

A node that calls `interrupt()` runs again from its start when the run resumes: the model calls of a proofreading are
made in `proofread_node`, and the pause on their fixes is `proofread_review`, so that they are made once."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from langgraph.types import interrupt

from . import compact, forge, inputs, mirrors, news, proofread, retouch, vault
from .graph_common import git, watch_branch
from .graph_corrections import note_retouches, retouched
from .graph_text import has_members, largest_first, pr_title
from .state import WatchState

if TYPE_CHECKING:
    from .graph_common import Deps


def split_answer(answer: Any) -> tuple[dict, Any]:
    """An answer to a review pause: {'accepted': …, 'edits': {id: text}}, or the accepted ones alone (no edits)."""
    if isinstance(answer, dict):
        return answer.get("edits") or {}, answer.get("accepted")
    return {}, answer


def named_ids(answer: Any) -> list[str]:
    """The ids an answer names: a list, or a string "C1,C3" (the command line, an older client), never read letter by
    letter."""
    return [i.strip() for i in (answer.split(",") if isinstance(answer, str) else answer) if i.strip()]


# -- review (interrupt 1) -------------------------------------------------
def review(deps: Deps, state: WatchState) -> dict:
    corrections = state["corrections"]
    answer = interrupt(
        {
            "step": "review",
            "report": state["report_path"],
            "corrections": [
                {"id": c["id"], "severity": c["severity"], "page": c["page"], "check": c["check"],
                 **({"group": c["group"]} if c["group"] != c["id"] or has_members(corrections, c) else {})}
                for c in corrections
            ],
            "question": "Which corrections to apply? 'all' (valid ones), 'none', or ids like C1,C3. "
            "A group is applied whole: naming one member accepts the others. "
            "Or {'accepted': [...], 'edits': {'C3': 'the text retouched'}}.",
        }
    )
    # The editor's texts, retouched in the review: they replace the proposals, go through the free checks again
    # and are kept beside the model's (`proposed_model`); no model is called again
    edits, answer = split_answer(answer)
    if edits:
        corrections = retouched(deps.vault, corrections, edits, state.get("mode"))
        note_retouches(state.get("report_path", ""), corrections)
    if answer == "all":
        asked = {c["id"] for c in corrections}
    elif answer == "none" or not answer:
        asked = set()
    else:
        asked = set(named_ids(answer))
    groups = {c["group"] for c in corrections if c["id"] in asked}
    # A group with one member that fails the check cannot be applied consistently.
    broken = {c["group"] for c in corrections if c["check"] != "ok"}
    accepted = [c["id"] for c in corrections if c["group"] in groups - broken]
    issue = state.get("issue")
    if not accepted and issue and deps.repo:
        # The watch is handled: its issue closes (a PR closes it on merge otherwise, see pr_body)
        forge.get().close_issue(deps.repo, issue,
                                f"Reviewed with vault-watch-agent: no correction applied ({len(corrections)} proposed).")
    return {"accepted": accepted, **({"corrections": corrections} if edits else {})}


# -- apply ----------------------------------------------------------------
def apply(deps: Deps, state: WatchState) -> dict:
    # One branch per run: a watch is named after its window and its issue (two watches of the same day, a weekly
    # one and an urgent one, would share a branch and a worktree otherwise), a fix run after its own label.
    branch = state.get("branch_name") or watch_branch(state)
    worktree = deps.home / "worktrees" / branch.replace("/", "-")
    if not worktree.exists():
        with vault._GIT:  # not while another run syncs main or resets the reading copy
            git("worktree", "add", "-B", branch, str(worktree), deps.base, cwd=deps.vault)
    chosen = [c for c in state["corrections"] if c["id"] in state["accepted"]]
    pages = sorted({c["page"] for c in chosen})
    before = {p: compact.weight(worktree, [p]) for p in pages}
    for c in news.ordered(chosen):
        if not vault.date_bump_only(c["current"], c["proposed"], vault.guide_of(worktree).modified_field):  # apply bumps it
            vault.apply(worktree, c["page"], c["current"], c["proposed"], deps.today)
    # What the edits weigh, shown for every run; `pages`: the change of each page, the largest first
    after = {p: compact.weight(worktree, [p]) for p in pages}
    weight = {"before": sum(before.values()), "after": sum(after.values()),
              "pages": largest_first({p: after[p] - before[p] for p in pages})}
    floors = vault.guide_of(worktree).version_floors
    if floors and (worktree / floors.script).is_file():
        try:  # the guide's own script follows the minimum versions its pages now state
            inputs.run(["node", floors.script, "--write"], cwd=worktree)
            pages.append(floors.file)
        except RuntimeError:
            pass  # the audits step runs the same check and reports it before the PR
    git("add", *pages, cwd=worktree)
    summary = ", ".join(f"{c['id']} {c['page']}" for c in chosen)
    git("commit", "-F", "-", cwd=worktree, text=f"{pr_title(state)}\n\n{summary}\n")  # the message on stdin: it can be long
    return {"branch": branch, "worktree": str(worktree), "applied": [c["id"] for c in chosen], "weight": weight,
            "applied_tip": git("rev-parse", "HEAD", cwd=worktree).strip()}


# -- retouch (interrupt, H3): the editor retouches the pages of the branch before the mirrors, or skips ---------
def retouch_node(deps: Deps, state: WatchState) -> dict:
    """The pages of the branch, retouched by hand before the mirrors follow them. The page of the agent can lend
    the guide's folder for it (retouch.py), and commits what was retouched there before it resumes; what was
    retouched in the worktree is committed here. A run started before this pause existed does not stop."""
    if not state.get("retouch_offered"):
        return {}
    wt = Path(state["worktree"])
    base = git("merge-base", deps.base, "HEAD", cwd=wt).strip()
    answer = interrupt({
        "step": "retouch", "branch": state["branch"], "worktree": str(wt),
        "pages": mirrors.changed_pages(wt, base),
        "question": "Retouch the pages of the branch before the mirrors follow them? 'skip', or 'done' once the "
                    "files of the worktree are retouched; {'action': 'done', 'proofread': ['spelling', 'facts', "
                    "'consistency']} has the retouches proofread first.",
    })
    done = answer in ("done", True) or (isinstance(answer, dict) and answer.get("action") == "done")
    tip = state.get("applied_tip", "")
    if done:
        retouch.commit(wt)
    else:
        _drop_retouches(wt, tip)
    out = {"retouched": [n for n in git("diff", "--name-only", tip, "HEAD", cwd=wt).splitlines() if n] if tip else []}
    asked = [c for c in proofread.CHECKS if isinstance(answer, dict) and c in (answer.get("proofread") or [])]
    if done and asked:  # the editor's retouches proofread before the mirrors follow them
        out |= {"proofread_checks": asked, "proofread_since": tip or base, "proofread_from": "retouch"}
    return out


def _drop_retouches(wt: Path, tip: str) -> None:
    """The retouches skipped: what was retouched is dropped, typed in the worktree or committed from the folder
    taken back."""
    if retouch.changed(wt):
        git("checkout", "-q", "--", ".", cwd=wt)
        git("clean", "-q", "-fd", cwd=wt)
    if tip and git("rev-parse", "HEAD", cwd=wt).strip() != tip:
        git("reset", "-q", "--hard", tip, cwd=wt)


# -- proofread: what the editor changed by hand, checked when asked (proofread.py); the pause comes next ------
def proofread_node(deps: Deps, state: WatchState) -> dict:
    """The checks the editor asked for (spelling, facts on the web, consistency with the whole guide), on the
    passages of the source pages they changed by hand since `proofread_since`: their retouches, or what they
    corrected at the publish pause. The model is called here, the editor answers in `proofread_review`: a node
    that resumes runs again from its start, and these calls are made once."""
    checks = state.get("proofread_checks") or []
    if not checks:  # not asked: nothing called; what an earlier proofreading found is not shown again
        return {"proofread_fixes": [], "proofread_notes": []} if state.get("proofread_fixes") or state.get("proofread_notes") else {}
    wt, since = Path(state["worktree"]), state["proofread_since"]
    changes = [(page, mirrors.edits_of(wt, page, since)) for page in mirrors.changed_pages(wt, since)]
    found = proofread.run(wt, changes, set(checks), deps.translator or deps.llm, deps.llm)
    log = [*(state.get("proofread_log") or []), {"checks": checks, "fixes": len(found["fixes"]), "applied": 0,
                                                  "from": state.get("proofread_from", "retouch")}]
    return {"proofread_checks": [], "proofread_fixes": found["fixes"], "proofread_notes": found["notes"],
            "usage": found["usage"], "proofread_log": log}


# -- proofread review (interrupt): the editor accepts, retouches or leaves each fix of their edits -----------
def proofread_review(deps: Deps, state: WatchState) -> dict:
    """The pause on what the proofreading found, when it found something: the fixes accepted are applied on the
    branch (each quote found once, as any edit) and committed as the editor's. Then the run goes on: to the
    mirrors after the retouches; from the publish pause, to the mirrors when a source page changed since they
    last followed (those pages only), else straight to the checks."""
    fixes, notes, out = state.get("proofread_fixes") or [], state.get("proofread_notes") or [], {}
    if not state.get("worktree"):
        return out
    wt = Path(state["worktree"])
    if fixes or notes:
        out = _proofread_choice(deps, state, wt, fixes, notes)
    if state.get("proofread_from") == "publish":
        tip = state.get("mirror_tip") or git("merge-base", deps.base, "HEAD", cwd=wt).strip()
        pages = mirrors.changed_pages(wt, tip)
        out |= {"recheck": "mirror", "mirror_only": {p: tip for p in pages}} if pages else {"recheck": "audits"}
    return out


def _proofread_choice(deps: Deps, state: WatchState, wt: Path, fixes: list[dict], notes: list[str]) -> dict:
    """The pause itself: the fixes shown, those the editor accepts (or retouches) applied and committed."""
    answer = interrupt({
        "step": "proofread",
        "fixes": [{k: f[k] for k in ("id", "kind", "page", "current", "proposed", "reason", "source_url", "check")}
                  for f in fixes],  # whole: the command line shows them as they are
        "notes": notes,
        "question": "Which fixes of your edits to apply? 'all' (those found once in the page, an overlapping one "
                    "left), 'none', or ids like F1,F3. Or {'accepted': [...], 'edits': {'F2': 'your text'}}.",
    })
    edits, answer = split_answer(answer)
    if answer == "all":
        ids = [f["id"] for f in fixes if f["check"] == "ok" and not f.get("overlaps")]
    elif answer == "none" or not answer:
        ids = []
    else:  # a list of ids, or one string "F1,F3" (the command line)
        ids = named_ids(answer)
    done = proofread.accept(wt, fixes, ids, edits, deps.today)
    if done["applied"]:
        git("add", *sorted({f["page"] for f in fixes if f["id"] in done["applied"]}), cwd=wt)
        git("commit", "-q", "-m", "Proofread fixes accepted", cwd=wt)
    log = [dict(x) for x in state.get("proofread_log") or []]
    if log:
        log[-1]["applied"] = len(done["applied"])
    return {"proofread_log": log, "proofread_fixes": [{**f, "applied": f["id"] in done["applied"],
                                                       "failed": done["failed"].get(f["id"], "")} for f in fixes]}
