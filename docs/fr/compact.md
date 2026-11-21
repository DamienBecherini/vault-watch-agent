*[English version](../compact.md)*

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
| Tailles | Ce que pèse chaque page et ce qu'elle a pris, ses sections les plus lourdes, le poids de ses notes de bas de page, ce que le guide a pris en 90 jours | aucun |
| Rapport | Lit tout le guide et liste ce qui est répété, ce qui est de l'historique empilé, quelles sections sont plus longues que ce qu'elles disent. Ne modifie rien | un appel (le coût d'une relecture croisée) |
| Allègements | Pour les pistes que vous gardez : des modifications ciblées (texte actuel, texte proposé, raison), puis relecture croisée, relecture, miroirs et pull request | un passage |

## Tailles

```bash
vault-watch --guide ../mon-guide compact       # les pages qui ont beaucoup grossi, puis les plus lourdes ; sans modèle
vault-watch --guide ../mon-guide doctor        # une ligne : le poids du guide, sa croissance, les pages qui ont beaucoup grossi
```

Dans l'interface : « Vérifier le guide », contrôle « Taille des pages » (gratuit, coché d'office).

La bonne longueur d'une page dépend de son sujet : une page de référence sur la sécurité est longue, une entrée
de lexique est courte. Une page n'est donc pas jugée face à une taille fixe, mais face à elle-même : elle est
signalée quand elle a **beaucoup grossi** en 90 jours, de 5 Ko ou plus, ou d'un quart de son poids (et de 2 Ko
au moins). La ligne d'une page signalée donne sa taille actuelle et ce qu'elle a pris (`46 KB  +18.9 KB, +71%`).

```toml
[budget]
growth_kb = 5                 # une page qui a pris autant en 90 jours est signalée (valeur par défaut)
growth_percent = 25           # ou cette part de ce qu'elle pesait (valeur par défaut)
```

Un guide qui veut un plafond peut en fixer un, pour toutes les pages ou pour celles d'un dossier ; il n'y en a
aucun par défaut :

```toml
[budget]
page_kb = 30                  # toutes les pages
[budget.pages]                # les pages d'un dossier ; le premier motif qui correspond l'emporte
"00-lexique/**" = 8
"05-solutions/**" = 20
```

Une page signalée est un avertissement, jamais un échec : elle dit où regarder d'abord. La croissance est lue
dans Git (ce que pesait chaque page il y a 90 jours sur la branche courante) ; un guide hors de Git a des tailles
et pas de croissance, donc rien n'y est signalé sans plafond. Une page nouvelle n'est pas signalée. Une page en
lecture seule (`[content] readonly`) est listée avec son poids et jamais signalée : l'agent ne la modifie pas.

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
`vault-watch fix <fil> --findings pistes.txt --compact`, une piste par ligne). Le modèle relit le guide et
propose des modifications ciblées, jamais une page réécrite en entier :

- une répétition est raccourcie et renvoie à la page qui garde l'énoncé complet, avec sa source ;
- l'historique empilé laisse la place au fait courant ;
- une section longue perd ce qui se répète, jamais un fait, un chiffre, une réserve ou une source.

Les propositions prennent plusieurs appels quand les pistes sont nombreuses : les pistes qui partagent des pages
vont ensemble, et aucun appel ne se voit demander plus que sa réponse ne peut contenir (les allègements de trente
pistes ne tiendraient pas dans une seule réponse). Un appel qui échoue laisse ses pistes sans allègement, ce que
dit le rapport du passage ; les autres continuent.

Ce que lit chaque appel dépend du moteur :

- **L'API Claude** : tout le guide, à chaque fois. Le premier appel l'écrit dans le cache, et les autres partent
  quand il a commencé à répondre : ils lisent alors le cache au lieu de payer le guide une nouvelle fois (sur
  Claude Fable 5.2, environ 4,3 $ pour écrire le guide IA on-prem, puis 0,09 $ par appel qui le relit).
- **Claude Code, un serveur compatible OpenAI, un guide trop grand pour le modèle** : les pages que nomment les
  pistes de l'appel, en entier. Une piste nomme toutes les pages qu'elle concerne ; le modèle sait que le guide a
  d'autres pages qu'il ne voit pas, et garde ce qu'il ne retrouve pas ailleurs. Une piste qui ne nomme aucune
  page du guide (une ligne saisie à la main) reçoit le guide entier.

Le passage suit ensuite le chemin de tous les autres : une relecture croisée écrite pour les allègements, qui lit
tout le guide (perd-on quelque chose ? la page se lit-elle encore à cet endroit ? le lien mène-t-il à une page
qui existe ?), votre relecture carte par carte, les miroirs, les contrôles du guide, la pull request. Sa branche
s'appelle `compact/<fil>`, et la pull request dit ce que pesaient les pages modifiées avant et après.

## Entre deux compactages

Chaque passage, une veille ou un passage de correction aussi, dit ce qu'il change au poids des pages qu'il
modifie : attendu dans son rapport avant la relecture (« Weight, if every valid correction is applied », avec les
trois pages qui changent le plus), mesuré dans sa pull request et sur l'écran de publication. Une correction qui
ajoute un paragraphe là où une phrase suffirait se voit quand elle est proposée, pas un trimestre plus tard.

## Quel modèle

Le rapport et les allègements tournent sur le modèle de raisonnement des Réglages, à l'effort `high`. Décider ce
qui peut partir sans que le guide en dise moins est un jugement sur tout le guide : prenez le meilleur modèle dont
vous disposez pour ces deux étapes, et ne baissez pas leur effort.

Elles peuvent avoir leur propre modèle, les veilles gardant le leur : dans les Réglages, « Modèles et effort »,
« Régler une étape à part », choisissez un modèle (et un effort si vous le voulez fixe) pour « ce qui alourdit le
guide » (le rapport) et « allègements proposés » (les allègements). La relecture croisée des allègements est
l'étape « relecture croisée », commune avec les veilles : elle suit le rôle tant que vous ne la réglez pas à part
elle aussi. Voir [Choisir un modèle](choose-a-model.md#un-modèle-pour-une-seule-étape).

Les estimations affichées avant chaque partie suivent le prix du modèle de chaque étape. Sur le guide IA on-prem
(environ 434 k tokens), aux prix publics de novembre 2026 :

| | Claude Opus 5.5 | Claude Fable 5.2 sur les deux étapes de compactage |
| :-- | --: | --: |
| Le rapport | ≈ 3,4 $ | ≈ 6,7 $ (mesuré le 20/11/2026 : 6,28 $, 48 k tokens écrits à l'effort `high`) |
| Un passage d'allègements, 10 pistes | ≈ 7,4 $ | ≈ 11,3 $ |
| Un passage d'allègements, 30 pistes | ≈ 13,1 $ | ≈ 20,4 $ (mesuré le 20/11/2026 : 17,79 $ avant les miroirs) |

Un passage paie le guide deux fois, quelles que soient les pistes : écrit dans le cache par ses propositions, puis
par sa relecture croisée, qui tourne sur son propre modèle avec une autre question (environ 4,7 $ ici avec
Opus 5.5 pour les deux, 6,9 $ avec Fable 5.2 pour les propositions). Puis une part par piste : ce qu'écrivent les
propositions, et le miroir de chaque page touchée.

Le passage mesuré le 20/11/2026 (30 pistes, Fable 5.2 à l'effort `high` pour les propositions, Opus 5.5 pour la
relecture croisée) : quatre appels de propositions ont écrit 250 k tokens, entre 39 k et 93 k chacun, et seul le
premier a payé l'écriture du guide (14,73 $ en tout) ; la relecture croisée a coûté 3,06 $. Il a proposé 195
allègements dans 39 pages, dont 40 notes retirées par le programme, pour 32 Ko de moins sur 891 Ko. Les autres
chiffres sont des estimations.

Ce qu'un modèle réfléchit est facturé comme de la sortie et compte dans la limite de ce qu'un appel peut écrire.
Le rapport liste au plus 30 pistes pour que sa réponse reste loin de cette limite ; une réponse coupée à la limite
est facturée et perdue, ce que le journal et le coût du contrôle montrent alors.

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
