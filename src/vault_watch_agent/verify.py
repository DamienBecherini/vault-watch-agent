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
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field

from . import compact, inputs, prompts, quotes, reading, sizes, steps, vault
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
    """The pages by top folder (reading.chapters)."""
    return reading.chapters(vault_dir)


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
            "excerpts": {line(f): quotes.locate_all(vault_dir, f.excerpts) for f in result.findings if f.excerpts}}


def _read_guide(vault_dir: Path, llm: LLM, plan: "reading.Plan", system: str, prompt: str, schema: type,
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
                 "default), is a warning, never a failure."}, None),
    Check("compaction", {"fr": "Compactage : ce qui alourdit le guide", "en": "Compaction: what makes the guide heavy"},
          {"fr": "Claude lit toutes les pages d'un coup et liste, sans rien modifier : le même fait répété dans plusieurs "
                 "pages, l'historique empilé à côté du fait courant, les sections plus longues que ce qu'elles disent. Les "
                 "pistes gardées partent dans une passe de compactage, relue comme une correction.",
           "en": "Claude reads every page at once and lists, without editing anything: the same fact repeated in several "
                 "pages, history piled up beside the current fact, sections longer than what they say. The leads you "
                 "keep go to a compaction run, reviewed like a correction."},
          MODEL, needs=("sizes",), fix_mode="compact"),
]
RUNNERS = {"audits": run_audits, "sources": run_sources, "freshness": run_freshness, "coherence": run_coherence,
           "translation": run_translation, "claims": run_claims, "deadlinks": run_deadlinks, "sizes": run_sizes,
           "compaction": run_compaction}
BY_ID = {c.id: c for c in CHECKS}


def plan(selected: list[str]) -> list[str]:
    """Selected checks plus what they need, in catalogue order."""
    wanted = set(selected)
    for c in selected:
        wanted |= set(BY_ID[c].needs)
    return [c.id for c in CHECKS if c.id in wanted]
