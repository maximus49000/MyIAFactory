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
