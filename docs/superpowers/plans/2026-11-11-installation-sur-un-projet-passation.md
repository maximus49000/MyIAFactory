# L'installation sur un projet — passation entre conversations

Le plan (`2026-11-11-installation-sur-un-projet.md`) est réalisé en dix phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les tâches de sa phase sans s'arrêter, puis s'arrête et annonce la suivante. Même méthode que `2026-11-10-parcours-d-une-tache-passation.md`.

Les phases A à I se font **dans ce dépôt**. La phase J se fait **dans le dépôt privé du projet pilote** : elle y tient ses notes, et n'écrit ici que des corrections génériques et, à la toute fin, une ligne générique dans le `README.md` et dans ce fichier.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Où | Tâches du plan | Pourquoi ce modèle | État |
|---|---|---|---|---|---|
| A | Sonnet 5.5 | ce dépôt | 1 à 3 : chemins `~`, limite d'agents locaux, leçon gardée en local | Changements courts et cadrés, tests nommés | fait |
| B | Sonnet 5.5 | ce dépôt | 4 à 6 : dossier stable, examen du dossier, calibrage et estimation | Fonctions au contrat écrit, tests en tableau | fait |
| C | Opus 5.5 | ce dépôt | 7 et 8 : proposition, mise en place, bureau commun, réparation, ligne de commande | Écritures atomiques sur plusieurs formats, réparation sans casser les adaptateurs | fait |
| D | Opus 5.5 | ce dépôt | 14 puis 9 : le support de traitement dans la proposition, puis le plugin et les consignes de la discussion | Les consignes guident toute l'installation : sobriété et justesse comptent plus que tout | à faire |
| E | Sonnet 5.5 | ce dépôt | 10 : l'organisation qui évolue | Décision, demande et commande sur le modèle de celles qui existent | à faire |
| F | Opus 5.5 | ce dépôt | 15 : le bureau ouvert au téléphone, le code d'accès, l'association | Sécurité : un bureau joignable depuis un autre appareil ne doit rien laisser passer sans code | à faire |
| G | Sonnet 5.5 | ce dépôt | 16 : la vue 3D adaptée au mobile | Fonctions pures testées, gestes et mise en page cadrés, vérifiés au navigateur | à faire |
| H | Opus 5.5 | ce dépôt | 11 : guides et relecture finale | Relecture finale sur un modèle fort | à faire |
| I | Opus 5.5 | ce dépôt (projets copiés hors dépôt) | 12 : le vrai passage, téléphone compris, mené avec l'utilisateur | Diagnostic d'une installation réelle et corrections génériques | à faire |
| J | Opus 5.5 | dépôt du projet pilote | 13 : le projet pilote rejoint le nouveau rangement | Dernier mot sur « rien n'est perdu » | à faire |

Les modèles sont une proposition ; l'utilisateur a le dernier mot. Haiku n'est retenu pour aucune phase : chacune demande de lire une conception et de tenir des tests. **Fable n'est utilisé dans aucune phase**, ni pour exécuter, ni pour relire.

Notes laissées par les phases précédentes (écarts au plan, choix faits, points à surveiller) :

Phase A (Sonnet 5.5) :

- Les tâches 1 à 3 sont dans un seul commit (les mêmes fichiers, dont les consignes, sont modifiés par plusieurs tâches).
- `releve.developper` n'accepte que `~/` et `~\` en début d'argument ; le même test vaut pour `factory.lire` (`~x` et `a~b` restent relatifs). Tout passe par `releve._executer`, donc le relevé, les actions, le catalogue et la demande en profitent sans autre changement.
- `depart.agent_libre` : la limite ne compte que les tâches actives tenues par une fiche de lieu `local` ; avec `lieu` non précisé, un agent cloud libre reste rendu quand les locaux sont retenus. La raison « limite de {n} agents locaux atteinte » n'apparaît que si un agent local aurait été rendu sans la limite.
- Relevé : `agents_locaux_max` est un champ de racine de la version 4 ; `libelleCharge(c, agentsLocauxMax)` (`bureau/web/ui/texte.js`) ajoute « {n} agents locaux au plus » à la bulle ; documenté dans `docs/releve.md` et `docs/orchestrateur.md`.
- `test_echec_du_push_defait_tout` est remplacé par `test_push_refuse_garde_le_commit_local` ; `test_echec_du_commit_defait_tout` garde l'ancienne garantie pour les autres échecs.

Phase B (Sonnet 5.5) :

- Les tâches 4 à 6 sont dans un seul commit. Le paquet `installation/` contient `dossier.py`, `examen.py`, `calibrage.py`, `estimation.py` (la phase C ajoute `proposition.py`, `mise_en_place.py`, `outil.py`).
- `dossier.Echec` est l'exception de refus de tout le paquet : la phase C la réutilise (`from installation.dossier import Echec`). `preparer` rend aussi l'action `deja_lie` quand `lier` désigne déjà la cible du dossier stable ; sinon, avec `lier` et un dossier stable déjà dépôt git, le `pull` passe d'abord.
- `examiner` rend en plus la clé `factory` (booléen) ; `nb_fichiers` vaut `"100000+"` au-delà de la borne ; `extensions` est une liste de `[extension, nombre]`.
- `calibrer` : mesure indisponible → `charge_max` reste celui du `conseiller` ; avec historique, `agents_locaux_max` = `floor((85 - repos) / par_agent)` borné à 1..6 (6 si `par_agent` est nul).
- `estimer` lève `ValueError` si un rôle du flux n'a pas d'agent (la proposition le refuse avant). `usages_du_genre` lit le genre de chaque projet du bureau par la clé `orchestrateur` de ses réglages ; un projet illisible est ignoré. Les euros comptent `PART_SORTIE` en sortie et ignorent les caches.

Phase C (Opus 5.5) :

- Deux commits (tâche 7, tâche 8). Aides de test communes dans `tests/inst_aide.py` (`AvecMaison`, `proposition_valide`, `instantane`).
- `proposition.verifier_organisation(services, flux, agents, briefs, cloud, roles_deja_pourvus, cles_prises, briefs_existants)` est la partie « organisation » du contrôle, réutilisable telle quelle par la tâche 10. Les ids de services, d'étapes, de rôles et de clés d'agents suivent `MOTIF_ID` (ils deviennent des noms de fichiers) ; `prenom`, `specialite`, `nom`, chaque contrôle et chaque mot interdit tiennent sur une ligne. Un service `facturation` déclaré à la main est refusé dans les deux cas (vrai : la mise en place l'ajoute ; faux : pas de pièce).
- `mise_en_place.appliquer(p, maintenant, git=executer_git)` : `git` en plus (pour `creer_genre`). Un genre ni connu ni décrit par `genre_nouveau` est refusé avant toute écriture. Le nouveau genre est créé **en dernier**, après la mise en place (il publie hors du projet) ; s'il échoue, le genre reste nul et le rendu porte `genre_raison`. Un `.factory/` sans `factory.json` est refusé (configuration faite à la main : `docs/orchestrateur.md`). `agents_cloud[].environnement` est une liste ; vide = environnement de base.
- `ecrire_organisation` refuse sans rien écrire (clé ou fichier de fiche déjà pris, rôle sans agent ni fiche existante, brief manquant, Fable) ; un brief existant est gardé, jamais réécrit ; `justification` n'entre pas dans le fichier de factory.
- La vérification se fait en processus (`mise_en_place.verifier`, qui joue `verifier_interface.verifier_lecture`) ; chaque commande reste un sous-processus de `outil.py`, d'où environ 1 s par test de mise en place.
- `reparer` rend aussi `relancer_bureau`. Il contrôle le bureau avant d'écrire, ne crée que les dossiers manquants situés dans le projet (fiches, pièces, racines des réglages), et ne touche ni `commandes` ni un catalogue `{fichier}`.
- `installation/outil.py proposer` **recalcule** l'estimation avec `estimer` (les usages du genre et les prix du bureau commun) et l'enregistre à la place de celle reçue. Le fichier de proposition s'appelle `<nom du dossier>-<empreinte du chemin>.json`. Un refus de `proposer` rend `{"erreur", "erreurs": [...]}` ; une entrée JSON illisible rend le code 2 avec `{"erreur"}`. `reparer` ajoute `calibrage` à sa sortie.
- Pour la phase D : `git init` et `gh repo create` restent dans les consignes de la discussion (aucune commande de l'outil ne les fait).

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

- Phase I : il choisit le petit projet existant à copier, lance la commande, mène les deux discussions, installe Tailscale sur l'ordinateur et le téléphone, et associe son téléphone.
- Phase J : il ouvre la conversation sur le dépôt privé, et valide les corrections de la réparation.
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

> Réalise la phase D de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 14 du plan, puis la tâche 9 : les consignes de la discussion doivent suivre la conception à la lettre et rester sobres (2 000 mots au plus). Termine par la fin de phase.

**Phase E — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase E de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 10 du plan, puis la fin de phase décrite dans la passation.

**Phase F — Opus 5.5 — dans ce dépôt**

> Réalise la phase F de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 15 du plan (le bureau ouvert au téléphone, le code d'accès, l'association), puis la fin de phase décrite dans la passation.

**Phase G — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase G de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 16 du plan (la vue 3D adaptée au mobile), vérifie-la dans le navigateur en vue mobile, puis fais la fin de phase décrite dans la passation.

**Phase H — Opus 5.5 — dans ce dépôt**

> Réalise la phase H de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 11 du plan ; elle se termine par la relecture de tout le projet 4 contre la conception et le plan (un relecteur indépendant sur Opus, jamais Fable, puis tes corrections). Termine par la fin de phase.

**Phase I — Opus 5.5 — dans ce dépôt**

> Réalise la phase I de l'installation sur un projet. Lis `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Fais la tâche 12 du plan avec moi : prépare hors du dépôt un dossier vide et la copie du petit projet que je te désignerai, dis-moi comment ajouter le plugin depuis ce dépôt, guide-moi pas à pas, y compris pour associer mon téléphone, et corrige ici, avec un test, chaque écart générique. Termine par la fin de phase ; la prochaine phase à annoncer est la phase J, dans le dépôt privé du projet pilote.

**Phase J — Opus 5.5 — dans le dépôt privé du projet pilote**

> Réalise la phase J de l'installation sur un projet de MyIAFactory, pour ce projet. Le dépôt de la skill MyIAFactory est sur cette machine (demande-moi son chemin si tu ne le trouves pas) : lis-y `docs/superpowers/plans/2026-11-11-installation-sur-un-projet-passation.md`, la conception et le plan (tâche 13) ; tout est validé, rien à recadrer. Fais pointer le dossier stable sur ce dépôt de la skill (`preparer --lier`), lance la réparation sur ce projet et montre-moi chaque correction, vérifie que ses adaptateurs n'ont pas bougé, fais-lui rejoindre le bureau commun, repasse la liste de compatibilité ligne par ligne, puis `git grep -i` des mots interdits de ce projet dans le dépôt de la skill (aucun résultat attendu). Enfin, dans le dépôt de la skill seulement, mets à jour le `README.md` et cette passation en une phrase générique (« projet 4 terminé, vérifié sur le projet pilote »), sans aucun nom, commit et push.
