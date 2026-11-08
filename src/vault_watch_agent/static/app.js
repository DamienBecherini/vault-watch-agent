/* vault-watch: one screen per pause of the graph. Routes: #/ (watches), #/run/<thread>, #/signaler, #/couts.
   The server holds every state (checkpoints); this page only shows it and sends the human's answers.
   Interface in French or English (toggle in the header, remembered); the guide's own text stays in French. */

const $ = s => document.querySelector(s);
const page = $("#page");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const dollars = n => `${(n ?? 0).toFixed(2)} $`;
const lienExt = (url, texte) => `<a href="${esc(url)}" target="_blank" rel="noopener">${texte}</a>`;
let source = null;  // EventSource of the run being followed

// --- Languages ---------------------------------------------------------------------------------------
const TEXTES = {
  fr: {
    nav: { veilles: "Veilles", verifier: "Vérifier le guide", signaler: "Signaler une erreur", couts: "Coûts" },
    liens: ["Guide", "Dépôt du guide", "Code de l'agent"],
    verif: {
      titre: "Vérifier le guide",
      intro: "Un bilan de santé du guide entier, à la demande. Les contrôles gratuits utilisent les scripts du guide ; les autres font lire le guide par Claude. Les résultats sont des pistes : celles que tu gardes partent dans une passe fix, qui les vérifie sur les sources et passe par ta relecture.",
      gratuit: "gratuit", tokens: n => `≈ ${n.toLocaleString("fr")} tokens`, inconnu: "selon le résultat",
      necessite: ids => `lance aussi : ${ids}`,
      lancer: usd => `Lancer la vérification · ≈ ${usd}`, historique: "Vérifications précédentes",
      aucune: "Aucune vérification pour l'instant.", enCours: "En cours…", pistes: n => `${n} piste(s)`,
      attente: "en attente", ok: "RAS", problemes: "à regarder", echec: "n'a pas pu tourner",
      nonCorrigeable: "Pas encore corrigeable par une passe fix (les traductions se corrigent depuis le français) : à reprendre à la main ou par une prochaine fonction.",
      voirDetails: "Détails", morts: "Sources qui ne répondent pas", bloques: "Bloquées par une protection anti-robots (souvent normales dans un navigateur)",
      affirmations: "Affirmations à revérifier", pagesDues: "Pages à revoir", journal: "Journal",
      creerFix: n => `Créer une passe fix avec ${n} piste(s) · ≈ 6 $`, toutCocher: "Tout cocher", rienCocher: "Tout décocher",
      cout: c => `Coût : ${c}`,
      comptes: c => c.open + c.fix + c.dismissed === 0 ? "aucune piste"
        : `${c.open} à traiter · ${c.fix} envoyée(s) en passe fix · ${c.dismissed} écartée(s)`,
      aTraiter: n => `${n} piste(s) à traiter`, traitee: "Traitée", traiter: "Traiter",
      envoyee: "→ passe fix", ecartee: "écartée", retablir: "Rétablir", ecarter: n => `Écarter ${n} piste(s)`,
    },
    chargement: "Chargement…",
    serveurArrete: "Le serveur ne répond pas : il s'arrête après 1 h d'inactivité. Relance-le (Nouvel onglet, module « Veille du guide IA »), puis recharge la page. Les passages en pause n'ont rien perdu.",
    statuts: {
      new: "À analyser", running: "En cours", review: "Relecture à faire", publish: "Publication à valider",
      published: "PR créée", "nothing-applied": "Rien appliqué", "not-published": "Non publié", stopped: "Interrompu",
      closed: "Traitée hors agent", merged: "✓ Terminée · PR fusionnée", "pr-open": "PR à fusionner",
      "pr-closed": "PR fermée sans fusion",
    },
    etapes: {
      collect: "Récupération de la veille", triage: "Tri des éléments", locate: "Recherche des pages concernées",
      propose: "Propositions de corrections", number: "Numérotation et contrôle des citations",
      crosscheck: "Relecture avec tout le guide et le web", report: "Rapport", review: "Ta relecture",
      apply: "Application sur une branche", mirror: "Traduction anglaise", audits: "Contrôles du guide (npm test)",
      links: "Vérification des liens", publish: "Push et pull request",
    },
    veilles: "Veilles",
    veillesIntro: "Une veille est publiée par GitHub tous les 15 jours. L'agent l'analyse, tu relis ses propositions, puis il ouvre la pull request.",
    analyser: "Analyser · ≈ 4 $", fusionner: "Fusionner sur GitHub",
    boutons: { review: "Relire", publish: "Valider la publication", running: "Suivre", stopped: "Reprendre" },
    details: "Détails",
    issue: open => `issue ${open ? "ouverte" : "fermée"}`,
    compte: (n, a) => `${n} correction(s), ${a} appliquée(s)`,
    aucuneVeille: "Aucune veille.", autres: "Autres passages",
    veilleJusqua: d => `Veille jusqu'au ${d}`,
    peutFermer: "Tu peux fermer la page : l'analyse continue sur le serveur, et l'état est enregistré à chaque étape.",
    avancement: (min, cout) => `Démarré il y a ${min} min · coût de ce passage ≈ ${cout}`,
    appliquerId: id => `Appliquer ${id}`,
    relectureGlobale: "Relecture globale", dapres: "D'après",
    chiffresRelecture: ["éléments de veille", "touchent une page", "corrections proposées", "pistes d'ajout"],
    corrections: "Corrections",
    aideRelecture: "Coche ce qui doit être appliqué. Les corrections liées (une phrase et sa note, par exemple) forment un groupe : elles se cochent ensemble. Un groupe dont un membre ne peut pas s'appliquer est écarté en entier.",
    groupe: g => `Groupe ${g}`, groupeEcarte: " · écarté : un membre ne s'applique pas",
    aucuneCorrection: "Aucune correction proposée.",
    pistes: n => `Pistes d'ajout (${n}, non rédigées)`, aucune: "Aucune.", rien: "Rien.",
    remarque: n => `Remarqué ailleurs dans le guide (${n})`,
    remarqueAide: "Pour les corriger : « Signaler une erreur », en copiant les lignes utiles.",
    affirmations: n => `Affirmations à revérifier (${n})`,
    rapport: "Rapport complet (Markdown)",
    neRienAppliquer: "Ne rien appliquer", appliquerN: n => `Appliquer ${n} correction${n > 1 ? "s" : ""}`,
    confirmerRien: "Ne rien appliquer et clore ce passage ?",
    chiffresPublication: ["corrections appliquées", "pages anglaises mises à jour", "contrôles du guide", "lien(s) à vérifier"],
    echec: "Échec",
    branchePrete: b => `Branche <code>${b}</code>, prête localement. Rien n'a encore quitté la machine.`,
    auditsRouges: "Les contrôles du guide échouent : la PR serait rouge.",
    traduction: "Traduction", liensTitre: "Liens", liensNew: "(« NEW » : ajouté par ce passage)",
    liensOk: "Toutes les sources des pages modifiées répondent.",
    modifications: "Modifications", nePasPublier: "Ne pas publier", publier: "Pousser et ouvrir la pull request",
    confirmerNon: "Garder la branche en local sans pull request ?",
    fin: {
      published: pr => `Pull request : ${pr}. Une fois relue et fusionnée sur GitHub, le site se redéploie tout seul.`,
      "pr-open": pr => `Pull request à relire et fusionner sur GitHub : ${pr}. Le site se redéploie tout seul après la fusion.`,
      merged: pr => `Terminé : la ${pr} est fusionnée et le site redéployé.`,
      "pr-closed": pr => `La ${pr} a été fermée sans fusion.`,
      "nothing-applied": () => "Aucune correction appliquée : le passage est clos.",
      "not-published": (pr, b) => `Branche <code>${b}</code> gardée en local, sans pull request.`,
      stopped: () => "Le passage s'est arrêté sur une erreur. Il peut reprendre à la dernière étape terminée.",
      new: () => "Ce passage n'a pas commencé.",
    },
    reprendre: "Reprendre", appliquees: "Appliquées",
    signalerTitre: "Signaler une erreur",
    signalerIntro: "Une erreur par ligne : la page, ce qui est faux, et si possible la bonne information. L'agent vérifie chaque point sur des sources primaires, avec tout le guide en contexte, puis propose des corrections que tu relis comme pour une veille. Compte 5 à 7 $.",
    signalerExemple: "03-stack/engines.md : vLLM 0.31 n'est plus la version minimale, la 0.33 corrige un avis de sécurité.",
    signalerBouton: "Vérifier et proposer des corrections",
    coutsTitre: "Coûts",
    coutsIntro: total => `Calculés à partir de l'usage que renvoie l'API, au prix catalogue (journal <code>metrics/usage.jsonl</code>). La page de facturation de la Console reste la référence. Total : ${total}.`,
    colonnes: ["Appels", "Tokens lus", "Écrits", "Coût"], parMois: "Par mois", mois: "Mois", parPassage: "Par passage", passage: "Passage",
  },
  en: {
    nav: { veilles: "Watches", verifier: "Check the guide", signaler: "Report an error", couts: "Costs" },
    liens: ["Guide", "Guide repository", "Agent code"],
    verif: {
      titre: "Check the guide",
      intro: "A health check of the whole guide, on demand. The free checks run the guide's own scripts; the others have Claude read the guide. Results are leads: the ones you keep go to a fix run, which checks them on sources and goes through your review.",
      gratuit: "free", tokens: n => `≈ ${n.toLocaleString("en")} tokens`, inconnu: "depends on the result",
      necessite: ids => `also runs: ${ids}`,
      lancer: usd => `Run the check · ≈ ${usd}`, historique: "Previous checks",
      aucune: "No check yet.", enCours: "Running…", pistes: n => `${n} lead(s)`,
      attente: "waiting", ok: "all clear", problemes: "to look at", echec: "could not run",
      nonCorrigeable: "Not fixable by a fix run yet (translations are fixed from the French side): to handle by hand or by a later feature.",
      voirDetails: "Details", morts: "Sources not answering", bloques: "Blocked by anti-bot protections (often fine in a browser)",
      affirmations: "Claims to re-check", pagesDues: "Pages due for review", journal: "Log",
      creerFix: n => `Create a fix run with ${n} point(s) · ≈ 6 $`, toutCocher: "Tick all", rienCocher: "Untick all",
      cout: c => `Cost: ${c}`,
      comptes: c => c.open + c.fix + c.dismissed === 0 ? "no lead"
        : `${c.open} to handle · ${c.fix} sent to a fix run · ${c.dismissed} dismissed`,
      aTraiter: n => `${n} lead(s) to handle`, traitee: "Handled", traiter: "Handle",
      envoyee: "→ fix run", ecartee: "dismissed", retablir: "Reopen", ecarter: n => `Dismiss ${n} lead(s)`,
    },
    chargement: "Loading…",
    serveurArrete: "The server does not answer: it may have stopped after being idle (`serve --idle-exit`). Start it again, then reload the page. Paused runs lost nothing.",
    statuts: {
      new: "To analyse", running: "Running", review: "Review pending", publish: "Publish pending",
      published: "PR opened", "nothing-applied": "Nothing applied", "not-published": "Not published", stopped: "Stopped",
      closed: "Handled without the agent", merged: "✓ Done · PR merged", "pr-open": "PR to merge",
      "pr-closed": "PR closed unmerged",
    },
    etapes: {
      collect: "Download the watch", triage: "Triage the items", locate: "Find the pages concerned",
      propose: "Propose corrections", number: "Number them, check the quotes",
      crosscheck: "Cross-check with the whole guide and the web", report: "Report", review: "Your review",
      apply: "Apply on a branch", mirror: "English translation", audits: "Guide audits (npm test)",
      links: "Link checks", publish: "Push and pull request",
    },
    veilles: "Watches",
    veillesIntro: "GitHub publishes a watch every two weeks. The agent analyses it, you review its proposals, then it opens the pull request.",
    analyser: "Analyse · ≈ 4 $", fusionner: "Merge on GitHub",
    boutons: { review: "Review", publish: "Approve publishing", running: "Follow", stopped: "Resume" },
    details: "Details",
    issue: open => `issue ${open ? "open" : "closed"}`,
    compte: (n, a) => `${n} correction(s), ${a} applied`,
    aucuneVeille: "No watch.", autres: "Other runs",
    veilleJusqua: d => `Watch up to ${d}`,
    peutFermer: "You can close the page: the analysis goes on in the server, and the state is saved after each step.",
    avancement: (min, cout) => `Started ${min} min ago · cost of this run ≈ ${cout}`,
    appliquerId: id => `Apply ${id}`,
    relectureGlobale: "Cross-check", dapres: "From",
    chiffresRelecture: ["watch items", "touch a page", "corrections proposed", "addition leads"],
    corrections: "Corrections",
    aideRelecture: "Tick what should be applied. Related corrections (a sentence and its footnote, for instance) form a group and are ticked together. A group with a member that cannot apply is left out whole.",
    groupe: g => `Group ${g}`, groupeEcarte: " · left out: a member does not apply",
    aucuneCorrection: "No correction proposed.",
    pistes: n => `Addition leads (${n}, not drafted)`, aucune: "None.", rien: "Nothing.",
    remarque: n => `Noticed elsewhere in the guide (${n})`,
    remarqueAide: "To fix them: « Report an error », with the relevant lines.",
    affirmations: n => `Claims due for re-check (${n})`,
    rapport: "Full report (Markdown)",
    neRienAppliquer: "Apply nothing", appliquerN: n => `Apply ${n} correction${n > 1 ? "s" : ""}`,
    confirmerRien: "Apply nothing and close this run?",
    chiffresPublication: ["corrections applied", "English pages updated", "guide audits", "link(s) to check"],
    echec: "Failed",
    branchePrete: b => `Branch <code>${b}</code>, ready locally. Nothing has left the machine yet.`,
    auditsRouges: "The guide audits fail: the PR would be red.",
    traduction: "Translation", liensTitre: "Links", liensNew: "(« NEW »: added by this run)",
    liensOk: "Every source of the changed pages answers.",
    modifications: "Changes", nePasPublier: "Do not publish", publier: "Push and open the pull request",
    confirmerNon: "Keep the branch locally, without a pull request?",
    fin: {
      published: pr => `Pull request: ${pr}. Once reviewed and merged on GitHub, the site redeploys by itself.`,
      "pr-open": pr => `Pull request to review and merge on GitHub: ${pr}. The site redeploys by itself after the merge.`,
      merged: pr => `Done: the ${pr} is merged and the site redeployed.`,
      "pr-closed": pr => `The ${pr} was closed without merging.`,
      "nothing-applied": () => "No correction applied: the run is closed.",
      "not-published": (pr, b) => `Branch <code>${b}</code> kept locally, without a pull request.`,
      stopped: () => "The run stopped on an error. It can resume from the last finished step.",
      new: () => "This run has not started.",
    },
    reprendre: "Resume", appliquees: "Applied",
    signalerTitre: "Report an error",
    signalerIntro: "One error per line: the page, what is wrong, and the right information if you have it. The agent checks each point on primary sources, with the whole guide in context, then proposes corrections you review as for a watch. About 5 to 7 $.",
    signalerExemple: "03-stack/engines.md: vLLM 0.31 is no longer the minimum version, 0.33 fixes a security advisory.",
    signalerBouton: "Check and propose corrections",
    coutsTitre: "Costs",
    coutsIntro: total => `Computed from the usage the API returns, at list price (journal <code>metrics/usage.jsonl</code>). The Console's billing page stays the reference. Total: ${total}.`,
    colonnes: ["Calls", "Tokens in", "Out", "Cost"], parMois: "By month", mois: "Month", parPassage: "By run", passage: "Run",
  },
};
const langueSauvee = () => { try { return localStorage.getItem("vault-watch-langue"); } catch { return null; } };
let langue = TEXTES[langueSauvee()] ? langueSauvee() : (navigator.language || "en").startsWith("fr") ? "fr" : "en";
let T = TEXTES[langue];

const CLASSES = {
  running: "attention", review: "attention", publish: "attention", "pr-open": "attention",
  published: "ok", merged: "ok", stopped: "erreur",
};
// Nothing left to do: the card is dimmed
const FINIS = ["closed", "merged", "pr-closed", "nothing-applied", "not-published"];
const pastille = st => `<span class="pastille ${CLASSES[st] || "neutre"}">${T.statuts[st] || st}</span>`;

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-Vault-Watch": "1" },
  };
  const r = await fetch(path, opts).catch(() => { throw new Error(T.serveurArrete); });  // stopped (idle, closed)
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r.text();
}

// --- Header -------------------------------------------------------------------------------------------
let infos = null;
function entete() {
  document.documentElement.lang = langue;
  document.querySelectorAll("nav [data-nav]").forEach(a => a.textContent = T.nav[a.dataset.nav]);
  const liens = infos ? [infos.site, `https://github.com/${infos.repo}`, infos.agent]
    .map((url, i) => url && lienExt(url, `${T.liens[i]} ↗`)).filter(Boolean).join("") : "";
  $("#externes").innerHTML = `${liens}<span class="langues">${["fr", "en"].map(l =>
    `<button data-langue="${l}" class="${l === langue ? "actif" : ""}" aria-pressed="${l === langue}">${l.toUpperCase()}</button>`).join("")}</span>`;
  $("#externes").querySelectorAll("[data-langue]").forEach(b => b.onclick = () => {
    langue = b.dataset.langue;
    T = TEXTES[langue];
    try { localStorage.setItem("vault-watch-langue", langue); } catch { /* private window: per page only */ }
    entete();
    route();
  });
}

// --- Router --------------------------------------------------------------------------------------
async function route() {
  if (source) { source.close(); source = null; }
  clearTimeout(suivi);
  const h = location.hash.slice(1) || "/";
  document.querySelectorAll("nav [data-nav]").forEach(a =>
    a.classList.toggle("actif", h === "/" ? a.dataset.nav === "veilles" : h.startsWith(`/${a.dataset.nav}`)));
  page.innerHTML = `<p class="doux">${T.chargement}</p>`;
  try {
    if (h.startsWith("/run/")) await vueRun(decodeURIComponent(h.slice(5)));
    else if (h.startsWith("/verifier/")) await vueVerification(decodeURIComponent(h.slice(10)));
    else if (h === "/verifier") await vueVerifier();
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
  const [veilles, autres] = await Promise.all([api("/api/veilles"), api("/api/runs")]);
  page.innerHTML = `
    <h1>${T.veilles}</h1>
    <p class="sous-titre">${T.veillesIntro}</p>
    ${veilles.map(v => {
      const r = v.run, lien = `#/run/${encodeURIComponent(r.thread)}`;
      const action = r.status === "closed" ? ""
        : r.status === "new" ? `<button class="principal" data-analyser="${v.number}">${T.analyser}</button>`
        : r.status === "pr-open" ? lienExt(r.pr_url, `<button class="principal">${T.fusionner}</button>`)
        : `<a href="${lien}"><button${["review", "publish", "stopped"].includes(r.status) ? ' class="principal"' : ""}>${
            T.boutons[r.status] || T.details}</button></a>`;
      return `<div class="carte ligne${FINIS.includes(r.status) ? " finie" : ""}">
        <div class="pousse">
          <b>#${v.number}</b> ${esc(v.title)} ${v.urgent ? `<span class="pastille ${FINIS.includes(r.status) ? "neutre" : "erreur"}">urgent</span>` : ""}
          <div class="doux petit">${v.date} · ${T.issue(v.state === "open")}${
            !["new", "closed"].includes(r.status) ? ` · ${T.compte(r.corrections, r.applied)} · ${dollars(r.cost)}` : ""}${
            r.pr_url ? ` · ${lienExt(r.pr_url, "pull request")}` : ""}</div>
        </div>
        ${pastille(r.status)} ${action}
      </div>`;
    }).join("") || `<p class="doux">${T.aucuneVeille}</p>`}
    ${autres.length ? `<h2>${T.autres}</h2>${autres.map(r => `
      <div class="carte ligne${FINIS.includes(r.status) ? " finie" : ""}"><div class="pousse"><b>${esc(r.thread)}</b>
        <div class="doux petit">${esc(r.source)} · ${r.corrections} correction(s) · ${dollars(r.cost)}${
          r.pr_url ? ` · ${lienExt(r.pr_url, "pull request")}` : ""}</div></div>
        ${pastille(r.status)} <a href="#/run/${encodeURIComponent(r.thread)}"><button>${T.details}</button></a></div>`).join("")}` : ""}`;
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
    <p class="sous-titre">${r.as_of ? `${T.veilleJusqua(r.as_of)} · ` : ""}${esc(r.usage)}</p>`;
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
      <ol class="etapes" id="etapes">${etapes.map(s => `<li data-etape="${s}">${T.etapes[s]}</li>`).join("")}</ol>
      <p class="doux petit" id="avancement"></p>
    </div>
    <p class="doux petit">${T.peutFermer}</p>`;
  const maj = (cout) => {
    let encours = true;
    page.querySelectorAll("#etapes li").forEach(li => {
      const fait = faits.has(li.dataset.etape);
      li.classList.toggle("fait", fait);
      li.classList.toggle("encours", !fait && encours && (encours = false, true));
    });
    const min = Math.round((Date.now() / 1000 - r.job.started) / 60);
    $("#avancement").textContent = T.avancement(min, dollars(cout));
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
    .map(i => i.url ? lienExt(i.url, esc(i.title)) : esc(i.title)).join(" · ");
  return `<div class="carte correction${valide ? "" : " refusee"}">
    <input type="checkbox" data-id="${c.id}" data-groupe="${c.group}" ${valide ? "checked" : "disabled"} aria-label="${T.appliquerId(c.id)}">
    <div>
      <div class="entete"><b>${c.id}</b><span class="pastille ${c.severity}">${c.severity}</span><code>${esc(c.page)}</code>
        ${valide ? "" : `<span class="pastille erreur">${esc(c.check)}</span>`}</div>
      <p>${esc(c.rationale)}</p>
      ${c.review ? `<p class="doux petit">${T.relectureGlobale} : ${esc(c.review)}</p>` : ""}
      <div class="diff avant" lang="fr">${av}</div>
      <div class="diff apres" lang="fr">${ap}</div>
      <div class="doux petit">${T.dapres} ${sources || "—"}${c.source_url ? ` · ${lienExt(c.source_url, "source")}` : ""}</div>
    </div>
  </div>`;
}

function vueRelecture(r, titre) {
  const num = id => Number(id.slice(1));
  const groupes = {};
  for (const c of [...r.corrections].sort((a, b) => num(a.group) - num(b.group) || num(a.id) - num(b.id)))
    (groupes[c.group] ||= []).push(c);
  const casses = new Set(r.corrections.filter(c => c.check !== "ok").map(c => c.group));
  const chiffres = [Object.values(r.triage).reduce((a, b) => a + b, 0), r.triage.correct, r.corrections.length, r.additions.length];
  page.innerHTML = `${titre}
    <div class="chiffres">${chiffres.map((n, i) => `<div><b>${n}</b>${T.chiffresRelecture[i]}</div>`).join("")}</div>
    <h2>${T.corrections}</h2>
    <p class="doux petit">${T.aideRelecture}</p>
    ${Object.entries(groupes).map(([g, cs]) => cs.length > 1
      ? `<div class="groupe"><p class="doux petit">${T.groupe(g)}${casses.has(g) ? T.groupeEcarte : ""}</p>${cs.map(c => carteCorrection(c, r)).join("")}</div>`
      : carteCorrection(cs[0], r)).join("") || `<p class="doux">${T.aucuneCorrection}</p>`}
    <details><summary>${T.pistes(r.additions.length)}</summary>
      <ul>${r.additions.map(a => `<li>${a.url ? lienExt(a.url, esc(a.title)) : esc(a.title)} : ${esc(a.reason)}</li>`).join("") || `<li>${T.aucune}</li>`}</ul></details>
    <details><summary>${T.remarque(r.findings.length)}</summary>
      <ul>${r.findings.map(f => `<li>${esc(f)}</li>`).join("") || `<li>${T.rien}</li>`}</ul>
      ${r.findings.length ? `<p class="doux petit">${T.remarqueAide}</p>` : ""}</details>
    <details><summary>${T.affirmations(r.claims_due.length)}</summary>
      <ul>${r.claims_due.map(c => `<li>${esc(c.recheckBy)} <code>${esc(c.page)}</code> : ${esc(c.claim)}</li>`).join("") || `<li>${T.aucune}</li>`}</ul></details>
    <p class="petit"><a href="/api/runs/${encodeURIComponent(r.thread)}/rapport" target="_blank">${T.rapport}</a></p>
    <div class="barre">
      <button id="rien">${T.neRienAppliquer}</button>
      <button class="principal" id="appliquer"></button>
    </div>`;
  const cases = [...page.querySelectorAll(".correction input")];
  cases.filter(i => casses.has(i.dataset.groupe)).forEach(i => { i.checked = false; i.disabled = true; });
  const compte = () => {
    const n = cases.filter(i => i.checked).length;
    $("#appliquer").textContent = T.appliquerN(n);
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
  $("#rien").onclick = () => confirm(T.confirmerRien) && envoyer("none");
}

async function vuePublication(r, titre) {
  const p = { mirror_problems: [], link_problems: [], ...r.pause };
  const diff = await api(`/api/runs/${encodeURIComponent(r.thread)}/diff`).catch(() => "");
  const couleur = l => l.startsWith("+") && !l.startsWith("+++") ? "plus" : l.startsWith("-") && !l.startsWith("---") ? "moins" : "";
  const chiffres = [r.applied.length, r.mirrored.length, p.audit_ok ? "OK" : T.echec, p.link_problems.length];
  page.innerHTML = `${titre}
    <div class="chiffres">${chiffres.map((n, i) => `<div><b>${n}</b>${T.chiffresPublication[i]}</div>`).join("")}</div>
    <div class="carte">
      <p>${T.branchePrete(esc(p.branch))}</p>
      ${p.audit_ok ? "" : `<p class="erreur-texte">${T.auditsRouges}</p><pre>${esc(r.audit_log)}</pre>`}
      ${p.mirror_problems.length ? `<p><b>${T.traduction}</b></p><ul>${p.mirror_problems.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${p.link_problems.length ? `<p><b>${T.liensTitre}</b> ${T.liensNew}</p><ul>${p.link_problems.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="doux">${T.liensOk}</p>`}
    </div>
    <details open><summary>${T.modifications}</summary>
      <pre>${diff.split("\n").map(l => `<span class="${couleur(l)}">${esc(l)}</span>`).join("\n") || esc(p.diffstat)}</pre></details>
    <div class="barre">
      <button id="non">${T.nePasPublier}</button>
      <button class="principal" id="oui">${T.publier}</button>
    </div>`;
  const envoyer = async go => {
    page.querySelectorAll(".barre button").forEach(b => b.disabled = true);
    await api(`/api/runs/${encodeURIComponent(r.thread)}/publish`, { go });
    route();
  };
  $("#oui").onclick = () => envoyer(true);
  $("#non").onclick = () => confirm(T.confirmerNon) && envoyer(false);
}

function vueFin(r, titre) {
  const pr = r.pr_url ? lienExt(r.pr_url, "pull request") : "";
  const texte = (T.fin[r.status] || (() => ""))(pr, esc(r.branch));
  page.innerHTML = `${titre}
    <div class="carte"><p>${texte}</p>
      ${r.error ? `<p class="erreur-texte">${esc(r.error)}</p>` : ""}
      ${r.status === "stopped" ? `<button class="principal" id="reprendre">${T.reprendre}</button>` : ""}</div>
    ${r.applied.length ? `<p>${T.appliquees} : ${r.applied.join(", ")}</p>` : ""}
    ${r.report_path ? `<p class="petit"><a href="/api/runs/${encodeURIComponent(r.thread)}/rapport" target="_blank">${T.rapport}</a></p>` : ""}`;
  const b = $("#reprendre");
  if (b) b.onclick = async () => { b.disabled = true; await api(`/api/runs/${encodeURIComponent(r.thread)}/resume`, {}); route(); };
}

// --- Check the guide ---------------------------------------------------------------------------------------
let suivi = null;  // timer following a running check
const etatVerif = p => {
  const V = T.verif, [texte, classe] = {
    running: [V.enCours, "attention"], "to-handle": [V.aTraiter(p.counts.open), "attention"],
    handled: [V.traitee, "ok"], clear: [V.ok, "ok"],
  }[p.status] || [p.status, "neutre"];
  return `<span class="pastille ${classe}">${texte}</span>`;
};

async function vueVerifier() {
  const [options, passes] = await Promise.all([api("/api/verifications/options"), api("/api/verifications")]);
  const V = T.verif, titres = Object.fromEntries(options.map(o => [o.id, o.title[langue]]));
  const prix = o => o.model ? (o.usd == null ? V.inconnu : `≈ ${dollars(o.usd)}`) : V.gratuit;
  page.innerHTML = `
    <h1>${V.titre}</h1>
    <p class="sous-titre">${V.intro}</p>
    ${options.map(o => `<label class="carte option">
      <input type="checkbox" data-check="${o.id}" ${o.model ? "" : "checked"}>
      <div>
        <div class="entete"><b>${esc(o.title[langue])}</b>
          <span class="pastille ${o.model ? "attention" : "ok"}">${prix(o)}</span>
          ${o.tokens ? `<span class="doux petit">${V.tokens(o.tokens)}</span>` : ""}</div>
        <p class="doux petit">${esc(o.what[langue])}</p>
        <p class="doux petit">${esc(o.note[langue])}${o.model ? ` · ${esc(o.model)}` : ""}${o.needs.length ? ` · ${V.necessite(o.needs.map(n => titres[n]).join(", "))}` : ""}</p>
      </div></label>`).join("")}
    <p><button class="principal" id="lancer"></button></p>
    <h2>${V.historique}</h2>
    ${passes.map(p => `<div class="carte ligne${["handled", "clear"].includes(p.status) ? " finie" : ""}"><div class="pousse"><b>${new Date(p.started * 1000).toLocaleString(langue)}</b>
        <div class="doux petit">${p.checks.map(c => esc(titres[c] || c)).join(" · ")} · ${dollars(p.cost)}</div>
        <div class="doux petit">${V.comptes(p.counts)}</div></div>
        ${etatVerif(p)}
        <a href="#/verifier/${encodeURIComponent(p.id)}"><button${p.status === "to-handle" ? ' class="principal"' : ""}>${p.status === "to-handle" ? V.traiter : T.details}</button></a></div>`).join("") || `<p class="doux">${V.aucune}</p>`}`;
  const cases = [...page.querySelectorAll("[data-check]")];
  const total = () => {
    const ids = new Set(cases.filter(c => c.checked).map(c => c.dataset.check));
    options.filter(o => ids.has(o.id)).forEach(o => o.needs.forEach(n => ids.add(n)));
    const usd = options.filter(o => ids.has(o.id)).reduce((s, o) => s + (o.usd || 0), 0);
    $("#lancer").textContent = V.lancer(dollars(usd));
    $("#lancer").disabled = ids.size === 0;
  };
  cases.forEach(c => c.onchange = total);
  total();
  $("#lancer").onclick = async () => {
    $("#lancer").disabled = true;
    const { id } = await api("/api/verifications", { checks: cases.filter(c => c.checked).map(c => c.dataset.check) });
    location.hash = `/verifier/${encodeURIComponent(id)}`;
  };
}

async function vueVerification(id) {
  clearTimeout(suivi);
  const [v, options] = await Promise.all([api(`/api/verifications/${encodeURIComponent(id)}`), api("/api/verifications/options")]);
  if (location.hash.slice(1) !== `/verifier/${id}`) return;  // left the page meanwhile
  const V = T.verif, titres = Object.fromEntries(options.map(o => [o.id, o.title[langue]]));
  const liste = (titre, items) => items && items.length ? `<details><summary>${titre} (${items.length})</summary><ul>${items.map(x => `<li>${x}</li>`).join("")}</ul></details>` : "";
  page.innerHTML = `
    <h1>${V.titre} · ${new Date(v.started * 1000).toLocaleString(langue)} ${etatVerif(v)}</h1>
    <p class="sous-titre">${V.cout(dollars(v.cost))} · ${V.comptes(v.counts)}</p>
    ${v.error ? `<p class="erreur-texte">${esc(v.error)}</p>` : ""}
    ${v.checks.map(c => {
      const r = v.results[c];
      const etat = !r ? `<span class="pastille neutre">${v.running ? V.attente : "—"}</span>`
        : r.summary?.startsWith("could not run") ? `<span class="pastille erreur">${V.echec}</span>`
        : `<span class="pastille ${r.ok ? "ok" : "attention"}">${r.ok ? V.ok : V.problemes}</span>`;
      return `<div class="carte"><div class="entete"><b>${esc(titres[c] || c)}</b>${etat}</div>
        ${r ? `<p class="doux petit">${esc(r.summary)}</p>
          ${liste(V.morts, (r.dead || []).map(d => `${lienExt(d.url, esc(d.url))} — ${esc(d.status)} ${esc(d.code ?? "")} (${esc(d.pages.join(", "))})`))}
          ${liste(V.bloques, (r.blocked || []).map(d => `${lienExt(d.url, esc(d.url))} (${esc(d.pages.join(", "))})`))}
          ${liste(V.affirmations, (r.claims || []).map(x => `${esc(x.recheckBy)} <code>${esc(x.page)}</code> : ${esc(x.claim)}`))}
          ${liste(V.pagesDues, (r.pages_due || []).map(esc))}
          ${r.log ? `<details><summary>${V.journal}</summary><pre>${esc(r.log)}</pre></details>` : ""}
          ${(r.findings || []).length ? `${r.fixable ? "" : `<p class="doux petit">${V.nonCorrigeable}</p>`}<ul class="pistes">${r.findings.map(f => piste(f, r.fixable)).join("")}</ul>` : ""}` : ""}
      </div>`;
    }).join("")}
    <div class="barre">
      <button id="tout">${V.toutCocher}</button><button id="rien">${V.rienCocher}</button>
      <button id="ecarter"></button>
      <button class="principal" id="fix"></button>
    </div>`;
  // A finding is open (checkbox), sent to a fix run (link to the run) or dismissed (can be reopened)
  function piste(f, corrigeable) {
    const h = v.handled[f];
    if (h?.status === "fix") return `<li class="traitee"><span class="pastille ok">${V.envoyee}</span> <a href="#/run/${encodeURIComponent(h.thread)}">${esc(h.thread)}</a> · ${esc(f)}</li>`;
    if (h?.status === "dismissed") return `<li class="traitee"><span class="pastille neutre">${V.ecartee}</span> <button class="petit-bouton" data-retablir="${esc(f)}">${V.retablir}</button> ${esc(f)}</li>`;
    return `<li><label><input type="checkbox" data-piste="${esc(f)}" data-corrigeable="${corrigeable}"> ${esc(f)}</label></li>`;
  }
  const cases = [...page.querySelectorAll("[data-piste]")];
  const coches = () => cases.filter(c => c.checked);
  const compte = () => {
    const n = coches().filter(c => c.dataset.corrigeable === "true").length, e = coches().length;
    $("#fix").textContent = V.creerFix(n); $("#fix").disabled = n === 0 || v.running;
    $("#ecarter").textContent = V.ecarter(e); $("#ecarter").disabled = e === 0 || v.running;
  };
  cases.forEach(c => c.onchange = compte);
  $("#tout").onclick = () => { cases.forEach(c => c.checked = true); compte(); };
  $("#rien").onclick = () => { cases.forEach(c => c.checked = false); compte(); };
  compte();
  const pistes = (findings, status) => api(`/api/verifications/${encodeURIComponent(id)}/pistes`, { findings, status }).then(() => vueVerification(id));
  page.querySelectorAll("[data-retablir]").forEach(b => b.onclick = () => pistes([b.dataset.retablir], "open"));
  if (!cases.length) page.querySelector(".barre").remove();
  else {
    $("#ecarter").onclick = () => pistes(coches().map(c => c.dataset.piste), "dismissed");
    $("#fix").onclick = async () => {
      $("#fix").disabled = true;
      const text = coches().filter(c => c.dataset.corrigeable === "true").map(c => c.dataset.piste).join("\n");
      const { thread } = await api("/api/fix", { text, verification: id });
      location.hash = `/run/${encodeURIComponent(thread)}`;
    };
  }
  if (v.running) suivi = setTimeout(() => vueVerification(id).catch(() => {}), 3000);
}

// --- Report errors -----------------------------------------------------------------------------------
function vueSignaler() {
  page.innerHTML = `
    <h1>${T.signalerTitre}</h1>
    <p class="sous-titre">${T.signalerIntro}</p>
    <textarea id="texte" placeholder="${esc(T.signalerExemple)}"></textarea>
    <p><button class="principal" id="envoyer">${T.signalerBouton}</button></p>`;
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
  const nombre = n => n.toLocaleString(langue);
  const tableau = (rows, titre) => `<table><thead><tr><th>${titre}</th>${T.colonnes.map(x => `<th class="nombre">${x}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(r => `<tr><td>${esc(r.key)}</td><td class="nombre">${r.calls}</td><td class="nombre">${nombre(r.in)}</td><td class="nombre">${nombre(r.out)}</td><td class="nombre">${dollars(r.cost)}</td></tr>`).join("")}</tbody></table>`;
  const total = c.month.reduce((s, r) => s + r.cost, 0);
  page.innerHTML = `
    <h1>${T.coutsTitre}</h1>
    <p class="sous-titre">${T.coutsIntro(dollars(total))}</p>
    <h2>${T.parMois}</h2><div class="carte">${tableau(c.month, T.mois)}</div>
    <h2>${T.parPassage}</h2><div class="carte">${tableau([...c.run].reverse(), T.passage)}</div>`;
}

entete();
api("/api/infos").then(i => { infos = i; entete(); }).catch(() => {});
route();
