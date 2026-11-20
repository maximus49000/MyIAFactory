# Exécution déportée : confier les actions lourdes à GitHub

Compiler l'APK, lancer les tests ou les tests de charge ralentit le poste. Chaque action peut tourner **au poste** ou
**sur GitHub Actions** ; le résultat revient dans le bureau. Conception : [docs/superpowers/specs/2026-11-17-execution-deportee-design.md](superpowers/specs/2026-11-17-execution-deportee-design.md).

## Le principe

- **Par défaut, tout reste au poste.** Rien ne change tant que le Directeur ne coche rien : ni consigne d'agent
  supplémentaire, ni appel à GitHub.
- **Un lieu par action** : `poste` ou `github`. `serveur` est affiché grisé (« bientôt »), **sauf pour la recette sur émulateur**
  (voir plus bas), qui ne tourne que sur le serveur.
- Le réglage est global (clé `deport` de `~/MyIAFactory/bureau.json`) avec **surcharge par projet** (clé `deport` des
  réglages du projet, comme `lecons_auto`). Le projet l'emporte, puis le défaut global, puis le poste.
- Jamais de bascule silencieuse : si GitHub est injoignable (code 4) ou le quota épuisé (code 8), `deporter` s'arrête
  et propose le poste ; `--poste` ne se lance qu'avec l'accord du Directeur.

## Les actions selon le type de projet

Le catalogue vient du genre du projet (`genre` dans `.factory/factory.json`). Genre absent ou inconnu : catalogue générique.

| Type | Actions (libellé, commande par défaut) | Lieux |
|---|---|---|
| Générique | `apk` (APK), `tests` (Tests), `emulateur` (Émulateur), `charge` (Charge), sans commande par défaut : le Directeur la fournit | poste, GitHub ; l'émulateur : poste seulement |
| `application-mobile-android` (Gradle natif) | `apk` « Générer l'APK » (`./gradlew assembleDebug`), `tests` « Tests unitaires » (`./gradlew testDebugUnitTest`), `lint` « Analyse lint » (`./gradlew lintDebug`) | poste, GitHub |
| | `emulateur` « Tests sur émulateur » (`./gradlew connectedDebugAndroidTest`), `release` « APK signé (release) » (`./gradlew assembleRelease`) | **poste seulement** |

**La recette sur émulateur** (`recette-emulateur`, libellé « Recette sur émulateur », présente dans le catalogue générique et dans
`application-mobile-android`) : l'APK est installé et joué sur un émulateur du **serveur** (voir [`serveur-taches.md`](serveur-taches.md)).
Elle est à part :

- **Serveur seulement** : ni poste ni GitHub, et **aucun lieu par défaut**. Non réglée, elle est refusée (code 2) ; `--poste` et
  `--sans-attendre` ne s'appliquent pas.
- **Réglée dans les réglages du projet seulement** : le défaut global du bureau ne compte jamais pour elle. Régler le lieu sur
  « serveur » vaut **accord permanent, pour ce projet**, de la lancer.
- **Projets enregistrés seulement** : le projet doit figurer dans le bureau (`bureau.json`) et le réglage être lu dans le fichier
  de réglages que le bureau enregistre pour lui ; `--reglages` n'est admis que s'il désigne ce fichier.
- Elle consomme l'APK mais **n'attend pas** une chaîne au même lieu : elle prend l'APK là où il est produit (aucun avertissement de
  chaîne pour elle).

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
Pour la **recette sur émulateur** la rangée ne propose que **« Serveur »** et **« Non réglé »** (le choix par défaut, qui vaut
refus) : « Serveur » est grisé avec « déclarez d'abord un serveur (Serveurs), puis réglez sur serveur » tant qu'aucun serveur n'est
déclaré, et une note rappelle que la régler sur serveur vaut accord permanent pour le projet (l'agent la lance sans redemander).
Une combinaison qui impose une attente est signalée (« les tests au poste attendront l'APK de GitHub… ») avec la
suggestion de mettre la chaîne entière au même lieu. Dès qu'une action est sur GitHub, le bloc propose l'aperçu du
workflow et affiche la consommation du mois.

## Valider le workflow

1. **Aperçu du workflow** : le bureau génère `.github/workflows/<projet>.yml` (Linux seulement) et affiche son état
   (absent, à valider, à jour, modifié à la main) et son diff. Rien n'est écrit ni poussé.
2. **Valider et pousser** : le workflow est envoyé **seulement sur la branche `deport/workflow`**, depuis un dossier de
   travail temporaire construit sur le **sommet distant** de la branche courante (son amont `@{u}`, sinon
   `origin/<branche>`), jamais sur le HEAD local : un commit local non poussé (travail d'un agent, fichier sensible)
   ne part jamais sur GitHub. L'aperçu annonce combien de commits locaux ne sont **pas** inclus ; une branche qui n'est
   pas sur le dépôt distant est refusée (« pousse ta branche d'abord »). La branche courante et le dossier du projet ne
   sont jamais touchés. Rien n'est poussé sans ce clic ; un aperçu périmé (réglages changés depuis) est refusé. Un
   fichier modifié à la main n'est jamais écrasé ; un workflow déjà à jour dans la branche locale n'est pas renvoyé.
3. **Étape manuelle obligatoire : fusionner `deport/workflow` dans la branche de travail** (et la pousser). GitHub ne
   déclenche un workflow que s'il existe sur la branche visée ; sans cette fusion, `lancer.py deporter` s'arrête avec le
   code 7. Pour le bouton manuel (`workflow_dispatch`), GitHub demande en plus que le fichier soit sur la **branche par
   défaut** du dépôt : fusionnez-le aussi dans `main` si vous travaillez sur une autre branche.
4. **Les secrets** (clés de signature, jetons) : à saisir par le Directeur lui-même dans GitHub (Settings, Secrets and
   variables, Actions). L'application ne les voit ni ne les demande jamais.

Déclencheurs du workflow : **pas de `push`** (un push suivi du déclenchement par l'agent donnait deux exécutions pour un
même commit). Seulement le bouton manuel (`workflow_dispatch`, utilisé par `lancer.py deporter`) et, si `charge` est
déportée, une planification (03:00 UTC par défaut, réglable) : la nuit, seuls `charge` et les jobs dont elle dépend
tournent (les autres portent `if: github.event_name != 'schedule'`). Un déclenchement manuel lance tous les jobs.
Les jobs `./gradlew …` reçoivent un JDK 17 (`actions/setup-java@v4`, temurin) et `chmod +x gradlew` (un dépôt créé
sous Windows enregistre `gradlew` sans le bit exécutable) ; `gradle/actions/setup-gradle@v4` met `~/.gradle` en
cache (le cache est propre au dépôt et n'est en lecture-écriture que sur la branche par défaut). Le SDK Android est celui préinstallé sur `ubuntu-latest`.

## `lancer.py deporter`

```
python lancer.py deporter <type> [--dossier <d>] [--reglages <fichier>] [--sans-attendre] [--poste] [-- <commande locale>]
python lancer.py deporter recette-emulateur [--mode scenario|pilote] [--scenario <nom>] [--apk <fichier>] [--dossier <d>] [--reglages <fichier>]
```

Au poste, la commande locale (après `--`) part par le lanceur de tests (verrou du poste). Sur GitHub, l'exécution du
**commit courant** est déclenchée, ou réutilisée si elle est en cours ou si les jobs **nécessaires** (celui de l'action
et ceux dont il dépend) y ont réussi : un job sans rapport en échec (ex. `lint`) ne fait pas refaire l'exécution.
`lancer.py tests` passe tout seul par `deporter` quand ses tests sont sur GitHub ou attendent une production d'ailleurs.
Les agents reçoivent la commande exacte dans leur message de départ.

- **Le projet** est le plus proche dossier (`--dossier` ou ses parents) qui contient `.factory/` : un agent peut donner
  un sous-dossier (`app/`) ; le catalogue, les lieux et le nom du workflow restent ceux du projet.
- **Le commit testé est celui qui est poussé** : `origin/<branche>` doit être au commit courant, et aucun fichier suivi
  ne doit être modifié sans commit (hors `.factory/`, que le moteur réécrit sans cesse) ; sinon code 6, avec la liste
  des fichiers. `deporter` ne pousse jamais le travail de l'agent.
- **Une seule relance par commit** : un job nécessaire en échec n'est relancé qu'une fois par (commit, job) (marqueur
  `<commit>-<workflow>-<job>.relance` dans `~/MyIAFactory/deport-en-cours/`) ; ensuite `deporter` rend 1 (ou 5 pour un
  amont) avec « déjà relancé une fois pour ce commit : corrige le code », sans redéclencher.
- **Quota** : avant de déclencher, `deporter` lit la dernière consommation en cache (sans appeler `gh`) ; niveau
  « dépassé » : code 8. Une exécution en `startup_failure` (refusée au démarrage, le plus souvent faute de minutes)
  donne aussi 8, « quota probablement épuisé ». Une exécution déjà réussie reste réutilisable.
- **Suivi** : au plus 1 h ; au-delà, « délai dépassé, l'exécution tourne peut-être encore » (code 1 ; relancer plus
  tard la retrouve et la suit, sans la refaire).

| Code | Sens |
|---|---|
| 0 | réussi |
| 1 | l'action a échoué |
| 2 | usage faux, action inconnue ou lieu refusé |
| 3 | refusé à cause de `--sans-attendre` |
| 4 | `gh` indisponible, non connecté ou réseau absent |
| 5 | l'action dont dépend celle-ci a échoué : elle n'est pas lancée |
| 6 | travail non poussé (`origin/<branche>` n'est pas au commit courant) ou fichiers suivis modifiés non commités (hors `.factory/`) |
| 7 | le workflow n'est pas dans la branche (ou GitHub ne le trouve pas : il doit aussi être sur la branche par défaut) : fusionner `deport/workflow` |
| 8 | quota GitHub épuisé (cache au niveau « dépassé », ou exécution en `startup_failure`) : proposer le poste au Directeur |

Pour `recette-emulateur` : **0 seulement si le statut du rapport est `ok`** (pas de plantage, pas de limite atteinte, pas d'erreur),
1 en cas d'échec, 2 pour un usage faux, un accord absent ou **aucun APK trouvé** (ni `--apk`, ni production `apk` du projet), et
**4** quand Python 3.12 est introuvable (le lanceur de tâches l'exige ; `deporter` lui-même reste compatible 3.9). Tout le détail
(recettes, pilote, rapatriement dans `<projet>/.factory/serveur/<id>/`, limites) est dans [`serveur-taches.md`](serveur-taches.md).
## Dépendances et attente visible

Si une action au poste consomme la production d'une action sur GitHub (tests au poste, APK sur GitHub), `deporter`
attend la fin de l'exécution distante, télécharge l'artefact (`gh run download`) dans
`~/MyIAFactory/artefacts/<commit>/<produit>` (hors du projet : jamais commité par un `git add -A`), puis lance la
commande locale avec le chemin du fichier dans la variable `MYIAFACTORY_ARTEFACT_<PRODUIT>` (ex.
`MYIAFACTORY_ARTEFACT_APK`). Un artefact déjà téléchargé pour ce commit est réutilisé. L'APK d'un commit n'est produit
qu'une fois tant que son job réussit ; s'il échoue, il est relancé une seule fois, puis code 5 sans nouvel essai.

Pendant l'attente, un fichier `~/MyIAFactory/deport-en-cours/<id>.json` dit quel agent attend quoi ; la fiche affiche
« en attente de l'APK (GitHub, depuis N min) » et le garde-fou « sans action » n'arrête pas l'agent. L'agent est
reconnu par sa clé : le moteur l'exporte dans `MYIAFACTORY_AGENT` au lancement et `deporter` l'écrit dans le fichier
(`agent`). Les autres agents du même dossier ne sont donc ni protégés ni étiquetés ; sans clé (appel à la main), le
dossier sert. Le fichier est
retiré à la fin, même en cas d'erreur. La protection est **plafonnée à 6 h** d'attente continue ; au-delà, le garde-fou
s'applique de nouveau.

## La consommation

Le bloc « Où tournent les actions » des réglages du projet (pas la vue des coûts) cumule par mois et par action les
minutes GitHub (un job est facturé à la minute entamée) et montre les derniers résultats. Un dépôt public est illimité. Pour un dépôt privé :

- **alerte à 80 %** du quota ; **à 100 %**, proposition de passer au poste, avec l'accord du Directeur, et
  `deporter` refuse de déclencher (code 8) ; jamais de bascule automatique vers le poste ;
- le quota officiel n'est lu que si le Directeur accorde l'autorisation `user` à `gh`, en lançant lui-même
  `gh auth refresh -h github.com -s user` ; sans elle, c'est une estimation par les durées. L'application ne change
  jamais les droits de `gh`.

Lecture en arrière-plan, au plus toutes les 5 minutes, cache dans `~/MyIAFactory/deport-conso.json` (relu par
`deporter` avant chaque déclenchement). Sans l'autorisation `user`, le quota officiel est inconnu : le niveau
« dépassé » ne peut pas être vu d'avance, et c'est l'exécution en `startup_failure` qui donne le code 8.

## Variables d'environnement

| Variable | Posée par | Sens |
|---|---|---|
| `MYIAFACTORY_AGENT` | le moteur, au lancement d'un agent détaché | la clé de l'agent ; `deporter` l'écrit dans le fichier d'attente |
| `MYIAFACTORY_ARTEFACT_<PRODUIT>` | `deporter`, pour la commande locale | le chemin de l'artefact téléchargé (ex. `MYIAFACTORY_ARTEFACT_APK`) |

## Pas encore fait

- Le lieu `serveur` pour les autres actions (exécution par SSH avec le même verrou de campagne) : grisé « bientôt ». Seule la
  recette sur émulateur tourne déjà sur le serveur (jamais encore essayée sur un vrai serveur).
- La bibliothèque globale d'actions : les catalogues générique et Android sont les premiers ; un nouveau genre n'en
  reçoit pas encore automatiquement.
- Les catalogues des autres genres (aujourd'hui : générique et `application-mobile-android`).
- La signature de l'APK en CI (clés dans les secrets GitHub).
- Windows et macOS côté GitHub (facturés plus cher) ; déport automatique selon la charge du poste.
