// @ts-check
/* vault-watch: the pause to retouch the pages of the branch (lend the folder to Obsidian, or edit here), and the
   banner shown on every screen while the folder is lent or something set aside is not put back. */

import { $, esc, obsidian, page, tip } from "./util.js";
import { api } from "./api.js";
import { T } from "./texts.js";
import { addedPart, highlightEditor, hlNav } from "./editor.js";
import { route } from "./router.js";
import { bindProof, proofChecks } from "./proofread.js";

// --- The pause to retouch the pages of the branch (H3): lend the folder to Obsidian, or edit here ---------------
export async function viewRetouch(r, title) {
  const R = T.retouchPause, at = `/api/runs/${encodeURIComponent(r.thread)}`;
  const f = await api(`${at}/folder`).catch(e => ({ error: e.message, changes: [] }));
  const lent = f.lent_to === r.thread, pages = r.pause?.pages || [];
  const folderCard = f.error ? `<p class="error-text">${esc(f.error)}</p>`
    : lent ? `<p>${R.lentNow(esc(f.path))}</p><p><button id="take-back">${R.takeBack}</button>${tip(R.takeBackHelp)}</p>`
    : f.lent_to ? `<p class="attention-text">${R.lentOther(esc(f.lent_to))}</p>`
    : f.blocked ? `<p class="attention-text">${R.blocked(esc(f.blocked))}</p>`
    : f.changes.length ? `<p>${R.dirty(f.changes.length)}</p><ul>${f.changes.map(c => `<li><code>${esc(c)}</code></li>`).join("")}</ul>
        <p class="muted small">${R.setAsideHelp}</p><p><button id="lend" data-aside="1">${R.setAside}</button></p>`
    : `<p><button id="lend">${R.lend}</button>${tip(R.lendHelp(f.path))}</p>`;
  // Each page: open it in the editor below, or in Obsidian once the folder is lent (before, Obsidian shows main)
  const vaultName = (f.path || "").split(/[\\/]/).filter(Boolean).pop() || "";
  const pageRow = p => `<li><code>${esc(p)}</code> <button type="button" class="small-button" data-open-here="${esc(p)}">${R.openHere}</button>
    ${lent ? `<a class="small" href="${obsidian(vaultName, p)}">${R.openObsidian}</a>` : `<a class="muted small" href="#" data-to-lend title="${esc(R.obsidianLater)}">${R.openObsidian}</a>`}</li>`;
  page.innerHTML = `${title}
    <div class="card"><p>${R.intro((r.applied || []).length, esc(r.branch || ""))}</p>
      ${pages.length ? `<p class="small"><b>${R.pages}</b></p><ul class="retouch-pages">${pages.map(pageRow).join("")}</ul>
        ${lent ? "" : `<p class="muted small">${R.obsidianFirst(`<a href="#" data-to-lend>${R.lendFirst}</a>`)}</p>`}` : ""}</div>
    <h2>${R.obsidian}</h2>
    <div class="card" id="folder-card">${folderCard}${lent ? "" : `<p class="muted small">${R.whyLend}</p>`}<p class="error-text small" id="lend-error"></p></div>
    <h2>${R.here}</h2>
    <div class="card" id="here"><p class="muted small">${R.hereHelp(lent)}</p>
      <p class="tick-row"><select id="page-pick">${pages.map(p => `<option>${esc(p)}</option>`).join("")}</select>
        <input id="page-other" type="text" placeholder="${esc(R.other)}" spellcheck="false">
        <button type="button" id="page-open">${R.open}</button></p>
      <div id="editor" hidden><p class="small hl-head"><code id="page-name"></code> <span class="badge attention" id="page-dirty" hidden>${R.unsaved}</span> ${hlNav()}</p>
        <textarea id="page-text" spellcheck="true"></textarea>
        <p class="muted small">${R.undoHelp}</p>
        <p class="tick-row"><button type="button" id="page-save" disabled>${R.save}</button>
          <button type="button" id="page-revert">${R.close}</button> <span class="small" id="page-said"></span></p></div></div>
    <h2>${R.proofTitle}</h2>
    <div class="card" id="proof-card"><p class="muted small">${R.proofIntro}</p>${proofChecks(true)}
      <p class="muted small" id="proof-pages"></p></div>
    <p class="error-text" id="done-error"></p>
    <div class="bar"><button id="skip">${R.skip}</button><button class="primary" id="done">${R.done}</button></div>`;
  let open = "";
  const proof = await bindProof($("#proof-card"), at, p => {
    $("#done").textContent = p.asked.length ? R.doneProof(p.cost) : R.done;
    $("#proof-pages").innerHTML = p.pages.length ? R.proofPages(p.pages.map(x => `<code>${esc(x)}</code>`).join(" · "))
      : `${R.proofNone} <button type="button" class="small-button" id="proof-refresh">${R.proofRefresh}</button>`;
    if ($("#proof-refresh")) $("#proof-refresh").onclick = () => proof.refresh();
  });
  if ($("#take-back")) $("#take-back").onclick = async () => {
    $("#take-back").disabled = true;
    try { await api(`${at}/folder/back`, {}); route(); }
    catch (e) { $("#lend-error").textContent = e.message; $("#take-back").disabled = false; }
  };
  if ($("#lend")) $("#lend").onclick = async () => {
    $("#lend").disabled = true;
    try { await api(`${at}/folder`, { set_aside: !!$("#lend").dataset.aside }); route(); }
    catch (e) { $("#lend-error").textContent = e.message; $("#lend").disabled = false; }
  };
  // The editor: the text as last saved is kept, so that what is not saved is said, and can be cancelled
  let saved = "";
  const dirty = () => !!open && $("#page-text").value !== saved;
  const said = () => {
    $("#page-dirty").hidden = !dirty();
    $("#page-save").disabled = !dirty();
    $("#page-revert").textContent = dirty() ? R.revert : R.close;  // nothing to cancel: it closes the page
  };
  let marked = null;  // the passages highlighted in the editor (highlightEditor), made with its first page
  const load = async path => {
    if (!path || (dirty() && !confirm(R.confirmLeave))) return;
    try {
      const p = await api(`${at}/page?path=${encodeURIComponent(path)}`);
      open = p.path;
      saved = p.text;
      $("#page-text").value = p.text;
      $("#page-name").textContent = p.path;
      $("#editor").hidden = false;
      $("#page-said").textContent = "";
      $("#page-text").style.height = "auto";
      $("#page-text").style.height = `${Math.min(window.innerHeight * 0.7, $("#page-text").scrollHeight + 4)}px`;
      // What the corrections applied to this page, in green; the editor opened at the first
      const passages = (r.corrections || []).filter(c => (r.applied || []).includes(c.id) && c.page === p.path).map(c => addedPart(c.current, c.proposed));
      marked ||= highlightEditor($("#page-text"), passages, $("#editor .hl-nav"));
      marked.set(passages);
      marked.go(0);
      said();
    } catch (e) { $("#page-said").textContent = e.message; $("#editor").hidden = false; }
  };
  $("#page-open").onclick = () => load($("#page-other").value.trim() || $("#page-pick").value);
  page.querySelectorAll("[data-open-here]").forEach(b => b.onclick = async () => {
    $("#page-pick").value = b.dataset.openHere;
    $("#page-other").value = "";
    await load(b.dataset.openHere);
    $("#here").scrollIntoView({ block: "start", behavior: "smooth" });
  });
  $("#page-text").oninput = said;
  // « Lend your folder first »: the button comes into view and glows for a moment (the card, when it has none)
  page.querySelectorAll("[data-to-lend]").forEach(a => a.onclick = e => {
    e.preventDefault();
    const target = $("#lend") || $("#folder-card");
    target.scrollIntoView({ block: "center", behavior: "smooth" });
    target.classList.remove("flash");
    void target.offsetWidth;  // the glow starts again on a second click
    target.classList.add("flash");
    setTimeout(() => target.classList.remove("flash"), 1800);
    if (target.id === "lend") setTimeout(() => target.focus({ preventScroll: true }), 400);
  });
  $("#page-save").onclick = async () => {
    if (!open) return;
    try {
      const wrote = await api(`${at}/page`, { path: open, text: $("#page-text").value });
      saved = $("#page-text").value;
      // Not lent: what was saved is in the run's copy only; the pages retouched so far are named
      const outside = lent ? [] : (wrote.changed || []).filter(p => /\.mdx?$/.test(p));
      $("#page-said").innerHTML = `${R.saved}${outside.length ? ` <span class="muted">${R.savedHere(outside.map(p => `<code>${esc(p)}</code>`).join(" · "))}</span>` : ""}`;
      said();
      proof.refresh();  // what the proofreading would read, and cost, now
    } catch (e) { $("#page-said").textContent = e.message; }
  };
  // Back to the text as last saved: typed over (not set), so that Ctrl+Z can still bring the changes back
  $("#page-revert").onclick = () => {
    if (!dirty()) {  // nothing changed: the page is closed
      open = saved = "";
      $("#editor").hidden = true;
      return;
    }
    const t = $("#page-text");
    t.focus();
    t.select();
    if (!document.execCommand?.("insertText", false, saved)) t.value = saved;
    t.setSelectionRange(0, 0);
    t.scrollTop = 0;
    $("#page-said").textContent = R.reverted;
    said();
  };
  const finish = async keep => {
    page.querySelectorAll(".bar button").forEach(b => b.disabled = true);
    try { await api(`${at}/retouched`, { keep, proofread: keep ? proof.asked() : [] }); route(); }
    catch (e) { $("#done-error").textContent = e.message; page.querySelectorAll(".bar button").forEach(b => b.disabled = false); }
  };
  $("#done").onclick = () => (!dirty() || confirm(R.confirmLeave)) && finish(true);
  $("#skip").onclick = () => (!lent && !open) || confirm(R.confirmSkip) ? finish(false) : null;
}

// A banner on every page while the guide's folder is lent to a run, or something set aside is not put back yet
export async function asideBanner() {
  const list = await api("/api/folder/aside").catch(() => []);
  document.querySelector("#aside-banner")?.remove();
  if (!list.length) return;
  const R = T.retouchPause, x = list[0];
  const div = document.createElement("p");
  div.id = "aside-banner";
  div.className = "banner";
  div.innerHTML = `${esc(R.banner(x.thread, x.lent, x.aside.length))} <a href="#/run/${encodeURIComponent(x.thread)}">${R.see}</a>${
    x.lent ? "" : ` <button type="button" class="small-button" id="put-back">${R.putBack}</button>`}`;
  page.prepend(div);
  const b = /** @type {HTMLButtonElement | null} */ (div.querySelector("#put-back"));
  if (b) b.onclick = async () => { try { await api(`/api/folder/aside/${encodeURIComponent(x.thread)}`, {}); asideBanner(); } catch (e) { div.append(` ${e.message}`); } };
}
