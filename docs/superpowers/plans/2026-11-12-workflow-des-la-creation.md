# Le workflow défini dès la création d'un projet au bureau — plan d'implémentation

> **Pour les agents qui exécutent :** sous-compétence requise : superpowers:subagent-driven-development (conseillé) ou superpowers:executing-plans, tâche par tâche. Les étapes se cochent (`- [ ]`). Le découpage en phases par modèle est dans `2026-11-12-workflow-des-la-creation-passation.md`.

**But :** « Nouveau projet… » se fait en deux fenêtres (informations générales, puis échange avec le chef) ; le chef pose ses questions (4 tours au plus), propose un workflow de genre expliqué, avec des étapes de validation du Directeur placées où l'utilisateur le veut ; après validation seulement, le projet est créé avec son organisation, et toute demande du genre du projet reprend ce workflow sans nouvelle proposition.

**Architecture :** une nouvelle sorte d'étape de flux (`{"id", "nom", "validation": true}`) lue par `orchestrateur/workflows.py` et respectée par la factory, l'installation, l'estimation, le moteur (la série s'arrête et pose une décision `valider_etape`) et la page ; un jugement nouveau `definir_workflow` (Sonnet) qui mène l'échange, appelé par le **bureau** (pas par le moteur : le projet n'existe pas encore) ; un brouillon d'échange dans `~/MyIAFactory/creations/` ; `creation.creer_projet` écrit l'organisation validée dans la même transaction que la configuration ; le moteur reprend le workflow de création (`w-<genre>`) pour une demande classée `meme`.

**Pile :** Python 3.12, bibliothèque standard seulement (`py -3.12`), `unittest` ; la page en JavaScript sans dépendance (`node --test`).

**Conception :** `docs/superpowers/specs/2026-11-12-workflow-des-la-creation-design.md` (à lire en entier avant toute tâche, **section 5 bis comprise** : elle tranche les choix techniques), avec `docs/superpowers/specs/2026-11-11-genre-par-fonctionnalite-design.md` (toujours valable), `orchestrateur/interface.md` et les notes de `2026-11-12-genre-par-fonctionnalite-passation.md` (formats exacts des décisions et des jugements actuels).

## Contraintes globales

- Python 3.12, bibliothèque standard seulement. **Pendant le travail**, chaque commit ne lance que les tests concernés : `py -3.12 outils/tests.py <mots>` (par exemple `moteur orch workflows`). **La suite complète**, `py -3.12 outils/tests.py` (environ 75 s), ne tourne qu'**en fin de phase**.
- Le moteur n'écrit dans un projet **que** par `lancer <commande>` (`orchestrateur.outil.executer`). Le bureau, pour un projet qui existe, aussi (`outil.executer(<factory>, ["lancer", …])`).
- **Aucun appel réel** à `claude`, à l'API, à `git push` ni à `gh` dans les tests : `appeler`, `git`, `gh`, `verifier_environnement` sont injectables partout.
- **Compatibilité** : un projet existant (sans workflow de création, sans étape de validation) se comporte exactement comme avant ; le banc gratuit (`py -3.12 outils/tests.py banc`) ne bouge pas.
- Étape de validation : `{"id", "nom", "validation": true}`, sans `role` ni `service` ; **interdite en première étape, en dernière étape** (la dernière remet le livrable) **et deux fois de suite** ; ignorée par les validateurs de rôles, l'estimation et le recrutement.
- Workflow de création : `{"id": "w-<genre>", "fonctionnalite": null, "genre": <genre>, "flux": [...]}` dans `workflows`, étapes sans préfixe ; ses étapes doivent tenir dans `MOTIF_ID` une fois préfixées par `f999-` (une copie `w-<fid>` les préfixe par `<fid>-`).
- Échange : jugement `definir_workflow`, modèle **Sonnet** ; **au plus 4 tours de questions** ; au 5ᵉ appel la consigne et la validation exigent une proposition ; une correction après proposition est un appel de plus, hors des 4 tours.
- Le brouillon ne contient **aucune clé** ; il vit dans `~/MyIAFactory/creations/`, jamais dans un projet ni dans le dépôt ; purge automatique après **30 jours**.
- Tout échec **avant l'inscription au bureau** n'écrit rien (ni dossier, ni bureau changé) ; GitHub vient après, et son échec ne défait rien.
- **Fable** : jamais choisi ; seulement `fable_suggere`, accordé agent par agent par le Directeur à la validation.
- Mots interdits : le nom du projet en fait partie **dès la fenêtre 1** (genre nouveau, descriptions).
- Textes destinés à l'utilisateur : en français, sans jargon. Jamais un nom de projet privé dans le dépôt public.

## Points d'attention de la relecture

1. **Deux clics sur « Envoyer », ou deux appareils sur le même brouillon** : un seul appel de jugement part ; le second reçoit « un tour est déjà en cours » et rien n'est compté deux fois. (Tâche 10 : `test_tour_deja_en_cours_refuse`.)
2. **Le nom ou le dossier devenu invalide entre la fenêtre 1 et la validation** (un projet du même nom créé entre-temps, dossier parent supprimé, bureau plein) : rien n'est créé, l'utilisateur revient à la fenêtre 1 et l'échange est gardé. (Tâche 9 : `test_nom_pris_entre_temps_retour_infos` ; tâche 10 : `test_valider_renvoie_aux_infos`.)
3. **Un tour dont le jugement rate deux fois** (réseau, réponse invalide) : un message lisible dans l'échange, le tour ne compte pas dans les 4, son coût est compté, l'utilisateur peut renvoyer. (Tâche 8 : `test_tour_rate_ne_compte_pas`.)
4. **« Renvoyer » sans remarque** à une étape de validation : refusé au bureau et par le moteur, l'élément reste en attente. (Tâche 2 : `test_renvoyer_sans_remarque_refuse`.)
5. **Le moteur relancé pendant qu'un élément attend une validation** (sa mémoire `etat["elements"]` est perdue) : la réponse du Directeur fait quand même avancer l'élément. (Tâche 2 : `test_validation_apres_redemarrage`.)

---

## Étape 1 — l'étape de validation du Directeur

### Tâche 1 : les données (étape de validation, workflow de genre)

**Fichiers :**
- Modifier : `orchestrateur/workflows.py`, `orchestrateur/factory.py` (`_controler_flux`), `installation/proposition.py` (`verifier_organisation`), `installation/estimation.py` (`estimer`), `installation/mise_en_place.py` (`ecrire_organisation`, `_ecrire_configuration` : écrire une étape par `workflows.etape_ecrite`)
- Test : `tests/test_orch_workflows.py`, `tests/test_orch_factory.py`, `tests/test_inst_proposition.py`, `tests/test_inst_estimation.py`, `tests/test_inst_mise_en_place.py`

**Interfaces :**
- Produit (`orchestrateur/workflows.py`) :
  - `CLE_VALIDATION = "validation"` ; `est_validation(etape: dict) -> bool` (`etape.get("validation") is True`) ;
  - `etape_ecrite(e: dict) -> dict` : `{id, nom, validation: True}` pour une étape de validation, sinon `{id, nom, role, service}` (ce que la factory garde) ;
  - `etapes_d_agent(flux: list) -> list` : les étapes sans les validations ;
  - `de_creation(f: dict, genre: str | None = None) -> dict | None` : le workflow de genre du projet (`fonctionnalite` nulle, `id` ≠ `principal`, `genre` = `genre` ou, à défaut, `f["genre"]`) ;
  - `copie_pour(w: dict, fid: str) -> dict` : `{"id": f"w-{fid}", "fonctionnalite": fid, "genre": w["genre"], "flux": [étapes avec id <fid>-<id>]}` ;
  - `colonnes(f, fonctionnalites)` : **les workflows de genre (`fonctionnalite` nulle, hors `principal`) n'ont pas de colonnes** (leurs copies en ont) ; une colonne d'étape de validation porte `"validation": True`.
- `factory.lire` : une étape de validation est valide sans `role` ni `service` ; refus « une étape de validation ne peut pas être la première », « … la dernière », « … deux étapes de validation de suite ».
- `proposition.verifier_organisation` et `estimation.estimer` ignorent les étapes de validation (aucun rôle à pourvoir, aucun coût).

- [x] **Étape 1 : tests** : `test_etape_de_validation_lue` ; `test_validation_premiere_derniere_ou_double_refusee` (factory) ; `test_workflow_de_creation_trouve` (`de_creation`) ; `test_copie_pour_prefixe_les_etapes` (validation gardée) ; `test_workflow_de_genre_sans_colonnes` (sa copie en a, la colonne de validation porte `validation`) ; `test_organisation_avec_validation_valide` (proposition) ; `test_estimation_ignore_la_validation` (même fourchette avec ou sans) ; `test_ecrire_organisation_garde_la_validation`.
- [x] **Étape 2 : les lancer**, `py -3.12 outils/tests.py workflows orch_factory inst_proposition inst_estimation inst_mise` : échec attendu.
- [x] **Étape 3 : écrire le code** décrit ci-dessus.
- [x] **Étape 4 : relancer** les mêmes et `py -3.12 outils/tests.py orch banc` : vert.
- [x] **Étape 5 : commit** « Données : étape de validation du Directeur, workflow de genre ».

### Tâche 2 : le moteur arrête l'élément à une étape de validation

**Fichiers :**
- Modifier : `moteur/regles.py` (`_production`, `_role_production`, `_colonne_du_role`, `_etape_de_relecture`, dossiers de `decouper`/`ecrire_methode` sans validations, `_apres_flux`, `_tache_de_flux`, `_avancer_serie`, nouvelle `_sur_valider_etape` dans `_SUR`), `orchestrateur/outil.py` (`cmd_decision` : décision de projet `valider_etape`), `bureau/releve.py` (`DECISIONS_PROJET` + champs), `bureau/demandes.py` (demande `valider_etape`), `orchestrateur/interface.md`, `orchestrateur/consignes.md`, `docs/releve.md`
- Test : `tests/test_moteur_regles.py`, `tests/test_orch_outil*.py` concernés, `tests/test_releve.py`, `tests/test_demandes.py`

**Interfaces :**
- Consomme : `workflows.est_validation`, `workflows.etapes_d_agent` (tâche 1).
- Produit :
  - `regles.GENRE_VALIDATION = "valider_etape"`, `regles.ETAPES_DE_VALIDATION = "validation:"`, `regles.VALIDER = "valider"`, `regles.RENVOYER = "renvoyer"` ;
  - quand un élément arrive à une étape de validation (`_tache_de_flux`) : une tâche `Validation du Directeur : <élément>` (étape `validation:<id>`, colonne = l'étape, sans rôle, jamais lancée par `_attente`), la phase de l'élément vaut `validation`, et une décision de projet `{"genre": "valider_etape", "texte", "fonctionnalite", "element": {"id", "nom"}, "etape": <id de l'étape>, "tache": <id de la tâche de validation>, "compte_rendu": <message de l'étape précédente, 2000 caractères au plus>, "fichiers": [{"chemin", "titre"}]}` (les `fichiers` du rapport précédent pour cet élément ; `_apres_flux` garde ce rapport dans `v["dernier_rapport"]`) ;
  - demande du bureau `{"type": "valider_etape", "decision", "verdict": "valider" | "renvoyer", "texte"?}` (`texte` obligatoire avec `renvoyer`) ;
  - `valider` : tâche de validation en `fait`, l'élément passe à l'étape suivante ; `renvoyer` : tâche de validation en `fait` (journal « Renvoyé : <remarque> »), l'élément refait l'étape précédente avec au journal `Remarque du Directeur : <texte>`, puis revient à la validation ; décision levée dans les deux cas ;
  - une phase `validation` compte parmi les deux éléments en cours (`ELEMENTS_EN_COURS_MAX`) ;
  - si l'élément n'est plus dans `etat["elements"]` (moteur relancé), il est reconstruit depuis la décision (`element`, rang de `etape` dans la production) ;
  - `_proposer` (workflows antérieurs donnés au jugement) et `_apres_proposer_organisation` (étapes préfixées `<fid>-`) gardent une étape de validation telle quelle, par `workflows.etape_ecrite` (plus de `x["role"]` sur une étape qui n'en a pas).

- [x] **Étape 1 : tests** : `test_element_s_arrete_a_la_validation` (tâche de validation, décision posée avec compte rendu et fichiers, aucun agent lancé) ; `test_valider_passe_a_l_etape_suivante` ; `test_renvoyer_refait_l_etape_precedente_avec_la_remarque` (puis revient à la validation) ; `test_renvoyer_sans_remarque_refuse` (moteur et `bureau/demandes.py`) ; `test_validation_apres_redemarrage` ; `test_validation_compte_parmi_les_elements_en_cours` ; `test_relecture_sans_relecteur_ignore_la_validation` ; `test_releve_decision_valider_etape` ; `test_proposition_avec_validation_prefixee` (décision `organisation` d'une fonctionnalité dont le workflow a une validation, acceptée puis suivie) ; les tests existants inchangés.
- [x] **Étape 2 : les lancer** : échec attendu.
- [x] **Étape 3 : écrire le code.**
- [x] **Étape 4 : relancer** `py -3.12 outils/tests.py moteur orch releve demandes banc` : vert.
- [x] **Étape 5 : commit** « Moteur : l'élément attend la validation du Directeur ».

### Tâche 3 : la page (décision de validation, colonnes, workflow)

**Fichiers :**
- Modifier : `bureau/web/ui/decisions.js` (décision `valider_etape` : élément, étape, compte rendu, fichiers — images par `/api/image?chemin=`, les autres en titre et chemin —, « Valider », « Renvoyer avec une remarque » avec texte obligatoire), `bureau/web/ui/kanban-plein.js` et `bureau/web/scene/kanban.js` (colonne `validation` : mention « Validation du Directeur »), `bureau/web/ui/organisation.js` (une étape de validation affichée « (validation du Directeur) », sans rôle)
- Test : `bureau/web/tests/decisions.test.js`, `bureau/web/tests/kanban-plein.test.js`, `bureau/web/tests/organisation.test.js`

**Interfaces :**
- Consomme : décision et demande `valider_etape` (tâche 2), colonne `validation` (tâche 1).
- Produit : `corpsValiderEtape(decision, verdict, texte) -> objet | null` (pure, exportée de `decisions.js` ; `null` si `renvoyer` sans texte).

- [x] **Étape 1 : tests** : `valider_etape montre le compte rendu et les fichiers` ; `renvoyer exige une remarque` ; `colonne de validation nommee` ; `workflow montre l etape de validation`.
- [x] **Étapes 2 à 4 : échec, code, vert** (`node --test bureau/web/tests`).
- [x] **Étape 5 : commit** « Bureau : valider ou renvoyer un élément ».

## Étape 2 — le jugement de l'échange

### Tâche 4 : `definir_workflow`, et les validations dans `proposer_organisation`

**Fichiers :**
- Créer : `moteur/consignes/definir_workflow.md`
- Modifier : `moteur/jugement.py` (`TYPES`, `LIBELLES`, `_VALIDEURS_AVEC_DOSSIER`, docstring des dossiers ; `_valider_proposer_organisation` accepte les étapes de validation et `environnement[i].version_min`), `moteur/consignes/proposer_organisation.md` (étapes de validation : quand le Directeur les demande, ou quand la demande le dit), `tests/test_orch_consignes.py` ou le test des consignes concerné si la nouvelle consigne doit nommer `fable_suggere`
- Test : `tests/test_moteur_jugement.py`

**Interfaces :**
- Produit :
  - `TYPES["definir_workflow"] = "sonnet"`, `LIBELLES["definir_workflow"] = "définir le workflow du projet"`, `TOURS_MAX_DEFINITION = 4`, `QUESTIONS_PAR_TOUR_MAX = 5`, `CHOIX_PAR_QUESTION_MAX = 6` ;
  - dossier : `{"projet": {"nom", "description", "facturation", "github"}, "genres_connus": [{id, domaine, livrable, outils}], "mots_interdits": [...], "services": [{id, nom}] (la facturation si elle est demandée), "echange": [{"auteur": "chef", "message", "questions": [...]} | {"auteur": "utilisateur", "reponses": [{"question", "texte"}]}], "tours_de_questions": int, "tours_max": 4, "proposer_maintenant": bool, "proposition_precedente": objet | null, "correction": texte | null}` ;
  - réponse questions : `{"type": "questions", "message": str, "questions": [{"id", "texte", "choix": [str]}]}` (1 à 5 questions, ids uniques, `choix` de 0 à 6 textes courts) ; **refusée** si `proposer_maintenant` est vrai, si `tours_de_questions` ≥ 4 ou si `correction` est donnée ;
  - réponse proposition : `{"type": "proposition", "message": str, "genre": id connu | null, "nouveau": {"id", "description"} | null, "flux": [{"etape", "nom", "role", "service", "raison"} | {"etape", "nom", "validation": true, "raison"}], "services", "agents", "briefs", "livrable", "environnement", "outils_installation"}` ; règles : `genre` ou `nouveau`, pas les deux (mêmes règles que `classer_genre` pour `nouveau` : motif, inconnu, sans mot interdit) ; chaque étape a une `raison` d'une ligne ; le reste validé par `_valider_proposer_organisation` avec `agents: []` et `fonctionnalite: "f999"` (les étapes tiennent une fois préfixées) ;
  - étapes de validation (les deux jugements) : ni première, ni dernière, ni deux de suite ;
  - `environnement[i].version_min` facultatif : texte de 1 à 20 caractères, chiffres et points (`"17"`, `"8.7"`).
- La consigne porte les décisions de l'utilisateur : ne jamais reposer ce que la description ou une réponse dit déjà ; chercher le besoin, les livrables et leur forme, les validations voulues, l'exigence de qualité et de tests, les zones d'ombre qui changent le workflow ; s'arrêter dès qu'on en sait assez ; proposer des `choix` quand les réponses probables sont peu nombreuses ; workflow complet jusqu'au livrable remis ; modèle selon la complexité ; Fable seulement en `fable_suggere` ; textes courts (coût).

- [x] **Étape 1 : tests des validateurs** : `test_definir_workflow_questions_valides` ; `test_definir_workflow_trop_de_questions_refuse` ; `test_cinquieme_appel_exige_une_proposition` ; `test_correction_exige_une_proposition` ; `test_definir_workflow_proposition_valide` (avec une validation avant la livraison) ; `test_definir_workflow_genre_nouveau_mot_interdit_refuse` (le nom du projet) ; `test_etape_sans_raison_refusee` ; `test_validation_premiere_ou_double_refusee` (les deux jugements) ; `test_version_min_lue`.
- [x] **Étape 2 : les lancer** : échec attendu.
- [x] **Étape 3 : écrire validateurs et consignes.**
- [x] **Étape 4 : relancer** `py -3.12 outils/tests.py jugement consignes` : vert.
- [x] **Étape 5 : essai réel, avec l'accord de l'utilisateur** (quelques centimes) : un échange complet joué par un script hors dépôt (comme en phase B du chantier précédent), projet synthétique « jeu Android » avec une validation voulue avant la livraison : questions utiles et non redondantes, proposition valide, tokens et coût de chaque appel notés dans la passation ; **cible : moins de 0,10 € l'échange complet** ; au plus 3 tours de réglage de la consigne.
- [x] **Étape 6 : commit** « Jugement : définir le workflow d'un projet avec le chef ».

## Étape 3 — le moteur après la création

### Tâche 5 : une demande du genre du projet reprend le workflow de création

**Fichiers :**
- Modifier : `orchestrateur/outil.py` (`cmd_organisation` : action `reprendre`), `moteur/regles.py` (`_apres_classer_genre` verdict `meme`, `_sur_fonctionnalite` avec `genre` du projet, `_reprendre_un_workflow`, `_classer_rate`), `orchestrateur/interface.md`
- Test : `tests/test_moteur_regles.py`, `tests/test_moteur_parcours.py`, `tests/test_orch_organisation.py`

**Interfaces :**
- Consomme : `workflows.de_creation`, `workflows.copie_pour` (tâche 1).
- Produit : `lancer organisation {"action": "reprendre", "fonctionnalite": <fid>, "workflow": <id du workflow de genre>}` → copie `w-<fid>` ajoutée par `mise_en_place.ecrire_organisation` (services inchangés, aucun agent, aucun brief), la fonctionnalité prend `genre` et `workflow` ; rend `{"ok": True, "workflow": "w-<fid>"}` ; refus si le workflow n'est pas un workflow de genre du projet ou si la fonctionnalité a déjà un workflow.
- Parcours : `classer_genre` → `meme` **et** `de_creation(fac)` existe → `reprendre`, une phrase au chef (« Cette demande suit le workflow du projet. »), puis cadrage : **aucun appel `proposer_organisation`, aucune décision `organisation`**. Sans workflow de création : comportement actuel. `proche`/`autre`/`incertain`, `coherente: false` : comportement actuel. `_reprendre_un_workflow` et `_classer_rate` copient aussi le workflow de création quand c'est lui qu'ils reprennent (une fonctionnalité ne pointe jamais sur `w-<genre>`).

- [x] **Étape 1 : tests** : `test_demande_meme_reprend_le_workflow_de_creation` (aucun jugement `proposer_organisation`, aucune décision, cadrage lancé, colonnes `f1-…`) ; `test_deuxieme_demande_meme_reprend_aussi` ; `test_demande_proche_propose_comme_avant` ; `test_projet_sans_workflow_de_creation_inchange` ; `test_classer_rate_copie_le_workflow_de_creation` ; `test_reprendre_refuse_un_workflow_de_fonctionnalite`.
- [x] **Étapes 2 à 4 : échec, code, vert** (`py -3.12 outils/tests.py moteur orch banc`).
- [x] **Étape 5 : commit** « Moteur : une demande du genre du projet reprend le workflow de création ».

### Tâche 6 : le poste (versions comparées, installation portée par le projet)

**Fichiers :**
- Modifier : `moteur/environnement.py` (`version_suffisante`, `verifier` compare `version_min`, `agent_d_installation` déplacé ici depuis `regles._agent_d_installation`), `moteur/regles.py` (`_agent_d_installation` appelle la fonction pure ; `_suite_de_tache`, `_poste_pret_ou_decision`, `_apres_echec_d_installation`, `_sur_environnement` acceptent une tâche d'installation **sans fonctionnalité**), `orchestrateur/outil.py` (`cmd_decision` : décision de projet `environnement`), `bureau/releve.py` (`DECISIONS_PROJET` gagne `environnement`), `bureau/demandes.py` (`environnement` : `fonctionnalite` devient facultatif), `bureau/web/ui/decisions.js` (décision `environnement` de projet), `bureau/web/ui/organisation.js` (version lue et version demandée côte à côte)
- Test : `tests/test_moteur_environnement.py`, `tests/test_moteur_regles.py`, `tests/test_demandes.py`, `bureau/web/tests/decisions.test.js`

**Interfaces :**
- Produit :
  - `environnement.version_suffisante(lue: str | None, minimale: str | None) -> bool | None` : `None` si l'une manque ou n'a aucun nombre ; compare les nombres dans l'ordre ; une version Java `1.x` vaut `x` (`"1.8.0_381"` < `"17"`) ;
  - `verifier(...)` : un outil trouvé mais trop ancien est `a_installer` avec `raison: "version <lue> trouvée, <min> demandée"` ; `version_min` est gardé dans l'outil ;
  - `environnement.agent_d_installation(existants: list[dict], nouveaux: list[dict], flux: list[dict], services: list[dict], outils_installation: list[str] | None = None) -> (dict | None, str | None)` : même agent et même brief qu'aujourd'hui (clé `env-<n>`, Sonnet, local, service de la première étape d'agent), avec `outils` = les règles quand elles sont données ;
  - tâche d'installation de projet : `{"titre": "Mise en place de l'environnement", "etape": "environnement", "role": "environnement", "colonne": "cadrage", "journal": [...]}` sans `fonctionnalite` ; à sa fin, revérification ; tout est là → une ligne au relevé (journal de la tâche) ; sinon décision de projet `environnement` `{texte, environnement: [outils qui manquent]}` (« C'est fait », « Continuer sans »), **sans jamais retenir le cadrage d'une demande** ; demande `{"type": "environnement", "decision", "verdict"}` sans `fonctionnalite`.

- [x] **Étape 1 : tests** : `test_version_suffisante` (`1.8` contre `17`, `21.0.2` contre `17`, absentes) ; `test_java_trop_ancien_a_installer` ; `test_agent_d_installation_pur` ; `test_installation_de_projet_reussie` ; `test_installation_de_projet_ratee_decision_de_projet` ; `test_installation_de_projet_ne_retient_pas_le_cadrage` ; `test_demande_environnement_sans_fonctionnalite` ; page : `decision environnement de projet`, `organisation montre la version demandee`.
- [x] **Étapes 2 à 4 : échec, code, vert** (`py -3.12 outils/tests.py moteur environnement orch demandes releve` et `node --test bureau/web/tests`).
- [x] **Étape 5 : commit** « Poste : versions comparées, installation portée par le projet ».

## Étape 4 — la création en deux fenêtres

### Tâche 7 : le brouillon d'échange, la couche et les prix du bureau commun

**Fichiers :**
- Créer : `installation/brouillons.py`
- Modifier : `bureau/reglages.py` (`lire_bureau` rend `moteur`, `{"couche": "claude"}` par défaut, contrôlé comme `_verifier_moteur`)
- Test : `tests/test_inst_brouillons.py`, `tests/test_reglages.py`

**Interfaces :**
- Produit (`installation/brouillons.py`) :
  - `JOURS_PURGE = 30`, `MOTIF_ID = re.compile(r"^c[0-9a-f]{12}\Z")` (jamais un chemin), dossier par défaut `dossier.racine() / "creations"`, fichier des échanges abandonnés `dossier.racine() / "usage-creations.jsonl"` ;
  - brouillon : `{"id", "cree", "maj", "infos": {"parent", "nom", "mots_interdits", "facturation", "github", "description"}, "echange": [...], "tours": int, "proposition": objet | null, "usages": [usage de `moteur.appel` + "t"], "erreur": texte | null}` ;
  - `creer(infos: dict, *, dossier=None, maintenant=None) -> dict` ; `lire(id_: str, *, dossier=None) -> dict` (`Echec` : id refusé, introuvable, illisible) ; `ecrire(b: dict, *, dossier=None) -> None` (écriture atomique, `maj` mise à jour) ; `lister(*, dossier=None) -> list[dict]` (`{id, nom, maj, etat: "questions" | "proposition", tours}`, le plus récent d'abord, illisibles ignorés) ; `abandonner(id_, *, dossier=None, commun=None) -> None` (ses usages ajoutés au fichier des échanges abandonnés, puis le brouillon supprimé) ; `retirer(id_, *, dossier=None) -> None` (après une création : usages déjà versés au projet) ; `purger(*, maintenant, dossier=None, commun=None) -> list[str]` (abandonne ceux dont `maj` a plus de 30 jours) ; `usages_abandonnes(*, commun=None) -> list[dict]`.
- `reglages.lire_bureau(...)["moteur"]` : la couche des appels faits avant le projet (`appel.choisir_couche(lire_bureau(...), environ)`).

- [x] **Étape 1 : tests** : `test_creer_lire_ecrire` ; `test_id_refuse_jamais_un_chemin` (`../x`, `c123`, absolu) ; `test_lister_plus_recent_d_abord_illisible_ignore` ; `test_abandonner_garde_les_usages` ; `test_purge_apres_30_jours` ; `test_brouillon_sans_cle` (la clé de l'environnement n'apparaît nulle part dans le fichier) ; `test_bureau_couche_par_defaut_et_api`.
- [x] **Étapes 2 à 4 : échec, code, vert** (`py -3.12 outils/tests.py brouillons reglages`).
- [x] **Étape 5 : commit** « Création : le brouillon de l'échange avec le chef ».

### Tâche 8 : le déroulé de l'échange

**Fichiers :**
- Créer : `installation/definition.py`
- Test : `tests/test_inst_definition.py`

**Interfaces :**
- Consomme : `jugement.juger("definir_workflow", …)` (tâche 4) ; `environnement.verifier`, `environnement.agent_d_installation` (tâche 6) ; `estimation.estimer`, `estimation.prix_de_modele` ; `brouillons` (tâche 7).
- Produit :
  - `dossier_du_tour(b: dict, *, genres_connus: list[dict], correction: str | None = None) -> dict` (le dossier de la tâche 4 ; `mots_interdits` = ceux des infos + le nom ; `proposer_maintenant` = `b["tours"] >= 4`) ;
  - `tour(b: dict, *, reponses: list[dict] | None = None, correction: str | None = None, genres_connus, couche, appeler=appel.appeler, verifier_environnement=environnement.verifier, prix_de=lambda modele: None) -> dict` : le brouillon mis à jour (non écrit) ; les réponses (`[{"question", "texte"}]`, une par question ouverte, texte ou choix) sont ajoutées à l'échange avant l'appel ; tous les usages ajoutés à `b["usages"]` ; réponse `questions` → message du chef, `tours += 1` ; réponse `proposition` → `b["proposition"] = proposition_calculee(...)` ; jugement raté (`Decision.question`) → `b["erreur"]` = la question, rien d'autre ne change ;
  - `proposition_calculee(o: dict, infos: dict, *, verifier_environnement, prix_de) -> dict` : `{"message", "genre": {"id", "nouveau": bool, "description"?}, "workflow": {"id": "w-<genre>", "genre", "flux"}, "raisons": {etape: raison}, "services" (tous : facturation + nouveaux), "agents" (nouveaux, `lieu: "local"`, + l'agent d'installation s'il manque des outils, avec `outils` = `outils_installation`), "briefs", "livrable", "environnement" (vérifié), "outils_installation", "cout": {"tokens", "euros"}, "texte"}` ; `texte` : la proposition expliquée (genre, étapes avec rôle, service et raison, validations du Directeur, agents avec modèle et justification, poste « déjà en place » / « à installer » avec versions, coût d'un élément) ; coût par `estimation.estimer` sur `workflows.etapes_d_agent`, Fable au tarif d'Opus ;
  - `cout_echange(usages: list[dict], prix_de) -> {"tokens": int, "euros": float | None}` (compteur par compteur, comme `estimation._euros_usage`).

- [x] **Étape 1 : tests** (faux `appeler`) : `test_premier_tour_pose_des_questions` ; `test_reponses_ajoutees_avant_l_appel` ; `test_cinquieme_appel_demande_la_proposition` (dossier `proposer_maintenant`) ; `test_proposition_calculee_poste_et_cout` (outil à installer → agent d'installation avec ses outils ; euros quand les prix sont connus, `null` sinon) ; `test_correction_hors_des_quatre_tours` ; `test_tour_rate_ne_compte_pas` (usages gardés, `erreur` posée, `tours` inchangé) ; `test_cout_echange_cumule`.
- [x] **Étapes 2 à 4 : échec, code, vert** (`py -3.12 outils/tests.py definition`).
- [x] **Étape 5 : commit** « Création : l'échange avec le chef, tour par tour ».

### Tâche 9 : créer le projet avec son organisation

**Fichiers :**
- Modifier : `installation/creation.py` (`creer_projet(..., organisation=None)` ; `_github` devient public `github(projet, nom, git, gh)`), `installation/mise_en_place.py` (`_ecrire_configuration` : avec `p["workflow"]`, `ecrire_organisation(..., workflow=…, environnement=…)` dans le dossier temporaire), `orchestrateur/fiches.py` (`accorder_fable`, employé aussi par `outil.cmd_organisation`), `installation/definition.py` (`valider`)
- Test : `tests/test_inst_creation.py`, `tests/test_inst_definition.py`, `tests/test_orch_organisation.py`

**Interfaces :**
- Consomme : `proposition_calculee` (tâche 8), `brouillons.retirer` (tâche 7).
- Produit :
  - `creer_projet(parent, nom, *, ..., organisation: dict | None = None)` : `organisation = {"services": [nouveaux], "agents", "briefs", "workflow": {"id", "genre", "flux"}, "environnement"}` écrite **dans la même transaction** que la configuration (dossier `.factory.tmp` puis renommage) ; un refus d'`ecrire_organisation` n'écrit rien ;
  - `fiches.accorder_fable(agents: list[dict], cles: list[str], jour: str) -> list[dict]` (`ValueError` pour une clé sans `fable_suggere`) ;
  - `class InfosAChanger(Echec)` (dans `definition.py`) : le nom, le dossier ou le bureau ne permettent plus la création ;
  - `definition.valider(b: dict, *, fable: list[str], installer: bool, genre_description: str | None, bureau_json, executer=outil.executer, git=..., gh=..., maintenant=None) -> {"reglages", "id", "projet", "github", "message"}`, dans cet ordre : revérifier les infos (`verifier_nom`, `verifier_parent`, dossier libre, bureau pas plein ; sinon `InfosAChanger`) ; Fable accordé ; sans `installer`, ni agent d'installation ni outils ; `creer_projet(..., genre=<genre connu> ou None, organisation=…, github=False)` ; **ensuite seulement**, et sans rien défaire en cas d'échec (le message le dit) : genre nouveau par `lancer genre {"action": "fixer", "genre", "description"}` (description éditée par l'utilisateur, sinon celle proposée), usages versés par `lancer usage` (agent `orchestrateur`, étape `orchestration`), tâche d'installation de projet (tâche 6) si `installer` et des outils manquent, GitHub par `creation.github` si demandé, `brouillons.retirer`.

- [x] **Étape 1 : tests** : `test_creer_avec_organisation` (workflow `w-<genre>` sans préfixe, fiches, briefs, services, environnement ; `factory.lire` valide) ; `test_organisation_refusee_ne_laisse_rien` ; `test_nom_pris_entre_temps_retour_infos` ; `test_genre_nouveau_cree_par_l_outil` ; `test_genre_nouveau_refuse_projet_garde` ; `test_usages_verses_au_releve` ; `test_installation_acceptee_tache_de_projet` ; `test_installation_refusee_pas_d_agent_d_installation` ; `test_fable_accorde_par_agent` ; `test_github_apres_et_sans_rien_defaire` ; `test_brouillon_retire_apres_creation`.
- [x] **Étapes 2 à 4 : échec, code, vert** (`py -3.12 outils/tests.py creation definition organisation`).
- [x] **Étape 5 : commit** « Création : le projet naît avec son workflow et son équipe ».

## Étape 5 — le bureau

### Tâche 10 : les routes de la création

**Fichiers :**
- Modifier : `bureau/serveur.py` (`Bureau` : `creations_liste`, `creations_infos`, `creations_tour`, `creations_valider`, `creations_supprimer` ; `appeler_jugement` et `verifier_environnement` injectables pour les essais ; un verrou par brouillon ; routes dans `do_GET`/`do_POST`)
- Test : `tests/test_bureau_creation.py`

**Interfaces :**
- Consomme : `brouillons` (tâche 7), `definition.tour`, `definition.cout_echange` (tâche 8), `definition.valider`, `InfosAChanger` (tâche 9).
- Produit (mêmes en-têtes que `POST /api/projets/creer` ; code d'accès exigé sur un écouteur distant ; 409 sans bureau commun) :
  - `GET /api/creations` → `{"brouillons": [{id, nom, maj, etat, tours, euros}], "abandonnes": {"euros"}}` (purge des plus de 30 jours d'abord) ;
  - `POST /api/creations/infos` `{id?, parent, nom, mots_interdits, facturation, github, description}` → contrôles de la fenêtre 1 (description obligatoire, `verifier_nom`, `verifier_parent`, dossier libre, bureau pas plein) → `{"brouillon": <vue>}` ; rien sur le disque hors du brouillon ;
  - `POST /api/creations/tour` `{id, reponses?, correction?}` → `definition.tour` (couche de `lire_bureau(...)["moteur"]`, prix par `estimation.prix_de_modele(<bureau commun>, …)`, genres de la mémoire de la skill), brouillon écrit → `{"brouillon": <vue>}` ; **409 « Un tour est déjà en cours pour ce projet. »** si le verrou est pris ;
  - `POST /api/creations/valider` `{id, fable?, installer?, genre_description?}` → `{ok, projet, github, message}` ; `InfosAChanger` → 409 `{"erreur", "retour": "infos"}` (brouillon gardé) ;
  - `POST /api/creations/supprimer` `{id}` → `brouillons.abandonner` → `{"ok": true}` ;
  - vue d'un brouillon : `{id, infos, echange, tours, tours_max, proposition, erreur, cout: {tokens, euros}}`.

- [x] **Étape 1 : tests** : `test_infos_controle_et_cree_le_brouillon` ; `test_infos_description_obligatoire` ; `test_tour_rend_les_questions_et_le_cout` ; `test_tour_deja_en_cours_refuse` ; `test_valider_cree_et_liste_le_projet` ; `test_valider_renvoie_aux_infos` ; `test_supprimer_garde_le_cout` ; `test_routes_exigent_le_code_d_acces` ; `test_aucun_projet_tant_que_rien_n_est_valide`.
- [x] **Étapes 2 à 4 : échec, code, vert** (`py -3.12 outils/tests.py bureau_creation serveur`).
- [x] **Étape 5 : commit** « Bureau : les routes de la création en deux fenêtres ».

### Tâche 11 : la page « Nouveau projet… » en deux fenêtres

**Fichiers :**
- Modifier : `bureau/web/ui/creation.js` (deux fenêtres ; la création depuis une décision `genre_fonctionnalite` garde le formulaire actuel), `bureau/web/main.js` ou `bureau/web/ui/projets.js` si l'ouverture change, `bureau/web/style.css` si besoin (utilisable au téléphone)
- Test : `bureau/web/tests/creation.test.js`

**Interfaces :**
- Consomme : les routes de la tâche 10.
- Produit (fonctions pures exportées, testées) : `corpsInfos(champs, id)`, `verifierInfos(champs) -> message | null` (description obligatoire), `corpsTour(id, questions, valeurs) -> objet | null` (`null` si une question est sans réponse), `corpsCorrection(id, texte)`, `vueEchange(brouillon) -> {messages, questions, proposition, erreur, cout}`, `texteCout(cout) -> str` (« Coût de l'échange : 0,03 € » ; tokens si les prix manquent), `lignesProposition(proposition) -> [str]` (genre, étapes avec rôle, service et raison, « Validation du Directeur », agents, poste avec versions, coût d'un élément), `corpsValidation(id, {fable, installer, genreDescription})`.
- Parcours : « Nouveau projet… » propose d'abord les brouillons existants (« Reprendre », « Supprimer », coût de chacun) ; fenêtre 1 (champs actuels + description obligatoire, bouton « Valider ») ; fenêtre 2 (messages du chef, un champ texte par question et les `choix` en boutons qui le remplissent, « Envoyer mes réponses », coût au fil de l'eau, un indicateur pendant l'appel) ; proposition (texte expliqué, description du genre nouveau pré-remplie et modifiable, case Fable par agent seulement si suggéré, case « Installer ce qui manque » si des outils sont à installer, « Valider et créer le projet », « Demander une correction » avec un texte) ; `retour: "infos"` ramène à la fenêtre 1 avec le message, l'échange gardé ; succès → `apresCreation`.

- [x] **Étape 1 : tests** : `infos exige la description` ; `tour exige une reponse par question` ; `un choix remplit la reponse` ; `cout affiche en euros ou en tokens` ; `proposition montre les validations et les raisons` ; `fable seulement si suggere` ; `retour infos garde l echange` ; `depuis une decision le formulaire actuel reste`.
- [x] **Étapes 2 à 4 : échec, code, vert** (`node --test bureau/web/tests`).
- [x] **Étape 5 : commit** « Bureau : créer un projet en définissant son workflow avec le chef ».

## Étape 6 — la vérification (avec l'utilisateur)

### Tâche 12 : banc gratuit et essai réel au bureau

**Fichiers :**
- Modifier : `docs/superpowers/plans/2026-11-12-workflow-des-la-creation-passation.md` (bilan) ; corrections éventuelles, une par commit, testées.

- [ ] **Étape 1 : banc gratuit** : `py -3.12 outils/tests.py banc` et le rejoueur sur le scénario de référence (sans appel réel) : aucun écart nouveau.
- [ ] **Étape 2 : essai réel au bureau, avec l'accord de l'utilisateur** (bureau et moteur relancés, pilotés par HTTP ; dossier parent d'essai hors dépôt, donné par l'utilisateur) : « Nouveau projet… » → jeu Android ; échange complet en demandant une **validation du Directeur avant la livraison** ; noter chaque appel (tokens, coût), **coût de l'échange complet < 0,10 €** ; valider ; projet créé, listé, avec workflow `w-<genre>`, agents et services ; une première demande du genre → **aucune proposition ni validation de workflow**, cadrage direct. **Ne rien installer sur le poste sans accord explicite** : si des outils sont « à installer », décocher « Installer ce qui manque » (ou s'arrêter et demander). Aller jusqu'à la validation du Directeur seulement si l'utilisateur accepte la dépense de production.
- [ ] **Étape 3 : suite complète** `py -3.12 outils/tests.py`, bilan dans la passation, commit et push.
