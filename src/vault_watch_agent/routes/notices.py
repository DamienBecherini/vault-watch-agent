"""Notifications when background work stops: what the human has to do next. On the desktop with `serve --notify`
(settings.notifier), and in the browser of a page whose bell is on (GET /api/notices)."""

from __future__ import annotations

import time

from fastapi import APIRouter

from .. import forge
from . import checks
from .context import AppContext, Job

MESSAGES = {
    "fr": {"review": ("Relecture à faire", "{n} correction(s) proposée(s) : à toi de trancher."),
           "publish": ("Publication à valider", "Corrections appliquées et contrôlées : la PR attend ton feu vert."),
           "retouch": ("Retouches possibles", "Corrections appliquées sur la branche : relis et retouche, ou passe."),
           "translation": ("Traduction à relire", "Le français et sa traduction, côte à côte : valide ou retouche."),
           "proofread": ("Relecture de tes modifications", "{n} correction(s) proposée(s) sur ce que tu as écrit : à toi de trancher."),
           "pr": ("Pull request ouverte", "À relire et fusionner sur {forge}."),
           "nothing-applied": ("Passe close", "Aucune correction appliquée."),
           "error": ("Passe interrompue", "Erreur : {error}"),
           "verif": ("Vérification terminée", "{n} piste(s) à traiter."), "verif-error": ("Vérification interrompue", "{error}")},
    "en": {"review": ("Review pending", "{n} correction(s) proposed: your call."),
           "publish": ("Publish pending", "Corrections applied and checked: the PR waits for your go-ahead."),
           "retouch": ("Retouches possible", "Corrections applied on the branch: read and retouch, or skip."),
           "translation": ("Translation to review", "The source and its translation, side by side: approve or retouch."),
           "proofread": ("Your edits proofread", "{n} fix(es) proposed on what you wrote: your call."),
           "pr": ("Pull request opened", "To review and merge on {forge}."),
           "nothing-applied": ("Run closed", "No correction applied."),
           "error": ("Run stopped", "Error: {error}"),
           "verif": ("Check finished", "{n} lead(s) to handle."), "verif-error": ("Check stopped", "{error}")},
}


def announce(ctx: AppContext, job: Job) -> None:
    """Says that `job` stopped, when it leaves the human something to do: kept for the pages, and on the desktop."""
    if job.thread.startswith("verif-"):
        v = checks.verif_view(ctx, checks.verif_path(ctx, job.thread))
        key, n, page = ("verif-error" if job.error else "verif"), v["counts"]["open"], f"#/check/{job.thread}"
    else:
        s = ctx.summary(job.thread)
        key = ("error" if job.error else "pr" if s["pr_url"] else s["status"])
        n, page = s["corrections"], f"#/run/{job.thread}"
        if key == "proofread":
            n = len(ctx.values(job.thread).get("proofread_fixes") or [])
    if key not in MESSAGES["en"]:
        return
    texts = {lang: {"title": f"vault-watch · {job.thread} · {m[key][0]}", "body": m[key][1].format(n=n, error=job.error[:150], forge=forge.get().name)}
             for lang, m in MESSAGES.items()}
    with ctx.lock:
        ctx.notices.append({"id": len(ctx.notices) + 1, "t": time.time(), "thread": job.thread, "key": key, "page": page, **texts})
    settings = ctx.settings
    if settings.notifier:
        mine = texts.get(settings.notify_lang, texts["en"])
        settings.notifier(mine["title"], mine["body"], settings.base_url + page)


def router(ctx: AppContext) -> APIRouter:
    api = APIRouter()

    @api.get("/api/notices")
    def notices_view(since: int = -1):
        """What stopped since the notice `since`, for the notifications of the page, in both languages. A page that
        just opened asks without `since`: it gets the last id only, and is told of what happens from then on."""
        with ctx.lock:
            return {"last": len(ctx.notices), "notices": [n for n in ctx.notices if n["id"] > since] if since >= 0 else []}

    return api
