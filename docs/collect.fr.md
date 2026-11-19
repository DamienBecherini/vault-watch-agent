*[English version](collect.md)*

# Collecter une veille (`vault-watch collect`)

Une veille liste ce qui a changé dans le domaine du guide sur quelques jours. L'agent peut la collecter lui-même :
vous listez dans un `feeds.json` les flux à lire, et `vault-watch collect` rassemble les éléments de la fenêtre,
écarte la routine par règles, garde les notes de version et le texte des avis, puis écrit un
[`watch.json`](watch-format.fr.md). Aucun modèle n'est appelé : une collecte ne coûte rien.

```bash
vault-watch --guide ../mon-guide collect                  # les 8 derniers jours ; rapport Markdown sur la sortie
vault-watch --guide ../mon-guide collect --days 15 --json watch.json --markdown watch.md
vault-watch --guide ../mon-guide collect --since 2026-11-01 --only security,releases
vault-watch --guide ../mon-guide collect --no-triage      # garder tous les éléments de la fenêtre
```

Sans `--json`, la veille va dans `watches/watch-<date>.json` du dossier de travail du guide. Avec
`source = "feeds"`, l'interface la liste à cet endroit (ci-dessous).

GitHub limite les requêtes sans jeton. Définissez `GITHUB_TOKEN` (ou `GH_TOKEN`) avant de collecter, par exemple
`GITHUB_TOKEN=$(gh auth token)`. Les avis de sécurité en ont besoin.

## Dans le manifeste

```toml
[watch]
source = "feeds"                    # l'interface liste les veilles collectées et offre un bouton « Collecter une veille »
feeds = "watch/feeds.json"          # les flux à lire (toute source peut le nommer : `vault-watch collect` marche quand même)
floors = "watch/floors.json"        # facultatif : les versions minimales que le guide recommande
seen = "watch/seen.md"              # facultatif : les éléments déjà triés, écartés s'ils reviennent
```

Sans `floors`, l'agent prend le fichier de `[checks] version_floors` quand le guide en a un.

## `feeds.json`

```json
{
  "defaults": { "days": 8, "maxItemsPerFeed": 15 },
  "domains": { "security": "Sécurité", "releases": "Versions", "news": "Actualités" },
  "feeds": [
    { "id": "memos", "domain": "releases", "type": "github-releases", "repo": "usememos/memos", "tier": "A" },
    { "id": "adv-memos", "domain": "security", "type": "github-advisories", "repo": "usememos/memos", "tier": "A" },
    { "id": "postgresql-news", "domain": "news", "type": "rss", "url": "https://www.postgresql.org/news.rss",
      "tier": "A", "keywords": ["released", "security"] }
  ]
}
```

Le guide d'exemple en a un complet : [`examples/sample-guide/feeds.json`](../examples/sample-guide/feeds.json).

| Clé | Ce que c'est |
| :-- | :-- |
| `defaults.days` | La fenêtre quand la commande n'en donne pas (8). |
| `defaults.maxItemsPerFeed` | Au plus ce nombre d'éléments par flux, les plus récents (15). |
| `domains` | Facultatif. Les sections du rapport, dans l'ordre, avec leur titre. Sans lui, les domaines viennent dans l'ordre des flux, `security` en tête et les pistes (`discovery`, `signals`) à la fin. |
| `feeds` | Les flux, ci-dessous. |

### Un flux

| Clé | Pour | Ce que c'est |
| :-- | :-- | :-- |
| `id` | tous | Un nom unique : il apparaît dans le rapport, et `floors` s'en sert. |
| `domain` | tous | La section du rapport : la partie du guide que le flux concerne. |
| `type` | tous | `github-releases`, `github-tags`, `github-advisories`, `rss` (RSS 2.0 ou Atom ; par défaut), `youtube`, `huggingface-author`, `huggingface-trending`, `github-search`. |
| `tier` | tous | La confiance due à la source : `A` primaire, `B` secondaire réputée, `C` simple piste. Les éléments de niveau C comptent comme des pistes. |
| `repo` | les types GitHub sauf la recherche | `propriétaire/nom`. |
| `url` | `rss` | L'adresse du flux. |
| `channelId`, `name` | `youtube` | La chaîne, et le nom affiché devant chaque titre. |
| `author` | `huggingface-author` | L'éditeur sur Hugging Face. |
| `query`, `minStars`, `maxAgeDays`, `limit` | `github-search` | Les dépôts jeunes qui ont vite pris : la recherche, les étoiles (500), l'âge en jours (30), le nombre (10). |
| `limit` | `huggingface-trending` | Combien de modèles en vogue lire (40) ; ceux des éditeurs déjà suivis sont laissés de côté. |
| `keywords` | tous | Ne garder que les éléments dont le titre ou le résumé contient l'un de ces mots, cherché en début de mot (`IA` ne trouve pas « Debian »). |
| `exclude` | tous | Une expression régulière : les éléments dont le titre y correspond sont laissés de côté. Le titre d'un élément GitHub commence par le dépôt : `owner/repo v2.3.0`, `owner/repo GHSA-…`. Les étiquettes mobiles (`stable`, `latest`, `next`, `v1`…) sont de toute façon écartées par le pré-tri. |
| `minLevel` | versions, étiquettes | `major`, `minor` (par défaut) ou `patch` : les versions plus petites sont écartées. |
| `collapse` | versions, étiquettes | `true` pour un projet qui publie une version par commit : les versions de la fenêtre deviennent une seule ligne de routine. |
| `discovery` | tous | `true` : le flux cherche ce que le guide ne couvre pas encore. Ses éléments vont dans la section `discovery`, et un élément compte selon son âge (`maxAgeDays`, 45), pas selon la fenêtre. |

## Le tri préalable

Chaque élément est retenu ou écarté par une règle, avec une raison. Seuls les éléments retenus arrivent au modèle.
Les règles :

- **Versions.** Les préversions (rc, alpha, beta, dev, nightly, preview, canary, snapshot) et les versions sous
  `minLevel` sont écartées. Une version dont les notes parlent d'un correctif de sécurité (security, CVE, GHSA,
  vulnerability) est retenue quand même.
- **Avis.** Un avis de faible gravité est écarté, de même qu'un avis déjà corrigé au plancher du guide : le plancher
  est hors de la plage vulnérable, ou la première version corrigée est égale ou inférieure au plancher, ou le
  correctif publié pour la branche du plancher l'est. Un avis High ou Critical que le plancher ne couvre pas est
  **urgent**, et le passage le traite en premier.
- **Modèles.** Les variantes quantifiées, les adaptateurs (LoRA) et les affinages d'un autre éditeur (en
  découverte) sont écartés.
- **Déjà vus.** Un élément dont l'adresse figure dans le fichier `seen` est écarté.

Le fichier des planchers :

```json
{ "floors": { "adv-memos": "26.11.0" } }
```

Le fichier des éléments déjà vus peut avoir n'importe quel format : chaque adresse `http(s)://` qu'il contient
compte. Un tableau des éléments déjà triés convient.

## Chaque semaine, sur GitHub

Le workflow réutilisable [`collect.yml`](../.github/workflows/collect.yml) fait la collecte sur GitHub. Il installe
l'agent, collecte, garde `watch.json` comme artefact et ouvre une issue avec le rapport. Ajoutez ce fichier au guide
sous le nom `.github/workflows/watch.yml` :

```yaml
name: Watch
on:
  schedule: [{ cron: "30 6 * * 1" }]   # le lundi, 6 h 30 UTC
  workflow_dispatch:
permissions:
  contents: read
  issues: write
jobs:
  watch:
    uses: DamienBecherini/vault-watch-agent/.github/workflows/collect.yml@v0.6.1
    with:
      days: 8
```

Le manifeste passe alors à `source = "issues"` avec `label = "watch"` : l'agent lit ces issues, dont
l'artefact contient la veille. Les paramètres du workflow :

| Paramètre | Par défaut | Ce que c'est |
| :-- | :-- | :-- |
| `days` | celle du fichier de flux | La fenêtre. |
| `guide` | `.` | Le dossier du guide dans son dépôt. |
| `label`, `artifact` | `watch`, `weekly-watch` | L'étiquette de l'issue et le nom de l'artefact ; `label` et `artifact` du manifeste doivent être les mêmes. |
| `title` | `Watch` | Le début du titre de l'issue. |
| `urgent_only` | `false` | N'ouvrir une issue que pour un avis urgent : un passage entre deux passages complets. |
| `open_issue` | `true` | `false` : garder l'artefact, ne rien ouvrir. |
| `agent_ref` | la version du workflow | La version de l'agent à installer. |

Aucune issue n'est ouverte quand rien n'est retenu.

## Le collecteur du guide IA on-premise

`vault-watch collect` est un portage de `scripts/watch-feeds.mjs` du guide IA on-premise. Il a les mêmes types de
flux et les mêmes règles, et son résultat a le même format. Sur les 63 flux de ce guide et sur la même fenêtre, les
deux donnent les mêmes éléments avec le même tri, les mêmes notes et les mêmes urgences (comparaison du 18 novembre
2026 : 172 éléments, 105 retenus depuis le 3 novembre ; 455 éléments, 241 retenus depuis le 1er juin). Un guide
peut garder son propre collecteur : l'agent ne lit que le `watch.json`.
