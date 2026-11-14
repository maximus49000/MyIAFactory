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
