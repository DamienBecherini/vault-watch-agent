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
// A lead or a finding as one line (news.line, verify._line): « [kind] pages: text Read also: a, b. Sources: u, v ».
// Its parts, to draw them apart; the line itself stays what is sent to a run.
function leadParts(line) {
  let rest = line, sources = [], read = [];
  const s = rest.match(/ Sources: (https?:\/\/\S.*)$/);
  if (s) { sources = s[1].split(/,\s+/).filter(u => /^https?:\/\//.test(u)); rest = rest.slice(0, s.index); }
  const r = rest.match(/ Read also: ([^\n]*?)\.$/);
  if (r) { read = r[1].split(/,\s+/); rest = rest.slice(0, r.index); }
  const k = rest.match(/^\[([^\]]+)\] ([^:]*?): /);
  if (!k) return { kind: "", pages: [], text: rest, read, sources };
  return { kind: k[1], pages: k[2] === "no page yet" ? [] : k[2].split(", "), text: rest.slice(k[0].length), read, sources };
}
// A check's estimate as the interface will start it: in another language than English, its leads are explained in
// it, which the model writes on top (verify.EXPLAIN_SHARE)
const est = (o, key) => lang !== "en" && o[`${key}_explained`] != null ? o[`${key}_explained`] : o[key];
const OPEN_LEADS = new Set();  // the leads unfolded, kept while the page is open (verification/line)
// Where a lead comes from, in a few words: the repository on GitHub, else the site
const origin = u => {
  try {
    const a = new URL(u), parts = a.pathname.split("/").filter(Boolean);
    return a.hostname === "github.com" && parts.length >= 2 ? `${parts[0]}/${parts[1]}` : a.hostname.replace(/^www\./, "");
  } catch { return u; }
};
// A page of the guide in Obsidian, at the heading the passage is under (Obsidian opens a heading, not a line)
const obsidian = (vaultName, path, heading = "") => `obsidian://open?vault=${encodeURIComponent(vaultName || "")}&file=${
  encodeURIComponent(path.replace(/\.md$/, "") + (heading ? `#${heading.replace(/\[\[([^\]|]*\|)?([^\]]*)\]\]/g, "$2").replace(/[*_`]/g, "")}` : ""))}`;
// A text of the model with its Markdown links: a link is kept only to one of the lead's sources (https), the others
// stay text
const linked = (text, sources) => {
  const known = new Set(sources.map(u => u.replace(/\/$/, ""))), out = [];
  let at = 0;
  for (const m of text.matchAll(/\[([^\]]+)\]\((https:\/\/[^)\s]+)\)/g)) {
    out.push(esc(text.slice(at, m.index)), known.has(m[2].replace(/\/$/, "")) ? extLink(m[2], esc(m[1])) : esc(m[1]));
    at = m.index + m[0].length;
  }
  return out.join("") + esc(text.slice(at));
};
// An address, short: its site and the end of its path (github.com › vllm/releases/tag/v0.34.0)
const shortUrl = u => {
  try {
    const a = new URL(u), path = decodeURIComponent(a.pathname).replace(/\/$/, "");
    const tail = path.length > 42 ? `…${path.slice(-40)}` : path;
    return `${a.hostname.replace(/^www\./, "")}${tail ? ` › ${tail.replace(/^\//, "")}` : ""}`;
  } catch { return u; }
};
let source = null;  // EventSource of the run being followed

// --- Languages ---------------------------------------------------------------------------------------
const TEXTS = {
  fr: {
    nav: { watches: "Veilles", sources: "Sources", check: "Vérifier le guide", report: "Signaler ou proposer", languages: "Langues", costs: "Coûts" },
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
      linksLink: "Un article, une page, un PDF à lire en entier ? Donne leurs adresses : l'agent en tire des pistes.",
      linksRead: "Les liens", linkChars: (n, cut) => `${n.toLocaleString("fr")} caractères lus${cut ? " (coupé)" : ""}`,
      dig: "creuser (plusieurs sources, plus de recherches, un peu plus cher)",
      kinds: { "From a link": "D'un lien", "Found on the web": "Trouvée sur le web", Newer: "Plus récent", Missing: "Manquant",
        "Seen by the watch": "Vu par la veille", Critical: "Critique", Major: "Majeur", Minor: "Mineur" },
      noPage: "pas encore de page", readAlso: "À lire aussi :", sources: "Sources :",
      detail: { says: "Ce que dit la source", guide: "Ce que dit le guide", check: "À vérifier", matters: "Ce que ça change pour le lecteur" },
      sentText: "Texte envoyé à la passe (en anglais)",
      readIn: "Lu dans", writeIn: "à écrire dans", openObsidian: "Ouvrir dans Obsidian", line: n => `ligne ${n}`,
      nothingQuoted: "Aucun passage cité : le sujet n'est dans aucune page.", theLink: "(le lien lu)",
      digSect: "Creuser et lecture", digLabel: "Creuser :", digNoneShort: "Rien", digAllShort: "Tout",
      barOptions: "Options", createShort: "Créer la passe",
      barSum: (n, d, price) => `<b>${n} piste${n > 1 ? "s" : ""} cochée${n > 1 ? "s" : ""}</b>${d ? `, dont ${d} creusée${d > 1 ? "s" : ""}` : ""}${price ? ` · ${price}` : ""}`,
      barSumShort: (n, price) => `<b>${n}</b>${price ? ` · ${price}` : ""}`,
      stepWhat: { add: "Vérifie chaque piste sur le web, puis écrit où elle va", fix: "Vérifie chaque erreur sur les sources, puis la corrige",
        "fix-translation": "Corrige la traduction à partir du français", compact: "Propose les allègements de chaque piste",
        crosscheck: "Relit tout le guide avec les modifications : ce qu'elles contredisent ailleurs", mirror: "Traduit les pages modifiées dans les autres langues" },
      digShort: "creuser", digNone: "Ne rien creuser", digAll: "Tout creuser", digTicked: "Creuser toutes les cochées",
      digSome: (d, m) => `Creuser ${d} sur ${m}`,
      digCost: (m, a, each, d, deep, base, total) => `${m} piste${m > 1 ? "s" : ""} cochée${m > 1 ? "s" : ""} : ${a} normale${a > 1 ? "s" : ""} (≈ ${each} chacune) + ${d} creusée${d > 1 ? "s" : ""} (≈ ${deep} chacune) + la relecture croisée et les miroirs (≈ ${base}) = ${total} au prix catalogue`,
      digFree: (a, d, how) => `${a} normale${a > 1 ? "s" : ""}, ${d} creusée${d > 1 ? "s" : ""} · ${how}`,
      digWarn: m => `Tout creuser : ${m} appels qui ont chacun tout le web d'un appel. Plus cher, plus long, et plus de limite sur un abonnement.`,
      digButton: "Creuser cette piste", digWhat: "Un appel rien que pour elle : plusieurs sources indépendantes, plus de recherches, plusieurs pages possibles.",
      sourcesTitle: n => `Sources (${n})`, readTitle: n => `Pages à relire aussi (${n})`,
      unfold: "déplier", unfoldAll: "Tout déplier", foldAll: "Tout replier", howToRead: "Comment lire une piste",
      legend: [["Une piste", "Une question à vérifier, écrite par le modèle après avoir lu la source et tout le guide. Rien n'est encore modifié."],
        ["La case", "Envoie la piste dans une passe d'ajouts (le bouton en bas), qui la vérifie sur les sources primaires puis propose une modification, que tu relis."],
        ["Creuser", "La même chose, avec un appel rien que pour elle : plusieurs sources indépendantes, plus de recherches, plusieurs pages possibles. Un peu plus cher ; coche aussi la piste."],
        ["Ce que dit le guide", "Le passage exact de la page, retrouvé par le programme (la phrase visée surlignée) ; le lien ouvre la page dans Obsidian, à l'intertitre le plus proche."],
        ["Sources", "La source lue, puis les sources primaires qu'elle cite : la passe les ouvrira pour vérifier."],
        ["Pages à relire aussi", "Les autres pages qui disent la même chose ou en dépendent : la passe les lit pour tout corriger d'un coup."],
        ["Texte envoyé à la passe", "Ce que lit vraiment la passe, en anglais (l'outillage s'écrit en anglais). Le français est une explication pour toi."]],
      leadsAdd: "Une piste est une question à vérifier, pas une modification : rien n'est encore écrit. Le passage encadré est ce que le guide dit aujourd'hui (en surligné, la phrase visée ; les lignes voisines donnent le contexte). Pour chaque piste cochée, la passe d'ajouts lit les sources, puis propose de corriger ce qui est dépassé ou d'ajouter ce qui manque, dans toutes les pages concernées. Tu relis ces propositions avant qu'elles s'appliquent.",
      onlyFree: "Seulement les gratuits",
      waiting: "en attente", checking: "en cours…", ok: "RAS", problems: "à regarder", failed: "n'a pas pu tourner",
      notFixable: "Pas encore corrigeable par une passe fix (les traductions se corrigent depuis le français) : à reprendre à la main ou par une prochaine fonction.",
      seeDetails: "Détails", dead: "Sources qui ne répondent pas", blocked: "Bloquées par une protection anti-robots (souvent normales dans un navigateur)",
      claims: "Affirmations à revérifier", pagesDue: "Pages à revoir", log: "Journal",
      // by: the ticked leads per kind of run (fix, translation, compact, add); one run per kind
      createFix: (by, c, runs = {}) => {
        const kinds = [["fix", "fix", "≈ 6-8 $"], ["translation", "traduction", "< 1 $"], ["compact", "compactage", runs.compact || "≈ 5-6 $"], ["add", "ajouts", runs.add || "≈ 15-25 $"]].filter(k => by[k[0]]);
        if (!kinds.length) return "Coche des pistes pour créer une passe";
        if (kinds.length === 1 && runs.short) return `Créer une passe ${kinds[0][0] === "add" ? "d'ajouts" : kinds[0][1]} · ${c(kinds[0][2], kinds[0][0])}`;
        return kinds.length > 1 ? `Créer ${kinds.length} passes : ${kinds.map(k => `${by[k[0]]} piste(s) en ${k[1]} (${c(k[2], k[0])})`).join(", ")}`
          : `Créer une passe ${kinds[0][0] === "add" ? "d'ajouts" : kinds[0][1]} avec ${kinds[0] ? by[kinds[0][0]] : 0} piste(s)${kinds[0][0] === "add" && runs.dug ? ` (${runs.dug} creusée${runs.dug > 1 ? "s" : ""})` : ""} · ${c((kinds[0] || [0, 0, "≈ 6-8 $"])[2], (kinds[0] || ["fix"])[0])}`;
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
      runRunning: "passe en cours", follow: "suivre",
      checkKinds: { health: "Santé du guide", light: "Allègement", news: "Nouveautés" },
      kindsWhat: { health: "liens, fraîcheur, cohérence, traductions…", light: "taille des pages, compactage", news: "ce qui manque au guide" },
      allKinds: "Toutes", fromReport: "depuis Signaler ou proposer",
      nLinks: n => `${n} lien${n > 1 ? "s" : ""}`, moreLinks: n => `et ${n} autre${n > 1 ? "s" : ""}`, nChecks: n => `${n} contrôles`,
      onSubscription: "abonnement", listPriceTip: "Valeur au prix catalogue de l'API ; pris sur ton abonnement Claude, rien n'est facturé",
      confirmParallel: names => `Une passe est déjà en cours : ${names}.\n\nEn lancer une autre en même temps ? Chacune travaille sur sa propre branche, mais le dépôt du guide n'accepte qu'une pull request à la fois : tu publieras la seconde après la fusion de la première.`,
    },
    loading: "Chargement…",
    serverDown: "Le serveur ne répond pas : il s'arrête après 1 h d'inactivité. Relance-le (Nouvel onglet, module « Veille du guide IA »), puis recharge la page. Les passages en pause n'ont rien perdu.",
    statuses: {
      new: "À analyser", running: "En cours", review: "Relecture à faire", retouch: "Retouches possibles", translation: "Traduction à relire", publish: "Publication à valider",
      published: "PR créée", "nothing-applied": "Rien appliqué", "not-published": "Non publié", stopped: "Interrompu",
      closed: "Traitée hors agent", merged: "✓ Terminée · PR fusionnée", "pr-open": "PR à fusionner",
      "pr-closed": "PR fermée sans fusion",
    },
    steps: {
      collect: "Récupération de la veille", triage: "Tri des éléments", locate: "Recherche des pages concernées",
      propose: "Propositions de corrections", number: "Numérotation et contrôle des citations",
      crosscheck: "Relecture avec tout le guide et le web", report: "Rapport", review: "Ta relecture",
      apply: "Application sur une branche", retouch: "Tes retouches", mirror: "Traduction anglaise", translation: "Ta relecture de la traduction", audits: "Contrôles du guide (npm test)",
      links: "Vérification des liens", publish: "Push et pull request",
    },
    watches: "Veilles",
    watchesIntro: () => `Une veille est publiée par ${forgeName()} tous les 15 jours. L'agent l'analyse, tu relis ses propositions, puis il ouvre la pull request.`,
    analyse: c => `Analyser · ${c}`, merge: () => `Fusionner sur ${forgeName()}`,
    buttons: { review: "Relire", retouch: "Retoucher", translation: "Relire la traduction", publish: "Valider la publication", running: "Suivre", stopped: "Reprendre" },
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
    addedAfter: "Ajouté après", notesAdded: "Note ajoutée : ",
    groupLinked: n => `${n} corrections liées`,
    groupWhy: "· appliquées ensemble : elles dépendent l'une de l'autre (un texte et sa note, par exemple). Pour changer un texte, retouche-le au lieu de décocher.",
    leadN: n => `Piste ${n}`, leadCount: (n, p) => `${n} correction${n > 1 ? "s" : ""} · ${p} page${p > 1 ? "s" : ""}`,
    leadSource: "Source", seeCheck: "voir la vérification",
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
    retouch: "Retoucher", retouchBack: "Revenir à la proposition", retouched: "retouchée",
    retouchHelp: "Ton texte remplace la proposition. Les contrôles gratuits le revérifient ; aucun modèle n'est rappelé. La proposition reste dans le rapport.",
    retouchProblem: check => `ne s'appliquera pas : ${check}`, retouchChecking: "vérification…",
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
    hl: { count: (i, n) => `passage ${i} / ${n}`, prev: "Passage modifié précédent", next: "Passage modifié suivant" },
    pub: {
      before: "Avant de publier", audits: "Contrôles du guide", auditsWhat: "(front matter, diagrammes, miroirs, liens internes)", log: "Le journal",
      translation: "Traduction", mirrored: n => `${n} page${n > 1 ? "s" : ""} traduite${n > 1 ? "s" : ""} mise${n > 1 ? "s" : ""} à jour`,
      links: "Liens", linksToCheck: n => `${n} lien${n > 1 ? "s" : ""} à vérifier toi-même`,
      linkBlocked: "Le site bloque les robots : ouvre-le dans ton navigateur.", linkDead: label => `Il ne répond pas (${label}).`,
      linkNew: "ajouté par ce passage", linkOld: "déjà dans le guide", citedBy: "Cité par",
      weightTitle: "Poids des pages", weight: (b, a, d) => `${d} (${b} → ${a}, miroirs non comptés)`,
      pagesTitle: "Les pages modifiées, et leur traduction", unfoldAll: "Tout déplier / replier",
      passages: n => `${n} passage${n > 1 ? "s" : ""}`, correct: "Corriger", again: "Retraduire la page depuis le début", againShort: "Retraduire",
      rawDiff: "Le diff git brut de la branche (pour vérifier ligne à ligne)",
      correctHelp: "Corrige la page et sa traduction. « Enregistrer et recontrôler » commite sur la branche du passage, puis les contrôles du guide et des liens repassent : aucun modèle n'est appelé. Le passage revient ensuite ici.",
      saveCheck: "Enregistrer et recontrôler",
      sourceOnly: "Tu as corrigé le français, pas sa traduction : elle ne le suit plus (les contrôles du guide échoueraient).",
      againMine: "Retraduire mes corrections", checkOnly: "Contrôler sans retraduire",
      confirmAgain: (t, cost) => `Retraduire « ${t} » depuis le début ?${cost ? ` (${cost})` : ""}\n\nLa traduction actuelle de ses passages modifiés est remplacée, y compris ce que tu y as corrigé.`,
    },
    pairs: {
      title: "La traduction, à côté de sa source",
      intro: "À gauche, ce qui a changé dans la page source ; à droite, ce que le modèle de traduction en a fait dans le miroir. Juge la traduction phrase à phrase.",
      edit: "Tu peux retoucher la traduction à droite : ton texte remplace celui du modèle, puis les contrôles du guide et les liens passent dessus.",
      source: "Source", target: "Traduction", none: "Rien de traduit pour ce passage.", removed: "(passage supprimé)",
      retouched: "retouchée", problem: "Le traducteur a signalé",
      ok: n => n ? `Valider avec ${n} retouche${n > 1 ? "s" : ""}` : "Valider la traduction",
      runTitle: "Synchronisation des langues",
    },
    retouchPause: {
      intro: (n, branch) => `Les ${n} corrections acceptées sont appliquées sur la branche du passage${branch ? ` (<code>${branch}</code>)` : ""} : une copie à part du guide, ton dossier et main n'ont pas bougé. Rien n'est encore traduit ni publié. C'est le moment de relire les pages telles qu'elles seront publiées, et d'y corriger ce qui ne va pas : tes retouches seront commitées à ton nom, la traduction anglaise les suivra, et les contrôles du guide passeront dessus. Rien à changer ? Clique « Passer ».`,
      pages: "Les pages modifiées par ce passage",
      openHere: "Ouvrir ici", openObsidian: "Ouvrir dans Obsidian",
      obsidianLater: "Prête d'abord ton dossier (ci-dessous) : sinon Obsidian montrerait la page sans les corrections.",
      obsidianFirst: a => `Pour les ouvrir dans Obsidian, ${a} : sinon il montrerait les pages sans les corrections.`, lendFirst: "prête d'abord ton dossier",
      obsidian: "Relire dans Obsidian",
      lend: "Prêter mon dossier à ce passage",
      lendHelp: path => `Obsidian affiche ton dossier du guide (${path}), qui est sur main : il ne voit pas les corrections, elles sont sur la branche du passage. Pour les relire dans Obsidian, avec son aperçu et ses liens, prête ton dossier au passage : il bascule sur cette branche le temps des retouches, et tu modifies les pages directement dans Obsidian. « J'ai fini » (ou « Passer ») le ramène sur main, comme avant. La bascule prend deux secondes : n'écris rien dans Obsidian à ce moment-là, ta frappe pourrait se perdre.`,
      whyLend: "Tu peux aussi tout faire ici, dans le navigateur, sans prêter ton dossier.",
      dirty: n => `Ton dossier contient ${n} fichier${n > 1 ? "s" : ""} modifié${n > 1 ? "s" : ""} ou nouveau${n > 1 ? "x" : ""}, pas commité${n > 1 ? "s" : ""} :`,
      setAside: "Les mettre de côté et prêter le dossier",
      setAsideHelp: "Ils sont rangés dans une remise git nommée d'après ce passage, et remis en place quand le dossier revient.",
      blocked: why => `Impossible de prêter le dossier : ${why}. Termine-le, ou retouche ici.`,
      lentOther: t => `Ton dossier est prêté au passage ${t} : termine ses retouches d'abord, ou retouche ici.`,
      lentNow: path => `Ton dossier <code>${path}</code> est sur la branche du passage : Obsidian montre les pages corrigées. Retouche-les, puis « J'ai fini » ; ou reprends ton dossier sans finir l'étape.`,
      takeBack: "Reprendre mon dossier",
      takeBackHelp: "Ton dossier revient sur main, comme avant le prêt, sans terminer l'étape. Ce que tu as modifié dans Obsidian est gardé : commité sur la branche du passage, tu le retrouves en ouvrant la page ici. Tu peux ensuite continuer ici, ou prêter ton dossier à nouveau.",
      here: "Relire ici, dans le navigateur",
      hereHelp: lent => lent ? "Choisis une page, modifie son texte (en Markdown), puis « Enregistrer ». Ton dossier étant prêté, ce que tu enregistres ici s'écrit dans ton dossier : Obsidian le voit aussitôt."
        : "Choisis une page, modifie son texte (en Markdown), puis « Enregistrer ». Tu modifies la copie du passage, pas ton dossier : Obsidian ne verra le résultat qu'une fois la pull request fusionnée.",
      other: "ou une autre page (chemin dans le guide)", open: "Ouvrir", save: "Enregistrer", saved: "Enregistré.",
      revert: "Annuler mes modifications", close: "Fermer la page", reverted: "Modifications annulées : la page est comme à son dernier enregistrement.",
      unsaved: "Modifications non enregistrées", undoHelp: "Ctrl+Z et Ctrl+Y annulent et rétablissent ta frappe ; « Annuler mes modifications » revient à la dernière version enregistrée.",
      confirmLeave: "Cette page a des modifications non enregistrées. Les abandonner ?",
      skip: "Passer", done: "J'ai fini",
      confirmSkip: "Passer cette étape et abandonner ce qui a été retouché ?",
      banner: (t, lent, n) => lent ? `Ton dossier du guide est prêté au passage ${t}.` : `${n} fichier(s) de ton dossier mis de côté pour le passage ${t} ne sont pas encore remis.`,
      putBack: "Les remettre", see: "Voir le passage",
    },
    languages: {
      title: "Synchroniser les langues",
      intro: names => `Tu écris dans la langue du guide, dans Obsidian ; ici, tu demandes que les autres langues suivent (${names}). La page liste les pages qui ont changé depuis leur dernière traduction, avec ce qui a changé. Tu peux d'abord faire vérifier tes modifications, puis l'agent traduit seulement les passages modifiés et le passage suit le chemin habituel : contrôles du guide, liens, et la pull request après ton feu vert.`,
      noMirror: "Le guide ne déclare aucun miroir : il n'y a rien à synchroniser.",
      none: "Tout est synchronisé : aucune page n'est en avance sur son miroir.",
      hand: "Modifiées dans ton dossier, pas encore commitées",
      handHelp: "Le passage les copie sur sa branche (un commit « edits by hand ») avec leur traduction : une seule pull request pour les deux langues. Ton dossier n'est pas touché ; une fois la pull request fusionnée, l'agent remet tes copies à l'identique de la branche principale à sa prochaine mise à jour du dossier.",
      ahead: "En avance sur leur miroir",
      aheadHelp: base => `Déjà sur <code>${base}</code>, modifiées depuis la dernière fois que leur miroir a changé : la traduction part de là.`,
      elsewhere: pages => `Pas proposées : ${pages}. Dans ton dossier, ces pages ne partent pas de la version fusionnée (une autre branche, ou un dossier en retard) : les copier sur une branche de la branche principale déferait ce qu'elle a reçu depuis. Reviens sur la branche principale à jour pour les synchroniser.`,
      passages: n => `${n} passage${n > 1 ? "s" : ""} modifié${n > 1 ? "s" : ""}`, since: c => `depuis ${c}`,
      zones: n => n > 1 ? `Les ${n} zones modifiées, deux lignes autour` : "La zone modifiée, deux lignes autour",
      tickAll: "Tout cocher", untickAll: "Tout décocher",
      button: (n, c) => n ? `Traduire ${n} page${n > 1 ? "s" : ""} · ${c}` : "Coche au moins une page",
      check: {
        title: "Vérifier avant de traduire (facultatif)",
        intro: "Sur les passages que tu as modifiés, dans les pages cochées. Rien ne change sans toi : chaque remarque s'accepte ou se laisse, et ce que tu acceptes s'écrit dans ton dossier comme si tu l'avais tapé, puis se traduit avec le reste.",
        kinds: { spelling: "Orthographe et grammaire", facts: "Véracité et pertinence, sur le web", consistency: "Cohérence avec le reste du guide" },
        what: { spelling: "le modèle de traduction, sur les passages seuls", facts: "le modèle de raisonnement cherche la source de chaque fait", consistency: "la relecture croisée lit tout le guide : ce que tes ajouts contredisent ou rendent obsolète ailleurs" },
        button: c => `Vérifier · ${c}`, none: "Coche une vérification",
        running: "Vérification en cours…", error: "La vérification n'a pas pu se faire",
        found: (n, c) => n ? `${n} remarque${n > 1 ? "s" : ""} · ${c}` : `Rien à corriger · ${c}`,
        notes: "Doutes, sans correction proposée", source: "source", notFound: "texte introuvable dans la page",
        apply: n => n ? `Appliquer ${n} correction${n > 1 ? "s" : ""} dans mon dossier` : "Ne rien appliquer",
        failed: "Pas appliquées (leur texte a changé depuis la vérification, par une autre correction ou dans ton dossier) :",
        overlaps: ids => `reprend le même passage que ${ids} : coche l'une ou l'autre`,
      },
    },
    reportTitle: "Signaler une erreur ou proposer un sujet",
    reportKinds: { fix: "Une erreur à corriger", add: "Une idée ou une information à creuser", links: "Des liens à lire en entier" },
    linksIntro: "Une adresse par ligne : un article, une page, un rapport en PDF, le dépôt d'un projet. L'agent lit chacune en entier, sans modèle, puis Claude la lit avec tout le guide et liste ce qui le concerne. Ce sont des pistes : rien n'est vérifié ni modifié. Tu coches celles à garder, et la passe d'ajouts les vérifie sur des sources primaires avant de proposer où les écrire.",
    linksCost: (base, each, max) => `Compte ${base}, plus ${each} par lien lu (${max} liens au plus), puis la passe d'ajouts pour les pistes gardées.`,
    linksExample: "https://example.org/un-article-sur-un-modele\nhttps://example.org/rapport-2026.pdf",
    linksButton: n => n ? `Lire ${n} lien${n > 1 ? "s" : ""} et lister les pistes` : "Lire les liens et lister les pistes",
    linksVideo: "Une vidéo (YouTube, Arte…) se lit par dl-sub-dub, qui n'est pas réglé (settings.json : videos, voir la doc « Nouveautés ») : pour l'instant, colle ce qu'elle dit dans l'onglet précédent.",
    linksVideoReady: "Une vidéo (YouTube, Arte…) se lit par dl-sub-dub, prêt : ses sous-titres, ou son audio transcrit sur cette machine (plusieurs minutes pour une longue vidéo).",
    linksVideoDown: why => `Une vidéo se lit par dl-sub-dub, qui n'est pas prêt : ${why}.`,
    linksTooMany: max => `${max} liens au plus par lecture.`,
    ideaIntro: "Un sujet par ligne : ce que tu as vu, ou ce qui manque d'après toi, avec une adresse si tu en as une. L'agent vérifie chaque sujet sur des sources primaires, avec tout le guide en contexte, puis propose où l'écrire ; tu relis comme pour une veille. Rien avant : pas de recherche de pistes.",
    ideaCost: (base, each, deep) => `Compte ${base}, plus ${each} par sujet (${deep} par sujet creusé).`,
    ideaExample: "Ollama fait tourner des modèles de voix en local depuis octobre : https://ollama.com/blog/speech-models",
    ideaButton: "Vérifier et proposer des ajouts",
    ideaDeep: "Creuser chaque sujet : plusieurs sources, plus de recherches, un peu plus cher",
    ideaLimit: "Limite : la passe d'ajouts n'écrit jamais de nouvelle page. Elle signale celles qu'il faudrait.",
    draft: { kept: "Brouillon gardé dans ce navigateur, même après un rechargement ; il se vide quand la passe démarre.",
      clear: "Effacer", cleared: "Brouillon effacé.", restore: "Rétablir" },
    perStep: { title: "Moteur et modèles de cette passe", change: "changer pour cette fois", once: "pour cette fois seulement", apply: "Appliquer",
      applyOnce: "Appliquer pour cette fois", changeShort: "changer", chipBilled: "à l'usage (API)", chipSubscription: "abonnement", chipLocal: "local, gratuit", chipProvider: "autre fournisseur",
      cancel: "annuler", edit: "modifier", reset: "revenir aux Réglages", engine: "Moteur", model: "Modèle", effortLabel: "Effort", modelOfRole: "modèle habituel de ce moteur",
      restUnbilled: "le reste non facturé",
      effort: e => ({ low: "effort faible", medium: "effort moyen", high: "effort élevé", xhigh: "effort très élevé", max: "effort maximal" })[e] || e,
      names: { fix: "Corrections", "fix-translation": "Corrections de traduction", compact: "Allègements", add: "Ajouts", crosscheck: "Relecture croisée", mirror: "Miroirs", links: "Lecture des liens" },
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
    nav: { watches: "Watches", sources: "Sources", check: "Check the guide", report: "Report or suggest", languages: "Languages", costs: "Costs" },
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
      linksLink: "An article, a page, a PDF to read whole? Give their addresses: the agent draws leads from them.",
      linksRead: "The links", linkChars: (n, cut) => `${n.toLocaleString("en")} characters read${cut ? " (cut)" : ""}`,
      dig: "dig deeper (several sources, more searches, a little more expensive)",
      kinds: {}, noPage: "no page yet", readAlso: "Read also:", sources: "Sources:",
      detail: { says: "What the source says", guide: "What the guide says", check: "To check", matters: "What it changes for the reader" },
      sentText: "Text sent to the run",
      readIn: "Read in", writeIn: "to write in", openObsidian: "Open in Obsidian", line: n => `line ${n}`,
      nothingQuoted: "No passage quoted: the subject is in no page.", theLink: "(the link read)",
      digSect: "Dig deeper and reading", digLabel: "Dig deeper:", digNoneShort: "None", digAllShort: "All",
      barOptions: "Options", createShort: "Create the run",
      barSum: (n, d, price) => `<b>${n} lead(s) ticked</b>${d ? `, ${d} dug deeper` : ""}${price ? ` · ${price}` : ""}`,
      barSumShort: (n, price) => `<b>${n}</b>${price ? ` · ${price}` : ""}`,
      stepWhat: { add: "Checks each lead on the web, then writes it where it belongs", fix: "Checks each error on the sources, then fixes it",
        "fix-translation": "Fixes the translation from the source language", compact: "Proposes the trims of each lead",
        crosscheck: "Reads the whole guide with the changes: what they contradict elsewhere", mirror: "Translates the pages changed into the other languages" },
      digShort: "dig", digNone: "Dig nothing", digAll: "Dig all", digTicked: "Dig every lead ticked",
      digSome: (d, m) => `Dig ${d} of ${m}`,
      digCost: (m, a, each, d, deep, base, total) => `${m} lead(s) ticked: ${a} plain (≈ ${each} each) + ${d} dug deeper (≈ ${deep} each) + the cross-check and the mirrors (≈ ${base}) = ${total} at list price`,
      digFree: (a, d, how) => `${a} plain, ${d} dug deeper · ${how}`,
      digWarn: m => `Dig all: ${m} calls that each have the whole web of a call. Dearer, longer, and more of a subscription's limit.`,
      digButton: "Dig deeper into this lead", digWhat: "A call of its own: several independent sources, more searches, several pages possible.",
      sourcesTitle: n => `Sources (${n})`, readTitle: n => `Pages to read also (${n})`,
      unfold: "unfold", unfoldAll: "Unfold all", foldAll: "Fold all", howToRead: "How to read a lead",
      legend: [["A lead", "A question to check, written by the model after reading the source and the whole guide. Nothing is changed yet."],
        ["The box", "Sends the lead to an addition run (the button below), which checks it on primary sources then proposes a change, which you review."],
        ["Dig deeper", "The same, with a call of its own: several independent sources, more searches, several pages possible. A little more expensive; it ticks the lead too."],
        ["What the guide says", "The exact passage of the page, found by the program (the sentence concerned highlighted); the link opens the page in Obsidian, at the nearest heading."],
        ["Sources", "The source read, then the primary sources it cites: the run will open them to check."],
        ["Pages to read also", "The other pages that state the same thing or depend on it: the run reads them to fix everything at once."],
        ["Text sent to the run", "What the run really reads, in English (the tooling is written in English)."]],
      leadsAdd: "A lead is a question to check, not a change: nothing is written yet. The framed passage is what the guide says today (highlighted: the sentence concerned; the lines around give the context). For each lead ticked, the addition run reads the sources, then proposes to correct what is out of date or to add what is missing, in every page concerned. You review these proposals before they apply.",
      onlyFree: "Only the free ones",
      waiting: "waiting", checking: "running…", ok: "all clear", problems: "to look at", failed: "could not run",
      notFixable: "Not fixable by a fix run yet (translations are fixed from the French side): to handle by hand or by a later feature.",
      seeDetails: "Details", dead: "Sources not answering", blocked: "Blocked by anti-bot protections (often fine in a browser)",
      claims: "Claims to re-check", pagesDue: "Pages due for review", log: "Log",
      createFix: (by, c, runs = {}) => {
        const kinds = [["fix", "fix", "≈ 6-8 $"], ["translation", "translation", "< 1 $"], ["compact", "compaction", runs.compact || "≈ 5-6 $"], ["add", "addition", runs.add || "≈ 15-25 $"]].filter(k => by[k[0]]);
        if (!kinds.length) return "Tick leads to create a run";
        if (kinds.length === 1 && runs.short) return `Create ${kinds[0][0] === "add" ? "an" : "a"} ${kinds[0][1]} run · ${c(kinds[0][2], kinds[0][0])}`;
        return kinds.length > 1 ? `Create ${kinds.length} runs: ${kinds.map(k => `${by[k[0]]} lead(s) as ${/^a/.test(k[1]) ? "an" : "a"} ${k[1]} run (${c(k[2], k[0])})`).join(", ")}`
          : `Create ${kinds[0]?.[0] === "add" ? "an" : "a"} ${(kinds[0] || [0, "fix"])[1]} run with ${kinds[0] ? by[kinds[0][0]] : 0} lead(s)${kinds[0][0] === "add" && runs.dug ? ` (${runs.dug} dug deeper)` : ""} · ${c((kinds[0] || [0, 0, "≈ 6-8 $"])[2], (kinds[0] || ["fix"])[0])}`;
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
      runRunning: "run in progress", follow: "follow",
      checkKinds: { health: "Guide health", light: "Lighter guide", news: "What is new" },
      kindsWhat: { health: "links, freshness, consistency, translations…", light: "size of the pages, compaction", news: "what the guide is missing" },
      allKinds: "All", fromReport: "from Report or suggest",
      nLinks: n => `${n} link${n > 1 ? "s" : ""}`, moreLinks: n => `and ${n} more`, nChecks: n => `${n} checks`,
      onSubscription: "subscription", listPriceTip: "Worth at the API's list price; taken from your Claude subscription, nothing is billed",
      confirmParallel: names => `A run is already in progress: ${names}.\n\nStart another one at the same time? Each works on its own branch, but publish their pull requests one after the other if the guide's repository takes one at a time.`,
    },
    loading: "Loading…",
    serverDown: "The server does not answer: it may have stopped after being idle (`serve --idle-exit`). Start it again, then reload the page. Paused runs lost nothing.",
    statuses: {
      new: "To analyse", running: "Running", review: "Review pending", retouch: "Retouches possible", translation: "Translation to review", publish: "Publish pending",
      published: "PR opened", "nothing-applied": "Nothing applied", "not-published": "Not published", stopped: "Stopped",
      closed: "Handled without the agent", merged: "✓ Done · PR merged", "pr-open": "PR to merge",
      "pr-closed": "PR closed unmerged",
    },
    steps: {
      collect: "Download the watch", triage: "Triage the items", locate: "Find the pages concerned",
      propose: "Propose corrections", number: "Number them, check the quotes",
      crosscheck: "Cross-check with the whole guide and the web", report: "Report", review: "Your review",
      apply: "Apply on a branch", retouch: "Your retouches", mirror: "English translation", translation: "Your review of the translation", audits: "Guide audits (npm test)",
      links: "Link checks", publish: "Push and pull request",
    },
    watches: "Watches",
    watchesIntro: () => `${forgeName()} publishes a watch every two weeks. The agent analyses it, you review its proposals, then it opens the pull request.`,
    analyse: c => `Analyse · ${c}`, merge: () => `Merge on ${forgeName()}`,
    buttons: { review: "Review", retouch: "Retouch", translation: "Review the translation", publish: "Approve publishing", running: "Follow", stopped: "Resume" },
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
    addedAfter: "Added after", notesAdded: "Footnote added: ",
    groupLinked: n => `${n} related corrections`,
    groupWhy: "· applied together: they depend on each other (a sentence and its footnote, for instance). To change a text, retouch it instead of unticking.",
    leadN: n => `Lead ${n}`, leadCount: (n, p) => `${n} correction${n > 1 ? "s" : ""} · ${p} page${p > 1 ? "s" : ""}`,
    leadSource: "Source", seeCheck: "see the check",
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
    retouch: "Retouch", retouchBack: "Back to the proposal", retouched: "retouched",
    retouchHelp: "Your text replaces the proposal. The free checks run again on it; no model is called again. The proposal stays in the report.",
    retouchProblem: check => `will not apply: ${check}`, retouchChecking: "checking…",
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
    hl: { count: (i, n) => `passage ${i} / ${n}`, prev: "Previous passage changed", next: "Next passage changed" },
    pub: {
      before: "Before publishing", audits: "Guide audits", auditsWhat: "(front matter, diagrams, mirrors, internal links)", log: "The log",
      translation: "Translation", mirrored: n => `${n} translated page${n > 1 ? "s" : ""} updated`,
      links: "Links", linksToCheck: n => `${n} link${n > 1 ? "s" : ""} to check yourself`,
      linkBlocked: "The site blocks robots: open it in your browser.", linkDead: label => `It does not answer (${label}).`,
      linkNew: "added by this run", linkOld: "already in the guide", citedBy: "Cited by",
      weightTitle: "Weight of the pages", weight: (b, a, d) => `${d} (${b} → ${a}, mirrors not counted)`,
      pagesTitle: "The pages changed, and their translation", unfoldAll: "Unfold / fold all",
      passages: n => `${n} passage${n > 1 ? "s" : ""}`, correct: "Correct", again: "Translate the page again from the start", againShort: "Translate again",
      rawDiff: "The raw git diff of the branch (to check line by line)",
      correctHelp: "Correct the page and its translation. « Save and check again » commits on the run's branch, then the guide's checks and the links run again: no model is called. The run then comes back here.",
      saveCheck: "Save and check again",
      sourceOnly: "You corrected the source, not its translation: it no longer follows it (the guide's checks would fail).",
      againMine: "Translate my corrections", checkOnly: "Check without translating",
      confirmAgain: (t, cost) => `Translate « ${t} » again from the start?${cost ? ` (${cost})` : ""}\n\nThe current translation of its changed passages is replaced, including what you corrected in it.`,
    },
    pairs: {
      title: "The translation, beside its source",
      intro: "Left, what changed in the source page; right, what the translation model made of it in the mirror. Judge the translation sentence by sentence.",
      edit: "You can retouch the translation on the right: your text replaces the model's, then the guide's checks and the links run on it.",
      source: "Source", target: "Translation", none: "Nothing translated for this passage.", removed: "(passage removed)",
      retouched: "retouched", problem: "The translator said",
      ok: n => n ? `Approve with ${n} retouch${n > 1 ? "es" : ""}` : "Approve the translation",
      runTitle: "Sync of the languages",
    },
    retouchPause: {
      intro: (n, branch) => `The ${n} corrections accepted are applied on the run's branch${branch ? ` (<code>${branch}</code>)` : ""}: a copy of the guide of its own, your folder and main have not moved. Nothing is translated or published yet. This is the time to read the pages as they will be published and fix what is wrong: your retouches will be committed as yours, the English translation will follow them, and the guide's checks will run on them. Nothing to change? Click « Skip ».`,
      pages: "The pages this run changed",
      openHere: "Open here", openObsidian: "Open in Obsidian",
      obsidianLater: "Lend your folder first (below): otherwise Obsidian would show the page without the corrections.",
      obsidianFirst: a => `To open them in Obsidian, ${a}: otherwise it would show the pages without the corrections.`, lendFirst: "lend your folder first",
      obsidian: "Read in Obsidian",
      lend: "Lend my folder to this run",
      lendHelp: path => `Obsidian shows your guide's folder (${path}), which is on main: it does not see the corrections, they are on the run's branch. To read them in Obsidian, with its preview and its links, lend your folder to the run: it switches to that branch for the retouches, and you edit the pages right in Obsidian. « I am done » (or « Skip ») brings it back to main, as it was. The switch takes two seconds: do not type in Obsidian then, your typing could be lost.`,
      whyLend: "You can also do it all here, in the browser, without lending your folder.",
      dirty: n => `Your folder holds ${n} file${n > 1 ? "s" : ""} changed or new, not committed:`,
      setAside: "Set them aside and lend the folder",
      setAsideHelp: "They go into a git stash named after this run, and come back when the folder does.",
      blocked: why => `The folder cannot be lent: ${why}. Finish it, or retouch here.`,
      lentOther: t => `Your folder is lent to the run ${t}: finish its retouches first, or retouch here.`,
      lentNow: path => `Your folder <code>${path}</code> is on the run's branch: Obsidian shows the corrected pages. Retouch them, then « I am done »; or take your folder back without ending the step.`,
      takeBack: "Take my folder back",
      takeBackHelp: "Your folder goes back to main, as before it was lent, without ending the step. What you changed in Obsidian is kept: committed onto the run's branch, you find it by opening the page here. You can then go on here, or lend your folder again.",
      here: "Read here, in the browser",
      hereHelp: lent => lent ? "Pick a page, change its text (in Markdown), then « Save ». As your folder is lent, what you save here is written into your folder: Obsidian sees it at once."
        : "Pick a page, change its text (in Markdown), then « Save ». You change the run's copy, not your folder: Obsidian will only see the result once the pull request is merged.",
      other: "or another page (path in the guide)", open: "Open", save: "Save", saved: "Saved.",
      revert: "Cancel my changes", close: "Close the page", reverted: "Changes cancelled: the page is as it was last saved.",
      unsaved: "Unsaved changes", undoHelp: "Ctrl+Z and Ctrl+Y undo and redo your typing; « Cancel my changes » goes back to the version last saved.",
      confirmLeave: "This page has unsaved changes. Drop them?",
      skip: "Skip", done: "I am done",
      confirmSkip: "Skip this step and drop what was retouched?",
      banner: (t, lent, n) => lent ? `Your guide's folder is lent to the run ${t}.` : `${n} file(s) of your folder set aside for the run ${t} are not put back yet.`,
      putBack: "Put them back", see: "See the run",
    },
    languages: {
      title: "Sync the languages",
      intro: names => `You write in the guide's language, in Obsidian; here, you ask for the other languages to follow (${names}). The page lists the pages that changed since they were last translated, with what changed. You can have your edits checked first; then the agent translates only the passages that changed, and the run takes the usual path: the guide's checks, the links, and the pull request after your go-ahead.`,
      noMirror: "The guide declares no mirror: there is nothing to sync.",
      none: "Everything is in step: no page is ahead of its mirror.",
      hand: "Changed in your folder, not committed yet",
      handHelp: "The run copies them onto its branch (a commit « edits by hand ») with their translation: one pull request for both languages. Your folder is not touched; once the pull request is merged, the agent puts your copies back in line with the main branch the next time it updates the folder.",
      ahead: "Ahead of their mirror",
      aheadHelp: base => `Already on <code>${base}</code>, changed since their mirror last moved: the translation starts from there.`,
      elsewhere: pages => `Not offered: ${pages}. In your folder these pages do not start from the merged version (another branch, or a folder behind): copied onto a branch of the main branch, they would undo what it received since. Come back to the main branch, up to date, to sync them.`,
      passages: n => `${n} passage${n > 1 ? "s" : ""} changed`, since: c => `since ${c}`,
      zones: n => n > 1 ? `The ${n} zones changed, two lines around` : "The zone changed, two lines around",
      tickAll: "Tick all", untickAll: "Untick all",
      button: (n, c) => n ? `Translate ${n} page${n > 1 ? "s" : ""} · ${c}` : "Tick a page at least",
      check: {
        title: "Check before translating (optional)",
        intro: "On the passages you changed, in the pages ticked. Nothing changes without you: each finding is accepted or left, and what you accept is written in your folder as if you had typed it, then translated with the rest.",
        kinds: { spelling: "Spelling and grammar", facts: "Truth and relevance, on the web", consistency: "Consistency with the rest of the guide" },
        what: { spelling: "the translation model, on the passages alone", facts: "the reasoning model looks for the source of each fact", consistency: "the cross-check reads the whole guide: what your edits contradict or make outdated elsewhere" },
        button: c => `Check · ${c}`, none: "Tick a check",
        running: "Checking…", error: "The check could not run",
        found: (n, c) => n ? `${n} finding${n > 1 ? "s" : ""} · ${c}` : `Nothing to fix · ${c}`,
        notes: "Doubts, without a fix proposed", source: "source", notFound: "text not found in the page",
        apply: n => n ? `Apply ${n} fix${n > 1 ? "es" : ""} in my folder` : "Apply nothing",
        failed: "Not applied (their text changed since the check, by another fix or in your folder):",
        overlaps: ids => `covers the same passage as ${ids}: tick one or the other`,
      },
    },
    reportTitle: "Report an error or suggest a subject",
    reportKinds: { fix: "An error to fix", add: "An idea or a piece of news to dig into", links: "Links to read whole" },
    linksIntro: "One address per line: an article, a page, a PDF report, a project's repository. The agent reads each one whole, without a model, then Claude reads it with the whole guide and lists what concerns it. These are leads: nothing is verified or edited. You tick those to keep, and the addition run checks them on primary sources before proposing where to write them.",
    linksCost: (base, each, max) => `Count ${base}, plus ${each} per link read (${max} links at the most), then the addition run for the leads kept.`,
    linksExample: "https://example.org/an-article-about-a-model\nhttps://example.org/report-2026.pdf",
    linksButton: n => n ? `Read ${n} link${n > 1 ? "s" : ""} and list the leads` : "Read the links and list the leads",
    linksVideo: "A video (YouTube, Arte…) is read through dl-sub-dub, which is not set (settings.json: videos, see the docs « What is new »): for now, paste what it says in the previous tab.",
    linksVideoReady: "A video (YouTube, Arte…) is read through dl-sub-dub, ready: its subtitles, or its audio transcribed on this machine (several minutes for a long video).",
    linksVideoDown: why => `A video is read through dl-sub-dub, which is not ready: ${why}.`,
    linksTooMany: max => `${max} links at the most per reading.`,
    ideaIntro: "One subject per line: what you saw, or what you think is missing, with an address if you have one. The agent checks each subject on primary sources, with the whole guide in context, then proposes where to write it; you review as for a watch. Nothing before: no search for leads.",
    ideaCost: (base, each, deep) => `Count ${base}, plus ${each} per subject (${deep} per subject dug deeper).`,
    ideaExample: "Ollama has run speech models locally since October: https://ollama.com/blog/speech-models",
    ideaButton: "Check and propose additions",
    ideaDeep: "Dig deeper into each subject: several sources, more searches, a little more expensive",
    ideaLimit: "Limit: the addition run never writes a new page. It says which ones would be needed.",
    draft: { kept: "Draft kept in this browser, even after a reload; it empties when the run starts.",
      clear: "Clear", cleared: "Draft cleared.", restore: "Restore" },
    perStep: { title: "Engine and models of this run", change: "change for this time", once: "for this time only", apply: "Apply",
      applyOnce: "Apply for this time", changeShort: "change", chipBilled: "pay per use (API)", chipSubscription: "subscription", chipLocal: "local, free", chipProvider: "another provider",
      cancel: "cancel", edit: "change", reset: "back to the Settings", engine: "Engine", model: "Model", effortLabel: "Effort", modelOfRole: "this engine's usual model",
      restUnbilled: "the rest not billed",
      effort: e => ({ low: "low effort", medium: "medium effort", high: "high effort", xhigh: "very high effort", max: "maximum effort" })[e] || e,
      names: { fix: "Corrections", "fix-translation": "Translation fixes", compact: "Trims", add: "Additions", crosscheck: "Cross-check", mirror: "Mirrors", links: "Reading the links" },
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
  running: "attention", review: "attention", retouch: "attention", translation: "attention", publish: "attention", "pr-open": "attention",
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
// The same as HTML: on a subscription, what the estimate is worth at list price, struck through, beside it
const costHtml = (step, usd) => {
  const said = costOf(step, usd);
  return said === T.subscription && /\d/.test(usd || "")  // on a subscription (the step's, or the engine's when steps are not loaded)
    ? `<s class="worth" title="${esc(T.verif.listPriceTip)}">${esc(usd)}</s> ${esc(said)}` : esc(said);
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
// One card per step of a run (the bar of a check): its number and name, what it does (on a phone, in a « ? »), what
// runs it as chips, and the same fields as stepLine to change it for this run (bindSteps)
function stepCard(step, n, name, what = "") {
  const s = stepNow(step);
  if (!s) return "";
  const pay = s.billing === "subscription" ? ["free", T.perStep.chipSubscription] : s.billing === "none" ? ["free", T.perStep.chipLocal]
    : s.engine !== "api" ? ["", T.perStep.chipProvider] : ["bill", T.perStep.chipBilled];
  return `<div class="step-card${OWN[step] ? " changed" : ""}" data-step-line="${step}">
    <div class="step-head"><b>${n} · ${esc(name)}</b>${what ? `<span class="narrow-only">${tip(what)}</span>` : ""}
      ${STEPS.forced ? "" : `<button type="button" class="small-button" data-step-edit="${step}" data-closed="${OWN[step] ? T.perStep.edit : T.perStep.changeShort}">${OWN[step] ? T.perStep.edit : T.perStep.changeShort}</button>`}</div>
    ${what ? `<div class="step-what wide-only">${esc(what)}</div>` : ""}
    <div class="chips"><span class="chip">${esc(s.engine_label.replace(/\s*\([^)]*\)$/, ""))}</span><span class="chip">${esc(s.model ? modelName(s.model) : "?")}</span><span class="chip">${T.perStep.effort(s.effort)}</span><span class="chip ${pay[0]}">${pay[1]}</span></div>
    ${OWN[step] ? `<div class="step-once">${T.perStep.once}${STEPS.forced ? "" : ` · <button type="button" class="link-button" data-step-reset="${step}">${T.perStep.reset}</button>`}</div>` : ""}
    <span class="step-fields" data-step-fields="${step}" hidden>
      <select data-f="engine" aria-label="${T.perStep.engine}">${STEPS.engines.map(e => `<option value="${esc(e.name)}"${e.name === s.engine ? " selected" : ""}>${esc(e.label)}</option>`).join("")}</select>
      <input type="text" data-f="model" list="models-${step}" value="${esc(s.model)}" placeholder="${esc(T.perStep.modelOfRole)}" aria-label="${T.perStep.model}" spellcheck="false">
      <datalist id="models-${step}"></datalist>
      <select data-f="effort" aria-label="${T.perStep.effortLabel}">${STEPS.efforts.map(e => `<option value="${e}"${e === s.effort ? " selected" : ""}>${T.perStep.effort(e)}</option>`).join("")}</select>
      <button type="button" class="small-button primary" data-step-ok="${step}">${T.perStep.applyOnce}</button>
    </span></div>`;
}
let BAR_ROOM = null;  // what keeps the page's room for the bar at its bottom as tall as the bar (ResizeObserver)
// A bar fixed at the bottom of a page (a check's, a review's, the retouches'): the page leaves room for it under its
// last line, as tall as it is now, so that nothing stays hidden behind it
function keepRoomForBar() {
  BAR_ROOM?.disconnect();
  const bar = page.querySelector(".bar");
  document.body.style.paddingBottom = "";
  if (!bar) return;
  BAR_ROOM = new ResizeObserver(() => { document.body.style.paddingBottom = `${bar.offsetHeight}px`; });
  BAR_ROOM.observe(bar);
}
let BAR_OPEN = (() => { try { return localStorage.getItem("vault-watch-bar-open") === "1"; } catch { return false; } })();
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
// What is typed on the three tabs of « Report or suggest » (fix, add, links): one draft per tab, kept while switching
// tabs and in this browser against a reload, a crash or a closed tab (written half a second after the last key, and
// when the page is left); emptied once the run or the check has started. One guide per server: per guide as well.
const DRAFTS = {}, UNSAVED = new Set();  // UNSAVED: typed here, not written yet (another tab may have sent it since)
const draftKey = k => `vault-watch-draft-${k}`;
const draft = k => k in DRAFTS ? DRAFTS[k] : (DRAFTS[k] = (() => { try { return localStorage.getItem(draftKey(k)) || ""; } catch { return ""; } })());
function storeDraft(k) {
  UNSAVED.delete(k);
  try { if ((DRAFTS[k] || "").trim()) localStorage.setItem(draftKey(k), DRAFTS[k]); else localStorage.removeItem(draftKey(k)); }
  catch { /* private window: kept while the page is open only */ }
}
let draftTimer = null;
addEventListener("pagehide", () => [...UNSAVED].forEach(storeDraft));
// The text area of tab `k` and the line under it that says the draft is kept, with « Clear » (and « Restore » after)
function bindDraft(k, area, note, changed = () => {}) {
  let undone = "";
  const say = () => {
    note.innerHTML = undone ? `${T.draft.cleared} <button type="button" class="link" data-draft="restore">${T.draft.restore}</button>`
      : area.value.trim() ? `${T.draft.kept} <button type="button" class="link" data-draft="clear">${T.draft.clear}</button>` : "";
    note.querySelector("[data-draft]")?.addEventListener("click", e => {
      if (e.target.dataset.draft === "clear") { undone = area.value; area.value = ""; } else { area.value = undone; undone = ""; }
      DRAFTS[k] = area.value;
      storeDraft(k);
      changed();
      say();
      area.focus();
    });
  };
  area.addEventListener("input", () => {
    DRAFTS[k] = area.value;
    UNSAVED.add(k);
    undone = "";
    clearTimeout(draftTimer);
    draftTimer = setTimeout(() => [...UNSAVED].forEach(storeDraft), 500);
    say();
  });
  say();
}
const dropDraft = k => { DRAFTS[k] = ""; storeDraft(k); };  // storeDraft takes it out of UNSAVED: the timer leaves it
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
    a.classList.toggle("active", h === "/" ? a.dataset.nav === "watches" : ["/idea", "/links"].includes(h) ? a.dataset.nav === "report" : h.startsWith(`/${a.dataset.nav}`)));
  page.innerHTML = `<p class="muted">${T.loading}</p>`;
  BAR_ROOM?.disconnect(); document.body.style.paddingBottom = "";  // the room left for a check's bar, until it is drawn again
  try {
    if (h.startsWith("/run/")) await viewRun(decodeURIComponent(h.slice(5)));
    else if (h.startsWith("/check/")) await viewCheck(decodeURIComponent(h.slice(7)));
    else if (h === "/check") await viewChecks();
    else if (h === "/sources") await viewSources();
    else if (h === "/links") await viewLinks();
    else if (h === "/report" || h === "/idea") await viewReport(h === "/idea");
    else if (h === "/costs") await viewCosts();
    else if (h === "/languages") await viewLanguages();
    else if (h === "/chapters") await viewChapters();
    else await viewWatches();
    keepRoomForBar();
    asideBanner();
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
            !["new", "closed"].includes(r.status) ? ` · ${T.count(r.corrections, r.applied)} · ${costTag(r.cost, r.unbilled_usd, false)}` : ""}${
            r.pr_url ? ` · ${extLink(r.pr_url, "pull request")}` : ""}</div>
        </div>
        ${badge(r.status)} ${action}
      </div>`;
    }).join("") || `<p class="muted">${T.noWatch}</p>`}
    ${others.length ? `<h2>${T.others}</h2>${others.slice(0, RUNS_SHOWN).map(r => `
      <div class="card row${FINISHED.includes(r.status) ? " finished" : ""}"><div class="grow"><b>${esc(r.thread)}</b>
        <div class="muted small">${esc(r.source)} · ${r.corrections} correction(s) · ${costTag(r.cost, r.unbilled_usd, false)}${
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
  // In the bar of a check, whose panel of options scrolls and would clip it: the bubble is placed on the screen
  if (t.closest(".check-bar")) {
    const r = t.getBoundingClientRect();
    t.classList.add("fixed");
    t.classList.remove("below");
    t.style.setProperty("--tip-fx", `${Math.max(8, Math.min(r.left / zoom - 8, room - width - 8))}px`);
    t.style.setProperty("--tip-fbottom", `${(window.innerHeight - r.top) / zoom + 8}px`);
  }
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
        <div class="header"><b>${C.askTitle}</b> <span class="badge attention">${costHtml("chapters", `≈ ${dollars(d.usd)}`)}</span></div>
        <p class="muted small">${C.askWhat}</p>
        <p><button id="ask">${C.ask(costHtml("chapters", `≈ ${dollars(d.usd)}`))}</button> <span class="error-text small" id="ask-error"></span></p>
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
    } catch (e) { b.disabled = false; b.innerHTML = C.ask(costHtml("chapters", `≈ ${dollars(d.usd)}`)); failed("#ask-error", e); }
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
// Its line of usage, its price at the end said like a check's: on a subscription, what it is worth, struck through
const usageHtml = r => {
  const line = T.usageLine(r.usage), at = line.lastIndexOf(" ≈ ");
  return !(r.unbilled_usd > 0) || at < 0 ? esc(line) : `${esc(line.slice(0, at))} ${costTag(r.cost, r.unbilled_usd, false)}`;
};
async function viewRun(thread) {
  const r = await api(`/api/runs/${encodeURIComponent(thread)}`);
  const name = r.mode === "mirror" ? T.pairs.runTitle : r.source || thread;
  const title = `<h1>${esc(name)} ${badge(r.status)}</h1>
    <p class="subtitle">${r.as_of && !r.mode ? `${T.watchUpTo(r.as_of)} · ` : ""}${usageHtml(r)}</p>`;
  if (r.status === "running") return viewRunning(r, title);
  if (r.status === "review") return viewReview(r, title);
  if (r.status === "publish") return viewPublish(r, title);
  if (r.status === "retouch") return viewRetouch(r, title);
  if (r.status === "translation") return viewTranslation(r, title);
  viewEnd(r, title);
}

function viewRunning(r, title) {
  const doneSteps = new Set(r.job.events.map(e => e.node));
  const first = r.job.action === "fix" ? "propose" : { run: "collect", review: "apply", retouch: "retouch", mirror: "mirror", translation: "translation", publish: "publish", recheck: "audits", retranslate: "mirror", resume: null }[r.job.action];
  const steps = r.steps.slice(first ? r.steps.indexOf(first) : 0);
  const cost = r.job.events.reduce((m, e) => e.cost ?? m, 0);
  let unbilled = r.job.events.reduce((m, e) => e.unbilled ?? m, 0);
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
    $("#progress").innerHTML = T.progress(min, costTag(cost, unbilled, false));
  };
  update(cost);
  source = new EventSource(`/api/runs/${encodeURIComponent(r.thread)}/events`);
  source.onmessage = ev => { const e = JSON.parse(ev.data); doneSteps.add(e.node); unbilled = e.unbilled ?? unbilled; update(e.cost ?? cost); };
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

// The texts retouched in the review, by run and correction: kept while the page is open, sent with the review
const RETOUCH = {};
const mineOf = (r, id) => RETOUCH[r.thread]?.[id];

// --- The passages a run changed, highlighted in an editor -----------------------------------------------------------
// A text area cannot colour part of its text: a layer behind it holds the same text, with the same font, padding,
// width and wrapping, its passages in <mark>; the text area, transparent, is typed in as usual (undo, selection,
// spelling). The layer follows its size (the page's zoom, the browser's, a resize), its scrolling and its typing.
// What a passage adds when it only adds (a sentence after a paragraph): that part alone
const addedPart = (before, after) => after.length > before.length && after.startsWith(before) ? after.slice(before.length) : after;
// Where the passages are in a text: each one whole, else its lines long enough to be found again (a passage typed over)
function passageRanges(text, passages) {
  const found = [];
  for (const p of passages) {
    const whole = String(p || "").trim();
    if (!whole) continue;
    const at = text.indexOf(whole);
    if (at >= 0) { found.push([at, at + whole.length]); continue; }
    for (const line of whole.split("\n").map(l => l.trim()).filter(l => l.length >= 12)) {
      const i = text.indexOf(line);
      if (i >= 0) found.push([i, i + line.length]);
    }
  }
  found.sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const r of found) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1] + 1) last[1] = Math.max(last[1], r[1]); else merged.push([...r]);
  }
  return merged;
}
// Every editor's passages in one highlight of the page (CSS Custom Highlight API), its colour in style.css
const HL_RANGES = new Map();
function hlRefresh() {
  for (const [layer] of HL_RANGES) if (!layer.isConnected) HL_RANGES.delete(layer);  // an editor closed, a page left
  CSS.highlights.set("vw-passage", new Highlight(...[...HL_RANGES.values()].flat()));
}
const HL_COPY = ["fontFamily", "fontSize", "fontWeight", "fontStyle", "lineHeight", "letterSpacing", "wordSpacing", "tabSize",
  "textIndent", "textTransform", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "whiteSpace", "overflowWrap",
  "wordBreak", "direction", "textAlign", "fontVariant", "fontStretch", "fontKerning", "fontFeatureSettings",
  "fontVariationSettings", "hyphens", "textRendering", "lineBreak"];
function highlightEditor(t, passages, nav) {
  const wrap = document.createElement("div"), back = document.createElement("div");
  back.style.backgroundColor = getComputedStyle(t).backgroundColor;  // read before the text area turns transparent
  wrap.className = "hl-wrap";
  back.className = "hl-back";
  back.setAttribute("aria-hidden", "true");
  if (t.lang) back.lang = t.lang;  // the lines break by the rules of the text's language (French spaces before « : ; ? ! »)
  t.parentNode.insertBefore(wrap, t);
  wrap.append(back, t);
  let list = passages, frame = 0, current = -1;
  const place = () => {
    const cs = getComputedStyle(t);
    HL_COPY.forEach(k => { back.style[k] = cs[k]; });
    // The same box as the text area: its whole width (100% of the wrapper, to the fraction of a pixel), its borders
    // (transparent), its scroll bar when it has one. A box narrower by the bar, even to the pixel, wraps some lines
    // elsewhere than a text area does.
    back.style.top = `${t.offsetTop}px`;
    back.style.left = `${t.offsetLeft}px`;
    back.style.width = "100%";
    back.style.height = `${t.offsetHeight}px`;
    back.style.borderStyle = "solid";
    back.style.borderColor = "transparent";
    ["Top", "Right", "Bottom", "Left"].forEach(side => { back.style[`border${side}Width`] = cs[`border${side}Width`]; });
    back.style.overflowY = t.scrollHeight > t.clientHeight + 1 ? "scroll" : "hidden";
    back.scrollTop = t.scrollTop;
    back.scrollLeft = t.scrollLeft;
  };
  // The passages' places in the layer: ranges of its one text (CSS highlights), or its <mark> where the API is missing
  let spans = [];
  const said = () => {
    if (!nav) return;
    const n = spans.length;
    nav.hidden = !n;
    nav.querySelector("[data-hl-count]").textContent = n ? T.hl.count(Math.max(0, current) + 1, n) : "";
  };
  const draw = () => {
    const text = t.value, found = passageRanges(text, list);
    // A text ending with a line break: the text area shows an empty last line, which a layer shows only when told
    const end = text.endsWith("\n") ? "\n" : "";
    if (window.CSS?.highlights && window.Highlight) {
      back.textContent = text + end;
      const node = back.firstChild;
      spans = node ? found.map(([a, b]) => { const r = new Range(); r.setStart(node, a); r.setEnd(node, b); return r; }) : [];
      HL_RANGES.set(back, spans);
      hlRefresh();
    } else {
      let html = "", pos = 0;
      for (const [a, b] of found) { html += `${esc(text.slice(pos, a))}<mark>${esc(text.slice(a, b))}</mark>`; pos = b; }
      back.innerHTML = `${html}${esc(text.slice(pos))}${end}`;
      spans = [...back.querySelectorAll("mark")];
    }
    place();
    said();
  };
  const later = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(draw); };
  // A passage: brought into view in the text area (a few lines above it), the cursor at its start
  const go = i => {
    if (!spans.length) return;
    current = (i + spans.length) % spans.length;
    // Its top in the layer's own pixels: measured on the screen, then brought back from the page's zoom
    const box = back.getBoundingClientRect(), scale = box.height / (back.clientHeight || 1) || 1;
    const top = (spans[current].getBoundingClientRect().top - box.top) / scale + back.scrollTop;
    t.scrollTop = Math.max(0, top - 3 * (parseFloat(getComputedStyle(t).lineHeight) || 20));
    const start = passageRanges(t.value, list)[current]?.[0] ?? 0;
    t.focus({ preventScroll: true });
    t.setSelectionRange(start, start);
    place();
    said();
  };
  t.addEventListener("input", later);
  t.addEventListener("scroll", () => { back.scrollTop = t.scrollTop; back.scrollLeft = t.scrollLeft; });
  new ResizeObserver(later).observe(t);
  window.addEventListener("resize", later);
  if (nav) {
    nav.querySelector("[data-hl-prev]").onclick = () => go(current - 1);
    nav.querySelector("[data-hl-next]").onclick = () => go(current + 1);
  }
  draw();
  return { go, draw, set: p => { list = p; current = -1; draw(); } };
}
const hlNav = () => `<span class="hl-nav" hidden><button type="button" class="small-button" data-hl-prev title="${esc(T.hl.prev)}">◀</button>
  <span class="small muted" data-hl-count></span><button type="button" class="small-button" data-hl-next title="${esc(T.hl.next)}">▶</button></span>`;

// A change, as the review shows it: what is added after the text kept, when it only adds (a sentence after a
// paragraph, a footnote after another); else the text before and after, word by word
const changeView = (current, text) => {
  if (current && text.length > current.length && text.startsWith(current)) {
    const added = text.slice(current.length).replace(/^\n+/, "");
    const notes = added.split("\n").filter(l => l.trim()).every(l => /^\[\^[^\]]+\]:/.test(l));
    const tail = current.length > 110 ? `…${current.slice(-100).trimStart()}` : current;
    return `<p class="anchor muted small">${T.addedAfter} « ${esc(tail)} »</p>
      <div class="diff after${notes ? " notes" : ""}" lang="fr">${notes ? `<span class="muted">${T.notesAdded}</span>` : ""}${esc(added)}</div>`;
  }
  const [before, after] = wordDiff(current, text);
  return `<div class="diff before" lang="fr">${before}</div>
    <div class="diff after" lang="fr">${after || `<span class="muted">${T.removedWhole}</span>`}</div>`;
};

function correctionCard(c, r) {
  const valid = c.check === "ok";
  const mine = mineOf(r, c.id), text = mine ?? c.proposed;
  // Where it comes from is said once, by the block of its lead (viewReview); a correction without one says it here
  const sources = (c.item_ids || [c.item_id]).filter(id => !r.items[id]?.shown).map(id => r.items[id]).filter(Boolean)
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
      <div data-diff="${c.id}">${changeView(c.current, text)}</div>
      ${c.retouchable ? `<div class="retouch" data-retouch="${c.id}" ${mine === undefined ? "hidden" : ""}>
        <p class="muted small">${T.retouchHelp}</p>
        <textarea data-text="${c.id}" lang="fr" spellcheck="true">${esc(text)}</textarea>
        <p class="small"><span data-retouch-state="${c.id}"></span>
          <button type="button" class="small-button" data-retouch-back="${c.id}">${T.retouchBack}</button></p></div>` : ""}
      <div class="muted small">${sources ? `${T.from} ${sources} · ` : ""}${c.source_url ? `${extLink(c.source_url, "source")}` : ""}
        ${c.retouchable ? ` · <button type="button" class="small-button" data-retouch-open="${c.id}"${mine === undefined ? "" : " hidden"}>✎ ${T.retouch}</button>` : ""}</div>
    </div>
  </div>`;
}

function viewReview(r, title) {
  const num = id => Number(id.slice(1));
  const groups = {};
  for (const c of [...r.corrections].sort((a, b) => num(a.group) - num(b.group) || num(a.id) - num(b.id)))
    (groups[c.group] ||= []).push(c);
  const broken = new Set(r.corrections.filter(c => c.check !== "ok").map(c => c.group));
  // The groups under the lead of their first correction, the leads in their order (F1, F2…); a lead says where it
  // comes from once: its number and title on the check's page, its source, the English text the run was given
  const byLead = new Map();
  for (const [g, cs] of Object.entries(groups)) {
    const k = (cs[0].item_ids || [cs[0].item_id])[0] || "";
    if (!byLead.has(k)) byLead.set(k, []);
    byLead.get(k).push([g, cs]);
  }
  const leadOrder = [...byLead.keys()].sort((a, b) => (num(a) || 1e9) - (num(b) || 1e9));
  leadOrder.forEach(k => { if (r.items[k]) r.items[k].shown = true; });
  const groupBlock = ([g, cs]) => cs.length > 1
    ? `<div class="group"><label class="group-head"><input type="checkbox" data-group-box="${g}" aria-label="${esc(T.group(g))}">
        <b>${T.groupLinked(cs.length)}</b> <span class="muted small">${broken.has(g) ? T.groupLeftOut : T.groupWhy}</span></label>
        ${cs.map(c => correctionCard(c, r)).join("")}</div>`
    : correctionCard(cs[0], r);
  const leadBlock = k => {
    const i = r.items[k], gs = byLead.get(k);
    if (!i) return gs.map(groupBlock).join("");
    const cs = gs.flatMap(([, x]) => x), pages = new Set(cs.map(c => c.page)).size;
    const name = i.name ? esc(i.name) : i.url ? extLink(i.url, esc(i.title)) : esc(i.title);
    return `<section class="lead-block">
      <div class="lead-head">${i.n ? `<span class="muted small">${T.leadN(i.n)}</span>` : ""}<b>${name}</b>
        <span class="badge neutral">${T.leadCount(cs.length, pages)}</span></div>
      ${i.name ? `<p class="muted small">${i.url ? `${T.leadSource}${T.colon}${extLink(i.url, esc(shortUrl(i.url)))} · ` : ""}${
        i.verification ? `<a href="#/check/${encodeURIComponent(i.verification)}">${T.seeCheck}</a>` : ""}</p>
        <details class="sent"><summary class="small muted">${T.verif.sentText}</summary><p class="small muted">${esc(i.title)}</p></details>` : ""}
      ${gs.map(groupBlock).join("")}</section>`;
  };
  const figures = [Object.values(r.triage).reduce((a, b) => a + b, 0), r.triage.correct, r.corrections.length, r.additions.length];
  page.innerHTML = `${title}
    <div class="figures">${figures.map((n, i) => `<div><b>${n}</b>${T.reviewFigures[i]}</div>`).join("")}</div>
    ${r.reading?.mode === "chapters" ? `<p class="banner small">${T.byChapter(r.reading.tokens, r.reading.budget)}</p>` : ""}
    ${r.mode === "add" ? `<div class="card notice"><p><strong>${T.noNewPage}</strong> ${T.pagesToWrite(r.pages_to_write.length)}</p>
      ${r.pages_to_write.length ? `<ul>${r.pages_to_write.map(p => `<li><strong>${esc(p.id)}</strong> ${esc(p.what)}<br><span class="muted small">${esc(p.lead)}</span></li>`).join("")}</ul>` : ""}</div>
    ${r.unchanged.length ? `<div class="card notice unchanged"><p><strong>${T.unchanged(r.unchanged.length)}</strong></p>
      <ul>${r.unchanged.map(u => { const i = r.items[u.id] || {}; return `<li><strong>${i.n ? T.leadN(i.n) : esc(u.id)}${i.name ? ` · ${esc(i.name)}` : ""}</strong><br>
        <span class="small">${esc(u.why)}</span><details class="sent"><summary class="small muted">${T.verif.sentText}</summary><p class="small muted">${esc(u.lead)}</p></details></li>`; }).join("")}</ul></div>` : ""}` : ""}
    <h2>${T.corrections}</h2>
    <p class="muted small">${T.reviewHelp}</p>
    ${leadOrder.map(leadBlock).join("") || `<p class="muted">${T.noCorrection}</p>`}
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
  // A group of several corrections is ticked by its own box (its members' boxes are hidden): one choice
  const groupBoxes = [...page.querySelectorAll("[data-group-box]")];
  const members = g => boxes.filter(o => o.dataset.group === g);
  const count = () => {
    const n = boxes.filter(i => i.checked).length;
    $("#apply").textContent = T.applyN(n);
    $("#apply").disabled = n === 0;
    groupBoxes.forEach(b => { b.checked = members(b.dataset.groupBox).every(o => o.checked); b.disabled = broken.has(b.dataset.groupBox); });
  };
  boxes.forEach(i => i.onchange = () => {
    boxes.filter(o => o.dataset.group === i.dataset.group && !o.disabled).forEach(o => o.checked = i.checked);
    count();
  });
  groupBoxes.forEach(b => b.onchange = () => {
    members(b.dataset.groupBox).filter(o => !o.disabled).forEach(o => { o.checked = b.checked; });
    count();
  });
  count();
  const send = async (accept, edits = {}) => {
    page.querySelectorAll(".bar button").forEach(b => b.disabled = true);
    await api(`/api/runs/${encodeURIComponent(r.thread)}/review`, { accept, edits });
    delete RETOUCH[r.thread];
    route();
  };
  bindRetouches(r, boxes);
  const edits = () => Object.fromEntries(Object.entries(RETOUCH[r.thread] || {})
    .filter(([id, text]) => text !== r.corrections.find(c => c.id === id)?.proposed));
  $("#apply").onclick = () => send(boxes.filter(i => i.checked).map(i => i.dataset.id), edits());
  $("#nothing").onclick = () => confirm(T.confirmNothing) && send("none");
}

// « Retouch » on the cards of a review: the text follows the typing in the diff, the free checks are asked a moment
// after the last key (POST /api/runs/<run>/retouch), and a retouched correction is ticked with its group
function bindRetouches(r, boxes) {
  const mine = RETOUCH[r.thread] ||= {};
  const proposal = id => r.corrections.find(c => c.id === id);
  const timers = {};
  const show = (id, text) => { page.querySelector(`[data-diff="${id}"]`).innerHTML = changeView(proposal(id).current, text); };
  const ask = id => {
    clearTimeout(timers[id]);
    const state = page.querySelector(`[data-retouch-state="${id}"]`);
    if (mine[id] === undefined || mine[id] === proposal(id).proposed) { state.innerHTML = ""; return; }
    state.innerHTML = `<span class="muted">${T.retouchChecking}</span>`;
    timers[id] = setTimeout(async () => {
      const said = await api(`/api/runs/${encodeURIComponent(r.thread)}/retouch`, { edits: { [id]: mine[id] } }).catch(e => ({ [id]: { check: e.message } }));
      const x = said[id] || {};
      state.innerHTML = `<span class="badge ${x.check === "ok" ? "ok" : "error"}">${x.check === "ok" ? T.retouched : esc(T.retouchProblem(x.check))}</span>${
        x.warning ? ` <span class="small">⚠️ ${T.sourceMissing}${T.colon}${esc(x.warning)}</span>` : ""}`;
    }, 500);
  };
  const fit = t => { t.style.height = "auto"; t.style.height = `${t.scrollHeight + 4}px`; };  // the whole text, no inner scroll
  const tick = id => {
    const box = boxes.find(b => b.dataset.id === id);
    if (box && !box.disabled && !box.checked) { box.checked = true; box.onchange(); }
  };
  page.querySelectorAll("[data-retouch-open]").forEach(b => b.onclick = () => {
    const id = b.dataset.retouchOpen;
    mine[id] = mine[id] ?? proposal(id).proposed;
    page.querySelector(`[data-retouch="${id}"]`).hidden = false;
    b.hidden = true;
    fit(page.querySelector(`[data-text="${id}"]`));
    page.querySelector(`[data-text="${id}"]`).focus();
  });
  page.querySelectorAll("[data-text]").forEach(t => {
    const id = t.dataset.text;
    t.oninput = () => { mine[id] = t.value; show(id, t.value); tick(id); ask(id); fit(t); };
    if (!t.closest("[hidden]")) fit(t);
    ask(id);
  });
  page.querySelectorAll("[data-retouch-back]").forEach(b => b.onclick = () => {
    const id = b.dataset.retouchBack;
    delete mine[id];
    page.querySelector(`[data-text="${id}"]`).value = proposal(id).proposed;
    page.querySelector(`[data-retouch="${id}"]`).hidden = true;
    page.querySelector(`[data-retouch-open="${id}"]`).hidden = false;
    show(id, proposal(id).proposed);
    ask(id);
  });
}

// --- The pause to retouch the pages of the branch (H3): lend the folder to Obsidian, or edit here ---------------
async function viewRetouch(r, title) {
  const R = T.retouchPause, at = `/api/runs/${encodeURIComponent(r.thread)}`;
  const f = await api(`${at}/folder`).catch(e => ({ error: e.message, changes: [] }));
  const lent = f.lent_to === r.thread, pages = r.pause?.pages || [];
  const folderCard = f.error ? `<p class="error-text">${esc(f.error)}</p>`
    : lent ? `<p>${R.lentNow(esc(f.path))}</p><p><button id="take-back">${R.takeBack}</button>${tip(R.takeBackHelp)}</p>`
    : f.lent_to ? `<p class="attention-text">${R.lentOther(esc(f.lent_to))}</p>`
    : f.blocked ? `<p class="attention-text">${R.blocked(esc(f.blocked))}</p>`
    : f.changes.length ? `<p>${R.dirty(f.changes.length)}</p><ul>${f.changes.map(c => `<li><code>${esc(c)}</code></li>`).join("")}</ul>
        <p class="muted small">${R.setAsideHelp}</p><p><button id="lend" data-aside="1">${R.setAside}</button></p>`
    : `<p><button id="lend">${R.lend}</button>${tip(R.lendHelp(f.path))}</p>`;
  // Each page: open it in the editor below, or in Obsidian once the folder is lent (before, Obsidian shows main)
  const vaultName = (f.path || "").split(/[\\/]/).filter(Boolean).pop() || "";
  const pageRow = p => `<li><code>${esc(p)}</code> <button type="button" class="small-button" data-open-here="${esc(p)}">${R.openHere}</button>
    ${lent ? `<a class="small" href="${obsidian(vaultName, p)}">${R.openObsidian}</a>` : `<a class="muted small" href="#" data-to-lend title="${esc(R.obsidianLater)}">${R.openObsidian}</a>`}</li>`;
  page.innerHTML = `${title}
    <div class="card"><p>${R.intro((r.applied || []).length, esc(r.branch || ""))}</p>
      ${pages.length ? `<p class="small"><b>${R.pages}</b></p><ul class="retouch-pages">${pages.map(pageRow).join("")}</ul>
        ${lent ? "" : `<p class="muted small">${R.obsidianFirst(`<a href="#" data-to-lend>${R.lendFirst}</a>`)}</p>`}` : ""}</div>
    <h2>${R.obsidian}</h2>
    <div class="card" id="folder-card">${folderCard}${lent ? "" : `<p class="muted small">${R.whyLend}</p>`}<p class="error-text small" id="lend-error"></p></div>
    <h2>${R.here}</h2>
    <div class="card" id="here"><p class="muted small">${R.hereHelp(lent)}</p>
      <p class="tick-row"><select id="page-pick">${pages.map(p => `<option>${esc(p)}</option>`).join("")}</select>
        <input id="page-other" type="text" placeholder="${esc(R.other)}" spellcheck="false">
        <button type="button" id="page-open">${R.open}</button></p>
      <div id="editor" hidden><p class="small hl-head"><code id="page-name"></code> <span class="badge attention" id="page-dirty" hidden>${R.unsaved}</span> ${hlNav()}</p>
        <textarea id="page-text" spellcheck="true"></textarea>
        <p class="muted small">${R.undoHelp}</p>
        <p class="tick-row"><button type="button" id="page-save" disabled>${R.save}</button>
          <button type="button" id="page-revert">${R.close}</button> <span class="small" id="page-said"></span></p></div></div>
    <p class="error-text" id="done-error"></p>
    <div class="bar"><button id="skip">${R.skip}</button><button class="primary" id="done">${R.done}</button></div>`;
  let open = "";
  if ($("#take-back")) $("#take-back").onclick = async () => {
    $("#take-back").disabled = true;
    try { await api(`${at}/folder/back`, {}); route(); }
    catch (e) { $("#lend-error").textContent = e.message; $("#take-back").disabled = false; }
  };
  if ($("#lend")) $("#lend").onclick = async () => {
    $("#lend").disabled = true;
    try { await api(`${at}/folder`, { set_aside: !!$("#lend").dataset.aside }); route(); }
    catch (e) { $("#lend-error").textContent = e.message; $("#lend").disabled = false; }
  };
  // The editor: the text as last saved is kept, so that what is not saved is said, and can be cancelled
  let saved = "";
  const dirty = () => !!open && $("#page-text").value !== saved;
  const said = () => {
    $("#page-dirty").hidden = !dirty();
    $("#page-save").disabled = !dirty();
    $("#page-revert").textContent = dirty() ? R.revert : R.close;  // nothing to cancel: it closes the page
  };
  let marked = null;  // the passages highlighted in the editor (highlightEditor), made with its first page
  const load = async path => {
    if (!path || (dirty() && !confirm(R.confirmLeave))) return;
    try {
      const p = await api(`${at}/page?path=${encodeURIComponent(path)}`);
      open = p.path;
      saved = p.text;
      $("#page-text").value = p.text;
      $("#page-name").textContent = p.path;
      $("#editor").hidden = false;
      $("#page-said").textContent = "";
      $("#page-text").style.height = "auto";
      $("#page-text").style.height = `${Math.min(window.innerHeight * 0.7, $("#page-text").scrollHeight + 4)}px`;
      // What the corrections applied to this page, in green; the editor opened at the first
      const passages = (r.corrections || []).filter(c => (r.applied || []).includes(c.id) && c.page === p.path).map(c => addedPart(c.current, c.proposed));
      marked ||= highlightEditor($("#page-text"), passages, $("#editor .hl-nav"));
      marked.set(passages);
      marked.go(0);
      said();
    } catch (e) { $("#page-said").textContent = e.message; $("#editor").hidden = false; }
  };
  $("#page-open").onclick = () => load($("#page-other").value.trim() || $("#page-pick").value);
  page.querySelectorAll("[data-open-here]").forEach(b => b.onclick = async () => {
    $("#page-pick").value = b.dataset.openHere;
    $("#page-other").value = "";
    await load(b.dataset.openHere);
    $("#here").scrollIntoView({ block: "start", behavior: "smooth" });
  });
  $("#page-text").oninput = said;
  // « Lend your folder first »: the button comes into view and glows for a moment (the card, when it has none)
  page.querySelectorAll("[data-to-lend]").forEach(a => a.onclick = e => {
    e.preventDefault();
    const target = $("#lend") || $("#folder-card");
    target.scrollIntoView({ block: "center", behavior: "smooth" });
    target.classList.remove("flash");
    void target.offsetWidth;  // the glow starts again on a second click
    target.classList.add("flash");
    setTimeout(() => target.classList.remove("flash"), 1800);
    if (target.id === "lend") setTimeout(() => target.focus({ preventScroll: true }), 400);
  });
  $("#page-save").onclick = async () => {
    if (!open) return;
    try {
      await api(`${at}/page`, { path: open, text: $("#page-text").value });
      saved = $("#page-text").value;
      $("#page-said").textContent = R.saved;
      said();
    } catch (e) { $("#page-said").textContent = e.message; }
  };
  // Back to the text as last saved: typed over (not set), so that Ctrl+Z can still bring the changes back
  $("#page-revert").onclick = () => {
    if (!dirty()) {  // nothing changed: the page is closed
      open = saved = "";
      $("#editor").hidden = true;
      return;
    }
    const t = $("#page-text");
    t.focus();
    t.select();
    if (!document.execCommand?.("insertText", false, saved)) t.value = saved;
    t.setSelectionRange(0, 0);
    t.scrollTop = 0;
    $("#page-said").textContent = R.reverted;
    said();
  };
  const finish = async keep => {
    page.querySelectorAll(".bar button").forEach(b => b.disabled = true);
    try { await api(`${at}/retouched`, { keep }); route(); }
    catch (e) { $("#done-error").textContent = e.message; page.querySelectorAll(".bar button").forEach(b => b.disabled = false); }
  };
  $("#done").onclick = () => (!dirty() || confirm(R.confirmLeave)) && finish(true);
  $("#skip").onclick = () => (!lent && !open) || confirm(R.confirmSkip) ? finish(false) : null;
}

// A banner on every page while the guide's folder is lent to a run, or something set aside is not put back yet
async function asideBanner() {
  const list = await api("/api/folder/aside").catch(() => []);
  document.querySelector("#aside-banner")?.remove();
  if (!list.length) return;
  const R = T.retouchPause, x = list[0];
  const div = document.createElement("p");
  div.id = "aside-banner";
  div.className = "banner";
  div.innerHTML = `${esc(R.banner(x.thread, x.lent, x.aside.length))} <a href="#/run/${encodeURIComponent(x.thread)}">${R.see}</a>${
    x.lent ? "" : ` <button type="button" class="small-button" id="put-back">${R.putBack}</button>`}`;
  page.prepend(div);
  const b = div.querySelector("#put-back");
  if (b) b.onclick = async () => { try { await api(`/api/folder/aside/${encodeURIComponent(x.thread)}`, {}); asideBanner(); } catch (e) { div.append(` ${e.message}`); } };
}

// --- The source beside its translation (graph.mirror keeps the pairs); editable at the pause of a sync ---------
const TRANSLATED = {};  // the translations retouched, by run and "<mirror page>#<n>", kept while the page is open

function pairsBlock(r, editable) {
  const P = T.pairs, mine = TRANSLATED[r.thread] ||= {};
  return `${r.mirror_pairs.filter(x => x.target.length || x.problem).map(x => {
    const rows = Math.max(x.source.length, x.target.length);
    return `<div class="card pair-page"><div class="header"><code>${esc(x.page)}</code> → <code>${esc(x.mirror)}</code></div>
      ${x.problem ? `<p class="small attention-text">${P.problem}${T.colon}${esc(x.problem)}</p>` : ""}
      ${Array.from({ length: rows }, (_, i) => {
        const src = x.source[i], tgt = x.target[i], key = `${x.mirror}#${i}`;
        const [sb, sa] = src ? wordDiff(src[0], src[1]) : ["", ""];
        const text = mine[key] ?? tgt?.[1];
        const [tb, ta] = tgt ? wordDiff(tgt[0], text) : ["", ""];
        return `<div class="pair">
          <div><p class="muted small">${P.source}</p>${src ? `<div class="diff before" lang="fr">${sb}</div><div class="diff after" lang="fr">${sa || `<span class="muted">${P.removed}</span>`}</div>` : `<p class="muted small">—</p>`}</div>
          <div><p class="muted small">${P.target}${tgt?.[2] ? ` · <span class="badge ok">${P.retouched}</span>` : ""}</p>${tgt ? `<div class="diff before" lang="en">${tb}</div>
            <div class="diff after" lang="en" data-pair-after="${esc(key)}">${ta || `<span class="muted">${P.removed}</span>`}</div>
            ${editable && tgt[1].trim() ? `<textarea data-pair="${esc(key)}" lang="en" spellcheck="true">${esc(text)}</textarea>` : ""}` : `<p class="muted small">${P.none}</p>`}</div>
        </div>`;
      }).join("")}</div>`;
  }).join("")}`;
}

function viewTranslation(r, title) {
  const P = T.pairs, mine = TRANSLATED[r.thread] ||= {};
  page.innerHTML = `${title}
    <h2>${P.title}</h2>
    <p class="muted small">${P.intro} ${P.edit}</p>
    ${pairsBlock(r, true)}
    <div class="bar"><button class="primary" id="ok"></button></div>`;
  const target = key => { const [page, n] = [key.slice(0, key.lastIndexOf("#")), Number(key.slice(key.lastIndexOf("#") + 1))];
    return r.mirror_pairs.find(x => x.mirror === page).target[n]; };
  const changed = () => Object.entries(mine).filter(([key, text]) => text !== target(key)[1]);
  const label = () => { $("#ok").textContent = P.ok(changed().length); };
  page.querySelectorAll("[data-pair]").forEach(t => {
    const fit = () => { t.style.height = "auto"; t.style.height = `${t.scrollHeight + 4}px`; };
    fit();
    t.oninput = () => {
      const key = t.dataset.pair, tgt = target(key);
      mine[key] = t.value;
      page.querySelector(`[data-pair-after="${CSS.escape(key)}"]`).innerHTML = wordDiff(tgt[0], t.value)[1];
      fit();
      label();
    };
  });
  label();
  $("#ok").onclick = async () => {
    $("#ok").disabled = true;
    await api(`/api/runs/${encodeURIComponent(r.thread)}/translation`, { edits: Object.fromEntries(changed()) });
    delete TRANSLATED[r.thread];
    route();
  };
}

async function viewPublish(r, title) {
  const P = T.pub, p = { mirror_problems: [], link_problems: [], ...r.pause }, at = `/api/runs/${encodeURIComponent(r.thread)}`;
  const linksChecked = p.link_problems !== null;   // null: the guide declares no source audit
  if (!linksChecked) p.link_problems = [];
  const diff = await api(`${at}/diff`).catch(() => "");
  const color = l => l.startsWith("+") && !l.startsWith("+++") ? "plus" : l.startsWith("-") && !l.startsWith("---") ? "minus" : "";
  const titleOf = path => (r.titles || {})[path] || path;
  // The pages changed, each with its mirrors (graph.mirror keeps the source beside its translation)
  const pages = [];
  for (const x of r.mirror_pairs || []) {
    let page = pages.find(y => y.page === x.page);
    if (!page) pages.push(page = { page: x.page, mirrors: [] });
    page.mirrors.push(x);
  }
  const anchor = path => `pub-${pages.findIndex(x => x.page === path)}`;
  const toPage = path => pages.some(x => x.page === path)
    ? `<a href="#" data-to-page="${esc(path)}">${esc(titleOf(path))}</a>` : `<code>${esc(path)}</code>`;
  // « Before publishing »: what was checked, one line each
  const row = (icon, cls, name, what) => `<div class="pub-row"><span class="pub-i ${cls}">${icon}</span><b>${name}</b><div>${what}</div></div>`;
  const links = p.link_problems.map(x => {
    const m = x.match(/^(NEW )?(.*?): (https?:\/\/\S+) \((.*)\)$/);
    if (!m) return `<li>${esc(x)}</li>`;
    const [, isNew, label, url, cited] = m;
    const why = label.startsWith("blocked") ? P.linkBlocked : P.linkDead(label);
    return `<li>${extLink(url, esc(shortUrl(url)))} <span class="badge neutral">${isNew ? P.linkNew : P.linkOld}</span><br>
      <span class="muted small">${why} ${P.citedBy} ${cited.split(", ").map(toPage).join(", ")}.</span></li>`;
  });
  const weight = r.weight?.before ? `${P.weight(kb(r.weight.before), kb(r.weight.after), signedKb(r.weight.after - r.weight.before))}${
    (r.weight.pages || []).length ? `<br><span class="muted small">${r.weight.pages.slice(0, 5).map(([x, d]) => `${toPage(x)} ${signedKb(d)}`).join(" · ")}</span>` : ""}` : "";
  const checks = [
    p.audit_ok === null ? row("–", "info-i", P.audits, T.notChecked)
      : p.audit_ok ? row("✓", "ok-i", P.audits, `OK <span class="muted small">${P.auditsWhat}</span>`)
      : row("✗", "bad-i", P.audits, `<span class="error-text">${T.auditsRed}</span><details><summary class="small">${P.log}</summary><pre>${esc(r.audit_log)}</pre></details>`),
    r.mode === "mirror" || r.mirrored.length || p.mirror_problems.length
      ? row(p.mirror_problems.length ? "!" : "✓", p.mirror_problems.length ? "warn-i" : "ok-i", P.translation,
        `${P.mirrored(r.mirrored.length)}${p.mirror_problems.length ? `<ul>${p.mirror_problems.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}`) : "",
    !linksChecked ? row("–", "info-i", P.links, T.linksNotChecked)
      : links.length ? row("!", "warn-i", P.linksToCheck(links.length), `<ul class="pub-links">${links.join("")}</ul>`)
      : row("✓", "ok-i", P.links, T.linksOk),
    weight ? row("ⓘ", "info-i", P.weightTitle, weight) : "",
  ].join("");
  // A page changed: one line folded (its title, its path, its passages, its buttons), open: source beside mirror
  const est = x => (r.retranslate_usd || {})[x.page];
  const price = x => est(x) != null ? `≈ ${dollars(est(x))}` : "";
  const pageBlock = (x, i) => {
    const passages = x.mirrors[0].source.length;
    return `<details class="pub-page" id="pub-${i}" data-page="${esc(x.page)}"${i === 0 && pages.length <= 3 ? " open" : ""}>
      <summary><span class="pub-name"><span class="pub-title">${esc(titleOf(x.page))}</span><code title="${esc(x.page)}">${esc(x.page)}</code></span>
        <span class="badge neutral">${P.passages(passages)}</span>
        <span class="pub-tools"><button type="button" class="small-button" data-correct="${i}">✎ ${P.correct}</button>
        <button type="button" class="small-button" data-again="${i}" title="${esc(`${P.again}${price(x) ? ` · ${costOf("mirror", price(x))}` : ""}`)}">↻ ${P.againShort}${
          price(x) ? ` ${costOf("mirror", price(x)) === T.subscription ? `<s class="worth">${price(x)}</s>` : esc(costOf("mirror", price(x)))}` : ""}</button></span></summary>
      <div class="pub-editor" data-editor="${i}" hidden></div>
      <div class="pub-pairs">${x.mirrors.map(m => Array.from({ length: Math.max(m.source.length, m.target.length) }, (_, k) => {
        const src = m.source[k], tgt = m.target[k];
        return `<div class="pair"><div><p class="muted small">${T.pairs.source}</p>${src ? changeView(src[0], src[1]) : `<p class="muted small">—</p>`}</div>
          <div><p class="muted small">${T.pairs.target} · <code>${esc(m.mirror)}</code></p>${tgt ? changeView(tgt[0], tgt[1]) : `<p class="muted small">${T.pairs.none}</p>`}</div></div>`;
      }).join("")).join("")}</div></details>`;
  };
  page.innerHTML = `${title}
    ${r.error ? `<p class="error-text"><b>${T.publishFailed}</b> ${esc(r.error)}</p>` : ""}
    <p class="small">${T.branchReady(esc(p.branch))}</p>
    <div class="card"><h3>${P.before}</h3><div class="pub-checks">${checks}</div></div>
    ${pages.length ? `<h2>${P.pagesTitle} <span class="muted small">· ${pages.length}</span></h2>
      <p class="small"><button type="button" class="small-button" id="unfold-pages">${P.unfoldAll}</button></p>
      ${pages.map(pageBlock).join("")}` : ""}
    <details${pages.length ? "" : " open"}><summary>${pages.length ? P.rawDiff : T.changes}</summary>
      <pre>${diff.split("\n").map(l => `<span class="${color(l)}">${esc(l)}</span>`).join("\n") || esc(p.diffstat)}</pre></details>
    <p class="error-text" id="pub-error"></p>
    <div class="bar">
      <button id="no">${T.doNotPublish}</button>
      <button class="primary" id="yes">${p.local ? T.keepLocal : T.publish}</button>
    </div>`;
  const send = async go => {
    page.querySelectorAll(".bar button").forEach(b => b.disabled = true);
    await api(`${at}/publish`, { go });
    route();
  };
  // Check again, or translate again: the run goes on, then comes back here with its checks up to date
  const again = async body => {
    page.querySelectorAll("button").forEach(b => b.disabled = true);
    try { await api(`${at}/publish`, body); route(); }
    catch (e) { $("#pub-error").textContent = e.message; page.querySelectorAll("button").forEach(b => b.disabled = false); }
  };
  $("#yes").onclick = () => send(true);
  $("#no").onclick = () => confirm(T.confirmNo) && send(false);
  if ($("#unfold-pages")) $("#unfold-pages").onclick = () => {
    const all = [...page.querySelectorAll(".pub-page")], open = !all.every(d => d.open);
    all.forEach(d => { d.open = open; });
  };
  // A page named above (its weight, a link cited): the page is opened, brought into view, and glows a moment
  page.querySelectorAll("[data-to-page]").forEach(a => a.onclick = e => {
    e.preventDefault();
    const d = $(`#${anchor(a.dataset.toPage)}`);
    d.open = true;
    d.scrollIntoView({ block: "start", behavior: "smooth" });
    d.classList.remove("flash"); void d.offsetWidth; d.classList.add("flash");
    setTimeout(() => d.classList.remove("flash"), 1800);
  });
  // « Translate again »: the page's translation starts over from the base (billed)
  page.querySelectorAll("[data-again]").forEach(b => b.onclick = e => {
    e.preventDefault(); e.stopPropagation();
    const x = pages[Number(b.dataset.again)];
    if (confirm(P.confirmAgain(titleOf(x.page), est(x) != null ? costOf("mirror", `≈ ${dollars(est(x))}`) : ""))) again({ action: "retranslate", pages: [x.page], fresh: true });
  });
  // « Correct »: the source page and its mirror side by side; saved, then checked again (or the French translated again)
  page.querySelectorAll("[data-correct]").forEach(b => b.onclick = async e => {
    e.preventDefault(); e.stopPropagation();
    const i = Number(b.dataset.correct), x = pages[i], box = page.querySelector(`[data-editor="${i}"]`), d = $(`#pub-${i}`);
    d.open = true;
    if (!box.hidden) return;
    const paths = [x.page, ...x.mirrors.map(m => m.mirror)];
    let texts;
    try { texts = await Promise.all(paths.map(path => api(`${at}/page?path=${encodeURIComponent(path)}`).then(t => t.text))); }
    catch (err) { $("#pub-error").textContent = err.message; return; }
    const saved = [...texts];
    box.hidden = false;
    box.innerHTML = `<p class="muted small">${P.correctHelp}</p>
      <div class="pair">${paths.map((path, k) => `<div><p class="muted small hl-head">${k ? T.pairs.target : T.pairs.source} · <code>${esc(path)}</code> ${hlNav()}</p>
        <textarea data-text-of="${k}" spellcheck="true" lang="${k ? "en" : "fr"}">${esc(texts[k])}</textarea></div>`).join("")}</div>
      <p class="muted small">${T.retouchPause.undoHelp}</p>
      <div class="pub-warn" hidden></div>
      <p class="tick-row"><button type="button" data-save>${P.saveCheck}</button> <button type="button" data-close>${T.retouchPause.close}</button></p>`;
    const areas = [...box.querySelectorAll("textarea")];
    areas.forEach(t => { t.style.height = `${Math.min(window.innerHeight * 0.6, t.scrollHeight + 4)}px`; });
    // Each text with the passages the run changed in green (the source's new text, the translation's), opened at the first
    areas.forEach((t, k) => {
      const passages = k ? x.mirrors[k - 1].target.map(([a, b]) => addedPart(a, b)) : x.mirrors[0].source.map(([a, b]) => addedPart(a, b));
      highlightEditor(t, passages, t.closest(".pair > div").querySelector(".hl-nav")).go(0);
    });
    const changed = () => areas.map((t, k) => t.value !== saved[k]);
    const said = () => {
      const c = changed();
      box.querySelector("[data-save]").disabled = !c.some(Boolean);
      box.querySelector("[data-close]").textContent = c.some(Boolean) ? T.retouchPause.revert : T.retouchPause.close;
    };
    areas.forEach(t => t.oninput = said);
    said();
    box.querySelector("[data-close]").onclick = () => {
      if (changed().some(Boolean)) { areas.forEach((t, k) => { t.focus(); t.select(); if (!document.execCommand?.("insertText", false, saved[k])) t.value = saved[k]; }); said(); return; }
      box.hidden = true; box.innerHTML = "";
    };
    box.querySelector("[data-save]").onclick = async () => {
      const c = changed();
      try { await Promise.all(paths.map((path, k) => c[k] ? api(`${at}/page`, { path, text: areas[k].value }) : null)); }
      catch (err) { $("#pub-error").textContent = err.message; return; }
      areas.forEach((t, k) => { saved[k] = t.value; });
      said();
      // The French corrected, its translation not: say it (the guide's checks would fail), offer to translate it
      if (c[0] && !c.slice(1).some(Boolean) && x.mirrors.length) {
        const w = box.querySelector(".pub-warn");
        w.hidden = false;
        w.innerHTML = `<span>⚠️ ${P.sourceOnly}</span>
          <button type="button" data-translate-mine>↻ ${P.againMine} ${costHtml("mirror", "")}</button>
          <button type="button" data-check-only>${P.checkOnly}</button>`;
        w.querySelector("[data-translate-mine]").onclick = () => again({ action: "retranslate", pages: [x.page], fresh: false });
        w.querySelector("[data-check-only]").onclick = () => again({ action: "recheck" });
        return;
      }
      again({ action: "recheck" });
    };
  });
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
// What a check cost: billed, or what its calls on a subscription are worth at list price, struck through (nothing is
// billed); a check that calls no model is free
let CHECKS_KIND = "";  // the kind the history of the checks is narrowed to ("": all)
const costTag = (cost, unbilled, free) => {
  const V = T.verif;
  const worth = unbilled > 0 ? `<span class="worth" title="${esc(V.listPriceTip)}"><s>${dollars(unbilled)}</s> <span class="sub-tag">${V.onSubscription}</span></span>` : "";
  if (cost > 0) return `${dollars(cost)}${worth ? ` + ${worth}` : ""}`;
  return worth || (free ? V.free : dollars(0));
};

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
  const price = o => o.model ? costHtml(o.id, o.usd == null ? V.unknown : `≈ ${dollars(est(o, "usd"))}`) : V.free;
  const origin = o => o.model && o.price_origin && o.usd != null && billedStep(o.id)
    ? ` <span class="muted small">${esc(T.priceOrigin(o.price_origin))}</span>` : "";
  // What is left to handle comes first; a new check is folded away while leads remain (it would find them again)
  const pending = verifs.filter(p => ["to-handle", "running"].includes(p.status));
  const remaining = pending.reduce((s, p) => s + p.counts.open, 0);
  // A card says what the check is (its kind, in colour; what it read), where it was started when not here, what it
  // cost or is worth at list price, then the runs its leads went to that still wait for something
  const kindOf = Object.fromEntries(options.map(o => [o.id, o.kind || "health"]));
  const short = c => {
    const t = titles[c] || c, i = t.indexOf(":");
    const s = i < 0 ? t : kindOf[c] === "news" ? t.slice(i + 1).trim() : t.slice(0, i).trim();
    return s.charAt(0).toUpperCase() + s.slice(1);
  };
  const cardTitle = p => {
    const k = p.kinds?.[0] || "health";
    if (p.checks.includes("links") && p.checks.length === 1) return `${esc(short("links"))} · ${V.nLinks(p.links?.length || 0)}`;
    return k === "health" && p.checks.length > 2 ? V.nChecks(p.checks.length) : p.checks.map(c => esc(short(c))).join(" · ");
  };
  const linkItem = l => `<li>${extLink(l.url, esc(l.title || shortUrl(l.url)))}${l.kind === "pdf" ? ' <span class="kindtag">PDF</span>' : ""}${
    l.title ? ` <span class="muted small">· ${esc(new URL(l.url).hostname.replace(/^www\./, ""))}</span>` : ""}</li>`;
  const linksList = p => !p.links?.length ? "" : `<ul class="check-links">${p.links.slice(0, 3).map(linkItem).join("")}</ul>${
    p.links.length > 3 ? `<details class="check-links-more"><summary class="small">${V.moreLinks(p.links.length - 3)}</summary><ul class="check-links">${p.links.slice(3).map(linkItem).join("")}</ul></details>` : ""}`;
  const WAITING = ["running", "review", "retouch", "translation", "publish", "stopped", "pr-open"];
  const runLine = ([t, r]) => `<div class="run-line small"><span class="badge attention">${esc(T.statuses[r.status] || r.status)}</span>
    <a href="${r.status === "pr-open" && r.pr_url ? esc(r.pr_url) : `#/run/${encodeURIComponent(t)}`}"${r.status === "pr-open" ? ' target="_blank" rel="noopener"' : ""}><button type="button" class="small-button">${
      r.status === "pr-open" ? T.merge() : T.buttons[r.status] || T.details}</button></a> <span class="muted">${esc(t)}</span></div>`;
  const checkCard = p => `<div class="card row check-item kind-${p.kinds?.[0] || "health"}${["handled", "clear"].includes(p.status) ? " finished" : ""}" data-kinds="${(p.kinds || []).join(" ")}"><div class="grow">
        <div class="check-top">${(p.kinds || []).map(k => `<span class="kind-tag ${k}">${V.checkKinds[k]}</span>`).join("")}<b>${cardTitle(p)}</b>${
          p.checks.length === 1 && p.checks[0] === "links" ? `<span class="from-tag">${V.fromReport}</span>` : ""}</div>
        ${(p.kinds?.[0] || "health") === "health" && p.checks.length > 2 ? `<div class="muted small">${p.checks.map(c => esc(short(c).toLowerCase())).join(", ")}</div>` : ""}
        ${linksList(p)}
        <div class="muted small">${costTag(p.cost, p.unbilled_usd, !p.checks.some(c => options.find(o => o.id === c)?.model))} · ${
          new Date(p.started * 1000).toLocaleString(lang, { dateStyle: "short", timeStyle: "short" })}</div>
        <div class="muted small">${V.counts(p.counts)}</div>
        ${Object.entries(p.runs || {}).filter(([, r]) => WAITING.includes(r.status)).map(runLine).join("")}</div>
        <div class="check-side">${checkBadge(p)}
        <a href="#/check/${encodeURIComponent(p.id)}"><button${p.status === "to-handle" ? ' class="primary"' : ""}>${p.status === "to-handle" ? V.handle : T.details}</button></a></div></div>`;
  // The history can be narrowed to one kind (kept while the page is open)
  const kindCount = k => older.filter(p => (p.kinds || []).includes(k)).length;
  const older = verifs.filter(p => !pending.includes(p));
  page.innerHTML = `
    <h1>${V.title}</h1>
    <p class="subtitle">${V.intro}</p>
    <p class="small"><a href="#/idea">${V.ideaLink}</a><br><a href="#/links">${V.linksLink}</a></p>
    ${pending.length ? `<h2>${V.toHandleTitle}</h2>${pending.map(checkCard).join("")}` : ""}
    <details class="new-check"${pending.length ? "" : " open"}><summary><h2>${V.newCheck}</h2></summary>
    ${remaining ? `<p class="attention-text">${V.warning(remaining)}</p>` : ""}
    <p class="tick-row"><button type="button" class="small-button" data-tick-checks="all">${V.tickAll}</button>
      <button type="button" class="small-button" data-tick-checks="none">${V.untickAll}</button>
      <button type="button" class="small-button" data-tick-checks="free">${V.onlyFree}</button></p>
    ${options.filter(o => !o.links_max).map(o => `<div class="card check-card"><label class="option">
      <input type="checkbox" data-check="${o.id}" ${(kept ? kept.checks.has(o.id) : !o.model) ? "checked" : ""}>
      <div>
        <div class="header"><b>${esc(o.title[lang])}</b>
          <span class="badge ${o.model ? "attention" : "ok"}">${price(o)}</span>${origin(o)}
          ${o.tokens ? `<span class="muted small">${V.tokens(o.tokens)}</span>` : ""}</div>
        <p class="muted small">${esc(o.what[lang])}</p>
        ${o.limit ? `<p class="small attention-text">${esc(o.limit[lang])}</p>` : ""}
        <p class="muted small">${esc(o.note[lang])}${o.needs.length ? ` · ${V.needs(o.needs.map(n => titles[n]).join(", "))}` : ""}</p>
      </div></label>${o.model ? `<div class="card-foot">${stepLine(o.id)}</div>` : ""}${o.chapters ? `<div class="card-foot chapters" data-chapters-of="${o.id}" hidden>
        <p class="muted small">${V.chapters(costHtml(o.id, `≈ ${dollars(est(o, "usd_chapter") || 0)}`))}</p>
        ${o.chapters.map(c => `<label><input type="checkbox" data-chapter="${esc(c.id)}" ${(kept ? kept.chapters.has(c.id) : c.explore) ? "checked" : ""}> ${esc(c.id)} <span class="muted small">(${c.pages} p., ${T.chapters.kb(Math.round(c.kb))})</span></label>`).join("")}
        <p class="small"><a href="#/chapters">${T.chapters.edit}</a></p>
      </div>` : ""}</div>`).join("")}
    <p><button class="primary" id="start"></button></p>
    </details>
    <h2>${V.history}</h2>
    ${older.length ? `<p class="kind-filters">${["", "health", "light", "news"].map(k => `<button type="button" class="chip${CHECKS_KIND === k ? " on" : ""}" data-kind-filter="${k}">${
      k ? V.checkKinds[k] : V.allKinds} <span class="muted">${k ? kindCount(k) : older.length}</span></button>`).join("")}</p>` : ""}
    <div id="history">${older.map(checkCard).join("") || `<p class="muted">${V.none}</p>`}</div>
    ${listed.length > CHECKS_SHOWN ? `<p><button type="button" id="older">${T.menu.older}</button></p>` : ""}`;
  if ($("#older")) $("#older").onclick = () => { CHECKS_SHOWN += 40; viewChecks(); };
  const narrow = () => {
    page.querySelectorAll("#history .check-item").forEach(c => { c.hidden = !!CHECKS_KIND && !c.dataset.kinds.split(" ").includes(CHECKS_KIND); });
    page.querySelectorAll("[data-kind-filter]").forEach(b => b.classList.toggle("on", b.dataset.kindFilter === CHECKS_KIND));
  };
  page.querySelectorAll("[data-kind-filter]").forEach(b => b.onclick = () => { CHECKS_KIND = b.dataset.kindFilter; narrow(); });
  narrow();
  const boxes = [...page.querySelectorAll("[data-check]")];
  const total = () => {
    const ids = new Set(boxes.filter(c => c.checked).map(c => c.dataset.check));
    options.filter(o => ids.has(o.id)).forEach(o => o.needs.forEach(n => ids.add(n)));
    // A check with chapters (the exploration) shows them when it is ticked, and costs one call per chapter ticked
    page.querySelectorAll("[data-chapters-of]").forEach(d => { d.hidden = !ids.has(d.dataset.chaptersOf); });
    const chosen = options.filter(o => ids.has(o.id)), paid = chosen.filter(o => o.model), billed = paid.filter(o => billedStep(o.id));
    const usd = billed.reduce((s, o) => s + (est(o, "usd") || 0) + (o.chapters ? (est(o, "usd_chapter") || 0) * chapters().length : 0), 0);
    // Scripts only: free. Every model check on a subscription or a local model: said. Else what the billed ones cost.
    const worth = paid.reduce((s, o) => s + (est(o, "usd") || 0) + (o.chapters ? (est(o, "usd_chapter") || 0) * chapters().length : 0), 0);
    $("#start").innerHTML = V.start(!paid.length ? V.free : !billed.length ? costHtml(paid[0].id, `≈ ${dollars(worth)}`)
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
    const { id } = await api("/api/verifications", { checks, lang, steps: ownFor(checks), ...(checks.includes("explore") ? { chapters: chapters() } : {}) });
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
    <p class="subtitle">${V.cost(costTag(v.cost, v.unbilled_usd, false))} · ${V.counts(v.counts)}${v.commit ? ` · main @ <code>${esc(v.commit)}</code>` : ""}</p>
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
          ${list(V.linksRead, (r.links || []).map(l => `${extLink(l.url, esc(l.title || l.url))} — ${l.error ? `<span class="attention-text">${esc(l.error)}</span>` : V.linkChars(l.chars, l.cut)}`))}
          ${r.sizes ? sizesBlock(r.sizes) : ""}
          ${r.log ? `<details><summary>${V.log}</summary><pre>${esc(r.log)}</pre></details>` : ""}
          ${(r.findings || []).length ? `${r.fixable ? "" : `<p class="muted small">${V.notFixable}</p>`}${r.mode === "add" ? `<details class="lead-legend"><summary>${V.howToRead}</summary><p>${V.leadsAdd}</p><dl>${
            V.legend.map(([k, t]) => `<dt>${k}</dt><dd>${t}</dd>`).join("")}</dl></details>
            <p class="small lead-tools"><button type="button" class="small-button" data-unfold-card="${c}">${V.unfoldAll}</button>
              <button type="button" class="small-button" data-dig-card="${c}" data-dig="all">🔍 ${V.digTicked}</button>
              <button type="button" class="small-button" data-dig-card="${c}" data-dig="none">${V.digNone}</button></p>` : ""}${stuck.length ? `<div class="unchecked-all" role="status"><span>${V.uncheckedAll(stuck.length)}</span>
            <button type="button" class="primary" data-reopen-card="${c}">${V.resendAll(stuck.length)}</button></div>` : ""}<ul class="leads"${r.mode === "add" ? ` data-card-list="${c}"` : ""}>${r.findings.map((f, i) => lead(f, r.fixable, c, r.mode, i + 1, r.excerpts?.[f], r.details?.[f])).join("")}</ul>` : ""}` : ""}
      </details>`;
    }).join("")}
    <div class="bar check-bar">
      <div class="bar-options" id="bar-options"${BAR_OPEN ? "" : " hidden"}>
        <div class="bar-sect" id="dig-box" hidden><div class="sect">${V.digSect}</div>
          <div class="bar-row"><span class="small">${V.digLabel}</span><span class="seg"><button type="button" data-dig-all="none">${V.digNoneShort}</button><button type="button" data-dig-all="some" disabled></button><button type="button" data-dig-all="all">${V.digAllShort}</button></span>
            <label class="add-context small" id="add-context-box">${V.context}
              <select id="add-context"><option value="pages">${V.contextPages}</option><option value="guide">${V.contextGuide}</option></select>${tip(V.contextTip)}</label></div>
          <div class="dig-cost muted small" id="dig-cost"></div><div class="attention-text small" id="dig-warn" hidden></div></div>
        <div class="bar-sect" id="run-steps-box" hidden><div class="sect">${T.perStep.title}</div><div class="step-cards" id="run-steps"></div></div>
        <div class="narrow-only bar-row end"><button type="button" class="ghost" data-dismiss></button></div>
      </div>
      <div class="bar-line">
        <span class="bar-sum" id="bar-sum"></span>
        <button type="button" class="ghost" id="bar-toggle" aria-expanded="${BAR_OPEN}"></button>
        <button type="button" class="ghost wide-only" id="dismiss" data-dismiss></button>
        <button class="primary" id="fix"></button>
      </div>
    </div>`;
  // A finding is open (checkbox), sent to a fix run (link to the run) or dismissed (can be reopened)
  // Handled findings stay one line; an open one shows the passages it is about
  function lead(f, fixable, card, mode = "fix", n = 0, passages = [], detail = null) {
    const h = v.handled[f], num = `<span class="num">${n}.</span>`;  // per card, stable: handled lines keep theirs
    // A lead handled (sent, dismissed): its title when it has one, its line folded under it
    const shown = detail?.title ? `<b>${esc(detail.title)}</b> <details class="sent"><summary>${V.sentText}</summary><p>${esc(f)}</p></details>` : esc(f);
    if (h?.status === "fix") {
      const run = v.runs[h.thread] || {};
      return `<li class="handled">${num} <span class="badge ok">${V.sent}</span> <a href="#/run/${encodeURIComponent(h.thread)}">${esc(h.thread)}</a>
        ${run.status ? badge(run.status) : ""}${run.pr_url ? ` ${extLink(run.pr_url, "PR")}` : ""} · ${shown}${
        v.unchecked?.[f] ? `<div class="unchecked"><span class="badge attention">${V.unchecked}</span>
          <span class="small">${esc(v.unchecked[f])}</span> <button type="button" class="primary" data-reopen="${esc(f)}">${V.resend}</button></div>` : ""}</li>`;
    }
    if (h?.status === "dismissed") return `<li class="handled">${num} <span class="badge neutral">${V.dismissed}</span> <button class="small-button" data-reopen="${esc(f)}">${V.reopen}</button> ${shown}</li>`;
    if (mode === "add") return addLead(f, fixable, card, n, passages, detail || {});
    const p = leadParts(f), kind = p.kind ? `<span class="badge neutral">${esc(V.kinds[p.kind] || p.kind)}</span> ` : "";
    const pages = p.pages.length ? p.pages.map(x => `<code>${esc(x)}</code>`).join(", ") : p.kind ? `<span class="muted">${V.noPage}</span>` : "";
    // Explained in the language of the interface when the check asked for it: the four parts; the line in English,
    // which is what a run reads, folded below
    const said = detail ? `<dl class="lead-detail">${["says", "guide", "check", "matters"].filter(k => detail[k])
      .map(k => `<dt>${V.detail[k]}</dt><dd>${esc(detail[k])}</dd>`).join("")}</dl>` : "";
    const meta = (detail ? `<details><summary>${V.sentText}</summary>${esc(p.text)}</details>` : "") + (p.read.length ? `<div>${V.readAlso} ${p.read.map(x => `<code>${esc(x)}</code>`).join(", ")}</div>` : "")
      + (p.sources.length ? `<div>${V.sources} ${p.sources.map(u => extLink(u, esc(shortUrl(u)))).join(" · ")}</div>` : "");
    return `<li><label><input type="checkbox" data-lead="${esc(f)}" data-fixable="${fixable}" data-mode="${mode}" data-card="${card}"> ${num} <span class="lead-body">${kind}${pages}${pages ? "<br>" : ""}${said || esc(p.text)}</span></label>${
      meta ? `<div class="lead-meta muted small">${meta}</div>` : ""}${
      mode === "add" ? `<label class="dig muted small"><input type="checkbox" data-deep="${esc(f)}"> ${V.dig}</label>` : ""}${excerpts(passages)}</li>`;
  }
  // A lead of an addition check: one line (its title, its page, where it comes from) that unfolds into the source
  // and the guide side by side, what to check, what it changes for the reader, « dig deeper », the sources and the
  // pages to read also, and the text the run will read
  function addLead(f, fixable, card, n, passages, d) {
    const p = leadParts(f), key = `${id}/${f}`, open = OPEN_LEADS.has(key);
    const title = d.title || (p.text.split(/(?<=\.)\s/)[0] || p.text).slice(0, 140);
    const short = x => x.split("/").pop().replace(/\.md$/, "");
    const from = p.kind === "From a link" && p.sources[0] ? origin(p.sources[0]) : V.kinds[p.kind] || p.kind;
    const pageLink = x => `<a href="${esc(obsidian(v.vault_name, x))}" title="${esc(V.openObsidian)}">${esc(v.titles?.[x] || short(x))}</a> <code>${esc(x)}</code>`;
    const where = (p.kind === "From a link" && p.sources[0] ? `${V.readIn} ${extLink(p.sources[0], esc(shortUrl(p.sources[0])))} ↗ → ` : `<span class="badge neutral">${esc(V.kinds[p.kind] || p.kind)}</span> `)
      + (p.pages.length ? `${V.writeIn} ${p.pages.map(pageLink).join(", ")}` : `<span class="muted">${V.noPage}</span>`);
    const said = x => linked(x || "", p.sources);
    const guideBox = passages?.length ? passages.map(e => e.match === "missing"
      ? `<p class="muted small"><code>${esc(e.page)}</code> · ${T.excerptMissing}</p>`
      : `<div class="excerpt-head muted small">${V.line(e.line)}${e.match === "approx" ? ` · ${T.excerptApprox}` : ""} · <a href="${esc(obsidian(v.vault_name, e.page, e.heading))}">${V.openObsidian} ↗</a></div>
        <div class="lines" lang="${e.page.startsWith("en/") ? "en" : "fr"}">${e.lines.map(l => `<div${l.hit ? ' class="target"' : ""}><span class="n">${l.n}</span><span>${
          l.parts ? `${esc(l.parts[0])}<mark>${esc(l.parts[1])}</mark>${esc(l.parts[2])}` : esc(l.text)}</span></div>`).join("")}</div>`).join("") : "";
    const extra = (() => {  // what digging adds to the cost of the run, when it is billed
      const o = options.find(x => x.id === card) || {}, narrow = ADD_CONTEXT === "pages" && o.run_usd_deep_pages;
      const more = narrow ? o.run_usd_deep_pages - o.run_usd_each_pages : (o.run_usd_deep || 0) - (o.run_usd_each || 0);
      return billedStep("add") && more > 0 ? ` <small>· + ≈ ${dollars(more)}</small>` : "";
    })();
    return `<li class="lead-item">
      <div class="lead-row" data-unfold="${esc(key)}"><input type="checkbox" data-lead="${esc(f)}" data-fixable="${fixable}" data-mode="add" data-card="${card}" aria-label="${esc(title)}">
        <span class="num">${n}.</span><span class="lead-title"><b>${esc(title)}</b>${p.pages[0] ? ` <span class="muted small">· ${esc(short(p.pages[0]))}</span>` : ""}</span>
        <span class="tag">${esc(from)}</span><label class="dig-mini" title="${esc(V.digWhat)}"><input type="checkbox" data-deep="${esc(f)}"> 🔍 ${V.digShort}</label><button type="button" class="unfold" aria-expanded="${open}" aria-label="${esc(V.unfold)}">${open ? "▾" : "▸"}</button></div>
      <div class="lead-open"${open ? "" : " hidden"}>
        <div class="where muted small">${where}</div>
        <div class="lead-cols"><div class="box"><h4>${V.detail.says}</h4>${d.says ? said(d.says) : esc(p.text)}</div>
          <div class="box"><h4>${V.detail.guide}</h4>${d.guide ? `<p>${said(d.guide)}</p>` : ""}${guideBox || (d.guide ? "" : `<p class="muted small">${V.nothingQuoted}</p>`)}</div></div>
        ${d.check || d.matters ? `<dl class="pair">${d.check ? `<dt>${V.detail.check}</dt><dd>${said(d.check)}</dd>` : ""}${d.matters ? `<dt>${V.detail.matters}</dt><dd>${said(d.matters)}</dd>` : ""}</dl>` : ""}
        <div class="lead-actions"><label class="digbtn"><input type="checkbox" data-deep="${esc(f)}"> 🔍 ${V.digButton}${extra}</label><span class="muted small">${V.digWhat}</span></div>
        <div class="lead-lists">
          ${p.sources.length ? `<div><h5>${V.sourcesTitle(p.sources.length)}</h5><ul>${p.sources.map((u, i) => `<li>${extLink(u, esc(shortUrl(u)))} ↗${i === 0 && p.kind === "From a link" ? ` <span class="muted">${V.theLink}</span>` : ""}</li>`).join("")}</ul></div>` : ""}
          ${p.read.length ? `<div><h5>${V.readTitle(p.read.length)}</h5><ul>${p.read.map(x => `<li>${pageLink(x)}</li>`).join("")}</ul></div>` : ""}
        </div>
        ${d.says ? `<details class="sent"><summary>${V.sentText}</summary><p>${esc(p.text)}</p></details>` : ""}
      </div></li>`;
  }
  const boxes = [...page.querySelectorAll("[data-lead]")];
  const ticked = () => boxes.filter(c => c.checked);
  // A lead unfolds by its line (not by its box, its links or its buttons); « unfold all » per card
  page.querySelectorAll("[data-unfold]").forEach(row => row.onclick = e => {
    if (e.target.closest("input, a, label") ) return;
    const body = row.nextElementSibling, open = body.hidden;
    body.hidden = !open;
    row.querySelector(".unfold").textContent = open ? "▾" : "▸";
    row.querySelector(".unfold").setAttribute("aria-expanded", open);
    if (open) OPEN_LEADS.add(row.dataset.unfold); else OPEN_LEADS.delete(row.dataset.unfold);
  });
  page.querySelectorAll("[data-unfold-card]").forEach(b => b.onclick = () => {
    const rows = [...page.querySelectorAll(`[data-card-list="${b.dataset.unfoldCard}"] [data-unfold]`)];
    const open = rows.some(r => r.nextElementSibling.hidden);
    rows.forEach(r => { if (r.nextElementSibling.hidden === open) r.click(); });
    b.textContent = open ? V.foldAll : V.unfoldAll;
  });
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
    const addCost = () => {
      const o = options.find(o => o.id === "news") || {};
      if (ADD_CONTEXT !== "pages" || !o.run_usd_pages) return runOf("news", adds.length, dug);
      const each = f => NO_PAGE.test(f) ? (deep().has(f) ? o.run_usd_deep : o.run_usd_each) : (deep().has(f) ? o.run_usd_deep_pages : o.run_usd_each_pages);
      return `≈ ${dollars(o.run_usd_pages + (adds.some(f => NO_PAGE.test(f)) ? o.run_usd - o.run_usd_pages : 0) + adds.reduce((s, f) => s + (each(f) || 0), 0))}`;
    };
    $("#fix").innerHTML = V.createFix(by, (usd, mode) => costHtml(MODE_STEP[mode] || "fix", usd),
      { compact: runOf("compaction", by.compact || 0), add: addCost(), dug, short: true });
    // The leads of an addition run: how many are dug deeper, and what the run costs, part by part
    $("#dig-box").hidden = !adds.length;
    if (adds.length) {
      const o = options.find(o => o.id === "news") || {}, narrow = ADD_CONTEXT === "pages" && o.run_usd_pages;
      const base = narrow ? o.run_usd_pages + (adds.some(f => NO_PAGE.test(f)) ? o.run_usd - o.run_usd_pages : 0) : o.run_usd;
      const each = narrow ? o.run_usd_each_pages : o.run_usd_each, deeper = narrow ? o.run_usd_deep_pages : o.run_usd_deep;
      const seg = $("#dig-box").querySelectorAll("[data-dig-all]");
      seg[0].classList.toggle("on", dug === 0); seg[2].classList.toggle("on", dug === adds.length);
      seg[1].classList.toggle("on", dug > 0 && dug < adds.length); seg[1].textContent = V.digSome(dug, adds.length);
      $("#dig-cost").textContent = billedStep("add") && o.run_usd
        ? V.digCost(adds.length, adds.length - dug, dollars(each || 0), dug, dollars(deeper || 0), dollars(base || 0), addCost())
        : V.digFree(adds.length - dug, dug, costOf("add", ""));
      $("#dig-warn").hidden = !(dug === adds.length && adds.length > 1);
      $("#dig-warn").textContent = V.digWarn(adds.length);
    }
    // The steps of the run(s) these leads go to: what runs each, changeable for this time
    const kinds = Object.keys(by);
    const wanted = [...kinds.map(k => MODE_STEP[k]), ...(kinds.some(k => k !== "translation") ? ["crosscheck"] : []), ...(kinds.length ? ["mirror"] : [])];
    $("#run-steps-box").hidden = !wanted.length;
    $("#run-steps").innerHTML = (STEPS.forced ? `<p class="muted small">${T.perStep.forced(STEPS.forced)}</p>` : "")
      + wanted.map((s, i) => stepCard(s, i + 1, T.perStep.names[s], V.stepWhat[s] || "")).join("");
    bindSteps($("#run-steps"), count);
    $("#fix").disabled = n === 0 || v.running;
    page.querySelectorAll("[data-dismiss]").forEach(b => { b.textContent = V.dismiss(e); b.disabled = e === 0 || v.running; });
    // The line of the bar: what is ticked and what it costs; the full label of the button on a wide screen
    const price = kinds.length === 1 ? (kinds[0] === "add" ? costHtml("add", addCost()) : "") : "";
    $("#bar-sum").innerHTML = n ? `<span class="wide-only">${V.barSum(n, dug, price)}</span><span class="narrow-only">${V.barSumShort(n, price)}</span>` : "";
    $("#fix").innerHTML = n ? `<span class="wide-only">${$("#fix").innerHTML}</span><span class="narrow-only">${V.createShort}</span>` : $("#fix").innerHTML;
    $("#bar-toggle").innerHTML = `<span class="wide-only">${V.barOptions} ${BAR_OPEN ? "▾" : "▴"}</span><span class="narrow-only">${BAR_OPEN ? "✕" : "⋯"}</span>`;
    $("#bar-toggle").hidden = !wanted.length;
  };
  // The boxes follow LeadRules (rules.js): read them, apply a rule, set them again (the box of a lead's line and the
  // button of its card are one choice), then count
  const digs = [...page.querySelectorAll("[data-deep]")];
  const deep = () => new Set(digs.filter(d => d.checked).map(d => d.dataset.deep));
  const state = () => ({ ticked: new Set(ticked().map(c => c.dataset.lead)), dug: deep() });
  const apply = s => {
    boxes.forEach(c => { c.checked = s.ticked.has(c.dataset.lead); });
    digs.forEach(d => { d.checked = s.dug.has(d.dataset.deep); });
    count();
  };
  const leadsOf = card => boxes.filter(c => !card || c.dataset.card === card).map(c => c.dataset.lead);
  boxes.forEach(c => c.onchange = () => apply(LeadRules.tick(state(), c.dataset.lead, c.checked)));
  digs.forEach(d => d.onchange = () => apply(LeadRules.dig(state(), d.dataset.deep, d.checked)));
  // Dig deeper into every lead ticked, or into none: in one card, or in the whole run (the bar)
  page.querySelectorAll("[data-dig-card]").forEach(b => b.onclick = () => apply(LeadRules.digTicked(state(), leadsOf(b.dataset.digCard), b.dataset.dig === "all")));
  page.querySelectorAll("[data-dig-all]").forEach(b => b.onclick = () => apply(LeadRules.digTicked(state(), leadsOf(null), b.dataset.digAll === "all")));
  // Tick or untick every open finding of one card (all ticked: untick)
  page.querySelectorAll("[data-fold]").forEach(d => d.ontoggle = () => { FOLDS[d.dataset.fold] = d.open; });
  page.querySelectorAll("[data-tick-card]").forEach(b => b.onclick = e => {
    e.preventDefault();  // in the card's summary: tick, do not fold
    const card = boxes.filter(c => c.dataset.card === b.dataset.tickCard), all = card.every(c => c.checked);
    apply(LeadRules.tickAll(state(), card.map(c => c.dataset.lead), !all));
  });
  // The page leaves room under its last line for the bar, as tall as it is now (its options open or folded)
  keepRoomForBar();
  // The options of the bar, opened or folded: the reader's choice, kept in the browser
  $("#bar-toggle").onclick = () => {
    BAR_OPEN = !BAR_OPEN;
    $("#bar-options").hidden = !BAR_OPEN;
    $("#bar-toggle").setAttribute("aria-expanded", BAR_OPEN);
    try { localStorage.setItem("vault-watch-bar-open", BAR_OPEN ? "1" : "0"); } catch { /* private window: per page only */ }
    count();
  };
  count();
  const leads = (findings, status) => api(`/api/verifications/${encodeURIComponent(id)}/leads`, { findings, status }).then(() => viewCheck(id));
  if ($("#remove")) $("#remove").onclick = () => confirm(V.confirmRemove)
    && api(`/api/verifications/${encodeURIComponent(id)}/delete`, {}).then(() => { location.hash = "/check"; });
  page.querySelectorAll("[data-reopen]").forEach(b => b.onclick = () => leads([b.dataset.reopen], "open"));
  page.querySelectorAll("[data-reopen-card]").forEach(b => b.onclick = () => leads(
    (v.results[b.dataset.reopenCard].findings || []).filter(f => v.unchecked?.[f] && v.handled[f]?.status === "fix"), "open"));
  if (!boxes.length) page.querySelector(".bar").remove();
  else {
    page.querySelectorAll("[data-dismiss]").forEach(b => b.onclick = () => leads(ticked().map(c => c.dataset.lead), "dismissed"));
    $("#fix").onclick = async () => {
      const busy = (await api("/api/runs").catch(() => [])).filter(r => r.status === "running").map(r => r.thread);
      if (busy.length && !confirm(V.confirmParallel(busy.join(", ")))) return;
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
    ${reportTabs(idea ? "idea" : "report")}
    <p class="subtitle">${idea ? T.ideaIntro : T.reportIntro} ${price}</p>
    ${idea ? `<p class="small attention-text">${T.ideaLimit}</p>` : ""}
    <textarea id="text" placeholder="${esc(idea ? T.ideaExample : T.reportExample)}">${esc(draft(kind))}</textarea>
    <p class="muted small" id="draft-note"></p>
    ${idea ? `<p><label class="small"><input type="checkbox" id="deep"> ${T.ideaDeep}</label></p>` : ""}
    <details class="run-steps"${Object.keys(ownFor(wanted)).length ? " open" : ""}><summary>${T.perStep.title}</summary>
      ${STEPS.forced ? `<p class="muted small">${T.perStep.forced(STEPS.forced)}</p>` : ""}${wanted.map(s => stepLine(s, T.perStep.names[s])).join("")}</details>
    <p><button class="primary" id="send">${idea ? T.ideaButton : T.reportButton}</button> <span class="error-text small" id="send-error"></span></p>`;
  bindDraft(kind, $("#text"), $("#draft-note"));
  bindSteps(page, () => viewReport(idea));
  $("#send").onclick = async () => {
    const text = $("#text").value.trim();
    if (!text) return;
    $("#send").disabled = true;
    const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
    try {  // the draft stays until the run has started: a refusal or a lost connection keeps the text
      const { thread } = await api("/api/fix", { text, mode: kind, steps: ownFor(wanted), ...(idea && $("#deep").checked ? { deep: lines } : {}) });
      dropDraft(kind);
      location.hash = `/run/${encodeURIComponent(thread)}`;
    } catch (e) { $("#send-error").textContent = e.message; $("#send").disabled = false; }
  };
}

const reportTabs = on => `<p class="tabs">${[["report", "fix"], ["idea", "add"], ["links", "links"]].map(([h, k]) =>
  `<a href="#/${h}"${h === on ? ' class="active"' : ""}>${T.reportKinds[k]}</a>`).join("")}</p>`;

// Links to read whole (links.py): a check of its own, started here; its leads are ticked on the page of the check
async function viewLinks() {
  await loadSteps();
  const [all, video] = await Promise.all([api(`/api/verifications/options${stepsQuery()}`), api("/api/videos")]);
  const o = all.find(x => x.id === "links") || {};
  const max = o.links_max || 10;
  const price = billedStep("links") ? T.linksCost(`≈ ${dollars(o.usd || 0)}`, `≈ ${dollars(est(o, "usd_link") || 0)}`, max)
    : stepNow("links")?.billing === "subscription" ? T.reportSubscription : costOf("links", "");
  page.innerHTML = `
    <h1>${T.reportTitle}</h1>
    ${reportTabs("links")}
    <p class="subtitle">${T.linksIntro} ${price}</p>
    <p class="small attention-text">${T.ideaLimit}</p>
    <p class="muted small">${video.ready ? T.linksVideoReady : video.set ? T.linksVideoDown(esc(video.why)) : T.linksVideo}</p>
    <textarea id="text" placeholder="${esc(T.linksExample)}">${esc(draft("links"))}</textarea>
    <p class="muted small" id="draft-note"></p>
    <p class="small error-text" id="too-many" hidden>${T.linksTooMany(max)}</p>
    <details class="run-steps"${Object.keys(ownFor(["links"])).length ? " open" : ""}><summary>${T.perStep.title}</summary>
      ${STEPS.forced ? `<p class="muted small">${T.perStep.forced(STEPS.forced)}</p>` : ""}${stepLine("links", T.perStep.names.links)}</details>
    <p><button class="primary" id="send"></button> <span class="error-text small" id="send-error"></span></p>`;
  const found = () => [...new Set(($("#text").value.match(/https?:\/\/[^\s<>"']+/g) || []).map(a => a.replace(/[.,;:!?)\]}»]+$/, "")))];
  const count = () => {
    const n = found().length;
    $("#send").textContent = T.linksButton(n);
    $("#send").disabled = !n || n > max;
    $("#too-many").hidden = n <= max;
  };
  $("#text").oninput = count;
  count();
  bindDraft("links", $("#text"), $("#draft-note"), count);
  bindSteps(page, () => viewLinks());
  $("#send").onclick = async () => {
    $("#send").disabled = true;
    try {  // the draft stays until the check has started
      const { id } = await api("/api/verifications", { checks: ["links"], links: found(), lang, steps: ownFor(["links"]) });
      dropDraft("links");
      location.hash = `/check/${encodeURIComponent(id)}`;
    } catch (e) { $("#send-error").textContent = e.message; $("#send").disabled = false; }
  };
}

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

// A language by its code, in the language of the page (« anglais », « English »); the server's name otherwise
const languageName = (code, fallback) => { try { return new Intl.DisplayNames([lang], { type: "language" }).of(code) || fallback; } catch { return fallback; } };

// --- Sync the languages: the mirrors follow the source pages (GET/POST /api/mirrors) --------------------------
async function viewLanguages() {
  await loadSteps();
  const L = T.languages, d = await api(`/api/mirrors${stepsQuery()}`);
  if (location.hash.slice(1) !== "/languages") return;  // left the page meanwhile
  if (!d.languages.length) {
    page.innerHTML = `<h1>${L.title}</h1><p class="muted">${L.noMirror}</p>`;
    return;
  }
  const card = (p, kind) => `<div class="card check-card"><label class="option">
      <input type="checkbox" data-kind="${kind}" data-page="${esc(p.page)}" data-usd="${p.usd}" checked>
      <div><div class="header"><code>${esc(p.page)}</code> <span class="badge attention">${costHtml("mirror", `≈ ${dollars(p.usd)}`)}</span></div>
        <p class="muted small">${L.passages(p.passages)}${p.since ? ` · ${L.since(esc(p.since.slice(0, 7)))}` : ""}</p></div></label>
      ${(p.hunks || []).length ? `<details class="hunks" open><summary>${L.zones(p.hunks.length)}</summary>${p.hunks.map(hunk).join("")}</details>` : ""}</div>`;
  // A changed zone of the page, two lines of context above and below it, the change as a word-level diff
  const around = lines => lines.length ? `<div class="context">${lines.map(l => esc(l) || "&nbsp;").join("\n")}</div>` : "";
  const hunk = h => { const [before, after] = wordDiff(h.old, h.new);
    return `<div class="hunk">${around(h.above)}${h.old ? `<div class="diff before">${before}</div>` : ""}${
      h.new ? `<div class="diff after">${after}</div>` : ""}${around(h.below)}</div>`; };
  const any = d.ahead.length + d.hand.length;
  page.innerHTML = `
    <h1>${L.title}</h1>
    <p class="subtitle">${L.intro(d.languages.map(l => esc(languageName(l.code, l.name))).join(", "))}</p>
    ${any ? "" : `<p class="banner">${L.none}</p>`}
    ${any > 1 ? `<p class="tick-row"><button type="button" class="small-button" data-tick="all">${L.tickAll}</button>
      <button type="button" class="small-button" data-tick="none">${L.untickAll}</button></p>` : ""}
    ${d.hand.length ? `<h2>${L.hand}</h2><p class="muted small">${L.handHelp}</p>${d.hand.map(p => card(p, "hand")).join("")}` : ""}
    ${d.ahead.length ? `<h2>${L.ahead}</h2><p class="muted small">${L.aheadHelp(esc(d.base))}</p>${d.ahead.map(p => card(p, "ahead")).join("")}` : ""}
    ${d.elsewhere.length ? `<p class="small attention-text">${L.elsewhere(d.elsewhere.map(p => `<code>${esc(p)}</code>`).join(", "))}</p>` : ""}
    ${any ? `<section class="card" id="proofread">${d.check ? checkFound(d.check) : checkOffer()}</section>` : ""}
    ${any ? `<details class="run-steps"${Object.keys(ownFor(["mirror"])).length ? " open" : ""}><summary>${T.perStep.title}</summary>
      ${STEPS.forced ? `<p class="muted small">${T.perStep.forced(STEPS.forced)}</p>` : ""}${stepLine("mirror", T.perStep.names.mirror)}</details>
    <p><button class="primary" id="sync"></button> <span class="error-text small" id="sync-error"></span></p>` : ""}`;
  bindSteps(page, () => viewLanguages());
  const boxes = () => [...page.querySelectorAll("input[data-page]")];
  bindCheck(d, boxes);
  const label = () => {
    const on = boxes().filter(b => b.checked), button = $("#sync");
    if (!button) return;
    button.disabled = !on.length;
    button.innerHTML = L.button(on.length, costHtml("mirror", `≈ ${dollars(on.reduce((sum, b) => sum + Number(b.dataset.usd), 0))}`));
  };
  boxes().forEach(b => { b.onchange = () => { label(); checkLabel(d, boxes); }; });
  page.querySelectorAll("[data-tick]").forEach(b => b.onclick = () => { boxes().forEach(x => { x.checked = b.dataset.tick === "all"; }); label(); checkLabel(d, boxes); });
  label();
  if (!$("#sync")) return;
  $("#sync").onclick = async () => {
    const on = boxes().filter(b => b.checked);
    $("#sync").disabled = true;
    try {
      const { thread } = await api("/api/mirrors", { pages: on.filter(b => b.dataset.kind === "ahead").map(b => b.dataset.page),
        hand: on.filter(b => b.dataset.kind === "hand").map(b => b.dataset.page), steps: ownFor(["mirror"]) });
      location.hash = `/run/${encodeURIComponent(thread)}`;
    } catch (e) {
      $("#sync-error").textContent = e.message;
      $("#sync").disabled = false;
    }
  };
}

// --- The edits checked before the sync (H4.2: POST /api/mirrors/check, proofread.py) --------------------------
const CHECK_STEP = { spelling: "proofread", facts: "factcheck", consistency: "crosscheck" };
let checkTimer = null;

function checkOffer() {
  const C = T.languages.check;
  return `<h2>${C.title}</h2><p class="muted small">${C.intro}</p>
    ${Object.keys(C.kinds).map(k => `<label class="option"><input type="checkbox" data-check="${k}">
      <div><b>${C.kinds[k]}</b> <span class="badge attention" data-check-usd="${k}"></span>
      <p class="muted small">${C.what[k]}</p></div></label>`).join("")}
    <p><button id="check-go"></button> <span class="error-text small" id="check-error"></span></p>`;
}

// What each check costs for the pages ticked: per page for the spelling and the facts, once for the consistency
function checkCost(d, boxes, kind) {
  if (kind === "consistency") return d.consistency_usd;
  const on = new Set(boxes().filter(b => b.checked).map(b => b.dataset.page));
  return [...d.hand, ...d.ahead].filter(p => on.has(p.page)).reduce((sum, p) => sum + (p.check_usd?.[kind] || 0), 0);
}

function checkLabel(d, boxes) {
  const C = T.languages.check, go = $("#check-go");
  if (!go) return;
  let total = 0, paid = false, free = "";
  page.querySelectorAll("[data-check-usd]").forEach(b => {
    const k = b.dataset.checkUsd, usd = checkCost(d, boxes, k), shown = `≈ ${dollars(usd)}`, label = costOf(CHECK_STEP[k], shown);
    b.innerHTML = costHtml(CHECK_STEP[k], shown);
    if (!page.querySelector(`[data-check="${k}"]`).checked) return;
    if (label === shown) { total += usd; paid = true; } else free = label;  // a step on a subscription or a local model
  });
  const asked = [...page.querySelectorAll("[data-check]:checked")];
  go.disabled = !asked.length || !boxes().some(b => b.checked);
  go.textContent = asked.length ? C.button(paid ? `≈ ${dollars(total)}` : free) : C.none;
}

function checkFound(c) {
  const C = T.languages.check;
  if (c.running || !c.done) return `<h2>${C.title}</h2><p class="muted">${C.running}</p>`;
  const byPage = {};
  c.fixes.forEach(f => (byPage[f.page] ||= []).push(f));
  return `<h2>${C.title}</h2>
    ${c.error ? `<p class="error-text small">${C.error}${T.colon}${esc(c.error)}</p>` : ""}
    <p class="muted small">${C.found(c.fixes.length, dollars(c.cost))}</p>
    ${Object.entries(byPage).map(([p, fixes]) => `<div class="pair-page"><div class="header"><code>${esc(p)}</code></div>
      ${fixes.map(f => { const [before, after] = wordDiff(f.current, f.proposed), ok = f.check === "ok", over = (f.overlaps || []).length;
        return `<label class="option fix"><input type="checkbox" data-fix="${esc(f.id)}"${!ok ? " disabled" : over ? "" : " checked"}>
          <div><p class="small"><span class="badge">${C.kinds[f.kind]}</span> ${esc(f.reason)}${
            f.source_url ? ` · <a href="${esc(f.source_url)}" target="_blank" rel="noopener">${C.source}</a>` : ""}${
            ok ? "" : ` · <span class="attention-text">${C.notFound}</span>`}${
            over ? ` · <span class="attention-text">${C.overlaps(f.overlaps.join(", "))}</span>` : ""}</p>
          <div class="diff before">${before}</div><div class="diff after">${after || `<span class="muted">—</span>`}</div>
          ${ok ? `<textarea data-fix-text="${esc(f.id)}" spellcheck="true">${esc(f.proposed)}</textarea>` : ""}</div></label>`; }).join("")}
    </div>`).join("")}
    ${c.notes.length ? `<p class="small"><b>${C.notes}</b></p><ul class="small">${c.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
    <p><button class="primary" id="check-apply"></button> <span class="error-text small" id="check-error"></span></p>`;
}

function bindCheck(d, boxes) {
  const C = T.languages.check, c = d.check;
  clearTimeout(checkTimer);
  if (!$("#proofread")) return;  // every page in line with its translation: nothing to check
  if (c && (c.running || !c.done)) {  // follow it until it is done
    checkTimer = setTimeout(() => { if (location.hash.slice(1) === "/languages") viewLanguages(); }, 1500);
    return;
  }
  if (c) {
    const fixes = () => [...page.querySelectorAll("[data-fix]:checked")].map(b => b.dataset.fix);
    const label = () => { $("#check-apply").textContent = C.apply(fixes().length); };
    page.querySelectorAll("[data-fix]").forEach(b => { b.onchange = label; });
    page.querySelectorAll("[data-fix-text]").forEach(t => {
      const f = c.fixes.find(x => x.id === t.dataset.fixText);
      const fit = () => { t.style.height = "auto"; t.style.height = `${t.scrollHeight + 4}px`; };
      fit();
      t.oninput = () => { t.previousElementSibling.innerHTML = wordDiff(f.current, t.value)[1]; fit(); };
    });
    label();
    $("#check-apply").onclick = async () => {
      $("#check-apply").disabled = true;
      const ids = fixes(), edits = {};
      ids.forEach(id => { const t = page.querySelector(`[data-fix-text="${CSS.escape(id)}"]`), f = c.fixes.find(x => x.id === id);
        if (t && t.value !== f.proposed) edits[id] = t.value; });
      try {
        const done = await api(`/api/mirrors/check/${encodeURIComponent(c.id)}/accept`, { ids, edits });
        await viewLanguages();
        const failed = Object.keys(done.failed);
        if (failed.length) $("#proofread")?.insertAdjacentHTML("beforebegin", `<p class="banner">${C.failed} ${esc(failed.join(", "))}</p>`);
      } catch (e) { $("#check-error").textContent = e.message; $("#check-apply").disabled = false; }
    };
    return;
  }
  page.querySelectorAll("[data-check]").forEach(b => { b.onchange = () => checkLabel(d, boxes); });
  checkLabel(d, boxes);
  $("#check-go").onclick = async () => {
    const on = boxes().filter(b => b.checked), checks = [...page.querySelectorAll("[data-check]:checked")].map(b => b.dataset.check);
    $("#check-go").disabled = true;
    try {
      await api("/api/mirrors/check", { pages: on.filter(b => b.dataset.kind === "ahead").map(b => b.dataset.page),
        hand: on.filter(b => b.dataset.kind === "hand").map(b => b.dataset.page), checks,
        steps: ownFor(checks.map(k => CHECK_STEP[k])) });
      viewLanguages();
    } catch (e) { $("#check-error").textContent = e.message; $("#check-go").disabled = false; }
  };
}

// --- Costs -------------------------------------------------------------------------------------------------
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
