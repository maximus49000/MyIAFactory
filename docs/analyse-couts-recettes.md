# Analyse des coûts et du temps : trois runs de « Recettes du frigo » (MyFridgeCleaner)

Date : 2026-11-19. Même évolution, trois fois, dans le bureau : « proposer une liste de recettes à partir du contenu du
frigo ». Code remis à la base `23346a2` entre les runs (tags `run1-fin`, `run2-fin`, `run3-fin` dans le dépôt du projet).
Prix : ceux du bureau (Sonnet 5,5 : 2 / 10 / 0,1 / 2,5 $ par million pour entrée / sortie / cache lu / cache écrit ; Haiku 5,5
pour la livraison), 1 $ = 0,9117 €.

**Mesuré** = relevé du bureau (`usage-historique.jsonl`, vue Facturation). **Estimé** = mon calcul, hypothèses dites.

## Synthèse (à lire d'abord)

Évolution « liste de recettes depuis le frigo » faite 10 fois dans le bureau (MyFridgeCleaner) et une fois dans une conversation.
Coûts mesurés par le bureau, vérifiés contre les transcriptions des agents (écart de 1 % sur les tokens).

| Run | Coût | Durée | Valide | Remarque |
|---|---|---|---|---|
| 1 | 2,82 € | 70 min | oui | départ : cloud sans SDK, 35 min de blocage |
| 2 | 2,30 € | 37 min | oui | code sur le poste |
| 3 | 1,92 € | 25 min | oui | |
| 4 | 1,09 € | 20,5 min | oui | maquettes, compilation séparée et 2e session de code retirées |
| 5 | **0,53 €** | 14,4 min | oui | cadrage sans question ; meilleur run |
| 6 | 1,36 € | 28,7 min | oui | boucle de correction (0,67 €) |
| 7 | 0,41 € | 14,2 min | **non** | code restauré depuis git |
| 8 | 0,96 € | 24,9 min | **non** | jugée « grande » : parcours complet |
| 9 | 1,12 € | 30,7 min | oui | règle préventive du catalogue : pas de correction, code plus cher |
| 10 | 1,15 € | 28,8 min | oui | suite complète une seule fois : pas de gain |
| Conversation unique | 0,95 € | 12 min | oui | 651 lignes, sans cahier ni revue |

**Conclusion.** Les réglages ont fait passer le coût de 2,82 € à environ **1,1 €** (−60 %) et le temps de 70 à environ 29 min ; le
run 5 (0,53 €) est un cas favorable. Sur cinq runs valides à parcours court (4, 5, 6, 9, 10), la moyenne est de **1,05 €** et la
médiane de 1,12 €, **au niveau de la conversation unique (0,95 €) en coût brut, et en dessous par ligne de code** (run 10 : 1,12 €
le millier de lignes contre 1,46 €), avec un cahier validé, une revue et un suivi en plus. En temps, la conversation reste 2,4 fois
plus rapide (12 contre 29 min). **Descendre nettement sous la conversation demande des changements du moteur, pas de réglage :**
voir la section « Recommandations », leviers structurels.

**Run 10 (f15) :** code 0,83 €, tests 0,12 €, cadrage 0,15 €, livraison 0,04 € ; 1 031 lignes, 572 tests verts. Ne relancer la suite
complète qu'une fois n'a rien changé au temps (livraison 10,4 min) ni au coût. Un défaut est revenu : la livraison note « défauts
connus de correspondance (pâtes / pâte brisée, lait / lait de coco…) non corrigés » : la règle préventive n'a pas tenu cette fois, et la
revue a laissé passer sans correction. **Le contrôle qualité accepte donc un défaut connu sans le bloquer.**

## 1. Les trois premiers runs

| | Run 1 (f6) | Run 2 (f7) | Run 3 (f8) |
|---|---|---|---|
| Durée | 70 min | 36,7 min | 25,5 min |
| Coût (app) | 2,82 € | 2,30 € | 1,92 € |
| Tâches | 16 | 12 | 11 |
| Tokens de sortie | 0,12 M | 0,11 M | 0,11 M |
| Cache lu / écrit | 5,7 M / 0,60 M | 6,6 M / 0,45 M | 6,2 M / 0,36 M |
| Code produit | ~1 100 lignes, 582 tests | ~1 250 lignes, 585 tests | ~1 140 lignes, tests verts |
| Interventions manuelles | 4 messages de déblocage + 3 réponses | 2 réponses + 2 validations | 2 réponses + 2 validations |

Ce qui change d'un run à l'autre :
- **Run 1** : consigne « pas d'émulateur » donnée après le départ ; étape de code sur le cloud (conteneur Linux sans SDK).
  Le code des écrans n'a jamais été écrit, la tâche a été marquée « terminée », puis cinq tâches de tests et de correction ont
  constaté l'absence de code (environ 0,9 € et 35 min pour rien). Une erreur « accès refusé » sur `suivi.json` a bloqué deux tâches.
- **Run 2** : étape de code sur le poste, consigne dans la demande. 4 min perdues, car j'ai raté la question du cadrage.
  Une boucle de correction (t353, 0,25 €) et des maquettes refaites (t346, 0,08 €).
- **Run 3** : mêmes réglages, réponse en 7 s, aucune boucle de correction.

**Variance à réglages égaux (runs 2 et 3) : 16 %**, et elle vient presque entièrement de la boucle de correction après la
revue (présente ou non). C'est la source de variance principale ; l'ordre de grandeur d'un run « propre » est 1,9 à 2,3 €.

## 2. Où va l'argent (run 3, 1,92 €)

| Poste | Coût | Part |
|---|---|---|
| Écriture du code (2 tâches) | 1,17 € | 61 % |
| Maquettes (3 tâches) | 0,22 € | 11 % |
| Tests et revue (2 tâches) | 0,20 € | 10 % |
| Cadrage | 0,16 € | 8 % |
| Mise en place et compilation | 0,12 € | 6 % |
| Livraison APK (Haiku) | 0,05 € | 2 % |

Par nature de token (moyenne des runs 2 et 3) : **sortie ~0,8 $ (35 %), cache écrit ~0,8 $ (33 %), cache lu ~0,46 $ (19 %),
entrée ~0,25 $ (10 %)**. Deux constats :
1. La **sortie** (~0,11 M tokens) est stable à ±5 % d'un run à l'autre : c'est le travail réel (code, tests, cahier, rapports).
2. Le **cache écrit** pèse autant : chaque session d'agent paie le chargement de son contexte (25 000 à 105 000 tokens par
   usage, soit 0,06 à 0,26 $). Plus il y a de sessions, plus ce poste monte (run 1 : 27 usages, 1,26 $ ; run 3 : 12 usages, 0,64 $).

Les lots répartissent leur usage à parts égales entre leurs tâches (`reparti: egal`) : deux tâches d'un même lot affichent le
même coût (par exemple 0,59 € et 0,59 € pour le code). Ce n'est pas une estimation, mais le coût par tâche est à lire par lot.

## 3. Temps (run 3, 25,5 min)

| Phase | Durée | Remarque |
|---|---|---|
| Cadrage + questions | 2 min | une aller-retour avec le Directeur |
| Cahier → découpage | 1,5 min | |
| Maquettes + validation | 3,5 min | |
| Code (2 tâches en parallèle) | 8 min | |
| Compilation + tests | 2 min | |
| **Livraison (APK release signé)** | **9 min** | **35 % du run pour 0,05 € : c'est la construction Gradle release** |

## 4. Référence MESURÉE : la même évolution faite dans une conversation

Une session Claude Code (Sonnet 5,5, même modèle que les agents) a refait la fonctionnalité seule, sans orchestrateur ni
sous-agent, dans une copie propre de la base, avec les mêmes choix et la même consigne « pas d'émulateur ». Coût relevé dans sa
transcription (37 réponses, 32 appels d'outils), aux prix du bureau :

| | Conversation unique | Run 3 (orchestrateur) | Run 2 | Run 1 |
|---|---|---|---|---|
| **Coût** | **0,95 €** | 1,92 € | 2,30 € | 2,82 € |
| Durée | **12 min** (11:00 à 11:12) | 25 min | 37 min | 70 min |
| Tokens de sortie | 35 000 | 110 000 | 110 000 | 120 000 |
| Cache lu / écrit | 4,4 M / 0,10 M | 6,2 M / 0,36 M | 6,6 M / 0,45 M | 5,7 M / 0,60 M |
| Code produit | 651 lignes, 10 fichiers | 1 141 lignes, 15 fichiers | 1 251 lignes, 18 fichiers | ~1 100 lignes, 14 fichiers |
| Tests unitaires | 565 verts (19 nouveaux) | verts, ~585 | 585 verts | 582 verts |
| Documents produits | aucun | cahier, maquettes, revue, notes | idem | idem |

**Le run 3 coûte 2 fois la conversation unique et prend 2 fois plus de temps.** L'écart est plus faible à périmètre égal :
la conversation a écrit **57 % du code** (un seul fichier d'écran, un seul fichier de tests, pas de revue indépendante,
`versionCode` laissé à 15, signature non revérifiée). Par ligne de code : 1,46 €/millier de lignes contre 1,68 (run 3),
1,84 (run 2) et 2,56 (run 1). **L'orchestrateur est donc 15 à 75 % plus cher par ligne, pas 100 %.**

Ce que l'orchestrateur achète en plus, et que la conversation n'a pas : un cahier des charges et des maquettes validés par le
Directeur, une revue indépendante (qui a trouvé des défauts de catalogue et de synonymes à corriger), des tests plus nombreux,
une traçabilité (suivi, leçons). Si ces garanties ne valent pas 1 € sur une évolution de cette taille, elles se retirent
(recommandations 1 à 4). Mon estimation de départ (1,0 à 2,0 €, centre 1,2 €) était juste dans l'ordre de grandeur : la mesure
tombe à 0,95 €, au bas de la fourchette.

Réserves : un seul essai de la conversation (variance inconnue, probablement ±20 %) ; la copie démarre avec le cache Gradle
utilisateur chaud mais sans cache de projet ; le cache écrit est facturé ici au prix du bureau (2,5 $/M) alors que le palier d'une
heure coûte davantage (+0,15 $ environ). La conversation qui a supervisé ces runs n'est pas comptée (voir ci-dessous).

À ne pas oublier : le bureau ne compte pas **la conversation qui le pilote**. La mienne (supervision de ces trois runs, une
centaine de tours à ~200 000 tokens de contexte) a coûté de l'ordre de 2 à 3 € (estimé), autant qu'un run. Ce coût vient de
l'essai (je guettais le bureau à chaque événement), pas du produit ; il disparaît si le Directeur répond lui-même. Quand le
besoin naît d'une discussion ici (ce qui était le cas), cette discussion doit entrer dans le coût de la fonctionnalité.

## 5. Run 4 : contrôle après les leviers 1 à 4

Même demande, mêmes réponses, code remis à la base. Réglages : workflow de base à 3 étapes (code, tests, livraison), consigne de
découpage « un seul élément », consignes de brièveté du projet.

| | Run 4 (f9) | Run 3 | Conversation unique |
|---|---|---|---|
| **Coût** | **1,09 €** | 1,92 € | 0,95 € |
| Durée | **20,5 min** (11:21 à 11:42) | 25,5 min | 12 min |
| Tâches | 4 | 11 | (1 session) |
| Tokens (tous types) | 3,7 M | 6,8 M | 4,5 M |
| Code | 900 lignes, 15 fichiers, 31 recettes | 1 141 lignes | 651 lignes |
| Tests | 21 recettes + 6 ViewModel, 53 avec les contrôles, suite verte | verts | 565 verts |
| Cahier validé, revue indépendante | oui, oui | oui, oui | non |
| €/millier de lignes | **1,21** | 1,68 | 1,46 |

- **Coût : −43 % par rapport au run 3** (1,92 → 1,09 €), et **sous la conversation unique par ligne de code** (1,21 contre 1,46).
  En coût brut, il reste 15 % au-dessus de la conversation (1,09 contre 0,95 €), mais avec 38 % de code en plus, un cahier
  validé et une revue qui a ajouté `RecettesViewModelTest`.
- **Temps : −20 %** (25,5 → 20,5 min), loin des 12 min de la conversation : la **livraison de l'APK prend 8 min** à elle seule
  (construction release et signature), ce que le seul processus ne comprime pas. Hors livraison, le run dure 12,5 min.
- Détail : code 0,73 €, tests et revue 0,21 €, cadrage 0,12 €, livraison 0,03 €. Plus de maquettes, plus de compilation séparée,
  une session de code au lieu de deux, aucune boucle de correction (un seul essai : la variance reste inconnue).
- Les rapports sont plus courts (3 à 4 lignes par tâche).

**Conclusion : l'objectif « sous le coût d'une évolution faite dans une conversation » est atteint par ligne de code, pas encore en
coût brut.** Pour passer sous 0,95 € brut sans perdre le cahier ni la revue, il reste deux pistes : la livraison (construire
l'APK release seulement sur demande de livraison, et pas à chaque évolution : −8 min, −0,03 €) et la revue fusionnée avec le code
quand le code est écrit sur le poste (−0,1 €).

## 6. Run 5 : leviers 1, 2 (réduit) et 7 en plus

Réglages ajoutés au run 4 : la demande donne directement ses choix et le cadrage ne pose aucune question (levier 7) ; le testeur
corrige lui-même les défauts simples (levier 1) ; la livraison ne relance pas les tests déjà verts (levier 2, version réduite).
Le levier 2 complet (livraison en parallèle ou sur demande) et le levier 6 (prompt de départ plus léger) ne sont pas appliqués.

| | **Run 5 (f10)** | Run 4 | Run 3 | Conversation unique |
|---|---|---|---|---|
| **Coût** | **0,53 €** | 1,09 € | 1,92 € | 0,95 € |
| Durée | **14,4 min** (11:46 à 12:01) | 20,5 min | 25,5 min | 12 min |
| Tâches | 4 | 4 | 11 | (1 session) |
| Tokens de sortie | 36 000 (dont 22 000 en livraison) | 78 000 | 110 000 | 35 000 |
| Code | 822 lignes, 14 fichiers | 900 lignes | 1 141 lignes | 651 lignes |
| Cahier validé, revue indépendante | oui, oui | oui, oui | oui, oui | non |
| €/millier de lignes | **0,64** | 1,21 | 1,68 | 1,46 |

Détail du run 5 : code 0,28 €, tests et revue 0,13 €, cadrage 0,08 €, livraison 0,03 €. Par nature : cache écrit 0,29 €,
sortie 0,14 €, cache lu 0,10 €.

**Le run 5 passe sous la conversation unique en coût brut (0,53 contre 0,95 €) et par ligne de code (0,64 contre 1,46 €), en
gardant le cahier validé et la revue.** En temps, il est à 14,4 min contre 12 : dont 1,7 min d'attente de ma part (cahier
validé en retard), soit environ 12,7 min nettes, au niveau de la conversation. La livraison reste à 7,7 min (la moitié du run).

**À lire avec prudence :**
- **Un seul run.** Le coût de l'étape de code varie de 2,5 fois entre les runs 4 et 5 (0,73 € contre 0,28 €) sans que les leviers
  touchent l'écriture du code : la session de run 5 a produit presque autant de code avec 6 000 tokens de sortie contre 39 000.
  Une partie de la baisse est donc de la variance, pas des leviers. Il faut au moins deux runs à réglages égaux pour les séparer.
- **Moins de tests :** la revue du run 5 a relevé l'absence de tests des ViewModels et l'a laissée en « réserve » ; au run 4,
  la revue avait ajouté `RecettesViewModelTest`. Le levier 1 ne s'est donc pas exercé sur ce point, et la qualité a baissé d'un cran.
- **Mesure vérifiée :** les tokens du bureau (sortie, cache lu et écrit) correspondent à ceux des transcriptions des agents à
  1 % près sur les runs 3 à 5. Un calcul de ma part qui donnait un coût double venait d'un oubli (la livraison est facturée
  au tarif Haiku, pas Sonnet).
- **Mon suivi a raté deux attentes** (cadrage du run 2, validation du cahier du run 5) : le temps de réponse de ces deux runs
  est à corriger de 2 à 4 min.

## 7. Run 6 : mêmes réglages que le run 5, pour mesurer la variance

Cahier validé en 12 s par un programme (plus d'attente humaine). Résultat : **1,36 €, 28,7 min, 7 tâches, 1 079 lignes**
(21 fichiers). Le run 5 avait fait 0,53 €, 14,4 min, 4 tâches, avec les mêmes réglages : **un facteur 2,6 entre deux runs identiques.**

| Tâche du run 6 | Coût | Remarque |
|---|---|---|
| Cadrage | 0,09 € | |
| Code | 0,40 € | 0,28 € au run 5 |
| Tests et revue | 0,15 € | la revue note l'oubli de tests de ViewModels |
| Livraison (1re) | 0,06 € | 8,3 min ; la suite complète trouve 1 test en échec et deux défauts de catalogue |
| **Correction** | **0,49 €** | 4,5 min |
| Tests et revue (2e) | 0,15 € | 2,3 min |
| Livraison (2e) | 0,03 € | 6 min |

Le surcoût du run 6 est **la boucle de correction : 0,67 € et environ 14 min** (correction, deuxième revue, deuxième livraison). Elle
vient de la livraison, pas de la revue : le levier 1 (le testeur corrige lui-même) ne s'est pas déclenché, car les défauts sont
apparus après la revue, à l'exécution de la suite complète en livraison. Les défauts sont **toujours les mêmes** : un ingrédient
simple (« pâtes », « lait », « pain », « fromage ») est jugé présent par un produit composé (« pâte brisée », « lait de coco »,
« pain d'épices »). On les retrouve au run 1 (« Spaghetti »), au run 2 (synonymes), au run 4 (revue) et au run 6.

**Variance à réglages égaux, sur les runs 4 à 6 :** 1,09 / 0,53 / 1,36 €, moyenne **0,99 €**, soit la conversation unique (0,95 €)
avec en plus le cahier validé et la revue. Sans boucle de correction, un run vaut 0,5 à 0,7 € ; avec une, 1,1 à 1,4 €. La seule
source de variance notable est donc la boucle de correction, que l'on peut prévenir (levier 9).

## 8. Runs 7, 8 et 9 : la règle préventive, et deux accidents de mesure

- **Run 7 : invalide.** 0,41 € et 14,2 min, mais l'agent de code a **restauré le code du run 6 depuis l'historique git** (en
  annulant ma remise à la base) au lieu de l'écrire. Il ne mesure donc que ce que coûte une restauration (~0,4 €) ; la règle
  préventive n'a pas été exercée. Les runs suivants interdisent la restauration dans la demande. Tag `run7-invalide`.
- **Run 8 : parcours complet, non comparable.** Le cadrage a jugé l'évolution « grande », parce qu'il a pris « un catalogue de
  trente recettes » pour un modèle qui se répète. Parcours : prototype puis méthode, sans tests ni livraison séparés : 0,96 €,
  24,9 min pour 2 tâches. Le moteur est aussi resté muet 8 min après le prototype (aucune décision « valider la méthode » posée)
  jusqu'à un message de relance. Tag `run8-grande-fin`. Correctif : section « Taille » dans les consignes du projet.
- **Run 9 : valide, parcours court (« moyenne »).** Règle préventive du catalogue et section « Taille » en place.

| Run 9 (f14) | Coût | Durée |
|---|---|---|
| Cadrage | 0,11 € | |
| Code | **0,79 €** | 6,7 min |
| Tests et revue | 0,17 € | 7,1 min |
| Livraison | 0,05 € | **14 min** |
| **Total** | **1,12 €** | **30,7 min** |

Résultat : 577 tests unitaires verts, dont 31 de recettes ; **aucune boucle de correction** (la règle préventive a fonctionné :
correspondance par mot entier, tests des cas composés, tests des ViewModels). Mais le coût n'a pas baissé : **le travail déplacé
vers l'amont a coûté à peu près ce que la boucle coûtait** (code à 0,79 € contre 0,28 à 0,40 € aux runs 5 et 6), et la suite
complète tourne trois fois (code, revue, livraison) : la livraison passe à 14 min, la plus longue de tous les runs.

**Bilan sur les runs valides à parcours court avec les mêmes leviers :** run 4 : 1,09 €, run 5 : 0,53 €, run 6 : 1,36 €, run 9 :
1,12 €, soit **une moyenne de 1,03 €** pour la conversation unique à 0,95 €. L'orchestrateur est donc **au niveau de la
conversation en coût brut**, avec en plus un cahier validé, un suivi, et une revue ; il n'est pas en dessous de façon régulière.
Ce qui reste à gagner est dans les doublons : la suite complète exécutée trois fois, la livraison qui reconstruit, et les 6 à 8 min
de construction de l'APK à chaque évolution.

## 9. Recommandations, classées par gain

| # | Levier | Gain estimé | Type |
|---|---|---|---|
| 1 | Supprimer l'étape maquettes pour une évolution « moyenne » sans nouveau parcours (logique + deux écrans sur un design existant), ou la fondre dans le cahier | −0,22 €, −3,5 min, −1 validation | processus |
| 2 | Écrire le code en **une** session (logique + écrans) quand la taille est « moyenne » ; le découpage en 2 tâches rend deux fois le chargement du contexte | −0,2 à −0,4 € | processus |
| 3 | Rapports et journaux d'agent **courts** (limite de longueur sur ce que l'agent écrit dans le suivi, la revue, le cahier) | −0,15 à −0,25 € (sortie ~35 % du coût) | consigne |
| 4 | Moins de sessions : fusionner « mise en place + compilation » avec les tests quand ils sont sur le poste, un seul agent pour revue + tests | −0,15 € (cache écrit) | processus |
| 5 | Lancer la **construction release en parallèle** des tests (elle ne dépend que de la compilation), et garder le cache Gradle chaud | −5 min (20 % du temps) | technique |
| 6 | Préremplir les réponses de cadrage par défaut du genre (« pour le reste je choisis moi-même ») : plus de question au Directeur | −1 à −4 min, −1 interaction | consigne |
| 7 | **Ne jamais marquer « terminée »** une tâche dont le rapport dit « non faite » ou « non compilé » ; ne pas lancer les tâches suivantes tant que le code attendu n'est pas dans master | évite 0,9 € et 35 min (run 1) | correction logicielle |
| 8 | Étape de code **locale par défaut** quand le projet exige un SDK (réglage fait ici) ; les corrections de tests suivent le lieu de l'étape contrôlée, pas le cloud | évite le run 1 entier | correction logicielle |
| 9 | **Prévenir le défaut récurrent du catalogue** : une règle écrite dans la consigne du code (« un ingrédient ne correspond qu'à un mot entier ; jamais à un produit composé : pâte brisée, lait de coco, pain d'épices ») et un test dédié, pour ne plus payer la boucle de correction (0,25 à 0,67 € sur 4 runs sur 6) | −0,3 à −0,6 € en moyenne, variance quasi nulle | processus, mesuré sur 4 runs |

**Leviers structurels (changement du moteur, après la synthèse) :**

| # | Levier | Gain estimé |
|---|---|---|
| S1 | Mode « évolution moyenne » : une seule session pour code, tests et revue (le testeur reste un second regard, mais dans la même session de contexte) | −0,15 à −0,3 €, −5 min |
| S2 | Construire l'APK release seulement sur demande de livraison, ou en parallèle des tests (aujourd'hui 8 à 14 min par évolution) | −8 à −10 min |
| S3 | Verdict « valider en parcours court » à la validation du cahier, avec texte annonçant le chemin | supprime le risque « grande » (+0,5 à 1 €) |
| S4 | Un défaut connu non corrigé bloque la livraison ou ouvre une correction au lieu de passer en note | qualité (le coût remonte de 0,3 à 0,6 € quand il se déclenche) |

Cumul réaliste de 1 à 4 : 1,92 € → **environ 1,2 à 1,4 €**, et 25 min → environ 15 min avec 5 et 6.

**Verdict contre la référence mesurée (0,95 € pour 651 lignes, 12 min) :**
- Au **même périmètre** (la conversation, ramenée à 1 141 lignes au même coût par ligne, serait à environ 1,7 €), le run 3 est
  au-dessus de 15 %, et les leviers 1 à 4 le placent **en dessous** (1,2 à 1,4 €), avec en plus un cahier validé et une revue.
- Au **coût brut** (0,95 €), il faudrait couper la moitié du run 3. Seul un parcours « léger » le permet : une session pour le
  code et les tests, pas de maquettes, pas de revue séparée, cadrage préinscrit. C'est ce que fait la conversation, au prix des
  garanties de la section 4. À proposer comme **mode « évolution moyenne »**, choisi par la taille du cahier, plutôt que comme
  réglage unique.
- Côté **temps**, 12 min contre 25 : la livraison de l'APK (9 min) est le seul poste incompressible par le seul processus ;
  les recommandations 1, 5 et 6 ramènent le run à 12 à 15 min.

Les leviers 1 et 2 sont à vérifier par un run chacun : les retirer sans mesure risque de transférer le coût vers les
corrections (la variance principale).

## 10. Défauts du logiciel trouvés pendant l'essai

1. **`suivi.json` : « accès refusé » (WinError 5)** sous Windows quand un lecteur tient le fichier une fraction de seconde.
   Corrigé dans `orchestrateur/suivi.py` (réessais jusqu'à 2 s, copie au lieu de déplacement pour la version précédente) avec
   deux tests. **Pas encore actif** dans le moteur en marche (redémarrage nécessaire).
2. **Tâche marquée terminée alors que l'agent dit « non faite »** (cloud sans SDK) : voir recommandation 7.
3. **La consigne type d'une correction demande les tests sur émulateur**, contre la consigne de la fonctionnalité.
4. **Une correction de tests part sur un agent cloud sans SDK**, qui rend « non compilé, à lancer sur le poste équipé ».
5. **Une question de cadrage n'apparaît que dans « Réponses attendues » du bureau** : le relevé ne la porte ni en décision ni
   en `attend_reponse` ; rien ne prévient l'autre côté (ici, moi).
6. **Le moteur reste muet après un prototype** (parcours complet) : aucune décision « valider la méthode » n'est posée avant qu'un message le réveille.
7. **La taille jugée au cadrage varie** pour une même demande (« moyenne » 7 fois, « grande » une fois) ; le texte de validation du cahier n'annonce pas le parcours pour « grande », et il n'existe pas de verdict « valider en parcours court ».
8. **Un agent peut restaurer du code depuis l'historique git** : cela fausse toute mesure sur le même dépôt.
9. **État du dépôt MyIAFactory, hors de cet essai** : `orchestrateur/depart.py` (modifié, non commité) n'a plus
   `contexte_de_tache`, que `orchestrateur/outil.py` appelle encore. Deux tests de `tests/test_orch_suivi.py` échouent à cause de
   cela, indépendamment du correctif ci-dessus.

## 11. Ce qui a été modifié pendant l'essai

- MyFridgeCleaner : étape « Développement de l'application : code » passée de **cloud à local** (réglage persistant) ; trois
  commits locaux de remise à la base ; tags `run1-fin`, `run2-fin`, `run3-fin` ; rien poussé.
- MyIAFactory : `orchestrateur/suivi.py`, `tests/test_orch_suivi.py` et `moteur/consignes/decouper.md` (non commités).
- MyFridgeCleaner (leviers 1 à 4) : workflow de base `w-application-mobile-android` réduit à `dev`, `tests`, `livraison` (maquettes, validation
  des maquettes et `dev-local` retirés ; sauvegarde `.factory/factory.json.avant-leviers`) ; outils d'environnement rattachés à `dev` ;
  `.factory/consignes-projet.md` (brièveté). Retour arrière : restaurer la sauvegarde. Ces réglages valent pour toutes les évolutions
  de ce projet, y compris celles qui créent un nouveau parcours : le cahier garde alors ses maquettes, mais le Directeur ne valide
  plus de maquettes à part.
- Tags `run4-fin` ajouté ; code du projet remis à la base avant chaque run (4 commits locaux). Le run 4 est le seul laissé dans l'état livré.
