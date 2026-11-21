*[English version](../write-an-engine.md)*

# Écrire un moteur

Un moteur, c'est ce qui appelle un modèle pour l'agent. L'agent en fournit trois :

| Nom | Ce qu'il appelle |
| :-- | :-- |
| `api` | l'API Claude, facturée au token |
| `claude-code` | Claude Code sur un abonnement Claude |
| `openai` | tout serveur compatible OpenAI, hébergé ou sur votre machine |

Pour atteindre un autre modèle, vous pouvez écrire un moteur dans un paquet à vous. L'agent le trouve dès qu'il est
installé, et ses Réglages le proposent alors comme les autres.

## Ce que le graphe demande à un moteur

Une méthode, `parse`, appelée une fois par étape. Elle rend la réponse du modèle sous la forme d'un objet du schéma
de l'étape, et l'usage de l'appel.

```python
reponse, usage = moteur.parse(system=..., prompt=..., schema=Triage, effort="medium", node="triage",
                              context=None, web=False)
```

| Argument | Ce que c'est |
| :-- | :-- |
| `system`, `prompt` | Les consignes et la demande. |
| `schema` | Un modèle Pydantic. La réponse doit le respecter : le graphe ne lit jamais de texte libre. |
| `effort` | De `low` à `max`, selon l'étape. Il se décale de `self.effort_step` avec `shift_effort` (l'effort du rôle dans les Réglages). |
| `node` | Le nom de l'étape. Chaque message d'erreur commence par lui. |
| `context` | Un long texte partagé par plusieurs appels (le guide). Placez-le en premier pour qu'un cache puisse le réutiliser. |
| `web` | Le modèle peut chercher sur le web et lire des pages avant de répondre. |

Le protocole est `llm.Engine`, et le contrat ci-dessous le vérifie. `parse` doit :

- **Rendre** `(objet, usage)`. `usage` contient au moins `llm.USAGE_KEYS` : `node`, `model`, `engine`, `effort`, les
  tokens `input`, `output`, `cache_read` et `cache_write`, `web_searches` et `cost_usd` (0.0 quand rien n'est
  facturé).
- **Écrire** cet usage dans le journal avec `self.record(usage)`, par la classe de base `_Journal`. La page Coûts et
  `vault-watch costs` le lisent.
- **Lever `llm.ModelError`**, sans jamais rendre une demi-réponse, quand :
  - la réponse ne respecte pas le schéma ;
  - le modèle a refusé, ou sa réponse a été coupée ;
  - le serveur est injoignable.

`capabilities()` dit sur quoi les étapes peuvent compter. Elle rend un `llm.Capabilities` :

| Champ | Valeurs |
| :-- | :-- |
| `context` | Les tokens qu'un appel peut lire. Un guide plus grand, moins une réserve, est relu chapitre par chapitre. |
| `structured` | `native` (le serveur impose le schéma) ou `instruction` (le schéma est dans les consignes). |
| `web` | `native` (les outils du fournisseur), `tools` (la recherche et la lecture de pages de l'agent), `fetch` (des pages seulement) ou `none`. Les étapes qui vérifient sur le web disent ce qui leur manque. |
| `efforts` | Les niveaux d'effort que le moteur envoie ; `()` quand il n'en envoie aucun. |
| `billing` | `token`, `subscription` ou `none` (un modèle local). La page affiche le coût d'une action en conséquence. |
| `exact_count` | `True` quand `count_tokens(texte)` compte exactement ; sinon l'agent estime. |

Un moteur sans web peut quand même l'offrir : `webtools.WebTools` et `webtools.Budget` fournissent la recherche, la
lecture de pages, les limites et la définition des outils. `openai_compat.py` montre la boucle.

## Le déclarer

Un `llm.EngineKind` dit à l'agent comment créer le moteur et ce qu'il propose :

| Champ | Ce que c'est |
| :-- | :-- |
| `name`, `label` | Le nom dans `settings.json` (`"engine": "ollama"`) et le libellé dans les Réglages. |
| `make(role, journal, settings)` | Le client d'un rôle (`reasoning` ou `translator`), sur le modèle que `settings` donne à ce rôle. Il est appelé une fois de plus pour chaque étape que l'utilisateur a réglée à part, avec le modèle de cette étape à la place de celui du rôle (dans `settings["models"][role]`, et dans l'option `models` de votre moteur s'il en a une). |
| `models(settings)` | Facultatif. Les modèles qu'il propose : `[{id, name, context, priced}]`. |
| `check(options)` | Facultatif. Il vérifie les options du moteur (`settings["engines"]["<nom>"]`), complète les valeurs par défaut et lève une erreur sur une mauvaise valeur. |
| `model_of(settings, role)` | Le modèle d'un rôle. |
| `options` | Les valeurs par défaut de ses options. |
| `protocol` | La version du protocole des moteurs qu'il implémente : `1` (par défaut, `llm.ENGINE_PROTOCOL`). Un moteur d'un autre protocole n'est pas chargé ([fr/compatibility.md](compatibility.md)). |

Pointez vers lui un point d'entrée du groupe `vault_watch_agent.engines`, dans le `pyproject.toml` de votre paquet :

```toml
[project.entry-points."vault_watch_agent.engines"]
ollama = "ollama_engine:KIND"
```

`llm.engines()` le charge au démarrage. Si un moteur ne se charge pas, les Réglages le signalent et l'agent continue
sans lui.

## L'exemple : l'API propre d'Ollama

[`examples/engines/ollama_engine.py`](../../examples/engines/ollama_engine.py) est un moteur complet en 90 lignes,
pour `POST /api/chat` :
- le schéma va dans `format`, qu'Ollama impose ;
- le contexte ouvre le message système ;
- l'usage se lit dans `prompt_eval_count` et `eval_count` ;
- il n'a pas de web, et rien n'est facturé.

C'est un exemple : Ollama parle aussi le protocole OpenAI, donc le moteur `openai` l'atteint déjà.

## Les tests de contrat

[`tests/engine_contract.py`](../../tests/engine_contract.py) vérifie un moteur avec des réponses enregistrées, sans
réseau et sans modèle :

| Scénario | Ce que le moteur doit faire |
| :-- | :-- |
| valid | Rendre l'objet, et l'usage avec ses clés dans le journal. |
| invalid | Lever `ModelError` en nommant l'étape, pour une réponse qui ne respecte pas le schéma. |
| refusal | Lever `ModelError` en nommant l'étape. |
| truncated | Lever `ModelError` en nommant l'étape, pour une réponse coupée à la limite de sortie. |
| web | N'offrir le web que s'il est demandé, et compter les recherches. Ignoré pour un moteur dont le `web` vaut `none`. |

Pour un refus, un serveur qui le signale (une raison d'arrêt, un champ `refusal`) donne une erreur qui le dit.
Sinon, le refus arrive sous forme de texte, qui ne respecte pas le schéma.

Écrivez un adaptateur qui rejoue les réponses de votre serveur, puis appelez `check_engine` :

```python
from engine_contract import check_engine

class MonAdaptateur:
    def make(self, scenario, journal):      # le moteur, son transport rejouant `scenario`
        ...
    def saw_web(self):                      # si le dernier appel a offert le web au modèle
        ...

def test_mon_moteur(tmp_path):
    check_engine(MonAdaptateur(), tmp_path)
```

[`tests/test_engine_contract.py`](../../tests/test_engine_contract.py) contient les adaptateurs des moteurs de l'agent
et de l'exemple. Ils remplacent :
- le client du SDK, pour `api` ;
- `claude -p`, pour `claude-code` ;
- le transport HTTP (`httpx.MockTransport`), pour `openai` et l'exemple Ollama.
