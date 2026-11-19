# Serveur dédié OVH : une plateforme prête à l'usage, configurée par API (conception)

## Pourquoi
Le Directeur a loué un serveur dédié OVH pour deux raisons : **compiler Unity pour Android** (impossible de façon fluide
sur un poste de 7,5 Go) et **augmenter la force de frappe** en hébergeant de nouveaux agents. Il veut que la plateforme
soit **prête à l'usage** : une machine propre, sécurisée, avec les outils installés, dont l'état est visible dans le bureau.
Se connecter à la machine pour y lancer des tâches est **hors de cette conception** : ce sera fait dans d'autres demandes.
Ce travail réalise le lieu `serveur` de `2026-11-17-execution-deportee-design.md` (côté mise en place, pas côté lancement).

## Buts
- Depuis le bureau, amener le serveur OVH de « livré » à « prêt » sans commande manuelle : système installé, accès par
  clé SSH, durcissement de base, Docker, images d'outils présentes.
- Montrer l'état dans une carte « Serveur » du bureau : joignable ou non, système, étapes de mise en place faites ou à
  faire, version des images, espace disque.
- Mise en place **rejouable sans risque** (idempotente) : relancer ne casse rien, ne refait que ce qui manque.

## Hors-buts
- Lancer des tâches (compilations, agents) sur le serveur : demandes ultérieures.
- Achat, résiliation, changement d'offre ou facturation OVH.
- Supervision continue, sauvegardes, haute disponibilité.
- Fournir ou saisir les secrets à la place du Directeur (clés API OVH, licence Unity).

## À éviter (échec même si « ça marche »)
- Une réinstallation du système lancée sans accord explicite (elle efface le disque).
- Des secrets (clés OVH, licence Unity) écrits dans le dépôt, dans les journaux ou dans une page du bureau.
- Un serveur ouvert : accès SSH par mot de passe, ports inutiles exposés.
- Une dépendance du bureau au serveur : si le serveur ou OVH est injoignable, le reste de l'application fonctionne.

## Approches considérées
A. Scripts Python, outils installés en dur sur la machine : simple, mais Unity et ses dépendances s'y accumulent, difficile
   à reproduire et à mettre à jour.
B. Ansible : propre mais ne tourne pas sous Windows sans WSL ; écartée.
**C. Mixte (retenue par le Directeur) : API OVH + SSH pour le système, puis Docker ; les outils vivent dans des images.**
Raison : isolation des futurs agents, environnement reconstructible en une commande, image Unity de référence (GameCI)
qui gère déjà la licence sans écran.

## Conception
1. **Couche OVH (API)** : client Python (bibliothèque standard, requêtes signées OVH) : lire le serveur
   (`/dedicated/server/{nom}`), ses informations, déclencher la réinstallation d'un modèle d'OS, suivre la tâche,
   enregistrer la clé SSH publique, lire l'état réseau. Région d'API (ovh-eu par défaut) réglable.
2. **Accès OVH** : le Directeur crée l'application et la clé consommateur (le bureau donne le lien et le mode opératoire,
   droits minimaux sur ce seul serveur) ; les trois valeurs sont lues dans `~/MyIAFactory` (hors dépôt, jamais journalisées).
3. **Étapes de mise en place**, chacune vérifiable et rejouable :
   1. *Lire* : serveur joignable par l'API, OS actuel.
   2. *Installer l'OS* (Linux, Ubuntu LTS par défaut) **seulement si demandé et accordé** ; sinon on garde l'OS présent.
   3. *Accès SSH* : clé dédiée générée sur le poste, clé publique posée, connexion vérifiée.
   4. *Durcissement* : accès par mot de passe coupé, pare-feu limité à SSH, mises à jour de sécurité automatiques.
   5. *Docker* installé et opérationnel.
   6. *Images d'outils* : image Unity (GameCI, version choisie par le Directeur), image Android/Gradle, image de base
      pour les agents (CLI Claude) ; tirées, versions épinglées.
   7. *Licence Unity* : activée dans un conteneur de test avec les éléments fournis par le Directeur ; état affiché.
4. **Réalisation des étapes 3 à 7** : un script de mise en place envoyé et exécuté par SSH, qui constate l'état avant
   d'agir (idempotent) et rend un compte rendu structuré (JSON) que le bureau affiche.
5. **Point d'entrée** : `lancer.py serveur <état|installer|verifier>` (même style que `lancer.py deporter`), et le bureau
   l'appelle ; `installer` demande l'accord avant l'étape 2.
6. **Carte « Serveur » du bureau** : état par étape (fait, à faire, bloqué avec la raison et le geste à faire),
   bouton « Mettre en place / reprendre », accord explicite pour la réinstallation, aide pour les étapes humaines
   (créer les clés OVH, obtenir la licence Unity) avec lien et mode opératoire.
7. **État conservé** dans `~/MyIAFactory` (cache de l'état connu), l'état réel étant toujours relu à la demande.
8. **Branchement avec l'existant** : une fois l'état « prêt », le lieu `serveur` de `bureau/deport.py` cesse d'être grisé
   (l'activation du lancement reste une demande ultérieure : ce travail ne change pas le routage des actions).

## Contraintes
- Poste Windows, Python 3.12 ; pas de nouvelle dépendance lourde. SSH via le client `ssh` de Windows.
- Les tests passent par le lanceur (`outils/tests_paralleles.py`) ; OVH et SSH sont simulés dans les tests, jamais réels.
- Licence Unity Personal : l'activation sans écran est plus contraignante qu'avec une licence Pro/serial ; ce que le
  Directeur possède décide du chemin (voir « Questions »).
- Une réinstallation OVH peut prendre plusieurs minutes et le serveur change de clé d'hôte : l'empreinte connue est à
  réinitialiser avec accord.

## Questions pour le Directeur (réponses attendues avant la planification)
1. Le serveur est-il déjà installé (quel OS) ou vierge ? Peut-on l'effacer ?
2. Quelle licence Unity possédez-vous (Personal, Pro/Plus, serial) ?
3. Quel modèle de serveur (processeur, mémoire, disque) ? Cela décide combien d'agents on peut espérer.

## Réponses du Directeur (2026-11-19)
1. **Serveur vierge** : rien à perdre, la réinstallation d'Ubuntu par l'API avec la clé dédiée est le chemin normal
   (l'accord explicite reste demandé dans le bureau, par principe).
2. **Licence Unity Personal** : l'activation passe par un fichier de demande (`.alf`) généré dans le conteneur, que le
   Directeur dépose sur le site d'Unity pour obtenir le fichier de licence (`.ulf`), à placer dans `~/MyIAFactory`.
   C'est une étape humaine : la carte donne le lien et le mode opératoire. Une licence Personal se renouvelle et son
   usage en compilation automatique est soumis aux conditions d'Unity (à vérifier par le Directeur).
3. **Matériel** : Xeon E5-1650v4 (6 cœurs / 12 threads, 3,6-4 GHz), 64 Go ECC DDR4, 2 × 4 To HDD SATA en RAID logiciel.
   Conséquences retenues : mémoire et processeur confortables pour plusieurs conteneurs ; **disques mécaniques lents** :
   les caches (Gradle, bibliothèque Unity) sont gardés dans des volumes persistants pour ne pas tout reconstruire, et le
   nombre de compilations simultanées est limité (réglage, 2 par défaut, ajustable). Le RAID est celui proposé par OVH à
   l'installation (à conserver).

## Laissé au réalisateur
Découpage des modules, forme du compte rendu JSON, texte et mise en page de la carte, choix exact de l'image Unity et de
ses versions, durcissement détaillé, stratégie de tests, noms des réglages.

## Choix du rédacteur après relecture (à relire, non validés)
- **Première connexion** : l'API OVH ne pose la clé SSH qu'à l'installation de l'OS. Chemin recommandé : réinstaller
  Ubuntu par l'API avec la clé dédiée (zéro mot de passe). Si le Directeur refuse d'effacer le serveur : il colle la clé
  publique dans `~/.ssh/authorized_keys` à la main (aide guidée dans la carte) ; le mot de passe root n'est jamais saisi
  dans le bureau.
- **Accord de réinstallation** : une confirmation unique par exécution, demandée dans le bureau (option
  `--accord-reinstallation` en ligne de commande). Sans accord, un OS absent ou inadapté (non Ubuntu LTS) met l'étape en
  « bloqué » avec la raison, sans rien effacer. Le même accord couvre la remise à zéro de l'empreinte d'hôte.
- **Pare-feu sans s'enfermer dehors** : port SSH 22 ; avant de couper le mot de passe et d'activer le pare-feu, le
  script vérifie qu'une seconde session par clé s'ouvre. Pas d'autre port ouvert ; les futurs besoins l'ajouteront.
- **Licence Unity** : lue depuis des fichiers de `~/MyIAFactory` (jamais un champ de page), transmise au conteneur par
  l'entrée standard SSH (jamais en argument ni dans l'historique), masquée dans les journaux et le compte rendu.
- **« Prêt »** = étapes 1 à 6. La licence Unity (étape 7) est facultative : sans elle, le serveur est « prêt, sans Unity ».
  Le lieu `serveur` se dégrise à « prêt ».
- **Images** : GameCI est tirée (version épinglée par étiquette) ; les images Android/Gradle et agents sont construites
  sur le serveur depuis des Dockerfile versionnés dans le dépôt (livrables de ce travail). La carte compare la version
  affichée à la liste du dépôt.
- **Script distant** : un fichier bash du dépôt, envoyé par `ssh` (entrée standard), sans `scp` ; client OpenSSH de
  Windows ; SSH simulé dans les tests.

## Choix du rédacteur (à relire, non validés)
- Ubuntu LTS comme OS par défaut ; image Unity GameCI ; client OVH écrit à la main (requêtes signées) plutôt que le SDK
  OVH, pour éviter une dépendance ; clé SSH dédiée au serveur plutôt que la clé personnelle.
