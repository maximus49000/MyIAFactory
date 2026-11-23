# Route serveur des campagnes de tests : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `lancer.py tests …` et `outils/tests_paralleles.py` envoient chaque campagne au serveur OVH (plusieurs en
parallèle, sortie en direct, même code de sortie), avec repli au poste par une règle exacte, et la suite de MyIAFactory
devient verte sous Linux.

**Architecture:** une route **attachée** (conception § 4, approche B) : le poste construit un instantané tar de l'arbre de
travail, le dépose par SSH dans `~/tests/<id>/`, puis une seule session SSH lance l'enveloppe hôte `lancer_tests.sh` qui
prend une place `flock` (N places, file premier arrivé premier servi), lance un conteneur `myiafactory/tests` sans réseau au
premier plan et relaie sa sortie ; l'entrée standard de la session sert de laisse. L'aiguillage (Python 3.9) vit dans
`deporter.lancer_tests` ; la route (Python 3.12) dans `outils/tests_serveur.py`.

**Tech Stack:** Python 3.12 bibliothèque standard (route), Python 3.9 pour `deporter`/`campagne`/`deport_types` ; bash
(enveloppe, `commun.sh`) ; Docker ; `unittest` par le lanceur.

**Spec:** `docs/superpowers/specs/2026-11-23-tests-sur-le-serveur-route-design.md`

## Global Constraints

- **Préalable** : le plan `docs/superpowers/plans/2026-11-23-tests-performants-peu-couteux.md` est exécuté et fusionné
  avant ce plan (sa tâche 7 crée `depart.tests_rapides(lieu, budget_s)`, que la tâche 15 prolonge).
- **Règle R4** : pendant le travail, seulement le module de la tâche ; la suite complète une fois, à la fin (tâche 16,
  contrôleur) ; un seul passage RED par test nouveau. Code sensible (relecture séparée) : tâches 2, 4, 6, 7 (ce qui choisit
  quoi envoyer, ce qui lance du code non fiable, ce qui juge l'accord).
- **Tests uniquement par le lanceur** : `py -3.12 outils/tests_paralleles.py <module>` ; jamais `unittest` ni `pytest`
  directement ; une campagne à la fois sur le poste.
- **Des tests économes** : aucun appel au vrai serveur, aucun `ssh` réel, aucun `docker` réel, aucun `sleep` ; `ssh`,
  `popen`, horloge, chemins (`bureau`, état local, fichier d'injoignable) injectés ; les scripts bash se testent avec un
  `PATH` de faux (`docker`, `flock` réel de Git bash si présent sinon faux, `timeout`, `df`), comme
  `tests/test_serveur_enveloppe.py` ; chaque tâche annonce la durée attendue de ses modules (au-delà du double, réduire).
  Aucun test ajouté à `tests/test_deporter.py` (149 s) ni à `tests/test_releve.py`.
- **Python 3.9** pour `outils/deporter.py`, `outils/campagne.py`, `bureau/deport_types.py`, `outils/tests_instantane.py`
  et `tests/plateforme_tests.py` (test `ast.parse(..., feature_version=(3, 9))`) ; `outils/tests_serveur.py` est en 3.12,
  importé à l'appel seulement, ou lancé par `deporter._python_312()` à part.
- **Valeurs de la conception** : instantané 50 Mo par fichier, 200 Mo au total, 50 000 fichiers ; limites par défaut
  `cpus 4`, `memoire_mo 8192`, `duree_s 1800` (borne 3 600), `/tmp` 4 Go, `--pids-limit 2048`, `nofile 8192` ; places
  1 à `PLACES_MAX = 4`, défaut 2 ; disque libre minimal 5 Go (code 76) ; image absente code 77 ; injoignable mémorisé
  **300 s** ; balayage des `~/tests/t*` de plus de **6 h** sans processus vivant ; sortie du conteneur coupée à **50 Mo** ;
  identifiant `t<AAAAMMJJ>-<HHMMSS>-<4 hexa>` (`serveur_tache.nouvel_id`, `MOTIF_ID`).
- **Codes** : celui de la commande ; 2 usage ou refus d'argument ; 3 `--sans-attendre` refusé ; 4 serveur injoignable avec
  `--serveur` ; 124 durée maximale dépassée ; 130 interruption.
- **Jamais** : de repli après un échec de test ou un Ctrl-C ; de route sans accord (R10) ; de secret, réseau ou socket
  Docker dans le conteneur de tests ; de `.git/` dans l'instantané.
- **Commits** : chemins explicites, messages en français préfixés « Tests au serveur : », attribution de la session ; ne
  rien pousser. Textes affichés en français, guillemets « ».
- **Jalons réels** (tâche 17) : contrôleur seul, chacun après le feu vert du Directeur.

## Review Focus

1. **Le poste s'en va en pleine campagne** (Ctrl-C, terminal fermé, ssh tué) : le conteneur doit mourir au serveur et la
   place se libérer, sans rien relancer au poste (T4 : `test_laisse_fermee_tue_le_conteneur` ; T6 :
   `test_interruption_ne_replie_pas`).
2. **Une ligne de la sortie des tests qui imite `#fin 0 …`** : le poste ne doit croire que l'enveloppe (T4 :
   `test_sortie_d_erreur_du_conteneur_prefixee` ; T5 : `test_fin_lue_seulement_en_derniere_ligne_d_erreur`).
3. **Fichier sensible ou piégé dans l'arbre** (`.env`, `id_ed25519`, `bureau.json` suivi par erreur ; lien vers `~/.ssh` ;
   nom `../x`) : jamais dans l'archive (T2 : `test_exclus_meme_suivis`, `test_liens_ecartes_et_nommes`,
   `test_nom_dangereux_refuse`).
4. **Copie de travail `.claude/worktrees/x` d'un projet enregistré, et dossier non enregistré** : la première part au
   serveur, le second jamais (T7 : `test_accord_copie_de_travail_sous_projet_enregistre`,
   `test_non_enregistre_jamais_route`).
5. **Serveur injoignable à chaque campagne** : une seule attente de connexion par 5 minutes, puis le poste directement
   (T6 : `test_injoignable_memorise_300_s`).

---

## Cartographie des fichiers

| Fichier | Rôle | Tâches |
|---|---|---|
| `tests/plateforme_tests.py` (nouveau) | marqueurs `windows_seulement`, `linux_seulement`, `pas_encore_linux` | 1, 9–12 |
| `outils/tests_paralleles.py` | bilan des ignorés ; route `--serveur`/`--local` ; mode conteneur | 1, 8 |
| `outils/tests_instantane.py` (nouveau, 3.9) | liste des fichiers, exclusions, limites, tar en flux | 2 |
| `serveur_ovh/images/tests/{Dockerfile,entree-tests.sh}` (nouveaux) | image de tests | 3 |
| `serveur_ovh/mise_en_place.sh`, `outils/serveur_installation.py`, `outils/serveur_capacites.py` | étape `tests_image`, empreinte, capacité | 3 |
| `serveur_ovh/taches/lancer_tests.sh` (nouveau) | enveloppe hôte : places, file, laisse, conteneur, nettoyage | 4, 14 |
| `outils/plateforme_ssh.py` | `executer_en_flux` | 5 |
| `outils/tests_serveur.py` (nouveau, 3.12) | route : serveur, envoi, exécution, repli, mesure | 6, 13, 14 |
| `bureau/deport_types.py`, `outils/deporter.py`, `lancer.py` | accord des actions routées, aiguillage | 7 |
| tests des 15 modules | compatibilité Linux | 9–12 |
| `outils/tests_mesure_places.py` (nouveau) | protocole de mesure des places | 13 |
| `orchestrateur/depart.py`, `bureau/deport_types.py` (affichage), installation | consigne, lieu « Serveur » pour les tests | 15 |
| `docs/serveur-tests.md` (nouveau), `docs/deport.md`, `docs/serveur-taches.md`, `CLAUDE.md` | documentation | 16 |

---

### Task 1: Les marqueurs de plateforme et le bilan des ignorés

**Files:**
- Create: `tests/plateforme_tests.py`
- Modify: `outils/tests_paralleles.py` (`lancer`, `_campagne`), les 15 modules en échec sous Linux (une ligne chacun)
- Test: `tests/test_plateforme_tests.py` (≈ 0,3 s)

**Interfaces:**
- Produces (`tests/plateforme_tests.py`, Python 3.9) :
  - `WINDOWS = sys.platform == "win32"`
  - `windows_seulement(raison: str)` → décorateur (classe ou test) = `unittest.skipUnless(WINDOWS, "Windows seulement : " + raison)`
  - `linux_seulement(raison: str)` → `unittest.skipUnless(sys.platform.startswith("linux"), "Linux seulement : " + raison)`
  - `pas_encore_linux(raison: str)` → `unittest.skipUnless(WINDOWS, "À rendre hermétique : " + raison)` (provisoire)
  - `module_pas_encore_linux(raison: str) -> None` : à appeler dans `setUpModule()` ; lève `unittest.SkipTest("À rendre hermétique : " + raison)` hors Windows.
  - `ValueError` si `raison` est vide ou blanche (une raison est toujours vraie et dite).
- Produces (`outils/tests_paralleles.py`) : `lancer(morceau, env)` rend en plus `ignores: int` (lu dans `OK (skipped=N)` /
  `FAILED (…, skipped=N)`), en 6ᵉ position ; la ligne de bilan finale ajoute « ; N ignoré(s) » quand N > 0.

- [ ] **Step 1: Write the failing tests** (`tests/test_plateforme_tests.py`) :
  - `test_raisons_prefixees` : une classe décorée `windows_seulement("registre")` sous `sys.platform` forcé à `linux`
    (patch de `plateforme_tests.WINDOWS` et de `sys.platform`) → `__unittest_skip_why__ == "Windows seulement : registre"` ;
    idem `linux_seulement` sous `win32` → « Linux seulement : … » ; `pas_encore_linux` → « À rendre hermétique : … ».
  - `test_raison_vide_refusee` : `windows_seulement("  ")` → `ValueError`.
  - `test_module_pas_encore_linux` : hors Windows lève `unittest.SkipTest` ; sous Windows ne lève rien.
  - `test_ignores_lus` : `tests_paralleles._ignores("Ran 4 tests in 0.1s\n\nOK (skipped=3)\n") == 3`, `FAILED (failures=1, skipped=2)` → 2, rien → 0.
  - `test_compatible_py39` : `ast.parse(source de tests/plateforme_tests.py, feature_version=(3, 9))`.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_plateforme_tests` → ÉCHEC (module absent).
- [ ] **Step 3: Implement** `tests/plateforme_tests.py`, `tests_paralleles._ignores(sortie: str) -> int` et son usage dans
  `lancer`/`_campagne`. Puis ajouter dans chacun des 15 modules en échec sous Linux (liste de la conception § 1 :
  `test_serveur_ovh_script`, `test_serveur_pont`, `test_serveur_enveloppe`, `test_serveur_agent_script`,
  `test_serveur_tache`, `test_serveur_capacites`, `test_serveur`, `test_bureau_creation`, `test_releve`,
  `test_telechargement`, `test_moteur_figes`, `test_moteur_environnement`, et les `test_inst_*` relevés en échec — ceux qui
  appellent `bash`, `powershell`, le registre ou `C:/` ; liste exacte confirmée au jalon J2) :
  `def setUpModule(): plateforme_tests.module_pas_encore_linux("<raison courte et vraie>")` (fusionné avec un
  `setUpModule` existant s'il y en a un). Sous Windows, rien ne change.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_plateforme_tests` → ok ; puis les
  modules marqués, un seul passage : `py -3.12 outils/tests_paralleles.py test_serveur_ test_inst_ test_bureau_creation
  test_releve test_telechargement test_moteur_figes test_moteur_environnement` → même résultat qu'avant (aucun ignoré sous Windows).
- [ ] **Step 5: Commit** : `git add tests/plateforme_tests.py tests/test_plateforme_tests.py outils/tests_paralleles.py`
  plus les modules marqués, par chemins ; « Tests au serveur : marqueurs de plateforme et bilan des ignorés ».

### Task 2: L'instantané de l'arbre de travail (code sensible)

**Files:**
- Create: `outils/tests_instantane.py` (Python 3.9)
- Test: `tests/test_tests_instantane.py` (≈ 1 s ; un seul vrai `git init` dans `setUpClass`)

**Interfaces:**
- Produces :
  - `MAX_FICHIER = 50 * 1024 * 1024`, `MAX_TOTAL = 200 * 1024 * 1024`, `MAX_FICHIERS = 50000`
  - `EXCLUS = (".git/", ".factory/", "node_modules/", ".env*", "*.pem", "*.key", "*.p12", "*.jks", "*.keystore", "id_rsa*", "id_ed25519*", "bureau.json", "*.local.json", "tests-sceau.json")` — motifs `fnmatch` appliqués au nom de base et, pour ceux en `/`, au premier segment de n'importe quel niveau.
  - `AJOUTS = (".durees-tests.json",)` : ajoutés s'ils existent, même ignorés.
  - `class HorsLimites(Exception)` : `.raison` (texte français).
  - `lister(racine: str, git=None) -> Tuple[List[str], List[str]]` : `(fichiers retenus, écartés nommés)` ; `git` injectable `(argv, cwd) -> (code, sortie)` (défaut : `deporter._git`-like local, `-z`) ; hors dépôt git → `HorsLimites("le projet n'est pas un dépôt git")`.
  - `ecrire_tar(racine: str, fichiers: List[str], destination: BinaryIO) -> Tuple[int, int]` : `(nombre, octets)` ; USTAR, `uid=gid=0`, `mtime=0`, droits 0644 ou 0755 (bit exécutable du fichier ou de git), lecture par blocs ; lève `HorsLimites` dès qu'une limite est dépassée.
  - `empreinte_verrou_node(racine: str) -> Optional[str]` : 16 hexa du SHA-256 de `package-lock.json` à la racine, sinon `None`.
  - `nom_sur(nom: str) -> bool` : relatif, sans `..`, sans `\`, sans octet nul, sans lecteur, ≤ 255 octets ustar (préfixe compris).

- [ ] **Step 1: Write the failing tests** :
  - `test_suivis_et_non_suivis_non_ignores` : dépôt avec `a.py` commité, `b.py` non suivi, `c.log` ignoré par `.gitignore` → `a.py`, `b.py`, `.gitignore` retenus, pas `c.log`.
  - `test_exclus_meme_suivis` : `.env`, `cle/id_ed25519`, `sous/bureau.json`, `x.local.json`, `node_modules/p/i.js`, `.factory/r.json` suivis de force → aucun retenu ; `.git/` jamais.
  - `test_ajout_durees` : `.durees-tests.json` ignoré mais présent → retenu.
  - `test_liens_ecartes_et_nommes` (sauté si le poste ne sait pas créer de lien) : un lien `l -> ~/.ssh` → dans les écartés, pas dans l'archive.
  - `test_nom_dangereux_refuse` : `nom_sur("../x")`, `nom_sur("/etc/x")`, `nom_sur("a\\b")`, `nom_sur("C:x")` → faux ; `nom_sur("src/a.py")` → vrai ; un nom dangereux rendu par un faux `git` est écarté.
  - `test_tar_reproductible_et_relisible` : deux `ecrire_tar` → mêmes octets ; `tarfile` relit les noms, `uid 0`, `mtime 0`, le bit exécutable d'un script gardé.
  - `test_limites` : `MAX_FICHIER` abaissé par `unittest.mock.patch` à 10 octets → `HorsLimites` dont la raison nomme le fichier ; idem total et nombre.
  - `test_empreinte_verrou_node` : sans verrou → `None` ; avec → 16 hexa stables.
  - `test_compatible_py39` : `ast.parse(..., feature_version=(3, 9))`.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_instantane` → ÉCHEC.
- [ ] **Step 3: Implement** `outils/tests_instantane.py` (`git ls-files -co --exclude-standard -z`, filtrage, `tarfile` sur la destination en flux).
- [ ] **Step 4: Run to verify they pass** : même commande → ok.
- [ ] **Step 5: Commit** : `git add outils/tests_instantane.py tests/test_tests_instantane.py` ; « Tests au serveur : instantané de l'arbre de travail ».

### Task 3: L'image de tests et la capacité `tests-image`

**Files:**
- Create: `serveur_ovh/images/tests/Dockerfile`, `serveur_ovh/images/tests/entree-tests.sh`
- Modify: `serveur_ovh/mise_en_place.sh` (étape `tests_image`, usage, liste des étapes), `outils/serveur_installation.py`
  (`FICHIERS_ETAPE`, `EMPREINTE_FICHIERS`, `MARQUEURS`, `empreinte_etape`), `outils/serveur_capacites.py` (`_CATALOGUE`, `_BESOINS`)
- Test: `tests/test_tests_image.py` (≈ 2 s : bash sur `entree-tests.sh` avec un faux `tar`/commande, aucune construction)

**Interfaces:**
- Produces :
  - Capacité `"tests-image"` : `Capacite("tests-image", "Image des campagnes de tests (conteneur sans réseau ni secret)", ("base",), "tests_image", "test -s ~/.myiafactory/tests-image.version", 1.0, 6)`.
  - `BESOINS["tests-serveur"] = ("tests-image",)`.
  - `FICHIERS_ETAPE["tests_image"] = ("images/tests/Dockerfile", "images/tests/entree-tests.sh")` (même tuple dans `EMPREINTE_FICHIERS`), `MARQUEURS["tests-image"] = ("tests_image", "$HOME/.myiafactory/tests-image.version")`.
  - `empreinte_etape("tests_image") == "ubuntu=<base_ubuntu>;python=3.12;node=<node>;fichiers=<16 hexa>"`.
  - Image `myiafactory/tests` : `ubuntu:24.04`, `python3` (3.12), `nodejs` du majeur `versions.json["node"]`, `npm`, `git`, `bash`, `util-linux`, `tar`, `build-essential`, `ca-certificates` ; `USER 1000:1000` ; `ENTRYPOINT ["/usr/local/bin/entree-tests.sh"]`.
  - `entree-tests.sh` (dans le conteneur) : lit la commande JSON dans `/entree/commande.json` (tableau de chaînes, validé par `python3 -I`), extrait `/entree/entree.tar` dans `/work` (`tar -x --no-same-owner --no-same-permissions`), lie `/deps/node_modules` en `/work/node_modules` s'il est monté, `cd /work`, `exec` la commande ; code 2 si la commande est invalide, code 70 si l'extraction échoue.
- [ ] **Step 1: Write the failing tests** :
  - `test_capacite_et_besoin` : `verifier_catalogue()` passe ; `manquantes_pour(["tests-serveur"], {"base"}) == ["tests-image"]`.
  - `test_empreinte_tests_image` : forme `^ubuntu=ubuntu:24\.04;python=3\.12;node=22;fichiers=[0-9a-f]{16}$` ; changer un octet de `entree-tests.sh` (copie temporaire, `RACINE_SERVEUR` patché) la change.
  - `test_etape_connue_du_script` : `mise_en_place.sh --etape tests_image --simuler` rend un JSON valide sans appeler `docker` (faux binaires qui journalisent, comme `test_simuler_ne_modifie_rien`).
  - `test_entree_refuse_commande_invalide` : `commande.json` = `"rm -rf /"` (texte, pas tableau) → code 2 ; tableau de 65 éléments → 2.
  - `test_entree_execute_le_tableau` : chemins `/entree`, `/work` remplacés par des variables réservées aux tests (`ENTREE_TESTS_RACINE`) ; tableau `["sh", "-c", "exit 7"]` → code 7 ; un argument `"; echo pirate"` reste un argument (jamais interprété).
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_image` → ÉCHEC.
- [ ] **Step 3: Implement** l'image, l'étape `tests_image` (copie d'`etape_agent_image` : contexte temporaire, étiquette `versions`, marqueur écrit après succès), les entrées Python.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_tests_image test_serveur_capacites test_serveur_installation` → ok (sous Windows).
- [ ] **Step 5: Commit** : chemins des fichiers ci-dessus ; « Tests au serveur : image de tests et capacité tests-image ».

### Task 4: L'enveloppe hôte `lancer_tests.sh` (code sensible)

**Files:**
- Create: `serveur_ovh/taches/lancer_tests.sh`
- Modify: `outils/serveur_installation.py` (déposer `taches/lancer_tests.sh` avec `taches/commun.sh`, hors empreinte d'image)
- Test: `tests/test_serveur_tests_enveloppe.py` (≈ 6 s ; faux `docker`, `timeout`, `df`, `sudo` dans `PATH` ; `HOME` temporaire)

**Interfaces:**
- Consumes : `commun.sh` (`dk`, `MOTIF_ID`, `MOTIF_CPUS`, `MOTIF_MEMOIRE`, `MOTIF_DUREE`, `liberer_creneau`).
- Produces : `lancer_tests.sh <id> <places> <cpus> <memoire_mo> <duree_s> <projet> <deps>` ; entrée standard : 1ʳᵉ ligne = commande JSON (≤ 4 096 octets), le reste = laisse.
  - Motifs : `places` `^[1-4]$`, `projet` `^[a-z0-9][a-z0-9-]{0,39}$`, `deps` `^([0-9a-f]{16}|-)$` ; `duree_s` ≤ 3 600 ; tout refus → code 2 avant toute écriture.
  - Dossier `~/tests/<id>/` : `entree/entree.tar` déposé avant (sinon code 2), `entree/commande.json` écrit par l'enveloppe (0600), `travail/` créé vide.
  - Disque : `df -Pk ~` < 5 242 880 Ko → code 76 ; image `myiafactory/tests` absente (`dk 20 image inspect`) → code 77.
  - Balayage : `~/tests/t*` de plus de 6 h dont aucun processus vivant ne porte l'identifiant (`processus_vivant`) → effacés ; tickets morts de `~/tests/.file/` effacés.
  - File : ticket `~/tests/.file/<date +%s%N>-<id>` contenant `$$` ; tour quand aucun ticket vivant plus ancien ; place : premier `flock -n` libre parmi `~/taches/.creneau-tests-1..4` si moins de `<places>` sont tenues ; sortie d'erreur `#attente <rang> <total>` à chaque changement et au plus toutes les 30 s.
  - Conteneur : `timeout <duree_s> sudo -n docker run --rm --pull never --name tests-<id> --label myiafactory.genre=tests --network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 1000:1000 --pids-limit 2048 --ulimit nofile=8192:8192 --memory <m>m --memory-swap <m>m --cpus <c> --tmpfs /tmp:size=4g,mode=1777 -v ~/tests/<id>/travail:/work` (dossier 0700 créé par l'enveloppe, sur disque : pas de mémoire prise par l'arbre) `-v ~/tests/<id>/entree:/entree:ro` (`entree.tar` et `commande.json`) -e HOME=/tmp -e MYIAFACTORY_TESTS_CONTENEUR=1 myiafactory/tests` ; Node (`deps` ≠ `-`) : `-v ~/tests/.deps/<projet>/<deps>:/deps:ro` (préparé par la tâche 14 ; absent → code 78 jusque-là).
  - Laisse : un fils lit l'entrée standard jusqu'à la fin de fichier, puis `dk 30 kill tests-<id>`.
  - Sortie standard : celle du conteneur telle quelle, coupée à 52 428 800 octets (puis une ligne « Sortie coupée à 50 Mo » sur la sortie d'erreur) ; sortie d'erreur du conteneur préfixée `| ` ligne par ligne.
  - Fin : dernière ligne de la sortie d'erreur `#fin <code> <debut_epoch> <fin_epoch> <attente_s>` ; `~/tests/<id>` effacé, ticket retiré, place libérée ; code rendu = celui du conteneur (124 si `timeout`).
- [ ] **Step 1: Write the failing tests** :
  - `test_arguments_refuses_sans_rien_ecrire` : `places 5`, `cpus 0`, `projet ../x`, `deps xyz`, `duree_s 3601`, identifiant hors motif → code 2, `~/tests` inchangé.
  - `test_drapeaux_du_conteneur` : le faux `docker` journalise ses arguments → contient chacun de `--network none`, `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--user 1000:1000`, `--pids-limit 2048`, `--memory 8192m`, `--memory-swap 8192m`, `--cpus 4`, `:/entree:ro` ; ne contient jamais `docker.sock`, `--privileged`, `-e` autre que `HOME` et `MYIAFACTORY_TESTS_CONTENEUR`.
  - `test_code_et_fin` : faux conteneur qui écrit `bonjour` et rend 3 → sortie standard `bonjour`, code 3, dernière ligne d'erreur `#fin 3 …`, `~/tests/<id>` effacé.
  - `test_sortie_d_erreur_du_conteneur_prefixee` : faux conteneur qui écrit `#fin 0 1 2 0` sur sa sortie d'erreur → la ligne arrive en `| #fin 0 1 2 0` et la vraie dernière ligne porte son vrai code.
  - `test_laisse_fermee_tue_le_conteneur` : faux conteneur qui dort (attente sur un fichier témoin, pas `sleep` du test) ; fermer l'entrée standard → `docker kill tests-<id>` journalisé, place libérée.
  - `test_places_et_file` : `places 1` et une place déjà tenue par un `flock` du test → `#attente 1 1` puis, place rendue, la campagne démarre ; deux tickets : le plus ancien passe d'abord.
  - `test_disque_et_image` : faux `df` à 1 Go libre → 76 ; faux `docker image inspect` en échec → 77 ; rien lancé.
  - `test_balayage` : un `~/tests/t20260101-000000-abcd` vieux de 7 h (`touch -d`) sans processus → effacé ; un récent → gardé.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_serveur_tests_enveloppe` → ÉCHEC.
- [ ] **Step 3: Implement** l'enveloppe (tableaux bash, aucune `eval`, `exec 8>>` pour la place comme `lancer_agent.sh`).
- [ ] **Step 4: Run to verify they pass** : même commande → ok ; et `test_serveur_installation` → ok.
- [ ] **Step 5: Commit** : `git add serveur_ovh/taches/lancer_tests.sh outils/serveur_installation.py tests/test_serveur_tests_enveloppe.py` ; « Tests au serveur : enveloppe hôte, places et laisse ».

### Task 5: La session SSH en flux

**Files:**
- Modify: `outils/plateforme_ssh.py`
- Test: `tests/test_plateforme_ssh_flux.py` (≈ 0,5 s ; faux `popen`)

**Interfaces:**
- Consumes : `campagne.relayer(entree, sortie, garder=4096)`, `_options(cle)`, `_verifier_hote`.
- Produces : `executer_en_flux(hote, commande, cle, premiere_ligne: bytes, sortie, sur_attente=None, delai_connexion=30, popen=subprocess.Popen) -> dict`
  - écrit `premiere_ligne` (terminée par `\n`) sur l'entrée standard de ssh et **la garde ouverte** (laisse) jusqu'à la fin ;
  - relaie la sortie standard vers `sortie` (`campagne.relayer`), lit la sortie d'erreur dans un fil : `#attente r t` → `sur_attente(r, t)` ; garde le reste (64 Ko) ;
  - rend `{"code": int, "octets": int, "fin": str, "fin_serveur": Optional[Tuple[int, int, int, int]], "erreur": str}` ; `fin_serveur` = les quatre entiers de `#fin` **seulement si c'est la dernière ligne non vide de la sortie d'erreur** ;
  - `KeyboardInterrupt` : ferme l'entrée, `terminate()` puis `kill()` après 5 s, relève l'exception.
- [ ] **Step 1: Write the failing tests** :
  - `test_relaie_et_rend_le_code` : faux processus (sortie `abc`, erreur `#fin 1 10 20 3\n`, code 1) → `sortie` reçoit `abc`, `code 1`, `fin_serveur == (1, 10, 20, 3)`.
  - `test_fin_lue_seulement_en_derniere_ligne_d_erreur` : erreur `#fin 0 1 2 0\nautre\n` → `fin_serveur is None`.
  - `test_attente_signalee` : `#attente 2 3` → `sur_attente(2, 3)` appelé une fois.
  - `test_laisse_ouverte_jusqu_a_la_fin` : l'entrée du faux processus n'est fermée qu'après la fin de la sortie standard.
  - `test_interruption_ferme_la_laisse` : `relayer` remplacé pour lever `KeyboardInterrupt` → entrée fermée, `terminate` appelé, exception relevée.
  - `test_hote_invalide` : hôte `-oProxyCommand=x` → `ValueError` avant tout `popen`.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_plateforme_ssh_flux` → ÉCHEC.
- [ ] **Step 3: Implement** `executer_en_flux`.
- [ ] **Step 4: Run to verify they pass** : même commande → ok.
- [ ] **Step 5: Commit** : `git add outils/plateforme_ssh.py tests/test_plateforme_ssh_flux.py` ; « Tests au serveur : session SSH en flux avec laisse ».

### Task 6: La route au serveur (code sensible)

**Files:**
- Create: `outils/tests_serveur.py` (Python 3.12)
- Test: `tests/test_tests_serveur.py` (≈ 1 s ; faux `ssh` objet, faux `choisir`, dossiers temporaires)

**Interfaces:**
- Consumes : `serveur_tache.choisir_serveur(dossier, requises)`, `serveur_tache.nouvel_id()`, `serveur_tache._octets`,
  `serveur_etat.cible(serveur)` ; `plateforme_ssh.executer_en_flux` (T5) ; `tests_instantane.lister`, `ecrire_tar`,
  `empreinte_verrou_node`, `HorsLimites` (T2) ; `tests_mesures.noter_campagne`, `tests_mesures.projet_enregistre` ;
  `campagne.executer`, `campagne._noter_l_attente`, `campagne._oublier_l_attente`.
- Produces :
  - `LIMITES = {"cpus": 4, "memoire_mo": 8192, "duree_s": 1800}`, `PLACES_DEFAUT = 2`, `INJOIGNABLE_S = 300`, `INJOIGNABLE = Path("~/MyIAFactory/tests-serveur-injoignable.json").expanduser()`, `ENVELOPPE_DISTANTE = f"{DOSSIER_DISTANT}/taches/lancer_tests.sh"`.
  - `class Repli(Exception)` : `.raison` (texte dit au poste).
  - `commande_conteneur(commande: List[str]) -> List[str]` : `py`/`py -3.12`/`python`/`python.exe` en tête → `python3` ; `npx.cmd`/`npm.cmd` → `npx`/`npm` ; le reste tel quel.
  - `executer(commande, dossier=None, attendre=True, forcer=False, places=None, dossier_etat=plateforme_acces.DOSSIER, ssh=plateforme_ssh, executer_poste=campagne.executer, noter=None, horloge=time.monotonic, maintenant=time.time, dire=print) -> int`
    - ordre : injoignable mémorisé (< 300 s, même serveur) → repli sans SSH ; `choisir_serveur(requises=("tests-image",))` (refus → R1) ; instantané dans un fichier temporaire (`HorsLimites` → R5) ; dépôt `install -d -m 700 ~/tests/<id>/entree` + `entree/entree.tar` par `_octets` (255/124 → R2) ; `executer_en_flux` ; codes 76/77 → R3 ; 255/124 sans `fin_serveur` → R4 ; sinon code de la commande ;
    - repli (`Repli`) : `dire("Serveur <raison> : tests au poste (une campagne à la fois).")` puis `executer_poste(commande, dossier=dossier, attendre=attendre)` ; avec `forcer` : `dire(raison)` et code 4 ;
    - `--sans-attendre` : passé à l'enveloppe par une place `-n` → code 3 rendu tel quel ;
    - attente d'une place : `campagne._noter_l_attente(..., motif="place de tests au serveur (rang r/t)")`, retirée ensuite ;
    - mesure après une campagne terminée au serveur : `noter(dossier, commande=…, duree_s=fin-debut, attente_s=…, code, fin, octets, lieu="serveur", tache=os.environ.get("MYIAFACTORY_TACHE"))`, erreurs tues ;
    - succès au serveur → `INJOIGNABLE` effacé ; R2/R4 → écrit `{serveur_id, jusqu_a}`.
  - `main(argv) -> int` : `serveur-tests [--dossier D] [--sans-attendre] [--serveur] -- <commande>` (lancé à part par `deporter` sous un Python plus ancien).
- [ ] **Step 1: Write the failing tests** :
  - `test_campagne_au_serveur_rend_le_code_et_note` : faux `executer_en_flux` → `code 1`, `fin_serveur (1, 100, 290, 12)` → rendu 1 ; `noter` appelé avec `lieu="serveur"`, `duree_s=190`, `attente_s≈12` ; `executer_poste` jamais appelé.
  - `test_repli_r1_aucun_serveur_pret` : `choisir_serveur` lève `RefusLancement` → `executer_poste` appelé une fois, la ligne dite contient « tests au poste ».
  - `test_repli_r2_depot_injoignable` et `test_injoignable_memorise_300_s` : `_octets` rend 255 → repli ; deuxième appel 100 s plus tard → repli **sans aucun appel ssh** ; 301 s plus tard → nouvel essai.
  - `test_repli_r3_disque_ou_image` : code 76 puis 77 → repli.
  - `test_repli_r4_session_perdue` : code 255, `fin_serveur None` → repli ; code 255 **avec** `fin_serveur` (la commande a rendu 255) → 255 rendu, pas de repli.
  - `test_jamais_de_repli_apres_echec_de_test` : code 1 avec `fin_serveur` → 1, `executer_poste` jamais appelé.
  - `test_interruption_ne_replie_pas` : `executer_en_flux` lève `KeyboardInterrupt` → relevée (le lanceur rend 130), `executer_poste` jamais appelé, rien noté.
  - `test_forcer_sans_repli` : `forcer=True` + R2 → 4.
  - `test_commande_conteneur` : `["py", "-3.12", "outils/x.py"]` → `["python3", "outils/x.py"]` ; `["npx.cmd", "vitest", "run"]` → `["npx", "vitest", "run"]`.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_serveur` → ÉCHEC.
- [ ] **Step 3: Implement** `outils/tests_serveur.py`.
- [ ] **Step 4: Run to verify they pass** : même commande → ok.
- [ ] **Step 5: Commit** : `git add outils/tests_serveur.py tests/test_tests_serveur.py` ; « Tests au serveur : route, repli et mesure ».

### Task 7: L'accord et l'aiguillage de `lancer.py tests` (code sensible)

**Files:**
- Modify: `bureau/deport_types.py`, `outils/deporter.py` (`lancer_tests`, `_lieux`, `lieux_refuses`), `lancer.py` (docstring, `serveur-tests`)
- Test: `tests/test_tests_aiguillage.py` (≈ 0,5 s ; bureau et réglages en dossier temporaire ; aucun ajout à `test_deporter.py`)

**Interfaces:**
- Produces (`bureau/deport_types.py`, 3.9) :
  - `ROUTEES_AU_SERVEUR = ("tests",)` ; `routee_au_serveur(nom, catalogue) -> bool` (dans le tuple, dans le catalogue, `"serveur"` dans ses lieux).
  - `refus_route(dossier, action, bureau=None) -> Optional[str]` : `None` si `tests_mesures.projet_enregistre(dossier, bureau)` trouve le projet ET que le lieu de l'action vaut `serveur` dans ses réglages enregistrés (`reglages_enregistres(racine)`), ou, si ces réglages ne règlent pas l'action, dans `deport.lieux` du bureau ; sinon le message (non enregistré, non réglé, réglé ailleurs).
  - `refus_accord` inchangé pour `SERVIES_AU_SERVEUR`.
- Produces (`outils/deporter.py`, 3.9) :
  - `lieux_refuses` : `serveur` admis pour une action routée (plus de refus « seuls poste et github »).
  - `lancer_tests(argv, bureau=BUREAU, deporter_main=None, campagne_main=None, route=None) -> int` : retire `--local` / `--serveur` de `argv` ; ordre de la conception § 5.1 ; route = `route(commande, dossier, attendre, forcer)` (défaut : `tests_serveur.executer` importé si Python ≥ 3.12, sinon `[*_python_312(), LANCEUR, "serveur-tests", …]` en sous-processus, sorties héritées, code rendu ; sans Python 3.12 → poste avec une ligne).
  - `--serveur` sans accord → code 2 et le message du refus (jamais de route sans accord).
- Produces (`lancer.py`) : `lancer.py serveur-tests …` → `tests_serveur.main`.
- [ ] **Step 1: Write the failing tests** :
  - `test_accord_projet_enregistre_regle_serveur` : bureau listant `<p>/.factory/reglages.json` avec `deport.lieux.tests = "serveur"` → `refus_route(<p>/src, "tests") is None`.
  - `test_accord_copie_de_travail_sous_projet_enregistre` : `<p>/.claude/worktrees/x` → `None`.
  - `test_accord_par_defaut_du_bureau` : réglages du projet sans `tests`, bureau `deport.lieux.tests = "serveur"` → `None` ; réglages du projet `tests: poste` → refus.
  - `test_non_enregistre_jamais_route` : dossier hors bureau avec ses propres réglages `serveur` → refus ; `lancer_tests` appelle `campagne_main`, jamais `route`.
  - `test_ordre_d_aiguillage` : `--local` → poste ; GitHub → `deporter_main` ; accord → `route` avec `forcer=False` ; `--serveur` → `forcer=True` ; `--serveur` sans accord → 2.
  - `test_options_retirees_de_la_commande` : `["--local", "--", "npx", "vitest", "--local"]` → la commande garde son `--local` final.
  - `test_compatible_py39` : `deport_types.py`, `deporter.py` passent `ast.parse(..., feature_version=(3, 9))`.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_aiguillage` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_tests_aiguillage test_deport_types test_orch_depart_deport` → ok ; `test_deporter` une fois, à la fin de la tâche (149 s) → ok.
- [ ] **Step 5: Commit** : `git add bureau/deport_types.py outils/deporter.py lancer.py tests/test_tests_aiguillage.py` ; « Tests au serveur : accord et aiguillage du lanceur ».

### Task 8: La suite de MyIAFactory par la route

**Files:**
- Modify: `outils/tests_paralleles.py` (`main`)
- Test: `tests/test_tests_paralleles_route.py` (≈ 0,3 s ; `tests_serveur.executer` et `refus_route` remplacés)

**Interfaces:**
- Consumes : `deport_types.refus_route` (T7), `tests_serveur.executer` (T6).
- Produces : options `--serveur` (forcé, sans repli) et `--local` ; variable `CONTENEUR = "MYIAFACTORY_TESTS_CONTENEUR"`.
  - Dans le conteneur (`CONTENEUR` = `1`) : ni route ni `campagne.attendre_son_tour`.
  - Sinon, sans `--local` et avec accord (ou `--serveur`) : `--touches` résolu au poste en liste de modules ; « Rien à tester. » → 0 sans route ; puis `tests_serveur.executer(["python3", "outils/tests_paralleles.py", "-j", str(LIMITES["cpus"]), "--lents", str(o.lents), *modules_ou_filtres], dossier=RACINE, attendre=not o.sans_attendre, forcer=o.serveur, executer_poste=<la campagne locale actuelle>)`.
  - Le repli local est exactement le chemin d'aujourd'hui (`attendre_son_tour` puis `_campagne`).
- [ ] **Step 1: Write the failing tests** :
  - `test_dans_le_conteneur_ni_route_ni_verrou` : `CONTENEUR=1` → `executer` et `attendre_son_tour` jamais appelés, `_campagne` appelé.
  - `test_touches_resolus_au_poste` : `impact_tests` remplacé (2 modules touchés) → la commande envoyée finit par ces 2 noms, sans `--touches`.
  - `test_local_et_sans_accord` : `--local` ou refus d'accord → chemin local actuel.
  - `test_serveur_force` : `--serveur` → `forcer=True`.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_paralleles_route` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_tests_paralleles_route test_plateforme_tests` → ok.
- [ ] **Step 5: Commit** : `git add outils/tests_paralleles.py tests/test_tests_paralleles_route.py` ; « Tests au serveur : la suite de MyIAFactory par la route ».

> **Fin de l'étape 1.** Les campagnes peuvent quitter le poste dès les jalons J1–J2 (tâche 17). Les tâches 9 à 12 utilisent
> `py -3.12 outils/tests_paralleles.py --serveur <module>` comme outil de vérification Linux (contrôleur seul).

### Tasks 9–12: Compatibilité Linux, un lot par tâche

Même forme pour les quatre ; **acceptation par module** : il passe sous Windows (implémenteur) **et** dans le conteneur
Linux (`--serveur <module>`, contrôleur, après J2), ou ses tests restants portent `windows_seulement("<raison vraie>")` ;
son `module_pas_encore_linux` est retiré. Un test Windows qui a un équivalent Linux utile reçoit son jumeau
`linux_seulement`. Pas de nouveau sous-processus réel dans les tests ; un faux de plus vaut mieux qu'un test sauté.

- [ ] **Step 1** : pour chaque module du lot, retirer `module_pas_encore_linux` et lire l'échec relevé au jalon J2 (sortie
  du serveur gardée par le contrôleur dans la note de reprise).
- [ ] **Step 2** : corriger la cause (faux, variable réservée aux tests, chemin `Path` au lieu de `C:/…`) ou marquer.
- [ ] **Step 3** : `py -3.12 outils/tests_paralleles.py <modules du lot>` sous Windows → ok.
- [ ] **Step 4** : contrôleur : `py -3.12 outils/tests_paralleles.py --serveur <modules du lot>` → ok (0 « à rendre hermétique »).
- [ ] **Step 5** : commit par chemins ; « Tests au serveur : <lot> sous Linux ».

**Task 9: Scripts du serveur** — `test_serveur_ovh_script`, `test_serveur_agent_script`, `test_serveur_enveloppe`,
`test_serveur_pont`, `test_serveur_tache`, `test_serveur_capacites`, `test_serveur`. Correctif attendu : variables
réservées aux tests dans `serveur_ovh/mise_en_place.sh` (ligne « Réservées aux tests » : ajouter `SSHD_CONFIG_DIR`
(défaut `/etc/ssh/sshd_config.d`), `SSHD_BIN` (défaut `sshd`), `UFW_BIN` (défaut `ufw`)) et les tests qui les pointent vers
leurs faux ; même principe pour les enveloppes (`/proc`, `/dev/kvm` : `KVM_PERIPH` existe déjà).
**Task 10: Installation et bureau** — les `test_inst_*` relevés en échec et `test_bureau_creation` (PATH du registre,
`C:/Program Files`, règles de noms de Windows : `windows_seulement` avec jumeau `linux_seulement` quand la règle Linux
existe dans le code).
**Task 11: Relevé et téléchargement** — `test_releve`, `test_telechargement`.
**Task 12: Moteur** — `test_moteur_figes`, `test_moteur_environnement` ; plus `test_moteur_detache`, `test_orch_factory`
(échecs seulement sous charge) : rendre leurs attentes indépendantes de l'horloge murale (horloge injectée) ou, à défaut,
les laisser « instables » (relance seule de `tests_paralleles`) et le dire dans le commit.

### Task 13: Places réglables et protocole de mesure

**Files:**
- Modify: `outils/tests_serveur.py` (lecture de `places_tests`), `outils/serveur_modele.py` (champ facultatif)
- Create: `outils/tests_mesure_places.py`
- Test: `tests/test_tests_places.py` (≈ 0,5 s)

**Interfaces:**
- Produces :
  - `serveur_modele` : champ facultatif `places_tests: int` (1 à 4, défaut 2 ; hors bornes → 2 et une raison au bureau) ; `tests_serveur.places_de(serveur) -> int`, passé à l'enveloppe.
  - `outils/tests_mesure_places.py` : `py -3.12 outils/tests_mesure_places.py --serveur-id <id> --paliers 1,2,3 [--avec-emulation]` ; lance k campagnes `tests_serveur.executer(..., forcer=True)` simultanées par palier (fils), relève par campagne `duree_s`, `attente_s`, code, et par palier `memory.peak` des conteneurs `tests-*` et `loadavg` (un `_bash` court après chaque palier) ; écrit `~/MyIAFactory/tests-places-mesure.json` et imprime la recommandation.
  - `recommander(mesures: dict, memoire_serveur_mo: int) -> int` : plus grand k avec `mediane(durees_k) <= 1.5 * mediane(durees_1)` et `somme(pics_k) <= 0.5 * memoire_serveur_mo` ; 1 au moins.
- [ ] **Step 1: Write the failing tests** : `test_places_bornees` (0 → 2, 5 → 2, 3 → 3) ; `test_recommander` (durées 190/230/320 s, pics 3/6/9 Go, 62 Go → 2) ; `test_recommander_memoire` (pics cumulés 40 Go à k = 2 → 1) ; `test_protocole_sans_serveur` (`executer` et `_bash` remplacés : 1 + 2 + 3 appels, fichier écrit).
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_places` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_tests_places test_serveur_modele` → ok.
- [ ] **Step 5: Commit** : chemins ci-dessus ; « Tests au serveur : places réglables et protocole de mesure ».

### Task 14: Projets Node : cache des dépendances (seulement si Q2 = oui)

**Files:**
- Modify: `serveur_ovh/taches/lancer_tests.sh` (préparation du cache), `outils/tests_serveur.py` (`deps`)
- Test: `tests/test_serveur_tests_deps.py` (≈ 4 s ; faux `docker`)

**Interfaces:**
- Produces : avec `deps` ≠ `-` et `~/tests/.deps/<projet>/<deps>/.pret` absent, l'enveloppe lance **avant la place de tests**
  un conteneur `deps-<id>` : `--network bridge` (seul conteneur avec réseau), mêmes autres drapeaux de T4, `--memory 4096m`,
  `--cpus 2`, `timeout 900`, archive montée en lecture seule, seuls `package.json` et `package-lock.json` extraits,
  `npm ci --ignore-scripts --no-audit --no-fund` dans `/deps` (dossier `~/tests/.deps/<projet>/<deps>.tmp`, renommé et
  `.pret` écrit seulement après succès) ; plus de 2 Go → abandon ; deux caches au plus par projet (le plus ancien effacé) ;
  échec → `#deps-echec` sur la sortie d'erreur, code 79 → **repli au poste** côté route (R3 étendue).
  - `tests_serveur` : `deps = empreinte_verrou_node(racine)` ; projet avec `package.json` sans verrou → R5 (« pas de
    `package-lock.json` : tests au poste »).
- [ ] **Step 1: Write the failing tests** : `test_cache_prepare_une_fois` (2ᵉ campagne : aucun `deps-*`) ; `test_seul_le_conteneur_deps_a_le_reseau` (le `run` des tests a `--network none`) ; `test_echec_deps_code_79_et_rien_de_pret` ; `test_deux_caches_au_plus` ; `test_route_sans_verrou_node_replie`.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_serveur_tests_deps` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_serveur_tests_deps test_serveur_tests_enveloppe test_tests_serveur` → ok.
- [ ] **Step 5: Commit** : chemins ci-dessus ; « Tests au serveur : dépendances Node en cache ».

### Task 15: La consigne des agents et le lieu « Serveur » des tests

**Files:**
- Modify: `orchestrateur/depart.py` (`tests_rapides`), `orchestrateur/outil.py` (passer la route), `bureau/deport_types.py`
  (`actions_exposees` : `routee_au_serveur`), l'étape d'installation qui propose les lieux (`installation/` : là où le genre
  propose `deport.lieux`)
- Test: `tests/test_tests_consigne_serveur.py` (≈ 0,3 s)

**Interfaces:**
- Consumes : `depart.tests_rapides(lieu, budget_s)` (plan tests économes, T7) ; `deport_types.refus_route` (T7).
- Produces :
  - `tests_rapides(lieu: str, budget_s: int = 300, route: bool = False) -> str` : pour `lieu == "local"` et `route`, la ligne
    exacte de la conception § 5.10 (« Il les envoie au serveur, où plusieurs campagnes tournent en parallèle ; si le serveur
    est injoignable, il les passe au poste, une campagne à la fois. ») ; sans route : la ligne actuelle ; `cloud`/`serveur` :
    inchangés quel que soit `route`.
  - `outil._route_du_depart(ctx) -> bool` : `deport_types.refus_route(racine, "tests") is None`, faux au moindre souci.
  - `actions_exposees` : champ `routee_au_serveur` ; le bureau ne grise plus « Serveur » pour `tests` (`bientot` à `None`
    pour le lieu serveur de `tests` dans `GENERIQUE`).
  - Installation : quand un serveur déclaré a `tests-image` présente, la proposition de lieux met `tests: serveur` (décision
    de Direction, comme les autres lieux), sinon `poste`.
- [ ] **Step 1: Write the failing tests** : `test_local_route` (contient « Il les envoie au serveur », `lancer.py" tests --`, pas « une seule campagne de tests à la fois sur le poste » en tête) ; `test_local_sans_route_inchange` (égal à `tests_rapides("local", 300)`) ; `test_cloud_serveur_inchanges` ; `test_plafond` (`len(tests_rapides("local", 3600, route=True)) <= 1450`) ; `test_actions_exposees_routee` ; `test_proposition_installation_avec_tests_image`.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_consigne_serveur` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_tests_consigne_serveur test_tests_consigne test_orch_depart test_orch_depart_deport` → ok.
- [ ] **Step 5: Commit** : chemins ci-dessus ; « Tests au serveur : consigne des agents et lieu Serveur ».

### Task 16: Documentation, CLAUDE.md et suite complète (contrôleur)

**Files:**
- Create: `docs/serveur-tests.md` (route, repli R1–R5, places, limites, sécurité, protocole et N mesuré, dépannage :
  `--local`, `--serveur`, fichier d'injoignable)
- Modify: `docs/deport.md` (le lieu serveur des tests), `docs/serveur-taches.md` (places `.creneau-tests-*`, `~/tests/`),
  `CLAUDE.md` (« Une seule campagne de tests à la fois **sur le poste** » ; « avec l'accord, le lanceur les envoie au
  serveur, plusieurs en parallèle ; `--local` pour forcer le poste » ; commandes inchangées), `lancer.py` (docstring)
- [ ] **Step 1** : écrire les documents (français, guillemets « »).
- [ ] **Step 2** : suite complète, une fois : `py -3.12 outils/tests_paralleles.py` → 0 morceau en échec (sous Windows).
- [ ] **Step 3** : commit par chemins ; « Tests au serveur : documentation ».

### Task 17: Jalons réels (contrôleur seul, chacun après le feu vert du Directeur)

Aucun implémenteur. Chaque jalon note son résultat dans la note de reprise (`docs/superpowers/plans/`), rien n'est laissé
sur le serveur ensuite.

- [ ] **J1** : `py -3.12 lancer.py plateforme serveurs installer <id> tests-serveur --accord` → `tests-image` « fait », empreinte égale à `empreinte_etape("tests_image")`.
- [ ] **J2** : `py -3.12 outils/tests_paralleles.py --serveur` → durée, liste exacte des modules en échec (attendu : 0 hors « à rendre hermétique »), sortie gardée pour les tâches 9–12.
- [ ] **J3** : `py -3.12 outils/tests_mesure_places.py --serveur-id <id> --paliers 1,2,3` puis `--paliers 2 --avec-emulation` → N recommandé, réglé dans le bureau, écrit dans `docs/serveur-tests.md`.
- [ ] **J4** : vérification Linux de chaque lot (tâches 9–12, étape 4).
- [ ] **J5** (si Q2) : un projet Node enregistré : `python lancer.py tests --dossier <p> -- npx vitest run` deux fois (installation puis cache).
- [ ] **J6** : enregistrer le dépôt MyIAFactory au bureau et poser `deport.lieux.tests = "serveur"` au défaut du bureau (geste du Directeur au bureau) ; `py -3.12 outils/tests_paralleles.py --touches` part au serveur.
- [ ] **J7** : repli : `serveurs-etat.json` d'une copie de `dossier_etat` marqué injoignable → une campagne passe au poste avec la ligne de repli, sans connexion.

## Auto-relecture

1. **Couverture de la conception** : § 5.1 → T7, T8 ; § 5.2 → T2, T4 (extraction, nettoyage) ; § 5.3 → T3 ; § 5.4 → T4,
   T5, T6 ; § 5.5 → T4 (places, file, limites), T13 (N, protocole) ; § 5.6 → T6 (note d'attente, mesure) ; § 5.7 → T7 ;
   § 5.8 → T14 ; § 5.9 → T1, T9–T12 ; § 5.10 → T15, T16 ; § 6 → T3, T4, T14 ; § 8 → T17.
2. **Pas** : chaque étape nomme le fichier, la signature et les valeurs ; aucun corps de fonction ; T9–T12 partagent une
   forme et nomment leurs modules et le correctif attendu.
3. **Noms** : `refus_route`, `routee_au_serveur`, `executer_en_flux`, `fin_serveur`, `tests_serveur.executer(…, forcer)`,
   `LIMITES`, `module_pas_encore_linux`, `places_tests` sont les mêmes partout.
4. **Review Focus** : chaque ligne a son test dans la tâche qui possède le code (T2, T4, T5, T6, T7).
5. **Proportion** : plan plus long que la conception, sans code ; les tests sont des noms et des assertions.
