"""Health check of the whole guide, on demand: pick the checks, see their estimated cost, run them.

The deterministic checks are the guide's own scripts (no model, no cost). The model checks read the guide
and return findings: one self-contained line each (page, problem, what to check). A finding is not a
correction: the ones the human keeps go to a fix run (`fix.py`), which verifies them on primary sources and
goes through the usual review and pull request.

Estimates use the size of the pages (2.1 bytes per token, measured on this guide: 853 KB of French pages
= 408 k tokens) and the list prices of `llm.PRICES`; web searches and the model's own reading of sources
make the real cost vary, hence « ≈ ».
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field

from . import inputs, vault
from .llm import LLM, MODEL, PRICES, TRANSLATOR

BYTES_PER_TOKEN = 2.1
COHERENCE_OUT = 16_000  # output tokens of the whole-guide read
CLAIM_USD = 0.12  # one watchlist claim checked on the web
DEAD_LINK_USD = 0.10  # one dead source: find where it moved
OUTPUT_PER_CHAPTER = 3_000


class Finding(BaseModel):
    pages: list[str] = Field(description="Vault-relative paths of the pages concerned.")
    problem: str = Field(description="One self-contained line, in English: what is wrong or inconsistent, quoting "
                         "the passages, and what a fix should check. Someone who has not read the guide must be able "
                         "to act on it.")
    severity: Literal["Critical", "Major", "Minor"]


class Findings(BaseModel):
    findings: list[Finding]


@dataclass
class Check:
    id: str
    title: dict  # {"fr": …, "en": …}
    what: dict
    model: str | None  # None: deterministic, free
    needs: tuple = ()  # checks whose results this one uses (run first, even when not ticked)
    estimate: Callable[[Path, dict], dict] | None = None
    fixable: bool = True  # findings can go to a fix run (French pages); translation findings cannot yet


def _tokens(paths: list[Path]) -> int:
    return int(sum(p.stat().st_size for p in paths) / BYTES_PER_TOKEN)


def _usd(model: str, tokens_in: int = 0, tokens_out: int = 0, cache_write: int = 0) -> float:
    p_in, p_out, _, p_write = PRICES[model]
    return (tokens_in * p_in + tokens_out * p_out + cache_write * p_write) / 1e6


def english_pages(vault_dir: Path) -> list[Path]:
    return [vault_dir / "en" / p.relative_to(vault_dir) for p in vault.french_pages(vault_dir)
            if (vault_dir / "en" / p.relative_to(vault_dir)).is_file()]


def estimates(vault_dir: Path, known: dict) -> dict[str, dict]:
    """{check id: {tokens, usd, note}}; `known` holds counts from the last run (dead links, claims due)."""
    fr = _tokens(vault.french_pages(vault_dir))
    en = _tokens(english_pages(vault_dir))
    chapters = len(by_chapter(vault_dir))
    claims, dead = known.get("claims"), known.get("dead")
    note = lambda fr_, en_: {"fr": fr_, "en": en_}  # noqa: E731
    return {
        "audits": {"tokens": 0, "usd": 0.0, "note": note("≈ 10 s", "≈ 10 s")},
        "sources": {"tokens": 0, "usd": 0.0, "note": note("≈ 2 à 4 min (réseau)", "≈ 2-4 min (network)")},
        "freshness": {"tokens": 0, "usd": 0.0, "note": note("≈ 5 s", "≈ 5 s")},
        "coherence": {"tokens": fr + COHERENCE_OUT, "usd": _usd(MODEL, tokens_out=COHERENCE_OUT, cache_write=fr),
                      "note": note(f"{fr:,} tokens de pages françaises, lues en entier".replace(",", " "),
                                   f"{fr:,} tokens of French pages, read whole")},
        "translation": {"tokens": fr + en + chapters * OUTPUT_PER_CHAPTER,
                        "usd": _usd(TRANSLATOR, tokens_in=fr + en, tokens_out=chapters * OUTPUT_PER_CHAPTER),
                        "note": note(f"FR + EN, {chapters} appels (un par chapitre)", f"FR + EN, {chapters} calls (one per chapter)")},
        "claims": {"tokens": None, "usd": CLAIM_USD * claims if claims is not None else None,
                   "note": note(f"{claims} affirmations dues au dernier contrôle de fraîcheur", f"{claims} claims due at the last freshness check")
                   if claims is not None else note(f"≈ {CLAIM_USD} $ par affirmation due", f"≈ {CLAIM_USD} $ per claim due")},
        "deadlinks": {"tokens": None, "usd": DEAD_LINK_USD * dead if dead is not None else None,
                      "note": note(f"{dead} sources mortes au dernier contrôle", f"{dead} dead sources at the last check")
                      if dead is not None else note(f"≈ {DEAD_LINK_USD} $ par source morte", f"≈ {DEAD_LINK_USD} $ per dead source")},
    }


def by_chapter(vault_dir: Path) -> dict[str, list[Path]]:
    """French pages by top folder; the pages at the root (index, home) form one group."""
    groups: dict[str, list[Path]] = {}
    for p in vault.french_pages(vault_dir):
        parts = p.relative_to(vault_dir).parts
        groups.setdefault(parts[0] if len(parts) > 1 else "(root)", []).append(p)
    return groups


# ---------------------------------------------------------------------------
# Deterministic checks (the guide's scripts)
# ---------------------------------------------------------------------------


def run_audits(vault_dir: Path, work: Path, results: dict, llm: LLM | None) -> dict:
    try:
        log = inputs.run(["node", "scripts/run-audits.mjs"], cwd=vault_dir)
        return {"ok": True, "summary": "all audits pass", "log": log[-3000:], "findings": []}
    except RuntimeError as e:
        return {"ok": False, "summary": "audits fail (see the log)", "log": str(e)[-3000:], "findings": []}


BROKEN = {"dead", "server-error", "network-error", "timeout"}


def run_sources(vault_dir: Path, work: Path, results: dict, llm: LLM | None) -> dict:
    out = work / "sources.json"
    inputs.run(["node", "scripts/audit-sources.mjs", "--concurrency=8", "--timeout=15000", f"--json={out}"],
               cwd=vault_dir)
    report = json.loads(out.read_text(encoding="utf-8"))
    rows = []
    for s in report.get("sources", []):
        probe = s.get("probe") or {}
        pages = sorted({c["page"] for c in s.get("citations", []) if not c["page"].startswith("en/")})
        if pages and probe.get("status") in BROKEN | {"blocked"}:
            rows.append({"url": s["url"], "status": probe.get("status"), "code": probe.get("code"), "pages": pages})
    dead = [r for r in rows if r["status"] in BROKEN]
    blocked = [r for r in rows if r["status"] == "blocked"]
    return {"ok": not dead, "summary": f"{len(report.get('sources', []))} sources: {len(dead)} not answering, "
            f"{len(blocked)} blocked by anti-bot protections (usually fine in a browser)",
            "dead": dead, "blocked": blocked,
            "findings": [f"{', '.join(r['pages'])} cites {r['url']}, which answers {r['status']} {r['code'] or ''}. "
                         "Find where it moved or an equivalent primary source and replace the link, keeping what the "
                         "citation supports." for r in dead]}


def run_freshness(vault_dir: Path, work: Path, results: dict, llm: LLM | None) -> dict:
    out = work / "freshness.json"
    inputs.run(["node", "scripts/audit-freshness.mjs", "--due-only", f"--json={out}"], cwd=vault_dir)
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

COHERENCE = """You audit a French-language guide on running AI on-premise for SMEs. The whole guide is above, one
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

TRANSLATION = """You compare French pages of a guide with their English mirror. For each pair below, report only
real divergences of meaning: a paragraph, row or footnote missing on one side, a number, version, date, price or
link that differs, a recommendation that says something else, text left untranslated. Do not report style or
wording choices that keep the meaning. Each finding names the English page and quotes both sides. Write the
findings in English."""

CLAIMS = """You check claims of a French-language guide on running AI on-premise whose « Recheck by » date has
passed. For each claim, search the web and open primary sources (release notes, official docs, vendor pages).
Report a finding only for a claim that is now wrong or outdated, with what the sources say today and their URLs.
Write the findings in English."""

DEAD_LINKS = """Sources cited by a French-language guide no longer answer. For each, search the web for where the
page moved, or an equivalent primary source (same publisher first). Report one finding per source: the page, the
dead URL, the replacement URL you opened and checked, and what it supports. If you find nothing reliable, say so in
the finding. Write the findings in English."""


def _findings(result: Findings) -> list[str]:
    return [f"[{f.severity}] {', '.join(f.pages)}: {f.problem}" for f in result.findings]


def run_coherence(vault_dir: Path, work: Path, results: dict, llm: LLM) -> dict:
    result, usage = llm.parse(system=COHERENCE, prompt="List the findings.", schema=Findings, effort="high",
                              node="verify coherence", context=f"<guide>\n{vault.corpus(vault_dir)}\n</guide>")
    return {"ok": not result.findings, "summary": f"{len(result.findings)} findings", "findings": _findings(result),
            "usage": [usage]}


def run_translation(vault_dir: Path, work: Path, results: dict, llm: LLM) -> dict:
    findings, usages = [], []
    for chapter, pages in sorted(by_chapter(vault_dir).items()):
        pairs = []
        for p in pages:
            rel = p.relative_to(vault_dir).as_posix()
            en = vault_dir / "en" / rel
            if en.is_file():
                pairs.append(f"<pair page=\"{rel}\">\n<french>\n{vault.read(p)}\n</french>\n"
                             f"<english path=\"en/{rel}\">\n{vault.read(en)}\n</english>\n</pair>")
            else:
                findings.append(f"[Major] en/{rel}: no English mirror for this French page.")
        if not pairs:
            continue
        result, usage = llm.parse(system=TRANSLATION, prompt="\n\n".join(pairs), schema=Findings, effort="medium",
                                  node=f"verify translation {chapter}")
        findings += _findings(result)
        usages.append(usage)
    return {"ok": not findings, "summary": f"{len(findings)} divergences", "findings": findings, "usage": usages}


def run_claims(vault_dir: Path, work: Path, results: dict, llm: LLM) -> dict:
    claims = results["freshness"]["claims"]
    if not claims:
        return {"ok": True, "summary": "no claim due", "findings": []}
    listing = "\n".join(f"- {c.get('page', '')} (recheck by {c.get('recheckBy', '')}): {c.get('claim', '')}" for c in claims)
    result, usage = llm.parse(system=CLAIMS, prompt=f"Claims to check:\n{listing}", schema=Findings, effort="high",
                              node="verify claims", web=True)
    return {"ok": not result.findings, "summary": f"{len(claims)} claims checked, {len(result.findings)} outdated",
            "findings": _findings(result), "usage": [usage]}


def run_deadlinks(vault_dir: Path, work: Path, results: dict, llm: LLM) -> dict:
    dead = results["sources"]["dead"]
    if not dead:
        return {"ok": True, "summary": "no dead source", "findings": []}
    listing = "\n".join(f"- {', '.join(d['pages'])}: {d['url']} ({d['status']} {d['code'] or ''})" for d in dead)
    result, usage = llm.parse(system=DEAD_LINKS, prompt=f"Dead sources:\n{listing}", schema=Findings, effort="medium",
                              node="verify deadlinks", web=True)
    return {"ok": not result.findings, "summary": f"{len(dead)} dead sources, {len(result.findings)} replacements",
            "findings": _findings(result), "usage": [usage]}


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
                 "figures or versions, untranslated text."}, TRANSLATOR, fixable=False),
    Check("claims", {"fr": "Revérification des affirmations datées", "en": "Re-check of dated claims"},
          {"fr": "Les affirmations dont la date est passée sont revérifiées sur le web.",
           "en": "Claims past their date are checked again on the web."}, MODEL, needs=("freshness",)),
    Check("deadlinks", {"fr": "Remplacement des liens morts", "en": "Replacement of dead links"},
          {"fr": "Pour chaque source morte, Claude cherche où la page a déménagé ou une source équivalente.",
           "en": "For each dead source, Claude looks for where the page moved or an equivalent source."},
          MODEL, needs=("sources",)),
]
RUNNERS = {"audits": run_audits, "sources": run_sources, "freshness": run_freshness, "coherence": run_coherence,
           "translation": run_translation, "claims": run_claims, "deadlinks": run_deadlinks}
BY_ID = {c.id: c for c in CHECKS}


def plan(selected: list[str]) -> list[str]:
    """Selected checks plus what they need, in catalogue order."""
    wanted = set(selected)
    for c in selected:
        wanted |= set(BY_ID[c].needs)
    return [c.id for c in CHECKS if c.id in wanted]
