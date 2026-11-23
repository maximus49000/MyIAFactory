# Route serveur des campagnes de tests — conception

Date : 2026-11-23. Statut : **conception, à relire par le Directeur.** Rien n'est implémenté. Remplace le brouillon non suivi
`docs/superpowers/specs/2026-11-20-tests-sur-le-serveur-design.md` (copie principale), dont elle reprend ce qui tient
(places `flock`, protections de la tranche A, protocole de mesure) et corrige ce que les mesures du 2026-11-23 ont démenti.

**Amendement du 2026-11-23 (exigence du Directeur)** : « Il faut que l'on puisse le faire qu'importe le projet : on doit
pouvoir déporter les tests si un serveur est dispo (donc analyse, modification de l'image, etc. sont nécessaires). » La
route ne se limite plus à Python et Node : chaque projet est **analysé** (§ 5.11), reçoit un **profil d'exécution**, une
**image** prise au catalogue ou **dérivée** (§ 5.12), un **cache de dépendances** (§ 5.13) et des **limites selon son
profil** (§ 5.14) ; l'adoption (§ 5.15) remplace le statut `non_supporte` par `image_a_construire` ou `non_deportable`
(raison précise, jamais silencieuse). Q1 et Q2 sont décidées (oui, oui).

## 1. Intention

Décision du Directeur (2026-11-23) : **toutes les campagnes de tests tournent sur le serveur OVH, aucune sur ce poste**
(7,4 Go ; une seule campagne le sature : 71 % de processeur, 0,7 Go libres), **plusieurs en parallèle** au serveur à côté
des agents du serveur. Serveur injoignable : repli au poste. Règle R4 : économe en temps et en tokens.

Pourquoi c'est faisable maintenant (mesure réelle du 2026-11-23, conteneur jetable `myiafactory/agent`, `--cpus 8
--memory 20g`, suite MyIAFactory, 4 374 tests) : phase principale **≈ 190 s**, **817 s de processeur cumulé** (contre
4 538 s au poste), 762 s au total en comptant les relances en série de 18 modules en échec. **15 modules échouent
(309 tests)** : tests propres à Windows (PATH du registre, `C:/Program Files`, règles de noms) et tests **non hermétiques**
(`mise_en_place.sh` lit le sshd/ufw réel de l'hôte au lieu des faux). 2 modules (`test_moteur_detache`, `test_orch_factory`)
n'ont échoué que sous charge. Le brouillon du 20 estimait 220–300 s : le serveur est en fait **plus rapide** que le poste
et 5,5 fois moins gourmand en processeur cumulé.

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
- O1. `python lancer.py tests [--dossier D] -- <commande>` (la commande que tout agent et tout projet utilise déjà) part
  **au serveur** quand l'accord est posé, avec la **même sortie en direct** et le **même code de sortie** ; l'agent n'a rien
  d'autre à apprendre.
- O2. `py -3.12 outils/tests_paralleles.py [--touches|<filtres>]` (suite de MyIAFactory) part au serveur de la même façon.
- O3. N campagnes à la fois au serveur (N mesuré, 2 proposé), file d'attente premier arrivé premier servi.
- O4. Repli automatique au poste, par une règle exacte (§ 5.4), sous le verrou du poste comme aujourd'hui.
- O5. La suite de MyIAFactory **verte sous Linux** : marqueurs `Windows seulement` / `Linux seulement` là où il le faut,
  et les 15 modules rendus hermétiques, module par module.
- O6. **Tout projet** (amendement) : Python, Node, Gradle/Android (tests unitaires), JVM (Gradle, Maven), .NET (SDK
  multiplateforme), Go, Rust, Godot, Unity (sous réserve de la licence, Q3), et toute pile dont la chaîne d'outils existe
  sous Linux x86_64 ; chacun par son profil d'exécution (§ 5.11–5.14). Seuls restent au poste les projets **non
  déportables** de la liste fermée du § 5.14, avec la raison montrée au Directeur.

**Non-objectifs** : tests **instrumentés** Android et tout test sur émulateur (ils relèvent des actions existantes
`emulateur` et `recette-emulateur`, KVM, image `myiafactory/emulateur`) ; compilation de chaînes d'outils depuis les sources
(pyenv, rbenv : seules des archives officielles vérifiées ou des paquets de la distribution) ; tableau de bord des places au
bureau (la file passe par l'affichage d'attente existant, § 5.6) ; index local des campagnes au serveur (`taches.json` n'en
sait rien).

**Anti-objectifs** : aucune campagne au serveur sans l'accord du bureau (règle R10) ; aucun secret, aucun réseau, aucune
socket Docker dans le conteneur de tests ; jamais de relance silencieuse ailleurs **après** un échec de test (seule une
panne d'acheminement replie) ; jamais deux campagnes au poste par le repli (le verrou du poste reste la loi au poste) ;
aucun démon de plus au poste ni au serveur.

## 3. Contraintes

- `outils/deporter.py`, `outils/campagne.py` et ce qu'ils importent restent **compatibles Python 3.9** (agents) ; la route
  vit dans des modules Python 3.12 importés **à l'appel** seulement, ou lancés par un Python 3.12 à part
  (`deporter._python_312`, même porte que `serveur-tache`).
- Réutiliser : `serveur_tache.choisir_serveur(requises=…)` (état local, aucune connexion), `_bash`, `_octets`,
  `plateforme_ssh` (options SSH, clé `id_ed25519_myiafactory`), `commun.sh` (`dk`, `ecrire_etat`, motifs), le patron des
  places `flock` de `lancer_agent.sh` (`~/taches/.creneau-agent-<k>`), `serveur_capacites` + `serveur_installation`
  (étape, marqueur `~/.myiafactory/<image>.version`, empreinte), `deport_types.refus_accord`, `campagne.relayer`,
  `tests_mesures.noter_campagne(lieu="serveur")` (le champ `lieu` existe déjà).
- Le plan « tests économes » (`docs/superpowers/plans/2026-11-23-tests-performants-peu-couteux.md`) est **exécuté avant**
  celui-ci : sa tâche 7 remplace `tests_un_a_la_fois()` par `tests_rapides(lieu, budget_s)` ; on prolonge cette fonction.
- Les tests du plan ne touchent jamais le vrai serveur : faux `ssh`, faux `docker`, `bash` sur scripts avec un `PATH` de faux.

## 4. Approches envisagées

**A. Action déportée `tests` au lieu `serveur`, en tâche détachée de la tranche A** (le brouillon du 20) : demande, index
`taches.json`, veilleur détaché, `rapatrier` de la sortie à la fin. + réutilise tout le cadre. − la sortie n'arrive qu'à la
fin (un agent ne voit rien pendant 3 min et relance), quatre allers-retours SSH, index et veilleur à tenir pour une action
qui dure 3 minutes ; le brouillon exigeait aussi un commit **poussé** (`git bundle`), ce qui interdit de tester un travail
en cours — l'usage principal des agents.

**B. Route en direct, attachée à la session SSH** : le lanceur envoie un instantané de l'arbre de travail, puis une seule
session SSH lance un conteneur au premier plan ; la sortie arrive en flux, le code de sortie est celui de la commande ; une
« laisse » (l'entrée standard de la session) tue le conteneur si le poste s'en va. + même expérience que `lancer.py tests`
aujourd'hui, deux appels SSH, rien à rapatrier, pas d'index. − pas de reprise si le poste redémarre en pleine campagne
(acceptable : la campagne est refaite, elle dure 3 min).

**C. GitHub Actions** (déjà servi par `deporter`) : gratuit pour un dépôt public, mais exige un commit poussé, ajoute
1 à 3 min de file, et ne répond pas à la décision « au serveur ».

**Choix : B.** C'est le seul qui garde la sortie en direct, les modifications non commitées et le code de sortie, avec le
moins de pièces neuves. Le cadre de la tranche A est réutilisé pour ses briques (choix du serveur, scripts, places,
capacités), pas pour son cycle de tâche détachée.

## 5. Conception détaillée

### 5.1 Point d'entrée et aiguillage

`lancer.py tests …` appelle déjà `deporter.lancer_tests(argv)`. Nouvel ordre de décision (pur, Python 3.9) :

1. `--local` donné → poste (verrou), comme aujourd'hui.
2. Tests réglés sur GitHub (ou en attente d'un amont GitHub) → `deporter` (inchangé).
3. **Accord serveur** (§ 5.7) posé pour le projet → **route serveur** (`tests_serveur.executer`, § 5.4).
4. Sinon → poste (verrou).

`--serveur` (nouveau) force la route **sans repli** (code 4 si injoignable) : pour les mesures et la vérification Linux.
`--sans-attendre` garde son sens : place du serveur toutes prises → code 3 (pas de repli au poste, qui serait la même
attente en pire).

`outils/tests_paralleles.py` (MyIAFactory) suit le même aiguillage avant `campagne.attendre_son_tour` : avec l'accord pour
le dépôt MyIAFactory, il s'envoie lui-même au serveur et y lance `python3 outils/tests_paralleles.py -j <cpus> <modules>`.
`--touches` est **résolu au poste** (il lui faut `git` et `origin/main`) et devient une liste de modules : `.git` ne part pas.
Dans le conteneur, `MYIAFACTORY_TESTS_CONTENEUR=1` coupe la route et le verrou (aucune récursion).

Composition avec la mesure (tâche 2 des tests économes) : une campagne au serveur est notée par
`tests_mesures.noter_campagne(dossier, lieu="serveur", duree_s=<du début du conteneur à sa fin>, attente_s=<de l'appel à la
place obtenue>, code, fin, octets)` ; un repli est noté `lieu="poste"` par `campagne.executer` comme aujourd'hui (une seule
ligne par campagne). Le **verrou du poste** ne s'applique qu'au repli.

### 5.2 Ce qui part : l'instantané

- **Liste** : `git ls-files -co --exclude-standard -z` dans la racine du projet (suivis + non suivis non ignorés, commités ou
  non). Hors dépôt git : refus de route → repli au poste (dit une fois).
- **Exclus toujours** (même suivis) : `.git/`, `.factory/`, `node_modules/`, `.env*`, `*.pem`, `*.key`, `*.p12`, `*.jks`,
  `*.keystore`, `id_rsa*`, `id_ed25519*`, `bureau.json`, `*.local.json`, `tests-sceau.json`. Les liens symboliques et
  fichiers spéciaux ne partent pas (une ligne les nomme, 10 au plus).
- **Amendement** : `local.properties` (chemin `sdk.dir` du poste, parfois des secrets de signature) rejoint les exclus ;
  la limite totale dépend de la famille (§ 5.14 : 1 Go pour Godot et Unity, dont les ressources sont lourdes ; `Library/`
  ne part jamais, elle est un cache du serveur, § 5.13).
- **Ajout** : `.durees-tests.json` s'il existe (ordre des morceaux ; ignoré par git ; jamais rapatrié).
- **Limites** : 50 Mo par fichier, 200 Mo au total, 50 000 fichiers ; au-delà, repli au poste avec la raison.
- **Format** : tar USTAR écrit **dans un fichier temporaire** du poste par flux (jamais tout en mémoire), noms relatifs
  validés (ni absolu, ni `..`, ni `\`), droits 0644/0755, propriétaire 0. Envoi par `executer_octets` vers
  `~/tests/<id>/entree.tar` (mode 0600), sous le motif d'identifiant de la tranche A (`t<AAAAMMJJ>-<HHMMSS>-<4 hexa>`).
- **Extraction dans le conteneur**, pas sur l'hôte : l'archive est montée en lecture seule, l'entrée du conteneur
  l'extrait dans `/work` sous l'utilisateur 1000 (`tar --no-same-owner --no-same-permissions`). Un nom piégé ne peut
  écrire que dans les dossiers inscriptibles du conteneur jetable.
- **Nettoyage** : `~/tests/<id>` est effacé par l'enveloppe à la fin (réussite, échec, arrêt). À chaque lancement,
  l'enveloppe balaie `~/tests/t*` de plus de 6 h sans processus vivant (panne, redémarrage). Aucune rétention : la sortie
  est déjà au poste.

### 5.3 L'image de tests : capacité `tests-image`

- `serveur_ovh/images/tests/Dockerfile` : `ubuntu:24.04` (Python 3.12.3 par la distribution), `nodejs` majeur de
  `versions.json` (`node: 22`), `git`, `bash`, `util-linux` (`flock`), `build-essential`, `tar`, `ca-certificates`,
  utilisateur 1000. Ni Claude Code, ni jeton, ni pont. `entree-tests.sh` : extrait, pose le cache de dépendances, lance
  la commande (tableau JSON, jamais un texte passé à un shell), rend son code.
- Étape `tests_image` de `mise_en_place.sh`, marqueur `~/.myiafactory/tests-image.version`, empreinte
  `ubuntu=…;python=3.12;node=22;fichiers=<16 hexa>` sur le modèle d'`agent_image` (`FICHIERS_ETAPE`, `EMPREINTE_FICHIERS`,
  `MARQUEURS`). Capacité `tests-image` (dépend de `base`, ~1 Go, ~6 min), besoin `"tests-serveur": ("tests-image",)`.
- La route choisit le serveur par `choisir_serveur(requises=("tests-image",))` : état local, aucune connexion.
  Amendement : `requises` vient du profil (§ 5.12 : `("tests-image",)`, `("tests-android",)`, ou `("tests-image",)` plus
  l'image dérivée connue du registre local).
- Constat (lecture du `Dockerfile` livré) : l'image installe Node par `curl … setup_22.x | bash -` (script NodeSource non
  épinglé). Les images dérivées l'interdisent (§ 5.12) ; l'image de catalogue est alignée sur la même règle (archive
  officielle et `SHASUMS256.txt`) dans la tâche 14c.

### 5.4 Exécution, flux, arrêt, repli

**Deux appels SSH** : (1) `_octets` dépose l'archive (et, pour Node, rien de plus) ; (2) une session lance
`~/myiafactory/serveur_ovh/taches/lancer_tests.sh <id> <places> <cpus> <memoire_mo> <duree_s> <projet> <deps>` (`projet` :
l'identifiant du bureau ; `deps` : 16 hexa de l'empreinte du verrou Node, ou `-`) avec la commande en JSON sur la première ligne de l'entrée standard ; **le reste de l'entrée standard est la laisse** : tant
qu'elle reste ouverte, la campagne vit ; fin de fichier (poste parti, Ctrl-C, ssh tué) → `docker kill tests-<id>`.

`lancer_tests.sh` (sourçant `commun.sh`) : valide chaque argument par motif ; contrôle le disque (moins de 5 Go libres →
code 76) ; balaie ; prend une **place** (§ 5.5) en attendant son tour (une ligne `#attente <rang>/<total>` sur la sortie
d'erreur toutes les 30 s, que le poste affiche) ; lance `docker run --rm --name tests-<id>` **au premier plan** sous
`timeout <duree_s>` ; relaie la sortie du conteneur telle quelle ; écrit en dernier sur la sortie d'erreur
`#fin <code> <debut_epoch> <fin_epoch> <attente_s>` ; nettoie ; rend le code du conteneur.

Au poste, `plateforme_ssh.executer_en_flux` relaie la sortie standard par `campagne.relayer` (mêmes octets, ordre, fin
gardée sur 4 Ko pour la mesure) et lit la sortie d'erreur ligne par ligne (`#attente`, `#fin`, le reste gardé sur 64 Ko).

**Règle de repli (exacte)** — repli au poste, **une fois**, avec une ligne « Serveur … : tests au poste (une campagne à la
fois) », dans ces cas seulement :
- R1. aucun serveur prêt pour `tests-image` d'après l'état local (jamais sondé, injoignable à la dernière sonde, image
  absente ou périmée) ;
- R2. dépôt de l'archive en échec de connexion (code 255 ou 124) ;
- R3. l'enveloppe refuse pour le disque (76) ou l'image (77 : image absente sur l'hôte) ;
- R4. session perdue **avant** `#fin` (code 255/124 sans ligne `#fin`) : la campagne est refaite au poste ;
- R5. instantané hors limites ou projet hors git.

Jamais de repli : test en échec (le code est celui de la commande), Ctrl-C (code 130, rien n'est relancé), `--serveur`
(code 4), argument refusé par l'enveloppe (code 2 : un défaut du lanceur, dit tel quel), `--sans-attendre` sur places
prises (code 3).

**Mémoire de l'injoignable (R4 économe)** : après R2 ou R4, `~/MyIAFactory/tests-serveur-injoignable.json` (`{serveur_id,
jusqu_a}`) envoie au poste **sans essai SSH** pendant 5 minutes ; effacé à la première campagne réussie au serveur.

### 5.5 Parallélisme : places, limites, file

- **Places** : `~/taches/.creneau-tests-<k>`, k de 1 à `PLACES_MAX = 4`, prises par `flock -n` sur le descripteur 8 comme
  `lancer_agent.sh` ; une place n'est prise que si moins de `<places>` verrous sont tenus (abaisser N n'expulse personne).
  Le verrou meurt avec la session : rien à nettoyer après une panne.
- **File premier arrivé, premier servi** : un ticket `~/tests/.file/<arrivee_ns>-<id>` (avec le PID de l'enveloppe) ; une
  enveloppe ne tente une place que si aucun ticket vivant plus ancien n'attend (même règle que `campagne._devant`). Les
  tickets morts (PID absent) sont ignorés puis effacés.
- **Limites par campagne** (défauts, réglables par le client dans des bornes que l'enveloppe valide) : `--cpus 4`,
  `--memory 8g --memory-swap 8g`, `--tmpfs /tmp:size=4g`, `--pids-limit 2048`, `--ulimit nofile=8192:8192`, durée 1 800 s
  (borne 3 600). Côté Python, `tests_paralleles -j` = `cpus`.
- **N proposé : 2**, avec le budget du serveur (12 fils, 62 Go) : émulateur 2 cpus/6 Go + 2 agents × 2 cpus/4 Go + 2
  campagnes × 4 cpus/8 Go = 14 cpus (léger surengagement, accepté par les quotas CFS) et 30 Go. Le temps du processeur est
  partagé, pas réservé : une campagne seule va plus vite.
- **Protocole de mesure** (outil `outils/tests_mesure_places.py`, lancé par le contrôleur après accord, ~40 min) : suite
  MyIAFactory complète en `--serveur`, (a) 1 campagne seule, (b) 2 puis (c) 3 simultanées, (d) 2 simultanées pendant une
  émulation de recette ; relevés : durée murale de chacune, `#fin`, pic mémoire (`memory.peak` du cgroup du conteneur),
  charge moyenne, disque avant/après. **Règle de choix** : N = le plus grand k tel que la durée murale médiane à k ≤ 1,5 ×
  celle à 1 **et** pic cumulé ≤ 50 % de la mémoire du serveur ; consigné dans `docs/serveur-tests.md`.
- **Amendement** : les places restent le plafond du nombre de campagnes ; s'y ajoutent des **jetons de mémoire** pondérés
  par le profil (§ 5.14).
- **Priorité en saturation** : aucune préemption ; émulation et agents ont leurs propres places ; les tests attendent leur
  place. N est un réglage du bureau par serveur (`places_tests`, 1 à 4, défaut 2), passé en argument.
- **Délais** : `timeout` du serveur (durée max) → code 124 de la commande, dit « durée maximale dépassée » ; aucune
  limite à l'attente d'une place (comme le verrou du poste), mais `--sans-attendre` refuse.

### 5.6 Ce que voit le Directeur

L'attente d'une place au serveur écrit la même note que l'attente du verrou (`~/MyIAFactory/tests-en-attente/<pid>.json`,
`motif` « place de tests au serveur (rang r/t) ») : la fiche de l'agent dit déjà « attend le poste », elle dira « attend le
serveur ». Le journal des tests (`tests-mesures.jsonl`) porte `lieu: serveur` ; la carte « Tests trop lents » et la
Facturation (plan tests économes) en profitent sans changement.

### 5.7 Accord (R10)

Une campagne part au serveur seulement si : le projet **qui contient le dossier** est enregistré au bureau
(`tests_mesures.projet_enregistre`, le plus long s'ils s'emboîtent : une copie de travail `.claude/worktrees/x` rangée sous
le projet compte comme lui) **et** le lieu de `tests` vaut `serveur` dans **ses** réglages enregistrés, **ou** dans le
défaut du bureau (`bureau.json`, clé `deport.lieux.tests`, écrit par le seul Directeur) quand le projet ne règle pas
`tests` lui-même. `deport_types` gagne `ROUTEES_AU_SERVEUR = ("tests",)` à côté de `SERVIES_AU_SERVEUR` : une action
routée garde ses autres lieux (le repli au poste existe), contrairement à `recette-emulateur`. Le catalogue `GENERIQUE` a
déjà `serveur` pour `tests` ; `ANDROID` le gagne par l'amendement (`./gradlew testDebugUnitTest` au serveur ; `emulateur`
reste `poste`). Un projet non enregistré ne part jamais.

Le dépôt MyIAFactory est un projet comme un autre : il part au serveur une fois enregistré au bureau avec `tests` sur
serveur (geste unique du Directeur, jalon J6).

### 5.8 Projets Node (`vitest`, `jest`)

> **Amendement** : ce paragraphe devient le cas `npm` de la règle générale du § 5.13 (mêmes valeurs : `--ignore-scripts`,
> 900 s, 2 Go, deux caches par projet). Q2 = oui : le réseau d'installation est accordé. Ce qui change : sans
> `package-lock.json`, le projet ne reste plus au poste (§ 5.13, « sans verrou ») ; `pnpm` et `yarn` sont servis par le
> même mécanisme (`pnpm install --frozen-lockfile --ignore-scripts`, `yarn install --immutable` avec `enableScripts: false`).

`node_modules/` ne part jamais (binaires de Windows). Si l'instantané contient `package-lock.json`, l'enveloppe prépare un
**cache par projet et par empreinte du verrou** : `~/tests/.deps/<projet>/<sha256(package-lock.json)[:16]>/node_modules`.
Absent : un conteneur d'installation **à part**, seul à avoir le réseau (`bridge`), sans jeton, mêmes protections, lance
`npm ci --ignore-scripts --no-audit --no-fund` (900 s au plus, 2 Go de sortie au plus), puis le cache est figé en lecture
seule. Le conteneur de tests le monte en lecture seule à `/work/node_modules`, **sans réseau**. Deux caches au plus par
projet (le plus ancien effacé). Ce réseau d'installation exige l'accord du Directeur (question Q2) : sans lui, un projet
avec `package.json` reste au poste (règle R5 étendue, dite une fois). `pnpm`/`yarn` : hors champ au départ (poste).

### 5.9 Marqueurs de plateforme et suite Linux

`tests/plateforme_tests.py` (aide minuscule, bibliothèque standard) :
`windows_seulement(raison)`, `linux_seulement(raison)` (décorateurs de classe ou de test, `unittest.skipUnless` avec la
raison préfixée « Windows seulement : » / « Linux seulement : »), et `pas_encore_linux(raison)` (provisoire, même effet que
`windows_seulement`, raison « À rendre hermétique : … », compté à part). `tests_paralleles` lit `skipped=<n>` à la fin de
chaque morceau et affiche en bilan « N ignorés (Windows seulement : a ; Linux seulement : b ; à rendre hermétique : c) ».
Un test ajouté pour Linux qui remplace un test Windows porte `linux_seulement`.

Étape 1 (avec la route) : les 15 modules en échec reçoivent `pas_encore_linux` au niveau du module ; la suite est verte
au serveur dès le premier jour. Étapes suivantes : un lot de modules par tâche, **acceptation par module** : le module
passe dans le conteneur Linux (vérifié par `tests_paralleles.py --serveur <module>`, contrôleur) **et** sous Windows, ou
ses tests restants sont marqués `windows_seulement` avec une raison vraie ; `pas_encore_linux` disparaît du module.
Correctif type des scripts : `mise_en_place.sh` gagne des variables « réservées aux tests » (comme `JVM_RACINE`,
`KVM_PERIPH`) pour la racine de `/etc/ssh` et l'exécutable `sshd`/`ufw`, que les tests pointent vers des faux.

### 5.10 Consigne des agents

`tests_rapides(lieu, budget_s)` (tests économes, tâche 7) gagne `route` : pour un agent **local** d'un projet dont les
tests sont routés au serveur, la ligne du lieu devient : « **Lance tes tests uniquement par le lanceur** : `python
"<LANCEUR_DE_TESTS>" tests --dossier <dossier où lancer> -- <ta commande de test>`. Il les envoie au serveur, où plusieurs
campagnes tournent en parallèle ; si le serveur est injoignable, il les passe au poste, une campagne à la fois. Jamais une
suite lancée directement. » Sans route : la ligne du poste actuelle. Agents **cloud** (machines GitHub, hors du poste) :
**pas de route** (ni clé SSH ni accord là-bas ; ils ne chargent pas le poste) — inchangé. Agents **serveur** : ils testent
dans leur propre conteneur, dans leur budget — inchangé. Projets par la skill : même `lancer.py`, donc même route ;
l'installation propose « Tests : serveur » quand un serveur a `tests-image` (décision de Direction, comme les autres lieux).
`CLAUDE.md` : la règle « une seule campagne à la fois » devient « au poste » ; les commandes restent les mêmes.

### 5.11 Analyse du projet et profil d'exécution (amendement)

Module `outils/tests_profil.py` (Python 3.12, bibliothèque standard, fonctions pures sur un dossier) : `analyser(racine)
-> Profil`. Il **ne lit qu'une liste fermée de fichiers**, bornés à 256 Ko chacun (`installation/examen.py` a déjà
`FICHIERS_CLES`, `DOSSIERS_SAUTES`, `NOMS_ENVIRONNEMENT` et `_lire_borne` : réutilisés, pas dupliqués), ne suit aucun lien,
n'ouvre jamais `.env*`, `local.properties`, `*.keystore`, `*.jks`, ni rien d'`EXCLUS` (§ 5.2), et **n'exécute rien** (ni
`gradlew`, ni `npm`, ni `python setup.py`) : tout se lit par motifs (JSON, TOML de `tomllib`, propriétés, XML borné, et pour
`build.gradle(.kts)` quelques expressions régulières sur des lignes simples).

| Indice lu | Pile déduite | Commande de test proposée | Versions lues |
|---|---|---|---|
| `pyproject.toml`, `requirements*.txt`, `setup.cfg`, `tox.ini`, `pytest.ini`, `tests/` | `python` | `pytest` si déclaré, sinon `python3 -m unittest discover` | `.python-version`, `requires-python`, `.tool-versions` |
| `package.json` (`scripts.test`), `package-lock.json` / `pnpm-lock.yaml` / `yarn.lock` | `node` | `npm test` (ou le script) | `.nvmrc`, `engines.node`, `.tool-versions`, `packageManager` |
| `build.gradle(.kts)` + `gradlew` + `AndroidManifest.xml` | `gradle-android` | `./gradlew testDebugUnitTest` (catalogue `ANDROID`) | `distributionUrl` du wrapper, `compileSdk`, `buildToolsVersion`, `ndkVersion`, `JavaVersion.VERSION_N`/`jvmToolchain(N)`, AGP (`com.android.application` version) |
| `build.gradle(.kts)` sans manifeste | `gradle-jvm` | `./gradlew test` | wrapper, JDK |
| `pom.xml` (+ `mvnw`) | `maven` | `./mvnw -B test` ou `mvn -B test` | `maven.compiler.release`, wrapper |
| `*.csproj` / `*.sln` | `dotnet` | `dotnet test` | `TargetFramework(s)`, `global.json` |
| `go.mod` | `go` | `go test ./...` | directive `go`/`toolchain` |
| `Cargo.toml` | `rust` | `cargo test` | `rust-toolchain(.toml)`, `rust-version` |
| `project.godot` | `godot` | celle du projet (ex. ZooRunner : `python tools/lancer_tests.py` → `godot --headless --script res://tests/lanceur.gd`) | `config/features` (ex. `"4.7"`) |
| `ProjectSettings/ProjectVersion.txt` | `unity` | `unity-editor -batchmode -nographics -runTests -testPlatform EditMode` | `m_EditorVersion` (lu déjà par `examen.py`) |
| `Gemfile`, `composer.json`, `Makefile` | `ruby`, `php`, `make` | `bundle exec rake test`, `composer test`, `make test` si la cible existe | `.ruby-version`, `require.php` |

- **Indices de la CI** : `.github/workflows/*.yml` (lus comme texte, 64 Ko au plus) servent à **confirmer** la commande et les
  versions (`java-version: '17'`, `node-version`, `python-version`, `run: ./gradlew …`) ; jamais exécutés, jamais recopiés
  dans une ligne de shell. Le catalogue du genre (`deport_types.catalogue_du_projet`) et la commande enregistrée de l'action
  `tests` priment sur la CI, qui prime sur la déduction.
- **Profil** (dataclass figée, sérialisée en JSON) : `pile` (une ou plusieurs : monorepo Node + Python = deux familles, une
  campagne par commande) ; `outils` (`{"jdk": "17", "node": "22.11.0", "python": "3.12", "gradle": "9.3.1", "android": {"compileSdk": 36, "build_tools": "36.0.0", "ndk": null}, "godot": "4.7", "unity": "6000.6.7f1"}`) ;
  `commandes` (tableaux, jamais des textes) ; `deps` (`{"gestionnaire": "npm"|"pip"|"gradle"|"maven"|"nuget"|"cargo"|"go"|"bundler"|"composer"|"upm"|null, "verrou": chemin|null, "reseau": bool, "execute_du_code": bool}`) ;
  `caches` (dossiers montés, § 5.13) ; `ressources` (`cpus`, `memoire_mo`, `disque_mo`, `kvm`, `gpu`, `duree_s`) ;
  `isolement` (`standard` ; `licence` pour Unity) ; `non_deportable` (raison du § 5.14 ou `None`) ; `confiance`
  (`haute` : catalogue ou CI concordants ; `moyenne` : déduction seule ; `basse` : indices contradictoires ou pile
  inconnue) ; `empreinte` (SHA-256 de la forme canonique du profil, hors confiance : ce qui change l'image ou les
  dépendances change l'empreinte).
- Exemple réel, MyFridgeCleaner (`C:\Users\maxim\EssaisMyIAFactory\MyFridgeCleaner`) : `gradle-android`, wrapper Gradle
  **9.3.1**, AGP **9.1.1**, `compileSdk 36`, JDK **17** (`JavaVersion.VERSION_17`, et `java-version: '17'` de sa CI),
  `org.gradle.jvmargs=-Xmx2048m`, tests JUnit 4 + `kotlinx-coroutines-test` (pas de Robolectric), aucun
  `distributionSha256Sum` dans le wrapper. Godot : ZooRunner et CasseBrickReborn (Godot **4.7**, tests en `--headless`) ;
  aucun projet Unity dans les essais (`ProjectVersion.txt` absent partout).
- **Ce que l'agent peut changer** : les fichiers de son projet (`.nvmrc`, verrou, commande du script `test`, version du
  JDK) ; l'analyse suit, l'empreinte change, l'adoption est refaite (§ 5.15). Il peut **proposer** un profil forcé (commande,
  versions, ressources) par une décision de Direction `tests_profil` ; le profil forcé est écrit par le bureau seul dans
  `reglages.json` > `tests.profil_force` (même garde que le budget). **Seul le Directeur approuve** : une image dérivée,
  le réseau d'un échauffement qui exécute du code (§ 5.13), des ressources au-delà des défauts du profil, la licence Unity.

### 5.12 Catalogue d'images et images dérivées (amendement)

**Ce qui existe au serveur** (lu dans `serveur_capacites.py`, `mise_en_place.sh`, `images/*`, `versions.json`) :

| Image / capacité | Contenu | Usage pour les tests |
|---|---|---|
| `myiafactory/tests` (`tests-image`) | Ubuntu 24.04, Python 3.12, Node 22, `build-essential`, utilisateur 1000 | profils `python`, `node`, `make` : **catalogue** tel quel |
| SDK de l'hôte `~/android-sdk` (`android-build`) | platform `android-36`, build-tools `36.0.0`, JDK 17 de l'hôte | **monté en lecture seule** dans l'image `tests-android` (même patron que `myiafactory/emulateur`, qui monte ce SDK) |
| `myiafactory/android` (étape `images`, aucune capacité) | Ubuntu, JDK 17, Gradle 8.7, platform **34**, build-tools 34, tourne en root, garde `curl` | **ne convient pas** : MyFridgeCleaner exige `compileSdk 36` et Gradle 9.3.1 ; pas réutilisée |
| `myiafactory/emulateur` (`emulateur-image`), `android-emulateur` | émulateur KVM | hors champ (tests instrumentés, actions `emulateur`/`recette-emulateur`) |
| `unityci/editor:ubuntu-6000.6.7f1-android-4.0.0` (étape `images`, tirée) + volume `unity-cache` ; étape `licence` | éditeur Unity 6000.6.7f1 GameCI ; licence `.ulf` reçue sur l'entrée standard et prouvée dans un conteneur | profil `unity` **si** la version du projet est 6000.6.7f1 **et** la licence est active (Q3) ; aucune capacité ne suit ni l'image ni la licence aujourd'hui |
| `unity-cli`, `unity-editeur` (non installable : Unity Hub de la session graphique) | outils de l'**hôte** | jamais pour les tests (pas d'isolement) |
| `myiafactory/agent` (`agent`) | Claude Code, pont | jamais (porte un client d'agent) |

**Nouvelle image de catalogue `myiafactory/tests-android`** (capacité `tests-android`, dépend de `tests-image` et
`android-build`) : `FROM myiafactory/tests` + `openjdk-17-jdk-headless` (et `openjdk-21-jdk-headless`, tous deux de la
distribution), rien d'autre ; le SDK de l'hôte est monté en lecture seule sur `/opt/android-sdk` (`ANDROID_HOME`), Gradle
vient du **wrapper du projet** (distribution mise en cache à l'échauffement, § 5.13). Le profil exige que `compileSdk`,
`buildToolsVersion` et `ndkVersion` soient présents dans ce SDK ; sinon statut `image_a_construire` avec la proposition
« ajouter `platforms;android-N` au SDK du serveur » (étape `android_build` étendue, décision de Direction).

**Images dérivées** quand aucune image de catalogue ne convient (Node 18, JDK 11, .NET 8, Go 1.23, Rust 1.82, Godot 4.7,
Maven…) :
- **Gabarit fermé** `outils/tests_images.py:rendre_dockerfile(profil) -> (texte, sha256)` : `FROM myiafactory/tests@<digest
  courant>` (ou `ubuntu:24.04` épinglé de `versions.json`), puis **un bloc par outil** pris dans une table fermée
  (`OUTILS = {"jdk", "node", "python", "maven", "dotnet", "go", "rust", "godot", "unity"}`) dont chaque bloc ne reçoit que des
  valeurs **validées par motif** (`^[0-9]{1,3}(\.[0-9]{1,4}){0,3}$`, plus `-stable`/`f<n>` pour Godot et Unity) : aucun texte
  du projet n'est interpolé ailleurs que dans ces champs ; tout autre caractère → refus (`ValueError`), testé.
- **Sources autorisées** (téléchargées dans un fichier, jamais `curl | sh`, somme vérifiée, construction refusée sinon — même
  discipline que l'étape `emulateur_image` et son SHA-1 du manifeste Google) : paquets Ubuntu signés (`openjdk-N`, `ruby`,
  `php`) ; Node : archive `nodejs.org/dist/vX/…-linux-x64.tar.xz` + `SHASUMS256.txt` ; Python autre que 3.12 : archive
  `python-build-standalone` + sa somme publiée ; Maven : archive Apache + `.sha512` ; .NET : archive du SDK de Microsoft
  + `sha512` de `releases.json` ; Go : `go.dev/dl` + `sha256` de `?mode=json` ; Rust : `rustup-init` + `.sha256`, puis
  `--default-toolchain <v> --profile minimal` ; Godot : archive officielle `godot-builds` + `SHA512-SUMS.txt` ; Unity :
  `unityci/editor:ubuntu-<version>-base-<gameci>` tiré **par digest**. Interdits : `nvm`, `sdkman`, `pyenv`, scripts
  d'installation non épinglés, `ADD <url>`.
- **Construction** : par l'enveloppe `serveur_ovh/taches/construire_image_tests.sh <etiquette> <sha256>` ; le Dockerfile
  rendu au poste est déposé par `_octets` dans un contexte vide (le Dockerfile et `entree-tests.sh`, **aucun fichier du
  projet** : la construction n'exécute aucun code du projet) ; l'enveloppe refuse si son SHA-256 n'est pas celui que la
  décision a approuvé ; `docker build` avec le **réseau de construction seulement** (Q4), 1 800 s au plus, disque vérifié ;
  étiquette `myiafactory/tests-<12 hexa de l'empreinte d'image>`, labels `myiafactory.genre=tests-derivee`,
  `myiafactory.empreinte=<64 hexa>`. Le conteneur de tests, lui, reste sans réseau.
- **Décision de Direction** `tests_image_derivee` : montre le Dockerfile rendu (texte, `textContent`), sa taille estimée,
  la durée estimée, « construit au serveur avec le réseau pendant la construction seulement, aucun code du projet n'y
  tourne » ; réponses `construire` / `plus_tard` / `garder_poste`. Une image n'est construite qu'après `construire`.
- **Cache et ramassage** : registre local `~/MyIAFactory/tests-images.json` (`{serveur_id: {etiquette: {empreinte,
  construite_le, utilisee_le, taille_mo}}}`) tenu par les lignes `#image` de l'enveloppe ; reconstruite **seulement** si
  l'empreinte d'image change (outils et versions ; pas le code). Ramassage par `construire_image_tests.sh --ramasser
  <budget_go>` : jamais une image dont un conteneur vit ; d'abord celles non utilisées depuis 30 jours, puis la plus
  anciennement utilisée tant que le total dépasse le budget (`budget_images_go`, défaut 30, Q5).

### 5.13 Dépendances : caches par projet et échauffement (amendement)

Règle unique pour tous les gestionnaires (le cas Node du § 5.8 en est une instance) :
- **Cache** `~/tests/.deps/<projet>/<famille>-<16 hexa>/` ; l'empreinte = SHA-256 du **verrou** (`package-lock.json`,
  `pnpm-lock.yaml`, `yarn.lock`, `poetry.lock`, `uv.lock`, `requirements*.txt` épinglés, `Cargo.lock`, `go.sum`,
  `packages.lock.json`, `Gemfile.lock`, `composer.lock`, `Packages/packages-lock.json`, `gradle.lockfile`) **et** de
  l'empreinte d'image. Gradle sans verrou : empreinte de `settings.gradle*`, de tous les `build.gradle*`,
  `gradle/libs.versions.toml`, `gradle.properties`, `gradle-wrapper.properties` (verrou implicite) ; Maven : tous les
  `pom.xml`.
- **Contenu par famille** : `npm`/`pnpm`/`yarn` → `node_modules` ; `pip` → un `venv` ; Gradle → `GRADLE_USER_HOME`
  (wrapper, `caches/modules-2`) ; Maven → `~/.m2/repository` ; NuGet → `~/.nuget/packages` ; Cargo → `CARGO_HOME` registre +
  `target/` des dépendances ; Go → `GOMODCACHE` ; Unity → `Library/` (import des paquets UPM et des ressources).
- **Échauffement** (conteneur `deps-<id>` à part, avant la place de tests, seul à avoir le réseau, aucun secret, mêmes
  autres drapeaux que les tests, ne voit que les manifestes et verrous, sauf quand l'outil l'exige) : `npm ci
  --ignore-scripts` ; `pip install --only-binary=:all: -r …` dans le venv (**aucun code exécuté** ; une dépendance sans
  roue → `execute_du_code`) ; `./gradlew --no-daemon dependencies` ou la tâche de résolution du profil (**exécute les
  scripts de construction du projet** : `execute_du_code`) ; `mvn -B dependency:go-offline` (plugins : idem) ; `dotnet
  restore` ; `cargo fetch` ; `go mod download` ; Unity : un import `-batchmode -quit` (exécute les scripts d'éditeur et a
  besoin de la licence). Le `gradle-wrapper.jar` du projet est vérifié contre les sommes publiées par Gradle avant tout
  lancement (sinon refus : un wrapper modifié est du code arbitraire). Durées : 900 s (npm, pip), 1 800 s (Gradle, Maven,
  Cargo, .NET), 3 600 s (Unity).
- **Réseau d'un échauffement qui exécute du code** (`execute_du_code` vrai : Gradle, Maven, pip sans roue, Unity) :
  accordé par projet par le Directeur (Q4), **recommandé avec une sortie limitée** à une liste fermée de registres par
  famille (Maven Central, `dl.google.com`, `plugins.gradle.org`, `services.gradle.org`, PyPI, npm, NuGet, crates.io,
  `proxy.golang.org`, `packages.unity.com`) par un mandataire éphémère lancé pour la durée de l'échauffement, sur un réseau
  Docker `--internal` (rien ne sort ailleurs ; aucun démon permanent). Refusé : le projet reste au poste avec la raison
  « échauffement réseau non accordé ».
- **Pendant les tests** : le cache figé est monté en **copie sur écriture** (volume local `overlay` : couche basse = le
  cache, en lecture seule ; couche haute = `~/tests/<id>/deps-haut`, effacée en fin de campagne) ; à défaut (vérifié au
  jalon J10), lecture seule et modes propres aux outils (`GRADLE_RO_DEP_CACHE`). Drapeaux hors ligne ajoutés par une table
  fermée par famille : Gradle `--offline --no-daemon`, Maven `-o`, Cargo `--offline`, .NET `--no-restore`, Go
  `GOFLAGS=-mod=readonly GOPROXY=off`, pip `PIP_NO_INDEX=1`, Gradle `-Dkotlin.compiler.execution.strategy=in-process` ;
  `GRADLE_OPTS`/`JAVA_TOOL_OPTIONS` pris dans la table, jamais du projet.
- **Sans verrou** : l'échauffement résout et **garde le verrou produit dans le cache** (jamais réécrit dans le projet) ;
  le cache est dit « non verrouillé », refait au plus tous les 7 jours ; la décision d'adoption propose à l'agent de commiter
  un verrou (proposition, jamais une tâche créée seule).
- **Plafonds et éviction** : par cache (npm, pip 2 Go ; Gradle, Maven, Cargo 6 Go ; Unity `Library/` 10 Go ; au-delà :
  abandon et `#deps-echec`) ; deux caches au plus par projet et par famille ; budget total `budget_caches_go` (défaut 40, Q5),
  éviction du moins récemment utilisé, jamais d'un cache tenu (`flock -s` pendant une campagne, `flock -x -n` pour effacer).
  Échec d'échauffement : code 79, **repli au poste** (R3 étendue), dit une fois.

### 5.14 Exécution selon le profil : poids, limites, ce qui ne part pas (amendement)

- **Ressources par famille** (défauts ; le profil peut les relever dans les bornes, au-delà = décision du Directeur) :

| Famille | cpus | mémoire | durée | instantané max |
|---|---|---|---|---|
| `python`, `make` | 4 | 8 Go | 1 800 s | 200 Mo |
| `node` | 2 | 4 Go | 1 800 s | 200 Mo |
| `gradle-android`, `gradle-jvm`, `maven` | 4 | 8 Go (`-Xmx` du projet + 4 Go, 6 Go au moins) | 2 700 s | 200 Mo |
| `dotnet`, `go` | 4 | 4 Go | 1 800 s | 200 Mo |
| `rust` | 4 | 8 Go | 2 700 s | 200 Mo |
| `godot` | 2 | 4 Go | 1 200 s | 1 Go |
| `unity` | 4 | 10 Go | 3 600 s | 1 Go |

- **Places pondérées par la mémoire** : budget des tests `budget_tests_mo` (réglage du bureau par serveur, défaut
  **32 768**) = 62 Go − agents (4 × 4 Go au plus, `lancer_agent.sh`) − émulateur (6 Go) − système et Docker (~8 Go) ; jetons
  de 2 Go `~/taches/.jeton-tests-1..16` ; une campagne prend `ceil(memoire_mo / 2048)` jetons **en plus** de sa place
  (§ 5.5, plafond du nombre). **Seul le premier de la file** prend des jetons (un par un, gardés jusqu'à en avoir assez) : pas
  d'interblocage, pas de famine (premier arrivé, premier servi). Ex. : 2 Gradle (8 Go) + 2 Python (8 Go) = 16 jetons, la
  cinquième attend. Le processeur reste partagé (quotas CFS), non réservé.
- **Hors de cette fonctionnalité** (et donc pas « non déportables ») : tests instrumentés Android et tout ce qui demande KVM
  → actions `emulateur` / `recette-emulateur` ; les tests unitaires Gradle (`test*UnitTest`) **sont** dans le champ.
- **Non déportables** (liste fermée ; la raison est montrée au Directeur, jamais silencieuse ; le projet reste alors au poste) :
  N1 chaîne d'outils propre à Windows : .NET Framework (`TargetFramework net4xx`, `TargetFrameworkVersion v4.x`), WPF/WinForms
  (`UseWPF`, `UseWindowsForms`), C++ MSBuild (`*.vcxproj`), tests qui pilotent le registre ou PowerShell Windows ;
  N2 macOS/iOS/Xcode (`*.xcodeproj`, `*.xcworkspace`, `Podfile`, cibles iOS) ; N3 GPU obligatoire (CUDA, rendu Vulkan/Metal
  réel : déclaré par le profil forcé ou constaté à l'évaluation) ; N4 matériel (USB, série, Bluetooth, caméra, dongle) ;
  N5 tests qui exigent le réseau ou un secret à l'exécution (constatés à l'évaluation : le conteneur n'aura jamais ni l'un ni
  l'autre) ; N6 architecture autre que x86_64 imposée. Un projet mixte n'est non déportable que pour la commande concernée ;
  ses autres commandes partent.

### 5.15 Adoption par projet (amendement, remplace l'ancienne tâche 15b)

Chaîne, une fois par projet puis à chaque changement d'empreinte de profil : **analyse** (§ 5.11) → **profil** → **image**
(catalogue, ou dérivée : décision `tests_image_derivee`) → **échauffement** des dépendances (§ 5.13 ; décision réseau si
`execute_du_code`) → **une** campagne d'évaluation par la route, sans repli ni nouvelle tentative → **verdict** :
- `passe` → décision « Activer les tests sur le serveur » (`activer` / `plus_tard`) ;
- `echoue` → les 20 premiers tests en échec, classés (« Windows seulement » probable : chemins `C:\`, `\\`, registre,
  `.exe` ; « réseau » ; « secret absent » ; autre) et la proposition de les marquer comme la suite de MyIAFactory (§ 5.9 :
  `windows_seulement`, ou l'équivalent de la pile : `@EnabledOnOs(WINDOWS)` JUnit 5, `Assume` JUnit 4,
  `test.skipIf(process.platform…)`, `[Fact(Skip=…)]`) — tâche **proposée**, jamais créée seule ; `garder_poste`, `plus_tard` ;
- `image_a_construire` → la décision d'image (ou d'ajout au SDK Android) est en attente ;
- `non_deportable` → la raison N1–N6, information + `garder_poste` ;
- `injoignable` (R1–R4) ; `trop_long` (au-delà de la durée de la famille, conteneur arrêté).
Jamais d'activation automatique (R10). `tests.adoption` (dans `reglages.json`, écrit par le bureau seul) garde `statut`,
`empreinte_profil`, `image`, `duree_s`, `nb_tests` ; une empreinte différente à la campagne suivante (verrou, versions
d'outils, commande) remet le projet en évaluation et le dit.

## 6. Sécurité

Le code des tests est **non fiable** (écrit par des agents). Conteneur : `--network none`, `--read-only`,
`--cap-drop ALL`, `--security-opt no-new-privileges`, `--user 1000:1000`, `--pids-limit`, mémoire et swap égaux, `--cpus`,
`--ulimit nofile`, `--tmpfs /tmp`, aucun `-e` hérité (seulement `HOME=/tmp`, `MYIAFACTORY_TESTS_CONTENEUR=1`,
`PYTHONDONTWRITEBYTECODE` absent), **ni socket Docker, ni jeton, ni clé**, archive en lecture seule, étiquette
`myiafactory.genre=tests` (ni `lancer_emulation.sh` ni `lancer_agent.sh` ne le comptent). La commande est un tableau JSON
validé (texte, 64 éléments, 4 Ko) passé à `exec`, jamais à un shell de l'hôte. Ce qu'un agent pourrait faire : lire
l'instantané (c'est son propre projet ; les fichiers sensibles en sont exclus), épuiser sa place (bornée en temps, mémoire,
processus, disque du tmpfs), inonder la sortie (le poste ne garde que 4 Ko ; l'enveloppe coupe au-delà de 50 Mo de sortie
et le dit). L'installation Node a le réseau sans aucun secret, `--ignore-scripts`, et ne voit que le `package.json` et le
verrou (pas les sources). Le poste ne fait confiance qu'aux lignes `#attente`/`#fin` de la sortie d'erreur **de
l'enveloppe** : la sortie du conteneur est relayée sur la sortie standard seulement, et l'enveloppe préfixe toute sortie
d'erreur du conteneur par `| ` pour qu'aucune ligne ne puisse imiter `#fin`.

**Amendement (tout type de projet)** :
- **Construction d'une image dérivée = du code exécuté au serveur avec le réseau.** Bornes : gabarit fermé, valeurs
  validées par motif (aucun texte du projet dans une ligne `RUN`), sources de la liste du § 5.12 avec sommes vérifiées,
  aucun fichier du projet dans le contexte, Dockerfile lié par son SHA-256 à la décision du Directeur, ni secret ni
  `--build-arg` hors table, `docker build` sans `--privileged` ni montage, durée et disque bornés.
- **Échauffement** : réseau sans secret ; quand il exécute du code du projet (Gradle, Maven, pip sans roue, Unity), le risque
  est un code non fiable **avec** réseau : il ne voit que l'instantané (déjà sans secret), sortie limitée aux registres
  (recommandation de Q4), durée, mémoire et disque bornés ; `gradle-wrapper.jar` vérifié ; jamais de jeton, de clé ni de
  socket Docker.
- **Caches** : propres à un projet (jamais partagés entre projets : un projet ne peut pas empoisonner le cache d'un autre),
  figés après l'échauffement, montés en copie sur écriture pendant les tests ; un test ne peut donc pas modifier le cache
  de la campagne suivante.
- **Licence Unity** (si Q3) : c'est un secret ; montée en lecture seule dans le seul conteneur d'un projet Unity accordé,
  copiée sur le tmpfs ; un test du projet **peut la lire** et l'écrire sur sa sortie (relayée au poste) : risque assumé
  seulement par la décision du Directeur.
- **Profil** : l'analyse ne lit qu'une liste fermée de fichiers bornés, jamais un secret, n'exécute rien.

## 7. Laissé à l'implémenteur

Le nom des variables internes ; le format exact des lignes d'attente affichées au poste (en français, une ligne par
changement) ; le découpage des faux binaires dans les tests de l'enveloppe ; le détail du balayage (tant qu'il ne touche
jamais un dossier dont un processus vit) ; les raisons des marqueurs, module par module (vraies, courtes).

## 8. Jalons réels (contrôleur seul, avec le feu vert du Directeur)

J1 construire `tests-image` (`plateforme serveurs installer <id> tests-serveur`) ; J2 une campagne MyIAFactory complète
en `--serveur` (relever la liste exacte des modules en échec) ; J3 protocole de mesure → N ; J4 vérification Linux de
chaque lot de compatibilité ; J5 un projet Node (installation puis tests) si Q2 ; J6 enregistrer MyIAFactory et poser
`tests: serveur` au défaut du bureau ; J7 repli : un serveur rendu injoignable par l'état local (sans toucher au serveur).

Amendement : J5 couvre le profil Node par le mécanisme général ; J8 construire `tests-android` et passer
`./gradlew testDebugUnitTest` de MyFridgeCleaner (échauffement en ligne puis campagne hors ligne) ; J9 construire une image
dérivée (Godot 4.7 pour ZooRunner, ou Node d'un autre majeur), vérifier sa reconstruction nulle à empreinte égale, puis le
ramassage ; J10 échauffement et campagne hors ligne, copie sur écriture vérifiée (le cache est intact après la campagne) ;
J11 parallélisme pondéré : 2 Gradle + 2 Python simultanées, pics mémoire relevés, budget de jetons confirmé ou corrigé ; J12
(si Q3) un projet Unity de test en EditMode. Chacun après le feu vert du Directeur, rien de laissé ensuite hors caches et
images voulus.

## 9. Questions au Directeur

**Décidées** : Q1 (feu vert J1–J3) = **oui** ; Q2 (réseau pour `npm ci --ignore-scripts`) = **oui**.

- **Q3. Licence Unity pour les tests au serveur.** Ce qui existe : l'étape `licence` de `mise_en_place.sh` reçoit un `.ulf`
  sur l'entrée standard, l'écrit dans le volume `unity-cache` et prouve l'activation dans `unityci/editor:ubuntu-6000.6.7f1-android-4.0.0` ;
  aucune capacité ne suit cette licence ni l'image GameCI, donc le bureau ne sait pas si elle est active sur le serveur ; la
  version d'éditeur est figée (6000.6.7f1) ; Unity a restreint l'activation manuelle `.ulf` des licences Personal (à
  vérifier pour votre licence) ; un test du projet peut lire la licence montée. Blocage : sans licence active, aucun test
  Unity ne tourne, au serveur comme sur GitHub. *Recommandation : reporter (aucun projet Unity dans les essais, les jeux
  actuels sont en Godot, déportables sans licence) ; le jour d'un projet Unity, fournir une licence dédiée au serveur et
  ajouter une capacité `unity-licence`.*
- **Q4. Réseau à la construction des images dérivées et aux échauffements qui exécutent du code du projet** (Gradle,
  Maven, pip sans roue, Unity) ? *Recommandation : oui, avec la sortie limitée aux registres de la liste fermée (mandataire
  éphémère, réseau Docker interne), accordée projet par projet à l'adoption ; sans cela, Android/Gradle et JVM restent au
  poste.*
- **Q5. Budget disque du serveur pour les tests** : images dérivées (`budget_images_go`) et caches de dépendances
  (`budget_caches_go`) ? *Recommandation : 30 Go et 40 Go, éviction du moins récemment utilisé, avec la place libre minimale
  de 5 Go déjà exigée (code 76) ; à revoir après J11 d'après les tailles réelles.*
