// @ts-check
/* vault-watch: the menu « Watch »: « To handle » (what waits for the editor, wherever it comes from), the automatic
   watch, every run; the cards of a watch and of a run, and the guide's folder against the forge (« Update my folder »). */

import { $, esc, extLink, followLater, page } from "./util.js";
import { api, info } from "./api.js";
import { lang, T } from "./texts.js";
import { cost, costTag, loadSteps, stepsQuery } from "./steps.js";
import { checkCardMaker } from "./checks.js";

// --- The menu « Watch »: to handle, the automatic watch, every run ------------------------------------
const CLASSES = {
  running: "attention", review: "attention", retouch: "attention", proofread: "attention", translation: "attention", publish: "attention", "pr-open": "attention",
  published: "ok", merged: "ok", stopped: "error",
};
// Nothing left to do: the card is dimmed
export const FINISHED = ["closed", "merged", "pr-closed", "nothing-applied", "not-published"];
export const badge = st => `<span class="badge ${CLASSES[st] || "neutral"}">${T.statuses[st] || st}</span>`;

// A run that waits for something: done by the agent (running), or by the editor (the others)
export const WAITING = ["running", "review", "retouch", "proofread", "translation", "publish", "stopped", "pr-open"];
export const crumb = () => `<div class="crumb">${T.nav.menu}</div>`;
// What the button of a run says and where it leads: its page, or the pull request to merge
const runButton = (thread, r) => r.status === "pr-open" && r.pr_url ? extLink(r.pr_url, `<button class="primary">${T.merge()}</button>`)
  : `<a href="#/run/${encodeURIComponent(thread)}"><button${["review", "retouch", "proofread", "translation", "publish", "stopped"].includes(r.status) ? ' class="primary"' : ""}>${
      T.buttons[r.status] || T.details}</button></a>`;

// A watch (an issue of the forge, or a file of collected items) and the run that handles it
function watchCard(v) {
  const r = v.run;
  const action = r.status === "closed" || v.error ? ""
    : r.status === "new" ? `<button class="primary" data-analyse="${esc(v.id)}" data-kind="${v.kind}">${T.analyse(cost("≈ 4 $"))}</button>`
    : runButton(r.thread, r);
  return `<div class="card row watch-card${FINISHED.includes(r.status) ? " finished" : ""}">
    <div class="grow">
      ${v.kind === "issue" ? `<b>#${v.number}</b> ` : ""}${esc(v.title)} ${v.urgent ? `<span class="badge ${FINISHED.includes(r.status) ? "neutral" : "error"}">urgent</span>` : ""}
      ${v.error ? `<div class="error-text small">${esc(v.error)}</div>` : ""}
      <div class="muted small">${esc(v.date)} · ${v.kind === "issue" ? T.issue(v.state === "open") : T.watchFile(v.items)}${
        !["new", "closed"].includes(r.status) ? ` · ${T.count(r.corrections, r.applied)} · ${costTag(r.cost, r.unbilled_usd, false)}` : ""}${
        r.pr_url ? ` · ${extLink(r.pr_url, "pull request")}` : ""}</div>
    </div>
    ${badge(r.status)} ${action}
  </div>`;
}
// A run that is not a watch's: from a check, « Report or suggest », « Languages »
const runCard = r => `<div class="card row${FINISHED.includes(r.status) ? " finished" : ""}"><div class="grow"><b>${esc(r.thread)}</b>
    <div class="muted small">${esc(r.source)} · ${r.corrections} correction(s) · ${costTag(r.cost, r.unbilled_usd, false)}${
      r.pr_url ? ` · ${extLink(r.pr_url, "pull request")}` : ""}</div></div>
    ${badge(r.status)} ${WAITING.includes(r.status) ? runButton(r.thread, r) : `<a href="#/run/${encodeURIComponent(r.thread)}"><button>${T.details}</button></a>`}</div>`;
// « Analyse »: the run of a watch starts, and its page opens
function bindAnalyse(root) {
  root.querySelectorAll("[data-analyse]").forEach(b => b.onclick = async () => {
    b.disabled = true;
    const { thread } = await api("/api/analyses", b.dataset.kind === "issue" ? { issue: Number(b.dataset.analyse) } : { watch: b.dataset.analyse });
    location.hash = `/run/${encodeURIComponent(thread)}`;
  });
}

let HOME = null;  // the last answer shown on the page of the watches: drawn at once on the way back, then refreshed
let RUNS_SHOWN = 20;  // the list shows the newest; « older ones » asks for more
export async function viewWatches() {
  const load = () => api("/api/watches");
  if (HOME) {
    drawWatches(HOME);
    const shown = JSON.stringify(HOME), at = location.hash;
    load().then(fresh => {  // still on this page, and something moved: drawn again
      HOME = fresh;
      if (location.hash === at && JSON.stringify(fresh) !== shown) drawWatches(fresh);
    }).catch(() => {});
    return;
  }
  HOME = await load();
  drawWatches(HOME);
}

function drawWatches(watches) {
  page.innerHTML = `
    ${crumb()}<h1>${T.watches}</h1>
    <p class="subtitle">${info?.watch_source === "feeds" ? T.collectIntro : T.watchesIntro()}</p>
    ${info?.watch_source === "feeds" ? `<p><button id="collect">${T.collectNow}</button></p>` : ""}
    ${watches.map(watchCard).join("") || `<p class="muted">${T.noWatch}</p>`}`;
  const collect = $("#collect");
  if (collect) collect.onclick = async () => {
    collect.disabled = true;
    collect.textContent = T.collecting;
    try { await api("/api/collect", {}); HOME = null; await viewWatches(); }
    catch (e) { collect.disabled = false; collect.textContent = T.collectNow; collect.insertAdjacentHTML("afterend", ` <span class="error-text">${esc(e.message)}</span>`); }
  };
  bindAnalyse(page);
}

// Every run, newest first: the watches' (their issue said in a line) and the others
export async function viewRuns() {
  const [watches, others] = await Promise.all([api("/api/watches"), api(`/api/runs?limit=${RUNS_SHOWN + 1}`)]);
  if (location.hash.slice(1) !== "/runs") return;  // left the page meanwhile
  const ofWatch = watches.filter(v => !["new", "closed"].includes(v.run.status)).map(v => ({ date: v.date, html: watchCard(v) }));
  const rest = others.slice(0, RUNS_SHOWN).map(r => ({ date: r.as_of || "", html: runCard(r) }));
  const all = [...ofWatch, ...rest].sort((a, b) => b.date.localeCompare(a.date));
  page.innerHTML = `${crumb()}<h1>${T.nav.runs}</h1><p class="subtitle">${T.runsIntro}</p>
    ${all.map(x => x.html).join("") || `<p class="muted">${T.noWatch}</p>`}
    ${others.length > RUNS_SHOWN ? `<p><button type="button" id="older">${T.menu.older}</button></p>` : ""}`;
  if ($("#older")) $("#older").onclick = () => { RUNS_SHOWN += 40; viewRuns(); };
}

// The guide's folder against the forge (« Update my folder », GET /api/folder, POST /api/folder/update): how far
// behind it is, where it is, then what the update did. `only`: the page of a run merged, which says this PR alone.
export function folderBox(f, done = null, only = 0) {
  const F = T.folder, box = (kind, title, body, action = "") => `<div class="card row folder-box ${kind}"><div class="grow"><b>${title}</b>${body}</div>${action}</div>`;
  const meta = t => `<div class="muted small">${t}</div>`;
  if (done && done.ok) return box("done", F.doneTitle, meta(F.done(esc(done.from), esc(done.to), done.files)
    + (done.kept.length ? F.kept(done.kept.length) : "") + (done.branch && done.branch !== f.base ? F.doneOther(esc(done.branch), esc(f.base)) : "")),
    `<span class="badge ok">${F.upToDate}</span>`);
  if (done) return box("stop", F.stopTitle, meta(done.files?.length ? F.stopFiles(done.files.map(x => `<code>${esc(x)}</code>`).join(", ")) : F.stopWhy(esc(done.why))),
    `<button type="button" data-folder-update>${F.retry}</button>`);
  if (f.lent_to) return only ? "" : box("", F.lentTitle(esc(f.lent_to)), meta(F.lent), `<a href="#/run/${encodeURIComponent(f.lent_to)}">${F.toRetouch}</a>`);
  if (!f.behind.length) return "";
  const button = `<button type="button" class="primary" data-folder-update>${f.branch && f.branch !== f.base ? F.updateBase(esc(f.base)) : F.update}</button>`;
  if (only) return box("", F.notYetTitle, meta(F.notYet), button);
  const prs = f.behind.every(b => b.pr), link = b => b.pr && info?.repo_url ? extLink(`${info.repo_url}/pull/${b.pr}`, `#${b.pr} ${esc(b.title)}`) : `${b.pr ? `#${b.pr} ` : ""}${esc(b.title)}`;
  const when = f.updated ? new Date(f.updated).toLocaleString(lang, { dateStyle: "short", timeStyle: "short" }) : F.unknown;
  return box("", F.behind(f.behind.length, prs),
    meta(`${f.behind.slice(0, 3).map(link).join(" · ")}${f.behind.length > 3 ? ` · ${F.more(f.behind.length - 3)}` : ""}. ${F.notSeen}`)
    + meta(F.where(esc(f.path), f.branch ? esc(f.branch) : F.detached, f.changes.length ? F.changes(f.changes.length) : F.clean, when))
    + (f.branch && f.branch !== f.base ? meta(F.otherBranch(esc(f.branch), esc(f.base))) : "")
    + (f.offline ? meta(F.offline()) : ""), button);
}
export function bindFolder(root, f, only = 0) {
  const b = root?.querySelector("[data-folder-update]");
  if (!b) return;
  b.onclick = async () => {
    b.disabled = true;
    const done = await api("/api/folder/update", {}).catch(e => ({ ok: false, why: e.message, files: [] }));
    root.innerHTML = folderBox(f, done, only);
    bindFolder(root, f, only);
    refreshTodo();
  };
}

// « To handle »: what waits for the editor, wherever it comes from. First a run in pause (or running), then a watch
// to start, then the checks whose leads are to sort; a count of what waits for the editor is shown on the menu.
let TODO_COUNT = null;
export function showTodoCount() {
  const n = TODO_COUNT || 0;
  [$("#todo-count"), ...document.querySelectorAll("[data-todo-count]")].forEach(c => { c.hidden = !n; c.textContent = n; });
  $("#watch-menu > summary").title = n ? T.todo.waiting(n) : "";
}
const todoOf = (watches, others, verifs, folder) => {
  const runs = [...watches.filter(v => WAITING.includes(v.run.status)).map(v => ({ watch: v, status: v.run.status })),
    ...others.filter(r => WAITING.includes(r.status)).map(r => ({ run: r, status: r.status }))];
  const starts = watches.filter(v => v.run.status === "new" && !v.error && v.state !== "closed");
  const leads = verifs.filter(p => ["to-handle", "running"].includes(p.status));
  // What waits for the editor: a run not running, a watch to start, a check with leads to sort
  const count = runs.filter(r => r.status !== "running").length + starts.length + leads.filter(p => p.status === "to-handle").length
    + (folder?.behind?.length && !folder.lent_to ? 1 : 0);
  return { runs, starts, leads, count };
};
export async function refreshTodo() {
  try {
    const [watches, others, verifs, folder] = await Promise.all([api("/api/watches"), api("/api/runs?limit=40"),
      api("/api/verifications?limit=40"), api("/api/folder").catch(() => null)]);
    TODO_COUNT = todoOf(watches, others, verifs, folder).count;
    showTodoCount();
  } catch { /* the count stays as it was */ }
}
export async function viewTodo() {
  await loadSteps();
  const [watches, others, verifs, options, folder, gap] = await Promise.all([api("/api/watches"), api("/api/runs?limit=40"),
    api("/api/verifications?limit=40"), api(`/api/verifications/options${stepsQuery()}`), api("/api/folder").catch(() => null),
    api("/api/last-gap-search").catch(() => null)]);
  // The search for what the guide lacks (E4): once a quarter; said when it is due
  const gapDays = gap?.started ? Math.floor((Date.now() / 1000 - gap.started) / 86400) : null;
  const gapDue = gap && (gapDays == null || gapDays > 90);
  if (!["", "/"].includes(location.hash.slice(1))) return;  // left the page meanwhile
  const D = T.todo, { runs, starts, leads, count } = todoOf(watches, others, verifs, folder), checkCard = checkCardMaker(options);
  TODO_COUNT = count;
  showTodoCount();
  // The runs that wait for the editor first, the running ones after
  runs.sort((a, b) => Number(a.status === "running") - Number(b.status === "running"));
  const open = leads.reduce((s, p) => s + p.counts.open, 0);
  page.innerHTML = `
    ${crumb()}<h1>${T.nav.todo}</h1>
    <p class="subtitle">${D.intro}</p>
    <div id="folder-box">${folder ? folderBox(folder) : ""}</div>
    ${!runs.length && !starts.length && !leads.length && !folder?.behind?.length ? `<p class="banner">${D.nothing}</p>` : ""}
    <h2>${D.runs} <span class="muted small">· ${runs.length}</span></h2>
    ${runs.map(r => r.watch ? watchCard(r.watch) : runCard(r.run)).join("") || `<p class="empty-note">${D.runsNone}</p>`}
    ${starts.length ? `<h2>${D.watches} <span class="muted small">· ${starts.length}</span></h2>${starts.map(watchCard).join("")}` : ""}
    ${leads.length ? `<h2>${D.leads} <span class="muted small">· ${D.leadsCount(leads.length, open)}</span></h2>${leads.map(checkCard).join("")}` : ""}
    <h2>${D.launch}</h2>
    ${gapDue ? `<p class="banner">${D.gapDue(gapDays, gap.started ? new Date(gap.started * 1000).toLocaleDateString(lang) : "")}
      <a href="#/check?new=news"><button type="button">${D.gapButton}</button></a></p>` : ""}
    <div class="launch-row">
      <div class="card"><b>${T.nav.check}</b><p class="muted small">${D.checkWhat}</p><a href="#/check?new"><button>${D.checkButton}</button></a></div>
      <div class="card"><b>${T.nav.report}</b><p class="muted small">${D.reportWhat}</p><a href="#/report"><button>${D.reportButton}</button></a></div>
    </div>`;
  bindAnalyse(page);
  bindFolder($("#folder-box"), folder);
  // Something still running here: the page is drawn again a little later, while it stays open
  if (runs.some(r => r.status === "running") || leads.some(p => p.status === "running"))
    followLater(() => { if (["", "#/"].includes(location.hash)) viewTodo().catch(() => {}); }, 5000);
}
