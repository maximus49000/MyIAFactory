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

## G19 — Construire les emblèmes pixel art à partir d'un masque de pi
Rôles : artiste
Date : 2026-11-12

Construire les emblèmes pixel art à partir d'un masque de pixels, puis calculer contour, reflet et ombre depuis les voisins, garantit des couleurs conformes à la palette sans retouche manuelle.

## G20 — Un script qui dessine du texte avec une police bitmap partie
Rôles : artiste
Date : 2026-11-12

Un script qui dessine du texte avec une police bitmap partielle doit lever une erreur sur tout caractère absent, plutôt que de l'ignorer.

## G21 — Pour une musique en boucle, initialiser le filtre avec la fi
Rôles : artiste
Date : 2026-11-12

Pour une musique en boucle, initialiser le filtre avec la fin du tampon et le faire passer deux fois, afin que la jonction reste continue.

## G22 — Pour un export Android signé d'un moteur de jeu, transmettre
Rôles : livreur
Date : 2026-11-12

Pour un export Android signé d'un moteur de jeu, transmettre le chemin, l'alias et le mot de passe du keystore par variables d'environnement, jamais dans le fichier de preset, et vérifier la signature de l'APK obtenu.

## G23 — Un avertissement de format de keystore n'est pas un blocage
Rôles : livreur
Date : 2026-11-12

Un avertissement de format de keystore n'est pas un blocage : vérifier le format attendu par l'outil de signature avant de migrer.

## G24 — Pour un jeu à musique en boucle, générer sons et musiques pa
Rôles : artiste
Date : 2026-11-12

Pour un jeu à musique en boucle, générer sons et musiques par un script en Python pur (module wave, oscillateurs, bruit) évite toute licence externe, et un script de vérification contrôle format, niveau, écrêtage et continuité de boucle.

## G25 — Pour des icônes de carte de progression, doubler la couleur
Rôles : artiste
Date : 2026-11-12

Pour des icônes de carte de progression, doubler la couleur par une silhouette distincte (pointes, anneau lisse, taille) garde les types de nœuds lisibles à petite taille et pour les daltoniens.

## G26 — Pour un jeu à carte de nœuds, fournir un marqueur de sélecti
Rôles : artiste, dev
Date : 2026-11-12

Pour un jeu à carte de nœuds, fournir un marqueur de sélection distinct des icônes et trois styles de liens (normal, actif, parcouru) évite au développeur de les redessiner et ne repose pas sur la seule couleur.

## G27 — Pour une barre d'état d'objets, utiliser un gabarit d'emplac
Rôles : artiste
Date : 2026-11-12

Pour une barre d'état d'objets, utiliser un gabarit d'emplacement unique par taille d'icône, avec la couleur de bordure comme seul signal d'état.

## G28 — Construire les emblèmes pixel art à partir d'un masque de pi
Rôles : artiste
Date : 2026-11-12

Construire les emblèmes pixel art à partir d'un masque de pixels, puis calculer contour, reflet et ombre depuis les voisins, garantit des couleurs conformes à la palette sans retouche manuelle.

## G29 — Quand un rapport est limité à un nombre d'images par message
Rôles : dev
Date : 2026-11-12

Quand un rapport est limité à un nombre d'images par message, n'y mettre que les plus parlantes et répartir les autres dans les comptes rendus par élément.

## G30 — Un robot de test qui gagne toujours prouve l'enchaînement du
Rôles : dev
Date : 2026-11-12

Un robot de test qui gagne toujours prouve l'enchaînement du jeu, pas sa difficulté ; l'équilibrage demande un humain ou un robot imparfait.

## G31 — Pour un export Android signé, localiser l'outil de signature
Rôles : livreur
Date : 2026-11-12

Pour un export Android signé, localiser l'outil de signature dans le SDK plutôt que supposer qu'il est sur le PATH, puis vérifier la signature de l'APK (schémas v2/v3).

## G32 — Pour contrôler qu'aucun mot de passe n'est écrit dans un fic
Rôles : livreur
Date : 2026-11-12

Pour contrôler qu'aucun mot de passe n'est écrit dans un fichier livré, afficher seulement le nom de la clé concernée et jamais sa valeur.

## G33 — Pour un export signé, demander à l'utilisateur le chemin et
Rôles : livreur
Date : 2026-11-12

Pour un export signé, demander à l'utilisateur le chemin et l'alias du keystore avant de lancer le build ; ne jamais deviner l'emplacement d'une clé de signature.

## G34 — Dans un roguelike d'action, équilibrer avec un robot de test
Rôles : designer, testeur
Date : 2026-11-12

Dans un roguelike d'action, équilibrer avec un robot de test imparfait (taux d'erreur réglable), mesurer le coût réel d'un combat, puis caler une simulation de runs sur ces mesures pour comparer les réglages.

## G35 — Avant un export signé, lister les clés de signature candidat
Rôles : livreur
Date : 2026-11-12

Avant un export signé, lister les clés de signature candidates sans lire leurs secrets, puis demander à l'utilisateur quelle clé et quel alias utiliser.

## G36 — Quand plusieurs clés de signature candidates existent, deman
Rôles : livreur
Date : 2026-11-12

Quand plusieurs clés de signature candidates existent, demander à l'utilisateur laquelle utiliser (chemin et alias) avant tout export signé ; ne jamais en supprimer aucune.

## G37 — Dans un roguelike, un robot de test avec un taux d'erreur fa
Rôles : testeur
Date : 2026-11-12

Dans un roguelike, un robot de test avec un taux d'erreur faible produit à la fois victoires et défaites, et vérifie les deux écrans de fin.

## G38 — Quand on déplace une valeur d'équilibrage vers une constante
Rôles : dev
Date : 2026-11-12

Quand on déplace une valeur d'équilibrage vers une constante, brancher à la fois le libellé affiché et l'effet réel sur cette constante.

## G39 — Pour une signature Android, si plusieurs fichiers de clé exi
Rôles : livreur
Date : 2026-11-12

Pour une signature Android, si plusieurs fichiers de clé existent, demander à l'utilisateur lequel utiliser et son alias avant de lancer l'export signé.
