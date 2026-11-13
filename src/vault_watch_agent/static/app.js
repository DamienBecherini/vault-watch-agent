/* vault-watch: one screen per pause of the graph. Routes: #/ (watches), #/run/<thread>, #/check, #/check/<id>, #/report, #/costs.
   The server holds every state (checkpoints); this page only shows it and sends the human's answers.
   Interface in French or English (toggle in the header, remembered); the guide's own text stays in French. */

const $ = s => document.querySelector(s);
const page = $("#page");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const dollars = n => `${(n ?? 0).toFixed(2)} $`;
const extLink = (url, text) => `<a href="${esc(url)}" target="_blank" rel="noopener">${text}</a>`;
let source = null;  // EventSource of the run being followed

// --- Languages ---------------------------------------------------------------------------------------
const TEXTS = {
  fr: {
    nav: { watches: "Veilles", check: "Vérifier le guide", report: "Signaler une erreur", costs: "Coûts" },
    links: ["Guide", "Dépôt du guide", "Code de l'agent"],
    verif: {
      title: "Vérifier le guide",
      intro: "Un bilan de santé du guide entier, à la demande. Les contrôles gratuits utilisent les scripts du guide ; les autres font lire le guide par Claude. Les résultats sont des pistes : celles que tu gardes partent dans une passe fix, qui les vérifie sur les sources et passe par ta relecture.",
      free: "gratuit", tokens: n => `≈ ${n.toLocaleString("fr")} tokens`, unknown: "selon le résultat",
      needs: ids => `lance aussi : ${ids}`,
      start: usd => `Lancer la vérification · ≈ ${usd}`, history: "Vérifications précédentes",
      none: "Aucune vérification pour l'instant.", running: "En cours…", leads: n => `${n} piste(s)`,
      waiting: "en attente", ok: "RAS", problems: "à regarder", failed: "n'a pas pu tourner",
      notFixable: "Pas encore corrigeable par une passe fix (les traductions se corrigent depuis le français) : à reprendre à la main ou par une prochaine fonction.",
      seeDetails: "Détails", dead: "Sources qui ne répondent pas", blocked: "Bloquées par une protection anti-robots (souvent normales dans un navigateur)",
      claims: "Affirmations à revérifier", pagesDue: "Pages à revoir", log: "Journal",
      createFix: (n, t) => t === n && n ? `Créer une passe traduction avec ${n} piste(s) · < 1 $`
        : t ? `Créer 2 passes : ${n - t} piste(s) en fix (≈ 6-8 $), ${t} en traduction (< 1 $)`
        : `Créer une passe fix avec ${n} piste(s) · ≈ 6-8 $`, tickAll: "Tout cocher", untickAll: "Tout décocher",
      cost: c => `Coût : ${c}`,
      counts: c => c.open + c.fix + c.dismissed === 0 ? "aucune piste"
        : `${c.open} à traiter · ${c.fix} envoyée(s) en passe fix · ${c.dismissed} écartée(s)`,
      toHandle: n => `${n} piste(s) à traiter`, handled: "Traitée", handle: "Traiter",
      tickCard: n => `Cocher / décocher les ${n}`,
      toHandleTitle: "À traiter", newCheck: "Nouvelle vérification", fixRuns: "Passes fix lancées depuis cette vérification",
      warning: n => `Il reste ${n} piste(s) à traiter ci-dessus. Une nouvelle vérification les retrouverait, en double : traite-les ou écarte-les d'abord.`,
      sent: "→ passe fix", dismissed: "écartée", reopen: "Rétablir", dismiss: n => `Écarter ${n} piste(s)`,
    },
    loading: "Chargement…",
    serverDown: "Le serveur ne répond pas : il s'arrête après 1 h d'inactivité. Relance-le (Nouvel onglet, module « Veille du guide IA »), puis recharge la page. Les passages en pause n'ont rien perdu.",
    statuses: {
      new: "À analyser", running: "En cours", review: "Relecture à faire", publish: "Publication à valider",
      published: "PR créée", "nothing-applied": "Rien appliqué", "not-published": "Non publié", stopped: "Interrompu",
      closed: "Traitée hors agent", merged: "✓ Terminée · PR fusionnée", "pr-open": "PR à fusionner",
      "pr-closed": "PR fermée sans fusion",
    },
    steps: {
      collect: "Récupération de la veille", triage: "Tri des éléments", locate: "Recherche des pages concernées",
      propose: "Propositions de corrections", number: "Numérotation et contrôle des citations",
      crosscheck: "Relecture avec tout le guide et le web", report: "Rapport", review: "Ta relecture",
      apply: "Application sur une branche", mirror: "Traduction anglaise", audits: "Contrôles du guide (npm test)",
      links: "Vérification des liens", publish: "Push et pull request",
    },
    watches: "Veilles",
    watchesIntro: "Une veille est publiée par GitHub tous les 15 jours. L'agent l'analyse, tu relis ses propositions, puis il ouvre la pull request.",
    analyse: "Analyser · ≈ 4 $", merge: "Fusionner sur GitHub",
    buttons: { review: "Relire", publish: "Valider la publication", running: "Suivre", stopped: "Reprendre" },
    details: "Détails",
    issue: open => `issue ${open ? "ouverte" : "fermée"}`,
    count: (n, a) => `${n} correction(s), ${a} appliquée(s)`,
    noWatch: "Aucune veille.", others: "Autres passages",
    watchUpTo: d => `Veille jusqu'au ${d}`,
    canClose: "Tu peux fermer la page : l'analyse continue sur le serveur, et l'état est enregistré à chaque étape.",
    progress: (min, cost) => `Démarré il y a ${min} min · coût de ce passage ≈ ${cost}`,
    applyId: id => `Appliquer ${id}`,
    crossCheck: "Relecture globale", from: "D'après",
    sourceMissing: "Source à vérifier", leftovers: n => `Valeurs retirées encore présentes, laissées telles quelles (${n})`,
    reviewFigures: ["éléments de veille", "touchent une page", "corrections proposées", "pistes d'ajout"],
    corrections: "Corrections",
    reviewHelp: "Coche ce qui doit être appliqué. Les corrections liées (une phrase et sa note, par exemple) forment un groupe : elles se cochent ensemble. Un groupe dont un membre ne peut pas s'appliquer est écarté en entier.",
    group: g => `Groupe ${g}`, groupLeftOut: " · écarté : un membre ne s'applique pas",
    noCorrection: "Aucune correction proposée.",
    leads: n => `Pistes d'ajout (${n}, non rédigées)`, none: "Aucune.", nothing: "Rien.",
    noticed: n => `Remarqué ailleurs dans le guide (${n})`,
    noticedHelp: "Pour les corriger : « Signaler une erreur », en copiant les lignes utiles.",
    excerptMissing: "extrait introuvable dans la page", excerptApprox: "passage le plus proche, pas une citation exacte",
    claims: n => `Affirmations à revérifier (${n})`,
    report: "Rapport complet (Markdown)",
    applyNothing: "Ne rien appliquer", applyN: n => `Appliquer ${n} correction${n > 1 ? "s" : ""}`,
    confirmNothing: "Ne rien appliquer et clore ce passage ?",
    publishFigures: ["corrections appliquées", "pages anglaises mises à jour", "contrôles du guide", "lien(s) à vérifier"],
    failed: "Échec",
    branchReady: b => `Branche <code>${b}</code>, prête localement. Rien n'a encore quitté la machine.`,
    auditsRed: "Les contrôles du guide échouent : la PR serait rouge.",
    translation: "Traduction", linksTitle: "Liens", linksNew: "(« NEW » : ajouté par ce passage)",
    linksOk: "Toutes les sources des pages modifiées répondent.",
    changes: "Modifications", doNotPublish: "Ne pas publier", publish: "Pousser et ouvrir la pull request",
    confirmNo: "Garder la branche en local sans pull request ?",
    end: {
      published: pr => `Pull request : ${pr}. Une fois relue et fusionnée sur GitHub, le site se redéploie tout seul.`,
      "pr-open": pr => `Pull request à relire et fusionner sur GitHub : ${pr}. Le site se redéploie tout seul après la fusion.`,
      merged: pr => `Terminé : la ${pr} est fusionnée et le site redéployé.`,
      "pr-closed": pr => `La ${pr} a été fermée sans fusion.`,
      "nothing-applied": () => "Aucune correction appliquée : le passage est clos.",
      "not-published": (pr, b) => `Branche <code>${b}</code> gardée en local, sans pull request.`,
      stopped: () => "Le passage s'est arrêté sur une erreur. Il peut reprendre à la dernière étape terminée.",
      new: () => "Ce passage n'a pas commencé.",
    },
    resume: "Reprendre", applied: "Appliquées",
    reportTitle: "Signaler une erreur",
    reportIntro: "Une erreur par ligne : la page, ce qui est faux, et si possible la bonne information. L'agent vérifie chaque point sur des sources primaires, avec tout le guide en contexte, puis propose des corrections que tu relis comme pour une veille. Compte 5 à 7 $.",
    reportExample: "03-stack/engines.md : vLLM 0.31 n'est plus la version minimale, la 0.33 corrige un avis de sécurité.",
    reportButton: "Vérifier et proposer des corrections",
    costsTitle: "Coûts",
    costsIntro: total => `Calculés à partir de l'usage que renvoie l'API, au prix catalogue (journal <code>metrics/usage.jsonl</code>). La page de facturation de la Console reste la référence. Total : ${total}.`,
    columns: ["Appels", "Tokens lus", "Écrits", "Coût"], byMonth: "Par mois", month: "Mois", byRun: "Par passage", run: "Passage",
  },
  en: {
    nav: { watches: "Watches", check: "Check the guide", report: "Report an error", costs: "Costs" },
    links: ["Guide", "Guide repository", "Agent code"],
    verif: {
      title: "Check the guide",
      intro: "A health check of the whole guide, on demand. The free checks run the guide's own scripts; the others have Claude read the guide. Results are leads: the ones you keep go to a fix run, which checks them on sources and goes through your review.",
      free: "free", tokens: n => `≈ ${n.toLocaleString("en")} tokens`, unknown: "depends on the result",
      needs: ids => `also runs: ${ids}`,
      start: usd => `Run the check · ≈ ${usd}`, history: "Previous checks",
      none: "No check yet.", running: "Running…", leads: n => `${n} lead(s)`,
      waiting: "waiting", ok: "all clear", problems: "to look at", failed: "could not run",
      notFixable: "Not fixable by a fix run yet (translations are fixed from the French side): to handle by hand or by a later feature.",
      seeDetails: "Details", dead: "Sources not answering", blocked: "Blocked by anti-bot protections (often fine in a browser)",
      claims: "Claims to re-check", pagesDue: "Pages due for review", log: "Log",
      createFix: (n, t) => t === n && n ? `Create a translation run with ${n} point(s) · < 1 $`
        : t ? `Create 2 runs: ${n - t} point(s) as a fix (≈ 6-8 $), ${t} as a translation run (< 1 $)`
        : `Create a fix run with ${n} point(s) · ≈ 6-8 $`, tickAll: "Tick all", untickAll: "Untick all",
      cost: c => `Cost: ${c}`,
      counts: c => c.open + c.fix + c.dismissed === 0 ? "no lead"
        : `${c.open} to handle · ${c.fix} sent to a fix run · ${c.dismissed} dismissed`,
      toHandle: n => `${n} lead(s) to handle`, handled: "Handled", handle: "Handle",
      tickCard: n => `Tick / untick the ${n}`,
      toHandleTitle: "To handle", newCheck: "New check", fixRuns: "Fix runs started from this check",
      warning: n => `${n} lead(s) above are still to handle. A new check would find them again, twice: handle or dismiss them first.`,
      sent: "→ fix run", dismissed: "dismissed", reopen: "Reopen", dismiss: n => `Dismiss ${n} lead(s)`,
    },
    loading: "Loading…",
    serverDown: "The server does not answer: it may have stopped after being idle (`serve --idle-exit`). Start it again, then reload the page. Paused runs lost nothing.",
    statuses: {
      new: "To analyse", running: "Running", review: "Review pending", publish: "Publish pending",
      published: "PR opened", "nothing-applied": "Nothing applied", "not-published": "Not published", stopped: "Stopped",
      closed: "Handled without the agent", merged: "✓ Done · PR merged", "pr-open": "PR to merge",
      "pr-closed": "PR closed unmerged",
    },
    steps: {
      collect: "Download the watch", triage: "Triage the items", locate: "Find the pages concerned",
      propose: "Propose corrections", number: "Number them, check the quotes",
      crosscheck: "Cross-check with the whole guide and the web", report: "Report", review: "Your review",
      apply: "Apply on a branch", mirror: "English translation", audits: "Guide audits (npm test)",
      links: "Link checks", publish: "Push and pull request",
    },
    watches: "Watches",
    watchesIntro: "GitHub publishes a watch every two weeks. The agent analyses it, you review its proposals, then it opens the pull request.",
    analyse: "Analyse · ≈ 4 $", merge: "Merge on GitHub",
    buttons: { review: "Review", publish: "Approve publishing", running: "Follow", stopped: "Resume" },
    details: "Details",
    issue: open => `issue ${open ? "open" : "closed"}`,
    count: (n, a) => `${n} correction(s), ${a} applied`,
    noWatch: "No watch.", others: "Other runs",
    watchUpTo: d => `Watch up to ${d}`,
    canClose: "You can close the page: the analysis goes on in the server, and the state is saved after each step.",
    progress: (min, cost) => `Started ${min} min ago · cost of this run ≈ ${cost}`,
    applyId: id => `Apply ${id}`,
    crossCheck: "Cross-check", from: "From",
    sourceMissing: "Source to check", leftovers: n => `Removed values still present, left as they are (${n})`,
    reviewFigures: ["watch items", "touch a page", "corrections proposed", "addition leads"],
    corrections: "Corrections",
    reviewHelp: "Tick what should be applied. Related corrections (a sentence and its footnote, for instance) form a group and are ticked together. A group with a member that cannot apply is left out whole.",
    group: g => `Group ${g}`, groupLeftOut: " · left out: a member does not apply",
    noCorrection: "No correction proposed.",
    leads: n => `Addition leads (${n}, not drafted)`, none: "None.", nothing: "Nothing.",
    noticed: n => `Noticed elsewhere in the guide (${n})`,
    noticedHelp: "To fix them: « Report an error », with the relevant lines.",
    excerptMissing: "excerpt not found in the page", excerptApprox: "closest passage, not an exact quote",
    claims: n => `Claims due for re-check (${n})`,
    report: "Full report (Markdown)",
    applyNothing: "Apply nothing", applyN: n => `Apply ${n} correction${n > 1 ? "s" : ""}`,
    confirmNothing: "Apply nothing and close this run?",
    publishFigures: ["corrections applied", "English pages updated", "guide audits", "link(s) to check"],
    failed: "Failed",
    branchReady: b => `Branch <code>${b}</code>, ready locally. Nothing has left the machine yet.`,
    auditsRed: "The guide audits fail: the PR would be red.",
    translation: "Translation", linksTitle: "Links", linksNew: "(« NEW »: added by this run)",
    linksOk: "Every source of the changed pages answers.",
    changes: "Changes", doNotPublish: "Do not publish", publish: "Push and open the pull request",
    confirmNo: "Keep the branch locally, without a pull request?",
    end: {
      published: pr => `Pull request: ${pr}. Once reviewed and merged on GitHub, the site redeploys by itself.`,
      "pr-open": pr => `Pull request to review and merge on GitHub: ${pr}. The site redeploys by itself after the merge.`,
      merged: pr => `Done: the ${pr} is merged and the site redeployed.`,
      "pr-closed": pr => `The ${pr} was closed without merging.`,
      "nothing-applied": () => "No correction applied: the run is closed.",
      "not-published": (pr, b) => `Branch <code>${b}</code> kept locally, without a pull request.`,
      stopped: () => "The run stopped on an error. It can resume from the last finished step.",
      new: () => "This run has not started.",
    },
    resume: "Resume", applied: "Applied",
    reportTitle: "Report an error",
    reportIntro: "One error per line: the page, what is wrong, and the right information if you have it. The agent checks each point on primary sources, with the whole guide in context, then proposes corrections you review as for a watch. About 5 to 7 $.",
    reportExample: "03-stack/engines.md: vLLM 0.31 is no longer the minimum version, 0.33 fixes a security advisory.",
    reportButton: "Check and propose corrections",
    costsTitle: "Costs",
    costsIntro: total => `Computed from the usage the API returns, at list price (journal <code>metrics/usage.jsonl</code>). The Console's billing page stays the reference. Total: ${total}.`,
    columns: ["Calls", "Tokens in", "Out", "Cost"], byMonth: "By month", month: "Month", byRun: "By run", run: "Run",
  },
};
const savedLang = () => { try { return localStorage.getItem("vault-watch-lang"); } catch { return null; } };
let lang = TEXTS[savedLang()] ? savedLang() : (navigator.language || "en").startsWith("fr") ? "fr" : "en";
let T = TEXTS[lang];

const CLASSES = {
  running: "attention", review: "attention", publish: "attention", "pr-open": "attention",
  published: "ok", merged: "ok", stopped: "error",
};
// Nothing left to do: the card is dimmed
const FINISHED = ["closed", "merged", "pr-closed", "nothing-applied", "not-published"];
const badge = st => `<span class="badge ${CLASSES[st] || "neutral"}">${T.statuses[st] || st}</span>`;

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-Vault-Watch": "1" },
  };
  const r = await fetch(path, opts).catch(() => { throw new Error(T.serverDown); });  // stopped (idle, closed)
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r.text();
}

// --- Header -------------------------------------------------------------------------------------------
let info = null;
function header() {
  document.documentElement.lang = lang;
  document.querySelectorAll("nav [data-nav]").forEach(a => a.textContent = T.nav[a.dataset.nav]);
  const links = info ? [info.site, `https://github.com/${info.repo}`, info.agent]
    .map((url, i) => url && extLink(url, `${T.links[i]} ↗`)).filter(Boolean).join("") : "";
  $("#external").innerHTML = `${links}<span class="langs">${["fr", "en"].map(l =>
    `<button data-lang="${l}" class="${l === lang ? "active" : ""}" aria-pressed="${l === lang}">${l.toUpperCase()}</button>`).join("")}</span>`;
  $("#external").querySelectorAll("[data-lang]").forEach(b => b.onclick = () => {
    lang = b.dataset.lang;
    T = TEXTS[lang];
    try { localStorage.setItem("vault-watch-lang", lang); } catch { /* private window: per page only */ }
    header();
    route();
  });
}

// --- Router --------------------------------------------------------------------------------------
async function route() {
  if (source) { source.close(); source = null; }
  clearTimeout(followTimer);
  const h = location.hash.slice(1) || "/";
  document.querySelectorAll("nav [data-nav]").forEach(a =>
    a.classList.toggle("active", h === "/" ? a.dataset.nav === "watches" : h.startsWith(`/${a.dataset.nav}`)));
  page.innerHTML = `<p class="muted">${T.loading}</p>`;
  try {
    if (h.startsWith("/run/")) await viewRun(decodeURIComponent(h.slice(5)));
    else if (h.startsWith("/check/")) await viewCheck(decodeURIComponent(h.slice(7)));
    else if (h === "/check") await viewChecks();
    else if (h === "/report") viewReport();
    else if (h === "/costs") await viewCosts();
    else await viewWatches();
  } catch (e) {
    page.innerHTML = `<p class="error-text">${esc(e.message)}</p>`;
  }
}
addEventListener("hashchange", route);

// --- Watches ---------------------------------------------------------------------------------------
async function viewWatches() {
  const [watches, others] = await Promise.all([api("/api/watches"), api("/api/runs")]);
  page.innerHTML = `
    <h1>${T.watches}</h1>
    <p class="subtitle">${T.watchesIntro}</p>
    ${watches.map(v => {
      const r = v.run, link = `#/run/${encodeURIComponent(r.thread)}`;
      const action = r.status === "closed" ? ""
        : r.status === "new" ? `<button class="primary" data-analyse="${v.number}">${T.analyse}</button>`
        : r.status === "pr-open" ? extLink(r.pr_url, `<button class="primary">${T.merge}</button>`)
        : `<a href="${link}"><button${["review", "publish", "stopped"].includes(r.status) ? ' class="primary"' : ""}>${
            T.buttons[r.status] || T.details}</button></a>`;
      return `<div class="card row${FINISHED.includes(r.status) ? " finished" : ""}">
        <div class="grow">
          <b>#${v.number}</b> ${esc(v.title)} ${v.urgent ? `<span class="badge ${FINISHED.includes(r.status) ? "neutral" : "error"}">urgent</span>` : ""}
          <div class="muted small">${v.date} · ${T.issue(v.state === "open")}${
            !["new", "closed"].includes(r.status) ? ` · ${T.count(r.corrections, r.applied)} · ${dollars(r.cost)}` : ""}${
            r.pr_url ? ` · ${extLink(r.pr_url, "pull request")}` : ""}</div>
        </div>
        ${badge(r.status)} ${action}
      </div>`;
    }).join("") || `<p class="muted">${T.noWatch}</p>`}
    ${others.length ? `<h2>${T.others}</h2>${others.map(r => `
      <div class="card row${FINISHED.includes(r.status) ? " finished" : ""}"><div class="grow"><b>${esc(r.thread)}</b>
        <div class="muted small">${esc(r.source)} · ${r.corrections} correction(s) · ${dollars(r.cost)}${
          r.pr_url ? ` · ${extLink(r.pr_url, "pull request")}` : ""}</div></div>
        ${badge(r.status)} <a href="#/run/${encodeURIComponent(r.thread)}"><button>${T.details}</button></a></div>`).join("")}` : ""}`;
  page.querySelectorAll("[data-analyse]").forEach(b => b.onclick = async () => {
    b.disabled = true;
    const { thread } = await api("/api/analyses", { issue: Number(b.dataset.analyse) });
    location.hash = `/run/${encodeURIComponent(thread)}`;
  });
}

// --- One run ---------------------------------------------------------------------------------------
async function viewRun(thread) {
  const r = await api(`/api/runs/${encodeURIComponent(thread)}`);
  const title = `<h1>${esc(r.source || thread)} ${badge(r.status)}</h1>
    <p class="subtitle">${r.as_of ? `${T.watchUpTo(r.as_of)} · ` : ""}${esc(r.usage)}</p>`;
  if (r.status === "running") return viewRunning(r, title);
  if (r.status === "review") return viewReview(r, title);
  if (r.status === "publish") return viewPublish(r, title);
  viewEnd(r, title);
}

function viewRunning(r, title) {
  const doneSteps = new Set(r.job.events.map(e => e.node));
  const first = r.job.action === "fix" ? "propose" : { run: "collect", review: "apply", publish: "publish", resume: null }[r.job.action];
  const steps = r.steps.slice(first ? r.steps.indexOf(first) : 0);
  const cost = r.job.events.reduce((m, e) => e.cost ?? m, 0);
  page.innerHTML = `${title}
    <div class="card">
      <ol class="steps" id="steps">${steps.map(s => `<li data-step="${s}">${T.steps[s]}</li>`).join("")}</ol>
      <p class="muted small" id="progress"></p>
    </div>
    <p class="muted small">${T.canClose}</p>`;
  const update = (cost) => {
    let current = true;
    page.querySelectorAll("#steps li").forEach(li => {
      const done = doneSteps.has(li.dataset.step);
      li.classList.toggle("done", done);
      li.classList.toggle("current", !done && current && (current = false, true));
    });
    const min = Math.round((Date.now() / 1000 - r.job.started) / 60);
    $("#progress").textContent = T.progress(min, dollars(cost));
  };
  update(cost);
  source = new EventSource(`/api/runs/${encodeURIComponent(r.thread)}/events`);
  source.onmessage = ev => { const e = JSON.parse(ev.data); doneSteps.add(e.node); update(e.cost ?? cost); };
  source.addEventListener("end", () => { source.close(); source = null; route(); });
}

// Word-level diff: words removed from `a` wrapped in <del>, words added to `b` in <ins>.
function wordDiff(a, b) {
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
function excerpts(list) {
  if (!list?.length) return "";
  const row = l => `<div${l.hit ? ' class="target"' : ""}><span class="n">${l.n}</span><span>${
    l.parts ? `${esc(l.parts[0])}<mark>${esc(l.parts[1])}</mark>${esc(l.parts[2])}` : esc(l.text)}</span></div>`;
  return `<div class="excerpts">${list.map(e => e.match === "missing"
    ? `<div class="excerpt muted small"><code>${esc(e.page)}</code> · ${T.excerptMissing}</div>`
    : `<div class="excerpt"><div class="muted small"><code>${esc(e.page)}:${e.line}</code>${e.match === "approx" ? ` · ${T.excerptApprox}` : ""}</div>
        <div class="lines" lang="${e.page.startsWith("en/") ? "en" : "fr"}">${e.lines.map(row).join("")}</div></div>`).join("")}</div>`;
}

function correctionCard(c, r) {
  const valid = c.check === "ok";
  const [before, after] = wordDiff(c.current, c.proposed);
  const sources = (c.item_ids || [c.item_id]).map(id => r.items[id]).filter(Boolean)
    .map(i => i.url ? extLink(i.url, esc(i.title)) : esc(i.title)).join(" · ");
  return `<div class="card correction${valid ? "" : " rejected"}">
    <input type="checkbox" data-id="${c.id}" data-group="${c.group}" ${valid ? "checked" : "disabled"} aria-label="${T.applyId(c.id)}">
    <div>
      <div class="header"><b>${c.id}</b><span class="badge ${c.severity}">${c.severity}</span><code>${esc(c.page)}</code>
        ${valid ? "" : `<span class="badge error">${esc(c.check)}</span>`}</div>
      <p>${esc(c.rationale)}</p>
      ${c.review ? `<p class="muted small">${T.crossCheck} : ${esc(c.review)}</p>` : ""}
      ${c.warning ? `<p class="small">⚠️ ${T.sourceMissing} : ${esc(c.warning)}</p>` : ""}
      <div class="diff before" lang="fr">${before}</div>
      <div class="diff after" lang="fr">${after}</div>
      <div class="muted small">${T.from} ${sources || "—"}${c.source_url ? ` · ${extLink(c.source_url, "source")}` : ""}</div>
    </div>
  </div>`;
}

function viewReview(r, title) {
  const num = id => Number(id.slice(1));
  const groups = {};
  for (const c of [...r.corrections].sort((a, b) => num(a.group) - num(b.group) || num(a.id) - num(b.id)))
    (groups[c.group] ||= []).push(c);
  const broken = new Set(r.corrections.filter(c => c.check !== "ok").map(c => c.group));
  const figures = [Object.values(r.triage).reduce((a, b) => a + b, 0), r.triage.correct, r.corrections.length, r.additions.length];
  page.innerHTML = `${title}
    <div class="figures">${figures.map((n, i) => `<div><b>${n}</b>${T.reviewFigures[i]}</div>`).join("")}</div>
    <h2>${T.corrections}</h2>
    <p class="muted small">${T.reviewHelp}</p>
    ${Object.entries(groups).map(([g, cs]) => cs.length > 1
      ? `<div class="group"><p class="muted small">${T.group(g)}${broken.has(g) ? T.groupLeftOut : ""}</p>${cs.map(c => correctionCard(c, r)).join("")}</div>`
      : correctionCard(cs[0], r)).join("") || `<p class="muted">${T.noCorrection}</p>`}
    <details><summary>${T.leads(r.additions.length)}</summary>
      <ul>${r.additions.map(a => `<li>${a.url ? extLink(a.url, esc(a.title)) : esc(a.title)} : ${esc(a.reason)}</li>`).join("") || `<li>${T.none}</li>`}</ul></details>
    <details><summary>${T.noticed(r.findings.length)}</summary>
      <ul>${r.findings.map(f => `<li>${esc(f)}${excerpts(r.finding_excerpts?.[f])}</li>`).join("") || `<li>${T.nothing}</li>`}</ul>
      ${r.findings.length ? `<p class="muted small">${T.noticedHelp}</p>` : ""}</details>
    <details><summary>${T.leftovers(r.leftovers.length)}</summary>
      <ul>${r.leftovers.map(h => `<li><code>${esc(h.page)}:${h.line}</code> (${esc(h.tokens.join(", "))}) : ${esc(h.text)}</li>`).join("") || `<li>${T.none}</li>`}</ul></details>
    <details><summary>${T.claims(r.claims_due.length)}</summary>
      <ul>${r.claims_due.map(c => `<li>${esc(c.recheckBy)} <code>${esc(c.page)}</code> : ${esc(c.claim)}</li>`).join("") || `<li>${T.none}</li>`}</ul></details>
    <p class="small"><a href="/api/runs/${encodeURIComponent(r.thread)}/report" target="_blank">${T.report}</a></p>
    <div class="bar">
      <button id="nothing">${T.applyNothing}</button>
      <button class="primary" id="apply"></button>
    </div>`;
  const boxes = [...page.querySelectorAll(".correction input")];
  boxes.filter(i => broken.has(i.dataset.group)).forEach(i => { i.checked = false; i.disabled = true; });
  const count = () => {
    const n = boxes.filter(i => i.checked).length;
    $("#apply").textContent = T.applyN(n);
    $("#apply").disabled = n === 0;
  };
  boxes.forEach(i => i.onchange = () => {
    boxes.filter(o => o.dataset.group === i.dataset.group && !o.disabled).forEach(o => o.checked = i.checked);
    count();
  });
  count();
  const send = async accept => {
    page.querySelectorAll(".bar button").forEach(b => b.disabled = true);
    await api(`/api/runs/${encodeURIComponent(r.thread)}/review`, { accept });
    route();
  };
  $("#apply").onclick = () => send(boxes.filter(i => i.checked).map(i => i.dataset.id));
  $("#nothing").onclick = () => confirm(T.confirmNothing) && send("none");
}

async function viewPublish(r, title) {
  const p = { mirror_problems: [], link_problems: [], ...r.pause };
  const diff = await api(`/api/runs/${encodeURIComponent(r.thread)}/diff`).catch(() => "");
  const color = l => l.startsWith("+") && !l.startsWith("+++") ? "plus" : l.startsWith("-") && !l.startsWith("---") ? "minus" : "";
  const figures = [r.applied.length, r.mirrored.length, p.audit_ok ? "OK" : T.failed, p.link_problems.length];
  page.innerHTML = `${title}
    <div class="figures">${figures.map((n, i) => `<div><b>${n}</b>${T.publishFigures[i]}</div>`).join("")}</div>
    <div class="card">
      <p>${T.branchReady(esc(p.branch))}</p>
      ${p.audit_ok ? "" : `<p class="error-text">${T.auditsRed}</p><pre>${esc(r.audit_log)}</pre>`}
      ${p.mirror_problems.length ? `<p><b>${T.translation}</b></p><ul>${p.mirror_problems.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${p.link_problems.length ? `<p><b>${T.linksTitle}</b> ${T.linksNew}</p><ul>${p.link_problems.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="muted">${T.linksOk}</p>`}
    </div>
    <details open><summary>${T.changes}</summary>
      <pre>${diff.split("\n").map(l => `<span class="${color(l)}">${esc(l)}</span>`).join("\n") || esc(p.diffstat)}</pre></details>
    <div class="bar">
      <button id="no">${T.doNotPublish}</button>
      <button class="primary" id="yes">${T.publish}</button>
    </div>`;
  const send = async go => {
    page.querySelectorAll(".bar button").forEach(b => b.disabled = true);
    await api(`/api/runs/${encodeURIComponent(r.thread)}/publish`, { go });
    route();
  };
  $("#yes").onclick = () => send(true);
  $("#no").onclick = () => confirm(T.confirmNo) && send(false);
}

function viewEnd(r, title) {
  const pr = r.pr_url ? extLink(r.pr_url, "pull request") : "";
  const text = (T.end[r.status] || (() => ""))(pr, esc(r.branch));
  page.innerHTML = `${title}
    <div class="card"><p>${text}</p>
      ${r.error ? `<p class="error-text">${esc(r.error)}</p>` : ""}
      ${r.status === "stopped" ? `<button class="primary" id="resume">${T.resume}</button>` : ""}</div>
    ${r.applied.length ? `<p>${T.applied} : ${r.applied.join(", ")}</p>` : ""}
    ${r.report_path ? `<p class="small"><a href="/api/runs/${encodeURIComponent(r.thread)}/report" target="_blank">${T.report}</a></p>` : ""}`;
  const b = $("#resume");
  if (b) b.onclick = async () => { b.disabled = true; await api(`/api/runs/${encodeURIComponent(r.thread)}/resume`, {}); route(); };
}

// --- Check the guide ---------------------------------------------------------------------------------------
let followTimer = null;  // timer following a running check
const checkBadge = p => {
  const V = T.verif, [text, cls] = {
    running: [V.running, "attention"], "to-handle": [V.toHandle(p.counts.open), "attention"],
    handled: [V.handled, "ok"], clear: [V.ok, "ok"],
  }[p.status] || [p.status, "neutral"];
  return `<span class="badge ${cls}">${text}</span>`;
};

async function viewChecks() {
  const [options, verifs] = await Promise.all([api("/api/verifications/options"), api("/api/verifications")]);
  const V = T.verif, titles = Object.fromEntries(options.map(o => [o.id, o.title[lang]]));
  const price = o => o.model ? (o.usd == null ? V.unknown : `≈ ${dollars(o.usd)}`) : V.free;
  // What is left to handle comes first; a new check is folded away while leads remain (it would find them again)
  const pending = verifs.filter(p => ["to-handle", "running"].includes(p.status));
  const remaining = pending.reduce((s, p) => s + p.counts.open, 0);
  const checkCard = p => `<div class="card row${["handled", "clear"].includes(p.status) ? " finished" : ""}"><div class="grow"><b>${new Date(p.started * 1000).toLocaleString(lang)}</b>
        <div class="muted small">${p.checks.map(c => esc(titles[c] || c)).join(" · ")} · ${dollars(p.cost)}</div>
        <div class="muted small">${V.counts(p.counts)}</div></div>
        ${checkBadge(p)}
        <a href="#/check/${encodeURIComponent(p.id)}"><button${p.status === "to-handle" ? ' class="primary"' : ""}>${p.status === "to-handle" ? V.handle : T.details}</button></a></div>`;
  const older = verifs.filter(p => !pending.includes(p));
  page.innerHTML = `
    <h1>${V.title}</h1>
    <p class="subtitle">${V.intro}</p>
    ${pending.length ? `<h2>${V.toHandleTitle}</h2>${pending.map(checkCard).join("")}` : ""}
    <details class="new-check"${pending.length ? "" : " open"}><summary><h2>${V.newCheck}</h2></summary>
    ${remaining ? `<p class="attention-text">${V.warning(remaining)}</p>` : ""}
    ${options.map(o => `<label class="card option">
      <input type="checkbox" data-check="${o.id}" ${o.model ? "" : "checked"}>
      <div>
        <div class="header"><b>${esc(o.title[lang])}</b>
          <span class="badge ${o.model ? "attention" : "ok"}">${price(o)}</span>
          ${o.tokens ? `<span class="muted small">${V.tokens(o.tokens)}</span>` : ""}</div>
        <p class="muted small">${esc(o.what[lang])}</p>
        <p class="muted small">${esc(o.note[lang])}${o.model ? ` · ${esc(o.model)}` : ""}${o.needs.length ? ` · ${V.needs(o.needs.map(n => titles[n]).join(", "))}` : ""}</p>
      </div></label>`).join("")}
    <p><button class="primary" id="start"></button></p>
    </details>
    <h2>${V.history}</h2>
    ${older.map(checkCard).join("") || `<p class="muted">${V.none}</p>`}`;
  const boxes = [...page.querySelectorAll("[data-check]")];
  const total = () => {
    const ids = new Set(boxes.filter(c => c.checked).map(c => c.dataset.check));
    options.filter(o => ids.has(o.id)).forEach(o => o.needs.forEach(n => ids.add(n)));
    const usd = options.filter(o => ids.has(o.id)).reduce((s, o) => s + (o.usd || 0), 0);
    $("#start").textContent = V.start(dollars(usd));
    $("#start").disabled = ids.size === 0;
  };
  boxes.forEach(c => c.onchange = total);
  total();
  $("#start").onclick = async () => {
    $("#start").disabled = true;
    const { id } = await api("/api/verifications", { checks: boxes.filter(c => c.checked).map(c => c.dataset.check) });
    location.hash = `/check/${encodeURIComponent(id)}`;
  };
}

async function viewCheck(id) {
  clearTimeout(followTimer);
  const [v, options] = await Promise.all([api(`/api/verifications/${encodeURIComponent(id)}`), api("/api/verifications/options")]);
  if (location.hash.slice(1) !== `/check/${id}`) return;  // left the page meanwhile
  const V = T.verif, titles = Object.fromEntries(options.map(o => [o.id, o.title[lang]]));
  const list = (title, items) => items && items.length ? `<details><summary>${title} (${items.length})</summary><ul>${items.map(x => `<li>${x}</li>`).join("")}</ul></details>` : "";
  page.innerHTML = `
    <h1>${V.title} · ${new Date(v.started * 1000).toLocaleString(lang)} ${checkBadge(v)}</h1>
    <p class="subtitle">${V.cost(dollars(v.cost))} · ${V.counts(v.counts)}</p>
    ${v.error ? `<p class="error-text">${esc(v.error)}</p>` : ""}
    ${Object.keys(v.runs).length ? `<h2>${V.fixRuns}</h2>${Object.entries(v.runs).map(([t, run]) => `
      <div class="card row${FINISHED.includes(run.status) ? " finished" : ""}"><div class="grow"><b>${esc(t)}</b>
        ${run.pr_url ? `<div class="muted small">${extLink(run.pr_url, run.pr_url)}</div>` : ""}</div>
        ${badge(run.status)}
        ${run.status === "pr-open" ? extLink(run.pr_url, `<button class="primary">${T.merge}</button>`)
          : `<a href="#/run/${encodeURIComponent(t)}"><button${["review", "publish"].includes(run.status) ? ' class="primary"' : ""}>${
            T.buttons[run.status] || T.details}</button></a>`}</div>`).join("")}` : ""}
    ${v.checks.map(c => {
      const r = v.results[c];
      // A check whose findings are all handled (sent or dismissed) is done, even if it found problems
      const stateBadge = !r ? `<span class="badge neutral">${v.running ? V.waiting : "—"}</span>`
        : r.summary?.startsWith("could not run") ? `<span class="badge error">${V.failed}</span>`
        : r.findings?.length && !r.open ? `<span class="badge ok">${V.handled}</span>`
        : `<span class="badge ${r.ok ? "ok" : "attention"}">${r.ok ? V.ok : r.open ? V.toHandle(r.open) : V.problems}</span>`;
      // Folded by default once nothing is left to do in it (all handled, or fine); the reader's choice is kept
      const finished = r && !r.open && !r.summary?.startsWith("could not run") && (r.ok || r.findings?.length);
      const isOpen = FOLDS[`${id}/${c}`] ?? !finished;
      return `<details class="card foldable" data-fold="${id}/${c}"${isOpen ? " open" : ""}><summary class="header"><b>${esc(titles[c] || c)}</b>${stateBadge}${r?.open ? ` <button class="small-button" data-tick-card="${c}">${V.tickCard(r.open)}</button>` : ""}</summary>
        ${r ? `<p class="muted small">${esc(r.summary)}</p>
          ${list(V.dead, (r.dead || []).map(d => `${extLink(d.url, esc(d.url))} — ${esc(d.status)} ${esc(d.code ?? "")} (${esc(d.pages.join(", "))})`))}
          ${list(V.blocked, (r.blocked || []).map(d => `${extLink(d.url, esc(d.url))} (${esc(d.pages.join(", "))})`))}
          ${list(V.claims, (r.claims || []).map(x => `${esc(x.recheckBy)} <code>${esc(x.page)}</code> : ${esc(x.claim)}`))}
          ${list(V.pagesDue, (r.pages_due || []).map(esc))}
          ${r.log ? `<details><summary>${V.log}</summary><pre>${esc(r.log)}</pre></details>` : ""}
          ${(r.findings || []).length ? `${r.fixable ? "" : `<p class="muted small">${V.notFixable}</p>`}<ul class="leads">${r.findings.map((f, i) => lead(f, r.fixable, c, r.mode, i + 1, r.excerpts?.[f])).join("")}</ul>` : ""}` : ""}
      </details>`;
    }).join("")}
    <div class="bar">
      <button id="all">${V.tickAll}</button><button id="nothing">${V.untickAll}</button>
      <button id="dismiss"></button>
      <button class="primary" id="fix"></button>
    </div>`;
  // A finding is open (checkbox), sent to a fix run (link to the run) or dismissed (can be reopened)
  // Handled findings stay one line; an open one shows the passages it is about
  function lead(f, fixable, card, mode = "fix", n = 0, passages = []) {
    const h = v.handled[f], num = `<span class="num">${n}.</span>`;  // per card, stable: handled lines keep theirs
    if (h?.status === "fix") {
      const run = v.runs[h.thread] || {};
      return `<li class="handled">${num} <span class="badge ok">${V.sent}</span> <a href="#/run/${encodeURIComponent(h.thread)}">${esc(h.thread)}</a>
        ${run.status ? badge(run.status) : ""}${run.pr_url ? ` ${extLink(run.pr_url, "PR")}` : ""} · ${esc(f)}</li>`;
    }
    if (h?.status === "dismissed") return `<li class="handled">${num} <span class="badge neutral">${V.dismissed}</span> <button class="small-button" data-reopen="${esc(f)}">${V.reopen}</button> ${esc(f)}</li>`;
    return `<li><label><input type="checkbox" data-lead="${esc(f)}" data-fixable="${fixable}" data-mode="${mode}" data-card="${card}"> ${num} <span>${esc(f)}</span></label>${excerpts(passages)}</li>`;
  }
  const boxes = [...page.querySelectorAll("[data-lead]")];
  const ticked = () => boxes.filter(c => c.checked);
  const count = () => {
    const ok = ticked().filter(c => c.dataset.fixable === "true"), n = ok.length, e = ticked().length;
    $("#fix").textContent = V.createFix(n, ok.filter(c => c.dataset.mode === "translation").length); $("#fix").disabled = n === 0 || v.running;
    $("#dismiss").textContent = V.dismiss(e); $("#dismiss").disabled = e === 0 || v.running;
  };
  boxes.forEach(c => c.onchange = count);
  // Tick or untick every open finding of one card (all ticked: untick)
  page.querySelectorAll("[data-fold]").forEach(d => d.ontoggle = () => { FOLDS[d.dataset.fold] = d.open; });
  page.querySelectorAll("[data-tick-card]").forEach(b => b.onclick = e => {
    e.preventDefault();  // in the card's summary: tick, do not fold
    const card = boxes.filter(c => c.dataset.card === b.dataset.tickCard), all = card.every(c => c.checked);
    card.forEach(c => c.checked = !all);
    count();
  });
  $("#all").onclick = () => { boxes.forEach(c => c.checked = true); count(); };
  $("#nothing").onclick = () => { boxes.forEach(c => c.checked = false); count(); };
  count();
  const leads = (findings, status) => api(`/api/verifications/${encodeURIComponent(id)}/leads`, { findings, status }).then(() => viewCheck(id));
  page.querySelectorAll("[data-reopen]").forEach(b => b.onclick = () => leads([b.dataset.reopen], "open"));
  if (!boxes.length) page.querySelector(".bar").remove();
  else {
    $("#dismiss").onclick = () => leads(ticked().map(c => c.dataset.lead), "dismissed");
    $("#fix").onclick = async () => {
      $("#fix").disabled = true;
      // One run per mode: content fixes and translation fixes do not take the same path
      const threads = [];
      for (const mode of ["fix", "translation"]) {
        const text = ticked().filter(c => c.dataset.fixable === "true" && c.dataset.mode === mode).map(c => c.dataset.lead).join("\n");
        if (text) threads.push((await api("/api/fix", { text, verification: id, mode })).thread);
      }
      location.hash = `/run/${encodeURIComponent(threads[0])}`;
    };
  }
  if (v.running) followTimer = setTimeout(() => viewCheck(id).catch(() => {}), 3000);
}

const FOLDS = {};  // check cards folded or opened by the reader, by verification/check, kept across refreshes

// --- Report errors -----------------------------------------------------------------------------------
function viewReport() {
  page.innerHTML = `
    <h1>${T.reportTitle}</h1>
    <p class="subtitle">${T.reportIntro}</p>
    <textarea id="text" placeholder="${esc(T.reportExample)}"></textarea>
    <p><button class="primary" id="send">${T.reportButton}</button></p>`;
  $("#send").onclick = async () => {
    const text = $("#text").value.trim();
    if (!text) return;
    $("#send").disabled = true;
    const { thread } = await api("/api/fix", { text });
    location.hash = `/run/${encodeURIComponent(thread)}`;
  };
}

// --- Costs -------------------------------------------------------------------------------------------------
async function viewCosts() {
  const c = await api("/api/costs");
  const number = n => n.toLocaleString(lang);
  const table = (rows, title) => `<table><thead><tr><th>${title}</th>${T.columns.map(x => `<th class="number">${x}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(r => `<tr><td>${esc(r.key)}</td><td class="number">${r.calls}</td><td class="number">${number(r.in)}</td><td class="number">${number(r.out)}</td><td class="number">${dollars(r.cost)}</td></tr>`).join("")}</tbody></table>`;
  const total = c.month.reduce((s, r) => s + r.cost, 0);
  page.innerHTML = `
    <h1>${T.costsTitle}</h1>
    <p class="subtitle">${T.costsIntro(dollars(total))}</p>
    <h2>${T.byMonth}</h2><div class="card">${table(c.month, T.month)}</div>
    <h2>${T.byRun}</h2><div class="card">${table([...c.run].reverse(), T.run)}</div>`;
}

header();
api("/api/info").then(i => { info = i; header(); }).catch(() => {});
route();
