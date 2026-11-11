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

Sans entrée. L'instantané **court** que l'orchestrateur relit à chaque réveil : `{projet, genre, pause, reveil,
seuil_methode, fonctionnalites, taches, taches_faites, file, decisions, lecons, agents, consignes}`. Les listes longues
y sont comptées, pas recopiées :
- une fonctionnalité : `id`, `nom`, `etape`, `agent_cadrage`, `attend_reponse`, `catalogue`, `decisions`, `livrable`,
  `cahier` (`{maquette: n, etapes: n, valide_le}`), `methode` (`{version, validee_le}`), et les nombres `file`,
  `messages`, `documents`, `glossaire`, plus `dernier_message` (`{id, auteur, t, texte}`, 300 caractères au plus) ;
- `taches` : les tâches pas encore faites (active, ou hors de la colonne `fait`), avec `journal` = le nombre
  d'entrées et `dernier_journal`, `captures` = leur nombre ; `taches_faites` : combien sont faites ;
- `file` : le nombre d'éléments à faire par fonctionnalité ; `lecons` : `{id, agent, etage_propose}` des leçons à
  valider ;
- un agent : `{cle, role, service, modele, lieu, session, libre}` ; une décision : `{id, genre, texte, portee}`
  (`portee` = l'id de la fonctionnalité, ou `projet`) ;
- `consignes` : une empreinte courte des consignes génériques, de cette interface et des consignes propres du projet ;
  elle change quand l'un de ces textes change.

### `detail`

Entrée : `{"fonctionnalite": id}` (la fonctionnalité entière : discussion, cahier, méthode, file, documents,
glossaire), `{"tache": id}` (la tâche entière : journal, captures) ou `{"lecons": true}` (les leçons à valider avec
leur texte). Ce que `etat` compte, `detail` le donne, quand il sert. Code 1 si l'objet est inconnu.

### `fonctionnalite`

Entrée : `{"id", "nom"?, "etape"?, "agent_cadrage"?, "cahier"?, "methode"?, "livrable"?, "catalogue"?}`. Met à
jour la fonctionnalité (`etape` : `cadrage`, `cahier`, `decoupage`, `prototype`, `methode`, `serie`, `terminee` ;
`cahier` : `{maquette: [chemins], etapes: [textes], valide_le?}` ; `methode` : `{version, lien | chemin,
validee_le?}` ; `livrable` : `{libelle, lien | chemin, date}`). Rend la fonctionnalité.

### `message`

Entrée : `{"fonctionnalite", "auteur", "texte", "images"?: [chemins]}`. `auteur` : `utilisateur` ou la clé d'un
agent. Un message d'agent remet `attend_reponse` à faux. `"attend": true` dit qu'il demande une réponse de l'utilisateur
(le Directeur le liste dans « Réponses attendues »), `false` que c'est un compte rendu ; sans lui, un message qui
contient une question en attend une. Un agent peut joindre des **questions à choix**,
`"questions": [{"texte", "choix": [2 à 12 textes], "multiple"?: true}]` (10 au plus) : le bureau montre un bouton par
choix, un bouton « Autre » (avec un champ pour la valeur voulue) et un bouton « Passer » ; la réponse revient en un `message` lisible (« question → choix », « (passée) »,
puis le texte libre, obligatoire quand une question est passée). Un agent peut aussi définir les mots spécialisés
qu'il emploie : `"glossaire": [{"mot", "definition"}]` (60 et 400 caractères au plus). Ils entrent dans le
**glossaire de la fonctionnalité** (un mot redéfini prend la définition la plus récente), qui est gardé par le suivi,
écrit dans `<pieces>/<fonctionnalité>/glossaire.md` (rangé dans ses documents), donné par `etat`, joint au message
de départ des agents de la fonctionnalité, et mis en valeur au bureau (définition au survol). `fonctionnalite` accepte
aussi `glossaire` (mêmes entrées). Rend `{"id": "m3"}`.

### `decision`

Entrée : `{"action": "poser", "portee", "genre", "texte", ...}` ou `{"action": "lever", "id"}`.
`portee` = l'id d'une fonctionnalité (`genre` : `valider_cahier`, `valider_methode`, `methode_a_revoir`) ou
`projet` (`confirmer_genre` avec `propose` et `genres_connus`, `session_cloud` avec `agent`, ou `organisation` avec
`organisation`). Une décision `organisation` porte `{"services": [{id, nom}] (la liste complète après changement),
"flux": [{id, nom, role, service}] (complet), "agents": [fiches] (les nouveaux seulement), "briefs": {rôle: texte}
(nouveaux rôles), "cout": {"tokens": [a, b], "euros": [a, b] | null}}` ; elle est contrôlée comme une proposition
(Fable refusé, clés et rôles, briefs). Poser deux fois la
même décision rend la même. Rend `{"id": "d2"}` ou `{"ok": true}`.

### `tache`

Entrée : sans `id`, une création (`titre` obligatoire) ; avec `id`, une mise à jour. Champs : `titre`,
`fonctionnalite`, `element`, `role`, `colonne`, `agent`, `etape`, `modele_depart`, `montee` (`{de, a, raison}`),
`journal` (un texte, ou une liste, ajoutés), `bloquee`, `active`, `captures` (chemins), `lignes` (les lignes produites
par la tâche, son total : l'échelle de son coût au bureau), `depend_de` (liste d'identifiants de tâches connues : ce
que la tâche attend ; refus d'une tâche inconnue, d'elle-même ou d'un cycle), `lot` (`{"id": "L2", "rang": 3}` ou
`null` : le lot de la tâche et son rang), `partenaires` (ids du catalogue des partenaires que la tâche appelle : le
départ donne leurs règles ; refus d'un id inconnu). L'outil note `debut` au passage à `active: true` et `fin` au passage à
`active: false` (ils servent à répartir le coût d'un lot). Un agent ne tient qu'une
tâche active à la fois ; passer dans `fait` rend la tâche inactive ; `Fable` est refusé (quelle que soit la casse)
en `modele_depart` comme en `montee` ; une `montee` va d'un cran exactement (Haiku → Sonnet → Opus). Rend la tâche.

### `organisation`

Entrée : `{"action": "appliquer", "decision": id}`, pour une décision `organisation` du projet que l'utilisateur a
acceptée (demande `organisation`, `verdict` : `accepter` ou `refuser`, version 4). Réécrit `services` et `flux` du
fichier de factory (le reste est gardé), crée les fiches et les briefs nouveaux (un brief existant est gardé), lève la
décision. Rend `{"ok": true, "services": [...], "flux": [...]}`. Refus (code 1) si la décision est inconnue ou n'est
pas de ce genre, ou si son contenu ne passe plus le contrôle (le projet a changé) : rien n'est écrit, la décision reste.

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

**Un lot.** `lot` (identifiant) à la place de `tache` : le total du lot (`entree`/`sortie`, ou `total`) est réparti
entre ses tâches au prorata de leur durée (`fin - debut`), à parts égales si une durée manque ou vaut 0, en entiers et par
la méthode des plus forts restes : la somme des parts vaut exactement le total, compteur par compteur. Une ligne
d'usage par tâche, avec `tache`, `lot` et `reparti` (`temps` ou `egal`) ; rend `{"ids": [...], "reparti": …}` ;
refus d'un lot inconnu ou déjà noté. Avec `tache`, `lot` et un `id` **cumulatif** (le même pour tout le lot), chaque
appel écrit l'écart avec le cumul précédent : exact, `reparti` absent (refus d'un cumul qui recule). Le bureau marque
« estimé (part d'un lot) » le coût d'une tâche aux parts réparties ; les totaux ne changent pas.

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
`[x, y]` dans un repère où **y monte vers le haut** (le nord est en haut de la carte). Un tracé peut porter son
`groupe` : il n'est alors montré qu'avec ce groupe. Le **fond** de la vue de haut, facultatif, est une liste
d'emprises `fond: [{points: [[x, y], …] (3 au moins), element?, groupe?}]` : une emprise qui nomme un `element` prend sa
teinte et suit son groupe, les autres sont un contexte neutre (rues, bâtiments voisins). Les chemins d'un catalogue
déclaré dans le fichier de factory sont relatifs au dossier de ce fichier ; le bureau les ramène lui-même à ses
réglages.

### `document`

Entrée : `{"fonctionnalite", "chemin", "titre", "agent"?, "etape"?, "tache"?, "element"?, "sous_tache"?, "livrable"?, "remplace"?}`.
`"remplace"` : le chemin du document dont celui-ci est la nouvelle version (une maquette refaite, une ébauche
reprise, un livrable corrigé) ; un document de même titre et de même élément en est aussi une. Le bureau montre la
dernière version, et les précédentes sous « Voir l'historique ».
`"livrable": true` marque un fichier final d'un élément validé : le bureau le montre dans les « Livrables » de la
fonctionnalité, où l'utilisateur peut demander une modification (`retour_element` si la fonctionnalité a un
catalogue, sinon un `message` qui nomme l'élément). Inscrit un
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
elle reste « à valider » (un échec du seul `git push` garde la leçon commitée dans la copie locale et le dit : elle n'est
pas publiée). `invalider` : la leçon disparaît. Rend `{"ok": true, "etage": …}`.

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
La limite `agents_locaux_max` du fichier de factory (de 1 à 16, 2 par défaut) borne les tâches actives tenues par des
agents locaux : une fois atteinte, aucun agent local n'est rendu, la raison est « limite de {n} agents locaux
atteinte » ; les agents cloud ne comptent pas. Le relevé (version 4) la publie en `agents_locaux_max`.

### `depart`

Entrée : `{"agent", "tache"}` (ou `taches`, voir plus bas). Assemble le **message de départ** de l'agent pour cette tâche : le projet et son
genre, la fiche entière, les leçons de la skill et du genre qui touchent son rôle (jamais celles d'un autre rôle ni
d'un autre genre), le brief du rôle (`<fiches>/briefs/<rôle>.md`), la tâche, la consigne de fin d'étape (résultat,
leçons avec étage proposé et texte général, retours sur la factory). Pour un agent cloud, le message commence par
« Tu repars de zéro. ». Une tâche qui porte `partenaires` ajoute « Règles de tes partenaires » : les règles de chacun,
mot pour mot, la clé jamais écrite ni affichée, et `lancer partenaires` `usage` / `limite` après chaque appel. Rend
`{"message": "…"}`.

**Un lot.** `taches` (liste d'identifiants, dans l'ordre du lot) à la place de `tache` : un seul message de départ
pour l'agent, avec le brief de chaque rôle présent, les tâches dans l'ordre et la consigne de rendre compte à la fin de
chaque tâche (`lancer tache`) avant de passer à la suivante.

### `partenaires`

Entrée : `{"action", …}`. Les partenaires (voix, images, 3D, traduction…) sont **facultatifs** : rien ne bloque sans
eux. **Aucune valeur de clé** n'est jamais écrite, rendue ni journalisée. Trois fichiers : le catalogue de la skill
(`partenaires/catalogue.json`), les connexions, quotas, limites et règles de la machine (`~/MyIAFactory/partenaires.json`,
communs à tous les projets) et les conseils du projet (`partenaires.json` à côté du fichier de factory, donc
`.factory/partenaires.json`).

| `action` | Entrée | Effet, sortie |
|---|---|---|
| `detecter` | — | Serveurs MCP déclarés (`~/.claude.json` et `.mcp.json` du projet : nom et `url` seulement, jamais `headers`, `env`, `args`) et **présence** des variables du catalogue (environnement, `.env` du projet : noms seulement) → `declare` ; un `declare` qui n'est plus vu → `non_connecte` ; un `connecte` le reste. Rend `{"connexions": {id: {nom, etat, source}}}`. |
| `confirmer` | `{ids, source?, retirer?}` | Les partenaires dont les outils sont vraiment disponibles (ou déclarés par l'utilisateur, comme un studio) → `connecte` ; `retirer: true` → `non_connecte`. |
| `quota` | `{ids?, force?}` | Lit le reste chez les partenaires qui ont un lecteur (`connecte` ou `declare` par défaut), au plus une fois par heure chacun sauf `force`. Le lecteur, son adresse et la variable de la clé sont figés dans l'outil (jamais lus du catalogue) ; la clé est lue (environnement, puis `.env` du projet) pour cet appel seulement, aucune redirection n'est suivie. Un reste nul pose une limite ; un reste positif ou « illimité » ne lève que celle-là. Un fichier des partenaires illisible : refus clair, sauf `choisir` (liste vide). Rend `{"lus", "rates", "sautes": [{id, raison}]}`. |
| `choisir` | `{besoin}` | Les connectés utilisables (actifs, sans limite en cours), dans l'ordre des conseils du projet pour ce besoin puis les autres de la même sous-catégorie : `{"partenaires": [{id, nom, tarif, accord_requis}], "meilleur_non_connecte"}`. `accord_requis` : tarif à l'usage ou inconnu. Une liste vide : mode manuel, navigateur (avec l'accord) ou autre voie. |
| `usage` | `{partenaire, tache?, agent?, quantite, unite, cout?, devise?, estime?}` | Une ligne d'usage partenaire dans le suivi (le relevé la donne au bureau, qui la facture). Sans `cout` : « non chiffré », jamais 0 ; un `cout` a sa `devise`. Rend `{"id"}`. |
| `limite` | `{partenaire, raison}` | « Limite atteinte » : sauté par `choisir` jusqu'au prochain relevé de quota qui montre un reste, un jour au plus. |
| `regle` | `{partenaire, operation: ajouter \| modifier \| supprimer, id?, texte?}` | Les règles d'usage de l'utilisateur (500 caractères au plus). À la création du fichier, la règle de départ de Tripo est proposée ; supprimée, elle ne revient pas. |
| `conseils` | `{}` ou `{besoins: {besoin: [{id, raison}]}}` | Lit ou écrit les conseils du projet (ids actifs du catalogue, une raison d'une phrase). |
| `a_refaire` | — | Les fiches que « Mettre à jour les offres » revérifie (actives, vérifiées il y a plus de 30 jours ou d'après une source tierce) et le coût estimé : `{"ids", "cout": {euros, texte}}`. |
| `offres` | `{partenaires: [fiches complètes]}` | Remplace (ou ajoute) ces fiches dans le catalogue de la skill, le contrôle (`catalogue.verifier`, mots interdits du projet), puis commit et push comme une leçon de skill. |

Le relevé porte `partenaires` (voir `docs/releve.md`) : le catalogue réduit aux champs affichés, l'état sans clé, les
conseils, `maj_catalogue` et `cout_maj` ; et ses `usage` portent les lignes `genre: "partenaire"`.

### `lots`

Entrée : `{"taches": [ids]?}`, ou `{}` : **toutes les tâches pas encore parties du projet, toutes fonctionnalités
confondues**. Regroupe ces tâches en lots d'un même modèle et d'un même lieu (ceux de leur agent, sinon de l'agent libre
du rôle) et rend `{"lots": [{"lot": "L3", "modele", "lieu", "taches": [ids]}], "tailles": {modèle: n}, "ecartees":
[{tache, raison}]}`. Une tâche déjà active, faite ou déjà prise n'est jamais remise en lot (refus si elle est nommée).
Chaque lot a au plus la taille conseillée de son modèle (5 sans mesure ; sinon d'après le coût moyen d'une tâche au rang
k d'un lot comparé à une tâche seule), une relecture est toujours seule, et un lot ne passe devant une tâche qui
dépend d'une autre non encore formée. Les lots sont numérotés après les lots déjà notés sur les tâches. Refus (code 1)
sur un cycle de `depend_de` ou une dépendance inconnue. La commande ne note rien : `lancer tache` (`lot`) le fait.

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
