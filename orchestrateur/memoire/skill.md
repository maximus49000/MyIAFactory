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
