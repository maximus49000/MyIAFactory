# Serveur OVH : plateforme prête à l'usage, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Amener un serveur dédié OVH vierge à l'état « prêt » (Ubuntu, SSH par clé, durcissement, Docker, images d'outils) depuis le bureau, avec une carte « Serveur » qui montre l'état.

**Architecture:** Trois couches sans dépendance externe : un client API OVH signé (`outils/ovh_api.py`), un exécuteur SSH et un script bash rejouable envoyé par l'entrée standard (`serveur_ovh/mise_en_place.sh`), et une machine à états (`outils/plateforme.py`) appelée par `lancer.py plateforme` et par le serveur du bureau. L'état est mis en cache dans `~/MyIAFactory/plateforme.json` ; l'état réel est relu à la demande.

**Tech Stack:** Python 3.12 (bibliothèque standard, `unittest`), bash, Docker, OpenSSH de Windows, JS ES modules (tests `node`), images GameCI.

**Spec:** `docs/superpowers/specs/2026-11-19-serveur-ovh-plateforme-design.md`

## Global Constraints

- Aucune dépendance nouvelle ; client OVH écrit à la main (pas de SDK OVH).
- Les secrets (clés OVH `ovh.json`, licence `unity.ulf`) vivent dans `~/MyIAFactory`, jamais dans le dépôt, les journaux, les comptes rendus ni une page du bureau ; la licence passe par l'entrée standard SSH, jamais en argument.
- Réinstallation de l'OS = effacement : exige l'accord explicite (`--accord-reinstallation` / confirmation dans le bureau), une confirmation par exécution ; le même accord couvre la remise à zéro de l'empreinte d'hôte.
- Ubuntu LTS par défaut ; port SSH 22 ; une seconde session par clé doit s'ouvrir avant de couper le mot de passe et d'activer le pare-feu ; aucun autre port ouvert.
- « Prêt » = étapes 1 à 6 ; l'étape 7 (licence Unity) est facultative (« prêt, sans Unity »).
- Compilations simultanées limitées : réglage `compilations_max`, 2 par défaut ; caches Gradle et Unity en volumes Docker persistants.
- Le serveur ou OVH injoignable ne casse jamais le reste du bureau.
- Tests : OVH et SSH simulés, jamais réels ; lancés par `py -3.12 outils/tests_paralleles.py <module>` (CLAUDE.md), une campagne à la fois.
- Écart avec la spec : `lancer.py serveur` est déjà le serveur web du bureau ; le point d'entrée s'appelle donc `lancer.py plateforme <etat|installer|verifier>`.
- Le dépôt contient des modifications non commitées d'autres travaux (dont un conflit sur `bureau/web/ui/directeur.js`) : ne committer que les fichiers de ce plan (`git add` par chemin), ne jamais `git add -A`.

## Review Focus

- Clé API OVH expirée ou droits insuffisants (401/403) : message clair avec le geste à faire, pas de trace de pile ni de secret.
- Dérive d'horloge du poste : la signature OVH échoue ; l'heure vient de `/auth/time`.
- Relance au milieu d'une installation (coupure, fermeture du bureau) : reprend sans rien refaire de fait ni effacer à nouveau.
- Serveur redémarré par OVH pendant la réinstallation : l'attente SSH patiente puis dit « en cours » plutôt que d'échouer.
- Clé d'hôte changée après réinstallation : refusée sans accord, jamais ignorée en silence (`StrictHostKeyChecking=no` interdit).
- Disque presque plein (HDD 2 × 4 To, images volumineuses) : l'étape images s'arrête avant de remplir et le dit.

---

### Task 1: Client API OVH signé

**Files:**
- Create: `outils/ovh_api.py`
- Test: `tests/test_ovh_api.py`

**Interfaces:**
- Produces: `class ErreurOvh(Exception)` (attributs `code: int`, `message: str`) ; `class ClientOvh(point: str, cle_app: str, secret: str, consommateur: str, http=None)` avec `appeler(methode: str, chemin: str, corps: dict | None = None) -> object` et `signer(methode, url, corps_texte, horodatage) -> str` ; `POINTS = {"ovh-eu": "https://eu.api.ovh.com/1.0", ...}`.
- `http` est un appelable `(methode, url, entetes, corps_bytes) -> (statut:int, texte:str)` injectable ; défaut `urllib.request`.

- [ ] **Step 1: Tests** : `test_signature_connue` (la signature `"$1$" + sha1("secret+consommateur+GET+URL++1700000000")` d'un cas fixé est exactement celle calculée à la main) ; `test_heure_prise_sur_auth_time` (premier appel `GET /auth/time` simulé, l'en-tête `X-Ovh-Timestamp` en dérive) ; `test_401_donne_erreur_claire` (`ErreurOvh.code == 401`, le message ne contient ni secret ni consommateur) ; `test_corps_json_signe_tel_quel` (le texte signé est celui envoyé).
- [ ] **Step 2:** `py -3.12 outils/tests_paralleles.py ovh_api` : échec attendu (module absent).
- [ ] **Step 3: Implémenter** `ClientOvh` et `ErreurOvh` dans `outils/ovh_api.py` : en-têtes `X-Ovh-Application`, `X-Ovh-Consumer`, `X-Ovh-Timestamp`, `X-Ovh-Signature`.
- [ ] **Step 4:** relancer, tout passe.
- [ ] **Step 5: Commit** `git add outils/ovh_api.py tests/test_ovh_api.py` ; message « Serveur OVH : client d'API signé ».

### Task 2: Accès et secrets, masquage

**Files:**
- Create: `outils/plateforme_acces.py`
- Test: `tests/test_plateforme_acces.py`

**Interfaces:**
- Produces: `DOSSIER = Path("~/MyIAFactory").expanduser()` ; `charger_ovh(dossier=DOSSIER) -> dict` (clés `point`, `cle_app`, `secret`, `consommateur`, `serveur`) levant `ErreurAcces` avec le mode opératoire (lien de création de clés, droits minimaux sur ce seul serveur) si `ovh.json` manque ou est incomplet ; `chemin_licence(dossier=DOSSIER) -> Path | None` (`unity.ulf`) ; `masquer(texte: str, secrets: list[str]) -> str` remplaçant chaque secret par `***`.

- [ ] **Step 1: Tests** : `test_ovh_json_absent_donne_mode_operatoire` (le message contient « ovh.json » et un lien) ; `test_champ_manquant_nomme_le_champ` ; `test_masquer_remplace_tous_les_secrets_meme_repetes` ; `test_masquer_ignore_secret_vide` (une chaîne vide ne détruit pas le texte).
- [ ] **Step 2:** lancer : échec. **Step 3:** implémenter ci-dessus. **Step 4:** lancer : succès.
- [ ] **Step 5: Commit** (fichiers de la tâche seulement).

### Task 3: Opérations OVH sur le serveur dédié

**Files:**
- Create: `outils/plateforme_ovh.py`
- Test: `tests/test_plateforme_ovh.py`

**Interfaces:**
- Consumes: `ClientOvh.appeler` (Task 1).
- Produces: `lire_serveur(client, nom) -> dict` (clés `os`, `ip`, `etat`, `modele`) ; `modeles_os(client, nom) -> list[str]` ; `enregistrer_cle_ssh(client, nom_cle: str, cle_publique: str) -> None` (`POST /me/sshKey`, tolère « existe déjà » avec la même clé) ; `reinstaller(client, nom, modele_os: str, nom_cle: str, accord: bool) -> int` (id de tâche ; **lève `ErreurAccord` si `accord` est faux avant tout appel réseau d'écriture**) ; `etat_tache(client, nom, id_tache) -> str` parmi `"en_cours" | "fini" | "echec"`.

- [ ] **Step 1: Tests** (client factice enregistrant les appels) : `test_reinstaller_sans_accord_ne_touche_a_rien` (aucun appel `POST`, `ErreurAccord`) ; `test_reinstaller_avec_accord_demande_ubuntu_lts_et_cle` (le corps nomme le modèle Ubuntu LTS le plus récent offert par `modeles_os` et la clé) ; `test_cle_existante_identique_tolérée` et `test_cle_existante_differente_refusee` ; `test_etat_tache_traduit_les_statuts_ovh` (`doing`/`todo` → en_cours, `done` → fini, `error`/`cancelled` → echec).
- [ ] **Step 2:** échec. **Step 3:** implémenter ; le choix du modèle : filtrer les noms contenant « ubuntu » et « server », prendre le plus récent, lever une erreur lisible si aucun. **Step 4:** succès.
- [ ] **Step 5: Commit.**

### Task 4: Exécuteur SSH et clé dédiée

**Files:**
- Create: `outils/plateforme_ssh.py`
- Test: `tests/test_plateforme_ssh.py`

**Interfaces:**
- Produces: `generer_cle(dossier: Path) -> tuple[Path, str]` (chemin privé, clé publique ; ed25519 via `ssh-keygen`, jamais régénérée si elle existe) ; `executer(hote: str, commande: str, cle: Path, stdin: str | None = None, delai: int = 60, runner=subprocess.run) -> tuple[int, str, str]` ; `attendre_ssh(hote, cle, delai_total: int, pas: int = 10, runner=..., dormir=time.sleep) -> bool` ; `oublier_hote(hote, accord: bool, runner=...) -> None` (`ssh-keygen -R`, exige `accord`, sinon `ErreurAccord`).
- Options SSH imposées : `-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o PasswordAuthentication=no -i <cle>` ; jamais `StrictHostKeyChecking=no`.

- [ ] **Step 1: Tests** (runner factice) : `test_options_sures_presentes_et_jamais_no` ; `test_stdin_transmis_et_pas_dans_la_commande` (le texte secret n'apparaît pas dans `args`) ; `test_attendre_ssh_patiente_puis_reussit` (3 échecs puis succès, `dormir` appelé 3 fois) ; `test_attendre_ssh_abandonne_au_delai` ; `test_oublier_hote_sans_accord_refuse` ; `test_cle_existante_non_ecrasee`.
- [ ] **Step 2:** échec. **Step 3:** implémenter. **Step 4:** succès. **Step 5: Commit.**

### Task 5: Script de mise en place et images

**Files:**
- Create: `serveur_ovh/mise_en_place.sh`, `serveur_ovh/images/android/Dockerfile`, `serveur_ovh/images/agent/Dockerfile`, `serveur_ovh/versions.json` (étiquettes épinglées : GameCI Unity, base Ubuntu, Android build-tools)
- Test: `tests/test_serveur_ovh_script.py`

**Interfaces:**
- Produces: le script lit `--etape <nom>` (une de `durcissement`, `docker`, `images`, `licence`, `etat`) et `--simuler` ; il écrit sur la sortie standard **un seul objet JSON** `{"etape": str, "statut": "fait"|"a_faire"|"bloque", "detail": str, "versions": {...}, "disque_libre_go": int}` ; idempotent : constate avant d'agir. La licence arrive par l'entrée standard.

- [ ] **Step 1: Tests** (lancent `bash` du poste en `--simuler`, ignorés si `bash` absent avec `skipUnless`) : `test_chaque_etape_rend_un_json_valide` ; `test_simuler_ne_modifie_rien` (aucune commande `apt`/`docker`/`ufw` exécutée : le mode n'imprime que ce qu'il ferait) ; `test_durcissement_verifie_seconde_session_avant_pare_feu` (dans le texte du script, l'appel de vérification précède `ufw enable` et la coupure du mot de passe) ; `test_images_refuse_si_disque_presque_plein` (variable simulée `DISQUE_LIBRE_GO=5` → statut `bloque`, détail le dit) ; `test_licence_non_lue_dans_argv` (le script lit stdin, aucune variante `--licence <valeur>`) ; `test_versions_epinglees` (aucune étiquette `latest` dans `versions.json` ni les Dockerfile).
- [ ] **Step 2:** échec. **Step 3: Écrire** le script : durcissement = `PasswordAuthentication no`, `ufw` limité à 22, `unattended-upgrades`, vérification d'une seconde session par clé avant ; docker = installation depuis le dépôt officiel, `docker run hello-world` ; images = tirer GameCI, construire `android` et `agent` depuis `serveur_ovh/images`, volumes `gradle-cache` et `unity-cache`, arrêt avant 20 Go libres ; licence = lit le `.ulf` sur stdin, l'active dans un conteneur de test. Écrire les deux Dockerfile (JDK 17, SDK Android, Gradle ; Node et CLI Claude). **Step 4:** succès.
- [ ] **Step 5: Commit.**

### Task 6: Machine à états et point d'entrée

**Files:**
- Create: `outils/plateforme.py`
- Modify: `lancer.py` (ajouter `"plateforme"` au routage des commandes d'`outils/`, sans toucher au reste)
- Test: `tests/test_plateforme.py`

**Interfaces:**
- Consumes: Tasks 2, 3, 4, 5.
- Produces: `ETAPES = ("lecture", "os", "ssh", "durcissement", "docker", "images", "licence")` ; `calculer_etat(rapports: dict) -> dict` renvoyant `{"etapes": [{"id","libelle","statut","detail","geste"}], "pret": bool, "pret_sans_unity": bool}` (statuts `fait|a_faire|bloque|en_cours`, `geste` = action humaine éventuelle) ; `installer(dossier, accord_reinstallation: bool, client=None, ssh=None) -> dict` (reprend là où la dernière exécution s'est arrêtée, écrit `plateforme.json` à chaque étape) ; `verifier(...) -> dict` ; `main(argv) -> int` pour `lancer.py plateforme <etat|installer|verifier> [--accord-reinstallation] [--dossier <d>]`.

- [ ] **Step 1: Tests** (client OVH et SSH factices) : `test_serveur_vierge_sans_accord_bloque_a_l_etape_os_sans_effacer` ; `test_avec_accord_enchaine_les_etapes_dans_l_ordre` ; `test_relance_reprend_sans_refaire_les_etapes_faites` ; `test_pret_vaut_etapes_1_a_6_et_licence_facultative` (licence `a_faire` → `pret` vrai, `pret_sans_unity` vrai) ; `test_os_present_non_ubuntu_bloque_avec_raison` ; `test_echec_de_tache_ovh_donne_geste_et_pas_de_trace_de_pile` ; `test_aucun_secret_dans_etat_ni_cache` (secrets de test absents de la sortie JSON et du fichier) ; `test_cle_hote_changee_exige_accord`.
- [ ] **Step 2:** échec. **Step 3: Implémenter**. L'attente de fin de réinstallation interroge `etat_tache` puis `attendre_ssh` (délai total 40 min). Aucune étape ne s'exécute avant que la précédente soit « fait ». **Step 4:** succès. **Step 5: Commit** (`lancer.py` inclus).

### Task 7: Étape licence Unity Personal (geste humain guidé)

**Files:**
- Modify: `outils/plateforme.py`, `serveur_ovh/mise_en_place.sh`
- Test: `tests/test_plateforme_licence.py`

**Interfaces:**
- Consumes: `chemin_licence` (Task 2), exécuteur SSH (Task 4).
- Produces: `demander_licence(dossier, ssh) -> Path` (fait générer le `.alf` dans le conteneur, le copie dans `~/MyIAFactory/unity.alf`, renvoie le chemin) ; l'étape `licence` a `geste` = « Déposez unity.alf sur license.unity3d.com, enregistrez le fichier obtenu sous ~/MyIAFactory/unity.ulf » tant que `unity.ulf` manque.

- [ ] **Step 1: Tests** : `test_sans_ulf_geste_guide_avec_lien` ; `test_avec_ulf_active_via_stdin_et_masque_la_sortie` ; `test_licence_refusee_par_unity_donne_statut_bloque_lisible` ; `test_ulf_jamais_dans_etat_ni_journal`.
- [ ] **Step 2:** échec. **Step 3:** implémenter. **Step 4:** succès. **Step 5: Commit.**

### Task 8: Serveur du bureau : routes de la plateforme

**Files:**
- Create: `bureau/plateforme.py`
- Modify: `bureau/serveur.py` (routes `GET /api/plateforme`, `POST /api/plateforme/installer`, ajoutées à côté des routes `deport`, lignes 74-87 et 1928-1953 ; `etat_deport` : `serveur_disponible` devient vrai quand `pret`), `bureau/deport.py` (`LIEUX_ETAPE_1` reste ; seulement le dégrisage conditionné par `etape_serveur`)
- Test: `tests/test_bureau_plateforme.py`

**Interfaces:**
- Consumes: `plateforme.calculer_etat`, `installer` (Task 6).
- Produces: `GET /api/plateforme` → `{"etapes": [...], "pret": bool, "pret_sans_unity": bool, "derniere_lecture": str}` (relit le cache, jamais bloquant) ; `POST /api/plateforme/installer` corps `{"accord_reinstallation": bool}` lance l'installation en arrière-plan (un seul travail à la fois ; 409 si déjà en cours) et répond immédiatement ; l'en-tête `X-Bureau: 1` est exigé comme les autres POST.

- [ ] **Step 1: Tests** : `test_get_sans_cache_donne_etat_a_faire_sans_erreur` ; `test_get_ne_bloque_pas_si_ovh_injoignable` ; `test_post_sans_en_tete_bureau_refuse` ; `test_post_deuxieme_lancement_renvoie_409` ; `test_post_sans_accord_ne_reinstalle_pas` ; `test_serveur_disponible_vrai_seulement_si_pret` ; `test_reponses_sans_secret`.
- [ ] **Step 2:** échec. **Step 3:** implémenter en suivant le modèle de `apercu_deport` / `appliquer_deport`. **Step 4:** succès, puis `py -3.12 outils/tests_paralleles.py test_deport_logique test_bureau_deport` pour vérifier l'absence de régression du flux local.
- [ ] **Step 5: Commit** (seulement les lignes de ce plan dans `bureau/serveur.py` : `git add -p`).

### Task 9: Carte « Serveur » du bureau

**Files:**
- Create: `bureau/web/ui/plateforme.js`, `bureau/web/tests/plateforme.test.js`
- Modify: `bureau/web/ui/deport.js` (la case « Serveur » n'est plus grisée « bientôt » quand `deport.serveur_disponible`)

**Interfaces:**
- Consumes: `GET /api/plateforme`, `POST /api/plateforme/installer` (Task 8).
- Produces: `export function carteServeur(etat, {installer, fetchFn})` → élément DOM : une ligne par étape (fait, à faire, bloqué avec raison et `geste`, en cours), bouton « Mettre en place / reprendre », case et texte d'avertissement « Réinstaller efface le disque » avant tout accord, mention « prêt, sans Unity » ; `export async function demanderInstallation(accord, fetchFn=fetch) -> {ok, message}` sans jamais lever.

- [ ] **Step 1: Tests** (même style que `deport.test.js`) : `la carte liste les sept étapes dans l ordre` ; `le bouton n envoie jamais accord_reinstallation vrai sans la case cochée` ; `un geste humain affiche son lien et son mode opératoire` ; `serveur injoignable affiche un message et pas d exception` ; `la case Serveur de deport.js se dégrise quand serveur_disponible`.
- [ ] **Step 2:** lancer le fichier de test avec `node` (voir un test existant dans `bureau/web/tests` pour la commande) : échec. **Step 3:** implémenter, puis brancher la carte dans la page des réglages comme `deport.js`. **Step 4:** succès, puis vérifier dans le bureau (`preview_start`) que la carte s'affiche et que l'état sans serveur est lisible.
- [ ] **Step 5: Commit.**

### Task 10: Documentation et consigne

**Files:**
- Create: `docs/serveur-ovh.md`
- Modify: `docs/superpowers/specs/2026-11-17-execution-deportee-design.md` (une ligne : l'étape 2 « serveur » s'appuie sur la plateforme OVH)

- [ ] **Step 1:** rédiger `docs/serveur-ovh.md` : créer les clés API OVH (lien, droits minimaux), placer `ovh.json` et `unity.ulf`, lancer `py -3.12 lancer.py plateforme etat`, puis `installer --accord-reinstallation`, lire la carte, geste de licence, ce que « prêt » veut dire, limites (HDD, `compilations_max`).
- [ ] **Step 2:** suite complète avant de pousser : `py -3.12 outils/tests_paralleles.py` ; attendu : aucun échec nouveau.
- [ ] **Step 3: Commit.** Ne pas pousser sans accord du Directeur.

---

## Self-Review

- **Couverture de la spec :** couche OVH (T1, T3), accès/secrets (T2), étapes 1-7 (T3, T5, T6, T7), point d'entrée (T6), carte et aide humaine (T7, T9), état en cache (T6), branchement du lieu `serveur` (T8, T9), réponses du Directeur HDD/Personal (T5, T7), limite de compilations (T5, constraints). Hors-buts respectés : aucun lancement de tâche, aucun achat.
- **Cohérence des types :** `ErreurAccord` défini en T3, réutilisé en T4 ; `calculer_etat` (T6) est la forme servie par T8 et lue par T9 ; `chemin_licence` (T2) lu en T7.
- **Écart à signaler :** le nom de la commande (`plateforme`, non `serveur`).
- **Proportion :** plan court, sans corps de fonction ; chaque test nomme ses assertions.
