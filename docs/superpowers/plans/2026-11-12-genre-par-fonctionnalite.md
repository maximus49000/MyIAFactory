# Un genre et un workflow par fonctionnalité — plan d'implémentation

> **Pour les agents qui exécutent :** sous-compétence requise : superpowers:subagent-driven-development (conseillé) ou superpowers:executing-plans, tâche par tâche. Les étapes se cochent (`- [ ]`). Le découpage en phases par modèle est dans `2026-11-12-genre-par-fonctionnalite-passation.md`.

**But :** chaque fonctionnalité porte son genre et son workflow ; le moteur classe chaque nouvelle demande, avertit quand elle n'est pas du genre du projet, propose un nouveau projet ou un workflow complet (jusqu'au livrable) à valider, recrute ce qui manque ; le bureau crée un projet et montre tous les workflows au tableau.

**Architecture :** les données d'abord (`factory.json` gagne `workflows`, le flux du projet devient facultatif, la fonctionnalité gagne `genre` et `workflow`, une étape `deplacee`), lues par un seul module `orchestrateur/workflows.py` que l'outil, le moteur et le bureau emploient ; deux jugements nouveaux (`classer_genre`, `proposer_organisation`) ; la table de règles du moteur enchaîne le parcours ; `installation/creation.py` crée un projet vide ; le bureau ajoute une route de création, deux décisions et des colonnes étiquetées par genre.

**Pile :** Python 3.12, bibliothèque standard seulement (`py -3.12`), `unittest` ; la page en JavaScript sans dépendance (`node --test`) ; `git` et `gh` seulement pour GitHub.

**Conception :** `docs/superpowers/specs/2026-11-11-genre-par-fonctionnalite-design.md` (à lire en entier avant toute tâche), avec `docs/superpowers/specs/2026-11-11-orchestrateur-procedural-design.md`, `orchestrateur/interface.md`.

## Contraintes globales

- Python 3.12, bibliothèque standard seulement. **Pendant le travail**, chaque commit ne lance que les tests concernés : `py -3.12 outils/tests.py <mots>` (par exemple `moteur orch workflows`). **La suite complète**, `py -3.12 outils/tests.py` (environ 75 s), ne tourne qu'**en fin de phase**.
- Le moteur n'écrit dans un projet **que** par `lancer <commande>` (`orchestrateur.outil.executer`).
- **Aucun appel réel** à `claude`, à `git push` ni à `gh` dans les tests : exécuteurs injectables.
- **Compatibilité** : un projet existant (genre et `flux` au niveau du projet, pas de `workflows`) marche sans changement ; ses fonctionnalités sans `genre`/`workflow` suivent le workflow principal `principal`.
- Identifiant d'une étape d'un workflow de fonctionnalité : `<id de la fonctionnalité>-<étape>` (`f2-dev`), unique dans le projet ; `cadrage` et `fait` réservés.
- **Fable** : jamais choisi par le moteur ; un agent n'est sur Fable que si sa fiche porte l'accord du Directeur (ligne `Fable : accordé par le Directeur le <date>`), pour cet agent seulement.
- **Ne jamais bloquer** (conception, section 8) : chaque échec de ce parcours a une issue qui laisse avancer et une phrase au bureau.
- Les mots interdits du projet passent avant toute écriture dans la mémoire de la skill (genre créé, leçon) ; le nom d'un projet créé au bureau est ajouté à ses mots interdits.
- Textes destinés à l'utilisateur : en français, sans jargon. Jamais un nom de projet privé dans le dépôt public.

## Points d'attention de la relecture

1. **Un projet existant, sans `workflows`, relu après la mise à jour** : relevé, tableau, moteur et départ des agents identiques à avant. (Tâche 1 : `test_projet_sans_workflows_lu_comme_avant` ; tâche 2 : `test_releve_inchange_sans_workflows`.)
2. **Deux workflows qui ont chacun une étape « Contrôle »** : deux colonnes distinctes, chacune avec son genre, et une tâche ne tombe jamais dans la colonne de l'autre. (Tâche 2 : `test_deux_controles_deux_colonnes`.)
3. **Le nom de projet saisi au bureau** vide, déjà pris, avec `..`, `/`, `:`, ou un nom réservé Windows (`CON`, `NUL`) : refusé avec un message, rien de créé à moitié. (Tâche 7 : `test_nom_refuse`, `test_echec_ne_laisse_rien`.)
4. **`gh` absent ou non connecté** quand GitHub est demandé : le projet est créé en local, le bureau dit pourquoi. (Tâche 7 : `test_github_sans_gh_projet_local`.)
5. **Le treizième projet** : refus clair, et depuis une décision l'issue « Dans ce projet » reste possible. (Tâche 7 : `test_bureau_plein_refuse` ; tâche 6 : `test_nouveau_projet_impossible_reste_ici`.)

---

## Étape 1 — les données

### Tâche 1 : workflows du projet et genre de la fonctionnalité

**Fichiers :**
- Créer : `orchestrateur/workflows.py`
- Modifier : `orchestrateur/factory.py` (clé `workflows`, `flux` facultatif, clé `description`), `orchestrateur/suivi.py` (`nouvelle_fonctionnalite` : `genre`, `workflow`), `bureau/releve.py` (`ETAPES` gagne `deplacee`), `orchestrateur/outil.py` (`cmd_fonctionnalite` accepte `genre`, `workflow`, `deplacee_vers` ; `Ctx.colonnes()`)
- Test : `tests/test_orch_workflows.py`

**Interfaces :**
- Produit (`orchestrateur/workflows.py`) :
  - `PRINCIPAL = "principal"` ;
  - `tous(f: dict) -> list[dict]` : les workflows du projet `{"id", "fonctionnalite" | None, "genre" | None, "flux"}`, dans l'ordre de création ; sans clé `workflows`, un seul : `{"id": "principal", "fonctionnalite": None, "genre": f["genre"], "flux": f["flux"]}` (rien si `flux` est vide) ;
  - `de_la_fonctionnalite(f: dict, fonc: dict | None) -> dict | None` : le workflow de `fonc["workflow"]`, sinon le principal ;
  - `genre_de(f: dict, fonc: dict | None) -> str | None` : `fonc["genre"]`, sinon le genre du projet ;
  - `ids_etapes(f: dict) -> list[str]` : toutes les étapes de tous les workflows ;
  - `colonnes(f: dict, fonctionnalites: list[dict]) -> list[dict]` : `[{"id": "cadrage", "nom": "Cadrage"}]` + les étapes des workflows dont la fonctionnalité n'est ni `terminee` ni `deplacee` (le principal toujours), chacune `{"id", "nom", "genre", "workflow"}` + `[{"id": "fait", "nom": "Fait", "terminee": True}]`.
- `factory.lire` : `workflows` (liste facultative) contrôlée comme `flux` (étapes `{id, nom, role, service}`, `id` unique **dans tout le projet**, service connu, `genre` motif `MOTIF_GENRE`) ; `flux` peut être vide ou absent (projet créé sans workflow) ; `description` facultative (texte).
- `Ctx.colonnes()` = `["cadrage"] + workflows.ids_etapes(f) + ["fait"]`.

- [x] **Étape 1 : écrire les tests** : `test_projet_sans_workflows_lu_comme_avant` (une factory actuelle : `tous` rend un seul workflow `principal`, `colonnes` identiques à l'ancien relevé) ; `test_workflow_de_la_fonctionnalite` ; `test_identifiant_en_double_entre_workflows_refuse` ; `test_projet_sans_flux_valide` ; `test_fonctionnalite_porte_genre_et_workflow` (par `lancer fonctionnalite`) ; `test_etape_deplacee` (`etape: deplacee` avec `deplacee_vers: "<nom>"`).
- [x] **Étape 2 : les lancer**, `py -3.12 outils/tests.py workflows` : échec attendu (module absent).
- [x] **Étape 3 : écrire le code** décrit ci-dessus.
- [x] **Étape 4 : relancer** `py -3.12 outils/tests.py workflows orch` : vert.
- [x] **Étape 5 : commit** « Données : workflows du projet, genre et workflow de la fonctionnalité ».

### Tâche 2 : relevé, tableau, départ et mémoire par fonctionnalité

**Fichiers :**
- Modifier : `orchestrateur/outil.py` (relevé `colonnes` par `workflows.colonnes` ; `cmd_tache` colonne par défaut = première étape du workflow de la fonctionnalité de la tâche ; `cmd_depart` et `_depart_d_un_lot` : `memoire.lire(..., workflows.genre_de(f, fonc), role)` ; `_appliquer_lecon` : genre de la fonctionnalité de la leçon), `orchestrateur/depart.py` (`_entete` : « genre : » de la fonctionnalité), `bureau/releve.py` (vérification des colonnes `genre`/`workflow` facultatifs), `installation/estimation.py` (`usages_du_genre` : usages par genre de fonctionnalité, champ `genre` de l'usage), `bureau/kpi.py` et `bureau/cout.py` (une fonctionnalité `deplacee` ne compte ni comme livrée ni dans les coûts de livraison), `bureau/etat.py`, `orchestrateur/outil.py` `cmd_usage` (note `genre` = genre de la fonctionnalité de la tâche)
- Modifier (page) : `bureau/web/scene/kanban.js`, `bureau/web/ui/kanban-plein.js`, `bureau/web/ui/fonctionnalite.js` (genre affiché sous le nom de colonne ; genre et workflow sur la page d'une fonctionnalité)
- Test : `tests/test_orch_workflows.py`, `tests/test_orch_releve*.py` existants, `bureau/web/tests/*.test.js`

**Interfaces :**
- Consomme : `workflows.colonnes`, `workflows.genre_de`, `workflows.de_la_fonctionnalite` (tâche 1).
- Produit : relevé `colonnes[i] = {"id", "nom", "genre"?, "workflow"?, "terminee"?}` ; usage noté `{..., "genre"?}`.

- [x] **Étape 1 : tests** : `test_releve_inchange_sans_workflows` ; `test_deux_controles_deux_colonnes` (deux workflows `f1-controle`, `f2-controle`, genres différents : deux colonnes, chacune son genre ; une tâche de `f2` créée sans colonne va dans `f2-…`) ; `test_colonnes_d_une_fonctionnalite_finie_cachees` ; `test_depart_donne_les_lecons_du_genre_de_la_fonctionnalite` ; `test_lecon_de_genre_va_au_genre_de_sa_fonctionnalite` ; `test_usage_porte_le_genre` ; `test_estimation_par_genre_de_fonctionnalite` (un usage ancien sans genre compte pour le genre du projet) ; `test_deplacee_ni_livree_ni_comptee` ; page : `colonne affiche son genre`.
- [x] **Étape 2 : les lancer** : échec attendu.
- [x] **Étape 3 : écrire le code.**
- [x] **Étape 4 : relancer** `py -3.12 outils/tests.py workflows orch releve estimation` et `node --test bureau/web/tests` : vert.
- [x] **Étape 5 : commit** « Relevé, départ et mémoire : le genre et le workflow de la fonctionnalité ».

## Étape 2 — les jugements

### Tâche 3 : `classer_genre` et `proposer_organisation`

**Fichiers :**
- Créer : `moteur/consignes/classer_genre.md`, `moteur/consignes/proposer_organisation.md`
- Modifier : `moteur/jugement.py` (`TYPES`, `LIBELLES`, validateurs, docstring des dossiers)
- Test : `tests/test_moteur_jugement.py` ; mesure réelle : `outils/essayer_jugements.py` (s'il existe, sinon un script d'essai dans la passation, comme en phase A de l'orchestrateur procédural)

**Interfaces :**
- Produit :
  - `TYPES["classer_genre"] = "haiku"` ; dossier `{"demande": {texte, images}, "projet": {nom, description}, "genres_du_projet": [{id, domaine, livrable, outils}], "genres_connus": [...]}` ; réponse `{"verdict": "meme"|"proche"|"autre"|"incertain", "genre": id|null, "nouveau": {"id", "description"}|null, "raison": str}` ; règles : `meme`/`proche` exigent un `genre` connu ; `autre` exige `genre` connu ou `nouveau` (id au motif `MOTIF_GENRE`) ; `nouveau.id` jamais un mot interdit (le dossier les porte en `mots_interdits`).
  - `TYPES["proposer_organisation"] = "sonnet"` ; dossier `{"demande", "genre", "projet": {nom, description}, "services", "agents": [{cle, role, modele, specialite}], "workflows_du_genre": [{id, flux}], "fonctionnalite": id, "refus": texte|null}` ; réponse `{"flux": [{"etape", "nom", "role", "service"}], "services": [{"id", "nom"}], "agents": [{"cle", "prenom"?, "role", "service", "modele", "justification", "fable_suggere"?: bool, "texte"}], "briefs": {role: texte}, "livrable": texte, "environnement": [{"outil", "pour", "executables": [str], "installation": texte}], "outils_installation": [règles d'outils, par exemple "Bash(winget:*)"]}` ; règles : `modele` dans Haiku/Sonnet/Opus (jamais Fable) ; chaque rôle du flux a un agent existant ou proposé ; la **dernière étape** produit ou remet le livrable (`livrable` non vide, et le nom de la dernière étape le dit) ; services du flux connus ou proposés.
- Les consignes portent les décisions de l'utilisateur : *proche* = mêmes savoir-faire, mêmes outils, même sorte de livrable ; **dans le doute `incertain`, jamais élargir un genre** ; le workflow va de la demande au livrable remis (fabrication, qualité dès que c'est logique, livraison) ; reprendre tel quel le workflow le plus récent du même genre s'il convient ; le modèle selon la complexité (Haiku mécanique, Sonnet création et code courant, Opus conception difficile) ; Fable seulement en `fable_suggere`.

- [x] **Étape 1 : tests des validateurs** : `test_proposer_organisation_environnement_valide` (chaque outil a `executables` non vide et `installation`), `test_classer_genre_valide`, `test_classer_genre_nouveau_mot_interdit_refuse`, `test_proposer_organisation_sans_livraison_refuse`, `test_proposer_organisation_fable_refuse`, `test_proposer_organisation_role_sans_agent_refuse`.
- [x] **Étape 2 : les lancer** : échec attendu.
- [x] **Étape 3 : écrire validateurs et consignes.**
- [x] **Étape 4 : relancer** `py -3.12 outils/tests.py jugement` : vert.
- [x] **Étape 5 : essai réel, avec l'accord de l'utilisateur** (quelques centimes) : les deux jugements sur trois demandes synthétiques (badge pour le chat YouTube → `proche` ; casse-briques Android → `autre`, workflow avec qualité et livraison `.apk` ; demande floue → `incertain`) ; noter dans la passation validité au premier essai, tokens, coût.
- [x] **Étape 6 : commit** « Jugements : classer le genre, proposer le workflow ».

## Étape 3 — le moteur

### Tâche 4 : le moteur suit le workflow de la fonctionnalité

**Fichiers :**
- Modifier : `moteur/regles.py` (`_production(projet, fid)`, `_colonne_du_role(projet, role, fid)`, `_role_cadrage(projet, fid)`, `_tache_de_flux`, dossiers de `decouper`, `ecrire_methode`, `_methodes_validees`, lots)
- Test : `tests/test_moteur_regles.py`

**Interfaces :**
- Consomme : `workflows.de_la_fonctionnalite` (tâche 1).
- Produit : `_production(projet, fid=None) -> list[dict]` (le workflow de la fonctionnalité `fid`, sans les étapes `relecteur`) ; idem `_colonne_du_role`, `_role_cadrage` avec `fid`.

- [ ] **Étape 1 : tests** : `test_serie_suit_le_workflow_de_la_fonctionnalite` (deux fonctionnalités, deux workflows : chaque élément passe par les étapes de sa fonctionnalité) ; `test_cadrage_par_le_role_du_workflow` ; les tests existants inchangés (workflow principal).
- [ ] **Étape 2 : les lancer** : échec attendu.
- [ ] **Étape 3 : écrire le code.**
- [ ] **Étape 4 : relancer** `py -3.12 outils/tests.py moteur banc` : vert.
- [ ] **Étape 5 : commit** « Moteur : chaque fonctionnalité suit son workflow ».

### Tâche 5 : Fable sur accord du Directeur

**Fichiers :**
- Modifier : `orchestrateur/fiches.py` (en-tête `Fable` : « accordé par le Directeur le <date> »), `orchestrateur/outil.py` (`MODELES_INTERDITS` / `_interdit` : Fable permis sur une fiche qui porte l'accord), `installation/proposition.py` (`_modele`), `moteur/appel.py`, `moteur/agents.py` (Fable accepté pour un agent dont la fiche porte l'accord ; jamais pour un jugement), `bureau/releve.py`
- Test : `tests/test_moteur_agents.py`, `tests/test_orch_*.py` concernés

**Interfaces :**
- Produit : `fiches.fable_accorde(fiche: dict) -> bool` ; `agents.executer_agent` lance Fable seulement si `fable_accorde(agent)`.

- [ ] **Étape 1 : tests** : `test_fable_refuse_sans_accord`, `test_fable_permis_avec_accord_pour_cet_agent_seulement`, `test_jugement_jamais_fable`, `test_montee_ne_va_jamais_a_fable`.
- [ ] **Étapes 2 à 4 : échec, code, vert** (`py -3.12 outils/tests.py moteur orch installation`).
- [ ] **Étape 5 : commit** « Fable : seulement sur accord du Directeur, agent par agent ».

### Tâche 6 : le parcours d'une nouvelle fonctionnalité

**Fichiers :**
- Modifier : `moteur/regles.py` (`_sur_fonctionnalite`, nouvelles fonctions, `_sur_organisation`, `appliquer_jugement` pour les deux types), `orchestrateur/outil.py` (décision `genre_fonctionnalite` : `cmd_decision` ; décision `organisation` étendue de `workflow`, `fonctionnalite`, `fable_suggere` ; `cmd_organisation` ajoute le workflow à `workflows`, rattache la fonctionnalité, recrute avec l'accord Fable coché), `installation/mise_en_place.py` (`ecrire_organisation(..., workflow=None)` ajoute un workflow au lieu de réécrire `flux`), `bureau/demandes.py` (réponses aux deux décisions), `orchestrateur/interface.md`
- Test : `tests/test_moteur_regles.py`, `tests/test_moteur_boucle.py`, `tests/test_orch_*.py`

**Interfaces :**
- Consomme : jugements de la tâche 3 ; `workflows` (tâche 1) ; `fiches.fable_accorde` (tâche 5).
- Produit :
  - demande du bureau `{"type": "genre_fonctionnalite", "decision", "fonctionnalite", "choix": "ici"|"meme"|"nouveau_projet", "genre"?, "description"?, "projet_cree"?: <chemin des réglages du nouveau projet>}` ;
  - demande `{"type": "organisation", "decision", "verdict": "accepter"|"refuser", "texte"?, "fable"?: [clés d'agents]}` ;
  - décision `genre_fonctionnalite` `{genre, portee: <fid>, texte, propose, nouveau?, incertain: bool, genres_connus}` ;
  - décision `organisation` existante + `{"fonctionnalite", "workflow": {"id", "genre", "flux"}, "agents"[i].fable_suggere?, "agents"[i].justification}`.
- Parcours (conception, section 5) : `classer_genre` → `meme`/`proche` : genre noté, `proposer_organisation` → décision `organisation` ; `autre`/`incertain` : décision `genre_fonctionnalite` → `ici` : `proposer_organisation` ; `meme` : genre du projet, `proposer_organisation` ; `nouveau_projet` : la demande d'origine (texte, images) recréée par `lancer actions` dans le projet `projet_cree` avec son `genre`, la fonctionnalité d'origine passe `deplacee` avec une ligne « Partie dans le projet <nom> ». À l'acceptation : `lancer organisation` (`appliquer`), puis cadrage. Au refus : avec texte, `proposer_organisation` relancé avec `refus` ; sans texte, conception section 5 étape 4.
- Projet sans genre (créé au bureau) : au premier passage, `classer_genre` sur `description`, décision `confirmer_genre` existante.
- Issues de secours (conception, section 8) : `classer_genre` raté → genre du projet, cadrage, une phrase ; `proposer_organisation` raté → question au Directeur avec l'issue « continuer avec le workflow actuel ».

- [ ] **Étape 1 : tests** (un par ligne du parcours) : `test_demande_du_meme_genre_propose_son_workflow`, `test_demande_proche_rattachee`, `test_demande_d_un_autre_genre_avertit`, `test_incertain_demande_a_l_utilisateur`, `test_choix_ici_propose_le_workflow`, `test_choix_nouveau_projet_deplace_la_demande`, `test_nouveau_projet_impossible_reste_ici`, `test_organisation_acceptee_recrute_et_lance_le_cadrage`, `test_agent_existant_reutilise`, `test_refus_avec_texte_nouvelle_proposition`, `test_refus_sans_texte_reprend_le_workflow_du_genre`, `test_projet_sans_workflow_refus_reste_pose`, `test_classer_rate_continue_avec_le_genre_du_projet`, `test_proposer_rate_question_au_directeur`, `test_fable_coche_recrute_sur_fable`, `test_projet_sans_genre_confirme_d_apres_la_description`.
- [ ] **Étape 2 : les lancer** : échec attendu.
- [ ] **Étape 3 : écrire le code.**
- [ ] **Étape 4 : relancer** `py -3.12 outils/tests.py moteur orch demandes banc` : vert.
- [ ] **Étape 5 : commit** « Moteur : classer chaque demande, proposer son workflow, recruter ».

### Tâche 10 : l'environnement du poste

**Fichiers :**
- Créer : `moteur/environnement.py`
- Modifier : `moteur/regles.py` (la proposition `organisation` porte l'environnement vérifié ; à l'acceptation, tâche « Mise en place de l'environnement » en tête du workflow, cadrage après sa fin ; décision d'échec), `orchestrateur/outil.py` (réglage `environnement` du projet ; `depart` : « Outils du poste : … »), `installation/mise_en_place.py` (`ecrire_organisation` : fiche de l'agent d'environnement avec ses `outils_installation`)
- Test : `tests/test_moteur_environnement.py`, `tests/test_moteur_regles.py`

**Interfaces :**
- Produit : `verifier(outils: list[dict], *, which=shutil.which, executer=..., env=os.environ) -> list[dict]` : chaque outil + `{"etat": "en_place"|"a_installer", "chemin"?, "version"?}` ; exécutables cherchés par `which` puis sous `JAVA_HOME`, `ANDROID_HOME`, `ANDROID_SDK_ROOT` ; version lue avec la première option de `("--version", "-version", "version")` qui répond (délai 10 s) ; **aucune commande venue de l'IA n'est exécutée**.
- Consomme : `environnement` de `proposer_organisation` (tâche 3) ; parcours de la tâche 6.

- [ ] **Étape 1 : tests** : `test_outil_present_en_place_avec_version`, `test_outil_absent_a_installer`, `test_android_home_trouve`, `test_jamais_de_commande_de_l_ia` (un exécutable nommé `rm -rf` ou avec espace/`;`/`&` est refusé sans être lancé), `test_tout_en_place_pas_de_tache_d_installation`, `test_acceptation_cree_la_tache_d_environnement_avant_le_cadrage`, `test_installation_ratee_devient_decision`, `test_c_est_fait_revérifie`, `test_continuer_sans_laisse_avancer`, `test_environnement_note_dans_les_reglages_et_au_depart`.
- [ ] **Étapes 2 à 4 : échec, code, vert** (`py -3.12 outils/tests.py moteur environnement orch`).
- [ ] **Étape 5 : commit** « Moteur : vérifier et installer l'environnement du poste ».

## Étape 4 — créer un projet, le bureau

### Tâche 7 : créer un projet vide

**Fichiers :**
- Créer : `installation/creation.py`
- Modifier : `installation/mise_en_place.py` (factoriser l'écriture de l'arborescence de `_ecrire_configuration` pour un projet sans organisation), `installation/outil.py` (commande `creer`)
- Test : `tests/test_installation_creation.py`

**Interfaces :**
- Produit : `creer_projet(parent: Path, nom: str, *, origine: Path | None, mots_interdits: list[str], facturation: bool, github: bool, description: str | None, genre: str | None, bureau_json: Path, git=..., gh=...) -> {"reglages": Path, "github": "fait"|"non demandé"|<raison>}` ; lève `Echec(message)` ; réglages repris de `origine` (charge, modèle de l'orchestrateur, agents locaux, couche du moteur, consignes du projet) ; `nom` ajouté aux `mots_interdits` ; pas de `flux` ; `regler_gitignore`, `inscrire`.

- [ ] **Étape 1 : tests** : `test_cree_l_arborescence_complete` (mêmes dossiers et fichiers que `appliquer`, sans fiche ni flux) ; `test_reglages_repris_de_l_origine` ; `test_nom_ajoute_aux_mots_interdits` ; `test_nom_refuse` (vide, existant, `..`, `/`, `:`, `CON`, `NUL`) ; `test_parent_absent_ou_dans_la_skill_refuse` ; `test_echec_ne_laisse_rien` ; `test_bureau_plein_refuse` ; `test_github_fait` (git et gh simulés : `git init`, premier commit, `gh repo create <nom> --private --source . --push`) ; `test_github_sans_gh_projet_local`.
- [ ] **Étapes 2 à 4 : échec, code, vert** (`py -3.12 outils/tests.py installation creation`).
- [ ] **Étape 5 : commit** « Installation : créer un projet vide depuis le bureau ».

### Tâche 8 : le bureau

**Fichiers :**
- Modifier : `bureau/serveur.py` (route `POST /api/projets/creer` : appelle `creation.creer_projet`, puis, si `decision` est donné, dépose la demande `genre_fonctionnalite` `nouveau_projet` dans le projet d'origine ; `GET /api/projets` ajoute `parents` suggérés), `bureau/web/ui/barre.js` (entrée « Nouveau projet… »), `bureau/web/ui/decisions.js` (décision `genre_fonctionnalite` ; décision `organisation` : workflow, agents avec modèle et justification, services, coût, case Fable par agent, environnement « déjà en place » / « à installer » ; décision d'échec d'installation : « C'est fait », « Continuer sans »), créer `bureau/web/ui/creation.js` (formulaire : répertoire parent avec suggestions, nom, mots interdits et facturation pré-remplis, GitHub, description si pas de demande d'origine ; « Le genre vous sera proposé dans un instant »), `bureau/web/main.js` (après une création, le bureau bascule sur le nouveau projet : choix gardé dans `localStorage` comme aujourd'hui)
- Test : `tests/test_bureau_serveur*.py`, `bureau/web/tests/*.test.js`

**Interfaces :**
- Consomme : `creation.creer_projet` (tâche 7) ; demandes de la tâche 6.
- Produit : `POST /api/projets/creer` `{parent, nom, mots_interdits, facturation, github, description?, origine: <id projet>, decision?, fonctionnalite?}` → `{ok, projet: <id>, github, message}` ou `{erreur}` (code d'accès exigé comme les autres routes d'écriture).

- [ ] **Étape 1 : tests** : `test_creer_projet_route` ; `test_creer_projet_depuis_une_decision_depose_la_demande` ; `test_creer_projet_erreur_lisible` ; `test_creer_exige_le_code_d_acces` ; page : `liste propose Nouveau projet`, `decision genre_fonctionnalite trois issues`, `organisation montre la case Fable seulement si suggeree`, `apres creation bascule sur le nouveau projet`, `organisation montre l environnement`.
- [ ] **Étapes 2 à 4 : échec, code, vert** (`py -3.12 outils/tests.py bureau serveur demandes` et `node --test bureau/web/tests`).
- [ ] **Étape 5 : commit** « Bureau : créer un projet, choisir le genre d'une demande, valider son workflow ».

## Étape 5 — la vérification (avec l'utilisateur)

### Tâche 9 : banc et essai réel

**Fichiers :**
- Modifier : `banc/construire.py`, `banc/jouer.py` (gestes nouveaux : accepter l'organisation proposée ; la demande de l'essai est du genre du projet), `docs/superpowers/plans/2026-11-12-genre-par-fonctionnalite-passation.md`

- [ ] **Étape 1 : banc moteur** sur l'essai de référence (`py -3.12 -m banc moteur …`, chemins donnés par l'utilisateur, hors dépôt) : orchestration ≤ 0,10 € avec les deux appels nouveaux ; sinon resserrer `proposer_organisation` (au plus 3 tours notés).
- [ ] **Étape 2 : essai au bureau, avec l'accord de l'utilisateur** : relancer bureau et moteur ; une demande d'un autre genre (le casse-briques Android) → avertissement, « Nouveau projet », formulaire, projet créé et listé, workflow proposé avec qualité et livraison `.apk`, recrutement, cadrage ; puis « Nouveau projet… » depuis la liste avec une description ; noter ce qui accroche.
- [ ] **Étape 3 : suite complète** `py -3.12 outils/tests.py`, bilan dans la passation, commit et push.
