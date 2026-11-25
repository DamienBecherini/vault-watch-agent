// @ts-check
/* vault-watch: the header: the menus « Watch » and the guide's, the tools (size of the text, mode, palettes, bell,
   language, Settings), « Give my opinion », and the header folded under one button on a narrow window. */

import { $, esc, extLink } from "./util.js";
import { forgeName, info } from "./api.js";
import { lang, setLang, T } from "./texts.js";
import { route } from "./router.js";
import { showTodoCount } from "./watches.js";
import { openSettings, SETTINGS_ICONS } from "./settings.js";
import { bindThemeButtons, themeButtons } from "./themes.js";
import { bindNotifyButton, notifyButton } from "./notify.js";
import { bindFeedback, feedbackButton } from "./feedback.js";

export function header() {
  document.documentElement.lang = lang;
  /** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll("nav > a[data-nav]")).forEach(a => a.textContent = T.nav[a.dataset.nav]);
  $("#watch-menu-name").textContent = T.nav.menu;
  const entry = (h, k, dot) => `<a href="#/${h}" data-nav="${k}"><span class="dot ${dot}"></span><span><b>${T.nav[k]}</b><small>${
    typeof T.navHelp[k] === "function" ? T.navHelp[k]() : T.navHelp[k]}</small></span>${k === "todo" ? '<span class="count" data-todo-count hidden></span>' : ""}</a>`;
  $("#watch-items").innerHTML = `${entry("", "todo", "todo")}<hr>${entry("watches", "watches", "auto")}${entry("check", "check", "check")}${
    entry("sources", "sources", "auto")}${entry("candidates", "candidates", "check")}<hr>${entry("runs", "runs", "runs")}`;
  showTodoCount();
  // The guide's menu: its name opens its site, its repository and its chapters (one guide per server)
  $("#guide-name").textContent = info?.guide || "";
  $("#guide-menu").hidden = !info;
  $("#guide-menu > summary").title = T.menu.open;
  const guideLinks = info ? [
    info.site && extLink(info.site, `${T.menu.site} ↗`),
    info.repo_url && extLink(info.repo_url, `${T.menu.repo(forgeName())} ↗`),
    `<a href="#/chapters">${T.menu.chapters}</a>`].filter(Boolean).join("") : "";
  $("#guide-links").innerHTML = guideLinks;
  // A narrow window: these links and the agent's code are in the one menu, under the pages (the name is then a text)
  $("#menu-more").innerHTML = info ? guideLinks + extLink(info.agent, `${T.menu.code} ↗`) : "";
  $("#burger").title = T.menu.burger;
  $("#burger").setAttribute("aria-label", T.menu.burger);
  // « Give my opinion » (feedback.js): a button of the header, and again in the footer with the version and the code
  $("#feedback-slot").innerHTML = info ? feedbackButton() : "";
  $("#footer").innerHTML = info?.version ? `<span>vault-watch ${esc(info.version)}</span>${extLink(info.agent, `${T.menu.code} ↗`)}${feedbackButton("quiet")}` : "";
  bindFeedback(document);
  fitHeader();
  document.title = info?.guide ? `vault-watch · ${info.guide}` : "vault-watch";
  // The size of the text, light or dark, the palettes (themes.js), the bell (notify.js), the language, the Settings
  const tools = $("#tools");
  tools.innerHTML = `${themeButtons()}${notifyButton()}<span class="langs">${["fr", "en"].map(l =>
    `<button data-lang="${l}" class="${l === lang ? "active" : ""}" aria-pressed="${l === lang}">${l.toUpperCase()}</button>`).join("")}</span>
    <button type="button" class="icon" data-tool="settings" title="${T.settings.open}" aria-label="${T.settings.open}">${SETTINGS_ICONS.gear}</button>`;
  tools.querySelector('[data-tool="settings"]').onclick = openSettings;
  bindThemeButtons(tools, header);
  bindNotifyButton(tools, header);
  tools.querySelectorAll("[data-lang]").forEach(b => b.onclick = () => {
    setLang(b.dataset.lang);
    try { localStorage.setItem("vault-watch-lang", lang); } catch { /* private window: per page only */ }
    header();
    route();
  });
}

// The guide's menu closes when one of its links is followed, on a click elsewhere, and with Escape
document.addEventListener("click", /** @param {MouseEvent & {target: Element}} e */ e => {
  const narrow = $("header").classList.contains("narrow");
  ["#guide-menu", "#watch-menu"].map($).forEach(menu => {
    if (menu.open && !(narrow && menu.id === "watch-menu") && (!menu.contains(e.target) || e.target.closest("a"))) menu.open = false;
  });
  if (e.target.closest("#header-menu a")) foldHeader();   // a page chosen in the folded menu: it closes
  const named = e.target.closest(".edit-label");   // the line above an editable box: into the box, nothing ticked
  if (named?.nextElementSibling?.matches("textarea")) { e.preventDefault(); /** @type {HTMLElement} */ (named.nextElementSibling).focus(); }
});
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  $("#guide-menu").open = false;
  if (!$("header").classList.contains("narrow")) $("#watch-menu").open = false;
  if ($("header").classList.contains("open")) { foldHeader(); $("#burger").focus(); }
});

// A narrow header (under 800 px of its own width, so the size of the text counts: boot.js zooms the page) keeps the
// name of the agent and of the guide, and folds the rest under one button. Under 1 180 px the button « Give my
// opinion » shows its icon alone. The width is the header's, not the window's: a media query would not see the zoom.
function fitHeader() {
  const head = $("header"), narrow = head.clientWidth < 800;
  head.classList.toggle("narrow", narrow);
  head.classList.toggle("compact", !narrow && head.clientWidth < 1180);
  if (!narrow) head.classList.remove("open");
  $("#burger").setAttribute("aria-expanded", String(head.classList.contains("open")));
  // The name of the guide: a menu on a wide header, a text on a narrow one (its links are in the folded menu)
  const name = $("#guide-menu > summary");
  name.tabIndex = narrow ? -1 : 0;
  if (narrow) $("#guide-menu").open = false;
  const watch = $("#watch-menu");
  if (narrow !== watch.classList.contains("unfolded")) { watch.open = narrow; watch.classList.toggle("unfolded", narrow); }
  watch.querySelector("summary").tabIndex = narrow ? -1 : 0;
}
function foldHeader() {
  $("header").classList.remove("open");
  $("#burger").setAttribute("aria-expanded", "false");
}
$("#burger").onclick = () => {
  const open = $("header").classList.toggle("open");
  $("#burger").setAttribute("aria-expanded", String(open));
};
$("#guide-menu > summary").addEventListener("click", e => { if ($("header").classList.contains("narrow")) e.preventDefault(); });
$("#watch-menu > summary").addEventListener("click", e => { if ($("header").classList.contains("narrow")) e.preventDefault(); });
new ResizeObserver(fitHeader).observe($("header"));
