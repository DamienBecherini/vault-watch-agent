// @ts-check
/* vault-watch: « Costs »: what the calls of the model cost, by month and by run (metrics/usage.jsonl). */

import { dollars, esc, page } from "./util.js";
import { api } from "./api.js";
import { lang, T } from "./texts.js";

// --- Costs -------------------------------------------------------------------------------------------------
export async function viewCosts() {
  const c = await api("/api/costs");
  const number = n => n.toLocaleString(lang);
  // Calls made through Claude Code on a subscription cost nothing: their columns show up with the first of them
  const calls = c.month.reduce((s, r) => s + (r.subscription || 0), 0), spared = c.month.reduce((s, r) => s + (r.spared || 0), 0);
  const columns = [...T.columns, ...(calls ? T.subscriptionColumns : [])];
  const table = (rows, title) => `<table><thead><tr><th>${title}</th>${columns.map(x => `<th class="number">${x}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(r => `<tr><td>${esc(r.key)}</td><td class="number">${r.calls}</td><td class="number">${number(r.in)}</td><td class="number">${number(r.out)}</td><td class="number">${dollars(r.cost)}</td>${
      calls ? `<td class="number">${r.subscription || ""}</td><td class="number">${r.subscription ? dollars(r.spared) : ""}</td>` : ""}</tr>`).join("")}</tbody></table>`;
  const total = c.month.reduce((s, r) => s + r.cost, 0);
  page.innerHTML = `
    <h1>${T.costsTitle}</h1>
    <p class="subtitle">${T.costsIntro(dollars(total))}${calls ? ` ${T.costsSubscription(calls, dollars(spared))}` : ""}</p>
    ${Object.keys(c.origins || {}).length ? `<p class="muted small">${T.costsOrigins} ${Object.entries(c.origins)
      .map(([o, n]) => `${esc(T.priceOrigin(o))} (${n})`).join(" · ")}</p>` : ""}
    <h2>${T.byMonth}</h2><div class="card">${table(c.month, T.month)}</div>
    <h2>${T.byRun}</h2><div class="card">${table([...c.run].reverse(), T.run)}</div>`;
}
