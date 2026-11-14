# Genre : application-mobile-android
Domaine : Application Android native, livrée sous forme d'apk signé installable.
Livrable : à préciser
Outils : à préciser

## G1 — Sur un écran mobile à liste, un bouton d'action flottant doi
Rôles : cadrage
Date : 2026-11-14

Sur un écran mobile à liste, un bouton d'action flottant doit être compact (rond) ou la liste doit prévoir une marge basse, sinon il masque du contenu.

## G2 — Pour un projet Android sans Gradle installé, lancer la distr
Rôles : dev
Date : 2026-11-14

Pour un projet Android sans Gradle installé, lancer la distribution en cache via un petit script qui fixe JAVA_HOME, écrit le journal en continu, et passe le compilateur Kotlin en mode in-process si le démon échoue.

## G3 — Avec un build incrémental, une tâche de test à jour n'est pa
Rôles : dev
Date : 2026-11-14

Avec un build incrémental, une tâche de test à jour n'est pas relancée. Lire les rapports de résultats pour donner les comptes réels, et forcer l'exécution si une preuve fraîche est demandée.

## G4 — Sur un SDK Android, cibler directement le sous-dossier voulu
Rôles : dev
Date : 2026-11-14

Sur un SDK Android, cibler directement le sous-dossier voulu, car un parcours complet est trop lent.

## G5 — Quand un script lance un wrapper de build, il l'appelle par
Rôles : testeur
Date : 2026-11-14

Quand un script lance un wrapper de build, il l'appelle par chemin absolu plutôt que par nom relatif.

## G6 — Pour livrer une application Android sans modifier le fichier
Rôles : release
Date : 2026-11-14

Pour livrer une application Android sans modifier le fichier de build, signer l'apk non signé en externe (alignement, signature, vérification) avec une clé stockée hors du dépôt et des mots de passe générés, jamais affichés.

## G7 — Dans un projet Android, org
Rôles : dev
Date : 2026-11-14

Dans un projet Android, org.json ne lit rien dans les tests unitaires JVM. Pour tester l'analyse d'une réponse JSON, utiliser un lecteur en Kotlin pur ou une bibliothèque JVM, et isoler le transport HTTP derrière une interface pour simuler les réponses.

## G8 — En Gradle Kotlin DSL, importer les classes Java en tête de f
Rôles : release, dev
Date : 2026-11-14

En Gradle Kotlin DSL, importer les classes Java en tête de fichier plutôt que les écrire en nom complet.

## G9 — Passer la clé de signature release hors du dépôt, par une pr
Rôles : release
Date : 2026-11-14

Passer la clé de signature release hors du dépôt, par une propriété de build, et n'activer la signature que si le fichier de clé est présent.

## G10 — Sans approbation possible, lire les rapports de tests avec l
Rôles : dev
Date : 2026-11-14

Sans approbation possible, lire les rapports de tests avec l'outil de recherche et des chemins absolus plutôt qu'avec des commandes shell.

## G11 — Dans un shell POSIX sous Windows, passer à l'interpréteur de
Rôles : designer
Date : 2026-11-14

Dans un shell POSIX sous Windows, passer à l'interpréteur des chemins avec des barres obliques, car les antislashs sont consommés.

## G12 — Pour un client de service externe, distinguer par un test le
Rôles : testeur, dev
Date : 2026-11-14

Pour un client de service externe, distinguer par un test les erreurs d'authentification, de limitation de débit, de surcharge et de réseau, et vérifier que chacune a un message ou un écran prévu.

## G13 — Pour un élément de persistance sans écran propre, lister les
Rôles : designer
Date : 2026-11-14

Pour un élément de persistance sans écran propre, lister les maquettes qui affichent ses données et ne dessiner que les erreurs d'enregistrement et de lecture, chacune avec une sortie de repli.

## G14 — Pour compter les tests par suite, lire les XML de résultats
Rôles : testeur
Date : 2026-11-14

Pour compter les tests par suite, lire les XML de résultats avec un script Python isolé plutôt que le journal de build.

## G15 — Dans une application mobile qui affiche des images distantes
Rôles : dev
Date : 2026-11-14

Dans une application mobile qui affiche des images distantes sans bibliothèque de chargement, télécharger l'image choisie dans le stockage privé de l'application ; ne jamais stocker une adresse web comme chemin de fichier.

## G16 — Quand l'environnement n'a pas le SDK de la plateforme cible,
Rôles : dev
Date : 2026-11-14

Quand l'environnement n'a pas le SDK de la plateforme cible, écrire la logique en classes pures testables, annoncer explicitement que rien n'a été compilé et indiquer la commande à lancer sur le poste équipé.

## G17 — Quand une clé de signature de livraison précédente existe ho
Rôles : release
Date : 2026-11-14

Quand une clé de signature de livraison précédente existe hors du dépôt, la réutiliser et vérifier son empreinte ; n'en générer une nouvelle que si elle est absente, en le signalant.

## G18 — Passer les mots de passe de signature aux outils de signatur
Rôles : release
Date : 2026-11-14

Passer les mots de passe de signature aux outils de signature par variables d'environnement, lues depuis un fichier hors dépôt, sans jamais les afficher.

## G19 — Utiliser la version la plus récente des outils de build inst
Rôles : release
Date : 2026-11-14

Utiliser la version la plus récente des outils de build installés pour aligner, signer et vérifier un paquet.

## G20 — Dans un code Kotlin à coroutines, tout catch large autour d'
Rôles : testeur, dev
Date : 2026-11-14

Dans un code Kotlin à coroutines, tout catch large autour d'un appel suspendu doit relancer CancellationException, sinon l'annulation devient une fausse erreur métier.

## G21 — Dans un code Kotlin à coroutines, tout catch large autour d'
Rôles : testeur, dev
Date : 2026-11-14

Dans un code Kotlin à coroutines, tout catch large autour d'un appel suspendu doit relancer CancellationException, sinon l'annulation devient une fausse erreur métier.

## G22 — Pour tester un ViewModel dont le travail s'exécute sur un di
Rôles : testeur
Date : 2026-11-14

Pour tester un ViewModel dont le travail s'exécute sur un dispatcher réel, remplacer le dispatcher principal par un dispatcher de test, attendre l'état attendu par une boucle à délai borné, et simuler un appel long par un verrou pour vérifier l'annulation.

## G23 — Une écriture dans un stockage matériel ou système (coffre de
Rôles : dev, testeur
Date : 2026-11-14

Une écriture dans un stockage matériel ou système (coffre de clés) peut lever une exception ; l'appelant la rattrape, en relançant l'annulation, pour ne pas planter l'application.

## G24 — Ne jamais lire un stockage chiffré ou bloquant dans l'initia
Rôles : dev, designer
Date : 2026-11-14

Ne jamais lire un stockage chiffré ou bloquant dans l'initialisation d'un modèle de vue : démarrer à un état neutre, charger en arrière-plan, mémoriser la valeur lue pour les actions suivantes.

## G25 — Quand la chaîne de compilation de la plateforme cible manque
Rôles : dev
Date : 2026-11-14

Quand la chaîne de compilation de la plateforme cible manque, mettre la validation, les conversions d'unités et les bornes dans un objet pur testable et garder les écrans minces ; déclarer le code non compilé.

## G26 — Sous Windows, une erreur « fichier utilisé par un autre proc
Rôles : dev
Date : 2026-11-14

Sous Windows, une erreur « fichier utilisé par un autre processus » pendant un build Gradle signale généralement un build concurrent sur le même dossier. Lister les processus par un script, attendre la fin du concurrent, puis relancer.

## G27 — Pour tester un ViewModel en test unitaire JVM, la bibliothèq
Rôles : testeur
Date : 2026-11-14

Pour tester un ViewModel en test unitaire JVM, la bibliothèque de test des coroutines doit être déclarée dans la configuration des tests unitaires, pas seulement dans celle des tests instrumentés.

## G28 — Un téléchargement borné en taille signale le dépassement au
Rôles : dev, testeur
Date : 2026-11-14

Un téléchargement borné en taille signale le dépassement au lieu de tronquer en silence ; l'écriture du fichier téléchargé rattrape ses exceptions d'E/S en relançant CancellationException, pour ne jamais planter l'application ni enregistrer une image corrompue.

## G29 — Pour un écran de saisie d'une quantité bornée, dessiner les
Rôles : designer
Date : 2026-11-14

Pour un écran de saisie d'une quantité bornée, dessiner les états : valeur au-dessus du maximum, vide ou nulle, valeur maximale, succès avec annulation, échec d'enregistrement avec repli.

## G30 — Réutilisez la clé de signature de livraison existante hors d
Rôles : release
Date : 2026-11-14

Réutilisez la clé de signature de livraison existante hors dépôt et vérifiez son empreinte contre la livraison précédente avant de compiler.

## G31 — Pour un écran de liste avec statistiques, dessiner les états
Rôles : designer
Date : 2026-11-14

Pour un écran de liste avec statistiques, dessiner les états vide, chargement, erreur de lecture, filtre sans résultat, période sans donnée (pas de division par zéro) et ligne dont l'objet source a disparu.

## G32 — Avant de signer une livraison, retrouver la clé de la livrai
Rôles : release
Date : 2026-11-14

Avant de signer une livraison, retrouver la clé de la livraison précédente hors du dépôt, la réutiliser et contrôler son empreinte contre celle de la livraison précédente.

## G33 — Les mots de passe de signature sont lus depuis un fichier ho
Rôles : release
Date : 2026-11-14

Les mots de passe de signature sont lus depuis un fichier hors dépôt, passés aux outils par variables d'environnement, et leurs valeurs ne sortent ni dans les journaux ni dans les notes.

## G34 — Pour un élément de notification système, dessiner la notific
Rôles : designer
Date : 2026-11-14

Pour un élément de notification système, dessiner la notification dans ses variantes (unique, groupée, urgente), les états d'autorisation (demande, refus, canal désactivé) et les erreurs de planification, de lecture et de cible disparue, chacune avec une sortie.

## G35 — Tester les raccourcis de saisie sur des valeurs décimales au
Rôles : testeur, dev
Date : 2026-11-14

Tester les raccourcis de saisie sur des valeurs décimales aux bornes (reste non rond) : un texte formaté pour l'affichage n'est pas un texte à relire par le contrôle de saisie.

## G36 — Avant de coder un écran de statistiques, vérifier que chaque
Rôles : dev
Date : 2026-11-14

Avant de coder un écran de statistiques, vérifier que chaque distinction affichée est bien enregistrée en base ; sinon ajouter la colonne avec une migration qui donne une valeur par défaut aux lignes existantes.

## G37 — Avant de lancer la livraison release, vérifier que la compil
Rôles : release
Date : 2026-11-14

Avant de lancer la livraison release, vérifier que la compilation release passe et que toutes les bibliothèques utilisées par le code sont déclarées dans le fichier de build, sinon la livraison bloque après la vérification de la clé.

## G38 — Une tâche périodique lit ses réglages à chaque exécution plu
Rôles : dev
Date : 2026-11-14

Une tâche périodique lit ses réglages à chaque exécution plutôt qu'à la planification ; changer un réglage n'impose alors aucune replanification.

## G39 — Une notification n'est enregistrée comme envoyée qu'après so
Rôles : dev
Date : 2026-11-14

Une notification n'est enregistrée comme envoyée qu'après son affichage ; si elle est bloquée, elle sera retentée. La logique de décision reste dans une classe pure testable.

## G40 — Tester les calculs par période aux bornes exactes (première
Rôles : testeur
Date : 2026-11-14

Tester les calculs par période aux bornes exactes (première et dernière seconde) et dans deux fuseaux horaires ; tester un observateur de flux avec un flux partagé qui émet plusieurs valeurs, puis annuler : l'annulation ne doit pas devenir un état d'erreur.

## G41 — Quand une valeur de réglage est normalisée pour un filtre, u
Rôles : testeur, dev
Date : 2026-11-14

Quand une valeur de réglage est normalisée pour un filtre, utiliser la même valeur normalisée pour la requête qui l'alimente ; tester qu'une notification refusée ou qui lève une exception n'enregistre pas l'événement comme envoyé.
