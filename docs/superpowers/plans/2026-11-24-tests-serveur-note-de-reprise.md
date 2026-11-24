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

## J7 — repli : FAIT

Copie de `serveurs.json` + `serveurs-etat.json` dans un dossier d'état d'essai, toutes les capacités marquées
« inconnue » ; `tests_serveur.executer(…, dossier_etat=<copie>, ssh=<objet qui échoue à tout appel>)` :
- ligne de repli : « Serveur indisponible (Aucun serveur prêt pour un agent (tests-image) (serveur-ovh : serveur
  injoignable ou état inconnu à la dernière sonde).) : tests au poste (une campagne à la fois). » ;
- **aucune connexion** (l'objet SSH n'a jamais été appelé) ; campagne au poste sous le verrou, code 0 (10 tests) ;
- elle a attendu 21 min le verrou du poste (une campagne ZooRunner tournait) : la règle « une campagne à la fois » tient.
