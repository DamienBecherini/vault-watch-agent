/* vault-watch: the Settings page (#/settings), loaded before app.js, which owns the router, the texts and the helpers
   used here ($, page, api, esc, T, info, header). What it edits is the settings file of the server (config.py):
   the engine that calls the model (Claude Code on a subscription, or the API), where the API key is (a reference,
   never the key) and the model of each role. A change applies to the next run.
   Layout after the Settings of dl-sub-dub: the categories at the left, one page each, Claude Code found on the
   machine proposed in a framed box. */

const SETTINGS_TEXTS = {
  fr: {
    title: "Réglages", open: "Réglages", save: "Enregistrer", cancel: "Annuler",
    saved: "Enregistré. S'applique au prochain passage.", modified: "modifié, pas encore enregistré",
    categories: "Catégories", cat: { engine: "Moteur", models: "Modèles" },
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
    modelsHelp: "Le modèle de chaque rôle, quel que soit le moteur. Les mesures de coût et de qualité de la documentation ont été faites avec les modèles par défaut.",
    roles: { reasoning: "Raisonnement", translator: "Traduction" },
    roleHelp: { reasoning: "Tri de la veille, propositions, relecture croisée, vérifications du guide.",
      translator: "Miroir anglais et contrôle des traductions." },
    byDefault: "par défaut",
  },
  en: {
    title: "Settings", open: "Settings", save: "Save", cancel: "Cancel",
    saved: "Saved. Applies to the next run.", modified: "changed, not saved yet",
    categories: "Categories", cat: { engine: "Engine", models: "Models" },
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
    modelsHelp: "The model of each role, whatever the engine. The cost and quality figures of the documentation were measured with the default models.",
    roles: { reasoning: "Reasoning", translator: "Translation" },
    roleHelp: { reasoning: "Triage of the watch, proposals, cross-check, checks of the guide.",
      translator: "English mirror and translation checks." },
    byDefault: "default",
  },
};

const SETTINGS_ICONS = {
  gear: `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></svg>`,
  engine: `<svg viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4"/></svg>`,
  models: `<svg viewBox="0 0 24 24"><path d="M12 3l8 4.5-8 4.5-8-4.5z"/><path d="M4 12l8 4.5 8-4.5M4 16.5L12 21l8-4.5"/></svg>`,
};

const KEY_REFERENCES = ["env:", "sops:", "file:"];
const modelName = m => m.replace(/^claude-/, "").replace(/-(\d+)-(\d+)$/, " $1.$2").replace(/^./, c => c.toUpperCase());
let settingsCategory = "engine";  // the category shown, kept across redraws

async function viewSettings() {
  drawSettings(await api("/api/settings"));
}

/* `s`: the settings as the server holds them, with what it found (Claude Code, the key); the page edits a copy. */
function drawSettings(s, message = "") {
  const S = T.settings, cc = s.claude_code;
  const draft = { engine: s.engine, key: s.key, models: { ...s.models } };
  const state = d => JSON.stringify([d.engine, d.key, d.models.reasoning, d.models.translator]);
  const engineNow = d => s.engine_forced || d.engine || (cc.subscription ? "claude-code" : "api");
  const claudeCodeNote = !cc.installed ? S.missing : !cc.signed_in ? S.signedOut : !cc.subscription ? S.noPlan : "";
  const category = (id, body) => `<section class="cfg-page" data-cat="${id}"${id === settingsCategory ? "" : " hidden"}>
      <h2 class="cfg-title">${S.cat[id]}</h2>${body}</section>`;

  page.innerHTML = `
    <h1>${S.title}</h1>
    <form class="card settings-page" id="settings" autocomplete="off">
      <div class="settings-bar">
        <span class="muted small grow" id="settings-message" role="status">${esc(message)}</span>
        <button type="button" id="settings-cancel">${S.cancel}</button>
        <button type="submit" class="primary" id="settings-save">${S.save}</button>
      </div>
      <div class="cfg-layout">
        <nav class="cfg-nav" aria-label="${S.categories}">
          ${["engine", "models"].map(id => `<button type="button" class="cfg-cat" data-cat="${id}"${id === settingsCategory ? ' aria-current="page"' : ""}>
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
            ${Object.entries(s.choices.models).map(([role, names]) => `<label class="cfg-field"><span class="cfg-label">${S.roles[role]}</span>
              <select data-role="${role}">${names.map((m, i) => `<option value="${m}"${m === s.models[role] ? " selected" : ""}>${modelName(m)}${i ? "" : ` (${S.byDefault})`}</option>`).join("")}</select>
              <span class="muted small">${S.roleHelp[role]}</span></label>`).join("")}`)}
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
    page.querySelector('[data-sum="models"]').textContent = Object.values(draft.models).map(modelName).join(" · ");
    page.querySelector('[data-dot="engine"]').hidden = draft.engine === s.engine && draft.key === s.key;
    page.querySelector('[data-dot="models"]').hidden = JSON.stringify(draft.models) === JSON.stringify(s.models);
    $("#settings-save").disabled = !changed || plainKey();
    $("#settings-cancel").disabled = !changed;
    if (changed) $("#settings-message").textContent = "";
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
  page.querySelectorAll("[data-role]").forEach(sel => sel.onchange = () => { draft.models[sel.dataset.role] = sel.value; refresh(); });
  $("#settings-cancel").onclick = () => drawSettings(s);
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
