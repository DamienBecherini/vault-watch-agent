// @ts-check
/* vault-watch: « Check the guide »: the checks to start with their estimates, the checks with leads to sort, the
   history; and the card of a check on the lists. */

import { $, dollars, esc, extLink, page, shortUrl, webUrl } from "./util.js";
import { api } from "./api.js";
import { lang, T } from "./texts.js";
import { billedStep, bindSteps, costHtml, costTag, est, loadSteps, ownFor, stepLine, stepsQuery } from "./steps.js";
import { crumb, WAITING } from "./watches.js";

// --- Check the guide ---------------------------------------------------------------------------------------
let CHECK_FORM = null;   // the boxes ticked on « Check the guide », kept while the form is drawn again
export let NEW_CHECK = false;   // « New check » asked from « To handle »: its form opens at once
let PICK = "";  // a check asked by another page (#/check?new=candidates): ticked when the form opens
// The router says whether « New check » was asked (#/check?new), and which check it ticks (#/check?new=<check>)
export function setNewCheck(on, pick = "") { NEW_CHECK = on; PICK = pick; }
let CHECKS_KIND = "";  // the kind the history of the checks is narrowed to ("": all)
let CHECKS_SHOWN = 20;  // the list shows the newest; « older ones » asks for more
export const checkBadge = p => {
  const V = T.verif, [text, cls] = {
    running: [V.running, "attention"], "to-handle": [V.toHandle(p.counts.open), "attention"],
    handled: [V.handled, "ok"], clear: [V.ok, "ok"],
  }[p.status] || [p.status, "neutral"];
  return `<span class="badge ${cls}">${text}</span>${p.interrupted ? ` <span class="badge neutral">${V.interrupted}</span>` : ""}`;
};

// A check on the lists (« Check the guide », « To handle »): its kind, in colour, what it read, where it was started when
// not there, what it cost or is worth at list price, then the runs its leads went to that still wait for something
export function checkCardMaker(options) {
  const V = T.verif, titles = Object.fromEntries(options.map(o => [o.id, o.title[lang]]));
  const kindOf = Object.fromEntries(options.map(o => [o.id, o.kind || "health"]));
  const short = c => {
    const t = titles[c] || c, i = t.indexOf(":");
    const s = i < 0 ? t : kindOf[c] === "news" ? t.slice(i + 1).trim() : t.slice(0, i).trim();
    return s.charAt(0).toUpperCase() + s.slice(1);
  };
  const cardTitle = p => {
    const k = p.kinds?.[0] || "health";
    if (p.checks.includes("links") && p.checks.length === 1) return `${esc(short("links"))} · ${V.nLinks(p.links?.length || 0)}`;
    return k === "health" && p.checks.length > 2 ? V.nChecks(p.checks.length) : p.checks.map(c => esc(short(c))).join(" · ");
  };
  const linkItem = l => `<li>${extLink(l.url, esc(l.title || shortUrl(l.url)))}${l.kind === "pdf" ? ' <span class="kindtag">PDF</span>' : ""}${
    l.title ? ` <span class="muted small">· ${esc(new URL(l.url).hostname.replace(/^www\./, ""))}</span>` : ""}</li>`;
  const linksList = p => !p.links?.length ? "" : `<ul class="check-links">${p.links.slice(0, 3).map(linkItem).join("")}</ul>${
    p.links.length > 3 ? `<details class="check-links-more"><summary class="small">${V.moreLinks(p.links.length - 3)}</summary><ul class="check-links">${p.links.slice(3).map(linkItem).join("")}</ul></details>` : ""}`;
  const runLine = ([t, r]) => `<div class="run-line small"><span class="badge attention">${esc(T.statuses[r.status] || r.status)}</span>
    <a href="${r.status === "pr-open" && webUrl(r.pr_url) ? esc(r.pr_url) : `#/run/${encodeURIComponent(t)}`}"${r.status === "pr-open" ? ' target="_blank" rel="noopener"' : ""}><button type="button" class="small-button">${
      r.status === "pr-open" ? T.merge() : T.buttons[r.status] || T.details}</button></a> <span class="muted">${esc(t)}</span></div>`;
  const checkCard = p => `<div class="card row check-item kind-${p.kinds?.[0] || "health"}${["handled", "clear"].includes(p.status) ? " finished" : ""}" data-kinds="${(p.kinds || []).join(" ")}"><div class="grow">
        <div class="check-top">${(p.kinds || []).map(k => `<span class="kind-tag ${k}">${V.checkKinds[k]}</span>`).join("")}<b>${cardTitle(p)}</b>${
          p.checks.length === 1 && p.checks[0] === "links" ? `<span class="from-tag">${V.fromReport}</span>` : ""}</div>
        ${(p.kinds?.[0] || "health") === "health" && p.checks.length > 2 ? `<div class="muted small">${p.checks.map(c => esc(short(c).toLowerCase())).join(", ")}</div>` : ""}
        ${linksList(p)}
        <div class="muted small">${costTag(p.cost, p.unbilled_usd, !p.checks.some(c => options.find(o => o.id === c)?.model))} · ${
          new Date(p.started * 1000).toLocaleString(lang, { dateStyle: "short", timeStyle: "short" })}</div>
        <div class="muted small">${V.counts(p.counts)}</div>
        ${Object.entries(p.runs || {}).filter(([, r]) => WAITING.includes(r.status)).map(runLine).join("")}</div>
        <div class="check-side">${checkBadge(p)}
        <a href="#/check/${encodeURIComponent(p.id)}"><button${p.status === "to-handle" ? ' class="primary"' : ""}>${p.status === "to-handle" ? V.handle : T.details}</button></a></div></div>`;
  return checkCard;
}

export async function viewChecks() {
  await loadSteps();
  const kept = CHECK_FORM;  // drawn again after a step was changed for this verification: the boxes stay as they were
  CHECK_FORM = null;
  const [options, listed] = await Promise.all([api(`/api/verifications/options${stepsQuery()}`), api(`/api/verifications?limit=${CHECKS_SHOWN + 1}`)]);
  const verifs = listed.slice(0, CHECKS_SHOWN);
  const V = T.verif, titles = Object.fromEntries(options.map(o => [o.id, o.title[lang]]));
  // An estimate says where its price comes from when it is not a price set or fetched by the user (a default, none)
  const price = o => o.model ? costHtml(o.id, o.usd == null ? V.unknown : `≈ ${dollars(est(o, "usd"))}`) : V.free;
  const origin = o => o.model && o.price_origin && o.usd != null && billedStep(o.id)
    ? ` <span class="muted small">${esc(T.priceOrigin(o.price_origin))}</span>` : "";
  // What is left to handle comes first; a new check is folded away while leads remain (it would find them again)
  const pending = verifs.filter(p => ["to-handle", "running"].includes(p.status));
  const remaining = pending.reduce((s, p) => s + p.counts.open, 0);
  const checkCard = checkCardMaker(options);
  // The history can be narrowed to one kind (kept while the page is open)
  const kindCount = k => older.filter(p => (p.kinds || []).includes(k)).length;
  const older = verifs.filter(p => !pending.includes(p));
  page.innerHTML = `
    ${crumb()}<h1>${V.title}</h1>
    <p class="subtitle">${V.intro}</p>
    <p class="small"><a href="#/idea">${V.ideaLink}</a><br><a href="#/links">${V.linksLink}</a></p>
    ${pending.length ? `<h2>${V.toHandleTitle}</h2>${pending.map(checkCard).join("")}` : ""}
    <details class="new-check" id="new-check"${pending.length && !NEW_CHECK ? "" : " open"}><summary><h2>${V.newCheck}</h2></summary>
    ${remaining ? `<p class="attention-text">${V.warning(remaining)}</p>` : ""}
    <p class="tick-row"><button type="button" class="small-button" data-tick-checks="all">${V.tickAll}</button>
      <button type="button" class="small-button" data-tick-checks="none">${V.untickAll}</button>
      <button type="button" class="small-button" data-tick-checks="free">${V.onlyFree}</button></p>
    ${options.filter(o => !o.links_max).map(o => `<div class="card check-card"><label class="option">
      <input type="checkbox" data-check="${o.id}" ${(kept ? kept.checks.has(o.id) : PICK ? o.id === PICK : !o.model) ? "checked" : ""}>
      <div>
        <div class="header"><b>${esc(o.title[lang])}</b>
          <span class="badge ${o.model ? "attention" : "ok"}">${price(o)}</span>${origin(o)}
          ${o.tokens ? `<span class="muted small">${V.tokens(o.tokens)}</span>` : ""}</div>
        <p class="muted small">${esc(o.what[lang])}</p>
        ${o.limit ? `<p class="small attention-text">${esc(o.limit[lang])}</p>` : ""}
        <p class="muted small">${esc(o.note[lang])}${o.needs.length ? ` · ${V.needs(o.needs.map(n => titles[n]).join(", "))}` : ""}</p>
      </div></label>${o.model ? `<div class="card-foot">${stepLine(o.id)}</div>` : ""}${o.chapters ? `<div class="card-foot chapters" data-chapters-of="${o.id}" hidden>
        <p class="muted small">${V.chapters(costHtml(o.id, `≈ ${dollars(est(o, "usd_chapter") || 0)}`))}</p>
        ${o.chapters.map(c => `<label><input type="checkbox" data-chapter="${esc(c.id)}" ${(kept ? kept.chapters.has(c.id) : c.explore) ? "checked" : ""}> ${esc(c.id)} <span class="muted small">(${c.pages} p., ${T.chapters.kb(Math.round(c.kb))})</span></label>`).join("")}
        <p class="small"><a href="#/chapters">${T.chapters.edit}</a></p>
      </div>` : ""}</div>`).join("")}
    <p><button class="primary" id="start"></button></p>
    </details>
    <h2>${V.history}</h2>
    ${older.length ? `<p class="kind-filters">${["", "health", "light", "news"].map(k => `<button type="button" class="chip${CHECKS_KIND === k ? " on" : ""}" data-kind-filter="${k}">${
      k ? V.checkKinds[k] : V.allKinds} <span class="muted">${k ? kindCount(k) : older.length}</span></button>`).join("")}</p>` : ""}
    <div id="history">${older.map(checkCard).join("") || `<p class="muted">${V.none}</p>`}</div>
    ${listed.length > CHECKS_SHOWN ? `<p><button type="button" id="older">${T.menu.older}</button></p>` : ""}`;
  if ($("#older")) $("#older").onclick = () => { CHECKS_SHOWN += 40; viewChecks(); };
  const narrow = () => {
    page.querySelectorAll("#history .check-item").forEach(c => { c.hidden = !!CHECKS_KIND && !c.dataset.kinds.split(" ").includes(CHECKS_KIND); });
    page.querySelectorAll("[data-kind-filter]").forEach(b => b.classList.toggle("on", b.dataset.kindFilter === CHECKS_KIND));
  };
  page.querySelectorAll("[data-kind-filter]").forEach(b => b.onclick = () => { CHECKS_KIND = b.dataset.kindFilter; narrow(); });
  narrow();
  const boxes = [...page.querySelectorAll("[data-check]")];
  const total = () => {
    const ids = new Set(boxes.filter(c => c.checked).map(c => c.dataset.check));
    options.filter(o => ids.has(o.id)).forEach(o => o.needs.forEach(n => ids.add(n)));
    // A check with chapters (the exploration) shows them when it is ticked, and costs one call per chapter ticked
    page.querySelectorAll("[data-chapters-of]").forEach(d => { d.hidden = !ids.has(d.dataset.chaptersOf); });
    const chosen = options.filter(o => ids.has(o.id)), paid = chosen.filter(o => o.model), billed = paid.filter(o => billedStep(o.id));
    const usd = billed.reduce((s, o) => s + (est(o, "usd") || 0) + (o.chapters ? (est(o, "usd_chapter") || 0) * chapters().length : 0), 0);
    // Scripts only: free. Every model check on a subscription or a local model: said. Else what the billed ones cost.
    const worth = paid.reduce((s, o) => s + (est(o, "usd") || 0) + (o.chapters ? (est(o, "usd_chapter") || 0) * chapters().length : 0), 0);
    $("#start").innerHTML = V.start(!paid.length ? V.free : !billed.length ? costHtml(paid[0].id, `≈ ${dollars(worth)}`)
      : `≈ ${dollars(usd)}${billed.length < paid.length ? ` + ${T.perStep.restUnbilled}` : ""}`);
    $("#start").disabled = ids.size === 0 || chosen.some(o => o.chapters && !chapters().length);
  };
  const chapters = () => [...page.querySelectorAll("[data-chapter]")].filter(c => c.checked).map(c => c.dataset.chapter);
  boxes.forEach(c => c.onchange = total);
  // All the checks, none, or the free ones (the default: those that call no model)
  const isFree = new Set(options.filter(o => !o.model).map(o => o.id));
  page.querySelectorAll("[data-tick-checks]").forEach(b => b.onclick = () => {
    const which = b.dataset.tickChecks;
    boxes.forEach(c => { c.checked = which === "all" || (which === "free" && isFree.has(c.dataset.check)); });
    total();
  });
  page.querySelectorAll("[data-chapter]").forEach(c => c.onchange = total);
  bindSteps(page, () => {
    CHECK_FORM = { checks: new Set(boxes.filter(c => c.checked).map(c => c.dataset.check)), chapters: new Set(chapters()) };
    viewChecks();
  });
  total();
  $("#start").onclick = async () => {
    $("#start").disabled = true;
    const checks = boxes.filter(c => c.checked).map(c => c.dataset.check);
    const { id } = await api("/api/verifications", { checks, lang, steps: ownFor(checks), ...(checks.includes("explore") ? { chapters: chapters() } : {}) });
    location.hash = `/check/${encodeURIComponent(id)}`;
  };
}
