# Les dossiers des services — passation entre conversations

Le plan (`2026-11-10-dossiers-des-services.md`) est réalisé en cinq phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les tâches de sa phase sans s'arrêter, puis s'arrête et annonce la suivante. Même méthode que `2026-11-10-bureau-vivant-passation.md`.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Tâches du plan | Pourquoi ce modèle | État |
|---|---|---|---|---|
| A | Opus 5.5 | 1 à 5 : la facturation (serveur) | Prix, dates figées, requêtes sortantes, valeurs absurdes : une erreur ici fausse des coûts sans se voir | à faire |
| B | Sonnet 5.5 | 6 : dossier, onglets Tâches et Facturation | Interface cadrée par l'interface serveur de la phase A | à faire |
| C | Opus 5.5 | 7 à 9 : connaissances, trois demandes, volet « Challenger » | Protocole en plusieurs étapes (challenge → solutions → verdict), cas de double clic et d'échec partiel | à faire |
| D | Sonnet 5.5 | 10 et 11 : KPI et onglet KPI | Calculs bornés et grille d'affichage | à faire |
| E | Fable 5.1 | 12 : démo, documentation, puis relecture de tout le projet | Le modèle le plus capable pour la relecture finale contre la spec et le Review Focus | à faire |

Les modèles sont une proposition ; l'utilisateur a le dernier mot.

Notes laissées par les phases précédentes (écarts au plan, choix faits, points à surveiller) : *(vide)*

## Ce que chaque conversation doit savoir

**Le cadre**

- Dossier de travail : la racine de ce dépôt. Dépôt GitHub public `maximus49000/MyIAFactory`, branche `main`.
- La conception et le plan sont **validés par l'utilisateur**. Il ne faut ni reposer les questions de cadrage ni refaire un plan : on exécute. La conversation réalise elle-même les tâches de sa phase, dans l'ordre (skill `superpowers:executing-plans`).
- Lire d'abord, en entier : la conception `docs/superpowers/specs/2026-11-10-dossiers-des-services-design.md`, le plan `docs/superpowers/plans/2026-11-10-dossiers-des-services.md`, et ce fichier. Les sections « Global Constraints » et « Review Focus » du plan valent pour toutes les tâches.

**Les règles à ne pas oublier**

- Dépôt public et vide de tout projet : rien de propre à un projet réel, rien de privé.
- Python : `py -3.12`, bibliothèque standard uniquement. Tests : `py -3.12 -m unittest discover -s tests -v` et `node --test "bureau/web/tests/*.test.js"`.
- Aucun test ne sort sur Internet (sources de prix injectées).
- Chaque tâche : test d'abord, le voir échouer, coder, le voir passer. Puis cocher la tâche dans le `README.md`, commit en français terminé par `Co-Authored-By: Claude <modèle de la conversation> <noreply@anthropic.com>`, et `git push`.
- Ne jamais annoncer qu'une tâche est finie sans avoir lancé les tests et lu leur sortie. Si un test échoue ou si une tâche ne peut pas être faite comme prévu, le dire avec la sortie, ne pas contourner.
- Un écart au plan (signature changée, fichier en plus) est permis s'il est nécessaire : le noter ci-dessus dans « Notes laissées », car la phase suivante ne lit que le plan et ce fichier.
- Répondre à l'utilisateur en français.

**La fin d'une phase**

1. Tous les tests passent (les deux commandes), sortie lue.
2. Mettre à jour « Où on en est » : la phase passe à « fait », et les notes pour la suivante sont écrites.
3. Dernier commit et push.
4. Dire à l'utilisateur, en clair : ce qui a été fait, ce qui n'a pas pu l'être, **quelle est la prochaine phase**, avec quel modèle, et le message à coller pour la lancer (ci-dessous). Puis s'arrêter : ne pas entamer la phase suivante.

## Les messages à coller

Un message par conversation. L'utilisateur crée la conversation dans ce dossier, choisit le modèle, colle le message.

**Phase A — Opus 5.5**

> Réalise la phase A des dossiers des services. Lis `docs/superpowers/plans/2026-11-10-dossiers-des-services-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 1 à 5 du plan sans t'arrêter, puis fais la fin de phase décrite dans la passation.

**Phase B — Sonnet 5.5**

> Réalise la phase B des dossiers des services. Lis `docs/superpowers/plans/2026-11-10-dossiers-des-services-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 6 du plan, puis la fin de phase décrite dans la passation.

**Phase C — Opus 5.5**

> Réalise la phase C des dossiers des services. Lis `docs/superpowers/plans/2026-11-10-dossiers-des-services-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 7 à 9 du plan, puis fais la fin de phase décrite dans la passation.

**Phase D — Sonnet 5.5**

> Réalise la phase D des dossiers des services. Lis `docs/superpowers/plans/2026-11-10-dossiers-des-services-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les tâches 10 et 11 du plan, puis fais la fin de phase décrite dans la passation.

**Phase E — Fable 5.1**

> Réalise la phase E des dossiers des services. Lis `docs/superpowers/plans/2026-11-10-dossiers-des-services-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 12 du plan. Ensuite, relis tout le projet contre la conception et le plan (un relecteur indépendant, puis tes corrections) : exactitude, cas du « Review Focus », rien de propre à un projet ni de privé dans le dépôt. Termine par la fin de phase ; la prochaine étape à annoncer est le projet 3 (le parcours d'une tâche), à concevoir.
