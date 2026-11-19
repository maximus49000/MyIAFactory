# Le serveur dédié OVH (plateforme)

Mise en place, depuis le poste Windows, d'un serveur dédié OVH : Ubuntu LTS, accès SSH par clé, durcissement, Docker, puis
les images d'outils (Unity, Android/Gradle, agent). Conception : [`2026-11-19-serveur-ovh-plateforme-design.md`](superpowers/specs/2026-11-19-serveur-ovh-plateforme-design.md).
Le reste de l'application ne dépend pas du serveur : s'il ou OVH est injoignable, rien d'autre ne casse.

## Ce que veut dire « prêt »

Sept étapes, plus une huitième facultative, rejouables, chacune lancée seulement quand la précédente est « fait » (la
huitième, quand les étapes 1 à 6 le sont : la licence, étape 7, ne la bloque pas) :

1. **Lecture** du serveur chez OVH (API).
2. **Système** : toute version Ubuntu serveur reconnue (22.04, 24.04, 26.04 et anciennes, variantes comprises) n'est
   jamais réinstallée ; tout autre système (Debian, Ubuntu non LTS, serveur vierge) est réinstallé en Ubuntu 24.04 LTS, avec accord.
3. **Accès SSH** par une clé dédiée (`~/MyIAFactory/id_ed25519_myiafactory`), utilisateur `ubuntu`. La clé est générée
   sur le poste **avant** la réinstallation (étape 2) : sa partie publique part dans la requête de réinstallation
   (`customizations.sshKey`), aucune clé n'est enregistrée à part chez OVH.
4. **Durcissement** : clé seule, pare-feu limité à SSH, mises à jour de sécurité automatiques.
5. **Docker** installé.
6. **Images** : Unity `unityci/editor:ubuntu-6000.6.7f1-android-4.0.0` (le projet se construit avec Unity 6000.6.7f1),
   image Android/Gradle et image de l'agent, volumes de cache Gradle et Unity.
7. **Licence Unity** : facultative.
8. **Session graphique (Unity Hub)** : facultative, jamais lancée sans le drapeau `--bureau-distant` (voir « Session
   graphique »).

**Prêt = étapes 1 à 6.** Sans la licence (étape 7), le serveur est « prêt, sans Unity » : cette mention ne dépend que de
la licence, jamais de la session graphique, même après une connexion à Unity Hub. Rien ne transporte la licence de Hub
(dossier `~/.local/share/unity3d/...` de l'utilisateur du serveur) vers les conteneurs de compilation : se connecter à Hub ne
rend donc pas, à lui seul, les compilations Docker sous licence (limite, voir « Utiliser Unity Hub »). L'indicateur
`serveur_disponible` du bureau suit l'état « prêt ».

## 1. Créer les clés API OVH

Créez le jeton sur <https://eu.api.ovh.com/createToken/> (validité : illimitée) avec ces droits, limités à ce seul
serveur (remplacez `<nom>` par son nom, `nsXXXX.ip-…eu`) :

```
GET  /dedicated/server/<nom>
GET  /dedicated/server/<nom>/*
POST /dedicated/server/<nom>/reinstall
```

`GET /dedicated/server/<nom>/*` couvre les modèles d'installation (`install/compatibleTemplates`) et le suivi des tâches
(`task/*`) ; `GET /dedicated/server/<nom>` (sans `/*`) est la lecture du serveur lui-même. Aucun droit sur `/me/sshKey`
n'est plus nécessaire.

Un jeton trop étroit donne une erreur HTTP 403 « This call has not been granted ». Variante la plus simple qui marche :
`GET /*` et `POST /*`, le temps de l'installation seulement.

**Les clés ne vont jamais dans le dépôt, ni dans une conversation d'agent.** Elles ont été collées une fois pendant le
développement : révoquez-les et recréez-les. Après l'installation, deux options : **garder un jeton en lecture seule**
(`GET /dedicated/server/<nom>` seulement), avec lequel la carte reste à jour ; ou **tout révoquer** : la plateforme continue
de fonctionner à partir de son cache (adresse du serveur, « OVH injoignable : adresse en cache »), mais ne peut plus ni se
rafraîchir ni réinstaller. Une panne d'OVH ou un jeton révoqué ne fait jamais passer en « non prêt » un serveur déjà installé.

## 2. Placer les fichiers dans `~/MyIAFactory`

`C:\Users\<nom>\MyIAFactory\ovh.json` (obligatoire) :

```json
{"point": "ovh-eu", "cle_app": "…", "secret": "…", "consommateur": "…", "serveur": "nsXXXX.ip-…eu"}
```

Le fichier doit être en UTF-8 (avec ou sans BOM). **PowerShell 5.1 (`Out-File`, `>`) écrit en UTF-16, illisible ici.**
Écrivez-le ainsi :

```powershell
New-Item -ItemType Directory -Force "$HOME\MyIAFactory" | Out-Null
$json = '{"point": "ovh-eu", "cle_app": "…", "secret": "…", "consommateur": "…", "serveur": "nsXXXX.ip-…eu"}'
[System.IO.File]::WriteAllText("$HOME\MyIAFactory\ovh.json", $json, (New-Object System.Text.UTF8Encoding $false))
```

`unity.ulf` (facultatif) : voir « Licence Unity ».

## 3. Lancer

```
py -3.12 lancer.py plateforme etat
py -3.12 lancer.py plateforme installer
py -3.12 lancer.py plateforme installer --accord-reinstallation
py -3.12 lancer.py plateforme verifier
py -3.12 lancer.py plateforme installer --bureau-distant
py -3.12 lancer.py plateforme bureau-distant
```

- `etat` : relit le cache `plateforme.json`, ne contacte rien.
- `installer` : enchaîne les étapes en reprenant où la dernière exécution s'est arrêtée.
- `verifier` : constate l'état réel du serveur sans rien modifier (seule exception : il peut créer la clé SSH dédiée
  locale si elle n'existe pas encore ; rien n'est écrit chez OVH ni sur le serveur).
- `--dossier <d>` remplace `~/MyIAFactory` (essais).
- `--bureau-distant` (avec `installer`) : lance aussi l'étape 8 facultative ; `bureau-distant` (sans `installer`) ouvre la
  session déjà installée. Les autres sous-commandes acceptent le drapeau sans l'utiliser : il n'a d'effet qu'avec
  `installer`. Voir « Session graphique (Unity Hub) ».
- Sortie : l'état en JSON (secrets masqués). Code de sortie 0 = prêt et rien de bloqué ; 1 = bloqué ou pas prêt ;
  2 = mauvais usage. Un blocage de l'étape facultative 8 donne aussi le code 1, et `etat` donne 1 tant que le serveur
  n'est pas « prêt ». (La commande `bureau-distant` a ses propres codes, voir plus bas.)

Le même parcours existe dans le bureau : carte **« Serveur »** du panneau Direction (étapes, raison et geste à faire en cas
de blocage, suivi de l'installation, case d'accord d'effacement).

## Sécurité : la réinstallation efface le disque

- Elle n'a lieu que si l'OS présent n'est pas une version Ubuntu LTS reconnue (22.04, 24.04, 26.04 et anciennes, variantes
  `-withapp` comprises : le nom commence par `ubuntu`, deux chiffres d'année paire et `04`) ou si le serveur est vierge, et **seulement avec un accord
  explicite à chaque exécution** : `--accord-reinstallation` en ligne de commande, ou la case cochée dans la carte
  « Serveur » (accord à usage unique). Seul `true` strict compte.
- Sans accord, l'étape passe en « bloqué » et rien n'est effacé.
- Le système cible est fixe : **Ubuntu 24.04 LTS** (`ubuntu2404-server_64`). S'il n'est pas dans la liste des modèles
  compatibles d'OVH pour ce serveur, une erreur le dit et la réinstallation n'est **pas** tentée.
- La requête est `POST /dedicated/server/<nom>/reinstall` avec `operatingSystem` et la clé publique SSH dans
  `customizations.sshKey` ; aucune disposition de disques n'est envoyée (valeur par défaut d'OVH). Un marqueur « demande »
  est écrit dans `plateforme.json` avant la requête et l'identifiant de tâche juste après : une relance attend cette tâche
  au lieu de réinstaller de nouveau. Si la dernière vérification avant la requête (lecture des modèles) échoue, la marque est
  effacée (rien n'est parti) et il suffit de relancer ; une erreur de la requête elle-même (délai, 5xx) la conserve, un refus
  net d'OVH (4xx) l'efface.
- Une empreinte SSH changée n'est oubliée **que** si la réinstallation vient d'avoir lieu dans cette exécution (ou si une
  tâche notée au cache vient de se terminer) ; sinon la connexion est refusée (risque d'interception), voir dépannage.
- Une réinstallation prend plusieurs minutes (budget d'attente : 40 minutes).
- Après toute réinstallation ou tout changement de système, les étapes suivantes (accès SSH, durcissement, Docker, images,
  licence) sont remises « à faire ».

## Licence Unity (facultative)

L'activation manuelle par fichier `.alf` n'est pas prise en charge par Unity pour la licence **Personal** (voir
<https://docs.unity3d.com/6000.6/Documentation/Manual/ManualActivationGuide.html> et game-ci/unity-test-runner#235).
Le chemin retenu :

1. Activez Unity dans Unity Hub sur votre PC.
2. Copiez le fichier de licence, en général `C:\ProgramData\Unity\Unity_lic.ulf`, vers `~/MyIAFactory/unity.ulf`.
3. Relancez `installer` : l'étape 7 l'envoie au serveur par l'entrée standard (jamais en argument, jamais réaffichée).

Avec le nouveau client de licences d'Unity, ce fichier peut ne pas exister. Il faut alors une licence Pro/Plus à numéro de
série, ou une session graphique du Hub sur le serveur (voir la section suivante). Sans licence, le serveur reste « prêt,
sans Unity ». Les conditions d'usage de la licence en compilation automatique sont à vérifier par le Directeur.

## Session graphique (Unity Hub)

**Pourquoi.** Unity Personal ne s'active plus par fichier `.alf` : il faut se connecter à Unity Hub, qui exige un navigateur,
et le serveur n'a pas d'écran. L'étape facultative 8 installe un bureau léger où Hub se lance tout seul ; vous vous y
connectez une fois à votre compte Unity, et la licence reste sur le serveur.

**Rien de ceci n'a encore été exécuté sur le vrai serveur** (code et script testés par simulation seulement). La première
exécution réelle change le serveur et demande l'accord explicite du Directeur : c'est une action à part. Voir « Non
vérifié ».

### Installer

```
py -3.12 lancer.py plateforme installer --bureau-distant
```

Sans le drapeau, l'étape 8 n'est jamais lancée (« Facultative : non demandée ») et ne change rien à « prêt » ; avec lui, elle
vient après les étapes 1 à 6 (la licence, étape 7, ne la bloque pas) et un blocage de l'étape 8 donne le code de sortie 1.
Sur le serveur, elle installe XFCE, xrdp (à l'écoute sur `127.0.0.1:3389` seulement), Mozilla Firefox (dépôt de Mozilla,
hors snap), Unity Hub (dépôt officiel d'Unity), et fait démarrer Hub à l'ouverture de la session. Les clés des deux dépôts
sont retéléchargées et validées à chaque exécution ; si l'une est introuvable, vide ou illisible, l'étape se bloque. Une liste
de sources n'est retirée que si sa propre clé manque ou est invalide (pour ne pas casser les `apt-get update` suivants du
serveur) ; si une clé valide et sa liste existent déjà d'une exécution réussie, les deux sont conservées telles quelles (le
Firefox de Mozilla reste épinglé et le paquet snap d'Ubuntu ne le remplace pas), et le détail le dit. Le paquet xrdp démarre
d'office sur toutes les interfaces : l'étape l'arrête aussitôt après l'installation et le laisse arrêté à tout blocage qui
précède la preuve d'écoute en boucle locale ; il ne redémarre qu'une fois configuré sur `127.0.0.1`. Les contrôles de clé
utilisent un dossier gpg temporaire supprimé ensuite (aucun `/root/.gnupg`). Coût **estimé** (non mesuré) : environ 1 Go de
mémoire pendant la session, 2 à 3 Go de disque ; budget d'attente de l'étape : 25 minutes.

**Rejouer.** Relancer `installer --bureau-distant` rejoue l'étape 8 même si elle est déjà « fait » : elle réapplique le mot de
passe du fichier `bureau-distant.txt`, y compris celui que vous y avez mis vous-même (les preuves passent avant). Les étapes
1 à 6 ne sont pas refaites et le serveur n'est jamais réinstallé. Sans le drapeau, une étape 8 déjà « fait » reste telle
quelle et le mot de passe n'est jamais changé.

L'étape refuse de s'exécuter (« bloqué », rien de modifié) si elle tourne en root, ou si SSH n'a pas **explicitement**
`passwordauthentication no` et `kbdinteractiveauthentication no` : lancez d'abord le durcissement (étape 4). Le mot de passe
de session n'est posé qu'en dernier, une fois prouvés : xrdp à l'écoute sur la boucle locale seule, aucune règle `ufw` pour
3389, `unityhub`, `startxfce4` et `firefox` présents, Firefox venant du dépôt Mozilla et non du lanceur snap.

### Ouvrir la session

```
py -3.12 lancer.py plateforme bureau-distant
```

Ouvre un tunnel `ssh -N -L 127.0.0.1:<port>:127.0.0.1:3389` avec la clé dédiée (port local 33890 s'il est libre, sinon un
port libre choisi par le système), écrit `bureau-distant.rdp` (utilisateur `ubuntu`, **sans mot de passe**, saisie demandée
par Windows), lance `mstsc`, et ferme le tunnel à la fermeture de la fenêtre (voir « Non vérifié » ci-dessous). Il faut que
l'étape 8 soit « fait » dans le cache (sinon : « Installez d'abord la session »). Dans la fenêtre de connexion de Windows,
saisissez l'utilisateur `ubuntu` et le mot de passe de `bureau-distant.txt` ; avec xrdp, l'invite peut être l'écran de
connexion propre à xrdp. Windows signale un certificat auto-signé : acceptez-le. Fermer la fenêtre ne ferme **pas** la
session xrdp côté serveur : elle reste active (Unity Hub continue d'y consommer de la mémoire) ; déconnectez-vous depuis la
session XFCE pour la libérer.

**Non vérifié :** que le tunnel se ferme bien à la fermeture de la fenêtre, ce qui suppose que `mstsc` bloque jusqu'à cette
fermeture (probable, non constaté) ; le tunnel porte aussi un contrôle de vie SSH (`ServerAliveInterval=30`). Autres
risques : `apt-get install` peut faire redémarrer des services par `needrestart` (dont `ssh` et `docker`) : lancez l'étape
quand aucune compilation n'est en cours. Après un `apt upgrade` ultérieur de xrdp, vérifiez `ss -ltn | grep 3389` : un
`xrdp.ini` fourni par le mainteneur pourrait de nouveau écouter sur `0.0.0.0`, et seul `ufw` resterait devant ; `verifier`
ne le prouve pas à nouveau.

Codes de sortie : 0 = session ouverte puis fermée ; 1 = échec (étape 8 pas faite, adresse du cache invalide, `ssh` introuvable,
tunnel non ouvert, ou Ctrl-C) ; 2 = plateforme non Windows, ou `mstsc` introuvable.

### Le mot de passe de session

- Il vit dans `~/MyIAFactory/bureau-distant.txt` (UTF-8, droits réservés à l'utilisateur, écriture atomique) et **nulle
  part ailleurs** : jamais dans `plateforme.json`, l'état affiché ou les journaux ; il part au serveur par l'entrée standard
  SSH, jamais en argument.
- Il est généré (24 caractères) seulement si le fichier est absent ou si sa première ligne a moins de 16 caractères
  (l'étape le dit alors dans son détail). Un fichier existant assez long est repris tel quel : vous pouvez y mettre le
  vôtre, puis relancer `installer --bureau-distant` pour que le serveur le prenne en compte (sans le drapeau, le mot de passe
  du serveur n'est jamais changé).
- Un fichier qui n'est pas du texte UTF-8 (UTF-16 notamment) met l'étape 8 en « bloqué » et **n'est jamais écrasé**.
  PowerShell 5.1 écrit en UTF-16 avec `>` ou `Out-File` ; utilisez `Set-Content -Encoding utf8` ou `Out-File -Encoding utf8`,
  ou supprimez le fichier pour en faire générer un nouveau.

### Utiliser Unity Hub

1. Ouvrez la session ; Hub se lance seul. Connectez-vous **une fois** à votre compte Unity.
2. Vérifiez dans Hub que la licence est active (Personal).
3. Si Hub ne s'affiche pas, lancez `unityhub` depuis le terminal XFCE ; une erreur de sandbox peut demander
   `--no-sandbox` (non vérifié).

**Limite :** rien ne transporte la licence de Hub (dossier `~/.local/share/unity3d/...` de l'utilisateur du serveur) vers les
conteneurs de compilation, qui utilisent leur propre licence (étape 7) : se connecter à Hub ne rend pas, à lui seul, les
compilations Docker sous licence, et le libellé « prêt, sans Unity » ne change pas. **Non vérifié :** qu'une licence obtenue
ainsi serve aux compilations sans écran. `plateforme verifier` n'affirme rien sur la licence.

### Sécurité

- xrdp écoute sur `127.0.0.1:3389` du serveur seulement ; le pare-feu reste limité au port 22 (aucune règle ajoutée,
  une règle `ufw` pour 3389 bloque l'étape). Si l'étape se bloque avant la preuve d'écoute en boucle locale, xrdp est laissé
  **arrêté** (jamais exposé sur toutes les interfaces derrière `ufw` seul) ; un blocage plus tardif (règle `ufw`, binaires,
  Firefox, mot de passe) le laisse démarré, mais déjà prouvé en boucle locale.
- La connexion SSH par mot de passe reste coupée : le mot de passe de session ne sert **que** par le tunnel, jamais pour SSH
  (c'est pourquoi l'étape refuse de s'exécuter sans ces deux réglages explicites).
- Le port local du tunnel n'est ouvert que sur `127.0.0.1` du poste, le temps de la session.

### Dépannage de la session

- **« L'empreinte du serveur a changé »** : le tunnel refuse par sécurité et n'oublie **jamais** l'empreinte. Si le serveur a
  bien été réinstallé, exécutez `ssh-keygen -R <adresse du serveur>` puis relancez ; sinon, ne continuez pas.
- **« Le tunnel SSH ne s'est pas ouvert »** : serveur injoignable, clé refusée ou port local pris ; lancez `plateforme verifier`.
- **« ssh est introuvable »** : activez le client OpenSSH de Windows (Paramètres, Applications, Fonctionnalités facultatives).
- **« mstsc introuvable (Bureau à distance de Windows). »** (code 2) : le Bureau à distance de Windows manque. Hors Windows le
  message est autre, avec le même code 2 : « Le client « mstsc » (Bureau à distance) n'existe que sous Windows : la session
  ne peut pas s'ouvrir d'ici. »
- **Étape 8 « bloqué »** : lisez le détail et le geste dans la carte ou la sortie JSON ; messages possibles : fichier de mot
  de passe illisible (voir ci-dessus), SSH par mot de passe pas explicitement coupé (lancez le durcissement), exécution en root,
  installation de XFCE/xrdp ou des paquets Firefox/Unity Hub impossible, clé de dépôt introuvable, xrdp n'écoutant pas sur
  3389 ou ailleurs que sur `127.0.0.1`, règle `ufw` pour 3389, Firefox venant du snap d'Ubuntu.

## Matériel et limites

Xeon E5-1650v4 (6 cœurs / 12 threads), 64 Go de mémoire, 2 × 4 To en disques mécaniques (RAID logiciel d'OVH, conservé).
Les disques sont lents : les caches Gradle et Unity sont dans des volumes persistants. Le script bloque l'étape des
images si moins de **20 Go** sont libres.

Une limite de compilations simultanées (`compilations_max`, 2 par défaut) est prévue par la conception mais
**n'existe pas dans le code** : elle reste à faire.

## Fichiers dans `~/MyIAFactory`

| Fichier | Rôle |
|---|---|
| `ovh.json`, `unity.ulf` | vos secrets, à ne jamais committer |
| `id_ed25519_myiafactory`, `.pub` | clé SSH dédiée, générée sur le poste à l'étape 2 (avant une réinstallation) ou à l'étape 3 |
| `plateforme.json` | cache de l'état connu, sans secret ; l'état réel est relu à la demande |
| `plateforme.lock` | verrou : une seule installation à la fois |
| `bureau-distant.txt` | mot de passe de la session graphique (étape 8), à ne jamais committer |
| `bureau-distant.rdp` | fichier de connexion écrit à l'ouverture de la session, sans mot de passe |

## Dépannage

- **HTTP 403 « This call has not been granted »** : jeton OVH trop étroit ; recréez-le (droits ci-dessus ou `GET /*` et
  `POST /*` le temps de l'installation).
- **Étape « Interrompu : à reprendre »** : le bureau a été fermé ou a planté pendant une étape ; relancez « Mettre en place /
  reprendre » (ou `installer`), l'étape reprend là où elle s'était arrêtée.
- **SSH refusé pendant la réinstallation** : normal tant que le serveur redémarre ; l'étape attend, relancez `installer`
  si elle a expiré. Si le message dit que le serveur « ne répond pas en SSH avec la clé dédiée » et que le blocage
  persiste, ajoutez `id_ed25519_myiafactory.pub` à `~/.ssh/authorized_keys` du serveur.
- **« HOST IDENTIFICATION HAS CHANGED » / « L'empreinte SSH du serveur a changé »** : si la plateforme vient elle-même de
  réinstaller le serveur (ou de voir se terminer la tâche de réinstallation notée au cache), elle oublie l'ancienne
  empreinte toute seule (que le changement soit vu aux premiers essais ou pendant l'attente du redémarrage), puis
  réessaie l'attente une fois ; si l'empreinte change encore, l'exécution s'arrête. Sinon elle refuse (ce peut être une interception) : si vous savez que le serveur a été
  réinstallé (par exemple depuis l'espace client OVH), supprimez l'ancienne empreinte vous-même
  (`ssh-keygen -R <adresse du serveur>`) puis relancez. Ce cas n'est jamais présenté comme un problème de
  `authorized_keys`.
- **« Réponse illisible du serveur (code 255) »** : le pare-feu `ufw limit` peut refuser des sessions SSH trop rapprochées ;
  relancez simplement l'installation quelques secondes plus tard.
- **Disque presque plein (moins de 20 Go libres)** : l'étape images est bloquée ; libérez de la place (`docker system prune`
  sur le serveur) puis relancez.
- **Verrou resté après un plantage** : un verrou dont le processus est mort est repris tout seul (un verrou vide ou illisible
  de moins de 30 secondes est considéré comme tenu). Si « Une installation est déjà en cours » persiste alors qu'aucune ne
  tourne : vérifiez qu'aucune fenêtre ne lance `lancer.py plateforme installer` et qu'aucun bureau n'est en train
  d'installer, puis supprimez le fichier `~/MyIAFactory/plateforme.lock`.
- **Réinstallation demandée mais tâche inconnue** (l'étape « Système » dit qu'une réinstallation a été demandée sans
  identifiant de tâche ; la plateforme refuse de réinstaller de nouveau) :
  1. ouvrez l'espace client OVH, Bare Metal Cloud, votre serveur, onglet **Tâches** : cherchez une tâche d'installation
     récente ;
  2. si une tâche est en cours, attendez qu'elle se termine ; si elle est terminée avec succès, ou s'il n'y en a aucune
     (la demande n'est pas partie), passez à l'étape 3 ;
  3. fermez le bureau et toute installation, ouvrez `~/MyIAFactory/plateforme.json` dans un éditeur de texte et remplacez
     `"demande": true` par `"demande": null` (ne supprimez PAS la ligne : le fichier deviendrait du JSON invalide et l'état
     en cache serait perdu) ; ne touchez à rien d'autre ;
  4. relancez l'installation : si le système est déjà Ubuntu LTS, la suite continue ; sinon l'accord d'effacement est de
     nouveau demandé.
- **Enfermé dehors (clé SSH perdue après le durcissement)** : après le durcissement, la clé du poste est le seul accès.
  Sauvegardez dès maintenant `~/MyIAFactory/id_ed25519_myiafactory` (et `.pub`) hors du poste, et, si vous le souhaitez,
  ajoutez aussi une clé personnelle à `~/.ssh/authorized_keys` du serveur. Si l'accès est perdu, la piste habituelle (**non
  vérifiée sur ce serveur**, voir « Non vérifié ») : espace client OVH, votre serveur, **Netboot** puis mode **rescue**
  (redémarrage sur un système de secours ; OVH fournit en général des identifiants temporaires, par courriel ou dans
  l'espace client) ; connectez-vous au système de secours, identifiez et montez le disque système (la partition et la
  disposition dépendent du serveur : `lsblk` ou `cat /proc/mdstat` pour les repérer ; avec la disposition par défaut d'OVH il
  peut s'agir d'une partition RAID de type `/dev/md*`), ajoutez votre clé publique à
  `<disque>/home/ubuntu/.ssh/authorized_keys`, rebasculez le netboot sur le disque dur et redémarrez.

## Non vérifié

**Vérifié le 2026-11-19** (lectures seules, avec un vrai jeton) : `GET /dedicated/server/<nom>` (système `none_64`, état
`ok`), `GET /dedicated/server/<nom>/install/compatibleTemplates` (la liste contient `ubuntu2404-server_64`) et le schéma
public de l'API (la route `POST /install/start` n'existe plus ; la route actuelle est `POST /reinstall`).

Ce qui n'a été testé qu'avec des simulations, jamais sur un vrai serveur :

- le corps de la **nouvelle** requête `POST /reinstall` : seuls son schéma et la liste des modèles ont été vérifiés, la
  requête elle-même n'a jamais été envoyée ;
- les noms des statuts de tâche OVH (`init`, `todo`, `doing`, `done`, `error`, `cancelled`, `customerError`, `ovhError`),
  tirés du schéma, jamais observés en réel ;
- la **procédure de secours « enfermé dehors »** (mode rescue OVH, identifiants temporaires, nom de la partition à monter,
  modification d'`authorized_keys` depuis le système de secours) : décrite d'après la documentation générale d'OVH, jamais
  essayée ici ;
- la disposition des disques / le RAID : aucun paramètre `storage` n'est envoyé, c'est la disposition par défaut d'OVH ;
- `ufw limit` (limitation de débit) peut refuser des sessions SSH trop rapprochées (« Réponse illisible, code 255 ») :
  relancez simplement ;
- la **session graphique** (étape 8 et commande `bureau-distant`), jamais exécutée sur un vrai serveur : le nom du paquet
  `unityhub`, l'adresse du dépôt et la clé d'Unity Hub pour Ubuntu 24.04 ; la preuve « Firefox hors snap » (lecture de
  `apt-cache policy firefox` et du chemin du binaire) ; xrdp avec XFCE sur 24.04 ; le démarrage automatique de Hub dans une
  session xrdp (un `--no-sandbox` peut être nécessaire) ; les exécutions réelles de `ssh` et `mstsc` ; et surtout si la
  connexion à Hub donne une licence utilisable en compilation sans écran ;
- le déroulement réel de la réinstallation OVH, les marqueurs du journal d'activation de la licence, l'adresse de
  téléchargement des outils en ligne de commande Android, et l'utilisateur SSH `ubuntu`.

## À venir (non réalisé)

- Un bouton d'accès direct : terminal SSH dans le bureau. La session graphique (étape 8, xrdp par tunnel SSH) existe
  désormais en ligne de commande ; un bouton de la carte « Serveur » pour l'ouvrir reste à faire.
- Une image Unreal Engine. Limites : pas de GPU sur ce serveur ; un PC de 7,4 Go ne fait pas tourner l'éditeur
  confortablement ; pistes : serveurs GPU OVH ou instances GPU horaires du cloud public.
- L'activation du lieu `serveur` dans le routage de `bureau/deport.py` (le drapeau `serveur_disponible` existe ; lancer
  des tâches sur le serveur est une demande ultérieure).
- Le réglage `compilations_max`.
