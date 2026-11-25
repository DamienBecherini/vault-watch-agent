// @ts-check
/* vault-watch: the page's entry module (index.html loads it with type="module"). One screen per pause of the graph:
   the server holds every state (checkpoints), this page only shows it and sends the human's answers. Interface in
   French or English (toggle in the header, remembered); the guide's own text stays in French.
   Each module imports what it uses from the others:
   - util.js: the helpers of every screen ($, esc, links, a help bubble, the room for a bar, a screen followed)
   - api.js: the calls of the server's API, and what the server says of itself (/api/info)
   - texts.js: the texts of the interface in both languages (T); explain.js: a model's English lines translated
   - header.js: the header and its menus; router.js: which screen the address shows
   - watches.js: « To handle », the automatic watch, every run, the guide's folder
   - checks.js and check.js: « Check the guide » and the page of one check (rules.js: what may be ticked)
   - run.js and the screens of a run's pauses: review.js, retouch.js, proofread.js, translation.js (pairs.js),
     publish.js; diff.js and editor.js show what changed
   - steps.js: the engine, model and effort of a run's steps, and what things cost
   - report.js, sources.js, languages.js, chapters.js, costs.js: the other screens
   - themes.js, notify.js, settings.js, feedback.js: the buttons of the header and their windows
   boot.js stays a plain script in <head>: it sets the mode, the palette and the size of the text before the first
   paint, and leaves window.themes and window.textZoom to themes.js and the others. */

import { $ } from "./util.js";
import { api, onSubscription, setInfo } from "./api.js";
import { route } from "./router.js";
import { header } from "./header.js";
import { watchNotices } from "./notify.js";

header();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { window.themes.apply(); header(); });  // the system's mode changes (evening): follow it
// The height of the header (it wraps on a narrow window, grows with the text): what sticks under it starts there
new ResizeObserver(() => document.documentElement.style.setProperty("--header-h", `${$("header").offsetHeight}px`)).observe($("header"));
watchNotices();
route();
// The engine in use arrives a moment later (the server asks Claude Code): on a subscription, the costs shown change
api("/api/info").then(i => { setInfo(i); header(); if (onSubscription()) route(); }).catch(() => {});
