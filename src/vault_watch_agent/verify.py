"""Health check of the whole guide, on demand: pick the checks, see their estimated cost, run them.

The deterministic checks are the guide's own scripts (no model, no cost). The model checks read the guide
and return findings: one self-contained line each (page, problem, what to check). A finding is not a
correction: the ones the human keeps go to a fix run (`fix.py`), which verifies them on primary sources and
goes through the usual review and pull request.

Estimates use the size of the pages (2.1 bytes per token, measured on this guide: 853 KB of French pages
= 408 k tokens) and the list prices of the agent's price table (prices.py); web searches and the model's own reading of sources
make the real cost vary, hence « ≈ ».
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from . import compact, inputs, links, news, prompts, quotes, reading, sizes, steps, vault, videos
from .guide import language_name
from .llm import LLM, MODEL, TRANSLATOR, price_of

BYTES_PER_TOKEN = 2.1
# Measured on the first full check (2026-11-08, 7.26 $): the whole-guide read wrote 27 k tokens; checking a
# claim on the web read ≈ 46 k tokens of sources (0.21 $), finding where a dead source moved ≈ 0.27 $.
COHERENCE_OUT = 27_000  # output tokens of the whole-guide read
CLAIM_USD = 0.21  # one watchlist claim checked on the web
DEAD_LINK_USD = 0.27  # one dead source: find where it moved
OUTPUT_PER_CHAPTER = 3_000
# Output tokens, thinking included, counted high on purpose: an estimate shown before a billed run should not be
# beaten. The coherence check wrote 27 to 29 k on Opus 5.5 at effort high, the proposals and the cross-check of a fix
# run 21 to 30 k and 12 to 15 k; the first compaction report on Fable 5.2 at effort high wrote more than 64 000
# (20/11/2026, cut at the limit of the time), then 48 459 once the report was held to 30 findings.
COMPACTION_OUT = 60_000
# A compaction run: its proposals write the guide to the cache once and read it in each of their calls (about one
# call per eight findings), then write the trims of each finding; then one cross-check of the whole guide on its
# own model, and the mirror of each page touched. Counted for the Claude API; an engine whose proposals read only
# the pages the findings name (compact.propose) pays less. Measured once (20/11/2026, the IA on-prem guide, 30
# findings, Fable 5.2 at effort high then Opus 5.5): 4 calls of proposals wrote 250 k tokens (39 to 93 k each) and
# only the first one wrote the cache; the cross-check read 58 k tokens of trims and wrote 34 k; 17.79 $ before the
# mirrors, which are still an estimate.
COMPACT_PER_CALL = 8  # findings per call of the proposals
COMPACT_OUT_EACH = 8_500  # proposals, thinking included
CROSS_IN_EACH = 2_000  # the trims of a finding, read by the cross-check
CROSS_OUT, CROSS_OUT_EACH = 10_000, 800
MIRROR_IN_EACH, MIRROR_OUT_EACH = 30_000, 2_000  # a page and its mirror, one page and a half per finding
# « Look for what is new » (news.py). The leads: one call that reads the whole guide and writes at most thirty leads.
# An addition run: its proposals write the guide to the cache once, then each lead has a call of its own, of several
# rounds of search (each round reads the guide from the cache, and what the web returned so far); then the
# cross-check of a watch (the guide written to its own cache, each source opened again), and the mirror of each page
# touched. Measured once (add-2026-11-20, the IA on-prem guide, Opus 5.5 at effort high, 10.84 $ before the mirrors):
# a lead about six price lists took 21 rounds, 76 k tokens of web pages and wrote 22 k (2.72 $ besides the guide
# written to the cache); a lead dug deeper 13 rounds, 100 k and 14 k (1.88 $); the cross-check of their 28 edits
# 14 rounds, 111 k and 18 k (4.08 $). Measured again the same day (add-2026-11-20-2, three leads, one call each,
# 12.78 $ before the mirrors for 13.12 $ announced): a version or a floor to check is no lighter (16, 18 and 25
# rounds, 50 to 68 k of web pages, 8 to 13 k written: 1.82, 1.94 and 2.79 $), and the cross-check of the 13 edits
# took 16 rounds, 87 k and 16 k (4.07 $). The mirrors of the first run: four pages, 0.17 $.
# A link's text and its leads, measured on 2026-11-21 (Opus, effort high): the releases page of vLLM (92,538
# characters, 30,000 tokens, 9,913 written) and a PDF guide of the ANSSI (75,930 characters, 34,550 tokens, 7,107 written)
LINK_IN = 32_000
LINK_OUT = 9_000
# The same check run in French on 2026-11-22: each lead also explained to the editor (news.in_language), 27,084 tokens
# written instead of 17,020: what the model writes for the leads grows by this share in any language but English
EXPLAIN_SHARE = 0.6
NEWS_OUT = 20_000  # the leads: 14 536 tokens written for 28 leads on 2026-11-20 (Opus, effort high: 2.28 $ in all)
CHAPTERS_OUT = 2_000  # the split of the guide into chapters: its answer (1 409 tokens measured on 2026-11-20, Opus, 9 chapters)
# A third run read its leads' pages and the plan instead of the guide (add-2026-11-20-3, five leads, 8.41 $ before
# the mirrors): calls of 7 to 30 rounds, 1.5 to 16 k written, 0.42 to 1.28 $ each. Its cross-check cost what the two
# others did (3.88 $ for five leads, 4.08 $ for two, 4.07 $ for three: 14 to 16 rounds, about 100 k of web pages and
# 16 to 18 k written whatever the leads), and its sweep 0.34 $ (0.18 $ twice before).
ADD_ROUNDS_EACH = 18  # readings of what the call was given (the guide, or its own pages) per lead, by the proposals
ADD_WEB_IN_EACH = 80_000  # tokens of web pages read per lead, by the proposals
ADD_OUT_EACH = 13_000
ADD_DEEP_ROUNDS, ADD_DEEP_WEB_IN, ADD_DEEP_OUT = 22, 120_000, 22_000  # a lead dug deeper: more sources, more pages
# The cross-check and the sweep of an addition run, whatever the leads: readings of the cached guide, web pages, output
ADD_CROSS_READS, ADD_CROSS_WEB_IN, ADD_CROSS_OUT = 15, 100_000, 18_000
ADD_SWEEP_IN, ADD_SWEEP_OUT = 15_000, 6_000
# A call that reads its lead's pages and the plan of the guide instead of the whole guide (news.propose, "pages"):
# the plan is a twentieth of the guide (38 KB of 820 on the IA on-prem guide), the pages a lead names 13 to 55 KB.
PLAN_SHARE, ADD_PAGES_BYTES = 0.05, 60_000
ADD_CROSS_WEB_IN_EACH, ADD_CROSS_OUT_EACH = 5_000, 1_000  # the cross-check, per lead: little
# A call that has the whole budget of searches for itself (a chapter explored, a lead dug deeper): about twenty-five
# rounds, each reading the cached guide and what the web returned so far. Twenty searches read 638 k tokens of
# sources on 17/11/2026 (the re-check of the dated claims).
WEB_CALL_ROUNDS, WEB_CALL_IN, WEB_CALL_OUT = 25, 640_000, 10_000
HEAVIEST = 15  # pages kept in the result of the size check at least: the flagged ones (all of them), then the heaviest


class Finding(BaseModel):
    pages: list[str] = Field(description="Vault-relative paths of the pages concerned.")
    problem: str = Field(description="One self-contained line, in English: what is wrong or inconsistent, quoting "
                         "the passages, and what a fix should check. Someone who has not read the guide must be able "
                         "to act on it.")
    severity: Literal["Critical", "Major", "Minor"]
    excerpts: list[quotes.Quote] = Field(default_factory=list, description="The passages in question, each copied "
                                         "verbatim from its page (both sides for a divergence between two pages), so "
                                         "the reviewer sees them without opening the page.")


class Findings(BaseModel):
    findings: list[Finding]


class TranslationFinding(Finding):
    meaning_differs: bool = Field(description="False when, on reflection, both sides say the same thing (wording, "
                                  "adaptation, a shared mistake): such findings are dropped.")


class TranslationFindings(BaseModel):
    findings: list[TranslationFinding]


@dataclass
class Check:
    id: str
    title: dict  # {"fr": …, "en": …}
    what: dict
    model: str | None  # None: deterministic, free
    needs: tuple = ()  # checks whose results this one uses (run first, even when not ticked)
    estimate: Callable[[Path, dict], dict] | None = None
    fixable: bool = True  # findings can go to a fix run
    fix_mode: str = "fix"  # "translation": a fix run on the French and English pages alone (fix.propose_translation)
    limit: dict | None = None  # what the check, or the run its leads go to, does not do: a line of its own on its card
    # Its kind, as the list of the checks groups them: "health" (what is wrong in the guide), "light" (what makes
    # it heavy), "news" (what it is missing)
    kind: str = "health"


def _tokens(paths: list[Path]) -> int:
    return int(sum(p.stat().st_size for p in paths) / BYTES_PER_TOKEN)


def _usd(model: str, tokens_in: int = 0, tokens_out: int = 0, cache_write: int = 0, table=None, cache_read: int = 0) -> float:
    p_in, p_out, p_read, p_write = price_of(model, table) or (0.0, 0.0, 0.0, 0.0)  # a model without a known price: 0, said in the Settings
    return (tokens_in * p_in + tokens_out * p_out + cache_write * p_write + cache_read * p_read) / 1e6


def mirror_pages(vault_dir: Path) -> list[Path]:
    """The pages of every mirror of the guide that have their source page."""
    guide = vault.guide_of(vault_dir)
    return [vault_dir / folder / p.relative_to(vault_dir) for folder in guide.mirrors.values()
            for p in vault.pages(vault_dir) if (vault_dir / folder / p.relative_to(vault_dir)).is_file()]


english_pages = mirror_pages  # its name before manifests


def estimates(vault_dir: Path, known: dict, models: dict | None = None, table=None,
              step_models: dict | None = None) -> dict[str, dict]:
    """{check id: {tokens, usd, note}}; `known` holds counts from the last run (dead links, claims due).
    `models`: the models of the user's settings ({reasoning, translator}), priced instead of the defaults;
    `step_models`: the steps that run on a model of their own ({step: model})."""
    reasoning, translator = (models or {}).get("reasoning", MODEL), (models or {}).get("translator", TRANSLATOR)
    of = lambda step: (step_models or {}).get(step) or (translator if steps.STEPS[step].role == "translator" else reasoning)  # noqa: E731
    fr = _tokens(vault.pages(vault_dir))
    en = _tokens(mirror_pages(vault_dir))
    chapters = len(by_chapter(vault_dir))
    claims, dead = known.get("claims"), known.get("dead")
    note = lambda fr_, en_: {"fr": fr_, "en": en_}  # noqa: E731
    # What follows the proposals of a lead of an addition run: its share of the cross-check, and its mirror
    add_after = (_usd(of("crosscheck"), tokens_in=ADD_CROSS_WEB_IN_EACH, tokens_out=ADD_CROSS_OUT_EACH, table=table)
                 + (_usd(of("mirror"), tokens_in=MIRROR_IN_EACH, tokens_out=MIRROR_OUT_EACH, table=table)
                    if vault.guide_of(vault_dir).mirrors else 0.0))
    # The cross-check of an addition run (the guide written to its cache, read at each round) and the sweep after it
    add_checked = (_usd(of("crosscheck"), tokens_in=ADD_CROSS_WEB_IN, tokens_out=ADD_CROSS_OUT, cache_write=fr,
                        cache_read=ADD_CROSS_READS * fr, table=table)
                   + _usd(of("crosscheck"), tokens_in=ADD_SWEEP_IN, tokens_out=ADD_SWEEP_OUT, cache_read=fr, table=table))
    # A check of leads started in another language than English: its leads explained in it, written on top
    explained = lambda step, out: _usd(of(step), tokens_out=int(EXPLAIN_SHARE * out), table=table)  # noqa: E731
    # What a call of the "pages" context reads, and caches: never more than the guide itself
    own = min(fr, int(PLAN_SHARE * fr + ADD_PAGES_BYTES / BYTES_PER_TOKEN))
    return {
        "audits": {"tokens": 0, "usd": 0.0, "note": note("≈ 10 s", "≈ 10 s")},
        "sources": {"tokens": 0, "usd": 0.0, "note": note("≈ 2 à 4 min (réseau)", "≈ 2-4 min (network)")},
        "freshness": {"tokens": 0, "usd": 0.0, "note": note("≈ 5 s", "≈ 5 s")},
        "sizes": {"tokens": 0, "usd": 0.0, "note": note("≈ 2 s", "≈ 2 s")},
        "compaction": {"tokens": fr + COMPACTION_OUT, "usd": _usd(of("compaction"), tokens_out=COMPACTION_OUT, cache_write=fr, table=table),
                       "note": note(f"{fr:,} tokens de pages lues en entier ; rien n'est modifié".replace(",", " "),
                                    f"{fr:,} tokens of pages, read whole; nothing is edited")},
        # Not a check: the run the compaction leads go to (shown on the button that creates it)
        # `usd`: whatever the findings (the guide written to the cache by the proposals, then by the cross-check);
        # `usd_each`: per finding sent to the run
        "compact-run": {"tokens": 2 * fr + CROSS_OUT,
                        "usd": _usd(of("compact"), cache_write=fr, table=table)
                        + _usd(of("crosscheck"), tokens_out=CROSS_OUT, cache_write=fr, table=table),
                        "usd_each": _usd(of("compact"), cache_read=fr // COMPACT_PER_CALL, tokens_out=COMPACT_OUT_EACH, table=table)
                        + _usd(of("crosscheck"), tokens_in=CROSS_IN_EACH, tokens_out=CROSS_OUT_EACH, table=table)
                        + (_usd(of("mirror"), tokens_in=MIRROR_IN_EACH, tokens_out=MIRROR_OUT_EACH, table=table)
                           if vault.guide_of(vault_dir).mirrors else 0.0)},
        "news": {"tokens": fr + NEWS_OUT, "usd": _usd(of("news"), tokens_out=NEWS_OUT, cache_write=fr, table=table),
                 "usd_explained": _usd(of("news"), tokens_out=NEWS_OUT, cache_write=fr, table=table) + explained("news", NEWS_OUT),
                 "note": note(f"{fr:,} tokens de pages lues en entier ; rien n'est vérifié ni modifié".replace(",", " "),
                              f"{fr:,} tokens of pages, read whole; nothing is verified or edited")},
        # One call per chapter: `usd` whatever the chapters (the guide written to the cache), `usd_chapter` for each
        "explore": {"tokens": fr + WEB_CALL_IN, "usd": _usd(of("explore"), cache_write=fr, table=table),
                    "usd_chapter": _usd(of("explore"), tokens_in=WEB_CALL_IN, tokens_out=WEB_CALL_OUT,
                                        cache_read=WEB_CALL_ROUNDS * fr, table=table),
                    "usd_chapter_explained": _usd(of("explore"), tokens_in=WEB_CALL_IN, tokens_out=WEB_CALL_OUT,
                                                  cache_read=WEB_CALL_ROUNDS * fr, table=table) + explained("explore", WEB_CALL_OUT),
                    "note": note(f"un appel par chapitre choisi, avec le web et les {fr:,} tokens du guide ; rien n'est "
                                 "modifié".replace(",", " "),
                                 f"one call per chapter chosen, with the web and the {fr:,} tokens of the guide; nothing is "
                                 "edited")},
        # One call per link read: `usd` whatever the links (the guide written to the cache), `usd_link` for each
        "links": {"tokens": fr + LINK_IN, "usd": _usd(of("links"), cache_write=fr, table=table),
                  "usd_link": _usd(of("links"), tokens_in=LINK_IN, tokens_out=LINK_OUT, cache_read=fr, table=table),
                  "usd_link_explained": _usd(of("links"), tokens_in=LINK_IN, tokens_out=LINK_OUT, cache_read=fr, table=table)
                  + explained("links", LINK_OUT),
                  "note": note(f"un appel par lien lu, sans le web, avec les {fr:,} tokens du guide ; rien n'est vérifié ni "
                               "modifié".replace(",", " "),
                               f"one call per link read, without the web, with the {fr:,} tokens of the guide; nothing is "
                               "verified or edited")},
        # Not a check: the run the leads of « news » go to. `usd`: whatever the leads (the guide written to the cache
        # by the proposals, then the cross-check); `usd_each`: per lead sent to the run
        "add-run": {"tokens": 2 * fr + CROSS_OUT,
                    "usd": _usd(of("add"), cache_write=fr, table=table) + add_checked,
                    "usd_each": _usd(of("add"), tokens_in=ADD_WEB_IN_EACH, tokens_out=ADD_OUT_EACH,
                                     cache_read=ADD_ROUNDS_EACH * fr, table=table) + add_after,
                    # a lead dug deeper: the same call, asked for a fuller look
                    "usd_deep": _usd(of("add"), tokens_in=ADD_DEEP_WEB_IN, tokens_out=ADD_DEEP_OUT,
                                     cache_read=ADD_DEEP_ROUNDS * fr, table=table) + add_after,
                    # the same run when each call reads its lead's pages and the plan (context "pages"): the
                    # proposals no longer write the guide to the cache, each call writes and reads its own pages
                    "usd_pages": add_checked,
                    "usd_each_pages": _usd(of("add"), tokens_in=ADD_WEB_IN_EACH, tokens_out=ADD_OUT_EACH, cache_write=own,
                                           cache_read=ADD_ROUNDS_EACH * own, table=table) + add_after,
                    "usd_deep_pages": _usd(of("add"), tokens_in=ADD_DEEP_WEB_IN, tokens_out=ADD_DEEP_OUT, cache_write=own,
                                           cache_read=ADD_DEEP_ROUNDS * own, table=table) + add_after},
        "coherence": {"tokens": fr + COHERENCE_OUT, "usd": _usd(of("coherence"), tokens_out=COHERENCE_OUT, cache_write=fr, table=table),
                      "note": note(f"{fr:,} tokens de pages françaises, lues en entier".replace(",", " "),
                                   f"{fr:,} tokens of French pages, read whole")},
        "translation": {"tokens": fr + en + chapters * OUTPUT_PER_CHAPTER,
                        "usd": _usd(of("translation"), tokens_in=fr + en, tokens_out=chapters * OUTPUT_PER_CHAPTER, table=table),
                        "note": note(f"FR + EN, {chapters} appels (un par chapitre)", f"FR + EN, {chapters} calls (one per chapter)")},
        "claims": {"tokens": None, "usd": CLAIM_USD * claims if claims is not None else None,
                   "note": note(f"{claims} affirmations dues au dernier contrôle de fraîcheur", f"{claims} claims due at the last freshness check")
                   if claims is not None else note(f"≈ {CLAIM_USD} $ par affirmation due", f"≈ {CLAIM_USD} $ per claim due")},
        "deadlinks": {"tokens": None, "usd": DEAD_LINK_USD * dead if dead is not None else None,
                      "note": note(f"{dead} sources mortes au dernier contrôle", f"{dead} dead sources at the last check")
                      if dead is not None else note(f"≈ {DEAD_LINK_USD} $ par source morte", f"≈ {DEAD_LINK_USD} $ per dead source")},
    }


def by_chapter(vault_dir: Path) -> dict[str, list[Path]]:
    """The pages by chapter (reading.chapters)."""
    return reading.chapters(vault_dir)


def chapters_usd(vault_dir: Path, model: str, table=None) -> float:
    """What a model's split of the guide costs (chapters.propose): the outline of the guide read, a short answer."""
    from . import chapters

    # The outline is given as context, which the engine writes to its cache (20 346 tokens measured for 38 KB)
    tokens = int(len(chapters.outline(vault_dir).encode("utf-8")) / BYTES_PER_TOKEN * reading.MARGIN)
    return _usd(model, cache_write=tokens, tokens_out=CHAPTERS_OUT, table=table)


# ---------------------------------------------------------------------------
# Deterministic checks (the guide's scripts)
# ---------------------------------------------------------------------------


NOT_DECLARED = "not checked: the guide declares no [checks] {}"


def run_audits(vault_dir: Path, work: Path, results: dict, llm: LLM | None) -> dict:
    try:
        log = inputs.check("audits", vault_dir)
        if log is None:
            return {"ok": True, "summary": NOT_DECLARED.format("audits"), "findings": []}
        return {"ok": True, "summary": "all audits pass", "log": log[-3000:], "findings": []}
    except RuntimeError as e:
        return {"ok": False, "summary": "audits fail (see the log)", "log": str(e)[-3000:], "findings": []}


BROKEN = {"dead", "server-error", "network-error", "timeout"}


def run_sources(vault_dir: Path, work: Path, results: dict, llm: LLM | None) -> dict:
    out = work / "sources.json"
    if inputs.check("sources", vault_dir, out) is None:
        return {"ok": True, "summary": NOT_DECLARED.format("sources"), "dead": [], "blocked": [], "findings": []}
    report = json.loads(out.read_text(encoding="utf-8"))
    rows = []
    for s in report.get("sources", []):
        probe = s.get("probe") or {}
        pages = sorted({c["page"] for c in s.get("citations", []) if not vault.in_mirror(vault_dir, c["page"])})
        if pages and probe.get("status") in BROKEN | {"blocked"}:
            rows.append({"url": s["url"], "status": probe.get("status"), "code": probe.get("code"), "pages": pages})
    dead = [r for r in rows if r["status"] in BROKEN]
    blocked = [r for r in rows if r["status"] == "blocked"]
    return {"ok": not dead, "summary": f"{len(report.get('sources', []))} sources: {len(dead)} not answering, "
            f"{len(blocked)} blocked by anti-bot protections (usually fine in a browser)",
            "dead": dead, "blocked": blocked,
            "findings": [_dead(r) for r in dead],
            # The line citing the URL, found by the code: no model, always exact
            "excerpts": {_dead(r): [quotes.locate(vault_dir, p, r["url"]) for p in r["pages"]] for r in dead}}


def _dead(r: dict) -> str:
    return (f"{', '.join(r['pages'])} cites {r['url']}, which answers {r['status']} {r['code'] or ''}. Find where it "
            "moved or an equivalent primary source and replace the link, keeping what the citation supports.")


def run_freshness(vault_dir: Path, work: Path, results: dict, llm: LLM | None) -> dict:
    out = work / "freshness.json"
    if inputs.check("claims_due", vault_dir, out) is None:
        return {"ok": True, "summary": NOT_DECLARED.format("claims_due"), "claims": [], "pages_due": [],
                "findings": []}
    data = json.loads(out.read_text(encoding="utf-8"))
    claims = data.get("claimsDue", [])
    pages = [p for p in data.get("pages", []) if p.get("status") in ("overdue", "due-soon", "never-verified")]
    by = data.get("byStatus", {})
    return {"ok": not claims and not by.get("overdue"),
            "summary": f"{len(claims)} watchlist claims past their « Recheck by » date; pages: {by.get('overdue', 0)} "
                       f"overdue, {by.get('due-soon', 0)} due soon, {by.get('never-verified', 0)} never verified",
            "claims": claims, "pages_due": [f"{p['page']} ({p['status']})" for p in pages], "findings": []}


# ---------------------------------------------------------------------------
# Model checks
# ---------------------------------------------------------------------------

COHERENCE = """You audit <<GUIDE>>. The whole guide is above, one
<page> per file. List what a careful editor would fix:
- contradictions between pages (a figure, a version floor, a recommendation, a price, a date stated differently);
- a page left behind by the others (an older hardware generation or version presented as current while other pages
  moved on);
- wrong technical definitions or explanations;
- internal inconsistencies within a page (a table that disagrees with its text, a footnote that does not support
  the sentence citing it).
Do not report style, tone, length or missing topics. Do not report what is consistent. Each finding names the pages
and quotes the passages, so that someone who has not read the guide can check it on primary sources. Write the
findings in English. Prefer a few solid findings to many weak ones."""

TRANSLATION = """You compare the <<LANG>> pages of <<GUIDE>> with their <<MIRROR>> mirror (<<MIRROR_DIR>>). For each pair below, report only
real divergences of meaning: a paragraph, row or footnote missing on one side, a number, version, date, price or
link that differs, a recommendation that says something else, text left untranslated. Do not report style or
wording choices that keep the meaning. A pair without divergence gets no finding at all: never write a finding
that says nothing differs. Each finding names the <<MIRROR>> page and quotes both sides. Write the
findings in English."""

CLAIMS = """You check claims of <<GUIDE>> whose « Recheck by » date has
passed. For each claim, search the web and open primary sources (release notes, official docs, vendor pages).
Report a finding only for a claim that is now wrong or outdated, with what the sources say today and their URLs.
Write the findings in English."""

DEAD_LINKS = """Sources cited by <<GUIDE>> no longer answer. For each, search the web for where the
page moved, or an equivalent primary source (same publisher first). Report one finding per source: the page, the
dead URL, the replacement URL you opened and checked, and what it supports. If you find nothing reliable, say so in
the finding. Write the findings in English."""


EXCERPTS = ("\nIn `excerpts`, copy each passage in question verbatim from its page (one sentence or one table row): "
            "the reviewer reads it without opening the page.")


def _line(f: Finding) -> str:
    return f"[{f.severity}] {', '.join(f.pages)}: {f.problem}"


def _findings(vault_dir: Path, result: Findings, line: Callable = _line) -> dict:
    """The findings as lines (what the human keeps, dismisses or sends to a fix run), and per line the passages
    found in the pages."""
    return {"findings": [line(f) for f in result.findings],
            "excerpts": {line(f): quotes.locate_all(vault_dir, f.excerpts) for f in result.findings if f.excerpts},
            # a lead's title and its explanation to the editor, in the language of the interface (news.in_language),
            # by its line
            "details": {line(f): d for f in result.findings if (d := _detail(f))}}


def _detail(f) -> dict:
    """What a lead says to the editor besides its line: its title, its explanation ({} for a finding)."""
    detail = getattr(f, "detail", None)
    return {**(detail.model_dump() if detail else {}), **({"title": f.title} if getattr(f, "title", "") else {})}


def _read_guide(vault_dir: Path, llm: LLM, plan: reading.Plan, system: str, prompt: str, schema: type,
                step: str) -> tuple[list, list[dict]]:
    """The findings of a check that reads the whole guide, and the usage of its calls: one call, or one per chapter
    when the guide does not fit in the model's window (what spans two chapters is then missed, said in the summary)."""
    if plan.mode == "whole":
        result, usage = llm.parse(system=system, prompt=prompt, schema=schema, effort=steps.effort(step),
                                  node=f"verify {step}", context=f"<guide>\n{vault.corpus(vault_dir)}\n</guide>")
        return list(result.findings), [usage]
    found, usages = [], []
    for chapter, pages in reading.chapters(vault_dir).items():
        part, usage = llm.parse(system=system.replace("The whole guide is above", f"One chapter of the guide ({chapter}) is above", 1),
                                prompt=prompt, schema=schema, effort=steps.effort(step), node=f"verify {step} {chapter}",
                                context=f"<guide>\n{reading.corpus_of(vault_dir, pages)}\n</guide>")
        found += part.findings
        usages.append(usage)
    return found, usages


def run_coherence(vault_dir: Path, work: Path, results: dict, llm: LLM) -> dict:
    plan = reading.plan(vault_dir, llm, step="coherence")
    found, usages = _read_guide(vault_dir, llm, plan, prompts.fill(COHERENCE, vault_dir) + EXCERPTS,
                                "List the findings.", Findings, "coherence")
    by = "" if plan.mode == "whole" else f" ({plan.note})"
    return {"ok": not found, "summary": f"{len(found)} findings{by}", **_findings(vault_dir, Findings(findings=found)),
            "usage": usages, "reading": plan.summary()}


def run_sizes(vault_dir: Path, work: Path, results: dict, llm: LLM | None) -> dict:
    """What each page weighs and what it gained (sizes.py): no model. A page that grew much, or one above the
    ceiling its guide set, is a warning."""
    rep = sizes.report(vault_dir)
    first = sizes.flagged(rep)
    shown = first + [r for r in rep["pages"] if r not in first][:max(0, HEAVIEST - len(first))]
    return {"ok": not first, "summary": sizes.summary(rep), "findings": [],
            "sizes": {"total": rep["total"], "pages": len(rep["pages"]), "over": rep["over"], "grew": rep["grew"], "heaviest": shown,
                      "chapters": rep["chapters"], "growth": rep["growth"]}}


def run_compaction(vault_dir: Path, work: Path, results: dict, llm: LLM) -> dict:
    """What makes the guide heavy (compact.REPORT): the model reads it whole, with the heaviest pages named, and
    edits nothing. The findings the editor keeps go to a compaction run (compact.propose)."""
    heaviest = results["sizes"]["sizes"]["heaviest"]
    listing = "\n".join(f"- {sizes.describe(r)}{' — over its budget' if r['over'] else ''}{' — grew much' if r.get('grew') else ''}"
                        f"{' — read-only' if r['readonly'] else ''}" for r in heaviest)
    plan = reading.plan(vault_dir, llm, step="compaction")
    system = compact.REPORT.replace("<<MAX>>", str(compact.MAX_FINDINGS))
    found, usages = _read_guide(vault_dir, llm, plan, prompts.fill(system, vault_dir) + compact.EXCERPTS,
                                f"The heaviest pages:\n{listing}\n\nList the findings.", compact.Trims, "compaction")
    guide = vault.guide_of(vault_dir)
    kept = [f for f in found if not (f.pages and all(guide.is_readonly(p) for p in f.pages))]  # nothing to edit there
    skipped = f", {len(found) - len(kept)} about read-only pages left out" if len(kept) < len(found) else ""
    by = "" if plan.mode == "whole" else f" ({plan.note})"
    return {"ok": not kept, "summary": f"{len(kept)} findings{skipped}{by}",
            **_findings(vault_dir, compact.Trims(findings=kept), compact.line), "usage": usages, "reading": plan.summary()}


def run_news(vault_dir: Path, work: Path, results: dict, llm: LLM) -> dict:
    """What a reader would look for and not find (news.LEADS): the model reads the whole guide and what past watches
    set aside, verifies nothing and edits nothing. The leads the editor keeps go to an addition run (news.propose),
    which checks each one on the web."""
    seen = news.candidates(news.reports_of(work), date.today())
    plan = reading.plan(vault_dir, llm, step="news")
    system = news.in_language(prompts.fill(news.LEADS.replace("<<MAX>>", str(news.MAX_LEADS))
                                           .replace("<<READ>>", str(news.MAX_READ)), vault_dir), options(work).get("lang", ""))
    found, usages = _read_guide(vault_dir, llm, plan, system, f"{news.listing(seen)}\n\nList the leads.", news.Leads, "news")
    guide = vault.guide_of(vault_dir)
    kept = [f for f in found if not (f.pages and all(guide.is_readonly(p) for p in f.pages))][:news.MAX_LEADS]
    by = "" if plan.mode == "whole" else f" ({plan.note})"
    return {"ok": not kept, "summary": f"{len(kept)} leads, {len(seen)} item(s) set aside by past watches read{by}",
            **_findings(vault_dir, news.Leads(findings=kept), news.line), "usage": usages, "reading": plan.summary()}


def options(work: Path) -> dict:
    """What the editor chose for the checks of this verification (`options.json` in its working folder, written by
    the server or the command line): {"chapters": […]} for the exploration, {"links": […]} for the links, {"lang":
    "fr"} the language of the interface, in which the leads are explained. {} when nothing was chosen."""
    try:
        found = json.loads((work / "options.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def run_explore(vault_dir: Path, work: Path, results: dict, llm: LLM) -> dict:
    """What the web says that the guide does not (news.explore): one call per chapter chosen (when none was: all
    of them, except those the guide's manifest leaves out with `explore = false`), each with the web and the whole
    guide. The leads come with their sources and edit nothing; those the editor keeps go to an addition run, as the
    leads of « news » do."""
    from . import chapters

    chosen = [c for c in options(work).get("chapters") or [] if isinstance(c, str)] or chapters.default_explored(vault_dir)
    found, usages, failed = news.explore(vault_dir, llm, chosen, options(work).get("lang", ""))
    guide = vault.guide_of(vault_dir)
    kept = [f for f in found if not (f.pages and all(guide.is_readonly(p) for p in f.pages))]
    explored = [c for c in news.explorable(vault_dir) if (not chosen or c in chosen) and c not in failed]
    missed = f"; not explored, the call failed: {', '.join(failed)} ({next(iter(failed.values()))[:200]})" if failed else ""
    return {"ok": not kept and not failed, "summary": f"{len(kept)} leads from {len(explored)} chapter(s){missed}",
            **_findings(vault_dir, news.Leads(findings=kept), news.line), "usage": usages, "chapters": explored}


def run_links(vault_dir: Path, work: Path, results: dict, llm: LLM) -> dict:
    """What the links the editor gave say for the guide (links.py): each link read whole without a model, then one
    call per link with the whole guide, without the web. The leads come with the link as their first source and edit
    nothing; those the editor keeps go to an addition run, which checks them on primary sources."""
    asked = [u for u in options(work).get("links") or [] if isinstance(u, str)][:links.MAX_LINKS]
    reader = videos.Videos.of({"videos": options(work).get("videos")})  # dl-sub-dub, when the settings name it
    sources = [links.read(u, video=reader.read if reader else None) for u in asked]
    unread = [s for s in sources if not s.text]
    found, usages, failed = links.leads(vault_dir, sources, llm, options(work).get("lang", ""))
    guide = vault.guide_of(vault_dir)
    kept = [f for f in found if not (f.pages and all(guide.is_readonly(p) for p in f.pages))]
    done = len(sources) - len(unread) - len(failed)
    missed = (f"; not read: {len(unread)}" if unread else "") + (f"; the call failed for {len(failed)}" if failed else "")
    for s in sources:
        if s.url in failed:
            s.error = f"the call failed: {failed[s.url][:200]}"
    return {"ok": not kept and not unread and not failed,
            "summary": f"{len(kept)} leads from {done} link(s) read{missed}" if sources else "no link given",
            **_findings(vault_dir, news.Leads(findings=kept), news.line), "usage": usages,
            "links": [s.view() for s in sources]}


def run_translation(vault_dir: Path, work: Path, results: dict, llm: LLM) -> dict:
    findings, found, usages = [], {}, []
    guide = vault.guide_of(vault_dir)
    if not guide.mirrors:
        return {"ok": True, "summary": "not checked: the guide declares no mirror", "findings": []}
    for (code, folder), (chapter, pages) in ((m, c) for m in sorted(guide.mirrors.items())
                                             for c in sorted(by_chapter(vault_dir).items())):
        pairs = []
        for p in pages:
            rel = p.relative_to(vault_dir).as_posix()
            copy = vault_dir / folder / rel
            if copy.is_file():
                pairs.append(f"<pair page=\"{rel}\">\n<source>\n{vault.read(p)}\n</source>\n"
                             f"<mirror path=\"{folder}{rel}\">\n{vault.read(copy)}\n</mirror>\n</pair>")
            else:
                findings.append(f"[Major] {folder}{rel}: no {language_name(code)} mirror for this page.")
        if not pairs:
            continue
        result, usage = llm.parse(system=prompts.fill(TRANSLATION, vault_dir, code) + EXCERPTS,
                                  prompt="\n\n".join(pairs), schema=TranslationFindings, effort=steps.effort("translation"),
                                  node=f"verify translation {chapter}" + (f" {code}" if len(guide.mirrors) > 1 else ""))
        # The first run reported « no divergence found » as findings: they are filtered out here
        kept = _findings(vault_dir, Findings(findings=[f for f in result.findings if f.meaning_differs]))
        findings += kept["findings"]
        found.update(kept["excerpts"])
        usages.append(usage)
    return {"ok": not findings, "summary": f"{len(findings)} divergences", "findings": findings, "excerpts": found,
            "usage": usages}


def run_claims(vault_dir: Path, work: Path, results: dict, llm: LLM) -> dict:
    claims = results["freshness"]["claims"]
    if not claims:
        return {"ok": True, "summary": "no claim due", "findings": []}
    listing = "\n".join(f"- {c.get('page', '')} (recheck by {c.get('recheckBy', '')}): {c.get('claim', '')}" for c in claims)
    result, usage = llm.parse(system=prompts.fill(CLAIMS, vault_dir) + EXCERPTS, prompt=f"Claims to check:\n{listing}", schema=Findings,
                              effort=steps.effort("claims"), node="verify claims", web=True)
    return {"ok": not result.findings, "summary": f"{len(claims)} claims checked, {len(result.findings)} outdated",
            **_findings(vault_dir, result), "usage": [usage]}


def citing(vault_dir: Path, page: str, url: str, width: int = 600) -> str:
    """What a page says with a source: the lines that hold its URL and, for a footnote, the lines that call that
    footnote. The model searching a replacement had only the URL (17/11/2026: « I could not open the guide's
    pages »), so it could neither check what the new source must support nor quote the passage."""
    path = vault_dir / page
    if not path.is_file():
        return f'  <page path="{page}">(not found)</page>'
    lines = vault.read(path).replace("\r\n", "\n").split("\n")
    shown = [n for n, line in enumerate(lines) if url in line]
    for n in list(shown):
        mark = re.match(r"\[\^([^\]]+)\]:", lines[n])
        if mark:
            shown += [k for k, line in enumerate(lines) if f"[^{mark.group(1)}]" in line and k != n][:3]
    body = "\n".join(f"{k + 1}: {lines[k][:width]}" for k in sorted(set(shown)))
    return f'  <page path="{page}">\n{body}\n  </page>'


def run_deadlinks(vault_dir: Path, work: Path, results: dict, llm: LLM) -> dict:
    dead = results["sources"]["dead"]
    if not dead:
        return {"ok": True, "summary": "no dead source", "findings": []}
    listing = "\n".join(f"- {', '.join(d['pages'])}: {d['url']} ({d['status']} {d['code'] or ''})"
                        + "".join(f"\n{citing(vault_dir, p, d['url'])}" for p in d["pages"]) for d in dead)
    result, usage = llm.parse(system=prompts.fill(DEAD_LINKS, vault_dir) + EXCERPTS, prompt=f"Dead sources:\n{listing}", schema=Findings,
                              effort=steps.effort("deadlinks"), node="verify deadlinks", web=True)
    return {"ok": not result.findings, "summary": f"{len(dead)} dead sources, {len(result.findings)} replacements",
            **_findings(vault_dir, result), "usage": [usage]}


NO_NEW_PAGE = {"fr": "Limite : la passe d'ajouts n'écrit jamais de nouvelle page. Elle signale celles qu'il faudrait.",
               "en": "Limit: the addition run never writes a new page. It says which ones would be needed."}
CHECKS = [
    Check("audits", {"fr": "Contrôles du guide", "en": "Guide audits"},
          {"fr": "Front matter, diagrammes Mermaid, fuites de notes d'agents, miroir anglais à jour (npm test).",
           "en": "Front matter, Mermaid diagrams, agent-note leaks, English mirror up to date (npm test)."}, None),
    Check("sources", {"fr": "Liens morts", "en": "Dead links"},
          {"fr": "Chaque URL citée par une page française est interrogée (404, erreurs, sites qui bloquent les robots).",
           "en": "Every URL cited by a French page is probed (404, errors, sites blocking bots)."}, None),
    Check("freshness", {"fr": "Fraîcheur", "en": "Freshness"},
          {"fr": "Pages à revoir et affirmations de la watchlist dont la date de revérification est passée.",
           "en": "Pages due for review and watchlist claims past their « Recheck by » date."}, None),
    Check("coherence", {"fr": "Cohérence de tout le guide", "en": "Consistency of the whole guide"},
          {"fr": "Claude lit toutes les pages françaises d'un coup : contradictions entre pages, pages restées en arrière, "
                 "définitions fausses, notes qui ne soutiennent pas leur phrase.",
           "en": "Claude reads every French page at once: contradictions between pages, pages left behind, wrong "
                 "definitions, footnotes that do not support their sentence."}, MODEL),
    Check("translation", {"fr": "Fidélité des traductions", "en": "Translation fidelity"},
          {"fr": "Chaque page anglaise comparée à sa page française, chapitre par chapitre : passages manquants, "
                 "chiffres ou versions différents, texte non traduit.",
           "en": "Each English page compared with its French page, chapter by chapter: missing passages, different "
                 "figures or versions, untranslated text."}, TRANSLATOR, fix_mode="translation"),
    Check("claims", {"fr": "Revérification des affirmations datées", "en": "Re-check of dated claims"},
          {"fr": "Les affirmations dont la date est passée sont revérifiées sur le web.",
           "en": "Claims past their date are checked again on the web."}, MODEL, needs=("freshness",)),
    Check("deadlinks", {"fr": "Remplacement des liens morts", "en": "Replacement of dead links"},
          {"fr": "Pour chaque source morte, Claude cherche où la page a déménagé ou une source équivalente.",
           "en": "For each dead source, Claude looks for where the page moved or an equivalent source."},
          MODEL, needs=("sources",)),
    Check("sizes", {"fr": "Taille des pages", "en": "Size of the pages"},
          {"fr": "Ce que pèse chaque page, ce qu'elle a pris en 90 jours et ses sections les plus lourdes. Une page qui a "
                 "beaucoup grossi (5 Ko ou 25 % par défaut), ou qui dépasse le plafond que le guide s'est fixé ([budget] du "
                 "manifeste, aucun par défaut), est un avertissement, jamais un échec.",
           "en": "What each page weighs, what it gained in 90 days and its heaviest sections. A page that grew much (5 KB "
                 "or 25% by default), or one above the ceiling the guide set itself ([budget] of the manifest, none by "
                 "default), is a warning, never a failure."}, None, kind="light"),
    Check("compaction", {"fr": "Compactage : ce qui alourdit le guide", "en": "Compaction: what makes the guide heavy"},
          {"fr": "Claude lit toutes les pages d'un coup et liste, sans rien modifier : le même fait répété dans plusieurs "
                 "pages, l'historique empilé à côté du fait courant, les sections plus longues que ce qu'elles disent. Les "
                 "pistes gardées partent dans une passe de compactage, relue comme une correction.",
           "en": "Claude reads every page at once and lists, without editing anything: the same fact repeated in several "
                 "pages, history piled up beside the current fact, sections longer than what they say. The leads you "
                 "keep go to a compaction run, reviewed like a correction."},
          MODEL, needs=("sizes",), fix_mode="compact", kind="light"),
    Check("news", {"fr": "Nouveautés : ce qu'un lecteur chercherait et ne trouve pas",
                   "en": "What is new: what a reader would look for and not find"},
          {"fr": "Claude lit toutes les pages d'un coup, avec ce que les veilles ont mis de côté sans l'écrire, et liste "
                 "des pistes sans rien vérifier ni modifier : ce que le guide présente comme actuel et qui a sans doute "
                 "évolué, les sujets qu'un lecteur attendrait et qu'aucune page ne couvre. Les pistes gardées partent dans "
                 "une passe d'ajouts, qui vérifie chacune sur le web puis propose où l'écrire, relue comme une correction.",
           "en": "Claude reads every page at once, with what the watches set aside without writing it, and lists leads "
                 "without verifying or editing anything: what the guide presents as current and has probably moved on, "
                 "the subjects a reader would expect and no page covers. The leads you keep go to an addition run, which "
                 "checks each one on the web then proposes where to write it, reviewed like a correction."},
          MODEL, fix_mode="add", limit=NO_NEW_PAGE, kind="news"),
    Check("explore", {"fr": "Nouveautés : exploration du web, chapitre par chapitre",
                      "en": "What is new: the web explored, chapter by chapter"},
          {"fr": "Pour chaque chapitre choisi, Claude cherche librement sur le web ce qui a bougé sur ses sujets et le "
                 "compare à tout le guide : il trouve ce que personne n'a pensé à demander, et chaque piste arrive avec "
                 "ses sources. Plus cher que le contrôle précédent, et le web est payé avant que tu aies rien vu. Les "
                 "pistes gardées partent dans la même passe d'ajouts, où tu peux en faire creuser une.",
           "en": "For each chapter chosen, Claude searches the web freely for what moved on its subjects and compares it "
                 "with the whole guide: it finds what nobody thought to ask, and each lead comes with its sources. It "
                 "costs more than the check above, and the web is paid for before you have seen anything. The leads you "
                 "keep go to the same addition run, where you can have one dug deeper."},
          MODEL, fix_mode="add", limit=NO_NEW_PAGE, kind="news"),
    Check("links", {"fr": "Nouveautés : des liens à lire en entier", "en": "What is new: links to read whole"},
          {"fr": "Tu donnes des adresses (un article, une page, un PDF, une vidéo par dl-sub-dub). L'agent lit "
                 "chacune en entier, sans modèle, puis Claude la lit avec tout le guide et liste ce qui le concerne : des "
                 "pistes, rien n'est vérifié ni modifié. Les pistes gardées partent dans la passe d'ajouts, qui les "
                 "vérifie sur des sources primaires.",
           "en": "You give addresses (an article, a page, a PDF, a video through dl-sub-dub). The agent reads each "
                 "one whole, without a model, then Claude reads it with the whole guide and lists what concerns it: leads, "
                 "nothing is verified or edited. The leads you keep go to the addition run, which checks them on primary "
                 "sources."},
          MODEL, fix_mode="add", limit=NO_NEW_PAGE, kind="news"),
]
RUNNERS = {"audits": run_audits, "sources": run_sources, "freshness": run_freshness, "coherence": run_coherence,
           "translation": run_translation, "claims": run_claims, "deadlinks": run_deadlinks, "sizes": run_sizes,
           "compaction": run_compaction, "news": run_news, "explore": run_explore, "links": run_links}
BY_ID = {c.id: c for c in CHECKS}
KINDS = ("health", "light", "news")  # the order the list of the checks gives them


def short_title(check: Check, lang: str = "en") -> str:
    """The title of a check without its kind: « What is new: links to read whole » is « links to read whole »."""
    head, _, rest = check.title[lang].partition(":")
    return (rest.strip() if check.kind == "news" and rest else head.strip()) or check.title[lang]


def plan(selected: list[str]) -> list[str]:
    """Selected checks plus what they need, in catalogue order."""
    wanted = set(selected)
    for c in selected:
        wanted |= set(BY_ID[c].needs)
    return [c.id for c in CHECKS if c.id in wanted]
