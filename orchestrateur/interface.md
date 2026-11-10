# L'interface des commandes de l'orchestrateur

Ce document est le **contrat** entre l'orchestrateur générique et un projet. Les outils génériques de ce dossier
le respectent ; un projet qui garde ses propres outils écrit de petits **adaptateurs** qui le respectent aussi, et
les déclare dans son fichier de factory (`commandes`). `verifier_interface.py` contrôle ce contrat.

## Appeler une commande

```
py -3.12 orchestrateur/outil.py --factory <fichier de factory> <commande> [arguments]
py -3.12 orchestrateur/outil.py --factory <fichier de factory> lancer <commande> [arguments]
```

- **Entrée** : un objet JSON (UTF-8) sur l'entrée standard, pour les commandes qui en prennent une. Une commande
  « sans entrée » ne lit jamais l'entrée standard.
- **Sortie** : un objet JSON (UTF-8) sur la sortie standard.
- **Codes** : `0` fait ; `1` refusé, la sortie est `{"erreur": "<texte>"}` ; `2` appel invalide (commande inconnue,
  entrée illisible ou absente alors qu'elle est obligatoire, fichier de factory illisible), même sortie d'erreur.
- `lancer <commande>` lance la commande **déclarée** par le projet (`commandes` du fichier de factory : une liste
  d'arguments, lancée depuis le dossier du fichier de factory, avec la variable `MYIAFACTORY_FACTORY` = le chemin
  du fichier de factory), avec la même entrée et les mêmes arguments ; sinon la commande générique. Le code et la
  sortie de la commande déclarée sont rendus tels quels. L'orchestrateur n'appelle les commandes que par `lancer`.
- Les chemins que les commandes échangent sont **relatifs au dossier du fichier de factory** ; le relevé les rend
  relatifs au dossier des réglages du bureau (c'est ce que le bureau attend).

## Les commandes

### `releve`

Sans entrée. Rend le **relevé version 4** (voir la conception, §8.1) tiré du suivi et des fiches : colonnes
`cadrage`, puis le flux du projet, puis `fait` (terminée) ; le chef porte une tâche active « Orchestration » dont
`maj` est son dernier `reveil` ; pendant le cadrage, l'agent de cadrage porte la tâche « Cadrage : <nom> » dans la
colonne `cadrage` (celle que l'orchestrateur a créée avec `tache`, ou à défaut une tâche montrée seulement au relevé,
d'identifiant `cadrage:<fonctionnalité>`). Le bureau le lit par la commande du relevé de ses réglages.

```
$ outil.py --factory F releve
{"version": 4, "projet": "…", "factory": {"etat": "en marche", "depuis": null}, "services": […], "colonnes": […],
 "titulaires": […], "taches": […], "file": {"visibles": […], "suite": […], "reste": 0}, "fonctionnalites": […], …}
```

### `charge`

Sans entrée. Lance `lancer.py charge --reglages <réglages>` du dépôt de la skill. Rend
`{"feu_vert": true|false, "texte": "ok : charge 12 % (max 75 %)"}` ; code 1 si la mesure ne peut pas se faire.

### `actions`

Entrée : une **demande du bureau** (JSON, avec son `type` et son `t`). C'est la commande d'actions des réglages du
bureau. La demande est ajoutée au suivi comme « en attente » (identifiant `r<n>`) et au journal `demandes.jsonl` à
côté du suivi. Les images jointes sont décodées dans `pieces/<fonctionnalité>/<date>-<nom>` et remplacées par leurs
chemins. `fonctionnalite` crée tout de suite la fonctionnalité (étape `cadrage`, nom provisoire de 40 caractères,
son message en première ligne de discussion) ; `message` ajoute le message à la discussion et met `attend_reponse` ;
le bouton `pause` ou `reprendre` change l'état de la factory (demande aussitôt « traitée ») ; un `deplacer` des
tâches `orchestration` ou `cadrage:<fonctionnalité>` (montrées seulement au relevé) est refusé. Rend
`{"ok": true, "id": "r1"}`.

**Exception au format des erreurs** : un refus (code 1) écrit **une ligne de texte brut** (pas du JSON), car le
bureau la montre telle quelle à l'utilisateur.

### `reveil`

Sans entrée. Note l'heure du réveil du chef (c'est ce qui dit au bureau que l'orchestrateur tourne). Rend
`{"reveil": "<date ISO>"}`.

### `demandes`

Sans entrée. Rend `{"demandes": [...]}` : les demandes « en attente », les plus anciennes d'abord. Chaque demande :
`id`, `type`, `t`, `statut`, `reponse`, plus ses champs ; l'identifiant d'un bouton ou d'une leçon visée est dans
`cible`.

### `demande-traitee`

Entrée : `{"id": "r1", "reponse"?: "texte"}`. Marque la demande traitée ; la réponse d'un `retour` apparaît sur la
tâche au relevé suivant. Rend `{"ok": true}` ; code 1 si la demande est inconnue ou déjà traitée.

### `etat`

Sans entrée. Un instantané pour l'orchestrateur : `{projet, genre, pause, reveil, seuil_methode, fonctionnalites,
taches, file, decisions, lecons, agents, consignes}`. `consignes` est une empreinte courte des consignes
génériques, de cette interface et des consignes propres du projet : elle change quand l'un de ces textes change. Un agent : `{cle, role, service, modele, lieu, session, libre}`. Une
décision : `{id, genre, texte, portee}` (`portee` = l'id de la fonctionnalité, ou `projet`).

### `fonctionnalite`

Entrée : `{"id", "nom"?, "etape"?, "agent_cadrage"?, "cahier"?, "methode"?, "livrable"?, "catalogue"?}`. Met à
jour la fonctionnalité (`etape` : `cadrage`, `cahier`, `decoupage`, `prototype`, `methode`, `serie`, `terminee` ;
`cahier` : `{maquette: [chemins], etapes: [textes], valide_le?}` ; `methode` : `{version, lien | chemin,
validee_le?}` ; `livrable` : `{libelle, lien | chemin, date}`). Rend la fonctionnalité.

### `message`

Entrée : `{"fonctionnalite", "auteur", "texte", "images"?: [chemins]}`. `auteur` : `utilisateur` ou la clé d'un
agent. Un message d'agent remet `attend_reponse` à faux. Rend `{"id": "m3"}`.

### `decision`

Entrée : `{"action": "poser", "portee", "genre", "texte", ...}` ou `{"action": "lever", "id"}`.
`portee` = l'id d'une fonctionnalité (`genre` : `valider_cahier`, `valider_methode`, `methode_a_revoir`) ou
`projet` (`confirmer_genre` avec `propose` et `genres_connus`, ou `session_cloud` avec `agent`). Poser deux fois la
même décision rend la même. Rend `{"id": "d2"}` ou `{"ok": true}`.

### `tache`

Entrée : sans `id`, une création (`titre` obligatoire) ; avec `id`, une mise à jour. Champs : `titre`,
`fonctionnalite`, `element`, `role`, `colonne`, `agent`, `etape`, `modele_depart`, `montee` (`{de, a, raison}`),
`journal` (un texte, ou une liste, ajoutés), `bloquee`, `active`, `captures` (chemins). Un agent ne tient qu'une
tâche active à la fois ; passer dans `fait` rend la tâche inactive ; `Fable` est refusé (quelle que soit la casse)
en `modele_depart` comme en `montee` ; une `montee` va d'un cran exactement (Haiku → Sonnet → Opus). Rend la tâche.

### `file`

Entrée : `{"fonctionnalite", "elements": [{"id", "nom", "groupe"?}]}`. Remplace la file des éléments à faire de la
fonctionnalité. Rend `{"elements": n}`.

### `file-prendre`

Entrée : `{"fonctionnalite", "element"?}`. Retire de la file et rend `{"element": {id, nom, groupe?}}` : l'élément
suivant, ou celui dont l'identifiant est `element` (code 1 s'il n'est pas dans la file) ; `{"element": null}` si la
file est vide.

### `usage`

Entrée : `{"modele", "agent"?, "tache"?, "etape"?, "entree", "sortie", "cache_lecture"?, "cache_ecriture"?, "id"?}`, ou
`total` à la place de `entree` et `sortie` quand seul le total est connu (un sous-agent ne donne que lui : il compte
alors comme des tokens d'entrée, et le coût est une **estimation basse**). Note les tokens d'une exécution d'agent ;
`id` absent : un nouvel usage, rendu `{"id": "u3"}` ; `id` donné : les compteurs de cet usage sont remplacés (des
**cumuls**, tant que l'exécution continue). Le relevé donne les usages récents au bureau (`usage`), qui les convertit en
euros estimés dans l'onglet Facturation ; une pièce `facturation` (service de ce nom) le garde toujours visible.

### `session`

Entrée : `{"agent", "session"}`. Inscrit la session attitrée de l'agent dans la table des sessions. Rend
`{"ok": true}`.

### `catalogue`

Entrée : `{"fonctionnalite"}` (ou, sans entrée, l'identifiant en argument : `catalogue <fonctionnalité>`, pour une
commande de catalogue du bureau). Rend le catalogue générique (format de `bureau/catalogue.py`) : les éléments de la
fonctionnalité avec leur état (`fait`, `en_cours`, `a_faire`), leurs captures, leurs passes et leurs retours.

Le bureau trouve la source du catalogue d'une fonctionnalité dans `catalogues` du fichier de factory (ou des
réglages) : `{<id>: {fichier} | {commande}}`, ou la clé `"*"` pour toutes les fonctionnalités, où `{fonctionnalite}`
est remplacé par l'identifiant (lettres, chiffres, `-` et `_` seulement) :
`"catalogues": {"*": {"commande": ["python", "<skill>/orchestrateur/outil.py", "--factory", "factory.json", "lancer",
"catalogue", "{fonctionnalite}"]}}`.

Pour que la carte et les fiches du bureau colorent bien un élément, un catalogue de projet devrait employer ces
identifiants d'état : `fait` (ou `valide`, `termine`, `ok`) pour un élément terminé, `a_faire` (ou `a_revoir`,
`en_cours`, `todo`) pour un élément à faire ; un élément qui porte un `doute` est montré à part ; tout autre état
est montré comme « autre ». Les positions (`position` d'un élément, `points` de `trace`) sont des paires `{x, y}` et
`[x, y]` dans un repère où **y monte vers le haut** (le nord est en haut de la carte).

### `document`

Entrée : `{"fonctionnalite", "chemin", "titre", "agent"?, "etape"?, "tache"?, "element"?, "sous_tache"?}`. Inscrit un
fichier produit pour la fonctionnalité (une méthode, un rapport, un script, une image…) dans ses **documents**, avec
son origine et la date ; un chemin déjà inscrit est complété, pas doublé. Rend `{"id": "doc3"}`. Les images de la
discussion (`message`, et celles jointes par l'utilisateur), les maquettes du cahier (`fonctionnalite`) et les
captures d'une tâche (`tache`) y sont rangées d'office, avec l'agent, l'étape, la tâche et l'élément. Le relevé les
montre dans `documents` de la fonctionnalité ; le bureau les sert depuis les racines `documents` de ses réglages.

### `memoire`

Entrée : `{"role"}`. Rend les leçons de la mémoire qui touchent ce rôle (ou « tous ») :
`{"genre_id": "…"|null, "skill": [leçon], "genre": [leçon]}`. Une leçon : `{id, titre, roles, date, texte}`. Un projet
sans genre ne reçoit que les leçons de la skill ; il ne reçoit **jamais** celles d'un autre genre.

### `genre`

Entrée : `{"action": "lister"}` → `{"genre": …, "genres": [{id, domaine, livrable, outils}]}`, ou
`{"action": "fixer", "genre", "description"?}` : écrit le genre dans le fichier de factory. Un genre inconnu demande
une `description` : son fichier de mémoire est alors créé, commité et poussé (rien n'est changé si cela échoue).
Rend `{"genre": "…", "cree": true|false}`.

### `lecon`

Entrée : `{"action": "noter", "agent", "texte", "tache"?, "etage_propose", "texte_general"?, "roles"}` : note la
leçon sur la fiche de l'agent, « à valider » ; `etage_propose` vaut `projet`, `genre` ou `skill` ; pour `genre` et
`skill`, `texte_general` (le texte réécrit en termes généraux, sans nom de projet, de lieu, de fichier ni de
personne) est obligatoire. Rend `{"id": "<agent>:L1"}`.

Entrée : `{"action": "appliquer", "id", "verdict": "valider"|"invalider", "etage"?}` : le verdict de l'utilisateur.
`projet` : la leçon de la fiche passe « validée ». `genre` ou `skill` : le texte général est ajouté à la mémoire (mise à
jour du dépôt, mots interdits, commit, push) ; la leçon ne passe « validée » que si l'ajout réussit, sinon code 1 et
elle reste « à valider ». `invalider` : la leçon disparaît. Rend `{"ok": true, "etage": …}`.

### `controle`

Entrée : `{"texte", "origine"}`. Ajoute une ligne au registre des contrôles du projet (`C<n> · date · origine :
texte`). Rend `{"numero": n}`.

### `agent-libre`

Entrée : `{"role", "modele"?, "lieu"?}`. Cherche le premier spécialiste du rôle (fiches) sans tâche active, au
modèle et au lieu demandés. Rend `{"agent": "<clé>"|null, "raison": "…"}` (code 0 même s'il n'y en a pas). Raisons
sans agent : « aucun dev libre » ; pour le cloud (un agent cloud n'est utilisable qu'avec une session attitrée) :
« aucun agent cloud dev sur Sonnet : session à créer pour dev-3 », avec `"sans_session": "dev-3"`, la fiche qui
attend sa session (l'orchestrateur pose alors une décision `session_cloud` qui la nomme) ; « aucun agent cloud dev
libre sur Sonnet » (les sessions existent, elles sont occupées : on attend) ; « aucune fiche cloud dev sur Sonnet :
ajoutez-en une ». Pour le cloud, `sans_session` est toujours présent quand `agent` est nul.
Choisir le modèle : on monte d'un cran au plus (Haiku → Sonnet → Opus) et jamais vers Fable.

### `depart`

Entrée : `{"agent", "tache"}`. Assemble le **message de départ** de l'agent pour cette tâche : le projet et son
genre, la fiche entière, les leçons de la skill et du genre qui touchent son rôle (jamais celles d'un autre rôle ni
d'un autre genre), le brief du rôle (`<fiches>/briefs/<rôle>.md`), la tâche, la consigne de fin d'étape (résultat,
leçons avec étage proposé et texte général, retours sur la factory). Pour un agent cloud, le message commence par
« Tu repars de zéro. ». Rend `{"message": "…"}`.

## Vérifier une implémentation

```
py -3.12 orchestrateur/verifier_interface.py --factory <fichier de factory> [--complet]
```

Lance chaque commande par `lancer` (donc l'adaptateur du projet s'il y en a un) et contrôle ses champs, ses types et
ses codes de sortie, y compris le refus (code 1 et un message) d'une entrée inconnue. Une ligne par commande : `ok`,
`ÉCART <commande> : …` ou `ignoré <commande> : …` ; code 0 si tout est conforme, 1 s'il y a un écart.

Sans `--complet`, seules les commandes qui ne changent rien (`releve`, `etat`, `demandes`, `memoire`,
`genre lister`, `agent-libre`, `depart`, `catalogue`) sont lancées : on peut le faire sur le projet lui-même. Avec
`--complet`, un petit scénario lance aussi les autres (création d'une fonctionnalité, d'une tâche, d'une décision,
d'une leçon…), qui **changent le suivi, les fiches et la table des sessions** : à ne faire que sur une **copie** du
projet. Il refuse si le dossier du fichier de factory est dans un dépôt git et n'est pas marqué par un fichier
`.copie-de-verification` (code 2).
