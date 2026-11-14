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
