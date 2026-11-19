# Serveur générique : un serveur quelconque, des capacités installées à la demande (conception)

Premier des quatre morceaux validés par le Directeur : 1 serveur générique, 2 lancer des tâches sur le serveur, 3 agents sur le
serveur, 4 interface (bouton d'accès, suivi). Ce document ne couvre que le morceau 1, plus ce qu'il faut pour que les trois autres
s'y accrochent.

## Pourquoi
MyIAFactory est universelle : elle ne doit pas dépendre d'OVH. Le Directeur donne **l'adresse d'un serveur** ; MyIAFactory y installe
**seulement ce qu'exigent les types de tâches qu'on lui confie**. Aujourd'hui tout ce qui a été construit (`outils/plateforme*.py`,
`serveur_ovh/`) est écrit pour un serveur OVH. Seule la création ou réinstallation du système est vraiment propre à OVH : SSH, Docker,
images, SDK Android, émulateur, Unity et session graphique marchent sur n'importe quel Ubuntu.

## Buts
- Un **modèle de serveur** : adresse, utilisateur, clé SSH dédiée, fournisseur facultatif (`ovh` ou aucun).
- Un **catalogue de capacités** (ce qu'on sait installer et vérifier sur un serveur) ; chaque capacité a des étapes rejouables.
- **Des types d'actions et d'agents qui déclarent leurs besoins** (liste de capacités). Confier un type d'action au serveur déclenche,
  avec aperçu (taille, durée) et accord du Directeur, l'installation des seules capacités manquantes.
- **Des écrans de paramétrage du serveur dans le bureau** : déclarer un serveur, voir ses capacités (installées, absentes, bloquées),
  installer ou réparer, et **choisir les actions qu'on lui confie : seules les actions que le serveur permet sont proposées**,
  les autres grisées avec ce qui manque (« Tests sur émulateur : capacité émulateur à installer »).
- Le serveur OVH actuel migre sans réinstallation : ses réglages et son état deviennent un serveur `fournisseur: ovh`.

## Hors-buts (morceaux suivants)
- Lancer réellement des tâches sur le serveur, verrou et créneaux de ressources (morceau 2).
- Agents sur le serveur, image d'agent, authentification par abonnement, comptage d'usage (morceau 3).
- Bouton d'accès SSH et vue graphique, suivi des tâches et des agents dans le bureau (morceau 4 ; la carte de paramétrage de ce morceau
  est limitée à déclarer, installer et choisir les actions).
- Plusieurs fournisseurs autres qu'OVH : seul le point d'extension est prévu.

## À éviter
- Une règle qui suppose OVH : aucune action ni capacité ne doit lire un réglage OVH.
- Installer des choses sur un serveur sans accord ou sans qu'une action confiée au serveur l'exige.
- Casser le serveur OVH en service : la migration ne le réinstalle jamais et ne change pas sa configuration (pare-feu, SSH).
- Un secret (clés API d'un fournisseur, mot de passe de session) dans l'état, les journaux ou le dépôt.

## Approches considérées
A. **Garder la plateforme OVH et ajouter des « adaptateurs » ailleurs** : moins de travail, mais chaque nouvelle règle serait écrite deux fois.
B. **Tout réécrire en un module « serveur » neuf** : propre, mais perd les relectures déjà faites.
**C. Extraire : un cœur générique (serveur, capacités, SSH, état), le code OVH devient un fournisseur branché dessus (retenue).**
On déplace et renomme sans réécrire la logique éprouvée (verrou, accord strict, reprise, masquage des secrets).

## Conception
1. **Serveur** (réglage global du bureau, une liste ; un seul serveur au départ) :
   `{id, nom, hote, utilisateur, cle, fournisseur: "ovh"|null, reglages_fournisseur}`. Premier accès (choix du rédacteur) : le bureau génère la clé
   dédiée et affiche la ligne à coller dans `authorized_keys` ; pour OVH, la clé est injectée à la réinstallation par l'API.
2. **Fournisseur** : interface minimale `lire()`, `reinstaller(accord)` et `attendre()`, implémentée par OVH (code actuel) ; un serveur sans
   fournisseur saute l'étape « système » et exige seulement un accès SSH qui marche.
3. **Capacités** (catalogue dans le dépôt, une entrée par capacité : `id`, libellé, dépendances, étapes rejouables, taille et durée estimées,
   preuve de réussite) : `base` (Ubuntu, durcissement, Docker, `unzip`), `android-build` (JDK 17, Gradle, SDK, plateformes 34/36),
   `android-emulateur` (KVM, groupe `kvm`, émulateur, image système), `unity` (éditeur et modules via Unity CLI ; licence par Hub),
   `session-graphique` (XFCE, xrdp en loopback, Hub), `agent` (CLI Claude, Git, clé de déploiement).
4. **Besoins des actions** : chaque entrée des catalogues d'actions (`bureau/deport_types.py`, par genre de projet) gagne `besoins: [capacités]`
   (ex. « Tests sur émulateur » → `android-emulateur`). Les types d'agents déclarent leurs besoins de la même manière.
5. **Installation à la demande** : quand le lieu `serveur` est choisi pour une action, le bureau calcule les capacités manquantes (en
   suivant les dépendances), montre l'aperçu (taille, durée, ce qui sera installé) et n'installe qu'après accord. Un échec laisse le serveur
   dans un état connu et la capacité « bloquée » avec la raison et le geste.
6. **Écrans de paramétrage** (dans le bureau, comme la carte « Serveur » actuelle) : (a) déclarer ou modifier un serveur (adresse,
   utilisateur, fournisseur, ligne de clé à copier, test de connexion) ; (b) la liste des capacités avec leur état et les boutons
   « installer » et « réparer » ; (c) « Où tournent les actions » : pour chaque action du genre du projet, `poste`, `GitHub` ou `serveur`,
   `serveur` n'étant sélectionnable que si le serveur a (ou peut installer, avec accord) les capacités de l'action. Le bureau ne propose jamais
   un lieu que le serveur ne permet pas.
7. **Migration, DERNIÈRE ÉTAPE du morceau 1 (demande du Directeur)** : on construit et on valide d'abord le serveur générique sur un
   serveur vierge simulé, de façon que l'universalité soit prouvée sans dépendre du serveur actuel. Ensuite seulement, **l'instance
   MyIAFactory du Directeur intègre automatiquement son serveur OVH** : au démarrage, si `~/MyIAFactory/ovh.json` et `plateforme.json`
   existent et qu'aucun serveur n'est déclaré, le bureau crée l'entrée `fournisseur: ovh` d'après ces fichiers (adresse, utilisateur
   `ubuntu`, clé dédiée existante), lit l'état réel du serveur (lecture seule, SSH) et marque installées les capacités qu'il y trouve
   (`base`, `android-build` pour le JDK et le SDK dédié, `session-graphique`, etc.). Elle ne réinstalle rien, ne change ni le pare-feu ni
   SSH, et demande confirmation du Directeur avant d'écrire l'inscription (aperçu : ce qui sera déclaré). Ses anciens fichiers restent
   lisibles (retour arrière possible).
7bis. **Environnement d'un agent** (prévu ici, construit au morceau 3) : l'agent ne contient que le CLI Claude, Git et le lanceur ; ses
   compilations et tests partent dans des **conteneurs d'outils séparés, sans les identifiants d'abonnement**, sur le dossier de travail
   partagé (choix du Directeur). Les capacités fournissent ces conteneurs d'outils.

## Contraintes
- Python 3.12, bibliothèque standard ; tests entièrement simulés (jamais de vrai serveur) ; passage par le lanceur de tests ; commits
  par chemins ; aucun accord d'effacement implicite ; messages en français.
- Le code du serveur OVH en service (relu et testé) est déplacé, pas réécrit : ses tests restent verts.
- Le contrat d'un serveur est minimal : une adresse, un utilisateur avec `sudo`, une clé SSH et un Ubuntu/Debian récent.

## Questions ouvertes
1. Un seul serveur au départ avec un modèle prêt pour plusieurs : le Directeur confirme-t-il ?
2. Où vit la configuration : un fichier global du bureau (`~/MyIAFactory/serveurs.json`) ou le fichier du bureau existant (`bureau.json`) ?

## Laissé au réalisateur
Découpage des modules, format du catalogue de capacités, noms des fichiers, détails de la migration, texte et mise en page des écrans.

## Choix du rédacteur après relecture (à relire, non validés)
- **Catalogue des actions** : `bureau/deport_types.py` (catalogues par genre) fait partie du travail de déport du Directeur, non commité dans
  cette branche. Le cœur générique ne dépend donc PAS de ce fichier : il porte sa propre table `besoins` (identifiant d'action → capacités),
  fusionnée plus tard avec les catalogues. Table de départ : `apk`, `tests`, `lint` → `android-build` ; `emulateur` → `android-emulateur` ;
  `release` → `android-build` (clés de signature restant au poste) ; actions Unity → `unity` ; `charge` → aucune capacité propre. L'écran « Où
  tournent les actions » et le branchement sur `deport_types.py` sont les tâches qui exigent que le travail de déport soit commité.
- **Preuves de capacité** : une sonde en lecture seule par capacité (fichier ou commande de vérification), jamais d'installation. Une sonde
  qui échoue donne « absente », même si l'ancien état disait « fait » ; les anciennes entrées d'état sans capacité correspondante (`licence`,
  `images`…) sont conservées à part (`ancien_etat`) et ignorées. La migration ne peut déclencher aucune réinstallation.
- **Lieu `serveur`** : le choix est autorisé dans la validation seulement pour les actions dont les capacités sont installées ; tant que le
  morceau 2 n'existe pas, le lancement reste indisponible et l'action est proposée au poste avec l'accord du Directeur (règle déjà posée par le
  design de déport), avec un message clair.
- **Accord d'installation** : même mécanisme que la plateforme (accord strict, jamais implicite, case ou bouton dans le bureau, option en
  ligne de commande). Tailles et durées : estimées dans le catalogue d'après nos installations réelles (SDK Android et émulateur ≈ 5 Go,
  éditeur Unity avec Android ≈ 24 Go, etc.), marquées « estimation ».
- **Dépendances** : `base` ← tout le reste ; `android-emulateur` ← `android-build` ; `unity` ← `base` (la connexion à Unity Hub passe par
  `session-graphique`, facultative) ; `agent` déclarée mais « non installable avant le morceau 3 » (affichée ainsi).
- **Tests** : les tests existants restent verts ; les modules déplacés laissent des **raccourcis** (`plateforme_ovh.py` etc. ré-exportent)
  jusqu'à la fin de la migration ; les tests peuvent être adaptés aux nouveaux noms quand un raccourci disparaît.
- **Utilisateur du serveur** : `sudo` sans mot de passe obligatoire (documenté) ; un utilisateur `root` est refusé avec le geste « créez un
  utilisateur avec sudo » (le code refuse déjà de tourner en root) ; aucune création d'utilisateur par MyIAFactory.
- **Durcissement d'un serveur non OVH** : capacité séparée de `base`, proposée et recommandée mais **facultative et soumise à l'accord** ; la
  garde anti-enfermement existante (seconde session avec la clé dédiée, clé présente) reste obligatoire.

## Choix du rédacteur (à relire, non validés)
Premier accès par clé publique collée par le Directeur ; un seul serveur au départ ; Ubuntu/Debian récent comme seul Linux supporté ;
capacités d'Unity par Unity CLI (éditeur installé par Hub sur la session graphique).
