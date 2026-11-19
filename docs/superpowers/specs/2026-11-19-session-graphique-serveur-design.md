# Session graphique sur le serveur OVH : Unity Hub lancé par défaut (conception courte)

## Pourquoi
Unity Personal ne s'active plus par fichier de demande (`.alf`) : Unity veut une connexion à Unity Hub, qui exige un navigateur.
Le serveur n'a pas d'écran. Le Directeur veut une **session graphique sur le serveur où Unity Hub se lance tout seul**, pour s'y
connecter une fois à son compte Unity ; la licence reste alors sur le serveur. Cette session servira aussi de « vue de la machine »
(demande ultérieure : bouton d'accès SSH + visuel).

## Buts
- Une étape facultative « Session graphique » de la plateforme (étape 8) qui installe un bureau léger, un navigateur et Unity Hub, et
  fait démarrer Hub à l'ouverture de la session.
- Une commande `py -3.12 lancer.py plateforme bureau-distant` qui ouvre le tunnel SSH et le client Bureau à distance de Windows.
- Rien d'exposé sur Internet : le pare-feu reste sur le port 22 seul.

## Hors-buts
- Le bouton du bureau MyIAFactory (suite de la demande « accès SSH + visuel »), le terminal SSH, plusieurs utilisateurs, le son.
- Garantir que la connexion à Hub donne une licence Personal utilisable en compilation : à constater sur place (voir « Non vérifié »).
- Unreal Engine.

## À éviter
- Ouvrir un port public (RDP écoute sur 127.0.0.1 du serveur seulement).
- Un mot de passe dans le cache, les journaux, le dépôt ou l'état du bureau.
- Que l'étape 8 change ce que veut dire « prêt » : « prêt » reste les étapes 1 à 6 ; l'étape 8 ne se lance que sur demande.
- Casser le durcissement : la connexion SSH par mot de passe reste coupée.

## Approches considérées (choisie par le Directeur : bureau à distance Windows)
A. **xrdp + tunnel SSH + client Windows (mstsc)** : rien à installer sur le PC, fluide, copier-coller. *Retenue.*
B. noVNC dans une page du bureau : plus intégré, plus de code, moins fluide.
C. VNC avec un client à installer : un programme de plus.

## Conception
1. **Étape 8 `bureau_distant`** (script `serveur_ovh/mise_en_place.sh --etape bureau_distant`, même contrat JSON que les autres, rejouable) :
   XFCE minimal, xrdp, navigateur Firefox (version vérifiable hors snap), Unity Hub depuis le dépôt officiel d'Unity, lancement automatique de
   Hub (`~/.config/autostart`), xrdp lié à `127.0.0.1:3389`.
2. **Accès** : tunnel `ssh -N -L 33890:127.0.0.1:3389` avec la clé dédiée, puis `mstsc /v:127.0.0.1:33890` ; la commande génère un
   fichier `.rdp` sans mot de passe (utilisateur `ubuntu`) et l'ouvre.
3. **Mot de passe de session** : xrdp exige un mot de passe système ; il est généré au hasard (24 caractères ou plus), posé sur le serveur
   par `chpasswd` via l'entrée standard SSH (jamais en argument), et écrit dans `~/MyIAFactory/bureau-distant.txt` (le seul endroit). Il ne
   sert que par le tunnel : l'accès SSH par mot de passe reste désactivé.
4. **Déclenchement** : `lancer.py plateforme installer --bureau-distant` (l'étape 8 ne tourne jamais sans ce drapeau) ; l'état s'affiche dans
   la carte « Serveur » comme étape facultative.
5. **Fin de la licence** : une fois connecté à Hub, la commande `plateforme verifier` n'affirme rien sur la licence ; le Directeur constate
   dans Hub s'il est « sous licence » (la compilation réelle le confirmera à l'usage).

## Contraintes
- Mêmes règles que la plateforme : accord explicite pour toute action qui change le serveur, aucune écriture de secret dans l'état, tests
  entièrement simulés, passage par le lanceur de tests, commits par chemins dans le worktree, rien de poussé.
- Coût attendu sur le serveur : environ 1 Go de mémoire pendant la session, 2 à 3 Go de disque.

## Non vérifié (à constater à la première exécution)
Le nom exact du paquet et du dépôt d'Unity Hub pour Ubuntu 24.04, le comportement de xrdp avec XFCE sur 24.04, le lancement automatique de
Hub dans une session xrdp, et surtout si la connexion à Hub fournit une licence utilisable en compilation sans écran.

## Laissé au réalisateur
Découpage des fonctions, noms des fichiers de configuration, version de Firefox, détails de la session XFCE, tests.
