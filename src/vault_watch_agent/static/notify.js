/* vault-watch: notifications of the browser, a bell in the header, off by default. Loaded before app.js, which owns
   the texts (T.notify) and the helpers used here (esc, lang). Taken from dl-sub-dub (subtitles/web/static/v2/notify.js),
   written without Preact.

   The browser asks its permission only on a click on the bell (never by itself, never again once refused: the bell
   then says how to allow it in the browser). When on, the page asks the server every 15 s what stopped
   (GET /api/notices: a run waiting for the review or the go-ahead to publish, a pull request opened, a run or a check
   ended or stopped by an error) and notifies it while the page is not in sight. A click on the notification brings
   the page back, on the run or the check concerned. The server sends the texts in both languages (web.py MESSAGES:
   the same as the desktop notifications of `serve --notify`). */

const NOTIFY_TEXTS = {
  fr: {
    off: "Notifications désactivées : cliquer pour être prévenu quand une passe attend ta relecture ou ton feu vert, se termine ou s'arrête sur une erreur (le navigateur demandera l'autorisation)",
    on: "Notifications activées (relecture à faire, publication à valider, fin ou erreur d'une passe), quand la page n'est pas affichée : cliquer pour les désactiver",
    blocked: "Notifications refusées pour cette page dans le navigateur : pour les autoriser, cliquer sur l'icône à gauche de l'adresse, puis Notifications",
    refused: "Le navigateur n'a pas autorisé les notifications : la cloche reste désactivée. Rien ne sera redemandé.",
  },
  en: {
    off: "Notifications off: click to be told when a run waits for your review or your go-ahead, ends or stops on an error (the browser will ask for permission)",
    on: "Notifications on (review pending, publish pending, end or error of a run), while the page is not in sight: click to turn them off",
    blocked: "Notifications refused for this page in the browser: to allow them, click the icon left of the address, then Notifications",
    refused: "The browser did not allow notifications: the bell stays off. Nothing will be asked again.",
  },
};

const notify = {
  supported: () => typeof window.Notification === "function",
  permission: () => (notify.supported() ? Notification.permission : "denied"),
  wanted: () => { try { return localStorage.getItem("notify") === "on"; } catch { return false; } },
  want: on => { try { if (on) localStorage.setItem("notify", "on"); else localStorage.removeItem("notify"); } catch { /* this page only */ } },
  active: () => notify.wanted() && notify.permission() === "granted",
  said: "",        // what the bell answered to the last click, shown beside it for a few seconds
  last: null,      // id of the last notice seen; null until the first answer of the server
  timer: null,
};

function notifyButton() {
  if (!notify.supported()) return "";
  const N = T.notify, on = notify.active(), title = notify.permission() === "denied" ? N.blocked : on ? N.on : N.off;
  return `<button type="button" class="icon notify${on ? " on" : ""}" data-tool="notify" title="${esc(title)}" aria-label="${esc(title)}" aria-pressed="${on}">
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4l2-2zM10 20a2 2 0 0 0 4 0" />${on ? "" : '<path d="M4 4l16 16" />'}</svg></button>${
    notify.said ? `<span class="notify-said" role="status">${esc(notify.said)}</span>` : ""}`;
}

/* `redraw`: draws the header again. */
function bindNotifyButton(root, redraw) {
  const b = root.querySelector('[data-tool="notify"]');
  if (!b) return;
  const say = text => { notify.said = text; setTimeout(() => { notify.said = ""; redraw(); }, 8000); };
  b.onclick = async () => {
    if (notify.active()) notify.want(false);
    else if (notify.permission() === "denied") say(T.notify.blocked);
    else {
      const answer = notify.permission() === "granted" ? "granted" : await Notification.requestPermission();
      notify.want(answer === "granted");
      if (answer !== "granted") say(T.notify.refused);
    }
    watchNotices();
    redraw();
    root.querySelector('[data-tool="notify"]')?.focus();
  };
}

/* Asks the server what stopped, while the bell is on; a notice is shown only while the page is not in sight. */
function watchNotices() {
  clearInterval(notify.timer);
  notify.timer = null;
  if (!notify.active()) { notify.last = null; return; }
  const ask = async () => {
    let d;
    try { d = await fetch(notify.last == null ? "/api/notices" : `/api/notices?since=${notify.last}`).then(r => r.json()); } catch { return; }   // server stopped: later
    if (typeof d?.last !== "number") return;
    if (d.last < (notify.last ?? 0)) { notify.last = d.last; return; }   // the server started again: its count too
    notify.last = d.last;
    if (document.visibilityState === "visible" && document.hasFocus()) return;   // in sight: the page itself says it
    for (const n of d.notices) {
      const text = n[lang] || n.en;
      try {
        const note = new Notification(text.title, { body: text.body, tag: `vault-watch-${n.id}` });
        note.onclick = () => { window.focus(); location.hash = n.page.slice(1); note.close(); };
      } catch { /* a browser that refuses notifications from a page (Android Chrome): nothing */ }
    }
  };
  ask();
  notify.timer = setInterval(ask, 15000);
}
