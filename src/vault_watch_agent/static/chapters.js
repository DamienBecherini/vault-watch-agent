// @ts-check
/* vault-watch: « Chapters »: the split of the guide, seen, proposed by a model, edited by hand, declared in the
   manifest through a pull request. */

import { $, dollars, esc, extLink, page, tip } from "./util.js";
import { api } from "./api.js";
import { T } from "./texts.js";
import { bindSteps, costHtml, costOf, loadSteps, ownFor, stepLine, stepsQuery } from "./steps.js";

// --- The chapters of the guide: seen, proposed by a model, edited by hand, declared in the manifest ---------
let CH_EDIT = null;   // what is being edited: {rows: [{name, paths, explore}], why: {name: reason}, result, error, said, done}
let chaptersTimer = 0;
// Another screen: what was said here is said once; what is being edited stays, unless it was saved
export function leaveChapters() { if (CH_EDIT) CH_EDIT = CH_EDIT.done ? null : { ...CH_EDIT, said: "" }; }
export async function viewChapters() {
  await loadSteps();
  const d = await api(`/api/chapters${stepsQuery()}`), C = T.chapters;
  if (!CH_EDIT) CH_EDIT = { rows: d.chapters.filter(c => c.declared).map(c => ({ name: c.name, paths: c.paths, explore: c.explore })), why: {} };
  const E = CH_EDIT;
  const table = (rows, why) => `<div class="scroll-x"><table class="chapters"><thead><tr>${C.cols.map((c, i) => `<th${i === 1 || i === 2 ? ' class="num"' : ""}>${c}${i === 3 ? tip(C.tips.explore) : i === 4 ? tip(C.tips.origin) : ""}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>
      <td><b>${esc(r.name)}</b><div class="muted small">${esc(r.first)}${r.pages > 1 ? ` … ${esc(r.last)}` : ""}</div>${why?.[r.name] ? `<div class="small">${esc(why[r.name])}</div>` : ""}</td>
      <td class="num">${r.pages}</td><td class="num">${C.kb(Math.round(r.kb))}</td>
      <td>${r.explore ? C.yes : `<b>${C.no}</b>`}</td><td class="muted">${r.declared ? C.declared : C.auto}</td></tr>`).join("")}</tbody></table></div>`;
  const notes = list => list.length ? `<ul class="attention-text small">${list.map(n => `<li>${esc(n)}</li>`).join("")}</ul>` : "";
  const pending = d.pending?.pr_url;
  const canSave = d.from_manifest && !pending;
  page.innerHTML = `
    <h1>${C.title}</h1>
    <p class="subtitle">${C.intro}</p>
    ${pending ? `<p class="banner">${C.pending} ${extLink(d.pending.pr_url, "pull request ↗")}</p>` : ""}
    ${E.said ? `<p class="banner">${E.said}</p>` : ""}
    <h2>${C.now} <span class="badge neutral">${d.source === "manifest" ? C.sourceManifest : C.sourceAuto}</span></h2>
    <div class="card">${table(d.chapters)}${notes(d.notes)}<p class="muted small">${C.autoHelp(d.big_kb, d.small_kb)}</p></div>
    <h2>${C.change}</h2>
    <p class="muted">${C.changeHelp}</p>
    <div class="card check-card"><div class="option-text">
        <div class="header"><b>${C.askTitle}</b> <span class="badge attention">${costHtml("chapters", `≈ ${dollars(d.usd)}`)}</span></div>
        <p class="muted small">${C.askWhat}</p>
        <p><button id="ask">${C.ask(costHtml("chapters", `≈ ${dollars(d.usd)}`))}</button> <span class="error-text small" id="ask-error"></span></p>
      </div><div class="card-foot">${stepLine("chapters")}</div></div>
    <h3>${C.byHand}</h3>
    <p class="muted small">${C.pathsHelp}</p>
    <div id="rows">${E.rows.map((r, i) => `<div class="card chapter-row" data-row="${i}">
      <div class="chapter-fields">
        <label class="small">${C.name}<input type="text" data-f="name" value="${esc(r.name)}" maxlength="80"></label>
        <label class="small"><span>${C.paths}${tip(C.tips.paths)}</span><textarea data-f="paths" rows="${Math.min(8, Math.max(2, r.paths.length))}" spellcheck="false">${esc(r.paths.join("\n"))}</textarea></label>
      </div>
      ${E.why[r.name] ? `<p class="muted small">${esc(E.why[r.name])}</p>` : ""}
      <div class="actions"><label class="small"><input type="checkbox" data-f="explore" ${r.explore ? "checked" : ""}> ${C.explore}</label>${tip(C.tips.explore)}
        <span class="spacer"></span><button type="button" class="small-button danger" data-remove="${i}">${C.remove}</button></div>
    </div>`).join("") || `<p class="muted">${C.empty}</p>`}</div>
    <p class="actions"><button type="button" id="add-row">${C.add}</button>
      <span><button type="button" id="from-now">${C.fromNow}</button>${tip(C.tips.fromNow)}</span></p>
    <h2>${C.result}</h2>
    <p class="muted">${C.resultHelp}</p>
    <div id="result"></div>
    ${d.source === "manifest" ? `<p><button type="button" class="small-button" id="back-auto"${canSave ? "" : " disabled"}>${C.backAuto}</button>${tip(C.tips.backAuto)}</p>` : ""}`;
  const read = () => [...page.querySelectorAll("[data-row]")].map(row => ({
    name: row.querySelector("[data-f=name]").value.trim(),
    paths: row.querySelector("[data-f=paths]").value.split("\n").map(p => p.trim()).filter(Boolean),
    explore: row.querySelector("[data-f=explore]").checked }));
  const keep = () => { E.rows = read(); };
  const failed = (where, e) => { $(where).textContent = e.message; };
  // Step 3 is drawn by itself: what the chapters of step 2 would give, then the button that saves it
  const drawResult = busy => {
    const r = E.result;
    $("#result").innerHTML = !E.rows.length ? `<p class="muted">${C.resultEmpty}</p>`
      : E.error ? `<p class="error-text" role="status">${esc(E.error)}</p>`
      : !r ? `<p class="muted" role="status">${C.updating}</p>`
      : `<div class="card${busy ? " updating" : ""}">${table(r.chapters, E.why)}${notes(r.notes)}
        <details><summary class="small">${C.toml}</summary><pre class="toml">${esc(r.toml)}</pre>
          <button type="button" class="small-button" id="copy-toml">${C.copy}</button></details></div>
      <p class="muted small">${d.from_manifest ? C.saveHelp(d.manifest, d.base) : C.noManifest}</p>
      ${d.from_manifest ? `<p class="small attention-text">${C.needs(d.needs)}</p>` : ""}
      <p><button type="button" class="primary" id="save"${canSave && !busy ? "" : " disabled"}>${d.has_repo ? C.save(d.forge) : C.saveLocal}</button>
        <span class="error-text small" id="save-error"></span></p>`;
    if ($("#save")) $("#save").onclick = () => save(E.rows, $("#save"));
    if ($("#copy-toml")) $("#copy-toml").onclick = async () => {
      try { await navigator.clipboard.writeText(E.result.toml); $("#copy-toml").textContent = C.copied; } catch { /* no clipboard: the text is selectable */ }
    };
  };
  const compute = async () => {   // asked again after each change; an answer that comes after a newer change is dropped
    const rows = E.rows, asked = JSON.stringify(rows);
    if (!rows.length) { E.result = null; E.error = ""; drawResult(); return; }
    try {
      const result = await api("/api/chapters/preview", { chapters: rows });
      if (JSON.stringify(E.rows) !== asked) return;
      E.result = result; E.error = "";
    } catch (e) {
      if (JSON.stringify(E.rows) !== asked) return;
      E.result = null; E.error = e.message;
    }
    if (location.hash === "#/chapters") drawResult();
  };
  const changed = () => {   // typed: the result follows, half a second after the last key
    keep();
    drawResult(true);
    clearTimeout(chaptersTimer);
    chaptersTimer = setTimeout(compute, 500);
  };
  $("#rows").oninput = changed;
  $("#add-row").onclick = () => { keep(); E.rows.push({ name: "", paths: [], explore: true }); E.result = null; viewChapters(); };
  $("#from-now").onclick = () => { CH_EDIT = { rows: d.chapters.map(c => ({ name: c.name, paths: c.cover, explore: c.explore })), why: {} }; viewChapters(); };
  page.querySelectorAll("[data-remove]").forEach(b => b.onclick = () => { keep(); E.rows.splice(Number(b.dataset.remove), 1); E.result = null; viewChapters(); });
  $("#ask").onclick = async () => {
    const b = $("#ask");
    b.disabled = true;
    b.textContent = C.asking;
    try {
      const p = await api("/api/chapters/propose", { steps: ownFor(["chapters"]) });
      CH_EDIT = { rows: p.chapters.filter(c => c.declared).map(c => ({ name: c.name, paths: c.paths, explore: c.explore })), why: p.why, result: p,
                  said: C.asked(costOf("chapters", dollars(p.cost))) };
      viewChapters();
    } catch (e) { b.disabled = false; b.innerHTML = C.ask(costHtml("chapters", `≈ ${dollars(d.usd)}`)); failed("#ask-error", e); }
  };
  const save = async (chapters, button) => {
    button.disabled = true;
    try {
      const done = await api("/api/chapters", { chapters });
      CH_EDIT = { rows: chapters, why: {}, done: true, said: done.pr_url ? `${C.saved} ${extLink(done.pr_url, "pull request ↗")}` : esc(C.savedLocal(done.branch, done.base)) };
      viewChapters();
    } catch (e) { button.disabled = false; ($("#save-error") || $("#ask-error")).textContent = e.message; }
  };
  if ($("#back-auto")) $("#back-auto").onclick = () => save([], $("#back-auto"));
  bindSteps(page, () => { keep(); viewChapters(); });
  drawResult();
  if (E.rows.length && !E.result && !E.error) compute();
}
