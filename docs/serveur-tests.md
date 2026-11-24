# Tests au serveur

> Document de la tâche 16 (route, repli, places, limites, sécurité, dépannage) : **pas encore écrit**. Cette page ne porte
> pour l'instant que les **valeurs mesurées** aux jalons réels (tâche 17), que le plan demande d'y consigner. Détail et
> protocole : `docs/superpowers/plans/2026-11-24-tests-serveur-note-de-reprise.md`.

## Valeurs mesurées (serveur OVH, Xeon E5-1650 v4, 12 fils, 64 Go ; 2026-11-24)

### Places (`places_tests`, jalon J3)

`py -3.12 outils/tests_mesure_places.py --serveur-id <id> --paliers 1,2,3` (suite MyIAFactory complète, `-j 4`) :

| campagnes simultanées | durée de chacune | pic mémoire cumulé |
|---|---|---|
| 1 | 211 s | 0,45 Go |
| 2 | 213 s | 0,67 Go |
| 3 | 226 s | 1,0 Go |
| 2, pendant une émulation | 217 s | 1,0 Go |

**N recommandé : 3** (`places_tests` du serveur dans `serveurs.json`, aucun champ au bureau pour l'instant ; 2 par
défaut). Au-delà, le processeur est plein
(3 × 4 fils = 12 fils).

### Mémoire (`budget_tests_mo`, jalon J11)

`--mixte gradle:2,python:2` (MyFridgeCleaner, cache chaud ; suite MyIAFactory) : Gradle 136 s, Python 243 s, pic
**5,1 Go** ; pendant une émulation : 147 s, 245 s, **5,7 Go**. Le défaut (32 Go, 16 jetons de 2 Go) est confirmé.

### Durées de référence

| projet | commande | durée (bout en bout) |
|---|---|---|
| MyIAFactory | suite complète | 224–230 s (204 s au serveur) |
| MyFridgeCleaner | `./gradlew testDebugUnitTest`, cache froid (échauffement compris) | 266 s, pic 3,2 Go, cache 1,2 Go |
| MyFridgeCleaner | même, cache chaud (évaluation) | 83 s, pic 2,6 Go |
| Node (vitest) | `npx vitest run` : échauffement npm, puis cache | 29 s, puis 10–17 s |
| Python (pip, roues) | `python3 -m unittest discover` : échauffement, puis cache | 30 s, puis 9 s |
| sur-la-route | tests Python (`Tools/factory/tests`, 109 tests, instantané ~650 Mo) | 46 s |

### Images

`myiafactory/tests` : 3 min 10 s à construire ; `tests-android` : 116 s ; image dérivée Node : ~45 s, ~220 Mo propres ;
`myiafactory/tests-unity-6000.6.7f1` (sur l'image GameCI présente, aucun tirage) : 451 s.
