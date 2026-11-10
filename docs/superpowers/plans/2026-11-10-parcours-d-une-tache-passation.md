# Le parcours d'une tâche — passation entre conversations

Le plan (`2026-11-10-parcours-d-une-tache.md`) est réalisé en dix phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les tâches de sa phase sans s'arrêter, puis s'arrête et annonce la suivante. Même méthode que `2026-11-10-dossiers-des-services-passation.md`.

Les phases A à G se font **dans ce dépôt**. Les phases H, I et J se font **dans le dépôt privé du projet pilote** : elles tiennent leurs notes dans ce dépôt privé, et n'écrivent ici que des corrections génériques et, à la toute fin, une ligne générique dans le `README.md` et dans ce fichier.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Où | Tâches du plan | Pourquoi ce modèle | État |
|---|---|---|---|---|---|
| A | Sonnet 5.5 | ce dépôt | 1 à 3 : relevé v4, état v4, demandes et images jointes | Validation de champs entièrement décrite par le plan, tests en tableau | à faire |
| B | Opus 5.5 | ce dépôt | 4 et 5 : plusieurs projets, catalogue et livrable servis | Serveur à fils scindé en deux classes sans rien casser, isolation entre projets, fichiers servis (bac à sable) | à faire |
| C | Sonnet 5.5 | ce dépôt | 6 à 8 : sélecteur, panneau de fonctionnalité et discussion, Directeur | Interface cadrée par les demandes et l'état des phases A et B | à faire |
| D | Opus 5.5 | ce dépôt | 9 : le catalogue | Reprendre fidèlement le design d'une page existante, carte avec zoom, 5 000 éléments | à faire |
| E | Sonnet 5.5 | ce dépôt | 10 à 12 : fichier de factory, suivi, mémoire, départ d'un agent, vérificateur | Outils en ligne de commande au contrat écrit ; les cas difficiles (git, mots interdits, écritures concurrentes) ont leurs tests nommés | à faire |
| F | Opus 5.5 | ce dépôt | 13 et 14 : consignes génériques, démo, documentation, relecture finale | Les consignes guident l'orchestrateur : leur justesse compte plus que tout ; relecture finale sur un modèle fort | à faire |
| G | Opus 5.5 | ce dépôt (projets copiés hors dépôt) | 15 : le vrai passage de bout en bout, mené avec l'utilisateur | Diagnostic d'un orchestrateur réel et corrections génériques | à faire |
| H | Opus 5.5 | dépôt du projet pilote | la liste de compatibilité | Ne rien oublier du fonctionnement actuel : lecture fine de longues consignes | à faire |
| I | Sonnet 5.5 | dépôt du projet pilote | les adaptateurs, la version 4, les demandes, le catalogue | Travail cadré par l'interface et contrôlé par `verifier_interface.py` | à faire |
| J | Opus 5.5 | dépôt du projet pilote | la bascule et la vérification finale | Dernier mot sur « rien n'est perdu » | à faire |

Les modèles sont une proposition ; l'utilisateur a le dernier mot. Haiku n'est retenu pour aucune phase : chacune demande de lire une conception longue et de tenir des tests. **Fable n'est utilisé dans aucune phase**, ni pour exécuter, ni pour relire (la relecture finale se fait sur Opus).

Notes laissées par les phases précédentes (écarts au plan, choix faits, points à surveiller) :

*(aucune pour l'instant)*

## Ce que chaque conversation doit savoir

**Le cadre**

- Dossier de travail : la racine de ce dépôt (phases A à G). Dépôt GitHub public `maximus49000/MyIAFactory`, branche `main`.
- La conception et le plan sont **validés par l'utilisateur**. Il ne faut ni reposer les questions de cadrage ni refaire un plan : on exécute. La conversation réalise elle-même les tâches de sa phase, dans l'ordre (skill `superpowers:executing-plans`).
- Lire d'abord, en entier : la conception `docs/superpowers/specs/2026-11-10-parcours-d-une-tache-design.md`, le plan `docs/superpowers/plans/2026-11-10-parcours-d-une-tache.md`, et ce fichier. Les sections « Global Constraints » et « Review Focus » du plan valent pour toutes les tâches.

**Les règles à ne pas oublier**

- Dépôt public et vide de tout projet : rien de propre à un projet réel, rien de privé. Le projet pilote n'est jamais nommé ici, ni dans le code, ni dans les mémoires, ni dans les commits.
- Python : `py -3.12`, bibliothèque standard uniquement. Tests : `py -3.12 -m unittest discover -s tests -v` et `node --test "bureau/web/tests/*.test.js"`.
- Aucun test ne sort sur Internet ; les tests de mémoire n'utilisent que des dépôts git temporaires locaux.
- Chaque tâche : test d'abord, le voir échouer, coder, le voir passer. Puis cocher la tâche dans le `README.md`, commit en français terminé par `Co-Authored-By: Claude <modèle de la conversation> <noreply@anthropic.com>`, et `git push`.
- Ne jamais annoncer qu'une tâche est finie sans avoir lancé les tests et lu leur sortie. Si un test échoue ou si une tâche ne peut pas être faite comme prévu, le dire avec la sortie, ne pas contourner. Si un passage complet de `unittest` échoue une fois sans raison visible, rediriger la sortie dans un fichier et noter le nom du test.
- Un écart au plan (signature changée, fichier en plus) est permis s'il est nécessaire : le noter ci-dessus dans « Notes laissées », car la phase suivante ne lit que le plan et ce fichier.
- Répondre à l'utilisateur en français.

**Ce qui demande l'utilisateur**

- Phase D : le chemin de la page de catalogue actuelle du projet pilote sur sa machine (lue en lecture seule, rien n'en est recopié).
- Phase G : c'est lui qui crée les conversations orchestratrices et mène la fonctionnalité dans le bureau.
- Phases H à J : c'est lui qui ouvre la conversation sur le dépôt privé, et qui crée les sessions cloud demandées.
- En dehors de ces moments, ne pas s'arrêter pour demander : enchaîner les tâches de la phase.

**La fin d'une phase**

1. Tous les tests passent (les deux commandes), sortie lue.
2. Mettre à jour « Où on en est » : la phase passe à « fait », et les notes pour la suivante sont écrites.
3. Dernier commit et push.
4. Dire à l'utilisateur, en clair : ce qui a été fait, ce qui n'a pas pu l'être, **quelle est la prochaine phase**, avec quel modèle, **dans quel dossier** l'ouvrir, et le message à coller pour la lancer (ci-dessous). Puis s'arrêter : ne pas entamer la phase suivante.

## Les messages à coller

Un message par conversation. L'utilisateur crée la conversation dans le dossier indiqué, choisit le modèle, colle le message.

**Phase A — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase A du parcours d'une tâche. Lis `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 1 à 3 du plan sans t'arrêter, puis fais la fin de phase décrite dans la passation.

**Phase B — Opus 5.5 — dans ce dépôt**

> Réalise la phase B du parcours d'une tâche. Lis `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 4 et 5 du plan, puis fais la fin de phase décrite dans la passation.

**Phase C — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase C du parcours d'une tâche. Lis `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 6 à 8 du plan, puis fais la fin de phase décrite dans la passation.

**Phase D — Opus 5.5 — dans ce dépôt**

> Réalise la phase D du parcours d'une tâche. Lis `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 9 du plan : demande-moi d'abord le chemin de la page de catalogue actuelle du projet pilote, lis-la en lecture seule pour en reprendre le design, et n'en recopie rien de propre au projet. Termine par la fin de phase décrite dans la passation.

**Phase E — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase E du parcours d'une tâche. Lis `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 10 à 12 du plan, puis fais la fin de phase décrite dans la passation.

**Phase F — Opus 5.5 — dans ce dépôt**

> Réalise la phase F du parcours d'une tâche. Lis `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 13 et 14 du plan. La tâche 14 se termine par la relecture de tout le projet contre la conception et le plan (un relecteur indépendant sur Opus, jamais Fable, puis tes corrections) : exactitude, cas du « Review Focus », rien de propre à un projet ni de privé dans le dépôt. Termine par la fin de phase.

**Phase G — Opus 5.5 — dans ce dépôt**

> Réalise la phase G du parcours d'une tâche. Lis `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 15 du plan avec moi : prépare les projets copiés hors du dépôt, donne-moi le message qui ouvre chaque conversation orchestratrice, puis guide-moi pas à pas et corrige ici, avec un test, chaque écart générique. Termine par la fin de phase ; la prochaine phase à annoncer est la phase H, dans le dépôt privé du projet pilote.

**Phase H — Opus 5.5 — dans le dépôt privé du projet pilote**

> Réalise la phase H du parcours d'une tâche de MyIAFactory, pour ce projet. Le dépôt de la skill MyIAFactory est sur cette machine (demande-moi son chemin si tu ne le trouves pas) : lis-y `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md`, la conception, le plan (« Étape 6 ») et `docs/orchestrateur.md` ; tout est validé, rien à recadrer. Relis les consignes d'orchestration actuelles de ce projet et ses outils, puis écris dans ce dépôt : la liste de compatibilité (chaque comportement actuel, l'outil qui le porte, comment le vérifier ; rien ne doit être perdu), le fichier de factory avec ses mots interdits, les consignes propres (le document actuel), le plan des adaptateurs, et une passation pour les phases I et J. N'écris rien de propre à ce projet dans le dépôt de la skill. Arrête-toi ensuite et annonce la phase I.

**Phase I — Sonnet 5.5 — dans le dépôt privé du projet pilote**

> Réalise la phase I du parcours d'une tâche de MyIAFactory, pour ce projet. Lis la passation et le plan des adaptateurs écrits en phase H dans ce dépôt, puis, dans le dépôt de la skill, `orchestrateur/interface.md` et `docs/orchestrateur.md`. Écris les adaptateurs (sans modifier les outils existants), les champs de la version 4 du relevé, les nouvelles demandes dans la commande d'actions, l'étage des leçons et le catalogue au format de la skill à côté de la page actuelle. `verifier_interface.py` doit passer sans `--complet` sur ce projet, et avec `--complet` sur une copie marquée. Une correction générique va dans le dépôt de la skill, avec son test et sans nom de ce projet. Arrête-toi ensuite et annonce la phase J.

**Phase J — Opus 5.5 — dans le dépôt privé du projet pilote**

> Réalise la phase J du parcours d'une tâche de MyIAFactory, pour ce projet. Lis la passation de ce dépôt. Fais passer ce projet sur l'orchestrateur générique, avec moi : vérifie chaque ligne de la liste de compatibilité et coche-la, et dis-moi en clair toute ligne qui ne passe pas. Lance ensuite, dans le dépôt de la skill, un `git grep` avec les mots interdits de ce projet : aucun résultat attendu. Enfin, dans le dépôt de la skill seulement, mets à jour le `README.md` et `docs/superpowers/plans/2026-11-10-parcours-d-une-tache-passation.md` en une phrase générique (« projet 3 terminé, vérifié sur le projet pilote »), sans aucun nom, commit et push. Annonce ensuite la prochaine étape : le projet 4, l'installation sur un projet, à concevoir.
