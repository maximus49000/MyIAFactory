# Avancement d'une tâche sur sa fiche — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** la fiche d'une tâche dit où l'agent en est, le temps passé, le temps restant (fourchette) et si ça avance ou si c'est bloqué.

**Architecture :** le moteur (`moteur/detache.py`) lit déjà le flux de chaque agent ; on y ajoute la liste d'avancement écrite par l'agent et la phase déduite du flux. Un module pur `bureau/avancement.py` calcule l'état, le temps passé et la fourchette restante ; `bureau/serveur.py` l'ajoute à chaque tâche de `/api/etat` ; l'interface (`bureau/web/ui`) l'affiche. Aucun nouveau stockage : les durées passées viennent de `suivi.json`.

**Tech Stack :** Python 3.12 (moteur, bureau ; tout ce que lance un agent doit rester compatible 3.9), JavaScript sans dépendance (`node --test`).

**Spec :** `docs/superpowers/specs/2026-11-17-avancement-d-une-tache-design.md`

## Global Constraints

- Une estimation inconnue s'affiche « inconnu » : moins de 3 durées connues pour l'étape → pas de fourchette.
- Seuils : résultat non lu après 2 min → « agent terminé, résultat en attente » ; moteur muet après 3 min sans battement.
- Garde-fou d'arrêt montré : `agents.DELAI_AGENT_S` (2400 s), jamais recopié en dur ailleurs.
- Python 3.9 : pas d'antislash dans une expression de f-string, pas de `X | Y` en annotation, pas de `match`.
- Jamais le contenu d'une commande, d'un fichier ou d'un message dans la fiche (règle de `detache.derniere_action`).
- Un seul rédacteur par fichier : l'agent écrit `<tâche>.avancement.json`, le moteur n'y touche pas.
- Une règle pour la famille, pas un cas par cas.

## Review Focus

- Flux de l'agent absent ou vide (agent qui démarre) : la fiche affiche « démarre », pas d'erreur.
- `avancement.json` illisible ou à moitié écrit : ignoré, phase déduite du flux.
- Liste d'avancement qui ne bouge plus alors que l'agent agit : la fiche le dit (« liste non mise à jour depuis N min »).
- Durées d'historique aberrantes (0 s, plusieurs jours) : écartées avant le calcul de la fourchette.
- Tâche déjà plus longue que d'habitude : « plus long que d'habitude », jamais un temps restant négatif.

---

### Task 1 : Lire l'avancement et la phase dans le moteur

**Files :**
- Modify: `moteur/detache.py` (`ajouter_au_travail`, `Registre.effacer`, nouvelles fonctions)
- Test: `tests/test_moteur_detache.py`

**Interfaces :**
- Produces: `detache.lire_avancement(chemin: Path) -> Optional[dict]` rend `{"points": [{"texte": str, "fait": bool}], "en_cours": Optional[str], "maj": iso}` ou `None` (absent, illisible, mal formé).
- Produces: `detache.phase_du_flux(lignes: list) -> Optional[str]` parmi `"lecture"`, `"modification"`, `"compilation"`, `"tests"`, `"autre"`, ou `None` sans action ; d'après le dernier `tool_use` (Read/Grep/Glob → lecture ; Edit/Write → modification ; commande Bash contenant `gradle`/`assemble`/`compile` → compilation ; contenant `test`/`lancer.py`/`adb`/`emulator` → tests ; sinon autre).
- Produces: `ajouter_au_travail` ajoute à `travail` les clés `avancement` (`lire_avancement` du `<tâche>.avancement.json`) et `phase` ; et pose `tache["agent_termine"] = {"t": iso}` pour une tâche dont l'agent n'est plus vivant mais dont le flux a une ligne `result` (`t` = date de modification du flux).
- `Registre.effacer` oublie aussi le suffixe `.avancement.json`.

- [ ] **Step 1 : tests qui échouent** — `test_lire_avancement_valide`, `test_lire_avancement_illisible_rend_none`, `test_phase_du_flux` (une ligne `tool_use` par cas : `Read` → `"lecture"`, `Bash "gradlew assembleRelease"` → `"compilation"`, `Bash "py lancer.py"` → `"tests"`, aucune ligne → `None`), `test_ajouter_au_travail_porte_avancement_et_phase`, `test_agent_mort_avec_resultat_est_dit_termine` (agent non vivant, flux avec `result` → `agent_termine["t"]` posé, `travail` absent), `test_effacer_oublie_avancement`.
- [ ] **Step 2 :** `py -3.12 -m unittest tests.test_moteur_detache` → les 6 nouveaux tests échouent.
- [ ] **Step 3 :** implémenter les deux fonctions et étendre `ajouter_au_travail` / `Registre.effacer` (le suffixe passe dans le tuple déjà parcouru par `effacer`).
- [ ] **Step 4 :** relancer ; attendu : tous verts. Vérifier aussi `py -3.9 -m py_compile moteur/detache.py`.
- [ ] **Step 5 :** `git commit -m "Moteur : l'avancement écrit par l'agent, la phase du flux et l'agent terminé sont lus pour la fiche"`.

### Task 2 : Calcul de l'état, du temps passé et du temps restant

**Files :**
- Create: `bureau/avancement.py`
- Test: `tests/test_bureau_avancement.py`

**Interfaces :**
- Consumes: `tache["travail"]` (`depuis`, `action_t`, `vie_t`, `avancement`, `phase`), `tache["agent_termine"]`, `tache["debut"]`, `tache["etape"]`, `tache["active"]` (Task 1 / suivi).
- Produces: `avancement.pour_la_tache(tache: dict, historique: list, battement_moteur_t: Optional[float], maintenant: datetime, delai_arret_s: int) -> dict` rend `{"etat", "etat_texte", "points", "en_cours", "phase", "passe_s", "cumul_s", "reste": {"min_s", "max_s"} | None, "reste_texte"}`.
  - `etat` ∈ `"avance"`, `"commande_longue"`, `"sans_action"`, `"termine_non_lu"`, `"moteur_muet"`, `"demarre"`.
  - `etat_texte` : « avance », « commande longue en cours depuis N min », « sans action depuis N min, arrêt automatique à M min », « agent terminé, résultat en attente de lecture depuis N min », « moteur muet depuis N min », « démarre ».
- Produces: `avancement.durees_de_l_etape(taches: list, etape: str) -> list` (secondes, tâches de l'étape avec `debut` et `fin`, durée entre 30 s et 6 h).
- Produces: `avancement.fourchette(durees: list) -> Optional[tuple]` : premier et troisième quartile ; `None` sous 3 durées.

- [ ] **Step 1 : tests qui échouent** — un test par état (`avance` : action il y a 20 s ; `commande_longue` : `vie_t` récent, `action_t` ancien de 5 min ; `sans_action` : rien depuis 12 min, texte « arrêt automatique à 40 min » ; `termine_non_lu` : `agent_termine.t` il y a 3 min → état dit, sous 2 min → pas dit ; `moteur_muet` : battement vieux de 4 min ; `demarre` : pas de flux) ; `test_fourchette_inconnue_sous_trois_durees` ; `test_fourchette_ecarte_les_durees_aberrantes` (0 s et 3 jours écartées) ; `test_reste_deduit_le_temps_passe` (fourchette 10–20 min, passé 4 min → « 6 à 16 min ») ; `test_reste_plus_long_que_d_habitude` (passé 30 min → texte « plus long que d'habitude », `reste` = `None`) ; `test_liste_non_mise_a_jour` (liste inchangée depuis 10 min alors que l'agent agit → `etat_texte` ajoute « liste non mise à jour depuis 10 min ») ; `test_avancement_ajuste_la_fourchette` (3 points sur 4 faits → la borne haute du reste est réduite d'autant).
- [ ] **Step 2 :** `py -3.12 -m unittest tests.test_bureau_avancement` → échecs.
- [ ] **Step 3 :** implémenter (module pur, aucune lecture de fichier : tout entre en paramètre).
- [ ] **Step 4 :** relancer ; attendu : verts ; `py -3.9 -m py_compile bureau/avancement.py`.
- [ ] **Step 5 :** `git commit -m "Bureau : l'état, le temps passé et la fourchette du temps restant d'une tâche"`.

### Task 3 : Servir l'avancement avec l'état

**Files :**
- Modify: `bureau/serveur.py` (juste après `detache.ajouter_au_travail`, vers la ligne 281)
- Test: `tests/test_bureau_serveur.py` (ou le fichier d'état existant le plus proche : `grep -l "ajouter_au_travail" tests`)

**Interfaces :**
- Consumes: `avancement.pour_la_tache`, `agents.DELAI_AGENT_S`.
- Produces: chaque `t` de `e["taches"]` portant `travail` ou `agent_termine` reçoit `t["avancement"]` (le dict de Task 2). Le battement du moteur est la date de la dernière ligne de `charge-historique.jsonl` du dossier de la factory (champ `t`, secondes) ; le réalisateur vérifie dans `moteur/boucle.py` qui l'écrit et, à défaut, se rabat sur `moteur.pid`. L'historique est `e["taches"]` lui-même (tâches terminées avec `debut` et `fin`).

- [ ] **Step 1 :** test `test_etat_porte_l_avancement_d_une_tache_au_travail` (tâche avec dossier d'agent factice → `avancement.etat == "avance"`) et `test_etat_dit_moteur_muet` (battement vieux de 10 min) ; ne jamais faire tomber l'état : `test_avancement_en_erreur_ne_fait_pas_tomber_l_etat` (module qui lève → tâche sans `avancement`, état servi).
- [ ] **Step 2 :** lancer le fichier de tests → échecs.
- [ ] **Step 3 :** brancher l'appel dans un `try/except Exception` comme les autres aides de l'état.
- [ ] **Step 4 :** relancer ; attendu : verts.
- [ ] **Step 5 :** `git commit -m "Bureau : l'état de chaque tâche au travail porte son avancement"`.

### Task 4 : Afficher l'avancement sur la fiche

**Files :**
- Modify: `bureau/web/ui/detail.js` (ligne ~226, section « Au travail »), `bureau/web/ui/texte.js`
- Test: `bureau/web/tests/avancement.test.js`

**Interfaces :**
- Produces: `texte.avancementEnClair(avancement: object, maintenant = new Date()) -> {etat, etatTexte, passe, cumul, reste, points}` où `passe`/`cumul` sont « 18 min » / « 1 h 05 » (réutiliser `dureeEnClair`), `reste` est la fourchette ou « inconnu », `points` la liste `{texte, fait}`.
- La fiche affiche, à la place de la seule ligne « Au travail » : « Où il en est » (points cochés, ligne « en cours », sinon « phase : tests » avec la mention « liste de l'agent absente »), « Temps » (passé · cumul · reste), « État » (pastille verte avance / orange commande longue / rouge sans action, terminé non lu ou moteur muet).

- [ ] **Step 1 :** tests `avancement.test.js` : `test_points_et_en_cours`, `test_phase_sans_liste`, `test_reste_inconnu_est_dit_inconnu`, `test_etat_rouge_pour_moteur_muet`, `test_sans_avancement_rend_null` (tâche sans le champ : la fiche garde l'ancienne ligne « Au travail »).
- [ ] **Step 2 :** `node --test bureau/web/tests/avancement.test.js` → échecs.
- [ ] **Step 3 :** implémenter `avancementEnClair` et le dessin dans `detail.js` ; `cleTravail` inclut l'état pour que la fiche se redessine quand il change.
- [ ] **Step 4 :** `node --test bureau/web/tests/` ; attendu : tout vert. Regarder la fiche dans le navigateur du bureau (une tâche au travail).
- [ ] **Step 5 :** `git commit -m "Bureau : la fiche d'une tâche dit où elle en est, le temps passé et restant, et si elle avance"`.

### Task 5 : Demander la liste à l'agent

**Files :**
- Modify: `moteur/regles.py` (constante près de `APK_A_JOUR_AVANT_LES_TESTS`, et la fonction qui assemble la consigne, vers la ligne 3690 où `if consignes:` termine)
- Test: `tests/test_moteur_regles.py`

**Interfaces :**
- Produces: `CONSIGNE_AVANCEMENT` ajoutée à toute consigne d'agent de tâche : « Dès le début, écris dans `<dossier factory>/agents-en-cours/<id>.avancement.json` la liste de tes points `{"points": [{"texte": "...", "fait": false}], "en_cours": "..."}` (pour une correction : un point par défaut du refus) ; coche `fait` et mets à jour `en_cours` à chaque point terminé. Une ligne, pas de commentaire. » Le chemin est calculé avec l'id de la tâche.

- [ ] **Step 1 :** tests : `test_la_consigne_demande_la_liste_d_avancement` (contient le chemin exact de la tâche), `test_la_consigne_d_avancement_est_dans_chaque_etape` (correction, flux, relecture), `test_pas_de_consigne_d_avancement_pour_le_chef`.
- [ ] **Step 2 :** `py -3.12 -m unittest tests.test_moteur_regles` → échecs.
- [ ] **Step 3 :** implémenter.
- [ ] **Step 4 :** relancer (la suite dure ~90 s) ; attendu : verts.
- [ ] **Step 5 :** `git commit -m "Agents : la consigne demande la liste d'avancement, lue par la fiche"`.

### Task 6 : Documentation et mise en service

**Files :**
- Modify: `docs/avancement.md` (section sur la fiche d'une tâche)

- [ ] **Step 1 :** décrire en quelques lignes les quatre états, la liste de l'agent et la fourchette.
- [ ] **Step 2 :** `py -3.12 -m unittest discover tests` et `node --test bureau/web/tests/` ; tout vert.
- [ ] **Step 3 :** commit, push, puis `git pull --ff-only` dans `~/MyIAFactory/skill`.
- [ ] **Step 4 :** relancer le bureau et le moteur (par PID exact, entre deux tâches) ; vérifier sur une tâche au travail que la fiche montre les quatre informations.
