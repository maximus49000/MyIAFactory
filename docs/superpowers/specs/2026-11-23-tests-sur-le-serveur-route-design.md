# Route serveur des campagnes de tests — conception

Date : 2026-11-23. Statut : **conception, à relire par le Directeur.** Rien n'est implémenté. Remplace le brouillon non suivi
`docs/superpowers/specs/2026-11-20-tests-sur-le-serveur-design.md` (copie principale), dont elle reprend ce qui tient
(places `flock`, protections de la tranche A, protocole de mesure) et corrige ce que les mesures du 2026-11-23 ont démenti.

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
- O6. Projets Python (bibliothèque standard) et Node (`vitest`, `jest`) servis.

**Non-objectifs** : Gradle (`./gradlew test…`) et Unity restent sur GitHub ou au poste (catalogue `ANDROID` inchangé) ;
dépendances Python (`pip`) ; tests d'interface avec navigateur (`playwright`) ; tableau de bord des places au bureau (la
file passe par l'affichage d'attente existant, § 5.6) ; index local des campagnes au serveur (`taches.json` n'en sait rien).

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
déjà `serveur` pour `tests` ; `ANDROID` non (Gradle hors champ). Un projet non enregistré ne part jamais.

Le dépôt MyIAFactory est un projet comme un autre : il part au serveur une fois enregistré au bureau avec `tests` sur
serveur (geste unique du Directeur, jalon J6).

### 5.8 Projets Node (`vitest`, `jest`)

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

## 7. Laissé à l'implémenteur

Le nom des variables internes ; le format exact des lignes d'attente affichées au poste (en français, une ligne par
changement) ; le découpage des faux binaires dans les tests de l'enveloppe ; le détail du balayage (tant qu'il ne touche
jamais un dossier dont un processus vit) ; les raisons des marqueurs, module par module (vraies, courtes).

## 8. Jalons réels (contrôleur seul, avec le feu vert du Directeur)

J1 construire `tests-image` (`plateforme serveurs installer <id> tests-serveur`) ; J2 une campagne MyIAFactory complète
en `--serveur` (relever la liste exacte des modules en échec) ; J3 protocole de mesure → N ; J4 vérification Linux de
chaque lot de compatibilité ; J5 un projet Node (installation puis tests) si Q2 ; J6 enregistrer MyIAFactory et poser
`tests: serveur` au défaut du bureau ; J7 repli : un serveur rendu injoignable par l'état local (sans toucher au serveur).

## 9. Questions au Directeur

- **Q1. Feu vert pour les jalons réels J1 à J3** (construction de l'image, ~6 min ; une campagne ; protocole de ~40 min,
  une campagne de mesure à la fois, rien de laissé ensuite) ? *Recommandation : oui, dès la fin des tâches 1 à 8 du plan.*
- **Q2. Réseau pour l'installation des dépendances Node** (conteneur d'installation à part, `npm ci --ignore-scripts`,
  sans secret, 15 min au plus, puis tests sans réseau) ? *Recommandation : oui ; sans cela les projets Node restent au
  poste et l'objectif « aucune campagne au poste » n'est tenu que pour MyIAFactory.*
