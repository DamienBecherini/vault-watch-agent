// @ts-check
/* vault-watch: which screen the address shows. Routes: #/ (to handle), #/watches, #/runs, #/run/<thread>, #/check,
   #/check/<id>, #/sources, #/candidates, #/report, #/idea, #/links, #/languages, #/costs, #/chapters, #/settings (the window of
   settings.js, over the first page). */

import { $, esc, forgetBar, keepRoomForBar, page, stopFollowing } from "./util.js";
import { T } from "./texts.js";
import { OWN } from "./steps.js";
import { refreshTodo, viewRuns, viewTodo, viewWatches } from "./watches.js";
import { closeSource, viewRun } from "./run.js";
import { asideBanner } from "./retouch.js";
import { NEW_CHECK, setNewCheck, viewChecks } from "./checks.js";
import { viewCheck } from "./check.js";
import { viewLinks, viewReport } from "./report.js";
import { viewSources } from "./sources.js";
import { viewLanguages } from "./languages.js";
import { leaveChapters, viewChapters } from "./chapters.js";
import { viewCosts } from "./costs.js";
import { viewCandidates } from "./candidates.js";
import { openSettings } from "./settings.js";

// --- Router --------------------------------------------------------------------------------------
let shownHash = "";  // the screen OWN belongs to
export async function route() {
  closeSource();
  stopFollowing();
  let h = location.hash.slice(1) || "/";
  if (h !== shownHash) {
    Object.keys(OWN).forEach(k => delete OWN[k]);
    shownHash = h;
    // « Chapters »: what was said there is said once; what is being edited stays, unless it was saved
    leaveChapters();
  }
  if (h === "/settings") {   // an address to open the Settings: the window, over the first page
    history.replaceState(null, "", "#/");
    h = "/";
    openSettings();
  }
  const here = h === "/" ? "todo" : ["/idea", "/links"].includes(h) ? "report" : h.startsWith("/run/") ? "runs" : h.split("/")[1].split("?")[0];
  /** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll("nav [data-nav]")).forEach(a => a.classList.toggle("active", a.dataset.nav === here));
  $("#watch-menu").classList.toggle("active", ["todo", "watches", "check", "sources", "candidates", "runs"].includes(here));
  if (!$("header").classList.contains("narrow")) $("#watch-menu").open = false;
  page.innerHTML = `<p class="muted">${T.loading}</p>`;
  forgetBar();  // the room left for a check's bar, until it is drawn again
  try {
    if (h.startsWith("/run/")) await viewRun(decodeURIComponent(h.slice(5)));
    else if (h.startsWith("/check/")) await viewCheck(decodeURIComponent(h.slice(7)));
    else if (h === "/check" || h.startsWith("/check?new")) {  // #/check?new=<check>: that check ticked
      setNewCheck(h !== "/check", h.split("?new=")[1] || ""); await viewChecks(); if (NEW_CHECK) $("#new-check")?.scrollIntoView();
    }
    else if (h === "/sources") await viewSources();
    else if (h === "/candidates") await viewCandidates();
    else if (h === "/links") await viewLinks();
    else if (h === "/report" || h === "/idea") await viewReport(h === "/idea");
    else if (h === "/costs") await viewCosts();
    else if (h === "/languages") await viewLanguages();
    else if (h === "/chapters") await viewChapters();
    else if (h === "/watches") await viewWatches();
    else if (h === "/runs") await viewRuns();
    else await viewTodo();
    if (h !== "/") refreshTodo();
    keepRoomForBar();
    asideBanner();
  } catch (e) {
    page.innerHTML = `<p class="error-text">${esc(e.message)}</p>`;
    console.error(e);  // a view that failed: in the console as well, where a bug of the page shows its stack
  }
}
addEventListener("hashchange", route);
