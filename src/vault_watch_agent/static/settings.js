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
    categories: "Catégories", cat: { engine: "Moteur", models: "Modèles et effort", guide: "Guide" },
    engineHelp: "Qui appelle le modèle. Un changement s'applique au prochain passage ; un passage en cours garde son moteur.",
    found: plan => `Claude Code trouvé sur cette machine (abonnement ${plan})`,
    foundHelp: "Les appels passent par ton abonnement Claude : pas de clé d'API, rien de facturé. L'usage compte dans les limites de l'abonnement.",
    use: "Utiliser Claude Code", inUse: "Utilisé",
    missing: "Claude Code n'est pas installé sur cette machine (ou pas dans le PATH).",
    signedOut: "Claude Code est installé mais pas connecté : lance <code>claude</code> une fois pour te connecter.",
    noPlan: "Claude Code est connecté sans abonnement (compte Console ou clé) : ses appels seraient facturés, il n'est donc pas proposé.",
    engines: { "": "Automatique", "claude-code": "Claude Code (abonnement)", api: "API (clé, facturée au token)" },
    engineLabel: "Moteur",
    autoHelp: "Automatique : Claude Code s'il est connecté à un abonnement, sinon l'API.",
    next: name => `Moteur du prochain passage : <b>${name}</b>`,
    names: { "claude-code": "Claude Code, sur l'abonnement", api: "API Claude, facturée au token" },
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
    stepNames: { triage: "tri", proposals: "propositions", crosscheck: "relecture croisée", checks: "vérifications", deadlinks: "liens morts", mirror: "miroir anglais", translation: "contrôle des traductions" },
    levels: { low: "bas", medium: "moyen", high: "élevé", xhigh: "très élevé", max: "maximal" },
    roles: { reasoning: "Raisonnement", translator: "Traduction" },
    roleHelp: { reasoning: "Tri de la veille, propositions, relecture croisée, vérifications du guide.",
      translator: "Miroir anglais et contrôle des traductions." },
    byDefault: "par défaut",
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
        "github-issue": w => `issues GitHub d'étiquette « ${w.label || "veille"} »`, file: w => `fichier <code>${w.path}</code>` },
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
    categories: "Categories", cat: { engine: "Engine", models: "Models and effort", guide: "Guide" },
    engineHelp: "What calls the model. A change applies to the next run; a run in progress keeps its engine.",
    found: plan => `Claude Code found on this machine (${plan} subscription)`,
    foundHelp: "The calls go through your Claude subscription: no API key, nothing billed. The usage counts in the limits of the subscription.",
    use: "Use Claude Code", inUse: "In use",
    missing: "Claude Code is not installed on this machine (or not in the PATH).",
    signedOut: "Claude Code is installed but not signed in: run <code>claude</code> once and sign in.",
    noPlan: "Claude Code is signed in without a subscription (a Console account or a key): its calls would be billed, so it is not proposed.",
    engines: { "": "Automatic", "claude-code": "Claude Code (subscription)", api: "API (key, billed per token)" },
    engineLabel: "Engine",
    autoHelp: "Automatic: Claude Code when it is signed in with a subscription, otherwise the API.",
    next: name => `Engine of the next run: <b>${name}</b>`,
    names: { "claude-code": "Claude Code, on the subscription", api: "Claude API, billed per token" },
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
    stepNames: { triage: "triage", proposals: "proposals", crosscheck: "cross-check", checks: "checks", deadlinks: "dead links", mirror: "English mirror", translation: "translation checks" },
    levels: { low: "low", medium: "medium", high: "high", xhigh: "extra high", max: "max" },
    roles: { reasoning: "Reasoning", translator: "Translation" },
    roleHelp: { reasoning: "Triage of the watch, proposals, cross-check, checks of the guide.",
      translator: "English mirror and translation checks." },
    byDefault: "default",
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
        "github-issue": w => `GitHub issues labelled « ${w.label || "veille"} »`, file: w => `file <code>${w.path}</code>` },
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
    ${row(G.repository, g.repository ? code(g.repository) : `<span class="muted">${G.local}</span>`)}
    ${g.site ? row(G.site, extLink(g.site, esc(g.site))) : ""}
    ${row(G.base, code(g.base_branch))}
    <h3 class="cfg-sub">${G.parts}</h3>
    <ul class="small cfg-list">
      ${g.mirrors.length ? g.mirrors.map(m => part(G.mirror, true, G.mirrorOn({ ...m, folder: esc(m.folder) }))).join("") : part(G.mirror, false, "", G.mirrorOff)}
      ${part(G.modified, !!g.modified_field, G.modifiedOn(esc(g.modified_field)), G.modifiedOff)}
      ${part(G.watch, w.source !== "none", typeof src === "function" ? src({ label: esc(w.label), path: esc(w.path) }) : "", G.watchSources.none)}
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
  const draft = { engine: s.engine, key: s.key, models: { ...s.models }, effort: { ...s.effort } };
  const state = d => JSON.stringify([d.engine, d.key, d.models.reasoning, d.models.translator, d.effort.reasoning, d.effort.translator]);
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
          ${["engine", "models", "guide"].map(id => `<button type="button" class="cfg-cat" data-cat="${id}"${id === settingsCategory ? ' aria-current="page"' : ""}>
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
                ${["", "claude-code", "api"].map(e => `<label><input type="radio" name="engine" value="${e}"${e === s.engine ? " checked" : ""}${
                  e === "claude-code" && !cc.subscription && s.engine !== e ? " disabled" : ""}>${S.engines[e]}</label>`).join("")}
              </div>
              <span class="muted small">${S.autoHelp}</span>
            </div>
            <p id="engine-next"></p>
            ${s.engine_forced ? `<p class="attention-text small">${S.forced(esc(s.engine_forced))}</p>` : ""}
            <p class="muted small">${S.noFallback}</p>
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
              <span class="small attention-text" data-unpriced="${role}" hidden>${S.unpricedHelp}</span>
              <div class="cfg-field"><span class="cfg-label" id="effort-${role}">${S.effortLabel}</span>
                <div class="cfg-seg" role="radiogroup" aria-labelledby="effort-${role}">
                  ${s.choices.effort.map(e => `<label><input type="radio" name="effort-${role}" value="${e}"${e === s.effort[role] ? " checked" : ""}>${S.efforts[e]}</label>`).join("")}
                </div>
                <span class="muted small" data-steps="${role}"></span></div>
            </fieldset>`).join("")}
            <p class="muted small">${S.effortHelp}</p>`)}
          ${category("guide", guidePage(s.guide))}
        </div>
      </div>
    </form>`;

  const key = $("#settings-key");
  const plainKey = () => draft.key !== "" && !KEY_REFERENCES.some(r => draft.key.startsWith(r));
  /* Everything that follows the fields: the engine of the next run, the state of the key, what is changed. */
  const refresh = () => {
    const changed = state(draft) !== state(s), now = engineNow(draft);
    $("#engine-next").innerHTML = S.next(S.names[now] || esc(now));
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
    page.querySelector('[data-sum="engine"]').textContent = S.engines[draft.engine];
    page.querySelector('[data-sum="guide"]').textContent = s.guide.name;
    page.querySelector('[data-sum="models"]').textContent = Object.keys(draft.models)
      .map(r => `${modelName(draft.models[r])}${draft.effort[r] === "normal" ? "" : ` (${S.efforts[draft.effort[r]].toLowerCase()})`}`).join(" · ");
    page.querySelector('[data-dot="engine"]').hidden = draft.engine === s.engine && draft.key === s.key;
    page.querySelector('[data-dot="models"]').hidden = JSON.stringify([draft.models, draft.effort]) === JSON.stringify([s.models, s.effort]);
    for (const role of Object.keys(draft.models)) {   // each step of the role at the effort chosen
      page.querySelector(`[data-steps="${role}"]`).textContent = `${S.stepsOf} ${s.choices.steps[role]
        .map(x => `${S.stepNames[x.step] || x.step} ${S.levels[x.levels[draft.effort[role]]]}`).join(" · ")}`;
      page.querySelector(`[data-unpriced="${role}"]`).hidden = models === null || models.find(m => m.id === draft.models[role])?.priced !== false;
    }
    $("#settings-save").disabled = !changed || plainKey();
    $("#settings-cancel").textContent = changed ? S.cancel : S.close;   // always there: it closes, dropping the changes if any
    if (changed) $("#settings-message").textContent = "";
  };
  settingsChanged = () => state(draft) !== state(s);

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
  page.querySelectorAll("[data-role]").forEach(sel => sel.onchange = () => { draft.models[sel.dataset.role] = sel.value; refresh(); });
  for (const role of Object.keys(draft.effort))
    page.querySelectorAll(`[name=effort-${role}]`).forEach(r => r.onchange = () => { draft.effort[role] = r.value; refresh(); });
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
      const saved = await api("/api/settings", draft);
      if (info) info.engine = saved.engine_now;  // the cost of the paid actions follows, on every page
      drawSettings(saved, S.saved);
    } catch (err) {
      $("#settings-message").innerHTML = `<span class="error-text">${esc(err.message)}</span>`;
      $("#settings-save").disabled = false;
    }
  };
  refresh();
}
