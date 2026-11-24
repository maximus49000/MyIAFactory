# Tests au serveur : jalons réels (tâche 17), note de reprise

Plan : `docs/superpowers/plans/2026-11-23-tests-sur-le-serveur-route.md` (§ Task 17). Serveur : `serveur-ovh`
(54.36.123.238, 64 Go, 3,6 To). Départ : `origin/main` 0391af2 (PR 26). Mené par un agent en autonomie le 2026-11-24.

## J1 — image `tests-image` : FAIT

- `py -3.12 lancer.py plateforme serveurs installer serveur-ovh tests-serveur --accord` : 3 min 10 s, code 0.
- L'image du serveur était périmée (marqueur `fichiers=3caa7bbbb4e4a011`, dépôt `ca15b375bc5af11f`) : reconstruite.
- Marqueur après : `ubuntu=ubuntu:24.04;python=3.12;node=22;fichiers=ca15b375bc5af11f` = `empreinte_etape("tests_image")`.
- Image `myiafactory/tests:latest` : 921 Mo (avant reconstruction).

## J2 — suite MyIAFactory complète au serveur : FAIT

- `py -3.12 outils/tests_paralleles.py --serveur` : 3 min 44 s de bout en bout (envoi, conteneur, rapatriement),
  dont 204 s de suite au serveur (742 s cumulées, 4 morceaux à la fois, `-j 4`), code 0.
- 197 modules en 207 morceaux, **5 156 tests, 28 ignorés, 0 morceau en échec** : aucun module « à rendre hermétique »
  ne reste (les lots 9–12 tiennent sous Linux).
- Plus longs : `test_serveur_enveloppe` 68,8 s, `test_bureau_serveurs` 65,2 s, `test_serveur_pont` 62,1 s,
  `test_serveur` 57,4 s, `test_serveur_agent_script` 50,3 s.
- Après : `~/tests/` vide (hors `.file`), aucun conteneur restant.
- Note : le dépôt MyIAFactory est déjà enregistré au bureau avec `deport.lieux.tests = "serveur"` dans ses propres
  réglages (`.factory/reglages.json`) : l'accord vient du projet, pas du défaut du bureau (voir J6).

## Brique ajoutée pour J3/J11 : mesure mémoire et émulation dans `tests_mesure_places`

Le plan cite `--serveur-id` et `--avec-emulation`, absents de l'outil, et `pics_mo` restait toujours vide (la
recommandation ne regardait donc jamais la mémoire). Ajouté (tests : `tests/test_tests_places.py`) :
- `Sonde` : lit `/proc/meminfo` du serveur par SSH toutes les 3 s pendant un palier ; pic compté au-dessus du départ ;
- `--serveur-id <id>` (serveur sondé) ; `--avec-emulation <apk> --projet-emulation <projet enregistré>` : une émulation
  pilote démarrée pendant la mesure, arrêtée à la fin ;
- `~/MyIAFactory/tests-places-mesure.json` garde chaque mesure sous sa clé (plus d'écrasement entre deux essais).

## J3 — places : mesures

Serveur : Xeon E5-1650 v4, 12 fils, 64 Go. Suite MyIAFactory complète (`-j 4`) par campagne.
`py -3.12 outils/tests_mesure_places.py --serveur-id serveur-ovh --paliers 1,2,3` (10 min 54 s) :

| campagnes simultanées | durée (chacune) | pic mémoire cumulé (au-dessus du départ) |
|---|---|---|
| 1 | 211 s | 453 Mo |
| 2 | 213 s / 213 s | 674 Mo |
| 3 | 226 s ×3 (+7 %) | 1 027 Mo |

Recommandation de l'outil : `places_tests = 3` (durée sous 1,5× la campagne seule, mémoire très loin de la moitié du
serveur). Une suite Python ne pèse que ~350 Mo : la mémoire n'est pas la limite des campagnes Python, le processeur
l'est (3 × 4 fils = 12 fils, le serveur entier).

`--paliers 2 --avec-emulation <app-debug.apk de MyFridgeCleaner> --projet-emulation <MyFridgeCleaner>` (4 min 51 s) :
émulation pilote `t20261123-234331-89cd` démarrée (émulateur allumé par `demarrer`) puis arrêtée ; 2 campagnes à
**217 s** chacune (+2 % contre 213 s sans émulation), pic **996 Mo** au-dessus du départ (émulateur déjà compté dans le
départ). Le dossier de la tâche au serveur (`~/taches/t20261123-234331-89cd`, 12 Mo) a été effacé à la main : `rapatrier`
exige une destination dans `<projet>/.factory/serveur/`, et le projet MyFridgeCleaner ne devait pas être touché.
(La « recommandation 1 » de cette seconde mesure n'a pas de sens : sans palier 1 dans le même essai, `recommander` rend 1.)

**N recommandé : 3.** Le réglage `places_tests` du serveur reste au Directeur (voir « À faire par le Directeur »).

## J4 — vérification Linux des lots 9–12 : FAIT (par J2)

La suite complète a tourné dans le conteneur Linux sans aucun module en échec ni marqué « pas encore Linux » : chaque lot
(tâches 9–12) tient sous Linux. Rien à corriger.

## J5 — profils Node et Python par le mécanisme général

Projets d'essai jetables (dans le bloc-notes de la session, dépôts git locaux), enregistrés dans un **fichier du bureau
d'essai** (`bureau_essai.py` remplace `BUREAU` des modules `deport_types`, `tests_mesures`, `deporter`,
`serveur_tache_cli` : le bureau du Directeur n'est ni lu ni modifié), `deport.lieux.tests = "serveur"` dans leurs réglages.

- **Node** (`vitest 3.2.4`, `package-lock.json`) : `lancer.py tests --dossier <j5-node> -- npx vitest run`
  1er passage **29 s** (« échauffement des dépendances (npm, 900 s et 2 Go au plus) », `npm ci --ignore-scripts` par le
  mandataire), 1 test passé ; 2e passage **17 s**, aucune ligne d'échauffement (cache `npm-1b2721dc5ce790af` prêt).
  FAIT.
- **Python** (`six==1.17.0` en `requirements.txt`) : 1er essai **en échec** à l'échauffement :
  « The virtual environment was not created successfully because ensurepip is not available » — l'image
  `myiafactory/tests` n'avait pas `python3-venv`, et `tests_hote.py --echauffer pip` crée `python3 -m venv`. L'échec est
  retenu une heure (`pip-….echec`) et la campagne retombait au poste (sans `--serveur`). **Corrigé** : `python3-venv`
  dans le Dockerfile, vérifié à la construction (`python3 -m venv`), test `test_venv_pour_l_echauffement_pip`.
  Image reconstruite (`installer … tests-serveur --accord`, 204 s, marqueur `fichiers=a2c5ecc8f989e4f8`), puis
  `lancer.py tests --serveur --dossier <j5-python> -- python3 -m unittest discover` : 1er passage **30 s** (échauffement
  pip, roues seulement), 2e **9 s** sans échauffement. FAIT.
- Node relancé sur la nouvelle image : 10 s et 10 s, sans nouvel échauffement (le cache npm reste valable).
- **Le contrôleur devra relancer J1 après fusion** si l'image du serveur a été reconstruite depuis une autre branche
  (empreinte `fichiers=a2c5ecc8f989e4f8` = cette branche).

## J6 — MyIAFactory au serveur : constaté ; réglage du défaut du bureau À FAIRE PAR LE DIRECTEUR

- Le dépôt est déjà enregistré au bureau (`C:\Users\maxim\Downloads\MyIAFactory\.factory\reglages.json`) avec
  `deport.lieux.tests = "serveur"` dans ses réglages propres : `py -3.12 outils/tests_paralleles.py --touches` part au
  serveur depuis cette copie de travail (conteneur `tests-t20261124-000115-ac33` vu au serveur, aucun verrou du poste
  pris pendant qu'une campagne ZooRunner le tenait). Les changements de cette branche touchant `outils/`, la sélection
  a pris toute la suite : **5 163 tests, 0 morceau en échec, 204 s au serveur, 230 s de bout en bout**.
- Reste le geste du plan, **défaut du bureau** `deport.lieux.tests = "serveur"` (pour tous les projets qui ne règlent
  rien eux-mêmes) : à faire par le Directeur, voir la section finale.

## J8 — Gradle Android (MyFridgeCleaner)

- `installer serveur-ovh tests-serveur-android --accord` : `tests-android` « fait » en 116 s
  (`base=…fichiers=a2c5ecc8f989e4f8;jdk=17,21;fichiers=50cb6444be1e5ed1`).
- Projet : **une copie** de MyFridgeCleaner (`git clone` local dans le bloc-notes ; le dépôt du Directeur n'est pas touché),
  enregistrée au bureau d'essai, `deport.lieux.tests = "serveur"` et `tests.adoption.reseau_echauffement = "accorde"`
  (Q4, accord du réseau d'échauffement pour ce projet). Évaluation par `tests_adoption.evaluer(…, accord=lambda r: None,
  reseau=lambda r: True)` (ce que fait le bouton du Directeur), sans écrire `tests.adoption`.
- Trois pannes réelles trouvées et corrigées (TDD), dans l'ordre où elles sont apparues :
  1. `#deps-echec somme-gradle-illisible` : `services.gradle.org` renvoie maintenant (301) les sommes vers
     `downloads.gradle.org`, et la distribution (307) vers `github.com/gradle/gradle-distributions/releases`, puis (302)
     vers `release-assets.githubusercontent.com` (URL signée avec `?`, `&`, `%`). `telecharger` ne suivait aucune
     redirection (le corps HTML de la 301 était lu comme une somme). **Corrigé** : redirections suivies à la main (4 au
     plus, jamais `curl -L`) vers les seuls hôtes de `DIST_HOTES`, élargi à `github.com`,
     `release-assets.githubusercontent.com`, `objects.githubusercontent.com` ; motif d'URL accepté avec la requête. La
     distribution reste vérifiée par sa somme officielle (`downloads.gradle.org`). Test `test_redirections_gradle_actuelles`.
  2. L'enveloppe corrigée **n'arrivait pas au serveur** : `lancer_tests.sh`, `tests_hote.py`, `commun.sh`,
     `construire_image_tests.sh`, `entree-unity.sh` sont déposés avec l'étape `tests_image` mais hors de l'empreinte de
     l'image ; marqueur à jour = capacité « présente » = rien n'est redéposé. **Corrigé par une règle générale**
     (`serveur_installation._deposes_perimes`) : pour toute capacité à marqueur, les fichiers déposés hors empreinte sont
     comparés (`sha256sum` au serveur, lecture seule) ; une différence rend la capacité « périmée » et l'installation les
     redépose (image inchangée : « déjà à jour », 9 s). Vaut aussi pour `agent` (`enregistrer_jeton.sh`, `pont_hote.py`).
     Test `test_fichiers_deposes_hors_empreinte_perimes`.
  3. `usage : tests_hote.py --commande | …` : `--echauffer gradle gradle-android` refusé, le motif de famille
     (`[a-z][a-z-]{1,11}`) n'admettait que 12 caractères. Aucun échauffement Gradle Android n'avait donc jamais pu tourner.
     **Corrigé** (`{1,23}`), test `test_echauffer_accepte_toutes_les_familles` (toutes les familles de `FAMILLES`).
  4. `FileNotFoundError: './gradlew'` : la copie avait été extraite avec `core.autocrlf=true` (gradlew en CRLF,
     « #!/bin/sh\r »). Le dépôt du Directeur, lui, est en LF (0 CR). Copie refaite en LF. **Ajouté** : un gradlew en CRLF
     est refusé AVANT tout conteneur avec la raison fermée `gradlew-fins-de-ligne-windows` (remède : `gradlew text eol=lf`
     dans `.gitattributes`). Test `test_gradlew_en_fins_de_ligne_windows`.
  5. `/home/ubuntu/.android: Read-only file system` : AGP écrit dans `~/.android` (`user.home` de Java, racine en
     lecture seule). **Corrigé** : `ANDROID_USER_HOME=/tmp/android` (tmpfs) pour l'échauffement et les tests
     gradle-android ; test dans `test_enveloppe_image_et_famille`.
  6. `Could not download … No cached version available for offline mode` (jars de `debugUnitTestRuntimeClasspath`) :
     l'échauffement ne faisait que compiler (`compileDebugUnitTestSources`) ; les jars d'exécution des tests,
     transformés par AGP, n'étaient jamais téléchargés. **Corrigé** : l'étape facultative de l'échauffement
     gradle-android lance `testDebugUnitTest` (test `test_plan_gradle_android_resout_le_classpath_des_tests`).
     Conséquence à connaître : les tests du projet s'exécutent une fois pendant l'échauffement (même conteneur durci,
     sortie par le mandataire seulement).
- **Résultat** (`lancer.py tests --serveur --dossier <copie> -- ./gradlew testDebugUnitTest`, cache froid) :
  échauffement en ligne puis campagne hors ligne, **BUILD SUCCESSFUL** (1 min 8 s de Gradle pour la campagne),
  **266 s de bout en bout** (échauffement compris), **pic mémoire 3,2 Go** au-dessus du départ, cache
  `gradle-4b7d6124c1a8e4ac` **1,2 Go**, 8 137 fichiers. Wrapper 9.3.1 vérifié contre sa somme publiée
  (`~/tests/.deps/.gradle-wrapper/9.3.1.sha256`), distribution téléchargée par l'hôte et vérifiée.
- **Verdict d'évaluation** (`tests_adoption.evaluer`, cache chaud) : **`passe`**, **83 s**, pic mémoire **2,6 Go**.
  J8 FAIT. Petit défaut relevé : `nb_tests` vaut `null` pour Gradle (`_nb_tests` ne lit pas la sortie de Gradle, qui
  ne compte pas les tests par défaut) — à trancher (voir points).

## J9 — images dérivées : FAIT (Node 20 et Node 18)

Godot 4.7 pour ZooRunner n'a pas été pris (projet du Directeur, campagne ZooRunner en cours au poste) : deux projets
d'essai Node (`.nvmrc` 20 et 18, même vitest), décision « construire » prise en autonomie (Dockerfile rendu par
`tests_images.rendre_dockerfile`, somme approuvée = la sienne), `tests_adoption.construire_image` :
- `myiafactory/tests-4160b6728b10` (Node 20.20.2) : **44 s**, 1,14 Go apparents, **224 Mo propres** ;
- `myiafactory/tests-bacde38ffe62` (Node 18.20.8) : **45 s**, 1,13 Go apparents, **215 Mo propres**.
- Seconde demande à empreinte égale : `evaluer` → **`passe`, 11 s, aucune construction** (registre `image_connue`).
- **Panne trouvée et corrigée** : une image dérivée construite n'était **jamais prise** par la route
  (`_image_de_la_campagne` rendait toujours « image dérivée à construire »). Maintenant : l'étiquette dérivée est prise
  si le registre du poste la connaît pour le serveur choisi (`_verifier_derivee`), et son usage est noté (registre et
  `construire_image_tests.sh --utilise`). Campagnes vitest au serveur : 23 s et 22 s (échauffement npm compris).
- **Ramassage** : 1er essai en échec réel — `docker ps --format '{{.ImageID}}'` est inconnu de Docker 29.10.0 (« can't
  evaluate field ImageID ») : le ramassage s'arrêtait sans rien supprimer. **Corrigé** (identifiants par
  `docker inspect --format {{.Image}}` des conteneurs). Puis, budget 1 Go : rien ne part (439 Mo propres au total,
  sous le budget : juste). Usages vieillis de 40 jours + un conteneur `j9-tenue` sur l'image Node 20 :
  `#ramassee myiafactory/tests-bacde38ffe62` seulement ; **l'image tenue reste**. Conteneur retiré, puis image Node 20
  ramassée à son tour (nettoyage).

## J10 — cache hors ligne et copie sur écriture : FAIT

Sur le cache Gradle de J8 : empreinte de l'arbre (`find contenu -type f -printf "%P %s %T@"` trié, puis `sha256sum`)
**identique avant et après** la campagne hors ligne d'évaluation (`d9be7b66…`, 8 137 fichiers, 1,2 Go) : le volume
`overlay` protège le cache. Aucune ligne « copie sur écriture indisponible » : pas de bascule en lecture seule,
`GRADLE_RO_DEP_CACHE` inutile. (Les caches Node et Python de J5 ont servi aussi deux fois sans réchauffement.)

## J11 — parallélisme pondéré : FAIT

`tests_mesure_places.py --serveur-id serveur-ovh --mixte gradle:2,python:2 --dossier-gradle <copie de MyFridgeCleaner>`
(cache Gradle chaud ; Python = suite MyIAFactory complète) :

| essai | Gradle ×2 (médiane) | Python ×2 (médiane) | pic mémoire cumulé | durée |
|---|---|---|---|---|
| seul | 136 s | 243 s (+15 % contre 211 s seule) | **5,1 Go** | 245 s |
| pendant une émulation pilote (MyFridgeCleaner, émulateur démarré) | 147 s | 245 s | **5,7 Go** | 316 s |

Codes tous 0. Une campagne a attendu sa place un instant (« rang 2/2 », `places` du palier = 4, jetons). Budget mémoire :
le défaut `budget_tests_mo` (16 jetons de 2 Go = 32 Go) est **confirmé** : 4 campagnes mixtes restent sous 6 Go au-dessus
de la charge courante, sur 64 Go ; la limite réelle est le processeur (12 fils). Rien à corriger au bureau. Dossier de la
tâche d'émulation `t20261124-004813-5b55` effacé au serveur (même raison qu'en J3).

## J12 — tests Python de sur-la-route : FAIT

Copie de `C:\Users\maxim\UnityProjects\sur-la-route-bureau` (clone local, le projet n'est pas touché), enregistrée au
bureau d'essai, `lancer.py tests --serveur --dossier <copie> -- python3 -m unittest discover -s Tools/factory/tests` :
- 1er essai refusé : « instantané trop gros : plus de 200,0 Mo ». **Panne corrigée** : `ecrire_tar` ignorait la limite
  de la famille (`limites_pour` : 1 Go pour Unity/Godot) et le serveur (`tests_hote.py --archive`) refusait lui aussi
  tout instantané de plus de 200 Mo. Le poste applique la limite de la famille, le serveur la plus grande (1 Go).
- Puis : **109 tests, OK (2 ignorés), 46 s de bout en bout** (instantané de ~650 Mo envoyé compris), profil `python`,
  image `myiafactory/tests`, aucune licence.
- Instantané : 4 039 fichiers, 0 écarté ; **aucun nom évoquant une licence** (`.ulf`, `Unity_lic`, `licens`,
  `entitlement`, `unityhub`, `.config/unity3d`) ; `Library/` absent.

## J7 — repli : FAIT

Copie de `serveurs.json` + `serveurs-etat.json` dans un dossier d'état d'essai, toutes les capacités marquées
« inconnue » ; `tests_serveur.executer(…, dossier_etat=<copie>, ssh=<objet qui échoue à tout appel>)` :
- ligne de repli : « Serveur indisponible (Aucun serveur prêt pour un agent (tests-image) (serveur-ovh : serveur
  injoignable ou état inconnu à la dernière sonde).) : tests au poste (une campagne à la fois). » ;
- **aucune connexion** (l'objet SSH n'a jamais été appelé) ; campagne au poste sous le verrou, code 0 (10 tests) ;
- elle a attendu 21 min le verrou du poste (une campagne ZooRunner tournait) : la règle « une campagne à la fois » tient.
