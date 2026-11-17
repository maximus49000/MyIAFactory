# Exécution déportée — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** le Directeur choisit, par type d'action (APK, tests, charge, émulateur), si elle s'exécute sur le poste, chez GitHub ou (plus tard) sur un serveur ; les dépendances entre actions sont attendues, le résultat et la consommation reviennent dans le bureau.

**Architecture :** un module pur `bureau/deport.py` porte les types d'action, leurs dépendances et le calcul du lieu effectif. Les réglages (`bureau/reglages.py`) stockent le lieu par action (global dans le fichier du bureau, surcharge par projet). Un point d'entrée `lancer.py deporter <type>` (`outils/deporter.py`) aiguille : poste = comportement actuel, `github` = workflow GitHub Actions généré par `outils/workflow_github.py` et piloté par `outils/github_actions.py` (enveloppe de `gh`). Le bureau affiche les cases, l'aperçu du workflow à valider, l'attente et la consommation.

**Tech Stack :** Python 3.12 pour le bureau (tout ce que lance un agent — `outils/`, `lancer.py` — reste compatible 3.9), JavaScript sans dépendance (`node --test`), `gh` CLI, GitHub Actions.

**Spec :** `docs/superpowers/specs/2026-11-17-execution-deportee-design.md`

## Global Constraints

- Le lieu par défaut de toute action est `poste` ; sans réglage, rien ne change pour l'existant.
- Lieux : `poste`, `github`, `serveur` (`serveur` affiché grisé « bientôt », refusé à la validation à l'étape 1). Types : `apk`, `tests`, `charge`, `emulateur`.
- `emulateur` en `github` est refusé : message « peu fiable sur GitHub, utilisez le poste ou le serveur ».
- GitHub : runners Linux uniquement (`ubuntu-latest`), jamais Windows ni macOS.
- Jamais de push, de workflow poussé ni de bascule vers le poste sans accord du Directeur ; jamais de secret saisi par l'application.
- Alerte de quota à 80 % ; à 100 %, proposition de passer au poste avec accord, jamais de bascule automatique.
- Charge de nuit planifiée à 03:00 par défaut, réglable ; le bouton manuel est un `workflow_dispatch` lancé par `gh`.
- Le garde-fou « sans action » des agents (`moteur.agents.DELAI_AGENT_S`) ne doit pas arrêter un agent qui attend une exécution déportée.
- L'action distante travaille sur le commit poussé : jamais compiler un code différent de celui que l'agent teste.
- Tests : toujours par le lanceur (`py -3.12 outils/tests_paralleles.py <module>` ou `py -3.12 lancer.py tests -- <commande>`), une campagne à la fois ; jamais `unittest discover` ni `pytest` directement.
- Python 3.9 pour `outils/` et `lancer.py` : pas de `X | Y` en annotation, pas de `match`, pas d'antislash dans une f-string.

## Review Focus

- Dépôt sans `gh` installé ou non connecté : `deporter` dit quoi faire (« gh auth login ») et ne plante pas, ne bascule pas.
- Réglage `deport` malformé dans un vieux fichier de réglages : lecture rejetée avec un message clair ; absent : défauts.
- Deux agents demandent l'APK du même commit en même temps : une seule exécution GitHub, l'autre attend la même.
- Tâche annulée ou agent arrêté pendant l'attente : l'exécution distante n'est pas relancée en boucle et le fichier d'attente est retiré.
- Workflow modifié à la main entre deux validations : jamais écrasé, le bureau demande.
- Pas de réseau ou quota atteint : l'action est proposée au poste avec accord, jamais relancée en silence.

---

### Task 1: Logique pure des lieux et des dépendances

**Files:**
- Create: `bureau/deport.py`
- Test: `tests/test_deport_logique.py`

**Interfaces:**
- Produces: `ACTIONS: dict` — `{"apk": {"produit": "apk", "consomme": []}, "tests": {"produit": None, "consomme": ["apk"]}, "emulateur": {"produit": None, "consomme": ["apk"]}, "charge": {"produit": None, "consomme": ["apk"]}}` ; `LIEUX = ("poste", "github", "serveur")` ; `LIEUX_ETAPE_1 = ("poste", "github")` ; `LIEUX_PAR_DEFAUT: dict` (tout à `poste`) ; `valider_lieux(lieux: dict, etape_serveur: bool = False) -> dict` (lève `ValueError` avec un message en français) ; `lieu_effectif(global_: dict, projet: dict, action: str) -> str` (la surcharge du projet l'emporte, sinon le global, sinon `poste`) ; `a_attendre(lieux: dict, action: str) -> list[str]` (les productions d'un autre lieu que celui de `action` dont elle dépend) ; `avertissements(lieux: dict) -> list[str]`.

- [ ] **Step 1: Write the failing tests** — `test_defaut_tout_au_poste` (`lieu_effectif({}, {}, "apk") == "poste"`), `test_surcharge_du_projet` (global `github`, projet `poste` → `poste`), `test_emulateur_github_refuse` (`valider_lieux({"emulateur": "github"})` lève `ValueError` dont le message contient « peu fiable »), `test_serveur_refuse_a_l_etape_1` et accepté avec `etape_serveur=True`, `test_action_inconnue_refusee`, `test_attend_l_apk_d_un_autre_lieu` (`a_attendre({"apk": "github", "tests": "poste"}, "tests") == ["apk"]`), `test_rien_a_attendre_au_meme_lieu` (`[]`), `test_avertissement_dit_la_chaine` (le texte cite « tests », « poste » et « GitHub » et suggère de mettre la chaîne au même lieu).
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py deport_logique` — attendu : échec (module absent).
- [ ] **Step 3: Implement** `bureau/deport.py` avec les signatures ci-dessus ; fonctions pures, aucun accès disque.
- [ ] **Step 4: Run** la même commande — attendu : tous les tests passent.
- [ ] **Step 5: Commit** `git add bureau/deport.py tests/test_deport_logique.py && git commit -m "Déport : types d'action, lieux et dépendances (module pur)"`

### Task 2: Réglages du déport (projet et bureau)

**Files:**
- Modify: `bureau/reglages.py` (`DEFAUTS`, `_verifier_moteur`, `lire_bureau`, nouvelles `fixer_deport`)
- Test: `tests/test_reglages.py` (ajouter), `tests/test_deport_reglages.py`

**Interfaces:**
- Consumes: `bureau.deport.valider_lieux`, `LIEUX_PAR_DEFAUT`.
- Produces: clé de réglages projet `deport: {"lieux": {action: lieu}, "commandes": {action: str}, "charge_heure": "03:00"}` (absente = défauts) ; même clé `deport` dans le fichier du bureau (valeurs globales) ; `reglages.fixer_deport(chemin: Path, deport: dict) -> dict` (écriture atomique via `_ecrire_cle`, valide avant d'écrire, rend les réglages rechargés) ; `lire_bureau(...)["deport"]`.

- [ ] **Step 1: Write the failing tests** — fichier absent : `charger(...)["deport"]["lieux"]["apk"] == "poste"` ; `{"deport": {"lieux": {"apk": "github"}}}` complète les autres actions au défaut ; `{"deport": {"lieux": {"emulateur": "github"}}}` lève `ReglagesInvalides` ; `charge_heure` valide `HH:MM` (`"25:00"` rejeté) ; `fixer_deport` écrit sans toucher aux autres clés (`charge_max` conservé) ; `lire_bureau` lit `deport` global et rejette un lieu inconnu.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py deport_reglages reglages` — attendu : échec.
- [ ] **Step 3: Implement** : `DEFAUTS["deport"]` (lieux tout `poste`, `commandes` vide, `charge_heure` `"03:00"`) ; la validation appelle `valider_lieux` et convertit `ValueError` en `ReglagesInvalides` ; `fixer_deport` suit le modèle de `fixer_lecons_auto`.
- [ ] **Step 4: Run** les mêmes tests — attendu : passent.
- [ ] **Step 5: Commit** `Déport : réglages par projet et globaux du bureau`

### Task 3: Interface HTTP et état du bureau

**Files:**
- Modify: `bureau/serveur.py` (bloc du `POST` des réglages vers 1870 ; état vers 256 ; `/api/etat`)
- Test: `tests/test_bureau_deport.py`

**Interfaces:**
- Consumes: `reglages.fixer_deport`, `deport.lieu_effectif`, `deport.avertissements`.
- Produces: `POST /api/reglages` accepte `{"deport": {...}}` ; `/api/etat` d'un projet contient `deport: {"lieux": {action: lieu_effectif}, "avertissements": [str], "serveur_disponible": false}`.

- [ ] **Step 1: Write the failing tests** (dans le style de `tests/test_bureau_projets.py`) — un `POST {"deport": {"lieux": {"apk": "github"}}}` rend 200 et `/api/etat` dit `apk: "github"` ; `{"deport": {"lieux": {"emulateur": "github"}}}` rend 400 avec « peu fiable » ; `{"apk": "github", "tests": "poste"}` produit un avertissement dans l'état.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py bureau_deport` — attendu : échec.
- [ ] **Step 3: Implement** la branche `"deport" in corps` (avant le `else`), l'état, et mettre à jour le message d'erreur « Le corps doit contenir … ».
- [ ] **Step 4: Run** les tests de ce module et `bureau_projets` — attendu : passent.
- [ ] **Step 5: Commit** `Déport : le serveur du bureau lit, écrit et expose les lieux`

### Task 4: Cases du bureau (lieu par action, avertissements)

**Files:**
- Create: `bureau/web/ui/deport.js`
- Modify: `bureau/web/ui/directeur.js` (insérer le bloc à côté des autres cases, vers la ligne 90)
- Test: `bureau/web/tests/deport.test.js`

**Interfaces:**
- Consumes: `état.deport` (Task 3), `enregistrerReglage` de `directeur.js`.
- Produces: `export function blocDeport(ctx) -> HTMLElement` ; `export function enregistrerDeport(lieux, fetchFn = fetch)` ; `export const AIDE_DEPORT` (texte qui dit que `poste` est le défaut et qu'on déporte pour soulager le poste).

- [ ] **Step 1: Write the failing tests** — pour chaque action, un choix poste / GitHub / serveur ; `serveur` est `disabled` avec le texte « bientôt » ; `emulateur` n'offre pas `github` (grisé, message « peu fiable sur GitHub ») ; changer un choix appelle `enregistrerDeport` avec `{"lieux": {"apk": "github"}}` ; les avertissements de l'état s'affichent sous les choix ; un refus du serveur remet le choix réel et affiche le message.
- [ ] **Step 2: Run** `py -3.12 lancer.py tests -- node --test bureau/web/tests/deport.test.js` — attendu : échec.
- [ ] **Step 3: Implement** `deport.js` sur le modèle de `caseReglage` ; brancher dans `directeur.js`.
- [ ] **Step 4: Run** ce test et `bureau/web/tests/directeur*.test.js` — attendu : passent.
- [ ] **Step 5: Commit** `Déport : les cases du bureau`

### Task 5: Enveloppe de `gh`

**Files:**
- Create: `outils/github_actions.py`
- Test: `tests/test_deport_github.py`

**Interfaces:**
- Produces (toutes prennent `lancer=subprocess.run`-compatible injectable, Python 3.9) :
  `gh_pret(lancer=...) -> tuple[bool, str]` (installé et connecté, sinon message « gh auth login ») ;
  `visibilite(depot_dossier: str, lancer=...) -> str` (`"public"` ou `"prive"`, via `gh repo view --json visibility`) ;
  `declencher(depot_dossier: str, workflow: str, ref: str, entrees: dict, lancer=...) -> None` (`gh workflow run`) ;
  `execution_du_commit(depot_dossier: str, workflow: str, commit: str, lancer=...) -> dict | None` (`{"id", "statut", "conclusion", "duree_s", "url"}`) ;
  `suivre(depot_dossier: str, run_id: int, dormir=time.sleep, dire=print, delai_s: int = 3600, lancer=...) -> dict` (attend la fin, imprime une ligne d'état par minute) ;
  `telecharger(depot_dossier: str, run_id: int, nom: str, dossier: str, lancer=...) -> str` (`gh run download`, rend le chemin).
  `Gh_indisponible(Exception)`.

- [ ] **Step 1: Write the failing tests** avec un faux `lancer` qui enregistre les arguments : `gh_pret` sans `gh` rend `(False, "…gh auth login…")` ; `visibilite` lit le JSON ; `declencher` construit `["gh","workflow","run",workflow,"--ref",ref,"-f","cle=valeur"]` ; `suivre` s'arrête sur `completed`, rend la conclusion, et rend `{"conclusion": "timeout"}` au-delà de `delai_s` ; `telecharger` rend le chemin du fichier trouvé.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py deport_github` — attendu : échec.
- [ ] **Step 3: Implement** le module ; aucun appel réseau dans les tests ; jamais le contenu d'un token dans une sortie.
- [ ] **Step 4: Run** — attendu : passent.
- [ ] **Step 5: Commit** `Déport : enveloppe de gh (déclencher, suivre, télécharger)`

### Task 6: Génération du workflow GitHub

**Files:**
- Create: `outils/workflow_github.py`
- Test: `tests/test_deport_workflow.py`

**Interfaces:**
- Consumes: `bureau.deport.ACTIONS`.
- Produces: `generer(nom: str, actions_github: list, commandes: dict, charge_heure: str = "03:00") -> str` (texte YAML : `on: push`, `workflow_dispatch`, `schedule` seulement si `charge` est présente, une tâche par action sur `ubuntu-latest`, étapes `actions/checkout`, la commande, et `actions/upload-artifact` pour `apk`) ; première ligne `# généré par MyIAFactory empreinte=<sha256 du reste>` ; `etat_du_fichier(chemin: Path, contenu_voulu: str) -> str` parmi `"absent"`, `"a_jour"`, `"a_valider"` (généré et différent), `"modifie_a_la_main"` (l'empreinte ne correspond plus au corps) ; `diff(ancien: str, nouveau: str) -> str` (diff unifié).

- [ ] **Step 1: Write the failing tests** — `charge` absente → pas de `schedule` ; `charge_heure="03:00"` donne `cron: '0 3 * * *'` ; chaque action déportée produit une tâche et `apk` un `upload-artifact` ; aucun `runs-on` autre que `ubuntu-latest` ; la même entrée donne le même texte (déterministe) ; fichier édité à la main → `"modifie_a_la_main"` ; changement de case → `"a_valider"` ; une commande vide pour une action déportée lève `ValueError("… commande …")`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py deport_workflow` — attendu : échec.
- [ ] **Step 3: Implement** sans dépendance YAML (génération par gabarit texte) ; la commande par défaut d'`apk` est `./gradlew assembleDebug` quand le projet a un `gradlew`, fournie par l'appelant dans `commandes`.
- [ ] **Step 4: Run** — attendu : passent.
- [ ] **Step 5: Commit** `Déport : génération et empreinte du workflow GitHub`

### Task 7: Aperçu, validation et push du workflow

**Files:**
- Create: `outils/deport_depot.py`
- Modify: `bureau/serveur.py` (deux routes), `bureau/web/ui/deport.js` (aperçu et bouton)
- Test: `tests/test_deport_depot.py`, `bureau/web/tests/deport-apercu.test.js`

**Interfaces:**
- Consumes: `workflow_github.generer/etat_du_fichier/diff`, `moteur.git_sur.verrou` et `executer`, `github_actions.gh_pret`.
- Produces: `apercu(dossier: str, reglages: dict) -> dict` (`{"etat", "diff", "chemin", "empreinte"}`) ; `appliquer(dossier: str, empreinte: str, reglages: dict, executer=...) -> dict` (refuse si l'empreinte validée n'est plus celle du contenu voulu ; refuse `modifie_a_la_main` ; écrit le fichier, commit sur la branche `deport/workflow`, pousse cette branche — jamais la principale) ; routes `GET /api/deport/apercu` et `POST /api/deport/appliquer` (corps `{"empreinte"}`).

- [ ] **Step 1: Write the failing tests** (dépôt git temporaire) — l'aperçu d'un projet sans fichier dit `absent` avec le diff complet ; `appliquer` avec la bonne empreinte crée le fichier sur `deport/workflow` et ne touche pas la branche courante ; une empreinte périmée est refusée ; `modifie_a_la_main` est refusé sans rien écrire ; côté interface : le diff s'affiche et le bouton « Valider et pousser » envoie l'empreinte affichée.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py deport_depot` et le test JS — attendu : échec.
- [ ] **Step 3: Implement** ; les opérations git passent par `moteur.git_sur.executer` (verrou par dépôt).
- [ ] **Step 4: Run** — attendu : passent.
- [ ] **Step 5: Commit** `Déport : aperçu, validation et push du workflow sur une branche de travail`

### Task 8: Point d'entrée `lancer.py deporter` et dépendances

**Files:**
- Create: `outils/deporter.py`
- Modify: `lancer.py` (routage de `deporter`, et de `tests` quand le lieu de `tests` est `github`), `outils/campagne.py` (rien si possible)
- Test: `tests/test_deporter.py`

**Interfaces:**
- Consumes: `deport.lieu_effectif/a_attendre`, `reglages.charger`, `github_actions.*`, `campagne.executer`.
- Produces: `main(argv: list, executer_poste=campagne.executer, gh=github_actions) -> int` pour `lancer.py deporter <type> [--dossier D] [--sans-attendre] [-- <commande locale>]` ; `ecrire_attente(id_: str, action: str, produit: str, lieu: str) / retirer_attente(id_: str)` (fichier `~/MyIAFactory/deport-en-cours/<id>.json` = `{action, attend, lieu, depuis, battement}`, battement mis à jour chaque minute) ; codes de retour : 0 réussi, 1 action échouée, 3 `--sans-attendre` refusé, 4 `gh` indisponible, 5 amont échoué (dépendance), 6 changements non poussés refusés.

- [ ] **Step 1: Write the failing tests** (faux `gh` et faux `executer_poste`) — lieu `poste` : la commande locale part par `campagne.executer` ; lieu `github` : pousse le commit courant (refus code 6 si des changements ne sont pas poussés et sans accord), déclenche, suit, rend 0/1 selon la conclusion ; `tests` au poste avec `apk` chez GitHub : attend l'exécution d'`apk` du commit, télécharge l'artefact, puis lance les tests ; `apk` échoué → code 5 sans lancer les tests ; deux appels pour le même commit ne déclenchent qu'une exécution (réutilise `execution_du_commit`) ; `gh` indisponible → code 4 et le message « gh auth login » ; le fichier d'attente est écrit pendant l'attente et retiré à la fin, même en cas d'exception.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py deporter` — attendu : échec.
- [ ] **Step 3: Implement** ; aucune bascule silencieuse vers le poste : en cas de réseau absent ou de quota atteint, imprimer la proposition (« relance avec `--poste` après accord du Directeur ») et rendre un code non nul.
- [ ] **Step 4: Run** — attendu : passent, et `py -3.12 outils/tests_paralleles.py campagne` toujours vert.
- [ ] **Step 5: Commit** `Déport : lancer.py deporter, avec attente des dépendances`

### Task 9: L'attente n'est pas un blocage

**Files:**
- Modify: `moteur/detache.py` (`attendre`, vers la ligne 613), `bureau/avancement.py` (nouvel état), `bureau/web/ui/texte.js`
- Test: `tests/test_deport_attente.py`, `tests/test_bureau_avancement.py` (ajouter), `bureau/web/tests/avancement.test.js` (ajouter)

**Interfaces:**
- Consumes: le fichier `~/MyIAFactory/deport-en-cours/<id>.json` (Task 8).
- Produces: `moteur.detache.attente_deportee(dossier_etat: Path, maintenant: datetime, delai_s: int = 180) -> dict | None` (vivante si le battement a moins de `delai_s`) ; dans `attendre`, une attente vivante repousse l'échéance `delai_s` du garde-fou ; `avancement.pour_la_tache` gagne l'état `attente_deportee` avec le texte `en attente de l'APK (GitHub, depuis N min)` et la durée type.

- [ ] **Step 1: Write the failing tests** — un agent sans action depuis 45 min mais dont le fichier d'attente a un battement récent n'est pas arrêté ; battement périmé de plus de 3 min → le garde-fou s'applique ; la fiche dit « en attente de l'APK (GitHub, depuis 12 min) » ; après le seuil d'alerte, l'état passe en alerte.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py deport_attente bureau_avancement` — attendu : échec.
- [ ] **Step 3: Implement** ; le moteur ne modifie jamais le fichier d'attente (un seul rédacteur : `deporter`).
- [ ] **Step 4: Run** — attendu : passent, plus le test JS.
- [ ] **Step 5: Commit** `Déport : l'attente d'une exécution distante n'arrête pas l'agent`

### Task 10: Consigne de départ des agents

**Files:**
- Modify: `orchestrateur/depart.py` (à côté de `tests_un_a_la_fois`), `orchestrateur/consignes.md` si la consigne y est reprise
- Test: `tests/test_orch_depart_deport.py`

**Interfaces:**
- Consumes: `LANCEUR_DE_TESTS` (le même `lancer.py`).
- Produces: `deport_consigne(lieux: dict) -> str` : vide si tout est au poste ; sinon dit, pour chaque action déportée, de la lancer par `python "<lancer.py>" deporter <type> --dossier <d> -- <commande>`, de pousser d'abord son travail, d'attendre le résultat, et de ne jamais la lancer directement ; `tests_un_a_la_fois` reste inchangée pour les actions au poste.

- [ ] **Step 1: Write the failing tests** — tout au poste : consigne vide (aucune régression de texte) ; `apk` chez GitHub : la consigne cite `deporter apk` et le chemin du lanceur ; le texte demande de pousser avant et d'accepter l'attente ; l'assemblage du message de départ l'inclut seulement quand non vide.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py orch_depart_deport orch_depart` — attendu : échec.
- [ ] **Step 3: Implement** et l'ajouter à l'assemblage du message de départ.
- [ ] **Step 4: Run** — attendu : passent.
- [ ] **Step 5: Commit** `Déport : la consigne de départ envoie les agents vers le lanceur déporté`

### Task 11: Résultats et consommation

**Files:**
- Create: `bureau/deport_conso.py`
- Modify: `bureau/serveur.py` (état du projet et vue des coûts), `bureau/web/ui/couts.js`, `bureau/web/ui/deport.js`
- Test: `tests/test_deport_conso.py`, `bureau/web/tests/deport-conso.test.js`

**Interfaces:**
- Consumes: `github_actions.visibilite`, sorties de `gh run list --json`.
- Produces: `cumuler(executions: list, mois: str) -> dict` (`{projet: {action: {"minutes": float, "executions": int}}}`, minutes facturées arrondies à la minute supérieure, Linux uniquement) ; `etat_quota(minutes_utilisees: float, quota: int | None, public: bool) -> dict` (`{"niveau": "ok"|"alerte"|"depasse", "restantes": int | None, "texte": str}` — alerte à 80 %, dépassé à 100 %, public : `ok` illimité) ; cache `~/MyIAFactory/deport-conso.json` (lecteur et rédacteur : `deport_conso.py`) ; l'état du bureau expose `deport.conso` et la vue des coûts affiche minutes par projet et par action ; si l'autorisation `user` de `gh` manque, le quota est `None` et le texte dit « estimation par les durées ; `gh auth refresh -h github.com -s user` pour le quota officiel ».

- [ ] **Step 1: Write the failing tests** — 79 % → `ok`, 80 % → `alerte`, 100 % → `depasse` avec la proposition de passer au poste ; dépôt public → pas de quota ; deux exécutions de 4 min 10 s comptent 5 min chacune ; quota inconnu → texte d'estimation ; un mois différent n'est pas cumulé ; l'interface affiche « 640 / 2 000 min ».
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py deport_conso` — attendu : échec.
- [ ] **Step 3: Implement** ; le rafraîchissement lit `gh` au plus une fois toutes les 5 min.
- [ ] **Step 4: Run** — attendu : passent, plus le test JS.
- [ ] **Step 5: Commit** `Déport : consommation GitHub et alerte de quota dans la vue des coûts`

### Task 12: Manuel et vérification de bout en bout

**Files:**
- Modify: `README.md` ou le manuel du bureau (là où `lecons_auto` est décrit), `CLAUDE.md` (une ligne : les agents déportés passent par `lancer.py deporter`)
- Test: `tests/test_deport_bout_en_bout.py`

**Interfaces:**
- Consumes: tout ce qui précède.

- [ ] **Step 1: Write the failing test** — avec un faux `gh` et un dépôt temporaire : réglage `apk: github`, `tests: poste` → l'aperçu du workflow est proposé, `appliquer` pousse la branche de travail, `deporter apk` déclenche et suit, `deporter tests` attend l'APK puis lance la commande locale, le fichier d'attente disparaît, la consommation est cumulée.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py deport_bout_en_bout` — attendu : échec tant que le câblage est incomplet.
- [ ] **Step 3: Implement** le câblage manquant et la documentation : défaut au poste, les cases, la validation du workflow, les secrets à saisir par le Directeur dans GitHub, la consommation, l'autorisation `user`.
- [ ] **Step 4: Run** `py -3.12 outils/tests_paralleles.py --touches`, puis la suite complète avant de pousser — attendu : tout vert.
- [ ] **Step 5: Commit** `Déport : documentation et essai de bout en bout`

---

## Auto-vérification

- **Couverture de la spec** : types et lieux (T1), portée globale + projet (T2), cases (T3-T4), workflow et validation avant push (T6-T7), point d'entrée et dépendances (T8), attente non confondue (T9), consigne des agents (T10), suivi de consommation, quota et alerte (T11), choix `serveur` grisé (T1, T4), refus de l'émulateur sur GitHub (T1, T4), détection public/privé (T5, T11), échec en amont, version du code, attente visible (T8, T9). La configuration SSH et l'exécution sur serveur sont hors de ce plan (étape 2 de la spec).
- **Cohérence des noms** : `valider_lieux`, `lieu_effectif`, `a_attendre`, `fixer_deport`, `etat_du_fichier`, `ecrire_attente` sont définis avant d'être utilisés.
- **Proportion** : un plan par tâche, sans corps de fonction ; les corps restent à écrire par le réalisateur.
