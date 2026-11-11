# Un genre et un workflow par fonctionnalité — passation entre conversations

Le plan (`2026-11-12-genre-par-fonctionnalite.md`) est réalisé en phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. **Une phase est un lot de modèle** : un même modèle fait d'une traite tout ce qu'il peut faire d'affilée. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les tâches de sa phase sans s'arrêter, puis s'arrête et annonce la suivante. Même méthode que `2026-11-11-orchestrateur-procedural-passation.md`.

La conception (`docs/superpowers/specs/2026-11-11-genre-par-fonctionnalite-design.md`) est **validée par l'utilisateur** le 2026-11-12 : rien à recadrer. Toutes les phases se font **dans ce dépôt**. Les données d'un essai réel restent **hors dépôt** ; leurs chemins sont donnés par l'utilisateur dans la conversation de la phase. Les sessions de phase n'utilisent pas le panneau navigateur de l'app : elles vérifient par les tests et par des requêtes HTTP. Une autre session peut travailler dans le même dossier : **ne committer que ses propres fichiers**. Aucune dépense réelle (appel `claude`, `gh`) sans l'accord de l'utilisateur.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Tâches du plan | Pourquoi ce modèle | État |
|---|---|---|---|---|
| A | Sonnet 5.5 | 1, 2 : workflows du projet, genre de la fonctionnalité ; relevé, tableau, départ et mémoire | Données et lecture au contrat écrit, tests nommés | **faite** le 2026-11-12 (1121 tests verts) |
| B | Opus 5.5 | 3 : jugements `classer_genre` et `proposer_organisation` | Les consignes décident de la qualité (genres précis, workflow complet jusqu'au livrable) et du coût | **faite** le 2026-11-12 (1138 tests verts) |
| C | Sonnet 5.5 | 4, 5, 6, 10 : le moteur suit le workflow de la fonctionnalité, Fable sur accord, parcours d'une nouvelle demande, environnement du poste | Table de règles au contrat écrit, un test par ligne | à faire : **c'est la prochaine phase** |
| D | Sonnet 5.5 | 7, 8 : créer un projet vide, le bureau | Installation et page au contrat écrit | à faire |
| E | Opus 5.5 | 9 : banc et essai réel, avec l'utilisateur | Diagnostic du coût et réglage des consignes | à faire |

Les modèles sont une proposition ; l'utilisateur a le dernier mot. **Fable n'est utilisé dans aucune phase.**

## Notes laissées par les phases

(Écarts au plan, choix faits, points à surveiller.)

**Phase A (Sonnet 5.5, 2026-11-12)** : tâches 1 et 2 faites, suite complète verte (1121 tests, `node --test` compris).

- **Le champ `genre` d'un usage est pris** : il ne vaut que `partenaire` (validation du relevé, historique des usages).
  Le genre de la fonctionnalité est donc noté dans `genre_fonctionnalite` (suivi, relevé, `usage-historique.jsonl`,
  `bureau/usage.py`). `estimation.usages_du_genre` lit ce champ ; un usage sans lui compte pour le genre du projet, et
  un projet est retenu s'il a ce genre ou un workflow de ce genre. Lignes de lot comprises.
- **Colonnes du relevé** : `genre` n'y est mis que s'il existe, `workflow` seulement si le projet a une clé `workflows`
  (un projet sans `workflows` garde un relevé identique à avant, sauf le `genre` du projet). Une tâche dont la colonne
  a quitté le tableau (fonctionnalité `terminee` ou `deplacee`) est rendue en colonne `fait`, pour que le relevé reste
  valide. La fonctionnalité du relevé gagne `genre`, `workflow`, `deplacee_vers` (s'ils existent) et `workflow_etapes`
  (`[{id, nom}]`, pour nommer ses documents par étape quand ses colonnes ont quitté le tableau).
- **`workflows.tous`** : le principal vient en premier (s'il a un flux), puis les workflows de `workflows`.
  Ajout : `workflows.premiere_etape(f, fonc)` (colonne par défaut d'une tâche ; `cadrage` si le projet n'a aucun workflow,
  `Ctx.premiere_colonne`). `workflows.colonnes` donne `genre: None` quand il n'y en a pas ; le relevé retire la clé.
- **`factory.lire`** rend aussi `workflows` (normalisés) et `description`. Un flux vide ou absent est valide. Le test
  `test_factory_flux_vide` est devenu `test_factory_flux_vide_ou_absent_valide`.
- **Départ** : le genre de la fonctionnalité est passé à `depart.message*` en remplaçant `genre` dans la copie de la
  factory (pas de changement de signature). Un lot qui mêle des genres donne les leçons de chacun, sans doublon, et
  l'en-tête les liste. Leçon de genre appliquée : genre de la fonctionnalité de sa tâche (`tache` de la leçon), sinon
  celui du projet.
- **`deplacee`** : exclue des KPI calculés et de `cout.couts_fonctionnalite` (coût nul), et ses décisions ne comptent
  plus pour le Directeur (`bureau/etat.py`). Documentée dans `interface.md` et d'une ligne dans `consignes.md`
  (le test des consignes exige que chaque étape y soit nommée).
- **Page** : `etiquetteColonne`, `genreEtWorkflow`, `libelleEtape` (pures, testées) ; genre sous le nom de colonne
  (Kanban plein écran et tableau 3D), genre et workflow sous le titre d'une fonctionnalité, étape « Partie dans le
  projet … ». Non regardé dans un navigateur (consigne de la phase).
- **À surveiller** : `main.js` recharge la page quand les identifiants de colonnes changent (`structure`) : chaque
  nouveau workflow de fonctionnalité va donc la recharger une fois, comme un changement de flux aujourd'hui. Ni
  `organisation.js` (qui regarde les colonnes retirées du flux) ni la décision `organisation` n'ont été adaptés
  (phases C et D). `ecrire_organisation`, `moteur/regles.py` lisent encore `ctx.f["flux"]` seul (phase C).

**Phase B (Opus 5.5, 2026-11-12)** : tâche 3 faite, suite complète verte (1138 tests).

- **La validation lit le dossier** : `jugement.valider(type_, objet, dossier=None)` ; `juger` passe son dossier.
  `classer_genre` et `proposer_organisation` sont dans `_VALIDEURS_AVEC_DOSSIER` (les cinq anciens n'ont pas changé).
  Le moteur (phase C) doit donc remplir le dossier exactement comme le docstring de `moteur/jugement.py` le dit, sinon
  la réponse est refusée : `genres_du_projet` et `genres_connus` (`[{id, …}]` ou `[id]`), `mots_interdits`,
  `services` (`[{id, nom}]`), `agents` (`[{cle, role, …}]`), `fonctionnalite` (son id).
- **`classer_genre`** : `meme` exige un genre de `genres_du_projet` ; `proche` un genre connu (projet ou skill) ;
  `autre` un genre connu **ou** `nouveau`, pas les deux ; `incertain` accepte une piste (`genre` ou `nouveau`) ou rien ;
  `nouveau` refusé avec `meme`/`proche`, si son id existe déjà, ou si son id ou sa description contient un mot interdit.
- **`proposer_organisation`** : `flux[i].etape` est l'id **court** (`dev`) ; le moteur le préfixe (`f5-dev`), et la
  validation vérifie que `<fonctionnalite>-<etape>` tient dans `MOTIF_ID` (40 caractères). `services` et `agents` ne
  listent que les nouveaux (un service ou une clé déjà au projet est refusé). Chaque rôle du flux a un agent du projet
  ou proposé ; chaque nouveau rôle a un brief. Pas de champ `lieu` (le moteur le fixe, comme `estimer` le coût).
  Modèle : Haiku, Sonnet ou Opus ; « Fable » en modèle est refusé avec un message qui renvoie à `fable_suggere`.
  **Dernière étape = livrable** : `livrable` non vide, et le nom de la dernière étape contient un mot de livraison
  (`MOTS_DE_LIVRAISON` : livr, remis/remise, publi, dépôt, export, envoi, déploi, mise en ligne) ou un mot (3 lettres
  et plus) du `livrable` : heuristique volontairement souple, à revoir au banc si elle laisse passer un « Développement
  du jeu ». `environnement[i].pour` : l'`etape` ou son nom ; `executables` : noms seuls (`MOTIF_EXECUTABLE`, ni
  chemin ni option) ; `outils_installation` : seulement `Bash(<cmd>:*)`, `Bash(<cmd> <args>)` ou `PowerShell(…)` de
  même forme (`MOTIF_REGLE_OUTIL`) ; `Bash`, `Bash(*)` et les autres outils refusés. Listes vides permises.
- **Écart au plan** : le test existant `test_aucune_consigne_ne_parle_de_fable_ni_d_un_projet` tolère aussi
  `fable_suggere` (le plan l'impose dans la consigne de `proposer_organisation`). Pas de script d'essai dans le dépôt :
  l'essai a tourné par un script hors dépôt (`juger` avec un `appeler` qui note `cout_usd`), sur le modèle de
  `outils/mesurer_appel.py`.
- **Essai réel** (couche `claude`, accord de l'utilisateur ; projet synthétique « badges d'une chaîne », genres
  synthétiques `badges-twitch` et `site-vitrine`) : 9 appels, **0,16 $ en tout**.
  - `classer_genre` (Haiku) : 4 appels, **4 valides au premier essai**, verdicts attendus (badge du chat YouTube →
    `proche` de `badges-twitch` ; casse-briques Android → `autre` avec `nouveau` (`jeu-mobile` puis
    `application-mobile` : l'id varie d'un essai à l'autre) ; demande floue → `incertain` avec la piste du genre du
    projet). Environ 2 100 à 2 500 tokens d'entrée (presque tout en cache), 260 à 385 de sortie, **0,0003 à 0,0006 $**
    par appel, 6 à 9 s.
  - `proposer_organisation` (Sonnet) : 5 appels pour 4 jugements. Badge YouTube et demande floue : **le workflow du
    genre repris tel quel** (mêmes étapes, aucun agent ni service nouveau), valides au premier essai, 1 000 à 1 200
    tokens de sortie, **0,016 à 0,022 $**. Casse-briques : au premier passage, premier essai refusé (`role` écrit en
    texte libre, « développement Android ») puis valide au second ; consigne réglée (ids en minuscules et tirets, un
    outil une seule fois), second passage **valide au premier essai** : 6 étapes (visuels, programmation,
    construction et signature de l'apk, tests, conformité, « Livraison de l'apk signé »), un service et deux agents
    nouveaux (Sonnet, Haiku), JDK, Gradle et SDK Android dans l'environnement. 2 400 à 2 600 tokens d'entrée, 3 100 à
    3 550 de sortie, **0,036 à 0,043 $** par appel, 26 à 29 s.
- **À savoir pour la phase C** : la qualité est parfois tenue par un agent du projet (`verification`) plutôt qu'un
  service qualité nouveau : la consigne le permet (réutiliser). Les `outils_installation` proposés comprennent des
  téléchargements (`Bash(curl:*)`, `PowerShell(Invoke-WebRequest:*)`, `Bash(unzip:*)`) : le Directeur les valide avec
  l'organisation ; ne pas les élargir en code. Un même exécutable peut revenir dans deux outils (vu au premier
  passage, avant le réglage) : dédoublonner par exécutable pour la vérification du poste. `nouveau.id` varie : la
  décision `genre_fonctionnalite` doit le laisser corriger. Les jugements ne choisissent jamais Fable (`juger` le
  refuse toujours ; aucun agent proposé n'a eu `fable_suggere: true` à l'essai).

## Messages à coller

**Phase A — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase A du chantier « un genre et un workflow par fonctionnalité ». Lis `docs/superpowers/plans/2026-11-12-genre-par-fonctionnalite-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne d'une traite les tâches 1 et 2 du plan. N'utilise pas le panneau navigateur de l'app. Une autre session peut travailler dans le même dossier : ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase B — Opus 5.5 — dans ce dépôt**

> Réalise la phase B du chantier « un genre et un workflow par fonctionnalité ». Lis `docs/superpowers/plans/2026-11-12-genre-par-fonctionnalite-passation.md` et suis-le. Fais la tâche 3 du plan ; demande mon accord avant l'essai réel des jugements. N'utilise pas le panneau navigateur de l'app. Ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase C — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase C du chantier « un genre et un workflow par fonctionnalité ». Lis `docs/superpowers/plans/2026-11-12-genre-par-fonctionnalite-passation.md` et suis-le. Enchaîne d'une traite les tâches 4, 5, 6 puis 10 du plan. N'utilise pas le panneau navigateur de l'app. Ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase D — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase D du chantier « un genre et un workflow par fonctionnalité ». Lis `docs/superpowers/plans/2026-11-12-genre-par-fonctionnalite-passation.md` et suis-le. Enchaîne d'une traite les tâches 7 et 8 du plan. N'utilise pas le panneau navigateur de l'app. Ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase E — Opus 5.5 — dans ce dépôt**

> Réalise la phase E du chantier « un genre et un workflow par fonctionnalité » : la tâche 9 du plan, avec moi. Lis `docs/superpowers/plans/2026-11-12-genre-par-fonctionnalite-passation.md`. Je te donnerai les chemins de l'essai de référence (hors dépôt). Demande mon accord avant toute dépense réelle. Ne committe que tes fichiers.

## Fin de phase

1. Toute la suite verte : `py -3.12 outils/tests.py` (environ 75 s). **Seulement ici** : pendant le travail, chaque commit ne lance que les tests concernés, `py -3.12 outils/tests.py <mots>`.
2. Cocher les tâches faites dans le plan, mettre à jour « Où on en est » et les notes.
3. Commit (ses seuls fichiers) et push.
4. Annoncer la phase suivante, son modèle et son message à coller.
