# L'installation sur un projet — conception

Date : 2026-11-11. Projet 4 de la vision. Suite de `2026-11-10-parcours-d-une-tache-design.md` (l'orchestrateur générique, la mémoire à trois étages, le bureau à plusieurs projets) : à lire avant celle-ci, avec `docs/orchestrateur.md` et `docs/installation.md`.

Convention : ce qui vient de l'utilisateur est écrit sans mention. Ce qui est un choix du rédacteur est marqué **[choix]**.

## 1. Pourquoi

Pour brancher MyIAFactory sur un projet, l'utilisateur a dû tout faire lui-même : configurer l'interface (réglages du bureau), préparer les agents (fiches, briefs) et les workflows (le flux de la série). Le projet 4 **automatise l'intégration de la skill** : depuis le dossier d'un projet, une commande installe la skill, mène une discussion pour comprendre le projet, propose une organisation, puis configure tout pour que le projet soit **prêt à partir sur une première fonctionnalité**.

Le plugin sert autant à **économiser** qu'à **montrer** : une factory qui coûte plus de tokens que la gestion autonome d'un néophyte avec Claude n'a pas de raison d'être.

## 2. Buts, non-buts, contre-buts

**Buts.**
- La skill devient un **plugin Claude Code**, installé une fois par machine depuis le dépôt GitHub public.
- Une **commande d'installation**, lancée depuis le dossier d'un projet, qui mène la discussion, propose l'organisation et configure tout après validation.
- Deux chemins : **projet vide** (série de questions) et **projet existant** (lecture du dossier, puis questions).
- Le **calibrage sur la machine** (combien d'agents en parallèle) et le choix **local ou cloud**.
- La question « **la facturation est-elle un objectif du projet ?** », et sa mise en place ou non.
- Une **estimation du coût** du workflow proposé, avant validation.
- **Les lots par modèle** comme norme de l'orchestrateur : un modèle fait d'une traite tout ce qu'il peut faire d'affilée, en réordonnant les tâches quand leurs dépendances le permettent (section 14).
- Une **organisation qui évolue** : pendant le cadrage d'une fonctionnalité, l'orchestrateur propose de créer un service et de modifier le workflow quand un secteur manque, comme une entreprise qui crée un service.
- Une **mémoire privée par défaut**, sauf ce qui est universel, qui alimente le plugin public.
- Le **support de traitement** de l'entreprise (ordinateur, mobile, ou les deux) : avec le mobile, l'entreprise est accessible sur le téléphone comme sur l'ordinateur, vue 3D comprise (section 13).

**Non-buts.**
- Passer sur l'orchestrateur générique un projet qui a **déjà sa propre factory** (ses consignes, ses outils, son relevé) : c'est le guide `docs/orchestrateur.md` (adaptateurs, liste de compatibilité), fait à la main comme pour le projet pilote. L'installation le détecte et renvoie vers ce guide **[choix]**.
- Créer les sessions cloud : impossible sans un message de l'utilisateur. L'installation les prépare et dit quoi régler.
- Lancer la première fonctionnalité : l'installation s'arrête quand tout est prêt.
- Une IA d'un autre fournisseur ; une application mobile native ; un bureau exposé publiquement sur Internet (tunnel public) ou hébergé en ligne (section 13).

**Contre-buts** (ce qui ferait un échec même si cela « marche »), par ordre d'importance donné par l'utilisateur.
1. **Un workflow ou une gestion trop complexe ou trop coûteuse en tokens** — plus coûteuse que la gestion autonome d'un néophyte. C'est la cause d'échec numéro 1.
2. **Des fonctionnalités à côté de la demande**, qui n'y répondent qu'à moitié ou presque pas. Il faut viser dans le mille en économisant les tokens.
3. Une installation qui écrit dans le projet avant que l'utilisateur ait validé la proposition.
4. Une mémoire liée à une personne ou à un projet précis qui part sur GitHub.
5. Un bureau joignable depuis un autre appareil sans code d'accès, ou depuis Internet en dehors du réseau privé de l'utilisateur.
6. Fable utilisé sans demande expresse de l'utilisateur (règle déjà en vigueur).

## 3. Les règles qui ne bougent pas

- Le dépôt de la skill reste **vide de tout projet** : rien de propre à un projet, rien de privé.
- **Le bureau n'agit jamais lui-même** et n'appelle aucune IA : les gestes deviennent des demandes, traitées par l'orchestrateur.
- **Le plus petit modèle capable** pour chaque agent : Haiku quand il suffit, Sonnet par défaut, Opus seulement quand la tâche l'exige, jamais Fable.
- Les règles de la mémoire à trois étages : une mémoire de genre n'est jamais servie à un projet d'un autre genre ; les mots interdits du projet bloquent toute leçon de genre ou de skill qui en contient un.

## 4. L'installation du plugin

- Le dépôt GitHub public devient un plugin Claude Code. On l'ajoute **une fois par machine** (`/plugin`).
- Il fournit la commande d'installation, par exemple `/myiafactory:installer` **[choix : le nom exact est laissé au constructeur]**.
- Le bureau et la mémoire partagée ont besoin d'un **emplacement stable** sur la machine, qui ne bouge pas quand le plugin se met à jour (le cache des plugins change de chemin d'une version à l'autre, alors que les fichiers de factory des projets notent le chemin de la skill). **[choix]** Un dossier `MyIAFactory` dans le dossier de l'utilisateur, qui contient :
  - une copie de travail du dépôt de la skill (le code du bureau et de l'orchestrateur, la mémoire publique : `skill.md`, les genres) ; c'est le chemin que les fichiers de factory notent dans `skill` ;
  - le **fichier de bureau** qui liste les projets suivis sur la machine ;
  - la **mémoire privée** de la machine (section 10).
  La commande crée ce dossier au premier usage et le met à jour aux suivants (`git pull`), en le disant. Le constructeur peut choisir un autre mécanisme s'il garde ces deux propriétés : chemin stable, mise à jour sans perte.

## 5. Le parcours de la commande

1. **Le point de départ.** L'utilisateur se place dans le dossier d'un projet et lance la commande.
2. **Déjà installé ?** Si le projet a déjà sa configuration MyIAFactory, la commande **vérifie et répare** (un fichier manquant, un chemin qui a bougé, le projet absent du bureau) sans refaire la discussion **[choix]**. Les évolutions de l'organisation viennent des fonctionnalités (section 9), pas de cette commande. **Les projets déjà branchés à la main sur l'orchestrateur générique, à commencer par le projet pilote, sont mis à jour** par ce chemin : chemins vers le dossier stable, règle de versionnement, entrée dans le fichier de bureau commun, réglage des agents en parallèle ; leurs adaptateurs (`commandes`) sont gardés tels quels. Le passage du projet pilote se fait dans son dépôt privé, comme les phases H à J du projet 3. **[choix]** Sur la machine de l'auteur, le dossier stable **est** la copie de développement de la skill (un seul clone, qui pousse les leçons) : pas de seconde copie. Si le projet a une factory à lui qui n'est pas celle de la skill : renvoi vers `docs/orchestrateur.md` (non-but).
3. **Vide ou existant ?** La commande regarde si le dossier est vide (ou presque : pas de code, pas de documentation) ou si le projet existe déjà.
4. **Projet vide** : une série de questions logique pour calibrer l'application et les agents (section 6).
5. **Projet existant** : une lecture du dossier pour comprendre le métier, puis des questions de bonne compréhension et pour combler les zones d'ombre (section 7).
6. **Les questions communes**, dans les deux cas : le support de traitement de l'entreprise (ordinateur, mobile : choix multiple ; section 13) ; agents cloud ou local seulement ; la facturation est-elle un objectif ; pour un projet vide, faut-il créer un dépôt GitHub. Le calibrage de la machine se fait pendant la discussion (section 8).
7. **La proposition** (section 8), corrigée dans la conversation Claude tant que le paramétrage n'est pas finalisé. **Rien n'est écrit dans le projet avant la validation.**
8. **La mise en place** (section 11), puis la vérification.
9. **La fin** : la liste des agents cloud à régler, le message qui ouvre la conversation orchestratrice, l'adresse du bureau. Le projet est prêt pour une première fonctionnalité.

**S'appuyer sur les autres projets.** La skill doit comprendre des projets de tout type, en s'appuyant sur ce qu'elle a appris des autres projets : la mémoire de la skill (le processus) et celle du **genre** du projet quand ce genre est déjà connu. Elle propose le genre (parmi les genres connus, ou un nouveau) dans la discussion ; l'utilisateur le confirme, comme la décision `confirmer_genre` aujourd'hui. Elle ne lit jamais la mémoire d'un autre genre.

**Sobriété de l'installation elle-même** **[choix]**. La discussion se tient sur le modèle de la conversation (Sonnet conseillé). La lecture d'un projet existant est ciblée (arborescence, fichiers de configuration et de dépendances, documentation, un échantillon du code) et peut être confiée à un sous-agent Haiku qui rend un résumé ; on ne lit pas tout le code.

## 6. Projet vide : la série de questions

Une question à la fois, dans un ordre logique, pour tout type de projet. **[choix]** L'ordre proposé (le constructeur peut l'ajuster, et sauter ce qui est déjà répondu) :
1. de quoi parle le projet, en une ou deux phrases ;
2. ce qu'il doit produire (le livrable) et pour qui ;
3. ce qui ferait qu'un résultat est faux ou raté (ces réponses deviennent les premiers contrôles, section 11) ;
4. les outils, langages ou moteurs imposés ou souhaités (sinon la skill propose) ;
5. la première fonctionnalité envisagée, pour dimensionner l'organisation au juste besoin ;
6. les questions communes (section 5, étape 6).

## 7. Projet existant : la lecture et les questions

- La lecture produit **un résumé du métier** : le domaine, ce que le projet produit, ses outils, son état, ses conventions (tests, structure). Elle repère aussi ce que l'environnement d'un agent cloud devrait contenir (langage, version, dépendances, outils).
- Les questions servent à **vérifier la compréhension** (la skill reformule, l'utilisateur corrige) et à **combler les zones d'ombre** (ce que le dossier ne dit pas). On ne devine rien en silence : bien comprendre le métier conditionne tout le reste, et c'est le rempart contre le contre-but 2.

## 8. La proposition

À la fin de la discussion, la skill présente, dans la conversation :
1. **le résumé de sa compréhension du projet** ;
2. **le paramétrage** : nom, genre, mots interdits, modèle de l'orchestrateur, charge maximum et nombre d'agents locaux en parallèle, local seul ou local et cloud, facturation oui ou non, dépôt GitHub (projet vide) ;
3. **l'organisation** : les services du bureau, les agents (rôle, service, modèle, local ou cloud) ;
4. **le workflow de production** : les étapes que l'orchestrateur enchaîne pour chaque élément, dans l'ordre, chacune avec son rôle et son service ; ce sont les colonnes du tableau du bureau (`cadrage` et `fait` s'y ajoutent) ;
5. **l'estimation du coût** d'un élément passé par ce workflow, en tokens et en euros.

L'utilisateur corrige dans la conversation, autant de tours que nécessaire, jusqu'à valider.

**Le workflow le plus court qui tienne** (contre-but 1). Le moins d'étapes et de relectures possible ; chaque étape proposée est justifiée en une phrase dans la proposition. Il garde un point d'ancrage peu coûteux sur la demande (le cadrage validé par l'utilisateur, déjà dans le parcours d'une fonctionnalité) : une question de plus au départ coûte moins que trois tours de corrections (contre-but 2). Le workflow est adapté au métier, en partant de ce que le genre a appris quand il est connu.

**Le calibrage de la machine.** La skill mesure les performances du poste pour évaluer combien d'agents locaux peuvent tourner en parallèle. **[choix]** Elle part de ce que le bureau sait déjà faire (« Me conseiller » : cœurs, mémoire, et l'historique de charge s'il existe) et en tire une charge maximum et un nombre d'agents locaux simultanés, que le bureau montre. **[choix]** Ce nombre est une limite tenue, pas un conseil : `agent-libre` ne rend pas d'agent local au-delà (la tâche attend, comme quand aucun agent n'est libre), les consignes le disent, et l'interface et ses tests sont mis à jour. La commande `charge` reste le second garde-fou. Hors Windows, la mesure de charge n'existe pas : valeur prudente, dite comme telle.

**L'estimation du coût** **[choix]**. Une fourchette honnête, pas un chiffre : tokens par étape d'après les usages déjà mesurés sur la machine (de préférence ceux du même genre), sinon des valeurs par défaut écrites dans la skill, multipliées par le prix des modèles choisis. Elle dit sur quoi elle s'appuie. Une fois les premières tâches faites, l'onglet Facturation donne le réel (si la facturation est activée).

## 9. L'organisation qui évolue

L'application doit être autonome pour proposer des évolutions de l'organisation au vu des fonctionnalités demandées : comme une entreprise, on crée des services.

- **Quand.** Pendant le cadrage d'une fonctionnalité, l'orchestrateur regarde si l'organisation la couvre. S'il manque un secteur, il propose :
  - de créer le service concerné ;
  - de modifier le workflow (ajouter, retirer ou changer une étape) ;
  - de créer les agents nécessaires (rôle, modèle, local ou cloud), avec le coût estimé.
- **Où.** La proposition arrive chez le **Directeur**, au bureau, comme une décision de portée projet. L'utilisateur accepte ou refuse là ; « Challenger » ouvre la discussion s'il veut en parler.
- **Après acceptation.** L'orchestrateur applique le changement par une commande de l'outil (fichier de factory, fiches, briefs), dans le même esprit que la mise en place (section 11). Au bureau, la nouvelle pièce apparaît avec ses agents, et la nouvelle colonne au tableau si le workflow change. Un agent cloud nouveau suit la règle de la section 12.
- **Sobriété.** La proposition est la plus petite qui suffise. Les contre-buts 1 et 2 valent ici aussi.
- **[choix]** Le constructeur définit le nouveau genre de décision (champs : service, étapes changées, fiches, coût estimé), la commande qui applique, et ce que devient une fonctionnalité en cadrage quand la proposition est refusée (elle continue avec l'organisation actuelle, et l'orchestrateur le dit).

## 10. La mémoire : privée sauf l'universel

- **Ce qui est universel**, c'est-à-dire sans aucun nom de projet, de personne, de lieu, de fichier, **alimente directement le plugin public**. **[choix]** Cela couvre les deux étages déjà écrits en termes généraux : la mémoire de la skill (le processus) et les mémoires de genre. Une leçon de ces étages validée par l'utilisateur est écrite dans la copie de travail de la skill (section 4), avec le contrôle des mots interdits, puis commitée et poussée comme aujourd'hui (`lecon appliquer`).
- **Ce qui est lié à une personne ou à un projet précis** est stocké **hors de GitHub**, c'est-à-dire hors du dépôt public de la skill. Le **dépôt GitHub du projet cible** est, lui, l'endroit où l'on merge les fonctionnalités : la configuration du projet y va. **[choix]** Un dépôt créé par l'installation l'est en privé par défaut ; pour un projet existant au dépôt public, l'installation le signale. La mémoire du projet (fiches, contrôles, méthodes) reste dans le dépôt du projet. **[choix]** Le fichier de bureau va dans le dossier stable. Les fichiers que le bureau crée pour un projet (équipe, historiques de charge, d'usage, de prix, d'alertes) restent où le bureau les écrit aujourd'hui, à côté des réglages du projet, et sont ignorés par git (section 11) : aucun changement du code du bureau. L'estimation du coût (section 8) lit les historiques d'usage des projets listés dans le fichier de bureau.
- **[choix]** Si la copie de travail ne peut pas pousser (pas de droits sur le dépôt public), la leçon reste dans la copie locale, et l'outil le dit.

## 11. La mise en place

Après validation, la skill écrit, en suivant les formats existants (`docs/orchestrateur.md`, `docs/installation.md`, `exemples/projet-neuf/`) :
- **le fichier de factory** (nom, chemin de la skill, genre, mots interdits, services, flux, fiches, contrôles, consignes, réglages, modèle de l'orchestrateur, seuil « méthode à revoir », catalogues), et le réglage nouveau du nombre d'agents locaux en parallèle ;
- **les réglages du bureau** (relevé et actions par l'outil générique, racines d'images, de documents et de livrables, alias des modèles, charge maximum ; prix automatiques selon la réponse sur la facturation) ;
- **une fiche par agent** et **un brief par rôle** ;
- **les consignes propres du projet** (ce qui est propre à ce projet : ses outils, ses règles) ;
- **le registre des contrôles**, amorcé avec ce que l'utilisateur a dit pendant la discussion : ce que le projet doit faire, ce qui serait faux. Les relectures vérifient ainsi la demande, pas seulement la qualité ;
- pour un projet vide, `git init`, et le dépôt GitHub si l'utilisateur l'a demandé.

**La facturation.** Si elle est un objectif : un service `facturation` (la pièce où l'onglet Facturation est toujours visible) et les prix automatiques. Sinon : pas de pièce Facturation **[choix : le bureau garde la commande `usage` et les tokens, sans pièce dédiée ; le constructeur décide s'il coupe aussi les lectures de prix]**.

**Le bureau.** S'il existe déjà un bureau qui suit d'autres projets sur la machine, le projet le **rejoint** (ajout au fichier de bureau). Sinon, l'installation crée le fichier de bureau. **[choix]** Le bureau lit son fichier au lancement : l'installation dit s'il faut le relancer, et donne la commande.

**Ce qui est versionné** **[choix]**. Les guides se contredisent aujourd'hui (`docs/installation.md` met `.factory/` hors de git, `docs/orchestrateur.md` veut le fichier de factory versionné). Règle retenue : la configuration du projet (fichier de factory, fiches, briefs, consignes propres, contrôles, réglages) est **versionnée dans le dépôt du projet** ; les fichiers que le bureau crée et qui sont propres à la machine (équipe, historiques de charge, d'usage, de prix, d'alertes) sont **ignorés par git**. Les chemins propres à la machine (celui de la skill dans le fichier de factory, celui de `outil.py` dans les réglages et la commande du catalogue) ne sont pas écrits en absolu dans des fichiers versionnés : **[choix]** ils s'écrivent par rapport au dossier stable (par exemple `~/MyIAFactory/...`), et `factory.py` comme le lanceur de commandes du bureau savent développer ce préfixe. Un clone du projet sur une autre machine marche donc dès que la skill y est installée. Les deux guides sont mis d'accord.

**La vérification.** `verifier_interface.py` (sans `--complet`) passe sans écart, et le bureau répond sur ce projet. Une installation qui ne passe pas le dit en clair et ne prétend pas être prête.

## 12. Les agents cloud

- Seulement si l'utilisateur veut des agents cloud.
- Chaque agent cloud est initialisé avec un **environnement de base**, sauf si la skill a détecté que l'environnement doit contenir des éléments spécifiques (langage, version, dépendances, outils).
- La skill écrit, **dans un message**, pour chaque agent cloud : sa clé, son rôle, **le modèle sur lequel régler sa session**, et l'environnement à utiliser. **C'est l'utilisateur qui règle le modèle** et crée la session. Les fiches cloud sont écrites ; la décision `session_cloud` existante prend le relais tant qu'une session manque.

## 13. L'accès mobile

L'installation demande **sur quels supports l'entreprise est traitée : ordinateur, mobile** (choix multiple). Si le mobile est retenu, l'entreprise doit être accessible sur le téléphone **tout comme sur l'ordinateur**. L'utilisateur a choisi, parmi quatre solutions (réseau privé, Wi-Fi de la maison, tunnel public, bureau hébergé), les deux premières, et de **garder la vue 3D** pour gérer l'entreprise, adaptée au mobile.

**Comment le téléphone atteint le bureau.**
- **A. Le réseau privé Tailscale (par défaut).** Gratuit ; une application sur l'ordinateur et sur le téléphone, installées par l'utilisateur (la skill dit comment, elle n'installe rien elle-même). Le bureau écoute en plus sur l'adresse Tailscale de la machine : il est joignable de partout (4G, ailleurs), chiffré, et rien n'est exposé sur Internet.
- **B. Le Wi-Fi de la maison (secours).** Rien à installer : le bureau écoute en plus sur l'adresse de la machine dans le réseau local. Le trafic n'y est pas chiffré : la skill le dit au moment du choix.
- L'ordinateur garde `127.0.0.1` comme aujourd'hui. Les deux accès s'ajoutent, ils ne le remplacent pas.

**Le code d'accès.** Toute requête qui ne vient pas de la machine elle-même exige un code d'accès, gestes compris. **[choix]** Le téléphone est associé une fois : la page du bureau sur l'ordinateur montre un **QR code** (le terminal qui l'a lancé affiche les adresses ouvertes) qui porte l'adresse et le code ; le téléphone le scanne, le bureau lui pose un cookie (`HttpOnly`, `SameSite=Strict`) et il n'a plus rien à saisir. Le code vit dans le dossier stable, hors de tout dépôt ; un geste « Révoquer les téléphones » en crée un nouveau. Sans code ou avec un code faux : 401, aucune donnée. Le contrôle de l'en-tête `Host` accepte les adresses ouvertes, et elles seules.

**Ce que le téléphone affiche.** La même page, la **vue 3D gardée** et adaptée au mobile **[choix pour le détail]** : toucher pour sélectionner, pincer pour zoomer, glisser pour se déplacer ; les panneaux (dossier d'un service, Directeur, fonctionnalité, catalogue) en plein écran ; une barre compacte ; le Kanban plein écran d'un geste ; dans la discussion, joindre une photo prise au téléphone ; rendu allégé (définition et ombres réduites) pour rester fluide. **Tous les gestes de l'ordinateur sont possibles sur le téléphone**, par les mêmes demandes : le bureau n'agit toujours pas lui-même. **[choix]** La page peut être ajoutée à l'écran d'accueil du téléphone (manifeste web).

**La mise en place.** Les réglages d'accès sont ceux de la machine : ils vont dans le fichier de bureau commun (par exemple `acces: {"tailscale": bool, "reseau_local": bool}`), pas dans le projet. La skill vérifie l'adresse Tailscale quand elle est choisie (`tailscale ip -4`), et à la fin donne la marche à suivre : relancer le bureau, ouvrir la page sur l'ordinateur, scanner le QR code. Sans mobile, rien ne change : le bureau n'écoute que sur `127.0.0.1`.

## 14. Les lots par modèle

La méthode de développement de l'utilisateur devient **la norme de la skill** : l'orchestrateur générique l'applique dans tous les projets installés.

- **À chaque sollicitation**, l'orchestrateur évalue le meilleur modèle pour chaque tâche (le plus petit capable, règle déjà en vigueur) et **regroupe les tâches en lots par modèle**.
- **Un modèle fait d'une traite tout ce qu'il peut faire d'affilée** : un lot est confié à **une seule conversation**, qui enchaîne ses tâches sans repartir de zéro entre elles. But : le moins possible de conversations différentes pour un même modèle, parce que le coût d'un agent vient surtout de ce qu'il relit à chaque départ.
- **On réordonne quand c'est possible.** Exemple de l'utilisateur : des tâches Sonnet en a, b et d, une tâche Opus en c. Si d peut passer avant c, on fait a, b, d puis c (une seule itération Sonnet) ; sinon on garde l'ordre.
- **L'orchestrateur gère le lien entre les modèles** : chaque lot reçoit ce que les lots précédents ont produit, comme la passation entre conversations le fait pour le développement de la skill.
- **[choix]** Les dépendances sont notées au découpage : chaque tâche peut porter `depend_de` (les tâches qu'elle attend). Sans cette mention, l'ordre d'origine est gardé entre les tâches concernées : on ne réordonne jamais sur une supposition.
- **[choix]** Un lot réunit des tâches de même modèle et de même lieu (local ou cloud) ; il peut mêler des rôles, et son message de départ porte alors le brief de chacun. **La relecture croisée ne se met jamais en lot** : chaque relecteur reste un agent à contexte neuf, distinct de celui qui a produit, et distinct de l'autre relecteur.
- **[choix]** Un lot compte 5 tâches au plus : au-delà, la conversation grossit et chaque tâche coûte plus cher qu'un départ neuf.
- Le bureau montre chaque tâche comme aujourd'hui ; une tâche faite dans un lot le dit (le lot et sa place dans le lot), pour que la facturation reste lisible.
- **Plusieurs fonctionnalités en parallèle.** Les lots ne s'arrêtent pas à une fonctionnalité : ils réunissent les tâches prêtes de toutes les fonctionnalités en cours du projet. **Quand une nouvelle fonctionnalité est demandée** (ou qu'une sollicitation ajoute des tâches), l'orchestrateur **réadapte le plan d'utilisation des agents** : il refait les lots de toutes les tâches pas encore parties, pour limiter les appels d'agents, en respectant toujours les dépendances. Un lot déjà parti n'est pas touché. Un lot ne mêle jamais deux projets (chaque projet a son orchestrateur).
- **La facturation reste exacte projet par projet et tâche par tâche**, même quand un agent traite plusieurs tâches dans un même échange : le coût d'un lot est réparti entre ses tâches, et la somme des parts vaut exactement le coût du lot. **[choix]** Quand les compteurs de tokens sont relevés à la fin de chaque tâche (une session cloud dont on note les cumuls), chaque tâche reçoit l'écart exact ; sinon (un sous-agent ne donne qu'un total à la fin), le total est réparti au prorata du temps passé sur chaque tâche (à parts égales si les temps manquent), et le bureau marque ces parts « estimées ». Les totaux par projet, par service et par période ne changent pas.

## 15. Ce qui est laissé au constructeur

- Le nom exact de la commande, la structure du plugin et le mécanisme du dossier stable, dans les limites de la section 4.
- Le format du nouveau réglage « agents locaux en parallèle » et la formule du calibrage.
- Les valeurs par défaut de l'estimation du coût et leur emplacement.
- Le genre de décision et la commande de l'organisation qui évolue (section 9).
- Comment l'installation est découpée en outils (Python, comme le reste de la skill) et en consignes de la commande (le texte que suit Claude pendant la discussion). **[choix]** Tout ce qui écrit des fichiers passe par un outil testé ; la discussion, elle, est guidée par des consignes.
- La mise à jour de `docs/installation.md` (« l'installation en tant que skill Claude arrivera avec le projet 4 ») et du `README.md`.
- Le découpage en phases par modèle et la passation, comme pour les projets précédents.
