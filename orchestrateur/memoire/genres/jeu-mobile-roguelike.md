# Genre : jeu-mobile-roguelike
Domaine : rogue-like procédural
Livrable : à préciser
Outils : à préciser

## G1 — Pour un moteur dont les templates d'export sont distribués à
Rôles : environnement
Date : 2026-11-12

Pour un moteur dont les templates d'export sont distribués à part, les télécharger depuis la source officielle et les placer dans le dossier utilisateur du moteur sous le nom exact de la version.

## G2 — Pour un jeu en pixel art, une police bitmap générée par scri
Rôles : artiste
Date : 2026-11-12

Pour un jeu en pixel art, une police bitmap générée par script, à échelle entière, évite d'inscrire une licence de police.

## G3 — Pour vérifier un projet de jeu sans écran, importer les ress
Rôles : dev
Date : 2026-11-12

Pour vérifier un projet de jeu sans écran, importer les ressources puis lancer quelques images en mode sans interface, et lire le code de retour et la console.

## G4 — Pour vérifier un rendu de jeu, un script lancé avec le moteu
Rôles : dev, testeur
Date : 2026-11-12

Pour vérifier un rendu de jeu, un script lancé avec le moteur instancie la scène, attend quelques images et enregistre la capture, ce qui prouve la résolution et l'affichage.

## G5 — Pour des personnages jouables aux particularités différentes
Rôles : artiste
Date : 2026-11-12

Pour des personnages jouables aux particularités différentes, garder une silhouette et une zone de collision identiques et varier seulement couleurs et détails, pour ne pas fausser l'équilibrage.

## G6 — Lancer un export de test (headless) dès la mise en place du
Rôles : dev, testeur
Date : 2026-11-12

Lancer un export de test (headless) dès la mise en place du projet : les prérequis de compression de textures et de signature ne se voient pas dans les fichiers de configuration, seulement à l'export.

## G7 — Pour un export mobile de test, désactiver la signature tant
Rôles : dev
Date : 2026-11-12

Pour un export mobile de test, désactiver la signature tant qu'aucun keystore n'est fourni.

## G8 — Pour prouver un rendu de jeu, instancie la scène depuis un s
Rôles : testeur
Date : 2026-11-12

Pour prouver un rendu de jeu, instancie la scène depuis un script lancé par le moteur. Attends quelques images, enregistre la capture et affiche sa taille.

## G9 — Quand les assets arrivent avant les scènes qui les utilisent
Rôles : dev
Date : 2026-11-12

Quand les assets arrivent avant les scènes qui les utilisent, centraliser leur accès dans un catalogue nommé et vérifier le branchement avec une scène galerie capturée par le moteur.

## G10 — Pour signer une APK Godot, créer le keystore avec keytool en
Rôles : livreur
Date : 2026-11-12

Pour signer une APK Godot, créer le keystore avec keytool en -storetype JKS, car apksigner ne lit pas le PKCS12 par défaut du JDK 17.

## G11 — Pour un export Godot signé, passer le chemin, l'alias et le
Rôles : livreur
Date : 2026-11-12

Pour un export Godot signé, passer le chemin, l'alias et le mot de passe du keystore par variables d'environnement, jamais dans le fichier de preset.

## G12 — Comparer par script les pixels de chaque sprite à la palette
Rôles : testeur
Date : 2026-11-12

Comparer par script les pixels de chaque sprite à la palette documentée, avec les variantes d'ombre et de reflet calculées, avant de valider un lot d'assets.

## G13 — Dans un script de génération de sprites, imposer par asserti
Rôles : artiste
Date : 2026-11-12

Dans un script de génération de sprites, imposer par assertion les seuls facteurs d'ombre et de reflet autorisés et fournir un script de vérification qui compare tous les pixels opaques à la palette évite les couleurs hors palette.

## G14 — Pour un export Android signé d'un moteur de jeu, transmettre
Rôles : livreur
Date : 2026-11-12

Pour un export Android signé d'un moteur de jeu, transmettre le chemin, l'alias et le mot de passe du keystore par variables d'environnement, jamais dans le fichier de preset, et vérifier la signature de l'APK obtenu.

## G15 — Pour un jeu à musique en boucle, générer sons et musiques pa
Rôles : artiste
Date : 2026-11-12

Pour un jeu à musique en boucle, générer sons et musiques par un script en Python pur (module wave, oscillateurs, bruit) évite toute licence externe, et un script de vérification contrôle format, niveau, écrêtage et continuité de boucle.

## G16 — Pour des icônes de carte de progression, doubler la couleur
Rôles : artiste
Date : 2026-11-12

Pour des icônes de carte de progression, doubler la couleur par une silhouette distincte (pointes, anneau lisse, taille) garde les types de nœuds lisibles à petite taille et pour les daltoniens.

## G17 — Pour un jeu à carte de nœuds, fournir un marqueur de sélecti
Rôles : artiste, dev
Date : 2026-11-12

Pour un jeu à carte de nœuds, fournir un marqueur de sélection distinct des icônes et trois styles de liens (normal, actif, parcouru) évite au développeur de les redessiner et ne repose pas sur la seule couleur.

## G18 — Pour une barre d'état d'objets, utiliser un gabarit d'emplac
Rôles : artiste
Date : 2026-11-12

Pour une barre d'état d'objets, utiliser un gabarit d'emplacement unique par taille d'icône, avec la couleur de bordure comme seul signal d'état.
