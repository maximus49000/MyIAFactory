# Le serveur générique (n'importe quel serveur, des capacités installées à la demande)

MyIAFactory ne dépend pas d'un fournisseur : vous lui donnez **l'adresse d'un serveur**, et elle y installe **seulement ce
qu'exigent les actions que vous lui confiez**, après aperçu et accord. OVH n'est plus qu'un fournisseur parmi ceux qu'on peut
brancher (voir [`serveur-ovh.md`](serveur-ovh.md)). Conception : [`2026-11-19-serveur-generique-design.md`](superpowers/specs/2026-11-19-serveur-generique-design.md).

Ce guide couvre le serveur et ses capacités. Les **tâches d'émulation** (l'APK joué sur un émulateur du serveur) ont leur propre
guide : [`serveur-taches.md`](serveur-taches.md) (rien n'y a encore tourné sur un vrai serveur). Le reste du lancement d'actions sur le
serveur n'existe pas encore : voir « Suite ».

## Ce qu'un serveur doit offrir (contrat minimal)

- une **adresse** (nom d'hôte ou IPv4 : lettres, chiffres, `.`, `_` et `-` seulement, sans tiret au début ; ni espace, ni `@`, ni `/ : [ ] ,`,
  ni aucun autre signe : une adresse IPv6 est refusée) ; l'utilisateur suit la même règle ;
- un **utilisateur** avec `sudo` **sans mot de passe** (le compte `root` est refusé : créez un utilisateur dédié, MyIAFactory
  n'en crée jamais) ;
- une **clé SSH** : MyIAFactory en génère une par serveur, vous collez sa partie publique dans `authorized_keys` ;
- un **Ubuntu récent** (seul Ubuntu est supporté : l'étape Docker utilise le dépôt `download.docker.com/linux/ubuntu`).

Rien d'autre. Un serveur sans fournisseur saute l'étape « système » : il suffit qu'on puisse s'y connecter.

## Déclarer un serveur

Dans le bureau (panneau Direction, carte « Serveurs de travail », formulaire « Déclarer un serveur » : nom, adresse,
utilisateur, fournisseur « Aucun » ou OVH) ou en ligne de commande :

```
py -3.12 lancer.py plateforme serveurs declarer "Mon serveur" 203.0.113.5 ubuntu
```

La déclaration écrit `~/MyIAFactory/serveurs.json` (hors dépôt, droits restreints, jamais de secret : les clés d'API d'un
fournisseur restent dans leurs propres fichiers) et crée la clé dédiée `~/MyIAFactory/id_ed25519_<id>` (jamais écrasée si elle
existe). Elle affiche la **ligne de clé publique à copier**, de la forme :

```
ssh-ed25519 AAAA... myiafactory
```

Collez cette ligne **telle quelle** dans `~/.ssh/authorized_keys` de l'utilisateur sur le serveur (le bureau a un bouton
« Copier la ligne »). L'identifiant est tiré du nom (minuscules, tirets). Le nom `migration` est réservé (voir plus bas).
Puis « Tester la connexion » (bureau) ou `py -3.12 lancer.py plateforme serveurs sonder <id>`.

Si la clé n'a pas pu être créée, le serveur est quand même déclaré, un avertissement le dit et le code de sortie est 1 :
relancez `cle <id>`.

## Les capacités

Une capacité est ce qu'on sait installer et **vérifier** sur un serveur. Chacune a une **sonde en lecture seule** (jamais
d'installation) : une sonde qui échoue donne « absente », un serveur injoignable donne « inconnue », jamais « absente ».

| Identifiant | Ce que c'est | Dépend de | Taille / durée (estimations) | Installable par MyIAFactory |
|---|---|---|---|---|
| `base` | Docker et outils | rien | 0,5 Go / 5 min | oui |
| `durcissement` | SSH par clé seule, pare-feu | `base` | 0 Go / 2 min | oui (étape `durcissement`) |
| `android-build` | SDK Android, plateforme 36, build-tools 36.0.0 et un Java (au choix : `java` du PATH, JDK 17 d'Ubuntu, ou JDK livré avec le module Android d'Unity, `~/Unity/Hub/Editor/*/Editor/Data/PlaybackEngines/AndroidPlayer/OpenJDK`  ; si le SDK est déjà complet et qu'un de ces Java existe, l'étape répond « déjà en place » sans rien installer ; sinon elle installe le JDK 17 d'apt avec le SDK) | `base` | 5,4 Go / 10 min | oui |
| `android-emulateur` | KVM, émulateur, image système (l'image **épinglée** `system-images;android-34;google_apis;x86_64`, celle de `versions.json`) | `android-build` | 2 Go / 8 min | oui, **si le serveur offre `/dev/kvm`** |
| `emulateur-image` | Image de conteneur `myiafactory/emulateur` (sans identifiants), construite sur le serveur ; sert aux tâches d'émulation | `android-emulateur` | 1,5 Go / 10 min | oui (étape `emulateur_image`) |
| `unity-cli` | Outil officiel Unity en ligne de commande | `base` | 0,1 Go / 2 min | oui |
| `unity-editeur` | Éditeur Unity | `unity-cli` | 24 Go / 25 min | **non** : à installer par la session graphique (Unity Hub) ou `unity install <version>` une fois connecté ; licence par Hub |
| `session-graphique` | Bureau distant et Unity Hub | `base` | 3 Go / 12 min | **non** par ce moteur : `py -3.12 lancer.py plateforme installer --bureau-distant` (il faut un mot de passe de session) |
| `agent` | Agent de développement sur le serveur | rien | 1 Go / 5 min | **non** avant le morceau 3 |

La sonde de `android-emulateur` vérifie le dossier de l'**image système épinglée** (pas seulement la présence de `system-images`) :
une autre image Android installée ne suffit pas à l'émulateur des tâches. Tailles et durées sont des **estimations** tirées de nos installations réelles, pas des garanties. Une capacité non
installable est « bloquée » avec sa raison et le geste à faire ; elle n'est jamais lancée.

**On n'installe pas une capacité directement : on confie une action**, et le bureau calcule les capacités manquantes (en suivant
les dépendances). Actions connues et capacité requise :

| Action | Capacité requise |
|---|---|
| `apk`, `tests`, `lint`, `release` | `android-build` (donc `base`) |
| `emulateur` | `android-emulateur` (donc `base`, `android-build`) |
| `charge` | aucune |

La capacité `emulateur-image` n'est demandée par **aucune action** de cette table aujourd'hui (l'action `recette-emulateur`, qui
en a besoin, n'y figure pas) : elle est sondée et affichée, mais ni l'écran d'action ni `installer` ne savent encore la demander.

`release` n'est qu'un besoin de construction : les clés de signature restent au poste. Aujourd'hui aucune action ne demande
`durcissement`, `unity-cli` ni les capacités non installables : elles sont **sondées et affichées**, pas installables depuis un
écran d'action.

## Aperçu, accord, installation

1. **Aperçu** (lecture seule : une connexion SSH de sonde, aucun fichier écrit) : liste des capacités manquantes, taille et durée
   totales (des seules capacités installables), capacités bloquées. Serveur injoignable ou état illisible : une erreur, et rien
   n'est calculé comme manquant.
2. **Accord** : il n'y a **aucune installation sans accord explicite**, jamais implicite. Dans le bureau : la case « J'autorise cette
   installation sur le serveur » (décochée par défaut, décochée après chaque envoi), puis « Lancer l'installation ». En ligne de commande :
   l'option `--accord` sur la ligne même. **L'accord vaut pour une seule installation** : relancer demande un nouvel accord.
   Sans accord, `installer` affiche l'aperçu et sort avec le code 1, rien n'est installé.
3. **Installation** : une seule à la fois sur le poste (verrou `serveurs-installation.lock`, aussi entre deux fenêtres). Elle partage le
   script distant `mise_en_place.sh` avec l'installation de la plateforme OVH (verrou `plateforme.lock`) : **les deux flux se refusent
   mutuellement**, dans le bureau (réponse 409 en français) comme en ligne de commande (code 1) : chacun prend son verrou puis vérifie
   que celui de l'autre est libre, sans jamais attendre. Le script est déposé dans un fichier temporaire puis renommé (`mv -f`), jamais
   écrit en place pendant que `bash` le lit. L'état réel est relu par sonde **une fois au début et une fois à la fin** (jamais le cache) ;
   entre les deux, l'état est écrit avant et après chaque capacité. Une étape « fait » dont la capacité n'est pas détectée à la fin
   devient « bloquée ». Un échec laisse le serveur dans un état connu : la capacité est « bloquée » avec sa raison et le geste proposé
   (le bureau les affiche dans la carte du serveur), les suivantes « à faire » ; une connexion perdue ou un délai dépassé donne
   « inconnue » (l'étape peut encore tourner : attendez avant de relancer). Une installation interrompue (fenêtre fermée) réapparaît
   « inconnue » : relancez ou lancez un aperçu. **Une installation ne réécrit que ses propres capacités** : les autres, leurs raisons de
   blocage et la charge mesurée sont conservées (une installation « charge » ne vide rien).

Les étapes distantes sont celles de `serveur_ovh/mise_en_place.sh` (`docker`, `durcissement`, `android_build`, `android_emulateur`,
`emulateur_image`, `unity_cli`), rejouables. Le script est déposé dans `~/myiafactory/` du serveur (droits 0700). L'état est écrit dans
`~/MyIAFactory/serveurs-etat.json` (aucun secret).

### La capacité `emulateur-image`

Elle construit l'image `myiafactory/emulateur` (Ubuntu 24.04, JDK 17, le pont d'actions, sans identifiants) sur le serveur, à partir
de trois fichiers déposés par le moteur : `images/emulateur/Dockerfile`, `images/emulateur/entree-tache.sh` et `taches/pont.sh`
(liste `FICHIERS_ETAPE`, sous `serveur_ovh/`). Ils sont déposés dans `$HOME/myiafactory/serveur_ovh/` du serveur (dossier que
l'étape retrouve par la variable `SERVEUR_OVH_DIR`, `$HOME/myiafactory/serveur_ovh` par défaut) par une archive tar, extraite dans
un dossier temporaire privé : rien n'est déplacé si l'archive est coupée ou si un fichier manque ou est vide. Elle demande 3 Go
libres et refuse de tourner sous root.

- **Le marqueur** : `~/.myiafactory/emulateur-image.version` contient les versions épinglées et l'**empreinte** des trois fichiers
  (16 premiers hexadécimaux du SHA-256). La sonde du catalogue est une simple existence de fichier (`test -s`) ; la **péremption**
  est une lecture de plus (`head -c 256` de ce seul fichier) faite par le moteur pour les capacités demandées.
- **Périmée** : si l'empreinte du marqueur diffère de celle des fichiers du dépôt, la capacité n'est plus « présente » : l'aperçu
  la range dans `perimees` et l'étape se montre **« À mettre à jour : les fichiers déposés sur le serveur sont périmés »** ;
  réinstaller reconstruit l'image (l'étape n'est refaite que si l'étiquette de l'image diffère). Une installation qui se termine
  avec un marqueur encore périmé est « bloquée ».
- Le lanceur de tâches refuse d'envoyer quoi que ce soit tant que l'image est périmée (voir `serveur-taches.md`).

## L'écran « Où tournent les actions »

Dans la même carte du panneau Direction, chaque action propose trois lieux : le **poste**, **GitHub** et le **serveur**. Chaque lieu
porte une **pastille de couleur et un libellé écrit** (la couleur n'est jamais seule), et sa raison s'affiche au survol :

| Niveau | Couleur | Sens |
|---|---|---|
| `recommande` | vert | le meilleur choix du moment |
| `possible` | ambre | utilisable, sans net avantage |
| `deconseille` | rouge | lieu très chargé (au-dessus de 85 %) ou quota GitHub presque épuisé (sous 15 %) |
| `indisponible` | gris | capacité manquante, serveur muet ou hors ligne : le choix « serveur » est grisé avec « Manque : ... » |

**C'est un conseil, pas un routage** : le bureau ne déplace jamais une action de lui-même, et l'écran le rappelle (« Ce n'est qu'un
conseil : le choix reste au Directeur »). Le choix de lieu fait avec les boutons radio de cet écran-ci n'est **pas enregistré** (aucune route ne le garde) ; le
réglage qui compte (l'accord permanent de la recette sur émulateur) se fait dans les réglages du projet : voir
[`deport.md`](deport.md).

**Ce qui est mesuré aujourd'hui, et ce qui ne l'est pas encore.** La recommandation n'utilise que ce que le **dernier test de connexion
du serveur** a rangé dans l'état : la charge moyenne **sur 5 minutes** par cœur, la mémoire libre, le nombre de conteneurs (lus par SSH en
lecture seule, horodatés ; une mesure de plus de 15 minutes est ignorée). Les **durées par lieu, la charge du poste et le quota
GitHub restant ne sont pas encore branchés** : ils valent « aucun » et la couleur retombe sur des règles simples (et le dit :
« fondée sur des règles » plutôt que « sur des mesures »). Sans charge connue, le serveur n'est jamais présenté comme le meilleur choix.
Les lieux poste et GitHub ne sont pas encore modélisés : toute action connue y est permise.

## En ligne de commande

Toutes les commandes se lancent par `py -3.12 lancer.py plateforme serveurs <commande> ...` ; `--dossier <d>` change le dossier de
configuration (par défaut `~/MyIAFactory`, ou la variable `MYIAFACTORY_PLATEFORME`). Les sorties sont en JSON masqué (aucune clé, aucun chemin de clé).

| Commande | Effet | Codes de sortie |
|---|---|---|
| `declarer <nom> <hote> <utilisateur> [--fournisseur ovh]` | déclare, crée la clé, affiche la ligne publique | 0 ; 1 refus (adresse, doublon, fichier abîmé) ou clé non créée ; 2 usage |
| `lister` | serveurs, capacités (présente/absente/inconnue/…), déclarations rejetées | 0 |
| `cle <id>` | affiche la ligne publique ; **génère la clé si elle est absente** (jamais écrasée), c'est voulu | 0 ; 1 serveur inconnu ou échec |
| `sonder <id>` | sonde toutes les capacités (SSH, lecture seule), range l'état et la charge | 0 joignable ; 1 injoignable ou installation en cours |
| `apercu <id> <action>...` | aperçu sans rien écrire (jusqu'à 20 actions) | 0 ; 1 injoignable ou état illisible ; 2 action inconnue |
| `installer <id> <action>... [--accord]` | installe sur accord ; sans `--accord`, aperçu et sortie 1 | 0 tout est en place ; 1 échec, bloqué, refus ou sans accord ; 2 usage ou action inconnue |

Code 2 : usage, option inconnue, option mal placée (`--accord` hors `installer`, `--fournisseur` hors `declarer`), identifiant ou action
invalide (minuscules, chiffres, `-`, `_`). Aucune trace d'exception n'est jamais affichée : au pire le type de l'erreur.

## Migration du serveur OVH existant

Le serveur OVH déjà installé par l'ancien flux (`lancer.py plateforme ...`) peut être inscrit comme serveur générique
`fournisseur: ovh`, **sans réinstallation** :

- La carte **apparaît à l'ouverture du panneau Direction** (pas au démarrage du bureau), seulement si `ovh.json` et
  `plateforme.json` existent, si la clé dédiée `id_ed25519_myiafactory` existe, et si **aucun serveur n'est déjà déclaré** (même rejeté).
  Elle propose : « Votre serveur OVH a été détecté ».
- « Voir l'aperçu (lecture seule) » relit l'état réel par SSH : ce qui sera déclaré (adresse, utilisateur `ubuntu`, clé existante)
  et les capacités constatées. Serveur injoignable : toutes « inconnues », jamais « absentes ».
- **Confirmation explicite** : case « J'autorise l'inscription de ce serveur (rien n'est réinstallé ni modifié sur le serveur) » puis
  « Confirmer l'inscription du serveur ». Sans accord, rien n'est écrit ni sondé.
- La migration n'écrit que `serveurs.json` (identifiant `serveur-ovh`) et `serveurs-etat.json`. Elle **ne touche jamais** à `ovh.json`, à
  `plateforme.json`, à la clé ni au serveur (pare-feu et SSH inchangés), n'appelle pas OVH et ne réinstalle rien. Les anciens fichiers
  restent lisibles : retour arrière possible (supprimer l'entrée de `serveurs.json`).
- L'identifiant `migration` est **réservé** : il se confondrait avec les routes `/api/serveurs/migration/...` ; la déclaration d'un
  serveur de ce nom est refusée. Une migration à la fois ; si l'écriture de l'état échoue, la déclaration faite est défaite
  (seulement si le fichier n'a pas été modifié entre-temps).
- Réinstaller le système OVH reste le travail de `plateforme installer --accord-reinstallation` : le moteur générique ne le fait jamais.

## Limites : ce qui n'a PAS été exécuté sur un vrai serveur

- Les étapes distantes **`android_build`, `android_emulateur`, `emulateur_image` et `unity_cli`**, telles qu'écrites dans `mise_en_place.sh`, n'ont **jamais été
  exécutées sur le vrai serveur** : leurs tests automatiques sont simulés. Une installation équivalente a été faite à la main plus tôt,
  avec d'autres scripts (pas ceux-ci).
- Le **moteur générique** (déclaration, sonde, aperçu, installation, charge), l'**interface du bureau**, la **ligne de commande** et la
  **migration** n'ont **jamais tourné contre le serveur réel** : tous leurs tests passent par de faux SSH et de faux dossiers. Aucune
  commande n'a été envoyée au vrai serveur pendant ce travail, et le vrai dossier `~/MyIAFactory` n'a pas été modifié.
- Le **montage réel dans le panneau Direction** n'a pas été vu à l'écran contre le vrai bureau branché à son vrai dossier
  (voir le rapport de vérification pour ce qui a été regardé avec un état jetable).
- Le comportement d'un serveur non OVH (Debian, autre fournisseur) n'a été simulé que par les tests.
- Connus et non corrigés : le durcissement n'ouvre le pare-feu que sur le port 22 ; la sonde du durcissement ne voit pas le pare-feu ;
  la sonde `base` vérifie le binaire Docker, pas que son démon tourne ; la déclaration web refuse (409) pendant une opération du bureau, mais ni elle ni la migration
  n'excluent strictement une déclaration simultanée de la ligne de commande d'un autre processus (fenêtre limitée par une revérification) ; si le serveur n'a pas `/dev/kvm`
  l'étape émulateur reste « bloquée ».
- L'historique Git contient d'anciens fragments de clés OVH (voir `serveur-ovh.md`) : le réécrire est un préalable à toute publication.

## Suite

1. **Morceau 2 : lancer des tâches sur le serveur** (verrou et créneaux de ressources). **Premier pas fait : les tâches d'émulation**
   ([`serveur-taches.md`](serveur-taches.md), jamais exécutées sur un vrai serveur) ; reste le reste du lancement d'actions. Brancher la table `besoins` de ce cœur sur
   `bureau/deport_types.py` **une fois le travail de déport du Directeur commité** (le cœur n'en dépend pas : il porte sa propre table) ;
   alimenter les mesures (durées par lieu, charge du poste, quota GitHub) par `mesures_pour`, point unique de branchement ; enregistrer le choix de lieu.
2. **Morceau 3 : agents sur le serveur** (conteneur d'agent éphémère par tâche, conteneurs d'outils sans identifiants, authentification
   par abonnement, **coffre de signature** partagé, **bascule** des agents entre lieux avec ordre de préférence, maximum par lieu et file visible).
3. **Morceau 4 : bouton d'accès SSH ou graphique** dans le bureau, suivi des tâches et des agents.
4. **Tâche 13 : recettes des capacités futures.** Familles 1 à 11 du plan, **ordre à confirmer avec le Directeur** avant d'écrire quoi que ce
   soit. Chaque capacité garde la forme actuelle (identifiant, dépendances, étape rejouable, sonde en lecture seule, taille et durée) et reçoit une recette
   (installer, sonder, nettoyer) relue par le Directeur avant son entrée au catalogue.
   **Hors périmètre** : la compilation iOS (exige un Mac) ; l'IA lourde et la génération d'images locale (exigent un GPU).
