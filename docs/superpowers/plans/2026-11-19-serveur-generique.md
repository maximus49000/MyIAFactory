# Serveur générique Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Passer de « plateforme OVH » à un serveur générique : un modèle de serveur (adresse, utilisateur, clé, fournisseur facultatif), un catalogue de capacités installées à la demande selon les actions confiées au serveur, des écrans de paramétrage, et, en dernière étape, l'inscription automatique du serveur OVH existant.

**Architecture:** Un cœur générique de nouveaux modules `outils/serveur_*.py` (modèle, catalogue de capacités avec sondes en lecture seule, moteur d'installation avec aperçu et accord strict, interface fournisseur) qui réutilise `outils/plateforme_ssh.py` (déjà générique) et appelle `serveur_ovh/mise_en_place.sh` pour les étapes distantes. Le code OVH existant (`plateforme.py`, `plateforme_ovh.py`, `ovh_api.py`) devient le fournisseur `ovh` derrière l'interface, sans être réécrit ; ses modules gardent leurs noms et leurs tests.

**Tech Stack:** Python 3.12 (bibliothèque standard, `unittest`), bash, JS ES modules (tests `node`), SSH de Windows.

**Spec:** `docs/superpowers/specs/2026-11-19-serveur-generique-design.md` (et, pour l'existant, `2026-11-19-serveur-ovh-plateforme-design.md`, `2026-11-19-session-graphique-serveur-design.md`).

## Global Constraints

- Branche et worktree existants : `worktree-serveur-ovh-plateforme` (`.claude/worktrees/serveur-ovh-plateforme`). Commits par `git add <chemins>`, jamais `git add -A`, rien de poussé.
- Aucune dépendance nouvelle ; tests entièrement simulés (jamais de vrai serveur, SSH ni fournisseur) ; jamais d'écriture dans le vrai `~/MyIAFactory` (dossier injecté ; `tests/__init__.py` fournit un défaut temporaire) ; passage par le lanceur : `py -3.12 outils/tests_paralleles.py <module>` (une campagne à la fois ; suite complète une fois à la fin, puis `node --test bureau/web/tests/*.test.js`).
- Le serveur OVH en service n'est JAMAIS touché par ce plan : aucune tâche n'exécute de commande sur le vrai serveur ; la migration (dernière tâche) ne fait qu'une lecture seule, avec aperçu et confirmation.
- Aucune règle ne suppose OVH hors du fournisseur `ovh`. Un serveur sans fournisseur saute l'étape « système ».
- Contrat minimal d'un serveur : adresse, utilisateur NON root avec `sudo` sans mot de passe, clé SSH dédiée, Ubuntu/Debian récent. Un utilisateur `root` est refusé avec le geste « créez un utilisateur avec sudo ».
- Installation d'une capacité : jamais sans accord strict (`accord is True`) ; aperçu obligatoire (capacités manquantes dans l'ordre des dépendances, taille et durée estimées) ; aucun secret dans l'état, les journaux ou le dépôt ; messages en français.
- Les tests existants (`test_plateforme*`, `test_ovh_api`, `test_serveur_ovh_script`, `test_bureau_plateforme`, node `plateforme.test.js`) restent verts ; si un module est renommé, un raccourci (ré-export) reste jusqu'à la fin de la tâche de migration.
- `bureau/deport_types.py` n'existe pas dans cette branche (travail de déport du Directeur, non commité) : le cœur porte sa propre table `besoins` ; le branchement sur ce fichier est hors de ce plan (voir « Suite »).
- La commande de ligne de commande reste `py -3.12 lancer.py plateforme …` (`lancer.py serveur` est le serveur web du bureau).

## Review Focus

- Un serveur déclaré avec `utilisateur: "root"` ou sans `sudo` sans mot de passe : refus clair, aucune commande mutante lancée.
- Capacité installée mais sonde en échec (serveur éteint, SSH coupé) : l'état dit « inconnue » (injoignable) et non « absente » ; jamais de réinstallation déclenchée par une panne réseau.
- Dépendances circulaires ou manquantes dans le catalogue : erreur claire au chargement, pas de boucle.
- Action confiée au serveur dont une capacité est « bloquée » : l'action reste au poste avec la raison, jamais lancée « à moitié ».
- Deux installations de capacités en même temps (bureau + ligne de commande) : un seul verrou, la seconde refusée.
- Migration relancée : idempotente (n'inscrit pas deux fois), n'écrase pas un serveur déjà déclaré, ne change rien sur le serveur.

---

### Task 1: Modèle de serveur et configuration

**Files:**
- Create: `outils/serveur_modele.py`
- Test: `tests/test_serveur_modele.py`

**Interfaces:**
- Produces:
  - `FICHIER = "serveurs.json"` (dans le dossier de configuration, défaut `plateforme_acces.DOSSIER`).
  - `Serveur` (dataclass figée) : `id: str`, `nom: str`, `hote: str`, `utilisateur: str`, `cle: str` (chemin de la clé privée dédiée), `fournisseur: str | None` (`"ovh"` ou `None`), `reglages_fournisseur: dict`.
  - `valider(serveur: dict) -> Serveur` : lève `ValueError` (message en français) pour hôte vide/avec espace/`@`/`-` initial, utilisateur vide ou `root`, fournisseur inconnu, clé non textuelle.
  - `lire(dossier=DOSSIER) -> list[Serveur]` (liste vide si absent ou abîmé, jamais d'exception) ; `ecrire(serveurs, dossier=DOSSIER) -> None` (écriture atomique, droits restreints, aucun secret : les clés API d'un fournisseur restent dans leurs propres fichiers, pas ici) ; `ajouter(serveur, dossier=DOSSIER) -> Serveur` (refuse un identifiant déjà pris) ; `ligne_cle_publique(dossier, serveur) -> str` (génère la clé dédiée si absente via `plateforme_ssh.generer_cle` et renvoie la ligne à coller dans `authorized_keys`).

- [ ] **Step 1: Write the failing tests** : `test_valider_refuse_root_et_hote_piege` (`root`, `-oProxyCommand=x`, `a b`, `u@x`, vide), `test_lire_fichier_abime_donne_liste_vide` (JSON invalide, liste de listes, entrée sans hôte), `test_ecrire_puis_lire_aller_retour_sans_secret`, `test_ajouter_refuse_doublon`, `test_ligne_cle_publique_genere_une_seule_fois` (deux appels, même clé ; fichier privé non écrasé), `test_ecriture_atomique_ne_laisse_pas_de_temporaire`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py serveur_modele` : échec attendu.
- [ ] **Step 3: Implement** les signatures ci-dessus dans `outils/serveur_modele.py` (lecture avec `utf-8-sig`, comme `plateforme_bureau`).
- [ ] **Step 4: Run** le module : tout passe. **Step 5: Commit** `git add outils/serveur_modele.py tests/test_serveur_modele.py` ; « Serveur générique : modèle de serveur et configuration ».

### Task 2: Catalogue de capacités, dépendances, sondes et besoins

**Files:**
- Create: `outils/serveur_capacites.py`
- Test: `tests/test_serveur_capacites.py`

**Interfaces:**
- Produces:
  - `Capacite` (dataclass figée) : `id`, `libelle`, `depend: tuple[str, ...]`, `etape: str` (nom de l'étape distante de `mise_en_place.sh`), `sonde: str` (commande SHELL de vérification en lecture seule, code 0 = présente), `taille_go: float`, `duree_min: int` (estimations), `installable: bool`, `raison_non_installable: str`.
  - `CATALOGUE: dict[str, Capacite]` : `base`, `durcissement` (facultative, dépend de `base`), `android-build`, `android-emulateur` (dépend de `android-build`), `unity` (dépend de `base`), `session-graphique` (dépend de `base`), `agent` (`installable=False`, raison « non installable avant le morceau 3 »).
  - `BESOINS: dict[str, tuple[str, ...]]` : `apk`, `tests`, `lint`, `release` → `("android-build",)` ; `emulateur` → `("android-emulateur",)` ; `charge` → `()`.
  - `ordre_installation(demandees: Iterable[str], installees: set[str]) -> list[str]` : capacités manquantes dans l'ordre des dépendances ; lève `ValueError` pour une capacité inconnue ou un cycle.
  - `manquantes_pour(actions: Iterable[str], installees: set[str]) -> list[str]` (via `BESOINS`) ; `verifier_catalogue() -> None` (cycles, dépendances inconnues).

- [ ] **Step 1: Write the failing tests** : `test_catalogue_sans_cycle_ni_dependance_inconnue`, `test_ordre_respecte_les_dependances` (émulateur seul sur serveur vide → `["base", "android-build", "android-emulateur"]`), `test_ordre_ignore_ce_qui_est_installe`, `test_capacite_inconnue_leve_une_erreur_claire`, `test_cycle_detecte` (catalogue injecté), `test_agent_non_installable_avec_sa_raison`, `test_manquantes_pour_actions` (`emulateur` sur serveur avec `android-build` seul → `["android-emulateur"]`), `test_sondes_sont_en_lecture_seule` (aucune sonde ne contient `install`, `apt`, `rm`, `>`, `sudo`).
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py serveur_capacites` : échec. **Step 3: Implement** (sondes : par exemple `command -v docker`, `test -x ~/android-sdk/emulator/emulator`, `test -x ~/Unity/Hub/Editor/*/Editor/Unity`, `ss -ltn | grep -q 127.0.0.1:3389`). **Step 4: Run** : passe.
- [ ] **Step 5: Commit** `git add outils/serveur_capacites.py tests/test_serveur_capacites.py` ; « Serveur générique : catalogue de capacités, dépendances et besoins ».

### Task 3: Lecture de l'état des capacités par SSH (sondes)

**Files:**
- Create: `outils/serveur_etat.py`
- Test: `tests/test_serveur_etat.py`

**Interfaces:**
- Consumes: `serveur_modele.Serveur`, `serveur_capacites.CATALOGUE`, `plateforme_ssh.executer(hote, commande, cle, stdin=None, delai=60, runner=...)`.
- Produces:
  - `sonder(serveur, ssh=plateforme_ssh, runner=None) -> dict[str, str]` : `{capacite_id: "presente" | "absente" | "inconnue"}`. Une seule connexion SSH exécute toutes les sondes (un script qui rend une ligne `id=0|1` par capacité) ; `inconnue` pour toutes si la connexion échoue (`ErreurSsh`, code 255, délai) ; jamais d'exception, jamais de commande mutante.
  - `refus_acces(serveur, ssh=...) -> str | None` : `None` si `sudo -n true` marche pour un utilisateur non root, sinon le message en français (utilisateur root, `sudo` demande un mot de passe, SSH impossible).

- [ ] **Step 1: Write the failing tests** (SSH factice) : `test_une_seule_connexion_pour_toutes_les_sondes`, `test_ssh_coupe_donne_inconnue_pas_absente`, `test_sortie_illisible_donne_inconnue`, `test_aucune_commande_mutante_envoyee` (argv/stdin sans `apt`, `rm`, `systemctl`, `tee`), `test_refus_acces_root_et_sudo_a_mot_de_passe`, `test_hote_invalide_refuse_avant_tout_appel`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py serveur_etat` : échec. **Step 3: Implement**. **Step 4: Run** : passe. **Step 5: Commit** (`outils/serveur_etat.py`, test) ; « Serveur générique : lecture de l'état des capacités ».

### Task 4: Interface fournisseur et fournisseur OVH

**Files:**
- Create: `outils/serveur_fournisseur.py`
- Test: `tests/test_serveur_fournisseur.py`

**Interfaces:**
- Consumes: `plateforme_ovh.lire_serveur`, `modeles_os`, `reinstaller`, `etat_tache`, `plateforme_acces.charger_ovh`, `ovh_api.ClientOvh` (existants, inchangés).
- Produces:
  - `Fournisseur` (protocole) : `nom: str` ; `lire(serveur) -> dict` (`{"os": str, "etat": str, "ip": str}`) ; `reinstaller(serveur, cle_publique: str, accord: bool) -> int` ; `etat_tache(serveur, id_tache: int) -> str` (`"en_cours" | "fini" | "echec"`).
  - `obtenir(nom: str | None, dossier=...) -> Fournisseur | None` : `None` pour `None` (serveur sans fournisseur) ; `FournisseurOvh` pour `"ovh"` ; `ValueError` pour un nom inconnu.
  - `FournisseurOvh` : délègue au code OVH existant (clés lues dans `ovh.json` du dossier) ; `reinstaller` garde l'accord strict `accord is True` avant tout appel.

- [ ] **Step 1: Write the failing tests** (client OVH factice injecté) : `test_obtenir_sans_fournisseur_renvoie_none`, `test_obtenir_inconnu_leve_valueerror`, `test_ovh_delegue_lecture_et_etat_de_tache`, `test_ovh_reinstaller_sans_accord_strict_n_ecrit_rien` (`"True"`, `1`, `None`), `test_aucun_nom_ovh_hors_du_fournisseur` (`serveur_modele`, `serveur_capacites`, `serveur_etat` ne contiennent pas « ovh » en dehors des chaînes de nom de fournisseur autorisées : test sur le texte des sources).
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py serveur_fournisseur` : échec. **Step 3: Implement**. **Step 4: Run** puis `py -3.12 outils/tests_paralleles.py test_plateforme_ovh test_plateforme` : vert. **Step 5: Commit** ; « Serveur générique : interface fournisseur et fournisseur OVH ».

### Task 5: Étapes distantes des capacités (script)

**Files:**
- Modify: `serveur_ovh/mise_en_place.sh` (nouvelles étapes `android_build`, `android_emulateur`, `unity_cli` ; usage et `case` mis à jour ; contrat JSON inchangé)
- Modify: `serveur_ovh/versions.json` (clés `android_sdk`, `unity_cli` si des versions sont épinglées)
- Test: `tests/test_serveur_ovh_script.py` (étendre, mêmes techniques : faux binaires, `--simuler`)

**Interfaces:**
- Produces: `bash mise_en_place.sh --etape android_build|android_emulateur|unity_cli [--simuler]`, statuts `fait|a_faire|bloque`, un seul objet JSON. Stdin fermé pour ces étapes (aucun secret). Contenu :
  - `android_build` : `unzip zip`, JDK 17 (paquet Ubuntu `openjdk-17-jdk-headless`), SDK dédié `~/android-sdk` via `cmdline-tools` officiels (téléchargés avec `curl -f` vers un temporaire, empreinte SHA-256 vérifiée, déplacés atomiquement), licences, `platform-tools`, `platforms;android-36`, `build-tools;36.0.0` ;
  - `android_emulateur` : `usermod -aG kvm`, `emulator`, `system-images;android-34;google_apis;x86_64`, vérification `/dev/kvm` ;
  - `unity_cli` : installation de l'outil officiel Unity CLI par son script (téléchargé, empreinte vérifiée avant exécution, installé dans `~/.local/bin`).
- Chaque étape : idempotente, vérifie avant d'agir, arrêt avec `bloque` et un détail en cas d'échec, rien de partiel laissé, aucun `curl | bash` direct.

- [ ] **Step 1: Write the failing tests** : `test_etapes_android_rendent_un_json_valide_en_simulation`, `test_android_build_telechargement_tronque_est_bloque_sans_rien_laisser`, `test_android_build_empreinte_fausse_refusee`, `test_android_emulateur_exige_dev_kvm` (absent → `bloque`), `test_unity_cli_n_execute_pas_un_script_non_verifie`, `test_etapes_idempotentes_deuxieme_passage_ne_refait_rien`, `test_autres_etapes_gardent_stdin_ferme`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py serveur_ovh_script` : échec. **Step 3: Implement**. **Step 4: Run** : passe ; `bash -n serveur_ovh/mise_en_place.sh` : OK. **Step 5: Commit** (`serveur_ovh/mise_en_place.sh`, `serveur_ovh/versions.json`, test) ; « Serveur générique : étapes distantes Android, émulateur et Unity CLI ».

### Task 6: Moteur d'installation à la demande (aperçu, accord, verrou)

**Files:**
- Create: `outils/serveur_installation.py`
- Test: `tests/test_serveur_installation.py`

**Interfaces:**
- Consumes: `serveur_capacites` (Task 2), `serveur_etat.sonder`/`refus_acces` (Task 3), `plateforme_ssh`, `plateforme.py` (`_prendre_verrou`, `_envoyer_script`, `_lancer_etape` ou leurs équivalents réexportés : réutiliser, ne pas copier), `serveur_modele.Serveur`.
- Produces:
  - `apercu(serveur, actions, ssh=...) -> dict` : `{"manquantes": [ids ordonnés], "taille_go": float, "duree_min": int, "bloquees": [{"id","raison"}], "etat": {id: etat}}` ; ne modifie rien.
  - `installer(serveur, actions, accord: bool, dossier=..., ssh=..., dormir=...) -> dict` : refuse (`ErreurAccord`-équivalent : `bloque` sans appel) sauf `accord is True` ; prend le verrou du dossier (une seule installation à la fois) ; installe les capacités manquantes dans l'ordre, chacune par son étape distante, écrit l'état `serveurs-etat.json` (sans secret) avant et après chaque étape (`en_cours`, `fait`, `bloque` + raison + geste) ; une capacité bloquée arrête la suite ; renvoie l'état par capacité.
  - `ErreurInstallation(Exception)` pour les refus (accès, accord, verrou).

- [ ] **Step 1: Write the failing tests** (SSH et script factices) : `test_apercu_ne_modifie_rien_et_donne_l_ordre`, `test_installer_sans_accord_strict_n_appelle_rien` (`"oui"`, `1`, `None`), `test_installer_dans_l_ordre_des_dependances`, `test_capacite_bloquee_arrete_la_suite_et_garde_la_raison`, `test_serveur_injoignable_donne_inconnue_et_n_installe_rien`, `test_deuxieme_installation_simultanee_refusee`, `test_relance_reprend_sans_refaire_ce_qui_est_fait`, `test_agent_refuse_avec_sa_raison`, `test_aucun_secret_dans_l_etat`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py serveur_installation` : échec. **Step 3: Implement**. **Step 4: Run** : passe ; puis `test_plateforme` : vert. **Step 5: Commit** ; « Serveur générique : installation des capacités à la demande ».

### Task 7: Routes du bureau pour les serveurs et les capacités

**Files:**
- Create: `bureau/serveurs.py`
- Modify: `bureau/serveur.py` (routes ajoutées à côté de `/api/plateforme`, sans toucher à l'existant)
- Test: `tests/test_bureau_serveurs.py`

**Interfaces:**
- Consumes: `serveur_modele`, `serveur_etat`, `serveur_installation`, `bureau/plateforme.py` (modèle de la tâche de fond et des garde-fous `X-Bureau`).
- Produces:
  - `GET /api/serveurs` → `{"serveurs": [{"id","nom","hote","utilisateur","fournisseur","capacites": {id: etat}, "ligne_cle_publique"}]}` ; ne se connecte à rien (état lu dans `serveurs-etat.json`).
  - `POST /api/serveurs` (déclarer ; corps `{nom, hote, utilisateur, fournisseur}`) → 201 ou 400 `{"erreur"}`.
  - `POST /api/serveurs/<id>/sonder` (lance une sonde en arrière-plan, un travail à la fois) → 202.
  - `POST /api/serveurs/<id>/apercu` (corps `{"actions": [...]}`) → l'aperçu.
  - `POST /api/serveurs/<id>/installer` (corps `{"actions": [...], "accord": true}`) → 202 ; l'accord n'est pris que s'il vaut exactement JSON `true` ; 409 si une installation tourne.
  - `GET /api/serveurs/lieux?actions=...` → pour chaque action, `{"serveur": {"permis": bool, "manque": [capacités], "raison": str}}` (jamais `permis` si une capacité est bloquée ou non installable).
  - Mêmes protections que `/api/plateforme/installer` : `X-Bureau: 1`, `Content-Type: application/json`, corps ≤ 1 Ko (2 Ko pour la déclaration), 404 sur un écouteur distant ; exceptions du fil de fond jamais affichées en clair (masquage).

- [ ] **Step 1: Write the failing tests** : `test_get_serveurs_ne_se_connecte_a_rien`, `test_declarer_refuse_root_et_hote_piege_avec_400`, `test_installer_sans_en_tete_bureau_refuse`, `test_installer_accord_non_booleen_ne_lance_rien`, `test_installer_deuxieme_lancement_409`, `test_lieux_serveur_non_permis_si_capacite_bloquee`, `test_route_distante_404`, `test_reponses_sans_secret`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py test_bureau_serveurs` : échec. **Step 3: Implement** (suivre `bureau/plateforme.py`). **Step 4: Run** puis `py -3.12 outils/tests_paralleles.py test_bureau_plateforme test_bureau_deport test_deport_logique` : vert. **Step 5: Commit** ; « Serveur générique : routes du bureau pour les serveurs et les capacités ».

### Task 8: Écrans de paramétrage du serveur

**Files:**
- Create: `bureau/web/ui/serveurs.js`, `bureau/web/tests/serveurs.test.js`
- Modify: `bureau/web/ui/panneaux.js` (montage dans le panneau Direction, à côté de la carte « Serveur » existante, additif), `bureau/web/style.css` (additif)

**Interfaces:**
- Consumes: les routes de la Task 7.
- Produces: `export function ecranServeurs(etat, {fetchFn, planifier})` → élément DOM avec : (a) formulaire « Déclarer un serveur » (nom, adresse, utilisateur, fournisseur : aucun/OVH) avec la **ligne de clé publique à copier** et un bouton « Tester la connexion » ; (b) la liste des capacités (`présente`, `absente`, `inconnue`, `bloquée`, `non installable` avec la raison) et les boutons « Installer » (ouvre l'aperçu : capacités, taille, durée estimées, bouton de confirmation avec case d'accord décochée par défaut et à usage unique) et « Vérifier » ; (c) « Où tournent les actions » : par action, lieux `poste`, `GitHub`, `serveur`, **le choix `serveur` grisé avec ce qui manque tant que le serveur ne le permet pas** ; chaque lieu porte la couleur de la recommandation de la Task 12 (vert recommandé, ambre possible, rouge déconseillé, gris indisponible), avec la raison au survol, une légende et un libellé en toutes lettres à côté de la pastille (la couleur n'est jamais le seul signal) ; ce n'est qu'un conseil, le choix reste au Directeur. Tout texte du serveur est inséré avec `textContent` ; liens http(s) construits par le DOM ; interrogation périodique injectable, arrêtée quand la carte disparaît.
- `export async function installerCapacites(idServeur, actions, accord, fetchFn = fetch) -> {ok, message}` : ne lève jamais ; `accord` n'est envoyé `true` que si la case est cochée.

- [ ] **Step 1: Write the failing tests** (même style que `plateforme.test.js`) : `la ligne de cle publique est affichee et copiable`, `le choix serveur est grise avec ce qui manque`, `le choix serveur est actif quand les capacites sont presentes`, `l accord n est jamais envoye vrai sans la case cochee`, `la case d accord se decoche apres l envoi`, `un texte du serveur avec du HTML n est pas interprete`, `serveur injoignable affiche un message sans exception`, `capacite non installable affiche sa raison`.
- [ ] **Step 2: Run** `node --test bureau/web/tests/serveurs.test.js` : échec. **Step 3: Implement** ; vérifier dans le vrai bureau (`preview_start` ou `lancer.py serveur --bureau <fichier temporaire>`) que l'écran s'affiche sans erreur avec un état vide. **Step 4: Run** `node --test bureau/web/tests/*.test.js` : vert. **Step 5: Commit** ; « Serveur générique : écrans de paramétrage du serveur ».

### Task 9: Ligne de commande générique

**Files:**
- Modify: `outils/plateforme.py` (`main` : sous-commandes déléguant à un nouveau module) ; Create: `outils/serveur_cli.py`
- Modify: `lancer.py` (docstring d'usage seulement)
- Test: `tests/test_serveur_cli.py`

**Interfaces:**
- Produces: `py -3.12 lancer.py plateforme serveurs [declarer <nom> <hote> <utilisateur> [--fournisseur ovh]|lister|cle <id>|sonder <id>|apercu <id> <action>...|installer <id> <action>... [--accord]]` ; codes de sortie 0 (ok), 1 (échec ou bloqué), 2 (usage) ; la sortie JSON est masquée comme les autres commandes ; `installer` sans `--accord` affiche seulement l'aperçu et sort avec le code 1.

- [ ] **Step 1: Write the failing tests** : `test_declarer_puis_lister`, `test_cle_affiche_la_ligne_publique_seulement`, `test_apercu_ne_modifie_rien`, `test_installer_sans_accord_affiche_l_apercu_et_n_installe_pas`, `test_usage_et_codes_de_sortie`, `test_aucune_sortie_ne_contient_un_secret`.
- [ ] **Step 2–5:** run en échec, implémenter, run vert (`serveur_cli`, `test_plateforme`), commit ; « Serveur générique : commandes de ligne de commande ».

### Task 10: Migration automatique du serveur OVH existant (DERNIÈRE ÉTAPE)

**Files:**
- Create: `outils/serveur_migration.py`
- Modify: `bureau/serveurs.py` (route d'aperçu et de confirmation de la migration)
- Test: `tests/test_serveur_migration.py`

**Interfaces:**
- Consumes: `plateforme_acces.charger_ovh`, le cache `plateforme.json` (champ `ip`), `serveur_modele`, `serveur_etat.sonder`, `serveur_capacites`.
- Produces:
  - `detecter(dossier=DOSSIER) -> dict | None` : `None` si un serveur est déjà déclaré ou si `ovh.json` ou `plateforme.json` manque ; sinon la proposition `{serveur: Serveur(fournisseur="ovh", hote=<ip du cache>, utilisateur="ubuntu", cle=<clé dédiée existante>), source: [fichiers lus]}`.
  - `apercu(proposition, ssh=...) -> dict` : la proposition plus l'état réel des capacités (sondes en lecture seule) ; modifie RIEN.
  - `confirmer(proposition, accord: bool, dossier=DOSSIER) -> Serveur` : `accord is True` strict ; écrit l'entrée dans `serveurs.json` et l'état des capacités sondées dans `serveurs-etat.json` ; idempotente (deuxième appel : refus « déjà déclaré ») ; ne touche ni `ovh.json`, ni `plateforme.json`, ni le serveur.
  - Au démarrage du bureau : si `detecter` renvoie une proposition, le bureau affiche « Votre serveur OVH a été détecté » avec l'aperçu et un bouton de confirmation (jamais d'écriture sans confirmation).

- [ ] **Step 1: Write the failing tests** : `test_detecter_sans_fichiers_ne_propose_rien`, `test_detecter_propose_le_serveur_ovh_depuis_le_cache`, `test_detecter_n_ecrase_pas_un_serveur_deja_declare`, `test_apercu_ne_fait_que_lire` (SSH factice : aucune commande mutante ; fichiers inchangés), `test_confirmer_sans_accord_strict_n_ecrit_rien`, `test_confirmer_deux_fois_refusee`, `test_sondes_en_echec_donnent_inconnue_et_pas_absente`, `test_anciens_fichiers_laisses_intacts`, `test_aucune_reinstallation_possible` (le fournisseur OVH n'est jamais appelé en écriture).
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py serveur_migration` : échec. **Step 3: Implement**. **Step 4: Run** : passe ; `node --test bureau/web/tests/*.test.js` : vert. **Step 5: Commit** ; « Serveur générique : migration automatique du serveur OVH existant ».

### Task 11: Documentation et vérification complète

**Files:**
- Create: `docs/serveur.md` (guide du serveur générique : contrat minimal, déclarer un serveur, capacités, aperçu et accord, écrans, ligne de commande, migration, limites) ; Modify: `docs/serveur-ovh.md` (renvoi : OVH est un fournisseur ; la migration), `docs/superpowers/specs/2026-11-19-serveur-generique-design.md` (note de réalisation si un choix a changé)

- [ ] **Step 1:** rédiger en vérifiant chaque commande, route, fichier et message contre le code ; dire ce qui n'a pas été exécuté sur un vrai serveur ; mettre à jour « Suite » (morceaux 2 à 4, raccordement à `bureau/deport_types.py` une fois le travail de déport commité).
- [ ] **Step 2:** suite complète `py -3.12 outils/tests_paralleles.py` (≈ 4 minutes ; tests instables connus : `test_inst_examen`, `test_moteur_detache` : à relancer seuls), puis `node --test bureau/web/tests/*.test.js`, `bash -n serveur_ovh/mise_en_place.sh`, et `git grep` qu'aucun fragment de clé OVH réelle n'est suivi (liste tenue hors dépôt).
- [ ] **Step 3: Commit** (`docs/serveur.md`, `docs/serveur-ovh.md`, spec) ; « Documentation : serveur générique ». Ne rien pousser.

### Task 12: Recommandation des lieux par couleur (à exécuter après la Task 7 et avant la Task 8)

**Files:**
- Create: `outils/serveur_recommandation.py`
- Modify: `bureau/serveurs.py` (la route `GET /api/serveurs/lieux` de la Task 7 gagne les champs `niveau` et `raison` par lieu)
- Test: `tests/test_serveur_recommandation.py`

**Interfaces:**
- Consumes: `serveur_capacites.manquantes_pour`/`bloquees` (Task 2), l'état des capacités (Task 3), les durées mesurées par lieu et par action (lire `bureau/deport_conso.py` et le cache de consommation pour la forme réelle ; si une durée par lieu n'existe pas pour un lieu, `None`), la charge du poste (mémoire libre, processeur : réutiliser la mesure existante des processus du bureau si elle est lisible sans effet de bord), la charge du serveur (une lecture SSH en lecture seule ajoutée à la sonde de la Task 3 : `uptime` charge moyenne, `nproc`, `free -m`, nombre de conteneurs d'outils en cours).
- Produces:
  - `Mesures` (dataclass figée) : `duree_min: dict[str, float | None]` (par lieu), `charge_poste: float | None` (0 à 1), `charge_serveur: float | None` (0 à 1), `quota_github_restant: float | None` (0 à 1), `serveur_joignable: bool`.
  - `recommander(action: str, lieux_permis: dict[str, bool], mesures: Mesures) -> dict[str, dict]` : pour chacun de `poste`, `github`, `serveur` : `{"niveau": "recommande" | "possible" | "deconseille" | "indisponible", "raison": str, "fondee_sur": "mesures" | "regles"}`. Règles : `indisponible` si le lieu n'est pas permis ou si le serveur est injoignable ; `deconseille` si la charge du lieu dépasse 0,85 ou si le quota GitHub restant est sous 0,15 ; `recommande` pour le lieu permis le plus rapide (durée mesurée) parmi ceux non déconseillés, avec un écart d'au moins 15 % sur le suivant, sinon `possible` pour tous les lieux permis non déconseillés ; sans durée mesurée, repli sur des règles simples (charge la plus basse) avec `fondee_sur: "regles"`. Au plus un lieu `recommande`. Jamais de mouvement automatique : la fonction ne fait que conseiller.

- [ ] **Step 1: Write the failing tests** : `test_lieu_non_permis_est_indisponible`, `test_serveur_injoignable_est_indisponible_et_pas_deconseille`, `test_le_plus_rapide_est_recommande_si_ecart_net`, `test_ecart_faible_donne_possible_pour_tous`, `test_poste_surcharge_est_deconseille_et_serveur_recommande`, `test_quota_github_bas_deconseille_github`, `test_sans_mesure_repli_sur_les_regles_et_le_dit`, `test_au_plus_un_recommande`, `test_raison_ne_contient_aucun_secret_ni_chemin`, `test_charge_serveur_inconnue_ne_donne_jamais_recommande`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py serveur_recommandation` : échec. **Step 3: Implement** et étendre la route des lieux (champs `niveau`, `raison`, `fondee_sur` ; test dans `tests/test_bureau_serveurs.py`). **Step 4: Run** : passe. **Step 5: Commit** ; « Serveur générique : recommandation des lieux par couleur ».

---

## Suite (hors de ce plan)
Morceau 2 (lancer des tâches sur le serveur : lanceur SSH, verrou et créneaux, résultats dans la fiche), morceau 3 (agents : image d'agent, abonnement, conteneurs d'outils séparés), morceau 4 (bouton d'accès SSH et vue graphique, suivi). Le raccordement des écrans « Où tournent les actions » aux catalogues par genre (`bureau/deport_types.py`) exige que le travail de déport du Directeur soit commité.

## Self-Review

- **Couverture du design :** modèle (T1), capacités et besoins (T2), sondes en lecture seule (T3), fournisseur (T4), étapes distantes (T5), installation à la demande avec aperçu, accord, verrou (T6), routes (T7), écrans de paramétrage avec actions grisées (T8), ligne de commande (T9), migration en dernier (T10), documentation (T11). Hors-buts respectés (aucun lancement de tâche ni d'agent).
- **Cohérence des noms :** `Serveur`, `Capacite`, `CATALOGUE`, `BESOINS`, `sonder`, `apercu`, `installer`, `detecter`, `confirmer` identiques d'une tâche à l'autre.
- **Proportion :** signatures et tests nommés, aucune fonction réécrite en entier.
