/* « Give my opinion »: a note out of five, a kind (opinion, bug, idea), a message, all optional. Nothing is sent
   by the agent: the reader sends it, as an issue of the agent's repository (public, a GitHub account) or by e-mail
   (no account), or copies the text. What is sent is shown before. It never says anything of the guide: its name,
   its pages and the run being looked at stay here; the version always goes, the system, Python, the engine and the
   screen only when the box is ticked.

   The issue is the form .github/ISSUE_TEMPLATE/feedback.yml, filled in by its address: the ids of its fields
   (rating, type, message, version, environment) are those `feedbackFields` gives. A security flaw never goes to
   that public form: its button opens the private report of the repository (the message copied, to paste there), and
   the mail stays.

   Needs from app.js: $, esc, extLink, info, lang, T (T.feedback is FEEDBACK_TEXTS of the language). */

const FEEDBACK_TEXTS = {
  fr: {
    open: "Donner mon avis", title: "Donner mon avis",
    intro: "Une note, un avis, un bug ou une idée : tout est facultatif, une seule information suffit. L'agent n'envoie rien : c'est toi qui envoies, par le moyen de ton choix.",
    rating: "Ta note", ratingOf: n => `${n} sur 5`, noRating: "Pas de note", clear: "retirer la note",
    type: "C'est plutôt", types: { opinion: "Un avis", bug: "Un bug", idea: "Une idée", security: "Une faille de sécurité" },
    message: "Ton message", messageHelp: { opinion: "Ce qui te plaît, ce qui te gêne, ce qui manque.", bug: "Ce que tu as fait, ce qui s'est passé, ce que tu attendais.", idea: "Ce que tu voudrais pouvoir faire, et pourquoi.", security: "Ce qui est exposé, comment le reproduire, ce qu'un attaquant pourrait en faire." },
    securityIntro: "Une faille se signale en privé : pas de ticket public, qui la montrerait à tout le monde avant qu'elle soit corrigée.",
    private: "Signaler en privé sur GitHub", privateHelp: "Avec un compte GitHub ; seuls les mainteneurs le voient. Ton message est copié : colle-le dans le formulaire qui s'ouvre.",
    emailPrivate: a => `Sans compte, et privé lui aussi : ouvre ta messagerie avec le message prêt, pour ${a}.`,
    securitySubject: v => `Faille de sécurité dans vault-watch ${v}`,
    diagnostic: "Joindre les informations techniques",
    diagnosticWhat: d => `Ajoute : ${d}. La version est toujours jointe. Rien du guide n'est transmis : ni son nom, ni ses pages, ni le passage affiché.`,
    preview: "Ce qui sera envoyé",
    github: "Ouvrir un ticket GitHub", githubHelp: "Public, avec un compte GitHub. Tu relis le ticket avant de le publier.",
    email: "Envoyer par e-mail", emailHelp: a => `Sans compte, et privé : ouvre ta messagerie avec le message prêt, pour ${a}.`,
    noEmail: "L'envoi par e-mail n'est pas proposé par cette version.",
    copy: "Copier le texte", copied: "Copié", copyHelp: "Pour le coller où tu veux.",
    needs: "Donne au moins une note, un type ou un message pour pouvoir envoyer.",
    cut: "Le message est trop long pour être transmis en entier par ce moyen : il sera coupé. « Copier le texte » le garde entier.",
    security: "Une faille de sécurité ? Ne l'écris pas dans un ticket public :", securityLink: "la signaler en privé",
    close: "Fermer", subject: v => `Retour sur vault-watch ${v}`,
    labels: { rating: "Note", type: "Type", message: "Message", version: "Version", environment: "Environnement" },
  },
  en: {
    open: "Give my opinion", title: "Give my opinion",
    intro: "A note, an opinion, a bug or an idea: everything is optional, one piece of information is enough. The agent sends nothing: you send it, the way you choose.",
    rating: "Your note", ratingOf: n => `${n} out of 5`, noRating: "No note", clear: "remove the note",
    type: "It is rather", types: { opinion: "An opinion", bug: "A bug", idea: "An idea", security: "A security flaw" },
    message: "Your message", messageHelp: { opinion: "What you like, what gets in your way, what is missing.", bug: "What you did, what happened, what you expected.", idea: "What you would like to be able to do, and why.", security: "What is exposed, how to reproduce it, what an attacker could do with it." },
    securityIntro: "A flaw is reported privately: no public issue, which would show it to everyone before it is fixed.",
    private: "Report privately on GitHub", privateHelp: "With a GitHub account; only the maintainers see it. Your message is copied: paste it in the form that opens.",
    emailPrivate: a => `No account, and private too: opens your mail program with the message ready, for ${a}.`,
    securitySubject: v => `Security flaw in vault-watch ${v}`,
    diagnostic: "Attach the technical information",
    diagnosticWhat: d => `Adds: ${d}. The version is always attached. Nothing of the guide is sent: not its name, not its pages, not the run shown.`,
    preview: "What will be sent",
    github: "Open a GitHub issue", githubHelp: "Public, with a GitHub account. You read the issue again before you publish it.",
    email: "Send by e-mail", emailHelp: a => `No account, and private: opens your mail program with the message ready, for ${a}.`,
    noEmail: "This version does not offer to send by e-mail.",
    copy: "Copy the text", copied: "Copied", copyHelp: "To paste it wherever you want.",
    needs: "Give at least a note, a kind or a message to be able to send.",
    cut: "The message is too long to be sent whole this way: it will be cut. « Copy the text » keeps all of it.",
    security: "A security flaw? Do not write it in a public issue:", securityLink: "report it privately",
    close: "Close", subject: v => `Feedback on vault-watch ${v}`,
    labels: { rating: "Rating", type: "Type", message: "Message", version: "Version", environment: "Environment" },
  },
};

const FEEDBACK_ICON = `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M12 13.2 9.4 10.7a1.7 1.7 0 0 1 2.4-2.4l.2.2.2-.2a1.7 1.7 0 0 1 2.4 2.4z"/></svg>`;
const FEEDBACK_MAX = { issue: 8000, mail: 1800 };   // the longest address an issue form, a mail program takes
const STARS = { 5: "★★★★★ 5/5", 4: "★★★★☆ 4/5", 3: "★★★☆☆ 3/5", 2: "★★☆☆☆ 2/5", 1: "★☆☆☆☆ 1/5" };
const TYPE_NAMES = { opinion: "Opinion", bug: "Bug", idea: "Idea", security: "Security" };   // as the issue form names them (English, like the repository)
const isSecurity = f => f.type === "security";   // never a public issue: the private report of the repository, or a mail
let feedback = null;   // what is being written: {rating, type, message, diagnostic, touched}

/* The fields of the issue form, by id; an answer not given is not sent. `screen`: the kind of screen shown (#/check),
   never the run or the check it shows. */
function feedbackFields(f, message = f.message.trim()) {
  const out = {};
  if (f.rating && !isSecurity(f)) out.rating = STARS[f.rating];   // a flaw is not rated
  if (f.type) out.type = TYPE_NAMES[f.type];
  if (message) out.message = message;
  out.version = info?.version || "?";
  if (f.diagnostic) out.environment = feedbackDiagnostic();
  return out;
}
function feedbackDiagnostic() {
  const screen = (location.hash.match(/^#\/[a-z]*/) || ["#/"])[0];
  return [info?.system, info?.python && `Python ${info.python}`, info?.engine && `engine ${info.engine}`, `screen ${screen}`].filter(Boolean).join(" · ");
}
function feedbackText(f, message) {
  const fields = feedbackFields(f, message), L = T.feedback.labels;
  const head = ["rating", "type"].filter(k => k in fields).map(k => `${L[k]}${T.colon}${fields[k]}`).join("\n");
  const tail = ["version", "environment"].filter(k => k in fields).map(k => `${L[k]}${T.colon}${fields[k]}`).join("\n");
  return [head, fields.message ? `${L.message}${T.colon.trimEnd()}\n${fields.message}` : "", tail].filter(Boolean).join("\n\n");
}
function feedbackTitle(f) {
  return [`[Feedback] ${f.type ? TYPE_NAMES[f.type] : "Opinion"}`, ...(f.rating ? [`${f.rating}/5`] : []), `v${info?.version || "?"}`].join(" · ");
}
/* The longest address under `max`: the whole message when it fits, else cut (by halving) with a note. */
function feedbackFit(message, build, max) {
  if (build(message).length <= max || !message) return { url: build(message), cut: false };
  const chars = Array.from(message), note = "\n\n[…]";
  let low = 0, high = chars.length - 1;
  while (low < high) {
    const mid = Math.ceil((low + high) / 2);
    if (build(chars.slice(0, mid).join("").trimEnd() + note).length <= max) low = mid; else high = mid - 1;
  }
  return { url: build(chars.slice(0, low).join("").trimEnd() + note), cut: true };
}
function feedbackIssue(f) {
  return feedbackFit(f.message.trim(), message => {
    const q = new URLSearchParams({ template: "feedback.yml", title: feedbackTitle(f), labels: "feedback", ...feedbackFields(f, message) });
    return `${info.agent}/issues/new?${q.toString().replace(/\+/g, "%20")}`;
  }, FEEDBACK_MAX.issue);
}
function feedbackMail(f) {
  const enc = text => encodeURIComponent(text.replace(/\r?\n/g, "\r\n"));
  return feedbackFit(f.message.trim(), message =>
    `mailto:${info.feedback_email}?subject=${enc(feedbackSubject(f))}&body=${enc(feedbackText(f, message))}`, FEEDBACK_MAX.mail);
}
const feedbackSubject = f => (isSecurity(f) ? T.feedback.securitySubject : T.feedback.subject)(info?.version || "?");
// Something to send: a note, a kind or a message; for a flaw, a message (its kind alone says nothing)
const feedbackReady = f => isSecurity(f) ? Boolean(f.message.trim()) : Boolean(f.rating || f.type || f.message.trim());

function openFeedback() {
  let dialog = $("#feedback-dialog");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "feedback-dialog";
    dialog.setAttribute("aria-labelledby", "feedback-title");
    document.body.appendChild(dialog);
    dialog.addEventListener("click", e => { if (e.target === dialog) dialog.close(); });   // a click outside: what was written stays
  }
  feedback = feedback || { rating: 0, type: "", message: "", diagnostic: false, touched: false };
  drawFeedback();
  if (!dialog.open) dialog.showModal();
}

function drawFeedback() {
  const dialog = $("#feedback-dialog"), F = T.feedback, f = feedback;
  const ready = feedbackReady(f), issue = feedbackIssue(f), mail = info?.feedback_email ? feedbackMail(f) : null, flaw = isSecurity(f);
  dialog.innerHTML = `
    <div class="dialog-head"><h2 id="feedback-title">${F.title}</h2><button type="button" class="close" data-close aria-label="${F.close}">×</button></div>
    <p class="muted">${F.intro}</p>
    <fieldset class="stars"${flaw ? " hidden" : ""}><legend>${F.rating}</legend>
      ${[1, 2, 3, 4, 5].map(n => `<label title="${F.ratingOf(n)}"><input type="radio" name="rating" value="${n}"${f.rating === n ? " checked" : ""}>
        <span class="star${n <= f.rating ? " on" : ""}" aria-hidden="true">★</span><span class="sr-only">${F.ratingOf(n)}</span></label>`).join("")}
      <span class="muted stars-said">${f.rating ? F.ratingOf(f.rating) : F.noRating}</span>
      ${f.rating ? `<button type="button" class="link" data-clear>${F.clear}</button>` : ""}
    </fieldset>
    <fieldset class="cfg-seg-set"><legend>${F.type}</legend><div class="cfg-seg">
      ${Object.entries(F.types).map(([k, name]) => `<label><input type="radio" name="type" value="${k}"${f.type === k ? " checked" : ""}><span>${name}</span></label>`).join("")}
    </div></fieldset>
    ${flaw ? `<p class="banner small">${F.securityIntro}</p>` : ""}
    <label class="field" for="feedback-message">${F.message}</label>
    <textarea id="feedback-message" rows="5" placeholder="${esc(F.messageHelp[f.type || "opinion"])}">${esc(f.message)}</textarea>
    <label class="check"><input type="checkbox" id="feedback-diagnostic"${f.diagnostic ? " checked" : ""}> ${F.diagnostic}</label>
    <p class="muted small">${esc(F.diagnosticWhat(feedbackDiagnostic()))}</p>
    <details${ready ? " open" : ""}><summary>${F.preview}</summary><pre id="feedback-preview">${esc(feedbackText(f))}</pre></details>
    <div class="send">
      ${flaw ? `<div><a class="button primary${ready ? "" : " disabled"}" ${ready ? `href="${esc(info.agent)}/security/advisories/new" target="_blank" rel="noopener"` : 'aria-disabled="true"'} id="feedback-private">${F.private} ↗</a>
        <p class="muted small">${F.privateHelp}</p></div>`
      : `<div><a class="button primary${ready ? "" : " disabled"}" ${ready ? `href="${esc(issue.url)}" target="_blank" rel="noopener"` : 'aria-disabled="true"'} id="feedback-issue">${F.github} ↗</a>
        <p class="muted small">${F.githubHelp}</p></div>`}
      ${mail ? `<div><a class="button${ready ? "" : " disabled"}" ${ready ? `href="${esc(mail.url)}"` : 'aria-disabled="true"'} id="feedback-mail">${F.email}</a>
        <p class="muted small">${esc((flaw ? F.emailPrivate : F.emailHelp)(info.feedback_email))}</p></div>` : ""}
      <div><button type="button" id="feedback-copy"${ready ? "" : " disabled"}>${F.copy}</button>
        <p class="muted small">${F.copyHelp}${mail ? "" : ` ${F.noEmail}`}</p></div>
    </div>
    ${ready ? "" : `<p class="attention-text small" role="status">${F.needs}</p>`}
    ${ready && ((!flaw && issue.cut) || mail?.cut) ? `<p class="attention-text small" role="status">${F.cut}</p>` : ""}
    ${flaw ? "" : `<p class="small security">${F.security} <button type="button" class="link" data-flaw>${F.securityLink}</button></p>`}`;
  // Drawn again after each answer (the preview and the addresses follow), the keyboard kept where it was
  const redraw = focus => { drawFeedback(); const el = focus && $("#feedback-dialog").querySelector(focus); if (el) el.focus(); };
  dialog.querySelector("[data-close]").onclick = () => dialog.close();
  dialog.querySelectorAll("[name=rating]").forEach(r => r.onchange = () => { f.rating = Number(r.value); redraw(`[name=rating][value="${r.value}"]`); });
  const clear = dialog.querySelector("[data-clear]");
  if (clear) clear.onclick = () => { f.rating = 0; redraw("[name=rating]"); };
  dialog.querySelectorAll("[name=type]").forEach(r => r.onchange = () => {
    f.type = r.value;
    if (!f.touched) f.diagnostic = f.type === "bug" || f.type === "security";   // rarely understood without them; the box says so and can be unticked
    redraw(`[name=type][value="${r.value}"]`);
  });
  const message = $("#feedback-message");
  message.oninput = () => {   // typed: the rest follows without the field being drawn again
    const was = feedbackReady(f);
    f.message = message.value;
    if (feedbackReady(f) !== was) { const at = message.selectionStart; drawFeedback(); const m = $("#feedback-message"); m.focus(); m.setSelectionRange(at, at); return; }
    $("#feedback-preview").textContent = feedbackText(f);
    if (feedbackReady(f)) {
      if ($("#feedback-issue")) $("#feedback-issue").href = feedbackIssue(f).url;
      if ($("#feedback-mail")) $("#feedback-mail").href = feedbackMail(f).url;
    }
  };
  // The private report of GitHub is not filled in by its address: the message is copied, to be pasted there
  const priv = $("#feedback-private");
  if (priv) priv.onclick = () => { navigator.clipboard?.writeText(feedbackText(f)).catch(() => {}); };
  const toFlaw = dialog.querySelector("[data-flaw]");
  if (toFlaw) toFlaw.onclick = () => { f.type = "security"; if (!f.touched) f.diagnostic = true; redraw("[name=type][value=security]"); };
  $("#feedback-diagnostic").onchange = e => { f.diagnostic = e.target.checked; f.touched = true; redraw("#feedback-diagnostic"); };
  $("#feedback-copy").onclick = async () => {
    try { await navigator.clipboard.writeText(`${feedbackSubject(f)}\n\n${feedbackText(f)}`); $("#feedback-copy").textContent = F.copied; }
    catch { const p = $("#feedback-preview"); p.closest("details").open = true; getSelection().selectAllChildren(p); }   // no clipboard: the text is selected
  };
}

/* The button of the header and of the footer: an icon and its name. */
function feedbackButton(extra = "") {
  return `<button type="button" class="feedback ${extra}" data-feedback title="${esc(T.feedback.open)}">${FEEDBACK_ICON}<span>${T.feedback.open}</span></button>`;
}
function bindFeedback(root) {
  root.querySelectorAll("[data-feedback]").forEach(b => b.onclick = openFeedback);
}
