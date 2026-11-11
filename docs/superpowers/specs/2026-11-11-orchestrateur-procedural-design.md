# L'orchestrateur procédural — conception

Date : 2026-11-11. Suite de `2026-11-10-parcours-d-une-tache-design.md` (l'orchestrateur générique) et de `2026-11-11-installation-sur-un-projet-design.md` (les lots par modèle, la facturation exacte) : à lire avant celle-ci, avec `orchestrateur/consignes.md` et `orchestrateur/interface.md`.

Convention : ce qui vient de l'utilisateur est écrit sans mention. Ce qui est un choix du rédacteur est marqué **[choix]**.

## 1. Pourquoi

L'orchestrateur est aujourd'hui **une conversation Claude** qui reste ouverte, réveillée par un moniteur, et qui tape elle-même les commandes de `outil.py`. Chaque réveil relit toute la conversation. Sur un essai réel (un lot de 5 éléments graphiques, une fonctionnalité de bout en bout, cadrage, cahier corrigé trois fois, prototype, méthode, série, une correction), l'orchestrateur a coûté **environ 1,76 €** pour **1,56 €** de production : 97 appels, un contexte passé de 72 000 à 186 000 tokens, 13,5 millions de tokens relus.

L'analyse de ces 97 appels (rangés par ce qu'ils faisaient) :

| Ce que faisait l'orchestrateur | Appels | Part des tokens |
|---|---|---|
| Accuser réception, raconter dans le chat | 29 | 30 % |
| Recopier le retour d'un agent dans la discussion, noter l'usage | 21 | 21 % |
| Enregistrer une demande, une tâche, la charge, une leçon | 17 | 18 % |
| Entretien (moniteur expiré, consignes changées pendant qu'il tournait) | 9 | 12 % |
| Écrire le brief d'un agent | 9 | 8 % |
| Démarrage (consignes, état) | 5 | 3 % |
| **Jugement réel** (découper le cahier, écrire la méthode, regrouper le lot, décider après un contrôle refusé) | **7** | **8 %** |

Environ 84 % du coût est du déterministe ou du bavardage, et le jugement lui-même n'a besoin que d'un petit dossier, pas de l'historique. C'est exactement le contre-but numéro 1 du projet : **une gestion plus coûteuse que la gestion autonome d'un néophyte**.

**L'intention.** Garder un projet **structuré, guidé et aidé** (le bureau, les étapes, les contrôles, les méthodes, la mémoire) **au coût le plus faible possible**.

## 2. Buts, non-buts, contre-buts

**Buts.**
- Un **moteur Python** remplace la conversation orchestratrice : il traite seul, sans IA, tout le déterministe (demandes, suivi, file, lots, usage, présence, recopie des rapports, commit et push).
- Il n'appelle l'IA que pour le **jugement**, en **appels courts à contexte neuf** (`claude -p`), chacun avec un petit dossier préparé et une réponse structurée.
- Il **lance lui-même les agents de production** (`claude -p`), sans fenêtre ; l'utilisateur suit tout au bureau.
- Un **banc d'essai** qui émule la discussion de l'essai de référence et compare trois façons de faire : le moteur, l'orchestrateur actuel, un agent seul, contre un **objectif chiffré** (section 9).
- La **facturation reste exacte** par projet et par tâche, appels du moteur compris.

**Non-buts.**
- Changer le bureau, le relevé, la page, le parcours d'une fonctionnalité (cadrage → cahier → découpage → prototype → méthode → série → terminée), la mémoire à trois étages ou les règles des partenaires : le moteur les **applique** tels qu'ils sont.
- Les agents cloud par **Managed Agents** (l'API hébergée, sur clé API) : écartés pour l'instant ; les agents cloud passent par les sessions cloud de Claude Code, sur l'abonnement (section 6 bis).
- Passer le **projet pilote** (sa propre factory, son adaptateur) sur le moteur : ce sera un travail à part, après le banc.
- Une IA d'un autre fournisseur.

**Contre-buts.**
1. **Un orchestrateur qui coûte plus que le gain** : un appel d'IA là où une règle suffit, un dossier d'appel qui grossit avec l'historique, un appel « pour raconter ».
2. **Des fonctionnalités à côté de la demande** : économiser au point de mal comprendre (cadrage bâclé, retour de l'utilisateur mal traduit) serait un échec. Le jugement garde le bon modèle (section 5).
3. **Un moteur qui bloque en silence** : un cas imprévu doit toujours aboutir à une action ou à une question visible au bureau.
4. **Perdre un garde-fou existant** : Fable jamais choisi, aucune clé de partenaire écrite, accord avant dépense, mots interdits, rien d'écrit dans la skill hors `lecon appliquer` et `genre fixer`.
5. **Rien de propre à l'essai de référence dans le dépôt public** (ni son nom, ni ses rapports, ni ses images).

## 3. Ce qui change pour l'utilisateur

- **Plus de conversation orchestratrice à ouvrir.** Le moteur tourne en tâche de fond, **un seul pour tous les projets du bureau** **[choix]**, comme le bureau. Le bouton « Lancer l'orchestrateur » démarre le moteur (sans fenêtre) au lieu d'ouvrir une console `claude`.
- **Les agents travaillent sans fenêtre** ; leur travail se suit au bureau (tâches, discussion, documents, facturation), comme aujourd'hui.
- **Plus de narration dans un chat** : le bureau est la seule interface. Tout ce que l'orchestrateur disait d'utile (« En attente de : … », une contradiction de consignes, un arrêt) devient une ligne au bureau (`reponse` d'une demande, journal d'une tâche, message de la discussion ou décision).
- Le reste ne bouge pas : mêmes gestes, mêmes décisions du Directeur, mêmes questions à choix.

## 4. Le moteur

### 4.1 La boucle

Un processus Python (bibliothèque standard seulement, `py -3.12`, comme le reste) :

1. **Présence** : il écrit `presence.json` de chaque projet qu'il tient (la même que `lancer guetter`) ; le bureau voit « orchestrateur présent » sans changement.
2. **Demandes** : il relit `demandes.jsonl` de chaque projet (même lecture que le guetteur, toutes les 2 s) et traite les demandes en attente dans l'ordre des consignes (messages de discussion d'abord).
3. **Retours d'agents** : à la fin d'un `claude -p` d'agent, il lit son rapport (section 6) et l'applique.
4. **Avancer** : pour chaque fonctionnalité, il fait ce que dit le parcours à son étape (section 4.2), dans les limites de la pause, de la charge (`charge` → `feu_vert`) et des agents libres.
5. **Commit et push** du dépôt du projet après chaque étape qui produit quelque chose.

Il **passe toujours par `lancer <commande>`** (la fonction `executer` de `outil.py`), jamais par les fonctions internes : un projet qui a déclaré un adaptateur garde son adaptateur.

### 4.2 La table de règles

Le cœur du moteur est une **table** : (type de demande ou événement, étape de la fonctionnalité) → suite d'actions. Les actions sont soit des commandes `lancer`, soit un **appel de jugement** (section 5), soit le **départ d'un agent** (section 6). Elle traduit `consignes.md` ligne à ligne. Exemples :

| Événement | Ce que fait le moteur | IA ? |
|---|---|---|
| `fonctionnalite` (nouvelle) | `agent-libre` (rôle de cadrage), `fonctionnalite` (agent de cadrage), tâche de cadrage, **départ de l'agent de cadrage** (première analyse) | l'agent de cadrage seulement ; le **nom court** de la fonctionnalité vient de lui |
| `message` en cadrage ou cahier | départ de l'agent de cadrage avec la discussion | l'agent |
| `cahier` `valider` | cahier `valide_le`, lever `valider_cahier`, étape `decoupage`, **jugement « découper »** | oui (découpage) |
| `cahier` `corriger` | lever la décision, étape `cadrage`, départ de l'agent de cadrage avec le texte | l'agent |
| `message` en prototype | **jugement « traduire le retour »** puis départ de l'agent du prototype avec la consigne | oui |
| `methode` `valider` | **jugement « écrire la méthode »**, briefs, contrôles, `fonctionnalite methode`, étape `serie` | oui |
| `methode` `reprendre` / `garder` / `revoir` | commandes seulement | non |
| `lecon` | `lecon appliquer` | non |
| `genre`, `organisation`, `session_cloud`, `deplacer`, `bouton` pause/reprendre, `partenaires_*` | commandes seulement (comme les consignes) | non |
| `retour`, `retour_element` | tâche de correction ; le texte part tel quel dans le départ de l'agent | non (l'agent lit le texte) **[choix]** |
| rapport d'un contrôle **refusé** | **jugement « après un refus »** : corriger, revoir la méthode ou bloquer | oui |
| file non vide en série, agent libre, feu vert | `lots`, `depart` du lot, départ | l'agent |
| `challenge` sur une leçon | départ de l'agent de la leçon avec la leçon et le texte | l'agent |
| **tout ce que la table ne couvre pas** | **appel de conseil** (section 5.3) | oui |

Les **consignes propres du projet** (un bouton du projet, une règle de parallélisme, un challenge de service) n'ont pas de ligne générique : leurs événements passent par l'appel de conseil, qui reçoit les consignes propres dans son dossier.

### 4.3 Ce qui sort de l'IA et devient du code

Tout ce que l'orchestrateur faisait à la main et qui ne demande pas de jugement : `reveil`, `etat`, `demande-traitee` (la `reponse` est un texte gabarit, ou celui que rend l'appel d'IA), la tâche marquée au départ et rendue à la fin, `usage` (exact, section 7), la recopie du message de l'agent dans la discussion (`message` avec `auteur`, `images`, `questions`, `glossaire`, `attend`, tels que l'agent les rend), `document` pour les fichiers rendus, `controle` pour les contrôles rendus, `lecon noter` pour les leçons rendues, `catalogue`, `livrable`, `terminee`, la relecture croisée (qui lance quoi, combien de tours, le seuil `methode_a_revoir`, « le même contrôle échoue sur deux éléments »), les lots et leur répartition de coût, le commit et push.

## 5. Les appels de jugement

### 5.1 Forme

Un appel = **un `claude -p` neuf**, sans outils sauf besoin déclaré **[choix]**, avec :
- **un dossier** préparé par le moteur, borné : la demande, la discussion de la fonctionnalité (ou son seul dernier tour quand cela suffit), le cahier, la fiche de l'agent concerné, les consignes propres, le dernier rapport. **Jamais l'historique du moteur.**
- **une consigne courte** propre au type d'appel (un fichier par type, dans la skill), qui dit quoi décider et la forme exacte de la réponse ;
- **une réponse JSON** que le moteur **valide** (champs, valeurs permises) avant d'agir. Une réponse invalide est redemandée une fois, avec l'erreur ; un second échec devient une **question au Directeur** au bureau (contre-but 3).

**La couche d'appel.** Par défaut `claude -p`. Si la mesure d'un appel vide (section 11) montre que le texte de départ de Claude Code rend l'objectif 1 intenable, les appels de jugement passent **directement par l'API d'Anthropic** (Messages API), avec une **clé API facturée à part de l'abonnement**. **C'est une option du paramétrage, jamais activée d'office** : l'installation (et ses réglages, modifiables ensuite) pose la question, avec l'écart de coût estimé, car chacun ne voudra pas ouvrir une facturation API ; sans accord, tout reste sur `claude -p` et l'objectif chiffré se lit avec cette couche. La clé se lit dans l'environnement (`ANTHROPIC_API_KEY`) au moment de l'appel seulement, jamais écrite, affichée ni journalisée (même règle que les clés des partenaires) ; sans clé, le moteur reste sur `claude -p` et le dit une fois au bureau. Les agents de production, eux, restent sur `claude -p` (ils ont besoin des outils de Claude Code). Les deux couches rendent le même usage exact (section 7).

### 5.2 Les types d'appels (tirés de l'essai)

| Type | Quand | Rend | Modèle **[choix]** |
|---|---|---|---|
| `decouper` | cahier validé | la file (éléments, groupes), le premier élément du prototype, les dépendances, ou `reprendre_methode` si une méthode validée ressemble | Sonnet |
| `traduire_retour` | message libre pendant le prototype | une consigne précise pour l'agent, ou « c'est une validation » | Haiku |
| `ecrire_methode` | méthode validée | le document de méthode, le brief de chaque rôle, les contrôles de départ | Sonnet (Opus si la fiche du projet le demande) |
| `apres_refus` | un contrôle ou une relecture refuse un élément | corriger (avec la consigne), `methode_a_revoir`, ou bloquer | Haiku |
| `conseil` | tout événement hors table, message ambigu | une action de la **liste fermée** des actions du moteur, avec ses paramètres, ou une question au Directeur | Haiku |

Les modèles suivent la norme des lots (le meilleur modèle par tâche, monter d'un cran au plus, jamais Fable).

### 5.3 Le conseil

Quand le moteur ne sait pas classer un événement (un message libre ambigu, une demande d'un type inconnu, un bouton du projet), il **demande conseil à une IA** : il lui donne l'événement, l'état court de la fonctionnalité et les consignes propres, et elle répond par une action de la liste fermée. Le moteur ne pose pas la question à l'utilisateur à sa place.

## 6. Les agents de production

- Le moteur assemble le message de départ avec **`lancer depart`** (inchangé : fiche, leçons, brief, tâche, consigne de fin), y ajoute la matière de la tâche (discussion, images, fichiers à lire, consigne rendue par un appel de jugement), et lance **`claude -p`** dans le dossier du projet, avec le modèle de la fiche (ou monté d'un cran, noté sur la tâche), les outils dont l'agent a besoin, et le format de sortie JSON.
- **Le rapport de fin** devient **structuré** : la consigne de fin d'étape de `depart` demande, en plus du texte, un bloc JSON (le message pour la discussion avec ses `images`, `questions`, `glossaire`, `attend` ; les fichiers produits ; les leçons ; les contrôles ; les retours sur la factory ; pour un contrôle, le verdict par élément). Le moteur le lit et applique les commandes ; le texte libre reste pour le journal.
- **Parallélisme** : le moteur tient la limite d'agents locaux du projet (`agent-libre`), la charge (`feu_vert`) et « deux éléments au plus en cours » en série, jamais pendant le prototype.
- **Les droits d'un agent sans fenêtre** **[choix]** : une liste d'outils autorisés par rôle (déclarée dans la fiche ; par défaut lire, écrire et modifier dans le dossier du projet, et lancer `py` et `git`), jamais le mode qui contourne toutes les autorisations. Un outil refusé est noté dans le rapport ; le moteur en fait une question au Directeur (ajouter l'outil à la fiche ou non).
- **L'accord de l'utilisateur en cours de tâche** **[choix]** (dépense chez un partenaire payant, changement de partenaire, navigateur) : l'agent ne peut pas attendre une réponse. Il **s'arrête et rend un rapport « accord requis »** (quoi, chez qui, combien) ; le moteur pose la décision au Directeur et, sur son accord, relance l'agent sur la même tâche avec l'accord écrit dans son départ. Le mode manuel reste toujours proposé à côté.
- **Ce que les agents écrivent eux-mêmes** **[choix]** : comme aujourd'hui, un agent d'un lot rend chaque tâche avec `lancer tache` avant la suivante (c'est ce qui donne la durée de chacune et la répartition exacte du coût), et note `partenaires usage` / `limite` après chaque appel payant. Tout le reste passe par son rapport structuré et c'est le moteur qui l'écrit. Les écritures simultanées dans le suivi existent déjà avec les agents en parallèle : l'outil les sérialise déjà.
- Un agent qui échoue (sortie illisible, code d'erreur, délai dépassé) : la tâche reste active une fois de plus avec la même consigne, puis passe bloquée avec la raison au journal.

## 6 bis. Les agents cloud

Les sessions cloud sont **intégrées au moteur** : un projet en cloud (ou mixte) passe lui aussi entièrement par le moteur, sans conversation orchestratrice. Voie retenue par l'utilisateur : **les sessions cloud de Claude Code, sur l'abonnement** ; leur facturation est **une estimation** (« de l'à-peu-près »), accepté par l'utilisateur.

- **Le départ.** Le moteur commit et pousse le dépôt du projet (la session clone la branche poussée), puis lance la session lui-même : `claude --cloud "<message de départ>"` dans le dossier du projet. Il n'y a plus de session à créer à la main ni de décision `session_cloud` à poser (la demande reste acceptée pour les projets existants). La sortie donne l'identifiant et l'adresse de la session, notés sur la tâche (le bureau peut les montrer).
- **Le modèle** : celui de la fiche, si la commande accepte de le choisir ; sinon le modèle par défaut de la session, noté sur la tâche **[à vérifier par le constructeur]**.
- **Le retour.** Aucune API ne rend la fin d'une session cloud, son texte ni ses tokens. Le message de départ d'un agent cloud lui demande donc de **committer son rapport structuré** (section 6) dans `.factory/rapports/<tâche>.json` sur sa branche `claude/…`, et de pousser. Le moteur fait un `git fetch` régulier (toutes les minutes **[choix]**), cherche ce fichier sur les branches `claude/…`, l'applique comme un rapport local, puis **fusionne la branche** dans la branche du projet ; un conflit devient une décision au Directeur (avec la branche et l'adresse de la session).
- **L'accord en cours de tâche** : l'agent cloud rend `accord_requis` de la même façon ; sur l'accord, le moteur envoie la suite à la même session (`claude -p "<accord>" --cloud <session>`).
- **La facturation** : l'agent déclare dans son rapport une estimation de ses tokens ; le moteur la note avec `lancer usage` (`total`, donc `estime: true`). Le bureau la montre comme une estimation.
- **Les limites** : les sessions cloud ne comptent pas dans la charge de la machine ; un nombre maximal de sessions cloud en même temps (réglage `agents_cloud_max`, 3 par défaut **[choix]**). Une session sans rapport au bout de 2 heures **[choix]** : décision au Directeur avec son adresse (relancer, attendre, abandonner).
- **Les prérequis** : le projet sur GitHub et `claude` connecté au compte claude.ai ; l'installation le vérifie quand le cloud est choisi. Sans eux, le moteur prend l'agent local équivalent si la charge le permet, et le dit au bureau.

## 7. La facturation

- `claude -p` en sortie JSON rend l'usage exact de l'appel (tokens d'entrée, de sortie, de cache, modèle, coût). Le moteur note **chaque** appel avec `lancer usage` :
  - un agent : sur sa tâche (un lot : la répartition existante entre ses tâches) ;
  - un appel de jugement : sur la tâche qu'il sert, étape `orchestration`, agent `orchestrateur` **[choix]** ; sans tâche, hors tâche, sur le projet. L'agent `orchestrateur` est connu de chaque projet sans fiche à écrire (l'outil `usage` l'accepte d'office).
- **Ce qui compte comme orchestration** **[choix]** : les seuls appels de jugement du moteur. L'agent de cadrage, ses questions et ses cahiers sont de la production, comme dans la mesure de référence (où les 1,76 € ne comptent que la conversation orchestratrice, sous-agents exclus) : la comparaison reste juste.
- La facturation reste exacte par projet et par tâche, et le bureau montre enfin **le coût de l'orchestration à part** de la production.

## 8. Garde-fous repris

Fable jamais choisi sans demande expresse ; aucune valeur de clé lue ailleurs qu'au moment de l'appel, jamais écrite ni journalisée ; accord de l'utilisateur avant une dépense chez un partenaire, un changement de partenaire, le navigateur ; mots interdits avant tout texte public ; mémoire de la skill seulement par `lecon appliquer` et `genre fixer`. Le moteur les tient **en code** quand c'est possible (refus avant l'appel), et les consignes des appels les rappellent.

## 9. Le banc d'essai

**But.** Mesurer, sur une même discussion, ce que coûte et ce que rend chacune de trois façons de faire, et vérifier l'objectif.

**Le scénario.** Un fichier de scénario rejoue la discussion d'un essai : les gestes de l'utilisateur (demandes du bureau, dans l'ordre, avec leurs textes et leurs images), déclenchés quand le moteur attend l'utilisateur, et les **rapports réels des agents** de l'essai (leur texte, leurs fichiers, leur usage), rendus à la place d'un vrai `claude -p` d'agent.
- Le **format** du scénario et un **petit scénario synthétique** générique (sans rien de l'essai) sont dans le dépôt, pour les tests.
- Le **scénario de l'essai de référence** est construit par un outil du dépôt à partir de son suivi et de ses transcriptions, **et rangé hors dépôt** (sous `~/MyIAFactory/bancs/`) **[choix]**. Rien de l'essai n'entre dans le dépôt public.

**Les trois façons de faire.**
1. **Le moteur**, avec les rapports d'agents rejoués : seuls ses appels de jugement sont réels et payés. C'est la mesure qu'on répète à chaque changement.
2. **L'orchestrateur actuel** : sa mesure est celle de l'essai lui-même (1,76 € d'orchestration, 97 appels), relevée dans sa transcription par l'outil du banc. On ne le refait pas tourner **[choix]**.
3. **Un agent seul** : une seule conversation `claude -p` (reprise à chaque tour) qui reçoit la même demande et les mêmes retours de l'utilisateur, et fait tout lui-même, comme le ferait un néophyte. **[choix]** Sonnet 5.5 (le modèle qu'un néophyte prend par défaut), les outils par défaut de Claude Code, dans une copie vide du dossier du projet, sans la skill, sans le bureau ni partenaire. Ses questions à l'utilisateur se comptent dans ses réponses (une réponse qui attend l'utilisateur = une question) ; le scénario lui donne le geste suivant de l'essai.

**Quand le moteur s'écarte de l'essai** **[choix]**. Les rapports d'agents de l'essai sont convertis une fois dans le nouveau format structuré et rangés par (étape, rôle, rang de l'élément dans la file). Le moteur qui découpe autrement (autre nombre d'éléments, autre premier élément du prototype) ou demande un tour de plus ne trouve plus de rapport : le banc **le note comme un écart** dans son rapport (ce n'est pas un échec en soi) et rend un rapport « rien à rejouer » qui fait finir la tâche. L'objectif 3 se lit alors sur le passage complet en vrai.

**Le budget.** Les passages répétés ne paient que l'orchestration. **Un seul passage complet en vrai** à la fin (vraie production) pour le moteur et pour l'agent seul.

**L'objectif chiffré**, sur l'essai de référence :
1. **Coût de l'orchestration du moteur ≤ 0,10 €**, contre 1,76 € (environ 6 % de la production).
2. **Coût total du moteur (orchestration + production) < coût total de l'agent seul** sur le passage complet.
3. **Même résultat** : cahier validé après les mêmes corrections, 5 éléments livrés aux trois tailles, méthode écrite, l'élément refusé corrigé, leçons notées ; et **pas plus de questions posées à l'utilisateur** que dans l'essai.

**Le rapport du banc** : par façon de faire, le nombre d'appels, les tokens, le coût, la part orchestration / production, les questions posées, et la liste du résultat attendu cochée ou non. Écrit hors dépôt, à côté du scénario.

## 10. Ce qui est remplacé

- `consignes.md` se réduit à ce que lisent les **appels de jugement** et les **agents** ; la boucle de réveil, la surveillance et la narration passent dans le code. `interface.md` reste le contrat des commandes.
- `guetteur.py` et la consigne « une conversation par fonctionnalité » ne servent plus qu'aux projets à adaptateur restés sur l'orchestrateur conversationnel (le projet pilote, en attendant son passage).
- `bureau/demarrage.py` démarre le moteur au lieu d'une console.

## 11. Ce qui est laissé au constructeur

- La **commande exacte** de `claude -p` (options pour couper les outils, le prompt système, les serveurs MCP et les réglages du dossier, pour qu'un appel de jugement ne paie pas le gros prompt système de Claude Code). **À mesurer en premier** : le coût d'un appel vide décide si les appels de jugement restent sur `claude -p` ou passent par l'API (section 5.1).
- Le **format** exact des dossiers d'appel, des réponses JSON et du rapport structuré des agents.
- La façon dont le moteur **démarre et s'arrête** avec le bureau (même processus ou processus enfant), et la reprise après un arrêt (le suivi garde tout ; une tâche active dont l'agent a disparu est relancée une fois).
- Les options exactes de `claude --cloud` (choix du modèle, branche de départ, envoi d'une suite) et la façon de retrouver la branche d'une session (section 6 bis).
- La **relecture croisée** et ses deux relecteurs : purement du code (qui lancer, quoi leur donner), ses comparaisons de rapports comprises quand les rapports sont structurés ; sinon un appel `apres_refus`.
