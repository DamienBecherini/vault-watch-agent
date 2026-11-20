/* vault-watch: the Settings, a window over the current page (the gear of the header, or the address #/settings),
   loaded before app.js, which owns the router, the texts and the helpers used here ($, api, esc, T, info, route).
   The page under it is not drawn again when the window closes, unless the engine changed (the costs shown follow
   it). Close, Cancel, the Escape key or a click outside close it; with changes not saved, only Cancel does (it
   drops them), so a stray click loses nothing. What it edits is the settings file of the server (config.py):
   the engine that calls the model (Claude Code on a subscription, or the API), where the API key is (a reference,
   never the key) and the model of each role. A change applies to the next run.
   Layout after the Settings of dl-sub-dub: the categories at the left, one page each, Claude Code found on the
   machine proposed in a framed box. */

const SETTINGS_TEXTS = {
  fr: {
    title: "Réglages", open: "Réglages", save: "Enregistrer", cancel: "Annuler", close: "Fermer",
    unsaved: "Modifications non enregistrées : Enregistrer, ou Annuler pour les abandonner.", loading: "Chargement…",
    saved: "Enregistré. S'applique au prochain passage.", modified: "modifié, pas encore enregistré",
    categories: "Catégories", cat: { engine: "Moteur", models: "Modèles et effort", prices: "Prix", guide: "Guide" },
    engineHelp: "Qui appelle le modèle. Un changement s'applique au prochain passage ; un passage en cours garde son moteur.",
    found: plan => `Claude Code trouvé sur cette machine (abonnement ${plan})`,
    foundHelp: "Les appels passent par ton abonnement Claude : pas de clé d'API, rien de facturé. L'usage compte dans les limites de l'abonnement.",
    use: "Utiliser Claude Code", inUse: "Utilisé",
    missing: "Claude Code n'est pas installé sur cette machine (ou pas dans le PATH).",
    signedOut: "Claude Code est installé mais pas connecté : lance <code>claude</code> une fois pour te connecter.",
    noPlan: "Claude Code est connecté sans abonnement (compte Console ou clé) : ses appels seraient facturés, il n'est donc pas proposé.",
    engines: { "": "Automatique", "claude-code": "Claude Code (abonnement)", api: "API (clé, facturée au token)", openai: "Serveur compatible OpenAI" },
    engineLabel: "Moteur",
    autoHelp: "Automatique : Claude Code s'il est connecté à un abonnement, sinon l'API.",
    next: name => `Moteur du prochain passage : <b>${name}</b>`,
    names: { "claude-code": "Claude Code, sur l'abonnement", api: "API Claude, facturée au token", openai: "un serveur compatible OpenAI" },
    server: {
      title: "Serveur compatible OpenAI",
      help: "Un serveur qui répond à <code>/v1/chat/completions</code> : un fournisseur hébergé, ou un modèle sur ta machine (llama.cpp, vLLM, Ollama, LM Studio).",
      url: "Adresse", urlHint: "http://127.0.0.1:8080/v1",
      key: "Référence de la clé du serveur", keyHint: "vide si le serveur n'en demande pas",
      context: "Fenêtre du modèle (tokens)", contextHelp: "Quand le serveur ne la donne pas. Un guide plus grand est relu chapitre par chapitre.",
      structured: "Réponse en JSON", structuredOptions: { auto: "automatique", native: "schéma imposé par le serveur", instruction: "schéma dans les consignes" },
      billing: "Facturation", billingOptions: { token: "au token (fixe le prix du modèle dans Prix)", local: "modèle local, rien de facturé" },
      effort: "Envoyer l'effort (reasoning_effort), pour les modèles qui le prennent",
      searxng: "Adresse SearXNG (recherche web)", searxngHelp: "Sans elle, le modèle lit les pages dont il a l'adresse mais ne cherche pas : les étapes qui vérifient sur le web le diront.",
      list: "Lire la liste des modèles", listing: "Lecture…", listed: n => `${n} modèle(s) sur le serveur.`,
      modelHint: "identifiant du modèle sur le serveur",
    },
    forced: v => `Imposé par la variable d'environnement <code>VAULT_WATCH_ENGINE=${v}</code>, qui passe avant ce réglage.`,
    noFallback: "L'agent ne bascule jamais de lui-même sur l'API : si une limite de l'abonnement est atteinte, le passage s'arrête et se reprend plus tard.",
    keyTitle: "Clé de l'API",
    keyHelp: "La clé n'est jamais enregistrée ici. Indique où elle se trouve :",
    keyForms: ["<code>env:NOM</code> : une variable d'environnement", "<code>sops:fichier#NOM</code> : un champ d'un fichier chiffré par sops, déchiffré au moment de l'appel",
      "<code>file:chemin</code> : un fichier qui ne contient que la clé"],
    keyLabel: "Référence de la clé", keyOnlyApi: "Elle ne sert qu'avec le moteur API.",
    keyFound: "clé trouvée", keyAbsent: "aucune clé à cette référence", keyEmpty: "aucune référence",
    keyUnchecked: "vérifiée à l'enregistrement",
    keyPlain: "Ceci n'est pas une référence. Ne colle jamais la clé ici : donne env:NOM, sops:fichier#NOM ou file:chemin.",
    modelsHelp: "Le modèle et l'effort de chaque rôle, quel que soit le moteur. Les mesures de coût et de qualité de la documentation ont été faites avec les modèles par défaut et l'effort normal.",
    modelsFromApi: "Liste des modèles lue sur l'API avec ta clé.",
    modelsKnown: e => `Liste de l'API illisible (${e}) : modèles connus de l'agent seulement.`,
    modelsLoading: "Lecture de la liste des modèles…",
    unpriced: "prix inconnu de l'agent : coûts comptés à 0",
    unpricedHelp: "Ce modèle n'a pas de prix dans l'agent : le journal et les estimations le compteront à 0 $. Rien ne change sur l'abonnement.",
    effortLabel: "Effort", efforts: { lower: "Plus bas", normal: "Normal", higher: "Plus haut" },
    effortHelp: "L'effort est fixé étape par étape dans le code ; ce réglage décale chaque étape d'un cran. Plus haut : plus de réflexion, plus de tokens (et de limites d'abonnement ou de coût), plus lent.",
    stepsOf: "Ce que donne chaque étape :",
    stepsApart: "Régler une étape à part", stepsApartCount: n => `${n} étape(s) à part`,
    stepsApartHelp: "Une étape peut tourner sur un autre modèle que son rôle, ou à un effort fixé : par exemple le compactage sur le modèle le plus fort, les veilles inchangées. Un effort choisi ici s'applique tel quel, sans le décalage du rôle.",
    asRole: "comme le rôle", stepModel: "Modèle", stepEffort: "Effort", stepServerHint: "comme le rôle (ou l'identifiant d'un modèle du serveur)",
    stepNames: { triage: "tri", proposals: "propositions", crosscheck: "relecture croisée", fix: "correction des erreurs signalées", coherence: "cohérence du guide", compaction: "ce qui alourdit le guide", compact: "allègements proposés", news: "pistes de nouveautés", add: "ajouts vérifiés sur le web",
      claims: "affirmations datées", checks: "vérifications", deadlinks: "liens morts", mirror: "miroir", translation: "contrôle des traductions", "fix-translation": "correction des traductions" },
    levels: { low: "bas", medium: "moyen", high: "élevé", xhigh: "très élevé", max: "maximal" },
    roles: { reasoning: "Raisonnement", translator: "Traduction" },
    roleHelp: { reasoning: "Tri de la veille, propositions, relecture croisée, vérifications du guide.",
      translator: "Miroir anglais et contrôle des traductions." },
    byDefault: "par défaut",
    prices: {
      help: "Le prix de chaque modèle, en dollars par million de tokens, et d'où il vient. Il sert au journal des coûts et aux estimations ; sur l'abonnement, rien n'est facturé.",
      cols: ["Modèle", "Entrée", "Sortie", "Lecture cache", "Écriture cache", "Origine", ""],
      origin: { set: "fixé ici", fetched: d => `liste du ${d}`, default: d => `par défaut (${d})`, none: "aucun prix : compté 0 $" },
      unsaved: "à enregistrer", inUse: "utilisé",
      set: "Fixer", reset: "Revenir au prix par défaut", ok: "OK", cancel: "Annuler", invalid: "Quatre nombres positifs ou nuls.",
      listTitle: "Liste publique des prix",
      listHelp: src => `La liste de LiteLLM (<a href="${src}" target="_blank" rel="noopener">fichier public</a>), lue seulement quand tu la demandes. Tes prix fixés ici passent toujours avant.`,
      listNone: "Aucune liste lue pour l'instant : les prix par défaut de l'agent s'appliquent.",
      listOf: (d, n) => `Liste du ${d} en place (${n} modèles).`,
      fetch: "Lire la liste", fetching: "Lecture…", apply: "Remplacer par cette liste", applied: "Liste en place.",
      changes: (d, n) => `Liste du ${d} (${n} modèles Claude). Ce qui changerait :`, noChange: "Elle ne change aucun prix.",
      newModels: n => `${n} modèle(s) sans prix aujourd'hui`, estimated: "prix du cache estimés (0,1 × et 1,25 × l'entrée) pour : ",
    },
    guide: {
      help: "Ce que le guide déclare dans son manifeste. En lecture seule : se modifie dans le fichier du guide, puis s'applique au prochain passage.",
      noManifest: m => `Pas de <code>${m}</code> dans le dossier du guide : il est lu comme le guide IA on-prem (pages en français, miroir <code>en/</code>, ses scripts). <code>vault-watch init</code> en écrira un.`,
      fromManifest: m => `Lu dans <code>${m}</code>.`,
      name: "Nom", about: "Sujet", language: "Langue des pages", pages: n => `${n} page(s)`,
      repository: "Dépôt", local: "aucun : guide local (pas d'issue, pas de pull request)", site: "Site", base: "Branche",
      parts: "Ses parties", provided: "fournie", missing: "absente",
      mirror: "Miroir de traduction", mirrorOn: m => `${m.language_name}, sous <code>${m.folder}</code>`,
      mirrorOff: "pas d'étape de traduction ni de contrôle des traductions",
      modified: "Date de modification", modifiedOn: f => `champ <code>${f}</code> mis à jour par une correction`,
      modifiedOff: "les dates des pages ne changent pas",
      watch: "Veille", watchSources: { none: "vérifications et erreurs signalées seulement",
        issues: w => `issues ${w.forge} d'étiquette « ${w.label || "veille"} »`, file: w => `fichier <code>${w.path}</code>`, feeds: w => `collectée par l'agent depuis <code>${w.feeds}</code>` },
      brief: "Consignes de veille", policy: "Politique de traduction", rulesOff: "celles de l'agent s'appliquent",
      audits: "Contrôles du guide", claims: "Affirmations datées", sources: "Audit des sources", floors: "Versions minimales",
      checkOff: "« non vérifié » à chaque passage, jamais un échec",
      budget: "Budget de contexte", tokens: n => `${n.toLocaleString()} tokens`, budgetOff: "aucune limite fixée",
    },
  },
  en: {
    title: "Settings", open: "Settings", save: "Save", cancel: "Cancel", close: "Close",
    unsaved: "Changes not saved: Save, or Cancel to drop them.", loading: "Loading…",
    saved: "Saved. Applies to the next run.", modified: "changed, not saved yet",
    categories: "Categories", cat: { engine: "Engine", models: "Models and effort", prices: "Prices", guide: "Guide" },
    engineHelp: "What calls the model. A change applies to the next run; a run in progress keeps its engine.",
    found: plan => `Claude Code found on this machine (${plan} subscription)`,
    foundHelp: "The calls go through your Claude subscription: no API key, nothing billed. The usage counts in the limits of the subscription.",
    use: "Use Claude Code", inUse: "In use",
    missing: "Claude Code is not installed on this machine (or not in the PATH).",
    signedOut: "Claude Code is installed but not signed in: run <code>claude</code> once and sign in.",
    noPlan: "Claude Code is signed in without a subscription (a Console account or a key): its calls would be billed, so it is not proposed.",
    engines: { "": "Automatic", "claude-code": "Claude Code (subscription)", api: "API (key, billed per token)", openai: "OpenAI-compatible server" },
    engineLabel: "Engine",
    autoHelp: "Automatic: Claude Code when it is signed in with a subscription, otherwise the API.",
    next: name => `Engine of the next run: <b>${name}</b>`,
    names: { "claude-code": "Claude Code, on the subscription", api: "Claude API, billed per token" },
    server: {
      title: "OpenAI-compatible server",
      help: "A server that answers <code>/v1/chat/completions</code>: a hosted provider, or a model on your machine (llama.cpp, vLLM, Ollama, LM Studio).",
      url: "Address", urlHint: "http://127.0.0.1:8080/v1",
      key: "Reference of the server's key", keyHint: "empty if the server asks for none",
      context: "Model window (tokens)", contextHelp: "When the server does not give it. A bigger guide is cross-checked chapter by chapter.",
      structured: "JSON answer", structuredOptions: { auto: "automatic", native: "schema enforced by the server", instruction: "schema in the instructions" },
      billing: "Billing", billingOptions: { token: "per token (set the model's price in Prices)", local: "local model, nothing billed" },
      effort: "Send the effort (reasoning_effort), for the models that take it",
      searxng: "SearXNG address (web search)", searxngHelp: "Without it the model reads the pages it has the address of but cannot search: the steps that check on the web will say so.",
      list: "Read the list of models", listing: "Reading…", listed: n => `${n} model(s) on the server.`,
      modelHint: "the model's id on the server",
    },
    forced: v => `Set by the environment variable <code>VAULT_WATCH_ENGINE=${v}</code>, which comes before this setting.`,
    noFallback: "The agent never falls back to the API on its own: when a limit of the subscription is reached, the run stops and is resumed later.",
    keyTitle: "API key",
    keyHelp: "The key is never stored here. Say where it is:",
    keyForms: ["<code>env:NAME</code>: an environment variable", "<code>sops:file#NAME</code>: a field of a file encrypted with sops, decrypted when a call is made",
      "<code>file:path</code>: a file that holds the key alone"],
    keyLabel: "Reference of the key", keyOnlyApi: "It is only used with the API engine.",
    keyFound: "key found", keyAbsent: "no key at this reference", keyEmpty: "no reference",
    keyUnchecked: "checked when saved",
    keyPlain: "This is not a reference. Never paste the key here: give env:NAME, sops:file#NAME or file:path.",
    modelsHelp: "The model and the effort of each role, whatever the engine. The cost and quality figures of the documentation were measured with the default models at the normal effort.",
    modelsFromApi: "List of the models read from the API with your key.",
    modelsKnown: e => `The list of the API could not be read (${e}): the models the agent knows only.`,
    modelsLoading: "Reading the list of the models…",
    unpriced: "price unknown to the agent: counted at 0",
    unpricedHelp: "The agent has no price for this model: the journal and the estimates will count it at 0 $. Nothing changes on the subscription.",
    effortLabel: "Effort", efforts: { lower: "Lower", normal: "Normal", higher: "Higher" },
    effortHelp: "The effort is set step by step in the code; this setting moves every step one level. Higher: more thinking, more tokens (and more of the subscription's limits or of the cost), slower.",
    stepsOf: "What each step then runs at:",
    stepsApart: "Set a step apart", stepsApartCount: n => `${n} step(s) set apart`,
    stepsApartHelp: "A step can run on another model than its role, or at a set effort: the compaction on the strongest model, for instance, and the watches unchanged. An effort chosen here applies as it is, without the role's shift.",
    asRole: "as the role", stepModel: "Model", stepEffort: "Effort", stepServerHint: "as the role (or the id of a model of the server)",
    stepNames: { triage: "triage", proposals: "proposals", crosscheck: "cross-check", fix: "fixing reported errors", coherence: "consistency of the guide", compaction: "what makes the guide heavy", compact: "trims proposed", news: "leads of what is new", add: "additions checked on the web",
      claims: "dated claims", checks: "checks", deadlinks: "dead links", mirror: "mirror", translation: "translation checks", "fix-translation": "fixing translations" },
    levels: { low: "low", medium: "medium", high: "high", xhigh: "extra high", max: "max" },
    roles: { reasoning: "Reasoning", translator: "Translation" },
    roleHelp: { reasoning: "Triage of the watch, proposals, cross-check, checks of the guide.",
      translator: "English mirror and translation checks." },
    byDefault: "default",
    prices: {
      help: "The price of each model, in dollars per million tokens, and where it comes from. The cost journal and the estimates use it; on the subscription, nothing is billed.",
      cols: ["Model", "Input", "Output", "Cache read", "Cache write", "Origin", ""],
      origin: { set: "set here", fetched: d => `list of ${d}`, default: d => `default (${d})`, none: "no price: counted 0 $" },
      unsaved: "to save", inUse: "in use",
      set: "Set", reset: "Back to the default price", ok: "OK", cancel: "Cancel", invalid: "Four numbers, 0 or more.",
      listTitle: "Public price list",
      listHelp: src => `LiteLLM's list (<a href="${src}" target="_blank" rel="noopener">public file</a>), read only when you ask. Your prices set here always come first.`,
      listNone: "No list read yet: the agent's default prices apply.",
      listOf: (d, n) => `List of ${d} in place (${n} models).`,
      fetch: "Read the list", fetching: "Reading…", apply: "Replace with this list", applied: "List in place.",
      changes: (d, n) => `List of ${d} (${n} Claude models). What would change:`, noChange: "It changes no price.",
      newModels: n => `${n} model(s) without a price today`, estimated: "cache prices estimated (0.1 × and 1.25 × input) for: ",
    },
    guide: {
      help: "What the guide declares in its manifest. Read-only: it changes in the guide's file, and applies to the next run.",
      noManifest: m => `No <code>${m}</code> in the guide's folder: it is read as the IA on-prem guide (French pages, an <code>en/</code> mirror, its scripts). <code>vault-watch init</code> will write one.`,
      fromManifest: m => `Read from <code>${m}</code>.`,
      name: "Name", about: "Subject", language: "Language of the pages", pages: n => `${n} page(s)`,
      repository: "Repository", local: "none: a local guide (no issue, no pull request)", site: "Site", base: "Branch",
      parts: "Its parts", provided: "provided", missing: "missing",
      mirror: "Translation mirror", mirrorOn: m => `${m.language_name}, under <code>${m.folder}</code>`,
      mirrorOff: "no translation step and no translation check",
      modified: "Modified date", modifiedOn: f => `field <code>${f}</code> updated by a correction`,
      modifiedOff: "the dates of the pages do not change",
      watch: "Watch", watchSources: { none: "checks and reported errors only",
        issues: w => `${w.forge} issues labelled « ${w.label || "veille"} »`, file: w => `file <code>${w.path}</code>`, feeds: w => `collected by the agent from <code>${w.feeds}</code>` },
      brief: "Watch brief", policy: "Translation policy", rulesOff: "the agent's own apply",
      audits: "Guide audits", claims: "Dated claims", sources: "Source audit", floors: "Version floors",
      checkOff: "« not checked » in every run, never a failure",
      budget: "Context budget", tokens: n => `${n.toLocaleString()} tokens`, budgetOff: "no limit set",
    },
  },
};

const SETTINGS_ICONS = {
  gear: `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></svg>`,
  engine: `<svg viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4"/></svg>`,
  models: `<svg viewBox="0 0 24 24"><path d="M12 3l8 4.5-8 4.5-8-4.5z"/><path d="M4 12l8 4.5 8-4.5M4 16.5L12 21l8-4.5"/></svg>`,
  prices: `<svg viewBox="0 0 24 24"><path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><circle cx="7.5" cy="7.5" r="1.5"/></svg>`,
  guide: `<svg viewBox="0 0 24 24"><path d="M4 5a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2z"/><path d="M4 21V5M8 7h6"/></svg>`,
};

const KEY_REFERENCES = ["env:", "sops:", "file:"];
const modelName = m => m.replace(/^claude-/, "").replace(/-(\d+)-(\d+)$/, " $1.$2").replace(/^./, c => c.toUpperCase());
let settingsCategory = "engine";  // the category shown, kept across redraws

let settingsEngine = null;         // the engine in use when the window opened: the page is drawn again if it changed
let settingsChanged = () => false; // whether the window holds changes not saved
let settingsOpening = 0;           // counts the openings: an answer of the server for an earlier one is dropped

/* Opens the window over the current page. */
async function openSettings() {
  let dialog = $("#settings-dialog");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "settings-dialog";
    dialog.className = "settings-dialog";
    document.body.appendChild(dialog);
    const keep = () => { const m = $("#settings-message"); if (m) m.innerHTML = `<span class="attention-text">${T.settings.unsaved}</span>`; };
    dialog.addEventListener("click", e => { if (e.target === dialog) settingsChanged() ? keep() : dialog.close(); });   // a click outside
    dialog.addEventListener("cancel", e => { if (settingsChanged()) { e.preventDefault(); keep(); } });                 // the Escape key
    // The browser can send `close` late, after the window opened again (seen in a tab not in sight): it must not
    // undo anything of the new opening, so the state of the window is reset when it opens, not here.
    dialog.addEventListener("close", () => {
      if (info && info.engine !== settingsEngine) { settingsEngine = info.engine; route(); }   // the costs shown follow the engine
    });
  }
  if (dialog.open) return;
  settingsEngine = info?.engine;
  settingsChanged = () => false;
  dialog.innerHTML = `<p class="muted settings-loading">${T.settings.loading}</p>`;
  dialog.showModal();
  try {
    const opening = ++settingsOpening, s = await api("/api/settings");
    if (opening === settingsOpening && dialog.open) drawSettings(s);   // closed, or opened again, meanwhile: not this answer
  } catch (e) {
    dialog.innerHTML = `<div class="settings-loading"><p class="error-text">${esc(e.message)}</p><button type="button" id="settings-cancel">${T.settings.close}</button></div>`;
    $("#settings-cancel").onclick = () => dialog.close();
  }
}

/* The « Guide » category: what the guide's manifest declares, read-only, and for each part it lacks what the agent
   then skips (a step, or « not checked » instead of a check). */
function guidePage(g) {
  const G = T.settings.guide;
  const row = (label, value) => `<div class="cfg-row"><span class="cfg-label">${label}</span><span>${value}</span></div>`;
  const part = (label, on, value, off) => `<li class="${on ? "" : "muted"}"><b>${label}</b> · ${on
    ? `<span class="ok-text">${G.provided}</span> — ${value}` : `${G.missing} — ${off}`}</li>`;
  const code = x => `<code>${esc(x)}</code>`;
  const w = g.watch, src = G.watchSources[w.source];
  return `<p class="muted small">${G.help}</p>
    <p class="${g.from_manifest ? "muted" : "attention-text"} small">${g.from_manifest ? G.fromManifest(g.manifest) : G.noManifest(g.manifest)}</p>
    ${row(G.name, esc(g.name))}
    ${g.description ? row(G.about, esc(g.description)) : ""}
    ${row(G.language, `${esc(g.language_name)} · ${G.pages(g.pages)}`)}
    ${row(G.repository, g.repository ? code(g.repository) + (g.forge === "gitea" ? ` · ${esc(g.forge_url)}` : "") : `<span class="muted">${G.local}</span>`)}
    ${g.site ? row(G.site, extLink(g.site, esc(g.site))) : ""}
    ${row(G.base, code(g.base_branch))}
    <h3 class="cfg-sub">${G.parts}</h3>
    <ul class="small cfg-list">
      ${g.mirrors.length ? g.mirrors.map(m => part(G.mirror, true, G.mirrorOn({ ...m, folder: esc(m.folder) }))).join("") : part(G.mirror, false, "", G.mirrorOff)}
      ${part(G.modified, !!g.modified_field, G.modifiedOn(esc(g.modified_field)), G.modifiedOff)}
      ${part(G.watch, w.source !== "none", typeof src === "function" ? src({ label: esc(w.label), path: esc(w.path), feeds: esc(w.feeds || ""), forge: g.forge === "gitea" ? "Gitea" : "GitHub" }) : "", G.watchSources.none)}
      ${part(G.brief, !!g.rules.brief, code(g.rules.brief), G.rulesOff)}
      ${part(G.policy, !!g.rules.translation_policy, code(g.rules.translation_policy), G.rulesOff)}
      ${part(G.audits, !!g.checks.audits, code(g.checks.audits), G.checkOff)}
      ${part(G.claims, !!g.checks.claims_due, code(g.checks.claims_due), G.checkOff)}
      ${part(G.sources, !!g.checks.sources, code(g.checks.sources), G.checkOff)}
      ${part(G.floors, !!g.checks.version_floors, code(g.checks.version_floors), G.checkOff)}
      ${part(G.budget, !!g.max_context_tokens, G.tokens(g.max_context_tokens || 0), G.budgetOff)}
    </ul>`;
}

/* `s`: the settings as the server holds them, with what it found (Claude Code, the key); the window edits a copy. */
function drawSettings(s, message = "") {
  const S = T.settings, cc = s.claude_code, page = $("#settings-dialog");   // `page`: the window, not the page under it
  // The OpenAI-compatible server's options: its defaults, then what is saved (`base` is what the draft starts from).
  const serverDefaults = (s.engine_options || {}).openai || {};
  const base = { ...serverDefaults, ...((s.engines || {}).openai || {}) };
  base.models = { reasoning: "", translator: "", ...(base.models || {}) };
  const draft = { engine: s.engine, key: s.key, models: { ...s.models }, effort: { ...s.effort }, prices: JSON.parse(JSON.stringify(s.prices || {})),
                  steps: JSON.parse(JSON.stringify(s.steps || {})), server: JSON.parse(JSON.stringify(base)) };
  // The steps set apart, in a stable order and without the ones that set nothing
  const apart = d => Object.keys(d.steps || {}).sort().filter(k => d.steps[k].model || d.steps[k].effort)
    .map(k => [k, d.steps[k].model || "", d.steps[k].effort || ""]);
  const state = d => JSON.stringify([d.engine, d.key, d.models.reasoning, d.models.translator, d.effort.reasoning, d.effort.translator, d.prices,
                                     d === draft ? d.server : base, apart(d)]);
  const installed = ["", ...(s.engines_installed || []).map(e => e.name)];
  const labelOf = name => S.engines[name] || esc(((s.engines_installed || []).find(e => e.name === name) || {}).label || name);
  const SV = S.server;
  const engineNow = d => s.engine_forced || d.engine || (cc.subscription ? "claude-code" : "api");
  const claudeCodeNote = !cc.installed ? S.missing : !cc.signed_in ? S.signedOut : !cc.subscription ? S.noPlan : "";
  const category = (id, body) => `<section class="cfg-page" data-cat="${id}"${id === settingsCategory ? "" : " hidden"}>
      <h2 class="cfg-title">${S.cat[id]}</h2>${body}</section>`;

  page.innerHTML = `
    <form class="settings-page" id="settings" autocomplete="off">
      <div class="settings-bar">
        <h2>${S.title}</h2>
        <span class="muted small grow" id="settings-message" role="status">${esc(message)}</span>
        <button type="button" id="settings-cancel"></button>
        <button type="submit" class="primary" id="settings-save">${S.save}</button>
      </div>
      <div class="cfg-layout">
        <nav class="cfg-nav" aria-label="${S.categories}">
          ${["engine", "models", "prices", "guide"].map(id => `<button type="button" class="cfg-cat" data-cat="${id}"${id === settingsCategory ? ' aria-current="page"' : ""}>
            <span class="cfg-ic" aria-hidden="true">${SETTINGS_ICONS[id]}</span>
            <span class="cfg-t"><b>${S.cat[id]}</b><span class="cfg-sum" data-sum="${id}"></span></span>
            <span class="cfg-dot" data-dot="${id}" title="${S.modified}" hidden></span></button>`).join("")}
        </nav>
        <div class="cfg-pages">
          ${category("engine", `
            <p class="muted small">${S.engineHelp}</p>
            ${cc.subscription ? `<div class="offer">
              <div class="offer-text"><strong>${esc(S.found(cc.subscription))}</strong> ${S.foundHelp}</div>
              <button type="button" class="primary" id="use-claude-code">${S.use}</button>
              <span class="badge ok" id="claude-code-used">${S.inUse}</span>
            </div>` : `<p class="banner small">${claudeCodeNote}</p>`}
            <div class="cfg-field">
              <span class="cfg-label" id="engine-label">${S.engineLabel}</span>
              <div class="cfg-seg" role="radiogroup" aria-labelledby="engine-label">
                ${installed.map(e => `<label><input type="radio" name="engine" value="${esc(e)}"${e === s.engine ? " checked" : ""}${
                  e === "claude-code" && !cc.subscription && s.engine !== e ? " disabled" : ""}>${labelOf(e)}</label>`).join("")}
              </div>
              <span class="muted small">${S.autoHelp}</span>
            </div>
            <p id="engine-next"></p>
            ${s.engine_forced ? `<p class="attention-text small">${S.forced(esc(s.engine_forced))}</p>` : ""}
            <p class="muted small">${S.noFallback}</p>
            <div id="server-options" hidden>
              <h3 class="cfg-sub">${SV.title}</h3>
              <p class="muted small">${SV.help}</p>
              <label class="cfg-field"><span class="cfg-label">${SV.url}</span>
                <input type="url" data-server="base_url" value="${esc(draft.server.base_url || "")}" placeholder="${SV.urlHint}" spellcheck="false"></label>
              <label class="cfg-field"><span class="cfg-label">${SV.key}</span>
                <input type="text" data-server="key" value="${esc(draft.server.key || "")}" placeholder="${SV.keyHint}" spellcheck="false" autocapitalize="off"></label>
              <p><button type="button" id="server-list">${SV.list}</button> <span class="small" id="server-listed" role="status"></span></p>
              <label class="cfg-field"><span class="cfg-label">${SV.context}</span>
                <input type="number" min="4096" step="1024" data-server="context" value="${draft.server.context || 131072}">
                <span class="muted small">${SV.contextHelp}</span></label>
              <label class="cfg-field"><span class="cfg-label">${SV.structured}</span>
                <select data-server="structured">${Object.entries(SV.structuredOptions).map(([v, t]) => `<option value="${v}"${v === draft.server.structured ? " selected" : ""}>${t}</option>`).join("")}</select></label>
              <label class="cfg-field"><span class="cfg-label">${SV.billing}</span>
                <select data-server="billing">${Object.entries(SV.billingOptions).map(([v, t]) => `<option value="${v}"${v === draft.server.billing ? " selected" : ""}>${t}</option>`).join("")}</select></label>
              <label class="small"><input type="checkbox" data-server="effort"${draft.server.effort ? " checked" : ""}> ${SV.effort}</label>
              <label class="cfg-field"><span class="cfg-label">${SV.searxng}</span>
                <input type="url" data-server="searxng" value="${esc(draft.server.searxng || "")}" placeholder="http://searxng.lan:8080" spellcheck="false">
                <span class="muted small">${SV.searxngHelp}</span></label>
            </div>
            <h3 class="cfg-sub">${S.keyTitle}</h3>
            <p class="muted small">${S.keyHelp}</p>
            <ul class="muted small cfg-list">${S.keyForms.map(f => `<li>${f}</li>`).join("")}</ul>
            <label class="cfg-field"><span class="cfg-label">${S.keyLabel}</span>
              <input type="text" id="settings-key" value="${esc(s.key)}" placeholder="env:ANTHROPIC_API_KEY" spellcheck="false" autocapitalize="off"></label>
            <p class="small" id="key-status" role="status"></p>`)}
          ${category("models", `
            <p class="muted small">${S.modelsHelp}</p>
            <p class="muted small" id="models-source">${S.modelsLoading}</p>
            ${Object.keys(s.choices.models).map(role => `<fieldset class="cfg-role">
              <legend>${S.roles[role]}</legend>
              <span class="muted small">${S.roleHelp[role]}</span>
              <select data-role="${role}" aria-label="${S.roles[role]}"></select>
              <input type="text" data-server-role="${role}" list="server-models" value="${esc(draft.server.models[role] || "")}"
                placeholder="${SV.modelHint}" aria-label="${S.roles[role]}" spellcheck="false" hidden>
              <span class="small attention-text" data-unpriced="${role}" hidden>${S.unpricedHelp}</span>
              <div class="cfg-field"><span class="cfg-label" id="effort-${role}">${S.effortLabel}</span>
                <div class="cfg-seg" role="radiogroup" aria-labelledby="effort-${role}">
                  ${s.choices.effort.map(e => `<label><input type="radio" name="effort-${role}" value="${e}"${e === s.effort[role] ? " checked" : ""}>${S.efforts[e]}</label>`).join("")}
                </div>
                <span class="muted small" data-steps="${role}"></span></div>
              <details class="cfg-steps"${s.choices.steps[role].some(x => (s.steps || {})[x.step]) ? " open" : ""}>
                <summary>${S.stepsApart} <span class="badge" data-apart="${role}" hidden></span></summary>
                <p class="muted small">${S.stepsApartHelp}</p>
                <div class="cfg-step cfg-step-head muted small"><span></span><span>${S.stepModel}</span><span>${S.stepEffort}</span></div>
                ${s.choices.steps[role].map(x => `<div class="cfg-step">
                  <span class="cfg-step-name">${S.stepNames[x.step] || x.step}</span>
                  <select data-step-model="${x.step}" aria-label="${S.stepModel} · ${S.stepNames[x.step] || x.step}"></select>
                  <input type="text" data-step-server="${x.step}" list="server-models" value="${esc(((s.steps || {})[x.step] || {}).model || "")}"
                    placeholder="${S.stepServerHint}" aria-label="${S.stepModel} · ${S.stepNames[x.step] || x.step}" spellcheck="false" hidden>
                  <select data-step-effort="${x.step}" aria-label="${S.stepEffort} · ${S.stepNames[x.step] || x.step}">
                    <option value="">${S.asRole}</option>
                    ${s.choices.levels.map(l => `<option value="${l}"${((s.steps || {})[x.step] || {}).effort === l ? " selected" : ""}>${S.levels[l]}</option>`).join("")}
                  </select></div>`).join("")}
              </details>
            </fieldset>`).join("")}
            <p class="muted small">${S.effortHelp}</p>
            <datalist id="server-models"></datalist>`)}
          ${category("prices", `
            <p class="muted small">${S.prices.help}</p>
            <div class="table-scroll"><table class="price-table small">
              <thead><tr>${S.prices.cols.map((c, i) => `<th${i >= 1 && i <= 4 ? ' class="number"' : ""}>${c}</th>`).join("")}</tr></thead>
              <tbody id="price-rows"></tbody></table></div>
            <p class="error-text small" id="price-error" role="alert"></p>
            <h3 class="cfg-sub">${S.prices.listTitle}</h3>
            <p class="muted small">${S.prices.listHelp(esc(s.price_table.source))}</p>
            <p class="small" id="price-list">${s.price_table.fetched ? S.prices.listOf(esc(s.price_table.fetched.date), s.price_table.fetched.models) : S.prices.listNone}</p>
            <p><button type="button" id="price-fetch">${S.prices.fetch}</button></p>
            <div id="price-changes" class="small"></div>`)}
          ${category("guide", guidePage(s.guide))}
        </div>
      </div>
    </form>`;

  const key = $("#settings-key");
  const plainKey = () => draft.key !== "" && !KEY_REFERENCES.some(r => draft.key.startsWith(r));
  /* Everything that follows the fields: the engine of the next run, the state of the key, what is changed. */
  const refresh = () => {
    const changed = state(draft) !== state(s), now = engineNow(draft);
    $("#engine-next").innerHTML = S.next(S.names[now] || labelOf(now));
    const onServer = now === "openai";
    $("#server-options").hidden = !onServer;
    page.querySelectorAll("[data-role]").forEach(x => x.hidden = onServer);
    page.querySelectorAll("[data-server-role]").forEach(x => x.hidden = !onServer);
    page.querySelectorAll("[data-step-model]").forEach(x => x.hidden = onServer);
    page.querySelectorAll("[data-step-server]").forEach(x => x.hidden = !onServer);
    $("#models-source").hidden = onServer;   // the Claude list: not the server's (its list is under Engine)
    if (cc.subscription) {
      $("#use-claude-code").hidden = now === "claude-code";
      $("#claude-code-used").hidden = now !== "claude-code";
    }
    const st = s.key_status;
    const [cls, text] = plainKey() ? ["error-text", S.keyPlain]
      : draft.key !== s.key ? ["muted", S.keyUnchecked]
      : st.error ? ["error-text", esc(st.error)]
      : !draft.key ? ["muted", S.keyEmpty]
      : st.found ? ["ok-text", `✓ ${S.keyFound}`] : ["attention-text", S.keyAbsent];
    $("#key-status").className = `small ${cls}`;
    $("#key-status").innerHTML = text + (now === "claude-code" && !plainKey() ? ` · ${S.keyOnlyApi}` : "");
    key.setAttribute("aria-invalid", plainKey());
    page.querySelector('[data-sum="engine"]').textContent = labelOf(draft.engine).replace(/<[^>]+>/g, "");
    page.querySelector('[data-sum="guide"]').textContent = s.guide.name;
    page.querySelector('[data-sum="prices"]').textContent = s.price_table.fetched ? S.prices.listOf(s.price_table.fetched.date, s.price_table.fetched.models).replace(/\.$/, "")
      : Object.keys(draft.prices).length ? `${Object.keys(draft.prices).length} ${S.prices.origin.set}` : S.prices.origin.default(s.price_table.models.find(m => m.origin === "default")?.date || "");
    page.querySelector('[data-dot="prices"]').hidden = JSON.stringify(draft.prices) === JSON.stringify(s.prices || {});
    drawPrices();
    page.querySelector('[data-sum="models"]').textContent = Object.keys(draft.models)
      .map(r => `${onServer ? (draft.server.models[r] || "?") : modelName(draft.models[r])}${draft.effort[r] === "normal" ? "" : ` (${S.efforts[draft.effort[r]].toLowerCase()})`}`).join(" · ")
      + (apart(draft).length ? ` · ${S.stepsApartCount(apart(draft).length)}` : "");
    const serverChanged = JSON.stringify(draft.server) !== JSON.stringify(base);
    page.querySelector('[data-dot="engine"]').hidden = draft.engine === s.engine && draft.key === s.key && !serverChanged;
    page.querySelector('[data-dot="models"]').hidden = JSON.stringify([draft.models, draft.effort, apart(draft)]) === JSON.stringify([s.models, s.effort, apart(s)]);
    for (const role of Object.keys(draft.models)) {   // each step of the role at the effort chosen
      page.querySelector(`[data-steps="${role}"]`).textContent = `${S.stepsOf} ${s.choices.steps[role]
        .map(x => `${S.stepNames[x.step] || x.step} ${S.levels[x.levels[draft.effort[role]]]}`).join(" · ")}`;
      const own = s.choices.steps[role].filter(x => apart(draft).some(a => a[0] === x.step)).length, badge = page.querySelector(`[data-apart="${role}"]`);
      badge.hidden = !own;
      badge.textContent = own;
      page.querySelector(`[data-unpriced="${role}"]`).hidden = onServer || models === null || models.find(m => m.id === draft.models[role])?.priced !== false;
    }
    $("#settings-save").disabled = !changed || plainKey();
    $("#settings-cancel").textContent = changed ? S.cancel : S.close;   // always there: it closes, dropping the changes if any
    if (changed) $("#settings-message").textContent = "";
  };
  settingsChanged = () => state(draft) !== state(s);

  /* The « Prices » category: the table with the draft's own prices (« to save » until the settings are saved). */
  let editing = null;
  const fmt = n => (Math.round(n * 1000) / 1000).toLocaleString(lang);
  const originOf = m => {
    const P = S.prices.origin, label = x => !x ? P.none : x.origin === "fetched" ? P.fetched(x.date) : P.default(x.date);
    if (draft.prices[m.id]) return JSON.stringify(draft.prices[m.id]) === JSON.stringify((s.prices || {})[m.id]) ? P.set : `${P.set} (${S.prices.unsaved})`;
    return m.origin === "set" ? label(m.base) : m.rates ? label(m) : P.none;
  };
  function drawPrices() {
    const body = $("#price-rows");
    if (!body) return;
    const rows = s.price_table.models;
    body.innerHTML = rows.map(m => {
      const rates = draft.prices[m.id] || (m.origin === "set" ? (m.base && m.base.rates) : m.rates);
      if (editing === m.id) {
        const r = rates || { input: 0, output: 0, cache_read: 0, cache_write: 0 };
        return `<tr><th scope="row">${esc(m.id)}</th>${["input", "output", "cache_read", "cache_write"].map(k =>
          `<td><input type="number" min="0" step="any" data-rate="${k}" value="${r[k]}" aria-label="${k}"></td>`).join("")}
          <td colspan="2"><button type="button" id="price-ok">${S.prices.ok}</button> <button type="button" id="price-cancel">${S.prices.cancel}</button></td></tr>`;
      }
      return `<tr${m.in_use ? ' class="in-use"' : ""}><th scope="row">${esc(m.id)}${m.in_use ? ` <span class="badge">${S.prices.inUse}</span>` : ""}</th>
        ${rates ? ["input", "output", "cache_read", "cache_write"].map(k => `<td class="number">${fmt(rates[k])}</td>`).join("") : `<td colspan="4" class="muted">—</td>`}
        <td class="muted">${originOf(m)}</td>
        <td>${draft.prices[m.id] ? `<button type="button" class="link" data-reset="${esc(m.id)}">${S.prices.reset}</button>`
          : `<button type="button" class="link" data-set="${esc(m.id)}">${S.prices.set}</button>`}</td></tr>`;
    }).join("");
    body.querySelectorAll("[data-set]").forEach(b => b.onclick = () => { editing = b.dataset.set; drawPrices(); });
    body.querySelectorAll("[data-reset]").forEach(b => b.onclick = () => { delete draft.prices[b.dataset.reset]; refresh(); });
    if (editing) {
      $("#price-cancel").onclick = () => { editing = null; $("#price-error").textContent = ""; drawPrices(); };
      $("#price-ok").onclick = () => {
        const r = {};
        for (const i of body.querySelectorAll("[data-rate]")) r[i.dataset.rate] = Number(i.value);
        if (Object.values(r).some(v => !Number.isFinite(v) || v < 0) || [...body.querySelectorAll("[data-rate]")].some(i => i.value === "")) {
          $("#price-error").textContent = S.prices.invalid;
          return;
        }
        $("#price-error").textContent = "";
        draft.prices[editing] = r;
        editing = null;
        refresh();
      };
    }
  }
  $("#price-fetch").onclick = async () => {
    const b = $("#price-fetch"), out = $("#price-changes");
    b.disabled = true;
    b.textContent = S.prices.fetching;
    try {
      const r = await api("/api/prices/fetch", {});
      const fresh = r.changes.filter(c => c.startsWith("+ ")), other = r.changes.filter(c => !c.startsWith("+ "));
      out.innerHTML = `<p>${S.prices.changes(esc(r.date), r.models)}</p>
        ${r.changes.length ? `<ul class="cfg-list">${other.map(c => `<li><code>${esc(c)}</code></li>`).join("")}
          ${fresh.length ? `<li>${S.prices.newModels(fresh.length)} : ${fresh.map(c => `<code>${esc(c.slice(2).split(":")[0])}</code>`).join(", ")}</li>` : ""}</ul>`
          : `<p class="muted">${S.prices.noChange}</p>`}
        ${r.estimated.length ? `<p class="muted">${S.prices.estimated}${r.estimated.map(esc).join(", ")}</p>` : ""}
        <p><button type="button" class="primary" id="price-apply">${S.prices.apply}</button></p>`;
      $("#price-apply").onclick = async () => {
        try {
          drawSettings(await api("/api/prices/apply", {}), S.prices.applied);
        } catch (err) { out.insertAdjacentHTML("beforeend", `<p class="error-text">${esc(err.message)}</p>`); }
      };
    } catch (err) {
      out.innerHTML = `<p class="error-text">${esc(err.message)}</p>`;
    } finally {
      b.disabled = false;
      b.textContent = S.prices.fetch;
    }
  };

  page.querySelectorAll(".cfg-cat").forEach(b => b.onclick = () => {
    settingsCategory = b.dataset.cat;
    page.querySelectorAll(".cfg-cat").forEach(o => o.dataset.cat === settingsCategory ? o.setAttribute("aria-current", "page") : o.removeAttribute("aria-current"));
    page.querySelectorAll(".cfg-page").forEach(p => p.hidden = p.dataset.cat !== settingsCategory);
  });
  page.querySelectorAll("[name=engine]").forEach(r => r.onchange = () => { draft.engine = r.value; refresh(); });
  if (cc.subscription) $("#use-claude-code").onclick = () => {
    // Shown only when the API is the engine: back to Claude Code, as an explicit choice
    page.querySelector('[name=engine][value="claude-code"]').checked = true;
    draft.engine = "claude-code";
    refresh();
  };
  key.oninput = () => { draft.key = key.value.trim(); refresh(); };
  page.querySelectorAll("[data-server]").forEach(f => f.oninput = f.onchange = () => {
    const k = f.dataset.server;
    draft.server[k] = f.type === "checkbox" ? f.checked : f.type === "number" ? Number(f.value) : f.value.trim();
    refresh();
  });
  page.querySelectorAll("[data-server-role]").forEach(f => f.oninput = () => { draft.server.models[f.dataset.serverRole] = f.value.trim(); refresh(); });
  /* The models of the OpenAI-compatible server, as suggestions for the two fields (an id can always be typed). */
  const listServer = async () => {
    const out = $("#server-listed"), b = $("#server-list");
    b.disabled = true;
    out.className = "small muted";
    out.textContent = SV.listing;
    try {
      const q = new URLSearchParams({ engine: "openai", base_url: draft.server.base_url || "", key: draft.server.key || "" });
      const r = await api(`/api/models?${q}`);
      $("#server-models").innerHTML = r.models.map(m => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join("");
      out.className = r.error ? "small error-text" : "small ok-text";
      out.textContent = r.error || SV.listed(r.models.length);
    } catch (e) {
      out.className = "small error-text";
      out.textContent = e.message;
    } finally { b.disabled = false; }
  };
  $("#server-list").onclick = listServer;
  if (engineNow(draft) === "openai" && draft.server.base_url) listServer();
  page.querySelectorAll("[data-role]").forEach(sel => sel.onchange = () => { draft.models[sel.dataset.role] = sel.value; refresh(); });
  for (const role of Object.keys(draft.effort))
    page.querySelectorAll(`[name=effort-${role}]`).forEach(r => r.onchange = () => { draft.effort[role] = r.value; refresh(); });
  /* A step set apart: its own model, its own effort; « as the role » on both removes it from the settings. */
  const setStep = (step, field, value) => {
    const own = { ...(draft.steps[step] || {}), [field]: value };
    if (!own[field]) delete own[field];
    if (Object.keys(own).length) draft.steps[step] = own; else delete draft.steps[step];
    refresh();
  };
  page.querySelectorAll("[data-step-model]").forEach(f => f.onchange = () => setStep(f.dataset.stepModel, "model", f.value));
  page.querySelectorAll("[data-step-server]").forEach(f => f.oninput = () => setStep(f.dataset.stepServer, "model", f.value.trim()));
  page.querySelectorAll("[data-step-effort]").forEach(f => f.onchange = () => setStep(f.dataset.stepEffort, "effort", f.value));
  /* The models of each role: the list of the API (with the key of the settings), else the ones the agent knows; the
     model chosen stays in the list even when the API does not offer it any more. */
  let models = null;
  const fill = list => {
    models = list;
    for (const [role, defaults] of Object.entries(s.choices.models)) {
      const sel = page.querySelector(`[data-role="${role}"]`);
      const ids = [...new Set([draft.models[role], ...list.map(m => m.id)])];
      sel.innerHTML = ids.map(id => {
        const m = list.find(x => x.id === id) || { id, name: modelName(id), priced: true };
        const notes = [id === defaults[0] ? S.byDefault : "", m.priced === false ? S.unpriced : ""].filter(Boolean).join(", ");
        return `<option value="${esc(id)}"${id === draft.models[role] ? " selected" : ""}>${esc(m.name)}${notes ? ` (${notes})` : ""}</option>`;
      }).join("");
    }
    page.querySelectorAll("[data-step-model]").forEach(sel => {
      const chosen = (draft.steps[sel.dataset.stepModel] || {}).model || "";
      const ids = [...new Set([chosen, ...list.map(m => m.id), ...Object.values(s.choices.models).flat()])].filter(Boolean);
      sel.innerHTML = `<option value="">${S.asRole}</option>` + ids.map(id => {
        const m = list.find(x => x.id === id) || { id, name: modelName(id), priced: true };
        return `<option value="${esc(id)}"${id === chosen ? " selected" : ""}>${esc(m.name)}${m.priced === false ? ` (${S.unpriced})` : ""}</option>`;
      }).join("");
    });
    refresh();
  };
  fill([]);
  models = null;
  api("/api/models").then(r => {
    if (!$("#models-source")) return;   // left the page meanwhile
    $("#models-source").textContent = r.source === "api" ? S.modelsFromApi : S.modelsKnown(r.error);
    fill(r.models);
  }).catch(e => { if ($("#models-source")) $("#models-source").textContent = S.modelsKnown(e.message); });
  $("#settings-cancel").onclick = () => { settingsChanged = () => false; page.close(); };
  $("#settings").onsubmit = async e => {
    e.preventDefault();
    if (plainKey()) return;
    $("#settings-save").disabled = true;
    try {
      const { server, ...rest } = draft;
      const saved = await api("/api/settings", { ...rest, engines: { ...(s.engines || {}), openai: server } });
      if (info) info.engine = saved.engine_now;  // the cost of the paid actions follows, on every page
      drawSettings(saved, S.saved);
    } catch (err) {
      $("#settings-message").innerHTML = `<span class="error-text">${esc(err.message)}</span>`;
      $("#settings-save").disabled = false;
    }
  };
  refresh();
}
