// @ts-check
/* vault-watch: the sources of the watch: what each one brought, their check, and the proposals to change the list. */

import { $, esc, extLink, followLater, page, stopFollowing } from "./util.js";
import { api } from "./api.js";
import { lang, T } from "./texts.js";

// --- Sources of the watch ----------------------------------------------------------------------------
const SOURCE_ORDER = ["error", "noise", "silent", "leads", "quiet", "useful"];  // what to look at first
const SOURCE_CLASS = { error: "error", noise: "attention", silent: "attention", leads: "neutral", quiet: "neutral", useful: "ok" };
// The columns, in the order of T.sources.columns: the field each one sorts by, and whether it is a number
const SOURCE_COLUMNS = [["id"], ["type"], ["last_item"], ["source_last"], ["collected", true], ["kept", true], ["judged", true], ["useful", true],
  ["proposed", true], ["accepted", true], ["verdict"]];
// The reader's choices, kept while the page is open: the column sorted (none: what to look at first), its
// direction, the states shown (none: all)
const SOURCES_VIEW = { sort: "", dir: 1, states: new Set(), query: "" };

// A table wider than its card: `html` in a frame that scrolls sideways and says so (a shade on the side that
// hides columns, an arrow that stays in the window while the table is there). `wideTables` wires the frames of a page.
const chevron = points => `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const wideTable = (html, left, right) => `<div class="card wide"><div class="scroll-x">${html}</div>
  <div class="scroll-arrows"><button type="button" data-scroll="-1" title="${esc(left)}" aria-label="${esc(left)}">${chevron("15,5 8,12 15,19")}</button>
  <button type="button" data-scroll="1" title="${esc(right)}" aria-label="${esc(right)}">${chevron("9,5 16,12 9,19")}</button></div></div>`;
function wideTables(root) {
  root.querySelectorAll(".card.wide").forEach(card => {
    const box = card.querySelector(".scroll-x");
    if (!box) return;
    const mark = () => {
      card.classList.toggle("can-left", box.scrollLeft > 1);
      card.classList.toggle("can-right", box.scrollLeft + box.clientWidth < box.scrollWidth - 1);
      // Where the fixed first column ends: the shade that says columns are hidden on the left starts there
      card.style.setProperty("--first", `${box.querySelector("th")?.offsetWidth || 0}px`);
    };
    box.addEventListener("scroll", mark, { passive: true });
    new ResizeObserver(mark).observe(box);
    // The arrows stay above the bar of actions, whatever its height (its buttons wrap on a narrow window)
    const bar = /** @type {HTMLElement | null} */ (document.querySelector(".bar")), lift = () => card.style.setProperty("--bar", `${bar ? bar.offsetHeight : 0}px`);
    if (bar) new ResizeObserver(lift).observe(bar);
    lift();
    card.querySelectorAll("[data-scroll]").forEach(b => b.onclick = () =>
      box.scrollBy({ left: Number(b.dataset.scroll) * box.clientWidth * 0.6, behavior: "smooth" }));
    mark();
  });
}

function sortSources(feeds) {
  const { sort, dir } = SOURCES_VIEW, number = (SOURCE_COLUMNS.find(c => c[0] === sort) || [])[1];
  const first = (a, b) => SOURCE_ORDER.indexOf(a.verdict) - SOURCE_ORDER.indexOf(b.verdict);
  const compare = !sort ? (a, b) => first(a, b) || b.collected - a.collected
    : sort === "verdict" ? (a, b) => dir * first(a, b)
    : number ? (a, b) => dir * (a[sort] - b[sort])
    // A source without a date stays at the bottom in both directions: it has nothing to compare
    : (a, b) => !a[sort] !== !b[sort] ? (a[sort] ? -1 : 1) : dir * String(a[sort]).localeCompare(String(b[sort]));
  return feeds.slice().sort((a, b) => compare(a, b) || a.id.localeCompare(b.id));
}

const SOURCE_TICKS = {};  // proposals ticked or unticked by the reader, kept while the page refreshes

export async function viewSources() {
  stopFollowing();
  const s = await api("/api/sources"), S = T.sources;
  if (location.hash.slice(1) !== "/sources") return;  // left the page meanwhile
  if (!s.file) { page.innerHTML = `<h1>${S.title}</h1><p class="subtitle">${S.none}</p>`; return; }
  const rules = S.rules(s.noise_min, s.noise_share), view = SOURCES_VIEW, check = s.check, busy = s.checking.running;
  s.feeds.forEach(f => { f.source_last = f.probe?.last || ""; });
  const by = v => s.feeds.filter(f => f.verdict === v);
  const cell = n => `<td class="number">${n || ""}</td>`;
  // What the source answered at the last check: its last publication, and what is wrong with it
  const answered = f => {
    const p = f.probe;
    if (!p) return "—";
    const note = p.state === "ok" ? "" : p.state === "moved" ? S.probe.moved(esc(p.moved)) : p.state === "stale" ? S.probe.stale(esc(p.last))
      : S.probe[p.state] || esc(p.state);
    return `${p.state === "stale" ? "" : `<span class="nowrap">${esc(p.last) || "—"}</span>`}${note ? `<div class="${p.state === "stale" ? "muted" : "error-text"} small">${note}</div>` : ""}`;
  };
  const what = f => esc(f.repo || f.author || f.url || f.name || "");
  const proposal = (p, group) => {
    const done = p.applied, later = !done && p.later;
    const ticked = SOURCE_TICKS[p.id] ?? p.recommended;
    return `<li${done || later ? ' class="handled"' : ""}><label>${done ? `<span class="badge ok">${S.applied}</span>`
      : later ? `<span class="badge neutral">${S.later}</span> <button class="small-button" data-now="${p.id}">${S.decideNow}</button>`
      : `<input type="checkbox" data-proposal="${p.id}" data-group="${group}"${ticked ? " checked" : ""}>`} <span><b>${esc(p.feed.id)}</b>
      <span class="muted">(${esc(p.feed.type || "rss")}${what(p.feed) ? `, ${what(p.feed)}` : ""})</span> : ${esc(S.why[p.why](p))}${
      p.recommended && !done && !later ? ` <span class="badge neutral">${S.recommended}</span>` : ""}${
      done?.pr_url ? ` ${extLink(done.pr_url, "PR")}` : ""}</span></label></li>`;
  };
  const groups = check ? [
    ["remove", check.proposals.filter(p => p.action === "remove")], ["change", check.proposals.filter(p => p.action === "change")],
    ["add", check.proposals.filter(p => p.action === "add" && p.why !== "no-advisories")],
    ["advisories", check.proposals.filter(p => p.why === "no-advisories")]].filter(([, list]) => list.length) : [];
  const last = check?.applied?.filter(a => !a.state).at(-1);  // the pull request (or branch) still to merge
  const draw = () => {
    const sideways = page.querySelector(".card.wide .scroll-x")?.scrollLeft || 0;  // kept when the table is drawn again
    const q = view.query.trim().toLowerCase(), open = p => !p.applied && !p.later;
    const typed = f => !q || [f.id, f.target, f.url, f.type, f.tier, S.verdicts[f.verdict]].some(x => x && String(x).toLowerCase().includes(q));
    const shown = sortSources(s.feeds.filter(f => (!view.states.size || view.states.has(f.verdict)) && typed(f)));
    const arrow = key => view.sort !== key ? "" : view.dir > 0 ? " ▲" : " ▼";
    page.innerHTML = `
    <h1>${S.title}</h1>
    <p class="subtitle">${s.period.watches ? S.intro(s.period, s.runs, esc(s.file)) : S.noHistory}</p>
    <p><button class="primary" id="check"${busy ? " disabled" : ""}>${busy ? S.checking(s.checking.done, s.checking.total) : S.check}</button>
      <span class="muted small">${check ? S.checked(new Date(check.checked).toLocaleString(lang)) : S.neverChecked} ${S.checkHelp}</span></p>
    ${s.checking.error ? `<p class="error-text">${esc(s.checking.error)}</p>` : ""}
    ${check ? `<h2>${S.proposals(check.proposals.filter(open).length, check.proposals.filter(p => p.applied).length, check.proposals.filter(p => !p.applied && p.later).length)}</h2>
      ${last ? `<p class="small">${S.appliedTo(esc(last.branch), last.pr_url ? extLink(last.pr_url, esc(last.pr_url)) : "")}</p>` : ""}
      ${groups.length ? groups.map(([g, list]) => `<details class="card foldable"${g === "advisories" ? "" : " open"}>
        <summary class="header"><b>${S.groups[g]}</b> <span class="badge neutral">${list.length}</span>${
          list.some(open) ? ` <button class="small-button" data-tick-group="${g}">${T.verif.tickCard(list.filter(open).length)}</button>` : ""}</summary>
        <ul class="leads">${list.map(p => proposal(p, g)).join("")}</ul></details>`).join("") : `<p class="muted">${S.noProposals}</p>`}
      <p class="muted small">${S.staleNote(check.stale_days)}</p>
      ${(check.answered || []).length ? `<details class="card foldable"><summary class="header"><b>${S.answered.title}</b>
        <span class="badge neutral">${check.answered.length}</span>${check.answered.some(a => !a.page_found || !a.named)
          ? ` <span class="badge attention">${S.answered.toLook}</span>` : ""}</summary>
        <p class="muted small">${S.answered.help}</p>
        <ul class="leads">${check.answered.map(a => `<li><b>${esc(a.id)}</b> · <code>${esc(a.page)}</code>${a.why ? ` : ${esc(a.why)}` : ""}${
          !a.page_found ? ` <span class="badge attention">${S.answered.gone}</span>` : !a.named ? ` <span class="badge attention">${S.answered.unnamed}</span>` : ""}</li>`).join("")}</ul>
      </details>` : ""}
      ${view.error ? `<p class="error-text">${esc(view.error)}</p>` : ""}
      ${check.proposals.some(open) ? `<div class="bar"><button id="all">${T.verif.tickAll}</button><button id="nothing">${T.verif.untickAll}</button>
        <button id="later" title="${esc(S.putOffHelp)}"></button><button class="primary" id="apply"></button></div>
        <p class="muted small">${S.putOffHelp}</p>` : ""}` : ""}
    <ul class="small filters">
      <li><button class="badge neutral${view.states.size ? " dim" : ""}" data-state="" aria-pressed="${!view.states.size}">${S.all(s.feeds.length)}</button> ${S.filterHelp}</li>
      ${SOURCE_ORDER.filter(v => by(v).length).map(v => `<li><button class="badge ${SOURCE_CLASS[v]}${view.states.size && !view.states.has(v) ? " dim" : ""}"
        data-state="${v}" aria-pressed="${view.states.has(v)}">${S.count(by(v).length, S.verdicts[v])}</button> ${rules[v]}</li>`).join("")}</ul>
    <p class="muted small table-tools"><input type="search" id="source-filter" value="${esc(view.query)}" placeholder="${esc(S.search)}" aria-label="${esc(S.search)}">
      <span>${S.shown(shown.length, s.feeds.length)}${view.sort ? ` · <button class="small-button" id="default-sort">${S.defaultSort}</button>` : ""}</span></p>
    ${wideTable(`<table class="sources">
      <thead><tr>${S.columns.map((c, i) => { const [key, number] = SOURCE_COLUMNS[i]; return `<th${number ? ' class="number"' : ""}${
        view.sort === key ? ` aria-sort="${view.dir > 0 ? "ascending" : "descending"}"` : ""}><button class="sort" data-sort="${key}" title="${esc(S.sortBy(c))}">${c}${arrow(key)}</button></th>`; }).join("")}</tr></thead>
      <tbody>${shown.map(f => `<tr>
        <td class="first"><b>${esc(f.id)}</b><div class="muted small">${f.url ? extLink(f.url, esc(f.target)) : esc(f.target)}</div></td>
        <td class="small">${esc(f.type)}${f.tier ? ` · ${esc(f.tier)}` : ""}</td>
        <td class="small nowrap">${esc(f.last_item) || "—"}</td>
        <td class="small">${answered(f)}</td>
        ${cell(f.collected)}${cell(f.kept)}${cell(f.judged)}${cell(f.useful)}${cell(f.proposed)}${cell(f.accepted)}
        <td class="nowrap"><span class="badge ${SOURCE_CLASS[f.verdict]}" title="${esc(rules[f.verdict])}">${S.verdicts[f.verdict]}</span>${
          f.insurance ? ` <span class="muted small" title="${esc(S.insurance)}">🛡</span>` : ""}</td></tr>`).join("")}</tbody>
    </table>`, S.scrollLeft, S.scrollRight)}
    <p class="muted small">${S.help.join(" ")} 🛡 ${S.insurance}.</p>
    ${s.removed.length ? `<p class="muted small">${S.removed(s.removed.length)} ${s.removed.map(r => `<code>${esc(r.id)}</code> (${r.items})`).join(", ")}</p>` : ""}`;
    // A state: shown alone, or with the others already chosen; « all » clears the choice
    page.querySelectorAll("[data-state]").forEach(b => b.onclick = () => {
      const v = b.dataset.state;
      if (!v) view.states.clear(); else if (view.states.has(v)) view.states.delete(v); else view.states.add(v);
      draw();
    });
    // A column: a first click sorts it (numbers from the largest, texts from A), a second one turns it round
    page.querySelectorAll("[data-sort]").forEach(b => b.onclick = () => {
      const key = b.dataset.sort, number = SOURCE_COLUMNS.find(c => c[0] === key)[1];
      view.dir = view.sort === key ? -view.dir : number ? -1 : 1;
      view.sort = key;
      draw();
      page.querySelector(`[data-sort="${key}"]`)?.focus();  // the keyboard stays on the column
    });
    if ($("#default-sort")) $("#default-sort").onclick = () => { view.sort = ""; view.dir = 1; draw(); };
    page.querySelector(".card.wide .scroll-x").scrollLeft = sideways;
    wideTables(page);
    // The text typed filters as it is typed; the page is drawn again, the caret stays where it was
    $("#source-filter").oninput = e => {
      view.query = e.target.value;
      const at = e.target.selectionStart;
      draw();
      $("#source-filter").focus();
      $("#source-filter").setSelectionRange(at, at);
    };
    $("#check").onclick = async () => { $("#check").disabled = true; await api("/api/sources/check", {}); viewSources(); };
    // The proposals: ticked ones go to one pull request
    const boxes = [...page.querySelectorAll("[data-proposal]")];
    const count = () => {
      const n = boxes.filter(b => b.checked).length;
      if ($("#apply")) { $("#apply").textContent = S.apply(n, s.repository); $("#apply").disabled = n === 0 || busy; }
      if ($("#later")) { $("#later").textContent = S.putOff(n); $("#later").disabled = n === 0 || busy; }
    };
    const tick = (list, on) => { list.forEach(b => { b.checked = on; SOURCE_TICKS[b.dataset.proposal] = on; }); count(); };
    boxes.forEach(b => b.onchange = () => { SOURCE_TICKS[b.dataset.proposal] = b.checked; count(); });
    // A whole group (all ticked: untick it), or every proposal
    page.querySelectorAll("[data-tick-group]").forEach(b => b.onclick = e => {
      e.preventDefault();  // in the group's title: tick, do not fold
      const group = boxes.filter(c => c.dataset.group === b.dataset.tickGroup);
      tick(group, !group.every(c => c.checked));
    });
    if ($("#all")) { $("#all").onclick = () => tick(boxes, true); $("#nothing").onclick = () => tick(boxes, false); }
    count();
    // Put off until the next check, or decide now after all: nothing changes in the guide
    const later = async (ids, on) => {
      try {
        await api("/api/sources/later", { ids, on });
        view.error = "";
      } catch (e) {
        view.error = e.message;
      }
      viewSources();
    };
    if ($("#later")) $("#later").onclick = () => later(boxes.filter(b => b.checked).map(b => b.dataset.proposal), true);
    page.querySelectorAll("[data-now]").forEach(b => b.onclick = e => { e.preventDefault(); later([b.dataset.now], false); });
    if ($("#apply")) $("#apply").onclick = async () => {
      $("#apply").disabled = true;
      try {
        await api("/api/sources/apply", { ids: boxes.filter(b => b.checked).map(b => b.dataset.proposal) });
        view.error = "";
      } catch (e) {
        view.error = e.message;
      }
      viewSources();
    };
  };
  draw();
  if (busy) followLater(() => viewSources().catch(() => {}), 1500);
}
