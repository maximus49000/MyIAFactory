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
| `colonnes` | oui | liste de `{id, nom}` dans l'ordre du Kanban ; à partir de la v2, `terminee` (vrai/faux, facultatif, `null` = absent) marque une colonne terminée (voir ci-dessous) ; `validation: true` (facultatif) marque la colonne d'une étape de validation du Directeur |
| `titulaires` | oui | voir ci-dessous |
| `taches` | oui | voir ci-dessous |
| `file` | non | `{"visibles": [{id, titre}], "reste": n}` — vide par défaut ; en v2, `suite` facultatif (voir ci-dessous) |
| `decisions` | non | nombre de décisions qui attendent le Directeur — `0` par défaut |
| `actions` | non, v2 | les boutons de la factory (voir « Faire agir le bureau ») |
| `types` | non, v2 | liste de `{id, nom}` : les types de tâches, pour le filtre de la vue liste |
| `lecons` | non, v2 | les leçons **à valider** : liste de `{id, agent, texte, tache?, date?, verdict_demande?}` ; `id` unique, `agent` = clé d'un titulaire, `verdict_demande` = `"valider"` ou `"invalider"` (verdict envoyé, pas encore appliqué : le bureau affiche « Verdict envoyé ») ; `refus` (texte, facultatif) = pourquoi la dernière validation n'a pas pu être écrite dans la mémoire de la skill (mot interdit, fichier de mémoire modifié à la main…) : la leçon reste à valider et le bureau dit la raison |
| `lecons_en_attente` | non, v4 | les leçons **validées** dont l'écriture dans la mémoire de la skill est en attente (push refusé, dépôt occupé…) : liste de `{id, agent, texte, etage?, raison?, depuis?, essais?}`. Elles ont quitté `lecons` ; le moteur les réessaie seul et elles disparaissent une fois écrites. Le bureau les montre avec leur `raison` |

**Titulaire** (un agent) : `cle` (stable, unique), `lieu` (`"local"` ou `"cloud"`) et `service` (sauf pour le chef et pour un agent polyvalent) sont obligatoires. Un **agent polyvalent** (qui prend n'importe quelle tâche, en spécialiste de son métier) porte `polyvalent: true`, sans `service` ni `modele` (ceux de sa tâche) ; `retrait_prevu: true` : l'équipe a perdu une place pendant qu'il travaillait, il finit sa tâche et part. Facultatifs : `modele` (`"?"` par défaut), `permanent` (ne quitte jamais le bureau), `chef` (le chef d'atelier ; un seul au plus, le bureau en ajoute un de clé `"chef"` s'il n'y en a aucun), `fraicheur_min` (délai de fraîcheur propre à cet agent, pour les travaux longs et silencieux).

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

`usage` : liste (**5 000 entrées au plus**) de `{id, tache, agent, modele, etape?, lot?, reparti?, t, entree, sortie, cache_lecture?, cache_ecriture?}`, une entrée par discussion. `lot` (texte) : le lot dont la tâche faisait partie ; `reparti` (`temps` ou `egal`) : la ligne est une part répartie du coût d'un lot, donc estimée (l'onglet Facturation la marque « estimé (part d'un lot) »).

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
| `abonnement` | facultatif : l'instantané d'abonnement Claude lu au début de l'appel, `{five_hour?: {pourcent, remise}, seven_day?: {pourcent, remise}, t}` (`pourcent` de 0 à 100 pour le **compte entier**, `remise` et `t` en secondes epoch). Posé par le moteur (`claude -p`) ; mal formé, il est ignoré sans invalider le relevé ; le premier instantané vu d'un `id` est gardé |

- Les compteurs d'un `id` sont des **cumuls** : republiez le même `id` avec des compteurs plus grands tant que la discussion continue, le bureau garde les derniers. Ne changez pas d'`id` en cours de discussion (elle serait comptée deux fois).
- Le relevé n'a besoin de porter que les usages **récents** : le bureau les range dans son historique (`usage-historique.jsonl`, à côté des réglages) et ne les oublie pas quand le projet les retire. Quand une tâche ou un agent quitte le relevé, retirez aussi ses usages : un usage qui cite une tâche ou un agent absent rend tout le relevé invalide.
- La **date de prix** d'un usage (son `t` à la première apparition) et son **service** (celui de l'agent à ce moment-là) sont figés : un coût passé ne bouge ni quand un prix change, ni quand l'agent change de service ou quitte le relevé.
- Un modèle dont le bureau ne connaît pas le prix n'est jamais compté à zéro : la discussion est montrée avec ses tokens et « prix inconnu », elle est exclue des euros, et les chiffres qui en dépendent le disent (« ≈ 3,00 € + prix inconnu », coût moyen « hors prix inconnus »).

**Les partenaires.** Une entrée `{id, genre: "partenaire", partenaire, tache, agent?, t, quantite, unite, cout, devise, estime}`
note un appel payant à un partenaire (voix, images…) : `quantite` et `unite` (« caractères », « crédits »…), `cout`
(nombre ≥ 0, dans sa `devise` à trois lettres) ou `null` (« non chiffré », jamais compté zéro), `estime` (vrai si le
coût n'est pas exact). Pas de `modele` ni de tokens. Le bureau convertit un coût en dollars au taux de la BCE du jour de
l'usage (figé à sa première apparition, le coût d'origine reste noté) ; une autre devise sans taux reste non chiffrée.
La facturation porte alors `partenaires` (voir la fin de ce fichier), à côté des tokens : le total des tokens n'en tient
pas compte.

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
| `regles_projet` | racine | les règles que le Directeur a retenues pour le projet : `[{id, texte (500 caractères au plus), cree_le?, modifie_le?, origine?: {decision, agent}}]`, identifiants distincts ; absent = le projet ne gère pas les règles (aucune partie « Règles du projet » au bureau, aucune demande `regle_projet` acceptée) |
| `decisions_projet` | racine | ce qui attend l'utilisateur pour le projet : `{id, genre, texte, ...}` avec `genre` = `confirmer_genre` (plus `propose` et `genres_connus`) `session_cloud` (plus `agent`, la clé du titulaire qui attend sa session ; la démarche simplifiée ajoute `tache`, `depart` (le message de départ complet, à copier), `lien` (https : claude.ai/code, ou la session déjà inscrite pour l'agent), `depot` (https, le dépôt GitHub) et `modele`), `faire_chez_partenaire` (« À faire chez <partenaire> » : un partenaire où l'utilisateur est inscrit, sans liaison directe ; `agent`, `tache`, `partenaire`, `quoi`, `prompt` (prêt à copier), `reglages` (liste de textes), `mode_operatoire` (liste de textes non vide), `a_rapporter` `{description, nom?}`, et facultatifs `elements` (liste de textes), `site` (https), `nom_partenaire`, `apres` (la décision à faire avant, une génération à la fois) ; « Fait » avec le résultat joint, ou « Je n'ai pas pu »), `accord_agent` (un agent demande l'accord de l'utilisateur : `agent`, `tache`, `quoi`, et facultatifs `partenaire`, `cout`, `pourquoi`, `implique`, `regle`, `appareil` (booléen : installation ou test sur un appareil physique), `regle_proposee` (le texte de la règle du projet que la case « Retenir comme règle du projet » propose, 500 caractères au plus), `choix` (1 à 6 textes de 120 caractères au plus : les choix que l'agent a proposés avec sa demande, montrés comme boutons à la place de « J'accepte » / « Je refuse »), `regles_touchees` (`[{id, texte}]`, 3 au plus : les règles du projet que la demande touche, rappelées au Directeur)) `outil_agent` (un agent est arrêté faute d'un outil que sa fiche ne lui ouvre pas : plus `agent` (sa clé), `tache`, `outil` (l'outil, ou la règle `Bash(<programme>:*)`) et, facultatifs, `programme` (à ouvrir à cet agent) et `commande` (la commande refusée, une ligne coupée à 160 caractères, valeurs secrètes masquées) ; posée quand le moteur ne peut pas ouvrir seul l'outil), `environnement` (plus `environnement` : la liste des outils du poste qui manquent, chacun avec un `outil` et, facultatifs, `objectif` (à quoi il sert dans ce projet, à quelle étape), `telechargement` (URL https de la page officielle, ou nul), `etapes` (le mode opératoire, une liste de textes), `autonome` (un agent peut l'installer seul) et `en_cours` (une tâche d'installation le couvre) ; après chaque « C'est fait », la décision porte `verifie_le` (l'heure de la dernière vérification) et chaque outil sa `verification` `{trouve, cherche: [exécutables], introuvables, version_demandee, version_trouvee}` (et `etat` `en_place` = trouvé, `a_installer` = non trouvé, `raison`) ; un outil forcé par le Directeur porte `etat` `en_place`, `declare` vrai et `note` « déclaré installé par le Directeur (non vérifié) » ; posée quand l'installation portée par le projet n'a pas tout installé), `elargir_genre` (élargir la description d'un genre gardé : plus `cible` (le genre), `ancienne`, `propose` et `fonctionnalite`), `serie_arretee` (une série qui ne progresse plus : aucune tâche ouverte, ni décision, ni agent au travail ; plus `fonctionnalite` ; le `texte` commence par « La série de « … » ne progresse plus : » et dit pourquoi, élément par élément), `organisation` (plus `organisation` : `{services, flux, agents, briefs, cout}`, l'organisation proposée ; `cout` = `{tokens: [a, b], euros: [a, b] ou null}`) ou `valider_etape` (un élément attend le Directeur à une étape de validation : plus `fonctionnalite`, `element` `{id, nom}`, `etape` (l'étape de validation), `tache` (la tâche « Validation du Directeur »), `compte_rendu` (2000 caractères au plus) et `fichiers` `[{chemin, titre}]` de l'étape précédente, ceux de **cet** élément seulement ; facultatifs : `objectif` (ce que l'élément devait produire, une ou deux phrases) et `a_valider` (le nom de l'étape de validation, et sa raison), montrés en tête, avant le compte rendu ; `points` (les points à vérifier de la fenêtre de validation : 1 à 8 phrases de 160 caractères au plus, sans doublon ; absent = un seul point « L'élément correspond à l'objectif »), `doit_marcher` (480 caractères au plus : ce qui doit fonctionner pour valider), `pas_encore` (480 au plus, peut être vide : ce qui n'est pas encore attendu à ce stade) et `conclusion` (200 au plus : « Validez si… ») ; absents = « Ce qui doit marcher : l'élément correspond à son objectif » ; `nature` (facultatif : `en_jeu`, `visuel`, `son`, `mecanique` ou `autre` — ce que le Directeur valide, donc les preuves jointes ; absente = comportement d'avant) et `mode_operatoire` (facultatif, pour `en_jeu` : 2 à 10 étapes courtes de 200 caractères au plus, affichées numérotées après « Télécharger ») ; `acces` `{url, description?}` (le lien d'accès d'un site qui tourne, http ou https) et, sur chaque fichier livrable trouvé, `taille` (octets) et `date` (modification, au moment de la pose)) |
| `agents_locaux_max` | racine | facultatif : le nombre d'agents locaux au plus travaillant en même temps (entier ≥ 1 ou nul) ; la bulle de la barre de charge l'affiche, la partie « Parallélisme du projet » de l'onglet Facturation le règle |
| `agents_cloud_max` | racine | facultatif : le nombre d'agents cloud au plus travaillant en même temps (entier ≥ 0 ou nul), la valeur effective (0 par défaut ; un projet qui avait déjà des agents cloud sans réglage garde l'ancienne limite de ses réglages) ; réglé dans la même partie |
| `recrutement` | racine | facultatif : de quoi recruter dans la même partie : `roles` `[{role, nom, modele, agents, cloud, travail}]` (les rôles des étapes d'agent des workflows ; `modele` = celui déjà choisi pour ce rôle ; `travail` = tâches prêtes et éléments en file qui passeront par ce rôle, sans ce qu'une validation retient), `places` `{cloud, locaux}` (les places sans agent recruté), `propositions` `[{role, modele, modele_necessaire, lieu, raison}]` (la répartition automatique, une recrue à la fois : les N premières valent pour « Recruter N agents »), `propositions_par_lieu` `{mieux, cloud, local}` (la même liste pour chaque lieu demandé ; `mieux` = `propositions`, `cloud` et `local` ne proposent que des agents de ce lieu, dans la limite de ses places ; `modele` = le plafond de la recrue, Opus ; `modele_necessaire` = le modèle que demandent les tâches qu'elle prend : celui posé sur l'étape, sinon le plus logique pour ce travail ; `raison` dit pourquoi : nature des tâches, montée d'un cran après échec ou « À revoir », sinon le modèle du rôle ; jamais Fable) et `notes_par_lieu` `{mieux, cloud, local}` (listes de textes : pourquoi la liste s'arrête), `notes` (textes), `depot` `{git, github, url, creable, essai?}` (lu dans `.git/config` ; `creable` : pas d'origine du tout ; `essai` `{t, fait, texte, url?}` : le dernier « Créer le dépôt Git ») et `cloud_impossible` (la raison, ou nul) ; `reprise_possible` (vrai ou faux, facultatif) : le projet a encore des fiches d'agents par rôle, la reprise est proposée ; `polyvalent` (vrai, facultatif) : le projet a des agents polyvalents, l'équipe suit les places et rien ne se recrute (`roles` et `propositions` y sont vides, la partie « Recruter » est cachée) |
| `orchestrateur_present` | racine | facultatif : vrai si le moniteur de l'orchestrateur (`guetter`) (ou une de ses commandes) a noté sa présence il y a moins de 2 minutes ; faux : le bureau bloque les gestes et propose « Lancer l'orchestrateur » ; absent : rien n'est bloqué (adaptateur qui ne le dit pas) |
| `partenaires` | racine | facultatif : l'espace partenaire (la pièce « Partenaires », voir ci-dessous) ; absent, la pièce n'existe pas |
| `fonctionnalite`, `element` | chaque tâche | la fonctionnalité et l'élément du catalogue de la tâche |
| `modele_depart`, `montee` | chaque tâche | le modèle de départ et une montée de modèle `{de, a, raison}` (montrée dans le panneau de la tâche) |
| `modele_necessaire` | chaque tâche | facultatif (nul : le modèle de la fiche, pour le cadrage, le prototype, l'installation) : `{modele, raison, ramene}`, le modèle sur lequel la tâche tourne — celui de son étape (posé avec le workflow, sinon déduit de sa nature), montée comprise ; `ramene` vrai quand aucun agent du rôle n'a un plafond suffisant et que le modèle est ramené au plus haut plafond du rôle. Le modèle de la fiche d'un agent (`modele` de ses titulaires) est son plafond. Montré « Modèle nécessaire » dans le panneau de la tâche |
| `lot` | chaque tâche | facultatif : `{id, rang}` (texte non vide, entier d'au moins 1) ou `null` ; le panneau de la tâche montre « Lot L2, tâche 3 sur 4 » |
| `etage_propose`, `texte_general`, `roles` | chaque leçon | l'étage proposé (`projet`, `genre` ou `skill`), le texte réécrit en termes généraux (obligatoire si l'étage n'est pas `projet`), les rôles concernés |

**Une fonctionnalité** : `id`, `nom`, `etape` (`cadrage`, `cahier`, `decoupage`, `prototype`, `methode`, `serie` ou
`terminee`), et facultativement :
- `agent_cadrage` (clé d'un titulaire) ; `discussion` : `[{id, t, auteur, texte, images?, fichiers?}]`, du plus ancien au plus
  récent, 1 000 messages au plus, `auteur` = `utilisateur` ou la clé d'un titulaire, `images` = 4 au plus, chacune un
  chemin (règles des images) ou `{chemin, legende?}` (voir « Les légendes ») ; `fichiers` = 8 au plus, les fichiers
  joints par l'utilisateur (voir « Les fichiers joints ») : `[{chemin, nom, type, taille}]`, `chemin` relatif au dossier des
  réglages comme les images, `nom` le nom d'origine, `type` le type servi, `taille` en octets (les images PNG et JPEG
  jointes figurent dans `images` **et** dans `fichiers`) ; `attend_reponse` (vrai ou faux) ;
- `cahier` : `{maquette: [images], etapes: [textes], valide_le?, partenaires?}`, chaque image de la maquette étant un chemin ou `{chemin, legende?}` ; `partenaires` (facultatif) : les partenaires décidés au cadrage, `[{id, mode}]` avec `mode` = `direct` (connecté), `inscrit` (l'utilisateur fait la génération chez le partenaire) ou `aucun` (pas de partenaire pour ce besoin), un partenaire au plus une fois, 20 au plus ;
- `cahiers_precedents` (facultatif) : les cahiers remplacés par une correction, du plus ancien au plus récent, chacun avec `remplace_le` ; une fonctionnalité revenue en `cadrage` alors qu'elle a un `cahier` est en correction (le bureau ne montre plus ce cahier comme valable) ;
- `methode` : `{version, lien | chemin, validee_le?}` ;
- `livrable` : `{libelle, lien | chemin, date}` ;
- `catalogue` : vrai si le projet fournit un catalogue pour cette fonctionnalité (bouton « Catalogue ») ;
- `fin` (facultatif, posé par le moteur quand la fonctionnalité passe à `terminee`) : `{date, vu, livrables: [{chemin, titre}], acces?: {url, description?}, laisses?: [noms]}` — l'avis « Fonctionnalités terminées » du bureau de direction, non bloquant (il ne compte pas dans les décisions) tant que `vu` est faux : les livrables se téléchargent par `/api/telecharger`, le site s'ouvre directement sur l'ordinateur ou, au téléphone, par le relais `/apercu/<projet>/fin-<fonctionnalité>/` ; le coût vient de `/api/couts`. « Vu » envoie `fin_vue` ;
- `decisions` : `[{id, genre, texte}]` avec `genre` = `valider_cahier`, `valider_methode`, `methode_a_revoir` ou `reprendre_methode` (une méthode déjà validée qui ressemble, proposée d'emblée) ou `genre_fonctionnalite` (plus `propose`, `genres_connus`, `incertain` et, facultatif, `nouveau` `{id, description}` : la demande n'est pas du genre du projet) ;
- `glossaire` : le vocabulaire de la fonctionnalité, `[{mot, definition}]` (500 mots au plus ; mot : 60 caractères,
  définition : 400) ; un message peut aussi porter son `glossaire`, et des `questions` à choix
  (`[{texte, choix: [2 à 12], multiple?}]`, 10 au plus) : le bureau met les mots en valeur (définition au survol) et
  montre un bouton par choix, « Autre » et « Passer » (avec `multiple`, les boutons sont basculables et la réponse
  liste les choix retenus ; absent ou faux, un seul choix, comme avant) ;
- `documents` : les fichiers produits pour la fonctionnalité, 2 000 au plus, chacun `{chemin, titre}` et, facultatifs,
  d'où il vient : `agent`, `etape`, `tache`, `element`, `sous_tache`, `date` (textes), et `livrable` (vrai : un fichier
  final de son élément, montré dans les « Livrables » du panneau avec « Demander une modification »). Le panneau de la fonctionnalité
  les range par étape ; le bureau les sert par `GET /api/document?fonctionnalite=…&chemin=…`, seulement s'ils sont
  listés ici et dans une des racines de `{"documents": {"racines": [...]}}` des réglages. Images, PDF et paquets
  comme un livrable ; `.md`, `.json`, `.csv`, `.txt`, `.html` et `.svg` en bac à sable (sans script).

**Téléchargement d'un livrable** (fenêtre de validation, « Télécharger » des Livrables) :
`GET /api/telecharger?projet=…&fonctionnalite=…&chemin=…` sert le fichier **toujours en pièce jointe** (sauf avec `&lecture=1` pour un son mp3, ogg, wav ou flac : type audio, sans pièce jointe, `Range` honoré, pour le lecteur de la fenêtre)
(`Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`) avec le type de son extension (`.apk` :
`application/vnd.android.package-archive` ; aussi `.aab`, `.zip`, `.7z`, `.pdf`, `.exe`, `.msi`, `.dmg`, `.deb`, `.pck`,
images, sons, vidéos, bureautique… la liste `TELECHARGEABLES` de `bureau/releve.py`), **500 Mo au plus** (au-delà :
413). Le fichier doit être un fichier ordinaire **dans le projet** (lien résolu ; jamais dans `.git`), le chemin relatif,
sans `..` ni lecteur, et soit sous une racine `livrables` ou `documents` des réglages, soit déclaré pour cette
fonctionnalité : document `livrable`, ou fichier d'une décision `valider_etape`. Il est cherché depuis le dossier des
réglages, puis, réglages dans `.factory`, depuis le dossier du projet (un `build/jeu.apk` à sa racine). Sinon : 404.

**Relais vers le site en cours** : `/apercu/<projet>/<décision>/<chemin>` (`-` pour le projet d'un bureau à un seul
projet) relaie GET, HEAD et POST vers `http://127.0.0.1:<port>/<chemin>` quand la décision `valider_etape` encore posée
déclare un `acces` local (http, 127.0.0.1/localhost/::1, port explicite, jamais un port du bureau). Ni cookie ni
`Origin` envoyés au site, pas de `Set-Cookie` ni de politique de sécurité rendues, pas de compression ; `Location`
ramenée sous le préfixe ; WebSocket : 501 ; site éteint : 502 ; corps envoyé 10 Mo au plus, réponse 200 Mo au plus.
Les deux routes passent par la même garde que les autres (code d'accès sur l'écouteur distant).

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
| `challenge` | `cible` (`{type, id}`), `texte?`, `solution?` | v3 : ouvrir un challenge sur cette cible ; `solution` : la solution que l'utilisateur écrit dans le même geste ; v4 : `cible.type` = `lecon` (une leçon, même à valider : `texte` obligatoire) pour la discuter avant le verdict |
| `solution` | `challenge`, `texte` (3 500 caractères au plus) | v3 : l'utilisateur ajoute sa solution à un challenge du relevé |
| `verdict_solution` | `challenge`, `solution`, `verdict` (`"valider"` ou `"ecarter"`) | v3 : la décision de l'utilisateur sur une solution (« Valider la sélection » ou « Écarter la sélection » : une demande par solution cochée) |

**Les demandes de la version 4** (refusées sans lancer la commande si le relevé n'est pas en version 4) :

| `type` | Champs | Quand |
|---|---|---|
| `fonctionnalite` | `texte`, `images?`, `fichiers?` | « + Nouvelle fonctionnalité » : son premier message |
| `message` | `fonctionnalite`, `texte`, `images?`, `fichiers?` | un message de l'utilisateur dans la discussion |
| `cahier` | `fonctionnalite`, `verdict` (`valider` ou `corriger`), `texte?` | « Valider le cahier des charges » ou « Demander une correction » |
| `methode` | `fonctionnalite`, `verdict` (`valider`, `revoir`, `garder`, `reprendre` ou `adapter`), `texte?` (obligatoire pour `adapter`) | valider la méthode ; « méthode à revoir ? » : Oui = `revoir`, Non = `garder` ; « reprendre la méthode ? » : « Oui, industrialiser » = `reprendre`, « Modifier le mode opératoire » = `adapter`, « Relancer le prototype » = `revoir` |
| `genre` | `decision`, `genre`, `description?` | le genre confirmé ou choisi ; `description` pour un nouveau genre |
| `session_cloud` | `decision`, `session` | « C'est fait » : la session cloud demandée est créée, avec ce nom ; si la décision porte `depart`, `session` est l'adresse `https://claude.ai/code/<id>` ou l'identifiant (`session_…` ou un UUID), sinon refusée |
| `accord_agent` | `decision`, `verdict` (`accepter` : l'agent reprend avec l'accord ; `refuser` : il reprend sans l'action, avec la consigne ; `choisir` : l'agent reprend avec le choix retenu, donné en `choix`, l'un de ceux de la décision), `texte` (consigne facultative, 3 500 caractères au plus), `regle?` (le texte à retenir comme règle du projet, 500 caractères au plus : la case « Retenir comme règle du projet » ; refusé si le relevé n'a pas `regles_projet`) | « J'accepte » / « Je refuse » et un champ de consigne (bureau de direction, partie « Demandes d'accord des agents ») |
| `regle_projet` | `operation` (`ajouter`, `modifier` ou `supprimer`), `id?` (la règle visée, d'`regles_projet`, pour `modifier` et `supprimer`), `texte?` (500 caractères au plus, pour `ajouter` et `modifier`) | « Règles du projet » du bureau de direction : ajouter, modifier ou supprimer (après confirmation) une règle |
| `outil_agent` | `decision`, `verdict` (`autoriser` : ajoute `Bash(<programme>:*)` à la fiche de l'agent et relance sa tâche, seulement si la décision porte un `programme` ; `refuser` : la tâche est bloquée avec la raison ; `relancer` : la fiche a été complétée à la main) | « Autoriser ce programme pour cet agent » / « Refuser » (bureau de direction) |
| `organisation` | `decision`, `verdict` (`accepter`, `refuser` ou `abandonner`) ; facultatifs : `texte` (ce qu'il faut changer à une proposition refusée), `fable` (les clés des agents cochés pour Fable), `installer` (avec « accepter » seulement : les noms des outils `autonome` du workflow à installer en autonomie, aucun par défaut) | « Accepter » ou « Refuser » une évolution de l'organisation, ou le workflow d'une fonctionnalité (« Abandonner » la demande) |
| `genre_fonctionnalite` | `decision`, `fonctionnalite`, `choix` (`ici`, `meme` si le moteur hésitait, ou `nouveau_projet`) ; facultatifs : `genre`, `description` (un genre nouveau), `projet_cree` (les réglages du projet créé, pour `nouveau_projet`) | La réponse à « cette demande n'est pas du genre du projet » |
| `installer_outil` | `decision` (une décision `environnement`), `outil` (son nom) ; facultatif : `fonctionnalite` (celle de la décision ; sans elle, la décision du projet) | « Installer en autonomie » : un outil `autonome`, encore à installer et sans installation en cours reçoit sa tâche d'installation (l'agent d'installation est recruté s'il manque) ; la décision reste, la fin de la tâche revérifie le poste |
| `environnement` | `decision` (une décision `environnement`), `verdict` (`fait`, `continuer` ou `forcer`) ; facultatifs : `fonctionnalite` (celle de la décision ; sans elle, la décision du projet), `outil` (avec `forcer` seulement : le nom d'un outil non trouvé ; sans lui, tous les outils non trouvés) | `fait` : le moteur revérifie en code chaque outil de la décision (le `PATH` à jour du registre Windows compris) ; tous trouvés, la décision est levée et le travail reprend, sinon elle reste et marque chaque outil « trouvé » ou « non trouvé » (ce qui a été cherché, la version trouvée). `forcer` (« Forcer : c'est installé », confirmé au bureau) : le Directeur affirme l'outil installé ; la décision est levée s'il ne reste rien, l'outil est noté « déclaré installé par le Directeur (non vérifié) » dans l'environnement du projet et les agents le savent. `continuer` : « Continuer sans » |
| `elargir_genre` | `decision`, `verdict` (`valider` ou `refuser`) ; facultatif : `description` (la phrase corrigée par l'utilisateur, 3 500 caractères au plus ; sinon la phrase proposée) | « Élargir » la description d'un genre gardé, ou « Laisser telle quelle » (bureau de direction) |
| `valider_etape` | `decision`, `verdict` (`valider` ou `renvoyer`), `reponses` `[{point, ok}]` (la fenêtre de validation : exactement une réponse par point de la décision ; le verdict doit en découler : tous OK = `valider`), `texte` (facultatif avec `reponses` : noté et transmis à la tâche suivante si tout est OK, ajouté aux points à revoir sinon ; sans `reponses` — forme d'avant —, obligatoire avec `renvoyer`) | un élément arrivé à une étape de validation du Directeur, envoyé depuis la fenêtre de validation : validé, il passe à l'étape suivante ; renvoyé, il refait l'étape précédente avec « Remarque du Directeur : points à revoir : … » |
| `parallelisme` | `agents_locaux_max` (entier de 1 à 16), `agents_cloud_max` (entier de 0 à 16) | les places du projet (onglet Facturation, « Parallélisme du projet ») : écrites dans le fichier de factory par `lancer parallelisme` |
| `recruter` | `mode` (`manuel` : un agent ; `auto` : 1 à 16), `agents` `[{role, modele, lieu, fable?}]` ; facultatif, en `auto` seulement : `lieu` (`mieux`, `cloud` ou `local` : le lieu choisi dans le formulaire ; avec `cloud` ou `local`, tout agent doit être de ce lieu, vérifié par le bureau puis par l'outil) | « Recruter un agent » (rôle de `recrutement.roles`, modèle Haiku, Sonnet ou Opus, Fable seulement en manuel avec `fable: true` — la case « J'accorde Fable »), ou « Confirmer le recrutement » d'une répartition automatique ; le bureau refuse le cloud sans GitHub (`recrutement.depot.github`) ou au-delà de `places.cloud`, et l'auto au-delà de `places.locaux` ; `lancer recruter` revérifie et écrit les fiches |
| `passer_polyvalent` | `confirme` (`true` obligatoire) | « Passer aux agents polyvalents » (le clic = le consentement), tant que `recrutement.reprise_possible` est vrai ; `lancer polyvalents` reprend le projet (un métier par rôle, leçons regroupées, équipe ramenée aux places, aucune tâche touchée) |
| `depot_git` | `confirme` (`true` obligatoire) | « Créer le dépôt Git » (le clic = le consentement) : seulement si `recrutement.depot.creable` ; `lancer depot` crée le dépôt git local si besoin et un dépôt GitHub **privé**, et pousse |
| `serie_arretee` | `decision`, `verdict` (`relancer`) | « Relancer la série » (bureau de direction, « Séries qui ne progressent plus ») : le moteur lève la décision et relit la série depuis le suivi ; si elle ne repart toujours pas, la décision revient avec la raison |
| `fin_vue` | `fonctionnalite` (une fonctionnalité qui a `fin`) | « Vu » sur l'avis « Fonctionnalités terminées » : l'avis se ferme, la fonctionnalité reste terminée |
| `retour_element` | `fonctionnalite`, `element`, `texte` | « Demander à modifier » dans le catalogue (l'élément doit y être) |
| `partenaire_regle` | `partenaire`, `operation` (`ajouter`, `modifier` ou `supprimer`), `id?`, `texte?` | une règle d'usage d'un partenaire (500 caractères au plus ; `id` = la règle visée pour `modifier` et `supprimer`) |
| `partenaire_inscrit` | `partenaire`, `inscrit` (booléen) ; facultatif : `note` (200 caractères au plus : le nom du compte, l'offre ; **jamais un mot de passe ni une clé** : refusée si elle en parle ou ressemble à un jeton) | « Je suis inscrit » / « Je ne suis plus inscrit » sur la carte d'un partenaire (hors liaison directe) : le bureau garde le fait, sa date et la note, rien d'autre ; refusé pour un partenaire fermé (on peut toujours retirer son inscription) |
| `faire_chez_partenaire` | `decision` (une décision `faire_chez_partenaire`), `verdict` (`fait` ou `impossible`) ; facultatifs : `texte` (3 500 caractères au plus ; obligatoire avec `impossible` : ce qui a bloqué), `fichiers` (avec `fait` seulement : le résultat rapporté, mêmes règles que les fichiers joints d'un message : `{nom, type, donnees}`, 8 au plus) | le retour de « À faire chez <partenaire> » : l'agent reprend la même tâche avec ce que l'utilisateur rapporte (les fichiers sont rangés sous `pieces/partenaires/<décision>/`) ; refusé tant qu'une demande plus ancienne du même partenaire (`apres`) n'est pas faite |
| `partenaires_actualiser` | aucun | « Actualiser » : relever de nouveau les quotas |
| `partenaires_maj` | `confirme` (`true` obligatoire) | « Mettre à jour les offres » : l'utilisateur a vu le coût estimé et confirmé |

Textes : 3 500 caractères au plus. **Images jointes** : 4 au plus par demande, `{nom, type, donnees}` avec `donnees`
en base64, `type` = `image/png` ou `image/jpeg`, extension `.png`, `.jpg` ou `.jpeg` assortie, 5 Mo au plus une fois
décodée, contenu vérifié par sa signature, nom simple (ni dossier ni `..`). Le bureau ne les écrit nulle part : **votre
commande d'actions les range** dans le projet (et les commite, si un agent cloud doit les lire), puis le relevé les
montre par leur chemin. Un message envoyé reste affiché « en attente » tant que le relevé ne l'a pas repris ; un double
clic ne crée qu'une demande (une demande identique dans les 10 secondes est ignorée). Une décision `valider_etape`,
`elargir_genre`, `outil_agent`, `accord_agent` ou `serie_arretee` n'a qu'une réponse : une deuxième demande pour la même décision, pendant 10 minutes, est refusée par le
bureau (409, « déjà reçu une réponse ») sans lancer la commande ; la page montre l'élément « envoyé, en cours de
traitement » jusqu'à ce que le relevé ne porte plus la décision.

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

### Les légendes

Une image produite par un agent peut porter sa **légende** : une phrase (160 caractères au plus, texte non vide) qui dit à quoi
l'image fait référence (écran, élément, moment du jeu…). Le bureau l'affiche en petit sous l'image, et s'en sert comme texte
alternatif (`alt`) ; sans légende, il n'affiche rien de plus. Où elle se porte :

- une image de message de la discussion (`images`), une image de la `maquette` d'un `cahier` ou d'un cahier précédent : un chemin
  seul (ancienne forme, toujours acceptée) **ou** `{"chemin": "…", "legende": "…"}` ; les deux formes se mélangent dans une liste ;
- une image de tâche (`images` : `{chemin, legende?}`) ;
- un élément du catalogue : `captures[].legende`, et `comparaisons[].legende_reel` / `legende_produit`.

Les images jointes par l'utilisateur n'ont pas de légende. Le titre d'un document image (`documents[].titre`) tient lieu de
légende dans les listes de documents ; l'outil y reprend celle de l'image quand le document n'avait que son nom de fichier.

Les textes sont affichés comme du texte, jamais comme du HTML, et tronqués s'ils sont longs.

## Les fichiers joints

L'utilisateur peut joindre des fichiers à « + Nouvelle fonctionnalité » (`fonctionnalite`) et à tout message de la discussion
(`message`), par le champ `fichiers: [{nom, type?, donnees}]` (`donnees` : le contenu en base64 ; `type` est ignoré, le type
vient de l'extension). Le champ `images` d'avant (PNG ou JPEG, 4 au plus, 5 Mo) reste accepté tel quel. Liste blanche, vérifiée
par le bureau puis par l'outil, par l'extension **et** par le début du contenu :

| Famille | Extensions | Début du contenu |
|---|---|---|
| images | `.png` `.jpg` `.jpeg` `.webp` | signature PNG, JPEG (`FFD8FF`), `RIFF….WEBP` |
| image animée | `.gif` | `GIF87a` ou `GIF89a` |
| vidéos courtes | `.mp4` `.webm` | `ftyp` à l'octet 4 ; en-tête EBML (`1A45DFA3`) |
| sons | `.mp3` `.ogg` `.wav` `.flac` | `ID3` ou une trame MPEG ; `OggS` ; `RIFF….WAVE` ; `fLaC` |
| documents | `.pdf` `.docx` `.xlsx` `.pptx` | `%PDF` ; `PK` (un document bureautique est une archive zip) |
| textes | `.md` `.txt` `.csv` `.json` | du texte : aucun octet nul |
| archives | `.zip` | `PK` |
| modèles 3D | `.glb`, `.fbx` | `glTF` ; `Kaydara FBX Binary` ou `; FBX` |
| modèles 3D (texte) | `.gltf`, `.obj`, `.mtl` | aucun octet nul |

Plafonds : **8 fichiers au plus par envoi**, dont **4 images PNG ou JPEG** au plus ; **25 Mo par fichier** (**5 Mo** pour une image
fixe : png, jpg, jpeg, webp) ; **40 Mo en tout**, une fois décodés. Un nom de fichier fait 80 caractères au plus, sans séparateur,
sans `..`, sans caractère de contrôle ni `* ? " < > |`. Tout autre type, un contenu qui ne correspond pas à l'extension, un
fichier vide, un dépassement : la demande est refusée avec la raison (en français).

L'outil range chaque fichier tel quel sous `pieces/<fonctionnalité>/<date>-<nom sûr>` (le nom sûr garde les lettres, chiffres,
tirets et la ligne basse ; un nom réservé de Windows est préfixé) et le message garde `fichiers: [{chemin, nom, type, taille}]`
(`nom` : le nom d'origine, `type` : celui de la liste blanche, `taille` : en octets). Les PNG et JPEG joints sont aussi dans
`images`, comme avant (documents, visionneuse). **Rien n'est jamais ouvert, décompressé ni exécuté par le bureau ou l'outil.**

Dans la page : une image ou un GIF en vignette (visionneuse au clic) ; une vidéo (`<video controls preload="none">`) ; un son
(`<audio controls preload="none">`) ; un `.md` lu en ligne ; tout le reste avec « Télécharger ». Le bureau sert ces fichiers par
`/api/telecharger` **seulement** s'ils sont joints à un message de la discussion de la fonctionnalité demandée et d'une extension de
la liste blanche (toujours en pièce jointe, sauf la lecture en ligne `lecture=1` d'un gif, webp, mp4, webm, son ou texte `.md`/`.txt` ;
un `.json` n'est jamais lu en ligne). Le moteur donne à l'agent la liste de ces fichiers (chemin depuis le dossier du projet,
type, taille) dans la discussion qu'il reçoit, avec la consigne de les lire.

## Ce que le bureau en déduit

- **Au travail** : le titulaire tient une tâche `active` dont `maj` est récente (30 minutes par défaut).
- **Sans nouvelles** : tâche active mais `maj` plus ancienne que le délai de fraîcheur — l'agent reste à son poste, sans animation, avec une bulle grisée. Une `maj` absente ou illisible compte comme « très ancienne ». Une date sans fuseau est une heure locale.
- **Libre** : aucune tâche active — l'agent va au café. Après 24 h sans activité, et s'il n'est ni permanent ni chef, il quitte le bureau.
- Quand une tâche **change de colonne** entre deux lectures, l'agent qui la tenait avant va déplacer son post-it sur le Kanban.
- Si la factory est **en pause**, le voyant le dit et les agents dont la tâche n'est plus à jour vont au café.

## Les semaines du forfait et leurs sujets (routes du bureau)

Ces routes concernent **tout le bureau commun** (pas de `?projet=`). Le format du relevé ne change pas.

- `GET /api/semaines` : `{semaines: [{id, debut, remise, courante, max, n}], maintenant}`, la plus récente d'abord. `id` est `AAAA-MM-JJ` (date UTC de la remise à zéro, avec `-2`… si deux semaines tombent le même jour) ; `debut` et `remise` sont en secondes epoch ; `max` est le plus haut % utilisé et `n` le nombre de points archivés. Le premier appel amorce l'archive avec l'historique d'abonnement.
- `GET /api/semaine?id=<id>` : `{id, debut, remise, vu, points: [{t, pourcent, source}]}` (la série archivée, `pourcent` utilisé de 0 à 100 pour le compte entier, `source` : `compte` ou `moteur`) ; 404 si l'`id` est inconnu ou mal formé.
- `GET /api/sujets?semaine=<id>` : `{semaine, debut, remise, euros, sans_prix, n, co2?, sujets: [nœud]}`. Un nœud : `{id, nom, genre (projet, fonctionnalite, tache, etape, groupe, echange, creation), euros, sans_prix, n, co2?, marques: [{t, euros, modele, duree}], enfants: [nœud]}` ; chaque nœud cumule ses descendants, les enfants sont triés par coût, et seul le nœud où s'arrête un usage porte ses `marques` (instants d'appel en secondes epoch ; `duree` en secondes ou `null`). Projet → fonctionnalité (« Hors fonctionnalité ») → tâche → étape (« Sans étape »), plus par projet « Orchestration », « Direction », « Hors tâche », et à la racine « Échanges de création » (un nœud par brouillon, plus « Échanges abandonnés »). Un usage sans prix est compté dans `sans_prix`, jamais pour zéro euro ; les usages de partenaires n'y figurent pas. La part estimée (≈ % semaine) est calculée par la page avec le taux de `/api/conso`.

## Les jauges d'abonnement (état servi à la page)

Les jauges et le rond lisent la même mesure, servie par `GET /api/conso` (le compte, sinon le dernier appel du moteur : `source` vaut `"compte"` ou `"moteur"`, `mesure` est l'instant de la mesure en secondes epoch, `part` la part estimée). Le format du relevé ne change pas. `GET /api/etat` porte de son côté `abonnement` : `{instantane, pourcent_par_euro: {five_hour, seven_day}, mesures, minimum, maintenant}`, ou `null` quand la couche des appels est l'API (rien à afficher). `instantane` est le dernier lu dans `~/MyIAFactory/abonnement.json` (`null` : « pas encore mesuré »). `pourcent_par_euro` est le nombre de points de pourcentage de l'abonnement par euro (équivalent tarif API) ; `null` tant que `mesures` est sous `minimum` (« en cours d'étalonnage »). Les pourcentages sont ceux du compte, pas ceux de ce seul bureau.

## Ce qui retient le travail (état servi à la page)

Le format du relevé ne change pas. Le moteur dit ce qui retient le travail par deux petits fichiers que le serveur du bureau
relit (les deux processus sont séparés) et ajoute à `GET /api/etat` :

- `pause_installation` : `{texte, projet, outils}` ou `null`. Une installation d'outil, dans un projet quelconque du
  bureau, met tous les projets en pause (« Pause : installation de Godot Engine (CasseBrickReborn) ») ; la barre l'affiche
  pour tous. Lu dans `installation-prioritaire.json`, à côté du fichier du bureau.
- `attente_charge` : `{texte, taches: [ids], charge, plafond}` ou `null`, et sur chaque tâche concernée `attente` (le même
  texte : « En attente : charge 90 % (plafond 70 %) »). Lu dans `.factory/attente-charge.json` du projet.

Un fichier non réécrit depuis deux minutes est ignoré (le moteur s'est arrêté). Aucun chemin ni clé n'y figure.

Une tâche dont l'agent local travaille (son processus vit, lu dans `.factory/agents-en-cours/`) porte aussi
`travail` : `{depuis, agent, action, action_t}` (`depuis` : début du travail, heure ISO ; `action` : la dernière action
de l'agent en quelques mots, « modifie scenes/combat.gd », ou `null` ; `action_t` : son heure ISO, ou `null`). Le reste
d'un lot porte le même `travail`. Absent quand aucun agent local ne travaille sur la tâche.

## L'empreinte carbone estimée (champ `co2` des coûts servis)

Le relevé ne porte rien de plus : l'empreinte est calculée par le bureau (`bureau/empreinte.py`, méthode EcoLogits) à partir des `sortie` de chaque usage et de son `modele`. Là où le bureau sert un coût en euros, il ajoute un champ `co2` (absent quand rien n'a pu être estimé, jamais `0` à la place d'un inconnu) :

`co2 = {min, max, wh_min, wh_max, assimile?, incomplet?}` : `min` et `max` en **gCO2e** (usage + fabrication), `wh_min` et `wh_max` en **Wh** ; `assimile: true` quand un modèle a pris l'entrée la plus proche de sa famille ; `incomplet: true` quand un usage chargé en tokens n'a pu être estimé.

Où : `/api/facturation` (`co2` au total, dans `services.<id>`, `direction` et `orchestration`, leurs `taches.<id>.co2`, `taches.<id>.etapes_co2`, `modeles_co2` et `usages[].co2`), `/api/couts?fonctionnalite=` (total et par tâche), `/api/creations` et le brouillon (`cout.co2`, `brouillons[].co2`, `abandonnes.co2`), `cout.co2` d'une proposition du chef et d'une décision `organisation` dans `decisions_projet` (estimé alors sans détail : un cinquième des tokens en sortie, réparti à parts égales entre les étapes). Un modèle de la famille Fable n'a pas de valeur.

**Équivalences.** Le `co2` du **total** (projet entier dans `/api/facturation`, fonctionnalité dans `/api/couts?fonctionnalite=`) porte en plus `equivalences: [{cle, valeur, unite, libelle, min, max}]` (3 ou 4 repères, absent sans empreinte) : `cle` (`voiture`, `smartphone`, `streaming`, `led`, `email`, `bouilloire`), `valeur` (milieu de la fourchette, dans l'unité choisie pour être lisible, au moins 1), `unite` (`m`, `km`, `%`, `recharge`, `s`, `min`, `h`…), `libelle` (texte accordé, ex. « km en voiture thermique »), `min` et `max` (la fourchette dans la même unité). Calculé par `bureau/empreinte.py` (`equivalences`), jamais par la page. Facteurs et sources : voir « L'empreinte carbone estimée » dans docs/installation.md.

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

## L'espace partenaire (champ `partenaires`, version 4)

Les partenaires (voix, images, vidéo, 3D, traduction…) sont **facultatifs** : le bureau ne fait qu'afficher ce champ et déposer des demandes ; il n'appelle aucun partenaire et ne connaît **aucune valeur de clé**. Une pièce « Partenaires » s'ajoute au bâtiment quand le champ est présent.

```json
"partenaires": {
  "categories": {"voix-audio": [{"id": "elevenlabs", "nom": "ElevenLabs", "categorie": "voix-audio", "sous_categorie": "synthese-vocale",
                                 "inscription": "https://…", "connexions": [{"type": "mcp", "url": "https://…", "commande": "claude mcp add …"}],
                                 "plans": [{"nom": "Gratuit", "prix": 0, "devise": "USD", "periode": "mois", "quota": "…", "tarif": "gratuit"}],
                                 "gratuit": "…", "quota_lisible": "oui", "illimite": false, "statut": "actif",
                                 "description": "À quoi sert le partenaire et ce qu'il contient (280 caractères au plus).",
                                 "popularite": {"niveau": 4, "base": "npm 5 M sur 30 jours", "date": "2026-11-11"},
                                 "fiabilite": "officielle", "verifie_le": "2026-11-11"}]},
  "etat": {"connexions": {"elevenlabs": {"etat": "connecte", "source": "…", "abonnement": "Pro", "vu_le": "2026-11-11T10:00:00"}},
           "quotas": {"elevenlabs": {"reste": 4200, "unite": "caractères", "lu_le": "2026-11-11T10:05:00"}},
           "limites": {"echo": {"depuis": "2026-11-11T09:00:00", "raison": "quota épuisé"}},
           "regles": {"tripo": [{"id": "r1", "texte": "…", "cree_le": "2026-11-11"}]},
           "inscriptions": {"tripo": {"depuis": "2026-11-12T10:00:00+01:00", "note": "compte gratuit"}}},
  "conseils": {"voix": [{"id": "elevenlabs", "raison": "…"}]},
  "maj_catalogue": "2026-11-11",
  "cout_maj": {"euros": 0.4, "texte": "Environ 40 fiches sur Sonnet."}
}
```

`categories` est le catalogue réduit aux champs affichés (obligatoire) ; tout identifiant de `etat` et de `conseils` doit y figurer. `etat.connexions[id].etat` vaut `connecte`, `declare` (« déclaré, à vérifier ») ou `non_connecte`. `etat.inscriptions[id]` (facultatif) = `{depuis (date), note? (200 caractères au plus)}` : l'utilisateur a un compte chez ce partenaire **sans liaison directe** (« inscrit ») ; l'état affiché est « connecté » s'il est connecté, sinon « inscrit » s'il a une inscription ; jamais un identifiant ni un mot de passe. Les agents n'appellent pas un partenaire inscrit : ils préparent une demande « À faire chez … » (décision `faire_chez_partenaire`). Un quota absent s'affiche « quota inconnu », jamais zéro ; `illimite: true` s'affiche « illimité » ; les dates sont montrées avec le quota (rien n'est montré comme actuel sans sa date). Seuls les liens `https://` sont rendus. `cout_maj` (facultatif) est le coût estimé que la fenêtre de confirmation de « Mettre à jour les offres » affiche avant la demande `partenaires_maj`.

La facturation peut porter `partenaires` : `{id: {nom, total (euros), origine: [{montant, devise}], estime, non_chiffre, usages, taches: {tache: euros}}}`, une ligne par partenaire ; un coût absent compte « non chiffré », jamais zéro.

## Créer un projet depuis le bureau (routes `/api/creations*`)

Le bureau qui suit plusieurs projets (fichier de bureau commun) crée un projet en deux fenêtres (voir « Créer un projet depuis le bureau » dans [installation.md](installation.md)). Ces routes ne passent pas par la commande d'actions d'un projet, qui n'existe pas encore : elles portent des **brouillons** gardés dans le dossier commun de MyIAFactory (jamais de clé, ni dans un projet), et exigent les mêmes en-têtes et le même code d'accès que les autres écritures.

| Route | Corps | Effet |
|---|---|---|
| `GET /api/creations` | — (ou `?id=` pour un brouillon) | les brouillons à reprendre, avec leur coût en euros, et le coût des échanges abandonnés |
| `POST /api/creations/infos` | `parent`, `nom`, `description`, … (+ `id` pour changer un brouillon) | première fenêtre validée : contrôle du nom et du dossier, brouillon créé ; rien n'est encore écrit dans un projet |
| `POST /api/creations/tour` | `id`, `reponses?`, `correction?`, `proposer_maintenant?` | un tour d'échange avec le chef (jugement `definir_workflow`), lancé en arrière-plan : la réponse marque le brouillon `tour: "en_cours"`, la page le relit ; 4 tours de questions au plus avant la proposition |
| `POST /api/creations/valider` | `id` ; facultatifs : `fable` (les clés des agents cochés pour Fable), `installer` (vrai : créer la tâche d'installation des outils), `genre_description` (la phrase du genre nouveau) | crée le projet avec son workflow de genre, ses services, ses agents et son genre, l'inscrit au bureau, verse les usages de l'échange à son relevé |
| `POST /api/creations/supprimer` | `id` | abandonne le brouillon (ses usages restent comptés) |

Une demande du genre du projet reprend ensuite ce workflow sans nouvelle proposition (action `reprendre` de la commande `organisation`, voir [interface.md](../orchestrateur/interface.md)).
