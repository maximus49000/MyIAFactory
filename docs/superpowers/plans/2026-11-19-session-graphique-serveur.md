# Session graphique sur le serveur OVH (Unity Hub par défaut) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter à la plateforme OVH une étape facultative « Session graphique » (bureau XFCE + xrdp + Firefox + Unity Hub lancé au démarrage de la session) et une commande qui ouvre le tunnel SSH et le client Bureau à distance de Windows.

**Architecture:** Une nouvelle étape distante `bureau_distant` dans `serveur_ovh/mise_en_place.sh` (même contrat JSON que les autres, rejouable), pilotée par un nouveau module `outils/plateforme_bureau.py` (mot de passe de session, étape, ouverture du tunnel et de mstsc) branché par quelques lignes dans `outils/plateforme.py` (déjà plus de 500 lignes : ne pas y ajouter de logique). L'étape ne tourne que sur demande (`installer --bureau-distant`) ; « prêt » ne change pas.

**Tech Stack:** Python 3.12 (bibliothèque standard, `unittest`), bash, OpenSSH et mstsc de Windows, xrdp/XFCE sur Ubuntu 24.04.

**Spec:** `docs/superpowers/specs/2026-11-19-session-graphique-serveur-design.md` (et, pour l'existant, `2026-11-19-serveur-ovh-plateforme-design.md`).

## Global Constraints

- Branche et worktree existants : `worktree-serveur-ovh-plateforme` dans `.claude/worktrees/serveur-ovh-plateforme`. Commits par `git add <chemins>`, rien de poussé, jamais `git add -A`.
- Aucune dépendance nouvelle ; tests entièrement simulés (jamais de vrai SSH, serveur, mstsc ni écriture dans le vrai `~/MyIAFactory` : le dossier est injecté ; `tests/__init__.py` pose déjà un dossier temporaire par défaut).
- Aucun port public : xrdp écoute sur `127.0.0.1:3389` uniquement ; `ufw` reste sur le port 22 seul ; la connexion SSH par mot de passe reste désactivée.
- Le mot de passe de session : généré au hasard (24 caractères ou plus, alphabet sans ambiguïté), écrit seulement dans `<dossier>/bureau-distant.txt` ; jamais dans le cache `plateforme.json`, la sortie, les journaux, les arguments de commande (entrée standard SSH uniquement) ni le dépôt ; il est ajouté à `c.secrets` pour le masquage.
- « Prêt » = étapes 1 à 6 (inchangé) ; l'étape 8 ne se lance qu'avec `--bureau-distant` et n'influe ni sur `pret` ni sur `pret_sans_unity`.
- Messages en français. `outils/plateforme.py` ne reçoit que des branchements (≈ 30 lignes au plus) ; la logique va dans `outils/plateforme_bureau.py`.
- Tests via le lanceur : `py -3.12 outils/tests_paralleles.py <module>` (une campagne à la fois) ; la suite complète une fois à la fin, puis `node --test bureau/web/tests/*.test.js`.
- Le script distant garde son contrat : un seul objet JSON `{"etape","statut":"fait|a_faire|bloque","detail","versions","disque_libre_go"}` ; l'entrée standard n'est lue que par les étapes `licence` et `bureau_distant`, toutes les autres l'ont fermée.
- Réalité à ne pas oublier : le serveur est en service (Ubuntu 24.04, durci, Docker et images faits) ; aucune tâche de ce plan ne le touche. L'exécution réelle de l'étape 8 est une action distincte qui exige l'accord du Directeur.

## Review Focus

- Le mot de passe de session n'apparaît nulle part sauf dans `bureau-distant.txt` : ni dans `plateforme.json`, ni dans la sortie de `lancer.py plateforme`, ni dans un argument de `ssh`/`mstsc`, ni dans un message d'erreur.
- xrdp lié à `127.0.0.1` ET aucune règle `ufw` pour 3389 : l'étape échoue (`bloque`) si `ss -ltn` montre 3389 sur une autre adresse que loopback.
- Une relance de l'étape ne change pas le mot de passe (fichier relu, pas régénéré) et ne casse pas une session ouverte.
- L'étape 8 ne s'exécute jamais sans `--bureau-distant`, même si toutes les autres sont faites ; l'état affiché dit pourquoi elle est `a_faire`.
- Le tunnel : port local libre choisi (pas de collision avec 33890 déjà pris), arrêt garanti du processus `ssh` quand mstsc se ferme ou en cas d'erreur, aucune écoute sur une adresse autre que `127.0.0.1` côté PC.
- Fichier `bureau-distant.txt` : droits restreints à l'utilisateur Windows (icacls au mieux), jamais affiché en entier ; la commande dit seulement où il se trouve.

---

### Task 1: Étape distante `bureau_distant` dans le script

**Files:**
- Modify: `serveur_ovh/mise_en_place.sh` (nouvelle fonction `etape_bureau_distant`, entrée dans le `case` et la liste d'usage ; en-tête : le contrat stdin cite maintenant `licence` et `bureau_distant`)
- Modify: `serveur_ovh/versions.json` (clé `unity_hub` si une version est épinglée ; sinon la source du dépôt Unity Hub y est notée)
- Test: `tests/test_serveur_ovh_script.py` (étendre) — mêmes techniques que les tests existants (faux binaires sur le PATH, `--simuler`)

**Interfaces:**
- Produces: `bash mise_en_place.sh --etape bureau_distant [--simuler]` lit sur l'entrée standard **une seule ligne : le mot de passe de session** ; rend le JSON habituel. Détails en cas de succès : « Session graphique prête : bureau XFCE, xrdp sur 127.0.0.1:3389, Unity Hub au démarrage de la session. » Statuts : `a_faire` (mot de passe absent), `bloque` (mot de passe < 16 caractères, 3389 exposé hors loopback, paquet ou service absent), `fait`.

- [ ] **Step 1: Write the failing tests** (noms et assertions) :
  - `test_bureau_distant_rend_un_json_valide_en_simulation` (statut présent, un seul objet JSON, rien d'exécuté en `--simuler`).
  - `test_bureau_distant_sans_mot_de_passe_est_a_faire` (stdin vide → `a_faire`, aucun `chpasswd`/`apt` appelé).
  - `test_bureau_distant_refuse_un_mot_de_passe_trop_court` (15 caractères → `bloque`, détail sans le mot de passe).
  - `test_bureau_distant_mot_de_passe_jamais_en_argument_ni_dans_la_sortie` (faux `sudo`/`chpasswd` enregistrent argv : le mot de passe n'y est pas ; la sortie JSON non plus).
  - `test_bureau_distant_xrdp_ecoute_seulement_en_loopback` (faux `ss` montrant 3389 sur `0.0.0.0` → `bloque` ; sur `127.0.0.1` → fait).
  - `test_bureau_distant_ne_touche_pas_ufw` (aucun appel `ufw` autre que `status`).
  - `test_bureau_distant_autostart_unityhub` (le fichier `~/.config/autostart/unityhub.desktop` est demandé avec `Exec=` contenant `unityhub`).
  - `test_autres_etapes_gardent_stdin_ferme` (l'ancien test existant : mis à jour pour que seules `licence` et `bureau_distant` lisent stdin).
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py serveur_ovh_script` : les nouveaux tests échouent.
- [ ] **Step 3: Implement `etape_bureau_distant`** dans `serveur_ovh/mise_en_place.sh` : lit la première ligne de stdin (`IFS= read -r`), vérifie la longueur ; installe `xfce4 xfce4-terminal dbus-x11 xrdp` (apt non interactif), Firefox hors snap (dépôt Mozilla avec trousseau signé et priorité de paquet) et `unityhub` depuis le dépôt officiel d'Unity (`hub.unity3d.com/linux/repos/deb`, clé publique `hub.unity3d.com/linux/keys/public`) ; configure xrdp pour `127.0.0.1` seulement (`port=tcp://127.0.0.1:3389` dans `/etc/xrdp/xrdp.ini`), `~/.xsession` = `startxfce4`, ajoute `xrdp` au groupe `ssl-cert`, active le service ; fixe le mot de passe par `printf 'ubuntu:%s\n' "$mdp" | sudo chpasswd` (jamais en argument, jamais affiché) ; écrit `~/.config/autostart/unityhub.desktop` ; vérifie `ss -ltn` (3389 uniquement sur loopback), l'absence de règle `ufw` pour 3389, le binaire `unityhub`. Sorties JSON via `repondre` existant ; `--simuler` n'exécute rien de mutant.
- [ ] **Step 4: Run** le même module : tout passe ; `bash -n serveur_ovh/mise_en_place.sh` : OK.
- [ ] **Step 5: Commit** : `git add serveur_ovh/mise_en_place.sh serveur_ovh/versions.json tests/test_serveur_ovh_script.py` ; message « Serveur OVH : étape session graphique (xrdp, XFCE, Unity Hub) ».

### Task 2: Branchement dans la machine à états et mot de passe de session

**Files:**
- Create: `outils/plateforme_bureau.py` (mot de passe, étape distante)
- Modify: `outils/plateforme.py` (≈ 30 lignes : `ETAPES` gagne `"bureau_distant"`, `LIBELLES`, `ENCOURS`, `DELAIS_ETAPE_S`, entrée dans `ACTIONS`, paramètre `bureau_distant: bool = False` de `installer`/`_installer`, drapeau `--bureau-distant` dans `main`, usage mis à jour)
- Test: `tests/test_plateforme_bureau.py` (nouveau) + ajustements de `tests/test_plateforme.py` si un test compte sept étapes

**Interfaces:**
- Produces dans `outils/plateforme_bureau.py` :
  - `FICHIER_MDP = "bureau-distant.txt"`
  - `mot_de_passe(dossier: Path) -> str` : relit `<dossier>/bureau-distant.txt` s'il existe (premier ligne, ≥ 16 caractères), sinon génère (`secrets.choice`, 24 caractères, alphabet sans `0Oo1lI`), écrit le fichier (UTF-8, restreint à l'utilisateur : `os.chmod(0o600)` et `icacls` au mieux sur Windows) et le renvoie.
  - `etape_bureau_distant(c, lancer_etape) -> dict` : `c` est le `_Contexte` ; ajoute le mot de passe à `c.secrets` AVANT tout envoi ; appelle `lancer_etape(c, "bureau_distant", stdin=mdp + "\n")` ; renvoie le rapport (`{"statut","detail","geste"}`) ; ajoute un `geste` en cas de `fait` : « Lancez py -3.12 lancer.py plateforme bureau-distant pour ouvrir la session ; le mot de passe est dans <chemin>. »
- Consumes (existant, `outils/plateforme.py`) : `_Contexte` (`c.dossier`, `c.secrets`, `c.masquer`), `_lancer_etape(c, etape, stdin=None) -> dict`, `_rapport(statut, detail, geste)`, `calculer_etat(rapports)`, `installer(dossier, accord_reinstallation, client, ssh, dormir, vivant)`.
- `calculer_etat` : l'étape `bureau_distant` figure toujours dans `etapes` ; absente des rapports → `a_faire` avec `detail="Facultative : non demandée (installer --bureau-distant)."` ; `pret`/`pret_sans_unity` inchangés (toujours `etapes[:6]`).

- [ ] **Step 1: Write the failing tests** :
  - `test_mot_de_passe_genere_puis_relu` (deux appels = même valeur ; ≥ 24 caractères ; alphabet sans ambiguïtés ; fichier créé dans le dossier injecté).
  - `test_mot_de_passe_trop_court_dans_le_fichier_est_regenere_avec_prevenance` (fichier de 5 caractères → régénéré ; jamais d'exception).
  - `test_etape_envoie_le_mot_de_passe_par_stdin_seulement` (faux SSH : stdin = mdp + "\n" ; le mot de passe n'est dans aucun `argv`).
  - `test_mot_de_passe_absent_de_l_etat_du_cache_et_de_la_sortie` (état renvoyé, `plateforme.json` et sortie de `main` ne contiennent pas le mot de passe ; il est masqué si le faux script le répète dans `detail`/stderr).
  - `test_installer_sans_drapeau_ne_lance_pas_l_etape_8` (toutes étapes 1 à 6 faites ; aucun appel `--etape bureau_distant` ; l'étape 8 vaut `a_faire` avec le détail « Facultative… » ; `pret` vrai).
  - `test_installer_avec_drapeau_lance_l_etape_8_apres_les_images` (ordre vérifié ; `pret` inchangé ; le statut remonte).
  - `test_etape_8_bloquee_ne_change_pas_pret` (`bloque` → `pret` toujours vrai si 1 à 6 faites).
  - `test_calculer_etat_a_huit_etapes_dans_l_ordre`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py plateforme_bureau test_plateforme` : échec attendu.
- [ ] **Step 3: Implement** `mot_de_passe` et `etape_bureau_distant` dans `outils/plateforme_bureau.py` ; brancher dans `outils/plateforme.py` : `ETAPES = (..., "licence", "bureau_distant")`, `LIBELLES["bureau_distant"] = "Session graphique (Unity Hub, facultative)"`, `ENCOURS["bureau_distant"] = "Installation de la session graphique en cours (quelques minutes)."`, `DELAIS_ETAPE_S["bureau_distant"] = 1500`, `ACTIONS["bureau_distant"] = lambda c: plateforme_bureau.etape_bureau_distant(c, _lancer_etape)`, et dans `_installer` : l'étape `bureau_distant` n'est exécutée que si le paramètre `bureau_distant` est vrai, sinon son rapport reste `a_faire` avec le détail ci-dessus et la boucle continue sans bloquer ; ajouter `--bureau-distant` à `main`. Ne pas toucher aux autres comportements.
- [ ] **Step 4: Run** les mêmes modules, puis `py -3.12 outils/tests_paralleles.py test_plateforme test_bureau_plateforme` : tout passe (ajuster, de façon explicite, les tests existants qui comptaient sept étapes).
- [ ] **Step 5: Commit** : `git add outils/plateforme_bureau.py outils/plateforme.py tests/test_plateforme_bureau.py tests/test_plateforme.py` ; message « Plateforme : étape facultative session graphique et mot de passe de session ».

### Task 3: Commande `bureau-distant` (tunnel SSH + client Windows) et carte

**Files:**
- Modify: `outils/plateforme_bureau.py` (ajouter `ouvrir`)
- Modify: `outils/plateforme.py` (`main` : sous-commande `bureau-distant`, 5 lignes qui délèguent)
- Modify: `bureau/web/tests/plateforme.test.js` et au besoin `bureau/web/ui/plateforme.js` (la carte doit afficher huit étapes ; l'étape 8 facultative a son badge « à faire » sans alarme)
- Test: `tests/test_plateforme_bureau.py` (étendre), `bureau/web/tests/plateforme.test.js`

**Interfaces:**
- Produces : `ouvrir(dossier: Path, popen=subprocess.Popen, lancer_rdp=subprocess.run, port_libre=_port_libre, attendre_port=_attendre_port, ssh_options=plateforme_ssh._options) -> int` (code de sortie 0/1/2) :
  1. lit l'état en cache : l'étape `bureau_distant` doit être `fait`, sinon message (« Installez d'abord la session : lancer.py plateforme installer --bureau-distant ») et code 1 ;
  2. choisit un port local libre (33890 si libre, sinon un port libre) ;
  3. lance le tunnel `ssh -N -L 127.0.0.1:<port>:127.0.0.1:3389` avec les options sûres existantes (clé dédiée, hôte du cache, `--` avant l'hôte) ; attend l'ouverture du port (délai borné) ;
  4. écrit `<dossier>/bureau-distant.rdp` (`full address:s:127.0.0.1:<port>`, `username:s:ubuntu`, aucune mention du mot de passe) ;
  5. lance `mstsc <fichier.rdp>` (Windows seulement ; ailleurs : message clair, code 2) et attend sa fermeture ; dans tous les cas (y compris exception) termine le processus du tunnel ;
  6. affiche seulement : le chemin du fichier mot de passe (jamais son contenu).
- Consumes : `plateforme_ssh` (options sûres, `ErreurSsh`), `_lire_cache(dossier)`, `FICHIER_MDP` (Task 2).
- UI : `carteServeur` existante rend les étapes de l'état reçu ; rien de nouveau côté serveur.

- [ ] **Step 1: Write the failing tests** :
  - `test_ouvrir_refuse_si_l_etape_8_n_est_pas_faite` (code 1, aucun `popen`).
  - `test_ouvrir_lance_le_tunnel_en_loopback_puis_mstsc` (arguments du faux `popen` : `-N`, `-L` avec `127.0.0.1:<port>:127.0.0.1:3389`, `-i`, `--` avant l'hôte, `StrictHostKeyChecking=accept-new`, jamais `=no` ; fichier `.rdp` écrit avec `full address:s:127.0.0.1:<port>` et sans `password`).
  - `test_ouvrir_arrete_le_tunnel_meme_si_mstsc_echoue` (exception du faux `lancer_rdp` → `terminate` appelé, code non nul, pas de trace de pile).
  - `test_ouvrir_choisit_un_autre_port_si_33890_est_pris`.
  - `test_ouvrir_n_affiche_jamais_le_mot_de_passe` (sortie capturée ne contient pas le contenu du fichier).
  - `test_ouvrir_hors_windows_dit_que_mstsc_est_absent` (code 2, tunnel non lancé).
  - Côté node : `la carte liste huit étapes dont la session graphique facultative` ; `l'étape facultative à faire n'est pas présentée comme une alerte`.
- [ ] **Step 2: Run** `py -3.12 outils/tests_paralleles.py plateforme_bureau` : échec attendu ; `node --test bureau/web/tests/plateforme.test.js` : échec attendu.
- [ ] **Step 3: Implement** `ouvrir` dans `outils/plateforme_bureau.py`, la sous-commande dans `main` (usage mis à jour : `lancer.py plateforme <etat|installer|verifier|bureau-distant> …`), et l'ajustement minimal de `bureau/web/ui/plateforme.js` s'il suppose sept étapes.
- [ ] **Step 4: Run** les deux commandes ci-dessus : tout passe ; puis `node --test bureau/web/tests/*.test.js`.
- [ ] **Step 5: Commit** : `git add outils/plateforme_bureau.py outils/plateforme.py tests/test_plateforme_bureau.py bureau/web/ui/plateforme.js bureau/web/tests/plateforme.test.js` ; message « Plateforme : commande bureau-distant (tunnel SSH et Bureau à distance) ».

### Task 4: Documentation et vérification complète

**Files:**
- Modify: `docs/serveur-ovh.md` (section « Session graphique » : drapeau `--bureau-distant`, commande `bureau-distant`, mot de passe `bureau-distant.txt`, usage de Hub et de la licence, limites, dépannage, « Non vérifié » mis à jour ; l'étape facultative figure dans le tableau des étapes)
- Modify: `docs/superpowers/specs/2026-11-19-session-graphique-serveur-design.md` (note de réalisation si un choix a changé)

- [ ] **Step 1:** rédiger la section en vérifiant chaque commande et drapeau contre le code (`outils/plateforme.py` `main`, `outils/plateforme_bureau.py`) ; dire que l'exécution réelle sur le serveur n'a pas encore eu lieu et ce qui est « Non vérifié » (paquet et dépôt Unity Hub, xrdp+XFCE sur 24.04, démarrage de Hub dans la session, licence Personal utilisable en compilation) ; rappeler que le mot de passe reste dans `bureau-distant.txt` seulement.
- [ ] **Step 2:** suite complète `py -3.12 outils/tests_paralleles.py` (≈ 4 minutes ; un test instable `test_inst_examen` qui repasse seul est connu), puis `node --test bureau/web/tests/*.test.js`, `bash -n serveur_ovh/mise_en_place.sh`, et `git grep` qu'aucun fragment de clé OVH réelle (`ee279d7a`, `eed004db`, `8c7d7a60`, `f3c3a90b`, `0a2d814d`, `350bf0d1`, `71fa5a13`, `e387741b`, `c67bfe11`, `xxxxxxfa`, `xxxxxx7c`, `exxxxxx3`) n'est suivi.
- [ ] **Step 3: Commit** : `git add docs/serveur-ovh.md docs/superpowers/specs/2026-11-19-session-graphique-serveur-design.md` ; message « Documentation : session graphique du serveur ». Ne rien pousser.

---

## Self-Review

- **Couverture de la spec :** étape 8 facultative distante (T1) ; branchement, drapeau, mot de passe (T2) ; commande tunnel + client + `.rdp` (T3) ; documentation et suites (T4). Hors-buts respectés (pas de bouton du bureau, pas de terminal SSH, pas d'Unreal).
- **Cohérence des noms :** `bureau_distant` (identifiant d'étape, option du script), `--bureau-distant` (drapeau), `bureau-distant` (sous-commande), `FICHIER_MDP = "bureau-distant.txt"`, `ouvrir`, `mot_de_passe`, `etape_bureau_distant` : identiques dans les trois tâches.
- **Proportion :** plan court, signatures et tests nommés, aucune fonction réécrite en entier.
