# Les tâches sur le serveur (tranche A : l'émulateur Android)

Un agent (ou vous) peut faire installer et jouer l'APK d'un projet sur un **émulateur Android qui tourne sur le serveur**,
sans charger le poste : les captures d'écran, le journal et un rapport reviennent dans le projet. Cette première tranche ne
fait que cela (une tâche de type « émulation ») ; l'agent qui travaille *sur* le serveur est la tranche B (voir « Suite »).
Conception : [`2026-11-19-agents-serveur-design.md`](superpowers/specs/2026-11-19-agents-serveur-design.md). Le serveur lui-même
(déclaration, capacités, installation) : [`serveur.md`](serveur.md).

> **Rien de tout cela n'a encore tourné sur un vrai serveur.** Tous les essais passent par de faux SSH et de faux dossiers ;
> la liste exacte de ce qui n'a pas été exécuté est dans « Ce qui n'a PAS été exécuté sur un vrai serveur ». Le premier essai
> réel est prévu avec l'accord explicite du Directeur, jamais avant.

## Les deux modes

| Mode | Qui conduit l'émulateur | Comment | Fin de la tâche |
|---|---|---|---|
| `scenario` | une **recette** (fichier JSON du projet), déroulée par le lanceur | une seule commande, `deporter recette-emulateur --scenario <nom>` (ou `serveur-tache lancer ... --attendre`) | le lanceur finit toujours par `journal` puis `arreter` du pont, rapatrie et imprime le rapport |
| `pilote` | **un agent**, verbe par verbe | `serveur-tache lancer --mode pilote` rend un identifiant, puis `serveur-outil <id> <verbe> ...` autant de fois que voulu | l'agent termine par `serveur-tache arreter <id>` puis `serveur-tache rapatrier <id>` ; sinon l'inactivité ou la durée maximale l'arrêtent |

Dans les deux cas l'agent n'a jamais de shell sur le serveur : il n'a que la **liste fermée de verbes** du pont (plus bas).

## Où se trouve quoi

Sur le serveur (tout sous l'utilisateur déclaré, jamais root) :

```
~/taches/.creneau-emulation          le verrou du créneau (flock) : une seule émulation à la fois
~/taches/<id>/
    demande.json                     la demande validée (projet, mode, scénario, limites, nom de l'APK)
    entree/app.apk                   l'APK envoyé (monté en lecture seule dans le conteneur)
    sortie/                          ce que le conteneur écrit (monté en écriture) : pont.log, captures/, plantage.txt,
                                     entree-tache.log, emulateur.log, .activite, .avd-pret, .paquet, emulateur.pid
    etat.json                        l'état de la tâche (écrit par l'enveloppe, atomiquement) : la vérité
    arret                            créé par le lanceur pour demander l'arrêt (contenu « arret » ou « fin »)
    enveloppe.pid, veilleur.pid      les deux processus de l'hôte (voir plus bas)
    veilleur.log, docker-run.log     journaux de l'hôte (jamais rapatriés)
~/myiafactory/serveur_ovh/...        les fichiers du dépôt déposés sur le serveur : images/emulateur/{Dockerfile,entree-tache.sh},
                                     taches/{pont.sh,lancer_emulation.sh}, versions.json (dossier `$HOME/myiafactory`, en minuscules)
~/.myiafactory/emulateur-image.version    le marqueur de l'image (voir « Maintenance »)
~/android-sdk                        le SDK Android de l'hôte, monté en lecture seule dans le conteneur
```

Sur le poste (`~/MyIAFactory`, avec majuscules) : `taches.json` (l'**index** des tâches, un simple cache : la vérité est sur le
serveur ; plafonné à 8 Mo en lecture) et son verrou `taches.lock`. Les résultats rapatriés vont dans le **projet** :
`<projet>/.factory/serveur/<id>/` (journaux, `captures/<nom>.png`, `rapport.json`). **Ajoutez `.factory/serveur/` à
`.gitignore` du projet** : ce sont des résultats d'essai, pas du code.

L'identifiant d'une tâche a la forme `t<AAAAMMJJ>-<HHMMSS>-<4 hexadécimaux>` (heure UTC).

## L'état d'une tâche : `etat.json`

Écrit par `lancer_emulation.sh` (temporaire puis `mv` : jamais à moitié écrit), relu par le lanceur :

```json
{"id": "t20261120-101500-a1b2", "etat": "terminee", "statut": "ok", "debut": "2026-11-20T10:15:03Z",
 "fin": "2026-11-20T10:17:41Z", "raison": "Fin demandée par le lanceur (arret : fin)."}
```

`etat` dit où en est la tâche, `statut` (renseigné à la fin seulement, sinon `null`) dit comment elle s'est passée.

| `etat` | `statut` | Ce que cela veut dire |
|---|---|---|
| `en_attente` | `null` | jamais démarrée : le créneau est occupé ; elle peut être relancée avec le même identifiant |
| `en_cours` | `null` | le conteneur tourne, un veilleur le surveille |
| `terminee` | `ok` | fin normale d'un scénario (le lanceur a demandé `fin`) |
| `terminee` | `limite` | durée maximale atteinte, inactivité du pilote, ou sortie trop volumineuse |
| `terminee` | `plantage` | l'application a planté (`plantage.txt` existe) : le plantage **prime** sur `ok` et `limite` |
| `arretee` | `ok` (ou `plantage`) | arrêt demandé (par vous, le bureau ou un agent), ou tâche arrêtée avant d'avoir démarré |
| `echouee` | `erreur` | le conteneur a disparu seul, Docker ne répond plus, le démarrage a échoué, le veilleur est mort ou a été interrompu |

**Pour le code de sortie** des commandes qui rapatrient (`rapatrier`, `lancer --attendre`, `deporter recette-emulateur`) : **0
seulement si le statut du rapport est `ok`**. Le rapport (`rapport.json`) recalcule le statut à l'arrivée : un conteneur
qui n'est pas dans un état final, un état `echouee`, une archive suspecte ou abîmée donnent `erreur` ; une limite atteinte,
une sortie tronquée ou un échec de recette par le code 3 du pont donnent `limite` ; un plantage donne `plantage`.
`serveur-tache etat` et `arreter`, eux, rendent 0 tant que l'état est lisible (1 si l'état est « inconnu » : serveur
injoignable, identifiant inconnu, état illisible).

## Le créneau : une émulation à la fois

- Le serveur ne fait tourner **qu'un seul émulateur**. L'enveloppe prend un verrou `flock` sur `~/taches/.creneau-emulation`
  (et refuse aussi si un conteneur `tache-*` existe déjà, par exemple d'un veilleur mort).
- Créneau occupé : l'enveloppe écrit `en_attente` et rend le code 75. Le lanceur **réessaie avec le même identifiant toutes les
  15 s, pendant 600 s au plus** ; au-delà il abandonne (APK retiré du serveur, état `en_attente`, message « Créneau d'émulation
  toujours occupé... », code de sortie 1).
- Un **arrêt pendant l'attente** est honoré : `arreter` écrit l'état `arretee` (APK retiré), l'enveloppe relit cet état final
  sous le créneau et ne démarre jamais ; le lanceur voit `arretee` et sort sans erreur de démarrage.
- Un veilleur **détaché** (il survit à la fin de la session SSH) tient le créneau pendant toute la tâche : si l'appelant meurt,
  l'échéance de durée arrête quand même le conteneur et libère le créneau.

## Les limites (valeurs par défaut lues dans le code)

Les commandes n'offrent pas encore de réglage : une tâche lancée par `serveur-tache` ou `deporter` a toujours les valeurs
par défaut ci-dessous. Les bornes « réglable » ne valent que pour une demande construite par le code (`Demande.limites`) ; une
limite ne peut jamais dépasser son défaut.

| Limite | Valeur | Où elle est appliquée |
|---|---|---|
| Durée maximale | **1200 s** (20 min) ; réglable de 1 à 1200 | veilleur ; en dernier recours le conteneur s'arrête seul à `durée + 60 s` |
| Inactivité (mode pilote) | **600 s** (10 min) ; une demande de pilote accepte **300 à 600** | veilleur : dernier verbe du pont (`pont.log`, `.activite` touché au début et à la fin de chaque verbe), AVD prêt, ou début de la tâche |
| Captures | **50** ; réglable de 1 à 50 | pont (code 3) et lanceur |
| Octets de captures | **100 Mo** (104 857 600) ; réglable de 1 à cette valeur ; les journaux ne comptent pas | pont (code 3) |
| Taille de `sortie/` | **256 000 Ko** (`du -sk`, sondé toutes les 5 s) ; au-delà : arrêt, `limite` | veilleur ; ce n'est pas un quota, un dépassement entre deux sondages est accepté |
| APK | **200 Mo** au plus, fichier ordinaire non vide commençant par la signature ZIP (`PK 03 04`) | lanceur, avant tout envoi |
| Mémoire du conteneur | **6144 Mo** (swap identique : pas de swap) | `docker run` |
| Processeurs | **2** | `docker run` |
| Processus du conteneur | **512** ; 4096 fichiers ouverts | `docker run` |
| Réseau | **aucun** (`--network none`) | `docker run` |
| Chaque journal rapatrié | 5 Mo au plus (au-delà il n'est pas rapatrié) | serveur et poste |

**Pourquoi 10 minutes d'inactivité et non 5 (décision R9).** La conception disait 5 minutes. Mais le pont accorde jusqu'à 300 s
au démarrage de l'émulateur (`demarrer`) : avec 300 s d'inactivité, un démarrage lent aurait été pris pour de l'inactivité.
Le défaut est donc 600 s et une demande de pilote ne peut pas descendre sous 300 s (ni dépasser 600 s).

Le lanceur passe à l'enveloppe les limites de la demande : durée, inactivité, mémoire, processeurs, captures et octets
(`lancer_emulation.sh <id> <mode> <duree_s> <inactivite_s> <memoire_mo> <cpus> <captures> <octets>`). L'enveloppe les revalide
(durée et inactivité 1 à 86400, mémoire 256 à 65536, processeurs 1 à 64, captures 1 à 50, octets 1 à 104 857 600) : un
lanceur modifié ne peut pas la tromper.

## Les verbes du pont

Le conteneur n'accepte **que** ces verbes, par `pont <verbe> [arguments]` (copie exacte de la table de `pont.sh`, dont
`outils/serveur_tache.py` garde le miroir `VERBES` ; un test fait passer les mêmes exemples par les deux) :

| Verbe | Arguments | Effet |
|---|---|---|
| `demarrer` | aucun | démarre l'émulateur et attend la fin du démarrage (300 s au plus) ; un second `demarrer` alors qu'il tourne : code 2 |
| `installer` | aucun | installe `entree/app.apk` (chemin fixe) et relève le nom du paquet |
| `lancer` | aucun | lance l'application installée |
| `toucher` | `x y` : deux entiers de 0 à 9999 | un appui |
| `glisser` | `x1 y1 x2 y2` : quatre entiers de 0 à 9999 | un glissement |
| `texte` | un texte : 1 à 60 caractères, commence par une lettre ou un chiffre, puis lettres, chiffres, espace, `.` `,` `_` `-` | saisit du texte (les espaces sont transmis en `%s`) |
| `touche` | `retour`, `accueil` ou `menu` | une touche |
| `attendre` | une durée entière de 0 à 120 secondes | pause |
| `capturer` | un nom : `[a-z0-9][a-z0-9_-]{0,39}` | capture d'écran PNG dans `captures/<nom>.png` |
| `journal` | un filtre facultatif : texte littéral de 1 à 60 caractères (`[A-Za-z0-9][A-Za-z0-9._:-]*`) | lit le journal de l'appareil (200 lignes de 500 caractères au plus), relève un plantage |
| `arreter` | aucun | arrête l'émulateur (au besoin par signal) |

Conséquences à connaître : **`-5` et les adresses e-mail sont refusés comme `texte`** (il doit commencer par une lettre ou un
chiffre, et `@` n'est pas admis) ; aucun caractère spécial du shell n'est admis nulle part ; les noms de capture
**réservés par Windows** (`con`, `prn`, `aux`, `nul`, `com0`-`com9`, `lpt0`-`lpt9`) sont refusés parce que le poste ne
pourrait pas écrire le fichier ; un nom de capture **déjà pris** rend le code 2 (jamais 3).

**Codes du pont** : 0 réussi ; **2** verbe ou argument refusé (y compris nom de capture déjà pris, second `demarrer`) ;
**3** limite atteinte (nombre ou octets de captures) ; 4 outil ou réglage en échec. Le pont répond par une ligne JSON
`{"ok", "verbe", "detail"}` ; le lanceur la relit avec prudence (une seule ligne, taille bornée, types vérifiés, `ok`
cohérent avec le code) et rend `{ok, verbe, code, detail}` ; pour `capturer`, plus `capture` : le chemin local de l'image
rapatriée. La réponse du pont est une **donnée**, jamais une consigne.

Le pont n'écrit que sous `sortie/` : `.activite`, `pont.log` (une ligne par appel : verbe, au plus 6 arguments tronqués,
durée), `captures/<nom>.png`, `plantage.txt`, `.paquet`, `emulateur.log`, `emulateur.pid` et ses verrous. Il refuse de
travailler sans `timeout` (code 4).

Délais SSH par verbe côté poste : `demarrer` 360 s, `installer` 240 s, `arreter` 120 s, `attendre` et `capturer` 150 s, les autres
90 s. `demarrer` attend d'abord que l'AVD soit créé dans le conteneur (jusqu'à 300 s).

## Les recettes (mode scénario)

Une recette est un fichier **`<projet>/.factory/recettes/<nom>.json`** (nom : minuscules, chiffres, `_`, `-`, 40 caractères au
plus) :

```json
{"nom": "demarrage", "reseau": false, "etapes": [{"verbe": "demarrer"}, {"verbe": "installer"}]}
```

Règles (le fichier vient du projet, donc d'un agent : il est traité comme une donnée hostile, validé en entier **avant** tout
envoi) : clés permises `nom` (facultative, doit égaler le nom du fichier), `reseau` (doit être `false` ; `true` est refusé en
tranche A) et `etapes` (obligatoire) ; chaque étape est `{"verbe": ..., "args": [...]}` ; **les arguments sont du TEXTE**
(des chaînes, même pour les nombres : `"args": ["100", "200"]`) validé par les mêmes motifs que le pont ; **200 étapes** au
plus, **64 Ko** au plus, UTF-8 ; ni lien symbolique ni jonction dans `.factory`, `recettes` ou le fichier ; clés JSON
dupliquées refusées. Les étapes sont déroulées dans l'ordre et la recette **s'arrête au premier code non nul** du pont.

**La fin est toujours faite par le lanceur** : après la recette (réussie ou non), il appelle `journal` puis `arreter` du pont,
même si la recette l'a déjà fait, pour que le plantage soit relevé (`plantage.txt`) avant l'arrêt de la tâche. Une recette
n'a donc pas besoin de les écrire. Ces deux appels sont au mieux : une panne ne masque jamais le résultat de la recette.

Exemple de recette, **donné en exemple seulement (il n'est créé dans aucun projet)**, pour MyFridgeCleaner :
`.factory/recettes/demarrage.json`

```json
{
  "nom": "demarrage",
  "reseau": false,
  "etapes": [
    {"verbe": "demarrer"},
    {"verbe": "installer"},
    {"verbe": "lancer"},
    {"verbe": "attendre", "args": ["10"]},
    {"verbe": "capturer", "args": ["accueil"]},
    {"verbe": "touche", "args": ["menu"]},
    {"verbe": "attendre", "args": ["2"]},
    {"verbe": "capturer", "args": ["menu"]}
  ]
}
```

## Les commandes

Toutes sous Python 3.12 : `py -3.12 lancer.py ...`. Les sorties sont en JSON, **masquées** (clés OVH, licence, chemins de
clés) et ne montrent jamais de trace d'exception (le type seulement).

### `serveur-tache`

```
py -3.12 lancer.py serveur-tache lancer --apk <fichier> --mode scenario|pilote [--scenario <nom>] [--projet <dossier>] [--attendre] [--dossier <d>]
py -3.12 lancer.py serveur-tache etat <id> [--dossier <d>]
py -3.12 lancer.py serveur-tache arreter <id> [--dossier <d>]
py -3.12 lancer.py serveur-tache rapatrier <id> [--destination <dossier>] [--projet <dossier>] [--dossier <d>]
py -3.12 lancer.py serveur-tache lister [--dossier <d>]
```

`--dossier` change le dossier de configuration (par défaut `~/MyIAFactory`, ou la variable `MYIAFACTORY_PLATEFORME`).
`--projet` vaut le dossier courant s'il est absent.

| Commande | Effet | Codes de sortie |
|---|---|---|
| `lancer` (scénario) | exige `--scenario` **et `--attendre`** ; charge la recette (refusée avant tout envoi : un nom mal écrit ne prend jamais le créneau), envoie, déroule, finit par le pont, arrête, rapatrie dans `<projet>/.factory/serveur/<id>/` et imprime le rapport | 0 seulement si le statut est `ok` et la recette sans échec ; 1 sinon ; 2 usage ou accord refusé |
| `lancer` (pilote) | envoie et démarre, imprime l'identifiant et le mode d'emploi ; `--attendre` est refusé | 0 tâche démarrée ; 1 non démarrée ; 2 usage ou accord refusé |
| `etat <id>` | relit l'état sur le serveur (SSH) et met l'index à jour ; une tâche `en_cours` dont **ni le veilleur ni l'enveloppe ne vivent** (veilleur mort ou jamais né depuis plus de 180 s) est nettoyée (conteneur supprimé) et devient `echouee` | 0 ; 1 si « inconnu » |
| `arreter <id>` | `en_cours` : écrit `arret` et attend l'état final (30 s au plus) ; jamais démarrée : retire l'APK et écrit `arretee` ; puis `docker stop` dans tous les cas ; idempotent ; rappelé jusqu'à 3 fois tant que l'état n'est pas final | 0 ; 1 si « inconnu » |
| `rapatrier <id>` | copie `sortie/` dans la destination, écrit `rapport.json` | 0 seulement si le statut est `ok` ; 1 sinon |
| `lister` | les tâches de l'index local (sans connexion) | 0 |

Ordre des contrôles de `lancer` : usage, **accord du Directeur** (voir plus bas, avant même de lire l'APK), APK, recette,
demande, puis l'envoi. Une interruption (Ctrl-C) ou une panne **pendant** le lancement imprime l'identifiant et arrête la tâche
au mieux (le message dit si l'arrêt est confirmé) ; code 1.

Avant tout envoi, le lanceur refuse si : aucun serveur déclaré, joignable à la dernière sonde, avec les capacités
`android-emulateur` et `emulateur-image` (il en choisit le premier) ; l'**image de l'émulateur du serveur est périmée** (voir
« Maintenance ») ; l'APK est absent, vide, trop gros, ou n'est pas un APK.

### `serveur-outil` (le pilote)

```
py -3.12 lancer.py serveur-outil <id> <verbe> [arguments] [--projet <dossier>] [--dossier <d>]
```

Relaie **un** verbe au pont du conteneur (`sudo -n docker exec tache-<id> /usr/local/bin/pont <verbe> ...`, sans aucune
variable d'environnement de l'appelant) après validation locale ; imprime la réponse sur une ligne JSON. Codes : **0** le
pont a répondu `ok` ; **1** refus (verbe hors de la liste fermée, mauvais nombre d'arguments, argument non permis, nom de
capture déjà pris, limite atteinte, échec du pont, serveur injoignable) ; **2** usage (identifiant mal formé, arguments
manquants, option sans valeur). Pour `capturer`, la capture est rapatriée dans `<projet>/.factory/serveur/<id>/captures/`.

**Usage d'un pilote** : `serveur-tache lancer --apk <fichier> --mode pilote` → noter l'identifiant → `serveur-outil <id>
demarrer`, `installer`, `lancer`, `capturer`, ... → `serveur-tache arreter <id>` → `serveur-tache rapatrier <id>`.
Le lanceur applique lui-même la limite de captures de la demande (chaque `capturer` réserve une place dans l'index ;
au-delà : code 3 sans rien envoyer).

### `deporter recette-emulateur` (la commande à connaître pour un agent)

```
python lancer.py deporter recette-emulateur [--mode scenario|pilote] [--scenario <nom>] [--apk <fichier>] [--dossier <d>] [--reglages <fichier>]
```

C'est la porte des agents : elle donne le lieu **serveur**, vérifie l'accord, trouve l'APK (`--apk`, sinon la production `apk`
du projet : artefact GitHub du commit, ou la sortie locale la plus récente ; aucun APK : code 2) et lance `serveur-tache
lancer`. Mode par défaut : scénario (alors `--scenario` est exigé). `--poste` et `--sans-attendre` ne s'appliquent pas
(code 2) : jamais de repli sur le poste ni sur GitHub. Codes : **0 seulement pour le statut `ok`**, 1 échec (plantage,
limite, erreur, serveur injoignable), 2 refus d'usage ou d'accord ou aucun APK, **4 Python 3.12 introuvable**.

**Python 3.9 / 3.12.** `deporter` reste compatible Python 3.9 (les agents le lancent avec n'importe quel Python). Sous 3.12 ou
plus, il appelle le lanceur de tâches dans le même processus ; sous un Python plus ancien, il cherche un Python 3.12 à des
endroits fixes et sûrs (le lanceur `py.exe` de Windows, ou `python3.12` dans un dossier absolu du PATH ; jamais le dossier
courant) et le lance avec `-E -s`. Aucun : code 4 et le message dit d'installer Python 3.12.

## L'accord du Directeur (décision R10)

Régler le lieu de l'action sur **serveur** vaut **accord permanent, pour ce projet** : l'agent la lance ensuite sans
redemander. Concrètement, la commande n'obéit que si :

1. le projet est **enregistré** dans le bureau (`~/MyIAFactory/bureau.json`, liste `projets`), et
2. les **réglages enregistrés** de ce projet disent `deport.lieux.recette-emulateur = "serveur"`.

Ni le défaut du bureau, ni un dossier non enregistré, ni un autre fichier donné par `--reglages` ne comptent ; sans réglage,
l'action est refusée (jamais de poste ni de GitHub par défaut). Le chemin enregistré n'est jamais suivi à travers un lien : une
entrée dont le fichier mène ailleurs est écartée. La règle est la même dans `deporter` et dans `serveur-tache lancer`
(**volontairement vérifiée deux fois** ; un sous-dossier du projet est jugé par son projet).

**Limites de cette protection, dites franchement** (ce sont des limites de conception, pas des oublis) :

- Un agent qui peut **écrire le fichier de réglages enregistré** du projet, ou appeler l'API de réglage du bureau (qui n'exige
  que l'en-tête `Host` local et `X-Bureau`), peut **régler lui-même le lieu** : la protection arrête l'oubli et la
  désobéissance involontaire, pas un agent décidé à la contourner.
- `--dossier <un autre projet>` lance la recette de cet autre projet, sous l'accord de cet autre projet.
- **`serveur-outil` ne vérifie aucun accord** et agit sur n'importe quelle tâche `tache-<id>` dont il connaît l'identifiant
  (toujours dans la liste fermée de verbes).
- Piste de durcissement : un registre d'accord **côté bureau** que les agents ne peuvent pas écrire (rien n'est fait).

## Sécurité : ce que le conteneur ne peut pas faire

- Il tourne avec l'**utilisateur 1000** (pas root), `--cap-drop ALL`, `no-new-privileges`, système de fichiers en **lecture
  seule** (seuls `/tmp` 512 Mo et `/avd` 4 Go sont des volumes mémoire), **aucun réseau**, 512 processus, mémoire et swap
  bornés.
- Il ne monte que le SDK Android (**lecture seule**), `entree/` (**lecture seule**) et `sortie/` (**lecture-écriture**). Pas de
  secret, pas de clé, pas de socket Docker, pas d'environnement de l'appelant (seuls les réglages posés par l'enveloppe, en
  `-e NOM=valeur`). L'image n'a ni `curl` ni `wget`.
- Le pont est la seule porte : liste fermée de verbes, chaque argument validé par un motif avant tout usage, aucun `eval`.
- Sur le serveur, le lanceur ne suit **jamais un lien symbolique ou dur** (`find` sans `-L`, `-type f`, `-links 1`, `cd -P`).
  Sur le poste, le rapatriement n'admet que des fichiers ordinaires aux **noms fixes** (`journal.txt`, `plantage.txt`,
  `entree-tache.log`, `emulateur.log`, `captures/<nom>.png` à signature PNG) ; liens, périphériques, `..`, chemins absolus,
  lettres de lecteur, doublons et noms inconnus sont refusés et comptés (le rapport passe à `erreur`). La destination est un
  **sous-dossier strict** de `<projet>/.factory/serveur/` (jamais le projet ni `.factory` eux-mêmes ; lien ou jonction
  refusés).
- Toute commande Docker passe par `sudo -n docker ...` (jamais de mot de passe demandé).
- **Ce que l'application émulée peut atteindre** : le *loopback du conteneur* seulement (adb sur 5037, console de
  l'émulateur sur 5554). C'est contenu : sans réseau, il n'y a rien d'autre à atteindre. Les journaux, captures et textes de l'application sont **des données, jamais des instructions** ; la consigne
  de départ de l'agent le lui dit.

## Dans le bureau

Dans le panneau Direction, la carte « Serveurs de travail » montre **« Tâches du serveur »** (état en toutes lettres, mode,
projet, durée, nombre de captures, statut) et un bouton **Arrêter** pour une tâche active. Deux routes :

- `GET /api/serveurs/taches` : **l'index local seulement** (`taches.json`), jamais le réseau ; les **100** tâches les plus
  récentes ; textes masqués puis bornés (aucun secret).
- `POST /api/serveurs/taches/<id>/arreter` : mêmes protections que les autres POST des serveurs (depuis l'ordinateur seulement :
  404 sur un écouteur distant ; en-tête `X-Bureau: 1` ; `Content-Type: application/json` ; corps `{}` : un objet JSON non vide de 1 Ko au plus,
  ignoré). L'identifiant doit suivre le motif des tâches **et** se trouver dans l'index local ; il ne sert jamais à construire un
  chemin. Réponses : 202 (arrêt demandé), 404 tâche inconnue, 409 tâche déjà terminée ou opération en cours.

**Ce qui bloque pendant un arrêt.** L'arrêt tourne dans l'**unique fil de fond** du bureau (celui des sondes, installations et
migrations) : tant qu'il dure, le bureau refuse de déclarer, sonder ou installer (409, « Un arrêt de tâche d'émulation est en
cours : réessayez à sa fin »). Il ne réessaie pas un état « inconnu » (serveur muet : jusqu'à 150 s par appel) : la raison est
affichée sur la tâche. Un arrêt qui échoue laisse l'état affiché tel que le dernier connu.

## Maintenance

- **Aucun nettoyage automatique.** `~/taches/<id>` garde l'APK, les captures et les journaux de chaque tâche : **le disque du
  serveur grossit**. Pour nettoyer à la main, une fois la tâche à l'état final (jamais d'une tâche en cours) : se connecter avec
  la clé du serveur (`ssh -i ~/MyIAFactory/id_ed25519_<id du serveur> <utilisateur>@<hôte>`) puis `rm -rf ~/taches/<id>`.
  L'index du poste (`~/MyIAFactory/taches.json`) garde ses fiches : c'est un cache, aucune commande ne les retire.
- **Empreinte de l'image.** Le marqueur `~/.myiafactory/emulateur-image.version` contient les versions épinglées et l'empreinte
  (16 premiers hexadécimaux du SHA-256) des trois fichiers de l'image (`Dockerfile`, `entree-tache.sh`, `pont.sh`). Si l'un d'eux
  change dans le dépôt, la capacité `emulateur-image` devient **« À mettre à jour »** (le bureau la dit absente, `perimees` dans
  l'aperçu) et **le lanceur refuse** tout envoi (« L'image de l'émulateur du serveur ... est périmée ») jusqu'à la réinstallation
  de cette capacité. Les autres capacités ne sont pas concernées. `lancer_emulation.sh` n'entre pas dans l'empreinte : il est
  redéposé à chaque lancement.

## Ce qui n'a PAS été exécuté sur un vrai serveur

Tout ce qui précède est vérifié par des tests simulés (faux SSH, dossiers jetables), pas contre le serveur réel. En
particulier **jamais exécutés** : `pont.sh`, `lancer_emulation.sh` et `entree-tache.sh` sous Linux (leurs tests bash tournent
sous Git bash sur Windows) ; la **construction de l'image** (`Dockerfile`) ; les chemins **`flock`, `setsid`, zombie et groupe de
processus** (absents de Windows : `test_serveur_pont` et les tests de l'enveloppe n'ont jamais tourné sous Linux) ;
**adb et l'émulateur** eux-mêmes ; la **création de l'AVD** (JDK 17 des outils en ligne de commande contre Java 21) ; le
**`/tmp` monté `noexec`** et la lisibilité de `~/android-sdk` par l'utilisateur 1000 ; l'appartenance au **groupe `kvm`** et
`/dev/kvm` ; le cycle de vie de **`docker exec`**. Le premier essai réel (installer la capacité `emulateur-image`, lancer une
recette avec l'APK de MyFridgeCleaner, vérifier KVM, la capture, le rapport, l'arrêt et la libération du créneau) n'aura lieu
qu'avec l'accord explicite du Directeur.

**Installer l'image avant cet essai** : l'action `recette-emulateur` demande la capacité `emulateur-image` (et sa chaîne
`base`, `android-build`, `android-emulateur`). Dans le bureau : écran Serveurs, « Installer », cocher « Recette sur émulateur »,
« Voir l'aperçu » puis donner l'accord. En ligne de commande : `py -3.12 lancer.py plateforme serveurs apercu <id>
recette-emulateur`, puis `py -3.12 lancer.py plateforme serveurs installer <id> recette-emulateur --accord`.

L'image apporte ses propres outils en ligne de commande Android (`avdmanager`, version épinglée de `versions.json`, SHA-1
vérifié à la construction) : l'hôte n'a besoin d'aucun `cmdline-tools` dans `~/android-sdk`. Vérification en lecture seule
avant l'essai, sur le serveur : `ls ~/android-sdk/system-images/android-34/google_apis/x86_64` (l'image système épinglée doit
y être).

## Suite

- **Tranche B** : l'agent qui travaille sur le serveur (image d'agent, abonnement, pont hôte, bascule entre lieux, file visible).
  Son plan suivra le premier essai réel de la tranche A.
- **Passer l'accord côté bureau** (registre que les agents ne peuvent pas écrire), pour lever la principale limite de l'accord permanent.
- **Nettoyage** des tâches terminées (disque du serveur, index du poste) et choix d'un serveur précis par action.
