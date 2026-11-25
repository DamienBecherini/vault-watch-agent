"""The answers to a run's pauses: the review of its corrections, the retouches of its pages (in its copy, or in the
guide's folder lent to it: retouch.py), the proofreading of the editor's edits, the review of the translation, and
the publish step (or, instead, a check again, a translation again, a proofreading)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from langgraph.types import Command
from pydantic import BaseModel

from .. import inputs, mirrors, proofread, retouch, vault
from ..graph import retouched
from .context import AppContext
from .languages import Accept, edits_usd


class Review(BaseModel):
    accept: list[str] | str  # "all", "none" or ids
    edits: dict[str, str] = {}  # the texts the editor retouched in the review: {id: text}


class Retouch(BaseModel):
    edits: dict[str, str]  # {id: text}, to check before the review is sent


class Publish(BaseModel):
    go: bool = False
    # Instead of publishing: check again what was corrected on the page ("recheck"), or translate again ("retranslate":
    # `pages`, from the French corrected since the mirrors, or started over from the base when `fresh`)
    # or have what was corrected proofread first ("proofread": `checks`), then translated and checked
    action: Literal["", "recheck", "retranslate", "proofread"] = ""
    pages: list[str] = []
    fresh: bool = False
    checks: list[str] = []


class Lend(BaseModel):
    set_aside: bool = False  # the folder's changes not committed, set aside to lend it (put back after)


class PageText(BaseModel):
    path: str
    text: str


class Retouched(BaseModel):
    keep: bool = True  # False: what was retouched is dropped, the run goes on as it was
    proofread: list[str] = []  # with keep: the retouches proofread first (proofread.CHECKS), then the mirrors


class TranslationReview(BaseModel):
    edits: dict[str, str] = {}  # {"<mirror page>#<n>": the translation retouched}


def review_answer(accept: list[str] | str, edits: dict[str, str]):
    """What the review sends the run: "all", "none", or ids: a list, or one string "C1,C3" (sent as such on
    17/11/2026, it was read as a set of characters and the run ended with nothing applied); with the texts retouched."""
    if isinstance(accept, str):
        accept = accept.strip()
        answer = accept if accept in ("all", "none") else [i.strip() for i in accept.split(",") if i.strip()]
    else:
        answer = [i.strip() for i in accept if i.strip()]
    return {"accepted": answer, "edits": edits} if edits else answer


def checks_asked(given: list[str], needed: bool = False) -> list[str]:
    """The proofreading checks asked, in their order; 400 for one that does not exist, or for none when needed."""
    if set(given) - set(proofread.CHECKS) or (needed and not given):
        raise HTTPException(400, f"checks: some of {', '.join(proofread.CHECKS)}")
    return [c for c in proofread.CHECKS if c in given]


def folder_error(e: Exception) -> HTTPException:
    return HTTPException(409, str(e))


def page_path(tree: Path, given: str) -> Path:
    """A Markdown page of the tree, by its path in the guide: never outside, never another kind of file."""
    rel = Path(given.replace("\\", "/"))
    # « C:x.md » is neither absolute nor « .. », yet leaves the tree on Windows: the path must resolve inside it
    if (rel.is_absolute() or ".." in rel.parts or ":" in given or rel.suffix not in (".md", ".mdx")
            or not (tree / rel).resolve().is_relative_to(tree.resolve())):
        raise HTTPException(400, f"not a page of the guide: {given}")
    path = tree / rel
    if not path.is_file():
        raise HTTPException(404, f"no page {given}")
    return path


def router(ctx: AppContext) -> APIRouter:
    api = APIRouter()
    settings = ctx.settings

    def where(thread: str, v: dict) -> Path:
        """Where the run's pages are being retouched: the guide's folder when it is lent to the run, else its copy."""
        return retouch.where(settings.vault, settings.home, thread, Path(v["worktree"]))

    @api.post("/api/runs/{thread}/review")
    def review(thread: str, body: Review):
        return ctx.resume_with(thread, "review", Command(resume=review_answer(body.accept, body.edits)))

    @api.post("/api/runs/{thread}/retouch")
    def retouch_check(thread: str, body: Retouch):
        """What the free checks say of texts retouched in the review, before it is sent: for each id, its check and
        its warning. Nothing is kept: the review sends the texts again."""
        v = ctx.values(thread)
        if not v.get("corrections"):
            raise HTTPException(404, f"no correction to retouch in {thread}")
        out = retouched(settings.vault, v["corrections"], body.edits, v.get("mode"))
        return {c["id"]: {"check": c["check"], "warning": c.get("warning", "")} for c in out if c["id"] in body.edits}

    @api.post("/api/runs/{thread}/publish")
    def publish(thread: str, body: Publish):
        """Publish (`go`), or not; or, instead, check again what was corrected on the page, or translate again first."""
        if not body.action:
            return ctx.resume_with(thread, "publish", Command(resume=body.go))
        v = ctx.paused_at(thread, ("publish",))
        if body.action == "retranslate" and not body.pages:
            raise HTTPException(400, "no page to translate again")
        if body.action == "proofread":
            checks_asked(body.checks, needed=True)
            if not mirrors.changed_pages(Path(v["worktree"]), "HEAD"):
                raise HTTPException(400, "nothing corrected in a page of the guide's language: nothing to proofread")
        asked = {"action": body.action, "pages": body.pages, "fresh": body.fresh, "checks": body.checks}
        return ctx.resume_with(thread, body.action, Command(resume=asked))

    # -- the pause to retouch the pages of the branch (H3, retouch.py) -------------------------------------------
    @api.get("/api/runs/{thread}/folder")
    def folder_view(thread: str):
        """Where the guide's folder is, whether it can be lent to this run, and to which run it is lent."""
        ctx.paused_at(thread)
        try:
            now = retouch.state(settings.vault)
        except retouch.FolderError as e:
            raise folder_error(e) from e
        return {**now, "lent_to": retouch.lent_to(settings.home), "path": str(settings.vault)}

    @api.post("/api/runs/{thread}/folder")
    def folder_lend(thread: str, body: Lend):
        v = ctx.paused_at(thread)
        tip = inputs.run(["git", "rev-parse", "HEAD"], cwd=Path(v["worktree"])).strip()
        try:
            return retouch.lend(settings.vault, settings.home, thread, tip, body.set_aside)
        except retouch.FolderError as e:
            raise folder_error(e) from e

    @api.post("/api/runs/{thread}/folder/back")
    def folder_take_back(thread: str):
        """The folder lent to this run comes back to where it was, the retouches not ended: what was retouched in it is
        committed onto the run's branch (kept), what was set aside is put back. The run stays paused; the page edits
        its worktree again, and the folder can be lent again."""
        v = ctx.paused_at(thread)
        if retouch.lent_to(settings.home) != thread:
            raise HTTPException(409, f"the guide's folder is not lent to {thread}")
        try:
            return {"commit": retouch.give_back(settings.vault, settings.home, thread, Path(v["worktree"]), keep=True)}
        except retouch.FolderError as e:
            raise folder_error(e) from e

    @api.get("/api/runs/{thread}/page")
    def page_read(thread: str, path: str):
        tree = where(thread, ctx.paused_at(thread, ("retouch", "publish")))
        return {"path": path, "text": vault.read(page_path(tree, path)).replace("\r\n", "\n"),
                "in": "folder" if tree == settings.vault else "worktree"}

    @api.post("/api/runs/{thread}/page")
    def page_write(thread: str, body: PageText):
        """Writes a page retouched in the page of the agent, with the line endings the file had (at the retouches, or
        at the publish pause: committed when the run is asked to check again)."""
        tree = where(thread, ctx.paused_at(thread, ("retouch", "publish")))
        path = page_path(tree, body.path)
        crlf = "\r\n" in vault.read(path)
        text = body.text.replace("\r\n", "\n")
        vault.write(path, text.replace("\n", "\r\n") if crlf else text)
        return {"path": body.path, "changed": retouch.changed(tree)}

    @api.post("/api/runs/{thread}/retouched")
    def retouches_done(thread: str, body: Retouched):
        """« Done » (keep) or « skip »: the retouches made in the folder are committed onto the branch, the folder is
        given back with what was set aside, then the run resumes (the worktree's retouches are committed by the
        graph). A failure leaves the run paused, the folder as it is, and says why."""
        v = ctx.paused_at(thread)
        checks = checks_asked(body.proofread)
        try:
            retouch.give_back(settings.vault, settings.home, thread, Path(v["worktree"]), keep=body.keep)
        except retouch.FolderError as e:
            raise folder_error(e) from e
        answer = ({"action": "done", "proofread": checks} if checks else "done") if body.keep else "skip"
        return ctx.resume_with(thread, "retouch", Command(resume=answer))

    @api.get("/api/runs/{thread}/proofread/estimate")
    def proofread_estimate(thread: str, steps: str = ""):
        """What proofreading the editor's edits would cost, at the retouches (what was retouched since the corrections
        were applied, in the folder lent or in the run's copy) or at the publish pause (what was corrected there, not
        committed yet): the source pages concerned, and each check's estimate."""
        v = ctx.paused_at(thread, ("retouch", "publish"))
        wt = Path(v["worktree"])
        at_retouch = ctx.pause_step(thread) == "retouch"
        tree = where(thread, v) if at_retouch else wt
        since = (v.get("applied_tip") or "HEAD") if at_retouch else "HEAD"
        changes = [(p, mirrors.edits_of(tree, p, since)) for p in mirrors.changed_pages(tree, since)]
        return {"pages": [p for p, _ in changes], "usd": edits_usd(ctx, tree, changes, steps)}

    @api.post("/api/runs/{thread}/proofread")
    def proofread_done(thread: str, body: Accept):
        """The fixes of the editor's edits decided: those accepted (with the editor's own text for some) are applied
        on the run's branch, then the run goes on."""
        ctx.paused_at(thread, ("proofread",))
        return ctx.resume_with(thread, "proofread-review", Command(resume={"accepted": body.ids, "edits": body.edits}))

    @api.post("/api/runs/{thread}/translation")
    def translation_done(thread: str, body: TranslationReview):
        """The translation of a « Sync the languages » run reviewed: as it is, or with passages retouched."""
        if ctx.pause_step(thread) != "translation":
            raise HTTPException(409, f"{thread} is not paused at the translation")
        return ctx.resume_with(thread, "translation", Command(resume={"edits": body.edits}))

    return api
