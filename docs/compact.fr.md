*[English version](compact.md)*

# Compactage : empêcher un guide de s'alourdir

Une veille ne fait qu'ajouter. Une note « depuis » à côté de l'ancienne phrase, une note de bas de page sous les
autres, le même avertissement recopié dans trois pages, une version gardée « pour mémoire » : chaque modification
est juste, et après quelques mois le guide pèse moitié plus sans que personne l'ait décidé. Le compactage est un
passage à part, distinct des veilles, qui repère ce qui pèse et propose de l'alléger. Rien n'est retiré sans
votre relecture : un allègement passe par la même relecture croisée, la même relecture humaine, les mêmes
miroirs, contrôles et pull request qu'une correction.

Il a trois parties. La première est gratuite ; les deux autres appellent le modèle et annoncent leur coût avant
de tourner.

| Partie | Ce qu'elle fait | Modèle |
| :-- | :-- | :-- |
| Tailles | Chaque page face à son budget, ses sections les plus lourdes, le poids de ses notes de bas de page, ce que le guide a pris en 90 jours | aucun |
| Rapport | Lit tout le guide et liste ce qui est répété, ce qui est de l'historique empilé, quelles sections sont plus longues que ce qu'elles disent. Ne modifie rien | un appel (le coût d'une relecture croisée) |
| Allègements | Pour les pistes que vous gardez : des modifications ciblées (texte actuel, texte proposé, raison), puis relecture croisée, relecture, miroirs et pull request | un passage |

## Tailles

```bash
vault-watch --guide ../mon-guide compact       # les pages au-dessus de leur budget, puis les plus lourdes ; sans modèle
vault-watch --guide ../mon-guide doctor        # une ligne : le poids du guide, sa croissance, les pages hors budget
```

Dans l'interface : « Vérifier le guide », contrôle « Taille des pages » (gratuit, coché d'office).

Le budget est une taille en Ko au-dessus de laquelle une page est signalée. Il vaut 30 Ko, sauf si le manifeste
dit autre chose :

```toml
[budget]
page_kb = 30                  # toutes les pages
[budget.pages]                # les pages d'un dossier ; le premier motif qui correspond l'emporte
"00-lexique/**" = 8
"05-solutions/**" = 20
```

Un dépassement est un avertissement, jamais un échec : il dit où regarder d'abord. La croissance est lue dans
Git (ce que pesait chaque page il y a 90 jours sur la branche courante) ; un guide hors de Git a des tailles et
pas de croissance. Une page en lecture seule (`[content] readonly`) est listée avec son poids et jamais
signalée : l'agent ne la modifie pas.

## Le rapport

```bash
vault-watch --guide ../mon-guide compact --report    # annonce le coût, demande, puis liste les pistes
```

Dans l'interface : « Vérifier le guide », contrôle « Compactage : ce qui alourdit le guide », avec son estimation.

Un appel lit toutes les pages du guide d'un coup, avec les pages les plus lourdes et leurs sections les plus
lourdes nommées, et liste trois sortes de pistes, les plus lourdes d'abord :

- **Répété** : le même fait, la même explication, le même avertissement ou tableau, énoncé longuement dans
  plusieurs pages. La piste dit quelle page garde l'énoncé complet ; les autres le raccourcissent et y renvoient.
  Un court rappel avec un lien n'est pas une répétition.
- **Historique** : ce qui est dépassé et reste à côté du fait courant : notes « depuis » successives, versions ou
  prix gardés pour mémoire, failles corrigées depuis longtemps dans des versions inférieures au minimum que le
  guide exige.
- **Long** : une section qui prend bien plus de place que ce qu'elle dit, et ce qui la rend longue.

Chaque piste cite ses passages, retrouvés dans les pages par le code. Le rapport ne modifie rien. Un guide trop
grand pour la fenêtre du modèle est lu chapitre par chapitre, et le rapport le dit : une répétition entre deux
chapitres échappe alors.

## Les allègements

Cochez les pistes à traiter et créez un passage de compactage (en ligne de commande :
`vault-watch fix <fil> --findings pistes.txt --compact`, une piste par ligne). Le modèle relit tout le guide et
propose des modifications ciblées, jamais une page réécrite en entier :

- une répétition est raccourcie et renvoie à la page qui garde l'énoncé complet, avec sa source ;
- l'historique empilé laisse la place au fait courant ;
- une section longue perd ce qui se répète, jamais un fait, un chiffre, une réserve ou une source.

Le passage suit ensuite le chemin de tous les autres : une relecture croisée écrite pour les allègements (perd-on
quelque chose ? la page se lit-elle encore à cet endroit ? le lien mène-t-il à une page qui existe ?), votre
relecture carte par carte, les miroirs, les contrôles du guide, la pull request. Sa branche s'appelle
`compact/<fil>`, et la pull request dit ce que pesaient les pages modifiées avant et après.

## Quel modèle

Le rapport et les allègements tournent sur le modèle de raisonnement des Réglages, à l'effort `high`. Décider ce
qui peut partir sans que le guide en dise moins est un jugement sur tout le guide : prenez le meilleur modèle dont
vous disposez pour ces deux étapes, et ne baissez pas leur effort.

Elles peuvent avoir leur propre modèle, les veilles gardant le leur : dans les Réglages, « Modèles et effort »,
« Régler une étape à part », choisissez un modèle (et un effort si vous le voulez fixe) pour « ce qui alourdit le
guide » (le rapport) et « allègements proposés » (les allègements). La relecture croisée des allègements est
l'étape « relecture croisée », commune avec les veilles : elle suit le rôle tant que vous ne la réglez pas à part
elle aussi. Voir [Choisir un modèle](choose-a-model.fr.md#un-modèle-pour-une-seule-étape).

Les estimations affichées avant chaque partie suivent le prix du modèle de chaque étape. Sur le guide IA on-prem
(environ 434 k tokens), aux prix publics de novembre 2026 : environ 2,80 $ pour le rapport et 5 $ pour un passage
d'allègements avec Claude Opus 5.5 ; avec Claude Fable 5.2 sur les deux étapes de compactage, environ 5,50 $ et
7,80 $. Un passage paie deux lectures du guide : ses propositions et sa relecture croisée ne partagent pas le
cache. Ce sont des estimations, à remplacer par des mesures après les premiers passages réels.

## Ce que le code vérifie lui-même

On ne confie pas à un modèle ce qu'un programme peut vérifier :

- **Un passage retiré en entier ne laisse pas de trou.** Un texte proposé vide retire les lignes avec leur saut
  de ligne : un tableau garde ses lignes ensemble, un paragraphe ne laisse pas deux lignes vides.
- **Une note qu'aucune phrase ne cite plus part avec l'allègement.** Quand un allègement retire la dernière
  phrase citant une note de bas de page, le programme ajoute le retrait de sa définition au même groupe :
  acceptés ou refusés ensemble.
- **Une phrase ne garde jamais une note disparue.** Un allègement qui retire la définition d'une note alors
  qu'une phrase la cite encore ne peut pas s'appliquer.
- **Ce qu'aucune page ne dira plus est signalé.** Sous chaque allègement, la relecture liste les versions,
  identifiants de failles, montants et liens que contient son texte et qu'aucune page du guide ne dira plus une
  fois les allègements appliqués. Retirer une répétition ne liste rien, puisque la page qui garde le fait le dit
  toujours ; retirer la seule mention d'un prix, si. C'est un signal, pas un refus : l'historique est retiré
  exprès.

## À la source

L'étape de proposition d'une veille a pour consigne de remplacer l'ancien fait plutôt que d'ajouter une note à
côté (« Remplacer, ne pas empiler », depuis la 1.0.1) : l'historique reste dans Git et dans la source. On empile
moins, donc on a moins à compacter.

## Quand

À la demande : après quelques mois de veilles, ou quand `doctor` montre des pages hors budget et un guide qui a
vite grossi. Commencez par la partie gratuite. Un rythme trimestriel convient à un guide veillé chaque semaine.
