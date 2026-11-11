# Le bureau partenaire — conception

Date : 2026-11-11. Fait partie du projet 4 (l'installation sur un projet), avant ses essais réels. À lire avec `2026-11-11-installation-sur-un-projet-design.md`, `docs/orchestrateur.md` et la recherche `docs/recherche/partenaires-2026-11.md`.

Convention : ce qui vient de l'utilisateur est écrit sans mention. Ce qui est un choix du rédacteur est marqué **[choix]**.

## 1. Pourquoi

Une factory produit aussi du contenu que Claude ne génère pas lui-même : des voix, des images, des vidéos, des modèles 3D, des traductions, des sons… Des services partenaires le font, par API, par serveur MCP ou par leur studio. L'utilisateur veut un **bureau partenaire** : voir tous les partenaires possibles, ceux qui sont connectés, ce qu'il leur reste, et ceux qui sont conseillés pour le projet. Le projet est **global** : il faut prévoir le plus de connecteurs possible.

## 2. Buts, non-buts, contre-buts

**Buts.**
- Un espace partenaire au bureau : la liste de tous les partenaires possibles, triés par catégorie ; pour chacun, ses plans (gratuit, payants avec le prix), connecté ou non, l'abonnement en cours s'il est connecté, et ce qu'il reste (tokens, générations, crédits) quand c'est connu, « illimité » quand il n'y a pas de limite.
- Deux liens par partenaire : **s'inscrire** et **se connecter** (lancer la connexion MCP, ou tout autre type de connexion).
- Une section **« connecteurs conseillés »**, propre à chaque projet.
- À l'installation, une étape au début : projet existant → reprendre les partenaires déjà définis, avec leurs informations ; projet vide → proposer un ensemble de partenaires utiles au projet.
- À l'usage : appeler le meilleur partenaire connecté pour le besoin, puis le suivant quand une limite est atteinte ; sinon, une autre solution (mode manuel, mode navigateur).
- Les coûts des partenaires dans la Facturation, par projet et par tâche, surtout pour les appels par API.
- Un bouton pour **mettre à jour les offres**.

**Non-buts.**
- **Gérer la connexion** : elle n'est pas liée à la skill. La skill vérifie s'il existe une connexion et propose de connecter, c'est tout.
- Créer des comptes, saisir des identifiants, acheter un plan : c'est l'utilisateur qui le fait, sur les pages du partenaire.
- Rendre un partenaire obligatoire.

**Contre-buts** (ce qui ferait un échec même si cela « marche »).
1. Un travail bloqué faute de partenaire : utiliser un MCP ou une autre IA est **totalement facultatif**, la factory doit pouvoir se débrouiller sans.
2. Une dépense, un changement de partenaire ou une action dans le navigateur sans l'accord de l'utilisateur.
3. Une clé secrète lue pour autre chose qu'un appel, écrite dans un fichier, affichée ou envoyée ailleurs que chez son partenaire.
4. Un prix ou un quota ancien montré comme s'il était actuel.

## 3. Les règles qui ne bougent pas

- Le bureau n'agit jamais lui-même et n'appelle aucune IA : un geste devient une demande, traitée par l'orchestrateur.
- Le dépôt de la skill reste vide de tout projet et de tout privé.
- Les lots par modèle, la facturation exacte par projet et par tâche, le plus petit modèle capable.

## 4. Les trois sources

1. **Le catalogue** (ce qui existe) : générique, universel, dans le dépôt de la skill **[choix]** (`partenaires/catalogue.json`). Pour chaque partenaire : identifiant, nom, catégorie et sous-catégorie, site, lien d'inscription, lien et type de connexion (MCP avec son adresse et la commande prête à copier, par exemple `claude mcp add --transport http <nom> <adresse>` ; clé API avec sa page et le nom habituel de sa variable d'environnement ; studio ; connexion par compte), plans (nom, prix, devise, période, quota inclus), plan gratuit, lecture du quota (oui avec la méthode, non, inconnu), illimité ou non, statut (actif, fermé, sans API), **fiabilité** (lu sur la page officielle ou source tierce) et **date de vérification**. Il est amorcé avec la recherche du 11 novembre 2026. Les partenaires fermés ou sans API y restent marqués, pour ne pas être reproposés.
2. **Les connexions** (ce qui est branché) : propres à la machine et aux comptes de l'utilisateur, **communes à tous les projets du bureau**, hors de tout dépôt **[choix]** (`~/MyIAFactory/partenaires.json`). Elles disent, pour chaque partenaire : connecté ou non, comment on l'a su, l'abonnement s'il est connu, le dernier quota lu et sa date.
3. **Les conseils** (ce qui est utile au projet) : propres au projet, versionnés dans son dépôt **[choix]** (`.factory/partenaires.json`) : par besoin (voix, images…), une liste ordonnée de partenaires conseillés, chacun avec sa raison en une phrase.

## 5. Savoir ce qui est connecté

**[choix]** Deux niveaux. **Déclaré** : une commande de l'outil lit les configurations, sans jamais toucher aux valeurs (ni en-têtes, ni variables, ni jetons d'un serveur MCP). **Utilisable** : l'orchestrateur confirme, dans sa propre conversation, que les outils du partenaire lui sont vraiment disponibles (un serveur MCP déclaré mais pas encore connecté à son compte, ou un connecteur de compte claude.ai que les fichiers ne montrent pas, se voient ainsi) ; le bureau affiche « connecté », « déclaré, à vérifier » ou « non connecté ». Sources lues, sans jamais lire la valeur d'une clé :
- les **serveurs MCP** déclarés dans Claude Code (configuration de l'utilisateur et `.mcp.json` du projet) : on lit leurs noms et leurs adresses ;
- la **présence** des variables d'environnement habituelles d'un partenaire (par exemple `ELEVENLABS_API_KEY`), dans l'environnement de la machine ou dans le `.env` du projet, sans lire leur valeur ;
- les **déclarations de l'utilisateur** pour ce qui ne se détecte pas (un compte de studio, comme Tripo utilisé à la main), faites dans la conversation ou au bureau.

## 6. Qui appelle un partenaire

**[choix]** La skill **ne livre pas un adaptateur de génération par partenaire** : ce serait des dizaines d'intégrations à maintenir. **Les agents appellent eux-mêmes le partenaire**, par ses outils MCP quand il en a, sinon par son API documentée (ou son studio, en mode manuel). L'outil de la skill fournit le reste : le catalogue, la détection, **le choix du partenaire** pour un besoin (une commande qui rend la liste ordonnée des partenaires connectés et utilisables, d'après les conseils du projet et les quotas connus), la lecture des quotas, et **la note de l'usage** (une commande que l'agent appelle après chaque appel payant : partenaire, quantité, unité, coût s'il le connaît). Une limite atteinte (quota épuisé, refus pour dépassement ou paiement requis) est signalée par l'agent avec la même commande ; le partenaire passe alors « limite atteinte » jusqu'au prochain relevé, et le choix suivant le saute.

## 7. Les règles de chaque partenaire

On peut fixer des **règles d'usage pour chaque partenaire** (chaque MCP ou autre connexion), que les agents suivent quand ils l'appellent. Exemple donné par l'utilisateur pour Tripo : « si plusieurs éléments sont nécessaires, on essaie au maximum de les générer en un seul prompt, sauf besoin de détail très précis ou d'animation ». Ce n'est qu'un exemple : **l'utilisateur définit lui-même les règles de chaque partenaire**.

- Dans l'espace partenaire, chaque carte montre ses règles ; on peut **les consulter, en ajouter, les modifier, les supprimer**.
- **[choix]** Les règles appartiennent à l'utilisateur et valent pour tous les projets, comme les connexions : elles vivent hors de tout dépôt, dans `~/MyIAFactory/partenaires.json`. Le bureau ne les écrit pas lui-même : chaque ajout, modification ou suppression est une demande que l'orchestrateur applique (règle du bureau qui n'agit pas). Elles peuvent aussi être dites dans une conversation, et l'orchestrateur les écrit.
- **[choix]** Le message de départ d'un agent dont la tâche appelle un partenaire contient les règles de ce partenaire, mot pour mot ; une règle qui contredit une consigne de tâche explicite de l'utilisateur cède devant elle, et l'agent le dit.
- **[choix]** À l'amorce, aucune règle n'est imposée ; l'exemple Tripo est proposé comme règle de départ, que l'utilisateur garde ou retire.

## 8. Lire ce qu'il reste

- C'est **l'orchestrateur** qui lit les quotas, par une commande de l'outil, jamais la page **[choix]**. Le bureau affiche le dernier relevé avec sa date.
- Seuls les partenaires qui le permettent par leur API sont lus (à l'amorce : ElevenLabs, Black Forest Labs, Stability, Leonardo, Meshy, remove.bg, DeepL, KIRI Engine ; les banques de médias par leurs en-têtes de limite). La clé est prise dans la variable d'environnement, ou **dans le `.env` du projet, au moment de l'appel seulement** (validé par l'utilisateur) : elle n'est jamais écrite, affichée, ni transmise à un autre service que celui du partenaire. Il en va de même pour un agent qui appelle un partenaire par son API.
- Affichage : « reste N (unité) », « illimité », ou « quota inconnu » ; toujours la date du relevé. **[choix]** Relevé au plus une fois par heure, ou sur le bouton « Actualiser » de l'espace partenaire (une demande).

## 9. L'espace partenaire au bureau

- **[choix]** Une pièce **« Partenaires »** dans le bâtiment 3D ; un clic ouvre son panneau, comme les autres services (et en plein écran sur le téléphone).
- Trois parties : **Connectés** ; **Conseillés pour ce projet** (dans l'ordre des conseils, avec leur raison) ; **Tous les partenaires**, par catégorie.
- Chaque carte : nom, catégorie, plans et prix, connecté ou non, abonnement, ce qu'il reste, la fiabilité et la date des informations, ses règles d'usage (section 7), et les deux liens « S'inscrire » et « Se connecter » (qui ouvrent les pages du partenaire ; pour un MCP, la commande à copier).
- Le bouton **« Mettre à jour les offres »** : une demande à l'orchestrateur, qui lance une recherche sur les sites des partenaires et réécrit le catalogue (prix, plans, statut, date). **[choix]** Le bouton annonce d'abord le coût estimé de la recherche et demande confirmation ; la recherche se fait en lots, sur un petit modèle (Sonnet), et ne touche que les fiches à refaire ; le catalogue mis à jour est universel et alimente le plugin public, comme une leçon de skill (contrôle des mots interdits, commit, push).

## 10. À l'installation

Une étape au début de la discussion d'installation :
- **projet existant** : reprendre les partenaires déjà définis dans le projet, avec leurs informations **[choix : serveurs de `.mcp.json`, paquets des partenaires dans les dépendances (par exemple le SDK `elevenlabs`), noms de variables dans `.env.example` — le `.env` seulement pour savoir quelles variables sont présentes, jamais pour en lire ou en recopier les valeurs]** ;
- **projet vide** : proposer un ensemble de partenaires utiles au projet, d'après les réponses de la discussion ;
- dans les deux cas : dire lesquels sont déjà connectés sur la machine, proposer de connecter les autres (liens), écrire les conseils du projet. Rien n'est obligatoire.

## 11. À l'usage

- Quand une tâche a besoin d'un contenu qu'un partenaire produit, l'orchestrateur prend **le meilleur partenaire connecté pour ce besoin** (l'ordre des conseils du projet), puis **le suivant** quand une limite est atteinte (quota épuisé, refus pour dépassement).
- Si un meilleur partenaire existe mais n'est pas connecté, il **ne bloque pas** : il dit simplement qu'on aurait pu utiliser tel partenaire, et qu'il prend tel autre à la place.
- Si **aucun** n'est utilisable :
  - **mode manuel** : il écrit le prompt et le **mode d'emploi exact** pour le réaliser (chaque réglage, comme pour Tripo jusqu'ici) ; l'utilisateur le fait et lui rend le résultat ;
  - **mode navigateur** : il propose la génération par le navigateur Claude ; **si l'utilisateur valide**, l'utilisateur s'y connecte lui-même, puis l'orchestrateur mène la suite ;
  - ou une autre solution sans partenaire.
- **L'accord de l'utilisateur**, selon ce qui est dépensé (validé par l'utilisateur) :
  - **plan gratuit, ou crédits d'un abonnement déjà payé** : pas d'accord à demander ; l'orchestrateur prévient seulement (quel partenaire, combien) ;
  - **appel facturé à l'usage, ou crédits achetés** : l'accord de l'utilisateur, **valable pour la tâche en cours** (une décision au Directeur ou la conversation) ;
  - **passer à un autre partenaire, ou agir dans le navigateur** : toujours l'accord de l'utilisateur.
  - **[choix]** Le catalogue marque donc chaque plan « gratuit », « inclus dans un abonnement » ou « facturé à l'usage » ; un plan inconnu est traité comme facturé (on demande).
- Les **nouvelles fonctionnalités** peuvent faire évoluer les conseils du projet (même logique que l'organisation qui évolue : une proposition, jamais une obligation).

## 12. La facturation

- Chaque appel payant à un partenaire est noté avec le projet, la tâche, le partenaire, la quantité et son unité, et le coût (exact quand l'API le donne ou que le tarif est connu ; sinon estimé, marqué comme tel).
- L'onglet Facturation montre ces coûts à côté des tokens, par projet, par tâche, par partenaire. Un coût en dollars est converti en euros comme les tokens aujourd'hui : par le taux du jour de la Banque centrale européenne que le bureau lit déjà, daté et gardé avec l'usage (le coût d'origine reste noté). Un usage par le studio ou le navigateur est noté quand l'utilisateur le donne, sinon estimé.

## 13. Ce qui est laissé au constructeur

- Le format exact des trois fichiers et le schéma du catalogue.
- La liste des lecteurs de quota à l'amorce et la forme d'un lecteur.
- La place de la pièce dans le plan du bâtiment.
- Le découpage en tâches et en lots, à la suite du plan du projet 4, avant les essais réels.
