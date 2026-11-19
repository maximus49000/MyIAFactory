# Le serveur dédié OVH (plateforme)

Mise en place, depuis le poste Windows, d'un serveur dédié OVH : Ubuntu LTS, accès SSH par clé, durcissement, Docker, puis
les images d'outils (Unity, Android/Gradle, agent). Conception : [`2026-11-19-serveur-ovh-plateforme-design.md`](superpowers/specs/2026-11-19-serveur-ovh-plateforme-design.md).
Le reste de l'application ne dépend pas du serveur : s'il ou OVH est injoignable, rien d'autre ne casse.

## Ce que veut dire « prêt »

Sept étapes, rejouables, chacune lancée seulement quand la précédente est « fait » :

1. **Lecture** du serveur chez OVH (API).
2. **Système** : Ubuntu LTS (déjà présent, ou réinstallé avec accord).
3. **Accès SSH** par une clé dédiée (`~/MyIAFactory/id_ed25519_myiafactory`), utilisateur `ubuntu`.
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
POST /dedicated/server/<nom>/install/start
GET  /me/sshKey*
POST /me/sshKey
```

Un jeton trop étroit donne une erreur HTTP 403 « This call has not been granted ». Variante la plus simple qui marche :
`GET /*` et `POST /*`, **à révoquer après l'installation**.

**Les clés ne vont jamais dans le dépôt, ni dans une conversation d'agent.** Elles ont été collées une fois pendant le
développement : révoquez-les et recréez-les après l'installation.

## 2. Placer les fichiers dans `~/MyIAFactory`

`C:\Users\<nom>\MyIAFactory\ovh.json` (obligatoire) :

```json
{"point": "ovh-eu", "cle_app": "…", "secret": "…", "consommateur": "…", "serveur": "nsXXXX.ip-…eu"}
```

Le fichier doit être en UTF-8 (avec ou sans BOM). **PowerShell 5.1 (`Out-File`, `>`) écrit en UTF-16, illisible ici.**
Écrivez-le ainsi :

```powershell
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
- `verifier` : constate l'état réel du serveur sans rien modifier.
- `--dossier <d>` remplace `~/MyIAFactory` (essais).
- Sortie : l'état en JSON (secrets masqués). Code de sortie 0 = prêt et rien de bloqué ; 1 = bloqué ou pas prêt ;
  2 = mauvais usage.

Le même parcours existe dans le bureau : carte **« Serveur »** du panneau Direction (étapes, raison et geste à faire en cas
de blocage, suivi de l'installation, case d'accord d'effacement).

## Sécurité : la réinstallation efface le disque

- Elle n'a lieu que si l'OS présent n'est pas Ubuntu LTS (ou si le serveur est vierge), et **seulement avec un accord
  explicite à chaque exécution** : `--accord-reinstallation` en ligne de commande, ou la case cochée dans la carte
  « Serveur » (accord à usage unique). Seul `true` strict compte.
- Sans accord, l'étape passe en « bloqué » et rien n'est effacé.
- Le même accord autorise à oublier l'ancienne empreinte SSH quand elle a changé (voir dépannage).
- Une réinstallation prend plusieurs minutes (budget d'attente : 40 minutes).

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
| `id_ed25519_myiafactory`, `.pub` | clé SSH dédiée, générée à l'étape 3 |
| `plateforme.json` | cache de l'état connu, sans secret ; l'état réel est relu à la demande |
| `plateforme.lock` | verrou : une seule installation à la fois |

## Dépannage

- **HTTP 403 « This call has not been granted »** : jeton OVH trop étroit ; recréez-le (droits ci-dessus ou `GET /*` et
  `POST /*` le temps de l'installation).
- **SSH refusé pendant la réinstallation** : normal tant que le serveur redémarre ; l'étape attend, relancez `installer`
  si elle a expiré. Si le blocage persiste, ajoutez `id_ed25519_myiafactory.pub` à `~/.ssh/authorized_keys` du serveur.
- **« HOST IDENTIFICATION HAS CHANGED »** : le serveur a été réinstallé. Relancez avec `--accord-reinstallation` pour oublier
  l'ancienne empreinte.
- **Disque presque plein (moins de 20 Go libres)** : l'étape images est bloquée ; libérez de la place (`docker system prune`
  sur le serveur) puis relancez.
- **Verrou resté après un plantage** : un verrou dont le processus est mort est repris tout seul. Si « Une installation est
  déjà en cours » persiste alors qu'aucune ne tourne, supprimez `~/MyIAFactory/plateforme.lock`.

## Non vérifié

Ce qui n'a été testé qu'avec des simulations, jamais sur un vrai serveur : le déroulement réel de la réinstallation OVH,
les marqueurs du journal d'activation de la licence, l'adresse de téléchargement des outils en ligne de commande Android,
et l'utilisateur SSH `ubuntu`.

## À venir (non réalisé)

- Un bouton d'accès direct : terminal SSH et vue graphique de la machine par un tunnel SSH (demande une étape
  facultative de bureau léger avec VNC ou xrdp).
- Une image Unreal Engine. Limites : pas de GPU sur ce serveur ; un PC de 7,4 Go ne fait pas tourner l'éditeur
  confortablement ; pistes : serveurs GPU OVH ou instances GPU horaires du cloud public.
- L'activation du lieu `serveur` dans le routage de `bureau/deport.py` (le drapeau `serveur_disponible` existe ; lancer
  des tâches sur le serveur est une demande ultérieure).
- Le réglage `compilations_max`.
