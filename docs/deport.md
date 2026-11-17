# Exécution déportée : confier les actions lourdes à GitHub

Compiler l'APK, lancer les tests ou les tests de charge ralentit le poste. Chaque action peut tourner **au poste** ou
**sur GitHub Actions** ; le résultat revient dans le bureau. Conception : [docs/superpowers/specs/2026-11-17-execution-deportee-design.md](superpowers/specs/2026-11-17-execution-deportee-design.md).

## Le principe

- **Par défaut, tout reste au poste.** Rien ne change tant que le Directeur ne coche rien : ni consigne d'agent
  supplémentaire, ni appel à GitHub.
- **Un lieu par action** : `poste` ou `github`. `serveur` est affiché grisé (« bientôt »).
- Le réglage est global (clé `deport` de `~/MyIAFactory/bureau.json`) avec **surcharge par projet** (clé `deport` des
  réglages du projet, comme `lecons_auto`). Le projet l'emporte, puis le défaut global, puis le poste.
- Jamais de bascule silencieuse : si GitHub est injoignable ou le quota atteint, l'action s'arrête et propose le poste ;
  `--poste` ne se lance qu'avec l'accord du Directeur.

## Les actions selon le type de projet

Le catalogue vient du genre du projet (`genre` dans `.factory/factory.json`). Genre absent ou inconnu : catalogue générique.

| Type | Actions (libellé, commande par défaut) | Lieux |
|---|---|---|
| Générique | `apk` (APK), `tests` (Tests), `emulateur` (Émulateur), `charge` (Charge), sans commande par défaut : le Directeur la fournit | poste, GitHub ; l'émulateur : poste seulement |
| `application-mobile-android` (Gradle natif) | `apk` « Générer l'APK » (`./gradlew assembleDebug`), `tests` « Tests unitaires » (`./gradlew testDebugUnitTest`), `lint` « Analyse lint » (`./gradlew lintDebug`) | poste, GitHub |
| | `emulateur` « Tests sur émulateur » (`./gradlew connectedDebugAndroidTest`), `release` « APK signé (release) » (`./gradlew assembleRelease`) | **poste seulement** |

Ce qui n'est pas proposé, et pourquoi :

- **Émulateur sur GitHub** : peu fiable ; au poste (ou, plus tard, sur serveur).
- **`release` sur GitHub** : il faudrait les clés de signature dans les secrets GitHub, que seul le Directeur saisit. La
  signature en CI n'est pas faite : la release reste au poste.
- **`charge` pour Android** : une application sans serveur n'a pas de test de charge ; demander cette action est refusé
  (« n'existe pas pour ce type de projet »).

**Dépendances.** Une action peut consommer la production d'une autre. Dans le catalogue générique, `tests`, `emulateur`
et `charge` consomment l'APK. Dans le catalogue Android, les tests unitaires se compilent depuis les sources : ils
**n'attendent pas** l'APK.

## Les cases dans le bureau

Dans les réglages du projet, le bloc « Où tournent les actions » montre une rangée par action du type du projet, avec
le choix Poste / GitHub / Serveur (grisé « bientôt »). Un lieu que l'action n'offre pas est grisé avec son explication.
Une combinaison qui impose une attente est signalée (« les tests au poste attendront l'APK de GitHub… ») avec la
suggestion de mettre la chaîne entière au même lieu. Dès qu'une action est sur GitHub, le bloc propose l'aperçu du
workflow et affiche la consommation du mois.

## Valider le workflow

1. **Aperçu du workflow** : le bureau génère `.github/workflows/<projet>.yml` (Linux seulement) et affiche son état
   (absent, à valider, à jour, modifié à la main) et son diff. Rien n'est écrit ni poussé.
2. **Valider et pousser** : le workflow est envoyé **seulement sur la branche `deport/workflow`**, depuis un dossier de
   travail temporaire. La branche courante et le dossier du projet ne sont jamais touchés. Rien n'est poussé sans ce clic ;
   un aperçu périmé (réglages changés depuis) est refusé. Un fichier modifié à la main n'est jamais écrasé.
3. **Étape manuelle obligatoire : fusionner `deport/workflow` dans la branche de travail** (et la pousser). GitHub ne
   déclenche un workflow que s'il existe sur la branche visée ; sans cette fusion, `lancer.py deporter` s'arrête avec le
   code 7.
4. **Les secrets** (clés de signature, jetons) : à saisir par le Directeur lui-même dans GitHub (Settings, Secrets and
   variables, Actions). L'application ne les voit ni ne les demande jamais.

Déclencheurs du workflow : push, bouton manuel (`workflow_dispatch`), et, pour `charge`, une planification (03:00 UTC
par défaut, réglable).

## `lancer.py deporter`

```
python lancer.py deporter <type> [--dossier <d>] [--reglages <fichier>] [--sans-attendre] [--poste] [-- <commande locale>]
```

Au poste, la commande locale (après `--`) part par le lanceur de tests (verrou du poste). Sur GitHub, l'exécution du
**commit courant** est déclenchée (ou réutilisée si un autre appelant l'a déjà lancée ou réussie) et suivie ;
`lancer.py tests` passe tout seul par `deporter` quand ses tests sont sur GitHub ou attendent une production d'ailleurs.
Les agents reçoivent la commande exacte dans leur message de départ.

| Code | Sens |
|---|---|
| 0 | réussi |
| 1 | l'action a échoué |
| 2 | usage faux, action inconnue ou lieu refusé |
| 3 | refusé à cause de `--sans-attendre` |
| 4 | `gh` indisponible, non connecté ou réseau absent |
| 5 | l'action dont dépend celle-ci a échoué : elle n'est pas lancée |
| 6 | travail non poussé : `origin/<branche>` n'est pas au commit courant (`deporter` ne pousse jamais le travail de l'agent) |
| 7 | le workflow n'est pas dans la branche : fusionner `deport/workflow` |

## Dépendances et attente visible

Si une action au poste consomme la production d'une action sur GitHub (tests au poste, APK sur GitHub), `deporter`
attend la fin de l'exécution distante, télécharge l'artefact (`gh run download`, dans `<dossier>/artefacts/`) puis lance
la commande locale. Si l'amont échoue : code 5, sans retenter en boucle. L'APK n'est produit qu'une fois par commit.

Pendant l'attente, un fichier `~/MyIAFactory/deport-en-cours/<id>.json` dit quel agent attend quoi ; la fiche affiche
« en attente de l'APK (GitHub, depuis N min) » et le garde-fou « sans action » n'arrête pas l'agent. Le fichier est
retiré à la fin, même en cas d'erreur. La protection est **plafonnée à 6 h** d'attente continue ; au-delà, le garde-fou
s'applique de nouveau.

## La consommation

La vue des coûts, dans le bloc du projet, cumule par mois et par action les minutes GitHub (un job est facturé à la
minute entamée). Un dépôt public est illimité. Pour un dépôt privé :

- **alerte à 80 %** du quota ; **à 100 %**, proposition de passer au poste, avec l'accord du Directeur (jamais de
  blocage ni de bascule automatiques) ;
- le quota officiel n'est lu que si le Directeur accorde l'autorisation `user` à `gh`, en lançant lui-même
  `gh auth refresh -h github.com -s user` ; sans elle, c'est une estimation par les durées. L'application ne change
  jamais les droits de `gh`.

Lecture en arrière-plan, au plus toutes les 5 minutes, cache dans `~/MyIAFactory/deport-conso.json`.

## Pas encore fait

- Le lieu `serveur` (exécution par SSH avec le même verrou de campagne) : grisé « bientôt ».
- La bibliothèque globale d'actions : les catalogues générique et Android sont les premiers ; un nouveau genre n'en
  reçoit pas encore automatiquement.
- Les catalogues des autres genres (aujourd'hui : générique et `application-mobile-android`).
- La signature de l'APK en CI (clés dans les secrets GitHub).
- Windows et macOS côté GitHub (facturés plus cher) ; déport automatique selon la charge du poste.
