// @ts-check
/* vault-watch: the calls of the server's API, and what the server says of itself and of its guide (/api/info): its
   forge, its engine (the costs shown follow it). */

import { T } from "./texts.js";

// Every call of the API says it comes from this page (X-Vault-Watch, a GET included: the server refuses the others)
export async function api(path, body) {
  const opts = body === undefined ? { headers: { "X-Vault-Watch": "1" } } : {
    method: "POST", body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-Vault-Watch": "1" },
  };
  const r = await fetch(path, opts).catch(() => { throw new Error(T.serverDown); });  // stopped (idle, closed)
  checkPage(r);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r.text();
}

// The version of the page as served (web.index), and the one the server says in each answer of the API: different,
// the server was updated since this page was opened, and its old scripts may not show what the server sends now
const served = /** @type {HTMLMetaElement | null} */ (document.querySelector('meta[name="vault-watch-page"]'))?.content;
/** @param {Response} r */
export function checkPage(r) {
  const now = r.headers.get("X-Vault-Watch-Page");
  if (!served || !now || now === served || document.querySelector("#stale-page")) return;
  const div = document.createElement("p");
  div.id = "stale-page";
  div.className = "banner";
  div.textContent = `${T.pageStale} `;
  const b = document.createElement("button");
  b.type = "button";
  b.className = "small-button";
  b.textContent = T.reload;
  b.onclick = () => location.reload();
  div.append(b);
  document.querySelector("#page")?.before(div);
}

export let info = null;  // what the server says of itself and of its guide (/api/info), a moment after the page opens
export function setInfo(i) { info = i; }
export const forgeName = () => info?.forge || "GitHub";  // where the pull requests are merged
// What a paid action costs: its estimate on the API, nothing on Claude Code with a subscription (info.engine)
export const onSubscription = () => info?.engine === "claude-code";
