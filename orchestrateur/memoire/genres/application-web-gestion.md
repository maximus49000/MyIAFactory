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

## G7 — Pour prouver un correctif de mise en forme (CSS) sans enviro
Rôles : dev
Date : 2026-11-17

Pour prouver un correctif de mise en forme (CSS) sans environnement de rendu réel disponible, un test qui vérifie la présence de la classe CSS attendue sur l'élément concerné suffit comme preuve automatisée (échoue avant, passe après) ; une illustration avant/après peut être produite par un schéma généré en code pur, sans dépendance graphique externe.

## G8 — Dans une application de gestion avec tableaux à statuts déri
Rôles : dev
Date : 2026-11-18

Dans une application de gestion avec tableaux à statuts dérivés, la petite fonction qui calcule le libellé affiché est le point d'entrée le plus rapide pour retrouver la règle métier exacte distinguant les catégories, avant de creuser les modèles de données.

## G9 — Dans un workflow de cadrage à une seule série de questions,
Rôles : dev
Date : 2026-11-18

Dans un workflow de cadrage à une seule série de questions, une correction du périmètre après coup se traite en réécrivant le cahier avec les choix qui en découlent, sans rouvrir une nouvelle série de questions à l'utilisateur.

## G10 — Quand un enregistrement a un champ de statut de verrouillage
Rôles : dev
Date : 2026-11-18

Quand un enregistrement a un champ de statut de verrouillage et un champ de contenu saisi indépendant, une action d'annulation doit croiser les deux pour choisir entre suppression (rien à perdre) et déverrouillage avec conservation du contenu (quelque chose à préserver), plutôt que se baser sur le seul statut.

## G11 — Dans un environnement de développement partagé par plusieurs
Rôles : dev
Date : 2026-11-18

Dans un environnement de développement partagé par plusieurs agents, un serveur déjà en écoute sur le port conventionnel peut appartenir à une autre session et exécuter une version de code antérieure au dernier commit ; avant de l'utiliser comme preuve de fonctionnement, comparer son schéma d'API exposé au code actuel, et ne jamais l'arrêter soi-même pour ne pas perturber le travail d'autrui.

## G12 — Quand un refus signale qu'un téléchargement censé être un fi
Rôles : dev
Date : 2026-11-18

Quand un refus signale qu'un téléchargement censé être un fichier binaire arrive comme du texte/JSON, produire la preuve en appelant la route réelle via un client de test HTTP in-process, sauvegarder les octets reçus sur disque et vérifier leur signature binaire, plutôt que de relire seulement le code source.

## G13 — Dans une application web qui exporte des fichiers Office pro
Rôles : dev
Date : 2026-11-18

Dans une application web qui exporte des fichiers Office protégés par cellule (feuille verrouillée, cellules spécifiques déverrouillées), un utilisateur signalant 'le fichier est en lecture seule' décrit souvent la Vue protégée d'Office déclenchée par le marquage 'provenance Internet' que le système d'exploitation ajoute à tout fichier téléchargé par navigateur — pas un défaut de verrouillage de cellules. Vérifier d'abord le code de protection et son test avant de chercher un bug.

## G14 — Pour un export Excel protégé perçu comme intégralement en le
Rôles : dev
Date : 2026-11-18

Pour un export Excel protégé perçu comme intégralement en lecture seule, plusieurs bandeaux distincts existent côté client avec des boutons différents ; l'absence d'un bouton précis ne prouve pas que la protection du fichier est cassée, seulement qu'un autre bandeau s'affiche — à vérifier en inspectant l'artefact produit, pas seulement le client.

## G15 — Quand un chef de projet résout un point de méthode ou de pro
Rôles : dev
Date : 2026-11-18

Quand un chef de projet résout un point de méthode ou de process de cadrage, cela ne remplace pas les questions fonctionnelles propres à la fonctionnalité elle-même ; les poser avant d'écrire le cahier des charges.

## G16 — Dans un modèle de validation en deux temps (brouillon modifi
Rôles : dev
Date : 2026-11-18

Dans un modèle de validation en deux temps (brouillon modifiable → version figée immuable), une donnée annexe qui n'a pas besoin d'être comparée à une version antérieure n'a pas besoin d'être copiée dans la structure figée : la garder uniquement sur l'entité vivante, avec le même verrou de modification que les autres champs du brouillon, suffit et simplifie le cycle validation/annulation.

## G17 — Avant de reprendre un element de developpement signale comme
Rôles : dev
Date : 2026-11-18

Avant de reprendre un element de developpement signale comme interrompu/repris d'une session precedente, verifier d'abord l'etat reel du code et lancer les tests deja ecrits plutot que de relire ou reecrire le perimetre : cela tranche en quelques secondes entre deja fait et reste a faire.
