# Un genre et un workflow par fonctionnalité — passation entre conversations

Le plan (`2026-11-12-genre-par-fonctionnalite.md`) est réalisé en phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. **Une phase est un lot de modèle** : un même modèle fait d'une traite tout ce qu'il peut faire d'affilée. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les tâches de sa phase sans s'arrêter, puis s'arrête et annonce la suivante. Même méthode que `2026-11-11-orchestrateur-procedural-passation.md`.

La conception (`docs/superpowers/specs/2026-11-11-genre-par-fonctionnalite-design.md`) est **validée par l'utilisateur** le 2026-11-12 : rien à recadrer. Toutes les phases se font **dans ce dépôt**. Les données d'un essai réel restent **hors dépôt** ; leurs chemins sont donnés par l'utilisateur dans la conversation de la phase. Les sessions de phase n'utilisent pas le panneau navigateur de l'app : elles vérifient par les tests et par des requêtes HTTP. Une autre session peut travailler dans le même dossier : **ne committer que ses propres fichiers**. Aucune dépense réelle (appel `claude`, `gh`) sans l'accord de l'utilisateur.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Tâches du plan | Pourquoi ce modèle | État |
|---|---|---|---|---|
| A | Sonnet 5.5 | 1, 2 : workflows du projet, genre de la fonctionnalité ; relevé, tableau, départ et mémoire | Données et lecture au contrat écrit, tests nommés | **faite** le 2026-11-12 (1121 tests verts) |
| B | Opus 5.5 | 3 : jugements `classer_genre` et `proposer_organisation` | Les consignes décident de la qualité (genres précis, workflow complet jusqu'au livrable) et du coût | à faire : **c'est la prochaine phase** |
| C | Sonnet 5.5 | 4, 5, 6, 10 : le moteur suit le workflow de la fonctionnalité, Fable sur accord, parcours d'une nouvelle demande, environnement du poste | Table de règles au contrat écrit, un test par ligne | à faire |
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
