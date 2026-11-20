*[English version](news.md)*

# Chercher les nouveautés : ce qu'un lecteur chercherait et ne trouve pas

Une veille suit les sources qu'elle connaît déjà. Ce qu'aucune n'annonce reste hors du guide : une nouvelle
génération de matériel chez un constructeur que personne n'a ajouté aux flux, un sujet devenu une obligation, un
outil apparu depuis la rédaction. Et ce qu'une veille voit mais met de côté comme « ajout possible » n'est jamais
écrit : cela reste une ligne dans un rapport. Ce passage est à part des veilles. Il cherche ce qui manque et
propose de l'ajouter ; rien n'est écrit sans votre relecture, et un ajout suit le chemin d'une correction :
relecture croisée, relecture, miroirs, contrôles du guide, pull request.

Il a deux parties. Les deux appellent le modèle et annoncent leur coût avant de tourner.

| Partie | Ce qu'elle fait | Web |
| :-- | :-- | :-- |
| Pistes | Lit tout le guide, et ce que les veilles passées ont mis de côté, et liste ce qu'il faut aller vérifier. Ne vérifie rien, ne modifie rien | non |
| Ajouts | Pour les pistes que vous gardez : vérifie chacune sur des sources primaires, puis propose où l'écrire, ou dit pourquoi non | oui |

> **Limite.** Ce passage ajoute dans les pages existantes : il n'écrit jamais de nouvelle page. Quand un sujet
> demanderait une page à lui, il le dit, en tête de l'écran de relecture, de son rapport et de la pull request, et
> vous laisse décider.

## Les pistes

```bash
vault-watch --guide ../mon-guide news          # annonce son coût et demande avant l'appel
```

Dans l'interface : « Vérifier le guide », contrôle « Nouveautés : ce qu'un lecteur chercherait et ne trouve pas ».

Un appel lit toutes les pages du guide d'un coup. Il liste au plus 30 pistes, de trois sortes :

| Sorte | Ce que c'est |
| :-- | :-- |
| `Newer` | Ce que le guide présente comme actuel et qui a sans doute évolué : une génération de produit, une famille de modèles, une version majeure, une grille de prix, une règle en vigueur |
| `Missing` | Un sujet, un outil, un modèle, un matériel, un risque ou une obligation que le guide doit à ses lecteurs et qu'aucune page ne couvre |
| `Seen by the watch` | Un élément que des veilles passées ont mis de côté comme ajout possible, et que le guide ne couvre toujours pas |

Une piste est une question, pas un fait. Le modèle ne vérifie rien à ce stade, et ce qu'il sait peut être plus
ancien que le guide : on lui demande quoi vérifier et sur quel genre de source primaire, jamais un chiffre, une
version ou une date. Le seuil d'ajout propre au guide (son contrat, `[rules] brief` du manifeste) lui est donné.

Les éléments mis de côté par les veilles sont lus dans les rapports des passages gardés sur la machine (leur
section « Addition candidates »), sur les 120 derniers jours, chaque adresse une fois : ni modèle ni réseau pour
cette partie.

Les pistes qui ne concernent que des pages en lecture seule sont laissées de côté. Comme pour tout contrôle,
vous gardez les pistes que vous voulez, vous écartez les autres, et celles gardées partent dans un passage.

## Les ajouts

```bash
vault-watch --guide ../mon-guide fix add-2026-11-20 --findings pistes.txt --add
```

Dans l'interface : cochez les pistes, puis « Créer une passe ajouts » ; le bouton affiche une estimation qui suit
le nombre de pistes cochées.

Pour chaque piste, le modèle cherche sur le web et ouvre des sources primaires, puis décide :

- rien de nouveau, rien qu'une source primaire établisse, déjà couvert, ou sous le seuil du guide : aucune
  modification, et la raison en une ligne, dans le rapport du passage ;
- le guide dit quelque chose de dépassé : une correction là où c'est dit, le fait actuel à la place de l'ancien ;
- le guide ne l'a pas : un ajout là où un lecteur le chercherait (une phrase dans son paragraphe, une ligne dans
  le tableau qui liste ces choses, un court paragraphe sous le bon titre), avec sa source citée comme la page
  cite les siennes ;
- il faudrait une page à part : la page n'est pas écrite. Le rapport dit « needs a page », avec ce qu'elle
  contiendrait et où ; écrire une nouvelle page reste votre décision.

Les modifications passent ensuite par la relecture croisée d'une veille (tout le guide, et la source citée
rouverte), votre relecture, les miroirs, les contrôles du guide et la pull request, sur une branche
`feat/<passage>`.

## Ce que lit chaque appel, et ce que cela coûte

Les pistes prennent un appel, qui lit tout le guide. Les ajouts prennent plusieurs appels, quatre pistes chacun,
regroupées par les pages qu'elles nomment : chaque tour de recherche relit ce que l'appel a rassemblé jusque-là,
donc un long appel coûte bien plus que plusieurs courts. Chaque appel lit tout le guide. Sur l'API Claude, le
premier appel l'écrit dans le cache et les autres le lisent là ; avec un autre moteur, les appels se suivent.

Les estimations ci-dessous valent pour le guide IA on-prem (129 pages, environ 430 000 tokens), avec Opus 5.5
pour les pistes, les ajouts et la relecture croisée. Elles ne sont pas encore mesurées : les constantes sont
comptées large et seront réglées sur les premiers passages réels.

| | Estimation |
| :-- | :-- |
| Les pistes | ≈ 2,80 $ |
| Un passage d'ajouts | ≈ 4,40 $, plus ≈ 0,75 $ par piste gardée |

Les étapes « pistes de nouveautés » et « ajouts vérifiés sur le web » apparaissent dans les Réglages, où chacune
peut tourner sur un modèle à elle.

## Ce qu'il ne fait pas

- Il n'écrit pas de nouvelle page, ni de nouvelle entrée de lexique dans un fichier à elle : il dit qu'il en
  faudrait une.
- Il ne remplace pas la veille : la veille lit chaque semaine ce que publient ses sources, pour quelques
  centimes ; ce passage cherche, de temps en temps, ce qu'aucune source n'annonce.
- Il ne contrôle pas ce que le guide dit déjà (les contrôles « Cohérence de tout le guide » et « Revérification
  des affirmations datées » le font).

## Quand

Après un compactage plutôt qu'avant : ce passage ajoute au guide, et il le lit en entier. Une fois par trimestre
est un rythme raisonnable pour un guide qu'une veille hebdomadaire suit déjà, ou quand un sujet bouge vite.
