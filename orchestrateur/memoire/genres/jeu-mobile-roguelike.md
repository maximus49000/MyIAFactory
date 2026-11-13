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

## G59 — Dans un roguelike, chaque événement à choix doit garder au m
Rôles : designer, qa
Date : 2026-11-13

Dans un roguelike, chaque événement à choix doit garder au moins un choix sans risque qui ne demande aucune ressource, et un contrôle automatique le vérifie.

## G60 — Quand une ligne du cahier regroupe plusieurs cartes, les com
Rôles : designer
Date : 2026-11-13

Quand une ligne du cahier regroupe plusieurs cartes, les compter une à une avant de remplir une réserve de taille fixée, et signaler le choix fait pour rester dans la taille.

## G61 — Quand une contrainte de tirage de récompense est retirée, re
Rôles : designer
Date : 2026-11-13

Quand une contrainte de tirage de récompense est retirée, recalculer ce que son repli garantissait : un type absent à certaines raretés peut disparaître des offres.

## G62 — Dans un roguelike de cartes, quand l'utilisateur retire une
Rôles : designer
Date : 2026-11-13

Dans un roguelike de cartes, quand l'utilisateur retire une contrainte d'un tirage, vérifier chaque autre tirage qui l'appliquait avant de supposer qu'il veut la garder ailleurs.

## G63 — Quand un prompt de génération peut produire plusieurs assets
Rôles : designer
Date : 2026-11-13

Quand un prompt de génération peut produire plusieurs assets, le plan de génération compte séparément les générations (le coût) et les assets obtenus, et dit pour chaque génération quels fichiers elle donne.

## G64 — Un robot de test qui ne fait que combattre sous-estime la vi
Rôles : dev
Date : 2026-11-13

Un robot de test qui ne fait que combattre sous-estime la victoire d'une run complète, parce qu'il ne profite pas des soins, achats et événements : le dire dans le rapport d'équilibrage et lui donner ces actions avant de conclure.

## G65 — Quand un jeu permet de voir à l'avance ce qui attend sur cha
Rôles : dev
Date : 2026-11-13

Quand un jeu permet de voir à l'avance ce qui attend sur chaque nœud, attribuer les contenus au niveau entier (ordre mélangé selon la graine, sans répétition tant que la liste suffit) et faire lire cette même attribution par l'aperçu et par le jeu.

## G66 — Un nœud d'interface créé par le code puis ajouté à la scène
Rôles : dev
Date : 2026-11-13

Un nœud d'interface créé par le code puis ajouté à la scène doit avoir une position et une taille explicites, ainsi que ses enfants plein écran ; il faut relire la capture réelle de l'écran avant de rendre.

## G67 — Dans un jeu à carte de nœuds, un test d'issue aléatoire d'un
Rôles : dev
Date : 2026-11-13

Dans un jeu à carte de nœuds, un test d'issue aléatoire d'un type de nœud doit partir d'un nœud réellement de ce type, sinon la branche testée n'est jamais atteinte.

## G68 — Quand un retour dit qu'une version améliorée d'une carte n'a
Rôles : dev
Date : 2026-11-13

Quand un retour dit qu'une version améliorée d'une carte n'a pas d'effet, comparer pour chaque carte le texte de l'amélioration à ce que le moteur applique à ce niveau, et tester la version de base et l'améliorée avec les mêmes données.

## G69 — Quand une version doit être validée par une personne, vérifi
Rôles : dev
Date : 2026-11-13

Quand une version doit être validée par une personne, vérifier ce qu'elle voit au premier lancement avec une sauvegarde vide, pas avec le profil de test ; si du contenu est verrouillé par progression, prévoir un réglage d'essai dans les données qui le rend accessible.

## G70 — Un titre de calque modal ne doit pas recouvrir la barre d'en
Rôles : dev
Date : 2026-11-13

Un titre de calque modal ne doit pas recouvrir la barre d'en-tête de l'écran ; à vérifier sur capture réelle.

## G71 — Une capture d'écran de moteur de jeu se fait dans une fenêtr
Rôles : dev
Date : 2026-11-13

Une capture d'écran de moteur de jeu se fait dans une fenêtre réelle ; le mode sans interface ne rend pas l'image.

## G72 — Une capture plein écran peut sortir plus petite que la résol
Rôles : dev
Date : 2026-11-13

Une capture plein écran peut sortir plus petite que la résolution cible à cause de la barre du système : vérifier la taille de chaque image avant de la rendre.

## G73 — Un panneau ouvert par-dessus un écran peut recouvrir des tex
Rôles : dev
Date : 2026-11-13

Un panneau ouvert par-dessus un écran peut recouvrir des textes et des cartes sans qu'aucun test ne le voie : relire chaque capture avant de rendre.

## G74 — Quand un contrôle impose un ordre entre catégories d'adversa
Rôles : equilibreur
Date : 2026-11-13

Quand un contrôle impose un ordre entre catégories d'adversaires (normal < élite < champion < boss), lire cet ordre avant de régler un adversaire : une baisse du dernier de la chaîne oblige à baisser les précédents.

## G75 — Une capture d'écran d'un moteur de jeu doit se faire dans un
Rôles : dev
Date : 2026-11-13

Une capture d'écran d'un moteur de jeu doit se faire dans une fenêtre sans bordure, à la résolution cible, réimposée après les premières images ; le plein écran du système peut réduire la hauteur.

## G76 — Pour un habillage 2D généré par code, utiliser des fonctions
Rôles : graphiste
Date : 2026-11-13

Pour un habillage 2D généré par code, utiliser des fonctions de contour communes (polygone, ovale, membre) et un jeu de sourcils et de paupières par personnage : l'expression fait le caractère à moindre coût. Après chaque changement, relire les captures aux endroits où un personnage touche une bulle ou le bord de l'écran.

## G77 — Un réglage de test qui montre tout masque le déblocage : une
Rôles : dev
Date : 2026-11-13

Un réglage de test qui montre tout masque le déblocage : une capture ou un test faits avec ce réglage ne prouvent pas ce que voit une installation neuve.

## G78 — Quand des contrôles imposent un ordre de PV entre catégories
Rôles : equilibreur
Date : 2026-11-13

Quand des contrôles imposent un ordre de PV entre catégories et entre niveaux, baisser un adversaire du haut de la chaîne oblige à baisser tous ceux qui le dépassent ; lire ces bornes avant l'essai, et déclarer comme calculées les valeurs ajustées par ricochet si le robot ne les mesure pas.

## G79 — Pour un habillage 2D généré par code, regrouper les icônes d
Rôles : graphiste
Date : 2026-11-13

Pour un habillage 2D généré par code, regrouper les icônes dans une classe de dessin à repère normalisé associée à une table id→forme ; pour des captures sans écran, lancer le moteur sous un écran virtuel avec rendu OpenGL logiciel.

## G80 — Un jeu testé seulement par ses tests unitaires peut passer s
Rôles : qa
Date : 2026-11-13

Un jeu testé seulement par ses tests unitaires peut passer sans que ses écrans, ses textes ou son orientation soient vérifiés ; ces points demandent un parcours complet sur appareil ou émulateur.

## G81 — Une suite de tests unitaires verte ne prouve ni le parcours
Rôles : qa
Date : 2026-11-13

Une suite de tests unitaires verte ne prouve ni le parcours du joueur ni le rendu : le parcours complet sur appareil ou émulateur reste une étape distincte.

## G82 — Une suite de tests unitaires verte ne prouve pas le parcours
Rôles : qa
Date : 2026-11-13

Une suite de tests unitaires verte ne prouve pas le parcours du joueur ; le parcours complet sur appareil ou émulateur est une étape distincte.

## G83 — Pour un jeu mobile, la lisibilité et la mise en page se véri
Rôles : designer, dev, qa
Date : 2026-11-13

Pour un jeu mobile, la lisibilité et la mise en page se vérifient d'abord par des captures du moteur à la résolution de référence et un contrôle automatique de chaque texte ; l'émulateur ne sert plus qu'à confirmer le rendu dans le paquet.

## G84 — Après chaque export d'un paquet, vérifier que les fichiers d
Rôles : release
Date : 2026-11-13

Après chaque export d'un paquet, vérifier que les fichiers de données embarqués sont identiques à ceux du dépôt, et refaire l'export si ce n'est pas le cas.

## G85 — Un paquet destiné à la publication doit être signé avec une
Rôles : release
Date : 2026-11-13

Un paquet destiné à la publication doit être signé avec une clé fournie par son propriétaire ; sans elle, le dire et signaler le paquet comme version de débogage.

## G86 — Un paquet signé avec une clé de débogage n'est pas une versi
Rôles : release
Date : 2026-11-13

Un paquet signé avec une clé de débogage n'est pas une version de publication : la clé de publication est fournie par le propriétaire du projet, hors du dépôt.

## G87 — Un paquet signé avec la clé de débogage du poste n'est pas u
Rôles : release
Date : 2026-11-13

Un paquet signé avec la clé de débogage du poste n'est pas une version de publication : la clé vient du propriétaire du projet, hors du dépôt, et l'agent ne la crée jamais.

## G88 — Un test sur émulateur n'est réussi que si ses captures montr
Rôles : tous
Date : 2026-11-13

Un test sur émulateur n'est réussi que si ses captures montrent l'application : une capture noire, uniforme ou d'une invite système est un échec, à détecter par le test lui-même. Sur un émulateur sans fenêtre, un rendu Vulkan peut rester noir : préférer un rendu OpenGL de compatibilité et confirmer les invites système par adb avant le lancement.

## G89 — Pour contrôler un paquet d'application, comparer chaque fich
Rôles : release
Date : 2026-11-13

Pour contrôler un paquet d'application, comparer chaque fichier de données du dépôt au contenu décompressé de chaque entrée du paquet, octet par octet, et ne pas se fier à la seule présence des fichiers.

## G90 — Avant de demander l'accord pour un test sur émulateur, vérif
Rôles : release, qa
Date : 2026-11-13

Avant de demander l'accord pour un test sur émulateur, vérifier quel appareil virtuel existe sans le lancer, et le nommer dans la demande.

## G91 — Une tâche de test sur émulateur exige le shell : l'ouvrir au
Rôles : qa
Date : 2026-11-13

Une tâche de test sur émulateur exige le shell : l'ouvrir au métier concerné avant de lancer la tâche, sinon l'agent se bloque sans pouvoir vérifier ses corrections.
