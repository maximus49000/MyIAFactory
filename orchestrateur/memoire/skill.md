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
