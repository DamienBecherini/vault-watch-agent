*[English version](../compatibility.md)*

# Ce qui reste stable

À partir de 1.0, quatre formats sont figés. Chacun porte un numéro de version, et l'agent refuse un numéro qu'il ne
connaît pas avec un message qui dit quoi mettre à jour. Un changement de l'un d'eux est un nouveau numéro, jamais un
changement de sens silencieux.

| Format | Où | Numéro | Écrit par |
| :-- | :-- | :-- | :-- |
| Le manifeste d'un guide | `vault-watch.toml` à la racine du guide | `schema = 1` | vous ([fr/connect-your-guide.md](connect-your-guide.md)) |
| Une veille | `watch.json` | `"schema": 1` | votre collecteur ou `vault-watch collect` ([fr/watch-format.md](watch-format.md)) |
| Le protocole des moteurs | `llm.Engine`, `llm.EngineKind` | `EngineKind.protocol = 1` | un paquet de moteur ([fr/write-an-engine.md](write-an-engine.md)) |
| Les réglages | `~/.vault-watch/settings.json` | `"schema": 1` | la page Réglages, ou vous |

## Les règles

- **À numéro égal, seulement des ajouts.** Une nouvelle clé facultative, une nouvelle source de veille, un nouveau
  champ facultatif d'un élément : un fichier valide le reste et garde son sens. Une clé n'est jamais retirée ni
  changée de sens sans nouveau numéro.
- **Un fichier plus récent que l'agent est refusé**, pas lu à moitié : `schema 2 … update vault-watch-agent`. Sinon
  un agent plus ancien perdrait ce qu'il ne connaît pas, et pour les réglages il enregistrerait le fichier sans.
- **Un fichier plus ancien que l'agent est migré.** Les réglages sont migrés à la lecture, un numéro après l'autre,
  et réécrits au format courant au prochain enregistrement. Pour le manifeste et la veille, un nouveau numéro arrive
  avec sa migration dans les notes de version, et l'agent lit encore le numéro précédent pendant une version majeure.
- **Le protocole des moteurs est vérifié au chargement.** Un paquet de moteur qui implémente un autre protocole
  n'est pas chargé : la page Réglages l'affiche avec la raison, et les autres moteurs continuent de fonctionner.
- **Les noms d'avant 1.0 restent lus.** `source = "github-issue"` est lu comme `issues` (la source lit aussi les
  issues d'une forge Gitea) ; un fichier de réglages sans `schema` est lu comme schema 1.

## Ce qui n'est pas figé

Les fichiers de travail de l'agent (`checkpoints.sqlite`, le journal des passes, les rapports d'une vérification,
les fichiers de `~/.vault-watch/guides/<guide>/`) appartiennent à l'agent : une version peut les changer, et le dit dans ses
notes de version. Les consignes au modèle, les étapes d'une passe et l'interface web évoluent à chaque version. Les
modules Python ne sont pas une bibliothèque : seuls `llm.Engine` et `llm.EngineKind`, pour les paquets de moteur,
font partie du protocole.
