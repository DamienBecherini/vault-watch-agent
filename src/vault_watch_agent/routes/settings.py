"""Page « Settings »: the user's settings (config.py: engine, reference to the API key, models, efforts, the steps
set apart), the prices of the models, and how each step would run."""

from __future__ import annotations

import os
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config as user_settings
from .. import llm, prices, steps, vault
from .context import AppContext

# What each step of a role runs at, shown in the Settings: read from the one table of the steps (steps.py)
STEP_EFFORTS = {role: [(s.id, s.effort) for s in steps.of_role(role)] for role in ("reasoning", "translator")}


class UserSettings(BaseModel):  # config.py: the key is a reference to where it is, never the key
    engine: str = ""
    key: str = ""
    models: dict[str, str] = {}
    effort: dict[str, str] = {}
    steps: dict[str, dict] | None = None  # the steps set apart from their role; None: keep those already set
    prices: dict[str, dict] | None = None  # None: keep the prices already set (a page that does not show them)
    engines: dict[str, dict] | None = None  # the other engines' options; None: keep those already set
    videos: dict[str, str] | None = None  # dl-sub-dub for the videos of the check « links »; None: keep it


def forced_engine() -> str:
    """The engine VAULT_WATCH_ENGINE imposes on every run ("" when it is not set)."""
    return os.environ.get("VAULT_WATCH_ENGINE", "").strip().lower()


def prices_view(ctx: AppContext, cfg: dict) -> dict:
    """Each priced model (the ones in use first) with its rates and where they come from, and the fetched list."""
    try:
        current = [llm.model_of(cfg, role) for role in user_settings.MODELS] + [
            own["model"] for own in cfg["steps"].values() if own.get("model")]
    except llm.ModelError:
        current = []
    table, in_use = ctx.price_table(cfg), [m for m in dict.fromkeys(current + list(cfg["models"].values())) if m]
    without = ctx.price_table({**cfg, "prices": {}})  # what a model costs when the user sets no price of their own
    rows = []
    for model in list(dict.fromkeys(in_use + list(cfg["prices"]) + table.known())):
        p, b = table.of(model), without.of(model)
        rows.append({"id": model, "in_use": model in in_use, "rates": p.rates() if p else None, "date": p.date if p else "",
                     "origin": p.origin if p else "", "label": p.label if p else "no price",
                     "base": {"rates": b.rates(), "origin": b.origin, "date": b.date} if b else None})
    fetched = next(((day, len(t)) for o, day, t in table.sources if o == "fetched" and t), None)
    return {"models": rows, "fetched": {"date": fetched[0], "models": fetched[1]} if fetched else None,
            "source": prices.LITELLM, "web_search_usd": table.web_search_usd}


def settings_view(ctx: AppContext, cfg: dict) -> dict:
    """The settings with what the page shows beside them: the engine in use, Claude Code on this machine,
    whether the reference gives a key (never the key), the models offered when the API cannot list them, the
    efforts of a role and the level each step of that role then runs at."""
    return {**cfg, "engine_now": llm.engine(cfg["engine"]),
            "engine_forced": forced_engine(),
            "claude_code": llm.claude_code_status(), "key_status": user_settings.key_status(cfg["key"]),
            "key_forms": user_settings.KEY_FORMS,
            "engines_installed": [{"name": k.name, "label": k.label} for k in llm.engines().values()],
            "engine_options": {k.name: k.options for k in llm.engines().values() if k.options},
            "engine_errors": llm.ENGINE_ERRORS,
            "guide": vault.guide_of(ctx.settings.vault).summary(),  # read-only: from its manifest
            "price_table": prices_view(ctx, cfg),
            "choices": {"models": user_settings.MODELS, "effort": user_settings.EFFORTS,
                        "levels": list(llm.EFFORT_LEVELS),  # what a step set apart may run at
                        "steps": {role: [{"step": step, "effort": effort,
                                          "levels": {e: llm.shift_effort(effort, llm.EFFORT_STEPS[e]) for e in user_settings.EFFORTS}}
                                         for step, effort in role_steps]
                                  for role, role_steps in STEP_EFFORTS.items()}}}


def router(ctx: AppContext) -> APIRouter:
    api = APIRouter()
    cfg_home = ctx.cfg_home
    pending: dict = {}  # the list of prices fetched last, until the user applies it or fetches again

    @api.get("/api/steps")
    def steps_now(steps: str = ""):
        """How each step would run now: with the settings, and with what the page chose for one run laid over them
        (`steps`). With it, what a page needs to offer another choice: the engines, the efforts."""
        cfg = ctx.with_steps(steps)
        return {"steps": ctx.steps_view(cfg), "efforts": list(llm.EFFORT_LEVELS),
                "engines": [{"name": k.name, "label": k.label} for k in llm.engines().values()],
                "forced": forced_engine()}

    @api.get("/api/models")
    def models_view(key: str = "", engine: str = "", base_url: str = ""):
        """The Claude models the API key can use, read from the Models API (`key`: a reference to try before saving
        it, else the one of the settings); without a key that answers, the models known to the agent and why.
        `engine`: another engine's models (the OpenAI-compatible server's: `base_url` and `key` tried before saving)."""
        if engine and engine not in ("api", "claude-code"):
            return other_models(engine, key, base_url)
        reference = key or user_settings.load(cfg_home)["key"]
        try:
            return {"source": "api", "models": llm.list_models(reference, prices=ctx.price_table()), "error": ""}
        except (llm.ModelError, user_settings.ConfigError) as e:
            known = dict.fromkeys(m for names in user_settings.MODELS.values() for m in names)
            return {"source": "known", "error": str(e),
                    "models": [{"id": m, "name": m, "context": None, "priced": ctx.price_table().of(m) is not None} for m in known]}

    def other_models(engine: str, key: str, base_url: str) -> dict:
        """The models of an engine other than Claude's, with the address and the key a page tries before saving."""
        cfg, kind = user_settings.load(cfg_home), llm.engines().get(engine)
        if not kind or not kind.models:
            return {"source": "none", "models": [], "error": f"{engine}: no list of models"}
        options = {**(cfg["engines"].get(engine) or {}), **({"base_url": base_url} if base_url else {}),
                   **({"key": key} if key else {})}
        try:
            return {"source": engine, "models": kind.models({**cfg, "engines": {**cfg["engines"], engine: options}}),
                    "error": ""}
        except (llm.ModelError, user_settings.ConfigError) as e:
            return {"source": engine, "models": [], "error": str(e)}

    @api.get("/api/settings")
    def settings_get():
        try:
            return settings_view(ctx, user_settings.load(cfg_home))
        except (user_settings.ConfigError, llm.ModelError) as e:
            raise HTTPException(500, str(e)) from e

    @api.post("/api/prices/fetch")
    def prices_fetch():
        """Reads LiteLLM's public list and says what it would change; nothing is replaced before /apply."""
        try:
            fetched = prices.fetch(date.today().isoformat())
        except ValueError as e:
            raise HTTPException(502, str(e)) from e
        pending.clear()
        pending.update(fetched)
        return {"date": fetched["date"], "models": len(fetched["models"]), "estimated": fetched["estimated"],
                "changes": prices.diff(ctx.price_table(), fetched)}

    @api.post("/api/prices/apply")
    def prices_apply():
        if not pending:
            raise HTTPException(409, "fetch the list first")
        prices.save(cfg_home, dict(pending))
        pending.clear()
        return settings_view(ctx, user_settings.load(cfg_home))

    @api.post("/api/settings")
    def settings_save(body: UserSettings):
        try:
            given = body.model_dump()
            for kept in ("prices", "steps", "engines", "videos"):  # a page that does not show them does not erase them
                if given[kept] is None:
                    given[kept] = user_settings.load(cfg_home)[kept]
            # dl-sub-dub's `start` is a command the agent runs (videos.py): set by hand in settings.json, never here
            given["videos"] = {**given["videos"], "start": user_settings.load(cfg_home)["videos"]["start"]}
            return settings_view(ctx, user_settings.save(cfg_home, given))
        except (user_settings.ConfigError, llm.ModelError) as e:
            raise HTTPException(400, str(e)) from e

    return api
