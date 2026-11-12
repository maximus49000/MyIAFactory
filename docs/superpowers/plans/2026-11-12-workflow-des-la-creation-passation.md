# Le workflow défini dès la création — passation entre conversations

Le plan (`2026-11-12-workflow-des-la-creation.md`) est réalisé en phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. **Une phase est un lot de modèle** : un même modèle fait d'une traite tout ce qu'il peut faire d'affilée. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les tâches de sa phase sans s'arrêter, puis s'arrête et annonce la suivante. Même méthode que `2026-11-12-genre-par-fonctionnalite-passation.md`.

La conception (`docs/superpowers/specs/2026-11-12-workflow-des-la-creation-design.md`, section 5 bis comprise) est **validée par l'utilisateur** le 2026-11-12 : rien à recadrer. Toutes les phases se font **dans ce dépôt**. Les données d'un essai réel restent **hors dépôt** ; leurs chemins sont donnés par l'utilisateur dans la conversation de la phase. Les sessions de phase n'utilisent pas le panneau navigateur de l'app : elles vérifient par les tests et par des requêtes HTTP. Une autre session peut travailler dans le même dossier : **ne committer que ses propres fichiers**, jamais de stash, reset ni changement de branche.

**Dépenses** : les phases marquées **dépense** appellent un vrai modèle (`claude -p` ou l'API). Elles **attendent l'accord explicite de l'utilisateur** avant le premier appel réel, disent ce qu'elles vont lancer et combien cela coûtera à peu près, et notent le coût réel ici. Aucune phase n'installe de logiciel sur le poste sans accord explicite (l'accord sur une dépense d'API ne le couvre pas).

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Tâches du plan | Dépense réelle | Pourquoi ce modèle | État |
|---|---|---|---|---|---|
| A | Sonnet 5.5 | 1, 2, 3 : étape de validation du Directeur (données, moteur, page) | non | Données, table de règles et page au contrat écrit, tests nommés | **faite** (2026-11-12) |
| B | Opus 5.5 | 4 : jugement `definir_workflow`, validations dans `proposer_organisation`, consignes | **oui** : 4 appels réels, 0,111 $ (≈ 0,096 €) | Les consignes décident de la qualité des questions, du workflow et du coût | **faite** (2026-11-12) |
| C | Sonnet 5.5 | 5, 6 : reprise du workflow de création, poste (versions, installation portée par le projet) | non | Règles du moteur au contrat écrit | à faire |
| D | Sonnet 5.5 | 7, 8, 9 : brouillon, déroulé de l'échange, création avec l'organisation | non (faux `appeler` seulement) | Installation au contrat écrit, tests nommés | à faire |
| E | Sonnet 5.5 | 10, 11 : routes du bureau, page en deux fenêtres | non | Routes et page au contrat écrit | à faire |
| F | Opus 5.5 | 12 : banc gratuit, essai réel au bureau, avec l'utilisateur | **oui** (échange réel au bureau ; production seulement si l'utilisateur l'accepte) | Diagnostic du coût, réglage des consignes, jugement de ce qui accroche | à faire |

Les modèles sont une proposition ; l'utilisateur a le dernier mot. **Fable n'est utilisé dans aucune phase.** Ordre imposé : A avant B (le validateur s'appuie sur `workflows.est_validation`) ; B et C avant D (D appelle `definir_workflow` et `environnement.agent_d_installation`) ; D avant E ; F en dernier. C peut se faire avant B si l'utilisateur le préfère.

## Ce que chaque phase doit vérifier avant de finir

- **A** : un projet existant, sans étape de validation, a le même relevé, le même tableau et la même série qu'avant (`py -3.12 outils/tests.py orch moteur banc`) ; un élément s'arrête bien à une validation, repart sur « Valider », refait l'étape précédente sur « Renvoyer » ; « Renvoyer » sans texte est refusé au bureau comme au moteur ; la réponse marche après un redémarrage du moteur ; un workflow de genre n'a pas de colonnes au tableau.
- **B** : les cinq anciens jugements et `classer_genre` n'ont pas bougé ; un 5ᵉ appel ou une correction qui rendrait des questions est refusé ; le nom du projet est refusé dans un genre nouveau. **Dépense** : essai réel d'un échange complet (jeu Android avec une validation avant la livraison) : validité au premier essai, questions non redondantes, tokens et coût par appel, **total < 0,10 €** ; au plus 3 tours de réglage, notés.
- **C** : une demande `meme` dans un projet qui a un workflow de création ne fait **aucun** appel `proposer_organisation` ni décision `organisation`, et démarre le cadrage dans des colonnes `f<n>-…` ; une demande `proche`/`autre` suit le parcours actuel ; un projet sans workflow de création est inchangé ; un Java 8 n'est plus « déjà en place » quand le workflow demande un JDK 17 ; l'installation de projet ne retient jamais le cadrage.
- **D** : rien sur le disque ni au bureau avant la validation finale ; un nom devenu invalide renvoie aux informations sans perdre l'échange ; le brouillon ne contient aucune clé ; un tour raté ne compte pas mais son coût, si ; les usages de l'échange sont versés au relevé du projet créé, ceux d'un brouillon abandonné ou purgé (30 jours) dans `~/MyIAFactory/usage-creations.jsonl` ; GitHub après, sans rien défaire.
- **E** : routes protégées comme `POST /api/projets/creer` (en-têtes, code d'accès distant) ; un seul tour à la fois par brouillon ; la création depuis une décision `genre_fonctionnalite` garde l'ancien formulaire ; la page est vérifiée par `node --test` (pas de navigateur).
- **F** : le banc gratuit ne bouge pas. **Dépense** : essai au bureau (voir le plan, tâche 12) : coût de l'échange relevé (< 0,10 €), projet créé avec son workflow, ses agents et ses services, première demande du genre sans proposition ni validation de workflow. Ne rien installer sur le poste sans accord ; aller jusqu'à la validation du Directeur seulement si l'utilisateur accepte la dépense de production.

## Notes laissées par les phases

(Écarts au plan, choix faits, points à surveiller.)

**Points de la conception interprétés par le plan (2026-11-12)** — à confirmer ou corriger par l'utilisateur ; une phase qui s'en écarte le note ici :

- **Où se font les appels de l'échange** : par le **bureau** (route `POST /api/creations/tour`, appel synchrone dans le fil de la requête), pas par la boucle du moteur, puisque le projet n'existe pas encore. La couche vient d'une clé facultative `moteur` du **fichier du bureau commun** (`bureau.json`, `claude` par défaut) ; les prix, de `estimation.prix_de_modele(<bureau commun>)`.
- **« Relevé du bureau commun »** : il n'en existe pas aujourd'hui. Le plan crée `~/MyIAFactory/usage-creations.jsonl` (usages des échanges abandonnés ou purgés), dont le total est montré dans la liste des brouillons.
- **Étape de validation** : interdite aussi en **dernière** position (la dernière étape remet le livrable, règle des jugements actuels). Un élément qui attend une validation **occupe une des deux places d'éléments en cours** : deux éléments en attente arrêtent la série (« le travail s'arrête »). Il apparaît aussi comme une tâche dans la colonne de l'étape.
- **Workflow de création** : il n'a **pas de colonnes** au tableau (seules ses copies `w-<fid>` en ont), pour ne pas doubler les colonnes à chaque demande. Une fonctionnalité ne pointe jamais sur `w-<genre>` : les reprises de secours (`_classer_rate`, refus sans texte) le copient aussi.
- **Tâche d'installation portée par le projet** : colonne `cadrage`, sans fonctionnalité ; son échec pose une décision de **projet** `environnement` ; elle **ne retient pas** le cadrage des demandes (le cadrage n'a pas besoin des outils), pour ne jamais bloquer.
- **« Versions comparées »** : un champ facultatif `version_min` par outil, rendu par les jugements et comparé en code (corrige le défaut « Java 8 vu comme JDK 17 » de la phase E précédente) ; vaut aussi pour `proposer_organisation`.
- **Forme des messages du chef** (laissée au constructeur) : 1 à 5 questions par tour, 0 à 6 choix par question ; chaque étape proposée porte une `raison`.
- **Création depuis une décision** « cette demande n'est pas du genre du projet » → « Nouveau projet » : inchangée (formulaire actuel, projet vide, la demande déplacée y propose son workflow). Seul « Nouveau projet… » de la liste passe par les deux fenêtres.
- **Un brouillon par projet en cours de définition** : identifiant `c` + 12 chiffres hexadécimaux, un fichier JSON par brouillon dans `~/MyIAFactory/creations/`.

**Notes de la phase A (2026-11-12, Sonnet 5.5)** — tâches 1, 2, 3 faites ; suite complète verte (une PermissionError Windows de nettoyage dans `test_releve.TestObtenir`, relancée seule : verte), banc rejoué gratuit vert, `node --test` vert (249).

- **Écarts au plan** : (1) `estimation.estimer` ignore une validation par `e.get("validation")` (pas par `workflows`, pour ne pas lier `installation` à `orchestrateur.workflows`) ; (2) `orchestrateur/verifier_interface.py` écrivait le flux avec `x["role"]` : passé par `workflows.etape_ecrite` (sinon la vérification d'un projet qui a une validation plante) ; (3) la décision de projet `valider_etape` est contrôlée par `outil._validation_decidee` (étape connue, tâche connue, `compte_rendu` ≤ 2000 caractères, `fichiers` = `[{chemin, titre}]`) et par `releve._verifier_validation` ; la colonne du relevé porte `validation: true` (booléen vérifié) ; (4) `valider_etape` est aussi un type de demande de `outil.TYPES_DEMANDE` et de `bureau/demandes.py` (`decision`, `verdict`, `texte?`).
- **Reconstruction après redémarrage** : `regles._element_en_validation` rebâtit l'élément depuis la décision (rang de `etape` dans la production, compte rendu et fichiers de la décision). Elle est appelée par la réponse **et** par `_avancer_serie` (sinon un moteur relancé compterait un élément de moins en cours et pourrait déclarer la série terminée).
- **Le flux et les rangs** : `_production` garde les validations (elles ont un rang) ; `_etape_de_relecture` les saute ; les dossiers des jugements `decouper` et `ecrire_methode` n'ont que les étapes d'agent (`workflows.etapes_d_agent`). `_proposer` (workflows antérieurs) et `_apres_proposer_organisation` (préfixe `<fid>-`) gardent une validation telle quelle, mais **le jugement `proposer_organisation` ne sait pas encore en produire** (phase B).
- **À savoir pour la phase B** : une étape de validation d'un jugement s'écrit `{"etape", "nom", "validation": true, "raison"?}` (le moteur lit `x["etape"]`, `x["nom"]`, `wf.est_validation(x)`) ; `proposition.verifier_organisation` accepte déjà `validation: true` (sans `role` ni `service`, ni première, ni dernière, ni deux de suite) : le validateur de jugement `_valider_proposer_organisation` doit aussi l'accepter et refuser ces trois positions avec un message lisible. `factory.lire` refuse les mêmes positions.
- **À savoir pour la phase C** : `workflows.de_creation`, `workflows.copie_pour` et le workflow de genre sans colonnes sont faits et testés ; `colonnes` n'a pas de colonnes pour un workflow de genre (`fonctionnalite` nulle, id ≠ `principal`) ; `ids_etapes` les compte toujours (les identifiants d'étape restent uniques dans le projet).
- **Page** : la décision `valider_etape` est dans la partie « Éléments à valider » de `decisions.js` (images par `/api/image?chemin=`, autres fichiers en titre et chemin ; `corpsValiderEtape` pure, `null` si « renvoyer » sans texte) ; le Kanban plein écran et la scène nomment la colonne « Validation du Directeur » ; l'organisation montre « (validation du Directeur) ». Non vérifié dans un navigateur (consigne : pas de panneau navigateur).

**Notes de la phase B (2026-11-12, Opus 5.5)** — tâche 4 faite ; `jugement consignes` verts, `moteur banc environnement` verts, suite complète verte (1307 tests, banc rejoué gratuit compris).

- **Validateurs** (`moteur/jugement.py`) : `definir_workflow` rend `{"type": "questions", "message", "questions": [{id, texte, choix}]}` ou `{"type": "proposition", "message", "genre" | "nouveau", "flux", "services", "agents", "briefs", "livrable", "environnement", "outils_installation"}`. Questions refusées (message qui demande une proposition) si `correction` est donnée, si `proposer_maintenant` est vrai, ou si `tours_de_questions` ≥ `min(tours_max, 4)`. Une question : `id` sur une ligne, 40 caractères au plus ; `choix` de 0 à 6 textes d'une ligne, **80 caractères** au plus (`LONGUEUR_CHOIX`, choix du constructeur). La proposition est validée par `_valider_proposer_organisation` avec `{"services": dossier.services, "agents": [], "fonctionnalite": "f999"}` (`FONCTIONNALITE_TYPE`) : une `etape` tient en **35 caractères**.
- **Écarts au plan** : (1) le nom du projet (`dossier.projet.nom`) est ajouté aux mots interdits par le validateur lui-même, même si le bureau l'oublie dans `mots_interdits` (attention : `mots_trouves` compare par sous-chaîne, un nom très court comme « Art » refuserait « cartes ») ; (2) dans les deux jugements, une étape de validation qui porte `role` ou `service`, ou un `validation` autre que `true`, est refusée ; `raison` est permise (une ligne) dans `proposer_organisation`, obligatoire dans `definir_workflow` ; (3) `environnement[i].pour` ne peut désigner qu'une étape d'agent ; (4) `version_min` : chiffres et points, 20 caractères au plus, ou null ; la comparaison reste `environnement.version_minimale` (commit cd4500e), rien de refait ; (5) `proposer_organisation.md` : une validation seulement si la demande ou le refus la demande ; la phrase « version minimale dans le nom » est remplacée par `version_min` (le nom marche toujours côté code).
- **Essai réel** (couche `claude`, accord de l'utilisateur ; projet synthétique « casse-briques Android », description qui dit déjà vouloir l'essayer avant la livraison ; genres synthétiques `badges-stream`, `site-vitrine`, `jeu-android` ; script hors dépôt, supprimé) — prix : `total_cost_usd` de `claude -p`, converti à 0,86 € le dollar :

| Appel | Résultat | Entrée / cache lu / cache écrit / sortie (tokens) | Coût |
|---|---|---|---|
| Avant réglage, tour 1 | proposition **directe, sans aucune question** (valide au 1er essai) | 2 / 0 / 2 710 / 1 796 | 0,0288 $ ≈ 0,025 € |
| Réglage 1, tour 1 | 5 questions à choix (style et commandes, nombre de niveaux, sons, façon d'essayer, exigence de tests), valides | 2 / 0 / 2 748 / 606 | 0,0171 $ ≈ 0,015 € |
| Réglage 1, tour 2 | proposition valide : dev → niveaux et bruitages → tests automatiques et build → **validation « Essai de l'apk »** → « Livraison de l'apk signé » ; `jeu-android` ; JDK `version_min` « 17 » | 2 / 1 507 / 2 029 / 2 381 | 0,0321 $ ≈ 0,028 € |
| Réglage 1, correction | « valider le style néon après le développement » : validation ajoutée au bon endroit, le reste inchangé | 2 / 1 507 / 4 128 / 1 671 | 0,0334 $ ≈ 0,029 € |

  - **Échange complet : 0,049 $ ≈ 0,042 €** (questions + proposition), **0,083 $ ≈ 0,071 €** avec une correction : cible < 0,10 € tenue. Toutes les réponses valides au premier essai. Dépense totale de la phase : 0,111 $ ≈ 0,096 €.
  - **Un tour de réglage** (sur 3 permis) : la consigne disait « arrête dès que tu en sais assez » et le chef proposait sans rien demander ; elle dit maintenant de poser ses questions au premier tour sauf si la description dit déjà tout (besoin, livrables, validations, exigence de qualité). Aucune question ne reposait ce que la description disait (la validation avant livraison a été reprise d'office, la question 4 demandait seulement comment essayer).
  - Le coût vient surtout de l'écriture du cache (consigne + dossier, 2 000 à 4 100 tokens, ≈ 0,01 $ par appel) et de la sortie de la proposition (1 700 à 2 400 tokens). Une correction renvoie la proposition précédente dans le dossier : plus chère que le premier tour.
- **À savoir pour la phase C** : les deux jugements rendent désormais `environnement[i].version_min` (validé : chiffres et points, ou null) ; la comparaison des versions existe déjà (`environnement.version_minimale` lit `version_min` puis le nombre du nom, `verifier` compare) : la tâche 6 n'a qu'à vérifier que `version_min` arrive jusqu'à `verifier` (organisation de fonctionnalité et de création), sans refaire la comparaison.
- **À savoir pour la phase D** : le dossier attendu est celui du plan ; le déroulé incrémente `tours_de_questions` à chaque réponse `questions` validée, met `correction` et `proposition_precedente` pour une correction (puis les remet à null), et peut mettre `proposer_maintenant` (bouton « proposez maintenant »). Le message de refus d'une question au 5ᵉ appel dit « rends une proposition » : la seconde tentative de `juger` suffit en pratique. L'`id` d'une étape de validation est libre (`essai`, `validation-style`).
- **Non vérifié** : une description déjà complète (le chef propose-t-il directement ?), un genre nouveau proposé en vrai (le dossier offrait `jeu-android`), les 4 tours épuisés en vrai.

## Messages à coller

**Phase A — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase A du chantier « le workflow défini dès la création ». Lis `docs/superpowers/plans/2026-11-12-workflow-des-la-creation-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne d'une traite les tâches 1, 2 et 3 du plan. N'utilise pas le panneau navigateur de l'app. Une autre session peut travailler dans le même dossier : ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase B — Opus 5.5 — dans ce dépôt (dépense : accord demandé)**

> Réalise la phase B du chantier « le workflow défini dès la création ». Lis `docs/superpowers/plans/2026-11-12-workflow-des-la-creation-passation.md` et suis-le. Fais la tâche 4 du plan ; demande mon accord avant l'essai réel de l'échange. N'utilise pas le panneau navigateur de l'app. Ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase C — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase C du chantier « le workflow défini dès la création ». Lis `docs/superpowers/plans/2026-11-12-workflow-des-la-creation-passation.md` et suis-le. Enchaîne d'une traite les tâches 5 et 6 du plan. N'utilise pas le panneau navigateur de l'app. Ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase D — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase D du chantier « le workflow défini dès la création ». Lis `docs/superpowers/plans/2026-11-12-workflow-des-la-creation-passation.md` et suis-le. Enchaîne d'une traite les tâches 7, 8 et 9 du plan, sans aucun appel réel à un modèle. N'utilise pas le panneau navigateur de l'app. Ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase E — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase E du chantier « le workflow défini dès la création ». Lis `docs/superpowers/plans/2026-11-12-workflow-des-la-creation-passation.md` et suis-le. Enchaîne d'une traite les tâches 10 et 11 du plan, sans aucun appel réel à un modèle. N'utilise pas le panneau navigateur de l'app. Ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase F — Opus 5.5 — dans ce dépôt (dépense : accord demandé)**

> Réalise la phase F du chantier « le workflow défini dès la création » : la tâche 12 du plan, avec moi. Lis `docs/superpowers/plans/2026-11-12-workflow-des-la-creation-passation.md`. Je te donnerai le dossier parent de l'essai (hors dépôt). Demande mon accord avant toute dépense réelle, et n'installe rien sur le poste sans mon accord. Ne committe que tes fichiers.

## Fin de phase

1. Toute la suite verte : `py -3.12 outils/tests.py` (environ 75 s). **Seulement ici** : pendant le travail, chaque commit ne lance que les tests concernés, `py -3.12 outils/tests.py <mots>`.
2. Cocher les tâches faites dans le plan, mettre à jour « Où on en est » et les notes.
3. Commit (ses seuls fichiers) et push.
4. Annoncer la phase suivante, son modèle, si elle dépense, et son message à coller.
