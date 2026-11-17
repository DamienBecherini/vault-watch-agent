/* Before the first paint (a plain script in <head>): the mode (light, dark or the system's), the palette of that mode
   and the size of the text, kept in this browser. Taken from dl-sub-dub (subtitles/web/static/boot.js), with the
   colours of this page.

   Palettes: the built-in ones live in style.css (data-palette on <html>). A theme of the user, or a built-in palette
   the user changed, is 4 colours (background, text, secondary text, accent) from which the other colours are derived
   (window.themes.tokens) and set on <html> as CSS variables, over those of style.css. Kept in localStorage:
   "theme" (light or dark; absent: the system's), "palette-light" and "palette-dark" (the palette of each mode),
   "custom-themes" {id: {name, colors}} and "palette-overrides" {built-in id: colors}.

   The size is a zoom of the whole page (text, buttons and spaces together, as the browser's own zoom), so that the
   targets grow with the text; window.textZoom changes it, for the magnifier buttons of the header ("zoom"). */
(function () {
  var root = document.documentElement;

  function read(key, fallback) {
    try { var v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); } catch (e) { return fallback; }
  }

  // --- colours ---
  function rgb(hex) {
    var h = String(hex).replace("#", "");
    if (h.length === 3) h = h.replace(/./g, "$&$&");
    return [0, 2, 4].map(function (i) { return parseInt(h.substr(i, 2), 16) || 0; });
  }
  function hex(c) { return "#" + c.map(function (x) { return ("0" + Math.round(Math.max(0, Math.min(255, x))).toString(16)).slice(-2); }).join(""); }
  function mix(a, b, t) { var x = rgb(a), y = rgb(b); return hex(x.map(function (v, i) { return v + (y[i] - v) * t; })); }
  function luminance(c) {
    var v = rgb(c).map(function (x) { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); });
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
  }
  /* WCAG contrast ratio, 1 to 21. */
  function contrast(a, b) {
    var x = luminance(a), y = luminance(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  }
  var isDark = function (bg) { return luminance(bg) < 0.18; };

  /* The CSS variables of a theme from its 4 colours {bg, text, muted, accent}. The colours of the states (ok,
     attention, error, the diff) stay those of the mode (style.css). */
  function tokens(c) {
    var dark = isDark(c.bg);
    var card = dark ? mix(c.bg, c.text, 0.05) : mix(c.bg, "#ffffff", 0.75);
    return {
      "--bg": c.bg, "--card": card, "--text": c.text, "--muted": c.muted, "--accent": c.accent,
      "--accent-text": contrast("#ffffff", c.accent) >= contrast("#111111", c.accent) ? "#ffffff" : "#111111",
      "--border": mix(card, c.text, dark ? 0.18 : 0.13),
      "--field-border": mix(card, c.text, 0.5)
    };
  }

  /* The colours of a theme the user made or changed, or null for a built-in palette left as it is. */
  function colorsOf(id) {
    var custom = read("custom-themes", {})[id];
    if (custom) return custom.colors;
    return read("palette-overrides", {})[id] || null;
  }

  var PALETTES = { light: ["azure", "slate", "sand", "sage", "lavender", "raspberry"], dark: ["azure-night", "night", "warm", "olive", "embers"] };   // style.css
  var applied = [];
  function apply() {
    var t = null;
    try { t = localStorage.getItem("theme"); } catch (e) { /* default */ }
    if (t === "light" || t === "dark") root.dataset.theme = t; else { t = null; delete root.dataset.theme; }
    var mode = t || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    var id = null;
    try { id = localStorage.getItem("palette-" + mode); } catch (e) { /* default */ }
    var custom = read("custom-themes", {});
    if (id && custom[id] && isDark(custom[id].colors.bg) !== (mode === "dark")) id = null;   // a theme of the other mode
    if (id && !custom[id] && PALETTES[mode].indexOf(id) < 0) id = null;                       // a theme deleted
    root.dataset.palette = id || PALETTES[mode][0];
    applied.forEach(function (k) { root.style.removeProperty(k); });
    applied = [];
    var c = colorsOf(root.dataset.palette);
    if (c) {
      var v = tokens(c);
      for (var k in v) { root.style.setProperty(k, v[k]); applied.push(k); }
    }
  }
  window.themes = { palettes: PALETTES, tokens: tokens, contrast: contrast, isDark: isDark, colorsOf: colorsOf, apply: apply };
  apply();

  // --- size ---
  var STEPS = [0.8, 0.9, 1, 1.1, 1.25, 1.4, 1.6];
  function get() {
    try { var z = parseFloat(localStorage.getItem("zoom")); return STEPS.indexOf(z) >= 0 ? z : 1; } catch (e) { return 1; }
  }
  var current = get();
  function zoom(z) {
    current = z;
    root.style.zoom = z === 1 ? "" : String(z);
  }
  window.textZoom = {
    get: function () { return current; },
    canGrow: function () { return STEPS.indexOf(current) < STEPS.length - 1; },
    canShrink: function () { return STEPS.indexOf(current) > 0; },
    /* +1: larger, -1: smaller; remembered. */
    step: function (d) {
      var i = STEPS.indexOf(current) + d;
      if (i < 0 || i >= STEPS.length) return current;
      zoom(STEPS[i]);
      try { if (current === 1) localStorage.removeItem("zoom"); else localStorage.setItem("zoom", String(current)); } catch (e) { /* this page only */ }
      return current;
    }
  };
  zoom(current);
})();
