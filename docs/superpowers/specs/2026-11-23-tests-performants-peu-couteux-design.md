# Des tests rapides et peu coûteux — conception

Date : 2026-11-23. Statut : **conception validée dans son principe par le Directeur (les trois approches sont décidées) ;
rien n'est implémenté.** Branche `tests-economes-conception`, à partir de `main` (d0b6ab7).

## 1. L'intention, et pourquoi

« Des tests rapides et peu coûteux, assurés par la plateforme pour tous les projets qu'elle développe, et pour le dépôt
MyIAFactory lui-même. » Rapide **et** économe, en temps **et** en argent (tokens), avec une règle que les agents ne
contournent pas et une mesure qui ne dérive pas en silence.

Ce qui s'est passé au dernier chantier : la suite complète de MyIAFactory est passée d'environ 4 minutes (253 s, chiffre
de `CLAUDE.md`) à **747 s (4 538 s cumulées)**, sans que personne ne le voie avant la fin. Cause principale : cinq
modules `serveur_*` lancent de vrais `bash` / `git` sous Windows. Aggravants : des agents ont relancé des campagnes
voisines « par prudence » et demandé des relectures séparées de tout petits correctifs. La règle R4 (seulement les tests
touchés pendant le travail, la suite complète une fois à la fin, un seul passage RED, pas de relecture séparée d'un petit
correctif tenu par un test sauf code sensible) existait, mais seulement comme consigne, sans mesure derrière.

Une branche parallèle (`tests-rapides`) réduit la durée actuelle ; **ce document ne traite pas de cette réduction**, il
empêche la prochaine dérive.

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs.**
1. Chaque agent (local, cloud, serveur) reçoit au départ une consigne « Des tests rapides et peu coûteux », courte et
   ferme.
2. La plateforme mesure chaque campagne de tests qu'elle lance, la compare à un budget propre au projet (défaut :
   5 minutes pour la suite complète) et, au dépassement, alerte le Directeur au bureau puis propose (ou crée, sur son
   accord) une tâche « Accélérer les tests ». Le coût des tests est visible dans la Facturation.
3. À l'installation, la skill `installer` mesure une référence, fait fixer le budget par le Directeur et écrit les
   conventions de tests dans le fichier d'instructions du projet, de façon idempotente et réversible.
4. Le dépôt MyIAFactory s'applique les mêmes règles : `CLAUDE.md` mis à jour, `outils/tests_paralleles.py` qui avertit
   (et échoue en mode strict) au-delà de son budget.

**Non-objectifs.** Accélérer la suite actuelle (branche `tests-rapides`). Exécuter les tests sur le serveur OVH (voir
`docs/superpowers/specs/2026-11-20-tests-sur-le-serveur-design.md`, encore non suivi dans le dépôt : la mesure conçue
ici devra simplement accepter `lieu: "serveur"` le jour venu). Juger la qualité des tests.

**Anti-objectifs.** Un dépassement de budget **ne fait jamais échouer la campagne d'un agent** : sinon le chemin le plus
court vers le vert serait d'affaiblir ou de supprimer des tests. Pas de mesure qui coûte elle-même des tokens ou un
processus de plus. Pas de nouvelle relecture, ni de nouvel appel de jugement, pour surveiller.

## 3. Les contraintes

- **Une seule campagne à la fois sur le poste** (`outils/campagne.py`, verrou `~/MyIAFactory/tests-en-cours.json`,
  file `~/MyIAFactory/tests-en-attente/`). La mesure ne doit compter que l'exécution, pas l'attente du verrou.
- **Deux chemins d'entrée** pour `lancer.py tests` : `deporter.lancer_tests` envoie soit vers `campagne.main` (poste),
  soit vers `deporter.main` (GitHub Actions). La mesure doit vivre aux deux.
- **Cloud et serveur n'ont pas le lanceur du poste** (`LIEUX_SANS_POSTE = ("cloud", "serveur")` dans
  `orchestrateur/depart.py` : ni `tests_un_a_la_fois()` ni le déport ne leur sont ajoutés). Leur seule voie de retour
  est le rapport (`.factory/rapports/<tâche>.json` pour le cloud, le rapport de l'agent serveur sinon).
- **Le poste est un seul utilisateur du système** : tout fichier que le lanceur écrit, un agent local peut l'écrire
  aussi. Même limite que celle dite franchement pour R10 (`docs/serveur-taches.md`, « L'accord du Directeur »).
- **Coût du message de départ** : chaque ligne ajoutée se paie à chaque départ d'agent (`SOBRIETE` le rappelle). La
  nouvelle section **remplace** `tests_un_a_la_fois()`, elle ne s'y ajoute pas.
- PC de 7,5 Go : pas de démon de surveillance supplémentaire ; le moteur et le bureau tournent déjà.
- `deporter` reste compatible Python 3.9 (les agents le lancent avec n'importe quel Python).

## 4. Les approches envisagées (le COMMENT)

Les trois approches sont décidées ; restent, pour chacune, des choix de construction.

### 4.1 Où vit la mesure

| Option | Pour | Contre |
|---|---|---|
| A. Dans `campagne.executer` (et dans le suivi du run de `deporter`) | Déjà sur le chemin de toute campagne ; connaît la commande, le dossier, la tâche (`MYIAFACTORY_TACHE`) ; zéro processus en plus | Ne voit pas le cloud ni le serveur |
| B. Le moteur chronomètre l'agent | Couvre tous les lieux | Ne distingue pas les tests du reste du travail : inutilisable |
| C. Déclarée par l'agent dans son rapport | Seule voie en cloud / serveur | Non vérifiable |

**Recommandé : A pour le poste et GitHub (mesuré), C pour cloud et serveur (déclaré, affiché comme tel, jamais seul
déclencheur d'une alerte).** Quand les tests passeront par le serveur (spécification du 2026-11-20), ils passeront par
`deporter` et deviendront mesurés sans autre changement.

### 4.2 Où est rangé le budget

| Option | Pour | Contre |
|---|---|---|
| A. `reglages.json` du projet (`.factory/`), clé `tests` | Comme tous les réglages (`bureau/reglages.py`, `fixer_*`) ; visible et réglable au bureau | Un agent local peut l'écrire ; versionné dans un projet dont `.factory/` est suivi |
| B. Fichier central hors projet, `~/MyIAFactory/tests-sceau.json` | Hors de l'arbre de travail des agents ; inatteignable du cloud et du serveur | Une donnée de plus hors du projet |
| C. A + B : réglage affiché dans A, **valeur qui fait foi dans B**, écrite seulement par le geste du bureau | Lisible comme les autres réglages, et une écriture d'agent dans A est vue | Deux endroits à tenir alignés |

**Recommandé : C.** Le sceau fait foi ; un écart entre les deux est lui-même une alerte (section 5.5).

### 4.3 Comment l'alerte apparaît

| Option | Pour | Contre |
|---|---|---|
| A. Anomalie du logiciel (`.factory/anomalies-logiciel.jsonl`) | Existe, lue en début de session | Réservée aux défauts **du logiciel**, pas du projet |
| B. Simple notification au bureau | Légère | Rien à décider : s'oublie |
| C. **Décision de Direction** (nouveau genre de `DECISIONS_PROJET`, posée par `lancer decision`) | Le canal des choix du Directeur ; boutons ; trace | Un genre de plus à vérifier (`bureau/demandes.py`) |

**Recommandé : C** pour les projets ; **A** pour une dérive détectée sur le dépôt MyIAFactory lui-même quand il est
piloté par la plateforme (c'est alors bien un défaut du logiciel).

### 4.4 Comment cloud et serveur reçoivent la consigne

| Option | Pour | Contre |
|---|---|---|
| A. La même section, en variante sans lanceur, ajoutée par `message()` / `message_lot()` pour tous les lieux | Un seul texte, une seule fonction testée | Deux variantes à garder alignées |
| B. Dans `consigne_serveur()` et `fin_cloud()` | Proche du reste de leur consigne | Texte dupliqué en trois endroits |

**Recommandé : A** : une fonction `tests_rapides(lieu)` qui rend la section commune et la ligne propre au lieu.

## 5. La conception

### 5.1 Approche 1 — la consigne de départ

`tests_rapides(lieu)` remplace `tests_un_a_la_fois()` dans `message()` et `message_lot()`, **pour tous les lieux**
(la condition `fiche["lieu"] not in LIEUX_SANS_POSTE` ne garde plus que le paragraphe du lanceur et le déport). Texte
exact de la section commune :

```
## Des tests rapides et peu coûteux
Chaque minute de test se paie deux fois : en temps, et en tokens quand tu lis la sortie.
- Pendant ton travail, lance **seulement les tests touchés** par ta tâche. La suite complète : **une fois au plus, à
  la fin**, et seulement si ta tâche le demande. Ne relance jamais la campagne d'un autre « par prudence ».
- Un test n'attend jamais pour de vrai : pas de `sleep` réel ; l'horloge, les délais et les attentes se simulent.
- Prépare une fois ce qui coûte (fixtures partagées par classe ou par module) ; ne lance pas de processus (shell, git,
  navigateur, émulateur) quand un appel direct suffit.
- **N'affaiblis, ne supprime, ne saute jamais une assertion ou un test pour gagner du temps.** Un test lent se rend
  plus rapide, jamais moins exigeant.
- Un seul passage en rouge suffit pour un correctif ; pas de relecture séparée d'un petit correctif tenu par un test,
  sauf code sensible.
- Dans ton résultat, donne la durée de ce que tu as lancé, en `tests` : `[{"commande", "portee": "touches" ou
  "complete", "duree_s", "code"}]`.
```

Ligne propre au lieu :
- **local** : le paragraphe actuel du lanceur (`python "<lancer.py>" tests --dossier … -- <commande>`), suivi de
  « Le lanceur mesure chaque campagne ; la plateforme compare la suite complète au budget du projet (<N> min). »
- **cloud** et **serveur** : « Ici, pas de lanceur : ta déclaration `tests` est la seule mesure. Elle est affichée au
  Directeur comme déclarée. »

Le budget `<N>` vient du sceau (section 5.2). Plafond : la section, budget compris, tient en 1 200 caractères
(l'actuelle en fait environ 750) ; un test le vérifie. Le champ `tests` du rapport est facultatif : le builder vérifie
que `moteur/rapport.py` accepte un champ en plus sans refuser le rapport, puis le moteur le reporte au journal
(section 5.2) avec `source: "declare"`.

### 5.2 Approche 2 — la mesure, le budget, l'alerte

**Le journal des campagnes.** `.factory/tests-mesures.jsonl` du projet **enregistré** (résolu par
`~/MyIAFactory/bureau.json`, comme R10 : un sous-dossier ou une copie de travail est rangé sous son projet ; un dossier
non enregistré n'écrit rien). Ajouté au `BLOC_GITIGNORE` de `installation/mise_en_place.py` (propre à la machine). Une
ligne par campagne :

```
{"t": "2026-11-23T10:12:03+01:00", "lieu": "poste" | "github" | "cloud" | "serveur",
 "source": "mesure" | "declare", "tache": "<MYIAFACTORY_TACHE ou null>", "commande": "<≤ 200 car.>",
 "portee": "complete" | "partielle", "duree_s": 412.6, "attente_s": 35.0, "code": 0,
 "nb_tests": 318 | null, "sortie_octets": 48211 | null}
```

- `duree_s` : de la prise du verrou à la fin de la commande ; l'attente va dans `attente_s`.
- `portee` **n'est jamais déclarée par l'agent** au poste : `complete` si la commande est exactement la commande de
  suite complète enregistrée (`tests.commande_complete`, fixée à l'installation, section 5.3), `partielle` sinon.
- `sortie_octets` et `nb_tests` : la sortie de la commande est relayée telle quelle à l'agent par un tuyau dont le
  lanceur compte les octets et lit les dernières lignes (`Ran N tests`, `N passed`, `Tests  N passed`…). Aucun
  processus en plus ; un format non reconnu donne `null`, jamais une erreur.
- Lignes de plus de 2 Ko ou illisibles : ignorées à la lecture. Au-delà de 2 000 lignes, les plus anciennes partent
  (comme `MAX_ANOMALIES`).

**Le budget.** Dans le sceau `~/MyIAFactory/tests-sceau.json`, par identifiant de projet :

```
{"<id projet>": {"budget_s": 300, "commande_complete": "npx vitest run", "reference_s": 241,
                 "campagnes": 57, "cumul_s": 9120.4, "derniers_nb_tests": 318, "maj": "<date>"}}
```

et, en miroir pour l'affichage, `reglages.json` → `"tests": {"budget_s": 300, "commande_complete": "…"}` (défaut
ajouté à `DEFAUTS` : `{"budget_s": 300, "commande_complete": null}`). Bornes : 60 à 3 600 s. Seul le geste du bureau
écrit les deux : une nouvelle demande `budget_tests` (`CHAMPS`: `("budget_s",)`, facultatif `commande_complete`) et
`reglages.fixer_budget_tests()`, sous `_verrou_fichier` comme les autres `fixer_*`.

**La règle d'alerte** (pure, une fonction, lue par le moteur à son tour de boucle, seulement si l'heure de
modification du journal a changé) :
1. **Suite trop longue** : la médiane des 3 dernières campagnes `complete` mesurées dépasse le budget, ou une seule
   dépasse 1,5 fois le budget. La médiane évite qu'un poste chargé déclenche à tort.
2. **Suite relancée** : plus d'une campagne `complete` pour la même tâche (R4).
3. **Tests disparus** : `nb_tests` d'une campagne `complete` verte inférieur de plus de 2 % au précédent sans que le
   Directeur l'ait vu (garde contre l'affaiblissement).
4. **Partielle démesurée** : une campagne `partielle` plus longue que le budget de la suite complète.

Une alerte ouverte à la fois par motif ; elle ne revient qu'aggravée de 20 % ou après un changement de budget.

**La décision.** Nouveau genre `tests_lents` dans `DECISIONS_PROJET` (`bureau/releve.py`), posé par le moteur via
`lancer decision` (`action: poser`, `portee: projet`), avec `motif`, `mesure_s`, `budget_s`, `lents` (les 5 morceaux
les plus longs connus, quand le lanceur les connaît). Textes exacts :
- motif 1 : « Les tests de ce projet dépassent leur budget : la suite complète prend <12 min 27 s> (médiane des 3
  dernières campagnes), pour un budget de <5 min>. Chaque campagne en plus coûte ce temps à un agent qui attend. »
- motif 2 : « La suite complète a été lancée <3> fois pour la tâche « <titre> » : la règle est une fois, à la fin. »
- motif 3 : « La suite complète compte <12> tests de moins qu'à la campagne précédente (<318> → <306>), tous verts.
  Vérifiez qu'aucun test n'a été supprimé ou sauté pour gagner du temps. »
- motif 4 : « Une campagne partielle a duré <7 min> : plus que le budget de la suite complète. »

Boutons (verdicts de la demande `tests_lents`) : **« Créer la tâche « Accélérer les tests » »** (`accelerer`),
**« Relever le budget »** (`relever`, ouvre le réglage), **« Plus tard »** (`plus_tard`, rappel à la prochaine
aggravation) ; pour le motif 3 : **« C'est voulu »** (`voulu`, recale `derniers_nb_tests`). « Créer la tâche » passe par
le chemin existant d'une correction (`NATURES` : `correction`), titre « Accélérer les tests », texte : la mesure, le
budget, les morceaux les plus lents et la consigne « sans affaiblir ni supprimer aucune assertion ». Le Directeur peut
cocher « Désormais, créer la tâche sans me demander » (réglage `tests.tache_auto`, faux par défaut).

**Le coût dans la Facturation.** Une fonction pure `cout_des_tests(mesures, prix_de, periode)` à côté de
`bureau/cout.py`, publiée par le relevé (`tests` : campagnes complètes / partielles / relancées, durée cumulée, minutes
GitHub déjà comptées par `bureau/deport_conso.py`, et tokens estimés = `sortie_octets / 4` au prix d'entrée du modèle de
la tâche, **marqués « estimé »**). La vue `bureau/web/ui/facturation.js` (pièce `facturation`) gagne un bloc « Tests »
sur la période choisie ; les déclarations cloud / serveur y sont comptées à part, sous « déclaré ». Le temps passé au
poste n'a pas de prix en euros : il est montré en minutes, jamais converti en silence.

**Codes de sortie.** Inchangés pour `lancer.py tests` : le code de la commande, 3 si refusé sans attendre. Le
dépassement ne change aucun code (anti-objectif). Une écriture du journal qui échoue est tue (comme
`_noter_l_attente`) : la mesure ne casse jamais une campagne.

### 5.3 Approche 3 — l'installation

Nouvelle étape dans `skills/installer/SKILL.md`, section 6, après `outil.py appliquer` :

1. **Trouver la commande de suite complète** : celle du résumé de lecture (section 3b) ou de `deport.commandes.tests` ;
   la redire à l'utilisateur en une ligne. Projet vide : aucune ; le budget par défaut s'applique et la mesure se fera
   à la première campagne complète.
2. **Mesurer la référence** : `outil.py mesurer-tests "<dossier>"` lance cette commande **par le lanceur** (verrou,
   journal) et rend `{duree_s, code, nb_tests}`. Elle peut être longue : la skill annonce la durée probable et demande
   l'accord avant de lancer.
3. **Fixer le budget par une décision de Direction** : `outil.py` pose la décision `budget_tests` (genre ajouté à
   `DECISIONS_PROJET`) avec la proposition `max(300, référence × 1,25 arrondie à la minute)`. Texte : « La suite
   complète de ce projet prend <4 min 01 s>. Budget proposé : <5 min> ; au-delà, le bureau vous alertera et proposera
   une tâche « Accélérer les tests ». » Boutons : « Valider <5 min> », « Autre budget… ». Sans réponse, 300 s
   s'appliquent.
4. **Écrire les conventions** dans le fichier d'instructions du projet : `CLAUDE.md` s'il existe, sinon `AGENTS.md`
   s'il existe, sinon un `CLAUDE.md` créé. Le bloc est délimité par `<!-- MyIAFactory : tests (début) -->` et
   `<!-- MyIAFactory : tests (fin) -->` : réécrit en place s'il existe (idempotent), jamais dupliqué. Son contenu : la
   section commune de 5.1, la commande de suite complète, la commande des tests touchés si le projet en a une, et le
   budget. `outil.py conventions-tests "<dossier>" --retirer` enlève le bloc, et le fichier s'il ne contient plus rien
   et a été créé par l'outil (noté dans `.factory/`). Écrire dans un fichier du projet suit la règle de l'installation :
   seulement après « je valide ».

### 5.4 Le dépôt MyIAFactory lui-même

- **`CLAUDE.md`** : la section « Les tests » reprend les règles de 5.1 (tests touchés au quotidien, suite complète
  avant de pousser et une fois, pas de `sleep` réel, pas de processus inutile, jamais une assertion affaiblie, pas de
  campagne voisine relancée par prudence, pas de relecture séparée d'un petit correctif tenu par un test) et corrige
  « environ 4 minutes » par le budget : **300 s**.
- **`outils/tests_paralleles.py`** : `BUDGET_SUITE_S = 300` (constante du dépôt : la changer est un diff visible à la
  revue). Le budget ne s'applique qu'à la suite complète (ni filtre, ni `--touches`). Au-delà, la dernière ligne est
  suivie de : « Budget dépassé : 747 s pour un budget de 300 s. Les plus longs : … Créez une tâche « Accélérer les
  tests » plutôt que de relever le budget. » Nouvelle option `--strict` (pour la CI et le crochet avant de pousser) :
  code **5** si la suite est verte mais hors budget (1 reste l'échec, 3 le refus). La campagne ajoute une ligne à
  `.mesures-tests.jsonl` à la racine (même forme qu'en 5.2, à ignorer dans `.gitignore` comme `.durees-tests.json`).
- Tant que `tests-rapides` n'a pas ramené la suite sous 300 s, `--strict` ferait échouer chaque passage : il n'est
  branché nulle part avant (question 3).

### 5.5 Ce qu'un agent ne peut pas contourner — et ce qu'il peut

**Tenu par construction.**
- La mesure au poste est passive : l'agent ne la déclenche pas, ne la déclare pas, ne choisit pas la portée.
- Le budget n'est écrit que par le geste du bureau ; ni la consigne ni le message de départ ne nomment le sceau.
- Cloud et serveur n'atteignent ni le sceau ni le journal du poste ; leurs déclarations ne déclenchent jamais seules
  une alerte.
- Un dépassement n'échoue jamais : rien à gagner à tricher sur la durée.

**Vu, pas empêché** (limites dites franchement, comme pour R10) :
- Un agent local peut écrire `reglages.json` : l'écart avec le sceau donne l'alerte « Le budget des tests a été
  modifié hors du bureau (<10 min> au lieu de <5 min>). » et le sceau garde sa valeur.
- Il peut effacer ou tronquer le journal : le sceau tient des compteurs monotones (`campagnes`, `cumul_s`) ; un journal
  qui en compte moins donne « Des mesures de tests ont disparu du journal du projet. »
- Il peut **écrire le sceau lui-même** (même utilisateur du système) : rien ne l'empêche au poste. Piste de
  durcissement, non retenue ici : le sceau tenu par le processus du bureau seul, servi en lecture.
- Il peut lancer une suite **sans le lanceur** quand personne n'attend : `campagne.suites_sans_verrou` ne la repère que
  pendant une attente. Elle n'est alors pas mesurée ; la consigne l'interdit, et le motif 2 attrape la relance faite
  par le lanceur ensuite.
- Il peut affaiblir une assertion sans retirer de test : le motif 3 ne le voit pas. Seule la revue le voit.

### 5.6 Le coût de la mesure

- Au poste : une ligne de ~300 octets ajoutée par campagne, une lecture-écriture du sceau ; le comptage des octets se
  fait dans le fil qui relaie déjà la sortie. Aucun processus, aucun appel de modèle.
- Au moteur : une lecture de la fin du journal, seulement quand son heure de modification change ; la règle d'alerte
  est pure. Aucun appel de jugement.
- Message de départ : la section remplace l'actuelle, + ~450 caractères au plus (~120 tokens par départ).
- Rapport : un champ `tests` de quelques dizaines de tokens.

### 5.7 La migration des projets existants

- `DEFAUTS` donne `tests.budget_s = 300` : rien à faire pour que la règle s'applique.
- Pas de `commande_complete` connue : aucune campagne n'est `complete`, donc pas d'alerte de durée (seul le motif 4
  joue). À la première campagne de plus de 60 s d'un projet sans commande enregistrée, le moteur pose la décision
  `budget_tests` en demandant : « Cette commande est-elle la suite complète du projet ? <commande> (<4 min 12 s>) »,
  avec le budget proposé comme en 5.3 et la case « Écrire les conventions de tests dans <CLAUDE.md> ».
- Les journaux n'existent pas encore : ils naissent à la première campagne. Le sceau naît au premier geste du bureau,
  ou à la première mesure avec le défaut.
- Rien n'est réécrit dans un projet sans l'accord de cette décision.

## 6. Les tests qui le prouvent (eux-mêmes rapides)

Tous purs ou sur dossier temporaire, horloge et lecture de fichiers injectées, **aucun `sleep`, aucun sous-processus**,
aucune vraie suite lancée :
- règle d'alerte : les 4 motifs, la médiane, le seuil 1,5, l'anti-répétition et l'aggravation de 20 % ;
- portée : commande égale / différente de la commande enregistrée ; attente exclue de `duree_s` (horloge injectée dans
  `executer`, dont les dépendances sont déjà injectables : `lancer`, `dormir`, `lister`) ;
- lecture de `nb_tests` sur des sorties types `unittest`, `pytest`, `vitest`, `jest`, et `null` sinon ;
- écart sceau / réglages et compteurs qui reculent ;
- `tests_rapides(lieu)` pour local, cloud, serveur : présence des phrases clés, du budget, plafond de 1 200 caractères ;
  `message()` et `message_lot()` la contiennent pour chaque lieu (test existant à étendre) ;
- demandes `budget_tests` et `tests_lents` : bornes, verdicts (`bureau/demandes.py`) ;
- bloc de conventions : insertion, réécriture identique au deuxième passage, retrait, fichier créé puis retiré ;
- `tests_paralleles` : la décision « avertir / code 5 » sur un total injecté (fonction de bilan pure), sans lancer la
  suite ;
- facturation : `cout_des_tests` pur ; le bloc « Tests » de `facturation.js` par `node --test`.

## 7. Ce qui reste au constructeur

Les noms exacts des fonctions et fichiers (ceux donnés ici sont des propositions), les motifs de lecture de `nb_tests`
pour chaque outil, la place du bloc « Tests » dans la vue, la façon dont `deporter` obtient la durée d'un run GitHub
(il suit déjà les jobs), l'acceptation du champ `tests` par `moteur/rapport.py`, la documentation (`docs/deport.md`,
`docs/orchestrateur.md`). Ordre conseillé : 5.1 et 5.4 d'abord (sans dépendance), puis le journal et le sceau, puis
l'alerte, la facturation, et l'installation en dernier.

## 8. Les questions que seul le Directeur peut trancher

1. **Créer la tâche « Accélérer les tests » d'office, ou toujours la proposer ?** Recommandation : la proposer
   (décision `tests_lents`), avec la case « Désormais sans me demander » ; une tâche d'office consomme des tokens que
   le Directeur n'a pas choisis.
2. **Le sceau du budget hors du projet (`~/MyIAFactory/tests-sceau.json`), ou seulement `reglages.json` ?**
   Recommandation : le sceau. Il ne protège pas d'un agent décidé, mais il rend visible toute modification faite hors
   du bureau, pour le prix d'un petit fichier.
3. **Le mode strict de `tests_paralleles.py` pour MyIAFactory : crochet avant de pousser, CI, ou à la main ?**
   Recommandation : avertissement seul tant que `tests-rapides` n'est pas fusionnée ; ensuite un crochet `pre-push`
   proposé (pas imposé) qui lance `--strict`, car la suite dépend de Windows et ne tourne pas telle quelle sur GitHub.
