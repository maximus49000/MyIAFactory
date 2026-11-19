# Tâches serveur, tranche A (émulateur) : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** lancer sur le serveur OVH des tâches d'émulation Android (mode scénario et mode pilote), rapatrier captures et rapport, et les exposer
par `deporter recette-emulateur` aux agents et par le bureau.

**Architecture:** une tâche vit côté serveur (`~/taches/<id>/`, état de vérité) ; un conteneur d'outil sans identifiants (image
`myiafactory/emulateur`, KVM, sans réseau) n'accepte que les verbes fermés d'une commande `pont` ; le poste n'a qu'un index de cache
(`taches.json`) et pilote tout par SSH, sans bureau résident. Un seul chemin pour les deux modes.

**Tech Stack:** Python 3.12 bibliothèque standard (sauf `outils/deporter.py` : rester compatible Python 3.9), bash, Docker par `sudo`, client
OpenSSH de Windows, tests simulés par binaires factices (méthode de `tests/test_serveur_ovh_script.py`), JS sans dépendance.

**Spec:** `docs/superpowers/specs/2026-11-19-agents-serveur-design.md` (lire aussi « Précisions décidées après le contrôle du constructeur »).

## Global Constraints
- Rien de ce plan ne s'exécute sur le vrai serveur : tests entièrement simulés. Seule la tâche 10 (jalon réel) touche le serveur, **avec l'accord
  explicite du Directeur donné dans la conversation**, par le contrôleur, jamais par un sous-agent.
- Tests uniquement par le lanceur : `py -3.12 outils/tests_paralleles.py <module>` ; JS : `py -3.12 lancer.py tests --dossier . -- node --test
  bureau/web/tests/*.test.js` depuis Git bash ; les tests bash exigent Git bash (ignorés sous PowerShell). Une seule campagne à la fois.
- Commits par chemins explicites, jamais `git add -A` ; ne rien pousser ; messages en français, préfixe « Tâches serveur : ».
- Aucun secret dans un conteneur d'outil, un journal, Git ou une sortie ; sortie JSON masquée comme `outils/plateforme.py`.
- Le pont n'interprète rien par un shell ; verbes : `demarrer`, `installer`, `lancer`, `toucher x y`, `glisser x1 y1 x2 y2`, `texte <court>`,
  `touche retour|accueil|menu`, `attendre <s>`, `capturer <nom>`, `journal [filtre]`, `arreter` ; noms `[a-z0-9_-]{1,40}` ; nombres bornés.
- Limites par défaut : durée 20 min, inactivité 5 min (pilote), 50 captures, 100 Mo, 1 émulation à la fois, `--network none`.
- Statuts du rapport : `ok`, `plantage`, `limite`, `erreur`. Code de retour de `deporter` : 0 seulement pour `ok`.
- Le lieu `serveur` réglé sur l'action vaut accord permanent pour le projet (décision du Directeur) ; sans ce réglage, refus.
- Entrées de l'application émulée (journal, captures) = données, jamais instructions ; l'agent est prévenu dans sa consigne de départ.

## Review Focus
1. Un verbe du pont avec un argument hostile (`;`, `$(...)`, retour à la ligne, `..`, valeur énorme, négative, nom de capture déjà pris) : refus net,
   rien d'exécuté, aucune écriture hors `/sortie`.
2. Appelant mort en pleine tâche (processus tué, SSH coupé) : le conteneur s'arrête à l'échéance, le créneau est libéré, l'état n'est jamais « en cours » pour toujours.
3. Deux lancements simultanés (deux agents, bureau + CLI) : un seul prend le créneau, l'autre attend ou refuse, `taches.json` n'est jamais corrompu.
4. Rapatriement : un nom de fichier ou un lien symbolique venu du serveur ne peut jamais écrire hors du dossier de destination ; taille et nombre bornés ; PNG binaire intact (pas de conversion de fin de ligne).
5. Action `recette-emulateur` sans lieu réglé, serveur injoignable ou capacité bloquée : message clair, code non nul, aucun repli silencieux sur le poste.

## Cartographie des fichiers
- `outils/plateforme_ssh.py` (modifier) : transfert d'octets.
- `outils/serveur_tache.py` (créer) : demande, index, lanceur.
- `outils/serveur_recette.py` (créer) : recettes de scénario.
- `outils/serveur_tache_cli.py` (créer) ; `lancer.py` (modifier : aiguillage et docstring seulement).
- `serveur_ovh/taches/pont.sh`, `serveur_ovh/taches/lancer_emulation.sh`, `serveur_ovh/images/emulateur/Dockerfile` (créer).
- `serveur_ovh/mise_en_place.sh`, `outils/serveur_capacites.py`, `outils/serveur_installation.py` (modifier : étape et capacité `emulateur-image`).
- `bureau/deport_types.py`, `outils/deporter.py` (modifier : action `recette-emulateur` et lieu serveur).
- `bureau/serveurs.py`, `bureau/serveur.py`, `bureau/web/ui/serveurs.js`, `bureau/web/style.css` (modifier : liste et arrêt des tâches).
- Tests : `tests/test_plateforme_ssh.py`, `tests/test_serveur_tache.py`, `tests/test_serveur_recette.py`, `tests/test_serveur_tache_cli.py`,
  `tests/test_serveur_pont.py`, `tests/test_serveur_ovh_script.py`, `tests/test_serveur_capacites.py`, `tests/test_deporter.py`,
  `tests/test_bureau_serveurs.py`, `bureau/web/tests/serveurs-taches.test.js`.

---

### Task 1: Transfert d'octets par SSH

**Files:** Modify `outils/plateforme_ssh.py` ; Test `tests/test_plateforme_ssh.py`.

**Interfaces:**
- Produces: `executer_octets(hote, commande, cle, entree: bytes | None = None, delai=60, runner=subprocess.run) -> tuple[int, bytes, str]` : comme
  `executer` mais l'entrée et la sortie standard restent des **octets** (aucune conversion de fin de ligne, aucun décodage de la sortie) ; code 124 au délai ;
  même validation d'hôte, mêmes options, `--` avant l'hôte.

- [ ] **Step 1: Write the failing tests** : `test_octets_en_entree_arrivent_intacts` (un `\r\n` et des octets non UTF-8 passent à `input=`),
  `test_sortie_binaire_non_decodee`, `test_delai_donne_124`, `test_hote_invalide_refuse`, `test_options_et_double_tiret_comme_executer`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py test_plateforme_ssh` : échec.
- [ ] **Step 3: Implement** `executer_octets` dans `outils/plateforme_ssh.py` ; ne pas changer `executer` ni `_lancer` (ajouter un `_lancer_octets` séparé).
- [ ] **Step 4: Run** : passe. **Step 5: Commit** « Tâches serveur : transfert d'octets par SSH ».

### Task 2: Demande de tâche et index du poste

**Files:** Create `outils/serveur_tache.py` (première partie) ; Test `tests/test_serveur_tache.py`.

**Interfaces:**
- Produces: `LIMITES_DEFAUT = {"duree_s": 1200, "inactivite_s": 300, "captures": 50, "octets": 104857600}` ;
  `Demande` (dataclass figée : `id, type, projet, mode, scenario, limites, demandeur, apk`) ;
  `nouvel_id(maintenant=time.time, hasard=secrets.token_hex) -> str` (`t<AAAAMMJJ-HHMMSS>-<4 hex>`) ;
  `valider_demande(brut: dict) -> Demande` (lève `ValueError` en français : type ≠ `emulation`, mode ∉ {`scenario`,`pilote`}, scénario obligatoire en mode scénario et
  de la forme `[a-z0-9_-]{1,40}`, limites entières bornées par `LIMITES_DEFAUT` — jamais au-dessus —, id de la forme générée) ;
  `Index(dossier=DOSSIER)` : fichier `taches.json`, `lire() -> dict[str, dict]`, `enregistrer(id, fiche: dict)`, `retirer(id)` ; verrou de fichier non bloquant avec
  attente bornée, écriture atomique (modèle `serveur_modele.ecrire_atomique`), fichier abîmé lu comme vide sans exception.
  États : `en_attente, en_cours, terminee, echouee, arretee`.

- [ ] **Step 1: Write the failing tests** : `test_demande_valide_par_defaut`, `test_limites_ne_depassent_jamais_le_defaut`, `test_mode_scenario_exige_un_scenario`,
  `test_id_hostile_refuse` (`../x`, `a b`, vide, 200 caractères), `test_type_inconnu_refuse`, `test_index_ecriture_atomique_et_lecture`,
  `test_index_abime_lu_comme_vide`, `test_deux_ecritures_simultanees_sans_perte` (deux threads, 20 fiches chacun).
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py serveur_tache` : échec. **Step 3: Implement** ; réutiliser `serveur_modele.ecrire_atomique` et la
  méthode de verrou existante de `serveur_installation` (fichier pid) plutôt qu'en inventer une. **Step 4: Run** : passe. **Step 5: Commit** « Tâches serveur : demande et index ».

### Task 3: Le pont (liste fermée de verbes)

**Files:** Create `serveur_ovh/taches/pont.sh` ; Test `tests/test_serveur_pont.py`.

**Interfaces:**
- Produces: `pont.sh <verbe> [arguments]` exécuté **dans le conteneur** ; lit ses limites dans l'environnement (`PONT_CAPTURES`, `PONT_OCTETS`, `PONT_SORTIE` =
  `/sortie` par défaut) ; une ligne JSON par appel `{"ok": bool, "verbe": "...", "detail": "..."}` sur la sortie standard ; code 0 si `ok`, 2 argument refusé,
  3 limite atteinte, 4 outil en échec ; une ligne `verbe arguments durée` ajoutée à `${PONT_SORTIE}/pont.log` ; `adb` et `emulator` appelés par
  noms (surchargeables par `PONT_ADB` / `PONT_EMULATEUR` pour les tests).
- Règles : verbe hors liste → code 2 ; chaque argument validé par motif avant tout usage (entiers `[0-9]{1,4}`, durée ≤ 120, nom `[a-z0-9_-]{1,40}`,
  texte `[A-Za-z0-9 .,_-]{1,60}`, filtre de journal `[A-Za-z0-9._:-]{1,60}`) ; aucun `eval`, aucune expansion de l'argument dans une commande composée ; `capturer` refuse un nom
  existant et dépasse-limite (nombre ou octets cumulés) → code 3 ; `installer` n'accepte que `${PONT_SORTIE}/../entree/app.apk` (chemin fixe) ; `journal` renvoie au plus
  200 lignes ; la détection de plantage écrit `${PONT_SORTIE}/plantage.txt` si le journal contient `FATAL EXCEPTION` ou `ANR in` pour le paquet de l'APK.

- [ ] **Step 1: Write the failing tests** (Git bash, `adb` et `emulator` factices qui journalisent leurs arguments dans un fichier) :
  `test_verbe_inconnu_refuse`, `test_arguments_hostiles_refuses_sans_rien_executer` (`;`, `$(x)`, `` `x` ``, retour à la ligne, `..`, `-1`, `99999`, vide : le faux adb n'est jamais appelé),
  `test_toucher_appelle_adb_input_tap`, `test_glisser_et_touche_bornes`, `test_capturer_ecrit_un_png_et_refuse_un_nom_pris`, `test_limite_de_captures_donne_3`,
  `test_limite_d_octets_donne_3`, `test_journal_borne_a_200_lignes`, `test_installer_chemin_fixe_seulement`, `test_plantage_detecte_dans_le_journal`,
  `test_chaque_appel_laisse_une_ligne_de_journal`, `test_sortie_toujours_une_ligne_json_valide`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py test_serveur_pont` depuis Git bash : échec. **Step 3: Implement** `pont.sh` (bash portable, `set -u`, `LC_ALL=C`).
  **Step 4: Run** : passe. **Step 5: Commit** « Tâches serveur : le pont d'actions ».

### Task 4: Image d'émulateur, enveloppe hôte et capacité `emulateur-image`

**Files:** Create `serveur_ovh/images/emulateur/Dockerfile`, `serveur_ovh/taches/lancer_emulation.sh` ; Modify `serveur_ovh/mise_en_place.sh`, `outils/serveur_capacites.py`,
`outils/serveur_installation.py` (délai et correspondance étape/capacité seulement) ; Test `tests/test_serveur_ovh_script.py`, `tests/test_serveur_capacites.py`, `tests/test_serveur_pont.py`.

**Interfaces:**
- Produces:
  - Capacité `emulateur-image` (dépend de `android-emulateur`, étape `emulateur_image`, installable) : construit `myiafactory/emulateur` sur l'hôte à partir de
    `serveur_ovh/images/emulateur/Dockerfile` (ubuntu, JDK 17 headless, `adb`, libs de l'émulateur, `pont.sh` copié en `/usr/local/bin/pont`, **pas** d'identifiants) puis écrit le marqueur
    `~/.myiafactory/emulateur-image.version` ; la sonde du catalogue est lecture seule (test du marqueur, pas de `sudo`) ; l'étape suit le modèle de `etape_images`
    (aperçu `--simuler`, un JSON par étape, `bloque` avec raison et geste, accord déjà porté par le moteur d'installation).
  - `lancer_emulation.sh <id> <mode>` exécuté **sur l'hôte** par SSH : crée `~/taches/<id>/{entree,sortie}`, prend le créneau par `flock -n` sur `~/taches/.creneau-emulation`
    (occupé → écrit `etat.json` `en_attente` et sort avec 75), lance `sudo docker run --rm -d --name tache-<id> --network none --device /dev/kvm --read-only --tmpfs /tmp
    --memory <lim> --cpus <lim> -v ~/android-sdk:/opt/android-sdk:ro -v ~/taches/<id>/entree:/entree:ro -v ~/taches/<id>/sortie:/sortie`, sous `timeout <duree_s>` ; l'enveloppe écrit `etat.json`
    (`en_cours` → `terminee|arretee|echouee`, dates, raison, `statut` du rapport), libère le créneau à la fin ou à l'échéance même si l'appelant a disparu, arrête le conteneur
    si le fichier `arret` apparaît ou si `inactivite_s` s'écoule en mode pilote ; un seul état `etat.json` écrit atomiquement.

- [ ] **Step 1: Write the failing tests** (script avec faux `docker`, `flock`, `sudo`, `timeout` comme les tests existants) : `test_etape_emulateur_image_simulation_json_valide`,
  `test_etape_emulateur_image_idempotente`, `test_etape_emulateur_image_construit_puis_ecrit_le_marqueur`, `test_sonde_emulateur_image_en_lecture_seule` (passe le validateur de sondes
  existant), `test_catalogue_et_recette_s_accordent`, `test_enveloppe_prend_le_creneau_et_ecrit_l_etat`, `test_enveloppe_creneau_occupe_donne_75_et_en_attente`,
  `test_enveloppe_libere_le_creneau_si_le_conteneur_meurt`, `test_enveloppe_arret_par_fichier`, `test_conteneur_sans_reseau_ni_identifiants` (la ligne `docker run` contient `--network none`, `--device /dev/kvm`,
  `:ro` pour le SDK et aucun volume des identifiants), `test_echeance_fait_passer_l_etat_en_limite`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py test_serveur_ovh_script` (Git bash) puis `test_serveur_capacites` : échec. **Step 3: Implement** ; le Dockerfile n'est
  jamais construit par un test (seulement lu). **Step 4: Run** : passe. **Step 5: Commit** « Tâches serveur : image d'émulateur, enveloppe hôte et capacité ».

### Task 5: Lanceur Python (lancer, état, arrêt, rapatriement)

**Files:** Modify `outils/serveur_tache.py` (deuxième partie) ; Test `tests/test_serveur_tache.py`.

**Interfaces:**
- Consumes: `plateforme_ssh.executer`/`executer_octets` (Task 1), `Demande`/`Index` (Task 2), `serveur_modele.lire`, `serveur_installation.lire_etat_vivant` (choix du serveur : premier déclaré, joignable, capacités `android-emulateur` et `emulateur-image` présentes, sinon `RefusLancement` avec la raison), `lancer_emulation.sh` (Task 4).
- Produces:
  - `choisir_serveur(dossier=DOSSIER) -> Serveur` (lève `RefusLancement(ValueError)`).
  - `lancer(demande, apk: bytes, dossier=DOSSIER, ssh=plateforme_ssh, attente_max_s=600, dormir=time.sleep) -> dict` : envoie l'APK et la demande, démarre l'enveloppe, gère l'attente de créneau
    (nouvel essai toutes les 15 s jusqu'à `attente_max_s`), enregistre la fiche dans l'index, renvoie `{id, etat, serveur_id}`.
  - `etat(id, dossier=DOSSIER, ssh=...) -> dict` (lit `~/taches/<id>/etat.json` par SSH, met l'index à jour ; serveur injoignable → `{"etat": "inconnu", "raison": ...}`, jamais d'exception).
  - `arreter(id, dossier=DOSSIER, ssh=...) -> dict` (écrit le fichier `arret` puis `docker stop` ; idempotent).
  - `rapatrier(id, destination, dossier=DOSSIER, ssh=...) -> dict` : archive `tar` de `sortie/` lue en octets, extraite **sans lien symbolique ni chemin absolu ni `..`**, au plus
    `limites["captures"] + 5` fichiers et `limites["octets"]` octets, dans `destination` ; renvoie le manifeste `{statut, captures: [chemins], journal, rapport, duree_s}` et écrit
    `rapport.json` localement.
  - `verbe(id, verbe, arguments, dossier=DOSSIER, ssh=...) -> dict` : un seul verbe relayé par `docker exec tache-<id> pont <verbe> ...` (arguments passés comme un seul texte
    entre guillemets simples échappés, **après** validation locale par les mêmes motifs que le pont) ; pour `capturer`, rapatrie la capture et renvoie son chemin local.
  - Statut du rapport : `ok|plantage|limite|erreur` d'après `etat.json`, `plantage.txt` et les codes du pont.

- [ ] **Step 1: Write the failing tests** (faux SSH enregistrant les commandes, serveur factice en mémoire) : `test_choisir_serveur_refuse_sans_capacite`, `test_choisir_serveur_refuse_serveur_injoignable`,
  `test_lancer_envoie_apk_en_octets_intacts`, `test_lancer_creneau_occupe_attend_puis_abandonne`, `test_lancer_deux_fois_un_seul_creneau` (deux threads, index sain),
  `test_etat_injoignable_ne_leve_pas`, `test_arreter_est_idempotent`, `test_rapatrier_refuse_chemin_traversant_et_lien_symbolique`, `test_rapatrier_borne_le_nombre_et_la_taille`,
  `test_rapatrier_conserve_le_png_binaire`, `test_verbe_valide_les_arguments_avant_ssh`, `test_verbe_capturer_rapatrie_et_donne_le_chemin_local`, `test_statut_plantage_et_limite`,
  `test_sorties_masquees_sans_secret`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py serveur_tache` : échec. **Step 3: Implement** (aucune commande distante construite par concaténation d'une valeur non validée ; `shlex.quote` en dernier recours seulement).
  **Step 4: Run** : passe. **Step 5: Commit** « Tâches serveur : lanceur, état, arrêt, rapatriement ».

### Task 6: Recettes de scénario

**Files:** Create `outils/serveur_recette.py` ; Test `tests/test_serveur_recette.py`.

**Interfaces:**
- Produces: `charger(projet: str, nom: str) -> Recette` lit `<projet>/.factory/recettes/<nom>.json` (`{"nom", "reseau": false, "etapes": [{"verbe": "...", "args": [...]}, ...]}`), valide **chaque étape par les motifs du pont**
  (importés d'un seul endroit partagé avec `serveur_tache.verbe`), refuse un verbe hors liste, plus de 200 étapes, un nom hostile, un fichier de plus de 64 Ko ; `executer(recette, id, dossier=DOSSIER, ssh=...) -> dict` déroule les étapes par
  `serveur_tache.verbe`, s'arrête au premier code non nul du pont et renvoie `{etapes_faites, echec}`. `reseau: true` est refusé en tranche A (message explicite).

- [ ] **Step 1: Write the failing tests** : `test_recette_valide_chargee`, `test_verbe_hors_liste_refuse`, `test_argument_hostile_refuse_au_chargement`, `test_nom_de_recette_hostile_refuse`, `test_recette_trop_longue_ou_trop_grosse_refusee`,
  `test_reseau_vrai_refuse`, `test_executer_s_arrete_au_premier_echec`, `test_executer_deroule_toutes_les_etapes_dans_l_ordre`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py serveur_recette` : échec. **Step 3: Implement.** **Step 4: Run** : passe. **Step 5: Commit** « Tâches serveur : recettes de scénario ».

### Task 7: Commandes `serveur-tache` et `serveur-outil`

**Files:** Create `outils/serveur_tache_cli.py` ; Modify `lancer.py` (aiguillage et docstring seulement) ; Test `tests/test_serveur_tache_cli.py`.

**Interfaces:**
- Produces: `py -3.12 lancer.py serveur-tache <lancer|etat|arreter|rapatrier|lister> ...` et `py -3.12 lancer.py serveur-outil <id> <verbe> [arguments]` ; codes 0 ok, 1 échec ou refus,
  2 usage ; `lancer --apk <fichier> --mode scenario|pilote [--scenario <nom>] [--projet <dossier>] [--attendre]` imprime `{id, etat}` (en mode scénario avec `--attendre` : déroule la recette,
  rapatrie dans `<projet>/.factory/serveur/<id>/` et imprime le manifeste) ; `serveur-outil` imprime la ligne JSON du pont et, pour `capturer`, le chemin local ; sortie masquée ; aucune trace d'exception
  (type seulement) ; arguments validés avant tout SSH ; identifiants et verbes de forme `[a-z0-9_-]{1,40}`.

- [ ] **Step 1: Write the failing tests** : `test_lancer_scenario_attend_et_rapatrie`, `test_lancer_pilote_rend_l_identifiant`, `test_apk_absent_ou_trop_gros_refuse`, `test_usage_et_codes_de_sortie`,
  `test_serveur_outil_relaie_un_verbe`, `test_serveur_outil_refuse_un_verbe_hors_liste`, `test_capturer_imprime_le_chemin_local`, `test_aucune_sortie_ne_contient_un_secret`, `test_lister_lit_l_index_sans_reseau`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py serveur_tache_cli` : échec. **Step 3: Implement.** **Step 4: Run** avec `test_plateforme` : passe. **Step 5: Commit** « Tâches serveur : commandes serveur-tache et serveur-outil ».

### Task 8: Action `recette-emulateur` et routage par `deporter`

**Files:** Modify `bureau/deport_types.py`, `outils/deporter.py` ; possibly `bureau/deport.py` (lire avant : comment `lieu_effectif` et les réglages traitent une action sans lieu `poste`) ; Test `tests/test_deporter.py`, `tests/test_deport_types.py`.

**Interfaces:**
- Consumes: `serveur_tache_cli` (Task 7), `serveur_recette` (Task 6).
- Produces: l'action `recette-emulateur` (libellé « Recette sur émulateur », `lieux=("serveur",)`, `consomme=["apk"]`) dans le catalogue `ANDROID` et `GENERIQUE` ; `deporter recette-emulateur [--mode scenario|pilote] [--scenario <nom>] [--apk <fichier>] [--dossier ...]` :
  **lieu effectif doit être `serveur`** (accord permanent) sinon refus code 2 « Réglez le lieu de l'action sur serveur dans le bureau (accord permanent pour ce projet) » ; `lieux_refuses` accepte `serveur` seulement pour les actions dont le catalogue le déclare ; l'APK vient de `--apk`
  sinon de la production `apk` du projet résolue comme aujourd'hui (artefact GitHub ou sortie locale) ; scénario : lance, attend, rapatrie, imprime le manifeste, code 0 seulement si `statut == "ok"` ; pilote : imprime l'identifiant et le mode d'emploi de `serveur-outil` ;
  le code reste compatible Python 3.9 ; les actions existantes ne changent pas de comportement (`emulateur` reste poste).

- [ ] **Step 1: Write the failing tests** : `test_recette_emulateur_dans_le_catalogue_android_et_generique`, `test_refus_si_le_lieu_n_est_pas_serveur`, `test_accepte_le_lieu_serveur_pour_cette_action_seulement`
  (`tests` réglé sur serveur reste refusé), `test_scenario_code_0_seulement_si_ok`, `test_plantage_donne_le_code_1`, `test_pilote_imprime_identifiant_et_mode_d_emploi`, `test_apk_pris_dans_la_production_apk`,
  `test_serveur_injoignable_message_clair_sans_repli_poste`, `test_actions_existantes_inchangees` (suite `test_deporter` actuelle verte).
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py test_deporter` : échec. **Step 3: Implement** (relire `lieu_effectif`, `catalogue_union`, `actions_exposees` et l'écran de déport pour qu'une action au seul lieu serveur s'affiche et se règle ; ne rien casser des
  tests de `bureau/web/tests/`). **Step 4: Run** : passe, puis `py -3.12 outils/tests_paralleles.py test_deport` et les tests JS du déport. **Step 5: Commit** « Tâches serveur : action recette-emulateur et routage par deporter ».

### Task 9: Liste et arrêt des tâches dans le bureau

**Files:** Modify `bureau/serveurs.py`, `bureau/serveur.py` (routes), `bureau/web/ui/serveurs.js`, `bureau/web/style.css` ; Test `tests/test_bureau_serveurs.py`, `bureau/web/tests/serveurs-taches.test.js`.

**Interfaces:**
- Produces: `GET /api/serveurs/taches` (index local seulement, jamais de réseau : `{taches: [{id, etat, mode, projet, serveur_id, debut, duree_s, captures, statut}]}`, masqué) ; `POST /api/serveurs/taches/<id>/arreter` (mêmes protections que les autres POST : Host, `X-Bureau`, JSON, taille ≤ 1 Ko, 404 sur l'écoute distante, clés dupliquées refusées ; id validé par le motif des tâches et comparé à l'index, jamais utilisé pour construire un chemin ; appelle `serveur_tache.arreter` dans un fil borné, 202).
  Écran : section « Tâches du serveur » (état en toutes lettres, durée, captures, bouton « Arrêter » désactivé hors `en_attente`/`en_cours`), suivi périodique injectable arrêté au retrait de la carte, texte serveur par `textContent`.

- [ ] **Step 1: Write the failing tests** : Python `test_get_taches_lit_l_index_sans_reseau`, `test_arreter_refuse_un_id_inconnu_ou_hostile`, `test_arreter_a_les_protections_des_autres_post`, `test_arreter_est_borne_et_masque_les_erreurs` ;
  JS `la liste affiche l etat en toutes lettres`, `le bouton arreter n existe que pour une tache active`, `un texte du serveur avec du HTML n est pas interprete`, `le suivi s arrete quand la carte disparait`, `arret echoue affiche un message sans exception`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py test_bureau_serveurs` puis les tests JS : échec. **Step 3: Implement.** **Step 4: Run** : passe. **Step 5: Commit** « Tâches serveur : liste et arrêt dans le bureau ».

### Task 10: Documentation et jalon réel (contrôleur, avec l'accord du Directeur)

**Files:** Create `docs/serveur-taches.md` ; Modify `docs/serveur.md` (renvoi, capacité `emulateur-image`).

- [ ] **Step 1:** rédiger `docs/serveur-taches.md` en vérifiant chaque commande, route, fichier et message contre le code : modèle de tâche, créneaux, limites, verbes du pont, recettes, accord permanent, commandes, `deporter recette-emulateur`, rapatriement, sécurité,
  ce qui n'a pas été exécuté sur le vrai serveur ; la consigne de départ des agents (données non fiables, une seule commande à connaître).
- [ ] **Step 2:** suite complète `py -3.12 outils/tests_paralleles.py` depuis Git bash, puis les tests JS, `bash -n` sur les scripts ajoutés, et la recherche de fragments de clé (liste hors dépôt).
- [ ] **Step 3: Jalon réel, après accord explicite du Directeur dans la conversation** : installer la capacité `emulateur-image` par le moteur d'installation (aperçu puis accord), lancer une tâche réelle avec l'APK de MyFridgeCleaner
  (`deporter recette-emulateur --mode scenario --scenario demarrage`), vérifier KVM, la capture rapatriée, le rapport, l'arrêt et la libération du créneau, puis nettoyer. Rapporter fidèlement chaque écart.
- [ ] **Step 4: Commit** « Documentation : tâches serveur (tranche A) ». Ne rien pousser sans demande.

---

## Suite (hors de ce plan)
Tranche B : agent distant (image d'agent, abonnement, pont hôte sur socket Unix, bascule, file) ; plan à rédiger après le jalon réel de la tranche A.

## Self-Review
- **Couverture de la conception :** tâche et créneaux (T2, T4, T5), conteneur sans identifiants (T4), pont fermé (T3), deux modes (T5–T7), rapatriement (T5), `deporter` et accord permanent (T8), écran (T9), image par capacité (T4), jalon réel (T10). Statuts et codes de retour : contraintes globales et T8.
- **Cohérence des noms :** `Demande`, `Index`, `lancer`, `etat`, `arreter`, `rapatrier`, `verbe`, `choisir_serveur`, `RefusLancement`, `executer_octets`, capacité `emulateur-image`, action `recette-emulateur`.
- **Proportion :** signatures, motifs et tests nommés ; aucune fonction réécrite en entier.
