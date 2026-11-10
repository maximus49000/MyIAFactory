# MyIAFactory — projet 1 : le bureau vivant

Date : 2026-11-10. Document de conception, à lire avant le plan de réalisation.

Convention : ce qui vient de l'utilisateur est écrit sans mention. Ce qui est un choix du rédacteur est marqué **[choix]** et peut être remis en cause par l'utilisateur.

## 1. Le contexte et le pourquoi

L'utilisateur fait déjà tourner une « factory » sur un de ses projets : une conversation Claude orchestratrice répartit le travail entre des sessions cloud et des sous-agents locaux, et tient un tableau de suivi.

Ce qui ne va pas aujourd'hui :

- tâches, livrables, suivi et reporting sont dispersés entre plusieurs onglets ;
- le suivi est un tableau de cartes, fonctionnel mais « boring ».

Ce qu'il veut : **une skill** réutilisable sur n'importe quel projet, qui montre la factory comme un bureau d'entreprise de jeu vidéo, joli et vivant, où l'on voit d'un coup d'œil qui travaille sur quoi et où l'on trouve tout au même endroit. Le but est de rendre le travail moins ennuyeux, pas seulement plus lisible.

## 2. Ce dépôt ne contient aucun projet

Ce dépôt GitHub public contient **la skill vide de tout projet**. Un projet qui veut son bureau l'implémente chez lui : c'est dans le dépôt du projet que vivent son adaptateur, ses réglages et ses données. Le premier projet branché a sa conception de branchement dans son propre dépôt, pas ici.

Conséquences :

- rien de propre à un projet n'entre ici : ni adaptateur, ni réglages, ni noms de fichiers d'un projet ;
- rien de privé non plus : aucune clé, aucun jeton, aucune adresse de session ;
- le dépôt fournit un exemple de démonstration pour essayer le bureau sans projet ;
- on pousse l'avancée au fur et à mesure, après chaque étape qui produit quelque chose ;
- le README explique comment ça fonctionne, quelles étapes sont réalisées et ce qu'il reste à faire ; un manuel d'installation et de configuration l'accompagne. Les deux sont tenus à jour à chaque étape.

## 3. La vision complète (quatre projets)

La skill finale se construit en quatre projets, conçus et livrés l'un après l'autre. **Ce document ne couvre que le projet 1.**

1. **Le bureau vivant** (ce document) : la scène, les agents qui bougent selon ce que fait réellement l'orchestrateur, la charge de l'ordinateur.
2. **Les dossiers des services** :
   - clic sur un agent : toutes ses tâches en cours ;
   - Facturation : tokens dépensés au total, puis par projet, par fonctionnalité, par micro-tâche, et pour chaque micro-tâche le coût décomposé par service (dev, QA…) et le nombre d'allers-retours ; réglage des limites (par exemple 60 % maximum pour les agents cloud, 80 % maximum pour la factory cette semaine ; **[choix]** pourcentage du quota hebdomadaire de l'abonnement Claude) ;
   - QA : liste des cas de test répartis par compétence métier ;
   - Métier : cahiers des charges ;
   - Directeur : toutes les actions que l'utilisateur doit valider ou décider, issues de la réflexion et des apprentissages des agents.
3. **Le parcours d'une tâche** : création d'une tâche depuis le bureau (à défaut, dans une conversation Claude dédiée), questions pour comprendre le besoin, explication de la méthode, cahier des charges, découpage en micro-tâches lançables en autonomie, QA qui cherche anomalies et incohérences, les note pour que le dev ne les refasse pas, puis décide de passer en exploitation ou de renvoyer au dev. L'orchestrateur choisit seul l'agent le plus qualifié ; chaque agent a un modèle attribué, de Haiku à Fable, et Fable ne sert que sur demande de l'utilisateur pour ce qui paraît très complexe.
4. **L'installation sur un projet** : à la première initialisation, demander le répertoire de travail, scanner le projet, proposer les services nécessaires (dont une équipe Intégration distincte de l'équipe Dev s'il y a un moteur comme Unity), calibrer le nombre d'agents en parallèle sur les capacités de la machine, demander si l'on veut un renfort d'agents cloud. C'est aussi là que le tout est emballé en skill.

## 4. Ce que l'utilisateur voit

Une page web locale, ouverte dans le navigateur, montrant un open space en 3D isométrique (caméra fixe en biais, façon Two Point Hospital). Style retenu par l'utilisateur sur maquette : isométrique.

- **Le voyant de la factory** : en marche ou en pause, visible en permanence.
- **La barre de charge** de l'ordinateur, en haut (§6).
- **Un bureau par service** déclaré par le projet (Métier, Dev, QA, Intégration, Facturation…), plus le bureau du Directeur, le coin café et, au centre de l'open space, le tableau Kanban.
- **Les agents** : des personnages avec un vrai prénom, un service et un modèle.
  - Au travail : à son poste, avec une bulle au-dessus de la tête qui dit qu'il travaille et sur quoi.
  - Sans travail : il va au coin café se détendre. Dès qu'on lui confie quelque chose, il retourne à son poste.
  - Quand une de ses tâches change de colonne : il se lève, marche jusqu'au Kanban, déplace le post-it dans la bonne colonne, puis repart (à son poste s'il a encore du travail, sinon au café).
- **Le Kanban** : un post-it par tâche, rangé par colonne.
- **Le bureau du Directeur** : l'utilisateur lui-même, avec une pastille portant le nombre de décisions qui l'attendent.

**[choix]** Dans le projet 1 :

- La page est en **lecture seule** : elle montre, elle ne commande pas la factory. Seule exception : le réglage de la charge maximum (§6).
- Survol ou clic sur un agent : une petite carte (prénom, service, modèle, local ou cloud, titres de ses tâches en cours). Le panneau complet est le projet 2.
- Clic sur un post-it : titre, colonne, agent, dernière étape notée.
- Clic sur un service : un panneau s'ouvre à droite sans quitter la scène (disposition validée sur maquette), avec le nom du service et ses agents ; le contenu documentaire arrive au projet 2.
- Les agents cloud sont dans les mêmes bureaux que les autres, avec un petit nuage au-dessus de la tête.
- L'orchestrateur est lui aussi un personnage (le chef d'atelier), posté près du Kanban.
- La page est en français.

## 5. D'où vient la vérité

Règle : **rien n'est simulé.** Ce qu'on voit correspond à l'état réel de la factory. Les seules libertés sont de mise en scène (durée d'une marche, animation d'attente au café).

### 5.1 Le relevé : le contrat entre un projet et le bureau

**[choix]** Le bureau ne connaît aucun projet. Chaque projet fournit un **relevé** : un petit document qui dit les faits bruts, dans un format fixé par ce dépôt. Le projet le fournit soit en tenant un fichier à jour, soit en donnant une commande que le bureau lance pour l'obtenir. Le relevé contient :

- le nom du projet et l'état de la factory (en marche / en pause, depuis quand) ;
- les services du projet ;
- les colonnes du Kanban, dans l'ordre ;
- les titulaires : pour chacun une clé stable, son service, local ou cloud, et si le projet le sait son modèle, s'il est permanent, s'il est le chef d'atelier ;
- les tâches : identifiant, titre, colonne, active ou non, titulaire, étape en clair, date de dernière mise à jour, avec ou sans post-it ;
- la file d'attente (les premiers éléments et le nombre restant) ;
- le nombre de décisions en attente pour le Directeur.

Le bureau en déduit ce que la page affiche. Tout ce qui suit dans cette section est fait par le bureau, de la même façon pour tous les projets.

### 5.2 Les prénoms

Le relevé ne donne pas de prénom : c'est le bureau qui en attribue un à chaque clé de titulaire, avec une couleur, et qui s'en souvient dans un fichier d'équipe rangé avec les réglages du projet. Un agent qui revient retrouve son prénom. L'utilisateur peut changer prénoms et modèles dans ce fichier.

### 5.3 Qui travaille

Un relevé ne dit pas si quelqu'un travaille vraiment en ce moment : une factory arrêtée depuis des jours laisse des tâches dans un état actif. Une règle fondée sur l'état seul montrerait un bureau affairé alors que tout est arrêté. **[choix]** Trois situations :

- **au travail** : l'agent tient une tâche active dont la dernière mise à jour est récente. Il est à son poste avec sa bulle ;
- **sans nouvelles** : il tient une tâche active, mais elle n'a pas bougé depuis plus longtemps que le délai de fraîcheur. Il reste à son poste, sans animation de travail, avec une bulle grisée « sans nouvelles depuis 2 h ». On ne prétend ni qu'il travaille ni qu'il est libre ;
- **libre** : aucune tâche active, il est au café.

Délai de fraîcheur par défaut : 30 minutes, réglable, et réglable par titulaire dans le relevé pour les travaux longs et silencieux.

Quand la factory est en pause, le voyant le dit et la lumière de l'open space baisse ; les agents dont la tâche continue d'être mise à jour restent « au travail » (la pause laisse finir ce qui tourne), les autres vont au café. Si la factory est « en marche » mais que rien n'a été mis à jour depuis le délai de fraîcheur, le voyant affiche « en marche, sans activité depuis… ».

Un agent sans tâche active reste au café 24 h après sa dernière activité, puis quitte le bureau, pour ne pas remplir la pièce de fantômes. Les permanents ne partent jamais. Une clé de titulaire inconnue du fichier d'équipe crée un nouvel agent plutôt que de masquer du travail réel.

### 5.4 Le déplacement du post-it

L'utilisateur le veut « pendant les derniers moments de réflexion de l'agent ». Un relevé ne dit pas qu'un agent est sur le point de finir ; il dit que la colonne a changé. **[choix]** La page compare deux relevés successifs : quand une tâche a changé de colonne, **l'agent qui la tenait avant le changement** (celui qui vient de finir son étape) va au Kanban et déplace le post-it. L'animation suit donc le changement réel de quelques secondes au lieu de le précéder ; le projet 3, où la skill pilotera les agents, pourra l'annoncer à l'avance.

- Si l'ancien titulaire est le chef d'atelier, ou n'est plus là, c'est le chef d'atelier qui se déplace.
- Une tâche qui apparaît est posée par le chef d'atelier.
- Si plusieurs tâches changent en même temps, les agents font la queue au tableau ; au-delà de six en attente, les post-its suivants sont déplacés directement.
- À l'ouverture de la page, les post-its sont posés à leur place sans rejouer l'historique.

### 5.5 Le service

**[choix]** Un petit serveur local sert la page et l'état, en Python avec la seule bibliothèque standard. Il n'écoute que sur la machine. La page redemande l'état toutes les quelques secondes. Si le relevé est illisible ou le serveur injoignable, la page garde la dernière scène connue et l'indique clairement plutôt que d'afficher un bureau vide.

## 6. La charge de l'ordinateur

- Une **barre de charge** en haut du bureau évalue la charge réelle de l'ordinateur.
- Dans le bureau Facturation, on règle la **charge maximum** en dessous de laquelle on a le droit de lancer une nouvelle tâche. Tant que la charge n'est pas redescendue, l'étape suivante ne démarre pas.
- Un bouton **« Me conseiller »** propose la meilleure charge supportable par cet ordinateur.
- On évalue la charge réelle de la machine : les sessions cloud ne comptent pas, puisqu'elles n'utilisent pas la machine.

**[choix]** Comment c'est fait :

- *Mesure* : processeur (lissé sur une minute, pour ne pas réagir à un pic) et mémoire utilisée, relevés par le serveur avec la bibliothèque standard de Python (appels système Windows, aucun paquet à installer). La barre affiche le plus élevé des deux, le détail au survol, et un trait à l'endroit du maximum réglé. Elle change de couleur au-dessus du maximum. Sur un autre système que Windows, la barre affiche « mesure indisponible » en attendant le projet 4.
- *Cloud* : la mesure porte sur la machine, donc le cloud en est exclu d'office. Le blocage ne concerne que les étapes locales.
- *Réglage* : il est enregistré dans les réglages du projet. Valeur de départ : 75 %.
- *« Me conseiller »* : le serveur garde un historique de la charge avec le nombre d'agents locaux au travail à chaque relevé. Le bouton s'appuie sur cet historique et sur les caractéristiques de la machine (cœurs, mémoire) pour proposer une valeur et l'expliquer en une phrase. L'utilisateur accepte ou non. Dans le projet 1 c'est un calcul immédiat, sans tokens ; au projet 3, quand le bureau saura parler à l'orchestrateur, c'est Claude qui affinera le conseil. Sans historique suffisant, le bouton le dit et propose une valeur prudente tirée des seules caractéristiques de la machine.
- *Blocage* : le bureau fournit une commande que l'orchestrateur d'un projet appelle avant de lancer une étape locale, et qui répond « on peut y aller » ou « trop chargé, attendre ». C'est au projet d'ajouter cet appel à ses consignes.

## 7. Comment c'est fabriqué

- **[choix]** Scène 3D dans le navigateur avec three.js et une caméra orthographique en vue isométrique. Pas de moteur de jeu : la page doit rester légère.
- **[choix]** three.js est copié en local dans le dépôt (pas chargé depuis internet à chaque ouverture). Ce téléchargement demande l'accord de l'utilisateur au moment de le faire.
- **[choix]** La logique « qui est où et fait quoi » est séparée du rendu 3D, pour être testée sans navigateur.
- **[choix]** La scène fonctionne d'abord avec des volumes simples, puis les modèles Tripo les remplacent un par un. Un modèle manquant ne casse rien.

### 7.1 Les modèles Tripo

L'utilisateur veut un rendu joli et génère lui-même les modèles sur son compte Tripo :

- le rédacteur propose le prompt en anglais, 1000 caractères maximum espaces compris, avec la liste complète des réglages Tripo Studio ; jamais un prompt seul ;
- plusieurs objets par génération, côte à côte sans se toucher, séparés ensuite ; les modèles articulés ou animés restent seuls ;
- une génération à la fois : le prompt suivant n'est donné qu'après vérification et intégration du résultat précédent.

Générations prévues :

1. mobilier de bureau : bureau, chaise, écran, armoire à dossiers, étagère, plante ;
2. espaces communs : machine à café, canapé, table basse, tableau Kanban sur pieds, grand bureau du Directeur ;
3. un personnage de base, articulé.

L'utilisateur a accepté, dans un premier temps, **un seul personnage de base** décliné par la page en couleurs, avec le prénom au-dessus. Des agents vraiment différents pourront venir plus tard.

Ce que Tripo sait réellement faire pour le personnage n'est pas vérifié ; le résultat de la génération 3 tranchera. **[choix]** Replis prévus :

- animations : seule la marche est attendue de Tripo. « Taper au clavier » et « boire un café » sont faites dans la page (pose d'attente, léger mouvement des bras, une tasse) ;
- couleurs : le personnage est généré en gris clair et la page applique une teinte par agent ;
- si le personnage Tripo n'est pas exploitable, l'outil autosprite déjà installé chez l'utilisateur est l'autre piste, à lui proposer avant de l'utiliser.

**[choix]** Style visuel : gouache douce, formes simples et trapues de jeu de gestion. Modèles en GLB. Sol, murs et post-its sont de la géométrie simple faite dans la page.

## 8. Ce qui n'est pas dans le projet 1

- Commander la factory depuis le bureau (pause, création de tâche, déplacement de post-it par l'utilisateur).
- Le contenu des dossiers : facturation et tokens, cas de test, cahiers des charges, liste détaillée des décisions.
- Le choix automatique de l'agent et du modèle, les apprentissages de la QA.
- Le scan d'un projet, le calibrage du nombre d'agents, le renfort cloud, l'emballage en skill.

## 9. Ce qui serait un échec même si ça marche

- Un bureau qui montre des agents affairés alors que rien ne tourne, ou l'inverse.
- Un bureau qui ralentit la machine.
- Quoi que ce soit de propre à un projet, ou de privé, dans ce dépôt public.
- Un rendu « outil interne » : l'utilisateur veut du joli et du ludique.

## 10. C'est réussi quand

- Avec l'exemple de démonstration, on lance le bureau en une commande et on voit l'équipe : les agents au travail à leur poste, les autres au café, le Kanban rempli.
- On change la colonne d'une tâche dans le relevé : dans les secondes qui suivent, l'agent concerné marche jusqu'au Kanban et déplace le post-it.
- On passe la factory en pause dans le relevé : le voyant change.
- La barre de charge suit la charge réelle, et « Me conseiller » propose une valeur expliquée.
- Un projet réel se branche sans qu'on touche à ce dépôt.
- L'utilisateur a envie de laisser la page ouverte.

## 11. Laissé au constructeur

- Le plan exact de l'open space, les trajets des agents, les durées d'animation.
- L'intervalle de rafraîchissement, l'organisation des fichiers.
- Les prénoms par défaut (prénoms français courants) et la palette de couleurs.
- Le choix de l'outil de test.
