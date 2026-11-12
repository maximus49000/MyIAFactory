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

## G40 — Dans un roguelike, tester chaque événement et chaque boutiqu
Rôles : testeur
Date : 2026-11-12

Dans un roguelike, tester chaque événement et chaque boutique en appelant directement la fonction d'effet sur l'état de run. Faire de nombreux tirages pour les effets aléatoires et vérifier que le résultat est un cas exact connu. Vérifier aussi le taux observé contre la valeur d'équilibrage, et les bornes : plafond, solde jamais négatif.

## G41 — Pour tester des bonus temporaires dans un jeu, un script lan
Rôles : testeur
Date : 2026-11-12

Pour tester des bonus temporaires dans un jeu, un script lancé par le moteur manipule l'état de la partie. Il vérifie ajout, cumul, plafond, usure et remise à zéro, puis instancie la scène de jeu pour lire les valeurs réellement appliquées.

## G42 — Pour tester une navigation d'écrans sans interface, émettre
Rôles : dev
Date : 2026-11-12

Pour tester une navigation d'écrans sans interface, émettre le signal des boutons, attendre quelques images, puis vérifier le chemin de la scène courante et que l'ancienne instance n'est plus valide.

## G43 — Pour des maquettes cartoon pas enfantines : expressions exag
Rôles : designer
Date : 2026-11-12

Pour des maquettes cartoon pas enfantines : expressions exagérées (sourcils, dents, yeux mi-clos), silhouettes anguleuses, contours épais et ombres décalées ; éviter les formes rondes et les grands yeux.

## G44 — Pour un export signé d'un moteur de jeu, passer le chemin, l
Rôles : livreur
Date : 2026-11-12

Pour un export signé d'un moteur de jeu, passer le chemin, l'alias et le mot de passe du keystore par variables d'environnement, puis contrôler le code retour, la date et la taille du paquet produit.

## G45 — Dans un roguelike de cartes, vérifier automatiquement que le
Rôles : designer, dev
Date : 2026-11-12

Dans un roguelike de cartes, vérifier automatiquement que le pool de chaque personnage contient, à chaque rareté proposée, de quoi remplir chaque contrainte de tirage des récompenses.

## G46 — Quand on ajoute un type de récompense pendant le design d'un
Rôles : designer
Date : 2026-11-12

Quand on ajoute un type de récompense pendant le design d'un roguelike, le distinguer d'abord des récompenses existantes, réutiliser un nœud existant de la carte plutôt que d'en créer un, et dire dans quelle étape il entre et quelles autres étapes il touche.

## G47 — Dans un tirage sans remise d'effets qui se cumulent sur une
Rôles : designer
Date : 2026-11-12

Dans un tirage sans remise d'effets qui se cumulent sur une partie, vérifier automatiquement que le pool remplit chaque offre au pire cas : effets déjà pris plus effets qu'ils excluent, dans chaque famille.

## G48 — Dans un roguelike, vérifier qu'un événement qui termine la r
Rôles : testeur, dev
Date : 2026-11-12

Dans un roguelike, vérifier qu'un événement qui termine la run (mort par piège) ne lance pas de temporisation ni d'accès à l'arbre de scène après la libération du nœud ; la console doit rester sans erreur.

## G49 — Dans un roguelike difficile, un robot de test même peu fauti
Rôles : testeur
Date : 2026-11-12

Dans un roguelike difficile, un robot de test même peu fautif peut ne jamais gagner. Prévoir un mode robot parfait pour exercer la victoire en run complète, en plus de la vérification des écrans de fin par un script d'état.

## G50 — Pour tester l'écran de victoire d'un roguelike avec un robot
Rôles : dev
Date : 2026-11-12

Pour tester l'écran de victoire d'un roguelike avec un robot imparfait, faire passer le robot en mode sans erreur et sans risque quand il lui reste une seule vie.

## G51 — Quand plusieurs clés de signature candidates existent, liste
Rôles : livreur
Date : 2026-11-12

Quand plusieurs clés de signature candidates existent, lister leurs noms, tailles et dates sans les ouvrir, puis demander à l'utilisateur laquelle utiliser et son alias.

## G52 — Pour un export signé destiné à une livraison, ne jamais rete
Rôles : livreur
Date : 2026-11-12

Pour un export signé destiné à une livraison, ne jamais retenir le keystore de debug fourni par le moteur ou le SDK : demander à l'utilisateur sa clé de release, son chemin et son alias avant le build.

## G53 — Quand un robot de test accélère le temps, vérifier l'écran d
Rôles : testeur
Date : 2026-11-12

Quand un robot de test accélère le temps, vérifier l'écran de fin au moment où le journal signale la fin, car un retour automatique peut le faire disparaître avant le contrôle.

## G54 — Avant un export signé d'un moteur de jeu, si seule une clé d
Rôles : livreur
Date : 2026-11-12

Avant un export signé d'un moteur de jeu, si seule une clé de debug est trouvée, la présenter comme choix explicite et ne jamais l'utiliser par défaut pour une release.

## G55 — Dans un roguelike, quand un nouveau type d'ennemi donne une
Rôles : designer
Date : 2026-11-12

Dans un roguelike, quand un nouveau type d'ennemi donne une récompense qui ressemble à un tirage existant, lui donner un stock à lui plutôt que de piocher dans le stock commun, pour ne pas fausser le contrôle du tirage au pire cas.

## G56 — Dans un roguelike à plusieurs personnages, le point faible d
Rôles : designer
Date : 2026-11-12

Dans un roguelike à plusieurs personnages, le point faible d'un ennemi commun doit pouvoir être atteint avec des moyens que tous les personnages ont, jamais avec la mécanique propre d'un seul.

## G57 — Pour une carte générée dont des règles valent sur chaque che
Rôles : designer, dev, equilibreur
Date : 2026-11-12

Pour une carte générée dont des règles valent sur chaque chemin, écrire un générateur de référence avec réparation, le vérifier sur des centaines de graines, et dire de combien la réparation éloigne la répartition voulue.

## G58 — Quand les intentions d'un ennemi tournent en boucle avec un
Rôles : designer, dev
Date : 2026-11-12

Quand les intentions d'un ennemi tournent en boucle avec un départ au hasard, vérifier qu'une intention qui n'a de sens qu'après une autre (fuite après un vol, coup après une préparation) ne peut pas tomber en premier.
