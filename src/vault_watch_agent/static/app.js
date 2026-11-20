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
    nav: { watches: "Veilles", sources: "Sources", check: "Vérifier le guide", report: "Signaler ou proposer", costs: "Coûts" },
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
        stale: d => `rien depuis le<br>${d}` },
      staleNote: days => `Une source qui n'a rien publié depuis ${days} jours n'est pas proposée au retrait : un outil qui ne bouge plus est une information sur le sujet du guide, c'est la page qui le recommande qu'il faut regarder.`,
      proposals: (n, open, later) => `Propositions : ${n} à décider${open ? `, ${open} dans une pull request ouverte` : ""}${later ? `, ${later} reportée(s)` : ""}`, noProposals: "Aucun changement à proposer.",
      groups: { remove: "Retirer", change: "Modifier", add: "Ajouter : cités dans le guide, suivis par aucune source", advisories: "Ajouter : failles de sécurité d'outils déjà suivis pour leurs versions" },
      why: {
        unreachable: p => `la source ne répond pas (${p.error})`, archived: () => "le dépôt est archivé",
        moved: p => `le dépôt a été déplacé vers ${p.new.repo}`, empty: () => "la source répond et ne liste rien",
        noise: p => `${p.judged} éléments jugés par le modèle sur la période, ${p.kept} retenu(s), aucune correction proposée`,
        "not-named": () => "aucune page du guide ne la nomme plus",
        cited: p => `cité dans ${p.pages} pages (${p.examples.join(", ")})`,
        "no-advisories": p => `suivi pour ses versions (${p.of}), pas pour ses failles`,
      },
      recommended: "un fait tranche", applied: "dans la PR", later: "reportée", decideNow: "Décider maintenant",
      putOff: n => `Reporter ${n} à la prochaine vérification`,
      putOffHelp: "Reporter retire une proposition de la liste sans rien changer au guide : la prochaine vérification la proposera de nouveau si elle tient toujours.",
      search: "Filtrer : nom, dépôt, type…", scrollLeft: "Voir les colonnes de gauche", scrollRight: "Voir les colonnes de droite",
      apply: (n, repo) => repo ? `Ouvrir une pull request avec ${n} changement(s)` : `Créer une branche avec ${n} changement(s)`,
      appliedTo: (branch, pr) => pr ? `Pull request ouverte : ${pr}` : `Changements sur la branche ${branch} (guide sans dépôt : à fusionner à la main).`,
      all: n => `Toutes (${n})`, filterHelp: "Clique un état pour ne voir que lui (plusieurs possibles), un titre de colonne pour trier.",
      shown: (n, total) => n === total ? `${total} sources` : `${n} source(s) affichée(s) sur ${total}`,
      sortBy: c => `Trier par « ${c} » (un second clic inverse)`, defaultSort: "Tri par défaut",
      count: (n, label) => `${n} ${label}`,
    },
    menu: { site: "Site du guide", repo: forge => `Dépôt sur ${forge}`, chapters: "Chapitres", code: "Code de l'agent",
      open: "Liens et chapitres du guide", older: "Afficher les plus anciens", burger: "Menu" },
    chapters: {
      title: "Chapitres",
      intro: "L'agent travaille chapitre par chapitre à trois endroits : l'exploration du web (un appel payant par chapitre), le contrôle des traductions (un appel par chapitre) et la lecture du guide quand il ne tient pas dans la fenêtre du modèle. Un chapitre réunit les pages qu'un lecteur consulterait ensemble et qu'une même actualité ferait changer.",
      now: "1. Le découpage actuel", sourceAuto: "règle automatique", sourceManifest: "déclaré dans le manifeste du guide",
      autoHelp: (big, small) => `Pour les pages qu'aucun chapitre déclaré ne prend, la règle automatique fait un chapitre par dossier de premier niveau, découpe un dossier de plus de ${big} Ko (par sous-dossier, sinon par tranches de pages) et réunit ceux de moins de ${small} Ko.`,
      cols: ["Chapitre", "Pages", "Poids", "Exploré par défaut", "Origine"],
      declared: "manifeste", auto: "automatique", yes: "oui", no: "non", kb: n => `${n} Ko`,
      change: "2. Préparer un nouveau découpage",
      changeHelp: "Deux façons, qui se combinent : demander une proposition à un modèle puis l'ajuster à la main, ou tout écrire à la main. Rien n'est enregistré avant l'étape 3.",
      askTitle: "Demander un découpage à un modèle",
      askWhat: "Le modèle lit le plan du guide (chemin, poids, titre et intertitres de chaque page, pas le texte) et propose des chapitres, avec ceux à ne pas explorer par défaut (un lexique, les pages sur le projet). Rien n'est écrit : tu relis et tu ajustes ci-dessous.",
      ask: c => `Proposer un découpage · ${c}`, asking: "Le modèle lit le plan du guide…",
      asked: c => `Proposition reçue (${c}). Relis-la, ajuste-la, puis enregistre.`,
      byHand: "Les chapitres du nouveau découpage", fromNow: "Reprendre le découpage actuel", add: "Ajouter un chapitre", remove: "Retirer",
      name: "Nom", paths: "Chemins, un par ligne : un dossier terminé par /, un motif avec * ou **, ou une page", explore: "exploré par défaut",
      pathsHelp: "Une page va au premier chapitre qui la prend. Les pages qu'aucun chapitre ne prend suivent la règle automatique.",
      result: "3. Vérifier et enregistrer",
      resultHelp: "Ce tableau se met à jour tout seul à chaque modification de l'étape 2 : il montre les chapitres que ton découpage donnerait, avec leur poids. Rien n'est écrit tant que tu n'as pas cliqué sur le bouton en dessous.",
      resultEmpty: "Ajoute un chapitre à l'étape 2, ou demande une proposition, pour voir ici ce que ça donne.", updating: "Calcul en cours…",
      tips: {
        explore: "Coché : ce chapitre est proposé d'office quand tu lances l'exploration du web (un appel payant par chapitre). Décoché : il reste disponible, mais c'est à toi de le cocher ce jour-là. À décocher pour un lexique ou des pages sur le projet, où le web n'apporte rien de neuf.",
        paths: "Exemples : 02-materiel/ prend tout le dossier ; 03-stack/*.md les pages placées directement dans ce dossier ; **/faq.md toutes les pages nommées faq.md ; 00-index.md une seule page.",
        origin: "« manifeste » : un chapitre que tu as déclaré dans le manifeste du guide. « automatique » : un chapitre formé par la règle automatique avec les pages rangées nulle part.",
        fromNow: "Recopie à l'étape 2 les chapitres du tableau de l'étape 1, pour les ajuster à la main au lieu de partir de zéro. Remplace ce qui est en cours d'édition.",
        backAuto: "Retire du manifeste tous les chapitres déclarés (par une pull request) : la règle automatique regroupe alors toutes les pages.",
      },
      save: forge => `Ouvrir la pull request sur ${forge}`, saveLocal: "Créer la branche",
      saveHelp: (manifest, base) => `Le découpage est écrit dans ${manifest}, sur une branche à part ; il s'applique une fois fusionné dans ${base}.`,
      needs: v => `Avant de fusionner : un manifeste qui déclare des chapitres demande l'agent ${v} ou plus récent partout où le guide est lu, y compris le workflow qui collecte sa veille. Un agent plus ancien refuse le manifeste.`,
      noManifest: "Ce guide n'a pas de manifeste : la commande vault-watch init en écrit un, et les chapitres s'y déclarent.",
      backAuto: "Revenir à la règle automatique",
      pending: "Une pull request déclare un découpage. Il s'appliquera une fois fusionnée ; d'ici là, rien d'autre ne peut être enregistré.",
      saved: "Pull request ouverte. Le découpage s'applique une fois fusionnée.",
      savedLocal: (branch, base) => `Branche ${branch} créée sur cette machine (guide sans dépôt) : fusionne-la dans ${base} pour appliquer le découpage.`,
      toml: "Lignes du manifeste (pour les coller à la main)", copy: "Copier", copied: "Copié",
      empty: "Aucun chapitre déclaré : ajoutes-en un, pars du découpage actuel ou demande une proposition.",
      edit: "Modifier les chapitres",
    },
    verif: {
      title: "Vérifier le guide",
      intro: "Un bilan de santé du guide entier, à la demande. Les contrôles gratuits utilisent les scripts du guide ; les autres font lire le guide par Claude. Les résultats sont des pistes : celles que tu gardes partent dans une passe fix, qui les vérifie sur les sources et passe par ta relecture.",
      free: "gratuit", tokens: n => `≈ ${n.toLocaleString("fr")} tokens`, unknown: "selon le résultat",
      needs: ids => `lance aussi : ${ids}`,
      start: c => `Lancer la vérification · ${c}`, history: "Vérifications précédentes",
      none: "Aucune vérification pour l'instant.", running: "En cours…", leads: n => `${n} piste(s)`,
      chapters: c => `Chapitres à explorer, un appel par chapitre coché (chacun : ${c}) :`,
      ideaLink: "Tu as déjà une idée ou une information précise ? Fais-la vérifier et écrire directement, sans recherche de pistes.",
      dig: "creuser (plusieurs sources, plus de recherches, un peu plus cher)",
      leadsAdd: "Une piste est une question à vérifier, pas une modification : rien n'est encore écrit. Le passage encadré est ce que le guide dit aujourd'hui (en surligné, la phrase visée ; les lignes voisines donnent le contexte). Pour chaque piste cochée, la passe d'ajouts lit les sources, puis propose de corriger ce qui est dépassé ou d'ajouter ce qui manque, dans toutes les pages concernées. Tu relis ces propositions avant qu'elles s'appliquent.",
      onlyFree: "Seulement les gratuits",
      waiting: "en attente", checking: "en cours…", ok: "RAS", problems: "à regarder", failed: "n'a pas pu tourner",
      notFixable: "Pas encore corrigeable par une passe fix (les traductions se corrigent depuis le français) : à reprendre à la main ou par une prochaine fonction.",
      seeDetails: "Détails", dead: "Sources qui ne répondent pas", blocked: "Bloquées par une protection anti-robots (souvent normales dans un navigateur)",
      claims: "Affirmations à revérifier", pagesDue: "Pages à revoir", log: "Journal",
      // by: the ticked leads per kind of run (fix, translation, compact, add); one run per kind
      createFix: (by, c, runs = {}) => {
        const kinds = [["fix", "fix", "≈ 6-8 $"], ["translation", "traduction", "< 1 $"], ["compact", "compactage", runs.compact || "≈ 5-6 $"], ["add", "ajouts", runs.add || "≈ 15-25 $"]].filter(k => by[k[0]]);
        return kinds.length > 1 ? `Créer ${kinds.length} passes : ${kinds.map(k => `${by[k[0]]} piste(s) en ${k[1]} (${c(k[2], k[0])})`).join(", ")}`
          : `Créer une passe ${(kinds[0] || [0, "fix"])[1]} avec ${kinds[0] ? by[kinds[0][0]] : 0} piste(s) · ${c((kinds[0] || [0, 0, "≈ 6-8 $"])[2], (kinds[0] || ["fix"])[0])}`;
      },
      heaviest: "Pages les plus lourdes", flaggedFirst: "Pages signalées, puis les plus lourdes", perChapter: "Par chapitre",
      over: "au-dessus de son plafond", grew: "a beaucoup grossi", newPage: "nouvelle page",
      readonly: "lecture seule", notes: (n, w) => `${n} notes de bas de page (${w})`, pagesWord: "page(s)",
      growth: g => `Le guide pesait ${kb(g.bytes)} le ${g.date} : ${signedKb(g.added)} en ${g.days} jours${g.new_pages ? `, dont ${g.new_pages} nouvelle(s) page(s)` : ""}.`,
      tickAll: "Tout cocher", untickAll: "Tout décocher",
      cost: c => `Coût : ${c}`,
      counts: c => c.open + c.fix + c.dismissed === 0 ? "aucune piste"
        : `${c.open} à traiter · ${c.fix} envoyée(s) à une passe · ${c.dismissed} écartée(s)`,
      toHandle: n => `${n} piste(s) à traiter`, handled: "Traitée", handle: "Traiter",
      tickCard: n => `Cocher / décocher les ${n}`,
      toHandleTitle: "À traiter", newCheck: "Nouvelle vérification", fixRuns: "Passes lancées depuis cette vérification",
      warning: n => `Il reste ${n} piste(s) à traiter ci-dessus. Une nouvelle vérification les retrouverait, en double : traite-les ou écarte-les d'abord.`,
      sent: "→ passe", dismissed: "écartée", reopen: "Rétablir",
      unchecked: "pas vérifiée par la passe", resend: "Remettre à traiter",
      context: "Chaque appel de piste lit", contextGuide: "tout le guide", contextPages: "les pages de la piste et le plan du guide",
      contextTip: "Tout le guide : l'appel voit chaque page. C'est le plus sûr et le plus cher, car le guide est relu à chaque tour de recherche. Les pages de la piste et le plan : l'appel lit les pages que la piste nomme ou demande de lire, plus la liste de toutes les pages avec leurs titres ; il ne modifie que ces pages. Une piste qui ne nomme aucune page lit quand même tout le guide. Dans les deux cas, la relecture croisée lit ensuite tout le guide et complète ou corrige.",
      uncheckedAll: n => `${n} piste(s) envoyée(s) n'ont pas été vérifiées par leur passe : rien n'a été cherché ni modifié pour elles. Remets-les à traiter pour les renvoyer.`,
      resendAll: n => n > 1 ? `Remettre les ${n} à traiter` : "Remettre à traiter", dismiss: n => `Écarter ${n} piste(s)`,
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
    // The server writes this line in English (graph.usage_line, also in the report): its words, said in French
    usageLine: s => String(s || "").replace(" calls, ", " appels, ").replace(" in (", " tokens lus (dont ").replace(" from cache) / ", " du cache) / ")
      .replace(" out, ", " écrits, ").replace("on the subscription, not billed", "sur l'abonnement, non facturés"),
    canClose: "Tu peux fermer la page : l'analyse continue sur le serveur, et l'état est enregistré à chaque étape.",
    progress: (min, cost) => `Démarré il y a ${min} min · coût de ce passage ≈ ${cost}`,
    applyId: id => `Appliquer ${id}`,
    crossCheck: "Relecture globale", from: "D'après", colon: " : ",
    byChapter: (t, b) => `Relecture globale chapitre par chapitre : le guide (≈ ${t.toLocaleString("fr")} tokens) dépasse ce qu'un appel du modèle peut lire (${b.toLocaleString("fr")}). Une contradiction entre deux chapitres peut échapper.`,
    lostValues: "Plus aucune page ne le dit ensuite", removedWhole: "(passage supprimé)",
    weight: w => `Les pages modifiées pèsent ${kb(w.before)} avant et ${kb(w.after)} après (${signedKb(w.after - w.before)}), miroirs non comptés.`,
    weightMost: "Le plus :",
    publishFailed: "La publication a échoué, rien n'est perdu, vous pouvez réessayer :",
    sourceMissing: "Source à vérifier", leftovers: n => `Valeurs retirées encore présentes, laissées telles quelles (${n})`,
    reviewFigures: ["éléments de veille", "touchent une page", "corrections proposées", "pistes d'ajout"],
    corrections: "Corrections",
    noNewPage: "Cette passe ajoute dans les pages existantes : elle n'écrit jamais de nouvelle page.",
    unchanged: n => `Pistes sans modification, et pourquoi (${n})`,
    pagesToWrite: n => n ? `${n} piste(s) demanderaient une page à elles. À toi de décider de les écrire :` : "Aucune de ses pistes n'en demandait une.",
    reviewHelp: "Coche ce qui doit être appliqué. Les corrections liées (une phrase et sa note, par exemple) forment un groupe : elles se cochent ensemble. Un groupe dont un membre ne peut pas s'appliquer est écarté en entier.",
    group: g => `Groupe ${g}`, groupLeftOut: " · écarté : un membre ne s'applique pas",
    noCorrection: "Aucune correction proposée.",
    leads: n => `Pistes d'ajout (${n}, non rédigées)`, none: "Aucune.", nothing: "Rien.",
    noticed: n => `Remarqué ailleurs dans le guide (${n})`,
    noticedHelp: "Pour les corriger : « Signaler une erreur », en copiant les lignes utiles.",
    excerptNow: "Le guide dit aujourd'hui",
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
    reportTitle: "Signaler une erreur ou proposer un sujet",
    reportKinds: { fix: "Une erreur à corriger", add: "Une idée ou une information à creuser" },
    ideaIntro: "Un sujet par ligne : ce que tu as vu, ou ce qui manque d'après toi, avec une adresse si tu en as une. L'agent vérifie chaque sujet sur des sources primaires, avec tout le guide en contexte, puis propose où l'écrire ; tu relis comme pour une veille. Rien avant : pas de recherche de pistes.",
    ideaCost: (base, each, deep) => `Compte ${base}, plus ${each} par sujet (${deep} par sujet creusé).`,
    ideaExample: "Ollama fait tourner des modèles de voix en local depuis octobre : https://ollama.com/blog/speech-models",
    ideaButton: "Vérifier et proposer des ajouts",
    ideaDeep: "Creuser chaque sujet : plusieurs sources, plus de recherches, un peu plus cher",
    ideaLimit: "Limite : la passe d'ajouts n'écrit jamais de nouvelle page. Elle signale celles qu'il faudrait.",
    perStep: { title: "Moteur et modèles de cette passe", change: "changer pour cette fois", once: "pour cette fois seulement", apply: "Appliquer",
      cancel: "annuler", edit: "modifier", reset: "revenir aux Réglages", engine: "Moteur", model: "Modèle", effortLabel: "Effort", modelOfRole: "modèle habituel de ce moteur",
      restUnbilled: "le reste non facturé",
      effort: e => ({ low: "effort faible", medium: "effort moyen", high: "effort élevé", xhigh: "effort très élevé", max: "effort maximal" })[e] || e,
      names: { fix: "Corrections", "fix-translation": "Corrections de traduction", compact: "Allègements", add: "Ajouts", crosscheck: "Relecture croisée", mirror: "Miroirs" },
      forced: e => `Le moteur de ce serveur est imposé (VAULT_WATCH_ENGINE=${e}) : il ne se change pas ici.` },
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
    nav: { watches: "Watches", sources: "Sources", check: "Check the guide", report: "Report or suggest", costs: "Costs" },
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
        stale: d => `nothing since<br>${d}` },
      staleNote: days => `A source that has published nothing for ${days} days is not proposed for removal: a tool that stopped moving is a fact about the guide's subject, the page that recommends it is what to look at.`,
      proposals: (n, open, later) => `Proposals: ${n} to decide${open ? `, ${open} in an open pull request` : ""}${later ? `, ${later} put off` : ""}`, noProposals: "No change to propose.",
      groups: { remove: "Remove", change: "Change", add: "Add: cited in the guide, followed by no source", advisories: "Add: security advisories of tools already followed for their releases" },
      why: {
        unreachable: p => `the source does not answer (${p.error})`, archived: () => "the repository is archived",
        moved: p => `the repository moved to ${p.new.repo}`, empty: () => "the source answers and lists nothing",
        noise: p => `${p.judged} items judged by the model over the period, ${p.kept} kept, no correction proposed`,
        "not-named": () => "no page of the guide names it any more",
        cited: p => `cited in ${p.pages} pages (${p.examples.join(", ")})`,
        "no-advisories": p => `followed for its releases (${p.of}), not for its advisories`,
      },
      recommended: "settled by a fact", applied: "in the PR", later: "put off", decideNow: "Decide now",
      putOff: n => `Put ${n} off until the next check`,
      putOffHelp: "Putting a proposal off takes it out of the list and changes nothing in the guide: the next check proposes it again if it still holds.",
      search: "Filter: name, repository, type…", scrollLeft: "See the columns on the left", scrollRight: "See the columns on the right",
      apply: (n, repo) => repo ? `Open a pull request with ${n} change(s)` : `Create a branch with ${n} change(s)`,
      appliedTo: (branch, pr) => pr ? `Pull request opened: ${pr}` : `Changes on the branch ${branch} (a guide without a repository: merge it by hand).`,
      all: n => `All (${n})`, filterHelp: "Click a state to see it alone (several can be chosen), a column title to sort.",
      shown: (n, total) => n === total ? `${total} sources` : `${n} source(s) shown out of ${total}`,
      sortBy: c => `Sort by « ${c} » (a second click reverses)`, defaultSort: "Default order",
      count: (n, label) => `${n} ${label}`,
    },
    menu: { site: "Site of the guide", repo: forge => `Repository on ${forge}`, chapters: "Chapters", code: "Agent code",
      open: "Links and chapters of the guide", older: "Show older ones", burger: "Menu" },
    chapters: {
      title: "Chapters",
      intro: "The agent works chapter by chapter in three places: the exploration of the web (one paid call per chapter), the check of the translations (one call per chapter) and the reading of the guide when it does not fit in the model's window. A chapter gathers the pages a reader would look up together and that the same news would change.",
      now: "1. The current split", sourceAuto: "automatic rule", sourceManifest: "declared in the guide's manifest",
      autoHelp: (big, small) => `For the pages no declared chapter takes, the automatic rule makes one chapter per top folder, splits a folder heavier than ${big} KB (by subfolder, else in slices of pages) and gathers those lighter than ${small} KB.`,
      cols: ["Chapter", "Pages", "Weight", "Explored by default", "From"],
      declared: "manifest", auto: "automatic", yes: "yes", no: "no", kb: n => `${n} KB`,
      change: "2. Prepare a new split",
      changeHelp: "Two ways, which combine: ask a model for a proposal then adjust it by hand, or write everything by hand. Nothing is saved before step 3.",
      askTitle: "Ask a model for a split",
      askWhat: "The model reads the outline of the guide (path, weight, title and headings of each page, not the text) and proposes chapters, with those not to explore by default (a glossary, the pages about the project). Nothing is written: you review and adjust below.",
      ask: c => `Propose a split · ${c}`, asking: "The model reads the outline of the guide…",
      asked: c => `Proposal received (${c}). Review it, adjust it, then save.`,
      byHand: "The chapters of the new split", fromNow: "Take the current split", add: "Add a chapter", remove: "Remove",
      name: "Name", paths: "Paths, one per line: a folder ending with /, a pattern with * or **, or a page", explore: "explored by default",
      pathsHelp: "A page goes to the first chapter that takes it. The pages no chapter takes follow the automatic rule.",
      result: "3. Check and save",
      resultHelp: "This table updates by itself after each change of step 2: it shows the chapters your split would give, with their weight. Nothing is written until you click the button below.",
      resultEmpty: "Add a chapter in step 2, or ask for a proposal, to see here what it gives.", updating: "Computing…",
      tips: {
        explore: "Ticked: this chapter is offered by default when you start the exploration of the web (one paid call per chapter). Unticked: it stays available, but you tick it yourself that day. Untick it for a glossary or pages about the project, where the web brings nothing new.",
        paths: "Examples: 02-hardware/ takes the whole folder; 03-stack/*.md the pages directly in that folder; **/faq.md every page named faq.md; 00-index.md one page.",
        origin: "« manifest »: a chapter you declared in the guide's manifest. « automatic »: a chapter the automatic rule made with the pages put nowhere.",
        fromNow: "Copies the chapters of the table of step 1 into step 2, to adjust them by hand instead of starting from nothing. Replaces what is being edited.",
        backAuto: "Removes every declared chapter from the manifest (through a pull request): the automatic rule then groups all the pages.",
      },
      save: forge => `Open the pull request on ${forge}`, saveLocal: "Create the branch",
      saveHelp: (manifest, base) => `The split is written to ${manifest}, on a branch of its own; it applies once merged into ${base}.`,
      needs: v => `Before you merge: a manifest that declares chapters needs the agent ${v} or newer wherever the guide is read, the workflow that collects its watch included. An older agent refuses the manifest.`,
      noManifest: "This guide has no manifest: the command vault-watch init writes one, and the chapters are declared there.",
      backAuto: "Back to the automatic rule",
      pending: "A pull request declares a split. It will apply once merged; until then nothing else can be saved.",
      saved: "Pull request opened. The split applies once it is merged.",
      savedLocal: (branch, base) => `Branch ${branch} created on this machine (a guide without a repository): merge it into ${base} to apply the split.`,
      toml: "Lines of the manifest (to paste them by hand)", copy: "Copy", copied: "Copied",
      empty: "No chapter declared: add one, start from the current split or ask for a proposal.",
      edit: "Change the chapters",
    },
    verif: {
      title: "Check the guide",
      intro: "A health check of the whole guide, on demand. The free checks run the guide's own scripts; the others have Claude read the guide. Results are leads: the ones you keep go to a fix run, which checks them on sources and goes through your review.",
      free: "free", tokens: n => `≈ ${n.toLocaleString("en")} tokens`, unknown: "depends on the result",
      needs: ids => `also runs: ${ids}`,
      start: c => `Run the check · ${c}`, history: "Previous checks",
      none: "No check yet.", running: "Running…", leads: n => `${n} lead(s)`,
      chapters: c => `Chapters to explore, one call per chapter ticked (each: ${c}):`,
      ideaLink: "You already have an idea or a precise piece of news? Have it checked and written straight away, without a search for leads.",
      dig: "dig deeper (several sources, more searches, a little more expensive)",
      leadsAdd: "A lead is a question to check, not a change: nothing is written yet. The framed passage is what the guide says today (highlighted: the sentence concerned; the lines around give the context). For each lead ticked, the addition run reads the sources, then proposes to correct what is out of date or to add what is missing, in every page concerned. You review these proposals before they apply.",
      onlyFree: "Only the free ones",
      waiting: "waiting", checking: "running…", ok: "all clear", problems: "to look at", failed: "could not run",
      notFixable: "Not fixable by a fix run yet (translations are fixed from the French side): to handle by hand or by a later feature.",
      seeDetails: "Details", dead: "Sources not answering", blocked: "Blocked by anti-bot protections (often fine in a browser)",
      claims: "Claims to re-check", pagesDue: "Pages due for review", log: "Log",
      createFix: (by, c, runs = {}) => {
        const kinds = [["fix", "fix", "≈ 6-8 $"], ["translation", "translation", "< 1 $"], ["compact", "compaction", runs.compact || "≈ 5-6 $"], ["add", "addition", runs.add || "≈ 15-25 $"]].filter(k => by[k[0]]);
        return kinds.length > 1 ? `Create ${kinds.length} runs: ${kinds.map(k => `${by[k[0]]} lead(s) as ${/^a/.test(k[1]) ? "an" : "a"} ${k[1]} run (${c(k[2], k[0])})`).join(", ")}`
          : `Create ${kinds[0]?.[0] === "add" ? "an" : "a"} ${(kinds[0] || [0, "fix"])[1]} run with ${kinds[0] ? by[kinds[0][0]] : 0} lead(s) · ${c((kinds[0] || [0, 0, "≈ 6-8 $"])[2], (kinds[0] || ["fix"])[0])}`;
      },
      heaviest: "Heaviest pages", flaggedFirst: "Flagged pages, then the heaviest", perChapter: "Per chapter",
      over: "over its ceiling", grew: "grew much", newPage: "new page",
      readonly: "read-only", notes: (n, w) => `${n} footnotes (${w})`, pagesWord: "page(s)",
      growth: g => `The guide weighed ${kb(g.bytes)} on ${g.date}: ${signedKb(g.added)} in ${g.days} days${g.new_pages ? `, ${g.new_pages} new page(s) among it` : ""}.`,
      tickAll: "Tick all", untickAll: "Untick all",
      cost: c => `Cost: ${c}`,
      counts: c => c.open + c.fix + c.dismissed === 0 ? "no lead"
        : `${c.open} to handle · ${c.fix} sent to a run · ${c.dismissed} dismissed`,
      toHandle: n => `${n} lead(s) to handle`, handled: "Handled", handle: "Handle",
      tickCard: n => `Tick / untick the ${n}`,
      toHandleTitle: "To handle", newCheck: "New check", fixRuns: "Runs started from this check",
      warning: n => `${n} lead(s) above are still to handle. A new check would find them again, twice: handle or dismiss them first.`,
      sent: "→ run", dismissed: "dismissed", reopen: "Reopen",
      unchecked: "not checked by the run", resend: "Put back to handle",
      context: "Each lead's call reads", contextGuide: "the whole guide", contextPages: "the lead's pages and the plan of the guide",
      contextTip: "The whole guide: the call sees every page. It is the safest and the most expensive, since the guide is read again at each round of search. The lead's pages and the plan: the call reads the pages the lead names or asks to read, and the list of every page with its headings; it edits these pages only. A lead that names no page reads the whole guide all the same. Either way, the cross-check then reads the whole guide and completes or corrects.",
      uncheckedAll: n => `${n} lead(s) sent were not checked by their run: nothing was searched or edited for them. Put them back to handle to send them again.`,
      resendAll: n => n > 1 ? `Put the ${n} back to handle` : "Put back to handle", dismiss: n => `Dismiss ${n} lead(s)`,
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
    usageLine: s => String(s || "").replace(" in (", " tokens in (").replace(" out, ", " tokens out, "),
    canClose: "You can close the page: the analysis goes on in the server, and the state is saved after each step.",
    progress: (min, cost) => `Started ${min} min ago · cost of this run ≈ ${cost}`,
    applyId: id => `Apply ${id}`,
    crossCheck: "Cross-check", from: "From", colon: ": ",
    byChapter: (t, b) => `Cross-check chapter by chapter: the guide (≈ ${t.toLocaleString("en")} tokens) exceeds what one call of the model can read (${b.toLocaleString("en")}). A contradiction between two chapters can be missed.`,
    lostValues: "No page states it any more", removedWhole: "(passage removed)",
    weight: w => `The pages changed weigh ${kb(w.before)} before and ${kb(w.after)} after (${signedKb(w.after - w.before)}), mirrors not counted.`,
    weightMost: "Most:",
    publishFailed: "The publication failed, nothing is lost, you can try again:",
    sourceMissing: "Source to check", leftovers: n => `Removed values still present, left as they are (${n})`,
    reviewFigures: ["watch items", "touch a page", "corrections proposed", "addition leads"],
    corrections: "Corrections",
    noNewPage: "This run adds to existing pages: it never writes a new page.",
    unchanged: n => `Leads without an edit, and why (${n})`,
    pagesToWrite: n => n ? `${n} lead(s) would need a page of their own. Writing them is your decision:` : "None of its leads asked for one.",
    reviewHelp: "Tick what should be applied. Related corrections (a sentence and its footnote, for instance) form a group and are ticked together. A group with a member that cannot apply is left out whole.",
    group: g => `Group ${g}`, groupLeftOut: " · left out: a member does not apply",
    noCorrection: "No correction proposed.",
    leads: n => `Addition leads (${n}, not drafted)`, none: "None.", nothing: "Nothing.",
    noticed: n => `Noticed elsewhere in the guide (${n})`,
    noticedHelp: "To fix them: « Report an error », with the relevant lines.",
    excerptNow: "The guide says today",
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
    reportTitle: "Report an error or suggest a subject",
    reportKinds: { fix: "An error to fix", add: "An idea or a piece of news to dig into" },
    ideaIntro: "One subject per line: what you saw, or what you think is missing, with an address if you have one. The agent checks each subject on primary sources, with the whole guide in context, then proposes where to write it; you review as for a watch. Nothing before: no search for leads.",
    ideaCost: (base, each, deep) => `Count ${base}, plus ${each} per subject (${deep} per subject dug deeper).`,
    ideaExample: "Ollama has run speech models locally since October: https://ollama.com/blog/speech-models",
    ideaButton: "Check and propose additions",
    ideaDeep: "Dig deeper into each subject: several sources, more searches, a little more expensive",
    ideaLimit: "Limit: the addition run never writes a new page. It says which ones would be needed.",
    perStep: { title: "Engine and models of this run", change: "change for this time", once: "for this time only", apply: "Apply",
      cancel: "cancel", edit: "change", reset: "back to the Settings", engine: "Engine", model: "Model", effortLabel: "Effort", modelOfRole: "this engine's usual model",
      restUnbilled: "the rest not billed",
      effort: e => ({ low: "low effort", medium: "medium effort", high: "high effort", xhigh: "very high effort", max: "maximum effort" })[e] || e,
      names: { fix: "Corrections", "fix-translation": "Translation fixes", compact: "Trims", add: "Additions", crosscheck: "Cross-check", mirror: "Mirrors" },
      forced: e => `The engine of this server is forced (VAULT_WATCH_ENGINE=${e}): it cannot be changed here.` },
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
for (const l of ["fr", "en"]) Object.assign(TEXTS[l], { settings: SETTINGS_TEXTS[l], theme: THEME_TEXTS[l], notify: NOTIFY_TEXTS[l], feedback: FEEDBACK_TEXTS[l] });
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
// What a paid action costs: its estimate on the API, nothing on Claude Code with a subscription (info.engine)
const onSubscription = () => info?.engine === "claude-code";
// What an action costs: the estimate (Claude API prices) on the API only; nothing on a subscription or a local model;
// another provider's prices are its own.
const cost = usd => onSubscription() ? T.subscription : info?.billing === "none" ? T.local
  : info?.engine && info.engine !== "api" ? T.provider : usd;

// --- What a run sets for its own steps: an engine, a model, an effort, for that run alone -----------------------
// The Settings give each step its engine, model and effort; a page that starts a run shows them and lets the reader
// change them for that run only (config.run_steps on the server). Forgotten when another screen is opened.
const OWN = {};      // {step: {engine, model, effort}}
let STEPS = null;    // how each step would run now, with OWN laid over the Settings (/api/steps)
let shownHash = "";  // the screen OWN belongs to
const MODE_STEP = { fix: "fix", translation: "fix-translation", compact: "compact", add: "add" };  // the step that proposes, per kind of run
const stepsQuery = () => Object.keys(OWN).length ? `?steps=${encodeURIComponent(JSON.stringify(OWN))}` : "";
const loadSteps = async () => { STEPS = await api(`/api/steps${stepsQuery()}`); };
const stepNow = step => STEPS?.steps.find(s => s.step === step);
const ownFor = steps => Object.fromEntries(Object.entries(OWN).filter(([step]) => steps.includes(step)));
// What an action costs with the engine of its step: its estimate on the Claude API only
const costOf = (step, usd) => {
  const s = stepNow(step);
  return !s ? cost(usd) : s.billing === "subscription" ? T.subscription : s.billing === "none" ? T.local : s.engine !== "api" ? T.provider : usd;
};
const billedStep = step => costOf(step, "$") === "$";
// One line per step: what runs it, and the fields to change it for this run
function stepLine(step, name = "") {
  const s = stepNow(step);
  if (!s) return "";
  return `<div class="step-line small" data-step-line="${step}">
    <span class="muted">${name ? `${esc(name)}${T.colon}` : ""}${esc(s.engine_label)} · ${esc(s.model || "?")} · ${T.perStep.effort(s.effort)}</span>
    ${OWN[step] ? `<span class="badge attention">${T.perStep.once}</span>` : ""}
    ${STEPS.forced ? "" : `<button type="button" class="small-button" data-step-edit="${step}" data-closed="${OWN[step] ? T.perStep.edit : T.perStep.change}">${OWN[step] ? T.perStep.edit : T.perStep.change}</button>`}
    ${OWN[step] && !STEPS.forced ? `<button type="button" class="small-button" data-step-reset="${step}">${T.perStep.reset}</button>` : ""}
    <span class="step-fields" data-step-fields="${step}" hidden>
      <select data-f="engine" aria-label="${T.perStep.engine}">${STEPS.engines.map(e => `<option value="${esc(e.name)}"${e.name === s.engine ? " selected" : ""}>${esc(e.label)}</option>`).join("")}</select>
      <input type="text" data-f="model" list="models-${step}" value="${esc(s.model)}" placeholder="${esc(T.perStep.modelOfRole)}" aria-label="${T.perStep.model}" spellcheck="false">
      <datalist id="models-${step}"></datalist>
      <select data-f="effort" aria-label="${T.perStep.effortLabel}">${STEPS.efforts.map(e => `<option value="${e}"${e === s.effort ? " selected" : ""}>${T.perStep.effort(e)}</option>`).join("")}</select>
      <button type="button" class="small-button" data-step-ok="${step}">${T.perStep.apply}</button>
    </span></div>`;
}
// The buttons of the lines above, inside `root`; `redraw` draws the screen again once a choice is made
function bindSteps(root, redraw) {
  const fields = step => root.querySelector(`[data-step-fields="${step}"]`);
  const models = async step => {  // the models the chosen engine offers, as suggestions: any id can be typed
    const f = fields(step), engine = f.querySelector("[data-f=engine]").value;
    const claude = engine === "api" || engine === "claude-code";
    const r = await api(`/api/models${claude ? "" : `?engine=${encodeURIComponent(engine)}`}`).catch(() => ({ models: [] }));
    f.querySelector("datalist").innerHTML = (r.models || []).map(m => `<option value="${esc(m.id)}">${esc(m.name || m.id)}</option>`).join("");
  };
  root.querySelectorAll("[data-step-edit]").forEach(b => b.onclick = () => {
    const f = fields(b.dataset.stepEdit);
    f.hidden = !f.hidden;
    b.textContent = f.hidden ? b.dataset.closed : T.perStep.cancel;  // the button says what it does now
    if (!f.hidden) models(b.dataset.stepEdit);
  });
  root.querySelectorAll("[data-step-fields]").forEach(f => f.querySelector("[data-f=engine]").onchange = () => {
    f.querySelector("[data-f=model]").value = "";  // another engine: its usual model, unless one is typed
    models(f.dataset.stepFields);
  });
  root.querySelectorAll("[data-step-ok]").forEach(b => b.onclick = async () => {
    const f = fields(b.dataset.stepOk), value = name => f.querySelector(`[data-f=${name}]`).value.trim();
    OWN[b.dataset.stepOk] = Object.fromEntries([["engine", value("engine")], ["model", value("model")], ["effort", value("effort")]].filter(([, v]) => v));
    await loadSteps();
    redraw();
  });
  root.querySelectorAll("[data-step-reset]").forEach(b => b.onclick = async () => {
    delete OWN[b.dataset.stepReset];
    await loadSteps();
    redraw();
  });
}
let CHECK_FORM = null;   // the boxes ticked on « Check the guide », kept while the form is drawn again
let REPORT_TEXT = "";    // what was typed on the report page, kept the same way
function header() {
  document.documentElement.lang = lang;
  document.querySelectorAll("nav [data-nav]").forEach(a => a.textContent = T.nav[a.dataset.nav]);
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
    lang = b.dataset.lang;
    T = TEXTS[lang];
    try { localStorage.setItem("vault-watch-lang", lang); } catch { /* private window: per page only */ }
    header();
    route();
  });
}

// The guide's menu closes when one of its links is followed, on a click elsewhere, and with Escape
document.addEventListener("click", e => {
  const menu = $("#guide-menu");
  if (menu.open && (!menu.contains(e.target) || e.target.closest("a"))) menu.open = false;
  if (e.target.closest("#header-menu a")) foldHeader();   // a page chosen in the folded menu: it closes
});
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  $("#guide-menu").open = false;
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
new ResizeObserver(fitHeader).observe($("header"));

// --- Router --------------------------------------------------------------------------------------
async function route() {
  if (source) { source.close(); source = null; }
  clearTimeout(followTimer);
  let h = location.hash.slice(1) || "/";
  if (h !== shownHash) {
    Object.keys(OWN).forEach(k => delete OWN[k]);
    shownHash = h;
    // « Chapters »: what was said there is said once; what is being edited stays, unless it was saved
    if (CH_EDIT) CH_EDIT = CH_EDIT.done ? null : { ...CH_EDIT, said: "" };
  }
  if (h === "/settings") {   // an address to open the Settings: the window, over the first page
    history.replaceState(null, "", "#/");
    h = "/";
    openSettings();
  }
  document.querySelectorAll("nav [data-nav]").forEach(a =>
    a.classList.toggle("active", h === "/" ? a.dataset.nav === "watches" : h === "/idea" ? a.dataset.nav === "report" : h.startsWith(`/${a.dataset.nav}`)));
  page.innerHTML = `<p class="muted">${T.loading}</p>`;
  try {
    if (h.startsWith("/run/")) await viewRun(decodeURIComponent(h.slice(5)));
    else if (h.startsWith("/check/")) await viewCheck(decodeURIComponent(h.slice(7)));
    else if (h === "/check") await viewChecks();
    else if (h === "/sources") await viewSources();
    else if (h === "/report" || h === "/idea") await viewReport(h === "/idea");
    else if (h === "/costs") await viewCosts();
    else if (h === "/chapters") await viewChapters();
    else await viewWatches();
  } catch (e) {
    page.innerHTML = `<p class="error-text">${esc(e.message)}</p>`;
  }
}
addEventListener("hashchange", route);

// --- Watches ---------------------------------------------------------------------------------------
let HOME = null;  // the last answer shown on the home page: drawn at once on the way back, then refreshed
let RUNS_SHOWN = 20, CHECKS_SHOWN = 20;  // the lists show the newest; « older ones » asks for more
async function viewWatches() {
  const load = () => Promise.all([api("/api/watches"), api(`/api/runs?limit=${RUNS_SHOWN + 1}`)]);  // one more: are there older ones?
  if (HOME) {
    drawWatches(...HOME);
    const shown = JSON.stringify(HOME), at = location.hash;
    load().then(fresh => {  // still on this page, and something moved: drawn again
      HOME = fresh;
      if (location.hash === at && JSON.stringify(fresh) !== shown) drawWatches(...fresh);
    }).catch(() => {});
    return;
  }
  HOME = await load();
  drawWatches(...HOME);
}

function drawWatches(watches, others) {
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
    ${others.length ? `<h2>${T.others}</h2>${others.slice(0, RUNS_SHOWN).map(r => `
      <div class="card row${FINISHED.includes(r.status) ? " finished" : ""}"><div class="grow"><b>${esc(r.thread)}</b>
        <div class="muted small">${esc(r.source)} · ${r.corrections} correction(s) · ${dollars(r.cost)}${
          r.pr_url ? ` · ${extLink(r.pr_url, "pull request")}` : ""}</div></div>
        ${badge(r.status)} <a href="#/run/${encodeURIComponent(r.thread)}"><button>${T.details}</button></a></div>`).join("")}
      ${others.length > RUNS_SHOWN ? `<p><button type="button" id="older">${T.menu.older}</button></p>` : ""}` : ""}`;
  if ($("#older")) $("#older").onclick = () => { RUNS_SHOWN += 40; HOME = null; viewWatches(); };
  const collect = $("#collect");
  if (collect) collect.onclick = async () => {
    collect.disabled = true;
    collect.textContent = T.collecting;
    try { await api("/api/collect", {}); HOME = null; await viewWatches(); }
    catch (e) { collect.disabled = false; collect.textContent = T.collectNow; collect.insertAdjacentHTML("afterend", ` <span class="error-text">${esc(e.message)}</span>`); }
  };
  page.querySelectorAll("[data-analyse]").forEach(b => b.onclick = async () => {
    b.disabled = true;
    const { thread } = await api("/api/analyses", b.dataset.kind === "issue" ? { issue: Number(b.dataset.analyse) } : { watch: b.dataset.analyse });
    location.hash = `/run/${encodeURIComponent(thread)}`;
  });
}

// --- The chapters of the guide: seen, proposed by a model, edited by hand, declared in the manifest ---------
// A help bubble: a « ? » that says what the thing beside it is, on hover, on keyboard focus and on a tap
// What each call of an addition run reads: the whole guide, or its lead's pages and the plan (the reader's choice,
// kept in this browser). A lead that names no page (« [Missing] no page yet: … ») reads the guide either way.
let ADD_CONTEXT = "pages";
try { if (localStorage.getItem("vault-watch-add-context") === "guide") ADD_CONTEXT = "guide"; } catch { /* private window */ }
const NO_PAGE = /^\[[^\]]+\] no page yet:/;
const tip = text => `<button type="button" class="tip" data-tip="${esc(text)}" aria-label="${esc(text)}">?</button>`;
// The bubble stays inside the window: its width and its place follow where the « ? » is
const placeTip = e => {
  const t = e.target instanceof Element ? e.target.closest(".tip") : null;
  if (!t) return;
  const zoom = window.textZoom?.get() || 1, room = window.innerWidth / zoom, width = Math.min(360, room - 32);
  const left = t.getBoundingClientRect().left / zoom;
  t.style.setProperty("--tip-width", `${width}px`);
  t.style.setProperty("--tip-left", `${-8 - Math.max(0, left - 8 + width - (room - 16))}px`);
  t.classList.toggle("below", t.getBoundingClientRect().top / zoom < 170);
};
document.addEventListener("pointerover", placeTip);
document.addEventListener("focusin", placeTip);

let CH_EDIT = null;   // what is being edited: {rows: [{name, paths, explore}], why: {name: reason}, result, error, said, done}
let chaptersTimer = 0;
async function viewChapters() {
  await loadSteps();
  const d = await api(`/api/chapters${stepsQuery()}`), C = T.chapters;
  if (!CH_EDIT) CH_EDIT = { rows: d.chapters.filter(c => c.declared).map(c => ({ name: c.name, paths: c.paths, explore: c.explore })), why: {} };
  const E = CH_EDIT;
  const table = (rows, why) => `<div class="scroll-x"><table class="chapters"><thead><tr>${C.cols.map((c, i) => `<th${i === 1 || i === 2 ? ' class="num"' : ""}>${c}${i === 3 ? tip(C.tips.explore) : i === 4 ? tip(C.tips.origin) : ""}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>
      <td><b>${esc(r.name)}</b><div class="muted small">${esc(r.first)}${r.pages > 1 ? ` … ${esc(r.last)}` : ""}</div>${why?.[r.name] ? `<div class="small">${esc(why[r.name])}</div>` : ""}</td>
      <td class="num">${r.pages}</td><td class="num">${C.kb(Math.round(r.kb))}</td>
      <td>${r.explore ? C.yes : `<b>${C.no}</b>`}</td><td class="muted">${r.declared ? C.declared : C.auto}</td></tr>`).join("")}</tbody></table></div>`;
  const notes = list => list.length ? `<ul class="attention-text small">${list.map(n => `<li>${esc(n)}</li>`).join("")}</ul>` : "";
  const pending = d.pending?.pr_url;
  const canSave = d.from_manifest && !pending;
  page.innerHTML = `
    <h1>${C.title}</h1>
    <p class="subtitle">${C.intro}</p>
    ${pending ? `<p class="banner">${C.pending} ${extLink(d.pending.pr_url, "pull request ↗")}</p>` : ""}
    ${E.said ? `<p class="banner">${E.said}</p>` : ""}
    <h2>${C.now} <span class="badge neutral">${d.source === "manifest" ? C.sourceManifest : C.sourceAuto}</span></h2>
    <div class="card">${table(d.chapters)}${notes(d.notes)}<p class="muted small">${C.autoHelp(d.big_kb, d.small_kb)}</p></div>
    <h2>${C.change}</h2>
    <p class="muted">${C.changeHelp}</p>
    <div class="card check-card"><div class="option-text">
        <div class="header"><b>${C.askTitle}</b> <span class="badge attention">${costOf("chapters", `≈ ${dollars(d.usd)}`)}</span></div>
        <p class="muted small">${C.askWhat}</p>
        <p><button id="ask">${C.ask(costOf("chapters", `≈ ${dollars(d.usd)}`))}</button> <span class="error-text small" id="ask-error"></span></p>
      </div><div class="card-foot">${stepLine("chapters")}</div></div>
    <h3>${C.byHand}</h3>
    <p class="muted small">${C.pathsHelp}</p>
    <div id="rows">${E.rows.map((r, i) => `<div class="card chapter-row" data-row="${i}">
      <div class="chapter-fields">
        <label class="small">${C.name}<input type="text" data-f="name" value="${esc(r.name)}" maxlength="80"></label>
        <label class="small"><span>${C.paths}${tip(C.tips.paths)}</span><textarea data-f="paths" rows="${Math.min(8, Math.max(2, r.paths.length))}" spellcheck="false">${esc(r.paths.join("\n"))}</textarea></label>
      </div>
      ${E.why[r.name] ? `<p class="muted small">${esc(E.why[r.name])}</p>` : ""}
      <div class="actions"><label class="small"><input type="checkbox" data-f="explore" ${r.explore ? "checked" : ""}> ${C.explore}</label>${tip(C.tips.explore)}
        <span class="spacer"></span><button type="button" class="small-button danger" data-remove="${i}">${C.remove}</button></div>
    </div>`).join("") || `<p class="muted">${C.empty}</p>`}</div>
    <p class="actions"><button type="button" id="add-row">${C.add}</button>
      <span><button type="button" id="from-now">${C.fromNow}</button>${tip(C.tips.fromNow)}</span></p>
    <h2>${C.result}</h2>
    <p class="muted">${C.resultHelp}</p>
    <div id="result"></div>
    ${d.source === "manifest" ? `<p><button type="button" class="small-button" id="back-auto"${canSave ? "" : " disabled"}>${C.backAuto}</button>${tip(C.tips.backAuto)}</p>` : ""}`;
  const read = () => [...page.querySelectorAll("[data-row]")].map(row => ({
    name: row.querySelector("[data-f=name]").value.trim(),
    paths: row.querySelector("[data-f=paths]").value.split("\n").map(p => p.trim()).filter(Boolean),
    explore: row.querySelector("[data-f=explore]").checked }));
  const keep = () => { E.rows = read(); };
  const failed = (where, e) => { $(where).textContent = e.message; };
  // Step 3 is drawn by itself: what the chapters of step 2 would give, then the button that saves it
  const drawResult = busy => {
    const r = E.result;
    $("#result").innerHTML = !E.rows.length ? `<p class="muted">${C.resultEmpty}</p>`
      : E.error ? `<p class="error-text" role="status">${esc(E.error)}</p>`
      : !r ? `<p class="muted" role="status">${C.updating}</p>`
      : `<div class="card${busy ? " updating" : ""}">${table(r.chapters, E.why)}${notes(r.notes)}
        <details><summary class="small">${C.toml}</summary><pre class="toml">${esc(r.toml)}</pre>
          <button type="button" class="small-button" id="copy-toml">${C.copy}</button></details></div>
      <p class="muted small">${d.from_manifest ? C.saveHelp(d.manifest, d.base) : C.noManifest}</p>
      ${d.from_manifest ? `<p class="small attention-text">${C.needs(d.needs)}</p>` : ""}
      <p><button type="button" class="primary" id="save"${canSave && !busy ? "" : " disabled"}>${d.has_repo ? C.save(d.forge) : C.saveLocal}</button>
        <span class="error-text small" id="save-error"></span></p>`;
    if ($("#save")) $("#save").onclick = () => save(E.rows, $("#save"));
    if ($("#copy-toml")) $("#copy-toml").onclick = async () => {
      try { await navigator.clipboard.writeText(E.result.toml); $("#copy-toml").textContent = C.copied; } catch { /* no clipboard: the text is selectable */ }
    };
  };
  const compute = async () => {   // asked again after each change; an answer that comes after a newer change is dropped
    const rows = E.rows, asked = JSON.stringify(rows);
    if (!rows.length) { E.result = null; E.error = ""; drawResult(); return; }
    try {
      const result = await api("/api/chapters/preview", { chapters: rows });
      if (JSON.stringify(E.rows) !== asked) return;
      E.result = result; E.error = "";
    } catch (e) {
      if (JSON.stringify(E.rows) !== asked) return;
      E.result = null; E.error = e.message;
    }
    if (location.hash === "#/chapters") drawResult();
  };
  const changed = () => {   // typed: the result follows, half a second after the last key
    keep();
    drawResult(true);
    clearTimeout(chaptersTimer);
    chaptersTimer = setTimeout(compute, 500);
  };
  $("#rows").oninput = changed;
  $("#add-row").onclick = () => { keep(); E.rows.push({ name: "", paths: [], explore: true }); E.result = null; viewChapters(); };
  $("#from-now").onclick = () => { CH_EDIT = { rows: d.chapters.map(c => ({ name: c.name, paths: c.cover, explore: c.explore })), why: {} }; viewChapters(); };
  page.querySelectorAll("[data-remove]").forEach(b => b.onclick = () => { keep(); E.rows.splice(Number(b.dataset.remove), 1); E.result = null; viewChapters(); });
  $("#ask").onclick = async () => {
    const b = $("#ask");
    b.disabled = true;
    b.textContent = C.asking;
    try {
      const p = await api("/api/chapters/propose", { steps: ownFor(["chapters"]) });
      CH_EDIT = { rows: p.chapters.filter(c => c.declared).map(c => ({ name: c.name, paths: c.paths, explore: c.explore })), why: p.why, result: p,
                  said: C.asked(costOf("chapters", dollars(p.cost))) };
      viewChapters();
    } catch (e) { b.disabled = false; b.textContent = C.ask(costOf("chapters", `≈ ${dollars(d.usd)}`)); failed("#ask-error", e); }
  };
  const save = async (chapters, button) => {
    button.disabled = true;
    try {
      const done = await api("/api/chapters", { chapters });
      CH_EDIT = { rows: chapters, why: {}, done: true, said: done.pr_url ? `${C.saved} ${extLink(done.pr_url, "pull request ↗")}` : esc(C.savedLocal(done.branch, done.base)) };
      viewChapters();
    } catch (e) { button.disabled = false; ($("#save-error") || $("#ask-error")).textContent = e.message; }
  };
  if ($("#back-auto")) $("#back-auto").onclick = () => save([], $("#back-auto"));
  bindSteps(page, () => { keep(); viewChapters(); });
  drawResult();
  if (E.rows.length && !E.result && !E.error) compute();
}

// --- One run ---------------------------------------------------------------------------------------
async function viewRun(thread) {
  const r = await api(`/api/runs/${encodeURIComponent(thread)}`);
  const title = `<h1>${esc(r.source || thread)} ${badge(r.status)}</h1>
    <p class="subtitle">${r.as_of ? `${T.watchUpTo(r.as_of)} · ` : ""}${esc(T.usageLine(r.usage))}</p>`;
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
    : `<div class="excerpt"><div class="muted small">${T.excerptNow} · <code>${esc(e.page)}:${e.line}</code>${e.match === "approx" ? ` · ${T.excerptApprox}` : ""}</div>
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
    ${r.mode === "add" ? `<div class="card notice"><p><strong>${T.noNewPage}</strong> ${T.pagesToWrite(r.pages_to_write.length)}</p>
      ${r.pages_to_write.length ? `<ul>${r.pages_to_write.map(p => `<li><strong>${esc(p.id)}</strong> ${esc(p.what)}<br><span class="muted small">${esc(p.lead)}</span></li>`).join("")}</ul>` : ""}</div>
    ${r.unchanged.length ? `<details><summary>${T.unchanged(r.unchanged.length)}</summary>
      <ul>${r.unchanged.map(u => `<li><strong>${esc(u.id)}</strong> ${esc(u.why)}<br><span class="muted small">${esc(u.lead)}</span></li>`).join("")}</ul></details>` : ""}` : ""}
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
      ${r.error ? `<p class="error-text"><b>${T.publishFailed}</b> ${esc(r.error)}</p>` : ""}
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
  await loadSteps();
  const kept = CHECK_FORM;  // drawn again after a step was changed for this verification: the boxes stay as they were
  CHECK_FORM = null;
  const [options, listed] = await Promise.all([api(`/api/verifications/options${stepsQuery()}`), api(`/api/verifications?limit=${CHECKS_SHOWN + 1}`)]);
  const verifs = listed.slice(0, CHECKS_SHOWN);
  const V = T.verif, titles = Object.fromEntries(options.map(o => [o.id, o.title[lang]]));
  // An estimate says where its price comes from when it is not a price set or fetched by the user (a default, none)
  const price = o => o.model ? costOf(o.id, o.usd == null ? V.unknown : `≈ ${dollars(o.usd)}`) : V.free;
  const origin = o => o.model && o.price_origin && o.usd != null && billedStep(o.id)
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
    <p class="small"><a href="#/idea">${V.ideaLink}</a></p>
    ${pending.length ? `<h2>${V.toHandleTitle}</h2>${pending.map(checkCard).join("")}` : ""}
    <details class="new-check"${pending.length ? "" : " open"}><summary><h2>${V.newCheck}</h2></summary>
    ${remaining ? `<p class="attention-text">${V.warning(remaining)}</p>` : ""}
    <p class="tick-row"><button type="button" class="small-button" data-tick-checks="all">${V.tickAll}</button>
      <button type="button" class="small-button" data-tick-checks="none">${V.untickAll}</button>
      <button type="button" class="small-button" data-tick-checks="free">${V.onlyFree}</button></p>
    ${options.map(o => `<div class="card check-card"><label class="option">
      <input type="checkbox" data-check="${o.id}" ${(kept ? kept.checks.has(o.id) : !o.model) ? "checked" : ""}>
      <div>
        <div class="header"><b>${esc(o.title[lang])}</b>
          <span class="badge ${o.model ? "attention" : "ok"}">${price(o)}</span>${origin(o)}
          ${o.tokens ? `<span class="muted small">${V.tokens(o.tokens)}</span>` : ""}</div>
        <p class="muted small">${esc(o.what[lang])}</p>
        ${o.limit ? `<p class="small attention-text">${esc(o.limit[lang])}</p>` : ""}
        <p class="muted small">${esc(o.note[lang])}${o.needs.length ? ` · ${V.needs(o.needs.map(n => titles[n]).join(", "))}` : ""}</p>
      </div></label>${o.model ? `<div class="card-foot">${stepLine(o.id)}</div>` : ""}${o.chapters ? `<div class="card-foot chapters" data-chapters-of="${o.id}" hidden>
        <p class="muted small">${V.chapters(costOf(o.id, `≈ ${dollars(o.usd_chapter || 0)}`))}</p>
        ${o.chapters.map(c => `<label><input type="checkbox" data-chapter="${esc(c.id)}" ${(kept ? kept.chapters.has(c.id) : c.explore) ? "checked" : ""}> ${esc(c.id)} <span class="muted small">(${c.pages} p., ${T.chapters.kb(Math.round(c.kb))})</span></label>`).join("")}
        <p class="small"><a href="#/chapters">${T.chapters.edit}</a></p>
      </div>` : ""}</div>`).join("")}
    <p><button class="primary" id="start"></button></p>
    </details>
    <h2>${V.history}</h2>
    ${older.map(checkCard).join("") || `<p class="muted">${V.none}</p>`}
    ${listed.length > CHECKS_SHOWN ? `<p><button type="button" id="older">${T.menu.older}</button></p>` : ""}`;
  if ($("#older")) $("#older").onclick = () => { CHECKS_SHOWN += 40; viewChecks(); };
  const boxes = [...page.querySelectorAll("[data-check]")];
  const total = () => {
    const ids = new Set(boxes.filter(c => c.checked).map(c => c.dataset.check));
    options.filter(o => ids.has(o.id)).forEach(o => o.needs.forEach(n => ids.add(n)));
    // A check with chapters (the exploration) shows them when it is ticked, and costs one call per chapter ticked
    page.querySelectorAll("[data-chapters-of]").forEach(d => { d.hidden = !ids.has(d.dataset.chaptersOf); });
    const chosen = options.filter(o => ids.has(o.id)), paid = chosen.filter(o => o.model), billed = paid.filter(o => billedStep(o.id));
    const usd = billed.reduce((s, o) => s + (o.usd || 0) + (o.chapters ? (o.usd_chapter || 0) * chapters().length : 0), 0);
    // Scripts only: free. Every model check on a subscription or a local model: said. Else what the billed ones cost.
    $("#start").textContent = V.start(!paid.length ? V.free : !billed.length ? costOf(paid[0].id, "")
      : `≈ ${dollars(usd)}${billed.length < paid.length ? ` + ${T.perStep.restUnbilled}` : ""}`);
    $("#start").disabled = ids.size === 0 || chosen.some(o => o.chapters && !chapters().length);
  };
  const chapters = () => [...page.querySelectorAll("[data-chapter]")].filter(c => c.checked).map(c => c.dataset.chapter);
  boxes.forEach(c => c.onchange = total);
  // All the checks, none, or the free ones (the default: those that call no model)
  const isFree = new Set(options.filter(o => !o.model).map(o => o.id));
  page.querySelectorAll("[data-tick-checks]").forEach(b => b.onclick = () => {
    const which = b.dataset.tickChecks;
    boxes.forEach(c => { c.checked = which === "all" || (which === "free" && isFree.has(c.dataset.check)); });
    total();
  });
  page.querySelectorAll("[data-chapter]").forEach(c => c.onchange = total);
  bindSteps(page, () => {
    CHECK_FORM = { checks: new Set(boxes.filter(c => c.checked).map(c => c.dataset.check)), chapters: new Set(chapters()) };
    viewChecks();
  });
  total();
  $("#start").onclick = async () => {
    $("#start").disabled = true;
    const checks = boxes.filter(c => c.checked).map(c => c.dataset.check);
    const { id } = await api("/api/verifications", { checks, steps: ownFor(checks), ...(checks.includes("explore") ? { chapters: chapters() } : {}) });
    location.hash = `/check/${encodeURIComponent(id)}`;
  };
}

async function viewCheck(id) {
  clearTimeout(followTimer);
  await loadSteps();
  const [v, options] = await Promise.all([api(`/api/verifications/${encodeURIComponent(id)}`), api(`/api/verifications/options${stepsQuery()}`)]);
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
      const stuck = (r?.findings || []).filter(f => v.unchecked?.[f] && v.handled[f]?.status === "fix");  // sent, not checked
      const finished = r && !r.open && !stuck.length && !r.summary?.startsWith("could not run") && (r.ok || r.findings?.length);
      const isOpen = FOLDS[`${id}/${c}`] ?? !finished;
      return `<details class="card foldable" data-fold="${id}/${c}"${isOpen ? " open" : ""}><summary class="header"><b>${esc(titles[c] || c)}</b>${stateBadge}${r?.open ? ` <button class="small-button" data-tick-card="${c}">${V.tickCard(r.open)}</button>` : ""}</summary>
        ${r ? `<p class="muted small">${esc(r.summary)}</p>
          ${list(V.dead, (r.dead || []).map(d => `${extLink(d.url, esc(d.url))} — ${esc(d.status)} ${esc(d.code ?? "")} (${esc(d.pages.join(", "))})`))}
          ${list(V.blocked, (r.blocked || []).map(d => `${extLink(d.url, esc(d.url))} (${esc(d.pages.join(", "))})`))}
          ${list(V.claims, (r.claims || []).map(x => `${esc(x.recheckBy)} <code>${esc(x.page)}</code> : ${esc(x.claim)}`))}
          ${list(V.pagesDue, (r.pages_due || []).map(esc))}
          ${r.sizes ? sizesBlock(r.sizes) : ""}
          ${r.log ? `<details><summary>${V.log}</summary><pre>${esc(r.log)}</pre></details>` : ""}
          ${(r.findings || []).length ? `${r.fixable ? "" : `<p class="muted small">${V.notFixable}</p>`}${r.mode === "add" ? `<p class="muted small">${V.leadsAdd}</p>` : ""}${stuck.length ? `<div class="unchecked-all" role="status"><span>${V.uncheckedAll(stuck.length)}</span>
            <button type="button" class="primary" data-reopen-card="${c}">${V.resendAll(stuck.length)}</button></div>` : ""}<ul class="leads">${r.findings.map((f, i) => lead(f, r.fixable, c, r.mode, i + 1, r.excerpts?.[f])).join("")}</ul>` : ""}` : ""}
      </details>`;
    }).join("")}
    <div class="bar">
      <details class="run-steps" id="run-steps-box" hidden><summary>${T.perStep.title}</summary><div id="run-steps"></div></details>
      <label class="add-context small" id="add-context-box" hidden>${V.context}
        <select id="add-context"><option value="pages">${V.contextPages}</option><option value="guide">${V.contextGuide}</option></select>${tip(V.contextTip)}</label>
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
        ${run.status ? badge(run.status) : ""}${run.pr_url ? ` ${extLink(run.pr_url, "PR")}` : ""} · ${esc(f)}${
        v.unchecked?.[f] ? `<div class="unchecked"><span class="badge attention">${V.unchecked}</span>
          <span class="small">${esc(v.unchecked[f])}</span> <button type="button" class="primary" data-reopen="${esc(f)}">${V.resend}</button></div>` : ""}</li>`;
    }
    if (h?.status === "dismissed") return `<li class="handled">${num} <span class="badge neutral">${V.dismissed}</span> <button class="small-button" data-reopen="${esc(f)}">${V.reopen}</button> ${esc(f)}</li>`;
    return `<li><label><input type="checkbox" data-lead="${esc(f)}" data-fixable="${fixable}" data-mode="${mode}" data-card="${card}"> ${num} <span>${esc(f)}</span></label>${
      mode === "add" ? `<label class="dig muted small"><input type="checkbox" data-deep="${esc(f)}"> ${V.dig}</label>` : ""}${excerpts(passages)}</li>`;
  }
  const boxes = [...page.querySelectorAll("[data-lead]")];
  const ticked = () => boxes.filter(c => c.checked);
  $("#add-context").value = ADD_CONTEXT;
  $("#add-context").onchange = e => {
    ADD_CONTEXT = e.target.value;
    try { localStorage.setItem("vault-watch-add-context", ADD_CONTEXT); } catch { /* private window: per page only */ }
    count();
  };
  const count = () => {
    const ok = ticked().filter(c => c.dataset.fixable === "true"), n = ok.length, e = ticked().length;
    const by = {};
    ok.forEach(c => { by[c.dataset.mode] = (by[c.dataset.mode] || 0) + 1; });
    // A compaction run, an addition run: what it costs whatever its leads, plus a share per lead, priced with the
    // models of the Settings (the check that gives the leads carries the estimate of the run they go to)
    // A lead dug deeper has a call of its own instead of a share of one
    const dug = ok.filter(c => c.dataset.mode === "add" && deep().has(c.dataset.lead)).length;
    const runOf = (check, leads, deeper = 0) => {
      const o = options.find(o => o.id === check) || {};
      return o.run_usd ? `≈ ${dollars(o.run_usd + (o.run_usd_each || 0) * (leads - deeper) + (o.run_usd_deep || 0) * deeper)}` : "";
    };
    // An addition run whose calls read their lead's pages and the plan: priced so, except the leads that name no
    // page, which read the whole guide (the first of them writes it to the cache: the difference of the two bases)
    const adds = ok.filter(c => c.dataset.mode === "add").map(c => c.dataset.lead);
    $("#add-context-box").hidden = !adds.length;
    const addCost = () => {
      const o = options.find(o => o.id === "news") || {};
      if (ADD_CONTEXT !== "pages" || !o.run_usd_pages) return runOf("news", adds.length, dug);
      const each = f => NO_PAGE.test(f) ? (deep().has(f) ? o.run_usd_deep : o.run_usd_each) : (deep().has(f) ? o.run_usd_deep_pages : o.run_usd_each_pages);
      return `≈ ${dollars(o.run_usd_pages + (adds.some(f => NO_PAGE.test(f)) ? o.run_usd - o.run_usd_pages : 0) + adds.reduce((s, f) => s + (each(f) || 0), 0))}`;
    };
    $("#fix").textContent = V.createFix(by, (usd, mode) => costOf(MODE_STEP[mode] || "fix", usd),
      { compact: runOf("compaction", by.compact || 0), add: addCost() });
    // The steps of the run(s) these leads go to: what runs each, changeable for this time
    const kinds = Object.keys(by);
    const wanted = [...kinds.map(k => MODE_STEP[k]), ...(kinds.some(k => k !== "translation") ? ["crosscheck"] : []), ...(kinds.length ? ["mirror"] : [])];
    $("#run-steps-box").hidden = !wanted.length;
    $("#run-steps").innerHTML = (STEPS.forced ? `<p class="muted small">${T.perStep.forced(STEPS.forced)}</p>` : "")
      + wanted.map(s => stepLine(s, T.perStep.names[s])).join("");
    bindSteps($("#run-steps"), count);
    $("#fix").disabled = n === 0 || v.running;
    $("#dismiss").textContent = V.dismiss(e); $("#dismiss").disabled = e === 0 || v.running;
  };
  boxes.forEach(c => c.onchange = count);
  // « Dig deeper » on a lead: it is then kept too
  const digs = [...page.querySelectorAll("[data-deep]")];
  const deep = () => new Set(digs.filter(d => d.checked).map(d => d.dataset.deep));
  digs.forEach(d => d.onchange = () => {
    if (d.checked) boxes.filter(c => c.dataset.lead === d.dataset.deep).forEach(c => c.checked = true);
    count();
  });
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
  page.querySelectorAll("[data-reopen-card]").forEach(b => b.onclick = () => leads(
    (v.results[b.dataset.reopenCard].findings || []).filter(f => v.unchecked?.[f] && v.handled[f]?.status === "fix"), "open"));
  if (!boxes.length) page.querySelector(".bar").remove();
  else {
    $("#dismiss").onclick = () => leads(ticked().map(c => c.dataset.lead), "dismissed");
    $("#fix").onclick = async () => {
      $("#fix").disabled = true;
      // One run per mode: content fixes, translation fixes, trims and additions do not take the same path
      const threads = [];
      for (const mode of ["fix", "translation", "compact", "add"]) {
        const text = ticked().filter(c => c.dataset.fixable === "true" && c.dataset.mode === mode).map(c => c.dataset.lead).join("\n");
        const dig = mode === "add" ? { deep: text.split("\n").filter(f => deep().has(f)), context: ADD_CONTEXT } : {};
        const steps = ownFor([MODE_STEP[mode], "crosscheck", "mirror"]);
        if (text) threads.push((await api("/api/fix", { text, verification: id, mode, steps, ...dig })).thread);
      }
      location.hash = `/run/${encodeURIComponent(threads[0])}`;
    };
  }
  if (v.running) followTimer = setTimeout(() => viewCheck(id).catch(() => {}), 3000);
}

// The size check: what the guide gained, its heaviest pages (those over their budget first), the weight per chapter
function sizesBlock(s) {
  const V = T.verif;
  // The size now, then what the page gained since the earlier commit (bytes and share of what it weighed)
  const share = p => p.before ? `, ${p.bytes >= p.before ? "+" : "−"}${Math.round(Math.abs(p.bytes - p.before) * 100 / p.before)} %` : "";
  const grew = p => !("before" in p) ? "" : p.before == null ? ` · ${V.newPage}` : p.bytes !== p.before ? ` · ${signedKb(p.bytes - p.before)}${share(p)}` : "";
  const row = p => `<li><code>${esc(p.page)}</code> — <b>${kb(p.bytes)}</b>${p.budget ? ` / ${kb(p.budget * 1024)}` : ""}${grew(p)}${p.readonly ? ` · ${V.readonly}` : ""}${
    p.over ? ` <span class="badge attention">${V.over}</span>` : ""}${p.grew ? ` <span class="badge attention">${V.grew}</span>` : ""}
    <div class="muted small">${[...p.sections.map(x => `${esc(x.title)} ${kb(x.bytes)}`),
      ...(p.footnotes.count ? [V.notes(p.footnotes.count, kb(p.footnotes.bytes))] : [])].join(" · ")}</div></li>`;
  return `${s.growth ? `<p class="small">${V.growth(s.growth)}</p>` : ""}
    <details${s.over || s.grew ? " open" : ""}><summary>${s.over || s.grew ? V.flaggedFirst : V.heaviest} (${s.heaviest.length})</summary><ul>${s.heaviest.map(row).join("")}</ul></details>
    <details><summary>${V.perChapter} (${s.chapters.length})</summary><ul>${s.chapters.map(c =>
      `<li><code>${esc(c.chapter)}</code> — ${kb(c.bytes)}, ${c.pages} ${V.pagesWord}</li>`).join("")}</ul></details>`;
}

const FOLDS = {};  // check cards folded or opened by the reader, by verification/check, kept across refreshes

// --- Report errors -----------------------------------------------------------------------------------
async function viewReport(idea = false) {
  await loadSteps();
  const kind = idea ? "add" : "fix", wanted = [MODE_STEP[kind], "crosscheck", "mirror"];
  // What the run costs: said for the engine of the step that proposes (an addition run: from the estimate of its check)
  const news = idea ? (await api(`/api/verifications/options${stepsQuery()}`)).find(o => o.id === "news") || {} : {};
  const price = !billedStep(MODE_STEP[kind]) ? (stepNow(MODE_STEP[kind])?.billing === "subscription" ? T.reportSubscription : costOf(MODE_STEP[kind], ""))
    : idea ? T.ideaCost(`≈ ${dollars(news.run_usd)}`, `≈ ${dollars(news.run_usd_each)}`, `≈ ${dollars(news.run_usd_deep)}`) : T.reportCost;
  page.innerHTML = `
    <h1>${T.reportTitle}</h1>
    <p class="tabs"><a href="#/report"${idea ? "" : ' class="active"'}>${T.reportKinds.fix}</a><a href="#/idea"${idea ? ' class="active"' : ""}>${T.reportKinds.add}</a></p>
    <p class="subtitle">${idea ? T.ideaIntro : T.reportIntro} ${price}</p>
    ${idea ? `<p class="small attention-text">${T.ideaLimit}</p>` : ""}
    <textarea id="text" placeholder="${esc(idea ? T.ideaExample : T.reportExample)}">${esc(REPORT_TEXT)}</textarea>
    ${idea ? `<p><label class="small"><input type="checkbox" id="deep"> ${T.ideaDeep}</label></p>` : ""}
    <details class="run-steps"${Object.keys(ownFor(wanted)).length ? " open" : ""}><summary>${T.perStep.title}</summary>
      ${STEPS.forced ? `<p class="muted small">${T.perStep.forced(STEPS.forced)}</p>` : ""}${wanted.map(s => stepLine(s, T.perStep.names[s])).join("")}</details>
    <p><button class="primary" id="send">${idea ? T.ideaButton : T.reportButton}</button></p>`;
  bindSteps(page, () => { REPORT_TEXT = $("#text").value; viewReport(idea); });
  $("#send").onclick = async () => {
    const text = $("#text").value.trim();
    if (!text) return;
    $("#send").disabled = true;
    const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
    const { thread } = await api("/api/fix", { text, mode: kind, steps: ownFor(wanted), ...(idea && $("#deep").checked ? { deep: lines } : {}) });
    REPORT_TEXT = "";
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
const SOURCES_VIEW = { sort: "", dir: 1, states: new Set(), query: "" };

// A table wider than its card: `html` in a frame that scrolls sideways and says so (a shade on the side that
// hides columns, an arrow that stays in the window while the table is there). `wideTables` wires the frames of a page.
const chevron = points => `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const wideTable = (html, left, right) => `<div class="card wide"><div class="scroll-x">${html}</div>
  <div class="scroll-arrows"><button type="button" data-scroll="-1" title="${esc(left)}" aria-label="${esc(left)}">${chevron("15,5 8,12 15,19")}</button>
  <button type="button" data-scroll="1" title="${esc(right)}" aria-label="${esc(right)}">${chevron("9,5 16,12 9,19")}</button></div></div>`;
function wideTables(root) {
  root.querySelectorAll(".card.wide").forEach(card => {
    const box = card.querySelector(".scroll-x");
    if (!box) return;
    const mark = () => {
      card.classList.toggle("can-left", box.scrollLeft > 1);
      card.classList.toggle("can-right", box.scrollLeft + box.clientWidth < box.scrollWidth - 1);
      // Where the fixed first column ends: the shade that says columns are hidden on the left starts there
      card.style.setProperty("--first", `${box.querySelector("th")?.offsetWidth || 0}px`);
    };
    box.addEventListener("scroll", mark, { passive: true });
    new ResizeObserver(mark).observe(box);
    // The arrows stay above the bar of actions, whatever its height (its buttons wrap on a narrow window)
    const bar = document.querySelector(".bar"), lift = () => card.style.setProperty("--bar", `${bar ? bar.offsetHeight : 0}px`);
    if (bar) new ResizeObserver(lift).observe(bar);
    lift();
    card.querySelectorAll("[data-scroll]").forEach(b => b.onclick = () =>
      box.scrollBy({ left: Number(b.dataset.scroll) * box.clientWidth * 0.6, behavior: "smooth" }));
    mark();
  });
}

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
    return `${p.state === "stale" ? "" : `<span class="nowrap">${esc(p.last) || "—"}</span>`}${note ? `<div class="${p.state === "stale" ? "muted" : "error-text"} small">${note}</div>` : ""}`;
  };
  const what = f => esc(f.repo || f.author || f.url || f.name || "");
  const proposal = (p, group) => {
    const done = p.applied, later = !done && p.later;
    const ticked = SOURCE_TICKS[p.id] ?? p.recommended;
    return `<li${done || later ? ' class="handled"' : ""}><label>${done ? `<span class="badge ok">${S.applied}</span>`
      : later ? `<span class="badge neutral">${S.later}</span> <button class="small-button" data-now="${p.id}">${S.decideNow}</button>`
      : `<input type="checkbox" data-proposal="${p.id}" data-group="${group}"${ticked ? " checked" : ""}>`} <span><b>${esc(p.feed.id)}</b>
      <span class="muted">(${esc(p.feed.type || "rss")}${what(p.feed) ? `, ${what(p.feed)}` : ""})</span> : ${esc(S.why[p.why](p))}${
      p.recommended && !done && !later ? ` <span class="badge neutral">${S.recommended}</span>` : ""}${
      done?.pr_url ? ` ${extLink(done.pr_url, "PR")}` : ""}</span></label></li>`;
  };
  const groups = check ? [
    ["remove", check.proposals.filter(p => p.action === "remove")], ["change", check.proposals.filter(p => p.action === "change")],
    ["add", check.proposals.filter(p => p.action === "add" && p.why !== "no-advisories")],
    ["advisories", check.proposals.filter(p => p.why === "no-advisories")]].filter(([, list]) => list.length) : [];
  const last = check?.applied?.filter(a => !a.state).at(-1);  // the pull request (or branch) still to merge
  const draw = () => {
    const sideways = page.querySelector(".card.wide .scroll-x")?.scrollLeft || 0;  // kept when the table is drawn again
    const q = view.query.trim().toLowerCase(), open = p => !p.applied && !p.later;
    const typed = f => !q || [f.id, f.target, f.url, f.type, f.tier, S.verdicts[f.verdict]].some(x => x && String(x).toLowerCase().includes(q));
    const shown = sortSources(s.feeds.filter(f => (!view.states.size || view.states.has(f.verdict)) && typed(f)));
    const arrow = key => view.sort !== key ? "" : view.dir > 0 ? " ▲" : " ▼";
    page.innerHTML = `
    <h1>${S.title}</h1>
    <p class="subtitle">${s.period.watches ? S.intro(s.period, s.runs, esc(s.file)) : S.noHistory}</p>
    <p><button class="primary" id="check"${busy ? " disabled" : ""}>${busy ? S.checking(s.checking.done, s.checking.total) : S.check}</button>
      <span class="muted small">${check ? S.checked(new Date(check.checked).toLocaleString(lang)) : S.neverChecked} ${S.checkHelp}</span></p>
    ${s.checking.error ? `<p class="error-text">${esc(s.checking.error)}</p>` : ""}
    ${check ? `<h2>${S.proposals(check.proposals.filter(open).length, check.proposals.filter(p => p.applied).length, check.proposals.filter(p => !p.applied && p.later).length)}</h2>
      ${last ? `<p class="small">${S.appliedTo(esc(last.branch), last.pr_url ? extLink(last.pr_url, esc(last.pr_url)) : "")}</p>` : ""}
      ${groups.length ? groups.map(([g, list]) => `<details class="card foldable"${g === "advisories" ? "" : " open"}>
        <summary class="header"><b>${S.groups[g]}</b> <span class="badge neutral">${list.length}</span>${
          list.some(open) ? ` <button class="small-button" data-tick-group="${g}">${T.verif.tickCard(list.filter(open).length)}</button>` : ""}</summary>
        <ul class="leads">${list.map(p => proposal(p, g)).join("")}</ul></details>`).join("") : `<p class="muted">${S.noProposals}</p>`}
      <p class="muted small">${S.staleNote(check.stale_days)}</p>
      ${view.error ? `<p class="error-text">${esc(view.error)}</p>` : ""}
      ${check.proposals.some(open) ? `<div class="bar"><button id="all">${T.verif.tickAll}</button><button id="nothing">${T.verif.untickAll}</button>
        <button id="later" title="${esc(S.putOffHelp)}"></button><button class="primary" id="apply"></button></div>
        <p class="muted small">${S.putOffHelp}</p>` : ""}` : ""}
    <ul class="small filters">
      <li><button class="badge neutral${view.states.size ? " dim" : ""}" data-state="" aria-pressed="${!view.states.size}">${S.all(s.feeds.length)}</button> ${S.filterHelp}</li>
      ${SOURCE_ORDER.filter(v => by(v).length).map(v => `<li><button class="badge ${SOURCE_CLASS[v]}${view.states.size && !view.states.has(v) ? " dim" : ""}"
        data-state="${v}" aria-pressed="${view.states.has(v)}">${S.count(by(v).length, S.verdicts[v])}</button> ${rules[v]}</li>`).join("")}</ul>
    <p class="muted small table-tools"><input type="search" id="source-filter" value="${esc(view.query)}" placeholder="${esc(S.search)}" aria-label="${esc(S.search)}">
      <span>${S.shown(shown.length, s.feeds.length)}${view.sort ? ` · <button class="small-button" id="default-sort">${S.defaultSort}</button>` : ""}</span></p>
    ${wideTable(`<table class="sources">
      <thead><tr>${S.columns.map((c, i) => { const [key, number] = SOURCE_COLUMNS[i]; return `<th${number ? ' class="number"' : ""}${
        view.sort === key ? ` aria-sort="${view.dir > 0 ? "ascending" : "descending"}"` : ""}><button class="sort" data-sort="${key}" title="${esc(S.sortBy(c))}">${c}${arrow(key)}</button></th>`; }).join("")}</tr></thead>
      <tbody>${shown.map(f => `<tr>
        <td class="first"><b>${esc(f.id)}</b><div class="muted small">${f.url ? extLink(f.url, esc(f.target)) : esc(f.target)}</div></td>
        <td class="small">${esc(f.type)}${f.tier ? ` · ${esc(f.tier)}` : ""}</td>
        <td class="small nowrap">${esc(f.last_item) || "—"}</td>
        <td class="small">${answered(f)}</td>
        ${cell(f.collected)}${cell(f.kept)}${cell(f.judged)}${cell(f.useful)}${cell(f.proposed)}${cell(f.accepted)}
        <td class="nowrap"><span class="badge ${SOURCE_CLASS[f.verdict]}" title="${esc(rules[f.verdict])}">${S.verdicts[f.verdict]}</span>${
          f.insurance ? ` <span class="muted small" title="${esc(S.insurance)}">🛡</span>` : ""}</td></tr>`).join("")}</tbody>
    </table>`, S.scrollLeft, S.scrollRight)}
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
    page.querySelector(".card.wide .scroll-x").scrollLeft = sideways;
    wideTables(page);
    // The text typed filters as it is typed; the page is drawn again, the caret stays where it was
    $("#source-filter").oninput = e => {
      view.query = e.target.value;
      const at = e.target.selectionStart;
      draw();
      $("#source-filter").focus();
      $("#source-filter").setSelectionRange(at, at);
    };
    $("#check").onclick = async () => { $("#check").disabled = true; await api("/api/sources/check", {}); viewSources(); };
    // The proposals: ticked ones go to one pull request
    const boxes = [...page.querySelectorAll("[data-proposal]")];
    const count = () => {
      const n = boxes.filter(b => b.checked).length;
      if ($("#apply")) { $("#apply").textContent = S.apply(n, s.repository); $("#apply").disabled = n === 0 || busy; }
      if ($("#later")) { $("#later").textContent = S.putOff(n); $("#later").disabled = n === 0 || busy; }
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
    // Put off until the next check, or decide now after all: nothing changes in the guide
    const later = async (ids, on) => {
      try {
        await api("/api/sources/later", { ids, on });
        view.error = "";
      } catch (e) {
        view.error = e.message;
      }
      viewSources();
    };
    if ($("#later")) $("#later").onclick = () => later(boxes.filter(b => b.checked).map(b => b.dataset.proposal), true);
    page.querySelectorAll("[data-now]").forEach(b => b.onclick = e => { e.preventDefault(); later([b.dataset.now], false); });
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
