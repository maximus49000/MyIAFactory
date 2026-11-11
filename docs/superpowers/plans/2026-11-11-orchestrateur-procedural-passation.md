# L'orchestrateur procédural — passation entre conversations

Le plan (`2026-11-11-orchestrateur-procedural.md`) est réalisé en phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. **Une phase est un lot de modèle** (la norme de la skill) : un même modèle fait d'une traite tout ce qu'il peut faire d'affilée. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les tâches de sa phase sans s'arrêter, puis s'arrête et annonce la suivante. Même méthode que `2026-11-11-installation-sur-un-projet-passation.md`.

Toutes les phases se font **dans ce dépôt**. Les données d'un essai réel (suivi, transcriptions, scénario construit, rapports du banc) restent **hors dépôt** ; leurs chemins sont donnés par l'utilisateur dans la conversation de la phase, jamais écrits ici. Les sessions de phase n'utilisent pas le panneau navigateur de l'app : elles vérifient par les tests et par des requêtes HTTP. Une autre session peut travailler dans le même dossier : **ne committer que ses propres fichiers**.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Tâches du plan | Pourquoi ce modèle | État |
|---|---|---|---|---|
| A | Opus 5.5 | 1 à 3 : mesure d'un appel vide, couche d'appel, appels de jugement et leurs consignes | Les consignes de jugement décident de la qualité et du coût ; la mesure décide de la couche | à faire : **c'est la prochaine phase** |
| B | Sonnet 5.5 | 4 à 7 : rapport structuré, lancer un agent, table de règles, boucle | Code au contrat écrit, tests nommés un par ligne de la table | à faire |
| C | Sonnet 5.5 | 8 à 10 : démarrage et option API, scénario et rejoueur, outils du banc | Changements cadrés, tests nommés | à faire |
| D | Opus 5.5 | 11 : le banc sur l'essai de référence, avec l'utilisateur | Diagnostic du coût et réglage des consignes sur un modèle fort | à faire |

Les modèles sont une proposition ; l'utilisateur a le dernier mot. **Fable n'est utilisé dans aucune phase.**

## Mesures

(La phase A note ici la commande `claude -p` retenue, les tokens et le coût d'un appel vide sur Haiku et Sonnet, et « couche API conseillée » si l'appel vide Haiku dépasse 0,004 $.)

## Notes laissées par les phases

(Écarts au plan, choix faits, points à surveiller.)

## Messages à coller

**Phase A — Opus 5.5 — dans ce dépôt**

> Réalise la phase A de l'orchestrateur procédural. Lis `docs/superpowers/plans/2026-11-11-orchestrateur-procedural-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne d'une traite les tâches 1 à 3 du plan. N'utilise pas le panneau navigateur de l'app. Une autre session peut travailler dans le même dossier : ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase B — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase B de l'orchestrateur procédural. Lis `docs/superpowers/plans/2026-11-11-orchestrateur-procedural-passation.md` et suis-le. Enchaîne d'une traite les tâches 4 à 7 du plan. N'utilise pas le panneau navigateur de l'app. Ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase C — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase C de l'orchestrateur procédural. Lis `docs/superpowers/plans/2026-11-11-orchestrateur-procedural-passation.md` et suis-le. Enchaîne d'une traite les tâches 8 à 10 du plan. N'utilise pas le panneau navigateur de l'app. Ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase D — Opus 5.5 — dans ce dépôt**

> Réalise la phase D de l'orchestrateur procédural : la tâche 11 du plan, avec moi. Lis `docs/superpowers/plans/2026-11-11-orchestrateur-procedural-passation.md`. Je te donnerai les chemins de l'essai de référence (hors dépôt). Demande mon accord avant le passage complet en vrai. Ne committe que tes fichiers.

## Fin de phase

1. Toute la suite verte (`py -3.12 -m unittest discover -s tests -v`, `node --test "bureau/web/tests/*.test.js"`).
2. Cocher les tâches faites dans le plan, mettre à jour « Où on en est » et les notes.
3. Commit (ses seuls fichiers) et push.
4. Annoncer la phase suivante, son modèle et son message à coller.
