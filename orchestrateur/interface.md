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
`{"feu_vert": true|false, "texte": "ok : charge 12 % (max 75 %)"}` ; code 1 si la mesure ne peut pas se faire. Le moteur lit
dans `texte` la charge et le plafond (`charge N % (max M %)`) pour dire au bureau « En attente : charge 90 % (plafond
70 %) » quand une tâche prête est retenue : ce format du texte est donc un contrat. (Les installations d'outils ne passent
pas par cette mesure : elles partent sans condition de charge.)

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

### `guetter`

Sans entrée, **ne rend jamais la main** : c'est la commande du moniteur de l'orchestrateur. Elle écrit une ligne
`demande <id> <type>` par demande ajoutée au journal (`demandes.jsonl`, à côté du suivi) après son lancement, et note
toutes les 20 s sa présence dans `presence.json` (à côté du suivi, ignoré par git) ; toute autre commande de l'orchestrateur la note aussi (sauf celles que le bureau lance). Le relevé en tire
`orchestrateur_present` (présence de moins de 2 minutes) ; sans lui, le bureau bloque les gestes et propose de lancer
l'orchestrateur.

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

Entrée : `{"id", "nom"?, "etape"?, "genre"?, "workflow"?, "deplacee_vers"?, "agent_cadrage"?, "cahier"?, "methode"?,
"livrable"?, "catalogue"?}`. Met à
jour la fonctionnalité (`etape` : `cadrage`, `cahier`, `decoupage`, `prototype`, `methode`, `serie`, `terminee`,
`deplacee` (la fonctionnalité est partie dans un autre projet, dont `deplacee_vers` donne le nom : ni livrée ni
comptée) ; `genre` : l'identifiant du genre de la fonctionnalité (ou `null`) ; `workflow` : l'identifiant du
workflow du projet qu'elle suit (ou `null` : le workflow principal) ;
`cahier` : `{maquette: [images], etapes: [textes], valide_le?}` (une image : un chemin, ou `{"chemin", "legende"}` ;
la légende est une phrase de 160 caractères au plus qui dit à quoi l'image correspond, affichée sous elle ; ajouter ou
changer des légendes seules ne crée pas de version du cahier) ; `methode` : `{version, lien | chemin,
validee_le?}` ; `livrable` : `{libelle, lien | chemin, date}`). Rend la fonctionnalité.

### `message`

Entrée : `{"fonctionnalite", "auteur", "texte", "images"?: [chemins ou {"chemin", "legende"}]}` (la légende d'une image d'agent :
une phrase de 160 caractères au plus). `auteur` : `utilisateur` ou la clé d'un
agent. Un message d'agent remet `attend_reponse` à faux. `"attend": true` dit qu'il demande une réponse de l'utilisateur
(le Directeur le liste dans « Réponses attendues »), `false` que c'est un compte rendu ; sans lui, un message qui
contient une question en attend une. Un agent peut joindre des **questions à choix**,
`"questions": [{"texte", "choix": [2 à 12 textes], "multiple"?: true}]` (10 au plus) : le bureau montre un bouton par
choix, un bouton « Autre » (avec un champ pour la valeur voulue) et un bouton « Passer » ; la réponse revient en un `message` lisible (« question → choix », « (passée) »,
puis le texte libre, obligatoire quand une question est passée). `multiple: true` (plusieurs réponses vraies
ensemble ; absent ou faux = un seul choix) rend les boutons basculables : la réponse liste les choix retenus. À la
création d'un projet, la même clé existe dans les questions du chef (`definir_workflow`) et la réponse arrive en
`"Fun ; Jouabilité ; Autre : texte libre"`. Un agent peut aussi définir les mots spécialisés
qu'il emploie : `"glossaire": [{"mot", "definition"}]` (60 et 400 caractères au plus). Ils entrent dans le
**glossaire de la fonctionnalité** (un mot redéfini prend la définition la plus récente), qui est gardé par le suivi,
écrit dans `<pieces>/<fonctionnalité>/glossaire.md` (rangé dans ses documents), donné par `etat`, joint au message
de départ des agents de la fonctionnalité, et mis en valeur au bureau (définition au survol). `fonctionnalite` accepte
aussi `glossaire` (mêmes entrées). Rend `{"id": "m3"}`.

### `decision`

Entrée : `{"action": "poser", "portee", "genre", "texte", ...}` ou `{"action": "lever", "id"}`.
`{"action": "completer", "id", "doit_marcher"?, "pas_encore"?, "conclusion"?, "points_a_verifier"?, "nature"?, "mode_operatoire"?, "fichiers"?}` complète une
décision `valider_etape` encore posée (au moins un champ, validés comme à la pose : `doit_marcher` 480 caractères au
plus et non vide, `pas_encore` 480 au plus et peut être vide, `conclusion` 200 au plus ; `points_a_verifier` devient
`points`, 1 à 8 phrases différentes de 160 au plus ; `fichiers`, liste non vide de `{chemin, titre}`, remplace ce qu'il y
a à vérifier, par exemple les images d'un style au lieu d'un apk qui ne les montre pas encore) et ne touche à rien d'autre ; refusée pour une décision inconnue
ou levée, ou d'un autre genre. Les trois champs se posent aussi avec `poser` (`valider_etape`). `nature` (`en_jeu`,
`visuel`, `son`, `mecanique` ou `autre`) et `mode_operatoire` (2 à 10 textes non vides de 200 caractères au plus) sont validés de
la même façon, à la pose comme à la complétion, pour corriger une décision déjà posée. Rend `{"ok": true}`.
`portee` = l'id d'une fonctionnalité (`genre` : `valider_cahier`, `valider_methode`, `methode_a_revoir`,
`reprendre_methode`, `environnement` avec `environnement` (la liste des outils du poste qui manquent), `genre_fonctionnalite` avec `propose` (le genre proposé), `genres_connus`, `incertain` (vrai
quand le moteur hésite) et, facultatif, `nouveau` `{id, description}`) ou
`projet` (`confirmer_genre` avec `propose`, `genres_connus` et, facultatif, `fonctionnalite` (celle qui attend ce
genre), `session_cloud` avec `agent`, `outil_agent` (un agent est arrêté faute d'un outil que sa fiche ne lui ouvre pas et le moteur ne peut pas l'ouvrir seul : `agent` (clé), `tache`, `outil`, et facultatifs `programme` (le programme du shell à ouvrir, d'après la commande refusée) et `commande` (la commande refusée, une ligne, coupée, valeurs secrètes masquées) ; le Directeur répond « Autoriser ce programme pour cet agent » ou « Refuser » : seul le moteur procédural pose cette décision et y répond), `accord_agent` (un agent demande l'accord de l'utilisateur : `agent` (clé), `tache`, `quoi`, et facultatifs `partenaire`, `cout`, `pourquoi`, `implique`, `regle` (rappel de la règle du projet), `appareil` (vrai : installation ou test sur un appareil physique), `regle_proposee` (le texte que la case « Retenir comme règle du projet » propose, 500 caractères au plus) `choix` (les choix que l'agent a proposés avec sa demande, 1 à 6 textes de 120 caractères au plus : le bureau les montre comme boutons) et `regles_touchees` (les règles du projet que la demande touche, `[{id, texte}]`, 3 au plus) ; « J'accepte » ou « Je refuse » avec une consigne : seul le moteur procédural pose cette décision et y répond), `elargir_genre` (élargir la description d'un genre gardé : `cible` le genre, `ancienne`, `propose`, `fonctionnalite` la demande qui l'a provoquée), `valider_etape` (un élément attend le Directeur à une étape de validation : `fonctionnalite`, `element` `{id, nom}`, `etape`, `tache`, `compte_rendu`, `fichiers`, et facultatifs `objectif` (ce que l'élément devait produire) et `a_valider` (le nom de l'étape, et sa raison), 600 caractères au plus, `points` (les points à vérifier de la fenêtre de validation : 1 à 8 phrases différentes de 160 caractères au plus) et `acces` `{url (http ou https), description? (200 au plus)}` ; un fichier image est rangé comme les autres images d'agent, un livrable téléchargeable (apk, zip, pdf, exe…) trouvé dans le projet reçoit `taille` et `date`, son chemin compté depuis la factory ou, hors de `.factory`, depuis le dossier du projet), `environnement` avec `environnement` (comme pour une fonctionnalité : l'installation portée par le projet, à sa création, a échoué) ou `organisation` avec `organisation`). Une décision `organisation` porte `{"services": [{id, nom}] (la liste complète après changement),
"flux": [{id, nom, role, service}] (complet), "agents": [fiches] (les nouveaux seulement), "briefs": {rôle: texte}
(nouveaux rôles), "cout": {"tokens": [a, b], "euros": [a, b] | null}}` ; elle est contrôlée comme une proposition
(Fable refusé, clés et rôles, briefs). Quand elle propose le workflow d'une fonctionnalité, elle porte aussi
`"fonctionnalite"` (son id), `"workflow": {"id", "genre", "flux", "genre_nouveau"?: {"description"}}` (le `flux` est celui
de l'organisation : des étapes `<fonctionnalité>-<étape>`, uniques dans le projet), `"livrable"`, `"environnement"`
(les outils du poste) et `"outils_installation"` ; ses agents portent `justification` et, facultatif,
`fable_suggere`. Poser deux fois la
même décision rend la même. Rend `{"id": "d2"}` ou `{"ok": true}`.

### `tache`

Entrée : sans `id`, une création (`titre` obligatoire) ; avec `id`, une mise à jour. Champs : `titre`,
`fonctionnalite`, `element`, `role`, `colonne`, `agent`, `etape`, `modele_depart`, `montee` (`{de, a, raison}`),
`journal` (un texte, ou une liste, ajoutés), `bloquee`, `active`, `captures` (chemins, ou `{chemin, legende}`), `lignes` (les lignes produites
par la tâche, son total : l'échelle de son coût au bureau), `depend_de` (liste d'identifiants de tâches connues : ce
que la tâche attend ; refus d'une tâche inconnue, d'elle-même ou d'un cycle), `lot` (`{"id": "L2", "rang": 3}` ou
`null` : le lot de la tâche et son rang), `partenaires` (ids du catalogue des partenaires que la tâche appelle : le
départ donne leurs règles ; refus d'un id inconnu). L'outil note `debut` au passage à `active: true` et `fin` au passage à
`active: false` (ils servent à répartir le coût d'un lot). Un agent ne tient qu'une
tâche active à la fois ; passer dans `fait` rend la tâche inactive ; `Fable` est refusé (quelle que soit la casse)
en `modele_depart` comme en `montee` ; une `montee` va d'un cran exactement (Haiku → Sonnet → Opus). Rend la tâche.

### `organisation`

Entrée : `{"action": "appliquer", "decision": id, "fable"?: [clés d'agents]}`, pour une décision `organisation` du
projet que l'utilisateur a acceptée (demande `organisation`, `verdict` : `accepter` ou `refuser`, version 4). Réécrit
`services` et `flux` du fichier de factory (le reste est gardé), crée les fiches et les briefs nouveaux (un brief
existant est gardé), lève la décision. Pour le workflow d'une fonctionnalité, le `flux` du projet n'est pas touché :
le workflow s'ajoute à `workflows`, la fonctionnalité prend son `genre` et son `workflow`, les outils du poste sont
notés (`environnement`), et un genre nouveau est créé dans la mémoire de la skill (en dernier : un échec est dit dans
`genre_raison`, il ne bloque rien). `fable` : les agents que le Directeur a cochés ; ils doivent avoir été suggérés
(`fable_suggere`), et leur fiche porte alors `Fable : accordé par le Directeur le <date>`. Rend `{"ok": true,
"services": [...], "flux": [...]}` (et, pour un workflow, `workflow`, `fonctionnalite`, `genre`, `genre_raison`?).
Refus (code 1) si la décision est inconnue ou n'est
pas de ce genre, ou si son contenu ne passe plus le contrôle (le projet a changé) : rien n'est écrit, la décision reste.
Entrée `{"action": "environnement", "outils": [{outil, etat: en_place | a_installer, chemin?, version?, …}]}` : note l'état
des outils du poste dans le fichier de factory (clé `environnement` ; un outil de même nom est remplacé). Chaque outil
peut porter `objectif`, `telechargement` (URL https officielle ou nul), `etapes` (mode opératoire) et `autonome` ; un outil
que le Directeur a forcé porte `declare: true` et `note` (« déclaré installé par le Directeur (non vérifié) ») : le message
de départ des agents le dit, et le moteur ne le revérifie pas.
Entrée `{"action": "verifier", "id": décision, "outils": [{outil, etat, verification: {trouve, cherche, introuvables,
version_demandee, version_trouvee}, chemin?, version?, raison?, declare?, note?}]}` (sous la commande `decision`, avec
`poser` et `lever`) : note dans une décision `environnement` le résultat de la dernière vérification de chaque outil nommé,
et l'heure (`verifie_le`) ; les autres outils sont gardés. Refus si la décision est inconnue, d'un autre genre, ou si un outil
n'y est pas.
La réponse « C'est fait » à une décision `environnement` est une demande `environnement` : `verdict` `fait` (le moteur
revérifie en code chaque outil de la décision, le `PATH` à jour du registre Windows compris ; tout trouvé, la décision est
levée ; sinon elle reste, chaque outil marqué trouvé ou non trouvé), `continuer`, ou `forcer` (avec `outil` : un outil non
trouvé ; sans lui, tous) : le Directeur affirme que c'est installé, l'outil est noté déclaré (non vérifié) et la décision levée
s'il ne reste rien à trouver. Seul le moteur la traite.
Entrée `{"action": "installateur", "agent": {cle, role: environnement, service, modele, lieu, texte, outils?}, "brief"}` :
recrute l'agent qui installe les outils du poste (rien si un agent de ce rôle existe ; jamais Fable) ; c'est ce que fait
le moteur au clic « Installer en autonomie » quand le projet n'en a pas encore.
Le clic « Installer en autonomie » arrive au projet comme une demande `installer_outil` (`decision`, `outil`, `fonctionnalite`?) : jamais d'installation sans ce clic, un outil à la fois ; seul le moteur la traite.
Entrée `{"action": "reprendre", "fonctionnalite": fid, "workflow": id}` : la fonctionnalité suit un workflow de genre du
projet (défini à la création, sans fonctionnalité, ni le principal) : sa copie `w-<fid>` (étapes préfixées `<fid>-`) est
ajoutée, sans service, agent ni brief nouveau, et la fonctionnalité prend son `genre` et son `workflow`. Rend
`{"ok": true, "workflow": "w-<fid>"}`. Refus si le workflow n'est pas un workflow de genre du projet, si la
fonctionnalité est inconnue ou a déjà un workflow, ou si le contrôle de l'organisation échoue (rien n'est écrit).

### `file`

Entrée : `{"fonctionnalite", "elements": [{"id", "nom", "groupe"?, "objectif"?, "validations"?}]}`. Remplace la file
des éléments à faire de la fonctionnalité. `objectif` (300 caractères au plus) : ce que l'élément doit produire, rappelé
à sa validation ; `validations` : les `id` des étapes de validation du Directeur qui le concernent (absent : toutes ;
un élément non concerné passe l'étape sans arrêt, mais attend que la validation soit franchie). Rend `{"elements": n}`.

### `file-prendre`

Entrée : `{"fonctionnalite", "element"?}`. Retire de la file et rend `{"element": {id, nom, groupe?}}` : l'élément
suivant, ou celui dont l'identifiant est `element` (code 1 s'il n'est pas dans la file) ; `{"element": null}` si la
file est vide.

### `usage`

Entrée : `{"modele", "agent"?, "tache"?, "etape"?, "entree", "sortie", "cache_lecture"?, "cache_ecriture"?, "id"?}`, ou
**`agent_id`** (l'identifiant d'un sous-agent) à la place des compteurs et du `modele` : l'outil lit les compteurs exacts
et le modèle dans sa transcription locale (`~/.claude/projects/*/*/subagents/agent-<id>.jsonl`, compteurs seulement,
jamais le contenu) ; ou `total` à la place de `entree` et `sortie` quand seul le total est connu (il compte alors comme
des tokens d'entrée, et le coût est une **estimation basse**). `reveil` note aussi la **gestion** : les tokens de la
conversation orchestratrice (une ligne cumulée par conversation et modèle, `etape: gestion`, sans tâche). Note les tokens d'une exécution d'agent ;
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

### `ecrire`

Entrée : `{"fonctionnalite", "nom", "texte", "titre"?, "agent"?, "etape"?, "tache"?, "element"?, "sous_tache"?}` ou
`{"brief": "<rôle>", "texte"}`. C'est le seul chemin par lequel le moteur écrit un texte du projet. Le premier écrit
`<pièces>/<fonctionnalité>/<nom>` (`nom` : un fichier `.md`) et, si `titre` est donné, l'inscrit dans les documents de la
fonctionnalité ; le second ajoute `texte` au brief du rôle (`<fiches>/briefs/<rôle>.md`, créé s'il manque ; un texte déjà
présent n'est pas ajouté deux fois). Rend `{"chemin": "…"}` (relatif au fichier de factory). Aucun autre dossier n'est
écrit.

### `memoire`

Entrée : `{"role"}`. Rend les leçons de la mémoire qui touchent ce rôle (ou « tous ») :
`{"genre_id": "…"|null, "skill": [leçon], "genre": [leçon]}`. Une leçon : `{id, titre, roles, date, texte}`. Un projet
sans genre ne reçoit que les leçons de la skill ; il ne reçoit **jamais** celles d'un autre genre.

### `genre`

Entrée : `{"action": "lister"}` → `{"genre": …, "genres": [{id, domaine, livrable, outils}]}`, ou
`{"action": "fixer", "genre", "description"?}` : écrit le genre dans le fichier de factory. Un genre inconnu demande
une `description` : son fichier de mémoire est alors créé, commité et poussé (rien n'est changé si cela échoue).
Rend `{"genre": "…", "cree": true|false}`.
`{"action": "decrire", "genre", "description"}` : élargit la description d'un genre existant, avec l'accord du Directeur (décision `elargir_genre`) ; même chemin git et mêmes contrôles de mot interdit que la création.

### `lecon`

Entrée : `{"action": "noter", "agent", "texte", "tache"?, "etage_propose", "texte_general"?, "roles"}` : note la
leçon sur la fiche de l'agent, « à valider » ; `etage_propose` vaut `projet`, `genre` ou `skill` ; pour `genre` et
`skill`, `texte_general` (le texte réécrit en termes généraux, sans nom de projet, de lieu, de fichier ni de
personne) est obligatoire. Rend `{"id": "<agent>:L1"}`.

Entrée : `{"action": "appliquer", "id", "verdict": "valider"|"invalider", "etage"?}` : le verdict de l'utilisateur.
`projet` : la leçon de la fiche passe « validée ». `genre` ou `skill` : le texte général est ajouté à la mémoire. Le
dépôt de la skill est celui où l'on développe : **ses autres fichiers modifiés ne bloquent jamais l'écriture**. Seul le
fichier de mémoire est commité (`git commit -- <fichier>` ; jamais `add -A`, pile ni `reset` sur le travail des autres).
Synchronisation : `git fetch` ; rien de neuf au distant, pas de pull ; du neuf et un arbre propre, `git pull --rebase` ;
du neuf et d'autres fichiers modifiés, pas de rebase : le commit reste local et sa publication est réessayée plus tard.
Issues :
- écrite et poussée : la leçon passe « validée » ;
- refusée (mot interdit, genre inconnu, **fichier de mémoire lui-même modifié et non commité** par une autre main) :
  code 1, la leçon reste « à valider » et porte la raison (`refus` dans le relevé) ;
- validée, écriture en attente (push refusé, distant injoignable, distant en avance avec un arbre modifié, `pull --rebase`
  en échec) : elle passe « validée » et **quitte la liste « à valider »** ; le suivi garde `ecriture` (`etat`
  `"en attente"`, `raison`, `depuis`, `essais`, `dernier_essai`, `commitee`). Rend alors
  `{"ok": true, "etage": …, "en_attente": true, "raison": "…"}`.

`invalider` : la leçon disparaît. Rend `{"ok": true, "etage": …}`.

Entrée : `{"action": "appliquer", "lot": [{"id", "verdict", "etage"?}, …]}` : plusieurs verdicts d'un coup (« Valider
toutes les leçons »), avec **une seule synchronisation et un seul push** pour tout le lot. Ne refuse jamais le lot pour
une leçon : rend `{"resultats": [{"id", "ok", "etage", "refus"?, "en_attente"?, "raison"?}]}`, un par verdict, dans
l'ordre (`ok` faux et `refus` : la leçon reste « à valider » ; `en_attente` : voir plus haut). Un même `id` deux fois dans
le lot : le second est refusé.

Entrée : `{"action": "reessayer"}` : reprend les leçons validées dont l'écriture est en attente (celles pas encore écrites,
avec une seule synchronisation ; celles seulement commitées en local, par un seul push). Sans leçon en attente, le dépôt
n'est pas touché. Rend `{"ecrites": n, "en_attente": restantes, "resultats": [{"id", "ok", "raison"}]}`. Le moteur
l'appelle seul toutes les 5 minutes (`ECRITURE_LECONS_TOUS_LES_S`), sans nouveau clic ; une leçon écrite cesse d'être
signalée. Un `pull --rebase` qui bute sur un conflit est abandonné (rien n'est laissé à moitié) et la raison est redite.

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
La limite des agents cloud est `agents_cloud_max` de la factory (de 0 à 16, 0 par défaut ; voir `parallelisme`) ; le
moteur procédural l'applique lui-même (une tâche active tenue par un agent cloud prend une place cloud).

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
chaque tâche (`lancer tache`) avant de passer à la suivante. Avec `"moteur": true` (le moteur procédural lance le
lot), aucune commande n'est demandée à l'agent : il rend un seul rapport à la fin du lot, le moteur tient le suivi.
Ce rapport porte aussi, pour chaque élément, son compte rendu à part (`comptes_rendus` : `[{element, texte, images?}]`) :
le Directeur ne voit, sous un élément à valider, que celui de cet élément.

**Avant une validation du Directeur** (fenêtre de validation) : la matière de l'étape qui précède une validation qui
concerne l'élément demande de quoi vérifier (captures légendées, le livrable dans `fichiers`, ou `acces`
`{url: "http://127.0.0.1:<port>/", description}` pour un site laissé en marche) et `points_a_verifier` : 3 à 8 phrases
de 160 caractères au plus, vérifiables par l'utilisateur, tirées du cahier (dans un lot : dans le compte rendu de
l'élément). Une forme fautive est écartée sans refuser le rapport ; sans points, le moteur en dérive de l'objectif.
Sans image, livrable téléchargeable existant ni lien d'accès, la décision n'est pas posée : l'étape est refaite une fois
avec la consigne d'ajouter de quoi vérifier, puis la tâche de validation est bloquée avec la raison.
Le même agent dit aussi ce que le Directeur doit juger, en trois champs (dans un lot : dans le compte rendu de
l'élément) : `doit_marcher` (1 à 3 phrases, 480 caractères au plus, obligatoire : ce qui doit fonctionner pour
valider), `pas_encore` (480 au plus, peut être vide : ce qui n'est pas encore attendu à ce stade) et `conclusion`
(une phrase, 200 au plus : « Validez si… »). Une forme fautive est écartée ; sans `doit_marcher`, même relance unique
(un seul compteur avec « rien à valider »), puis tâche bloquée avec la raison. Ils sont stockés sur la décision
`valider_etape`.
Il déclare aussi la `nature` de ce qu'il fait valider (rapport, ou compte rendu de l'élément dans un lot) et ne joint que
les preuves qui conviennent : `en_jeu` (à essayer dans le livrable exécutable) → le livrable téléchargeable (apk, exe, zip…)
ou le lien d'accès d'un site, et `mode_operatoire` (2 à 10 étapes courtes de 200 caractères au plus : installer, lancer, quoi
faire, quoi observer) ; `visuel` (images, sprites) → les images légendées (et les sons s'il y en a), jamais l'apk ; `son` (bruitages, musique) →
les fichiers audio (mp3, ogg, wav, flac), lus dans la fenêtre, jamais l'apk ; `mecanique` →
un document explicatif (md, pdf…) et, si utile, des schémas, jamais l'apk sauf si la mécanique est déjà jouable (alors
`en_jeu`) ; `autre` → de quoi juger, expliqué. Le moteur contrôle avant de poser la décision (même relance unique, même
compteur, puis blocage) : `en_jeu` sans livrable ni lien, ou sans mode opératoire ; `visuel` sans image ; `son` sans fichier audio ; `mecanique`
sans document. Un livrable exécutable joint à une validation `visuel`, `son` ou `mecanique` est retiré des fichiers montrés (ce
n'est pas une erreur). Une nature absente ou inconnue : comportement d'avant.

La demande `valider_etape` venue de la fenêtre porte `reponses` `[{point, ok}]` : `lancer actions` refuse (code 1) une
forme fautive ou un verdict qui n'en découle pas (tous OK = `valider`) ; le moteur vérifie en plus que les points sont
ceux de la décision. Validé : le texte libre est noté sur la tâche de validation et joint à la tâche suivante
(« Note du Directeur à la validation … ») ; renvoyé : « Remarque du Directeur : points à revoir : … ; … » suivie du texte.

### `parallelisme`

Entrée : `{"agents_locaux_max": 1 à 16, "agents_cloud_max": 0 à 16}` (entiers). Les **places** du projet, réglées par
le Directeur dans l'onglet Facturation (demande `parallelisme`) : écrites dans le fichier de factory, le reste du
fichier gardé. Rend les deux valeurs. Refus (code 1) hors bornes. Une place locale est soumise à la charge du poste,
une place cloud non ; chaque place est tenue par un agent recruté (une fiche, une tâche à la fois). Clé
`agents_cloud_max` absente : 0 pour un projet sans agent cloud, l'ancienne limite des réglages (`agents_cloud_max`,
3 par défaut) pour un projet qui en a ; le relevé publie la valeur effective en `agents_cloud_max`.

Le moteur procédural lance au plus (places locales libres sous la charge) + (places cloud libres) tâches prêtes ; les
tâches qui mènent à une validation du Directeur passent d'abord, et aucune tâche située après une étape de validation
pas encore franchie (un élément qu'elle concerne est encore avant elle ou en attente) ne démarre. Une installation
prioritaire et la pause restent au-dessus de tout. Des places libres sans tâche permise pendant qu'une validation
attend : `attente-places.json` dans `.factory` (« 2 places libres : en attente de votre validation « … » »).

### `fiche`

Entrée : `{"action": "ouvrir_outil", "cle", "outil"}`. Ajoute `outil` à la ligne « Outils : » de la fiche de l'agent `cle` ;
sans cette ligne, elle est créée avec les outils par défaut (`Read`, `Write`, `Edit`, `Glob`, `Grep`, `Bash(py:*)`,
`Bash(python:*)`, `Bash(python3:*)`, `Bash(mkdir:*)`, `Bash(git:*)`) plus la règle. Seule une règle `Bash(<programme>:*)`
(un nom de programme : lettres, chiffres, point, tiret) s'ouvre ainsi ; `Bash` seul, une autre forme ou un agent inconnu
est refusé (code 1). Rend `{"ok": true, "deja": <vrai si la fiche l'ouvrait déjà>, "outils": [...]}`. C'est la commande du
moteur quand un agent est arrêté faute d'outil (voir la décision `outil_agent`) : il lit la commande refusée dans la sortie
de `claude -p` et n'ouvre que le programme d'un exécutable déclaré dans l'environnement du projet ou un outil de base des
agents ; tout autre cas est une décision.

### `recruter`

Entrée : `{"mode": "manuel" | "auto", "agents": [{"role", "modele", "lieu", "fable"?}]}` (un agent en manuel, 1 à 16
en auto ; demande `recruter` du bureau). Écrit une fiche par recrue, tout ou rien : clé `<rôle>-<n>` libre, le prénom
libre suivant de l'équipe, le service, le texte, la spécialité et les outils d'une fiche du même rôle (sinon le service
de l'étape), le même brief (`briefs/<rôle>.md`, exigé). Refus (code 1) : rôle hors des étapes d'agent des workflows,
modèle hors Haiku/Sonnet/Opus (Fable seulement en manuel avec `fable: true`, la fiche porte alors « accordé par le
Directeur le … »), cloud sans dépôt GitHub (origine `origin` sur github.com, lue dans `.git/config`) ou au-delà des
places cloud sans agent (`agents_cloud_max` effectif moins les agents cloud), auto au-delà des places locales sans agent
(`agents_locaux_max` moins les agents locaux, chef exclu). Rend `{"ok": true, "agents": [{cle, prenom, role, modele,
lieu}]}`. Le relevé publie `recrutement` (rôles, places, dépôt, répartition automatique proposée, sans appel d'IA).

Après le recrutement d'un agent cloud, tout est automatique tant que le projet est sur GitHub et que `claude` est
installé et connecté : quand une tâche de son rôle part, le moteur pousse, lance `claude --cloud`, relève le rapport
par le dépôt et fusionne. Si le lancement échoue deux fois, la tâche est bloquée et le moteur pose la décision
`session_cloud` (« Sessions cloud à créer ») avec la démarche ; « C'est fait » inscrit la session et remet en route
les tâches de cet agent bloquées faute de session.

### `depot`

Entrée : `{"action": "creer", "confirme": true}` (demande `depot_git` : le clic « Créer le dépôt Git » du Directeur,
jamais sans lui). Règle le `.gitignore` (convention de l'installation : `.env` et les fichiers propres au poste restent
hors du dépôt, `.factory` est versionné), crée le dépôt git local si besoin (premier commit, ou un commit de ce qui
n'est pas encore commité), puis le dépôt GitHub **privé** avec `gh repo create <nom> --private --source . --push`.
Une origine existante n'est jamais remplacée. Rend `{"fait", "url", "texte"}` (le lien, ou la raison : gh absent, gh
non connecté — « gh auth login » —, git absent, commit refusé) ; noté dans `depot-git.json` (relevé : `recrutement.depot.essai`).

### `regles`

Entrée : `{"action": "lister" | "ajouter" | "modifier" | "supprimer", …}`. Les règles du projet
(`.factory/regles-projet.json`, à côté du fichier de factory) : `[{id, texte, cree_le, modifie_le?, origine?}]`. Seul
écrivain du fichier. `ajouter` : `texte` (1 à 500 caractères, espaces resserrés) et facultativement `origine`
`{decision, agent}` ; rend `{regle, deja}` (`deja` vrai : le même texte existait, rien n'est ajouté) ; 40 règles au plus.
`modifier` : `id`, `texte`. `supprimer` : `id`. `lister` rend `{regles}`. Un texte vide ou trop long, une règle inconnue ou
une `action` inconnue est refusé. Les règles sont aussi au relevé (`regles_projet`), en tête de chaque message de
`depart` (« Règles du projet, à respecter : ») et dans le dossier du jugement `proposer_organisation`. Le bureau les
demande par `regle_projet` ; le moteur procédural y répond, la conversation orchestratrice ne les touche pas.

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
