"""The nodes from the branch to the pull request: the mirrors follow the source pages → the translation shown in a
« Sync the languages » run (interrupt) → the guide's audits → the link checks → the last go-ahead (interrupt), where
the editor can also correct the branch and have it translated, proofread or checked again."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from langgraph.types import interrupt

from . import forge, inputs, mirrors, prompts, proofread, retouch, steps, vault
from .graph_common import git
from .graph_text import pr_body, pr_title
from .guide import Guide, language_name
from .state import MirrorEdit, MirrorResult, WatchState

if TYPE_CHECKING:
    from .graph_common import Deps
    from .llm import LLM

MIRROR_NOTES = ("A passage whose new text is empty was removed: give the matching passage of the mirror page as "
                "`current` and leave `proposed` empty. A passage whose new text begins or ends with its old text adds "
                "what follows or precedes it: quote the matching mirror passage and add the translation next to it. "
                "The mirror page may already say some of the new text (a page edited by hand in both languages): "
                "give no edit for what it already says.")


# -- mirror (the pages of each mirror of the manifest follow the edits of the source) ---------------
def mirror(deps: Deps, state: WatchState) -> dict:
    """The mirrors follow what changed in the source pages on the branch, paragraph by paragraph (mirrors.py):
    the corrections applied, and whatever was edited by hand. A page listed in `mirror_since` is translated from
    that commit instead of the base (a page ahead of its mirror before the run). An edit whose quote the mirror page
    does not have exactly once goes back to the translator once, alone with the others missed: only what is still
    missed then is skipped (said in `mirror_problems`)."""
    wt = Path(state["worktree"])
    translator = deps.translator or deps.llm
    guide = vault.guide_of(wt)
    base = git("merge-base", deps.base, "HEAD", cwd=wt).strip()
    since = {page: base for page in mirrors.changed_pages(wt, base)} | dict(state.get("mirror_since") or {})
    again = dict(state.get("mirror_only") or {})  # asked again from the publish pause: these pages only
    if again:
        since = again
    mirrored, problems, usage, pairs = [], [], [], []
    for (code, folder), page in ((m, p) for m in sorted(guide.mirrors.items()) for p in sorted(since)):
        changed = mirrors.edits_of(wt, page, since[page])
        if not changed:
            continue
        en = f"{folder}{page}"
        if not (wt / en).is_file():
            problems.append(f"{en}: no mirror in {language_name(code)}")
            continue
        result, u = _translate(translator, wt, guide, code, page, en, changed)
        usage.append(u)
        if result.problem:
            problems.append(f"{en}: {result.problem}")
        done, missed = _apply_mirror_edits(deps, wt, guide, en, result.edits)
        if ask := [m for m in missed if m[1] in _ASK_AGAIN]:
            # quotes the page does not have once: the translator is asked once more, for those edits only
            retry, u = _translate_again(translator, wt, code, en, ask)
            usage.append(u)
            if retry.problem:
                problems.append(f"{en}: {retry.problem}")
            more, still = _apply_mirror_edits(deps, wt, guide, en, retry.edits)
            done += more
            missed = [m for m in missed if m[1] not in _ASK_AGAIN] + still
        problems += [f"{en}: quoted text {_MISSED[why]} in the mirror, even when asked again: edit skipped"
                     if why in _MISSED else f"{en}: edit skipped ({why})" for _, why in missed]
        # What changed in the source page beside what the translator made of it: shown side by side, so that the
        # translation can be judged (and, in a « Sync the languages » run, retouched)
        pairs.append({"page": page, "mirror": en, "source": [list(c) for c in changed], "target": done,
                      "problem": result.problem})
        if done:
            mirrored.append(en)
    if mirrored:
        git("add", *mirrored, cwd=wt)
        git("commit", "-m", "chore(i18n): sync the mirrors with the source pages", cwd=wt)
    tip = git("rev-parse", "HEAD", cwd=wt).strip()
    if not again:
        return {"mirrored": mirrored, "mirror_problems": problems, "usage": usage, "mirror_pairs": pairs, "mirror_tip": tip}
    # The pages translated again replace their pairs and their problems; the others are kept as they were
    kept = [p for p in state.get("mirror_pairs", []) if p["page"] not in again]
    earlier = [x for x in state.get("mirror_problems", [])
               if not any(x.startswith(f"{f}{p}:") for f in guide.mirrors.values() for p in again)]
    return {"mirrored": sorted(set(state.get("mirrored", [])) | set(mirrored)), "usage": usage,
            "mirror_problems": earlier + problems, "mirror_pairs": kept + pairs, "mirror_only": {}, "mirror_tip": tip}


def _translate(translator: LLM, wt: Path, guide: Guide, code: str, page: str, en: str,
               changed: list[tuple[str, str]]) -> tuple[MirrorResult, dict]:
    """One model call: what changed in the source page `page`, passage by passage, carried to its mirror page `en`."""
    edits = "\n\n".join(f"<edit>\n<old_source>\n{old}\n</old_source>\n<new_source>\n{new}\n</new_source>\n</edit>"
                        for old, new in changed)
    prompt = (f"Page `{en}` of the {language_name(code)} mirror:\n\n<mirror_page>\n{vault.read(wt / en)}\n"
              f"</mirror_page>\n\nWhat changed in the {language_name(guide.language)} page `{page}`, passage by "
              f"passage:\n\n{edits}\n\n{MIRROR_NOTES}")
    return translator.parse(system=prompts.mirror(wt, code), prompt=prompt, schema=MirrorResult, effort=steps.effort("mirror"),
                            node=f"mirror {en}")


_MISSED = {"text-not-found": "not found", "ambiguous": "found more than once"}
# What the translator is told when asked again, by `vault.check`'s answer
_ASK_AGAIN = {"text-not-found": "this `current` is not in the page",
              "ambiguous": "this `current` occurs more than once in the page: quote a longer passage, one that occurs once"}


def _translate_again(translator: LLM, wt: Path, code: str, en: str,
                     missed: list[tuple[MirrorEdit, str]]) -> tuple[MirrorResult, dict]:
    """A second call for the edits whose quote the mirror page `en` does not have once, each with why, against the
    page as it now stands (the other edits applied): the translator copies the passage again, verbatim."""
    edits = "\n\n".join(f"<edit>\n<current>\n{e.current}\n</current>\n<proposed>\n{e.proposed}\n</proposed>\n"
                        f"<why>{_ASK_AGAIN.get(why, why)}</why>\n</edit>" for e, why in missed)
    prompt = (f"Page `{en}` of the {language_name(code)} mirror, as it now stands:\n\n<mirror_page>\n{vault.read(wt / en)}\n"
              f"</mirror_page>\n\nThese edits of the page could not be placed: an edit's `current` must be copied from "
              f"the page above, character for character, and occur in it exactly once.\n\n{edits}\n\nGive each edit again: "
              "`current` copied verbatim from the page (same letters, spaces, punctuation, Markdown, links and footnote "
              "markers), longer when the passage occurs more than once, and `proposed` the same translation, widened "
              "as `current` was. Give no edit for a passage the page no longer has or already says as `proposed` does.")
    return translator.parse(system=prompts.mirror(wt, code), prompt=prompt, schema=MirrorResult, effort=steps.effort("mirror"),
                            node=f"mirror {en} (asked again)")


def _apply_mirror_edits(deps: Deps, wt: Path, guide: Guide, en: str,
                        edits: list[MirrorEdit]) -> tuple[list[list[str]], list[tuple[MirrorEdit, str]]]:
    """The translator's edits applied to the mirror page `en`: [[current, proposed]…] of those applied, and the edits
    whose quote the page does not have exactly once, with why (`vault.check`). A quote that differs from the page
    only by what a reader does not see (`vault.loose_match`) is applied to the page's own text."""
    done, missed = [], []
    for e in edits:
        if vault.date_bump_only(e.current, e.proposed, guide.modified_field) or e.current == e.proposed:
            continue  # apply bumps the date itself; an edit the mirror already carries changes nothing
        current, proposed, why = e.current, e.proposed, vault.check(wt, en, e.current)
        if why == "text-not-found" and (found := vault.loose_match(vault.read(wt / en), current)):
            # the copy's own spaces around it are not in the page: the translation does not bring them either
            current, proposed, why = found, (proposed.strip() if current != current.strip() else proposed), "ok"
        if why != "ok":
            missed.append((e, why))
            continue
        vault.apply(wt, en, current, proposed, deps.today)
        done.append([current, proposed])
    return done, missed


# -- translation (interrupt): a « Sync the languages » run shows the translation beside its source, editable ---
def translation(deps: Deps, state: WatchState) -> dict:
    """The pause of a « Sync the languages » run after the mirrors: each passage of the source beside its
    translation, the translation editable. A text retouched replaces the translator's in the mirror page (found
    once, as any edit), committed as the editor's; the guide's checks and the links run after. Other runs go on."""
    if state.get("mode") != "mirror" or not any(p["target"] for p in state.get("mirror_pairs", [])):
        return {}
    answer = interrupt({"step": "translation", "pages": [p["mirror"] for p in state["mirror_pairs"] if p["target"]],
                        "question": "The translation, beside its source: 'ok', or {'edits': {'<mirror page>#<n>': text}}"})
    edits = (answer.get("edits") or {}) if isinstance(answer, dict) else {}
    wt = Path(state["worktree"])
    pairs = [dict(p, target=[list(t) for t in p["target"]]) for p in state["mirror_pairs"]]
    problems, changed = list(state.get("mirror_problems", [])), set()
    for key, text in edits.items():
        page, _, n = key.rpartition("#")
        pair = next((p for p in pairs if p["mirror"] == page), None)
        if not pair or not n.isdigit() or int(n) >= len(pair["target"]):
            continue
        target = pair["target"][int(n)]
        text = text.replace("\r\n", "\n")
        if text == target[1] or not target[1].strip():
            continue  # unchanged, or a passage the translation removed: nothing to retouch
        if vault.check(wt, page, target[1]) != "ok":
            problems.append(f"{page}: the translation retouched could not be placed (its text is not found once)")
            continue
        vault.apply(wt, page, target[1], text, deps.today)
        target.extend([target[1]])  # [current, text applied, the translator's]
        target[1] = text
        changed.add(page)
    if changed:
        git("add", *sorted(changed), cwd=wt)
        git("commit", "-q", "-m", "chore(i18n): the translation retouched at the review", cwd=wt)
    return {"mirror_pairs": pairs, "mirror_problems": problems, "translation_retouched": sorted(changed)}


# -- audits (the guide's own checks, [checks] audits, no model) ---------------
def audits(deps: Deps, state: WatchState) -> dict:
    notes = {"footnote_problems": footnote_problems(deps, Path(state["worktree"]))}
    try:
        log = inputs.check("audits", Path(state["worktree"]))
    except RuntimeError as e:
        return {"audit_ok": False, "audit_log": str(e)[-3000:], "recheck": "", **notes}
    if log is None:  # None: not checked (the publish screen says so)
        return {"audit_ok": None, "audit_log": "not checked: the guide declares no [checks] audits", "recheck": "", **notes}
    return {"audit_ok": True, "audit_log": log[-3000:], "recheck": "", **notes}


def footnote_problems(deps: Deps, wt: Path) -> list[str]:
    """The footnotes a reader would find broken in the pages of the branch, sources and mirrors (vault.footnote_problems):
    « page: never cited [^22], [^23] ». The guide's own checks may not look at them; said before the pull request."""
    out = []
    for page in git("diff", "--name-only", f"{deps.base}...HEAD", cwd=wt).split():
        if not page.endswith(".md") or not (wt / page).is_file():
            continue
        found = vault.footnote_problems(vault.read(wt / page))
        said = [f"{what} " + ", ".join(f"[^{n}]" for n in found[key])
                for key, what in (("never_cited", "never cited"), ("undefined", "cited, never defined"), ("twice", "defined twice"))
                if found[key]]
        if said:
            out.append(f"{page}: {'; '.join(said)}")
    return out


# -- links: the external sources of the changed pages still answer (vault script, no model) --
def links(deps: Deps, state: WatchState) -> dict:
    wt = Path(state["worktree"])
    out = deps.home / "downloads" / f"sources-{state['branch'].replace('/', '-')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        if inputs.check("sources", wt, out) is None:
            return {"link_problems": None}  # the guide declares no [checks] sources: not checked
    except RuntimeError as e:
        return {"link_problems": [f"source audit could not run: {str(e)[:200]}"]}
    added = git("diff", "-U0", f"{deps.base}...HEAD", cwd=wt)
    added = "\n".join(line for line in added.splitlines() if line.startswith("+"))
    return {"link_problems": link_problems(json.loads(out.read_text(encoding="utf-8")),
                                           {c["page"] for c in state["corrections"] if c["id"] in state["applied"]},
                                           added)}


BROKEN = {"dead", "server-error", "network-error", "timeout"}


def link_problems(report: dict, pages: set[str], added: str) -> list[str]:
    """Sources of the changed pages that do not answer, new ones (added by this run) first.

    `blocked` (403 from anti-bot protections) is listed apart: the page usually opens in a browser.
    """
    rows = []
    for s in report.get("sources", []):
        status = (s.get("probe") or {}).get("status")
        cited = sorted({c["page"] for c in s.get("citations", []) if c["page"] in pages})
        if not cited or status not in BROKEN | {"blocked"}:
            continue
        new = s["url"] in added
        code = (s.get("probe") or {}).get("code") or ""
        label = "blocked by the site (anti-bot?), check in a browser" if status == "blocked" else f"{status} {code}".strip()
        rows.append((status == "blocked", not new, f"{'NEW ' if new else ''}{label}: {s['url']} ({', '.join(cited)})"))
    return [r[2] for r in sorted(rows)]


# -- publish (interrupt 2) -------------------------------------------------
def publish(deps: Deps, state: WatchState) -> dict:
    diffstat = git("diff", "--stat", f"{deps.base}...HEAD", cwd=Path(state["worktree"]))
    go = interrupt(
        {
            "step": "publish",
            "branch": state["branch"],
            "audit_ok": state["audit_ok"],
            "mirror_problems": state.get("mirror_problems", []),
            "link_problems": state.get("link_problems", []),
            "footnote_problems": state.get("footnote_problems", []),
            "diffstat": diffstat,
            "local": not deps.repo,  # no repository: the branch stays on this machine
            "question": "Push the branch and open the pull request? yes / no" if deps.repo else
                        f"The guide has no repository: the corrections stay on the branch {state['branch']}. yes / no",
        }
    )
    wt = Path(state["worktree"])
    if isinstance(go, dict) and go.get("action") in ("recheck", "retranslate", "proofread"):
        return correct_again(deps, state, wt, go)
    if go is not True or not deps.repo:
        return {}
    git("push", "-u", "origin", state["branch"], cwd=wt)
    body = pr_body(state)
    url = forge.get().open_pull_request(deps.repo, base=deps.base, head=state["branch"], title=pr_title(state),
                                        body=body, cwd=wt)
    return {"pr_url": url}


def correct_again(deps: Deps, state: WatchState, wt: Path, asked: dict) -> dict:
    """Asked at the publish pause, once the page has corrected files of the branch (source or mirror pages): what
    was corrected is committed as the editor's, then the run checks again, or translates again first: the French
    corrected since the mirrors (`fresh` false), or a page whose translation starts over from the base (`fresh`);
    or has what was corrected proofread first (`proofread`, its `checks`), then translated and checked."""
    before = git("rev-parse", "HEAD", cwd=wt).strip()
    edited = retouch.changed(wt)
    if edited:
        git("add", "-A", cwd=wt)
        git("commit", "-q", "-m", "Corrected at the publish review", cwd=wt)
    out = {"recheck": "audits", "publish_edits": sorted(set(state.get("publish_edits") or []) | set(edited))}
    if asked["action"] == "proofread":
        return out | {"recheck": "proofread", "proofread_from": "publish", "proofread_since": before,
                      "proofread_checks": [c for c in proofread.CHECKS if c in (asked.get("checks") or [])]}
    if asked["action"] != "retranslate":
        return out
    base = git("merge-base", deps.base, "HEAD", cwd=wt).strip()
    since, guide = {}, vault.guide_of(wt)
    for page in asked.get("pages") or []:
        if asked.get("fresh"):  # its translation starts over: the mirror back to the base, then translated again
            _mirror_back_to(base, wt, guide, page)
            since[page] = base
        else:
            since[page] = state.get("mirror_tip") or base
    return out | {"recheck": "mirror", "mirror_only": since}


def _mirror_back_to(base: str, wt: Path, guide: Guide, page: str) -> None:
    """The mirrors of `page` as they are on the base branch, committed: its translation starts over."""
    for folder in guide.mirrors.values():
        if git("ls-tree", "--name-only", base, "--", f"{folder}{page}", cwd=wt).strip():
            git("checkout", "-q", base, "--", f"{folder}{page}", cwd=wt)
    if retouch.changed(wt):
        git("commit", "-q", "-am", f"chore(i18n): the translation of {page} started over", cwd=wt)
