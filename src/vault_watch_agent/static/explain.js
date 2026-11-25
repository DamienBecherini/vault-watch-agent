// @ts-check
/* vault-watch: the lines a model or a check wrote in English, shown in the language of the interface. */

import { esc, page } from "./util.js";
import { api } from "./api.js";
import { lang } from "./texts.js";

// A line a model or a check wrote in English (why a correction, a verdict, a doubt, what a check found): in another
// language, shown translated once the server has it (/api/explain, explain.py), the English on hover. Lines already
// translated are drawn translated at once, so that a screen drawn again does not flicker.
const EXPLAINED = {}, ASKED = new Set();  // {lang: {english: translated}}; the lines asked, per language
export function en(text) {
  if (!text) return "";
  const done = lang !== "en" && EXPLAINED[lang]?.[text];
  return done ? `<span data-en="${esc(text)}" data-done title="${esc(text)}">${esc(done)}</span>`
    : `<span data-en="${esc(text)}"${lang === "en" ? " data-done" : ""}>${esc(text)}</span>`;
}
const shownRun = () => decodeURIComponent((location.hash.match(/^#\/(?:run|check)\/([^?]+)/) || [])[1] || "");
async function explainPage() {
  if (lang === "en") return;
  const asked = lang, memo = EXPLAINED[asked] ||= {};
  const put = () => page.querySelectorAll("[data-en]:not([data-done])").forEach(x => {
    if (memo[x.dataset.en]) { x.textContent = memo[x.dataset.en]; x.title = x.dataset.en; x.dataset.done = ""; }
  });
  put();
  const missing = [...new Set([...page.querySelectorAll("[data-en]:not([data-done])")].map(x => x.dataset.en))]
    .filter(t => !ASKED.has(`${asked}\n${t}`));
  if (!missing.length) return;
  missing.forEach(t => ASKED.add(`${asked}\n${t}`));
  const r = await api("/api/explain", { texts: missing, lang: asked, thread: shownRun() }).catch(() => ({ lines: {} }));
  const got = Object.keys(r.lines || {}).filter(t => missing.includes(t));
  Object.assign(memo, r.lines || {});
  if (got.length && got.length < missing.length) missing.filter(t => !got.includes(t)).forEach(t => ASKED.delete(`${asked}\n${t}`));  // more than one ask holds: the rest next
  if (lang === asked) put();
  if (got.length && got.length < missing.length) explainPage();
}
let explainTimer = null;
new MutationObserver(() => { clearTimeout(explainTimer); explainTimer = setTimeout(explainPage, 200); })
  .observe(page, { childList: true, subtree: true });
