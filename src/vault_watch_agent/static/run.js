// @ts-check
/* vault-watch: one run: its screen chosen by its state (a pause: review.js, retouch.js, proofread.js,
   translation.js, publish.js), its steps while it runs (server-sent events), its end. */

import { $, esc, extLink, page } from "./util.js";
import { api } from "./api.js";
import { T } from "./texts.js";
import { en } from "./explain.js";
import { costTag } from "./steps.js";
import { route } from "./router.js";
import { badge, bindFolder, folderBox } from "./watches.js";
import { viewReview } from "./review.js";
import { viewRetouch } from "./retouch.js";
import { viewProofread } from "./proofread.js";
import { viewTranslation } from "./translation.js";
import { viewPublish } from "./publish.js";

// --- One run ---------------------------------------------------------------------------------------
let source = null;  // EventSource of the run being followed
// Another screen: the run is no longer followed
export function closeSource() { if (source) { source.close(); source = null; } }

// Its line of usage, its price at the end said like a check's: on a subscription, what it is worth, struck through
const usageHtml = r => {
  const line = T.usageLine(r.usage), at = line.lastIndexOf(" ≈ ");
  return !(r.unbilled_usd > 0) || at < 0 ? esc(line) : `${esc(line.slice(0, at))} ${costTag(r.cost, r.unbilled_usd, false)}`;
};
export async function viewRun(thread) {
  const r = await api(`/api/runs/${encodeURIComponent(thread)}`);
  const name = r.mode === "mirror" ? T.pairs.runTitle : r.source || thread;
  const title = `<h1>${r.mode !== "mirror" && r.source ? en(name) : esc(name)} ${badge(r.status)}</h1>
    <p class="subtitle">${r.as_of && !r.mode ? `${T.watchUpTo(r.as_of)} · ` : ""}${usageHtml(r)}</p>`;
  if (r.status === "running") return viewRunning(r, title);
  if (r.status === "review") return viewReview(r, title);
  if (r.status === "publish") return viewPublish(r, title);
  if (r.status === "retouch") return viewRetouch(r, title);
  if (r.status === "translation") return viewTranslation(r, title);
  if (r.status === "proofread") return viewProofread(r, title);
  viewEnd(r, title);
}

function viewRunning(r, title) {
  const doneSteps = new Set(r.job.events.map(e => e.node));
  const first = r.job.action === "fix" ? "propose" : { run: "collect", review: "apply", retouch: "retouch", mirror: "mirror", translation: "translation", publish: "publish", recheck: "audits", retranslate: "mirror", proofread: "proofread", "proofread-review": "mirror", resume: null }[r.job.action];
  const steps = r.steps.slice(first ? r.steps.indexOf(first) : 0);
  const cost = r.job.events.reduce((m, e) => e.cost ?? m, 0);
  let unbilled = r.job.events.reduce((m, e) => e.unbilled ?? m, 0);
  page.innerHTML = `${title}
    <div class="card">
      <ol class="steps" id="steps">${steps.map(s => `<li data-step="${s}">${T.steps[s]}</li>`).join("")}</ol>
      <p class="muted small" id="progress"></p>
    </div>
    <p class="muted small">${T.canClose}</p>`;
  const update = (cost) => {
    let current = true;
    page.querySelectorAll("#steps li").forEach(li => {
      const done = doneSteps.has(li.dataset.step);
      li.classList.toggle("done", done);
      li.classList.toggle("current", !done && current && (current = false, true));
    });
    const min = Math.round((Date.now() / 1000 - r.job.started) / 60);
    $("#progress").innerHTML = T.progress(min, costTag(cost, unbilled, false));
  };
  update(cost);
  source = new EventSource(`/api/runs/${encodeURIComponent(r.thread)}/events`);
  source.onmessage = ev => { const e = JSON.parse(ev.data); doneSteps.add(e.node); unbilled = e.unbilled ?? unbilled; update(e.cost ?? cost); };
  source.addEventListener("end", () => { source.close(); source = null; route(); });
}

function viewEnd(r, title) {
  const pr = r.pr_url ? extLink(r.pr_url, "pull request") : "";
  const text = (T.end[r.status] || (() => ""))(pr, esc(r.branch));
  page.innerHTML = `${title}
    <div class="card"><p>${text}</p>
      ${r.error ? `<p class="error-text">${esc(r.error)}</p>` : ""}
      ${r.status === "stopped" ? `<button class="primary" id="resume">${T.resume}</button>` : ""}</div>
    ${r.applied.length ? `<p>${T.applied}${T.colon}${r.applied.join(", ")}</p>` : ""}
    ${r.report_path ? `<p class="small"><a href="/api/runs/${encodeURIComponent(r.thread)}/report" target="_blank">${T.report}</a></p>` : ""}
    <div id="folder-box"></div>`;
  const number = Number((r.pr_url || "").match(/\/pull\/(\d+)/)?.[1] || 0);
  if (r.status === "merged" && number) api("/api/folder").then(f => {
    const box = $("#folder-box");
    if (!box || !f.behind.some(b => b.pr === number)) return;
    box.innerHTML = folderBox(f, null, number);
    bindFolder(box, f, number);
  }).catch(() => {});
  const b = $("#resume");
  if (b) b.onclick = async () => { b.disabled = true; await api(`/api/runs/${encodeURIComponent(r.thread)}/resume`, {}); route(); };
}
