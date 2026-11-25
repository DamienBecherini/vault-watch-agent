// @ts-check
/* vault-watch: the fixes of a proofreading, ticked and retouched: before a sync (« Languages »), and inside a run, on
   the editor's own edits at the retouches and at the publish step. */

import { $, dollars, esc, extLink, page } from "./util.js";
import { api } from "./api.js";
import { T } from "./texts.js";
import { en } from "./explain.js";
import { costHtml, costOf } from "./steps.js";
import { wordDiff } from "./diff.js";
import { route } from "./router.js";

export const CHECK_STEP = { spelling: "proofread", facts: "factcheck", consistency: "crosscheck" };
// The fixes of a proofreading, page by page: each ticked (unless its text is gone, or it overlaps an earlier one),
// its diff, its text editable; then the doubts without a fix
export function fixesHtml(fixes, notes) {
  const C = T.languages.check, byPage = {};
  fixes.forEach(f => (byPage[f.page] ||= []).push(f));
  return `${Object.entries(byPage).map(([p, list]) => `<div class="pair-page"><div class="header"><code>${esc(p)}</code></div>
      ${list.map(f => { const [before, after] = wordDiff(f.current, f.proposed), ok = f.check === "ok", over = (f.overlaps || []).length;
        return `<label class="option fix"><input type="checkbox" data-fix="${esc(f.id)}"${!ok ? " disabled" : over ? "" : " checked"}>
          <div><p class="small"><span class="badge">${C.kinds[f.kind]}</span> ${en(f.reason)}${
            f.source_url ? ` · ${extLink(f.source_url, C.source)}` : ""}${
            ok ? "" : ` · <span class="attention-text">${C.notFound}</span>`}${
            over ? ` · <span class="attention-text">${C.overlaps(f.overlaps.join(", "))}</span>` : ""}</p>
          <div class="diff before">${before}</div><div class="diff after" data-fix-after="${esc(f.id)}">${after || `<span class="muted">—</span>`}</div>
          ${ok ? `<span class="edit-label">${T.editable}</span><textarea class="editable" data-fix-text="${esc(f.id)}" spellcheck="true">${esc(f.proposed)}</textarea>` : ""}</div></label>`; }).join("")}
    </div>`).join("")}
    ${notes.length ? `<p class="small"><b>${C.notes}</b></p><ul class="small">${notes.map(n => `<li>${en(n)}</li>`).join("")}</ul>` : ""}`;
}

// What the editor ticked of the fixes drawn by fixesHtml, with their own texts: {ids(), edits()}
export function bindFixes(fixes, onChange) {
  const ids = () => [...page.querySelectorAll("[data-fix]:checked")].map(b => b.dataset.fix);
  page.querySelectorAll("[data-fix]").forEach(b => { b.onchange = onChange; });
  page.querySelectorAll("[data-fix-text]").forEach(t => {
    const f = fixes.find(x => x.id === t.dataset.fixText);
    const fit = () => { t.style.height = "auto"; t.style.height = `${t.scrollHeight + 4}px`; };
    fit();
    t.oninput = () => { page.querySelector(`[data-fix-after="${CSS.escape(f.id)}"]`).innerHTML = wordDiff(f.current, t.value)[1]; fit(); };
  });
  const edits = () => Object.fromEntries(ids().map(id => [id, page.querySelector(`[data-fix-text="${CSS.escape(id)}"]`)?.value])
    .filter(([id, text]) => text != null && text !== fixes.find(x => x.id === id).proposed));
  return { ids, edits };
}

// --- The editor's own edits proofread inside a run (graph.proofread): offered at the retouches and the publish step
export function proofChecks(withWhat) {
  const C = T.languages.check;
  return Object.keys(C.kinds).map(k => `<label class="option"><input type="checkbox" data-proof="${k}">
    <div><b>${C.kinds[k]}</b> <span class="badge attention" data-proof-usd="${k}"></span>${
      withWhat ? `<p class="muted small">${C.what[k]}</p>` : ""}</div></label>`).join("");
}

// The checks' estimates for what the editor changed (GET …/proofread/estimate), asked again on `refresh`; `onChange`
// gets what is ticked, its cost as shown (billed, or what a subscription takes) and the pages it would read
export async function bindProof(root, at, onChange) {
  let est = { pages: [], usd: {} };
  const boxes = () => [...root.querySelectorAll("[data-proof]")];
  const asked = () => boxes().filter(b => b.checked).map(b => b.dataset.proof);
  const cost = () => {
    let usd = 0, paid = false, free = "";
    asked().forEach(k => {
      const shown = `≈ ${dollars(est.usd[k] || 0)}`, label = costOf(CHECK_STEP[k], shown);
      if (label === shown) { usd += est.usd[k] || 0; paid = true; } else free = label;
    });
    return asked().length ? (paid ? `≈ ${dollars(usd)}` : free) : "";
  };
  const draw = () => {
    root.querySelectorAll("[data-proof-usd]").forEach(b => { b.innerHTML = costHtml(CHECK_STEP[b.dataset.proofUsd], `≈ ${dollars(est.usd[b.dataset.proofUsd] || 0)}`); });
    boxes().forEach(b => { b.disabled = !est.pages.length; if (b.disabled) b.checked = false; });
    onChange({ asked: asked(), cost: cost(), pages: est.pages });
  };
  const refresh = async () => { est = await api(`${at}/proofread/estimate`).catch(() => est); draw(); };
  boxes().forEach(b => { b.onchange = draw; });
  await refresh();
  return { asked, refresh };
}

// The pause on what the proofreading found: the fixes to apply, retouched or not, then the run goes on
export function viewProofread(r, title) {
  const C = T.languages.check, Q = T.proofPause, fixes = r.proofread_fixes || [], notes = r.proofread_notes || [];
  const last = (r.proofread_log || []).slice(-1)[0] || { checks: [] };
  page.innerHTML = `${title}
    <div class="card"><p>${Q.intro(last.from === "publish")}</p>
      <p class="muted small">${Q.what(last.checks.map(k => C.kinds[k]).join(", "))}</p></div>
    ${fixesHtml(fixes, notes)}
    <p class="error-text" id="proof-error"></p>
    <div class="bar"><button class="primary" id="proof-go"></button></div>`;
  const label = () => { $("#proof-go").textContent = Q.apply(pick.ids().length); };
  const pick = bindFixes(fixes, label);
  label();
  $("#proof-go").onclick = async () => {
    $("#proof-go").disabled = true;
    try { await api(`/api/runs/${encodeURIComponent(r.thread)}/proofread`, { ids: pick.ids(), edits: pick.edits() }); route(); }
    catch (e) { $("#proof-error").textContent = e.message; $("#proof-go").disabled = false; }
  };
}
