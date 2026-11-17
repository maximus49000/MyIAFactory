# Genre : application-web-gestion
Domaine : Application web de gestion interne (backend Python, frontend React/TypeScript) qui importe des données de plusieurs sources, fait des calculs métier qui doivent être exacts, et les restitue en tableaux et graphiques pour piloter une activité professionnelle.
Livrable : à préciser
Outils : à préciser

## G1 — Quand une demande de correction exige une preuve vérifiable
Rôles : dev
Date : 2026-11-16

Quand une demande de correction exige une preuve vérifiable et que le correctif est déjà en place, produire une preuve au niveau le plus proche de l'usage réel possible sans ouvrir une fenêtre sur le poste (ex. appel de la vraie route HTTP via un client de test en mémoire) plutôt que de se contenter de rappeler un test unitaire déjà existant.

## G2 — Dans un dossier de travail partagé par plusieurs agents conc
Rôles : dev
Date : 2026-11-16

Dans un dossier de travail partagé par plusieurs agents concurrents, un fichier modifié mais non committé par l'un peut se retrouver absorbé dans le commit d'un autre agent exécutant une opération de commit large (type « tout »). Ne pas corriger cet historique a posteriori ; vérifier que le contenu voulu y figure et poursuivre.

## G3 — Dans une application de gestion, un terme utilisateur comme
Rôles : dev
Date : 2026-11-17

Dans une application de gestion, un terme utilisateur comme « menu de sélection » ou « bandeau déroulant » peut désigner la navigation principale (sidebar) et non un composant de formulaire ; chercher aussi du côté des fichiers de configuration de routes/navigation avant de restreindre la recherche aux composants de type select.

## G4 — Quand une fonctionnalité doit remplacer plusieurs écrans exi
Rôles : dev
Date : 2026-11-17

Quand une fonctionnalité doit remplacer plusieurs écrans existants par un seul composant composite, construire et tester ce composant isolément sur le premier cas représentatif avant de modifier le routage/menu global évite de casser la navigation en cours de validation.

## G5 — Quand on retire une URL en faveur d'une URL paramètrée, préf
Rôles : dev
Date : 2026-11-17

Quand on retire une URL en faveur d'une URL paramètrée, préférer une redirection 301/302 avec paramètre préséléctionné plutôt qu'une simple suppression, pour préserver les bookmarks et liens externes.

## G6 — Pour intégrer un écran existant comme onglet d'un composant
Rôles : dev
Date : 2026-11-17

Pour intégrer un écran existant comme onglet d'un composant conteneur, le réutiliser sans modification et mocker ses appels API dans le test du conteneur, à l'identique de ce que fait le test de l'écran d'origine.
