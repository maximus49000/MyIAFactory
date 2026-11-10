# Le parcours d'une tâche — conception

Date : 2026-11-10. Projet 3 de la vision. Suite de `2026-11-10-bureau-vivant-design.md` (« la conception du bureau »), `2026-11-10-bureau-qui-agit-design.md` et `2026-11-10-dossiers-des-services-design.md` : à lire avant celle-ci.

Convention : ce qui vient de l'utilisateur est écrit sans mention. Ce qui est un choix du rédacteur est marqué **[choix]**.

## 1. Pourquoi

L'utilisateur fait déjà tourner une factory sur un premier projet, appelé ici **le projet pilote** (son dépôt est privé, son nom n'entre pas ici). C'est une conversation Claude orchestratrice, qui suit des consignes écrites pour ce projet seul. Elle répartit les étapes entre des agents spécialistes déclarés par fiches, en local ou en cloud, et le bureau la montre et la commande.

La manière de travailler de l'utilisateur, telle qu'il la décrit :

1. on échange avec l'IA pour bien cibler le besoin et la solution ;
2. on décompose en projet, et on cherche la récurrence : pour faire trois villes, on se concentre sur une ville, puis bâtiment par bâtiment ;
3. on cherche d'abord à faire **en itération** pour **valider la méthode** ;
4. puis on **industrialise** la méthode, quand la factory travaille en série autour d'un même besoin ;
5. ensuite on développe, on intègre et on teste, avec des **tests croisés entre deux agents Claude** pour une plus grande couverture.

Le projet pilote fait déjà bien plusieurs de ces choses :
- une méthode mise au point sur un élément puis rejouée ;
- un registre de contrôles où chaque correction devient une vérification faite plus tôt ;
- des spécialistes à modèle attitré ;
- la règle « les outils d'abord » ;
- deux relectures indépendantes en boucle.

Il lui manque :
- le cadrage et le cahier des charges, qui se font hors de la factory ;
- le découpage, qui se fait à la main ;
- la validation de la méthode, qui n'est pas une étape visible ;
- le renvoi vers la méthode quand un élément échoue plusieurs fois.

L'utilisateur veut **un orchestrateur générique, qui convienne à n'importe quel projet**, et que **le projet pilote puisse reprendre tel quel** : « tout le fonctionnement actuel doit être récupéré. On ajoute des fonctionnalités à ce nouvel orchestrateur, on ne casse pas ».

## 2. Buts, non-buts, contre-buts

**Buts.**
- Un orchestrateur générique, fourni par la skill, qui mène une fonctionnalité du cadrage jusqu'à la production en série.
- Une mémoire à trois étages : la skill, le genre de projet, le projet.
- Un bureau qui suit plusieurs projets, avec un bouton « Nouvelle fonctionnalité » et une discussion de cadrage dans un panneau, le catalogue de chaque fonctionnalité et le dernier livrable de chaque projet.
- Le projet pilote passe sur l'orchestrateur générique sans rien perdre.

**Non-buts.**
- Plusieurs modèles de présentation (gabarits) au choix pour le catalogue : ce sera fait plus tard.
- L'installation sur un nouveau projet (scan, proposition des services, calibrage, emballage en skill) : c'est le projet 4.
- Une IA d'un autre fournisseur.
- L'accès depuis le téléphone.
- La création automatique de sessions cloud : elle est impossible sans un message de l'utilisateur, c'est donc lui qui les crée.

**Contre-buts** (ce qui ferait un échec même si cela « marche »).
- Le projet pilote perd un comportement qu'il a aujourd'hui.
- Une mémoire de genre servie à un projet d'un autre genre.
- Une mémoire de la skill ou d'un genre qui cite un projet précis : un nom, un lieu, un fichier ou une personne.
- Le bureau qui agit lui-même ou qui appelle une IA.
- Fable utilisé sans demande expresse de l'utilisateur.
- Un nom, un chemin ou un fichier propre à un projet réel dans ce dépôt public.

## 3. Les règles qui ne bougent pas

- Ce dépôt reste **vide de tout projet** : rien de propre à un projet, rien de privé.
- **Le bureau n'agit jamais lui-même** : chaque geste devient une demande remise à la commande d'actions du projet, et son effet n'apparaît qu'au relevé suivant. **La discussion de cadrage suit cette règle** : le bureau ne parle à aucune IA (l'utilisateur a choisi cette voie, plus lente, contre un bureau qui lancerait Claude lui-même).
- Python : bibliothèque standard seulement. Les textes venus d'un projet s'affichent comme du texte, jamais comme du HTML.
- Un relevé version 1, 2 ou 3 continue de marcher tel quel. Un bureau lancé sur un seul fichier de réglages marche comme aujourd'hui.
- Le plus petit modèle capable. Fable seulement sur demande expresse de l'utilisateur.

## 4. Le parcours d'une fonctionnalité

Vocabulaire **[choix]** :
- un **projet** contient des **fonctionnalités**, par exemple « ville 3D » dans une application de jeu ;
- une fonctionnalité a un **cahier des charges**, puis un **découpage** en **éléments** (le bâtiment de l'exemple de l'utilisateur), regroupés en **groupes** (la ville) ;
- chaque élément passe par des **micro-tâches** : une étape du flux, tenue par un agent, qui est un post-it du Kanban.

Les étapes d'une fonctionnalité, dans l'ordre. L'étape en cours est montrée dans le bandeau du panneau de la fonctionnalité (§6.3).

1. **Cadrage.** Un agent de cadrage du service Métier pose ses questions dans la discussion (§6.3) jusqu'à ce que le besoin et la solution soient clairs. L'orchestrateur y propose aussi **le genre du projet** si le projet n'en a pas encore (§5).
2. **Cahier des charges.** Il porte deux pièces : **une maquette**, qui permet de valider la bonne compréhension du besoin, et **la liste des étapes à réaliser dans l'ordre**. L'utilisateur le valide, ou demande une correction, depuis le panneau. C'est une décision du Directeur.
3. **Découpage.** On identifie l'élément qui se répète et les groupes, puis on dresse la file des éléments. La file est celle du relevé (`file`), comme aujourd'hui.
4. **Prototype.** La méthode est mise au point **en itération, avec l'utilisateur**, sur le premier élément. Elle est passée par le même flux que la série (dev, intégration, relecture croisée), mais l'utilisateur fait ses retours à chaque tour. **[choix]** Ces retours passent par la discussion de la fonctionnalité, où l'agent montre les images de chaque tour.
5. **Méthode validée.** L'utilisateur valide la méthode, ce qui est une décision du Directeur. La méthode est alors écrite : son document, les briefs de chaque rôle, et les contrôles de départ. Elle porte une **version**, la « passe » du catalogue.
6. **Série.** La factory applique la méthode à chaque élément de la file sans attendre l'utilisateur :
   - dev, puis intégration ;
   - **relecture croisée** par deux agents Claude indépendants, chacun avec un contexte neuf, aucun ne voyant le rapport de l'autre avant d'avoir rendu le sien ;
   - corrections, puis un nouveau tour de relecture, tant qu'une des deux relectures trouve quelque chose ;
   - catalogue, puis « fait ».
   L'utilisateur suit et fait ses retours depuis le catalogue (§6.4). Il n'est sollicité que pour les leçons, les décisions bloquantes et les sessions cloud à créer.
7. **Terminée** quand la file est vide et que tous les éléments sont faits.

**En continu, pendant toutes les étapes :**
- chaque correction et chaque point de relecture devient un contrôle du registre du projet, passé **avant** de rendre un élément ;
- chaque agent note ses leçons ;
- la règle « les outils d'abord » s'applique (§7.2).

**Méthode à revoir.** **[choix]** Quand un élément dépasse un nombre de tours de corrections (réglage du projet, 3 par défaut), ou quand le même contrôle échoue sur deux éléments différents, l'orchestrateur pose une décision au Directeur : « méthode à revoir ? ».
- Si l'utilisateur accepte, la fonctionnalité repasse à l'étape 4 sur cet élément, puis à l'étape 5 (nouvelle version de la méthode). Les éléments faits avec une version plus ancienne restent faits. Le catalogue les marque « à réévaluer » si la nouvelle version les concerne.
- Si l'utilisateur refuse, l'élément suit le traitement « bloqué » du projet.

**Choisir l'agent et le modèle.**
- L'orchestrateur choisit seul **le spécialiste libre du rôle de l'étape**. Un agent ne tient qu'une tâche à la fois. Si aucun spécialiste du rôle n'est libre, la tâche attend.
- Le modèle de départ est celui de la fiche de l'agent. **On peut monter si une tâche semble complexe**, d'un cran (Haiku vers Sonnet, Sonnet vers Opus). Fable n'est utilisé que sur demande expresse de l'utilisateur.
- Toute montée est notée sur la tâche (le modèle de départ, le modèle utilisé, la raison en une phrase) et se voit dans le panneau de la tâche et dans la facturation, qui compte déjà les usages par modèle.
- En local, l'orchestrateur crée simplement le sous-agent avec le modèle plus fort.
- En cloud, le modèle d'une session est fixé à sa création, et une session ne peut être créée que sur un message de l'utilisateur. **On déclare donc d'autres agents cloud** : une fiche par couple rôle et modèle (par exemple un préparateur sur Sonnet et un autre sur Opus), chacun avec sa session attitrée.
- **[choix]** S'il manque l'agent cloud du bon rôle et du bon modèle, l'orchestrateur pose une décision au Directeur (« créer une session cloud pour … ») au lieu de bloquer en silence. En attendant, il prend l'agent local équivalent si le mode et la charge le permettent.

## 5. La mémoire à trois étages

| Étage | Ce qu'il garde | Où | Qui le lit |
|---|---|---|---|
| **La skill** | ce qui touche au **processus pur** de la skill et peut améliorer les itérations de **n'importe quel projet** | ce dépôt, `orchestrateur/memoire/skill.md` **[choix]** | tous les orchestrateurs |
| **Le genre** | ce qui vaut pour **tous les projets d'un même genre** ; général, il **ne cite aucun projet précis** | ce dépôt, `orchestrateur/memoire/genres/<id>.md` **[choix]**, un fichier par genre, avec en tête sa description (domaine, livrable, outils) | les orchestrateurs des projets de ce genre, et eux seuls |
| **Le projet** | ce qui ne vaut que pour le projet : fiches, contrôles, méthodes | le dépôt du projet, comme aujourd'hui | l'orchestrateur du projet |

**Le genre d'un projet.**
- Au premier cadrage d'un projet qui n'a pas encore de genre, l'orchestrateur décrit le projet en une phrase (domaine, livrable, outils).
- Il la compare aux genres déjà connus et **propose** soit un genre existant, soit un nouveau.
- L'utilisateur confirme ou choisit l'autre option : c'est une décision du Directeur.
- Le genre est rattaché au **projet**, et toutes ses fonctionnalités en profitent. Il est noté dans le fichier du projet (§7.1).
- Un projet d'un autre genre ne lit jamais ce fichier.

**Le tri d'une leçon.**
- Chaque leçon arrive comme aujourd'hui : l'agent l'écrit en fin d'étape, elle est notée « à valider » sur sa fiche, puis le Directeur la valide ou l'invalide.
- L'orchestrateur lui ajoute **un étage proposé** (projet, genre ou skill).
- Pour l'étage genre ou skill, il ajoute aussi **le texte réécrit en termes généraux**, sans nom de projet, de lieu, de fichier ni de personne. C'est ce texte que l'utilisateur valide, mot pour mot.
- L'utilisateur peut changer l'étage au moment de son verdict (§6.5).
- Une fois validée, une leçon de projet va sur la fiche de l'agent, comme aujourd'hui.
- Une leçon de genre ou de skill est ajoutée par l'orchestrateur au fichier de mémoire de ce dépôt, puis commitée et poussée. **[choix]** Le dépôt local est d'abord mis à jour (`git pull --rebase`), puisque plusieurs orchestrateurs peuvent y écrire. En cas de conflit, l'orchestrateur s'arrête et le signale au lieu de forcer.
- **[choix]** Avant ce commit, l'orchestrateur vérifie que le texte ne contient aucun des **mots interdits** listés par le projet (son nom, ses lieux, ses chemins), et s'arrête s'il en trouve un.

**Lire la mémoire.** Au démarrage, puis à chaque nouvelle fonctionnalité, l'orchestrateur relit la mémoire de la skill et celle du genre du projet. Le message de départ d'un agent (§7.3) contient les leçons de genre et de skill qui touchent son rôle **[choix]** (chaque leçon porte les rôles qu'elle concerne, ou « tous »).

## 6. Ce que l'utilisateur voit dans le bureau

L'utilisateur a choisi sur maquette : **un projet à la fois avec un sélecteur**, **la discussion dans un panneau à droite** (la scène reste visible), et **le catalogue dans le bureau**, dont la première version reprend tout le catalogue actuel du projet pilote.

### 6.1 Plusieurs projets

- Un seul bureau suit plusieurs projets. Dans la barre du haut, le nom du projet devient un **sélecteur**. Un projet qui attend une décision du Directeur porte une pastille avec ce nombre dans le sélecteur.
- L'open space, le Kanban, les dossiers des services, la facturation et les KPI ne montrent que le projet choisi.
- **[choix]** Le choix est retenu dans le navigateur, et le dernier projet choisi s'ouvre au lancement.
- **[choix]** La configuration du bureau devient un fichier qui liste les réglages des projets : `lancer.py serveur --bureau bureau.local.json`, avec `{"projets": ["<chemin>/.factory/reglages.json", …]}`. Chaque projet garde son `.factory/reglages.json` sans changement. `--reglages <un fichier>` marche comme aujourd'hui, avec un seul projet et sans sélecteur. Un seul port, pris dans le fichier du bureau (8770 par défaut).
- **[choix]** La charge est mesurée pour la machine. La charge maximum reste dans les réglages de chaque projet, puisque la commande `charge` de chaque orchestrateur la lit. La barre de charge montre celle du projet choisi.
- **[choix]** Les fichiers que le bureau écrit (équipe, historiques) restent à côté des réglages de chaque projet, comme aujourd'hui.

### 6.2 La barre du haut

Elle garde le voyant, Pause, la documentation, « Toutes les tâches » et la charge. Elle gagne deux boutons :
- **« + Nouvelle fonctionnalité »** : il ouvre une discussion neuve pour le projet choisi (§6.3).
- **« Dernier livrable »** : il ouvre le dernier livrable du projet choisi (un lien, ou un fichier servi comme les images).
  - Avec plusieurs fonctionnalités, un petit menu propose le dernier livrable de chacune, le plus récent en premier.
  - Un projet qui a déjà un bouton de livraison dans `actions` le garde.

### 6.3 La fonctionnalité et sa discussion

- Le panneau d'une fonctionnalité s'ouvre à droite. On l'ouvre avec « Nouvelle fonctionnalité », ou depuis une liste « Fonctionnalités » du projet **[choix]** : un bouton de la barre, ou le bureau Métier.
- En haut du panneau : le nom de la fonctionnalité et **le bandeau du parcours** (Cadrage › Cahier des charges › Découpage › Prototype › Méthode › Série), avec l'étape en cours en gras.
- **La discussion** :
  - les messages de l'utilisateur et ceux de l'agent (prénom et service), du plus ancien au plus récent, **avec des images** dans les deux sens : l'utilisateur joint les siennes (photos de référence, croquis), l'agent montre sa maquette ;
  - une zone de saisie, avec le bouton « Joindre une image » ;
  - une ligne « <prénom> est en train d'écrire… » tant qu'un message de l'utilisateur attend sa réponse.
- Chaque message envoyé devient une demande. La réponse arrive au relevé suivant, ce qui prend quelques secondes à une minute (§7.4).
- La première demande d'une discussion neuve crée la fonctionnalité. **[choix]** Son nom est proposé par l'agent de cadrage et l'utilisateur peut le changer dans la discussion.
- **Sous la discussion, les pièces du cahier des charges** :
  - la maquette (images) et la liste des étapes, numérotée ;
  - les boutons « Valider le cahier des charges » et « Demander une correction » (celui-ci envoie le texte écrit dans la saisie) ;
  - à l'étape Méthode : le lien vers le document de la méthode et le bouton « Valider la méthode ».
- Pendant le cadrage, l'agent de cadrage est à son poste au Métier, avec sa bulle « Cadrage : <fonctionnalité> ». Le cadrage est une tâche du Kanban comme une autre.

### 6.4 Le catalogue d'une fonctionnalité

- **Un catalogue par fonctionnalité.** Il liste tout ce qui a été réalisé, avec une photo si l'élément est graphique, et permet de faire un retour pour chaque élément de la liste.
- Il s'ouvre dans le panneau de droite, ou en grand à la demande **[choix]** (bouton « Agrandir »). On l'ouvre depuis le panneau de la fonctionnalité ou depuis « Dernier livrable ».
- Son format de données est fixé par la skill (§8.3). **La première version reprend tout le design du catalogue actuel du projet pilote**, avec les noms généralisés (élément, groupe).

**Chaque fiche d'élément montre :**
- le nom, l'identifiant, le groupe et l'état ;
- la capture principale, avec la passe qui l'a produite et le nombre de passes ;
- **la comparaison avec la référence, à plusieurs prises de vues** : un sélecteur d'angle, une barre à glisser entre « Produit » et « Réel », et le crédit de la photo avec son lien ;
- la note, les caractéristiques (libellé et valeur, avec une pastille de couleur si la valeur est une couleur) et les liens de référence ;
- les éléments communs qu'il utilise (le kit) ;
- un événement passager s'il en a un ;
- **la connaissance** : les leçons appliquées à l'élément, et « à réévaluer » avec les leçons plus récentes qui le concernent ;
- **le doute** : sa date, sa raison et ce qui le lèverait ;
- le bouton **« Demander à modifier »**, puis le suivi de chaque retour sur la fiche (texte, état, réponse).

**La page du catalogue montre :**
- le choix du groupe, avec pour chaque groupe ses compteurs ;
- **la vue de haut**, une carte des éléments si ceux-ci ont une position : une couleur par état, un clic mène à la fiche, et on peut zoomer et se déplacer ;
- les compteurs généraux ;
- les demandes de modification et leurs réponses ;
- **les passes**, c'est-à-dire les versions de la méthode, avec leur date et le nombre d'éléments de chacune ;
- « Ce que j'ai appris » : les leçons, avec leur portée ;
- les filtres (passe, à réévaluer, doutes, état) et la recherche ;
- le kit, élément commun par élément commun, avec le nombre et la liste des éléments qui l'utilisent.

Chaque partie ne s'affiche que si le projet en fournit les données. Un projet sans images ni positions a donc un catalogue plus simple. Les gabarits au choix viendront plus tard (non-but).

### 6.5 Le Directeur

Le panneau du Directeur gagne :
- les cahiers des charges et les méthodes à valider (un lien vers le panneau de la fonctionnalité) ;
- les genres à confirmer ;
- les « méthode à revoir ? » ;
- les sessions cloud à créer, chacune avec le modèle et le rôle attendus, et un champ « Nom de la session créée » suivi du bouton « C'est fait ».

Pour une leçon, le verdict porte aussi **l'étage**. Le Directeur voit l'étage proposé et le texte généralisé, et peut changer l'étage (un menu Projet, Genre ou Skill) avant de valider. La pastille compte tout ce qui attend.

## 7. L'orchestrateur générique

### 7.0 Une conversation orchestratrice par projet

L'utilisateur a retenu **une conversation orchestratrice par projet**, comme aujourd'hui. Chacune suit les mêmes consignes génériques et mène les agents de son projet.
- Les projets restent séparés : chacun a ses fiches, ses leçons, ses sessions cloud attitrées et son dépôt.
- Le seul point commun est la machine. La charge est mesurée pour toute la machine, donc la commande `charge` freine déjà tous les orchestrateurs en même temps, chacun sous la charge maximum de ses réglages.
- Le bureau, lui, montre tous les projets (§6.1).

### 7.1 Ce que la skill fournit et ce que le projet garde

**La skill fournit**, dans `orchestrateur/` **[choix]** :
- `consignes.md` : le rôle d'orchestrateur, le parcours (§4), la boucle de réveil (§7.2), les règles de choix d'agent et de modèle, la mémoire et la relecture croisée. C'est le texte qu'une conversation orchestratrice lit au départ, sur Opus.
- `memoire/` : la mémoire de la skill et celles des genres (§5).
- **Des outils génériques** (Python, bibliothèque standard), pour qu'un projet qui n'a rien puisse démarrer :
  - un suivi des tâches et des fonctionnalités, avec ses commandes en ligne ;
  - la commande du relevé et la commande d'actions branchées sur ce suivi ;
  - le message de départ d'un agent assemblé depuis sa fiche ;
  - les leçons et leurs verdicts.
- Des modèles de fiche d'agent, de brief de rôle et de registre de contrôles.

**Le projet garde**, dans son dépôt :
- **son fichier de factory** **[choix]**, un fichier versionné du projet, désigné dans `.factory/reglages.json` par la clé `orchestrateur`. Il dit :
  - le chemin du dépôt de la skill sur la machine **[choix]** (la skill n'est pas encore emballée, ce sera au projet 4) ;
  - le genre ;
  - les mots interdits (§5) ;
  - le dossier des fiches ;
  - le registre des contrôles ;
  - ses **consignes propres** (un document) ;
  - les commandes qui remplacent les outils génériques (§7.5) ;
  - le flux de la série (les étapes et leur rôle, ce qui donne les colonnes) ;
  - le seuil « méthode à revoir » ;
  - la source du catalogue de chaque fonctionnalité ;
- ses fiches d'agents, ses méthodes, ses briefs, son registre de contrôles et ses données.

**[choix]** **Quand les consignes propres du projet et les consignes génériques se contredisent, celles du projet l'emportent**, et la contradiction est notée pour l'utilisateur. C'est ce qui garantit que le projet pilote ne perd rien.

### 7.2 La boucle de réveil

Elle reprend, en générique, celle que le projet pilote pratique. À chaque réveil (moniteur, sous-agent, message de l'utilisateur), dans cet ordre :
1. Pause ? Mode (en ligne, ou local avec la commande `charge` du bureau avant chaque étape locale) ?
2. Les demandes du bureau d'abord : messages de discussion, validations, retours, déplacements, verdicts.
3. Les outils d'abord : une amélioration des outils de la factory est relue (relecture de code), fusionnée, puis annoncée à chaque agent actif avant toute nouvelle tâche.
4. Les retours des agents : leurs résultats, leurs leçons et leurs améliorations de la factory, qui deviennent des contrôles ou des outils.
5. Faire avancer chaque fonctionnalité selon son étape (§4).
6. Commit et push après chaque étape qui produit quelque chose : un arrêt à tout moment ne perd rien.
7. Toujours dire à l'utilisateur ce qu'on attend (« En attente de : … »).

Les règles propres d'un projet (par exemple : une seule construction à la fois, un nombre de préparations gardées d'avance, une priorité absolue pour un livrable demandé) s'insèrent dans cette boucle par ses consignes propres.

### 7.3 Recréer un agent

- À chaque tâche, l'agent repart d'un contexte neuf.
- Son message de départ est assemblé par une commande, jamais à la main. Il contient : le projet, la fiche entière, les leçons de genre et de skill qui touchent son rôle, le brief du rôle, la tâche et la consigne de fin d'étape (résultat, leçons, retours sur la factory).
- En local, c'est un sous-agent neuf avec le modèle choisi (§4).
- En cloud, c'est un message envoyé à la session attitrée de l'agent, qui commence par « Tu repars de zéro ». La table des sessions attitrées est tenue par le projet.

### 7.4 La discussion passe par l'orchestrateur

- Un message de l'utilisateur est une demande (§8.2). La commande d'actions l'écrit dans le suivi et ajoute une ligne au journal des demandes, que le moniteur de l'orchestrateur suit.
- L'orchestrateur confie la réponse à l'agent de cadrage (le cadrage est sa tâche), puis met la réponse dans le suivi. Le relevé suivant la montre.
- **[choix]** Pour garder la discussion vivante, l'orchestrateur traite une demande de discussion avant les autres retours (juste après la pause), et l'agent de cadrage reste le même pendant toute une fonctionnalité.
- Si l'orchestrateur ne tourne pas, la page affiche « En attente de l'orchestrateur » à côté du message **[choix]**, d'après la fraîcheur de la bulle du chef.

### 7.5 Le projet pilote passe dessus sans rien perdre

**Ce qui ne doit pas changer : tout le fonctionnement actuel**, notamment :
- la pause et les modes en ligne et local, avec la commande de charge ;
- les fiches et leur commande de message de départ ;
- les sessions cloud attitrées ;
- les préparations gardées d'avance et la construction une à la fois ;
- les outils d'abord ;
- les leçons et leurs verdicts, le registre des contrôles ;
- le commit et le push à chaque étape ;
- le livrable demandé qui passe avant tout ;
- son relevé, sa commande d'actions et son catalogue actuel (la page et sa publication).

**Comment** :
- **[choix]** la skill fixe une **interface stricte** pour chaque commande que l'orchestrateur générique appelle : ses arguments, son entrée et sa sortie en JSON, ses codes de retour. Elle est documentée et testée avec les outils génériques ;
- le projet pilote garde **tous ses outils, sans les modifier**, et écrit de **petits adaptateurs** qui respectent cette interface en appelant ses outils. Il les déclare dans son fichier de factory ;
- son document d'orchestration actuel devient **ses consignes propres** ;
- il n'ajoute que ce qui est nouveau :
  - les fonctionnalités dans son relevé ;
  - les nouvelles demandes dans sa commande d'actions ;
  - l'étage des leçons ;
  - un catalogue au format de la skill, produit à partir de ses données, à côté de sa page actuelle qui continue.

**La liste détaillée de compatibilité** (chaque mécanisme, l'outil du projet qui le porte, comment le vérifier) est tenue **dans le dépôt du projet pilote**, pas ici, puisqu'elle nomme ses fichiers. **La vérification finale** du projet 3 : le projet pilote tourne avec l'orchestrateur générique, et chaque ligne de cette liste est cochée.

**[choix]** Comme pour le bureau qui agit, **les dernières phases du plan se font dans le dépôt privé du projet pilote**, par une conversation ouverte sur ce dépôt. Elles commencent par écrire la liste de compatibilité en relisant ses consignes d'orchestration actuelles, puis elles écrivent les adaptateurs, les champs de la version 4, les nouvelles demandes et la production du catalogue au format de la skill. Le plan de ce dépôt s'arrête aux livrables génériques et à un guide de passage. Il annonce ces phases avec leur message de lancement.

**[choix]** La phase qui construit le catalogue du bureau **lit la page de catalogue actuelle du projet pilote sur la machine de l'utilisateur**, en lecture seule, pour en reprendre le design. Elle n'en recopie dans ce dépôt ni les données, ni les noms, ni les images.

## 8. Le contrat : relevé version 4, demandes, catalogue

### 8.1 Le relevé version 4

Ajouts au relevé, ignorés en version inférieure à 4 :

- `genre` : l'identifiant du genre du projet, ou `null` s'il n'est pas encore choisi.
- `livrable` : `{libelle, lien | chemin, date}`, le dernier livrable du projet (facultatif).
- `fonctionnalites` : une liste. Pour chacune :
  - `id`, `nom` ;
  - `etape` : `cadrage`, `cahier`, `decoupage`, `prototype`, `methode`, `serie` ou `terminee` ;
  - `agent_cadrage` (clé d'un titulaire) ;
  - `discussion` : une liste de `{id, t, auteur, texte, images?}`, où `auteur` vaut `utilisateur` ou la clé d'un titulaire ;
  - `attend_reponse` (vrai ou faux) ;
  - `cahier` : `{maquette: [images], etapes: [textes], valide_le?}` ;
  - `methode` : `{version, lien | chemin, validee_le?}` ;
  - `livrable` : `{libelle, lien | chemin, date}` ;
  - `catalogue` (vrai ou faux : le projet en fournit-il un) ;
  - `decisions` : ce qui attend l'utilisateur pour cette fonctionnalité, une liste de `{id, genre, texte}` où `genre` vaut `valider_cahier`, `valider_methode` ou `methode_a_revoir`.
- `decisions_projet` : ce qui attend l'utilisateur pour le projet, une liste de `{id, genre, texte, ...}` où `genre` vaut `confirmer_genre` (avec `propose` et la liste `genres_connus`) ou `session_cloud` (avec `agent`, la clé de la fiche qui attend sa session).
- **[choix]** La pastille d'un projet dans le sélecteur est la somme du nombre `decisions` actuel (qui reste valable), des décisions des fonctionnalités et des décisions du projet.
- Sur une tâche : `fonctionnalite` (identifiant), `element` (identifiant d'élément du catalogue), `modele_depart` et `montee` (`{de, a, raison}`).
- Sur une leçon : `etage_propose` (`projet`, `genre` ou `skill`), `texte_general` (obligatoire si l'étage n'est pas `projet`), `roles`.

Les images suivent les règles actuelles : chemins relatifs aux réglages, racines déclarées, `.png`, `.jpg` et `.jpeg` seulement. Les textes s'affichent comme du texte.

### 8.2 Les nouvelles demandes

| `type` | Champs | Sens |
|---|---|---|
| `fonctionnalite` | `texte`, `images?` | nouvelle fonctionnalité : son premier message |
| `message` | `fonctionnalite`, `texte`, `images?` | un message de l'utilisateur dans la discussion |
| `cahier` | `fonctionnalite`, `verdict` (`valider` ou `corriger`), `texte?` | décision sur le cahier des charges |
| `methode` | `fonctionnalite`, `verdict` (`valider`, `revoir` ou `garder`), `texte?` | `valider` : la méthode du prototype ; `revoir` : demander une nouvelle mise au point, ou dire oui à « méthode à revoir ? » ; `garder` : dire non à « méthode à revoir ? » (l'élément suit le traitement « bloqué ») |
| `genre` | `decision`, `genre` (identifiant existant ou nouveau), `description?` | confirmation du genre du projet |
| `session_cloud` | `decision`, `session` (le nom de la session créée) | l'utilisateur a créé la session cloud demandée ; l'orchestrateur l'inscrit dans la table des sessions attitrées |
| `retour_element` | `fonctionnalite`, `element`, `texte` | « Demander à modifier » dans le catalogue |
| `lecon` (étendue) | `etage?` | l'étage choisi au verdict ; absent = celui proposé |

- **Images jointes** **[choix]** : la page les envoie dans la demande, en base64, avec leur nom et leur type. Au plus 4 images par message, 5 Mo chacune, `.png` ou `.jpg` seulement. **La commande d'actions du projet les range** où le projet veut : le bureau n'écrit rien dans le projet, et un agent cloud doit pouvoir les lire, donc le projet les commite. Le relevé les montre ensuite par leur chemin.
- Chaque demande est vérifiée contre le dernier relevé, comme aujourd'hui : une fonctionnalité, un élément ou une décision inconnus sont refusés sans lancer la commande.
- Dans un bureau à plusieurs projets, chaque demande va à la commande d'actions **du projet choisi**, avec le relevé de ce projet.

### 8.3 Le catalogue

- Un fichier JSON par fonctionnalité, ou une commande, déclaré dans le fichier de factory du projet et donné au bureau par les réglages : `catalogues: {<id de fonctionnalité>: {fichier | commande}}`.
- Le bureau le lit à la demande (pas à chaque relevé) et le sert par `GET /api/catalogue?fonctionnalite=…`. Il peut compter des milliers d'éléments.
- Champs, tous facultatifs sauf l'identifiant et le nom d'un élément :
  - `groupes` : `[{id, nom}]` ;
  - `elements` : chacun avec `id`, `nom`, `groupe`, `etat`, `note`, `caracteristiques: [{libelle, valeur}]`, `captures: [{chemin, passe}]`, `comparaisons: [{angle, reel, produit, credit, lien}]`, `liens: [{libelle, url}]`, `kit: [ids]`, `evenement`, `lecons_appliquees: [ids]`, `a_reevaluer: [ids]`, `doute: {date, raison, leve_par}`, `retours: [{t, texte, etat, reponse}]`, `position: {x, y}`, `passes: [n]` ;
  - `passes` : `[{numero, date, titre}]` ;
  - `lecons` : `[{id, titre, texte, portee, passe}]` ;
  - `kit` : `[{id, nom, description}]` ;
  - `trace` : des polylignes facultatives pour la vue de haut, `[{nom, points}]`.
- Les noms exacts des champs sont laissés au constructeur, à condition de couvrir cette liste et le §6.4.

## 9. Ce qui est laissé au constructeur

- Le découpage du code entre `bureau/` et `orchestrateur/`, et les noms exacts des fichiers et des commandes génériques.
- Le style visuel du panneau de discussion et du catalogue, dans la continuité du bureau actuel et du catalogue du projet pilote.
- Le découpage en phases du plan, et le modèle de chaque phase (le plus petit capable ; la relecture finale sur un modèle fort).
- La démo est **simulée**, comme pour les projets précédents : sa commande d'actions joue le projet. **[choix]** S'y ajoute, à la fin du plan, **un vrai passage de bout en bout** : l'utilisateur lance une conversation orchestratrice sur la démo, avec les outils génériques, et mène une fonctionnalité du bouton jusqu'à la série.
- La démo doit montrer deux projets (sélecteur), une fonctionnalité en cadrage (discussion avec image), une en série avec son catalogue (quelques éléments, comparaison à deux angles, un doute, un « à réévaluer », une carte), et un dernier livrable. Le tout est inventé et sans lien avec un projet réel.

## 10. Comment on saura que c'est réussi

- Le projet pilote tourne avec l'orchestrateur générique et chaque ligne de sa liste de compatibilité est cochée.
- Une nouvelle fonctionnalité de la démo va du bouton jusqu'à « Série » par la discussion, avec la maquette, la liste d'étapes et les deux validations.
- Une leçon validée à l'étage « genre » est lue par un second projet du même genre, et n'est pas lue par un projet d'un autre genre.
- `git grep` sur les mémoires et sur tout le dépôt : aucun nom, lieu, chemin ou fichier d'un projet réel.
- Un relevé version 1, 2 ou 3 et un bureau à un seul fichier de réglages marchent comme avant.
