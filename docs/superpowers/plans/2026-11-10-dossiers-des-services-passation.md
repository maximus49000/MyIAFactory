# Les dossiers des services — passation entre conversations

Le plan (`2026-11-10-dossiers-des-services.md`) est réalisé en cinq phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les tâches de sa phase sans s'arrêter, puis s'arrête et annonce la suivante. Même méthode que `2026-11-10-bureau-vivant-passation.md`.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Tâches du plan | Pourquoi ce modèle | État |
|---|---|---|---|---|
| A | Opus 5.5 | 1 à 5 : la facturation (serveur) | Prix, dates figées, requêtes sortantes, valeurs absurdes : une erreur ici fausse des coûts sans se voir | fait |
| B | Sonnet 5.5 | 6 : dossier, onglets Tâches et Facturation | Interface cadrée par l'interface serveur de la phase A | fait |
| C | Opus 5.5 | 7 à 9 : connaissances, trois demandes, volet « Challenger » | Protocole en plusieurs étapes (challenge → solutions → verdict), cas de double clic et d'échec partiel | à faire |
| D | Sonnet 5.5 | 10 et 11 : KPI et onglet KPI | Calculs bornés et grille d'affichage | à faire |
| E | Fable 5.1 | 12 : démo, documentation, puis relecture de tout le projet | Le modèle le plus capable pour la relecture finale contre la spec et le Review Focus | à faire |

Les modèles sont une proposition ; l'utilisateur a le dernier mot.

Notes laissées par les phases précédentes (écarts au plan, choix faits, points à surveiller) :

**Phase A (tâches 1 à 5, faite).**

- *Écart — la direction n'est pas dans `services`.* Le résultat de `cout.facturation` (et de `GET /api/facturation`) range le chef et les usages sans service dans une clé **`direction` au même niveau que `services`** (même forme : `{total, taches, modeles, usages}`), et non dans `services["direction"]` comme l'écrit le plan : un projet peut avoir un service d'identifiant `direction`, les deux se seraient mélangés sans le dire.
- *Forme exacte de `GET /api/facturation?periode=…`* (pour la phase B) : `{disponible: true, periode, total, gestion, sans_prix: [{modele, tokens, usages}], services: {id: {total, taches: {id: {total, etapes: {nom: euros}}}, modeles: {nom: euros}, usages: [...]}}, direction: {même forme}, sources: [{id, genre, service, tache, texte}], prix_du, avertissement, maj, message}` ; ou `{disponible: false}` (relevé en version < 3, relevé en erreur, ou aucun usage ni dans le relevé ni dans l'historique). Dans `taches` et `etapes`, la clé **`""`** veut dire « hors tâche » / « sans étape » (aucun identifiant réel n'est vide). Un usage de `usages` : `{id, tache, agent, modele, etape, t, tokens: {entree, sortie, cache_lecture, cache_ecriture}, cout (euros ou null si prix inconnu), prix_du, ancien}`. `genre` d'une source : `tache_chere`, `modele_trop_fort`, `allers_retours` (une source par tâche) ; identifiant `source:<service>:<genre>:<tache>`, à recalculer par `cout.id_source`. `message` vaut null quand les prix sont à jour, sinon le texte à montrer (« Prix du …, mise à jour impossible : … », prix automatiques coupés, valeur absurde gardée). `gestion` vaut toujours 0 (le bureau ne consomme aucun token). `cout.euros_en_clair(x)` donne « ≈ 4,20 € » (le serveur l'utilise dans les textes des sources ; la page doit faire de même avec « ≈ »).
- *Écart — la source de prix s'injecte à la construction* : `serveur.creer(chemin, port=None, ouvrir=None)` et `Bureau(adresse, chemin, ouvrir=None)` ; `Bureau.ouvrir` existe toujours. Raison : le fil des prix démarre dans le constructeur, donc un test qui remplacerait `ouvrir` après coup arriverait trop tard (les tests serveur passent une `SourceSimulee`). `Bureau._fil_prix` vaut `None` si `prix_automatiques` est faux **ou si les réglages sont illisibles** (aucune requête dans le doute). Remettre `prix_automatiques` à vrai demande un redémarrage ; le mettre à faux est respecté dès l'heure suivante.
- *État* : `etat["dossier"] = {facturation, kpi, connaissances}`. Pour l'instant `kpi` = un service du relevé v3 a une liste `kpi`, `connaissances` = une liste `challenges` ou un titulaire avec une liste `connaissances` ; les phases C et D valident ces champs et peuvent affiner ces deux règles dans `etat.dossier(r)`. `facturation` est aussi vrai quand l'historique contient des usages (le serveur l'ajoute).
- *Relevé, petits choix* : un usage peut avoir `agent: null` (rangé en direction) ; la clé `chef` ajoutée par la normalisation est un agent connu quand le projet ne déclare pas de chef ; `t` doit être une date ISO lisible ; `cache_lecture`/`cache_ecriture` valent 0 par défaut après normalisation.
- *Prix, choix de réalisation* : après la première lecture, la table ne garde que les prix qui changent ; une valeur absurde est rejetée **modèle par modèle** (le reste de la liste est pris) ; un modèle neuf à 0 $ dans la liste (modèles locaux) est ignoré sans bruit → « prix inconnu » ; un prix de cache absent compte au prix d'entrée ; une correction à la main sans `date` lisible est ignorée (elle bougerait le passé).
- *À surveiller — certificat de la BCE sous Windows.* Sur la machine de l'utilisateur, Python ne peut pas vérifier `www.ecb.europa.eu` (autorité Sectigo Public Server Authentication Root E46, que Windows n'installe qu'à la première visite par un programme Windows). Le bureau le dit en clair dans `message` ; mais **sans aucun taux enregistré, tous les prix restent « inconnus »**. La phase E doit l'écrire dans `docs/installation.md` (ouvrir une fois l'adresse du taux dans Edge). La liste de LiteLLM pèse 3,4 Mo (limite 5 Mo) : à surveiller.
- *À surveiller — une erreur de test vue une fois.* En fin de phase A, un passage complet de `unittest` a donné « FAILED (errors=1) » sans que le test fautif ait été noté, puis dix passages de suite ont été verts. Cause probable corrigée : le fil des prix pouvait encore écrire dans le dossier temporaire d'un test après la fermeture du serveur (`server_close` attend maintenant ce fil). Si l'erreur revient, noter le nom du test.
- *Commits* : le plan écrit « Co-Authored-By: Claude Sonnet 5.5 » ; chaque phase signe avec son propre modèle, comme le dit ce fichier.

**Phase B (tâche 6, faite).**

- *Écart — seuls deux onglets existent.* `dossier.js` exporte `ongletsDisponibles(etat)` : Tâches (toujours) et Facturation (si `etat.dossier.facturation`). La phase C ajoutera Connaissances et la phase D KPI dans cette fonction et dans `dessiner()` (une branche par onglet) ; un onglet sans module n'est pas montré plutôt que vide. `contenuDossier(ctx, conteneur, service, onglet?)` garde onglet et période dans une variable de module (`choix`), et dessine aussi la liste des agents sous les onglets.
- *Écart — le panneau « service » ne reçoit plus la phrase ni la liste d'agents de `panneaux.js`* : tout vient de `contenuDossier`. La signature du panneau inclut `etat.dossier` et les tâches actives, pour redessiner quand elles changent. `ctx.ouvrirTache(id)` ouvre une tâche depuis le dossier.
- *Facturation côté page* : `facturation.js` exporte `chargerFacturation(periode)` (fetch, 15 s, erreur lisible), `serviceFacture`, `lignesTaches`, `lignesModeles`, `dessinerFacturation`. La clé `""` devient « Hors tâche » / « Sans étape ». Le bouton « Challenger » des sources est désactivé (« Bientôt disponible ») : la phase C doit l'activer (c'est dans `dessinerFacturation`). L'onglet Tâches affiche le coût de chaque tâche en cours (même appel, silencieux en cas d'échec). La direction (`donnees.direction`) n'est pas montrée : elle n'a pas de dossier.
- *Texte* : `texte.js` gagne `euros`, `tokens`, `libellePeriode`, `PERIODES`, `PERIODE_DEFAUT`. Le sélecteur de période est masqué si le relevé ne fournit pas de facturation.
- *Vérifié au navigateur* sur une copie de la démo en version 3 (usage inventé, modèle hostile `<img onerror>`, prix à la main, `prix_automatiques: false`) : onglets, période qui recharge, prix inconnu visible, texte hostile affiché tel quel, console vide. Pas de capture d'écran gardée (la capture du dossier est à refaire en phase E).

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
