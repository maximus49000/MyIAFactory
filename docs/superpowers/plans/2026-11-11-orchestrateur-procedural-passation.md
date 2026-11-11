# L'orchestrateur procédural — passation entre conversations

Le plan (`2026-11-11-orchestrateur-procedural.md`) est réalisé en phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. **Une phase est un lot de modèle** (la norme de la skill) : un même modèle fait d'une traite tout ce qu'il peut faire d'affilée. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les tâches de sa phase sans s'arrêter, puis s'arrête et annonce la suivante. Même méthode que `2026-11-11-installation-sur-un-projet-passation.md`.

Toutes les phases se font **dans ce dépôt**. Les données d'un essai réel (suivi, transcriptions, scénario construit, rapports du banc) restent **hors dépôt** ; leurs chemins sont donnés par l'utilisateur dans la conversation de la phase, jamais écrits ici. Les sessions de phase n'utilisent pas le panneau navigateur de l'app : elles vérifient par les tests et par des requêtes HTTP. Une autre session peut travailler dans le même dossier : **ne committer que ses propres fichiers**.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Tâches du plan | Pourquoi ce modèle | État |
|---|---|---|---|---|
| A | Opus 5.5 | 1 à 3 : mesure d'un appel vide, couche d'appel, appels de jugement et leurs consignes | Les consignes de jugement décident de la qualité et du coût ; la mesure décide de la couche | **faite** le 2026-11-11 |
| B | Sonnet 5.5 | 4 à 7 : rapport structuré, lancer un agent, table de règles, boucle | Code au contrat écrit, tests nommés un par ligne de la table | **faite** le 2026-11-11 |
| C | Sonnet 5.5 | 8, 12, 9 puis 10 : démarrage et option API, agents cloud (sessions Claude Code, coût estimé), scénario et rejoueur, outils du banc | Changements cadrés, tests nommés | à faire : **c'est la prochaine phase** |
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

**Phase A (Opus 5.5).**
- `moteur/appel.py` : en plus du contrat, `Reponse.usages` (un usage par modèle, le principal d'abord ; `Reponse.usage`
  est le principal) et `Reponse.cout_usd` ; `ErreurAppel.usages` garde ce qu'un appel raté a coûté (point d'attention
  2 : la tâche 5 le note quand même). **La boucle doit noter chaque élément de `usages`** (`lancer usage` ne prend
  qu'un modèle par ligne ; un agent `claude -p` peut en employer plusieurs).
- Commande d'un **agent** (`outils` non vide) : le prompt de Claude Code est gardé (`--append-system-prompt-file`
  pour le départ), `--tools` reçoit les noms d'outils, `--allowedTools` les règles (`Bash(py:*)`), et
  `--permission-prompts none` refuse tout le reste sans attendre ; session gardée pour la reprise ; pas de MCP, pas de
  réglages. Essayé en vrai (Haiku, `Read`) : 0,0015 $, environ 13 700 tokens d'entrée. Sans `dossier_travail`, un
  jugement tourne dans un dossier temporaire vide.
- `ANTHROPIC_API_KEY` est **retirée de l'environnement de `claude -p`** : sinon Claude Code facturerait les agents
  sur la clé API au lieu de l'abonnement dès que l'option API est activée.
- `trouver_claude()` : PATH, puis l'installation de l'application Claude (voir « Mesures »). Le bureau
  (`bureau/demarrage.py`) ne cherche que dans le PATH : à aligner en tâche 8.
- `moteur/jugement.py` : `extraire_json` (dernier bloc ```json, sinon le texte, sinon les accolades) et `CLE_ERREUR`
  (clé ajoutée au dossier pour le second essai) sont publics. Un `ErreurAppel` compte comme un essai raté. Le
  docstring liste les clés de dossier attendues par type : la tâche 6 les remplit.
- Conseil : `transmettre_agent` prend `{"consigne", "agent"?}`, `poser_decision` `{"texte"}`, `lancer`
  `{"commande", "entree"}` (commande connue, hors commandes du bureau, `lecon` et `genre`). À l'essai, le modèle a mis
  un **rôle** (« dev ») dans `agent` : la tâche 6 doit accepter une clé ou un rôle (`agent-libre`).
- Essai réel des cinq consignes sur un petit dossier synthétique : toutes valides au premier essai ; 1 500 à 1 800
  tokens d'entrée par appel ; `decouper` 713 tokens de sortie, `ecrire_methode` 2 310 (Sonnet). Ordre de grandeur
  d'une fonctionnalité : moins de 0,05 $ de jugement.

**Phase B (Sonnet 5.5).**
- **Écart au plan : une commande `ecrire`** (`orchestrateur/outil.py`, `interface.md`, `consignes.md`). Le moteur doit
  écrire le document de méthode et les briefs rendus par `ecrire_methode`, et aucune commande ne le permettait ; pour
  tenir « le moteur n'écrit que par `lancer` », `ecrire` écrit `<pièces>/<fonctionnalité>/<nom>.md` (inscrit dans les
  documents) ou ajoute un texte à `<fiches>/briefs/<rôle>.md`. Rien d'autre n'est écrit. Un adaptateur de projet peut la
  remplacer comme les autres.
- **Rapport structuré** (`moteur/rapport.py`) : en plus du contrat, trois champs facultatifs demandés **par la matière**
  des agents concernés (pas par la consigne de fin commune) : `nom` et `cahier` (cadrage), `methode_prete` (prototype).
  Les tests de l'`usage` de `orchestrateur` et du bloc `json` du départ sont dans `tests/test_moteur_rapport.py`.
- **Outils d'un agent** : ligne `Outils :` facultative de la fiche (`fiches.outils`, défaut `fiches.OUTILS_PAR_DEFAUT`,
  repris par `agents.OUTILS_PAR_DEFAUT`). `agents.executer_agent` accepte aussi `tache`, `lot`, `delai_s`.
- **Architecture de `regles.py`** : les fonctions publiques **exécutent** leurs commandes (par `lancer`) et ne rendent
  que ce qui reste asynchrone : `("juger", type, dossier, suite)` et `("agent", agent, taches, matiere)` (plus
  `("lancer", nom, entree)`, que la boucle sait aussi passer). La `suite` d'un jugement porte l'identifiant de la
  demande, qui n'est marquée traitée qu'à la fin du jugement (ou de l'agent, `etat["liees"]`). `appliquer_jugement` prend
  `etat` en cinquième argument. Le modèle du départ est dans `etat["departs"][taches[0]]`.
- **Une tâche « en attente de départ »** = pas active, pas faite, jamais prise, d'étape `flux:<id>`, `prototype`,
  `relecture`, `correction`, `retour` ou `demande` (ou dans `etat["a_lancer"]` : cadrage, challenge, agent imposé). Les
  tâches de flux sont regroupées par `lancer lots` ; tout le reste part seul. Charge (`feu_vert`), pause et
  `agent-libre` sont tenus avant chaque départ.
- **Choix pour tenir la conception** : la relecture croisée est faite en code (deux relecteurs au premier tour, un seul
  ensuite, comparaison des `verdicts`) ; un refus passe par `apres_refus` (Haiku) sauf si le seuil de tours est dépassé
  ou si le même point échoue sur deux éléments (décision `methode_a_revoir` posée **sans IA**). Un accord
  (`accord_requis`) ou un outil refusé devient un **message à choix** dans la discussion (aucun genre de décision ne
  convient) ; la réponse revient en `message` (« J'accepte », « C'est fait, relancez l'agent »…).
- **Prototype** : un seul tour d'agent par message de l'utilisateur, au rôle de la première étape du flux (le flux
  entier n'est appliqué qu'en série). `methode adapter` écrit la méthode adaptée d'emblée (sans seconde validation).
- **Limites connues (à traiter ou à accepter en phase D)** : l'état de la série (éléments en cours, tours de
  relecture, dépendances, contrôles refusés) est **en mémoire** ; après un arrêt, seules les tâches orphelines sont
  reprises (une fois). Pas de montée de modèle dédiée pour l'écriture du cahier ; pas d'alternance des relecteurs ni de
  retour à deux relecteurs quand une correction refait plus de la moitié de l'élément ; pas de proposition de genre ni
  d'organisation par le moteur ; `partenaires_maj` relève seulement les fiches à refaire (la recherche n'est pas
  lancée, la réponse le dit). Un message de l'utilisateur envoyé pendant qu'un agent de cadrage répond n'est pas relu
  avant sa fin. Les jugements sont synchrones (la boucle attend leur fin).
- **La boucle** (`moteur/boucle.py`) lit le bureau à chaque passage (projet ajouté pris sans redémarrer), lance les
  agents dans des fils (`synchrone=True` pour les essais), note l'usage de chaque appel, commit/push le dépôt du projet
  avec `Factory : <ce que l'agent a dit>` (`git add -A` sur tout le dossier du projet), relance une fois les tâches
  orphelines. La ligne « API sans clé » est dite dans la réponse de la première demande traitée du projet. Le verrou
  `moteur.pid` et le démarrage depuis le bureau sont en tâche 8 ; `py -3.12 -m moteur [--bureau …]` tourne déjà.

## Messages à coller

**Phase A — Opus 5.5 — dans ce dépôt**

> Réalise la phase A de l'orchestrateur procédural. Lis `docs/superpowers/plans/2026-11-11-orchestrateur-procedural-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne d'une traite les tâches 1 à 3 du plan. N'utilise pas le panneau navigateur de l'app. Une autre session peut travailler dans le même dossier : ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase B — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase B de l'orchestrateur procédural. Lis `docs/superpowers/plans/2026-11-11-orchestrateur-procedural-passation.md` et suis-le. Enchaîne d'une traite les tâches 4 à 7 du plan. N'utilise pas le panneau navigateur de l'app. Ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase C — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase C de l'orchestrateur procédural. Lis `docs/superpowers/plans/2026-11-11-orchestrateur-procedural-passation.md` et suis-le. Enchaîne d'une traite les tâches 8, 12, 9 puis 10 du plan (dans cet ordre). N'utilise pas le panneau navigateur de l'app. Ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase D — Opus 5.5 — dans ce dépôt**

> Réalise la phase D de l'orchestrateur procédural : la tâche 11 du plan, avec moi. Lis `docs/superpowers/plans/2026-11-11-orchestrateur-procedural-passation.md`. Je te donnerai les chemins de l'essai de référence (hors dépôt). Demande mon accord avant le passage complet en vrai. Ne committe que tes fichiers.

## Fin de phase

1. Toute la suite verte (`py -3.12 -m unittest discover -s tests -v`, `node --test "bureau/web/tests/*.test.js"`).
2. Cocher les tâches faites dans le plan, mettre à jour « Où on en est » et les notes.
3. Commit (ses seuls fichiers) et push.
4. Annoncer la phase suivante, son modèle et son message à coller.
