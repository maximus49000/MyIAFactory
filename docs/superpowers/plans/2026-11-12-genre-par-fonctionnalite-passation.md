# Un genre et un workflow par fonctionnalité — passation entre conversations

Le plan (`2026-11-12-genre-par-fonctionnalite.md`) est réalisé en phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. **Une phase est un lot de modèle** : un même modèle fait d'une traite tout ce qu'il peut faire d'affilée. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les tâches de sa phase sans s'arrêter, puis s'arrête et annonce la suivante. Même méthode que `2026-11-11-orchestrateur-procedural-passation.md`.

La conception (`docs/superpowers/specs/2026-11-11-genre-par-fonctionnalite-design.md`) est **validée par l'utilisateur** le 2026-11-12 : rien à recadrer. Toutes les phases se font **dans ce dépôt**. Les données d'un essai réel restent **hors dépôt** ; leurs chemins sont donnés par l'utilisateur dans la conversation de la phase. Les sessions de phase n'utilisent pas le panneau navigateur de l'app : elles vérifient par les tests et par des requêtes HTTP. Une autre session peut travailler dans le même dossier : **ne committer que ses propres fichiers**. Aucune dépense réelle (appel `claude`, `gh`) sans l'accord de l'utilisateur.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Tâches du plan | Pourquoi ce modèle | État |
|---|---|---|---|---|
| A | Sonnet 5.5 | 1, 2 : workflows du projet, genre de la fonctionnalité ; relevé, tableau, départ et mémoire | Données et lecture au contrat écrit, tests nommés | à faire : **c'est la prochaine phase** |
| B | Opus 5.5 | 3 : jugements `classer_genre` et `proposer_organisation` | Les consignes décident de la qualité (genres précis, workflow complet jusqu'au livrable) et du coût | à faire |
| C | Sonnet 5.5 | 4, 5, 6, 10 : le moteur suit le workflow de la fonctionnalité, Fable sur accord, parcours d'une nouvelle demande, environnement du poste | Table de règles au contrat écrit, un test par ligne | à faire |
| D | Sonnet 5.5 | 7, 8 : créer un projet vide, le bureau | Installation et page au contrat écrit | à faire |
| E | Opus 5.5 | 9 : banc et essai réel, avec l'utilisateur | Diagnostic du coût et réglage des consignes | à faire |

Les modèles sont une proposition ; l'utilisateur a le dernier mot. **Fable n'est utilisé dans aucune phase.**

## Notes laissées par les phases

(Écarts au plan, choix faits, points à surveiller.)

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
