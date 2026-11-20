/* vault-watch: one screen per pause of the graph. Routes: #/ (watches), #/run/<thread>, #/check, #/check/<id>, #/report, #/costs,
   #/settings (settings.js). The buttons of the header: themes.js (size of the text, light or dark, palettes) and
   notify.js (notifications of the browser); the three are loaded before this file.
   The server holds every state (checkpoints); this page only shows it and sends the human's answers.
   Interface in French or English (toggle in the header, remembered); the guide's own text stays in French. */

const $ = s => document.querySelector(s);
const page = $("#page");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const dollars = n => `${(n ?? 0).toFixed(2)} $`;
// A size in KB (« Ko » in French), one decimal under 10
const kb = n => `${(n / 1024).toLocaleString(lang, { maximumFractionDigits: Math.abs(n) < 10240 ? 1 : 0 })} ${lang === "fr" ? "Ko" : "KB"}`;
const signedKb = n => `${n > 0 ? "+" : ""}${kb(n)}`;
const extLink = (url, text) => `<a href="${esc(url)}" target="_blank" rel="noopener">${text}</a>`;
let source = null;  // EventSource of the run being followed

// --- Languages ---------------------------------------------------------------------------------------
const TEXTS = {
  fr: {
    nav: { watches: "Veilles", sources: "Sources", check: "Vérifier le guide", report: "Signaler une erreur", costs: "Coûts" },
    sources: {
      title: "Sources de la veille",
      intro: (p, runs, file) => `Ce que chaque source a apporté sur ${p.watches} veille(s), du ${p.since || "…"} au ${p.until}, et ce qu'il en est sorti dans ${runs} passage(s). Calculé sans modèle, à partir des veilles et des passages gardés sur cette machine. La liste est dans <code>${file}</code>.`,
      none: "Ce guide ne déclare pas de liste de sources (<code>[watch] feeds</code> dans son manifeste).",
      noHistory: "Aucune veille n'a encore été lue sur cette machine : le tableau se remplira avec les premières.",
      columns: ["Source", "Type", "Dernier élément", "À la source", "Collectés", "Gardés au tri", "Jugés par le modèle", "Retenus", "Corrections proposées", "Acceptées", "État"],
      help: ["Collectés : éléments distincts vus dans les veilles.", "Gardés au tri : après les règles du collecteur (pré-versions, correctifs de routine écartés), sans modèle.",
        "Jugés par le modèle : ceux qu'un passage a triés.", "Retenus : jugés utiles pour une correction ou un ajout."],
      verdicts: { error: "en erreur", noise: "bruit", silent: "muette", quiet: "peu d'éléments", leads: "pistes sans suite", useful: "utile" },
      rules: (n, share) => ({
        error: "le collecteur n'a pas pu la lire à la dernière veille",
        noise: `au moins ${n} éléments jugés par le modèle, ${Math.round(share * 100)} % au plus retenus, aucune correction proposée`,
        silent: "aucun élément sur toute la période : source morte, ou sujet qui ne publie rien (seule la source peut le dire)",
        leads: "des éléments retenus par le modèle, aucune correction n'en est sortie",
        quiet: "quelques éléments, rien de retenu : trop peu pour juger",
        useful: "au moins une correction proposée ou un candidat à l'ajout",
      }),
      insurance: "faille de sécurité : se juge sur sa santé, jamais sur son rendement",
      removed: n => `${n} source(s) présentes dans les veilles ne sont plus dans la liste :`,
      check: "Vérifier les sources", checkHelp: "Interroge chaque source et relit le guide : sans modèle, rien de facturé, moins d'une minute.",
      checking: (n, total) => `Vérification en cours… ${n} / ${total}`,
      checked: d => `Dernière vérification : ${d}.`, neverChecked: "Jamais vérifiées : la colonne « À la source » et les propositions viennent avec la première vérification.",
      probe: { unreachable: "ne répond pas", archived: "dépôt archivé", moved: r => `déplacé vers ${r}`, empty: "ne liste rien",
        stale: d => `rien depuis le ${d}` },
      staleNote: days => `Une source qui n'a rien publié depuis ${days} jours n'est pas proposée au retrait : un outil qui ne bouge plus est une information sur le sujet du guide, c'est la page qui le recommande qu'il faut regarder.`,
      proposals: (n, open) => `Propositions : ${n} à décider${open ? `, ${open} dans une pull request ouverte` : ""}`, noProposals: "Aucun changement à proposer.",
      groups: { remove: "Retirer", change: "Modifier", add: "Ajouter : cités dans le guide, suivis par aucune source", advisories: "Ajouter : failles de sécurité d'outils déjà suivis pour leurs versions" },
      why: {
        unreachable: p => `la source ne répond pas (${p.error})`, archived: () => "le dépôt est archivé",
        moved: p => `le dépôt a été déplacé vers ${p.new.repo}`, empty: () => "la source répond et ne liste rien",
        noise: p => `${p.judged} éléments jugés par le modèle sur la période, ${p.kept} retenu(s), aucune correction proposée`,
        "not-named": () => "aucune page du guide ne la nomme plus",
        cited: p => `cité dans ${p.pages} pages (${p.examples.join(", ")})`,
        "no-advisories": p => `suivi pour ses versions (${p.of}), pas pour ses failles`,
      },
      recommended: "un fait tranche", applied: "dans la PR",
      apply: (n, repo) => repo ? `Ouvrir une pull request avec ${n} changement(s)` : `Créer une branche avec ${n} changement(s)`,
      appliedTo: (branch, pr) => pr ? `Pull request ouverte : ${pr}` : `Changements sur la branche ${branch} (guide sans dépôt : à fusionner à la main).`,
      all: n => `Toutes (${n})`, filterHelp: "Clique un état pour ne voir que lui (plusieurs possibles), un titre de colonne pour trier.",
      shown: (n, total) => n === total ? `${total} sources` : `${n} source(s) affichée(s) sur ${total}`,
      sortBy: c => `Trier par « ${c} » (un second clic inverse)`, defaultSort: "Tri par défaut",
      count: (n, label) => `${n} ${label}`,
    },
    links: ["Guide", "Dépôt du guide", "Code de l'agent", "Claude API"],
    verif: {
      title: "Vérifier le guide",
      intro: "Un bilan de santé du guide entier, à la demande. Les contrôles gratuits utilisent les scripts du guide ; les autres font lire le guide par Claude. Les résultats sont des pistes : celles que tu gardes partent dans une passe fix, qui les vérifie sur les sources et passe par ta relecture.",
      free: "gratuit", tokens: n => `≈ ${n.toLocaleString("fr")} tokens`, unknown: "selon le résultat",
      needs: ids => `lance aussi : ${ids}`,
      start: c => `Lancer la vérification · ${c}`, history: "Vérifications précédentes",
      none: "Aucune vérification pour l'instant.", running: "En cours…", leads: n => `${n} piste(s)`,
      waiting: "en attente", checking: "en cours…", ok: "RAS", problems: "à regarder", failed: "n'a pas pu tourner",
      notFixable: "Pas encore corrigeable par une passe fix (les traductions se corrigent depuis le français) : à reprendre à la main ou par une prochaine fonction.",
      seeDetails: "Détails", dead: "Sources qui ne répondent pas", blocked: "Bloquées par une protection anti-robots (souvent normales dans un navigateur)",
      claims: "Affirmations à revérifier", pagesDue: "Pages à revoir", log: "Journal",
      // by: the ticked leads per kind of run (fix, translation, compact); one run per kind
      createFix: (by, c, runs = {}) => {
        const kinds = [["fix", "fix", "≈ 6-8 $"], ["translation", "traduction", "< 1 $"], ["compact", "compactage", runs.compact || "≈ 5-6 $"]].filter(k => by[k[0]]);
        return kinds.length > 1 ? `Créer ${kinds.length} passes : ${kinds.map(k => `${by[k[0]]} piste(s) en ${k[1]} (${c(k[2])})`).join(", ")}`
          : `Créer une passe ${(kinds[0] || [0, "fix"])[1]} avec ${kinds[0] ? by[kinds[0][0]] : 0} piste(s) · ${c((kinds[0] || [0, 0, "≈ 6-8 $"])[2])}`;
      },
      heaviest: "Pages les plus lourdes", perChapter: "Par chapitre", over: "au-dessus du budget", newPage: "nouvelle page",
      readonly: "lecture seule", notes: (n, w) => `${n} notes de bas de page (${w})`, pagesWord: "page(s)",
      growth: g => `Le guide pesait ${kb(g.bytes)} le ${g.date} : ${signedKb(g.added)} en ${g.days} jours${g.new_pages ? `, dont ${g.new_pages} nouvelle(s) page(s)` : ""}.`,
      tickAll: "Tout cocher", untickAll: "Tout décocher",
      cost: c => `Coût : ${c}`,
      counts: c => c.open + c.fix + c.dismissed === 0 ? "aucune piste"
        : `${c.open} à traiter · ${c.fix} envoyée(s) en passe fix · ${c.dismissed} écartée(s)`,
      toHandle: n => `${n} piste(s) à traiter`, handled: "Traitée", handle: "Traiter",
      tickCard: n => `Cocher / décocher les ${n}`,
      toHandleTitle: "À traiter", newCheck: "Nouvelle vérification", fixRuns: "Passes fix lancées depuis cette vérification",
      warning: n => `Il reste ${n} piste(s) à traiter ci-dessus. Une nouvelle vérification les retrouverait, en double : traite-les ou écarte-les d'abord.`,
      sent: "→ passe fix", dismissed: "écartée", reopen: "Rétablir", dismiss: n => `Écarter ${n} piste(s)`,
      interrupted: "interrompue",
      interruptedText: names => `Cette vérification s'est arrêtée avant la fin (serveur fermé pendant qu'elle tournait). Contrôles non faits : ${names}. Ce qu'elle a trouvé reste utilisable ; pour le reste, lance une nouvelle vérification.`,
      remove: "Supprimer cette vérification",
      confirmRemove: "Supprimer cette vérification et ses pistes ? Les passes fix déjà lancées restent.",
    },
    loading: "Chargement…",
    serverDown: "Le serveur ne répond pas : il s'arrête après 1 h d'inactivité. Relance-le (Nouvel onglet, module « Veille du guide IA »), puis recharge la page. Les passages en pause n'ont rien perdu.",
    statuses: {
      new: "À analyser", running: "En cours", review: "Relecture à faire", publish: "Publication à valider",
      published: "PR créée", "nothing-applied": "Rien appliqué", "not-published": "Non publié", stopped: "Interrompu",
      closed: "Traitée hors agent", merged: "✓ Terminée · PR fusionnée", "pr-open": "PR à fusionner",
      "pr-closed": "PR fermée sans fusion",
    },
    steps: {
      collect: "Récupération de la veille", triage: "Tri des éléments", locate: "Recherche des pages concernées",
      propose: "Propositions de corrections", number: "Numérotation et contrôle des citations",
      crosscheck: "Relecture avec tout le guide et le web", report: "Rapport", review: "Ta relecture",
      apply: "Application sur une branche", mirror: "Traduction anglaise", audits: "Contrôles du guide (npm test)",
      links: "Vérification des liens", publish: "Push et pull request",
    },
    watches: "Veilles",
    watchesIntro: () => `Une veille est publiée par ${forgeName()} tous les 15 jours. L'agent l'analyse, tu relis ses propositions, puis il ouvre la pull request.`,
    analyse: c => `Analyser · ${c}`, merge: () => `Fusionner sur ${forgeName()}`,
    buttons: { review: "Relire", publish: "Valider la publication", running: "Suivre", stopped: "Reprendre" },
    details: "Détails",
    issue: open => `issue ${open ? "ouverte" : "fermée"}`, watchFile: n => n == null ? "fichier de veille" : `fichier de veille, ${n} élément(s) retenu(s)`,
    count: (n, a) => `${n} correction(s), ${a} appliquée(s)`,
    noWatch: "Aucune veille.", others: "Autres passages",
    collectIntro: "L'agent lit les flux du guide (versions, avis de sécurité, annonces) sur les derniers jours et écarte la routine par règles, sans modèle : c'est gratuit. Tu analyses ensuite la veille obtenue.",
    collectNow: "Collecter une veille", collecting: "Lecture des flux…",
    watchUpTo: d => `Veille jusqu'au ${d}`,
    canClose: "Tu peux fermer la page : l'analyse continue sur le serveur, et l'état est enregistré à chaque étape.",
    progress: (min, cost) => `Démarré il y a ${min} min · coût de ce passage ≈ ${cost}`,
    applyId: id => `Appliquer ${id}`,
    crossCheck: "Relecture globale", from: "D'après", colon: " : ",
    byChapter: (t, b) => `Relecture globale chapitre par chapitre : le guide (≈ ${t.toLocaleString("fr")} tokens) dépasse ce qu'un appel du modèle peut lire (${b.toLocaleString("fr")}). Une contradiction entre deux chapitres peut échapper.`,
    lostValues: "Plus aucune page ne le dit ensuite", removedWhole: "(passage supprimé)",
    weight: w => `Les pages modifiées pèsent ${kb(w.before)} avant et ${kb(w.after)} après (${signedKb(w.after - w.before)}), miroirs non comptés.`,
    weightMost: "Le plus :",
    sourceMissing: "Source à vérifier", leftovers: n => `Valeurs retirées encore présentes, laissées telles quelles (${n})`,
    reviewFigures: ["éléments de veille", "touchent une page", "corrections proposées", "pistes d'ajout"],
    corrections: "Corrections",
    reviewHelp: "Coche ce qui doit être appliqué. Les corrections liées (une phrase et sa note, par exemple) forment un groupe : elles se cochent ensemble. Un groupe dont un membre ne peut pas s'appliquer est écarté en entier.",
    group: g => `Groupe ${g}`, groupLeftOut: " · écarté : un membre ne s'applique pas",
    noCorrection: "Aucune correction proposée.",
    leads: n => `Pistes d'ajout (${n}, non rédigées)`, none: "Aucune.", nothing: "Rien.",
    noticed: n => `Remarqué ailleurs dans le guide (${n})`,
    noticedHelp: "Pour les corriger : « Signaler une erreur », en copiant les lignes utiles.",
    excerptMissing: "extrait introuvable dans la page", excerptApprox: "passage le plus proche, pas une citation exacte",
    claims: n => `Affirmations à revérifier (${n})`,
    report: "Rapport complet (Markdown)",
    applyNothing: "Ne rien appliquer", applyN: n => `Appliquer ${n} correction${n > 1 ? "s" : ""}`,
    confirmNothing: "Ne rien appliquer et clore ce passage ?",
    publishFigures: ["corrections appliquées", "pages anglaises mises à jour", "contrôles du guide", "lien(s) à vérifier"],
    failed: "Échec", notChecked: "non vérifié",
    branchReady: b => `Branche <code>${b}</code>, prête localement. Rien n'a encore quitté la machine.`,
    auditsRed: "Les contrôles du guide échouent : la PR serait rouge.",
    translation: "Traduction", linksTitle: "Liens", linksNew: "(« NEW » : ajouté par ce passage)",
    linksOk: "Toutes les sources des pages modifiées répondent.",
    linksNotChecked: "Sources non vérifiées : le guide ne déclare pas d'audit des sources.",
    changes: "Modifications", doNotPublish: "Ne pas publier", publish: "Pousser et ouvrir la pull request",
    billedNext: "Ce passage a tourné jusqu'ici sans facturation (abonnement ou modèle local), mais les Réglages désignent maintenant un moteur facturé : la suite (la traduction) serait facturée à l'API. Change le moteur dans les Réglages avant d'appliquer si ce n'est pas voulu.",
    keepLocal: "Terminer (branche gardée en local)",
    confirmNo: "Garder la branche en local sans pull request ?",
    end: {
      published: pr => `Pull request : ${pr}. Une fois relue et fusionnée sur ${forgeName()}, le site se redéploie tout seul.`,
      "pr-open": pr => `Pull request à relire et fusionner sur ${forgeName()} : ${pr}. Le site se redéploie tout seul après la fusion.`,
      merged: pr => `Terminé : la ${pr} est fusionnée et le site redéployé.`,
      "pr-closed": pr => `La ${pr} a été fermée sans fusion.`,
      "nothing-applied": () => "Aucune correction appliquée : le passage est clos.",
      "not-published": (pr, b) => `Branche <code>${b}</code> gardée en local, sans pull request.`,
      stopped: () => "Le passage s'est arrêté sur une erreur. Il peut reprendre à la dernière étape terminée.",
      new: () => "Ce passage n'a pas commencé.",
    },
    resume: "Reprendre", applied: "Appliquées",
    reportTitle: "Signaler une erreur",
    reportIntro: "Une erreur par ligne : la page, ce qui est faux, et si possible la bonne information. L'agent vérifie chaque point sur des sources primaires, avec tout le guide en contexte, puis propose des corrections que tu relis comme pour une veille.",
    reportCost: "Compte 5 à 7 $.", reportSubscription: "Les appels passent par Claude Code sur ton abonnement : rien n'est facturé.",
    reportExample: "03-stack/engines.md : vLLM 0.31 n'est plus la version minimale, la 0.33 corrige un avis de sécurité.",
    reportButton: "Vérifier et proposer des corrections",
    costsTitle: "Coûts",
    costsIntro: total => `Calculés à partir de l'usage que renvoie l'API, au prix catalogue (journal <code>metrics/usage.jsonl</code>). La page de facturation de la Console reste la référence. Total : ${total}.`,
    costsSubscription: (calls, spared) => `${calls} appel(s) sont passés par Claude Code sur l'abonnement : non facturés, ils auraient coûté environ ${spared} sur l'API.`,
    costsOrigins: "Prix utilisés pour les appels à l'API :",
    priceOrigin: o => o === "no price" ? "aucun prix connu : compté 0 $" : o === "list prices of the time" ? "prix catalogue de l'époque (avant la 0.4.0)"
      : o === "set in the Settings" ? "prix fixé dans les réglages" : o.replace(/^default of /, "prix par défaut de ").replace(/^fetched of /, "liste du "),
    columns: ["Appels", "Tokens lus", "Écrits", "Coût"], subscriptionColumns: ["Sur l'abonnement", "Non facturé"],
    byMonth: "Par mois", month: "Mois", byRun: "Par passage", run: "Passage",
    subscription: "abonnement, non facturé", local: "modèle local, non facturé", provider: "facturé par ton fournisseur",
  },
  en: {
    nav: { watches: "Watches", sources: "Sources", check: "Check the guide", report: "Report an error", costs: "Costs" },
    sources: {
      title: "Sources of the watch",
      intro: (p, runs, file) => `What each source brought over ${p.watches} watch(es), from ${p.since || "…"} to ${p.until}, and what came out of it in ${runs} run(s). Computed without a model, from the watches and the runs kept on this machine. The list is in <code>${file}</code>.`,
      none: "This guide declares no list of sources (<code>[watch] feeds</code> in its manifest).",
      noHistory: "No watch has been read on this machine yet: the table fills with the first ones.",
      columns: ["Source", "Type", "Last item", "At the source", "Collected", "Kept by the rules", "Judged by the model", "Kept", "Corrections proposed", "Accepted", "State"],
      help: ["Collected: distinct items seen in the watches.", "Kept by the rules: after the collector's rules (pre-releases, routine patches dropped), no model.",
        "Judged by the model: those a run has triaged.", "Kept: judged useful for a correction or an addition."],
      verdicts: { error: "in error", noise: "noise", silent: "silent", quiet: "few items", leads: "leads without follow-up", useful: "useful" },
      rules: (n, share) => ({
        error: "the collector could not read it in the latest watch",
        noise: `at least ${n} items judged by the model, ${Math.round(share * 100)} % at most kept, no correction proposed`,
        silent: "no item over the whole period: a dead source, or a subject that publishes nothing (only the source can tell)",
        leads: "items kept by the model, no correction came out of them",
        quiet: "a few items, none kept: too few to judge",
        useful: "at least one correction proposed or one addition candidate",
      }),
      insurance: "security advisories: judged on its health, never on its yield",
      removed: n => `${n} source(s) found in the watches are no longer in the list:`,
      check: "Check the sources", checkHelp: "Asks each source and reads the guide again: no model, nothing billed, under a minute.",
      checking: (n, total) => `Checking… ${n} / ${total}`,
      checked: d => `Last check: ${d}.`, neverChecked: "Never checked: the « At the source » column and the proposals come with the first check.",
      probe: { unreachable: "does not answer", archived: "repository archived", moved: r => `moved to ${r}`, empty: "lists nothing",
        stale: d => `nothing since ${d}` },
      staleNote: days => `A source that has published nothing for ${days} days is not proposed for removal: a tool that stopped moving is a fact about the guide's subject, the page that recommends it is what to look at.`,
      proposals: (n, open) => `Proposals: ${n} to decide${open ? `, ${open} in an open pull request` : ""}`, noProposals: "No change to propose.",
      groups: { remove: "Remove", change: "Change", add: "Add: cited in the guide, followed by no source", advisories: "Add: security advisories of tools already followed for their releases" },
      why: {
        unreachable: p => `the source does not answer (${p.error})`, archived: () => "the repository is archived",
        moved: p => `the repository moved to ${p.new.repo}`, empty: () => "the source answers and lists nothing",
        noise: p => `${p.judged} items judged by the model over the period, ${p.kept} kept, no correction proposed`,
        "not-named": () => "no page of the guide names it any more",
        cited: p => `cited in ${p.pages} pages (${p.examples.join(", ")})`,
        "no-advisories": p => `followed for its releases (${p.of}), not for its advisories`,
      },
      recommended: "settled by a fact", applied: "in the PR",
      apply: (n, repo) => repo ? `Open a pull request with ${n} change(s)` : `Create a branch with ${n} change(s)`,
      appliedTo: (branch, pr) => pr ? `Pull request opened: ${pr}` : `Changes on the branch ${branch} (a guide without a repository: merge it by hand).`,
      all: n => `All (${n})`, filterHelp: "Click a state to see it alone (several can be chosen), a column title to sort.",
      shown: (n, total) => n === total ? `${total} sources` : `${n} source(s) shown out of ${total}`,
      sortBy: c => `Sort by « ${c} » (a second click reverses)`, defaultSort: "Default order",
      count: (n, label) => `${n} ${label}`,
    },
    links: ["Guide", "Guide repository", "Agent code", "Claude API"],
    verif: {
      title: "Check the guide",
      intro: "A health check of the whole guide, on demand. The free checks run the guide's own scripts; the others have Claude read the guide. Results are leads: the ones you keep go to a fix run, which checks them on sources and goes through your review.",
      free: "free", tokens: n => `≈ ${n.toLocaleString("en")} tokens`, unknown: "depends on the result",
      needs: ids => `also runs: ${ids}`,
      start: c => `Run the check · ${c}`, history: "Previous checks",
      none: "No check yet.", running: "Running…", leads: n => `${n} lead(s)`,
      waiting: "waiting", checking: "running…", ok: "all clear", problems: "to look at", failed: "could not run",
      notFixable: "Not fixable by a fix run yet (translations are fixed from the French side): to handle by hand or by a later feature.",
      seeDetails: "Details", dead: "Sources not answering", blocked: "Blocked by anti-bot protections (often fine in a browser)",
      claims: "Claims to re-check", pagesDue: "Pages due for review", log: "Log",
      createFix: (by, c, runs = {}) => {
        const kinds = [["fix", "fix", "≈ 6-8 $"], ["translation", "translation", "< 1 $"], ["compact", "compaction", runs.compact || "≈ 5-6 $"]].filter(k => by[k[0]]);
        return kinds.length > 1 ? `Create ${kinds.length} runs: ${kinds.map(k => `${by[k[0]]} point(s) as a ${k[1]} run (${c(k[2])})`).join(", ")}`
          : `Create a ${(kinds[0] || [0, "fix"])[1]} run with ${kinds[0] ? by[kinds[0][0]] : 0} point(s) · ${c((kinds[0] || [0, 0, "≈ 6-8 $"])[2])}`;
      },
      heaviest: "Heaviest pages", perChapter: "Per chapter", over: "over its budget", newPage: "new page",
      readonly: "read-only", notes: (n, w) => `${n} footnotes (${w})`, pagesWord: "page(s)",
      growth: g => `The guide weighed ${kb(g.bytes)} on ${g.date}: ${signedKb(g.added)} in ${g.days} days${g.new_pages ? `, ${g.new_pages} new page(s) among it` : ""}.`,
      tickAll: "Tick all", untickAll: "Untick all",
      cost: c => `Cost: ${c}`,
      counts: c => c.open + c.fix + c.dismissed === 0 ? "no lead"
        : `${c.open} to handle · ${c.fix} sent to a fix run · ${c.dismissed} dismissed`,
      toHandle: n => `${n} lead(s) to handle`, handled: "Handled", handle: "Handle",
      tickCard: n => `Tick / untick the ${n}`,
      toHandleTitle: "To handle", newCheck: "New check", fixRuns: "Fix runs started from this check",
      warning: n => `${n} lead(s) above are still to handle. A new check would find them again, twice: handle or dismiss them first.`,
      sent: "→ fix run", dismissed: "dismissed", reopen: "Reopen", dismiss: n => `Dismiss ${n} lead(s)`,
      interrupted: "interrupted",
      interruptedText: names => `This check stopped before its end (the server was closed while it ran). Checks not done: ${names}. What it found stays usable; for the rest, start a new check.`,
      remove: "Delete this check",
      confirmRemove: "Delete this check and its leads? The fix runs already started stay.",
    },
    loading: "Loading…",
    serverDown: "The server does not answer: it may have stopped after being idle (`serve --idle-exit`). Start it again, then reload the page. Paused runs lost nothing.",
    statuses: {
      new: "To analyse", running: "Running", review: "Review pending", publish: "Publish pending",
      published: "PR opened", "nothing-applied": "Nothing applied", "not-published": "Not published", stopped: "Stopped",
      closed: "Handled without the agent", merged: "✓ Done · PR merged", "pr-open": "PR to merge",
      "pr-closed": "PR closed unmerged",
    },
    steps: {
      collect: "Download the watch", triage: "Triage the items", locate: "Find the pages concerned",
      propose: "Propose corrections", number: "Number them, check the quotes",
      crosscheck: "Cross-check with the whole guide and the web", report: "Report", review: "Your review",
      apply: "Apply on a branch", mirror: "English translation", audits: "Guide audits (npm test)",
      links: "Link checks", publish: "Push and pull request",
    },
    watches: "Watches",
    watchesIntro: () => `${forgeName()} publishes a watch every two weeks. The agent analyses it, you review its proposals, then it opens the pull request.`,
    analyse: c => `Analyse · ${c}`, merge: () => `Merge on ${forgeName()}`,
    buttons: { review: "Review", publish: "Approve publishing", running: "Follow", stopped: "Resume" },
    details: "Details",
    issue: open => `issue ${open ? "open" : "closed"}`, watchFile: n => n == null ? "watch file" : `watch file, ${n} item(s) kept`,
    count: (n, a) => `${n} correction(s), ${a} applied`,
    noWatch: "No watch.", others: "Other runs",
    collectIntro: "The agent reads the guide's feeds (releases, security advisories, announcements) over the last days and drops the routine by rules, without a model: it is free. You then analyse the watch it gives.",
    collectNow: "Collect a watch", collecting: "Reading the feeds…",
    watchUpTo: d => `Watch up to ${d}`,
    canClose: "You can close the page: the analysis goes on in the server, and the state is saved after each step.",
    progress: (min, cost) => `Started ${min} min ago · cost of this run ≈ ${cost}`,
    applyId: id => `Apply ${id}`,
    crossCheck: "Cross-check", from: "From", colon: ": ",
    byChapter: (t, b) => `Cross-check chapter by chapter: the guide (≈ ${t.toLocaleString("en")} tokens) exceeds what one call of the model can read (${b.toLocaleString("en")}). A contradiction between two chapters can be missed.`,
    lostValues: "No page states it any more", removedWhole: "(passage removed)",
    weight: w => `The pages changed weigh ${kb(w.before)} before and ${kb(w.after)} after (${signedKb(w.after - w.before)}), mirrors not counted.`,
    weightMost: "Most:",
    sourceMissing: "Source to check", leftovers: n => `Removed values still present, left as they are (${n})`,
    reviewFigures: ["watch items", "touch a page", "corrections proposed", "addition leads"],
    corrections: "Corrections",
    reviewHelp: "Tick what should be applied. Related corrections (a sentence and its footnote, for instance) form a group and are ticked together. A group with a member that cannot apply is left out whole.",
    group: g => `Group ${g}`, groupLeftOut: " · left out: a member does not apply",
    noCorrection: "No correction proposed.",
    leads: n => `Addition leads (${n}, not drafted)`, none: "None.", nothing: "Nothing.",
    noticed: n => `Noticed elsewhere in the guide (${n})`,
    noticedHelp: "To fix them: « Report an error », with the relevant lines.",
    excerptMissing: "excerpt not found in the page", excerptApprox: "closest passage, not an exact quote",
    claims: n => `Claims due for re-check (${n})`,
    report: "Full report (Markdown)",
    applyNothing: "Apply nothing", applyN: n => `Apply ${n} correction${n > 1 ? "s" : ""}`,
    confirmNothing: "Apply nothing and close this run?",
    publishFigures: ["corrections applied", "English pages updated", "guide audits", "link(s) to check"],
    failed: "Failed", notChecked: "not checked",
    branchReady: b => `Branch <code>${b}</code>, ready locally. Nothing has left the machine yet.`,
    auditsRed: "The guide audits fail: the PR would be red.",
    translation: "Translation", linksTitle: "Links", linksNew: "(« NEW »: added by this run)",
    linksOk: "Every source of the changed pages answers.",
    linksNotChecked: "Sources not checked: the guide declares no source audit.",
    changes: "Changes", doNotPublish: "Do not publish", publish: "Push and open the pull request",
    billedNext: "This run has cost nothing so far (a subscription or a local model), but the Settings now name a billed engine: what is left (the translation) would be billed to the API. Change the engine in the Settings before applying if that is not what you want.",
    keepLocal: "Finish (branch kept locally)",
    confirmNo: "Keep the branch locally, without a pull request?",
    end: {
      published: pr => `Pull request: ${pr}. Once reviewed and merged on ${forgeName()}, the site redeploys by itself.`,
      "pr-open": pr => `Pull request to review and merge on ${forgeName()}: ${pr}. The site redeploys by itself after the merge.`,
      merged: pr => `Done: the ${pr} is merged and the site redeployed.`,
      "pr-closed": pr => `The ${pr} was closed without merging.`,
      "nothing-applied": () => "No correction applied: the run is closed.",
      "not-published": (pr, b) => `Branch <code>${b}</code> kept locally, without a pull request.`,
      stopped: () => "The run stopped on an error. It can resume from the last finished step.",
      new: () => "This run has not started.",
    },
    resume: "Resume", applied: "Applied",
    reportTitle: "Report an error",
    reportIntro: "One error per line: the page, what is wrong, and the right information if you have it. The agent checks each point on primary sources, with the whole guide in context, then proposes corrections you review as for a watch.",
    reportCost: "About 5 to 7 $.", reportSubscription: "The calls go through Claude Code on your subscription: nothing is billed.",
    reportExample: "03-stack/engines.md: vLLM 0.31 is no longer the minimum version, 0.33 fixes a security advisory.",
    reportButton: "Check and propose corrections",
    costsTitle: "Costs",
    costsIntro: total => `Computed from the usage the API returns, at list price (journal <code>metrics/usage.jsonl</code>). The Console's billing page stays the reference. Total: ${total}.`,
    costsSubscription: (calls, spared) => `${calls} call(s) went through Claude Code on the subscription: not billed, they would have cost about ${spared} on the API.`,
    costsOrigins: "Prices used for the API calls:",
    priceOrigin: o => o === "no price" ? "no known price: counted 0 $" : o === "list prices of the time" ? "list prices of the time (before 0.4.0)"
      : o === "set in the Settings" ? "price set in the Settings" : o.replace(/^default of /, "default price of ").replace(/^fetched of /, "list of "),
    columns: ["Calls", "Tokens in", "Out", "Cost"], subscriptionColumns: ["On the subscription", "Not billed"],
    byMonth: "By month", month: "Month", byRun: "By run", run: "Run",
    subscription: "subscription, not billed", local: "local model, not billed", provider: "billed by your provider",
  },
};
for (const l of ["fr", "en"]) Object.assign(TEXTS[l], { settings: SETTINGS_TEXTS[l], theme: THEME_TEXTS[l], notify: NOTIFY_TEXTS[l] });
const savedLang = () => { try { return localStorage.getItem("vault-watch-lang"); } catch { return null; } };
let lang = TEXTS[savedLang()] ? savedLang() : (navigator.language || "en").startsWith("fr") ? "fr" : "en";
let T = TEXTS[lang];

const CLASSES = {
  running: "attention", review: "attention", publish: "attention", "pr-open": "attention",
  published: "ok", merged: "ok", stopped: "error",
};
// Nothing left to do: the card is dimmed
const FINISHED = ["closed", "merged", "pr-closed", "nothing-applied", "not-published"];
const badge = st => `<span class="badge ${CLASSES[st] || "neutral"}">${T.statuses[st] || st}</span>`;

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-Vault-Watch": "1" },
  };
  const r = await fetch(path, opts).catch(() => { throw new Error(T.serverDown); });  // stopped (idle, closed)
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r.text();
}

// --- Header -------------------------------------------------------------------------------------------
let info = null;
const forgeName = () => info?.forge || "GitHub";  // where the pull requests are merged
const CLAUDE_BILLING = "https://platform.claude.com/settings/billing";  // API credits left (the API engine spends them)
// What a paid action costs: its estimate on the API, nothing on Claude Code with a subscription (info.engine)
const onSubscription = () => info?.engine === "claude-code";
// What an action costs: the estimate (Claude API prices) on the API only; nothing on a subscription or a local model;
// another provider's prices are its own.
const cost = usd => onSubscription() ? T.subscription : info?.billing === "none" ? T.local
  : info?.engine && info.engine !== "api" ? T.provider : usd;
function header() {
  document.documentElement.lang = lang;
  document.querySelectorAll("nav [data-nav]").forEach(a => a.textContent = T.nav[a.dataset.nav]);
  const links = info ? [info.site, info.repo_url, info.agent, CLAUDE_BILLING]
    .map((url, i) => url && extLink(url, `${T.links[i]} ↗`)).filter(Boolean).join("") : "";
  $("#external").innerHTML = links;
  $("#footer").textContent = info?.version ? `vault-watch ${info.version}` : "";
  $("#guide-name").textContent = info?.guide || "";   // one guide per server
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
    lang = b.dataset.lang;
    T = TEXTS[lang];
    try { localStorage.setItem("vault-watch-lang", lang); } catch { /* private window: per page only */ }
    header();
    route();
  });
}

// --- Router --------------------------------------------------------------------------------------
async function route() {
  if (source) { source.close(); source = null; }
  clearTimeout(followTimer);
  let h = location.hash.slice(1) || "/";
  if (h === "/settings") {   // an address to open the Settings: the window, over the first page
    history.replaceState(null, "", "#/");
    h = "/";
    openSettings();
  }
  document.querySelectorAll("nav [data-nav]").forEach(a =>
    a.classList.toggle("active", h === "/" ? a.dataset.nav === "watches" : h.startsWith(`/${a.dataset.nav}`)));
  page.innerHTML = `<p class="muted">${T.loading}</p>`;
  try {
    if (h.startsWith("/run/")) await viewRun(decodeURIComponent(h.slice(5)));
    else if (h.startsWith("/check/")) await viewCheck(decodeURIComponent(h.slice(7)));
    else if (h === "/check") await viewChecks();
    else if (h === "/sources") await viewSources();
    else if (h === "/report") viewReport();
    else if (h === "/costs") await viewCosts();
    else await viewWatches();
  } catch (e) {
    page.innerHTML = `<p class="error-text">${esc(e.message)}</p>`;
  }
}
addEventListener("hashchange", route);

// --- Watches ---------------------------------------------------------------------------------------
async function viewWatches() {
  const [watches, others] = await Promise.all([api("/api/watches"), api("/api/runs")]);
  page.innerHTML = `
    <h1>${T.watches}</h1>
    <p class="subtitle">${info?.watch_source === "feeds" ? T.collectIntro : T.watchesIntro()}</p>
    ${info?.watch_source === "feeds" ? `<p><button id="collect">${T.collectNow}</button></p>` : ""}
    ${watches.map(v => {
      const r = v.run, link = `#/run/${encodeURIComponent(r.thread)}`;
      const action = r.status === "closed" ? ""
        : v.error ? ""
        : r.status === "new" ? `<button class="primary" data-analyse="${esc(v.id)}" data-kind="${v.kind}">${T.analyse(cost("≈ 4 $"))}</button>`
        : r.status === "pr-open" ? extLink(r.pr_url, `<button class="primary">${T.merge()}</button>`)
        : `<a href="${link}"><button${["review", "publish", "stopped"].includes(r.status) ? ' class="primary"' : ""}>${
            T.buttons[r.status] || T.details}</button></a>`;
      return `<div class="card row${FINISHED.includes(r.status) ? " finished" : ""}">
        <div class="grow">
          ${v.kind === "issue" ? `<b>#${v.number}</b> ` : ""}${esc(v.title)} ${v.urgent ? `<span class="badge ${FINISHED.includes(r.status) ? "neutral" : "error"}">urgent</span>` : ""}
          ${v.error ? `<div class="error-text small">${esc(v.error)}</div>` : ""}
          <div class="muted small">${v.date} · ${v.kind === "issue" ? T.issue(v.state === "open") : T.watchFile(v.items)}${
            !["new", "closed"].includes(r.status) ? ` · ${T.count(r.corrections, r.applied)} · ${dollars(r.cost)}` : ""}${
            r.pr_url ? ` · ${extLink(r.pr_url, "pull request")}` : ""}</div>
        </div>
        ${badge(r.status)} ${action}
      </div>`;
    }).join("") || `<p class="muted">${T.noWatch}</p>`}
    ${others.length ? `<h2>${T.others}</h2>${others.map(r => `
      <div class="card row${FINISHED.includes(r.status) ? " finished" : ""}"><div class="grow"><b>${esc(r.thread)}</b>
        <div class="muted small">${esc(r.source)} · ${r.corrections} correction(s) · ${dollars(r.cost)}${
          r.pr_url ? ` · ${extLink(r.pr_url, "pull request")}` : ""}</div></div>
        ${badge(r.status)} <a href="#/run/${encodeURIComponent(r.thread)}"><button>${T.details}</button></a></div>`).join("")}` : ""}`;
  const collect = $("#collect");
  if (collect) collect.onclick = async () => {
    collect.disabled = true;
    collect.textContent = T.collecting;
    try { await api("/api/collect", {}); await viewWatches(); }
    catch (e) { collect.disabled = false; collect.textContent = T.collectNow; collect.insertAdjacentHTML("afterend", ` <span class="error-text">${esc(e.message)}</span>`); }
  };
  page.querySelectorAll("[data-analyse]").forEach(b => b.onclick = async () => {
    b.disabled = true;
    const { thread } = await api("/api/analyses", b.dataset.kind === "issue" ? { issue: Number(b.dataset.analyse) } : { watch: b.dataset.analyse });
    location.hash = `/run/${encodeURIComponent(thread)}`;
  });
}

// --- One run ---------------------------------------------------------------------------------------
async function viewRun(thread) {
  const r = await api(`/api/runs/${encodeURIComponent(thread)}`);
  const title = `<h1>${esc(r.source || thread)} ${badge(r.status)}</h1>
    <p class="subtitle">${r.as_of ? `${T.watchUpTo(r.as_of)} · ` : ""}${esc(r.usage)}</p>`;
  if (r.status === "running") return viewRunning(r, title);
  if (r.status === "review") return viewReview(r, title);
  if (r.status === "publish") return viewPublish(r, title);
  viewEnd(r, title);
}

function viewRunning(r, title) {
  const doneSteps = new Set(r.job.events.map(e => e.node));
  const first = r.job.action === "fix" ? "propose" : { run: "collect", review: "apply", publish: "publish", resume: null }[r.job.action];
  const steps = r.steps.slice(first ? r.steps.indexOf(first) : 0);
  const cost = r.job.events.reduce((m, e) => e.cost ?? m, 0);
  page.innerHTML = `${title}
    <div class="card">
      <ol class="steps" id="steps">${steps.map(s => `<li data-step="${s}">${T.steps[s]}</li>`).join("")}</ol>
      <p class="muted small" id="progress"></p>
    </div>
    <p class="muted small">${T.canClose}</p>`;
  const update = (cost) => {
    let current = true;
    page.querySelectorAll("#steps li").forEach(li => {
      const done = doneSteps.has(li.dataset.step);
      li.classList.toggle("done", done);
      li.classList.toggle("current", !done && current && (current = false, true));
    });
    const min = Math.round((Date.now() / 1000 - r.job.started) / 60);
    $("#progress").textContent = T.progress(min, dollars(cost));
  };
  update(cost);
  source = new EventSource(`/api/runs/${encodeURIComponent(r.thread)}/events`);
  source.onmessage = ev => { const e = JSON.parse(ev.data); doneSteps.add(e.node); update(e.cost ?? cost); };
  source.addEventListener("end", () => { source.close(); source = null; route(); });
}

// Word-level diff: words removed from `a` wrapped in <del>, words added to `b` in <ins>.
function wordDiff(a, b) {
  const x = a.split(/(\s+)/), y = b.split(/(\s+)/);
  const n = x.length, m = y.length, L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  let i = 0, j = 0, before = "", after = "";
  while (i < n || j < m) {
    if (i < n && j < m && x[i] === y[j]) { before += esc(x[i]); after += esc(y[j]); i++; j++; }
    else if (j < m && (i === n || L[i][j + 1] >= L[i + 1][j])) { after += `<ins>${esc(y[j])}</ins>`; j++; }
    else { before += `<del>${esc(x[i])}</del>`; i++; }
  }
  return [before, after];
}

// The passages a finding is about, as the server found them in the page: never the model's own words
function excerpts(list) {
  if (!list?.length) return "";
  const row = l => `<div${l.hit ? ' class="target"' : ""}><span class="n">${l.n}</span><span>${
    l.parts ? `${esc(l.parts[0])}<mark>${esc(l.parts[1])}</mark>${esc(l.parts[2])}` : esc(l.text)}</span></div>`;
  return `<div class="excerpts">${list.map(e => e.match === "missing"
    ? `<div class="excerpt muted small"><code>${esc(e.page)}</code> · ${T.excerptMissing}</div>`
    : `<div class="excerpt"><div class="muted small"><code>${esc(e.page)}:${e.line}</code>${e.match === "approx" ? ` · ${T.excerptApprox}` : ""}</div>
        <div class="lines" lang="${e.page.startsWith("en/") ? "en" : "fr"}">${e.lines.map(row).join("")}</div></div>`).join("")}</div>`;
}

function correctionCard(c, r) {
  const valid = c.check === "ok";
  const [before, after] = wordDiff(c.current, c.proposed);
  const sources = (c.item_ids || [c.item_id]).map(id => r.items[id]).filter(Boolean)
    .map(i => i.url ? extLink(i.url, esc(i.title)) : esc(i.title)).join(" · ");
  return `<div class="card correction${valid ? "" : " rejected"}">
    <input type="checkbox" data-id="${c.id}" data-group="${c.group}" ${valid ? "checked" : "disabled"} aria-label="${T.applyId(c.id)}">
    <div>
      <div class="header"><b>${c.id}</b><span class="badge ${c.severity}">${c.severity}</span><code>${esc(c.page)}</code>
        ${valid ? "" : `<span class="badge error">${esc(c.check)}</span>`}</div>
      <p>${esc(c.rationale)}</p>
      ${c.review ? `<p class="muted small">${T.crossCheck}${T.colon}${esc(c.review)}</p>` : ""}
      ${c.warning ? `<p class="small">⚠️ ${T.sourceMissing}${T.colon}${esc(c.warning)}</p>` : ""}
      ${c.lost?.length ? `<p class="small">⚠️ ${T.lostValues}${T.colon}${esc(c.lost.join(", "))}</p>` : ""}
      <div class="diff before" lang="fr">${before}</div>
      <div class="diff after" lang="fr">${after || `<span class="muted">${T.removedWhole}</span>`}</div>
      <div class="muted small">${T.from} ${sources || "—"}${c.source_url ? ` · ${extLink(c.source_url, "source")}` : ""}</div>
    </div>
  </div>`;
}

function viewReview(r, title) {
  const num = id => Number(id.slice(1));
  const groups = {};
  for (const c of [...r.corrections].sort((a, b) => num(a.group) - num(b.group) || num(a.id) - num(b.id)))
    (groups[c.group] ||= []).push(c);
  const broken = new Set(r.corrections.filter(c => c.check !== "ok").map(c => c.group));
  const figures = [Object.values(r.triage).reduce((a, b) => a + b, 0), r.triage.correct, r.corrections.length, r.additions.length];
  page.innerHTML = `${title}
    <div class="figures">${figures.map((n, i) => `<div><b>${n}</b>${T.reviewFigures[i]}</div>`).join("")}</div>
    ${r.reading?.mode === "chapters" ? `<p class="banner small">${T.byChapter(r.reading.tokens, r.reading.budget)}</p>` : ""}
    <h2>${T.corrections}</h2>
    <p class="muted small">${T.reviewHelp}</p>
    ${Object.entries(groups).map(([g, cs]) => cs.length > 1
      ? `<div class="group"><p class="muted small">${T.group(g)}${broken.has(g) ? T.groupLeftOut : ""}</p>${cs.map(c => correctionCard(c, r)).join("")}</div>`
      : correctionCard(cs[0], r)).join("") || `<p class="muted">${T.noCorrection}</p>`}
    <details><summary>${T.leads(r.additions.length)}</summary>
      <ul>${r.additions.map(a => `<li>${a.url ? extLink(a.url, esc(a.title)) : esc(a.title)}${T.colon}${esc(a.reason)}</li>`).join("") || `<li>${T.none}</li>`}</ul></details>
    <details><summary>${T.noticed(r.findings.length)}</summary>
      <ul>${r.findings.map(f => `<li>${esc(f)}${excerpts(r.finding_excerpts?.[f])}</li>`).join("") || `<li>${T.nothing}</li>`}</ul>
      ${r.findings.length ? `<p class="muted small">${T.noticedHelp}</p>` : ""}</details>
    <details><summary>${T.leftovers(r.leftovers.length)}</summary>
      <ul>${r.leftovers.map(h => `<li><code>${esc(h.page)}:${h.line}</code> (${esc(h.tokens.join(", "))}) : ${esc(h.text)}</li>`).join("") || `<li>${T.none}</li>`}</ul></details>
    <details><summary>${T.claims(r.claims_due.length)}</summary>
      <ul>${r.claims_due.map(c => `<li>${esc(c.recheckBy)} <code>${esc(c.page)}</code> : ${esc(c.claim)}</li>`).join("") || `<li>${T.none}</li>`}</ul></details>
    <p class="small"><a href="/api/runs/${encodeURIComponent(r.thread)}/report" target="_blank">${T.report}</a></p>
    ${r.billed_next ? `<p class="error-text">${T.billedNext}</p>` : ""}
    <div class="bar">
      <button id="nothing">${T.applyNothing}</button>
      <button class="primary" id="apply"></button>
    </div>`;
  const boxes = [...page.querySelectorAll(".correction input")];
  boxes.filter(i => broken.has(i.dataset.group)).forEach(i => { i.checked = false; i.disabled = true; });
  const count = () => {
    const n = boxes.filter(i => i.checked).length;
    $("#apply").textContent = T.applyN(n);
    $("#apply").disabled = n === 0;
  };
  boxes.forEach(i => i.onchange = () => {
    boxes.filter(o => o.dataset.group === i.dataset.group && !o.disabled).forEach(o => o.checked = i.checked);
    count();
  });
  count();
  const send = async accept => {
    page.querySelectorAll(".bar button").forEach(b => b.disabled = true);
    await api(`/api/runs/${encodeURIComponent(r.thread)}/review`, { accept });
    route();
  };
  $("#apply").onclick = () => send(boxes.filter(i => i.checked).map(i => i.dataset.id));
  $("#nothing").onclick = () => confirm(T.confirmNothing) && send("none");
}

async function viewPublish(r, title) {
  const p = { mirror_problems: [], link_problems: [], ...r.pause };
  const linksChecked = p.link_problems !== null;   // null: the guide declares no source audit
  if (!linksChecked) p.link_problems = [];
  const diff = await api(`/api/runs/${encodeURIComponent(r.thread)}/diff`).catch(() => "");
  const color = l => l.startsWith("+") && !l.startsWith("+++") ? "plus" : l.startsWith("-") && !l.startsWith("---") ? "minus" : "";
  const figures = [r.applied.length, r.mirrored.length, p.audit_ok === null ? T.notChecked : p.audit_ok ? "OK" : T.failed, linksChecked ? p.link_problems.length : T.notChecked];
  page.innerHTML = `${title}
    <div class="figures">${figures.map((n, i) => `<div><b>${n}</b>${T.publishFigures[i]}</div>`).join("")}</div>
    <div class="card">
      <p>${T.branchReady(esc(p.branch))}</p>
      ${r.weight?.before ? `<p>${T.weight(r.weight)}${(r.weight.pages || []).length ? ` ${T.weightMost} ${r.weight.pages.slice(0, 3).map(([p, d]) => `<code>${esc(p)}</code> ${signedKb(d)}`).join(", ")}.` : ""}</p>` : ""}
      ${p.audit_ok !== false ? "" : `<p class="error-text">${T.auditsRed}</p><pre>${esc(r.audit_log)}</pre>`}
      ${p.mirror_problems.length ? `<p><b>${T.translation}</b></p><ul>${p.mirror_problems.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${p.link_problems.length ? `<p><b>${T.linksTitle}</b> ${T.linksNew}</p><ul>${p.link_problems.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="muted">${linksChecked ? T.linksOk : T.linksNotChecked}</p>`}
    </div>
    <details open><summary>${T.changes}</summary>
      <pre>${diff.split("\n").map(l => `<span class="${color(l)}">${esc(l)}</span>`).join("\n") || esc(p.diffstat)}</pre></details>
    <div class="bar">
      <button id="no">${T.doNotPublish}</button>
      <button class="primary" id="yes">${p.local ? T.keepLocal : T.publish}</button>
    </div>`;
  const send = async go => {
    page.querySelectorAll(".bar button").forEach(b => b.disabled = true);
    await api(`/api/runs/${encodeURIComponent(r.thread)}/publish`, { go });
    route();
  };
  $("#yes").onclick = () => send(true);
  $("#no").onclick = () => confirm(T.confirmNo) && send(false);
}

function viewEnd(r, title) {
  const pr = r.pr_url ? extLink(r.pr_url, "pull request") : "";
  const text = (T.end[r.status] || (() => ""))(pr, esc(r.branch));
  page.innerHTML = `${title}
    <div class="card"><p>${text}</p>
      ${r.error ? `<p class="error-text">${esc(r.error)}</p>` : ""}
      ${r.status === "stopped" ? `<button class="primary" id="resume">${T.resume}</button>` : ""}</div>
    ${r.applied.length ? `<p>${T.applied}${T.colon}${r.applied.join(", ")}</p>` : ""}
    ${r.report_path ? `<p class="small"><a href="/api/runs/${encodeURIComponent(r.thread)}/report" target="_blank">${T.report}</a></p>` : ""}`;
  const b = $("#resume");
  if (b) b.onclick = async () => { b.disabled = true; await api(`/api/runs/${encodeURIComponent(r.thread)}/resume`, {}); route(); };
}

// --- Check the guide ---------------------------------------------------------------------------------------
let followTimer = null;  // timer following a running check
const checkBadge = p => {
  const V = T.verif, [text, cls] = {
    running: [V.running, "attention"], "to-handle": [V.toHandle(p.counts.open), "attention"],
    handled: [V.handled, "ok"], clear: [V.ok, "ok"],
  }[p.status] || [p.status, "neutral"];
  return `<span class="badge ${cls}">${text}</span>${p.interrupted ? ` <span class="badge neutral">${V.interrupted}</span>` : ""}`;
};

async function viewChecks() {
  const [options, verifs] = await Promise.all([api("/api/verifications/options"), api("/api/verifications")]);
  const V = T.verif, titles = Object.fromEntries(options.map(o => [o.id, o.title[lang]]));
  // An estimate says where its price comes from when it is not a price set or fetched by the user (a default, none)
  const price = o => o.model ? cost(o.usd == null ? V.unknown : `≈ ${dollars(o.usd)}`) : V.free;
  const origin = o => o.model && o.price_origin && o.usd != null && !onSubscription()
    ? ` <span class="muted small">${esc(T.priceOrigin(o.price_origin))}</span>` : "";
  // What is left to handle comes first; a new check is folded away while leads remain (it would find them again)
  const pending = verifs.filter(p => ["to-handle", "running"].includes(p.status));
  const remaining = pending.reduce((s, p) => s + p.counts.open, 0);
  const checkCard = p => `<div class="card row${["handled", "clear"].includes(p.status) ? " finished" : ""}"><div class="grow"><b>${new Date(p.started * 1000).toLocaleString(lang)}</b>
        <div class="muted small">${p.checks.map(c => esc(titles[c] || c)).join(" · ")} · ${dollars(p.cost)}</div>
        <div class="muted small">${V.counts(p.counts)}</div></div>
        ${checkBadge(p)}
        <a href="#/check/${encodeURIComponent(p.id)}"><button${p.status === "to-handle" ? ' class="primary"' : ""}>${p.status === "to-handle" ? V.handle : T.details}</button></a></div>`;
  const older = verifs.filter(p => !pending.includes(p));
  page.innerHTML = `
    <h1>${V.title}</h1>
    <p class="subtitle">${V.intro}</p>
    ${pending.length ? `<h2>${V.toHandleTitle}</h2>${pending.map(checkCard).join("")}` : ""}
    <details class="new-check"${pending.length ? "" : " open"}><summary><h2>${V.newCheck}</h2></summary>
    ${remaining ? `<p class="attention-text">${V.warning(remaining)}</p>` : ""}
    ${options.map(o => `<label class="card option">
      <input type="checkbox" data-check="${o.id}" ${o.model ? "" : "checked"}>
      <div>
        <div class="header"><b>${esc(o.title[lang])}</b>
          <span class="badge ${o.model ? "attention" : "ok"}">${price(o)}</span>${origin(o)}
          ${o.tokens ? `<span class="muted small">${V.tokens(o.tokens)}</span>` : ""}</div>
        <p class="muted small">${esc(o.what[lang])}</p>
        <p class="muted small">${esc(o.note[lang])}${o.model ? ` · ${esc(o.model)}` : ""}${o.needs.length ? ` · ${V.needs(o.needs.map(n => titles[n]).join(", "))}` : ""}</p>
      </div></label>`).join("")}
    <p><button class="primary" id="start"></button></p>
    </details>
    <h2>${V.history}</h2>
    ${older.map(checkCard).join("") || `<p class="muted">${V.none}</p>`}`;
  const boxes = [...page.querySelectorAll("[data-check]")];
  const total = () => {
    const ids = new Set(boxes.filter(c => c.checked).map(c => c.dataset.check));
    options.filter(o => ids.has(o.id)).forEach(o => o.needs.forEach(n => ids.add(n)));
    const chosen = options.filter(o => ids.has(o.id)), usd = chosen.reduce((s, o) => s + (o.usd || 0), 0);
    $("#start").textContent = V.start(chosen.some(o => o.model) ? cost(`≈ ${dollars(usd)}`) : V.free);  // scripts only: free
    $("#start").disabled = ids.size === 0;
  };
  boxes.forEach(c => c.onchange = total);
  total();
  $("#start").onclick = async () => {
    $("#start").disabled = true;
    const { id } = await api("/api/verifications", { checks: boxes.filter(c => c.checked).map(c => c.dataset.check) });
    location.hash = `/check/${encodeURIComponent(id)}`;
  };
}

async function viewCheck(id) {
  clearTimeout(followTimer);
  const [v, options] = await Promise.all([api(`/api/verifications/${encodeURIComponent(id)}`), api("/api/verifications/options")]);
  if (location.hash.slice(1) !== `/check/${id}`) return;  // left the page meanwhile
  const V = T.verif, titles = Object.fromEntries(options.map(o => [o.id, o.title[lang]]));
  const list = (title, items) => items && items.length ? `<details><summary>${title} (${items.length})</summary><ul>${items.map(x => `<li>${x}</li>`).join("")}</ul></details>` : "";
  page.innerHTML = `
    <h1>${V.title} · ${new Date(v.started * 1000).toLocaleString(lang)} ${checkBadge(v)}</h1>
    <p class="subtitle">${V.cost(dollars(v.cost))} · ${V.counts(v.counts)}${v.commit ? ` · main @ <code>${esc(v.commit)}</code>` : ""}</p>
    ${v.error ? `<p class="error-text">${esc(v.error)}</p>` : ""}
    ${v.interrupted ? `<p class="muted">${V.interruptedText(v.missing.map(c => esc(titles[c] || c)).join(", ") || "—")}</p>` : ""}
    ${v.running ? "" : `<p><button class="small-button" id="remove">${V.remove}</button></p>`}
    ${Object.keys(v.runs).length ? `<h2>${V.fixRuns}</h2>${Object.entries(v.runs).map(([t, run]) => `
      <div class="card row${FINISHED.includes(run.status) ? " finished" : ""}"><div class="grow"><b>${esc(t)}</b>
        ${run.pr_url ? `<div class="muted small">${extLink(run.pr_url, run.pr_url)}</div>` : ""}</div>
        ${badge(run.status)}
        ${run.status === "pr-open" ? extLink(run.pr_url, `<button class="primary">${T.merge()}</button>`)
          : `<a href="#/run/${encodeURIComponent(t)}"><button${["review", "publish"].includes(run.status) ? ' class="primary"' : ""}>${
            T.buttons[run.status] || T.details}</button></a>`}</div>`).join("")}` : ""}
    ${v.checks.map(c => {
      const r = v.results[c];
      // A check whose findings are all handled (sent or dismissed) is done, even if it found problems
      const stateBadge = !r && v.running && v.current === c ? `<span class="badge attention">${V.checking}</span>`
        : !r ? `<span class="badge neutral">${v.running ? V.waiting : "—"}</span>`
        : r.summary?.startsWith("could not run") ? `<span class="badge error">${V.failed}</span>`
        : r.findings?.length && !r.open ? `<span class="badge ok">${V.handled}</span>`
        : `<span class="badge ${r.ok ? "ok" : "attention"}">${r.ok ? V.ok : r.open ? V.toHandle(r.open) : V.problems}</span>`;
      // Folded by default once nothing is left to do in it (all handled, or fine); the reader's choice is kept
      const finished = r && !r.open && !r.summary?.startsWith("could not run") && (r.ok || r.findings?.length);
      const isOpen = FOLDS[`${id}/${c}`] ?? !finished;
      return `<details class="card foldable" data-fold="${id}/${c}"${isOpen ? " open" : ""}><summary class="header"><b>${esc(titles[c] || c)}</b>${stateBadge}${r?.open ? ` <button class="small-button" data-tick-card="${c}">${V.tickCard(r.open)}</button>` : ""}</summary>
        ${r ? `<p class="muted small">${esc(r.summary)}</p>
          ${list(V.dead, (r.dead || []).map(d => `${extLink(d.url, esc(d.url))} — ${esc(d.status)} ${esc(d.code ?? "")} (${esc(d.pages.join(", "))})`))}
          ${list(V.blocked, (r.blocked || []).map(d => `${extLink(d.url, esc(d.url))} (${esc(d.pages.join(", "))})`))}
          ${list(V.claims, (r.claims || []).map(x => `${esc(x.recheckBy)} <code>${esc(x.page)}</code> : ${esc(x.claim)}`))}
          ${list(V.pagesDue, (r.pages_due || []).map(esc))}
          ${r.sizes ? sizesBlock(r.sizes) : ""}
          ${r.log ? `<details><summary>${V.log}</summary><pre>${esc(r.log)}</pre></details>` : ""}
          ${(r.findings || []).length ? `${r.fixable ? "" : `<p class="muted small">${V.notFixable}</p>`}<ul class="leads">${r.findings.map((f, i) => lead(f, r.fixable, c, r.mode, i + 1, r.excerpts?.[f])).join("")}</ul>` : ""}` : ""}
      </details>`;
    }).join("")}
    <div class="bar">
      <button id="all">${V.tickAll}</button><button id="nothing">${V.untickAll}</button>
      <button id="dismiss"></button>
      <button class="primary" id="fix"></button>
    </div>`;
  // A finding is open (checkbox), sent to a fix run (link to the run) or dismissed (can be reopened)
  // Handled findings stay one line; an open one shows the passages it is about
  function lead(f, fixable, card, mode = "fix", n = 0, passages = []) {
    const h = v.handled[f], num = `<span class="num">${n}.</span>`;  // per card, stable: handled lines keep theirs
    if (h?.status === "fix") {
      const run = v.runs[h.thread] || {};
      return `<li class="handled">${num} <span class="badge ok">${V.sent}</span> <a href="#/run/${encodeURIComponent(h.thread)}">${esc(h.thread)}</a>
        ${run.status ? badge(run.status) : ""}${run.pr_url ? ` ${extLink(run.pr_url, "PR")}` : ""} · ${esc(f)}</li>`;
    }
    if (h?.status === "dismissed") return `<li class="handled">${num} <span class="badge neutral">${V.dismissed}</span> <button class="small-button" data-reopen="${esc(f)}">${V.reopen}</button> ${esc(f)}</li>`;
    return `<li><label><input type="checkbox" data-lead="${esc(f)}" data-fixable="${fixable}" data-mode="${mode}" data-card="${card}"> ${num} <span>${esc(f)}</span></label>${excerpts(passages)}</li>`;
  }
  const boxes = [...page.querySelectorAll("[data-lead]")];
  const ticked = () => boxes.filter(c => c.checked);
  const count = () => {
    const ok = ticked().filter(c => c.dataset.fixable === "true"), n = ok.length, e = ticked().length;
    const by = {};
    ok.forEach(c => { by[c.dataset.mode] = (by[c.dataset.mode] || 0) + 1; });
    // A compaction run: its cross-check, plus a share per finding, priced with the models of the Settings
    const o = options.find(o => o.id === "compaction") || {}, run = o.run_usd ? o.run_usd + (o.run_usd_each || 0) * (by.compact || 0) : 0;
    $("#fix").textContent = V.createFix(by, cost, { compact: run ? `≈ ${dollars(run)}` : "" }); $("#fix").disabled = n === 0 || v.running;
    $("#dismiss").textContent = V.dismiss(e); $("#dismiss").disabled = e === 0 || v.running;
  };
  boxes.forEach(c => c.onchange = count);
  // Tick or untick every open finding of one card (all ticked: untick)
  page.querySelectorAll("[data-fold]").forEach(d => d.ontoggle = () => { FOLDS[d.dataset.fold] = d.open; });
  page.querySelectorAll("[data-tick-card]").forEach(b => b.onclick = e => {
    e.preventDefault();  // in the card's summary: tick, do not fold
    const card = boxes.filter(c => c.dataset.card === b.dataset.tickCard), all = card.every(c => c.checked);
    card.forEach(c => c.checked = !all);
    count();
  });
  $("#all").onclick = () => { boxes.forEach(c => c.checked = true); count(); };
  $("#nothing").onclick = () => { boxes.forEach(c => c.checked = false); count(); };
  count();
  const leads = (findings, status) => api(`/api/verifications/${encodeURIComponent(id)}/leads`, { findings, status }).then(() => viewCheck(id));
  if ($("#remove")) $("#remove").onclick = () => confirm(V.confirmRemove)
    && api(`/api/verifications/${encodeURIComponent(id)}/delete`, {}).then(() => { location.hash = "/check"; });
  page.querySelectorAll("[data-reopen]").forEach(b => b.onclick = () => leads([b.dataset.reopen], "open"));
  if (!boxes.length) page.querySelector(".bar").remove();
  else {
    $("#dismiss").onclick = () => leads(ticked().map(c => c.dataset.lead), "dismissed");
    $("#fix").onclick = async () => {
      $("#fix").disabled = true;
      // One run per mode: content fixes, translation fixes and trims do not take the same path
      const threads = [];
      for (const mode of ["fix", "translation", "compact"]) {
        const text = ticked().filter(c => c.dataset.fixable === "true" && c.dataset.mode === mode).map(c => c.dataset.lead).join("\n");
        if (text) threads.push((await api("/api/fix", { text, verification: id, mode })).thread);
      }
      location.hash = `/run/${encodeURIComponent(threads[0])}`;
    };
  }
  if (v.running) followTimer = setTimeout(() => viewCheck(id).catch(() => {}), 3000);
}

// The size check: what the guide gained, its heaviest pages (those over their budget first), the weight per chapter
function sizesBlock(s) {
  const V = T.verif;
  const grew = p => !("before" in p) ? "" : p.before == null ? ` · ${V.newPage}` : p.bytes !== p.before ? ` · ${signedKb(p.bytes - p.before)}` : "";
  const row = p => `<li><code>${esc(p.page)}</code> — <b>${kb(p.bytes)}</b> / ${kb(p.budget * 1024)}${grew(p)}${p.readonly ? ` · ${V.readonly}` : ""}${
    p.over ? ` <span class="badge attention">${V.over}</span>` : ""}
    <div class="muted small">${[...p.sections.map(x => `${esc(x.title)} ${kb(x.bytes)}`),
      ...(p.footnotes.count ? [V.notes(p.footnotes.count, kb(p.footnotes.bytes))] : [])].join(" · ")}</div></li>`;
  return `${s.growth ? `<p class="small">${V.growth(s.growth)}</p>` : ""}
    <details${s.over ? " open" : ""}><summary>${V.heaviest} (${s.heaviest.length})</summary><ul>${s.heaviest.map(row).join("")}</ul></details>
    <details><summary>${V.perChapter} (${s.chapters.length})</summary><ul>${s.chapters.map(c =>
      `<li><code>${esc(c.chapter)}</code> — ${kb(c.bytes)}, ${c.pages} ${V.pagesWord}</li>`).join("")}</ul></details>`;
}

const FOLDS = {};  // check cards folded or opened by the reader, by verification/check, kept across refreshes

// --- Report errors -----------------------------------------------------------------------------------
function viewReport() {
  page.innerHTML = `
    <h1>${T.reportTitle}</h1>
    <p class="subtitle">${T.reportIntro} ${onSubscription() ? T.reportSubscription : T.reportCost}</p>
    <textarea id="text" placeholder="${esc(T.reportExample)}"></textarea>
    <p><button class="primary" id="send">${T.reportButton}</button></p>`;
  $("#send").onclick = async () => {
    const text = $("#text").value.trim();
    if (!text) return;
    $("#send").disabled = true;
    const { thread } = await api("/api/fix", { text });
    location.hash = `/run/${encodeURIComponent(thread)}`;
  };
}

// --- Costs -------------------------------------------------------------------------------------------------
// --- Sources of the watch ----------------------------------------------------------------------------
const SOURCE_ORDER = ["error", "noise", "silent", "leads", "quiet", "useful"];  // what to look at first
const SOURCE_CLASS = { error: "error", noise: "attention", silent: "attention", leads: "neutral", quiet: "neutral", useful: "ok" };
// The columns, in the order of T.sources.columns: the field each one sorts by, and whether it is a number
const SOURCE_COLUMNS = [["id"], ["type"], ["last_item"], ["source_last"], ["collected", true], ["kept", true], ["judged", true], ["useful", true],
  ["proposed", true], ["accepted", true], ["verdict"]];
// The reader's choices, kept while the page is open: the column sorted (none: what to look at first), its
// direction, the states shown (none: all)
const SOURCES_VIEW = { sort: "", dir: 1, states: new Set() };

function sortSources(feeds) {
  const { sort, dir } = SOURCES_VIEW, number = (SOURCE_COLUMNS.find(c => c[0] === sort) || [])[1];
  const first = (a, b) => SOURCE_ORDER.indexOf(a.verdict) - SOURCE_ORDER.indexOf(b.verdict);
  const compare = !sort ? (a, b) => first(a, b) || b.collected - a.collected
    : sort === "verdict" ? (a, b) => dir * first(a, b)
    : number ? (a, b) => dir * (a[sort] - b[sort])
    // A source without a date stays at the bottom in both directions: it has nothing to compare
    : (a, b) => !a[sort] !== !b[sort] ? (a[sort] ? -1 : 1) : dir * String(a[sort]).localeCompare(String(b[sort]));
  return feeds.slice().sort((a, b) => compare(a, b) || a.id.localeCompare(b.id));
}

const SOURCE_TICKS = {};  // proposals ticked or unticked by the reader, kept while the page refreshes

async function viewSources() {
  clearTimeout(followTimer);
  const s = await api("/api/sources"), S = T.sources;
  if (location.hash.slice(1) !== "/sources") return;  // left the page meanwhile
  if (!s.file) { page.innerHTML = `<h1>${S.title}</h1><p class="subtitle">${S.none}</p>`; return; }
  const rules = S.rules(s.noise_min, s.noise_share), view = SOURCES_VIEW, check = s.check, busy = s.checking.running;
  s.feeds.forEach(f => { f.source_last = f.probe?.last || ""; });
  const by = v => s.feeds.filter(f => f.verdict === v);
  const cell = n => `<td class="number">${n || ""}</td>`;
  // What the source answered at the last check: its last publication, and what is wrong with it
  const answered = f => {
    const p = f.probe;
    if (!p) return "—";
    const note = p.state === "ok" ? "" : p.state === "moved" ? S.probe.moved(esc(p.moved)) : p.state === "stale" ? S.probe.stale(esc(p.last))
      : S.probe[p.state] || esc(p.state);
    return `${p.state === "stale" ? "" : esc(p.last) || "—"}${note ? `<div class="${p.state === "stale" ? "muted" : "error-text"} small">${note}</div>` : ""}`;
  };
  const what = f => esc(f.repo || f.author || f.url || f.name || "");
  const proposal = (p, group) => {
    const done = p.applied;
    const ticked = SOURCE_TICKS[p.id] ?? p.recommended;
    return `<li${done ? ' class="handled"' : ""}><label>${done ? `<span class="badge ok">${S.applied}</span>`
      : `<input type="checkbox" data-proposal="${p.id}" data-group="${group}"${ticked ? " checked" : ""}>`} <span><b>${esc(p.feed.id)}</b>
      <span class="muted">(${esc(p.feed.type || "rss")}${what(p.feed) ? `, ${what(p.feed)}` : ""})</span> : ${esc(S.why[p.why](p))}${
      p.recommended && !done ? ` <span class="badge neutral">${S.recommended}</span>` : ""}${
      done?.pr_url ? ` ${extLink(done.pr_url, "PR")}` : ""}</span></label></li>`;
  };
  const groups = check ? [
    ["remove", check.proposals.filter(p => p.action === "remove")], ["change", check.proposals.filter(p => p.action === "change")],
    ["add", check.proposals.filter(p => p.action === "add" && p.why !== "no-advisories")],
    ["advisories", check.proposals.filter(p => p.why === "no-advisories")]].filter(([, list]) => list.length) : [];
  const last = check?.applied?.filter(a => !a.state).at(-1);  // the pull request (or branch) still to merge
  const draw = () => {
    const shown = sortSources(s.feeds.filter(f => !view.states.size || view.states.has(f.verdict)));
    const arrow = key => view.sort !== key ? "" : view.dir > 0 ? " ▲" : " ▼";
    page.innerHTML = `
    <h1>${S.title}</h1>
    <p class="subtitle">${s.period.watches ? S.intro(s.period, s.runs, esc(s.file)) : S.noHistory}</p>
    <p><button class="primary" id="check"${busy ? " disabled" : ""}>${busy ? S.checking(s.checking.done, s.checking.total) : S.check}</button>
      <span class="muted small">${check ? S.checked(new Date(check.checked).toLocaleString(lang)) : S.neverChecked} ${S.checkHelp}</span></p>
    ${s.checking.error ? `<p class="error-text">${esc(s.checking.error)}</p>` : ""}
    ${check ? `<h2>${S.proposals(check.proposals.filter(p => !p.applied).length, check.proposals.filter(p => p.applied).length)}</h2>
      ${last ? `<p class="small">${S.appliedTo(esc(last.branch), last.pr_url ? extLink(last.pr_url, esc(last.pr_url)) : "")}</p>` : ""}
      ${groups.length ? groups.map(([g, list]) => `<details class="card foldable"${g === "advisories" ? "" : " open"}>
        <summary class="header"><b>${S.groups[g]}</b> <span class="badge neutral">${list.length}</span>${
          list.some(p => !p.applied) ? ` <button class="small-button" data-tick-group="${g}">${T.verif.tickCard(list.filter(p => !p.applied).length)}</button>` : ""}</summary>
        <ul class="leads">${list.map(p => proposal(p, g)).join("")}</ul></details>`).join("") : `<p class="muted">${S.noProposals}</p>`}
      <p class="muted small">${S.staleNote(check.stale_days)}</p>
      ${view.error ? `<p class="error-text">${esc(view.error)}</p>` : ""}
      ${check.proposals.some(p => !p.applied) ? `<div class="bar"><button id="all">${T.verif.tickAll}</button><button id="nothing">${T.verif.untickAll}</button>
        <button class="primary" id="apply"></button></div>` : ""}` : ""}
    <ul class="small filters">
      <li><button class="badge neutral${view.states.size ? " dim" : ""}" data-state="" aria-pressed="${!view.states.size}">${S.all(s.feeds.length)}</button> ${S.filterHelp}</li>
      ${SOURCE_ORDER.filter(v => by(v).length).map(v => `<li><button class="badge ${SOURCE_CLASS[v]}${view.states.size && !view.states.has(v) ? " dim" : ""}"
        data-state="${v}" aria-pressed="${view.states.has(v)}">${S.count(by(v).length, S.verdicts[v])}</button> ${rules[v]}</li>`).join("")}</ul>
    <p class="muted small">${S.shown(shown.length, s.feeds.length)}${view.sort ? ` · <button class="small-button" id="default-sort">${S.defaultSort}</button>` : ""}</p>
    <div class="card wide"><table>
      <thead><tr>${S.columns.map((c, i) => { const [key, number] = SOURCE_COLUMNS[i]; return `<th${number ? ' class="number"' : ""}${
        view.sort === key ? ` aria-sort="${view.dir > 0 ? "ascending" : "descending"}"` : ""}><button class="sort" data-sort="${key}" title="${esc(S.sortBy(c))}">${c}${arrow(key)}</button></th>`; }).join("")}</tr></thead>
      <tbody>${shown.map(f => `<tr>
        <td><b>${esc(f.id)}</b><div class="muted small">${f.url ? extLink(f.url, esc(f.target)) : esc(f.target)}</div></td>
        <td class="small">${esc(f.type)}${f.tier ? ` · ${esc(f.tier)}` : ""}</td>
        <td class="small nowrap">${esc(f.last_item) || "—"}</td>
        <td class="small nowrap">${answered(f)}</td>
        ${cell(f.collected)}${cell(f.kept)}${cell(f.judged)}${cell(f.useful)}${cell(f.proposed)}${cell(f.accepted)}
        <td class="nowrap"><span class="badge ${SOURCE_CLASS[f.verdict]}" title="${esc(rules[f.verdict])}">${S.verdicts[f.verdict]}</span>${
          f.insurance ? ` <span class="muted small" title="${esc(S.insurance)}">🛡</span>` : ""}</td></tr>`).join("")}</tbody>
    </table></div>
    <p class="muted small">${S.help.join(" ")} 🛡 ${S.insurance}.</p>
    ${s.removed.length ? `<p class="muted small">${S.removed(s.removed.length)} ${s.removed.map(r => `<code>${esc(r.id)}</code> (${r.items})`).join(", ")}</p>` : ""}`;
    // A state: shown alone, or with the others already chosen; « all » clears the choice
    page.querySelectorAll("[data-state]").forEach(b => b.onclick = () => {
      const v = b.dataset.state;
      if (!v) view.states.clear(); else if (view.states.has(v)) view.states.delete(v); else view.states.add(v);
      draw();
    });
    // A column: a first click sorts it (numbers from the largest, texts from A), a second one turns it round
    page.querySelectorAll("[data-sort]").forEach(b => b.onclick = () => {
      const key = b.dataset.sort, number = SOURCE_COLUMNS.find(c => c[0] === key)[1];
      view.dir = view.sort === key ? -view.dir : number ? -1 : 1;
      view.sort = key;
      draw();
      page.querySelector(`[data-sort="${key}"]`)?.focus();  // the keyboard stays on the column
    });
    if ($("#default-sort")) $("#default-sort").onclick = () => { view.sort = ""; view.dir = 1; draw(); };
    $("#check").onclick = async () => { $("#check").disabled = true; await api("/api/sources/check", {}); viewSources(); };
    // The proposals: ticked ones go to one pull request
    const boxes = [...page.querySelectorAll("[data-proposal]")];
    const count = () => {
      const n = boxes.filter(b => b.checked).length;
      if ($("#apply")) { $("#apply").textContent = S.apply(n, s.repository); $("#apply").disabled = n === 0 || busy; }
    };
    const tick = (list, on) => { list.forEach(b => { b.checked = on; SOURCE_TICKS[b.dataset.proposal] = on; }); count(); };
    boxes.forEach(b => b.onchange = () => { SOURCE_TICKS[b.dataset.proposal] = b.checked; count(); });
    // A whole group (all ticked: untick it), or every proposal
    page.querySelectorAll("[data-tick-group]").forEach(b => b.onclick = e => {
      e.preventDefault();  // in the group's title: tick, do not fold
      const group = boxes.filter(c => c.dataset.group === b.dataset.tickGroup);
      tick(group, !group.every(c => c.checked));
    });
    if ($("#all")) { $("#all").onclick = () => tick(boxes, true); $("#nothing").onclick = () => tick(boxes, false); }
    count();
    if ($("#apply")) $("#apply").onclick = async () => {
      $("#apply").disabled = true;
      try {
        await api("/api/sources/apply", { ids: boxes.filter(b => b.checked).map(b => b.dataset.proposal) });
        view.error = "";
      } catch (e) {
        view.error = e.message;
      }
      viewSources();
    };
  };
  draw();
  if (busy) followTimer = setTimeout(() => viewSources().catch(() => {}), 1500);
}

async function viewCosts() {
  const c = await api("/api/costs");
  const number = n => n.toLocaleString(lang);
  // Calls made through Claude Code on a subscription cost nothing: their columns show up with the first of them
  const calls = c.month.reduce((s, r) => s + (r.subscription || 0), 0), spared = c.month.reduce((s, r) => s + (r.spared || 0), 0);
  const columns = [...T.columns, ...(calls ? T.subscriptionColumns : [])];
  const table = (rows, title) => `<table><thead><tr><th>${title}</th>${columns.map(x => `<th class="number">${x}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(r => `<tr><td>${esc(r.key)}</td><td class="number">${r.calls}</td><td class="number">${number(r.in)}</td><td class="number">${number(r.out)}</td><td class="number">${dollars(r.cost)}</td>${
      calls ? `<td class="number">${r.subscription || ""}</td><td class="number">${r.subscription ? dollars(r.spared) : ""}</td>` : ""}</tr>`).join("")}</tbody></table>`;
  const total = c.month.reduce((s, r) => s + r.cost, 0);
  page.innerHTML = `
    <h1>${T.costsTitle}</h1>
    <p class="subtitle">${T.costsIntro(dollars(total))}${calls ? ` ${T.costsSubscription(calls, dollars(spared))}` : ""}</p>
    ${Object.keys(c.origins || {}).length ? `<p class="muted small">${T.costsOrigins} ${Object.entries(c.origins)
      .map(([o, n]) => `${esc(T.priceOrigin(o))} (${n})`).join(" · ")}</p>` : ""}
    <h2>${T.byMonth}</h2><div class="card">${table(c.month, T.month)}</div>
    <h2>${T.byRun}</h2><div class="card">${table([...c.run].reverse(), T.run)}</div>`;
}

header();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { window.themes.apply(); header(); });  // the system's mode changes (evening): follow it
// The height of the header (it wraps on a narrow window, grows with the text): what sticks under it starts there
new ResizeObserver(() => document.documentElement.style.setProperty("--header-h", `${$("header").offsetHeight}px`)).observe($("header"));
watchNotices();
route();
// The engine in use arrives a moment later (the server asks Claude Code): on a subscription, the costs shown change
api("/api/info").then(i => { info = i; header(); if (onSubscription()) route(); }).catch(() => {});
