*[English version](choose-a-model.md)*

# Choisir un modèle

Depuis la 0.6.0, l'agent tourne sur n'importe quel moteur : l'API Claude, Claude Code, ou tout serveur de l'API de
chat d'OpenAI, hébergé ou local ([Écrire un moteur](write-an-engine.fr.md)). Tourner n'est pas bien faire le travail.
Cette page dit avec quels modèles l'agent est utilisé, ce qui a été essayé au-delà, et pourquoi rien de plus n'est
promis.

## Les modèles du guide IA on-premise

L'agent tient à jour le guide [Zero to Hero : IA on-premise](https://github.com/DamienBecherini/ia-on-prem-vault)
avec :

| Rôle | Étapes | Modèle |
| :-- | :-- | :-- |
| raisonnement | tri de la veille, propositions, relecture globale du guide, balayage | Claude Opus 5.5 |
| traduction | le miroir anglais des pages corrigées | Claude Sonnet 5.5 |

par l'API Claude (facturée au token) ou par Claude Code (l'abonnement). Chaque correction passe par l'écran de
relecture et une pull request qu'un humain fusionne : c'est cette relecture, pas un score, qui garantit le guide.

Ce sont les seuls modèles sur lesquels le projet s'engage. Avec un autre, le moteur fonctionne (il passe les
[tests de contrat](../tests/engine_contract.py)), la qualité des corrections n'est pas mesurée, et il faut vérifier
ses propositions avant de croire une veille qui dit « rien à changer ».

## Ce que chaque étape demande au modèle

- **Tri** : lire les éléments de la veille et garder ceux qui peuvent toucher le guide. Des appels courts ; un
  modèle modeste y arrive.
- **Propositions** : décider, pour chaque élément gardé et ses extraits du guide, si une phrase est devenue fausse et
  comment la réécrire. L'étape de jugement : un modèle trop prudent répond « pas de changement » et la veille semble
  propre.
- **Relecture globale et balayage** : relire les corrections face au guide entier, avec le web, et trouver les
  autres pages qui énoncent le même fait. L'étape la plus longue, et celle d'où viennent la plupart des corrections
  (7 des 11 de la veille #77). Une fenêtre plus petite que le guide fait lire le guide par chapitre : plus d'appels,
  et un fait énoncé dans deux chapitres n'est plus vu d'une seule lecture.
- **Miroir** : traduire les passages corrigés. Un bon modèle de traduction suffit.

## Un modèle pour une seule étape

Les Réglages donnent un modèle et un effort à deux rôles : le raisonnement (tri, propositions, relecture croisée,
vérifications du guide, compactage) et la traduction (le miroir, le contrôle des traductions). Une étape peut être
réglée à part de son rôle : « Modèles et effort », puis « Régler une étape à part » sous le rôle. Elle tourne
alors sur le modèle choisi pour elle, et à l'effort choisi pour elle s'il y en a un : cet effort s'applique tel
quel, alors que « plus bas » et « plus haut » du rôle décalent d'un cran toutes les autres étapes. Tout le reste
suit le rôle.

L'usage pour lequel c'est fait : le [compactage](compact.fr.md) sur le modèle le plus fort, quelques fois par an,
pendant que les veilles hebdomadaires restent sur le modèle mesuré ici. Les estimations et le journal des coûts
suivent le modèle de chaque étape. Dans `settings.json` :
`"steps": {"compaction": {"model": "claude-fable-5-2", "effort": "high"}}`.

Une étape peut aussi avoir son propre moteur (`"steps": {"news": {"engine": "claude-code"}}`) : la recherche de
nouveautés par un abonnement, par exemple, pendant que les veilles restent sur l'API. Sans modèle à elle, une telle
étape prend le modèle que son rôle a avec ce moteur. Si son moteur ne peut pas servir (l'API sans clé), l'erreur
arrive quand cette étape est demandée, pas avant.

Trois niveaux, du plus général au plus particulier :

| Niveau | Où | S'applique à |
| :-- | :-- | :-- |
| Les valeurs par défaut | L'agent lui-même | Une machine où rien n'a été réglé |
| Les Réglages | « Moteur », « Modèles et effort », « Régler une étape à part » | Tous les passages à partir de là |
| Ce passage seulement | « changer pour cette fois », à côté de chaque contrôle et au-dessus du bouton qui crée un passage | Ce passage, jusqu'à sa dernière étape (les miroirs après la relecture) ; les Réglages ne sont pas touchés |

Chaque écran qui lance un passage montre ce qui fera tourner chacune de ses étapes (moteur, modèle, effort) et
comment c'est payé, avant le clic. Un moteur imposé à toute une commande (`VAULT_WATCH_ENGINE`) l'emporte sur les
trois.

## Ce qui a été essayé

**Un modèle local sur un portable.** Qwen3.6-35B-A3B (llama.cpp, quantifié, fenêtre de 64k) sur un GPU de portable
de 8 Go. Il répond à chaque étape dans le schéma ; sur le guide exemple, lu en entier d'un seul appel, sa relecture
globale a trouvé la contradiction plantée entre deux chapitres. Sur la
veille #77 rejouée par extraits (sans relecture globale), il a gardé le bon élément, un avis de sécurité LiteLLM, a vu
que la version minimale du guide était inférieure à celle de l'avis, puis a refusé de changer la phrase : aucune
proposition, là où Claude Opus 5.5 en a fait trois, toutes justes. Un essai sur une veille : un signe, pas une mesure.

Les modèles capables de l'étape des propositions en local demandent bien plus de mémoire : une carte graphique de
32 Go ou plus, ou un moteur qui lit un grand modèle depuis le SSD (InferSSD ou équivalent) sur une telle carte. Le
projet n'en a pas : aucun modèle local n'est recommandé.

**Un modèle hébergé par le moteur compatible OpenAI.** Claude Haiku 5.5 par la couche OpenAI d'Anthropic, sur le
guide exemple seulement, pour essayer le moteur lui-même (schéma dans les instructions, recherche web par SearXNG,
facturation au token). Cela ne dit rien des autres modèles hébergés : pour un modèle Claude, prendre le moteur API
Claude.

## Mesurer son propre modèle

`vault-watch eval` rejoue une veille passée sur le guide tel qu'il était, jusqu'à la relecture, et compare les
propositions à la pull request qu'un humain a fusionnée ensuite :

```bash
vault-watch eval --issue 77 --at <commit avant la PR> --truth <base>..<head> --variant keyword --judge claude-code
```

`keyword` s'arrête avant la relecture globale (quelques minutes) ; `full` la fait (le guide entier, bien plus long sur
un modèle local). Lire le résultat avec ses limites :

- **Le juge est un modèle.** Il apparie chaque proposition aux morceaux du diff fusionné. Par défaut c'est un modèle
  Claude (`--judge api|claude-code`), pour qu'un modèle local ne se note pas lui-même ; mais Claude jugeant les
  propositions de Claude n'est pas neutre non plus. Lire l'appariement dans le fichier de résultat, pas seulement les
  chiffres.
- **La vérité, c'est ce que l'humain a fusionné.** Pour la veille #77, cette pull request était elle-même un run de
  l'agent sur Claude Opus, vérifié et fusionné par un humain : rejouer Opus mesure à quel point il refait un run
  relu, pas une vérité indépendante. Une veille traitée à la main (comme la #30) est un test plus juste.
- **Une veille est un cas.** Plusieurs veilles, de plusieurs natures (sécurité, versions, prix), avant de décider.

Les fichiers de résultat des essais ci-dessus sont dans [`metrics/eval/`](../metrics/eval/).
