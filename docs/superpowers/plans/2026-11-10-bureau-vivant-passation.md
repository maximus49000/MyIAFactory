# Le bureau vivant — passation entre conversations

Le plan (`2026-11-10-bureau-vivant.md`) est réalisé en quatre phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les étapes de sa phase sans s'arrêter, puis s'arrête et annonce la suivante.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle | Étapes du plan | État |
|---|---|---|---|
| A | Sonnet | 1 à 6 : le serveur | à faire |
| B | Opus | 7 et 8 : la logique de la page et la scène 3D | à faire |
| C | Sonnet | 9, 10 et 11 : l'interface, le mode d'emploi, le mobilier Tripo | à faire |
| D | Opus | 12 : le personnage Tripo, puis la relecture finale de tout le projet | à faire |

Notes laissées par la phase précédente (écarts au plan, choix faits, points à surveiller) :

- (aucune pour l'instant)

## Ce que chaque conversation doit savoir

**Le cadre**

- Dossier de travail : la racine de ce dépôt. Dépôt GitHub public `maximus49000/MyIAFactory`, branche `main`.
- La conception et le plan sont **validés par l'utilisateur**. Il ne faut ni reposer les questions de cadrage ni refaire un plan : on exécute. Méthode : la conversation réalise elle-même les étapes, dans l'ordre, sans sous-agent par étape (skill `superpowers:executing-plans`).
- Lire d'abord, en entier : la conception `docs/superpowers/specs/2026-11-10-bureau-vivant-design.md`, le plan `docs/superpowers/plans/2026-11-10-bureau-vivant.md`, et ce fichier.
- Les sections « Global Constraints », « Les fichiers » et « Les deux formats » du plan valent pour toutes les étapes.

**Les règles à ne pas oublier**

- Dépôt public et vide de tout projet : rien de propre à un projet réel, rien de privé.
- Python : `py -3.12`, bibliothèque standard uniquement. Tests : `py -3.12 -m unittest discover -s tests -v` et `node --test bureau/web/tests/`.
- Chaque étape : test d'abord, le voir échouer, coder, le voir passer. Puis cocher l'étape dans le `README.md`, commit en français terminé par `Co-Authored-By: Claude <noreply@anthropic.com>`, et `git push`.
- Ne jamais annoncer qu'une étape est finie sans avoir lancé les tests et lu leur sortie. Si un test échoue ou si une étape ne peut pas être faite comme prévu, le dire avec la sortie, ne pas contourner.
- Un écart au plan (signature changée, fichier en plus) est permis s'il est nécessaire : le noter ci-dessus dans « Notes laissées », car la phase suivante ne lit que le plan et ce fichier.
- Répondre à l'utilisateur en français.

**Ce qui demande l'utilisateur**

- Étape 8 : son accord avant de télécharger three.js (la liste des fichiers est dans le plan).
- Étapes 11 et 12 : c'est lui qui lance les générations Tripo. Lui donner le prompt du plan **avec tous les réglages**, une génération à la fois, vérifier le nombre de caractères (1000 maximum), attendre la capture puis le fichier, intégrer, et seulement ensuite donner la génération suivante.
- En dehors de ces moments, ne pas s'arrêter pour demander : enchaîner les étapes de la phase.

**La fin d'une phase**

1. Tous les tests passent (les deux commandes), sortie lue.
2. Mettre à jour « Où on en est » : la phase passe à « fait », et les notes pour la suivante sont écrites.
3. Dernier commit et push.
4. Dire à l'utilisateur, en clair : ce qui a été fait, ce qui n'a pas pu l'être, **quelle est la prochaine étape**, avec quel modèle, et le message à coller pour la lancer (ci-dessous). Puis s'arrêter : ne pas entamer la phase suivante.

## Les messages à coller

Un message par conversation. L'utilisateur crée la conversation dans ce dossier, choisit le modèle, colle le message.

**Phase A — Sonnet**

> Réalise la phase A du bureau vivant. Lis `docs/superpowers/plans/2026-11-10-bureau-vivant-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les étapes 1 à 6 du plan sans t'arrêter, puis fais la fin de phase décrite dans la passation.

**Phase B — Opus**

> Réalise la phase B du bureau vivant. Lis `docs/superpowers/plans/2026-11-10-bureau-vivant-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les étapes 7 et 8 du plan, puis fais la fin de phase décrite dans la passation. Le rendu doit être joli : soigne le cadrage isométrique, la lumière, les couleurs et la fluidité des déplacements.

**Phase C — Sonnet**

> Réalise la phase C du bureau vivant. Lis `docs/superpowers/plans/2026-11-10-bureau-vivant-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne les étapes 9, 10 et 11 du plan, puis fais la fin de phase décrite dans la passation.

**Phase D — Opus**

> Réalise la phase D du bureau vivant. Lis `docs/superpowers/plans/2026-11-10-bureau-vivant-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais l'étape 12 du plan. Ensuite, relis tout le projet contre la conception et le plan (un relecteur indépendant, puis tes corrections) : exactitude, cas de la section « Review Focus », rien de propre à un projet ni de privé dans le dépôt, légèreté de la page. Termine par la fin de phase ; la prochaine étape à annoncer est le branchement d'un premier projet réel, à concevoir dans le dépôt de ce projet.
