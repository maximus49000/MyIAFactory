# L'installation sur un projet — passation entre conversations

Le plan (`2026-11-11-installation-sur-un-projet.md`) est réalisé en huit phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les tâches de sa phase sans s'arrêter, puis s'arrête et annonce la suivante. Même méthode que `2026-11-10-parcours-d-une-tache-passation.md`.

Les phases A à G se font **dans ce dépôt**. La phase H se fait **dans le dépôt privé du projet pilote** : elle y tient ses notes, et n'écrit ici que des corrections génériques et, à la toute fin, une ligne générique dans le `README.md` et dans ce fichier.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Où | Tâches du plan | Pourquoi ce modèle | État |
|---|---|---|---|---|---|
| A | Sonnet 5.5 | ce dépôt | 1 à 3 : chemins `~`, limite d'agents locaux, leçon gardée en local | Changements courts et cadrés, tests nommés | à faire |
| B | Sonnet 5.5 | ce dépôt | 4 à 6 : dossier stable, examen du dossier, calibrage et estimation | Fonctions au contrat écrit, tests en tableau | à faire |
| C | Opus 5.5 | ce dépôt | 7 et 8 : proposition, mise en place, bureau commun, réparation, ligne de commande | Écritures atomiques sur plusieurs formats, réparation sans casser les adaptateurs | à faire |
| D | Opus 5.5 | ce dépôt | 9 : le plugin et les consignes de la discussion | Les consignes guident toute l'installation : sobriété et justesse comptent plus que tout | à faire |
| E | Sonnet 5.5 | ce dépôt | 10 : l'organisation qui évolue | Décision, demande et commande sur le modèle de celles qui existent | à faire |
| F | Opus 5.5 | ce dépôt | 11 : guides et relecture finale | Relecture finale sur un modèle fort | à faire |
| G | Opus 5.5 | ce dépôt (projets copiés hors dépôt) | 12 : le vrai passage, mené avec l'utilisateur | Diagnostic d'une installation réelle et corrections génériques | à faire |
| H | Opus 5.5 | dépôt du projet pilote | 13 : le projet pilote rejoint le nouveau rangement | Dernier mot sur « rien n'est perdu » | à faire |

Les modèles sont une proposition ; l'utilisateur a le dernier mot. Haiku n'est retenu pour aucune phase : chacune demande de lire une conception et de tenir des tests. **Fable n'est utilisé dans aucune phase**, ni pour exécuter, ni pour relire.

Notes laissées par les phases précédentes (écarts au plan, choix faits, points à surveiller) :

(aucune pour l'instant)

## Ce que chaque conversation doit savoir

**Le cadre**

- Dossier de travail : la racine de ce dépôt (phases A à G). Dépôt GitHub public `maximus49000/MyIAFactory`, branche `main`.
- La conception et le plan sont **validés par l'utilisateur**. Il ne faut ni reposer les questions de cadrage ni refaire un plan : on exécute. La conversation réalise elle-même les tâches de sa phase, dans l'ordre (skill `superpowers:executing-plans`).
- Lire d'abord, en entier : la conception `docs/superpowers/specs/2026-11-11-installation-sur-un-projet-design.md`, le plan `docs/superpowers/plans/2026-11-11-installation-sur-un-projet.md`, et ce fichier. Les sections « Global Constraints » et « Review Focus » du plan valent pour toutes les tâches.

**Les règles à ne pas oublier**

- Dépôt public et vide de tout projet : rien de propre à un projet réel, rien de privé. Le projet pilote n'est jamais nommé ici, ni dans le code, ni dans les mémoires, ni dans les commits.
- Contre-buts 1 et 2 de la conception : une installation ou un workflow plus coûteux en tokens que la gestion autonome d'un néophyte, ou des fonctionnalités à côté de la demande, sont des échecs même si tout « marche ».
- Python : `py -3.12`, bibliothèque standard uniquement. Tests : `py -3.12 -m unittest discover -s tests -v` et `node --test "bureau/web/tests/*.test.js"`.
- Aucun test ne sort sur Internet ni ne touche le vrai dossier de l'utilisateur (`HOME` et `USERPROFILE` temporaires, git simulé ou dépôts temporaires locaux).
- Chaque tâche : test d'abord, le voir échouer, coder, le voir passer. Puis cocher la tâche dans le `README.md`, commit en français terminé par `Co-Authored-By: Claude <modèle de la conversation> <noreply@anthropic.com>`, et `git push`.
- Ne jamais annoncer qu'une tâche est finie sans avoir lancé les tests et lu leur sortie. Si un test échoue ou si une tâche ne peut pas être faite comme prévu, le dire avec la sortie, ne pas contourner. Deux tests connus pour tomber parfois sous charge (`test_json_tres_imbrique`, `test_ecritures_concurrentes`) : relancer seuls, noter s'ils retombent.
- Un écart au plan (signature changée, fichier en plus) est permis s'il est nécessaire : le noter ci-dessus dans « Notes laissées », car la phase suivante ne lit que le plan et ce fichier.
- Répondre à l'utilisateur en français.

**Ce qui demande l'utilisateur**

- Phase G : il choisit le petit projet existant à copier, lance la commande et mène les deux discussions.
- Phase H : il ouvre la conversation sur le dépôt privé, et valide les corrections de la réparation.
- En dehors de ces moments, ne pas s'arrêter pour demander : enchaîner les tâches de la phase.

**La fin d'une phase**

1. Tous les tests passent (les deux commandes), sortie lue.
2. Mettre à jour « Où on en est » : la phase passe à « fait », et les notes pour la suivante sont écrites.
3. Dernier commit et push.
4. Dire à l'utilisateur, en clair : ce qui a été fait, ce qui n'a pas pu l'être, **quelle est la prochaine phase**, avec quel modèle, **dans quel dossier** l'ouvrir, et le message à coller pour la lancer (ci-dessous). Puis s'arrêter : ne pas entamer la phase suivante.

## Les messages à coller

Un message par conversation. L'utilisateur crée la conversation dans le dossier indiqué, choisit le modèle, colle le message.

**Phase A — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase A de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 1 à 3 du plan sans t'arrêter, puis fais la fin de phase décrite dans la passation.

**Phase B — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase B de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 4 à 6 du plan, puis fais la fin de phase décrite dans la passation.

**Phase C — Opus 5.5 — dans ce dépôt**

> Réalise la phase C de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 7 et 8 du plan, puis fais la fin de phase décrite dans la passation.

**Phase D — Opus 5.5 — dans ce dépôt**

> Réalise la phase D de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 9 du plan : les consignes de la discussion doivent suivre la conception à la lettre et rester sobres (2 000 mots au plus). Termine par la fin de phase.

**Phase E — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase E de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 10 du plan, puis la fin de phase décrite dans la passation.

**Phase F — Opus 5.5 — dans ce dépôt**

> Réalise la phase F de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 11 du plan ; elle se termine par la relecture de tout le projet 4 contre la conception et le plan (un relecteur indépendant sur Opus, jamais Fable, puis tes corrections). Termine par la fin de phase.

**Phase G — Opus 5.5 — dans ce dépôt**

> Réalise la phase G de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 12 du plan avec moi : prépare hors du dépôt un dossier vide et la copie du petit projet que je te désignerai, dis-moi comment ajouter le plugin depuis ce dépôt, puis guide-moi pas à pas et corrige ici, avec un test, chaque écart générique. Termine par la fin de phase ; la prochaine phase à annoncer est la phase H, dans le dépôt privé du projet pilote.

**Phase H — Opus 5.5 — dans le dépôt privé du projet pilote**

> Réalise la phase H de l'installation sur un projet de MyIAFactory, pour ce projet. Le dépôt de la skill MyIAFactory est sur cette machine (demande-moi son chemin si tu ne le trouves pas) : lis-y `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md`, la conception et le plan (tâche 13) ; tout est validé, rien à recadrer. Fais pointer le dossier stable sur ce dépôt de la skill (`preparer --lier`), lance la réparation sur ce projet et montre-moi chaque correction, vérifie que ses adaptateurs n'ont pas bougé, fais-lui rejoindre le bureau commun, repasse la liste de compatibilité ligne par ligne, puis `git grep -i` des mots interdits de ce projet dans le dépôt de la skill (aucun résultat attendu). Enfin, dans le dépôt de la skill seulement, mets à jour le `README.md` et cette passation en une phrase générique (« projet 4 terminé, vérifié sur le projet pilote »), sans aucun nom, commit et push.
