// @ts-check
/* vault-watch: the pause before publishing: what was checked, the pages changed beside their translation (corrected
   or translated again from here), then the push and the pull request. */

import { $, dollars, esc, extLink, langOf, page, shortUrl } from "./util.js";
import { api } from "./api.js";
import { kb, signedKb, T } from "./texts.js";
import { en } from "./explain.js";
import { costHtml, costOf } from "./steps.js";
import { changeView } from "./diff.js";
import { addedPart, highlightEditor, hlNav } from "./editor.js";
import { alignPairs } from "./pairs.js";
import { route } from "./router.js";
import { bindProof, proofChecks } from "./proofread.js";

export async function viewPublish(r, title) {
  const P = T.pub, p = { mirror_problems: [], link_problems: [], ...r.pause }, at = `/api/runs/${encodeURIComponent(r.thread)}`;
  const linksChecked = p.link_problems !== null;   // null: the guide declares no source audit
  if (!linksChecked) p.link_problems = [];
  const diff = await api(`${at}/diff`).catch(() => "");
  const color = l => l.startsWith("+") && !l.startsWith("+++") ? "plus" : l.startsWith("-") && !l.startsWith("---") ? "minus" : "";
  const titleOf = path => (r.titles || {})[path] || path;
  // The pages changed, each with its mirrors (graph.mirror keeps the source beside its translation)
  const pages = [];
  for (const x of r.mirror_pairs || []) {
    let page = pages.find(y => y.page === x.page);
    if (!page) pages.push(page = { page: x.page, mirrors: [] });
    page.mirrors.push(x);
  }
  const anchor = path => `pub-${pages.findIndex(x => x.page === path)}`;
  const toPage = path => pages.some(x => x.page === path)
    ? `<a href="#" data-to-page="${esc(path)}">${esc(titleOf(path))}</a>` : `<code>${esc(path)}</code>`;
  // « Before publishing »: what was checked, one line each
  const row = (icon, cls, name, what) => `<div class="pub-row"><span class="pub-i ${cls}">${icon}</span><b>${name}</b><div>${what}</div></div>`;
  const links = p.link_problems.map(x => {
    const m = x.match(/^(NEW )?(.*?): (https?:\/\/\S+) \((.*)\)$/);
    if (!m) return `<li>${en(x)}</li>`;
    const [, isNew, label, url, cited] = m;
    const why = label.startsWith("blocked") ? P.linkBlocked : P.linkDead(label);
    return `<li>${extLink(url, esc(shortUrl(url)))} <span class="badge neutral">${isNew ? P.linkNew : P.linkOld}</span><br>
      <span class="muted small">${why} ${P.citedBy} ${cited.split(", ").map(toPage).join(", ")}.</span></li>`;
  });
  const weight = r.weight?.before ? `${P.weight(kb(r.weight.before), kb(r.weight.after), signedKb(r.weight.after - r.weight.before))}${
    (r.weight.pages || []).length ? `<br><span class="muted small">${r.weight.pages.slice(0, 5).map(([x, d]) => `${toPage(x)} ${signedKb(d)}`).join(" · ")}</span>` : ""}` : "";
  const checks = [
    p.audit_ok === null ? row("–", "info-i", P.audits, T.notChecked)
      : p.audit_ok ? row("✓", "ok-i", P.audits, `OK <span class="muted small">${P.auditsWhat}</span>`)
      : row("✗", "bad-i", P.audits, `<span class="error-text">${T.auditsRed}</span><details><summary class="small">${P.log}</summary><pre>${esc(r.audit_log)}</pre></details>`),
    r.mode === "mirror" || r.mirrored.length || p.mirror_problems.length
      ? row(p.mirror_problems.length ? "!" : "✓", p.mirror_problems.length ? "warn-i" : "ok-i", P.translation,
        `${P.mirrored(r.mirrored.length)}${p.mirror_problems.length ? `<ul>${p.mirror_problems.map(x => `<li>${en(x)}</li>`).join("")}</ul>` : ""}`) : "",
    !linksChecked ? row("–", "info-i", P.links, T.linksNotChecked)
      : links.length ? row("!", "warn-i", P.linksToCheck(links.length), `<ul class="pub-links">${links.join("")}</ul>`)
      : row("✓", "ok-i", P.links, T.linksOk),
    weight ? row("ⓘ", "info-i", P.weightTitle, weight) : "",
    (r.proofread_log || []).length ? row("ⓘ", "info-i", P.proofTitle, r.proofread_log.map(x =>
      P.proofLine(x.checks.map(k => T.languages.check.kinds[k]).join(", "), x.fixes, x.applied)).join("<br>")) : "",
  ].join("");
  // A page changed: one line folded (its title, its path, its passages, its buttons), open: source beside mirror
  const est = x => (r.retranslate_usd || {})[x.page];
  const price = x => est(x) != null ? `≈ ${dollars(est(x))}` : "";
  const pageBlock = (x, i) => {
    const passages = x.mirrors[0].source.length;
    return `<details class="pub-page" id="pub-${i}" data-page="${esc(x.page)}"${i === 0 && pages.length <= 3 ? " open" : ""}>
      <summary><span class="pub-name"><span class="pub-title">${esc(titleOf(x.page))}</span><code title="${esc(x.page)}">${esc(x.page)}</code></span>
        <span class="badge neutral">${P.passages(passages)}</span>
        <span class="pub-tools"><button type="button" class="small-button" data-correct="${i}">✎ ${P.correct}</button>
        <button type="button" class="small-button" data-again="${i}" title="${esc(`${P.again}${price(x) ? ` · ${costOf("mirror", price(x))}` : ""}`)}">↻ ${P.againShort}${
          price(x) ? ` ${costOf("mirror", price(x)) === T.subscription ? `<s class="worth">${price(x)}</s>` : esc(costOf("mirror", price(x)))}` : ""}</button></span></summary>
      <div class="pub-editor" data-editor="${i}" hidden></div>
      <div class="pub-pairs">${x.mirrors.map(m => alignPairs(m.source, m.target).map(({ source: src, target: tgt }) => {
        return `<div class="pair"><div><p class="muted small">${T.pairs.source}</p>${src ? changeView(src[0], src[1], langOf(x.page)) : `<p class="muted small">—</p>`}</div>
          <div><p class="muted small">${T.pairs.target} · <code>${esc(m.mirror)}</code></p>${tgt ? changeView(tgt[0], tgt[1], langOf(m.mirror)) : `<p class="muted small">${T.pairs.none}</p>`}</div></div>`;
      }).join("")).join("")}</div></details>`;
  };
  page.innerHTML = `${title}
    ${r.error ? `<p class="error-text"><b>${T.publishFailed}</b> ${esc(r.error)}</p>` : ""}
    <p class="small">${T.branchReady(esc(p.branch))}</p>
    <div class="card"><h3>${P.before}</h3><div class="pub-checks">${checks}</div></div>
    ${pages.length ? `<h2>${P.pagesTitle} <span class="muted small">· ${pages.length}</span></h2>
      <p class="small"><button type="button" class="small-button" id="unfold-pages">${P.unfoldAll}</button></p>
      ${pages.map(pageBlock).join("")}` : ""}
    <details${pages.length ? "" : " open"}><summary>${pages.length ? P.rawDiff : T.changes}</summary>
      <pre>${diff.split("\n").map(l => `<span class="${color(l)}">${esc(l)}</span>`).join("\n") || esc(p.diffstat)}</pre></details>
    <p class="error-text" id="pub-error"></p>
    <div class="bar">
      <button id="no">${T.doNotPublish}</button>
      <button class="primary" id="yes">${p.local ? T.keepLocal : T.publish}</button>
    </div>`;
  const send = async go => {
    page.querySelectorAll(".bar button").forEach(b => b.disabled = true);
    await api(`${at}/publish`, { go });
    route();
  };
  // Check again, or translate again: the run goes on, then comes back here with its checks up to date
  const again = async body => {
    page.querySelectorAll("button").forEach(b => b.disabled = true);
    try { await api(`${at}/publish`, body); route(); }
    catch (e) { $("#pub-error").textContent = e.message; page.querySelectorAll("button").forEach(b => b.disabled = false); }
  };
  $("#yes").onclick = () => send(true);
  $("#no").onclick = () => confirm(T.confirmNo) && send(false);
  if ($("#unfold-pages")) $("#unfold-pages").onclick = () => {
    const all = [...page.querySelectorAll(".pub-page")], open = !all.every(d => d.open);
    all.forEach(d => { d.open = open; });
  };
  // A page named above (its weight, a link cited): the page is opened, brought into view, and glows a moment
  page.querySelectorAll("[data-to-page]").forEach(a => a.onclick = e => {
    e.preventDefault();
    const d = $(`#${anchor(a.dataset.toPage)}`);
    d.open = true;
    d.scrollIntoView({ block: "start", behavior: "smooth" });
    d.classList.remove("flash"); void d.offsetWidth; d.classList.add("flash");
    setTimeout(() => d.classList.remove("flash"), 1800);
  });
  // « Translate again »: the page's translation starts over from the base (billed)
  page.querySelectorAll("[data-again]").forEach(b => b.onclick = e => {
    e.preventDefault(); e.stopPropagation();
    const x = pages[Number(b.dataset.again)];
    if (confirm(P.confirmAgain(titleOf(x.page), est(x) != null ? costOf("mirror", `≈ ${dollars(est(x))}`) : ""))) again({ action: "retranslate", pages: [x.page], fresh: true });
  });
  // « Correct »: the source page and its mirror side by side; saved, then checked again (or the source translated again)
  page.querySelectorAll("[data-correct]").forEach(b => b.onclick = async e => {
    e.preventDefault(); e.stopPropagation();
    const i = Number(b.dataset.correct), x = pages[i], box = page.querySelector(`[data-editor="${i}"]`), d = $(`#pub-${i}`);
    d.open = true;
    if (!box.hidden) return;
    const paths = [x.page, ...x.mirrors.map(m => m.mirror)];
    let texts;
    try { texts = await Promise.all(paths.map(path => api(`${at}/page?path=${encodeURIComponent(path)}`).then(t => t.text))); }
    catch (err) { $("#pub-error").textContent = err.message; return; }
    const saved = [...texts];
    box.hidden = false;
    box.innerHTML = `<p class="muted small">${P.correctHelp}</p>
      <div class="pair">${paths.map((path, k) => `<div><p class="muted small hl-head">${k ? T.pairs.target : T.pairs.source} · <code>${esc(path)}</code> ${hlNav()}</p>
        <textarea data-text-of="${k}" spellcheck="true" lang="${langOf(path)}">${esc(texts[k])}</textarea></div>`).join("")}</div>
      <p class="muted small">${T.retouchPause.undoHelp}</p>
      <div class="pub-warn" hidden></div>
      <p class="tick-row"><button type="button" data-save>${P.saveCheck}</button> <button type="button" data-close>${T.retouchPause.close}</button></p>`;
    const areas = [...box.querySelectorAll("textarea")];
    areas.forEach(t => { t.style.height = `${Math.min(window.innerHeight * 0.6, t.scrollHeight + 4)}px`; });
    // Each text with the passages the run changed in green (the source's new text, the translation's), opened at the first
    areas.forEach((t, k) => {
      const passages = k ? x.mirrors[k - 1].target.map(([a, b]) => addedPart(a, b)) : x.mirrors[0].source.map(([a, b]) => addedPart(a, b));
      highlightEditor(t, passages, t.closest(".pair > div").querySelector(".hl-nav")).go(0);
    });
    const changed = () => areas.map((t, k) => t.value !== saved[k]);
    const said = () => {
      const c = changed();
      box.querySelector("[data-save]").disabled = !c.some(Boolean);
      box.querySelector("[data-close]").textContent = c.some(Boolean) ? T.retouchPause.revert : T.retouchPause.close;
    };
    areas.forEach(t => t.oninput = said);
    said();
    box.querySelector("[data-close]").onclick = () => {
      if (changed().some(Boolean)) { areas.forEach((t, k) => { t.focus(); t.select(); if (!document.execCommand?.("insertText", false, saved[k])) t.value = saved[k]; }); said(); return; }
      box.hidden = true; box.innerHTML = "";
    };
    box.querySelector("[data-save]").onclick = async () => {
      const c = changed();
      try { await Promise.all(paths.map((path, k) => c[k] ? api(`${at}/page`, { path, text: areas[k].value }) : null)); }
      catch (err) { $("#pub-error").textContent = err.message; return; }
      areas.forEach((t, k) => { saved[k] = t.value; });
      said();
      // The source corrected: its proofreading offered (then the translation follows); its translation not
      // corrected: say it (the guide's checks would fail), offer to translate it
      if (c[0]) {
        const w = box.querySelector(".pub-warn"), alone = !c.slice(1).some(Boolean) && x.mirrors.length;
        w.hidden = false;
        w.innerHTML = `${alone ? `<span>⚠️ ${P.sourceOnly}</span>` : ""}
          <div class="pub-proof"><span class="small">${P.proofAsk}</span>${proofChecks(false)}
            <button type="button" data-proofread disabled>${P.proofread("")}</button></div>
          ${alone ? `<button type="button" data-translate-mine>↻ ${P.againMine} ${costHtml("mirror", "")}</button>` : ""}
          <button type="button" data-check-only>${alone ? P.checkOnly : P.recheckOnly}</button>`;
        const proof = await bindProof(w.querySelector(".pub-proof"), at, p => {
          const go = w.querySelector("[data-proofread]");
          go.disabled = !p.asked.length;
          go.textContent = P.proofread(p.cost);
        });
        w.querySelector("[data-proofread]").onclick = () => again({ action: "proofread", checks: proof.asked() });
        if (alone) w.querySelector("[data-translate-mine]").onclick = () => again({ action: "retranslate", pages: [x.page], fresh: false });
        w.querySelector("[data-check-only]").onclick = () => again({ action: "recheck" });
        return;
      }
      again({ action: "recheck" });
    };
  });
}
