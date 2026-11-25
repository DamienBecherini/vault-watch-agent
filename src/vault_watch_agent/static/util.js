// @ts-check
/* vault-watch: the helpers every screen uses: the DOM ($, page), HTML escaped, links out of the page and into
   Obsidian, the parts of a lead, a help bubble, the room kept for the bar at the bottom of a screen, and the timer that
   draws a screen again while something runs on it. */

// The guide's languages, put in the page by the server (web.index): its source, and the folder of each mirror. The
// lang of a passage (spellcheck, hyphenation, screen readers) follows the page it comes from; "" when unknown.
const GUIDE = (() => {
  try { return JSON.parse(document.querySelector('meta[name="vault-watch-guide"]')?.getAttribute("content") || "{}"); }
  catch { return {}; }
})();
/** @returns {string} the guide's source language ("fr") */
export const sourceLang = () => GUIDE.source || "";
/** @param {string} path a page of the guide @returns {string} its language: a mirror's when it is in its folder */
export function langOf(path) {
  for (const [code, folder] of Object.entries(GUIDE.mirrors || {}))
    if (folder && String(path || "").startsWith(String(folder))) return code;
  return sourceLang();
}

export const $ = s => document.querySelector(s);
export const page = $("#page");
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
export const dollars = n => `${(n ?? 0).toFixed(2)} $`;
// A link out of the page: http(s) only (a source written by a model or a feed could be « javascript: »), else its text
export const webUrl = url => /^https?:\/\//i.test(String(url || ""));
export const extLink = (url, text) => webUrl(url) ? `<a href="${esc(url)}" target="_blank" rel="noopener">${text}</a>` : text;
// A lead or a finding as one line (news.line, verify._line): « [kind] pages: text Read also: a, b. Sources: u, v ».
// Its parts, to draw them apart; the line itself stays what is sent to a run.
export function leadParts(line) {
  let rest = line, sources = [], read = [];
  const s = rest.match(/ Sources: (https?:\/\/\S.*)$/);
  if (s) { sources = s[1].split(/,\s+/).filter(u => /^https?:\/\//.test(u)); rest = rest.slice(0, s.index); }
  const r = rest.match(/ Read also: ([^\n]*?)\.$/);
  if (r) { read = r[1].split(/,\s+/); rest = rest.slice(0, r.index); }
  const k = rest.match(/^\[([^\]]+)\] ([^:]*?): /);
  if (!k) return { kind: "", pages: [], text: rest, read, sources };
  return { kind: k[1], pages: k[2] === "no page yet" ? [] : k[2].split(", "), text: rest.slice(k[0].length), read, sources };
}
// Where a lead comes from, in a few words: the repository on GitHub, else the site
export const origin = u => {
  try {
    const a = new URL(u), parts = a.pathname.split("/").filter(Boolean);
    return a.hostname === "github.com" && parts.length >= 2 ? `${parts[0]}/${parts[1]}` : a.hostname.replace(/^www\./, "");
  } catch { return u; }
};
// A page of the guide in Obsidian, at the heading the passage is under (Obsidian opens a heading, not a line)
export const obsidian = (vaultName, path, heading = "") => `obsidian://open?vault=${encodeURIComponent(vaultName || "")}&file=${
  encodeURIComponent(path.replace(/\.md$/, "") + (heading ? `#${heading.replace(/\[\[([^\]|]*\|)?([^\]]*)\]\]/g, "$2").replace(/[*_`]/g, "")}` : ""))}`;
// A text of the model with its Markdown links: a link is kept only to one of the lead's sources (https), the others
// stay text
export const linked = (text, sources) => {
  const known = new Set(sources.map(u => u.replace(/\/$/, ""))), out = [];
  let at = 0;
  for (const m of text.matchAll(/\[([^\]]+)\]\((https:\/\/[^)\s]+)\)/g)) {
    out.push(esc(text.slice(at, m.index)), known.has(m[2].replace(/\/$/, "")) ? extLink(m[2], esc(m[1])) : esc(m[1]));
    at = m.index + m[0].length;
  }
  return out.join("") + esc(text.slice(at));
};
// An address, short: its site and the end of its path (github.com › vllm/releases/tag/v0.34.0)
export const shortUrl = u => {
  try {
    const a = new URL(u), path = decodeURIComponent(a.pathname).replace(/\/$/, "");
    const tail = path.length > 42 ? `…${path.slice(-40)}` : path;
    return `${a.hostname.replace(/^www\./, "")}${tail ? ` › ${tail.replace(/^\//, "")}` : ""}`;
  } catch { return u; }
};
let BAR_ROOM = null;  // what keeps the page's room for the bar at its bottom as tall as the bar (ResizeObserver)
// A bar fixed at the bottom of a page (a check's, a review's, the retouches'): the page leaves room for it under its
// last line, as tall as it is now, so that nothing stays hidden behind it
export function keepRoomForBar() {
  BAR_ROOM?.disconnect();
  const bar = page.querySelector(".bar");
  document.body.style.paddingBottom = "";
  if (!bar) return;
  BAR_ROOM = new ResizeObserver(() => { document.body.style.paddingBottom = `${bar.offsetHeight}px`; });
  BAR_ROOM.observe(bar);
}
// Another screen: no room is kept for a bar until one is drawn again
export function forgetBar() { BAR_ROOM?.disconnect(); document.body.style.paddingBottom = ""; }
let followTimer = null;  // draws the screen shown again while something runs on it (a check, the sources, « To handle »)
export function followLater(f, ms) { followTimer = setTimeout(f, ms); }
export function stopFollowing() { clearTimeout(followTimer); }  // another screen opened
// A help bubble: a « ? » that says what the thing beside it is, on hover, on keyboard focus and on a tap
export const tip = text => `<button type="button" class="tip" data-tip="${esc(text)}" aria-label="${esc(text)}">?</button>`;
// The bubble stays inside the window: its width and its place follow where the « ? » is
const placeTip = e => {
  const t = e.target instanceof Element ? e.target.closest(".tip") : null;
  if (!t) return;
  const zoom = window.textZoom?.get() || 1, room = window.innerWidth / zoom, width = Math.min(360, room - 32);
  const left = t.getBoundingClientRect().left / zoom;
  t.style.setProperty("--tip-width", `${width}px`);
  t.style.setProperty("--tip-left", `${-8 - Math.max(0, left - 8 + width - (room - 16))}px`);
  t.classList.toggle("below", t.getBoundingClientRect().top / zoom < 170);
  // In the bar of a check, whose panel of options scrolls and would clip it: the bubble is placed on the screen
  if (t.closest(".check-bar")) {
    const r = t.getBoundingClientRect();
    t.classList.add("fixed");
    t.classList.remove("below");
    t.style.setProperty("--tip-fx", `${Math.max(8, Math.min(r.left / zoom - 8, room - width - 8))}px`);
    t.style.setProperty("--tip-fbottom", `${(window.innerHeight - r.top) / zoom + 8}px`);
  }
};
document.addEventListener("pointerover", placeTip);
document.addEventListener("focusin", placeTip);
