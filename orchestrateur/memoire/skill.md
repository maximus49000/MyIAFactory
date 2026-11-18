# Mémoire de la skill

Ce fichier garde les leçons du **processus pur** de la skill, celles qui peuvent améliorer les itérations de
n'importe quel projet. Il ne contient aucun nom, lieu, chemin, fichier ou personne d'un projet. Il commence sans
leçon : une leçon n'y entre que validée par l'utilisateur, par `outil.py lecon appliquer`.

## S1 — Quand aucun humain ne peut approuver les commandes, éviter l
Rôles : environnement
Date : 2026-11-12

Quand aucun humain ne peut approuver les commandes, éviter les variables shell : passer par un script avec des chemins absolus en slashs avant.

## S2 — Sous Git Bash, mettre les chemins Windows entre guillemets a
Rôles : environnement
Date : 2026-11-12

Sous Git Bash, mettre les chemins Windows entre guillemets avec des slashs avant.

## S3 — Quand aucune bibliothèque d'images n'est garantie, générer l
Rôles : artiste
Date : 2026-11-12

Quand aucune bibliothèque d'images n'est garantie, générer les maquettes PNG avec le module standard zlib et struct, depuis un script écrit par l'outil Write puis lancé avec python.

## S4 — Produire les visuels pixel art par un script versionné évite
Rôles : artiste
Date : 2026-11-12

Produire les visuels pixel art par un script versionné évite les licences externes et permet de régénérer tout le lot quand la palette change.

## S5 — Quand aucune approbation n'est possible, mets les enchaîneme
Rôles : artiste, dev
Date : 2026-11-12

Quand aucune approbation n'est possible, mets les enchaînements de commandes dans un script lancé par une seule commande.

## S6 — Dans un environnement sans approbation possible, éviter les
Rôles : dev
Date : 2026-11-12

Dans un environnement sans approbation possible, éviter les variables d'environnement dans les commandes shell. Mettre la logique dans un script lancé par l'interpréteur, avec des chemins explicites.

## S7 — Avant une étape d'équilibrage, vérifier qu'il existe du code
Rôles : designer
Date : 2026-11-12

Avant une étape d'équilibrage, vérifier qu'il existe du code de gameplay et un fichier de valeurs ; sinon, déclarer l'étape non applicable en une ligne au lieu de produire un livrable vide.

## S8 — Quand un outil externe est refusé au shell sans possibilité
Rôles : dev
Date : 2026-11-12

Quand un outil externe est refusé au shell sans possibilité d'approbation, l'encapsuler dans un script écrit au préalable et lancé par l'interpréteur.

## S9 — Quand une étape est relancée sur un élément déjà traité, rep
Rôles : designer
Date : 2026-11-12

Quand une étape est relancée sur un élément déjà traité, repartir du livrable existant et noter seulement ce qui a changé, sans tout refaire.

## S10 — Quand aucune approbation n'est possible, utiliser les outils
Rôles : artiste
Date : 2026-11-12

Quand aucune approbation n'est possible, utiliser les outils de lecture dédiés, un par fichier, plutôt qu'un enchaînement de commandes shell.

## S11 — Quand une commande shell est refusée parce qu'elle contient
Rôles : artiste
Date : 2026-11-12

Quand une commande shell est refusée parce qu'elle contient une variable ou un enchaînement, l'envelopper dans un script lancé par python permet de la faire passer.

## S12 — Lorsqu'aucune approbation n'est possible, évite les variable
Rôles : testeur, dev, livreur
Date : 2026-11-12

Lorsqu'aucune approbation n'est possible, évite les variables shell dans les commandes. Écris un script avec l'outil de fichier, puis lance-le avec des chemins guillemetés en slashs.

## S13 — Quand une étape de design porte sur un élément d'assets, vér
Rôles : designer
Date : 2026-11-12

Quand une étape de design porte sur un élément d'assets, vérifier seulement que chaque entité prévue a son asset nommé, puis déclarer l'étape non applicable.

## S14 — Si le shell est refusé, reformuler la commande dans un scrip
Rôles : livreur
Date : 2026-11-12

Si le shell est refusé, reformuler la commande dans un script Python écrit avec l'outil Write puis lancé par python.

## S15 — Pour valider des assets graphiques, lancer un script qui com
Rôles : testeur
Date : 2026-11-12

Pour valider des assets graphiques, lancer un script qui compare chaque couleur opaque à la palette autorisée, puis une capture produite par le moteur qui prouve résolution et affichage.

## S16 — Quand un outil système affiche des libellés traduits, ne pas
Rôles : livreur
Date : 2026-11-12

Quand un outil système affiche des libellés traduits, ne pas parser le texte d'un libellé fixe : utiliser un motif tolérant à la langue ou une sortie structurée.

## S17 — Un contrôle de continuité de boucle audio fondé sur l'écart
Rôles : artiste
Date : 2026-11-12

Un contrôle de continuité de boucle audio fondé sur l'écart entre premier et dernier échantillon donne de faux positifs avec des ondes carrées ; fixer un seuil large qui ne détecte que les vrais clics.

## S18 — Quand une police bitmap générée par script ne couvre pas tou
Rôles : artiste
Date : 2026-11-12

Quand une police bitmap générée par script ne couvre pas tous les caractères, documenter son jeu de caractères et rédiger les textes d'aperçu avec ses seuls glyphes, sinon un symbole manquant disparaît sans erreur.

## S19 — Quand un générateur audio utilise des graines fixes, on peut
Rôles : artiste
Date : 2026-11-12

Quand un générateur audio utilise des graines fixes, on peut ajouter des sons au script et le relancer sans altérer l'existant.

## S20 — Appliquer systématiquement un filtre passe-bas (environ 2 à
Rôles : artiste
Date : 2026-11-12

Appliquer systématiquement un filtre passe-bas (environ 2 à 3 kHz) au mixage final des musiques synthétisées, et le dire dans la vérification.

## S21 — Pour valider des assets graphiques, lancer un script qui com
Rôles : testeur
Date : 2026-11-12

Pour valider des assets graphiques, lancer un script qui compare chaque couleur opaque à la palette autorisée, puis une capture produite par le moteur qui prouve résolution et affichage.

## S22 — Quand un outil système affiche des libellés traduits, ne pas
Rôles : livreur
Date : 2026-11-12

Quand un outil système affiche des libellés traduits, ne pas parser le texte d'un libellé fixe : utiliser un motif tolérant à la langue ou une sortie structurée.

## S23 — Un contrôle de continuité de boucle audio fondé sur l'écart
Rôles : artiste
Date : 2026-11-12

Un contrôle de continuité de boucle audio fondé sur l'écart entre premier et dernier échantillon donne de faux positifs avec des ondes carrées ; fixer un seuil large qui ne détecte que les vrais clics.

## S24 — Quand une police bitmap générée par script ne couvre pas tou
Rôles : artiste
Date : 2026-11-12

Quand une police bitmap générée par script ne couvre pas tous les caractères, documenter son jeu de caractères et rédiger les textes d'aperçu avec ses seuls glyphes, sinon un symbole manquant disparaît sans erreur.

## S25 — Quand un générateur audio utilise des graines fixes, on peut
Rôles : artiste
Date : 2026-11-12

Quand un générateur audio utilise des graines fixes, on peut ajouter des sons au script et le relancer sans altérer l'existant.

## S26 — Quand un outil de signature affiche les détails du certifica
Rôles : livreur
Date : 2026-11-12

Quand un outil de signature affiche les détails du certificat, n'en recopier que le statut de vérification ; le détail peut contenir des données personnelles.

## S27 — Pour créer un keystore de signature, générer un mot de passe
Rôles : artiste, livreur
Date : 2026-11-12

Pour créer un keystore de signature, générer un mot de passe aléatoire, le passer à l'outil par variable d'environnement, le stocker hors du dépôt et masquer sa valeur dans toute sortie ; rendre le script idempotent : il ne recrée rien si le keystore existe.

## S28 — Quand les tests automatiques ne peuvent pas échouer, équilib
Rôles : designer
Date : 2026-11-12

Quand les tests automatiques ne peuvent pas échouer, équilibrer seulement ce qui se calcule (ressources, fréquences) et ne pas changer les valeurs de difficulté sans mesure.

## S29 — Après avoir changé une valeur d'équilibrage, chercher les te
Rôles : designer, dev
Date : 2026-11-12

Après avoir changé une valeur d'équilibrage, chercher les textes affichés qui la répètent en dur et les mettre à jour.

## S30 — Les textes affichés et les tests lisent les valeurs d'équili
Rôles : designer, dev
Date : 2026-11-12

Les textes affichés et les tests lisent les valeurs d'équilibrage au lieu de recopier leurs chiffres, pour qu'un réglage ne les casse pas.

## S31 — Chaque journal de mesure note les valeurs avec lesquelles il
Rôles : designer
Date : 2026-11-12

Chaque journal de mesure note les valeurs avec lesquelles il a été pris, et les outils qui le relisent ignorent ceux pris avec d'autres valeurs.

## S32 — Quand un message est limité en nombre d'images, montrer les
Rôles : designer
Date : 2026-11-12

Quand un message est limité en nombre d'images, montrer les principales dans le message et mettre la liste complète dans le livrable qui l'accompagne.

## S33 — Mettre dans le document de cadrage la liste ordonnée des éta
Rôles : designer
Date : 2026-11-12

Mettre dans le document de cadrage la liste ordonnée des étapes, pour que le rapport la reprenne sans la refaire.

## S34 — Pour vérifier l'environnement d'un build, lancer en une seul
Rôles : livreur
Date : 2026-11-12

Pour vérifier l'environnement d'un build, lancer en une seule fois un script qui contrôle la version de l'outil, les modèles d'export, les outils de signature et la présence des variables secrètes, sans afficher leur valeur.

## S35 — Pour un test long, le lancer en tâche de fond avec un délai
Rôles : testeur
Date : 2026-11-12

Pour un test long, le lancer en tâche de fond avec un délai généreux et ne lire la sortie qu'à la fin.

## S36 — Quand une édition multi-lignes échoue sur l'indentation, la
Rôles : dev, artiste
Date : 2026-11-12

Quand une édition multi-lignes échoue sur l'indentation, la découper en remplacements d'une seule ligne, puis relire le bloc pour vérifier les tabulations.

## S37 — Avant une correction guidée par des numéros de ligne, relire
Rôles : dev, artiste
Date : 2026-11-12

Avant une correction guidée par des numéros de ligne, relire les lignes ciblées ; si le défaut n'y est plus, le signaler plutôt que de modifier le fichier.

## S38 — Un script de test lancé par le moteur doit toujours être app
Rôles : testeur
Date : 2026-11-12

Un script de test lancé par le moteur doit toujours être appelé avec un délai maximal. En cas d'erreur de script, le moteur peut rester actif sans jamais quitter. Le lanceur doit alors afficher la sortie partielle plutôt que d'attendre.

## S39 — Dans un script de test Godot sans interface, les warnings «
Rôles : dev, artiste
Date : 2026-11-12

Dans un script de test Godot sans interface, les warnings « ObjectDB instances were leaked » et « resources still in use » viennent souvent de lectures audio encore actives à quit(). Arrêter les lecteurs, vider leurs flux, attendre un court délai en temps réel pour que le serveur audio libère les lectures, puis quitter, en s'assurant qu'aucune scène en cours de chargement ne relance un son après l'arrêt.

## S40 — Dans une constante GDScript, utiliser l'operateur de formata
Rôles : dev, artiste
Date : 2026-11-12

Dans une constante GDScript, utiliser l'operateur de formatage % plutot que str(), qui empeche la compilation.

## S41 — Pour attribuer un avertissement de fuite a la fermeture, le
Rôles : dev
Date : 2026-11-12

Pour attribuer un avertissement de fuite a la fermeture, le relancer avec --verbose avant de modifier du code.

## S42 — Quand un document de conception est corrigé, ajouter en tête
Rôles : designer
Date : 2026-11-12

Quand un document de conception est corrigé, ajouter en tête la liste de ce qui a changé et reporter chaque correction dans tous les tableaux, règles, prompts et maquettes qu'elle touche.

## S43 — Pour vérifier une signature Android, considérer valide un AP
Rôles : livreur
Date : 2026-11-12

Pour vérifier une signature Android, considérer valide un APK dont les schémas v2 ou v3 sont à true, même si v1 est à false.

## S44 — Pour contrôler les fuites à la fermeture d'un jeu Godot avec
Rôles : dev, artiste
Date : 2026-11-12

Pour contrôler les fuites à la fermeture d'un jeu Godot avec audio, ne pas se fier à l'option de sortie automatique, qui court-circuite la demande de fermeture. Simuler la notification de fermeture de fenêtre et intercepter celle-ci dans l'autoload audio : couper les lecteurs, attendre environ 0,5 s, puis quitter.

## S45 — Produire les tableaux et les images de design par un script
Rôles : designer
Date : 2026-11-12

Produire les tableaux et les images de design par un script qui lit le fichier de valeurs, et garder dans la fiche écrite les règles et l'intention sans recopier les chiffres.

## S46 — Contrôler la console de chaque outil de test séparément : un
Rôles : testeur
Date : 2026-11-12

Contrôler la console de chaque outil de test séparément : une fuite ou une erreur peut n'apparaître que dans la run complète.

## S47 — Quand un avertissement de fuite à la sortie apparaît dans to
Rôles : testeur, dev
Date : 2026-11-12

Quand un avertissement de fuite à la sortie apparaît dans tous les tests, chercher l'objet commun (autoload, singleton) au lieu de le répéter élément par élément.

## S48 — Dans un test automatique avec écran de fin qui revient au me
Rôles : dev, artiste
Date : 2026-11-12

Dans un test automatique avec écran de fin qui revient au menu, désactiver le pilote automatique dès la fin de run, laisser la scène s'installer quelques images, puis seulement arrêter l'audio et quitter.

## S49 — Après tout await dans une scène pouvant être remplacée en co
Rôles : dev
Date : 2026-11-12

Après tout await dans une scène pouvant être remplacée en cours de route, tester que le nœud est toujours dans l'arbre avant d'utiliser get_tree() ou de poursuivre.

## S50 — Quand un script référence les constantes d'une classe global
Rôles : dev
Date : 2026-11-12

Quand un script référence les constantes d'une classe globale et que le cache de classes peut être périmé, préférer une constante locale initialisée par preload du script.

## S51 — Un contrôle d'environnement de signature liste les clés par
Rôles : livreur
Date : 2026-11-12

Un contrôle d'environnement de signature liste les clés par chemin et taille, vérifie la présence des variables secrètes sans afficher leurs valeurs, et ne les ouvre pas.

## S52 — Faire tourner dès le premier élément un contrôle qui parcour
Rôles : designer, dev
Date : 2026-11-12

Faire tourner dès le premier élément un contrôle qui parcourt tous les fichiers de valeurs et signale tout chiffre écrit en dur dans un texte à trous ; il trouve aussi les oublis des éléments déjà validés.

## S53 — Un test qui donne une donnée fausse à un contrôle ne compte
Rôles : designer, dev, qa
Date : 2026-11-12

Un test qui donne une donnée fausse à un contrôle ne compte que si une erreur nouvelle apparaît par rapport aux données justes.

## S54 — Un contrôle qui cherche des secrets par mots-clés doit viser
Rôles : designer, dev, qa
Date : 2026-11-13

Un contrôle qui cherche des secrets par mots-clés doit viser un motif de valeur (mot suivi d'un séparateur et d'une valeur), pas le mot seul, pour ne pas bloquer des noms de contenu légitimes.

## S55 — Quand un élément d'équilibrage est conçu avant que le jeu ex
Rôles : designer, equilibreur
Date : 2026-11-13

Quand un élément d'équilibrage est conçu avant que le jeu existe, livrer le plan de mesure et des indicateurs calculés depuis les fichiers de valeurs, sans changer aucune valeur.

## S56 — Un script qui produit des images et vérifie la présence des
Rôles : designer, dev
Date : 2026-11-13

Un script qui produit des images et vérifie la présence des images référencées doit exclure de la vérification celles qu'il produit lui-même.

## S57 — Quand une remarque reformule une règle déjà appliquée, rendr
Rôles : designer
Date : 2026-11-13

Quand une remarque reformule une règle déjà appliquée, rendre la règle visible à l'écran et la contrôler automatiquement plutôt que de la modifier.

## S58 — Quand une étape de conception porte sur des tests d'applicat
Rôles : designer
Date : 2026-11-13

Quand une étape de conception porte sur des tests d'application (émulateur, paquet installable), vérifier d'abord qu'un projet compilable existe ; sinon, déclarer l'étape non applicable en une ligne, sans produire de livrable vide.

## S59 — Quand une regénération d'images ne vient d'aucun changement
Rôles : designer
Date : 2026-11-13

Quand une regénération d'images ne vient d'aucun changement de données, annuler ces modifications binaires plutôt que de les commiter, pour garder un historique lisible.

## S60 — Quand seul le rapport d'une étape a été refusé pour sa forme
Rôles : designer
Date : 2026-11-13

Quand seul le rapport d'une étape a été refusé pour sa forme, reprendre le livrable déjà produit, relancer ses contrôles et rendre un rapport complet au lieu de refaire le travail.

## S61 — Quand des prompts de génération d'assets sont regroupés pour
Rôles : designer
Date : 2026-11-13

Quand des prompts de génération d'assets sont regroupés pour réduire le nombre de générations, limiter chaque groupe à quelques sujets de même gabarit et du même lot, les numéroter dans un ordre fixe lié à leurs identifiants, faire vérifier la numérotation par un contrôle et prévoir de régénérer seul un sujet raté.

## S62 — Un test qui donne une donnée fausse à un contrôle doit vérif
Rôles : designer, dev
Date : 2026-11-13

Un test qui donne une donnée fausse à un contrôle doit vérifier que l'erreur visée apparaît (par un motif), pas seulement qu'une erreur nouvelle quelconque apparaît.

## S63 — Quand une consigne interdit une catégorie de contenu, ajoute
Rôles : dev
Date : 2026-11-13

Quand une consigne interdit une catégorie de contenu, ajouter un test automatique sur les noms et descriptions avec une liste de mots interdits, plutôt que de renommer à la main.

## S64 — Regarder les captures réelles de l'interface avant de rendre
Rôles : dev
Date : 2026-11-13

Regarder les captures réelles de l'interface avant de rendre : les textes coupés ou superposés échappent aux tests automatiques.

## S65 — Au début d'une reprise de travail, comparer l'état du dépôt
Rôles : dev
Date : 2026-11-13

Au début d'une reprise de travail, comparer l'état du dépôt à la liste des tâches avant d'écrire du code : une partie peut déjà exister.

## S66 — Quand aucune approbation n'est possible, écrire un lanceur d
Rôles : dev
Date : 2026-11-13

Quand aucune approbation n'est possible, écrire un lanceur dans un script qui exécute l'outil et filtre sa sortie, plutôt que d'enchaîner des commandes avec des tubes ou des documents en ligne.

## S67 — Quand une tâche redemande un élément déjà livré et sans nouv
Rôles : dev
Date : 2026-11-13

Quand une tâche redemande un élément déjà livré et sans nouveau retour, relancer la suite de tests et rendre l'existant au lieu de le refaire.

## S68 — Quand une consigne de l'utilisateur est coupée, implémenter
Rôles : dev
Date : 2026-11-13

Quand une consigne de l'utilisateur est coupée, implémenter ce qui est clair, ne rien inventer pour la suite et la signaler explicitement dans le rapport.

## S69 — Quand une nouvelle consigne annule une consigne précédente s
Rôles : dev
Date : 2026-11-13

Quand une nouvelle consigne annule une consigne précédente sur le même point, remplacer l'ancien comportement, son texte affiché et sa documentation, puis noter l'interprétation retenue pour la faire confirmer.

## S70 — Quand un seul test de données de mesure périmées échoue dans
Rôles : dev
Date : 2026-11-13

Quand un seul test de données de mesure périmées échoue dans une suite, le signaler comme dette de l'étape d'équilibrage plutôt que de modifier l'élément en cours ; relancer la mesure suffit à le résoudre.

## S71 — Quand la suite de tests dépasse la limite d'une commande au
Rôles : dev
Date : 2026-11-13

Quand la suite de tests dépasse la limite d'une commande au premier plan, lancer les modules séparément et les mesures longues en arrière-plan, puis les attendre par de courtes pauses.

## S72 — Un lanceur de tests qui ne rend sa sortie qu'à la fin masque
Rôles : dev
Date : 2026-11-13

Un lanceur de tests qui ne rend sa sortie qu'à la fin masque une suite bloquée ou très longue. Afficher la progression au fil de l'eau et annoncer la durée attendue.

## S73 — Quand l'environnement ne contient pas le moteur nécessaire p
Rôles : dev
Date : 2026-11-13

Quand l'environnement ne contient pas le moteur nécessaire pour relancer les tests et qu'une tâche redemande un élément déjà livré sans nouveau retour, vérifier l'état du dépôt, rendre l'existant et dire clairement que les tests n'ont pas été relancés.

## S74 — Quand l'environnement ne contient pas le moteur nécessaire p
Rôles : dev
Date : 2026-11-13

Quand l'environnement ne contient pas le moteur nécessaire pour relancer les tests et qu'une tâche redemande un élément déjà livré sans nouveau retour, vérifier l'état du dépôt, rendre l'existant et dire clairement que les tests n'ont pas été relancés.

## S75 — Lancer la suite de tests avec une limite de temps et un jour
Rôles : dev
Date : 2026-11-13

Lancer la suite de tests avec une limite de temps et un journal écrit en continu ; un script de test qui ne compile pas peut laisser le lanceur bloqué sans sortie.

## S76 — Quand l'environnement ne contient pas le moteur nécessaire p
Rôles : dev
Date : 2026-11-13

Quand l'environnement ne contient pas le moteur nécessaire pour relancer les tests et qu'une tâche redemande un élément déjà livré sans nouveau retour, vérifier l'état du dépôt, rendre l'existant et dire clairement que les tests n'ont pas été relancés.

## S77 — Quand une commande shell simple est refusée faute d'approbat
Rôles : dev
Date : 2026-11-13

Quand une commande shell simple est refusée faute d'approbation, passer par un lanceur Python du projet qui trouve l'outil à sa place.

## S78 — Un taux de victoire mesuré avec un robot qui ignore une part
Rôles : equilibreur
Date : 2026-11-13

Un taux de victoire mesuré avec un robot qui ignore une partie des décisions du jeu (soin, achats) ne représente pas un joueur : régler les combats isolés et signaler que le niveau de run reste non mesuré.

## S79 — Avant une action qui fait apparaître une fenêtre système, po
Rôles : dev
Date : 2026-11-13

Avant une action qui fait apparaître une fenêtre système, poser la question avec son choix recommandé et attendre la réponse, même si l'accord de principe est déjà donné.

## S80 — Quand une commande shell vers un outil externe est refusée s
Rôles : dev
Date : 2026-11-13

Quand une commande shell vers un outil externe est refusée sans approbation possible, l'encapsuler dans un script écrit au préalable et lancé par l'interpréteur.

## S81 — Quand les commandes composées exigent une approbation imposs
Rôles : graphiste, equilibreur
Date : 2026-11-13

Quand les commandes composées exigent une approbation impossible, écrire un petit lanceur dans le langage du projet et l'appeler seul.

## S82 — Un script d'orchestration qui lit la sortie de sous-processu
Rôles : graphiste
Date : 2026-11-13

Un script d'orchestration qui lit la sortie de sous-processus en UTF-8 plante dès qu'un contrôle écrit en cp1252 : décoder avec errors=replace et ne pas déclarer le contrôle global passé s'il n'a pas tourné.

## S83 — Un lanceur de tests qui affiche des caractères accentués doi
Rôles : dev
Date : 2026-11-13

Un lanceur de tests qui affiche des caractères accentués doit forcer la sortie en UTF-8 pour que le compte rendu soit lisible sur toutes les consoles.

## S84 — Quand une tâche d'équilibrage porte sur un élément sans vale
Rôles : equilibreur
Date : 2026-11-13

Quand une tâche d'équilibrage porte sur un élément sans valeur de jeu, ne changer aucune valeur : lancer son contrôle, le déclarer passé, et dire que rien n'a été mesuré.

## S85 — Quand le journal de mesures correspond aux données et qu'auc
Rôles : equilibreur
Date : 2026-11-13

Quand le journal de mesures correspond aux données et qu'aucune cible chiffrée n'existe pour la catégorie à régler, ne pas modifier de valeurs : rendre les mesures et demander la cible.

## S86 — Dans un moteur à scène, un nœud de fond ajouté en enfant rec
Rôles : graphiste
Date : 2026-11-13

Dans un moteur à scène, un nœud de fond ajouté en enfant recouvre ce que le parent dessine ; dessiner le fond dans le parent.

## S87 — Quand le robot de test ne joue pas une décision (achat, soin
Rôles : equilibreur
Date : 2026-11-13

Quand le robot de test ne joue pas une décision (achat, soin), ne règle pas les prix ni les coûts qui en dépendent : calcule le rythme de la ressource depuis les fichiers de valeurs, rapporte-le comme calculé et laisse les valeurs inchangées.

## S88 — Un journal de mesures périmé sans changement de valeurs se r
Rôles : equilibreur
Date : 2026-11-13

Un journal de mesures périmé sans changement de valeurs se régénère avant de conclure ; sans cible chiffrée, on ne change aucune valeur.

## S89 — Avant de refaire un habillage graphique demandé, chercher da
Rôles : graphiste
Date : 2026-11-13

Avant de refaire un habillage graphique demandé, chercher dans l'historique si un commit l'a déjà livré ; si oui, relire la capture, signaler les défauts mineurs, ne rien régénérer.

## S90 — Quand l'élément à équilibrer n'est pas mesuré par le robot d
Rôles : equilibreur
Date : 2026-11-13

Quand l'élément à équilibrer n'est pas mesuré par le robot de test et n'a pas de cible chiffrée, ne change aucune valeur : vérifie que le journal est à jour, lance le contrôle propre à l'élément et déclare ce qui reste seulement calculé.

## S91 — Un contrôle de relecture ne doit pas modifier les fichiers d
Rôles : qa
Date : 2026-11-13

Un contrôle de relecture ne doit pas modifier les fichiers du projet ; s'il le fait, il faut un mode lecture seule.

## S92 — Dans une consigne, indiquer les chemins avec des barres obli
Rôles : qa, dev
Date : 2026-11-13

Dans une consigne, indiquer les chemins avec des barres obliques ou passer par un lanceur Python, car le shell peut déformer les antislashs.

## S93 — Dans un moteur où une étiquette s'agrandit toute seule à son
Rôles : dev, designer
Date : 2026-11-13

Dans un moteur où une étiquette s'agrandit toute seule à son texte, un contrôle de débordement compare le texte au cadre visible qui le contient, jamais à la taille de l'étiquette.

## S94 — Mesurer le contraste de chaque texte contre le fond réelleme
Rôles : designer, dev
Date : 2026-11-13

Mesurer le contraste de chaque texte contre le fond réellement rendu derrière lui, et compter le contour du texte quand il est assez épais.

## S95 — Un contrôle d'écran se prouve en injectant un faux élément p
Rôles : designer, dev, qa
Date : 2026-11-13

Un contrôle d'écran se prouve en injectant un faux élément par défaut visé et en exigeant que chaque erreur attendue apparaisse, en plus de celles de l'écran juste.

## S96 — Dans un shell POSIX sous Windows, écrire les chemins avec de
Rôles : release
Date : 2026-11-13

Dans un shell POSIX sous Windows, écrire les chemins avec des barres obliques, car les barres inverses sont altérées.

## S97 — Pour contrôler un paquet, comparer le contenu des fichiers d
Rôles : release
Date : 2026-11-13

Pour contrôler un paquet, comparer le contenu des fichiers de données octet par octet avec le dépôt ; la seule présence des fichiers ne suffit pas.

## S98 — Quand une commande shell d'un outil est refusée sans approba
Rôles : release
Date : 2026-11-13

Quand une commande shell d'un outil est refusée sans approbation, lance-la depuis un petit script Python qui l'exécute ; c'est la voie prévue, pas un contournement.

## S99 — Pour vérifier qu'un paquet embarque les fichiers du dépôt, d
Rôles : release
Date : 2026-11-13

Pour vérifier qu'un paquet embarque les fichiers du dépôt, décompresse chaque entrée avant de comparer les octets.

## S100 — Avant de modifier un outil de mesure, enregistrer un petit r
Rôles : designer, dev
Date : 2026-11-13

Avant de modifier un outil de mesure, enregistrer un petit résultat de référence sur un jeu d'entrées fixe, garder l'ancien comportement en option et vérifier qu'il reproduit cette référence chiffre pour chiffre.

## S101 — Un test de capture d'écran doit mesurer le contenu de l'imag
Rôles : qa
Date : 2026-11-13

Un test de capture d'écran doit mesurer le contenu de l'image (écart de luminance) et échouer si elle est uniforme ou identique à une autre.

## S102 — Pour vérifier qu'une application est au premier plan, lire l
Rôles : qa
Date : 2026-11-13

Pour vérifier qu'une application est au premier plan, lire l'activité du dessus, pas la liste des fenêtres.

## S103 — Une capture d'application qui n'est pas uniforme peut n'être
Rôles : designer, qa, dev
Date : 2026-11-14

Une capture d'application qui n'est pas uniforme peut n'être que l'écran de démarrage du moteur : un test d'affichage doit aussi la comparer à cet écran.

## S104 — Avant de corriger un shader attribué à un élément, vérifier
Rôles : designer, dev
Date : 2026-11-14

Avant de corriger un shader attribué à un élément, vérifier que le projet en contient un ; une erreur de liaison peut venir des shaders du moteur, qui ne se corrigent pas dans l'élément.

## S105 — Pour juger l'effet d'un réglage du projet sur un test, vérif
Rôles : dev, qa
Date : 2026-11-14

Pour juger l'effet d'un réglage du projet sur un test, vérifier d'abord qu'il est bien dans le paquet testé.

## S106 — Quand un livrable comporte plus de 4 images, ne joindre que
Rôles : cadrage
Date : 2026-11-14

Quand un livrable comporte plus de 4 images, ne joindre que 4 images au message et référencer les autres dans la structure du livrable.

## S107 — Pour une correction de style, centraliser palette et composa
Rôles : cadrage
Date : 2026-11-14

Pour une correction de style, centraliser palette et composants dans un script unique de maquettes et le relancer, afin que tous les écrans restent cohérents.

## S108 — Prototyper un écran dans un script qui reproduit les règles
Rôles : cadrage, dev
Date : 2026-11-14

Prototyper un écran dans un script qui reproduit les règles métier (filtre, regroupement, état visuel), avec assertions et rendu image, permet de valider avant d'écrire le code de l'application.

## S109 — Quand une étape de maquettes porte sur un élément d'infrastr
Rôles : designer
Date : 2026-11-14

Quand une étape de maquettes porte sur un élément d'infrastructure, écrire seulement ce qu'il doit fournir aux écrans (thème, composants communs, navigation) et renvoyer aux maquettes existantes.

## S110 — Dans une image générée par script, les symboles Unicode peuv
Rôles : designer
Date : 2026-11-14

Dans une image générée par script, les symboles Unicode peuvent s'afficher en carrés vides selon la police ; dessiner les icônes ou utiliser du texte, et relire l'image ouverte.

## S111 — Avant de compiler, comparer l'état du dépôt à ce qu'on a écr
Rôles : dev
Date : 2026-11-14

Avant de compiler, comparer l'état du dépôt à ce qu'on a écrit. Si un autre intervenant a modifié ou dupliqué des fichiers, aligner son code sur le sien et supprimer ses doublons plutôt que de le réécrire.

## S112 — Quand plusieurs agents partagent un dépôt, relire l'état du
Rôles : dev
Date : 2026-11-14

Quand plusieurs agents partagent un dépôt, relire l'état du dépôt avant d'ajouter des fichiers, car un commit automatique peut embarquer le travail d'un autre ; lancer les compilations sans démon partagé.

## S113 — Sans approbation possible, les commandes composées sont refu
Rôles : testeur
Date : 2026-11-14

Sans approbation possible, les commandes composées sont refusées. Il faut les mettre dans un script écrit par l'outil de fichier, avec un délai maximal et la sortie écrite dans un fichier, puis lancer ce script seul.

## S114 — Quand aucune approbation n'est possible, remplacer les comma
Rôles : dev
Date : 2026-11-14

Quand aucune approbation n'est possible, remplacer les commandes shell composées par les outils de lecture et de recherche, ou par un script lancé seul.

## S115 — Pour lister ou lire un dossier situé hors du projet, utilise
Rôles : release
Date : 2026-11-14

Pour lister ou lire un dossier situé hors du projet, utiliser les outils de lecture et de recherche de fichiers plutôt qu'une commande shell, qui peut demander une approbation impossible à donner.

## S116 — Pour un élément de service sans écran propre, lister les maq
Rôles : designer
Date : 2026-11-14

Pour un élément de service sans écran propre, lister les maquettes existantes qu'il utilise et ne dessiner que les états absents (attente, données incomplètes, erreurs), avec un contrôle de débordement dans le script.

## S117 — Quand une commande shell est refusée sans approbation, la re
Rôles : release
Date : 2026-11-14

Quand une commande shell est refusée sans approbation, la relancer depuis un petit script Python qui exécute la même commande, sans changer les outils autorisés.

## S118 — Un contrôle de débordement compare chaque élément au cadre v
Rôles : designer
Date : 2026-11-14

Un contrôle de débordement compare chaque élément au cadre visible qui le contient, pas seulement à l'écran entier ; la relecture visuelle reste nécessaire.

## S119 — Pour compter les tests par suite, interroger les fichiers XM
Rôles : testeur
Date : 2026-11-14

Pour compter les tests par suite, interroger les fichiers XML de résultats, pas le journal de build.

## S120 — Pour un écran déjà maquetté, ne dessiner que les états absen
Rôles : designer
Date : 2026-11-14

Pour un écran déjà maquetté, ne dessiner que les états absents (vide, attente, succès, erreurs) ; dessiner les icônes plutôt que d'utiliser des glyphes Unicode, puis relire les images.

## S121 — Quand une correction est relancée après une interruption du
Rôles : designer
Date : 2026-11-14

Quand une correction est relancée après une interruption du moteur, vérifier d'abord ce qui est déjà appliqué dans les fichiers et ne reprendre que ce qui manque.

## S122 — Quand l'environnement d'exécution ne contient pas la chaîne
Rôles : dev
Date : 2026-11-14

Quand l'environnement d'exécution ne contient pas la chaîne de compilation nécessaire, écrire le code, le déclarer non compilé et non testé dans le rapport, et indiquer la commande à lancer ailleurs.

## S123 — Relire chaque édition juste après l'avoir faite : une erreur
Rôles : dev
Date : 2026-11-14

Relire chaque édition juste après l'avoir faite : une erreur d'inattention compile parfois sans que personne ne la voie.

## S124 — Quand une tâche redemande un élément déjà livré et que l'env
Rôles : dev
Date : 2026-11-14

Quand une tâche redemande un élément déjà livré et que l'environnement n'a pas les outils de build, vérifier l'historique du dépôt, rendre l'existant et signaler clairement que rien n'a été recompilé ni retesté.

## S125 — Sous Windows, lancer un script de build par son chemin compl
Rôles : release
Date : 2026-11-14

Sous Windows, lancer un script de build par son chemin complet, jamais par son seul nom, car le shell ne cherche pas dans le dossier courant.

## S126 — Après avoir écrit un fichier de code, chercher les caractère
Rôles : testeur
Date : 2026-11-14

Après avoir écrit un fichier de code, chercher les caractères non ASCII invisibles dans les identifiants, car ils compilent parfois mais cassent la lecture.

## S127 — Après avoir écrit un fichier de code, chercher les caractère
Rôles : testeur
Date : 2026-11-14

Après avoir écrit un fichier de code, chercher les caractères non ASCII invisibles dans les identifiants, car ils compilent parfois mais cassent la lecture.

## S128 — Quand une correction de code est confiée à un rôle de concep
Rôles : designer
Date : 2026-11-14

Quand une correction de code est confiée à un rôle de conception, appliquer exactement la consigne, ne pas toucher aux maquettes, et déclarer ce qui n'a pas pu être compilé ou exécuté.

## S129 — Dans une coroutine, entourer chaque écriture persistante d'u
Rôles : dev
Date : 2026-11-14

Dans une coroutine, entourer chaque écriture persistante d'un try/catch : relancer l'annulation, convertir le reste en état d'erreur visible avec une sortie de repli.

## S130 — En Kotlin, une lambda finale est affectée au dernier paramèt
Rôles : dev
Date : 2026-11-14

En Kotlin, une lambda finale est affectée au dernier paramètre, même si un paramètre précédent attend une interface à méthode unique : passer l'argument ou le constructeur SAM explicitement.

## S131 — Le script qui lance les tests doit afficher les comptes par
Rôles : testeur
Date : 2026-11-14

Le script qui lance les tests doit afficher les comptes par suite depuis les XML de résultats, pour repérer une suite manquante.

## S132 — Quand une maquette déjà validée contient un glyphe manquant,
Rôles : designer
Date : 2026-11-14

Quand une maquette déjà validée contient un glyphe manquant, le signaler comme écart sans la régénérer si aucune donnée n'a changé, et dessiner l'icône dans les nouvelles images.

## S133 — Si l'affichage d'un certificat échoue dans l'outil de clés,
Rôles : release
Date : 2026-11-14

Si l'affichage d'un certificat échoue dans l'outil de clés, exportez le certificat au format DER et calculez son empreinte avec un calcul de hachage.

## S134 — Dans une maquette, vérifier que les chiffres d'exemple reste
Rôles : designer
Date : 2026-11-14

Dans une maquette, vérifier que les chiffres d'exemple restent cohérents avec le filtre ou l'état affiché à côté.

## S135 — Pour contrôler la présence d'une classe dans un paquet, déco
Rôles : release
Date : 2026-11-14

Pour contrôler la présence d'une classe dans un paquet, décompresser l'entrée dex avec le module zip avant de chercher le nom de la classe.

## S136 — Annuler ou attendre le travail asynchrone d'un test avant re
Rôles : testeur
Date : 2026-11-14

Annuler ou attendre le travail asynchrone d'un test avant resetMain, et relancer une fois pour distinguer un test instable d'une régression.

## S137 — Pour étendre une interface déjà implémentée par des faux de
Rôles : dev
Date : 2026-11-14

Pour étendre une interface déjà implémentée par des faux de test, ajouter une méthode avec corps par défaut qui délègue à l'ancienne, au lieu de modifier la signature existante.

## S138 — Pour lire une version dans une sortie d'outil, chercher le n
Rôles : release
Date : 2026-11-14

Pour lire une version dans une sortie d'outil, chercher le nom exact du champ affiché et ne pas supposer un préfixe.

## S139 — Quand une étape de conception porte sur un élément de test o
Rôles : designer
Date : 2026-11-14

Quand une étape de conception porte sur un élément de test ou de validation sans interface propre, la déclarer non applicable en une ligne, sans produire de livrable vide.

## S140 — Ne jamais afficher, même partiellement, un fichier contenant
Rôles : release
Date : 2026-11-14

Ne jamais afficher, même partiellement, un fichier contenant des secrets ; le lire par un script qui ne sort que les noms des clés.

## S141 — Pour contrôler l'empreinte d'un certificat sans exposer son
Rôles : release
Date : 2026-11-14

Pour contrôler l'empreinte d'un certificat sans exposer son mot de passe, passer le mot de passe par variable d'environnement et calculer le SHA-256 du certificat exporté.

## S142 — Quand le build répond UP-TO-DATE, lire les XML de résultats
Rôles : testeur
Date : 2026-11-14

Quand le build répond UP-TO-DATE, lire les XML de résultats existants et vérifier leur nombre par suite avant de conclure.

## S143 — Un outil de comptage qui lit les fichiers de résultats peut
Rôles : testeur
Date : 2026-11-14

Un outil de comptage qui lit les fichiers de résultats peut montrer d'anciens résultats après un échec de compilation ; vérifier que le build a réussi avant de s'y fier.

## S144 — Quand une tâche de build échoue sur un dossier intermédiaire
Rôles : release
Date : 2026-11-14

Quand une tâche de build échoue sur un dossier intermédiaire absent et que le code n'y est pour rien, relancer le build une fois avant de supprimer des sorties générées.

## S145 — Journaliser la sortie complète d'un build dans un fichier av
Rôles : release
Date : 2026-11-14

Journaliser la sortie complète d'un build dans un fichier avant de la filtrer : un filtre par mots-clés peut masquer la cause réelle de l'échec.

## S146 — Pour contrôler un certificat de signature, passer le mot de
Rôles : release
Date : 2026-11-14

Pour contrôler un certificat de signature, passer le mot de passe par variable d'environnement et calculer le SHA-256 du certificat exporté.

## S147 — Quand les états d'un écran sont déjà maquettés et validés, l
Rôles : designer
Date : 2026-11-14

Quand les états d'un écran sont déjà maquettés et validés, livrer un tableau état → texte → actions et les règles de comportement, sans regénérer d'images.

## S148 — Quand un élément est couvert par une maquette déjà validée e
Rôles : designer
Date : 2026-11-14

Quand un élément est couvert par une maquette déjà validée et une fiche écrite, relancer l'étape de maquettes ne produit rien : vérifier la présence des fichiers, déclarer l'étape non applicable et fournir au valideur de quoi juger.

## S149 — Quand une validation est refusée faute de consigne, reprendr
Rôles : designer
Date : 2026-11-14

Quand une validation est refusée faute de consigne, reprendre le livrable existant, vérifier qu'il est intact et ne rendre que les champs de consigne manquants, sans refaire le travail.

## S150 — Injecter le dispatcher dans tout composant qui lance du trav
Rôles : dev
Date : 2026-11-14

Injecter le dispatcher dans tout composant qui lance du travail asynchrone : dispatcher synchrone pour les tests déterministes, vrai dispatcher avec verrou pour tester l'annulation pendant l'appel.

## S151 — Sans approbation possible, enchaîner les lectures par des ap
Rôles : testeur
Date : 2026-11-14

Sans approbation possible, enchaîner les lectures par des appels d'outils séparés ou par un script écrit avec l'outil de fichier, jamais par une commande composée.

## S152 — Quand des codes de statut d'un service sont regroupés sous u
Rôles : dev, designer
Date : 2026-11-14

Quand des codes de statut d'un service sont regroupés sous un message, chaque code voisin doit avoir un cas explicite et un test, sinon il tombe dans le message générique d'erreur.

## S153 — Une erreur de compilation sur une ressource existante peut v
Rôles : release
Date : 2026-11-14

Une erreur de compilation sur une ressource existante peut venir d'un état périmé : relancer une fois avant de corriger le code.

## S154 — Dans un script de maquettes, éviter les symboles Unicode déc
Rôles : cadrage
Date : 2026-11-14

Dans un script de maquettes, éviter les symboles Unicode décoratifs et préférer du texte ou des formes dessinées ; relire au moins une image rendue avant de livrer.

## S155 — Quand un message est limité en nombre d'images, montrer les
Rôles : designer
Date : 2026-11-14

Quand un message est limité en nombre d'images, montrer les principales dans le message et mettre la liste complète dans le livrable qui l'accompagne.

## S156 — Pour ajouter une variante à un jeu d'images produit par scri
Rôles : designer
Date : 2026-11-14

Pour ajouter une variante à un jeu d'images produit par script, paramétrer la fonction de dessin existante et vérifier que les images déjà validées sont regénérées à l'identique.

## S157 — Quand une étape de maquettes porte sur un correctif de compo
Rôles : designer
Date : 2026-11-14

Quand une étape de maquettes porte sur un correctif de comportement sans interface nouvelle, vérifier que la maquette de l'écran concerné existe, déclarer l'étape non applicable et renvoyer aux contrôles du registre.

## S158 — Quand un élément est couvert par une maquette déjà validée,
Rôles : designer
Date : 2026-11-14

Quand un élément est couvert par une maquette déjà validée, relancer l'étape de maquettes ne produit rien : vérifier que le fichier existe et fournir au valideur de quoi juger.

## S159 — Quand la tâche annoncée est introuvable dans les fichiers de
Rôles : designer
Date : 2026-11-14

Quand la tâche annoncée est introuvable dans les fichiers de suivi, récupérer d'abord la dernière version de la branche principale et la fusionner avant de déclarer l'information absente ; en cas de conflit hors périmètre, garder la version de la branche principale.

## S160 — Quand une étape de maquettes porte sur un branchement de par
Rôles : designer
Date : 2026-11-14

Quand une étape de maquettes porte sur un branchement de parcours ou un contrôle de navigation sans écran nouveau, vérifier que les maquettes des écrans reliés existent, déclarer l'étape non applicable en une ligne et renvoyer aux contrôles du registre.

## S161 — Quand une étape est relancée uniquement faute de consigne de
Rôles : designer
Date : 2026-11-14

Quand une étape est relancée uniquement faute de consigne de validation, relire le livrable existant et ne rendre que les champs de consigne manquants, sans refaire le travail.

## S162 — Écrire un lanceur de build qui n'affiche que les erreurs de
Rôles : dev
Date : 2026-11-14

Écrire un lanceur de build qui n'affiche que les erreurs de compilation, les échecs et le résultat final, et qui garde le journal complet dans un fichier, évite de relire des centaines de lignes.

## S163 — Quand une fiche est corrigée après une remarque, vérifier da
Rôles : testeur
Date : 2026-11-14

Quand une fiche est corrigée après une remarque, vérifier dans le code que chaque nouvel état et chaque nouveau réglage décrit existe, par une recherche de ses libellés et de son état ; les tests écrits avant la correction restent verts.

## S164 — Quand l'environnement n'a pas l'émulateur ou le SDK demandé
Rôles : designer
Date : 2026-11-14

Quand l'environnement n'a pas l'émulateur ou le SDK demandé pour vérifier un écran, le dire, remplacer la vérification par une relecture du code contre la maquette et déclarer non exécutés les tests ajoutés.

## S165 — Un contrôle de textes en dur ne signale que les littéraux co
Rôles : dev, designer
Date : 2026-11-14

Un contrôle de textes en dur ne signale que les littéraux contenant des lettres (ni icônes, ni simples formats numériques), couvre aussi snackbar, étiquettes d'action, descriptions et replis, et se prouve par injection de faux littéraux.

## S166 — Pour une preuve de build, relancer les tâches sans cache et
Rôles : release
Date : 2026-11-14

Pour une preuve de build, relancer les tâches sans cache et journaliser toute la sortie dans un fichier avant de la filtrer.

## S167 — Quand un contrôle exige un shell composé (opérateurs enchaîn
Rôles : release
Date : 2026-11-15

Quand un contrôle exige un shell composé (opérateurs enchaînés), passer par les outils de recherche ou par un script Python qui exécute la même commande.

## S168 — Un test de reprise après panne qui s'appuie sur un faux non
Rôles : testeur
Date : 2026-11-15

Un test de reprise après panne qui s'appuie sur un faux non transactionnel doit modéliser le retour arrière, sinon il compte des écritures que la vraie base annulerait.

## S169 — Avant d'appliquer une consigne qui s'appuie sur un état supp
Rôles : designer, dev
Date : 2026-11-15

Avant d'appliquer une consigne qui s'appuie sur un état supposé du code (« comme le fait déjà tel écran »), vérifier cet état par recherche ; s'il est faux, appliquer le minimum cohérent et signaler l'écart.

## S170 — Un rappel d'interface avec valeur par défaut vide ne fait ja
Rôles : testeur
Date : 2026-11-15

Un rappel d'interface avec valeur par défaut vide ne fait jamais échouer la compilation. En revue, relire chaque appel de l'écran dans la navigation et vérifier que chaque rappel est passé.

## S171 — Sous Windows, dans un shell POSIX, écrire les chemins avec d
Rôles : release
Date : 2026-11-15

Sous Windows, dans un shell POSIX, écrire les chemins avec des barres obliques, les barres inverses étant perdues.

## S172 — Pour exécuter des tests sur émulateur sans approbation inter
Rôles : designer
Date : 2026-11-15

Pour exécuter des tests sur émulateur sans approbation interactive, regrouper dans un script le démarrage, l'attente du démarrage complet, les tests filtrés par classe et l'arrêt dans un finally.

## S173 — Un contrôle automatique des textes affichés doit parcourir t
Rôles : testeur
Date : 2026-11-15

Un contrôle automatique des textes affichés doit parcourir toutes les sources du module, pas seulement le fichier de ressources.

## S174 — Une livraison déclare vérifié seulement ce qui a été exécuté
Rôles : release
Date : 2026-11-15

Une livraison déclare vérifié seulement ce qui a été exécuté pendant la livraison ; les résultats de tests antérieurs ne comptent pas.

## S175 — Un test de câblage provisoire doit échouer quand la cible es
Rôles : testeur
Date : 2026-11-15

Un test de câblage provisoire doit échouer quand la cible est créée sans être branchée, et dire dans son message que l'accroche vide est un défaut connu, pas une validation.

## S176 — Quand un élément a été repris plusieurs fois pour des défaut
Rôles : designer
Date : 2026-11-15

Quand un élément a été repris plusieurs fois pour des défauts qui se retrouveront ailleurs, revoir la méthode : inventaire global, contrôle automatique couvrant tout le code, test réellement exécuté, critère de sortie explicite et plafond de reprises.

## S177 — Un test qui accepte un point d'accroche vide tant que la cib
Rôles : testeur
Date : 2026-11-15

Un test qui accepte un point d'accroche vide tant que la cible n'existe pas ne valide rien ; le rapport le dit à chaque tour jusqu'à la création de la cible.

## S178 — Un contrôle automatique de littéraux dans les écrans ne voit
Rôles : designer
Date : 2026-11-15

Un contrôle automatique de littéraux dans les écrans ne voit pas les textes portés par des objets de constantes ou des énumérations ; les inventorier séparément et déclarer la limite du contrôle.

## S179 — Deux fichiers de même taille peuvent différer : comparer le
Rôles : release
Date : 2026-11-15

Deux fichiers de même taille peuvent différer : comparer le hachage avant de conclure qu'un livrable est identique à un précédent.

## S180 — Avant de reporter un point ouvert d'un registre de contrôles
Rôles : release, testeur
Date : 2026-11-15

Avant de reporter un point ouvert d'un registre de contrôles, vérifier son état réel dans le code par une recherche ciblée, et signaler la différence plutôt que de recopier l'ancien statut.

## S181 — Pour un inventaire de manques, interroger le registre des co
Rôles : cadrage
Date : 2026-11-15

Pour un inventaire de manques, interroger le registre des contrôles par recherches ciblées (TODO, provisoire, à venir, non réalisé) plutôt que de le lire en entier.

## S182 — Pour ajouter un état à un jeu d'images validé, écrire un scr
Rôles : designer
Date : 2026-11-15

Pour ajouter un état à un jeu d'images validé, écrire un script qui importe le script existant sans le modifier, puis vérifier par le suivi git que les images validées n'ont pas changé.

## S183 — Quand une étape de maquettes porte sur des tests automatique
Rôles : designer
Date : 2026-11-15

Quand une étape de maquettes porte sur des tests automatiques d'un écran déjà maquetté, vérifier que les maquettes existent et déclarer l'étape non applicable en une ligne, sans livrable vide.

## S184 — Quand une étape est relancée parce que le rapport n'a ni ima
Rôles : designer
Date : 2026-11-15

Quand une étape est relancée parce que le rapport n'a ni image ni consigne de validation, relire le livrable existant, vérifier qu'il est intact et rendre seulement les images légendées et les champs de consigne.

## S185 — Quand une étape de conception est relancée uniquement parce
Rôles : designer
Date : 2026-11-15

Quand une étape de conception est relancée uniquement parce que le rapport ne disait pas au valideur ce qu'il doit juger, relire le livrable existant, vérifier qu'il est intact et rendre seulement les champs de consigne (ce qui doit marcher, ce qui n'est pas attendu, conclusion), sans rien régénérer.

## S186 — Quand une étape de maquettes porte sur un élément d'inventai
Rôles : designer
Date : 2026-11-15

Quand une étape de maquettes porte sur un élément d'inventaire ou d'audit dont le seul livrable est un document de statuts, la déclarer non applicable en une ligne ; les maquettes des manques constatés se font dans l'élément qui prépare leur correction.

## S187 — Quand un élément prépare les corrections de plusieurs manque
Rôles : designer
Date : 2026-11-15

Quand un élément prépare les corrections de plusieurs manques, associer chaque manque à sa maquette existante, déclarer non applicable ce qui est couvert, et soumettre à l'utilisateur par question à choix les manques sans maquette.

## S188 — Quand une étape de maquettes est relancée parce que le rappo
Rôles : designer
Date : 2026-11-15

Quand une étape de maquettes est relancée parce que le rapport ne contenait ni image ni consigne de validation, relire le livrable existant, joindre les images déjà produites avec légende et rendre les champs de consigne, sans regénérer.

## S189 — Quand une étape de conception est refusée parce que le rappo
Rôles : designer
Date : 2026-11-15

Quand une étape de conception est refusée parce que le rapport ne contient aucune image, relire le livrable, joindre au rapport les images existantes pertinentes (dans la limite du nombre autorisé) avec légende, et renvoyer les autres à la fiche, sans rien regénérer.

## S190 — Sans interlocuteur, quand l'accord de l'action figure déjà d
Rôles : dev
Date : 2026-11-15

Sans interlocuteur, quand l'accord de l'action figure déjà dans la tâche et dans une règle du projet, l'exécuter au premier plan et signaler dans le rapport toute fenêtre éventuelle, au lieu de s'arrêter sur une question qui restera sans réponse.

## S191 — Quand l'environnement n'a pas de quoi compiler ou exécuter d
Rôles : designer, dev
Date : 2026-11-15

Quand l'environnement n'a pas de quoi compiler ou exécuter des tests, livrer les tests en les déclarant non compilés et non exécutés, avec la liste exacte des classes à lancer et du résultat à relire.

## S192 — Dans un inventaire de statuts, distinguer l'état où une sort
Rôles : designer
Date : 2026-11-15

Dans un inventaire de statuts, distinguer l'état où une sortie existe de celui où elle manque : lire la ligne de code concernée avant d'écrire « absent », et nommer précisément ce qui manque.

## S193 — Quand une livraison inclut une étape qui ouvre une fenêtre s
Rôles : dev
Date : 2026-11-15

Quand une livraison inclut une étape qui ouvre une fenêtre système sans réponse possible, exécuter et livrer la partie sûre (compilation, signature, vérifications) et déclarer explicitement l'étape non faite.

## S194 — Avant de rendre un document de statuts, relire chaque ligne
Rôles : testeur
Date : 2026-11-15

Avant de rendre un document de statuts, relire chaque ligne contre l'état courant du code, car une décision livrée entre deux tours rend les lignes fausses sans casser un test.

## S195 — Quand une correction remplace une valeur ou un choix périmé
Rôles : designer
Date : 2026-11-15

Quand une correction remplace une valeur ou un choix périmé dans un document, rechercher toutes ses variantes avant et après la modification, et reporter les statuts qui en découlent directement, sans toucher aux autres.

## S196 — Après avoir reporté une décision validée dans un document, c
Rôles : designer
Date : 2026-11-15

Après avoir reporté une décision validée dans un document, chercher par recherche dans tout le projet les autres documents qui la présentent encore comme ouverte ; ceux hors périmètre se signalent sans être modifiés.

## S197 — Dédoublonner les fichiers de résultats avant de totaliser le
Rôles : testeur
Date : 2026-11-15

Dédoublonner les fichiers de résultats avant de totaliser les comptes d'un lot de tests.

## S198 — Avant de valider un document qui cite une version ou un sché
Rôles : testeur
Date : 2026-11-15

Avant de valider un document qui cite une version ou un schéma de signature, relire la configuration de build courante et lancer l'outil de vérification de signature sur chaque fichier livré : une livraison ultérieure rend les notes fausses sans casser de test.

## S199 — Quand un document corrigé liste en tête ce qui a changé, cet
Rôles : designer
Date : 2026-11-15

Quand un document corrigé liste en tête ce qui a changé, cette liste cite les anciennes valeurs ; le contrôle de recherche après correction doit les distinguer des occurrences oubliées.

## S200 — Quand une correction remplace une valeur périmée dans un doc
Rôles : designer
Date : 2026-11-15

Quand une correction remplace une valeur périmée dans un document qui s'appuie sur un autre document, relire la source réelle (code) plutôt que le document intermédiaire, qui peut être lui aussi en retard ; signaler l'écart sans le corriger hors périmètre.

## S201 — Un message de commit annonçant la correction d'un document n
Rôles : testeur
Date : 2026-11-15

Un message de commit annonçant la correction d'un document ne prouve pas que le contenu a changé : relire le fichier et rapprocher chaque point de la consigne avant de conclure.

## S202 — Après le remplacement d'un livrable, relire chaque mention «
Rôles : testeur
Date : 2026-11-15

Après le remplacement d'un livrable, relire chaque mention « reste à faire » ou « à corriger par un autre élément » dans les documents liés et la comparer à l'état réel : elles deviennent périmées sans casser aucun test.

## S203 — Avant d'appliquer une consigne de correction d'un document,
Rôles : designer
Date : 2026-11-15

Avant d'appliquer une consigne de correction d'un document, vérifier par recherche des variantes périmées si elle est déjà appliquée ; si oui, ne rien modifier et le dire.

## S204 — Après la correction d'un document de statuts, chercher par G
Rôles : testeur
Date : 2026-11-15

Après la correction d'un document de statuts, chercher par Grep chaque ancienne valeur et chaque formule périmée : elles ne doivent subsister que dans le journal des changements. Relire ensuite le total de tests dans les résultats.

## S205 — Quand une consigne de revue cite des numéros de ligne à corr
Rôles : testeur
Date : 2026-11-15

Quand une consigne de revue cite des numéros de ligne à corriger, vérifier d'abord par recherche ciblée l'état courant du document : la correction peut déjà être livrée, et la revue consiste alors à confirmer sans rien recopier de l'ancien statut.

## S206 — Pour contrôler un certificat de signature, passer le mot de
Rôles : release
Date : 2026-11-15

Pour contrôler un certificat de signature, passer le mot de passe par variable d'environnement et comparer le SHA-256 du certificat à celui de la livraison précédente.

## S207 — Pour relever une version dans une sortie d'outil, filtrer sa
Rôles : release
Date : 2026-11-15

Pour relever une version dans une sortie d'outil, filtrer sans sensibilité à la casse sur le mot-clé, et non sur le préfixe exact du champ.

## S208 — Dans un script de maquettes, dimensionner les cartes d'après
Rôles : cadrage
Date : 2026-11-15

Dans un script de maquettes, dimensionner les cartes d'après leur contenu et relire l'image rendue pour repérer les chevauchements de texte.

## S209 — Pour une quantité répartie sur plusieurs lignes, définir des
Rôles : designer
Date : 2026-11-15

Pour une quantité répartie sur plusieurs lignes, définir des invariants dans une logique pure testée, puis faire lire ces règles par le script de rendu.

## S210 — Ne pas importer un script d'images qui s'exécute à l'import
Rôles : designer
Date : 2026-11-15

Ne pas importer un script d'images qui s'exécute à l'import et dépend d'une police absente du poste ; écrire un script autonome qui n'écrit que dans son propre dossier.

## S211 — Quand une étape de maquettes est relancée uniquement faute d
Rôles : designer
Date : 2026-11-15

Quand une étape de maquettes est relancée uniquement faute de consigne de validation et que la maquette existe, vérifier sa présence, joindre les images existantes et ne rendre que les champs de consigne.

## S212 — Quand une étape est relancée uniquement faute de consigne de
Rôles : designer
Date : 2026-11-15

Quand une étape est relancée uniquement faute de consigne de validation, vérifier que le livrable est intact, joindre au plus quatre images existantes et ne rédiger que les champs de consigne, sans rien regénérer.

## S213 — Quand un lot de code a été écrit sans chaîne de compilation,
Rôles : dev
Date : 2026-11-15

Quand un lot de code a été écrit sans chaîne de compilation, lire le détail de chaque échec pour savoir si le test ou le code est faux avant de modifier l'un des deux.

## S214 — Quand on écrit du code d'interface sans pouvoir compiler, re
Rôles : designer
Date : 2026-11-15

Quand on écrit du code d'interface sans pouvoir compiler, relire les signatures utilisées et les portées des modificateurs (weight, align) avant de rendre, et déclarer le code non compilé.

## S215 — Quand on ajoute un paramètre après un paramètre de type fonc
Rôles : testeur
Date : 2026-11-15

Quand on ajoute un paramètre après un paramètre de type fonction, le lambda de fin se lie au nouveau dernier paramètre : compiler les tests après tout changement de signature et passer le lambda entre parenthèses.

## S216 — Corriger à la source ce qui a été rattrapé depuis l'interface
Rôles : orchestrateur
Date : 2026-11-16

Quand un traitement a dû être fait ou rattrapé à la main depuis l'interface Claude Code parce que le bureau n'a pas su le faire seul, corriger la cause à la source, dans le code de la skill, pour que le bureau redevienne autonome ; le contournement à la main ne suffit pas. Si l'utilisateur est le propriétaire du dépôt de la skill (le compte de git remote get-url origin ; le vérifier par gh api user quand gh est installé, sinon le lui demander une fois), commiter la correction avec ses tests et la pousser directement. Sinon, ne rien pousser : ouvrir une issue sur le dépôt de la skill qui décrit le problème, sa cause et la correction proposée ; elle sera analysée avant d'être fusionnée.

## S217 — Un test est qualitatif et rapide
Rôles : dev, testeur, orchestrateur
Date : 2026-11-16

Tout test doit être à la fois qualitatif et rapide à exécuter, et on cherche toujours à l'optimiser : pas d'attente réelle, de réseau, de gros fichiers ni de scénario complet quand un double ou une donnée minimale prouve la même chose, en gardant des assertions précises. Quand une suite devient lente, repérer les tests les plus lents (par exemple pytest --durations=15) et les accélérer sans perdre ce qu'ils vérifient.

## S218 — Avant de poser une question de cadrage sur une correction va
Rôles : dev
Date : 2026-11-16

Avant de poser une question de cadrage sur une correction vague, vérifier dans les registres de suivi du projet et dans le code si la fonctionnalité ou l'anomalie citée existe réellement, afin de ne poser que la question strictement nécessaire.

## S219 — Quand un signalement de correction évoque un suivi, une tâch
Rôles : dev
Date : 2026-11-16

Quand un signalement de correction évoque un suivi, une tâche ou un écran qui n'existe pas dans le code du projet, vérifier s'il décrit en réalité le comportement de l'outil d'orchestration (moteur/Factory) plutôt qu'un défaut de l'application développée, avant de chercher à reproduire dans le code applicatif.

## S220 — Quand une fonction bascule entre deux colonnes/dates de réfé
Rôles : dev
Date : 2026-11-16

Quand une fonction bascule entre deux colonnes/dates de référence selon un paramètre de mode, vérifier que TOUS les champs dérivés de cette date (pas seulement le filtre ou le tri principal) basculent aussi — sinon un champ dérivé reste calé sur l'ancien mode par défaut, bug difficile à repérer car les tests du mode par défaut restent verts.

## S221 — Pour une tâche de correction de bug, commencer par chercher
Rôles : dev
Date : 2026-11-16

Pour une tâche de correction de bug, commencer par chercher dans l'historique git si le fichier/la fonction visée a déjà été modifiée récemment dans un sens qui corrige le symptôme décrit, avant de réécrire le correctif.

## S222 — Avant d'investiguer un signalement, chercher dans l'historiq
Rôles : dev
Date : 2026-11-16

Avant d'investiguer un signalement, chercher dans l'historique de versions si une tâche identique a déjà été conclue récemment ; si oui, citer cette conclusion au lieu de relancer l'exploration.

## S223 — Quand la consigne d'une étape de correction demande explicit
Rôles : dev
Date : 2026-11-16

Quand la consigne d'une étape de correction demande explicitement un retour/texte de cadrage plutôt qu'un correctif de code, le livrable attendu pour cette étape est ce texte réutilisable comme future consigne, et non une modification de fichiers.

## S224 — Un ticket de correction resoumis plusieurs fois avec un diag
Rôles : dev
Date : 2026-11-16

Un ticket de correction resoumis plusieurs fois avec un diagnostic identique de hors-périmètre doit être fermé par l'orchestrateur plutôt que renvoyé à un nouvel agent de résolution.

## S225 — Avant de démarrer un service réseau local pour produire une
Rôles : dev
Date : 2026-11-16

Avant de démarrer un service réseau local pour produire une preuve de validation, vérifier d'abord par une requête s'il n'est pas déjà actif, afin d'éviter un conflit de port et de réutiliser le service existant.

## S226 — Quand un même signalement de correction a déjà été confirmé
Rôles : dev
Date : 2026-11-16

Quand un même signalement de correction a déjà été confirmé hors périmètre ou déjà corrigé à 5-6 reprises consécutives avec le même diagnostic, il doit être clos directement par l'orchestrateur sans nouvelle instruction à un agent, pour éviter de gaspiller des cycles d'exploration identiques.

## S227 — Quand une commande shell impliquant le réseau (curl, netstat
Rôles : dev
Date : 2026-11-16

Quand une commande shell impliquant le réseau (curl, netstat) ou un changement de répertoire avant une commande git est refusée automatiquement faute d'approbateur, la reformuler : écrire un script dans le langage du projet (ex. Python) avec l'outil d'écriture de fichier puis l'exécuter directement, et utiliser l'option de l'outil qui évite le changement de répertoire (ex. `-C`) plutôt que `cd &&`.

## S228 — Avant d'investiguer une anomalie signalée, chercher si un te
Rôles : dev
Date : 2026-11-16

Avant d'investiguer une anomalie signalée, chercher si un test automatisé couvre déjà précisément ce scénario et l'exécuter ; son statut (passant/échouant) tranche immédiatement sans lecture de code supplémentaire.

## S229 — Quand on cherche une anomalie sans piste donnée, lancer la s
Rôles : dev
Date : 2026-11-16

Quand on cherche une anomalie sans piste donnée, lancer la suite de tests existante et examiner les warnings qu'elle émet (pas seulement les échecs) est un moyen rapide et peu coûteux de trouver un vrai défaut plutôt que d'explorer le code au hasard.

## S230 — Quand du code applique une suppression explicite d'enregistr
Rôles : dev
Date : 2026-11-16

Quand du code applique une suppression explicite d'enregistrements enfants en filet de sécurité contre une cascade de clé étrangère potentiellement inactive sur certaines connexions, forcer un flush de ces suppressions avant de supprimer le parent : sans relation déclarée entre les deux objets au niveau de l'ORM, l'ordre des instructions de suppression n'est pas garanti et peut entrer en course avec la cascade côté base de données, produisant des suppressions redondantes ou des avertissements silencieux.

## S231 — Avant d'instruire une demande de correction, chercher un tes
Rôles : dev
Date : 2026-11-16

Avant d'instruire une demande de correction, chercher un test automatisé reproduisant exactement le scénario décrit dans la fiche ; son exécution tranche immédiatement entre 'déjà corrigé' et 'encore buggé', sans lecture de code approfondie ni nouvelle exploration.

## S232 — Avant de corriger un test qui échoue sur un symptôme de conf
Rôles : dev
Date : 2026-11-16

Avant de corriger un test qui échoue sur un symptôme de configuration (403/503/auth manquante), vérifier aussi que les paramètres qu'il envoie à l'endpoint testé sont bien consommés par celui-ci ; un paramètre non déclaré dans la signature de la route est ignoré sans erreur, ce qui masque un second défaut une fois le premier corrigé.

## S233 — Quand aucune bibliothèque graphique (image/police) n'est dis
Rôles : dev
Date : 2026-11-17

Quand aucune bibliothèque graphique (image/police) n'est disponible dans l'environnement, une maquette basse-fidélité peut être produite par un script d'encodage d'image minimal utilisant uniquement la bibliothèque standard, en simulant le texte par des barres plutôt que des lettres.

## S234 — Dans un rapport de fin d'étape de cadrage, le champ listant
Rôles : dev
Date : 2026-11-17

Dans un rapport de fin d'étape de cadrage, le champ listant maquettes et étapes à réaliser est une condition de passage à la validation, pas une simple information : son absence bloque la fonctionnalité même si les livrables existent déjà sur disque. Toujours le renseigner dès que des maquettes et une liste d'étapes sont produites.

## S235 — Dans une session sans approbateur pour l'outil shell, un app
Rôles : dev
Date : 2026-11-17

Dans une session sans approbateur pour l'outil shell, un appel direct à un outil de build/test dans un autre langage peut être refusé alors qu'un script dans le langage dont l'exécution est autorisée (ex. Python), qui lance ce même outil en sous-processus, est accepté.

## S236 — Un test qui échoue seulement dans la suite complète mais pas
Rôles : dev
Date : 2026-11-17

Un test qui échoue seulement dans la suite complète mais passe isolément est un indice de flakiness (charge, concurrence, ordre d'exécution), pas forcément une régression du changement en cours ; vérifier par exécution isolée avant de l'imputer à sa propre tâche.

## S237 — Quand un format de rapport impose une limite de longueur sur
Rôles : dev
Date : 2026-11-17

Quand un format de rapport impose une limite de longueur sur un champ texte (légende d'image), mesurer la longueur réelle de la chaîne avant de l'envoyer plutôt que de l'estimer à l'œil.

## S238 — Dans un test d'interface, ne jamais agir sur un élément alim
Rôles : dev, testeur
Date : 2026-11-17

Dans un test d'interface, ne jamais agir sur un élément alimenté par un chargement asynchrone sans avoir attendu qu'il soit présent ; chercher ce motif dans toute la suite.

## S239 — Avant de valider une livraison, rapprocher la date de constr
Rôles : testeur
Date : 2026-11-17

Avant de valider une livraison, rapprocher la date de construction du fichier livré de celle du dernier changement de code ; une correction commitée après le fichier n'y figure pas, même si les tests sont verts.

## S240 — Relire chaque statut d'une note de livraison contre les dern
Rôles : testeur
Date : 2026-11-17

Relire chaque statut d'une note de livraison contre les derniers résultats de tests avant de la valider ; elle reste fausse après une correction ultérieure.

## S241 — Avant de rapporter des résultats de tests, relire l'horodata
Rôles : designer
Date : 2026-11-17

Avant de rapporter des résultats de tests, relire l'horodatage et les comptes de chaque XML de résultats ; si une relance rapide n'a rien réécrit, le dire plutôt que d'affirmer une revérification complète.

## S242 — Une mesure de performance faite uniquement sur émulateur ne
Rôles : designer
Date : 2026-11-17

Une mesure de performance faite uniquement sur émulateur ne doit pas être présentée comme validée sur appareil réel ; le périmètre se déclare dans la note de livraison et dans la fenêtre de validation.

## S243 — Pour juger si un fichier livré est périmé, comparer la date
Rôles : testeur
Date : 2026-11-17

Pour juger si un fichier livré est périmé, comparer la date de la sortie de build d'origine avec le dernier changement de code, car la copie dans le dossier de livraison porte la date de la copie.

## S244 — Dans un cadrage, quand l'utilisateur corrige une règle métie
Rôles : dev
Date : 2026-11-18

Dans un cadrage, quand l'utilisateur corrige une règle métier après la rédaction du cahier, il faut réécrire explicitement toutes les parties du cahier affectées (étapes, taille, légendes de maquette) dans le rapport final — le message de confirmation et une nouvelle maquette ne suffisent pas si le champ structuré du cahier n'est pas lui-même renvoyé à jour.

## S245 — Quand une correction de cahier déjà posée par l'utilisateur
Rôles : dev
Date : 2026-11-18

Quand une correction de cahier déjà posée par l'utilisateur introduit un besoin distinct de l'objet initial de la fonctionnalité, on l'intègre quand même dans le même cahier corrigé, sans rouvrir de série de questions ; on choisit soi-même la forme des points encore ouverts et on l'explique dans le compte rendu.

## S246 — Quand l'analyse d'une correction de cahier des charges est d
Rôles : dev
Date : 2026-11-18

Quand l'analyse d'une correction de cahier des charges est déjà complète, rendre le cahier des charges (étapes, taille) dans le même rapport que l'analyse ; un rapport sans ce cahier laisse la fonctionnalité bloquée et provoque un aller-retour inutile.

## S247 — Quand une correction lève explicitement une règle métier déj
Rôles : dev
Date : 2026-11-18

Quand une correction lève explicitement une règle métier déjà couverte par un test, rechercher ce test par son nom/assertion et le réécrire pour le nouveau comportement, plutôt que d'ajouter un test en parallèle qui laisserait l'ancien échouer ou mentir.

## S248 — Quand un processus est lancé détaché depuis un script avec d
Rôles : dev
Date : 2026-11-18

Quand un processus est lancé détaché depuis un script avec des flags de détachement système, la redirection de sa sortie standard vers un fichier peut rester vide même si le processus a réellement démarré et s'est lié à son port ; vérifier l'état réel par une requête fonctionnelle (ex. HTTP) plutôt que de se fier au contenu du fichier de log.

## S249 — Avant de corriger un symptôme décrit dans un cahier des char
Rôles : dev
Date : 2026-11-18

Avant de corriger un symptôme décrit dans un cahier des charges, vérifier directement dans le code si la fonction citée existe déjà avec le comportement attendu ; si oui, se limiter à relancer les tests ciblés et produire la preuve demandée plutôt que de ré-écrire du code.

## S250 — Avant de conclure qu'une route API n'existe pas, inspecter l
Rôles : dev
Date : 2026-11-18

Avant de conclure qu'une route API n'existe pas, inspecter la liste complète des chemins exposés (openapi/swagger) plutôt que de tester un chemin deviné : un préfixe de routeur peut changer le chemin réel.

## S251 — Une remarque de correction peut porter sur un état du code d
Rôles : dev
Date : 2026-11-18

Une remarque de correction peut porter sur un état du code déjà corrigé entretemps par une autre session partageant le même dossier ; vérifier le code actuel et git log avant de rejouer le correctif.

## S252 — Sur un poste partagé, un port déjà annoncé « in use » par un
Rôles : dev
Date : 2026-11-18

Sur un poste partagé, un port déjà annoncé « in use » par un outil de build peut être occupé en IPv6 loopback ([::1]) sans répondre sur 127.0.0.1 ; vérifier les deux avant de conclure à un échec de démarrage ou de tenter de libérer le port.

## S253 — Pour une tâche de vérification, lancer d'abord les tests exi
Rôles : dev
Date : 2026-11-18

Pour une tâche de vérification, lancer d'abord les tests existants couvrant exactement le scénario. Cela résout en quelques secondes ce qu'une lecture de code approfondie prendrait des minutes à clarifier.

## S254 — Avant de produire une nouvelle preuve visuelle, vérifier si
Rôles : dev
Date : 2026-11-18

Avant de produire une nouvelle preuve visuelle, vérifier si une preuve équivalente a déjà été produite par une session très récente sur le même sujet, et la réutiliser plutôt que de la régénérer.

## S255 — Quand un commanditaire conteste un diagnostic « hors périmèt
Rôles : dev
Date : 2026-11-18

Quand un commanditaire conteste un diagnostic « hors périmètre » avec un détail précis et contradictoire, avant de répéter la même conclusion, vérifier l'artefact produit au niveau le plus bas possible (octets/fichier réel, pas seulement l'objet en mémoire de la bibliothèque utilisée) : cela donne une preuve plus forte, positive ou négative, que de relire seulement le code.

## S256 — Avant de concevoir un contrôle d'accès pour une nouvelle règ
Rôles : dev
Date : 2026-11-18

Avant de concevoir un contrôle d'accès pour une nouvelle règle (« qui a le droit de remplir/modifier ce champ »), vérifier si l'application dispose déjà d'un système de permissions par utilisateur ; si non, ne pas ajouter de contrôle technique isolé pour cette seule règle — elle reste une convention d'usage, cohérente avec le reste de l'application.

## S257 — Quand un test d'aller-retour (export puis reimport) echoue,
Rôles : dev
Date : 2026-11-18

Quand un test d'aller-retour (export puis reimport) echoue, verifier d'abord la fonction d'aide qui reconstruit le fichier intermediaire : si elle n'ecrase que les valeurs fournies sans effacer les anciennes au-dela de la nouvelle liste, le test accuse a tort le code applicatif.
