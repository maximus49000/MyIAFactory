# Le relevé : le contrat entre un projet et le bureau

Le bureau ne connaît aucun projet. Chaque projet lui fournit un **relevé** : un document JSON qui dit les faits bruts. Le bureau en déduit tout le reste (prénoms, statuts, charge de l'ordinateur).

## Deux façons de fournir le relevé

Dans le fichier de réglages du projet (par exemple `reglages.json`), la clé `releve` désigne la source. Les chemins relatifs sont résolus depuis le dossier du fichier de réglages.

**Un fichier tenu à jour par le projet :**

```json
{"releve": {"fichier": "releve.json"}}
```

**Une commande que le bureau lance** (sans shell, 10 secondes au plus, le relevé est lu sur la sortie standard en UTF-8) :

```json
{"releve": {"commande": ["python", "mon_releve.py"], "dossier": "."}}
```

Au-delà de 10 secondes, le bureau arrête la commande et tous les processus qu'elle a lancés, et affiche « La commande du relevé a dépassé 10 s ». La sortie doit être en UTF-8 (un BOM en tête est accepté, comme pour les fichiers). Sous Windows, un script PowerShell écrit par défaut dans la page de codes de la console : commencez-le par `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`. En Python, `sys.stdout.reconfigure(encoding="utf-8")`.

> **Écrivez le fichier par remplacement atomique** : écrivez dans un fichier temporaire du même dossier, puis renommez-le sur `releve.json`. Le bureau relit le fichier toutes les quelques secondes ; un fichier écrit à moitié est refusé (le bureau garde alors sa dernière scène et affiche un bandeau), mais un remplacement atomique évite même cela.

## Les champs

| Champ | Obligatoire | Valeurs |
|---|---|---|
| `version` | oui | `1`, `2` ou `3` (la version 2 ajoute les champs marqués « v2 » ci-dessous, la version 3 ceux de « Version 3 : les dossiers des services » ; un relevé version 1 ou 2 marche toujours, sans eux) |
| `projet` | oui | nom affiché |
| `factory.etat` | oui | `"en marche"` ou `"en pause"` |
| `factory.depuis` | non | date ISO 8601 |
| `services` | oui | liste de `{id, nom}` ; **8 au plus**, identifiants uniques |
| `colonnes` | oui | liste de `{id, nom}` dans l'ordre du Kanban ; à partir de la v2, `terminee` (vrai/faux, facultatif, `null` = absent) marque une colonne terminée (voir ci-dessous) |
| `titulaires` | oui | voir ci-dessous |
| `taches` | oui | voir ci-dessous |
| `file` | non | `{"visibles": [{id, titre}], "reste": n}` — vide par défaut ; en v2, `suite` facultatif (voir ci-dessous) |
| `decisions` | non | nombre de décisions qui attendent le Directeur — `0` par défaut |
| `actions` | non, v2 | les boutons de la factory (voir « Faire agir le bureau ») |
| `types` | non, v2 | liste de `{id, nom}` : les types de tâches, pour le filtre de la vue liste |
| `lecons` | non, v2 | les leçons **à valider** : liste de `{id, agent, texte, tache?, date?, verdict_demande?}` ; `id` unique, `agent` = clé d'un titulaire, `verdict_demande` = `"valider"` ou `"invalider"` (verdict envoyé, pas encore appliqué : le bureau affiche « Verdict envoyé ») |

**Titulaire** (un agent) : `cle` (stable, unique), `lieu` (`"local"` ou `"cloud"`) et `service` (sauf pour le chef) sont obligatoires. Facultatifs : `modele` (`"?"` par défaut), `permanent` (ne quitte jamais le bureau), `chef` (le chef d'atelier ; un seul au plus, le bureau en ajoute un de clé `"chef"` s'il n'y en a aucun), `fraicheur_min` (délai de fraîcheur propre à cet agent, pour les travaux longs et silencieux).

Facultatifs à partir de la version 2 : `prenom` (remplace le prénom tiré par le bureau, sans être écrit dans `equipe.json`, et tant que le relevé le donne : il l'emporte sur celui du fichier), `specialite` (texte) et `lecons` (liste de `{id, texte, etat}`, `etat` valant `"à valider"` ou `"validée"`).

**Tâche** : `id` (unique), `titre`, `colonne` (connue) et `active` (vrai/faux) sont obligatoires. Facultatifs : `titulaire` (clé connue, ou nul), `etape` (texte en clair), `maj` (date de dernière mise à jour), `postit` (vrai par défaut ; faux = pas de post-it sur le Kanban).

Facultatifs à partir de la version 2, pour le détail d'une tâche :

| Champ | Valeurs |
|---|---|
| `type` | identifiant d'un type de `types` (s'il y en a) |
| `journal` | liste de `{t, texte}` ; le plus récent est montré en premier |
| `images` | liste de `{chemin, legende?}` ; **40 au plus** ; voir « Les images » |
| `liens` | liste de `{libelle, url}` ; schémas `https`, `http` ou `claude` (ce dernier ouvre l'application Claude de bureau) ; ouverts dans un nouvel onglet |
| `retours` | liste de `{t, texte, reponse?, etat?}` (`etat` : mot court affiché à côté de la date, par exemple « nouveau » ou « pris en compte ») ; un retour sans `reponse` est « en attente de réponse » et compte pour le Directeur |
| `notes` | liste de `{libelle, texte}` (deux textes non vides) : notes libres, montrées sous l'étape ; le texte peut avoir plusieurs lignes |
| `bloquee` | texte : la raison, si la tâche attend une décision (compte pour le Directeur) |

Un champ facultatif de mauvais type (par exemple un `journal` qui n'est pas une liste, ou un lien `javascript:`) rend tout le relevé invalide : le bandeau « Relevé invalide » nomme le champ, et la scène garde sa dernière image. Un champ facultatif à `null` compte pour absent. En version 1, ces champs sont ignorés.

**Colonnes terminées.** En version 2, une colonne peut porter `"terminee": true`. Dès qu'au moins une colonne est terminée, la vue liste gagne un filtre « Non terminées » (toutes les tâches qui ne sont pas dans une colonne terminée, y compris celles en attente ou bloquées) : il est placé en premier et choisi par défaut, tant que l'utilisateur n'a pas choisi un autre filtre. Le filtre « En cours » (tâches `active`) ne change pas. Sans colonne terminée, ce filtre n'existe pas.

**File dépliable.** En version 2, `file.suite` (facultatif, `null` = absent) est la liste `{id, titre}` des éléments qui viennent après les `visibles` : **500 au plus**, mêmes règles que `visibles`. Les identifiants sont uniques entre `visibles`, `suite` et `taches` : en version 2, un `id` de `file.visibles` ou de `file.suite` identique à celui d'une tâche (ou d'un autre élément de la file) rend le relevé invalide (retirez l'élément de la file dès qu'il devient une tâche). `reste` garde son sens : le nombre total d'éléments au-delà des visibles ; `suite` peut être plus courte que `reste` (la page dit alors combien d'éléments elle ne détaille pas). Quand il y a quelque chose au-delà des visibles, le « + n » de la file sur le Kanban (et le bouton « File d'attente » de la vue liste) ouvre un panneau « File » qui liste tous les éléments, chacun avec « Déplacer vers… » comme les éléments visibles.

## Version 3 : les dossiers des services

En version 3, cliquer un service ouvre son **dossier** : quatre onglets (Tâches, Connaissances, KPI, Facturation) et un sélecteur de période (aujourd'hui, 7 jours, 30 jours). Tout ce qui suit est **facultatif** : un onglet dont le relevé ne donne pas la matière n'est pas montré (Tâches est toujours là). En version 1 et 2, ces champs sont ignorés et le dossier se réduit à l'onglet Tâches.

| Champ | Où | Sert à |
|---|---|---|
| `usage` | racine | la facturation : les tokens consommés, discussion par discussion |
| `kpi` | chaque service | l'onglet KPI et les alertes |
| `connaissances` | chaque titulaire | l'onglet Connaissances |
| `challenges` | racine | les challenges ouverts et leurs solutions |

### L'usage (la facturation)

Le bureau ne compte pas les tokens : le projet les donne, bruts, et le bureau les convertit en euros **estimés** (toujours affichés avec « ≈ » : ce n'est pas une facture).

`usage` : liste (**5 000 entrées au plus**) de `{id, tache, agent, modele, etape?, t, entree, sortie, cache_lecture?, cache_ecriture?}`, une entrée par discussion.

| Champ | Valeurs |
|---|---|
| `id` | texte non vide, unique dans `usage` |
| `tache` | `id` d'une tâche **présente dans ce relevé**, ou `null` (« hors tâche ») |
| `agent` | clé d'un titulaire **présent dans ce relevé**, ou `null` ; l'usage du chef, ou un usage sans agent, est rangé dans « direction / hors service » |
| `modele` | le nom du modèle, tel que le projet l'écrit (voir `alias_modeles` dans [installation.md](installation.md)) |
| `etape` | texte libre : l'étape de la tâche (« Tests », « Maquette »…) |
| `t` | date ISO 8601 de la discussion |
| `entree`, `sortie` | tokens, entiers ≥ 0 |
| `cache_lecture`, `cache_ecriture` | tokens de cache, entiers ≥ 0 (0 par défaut) |

- Les compteurs d'un `id` sont des **cumuls** : republiez le même `id` avec des compteurs plus grands tant que la discussion continue, le bureau garde les derniers. Ne changez pas d'`id` en cours de discussion (elle serait comptée deux fois).
- Le relevé n'a besoin de porter que les usages **récents** : le bureau les range dans son historique (`usage-historique.jsonl`, à côté des réglages) et ne les oublie pas quand le projet les retire. Quand une tâche ou un agent quitte le relevé, retirez aussi ses usages : un usage qui cite une tâche ou un agent absent rend tout le relevé invalide.
- La **date de prix** d'un usage (son `t` à la première apparition) et son **service** (celui de l'agent à ce moment-là) sont figés : un coût passé ne bouge ni quand un prix change, ni quand l'agent change de service ou quitte le relevé.
- Un modèle dont le bureau ne connaît pas le prix n'est jamais compté à zéro : la discussion est montrée avec ses tokens et « prix inconnu », elle est exclue des euros, et les chiffres qui en dépendent le disent (« ≈ 3,00 € + prix inconnu », coût moyen « hors prix inconnus »).

Le bureau en tire aussi des **sources d'amélioration** (onglet Facturation) : les tâches qui coûtent plus de trois fois la médiane du service, une étape faite avec le modèle le plus cher du service quand les autres usages de cette étape sont en médiane moins chers, et la part du coût des tâches qui ont reçu au moins deux `retours`.

### Les KPI

Par service, `kpi` : liste de `{id, nom, valeur, unite?, evolution?, alerte?, texte?, periodes?}`. La liste est ouverte : ajoutez les vôtres, le bureau les montre tels quels.

| Champ | Valeurs |
|---|---|
| `id` | texte non vide, unique **dans le service** |
| `nom` | texte affiché |
| `valeur` | nombre ou texte |
| `unite`, `evolution` | textes courts affichés tels quels (« défauts », « +2 depuis hier ») |
| `alerte` | vrai si votre projet juge le seuil franchi ; `texte` explique alors pourquoi |
| `periodes` | `{"aujourdhui": v, "7j": v, "30j": v}` : la valeur suit le sélecteur de période ; sans `periodes`, le KPI est marqué « toutes périodes » |

Le bureau ajoute ceux qu'il sait calculer sur la période : tâches terminées (tâches du service dans une colonne `terminee` dont `maj` tombe dans la période), allers-retours moyens (nombre de `retours` par tâche), durée moyenne d'une tâche (de la première à la dernière entrée de son `journal`), coût moyen par tâche (d'après `usage`). Un chiffre sans donnée n'est pas montré. Si vous donnez un KPI avec le même `id` qu'un calculé (`taches_terminees`, `allers_retours`, `duree_tache`, `cout_moyen`), le vôtre le remplace.

Un KPI en alerte est rappelé en haut de l'onglet Tâches, avec un bouton « Challenger ».

### Les connaissances

Par titulaire, `connaissances` : liste de `{id, texte, date?, origine?, appris_de?}`. Les leçons **validées** du titulaire (`lecons`, version 2) sont montrées avec elles.

| Champ | Valeurs |
|---|---|
| `id` | texte non vide, unique parmi **toutes** les connaissances du relevé (une connaissance partagée a donc un `id` par agent qui la reçoit) |
| `texte` | la connaissance |
| `date` | date ISO (`2026-11-08`, ou avec l'heure) |
| `origine` | texte libre, ou l'`id` du challenge qui l'a produite (voir « Problème revenu ») |
| `appris_de` | liste de `{agent, tache?, retour?}` : l'agent dont le retour est la source (clé d'un titulaire, de n'importe quel service), la tâche, la date du retour |

Une connaissance qui porte `appris_de` est marquée « partagée » : « appris du retour de Hugo sur *Export CSV* ». L'onglet Connaissances d'un service montre aussi ce que ses agents ont reçu d'un autre service, et signale les agents qui n'ont rien reçu sur la période. C'est votre projet qui organise le partage ; le bureau le rend visible.

### Les challenges

`challenges` : liste de `{id, cible, texte, date?, solutions?}`.

| Champ | Valeurs |
|---|---|
| `id` | texte non vide, unique parmi les challenges |
| `cible` | `{type, id}` ; `type` : `"kpi"`, `"connaissance"` ou `"source"` ; `id` : celui que la demande `challenge` vous a donné, recopié tel quel |
| `texte` | le problème, en clair |
| `solutions` | liste de `{id, texte, auteur, etat?}` ; `id` unique parmi les solutions de **tous** les challenges ; `auteur` : `"directeur"`, `"service"` ou `"utilisateur"` ; `etat` : mot court (« proposée », « validée », « écartée » ; une solution validée ou écartée n'a plus de case à cocher). Gardez un challenge dans le relevé tant qu'il doit rester visible : l'onglet Tâches du service les liste tous |

**Les identifiants de cible.** Une cible `connaissance` porte l'`id` de la connaissance (ou de la leçon validée). Une cible `kpi` porte **`kpi:<service>:<id du KPI>`**, pour les KPI calculés comme pour les vôtres (les `id` de KPI ne sont uniques que par service) : pour votre KPI `defauts` du service `dev`, la demande dit `kpi:dev:defauts`. Une cible `source` porte `source:<service>:<genre>:<tâche>`, `genre` valant `tache_chere`, `modele_trop_fort` ou `allers_retours`.

**Le cycle.** L'utilisateur clique « Challenger » (demande `challenge`) ; votre projet ajoute le challenge au relevé et y dépose les solutions du Directeur et du service ; l'utilisateur peut ajouter la sienne (demande `solution`), puis coche et valide ou écarte (une demande `verdict_solution` par solution cochée). Sur `"valider"`, votre projet inscrit la solution dans les `connaissances` des agents concernés, avec `origine` = l'`id` du challenge ; sur `"ecarter"`, il la marque écartée (`etat`). Le bureau n'invente jamais une solution et n'écrit jamais une connaissance.

**Problème revenu.** Si une connaissance a pour `origine` l'`id` d'un challenge dont la cible est un KPI de votre projet, et que ce KPI entre de nouveau en alerte **après** la date de la connaissance, le bureau la marque « problème revenu ». Il lui faut donc quatre choses : `origine` = `id` du challenge, ce challenge toujours présent dans `challenges`, une `date` sur la connaissance, et un KPI dont `alerte` repasse à faux quand le problème cesse. Le bureau note chaque entrée en alerte dans `alertes-historique.jsonl`, à côté des réglages, à la date où il la lit : une alerte apparue et disparue pendant que le bureau était arrêté n'est pas vue.

## Version 4 : le parcours d'une tâche

En version 4, le relevé montre **les fonctionnalités** du projet, chacune avec son étape et sa discussion de
cadrage, et ce qui attend l'utilisateur. Tout est **facultatif** ; en version 1, 2 et 3, ces champs sont ignorés.

| Champ | Où | Sens |
|---|---|---|
| `genre` | racine | l'identifiant du genre du projet (`^[a-z0-9][a-z0-9-]{0,39}$`), ou `null` s'il n'est pas encore choisi |
| `livrable` | racine | le dernier livrable du projet : `{libelle, lien \| chemin, date}` (le bouton « Dernier livrable ») |
| `fonctionnalites` | racine | la liste des fonctionnalités (ci-dessous), 100 au plus |
| `decisions_projet` | racine | ce qui attend l'utilisateur pour le projet : `{id, genre, texte, ...}` avec `genre` = `confirmer_genre` (plus `propose` et `genres_connus`) ou `session_cloud` (plus `agent`, la clé du titulaire qui attend sa session) |
| `fonctionnalite`, `element` | chaque tâche | la fonctionnalité et l'élément du catalogue de la tâche |
| `modele_depart`, `montee` | chaque tâche | le modèle de départ et une montée de modèle `{de, a, raison}` (montrée dans le panneau de la tâche) |
| `etage_propose`, `texte_general`, `roles` | chaque leçon | l'étage proposé (`projet`, `genre` ou `skill`), le texte réécrit en termes généraux (obligatoire si l'étage n'est pas `projet`), les rôles concernés |

**Une fonctionnalité** : `id`, `nom`, `etape` (`cadrage`, `cahier`, `decoupage`, `prototype`, `methode`, `serie` ou
`terminee`), et facultativement :
- `agent_cadrage` (clé d'un titulaire) ; `discussion` : `[{id, t, auteur, texte, images?}]`, du plus ancien au plus
  récent, 1 000 messages au plus, `auteur` = `utilisateur` ou la clé d'un titulaire, `images` = chemins (règles des
  images) ; `attend_reponse` (vrai ou faux) ;
- `cahier` : `{maquette: [chemins d'images], etapes: [textes], valide_le?}` ;
- `methode` : `{version, lien | chemin, validee_le?}` ;
- `livrable` : `{libelle, lien | chemin, date}` ;
- `catalogue` : vrai si le projet fournit un catalogue pour cette fonctionnalité (bouton « Catalogue ») ;
- `decisions` : `[{id, genre, texte}]` avec `genre` = `valider_cahier`, `valider_methode` ou `methode_a_revoir` ;
- `glossaire` : le vocabulaire de la fonctionnalité, `[{mot, definition}]` (500 mots au plus ; mot : 60 caractères,
  définition : 400) ; un message peut aussi porter son `glossaire`, et des `questions` à choix
  (`[{texte, choix: [2 à 12], multiple?}]`, 10 au plus) : le bureau met les mots en valeur (définition au survol) et
  montre un bouton par choix, « Autre » et « Passer » ;
- `documents` : les fichiers produits pour la fonctionnalité, 2 000 au plus, chacun `{chemin, titre}` et, facultatifs,
  d'où il vient : `agent`, `etape`, `tache`, `element`, `sous_tache`, `date` (textes). Le panneau de la fonctionnalité
  les range par étape ; le bureau les sert par `GET /api/document?fonctionnalite=…&chemin=…`, seulement s'ils sont
  listés ici et dans une des racines de `{"documents": {"racines": [...]}}` des réglages. Images, PDF et paquets
  comme un livrable ; `.md`, `.json`, `.csv`, `.txt`, `.html` et `.svg` en bac à sable (sans script).

Les identifiants de décisions sont uniques dans tout le relevé. La pastille d'un projet dans le sélecteur compte
`decisions`, les décisions des fonctionnalités et celles du projet. Pendant que `attend_reponse` est vrai, la page
écrit « <prénom> est en train d'écrire… » si l'orchestrateur tourne (la bulle du chef est fraîche), sinon « En attente
de l'orchestrateur ».

**Le dernier livrable** : un `lien` (`https`, `http` ou `claude`) est ouvert tel quel ; un `chemin` est servi par le
bureau s'il est dans une des racines de `livrables` des réglages (`{"livrables": {"racines": ["livrables"]}}`),
avec l'extension `.html`, `.txt`, `.png`, `.jpg`, `.jpeg`, `.pdf`, `.zip` ou `.glb`. Un `.html` ou un `.txt` est
servi **en bac à sable** (sans script) ; un `.zip` ou un `.glb` est téléchargé.

### Le catalogue d'une fonctionnalité

Le bureau ne le lit qu'à l'ouverture (bouton « Catalogue », ou le menu « Dernier livrable »), pas à chaque relevé.
Déclarez sa source dans les réglages, ou dans le fichier de factory que les réglages désignent par
`"orchestrateur"` :

```json
{"catalogues": {"magasin": {"fichier": "catalogue-magasin.json"},
                "*": {"commande": ["python", "mon_catalogue.py", "{fonctionnalite}"], "dossier": "."}}}
```

`"*"` vaut pour toutes les fonctionnalités qui n'ont pas de déclaration à elles ; `{fonctionnalite}` y est remplacé
par l'identifiant (lettres, chiffres, `-` et `_`). Une commande a 10 s pour écrire le catalogue en JSON UTF-8 ; son
résultat est gardé 30 s. Format (tout est facultatif sauf `id` et `nom` d'un élément ; 20 000 éléments au plus) :

- `groupes` : `[{id, nom}]` ; `passes` : `[{numero, date, titre}]` (les versions de la méthode) ;
  `lecons` : `[{id, titre, texte, portee, passe}]` ; `kit` : `[{id, nom, description}]` (les éléments communs) ;
  `trace` : `[{nom, points: [[x, y], …]}]` (des lignes sur la vue de haut) ;
- `elements` : chacun `{id, nom, groupe, etat, note, caracteristiques: [{libelle, valeur}], captures: [{chemin,
  passe}], comparaisons: [{angle, reel, produit, credit, lien}], liens: [{libelle, url}], kit: [ids], evenement,
  lecons_appliquees: [ids], a_reevaluer: [ids], doute: {date, raison, leve_par}, retours: [{t, texte, etat,
  reponse}], position: {x, y}, passes: [n]}`.

Les images (`captures`, `reel`, `produit`) suivent les règles des images ci-dessous. `etat` : `fait` (ou `valide`,
`termine`) pour un élément terminé, `a_faire` (ou `a_revoir`, `en_cours`) pour un élément à faire ; un élément avec
un `doute` est montré à part ; un autre état est montré comme « autre ». Les positions sont dans un repère où **y monte
vers le haut**. Un champ inconnu est ignoré ; un champ facultatif de mauvais type est retiré avec un avertissement
(montré en haut du catalogue) ; un `elements` illisible rend le catalogue indisponible. Une partie sans donnée n'est
pas montrée.

## Faire agir le bureau

Le bureau **n'agit jamais lui-même** sur la factory : chaque geste de l'utilisateur (un bouton, un déplacement de tâche, un retour, un verdict sur une leçon, un challenge) devient une **demande** remise à votre projet, par une commande d'actions que vous déclarez dans les réglages :

```json
{"actions": {"commande": ["python", "actions.py"], "dossier": "."}}
```

Le bureau lance cette commande (sans shell, 10 secondes au plus, dans `dossier`, relatif au dossier des réglages) **une demande à la fois**, avec la demande en JSON, en **UTF-8**, sur l'entrée standard. Code de sortie 0 : demande prise. Autre code, commande absente ou trop lente : la page affiche « Demande refusée : » suivi de la première ligne que la commande a écrite (200 caractères au plus). Sans `actions` dans les réglages, la page est en lecture seule : aucun bouton-demande, aucun menu, aucune zone de retour.

| `type` | Champs | Sens |
|---|---|---|
| `bouton` | `id` | l'utilisateur a cliqué un bouton-demande |
| `deplacer` | `tache`, `colonne` | passer une tâche (ou un élément de `file.visibles` ou de `file.suite`, par son `id`) dans cette colonne |
| `retour` | `tache`, `texte` (3 500 caractères au plus) | un retour de l'utilisateur sur une tâche |
| `lecon` | `id`, `verdict` (`"valider"` ou `"invalider"`), `etage?` | la décision du Directeur sur une leçon ; v4 : `etage` (`projet`, `genre` ou `skill`), absent s'il est celui proposé |
| `challenge` | `cible` (`{type, id}`), `texte?`, `solution?` | v3 : ouvrir un challenge sur cette cible ; `solution` : la solution que l'utilisateur écrit dans le même geste |
| `solution` | `challenge`, `texte` (3 500 caractères au plus) | v3 : l'utilisateur ajoute sa solution à un challenge du relevé |
| `verdict_solution` | `challenge`, `solution`, `verdict` (`"valider"` ou `"ecarter"`) | v3 : la décision de l'utilisateur sur une solution (« Valider la sélection » ou « Écarter la sélection » : une demande par solution cochée) |

**Les demandes de la version 4** (refusées sans lancer la commande si le relevé n'est pas en version 4) :

| `type` | Champs | Quand |
|---|---|---|
| `fonctionnalite` | `texte`, `images?` | « + Nouvelle fonctionnalité » : son premier message |
| `message` | `fonctionnalite`, `texte`, `images?` | un message de l'utilisateur dans la discussion |
| `cahier` | `fonctionnalite`, `verdict` (`valider` ou `corriger`), `texte?` | « Valider le cahier des charges » ou « Demander une correction » |
| `methode` | `fonctionnalite`, `verdict` (`valider`, `revoir` ou `garder`), `texte?` | valider la méthode ; « méthode à revoir ? » : Oui = `revoir`, Non = `garder` |
| `genre` | `decision`, `genre`, `description?` | le genre confirmé ou choisi ; `description` pour un nouveau genre |
| `session_cloud` | `decision`, `session` | « C'est fait » : la session cloud demandée est créée, avec ce nom |
| `retour_element` | `fonctionnalite`, `element`, `texte` | « Demander à modifier » dans le catalogue (l'élément doit y être) |

Textes : 3 500 caractères au plus. **Images jointes** : 4 au plus par demande, `{nom, type, donnees}` avec `donnees`
en base64, `type` = `image/png` ou `image/jpeg`, extension `.png`, `.jpg` ou `.jpeg` assortie, 5 Mo au plus une fois
décodée, contenu vérifié par sa signature, nom simple (ni dossier ni `..`). Le bureau ne les écrit nulle part : **votre
commande d'actions les range** dans le projet (et les commite, si un agent cloud doit les lire), puis le relevé les
montre par leur chemin. Un message envoyé reste affiché « en attente » tant que le relevé ne l'a pas repris ; un double
clic ne crée qu'une demande (une demande identique dans les 10 secondes est ignorée).

Chaque demande porte aussi `t` (date ISO). Le bureau ne transmet une demande qu'après l'avoir comparée au dernier relevé valide : un bouton, une colonne, une tâche, une leçon, une cible, un challenge ou une solution qui n'y figure pas est refusé sans lancer la commande.

**Les demandes de challenge** (relevé version 3 seulement). Pour une cible que le bureau calcule lui-même (un KPI calculé, une source d'amélioration), il écrit le constat en clair dans `texte` (« Tâche « … » : coût de ≈ 4,20 € pour une médiane de ≈ 1,10 € dans le service. »), suivi du texte de l'utilisateur s'il y en a un ; pour un KPI de votre projet ou une connaissance, `texte` est absent : votre projet les connaît par leur identifiant. Une cible qui a déjà un challenge dans le relevé est refusée (la page ouvre le challenge existant) ; tant que votre relevé ne montre pas le challenge demandé, le bureau refuse pendant deux minutes d'en envoyer un second sur la même cible : ajoutez le challenge au relevé dès que vous prenez la demande, même sans solution. Une solution non cochée ne reçoit aucune demande : elle reste en l'état.

**Les boutons** (`actions` dans le relevé) : liste de `{id, libelle}` plus, au choix, `lien` (le bouton ouvre cette adresse dans un nouvel onglet) ou rien (le bouton envoie une demande `bouton`) ; facultativement `confirmer` (la question posée avant l'envoi) et `actif` (`false` = grisé). Pour un bouton à bascule (Pause / Reprendre), c'est le projet qui donne le bon libellé à chaque relevé. **Choisissez des identifiants qui disent l'état voulu** (`pause` puis `reprendre`, pas `basculer`) : un double clic avant le relevé suivant ne défait alors pas la demande.

**Ce que la page montre après un geste** : seulement « Demande envoyée ». L'effet (post-it qui bouge, voyant qui change, leçon qui disparaît) n'apparaît qu'au relevé suivant, quand votre projet l'a vraiment fait.

L'exemple de démonstration, [`exemples/demo/actions.py`](../exemples/demo/actions.py), applique chaque demande à `releve.json`.

## Les images

Une image d'une tâche est un fichier du projet. Les réglages disent d'où le bureau a le droit d'en servir :

```json
{"images": {"racines": ["images"]}}
```

Les racines sont relatives au dossier des réglages. Le champ `chemin` d'une image est relatif à ce même dossier. Le bureau ne sert que les fichiers `.png`, `.jpg` et `.jpeg` qui, une fois le chemin résolu (liens symboliques compris), sont dans une de ces racines ; tout le reste est refusé (404). Sans `images` dans les réglages, les tâches n'ont pas de vignettes. La première image d'une tâche sert aussi de vignette sur son post-it du Kanban (au plus une par post-it visible, chargée en différé, libérée quand le post-it disparaît ou que l'image change ; aucune requête sans `images`). Les autres images sont chargées quand elles deviennent visibles dans le panneau ; l'adresse porte la `maj` de la tâche : mettez-la à jour quand une image est refaite sous le même nom.

Les textes sont affichés comme du texte, jamais comme du HTML, et tronqués s'ils sont longs.

## Ce que le bureau en déduit

- **Au travail** : le titulaire tient une tâche `active` dont `maj` est récente (30 minutes par défaut).
- **Sans nouvelles** : tâche active mais `maj` plus ancienne que le délai de fraîcheur — l'agent reste à son poste, sans animation, avec une bulle grisée. Une `maj` absente ou illisible compte comme « très ancienne ». Une date sans fuseau est une heure locale.
- **Libre** : aucune tâche active — l'agent va au café. Après 24 h sans activité, et s'il n'est ni permanent ni chef, il quitte le bureau.
- Quand une tâche **change de colonne** entre deux lectures, l'agent qui la tenait avant va déplacer son post-it sur le Kanban.
- Si la factory est **en pause**, le voyant le dit et les agents dont la tâche n'est plus à jour vont au café.

## Exemple complet

Voir [`exemples/demo/releve.json`](../exemples/demo/releve.json) (projet inventé « Démo », version 4 : boutons, détail d'une tâche, leçon à valider, retour sans réponse, tâche bloquée, usage sur plusieurs modèles, KPI dont un en alerte, connaissances partagées, un challenge avec trois solutions, une fonctionnalité en série avec son catalogue [`catalogue-magasin.json`](../exemples/demo/catalogue-magasin.json), une montée de modèle, un dernier livrable) et [`exemples/demo-b/releve.json`](../exemples/demo-b/releve.json) (une fonctionnalité en cadrage avec une image dans la discussion, un genre à confirmer, une session cloud à créer).

Version minimale :

```json
{
  "version": 1,
  "projet": "Mon projet",
  "factory": {"etat": "en marche"},
  "services": [{"id": "dev", "nom": "Dev"}],
  "colonnes": [{"id": "afaire", "nom": "À faire"}, {"id": "fait", "nom": "Fait"}],
  "titulaires": [{"cle": "dev:1", "service": "dev", "lieu": "local"}],
  "taches": [{"id": "t1", "titre": "Une tâche", "colonne": "afaire", "active": true,
              "titulaire": "dev:1", "maj": "2026-11-10T09:12:00"}]
}
```
