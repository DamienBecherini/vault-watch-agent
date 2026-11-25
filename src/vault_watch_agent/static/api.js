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
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r.text();
}

export let info = null;  // what the server says of itself and of its guide (/api/info), a moment after the page opens
export function setInfo(i) { info = i; }
export const forgeName = () => info?.forge || "GitHub";  // where the pull requests are merged
// What a paid action costs: its estimate on the API, nothing on Claude Code with a subscription (info.engine)
export const onSubscription = () => info?.engine === "claude-code";
