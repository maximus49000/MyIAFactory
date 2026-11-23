# Des tests rapides et peu coûteux : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** chaque campagne de tests lancée par la plateforme est mesurée et comparée à un budget propre au projet (sceau hors
du projet) ; au dépassement, le Directeur est alerté au bureau et la tâche « Accélérer les tests » lui est proposée ; chaque
agent reçoit la consigne « Des tests rapides et peu coûteux » ; l'installation fixe le budget et écrit les conventions ; le
dépôt MyIAFactory s'applique les mêmes règles.

**Architecture:** deux petits modules de stockage compatibles Python 3.9 (`bureau/tests_mesures.py` : le journal
`.factory/tests-mesures.jsonl` ; `bureau/tests_sceau.py` : `~/MyIAFactory/tests-sceau.json`) sont appelés **passivement** par
le lanceur (`outils/campagne.py`, `outils/deporter.py`). Une règle d'alerte **pure** (`bureau/tests_alerte.py`) est lue par le
moteur à son tour de boucle, seulement quand l'heure de modification du journal change, et pose la décision de projet
`tests_lents`. Le budget ne s'écrit que par un geste du Directeur (`reglages.fixer_tests`, appelé par le bureau ou par le
moteur en réponse à une décision), sceau d'abord, copie d'affichage dans `reglages.json` ensuite.

**Tech Stack:** Python 3.12 bibliothèque standard (plateforme), Python 3.9 pour ce qu'importe `deporter` ; JavaScript en
modules ES, `node --test` ; `unittest` par le lanceur.

**Spec:** `docs/superpowers/specs/2026-11-23-tests-performants-peu-couteux-design.md` (sections 5, 6 et 8 : décisions du
Directeur du 2026-11-23).

## Global Constraints

- **Exécution** : superpowers:subagent-driven-development, une tâche par implémenteur, dans l'ordre (T2 dépend de T1, T5 de
  T3 et T4, T9 de T3 et T5).
- **Règle R4 du Directeur** : pendant le travail, **seulement les tests touchés** (le module de la tâche) ; la suite complète
  **une fois, à la fin** (T11, par le contrôleur) ; **un seul passage RED** par test nouveau ; pas de relecture séparée d'un
  petit correctif tenu par un test, **sauf code sensible**. Sensible ici : tout ce qui **stocke le budget ou le sceau**
  (`bureau/tests_sceau.py`, `reglages.fixer_tests`, les réponses `budget_tests` / `tests_lents` du moteur qui écrivent le
  sceau) et tout ce qui **lance les commandes des agents** (`campagne.executer`, `campagne._lancer`, `deporter`).
- **Tests uniquement par le lanceur**, depuis Git bash : `py -3.12 outils/tests_paralleles.py <module>` ; JS :
  `py -3.12 lancer.py tests --dossier . -- node --test bureau/web/tests/<fichier>.test.js`. Une seule campagne à la fois
  sur le poste ; jamais `python -m unittest` ni `pytest` directement.
- **Des tests eux-mêmes économes** : purs ou sur dossier temporaire ; horloge, `maintenant`, chemins du sceau et du bureau
  **injectés** ; **aucun `sleep`**, aucun `bash`/`git`/`gh` réel ; un seul sous-processus dans tout le plan (le test de
  fumée de `_lancer`, T2, `sys.executable -c …`) ; fixtures partagées par classe (`setUpClass`) quand un dossier n'est que lu ;
  le moteur se teste en remplaçant `regles.lancer` / `regles._etat` (`unittest.mock.patch.object`), un seul test de bout en
  bout par tâche au plus. Chaque tâche annonce la durée attendue de ses modules ; au-delà du double, réduire avant de
  committer. Aucun test n'est ajouté à `tests/test_deporter.py` (149 s) ni à `tests/test_releve.py` (13 s).
- **Python** : 3.12 pour la plateforme ; `outils/deporter.py`, `outils/campagne.py` et tout ce qu'ils importent
  (`bureau/tests_mesures.py`, `bureau/tests_sceau.py`, `bureau/verrou_fichier.py`) restent **compatibles Python 3.9**
  (bibliothèque standard, pas de `X | Y`, pas de `match`) ; un test les analyse avec `ast.parse(..., feature_version=(3, 9))`.
- **Anti-objectif** : un dépassement ne change **jamais** le code de sortie d'une campagne d'agent (`lancer.py tests` rend le
  code de la commande, 3 si refusé sans attendre) ; une mesure ou une écriture du sceau qui échoue est **tue** et ne casse
  jamais la campagne. Aucun processus, démon ou appel de modèle de plus pour mesurer ou surveiller.
- **Valeurs du spec** : budget par défaut **300 s**, bornes **60 à 3 600 s** ; journal **2 000 lignes** au plus, ligne de plus
  de **2 Ko** ignorée, `commande` tronquée à **200** caractères ; alerte : **médiane des 3 dernières** campagnes complètes
  mesurées, ou la dernière **> 1,5 × budget** ; **> 1** campagne complète par tâche ; tests disparus : **> 2 %** ; partielle
  > budget ; une alerte ouverte par motif, qui ne revient qu'**aggravée de 20 %** ou **après un changement de budget** ;
  migration : première campagne de **plus de 60 s** ; budget proposé `max(300, référence × 1,25 arrondie à la minute)`.
- **Ce que les agents lisent ne nomme jamais le sceau** (ni `tests-sceau` ni son chemin dans un message de départ).
- **Décisions du Directeur (section 8)** : la tâche « Accélérer les tests » est **proposée** (décision `tests_lents`, case
  « Désormais sans me demander » = `tests.tache_auto`, faux par défaut), jamais créée d'office sans cet accord ; le budget fait
  foi dans le sceau, `reglages.json` n'en est qu'une copie, un écart donne une alerte ; `--strict` de `tests_paralleles.py`
  (code 5) **n'est branché nulle part** avant la fusion de `tests-rapides`, ensuite un crochet `pre-push` **facultatif** ;
  pas de CI.
- **Commits** : chemins explicites, messages en français préfixés « Tests rapides : », attribution de la session ; **ne rien
  pousser**. Textes affichés en français, avec les guillemets « » et les espaces du spec.

## Review Focus

1. **Sortie d'une commande d'agent énorme, binaire ou non UTF-8, ou campagne interrompue (Ctrl-C)** : le relais ne garde que
   les 4 096 derniers octets en mémoire, ne lève jamais sur le décodage, rend le code, et le verrou est libéré ; une
   campagne interrompue n'écrit pas de ligne (T2 : `test_relayer_borne_la_memoire_et_tolere_l_octet_invalide`,
   `test_interruption_libere_le_verrou_sans_ligne`).
2. **Deux écritures du sceau au même moment** (deux campagnes, ou le moteur qui note une alerte pendant que le lanceur compte)
   : aucune incrémentation perdue (T1 : `test_modifier_sous_verrou_ne_perd_aucune_incrementation`, 8 fils, sans `sleep`).
3. **Journal ou sceau abîmés** (tronqué, BOM, ligne de 50 Ko, JSON invalide, fichier remplacé par un dossier) : la lecture
   ne lève jamais, la campagne tourne ; un sceau illisible n'est **jamais réécrit à l'aveugle** (il garde les autres projets)
   (T1 : `test_lire_tolere_un_journal_abime`, `test_sceau_illisible_n_est_pas_ecrase`).
4. **Le même projet par des chemins différents** (sous-dossier `app/`, copie de travail `.claude/worktrees/x` rangée sous le
   projet, casse ou préfixe `\\?\` sous Windows) : rangé sous le projet enregistré le plus long ; un dossier non enregistré
   n'écrit rien (T1 : `test_projet_enregistre_resout_sous_dossier_copie_et_casse`).
5. **Portée** : `npx vitest run` et ` npx  vitest  run ` sont la même commande ; `npx vitest run --reporter=dot` ou
   `npx vitest run src/a.test.ts` sont **partielles** ; sans commande enregistrée, rien n'est jamais « complète » (T1 :
   `test_portee_compare_la_commande_normalisee`).

## Cartographie des fichiers

- Créer : `bureau/verrou_fichier.py`, `bureau/tests_mesures.py`, `bureau/tests_sceau.py`, `bureau/tests_alerte.py`,
  `bureau/tests_cout.py`, `installation/conventions_tests.py`, `installation/mesure_tests.py`, `outils/crochets/pre-push`.
- Modifier : `outils/campagne.py`, `outils/deporter.py`, `outils/tests_paralleles.py`, `bureau/reglages.py`,
  `bureau/serveur.py`, `bureau/demandes.py`, `bureau/releve.py`, `bureau/web/ui/directeur.js`, `bureau/web/ui/actions.js`,
  `bureau/web/ui/decisions.js`, `bureau/web/ui/facturation.js`, `orchestrateur/depart.py`, `orchestrateur/outil.py`,
  `orchestrateur/consignes.md`, `moteur/rapport.py`, `moteur/regles.py`, `moteur/boucle.py`, `moteur/cloud.py`,
  `installation/mise_en_place.py`, `installation/outil.py`, `skills/installer/SKILL.md`, `CLAUDE.md`, `.gitignore`.
- Tests nouveaux : `tests/test_tests_mesures.py`, `tests/test_tests_sceau.py`, `tests/test_campagne_mesure.py`,
  `tests/test_tests_budget.py`, `tests/test_tests_alerte.py`, `tests/test_moteur_tests_lents.py`,
  `tests/test_tests_consigne.py`, `tests/test_tests_cout.py`, `tests/test_inst_tests.py`, `tests/test_tests_paralleles.py` ;
  JS : `bureau/web/tests/budget-tests.test.js`, `bureau/web/tests/tests-lents.test.js`,
  `bureau/web/tests/facturation-tests.test.js`.
- Docs : `docs/deport.md`, `docs/orchestrateur.md`, `docs/installation.md`.

---

### Task 1: Le journal et le sceau (stockage, Python 3.9)

**Files:** Create `bureau/verrou_fichier.py`, `bureau/tests_mesures.py`, `bureau/tests_sceau.py` ; Modify `bureau/reglages.py`
(le verrou déménage) ; Test `tests/test_tests_mesures.py` (≈ 0,3 s), `tests/test_tests_sceau.py` (≈ 0,4 s).

**Interfaces:**
- Produces (`bureau/verrou_fichier.py`) : `verrou_fichier(chemin)` (gestionnaire de contexte), le corps exact de
  `reglages._verrou_fichier` avec `VERROU_ATTENTE_S = 10`, `VERROU_PERIME_S = 60` ; `reglages._verrou_fichier` devient un
  alias (`from .verrou_fichier import verrou_fichier as _verrou_fichier`), comportement inchangé.
- Produces (`bureau/tests_sceau.py`) :
  - `SCEAU = Path("~/MyIAFactory/tests-sceau.json").expanduser()` ; `BUDGET_DEFAUT_S = 300` ; `BUDGET_MIN_S, BUDGET_MAX_S = 60, 3600`.
  - `ENTREE_VIDE = {"budget_s": 300, "commande_complete": None, "reference_s": None, "campagnes": 0, "cumul_s": 0.0,
    "derniers_nb_tests": None, "tache_auto": False, "commande_refusee": None, "alertes": {}, "maj": None}`.
  - `class SceauIllisible(Exception)`.
  - `lire(id_projet: str, sceau=SCEAU) -> dict` : l'entrée complétée par `ENTREE_VIDE` ; absente ou illisible : une copie de
    `ENTREE_VIDE` ; ne lève jamais.
  - `modifier(id_projet: str, changer: Callable[[dict], None], sceau=SCEAU, maintenant: Callable[[], str] = _maintenant) -> dict`
    : sous `verrou_fichier(sceau)`, relit, applique `changer` à l'entrée (complétée), pose `maj`, écrit par fichier temporaire
    puis `os.replace`, rend l'entrée. Sceau présent mais illisible (JSON invalide, pas un objet) : lève `SceauIllisible` sans
    rien écrire. Peut lever `TimeoutError` / `OSError` : les appelants du lanceur les taisent.
- Produces (`bureau/tests_mesures.py`) :
  - `BUREAU = Path("~/MyIAFactory/bureau.json").expanduser()` ; `NOM_JOURNAL = "tests-mesures.jsonl"` ;
    `MAX_LIGNES = 2000` ; `MAX_OCTETS_LIGNE = 2048` ; `MAX_COMMANDE = 200` ; `LIEUX = ("poste", "github", "cloud", "serveur")` ;
    `SOURCES = ("mesure", "declare")` ; `PORTEES = ("complete", "partielle")` ; `SEUIL_BAISSE = 0.02`.
  - `projet_enregistre(dossier, bureau=BUREAU) -> Optional[Tuple[str, Path]]` : `(id, racine)` du projet du bureau dont la
    racine (dossier de `reglages.json`, ou parent de `.factory`) contient `dossier` — le plus long ; comparaison par
    `bureau.deport_types._norme` ; `id` = celui de l'entrée, sinon la règle de `reglages._id_par_defaut` (doublons suffixés
    `-2`, `-3` comme `lire_bureau`). Aucun : `None`. Ne lève jamais.
  - `journal_de(racine) -> Path` = `<racine>/.factory/tests-mesures.jsonl`.
  - `ligne(*, lieu, source, tache, commande, portee, duree_s, attente_s, code, nb_tests=None, sortie_octets=None, n=None,
    run=None, t) -> dict` : la forme du spec (§ 5.2), `commande` tronquée à 200, `duree_s`/`attente_s` arrondis au dixième ;
    `n` (numéro de campagne mesurée, donné par le sceau) et `run` (identifiant d'exécution GitHub) seulement s'ils ne sont pas
    `None`. Lève `ValueError` si `lieu`, `source` ou `portee` sont hors de leurs listes.
  - `ajouter(chemin: Path, ligne: dict) -> None` : ajoute une ligne JSON ; au-delà de `MAX_LIGNES`, réécrit par fichier
    temporaire en gardant les 2 000 dernières. Peut lever `OSError`.
  - `lire(chemin: Path) -> List[dict]` : lignes valides seulement (JSON objet, ≤ 2 Ko, `lieu`/`source`/`portee` connus,
    `duree_s` nombre ≥ 0) ; absent ou illisible : `[]` ; ne lève jamais.
  - `nb_tests_de(fin: str) -> Optional[int]` : sur les dernières lignes d'une sortie : unittest `Ran N tests` ; pytest
    (somme des nombres devant `passed`, `failed`, `error(s)`, `skipped` de la dernière ligne de résumé) ; vitest
    `Tests  N passed (T)` → `T` ; jest `Tests: … T total` → `T` ; sinon `None`.
  - `meme_commande(a: str, b: Optional[str]) -> bool` : égalité après `" ".join(x.split())` ; `b` nul → faux.
  - `noter_campagne(dossier, *, commande: str, duree_s, attente_s, code, fin="", octets=None, lieu="poste", tache=None,
    run=None, bureau=BUREAU, sceau=SCEAU, maintenant=_maintenant) -> Optional[dict]` : projet non enregistré → `None` ;
    `run` déjà présent dans les 50 dernières lignes → `None` ; sinon, sous `tests_sceau.modifier` : `campagnes += 1`,
    `cumul_s += duree_s`, `n = campagnes` ; pour une campagne `complete` verte avec `nb_tests`, `derniers_nb_tests` prend
    la nouvelle valeur **sauf** baisse de plus de 2 % (il reste alors à l'ancienne : l'alerte tient jusqu'à « C'est voulu ») ;
    `portee = "complete" if meme_commande(commande, entree["commande_complete"]) else "partielle"` ; puis `ajouter`. Rend la
    ligne. Toute exception (OSError, ValueError, TimeoutError, SceauIllisible) → `None`.
  - `noter_declarations(dossier, lieu, tache, declarations: list, bureau=BUREAU, maintenant=_maintenant) -> int` : une ligne
    `source: "declare"` par déclaration valide (`portee` agent `touches` → `partielle`), sans toucher au sceau ; rend le nombre
    écrit ; ne lève jamais.

- [ ] **Step 1: Write the failing tests** (`tests/test_tests_mesures.py`, `tests/test_tests_sceau.py`), dossiers temporaires
  créés une fois par classe, `bureau.json` et sceau écrits dans ce dossier, `maintenant` fixe :
  - `test_modules_compatibles_python_3_9` : `ast.parse(source, feature_version=(3, 9))` pour les trois modules.
  - `test_verrou_reglages_inchange` : `reglages._verrou_fichier is verrou_fichier.verrou_fichier`.
  - `test_projet_enregistre_resout_sous_dossier_copie_et_casse` : `<p>/app`, `<p>/.claude/worktrees/x`, `<P>` en majuscules
    sous Windows → `("p-id", <p>)` ; un dossier hors bureau → `None` ; deux projets imbriqués → le plus long ; les `id`
    égalent ceux de `reglages.lire_bureau` pour le même fichier (concordance).
  - `test_ligne_forme_du_spec` : clés exactes du spec, `commande` de 300 caractères → 200, `lieu="ailleurs"` → `ValueError`.
  - `test_rotation_garde_les_2000_dernieres` : 2 001 ajouts (fichier préparé à 2 000 lignes d'un coup, puis un `ajouter`)
    → 2 000 lignes, la première partie.
  - `test_lire_tolere_un_journal_abime` : BOM, ligne tronquée, ligne de 50 Ko, `[1, 2]`, `duree_s: -1`, dossier à la place
    du fichier → seules les lignes valides, aucune exception.
  - `test_nb_tests_des_sorties_types` : `"Ran 318 tests in 4.2s\n\nOK"` → 318 ; `"==== 3 failed, 315 passed, 2 skipped in 9.1s ===="`
    → 320 ; `" Tests  306 passed (306)"` → 306 ; `"Tests:       1 failed, 11 passed, 12 total"` → 12 ; `"bonjour"` → `None`.
  - `test_portee_compare_la_commande_normalisee` (Review Focus 5).
  - `test_noter_campagne_numerote_et_compte` : deux campagnes → `n` 1 puis 2, `campagnes == 2`, `cumul_s` additionné ;
    même `run` deux fois → une seule ligne ; dossier non enregistré → `None`, ni journal ni sceau créés.
  - `test_reference_nb_tests_ne_suit_pas_une_baisse` : 318 puis 306 (baisse 3,8 %) → `derniers_nb_tests == 318` ; 318 puis
    315 (0,9 %) → 315.
  - `test_noter_campagne_tait_les_erreurs` : sceau illisible, journal en lecture seule (dossier à la place) → `None`, aucune
    exception.
  - `test_noter_declarations_sans_toucher_au_sceau` : 2 valides + 1 sans `duree_s` → 2 lignes `declare`, `portee` mappée ;
    sceau inchangé.
  - `test_lire_sceau_absent_ou_illisible_rend_les_defauts`, `test_sceau_illisible_n_est_pas_ecrase` (modifier lève
    `SceauIllisible`, contenu du fichier identique octet pour octet), `test_modifier_garde_les_autres_projets`,
    `test_modifier_sous_verrou_ne_perd_aucune_incrementation` (8 fils × 5 `modifier` → `campagnes == 40`).

- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_mesures test_tests_sceau` →
  ÉCHEC (modules absents).
- [ ] **Step 3: Implement** les trois modules selon les interfaces ; `reglages.py` importe le verrou.
- [ ] **Step 4: Run to verify they pass** : même commande, plus `test_reglages` (touché par le déménagement) → ok.
- [ ] **Step 5: Commit** : `git add bureau/verrou_fichier.py bureau/tests_mesures.py bureau/tests_sceau.py bureau/reglages.py
  tests/test_tests_mesures.py tests/test_tests_sceau.py` ; « Tests rapides : journal des campagnes et sceau du budget ».

### Task 2: La mesure passive au poste et sur GitHub (code sensible)

**Files:** Modify `outils/campagne.py`, `outils/deporter.py`, `installation/mise_en_place.py` (`BLOC_GITIGNORE`),
`moteur/cloud.py` (`ETAT_DU_MOTEUR`) ; Test `tests/test_campagne_mesure.py` (≈ 0,5 s, dont le seul sous-processus du plan ;
la vérification du bloc `.gitignore` y est aussi, plutôt que dans `test_inst_mise_en_place`, module de 38 s).

**Interfaces:**
- Consumes : `tests_mesures.noter_campagne` (T1).
- Produces (`outils/campagne.py`) :
  - `relayer(entree: BinaryIO, sortie: BinaryIO, garder: int = 4096, morceau: int = 65536) -> Tuple[int, str]` : copie
    `entree` vers `sortie` morceau par morceau (`flush` après chaque), rend `(octets, fin)` où `fin` est le décodage
    `utf-8`/`replace` des `garder` derniers octets.
  - `_lancer(commande, dossier, env=None) -> Tuple[int, int, str]` : `subprocess.Popen` (sous Windows `shell=True` avec
    `list2cmdline`, comme avant), `stdout=PIPE`, `stderr=STDOUT`, relayé vers `sys.stdout.buffer` par `relayer` ; rend
    `(code, octets, fin)`.
  - `executer(commande, dossier=None, attendre=True, verrou=VERROU, lister=processus, dormir=time.sleep, dire=print,
    lancer=_lancer, attentes=ATTENTES, env=None, horloge=time.monotonic, noter=None) -> int` : `attente_s` = de l'appel à la
    prise du verrou, `duree_s` = de la prise du verrou à la fin de la commande ; `lancer` peut rendre un `int` (anciens
    appelants et tests) ou `(code, octets, fin)` ; après la commande, `noter(racine, commande=" ".join(commande),
    duree_s=…, attente_s=…, code=…, fin=…, octets=…, tache=os.environ.get(VARIABLE_TACHE) or None)` dans un
    `try/except Exception: pass` ; `noter` nul → `tests_mesures.noter_campagne`. Rend **toujours** le code de la commande
    (3 si refusé). `KeyboardInterrupt` pendant la commande : verrou libéré, pas de ligne, l'exception remonte.
- Produces (`outils/deporter.py`) : `_noter_le_run(c, run, reussi: bool, noter=None) -> None` appelé dans `_sur_github`
  quand `sur_github and action == "tests"`, juste avant le `return 0 if reussi else 1` : `noter(c["dossier"],
  commande=" ".join(<commande après -->) or c["catalogue"]["tests"].get("commande") or "tests", duree_s=run.get("duree_s")
  or 0, attente_s=0, code=0 if reussi else 1, lieu="github", run=run.get("id"))`, erreurs tues ; `main(..., noter=None)`
  le passe par `contexte["noter"]`. Codes de sortie de `deporter` inchangés.
- `BLOC_GITIGNORE` gagne `".factory/tests-mesures.jsonl"` ; `ETAT_DU_MOTEUR` gagne `tests-mesures\.jsonl`.

- [ ] **Step 1: Write the failing tests** (`tests/test_campagne_mesure.py`, verrou et attentes en dossier temporaire,
  `lister=lambda: []`, `dormir` qui avance une horloge factice, `noter` = enregistreur) :
  - `test_executer_mesure_l_execution_sans_l_attente` : horloge `[0, 35, 35, 447.6]` (appel, verrou pris, début, fin) →
    `attente_s == 35`, `duree_s == 412.6`, code rendu tel quel.
  - `test_executer_ancien_lancer_entier` : `lancer=lambda c, d: 0` → `noter` appelé avec `octets=None`, `fin=""`.
  - `test_depassement_ne_change_jamais_le_code` : `noter` qui lève → code 0 rendu ; code 1 de la commande → 1.
  - `test_refus_sans_attendre_ne_note_rien` : verrou pris par un pid vivant (`vivant` injecté) → 3, `noter` jamais appelé.
  - `test_interruption_libere_le_verrou_sans_ligne` : `lancer` qui lève `KeyboardInterrupt` → exception remontée, verrou
    absent, `noter` jamais appelé.
  - `test_relayer_borne_la_memoire_et_tolere_l_octet_invalide` : entrée `BytesIO` de 10 Mo terminée par
    `b"\xff\xfeRan 3 tests\n"` → octets exacts, `fin` ≤ 4 096 caractères et finit par `"Ran 3 tests\n"`, sortie identique à
    l'entrée.
  - `test_lancer_reel_relaie_sortie_et_erreurs` (seul sous-processus) : `[sys.executable, "-c", "import sys;
    print('Ran 2 tests'); print('x', file=sys.stderr); sys.exit(4)"]` → code 4, `"Ran 2 tests"` dans `fin`.
  - `test_github_note_le_run_une_fois` : `_noter_le_run({"dossier": d, "catalogue": {"tests": {"commande": "npm test"}},
    …}, {"id": 7, "duree_s": 312}, True, noter=enregistreur)` → `lieu="github"`, `run=7`, `code=0`, `duree_s=312`.
  - `test_campagne_et_deporter_compatibles_3_9` : `ast.parse(..., feature_version=(3, 9))` sur `campagne.py` et `deporter.py`.
  - `test_journal_hors_depot` : `".factory/tests-mesures.jsonl"` dans `mise_en_place.BLOC_GITIGNORE` et
    `cloud.ETAT_DU_MOTEUR.match(".factory/tests-mesures.jsonl")`.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_campagne_mesure` → ÉCHEC.
- [ ] **Step 3: Implement** selon les interfaces.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_campagne_mesure test_campagne` → ok
  (`test_campagne` existant reste vert sans modification).
- [ ] **Step 5: Commit** : `git add outils/campagne.py outils/deporter.py installation/mise_en_place.py moteur/cloud.py
  tests/test_campagne_mesure.py` ; « Tests rapides : le lanceur mesure chaque campagne (poste et GitHub) ».

### Task 3: Le budget au bureau (code sensible)

**Files:** Modify `bureau/reglages.py`, `bureau/serveur.py`, `bureau/web/ui/directeur.js` ; Test `tests/test_tests_budget.py`
(≈ 0,4 s), `bureau/web/tests/budget-tests.test.js` (≈ 0,3 s).

**Interfaces:**
- Consumes : `tests_sceau.lire`, `tests_sceau.modifier`, `tests_mesures.projet_enregistre` (T1).
- Produces (`bureau/reglages.py`) :
  - `DEFAUTS["tests"] = {"budget_s": 300, "commande_complete": None, "tache_auto": False}` ; `charger` complète la clé
    (un `tests` partiel garde les défauts manquants) et la valide : `budget_s` entier 60–3 600, `commande_complete` texte
    ≤ 200 ou nul, `tache_auto` booléen ; sinon `ReglagesInvalides` (« Réglages : « tests.budget_s » doit être un entier de 60
    à 3600 (secondes). »).
  - `fixer_tests(chemin, id_projet: Optional[str], valeurs: dict, sceau=tests_sceau.SCEAU) -> dict` : valeurs admises
    `budget_s`, `commande_complete`, `reference_s`, `tache_auto` (mêmes bornes ; autre clé → `ValueError`) ; écrit **d'abord**
    le sceau (`tests_sceau.modifier`, `alertes` vidées si `budget_s` change), **puis** la copie `tests` de `reglages.json`
    (`_ecrire_cle`, sans `reference_s`) ; `id_projet` nul (projet non enregistré) : la copie seule. Rend les réglages rechargés.
    `SceauIllisible` → `ReglagesInvalides("Le sceau des tests est illisible (<chemin>) : rien n'est changé.")`.
  - `ecart_tests(regl: dict, entree: dict) -> Optional[dict]` : `{"reglages_s", "sceau_s"}` si `regl["tests"]["budget_s"]`
    diffère de `entree["budget_s"]`, sinon `None`.
- Produces (`bureau/serveur.py`) : POST des réglages accepte `{"tests": {...}}` (branche comme `lecons_auto`) →
  `reglages.fixer_tests(projet.chemin_reglages, <id>, corps["tests"])` ; l'état du projet publie
  `e["tests"] = {"budget_s", "commande_complete", "tache_auto"}` **lus dans le sceau** (copie si non enregistré) et
  `e["tests"]["ecart"] = reglages.ecart_tests(...)`. `<id>` : `tests_mesures.projet_enregistre(dossier du projet)[0]`.
- Produces (`bureau/web/ui/directeur.js`) : `demandeBudgetTests(minutes) -> {tests: {budget_s}}` (minutes entières 1–60 ;
  hors bornes → `null`), `demandeTacheAuto(coche) -> {tests: {tache_auto}}`, `partieBudgetTests(ctx)` : champ « Budget des
  tests (minutes) », case « Désormais, créer la tâche « Accélérer les tests » sans me demander », et, si `e.tests.ecart`,
  la ligne « Le budget des tests a été modifié hors du bureau (<10 min> au lieu de <5 min>). ».

- [ ] **Step 1: Write the failing tests** :
  - `test_defauts_tests_et_bornes` : réglages sans `tests` → `{"budget_s": 300, "commande_complete": None, "tache_auto":
    False}` ; `{"tests": {"budget_s": 59}}` et `3601` et `"300"` → `ReglagesInvalides` ; `{"tests": {"budget_s": 600}}` →
    défauts complétés.
  - `test_fixer_tests_ecrit_le_sceau_puis_la_copie` : sceau et réglages en dossier temporaire → les deux à 600 ; un
    `os.replace` qui échoue pour la copie (patch) laisse le sceau à 600 (le sceau fait foi).
  - `test_changer_le_budget_vide_les_alertes` : `alertes` non vides → `{}` après un nouveau budget ; même budget → gardées.
  - `test_fixer_tests_refuse_cle_inconnue_et_sceau_illisible`.
  - `test_ecart_tests` : copie 600, sceau 300 → `{"reglages_s": 600, "sceau_s": 300}` ; égaux → `None`.
  - `test_serveur_publie_le_budget_du_sceau` : `Projet` du bureau sur un dossier temporaire (comme les tests existants de
    `serveur`, sans lancer de serveur HTTP), copie trafiquée à 600, sceau 300 → `e["tests"]["budget_s"] == 300`, `ecart` non nul.
  - JS `budget-tests.test.js` : `demandeBudgetTests(5)` → `{tests: {budget_s: 300}}` ; `0` et `61` → `null` ;
    `demandeTacheAuto(true)` ; le texte d'écart exact.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_budget` puis
  `py -3.12 lancer.py tests --dossier . -- node --test bureau/web/tests/budget-tests.test.js` → ÉCHEC.
- [ ] **Step 3: Implement** selon les interfaces.
- [ ] **Step 4: Run to verify they pass** : les deux commandes, plus `test_reglages` → ok.
- [ ] **Step 5: Commit** : `git add bureau/reglages.py bureau/serveur.py bureau/web/ui/directeur.js tests/test_tests_budget.py
  bureau/web/tests/budget-tests.test.js` ; « Tests rapides : le budget des tests, sceau et copie, réglé au bureau ».

### Task 4: La règle d'alerte (pure)

**Files:** Create `bureau/tests_alerte.py` ; Test `tests/test_tests_alerte.py` (≈ 0,05 s).

**Interfaces:**
- Produces :
  - `MOTIFS = ("suite_longue", "suite_relancee", "tests_disparus", "partielle_longue", "budget_modifie", "mesures_disparues")`.
  - `VERDICTS = {"suite_longue": ("accelerer", "relever", "plus_tard"), "partielle_longue": ("accelerer", "relever",
    "plus_tard"), "suite_relancee": ("vu",), "tests_disparus": ("voulu", "plus_tard"), "budget_modifie": ("retablir",
    "relever"), "mesures_disparues": ("vu",)}`, écrit comme un littéral compatible JSON (guillemets doubles, listes) entre
    les lignes `# VERDICTS:début` et `# VERDICTS:fin` (T6 le relit pour sa concordance) ; `ACCELERABLES = ("suite_longue",
    "partielle_longue")`.
  - `duree_en_clair(s: float) -> str` : `45` → « 45 s », `300` → « 5 min », `241` → « 4 min 01 s », `747` → « 12 min 27 s ».
  - `alertes(mesures: List[dict], entree: dict, budget_copie_s: Optional[int], titres: Dict[str, str]) -> List[dict]` :
    candidates `{"motif", "texte", "budget_s", "valeur", "cle", "mesure_s"?, "tache"?}` ; seules les lignes
    `source == "mesure"` comptent (une déclaration ne déclenche jamais) ; `cle` = motif, ou `suite_relancee:<tâche>`.
    1. `suite_longue` : au moins 3 complètes → médiane des 3 dernières > budget (`valeur` = médiane) ; ou la dernière
       complète > 1,5 × budget (`valeur` = sa durée).
    2. `suite_relancee` : par tâche non nulle, plus d'une complète (`valeur` = leur nombre).
    3. `tests_disparus` : dernière complète verte avec `nb_tests` < `derniers_nb_tests` × 0,98 (`valeur` = l'écart).
    4. `partielle_longue` : dernière partielle > budget.
    5. `budget_modifie` : `budget_copie_s` non nul et différent du sceau.
    6. `mesures_disparues` : `entree["campagnes"] > 0` et (aucune ligne numérotée, ou plus grand `n` < `campagnes`, ou un
       trou dans les `n` présents).
  - Textes exacts (spec § 5.2 et § 5.5, durées par `duree_en_clair`) : motif 1 « Les tests de ce projet dépassent leur
    budget : la suite complète prend <12 min 27 s> (médiane des 3 dernières campagnes), pour un budget de <5 min>. Chaque
    campagne en plus coûte ce temps à un agent qui attend. » (sans « (médiane… ) » quand c'est la règle des 1,5) ; motif 2
    « La suite complète a été lancée <3> fois pour la tâche « <titre> » : la règle est une fois, à la fin. » ; motif 3 « La
    suite complète compte <12> tests de moins qu'à la campagne précédente (<318> → <306>), tous verts. Vérifiez qu'aucun
    test n'a été supprimé ou sauté pour gagner du temps. » ; motif 4 « Une campagne partielle a duré <7 min> : plus que le
    budget de la suite complète. » ; motif 5 « Le budget des tests a été modifié hors du bureau (<10 min> au lieu de
    <5 min>). » ; motif 6 « Des mesures de tests ont disparu du journal du projet. »
  - `a_poser(candidates: List[dict], ouvertes: Set[str], memoire: Dict[str, dict], budget_s: int) -> List[dict]` : écarte
    une `cle` déjà ouverte ; écarte une `cle` notée en mémoire `{valeur, budget_s}` avec le même budget et
    `valeur < ancienne × 1,2`.
  - `texte_de_la_tache(decision: dict) -> str` : la mesure, le budget, les morceaux `lents` s'il y en a, et la phrase « Rendez
    la suite plus rapide sans affaiblir ni supprimer aucune assertion. »

- [ ] **Step 1: Write the failing tests** (lignes fabriquées par `tests_mesures.ligne`) :
  `test_duree_en_clair`, `test_mediane_exige_trois_complete` (2 complètes à 400 s, budget 300 → rien),
  `test_mediane_au_dessus_du_budget` (290, 410, 420 → 410, texte exact avec « 6 min 50 s »), `test_un_poste_charge_ne_declenche_pas`
  (280, 290, 400 : médiane 290 et 400 < 450 → rien ; 280, 290, 900 : médiane 290 mais 900 > 450 → une alerte par la règle
  des 1,5, `valeur` 900, texte sans « médiane »),
  `test_suite_relancee_par_tache`, `test_tests_disparus_au_dela_de_2_pourcent` (318 → 312 rien ; 318 → 306 alerte, texte
  exact), `test_partielle_plus_longue_que_le_budget`, `test_declaration_ne_declenche_jamais` (cloud à 5 000 s),
  `test_budget_modifie_hors_du_bureau`, `test_mesures_disparues_trou_fin_et_vide` (n = 1,2,4 ; n max 3 < 5 ; aucune ligne avec
  `campagnes` 3 ; rotation normale 1 001–3 000 avec `campagnes` 3 000 → rien), `test_a_poser_anti_repetition` (ouverte →
  écartée ; 410 puis 480 (+17 %) → écartée ; 500 (+22 %) → posée ; budget changé → posée), `test_verdicts_couvrent_les_motifs`,
  `test_texte_de_la_tache_interdit_d_affaiblir`.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_alerte` → ÉCHEC.
- [ ] **Step 3: Implement** `bureau/tests_alerte.py`.
- [ ] **Step 4: Run to verify they pass** : même commande → ok.
- [ ] **Step 5: Commit** : `git add bureau/tests_alerte.py tests/test_tests_alerte.py` ; « Tests rapides : la règle d'alerte ».

### Task 5: La décision `tests_lents`, posée et répondue par le moteur (code sensible)

**Files:** Modify `bureau/releve.py`, `bureau/demandes.py`, `bureau/serveur.py` (`REPONSES_UNE_FOIS`),
`orchestrateur/outil.py` (`TYPES_DEMANDE`, `cmd_decision`), `orchestrateur/consignes.md`, `moteur/regles.py`,
`moteur/boucle.py` ; Test `tests/test_moteur_tests_lents.py` (≈ 1,5 s : tout par `patch.object(regles, "lancer")`, un seul
test de bout en bout sur un projet temporaire).

**Interfaces:**
- Consumes : `tests_alerte.alertes`, `a_poser`, `VERDICTS`, `ACCELERABLES`, `texte_de_la_tache` (T4) ; `tests_sceau`,
  `tests_mesures` (T1) ; `reglages.fixer_tests`, `reglages.charger` (T3).
- Produces :
  - `releve.DECISIONS_PROJET` gagne `"tests_lents"` ; le relevé exige pour elle `motif` ∈ `MOTIFS` et `budget_s` entier.
  - `cmd_decision` `poser` `tests_lents` : `motif` (∈ `MOTIFS`), `budget_s` (entier), `mesure_s` (nombre ou absent),
    `tache` (texte ou absent), `lents` (liste de 5 textes au plus) ; sinon `Refus`.
  - `demandes.CHAMPS["tests_lents"] = ("decision", "verdict")`, `FACULTATIFS["tests_lents"] = ("tache_auto",)`, ajoutée à
    `DEMANDES_V4`, `outil.TYPES_DEMANDE`, `serveur.REPONSES_UNE_FOIS` ; vérification : décision connue de ce genre, verdict ∈
    `VERDICTS[motif]`, `tache_auto` booléen et seulement avec `accelerer`. Ligne de `consignes.md` : « seul le moteur
    procédural pose `tests_lents` et y répond ; ne la traite pas toi-même ».
  - `regles.surveiller_les_tests(projet, etat, *, bureau=tests_mesures.BUREAU, sceau=tests_sceau.SCEAU) -> List[str]`
    (lignes de journal du moteur ; racine du projet = parent du dossier `.factory` de `projet.factory`) : rien si le projet
    n'est pas enregistré ou si `mtime` du journal égale
    `etat["tests_mtime"]` ; sinon lit le journal, l'entrée du sceau, la copie `tests.budget_s`, les décisions `tests_lents`
    ouvertes et les titres des tâches ; pour chaque `a_poser` : si le projet est le dépôt MyIAFactory (`racine` ==
    racine de la plateforme) → `lancer(projet, "anomalies", {"action": "ajouter", "titre": "Tests trop lents",
    "description": texte})` ; sinon si `motif ∈ ACCELERABLES` et `entree["tache_auto"]` → la tâche directement
    (`_accelerer`) ; sinon `lancer(projet, "decision", {"action": "poser", "portee": "projet", "genre": "tests_lents",
    …})` ; puis mémoire `alertes[cle] = {"valeur", "budget_s"}` dans le sceau. Toute erreur de lecture : rien, jamais d'exception.
  - `regles._accelerer(projet, decision: dict) -> None` : `lancer(projet, "actions", {"type": "fonctionnalite", "nature":
    "correction", "texte": "Accélérer les tests\n\n" + tests_alerte.texte_de_la_tache(decision)})` (le chemin existant d'une
    correction).
  - `regles._sur_tests_lents(projet, demande, etat)` enregistré dans `_SUR["tests_lents"]` : `accelerer` → `_accelerer`, et
    si `tache_auto` vrai → `reglages.fixer_tests(projet.fichier_reglages, id, {"tache_auto": True})` ; `relever` et
    `plus_tard` → rien d'autre (la mémoire garde la valeur : rappel à l'aggravation) ; `voulu` → sceau
    `derniers_nb_tests` = `nb_tests` de la dernière complète ; `retablir` → `fixer_tests(…, {"budget_s": <sceau>})` (la copie
    reprend la valeur du sceau) ; `vu` → rien ; toujours `lever` la décision et `_terminer` avec une phrase.
  - `boucle._tour_projet` appelle `self._surveiller_les_tests(projet, etat)` après `_quota` ; elle note au journal du moteur
    ce que rend `regles.surveiller_les_tests`, erreurs tues.

- [ ] **Step 1: Write the failing tests** (`tests/test_moteur_tests_lents.py`, `bureau.json`, sceau et journal en dossier
  temporaire de classe ; `regles.lancer` remplacé par un enregistreur qui rend `{"id": "d1"}`) :
  - `test_rien_sans_changement_du_journal` : deux appels, `mtime` identique → un seul passage de lecture (enregistreur vide
    la seconde fois).
  - `test_pose_tests_lents_avec_motif_et_texte` : trois complètes à 410 s → un `("decision", {"genre": "tests_lents",
    "motif": "suite_longue", "budget_s": 300, …})` ; la mémoire du sceau notée.
  - `test_tache_auto_cree_la_correction_sans_decision` : `tache_auto` vrai → un `("actions", {"type": "fonctionnalite",
    "nature": "correction", …})`, aucune décision ; et faux par défaut → une décision, aucune action.
  - `test_depot_myiafactory_passe_par_les_anomalies`.
  - `test_reponses` : `accelerer` (+ `tache_auto`) → action + `fixer_tests` ; `voulu` → `derniers_nb_tests` recalé ;
    `retablir` → copie = sceau ; `plus_tard` → seulement `lever` ; verdict hors `VERDICTS[motif]` → `Refus`.
  - `test_demande_verifiee_par_le_bureau` : `demandes.verifier` refuse `voulu` sur `suite_longue`, `tache_auto` avec
    `relever`, accepte `accelerer` + `tache_auto: true`.
  - `test_decision_posee_de_bout_en_bout` (le seul sur projet temporaire réel, base `tests.test_moteur_polyvalents.Base`) :
    `lancer decision poser tests_lents` valide, relevé valide (`releve` sans erreur), décision visible.
  - `test_consignes_nomment_tests_lents` : déjà couvert par `test_orch_consignes` (lancé à l'étape 4).
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_moteur_tests_lents` → ÉCHEC.
- [ ] **Step 3: Implement** selon les interfaces.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_moteur_tests_lents test_orch_consignes
  test_demandes` → ok.
- [ ] **Step 5: Commit** : `git add bureau/releve.py bureau/demandes.py bureau/serveur.py orchestrateur/outil.py
  orchestrateur/consignes.md moteur/regles.py moteur/boucle.py tests/test_moteur_tests_lents.py` ; « Tests rapides : le moteur
  alerte et propose « Accélérer les tests » ».

### Task 6: La carte « Tests trop lents » au bureau

**Files:** Modify `bureau/web/ui/actions.js`, `bureau/web/ui/decisions.js` ; Test `bureau/web/tests/tests-lents.test.js`
(≈ 0,3 s).

**Interfaces:**
- Consumes : la décision `tests_lents` (T5) ; `VERDICTS` (T4, recopiés en JS, test de concordance par lecture du `.py`) ;
  `partieBudgetTests` (T3) pour « Relever le budget ».
- Produces : `sortie.testsLents` dans le tri de `actions.js` ; `LIBELLES_TESTS = {accelerer: "Créer la tâche « Accélérer les
  tests »", relever: "Relever le budget", plus_tard: "Plus tard", voulu: "C'est voulu", retablir: "Garder le budget du
  bureau", vu: "Vu"}` ; `VERDICTS_TESTS` (copie de `tests_alerte.VERDICTS`) ; `demandeTestsLents(decision, verdict,
  tacheAuto = false) -> {type: "tests_lents", decision, verdict, tache_auto?}` (`tache_auto` seulement avec `accelerer`) ;
  `decisionTestsLents(ctx, d)` : le `texte`, un bouton par verdict du motif, la case « Désormais sans me demander » à côté de
  « Créer la tâche… » ; « Relever le budget » envoie la demande puis ouvre `partieBudgetTests`.
- [ ] **Step 1: Write the failing tests** : `demandeTestsLents` (avec / sans `tache_auto`, `tache_auto` ignoré hors
  `accelerer`), boutons par motif (motif `tests_disparus` → « C'est voulu », « Plus tard »), concordance `VERDICTS_TESTS` avec
  le dictionnaire lu dans `bureau/tests_alerte.py` (lecture du fichier, `JSON.parse` du littéral entre `# VERDICTS:début` et
  `# VERDICTS:fin`, après `VERDICTS = `).
- [ ] **Step 2: Run to verify they fail** : `py -3.12 lancer.py tests --dossier . -- node --test
  bureau/web/tests/tests-lents.test.js` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : la même commande, plus `bureau/web/tests/decisions.test.js` et
  `bureau/web/tests/actions.test.js` → ok.
- [ ] **Step 5: Commit** : `git add bureau/web/ui/actions.js bureau/web/ui/decisions.js
  bureau/web/tests/tests-lents.test.js` ; « Tests rapides : la carte des tests trop lents ».

### Task 7: La consigne de départ et le champ `tests` du rapport

**Files:** Modify `orchestrateur/depart.py`, `orchestrateur/outil.py`, `moteur/rapport.py`, `moteur/boucle.py` ; Test
`tests/test_tests_consigne.py` (≈ 0,2 s) ; une assertion ajustée dans `tests/test_orch_depart.py` si besoin (le test
`test_un_agent_local_passe_ses_tests_par_le_verrou_du_poste` doit rester vert **sans** changement).

**Interfaces:**
- Consumes : `tests_alerte.duree_en_clair` (T4) ; `tests_sceau.lire`, `tests_mesures.projet_enregistre`,
  `tests_mesures.noter_declarations` (T1).
- Produces (`orchestrateur/depart.py`) :
  - `SECTION_TESTS` : le texte exact du spec § 5.1, du titre `## Des tests rapides et peu coûteux` à la ligne `tests`
    (repris aussi par T9).
  - `tests_rapides(lieu: str, budget_s: int = 300) -> str` : `SECTION_TESTS`, puis la ligne du lieu. **local** (exacte) :
    « **Lance tes tests uniquement par le lanceur du poste** (une seule campagne de tests à la fois sur le poste : il attend son
    tour) : `python "<LANCEUR_DE_TESTS>" tests --dossier <dossier où lancer> -- <ta commande de test>`. Jamais une suite
    lancée directement. Le lanceur mesure chaque campagne ; la plateforme compare la suite complète au budget du projet
    (<duree_en_clair(budget_s)>). » ; **cloud** et **serveur** : « Ici, pas de lanceur : ta déclaration `tests` est la seule
    mesure. Elle est affichée au Directeur comme déclarée. » ; autre lieu → `ValueError`.
  - `tests_un_a_la_fois()` est **supprimée** ; `message(..., budget_tests_s=300)` et `message_lot(..., budget_tests_s=300)`
    ajoutent `tests_rapides(fiche["lieu"], budget_tests_s)` pour **tous** les lieux, à la place de l'ancienne section ; la
    condition `not in LIEUX_SANS_POSTE` ne garde plus que `deport`.
  - `orchestrateur/outil.py` : `_budget_du_depart(ctx) -> int` (sceau du projet enregistré, 300 au moindre souci) passé par
    `cmd_depart` et `_depart_d_un_lot`.
- Produces (`moteur/rapport.py`) : champ facultatif `tests` : `r["tests"]` = les entrées valides seulement
  (`{"commande": texte ≤ 200, "portee": "touches" | "complete", "duree_s": nombre ≥ 0, "code": entier}`, 20 au plus) ; une
  forme fautive est écartée, **jamais** une raison de refuser le rapport ; documenté dans la docstring.
- Produces (`moteur/boucle.py`) : dans `_retours_des_agents`, pour un agent **cloud** (`getattr(e, "branche", None)`) ou
  **serveur** (`getattr(e, "serveur", False)`) dont le rapport a des `tests` : `tests_mesures.noter_declarations(racine du
  projet, lieu, e.tache, e.rapport["tests"])`, erreurs tues. Un agent local n'est pas déclaré (il est mesuré).

- [ ] **Step 1: Write the failing tests** (`tests/test_tests_consigne.py`) :
  - `test_section_commune_exacte` : `SECTION_TESTS` contient chaque puce du spec mot pour mot (liste des six phrases clés).
  - `test_local_cloud_serveur` : local contient `lancer.py" tests --`, « (5 min) », « une seule campagne de tests à la fois » ;
    cloud et serveur contiennent « ta déclaration `tests` est la seule mesure » et pas `lancer.py` ; `budget_s=747` →
    « (12 min 27 s) ».
  - `test_plafond` : `len(tests_rapides("cloud")) <= 1200`, `len(tests_rapides("serveur")) <= 1200`,
    `len(tests_rapides("local", 3600)) <= 1450` (voir « Décision ouverte », en fin de plan).
  - `test_message_et_lot_pour_chaque_lieu` : `message` et `message_lot` contiennent « ## Des tests rapides et peu coûteux »
    une seule fois pour local, cloud, serveur ; plus de « ## Tes tests : une seule campagne » ; aucun message ne contient
    `tests-sceau`.
  - `test_rapport_tests_facultatif` : `rapport.lire` d'un bloc avec `tests` valide + une entrée `{"duree_s": "x"}` → une
    entrée gardée ; `tests: "n'importe quoi"` → `[]`, rapport accepté.
  - `test_declarations_cloud_notees` : `boucle` avec un `Execution` cloud (attribut `branche`) et `noter_declarations`
    remplacé → appelé avec `lieu="cloud"` ; un local → jamais appelé.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_consigne` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_tests_consigne test_orch_depart
  test_orch_depart_deport test_regles_projet test_moteur_rapport` → ok.
- [ ] **Step 5: Commit** : `git add orchestrateur/depart.py orchestrateur/outil.py moteur/rapport.py moteur/boucle.py
  tests/test_tests_consigne.py` (et `tests/test_orch_depart.py` s'il a changé) ; « Tests rapides : la consigne de départ
  pour tous les lieux et la déclaration `tests` ».

### Task 8: Le coût des tests dans la Facturation

**Files:** Create `bureau/tests_cout.py` ; Modify `bureau/serveur.py` (`/api/facturation`), `bureau/web/ui/facturation.js` ;
Test `tests/test_tests_cout.py` (≈ 0,05 s), `bureau/web/tests/facturation-tests.test.js` (≈ 0,3 s).

**Interfaces:**
- Consumes : `tests_mesures.lire`, `journal_de`, `projet_enregistre` (T1) ; `cout.PERIODES`, `cout._dans_la_periode`.
- Produces : `cout_des_tests(mesures: list, usages: list, prix_de, periode: str, maintenant) -> dict` :
  `{"mesure": {"complete": n, "partielle": n, "relancees": n, "duree_s": s, "github_s": s}, "declare": {"campagnes": n,
  "duree_s": s}, "tokens_estimes": n, "euros_estimes": x | None, "sans_prix": n, "estime": True}` ; `relancees` = complètes
  au-delà de la première par tâche ; tokens = `sortie_octets // 4` des lignes mesurées ; euros = tokens × prix d'**entrée**
  du modèle du dernier usage de la même tâche (`prix_de(modele, date)[0]["entree"]`), sinon compté dans `sans_prix`. Les
  minutes GitHub ne sont pas des euros ici (elles sont comptées par `deport_conso`).
- `/api/facturation` ajoute `"tests": cout_des_tests(...)` (journal du projet enregistré ; sinon absent).
- `facturation.js` : `lignesTests(t) -> [{nom, valeur, classe}]` et un bloc « Tests » dans `dessinerFacturation` : « Suites
  complètes », « Partielles », « Suites relancées », « Temps au poste » (minutes, jamais d'euros), « Sur GitHub » (minutes,
  « comptées dans le déport »), « Tokens de sortie lus (estimé) », « Coût estimé » ; une ligne « Déclaré (cloud, serveur) »
  à part.
- [ ] **Step 1: Write the failing tests** : `test_compte_par_periode_et_portee`, `test_relancees_par_tache`,
  `test_tokens_et_euros_estimes` (48 000 octets → 12 000 tokens ; prix 3e-6 € → 0,036), `test_sans_modele_sans_euros`
  (`sans_prix` 1, `euros_estimes` 0 ou `None` si aucun prix), `test_declare_a_part` ; JS : libellés exacts, « estimé »,
  minutes sans euros.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_cout` et le `node --test` du
  fichier JS → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : les deux, plus `bureau/web/tests/facturation.test.js` → ok.
- [ ] **Step 5: Commit** : `git add bureau/tests_cout.py bureau/serveur.py bureau/web/ui/facturation.js
  tests/test_tests_cout.py bureau/web/tests/facturation-tests.test.js` ; « Tests rapides : le coût des tests dans la
  Facturation ».

### Task 9: L'installation, la décision `budget_tests` et la migration (code sensible)

**Files:** Create `installation/conventions_tests.py`, `installation/mesure_tests.py` ; Modify `installation/outil.py`,
`skills/installer/SKILL.md`, `bureau/releve.py`, `bureau/demandes.py`, `bureau/serveur.py`, `orchestrateur/outil.py`,
`orchestrateur/consignes.md`, `moteur/regles.py`, `bureau/web/ui/actions.js`, `bureau/web/ui/decisions.js` ; Test
`tests/test_inst_tests.py` (≈ 0,6 s), un cas ajouté à `bureau/web/tests/tests-lents.test.js`.

**Interfaces:**
- Consumes : `depart.SECTION_TESTS` (T7) ; `reglages.fixer_tests` (T3) ; `tests_alerte.duree_en_clair` (T4) ;
  `regles.surveiller_les_tests` (T5) ; `orchestrateur.outil.executer` (`lancer decision`).
- Produces (`installation/conventions_tests.py`) : `DEBUT = "<!-- MyIAFactory : tests (début) -->"`,
  `FIN = "<!-- MyIAFactory : tests (fin) -->"` ; `fichier_d_instructions(projet) -> Path` (`CLAUDE.md` s'il existe, sinon
  `AGENTS.md` s'il existe, sinon `CLAUDE.md`) ; `bloc(budget_s, commande_complete, commande_touches=None) -> str` (DEBUT,
  `SECTION_TESTS`, « Suite complète : `<commande>` », « Tests touchés : `<commande>` » si donnée, « Budget : <5 min> »,
  FIN) ; `ecrire(projet, budget_s, commande_complete, commande_touches=None) -> {"fichier", "change", "cree"}` (réécrit en
  place, jamais dupliqué ; un fichier créé est noté dans `.factory/conventions-tests.json`) ; `retirer(projet) ->
  {"fichier", "change", "supprime"}` (le fichier n'est supprimé que s'il a été créé par l'outil et ne contient plus que des
  blancs).
- Produces (`installation/mesure_tests.py`) : `budget_propose(reference_s) -> int` = `max(300, int(reference_s * 1.25 / 60 +
  0.5) * 60)` ; `mesurer(projet, commande: str, executer=_executer, lire=tests_mesures.lire, horloge=time.monotonic) ->
  {"duree_s", "code", "nb_tests"}` : lance `[sys.executable, LANCEUR, "tests", "--dossier", projet, "--", *commande.split()]`
  (sortie vers `DEVNULL` : la ligne JSON d'`outil.py` reste propre), puis prend la dernière ligne du journal postérieure au
  départ ; sans ligne (projet non enregistré) : la durée de `horloge`, `nb_tests` nul.
- `installation/outil.py` : `mesurer-tests <dossier> --commande "<cmd>"`, `budget-tests <dossier> --reference <s>
  --commande "<cmd>"` (pose la décision `budget_tests`), `conventions-tests <dossier> [--retirer] [--budget <s>]
  [--commande "<cmd>"] [--touches "<cmd>"]`.
- Décision `budget_tests` (`DECISIONS_PROJET`, relevé, `cmd_decision`) : `budget_s` (60–3 600), `commande_complete`
  (≤ 200), `reference_s` (nombre ou nul), `conventions` (booléen), `fichier` (nom du fichier d'instructions). Textes exacts :
  installation « La suite complète de ce projet prend <4 min 01 s>. Budget proposé : <5 min> ; au-delà, le bureau vous
  alertera et proposera une tâche « Accélérer les tests ». » ; migration « Cette commande est-elle la suite complète du
  projet ? <commande> (<4 min 12 s>) ».
- Demande `budget_tests` : `CHAMPS ("decision", "verdict")`, `FACULTATIFS ("budget_s", "conventions")`, verdicts
  `("valider", "refuser")`, `budget_s` dans les bornes ; `REPONSES_UNE_FOIS`, `TYPES_DEMANDE`, `DEMANDES_V4`, `consignes.md`.
- `regles._sur_budget_tests` : `valider` → `reglages.fixer_tests(…, {"budget_s": demande.get("budget_s") or
  d["budget_s"], "commande_complete": d["commande_complete"], "reference_s": d.get("reference_s")})`, puis, si
  `conventions` (demande, sinon décision), `conventions_tests.ecrire(...)` ; `refuser` → sceau `commande_refusee` =
  la commande ; toujours `lever`. Sans réponse, rien n'est écrit : le défaut 300 s s'applique.
- Migration dans `surveiller_les_tests` : sceau sans `commande_complete`, dernière campagne mesurée de plus de 60 s, commande
  ≠ `commande_refusee`, aucune `budget_tests` ouverte → pose `budget_tests` (proposition `budget_propose(durée)`,
  `conventions: true` proposé, case « Écrire les conventions de tests dans <CLAUDE.md> » côté carte).
- Carte JS : « Valider <5 min> », « Autre budget… » (champ minutes, puis `valider` avec `budget_s`), et pour la migration
  « Non, ce n'est pas la suite complète » (`refuser`) et la case des conventions.
- `SKILL.md` § 6, nouvelle étape après `outil.py appliquer` : redire la commande de suite complète (résumé 3b ou
  `deport.commandes.tests`) ; annoncer la durée probable et **demander l'accord** avant `mesurer-tests` ; `budget-tests` ;
  `conventions-tests` (écriture couverte par « je valide ») ; projet vide : aucune commande, le défaut s'applique ;
  réparation d'un projet existant : rien à faire (défauts, migration par le moteur).

- [ ] **Step 1: Write the failing tests** (`tests/test_inst_tests.py`, dossiers temporaires par classe) :
  `test_fichier_d_instructions_ordre`, `test_bloc_contient_section_commande_et_budget`,
  `test_ecrire_idempotent` (deux passages → contenu identique, `change` faux la seconde fois, un seul DEBUT),
  `test_ecrire_remplace_en_place` (texte avant et après le bloc gardé), `test_retirer_supprime_seulement_un_fichier_cree`,
  `test_budget_propose` (241 → 300, 600 → 780, 100 → 300), `test_mesurer_lit_le_journal` (`executer` factice qui écrit
  une ligne de journal → `{"duree_s": 241.0, "code": 0, "nb_tests": 318}`), `test_mesurer_sans_journal_prend_l_horloge`,
  `test_texte_budget_tests_installation_et_migration` (textes exacts), `test_reponse_valider_ecrit_sceau_et_conventions`
  (`regles.lancer` remplacé ; `fixer_tests` réel sur dossier temporaire), `test_reponse_refuser_ne_repose_pas`,
  `test_migration_pose_une_seule_fois`, `test_demande_budget_tests_bornes` ; JS : boutons de la carte et demande « Autre
  budget… » (7 min → 420).
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_inst_tests` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_inst_tests test_inst_outil
  test_orch_consignes` et le `node --test` de `tests-lents.test.js` → ok.
- [ ] **Step 5: Commit** : chemins listés ci-dessus ; « Tests rapides : budget et conventions à l'installation, migration des
  projets ».

### Task 10: Le dépôt MyIAFactory lui-même

**Files:** Modify `outils/tests_paralleles.py`, `CLAUDE.md`, `.gitignore` ; Create `outils/crochets/pre-push` ; Test
`tests/test_tests_paralleles.py` (≈ 0,1 s, sans lancer la suite).

**Interfaces:**
- Consumes : `tests_mesures.ligne`, `tests_mesures.ajouter` (T1).
- Produces (`outils/tests_paralleles.py`) : `BUDGET_SUITE_S = 300` ; `MESURES = RACINE / ".mesures-tests.jsonl"` ; option
  `--strict` ; `bilan(total_s: float, code: int, complete: bool, strict: bool, lents: List[Tuple[str, float]]) ->
  Tuple[int, Optional[str]]` (pure) : budget seulement pour la suite complète (ni filtre, ni `--touches`) ; verte et hors
  budget → avertissement exact « Budget dépassé : 747 s pour un budget de 300 s. Les plus longs : <m1> (<d1> s), <m2>
  (<d2> s), <m3> (<d3> s). Créez une tâche « Accélérer les tests » plutôt que de relever le budget. » et code **5** si
  `strict`, 0 sinon ; échec → 1 (l'avertissement s'affiche aussi) ; refus → 3 (inchangé, hors `bilan`). `_campagne` imprime
  l'avertissement après la dernière ligne, ajoute une ligne `.mesures-tests.jsonl` (`lieu="poste"`, `source="mesure"`,
  `portee` selon `complete`, `nb_tests` = la somme), erreurs d'écriture tues, et rend `bilan(...)[0]`.
- `outils/crochets/pre-push` (fins de ligne LF) : `#!/bin/sh` puis `exec py -3.12 outils/tests_paralleles.py --strict` ;
  **non branché** : `CLAUDE.md` dit comment l'activer (`git config core.hooksPath outils/crochets`) **seulement après la
  fusion de `tests-rapides`**.
- `CLAUDE.md` « Les tests » : les règles de 5.1 (tests touchés au quotidien ; suite complète avant de pousser et une fois ;
  pas de `sleep` réel ; pas de processus inutile ; jamais une assertion affaiblie ; pas de campagne voisine relancée par
  prudence ; pas de relecture séparée d'un petit correctif tenu par un test, sauf code sensible), « environ 4 minutes »
  remplacé par « budget : 300 s », `--strict` et le crochet facultatif décrits.
- `.gitignore` : `.mesures-tests.jsonl`.
- [ ] **Step 1: Write the failing tests** : `test_bilan_dans_le_budget` (250 s → `(0, None)`), `test_bilan_hors_budget`
  (747 s, 3 lents → texte exact, `(0, …)` ; `strict` → `(5, …)`), `test_bilan_partielle_sans_budget` (`complete` faux, 900 s
  → `(0, None)`), `test_bilan_echec_reste_1` (`code` 1, `strict`, 900 s → 1), `test_crochet_facultatif` (le fichier existe,
  contient `--strict`, aucun `\r`, et `.git/config` du dépôt n'est pas lu ni modifié), `test_claude_md_annonce_le_budget`
  (« 300 s » présent, « environ 4 minutes » absent), `test_mesures_ignorees` (`.mesures-tests.jsonl` dans `.gitignore`).
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_paralleles` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : même commande → ok (la campagne elle-même affiche ou non l'avertissement : ne
  rien en conclure, elle n'est pas complète).
- [ ] **Step 5: Commit** : `git add outils/tests_paralleles.py outils/crochets/pre-push CLAUDE.md .gitignore
  tests/test_tests_paralleles.py` ; « Tests rapides : budget et mode strict pour le dépôt MyIAFactory ».

### Task 11: Documentation et suite complète (contrôleur)

**Files:** Modify `docs/deport.md` (la mesure d'un run GitHub, lieu `github`), `docs/orchestrateur.md` (décisions
`tests_lents` et `budget_tests`, champ `tests` du rapport, journal et sceau, ce qui est vu et pas empêché — § 5.5),
`docs/installation.md` (l'étape et la migration).

- [ ] **Step 1: Write** les trois sections (courtes ; renvoi au spec pour le détail).
- [ ] **Step 2: Run the full suite once** : `py -3.12 outils/tests_paralleles.py` (environ 4 à 13 minutes selon l'état de
  `tests-rapides`) → 0 échec ; noter la durée totale et la ligne d'avertissement de budget éventuelle dans le compte rendu au
  Directeur (elle n'échoue pas : pas de `--strict`). Puis les tests JS une fois :
  `py -3.12 lancer.py tests --dossier . -- node --test "bureau/web/tests/*.test.js"` → ok.
- [ ] **Step 3: Commit** : `git add docs/deport.md docs/orchestrateur.md docs/installation.md` ; « Tests rapides :
  documentation ».

---

## Décision ouverte

1. **Plafond de la consigne locale** : le texte exact de la section commune (§ 5.1) fait 1 067 caractères ; avec la ligne
   du lanceur, la variante locale atteint ≈ 1 400 (≈ 350 tokens par départ, soit ≈ 160 de plus que l'actuelle, au lieu des
   ≈ 120 prévus). Le plan plafonne la variante locale à **1 450** et garde le texte mot pour mot ; l'autre voie est de
   raccourcir le texte commun pour tenir 1 200 partout. T7 suit le plan tant que le Directeur n'a pas choisi autrement.

## Self-review (faite)

- **Couverture du spec** : 5.1 → T7 ; 5.2 journal / portée / `nb_tests` / rotation → T1-T2, budget et sceau → T1-T3, règle
  → T4, décision → T5-T6, Facturation → T8, codes de sortie → T2 ; 5.3 → T9 ; 5.4 → T10 ; 5.5 (écart, mesures
  disparues, sceau jamais nommé) → T3-T4-T7 ; 5.6 (aucun processus) → contraintes globales ; 5.7 → T3 (défauts) et T9
  (migration) ; 4.3 A (anomalie pour le dépôt MyIAFactory) → T5 ; § 6 → les tests de chaque tâche ; § 7 docs → T11 ;
  § 8 → contraintes globales, T5, T10.
- **Écart relevé dans le spec** : le texte exact de la section commune (1 067 caractères) plus la ligne locale (≈ 330)
  dépasse le plafond de 1 200 ; cloud et serveur (≈ 1 180) tiennent. Le plan garde le texte exact et plafonne la variante
  locale à 1 450 (décision ouverte n° 1).
- **Types et noms** : `noter_campagne`, `noter_declarations`, `fixer_tests`, `ecart_tests`, `alertes`, `a_poser`,
  `VERDICTS`, `ACCELERABLES`, `duree_en_clair`, `texte_de_la_tache`, `SECTION_TESTS`, `tests_rapides`, `surveiller_les_tests`,
  `cout_des_tests`, `bilan` : définis une fois, repris sous le même nom.
