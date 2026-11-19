# Le serveur dédié OVH (plateforme)

Mise en place, depuis le poste Windows, d'un serveur dédié OVH : Ubuntu LTS, accès SSH par clé, durcissement, Docker, puis
les images d'outils (Unity, Android/Gradle, agent). Conception : [`2026-11-19-serveur-ovh-plateforme-design.md`](superpowers/specs/2026-11-19-serveur-ovh-plateforme-design.md).
Le reste de l'application ne dépend pas du serveur : s'il ou OVH est injoignable, rien d'autre ne casse.

## Ce que veut dire « prêt »

Sept étapes, rejouables, chacune lancée seulement quand la précédente est « fait » :

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

**Prêt = étapes 1 à 6.** Sans la licence, le serveur est « prêt, sans Unity ». L'indicateur `serveur_disponible` du bureau
suit cet état.

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
```

- `etat` : relit le cache `plateforme.json`, ne contacte rien.
- `installer` : enchaîne les étapes en reprenant où la dernière exécution s'est arrêtée.
- `verifier` : constate l'état réel du serveur sans rien modifier (seule exception : il peut créer la clé SSH dédiée
  locale si elle n'existe pas encore ; rien n'est écrit chez OVH ni sur le serveur).
- `--dossier <d>` remplace `~/MyIAFactory` (essais).
- Sortie : l'état en JSON (secrets masqués). Code de sortie 0 = prêt et rien de bloqué ; 1 = bloqué ou pas prêt ;
  2 = mauvais usage.

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
série, ou une session graphique du Hub sur le serveur. Sans licence, le serveur reste « prêt, sans Unity ». Les conditions
d'usage de la licence en compilation automatique sont à vérifier par le Directeur.

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
- le déroulement réel de la réinstallation OVH, les marqueurs du journal d'activation de la licence, l'adresse de
  téléchargement des outils en ligne de commande Android, et l'utilisateur SSH `ubuntu`.

## À venir (non réalisé)

- Un bouton d'accès direct : terminal SSH et vue graphique de la machine par un tunnel SSH (demande une étape
  facultative de bureau léger avec VNC ou xrdp).
- Une image Unreal Engine. Limites : pas de GPU sur ce serveur ; un PC de 7,4 Go ne fait pas tourner l'éditeur
  confortablement ; pistes : serveurs GPU OVH ou instances GPU horaires du cloud public.
- L'activation du lieu `serveur` dans le routage de `bureau/deport.py` (le drapeau `serveur_disponible` existe ; lancer
  des tâches sur le serveur est une demande ultérieure).
- Le réglage `compilations_max`.
