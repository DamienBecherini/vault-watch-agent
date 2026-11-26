// @ts-check
/* vault-watch: « Candidates » (ROADMAP D3.2): the registry of discovery, what the agent found that the guide does
   not cover yet, followed over time (candidates.py). Changed here in a draft of the agent, published by a pull request
   of the guide (routes/candidates.py); « Propose an addition » takes a candidate to the screen of an addition run. */

import { $, esc, extLink, page, shortUrl, tip } from "./util.js";
import { api } from "./api.js";
import { addTexts, lang, T } from "./texts.js";
import { proposeCandidate } from "./report.js";

const CANDIDATES_TEXTS = {
  fr: {
    title: "Candidats",
    proposing: name => `Pour le candidat « ${name} » du registre : il deviendra « Proposé » quand la passe démarrera.`,
    forget: "Ne plus le lier",
    intro: "Ce que l'agent a trouvé et que le guide ne couvre pas encore : un modèle, un outil, un matériel. Plutôt que d'être trié une fois puis oublié, chacun est suivi : mis en observation avec une date pour le revoir, écarté avec sa raison, ou proposé comme ajout. La collecte de la veille ne repropose pas ce que le registre suit, et liste ceux dont la date est arrivée.",
    states: { lead: "Piste", watching: "En observation", confirmed: "Confirmé", proposed: "Proposé", added: "Ajouté", dismissed: "Écarté" },
    kinds: { model: "Modèle", tool: "Outil", hardware: "Matériel", other: "Autre" },
    all: "Tous",
    none: "Aucun candidat pour l'instant. Ajoute ici ce que tu as repéré ; la veille, les vérifications et la collecte en ajouteront ensuite d'elles-mêmes.",
    noneHere: "Aucun candidat dans cet état.",
    due: n => `${n} candidat(s) à revoir : leur date est arrivée.`,
    dueBadge: "à revoir",
    seen: (first, last) => first === last ? `vu le ${first}` : `vu du ${first} au ${last}`,
    lookAgain: d => `à revoir le ${d}`,
    sources: n => `${n} source(s)`,
    history: "Historique",
    facts: {
      licence: "licence", params: n => `${n} de paramètres`, context: n => `contexte ${n}`, gguf: "GGUF disponible",
      downloads: n => `${n} téléchargements`, likes: n => `${n} likes`, gated: "accès sur demande", updated: d => `mis à jour le ${d}`,
      stars: n => `${n} étoiles`, release: (t, d) => `version ${t}${d ? ` du ${d}` : ""}`, contributors: n => `${n} contributeurs`,
      pushed: d => `dernier commit le ${d}`, archived: "archivé", read: d => { const [day, time] = String(d).split(" "); return time ? `lu le ${day} à ${time}` : `lu le ${day}`; },
    },
    readAgain: "Relire",
    readAgainTip: "Relit ce que dit chaque adresse du candidat là où le guide sait lire (son manifeste, candidate_readers : licence, taille, versions…), sans modèle ni coût.",
    readFailed: list => `Lecture impossible : ${list}`,
    add: "Ajouter un candidat",
    addHelp: "Un nom déjà suivi, ou une adresse déjà connue, ajoute seulement la source au candidat existant.",
    name: "Nom", url: "Adresse (facultative)", kind: "Type", note: "Pourquoi (facultatif)",
    addButton: "Ajouter",
    known: name => `Déjà suivi : cette adresse est ajoutée aux sources de « ${name} », pas de nouvelle carte.`,
    knownSame: name => `Déjà suivi : « ${name} » a déjà cette adresse, rien n'a changé.`,
    addedNew: "Ajouté.",
    reread: t => `Relu à ${t}.`,
    watch: "Mettre en observation", dismiss: "Écarter", confirm: "Confirmer", lead: "Remettre en piste", added: "Marquer ajouté",
    propose: "Proposer un ajout",
    tips: {
      watch: "Pas encore assez pour le guide (pas de poids, pas de mesure…) : à revoir à une date. La veille te le rappellera.",
      dismiss: "Ne convient pas au guide : la raison reste, et une date pour le revoir si la situation peut changer.",
      confirm: "Vérifié : sa place dans le guide est acquise, il reste à l'y écrire.",
      propose: "Ouvre « Proposer un ajout » avec ce candidat : la passe d'ajout vérifie sur le web et écrit là où il faut. Le candidat devient « Proposé ».",
      added: "Le guide le couvre maintenant (la pull request de son ajout est fusionnée).",
    },
    reason: "Raison", reasonNeeded: "Raison (obligatoire)", reasonMissing: "Dis pourquoi tu l'écartes : la raison reste dans le registre.", date: "À revoir le", ok: "Valider", cancel: "Annuler",
    draftTitle: n => `Changements à publier (${n})`,
    draftHelp: "Tes changements restent dans un brouillon de l'agent : ton dossier du guide n'est pas touché. Le registre est un fichier du guide, lu par sa collecte hebdomadaire ; il change par une pull request.",
    inPr: "Tous ces changements sont dans la pull request ouverte.",
    pending: url => `Une pull request publie le registre : ${extLink(url, "pull request ↗")}. Publier à nouveau y ajoute un commit.`,
    path: "Fichier du registre dans le guide",
    pathHelp: (manifest, needs) => `Le manifeste (${manifest}) ne nomme pas encore de registre : la pull request l'y ajoute. Il faudra vault-watch-agent ${needs} ou plus là où le guide est lu (le workflow de la collecte compris) avant de la fusionner.`,
    publish: "Publier le registre",
    publishLocal: "Enregistrer le registre sur une branche",
    discard: "Abandonner ces changements",
    confirmDiscard: "Abandonner les changements non publiés du registre ?",
    published: (branch, url) => url ? `Publié : ${extLink(url, "pull request ↗")} (branche ${esc(branch)}).` : `Enregistré sur la branche ${esc(branch)} (le guide n'a pas de dépôt).`,
    change: {
      new: c => `<b>${esc(c.name)}</b> ajouté (${esc(c.state)})`,
      state: c => `<b>${esc(c.name)}</b> : ${esc(c.from)} → ${esc(c.state)}`,
      sources: c => `<b>${esc(c.name)}</b> : ${c.n} source(s) en plus`,
      removed: c => `<b>${esc(c.name)}</b> retiré`,
      merged: c => `<b>${esc(c.name)}</b> fusionné dans <b>${esc(c.into)}</b>`,
      judged: c => `<b>${esc(c.name)}</b> jugé avec le guide : ${esc(c.verdict)}`,
    },
    score: n => `score ${n}`,
    scoreTip: (e, tiers) => `Le score de l'entité (ce candidat et ceux de sa famille, ensemble) : le rang de chaque éditeur indépendant qui en a parlé (A 3, B 2, C ou non classé 1), additionnés, multiplié par les semaines où il a été vu. Ici : ${e.publishers.map(p => `${p.publisher}${p.tier ? ` (${p.tier})` : ""}`).join(", ") || "aucune source"}, ${e.weeks} semaine(s).${tiers ? "" : " Le guide ne déclare pas de fichier de rangs (source_tiers dans son manifeste) : chaque source compte 1."}`,
    corroborated: "2 sources A/B",
    corroboratedTip: "Au moins deux éditeurs indépendants de rang A ou B en parlent : le seuil que le guide demande avant d'écrire. À vérifier avant de confirmer.",
    family: "Même famille :",
    familyTip: "Le même nom sans ce qui distingue une version d'une autre (taille, variante, quantification, date). Si c'est la même chose, fusionne : les sources, les informations lues et l'historique vont dans ce candidat, et l'autre nom reste un de ses noms.",
    merge: name => `Fusionner « ${name} » ici`,
    confirmMerge: (other, into) => `Fusionner « ${other} » dans « ${into} » ? Il disparaît du registre ; ses sources et son historique vont dans « ${into} ».`,
    merged: name => `« ${name} » fusionné ici.`,
    aka: "aussi nommé",
    sortBy: "Ordre :", sortState: "par état", sortScore: "par score",
    judge: n => `Juger avec le guide (${n} ouvert(s))`,
    judgeTip: "Une vérification payante : Claude lit tout le guide avec les candidats ouverts (piste, en observation, confirmé) et dit de chacun s'il faut l'ajouter (où, et quelle décision du lecteur il change), le surveiller ou l'écarter. Rien n'est vérifié sur le web ; le jugement reste ici, et les candidats à ajouter que tu gardes partent dans une passe d'ajouts. L'estimation s'affiche avant de lancer.",
    verdicts: { add: "à ajouter", watch: "à surveiller", dismiss: "à écarter" },
    judged: (date, verdict) => `Jugé avec le guide le ${date} : ${verdict}`,
    seeCheck: "voir la vérification",
  },
  en: {
    title: "Candidates",
    proposing: name => `For the candidate « ${name} » of the registry: it becomes « Proposed » when the run starts.`,
    forget: "Unlink it",
    intro: "What the agent found that the guide does not cover yet: a model, a tool, a piece of hardware. Instead of being triaged once and forgotten, each is followed: watched with a date to look again, dismissed with its reason, or proposed as an addition. The collection of the watch does not propose again what the registry tracks, and lists those whose date has come.",
    states: { lead: "Lead", watching: "Watching", confirmed: "Confirmed", proposed: "Proposed", added: "Added", dismissed: "Dismissed" },
    kinds: { model: "Model", tool: "Tool", hardware: "Hardware", other: "Other" },
    all: "All",
    none: "No candidate yet. Add here what you spotted; the watch, the checks and the collection will add theirs later.",
    noneHere: "No candidate in this state.",
    due: n => `${n} candidate(s) to look at again: their date has come.`,
    dueBadge: "look again",
    seen: (first, last) => first === last ? `seen on ${first}` : `seen from ${first} to ${last}`,
    lookAgain: d => `look again on ${d}`,
    sources: n => `${n} source(s)`,
    history: "History",
    facts: {
      licence: "licence", params: n => `${n} parameters`, context: n => `context ${n}`, gguf: "GGUF available",
      downloads: n => `${n} downloads`, likes: n => `${n} likes`, gated: "access on request", updated: d => `updated on ${d}`,
      stars: n => `${n} stars`, release: (t, d) => `release ${t}${d ? ` of ${d}` : ""}`, contributors: n => `${n} contributors`,
      pushed: d => `last commit on ${d}`, archived: "archived", read: d => { const [day, time] = String(d).split(" "); return time ? `read on ${day} at ${time}` : `read on ${day}`; },
    },
    readAgain: "Read again",
    readAgainTip: "Reads again what each address of the candidate says where the guide can read (its manifest, candidate_readers: licence, size, releases…), no model, no cost.",
    readFailed: list => `Could not read: ${list}`,
    add: "Add a candidate",
    addHelp: "A name already followed, or an address already known, only adds the source to the existing candidate.",
    name: "Name", url: "Address (optional)", kind: "Kind", note: "Why (optional)",
    addButton: "Add",
    known: name => `Already followed: this address is added to the sources of « ${name} », no new card.`,
    knownSame: name => `Already followed: « ${name} » has this address already, nothing changed.`,
    addedNew: "Added.",
    reread: t => `Read again at ${t}.`,
    watch: "Watch", dismiss: "Dismiss", confirm: "Confirm", lead: "Back to lead", added: "Mark added",
    propose: "Propose an addition",
    tips: {
      watch: "Not enough for the guide yet (no weights, no measure…): to look at again on a date. The watch will remind you.",
      dismiss: "Not for the guide: the reason stays, and a date to look again if things may change.",
      confirm: "Checked: its place in the guide is settled, it remains to write it there.",
      propose: "Opens « Propose an addition » with this candidate: the addition run checks on the web and writes where it belongs. The candidate becomes « Proposed ».",
      added: "The guide covers it now (the pull request of its addition is merged).",
    },
    reason: "Reason", reasonNeeded: "Reason (required)", reasonMissing: "Say why you dismiss it: the reason stays in the registry.", date: "Look again on", ok: "Apply", cancel: "Cancel",
    draftTitle: n => `Changes to publish (${n})`,
    draftHelp: "Your changes stay in a draft of the agent: your folder of the guide is not touched. The registry is a file of the guide, read by its weekly collection; it changes through a pull request.",
    inPr: "All these changes are in the open pull request.",
    pending: url => `A pull request publishes the registry: ${extLink(url, "pull request ↗")}. Publishing again adds a commit to it.`,
    path: "File of the registry in the guide",
    pathHelp: (manifest, needs) => `The manifest (${manifest}) names no registry yet: the pull request adds it. It will need vault-watch-agent ${needs} or newer wherever the guide is read (the collection's workflow included) before merging it.`,
    publish: "Publish the registry",
    publishLocal: "Save the registry on a branch",
    discard: "Drop these changes",
    confirmDiscard: "Drop the changes of the registry not published?",
    published: (branch, url) => url ? `Published: ${extLink(url, "pull request ↗")} (branch ${esc(branch)}).` : `Saved on the branch ${esc(branch)} (the guide has no repository).`,
    change: {
      new: c => `<b>${esc(c.name)}</b> added (${esc(c.state)})`,
      state: c => `<b>${esc(c.name)}</b>: ${esc(c.from)} → ${esc(c.state)}`,
      sources: c => `<b>${esc(c.name)}</b>: ${c.n} more source(s)`,
      removed: c => `<b>${esc(c.name)}</b> removed`,
      merged: c => `<b>${esc(c.name)}</b> merged into <b>${esc(c.into)}</b>`,
      judged: c => `<b>${esc(c.name)}</b> judged with the guide: ${esc(c.verdict)}`,
    },
    score: n => `score ${n}`,
    scoreTip: (e, tiers) => `The score of the entity (this candidate and those of its family, together): the tier of each independent publisher that spoke of it (A 3, B 2, C or unclassified 1), added up, times the weeks it was seen. Here: ${e.publishers.map(p => `${p.publisher}${p.tier ? ` (${p.tier})` : ""}`).join(", ") || "no source"}, ${e.weeks} week(s).${tiers ? "" : " The guide declares no file of tiers (source_tiers in its manifest): every source counts 1."}`,
    corroborated: "2 A/B sources",
    corroboratedTip: "At least two independent publishers of tier A or B speak of it: the threshold the guide asks before writing. Check before confirming.",
    family: "Same family:",
    familyTip: "The same name without what tells one release from another (size, variant, quantisation, date). If it is the same thing, merge: the sources, the facts read and the history come to this candidate, and the other name stays one of its names.",
    merge: name => `Merge « ${name} » here`,
    confirmMerge: (other, into) => `Merge « ${other} » into « ${into} »? It leaves the registry; its sources and history go to « ${into} ».`,
    merged: name => `« ${name} » merged here.`,
    aka: "also named",
    sortBy: "Order:", sortState: "by state", sortScore: "by score",
    judge: n => `Judge with the guide (${n} open)`,
    judgeTip: "A paid check: Claude reads the whole guide with the open candidates (lead, watching, confirmed) and says of each whether to add it (where, and which decision of the reader it changes), to watch it or to dismiss it. Nothing is verified on the web; the judgement stays here, and the candidates to add you keep go to an addition run. The estimate shows before you start.",
    verdicts: { add: "to add", watch: "to watch", dismiss: "to dismiss" },
    judged: (date, verdict) => `Judged with the guide on ${date}: ${verdict}`,
    seeCheck: "see the check",
  },
};
addTexts("candidates", CANDIDATES_TEXTS);

// Numbers as the reader reads them: 7.6 B, 1.2 M, 32 768
const big = n => typeof n !== "number" ? String(n) : n >= 1e9 ? `${(n / 1e9).toLocaleString(lang, { maximumFractionDigits: 1 })} B`
  : n >= 1e6 ? `${(n / 1e6).toLocaleString(lang, { maximumFractionDigits: 1 })} M` : n.toLocaleString(lang);
// What a reader of the guide says of an address of a candidate (enrich.py), in one line; `labels` names the readers
const factLine = (f, C, labels) => {
  const F = C.facts;
  const bits = f.source === "huggingface"
    ? [f.licence && `${F.licence} ${esc(f.licence)}`, f.params && F.params(big(f.params)), f.context && F.context(big(f.context)),
      f.gguf && F.gguf, f.gated && F.gated, f.downloads != null && F.downloads(big(f.downloads)), f.updated && F.updated(esc(f.updated))]
    : f.source === "github"
    ? [f.licence && `${F.licence} ${esc(f.licence)}`, f.stars != null && F.stars(big(f.stars)),
      f.release && F.release(esc(f.release), esc(f.released || "")), f.contributors != null && F.contributors(esc(f.contributors)),
      f.pushed && F.pushed(esc(f.pushed)), f.archived && `<b>${F.archived}</b>`]
    : [f.licence && `${F.licence} ${esc(f.licence)}`];  // a reader this page does not lay out yet
  return `<li><span class="badge neutral">${esc((labels || {})[f.source] || f.source)}</span> ${bits.filter(Boolean).join(" · ")}
    <span class="muted">(${F.read(esc(f.read))})</span>${f.description ? `<br><span class="muted">${esc(f.description)}</span>` : ""}</li>`;
};

// What the check « candidates » said of a candidate (D4): its verdict, why, where, when to look again
const judgementBlock = j => {
  const C = T.candidates;
  return `<div class="small judgement"><span class="badge ${j.verdict === "add" ? "ok" : "neutral"}">${esc(C.judged(j.date, C.verdicts[j.verdict] || j.verdict))}</span>
    <a href="#/check/${encodeURIComponent(j.check)}">${C.seeCheck}</a>
    <p>${esc(j.matters || j.why || "")}</p>${(j.pages || []).length ? `<p class="muted">${j.pages.map(p => `<code>${esc(p)}</code>`).join(", ")}</p>` : ""}${
    j.recheck ? `<p class="muted">${C.lookAgain(esc(j.recheck))}</p>` : ""}</div>`;
};

let FILTER = "";  // the state shown, "" for all
let SORT = "state";  // or "score" (D2): the entities most seen by the best sources first
let SAID = "";    // said once at the top after an action on the registry (a publication)
let FLASH = null; // said once on the card an action concerns, brought into view: {id, text, error}

// The line of a candidate in the draft of « Propose an addition »: its name, kind, sources and what was said of it
const leadLine = (c, C) => `${c.name} (${C.kinds[c.kind] || c.kind})${(c.sources || []).length ? ` : ${c.sources.map(s => s.url).filter(Boolean).join(" ")}` : ""}${c.reason ? ` (${c.reason})` : ""}`;

export async function viewCandidates() {
  const d = await api("/api/candidates"), C = T.candidates;
  const stateOf = s => C.states[s] || s;
  const due = new Set(d.due);
  const byId = id => d.candidates.find(c => c.id === id);
  const count = s => d.candidates.filter(c => c.state === s).length;
  const E = d.entities || {};
  const scoreOf = c => E[c.id]?.score || 0;
  const shown = d.candidates.filter(c => !FILTER || c.state === FILTER);
  if (SORT === "score") shown.sort((a, b) => scoreOf(b) - scoreOf(a));
  const changeLine = c => C.change[c.what]({ ...c, from: stateOf(c.from), state: stateOf(c.state),
    verdict: C.verdicts[c.verdict] || c.verdict });
  const actions = c => {
    const b = (state, label, help, cls = "") => `<span><button type="button" class="small-button ${cls}" data-act="${state}" data-id="${esc(c.id)}">${label}</button>${help ? tip(help) : ""}</span>`;
    const out = [];
    if (!["proposed", "added"].includes(c.state)) out.push(`<span><button type="button" class="small-button primary" data-propose="${esc(c.id)}">${C.propose}</button>${tip(C.tips.propose)}</span>`);
    if (["lead", "dismissed", "confirmed"].includes(c.state)) out.push(b("watching", C.watch, C.tips.watch));
    if (["lead", "watching"].includes(c.state)) out.push(b("confirmed", C.confirm, C.tips.confirm));
    if (["proposed", "confirmed"].includes(c.state)) out.push(b("added", C.added, C.tips.added));
    if (c.state !== "lead" && c.state !== "added") out.push(b("lead", C.lead, ""));
    if (c.state !== "dismissed" && c.state !== "added") out.push(b("dismissed", C.dismiss, C.tips.dismiss, "danger"));
    if (c.state === "watching") out.push(b("watching", `${C.date}…`, ""));
    if ((d.readable || []).includes(c.id))
      out.push(`<span><button type="button" class="small-button" data-enrich="${esc(c.id)}">↻ ${C.readAgain}</button>${tip(C.readAgainTip)}</span>`);
    return out.join("");
  };
  const card = c => `<div class="card candidate" data-card="${esc(c.id)}">
      <div class="header"><b>${esc(c.name)}</b> <span class="badge neutral">${esc(C.kinds[c.kind] || c.kind)}</span>
        <span class="badge ${c.state === "dismissed" ? "neutral" : c.state === "added" ? "ok" : "attention"}">${esc(stateOf(c.state))}</span>
        ${due.has(c.id) ? `<span class="badge error">${C.dueBadge}</span>` : ""}
        ${E[c.id] ? `<span class="badge neutral">${C.score(E[c.id].score)}</span>${tip(C.scoreTip(E[c.id], d.tiers))}` : ""}
        ${E[c.id]?.corroborated ? `<span class="badge ok">${C.corroborated}</span>${tip(C.corroboratedTip)}` : ""}</div>
      ${(c.aka || []).length ? `<p class="muted small">${C.aka} ${c.aka.map(esc).join(", ")}</p>` : ""}
      ${(E[c.id]?.group || []).length ? `<p class="small">${C.family} ${E[c.id].group.map(o => `<span>${esc(byId(o)?.name || o)}
        <button type="button" class="small-button" data-merge="${esc(o)}" data-into="${esc(c.id)}">${C.merge(esc(byId(o)?.name || o))}</button></span>`).join(" ")}${tip(C.familyTip)}</p>` : ""}
      <p class="muted small">${C.seen(esc(c.first_seen), esc(c.last_seen))}${c.recheck ? ` · ${C.lookAgain(esc(c.recheck))}` : ""}</p>
      ${c.reason ? `<p class="small">${esc(c.reason)}</p>` : ""}
      ${c.judgement ? judgementBlock(c.judgement) : ""}
      ${(c.sources || []).length ? `<ul class="small">${c.sources.map(s => `<li>${extLink(s.url, esc(s.title || shortUrl(s.url)))} <span class="muted">${esc(s.seen)} · ${esc(s.origin)}</span></li>`).join("")}</ul>` : ""}
      ${(c.facts || []).length ? `<ul class="small facts">${c.facts.map(f => factLine(f, C, d.reader_labels)).join("")}</ul>` : ""}
      <details class="small"><summary>${C.history}</summary><ul>${(c.history || []).map(h => `<li>${esc(h.date)} · ${esc(stateOf(h.state))}${h.note ? ` : ${esc(h.note)}` : ""}${h.recheck ? ` (${C.lookAgain(esc(h.recheck))})` : ""}</li>`).join("")}</ul></details>
      <div class="actions">${actions(c)}</div>
      <div class="move-form" hidden></div>
    </div>`;
  const open = d.candidates.filter(c => ["lead", "watching", "confirmed"].includes(c.state)).length;
  const pending = d.pending?.pr_url;
  const asksPath = !d.declared && !pending;
  page.innerHTML = `
    <h1>${C.title}</h1>
    <p class="subtitle">${C.intro}</p>
    ${pending ? `<p class="banner">${C.pending(d.pending.pr_url)}</p>` : ""}
    ${SAID ? `<p class="banner">${SAID}</p>` : ""}
    ${d.due.length ? `<p class="banner">${C.due(d.due.length)}</p>` : ""}
    ${d.changes.length ? `<div class="card" id="draft"><div class="header"><b>${C.draftTitle(d.changes.length)}</b></div>
      <ul class="small">${d.changes.map(c => `<li>${changeLine(c)}</li>`).join("")}</ul>
      ${d.unpublished ? `<p class="muted small">${C.draftHelp}</p>
        ${asksPath ? `<p><label class="small">${C.path} <input type="text" id="reg-path" value="${esc(d.path)}" spellcheck="false"></label></p>
          <p class="muted small">${C.pathHelp(esc(d.manifest), esc(d.needs))}</p>` : ""}
        <p class="actions"><button type="button" class="primary" id="publish">${d.has_repo ? C.publish : C.publishLocal}</button>
          <button type="button" class="small-button danger" id="discard">${C.discard}</button> <span class="error-text small" id="publish-error"></span></p>`
        : `<p class="muted small">${C.inPr}</p>`}
    </div>` : ""}
    ${open ? `<p><a href="#/check?new=candidates"><button type="button">${C.judge(open)}</button></a>${tip(C.judgeTip)}</p>` : ""}
    <p class="small">${C.sortBy} <select id="c-sort"><option value="state"${SORT === "state" ? " selected" : ""}>${C.sortState}</option><option value="score"${SORT === "score" ? " selected" : ""}>${C.sortScore}</option></select></p>
    <p class="tabs">${["", ...d.states].map(s => `<a href="#" data-filter="${s}"${s === FILTER ? ' class="active"' : ""}>${s ? stateOf(s) : C.all} (${s ? count(s) : d.candidates.length})</a>`).join("")}</p>
    <div id="list">${shown.map(card).join("") || `<p class="muted">${d.candidates.length ? C.noneHere : C.none}</p>`}</div>
    <h2>${C.add}</h2>
    <p class="muted small">${C.addHelp}</p>
    <div class="card"><div class="chapter-fields">
      <label class="small">${C.name}<input type="text" id="c-name" maxlength="120"></label>
      <label class="small">${C.url}<input type="url" id="c-url" spellcheck="false"></label>
      <label class="small">${C.kind}<select id="c-kind">${d.kinds.map(k => `<option value="${esc(k)}">${esc(C.kinds[k] || k)}</option>`).join("")}</select></label>
      <label class="small">${C.note}<input type="text" id="c-note" maxlength="300"></label>
    </div><p><button type="button" id="c-add">${C.addButton}</button> <span class="error-text small" id="add-error"></span></p></div>`;
  SAID = "";
  // The card an action concerns: its message on it, in view (the list may be long, the form is below it)
  if (FLASH) {
    const card = page.querySelector(`[data-card="${CSS.escape(FLASH.id)}"]`);
    if (card) {
      card.classList.add("flash");
      card.insertAdjacentHTML("afterbegin", `<p class="${FLASH.error ? "error-text" : "attention-text"} small" data-flash>${FLASH.text}</p>`);
      card.scrollIntoView({ block: "center" });
    }
    FLASH = null;
  }

  page.querySelectorAll("[data-filter]").forEach(a => a.addEventListener("click", e => {
    e.preventDefault();
    FILTER = /** @type {HTMLElement} */ (a).dataset.filter || "";
    viewCandidates();
  }));
  page.querySelectorAll("[data-propose]").forEach(b => b.addEventListener("click", () => {
    const c = byId(/** @type {HTMLElement} */ (b).dataset.propose);
    if (c) proposeCandidate(c, leadLine(c, C));
  }));
  $("#c-sort").onchange = e => { SORT = /** @type {HTMLSelectElement} */ (e.target).value; viewCandidates(); };
  page.querySelectorAll("[data-merge]").forEach(b => b.addEventListener("click", async () => {
    const { merge: other, into } = /** @type {HTMLElement} */ (b).dataset;
    if (!other || !into || !confirm(C.confirmMerge(byId(other)?.name || other, byId(into)?.name || into))) return;
    try {
      await api(`/api/candidates/${encodeURIComponent(into)}/merge`, { other });
      FLASH = { id: into, text: C.merged(esc(byId(other)?.name || other)), error: false };
    } catch (e) { FLASH = { id: into, text: esc(e.message), error: true }; }
    viewCandidates();
  }));
  page.querySelectorAll("[data-enrich]").forEach(b => b.addEventListener("click", async () => {
    const id = /** @type {HTMLElement} */ (b).dataset.enrich || "";
    /** @type {HTMLButtonElement} */ (b).disabled = true;
    try {
      const r = await api(`/api/candidates/${encodeURIComponent(id)}/enrich`, {});
      const time = new Date().toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });
      FLASH = { id, text: r.errors?.length ? C.readFailed(esc(r.errors.join(" ; "))) : C.reread(time), error: !!r.errors?.length };
      viewCandidates();
    } catch (e) { FLASH = { id, text: esc(e.message), error: true }; viewCandidates(); }
  }));
  const move = async (id, body, error) => {
    try { await api(`/api/candidates/${encodeURIComponent(id)}`, body); viewCandidates(); }
    catch (e) { error.textContent = e.message; }
  };
  page.querySelectorAll("[data-act]").forEach(b => b.addEventListener("click", () => {
    const { act, id } = /** @type {HTMLElement} */ (b).dataset;
    const c = byId(id), box = /** @type {HTMLElement} */ (b.closest("[data-card]")), form = /** @type {HTMLElement} */ (box.querySelector(".move-form"));
    if (!c || !act) return;
    if (!["watching", "dismissed"].includes(act)) { move(id, { state: act }, form); return; }
    // Watching or dismissed: a reason (needed to dismiss) and a date to look again
    form.hidden = false;
    form.innerHTML = `<div class="chapter-fields">
        <label class="small">${act === "dismissed" ? C.reasonNeeded : C.reason}<input type="text" data-f="reason" maxlength="300" value="${esc(act === c.state ? c.reason : "")}"></label>
        <label class="small">${C.date}<input type="date" data-f="recheck" min="${esc(d.today)}" value="${esc(act === c.state ? c.recheck : "")}"></label>
      </div><p class="actions"><button type="button" class="small-button primary" data-f="ok">${C.ok}</button>
        <button type="button" class="small-button" data-f="cancel">${C.cancel}</button> <span class="error-text small" data-f="error"></span></p>`;
    const f = k => /** @type {HTMLInputElement} */ (form.querySelector(`[data-f=${k}]`));
    f("reason").focus();
    f("cancel").onclick = () => { form.hidden = true; form.innerHTML = ""; };
    f("ok").onclick = () => {
      if (act === "dismissed" && !f("reason").value.trim()) { f("error").textContent = C.reasonMissing; f("reason").focus(); return; }
      move(id, { state: act, reason: f("reason").value, recheck: f("recheck").value }, f("error"));
    };
  }));
  $("#c-add").onclick = async () => {
    // The fields as they are now: the page may be drawn again while the server answers
    const [nameF, urlF, kindF, noteF, errorF] = ["#c-name", "#c-url", "#c-kind", "#c-note", "#add-error"].map(s => /** @type {HTMLInputElement} */ ($(s)));
    const name = nameF.value.trim();
    if (!name) return;
    try {
      const r = await api("/api/candidates", { name, url: urlF.value.trim(), kind: kindF.value, note: noteF.value.trim() });
      const known = esc(r.candidates.find(c => c.id === r.id)?.name || name);
      const said = r.new ? C.addedNew : r.source_added ? C.known(known) : C.knownSame(known);
      FLASH = { id: r.id, text: `${said}${r.errors?.length ? ` ${C.readFailed(esc(r.errors.join(" ; ")))}` : ""}`, error: false };
      FILTER = "";  // the card shown, whatever its state
      [nameF, urlF, noteF].forEach(f => { f.value = ""; });
      viewCandidates();
    } catch (e) { errorF.textContent = e.message; }
  };
  const publish = $("#publish");
  if (publish) publish.onclick = async () => {
    publish.disabled = true;
    try {
      const r = await api("/api/candidates-draft/publish", { path: $("#reg-path")?.value.trim() || "" });
      SAID = C.published(r.branch, r.pr_url);
      viewCandidates();
    } catch (e) { $("#publish-error").textContent = e.message; publish.disabled = false; }
  };
  const discard = $("#discard");
  if (discard) discard.onclick = async () => {
    if (!confirm(C.confirmDiscard)) return;
    await api("/api/candidates-draft/discard", {});
    viewCandidates();
  };
}
