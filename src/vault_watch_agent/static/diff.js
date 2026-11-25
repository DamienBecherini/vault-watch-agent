// @ts-check
/* vault-watch: what changed, as the screens of a run show it: word by word, or what is added after the text kept;
   and the passages of the guide a finding is about. */

import { esc, langOf, sourceLang } from "./util.js";
import { T } from "./texts.js";

// Word-level diff: words removed from `a` wrapped in <del>, words added to `b` in <ins>.
export function wordDiff(a, b) {
  const x = a.split(/(\s+)/), y = b.split(/(\s+)/);
  const n = x.length, m = y.length, L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  let i = 0, j = 0, before = "", after = "";
  while (i < n || j < m) {
    if (i < n && j < m && x[i] === y[j]) { before += esc(x[i]); after += esc(y[j]); i++; j++; }
    else if (j < m && (i === n || L[i][j + 1] >= L[i + 1][j])) { after += `<ins>${esc(y[j])}</ins>`; j++; }
    else { before += `<del>${esc(x[i])}</del>`; i++; }
  }
  return [before, after];
}

// The passages a finding is about, as the server found them in the page: never the model's own words
export function excerpts(list) {
  if (!list?.length) return "";
  const row = l => `<div${l.hit ? ' class="target"' : ""}><span class="n">${l.n}</span><span>${
    l.parts ? `${esc(l.parts[0])}<mark>${esc(l.parts[1])}</mark>${esc(l.parts[2])}` : esc(l.text)}</span></div>`;
  return `<div class="excerpts">${list.map(e => e.match === "missing"
    ? `<div class="excerpt muted small"><code>${esc(e.page)}</code> · ${T.excerptMissing}</div>`
    : `<div class="excerpt"><div class="muted small">${T.excerptNow} · <code>${esc(e.page)}:${e.line}</code>${e.match === "approx" ? ` · ${T.excerptApprox}` : ""}</div>
        <div class="lines" lang="${langOf(e.page)}">${e.lines.map(row).join("")}</div></div>`).join("")}</div>`;
}

// A change, as the review shows it: what is added after the text kept, when it only adds (a sentence after a
// paragraph, a footnote after another); else the text before and after, word by word. `lang`: the page's language
export const changeView = (current, text, lang = sourceLang()) => {
  if (current && text.length > current.length && text.startsWith(current)) {
    const added = text.slice(current.length).replace(/^\n+/, "");
    const notes = added.split("\n").filter(l => l.trim()).every(l => /^\[\^[^\]]+\]:/.test(l));
    const tail = current.length > 110 ? `…${current.slice(-100).trimStart()}` : current;
    return `<p class="anchor muted small">${T.addedAfter} « ${esc(tail)} »</p>
      <div class="diff after${notes ? " notes" : ""}" lang="${lang}">${notes ? `<span class="muted">${T.notesAdded}</span>` : ""}${esc(added)}</div>`;
  }
  const [before, after] = wordDiff(current, text);
  return `<div class="diff before" lang="${lang}">${before}</div>
    <div class="diff after" lang="${lang}">${after || `<span class="muted">${T.removedWhole}</span>`}</div>`;
};
