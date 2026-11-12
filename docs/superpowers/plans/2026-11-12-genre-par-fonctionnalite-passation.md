# Un genre et un workflow par fonctionnalité — passation entre conversations

Le plan (`2026-11-12-genre-par-fonctionnalite.md`) est réalisé en phases, chacune dans sa propre conversation Claude, avec le modèle indiqué. **Une phase est un lot de modèle** : un même modèle fait d'une traite tout ce qu'il peut faire d'affilée. C'est l'utilisateur qui crée chaque conversation et choisit le modèle. Une conversation enchaîne toutes les tâches de sa phase sans s'arrêter, puis s'arrête et annonce la suivante. Même méthode que `2026-11-11-orchestrateur-procedural-passation.md`.

La conception (`docs/superpowers/specs/2026-11-11-genre-par-fonctionnalite-design.md`) est **validée par l'utilisateur** le 2026-11-12 : rien à recadrer. Toutes les phases se font **dans ce dépôt**. Les données d'un essai réel restent **hors dépôt** ; leurs chemins sont donnés par l'utilisateur dans la conversation de la phase. Les sessions de phase n'utilisent pas le panneau navigateur de l'app : elles vérifient par les tests et par des requêtes HTTP. Une autre session peut travailler dans le même dossier : **ne committer que ses propres fichiers**. Aucune dépense réelle (appel `claude`, `gh`) sans l'accord de l'utilisateur.

## Où on en est

Tenir cette section à jour à la fin de chaque phase (dernière action avant le dernier push).

| Phase | Modèle proposé | Tâches du plan | Pourquoi ce modèle | État |
|---|---|---|---|---|
| A | Sonnet 5.5 | 1, 2 : workflows du projet, genre de la fonctionnalité ; relevé, tableau, départ et mémoire | Données et lecture au contrat écrit, tests nommés | **faite** le 2026-11-12 (1121 tests verts) |
| B | Opus 5.5 | 3 : jugements `classer_genre` et `proposer_organisation` | Les consignes décident de la qualité (genres précis, workflow complet jusqu'au livrable) et du coût | **faite** le 2026-11-12 (1138 tests verts) |
| C | Sonnet 5.5 | 4, 5, 6, 10 : le moteur suit le workflow de la fonctionnalité, Fable sur accord, parcours d'une nouvelle demande, environnement du poste | Table de règles au contrat écrit, un test par ligne | **faite** le 2026-11-12 (1202 tests verts) |
| D | Sonnet 5.5 | 7, 8 : créer un projet vide, le bureau | Installation et page au contrat écrit | **faite** le 2026-11-12 (1233 tests verts) |
| E | Opus 5.5 | 9 : banc et essai réel, avec l'utilisateur | Diagnostic du coût et réglage des consignes | à faire : **c'est la prochaine phase** |

Les modèles sont une proposition ; l'utilisateur a le dernier mot. **Fable n'est utilisé dans aucune phase.**

## Notes laissées par les phases

(Écarts au plan, choix faits, points à surveiller.)

**Phase A (Sonnet 5.5, 2026-11-12)** : tâches 1 et 2 faites, suite complète verte (1121 tests, `node --test` compris).

- **Le champ `genre` d'un usage est pris** : il ne vaut que `partenaire` (validation du relevé, historique des usages).
  Le genre de la fonctionnalité est donc noté dans `genre_fonctionnalite` (suivi, relevé, `usage-historique.jsonl`,
  `bureau/usage.py`). `estimation.usages_du_genre` lit ce champ ; un usage sans lui compte pour le genre du projet, et
  un projet est retenu s'il a ce genre ou un workflow de ce genre. Lignes de lot comprises.
- **Colonnes du relevé** : `genre` n'y est mis que s'il existe, `workflow` seulement si le projet a une clé `workflows`
  (un projet sans `workflows` garde un relevé identique à avant, sauf le `genre` du projet). Une tâche dont la colonne
  a quitté le tableau (fonctionnalité `terminee` ou `deplacee`) est rendue en colonne `fait`, pour que le relevé reste
  valide. La fonctionnalité du relevé gagne `genre`, `workflow`, `deplacee_vers` (s'ils existent) et `workflow_etapes`
  (`[{id, nom}]`, pour nommer ses documents par étape quand ses colonnes ont quitté le tableau).
- **`workflows.tous`** : le principal vient en premier (s'il a un flux), puis les workflows de `workflows`.
  Ajout : `workflows.premiere_etape(f, fonc)` (colonne par défaut d'une tâche ; `cadrage` si le projet n'a aucun workflow,
  `Ctx.premiere_colonne`). `workflows.colonnes` donne `genre: None` quand il n'y en a pas ; le relevé retire la clé.
- **`factory.lire`** rend aussi `workflows` (normalisés) et `description`. Un flux vide ou absent est valide. Le test
  `test_factory_flux_vide` est devenu `test_factory_flux_vide_ou_absent_valide`.
- **Départ** : le genre de la fonctionnalité est passé à `depart.message*` en remplaçant `genre` dans la copie de la
  factory (pas de changement de signature). Un lot qui mêle des genres donne les leçons de chacun, sans doublon, et
  l'en-tête les liste. Leçon de genre appliquée : genre de la fonctionnalité de sa tâche (`tache` de la leçon), sinon
  celui du projet.
- **`deplacee`** : exclue des KPI calculés et de `cout.couts_fonctionnalite` (coût nul), et ses décisions ne comptent
  plus pour le Directeur (`bureau/etat.py`). Documentée dans `interface.md` et d'une ligne dans `consignes.md`
  (le test des consignes exige que chaque étape y soit nommée).
- **Page** : `etiquetteColonne`, `genreEtWorkflow`, `libelleEtape` (pures, testées) ; genre sous le nom de colonne
  (Kanban plein écran et tableau 3D), genre et workflow sous le titre d'une fonctionnalité, étape « Partie dans le
  projet … ». Non regardé dans un navigateur (consigne de la phase).
- **À surveiller** : `main.js` recharge la page quand les identifiants de colonnes changent (`structure`) : chaque
  nouveau workflow de fonctionnalité va donc la recharger une fois, comme un changement de flux aujourd'hui. Ni
  `organisation.js` (qui regarde les colonnes retirées du flux) ni la décision `organisation` n'ont été adaptés
  (phases C et D). `ecrire_organisation`, `moteur/regles.py` lisent encore `ctx.f["flux"]` seul (phase C).

**Phase B (Opus 5.5, 2026-11-12)** : tâche 3 faite, suite complète verte (1138 tests).

- **La validation lit le dossier** : `jugement.valider(type_, objet, dossier=None)` ; `juger` passe son dossier.
  `classer_genre` et `proposer_organisation` sont dans `_VALIDEURS_AVEC_DOSSIER` (les cinq anciens n'ont pas changé).
  Le moteur (phase C) doit donc remplir le dossier exactement comme le docstring de `moteur/jugement.py` le dit, sinon
  la réponse est refusée : `genres_du_projet` et `genres_connus` (`[{id, …}]` ou `[id]`), `mots_interdits`,
  `services` (`[{id, nom}]`), `agents` (`[{cle, role, …}]`), `fonctionnalite` (son id).
- **`classer_genre`** : `meme` exige un genre de `genres_du_projet` ; `proche` un genre connu (projet ou skill) ;
  `autre` un genre connu **ou** `nouveau`, pas les deux ; `incertain` accepte une piste (`genre` ou `nouveau`) ou rien ;
  `nouveau` refusé avec `meme`/`proche`, si son id existe déjà, ou si son id ou sa description contient un mot interdit.
- **`proposer_organisation`** : `flux[i].etape` est l'id **court** (`dev`) ; le moteur le préfixe (`f5-dev`), et la
  validation vérifie que `<fonctionnalite>-<etape>` tient dans `MOTIF_ID` (40 caractères). `services` et `agents` ne
  listent que les nouveaux (un service ou une clé déjà au projet est refusé). Chaque rôle du flux a un agent du projet
  ou proposé ; chaque nouveau rôle a un brief. Pas de champ `lieu` (le moteur le fixe, comme `estimer` le coût).
  Modèle : Haiku, Sonnet ou Opus ; « Fable » en modèle est refusé avec un message qui renvoie à `fable_suggere`.
  **Dernière étape = livrable** : `livrable` non vide, et le nom de la dernière étape contient un mot de livraison
  (`MOTS_DE_LIVRAISON` : livr, remis/remise, publi, dépôt, export, envoi, déploi, mise en ligne) ou un mot (3 lettres
  et plus) du `livrable` : heuristique volontairement souple, à revoir au banc si elle laisse passer un « Développement
  du jeu ». `environnement[i].pour` : l'`etape` ou son nom ; `executables` : noms seuls (`MOTIF_EXECUTABLE`, ni
  chemin ni option) ; `outils_installation` : seulement `Bash(<cmd>:*)`, `Bash(<cmd> <args>)` ou `PowerShell(…)` de
  même forme (`MOTIF_REGLE_OUTIL`) ; `Bash`, `Bash(*)` et les autres outils refusés. Listes vides permises.
- **Écart au plan** : le test existant `test_aucune_consigne_ne_parle_de_fable_ni_d_un_projet` tolère aussi
  `fable_suggere` (le plan l'impose dans la consigne de `proposer_organisation`). Pas de script d'essai dans le dépôt :
  l'essai a tourné par un script hors dépôt (`juger` avec un `appeler` qui note `cout_usd`), sur le modèle de
  `outils/mesurer_appel.py`.
- **Essai réel** (couche `claude`, accord de l'utilisateur ; projet synthétique « badges d'une chaîne », genres
  synthétiques `badges-twitch` et `site-vitrine`) : 9 appels, **0,16 $ en tout**.
  - `classer_genre` (Haiku) : 4 appels, **4 valides au premier essai**, verdicts attendus (badge du chat YouTube →
    `proche` de `badges-twitch` ; casse-briques Android → `autre` avec `nouveau` (`jeu-mobile` puis
    `application-mobile` : l'id varie d'un essai à l'autre) ; demande floue → `incertain` avec la piste du genre du
    projet). Environ 2 100 à 2 500 tokens d'entrée (presque tout en cache), 260 à 385 de sortie, **0,0003 à 0,0006 $**
    par appel, 6 à 9 s.
  - `proposer_organisation` (Sonnet) : 5 appels pour 4 jugements. Badge YouTube et demande floue : **le workflow du
    genre repris tel quel** (mêmes étapes, aucun agent ni service nouveau), valides au premier essai, 1 000 à 1 200
    tokens de sortie, **0,016 à 0,022 $**. Casse-briques : au premier passage, premier essai refusé (`role` écrit en
    texte libre, « développement Android ») puis valide au second ; consigne réglée (ids en minuscules et tirets, un
    outil une seule fois), second passage **valide au premier essai** : 6 étapes (visuels, programmation,
    construction et signature de l'apk, tests, conformité, « Livraison de l'apk signé »), un service et deux agents
    nouveaux (Sonnet, Haiku), JDK, Gradle et SDK Android dans l'environnement. 2 400 à 2 600 tokens d'entrée, 3 100 à
    3 550 de sortie, **0,036 à 0,043 $** par appel, 26 à 29 s.
- **À savoir pour la phase C** : la qualité est parfois tenue par un agent du projet (`verification`) plutôt qu'un
  service qualité nouveau : la consigne le permet (réutiliser). Les `outils_installation` proposés comprennent des
  téléchargements (`Bash(curl:*)`, `PowerShell(Invoke-WebRequest:*)`, `Bash(unzip:*)`) : le Directeur les valide avec
  l'organisation ; ne pas les élargir en code. Un même exécutable peut revenir dans deux outils (vu au premier
  passage, avant le réglage) : dédoublonner par exécutable pour la vérification du poste. `nouveau.id` varie : la
  décision `genre_fonctionnalite` doit le laisser corriger. Les jugements ne choisissent jamais Fable (`juger` le
  refuse toujours ; aucun agent proposé n'a eu `fable_suggere: true` à l'essai).

**Phase C (Sonnet 5.5, 2026-11-12)** : tâches 4, 5, 6 et 10 faites, suite complète verte (1202 tests, `node --test` compris).
Quatre commits : `Moteur : chaque fonctionnalité suit son workflow`, `Fable : seulement sur accord…`, `Moteur : classer
chaque demande, proposer son workflow, recruter`, `Moteur : vérifier et installer l'environnement du poste`.

- **Tâche 4** : `regles._flux/_production/_role_cadrage/_colonne_du_role(projet, …, fid)` lisent le workflow de la
  fonctionnalité (`workflows.de_la_fonctionnalite`), le principal sans fonctionnalité. Nouveau : `_role_production`
  (rôle de la première étape, ou `cadrage` si le projet n'a aucun workflow : plus d'`IndexError`) ; sans workflow,
  `_colonne_du_role` rend `cadrage`. Le dossier de `decouper` et `methodes_validees` portent le flux de chaque fonctionnalité.
- **Tâche 5** : une fiche porte `Fable : accordé par le Directeur le AAAA-MM-JJ` (en-tête `Fable`, motif
  `fiches.ACCORD_FABLE`) ; `Modèle : Fable` n'est lisible qu'avec cette ligne. `fiches.fable_accorde(fiche)`.
  `agents.executer_agent` lance Fable (modèle `fable`) seulement pour une telle fiche, avec `fable_accorde=True` passé à
  `appel.appeler` (qui le refuse sans outils, donc pour tout jugement, et hors couche `claude`). `outil` : `modele_depart`
  Fable permis pour l'agent accordé seulement ; une `montee` ne va jamais à Fable ; la décision `organisation` refuse
  toujours `modele: Fable` (l'accord se donne à l'acceptation). `proposition._modele` accepte `Fable` + accord. Les
  agents cloud restent refusés sur Fable (`moteur/cloud.py` inchangé) : les agents recrutés sont locaux.
- **Tâche 6 — le parcours** (`regles._sur_fonctionnalite` → `_classer` → `classer_genre`) :
  - demande `fonctionnalite` : `classer_genre` (Haiku) ; le dossier est préparé comme le docstring de `moteur/jugement.py`.
    Une demande recréée dans un autre projet porte `genre` (et `description` si le genre est nouveau) : le classement est
    sauté, étape 3 directement.
  - `meme`/`proche` : `fonctionnalite.genre` noté (un message du chef dit « proche »), puis `proposer_organisation`
    (Sonnet). `autre`/`incertain` : décision de fonctionnalité `genre_fonctionnalite`, la fonctionnalité attend.
  - **Projet sans genre** (`factory.genre` et genres des workflows vides, même sans description) : `classer_genre`
    sur la description (à défaut le texte de la demande), puis décision de projet `confirmer_genre` qui porte en plus
    `fonctionnalite` ; la réponse (demande `genre`) fixe le genre du projet et de la fonctionnalité, puis la
    proposition de workflow. Sans aucune piste du jugement : proposition de workflow sans genre.
  - `proposer_organisation` rend une décision de projet `organisation` (voir formats ci-dessous). Le moteur préfixe les
    étapes (`f2-dev`), fixe `lieu: local`, calcule le coût par `estimation.estimer` (prix inconnus : `euros` nul ; les
    mesures du bureau servent si `projet.bureau` est posé, ce que `boucle.Moteur._ajouter` fait), l'id du workflow est
    `w-<fid>`. Un workflow du même genre est donné au jugement sans le préfixe de sa fonctionnalité.
  - acceptation : `lancer organisation appliquer` (+ `fable`) puis cadrage (ou la tâche d'environnement). Le workflow
    s'ajoute à `workflows`, `flux` du projet intact ; la fonctionnalité prend `genre` et `workflow`. Un genre nouveau
    (`workflow.genre_nouveau.description`) est créé dans la mémoire **en dernier** (`outil.GIT`, remplacé par les tests) ;
    un échec est dit (`genre_raison`) et ne bloque rien.
  - refus : avec `texte`, `proposer_organisation` relancé avec `refus` ; sans texte, la fonctionnalité prend le workflow
    le plus récent du même genre, sinon le principal, et le dit ; **projet sans aucun workflow : la décision reste posée**
    (réponse « ce projet n'a encore aucun workflow… »). Verdict ajouté : `abandonner` (lève la décision, la fonctionnalité
    passe `deplacee` avec `deplacee_vers: "(demande abandonnée)"` : pas d'étape « abandonnée » dans le relevé, à afficher
    comme tel côté page, ou à remplacer si l'utilisateur veut une autre étape).
  - `nouveau_projet` : le moteur lit `projet_cree` (chemin des réglages du projet créé ; sa factory = clé `orchestrateur`
    des réglages, sinon `factory.json` à côté), recrée la demande (texte, images relues sur le disque en base64, `genre`,
    `description`) par `outil.executer(<factory>, ["lancer", "actions"], …)`, puis la fonctionnalité passe `deplacee`
    (`deplacee_vers` = nom du projet) avec le message « Partie dans le projet <nom> ». **Projet introuvable ou illisible :
    rien ne bouge, la décision reste** et la réponse dit que « Dans ce projet » reste possible.
  - **Issues de secours** : `classer_genre` raté (deux essais) → `_classer_rate` : genre du projet, une phrase au chef,
    cadrage ; `proposer_organisation` raté (ou refusé par `lancer decision`) → question de discussion avec les choix
    `regles.CONTINUER` (« Continuer avec le workflow actuel ») et `regles.JE_PRECISE` ; la réponse arrive comme un
    `message` : `CONTINUER` → workflow de repli puis cadrage, un texte libre → nouvelle proposition (`refus`). Cet état est
    en mémoire (`etat["proposition_ratee"]`) : après un arrêt du moteur, un message de l'utilisateur ouvre simplement le
    cadrage (le plus sûr pour ne rien bloquer).
  - **Le cadrage ne démarre pas** tant que la fonctionnalité attend : décision `genre_fonctionnalite` ou `environnement`
    posée, décision `organisation`/`confirmer_genre` de projet qui la nomme (`fonctionnalite`), question `proposition_ratee`,
    tâche d'environnement en cours (`_en_parcours`) ; un message de l'utilisateur pendant l'attente reçoit « répondez
    d'abord à la question posée dans les décisions ».
  - Tests existants adaptés : `Base.cadrer()` (le classement raté mène au cadrage), `test_aucune_demande_sans_reponse`
    donne une réponse à `classer_genre`, `tests/test_banc_scenario.py` (`Jugements` fait échouer les deux nouveaux appels :
    **le banc n'a pas encore ses gestes, c'est la phase E** ; un passage réel du banc ne rendrait la main qu'après la
    décision d'organisation).
- **Tâche 10** (`moteur/environnement.py`) : `verifier(outils, *, which, executer, env)` ; un outil est `en_place` quand
  tous ses exécutables sont trouvés (`PATH`, puis `JAVA_HOME/bin`, `ANDROID_HOME`/`ANDROID_SDK_ROOT` : `cmdline-tools/latest/bin`,
  `cmdline-tools/bin`, `platform-tools`, `tools/bin`, `emulator`, `build-tools/*`), avec `chemin` (du premier) et `version`
  (première option de `--version`, `-version`, `version` qui répond, 10 s). Un nom qui n'a pas la forme d'un nom de
  programme (`MOTIF_EXECUTABLE`) n'est ni cherché ni lancé : l'outil reste `a_installer` avec `refuses`. Un exécutable
  commun à deux outils n'est cherché qu'une fois. `Projet.verifier_environnement` (injectable) l'appelle à la proposition.
  - Si quelque chose manque, la proposition porte un agent d'installation (rôle `environnement`, clé `env-<n>`, Sonnet,
    local, service = le premier du projet ; brief `environnement`) sauf si un agent de ce rôle existe ; à l'acceptation,
    `outil._ouvrir_les_outils_d_installation` ajoute les `outils_installation` à sa ligne `Outils :` (et à lui seul), puis
    la tâche « Mise en place de l'environnement » (étape `environnement`, colonne = première étape du workflow, rôle
    `environnement`) part ; le cadrage vient à sa fin. Elle finie : revérification (`_verifier_le_poste`), outils notés par
    `lancer organisation {"action": "environnement", "outils": […]}` ; tout est là → cadrage ; sinon (ou agent en échec,
    ou sans rapport) → décision de fonctionnalité `environnement`, jamais de blocage.
  - Réglage `environnement` du projet (`factory.json`, liste `{outil, etat, chemin?, version?, executables, installation, pour}`) ;
    `factory.lire` le rend ; `depart` ajoute « ## Outils du poste » (les outils `en_place`, avec chemin et version).

**Phase D (Sonnet 5.5, 2026-11-12)** : tâches 7 et 8 faites, suite complète verte (1233 tests, `node --test` compris).
Deux commits : `Installation : créer un projet vide depuis le bureau`, `Bureau : créer un projet, choisir le genre d'une demande,
valider son workflow`. Rien n'a été regardé dans un navigateur (consigne) : la page est vérifiée par `node --test` (faux DOM
pour les décisions) et la route par des requêtes HTTP de test.

- **`installation/creation.py`** : `creer_projet(parent, nom, *, origine, mots_interdits, facturation, github, description, genre,
  bureau_json, git, gh, maintenant)` rend `{reglages, id, projet, github}` (`github` : `"fait"`, `"non demandé"` ou la raison, avec le
  geste à la main). `origine` = le `reglages.json` du projet d'origine (charge, couche du moteur ; si ses réglages ont une clé
  `orchestrateur` : modèle de l'orchestrateur, agents locaux et consignes du projet). Un projet d'origine sans orchestrateur
  (la démo) ne bloque pas. `git`/`gh` : `(args, cwd) -> (code, sortie)` ; l'absence d'un outil se reconnaît à « pas pu s'exécuter ».
  Ordre GitHub : `gh auth status`, puis `git init`, `git add .`, `git commit`, `gh repo create <nom> --private --source . --push`.
  `mise_en_place._ecrire_configuration` accepte un projet sans `flux` ni agent (dossiers `fiches/briefs`, pas de `flux` dans
  `factory.json`, `description` écrite). Commande `installation/outil.py creer` (citée dans `skills/installer/SKILL.md`, dont le test
  de longueur est à 2000 mots : deux phrases raccourcies pour la loger).
- **Route** : `POST /api/projets/creer` (`Bureau.creer_projet`), mêmes en-têtes que les autres écritures, code d'accès exigé sur un
  écouteur distant (garde commune). Corps : `{parent, nom, mots_interdits, facturation, github, description?, origine?, decision?,
  fonctionnalite?, genre?, genre_description?}` → `{ok, projet, github, message, demande_deposee?}`. **Un genre inconnu de la mémoire
  de la skill n'est jamais écrit dans le projet créé** : il part dans `genre_description` (et sert de description du projet) ; la
  demande `nouveau_projet` porte `genre` et `description`. Depuis une décision, la demande est **vérifiée avant la création**
  (un refus ne laisse pas de projet orphelin) puis déposée par le projet d'origine ; si le dépôt échoue après coup, le projet
  reste créé et le message le dit (`demande_deposee: false`). Le serveur refuse sans fichier de bureau commun (409, bureau lancé
  sur un seul `reglages.json`).
- `GET /api/projets` (bureau multi seulement) ajoute `parents` (dossiers où l'on range déjà des projets) et, par projet,
  `mots_interdits` et `facturation` (service « facturation ») pour pré-remplir le formulaire. Le bureau à un seul projet est inchangé.
- **Page** : `ui/creation.js` (formulaire, fonctions pures testées), dernière entrée « Nouveau projet… » de la liste
  (`projets.optionsProjets`), décisions `genre_fonctionnalite` et `environnement` au bureau du Directeur (`decisions.js`), décision
  `organisation` d'un workflow (étapes, livrable, agents avec justification, case Fable seulement si `fable_suggere`, environnement
  « déjà en place »/« à installer », texte du refus, « Abandonner la demande »). `organisation.js` aligné sur la décision d'un workflow :
  ses étapes sont toutes « ajoutées », et une évolution du principal ne « retire » plus les colonnes des autres workflows. Une
  fonctionnalité `deplacee` n'apparaît plus dans les décisions du Directeur ; `deplacee_vers: "(demande abandonnée)"` s'affiche
  « Demande abandonnée ».
- **Pour la phase E (essai au bureau)** : relancer le bureau et le moteur (le bureau relit `bureau.json` mais pas son code). La
  première création écrit dans le vrai `~/MyIAFactory/bureau.json` : prévoir un dossier parent d'essai. Le formulaire propose en
  suggestions les dossiers parents des projets déjà inscrits. Après la création depuis une décision, le **moteur du projet d'origine**
  recrée la demande dans le nouveau projet à son prochain passage (il lit `projet_cree`) : le nouveau projet apparaît tout de suite,
  la demande après un tour de moteur. Le nouveau projet est pris par le moteur au passage suivant (il relit le bureau). Non vérifié
  autrement qu'en test : l'affichage réel du formulaire (superposition `.creation-fond`), le rendu mobile des décisions, le
  `gh repo create` réel. Le banc n'a toujours pas ses gestes (phase E).

**Formats exacts pour la phase D (route de création et décisions au bureau)** :

- Demande `{"type": "genre_fonctionnalite", "decision": <id>, "fonctionnalite": <fid>, "choix": "ici" | "meme" | "nouveau_projet",
  "genre"?: <id>, "description"?: <texte d'un genre nouveau>, "projet_cree"?: <chemin des réglages du projet créé>}`.
  `meme` n'est accepté que si la décision a `incertain: true` ; `nouveau_projet` exige `projet_cree` ; `ici` prend `genre`
  sinon le `propose` de la décision (un genre absent de `genres_connus` demande une `description`, sauf si c'est le
  `nouveau.id` de la décision). **La route du bureau (tâche 8) dépose cette demande avec `choix: "nouveau_projet"` et
  `projet_cree` = le chemin des réglages (`chemin` inscrit dans `bureau.json`) du projet qu'elle vient de créer ; c'est le
  moteur du projet d'origine qui recrée la demande dans le nouveau projet — la route ne le fait pas** (ajuster le texte du
  plan, tâche 8, qui disait « dépose la demande dans le projet d'origine » : c'est bien cela, mais le moteur fait le déplacement).
  Le projet créé doit être lisible par `factory.lire` (flux vide permis) ; son genre peut être celui de la demande.
- Décision de fonctionnalité `genre_fonctionnalite` (dans `fonctionnalites[i].decisions`) : `{id, genre, texte, propose, genres_connus: [ids],
  incertain: bool, nouveau?: {id, description}}`. Trois boutons : « Nouveau projet » (`nouveau_projet`), « Dans ce projet » (`ici`, avec
  un genre modifiable : liste `genres_connus` + « nouveau genre… » avec description), « C'est le même genre » (`meme`) si `incertain`.
- Demande `{"type": "organisation", "decision", "verdict": "accepter" | "refuser" | "abandonner", "texte"?, "fable"?: [clés]}`.
  `texte` : ce qu'il faut changer (refus) ; `fable` : les clés des agents cochés, parmi ceux dont `fable_suggere` est vrai
  (seulement avec `accepter`) ; `abandonner` seulement pour une décision qui porte un `workflow`.
- Décision de projet `organisation` d'un workflow : `{id, genre: "organisation", texte, organisation: {services (tous, après changement),
  flux (les étapes du workflow, ids `<fid>-<étape>`), agents (les nouveaux : {cle, prenom?, role, service, modele, lieu: "local",
  justification, fable_suggere?, texte}), briefs, cout: {tokens: [a, b], euros: [a, b] | null}, fonctionnalite, workflow: {id, genre,
  flux, genre_nouveau?: {description}}, livrable, environnement: [{outil, pour, executables, installation, etat: "en_place" | "a_installer",
  chemin?, version?, refuses?}], outils_installation: [règles]}}`. Si des outils manquent, `agents` comprend l'agent d'installation
  (rôle `environnement`). Une décision `organisation` sans `workflow` est l'ancienne (évolution d'organisation).
- Décision de projet `confirmer_genre` : porte en plus `fonctionnalite` (facultatif) ; la demande reste `{"type": "genre", "decision", "genre", "description"?}`.
- Décision de fonctionnalité `environnement` : `{id, genre, texte, environnement: [outils qui manquent]}` ; demande
  `{"type": "environnement", "decision", "fonctionnalite", "verdict": "fait" | "continuer"}` (« C'est fait », « Continuer sans »).
- Relevé : `DECISIONS_FONCTIONNALITE` gagne `genre_fonctionnalite` et `environnement` (champs contrôlés) ; la page doit les afficher,
  ainsi que l'étape `deplacee` d'une demande abandonnée (`deplacee_vers: "(demande abandonnée)"`). `bureau/demandes.py` vérifie les
  trois types (`organisation` étendue, `genre_fonctionnalite`, `environnement`) ; `docs/releve.md` et `orchestrateur/interface.md` les décrivent.
- **À surveiller** : `ecrire_organisation` (installation) remplace la liste `services` (le moteur envoie tous les services) ;
  `creation.creer_projet` (tâche 7) doit écrire un `factory.json` valide sans `flux`, éventuellement avec `description` et `genre` ;
  `bureau/web/ui/organisation.js` lit encore les colonnes retirées du flux (note de la phase A).

## Messages à coller

**Phase A — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase A du chantier « un genre et un workflow par fonctionnalité ». Lis `docs/superpowers/plans/2026-11-12-genre-par-fonctionnalite-passation.md` et suis-le : la conception et le plan sont validés, il n'y a rien à recadrer. Enchaîne d'une traite les tâches 1 et 2 du plan. N'utilise pas le panneau navigateur de l'app. Une autre session peut travailler dans le même dossier : ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase B — Opus 5.5 — dans ce dépôt**

> Réalise la phase B du chantier « un genre et un workflow par fonctionnalité ». Lis `docs/superpowers/plans/2026-11-12-genre-par-fonctionnalite-passation.md` et suis-le. Fais la tâche 3 du plan ; demande mon accord avant l'essai réel des jugements. N'utilise pas le panneau navigateur de l'app. Ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase C — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase C du chantier « un genre et un workflow par fonctionnalité ». Lis `docs/superpowers/plans/2026-11-12-genre-par-fonctionnalite-passation.md` et suis-le. Enchaîne d'une traite les tâches 4, 5, 6 puis 10 du plan. N'utilise pas le panneau navigateur de l'app. Ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase D — Sonnet 5.5 — dans ce dépôt**

> Réalise la phase D du chantier « un genre et un workflow par fonctionnalité ». Lis `docs/superpowers/plans/2026-11-12-genre-par-fonctionnalite-passation.md` et suis-le. Enchaîne d'une traite les tâches 7 et 8 du plan. N'utilise pas le panneau navigateur de l'app. Ne committe que tes fichiers. Termine par la fin de phase, sans lancer la suivante.

**Phase E — Opus 5.5 — dans ce dépôt**

> Réalise la phase E du chantier « un genre et un workflow par fonctionnalité » : la tâche 9 du plan, avec moi. Lis `docs/superpowers/plans/2026-11-12-genre-par-fonctionnalite-passation.md`. Je te donnerai les chemins de l'essai de référence (hors dépôt). Demande mon accord avant toute dépense réelle. Ne committe que tes fichiers.

## Fin de phase

1. Toute la suite verte : `py -3.12 outils/tests.py` (environ 75 s). **Seulement ici** : pendant le travail, chaque commit ne lance que les tests concernés, `py -3.12 outils/tests.py <mots>`.
2. Cocher les tâches faites dans le plan, mettre à jour « Où on en est » et les notes.
3. Commit (ses seuls fichiers) et push.
4. Annoncer la phase suivante, son modèle et son message à coller.
