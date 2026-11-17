/* vault-watch: the buttons of the header for the look of the page (the size of the text, light or dark, the palettes)
   and the Theme window. Loaded before app.js, which owns the texts (T.theme) and the helpers used here ($, esc).
   Taken from dl-sub-dub (subtitles/web/static/v2/header.js and themes.js), written without Preact.

   The Theme window: the mode (system, light, dark), then the palettes of each mode, built-in and the user's own.
   Every palette can be changed: its 4 colours (background, text, secondary text, accent; the others are derived, see
   boot.js), with a check of the contrasts against WCAG shown while choosing (AAA, AA, large text only, not enough);
   saving is allowed whatever the result. A built-in palette changed has "Back to factory"; a theme of the user can be
   deleted. Everything is kept in this browser (localStorage, keys in boot.js). */

const THEME_TEXTS = {
  fr: {
    zoomIn: pct => `Agrandir le texte (actuellement ${pct} %)`, zoomOut: pct => `Réduire le texte (actuellement ${pct} %)`,
    toDark: "Passer au thème sombre", toLight: "Passer au thème clair", palettes: "Thème et palettes",
    title: "Thème", mode: "Mode", modes: { system: "Système", light: "Clair", dark: "Sombre" },
    modePalettes: { light: "Palette du thème clair", dark: "Palette du thème sombre" },
    help: "Chaque mode garde sa palette ; le bouton clair / sombre de l'en-tête bascule le mode sans la changer. Chaque palette se modifie avec son crayon ; tes thèmes vont dans le mode clair ou sombre selon leur fond. Mémorisé dans ce navigateur.",
    names: {
      azure: ["Azur", "La palette d'origine"], slate: ["Ardoise", "Gris bleutés, accent pétrole"], sand: ["Sable", "Gris chauds, accent orange"],
      sage: ["Sauge", "Gris neutres, accent sarcelle"], lavender: ["Lavande", "Gris froids, accent violet"],
      raspberry: ["Framboise", "Gris, accent rose"], "azure-night": ["Azur nuit", "La palette d'origine"],
      night: ["Bleu nuit", "Gris bleutés, accent turquoise"], warm: ["Chaud", "Sans lumière bleue, accent orange"],
      olive: ["Olive", "Sans lumière bleue, accent citron vert"], embers: ["Braise", "Sans lumière bleue, accent rouge"],
    },
    newButton: "+ Nouveau thème", new: "Nouveau thème", editTitle: name => `Modifier « ${name} »`, name: "Nom du thème",
    untitled: "Mon thème", yours: "Ton thème", changed: "modifiée", reset: "Revenir au thème d'usine",
    resetTitle: "Remet les couleurs d'origine de cette palette", delete: "Supprimer ce thème", deleteConfirm: "Confirmer la suppression",
    colors: { bg: "Fond", text: "Texte", muted: "Texte secondaire", accent: "Accent (boutons, liens)" },
    preview: { title: "Aperçu", muted: "Un texte secondaire, comme les aides sous les champs", link: "Un lien", field: "Un champ", button: "Lancer" },
    checkTitle: "Lisibilité (contrastes WCAG) :",
    levels: { AAA: "AAA", AA: "AA", large: "AA gros texte", fail: "Insuffisant", uiOk: "Suffisant (3:1)" },
    levelHelp: {
      AAA: "Niveau le plus élevé : lisible par presque tous, y compris avec une vue basse.",
      AA: "Le niveau recommandé : lisible par la plupart des gens.",
      large: "Seuls les gros textes sont assez contrastés ; les petits textes seront difficiles à lire. Tu peux quand même l'enregistrer.",
      fail: "Certains éléments seront difficiles, voire impossibles, à lire ou à repérer. Tu peux quand même l'enregistrer.",
    },
    pairs: { text_bg: "Texte sur le fond", text_card: "Texte sur les cartes", muted_card: "Texte secondaire sur les cartes",
      muted_bg: "Texte secondaire sur le fond", accent_card: "Accent (liens) sur les cartes", button: "Texte des boutons principaux",
      field: "Bordure des champs" },
    goesTo: { light: "Fond clair : ce thème sera rangé dans les palettes du mode clair.", dark: "Fond sombre : ce thème sera rangé dans les palettes du mode sombre." },
    mismatch: { light: "Ce fond est clair alors que la palette est celle du mode sombre.", dark: "Ce fond est sombre alors que la palette est celle du mode clair." },
    close: "Fermer", save: "Enregistrer", cancel: "Annuler",
  },
  en: {
    zoomIn: pct => `Larger text (now ${pct}%)`, zoomOut: pct => `Smaller text (now ${pct}%)`,
    toDark: "Switch to the dark theme", toLight: "Switch to the light theme", palettes: "Theme and palettes",
    title: "Theme", mode: "Mode", modes: { system: "System", light: "Light", dark: "Dark" },
    modePalettes: { light: "Light theme palette", dark: "Dark theme palette" },
    help: "Each mode keeps its palette; the light / dark button of the header switches the mode without changing it. Every palette can be changed with its pencil; your themes go to the light or dark mode according to their background. Kept in this browser.",
    names: {
      azure: ["Azure", "The original palette"], slate: ["Slate", "Blue greys, petrol accent"], sand: ["Sand", "Warm greys, orange accent"],
      sage: ["Sage", "Neutral greys, teal accent"], lavender: ["Lavender", "Cool greys, violet accent"],
      raspberry: ["Raspberry", "Greys, rose accent"], "azure-night": ["Azure night", "The original palette"],
      night: ["Midnight blue", "Blue greys, turquoise accent"], warm: ["Warm", "No blue light, orange accent"],
      olive: ["Olive", "No blue light, lime accent"], embers: ["Embers", "No blue light, red accent"],
    },
    newButton: "+ New theme", new: "New theme", editTitle: name => `Edit “${name}”`, name: "Name of the theme",
    untitled: "My theme", yours: "Your theme", changed: "changed", reset: "Back to factory theme",
    resetTitle: "Puts back the original colours of this palette", delete: "Delete this theme", deleteConfirm: "Confirm deletion",
    colors: { bg: "Background", text: "Text", muted: "Secondary text", accent: "Accent (buttons, links)" },
    preview: { title: "Preview", muted: "A secondary text, like the help under the fields", link: "A link", field: "A field", button: "Run" },
    checkTitle: "Readability (WCAG contrasts):",
    levels: { AAA: "AAA", AA: "AA", large: "AA large text", fail: "Not enough", uiOk: "Enough (3:1)" },
    levelHelp: {
      AAA: "Highest level: readable by nearly everyone, low vision included.",
      AA: "The recommended level: readable by most people.",
      large: "Only large text has enough contrast; small text will be hard to read. You can save it anyway.",
      fail: "Some elements will be hard or impossible to read or to spot. You can save it anyway.",
    },
    pairs: { text_bg: "Text on the background", text_card: "Text on the cards", muted_card: "Secondary text on the cards",
      muted_bg: "Secondary text on the background", accent_card: "Accent (links) on the cards", button: "Text of the main buttons",
      field: "Border of the fields" },
    goesTo: { light: "Light background: this theme goes with the palettes of the light mode.", dark: "Dark background: this theme goes with the palettes of the dark mode." },
    mismatch: { light: "This background is light while the palette is one of the dark mode.", dark: "This background is dark while the palette is one of the light mode." },
    close: "Close", save: "Save", cancel: "Cancel",
  },
};

// --- what this browser remembers (keys in boot.js) ---
const THEME_COLORS = ["bg", "text", "muted", "accent"];
const themeStore = {
  read(key, fallback) { try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); } catch { return fallback; } },
  write(key, value) { try { if (value == null) localStorage.removeItem(key); else localStorage.setItem(key, JSON.stringify(value)); } catch { /* this page only */ } },
  remember(key, value) { try { if (value == null) localStorage.removeItem(key); else localStorage.setItem(key, value); } catch { /* this page only */ } },
  remembered(key) { try { return localStorage.getItem(key); } catch { return null; } },
};
const customThemes = () => themeStore.read("custom-themes", {});
const paletteOverrides = () => themeStore.read("palette-overrides", {});
const modeOfColors = c => (window.themes.isDark(c.bg) ? "dark" : "light");
const currentMode = () => document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");

/* mode: "light", "dark" or "system". */
function setThemeMode(mode) {
  themeStore.remember("theme", mode === "system" ? null : mode);
  window.themes.apply();
}

/* The palettes of a mode: built-in ones, then the user's themes whose background belongs to that mode. */
function palettesOf(mode) {
  const own = Object.entries(customThemes()).filter(([, t]) => modeOfColors(t.colors) === mode).map(([id]) => id);
  return [...window.themes.palettes[mode], ...own];
}
const paletteOf = mode => {
  const id = themeStore.remembered("palette-" + mode);
  return palettesOf(mode).includes(id) ? id : window.themes.palettes[mode][0];
};

/* The colours of a built-in palette as style.css has them (read from a hidden swatch). */
function factoryColors(id) {
  const probe = document.createElement("span");
  probe.className = "swatch";
  probe.dataset.palette = id;
  probe.hidden = true;
  document.body.appendChild(probe);
  const s = getComputedStyle(probe);
  const c = Object.fromEntries(THEME_COLORS.map(k => [k, s.getPropertyValue("--" + k).trim()]));
  probe.remove();
  return c;
}
const paletteColors = id => window.themes.colorsOf(id) || factoryColors(id);
const paletteName = id => customThemes()[id]?.name || T.theme.names[id]?.[0] || id;
const styleOf = vars => Object.entries(vars).map(([k, v]) => `${k}:${v}`).join(";");

/* The contrasts that matter, from the colours derived: each pair with its ratio and its level, and the level of the
   whole. Text: AAA from 7, AA from 4.5, large text only from 3. Borders of the fields: 3 is the only level (WCAG 1.4.11). */
const THEME_LEVELS = ["fail", "large", "AA", "AAA"];
function checkTheme(colors) {
  const v = window.themes.tokens(colors);
  const pairs = [["text_bg", "--text", "--bg"], ["text_card", "--text", "--card"], ["muted_card", "--muted", "--card"],
    ["muted_bg", "--muted", "--bg"], ["accent_card", "--accent", "--card"], ["button", "--accent-text", "--accent"],
    ["field", "--field-border", "--card", true]];
  const rows = pairs.map(([key, a, b, ui]) => {
    const ratio = window.themes.contrast(v[a], v[b]);
    const level = ui ? (ratio >= 3 ? "AAA" : "fail") : ratio >= 7 ? "AAA" : ratio >= 4.5 ? "AA" : ratio >= 3 ? "large" : "fail";
    return { key, ratio, level, ui };
  });
  return { rows, level: THEME_LEVELS[Math.min(...rows.map(r => THEME_LEVELS.indexOf(r.level)))] };
}
const levelBadge = level => `<span class="level level-${level}">${T.theme.levels[level]}</span>`;

// --- the buttons of the header ---
const THEME_ICONS = {
  zoom: plus => `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><circle cx="10" cy="10" r="6.5" /><path d="${plus ? "M15 15l5.5 5.5M7 10h6M10 7v6" : "M15 15l5.5 5.5M7 10h6"}" /></svg>`,
  mode: `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="8.5" /><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor" stroke="none" /></svg>`,
  palette: `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path d="M12 3.5a8.5 8.5 0 1 0 0 17c1.4 0 2-.9 2-1.8 0-1.3-1-1.7-1-2.7 0-.8.7-1.5 1.6-1.5H17a3.5 3.5 0 0 0 3.5-3.5c0-4.2-3.8-7.5-8.5-7.5z" /><circle cx="8" cy="10.5" r="1" fill="currentColor" stroke="none" /><circle cx="12" cy="7.5" r="1" fill="currentColor" stroke="none" /><circle cx="16" cy="10.5" r="1" fill="currentColor" stroke="none" /></svg>`,
  pencil: `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false"><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4z" /><path d="m13.5 6.5 4 4" /></svg>`,
};

/* Two magnifiers (- and +: the size of the whole page), light or dark, and the palettes. */
function themeButtons() {
  const TH = T.theme, pct = Math.round(window.textZoom.get() * 100), toggle = currentMode() === "dark" ? TH.toLight : TH.toDark;
  const button = (id, title, icon, disabled) => `<button type="button" class="icon" data-tool="${id}" title="${esc(title)}" aria-label="${esc(title)}"${disabled ? " disabled" : ""}>${icon}</button>`;
  return button("zoom-out", TH.zoomOut(pct), THEME_ICONS.zoom(false), !window.textZoom.canShrink())
    + button("zoom-in", TH.zoomIn(pct), THEME_ICONS.zoom(true), !window.textZoom.canGrow())
    + button("mode", toggle, THEME_ICONS.mode) + button("palettes", TH.palettes, THEME_ICONS.palette);
}

/* `redraw`: draws the header again (the bubbles of the buttons say the size and the mode). */
function bindThemeButtons(root, redraw) {
  const on = (id, action) => { const b = root.querySelector(`[data-tool="${id}"]`); if (b) b.onclick = action; };
  const refocus = id => root.querySelector(`[data-tool="${id}"]:not(:disabled)`)?.focus();   // the header is drawn again: keep the keyboard there
  on("zoom-out", () => { window.textZoom.step(-1); redraw(); refocus("zoom-out"); });
  on("zoom-in", () => { window.textZoom.step(1); redraw(); refocus("zoom-in"); });
  on("mode", () => { setThemeMode(currentMode() === "dark" ? "light" : "dark"); redraw(); refocus("mode"); });
  on("palettes", () => openThemeDialog(redraw));
}

// --- the Theme window ---
let themeEdit = null;   // the palette being edited: {id, mode, builtin, name, colors, isNew}, null for the list

function openThemeDialog(redraw) {
  let dialog = $("#theme-dialog");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "theme-dialog";
    dialog.className = "theme-dialog";
    document.body.appendChild(dialog);
    dialog.addEventListener("click", e => { if (e.target === dialog) dialog.close(); });   // a click on the backdrop
    dialog.addEventListener("close", () => { themeEdit = null; redraw(); });
  }
  themeEdit = null;
  drawThemeDialog(dialog, redraw);
  if (!dialog.open) dialog.showModal();
}

function drawThemeDialog(dialog, redraw) {
  const TH = T.theme;
  const head = `<div class="dialog-head"><h2>${TH.title}</h2><button type="button" class="close" aria-label="${TH.close}" data-close>×</button></div>`;
  if (themeEdit) return drawThemeEditor(dialog, redraw, head);
  const mode = document.documentElement.dataset.theme || "system";
  const swatch = id => {
    const c = window.themes.colorsOf(id);   // changed or the user's: its own colours over style.css
    return `<span class="swatch" data-palette="${esc(id)}"${c ? ` style="${styleOf(window.themes.tokens(c))}"` : ""} aria-hidden="true"><i></i><i></i><i></i></span>`;
  };
  dialog.innerHTML = `${head}
    <h3>${TH.mode}</h3>
    <div class="checks">${["system", "light", "dark"].map(m => `<label class="check"><input type="radio" name="theme-mode" value="${m}"${mode === m ? " checked" : ""}> ${TH.modes[m]}</label>`).join("")}</div>
    ${["light", "dark"].map(m => `
      <h3>${TH.modePalettes[m]} <button type="button" class="small-button" data-new="${m}">${TH.newButton}</button></h3>
      <div class="palettes">${palettesOf(m).map(id => {
        const builtin = window.themes.palettes[m].includes(id), changed = builtin && !!paletteOverrides()[id];
        return `<div class="palette-card">
          <label class="palette"><input type="radio" name="palette-${m}" value="${esc(id)}"${paletteOf(m) === id ? " checked" : ""}>
            ${swatch(id)}
            <span><span class="name">${esc(paletteName(id))}</span>
              <span class="desc">${builtin ? TH.names[id][1] : TH.yours}${changed ? ` · ${TH.changed}` : ""}</span></span>
            ${levelBadge(checkTheme(paletteColors(id)).level)}</label>
          <button type="button" class="icon edit" data-edit="${esc(id)}" data-mode="${m}" aria-label="${esc(TH.editTitle(paletteName(id)))}" title="${esc(TH.editTitle(paletteName(id)))}">${THEME_ICONS.pencil}</button>
        </div>`;
      }).join("")}</div>`).join("")}
    <p class="muted small">${TH.help}</p>`;
  const again = () => { redraw(); drawThemeDialog(dialog, redraw); };
  dialog.querySelector("[data-close]").onclick = () => dialog.close();
  dialog.querySelectorAll("[name=theme-mode]").forEach(r => r.onchange = () => { setThemeMode(r.value); again(); });
  for (const m of ["light", "dark"]) dialog.querySelectorAll(`[name=palette-${m}]`).forEach(r => r.onchange = () => {
    themeStore.remember("palette-" + m, r.value);
    window.themes.apply();
    again();
  });
  dialog.querySelectorAll("[data-edit]").forEach(b => b.onclick = () => {
    const id = b.dataset.edit, m = b.dataset.mode;
    themeEdit = { id, mode: m, builtin: window.themes.palettes[m].includes(id), name: customThemes()[id]?.name || "", colors: { ...paletteColors(id) }, isNew: false };
    drawThemeDialog(dialog, redraw);
  });
  dialog.querySelectorAll("[data-new]").forEach(b => b.onclick = () => {
    const m = b.dataset.new;
    themeEdit = { id: "theme-" + Date.now().toString(36), mode: m, builtin: false, name: "", colors: { ...paletteColors(paletteOf(m)) }, isNew: true };
    drawThemeDialog(dialog, redraw);
  });
}

/* The editor of one palette: its 4 colours, a preview and the check of the contrasts, both following the colours. */
function drawThemeEditor(dialog, redraw, head) {
  const TH = T.theme, edit = themeEdit, HEX = /^#[0-9a-f]{6}$/i;
  const done = () => { themeEdit = null; redraw(); drawThemeDialog(dialog, redraw); };
  const changedBuiltin = edit.builtin && !!paletteOverrides()[edit.id];
  dialog.innerHTML = `${head}
    <div class="theme-editor">
      <h3>${edit.isNew ? TH.new : esc(TH.editTitle(paletteName(edit.id)))}</h3>
      ${edit.builtin ? "" : `<label class="theme-name">${TH.name}
        <input type="text" id="theme-name" value="${esc(edit.name)}" maxlength="40" placeholder="${esc(TH.untitled)}"></label>`}
      <div class="color-fields">${THEME_COLORS.map(k => `<div class="color-field">
        <label for="theme-color-${k}">${TH.colors[k]}</label>
        <input type="color" id="theme-color-${k}" data-color="${k}" value="${esc(edit.colors[k])}">
        <input type="text" class="hex" data-hex="${k}" value="${esc(edit.colors[k])}" spellcheck="false" maxlength="7" aria-label="${esc(TH.colors[k])} (hex)">
      </div>`).join("")}</div>
      <div class="theme-preview" id="theme-preview"><div class="preview-card">
        <strong>${TH.preview.title}</strong><span class="preview-muted">${TH.preview.muted}</span>
        <span class="preview-link">${TH.preview.link}</span><span class="preview-field">${TH.preview.field}</span>
        <span class="preview-button">${TH.preview.button}</span></div></div>
      <div class="theme-check" id="theme-check" aria-live="polite"></div>
      <div class="actions">
        <button type="button" class="primary" data-save>${TH.save}</button>
        <button type="button" data-cancel>${TH.cancel}</button>
        <span class="spacer"></span>
        ${edit.builtin ? `<button type="button" data-reset title="${esc(TH.resetTitle)}"${changedBuiltin ? "" : " disabled"}>${TH.reset}</button>` : ""}
        ${!edit.builtin && !edit.isNew ? `<button type="button" class="danger" data-delete>${TH.delete}</button>` : ""}
      </div>
    </div>`;
  const follow = () => {
    const result = checkTheme(edit.colors), mode = modeOfColors(edit.colors);
    $("#theme-preview").style.cssText = styleOf(window.themes.tokens(edit.colors));
    $("#theme-check").innerHTML = `
      <p><span>${TH.checkTitle}</span> ${levelBadge(result.level)}</p>
      <p class="muted small">${TH.levelHelp[result.level]}</p>
      <ul>${result.rows.map(r => `<li class="level-row level-row-${r.level}"><span>${TH.pairs[r.key]}</span>
        <span class="ratio">${r.ratio.toFixed(1)}:1</span>
        <span>${r.ui ? TH.levels[r.level === "fail" ? "fail" : "uiOk"] : TH.levels[r.level]}</span></li>`).join("")}</ul>
      ${edit.builtin && mode !== edit.mode ? `<p class="muted small">${TH.mismatch[mode]}</p>` : ""}
      ${edit.builtin ? "" : `<p class="muted small">${TH.goesTo[mode]}</p>`}`;
  };
  dialog.querySelector("[data-close]").onclick = () => dialog.close();
  dialog.querySelectorAll("[data-color]").forEach(i => i.oninput = () => {
    edit.colors[i.dataset.color] = i.value;
    dialog.querySelector(`[data-hex="${i.dataset.color}"]`).value = i.value;
    follow();
  });
  dialog.querySelectorAll("[data-hex]").forEach(i => i.oninput = () => {
    if (!HEX.test(i.value)) return;   // being typed
    edit.colors[i.dataset.hex] = i.value.toLowerCase();
    dialog.querySelector(`[data-color="${i.dataset.hex}"]`).value = edit.colors[i.dataset.hex];
    follow();
  });
  dialog.querySelector("[data-cancel]").onclick = done;
  dialog.querySelector("[data-save]").onclick = () => {
    if (edit.builtin) {
      const o = paletteOverrides(), f = factoryColors(edit.id);   // style.css, whatever the user changed: the probe is not <html>
      if (THEME_COLORS.every(k => f[k].toLowerCase() === edit.colors[k].toLowerCase())) delete o[edit.id];
      else o[edit.id] = edit.colors;
      themeStore.write("palette-overrides", o);
    } else {
      const all = customThemes();
      all[edit.id] = { name: ($("#theme-name").value || "").trim() || TH.untitled, colors: edit.colors };
      themeStore.write("custom-themes", all);
      themeStore.remember("palette-" + modeOfColors(edit.colors), edit.id);   // a new or changed theme of the user: chosen for its mode
    }
    window.themes.apply();
    done();
  };
  const reset = dialog.querySelector("[data-reset]");
  if (reset) reset.onclick = () => {
    const o = paletteOverrides();
    delete o[edit.id];
    themeStore.write("palette-overrides", o);
    window.themes.apply();
    done();
  };
  const remove = dialog.querySelector("[data-delete]");
  if (remove) remove.onclick = () => {
    if (!remove.dataset.sure) { remove.dataset.sure = "1"; remove.textContent = TH.deleteConfirm; return; }   // asked twice
    const all = customThemes();
    delete all[edit.id];
    themeStore.write("custom-themes", all);
    window.themes.apply();
    done();
  };
  follow();
}
