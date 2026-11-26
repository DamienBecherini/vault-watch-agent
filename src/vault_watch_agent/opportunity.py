"""The candidates of the registry judged with the whole guide in context (ROADMAP D4): the opportunity note.

The registry (candidates.py) follows what the agent found over time; its score (entities.py, D2) says how much was
said of a candidate and by whom, not whether the guide needs it. This check reads the whole guide with the open
candidates (their sources, what their pages said when the agent read them, their score, their history) and judges
each one: `add` (where it goes and which decision of the reader it changes), `watch` (what would make it worth adding,
and when to look again) or `dismiss` (why it changes no decision). Nothing is verified on the web here.

What becomes of it:
- each judgement is kept in its candidate (`judgement`, with the day and the check), shown on the page « Candidates »,
  so the editor moves it knowing why;
- a candidate to add is a lead of the check (news.Lead, kind « candidate »), which the editor sends to an addition
  run (news.propose: checked on primary sources, written where it belongs) or dismisses (then dismissed in the
  registry, as any lead of an addition check).

It runs as a check of `verify.py` (« candidates »), started from the page « Candidates » or « Check the guide ».
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from . import news, quotes

JUDGE = """You judge candidates for <<GUIDE>>: models, tools, hardware or other subjects that its watches and checks
found and that the guide does not cover yet. The whole guide is above, one <page> per file. Today is <<TODAY>>. Each
candidate below comes with the sources where it was seen, what its pages said when the agent read them, its score
(the tier of each independent publisher that spoke of it, added up, times the weeks it was seen) and its history.
Judge each one with the whole guide in mind:
- add: it would change a decision of the guide's reader (a choice of hardware, of model, of tool, a risk, an
  obligation), and the guide's threshold for additions is met or can be met on primary sources. Say where it goes
  (the page and its section, or that it needs a page of its own) and which decision of the reader it changes;
- watch: it may matter, but not yet (no weights, no measure, announced for later, a single source): say what would
  make it worth adding, and give a date to look again;
- dismiss: it changes no decision of the reader (off the guide's subject, a minor variant of what the guide covers,
  superseded, covered already): say why; a date to look again only when things may change.
You verify nothing on the web here: what you know may be out of date, and the sources listed are only what the agent
saw. Never write a figure, a version or a date as established. Judge every candidate listed, once, by its id. Follow
the guide's own threshold for additions, in its contract below. In `pages`, the pages the addition would go to; in
`read`, the other pages one must have read to write it well (<<READ>> at the most). In `excerpts`, copy verbatim the
passage of the guide the addition would sit next to or change (one sentence or one table row, two at most); none when
no page is close. Write the leads in English.<<BRIEF>>"""

MAX_JUDGED = 40  # candidates in one check: the open ones, the most seen first
OPEN = ("lead", "watching", "confirmed")  # the states a candidate is judged in, when none is named


class Judgement(BaseModel):
    id: str = Field(description="The id of the candidate, as listed.")
    verdict: Literal["add", "watch", "dismiss"]
    title: str = Field(default="", description="A short title, in the language the instructions name, 90 characters "
                       "at most.")
    pages: list[str] = Field(default_factory=list, description="add: vault-relative paths of the pages the addition "
                             "would go to; empty when it needs a page of its own. Else the pages that cover the subject "
                             "closest, if any.")
    read: list[str] = Field(default_factory=list, description="add: vault-relative paths of the other pages one must "
                            "have read to write it well. Not the pages of `pages`.")
    problem: str = Field(description="One self-contained line, in English. add: what to add and where, on which kind "
                         "of primary source to check it, and which decision of the reader it changes. watch: what would "
                         "make it worth adding. dismiss: why it changes no decision of the reader.")
    recheck: str = Field(default="", description="watch, and dismiss when things may change: a date to look again, "
                         "YYYY-MM-DD, after today. Else empty.")
    excerpts: list[quotes.Quote] = Field(default_factory=list)
    detail: news.LeadDetail | None = Field(default=None, description="The judgement explained to the editor, in the "
                                           "language the instructions name; empty when they say so.")


class Judgements(BaseModel):
    findings: list[Judgement]


def chosen(candidates: list[dict], ids: list[str], scores: dict[str, dict]) -> list[dict]:
    """The candidates to judge: those named (`ids`), else the open ones; the most seen first (the score of D2),
    MAX_JUDGED at most."""
    pool = [c for c in candidates if (c["id"] in ids if ids else c.get("state") in OPEN)]
    pool.sort(key=lambda c: -(scores.get(c["id"], {}).get("score") or 0))
    return pool[:MAX_JUDGED]


def listing(candidates: list[dict], scores: dict[str, dict]) -> str:
    """The candidates as the model reads them, one <candidate> each."""
    out = []
    for c in candidates:
        s = scores.get(c["id"], {})
        said = ", ".join(f"{p['publisher']}{' ' + p['tier'] if p.get('tier') else ''}" for p in s.get("publishers", []))
        state = c.get("state", "") + (f" ({c['reason']})" if c.get("reason") else "") + \
            (f", look again on {c['recheck']}" if c.get("recheck") else "")
        lines = [f'<candidate id="{c["id"]}">', f"name: {c['name']}" + (f" (also named {', '.join(c['aka'])})" if c.get("aka") else ""),
                 f"kind: {c.get('kind', '')}; state: {state}",
                 f"seen: {c.get('first_seen', '')} to {c.get('last_seen', '')}"
                 + (f"; score {s['score']} ({said or 'no source'}; {s['weeks']} week(s))" if s else "")]
        lines += ["sources:"] + [f"- {x['url']} ({x.get('seen', '')}, {x.get('origin', '')})" for x in c.get("sources", [])][:8]
        for f in c.get("facts", [])[:4]:
            lines.append(f"what its page said ({f.get('source', '')}, read {f.get('read', '')}): "
                         + "; ".join(f"{k} {v}" for k, v in f.items() if k not in ("url", "read", "source") and v not in (None, "")))
        lines += [f"history: {h.get('date', '')} {h.get('state', '')} {h.get('note', '')}".rstrip() for h in c.get("history", [])[-4:]]
        out.append("\n".join(lines) + "\n</candidate>")
    return "\n".join(out)


def kept(judged: list[Judgement], asked: list[dict]) -> list[Judgement]:
    """One judgement per candidate asked, in the order asked: the first `add` among those it got (a guide read
    chapter by chapter judges a candidate once per chapter), else the first."""
    by: dict[str, Judgement] = {}
    for j in judged:
        if j.id in by and not (j.verdict == "add" and by[j.id].verdict != "add"):
            continue
        by[j.id] = j
    return [by[c["id"]] for c in asked if c["id"] in by]


def lead(j: Judgement, c: dict) -> news.Lead:
    """A candidate to add, as a lead of the check: what an addition run takes (its sources go with it). Its title is
    the candidate's name: the registry finds it by it when the lead is dismissed."""
    return news.Lead(kind="candidate", title=c["name"][:90], pages=j.pages, read=j.read, problem=f"{c['name']}: {j.problem}",
                     excerpts=j.excerpts, sources=[s["url"] for s in c.get("sources", []) if s.get("url")][:5], detail=j.detail)


def said(j: Judgement) -> dict:
    """A judgement as the registry keeps it."""
    out = {"id": j.id, "verdict": j.verdict, "why": j.problem, "pages": j.pages, "recheck": j.recheck}
    if j.detail and j.detail.matters:
        out["matters"] = j.detail.matters
    return {k: v for k, v in out.items() if v not in ("", [])}
