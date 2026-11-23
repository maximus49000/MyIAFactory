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
  quoi envoyer, ce qui lance du code non fiable, ce qui juge l'accord), et depuis l'amendement 14a (ce qui est lu du
  projet), 14c (construction d'image = code exécuté au serveur avec réseau), 14d (échauffement avec réseau, caches), 15b
  (ce qui décide quels projets envoient leur code).
- **Amendement du 2026-11-23 (tout type de projet)** : la conception § 5.11–5.15 remplace l'ancienne tâche 14 (Node seul)
  par les tâches 14a–14e et réécrit 15b ; la numérotation des autres tâches est inchangée. Les arguments ajoutés à
  `lancer_tests.sh` (T4) sont **facultatifs et en fin de ligne** (absents = comportement de T4) : les tests de T4 restent
  valides. Fixtures de profils : petits dossiers sous `tests/fixtures/profils/<cas>/` (quelques fichiers texte, aucun
  binaire, aucun `gradlew` réel).
- **Amendement Unity du 2026-11-23** (conception § 5.16, Q3 = « B puis A ») : tâches **14f** (profil Unity et
  exclusions), **14g** (enveloppe à exécuteurs et exécuteur `conteneur` Unity), **14h** (exécuteur `hote_bac_a_sable` et son
  confinement), **14i** (capacités `unity-licence` / `unity-bac-a-sable`, choix automatique, bureau, outil de l'expérience) ;
  jalons J12 (réécrit), J13, J14. Aucune autre tâche renumérotée. Code sensible (relecture séparée) : 14f (secrets exclus),
  14g (licence montée, journal filtré), 14h (code non fiable sur l'hôte), 14i (choix de l'exécuteur). Aucun test ne lance
  Unity, `systemd-run`, `sudo` ni `setfacl` réels : faux dans `PATH`. Licence factice des tests : un texte sans valeur
  (`LICENCE-FACTICE-<n>`), jamais un vrai fichier.
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
6. **Une version piégée dans le projet** (`.nvmrc` = `18; curl x | sh`) : jamais dans le profil, jamais dans un
   Dockerfile (14a : `test_valeurs_hostiles_refusees` ; 14c : `test_rendu_sans_texte_du_projet`).
7. **Une image ou un réseau non approuvés** : aucune construction sans le SHA-256 approuvé, aucun échauffement qui exécute
   du code sans accord, jamais de réseau aux tests (14c : `test_construction_refuse_sha_different` ; 14d :
   `test_code_du_projet_jamais_en_bridge`, `test_seul_l_echauffement_a_le_reseau`).
8. **Un projet qui ne peut pas partir** : il reste au poste avec sa raison, jamais en silence (15b :
   `test_non_deportable_n_envoie_rien_et_dit_la_raison`).
9. **La licence Unity ou la session de Hub dans un instantané ou sur une sortie** : `Unity_lic.ulf`,
   `UnityEntitlementLicense.xml`, `.config/unityhub/…` suivis par erreur → jamais dans l'archive ; une ligne de journal qui
   cite la licence → jamais relayée (14f : `test_licence_unity_exclue` ; 14g : `test_journal_unity_filtre`,
   `test_jamais_unityhub_ni_socket_montes`).
10. **L'option A choisie sans son bac à sable** : `unity-licence = hote` sans `unity-bac-a-sable` → rien sur l'hôte, repli
    dit (14i : `test_hote_jamais_sans_bac_a_sable`) ; l'unité systemd a toutes ses protections et ne voit pas
    `~/agent-identifiants` (14h : `test_proprietes_figees_de_l_unite`, `test_arguments_hostiles_refuses` ; audit réel J14).
11. **Zéro test exécuté pris pour une réussite** (tests sans `.asmdef` non découverts) : code 82, jamais `passe`, jamais
    un verdict `conteneur` (14g : `test_zero_test_n_est_pas_un_succes` ; 14i : `test_essai_indetermine_n_ecrit_rien`).

---

## Cartographie des fichiers

| Fichier | Rôle | Tâches |
|---|---|---|
| `tests/plateforme_tests.py` (nouveau) | marqueurs `windows_seulement`, `linux_seulement`, `pas_encore_linux` | 1, 9–12 |
| `outils/tests_paralleles.py` | bilan des ignorés ; route `--serveur`/`--local` ; mode conteneur | 1, 8 |
| `outils/tests_instantane.py` (nouveau, 3.9) | liste des fichiers, exclusions, limites, tar en flux | 2 |
| `serveur_ovh/images/tests/{Dockerfile,entree-tests.sh}` (nouveaux) | image de tests | 3 |
| `serveur_ovh/mise_en_place.sh`, `outils/serveur_installation.py`, `outils/serveur_capacites.py` | étape `tests_image`, empreinte, capacité | 3 |
| `serveur_ovh/taches/lancer_tests.sh` (nouveau) | enveloppe hôte : places, file, laisse, conteneur, nettoyage | 4, 14b, 14d, 14e |
| `outils/plateforme_ssh.py` | `executer_en_flux` | 5 |
| `outils/tests_serveur.py` (nouveau, 3.12) | route : serveur, envoi, exécution, repli, mesure | 6, 13, 14b, 14d, 14e |
| `outils/tests_profil.py` (nouveau, 3.12) | analyse du projet → profil d'exécution | 14a, 15b |
| `outils/tests_images.py` (nouveau, 3.12) | catalogue d'images, gabarit des images dérivées, registre local | 14b, 14c |
| `serveur_ovh/images/tests-android/Dockerfile` (nouveau) | image de catalogue Gradle/Android (SDK de l'hôte monté) | 14b |
| `serveur_ovh/taches/construire_image_tests.sh` (nouveau) | construction et ramassage des images dérivées | 14c |
| `tests/fixtures/profils/` (nouveau) | dossiers de projets factices (Python, Node, Gradle/Android, Maven, .NET, Go, Rust, Godot, Unity, Windows, Xcode) | 14a |
| `bureau/deport_types.py`, `outils/deporter.py`, `lancer.py` | accord des actions routées, aiguillage | 7 |
| tests des 15 modules | compatibilité Linux | 9–12 |
| `outils/tests_mesure_places.py` (nouveau) | protocole de mesure des places | 13 |
| `orchestrateur/depart.py`, `bureau/deport_types.py` (affichage), installation | consigne, lieu « Serveur » pour les tests | 15, 15b |
| `outils/tests_adoption.py` (nouveau) | adoption par projet : analyse → image → échauffement → évaluation → verdict | 15b |
| `outils/tests_instantane.py`, `outils/tests_profil.py`, `tests/fixtures/profils/unity*/` | exclusions de licence, profil Unity | 14f |
| `serveur_ovh/images/tests-unity/` (nouveau), `serveur_ovh/taches/lancer_tests.sh`, `entree-tests.sh` | exécuteurs, Unity en conteneur | 14g |
| `serveur_ovh/unity-bac-a-sable.sh` (nouveau, déposé en `/usr/local/lib/myiafactory/`), `serveur_ovh/mise_en_place.sh` | bac à sable de l'option A | 14h |
| `outils/serveur_capacites.py`, `outils/serveur_tache.py`, `outils/tests_unity_essai.py` (nouveau), `bureau/web/ui/` | capacités Unity, choix, expérience, affichage | 14i |
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

### Task 14 (amendée) : profils d'exécution, images et caches de dépendances — tâches 14a à 14e

L'ancienne tâche 14 (cache Node seul) est remplacée par cinq tâches (conception § 5.11–5.14) ; son cas Node devient le cas
`npm` de 14d (mêmes valeurs ; Q2 = oui). Ordre : 14a → 14b → 14c → 14d → 14e ; chacune n'exige que les précédentes.

### Task 14a: L'analyse du projet et le profil d'exécution (code sensible : ce qui est lu du projet)

**Files:**
- Create: `outils/tests_profil.py` (Python 3.12, bibliothèque standard), `tests/fixtures/profils/<cas>/` (fichiers texte
  minuscules : `python-stdlib`, `python-pytest`, `node-npm`, `node-sans-verrou`, `gradle-android` (copie réduite des en-têtes
  de MyFridgeCleaner : `settings.gradle.kts`, `build.gradle.kts` racine et `app/`, `gradle-wrapper.properties`,
  `gradle.properties`, `AndroidManifest.xml`, un `.github/workflows/x.yml`), `maven`, `dotnet`, `dotnet-framework`, `go`,
  `rust`, `godot`, `unity`, `xcode`, `contradictoire`, `inconnu`)
- Modify: `outils/tests_instantane.py` (`EXCLUS` += `local.properties` ; `limites_pour(famille)`), `outils/tests_serveur.py`
  (`commande_conteneur` : `gradlew.bat` → `./gradlew`, `mvnw.cmd` → `./mvnw`, `dotnet.exe` → `dotnet`, `godot*.exe` → `godot`)
- Test: `tests/test_tests_profil.py` (≈ 0,5 s ; fixtures seulement, aucun sous-processus)

**Interfaces:**
- Consumes : `installation.examen` (`FICHIERS_CLES`, `DOSSIERS_SAUTES`, `_lire_borne`) ; `deport_types.catalogue_du_projet`.
- Produces :
  - `FAMILLES = ("python", "node", "gradle-android", "gradle-jvm", "maven", "dotnet", "go", "rust", "godot", "unity", "ruby", "php", "make")`.
  - `LUS = (...)` : la liste fermée des motifs de fichiers lus (tableau du § 5.11 + `.github/workflows/*.yml`) ; `MAX_LU = 256 * 1024` (CI : 64 Ko).
  - `@dataclass(frozen=True) class Profil` : `familles`, `outils: dict`, `commandes: List[List[str]]`, `deps: dict`, `caches: List[str]`, `ressources: dict`, `isolement`, `non_deportable: Optional[str]`, `confiance`, `empreinte` ; `vers_json()` / `depuis_json()`.
  - `analyser(racine: str, commande: Optional[List[str]] = None, catalogue=None, lire=None) -> Profil` : pur ; `lire` injectable `(chemin) -> Optional[str]` (défaut : `_lire_borne`, refuse liens et exclus).
  - `empreinte_profil(profil) -> str` (64 hexa, forme canonique triée, hors `confiance`) et `empreinte_image(profil) -> str` (seulement `outils`).
  - `non_deportable(racine, lire) -> Optional[str]` : raisons N1, N2, N6 du § 5.14 détectées statiquement (N3–N5 viennent de `tests.profil_force` ou de l'évaluation).
  - `ressources_par_defaut(famille) -> dict` (tableau du § 5.14 ; Gradle : `-Xmx` de `org.gradle.jvmargs` + 4 096 Mo, 6 144 au moins).
- [ ] **Step 1: Write the failing tests** :
  - `test_familles_detectees` : chaque fixture → sa famille ; `contradictoire` → confiance `basse` ; `inconnu` → famille vide, confiance `basse`, aucune exception.
  - `test_gradle_android_comme_myfridgecleaner` : `outils == {"jdk": "17", "gradle": "9.3.1", "android": {"compileSdk": 36, ...}}`, AGP `9.1.1`, commande `["./gradlew", "testDebugUnitTest"]` (catalogue `ANDROID` prime), mémoire 6 144 Mo (`-Xmx2048m` + 4 096), confiance `haute` (CI `java-version: '17'` concordante).
  - `test_versions_lues` : `.nvmrc` `18.20.4`, `.python-version` `3.11`, `global.json`, `rust-toolchain.toml`, `go 1.23`, Godot `"4.7"`, Unity `6000.6.7f1`.
  - `test_ne_lit_que_la_liste_fermee` : `lire` espion → jamais `.env`, `local.properties`, `*.keystore`, ni un fichier hors `LUS` ; un lien symbolique n'est pas suivi (sauté si le poste ne sait pas en créer).
  - `test_rien_n_est_execute` : `subprocess.Popen`, `os.system` remplacés par des pièges → jamais appelés.
  - `test_valeurs_hostiles_refusees` : `.nvmrc` = `18; curl x | sh` → version rejetée (confiance `basse`, raison dite), jamais recopiée dans le profil.
  - `test_non_deportables` : `dotnet-framework` → N1 ; `xcode` → N2 ; `dotnet` (net8.0) → `None`.
  - `test_empreintes` : changer `package-lock.json` change `empreinte_profil` mais pas `empreinte_image` ; changer `.nvmrc` change les deux.
  - `test_local_properties_exclu` et `test_limites_par_famille` (`tests_instantane`) ; `test_commande_conteneur_windows` (`gradlew.bat` → `./gradlew`).
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_profil` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_tests_profil test_tests_instantane test_tests_serveur` → ok.
- [ ] **Step 5: Commit** : chemins ci-dessus ; « Tests au serveur : analyse du projet et profil d'exécution ».

### Task 14b: Les images existantes au catalogue et l'image `tests-android`

**Files:**
- Create: `outils/tests_images.py` (catalogue et choix), `serveur_ovh/images/tests-android/Dockerfile`
- Modify: `outils/serveur_capacites.py` (`tests-android`), `outils/serveur_installation.py` et `serveur_ovh/mise_en_place.sh`
  (étape `tests_android_image`), `serveur_ovh/taches/lancer_tests.sh` (8ᵉ et 9ᵉ arguments facultatifs `<image>`
  `<famille>`), `outils/tests_serveur.py` (choix de l'image et des capacités requises d'après le profil)
- Test: `tests/test_tests_images.py` (≈ 1 s ; faux `docker` pour l'enveloppe, aucune construction)

**Interfaces:**
- Produces :
  - Capacité `Capacite("tests-android", "Image des tests Gradle/Android (SDK de l'hôte en lecture seule)", ("tests-image", "android-build"), "tests_android_image", "test -s ~/.myiafactory/tests-android-image.version", 0.5, 4)` ; `BESOINS["tests-serveur-android"] = ("tests-android",)`.
  - Image `myiafactory/tests-android` : `FROM myiafactory/tests`, `openjdk-17-jdk-headless` et `openjdk-21-jdk-headless` (distribution), `ANDROID_HOME=/opt/android-sdk`, `GRADLE_USER_HOME=/deps/gradle`, utilisateur 1000 ; vérifié à la construction : `java -version` 17, ni `curl` ni `wget`.
  - `CATALOGUE_IMAGES` : `{"myiafactory/tests": {"capacite": "tests-image", "familles": ("python", "node", "make"), "outils": {"python": "3.12", "node": "22"}}, "myiafactory/tests-android": {"capacite": "tests-android", "familles": ("gradle-android", "gradle-jvm"), "outils": {"jdk": ("17", "21")}}}` ; `myiafactory/android` (Gradle 8.7, plateforme 34) et `unityci/editor` ne sont **pas** au catalogue des tests (conception § 5.12) ; l'image GameCI n'y entre que comme base de
    `myiafactory/tests-unity-<version>` (14g, Q3 = B puis A).
  - `choisir_image(profil, sdk_android=None) -> dict` : `{"image", "capacites", "derivee": bool, "manque": [..]}` ; une image de catalogue convient si chaque outil du profil y est à la même version majeure (Python majeur.mineur) ; pour `gradle-android`, `sdk_android` (relevé de la sonde `android-build` : plateformes et build-tools présents) doit contenir `compileSdk` et `build_tools`, sinon `manque = ["platforms;android-N"]`.
  - `lancer_tests.sh … <deps> [<image> [<famille>]]` : `image` motif `^myiafactory/tests(-[a-z0-9]{1,24})?$` (défaut `myiafactory/tests`) ; `famille` dans `FAMILLES` (défaut `python`) ; table fermée par famille dans l'enveloppe : montages (`gradle-android` : `-v ~/android-sdk:/opt/android-sdk:ro`) et variables (`GRADLE_OPTS`, `ANDROID_HOME`) ; jamais une valeur venue du poste hors motif.
- [ ] **Step 1: Write the failing tests** : `test_capacite_tests_android` (`verifier_catalogue`, `manquantes_pour(["tests-serveur-android"], {"base", "tests-image"}) == ["android-build", "tests-android"]`) ; `test_choix_catalogue` (Python 3.12 → `myiafactory/tests` ; Node 18 → dérivée ; MyFridgeCleaner + SDK android-36/36.0.0 → `tests-android` ; même projet + SDK sans android-36 → `manque`) ; `test_enveloppe_image_et_famille` (motifs refusés → 2 ; `gradle-android` monte le SDK en `:ro` ; sans les deux arguments : identique à T4) ; `test_etape_simulee` (`--etape tests_android_image --simuler`, aucun `docker`).
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_images` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_tests_images test_serveur_capacites test_serveur_tests_enveloppe` → ok.
- [ ] **Step 5: Commit** : chemins ci-dessus ; « Tests au serveur : images du catalogue et image tests-android ».

### Task 14c: Les images dérivées : gabarit, décision, construction, ramassage (code sensible : code exécuté au serveur avec réseau)

**Files:**
- Modify: `outils/tests_images.py` (gabarit, registre), `serveur_ovh/images/tests/Dockerfile` (Node par archive officielle
  et `SHASUMS256.txt` au lieu de `curl … | bash -`, empreinte `tests_image` changée)
- Create: `serveur_ovh/taches/construire_image_tests.sh`
- Test: `tests/test_tests_images_derivees.py` (≈ 2 s ; rendu pur ; bash sur l'enveloppe avec faux `docker`, `df`)

**Interfaces:**
- Produces :
  - `OUTILS` (table fermée : `jdk`, `node`, `python`, `maven`, `dotnet`, `go`, `rust`, `godot`, `unity`) ; `MOTIFS_VERSION` par outil.
  - `rendre_dockerfile(profil) -> Tuple[str, str]` : `(texte, sha256)` ; reproductible (mêmes octets à profil égal) ; blocs dans un ordre fixe ; chaque téléchargement dans un fichier puis vérification de la somme officielle (conception § 5.12), échec de construction sinon ; `ValueError` pour tout outil ou version hors table.
  - `etiquette_derivee(profil) -> str` : `myiafactory/tests-<12 hexa de empreinte_image>`.
  - Registre `REGISTRE = ~/MyIAFactory/tests-images.json` : `noter_image(serveur_id, etiquette, empreinte, taille_mo, maintenant)`, `image_connue(serveur_id, empreinte) -> Optional[str]`, `noter_usage(...)`.
  - `construire_image_tests.sh <etiquette> <sha256>` : contexte `~/tests/.construction/<etiquette>/` avec le seul `Dockerfile` déposé (et `entree-tests.sh` copié du dépôt du serveur) ; refus (code 2) si le SHA-256 diffère, si l'étiquette sort du motif, si le contexte contient autre chose ; disque < 10 Go → 76 ; `timeout 1800 sudo -n docker build --pull --label myiafactory.genre=tests-derivee --label myiafactory.empreinte=… -t <etiquette>` (ni `--privileged`, ni `--build-arg` hors table, ni montage) ; sortie : `#image <etiquette> <taille_mo>` ; journal de construction gardé 64 Ko.
  - `construire_image_tests.sh --ramasser <budget_go>` : ne touche que les images `myiafactory.genre=tests-derivee` ; jamais une image d'un conteneur vivant ; > 30 jours sans usage puis la moins récemment utilisée tant que le total dépasse le budget ; une ligne `#ramassee <etiquette>` chacune.
  - Décision de Direction `tests_image_derivee` (posée par 15b) : `{"dockerfile", "sha256", "etiquette", "taille_estimee_mo", "duree_estimee_s"}` ; réponses `construire` / `plus_tard` / `garder_poste`.
- [ ] **Step 1: Write the failing tests** :
  - `test_rendu_reproductible` ; `test_rendu_sans_texte_du_projet` (profil avec une version `1; rm -rf /` ou un retour à la ligne → `ValueError` ; aucun caractère hors `[0-9A-Za-z.+_-]` dans les valeurs d'une ligne `RUN`) ; `test_aucun_curl_pipe_shell` (aucune ligne ne contient `| sh`, `| bash`, `nvm`, `sdkman`, `pyenv`, `ADD http`) ; `test_chaque_telechargement_verifie` (chaque `curl -o` suivi d'un `sha256sum -c`/`sha512sum -c`) ; `test_etiquette_stable` (même `empreinte_image` → même étiquette, changer seulement le verrou ne la change pas).
  - `test_construction_refuse_sha_different` (code 2, `docker build` jamais lancé) ; `test_contexte_sans_fichier_du_projet` ; `test_construction_ligne_image` (faux `docker` : `#image … 812`) ; `test_ramassage` (3 images fausses, une utilisée par un conteneur vivant, budget dépassé → les deux autres seulement, la plus ancienne d'abord).
  - `test_image_tests_sans_curl_pipe` : le `Dockerfile` de `images/tests` ne contient plus `| bash`.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_images_derivees` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_tests_images_derivees test_tests_images test_tests_image` → ok.
- [ ] **Step 5: Commit** : chemins ci-dessus ; « Tests au serveur : images dérivées, construction et ramassage ». Relecture séparée.

### Task 14d: Caches de dépendances et échauffement (code sensible : réseau, caches ; reprend l'ancienne tâche 14)

**Files:**
- Modify: `serveur_ovh/taches/lancer_tests.sh` (échauffement, copie sur écriture, drapeaux hors ligne), `outils/tests_serveur.py`
  (`deps` = empreinte du cache du profil), `outils/tests_profil.py` (`empreinte_deps`)
- Test: `tests/test_serveur_tests_deps.py` (≈ 4 s ; faux `docker`, `flock`, `df`)

**Interfaces:**
- Produces :
  - `empreinte_deps(profil, racine, lire) -> Optional[str]` (16 hexa : verrou ou verrou implicite Gradle/Maven, plus `empreinte_image`, conception § 5.13) ; `None` si aucune dépendance.
  - `ECHAUFFEMENTS` (table fermée, côté enveloppe et côté Python pour l'affichage) : famille → commande en tableau, durée (900 / 1 800 / 3 600 s), plafond (2 / 6 / 10 Go), `execute_du_code` (`npm`, `pnpm`, `yarn`, `pip` à roues seulement, `cargo fetch`, `go mod download`, `dotnet restore` : faux ; Gradle, Maven, pip sans roue, Unity : vrai).
  - Enveloppe : `deps` ≠ `-` et `~/tests/.deps/<projet>/<famille>-<deps>/.pret` absent → conteneur `deps-<id>` **avant la place de tests** : réseau `bridge` (Q2, familles sans code) ou réseau `--internal` + mandataire éphémère à liste fermée (familles `execute_du_code`, seulement si l'argument `<reseau_code>` vaut `accorde`, posé par la route d'après `tests.adoption`) ; mêmes autres drapeaux que T4 ; cache écrit dans `<…>.tmp`, renommé et `.pret` posé après succès ; `gradle-wrapper.jar` vérifié avant tout lancement Gradle (sommes publiées, copie de la liste dans l'image) ; échec ou plafond → `#deps-echec <raison>`, code 79.
  - Sans verrou : le verrou produit reste dans le cache (`.verrou-produit`), cache « non verrouillé », refait si `.pret` a plus de 7 jours.
  - Pendant les tests : volume `overlay` par campagne (basse : le cache en lecture seule ; haute : `~/tests/<id>/deps-haut`), monté sur `/deps`, effacé à la fin ; `flock -s` sur `<cache>/.verrou` pendant la campagne ; drapeaux hors ligne par famille (table fermée du § 5.13) ajoutés par l'entrée du conteneur, jamais par le poste.
  - Éviction : deux caches au plus par projet et par famille ; `budget_caches_go` (argument, défaut 40) : le moins récemment utilisé (`.utilise` touché à chaque campagne), jamais un cache tenu (`flock -x -n`).
  - Route : code 79 → repli au poste (R3 étendue) ; projet `execute_du_code` sans accord réseau → repli R5 avec « échauffement réseau non accordé ».
- [ ] **Step 1: Write the failing tests** : `test_cache_prepare_une_fois` (2ᵉ campagne : aucun `deps-*`) ; `test_seul_l_echauffement_a_le_reseau` (le `run` des tests a `--network none`) ; `test_code_du_projet_jamais_en_bridge` (famille Gradle → réseau interne + mandataire, ou refus sans `accorde`) ; `test_wrapper_modifie_refuse` ; `test_echec_deps_code_79_et_rien_de_pret` ; `test_copie_sur_ecriture` (le faux `docker` reçoit un volume `overlay` dont la basse est le cache, effacé ensuite) ; `test_drapeaux_hors_ligne` (Gradle : `--offline --no-daemon` ; Cargo : `--offline`) ; `test_sans_verrou_garde_le_verrou_produit` ; `test_deux_caches_et_budget` ; `test_cache_tenu_jamais_efface` ; `test_route_code_79_replie`.
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_serveur_tests_deps` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_serveur_tests_deps test_serveur_tests_enveloppe test_tests_serveur` → ok.
- [ ] **Step 5: Commit** : chemins ci-dessus ; « Tests au serveur : caches de dépendances et échauffement ». Relecture séparée.

### Task 14e: Places pondérées par la mémoire et limites par profil

**Files:**
- Modify: `serveur_ovh/taches/lancer_tests.sh` (jetons), `outils/tests_serveur.py` (limites du profil), `outils/serveur_modele.py`
  (`budget_tests_mo`), `outils/tests_mesure_places.py` (paliers mixtes)
- Test: `tests/test_tests_jetons.py` (≈ 3 s ; `flock` de Git bash ou faux, faux `docker`)

**Interfaces:**
- Produces :
  - `serveur_modele` : champ facultatif `budget_tests_mo` (8 192 à 40 960, défaut 32 768 ; hors bornes → défaut et une raison au bureau).
  - `tests_serveur.limites_de(profil) -> dict` : `ressources_par_defaut` (14a) relevées par `tests.profil_force` dans les bornes (`cpus` ≤ 8, `memoire_mo` ≤ 16 384, `duree_s` ≤ 3 600) ; au-delà, refus avec « décision du Directeur requise ».
  - `lancer_tests.sh … [<image> [<famille> [<budget_unites>]]]` : `budget_unites` `^([4-9]|1[0-9]|20)$` (défaut 16) ; jetons `~/taches/.jeton-tests-1..20` de 2 Go ; poids = `ceil(memoire_mo / 2048)` ; seul le premier ticket de la file prend des jetons, un par un, et les garde jusqu'à en avoir assez (puis prend sa place, § 5.5) ; `#attente <rang> <total> <jetons_libres>` ; jetons rendus avec la place.
  - `tests_mesure_places.py --mixte gradle:2,python:2` : paliers mixtes (jalon J11).
- [ ] **Step 1: Write the failing tests** : `test_poids` (8 192 → 4 ; 10 240 → 5 ; 4 096 → 2) ; `test_seul_le_premier_prend_des_jetons` (deux tickets, le second n'en tient aucun tant que le premier attend) ; `test_budget_respecte` (16 jetons, 2 × 4 + 2 × 4 tenus → la cinquième attend avec `#attente 1 1 0`) ; `test_jetons_rendus_a_la_fin_et_a_la_laisse` ; `test_sans_argument_comme_t4` ; `test_limites_bornees` (`memoire_mo` 20 000 forcé → refus dit).
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_jetons` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_tests_jetons test_serveur_tests_enveloppe test_tests_places` → ok.
- [ ] **Step 5: Commit** : chemins ci-dessus ; « Tests au serveur : places pondérées et limites par profil ».

### Tasks 14f–14i (amendement Unity) : licence de Hub, option B puis option A

Conception § 5.16. Ordre : 14f (après 14a, indépendante du reste : elle peut passer tôt) → 14g (après 14c, 14d, 14e) →
14i (après 14g ; la partie A de 14i attend 14h) ; 14h après 14g. Les tests Python de `sur-la-route` n'attendent aucune de
ces tâches (profil `python`, jalon J12).

### Task 14f: Le profil Unity et les exclusions de licence (code sensible : secrets exclus)

**Files:**
- Modify: `outils/tests_instantane.py` (`EXCLUS_EN_PLUS`, comparaison des motifs à plusieurs segments, exclusions par
  famille), `outils/tests_profil.py` (famille `unity`), docstring de `tests_instantane` (liste des motifs)
- Create: `tests/fixtures/profils/unity-asmdef/`, `tests/fixtures/profils/unity-sans-asmdef/` (copie réduite des en-têtes de
  `sur-la-route` : `ProjectSettings/ProjectVersion.txt`, `Packages/manifest.json` avec une dépendance git, un
  `Assets/Editor/Tests/X.cs` vide, `Tools/factory/tests/test_x.py`) ; la fixture `unity` de 14a devient `unity-asmdef`
- Test: `tests/test_tests_unity_profil.py` (≈ 0,5 s ; un vrai `git init` seulement pour l'exclusion, dans `setUpClass`)

**Interfaces:**
- Produces (`tests_instantane`, Python 3.9) :
  - `EXCLUS_EN_PLUS` += `"*.ulf"`, `"Unity_lic*"`, `"UnityEntitlementLicense*"`, `"Unity.Licensing.Client*"`, `"unityhub/"`,
    et `EXCLUS_SEGMENTS = (".config/unity3d/", ".local/share/unity3d/")` : suites de segments consécutifs à n'importe quel
    niveau, sans tenir compte de la casse (un `Assets/Unity3D/` reste admis).
  - `exclus_de_famille(famille) -> Tuple[str, ...]` : `unity` → `("Library/", "Temp/", "Logs/", "UserSettings/", "obj/",
    "Build/", "Builds/")`, appliqués **à la racine du projet Unity seulement** ; autres familles → `()`. `limites_pour("unity")`
    garde 1 Go (14a).
- Produces (`tests_profil`, Python 3.12) :
  - Famille `unity` : `outils["unity"] = "6000.6.7f1"`, `outils["unity_revision"] = "b22767f04f04"` (motif
    `^[0-9]{4}\.[0-9]{1,2}\.[0-9]{1,3}[abfp][0-9]{1,2}$` et `^[0-9a-f]{12}$`, sinon refus dit) ; `deps = {"gestionnaire":
    "upm", "verrou": "Packages/packages-lock.json", "reseau": True, "execute_du_code": True, "git": [hôtes des dépendances
    git du manifeste, ex. "github.com"]}` ; `commandes` = le tableau du § 5.11 ; `isolement = "licence"` ;
    `ressources_par_defaut("unity")` = 4 cpus, 10 240 Mo, 3 600 s, `/tmp` 6 Go.
  - `tests_unity(racine, lire) -> dict` : `{"asmdef": bool, "dossiers": [..], "confiance": "haute"|"moyenne"|"basse"}` :
    `.asmdef` qui cite `nunit.framework.dll` ou `UNITY_INCLUDE_TESTS` → `haute` ; dossiers `Editor/**/Tests` sans `.asmdef`
    → `moyenne` ; rien → `basse` (« aucun test EditMode repéré »). `.asmdef` lus comme JSON borné (ajoutés à `LUS`).
  - PlayMode : un `.asmdef` de tests sans `"Editor"` dans `includePlatforms` → commande PlayMode **non** proposée,
    `non_deportable` de cette commande = N3 (« Unity PlayMode : rendu requis »).
  - Projet mixte (`Tools/factory/tests` + Unity) : deux familles, `python` et `unity`, deux commandes ; la famille `python`
    ne porte **aucun** besoin de licence.
- [ ] **Step 1: Write the failing tests** : `test_licence_unity_exclue` (dépôt où sont suivis de force `Unity_lic.ulf`,
  `x/UnityEntitlementLicense.xml`, `.config/unity3d/Unity/licenses/a.xml`, `.config/unityhub/session.json`,
  `.local/share/unity3d/Unity/Unity_lic.ulf`, `Unity.Licensing.Client.log` → aucun retenu ; `Assets/Unity3D/a.cs` retenu) ;
  `test_exclus_de_famille_unity` (`Library/`, `Temp/` de la racine Unity écartés ; `Assets/Library/x.cs` gardé ; famille
  `python` : rien d'écarté de plus) ; `test_profil_sur_la_route` (fixture `unity-sans-asmdef` → familles `python` et
  `unity`, version et révision lues, `deps.git == ["github.com"]`, confiance `moyenne`) ; `test_asmdef_confiance_haute` ;
  `test_playmode_n3` ; `test_version_unity_hostile_refusee` (`m_EditorVersion: 6000.6.7f1; rm -rf /` → refus dit, rien
  dans le profil) ; `test_python_du_projet_sans_licence` (la commande `python` du profil mixte a `isolement == "standard"`).
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_unity_profil` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_tests_unity_profil test_tests_instantane test_tests_profil` → ok.
- [ ] **Step 5: Commit** : chemins ci-dessus ; « Tests au serveur : profil Unity et exclusions de licence ». Relecture séparée.

### Task 14g: L'enveloppe à exécuteurs et Unity dans le conteneur (option B ; code sensible : licence montée)

**Files:**
- Create: `serveur_ovh/images/tests-unity/Dockerfile.gabarit` (bloc `unity` du gabarit de 14c : `FROM` l'image GameCI
  par digest local, `entree-tests.sh`, utilisateur 1000, `git` vérifié), `serveur_ovh/images/tests/entree-unity.sh`
  (appelé par `entree-tests.sh` pour la famille `unity`)
- Modify: `serveur_ovh/taches/lancer_tests.sh` (exécuteurs, table des montages Unity, codes 81/82), `outils/tests_images.py`
  (bloc `unity`, taille propre pour le ramassage), `outils/tests_serveur.py` (arguments `executeur`, `licence`),
  `serveur_ovh/taches/construire_image_tests.sh` (taille propre)
- Test: `tests/test_serveur_tests_unity.py` (≈ 3 s ; faux `docker`, faux `unity-editor` qui écrit un XML de résultats et
  un journal choisis par le test)

**Interfaces:**
- Produces (`lancer_tests.sh`) : deux arguments facultatifs de plus, **après** ceux de 14b–14e (`reseau_code` compris),
  dans cet ordre : `<executeur>` `^(conteneur|hote_bac_a_sable)$` (défaut `conteneur`) et `<licence>` `^(-|B1|B2|B3)$`
  (défaut `-`) ; absents = comportement actuel (tests de T4, 14b, 14d, 14e inchangés). L'implémenteur fixe les positions
  exactes après relecture de l'état livré de l'enveloppe et les écrit dans son en-tête.
  - Exécuteurs : fonctions `executeur_conteneur_lancer`/`_arreter` (le `docker run`/`docker kill` actuels) et
    `executeur_hote_lancer`/`_arreter` (14h ; d'ici là : code 2 « exécuteur hôte non installé ») ; places, jetons, file,
    laisse, `timeout`, coupe à 50 Mo, préfixe `| `, `#fin`, nettoyage : **communs**, jamais dupliqués.
  - Famille `unity`, exécuteur `conteneur` : image `myiafactory/tests-unity-<version>` (motif) ; `licence` ≠ `-` exigée
    (sinon 2) ; montages de la table fermée : `$HOME/.config/unity3d/Unity/licenses:/licence/droits:ro`, et
    `$HOME/.local/share/unity3d/Unity/Unity_lic.ulf:/licence/ulf:ro` s'il existe ; B2 ajoute `/etc/machine-id:/etc/machine-id:ro`
    et `--hostname "$(hostname)"` ; B3 : réseau `--internal` du mandataire (14d) avec la liste des hôtes de licence passée
    par le poste **et** validée par motif de nom d'hôte, accepté seulement si `tests.adoption.reseau_licence == "accorde"`
    (route) ; jamais `unityhub`, jamais une socket ; `--tmpfs /tmp:size=6g`.
- Produces (`entree-unity.sh`, dans le conteneur) : copie `/licence/*` vers `$HOME/.config/unity3d/Unity/licenses/` et
  `$HOME/.local/share/unity3d/Unity/` (0600) ; lance le tableau de la commande ; le journal reste dans `/tmp/unity.log` ;
  relaie un résumé : lignes filtrées (motif `licen|entitlement|serial|token|ulf`, sans casse, retirées) et bilan du XML
  (`total`, `passed`, `failed`, 20 noms d'échecs) ; code : celui de l'éditeur (0, 2, 3), **81** si un motif de licence
  refusée est trouvé (`grep -qiE`, jamais affiché), **82** si le XML est absent ou `total == 0`.
- Produces (`tests_images`) : bloc `unity` (`FROM <image GameCI>@<digest>` ; digest lu par la sonde, motif
  `^sha256:[0-9a-f]{64}$`) ; `taille_propre_mo(image)` pour le budget (couches non partagées), utilisée par `--ramasser`.
- [ ] **Step 1: Write the failing tests** : `test_sans_executeur_comme_avant` (arguments de 14e seuls → mêmes appels
  `docker` qu'avant) ; `test_executeur_inconnu_refuse` (→ 2, rien écrit) ; `test_unity_montages_de_licence_en_lecture_seule`
  (B1 : les deux `:ro`, `--network none`, aucun `machine-id`) ; `test_b2_identifiants_de_machine` ;
  `test_b3_refuse_sans_accord` ; `test_jamais_unityhub_ni_socket_montes` (aucun argument `docker` ne contient `unityhub`,
  `.sock`, `/run/user`) ; `test_journal_unity_filtre` (journal factice avec `LICENCE-FACTICE-1` sur une ligne « license »
  → absente de la sortie relayée) ; `test_licence_refusee_code_81` ; `test_zero_test_n_est_pas_un_succes` (XML
  `total="0"`, éditeur rend 0 → 82) ; `test_bilan_des_resultats` (3 tests dont 1 échec → code 2, nom de l'échec relayé) ;
  `test_hote_non_installe_code_2` ; `test_taille_propre_pour_le_budget` (image dérivée de 27 Go apparents, 40 Mo propres →
  40 Mo comptés) ; `test_rendu_unity_par_digest` (aucun `FROM` par étiquette seule).
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_serveur_tests_unity` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_serveur_tests_unity test_serveur_tests_enveloppe test_serveur_tests_deps test_tests_jetons test_tests_images_derivees` → ok.
- [ ] **Step 5: Commit** : chemins ci-dessus ; « Tests au serveur : exécuteurs de l'enveloppe et Unity en conteneur ».
  Relecture séparée.

### Task 14h: L'exécuteur `hote_bac_a_sable` et son confinement (option A ; code sensible : code non fiable sur l'hôte)

Implémentée à l'avance (tests avec faux seulement) mais **installée au serveur seulement si J13 rend `hote`** (J14).

**Files:**
- Create: `serveur_ovh/unity-bac-a-sable.sh` (script racine, déposé en `/usr/local/lib/myiafactory/unity-bac-a-sable.sh`
  par l'étape), `serveur_ovh/sonde-bac-a-sable.sh` (sonde d'audit de J14, lancée **dans** l'unité à la place de l'éditeur)
- Modify: `serveur_ovh/mise_en_place.sh` (étape `unity_bac_a_sable`, usage et liste des étapes), `outils/serveur_installation.py`
  (`FICHIERS_ETAPE`, `EMPREINTE_FICHIERS`, `MARQUEURS`), `serveur_ovh/taches/lancer_tests.sh` (`executeur_hote_lancer`/`_arreter`)
- Test: `tests/test_serveur_unity_bac_a_sable.py` (≈ 3 s ; faux `systemd-run`, `systemctl`, `sudo`, `setfacl`, `useradd`,
  `visudo`, `id` dans `PATH`)

**Interfaces:**
- Produces (étape `unity_bac_a_sable`, `--simuler` connu) : utilisateur système `unity-tests` (sans shell, sans mot de passe,
  hors `docker`/`kvm`/`sudo`), `/var/lib/unity-tests` 0700 ; script racine 0755 propriété root ; règle
  `/etc/sudoers.d/myiafactory-unity` limitée à `/usr/local/lib/myiafactory/unity-bac-a-sable.sh` (vérifiée par `visudo -c`,
  retirée si refus) ; ACL `u:unity-tests:r` sur les **seuls** fichiers de licence et ACL par défaut sur `licenses/` ;
  vérifie que `~/agent-identifiants`, `~/.ssh`, `~/taches` sont 0700 (sinon `bloque` avec la raison) ; marqueur
  `~/.myiafactory/unity-bac-a-sable.version` **écrit par l'audit J14 seulement**, pas par l'étape.
- Produces (`unity-bac-a-sable.sh`, root) : `lancer <id> <cpus> <memoire_mo> <duree_s> <version> <reseau>` et `arreter <id>` ;
  motifs sur chaque argument (id de la tranche A, version Unity, `reseau` `^(aucun|licence)$`) ; refuse si l'éditeur
  `/opt/unity/editors/<version>/Editor/Unity` (ou la version de repli décidée) est absent ; crée
  `/var/lib/unity-tests/campagnes/<id>/` ; `systemd-run --pipe --wait --collect --unit unity-tests-<id>` avec la liste
  **figée** de propriétés de la conception § 5.16 (`User=unity-tests`, `ProtectHome=tmpfs`, `ProtectSystem=strict`,
  `PrivateTmp`, `PrivateDevices`, `NoNewPrivileges`, `CapabilityBoundingSet=`, `ProtectProc=invisible`, `ProcSubset=pid`,
  `RestrictNamespaces`, `SystemCallFilter=@system-service`, `InaccessiblePaths` des sockets Docker, `ReadWritePaths` de la
  campagne seule, `BindReadOnlyPaths` de l'éditeur et des fichiers de licence vers le `HOME` de l'unité, `PrivateNetwork=yes`
  ou, avec `reseau=licence`, `IPAddressDeny=any` + `IPAddressAllow=<mandataire>`, `MemoryMax`, `MemorySwapMax=0`,
  `CPUQuota`, `TasksMax=2048`, `LimitNOFILE=8192`, `RuntimeMaxSec`) ; l'archive est extraite **dans** l'unité ; `Library/`
  par overlay dans un espace de montage privé, à défaut `cp --reflink=auto` ; dossier effacé à la fin ; balaie les unités
  `unity-tests-*` de plus de 6 h.
- Produces (`lancer_tests.sh`) : `executeur_hote_*` = `sudo -n /usr/local/lib/myiafactory/unity-bac-a-sable.sh lancer|arreter …`,
  sortie traitée par le chemin commun ; la version d'éditeur du profil, ou la version de repli décidée par le Directeur
  (`tests.profil_force.unity_version_hote`) avec la ligne d'avertissement « Éditeur <v> au lieu de <v projet> : résultats
  indicatifs » en tête de la sortie.
- [ ] **Step 1: Write the failing tests** : `test_proprietes_figees_de_l_unite` (le faux `systemd-run` journalise ses
  `-p` : chacune de la liste présente, `User=unity-tests`, `ProtectHome=tmpfs`, aucun `BindPaths` hors campagne) ;
  `test_arguments_hostiles_refuses` (id `../x`, version `6000.6.7f1;id`, `reseau=bridge` → 2, aucun `systemd-run`) ;
  `test_licence_liee_jamais_copiee` (aucun `cp` de `licenses/` ni d'`.ulf` vers la campagne ; liaison en lecture seule) ;
  `test_reseau_prive_par_defaut` ; `test_arreter_arrete_l_unite` (laisse fermée → `arreter <id>` → `systemctl stop
  unity-tests-<id>`) ; `test_version_absente_refusee` ; `test_avertissement_version_de_repli` ; `test_etape_simulee`
  (`--etape unity_bac_a_sable --simuler` : JSON, aucun `useradd`) ; `test_etape_refuse_dossiers_lisibles`
  (`~/agent-identifiants` en 0755 → `bloque`) ; `test_sudoers_verifie` (faux `visudo -c` en échec → règle retirée, `bloque`).
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_serveur_unity_bac_a_sable` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_serveur_unity_bac_a_sable test_serveur_tests_unity test_serveur_installation` → ok.
- [ ] **Step 5: Commit** : chemins ci-dessus ; « Tests au serveur : bac à sable Unity sur l'hôte (option A) ». Relecture
  séparée (le code des tests tourne sur l'hôte).

### Task 14i: Capacités `unity-licence` et `unity-bac-a-sable`, choix automatique, expérience et bureau (code sensible : choix de l'exécuteur)

**Files:**
- Create: `outils/tests_unity_essai.py` (outil du contrôleur pour J13/J14), `tests/test_tests_unity_choix.py` (≈ 1 s)
- Modify: `outils/serveur_capacites.py` (deux capacités), `outils/serveur_tache.py` (`choisir_serveur` : exigence `nom=etat`),
  `serveur_ovh/mise_en_place.sh` (étape `unity_licence_etat` : lit un état sur l'entrée standard, écrit le marqueur),
  `outils/tests_serveur.py` (choix de l'exécuteur), `outils/tests_adoption.py` (verdict Unity, code 82), `bureau/web/ui/`
  (carte du serveur), `orchestrateur/consignes.md` et `bureau/releve.py` (étape humaine « Reconnecter Unity Hub »,
  « Installer 6000.6.7f1 par Hub »)

**Interfaces:**
- Produces (`serveur_capacites`) :
  - `Capacite("unity-licence", "Licence Unity de Hub pour les tests", ("base",), "unity_licence_etat",
    "<sonde : lit ~/.myiafactory/unity-licence.etat ; test -s des fichiers de licence ; imprime conteneur|hote|absente>", …,
    installable=False, raison_non_installable="licence de Unity Hub : reconnecter Hub par la session graphique")` ; état et
    variante (`B1`/`B2`/`B3`) gardés dans l'état local du serveur.
  - `Capacite("unity-bac-a-sable", "Bac à sable de l'hôte pour les tests Unity (option A)", ("unity-licence", "session-graphique"),
    "unity_bac_a_sable", "<sonde : utilisateur, script racine, règle sudoers, marqueur d'audit, éditeur lisible>", …)`.
- Produces (`serveur_tache.choisir_serveur`) : une exigence `"unity-licence=conteneur"` n'est satisfaite que par cet état
  relevé ; les exigences sans `=` gardent leur sens.
- Produces (`tests_serveur.executeur_pour(profil, etat_serveur) -> Tuple[str, Optional[str]]`, pur) : règle exacte du § 5.16 :
  `conteneur` + variante ; `hote_bac_a_sable` seulement si `unity-licence=hote` **et** `unity-bac-a-sable` présente ;
  sinon `Repli` (« licence Unity absente » / « bac à sable Unity absent : rien ne tourne sur l'hôte sans lui ») ; code 81 au
  retour → état `absente` noté (étape `unity_licence_etat`) et étape humaine posée, une fois.
- Produces (`tests_unity_essai.py`) : `py -3.12 outils/tests_unity_essai.py --serveur-id <id> --dossier <projet> --test <nom>
  [--variantes B1,B2[,B3]] [--hote]` : inventaire des **noms** et tailles (`find … -printf '%p %s\n'` sur les dossiers de
  licence, `ss -xl` filtré sur le client de licence ; jamais un contenu), puis une campagne `-testFilter <nom>` par
  variante, à froid puis à chaud, par `tests_serveur.executer(…, forcer=True, evaluation=True, executeur=…, licence=…)` ;
  verdict : `conteneur` (première variante réussie, ≥ 1 test exécuté), `hote` (81 dans toutes les variantes permises),
  `indetermine` (82, erreur de compilation, autre code : **rien n'est écrit**) ; écrit l'état par `unity_licence_etat` ; B3
  seulement si `--variantes` la cite et que la décision QU1 est `accorde` ; `--hote` (J14) lance d'abord
  `sonde-bac-a-sable.sh` par l'exécuteur hôte et n'écrit le marqueur d'audit que si toutes ses vérifications passent ;
  relevés (durées, pic mémoire, taille de `Library/`) écrits dans `~/MyIAFactory/tests-unity-essai.json`.
- Produces (bureau) : carte du serveur « Licence Unity : dans le conteneur (B1) / sur l'hôte, bac à sable / absente —
  raison » et « Bac à sable Unity : prêt / absent » (`textContent`) ; décision `environnement` non autonome « Reconnecter
  Unity Hub sur le serveur » (`lien` vers la page de gestion des licences de la documentation de Unity Hub, vérifié par
  l'implémenteur ; `mode_operatoire` de 5 étapes du § 5.16 ; `releve.mode_operatoire_ok`) avec le bouton « Vérifier la
  licence » (sonde, autonome) ; même forme pour « Installer 6000.6.7f1 par Hub » (QU2) ; verdict d'adoption d'un projet
  Unity qui nomme l'exécuteur et, pour A, le risque résiduel en une ligne.
- [ ] **Step 1: Write the failing tests** : `test_conteneur_choisi` ; `test_hote_jamais_sans_bac_a_sable` (`hote` sans la
  capacité → `Repli` dit, aucun appel d'exécuteur hôte) ; `test_hote_avec_bac_a_sable` ; `test_absente_repli_et_etape_humaine`
  (décision posée une fois, `mode_operatoire_ok` vrai) ; `test_code_81_rend_la_licence_absente` ; `test_exigence_nom_etat`
  (`choisir_serveur(requises=("unity-licence=conteneur",))` refuse un serveur `hote`) ; `test_essai_ordre_des_variantes`
  (B1 rend 81, B2 rend 0 avec 1 test → `conteneur`, variante B2, B3 jamais tentée) ; `test_essai_indetermine_n_ecrit_rien`
  (82 → aucune écriture d'état) ; `test_b3_jamais_sans_accord` ; `test_inventaire_noms_seulement` (aucune commande
  `cat`, `head`, `base64`, `xxd`, `cp` dans le `_bash` de l'inventaire) ; `test_marqueur_audit_seulement_si_tout_passe` ;
  `test_python_du_projet_ne_demande_pas_la_licence` (la commande `python` de `sur-la-route` part par `tests-image` même
  avec `unity-licence=absente`).
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_unity_choix` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_tests_unity_choix test_serveur_capacites test_serveur_tache test_tests_adoption test_releve` → ok.
- [ ] **Step 5: Commit** : chemins ci-dessus ; « Tests au serveur : licence Unity, choix de l'exécuteur et bureau ».
  Relecture séparée.

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

### Task 15b (réécrite) : Adoption par projet : analyse, profil, image, échauffement, évaluation — demande du Directeur du 2026-11-23, amendée le même jour (« qu'importe le projet »)

Le mécanisme sert **tout** projet (conception § 5.15). Plus aucun statut `non_supporte` : un projet hors Python/Node passe
par son profil (14a), son image (14b, 14c) et ses dépendances (14d) ; il ne reste au poste que `non_deportable` (raison
N1–N6) ou par choix du Directeur, toujours dit.

**Files:**
- Create: `outils/tests_adoption.py` (Python 3.12, stdlib), `tests/test_tests_adoption.py` (≈ 0,8 s ; route, construction et
  échauffement simulés par des faux ; fixtures de 14a ; aucun accès serveur)
- Modify: `outils/tests_serveur.py` (`evaluation`, contrôle de l'empreinte du profil adopté),
  `bureau/deport_types.py` (`ANDROID["tests"]` : `lieux=("poste", "github", "serveur")`), `orchestrateur/outil.py`
  (commande `evaluer-tests-serveur`), `orchestrateur/consignes.md` (décisions `tests_serveur_adoption`,
  `tests_image_derivee`, `tests_reseau_echauffement`, `tests_profil`), `bureau/demandes.py` / `bureau/releve.py`
  (validation des réponses), `skills/installer/SKILL.md` (l'étape d'installation), `bureau/web/ui/` (cartes : Dockerfile
  et listes par `textContent` seulement), docs.

**Interfaces:**
- Consumes : `tests_profil.analyser`, `empreinte_profil` (14a) ; `tests_images.choisir_image`, `rendre_dockerfile`,
  `image_connue` (14b, 14c) ; `tests_serveur.executer(…, forcer=True)` (T6 ; 15b y ajoute `evaluation=True` : profil
  non encore adopté admis pour cette seule campagne, durée de la famille, aucune ligne de mesure ordinaire) ; `deport_types.refus_route`
  (T7) ; `tests_mesures` (durée, nombre de tests).
- Produces :
  - `etapes(racine, profil, etat) -> List[str]` : ce qui reste à faire, dans l'ordre (`image`, `sdk_android`, `reseau`,
    `echauffement`, `evaluation`) ; pur.
  - `evaluer(racine, commande=None, route=…, construire=…, delai_s=None, lire=None) -> dict` : analyse → profil ; `non_deportable`
    → rien n'est envoyé ; image absente → `image_a_construire` (rien de construit sans la réponse `construire`) ; réseau
    d'échauffement requis et non accordé → `image_a_construire` avec `attend: "reseau"` ; sinon UNE campagne par la route
    **sans repli ni nouvelle tentative**, échauffement compris ; rend `{"statut": "passe"|"echoue"|"image_a_construire"|"non_deportable"|"injoignable"|"trop_long", "profil", "empreinte_profil", "image", "duree_s", "nb_tests", "echecs": [≤ 20 {"nom", "classe"}], "raison", "attend"}`.
  - `classer_echec(nom, extrait) -> str` : `windows` (chemins `C:\`, `\\`, registre, `.exe`, `cmd`), `reseau`, `secret`,
    `autre` ; pur, sur 4 Ko d'extrait au plus.
  - `marqueur_pour(famille) -> str` : le marqueur conseillé par pile (`plateforme_tests.windows_seulement` en Python ;
    `Assume.assumeTrue` JUnit 4 ; `@EnabledOnOs(OS.WINDOWS)` JUnit 5 ; `it.skipIf` Vitest ; `[SkippableFact]`/`Skip` .NET ;
    `#[cfg(windows)]` Rust ; `t.Skip` Go).
  - Réglages : `reglages.json` > `tests.adoption = {"date", "statut", "empreinte_profil", "image", "reseau_echauffement": "accorde"|"refuse"|null, "duree_s", "nb_tests"}` — écrit par le bureau/l'outil, jamais par l'agent (même garde que le budget) ; l'accord reste `deport.lieux["tests"]` (R10).
  - Décisions de Direction : `tests_image_derivee` (14c : `construire` / `plus_tard` / `garder_poste`) ;
    `tests_reseau_echauffement` (Q4 : registres autorisés, durée, « le code de construction du projet tourne avec ce
    réseau » ; `accorder` / `refuser`) ; `tests_serveur_adoption` : `passe` → « Activer les tests sur le serveur »
    (`activer` / `plus_tard`) ; `echoue` → les 20 premiers échecs classés et le marqueur conseillé, `marquer` (tâche
    **proposée**, jamais créée seule), `garder_poste`, `plus_tard` ; `non_deportable` → la raison N1–N6 et `garder_poste` ;
    `injoignable` / `trop_long` → information et `reessayer` / `garder_poste`. **Jamais d'activation automatique.**
  - `outil.py evaluer-tests-serveur [--dossier D]` : lance `evaluer`, pose la décision qui convient, écrit `tests.adoption` ;
    rappelée après chaque réponse `construire` / `accorder` (étape suivante) ; la construction elle-même passe par
    `construire_image_tests.sh` (14c), contrôleur ou bureau, jamais par l'agent.
  - Réévaluation : à chaque campagne routée, `empreinte_profil` différente de `tests.adoption.empreinte_profil` → la route
    passe au poste **une fois en le disant** (« profil changé : nouvelle évaluation proposée ») et pose la décision ; jamais
    de campagne au serveur sur un profil non évalué.
  - L'étape `installer` de la skill appelle `evaluer-tests-serveur` après la mesure de départ des tests économes ; un projet
    déjà installé est évalué à sa première campagne de plus de 60 s (migration) ou par le bouton « Évaluer les tests sur le
    serveur » de la carte du projet.
- [ ] **Step 1: Write the failing tests** : `test_toutes_les_familles_ont_un_chemin` (chaque fixture de 14a sauf N1/N2 →
  un statut autre que `non_deportable`) ; `test_non_deportable_n_envoie_rien_et_dit_la_raison` (`dotnet-framework`,
  `xcode`) ; `test_image_a_construire_ne_construit_rien_sans_reponse` ; `test_reseau_code_attend_l_accord` (Gradle sans
  `reseau_echauffement`) ; `test_myfridgecleaner_chemin_complet` (fixture `gradle-android`, faux : image `tests-android`
  présente, échauffement réussi, campagne 0 → `passe`) ; `test_echoue_classe_et_propose_le_marqueur` (20 noms au plus,
  `windows` pour un `C:\Users` dans l'extrait, marqueur JUnit pour Gradle) ; `test_injoignable_ne_replie_pas_et_ne_reessaie_pas` ;
  `test_trop_long_selon_la_famille` (Gradle : 2 700 s) ; `test_decision_ne_s_active_jamais_seule` ;
  `test_adoption_ecrite_par_le_bureau_pas_par_l_agent` ; `test_reevaluation_quand_l_empreinte_change` (verrou modifié →
  poste une fois, décision posée) ; `test_android_tests_lieu_serveur` (`ANDROID["tests"]` admet `serveur`, `emulateur`
  non).
- [ ] **Step 2: Run to verify they fail** : `py -3.12 outils/tests_paralleles.py test_tests_adoption` → ÉCHEC.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run to verify they pass** : `py -3.12 outils/tests_paralleles.py test_tests_adoption test_deport_types test_demandes test_releve` → ok.
- [ ] **Step 5: Commit** : chemins ci-dessus ; « Tests au serveur : adoption par projet, tout type de projet ». Code
  sensible : relecture (elle décide quels projets envoient leur code au serveur et quand le réseau est demandé).

### Task 15c (ajoutée le 2026-11-23, demande du Directeur) : le serveur comme poste de développement — build et test pilotés par un agent du serveur

Objectif : qu'un agent qui travaille AU SERVEUR (tranche B) puisse compiler, lancer les tests et bâtir un APK/une build avec le même moteur
que la route des tests (profils 14a, images 14b/14c, caches 14d, jetons 14e, Unity 14g–14i), sans retomber au poste. Limites assumées :
pas de GPU (rendu PlayMode, captures) ni de macOS/iOS : ces cas restent au poste, raison dite.
**Files (à préciser à l'écriture du brief, après 14g–15b) :** outils de l'agent serveur (`outils/serveur_agent.py`, consigne de départ),
`serveur_ovh/taches/pont_hote.py` (verbes `construire`/`tester` côté hôte), `moteur/executeur_serveur.py`.
**Produces :** verbes du pont `tester <commande>` et `construire <cible>` qui réutilisent `tests_serveur`/`lancer_tests.sh` depuis le
serveur (sans repasser par le poste), profil + image + cache + jetons identiques ; sortie en flux à l'agent ; APK/artefacts rapatriés
par le chemin existant ; mêmes durcissements et même consentement par projet.
**Tests :** faux pont/faux docker ; essai réel J15 (build Android depuis un agent du serveur) puis J16 (Unity, après 14g–14i).

### Task 15d (ajoutée le 2026-11-23, demande du Directeur) : « Release signé » — le serveur compile, le poste signe

Option 1 retenue (la clé de signature ne quitte jamais le poste ; l'option 2, clé déposée au serveur, reste possible plus tard si le projet utilise
Play App Signing). Légère par construction : elle réutilise 14d–15c.
**Produces :** (1) le serveur construit la release NON signée (`assembleRelease`/`bundleRelease` sans `signingConfig` ; le projet n'a pas à changer :
l'enveloppe passe une propriété qui désactive la signature, ou lit l'APK `*-release-unsigned.apk`) ; (2) rapatriement de l'artefact par le chemin
existant (octets, pas de chemin) ; (3) étape locale `zipalign` + `apksigner sign` (AAB : `jarsigner`) avec les outils du SDK du poste, mot de passe saisi
par le Directeur au poste (jamais lu, stocké ni journalisé par l'outil) ; (4) action « Release signé » du bureau : build au serveur puis signature locale,
lieu `serveur` ; la signature n'est jamais exécutée par un agent. **Tests :** faux serveur/faux `apksigner` ; essai réel J15b sur FM_Stats.

### Task 15e (ajoutée le 2026-11-23, demande du Directeur) : réglage « signature des APK » par projet

Pour un projet Android/Flutter, le choix de la signature appartient à l'utilisateur : nouveau champ dans les paramètres « projet » (page Réglages à trois niveaux : global / type / projet ; valeur par défaut = la plus sûre) : (a) **le serveur signe avec la clé de debug copiée** (`~/android-signature/debug.keystore`, montée en lecture seule dans le conteneur de l'agent : c'est ce qui est codé pour FM_Stats sur la branche `flutter-build-apk` en attendant) ; (b) **le serveur construit, le poste signe** (tâche 15d) ; (c) **aucune clé ne quitte le poste**, build non signée ou clé jetable. Le montage de la clé de debug n'a lieu que si le réglage du projet choisit (a). **Files :** réglages (`bureau/reglages*.py`, page Réglages), `moteur/executeur_serveur.py` (demande : `signature`), `serveur_ovh/taches/lancer_agent.sh`. **Tests :** faux serveur ; défaut sans montage.

### Task 15f (ajoutée le 2026-11-23, demande du Directeur « faciliter cela ») : commandes uniques pour les étapes standard des agents du serveur

Au serveur personne n'approuve une commande : toute commande composée/préfixée (`cd … && flutter …`, `timeout …`, `VAR=… flutter …`) est refusée et l'agent s'arrête. Fournir des commandes COURTES et FIXES qui font l'étape complète (placement dans le dossier du projet, programme et arguments figés) : pour Flutter `analyser-flutter`, `tester-flutter`, `construire-apk` (arguments énumérés : `release`|`debug`), scripts du dépôt (`serveur_ovh/agent-outils/`), déposés par le poste à chaque lancement et montés en lecture seule sur `/opt/outils` (aucune reconstruction d'image), `PATH` du conteneur ; une règle `Bash(<commande>:*)` par commande (jamais `Bash` seul ; `ouvrir_outil` existant). Aucun shell libre, aucun argument libre. **Tests :** faux docker, motifs d'arguments refusés. Essai réel : Lucas, `construire-apk`.

### Task 15g (ajoutée le 2026-11-23) : profil d'outils par type de projet (Réglages, niveau « type »)

Les programmes ouverts aux agents d'un type de projet (Flutter : `analyser-flutter`, `tester-flutter`, `construire-apk` et `flutter` ; Gradle : …) se règlent une fois dans la page Réglages (niveau « type », valeur par défaut sûre) ; tout agent du serveur créé (`parallelisme`/`synchroniser_equipe`) reçoit ce profil : plus de décision « ouvrez-lui l'outil » fiche par fiche. Même famille que le réglage « signature des APK » (15e).

### Task 16: Documentation, CLAUDE.md et suite complète (contrôleur)

**Files:**
- Create: `docs/serveur-tests.md` (route, repli R1–R5, places, limites, sécurité, protocole et N mesuré, dépannage :
  `--local`, `--serveur`, fichier d'injoignable ; amendement : profils par famille, catalogue d'images et images dérivées,
  caches et échauffement, jetons de mémoire, liste N1–N6 des non déportables, adoption et ses décisions ; Unity : fichiers
  de licence, options B et A, états de `unity-licence`, bac à sable et son risque résiduel, étapes humaines)
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
- [ ] **J5** (Q2 = oui) : profil Python et profil Node par le mécanisme général (14a, 14d) : un projet Node enregistré, `python lancer.py tests --dossier <p> -- npx vitest run` deux fois (échauffement puis cache, aucun `deps-*` la seconde fois) ; un projet Python à dépendances `pip` (roues seulement), même double passage.
- [ ] **J6** : enregistrer le dépôt MyIAFactory au bureau et poser `deport.lieux.tests = "serveur"` au défaut du bureau (geste du Directeur au bureau) ; `py -3.12 outils/tests_paralleles.py --touches` part au serveur.
- [ ] **J7** : repli : `serveurs-etat.json` d'une copie de `dossier_etat` marqué injoignable → une campagne passe au poste avec la ligne de repli, sans connexion.
- [ ] **J8** (après 14b, 14d ; Q4 pour le réseau de l'échauffement Gradle) : `plateforme serveurs installer <id> tests-serveur-android --accord` → `tests-android` « fait » ; MyFridgeCleaner enregistré : `evaluer-tests-serveur --dossier <MyFridgeCleaner>` → échauffement en ligne (wrapper Gradle 9.3.1 vérifié, dépendances), puis `./gradlew testDebugUnitTest --offline` au serveur ; relever durée, pic mémoire, taille du cache ; verdict `passe` attendu (à défaut : liste des échecs classés).
- [ ] **J9** (après 14c, décision `tests_image_derivee` du Directeur) : une image dérivée (Godot 4.7 pour ZooRunner, ou Node d'un autre majeur) : construction (durée, taille), seconde demande à empreinte égale → aucune construction ; `--ramasser` avec un budget abaissé → l'image inutilisée part, celle d'un conteneur vivant reste.
- [ ] **J10** (après 14d) : échauffement puis campagne hors ligne sur un projet du J5 ou J8 : le volume `overlay` fonctionne (sinon : bascule sur la lecture seule et `GRADLE_RO_DEP_CACHE`, notée) ; somme du cache identique avant et après la campagne.
- [ ] **J11** (après 14e) : `tests_mesure_places.py --mixte gradle:2,python:2` puis la même pendant une émulation de recette → pics mémoire, durées ; `budget_tests_mo` confirmé ou corrigé au bureau, écrit dans `docs/serveur-tests.md`.
- [ ] **J12** (réécrit, après J1–J2, aucune licence) : `sur-la-route` enregistré au bureau ; ses tests Python par le profil `python` : `python lancer.py tests --serveur --dossier <sur-la-route> -- python3 -m unittest discover -s Tools/factory/tests` (ou la commande de son catalogue) → durée, verdict ; l'instantané ne contient aucun fichier de licence (liste des noms relevée).
- [ ] **J13 — expérience B** (après 14f, 14g, 14i ; feu vert du Directeur ; aucun changement de l'hôte hors l'image dérivée) : construire `myiafactory/tests-unity-6000.6.7f1` (décision `tests_image_derivee`, base GameCI présente, aucun tirage de 27 Go) ; échauffement de `Library/` (réseau UPM de Q4 avec `github.com` pour UniVRM, accord du projet) ; `py -3.12 outils/tests_unity_essai.py --serveur-id <id> --dossier <sur-la-route> --test <un test de Assets/Editor/Tests> --variantes B1,B2` → inventaire des noms, durées à froid et à chaud, pic mémoire, taille de `Library/`, verdict écrit dans `unity-licence`. Si B1 et B2 rendent 81 et que le journal (filtré) montre un appel aux serveurs d'Unity : **poser QU1** au Directeur ; si oui, `--variantes B3`. Verdict `indetermine` (82, compilation) : corriger puis refaire, jamais conclure à A. Rien ne reste hors image et cache voulus.
- [ ] **J14 — confinement A** (**seulement si J13 rend `hote`** ; après 14h ; feu vert du Directeur) : poser QU2 et faire l'étape humaine d'installation de 6000.6.7f1 par Hub dans `/opt/unity/editors` (ou décision de repli 6000.6.10f1) ; `plateforme serveurs installer <id> unity-bac-a-sable --accord` ; `tests_unity_essai.py … --hote` : audit par `sonde-bac-a-sable.sh` (lecture refusée de `~/agent-identifiants`, `~/.ssh`, `~/taches`, d'une autre campagne, de `~/.config/unityhub`, de `/run/docker.sock` ; connexion sortante refusée ; `TasksMax`, `MemoryMax`, `RuntimeMaxSec` effectifs ; laisse qui arrête l'unité ; ACL limitées aux fichiers de licence, gardées après un rafraîchissement par Hub) ; puis le même test EditMode par l'exécuteur hôte, durée relevée ; marqueur d'audit posé seulement si tout passe ; sinon `unity-bac-a-sable` reste absente et les tests Unity restent au poste, dit au bureau.

## Auto-relecture

1. **Couverture de la conception** : § 5.1 → T7, T8 ; § 5.2 → T2, T4 (extraction, nettoyage) ; § 5.3 → T3 ; § 5.4 → T4,
   T5, T6 ; § 5.5 → T4 (places, file, limites), T13 (N, protocole) ; § 5.6 → T6 (note d'attente, mesure) ; § 5.7 → T7 ;
   § 5.8 → T14d ; § 5.9 → T1, T9–T12 ; § 5.10 → T15, T16 ; § 5.11 → T14a ; § 5.12 → T14b, T14c ; § 5.13 → T14d ;
   § 5.14 → T14a (ressources, N1/N2/N6), T14e (jetons, limites), T14f (PlayMode en N3) ; § 5.15 → T15b ; § 5.16 → T14f
   (profil, exclusions), T14g (exécuteurs, option B), T14h (option A), T14i (capacités, choix, expérience, bureau) ;
   § 6 → T3, T4, T14c, T14d, T14g, T14h ; § 8 → T17 (J1–J14).
2. **Pas** : chaque étape nomme le fichier, la signature et les valeurs ; aucun corps de fonction ; T9–T12 partagent une
   forme et nomment leurs modules et le correctif attendu.
3. **Noms** : `refus_route`, `routee_au_serveur`, `executer_en_flux`, `fin_serveur`, `tests_serveur.executer(…, forcer)`,
   `LIMITES`, `module_pas_encore_linux`, `places_tests` sont les mêmes partout ; amendement : `Profil`, `analyser`,
   `empreinte_profil`, `empreinte_image`, `empreinte_deps`, `choisir_image`, `rendre_dockerfile`, `etiquette_derivee`,
   `budget_tests_mo`, `budget_images_go`, `budget_caches_go`, `tests.adoption.empreinte_profil` idem ; amendement Unity :
   `unity-licence` (états `conteneur`/`hote`/`absente`), `unity-bac-a-sable`, exécuteurs `conteneur`/`hote_bac_a_sable`,
   variantes `B1`/`B2`/`B3`, codes 81/82, `executeur_pour`, `exclus_de_famille`, `EXCLUS_SEGMENTS` idem.
4. **Review Focus** : chaque ligne a son test dans la tâche qui possède le code (T2, T4, T5, T6, T7 ; 14a, 14c, 14d, 15b ;
   14f, 14g, 14h, 14i).
5. **Proportion** : plan plus long que la conception, sans code ; les tests sont des noms et des assertions.
6. **Amendement « qu'importe le projet »** : plus de `non_supporte` ; chaque famille a un chemin (catalogue ou image
   dérivée) ; seuls N1–N6 restent au poste, raison dite ; les tests instrumentés restent aux actions de l'émulateur ; les
   arguments ajoutés à l'enveloppe de T4 sont facultatifs, ses tests restent valides ; Q1 à Q5 décidées (Q3 = B puis A,
   Q4 = réseau limité projet par projet, Q5 = 30 Go et 40 Go, valeurs par défaut de 14c/14d).
7. **Amendement Unity** : la licence ne part jamais (14f) et n'est jamais affichée (14g) ; B est essayée d'abord et son
   verdict vient d'une expérience réelle (J13), jamais d'une supposition ; A n'est jamais choisie sans `unity-bac-a-sable`
   ni sans l'audit J14 ; 0 test n'est jamais une réussite ; les tests Python de `sur-la-route` partent tout de suite, sans
   licence (J12) ; PlayMode reste en N3. Restent au Directeur, au moment venu : QU1 (sortie vers les hôtes de licence si B
   l'exige) et QU2 (installer 6000.6.7f1 par Hub si A).
