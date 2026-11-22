*[English version](../README.md)*

# La documentation de vault-watch-agent

Toutes les pages, rangées selon la question à laquelle elles répondent. Chaque page est ici en français, et en
anglais dans [`docs/`](../), sous le même nom ; les captures d'écran sont dans [`images/`](../images/). Ce qu'est
l'agent, comment l'installer et les pages de son interface : le [README](../../README.fr.md) du dépôt.

```mermaid
flowchart LR
  readme["README<br/>ce qu'il est, démarrage"] --> overview["Présentation<br/>la boucle, la feuille de route"]
  readme --> connect
  subgraph start["Brancher et alimenter son guide"]
    connect["Brancher son guide<br/>le manifeste"] --> collect["Collecter une veille"]
    collect --> format["Le format d'une veille"]
  end
  subgraph agent["Ce que fait l'agent"]
    run["Une veille étape par étape"]
    check["Vérifier le guide"] --> news["Nouveautés"]
    check --> compact["Compactage"]
    news --> chapters["Chapitres"]
  end
  subgraph models["Modèles et coûts"]
    model["Choisir un modèle"] --> engine["Écrire un moteur"]
    costs["Coûts"]
  end
  subgraph trust["Sécurité et stabilité"]
    security["Sécurité"]
    stable["Ce qui reste stable"]
  end
  subgraph dev["Pour les développeurs"]
    code["Structure du code"] --> plan["Le plan modulaire<br/>(historique)"]
  end
  connect --> run
  run --> check
  run --> costs
  connect --> model
  connect --> security
  overview --> code
```

## Découvrir

| Page | Ce à quoi elle répond |
| :-- | :-- |
| [Présentation](presentation.md) | Pourquoi un guide technique vieillit vite, toute la boucle d'une veille à une pull request fusionnée, les trois pauses, ce que l'agent a produit sur le guide IA on-prem, ce que ça vaut, la suite. Cinq schémas |

## Brancher et alimenter son guide

| Page | Ce à quoi elle répond |
| :-- | :-- |
| [Brancher son guide](connect-your-guide.md) | Les trois commandes pour démarrer, le manifeste `vault-watch.toml` clé par clé, ce que débloque chaque partie facultative, le guide d'exemple pour essayer. Une capture de la page « Chapitres » |
| [Collecter une veille](collect.md) | `vault-watch collect` : les flux que suit un guide (`feeds.json`), le pré-tri sans modèle, la page « Sources suivies » et le contrôle des sources, le workflow hebdomadaire sur GitHub. Une capture de cette page |
| [Le format d'une veille](watch-format.md) | `watch.json` champ par champ, pour un guide qui apporte son propre collecteur |

## Ce que fait l'agent

| Page | Ce à quoi elle répond |
| :-- | :-- |
| [Une veille étape par étape](run.md) | Un élément d'une veille à travers chaque étape : ce que lit chacune, ce qui décide, ce qui peut arrêter une modification ; un exemple avec son coût ; l'écran de relecture, la pause pour retoucher les pages et l'écran de publication ; « Mettre à jour mon dossier » après la fusion ; pauses et reprises ; la synchronisation des langues. Un schéma, des captures de la relecture, des retouches, de l'écran de publication, de « À traiter » et de la page « Langues » |
| [Vérifier le guide](check.md) | Les onze contrôles du catalogue et leurs trois sortes : ce que lit chacun, son estimation et ce qu'il a coûté, ce qu'il trouve, où partent ses pistes ; la liste des vérifications et la page d'une vérification ; la vie d'une piste ; les passes où elles partent ; « Signaler ou proposer ». Un schéma, une capture du catalogue |
| [Nouveautés](news.md) | Ce qu'un lecteur chercherait et ne trouve pas : les pistes tirées du guide et du web, une idée à soi, des liens à lire en entier (une vidéo aussi), les ajouts et leur vérification sur le web, creuser une piste, ce que lit et coûte chaque appel. Des captures de « Des liens à lire en entier » et des pistes |
| [Chapitres](chapters.md) | Les trois étapes qui travaillent sur une partie du guide à la fois, d'où viennent les chapitres, la règle automatique et pourquoi 150 Ko et 20 Ko, ce que coûte un découpage mal adapté. Un schéma de la règle |
| [Compactage](compact.md) | Empêcher un guide de s'alourdir : les tailles, le rapport, les coupes, quel modèle, ce que le code vérifie lui-même |

## Modèles et coûts

| Page | Ce à quoi elle répond |
| :-- | :-- |
| [Choisir un modèle](choose-a-model.md) | Les modèles mesurés sur le guide IA on-prem, ce que chaque étape demande à un modèle, un modèle pour une étape, ce que change chaque réglage, ce qui a été essayé, mesurer son propre modèle. Une capture des Réglages |
| [Écrire un moteur](write-an-engine.md) | Ce que le graphe demande à un moteur, comment le déclarer, l'exemple de l'API propre d'Ollama, les tests de contrat |
| [Coûts](costs.md) | Ce qui fait le prix d'un appel (le cache de prompt avant tout), où part l'argent selon la sorte de passe, comment sont faites les estimations et pourquoi elles se trompent, le prix catalogue barré sur un abonnement, d'où viennent les prix, le journal et la page « Coûts », ce qui fait baisser le coût. Un schéma du cache, une capture de la page « Coûts » |

## Sécurité et stabilité

| Page | Ce à quoi elle répond |
| :-- | :-- |
| [Sécurité](security.md) | Clés et jetons gardés comme références, ce que le modèle peut faire et ce qu'il ne peut pas, ce qui sort de la machine, le serveur local, ce qu'il faut vérifier avant de brancher un guide |
| [Ce qui reste stable](compatibility.md) | Les quatre formats figés depuis 1.0 (manifeste, veille, protocole des moteurs, réglages), les règles d'un changement, ce qui n'est pas figé |

## Pour les développeurs

| Page | Ce à quoi elle répond |
| :-- | :-- |
| [Structure du code](code.md) | Les modules et leurs dépendances, le graphe nœud par nœud, l'état, un appel au modèle de bout en bout, la pause et la reprise d'une passe, les tests. Six schémas |
| [Le plan modulaire](../modular-plan.md) | Le plan de la phase G, d'un seul guide à un agent que tout guide peut utiliser. Gardé comme historique, en anglais seulement |

À la racine du dépôt : [ROADMAP](../../ROADMAP.md), [CHANGELOG](../../CHANGELOG.md),
[CONTRIBUTING](../../CONTRIBUTING.md) (en anglais).
