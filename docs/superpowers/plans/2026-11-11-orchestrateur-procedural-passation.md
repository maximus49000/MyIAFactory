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

Mesuré le 2026-11-11 avec `py -3.12 outils/mesurer_appel.py` (Claude Code 2.1.321), consigne « Réponds {"ok":true} », dossier temporaire vide.

**Commande retenue** (la consigne en fichier, le dossier par l'entrée standard) :

    claude -p --output-format json --model <modele> --tools "" --system-prompt-file <consigne>
           --strict-mcp-config --setting-sources "" --disable-slash-commands --no-session-persistence

| Modèle | Commande | Tokens d'entrée (dont cache écrit) | Sortie | Coût d'un appel |
|---|---|---|---|---|
| Haiku 5.5 | dépouillée (3 appels) | ≈ 888 (≈ 886, aucun cache relu d'un appel à l'autre) | 9 | **0,00018 $** |
| Sonnet 5.5 | dépouillée (3 appels) | ≈ 870 (≈ 868) | 9 | **0,0036 $** |
| Haiku 5.5 | par défaut (`claude -p` seul) | ≈ 44 800 (29 600 relus, 15 200 écrits) | 135 | 0,0034 $ |
| Sonnet 5.5 | par défaut | ≈ 44 000 | 9 | 0,061 $ |

- Le texte de départ dépouillé est d'environ 880 tokens ; la commande par défaut en paie environ 44 000 (prompt système, outils, réglages). Le dépouillement divise le coût d'un appel vide par 19 (Haiku) à 17 (Sonnet).
- `--bare` n'est pas utilisable : il exige `ANTHROPIC_API_KEY` (pas de connexion par abonnement).
- L'appel vide Haiku (0,00018 $) est très sous le seuil de 0,004 $ : **couche API non conseillée**, `claude -p` reste la couche par défaut.
- La commande `claude` n'est pas toujours dans le PATH : l'application Claude l'installe sous `%APPDATA%\Claude\claude-code\<version>\<id>\claude.exe` ; le moteur la cherche là en second.

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
