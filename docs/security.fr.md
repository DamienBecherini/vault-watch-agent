*[English version](security.md)*

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

C'est le cas de la clé d'API des réglages (`key`), de la clé du serveur compatible OpenAI et du jeton d'une forge
Gitea (`[guide] forge_token`). Une valeur en clair est refusée à l'enregistrement des réglages, puis à leur
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
- **Deux pauses humaines.** Rien n'est appliqué avant la relecture, rien n'est poussé avant un second oui. La pull
  request est ensuite fusionnée par un humain, sur la forge.
- **Claude Code tourne à nu.** Avec le moteur `claude-code`, chaque appel est un `claude -p --safe-mode` sans vos
  instructions, hooks, skills ni serveurs MCP, sans conversation gardée, sans autre outil que la recherche et la
  lecture web (aucun outil aux étapes qui ne vérifient pas de source), et sans les clés d'API dans son
  environnement. Il est refusé quand il est connecté autrement qu'avec un abonnement, pour qu'aucun appel ne soit
  facturé sans qu'on vous l'ait demandé.

## Ce que lit le modèle, ce sont des données

La veille (notes de version, avis de sécurité, flux) et les pages lues sur le web sont écrites par d'autres. Une
page peut contenir un texte écrit pour orienter un modèle. L'agent ne compte pas sur la résistance du modèle ; il
limite ce qu'un tel texte peut obtenir :

- au pire, le modèle propose une correction fausse ou un verdict faux. Chaque proposition montre sa source et un
  diff mot à mot à la relecture, et la relecture croisée la relit avec tout le guide ;
- un passage que le modèle dit avoir trouvé est cherché dans la page par le code (`quotes.py`) : une citation
  introuvable est affichée comme telle, jamais comme le texte du guide ;
- les outils web de l'agent (pour les moteurs sans web propre, `webtools.py`) ne lisent que du http et du https,
  et refusent toute adresse qui n'est pas publique : ni la machine elle-même, ni le réseau local, ni une adresse
  de métadonnées d'un cloud ;
- les réponses du modèle ne deviennent jamais des commandes : les seuls programmes que l'agent lance sont git,
  `gh` et les contrôles du guide, avec des arguments construits par le code.

## Le serveur local

`vault-watch serve` n'écoute que sur 127.0.0.1. Il refuse une requête dont l'en-tête `Host` n'est pas local
(DNS rebinding), et chaque requête qui modifie quelque chose doit porter un en-tête `X-Vault-Watch`, qu'une page
d'un autre site ne peut pas envoyer sans une requête CORS préalable que le serveur n'accorde jamais. Il n'y a pas
de compte : quiconque peut ouvrir une connexion sur la machine elle-même peut l'utiliser, donc n'exposez pas le
port (proxy inverse, tunnel) sans authentification devant.

## Avant de brancher un guide

- **Le manifeste lance des commandes.** `[checks] audits`, `claims_due`, `sources` et `version_floors` sont des
  commandes que l'agent lance dans le dossier du guide, avec vos droits. Ne branchez qu'un guide dont vous avez lu
  le manifeste, comme avant de lancer son `npm test`.
- **Le guide est envoyé au modèle.** Une relecture croisée envoie tout le guide (moins `exclude`) au moteur
  choisi : Anthropic pour `api` et `claude-code`, votre serveur pour `openai`. Écartez avec `exclude` les pages qui
  ne doivent pas quitter la machine, ou utilisez un modèle local.
- **Le journal des coûts** (`~/.vault-watch/usage.jsonl`, ou `VAULT_WATCH_JOURNAL`)
  contient les noms des passages, les étapes, les modèles, les tokens et les coûts, aucun contenu du guide. Ce dépôt
  versionne celui du guide de référence ; gardez le vôtre hors d'un dépôt public si les noms des passages en
  disent trop.

## Signaler un problème

Signalez-le en privé depuis l'onglet Security du dépôt GitHub (« Report a vulnerability »), pas dans une issue
publique.
