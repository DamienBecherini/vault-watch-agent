*[English version](../watch-format.md)*

# Le format d'une veille (`watch.json`)

Une veille, c'est ce qui a changé dans le domaine d'un guide sur une fenêtre de quelques jours : nouvelles versions,
avis de sécurité, nouveaux modèles, annonces. Un collecteur la rassemble (le `vault-watch collect` de l'agent, ou ce que vous écrivez) et la remet à l'agent sous la forme d'un seul
`watch.json`. Cette page est le contrat entre les deux.

```json
{
  "schema": 1,
  "since": "2026-11-08",
  "until": "2026-11-16",
  "items": [
    {
      "title": "vllm-project/vllm v0.33.1",
      "url": "https://github.com/vllm-project/vllm/releases/tag/v0.33.1",
      "date": "2026-11-12T09:30:00Z",
      "triage": "keep",
      "reason": "release of a tool the guide covers",
      "urgent": false,
      "feed": "vllm", "domain": "engines", "tier": "A",
      "notes": "Notes de version, mises en cache par le collecteur : ce que le modèle lit de l'élément."
    }
  ],
  "errors": []
}
```

## Le fichier

| Clé | Obligatoire | Ce que c'est |
| :-- | :-- | :-- |
| `schema` | non | La version de ce format, `1` aujourd'hui (absente : 1). L'agent refuse un fichier dont le `schema` est plus récent que celui qu'il lit, et le dit : mettez l'agent à jour. |
| `since`, `until` | `until` | La fenêtre, en dates (`AAAA-MM-JJ`). `until` est la date du rapport de la passe et de sa branche. |
| `items` | oui | Les éléments, retenus ou écartés (ci-dessous). |
| `errors` | non | Ce que le collecteur n'a pas pu lire (un flux en panne, une limite de requêtes), une chaîne chacun, ou `{"feed": …, "error": …}` comme l'écrivent les deux collecteurs ; affiché, jamais bloquant. |
| `recheck` | non | Les candidats du registre de la découverte dont la date de revérification est arrivée (`{id, name, kind, state, reason, recheck, first_seen, url}`), écrits par `vault-watch collect` quand le manifeste nomme `[watch] candidates` ([Collecter une veille](collect.md#le-registre-des-candidats)). |
| `pages` | non | Ce que disait chaque page surveillée à cette veille (`{id du flux : {url, snapshot, changed, before}}`), pour que la collecte suivante compare ; écrit par `vault-watch collect` pour les flux de type `page`. Les passes de l'agent ne le lisent pas. |

Les autres clés (comptes, version du collecteur) sont permises et ignorées.

## Un élément

| Clé | Obligatoire | Ce que c'est |
| :-- | :-- | :-- |
| `title` | oui | Une ligne : ce qui s'est passé. |
| `url` | attendue | La source primaire : la page de version, l'avis, l'annonce. Le modèle l'ouvre pour vérifier un fait ; sans elle, il ne peut que croire les notes. |
| `date` | attendue | Quand c'est arrivé, en ISO 8601 (une date, ou une date et une heure) ; l'agent garde la date, et une correction énonce le fait avec elle. |
| `triage` | oui | `keep` ou `drop` : le tri du collecteur lui-même, par règle (une préversion, un correctif de routine, un flux hors sujet). Seuls les éléments `keep` arrivent au modèle. |
| `reason` | non | Pourquoi le collecteur l'a retenu ou écarté, en une ligne. |
| `urgent` | non | `true` pour un avis de sécurité à traiter avant les autres : il passe en tête de la passe. |
| `severity` | non | La gravité donnée par l'avis lui-même (`Critical`, `High`…). |
| `notes` | non | Ce que le modèle lit de l'élément : les notes de version, le texte de l'avis, mis en cache à la collecte ; pour un élément que son flux donne sans texte, le début de sa propre page (précédé de `(read from <url>)`). Plus elles contiennent de faits (versions, dates, chiffres), moins le modèle devine. Coupées à 4 000 caractères. Sans `notes`, `summary` est lu. |
| `feed`, `domain` | non | De quel flux et de quelle partie du guide vient l'élément ; affichés dans le rapport. |
| `tier` | non | La confiance due à la source : `A` primaire (notes de version, page de l'éditeur, avis), `B` secondaire réputée, `C` simple piste. |

Les clés inconnues restent dans le fichier et sont ignorées par l'agent.

## Comment l'agent la lit

Les éléments retenus reçoivent un identifiant propre à la passe (`W1`, `W2`…), les urgents d'abord, et passent au tri :
pour chacun, le modèle dit s'il rend une page du guide fausse (une correction), s'il pourrait l'enrichir (une piste
pour l'éditeur) ou s'il ne change rien ; ce que le modèle écarte est listé en fin de rapport avec sa raison. Les
éléments écartés par le collecteur ne sont pas lus.

## D'où elle vient

Le manifeste du guide le dit (`[watch]`, voir [Brancher son guide](connect-your-guide.md)) : un `watch.json` dans le
guide (`source = "file"`), l'artefact du run de workflow lié depuis une issue de la forge (`source = "issues"`), les
veilles que l'agent a collectées depuis les flux du guide (`source = "feeds"`, voir [Collecter une veille](collect.md)), ou
aucune.
