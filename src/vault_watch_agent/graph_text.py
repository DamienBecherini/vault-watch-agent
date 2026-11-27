"""What a run writes for people: the report before the review, the usage and weight lines, the pull request's title
and description."""

from __future__ import annotations

import re

from . import news, quotes, verify
from .state import WatchState


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _source(url: str) -> str:
    """A correction's source as the pull request shows it: an http(s) address, else a page of the guide; nothing that
    could break the table or show as something else (a model wrote it, from what it read)."""
    url = str(url or "").strip()
    return url if re.fullmatch(r"https?://[^\s|<>]+|[\w./-]+\.mdx?", url) else ""


def has_members(corrections: list[dict], c: dict) -> bool:
    """Whether other corrections belong to the group named after `c`."""
    return any(o["group"] == c["id"] and o["id"] != c["id"] for o in corrections)


# ---------------------------------------------------------------------------
# Usage and weight
# ---------------------------------------------------------------------------


def usage_line(usage: list[dict]) -> str:
    tokens_in = sum(u["input"] + u.get("cache_read", 0) + u.get("cache_write", 0) for u in usage)
    tokens_out = sum(u["output"] for u in usage)
    cache = sum(u.get("cache_read", 0) for u in usage)
    cost = sum(u.get("cost_usd", 0.0) for u in usage)
    subscription = sum(1 for u in usage if u.get("engine") == "claude-code")  # Claude Code on a subscription: not billed
    worth = sum(u.get("list_usd") or 0.0 for u in usage if not u.get("cost_usd"))  # what they are worth at list price
    spared = (f" ({subscription} on the subscription, not billed{f'; worth {worth:.2f} $ at list price' if worth else ''})"
              if subscription else "")
    return f"{len(usage)} calls, {tokens_in:,} in ({cache:,} from cache) / {tokens_out:,} out, ≈ {cost:.2f} ${spared}"


def weight_line(w: dict) -> str:
    """What a run changes in the weight of the pages it edits (`weight` of the state): the total, then the pages
    that change the most."""
    line = (f"The pages changed weigh {w['before'] / 1024:.1f} KB before and {w['after'] / 1024:.1f} KB after "
            f"({(w['after'] - w['before']) / 1024:+.1f} KB), mirrors not counted.")
    most = [f"`{p}` {d / 1024:+.1f} KB" for p, d in (w.get("pages") or [])[:3] if abs(d) >= 512]
    return line + (f" Most: {', '.join(most)}." if most else "")


def largest_first(changes: dict[str, int]) -> list[list]:
    """The pages that change, as [[page, bytes]…], the largest change first (by page for the same size)."""
    return [[p, d] for p, d in sorted(changes.items(), key=lambda x: (-abs(x[1]), x[0])) if d]


def expected_weight(corrections: list[dict]) -> dict:
    """What the valid corrections would change if all were applied: {total, pages: [[page, bytes]…]}, in bytes of
    the source pages."""
    per: dict[str, int] = {}
    for c in corrections:
        if c["check"] == "ok":
            per[c["page"]] = per.get(c["page"], 0) + len(c["proposed"].encode("utf-8")) - len(c["current"].encode("utf-8"))
    return {"total": sum(per.values()), "pages": largest_first(per)}


def _weight_rows(corrections: list[dict]) -> list[str]:
    """The row of the report that says what the run would add to the pages, before the review."""
    w = expected_weight(corrections)
    if not w["pages"]:
        return []
    most = ", ".join(f"`{p}` {d / 1024:+.1f} KB" for p, d in w["pages"][:3])
    return [f"| Weight, if every valid correction is applied | {w['total'] / 1024:+.1f} KB on {len(w['pages'])} page(s), "
            f"mirrors not counted. Most: {most} |"]


# ---------------------------------------------------------------------------
# The report, before the review
# ---------------------------------------------------------------------------


def _pages_to_write(state: WatchState) -> list[str]:
    """An addition run: that it writes no new page, and the pages its leads would need, before anything else."""
    if state.get("mode") != "add":
        return []
    found = news.pages_to_write(dict(state))
    return ["## New pages: not written", "",
            f"{news.NO_NEW_PAGE} " + (f"{len(found)} lead(s) would need a page of their own, which stays your decision:"
                                      if found else "None of its leads asked for one."), "",
            *[f"- **{f['id']}** {f['what']} (lead: {_cell(f['lead'])})" for f in found], *([""] if found else [])]


def _correction_lines(c: dict, item: dict, corrections: list[dict]) -> list[str]:
    """One correction of the report: its heading, where it comes from, what the checks say, its texts."""
    check = "" if c["check"] == "ok" else f" — ⚠️ **{c['check']}**: cannot be applied as is"
    grouped = c["group"] != c["id"] or has_members(corrections, c)
    group = f" · group {c['group']} (applied whole)" if grouped else ""
    return [
        f"### {c['id']} · {c['severity']} · `{c['page']}`{group}{check}",
        "",
        f"From {', '.join(c['item_ids'])} [{item['title']}]({item['url']}). {c['rationale']}",
        "",
        *([f"Cross-check: {c['review']}", ""] if c.get("review") else []),
        *([f"⚠️ Source: {c['warning']}.", ""] if c.get("warning") else []),
        *([f"⚠️ No page states any more: {', '.join(c['lost'])}.", ""] if c.get("lost") else []),
        "Current:",
        "",
        *[f"> {line}" for line in c["current"].splitlines()],
        "",
        "Proposed (revised by the cross-check):" if c.get("proposed_initial") else "Proposed:",
        "",
        *[f"> {line}" for line in c["proposed"].splitlines()],
        "",
        f"Source: {c['source_url']}",
        "",
    ]


def render_report(state: WatchState, proposals: list[dict], corrections: list[dict]) -> str:
    items = {i["id"]: i for i in state["items"]}
    decisions = state["decisions"]
    count = {a: sum(1 for d in decisions if d["action"] == a) for a in ("correct", "addition", "drop")}
    sev = {s: sum(1 for c in corrections if c["severity"] == s) for s in ("Critical", "Major", "Minor")}
    lines = [
        f"# Watch report — {state['as_of']}",
        "",
        f"Source: {state['source']}. Generated by vault-watch-agent. **Read-only: no page modified** "
        "until the review.",
        "",
        "| Step | Result |",
        "| :-- | :-- |",
        f"| Triage | {len(items)} items → correct {count['correct']} · addition {count['addition']} · drop {count['drop']} |",
        f"| Proposals | Critical {sev['Critical']} · Major {sev['Major']} · Minor {sev['Minor']} |",
        f"| Claims past « Recheck by » | {len(state.get('claims_due', []))} (listed below; re-checked on the web by "
        f"the check « claims » of « Check the guide », ≈ {verify.CLAIM_USD} $ each) |",
        *([f"| Cross-check | {state['reading']['note']} |"] if state.get("reading") else []),
        f"| Model usage | {usage_line(state.get('usage', []))} |",
        *_weight_rows(corrections),
        "",
        *_pages_to_write(state),
        "## Corrections",
        "",
    ]
    if not corrections:
        lines.append("None.")
    # Members of a group side by side, including the ones the cross-check added
    num = lambda cid: int(cid[1:])
    for c in sorted(corrections, key=lambda c: (num(c["group"]), num(c["id"]))):
        lines += _correction_lines(c, items[c["item_id"]], corrections)
    lines += ["## Events and items without change", "", "| Item | Event | Why no change |", "| :-- | :-- | :-- |"]
    used = {i for c in corrections for i in c["item_ids"]}
    lines += [f"| {o['item_id']} {_cell(items[o['item_id']]['title'])} | {_cell(o['event'])} | {_cell(o['no_change_reason'])} |"
              for p in proposals for o in p["outcomes"] if o["item_id"] not in used]
    lines += ["", "## Addition candidates (not written, opportunity notes need a go-ahead)", ""]
    adds = [d for d in decisions if d["action"] == "addition"]
    lines += [f"- {d['item_id']} [{items[d['item_id']]['title']}]({items[d['item_id']]['url']}): {d['reason']}" for d in adds] or ["None."]
    lines += ["", "## Noticed elsewhere in the vault by the cross-check (not proposed)", ""]
    excerpts = state.get("finding_excerpts", {})
    lines += [line for f in state.get("findings", []) for line in (f"- {f}", *quotes.markdown(excerpts.get(f, [])))] \
        or ["None."]
    lines += ["", "## Removed values still present, left as they are", ""]
    lines += [f"- `{h['page']}:{h['line']}` ({', '.join(h['tokens'])}): {_cell(h['text'])}"
              for h in state.get("leftovers", [])] or ["None."]
    lines += ["", "## Claims due for re-check", ""]
    lines += [f"- {claim.get('recheckBy', '')} `{claim.get('page', '')}`: {_cell(str(claim.get('claim', '')))}"
              for claim in state.get("claims_due", [])]
    if not state.get("claims_due"):
        lines.append("None.")
    lines += ["", "## Dropped at triage", ""]
    lines += [f"- {d['item_id']} {items[d['item_id']]['title']}: {d['reason']}" for d in decisions if d["action"] == "drop"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# The pull request
# ---------------------------------------------------------------------------


def pr_title(state: WatchState) -> str:
    return state.get("title") or f"chore(watch): reviewed corrections, watch of {state['as_of']}"


PR_BODY_MAX = 60_000  # characters: GitHub refuses a description over 65 536


def pr_body(state: WatchState, limit: int = PR_BODY_MAX) -> str:
    """The description of the pull request, under `limit` characters. A run with many corrections loses, in this
    order and only as far as needed: the passages under its findings, the end of its « Why » cells, the last rows of
    its table (the commit message of the branch names every correction)."""
    if state.get("mode") == "mirror":
        return _mirror_pr_body(state)[:limit]
    count = len([c for c in state["corrections"] if c["id"] in state.get("applied", [])])
    for passages, why, rows in ((True, 0, count), (False, 0, count), (False, 120, count)):
        body = _pr_body(state, passages, why, rows)
        if len(body) <= limit:
            return body
    low, high = 0, count  # the most rows that fit
    while low < high:
        middle = (low + high + 1) // 2
        if len(_pr_body(state, False, 120, middle)) <= limit:
            low = middle
        else:
            high = middle - 1
    return _pr_body(state, False, 120, low)


# Where a proofreading of the editor's edits was asked, as the pull request says it
_PROOFREAD_AT = {"retouch": "at the retouches ", "publish": "before publishing "}


def watchlist_lines(state: WatchState) -> str:
    """The rows of the guide's watchlist that follow the corrections (watchlist.follow), as the pull request says
    them: those requoted and removed, then those left to the editor."""
    rows, error = state.get("watchlist") or [], state.get("watchlist_error") or ""
    if error:
        return f"⚠️ Watchlist not followed: {error}\n\n"
    if not rows:
        return ""
    done = [r for r in rows if r["ok"]]
    left = [r for r in rows if not r["ok"]]
    out = [f"Watchlist: {len(done)} row(s) follow the corrections (Checked, Status and Recheck by unchanged).\n"]
    out += [f"- `{r['page']}`: " + (f"{r['new']}" if r["action"] == "requote" else "row removed, its sentence is gone")
            + "\n" for r in done]
    if left:
        out.append(f"\n⚠️ Watchlist rows to requote by hand ({len(left)}), their quote no longer in the page:\n")
        out += [f"- `{r['file']}` line {r['line']} (`{r['page']}`): {r['old']}\n" for r in left]
    return "".join(out) + "\n"


def _checks_lines(state: WatchState) -> str:
    """The guide's audits, the mirrors and the external sources, as every pull request says them."""
    retouched, translated = state.get("retouched") or [], state.get("translation_retouched") or []
    edited, problems = state.get("publish_edits") or [], state.get("link_problems", [])
    parts: list[str] = []
    if retouched:
        parts.append(f"Retouched by the editor before the mirrors: {', '.join(f'`{p}`' for p in retouched)}.\n\n")
    parts += [f"The editor's edits proofread {_PROOFREAD_AT.get(x.get('from') or '', '')}({', '.join(x['checks'])}): "
              f"{x['fixes']} fix(es) proposed, {x['applied']} accepted.\n\n" for x in state.get("proofread_log") or []]
    if translated:
        parts.append(f"Translation retouched by the editor: {', '.join(f'`{p}`' for p in translated)}.\n\n")
    if edited:
        parts.append(f"Corrected by the editor before publishing: {', '.join(f'`{p}`' for p in edited)}.\n\n")
    audits = {True: "passed", None: "not checked (the guide declares no audits)"}.get(state.get("audit_ok"), "FAILED, see the log below")
    parts.append(f"Guide audits: {audits}.\n\n")
    if state.get("notes_removed"):
        parts.append(f"Footnotes removed with their last citation: {', '.join(f'`{n}`' for n in state['notes_removed'])}.\n\n")
    parts += [f"⚠️ Footnotes: {p}\n\n" for p in state.get("footnote_problems") or []]
    parts.append(watchlist_lines(state))
    parts.append(f"Mirrors updated: {', '.join(f'`{p}`' for p in state.get('mirrored', [])) or 'none'}.\n")
    parts += [f"- ⚠️ {p}\n" for p in state.get("mirror_problems", [])]
    parts.append("\nExternal sources of the changed pages (the guide's source audit): ")
    if problems is None:
        parts.append("not checked (the guide declares no source audit).\n")
    elif not problems:
        parts.append("all answer.\n")
    else:
        parts.append("\n" + "".join(f"- {p}\n" for p in problems))
    if state.get("audit_ok") is False:
        parts.append(f"\n```\n{state.get('audit_log', '')}\n```\n")
    return "".join(parts)


def _mirror_pr_body(state: WatchState) -> str:
    """A « Sync the languages » run: no correction, the source pages the mirrors were brought in line with."""
    hand = state.get("hand_pages", [])
    since = state.get("mirror_since", {})
    return (
        "The mirrors follow their source pages, passage by passage: what changed since each mirror was last "
        "translated, and what was edited by hand.\n\n"
        + (f"Edited by hand, committed on this branch: {', '.join(f'`{p}`' for p in hand)}.\n\n" if hand else "")
        + ("Ahead of their mirror on the base branch:\n\n"
           + "".join(f"- `{p}`, translated from {c[:7]}\n" for p, c in sorted(since.items())) + "\n" if since else "")
        + _checks_lines(state)
    )


def _pr_body(state: WatchState, passages: bool, why: int, rows_kept: int) -> str:
    applied = [c for c in state["corrections"] if c["id"] in state.get("applied", [])]
    cut = lambda text: text if not why or len(text) <= why else text[:why].rstrip() + "…"
    rows = "\n".join(f"| {c['id']}{' ✍️' if c.get('edited') else ''} | {c['severity']} | `{c['page']}` | "
                     f"{_cell(cut(c['rationale']))} | {_source(c['source_url'])} |" for c in applied[:rows_kept])
    retouches = sum(1 for c in applied if c.get("edited"))
    if retouches:
        rows += (f"\n\n✍️ {retouches} correction(s) retouched by the editor at the review: the text applied is theirs, "
                 "the model's proposal is in the report of the run.")
    if rows_kept < len(applied):
        rows += (f"\n\n{len(applied) - rows_kept} more, {applied[rows_kept]['id']} to {applied[-1]['id']}: the commit "
                 "message of the branch names every one.")
    shortened = ("" if passages and not why else
                 "\nThis description is shortened to fit: the report of the run, on the machine that ran it, has all of it.\n")
    # A fix run: the reported errors behind the applied corrections, with the passages they are about
    used = {i for c in applied for i in c.get("item_ids", [c["item_id"]])}
    reported = [i for i in state.get("items", []) if i.get("domain") == "fix" and i["id"] in used]
    errors = "".join(f"- {i['id']}: {i['title']}\n"
                     + ("".join(f"{line}\n" for line in quotes.markdown(i.get("excerpts", []))) if passages else "")
                     for i in reported)
    mode = state.get("mode")
    trims = mode == "compact"
    w = state.get("weight") or {}
    saved = weight_line(w) + "\n\n" if w.get("before") else ""
    # An addition run writes no new page: the ones its leads would need are said first
    pages = news.pages_to_write(dict(state)) if mode == "add" else []
    wanted = ("Not written: " + f"{len(pages)} subject(s) that would need a page of their own (the run adds to existing "
              "pages only).\n\n" + "".join(f"- {p['what']}\n" for p in pages) + "\n") if pages else ""
    # « What I already know »: said, never shown (the editor's own measurements, unpublished)
    noted = sum(1 for i in state.get("items", []) if i.get("editor_note"))
    known = (f"{noted} of them came with a note of the editor (their own measurements or experience, not published): "
             "used to check what the sources say, cited nowhere.\n\n") if noted else ""
    if trims:
        opening = f"Trims of {state['source']}, reviewed before apply: the guide weighs less and says no less.\n\n{saved}{known}"
    elif mode == "add":
        opening = (f"Additions from {state['source']}, each checked on primary sources and reviewed before apply.\n\n"
                   f"{saved}{known}{wanted}")
    else:
        opening = f"Corrections from {state['source']}, reviewed before apply.\n\n{saved}{known}"
    errors_title = "What weighed" if trims else "Leads" if mode == "add" else "Reported errors"
    return (
        opening
        + "| # | Severity | Page | Why | Source |\n| :-- | :-- | :-- | :-- | :-- |\n"
        f"{rows}\n\n"
        + (f"{errors_title}:\n\n{errors}\n" if errors else "")
        + _checks_lines(state)
        + shortened
        + (f"\nCloses #{state['issue']}.\n" if state.get("issue") else "")  # the watch is handled once merged
    )
