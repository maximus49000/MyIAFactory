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

## G42 — Avant une livraison, réutiliser la clé de signature précéden
Rôles : release
Date : 2026-11-14

Avant une livraison, réutiliser la clé de signature précédente hors dépôt et contrôler son empreinte contre celle de la livraison précédente, avant toute compilation.

## G43 — Si le build signe déjà la release, ne pas re-signer en exter
Rôles : release
Date : 2026-11-14

Si le build signe déjà la release, ne pas re-signer en externe : vérifier la signature produite.

## G44 — Comparer le schéma de signature de chaque livraison à la pré
Rôles : release
Date : 2026-11-14

Comparer le schéma de signature de chaque livraison à la précédente et signaler toute différence.

## G45 — Pour les tests instrumentés d'une application mobile sans po
Rôles : dev
Date : 2026-11-14

Pour les tests instrumentés d'une application mobile sans possibilité d'approbation, encapsuler dans un seul script la création de l'émulateur s'il manque, son démarrage sans fenêtre, l'attente de fin de boot, l'exécution des tests et l'arrêt de l'émulateur dans un bloc finally, avec journal écrit au fil de l'eau.

## G46 — Avant de clore une étape de tests instrumentés, rapprocher l
Rôles : testeur
Date : 2026-11-14

Avant de clore une étape de tests instrumentés, rapprocher la liste des contrôles encore ouverts qui réclament un test sur émulateur de la liste des suites réellement exécutées ; tout écart est un défaut à signaler.

## G47 — Une tâche qui doit compiler et signer un apk échoue dans un
Rôles : dev
Date : 2026-11-14

Une tâche qui doit compiler et signer un apk échoue dans un conteneur sans SDK ni clé : la rendre seulement quand l'exécution sur le poste équipé est assurée, sinon livrer le code commité en disant que rien n'a été compilé.

## G48 — Pour des tests sur émulateur, regrouper dans un seul script
Rôles : dev
Date : 2026-11-14

Pour des tests sur émulateur, regrouper dans un seul script le démarrage sans fenêtre, l'attente du démarrage complet, les tests, l'installation et l'arrêt dans un bloc finally, en journalisant au fil de l'eau.

## G49 — Relire les résultats de tests dans les fichiers XML, suite p
Rôles : dev
Date : 2026-11-14

Relire les résultats de tests dans les fichiers XML, suite par suite, plutôt que de se fier au seul code de sortie de l'outil de build.

## G50 — Pour clore une étape de tests sur appareil, rapprocher chaqu
Rôles : testeur
Date : 2026-11-14

Pour clore une étape de tests sur appareil, rapprocher chaque contrôle ouvert d'un test nommé, puis vérifier que les comptes lus dans les XML (toutes les suites du fichier, pas la première) correspondent au nombre de tests écrits.

## G51 — Un message d'erreur d'un écran qui ouvre une feuille ou une
Rôles : designer, dev
Date : 2026-11-14

Un message d'erreur d'un écran qui ouvre une feuille ou une boîte modale doit être affiché dans la feuille elle-même, sinon il reste caché derrière jusqu'à sa fermeture.

## G52 — Pour un écran de capture d'image déjà maquetté, ne dessiner
Rôles : designer
Date : 2026-11-14

Pour un écran de capture d'image déjà maquetté, ne dessiner que l'aperçu après capture, les états d'autorisation (demande, refus, matériel indisponible) et les erreurs d'image (illisible, trop lourde, non enregistrée, introuvable), chacun avec une sortie de repli.

## G53 — Quand la chaîne de compilation mobile manque, mettre la vali
Rôles : dev
Date : 2026-11-14

Quand la chaîne de compilation mobile manque, mettre la validation d'image, le plafond de taille et la décision de permission dans des classes pures testables avec des flux simulés, garder l'écran mince, et déclarer le code non compilé.

## G54 — Si la compilation des tests échoue sur des références non ré
Rôles : testeur
Date : 2026-11-14

Si la compilation des tests échoue sur des références non résolues vers des symboles qui existent, relancer une fois avant de les traiter comme un défaut : le cache incrémental peut être périmé.

## G55 — Tout téléchargement borné en taille passe par un transport i
Rôles : testeur, dev
Date : 2026-11-14

Tout téléchargement borné en taille passe par un transport injectable, pour tester le dépassement et l'échec d'écriture sans réseau.

## G56 — Pour vérifier la présence d'une classe dans un paquet, lire
Rôles : release
Date : 2026-11-14

Pour vérifier la présence d'une classe dans un paquet, lire les noms réels dans les déclarations du code et tenir compte des classes générées par les outils.

## G57 — Relire le câblage de navigation entre deux écrans : un rappe
Rôles : testeur, dev
Date : 2026-11-14

Relire le câblage de navigation entre deux écrans : un rappel qui reçoit une donnée mais navigue sans la transmettre passe tous les tests unitaires de la logique.

## G58 — Les mots de passe de signature ne sortent jamais dans les jo
Rôles : release
Date : 2026-11-14

Les mots de passe de signature ne sortent jamais dans les journaux : ils sont passés aux outils par variables d'environnement, et seuls les noms des clés de configuration sont affichés.

## G59 — Chaque livraison signée est comparée à la précédente sur ses
Rôles : release
Date : 2026-11-14

Chaque livraison signée est comparée à la précédente sur ses schémas de signature ; tout écart est signalé à l'utilisateur.

## G60 — Quand une route de navigation reçoit un argument, la route c
Rôles : dev, designer
Date : 2026-11-14

Quand une route de navigation reçoit un argument, la route courante exposée est le motif complet ; les listes de routes (barre masquée, etc.) doivent utiliser ce motif.

## G61 — Supprimer un fichier temporaire à la sortie d'un écran exige
Rôles : dev
Date : 2026-11-14

Supprimer un fichier temporaire à la sortie d'un écran exige un drapeau « transmis » et d'ignorer la rotation, sinon on détruit la donnée utile.

## G62 — Avant de créer une classe de test, chercher son nom dans tou
Rôles : testeur
Date : 2026-11-14

Avant de créer une classe de test, chercher son nom dans tout le paquet de test, car une déclaration en double fait échouer la compilation de toute la suite.

## G63 — Pour tester la libération d'un ViewModel en JVM, appeler onC
Rôles : testeur
Date : 2026-11-14

Pour tester la libération d'un ViewModel en JVM, appeler onCleared par réflexion, car il reste protégé même redéclaré par override sans modificateur.

## G64 — Quand la génération de code par processeur d'annotations éch
Rôles : dev
Date : 2026-11-14

Quand la génération de code par processeur d'annotations échoue sur un fichier de cache introuvable, supprimer le dossier de cache de la variante concernée puis relancer : le code n'est pas en cause.

## G65 — Avant de conclure qu'une classe est absente d'un paquet, lir
Rôles : release
Date : 2026-11-14

Avant de conclure qu'une classe est absente d'un paquet, lire ses déclarations dans le code : une fonction de niveau fichier, un objet ou une classe n'ont pas le même nom compilé.

## G66 — Avant de livrer une application, vérifier que les bibliothèq
Rôles : release
Date : 2026-11-14

Avant de livrer une application, vérifier que les bibliothèques importées par le code sont déclarées dans le fichier de build.

## G67 — Quand une étape livre la logique d'une fonction sans son bra
Rôles : cadrage, dev
Date : 2026-11-14

Quand une étape livre la logique d'une fonction sans son branchement dans l'interface, la liste des étapes doit contenir une étape explicite de branchement. Un écran provisoire encore atteignable en livraison doit être signalé dans le rapport de livraison.

## G68 — Les messages d'erreur destinés à l'utilisateur ne montrent p
Rôles : designer
Date : 2026-11-14

Les messages d'erreur destinés à l'utilisateur ne montrent pas de codes techniques ; les garder pour le journal interne.

## G69 — Une maquette d'attente qui montre un pourcentage est transcr
Rôles : designer
Date : 2026-11-14

Une maquette d'attente qui montre un pourcentage est transcrite en progression indéterminée quand la durée est inconnue. La fiche précise que la rotation d'écran n'annule ni ne relance l'opération.

## G70 — Pour modifier un élément déjà saisi, réutiliser l'écran de s
Rôles : dev
Date : 2026-11-14

Pour modifier un élément déjà saisi, réutiliser l'écran de saisie avec une valeur initiale et un rappel de validation facultatifs plutôt que créer un second écran ; les valeurs par défaut gardent les tests existants verts.

## G71 — Pour une application mobile, vérifier en revue qu'une phrase
Rôles : testeur
Date : 2026-11-14

Pour une application mobile, vérifier en revue qu'une phrase affichée figure dans les ressources de chaînes ; des constantes de code qui la répètent passent tous les tests unitaires.

## G72 — Quand une fiche ne dit pas quels champs absents bloquent un
Rôles : testeur
Date : 2026-11-14

Quand une fiche ne dit pas quels champs absents bloquent un ajout, tester la règle effective de validation du formulaire et signaler l'écart pour validation, au lieu de le passer sous silence.

## G73 — Un build tout vert et UP-TO-DATE ne prouve pas la règle « te
Rôles : testeur
Date : 2026-11-14

Un build tout vert et UP-TO-DATE ne prouve pas la règle « textes dans les ressources de chaînes » : en revue, chercher chaque phrase affichée dans le fichier de ressources, car des constantes de code passent tous les tests.

## G74 — Quand des textes d'interface passent de constantes du code à
Rôles : designer
Date : 2026-11-14

Quand des textes d'interface passent de constantes du code à des ressources, les tests unitaires qui les comparaient doivent lire le fichier de ressources, car les ressources ne sont pas accessibles en test sans émulateur.

## G75 — Quand une règle impose que les textes affichés soient dans l
Rôles : testeur
Date : 2026-11-14

Quand une règle impose que les textes affichés soient dans les ressources de chaînes, chercher chaque libellé dans le fichier de ressources et compter les appels de lecture de ressources ; une application dont tous les textes sont des constantes de code passe tous les tests unitaires.

## G76 — Quand un écran affiche un texte de repli par `?:` sur une va
Rôles : testeur, dev
Date : 2026-11-14

Quand un écran affiche un texte de repli par `?:` sur une valeur nulle, ce repli s'applique à toute future valeur nulle. Préférer une correspondance explicite sur le cas visé.

## G77 — Quand une consigne demande de déplacer les textes d'un écran
Rôles : designer
Date : 2026-11-14

Quand une consigne demande de déplacer les textes d'un écran en ressources, chercher tous les objets de constantes et propriétés d'énumération que l'écran lit, pas seulement celui nommé ; signaler ceux laissés hors périmètre.

## G78 — Dans une interface, le repli d'un libellé manquant doit être
Rôles : designer, dev
Date : 2026-11-14

Dans une interface, le repli d'un libellé manquant doit être un texte neutre, jamais le texte d'une autre erreur précise ; un test doit interdire ce repli.

## G79 — Avant une livraison, relever le versionCode de la livraison
Rôles : release
Date : 2026-11-14

Avant une livraison, relever le versionCode de la livraison précédente, le monter avant compilation, et donner au brief le chemin du fichier de propriétés de signature.

## G80 — Après toute écriture d'une ressource de chaînes Android, vér
Rôles : testeur
Date : 2026-11-14

Après toute écriture d'une ressource de chaînes Android, vérifier l'échappement des apostrophes et l'absence de marques de gabarit ; une correction commitée sans compilation ne prouve rien tant que le build n'a pas réussi.

## G81 — Quand une correction de revue ajoute un état ou un écran abs
Rôles : testeur
Date : 2026-11-14

Quand une correction de revue ajoute un état ou un écran absent de la fiche, la revue le signale comme écart à faire valider, même si les tests passent : les tests prouvent le comportement, pas l'accord sur la conception.

## G82 — Avant de déplacer les textes d'un écran en ressources, liste
Rôles : designer, dev
Date : 2026-11-14

Avant de déplacer les textes d'un écran en ressources, lister par recherche tous les objets de constantes et énumérations qu'il lit, et ajouter un contrôle automatique qui signale tout texte affiché en dur, prouvé par injection d'un faux littéral.

## G83 — Quand un écran n'est connu que par sa carte d'entrée, le con
Rôles : designer
Date : 2026-11-14

Quand un écran n'est connu que par sa carte d'entrée, le concevoir dans le thème existant, le signaler comme écart, et dessiner ses états (nominal, vide, attente, erreur, action modale, échec, succès avec annulation, objet disparu).

## G84 — Un script de maquettes qui charge des polices système doit p
Rôles : designer
Date : 2026-11-14

Un script de maquettes qui charge des polices système doit prévoir un repli métriquement équivalent (Liberation pour Arial) pour tourner hors du poste d'origine ; le noter en écart.

## G85 — Quand deux niveaux d'alerte partagent une même famille de co
Rôles : designer
Date : 2026-11-14

Quand deux niveaux d'alerte partagent une même famille de couleur, les séparer par la teinte, ajouter un badge texte, rendre les couleurs réglables et refuser deux choix identiques.

## G86 — Dans une application Android avec Room, écrire les opération
Rôles : dev
Date : 2026-11-14

Dans une application Android avec Room, écrire les opérations composées (enregistrer, supprimer avec report) comme méthodes avec corps au-dessus de requêtes de base abstraites, puis tester ces méthodes avec un faux qui n'implémente que les requêtes de base.

## G87 — Quand un élément ajouté n'apparaît pas dans une liste, vérif
Rôles : dev
Date : 2026-11-14

Quand un élément ajouté n'apparaît pas dans une liste, vérifier d'abord que l'écran de la liste lit bien la source de données, avant de chercher une erreur dans l'écriture.

## G88 — Avant d'installer une version de test sur un émulateur persi
Rôles : dev
Date : 2026-11-14

Avant d'installer une version de test sur un émulateur persistant, désinstaller le paquet existant sur l'émulateur seulement (jamais sur un appareil physique) pour éviter un conflit de signature.

## G89 — Un contrôle automatique des littéraux affichés doit viser to
Rôles : testeur
Date : 2026-11-14

Un contrôle automatique des littéraux affichés doit viser tous les fichiers qui produisent du texte visible, pas seulement les écrans de l'élément en cours, sinon les messages construits dans la navigation ou dans les modèles de vue y échappent.

## G90 — Dans une application mobile, ajouter un test unitaire qui li
Rôles : testeur
Date : 2026-11-14

Dans une application mobile, ajouter un test unitaire qui lit les fichiers d'écran et le fichier de ressources. Il vérifie que les identifiants de texte utilisés existent, qu'aucune chaîne n'est écrite en dur et que les apostrophes sont échappées.

## G91 — Un effet de lancement qui appelle le chargement d'un modèle
Rôles : testeur, dev
Date : 2026-11-14

Un effet de lancement qui appelle le chargement d'un modèle de vue se relance à chaque recréation de l'écran. La garde « déjà chargé » appartient au modèle de vue, et un test appelle charger deux fois.

## G92 — Mesurer le contraste des couleurs d'alerte du thème avant de
Rôles : designer
Date : 2026-11-14

Mesurer le contraste des couleurs d'alerte du thème avant de les employer en texte : sous 4,5:1 sur le fond, utiliser une variante plus foncée pour le texte et réserver la teinte vive aux bordures et pastilles.

## G93 — Un modèle de vue sans contexte expose ses messages d'erreur
Rôles : dev, designer
Date : 2026-11-14

Un modèle de vue sans contexte expose ses messages d'erreur sous forme d'identifiants de ressources ; l'écran les résout. Les tests vérifient la présence de l'identifiant, et le texte se lit dans le fichier de ressources.

## G94 — Les règles de pluriel d'une langue peuvent classer zéro comm
Rôles : dev, designer
Date : 2026-11-14

Les règles de pluriel d'une langue peuvent classer zéro comme singulier ; quand un titre doit rester au pluriel pour zéro, utiliser deux chaînes distinctes plutôt qu'un pluriel de ressources.

## G95 — Quand un effet d'écran relance un chargement à chaque change
Rôles : designer
Date : 2026-11-14

Quand un effet d'écran relance un chargement à chaque changement de configuration, ajouter une méthode gardée (sans effet si déjà chargé) et la faire appeler par l'écran, en laissant la méthode de chargement complète intacte pour les rechargements explicites et les tests.

## G96 — Le brief de livraison doit donner le chemin du dossier de cl
Rôles : release
Date : 2026-11-14

Le brief de livraison doit donner le chemin du dossier de clés de signature hors dépôt et du fichier de propriétés, sans que l'agent ait à le chercher dans les scripts précédents.

## G97 — Avant de compiler une livraison, relever le code de version
Rôles : release
Date : 2026-11-14

Avant de compiler une livraison, relever le code de version de la livraison précédente et le comparer à celui du projet : ne monter le code que s'il n'est pas déjà supérieur.

## G98 — Avant de monter le versionCode d'une livraison, relever le c
Rôles : release
Date : 2026-11-15

Avant de monter le versionCode d'une livraison, relever le code le plus élevé de toutes les livraisons précédentes, pas seulement de la dernière de la série.

## G99 — Quand un test lit par réflexion les champs entiers d'une cla
Rôles : testeur
Date : 2026-11-15

Quand un test lit par réflexion les champs entiers d'une classe pour en tirer des identifiants, écarter les champs synthétiques (nom commençant par $) ajoutés par le compilateur.

## G100 — Un NoSuchMethodError sur une méthode existante après un chan
Rôles : testeur
Date : 2026-11-15

Un NoSuchMethodError sur une méthode existante après un changement de type signale un cache de compilation périmé : recompiler à froid avant d'ouvrir un défaut.

## G101 — Quand la destination d'une action n'existe pas encore et que
Rôles : designer
Date : 2026-11-15

Quand la destination d'une action n'existe pas encore et que la navigation est hors périmètre, exposer un rappel à valeur par défaut, ne rien inventer et signaler que l'action reste sans effet jusqu'au câblage.

## G102 — Un contrôle de textes en dur par expression régulière laisse
Rôles : testeur
Date : 2026-11-15

Un contrôle de textes en dur par expression régulière laisse passer les constantes de code lues par les écrans ; en revue, lister chaque objet de constantes textuelles et le comparer au fichier de ressources.

## G103 — Quand des libellés passent de constantes texte à des identif
Rôles : designer
Date : 2026-11-15

Quand des libellés passent de constantes texte à des identifiants de ressources, les listes et propriétés qui les transportent changent de type : chercher tous leurs usages, tests compris, avant la modification.

## G104 — Quand un registre annonce qu'un réglage est appliqué partout
Rôles : testeur
Date : 2026-11-15

Quand un registre annonce qu'un réglage est appliqué partout ou qu'un test existe, chercher les usages du réglage dans les sources et le nom du test avant de le croire.

## G105 — Pour étendre un composant partagé avec un réglage utilisateu
Rôles : designer, dev
Date : 2026-11-15

Pour étendre un composant partagé avec un réglage utilisateur, passer le réglage en paramètre facultatif (nul = comportement actuel) et le charger en arrière-plan, l'écran restant neutre tant que la lecture n'est pas finie.

## G106 — Le brief de livraison doit donner le chemin du fichier de pr
Rôles : release
Date : 2026-11-15

Le brief de livraison doit donner le chemin du fichier de propriétés de signature et du dossier de clés hors dépôt, sans que l'agent ait à les chercher dans les scripts précédents.

## G107 — Une livraison ne déclare vérifié que ce qui a été exécuté ;
Rôles : release
Date : 2026-11-15

Une livraison ne déclare vérifié que ce qui a été exécuté ; un test non lancé est écrit « non vérifié » dans la note d'installation.

## G108 — Une garde de chargement se teste en modifiant la source entr
Rôles : testeur
Date : 2026-11-15

Une garde de chargement se teste en modifiant la source entre deux appels : le second ne doit pas relire ; après une erreur, seul un rechargement explicite relit.

## G109 — Un paramètre optionnel qui vaut null par défaut masque les a
Rôles : testeur
Date : 2026-11-15

Un paramètre optionnel qui vaut null par défaut masque les appels qui oublient de le passer. Pour un réglage annoncé comme appliqué partout, lister les appels du composant partagé et vérifier que chacun transmet la valeur.

## G110 — Une apk de même taille que la livraison précédente n'est pas
Rôles : release
Date : 2026-11-15

Une apk de même taille que la livraison précédente n'est pas forcément la même : comparer le hachage du fichier et le versionCode réel.

## G111 — Quand une correction câble ce qu'un test source gardait expl
Rôles : designer
Date : 2026-11-15

Quand une correction câble ce qu'un test source gardait explicitement comme non câblé, mettre à jour ce test dans la même modification, en gardant l'interdiction de navigation vers une route absente.

## G112 — Un test qui valide un câblage provisoire doit être marqué co
Rôles : testeur
Date : 2026-11-15

Un test qui valide un câblage provisoire doit être marqué comme tel et échouer quand la cible est créée, sinon un toucher sans effet reste vert.

## G113 — Avant de câbler une navigation demandée par une consigne, ch
Rôles : designer
Date : 2026-11-15

Avant de câbler une navigation demandée par une consigne, chercher la route cible dans le code ; si elle n'existe pas, ne pas en inventer une, laisser le rappel sans effet et le signaler avec une question à choix.

## G114 — Avant de lancer un émulateur ou un outil qui ouvre une fenêt
Rôles : release, testeur
Date : 2026-11-15

Avant de lancer un émulateur ou un outil qui ouvre une fenêtre sur le poste de l'utilisateur, demander son accord en question à choix, même si le brief du projet autorise le lancement.

## G115 — Le contrôle des textes affichés parcourt toutes les sources
Rôles : testeur
Date : 2026-11-15

Le contrôle des textes affichés parcourt toutes les sources du module et prouve son efficacité en injectant un faux littéral.

## G116 — Quand la consigne demande explicitement de créer une destina
Rôles : designer
Date : 2026-11-15

Quand la consigne demande explicitement de créer une destination de navigation absente, la créer en version minimale conforme à la fiche et lister ce qui manque, au lieu de laisser le rappel vide.

## G117 — Dans un paquet Android multidex, la recherche d'une classe d
Rôles : release
Date : 2026-11-15

Dans un paquet Android multidex, la recherche d'une classe doit couvrir chaque fichier dex de l'archive, et non le seul premier.

## G118 — Un contrôle automatique des textes affichés doit aussi couvr
Rôles : testeur
Date : 2026-11-15

Un contrôle automatique des textes affichés doit aussi couvrir les objets de constantes de texte lus par les écrans, pas seulement les littéraux passés aux composants.
