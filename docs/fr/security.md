*[English version](../security.md)*

# Sécurité

Ce que l'agent peut atteindre, ce que le modèle peut faire, et ce qu'il faut savoir avant de brancher un guide. En
bref : le modèle ne fait que répondre dans une forme imposée, le code décide de ce qui est écrit, un humain relit
avant que quoi que ce soit ne quitte la machine, et l'agent ne stocke jamais de clé.

## Les clés et les jetons sont des références

L'agent ne stocke jamais de clé. Chaque champ qui en demande une prend une référence à l'endroit où elle se trouve :

| Référence | Où est la valeur |
| :-- | :-- |
| `env:NOM` | une variable d'environnement (définie par votre shell, ou injectée par `sops exec-env`) |
| `sops:fichier#NOM` | un champ d'un fichier chiffré avec [sops](https://github.com/getsops/sops), déchiffré au moment où un appel en a besoin |
| `file:chemin` | un fichier qui ne contient que la valeur |

C'est le cas de la clé d'API des réglages (`key`), de la clé du serveur compatible OpenAI, du jeton d'une forge
Gitea (`[guide] forge_token`) et du jeton de dl-sub-dub (`videos.token`). Une valeur en clair est refusée à l'enregistrement des réglages, puis à leur
lecture. La valeur est lue au moment d'un appel et n'est jamais écrite dans le journal, les rapports ni les
messages. GitHub passe par `gh`, connecté par vous (`gh auth login`) : l'agent ne voit jamais son jeton.

Un jeton Gitea vaut pour tous les dépôts que son compte peut atteindre (Gitea n'a pas de jeton par dépôt) : donnez
à l'agent un compte à lui, collaborateur du seul dépôt du guide, avec le droit `repository` (et `issue` pour une
veille `issues`).

## Ce que le modèle peut faire

- **Répondre, pas agir.** Chaque appel répond dans un schéma Pydantic (sortie structurée). Le modèle n'a aucun
  outil qui écrive un fichier, lance une commande ou appelle git. Les seuls outils qu'il reçoit sont la recherche
  web et la lecture de pages, aux étapes qui vérifient les sources.
- **Une correction est une citation et un remplacement.** Le code ne l'applique que si le texte cité apparaît une
  seule fois dans la page (`vault.check`), dans un worktree git sur une nouvelle branche, jamais sur `main`. Une
  page en lecture seule (`[content] readonly`) est refusée, quelle que soit l'étape qui propose la modification.
- **Une correction ne touche qu'une page du guide.** La page que nomme une correction est écrite par le modèle, à
  partir de ce qu'il a lu ; le code n'accepte qu'une page de contenu du guide ou son miroir (`vault.is_page` : un
  chemin relatif dans le guide, une page Markdown de `[content] include`). Jamais les scripts du guide, son
  manifeste, un dossier caché ni un fichier hors du guide : l'agent lance les contrôles du guide après avoir
  appliqué, donc une correction sur l'un d'eux aurait été du code exécuté sur votre machine (jusqu'à la 1.4.2).
- **Deux pauses humaines.** Rien n'est appliqué avant la relecture, rien n'est poussé avant un second oui. La pull
  request est ensuite fusionnée par un humain, sur la forge.
- **Claude Code tourne à nu.** Avec le moteur `claude-code`, chaque appel est un `claude -p --safe-mode` sans vos
  instructions, hooks, skills ni serveurs MCP, sans conversation gardée, sans aucun outil aux étapes qui ne
  vérifient pas de source, et sans les clés d'API dans son environnement. Aux étapes qui vérifient des sources, il a
  sa recherche web et, à la place de son WebFetch (qui tourne sur votre machine et lisait n'importe quelle adresse,
  votre réseau local compris), le lecteur de pages de l'agent, en outil MCP local (`mcp_fetch.py`) ; ces appels ne
  chargent aucune source de réglages au lieu de `--safe-mode`, qui couperait aussi cet outil : vos réglages, hooks,
  extensions et instructions restent dehors de la même façon. Il est refusé quand il est connecté autrement qu'avec
  un abonnement, pour qu'aucun appel ne soit facturé sans qu'on vous l'ait demandé.

## Ce que lit le modèle, ce sont des données

La veille (notes de version, avis de sécurité, flux) et les pages lues sur le web sont écrites par d'autres. Une
page peut contenir un texte écrit pour orienter un modèle. L'agent ne compte pas sur la résistance du modèle ; il
limite ce qu'un tel texte peut obtenir :

- au pire, le modèle propose une correction fausse ou un verdict faux. Chaque proposition montre sa source et un
  diff mot à mot à la relecture, et la relecture croisée la relit avec tout le guide ;
- un passage que le modèle dit avoir trouvé est cherché dans la page par le code (`quotes.py`) : une citation
  introuvable est affichée comme telle, jamais comme le texte du guide ;
- le lecteur de pages de l'agent (`webtools.py` : pour le moteur compatible OpenAI, pour Claude Code par
  `mcp_fetch.py`, pour les liens lus en entier et les notes d'une veille) ne lit que du http et du https, et refuse
  toute adresse qui n'est pas publique : ni la machine elle-même, ni le réseau local, ni une adresse de métadonnées
  d'un cloud. Il contrôle l'adresse que chaque requête a réellement atteinte, pas seulement celle que le nom donnait
  au moment du contrôle (DNS rebinding), chaque redirection, et une adresse IPv6 qui porte une IPv4 privée (NAT64,
  6to4, Teredo). Les outils web de l'API Claude tournent sur les serveurs d'Anthropic et ne peuvent pas atteindre
  votre réseau ;
- un lien affiché par la page n'est un lien que si c'est une adresse http(s) (jamais `javascript:`), quel qu'en
  soit l'auteur : un modèle, un flux, une page ;
- les réponses du modèle ne deviennent jamais des commandes : les seuls programmes que l'agent lance sont git,
  `gh`, les contrôles du guide et, quand vos réglages s'en servent, `claude` et `sops`, avec des arguments
  construits par le code, et dl-sub-dub par `videos.start` : une commande que vous écrivez à la main dans
  `settings.json` (la page ne peut pas la régler), lancée sans shell et sans les clés de l'agent dans son
  environnement.

## Ce qui sort de la machine

Il n'y a pas de télémétrie : l'agent n'envoie rien sur vous ni sur votre guide à son auteur. Il se sert du réseau
pour :

| Quoi | Vers qui |
| :-- | :-- |
| Les appels au modèle : les consignes, la veille, les pages ou tout le guide | Le moteur que vous avez choisi |
| La recherche web et la lecture de pages, aux étapes qui vérifient des sources | Les outils web du moteur, ou votre SearXNG et les pages elles-mêmes |
| La collecte d'une veille et le contrôle de ses sources | GitHub, Hugging Face, les flux et les pages de `feeds.json` |
| Les liens des pages, quand ils sont vérifiés | Les sites vers lesquels le guide renvoie |
| Le lien d'une vidéo, quand une piste ou un contrôle lit son texte | Votre dl-sub-dub, sur cette machine seulement (`videos.url` est refusé sinon), qui va chercher la vidéo sur son site |
| Les issues, les artefacts, la branche et la pull request | La forge du guide : GitHub par `gh`, ou votre Gitea |
| La liste publique des prix, quand vous la demandez dans les Réglages | Un fichier du dépôt LiteLLM, sur GitHub |

« Donner mon avis » n'envoie rien de lui-même. Il prépare une issue GitHub ou un e-mail que vous relisez et
envoyez vous-même, ou un texte à copier. La version y figure ; le système, Python, le moteur et l'écran ne
s'ajoutent que si vous cochez la case ; rien du guide n'y est jamais, ni son nom, ni ses pages, ni la passe
affichée.

## Le serveur local

`vault-watch serve` n'écoute que sur 127.0.0.1. Il refuse une requête dont l'en-tête `Host` n'est pas local
(DNS rebinding) et une requête que le navigateur signale comme venant d'un autre site (`Sec-Fetch-Site`, `Origin`).
Chaque appel de son API, lecture comprise, doit porter un en-tête `X-Vault-Watch`, qu'une page d'un autre site ne
peut pas envoyer sans une requête CORS préalable que le serveur n'accorde jamais ; seul ce que le navigateur demande
de lui-même s'en passe (la sonde de santé, les avis, le flux d'une passe, son rapport). Jusqu'à la 1.4.2, une
lecture n'avait pas besoin de l'en-tête, et une image sur n'importe quel site pouvait faire résoudre une clé au
serveur et l'envoyer ailleurs. La page n'est jamais affichée dans le cadre d'un autre site (`X-Frame-Options`,
`frame-ancestors`), n'exécute que ses propres scripts (une Content Security Policy) et n'est jamais « reniflée ». Il
n'y a pas de compte : quiconque peut ouvrir une connexion sur la machine elle-même peut l'utiliser, donc n'exposez
pas le port (proxy inverse, tunnel) sans authentification devant.

## Avant de brancher un guide

- **Le manifeste lance des commandes.** `[checks] audits`, `claims_due`, `sources` et `version_floors` sont des
  commandes que l'agent lance dans le dossier du guide, avec vos droits. Ne branchez qu'un guide dont vous avez lu
  le manifeste, comme avant de lancer son `npm test`.
- **Le guide est envoyé au modèle.** Une relecture croisée envoie tout le guide (moins `exclude`) au moteur
  choisi : Anthropic pour `api` et `claude-code`, votre serveur pour `openai`. Écartez avec `exclude` les pages qui
  ne doivent pas quitter la machine, ou utilisez un modèle local.
- **Le journal des coûts** (`~/.vault-watch/usage.jsonl`, ou `VAULT_WATCH_JOURNAL`)
  contient les noms des passes, les étapes, les modèles, les tokens et les coûts, aucun contenu du guide. Ce dépôt
  versionne celui du guide de référence ; gardez le vôtre hors d'un dépôt public si les noms des passes en
  disent trop.

## Signaler un problème

Signalez-le en privé depuis l'onglet Security du dépôt GitHub (« Report a vulnerability »), pas dans une issue
publique.
