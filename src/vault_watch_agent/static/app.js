/* vault-watch: one screen per pause of the graph. Routes: #/ (watches), #/run/<thread>, #/signaler, #/couts.
   The server holds every state (checkpoints); this page only shows it and sends the human's answers. */

const $ = s => document.querySelector(s);
const page = $("#page");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const dollars = n => `${(n ?? 0).toFixed(2)} $`;
let source = null;  // EventSource of the run being followed

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-Vault-Watch": "1" },
  };
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r.text();
}

const STATUTS = {
  new: ["À analyser", "neutre"], running: ["En cours", "attention"], review: ["Relecture à faire", "attention"],
  publish: ["Publication à valider", "attention"], published: ["PR créée", "ok"],
  "nothing-applied": ["Rien appliqué", "neutre"], "not-published": ["Non publié", "neutre"], stopped: ["Interrompu", "erreur"],
  closed: ["Traitée hors agent", "neutre"], merged: ["✓ Terminée · PR fusionnée", "ok"],
  "pr-open": ["PR à fusionner", "attention"], "pr-closed": ["PR fermée sans fusion", "neutre"],
};
// Nothing left to do: the card is dimmed
const FINIS = ["closed", "merged", "pr-closed", "nothing-applied", "not-published"];
const pastille = st => { const [t, c] = STATUTS[st] || [st, "neutre"]; return `<span class="pastille ${c}">${t}</span>`; };

const NOMS = {
  collect: "Récupération de la veille", triage: "Tri des éléments", locate: "Recherche des pages concernées",
  propose: "Propositions de corrections", number: "Numérotation et contrôle des citations",
  crosscheck: "Relecture avec tout le guide et le web", report: "Rapport", review: "Ta relecture",
  apply: "Application sur une branche", mirror: "Traduction anglaise", audits: "Contrôles du guide (npm test)",
  links: "Vérification des liens", publish: "Push et pull request",
};

// --- Router --------------------------------------------------------------------------------------
async function route() {
  if (source) { source.close(); source = null; }
  const h = location.hash.slice(1) || "/";
  document.querySelectorAll("nav a").forEach(a =>
    a.classList.toggle("actif", h === "/" ? a.dataset.nav === "veilles" : h.startsWith(`/${a.dataset.nav}`)));
  page.innerHTML = `<p class="doux">Chargement…</p>`;
  try {
    if (h.startsWith("/run/")) await vueRun(decodeURIComponent(h.slice(5)));
    else if (h === "/signaler") vueSignaler();
    else if (h === "/couts") await vueCouts();
    else await vueVeilles();
  } catch (e) {
    page.innerHTML = `<p class="erreur-texte">${esc(e.message)}</p>`;
  }
}
addEventListener("hashchange", route);

// --- Watches ---------------------------------------------------------------------------------------
async function vueVeilles() {
  const [veilles, runs] = await Promise.all([api("/api/veilles"), api("/api/runs")]);
  const autres = runs;
  page.innerHTML = `
    <h1>Veilles</h1>
    <p class="sous-titre">Une veille est publiée par GitHub tous les 15 jours. L'agent l'analyse, tu relis ses propositions, puis il ouvre la pull request.</p>
    ${veilles.map(v => {
      const r = v.run, lien = `#/run/${encodeURIComponent(r.thread)}`;
      const action = r.status === "closed" ? ""
        : r.status === "new" ? `<button class="principal" data-analyser="${v.number}">Analyser · ≈ 4 $</button>`
        : r.status === "pr-open" ? `<a href="${esc(r.pr_url)}" target="_blank" rel="noopener"><button class="principal">Fusionner sur GitHub</button></a>`
        : `<a href="${lien}"><button${["review", "publish", "stopped"].includes(r.status) ? ' class="principal"' : ""}>${
            { review: "Relire", publish: "Valider la publication", running: "Suivre", stopped: "Reprendre" }[r.status] || "Détails"}</button></a>`;
      return `<div class="carte ligne${FINIS.includes(r.status) ? " finie" : ""}">
        <div class="pousse">
          <b>#${v.number}</b> ${esc(v.title)} ${v.urgent ? `<span class="pastille ${FINIS.includes(r.status) ? "neutre" : "erreur"}">urgent</span>` : ""}
          <div class="doux petit">${v.date} · issue ${v.state === "open" ? "ouverte" : "fermée"}${
            !["new", "closed"].includes(r.status) ? ` · ${r.corrections} correction(s), ${r.applied} appliquée(s) · ${dollars(r.cost)}` : ""}${
            r.pr_url ? ` · <a href="${esc(r.pr_url)}" target="_blank" rel="noopener">pull request</a>` : ""}</div>
        </div>
        ${pastille(r.status)} ${action}
      </div>`;
    }).join("") || `<p class="doux">Aucune veille.</p>`}
    ${autres.length ? `<h2>Autres passages</h2>${autres.map(r => `
      <div class="carte ligne${FINIS.includes(r.status) ? " finie" : ""}"><div class="pousse"><b>${esc(r.thread)}</b>
        <div class="doux petit">${esc(r.source)} · ${r.corrections} correction(s) · ${dollars(r.cost)}${
          r.pr_url ? ` · <a href="${esc(r.pr_url)}" target="_blank" rel="noopener">pull request</a>` : ""}</div></div>
        ${pastille(r.status)} <a href="#/run/${encodeURIComponent(r.thread)}"><button>Détails</button></a></div>`).join("")}` : ""}`;
  page.querySelectorAll("[data-analyser]").forEach(b => b.onclick = async () => {
    b.disabled = true;
    const { thread } = await api("/api/analyses", { issue: Number(b.dataset.analyser) });
    location.hash = `/run/${encodeURIComponent(thread)}`;
  });
}

// --- One run ---------------------------------------------------------------------------------------
async function vueRun(thread) {
  const r = await api(`/api/runs/${encodeURIComponent(thread)}`);
  const titre = `<h1>${esc(r.source || thread)} ${pastille(r.status)}</h1>
    <p class="sous-titre">${r.as_of ? `Veille jusqu'au ${r.as_of} · ` : ""}${esc(r.usage)}</p>`;
  if (r.status === "running") return vueEnCours(r, titre);
  if (r.status === "review") return vueRelecture(r, titre);
  if (r.status === "publish") return vuePublication(r, titre);
  vueFin(r, titre);
}

function vueEnCours(r, titre) {
  const faits = new Set(r.job.events.map(e => e.node));
  const debut = r.job.action === "fix" ? "propose" : { run: "collect", review: "apply", publish: "publish", resume: null }[r.job.action];
  const etapes = r.steps.slice(debut ? r.steps.indexOf(debut) : 0);
  const cout = r.job.events.reduce((m, e) => e.cost ?? m, 0);
  page.innerHTML = `${titre}
    <div class="carte">
      <ol class="etapes" id="etapes">${etapes.map(s => `<li data-etape="${s}">${NOMS[s]}</li>`).join("")}</ol>
      <p class="doux petit" id="avancement"></p>
    </div>
    <p class="doux petit">Tu peux fermer la page : l'analyse continue sur le serveur, et l'état est enregistré à chaque étape.</p>`;
  const maj = (cout) => {
    let encours = true;
    page.querySelectorAll("#etapes li").forEach(li => {
      const fait = faits.has(li.dataset.etape);
      li.classList.toggle("fait", fait);
      li.classList.toggle("encours", !fait && encours && (encours = false, true));
    });
    const min = Math.round((Date.now() / 1000 - r.job.started) / 60);
    $("#avancement").textContent = `Démarré il y a ${min} min · coût de ce passage ≈ ${dollars(cout)}`;
  };
  maj(cout);
  source = new EventSource(`/api/runs/${encodeURIComponent(r.thread)}/events`);
  source.onmessage = ev => { const e = JSON.parse(ev.data); faits.add(e.node); maj(e.cost ?? cout); };
  source.addEventListener("end", () => { source.close(); source = null; route(); });
}

// Word-level diff: words removed from `a` wrapped in <del>, words added to `b` in <ins>.
function diffMots(a, b) {
  const x = a.split(/(\s+)/), y = b.split(/(\s+)/);
  const n = x.length, m = y.length, L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  let i = 0, j = 0, av = "", ap = "";
  while (i < n || j < m) {
    if (i < n && j < m && x[i] === y[j]) { av += esc(x[i]); ap += esc(y[j]); i++; j++; }
    else if (j < m && (i === n || L[i][j + 1] >= L[i + 1][j])) { ap += `<ins>${esc(y[j])}</ins>`; j++; }
    else { av += `<del>${esc(x[i])}</del>`; i++; }
  }
  return [av, ap];
}

function carteCorrection(c, r) {
  const valide = c.check === "ok";
  const [av, ap] = diffMots(c.current, c.proposed);
  const sources = (c.item_ids || [c.item_id]).map(id => r.items[id]).filter(Boolean)
    .map(i => i.url ? `<a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title)}</a>` : esc(i.title)).join(" · ");
  return `<div class="carte correction${valide ? "" : " refusee"}">
    <input type="checkbox" data-id="${c.id}" data-groupe="${c.group}" ${valide ? "checked" : "disabled"} aria-label="Appliquer ${c.id}">
    <div>
      <div class="entete"><b>${c.id}</b><span class="pastille ${c.severity}">${c.severity}</span><code>${esc(c.page)}</code>
        ${valide ? "" : `<span class="pastille erreur">${esc(c.check)}</span>`}</div>
      <p>${esc(c.rationale)}</p>
      ${c.review ? `<p class="doux petit">Relecture globale : ${esc(c.review)}</p>` : ""}
      <div class="diff avant">${av}</div>
      <div class="diff apres">${ap}</div>
      <div class="doux petit">D'après ${sources || "—"}${c.source_url ? ` · <a href="${esc(c.source_url)}" target="_blank" rel="noopener">source</a>` : ""}</div>
    </div>
  </div>`;
}

function vueRelecture(r, titre) {
  const num = id => Number(id.slice(1));
  const groupes = {};
  for (const c of [...r.corrections].sort((a, b) => num(a.group) - num(b.group) || num(a.id) - num(b.id)))
    (groupes[c.group] ||= []).push(c);
  const casses = new Set(r.corrections.filter(c => c.check !== "ok").map(c => c.group));
  page.innerHTML = `${titre}
    <div class="chiffres">
      <div><b>${Object.values(r.triage).reduce((a, b) => a + b, 0)}</b>éléments de veille</div>
      <div><b>${r.triage.correct}</b>touchent une page</div>
      <div><b>${r.corrections.length}</b>corrections proposées</div>
      <div><b>${r.additions.length}</b>pistes d'ajout</div>
    </div>
    <h2>Corrections</h2>
    <p class="doux petit">Coche ce qui doit être appliqué. Les corrections liées (une phrase et sa note, par exemple) forment un groupe : elles se cochent ensemble. Un groupe dont un membre ne peut pas s'appliquer est écarté en entier.</p>
    ${Object.entries(groupes).map(([g, cs]) => cs.length > 1
      ? `<div class="groupe"><p class="doux petit">Groupe ${g}${casses.has(g) ? " · écarté : un membre ne s'applique pas" : ""}</p>${cs.map(c => carteCorrection(c, r)).join("")}</div>`
      : carteCorrection(cs[0], r)).join("") || `<p class="doux">Aucune correction proposée.</p>`}
    <details><summary>Pistes d'ajout (${r.additions.length}, non rédigées)</summary>
      <ul>${r.additions.map(a => `<li>${a.url ? `<a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)}</a>` : esc(a.title)} : ${esc(a.reason)}</li>`).join("") || "<li>Aucune.</li>"}</ul></details>
    <details><summary>Remarqué ailleurs dans le guide (${r.findings.length})</summary>
      <ul>${r.findings.map(f => `<li>${esc(f)}</li>`).join("") || "<li>Rien.</li>"}</ul>
      ${r.findings.length ? `<p class="doux petit">Pour les corriger : « Signaler une erreur », en copiant les lignes utiles.</p>` : ""}</details>
    <details><summary>Affirmations à revérifier (${r.claims_due.length})</summary>
      <ul>${r.claims_due.map(c => `<li>${esc(c.recheckBy)} <code>${esc(c.page)}</code> : ${esc(c.claim)}</li>`).join("") || "<li>Aucune.</li>"}</ul></details>
    <p class="petit"><a href="/api/runs/${encodeURIComponent(r.thread)}/rapport" target="_blank">Rapport complet (Markdown)</a></p>
    <div class="barre">
      <button id="rien">Ne rien appliquer</button>
      <button class="principal" id="appliquer"></button>
    </div>`;
  const cases = [...page.querySelectorAll(".correction input")];
  cases.filter(i => casses.has(i.dataset.groupe)).forEach(i => { i.checked = false; i.disabled = true; });
  const compte = () => {
    const n = cases.filter(i => i.checked).length;
    $("#appliquer").textContent = `Appliquer ${n} correction${n > 1 ? "s" : ""}`;
    $("#appliquer").disabled = n === 0;
  };
  cases.forEach(i => i.onchange = () => {
    cases.filter(o => o.dataset.groupe === i.dataset.groupe && !o.disabled).forEach(o => o.checked = i.checked);
    compte();
  });
  compte();
  const envoyer = async accept => {
    page.querySelectorAll(".barre button").forEach(b => b.disabled = true);
    await api(`/api/runs/${encodeURIComponent(r.thread)}/review`, { accept });
    route();
  };
  $("#appliquer").onclick = () => envoyer(cases.filter(i => i.checked).map(i => i.dataset.id));
  $("#rien").onclick = () => confirm("Ne rien appliquer et clore ce passage ?") && envoyer("none");
}

async function vuePublication(r, titre) {
  const p = { mirror_problems: [], link_problems: [], ...r.pause };
  const diff = await api(`/api/runs/${encodeURIComponent(r.thread)}/diff`).catch(() => "");
  const couleur = l => l.startsWith("+") && !l.startsWith("+++") ? "plus" : l.startsWith("-") && !l.startsWith("---") ? "moins" : "";
  page.innerHTML = `${titre}
    <div class="chiffres">
      <div><b>${r.applied.length}</b>corrections appliquées</div>
      <div><b>${r.mirrored.length}</b>pages anglaises mises à jour</div>
      <div><b>${p.audit_ok ? "OK" : "Échec"}</b>contrôles du guide</div>
      <div><b>${p.link_problems.length}</b>lien(s) à vérifier</div>
    </div>
    <div class="carte">
      <p>Branche <code>${esc(p.branch)}</code>, prête localement. Rien n'a encore quitté la machine.</p>
      ${p.audit_ok ? "" : `<p class="erreur-texte">Les contrôles du guide échouent : la PR serait rouge.</p><pre>${esc(r.audit_log)}</pre>`}
      ${p.mirror_problems.length ? `<p><b>Traduction</b></p><ul>${p.mirror_problems.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${p.link_problems.length ? `<p><b>Liens</b> (« NEW » : ajouté par ce passage)</p><ul>${p.link_problems.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="doux">Toutes les sources des pages modifiées répondent.</p>`}
    </div>
    <details open><summary>Modifications</summary>
      <pre>${diff.split("\n").map(l => `<span class="${couleur(l)}">${esc(l)}</span>`).join("\n") || esc(p.diffstat)}</pre></details>
    <div class="barre">
      <button id="non">Ne pas publier</button>
      <button class="principal" id="oui">Pousser et ouvrir la pull request</button>
    </div>`;
  const envoyer = async go => {
    page.querySelectorAll(".barre button").forEach(b => b.disabled = true);
    await api(`/api/runs/${encodeURIComponent(r.thread)}/publish`, { go });
    route();
  };
  $("#oui").onclick = () => envoyer(true);
  $("#non").onclick = () => confirm("Garder la branche en local sans pull request ?") && envoyer(false);
}

function vueFin(r, titre) {
  const texte = {
    published: `Pull request : <a href="${esc(r.pr_url)}" target="_blank" rel="noopener">${esc(r.pr_url)}</a>. Une fois relue et fusionnée sur GitHub, le site se redéploie tout seul.`,
    "pr-open": `Pull request à relire et fusionner sur GitHub : <a href="${esc(r.pr_url)}" target="_blank" rel="noopener">${esc(r.pr_url)}</a>. Le site se redéploie tout seul après la fusion.`,
    merged: `Terminé : la <a href="${esc(r.pr_url)}" target="_blank" rel="noopener">pull request</a> est fusionnée et le site redéployé.`,
    "pr-closed": `La <a href="${esc(r.pr_url)}" target="_blank" rel="noopener">pull request</a> a été fermée sans fusion.`,
    "nothing-applied": "Aucune correction appliquée : le passage est clos.",
    "not-published": `Branche <code>${esc(r.branch)}</code> gardée en local, sans pull request.`,
    stopped: "Le passage s'est arrêté sur une erreur. Il peut reprendre à la dernière étape terminée.",
    new: "Ce passage n'a pas commencé.",
  }[r.status] || "";
  page.innerHTML = `${titre}
    <div class="carte"><p>${texte}</p>
      ${r.error ? `<p class="erreur-texte">${esc(r.error)}</p>` : ""}
      ${r.status === "stopped" ? `<button class="principal" id="reprendre">Reprendre</button>` : ""}</div>
    ${r.applied.length ? `<p>Appliquées : ${r.applied.join(", ")}</p>` : ""}
    ${r.report_path ? `<p class="petit"><a href="/api/runs/${encodeURIComponent(r.thread)}/rapport" target="_blank">Rapport complet (Markdown)</a></p>` : ""}`;
  const b = $("#reprendre");
  if (b) b.onclick = async () => { b.disabled = true; await api(`/api/runs/${encodeURIComponent(r.thread)}/resume`, {}); route(); };
}

// --- Report errors -----------------------------------------------------------------------------------
function vueSignaler() {
  page.innerHTML = `
    <h1>Signaler une erreur</h1>
    <p class="sous-titre">Une erreur par ligne : la page, ce qui est faux, et si possible la bonne information. L'agent vérifie chaque point sur des sources primaires, avec tout le guide en contexte, puis propose des corrections que tu relis comme pour une veille. Compte 5 à 7 $.</p>
    <textarea id="texte" placeholder="03-stack/engines.md : vLLM 0.31 n'est plus la version minimale, la 0.33 corrige un avis de sécurité."></textarea>
    <p><button class="principal" id="envoyer">Vérifier et proposer des corrections</button></p>`;
  $("#envoyer").onclick = async () => {
    const text = $("#texte").value.trim();
    if (!text) return;
    $("#envoyer").disabled = true;
    const { thread } = await api("/api/fix", { text });
    location.hash = `/run/${encodeURIComponent(thread)}`;
  };
}

// --- Costs -------------------------------------------------------------------------------------------------
async function vueCouts() {
  const c = await api("/api/couts");
  const tableau = (rows, titre) => `<table><thead><tr><th>${titre}</th><th class="nombre">Appels</th><th class="nombre">Tokens lus</th><th class="nombre">Écrits</th><th class="nombre">Coût</th></tr></thead>
    <tbody>${rows.map(r => `<tr><td>${esc(r.key)}</td><td class="nombre">${r.calls}</td><td class="nombre">${r.in.toLocaleString("fr")}</td><td class="nombre">${r.out.toLocaleString("fr")}</td><td class="nombre">${dollars(r.cost)}</td></tr>`).join("")}</tbody></table>`;
  const total = c.month.reduce((s, r) => s + r.cost, 0);
  page.innerHTML = `
    <h1>Coûts</h1>
    <p class="sous-titre">Calculés à partir de l'usage que renvoie l'API, au prix catalogue (journal <code>metrics/usage.jsonl</code>). La page de facturation de la Console reste la référence. Total : ${dollars(total)}.</p>
    <h2>Par mois</h2><div class="carte">${tableau(c.month, "Mois")}</div>
    <h2>Par passage</h2><div class="carte">${tableau([...c.run].reverse(), "Passage")}</div>`;
}

// Header links: the guide, its repository, this agent's repository
api("/api/infos").then(i => {
  $("#externes").innerHTML = [[i.site, "Guide"], [`https://github.com/${i.repo}`, "Dépôt du guide"], [i.agent, "Code de l'agent"]]
    .filter(([url]) => url).map(([url, nom]) => `<a href="${esc(url)}" target="_blank" rel="noopener">${nom} ↗</a>`).join("");
}).catch(() => {});

route();
