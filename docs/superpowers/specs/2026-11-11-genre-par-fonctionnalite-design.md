# Un genre et un workflow par fonctionnalité — conception

Date : 2026-11-11. Statut : à valider par l'utilisateur.

## 1. Pourquoi

Dans le projet des badges Twitch (genre `creation-graphique-twitch`, workflow Création → Contrôle, agents graphiste et
contrôleur), l'utilisateur a demandé un casse-briques pour Android. Le moteur procédural l'a confié au graphiste, sans
rien dire : il ne compare jamais une demande au genre du projet et ne propose jamais d'organisation (limite connue depuis
la phase B de l'orchestrateur procédural). Aujourd'hui le genre et le workflow sont des réglages **du projet** : un seul
genre, un seul flux, fixés à l'installation.

L'utilisateur veut que :
- l'orchestrateur **remarque** qu'une demande n'est pas du genre du projet et le **dise** ;
- il propose de **créer un nouveau projet** pour ce genre, ou de **garder la fonctionnalité dans le projet actuel** ;
- dans les deux cas, la fonctionnalité ait **son genre et son workflow**, et que les services et agents qui manquent
  soient créés et recrutés après validation ;
- on puisse aussi **créer un projet depuis le bureau** (liste déroulante des projets).

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
1. Chaque fonctionnalité porte un **genre** et un **workflow** (les étapes du flux, chacune avec son rôle et son service).
2. À chaque nouvelle demande de fonctionnalité, le moteur classe la demande : même genre que le projet, genre proche
   (rattaché), ou genre différent. S'il est différent, il le dit et propose : nouveau projet ou projet actuel.
3. Le workflow d'une fonctionnalité d'un genre nouveau pour le projet est **proposé** (étapes, agents à recruter avec
   leur modèle, services à créer, coût estimé), validé par l'utilisateur, puis **mis en place automatiquement**.
4. Un projet peut être **créé depuis le bureau** : depuis cette proposition, ou depuis l'entrée « Nouveau projet… » de
   la liste déroulante. Il apparaît aussitôt dans la liste.
5. Le tableau des tâches montre les tâches de **tous** les workflows du projet, colonnes dans l'ordre de réalisation,
   **chaque colonne indiquant son genre**.

**Non-objectifs**
- Changer le genre d'une fonctionnalité déjà commencée (une fois le cahier écrit, le genre est fixé).
- Fusionner ou supprimer des projets depuis le bureau.
- Reproduire tout le parcours d'installation (examen d'un projet existant, partenaires, accès réseau) dans le bureau :
  la création depuis le bureau fait un projet **vide**, prêt pour sa première demande.
- Adapter l'ancien orchestrateur conversationnel (`orchestrateur/consignes.md`) : seul le moteur procédural porte ce
  parcours. *Choix de conception (pas une décision de l'utilisateur).*

**Anti-objectifs** (ce qui ferait échouer le chantier même s'il « marche »)
1. **Un blocage.** Une fonctionnalité qui reste coincée parce qu'il manque un agent, un service, une connaissance, un
   accès (GitHub, `gh`), ou parce qu'un appel de jugement a échoué. Toute étape de ce parcours a une issue de secours
   qui laisse avancer (voir 8) et dit à l'utilisateur ce qui s'est passé.
2. **Des genres fourre-tout.** Rattacher à un genre existant un sujet trop éloigné mélange des leçons sans rapport :
   les agents reçoivent des connaissances éloignées, le travail coûte plus cher et sort moins bon. **Dans le doute, un
   genre nouveau et précis vaut mieux qu'un genre élargi** ; et quand c'est vraiment ambigu, on demande à
   l'utilisateur.

## 3. Ce que l'utilisateur a décidé

- Le genre se décide **par fonctionnalité**, et chaque fonctionnalité a **son workflow dédié** (même deux
  fonctionnalités du même genre : un workflow chacune, une proposition chacune).
- Le workflow va **de la demande au livrable remis** : toutes les étapes, y compris la livraison (un service de
  livraison pour un `.apk`, par exemple), et une **équipe qualité** qui vérifie la bonne exécution dès que c'est logique.
- Un projet créé depuis le bureau **reprend les réglages** du projet d'origine ; le formulaire demande en plus les
  **mots interdits** et la **facturation**, pré-remplis.
- Demande d'un autre genre : l'orchestrateur avertit et propose **un nouveau projet** ; « oui » crée le projet (nom
  demandé, répertoire parent choisi, GitHub oui ou non) et la demande y part ; « non » la garde dans le projet actuel.
- Création d'un projet : on **choisit le répertoire parent et le nom** ; le dossier `<parent>/<nom>` est créé avec
  **toute l'arborescence de la skill** dès la création ; on choisit s'il part **sur GitHub ou non**.
- La liste déroulante des projets propose **« Nouveau projet… »**. Sans contexte (pas de demande d'origine), on demande
  une **courte description du projet**, qui sert à proposer un genre (existant ou nouveau).
- Un agent du projet qui sait déjà faire une étape du nouveau workflow est **réutilisé** ; on ne recrute que les rôles
  qui manquent.
- Après validation de la proposition, services et agents sont créés **automatiquement**. Le modèle de chaque nouvel
  agent est choisi par l'orchestrateur selon le projet et la complexité de la tâche (Haiku, Sonnet, Opus).
- **Fable** peut être proposé, mais **doit être validé par le Directeur** (l'utilisateur).
- Un genre **proche** (exemple : un logo pour le chat YouTube ou pour une conversation privée, à côté des badges
  Twitch) est **rattaché** au genre existant.
- Tableau : toutes les tâches de tous les workflows, dans l'ordre de réalisation, avec **le genre de chaque phase**.

## 4. Le modèle de données

**Fonctionnalité** (`suivi.json`, `orchestrateur/suivi.py:nouvelle_fonctionnalite`) : deux champs nouveaux.
- `genre` : l'identifiant du genre (motif `MOTIF_GENRE` de `orchestrateur/factory.py`), `null` tant qu'il n'est pas
  classé.
- `workflow` : l'identifiant du workflow du projet qu'elle suit, `null` tant qu'il n'est pas fixé.

**Workflows du projet** (`factory.json`) : une clé nouvelle `workflows`, liste de
`{"id", "fonctionnalite", "genre", "flux": [{id, nom, role, service}]}`. **Un workflow par fonctionnalité**
(décision de l'utilisateur) : chaque fonctionnalité a le sien, même quand elle est du même genre qu'une autre. Les
`services` restent ceux du projet (partagés). Les agents (fiches) restent ceux du projet (partagés : un agent peut
servir plusieurs workflows).

**Identifiants d'étape** : uniques **dans tout le projet**, puisqu'ils servent d'identifiants de colonne
(`Ctx.colonnes()` de `orchestrateur/outil.py`). *Choix de conception :* l'identifiant d'une étape est préfixé par sa
fonctionnalité (`f2-dev`, `f2-qualite`, `f2-livraison`) ; deux workflows qui ont chacun une étape « Contrôle » ont
donc deux colonnes. `cadrage` et `fait` restent réservés et communs.

**Compatibilité** : un projet existant a `genre` et `flux` au niveau du projet et pas de `workflows`. On le lit comme un
projet à un seul workflow (`id` = `principal`, son genre = le genre du projet, son flux = `flux`). Une fonctionnalité
sans `genre`/`workflow` suit ce workflow principal. Les clés `genre` et `flux` du projet sont gardées et tenues à jour
comme « genre et workflow principaux » (le premier), pour que le bureau, le relevé et l'installation actuels continuent
de les lire. *Choix de conception.*

## 5. Le parcours d'une nouvelle demande de fonctionnalité

Dans le moteur (`moteur/regles.py`, `_sur_fonctionnalite`), **avant** le cadrage :

1. **Classer la demande** : un nouvel appel de jugement `classer_genre` (Haiku, contexte neuf, comme les autres
   jugements de `moteur/jugement.py`). Dossier : le texte et les images de la demande ; le nom du projet ; les genres
   déjà utilisés dans le projet (ceux de ses workflows) avec leur description ; les genres connus de la skill
   (`memoire.genres` : `id`, `domaine`, `livrable`, `outils`). Réponse validée :
   `{"verdict": "meme" | "proche" | "autre" | "incertain", "genre": id | null, "nouveau": {"id", "description"} | null,
   "raison": texte}`.
   - `meme` : le genre d'une fonctionnalité du projet → la fonctionnalité prend ce genre ; étape 3.
   - `proche` : un genre existant (du projet ou de la skill) assez proche pour partager ses leçons → rattaché ; étape 3.
   - `autre` : genre différent → étape 2. `nouveau` propose un identifiant et une description si aucun genre connu ne
     convient.
   - `incertain` : la consigne dit de répondre `incertain` plutôt que d'élargir un genre (anti-objectif 2) → étape 2,
     avec la question formulée comme une hésitation.
   La consigne de `classer_genre` porte le critère de l'utilisateur : *proche* = mêmes savoir-faire, mêmes outils, même
   sorte de livrable (badge Twitch, emote, logo de chat : proches ; jeu Android : autre).
2. **Avertir et proposer** (verdict `autre` ou `incertain`) : une décision nouvelle `genre_fonctionnalite` (portée : la
   fonctionnalité) : « Cette demande n'est pas du genre du projet (<genre du projet>) : elle relève de <genre proposé>.
   La faire dans un nouveau projet, ou dans ce projet ? ». Le bureau montre trois issues :
   - **Nouveau projet** → formulaire de création (section 6), puis la demande y part ;
   - **Dans ce projet** → la fonctionnalité garde ce genre, étape 3 ;
   - (pour `incertain`) **C'est le même genre** → rattachée au genre du projet, cadrage normal.
   L'utilisateur peut corriger le genre proposé (liste des genres connus + « nouveau genre… » comme la décision
   `confirmer_genre` actuelle, `bureau/web/ui/decisions.js`).
3. **Proposer le workflow de la fonctionnalité** (toujours : un workflow par fonctionnalité) : un nouvel appel de
   jugement `proposer_organisation` (Sonnet). Dossier : la demande, le genre, la description du projet, les services,
   les agents existants (clé, rôle, modèle, spécialité), les workflows des fonctionnalités **du même genre** dans le
   projet (le plus récent d'abord : la consigne dit de le reprendre tel quel s'il convient, et de n'ajouter que ce que
   la demande exige), les règles de modèle (ci-dessous).
   Réponse : un workflow (étapes ordonnées avec rôle et service), les **nouveaux** agents seulement (rôles non pourvus),
   les **nouveaux** services seulement, les briefs des nouveaux rôles, le modèle de chaque nouvel agent avec une
   justification d'une ligne. Le moteur calcule le coût par `installation/estimation.estimer` (en code, pas par l'IA)
   et vérifie la proposition par `proposition.verifier_organisation` (chaque rôle du workflow a un agent et un brief).
   Il pose la décision `organisation` existante (`lancer decision`, portée projet), étendue d'un `workflow`
   (`{id, genre, flux}`) et de la `fonctionnalite` concernée.
4. **Mettre en place** à l'acceptation (`_sur_organisation`) : services créés, agents recrutés (fiches et briefs), le
   workflow ajouté à `workflows`, la fonctionnalité rattachée (`genre`, `workflow`), puis **le cadrage démarre**. Le
   genre nouveau est créé dans la mémoire de la skill (`memoire.creer_genre`) au même moment.
   Au refus : le refus peut porter un texte (« pas de service qualité », « Sonnet plutôt qu'Opus »…) ; le moteur
   relance `proposer_organisation` avec ce texte et repose la décision. Sans texte, la fonctionnalité reprend le
   workflow le plus récent du même genre dans le projet s'il existe, sinon le workflow principal, et le moteur le dit ;
   dans un projet qui n'a encore aucun workflow, la décision reste posée avec ces deux issues (proposer autre chose,
   ou abandonner la demande) : rien n'avance en silence (anti-objectif 1).
5. **Le cadrage** est fait par l'agent du rôle de cadrage du **workflow de la fonctionnalité** (même règle que
   `_role_cadrage` aujourd'hui, appliquée aux étapes de ce workflow). Tout le reste du parcours (cahier, découpage,
   prototype, série, contrôle) lit **le workflow de la fonctionnalité** au lieu du flux du projet : `_production`,
   `_colonne_du_role`, `_tache_de_flux`, les dossiers de `decouper` et `ecrire_methode`, les lots.

**Un workflow complet, jusqu'au livrable** (décision de l'utilisateur) : la proposition pense **toutes les étapes**
jusqu'à la remise du résultat, pas seulement la fabrication. Exemples : un jeu Android doit finir par un fichier `.apk`
remis à l'utilisateur, donc une étape et un **service de livraison** (construction, signature, dépôt du fichier dans les
livrables) ; et, dès que c'est logique pour le genre, une **équipe qualité** (un service et un rôle) qui prend le sujet
en main et **vérifie la bonne exécution** (tests, essai du livrable, conformité au cahier), avec ses verdicts comme le
contrôle actuel (section « sans relecteur » du moteur : la dernière étape rend des `verdicts` par élément, un refus part
en correction). La consigne de `proposer_organisation` le demande explicitement (« de la demande au livrable remis :
fabrication, qualité, livraison »), et le moteur refuse une proposition dont le workflow ne finit pas par une étape qui
produit ou remet le livrable (contrôle en code, avec renvoi au jugement une fois comme les autres jugements).

**Règles du choix de modèle** (dans la consigne de `proposer_organisation` et vérifiées en code) : Haiku pour un
travail mécanique ou de vérification ; Sonnet pour la création et le code courant ; Opus pour une conception difficile
ou un travail où l'erreur coûte cher. **Fable** : jamais par défaut. La proposition peut le suggérer pour un agent
(`modele: "Opus"`, `fable_suggere: true`, raison) ; le bureau montre alors une case séparée « Utiliser Fable pour cet
agent (coût : …) », décochée. Cochée, l'agent est recruté sur Fable ; c'est l'accord du Directeur, **pour cet agent
seulement**. Les garde-fous actuels qui refusent Fable (`MODELES_INTERDITS` de `outil.py`, `proposition._modele`,
`moteur/appel.py`, `moteur/agents.py`…) acceptent Fable **seulement** sur une fiche portant la marque de cet accord
(champ de fiche, par exemple `Fable : accordé par le Directeur le <date>`). Le moteur ne choisit jamais Fable de
lui-même (montée de modèle, jugements).

## 6. Créer un projet depuis le bureau

**Deux entrées** : l'issue « Nouveau projet » de la décision `genre_fonctionnalite`, et l'entrée « Nouveau projet… » de
la liste déroulante des projets (`bureau/web/ui/barre.js:majProjets`).

**Le formulaire** :
- **Répertoire parent** : un champ texte (le bureau est utilisé depuis un téléphone : pas de sélecteur de fichiers du
  système), pré-rempli et avec des suggestions : les dossiers parents des projets déjà inscrits au bureau. Le chemin
  doit exister, être un dossier, et ne pas être dans le dépôt de la skill. *Choix de conception.*
- **Nom du projet** : il devient le nom du dossier (`<parent>/<nom>`). Refusé s'il existe déjà, s'il contient des
  caractères interdits dans un nom de dossier Windows, ou s'il est vide.
- **Mots interdits** et **facturation** (un objectif ou non) : pré-remplis avec ceux du projet d'origine (depuis la
  liste déroulante : du projet affiché), modifiables. Le nom du nouveau projet est ajouté aux mots interdits (il ne
  doit jamais partir dans la mémoire publique de la skill). Les autres réglages (charge, modèle de l'orchestrateur,
  agents locaux, couche du moteur, consignes du projet) sont **repris du projet d'origine** sans être demandés.
- **GitHub** : oui / non (défaut non). Oui : dépôt **privé** créé par `gh repo create <nom> --private --source . --push`
  après `git init` et un premier commit, comme le fait la skill d'installation (`skills/installer/SKILL.md`). Si `git`
  ou `gh` manque, ou si `gh` n'est pas connecté : le projet est créé quand même, en local, et le bureau dit pourquoi
  GitHub n'a pas été fait et comment le faire (anti-objectif 1).
- **Description du projet** : demandée seulement depuis la liste déroulante (sans demande d'origine). Elle sert à
  proposer le genre du projet. *Choix de conception :* le bureau ne fait aucun appel d'IA (seul le moteur en fait) ; le
  projet est donc créé **sans genre**, avec sa description gardée dans `factory.json`. À son premier passage sur un
  projet sans genre, le moteur lance `classer_genre` sur la description et pose la décision `confirmer_genre` existante
  (genre proposé, existant ou nouveau, modifiable). Le formulaire le dit : « Le genre vous sera proposé dans un
  instant. »

**La création** (côté serveur, une route nouvelle du bureau, qui appelle une fonction nouvelle de `installation/`) :
1. Contrôles : répertoire, nom, `MAX_PROJETS` du bureau (12) ; au-delà, refus avec explication (et, depuis une
   décision, l'issue « Dans ce projet » reste possible).
2. Création de `<parent>/<nom>/` et de `.factory/` avec l'arborescence complète de la skill, comme
   `installation/mise_en_place.appliquer` (`_ecrire_configuration`, `DOSSIERS`, `reglages.json`, `controles.md`,
   `consignes-projet.md`, `.gitignore`), mais **sans workflow ni agent** : le projet est vide d'organisation jusqu'à sa
   première demande. Cela demande d'accepter un `factory.json` sans `flux` (aujourd'hui au moins une étape exigée par
   `orchestrateur/factory.py`) : un projet sans workflow est valide, et sa première demande passe par la section 5
   (étape 3). Le genre du projet : celui de la demande d'origine, ou celui proposé d'après la description (confirmé
   par l'utilisateur dans le formulaire, comme `confirmer_genre`).
3. Inscription au bureau (`mise_en_place.inscrire`) : le projet apparaît dans la liste déroulante sans redémarrage
   (`Bureau.actualiser_projets` relit `bureau.json`), et le moteur le prend à son prochain passage (`moteur/boucle.py`
   relit le bureau).
4. GitHub si demandé (ci-dessus).
5. **Depuis une décision** : la demande d'origine (texte, images) est recréée comme demande `fonctionnalite` du nouveau
   projet, dont le moteur fait la section 5 (son genre est déjà connu : étape 3 directement). Dans le projet d'origine,
   la fonctionnalité passe à une **étape nouvelle `deplacee`** (avec le nom du projet d'arrivée), et une ligne de sa
   discussion le dit : « Partie dans le projet <nom> ». *Choix de conception :* `deplacee` n'est pas `terminee` : elle
   ne compte ni comme livrée, ni dans les KPI, ni dans les coûts de livraison ; le relevé (`bureau/releve.py`,
   `ETAPES`), `bureau/etat.py`, les KPI et la page l'affichent comme telle. Rien d'autre ne reste dans le projet
   d'origine.
6. Le bureau bascule sur le nouveau projet (choix gardé comme aujourd'hui dans `localStorage`).

## 7. La mémoire et les leçons

- Le **départ** d'un agent (`orchestrateur/depart.py`, `cmd_depart`, `_depart_d_un_lot`) donne les leçons du **genre de
  la fonctionnalité de la tâche**, plus celles de la skill ; l'en-tête dit le genre de la fonctionnalité. Une tâche sans
  fonctionnalité prend le genre principal du projet.
- Une leçon d'étage `genre` validée s'ajoute à la mémoire du **genre de la fonctionnalité** où elle a été notée
  (`_appliquer_lecon` utilise aujourd'hui `ctx.f["genre"]`).
- L'estimation par genre (`installation/estimation.usages_du_genre`) lit les usages **par genre de fonctionnalité** :
  chaque usage noté porte le genre de sa fonctionnalité (champ ajouté à l'usage), et les usages anciens sans genre
  comptent pour le genre principal de leur projet.
- Anti-objectif 2 : la consigne de `classer_genre` et celle des leçons (`texte_general`) rappellent qu'un genre doit
  rester précis.

## 8. Ne jamais bloquer

| Ce qui peut manquer | Ce qui se passe |
|---|---|
| `classer_genre` échoue deux fois | La fonctionnalité prend le genre principal du projet, le cadrage démarre, une ligne le dit dans la discussion. |
| L'utilisateur ne répond pas à `genre_fonctionnalite` | La fonctionnalité attend sa réponse (comme toute décision) ; le reste du projet avance. |
| `proposer_organisation` échoue ou propose une organisation invalide | Une question au Directeur (comme un jugement raté aujourd'hui) avec l'issue « continuer avec le workflow actuel ». |
| Organisation refusée | Avec un texte : nouvelle proposition. Sans texte : le workflow le plus récent du même genre, sinon le principal, et le moteur le dit ; projet sans aucun workflow : la décision reste posée (proposer autre chose ou abandonner). |
| Création du projet impossible (droits, nom pris, 12 projets) | Message clair dans le formulaire ; depuis une décision, l'issue « Dans ce projet » reste là. |
| `git`/`gh` absent ou non connecté | Projet créé en local, GitHub expliqué. |
| Un rôle du workflow sans agent libre | Comportement actuel (attente d'un agent libre) ; jamais un rôle sans fiche : la mise en place refuse un workflow dont un rôle n'a pas d'agent. |

## 9. Le bureau

- **Liste déroulante** : une dernière entrée « Nouveau projet… » qui ouvre le formulaire (section 6).
- **Décision `genre_fonctionnalite`** : texte, genre proposé (modifiable), issues « Nouveau projet », « Dans ce
  projet » (et « C'est le même genre » si incertain).
- **Décision `organisation`** étendue : le workflow proposé (étapes, rôles, services), les nouveaux agents avec leur
  modèle et sa justification, les nouveaux services, le coût estimé, et la case Fable par agent quand elle est
  suggérée (section 5).
- **Tableau** : colonnes = `cadrage`, puis les étapes de chaque workflow dans l'ordre de réalisation (les workflows dans
  l'ordre de leur création, les étapes dans l'ordre du flux), puis `fait`. **Chaque colonne affiche son genre.** Le
  relevé (`outil.py`, `colonnes`) donne pour chaque colonne `{id, nom, genre, workflow}`. Toute la page qui lit
  `colonnes` (plan, kanban, détail, documents par étape, régie : voir `bureau/web/main.js`, `scene/kanban.js`,
  `ui/kanban-plein.js`, `ui/detail.js`, `ui/fonctionnalite.js`, `logique/regie.js`, `logique/plan.js`) suit.
  *Choix de conception :* un workflow par fonctionnalité allonge le tableau à chaque fonctionnalité ; le tableau ne
  montre donc que les colonnes des fonctionnalités **en cours** (ni `terminee` ni `deplacee`), plus `cadrage` et
  `fait`. Les colonnes d'une fonctionnalité finie restent lisibles depuis sa page (documents par étape).
- La page d'une fonctionnalité affiche son genre et son workflow.

## 10. Coût attendu

- `classer_genre` : un appel Haiku court par **nouvelle fonctionnalité**, de l'ordre de 0,002 €.
- `proposer_organisation` : un appel Sonnet par **nouvelle fonctionnalité** (un workflow chacune), de l'ordre de
  quelques centimes (à mesurer au banc). Quand un workflow du même genre existe, la consigne le fait reprendre : la
  réponse est courte.
- L'objectif de l'orchestration procédurale (≤ 0,10 € sur l'essai de référence, mesuré à 0,05–0,08 €) doit rester
  tenu avec ces deux appels de plus : le banc (`py -3.12 -m banc moteur`) le vérifie. Si l'objectif n'est plus tenu,
  c'est `proposer_organisation` qu'il faut resserrer (comme `ecrire_methode` en phase D). Le scénario du banc doit
  alors donner les deux gestes nouveaux (accepter l'organisation proposée ; la demande de l'essai est du genre du
  projet).

## 11. Ce qui reste au constructeur

- Les noms exacts des champs, routes, commandes et consignes, dans le style du dépôt (français, bibliothèque standard).
- Les consignes des jugements `classer_genre` et `proposer_organisation` (mesurées comme en phase A : validité au
  premier essai, tokens).
- L'emplacement des nouveaux tests (un test nommé par règle, comme `tests/test_moteur_regles.py`).
- La mise en page du formulaire et des décisions au bureau, dans le style existant.
- Le découpage en phases par modèle, selon la norme du dépôt (`docs/superpowers/plans/*-passation.md`).
