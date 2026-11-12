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
