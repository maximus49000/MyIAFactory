# L'installation sur un projet — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (une conversation par lot de modèle, voir la passation `2026-11-11-installation-sur-un-projet-passation.md` : l'ordre des tâches y est celui des lots, pas celui des numéros). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La skill devient un plugin Claude Code ; depuis le dossier d'un projet, une commande mène la discussion (projet vide ou existant), propose une organisation chiffrée, puis configure tout (fichier de factory, réglages, fiches, consignes, contrôles, bureau commun, accès mobile si demandé) pour partir sur une première fonctionnalité ; le bureau devient accessible au téléphone (Tailscale, Wi-Fi de la maison) avec un code d'accès et une vue 3D adaptée ; ensuite l'orchestrateur fait évoluer l'organisation par des décisions du Directeur.

**Architecture:** Un nouveau paquet `installation/` (Python, bibliothèque standard) : `dossier.py` (le dossier stable `~/MyIAFactory`), `examen.py` (vide, existant, déjà installé), `calibrage.py`, `estimation.py`, `proposition.py` (contrôle d'une proposition), `mise_en_place.py` (écriture, inscription au bureau, réparation, organisation), `outil.py` (ligne de commande). Le plugin : `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `skills/installer/SKILL.md` (les consignes de la discussion). Côté orchestrateur et bureau : chemins `~` développés, limite d'agents locaux tenue, leçon gardée en local si le push échoue, décision et commande `organisation`, écouteurs distants avec code d'accès (`bureau/acces.py`), vue 3D adaptée au mobile (`logique/mobile.js`).

**Tech Stack:** Python 3.12 bibliothèque standard ; JavaScript en modules ; `git` et, dans la discussion seulement, `gh` ; tests `unittest` et `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-11-installation-sur-un-projet-design.md` (contexte : `2026-11-10-parcours-d-une-tache-design.md`, `docs/orchestrateur.md`, `docs/installation.md`).

## Global Constraints

- Dépôt public, vide de tout projet : aucun nom, lieu, chemin, fichier ou personne d'un projet réel. Le projet pilote n'est jamais nommé. L'adresse du dépôt public `https://github.com/maximus49000/MyIAFactory.git` est la seule adresse propre à l'auteur qui entre dans le code (`installation/dossier.py`).
- Python : `py -3.12`, bibliothèque standard uniquement. Tests : `py -3.12 -m unittest discover -s tests -v` et `node --test "bureau/web/tests/*.test.js"`.
- Dossier stable : `~/MyIAFactory` ; la skill y est en `~/MyIAFactory/skill` ; le fichier de bureau commun en `~/MyIAFactory/bureau.json` ; les propositions en attente en `~/MyIAFactory/propositions/`. Dans tout fichier versionné, la skill s'écrit `~/MyIAFactory/skill/...` (jamais un chemin absolu).
- **Rien n'est écrit dans le dossier du projet avant `appliquer`** : `examiner`, `calibrer`, `estimer`, `proposer` n'y écrivent rien.
- Modèles : Haiku, Sonnet, Opus ; **Fable refusé par tout outil** (proposition, organisation, fiche).
- Accès mobile : `127.0.0.1` reste toujours ouvert ; les écouteurs distants (adresse Tailscale, adresse du réseau local privé) n'existent que si le fichier de bureau les demande, et **chaque requête qui y arrive exige le cookie d'accès**, y compris depuis la machine elle-même. Aucun tunnel public, aucun hébergement.
- Le bureau n'agit jamais lui-même et n'appelle aucune IA ; un geste devient une demande.
- Versionnés dans le projet : `.factory/factory.json`, `.factory/reglages.json`, fiches, briefs, consignes propres, contrôles, suivi. Ignorés par git : `.factory/equipe.json`, `.factory/*-historique.jsonl`.
- Les tests n'utilisent jamais le vrai dossier de l'utilisateur ni le réseau : ils fixent `HOME` et `USERPROFILE` sur un dossier temporaire, et les appels `git` passent par une fonction injectée ou par des dépôts temporaires locaux.
- Chaque tâche : test d'abord, le voir échouer, coder, le voir passer, tous les tests ; cocher dans le `README.md` ; commit en français terminé par `Co-Authored-By: Claude <modèle de la conversation> <noreply@anthropic.com>` ; `git push`.

## Review Focus

1. Projet existant très lourd (`node_modules`, dossier `Library` d'un moteur, 100 000 fichiers, lien symbolique qui sort du dossier) : l'examen reste borné (2 s, 200 entrées d'arbre) et ne suit pas les liens. (Tâche 5 : `test_gros_dossier`, `test_lien_sortant_ignore`.)
2. Commande relancée, `appliquer` lancé deux fois, bureau déjà à 12 projets, `bureau.json` illisible : aucun doublon, refus clair, rien de cassé. (Tâche 7 : `test_appliquer_deux_fois_refuse`, `test_bureau_plein`, `test_bureau_illisible_rien_ecrit`.)
3. Dossier utilisateur avec espaces et accents (`Zoé Martin`) : les chemins `~` se développent, le bureau lance les commandes, `bureau.json` se relit. (Tâche 1 : `test_tilde_espaces_accents` ; tâche 7 : `test_chemin_espaces_accents`.)
4. Échec au milieu de la mise en place (fiche invalide, disque plein simulé) : aucun `.factory/` à moitié écrit, `.gitignore` et `bureau.json` intacts. (Tâche 7 : `test_echec_au_milieu_rien_ne_reste`.)
5. `.gitignore` absent, sans fin de ligne, ou portant l'ancienne règle `.factory/` du guide : la configuration devient versionnée, le bloc n'est ajouté qu'une fois. (Tâche 7 : `test_gitignore_ancienne_regle`, `test_gitignore_idempotent`.)
6. Le bureau ouvert au réseau : une requête sur l'écouteur distant sans cookie, avec un cookie d'avant une révocation, avec un code d'association déjà servi ou expiré, ou avec un `Host` inconnu → 401 ou 403, aucune donnée ; `/api/acces` (le code et le QR) n'est jamais servi à l'écouteur distant. (Tâche 15 : `test_distant_sans_cookie_401`, `test_revoquer_invalide_les_cookies`, `test_code_usage_unique`, `test_api_acces_jamais_a_distance`.)
7. Photo prise au téléphone : 12 Mo, format HEIC ou WebP, très grande définition → réduite et réencodée en JPEG sous 5 Mo dans la page avant l'envoi, jamais refusée en silence. (Tâche 16 : tests de `dimensionsReduites`, `formatEnvoye` et `qualitePour`.)
8. Lots par modèle : `depend_de` qui forme un cycle, nomme une tâche inconnue ou une tâche déjà faite ; une relecture qui dépend du travail relu ; 12 tâches du même modèle → refus clair pour le cycle et l'inconnue, relecture toujours seule, lots de 5 au plus, ordre d'origine gardé à défaut de dépendance connue. (Tâche 17 : `test_cycle_refuse`, `test_relecture_jamais_en_lot`, `test_lot_de_cinq_au_plus`.)

---

## Étape 1 — l'orchestrateur et le bureau s'y prêtent

### Task 1 : les chemins `~`

**Files:** Modify `orchestrateur/factory.py`, `bureau/releve.py`, `orchestrateur/outil.py` (`lancer_declaree`) ; Test `tests/test_orch_factory.py`, `tests/test_releve.py`

**Interfaces:**
- Produces: `bureau.releve.developper(arg: str) -> str` : un argument qui commence par `~/` ou `~\` est développé par `os.path.expanduser` ; tout autre argument est rendu tel quel. `releve._executer` développe chaque argument de `cmd` (le relevé, les actions, le catalogue passent tous par lui). `lancer_declaree` développe aussi ses arguments.
- `factory.lire` : un chemin qui commence par `~` est développé puis résolu ; les autres restent relatifs au fichier de factory.

- [ ] **Step 1 : tests** — `test_tilde_dans_skill` (`"skill": "~/MyIAFactory/skill"` avec `HOME`/`USERPROFILE` temporaires → `f["skill"]` sous ce dossier), `test_tilde_au_milieu_inchange` (`"a~b"`, `"~x"`), `test_commande_releve_tilde` (une commande `["python", "~/s/ecrire.py"]` écrit le relevé), `test_tilde_espaces_accents` (dossier utilisateur `Zoé Martin`).
- [ ] **Step 2–4 :** échec, coder, tous verts. **Step 5 :** commit « Chemins ~ dans la factory et les commandes ».

### Task 2 : la limite d'agents locaux

**Files:** Modify `orchestrateur/factory.py`, `orchestrateur/depart.py`, `orchestrateur/outil.py` (`cmd_agent_libre`, `construire_releve`), `bureau/releve.py`, `bureau/etat.py`, `bureau/web/ui/barre.js`, `orchestrateur/consignes.md`, `orchestrateur/interface.md` ; Test `tests/test_orch_depart.py`, `tests/test_orch_factory.py`, `tests/test_releve.py`, `tests/test_etat.py`

**Interfaces:**
- Produces: clé de factory `agents_locaux_max` (entier de 1 à 16, défaut 2) ajoutée à `CLES` et rendue par `lire`.
- `depart.agent_libre(fiches, taches, role, modele=None, lieu=None, agents_locaux_max=None)` : quand le nombre de tâches actives tenues par un agent local atteint la limite, aucun agent local n'est rendu ; raison exacte `"limite de {n} agents locaux atteinte"` ; les agents cloud ne comptent pas.
- Relevé version 4 : `agents_locaux_max` facultatif à la racine (entier ≥ 1 ou nul ; normalisé à `None`) ; `construire_releve` le remplit depuis la factory ; `etat.construire` le rend tel quel (absent en version < 4) ; la bulle de la barre de charge ajoute « {n} agents locaux au plus ».
- Consignes, section « Choisir l'agent et le modèle » : une ligne « `agent-libre` tient la limite d'agents locaux du projet : s'il répond « limite … atteinte », la tâche attend (ou un agent cloud la prend) ».

- [ ] **Step 1 : tests** — `test_limite_agents_locaux` (limite 1, une tâche locale active → `(None, "limite de 1 agents locaux atteinte")`), `test_limite_ne_compte_pas_le_cloud`, `test_agents_locaux_max_invalide` (`0`, `17`, `true`, `"2"` refusés, message nommant la clé), `test_agents_locaux_max_releve_v4`, `test_etat_agents_locaux_max`.
- [ ] **Step 2–4 :** échec, coder, verts (dont `test_orch_consignes`). **Step 5 :** commit « Limite d'agents locaux tenue par agent-libre ».

### Task 3 : une leçon gardée en local quand le push échoue

**Files:** Modify `orchestrateur/memoire.py` (`_ecrire_et_pousser`), `orchestrateur/consignes.md` (section « Les leçons ») ; Test `tests/test_orch_memoire.py`

**Interfaces:**
- `_ecrire_et_pousser` : un échec de `git push` (et de lui seul) **garde** le fichier et le commit et rend `(True, "Leçon ajoutée et commitée dans la copie locale ; « git push » a échoué (droits ou réseau) : elle n'est pas publiée. " + détail)` (400 caractères au plus). Les échecs de `pull`, `add`, `commit` et les mots interdits restent des arrêts sans rien écrire.

- [ ] **Step 1 : tests** — `test_push_refuse_garde_le_commit_local` (git simulé : push rend 1 → fichier écrit, `reset` jamais appelé, message contenant « n'est pas publiée »), `test_conflit_arrete_sans_commit` inchangé.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Leçon gardée en local si le push échoue ».

## Étape 2 — les outils de l'installation

### Task 4 : le dossier stable

**Files:** Create `installation/__init__.py`, `installation/dossier.py` ; Test `tests/test_inst_dossier.py`

**Interfaces:**
- Produces: `DEPOT = "https://github.com/maximus49000/MyIAFactory.git"`, `PREFIXE_SKILL = "~/MyIAFactory/skill"` ; `racine() -> Path` (`Path("~/MyIAFactory").expanduser()`), `skill() -> Path`, `bureau() -> Path` (`racine()/"bureau.json"`), `propositions() -> Path`.
- `executer_git(args, cwd) -> (code, sortie)` (même forme que `orchestrateur.memoire.executer_git`, réutilisée).
- `preparer(lier=None, git=executer_git, lien=creer_lien) -> {"skill": str, "action": "clone" | "mise_a_jour" | "lien" | "deja_lie", "message": str}` :
  - `skill()` existe et est un dépôt git → `git pull --ff-only` ; un échec n'arrête rien (`action: "mise_a_jour"`, le message le dit) ;
  - sinon `lier` donné (un clone existant de la skill, contrôlé : il contient `orchestrateur/outil.py`) → `lien(lier, skill())` (`action: "lien"`) ;
  - sinon `git clone DEPOT skill()` ; un échec → exception `Echec` au message clair.
- `creer_lien(cible, lien)` : jonction `mklink /J` sous Windows (pas de droits administrateur), `os.symlink` ailleurs.

- [ ] **Step 1 : tests** — `test_clone_au_premier_usage`, `test_pull_aux_suivants`, `test_pull_echoue_continue`, `test_lier_un_clone_existant`, `test_lier_refuse_un_dossier_qui_n_est_pas_la_skill`, `test_racine_suit_home` (git et lien simulés, `HOME`/`USERPROFILE` temporaires).
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Installation : le dossier stable ».

### Task 5 : l'examen du dossier

**Files:** Create `installation/examen.py` ; Test `tests/test_inst_examen.py`

**Interfaces:**
- Produces: `examiner(dossier: Path) -> dict` : `{"cas", "factory", "inventaire", "environnement"}`.
  - `cas` : `"installe"` si `.factory/factory.json` existe ; `"factory_propre"` si `.factory/reglages.json` existe sans clé `orchestrateur` ; `"vide"` s'il n'y a aucun fichier hors `IGNORES_VIDE = (".git", ".gitignore", ".gitattributes", "README*", "LICENSE*", ".claude", ".vscode", ".idea")` ; sinon `"existant"`.
  - `inventaire` : `arbre` (dossiers et fichiers jusqu'à la profondeur 2, 200 entrées au plus), `fichiers_cles` (ceux de `FICHIERS_CLES` présents, chemins relatifs), `extensions` (les 10 plus fréquentes avec leur nombre), `nb_fichiers` (compté jusqu'à 100 000, puis `"100000+"`), `git` `{"depot": bool, "distant": str | None}` (lu localement, sans réseau). Parcours sans suivre les liens, en sautant `DOSSIERS_SAUTES = (".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "Library", "Temp", "obj", "bin", ".factory")`, arrêté à 2 s.
  - `FICHIERS_CLES` : `README*`, `package.json`, `pyproject.toml`, `requirements.txt`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, `*.csproj`, `*.sln`, `ProjectSettings/ProjectVersion.txt`, `Gemfile`, `composer.json`, `Dockerfile`, `CLAUDE.md`.
  - `environnement` : la liste de ce qu'un agent cloud devrait trouver, déduite des fichiers clés (`Node.js`, `Python`, `.NET`, `Rust`, `Go`, `Java`, `Ruby`, `PHP`, `Docker`, et pour `ProjectVersion.txt` « moteur de jeu, version <lue> ») ; vide → environnement de base.
- L'examen ne lit le contenu d'aucun fichier, sauf `ProjectVersion.txt` (sa première ligne) et `.factory/reglages.json` (la présence de la clé).

- [ ] **Step 1 : tests** — `test_dossier_vide`, `test_vide_avec_readme_et_git`, `test_existant_python` (environnement `["Python"]`), `test_installe`, `test_factory_propre`, `test_node_modules_saute`, `test_gros_dossier` (5 000 fichiers sur 3 niveaux : moins de 2 s, arbre ≤ 200), `test_lien_sortant_ignore`, `test_rien_n_est_ecrit` (contenu du dossier identique avant et après).
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Installation : l'examen du dossier ».

### Task 6 : le calibrage et l'estimation du coût

**Files:** Create `installation/calibrage.py`, `installation/estimation.py` ; Test `tests/test_inst_calibrage.py`, `tests/test_inst_estimation.py`

**Interfaces:**
- Consumes: `bureau.charge.machine()`, `bureau.charge.conseiller(historique, mach)`, `bureau.charge.Historique`.
- Produces: `calibrer(mach: dict, historique: list) -> {"charge_max": int, "agents_locaux_max": int, "source": "machine" | "historique" | "indisponible", "explication": str}` :
  - `charge_max` = `conseiller(...)["valeur"]` ;
  - mesure indisponible → `agents_locaux_max = 1`, explication « Mesure indisponible sur cette machine : 1 agent local, par prudence. » ;
  - sans historique suffisant (moins de 30 mesures avec agents) → `min(coeurs // 4, int(memoire_go // 6))` borné à 1..4 ;
  - avec historique → `floor((85 - repos) / par_agent)` (mêmes `repos` et `par_agent` que `conseiller`) borné à 1..6.
- `DEFAUTS_TOKENS = {"Haiku": (40_000, 150_000), "Sonnet": (80_000, 300_000), "Opus": (80_000, 300_000)}` par étape d'un élément ; `PART_SORTIE = 0.2` (part des tokens en sortie, pour les euros).
- `usages_du_genre(bureau_json: Path, genre: str | None) -> list[dict]` : les lignes `usage-historique.jsonl` des projets du fichier de bureau dont la factory a ce genre (aucune si `genre` est nul ou le bureau absent).
- `estimer(flux, agents, usages, prix_de) -> {"tokens": [min, max], "euros": [min, max] | None, "source": "mesures" | "defauts" | "mixte", "detail": [{"etape", "modele", "tokens": [a, b], "source"}], "explication": str}` : pour chaque étape, le modèle de l'agent de son rôle ; 5 usages ou plus de ce modèle → quartiles 1 et 3 de leurs tokens totaux, sinon `DEFAUTS_TOKENS` ; plus une étape de cadrage sur Sonnet ; `prix_de(modele) -> {"entree": €/token, "sortie": €/token} | None` ; un prix manquant → `euros: None` et l'explication dit « prix inconnu ».

- [ ] **Step 1 : tests** — calibrage en tableau (machine 4 cœurs 8 Go → 1 ; 16 cœurs 32 Go → 4 ; indisponible → 1 ; historique repos 20 %, 15 % par agent → 4) ; `test_defauts_sans_mesure`, `test_mesures_du_genre_seulement` (les usages d'un autre genre ne comptent pas), `test_euros_sans_prix_none`, `test_fourchette_ordonnee` (min ≤ max partout).
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Installation : calibrage et estimation ».

### Task 7 : la proposition, la mise en place, le bureau commun, la réparation

**Files:** Create `installation/proposition.py`, `installation/mise_en_place.py` ; Test `tests/test_inst_proposition.py`, `tests/test_inst_mise_en_place.py`

**Interfaces:**
- Consumes: `dossier.*`, `orchestrateur.factory.lire`, `orchestrateur.fiches.ecrire_fiche`, `orchestrateur.memoire.genres`/`creer_genre`, `bureau.reglages.lire_bureau`, `orchestrateur.verifier_interface` (sans `--complet`, en processus), les modèles `orchestrateur/modeles/` et `exemples/projet-neuf/`.
- Produces: `proposition.verifier(p: dict) -> list[str]` (vide = valide). Format (version 1) :
  `{"version": 1, "projet": chemin absolu, "cas": "vide" | "existant", "nom", "comprehension": texte, "genre": id | null, "genre_nouveau": {"description"}?, "mots_interdits": [textes], "modele_orchestrateur", "charge_max", "agents_locaux_max", "cloud": bool, "facturation": bool, "services": [{id, nom}], "flux": [{id, nom, role, service, justification}], "agents": [{cle, prenom?, role, service, modele, lieu, specialite?, texte, environnement?: [textes]}], "briefs": {role: texte}, "consignes": texte, "controles": [textes], "estimation": objet de estimer}`.
  Règles : services et flux comme `factory.lire` (même motif d'id, `cadrage` et `fait` réservés, service connu) ; chaque rôle du flux a au moins un agent ; chaque agent a un service connu, un modèle ∈ Haiku, Sonnet, Opus (Fable : « Fable n'est jamais choisi par l'installation. »), un lieu `local` ou `cloud` (cloud seulement si `cloud` est vrai), des clés uniques ; chaque étape a une `justification` non vide ; un brief par rôle du flux ; `charge_max` 30..95 ; `agents_locaux_max` 1..16 ; `facturation` vrai interdit un service `facturation` déclaré à la main (il est ajouté par la mise en place).
- `mise_en_place.appliquer(p, maintenant) -> dict` : `{"ecrits": [chemins], "bureau": str, "relancer_bureau": bool, "agents_cloud": [{"cle", "role", "modele", "environnement"}], "message_orchestrateur": str, "verification": [lignes], "pret": bool}`. Refus (`Echec`) si la proposition est invalide ou si `.factory/factory.json` existe déjà (« Déjà installé : lancez la réparation. »).
  - Écrit d'abord tout dans `.factory.tmp/`, puis le renomme en `.factory/` : un échec ne laisse rien. Contenu : `factory.json` (`skill: PREFIXE_SKILL`, `catalogues["*"]` par `~/MyIAFactory/skill/orchestrateur/outil.py`, `agents_locaux_max`, service `facturation` ajouté si `facturation`), `reglages.json` (relevé et actions par `["python", "~/MyIAFactory/skill/orchestrateur/outil.py", "--factory", "factory.json", "lancer", …]`, racines d'images, de documents, de livrables comme `exemples/projet-neuf/reglages.json`, `alias_modeles`, `charge_max`, `prix_automatiques` = `facturation`), `fiches/<cle>.md`, `fiches/briefs/<role>.md`, `consignes-projet.md`, `controles.md` (une entrée par contrôle, format de `orchestrateur/modeles/registre-controles.md`), dossiers `pieces`, `captures`, `livrables`, `methodes`, `documents`.
  - `.gitignore` du projet : retire une ligne `.factory/` ou `.factory` héritée, ajoute une fois le bloc `# MyIAFactory : fichiers propres à la machine` + `.factory/equipe.json` + `.factory/*-historique.jsonl`.
  - Genre : connu (`memoire.genres`) → écrit ; `genre_nouveau` → `memoire.creer_genre` ; s'il échoue, genre nul et la raison va dans le rendu (l'orchestrateur reposera `confirmer_genre`).
  - `inscrire(bureau_json, reglages, id_=None) -> bool` : crée `{"port": 8770, "projets": [...]}` s'il n'existe pas, sinon ajoute (chemin absolu) ; déjà inscrit → `False` ; 12 projets → `Echec` (« Le bureau suit déjà 12 projets. ») ; illisible → `Echec`, fichier intact ; relu par `lire_bureau` après écriture. `relancer_bureau` vrai quand le projet a été ajouté à un bureau existant.
  - `verification` : les lignes de `verifier_interface` ; `pret` vrai s'il n'y a aucun `ÉCART`.
  - `message_orchestrateur` : le texte de `docs/orchestrateur.md` §7 avec le chemin du fichier de factory.
- `reparer(projet: Path, calibrage: dict) -> {"corrections": [textes], "verification": [lignes], "pret": bool}` : `skill` → `PREFIXE_SKILL` ; tout argument de commande (réglages, catalogues) qui finit par `orchestrateur/outil.py` → `~/MyIAFactory/skill/orchestrateur/outil.py` ; `agents_locaux_max` absent → valeur du calibrage ; bloc `.gitignore` ; dossiers manquants ; inscription au bureau. **`commandes` (les adaptateurs) n'est jamais touché.** Deuxième passage → `corrections == []`.
- `ecrire_organisation(factory_json, services, flux, agents, briefs)` : réécrit `services` et `flux` du fichier de factory (le reste gardé, écriture atomique), écrit les fiches et briefs nouveaux ; contrôle comme `proposition.verifier` ; utilisé par `appliquer` et par la tâche 10.

- [ ] **Step 1 : tests** — `test_proposition_valide`, `test_fable_refuse`, `test_role_sans_agent`, `test_cloud_interdit_sans_cloud`, `test_justification_manquante`, `test_appliquer_projet_vide` (`factory.lire` passe, fiches relues par `fiches.lire_toutes`, `pret` vrai), `test_rien_avant_appliquer`, `test_appliquer_deux_fois_refuse`, `test_facturation_non` (pas de service, `prix_automatiques` faux), `test_inscription_bureau_nouveau`, `test_inscription_bureau_existant` (`relancer_bureau` vrai), `test_deja_inscrit`, `test_bureau_plein`, `test_bureau_illisible_rien_ecrit`, `test_gitignore_absent`, `test_gitignore_ancienne_regle`, `test_gitignore_idempotent`, `test_chemin_espaces_accents`, `test_echec_au_milieu_rien_ne_reste`, `test_reparer_chemins_absolus`, `test_reparer_garde_les_adaptateurs`, `test_reparer_idempotent`, `test_genre_nouveau_echoue_reste_nul`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Installation : proposition, mise en place, bureau commun, réparation ».

### Task 8 : la ligne de commande de l'installation

**Files:** Create `installation/outil.py` ; Test `tests/test_inst_outil.py`

**Interfaces:**
- Produces: `py -3.12 installation/outil.py <commande> [arguments]`, sortie JSON UTF-8, codes 0 (fait), 1 (refus, `{"erreur"}`), 2 (appel invalide) :
  - `preparer [--lier <chemin>]` → `dossier.preparer` ;
  - `examiner <dossier>` → `examen.examiner` ;
  - `calibrer` → `calibrage.calibrer(machine(), historique)` (historique : celui du premier projet du bureau commun s'il existe, sinon vide) ;
  - `estimer` (entrée `{flux, agents, genre}`) → `estimation.estimer` avec les usages du genre et les prix du bureau commun ;
  - `proposer` (entrée : la proposition) → `proposition.verifier`, puis enregistrement en `propositions()/<id du dossier>.json` ; rend `{"proposition": chemin, "estimation"}` ; refus avec la liste des erreurs ;
  - `appliquer <dossier>` → la proposition enregistrée pour ce dossier, `mise_en_place.appliquer`, puis suppression de la proposition ;
  - `reparer <dossier>` → `calibrer` puis `mise_en_place.reparer`.

- [ ] **Step 1 : tests** — `test_parcours_vide_bout_en_bout` (sous-processus, `HOME`/`USERPROFILE` temporaires, git simulé par un dépôt local : `examiner` → `proposer` → `appliquer` → `reparer` sans correction), `test_appliquer_sans_proposition`, `test_proposer_invalide_code_1`, `test_commande_inconnue_code_2`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Installation : la ligne de commande ».

## Étape 3 — le plugin et la discussion

### Task 14 : le support de traitement dans la proposition et la mise en place

**Files:** Modify `installation/proposition.py`, `installation/mise_en_place.py`, `installation/outil.py`, `bureau/reglages.py`, `tests/inst_aide.py` ; Create `installation/acces.py` ; Test `tests/test_inst_proposition.py`, `tests/test_inst_mise_en_place.py`, `tests/test_inst_acces.py`, `tests/test_reglages.py`

**Interfaces:**
- Produces: la proposition gagne `supports` (liste non vide, sans double, de `"ordinateur"`, `"mobile"`) et `acces` `{"tailscale": bool, "reseau_local": bool}` (au moins un vrai si `"mobile"` est dans `supports` ; tous deux faux sinon).
- `acces.adresse_tailscale(executer=subprocess.run) -> str | None` (`tailscale ip -4`, première ligne, délai 5 s ; absent ou en échec → `None`) ; `acces.adresse_reseau_local() -> str | None` (l'adresse IPv4 de sortie de la machine, lue par un `socket` UDP connecté sans envoi, gardée seulement si elle est privée : `10/8`, `172.16/12`, `192.168/16`).
- `outil.py acces` → `{"tailscale": adresse | null, "reseau_local": adresse | null}` (pour la discussion).
- `mise_en_place.appliquer` et `reparer` : si la proposition demande le mobile, le fichier de bureau commun reçoit `acces` (fusion : un accès déjà ouvert le reste) et le rendu gagne `acces: {"tailscale", "reseau_local"}` (les adresses, ou `null`) ; `relancer_bureau` est vrai quand `acces` a changé. `bureau.reglages.lire_bureau` accepte et rend `acces` (défaut : tous deux faux ; tout autre type refusé).

- [ ] **Step 1 : tests** — `test_supports_vides_refuses`, `test_mobile_sans_acces_refuse`, `test_ordinateur_seul_acces_faux`, `test_acces_ecrit_dans_le_bureau`, `test_acces_fusionne`, `test_lire_bureau_acces_invalide`, `test_adresse_reseau_local_publique_refusee`, `test_tailscale_absent_none`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Installation : le support de traitement et l'accès mobile ».

### Task 9 : le plugin et les consignes de la discussion

**Files:** Create `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `skills/installer/SKILL.md` ; Test `tests/test_plugin.py`

**Interfaces:**
- `plugin.json` : `{"name": "myiafactory", "version": "0.4.0", "description": …}` ; `marketplace.json` : la place de marché `myiafactory` avec ce seul plugin, `"source": "./"`. La commande est `/myiafactory:installer`.
- `SKILL.md` (frontmatter `name: installer`, `description`) : les consignes que Claude suit pendant la discussion, **2 000 mots au plus** (contre-but 1 : chaque mot est relu). Elles disent, dans l'ordre de la conception (sections 5 à 8, 11, 12) :
  1. `py -3.12 "${CLAUDE_PLUGIN_ROOT}/installation/outil.py" preparer` ; ensuite toujours `~/MyIAFactory/skill/installation/outil.py` ;
  2. `examiner` le dossier courant ; `installe` → `reparer` et en rendre compte ; `factory_propre` → renvoyer vers `docs/orchestrateur.md` et s'arrêter ;
  3. vide → les questions de la section 6, une à la fois ; existant → lecture confiée à un sous-agent Haiku (arbre, fichiers clés, documentation, un échantillon du code ; résumé du métier en 300 mots au plus), puis reformulation et questions sur les zones d'ombre ;
  4. les questions communes : le support de traitement (ordinateur, mobile : choix multiple ; avec le mobile, `outil.py acces`, puis Tailscale par défaut — la marche à suivre pour installer l'application sur l'ordinateur et le téléphone, que l'utilisateur fait lui-même — et le Wi-Fi de la maison en secours, en disant que son trafic n'est pas chiffré), cloud ou local, facturation, dépôt GitHub (vide), genre proposé parmi `orchestrateur/memoire/genres/` (jamais la mémoire d'un autre genre lue en détail) ; `calibrer` ;
  5. la proposition en cinq parties (compréhension, paramétrage, organisation, workflow avec une justification par étape, estimation par `estimer`), le workflow le plus court qui tienne, le plus petit modèle capable, jamais Fable ; corrections jusqu'à « je valide » ;
  6. `proposer`, puis `appliquer` ; pour un projet vide et si demandé : `git init`, puis `gh repo create <nom> --private --source . --push` après un dernier accord ; pour un projet existant au dépôt GitHub public, le signaler ;
  7. la fin : la liste des agents cloud (clé, rôle, modèle à régler, environnement), la commande du bureau (`py -3.12 ~/MyIAFactory/skill/lancer.py serveur --bureau ~/MyIAFactory/bureau.json`, et « relancez-le » si `relancer_bureau`), le message qui ouvre la conversation orchestratrice ; avec le mobile : relancer le bureau, ouvrir la page sur l'ordinateur, « Associer un téléphone », scanner le QR code ; si `pret` est faux, le dire en clair.

- [ ] **Step 1 : tests** — `test_json_du_plugin` (champs ci-dessus), `test_frontmatter`, `test_commandes_citees_existent` (chaque `outil.py <commande>` cité dans `SKILL.md` existe dans `installation/outil.py`), `test_longueur_consignes` (≤ 2 000 mots), `test_aucun_fable_choisi`. Si `claude plugin validate` existe sur la machine, le passer aussi.
- [ ] **Step 2–4 :** échec, écrire, verts. **Step 5 :** commit « Le plugin et la commande d'installation ».

## Étape 4 — l'organisation qui évolue et les lots par modèle

### Task 10 : la décision et la commande `organisation`

**Files:** Modify `bureau/releve.py`, `bureau/demandes.py`, `bureau/web/ui/directeur.js`, `orchestrateur/outil.py` (`cmd_decision`, nouvelle `cmd_organisation`, `cmd_actions`), `orchestrateur/verifier_interface.py`, `orchestrateur/consignes.md`, `orchestrateur/interface.md` ; Test `tests/test_releve.py`, `tests/test_demandes.py`, `tests/test_orch_interface.py`, `bureau/web/tests/organisation.test.js`

**Interfaces:**
- Consumes: `installation.mise_en_place.ecrire_organisation`, `installation.proposition.verifier` (partie services, flux, agents, briefs).
- Produces: `DECISIONS_PROJET = ("confirmer_genre", "session_cloud", "organisation")`. Une décision `organisation` porte `organisation: {"services": [{id, nom}] (la liste complète après changement), "flux": [...] (complet), "agents": [...] (les nouveaux seulement), "briefs": {...} (nouveaux rôles), "cout": {"tokens": [a, b], "euros": [a, b] | null}}`.
- Demande nouvelle `organisation` : champs `("decision", "verdict")`, `verdict` ∈ `accepter`, `refuser` ; version 4 seulement ; la décision doit exister et être de ce genre.
- `outil.py lancer organisation` `{"action": "appliquer", "decision": id}` → `ecrire_organisation`, décision levée, rend `{"ok": true, "services", "flux"}` ; refus (code 1) si le contenu ne passe plus le contrôle. `verifier_interface` la joue dans le scénario `--complet`.
- Consignes, « Le parcours d'une fonctionnalité », au cadrage : si l'organisation ne couvre pas la fonctionnalité, pose une décision `organisation` (la plus petite qui suffise, coût par `installation/outil.py estimer`) ; verdict `accepter` → `lancer organisation` ; `refuser` → la fonctionnalité continue avec l'organisation actuelle, et tu le dis.
- Directeur : la décision montre les services ajoutés, les colonnes qui changent, les agents (rôle, modèle, lieu), le coût ; boutons « Accepter », « Refuser » ; textes insérés par `textContent`.

- [ ] **Step 1 : tests** — `test_decision_organisation_valide`, `test_decision_organisation_fable_refuse`, `test_demande_organisation_v3_refusee`, `test_demande_organisation_verdict_inconnu`, `test_appliquer_organisation` (factory relue avec le nouveau service et la nouvelle étape, fiche créée, décision levée), `test_appliquer_garde_les_autres_cles`, `test_refus_etape_service_inconnu` ; node : rendu de la décision (texte hostile littéral, coût sans euros → « prix inconnu »).
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « L'organisation qui évolue ».

### Task 17 : les lots par modèle dans l'orchestrateur

**Files:** Create `orchestrateur/lots.py` ; Modify `orchestrateur/outil.py` (`cmd_tache`, `cmd_depart`, nouvelle `cmd_lots`, `construire_releve`), `orchestrateur/depart.py`, `orchestrateur/verifier_interface.py`, `orchestrateur/consignes.md`, `orchestrateur/interface.md`, `bureau/releve.py`, `bureau/web/ui/detail.js` ; Test `tests/test_orch_lots.py`, `tests/test_orch_depart.py`, `tests/test_orch_interface.py`, `tests/test_releve.py`

**Interfaces:**
- Produces: `MAX_TACHES_LOT = 5` ; `lots.former(taches: list[dict]) -> list[dict]`. Chaque tâche en entrée : `{"id", "modele", "lieu", "role", "depend_de": [ids]}` (dans l'ordre d'origine). Rend `[{"lot": "L1", "modele", "lieu", "taches": [ids]}]`. Algorithme glouton stable : tant qu'il reste des tâches, prendre les tâches prêtes (dépendances faites ou formées dans un lot précédent) ; continuer le lot courant avec la première tâche prête de même modèle et même lieu dans l'ordre d'origine ; sinon ouvrir un lot sur la première tâche prête dans l'ordre d'origine ; une tâche de rôle `relecteur` forme toujours un lot à elle seule ; un lot s'arrête à `MAX_TACHES_LOT`. Lève `ValueError` sur un cycle ou une dépendance inconnue (message nommant les tâches).
- `outil.py lancer tache` accepte `depend_de` (liste d'ids de tâches connues) et `lot` (`{"id", "rang"}`) ; `lancer lots` `{"taches": [ids]}` → `{"lots": [...]}` sur les tâches suivies (modèle et lieu tirés de l'agent libre du rôle si la tâche n'en a pas encore) ; `lancer depart` accepte `taches: [ids]` à la place de `tache` : un seul message de départ, les briefs de chaque rôle présent, les tâches dans l'ordre du lot, et la consigne « rends compte à la fin de chaque tâche (`lancer tache`) avant de passer à la suivante ».
- Relevé version 4 : une tâche peut porter `lot` `{"id": texte, "rang": entier ≥ 1}` (facultatif, normalisé à `None`) ; le détail d'une tâche au bureau affiche « Lot L2, tâche 3 sur 4 ».
- Consignes, « Choisir l'agent et le modèle » et « Recréer un agent » : au découpage, note `depend_de` ; avant de lancer, `lancer lots` sur les tâches prêtes ; un lot = un agent, un départ (`depart` avec `taches`), enchaîné d'une traite ; « contexte neuf » vaut désormais à chaque **lot** ; la relecture croisée reste un agent neuf par relecteur.

- [ ] **Step 1 : tests** — `test_exemple_de_l_utilisateur` (a, b, d Sonnet, c Opus, sans dépendance → `[a, b, d]`, `[c]` ; avec `d` dépendant de `c` → `[a, b]`, `[c]`, `[d]`), `test_ordre_garde_sans_dependance_connue_entre_modeles` (l'ordre interne de chaque lot suit l'ordre d'origine), `test_lieu_separe_les_lots`, `test_relecture_jamais_en_lot`, `test_lot_de_cinq_au_plus`, `test_cycle_refuse`, `test_dependance_inconnue_refusee`, `test_depart_d_un_lot` (un message, deux briefs, consigne de compte rendu par tâche), `test_tache_lot_releve_v4`.
- [ ] **Step 2–4 :** échec, coder, verts (dont `test_orch_consignes`). **Step 5 :** commit « Les lots par modèle dans l'orchestrateur ».

## Étape 5 — le bureau sur le téléphone

### Task 15 : le bureau ouvert au réseau, le code d'accès, l'association

**Files:** Modify `bureau/serveur.py`, `bureau/web/index.html`, `bureau/web/ui/barre.js` ; Create `bureau/acces.py`, `bureau/web/ui/associer.js`, `bureau/web/vendor/qrcode.js` (+ sa licence) ; Test `tests/test_acces.py`, `bureau/web/tests/associer.test.js`

**Interfaces:**
- Consumes: `lire_bureau(...)["acces"]` et `installation.acces.adresse_tailscale`, `adresse_reseau_local` (tâche 14).
- Produces: `bureau/acces.py` : `Cles(chemin)` sur `~/MyIAFactory/acces.json` `{"cle": secret}` (créé au besoin, `secrets.token_urlsafe(32)`) avec `cle()`, `revoquer() -> str` (nouvelle clé), `code_association() -> str` (usage unique, 10 minutes, 8 caractères sans ambiguïté), `echanger(code) -> str | None`, `valide(cookie) -> bool` (`hmac.compare_digest`).
- `serveur.creer(...)` avec un fichier de bureau dont `acces` ouvre quelque chose : en plus de `127.0.0.1`, un **écouteur distant** par adresse trouvée (même port), qui sert le même `Bureau` ; une adresse introuvable est dite au lancement et ignorée. Le mode `--reglages` (un projet) n'ouvre jamais d'écouteur distant. Les tests simulent un écouteur distant sur `127.0.0.1` (port libre).
- Sur un écouteur distant : `Host` doit valoir `<adresse>:<port>` (sinon 403) ; `GET /associer?code=…` valide → cookie `myiafactory_acces=<clé>; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000` et redirection vers `/` ; toute autre requête sans cookie valide → 401 et une page courte « Scannez le QR code affiché sur l'ordinateur » ; un `POST` exige aussi `Origin` égal à l'adresse servie (sinon 403).
- Sur `127.0.0.1` seulement : `GET /api/acces` → `{"adresses": [{"genre": "tailscale" | "reseau_local", "url"}], "code", "expire"}` (un code neuf à chaque appel) ; `POST /api/acces/revoquer` → nouvelle clé, codes en cours annulés. Sur un écouteur distant : 404.
- Page (ordinateur) : « Associer un téléphone » dans la barre quand une adresse distante existe ; un panneau montre, par adresse, le QR code de `<url>/associer?code=<code>` (bibliothèque `qrcode-generator`, licence MIT, copiée dans `bureau/web/vendor/` comme three.js), l'adresse en clair, la mention « non chiffré » pour le réseau local, et « Révoquer les téléphones ». Le terminal affiche les adresses ouvertes (pas de QR).

- [ ] **Step 1 : tests** — `test_sans_acces_un_seul_ecouteur`, `test_distant_sans_cookie_401`, `test_associer_pose_le_cookie`, `test_code_usage_unique`, `test_code_expire`, `test_revoquer_invalide_les_cookies`, `test_host_inconnu_403`, `test_post_distant_sans_origin_403`, `test_api_acces_jamais_a_distance`, `test_reglages_un_projet_jamais_distant` ; node : le panneau d'association (adresse et mention en `textContent`, un QR par adresse).
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Le bureau ouvert au téléphone, avec un code d'accès ».

### Task 16 : la vue 3D adaptée au mobile

**Files:** Modify `bureau/web/main.js`, `bureau/web/scene/scene.js`, `bureau/web/style.css`, `bureau/web/index.html`, `bureau/web/ui/fonctionnalite.js`, `bureau/web/ui/panneaux.js` ; Create `bureau/web/logique/mobile.js`, `bureau/web/manifest.webmanifest`, `bureau/web/icone.png` ; Test `bureau/web/tests/mobile.test.js`

**Interfaces:**
- Produces: `logique/mobile.js` (pur, testable) : `estMobile(largeur, pointeurGrossier) -> bool` (vrai sous 768 px ou pointeur grossier), `zoomPincement(ecartDebut, ecartFin, zoom, min, max) -> number`, `dimensionsReduites(largeur, hauteur, coteMax = 2048) -> [l, h]`, `formatEnvoye(type) -> "image/png" | "image/jpeg"` (PNG gardé, tout le reste en JPEG), `qualitePour(octets) -> number` (pour rester sous 5 Mo).
- Sur mobile : la scène 3D reste ; toucher = le clic actuel (`pointer`), pincer = zoom borné, glisser à un doigt = déplacement borné au bâtiment ; définition plafonnée à 1,5 × et ombres coupées ; panneaux plein écran avec un bouton « Fermer » ; barre compacte ; le Kanban plein écran garde son geste. Sur ordinateur, rien ne change.
- Discussion : le champ image accepte `image/*` ; chaque image est réduite (`dimensionsReduites`) et réencodée (`formatEnvoye`, `qualitePour`) par un `canvas` avant l'envoi ; si elle dépasse encore 5 Mo, un message clair, pas d'envoi.
- `manifest.webmanifest` (nom « MyIAFactory », `display: standalone`, l'icône) lié depuis `index.html` : la page s'ajoute à l'écran d'accueil.

- [ ] **Step 1 : tests** node — `estMobile` en tableau, `zoomPincement` borné, `dimensionsReduites` (4032 × 3024 → 2048 × 1536 ; petite image inchangée), `formatEnvoye` (`image/heic`, `image/webp` → JPEG ; PNG gardé), `qualitePour`.
- [ ] **Step 2–4 :** échec, coder, verts ; vérifier dans le navigateur en vue mobile (375 × 812) et en tablette : toucher une pièce ouvre son dossier, pincer zoome, une décision du Directeur se valide, une photo s'envoie ; capture d'écran.
- [ ] **Step 5 :** commit « La vue 3D adaptée au mobile ».

## Étape 6 — les guides et la relecture

### Task 11 : les guides d'accord, relecture finale

**Files:** Modify `docs/installation.md`, `docs/orchestrateur.md`, `README.md`

- [ ] **Step 1 :** `docs/installation.md` commence par l'installation du plugin (`/plugin marketplace add maximus49000/MyIAFactory`, `/plugin install myiafactory@myiafactory`, puis `/myiafactory:installer` dans le dossier d'un projet) ; « Brancher son projet » suit la nouvelle règle de versionnement (plus de `.factory/` dans `.gitignore`) ; une section « Le bureau sur le téléphone » (Tailscale, Wi-Fi de la maison, association par QR code, révocation, ce qui n'est pas chiffré) ; `docs/orchestrateur.md` « Démarrer un projet neuf » renvoie à la commande ; README : le projet 4 et ses cases.
- [ ] **Step 2 :** relecture de tout le projet 4 contre la conception et ce plan par un relecteur indépendant **sur Opus** (jamais Fable) : exactitude, Review Focus, contre-buts 1 et 2 (sobriété des consignes, workflow proposé, lots par modèle), rien de propre à un projet ; corrections avec leurs tests.
- [ ] **Step 3 :** tous les tests verts ; commit « Projet 4 : guides et relecture ».

## Étape 7 — le vrai passage (avec l'utilisateur)

### Task 12 : installer sur un projet vide et sur un projet existant

- [ ] **Step 1 :** hors du dépôt, un dossier vide et la copie d'un petit projet existant choisi par l'utilisateur ; le plugin ajouté depuis le dépôt local (`/plugin marketplace add <chemin du dépôt>`).
- [ ] **Step 2 :** l'utilisateur lance `/myiafactory:installer` dans chacun et mène la discussion ; on note chaque écart (question inutile, workflow trop long, coût mal estimé, fichier faux).
- [ ] **Step 3 :** chaque écart générique est corrigé ici avec un test ; la première fonctionnalité démarre sur l'un des deux projets pour vérifier qu'il est prêt ; l'utilisateur associe son téléphone (Tailscale puis Wi-Fi) et y fait un geste de chaque sorte (décision du Directeur, message avec photo, déplacement d'un post-it).
- [ ] **Step 4 :** commit et push ; fin de phase.

## Étape 8 — la mise à jour du projet pilote (dépôt privé)

### Task 13 : le projet pilote rejoint le nouveau rangement

- [ ] **Step 1 :** dans le dépôt de la skill, `installation/outil.py preparer --lier <chemin de ce dépôt>` : le dossier stable pointe sur la copie de développement (un seul clone).
- [ ] **Step 2 :** dans le dépôt du projet pilote, `reparer` ; relire chaque correction ; les adaptateurs restent tels quels.
- [ ] **Step 3 :** le bureau commun suit le projet pilote ; la liste de compatibilité du projet 3 est repassée ligne par ligne ; `git grep -i` des mots interdits du projet sur le dépôt de la skill : aucun résultat.
- [ ] **Step 4 :** dans le dépôt de la skill, `README.md` et la passation : « projet 4 terminé, vérifié sur le projet pilote », sans aucun nom ; commit et push.
