// @ts-check
/* vault-watch: the source beside its translation: at the pause of a « Sync the languages » run, the translation
   editable. The rows pair each passage of the source with its own translation (pairs.js). */

import { $, esc, page } from "./util.js";
import { api } from "./api.js";
import { T } from "./texts.js";
import { en } from "./explain.js";
import { wordDiff } from "./diff.js";
import { alignPairs } from "./pairs.js";
import { route } from "./router.js";

// --- The source beside its translation (graph.mirror keeps the pairs); editable at the pause of a sync ---------
const TRANSLATED = {};  // the translations retouched, by run and "<mirror page>#<n>", kept while the page is open

function pairsBlock(r, editable) {
  const P = T.pairs, mine = TRANSLATED[r.thread] ||= {};
  return `${r.mirror_pairs.filter(x => x.target.length || x.problem).map(x => {
    return `<div class="card pair-page"><div class="header"><code>${esc(x.page)}</code> → <code>${esc(x.mirror)}</code></div>
      ${x.problem ? `<p class="small attention-text">${P.problem}${T.colon}${en(x.problem)}</p>` : ""}
      ${alignPairs(x.source, x.target).map(({ source: src, target: tgt, t }) => {
        const key = `${x.mirror}#${t}`;  // the edit's own rank in the mirror's list: what the server retouches
        const [sb, sa] = src ? wordDiff(src[0], src[1]) : ["", ""];
        const text = mine[key] ?? tgt?.[1];
        const [tb, ta] = tgt ? wordDiff(tgt[0], text) : ["", ""];
        return `<div class="pair">
          <div><p class="muted small">${P.source}</p>${src ? `<div class="diff before" lang="fr">${sb}</div><div class="diff after" lang="fr">${sa || `<span class="muted">${P.removed}</span>`}</div>` : `<p class="muted small">—</p>`}</div>
          <div><p class="muted small">${P.target}${tgt?.[2] ? ` · <span class="badge ok">${P.retouched}</span>` : ""}</p>${tgt ? `<div class="diff before" lang="en">${tb}</div>
            <div class="diff after" lang="en" data-pair-after="${esc(key)}">${ta || `<span class="muted">${P.removed}</span>`}</div>
            ${editable && tgt[1].trim() ? `<span class="edit-label">${T.editable}</span><textarea class="editable" data-pair="${esc(key)}" lang="en" spellcheck="true">${esc(text)}</textarea>` : ""}` : `<p class="muted small">${P.none}</p>`}</div>
        </div>`;
      }).join("")}</div>`;
  }).join("")}`;
}

export function viewTranslation(r, title) {
  const P = T.pairs, mine = TRANSLATED[r.thread] ||= {};
  page.innerHTML = `${title}
    <h2>${P.title}</h2>
    <p class="muted small">${P.intro} ${P.edit}</p>
    ${pairsBlock(r, true)}
    <div class="bar"><button class="primary" id="ok"></button></div>`;
  const target = key => { const [page, n] = [key.slice(0, key.lastIndexOf("#")), Number(key.slice(key.lastIndexOf("#") + 1))];
    return r.mirror_pairs.find(x => x.mirror === page).target[n]; };
  const changed = () => Object.entries(mine).filter(([key, text]) => text !== target(key)[1]);
  const label = () => { $("#ok").textContent = P.ok(changed().length); };
  page.querySelectorAll("[data-pair]").forEach(t => {
    const fit = () => { t.style.height = "auto"; t.style.height = `${t.scrollHeight + 4}px`; };
    fit();
    t.oninput = () => {
      const key = t.dataset.pair, tgt = target(key);
      mine[key] = t.value;
      page.querySelector(`[data-pair-after="${CSS.escape(key)}"]`).innerHTML = wordDiff(tgt[0], t.value)[1];
      fit();
      label();
    };
  });
  label();
  $("#ok").onclick = async () => {
    $("#ok").disabled = true;
    await api(`/api/runs/${encodeURIComponent(r.thread)}/translation`, { edits: Object.fromEntries(changed()) });
    delete TRANSLATED[r.thread];
    route();
  };
}
