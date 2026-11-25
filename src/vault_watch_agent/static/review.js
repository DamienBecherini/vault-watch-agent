// @ts-check
/* vault-watch: the review of a run's corrections: ticked by group under their lead, retouched before they apply. */

import { $, esc, extLink, page, shortUrl } from "./util.js";
import { api } from "./api.js";
import { T } from "./texts.js";
import { en } from "./explain.js";
import { changeView, excerpts } from "./diff.js";
import { route } from "./router.js";

// The texts retouched in the review, by run and correction: kept while the page is open, sent with the review
const RETOUCH = {};
const mineOf = (r, id) => RETOUCH[r.thread]?.[id];

function correctionCard(c, r) {
  const valid = c.check === "ok";
  const mine = mineOf(r, c.id), text = mine ?? c.proposed;
  // Where it comes from is said once, by the block of its lead (viewReview); a correction without one says it here
  const sources = (c.item_ids || [c.item_id]).filter(id => !r.items[id]?.shown).map(id => r.items[id]).filter(Boolean)
    .map(i => i.url ? extLink(i.url, esc(i.title)) : esc(i.title)).join(" · ");
  return `<div class="card correction${valid ? "" : " rejected"}">
    <input type="checkbox" data-id="${c.id}" data-group="${c.group}" ${valid ? "checked" : "disabled"} aria-label="${T.applyId(c.id)}">
    <div>
      <div class="header"><b>${c.id}</b><span class="badge ${c.severity}">${c.severity}</span><code>${esc(c.page)}</code>
        ${valid ? "" : `<span class="badge error">${esc(c.check)}</span>`}</div>
      <p>${en(c.rationale)}</p>
      ${c.review ? `<p class="muted small">${T.crossCheck}${T.colon}${en(c.review)}</p>` : ""}
      ${c.warning ? `<p class="small">⚠️ ${T.sourceMissing}${T.colon}${en(c.warning)}</p>` : ""}
      ${c.lost?.length ? `<p class="small">⚠️ ${T.lostValues}${T.colon}${esc(c.lost.join(", "))}</p>` : ""}
      <div data-diff="${c.id}">${changeView(c.current, text)}</div>
      ${c.retouchable ? `<div class="retouch" data-retouch="${c.id}" ${mine === undefined ? "hidden" : ""}>
        <p class="muted small">${T.retouchHelp}</p>
        <textarea class="editable" data-text="${c.id}" lang="fr" spellcheck="true">${esc(text)}</textarea>
        <p class="small"><span data-retouch-state="${c.id}"></span>
          <button type="button" class="small-button" data-retouch-back="${c.id}">${T.retouchBack}</button></p></div>` : ""}
      <div class="muted small">${sources ? `${T.from} ${sources} · ` : ""}${c.source_url ? `${extLink(c.source_url, "source")}` : ""}
        ${c.retouchable ? ` · <button type="button" class="small-button" data-retouch-open="${c.id}"${mine === undefined ? "" : " hidden"}>✎ ${T.retouch}</button>` : ""}</div>
    </div>
  </div>`;
}

export function viewReview(r, title) {
  const num = id => Number(id.slice(1));
  const groups = {};
  for (const c of [...r.corrections].sort((a, b) => num(a.group) - num(b.group) || num(a.id) - num(b.id)))
    (groups[c.group] ||= []).push(c);
  const broken = new Set(r.corrections.filter(c => c.check !== "ok").map(c => c.group));
  // The groups under the lead of their first correction, the leads in their order (F1, F2…); a lead says where it
  // comes from once: its number and title on the check's page, its source, the English text the run was given
  const byLead = new Map();
  for (const [g, cs] of Object.entries(groups)) {
    const k = (cs[0].item_ids || [cs[0].item_id])[0] || "";
    if (!byLead.has(k)) byLead.set(k, []);
    byLead.get(k).push([g, cs]);
  }
  const leadOrder = [...byLead.keys()].sort((a, b) => (num(a) || 1e9) - (num(b) || 1e9));
  leadOrder.forEach(k => { if (r.items[k]) r.items[k].shown = true; });
  const groupBlock = ([g, cs]) => cs.length > 1
    ? `<div class="group"><label class="group-head"><input type="checkbox" data-group-box="${g}" aria-label="${esc(T.group(g))}">
        <b>${T.groupLinked(cs.length)}</b> <span class="muted small">${broken.has(g) ? T.groupLeftOut : T.groupWhy}</span></label>
        ${cs.map(c => correctionCard(c, r)).join("")}</div>`
    : correctionCard(cs[0], r);
  const leadBlock = k => {
    const i = r.items[k], gs = byLead.get(k);
    if (!i) return gs.map(groupBlock).join("");
    const cs = gs.flatMap(([, x]) => x), pages = new Set(cs.map(c => c.page)).size;
    const name = i.name ? esc(i.name) : i.url ? extLink(i.url, esc(i.title)) : esc(i.title);
    return `<section class="lead-block">
      <div class="lead-head">${i.n ? `<span class="muted small">${T.leadN(i.n)}</span>` : ""}<b>${name}</b>
        <span class="badge neutral">${T.leadCount(cs.length, pages)}</span></div>
      ${i.name ? `<p class="muted small">${i.url ? `${T.leadSource}${T.colon}${extLink(i.url, esc(shortUrl(i.url)))} · ` : ""}${
        i.verification ? `<a href="#/check/${encodeURIComponent(i.verification)}">${T.seeCheck}</a>` : ""}</p>
        <details class="sent"><summary class="small muted">${T.verif.sentText}</summary><p class="small muted">${esc(i.title)}</p></details>` : ""}
      ${i.editor_note ? `<div class="lead-note"><div class="note-shown"><b>📝 ${T.verif.noteTitle}</b> <span class="muted small">${T.verif.noteHint}</span><p>${esc(i.editor_note)}</p></div></div>` : ""}
      ${gs.map(groupBlock).join("")}</section>`;
  };
  const figures = [Object.values(r.triage).reduce((a, b) => a + b, 0), r.triage.correct, r.corrections.length, r.additions.length];
  page.innerHTML = `${title}
    <div class="figures">${figures.map((n, i) => `<div><b>${n}</b>${T.reviewFigures[i]}</div>`).join("")}</div>
    ${r.reading?.mode === "chapters" ? `<p class="banner small">${T.byChapter(r.reading.tokens, r.reading.budget)}</p>` : ""}
    ${r.mode === "add" ? `<div class="card notice"><p><strong>${T.noNewPage}</strong> ${T.pagesToWrite(r.pages_to_write.length)}</p>
      ${r.pages_to_write.length ? `<ul>${r.pages_to_write.map(p => `<li><strong>${esc(p.id)}</strong> ${esc(p.what)}<br><span class="muted small">${esc(p.lead)}</span></li>`).join("")}</ul>` : ""}</div>
    ${r.unchanged.length ? `<div class="card notice unchanged"><p><strong>${T.unchanged(r.unchanged.length)}</strong></p>
      <ul>${r.unchanged.map(u => { const i = r.items[u.id] || {}; return `<li><strong>${i.n ? T.leadN(i.n) : esc(u.id)}${i.name ? ` · ${esc(i.name)}` : ""}</strong><br>
        <span class="small">${esc(u.why)}</span><details class="sent"><summary class="small muted">${T.verif.sentText}</summary><p class="small muted">${esc(u.lead)}</p></details></li>`; }).join("")}</ul></div>` : ""}` : ""}
    <h2>${T.corrections}</h2>
    <p class="muted small">${T.reviewHelp}</p>
    ${leadOrder.map(leadBlock).join("") || `<p class="muted">${T.noCorrection}</p>`}
    <details><summary>${T.leads(r.additions.length)}</summary>
      <ul>${r.additions.map(a => `<li>${a.url ? extLink(a.url, esc(a.title)) : esc(a.title)}${T.colon}${esc(a.reason)}</li>`).join("") || `<li>${T.none}</li>`}</ul></details>
    <details><summary>${T.noticed(r.findings.length)}</summary>
      <ul>${r.findings.map(f => `<li>${esc(f)}${excerpts(r.finding_excerpts?.[f])}</li>`).join("") || `<li>${T.nothing}</li>`}</ul>
      ${r.findings.length ? `<p class="muted small">${T.noticedHelp}</p>` : ""}</details>
    <details><summary>${T.leftovers(r.leftovers.length)}</summary>
      <ul>${r.leftovers.map(h => `<li><code>${esc(h.page)}:${h.line}</code> (${esc(h.tokens.join(", "))}) : ${esc(h.text)}</li>`).join("") || `<li>${T.none}</li>`}</ul></details>
    <details><summary>${T.claims(r.claims_due.length)}</summary>
      <ul>${r.claims_due.map(c => `<li>${esc(c.recheckBy)} <code>${esc(c.page)}</code> : ${esc(c.claim)}</li>`).join("") || `<li>${T.none}</li>`}</ul></details>
    <p class="small"><a href="/api/runs/${encodeURIComponent(r.thread)}/report" target="_blank">${T.report}</a></p>
    ${r.billed_next ? `<p class="error-text">${T.billedNext}</p>` : ""}
    <div class="bar">
      <button id="nothing">${T.applyNothing}</button>
      <button class="primary" id="apply"></button>
    </div>`;
  const boxes = [...page.querySelectorAll(".correction input")];
  boxes.filter(i => broken.has(i.dataset.group)).forEach(i => { i.checked = false; i.disabled = true; });
  // A group of several corrections is ticked by its own box (its members' boxes are hidden): one choice
  const groupBoxes = [...page.querySelectorAll("[data-group-box]")];
  const members = g => boxes.filter(o => o.dataset.group === g);
  const count = () => {
    const n = boxes.filter(i => i.checked).length;
    $("#apply").textContent = T.applyN(n);
    $("#apply").disabled = n === 0;
    groupBoxes.forEach(b => { b.checked = members(b.dataset.groupBox).every(o => o.checked); b.disabled = broken.has(b.dataset.groupBox); });
  };
  boxes.forEach(i => i.onchange = () => {
    boxes.filter(o => o.dataset.group === i.dataset.group && !o.disabled).forEach(o => o.checked = i.checked);
    count();
  });
  groupBoxes.forEach(b => b.onchange = () => {
    members(b.dataset.groupBox).filter(o => !o.disabled).forEach(o => { o.checked = b.checked; });
    count();
  });
  count();
  const send = async (accept, edits = {}) => {
    page.querySelectorAll(".bar button").forEach(b => b.disabled = true);
    await api(`/api/runs/${encodeURIComponent(r.thread)}/review`, { accept, edits });
    delete RETOUCH[r.thread];
    route();
  };
  bindRetouches(r, boxes);
  const edits = () => Object.fromEntries(Object.entries(RETOUCH[r.thread] || {})
    .filter(([id, text]) => text !== r.corrections.find(c => c.id === id)?.proposed));
  $("#apply").onclick = () => send(boxes.filter(i => i.checked).map(i => i.dataset.id), edits());
  $("#nothing").onclick = () => confirm(T.confirmNothing) && send("none");
}

// « Retouch » on the cards of a review: the text follows the typing in the diff, the free checks are asked a moment
// after the last key (POST /api/runs/<run>/retouch), and a retouched correction is ticked with its group
function bindRetouches(r, boxes) {
  const mine = RETOUCH[r.thread] ||= {};
  const proposal = id => r.corrections.find(c => c.id === id);
  const timers = {};
  const show = (id, text) => { page.querySelector(`[data-diff="${id}"]`).innerHTML = changeView(proposal(id).current, text); };
  const ask = id => {
    clearTimeout(timers[id]);
    const state = page.querySelector(`[data-retouch-state="${id}"]`);
    if (mine[id] === undefined || mine[id] === proposal(id).proposed) { state.innerHTML = ""; return; }
    state.innerHTML = `<span class="muted">${T.retouchChecking}</span>`;
    timers[id] = setTimeout(async () => {
      const said = await api(`/api/runs/${encodeURIComponent(r.thread)}/retouch`, { edits: { [id]: mine[id] } }).catch(e => ({ [id]: { check: e.message } }));
      const x = said[id] || {};
      state.innerHTML = `<span class="badge ${x.check === "ok" ? "ok" : "error"}">${x.check === "ok" ? T.retouched : esc(T.retouchProblem(x.check))}</span>${
        x.warning ? ` <span class="small">⚠️ ${T.sourceMissing}${T.colon}${esc(x.warning)}</span>` : ""}`;
    }, 500);
  };
  const fit = t => { t.style.height = "auto"; t.style.height = `${t.scrollHeight + 4}px`; };  // the whole text, no inner scroll
  const tick = id => {
    const box = boxes.find(b => b.dataset.id === id);
    if (box && !box.disabled && !box.checked) { box.checked = true; box.onchange(); }
  };
  page.querySelectorAll("[data-retouch-open]").forEach(b => b.onclick = () => {
    const id = b.dataset.retouchOpen;
    mine[id] = mine[id] ?? proposal(id).proposed;
    page.querySelector(`[data-retouch="${id}"]`).hidden = false;
    b.hidden = true;
    fit(page.querySelector(`[data-text="${id}"]`));
    page.querySelector(`[data-text="${id}"]`).focus();
  });
  page.querySelectorAll("[data-text]").forEach(t => {
    const id = t.dataset.text;
    t.oninput = () => { mine[id] = t.value; show(id, t.value); tick(id); ask(id); fit(t); };
    if (!t.closest("[hidden]")) fit(t);
    ask(id);
  });
  page.querySelectorAll("[data-retouch-back]").forEach(b => b.onclick = () => {
    const id = b.dataset.retouchBack;
    delete mine[id];
    page.querySelector(`[data-text="${id}"]`).value = proposal(id).proposed;
    page.querySelector(`[data-retouch="${id}"]`).hidden = true;
    page.querySelector(`[data-retouch-open="${id}"]`).hidden = false;
    show(id, proposal(id).proposed);
    ask(id);
  });
}
