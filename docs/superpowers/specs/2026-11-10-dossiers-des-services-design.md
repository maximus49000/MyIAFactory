# Les dossiers des services — conception

Date : 2026-11-10. Projet 2 de la vision. Suite de `2026-11-10-bureau-vivant-design.md` (la conception du bureau) et de `2026-11-10-bureau-qui-agit-design.md` (« le bureau qui agit ») : à lire avant celle-ci.

Convention : ce qui vient de l'utilisateur est écrit sans mention. Ce qui est un choix du rédacteur est marqué **[choix]**.

## 1. Pourquoi

Le panneau d'un service ne montre aujourd'hui que ses agents (prénom, modèle, statut). L'utilisateur veut y ouvrir un vrai **dossier** pour pouvoir :

- voir les **tâches en cours** du service ;
- lire les **connaissances** du service ;
- les **challenger** : chercher l'optimisation. Si un service a laissé passer deux fois le même problème (exemple de l'utilisateur : un défaut de dev qui passe deux fois au contrôle), cela remonte dans ses KPI, et l'utilisateur peut ouvrir un « challenge » pour faire sortir des solutions ;
- voir les **KPI** de chaque service ;
- consulter la **facturation** : tous les coûts, du total (macro) jusqu'au détail (micro), et les sources d'amélioration.

## 2. Buts, non-buts, contre-buts

**Buts.** Un dossier par service, au même format pour tous les services, avec quatre onglets. Un coût en euros estimé, calculé à partir des tokens, qui suit les prix des modèles tout seul. Un geste « Challenger » qui mène à une connaissance validée.

**Non-buts.** **[choix]** Pas d'écran de facturation avec paiement ou export comptable : les chiffres sont des estimations pour piloter, pas une facture. Pas de plafond de dépense qui coupe la factory dans ce projet. Pas d'accès depuis le téléphone (déjà écarté par le projet précédent). Le parcours d'une tâche (création, cahier des charges, boucle QA, choix de l'agent et du modèle) est le projet 3 et n'est pas fait ici.

**Contre-buts** (ce qui ferait un échec même si cela « marche »). Un euro affiché comme exact alors qu'il est estimé. Des chiffres passés qui bougent quand un prix change. Un prix automatique faux ou périmé sans que personne le sache. Le bureau qui agit à la place du projet. Un nom, un chemin ou un fichier propre à un projet réel dans ce dépôt public.

## 3. Les règles qui ne bougent pas

- Le dépôt reste **vide de tout projet** : tout ce qui est propre à un projet passe par le relevé.
- **Le bureau n'agit jamais lui-même** sur la factory : chaque geste devient une demande remise à la commande d'actions du projet, et son effet n'apparaît qu'au relevé suivant.
- Python : bibliothèque standard seulement. Les textes venus du projet ou d'Internet s'affichent comme du texte (jamais du HTML).
- Un relevé version 1 ou 2 continue de marcher tel quel.

## 4. Ce que l'utilisateur voit

**[choix]** pour la disposition de cette section (l'utilisateur a choisi sur maquette : **quatre onglets**, le geste « Challenger » comme montré). Le dossier s'ouvre dans le panneau de droite déjà en place quand on clique un service.

En-tête : le nom du service, un sélecteur de période (**aujourd'hui, 7 jours, 30 jours**, 7 jours par défaut **[choix]**), puis les onglets :

1. **Tâches** : les tâches en cours du service, chacune avec son agent, son étape, son coût estimé ; un clic ouvre le panneau de la tâche existant. Les alertes du service (voir KPI) sont rappelées en haut, avec leur bouton « Challenger ».
2. **Connaissances** : la vue d'ensemble du service = les connaissances de tous ses agents, groupées par agent. Chaque connaissance a son texte, sa date, la tâche ou le challenge d'où elle vient, et un bouton « Challenger ».
3. **KPI** : une grille de chiffres avec leur évolution sur la période (voir §7). Un KPI en alerte est marqué et a un bouton « Challenger ».
4. **Facturation** : le total estimé en euros du service sur la période, puis le détail (voir §5).

Le geste « Challenger » (sur une alerte, un KPI ou une connaissance) ouvre un volet : ce qui s'est passé (le texte de l'alerte et les tâches concernées), les **solutions proposées**, chacune avec son auteur (**le Directeur, le service, ou l'utilisateur**), une zone pour écrire sa propre solution, et un bouton « Valider la sélection » (§6).

Tout est en lecture seule sauf ces gestes. Après un geste, la page affiche « Demande envoyée » ; l'effet apparaît au relevé suivant.

## 5. La facturation

**Ce que l'utilisateur a décidé.** On compte les **tokens**. On affiche un **prix en euros, approximatif**, calculé d'après le nombre de tokens (en millions), le **modèle utilisé** et la **fluctuation de son prix**. Les chiffres se lisent **par discussion, par modèle, par développement et par étape** (le « développement » est la tâche, ou la micro-tâche ; l'« étape » est celle de la tâche). Les prix se mettent à jour **automatiquement**, ce qui est accepté comme un coût de gestion. L'utilisateur accepte que le bureau fasse des requêtes sortantes pour cela.

**[choix] Qui compte quoi.** Le bureau ne peut pas compter les tokens (il ne connaît aucun projet) : le projet les fournit, en tokens bruts. Le bureau les convertit en euros et additionne.

**[choix] Les relevés d'usage.** Une nouvelle liste `usage` dans le relevé version 3 : chaque entrée est une discussion, `{id, tache, agent, modele, etape?, t, entree, sortie, cache_lecture?, cache_ecriture?}` (compteurs de tokens entiers ≥ 0). `tache` et `agent` sont des identifiants connus (ou nuls : un usage sans tâche, par exemple celui du Directeur, est rangé dans « hors tâche »). Le relevé ne porte que les usages récents ; le bureau les range dans son propre historique (`usage-historique.jsonl` à côté des réglages, comme `charge-historique.jsonl`) en dédoublonnant par `id`, de sorte qu'un usage enregistré ne disparaît pas si le projet le retire du relevé. Les usages d'un service sont ceux de ses agents.

**[choix] Sémantique d'un usage.** Les compteurs d'un `id` sont des **cumuls** : si le projet republie le même `id` avec des compteurs plus grands, le bureau garde les derniers compteurs. En revanche la **date de prix** d'un usage est fixée à sa première apparition (son `t` tel que vu la première fois) et le **service** est celui de l'agent à ce moment-là, enregistré dans l'historique : un coût passé ne bouge ni quand un prix change, ni quand un agent change de service ou quitte le relevé. L'usage du chef et celui d'un usage sans service sont rangés dans « direction / hors service ». `tache` est l'identifiant d'une tâche du relevé : la micro-tâche n'existe pas dans le relevé, donc « par développement » veut dire par tâche pour l'instant (la micro-tâche viendra si le projet en déclare). « Par étape » est le champ `etape` de l'usage.

**[choix] Le calcul.** Prix d'un usage = tokens × prix par million du modèle à la date `t` de l'usage, converti en euros au taux de cette date. Les prix distinguent entrée, sortie et, si la source les donne, les deux sortes de cache. Les totaux se lisent à cinq niveaux : discussion, étape d'une tâche, tâche, modèle, service ; plus le total général et la ligne **gestion**. Un modèle dont le prix est inconnu n'est pas compté à zéro : l'usage est montré avec « prix inconnu » et ses tokens, et exclu des euros avec une mention visible.

**[choix] Les prix automatiques.** Un module du bureau met à jour, au plus une fois par jour et au démarrage, une table de prix datée :

- prix des modèles par million de tokens : lus dans une liste publique de la communauté (le fichier de prix de LiteLLM, sur GitHub) ; aucune source officielle lisible par programme n'est connue du rédacteur ;
- taux dollar-euro : lu dans la source publique de la BCE ;
- chaque lecture ajoute une ligne datée à `prix-historique.jsonl` ; **le prix qui compte pour un usage est le dernier prix enregistré à la date de l'usage ou avant** : les chiffres passés ne bougent plus ;
- si une source est injoignable, ou donne une valeur absurde (négative, nulle, ou qui change de plus d'un facteur 10 d'un jour à l'autre **[choix]**), le bureau garde le dernier prix connu et le signale dans l'onglet Facturation (« prix du 3 novembre, mise à jour impossible ») ;
- **[choix]** un usage plus ancien que le premier prix enregistré prend ce premier prix, marqué « prix du jour de l'installation » dans l'info-bulle ; le premier jour, le bureau lit les prix tout de suite, avant de calculer ;
- l'utilisateur peut **corriger un prix à la main** dans les réglages (`prix`) : la correction passe avant l'automatique, avec sa date ;
- les noms de modèle du relevé sont rapprochés de la liste par une table d'alias dans les réglages (le projet écrit « sonnet », la liste dit autre chose) ; un nom sans correspondance donne « prix inconnu » ;
- les euros s'affichent précédés de « ≈ », jamais comme une facture ; une info-bulle donne la date des prix utilisés.

Le coût de ces mises à jour (le temps de la requête, nul en tokens) est la ligne **gestion** de la facturation, qui compte aussi les tokens des commandes du bureau lui-même s'il y en a **[choix : interprétation de « on le comptera comme un coût de gestion »]**.

**[choix] Les sources d'amélioration.** Dans l'onglet Facturation, une liste calculée par le bureau : les tâches dont le coût dépasse trois fois la médiane du service sur la période ; les usages où un modèle de la gamme la plus chère a servi à une étape où la médiane des autres usages est d'un modèle moins cher ; la part du coût que représentent les allers-retours (tâches qui ont reçu plusieurs retours). Chaque ligne a un bouton « Challenger ».

## 6. Challenger : du problème à la connaissance

**Les connaissances.** Chaque agent a des connaissances (texte, date, origine). **[choix]** Les leçons « validées » qui existent déjà sont des connaissances ; le bureau les range donc dans cette liste, avec les connaissances que le projet donne en plus. Un agent est un titulaire ; le service voit la somme.

**Le cycle.**

1. Un problème remonte : une alerte KPI, une source d'amélioration, ou une connaissance que l'utilisateur veut contester.
2. L'utilisateur clique « Challenger » : demande `challenge` `{cible, texte?, solution?}` (§8). **[choix]** Il peut écrire sa propre solution dans le même geste (`solution`) ; une solution ajoutée plus tard passe par la demande `solution` `{challenge, texte}`, possible seulement sur un challenge déjà présent dans le relevé. Un second clic sur une cible qui a déjà un challenge ouvre le challenge existant au lieu d'en créer un autre ; tant que la première demande n'est pas dans le relevé, le bouton affiche « Demande envoyée » et ne renvoie rien.
3. Le projet répond au relevé suivant en déposant des **solutions proposées** sur le challenge, avec leur auteur (le Directeur ou le service) : l'utilisateur, le service et le Directeur peuvent donc tous proposer.
4. L'utilisateur coche une ou plusieurs solutions et valide : demande `verdict_solution` `{challenge, solution, verdict}`. `verdict` : `"valider"` ou `"ecarter"`. **[choix]** Une demande par solution cochée, envoyées l'une après l'autre ; une solution non cochée reste en l'état (ni validée ni écartée). Si l'une est refusée, la page dit lesquelles sont parties et lesquelles ne le sont pas, sans rien annuler.
5. Au relevé suivant, le projet a inscrit la solution validée dans les connaissances des agents concernés, avec la date et le problème qui l'a provoquée ; les agents l'appliquent aux tâches suivantes.
6. Le KPI du problème (§7) dit ensuite si le problème est revenu : le bureau marque la connaissance « problème revenu » si le KPI d'origine est de nouveau en alerte après la date de la connaissance **[choix]**.

Le bureau n'invente jamais une solution et n'écrit jamais une connaissance : c'est le projet qui le fait, sur demande.

**Chaque agent apprend des retours des autres agents** (précision de l'utilisateur). Quand un agent reçoit un retour (de l'utilisateur ou du contrôle) sur une tâche, ce qu'on en tire n'est pas réservé à lui : les autres agents en profitent. Le bureau ne fait pas cet apprentissage (c'est le projet qui l'organise) ; il le **rend visible** :

- **[choix]** une connaissance peut porter `appris_de` : liste `{agent, tache?, retour?}` (l'agent dont le retour est la source, la tâche, la date du retour). Le dossier l'affiche : « appris du retour de Hugo sur *Export CSV* » ;
- **[choix]** la vue d'ensemble du service met en évidence ce qui circule : une connaissance qu'un agent a reçue d'un autre est marquée « partagée », avec qui l'a apprise et qui l'a fournie ; un agent qui n'a rien reçu depuis la période est visible (il n'apprend peut-être pas) ;
- **[choix]** le partage s'étend à tous les agents du projet, pas seulement ceux du même service : le projet décide quels agents reçoivent quoi, le bureau montre le résultat, et c'est le projet qui donne la liste des agents concernés dans `appris_de` / `connaissances`. **Confirmé par l'utilisateur** : le partage se fait entre tous les services ; l'onglet Connaissances d'un service montre aussi ce que ses agents ont reçu d'un autre service, et « n'a rien reçu depuis la période » se compare à tout le projet ;
- un retour qui a produit une connaissance partagée est un cas d'usage du challenge : l'utilisateur peut contester une connaissance « partagée » comme n'importe quelle autre ; la décision (§6, étape 4) s'applique alors à tous les agents qui l'ont reçue.

## 7. Les KPI

Les KPI sont une **liste ouverte** (l'utilisateur veut pouvoir en ajouter plus tard) : le relevé donne, par service, une liste `{id, nom, valeur, unite?, evolution?, alerte?, texte?}` ; `alerte` est vrai si le projet juge le seuil franchi, `texte` explique l'alerte (« remises : défaut passé 2 fois au contrôle »). Le bureau les montre tels quels : il ne connaît aucune règle d'un projet. **[choix]** `evolution` est un texte court affiché tel quel (« +2 depuis hier »). `valeur` est celle du projet : les KPI du projet ne suivent pas le sélecteur de période, sauf si le projet donne `periodes` (`{"aujourdhui": v, "7j": v, "30j": v}`) ; sans `periodes`, le KPI est marqué « toutes périodes ». Pour la règle « problème revenu » (§6), le bureau garde la date de la première alerte de chaque KPI dans un petit fichier d'historique à côté des réglages (`alertes-historique.jsonl`) : étape 4 du découpage.

**[choix]** Le bureau calcule lui-même, en plus, ceux qu'il peut tirer du relevé : coût total et coût moyen par tâche (§5), tâches terminées sur la période (tâches dans une colonne `terminee` dont `maj` tombe dans la période), allers-retours moyens par tâche (nombre de `retours`), durée moyenne d'une tâche (de la première entrée du journal à la dernière). L'utilisateur a validé ces cinq-là comme premier jeu : **tâches terminées, défauts passés au contrôle, allers-retours, durée d'une tâche, coût moyen par tâche**. Le deuxième (« défauts passés ») ne peut venir que du projet : il le donne comme KPI avec `alerte` dès la deuxième occurrence (l'utilisateur a dit « deux fois »).

## 8. Le relevé version 3 et les demandes

**[choix]** Le relevé passe à `version: 3`. Les versions 1 et 2 sont acceptées telles quelles et n'ont ni dossier enrichi ni facturation. Tous les ajouts sont facultatifs. Le bureau détecte l'absence et masque l'onglet concerné.

Ajouts au relevé :

- `usage` : voir §5 ;
- par service : `kpi` : voir §7 ;
- par titulaire : `connaissances` : liste `{id, texte, date?, origine?, appris_de?}` (`origine` : texte libre ou identifiant de challenge ; `appris_de` : voir §6) ;
- `challenges` : liste `{id, cible, texte, date?, solutions: [{id, texte, auteur, etat?}]}` ; `auteur` : `"directeur"`, `"service"` ou `"utilisateur"` ; `etat` : mot court (« proposée », « validée », « écartée ») ; `cible` : `{type: "kpi"|"connaissance"|"source", id}` ;
- `types`, `lecons` et les autres champs de la version 2 sont inchangés.

Nouvelles demandes (même circuit que celles qui existent : JSON sur l'entrée standard de la commande d'actions, `t` ajouté, comparées au dernier relevé valide avant envoi) :

| `type` | Champs | Sens |
|---|---|---|
| `challenge` | `cible` (`{type, id}`), `texte?`, `solution?` | ouvrir un challenge sur cette cible, avec éventuellement sa solution |
| `solution` | `challenge`, `texte` (3 500 caractères au plus) | l'utilisateur ajoute sa solution à un challenge existant |
| `verdict_solution` | `challenge`, `solution`, `verdict` | valider ou écarter une solution |

**[choix] Les cibles calculées par le bureau** (sources d'amélioration, KPI calculés) ont des identifiants que le bureau fabrique de façon déterministe : `kpi:<service>:<id>` et `source:<service>:<genre>:<tache>`. Le bureau vérifie une demande `challenge` contre ce qu'il recalcule à partir du dernier relevé, et remplit lui-même `texte` avec le constat en clair (« coût de 4,2 € pour une médiane de 1,1 € ») pour que le projet comprenne. Les `id` de KPI sont uniques par service ; ceux des connaissances, des leçons, des challenges et des solutions le sont dans tout le relevé (les leçons et les connaissances partagent le même espace : en cas de doublon d'`id`, la connaissance l'emporte).

La fraîcheur : un challenge dont la demande est partie mais qui n'est pas encore dans le relevé s'affiche « Demande envoyée », comme les verdicts de leçons.

## 9. Les réglages

Ajouts au fichier de réglages du projet (tous facultatifs) : `prix` (corrections à la main : modèle → prix par million entrée/sortie en euros, avec date), `alias_modeles` (nom du relevé → nom de la liste de prix), `prix_automatiques` (`true` par défaut ; `false` coupe toute requête sortante). **[choix]** L'adresse des deux sources est dans le code, pas dans les réglages, pour qu'un réglage ne puisse pas rediriger les requêtes ailleurs.

## 10. Découpage et ordre

**[choix]** Un seul projet, une conception, un plan, réalisé en quatre étapes dans cet ordre, chacune testée et livrée :

1. la facturation : relevé version 3 (`usage`), historique des usages et des prix, mise à jour automatique des prix, calcul en euros, état serveur ;
2. le dossier à quatre onglets, l'onglet Tâches et l'onglet Facturation ;
3. les connaissances et le geste « Challenger » (relevé `connaissances`, `challenges`, trois demandes) ;
4. les KPI.

## 11. Ce qui est laissé au réalisateur

La structure interne des modules, le format exact des fichiers d'historique, la mise en page fine des quatre onglets, les noms de fichiers, l'interprétation des champs du fichier de prix de la source communautaire, la façon de tester les requêtes sortantes (sources simulées), le détail des textes affichés. Le plan doit prévoir des tests avec des sources de prix inventées : aucun test ne doit sortir sur Internet.

## 12. Points à vérifier à la relecture

Que rien de ce qui est propre à un projet réel n'entre dans le dépôt. Qu'aucune requête sortante ne parte quand `prix_automatiques` est faux ou en test. Qu'un prix qui change ne modifie jamais un coût passé. Qu'un modèle sans prix ne fausse pas les totaux sans le dire. Que les textes venus de la source de prix ou du projet s'affichent littéralement.
