// @ts-check
/* vault-watch: the page of one check: its results and its leads, ticked, dug deeper, with a note, then sent to the
   runs that check them (rules.js says what may be ticked). */

import { $, dollars, esc, extLink, followLater, keepRoomForBar, leadParts, linked, obsidian, origin, page, shortUrl, stopFollowing, tip } from "./util.js";
import { api } from "./api.js";
import { kb, lang, signedKb, T } from "./texts.js";
import { billedStep, bindSteps, costHtml, costOf, costTag, loadSteps, MODE_STEP, ownFor, stepCard, STEPS, stepsQuery } from "./steps.js";
import { excerpts } from "./diff.js";
import { badge, FINISHED } from "./watches.js";
import { checkBadge } from "./checks.js";
import { LeadRules } from "./rules.js";

const OPEN_LEADS = new Set();  // the leads unfolded, kept while the page is open (verification/line)
// The options of the bar of a check, opened or folded: the reader's choice, kept in the browser
let BAR_OPEN = (() => { try { return localStorage.getItem("vault-watch-bar-open") === "1"; } catch { return false; } })();
// What each call of an addition run reads: the whole guide, or its lead's pages and the plan (the reader's choice,
// kept in this browser). A lead that names no page (« [Missing] no page yet: … ») reads the guide either way.
let ADD_CONTEXT = "pages";
try { if (localStorage.getItem("vault-watch-add-context") === "guide") ADD_CONTEXT = "guide"; } catch { /* private window */ }
const NO_PAGE = /^\[[^\]]+\] no page yet:/;

export async function viewCheck(id) {
  stopFollowing();
  await loadSteps();
  const [v, options] = await Promise.all([api(`/api/verifications/${encodeURIComponent(id)}`), api(`/api/verifications/options${stepsQuery()}`)]);
  if (location.hash.slice(1) !== `/check/${id}`) return;  // left the page meanwhile
  const V = T.verif, titles = Object.fromEntries(options.map(o => [o.id, o.title[lang]]));
  const list = (title, items) => items && items.length ? `<details><summary>${title} (${items.length})</summary><ul>${items.map(x => `<li>${x}</li>`).join("")}</ul></details>` : "";
  page.innerHTML = `
    <h1>${V.title} · ${new Date(v.started * 1000).toLocaleString(lang)} ${checkBadge(v)}</h1>
    <p class="subtitle">${V.cost(costTag(v.cost, v.unbilled_usd, false))} · ${V.counts(v.counts)}${v.commit ? ` · main @ <code>${esc(v.commit)}</code>` : ""}</p>
    ${v.error ? `<p class="error-text">${esc(v.error)}</p>` : ""}
    ${v.interrupted ? `<p class="muted">${V.interruptedText(v.missing.map(c => esc(titles[c] || c)).join(", ") || "—")}</p>` : ""}
    ${v.running ? "" : `<p><button class="small-button" id="remove">${V.remove}</button></p>`}
    ${Object.keys(v.runs).length ? `<h2>${V.fixRuns}</h2>${Object.entries(v.runs).map(([t, run]) => `
      <div class="card row${FINISHED.includes(run.status) ? " finished" : ""}"><div class="grow"><b>${esc(t)}</b>
        ${run.pr_url ? `<div class="muted small">${extLink(run.pr_url, run.pr_url)}</div>` : ""}</div>
        ${badge(run.status)}
        ${run.status === "pr-open" ? extLink(run.pr_url, `<button class="primary">${T.merge()}</button>`)
          : `<a href="#/run/${encodeURIComponent(t)}"><button${["review", "publish"].includes(run.status) ? ' class="primary"' : ""}>${
            T.buttons[run.status] || T.details}</button></a>`}</div>`).join("")}` : ""}
    ${v.checks.map(c => {
      const r = v.results[c];
      // A check whose findings are all handled (sent or dismissed) is done, even if it found problems
      const stateBadge = !r && v.running && v.current === c ? `<span class="badge attention">${V.checking}</span>`
        : !r ? `<span class="badge neutral">${v.running ? V.waiting : "—"}</span>`
        : r.summary?.startsWith("could not run") ? `<span class="badge error">${V.failed}</span>`
        : r.findings?.length && !r.open ? `<span class="badge ok">${V.handled}</span>`
        : `<span class="badge ${r.ok ? "ok" : "attention"}">${r.ok ? V.ok : r.open ? V.toHandle(r.open) : V.problems}</span>`;
      // Folded by default once nothing is left to do in it (all handled, or fine); the reader's choice is kept
      const stuck = (r?.findings || []).filter(f => v.unchecked?.[f] && v.handled[f]?.status === "fix");  // sent, not checked
      const finished = r && !r.open && !stuck.length && !r.summary?.startsWith("could not run") && (r.ok || r.findings?.length);
      const isOpen = FOLDS[`${id}/${c}`] ?? !finished;
      return `<details class="card foldable" data-fold="${id}/${c}"${isOpen ? " open" : ""}><summary class="header"><b>${esc(titles[c] || c)}</b>${stateBadge}${r?.open ? ` <button class="small-button" data-tick-card="${c}">${V.tickCard(r.open)}</button>` : ""}</summary>
        ${r ? `<p class="muted small">${esc(r.summary)}</p>
          ${list(V.dead, (r.dead || []).map(d => `${extLink(d.url, esc(d.url))} — ${esc(d.status)} ${esc(d.code ?? "")} (${esc(d.pages.join(", "))})`))}
          ${list(V.blocked, (r.blocked || []).map(d => `${extLink(d.url, esc(d.url))} (${esc(d.pages.join(", "))})`))}
          ${list(V.claims, (r.claims || []).map(x => `${esc(x.recheckBy)} <code>${esc(x.page)}</code> : ${esc(x.claim)}`))}
          ${list(V.pagesDue, (r.pages_due || []).map(esc))}
          ${list(V.linksRead, (r.links || []).map(l => `${extLink(l.url, esc(l.title || l.url))} — ${l.error ? `<span class="attention-text">${esc(l.error)}</span>` : V.linkChars(l.chars, l.cut)}`))}
          ${r.sizes ? sizesBlock(r.sizes) : ""}
          ${r.log ? `<details><summary>${V.log}</summary><pre>${esc(r.log)}</pre></details>` : ""}
          ${(r.findings || []).length ? `${r.fixable ? "" : `<p class="muted small">${V.notFixable}</p>`}${r.mode === "add" ? `<details class="lead-legend"><summary>${V.howToRead}</summary><p>${V.leadsAdd}</p><dl>${
            V.legend.map(([k, t]) => `<dt>${k}</dt><dd>${t}</dd>`).join("")}</dl></details>
            <p class="small lead-tools"><button type="button" class="small-button" data-unfold-card="${c}">${V.unfoldAll}</button>
              <button type="button" class="small-button" data-dig-card="${c}" data-dig="all">🔍 ${V.digTicked}</button>
              <button type="button" class="small-button" data-dig-card="${c}" data-dig="none">${V.digNone}</button></p>` : ""}${stuck.length ? `<div class="unchecked-all" role="status"><span>${V.uncheckedAll(stuck.length)}</span>
            <button type="button" class="primary" data-reopen-card="${c}">${V.resendAll(stuck.length)}</button></div>` : ""}<ul class="leads"${r.mode === "add" ? ` data-card-list="${c}"` : ""}>${r.findings.map((f, i) => lead(f, r.fixable, c, r.mode, i + 1, r.excerpts?.[f], r.details?.[f])).join("")}</ul>` : ""}` : ""}
      </details>`;
    }).join("")}
    <div class="bar check-bar">
      <div class="bar-options" id="bar-options"${BAR_OPEN ? "" : " hidden"}>
        <div class="bar-sect" id="dig-box" hidden><div class="sect">${V.digSect}</div>
          <div class="bar-row"><span class="small">${V.digLabel}</span><span class="seg"><button type="button" data-dig-all="none">${V.digNoneShort}</button><button type="button" data-dig-all="some" disabled></button><button type="button" data-dig-all="all">${V.digAllShort}</button></span>
            <label class="add-context small" id="add-context-box">${V.context}
              <select id="add-context"><option value="pages">${V.contextPages}</option><option value="guide">${V.contextGuide}</option></select>${tip(V.contextTip)}</label></div>
          <div class="dig-cost muted small" id="dig-cost"></div><div class="attention-text small" id="dig-warn" hidden></div></div>
        <div class="bar-sect" id="run-steps-box" hidden><div class="sect">${T.perStep.title}</div><div class="step-cards" id="run-steps"></div></div>
        <div class="narrow-only bar-row end"><button type="button" class="ghost" data-dismiss></button></div>
      </div>
      <div class="bar-line">
        <span class="bar-sum" id="bar-sum"></span>
        <button type="button" class="ghost" id="bar-toggle" aria-expanded="${BAR_OPEN}"></button>
        <button type="button" class="ghost wide-only" id="dismiss" data-dismiss></button>
        <button class="primary" id="fix"></button>
      </div>
    </div>`;
  // A finding is open (checkbox), sent to a fix run (link to the run) or dismissed (can be reopened)
  // Handled findings stay one line; an open one shows the passages it is about
  function lead(f, fixable, card, mode = "fix", n = 0, passages = [], detail = null) {
    const h = v.handled[f], num = `<span class="num">${n}.</span>`;  // per card, stable: handled lines keep theirs
    // A lead handled (sent, dismissed): its title when it has one, its line folded under it
    const shown = detail?.title ? `<b>${esc(detail.title)}</b> <details class="sent"><summary>${V.sentText}</summary><p>${esc(f)}</p></details>` : esc(f);
    if (h?.status === "fix") {
      const run = v.runs[h.thread] || {};
      return `<li class="handled">${num} <span class="badge ok">${V.sent}</span> <a href="#/run/${encodeURIComponent(h.thread)}">${esc(h.thread)}</a>
        ${run.status ? badge(run.status) : ""}${run.pr_url ? ` ${extLink(run.pr_url, "PR")}` : ""} · ${shown}${
        v.unchecked?.[f] ? `<div class="unchecked"><span class="badge attention">${V.unchecked}</span>
          <span class="small">${esc(v.unchecked[f])}</span> <button type="button" class="primary" data-reopen="${esc(f)}">${V.resend}</button></div>` : ""}</li>`;
    }
    if (h?.status === "dismissed") return `<li class="handled">${num} <span class="badge neutral">${V.dismissed}</span> <button class="small-button" data-reopen="${esc(f)}">${V.reopen}</button> ${shown}</li>`;
    if (mode === "add") return addLead(f, fixable, card, n, passages, detail || {});
    const p = leadParts(f), kind = p.kind ? `<span class="badge neutral">${esc(V.kinds[p.kind] || p.kind)}</span> ` : "";
    const pages = p.pages.length ? p.pages.map(x => `<code>${esc(x)}</code>`).join(", ") : p.kind ? `<span class="muted">${V.noPage}</span>` : "";
    // Explained in the language of the interface when the check asked for it: the four parts; the line in English,
    // which is what a run reads, folded below
    const said = detail ? `<dl class="lead-detail">${["says", "guide", "check", "matters"].filter(k => detail[k])
      .map(k => `<dt>${V.detail[k]}</dt><dd>${esc(detail[k])}</dd>`).join("")}</dl>` : "";
    const meta = (detail ? `<details><summary>${V.sentText}</summary>${esc(p.text)}</details>` : "") + (p.read.length ? `<div>${V.readAlso} ${p.read.map(x => `<code>${esc(x)}</code>`).join(", ")}</div>` : "")
      + (p.sources.length ? `<div>${V.sources} ${p.sources.map(u => extLink(u, esc(shortUrl(u)))).join(" · ")}</div>` : "");
    return `<li><label><input type="checkbox" data-lead="${esc(f)}" data-fixable="${fixable}" data-mode="${mode}" data-card="${card}"> ${num} <span class="lead-body">${kind}${pages}${pages ? "<br>" : ""}${said || esc(p.text)}</span></label>${
      meta ? `<div class="lead-meta muted small">${meta}</div>` : ""}${
      mode === "add" ? `<label class="dig muted small"><input type="checkbox" data-deep="${esc(f)}"> ${V.dig}</label>` : ""}${excerpts(passages)}${noteBox(f)}</li>`;
  }
  // « What I already know » on an open lead: kept with the check (POST …/note), sent with the lead to its run
  function noteBox(f) {
    const note = v.notes?.[f] || "";
    return `<div class="lead-note" data-note-box="${esc(f)}">${note
      ? `<div class="note-shown"><b>📝 ${V.noteTitle}</b> <span class="muted small">${V.noteHint}</span><p>${esc(note)}</p>
          <button type="button" class="link" data-note-edit>${V.noteEdit}</button></div>`
      : `<button type="button" class="link" data-note-edit>+ ${V.noteAdd}</button>`}
      <div class="note-edit" hidden><textarea data-note-text maxlength="4000">${esc(note)}</textarea><p class="muted small">${V.noteHelp}</p>
        <button type="button" class="small-button" data-note-save>${V.noteSave}</button> <button type="button" class="small-button" data-note-cancel>${V.noteCancel}</button>
        <span class="small" data-note-said></span></div></div>`;
  }
  function bindNote(box) {
    const f = box.dataset.noteBox, edit = box.querySelector(".note-edit"), area = box.querySelector("[data-note-text]");
    box.querySelector("[data-note-edit]").onclick = () => { edit.hidden = false; box.querySelector("[data-note-edit]").hidden = true; area.focus(); };
    box.querySelector("[data-note-cancel]").onclick = () => { area.value = v.notes?.[f] || ""; edit.hidden = true; box.querySelector("[data-note-edit]").hidden = false; };
    box.querySelector("[data-note-save]").onclick = async e => {
      e.target.disabled = true;
      try {
        v.notes = (await api(`/api/verifications/${encodeURIComponent(id)}/note`, { finding: f, text: area.value })).notes;
        box.outerHTML = noteBox(f);
        const fresh = [...page.querySelectorAll("[data-note-box]")].find(b => b.dataset.noteBox === f);
        bindNote(fresh);
        fresh.insertAdjacentHTML("beforeend", `<span class="small ok-text">${V.noteSaved}</span>`);
        const mark = [...page.querySelectorAll("[data-note-mark]")].find(m => m.dataset.noteMark === f);
        if (mark && !v.notes[f]) mark.remove();
      } catch (err) { box.querySelector("[data-note-said]").textContent = err.message; e.target.disabled = false; }
    };
  }
  // A lead of an addition check: one line (its title, its page, where it comes from) that unfolds into the source
  // and the guide side by side, what to check, what it changes for the reader, « dig deeper », the sources and the
  // pages to read also, and the text the run will read
  function addLead(f, fixable, card, n, passages, d) {
    const p = leadParts(f), key = `${id}/${f}`, open = OPEN_LEADS.has(key);
    const title = d.title || (p.text.split(/(?<=\.)\s/)[0] || p.text).slice(0, 140);
    const short = x => x.split("/").pop().replace(/\.md$/, "");
    const from = p.kind === "From a link" && p.sources[0] ? origin(p.sources[0]) : V.kinds[p.kind] || p.kind;
    const pageLink = x => `<a href="${esc(obsidian(v.vault_name, x))}" title="${esc(V.openObsidian)}">${esc(v.titles?.[x] || short(x))}</a> <code>${esc(x)}</code>`;
    const where = (p.kind === "From a link" && p.sources[0] ? `${V.readIn} ${extLink(p.sources[0], esc(shortUrl(p.sources[0])))} ↗ → ` : `<span class="badge neutral">${esc(V.kinds[p.kind] || p.kind)}</span> `)
      + (p.pages.length ? `${V.writeIn} ${p.pages.map(pageLink).join(", ")}` : `<span class="muted">${V.noPage}</span>`);
    const said = x => linked(x || "", p.sources);
    const guideBox = passages?.length ? passages.map(e => e.match === "missing"
      ? `<p class="muted small"><code>${esc(e.page)}</code> · ${T.excerptMissing}</p>`
      : `<div class="excerpt-head muted small">${V.line(e.line)}${e.match === "approx" ? ` · ${T.excerptApprox}` : ""} · <a href="${esc(obsidian(v.vault_name, e.page, e.heading))}">${V.openObsidian} ↗</a></div>
        <div class="lines" lang="${e.page.startsWith("en/") ? "en" : "fr"}">${e.lines.map(l => `<div${l.hit ? ' class="target"' : ""}><span class="n">${l.n}</span><span>${
          l.parts ? `${esc(l.parts[0])}<mark>${esc(l.parts[1])}</mark>${esc(l.parts[2])}` : esc(l.text)}</span></div>`).join("")}</div>`).join("") : "";
    const extra = (() => {  // what digging adds to the cost of the run, when it is billed
      const o = options.find(x => x.id === card) || {}, narrow = ADD_CONTEXT === "pages" && o.run_usd_deep_pages;
      const more = narrow ? o.run_usd_deep_pages - o.run_usd_each_pages : (o.run_usd_deep || 0) - (o.run_usd_each || 0);
      return billedStep("add") && more > 0 ? ` <small>· + ≈ ${dollars(more)}</small>` : "";
    })();
    return `<li class="lead-item">
      <div class="lead-row" data-unfold="${esc(key)}"><input type="checkbox" data-lead="${esc(f)}" data-fixable="${fixable}" data-mode="add" data-card="${card}" aria-label="${esc(title)}">
        <span class="num">${n}.</span><span class="lead-title"><b>${esc(title)}</b>${p.pages[0] ? ` <span class="muted small">· ${esc(short(p.pages[0]))}</span>` : ""}${
          v.notes?.[f] ? ` <span class="note-mark" data-note-mark="${esc(f)}">📝 ${V.noteMark}</span>` : ""}</span>
        <span class="tag">${esc(from)}</span><label class="dig-mini" title="${esc(V.digWhat)}"><input type="checkbox" data-deep="${esc(f)}"> 🔍 ${V.digShort}</label><button type="button" class="unfold" aria-expanded="${open}" aria-label="${esc(V.unfold)}">${open ? "▾" : "▸"}</button></div>
      <div class="lead-open"${open ? "" : " hidden"}>
        <div class="where muted small">${where}</div>
        <div class="lead-cols"><div class="box"><h4>${V.detail.says}</h4>${d.says ? said(d.says) : esc(p.text)}</div>
          <div class="box"><h4>${V.detail.guide}</h4>${d.guide ? `<p>${said(d.guide)}</p>` : ""}${guideBox || (d.guide ? "" : `<p class="muted small">${V.nothingQuoted}</p>`)}</div></div>
        ${d.check || d.matters ? `<dl class="pair">${d.check ? `<dt>${V.detail.check}</dt><dd>${said(d.check)}</dd>` : ""}${d.matters ? `<dt>${V.detail.matters}</dt><dd>${said(d.matters)}</dd>` : ""}</dl>` : ""}
        <div class="lead-actions"><label class="digbtn"><input type="checkbox" data-deep="${esc(f)}"> 🔍 ${V.digButton}${extra}</label><span class="muted small">${V.digWhat}</span></div>
        ${noteBox(f)}
        <div class="lead-lists">
          ${p.sources.length ? `<div><h5>${V.sourcesTitle(p.sources.length)}</h5><ul>${p.sources.map((u, i) => `<li>${extLink(u, esc(shortUrl(u)))} ↗${i === 0 && p.kind === "From a link" ? ` <span class="muted">${V.theLink}</span>` : ""}</li>`).join("")}</ul></div>` : ""}
          ${p.read.length ? `<div><h5>${V.readTitle(p.read.length)}</h5><ul>${p.read.map(x => `<li>${pageLink(x)}</li>`).join("")}</ul></div>` : ""}
        </div>
        ${d.says ? `<details class="sent"><summary>${V.sentText}</summary><p>${esc(p.text)}</p></details>` : ""}
      </div></li>`;
  }
  const boxes = [...page.querySelectorAll("[data-lead]")];
  const ticked = () => boxes.filter(c => c.checked);
  page.querySelectorAll("[data-note-box]").forEach(bindNote);
  // A lead unfolds by its line (not by its box, its links or its buttons); « unfold all » per card
  page.querySelectorAll("[data-unfold]").forEach(row => row.onclick = e => {
    if (e.target.closest("input, a, label") ) return;
    const body = row.nextElementSibling, open = body.hidden;
    body.hidden = !open;
    row.querySelector(".unfold").textContent = open ? "▾" : "▸";
    row.querySelector(".unfold").setAttribute("aria-expanded", open);
    if (open) OPEN_LEADS.add(row.dataset.unfold); else OPEN_LEADS.delete(row.dataset.unfold);
  });
  page.querySelectorAll("[data-unfold-card]").forEach(b => b.onclick = () => {
    const rows = [...page.querySelectorAll(`[data-card-list="${b.dataset.unfoldCard}"] [data-unfold]`)];
    const open = rows.some(r => r.nextElementSibling.hidden);
    rows.forEach(r => { if (r.nextElementSibling.hidden === open) r.click(); });
    b.textContent = open ? V.foldAll : V.unfoldAll;
  });
  $("#add-context").value = ADD_CONTEXT;
  $("#add-context").onchange = e => {
    ADD_CONTEXT = e.target.value;
    try { localStorage.setItem("vault-watch-add-context", ADD_CONTEXT); } catch { /* private window: per page only */ }
    count();
  };
  const count = () => {
    const ok = ticked().filter(c => c.dataset.fixable === "true"), n = ok.length, e = ticked().length;
    const by = {};
    ok.forEach(c => { by[c.dataset.mode] = (by[c.dataset.mode] || 0) + 1; });
    // A compaction run, an addition run: what it costs whatever its leads, plus a share per lead, priced with the
    // models of the Settings (the check that gives the leads carries the estimate of the run they go to)
    // A lead dug deeper has a call of its own instead of a share of one
    const dug = ok.filter(c => c.dataset.mode === "add" && deep().has(c.dataset.lead)).length;
    const runOf = (check, leads, deeper = 0) => {
      const o = options.find(o => o.id === check) || {};
      return o.run_usd ? `≈ ${dollars(o.run_usd + (o.run_usd_each || 0) * (leads - deeper) + (o.run_usd_deep || 0) * deeper)}` : "";
    };
    // An addition run whose calls read their lead's pages and the plan: priced so, except the leads that name no
    // page, which read the whole guide (the first of them writes it to the cache: the difference of the two bases)
    const adds = ok.filter(c => c.dataset.mode === "add").map(c => c.dataset.lead);
    const addCost = () => {
      const o = options.find(o => o.id === "news") || {};
      if (ADD_CONTEXT !== "pages" || !o.run_usd_pages) return runOf("news", adds.length, dug);
      const each = f => NO_PAGE.test(f) ? (deep().has(f) ? o.run_usd_deep : o.run_usd_each) : (deep().has(f) ? o.run_usd_deep_pages : o.run_usd_each_pages);
      return `≈ ${dollars(o.run_usd_pages + (adds.some(f => NO_PAGE.test(f)) ? o.run_usd - o.run_usd_pages : 0) + adds.reduce((s, f) => s + (each(f) || 0), 0))}`;
    };
    $("#fix").innerHTML = V.createFix(by, (usd, mode) => costHtml(MODE_STEP[mode] || "fix", usd),
      { compact: runOf("compaction", by.compact || 0), add: addCost(), dug, short: true });
    // The leads of an addition run: how many are dug deeper, and what the run costs, part by part
    $("#dig-box").hidden = !adds.length;
    if (adds.length) {
      const o = options.find(o => o.id === "news") || {}, narrow = ADD_CONTEXT === "pages" && o.run_usd_pages;
      const base = narrow ? o.run_usd_pages + (adds.some(f => NO_PAGE.test(f)) ? o.run_usd - o.run_usd_pages : 0) : o.run_usd;
      const each = narrow ? o.run_usd_each_pages : o.run_usd_each, deeper = narrow ? o.run_usd_deep_pages : o.run_usd_deep;
      const seg = $("#dig-box").querySelectorAll("[data-dig-all]");
      seg[0].classList.toggle("on", dug === 0); seg[2].classList.toggle("on", dug === adds.length);
      seg[1].classList.toggle("on", dug > 0 && dug < adds.length); seg[1].textContent = V.digSome(dug, adds.length);
      $("#dig-cost").textContent = billedStep("add") && o.run_usd
        ? V.digCost(adds.length, adds.length - dug, dollars(each || 0), dug, dollars(deeper || 0), dollars(base || 0), addCost())
        : V.digFree(adds.length - dug, dug, costOf("add", ""));
      $("#dig-warn").hidden = !(dug === adds.length && adds.length > 1);
      $("#dig-warn").textContent = V.digWarn(adds.length);
    }
    // The steps of the run(s) these leads go to: what runs each, changeable for this time
    const kinds = Object.keys(by);
    const wanted = [...kinds.map(k => MODE_STEP[k]), ...(kinds.some(k => k !== "translation") ? ["crosscheck"] : []), ...(kinds.length ? ["mirror"] : [])];
    $("#run-steps-box").hidden = !wanted.length;
    $("#run-steps").innerHTML = (STEPS.forced ? `<p class="muted small">${T.perStep.forced(STEPS.forced)}</p>` : "")
      + wanted.map((s, i) => stepCard(s, i + 1, T.perStep.names[s], V.stepWhat[s] || "")).join("");
    bindSteps($("#run-steps"), count);
    $("#fix").disabled = n === 0 || v.running;
    page.querySelectorAll("[data-dismiss]").forEach(b => { b.textContent = V.dismiss(e); b.disabled = e === 0 || v.running; });
    // The line of the bar: what is ticked and what it costs; the full label of the button on a wide screen
    const price = kinds.length === 1 ? (kinds[0] === "add" ? costHtml("add", addCost()) : "") : "";
    $("#bar-sum").innerHTML = n ? `<span class="wide-only">${V.barSum(n, dug, price)}</span><span class="narrow-only">${V.barSumShort(n, price)}</span>` : "";
    $("#fix").innerHTML = n ? `<span class="wide-only">${$("#fix").innerHTML}</span><span class="narrow-only">${V.createShort}</span>` : $("#fix").innerHTML;
    $("#bar-toggle").innerHTML = `<span class="wide-only">${V.barOptions} ${BAR_OPEN ? "▾" : "▴"}</span><span class="narrow-only">${BAR_OPEN ? "✕" : "⋯"}</span>`;
    $("#bar-toggle").hidden = !wanted.length;
  };
  // The boxes follow LeadRules (rules.js): read them, apply a rule, set them again (the box of a lead's line and the
  // button of its card are one choice), then count
  const digs = [...page.querySelectorAll("[data-deep]")];
  const deep = () => new Set(digs.filter(d => d.checked).map(d => d.dataset.deep));
  const state = () => ({ ticked: new Set(ticked().map(c => c.dataset.lead)), dug: deep() });
  const apply = s => {
    boxes.forEach(c => { c.checked = s.ticked.has(c.dataset.lead); });
    digs.forEach(d => { d.checked = s.dug.has(d.dataset.deep); });
    count();
  };
  const leadsOf = card => boxes.filter(c => !card || c.dataset.card === card).map(c => c.dataset.lead);
  boxes.forEach(c => c.onchange = () => apply(LeadRules.tick(state(), c.dataset.lead, c.checked)));
  digs.forEach(d => d.onchange = () => apply(LeadRules.dig(state(), d.dataset.deep, d.checked)));
  // Dig deeper into every lead ticked, or into none: in one card, or in the whole run (the bar)
  page.querySelectorAll("[data-dig-card]").forEach(b => b.onclick = () => apply(LeadRules.digTicked(state(), leadsOf(b.dataset.digCard), b.dataset.dig === "all")));
  page.querySelectorAll("[data-dig-all]").forEach(b => b.onclick = () => apply(LeadRules.digTicked(state(), leadsOf(null), b.dataset.digAll === "all")));
  // Tick or untick every open finding of one card (all ticked: untick)
  page.querySelectorAll("[data-fold]").forEach(d => d.ontoggle = () => { FOLDS[d.dataset.fold] = d.open; });
  page.querySelectorAll("[data-tick-card]").forEach(b => b.onclick = e => {
    e.preventDefault();  // in the card's summary: tick, do not fold
    const card = boxes.filter(c => c.dataset.card === b.dataset.tickCard), all = card.every(c => c.checked);
    apply(LeadRules.tickAll(state(), card.map(c => c.dataset.lead), !all));
  });
  // The page leaves room under its last line for the bar, as tall as it is now (its options open or folded)
  keepRoomForBar();
  // The options of the bar, opened or folded: the reader's choice, kept in the browser
  $("#bar-toggle").onclick = () => {
    BAR_OPEN = !BAR_OPEN;
    $("#bar-options").hidden = !BAR_OPEN;
    $("#bar-toggle").setAttribute("aria-expanded", BAR_OPEN);
    try { localStorage.setItem("vault-watch-bar-open", BAR_OPEN ? "1" : "0"); } catch { /* private window: per page only */ }
    count();
  };
  count();
  const leads = (findings, status) => api(`/api/verifications/${encodeURIComponent(id)}/leads`, { findings, status }).then(() => viewCheck(id));
  if ($("#remove")) $("#remove").onclick = () => confirm(V.confirmRemove)
    && api(`/api/verifications/${encodeURIComponent(id)}/delete`, {}).then(() => { location.hash = "/check"; });
  page.querySelectorAll("[data-reopen]").forEach(b => b.onclick = () => leads([b.dataset.reopen], "open"));
  page.querySelectorAll("[data-reopen-card]").forEach(b => b.onclick = () => leads(
    (v.results[b.dataset.reopenCard].findings || []).filter(f => v.unchecked?.[f] && v.handled[f]?.status === "fix"), "open"));
  if (!boxes.length) page.querySelector(".bar").remove();
  else {
    page.querySelectorAll("[data-dismiss]").forEach(b => b.onclick = () => leads(ticked().map(c => c.dataset.lead), "dismissed"));
    $("#fix").onclick = async () => {
      const busy = (await api("/api/runs").catch(() => [])).filter(r => r.status === "running").map(r => r.thread);
      if (busy.length && !confirm(V.confirmParallel(busy.join(", ")))) return;
      $("#fix").disabled = true;
      // One run per mode: content fixes, translation fixes, trims and additions do not take the same path
      const threads = [];
      for (const mode of ["fix", "translation", "compact", "add"]) {
        const text = ticked().filter(c => c.dataset.fixable === "true" && c.dataset.mode === mode).map(c => c.dataset.lead).join("\n");
        const dig = mode === "add" ? { deep: text.split("\n").filter(f => deep().has(f)), context: ADD_CONTEXT } : {};
        const steps = ownFor([MODE_STEP[mode], "crosscheck", "mirror"]);
        if (text) threads.push((await api("/api/fix", { text, verification: id, mode, steps, ...dig })).thread);
      }
      location.hash = `/run/${encodeURIComponent(threads[0])}`;
    };
  }
  if (v.running) followLater(() => viewCheck(id).catch(() => {}), 3000);
}

// The size check: what the guide gained, its heaviest pages (those over their budget first), the weight per chapter
function sizesBlock(s) {
  const V = T.verif;
  // The size now, then what the page gained since the earlier commit (bytes and share of what it weighed)
  const share = p => p.before ? `, ${p.bytes >= p.before ? "+" : "−"}${Math.round(Math.abs(p.bytes - p.before) * 100 / p.before)} %` : "";
  const grew = p => !("before" in p) ? "" : p.before == null ? ` · ${V.newPage}` : p.bytes !== p.before ? ` · ${signedKb(p.bytes - p.before)}${share(p)}` : "";
  const row = p => `<li><code>${esc(p.page)}</code> — <b>${kb(p.bytes)}</b>${p.budget ? ` / ${kb(p.budget * 1024)}` : ""}${grew(p)}${p.readonly ? ` · ${V.readonly}` : ""}${
    p.over ? ` <span class="badge attention">${V.over}</span>` : ""}${p.grew ? ` <span class="badge attention">${V.grew}</span>` : ""}
    <div class="muted small">${[...p.sections.map(x => `${esc(x.title)} ${kb(x.bytes)}`),
      ...(p.footnotes.count ? [V.notes(p.footnotes.count, kb(p.footnotes.bytes))] : [])].join(" · ")}</div></li>`;
  return `${s.growth ? `<p class="small">${V.growth(s.growth)}</p>` : ""}
    <details${s.over || s.grew ? " open" : ""}><summary>${s.over || s.grew ? V.flaggedFirst : V.heaviest} (${s.heaviest.length})</summary><ul>${s.heaviest.map(row).join("")}</ul></details>
    <details><summary>${V.perChapter} (${s.chapters.length})</summary><ul>${s.chapters.map(c =>
      `<li><code>${esc(c.chapter)}</code> — ${kb(c.bytes)}, ${c.pages} ${V.pagesWord}</li>`).join("")}</ul></details>`;
}

const FOLDS = {};  // check cards folded or opened by the reader, by verification/check, kept across refreshes
