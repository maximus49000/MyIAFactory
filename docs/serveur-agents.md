# Les agents sur le serveur (tranche B)

Un agent de l'équipe peut travailler **sur le serveur** au lieu du poste ou du cloud : il y reçoit une copie du projet, y fait son
travail dans un conteneur éphémère, et ses **commits** reviennent sur le poste dans une branche `agent/<tâche>`, avec son rapport.
Deux modes : **seul** (il produit du code ou des documents) et **pilote** (il conduit en plus un émulateur Android du serveur par le
pont fermé de la tranche A et analyse les captures). Le serveur n'écrit **jamais** sur GitHub.
Conception : [`2026-11-19-agents-serveur-design.md`](superpowers/specs/2026-11-19-agents-serveur-design.md) ; plan :
[`2026-11-20-agents-serveur-tranche-b.md`](superpowers/plans/2026-11-20-agents-serveur-tranche-b.md). Le serveur lui-même :
[`serveur.md`](serveur.md) ; l'émulateur et le pont (tranche A) : [`serveur-taches.md`](serveur-taches.md).

> **Rien de cette tranche n'a encore tourné sur un vrai serveur.** Tout est vérifié par de faux SSH, de faux `docker`, de faux
> `claude` et des dépôts Git jetables. La liste de ce qui reste à prouver est dans « Non vérifié sur un vrai serveur », et la marche
> à suivre pour le prouver dans « Essais réels ». **Aucun agent n'est possible tant que le Directeur n'a pas fait la
> [connexion à l'abonnement](#connexion-a-l-abonnement).**

## Vue d'ensemble (poste et serveur)

En mots, de bout en bout :

1. **Au poste**, le moteur du bureau choisit un lieu pour l'agent (la bascule : local, serveur ou cloud, voir plus bas). Si c'est le
   serveur, un **exécuteur distant** (`moteur/executeur_serveur.py`) remplace le lancement de `claude -p` sur le poste : il prépare un
   paquet Git du projet, la consigne et le message, et les envoie par SSH (`outils/serveur_agent.py`). L'environnement et le dossier
   de travail du poste ne partent jamais.
2. **Sur le serveur**, l'enveloppe `lancer_agent.sh` prend une **place** d'agent, démarre le conteneur `myiafactory/agent` (le réseau
   `myiafactory-agents`, le jeton de l'abonnement monté en lecture seule) et rend la main. Un **veilleur détaché** tient la place,
   applique les limites, arrête le conteneur et écrit l'état final.
3. **Dans le conteneur**, `entree-agent` clone le paquet, crée la branche `agent/<tâche>`, lance `claude -p` sur le projet, puis
   commite les restes et écrit un paquet Git des seuls nouveaux commits, plus `fin.json`.
4. **En mode pilote**, un **pont hôte** (`pont_hote.py`, sur l'hôte, hors de tout conteneur) écoute sur une socket Unix montée dans le
   conteneur de l'agent et relaie, vers un **second conteneur** (l'émulateur de la tranche A, créé à la demande), la même liste fermée de verbes. L'agent
   n'a ni Docker ni accès à l'hôte.
5. **À la fin**, l'hôte contrôle que le jeton n'est dans aucune sortie ; si c'est propre, le poste rapatrie le flux, `fin.json` et le
   paquet, **vérifie** le paquet, récupère la branche `agent/<tâche>` dans le projet et lit le rapport. Une tâche faite est alors
   **fusionnée localement** (sauf chemins réservés), sans rien pousser depuis le serveur.

Le suivi est entièrement du côté du poste : la vérité sur une tâche est `~/taches/<id>/etat.json` sur le serveur, l'**index** du poste
(`~/MyIAFactory/taches.json`, un cache, comme en tranche A) en garde la fiche `type: "agent"`. Un moteur ou un bureau redémarré **rattache**
la tâche encore active au lieu d'en lancer une seconde.

## Modèle d'une tâche d'agent

Même identifiant que les tâches d'émulation : `t<AAAAMMJJ>-<HHMMSS>-<4 hexadécimaux>` (heure UTC), même `etat.json`, même veilleur.
Le **nom de tâche** (`<tâche>`, celui de la tâche du suivi du projet) donne la branche `agent/<tâche>` : lettres, chiffres, `_` `.` `-`,
60 caractères au plus, ni `..` ni point au début ou à la fin, pas de nom réservé de Windows (`con`, `nul`...). Deux tâches d'agent actives du
même projet ne peuvent pas porter le même nom, à la casse près.

### États

| `etat` | `statut` | Ce que cela veut dire |
|---|---|---|
| `en_attente` | `null` | pas de place d'agent libre (l'enveloppe rend 75) : la tâche attend, le poste réessaie toutes les 15 s, 600 s au plus, puis abandonne (la tâche reste « en attente » et marquée abandonnée, le paquet et l'APK sont retirés du serveur) |
| `en_cours` | `null` | le conteneur tourne, un veilleur le surveille |
| `terminee` | `ok` | `fin.json` présent : l'agent a fini (le code de sortie de `claude` est dans `fin.json`), ou fin normale demandée |
| `terminee` | `limite` | durée maximale (échéance du veilleur ou échéance interne de l'entrée), sortie trop volumineuse, `travail/` + `maison/` trop gros, ou moins de 5 Go libres sur le disque |
| `arretee` | `ok` | arrêt demandé (bouton du bureau) : le travail déjà fait est conclu et rapatrié |
| `echouee` | `erreur` | le conteneur est parti sans `fin.json`, Docker ne répond plus, le veilleur est mort, **secret de l'abonnement trouvé** (rien n'est rapatrié), contrôle du secret impossible, jeton absent ou mal formé, `ptrace_scope` à 0, entrée manquante |

Il n'y a pas de statut `plantage` pour un agent (c'est une notion de l'émulateur). Le poste ne rapatrie **que** les tâches `terminee` et
`arretee` : `echouee` ne donne jamais ni flux ni paquet (la sortie a pu être vidée pour un secret).

### Dossiers et fichiers sur le serveur

```
~/taches/.creneau-agent-1 ... .creneau-agent-4   les 4 verrous des places d'agent (flock) ; ~/taches/.creneau-emulation : celui de l'émulation
~/taches/<id>/
    entree/        déposé par le poste AVANT le lancement, monté en lecture seule dans le conteneur : projet.bundle (le paquet aller),
                   argv.json (les options de claude), consigne.md, message.md, demande.json, et app.apk en mode pilote
    travail/       le dépôt de l'agent (travail/projet) ; 0700, écrit par le conteneur
    maison/        le HOME de l'agent (HOME=/maison : ses sessions Claude) ; 0700
    sortie/        écrit à la fin par l'entrée : flux.jsonl, claude.err, resultat.bundle (le paquet retour), fin.json ; 0700
    pont/          pilote : pont.sock, la socket du pont hôte (monté sous /pont)
    outil/         pilote : les médias que le pont hôte COPIE depuis l'émulation (monté en lecture seule sous /outil)
    etat.json      l'état de la tâche (écrit par l'enveloppe, atomiquement) : la vérité
    arret          créé pour demander l'arrêt (« arret » ou « fin »)
    creneau        le numéro de la place prise
    emulation      pilote : l'identifiant de l'émulation liée (écrit par le pont hôte, hors de tout montage)
    enveloppe.pid, veilleur.pid, pont-hote.pid       les processus de l'hôte
    veilleur.log, docker-run.log, controle.log       journaux de l'hôte (jamais rapatriés)
    pont-hote.log, pont-hote.out                     pilote : une ligne par appel du pont hôte ; sa sortie d'erreur
~/myiafactory/serveur_ovh/...   les fichiers du dépôt déposés sur le serveur : images/agent/{Dockerfile,entree-agent.py,pont},
                                taches/{lancer_agent.sh,commun.sh,pont_hote.py,lancer_emulation.sh,enregistrer_jeton.sh}
~/agent-identifiants/jeton      le jeton de l'abonnement (dossier 0700, fichier 0600)
~/.myiafactory/agent-image.version   le marqueur de l'image (comme `emulateur-image.version`, voir `serveur.md`)
```

Sur le poste : la fiche de la tâche dans `~/MyIAFactory/taches.json` (type `agent`, tâche, mode, branche, base, session, lieu...) ; la réponse
d'un agent aux questions du Directeur est gardée dans `<projet>/.factory/agents-en-cours/` (fichier `<tâche>.reponse-serveur`) tant qu'elle tourne.

## Les paquets Git, à l'aller et au retour

**Aller.** Le poste envoie `git bundle create - HEAD <branche>` : **seuls les commits partent**.
- Les changements **non commités** restent au poste : le lancement en dit le nombre (un avertissement) et les premiers fichiers.
- Le projet doit être **sur une branche** : un HEAD détaché est refusé (« placez le projet sur une branche »), un dépôt sans commit aussi, et
  le nom de la branche doit être admis (lettres, chiffres, `_ . / -`, 200 caractères au plus).
- Le paquet fait **500 Mo au plus** (au-delà : refus avant tout envoi). Il est écrit dans un fichier temporaire puis envoyé par SSH, jamais
  gardé en entier en mémoire.
- La branche locale **`agent/<tâche>` ne doit pas être extraite** dans un dossier de travail du projet (`git worktree`) ni être la branche
  courante : le travail de l'agent ne pourrait pas y être récupéré, le lancement est refusé avant tout envoi. Si `agent/<tâche>` existe déjà et
  n'est **pas un ancêtre** de la base envoyée, le lancement est refusé aussi (choisir un autre nom de tâche, ou fusionner ou supprimer
  l'ancienne branche) : le retour n'écrase jamais une branche.

**Dans le conteneur.** `git clone --branch <branche>` du paquet, `HEAD` vérifié égal à la base annoncée, puis `git switch -c agent/<tâche>` (identité
« Agent serveur MyIAFactory » / `agent@myiafactory.invalid`). À la fin, les restes non commités sont commités (message « Agent : travail non commité à la
fin ») et `git bundle create` ne met dans `resultat.bundle` que `<base>..agent/<tâche>` ; **sans commit, il n'y a pas de paquet**.
Ces commandes tournent dans un dépôt que l'agent a pu piéger : elles sont lancées sans crochet, sans `fsmonitor`, sans signature, sans
maintenance automatique, et avec les filtres de `.gitattributes` neutralisés le temps de conclure.

**Retour.** Le poste ne fait confiance à rien de ce que le serveur renvoie (`fin.json`, flux et paquet sont des données **non fiables**) :
- tailles bornées : flux 20 Mo, `fin.json` 64 Ko, paquet 500 Mo, fichiers ordinaires seulement ;
- `fin.json` est revalidé champ par champ (code, nombre de commits, branche **exactement** `agent/<tâche>`, base égale à celle envoyée) ;
- l'en-tête du paquet est relu (format v2 ou v3 `sha1`, un seul prérequis égal à la base, **une seule référence** `refs/heads/agent/<tâche>`), puis
  `git bundle verify` et `git bundle list-heads` ; un paquet qui porte `refs/heads/main` ou une deuxième tête est refusé ;
- la branche est récupérée par un simple `git fetch` (`transfer.fsckObjects`, crochets et `fsmonitor` coupés), **jamais forcé** : une
  branche locale qui a divergé n'est pas réécrite ;
- le paquet temporaire est toujours effacé.

La branche **est gardée, non fusionnée** quand : l'agent a été **arrêté** (bouton du bureau) ; la **durée maximale** a été atteinte ou une
autre limite du serveur l'a arrêté ; le rapport n'est pas « fait » ; ou la branche touche des **chemins réservés** (voir « La fusion
locale protégée »). Elle reste alors dans le projet, à la disposition du Directeur.

## Livrables rapatriés

Un livrable construit au serveur (l'APK de `construire-apk`, sous `android_app/build/…`) est **ignoré par git** : il n'est pas dans le
paquet. Après le rapport de l'agent, le moteur rapatrie donc **en octets**, au poste, à leur chemin relatif dans le projet, les fichiers
que le rapport déclare livrables (`fichiers` avec `livrable: true`) ; le bureau peut alors les proposer au téléchargement
(`outils/serveur_livrables.py`, appelé par `ExecuteurServeur.rapatrier_livrables`).

- **Quels fichiers.** Seulement ceux du rapport, chacun revalidé au poste : chemin relatif au projet, sans `..`, sans lecteur ni `/`
  initial, segments au motif strict (lettres, chiffres, `_ . + -`, jamais un segment qui commence par « . ») ; extension dans une liste
  **fermée et minimale** propre au rapatriement : `.apk`, `.aab`, `.zip` (aucun exécutable du poste : ni `.exe`, `.msi`, `.dmg`,
  `.jar`) ; le chemin doit être une **sortie de build Android** : `(^|/)build/(app/)?outputs/(flutter-apk|apk|bundle)/<fichier>`,
  exigé pour un fichier neuf comme pour un fichier existant (Gradle range `apk/release/…` et `bundle/release/…` un niveau plus bas :
  refusés tant qu'aucune décision n'élargit le motif) ; **jamais** une clé ou un certificat (`.keystore`, `.jks`, `.pem`, `.key`,
  `.p12`, `.pfx`…) ni rien sous `maison/`, `android-signature/`, `agent-identifiants/`, `node_modules/`, `venv/`, `.venv/`,
  `vendor/`, `.git/`, `.factory/`, `site-packages/` ; **8 fichiers** au plus, **500 Mo** chacun, **1 Go** en tout.
- **Pourquoi côté poste.** La liste n'est connue que du rapport, lu par le moteur sur le poste ; l'enveloppe du serveur n'est pas
  modifiée. Le poste envoie chaque chemin validé comme une **valeur** insérée dans deux scripts figés (aucun espace, guillemet ni
  caractère de motif possible) : le **manifeste** (taille et SHA-256), puis l'**envoi** d'un fichier.
- **Au serveur.** `~/taches/<id>`, `travail` et `travail/projet` ne sont pas des liens et `pwd -P` vaut bien ce chemin ; aucun
  composant du chemin demandé n'est un lien. Le fichier est ouvert **une fois** (descripteur 3), vérifié sur ce descripteur
  (`stat -L /proc/self/fd/3` : fichier ordinaire, un seul lien, même inode que le chemin), puis haché ou envoyé **depuis ce
  descripteur** : un échange de fichier entre le contrôle et la lecture ne passe pas. Un fichier qui contient le jeton de
  l'abonnement est refusé (même `grep -F` que la sortie).
- **Limite connue.** Un `.zip` (ou un APK, qui en est un) peut contenir n'importe quoi, une clé comprise, et son contenu compressé
  n'est pas lisible par le `grep -F` du jeton : le contrôle porte sur le chemin et l'extension, pas sur le contenu d'une archive.
- **Au poste.** Les octets arrivent dans un fichier temporaire du **même dossier**, la taille et le SHA-256 sont vérifiés contre le
  manifeste, puis le fichier est **renommé** (atomique) ; un écart jette le temporaire et retire les dossiers créés pour lui.
  L'espace libre doit couvrir la taille plus 1 Go. La destination reste dans le projet (aucun lien suivi), n'est jamais un fichier
  **suivi par git**, et son chemin est écrit dans **`.git/info/exclude`** (local, jamais commité, une ligne `/<chemin>`, une seule fois)
  avant le renommage : le commit « Factory : … » (`git add -A`) ne l'ajoute jamais, même si l'agent a retiré `/build/` du
  `.gitignore`. Un fichier déjà là n'est remplacé que s'il est **plus ancien que la tâche** (date `cree` de l'index) ; sinon il est
  gardé et la raison est dite.
- **Arrêt.** L'arrêt du bureau est lu avant chaque fichier et pendant un transfert (ssh coupé) ; les fichiers restants sont dits
  « arrêt demandé ». Délai d'un envoi : taille à 1 Mo/s plus 60 s, 30 min au plus ; manifeste : 3 min.
- **Résultat dit.** Une ligne par fichier dans le journal de la tâche (caractères de contrôle remplacés) : « Livrable rapatrié : `<chemin>` (`<taille>`, `<sha16>`) », ou
  « Livrable non rapatrié : `<chemin>` : `<raison>` ». Un refus ou une panne ne fait **jamais** échouer la tâche et ne touche pas aux
  commits rapatriés (la branche `agent/<tâche>` revient comme avant).

## Les limites par défaut

Valeurs lues dans le code (`LIMITES_AGENT` de `outils/serveur_agent.py`, `lancer_agent.sh`, `entree-agent.py`). Une limite ne dépasse jamais son défaut.

| Limite | Valeur | Où elle est appliquée |
|---|---|---|
| Durée maximale | **2400 s** (40 min) ; jamais au-dessus du délai demandé par le moteur ; l'enveloppe accepte 1 à 86400 | veilleur ; l'entrée arrête `claude` **120 s avant** (à mi-chemin pour une tâche de moins de 240 s), conclut, et note `"echeance": true` |
| Tours de l'agent | **200** (`--max-turns`, ajouté par l'entrée) | `claude` |
| Mémoire | **4096 Mo** (swap identique : pas de swap) ; projet Flutter : **12 288 Mo** (`LIMITES_AGENT_FLUTTER` : un build APK dépasse 4 Go) | `docker run` |
| Processeurs | **2** ; projet Flutter : **4** | `docker run` |
| Processus | **512** ; `/tmp` en mémoire de 1 Go ; système de fichiers en lecture seule | `docker run` |
| Paquet Git | **500 Mo** à l'aller comme au retour | poste (aller) ; poste et serveur (retour) |
| Flux `stream-json` | **20 Mo** (au-delà : `claude` arrêté) ; `claude.err` 64 Ko | entrée |
| `sortie/` | **540 672 Ko** (paquet 500 Mo + flux 20 Mo + marge), taille apparente, sondé toutes les 5 s | veilleur (`limite`) |
| `travail/` + `maison/` | **8 Go** ; projet Flutter : **16 Go** avec les couches hautes des SDK (`flutter-up`, `android-up` ; Gradle prend 3 à 5 Go dans `maison/`), sondés toutes les 60 s | veilleur (`limite`) |
| Disque du serveur | plancher de **5 Go** libres (`df`), sondé toutes les 5 s | veilleur (`limite`) |
| Places d'agent par serveur | **2** par défaut, de **1 à 4** (réglage `agents_serveur_max` du projet quand il est donné) ; elles comptent des agents, **pas de la mémoire** : 2 agents Flutter (24 Go) + l'émulation (6 Go) + des campagnes de tests (jetons de mémoire de 14e, tests seulement) peuvent approcher les 62 Go du serveur | enveloppe (verrous `flock`) |
| Attente d'une place | nouvel essai toutes les **15 s**, **600 s** au plus | poste |
| Suivi par le poste | durée de la tâche **+ 120 s**, puis arrêt et rapatriement du travail | exécuteur distant |
| Consigne, message | 1 Mo au plus chacun ; options de `claude` : 64 Ko | poste |

Détail utile : la place prise est le **premier verrou libre** parmi `.creneau-agent-1..4` de rang au plus `places`, et seulement si moins de `places`
verrous sont tenus (une place abaissée pendant que des agents tiennent les rangs 3 et 4 n'est jamais dépassée). Les places sont **par serveur**, et partagées
par tous les projets qui s'en servent. Le nombre de places **par projet** dans la bascule est une autre notion : voir « La bascule ».

## Les modes « seul » et « pilote »

**Seul** : aucun pont, aucune émulation. L'agent travaille sur le code et rend des commits et un rapport. Le conteneur a le réseau
`myiafactory-agents` (sortant : l'API de Claude, mais aussi npm, Gradle, la documentation).

**Pilote** : l'agent conduit un émulateur Android du serveur, par la commande `pont <verbe> [arguments]` (client dans l'image : une ligne JSON vers
`/pont/pont.sock`, une ligne de réponse, le code du pont rendu). Même liste fermée de verbes que la tranche A
([`serveur-taches.md`](serveur-taches.md), « Les verbes du pont »). Il commence par `pont demarrer` et finit par `pont arreter`.

Un agent n'est lancé **en pilote** que si **toutes** ces conditions sont réunies (sinon il part **seul**, et le journal du moteur dit pourquoi) :
1. le Directeur a réglé l'action `recette-emulateur` sur **serveur** pour ce projet (l'accord permanent, voir [`deport.md`](deport.md)) ;
2. un **APK** est trouvé : la production `apk` du projet, la **sortie locale la plus récente** (jamais un APK de tests instrumentés, jamais un fichier atteint par un
   lien qui sort du projet) ; l'artefact GitHub n'est pas téléchargé ici ;
3. à la dernière sonde, un serveur déclaré a les capacités **`agent`, `agent-abonnement` et `emulateur-image`** (le besoin `agent-pilote`).

Une **réponse aux questions** d'un agent (voir plus bas) repart toujours en mode seul.

**Un créneau d'émulation par serveur.** L'émulation liée est une tâche d'émulation ordinaire de la tranche A : elle prend le **créneau d'émulation** du
serveur (`~/taches/.creneau-emulation`), distinct des places d'agent, et **partagé avec les tâches « Test »** et les recettes. Créneau occupé : `demarrer` rend le
code 4 « créneau d'émulation occupé, réessaie plus tard », et l'agent peut réessayer.

**Limites de l'émulation liée.** Celles de la tranche A (2 processeurs, 6144 Mo, sans réseau, 50 captures, 100 Mo de médias, 5 vidéos...) avec deux
différences : la durée de l'émulation est **le temps qui reste à l'agent**, et son inactivité est de 600 s au plus, bornée par ce reste. Quand il ne reste
plus de temps, plus aucune nouvelle émulation n'est créée (code 4). L'émulation est arrêtée (« fin ») avec l'agent, qu'il finisse, soit arrêté ou échoue.

**Médias en lecture seule sous `/outil`.** Après `capturer`, `journal`, `finfilm` (et `arreter` qui finit un film), le pont hôte **copie** la capture, `logcat.txt`, la vidéo et
ses images depuis la sortie de l'émulation vers `~/taches/<id>/outil`, que le conteneur de l'agent monte **en lecture seule** sous `/outil/` : la
réponse du pont donne le chemin `/outil/...`. Seuls des fichiers ordinaires à un seul lien sont copiés, sans jamais suivre un lien (`O_NOFOLLOW`),
dans un temporaire puis renommés ; 64 Mo au plus par fichier, 160 Mo pour tout `outil/`. L'agent lit les captures lui-même.

## Le pont hôte

`serveur_ovh/taches/pont_hote.py <id> <duree_s>` (Python 3 de l'hôte, bibliothèque standard, lancé détaché par `lancer_agent.sh`, chef de son
groupe de processus) : **la seule porte** de l'agent vers l'émulateur. Il n'a pas de confiance en l'agent, qui tient le client de la socket :

- **protocole** : une connexion, **une requête** d'une ligne JSON de 4 Ko au plus `{"verbe": ..., "args": [...]}` (exactement ces deux clés, arguments
  textes), une ligne de réponse `{"ok", "verbe", "code", "detail"}` ; une requête à la fois ;
- **liste fermée et motifs de la tranche A** (un test les fait passer par `pont.sh`, `serveur_tache.VERBES` et `pont_hote.py`) : clé dupliquée, type faux,
  verbe hors liste, argument hors motif, JSON invalide : **code 2, sans rien exécuter** ;
- **codes** : 0 fait ; 2 refusé ; 3 limite atteinte ; 4 outil en échec, émulation indisponible, **pas de pont** (« pas de pont : tâche en mode seul » si le
  dossier `/pont` n'est pas monté ; « pont pas encore prêt : réessaie dans quelques secondes » s'il l'est mais que la socket n'existe pas) ;
- **exécution** : `sudo -n docker exec tache-<émulation> /usr/local/bin/pont <verbe> ...` en **tableau, sans shell**, avec un environnement fixe, borné par
  les délais de la tranche A ; le nom du conteneur est celui de l'émulation que **ce** pont a créée, jamais une valeur reçue ;
- **5 émulations** par tâche d'agent au plus (après `arreter`, le `demarrer` suivant en crée une nouvelle ; au-delà : code 4 « limite d'émulations ») ;
- **2000 appels** au plus (les refus comptent) : au-delà, code 3 sans rien exécuter ;
- **socket** : dossier `pont/` 0700, socket 0600, propriétaire l'utilisateur de l'hôte (le même uid que le conteneur) ; un pair d'un autre uid (`SO_PEERCRED`) est refusé ;
- **journal** `pont-hote.log` : une ligne par appel (heure, verbe et arguments **validés** seulement, code, durée), sur l'hôte seul : `pont/` est inscriptible par l'agent ;
- le pont hôte **ne voit jamais le jeton** ; à sa fin (signal du veilleur), il arrête l'émulation encore liée.

## La bascule entre lieux et les places

Un projet a trois lieux possibles pour ses agents : **local** (le poste), **serveur**, **cloud**. Réglages, dans la partie « Parallélisme du projet »
du bureau (onglet de facturation) ou dans `.factory/factory.json` du projet :

| Réglage | Valeurs | Défaut |
|---|---|---|
| `agents_locaux_max` | 1 à 16 | (réglage existant) |
| `agents_cloud_max` | 0 à 16 | (réglage existant) |
| **`agents_serveur_max`** | **0 à 4** : agents simultanés au serveur pour ce projet | **0** : le serveur ne sert à rien tant qu'on ne l'a pas réglé |
| **`ordre_lieux`** | liste sans doublon d'au moins un lieu parmi `local`, `serveur`, `cloud` ; un lieu retiré n'est jamais utilisé | **`["local", "serveur", "cloud"]`** |
| **`ordre_lieux_par_metier`** | `{rôle: ordre}` : l'ordre d'un métier l'emporte sur celui du projet (« réglable par type de tâche ») | vide |
| **`agents_abonnement_max`** | **1 à 32**, ou absent (aucun plafond) ; dans le fichier du **bureau** (`~/MyIAFactory/bureau.json`), pas dans le projet | absent |

**Règle.** Pour une tâche, le moteur essaie les lieux **dans l'ordre**, et prend le **premier lieu non hors ligne qui a une place libre** (agents actifs du lieu < places
du lieu) **et une fiche d'agent libre**. Un lieu imposé (le `lieu` écrit de l'étape de la tâche, ou le métier réservé à un lieu) l'emporte sur l'ordre. Un projet sans place
serveur, sans ordre réglé et sans plafond garde le comportement d'avant, à l'identique.

**Le choix de l'agent par le moteur** (`moteur/regles.py`, `_demarrer_en_attente` et `_choisir_agent`) applique cette règle à toute tâche qui part d'elle-même
(prototype, étape du flux, correction...) :
- les places serveur sont **comptées à part** (`agents_serveur_max` moins les tâches actives d'agents serveur) : un agent serveur ne prend jamais une place locale,
  et la charge du poste ne retient pas le serveur ;
- les lieux sont essayés dans l'ordre du projet (ou du métier) ; un lieu sans place libre, hors ligne ou sans fiche libre passe au suivant ; un lieu absent de
  l'ordre n'est jamais utilisé, même avec une place libre ;
- une étape au `lieu` écrit (`local` : `dev-local`, `livraison`...) ou un métier réservé reste à son lieu : jamais au serveur ;
- une tâche dont Fable est accordé reste au poste (comme pour le cloud, par prudence).

**L'agent attitré ou repris.** L'agent attitré du **cadrage** est choisi au poste et le reste (la discussion avec le Directeur). Une tâche **reprise** (déjà commencée)
revient de préférence au même agent polyvalent, **à son lieu**, s'il est libre et que ce lieu a une place et convient à l'étape ; sinon n'importe quel agent la reprend
selon l'ordre des lieux : elle repart d'un contexte neuf (le départ ordinaire ne reprend jamais une session). La reprise d'une session (`--resume`, réponse aux
questions d'un agent) ne passe pas par ce choix : elle repart toujours là où la session est née (un agent serveur sur le serveur, un agent local au poste).
Une installation d'outils garde le choix d'avant (le poste, puis le cloud).

**Le plafond d'abonnement** est **au-dessus** des places par lieu : c'est le nombre total d'agents actifs, **tous lieux et tous projets du bureau**,
que l'abonnement supporte. Atteint, la tâche attend : « plafond d'abonnement atteint (n/n) ». Un fichier du bureau illisible ou un plafond invalide ferme
aussi la porte (« plafond d'abonnement : réglage illisible (chemin) ») : on ne retire pas la garde en silence.

**Serveur hors ligne.** Le serveur est « hors ligne » pour la bascule si **aucun** serveur déclaré n'a les capacités `agent` et `agent-abonnement` constatées
présentes **il y a moins de 24 h** (état local `serveurs-etat.json`, aucune connexion à ce moment-là). Le moteur **rafraîchit la sonde toutes les 6 h** (seulement
si un projet a `agents_serveur_max` > 0), et aussi après le retour d'un agent serveur sans erreur (au plus une fois toutes les 10 min) : il faut donc plusieurs sondes ratées de suite (24 h pour 6 h) avant que le
serveur passe hors ligne. Un lieu hors ligne est sauté.

**La file.** Si tout est plein ou hors ligne, la tâche **reste en file avec une raison qui nomme chaque lieu**, par exemple
`local : 2/2 occupés ; serveur : hors ligne ; cloud : 0 place` (ou `serveur : 1/2 occupés`, `cloud : session à créer pour ...`). Elle n'est **jamais lancée ailleurs en silence**.
Cette raison est celle que montre la file du bureau.

## Les questions de l'agent

Personne ne voit la fenêtre d'un agent serveur et le Directeur n'est pas joignable pendant son travail (le conteneur n'a **aucun accès entrant**). Sa consigne de départ
(`depart.consigne_serveur`) lui dit donc : commiter son travail sur `agent/<tâche>`, ne rien pousser, et poser une question ou demander un accord dans son rapport, en
`message.questions` avec `attend: true`, puis s'arrêter. Le bureau relaie les questions au Directeur par le chemin habituel. À la réponse, le moteur relance l'agent **avec sa
session** (`claude --resume <session>`) :

- une **nouvelle tâche serveur** démarre avec `reprend: <ancienne tâche>` : l'enveloppe copie `~/taches/<ancienne>/{travail,maison}` par `cp -a` (les liens sont copiés comme des liens, jamais suivis)
  et refuse si l'ancienne tâche n'est pas finie ou n'est pas une tâche d'agent du même projet ;
- l'entrée reprend le dépôt gardé tel quel (pas de nouveau clone) ; la nouvelle base est la tête de la branche rapatriée si elle descend de l'ancienne base ;
- une réponse aux questions est toujours en mode **seul**.

Conséquence : **ne supprimez pas `~/taches/<id>`** d'un agent qui attend une réponse (voir « Entretien »).

## L'arrêt

- **Le bouton « Arrêter »** de la carte « Tâches du serveur » du bureau (route `POST /api/serveurs/taches/<id>/arreter`, mêmes protections que les autres POST des
  serveurs, voir [`serveur-taches.md`](serveur-taches.md)). Pour un agent, il pose la marque d'arrêt du moteur (par le **nom du dossier** du projet), arrête l'agent **et son
  émulation liée**, et attend au plus **25 s** avant de répondre. L'arrêt fini dans ce délai : réponse 200 avec l'état final (et `emulation` : `arretee` ou `non_confirmee`) ; sinon
  **202** (`{"demarre": true}`) et l'écran lit l'état. 404 tâche inconnue, 409 déjà terminée ou une opération déjà en cours.
- **La conclusion.** Le veilleur arrête le conteneur par `docker stop -t 60` : l'entrée reçoit `SIGTERM`, arrête `claude`, mais **conclut quand même** (restes commités, paquet,
  `fin.json`) : la **fenêtre de conclusion va jusqu'à 60 s**. Le pont hôte (son groupe de processus) et l'émulation liée sont arrêtés, **puis le contrôle du secret** passe, et
  seulement alors l'état final `arretee` est écrit.
- **Aucune relance.** L'agent est lu comme « agent arrêté par l'utilisateur depuis le bouton du bureau » : le moteur ne repart pas de lui-même. Son travail déjà commité est rapatrié
  dans la branche `agent/<tâche>`, **non fusionnée**. Serveur muet au moment de l'arrêt : il est noté (`arret_demande`) et relayé dès que le serveur répond.
- **Une échéance n'est jamais relancée** : durée maximale atteinte (celle du veilleur, ou celle que le poste constate après durée + 120 s), le travail rapatrié est gardé et le moteur ne
  relance pas (un nouvel essai retrouverait la même limite). Même règle pour les autres limites du serveur (sortie, disque, travail trop gros), dont la raison est dite.

## La fusion locale protégée

Un agent serveur dont le rapport est « fait » et qui a rapporté une branche voit celle-ci **fusionnée dans le projet, localement** (`cloud.fusionner(..., distante=False)`) : la fusion se fait
dans le dépôt du poste, sans crochet ni `fsmonitor` du dépôt, sur le **commit épinglé** de la branche (ce qui est fusionné est exactement ce qui a été contrôlé). Un envoi manqué n'est pas un échec :
la fusion part avec le prochain envoi du moteur. **Avant la fusion**, deux listes de chemins sont contrôlées : ce que la branche change depuis la base commune, **et** ce que la fusion changerait
vraiment (renommages, bases multiples). Un seul chemin **réservé** et la fusion est **refusée** : la branche est gardée telle quelle pour le Directeur.

Sont réservés, **à toute profondeur** (un projet peut vivre dans un sous-dossier : `app/.factory/...`), sans tenir compte de la casse ni des points et espaces finaux :

- `.factory`, `fiches`, `factory.json` (l'état et les réglages de la factory, dont l'accord du Directeur) ;
- `.gitattributes`, `.gitmodules`, `.lfsconfig`, `.git` et **tout dossier dont le nom commence par `.git`** (`.github`, crochets, workflows ; un simple fichier `.gitignore` reste permis) ;
- `.claude`, `.mcp.json` (réglages et serveurs MCP de Claude Code), `.pre-commit-config.yaml` / `.yml`, `lefthook.yml` / `.yaml` (et leurs variantes `.lefthook`, `lefthook-local`), `.husky` ;
- `.vscode`, `.devcontainer`, `.devcontainer.json`, `.envrc` ;
- le **dossier de crochets** que le dépôt déclare (`core.hooksPath`, même absolu s'il tombe dans le dépôt) ;
- tout chemin qui sort du dépôt (`..`, absolu, lecteur, `:`) et les noms courts de Windows (`FACTOR~1`).

Message de refus : « la branche ... de l'agent serveur touche des chemins réservés au Directeur et à la factory (...) : elle est gardée telle quelle pour le Directeur, non fusionnée ». Le moteur note la
raison et pose au Directeur la question habituelle d'une fusion impossible (comme un conflit). Les fichiers d'état du moteur en conflit gardent la version locale.

## Sécurité

- **Le jeton de l'abonnement** vit dans `~/agent-identifiants/jeton` (dossier 0700, fichier 0600), **monté en lecture seule** (`-v ...:/run/identifiants/jeton:ro`) dans les **seuls** conteneurs d'agent :
  jamais dans un conteneur d'outil, une ligne de commande, `docker inspect` (pas de `-e` du jeton), Git ou un journal. MyIAFactory ne le lit, ne le saisit, ne le transmet ni ne le journalise jamais.
- **Ce que l'agent peut lire.** L'agent **peut lire le jeton** : l'entrée le lit dans `/run/identifiants/jeton` et le pose dans la variable **`CLAUDE_CODE_OAUTH_TOKEN`** de `claude`, que **ses outils héritent**, et le
  fichier reste lisible sous le même utilisateur. Il faut le savoir : un agent manipulé peut tenter de le recopier ou de l'envoyer.
- **Le contrôle du secret** (par le veilleur, **avant** l'état final) cherche le jeton **brut** et ses **trois alignements en base64** : dans tout `sortie/` (flux, erreurs, `fin.json`, paquet), puis, **toujours**, dans le
  texte de `git log -p` (sans filtres ni conversions) et dans le contenu de **chaque objet** du paquet, produit par un **conteneur de contrôle sans jeton et sans réseau** (jamais par un `git` de l'hôte : la configuration
  du dépôt piégé pourrait y lancer n'importe quoi). Trouvé : `sortie/` est vidée, la tâche finit `echouee`/`erreur`, raison **« secret de l'abonnement trouvé dans la sortie : rien n'est rapatrié »**.
  Contrôle impossible (fichier du jeton qui n'est pas **une** ligne valide, `grep` ou conteneur de contrôle en échec ou trop long) : même sortie vidée, raison « Contrôle du secret de l'abonnement impossible (voir
  controle.log) : rien n'est rapatrié ».
- **Ce que le contrôle ne voit pas, dit franchement.** Il ne détecte **que la forme brute et trois alignements base64** : une sortie **encodée autrement** (hexadécimal, découpée, chiffrée...) passe, et un **envoi par le
  réseau** n'est pas vu du tout. **Le réseau sortant du conteneur reste OUVERT** (npm, Gradle, documentation en ont besoin). C'est une **décision du Directeur** : la liste blanche du trafic sortant (limiter à l'API de Claude)
  est **écartée pour l'instant**, **à rouvrir avant d'exposer des projets sensibles** à un agent serveur.
- **Le conteneur d'agent** : utilisateur de l'hôte (`--user $(id -u):$(id -g)`, jamais root), `--read-only`, `--cap-drop ALL`, `no-new-privileges`, 512 processus, mémoire et processeurs bornés. Il n'a ni socket Docker, ni `sudo`,
  ni accès entrant, ni `curl` ni `wget` dans l'image (purgés en fin de construction).
- **Ce que l'agent ne peut pas falsifier.** L'entrée de l'agent (PID 1) se rend non « dumpable », écrit le flux et les erreurs dans des fichiers **sans nom** qu'elle recopie à la fin, retire de `sortie/` tout ce que
  l'agent y a déposé, et ne laisse que le paquet qu'elle a créé. Elle ne lance jamais ce que contient le dépôt de l'agent. Malgré cela, `fin.json`, le flux et le paquet restent des **données non fiables** pour le poste (vérifiées, voir
  « Retour »).
- **`ptrace_scope`.** `claude` et l'entrée tournent sous le même utilisateur : avec `kernel.yama.ptrace_scope` à 0, `claude` pourrait tracer l'entrée et lui faire écrire n'importe quoi. L'enveloppe **exige 1 ou plus** : à **0**,
  la tâche est refusée (`echouee`, avec la commande à lancer : `sudo sysctl -w kernel.yama.ptrace_scope=1`, et un fichier dans `/etc/sysctl.d/` pour le garder) ; **valeur illisible** (Yama absent) : un **avertissement**
  dans `veilleur.log`, et la tâche démarre.
- **Données, jamais instructions.** Ce qui vient de l'application émulée ou du pont (textes à l'écran, journaux, captures, réponse du pont) est une donnée : la consigne de départ le dit à l'agent.

## Prérequis du serveur

- Les capacités **`agent`** (installable : image `myiafactory/agent` et réseau Docker `myiafactory-agents`, depuis `base`), **`agent-abonnement`** (**non installable** : l'étape humaine de la
  section suivante) et, pour le mode pilote, **`emulateur-image`** (donc `android-emulateur`, `/dev/kvm`). Besoins : `agent-serveur` = `agent` + `agent-abonnement` ; `agent-pilote` = `agent-serveur` + `emulateur-image`.
- Installer la capacité `agent` : l'écran Serveurs du bureau ne propose pas (encore) d'action pour elle ; en ligne de commande, `py -3.12 lancer.py plateforme serveurs apercu <id> agent-serveur`, puis
  `py -3.12 lancer.py plateforme serveurs installer <id> agent-serveur --accord` (aperçu puis accord, comme toute installation : [`serveur.md`](serveur.md)). L'aperçu range `agent-abonnement` dans les capacités bloquées
  avec le geste à faire. Elle demande de la place pour construire l'image (Ubuntu 24.04, Node, Claude Code à la version épinglée de `versions.json`) et refuse de tourner sous root.
- Sur l'hôte : un utilisateur ordinaire avec `sudo` sans mot de passe (comme pour tout le serveur), `python3` (pour le pont hôte), `flock`, `setsid`, `timeout`, `base64`, `/proc` et `kernel.yama.ptrace_scope` ≥ 1 (Ubuntu : 1 par défaut).
- **Si l'image change** dans le dépôt (Dockerfile, entrée ou client du pont), le marqueur `~/.myiafactory/agent-image.version` ne correspond plus : la capacité `agent` devient « À mettre à jour » et il faut la réinstaller
  (même mécanisme que `emulateur-image`).

<a id="projets-flutter"></a>
## Projets Flutter (capacité `flutter-sdk`)

Un agent serveur d'un projet **Flutter** (FM_Stats : `android_app/pubspec.yaml`) a besoin de l'outil `flutter`. Il n'est
**jamais dans l'image** : le SDK vit sur l'**hôte**, dans `~/flutter-sdk`, et n'est monté **qu'en lecture seule** dans le
conteneur des agents des projets Flutter.

- **La capacité `flutter-sdk`** (étape `flutter_sdk` de `mise_en_place.sh`, dépend d'`android-build`) : Flutter **stable
  épinglé** (clé `flutter` de `serveur_ovh/versions.json`, aujourd'hui 3.47.1, la version du poste). Le manifeste officiel
  `releases_linux.json` (storage.googleapis.com/flutter_infra_release) est téléchargé puis lu (JSON) : **une seule** archive
  Linux de cette version au canal stable, nom vérifié par motif strict, SHA-256 de 64 hexadécimaux ; l'archive est
  téléchargée, **vérifiée par ce SHA-256 avant extraction** (jamais de `curl | sh`), puis mise en place atomiquement (une
  autre version est mise de côté dans `~/flutter-sdk.ancien.<date>`, jamais supprimée par l'étape). Suivent
  `flutter precache --android --universal` (rien d'autre), l'acceptation des licences Android (`sdkmanager --licenses`,
  avertissement seulement) et le fichier `bin/cache/lockfile`. Marqueur `~/.myiafactory/flutter-sdk.version`
  (« `flutter=<version>;canal=stable` ») écrit en dernier ; changer la version de `versions.json` le rend **périmé** : la
  capacité est alors refaite. Jamais sous root ; environ 3 Go ; idempotente (rien n'est retéléchargé si le marqueur est à jour).
  Un `~/flutter-sdk` **déjà présent** qui annonce la bonne version (`flutter --version`) est **gardé sans contrôle de
  somme** : seuls cette étape ou l'utilisateur du serveur peuvent l'avoir posé (hors menace). Délai SSH de l'étape :
  3600 s, au-dessus de la somme de ses délais internes (3480 s).
- **Après cette mise à jour, l'image `agent` doit être reconstruite** : l'entrée du conteneur (`entree-agent.py`) a
  changé, donc la capacité `agent` apparaît « **À mettre à jour** » jusqu'à la réinstallation de `agent-serveur`
  (`py -3.12 lancer.py plateforme serveurs installer <id> agent-serveur --accord`, ou `agent-flutter`, qui la comprend).
  D'ici là, les agents serveur partent avec l'ancienne image (sans les variables Flutter).
- **L'installer** : besoin `agent-flutter` (= `agent` + `agent-abonnement` + `flutter-sdk`). L'écran Serveurs du bureau ne
  propose pas encore cette action ; en ligne de commande, aperçu puis accord :
  `py -3.12 lancer.py plateforme serveurs apercu <id> agent-flutter` puis
  `py -3.12 lancer.py plateforme serveurs installer <id> agent-flutter --accord`.
- **Le projet est reconnu sur le poste** (`outils/projet_flutter.py`) : un `pubspec.yaml` à la racine ou dans un
  sous-dossier direct dont la section `dependencies:` déclare `flutter:` + `sdk: flutter`. La demande de l'agent porte alors
  `"flutter": true` (un booléen, relu sur le serveur par un motif strict ; une clé en double ou une autre valeur fait échouer
  la tâche) et le serveur choisi doit avoir `flutter-sdk`. **Bascule** : pour un projet Flutter, un serveur sans
  `flutter-sdk` compte comme indisponible **pour ce projet** : le choix retombe sur le lieu suivant de l'ordre (le poste),
  avec la raison « serveur : flutter-sdk absent du serveur » ; un projet non Flutter n'est pas concerné.
- **Dans le conteneur** (mêmes durcissements : utilisateur de l'hôte, `--read-only`, `--cap-drop ALL`,
  `no-new-privileges`…) : **SDK en copie sur écriture par tâche : lecture sur `~/flutter-sdk`, jamais modifié ;
  écritures dans la couche de la tâche.** Flutter écrit dans son propre SDK (`bin/cache` à chaque lancement,
  `packages/flutter_tools/.dart_tool` pour `flutter analyze`… : constaté sur le serveur réel, en lecture seule
  `flutter analyze` échouait). `/opt/flutter-sdk` est donc un **volume overlay propre à la tâche** `flutter-<id>` (aucun
  montage du SDK de l'hôte en bind) : couche basse `~/flutter-sdk` entier (jamais modifiée),
  couche haute et dossier de travail `~/taches/<id>/flutter-up` et `flutter-work` (0700, même disque). Le volume est créé
  par `sudo -n docker volume create --driver local --opt type=overlay …`, puis **prouvé** avant l'agent par un
  `docker run --rm --network none` bref qui le monte (un overlay n'est monté qu'au lancement d'un conteneur) ; refusé : la
  tâche échoue « **flutter : overlay refusé** », jamais de repli en écriture sur le SDK de l'hôte. Il est retiré à la fin
  de la tâche, sur un échec de l'enveloppe et, à chaque lancement d'un agent Flutter, pour les tâches finies (balayage) ;
  `flutter-up` compte dans le plafond `travail/` + `maison/`. `~/android-sdk` suit le même chemin (même fonction
  `preparer_overlay`) : volume `asdk-<id>`, couches `android-up` et `android-work`, sur `/opt/android-sdk`, prouvé de
  même (« **SDK Android : overlay refusé** » sinon), retiré et balayé de même, `android-up` compté. L'entrée pose des
  valeurs **fixes** :
  `PATH` (`/opt/flutter-sdk/bin` en tête), `FLUTTER_ROOT`, `PUB_CACHE=/maison/.pub-cache` (inscriptible, gardé à la
  reprise, compté dans les 8 Go de `travail/` + `maison/`), `ANDROID_HOME`, `JAVA_HOME` (JDK 17 de l'image),
  `GRADLE_USER_HOME=/maison/.gradle`, `CI=true`, `FLUTTER_SUPPRESS_ANALYTICS=true`, et `ANDROID_USER_HOME=/maison/.android`
  (créé par l'enveloppe) avec `JAVA_TOOL_OPTIONS=-Duser.home=/maison` : la JVM prend sinon `user.home` dans `/etc/passwd`
  (le `/home` de l'hôte, en lecture seule dans le conteneur) et Gradle/AGP échouaient sur `~/.android`.
  `flutter pub get` passe par le **réseau sortant ouvert** des agents (pub.dev).
- **Le droit d'appeler `flutter`** n'est jamais donné par la capacité : c'est la règle `Bash(flutter:*)` de la fiche de
  l'agent (jamais `Bash` seul), ouverte par le Directeur (décision `outil_agent`, « Autoriser ce programme ») ou par
  `{"action": "ouvrir_outil", "cle": "<agent>", "outil": "Bash(flutter:*)"}` envoyé à `orchestrateur/outil.py --factory <F>
  lancer fiche`. La règle couvre une commande qui **commence** par `flutter` ; dans une commande composée (`cd x && flutter
  test`), chaque morceau doit être couvert : préférer `flutter pub get --directory android_app`, et pour `flutter test`
  un `cd android_app` seul puis `flutter test`. La consigne de départ d'un agent serveur d'un projet Flutter le dit
  (`depart.CONSIGNE_FLUTTER_SERVEUR` : commandes simples, ni `&&`, `;`, `|`, `timeout` ni variable en préfixe).
- **Commandes uniques** (`serveur_ovh/agent-outils/outil-flutter.sh`, déposé par le poste avec l'enveloppe, monté en lecture
  seule sous `/opt/outils`, en tête du `PATH` du conteneur, image inchangée) : `analyser-flutter`, `tester-flutter`,
  `construire-apk [release|debug]` (défaut `release`) ; elles se placent dans le dossier Flutter du projet (transmis par le
  poste, `"flutter_dossier"`, motif strict), lancent `flutter pub get` si les paquets ne sont pas à jour puis l'étape
  (sortie bornée aux 200 000 derniers octets) ; tout autre argument : code 2 sans rien lancer. Chacune s'ouvre à la fiche
  par sa règle (`Bash(analyser-flutter:*)`, `Bash(tester-flutter:*)`, `Bash(construire-apk:*)`, jamais `Bash` seul), par la
  décision `outil_agent` ou la commande `fiche` `ouvrir_outil`.
- **Construire l'APK au serveur : JDK 17, SDK Android et Flutter en copie sur écriture par tâche.** L'image `agent`
  porte le JDK 17 de la distribution (`openjdk-17-jdk-headless`) : elle change, la capacité `agent` redevient
  « À mettre à jour » jusqu'à la réinstallation d'`agent-serveur`. `flutter build apk` est appelé par `flutter` (règle
  `Bash(flutter:*)`) ; Gradle (wrapper) et AGP sont lancés par flutter, pas par l'agent : aucune règle `java` ou
  `gradle` n'est requise tant que l'agent n'appelle pas `./gradlew` lui-même (sinon `Bash(./gradlew:*)` serait à demander
  : un chemin relatif, que la fiche n'ouvre pas). Gradle et ses dépendances passent par le réseau sortant ouvert ; leur
  cache vit sous `/maison/.gradle` (compté dans les 8 Go). L'APK est écrit dans le dépôt de l'agent
  (`build/app/outputs/flutter-apk/` du dossier Flutter), qui est hors des commits (`build/` ignoré) : il ne revient
  **pas** au poste par la branche ; le rapatrier est à faire.
- **Signature : la clé de debug du poste du Directeur.** Un projet qui signe sa release avec la configuration `debug`
  (FM_Stats) doit signer au serveur avec la **même** clé que le poste, sinon l'APK ne se met pas à jour sur l'appareil
  (conflit de signature). Décision du Directeur : sa clé `~/.android/debug.keystore` est copiée sur le serveur dans
  `~/android-signature/debug.keystore` (dossier 0700, fichier 0400 ; étape manuelle, faite par le Directeur ou le
  contrôleur, jamais par MyIAFactory, qui ne lit ni la clé ni son mot de passe). Pour un projet Flutter, l'enveloppe la monte
  **en lecture seule** sur `/maison/.android/debug.keystore` (`user.home/.android` d'AGP, `HOME=/maison`), après avoir
  créé elle-même la cible (un fichier vide de `maison/.android/`, sous l'uid de l'hôte). **Absente** : rien n'est monté,
  la tâche continue et AGP signe avec une clé de debug **jetable** créée dans `/maison/.android` (l'APK ne remplacera pas
  celui de l'appareil). **Présente mais pas un fichier ordinaire** (lien, dossier) : la tâche échoue (« clé de debug
  refusée »). Un projet non Flutter ne la reçoit jamais.
  **Risque accepté par le Directeur** : le code du projet qui tourne dans le conteneur (Gradle, scripts de build, tests)
  et l'agent lui-même **peuvent lire cette clé** (clé de debug, projets du Directeur seulement). Elle ne doit **jamais**
  être poussée ni rapatriée : `maison/` n'est jamais rapatrié (seuls `flux.jsonl`, `fin.json` et `resultat.bundle`
  reviennent) et le paquet résultat ne contient que les commits du dépôt `/travail/projet` ; le fichier de `maison/.android`
  sur l'hôte reste vide (le montage le recouvre). Limite : un agent qui **copierait** la clé dans le dépôt et la commiterait
  la ferait entrer dans le paquet ; aucun contrôle ne le détecte aujourd'hui (contrairement au jeton de l'abonnement) :
  relire les branches rapatriées (un fichier `*.keystore` ne doit jamais y apparaître).
- **« Release signé » : le serveur compile, le poste signe** (réglage « Signature des APK » = `poste_signe`, action
  `release-signe` du catalogue Android). L'enveloppe écrit le choix de signature dans `~/taches/<id>/signature`, monté en
  lecture seule sur `/opt/outils/signature`. Avec `poste_signe`, `construire-apk` (release) pose le temps de la
  construction un script d'init Gradle figé (`$GRADLE_USER_HOME/init.d/myiafactory-release-non-signee.gradle` :
  `androidComponents.finalizeDsl`, `signingConfig = null` pour la release ; le projet n'a rien à changer), puis range
  l'APK sous `build/app/outputs/flutter-apk/app-release-unsigned.apk` (jamais sous le nom `app-release.apk`) : l'agent le
  déclare livrable, il est rapatrié au poste. La signature se fait au poste, par le Directeur : `py -3.12 lancer.py
  signer-release --dossier <projet> --keystore <coffre> --alias <alias> --sortie <fichier>` (`zipalign`, `apksigner` du
  SDK du poste ; mot de passe saisi au terminal, jamais par un agent ; `outils/signature_locale.py`). `lancer.py deporter
  release-signe` ne lance rien : il dit cette marche à suivre. Non vérifié sur un vrai serveur (essai J15b sur FM_Stats).
- **Limites** : les tests routés au serveur (`lancer.py tests`) ne connaissent pas encore la famille `flutter`.

<a id="connexion-a-l-abonnement"></a>
## Connexion à l'abonnement

**Étape humaine, à faire une seule fois par le Directeur.** MyIAFactory ne saisit, ne lit et ne transmet jamais le jeton : c'est **vous** qui le créez et le déposez sur le serveur. Sans lui, la capacité
`agent-abonnement` est absente, le serveur est « hors ligne » pour la bascule, et la carte du serveur affiche « Connexion à l'abonnement à faire » avec un lien vers cette page.

**Avant de commencer** : la capacité `agent` doit être installée (l'image `myiafactory/agent` existe, voir « Prérequis du serveur ») ; vous avez la session graphique du serveur (capacité `session-graphique`).

1. **Ouvrir la session graphique du serveur.** Procédure complète dans [`serveur-ovh.md`](serveur-ovh.md#session-graphique-unity-hub) : `py -3.12 lancer.py plateforme bureau-distant` ouvre le tunnel et le fichier de connexion ; saisissez l'utilisateur
   du serveur et le mot de passe de session (fichier `bureau-distant.txt`). Si la capacité `session-graphique` manque : `py -3.12 lancer.py plateforme installer --bureau-distant` (voir [`serveur.md`](serveur.md)).
2. **Ouvrir un terminal** dans cette session et lancer (l'image n'a pas de point d'entrée, la commande s'exécute telle quelle) :
   ```
   sudo docker run --rm -it --network myiafactory-agents myiafactory/agent claude setup-token
   ```
3. **Se connecter.** Le terminal affiche un **lien** : ouvrez-le dans le **navigateur de la session** (Firefox), connectez-vous au **compte de l'abonnement** que les agents utiliseront, autorisez l'accès ; si le terminal demande un code,
   collez-le. Le terminal affiche alors le **jeton** (une longue suite de lettres, chiffres, points et tirets). **Copiez-le entièrement** : une coupure de ligne ou un espace en trop le fait refuser à l'étape suivante.
4. **Le déposer.** Dans le même terminal :
   ```
   bash ~/myiafactory/serveur_ovh/taches/enregistrer_jeton.sh
   ```
   puis **collez** le jeton et validez par Entrée. **Rien ne s'affiche** pendant la saisie (c'est voulu). Le script refuse un jeton vide ou hors de 20 à 400 caractères parmi lettres, chiffres, `.`, `-`, `_`, l'écrit dans
   `~/agent-identifiants/jeton` (dossier 0700, fichier 0600, par un fichier temporaire puis renommage : un refus laisse l'ancien jeton intact), et répond « Jeton enregistré... ». Il ne l'affiche jamais ; code 0 enregistré, 2 refusé.
5. **Effacer la trace.** Fermez le terminal (le jeton est resté à l'écran à l'étape 3), et fermez la session graphique si vous ne vous en servez plus.
6. **Vérifier dans le bureau.** La capacité « **Connexion à l'abonnement** » (`agent-abonnement`) doit passer à « présente » à la **prochaine sonde** : « Tester la connexion » sur la carte du serveur, ou
   `py -3.12 lancer.py plateforme serveurs sonder <id>`. Le message « Connexion à l'abonnement à faire » disparaît. (Le moteur sonde aussi de lui-même toutes les 6 h quand un projet a des places serveur.)

**Renouvellement.** Le jeton a une durée limitée (un an, d'après le plan) et peut être révoqué : refaites les étapes 1 à 6 ; le nouveau jeton remplace l'ancien, qui reste en place si un refus survient. **Retrait.**
Pour retirer l'accès des agents du serveur : `rm ~/agent-identifiants/jeton` sur le serveur ; la capacité redevient absente à la sonde suivante et le serveur est hors ligne pour la bascule. Révoquer le jeton lui-même se fait
depuis le compte de l'abonnement (chemin exact non vérifié ici).

## Essais réels

À faire **un seul à la fois, avec l'accord explicite du Directeur**, jamais par un sous-agent, sur MyFridgeCleaner ; noter chaque écart et les temps mesurés.

- [ ] **Capacité `agent` installée** : aperçu puis accord (`plateforme serveurs installer <id> agent-serveur --accord`) ; la capacité passe « présente » ; le réseau `myiafactory-agents` existe (`sudo docker network ls`).
- [ ] **Image reconstruite** : `sudo docker image inspect myiafactory/agent` ; `~/.myiafactory/agent-image.version` présent ; ni `curl` ni `wget` dans l'image ; relancer l'installation ne reconstruit rien (idempotente).
- [ ] **Connexion** (« Connexion à l'abonnement » ci-dessus) : `agent-abonnement` « présente » dans le bureau ; vérifier à l'hôte `stat -c %a ~/agent-identifiants ~/agent-identifiants/jeton` (700 puis 600) ; vérifier `cat /proc/sys/kernel/yama/ptrace_scope` (≥ 1) ;
  vérifier l'uid de l'hôte et celui du conteneur ; vérifier l'accès sortant à l'API depuis `myiafactory-agents`.
- [ ] **Agent seul** : `agents_serveur_max = 1`, `ordre_lieux = ["serveur"]`, une petite tâche documentaire → branche `agent/<tâche>` rapatriée, rapport lu, fusion locale, usage noté dans l'abonnement du bureau.
- [ ] **Agent pilote** : l'accord `recette-emulateur` sur serveur, `emulateur-image` présente, un APK → « lance l'application et décris l'écran d'accueil » : `pont demarrer` ... `capturer`, capture sous `/outil/`, lue par l'agent.
- [ ] **Bascule** : places locales pleines → le serveur est choisi ; serveur marqué hors ligne (sonde ancienne ou jeton retiré) → la tâche reste en file avec la raison qui nomme chaque lieu.
- [ ] **Arrêt** : « Arrêter » depuis le bureau pendant l'essai pilote : agent, pont hôte et émulation s'arrêtent, les deux créneaux sont libérés, « arrêtée par l'utilisateur », branche gardée non fusionnée ; puis nettoyer `~/taches`.

## Entretien

- **Aucun nettoyage automatique.** `~/taches/<id>` garde le dépôt de l'agent, sa maison et ses sorties : **le disque du serveur grossit** (jusqu'à 8 Go de `travail/` + `maison/` par tâche) ; le veilleur arrête les tâches qui descendent le disque sous 5 Go libres.
  Pour nettoyer à la main, **une fois la tâche à l'état final** et si aucune question ne lui est en attente (la reprise relit son `travail/` et sa `maison/`) : se connecter (`ssh -i ~/MyIAFactory/id_ed25519_<id du serveur> <utilisateur>@<hôte>`),
  lire l'émulation liée (`cat ~/taches/<id>/emulation`) puis `rm -rf ~/taches/<id>` (et celui de l'émulation). L'index du poste garde ses fiches : c'est un cache.
- **Journaux** (sur le serveur, dans `~/taches/<id>/`) : `veilleur.log` (le veilleur, l'avertissement `ptrace_scope`), `controle.log` (les erreurs du conteneur de contrôle du secret, 64 Ko, lignes portant le jeton retirées),
  `docker-run.log` (l'échec d'un `docker run`), `pont-hote.log` (une ligne par appel du pont hôte) et `pont-hote.out` (sa sortie d'erreur). `sortie/claude.err` (64 Ko) n'existe qu'à la fin de la tâche.
- **Reste d'un incident** : un conteneur `tache-<id>` qui ne s'arrête pas est dit par la raison de la tâche (« à arrêter à la main (docker stop) ») ; `sudo docker ps --filter label=myiafactory.genre=agent` les liste.

## Limites connues

- **Projets homonymes.** Le bureau retrouve le projet d'un agent par le **nom du dossier** : deux projets du bureau de même nom de dossier n'ont **aucune** marque d'arrêt posée (l'arrêt sur le serveur a lieu quand même).
- **Réglage des places.** La commande de réglage des places du projet (`parallelisme`, qui écrit `agents_serveur_max` et l'ordre des lieux) peut être appelée par un **agent local** : il peut donc changer ces réglages du projet.
  Le **plafond d'abonnement** (`agents_abonnement_max`) n'est pas réglable par cette commande : il n'est écrit que par le bureau, dans son propre fichier.
- **Installation et recrutement.** L'installation (skill d'installation) et le recrutement d'agents **ne proposent pas encore d'agents serveur** : les places serveur et l'ordre des lieux se règlent à la main (bureau ou
  `factory.json`).
- **Pas de `.factory/recettes`.** Un agent serveur **ne peut pas livrer** `.factory/recettes` (ni rien sous `.factory`) : la branche serait gardée, non fusionnée. Les recettes se font au poste.
- **Flux et `claude.err`** n'existent qu'à la fin de la tâche : on ne peut pas suivre l'agent en direct, seulement l'état, la durée et les journaux de l'hôte.
- **Réseau ouvert** (voir « Sécurité ») et **accord permanent** de la recette sur émulateur : mêmes limites que la tranche A.

## Non vérifié sur un vrai serveur

Tout ce qui précède est vérifié par des tests simulés. À prouver sur le serveur réel (voir « Essais réels ») :

- **Node et Claude Code** lancés avec `--user <uid>:<gid>` **sans entrée dans `/etc/passwd`**, sur un système de fichiers racine en **lecture seule**, avec `HOME=/maison`.
- L'acceptation d'un jeton **`setup-token`** par `CLAUDE_CODE_OAUTH_TOKEN` en mode `-p` (et le déroulé exact de `claude setup-token` dans un conteneur sans navigateur : lien, code éventuel, affichage du jeton).
- Le **trafic sortant** du réseau `myiafactory-agents` sous les règles `ufw` du serveur (l'API de Claude passe-t-elle ?).
- L'accès des conteneurs aux **services de l'hôte** (`sshd`, `xrdp`) et à l'**adresse de métadonnées OVH** depuis le réseau des agents.
- `SO_PEERCRED` et l'**uid à travers Docker** (`userns-remap`) : le pair de la socket a-t-il bien l'uid de l'hôte ?
- La **socket du pont par montage** (`bind mount`) dans le conteneur, et l'**arrêt par groupe de processus** (`setsid`) du pont hôte.
- La **valeur réelle de `ptrace_scope`** du serveur et l'effet du **profil seccomp** par défaut de Docker sur `claude` et ses outils.
- La **durée du contrôle du secret** sur de gros paquets (le poste suit jusqu'à la durée de la tâche + 120 s ; le contrôle peut durer jusqu'à 15 min) ; son effet sur un arrêt.
- `git bundle unbundle` d'un **paquet mince** avec `alternates` sur `/travail` en lecture seule, dans le conteneur de contrôle.
- Le **budget mémoire** : émulateur 6 Go + 2 agents × 4 Go + l'hôte, sur les 62 Go du serveur.
- Le parcours de dossiers sans suivre de lien (**`O_NOFOLLOW`**) et les droits **0700 / 0600** sur le serveur réel.
- La fenêtre de **60 s** de `docker stop` : l'entrée conclut-elle (restes, paquet, `fin.json`) dans ce délai sur un vrai projet ?
- La **neutralisation des filtres** (`info/attributes`, `.gitattributes`) avec la version de Git du conteneur.
- **Flutter** : avec l'overlay du SDK entier, `flutter analyze` et `flutter test` passent à la main (2026-11-23, couche
  haute d'environ 76 Ko) ; restent `flutter pub get`, `analyze` et `test` dans le conteneur de l'agent lancé par
  l'enveloppe, la suppression du volume en fin de tâche, les bibliothèques système dont `flutter_tester` a besoin dans l'image (Ubuntu
  minimal) ; le nom exact de l'archive et la présence de la 3.47.1 dans `releases_linux.json`.
- **APK au serveur** : `flutter build apk --debug` dans l'agent (téléchargement de Gradle et des dépendances par le
  réseau de l'agent, durée, mémoire sous 4 Go, taille de `/maison/.gradle` et de `android-up`, chemin réel du JDK dans
  l'image, overlay du SDK Android).
- **Livrables rapatriés** (voir cette section) : le manifeste et l'envoi au vrai serveur (`stat`, `sha256sum`, `find -links`),
  la durée d'un APK de 50 à 150 Mo par `executer_vers_fichier`, le chemin réellement déclaré par l'agent dans son rapport, et le
  bouton « Télécharger » du bureau sur le fichier rapatrié.
