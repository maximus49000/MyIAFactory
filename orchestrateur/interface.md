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
colonne `cadrage`. Le bureau le lit par la commande du relevé de ses réglages.

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
le bouton `pause` ou `reprendre` change l'état de la factory (demande aussitôt « traitée »). Rend
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
taches, file, decisions, lecons, agents}`. Un agent : `{cle, role, service, modele, lieu, session, libre}`. Une
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
tâche active à la fois ; passer dans `fait` rend la tâche inactive ; `Fable` est refusé. Rend la tâche.

### `file`

Entrée : `{"fonctionnalite", "elements": [{"id", "nom", "groupe"?}]}`. Remplace la file des éléments à faire de la
fonctionnalité. Rend `{"elements": n}`.

### `file-prendre`

Entrée : `{"fonctionnalite"}`. Rend `{"element": {id, nom, groupe?}}`, l'élément suivant, ou `{"element": null}`.

### `session`

Entrée : `{"agent", "session"}`. Inscrit la session attitrée de l'agent dans la table des sessions. Rend
`{"ok": true}`.

### `catalogue`

Entrée : `{"fonctionnalite"}` (ou, sans entrée, l'identifiant en argument : `catalogue <fonctionnalité>`, pour une
commande de catalogue du bureau). Rend le catalogue générique (format de `bureau/catalogue.py`) : les éléments de la
fonctionnalité avec leur état (`fait`, `en_cours`, `a_faire`), leurs captures, leurs passes et leurs retours.

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
