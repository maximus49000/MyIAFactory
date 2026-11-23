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
