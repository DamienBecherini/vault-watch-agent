// @ts-check
/* vault-watch: « Report or suggest »: an error to fix, an idea to check, links to read whole; what is typed is kept
   as a draft in this browser. */

import { $, dollars, esc, page } from "./util.js";
import { api } from "./api.js";
import { lang, T } from "./texts.js";
import { billedStep, bindSteps, costOf, est, loadSteps, MODE_STEP, ownFor, stepLine, stepNow, STEPS, stepsQuery } from "./steps.js";

// What is typed on the three tabs of « Report or suggest » (fix, add, links): one draft per tab, kept while switching
// tabs and in this browser against a reload, a crash or a closed tab (written half a second after the last key, and
// when the page is left); emptied once the run or the check has started. One guide per server: per guide as well.
const DRAFTS = {}, UNSAVED = new Set();  // UNSAVED: typed here, not written yet (another tab may have sent it since)
const draftKey = k => `vault-watch-draft-${k}`;
const draft = k => k in DRAFTS ? DRAFTS[k] : (DRAFTS[k] = (() => { try { return localStorage.getItem(draftKey(k)) || ""; } catch { return ""; } })());
function storeDraft(k) {
  UNSAVED.delete(k);
  try { if ((DRAFTS[k] || "").trim()) localStorage.setItem(draftKey(k), DRAFTS[k]); else localStorage.removeItem(draftKey(k)); }
  catch { /* private window: kept while the page is open only */ }
}
let draftTimer = null;
addEventListener("pagehide", () => [...UNSAVED].forEach(storeDraft));

// A candidate of the registry proposed as an addition (candidates.js): its line added to the draft of « Propose an
// addition », and its id sent with the run, which marks it proposed (routes/candidates.py)
let FOR_CANDIDATE = null;  // {id, name}
/** @param {{id: string, name: string}} c @param {string} line */
export function proposeCandidate(c, line) {
  const now = draft("add").trim();
  DRAFTS.add = now && !now.split("\n").includes(line) ? `${now}\n${line}` : now || line;
  storeDraft("add");
  FOR_CANDIDATE = { id: c.id, name: c.name };
  location.hash = "/idea";
}
// The text area of tab `k` and the line under it that says the draft is kept, with « Clear » (and « Restore » after)
function bindDraft(k, area, note, changed = () => {}) {
  let undone = "";
  const say = () => {
    note.innerHTML = undone ? `${T.draft.cleared} <button type="button" class="link" data-draft="restore">${T.draft.restore}</button>`
      : area.value.trim() ? `${T.draft.kept} <button type="button" class="link" data-draft="clear">${T.draft.clear}</button>` : "";
    note.querySelector("[data-draft]")?.addEventListener("click", e => {
      if (e.target.dataset.draft === "clear") { undone = area.value; area.value = ""; } else { area.value = undone; undone = ""; }
      DRAFTS[k] = area.value;
      storeDraft(k);
      changed();
      say();
      area.focus();
    });
  };
  area.addEventListener("input", () => {
    DRAFTS[k] = area.value;
    UNSAVED.add(k);
    undone = "";
    clearTimeout(draftTimer);
    draftTimer = setTimeout(() => [...UNSAVED].forEach(storeDraft), 500);
    say();
  });
  say();
}
const dropDraft = k => { DRAFTS[k] = ""; storeDraft(k); };  // storeDraft takes it out of UNSAVED: the timer leaves it
// --- Report errors -----------------------------------------------------------------------------------
export async function viewReport(idea = false) {
  await loadSteps();
  const kind = idea ? "add" : "fix", wanted = [MODE_STEP[kind], "crosscheck", "mirror"];
  // What the run costs: said for the engine of the step that proposes (an addition run: from the estimate of its check)
  const news = idea ? (await api(`/api/verifications/options${stepsQuery()}`)).find(o => o.id === "news") || {} : {};
  const price = !billedStep(MODE_STEP[kind]) ? (stepNow(MODE_STEP[kind])?.billing === "subscription" ? T.reportSubscription : costOf(MODE_STEP[kind], ""))
    : idea ? T.ideaCost(`≈ ${dollars(news.run_usd)}`, `≈ ${dollars(news.run_usd_each)}`, `≈ ${dollars(news.run_usd_deep)}`) : T.reportCost;
  page.innerHTML = `
    <h1>${T.reportTitle}</h1>
    ${reportTabs(idea ? "idea" : "report")}
    <p class="subtitle">${idea ? T.ideaIntro : T.reportIntro} ${price}</p>
    ${idea ? `<p class="small attention-text">${T.ideaLimit}</p>` : ""}
    ${idea && FOR_CANDIDATE ? `<p class="banner small" id="for-candidate">${T.candidates.proposing(esc(FOR_CANDIDATE.name))}
      <button type="button" class="link" id="forget-candidate">${T.candidates.forget}</button></p>` : ""}
    <textarea id="text" placeholder="${esc(idea ? T.ideaExample : T.reportExample)}">${esc(draft(kind))}</textarea>
    <p class="muted small" id="draft-note"></p>
    ${idea ? `<p><label class="small"><input type="checkbox" id="deep"> ${T.ideaDeep}</label></p>` : ""}
    <details class="run-steps"${Object.keys(ownFor(wanted)).length ? " open" : ""}><summary>${T.perStep.title}</summary>
      ${STEPS.forced ? `<p class="muted small">${T.perStep.forced(STEPS.forced)}</p>` : ""}${wanted.map(s => stepLine(s, T.perStep.names[s])).join("")}</details>
    <p><button class="primary" id="send">${idea ? T.ideaButton : T.reportButton}</button> <span class="error-text small" id="send-error"></span></p>`;
  bindDraft(kind, $("#text"), $("#draft-note"));
  bindSteps(page, () => viewReport(idea));
  const forget = $("#forget-candidate");
  if (forget) forget.onclick = () => { FOR_CANDIDATE = null; $("#for-candidate").remove(); };
  $("#send").onclick = async () => {
    const text = $("#text").value.trim();
    if (!text) return;
    $("#send").disabled = true;
    const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
    try {  // the draft stays until the run has started: a refusal or a lost connection keeps the text
      const { thread } = await api("/api/fix", { text, mode: kind, steps: ownFor(wanted), ...(idea && $("#deep").checked ? { deep: lines } : {}),
        ...(idea && FOR_CANDIDATE ? { candidate: FOR_CANDIDATE.id } : {}) });
      if (idea) FOR_CANDIDATE = null;
      dropDraft(kind);
      location.hash = `/run/${encodeURIComponent(thread)}`;
    } catch (e) { $("#send-error").textContent = e.message; $("#send").disabled = false; }
  };
}

const reportTabs = on => `<p class="tabs">${[["report", "fix"], ["idea", "add"], ["links", "links"]].map(([h, k]) =>
  `<a href="#/${h}"${h === on ? ' class="active"' : ""}>${T.reportKinds[k]}</a>`).join("")}</p>`;

// Links to read whole (links.py): a check of its own, started here; its leads are ticked on the page of the check
export async function viewLinks() {
  await loadSteps();
  const [all, video] = await Promise.all([api(`/api/verifications/options${stepsQuery()}`), api("/api/videos")]);
  const o = all.find(x => x.id === "links") || {};
  const max = o.links_max || 10;
  const price = billedStep("links") ? T.linksCost(`≈ ${dollars(o.usd || 0)}`, `≈ ${dollars(est(o, "usd_link") || 0)}`, max)
    : stepNow("links")?.billing === "subscription" ? T.reportSubscription : costOf("links", "");
  page.innerHTML = `
    <h1>${T.reportTitle}</h1>
    ${reportTabs("links")}
    <p class="subtitle">${T.linksIntro} ${price}</p>
    <p class="small attention-text">${T.ideaLimit}</p>
    <p class="muted small">${video.ready ? (video.asleep ? T.linksVideoAsleep : T.linksVideoReady) : video.set ? T.linksVideoDown(esc(video.why)) : T.linksVideo}</p>
    <textarea id="text" placeholder="${esc(T.linksExample)}">${esc(draft("links"))}</textarea>
    <p class="muted small" id="draft-note"></p>
    <p class="small error-text" id="too-many" hidden>${T.linksTooMany(max)}</p>
    <details class="run-steps"${Object.keys(ownFor(["links"])).length ? " open" : ""}><summary>${T.perStep.title}</summary>
      ${STEPS.forced ? `<p class="muted small">${T.perStep.forced(STEPS.forced)}</p>` : ""}${stepLine("links", T.perStep.names.links)}</details>
    <p><button class="primary" id="send"></button> <span class="error-text small" id="send-error"></span></p>`;
  const found = () => [...new Set(($("#text").value.match(/https?:\/\/[^\s<>"']+/g) || []).map(a => a.replace(/[.,;:!?)\]}»]+$/, "")))];
  const count = () => {
    const n = found().length;
    $("#send").textContent = T.linksButton(n);
    $("#send").disabled = !n || n > max;
    $("#too-many").hidden = n <= max;
  };
  $("#text").oninput = count;
  count();
  bindDraft("links", $("#text"), $("#draft-note"), count);
  bindSteps(page, () => viewLinks());
  $("#send").onclick = async () => {
    $("#send").disabled = true;
    try {  // the draft stays until the check has started
      const { id } = await api("/api/verifications", { checks: ["links"], links: found(), lang, steps: ownFor(["links"]) });
      dropDraft("links");
      location.hash = `/check/${encodeURIComponent(id)}`;
    } catch (e) { $("#send-error").textContent = e.message; $("#send").disabled = false; }
  };
}
