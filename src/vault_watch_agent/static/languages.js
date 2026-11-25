// @ts-check
/* vault-watch: « Languages »: the pages ahead of their mirror, checked before translating if asked, then translated
   by a run. */

import { $, dollars, esc, page } from "./util.js";
import { api } from "./api.js";
import { lang, T } from "./texts.js";
import { bindSteps, costHtml, costOf, costTag, loadSteps, ownFor, stepLine, STEPS, stepsQuery } from "./steps.js";
import { wordDiff } from "./diff.js";
import { bindFixes, CHECK_STEP, fixesHtml } from "./proofread.js";

// A language by its code, in the language of the page (« anglais », « English »); the server's name otherwise
const languageName = (code, fallback) => { try { return new Intl.DisplayNames([lang], { type: "language" }).of(code) || fallback; } catch { return fallback; } };

// --- Sync the languages: the mirrors follow the source pages (GET/POST /api/mirrors) --------------------------
export async function viewLanguages() {
  await loadSteps();
  const L = T.languages, d = await api(`/api/mirrors${stepsQuery()}`);
  if (location.hash.slice(1) !== "/languages") return;  // left the page meanwhile
  if (!d.languages.length) {
    page.innerHTML = `<h1>${L.title}</h1><p class="muted">${L.noMirror}</p>`;
    return;
  }
  const card = (p, kind) => `<div class="card check-card"><label class="option">
      <input type="checkbox" data-kind="${kind}" data-page="${esc(p.page)}" data-usd="${p.usd}" checked>
      <div><div class="header"><code>${esc(p.page)}</code> <span class="badge attention">${costHtml("mirror", `≈ ${dollars(p.usd)}`)}</span></div>
        <p class="muted small">${L.passages(p.passages)}${p.since ? ` · ${L.since(esc(p.since.slice(0, 7)))}` : ""}</p></div></label>
      ${(p.hunks || []).length ? `<details class="hunks" open><summary>${L.zones(p.hunks.length)}</summary>${p.hunks.map(hunk).join("")}</details>` : ""}</div>`;
  // A changed zone of the page, two lines of context above and below it, the change as a word-level diff
  const around = lines => lines.length ? `<div class="context">${lines.map(l => esc(l) || "&nbsp;").join("\n")}</div>` : "";
  const hunk = h => { const [before, after] = wordDiff(h.old, h.new);
    return `<div class="hunk">${around(h.above)}${h.old ? `<div class="diff before">${before}</div>` : ""}${
      h.new ? `<div class="diff after">${after}</div>` : ""}${around(h.below)}</div>`; };
  const any = d.ahead.length + d.hand.length;
  page.innerHTML = `
    <h1>${L.title}</h1>
    <p class="subtitle">${L.intro(d.languages.map(l => esc(languageName(l.code, l.name))).join(", "))}</p>
    ${any ? "" : `<p class="banner">${L.none}</p>`}
    ${any > 1 ? `<p class="tick-row"><button type="button" class="small-button" data-tick="all">${L.tickAll}</button>
      <button type="button" class="small-button" data-tick="none">${L.untickAll}</button></p>` : ""}
    ${d.hand.length ? `<h2>${L.hand}</h2><p class="muted small">${L.handHelp}</p>${d.hand.map(p => card(p, "hand")).join("")}` : ""}
    ${d.ahead.length ? `<h2>${L.ahead}</h2><p class="muted small">${L.aheadHelp(esc(d.base))}</p>${d.ahead.map(p => card(p, "ahead")).join("")}` : ""}
    ${d.elsewhere.length ? `<p class="small attention-text">${L.elsewhere(d.elsewhere.map(p => `<code>${esc(p)}</code>`).join(", "))}</p>` : ""}
    ${any ? `<section class="card" id="proofread">${d.check ? checkFound(d.check) : checkOffer()}</section>` : ""}
    ${any ? `<details class="run-steps"${Object.keys(ownFor(["mirror"])).length ? " open" : ""}><summary>${T.perStep.title}</summary>
      ${STEPS.forced ? `<p class="muted small">${T.perStep.forced(STEPS.forced)}</p>` : ""}${stepLine("mirror", T.perStep.names.mirror)}</details>
    <p><button class="primary" id="sync"></button> <span class="error-text small" id="sync-error"></span></p>` : ""}`;
  bindSteps(page, () => viewLanguages());
  const boxes = () => [...page.querySelectorAll("input[data-page]")];
  bindCheck(d, boxes);
  const label = () => {
    const on = boxes().filter(b => b.checked), button = $("#sync");
    if (!button) return;
    button.disabled = !on.length;
    button.innerHTML = L.button(on.length, costHtml("mirror", `≈ ${dollars(on.reduce((sum, b) => sum + Number(b.dataset.usd), 0))}`));
  };
  boxes().forEach(b => { b.onchange = () => { label(); checkLabel(d, boxes); }; });
  page.querySelectorAll("[data-tick]").forEach(b => b.onclick = () => { boxes().forEach(x => { x.checked = b.dataset.tick === "all"; }); label(); checkLabel(d, boxes); });
  label();
  if (!$("#sync")) return;
  $("#sync").onclick = async () => {
    const on = boxes().filter(b => b.checked);
    $("#sync").disabled = true;
    try {
      const { thread } = await api("/api/mirrors", { pages: on.filter(b => b.dataset.kind === "ahead").map(b => b.dataset.page),
        hand: on.filter(b => b.dataset.kind === "hand").map(b => b.dataset.page), steps: ownFor(["mirror"]) });
      location.hash = `/run/${encodeURIComponent(thread)}`;
    } catch (e) {
      $("#sync-error").textContent = e.message;
      $("#sync").disabled = false;
    }
  };
}

// --- The edits checked before the sync (H4.2: POST /api/mirrors/check, proofread.py) --------------------------
let checkTimer = null;

function checkOffer() {
  const C = T.languages.check;
  return `<h2>${C.title}</h2><p class="muted small">${C.intro}</p>
    ${Object.keys(C.kinds).map(k => `<label class="option"><input type="checkbox" data-check="${k}">
      <div><b>${C.kinds[k]}</b> <span class="badge attention" data-check-usd="${k}"></span>
      <p class="muted small">${C.what[k]}</p></div></label>`).join("")}
    <p><button id="check-go"></button> <span class="error-text small" id="check-error"></span></p>`;
}

// What each check costs for the pages ticked: per page for the spelling and the facts, once for the consistency
function checkCost(d, boxes, kind) {
  if (kind === "consistency") return d.consistency_usd;
  const on = new Set(boxes().filter(b => b.checked).map(b => b.dataset.page));
  return [...d.hand, ...d.ahead].filter(p => on.has(p.page)).reduce((sum, p) => sum + (p.check_usd?.[kind] || 0), 0);
}

function checkLabel(d, boxes) {
  const C = T.languages.check, go = $("#check-go");
  if (!go) return;
  let total = 0, paid = false, free = "";
  page.querySelectorAll("[data-check-usd]").forEach(b => {
    const k = b.dataset.checkUsd, usd = checkCost(d, boxes, k), shown = `≈ ${dollars(usd)}`, label = costOf(CHECK_STEP[k], shown);
    b.innerHTML = costHtml(CHECK_STEP[k], shown);
    if (!page.querySelector(`[data-check="${k}"]`).checked) return;
    if (label === shown) { total += usd; paid = true; } else free = label;  // a step on a subscription or a local model
  });
  const asked = [...page.querySelectorAll("[data-check]:checked")];
  go.disabled = !asked.length || !boxes().some(b => b.checked);
  go.textContent = asked.length ? C.button(paid ? `≈ ${dollars(total)}` : free) : C.none;
}

function checkFound(c) {
  const C = T.languages.check;
  if (c.running || !c.done) return `<h2>${C.title}</h2><p class="muted">${C.running}</p>`;
  return `<h2>${C.title}</h2>
    ${c.error ? `<p class="error-text small">${C.error}${T.colon}${esc(c.error)}</p>` : ""}
    <p class="muted small">${C.found(c.fixes.length, costTag(c.cost, c.unbilled_usd || 0, false))}</p>
    ${fixesHtml(c.fixes, c.notes)}
    <p><button class="primary" id="check-apply"></button> <span class="error-text small" id="check-error"></span></p>`;
}

function bindCheck(d, boxes) {
  const C = T.languages.check, c = d.check;
  clearTimeout(checkTimer);
  if (!$("#proofread")) return;  // every page in line with its translation: nothing to check
  if (c && (c.running || !c.done)) {  // follow it until it is done
    checkTimer = setTimeout(() => { if (location.hash.slice(1) === "/languages") viewLanguages(); }, 1500);
    return;
  }
  if (c) {
    const label = () => { $("#check-apply").textContent = C.apply(pick.ids().length); };
    const pick = bindFixes(c.fixes, label);
    label();
    $("#check-apply").onclick = async () => {
      $("#check-apply").disabled = true;
      try {
        const done = await api(`/api/mirrors/check/${encodeURIComponent(c.id)}/accept`, { ids: pick.ids(), edits: pick.edits() });
        await viewLanguages();
        const failed = Object.keys(done.failed);
        if (failed.length) $("#proofread")?.insertAdjacentHTML("beforebegin", `<p class="banner">${C.failed} ${esc(failed.join(", "))}</p>`);
      } catch (e) { $("#check-error").textContent = e.message; $("#check-apply").disabled = false; }
    };
    return;
  }
  page.querySelectorAll("[data-check]").forEach(b => { b.onchange = () => checkLabel(d, boxes); });
  checkLabel(d, boxes);
  $("#check-go").onclick = async () => {
    const on = boxes().filter(b => b.checked), checks = [...page.querySelectorAll("[data-check]:checked")].map(b => b.dataset.check);
    $("#check-go").disabled = true;
    try {
      await api("/api/mirrors/check", { pages: on.filter(b => b.dataset.kind === "ahead").map(b => b.dataset.page),
        hand: on.filter(b => b.dataset.kind === "hand").map(b => b.dataset.page), checks,
        steps: ownFor(checks.map(k => CHECK_STEP[k])) });
      viewLanguages();
    } catch (e) { $("#check-error").textContent = e.message; $("#check-go").disabled = false; }
  };
}
