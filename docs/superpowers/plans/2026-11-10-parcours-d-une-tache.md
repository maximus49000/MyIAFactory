# Le parcours d'une tâche — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (une conversation par phase, voir la passation). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un orchestrateur générique fourni par la skill mène une fonctionnalité du cadrage à la production en série ; la mémoire a trois étages (skill, genre, projet) ; le bureau suit plusieurs projets, avec « Nouvelle fonctionnalité », la discussion de cadrage, le Directeur enrichi et le catalogue de chaque fonctionnalité ; le projet pilote passe dessus sans rien perdre.

**Architecture:** Côté bureau : le relevé passe en version 4 (`releve.py`, `etat.py`), sept demandes nouvelles (`demandes.py`, images jointes en base64), un serveur à plusieurs projets (`serveur.py` scindé en `Projet` et `Bureau`, `--bureau`), le catalogue et le dernier livrable servis (`catalogue.py`). Côté page : `ui/projets.js` (sélecteur), `ui/fonctionnalite.js` (panneau et discussion), `ui/directeur.js` enrichi, `ui/catalogue.js` et `ui/vue-de-haut.js`. Nouveau dossier `orchestrateur/` : `consignes.md`, `interface.md`, `memoire/`, `modeles/`, et des outils Python (`factory.py`, `suivi.py`, `memoire.py`, `depart.py`, `outil.py`, `verifier_interface.py`). Les phases H à J se font dans le dépôt privé du projet pilote.

**Tech Stack:** Python 3.12 bibliothèque standard ; JavaScript en modules ; `git` en ligne de commande (mémoire partagée) ; tests `unittest` et `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-10-parcours-d-une-tache-design.md` (contexte : les trois conceptions précédentes du même dossier).

## Global Constraints

- Dépôt public, vide de tout projet : aucun nom, lieu, chemin, fichier ou personne d'un projet réel, ni dans le code, ni dans les mémoires `orchestrateur/memoire/`, ni dans les exemples. Le projet pilote n'est jamais nommé.
- Python : `py -3.12`, bibliothèque standard uniquement. Tests : `py -3.12 -m unittest discover -s tests -v` et `node --test "bureau/web/tests/*.test.js"` (guillemets compris).
- Relevé : `version` 1, 2, 3 ou 4. Un relevé 1, 2 ou 3 marche exactement comme avant ; `lancer.py serveur --reglages <fichier>` marche comme avant (un projet, pas de sélecteur). Tous les ajouts de la version 4 sont facultatifs.
- **Le bureau n'agit jamais lui-même et ne parle à aucune IA** : chaque geste est une demande à la commande d'actions du projet choisi ; l'effet n'apparaît qu'au relevé suivant ; aucune requête sortante nouvelle.
- Demandes nouvelles (§8.2 de la spec, champs exacts) : `fonctionnalite`, `message`, `cahier` (`valider`|`corriger`), `methode` (`valider`|`revoir`|`garder`), `genre`, `session_cloud`, `retour_element` ; `lecon` gagne `etage?` ∈ `projet`, `genre`, `skill`. Textes : 3 500 caractères au plus.
- Images jointes : 4 au plus par demande, 5 Mo chacune une fois décodées, `{nom, type, donnees}` avec `type` ∈ `image/png`, `image/jpeg`, extension `.png`, `.jpg` ou `.jpeg`, contenu vérifié par sa signature. Le bureau ne les écrit nulle part : la commande d'actions du projet les range.
- Identifiant de genre : `^[a-z0-9][a-z0-9-]{0,39}$` (il devient un nom de fichier). Mémoires : `orchestrateur/memoire/skill.md`, `orchestrateur/memoire/genres/<id>.md`.
- Une leçon d'étage genre ou skill n'est commitée qu'après `git pull --rebase` réussi et vérification des mots interdits du projet (comparaison en minuscules, sans accents) ; en cas de conflit ou de mot interdit : arrêt, rien n'est écrit, message clair. Les tests n'utilisent que des dépôts git temporaires locaux, jamais un dépôt distant réel.
- Modèles : on monte d'un cran au plus (Haiku → Sonnet → Opus) ; **Fable n'est jamais choisi par un outil** ni par une phase de ce plan.
- Textes de la page toujours insérés comme texte (`textContent`).
- Chaque tâche : test d'abord, le voir échouer, coder, le voir passer, tous les tests ; cocher dans le `README.md` ; commit en français terminé par `Co-Authored-By: Claude <modèle de la conversation> <noreply@anthropic.com>` ; `git push`.

## Review Focus

1. Bureau à deux projets : une demande, une image, un catalogue ou un livrable demandés pour le projet B n'atteignent jamais la commande ni les fichiers du projet A ; `projet` inconnu → 404 ; un projet aux réglages illisibles ne bloque pas l'autre. (Tâche 4 : `test_isolation_des_projets`, `test_projet_casse_n_arrete_pas_l_autre`.)
2. Images jointes hostiles : 5 images, une de 6 Mo, un GIF renommé `.png`, base64 invalide, nom `../x.png` : 400, la commande n'est pas lancée. (Tâche 3 : `test_images_refusees`.)
3. Leçon d'étage genre ou skill contenant un mot interdit écrit autrement (« Ville-Lumière » contre « ville lumiere »), ou `git pull --rebase` en conflit : arrêt, fichier de mémoire inchangé, aucun commit. (Tâche 11 : `test_mot_interdit_accents_casse`, `test_conflit_arrete_sans_commit`.)
4. Catalogue de 5 000 éléments, parties absentes, textes hostiles, capture hors des racines ; livrable `.html` : la page reste utilisable (affichage par pages de 100), les parties absentes sont masquées, le texte est littéral, l'image hors racine répond 404, le HTML est servi en bac à sable sans script. (Tâche 5 : `test_catalogue_5000`, `test_livrable_html_bac_a_sable` ; tâche 9 : test de `filtrerElements` sur 5 000.)
5. Orchestrateur arrêté : le message de l'utilisateur reste affiché avec « En attente de l'orchestrateur » ; un double clic sur « Envoyer » ne crée qu'une demande. (Tâche 3 : `test_doublon_message_ignore` ; tâche 7 : test de `ecrit`.)

---

## Étape 1 — le contrat (phase A)

### Task 1 : le relevé version 4

**Files:** Modify `bureau/releve.py`, `tests/test_releve.py`

**Interfaces:**
- Produces: `VERSIONS = (1, 2, 3, 4)` ; les contrôles des versions 2 et 3 valent aussi en 4. Constantes : `ETAPES = ("cadrage", "cahier", "decoupage", "prototype", "methode", "serie", "terminee")`, `DECISIONS_FONCTIONNALITE = ("valider_cahier", "valider_methode", "methode_a_revoir")`, `DECISIONS_PROJET = ("confirmer_genre", "session_cloud")`, `ETAGES = ("projet", "genre", "skill")`, `MOTIF_GENRE` (regex des contraintes), `MAX_FONCTIONNALITES = 100`, `MAX_MESSAGES = 1000`, `MAX_IMAGES_MESSAGE = 4`.
- Version 4, tous facultatifs (§8.1 de la spec) : `genre` (nul ou `MOTIF_GENRE`) ; `livrable` `{libelle, lien | chemin, date}` (exactement un des deux ; `lien` passe `lien_valide`) ; `fonctionnalites` (ids uniques ; `etape` ∈ `ETAPES` ; `agent_cadrage` titulaire connu ou nul ; `discussion` `{id unique dans la discussion, t, auteur: "utilisateur" | titulaire connu, texte, images?: [chemins] ≤ 4}` ; `attend_reponse` booléen ; `cahier` `{maquette: [chemins], etapes: [textes], valide_le?}` ; `methode` `{version: entier ≥ 1, lien | chemin, validee_le?}` ; `livrable` comme ci-dessus ; `catalogue` booléen ; `decisions` `[{id, genre ∈ DECISIONS_FONCTIONNALITE, texte}]`) ; `decisions_projet` `[{id, genre ∈ DECISIONS_PROJET, texte, propose?, genres_connus?, agent?}]` (`confirmer_genre` exige `propose` et `genres_connus` au `MOTIF_GENRE` ; `session_cloud` exige `agent` titulaire connu). Ids de décisions uniques dans tout le relevé. Tâche : `fonctionnalite` (id connu), `element` (texte), `modele_depart` (texte), `montee` `{de, a, raison}`. Leçon (racine et titulaire) : `etage_propose` ∈ `ETAGES`, `texte_general` (texte non vide, exigé si l'étage n'est pas `projet`), `roles` (liste de textes non vide).
- `normaliser(r)` : en version 4, `genre`, `livrable` → `None` ; `fonctionnalites`, `decisions_projet` → `[]` ; par fonctionnalité `discussion`, `decisions` → `[]`, `attend_reponse`, `catalogue` → `False`, `cahier`, `methode`, `livrable`, `agent_cadrage` → `None` ; par tâche les quatre champs → `None` ; par leçon `etage_propose` → `"projet"`, `texte_general` → `None`, `roles` → `["tous"]`. En version < 4, tous ces champs sont retirés.

- [ ] **Step 1 : tests** — `test_version_4_minimale`, `test_version_5_refusee`, `test_v3_inchange` (un relevé v3 portant des champs v4 invalides reste valide et les perd), `test_genre_motif` (`"../x"` et `"A"` refusés), `test_livrable_lien_et_chemin_refuse`, `test_fonctionnalite_etape_inconnue`, `test_fonctionnalites_ids_doubles`, `test_message_auteur_inconnu`, `test_message_cinq_images`, `test_decision_genre_inconnu`, `test_decisions_ids_doubles_entre_fonctionnalite_et_projet`, `test_confirmer_genre_sans_propose`, `test_session_cloud_agent_inconnu`, `test_tache_fonctionnalite_inconnue`, `test_lecon_genre_sans_texte_general`, `test_normaliser_v4_defauts`. Chaque message d'erreur nomme le champ.
- [ ] **Step 2–4 :** échec, coder, tous verts. **Step 5 :** commit « Relevé version 4 ».

### Task 2 : l'état version 4

**Files:** Modify `bureau/etat.py`, `tests/test_etat.py`

**Interfaces:**
- Consumes: le relevé normalisé de la tâche 1.
- Produces: `construire(...)` rend en plus `genre`, `livrable`, `fonctionnalites` (copiées ; chaque message reçoit `prenom` et `service` de son auteur, `prenom: null` pour l'utilisateur), `decisions_projet` ; chaque tâche ses quatre champs v4 ; chaque leçon ses trois champs v4. `directeur` gagne `fonctionnalites` (nombre de décisions de toutes les fonctionnalités) et `projet` (nombre de `decisions_projet`) ; `total` les ajoute. `etat["orchestrateur_actif"]` : vrai si le chef a une tâche active au statut `travail` (sa fraîcheur dit que l'orchestrateur tourne) ; faux sinon ; clé absente en version < 4.

- [ ] **Step 1 : tests** — `test_v3_etat_inchange` (champ par champ), `test_messages_prenom_service`, `test_directeur_total_v4` (1 leçon, 2 décisions de fonctionnalités, 1 décision de projet, `decisions: 1` → `total == 5`), `test_orchestrateur_actif` (chef en travail, chef sans nouvelles, pas de chef).
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « État version 4 ».

### Task 3 : les sept demandes et les images jointes

**Files:** Modify `bureau/demandes.py`, `bureau/serveur.py`, `tests/test_demandes.py`, `tests/test_serveur.py`

**Interfaces:**
- Produces: `CHAMPS` gagne `fonctionnalite: ("texte",)`, `message: ("fonctionnalite", "texte")`, `cahier: ("fonctionnalite", "verdict")`, `methode: ("fonctionnalite", "verdict")`, `genre: ("decision", "genre")`, `session_cloud: ("decision", "session")`, `retour_element: ("fonctionnalite", "element", "texte")` ; `FACULTATIFS` gagne `images` (pour `fonctionnalite`, `message`), `texte` (pour `cahier`, `methode`), `description` (pour `genre`), `etage` (pour `lecon`).
- `verifier_images(images) -> str | None` (règles des contraintes ; nom = un nom de fichier sans séparateur ni `..`, 80 caractères au plus ; `base64.b64decode(..., validate=True)` ; signatures PNG `89 50 4E 47 0D 0A 1A 0A`, JPEG `FF D8 FF`).
- `verifier(demande, r, cibles_calculees=frozenset(), elements=None)` : toutes les demandes v4 sont refusées si `r["version"] < 4`. `fonctionnalite` : texte non vide. `message` : fonctionnalité connue, texte non vide. `cahier` : `valider` exige une décision `valider_cahier` sur la fonctionnalité ; `corriger` exige un texte. `methode` : `valider` exige une décision `valider_methode` ; `garder` exige `methode_a_revoir` ; `revoir` exige l'étape `methode` ou `serie` ou une décision `methode_a_revoir`. `genre` : décision `confirmer_genre` connue, genre au motif ; un genre absent de `genres_connus` exige `description`. `session_cloud` : décision `session_cloud` connue, `session` texte non vide de 200 caractères au plus. `retour_element` : fonctionnalité connue avec `catalogue` vrai, `element` dans `elements` (ensemble des ids du catalogue ; `None` → refus « Catalogue indisponible. »), texte non vide. `lecon` : `etage` ∈ `ETAGES` ; un étage autre que `projet` exige `texte_general` sur la leçon.
- Serveur : `MAX_CORPS_DEMANDE = 28 * 1024 * 1024` pour `POST /api/demande` (4 096 inchangé pour `/api/reglages`) ; `GARDE_DOUBLON_S = 10` : une demande `fonctionnalite` ou `message` identique (hors `t`) à la précédente prise depuis moins de 10 s rend `200 {"ok": true, "doublon": true}` sans lancer la commande. `Bureau.demande` lit le catalogue pour `retour_element` (la tâche 5 fournit la lecture ; d'ici là `elements=None`).

- [ ] **Step 1 : tests** — un refus et un accepté par type et par règle ci-dessus ; `test_images_refusees` (les cinq cas du Review Focus 2) ; `test_image_jpeg_acceptee` ; `test_demandes_v4_refusees_en_v3` ; `test_commande_recoit_les_images` (la commande de test recopie l'entrée : base64 intact) ; `test_corps_28_mo` (accepté juste sous la limite, 400 au-dessus) ; `test_doublon_message_ignore` (deux envois identiques : une ligne dans le fichier de la commande).
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Demandes version 4 et images jointes ».

## Étape 2 — le bureau à plusieurs projets (phase B)

### Task 4 : plusieurs projets dans un bureau

**Files:** Modify `bureau/serveur.py`, `bureau/reglages.py`, `lancer.py` (aide), `tests/test_serveur.py` ; Create `tests/test_bureau_multi.py`

**Interfaces:**
- Produces: `reglages.lire_bureau(chemin) -> {"port": int, "projets": [{"id": str, "chemin": Path}]}` : fichier `{"port"?: 8770, "projets": [chemin | {"chemin", "id"?}]}`, chemins relatifs au fichier du bureau, 1 à 12 projets ; `id` par défaut = nom du dossier des réglages, ou de son parent si ce dossier s'appelle `.factory`, ramené à `[a-z0-9-]` (doublon → suffixe `-2`, `-3`) ; un `id` donné suit `MOTIF_GENRE` et est unique ; erreur → `ReglagesInvalides`.
- `class Projet` : tout ce que `Bureau` tient aujourd'hui pour un fichier de réglages (équipe, historiques, table et fil des prix, cache d'état, dernier relevé, verrou des demandes, garde des challenges et des doublons) et ses méthodes `reglages`, `etat`, `facturation`, `kpi`, `cibles_calculees`, `demande`. `class Bureau(ThreadingHTTPServer)` : `__init__(adresse, projets: list[tuple[str, Path]], ouvrir=None, multi=True)` ; `self.projets: dict[str, Projet]` (ordre du fichier) ; une seule `Sonde` et un seul `Lisseur` (la charge est celle de la machine), chaque mesure ajoutée à l'historique de charge de chaque projet. `creer(chemin_reglages=None, port=None, ouvrir=None, bureau=None)` ; `lancer.py serveur --bureau <fichier>` ou `--reglages <fichier>` (exclusifs ; `--reglages` → un projet d'id `projet`, `multi=False`).
- HTTP : chaque route de projet (`/api/etat`, `/api/charge`, `/api/conseil`, `/api/facturation`, `/api/kpi`, `/api/image`, `POST /api/demande`, `POST /api/reglages`) prend `?projet=<id>` ; absent → le premier projet ; inconnu → 404 `{"erreur": "Projet inconnu."}`. `GET /api/projets` → `{"multi": bool, "projets": [{"id", "nom" (le nom du relevé, sinon l'id), "attente": directeur.total, "erreur": texte | null}]}`.

- [ ] **Step 1 : tests** — `test_lire_bureau` (ids par défaut, `.factory`, doublons, id invalide, 13 projets, chemin relatif), `test_reglages_seul_inchange` (toutes les routes sans `projet`), `test_api_projets` (pastille = somme du Directeur), `test_isolation_des_projets` (demande, image, réglage de charge envoyés à B : seuls les fichiers de B bougent), `test_projet_inconnu_404`, `test_projet_casse_n_arrete_pas_l_autre`, `test_une_seule_sonde`.
- [ ] **Step 2–4 :** échec, coder, tous les tests verts (les tests serveur existants passent sans changement de fond). **Step 5 :** commit « Un bureau, plusieurs projets ».

### Task 5 : le catalogue et le dernier livrable servis

**Files:** Create `bureau/catalogue.py`, `tests/test_catalogue.py` ; Modify `bureau/serveur.py`, `tests/test_serveur.py`

**Interfaces:**
- Produces: `catalogue.declaration(regl, fonctionnalite) -> dict | None` : `regl["catalogues"][id]`, sinon la clé `catalogues` du fichier de factory désigné par `regl["orchestrateur"]` (chemin relatif aux réglages) ; forme `{fichier}` ou `{commande, dossier?}`. `catalogue.lire(regl, fonctionnalite) -> (code, objet)` : fichier relatif aux réglages, gardé en cache selon (date, taille) ; commande lancée comme celle du relevé (`releve._executer`, 10 s, sans shell), cache 30 s ; 50 Mo au plus. `catalogue.valider(c) -> (propre, avertissements)` : `elements` liste obligatoire, chaque élément `id` unique et `nom` textes, `MAX_ELEMENTS = 20000` ; tout champ facultatif de §8.3 au mauvais type est retiré et nommé dans `avertissements` ; `captures[].chemin`, `comparaisons[].reel` et `.produit` sont des chemins (une adresse est retirée avec avertissement). Réponses : 200 `{"catalogue": propre, "avertissements": [...]}`, 404 (fonctionnalité sans déclaration), 502 (commande en échec, message), 422 (fichier illisible ou `elements` invalide).
- Serveur : `GET /api/catalogue?projet=&fonctionnalite=` ; `Projet.demande` passe à `verifier` les ids du catalogue pour `retour_element`. Les images du catalogue passent par `/api/image` (racines inchangées). `GET /api/livrable?projet=&fonctionnalite=?` sert le `chemin` du livrable du projet (ou de la fonctionnalité) s'il est dans une des `livrables.racines` (nouveau réglage, relatif aux réglages) et d'extension `.png .jpg .jpeg .pdf .zip .glb .html .txt` ; `.html` et `.txt` avec `Content-Security-Policy: sandbox` et `X-Content-Type-Options: nosniff` ; `.zip`, `.glb` en pièce jointe ; sinon 404.

- [ ] **Step 1 : tests** — `test_declaration_par_reglages`, `test_declaration_par_fichier_de_factory`, `test_fichier_cache_puis_relu`, `test_commande_en_echec_502`, `test_elements_absents_422`, `test_champ_facultatif_faux_retire_et_signale`, `test_reel_adresse_retiree`, `test_catalogue_5000` (rendu en moins de 2 s), `test_retour_element_inconnu_400`, `test_livrable_hors_racine_404`, `test_livrable_html_bac_a_sable` (en-têtes exacts), `test_catalogue_autre_projet` (B ne lit jamais la déclaration de A).
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Catalogue et dernier livrable servis ».

## Étape 3 — la page (phases C et D)

### Task 6 : le sélecteur de projets et la barre

**Files:** Create `bureau/web/ui/projets.js`, `bureau/web/tests/projets.test.js` ; Modify `bureau/web/main.js`, `bureau/web/ui/barre.js`, `bureau/web/ui/actions.js`, `bureau/web/ui/facturation.js`, `bureau/web/ui/kpi.js`, `bureau/web/ui/panneaux.js`, `bureau/web/ui/texte.js`, `bureau/web/style.css`

**Interfaces:**
- Consumes: `GET /api/projets`, `?projet=` (tâche 4).
- Produces (purs, testés) : `avecProjet(url, id) -> url` (ajoute ou remplace `projet`, encodé ; `id` nul → url inchangée) ; `projetInitial(liste, memorise) -> id` (le mémorisé s'il existe encore, sinon le premier) ; `livrables(etat) -> [{libelle, url, date}]` (celui du projet et ceux des fonctionnalités, plus récent d'abord ; `lien` tel quel si `lienSur`, `chemin` → `/api/livrable?...`). Choix retenu sous la clé `localStorage` `myiafactory.projet` (lecture et écriture dans `try/catch`). **Changer de projet recharge la page** (la scène est reconstruite pour les services du nouveau projet). Toute requête de la page passe par `avecProjet` (état, charge, conseil, réglages, demandes, facturation, KPI, images).
- Barre : en mode `multi`, le nom du projet devient un `<select>` avec la pastille `attente` de chaque projet (rafraîchi avec l'état) ; boutons « + Nouvelle fonctionnalité » et « Fonctionnalités » (relevé v4 et `agir`) ; « Dernier livrable » (lien direct, ou petit menu s'il y en a plusieurs) ; un bouton du projet dans `actions` reste tel quel.

- [ ] **Step 1 : tests JS** — `avecProjet` (url sans paramètre, avec paramètre, id avec espace), `projetInitial` (mémorisé disparu), `livrables` (ordre, lien `javascript:` écarté, chemin).
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** navigateur avec deux copies de la démo dans un fichier de bureau hors dépôt : sélecteur, pastille, choix retenu au rechargement, `--reglages` sans sélecteur, console vide. **Step 6 :** commit « Sélecteur de projets ».

### Task 7 : le panneau d'une fonctionnalité et sa discussion

**Files:** Create `bureau/web/ui/fonctionnalite.js`, `bureau/web/tests/fonctionnalite.test.js` ; Modify `bureau/web/ui/panneaux.js`, `bureau/web/ui/barre.js`, `bureau/web/style.css`

**Interfaces:**
- Produces (purs, testés) : `ETAPES_PARCOURS` (`cadrage` « Cadrage », `cahier` « Cahier des charges », `decoupage` « Découpage », `prototype` « Prototype », `methode` « Méthode », `serie` « Série ») ; `bandeau(etape) -> [{libelle, courante, faite}]` (`terminee` → toutes faites) ; `demandeNouvelle(texte, images)`, `demandeMessage(fonc, texte, images)`, `demandeCahier(fonc, verdict, texte)`, `demandeMethode(fonc, verdict, texte)` (champs exacts, `images` absent si vide) ; `verifierPieces(fichiers) -> erreur | null` (règles des contraintes, sur `name`, `type`, `size`) ; `async lireImage(fichier) -> {nom, type, donnees}` ; `ecrit(fonc, etat) -> texte | null` (« <prénom de agent_cadrage> est en train d'écrire… » si `attend_reponse` et `orchestrateur_actif`, « En attente de l'orchestrateur » si `attend_reponse` sans lui, sinon `null`) ; `nouvelleApparue(avant, apres, texte) -> id | null` (fonctionnalité absente d'`avant` dont le premier message a ce texte).
- Panneau (à droite, la scène reste visible) : nom, bandeau (étape courante en gras), discussion du plus ancien au plus récent (prénom et service, images via `/api/image`, agrandies au clic), ligne `ecrit`, saisie (brouillon gardé quand l'état se rafraîchit), « Joindre une image » (vignettes avant envoi, retrait possible), « Envoyer » grisé jusqu'à la réponse ; sous la discussion : maquette, étapes numérotées, « Valider le cahier des charges » / « Demander une correction » (le texte de la saisie) si la décision `valider_cahier` existe ; lien de la méthode et « Valider la méthode » si `valider_methode` existe ; « Catalogue » si `catalogue` (ouvre la tâche 9 ; caché jusque-là). « + Nouvelle fonctionnalité » ouvre un panneau vide ; après l'envoi, la page ouvre la fonctionnalité donnée par `nouvelleApparue`. « Fonctionnalités » liste celles du projet (nom, étape, nombre de décisions).

- [ ] **Step 1 : tests JS** — `bandeau` (prototype, terminee), formes exactes des quatre demandes, `verifierPieces` (5 fichiers, 6 Mo, `.gif`), `ecrit` (trois cas), `nouvelleApparue`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** navigateur sur une copie v4 de la démo : nouvelle fonctionnalité avec image, réponse au relevé suivant, « En attente de l'orchestrateur » quand le chef est sans nouvelles, double clic → une demande, texte hostile littéral, console vide. **Step 6 :** commit « Fonctionnalité et discussion ».

### Task 8 : le Directeur enrichi et la montée de modèle

**Files:** Modify `bureau/web/ui/directeur.js`, `bureau/web/ui/detail.js`, `bureau/web/ui/actions.js`, `bureau/web/tests/actions.test.js`, `bureau/web/style.css`

**Interfaces:**
- Produces (purs, testés) : `decisionsDirecteur(etat) -> {cahiers, methodes, revoir, genres, sessions}` (chaque entrée garde sa fonctionnalité) ; `demandeLecon(lecon, verdict, etage)` (`etage` omis s'il est égal à `etage_propose`) ; `demandeGenre(decision, genre, description)` ; `demandeSession(decision, session)` ; `libelleMontee(tache) -> texte | null` (« Sonnet, monté depuis Haiku : <raison> »).
- Panneau du Directeur : nouvelles parties « Cahiers et méthodes à valider » (lien qui ouvre le panneau de la fonctionnalité), « Genres à confirmer » (genre proposé, menu des genres connus, « Nouveau genre » avec identifiant et description), « Méthode à revoir ? » (Oui → `methode` `revoir`, Non → `garder`), « Sessions cloud à créer » (texte, agent, champ « Nom de la session créée », « C'est fait »). Une leçon montre l'étage proposé et le texte général (c'est lui qui est validé mot pour mot) et un menu Projet / Genre / Skill ; Genre et Skill sont désactivés si la leçon n'a pas de `texte_general`. Le panneau d'une tâche montre `libelleMontee`.

- [ ] **Step 1 : tests JS** — `decisionsDirecteur`, `demandeLecon` (étage changé, inchangé), `demandeGenre` (nouveau avec description), `demandeSession`, `libelleMontee`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** navigateur : chaque partie vue et chaque bouton envoie la bonne demande (fichier de la commande de test), console vide. **Step 6 :** commit « Directeur : cahiers, méthodes, genres, sessions cloud ».

### Task 9 : le catalogue d'une fonctionnalité

**Files:** Create `bureau/web/ui/catalogue.js`, `bureau/web/ui/vue-de-haut.js`, `bureau/web/tests/catalogue.test.js` ; Modify `bureau/web/ui/fonctionnalite.js`, `bureau/web/ui/barre.js`, `bureau/web/style.css`

**Interfaces:**
- Consumes: `GET /api/catalogue` (tâche 5), demande `retour_element` (tâche 3).
- Produces (purs, testés) : `filtrerElements(cat, {groupe, passe, aReevaluer, doutes, etat, recherche}) -> elements` (recherche sans casse ni accents sur nom, id et note) ; `compteurs(cat, groupe) -> {total, parEtat}` ; `utilisationsKit(cat) -> Map<idKit, [idElement]>` ; `estCouleur(v) -> bool` (`#rgb`, `#rrggbb`, `rgb(...)`) ; `cadrage(elements, traces, largeur, hauteur) -> {echelle, dx, dy}` ; `demandeRetourElement(fonc, element, texte)` ; `pageDe(liste, n, taille = 100)`.
- **Avant de coder** : demander à l'utilisateur le chemin de la page de catalogue actuelle du projet pilote sur sa machine, la lire **en lecture seule** et en reprendre la disposition et le style (§6.4) ; n'en recopier dans ce dépôt ni données, ni noms, ni images, ni textes propres au projet.
- Vue : s'ouvre dans le panneau de droite, bouton « Agrandir » (plein écran, Échap pour revenir) ; page du catalogue (choix du groupe avec compteurs, vue de haut sur `<canvas>` avec couleur par état, clic → fiche, molette pour zoomer et glisser pour se déplacer ; compteurs ; demandes de modification et réponses ; passes ; « Ce que j'ai appris » ; filtres et recherche ; kit) ; fiche d'élément (tous les points de §6.4, comparaison à plusieurs angles avec barre à glisser « Produit » / « Réel » et crédit avec lien `lienSur`, « Demander à modifier » puis suivi des retours). Listes affichées par pages de 100. Une partie sans donnée n'est pas montrée.

- [ ] **Step 1 : tests JS** — `filtrerElements` (chaque filtre, recherche « eglise » trouve « Église », 5 000 éléments en moins de 50 ms), `compteurs`, `utilisationsKit`, `estCouleur`, `cadrage` (points alignés, un seul point), `demandeRetourElement`, `pageDe`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** navigateur sur un catalogue inventé de 5 000 éléments hors dépôt et sur celui de la démo : filtres, carte, comparaison, retour envoyé, texte hostile littéral, console vide ; comparer côte à côte avec la page du projet pilote. **Step 6 :** commit « Catalogue d'une fonctionnalité ».

## Étape 4 — l'orchestrateur générique (phases E et F)

### Task 10 : le fichier de factory, l'interface et le suivi générique

**Files:** Create `orchestrateur/__init__.py`, `orchestrateur/factory.py`, `orchestrateur/suivi.py`, `orchestrateur/outil.py`, `orchestrateur/interface.md`, `tests/test_orch_factory.py`, `tests/test_orch_suivi.py`

**Interfaces:**
- Produces: `factory.lire(chemin) -> dict` normalisé, `factory.FactoryInvalide`. Fichier JSON, chemins relatifs à lui : `skill` (dépôt de la skill), `genre` (nul ou `MOTIF_GENRE`), `mots_interdits` (textes), `fiches` (dossier), `controles` (fichier), `consignes` (document propre, facultatif), `reglages` (le `.factory/reglages.json` du bureau), `services` `[{id, nom}]`, `flux` `[{id, nom, role, service}]` (≥ 1 étape), `seuil_methode` (entier ≥ 1, défaut 3), `catalogues` `{id de fonctionnalité: {fichier | commande}}`, `sessions` (fichier de la table des sessions attitrées), `suivi` (défaut `suivi.json`), `pieces` (dossier des images jointes, défaut `pieces/`), `commandes` `{nom de l'interface: [argv]}`, `memoire` (dossier de mémoire, défaut `<skill>/orchestrateur/memoire` ; à ne changer que pour la démo et les tests).
- `orchestrateur/outil.py --factory <chemin> <commande>` : entrée JSON sur l'entrée standard quand la commande en prend, sortie JSON sur la sortie standard, code 0 (fait), 1 (refusé, `{"erreur": texte}`), 2 (appel invalide). `outil.py --factory F lancer <commande>` lance la commande déclarée dans `commandes` si elle existe, sinon la générique, avec la même entrée. **Commandes de cette tâche** : `releve` (relevé v4 tiré du suivi et des fiches : colonnes `cadrage`, puis le `flux`, puis `fait` terminée ; le chef porte une tâche active « Orchestration » dont `maj` est son dernier réveil ; pendant le cadrage, `agent_cadrage` porte la tâche « Cadrage : <nom> » dans la colonne `cadrage`, d'où sa bulle au Métier), `charge` (lance `lancer.py charge --reglages <reglages>` du dépôt de la skill et rend `{"feu_vert": bool, "texte"}`), `actions` (demande du bureau → ajoutée au suivi comme « en attente » et au journal `demandes.jsonl` à côté du suivi ; images décodées dans `pieces/<fonctionnalité ou nouvelle>/<date>-<nom>` et remplacées par leurs chemins ; `fonctionnalite` crée tout de suite la fonctionnalité en `cadrage` avec le message et un nom provisoire de 40 caractères ; `message` ajoute le message et met `attend_reponse`), `reveil` (note l'heure du réveil du chef), `demandes` (en attente, plus anciennes d'abord), `demande-traitee` `{id, reponse?}`, `etat` (instantané : `genre`, fonctionnalités, tâches, file, décisions, leçons, agents `{cle, role, service, modele, lieu, session?, libre}`), `fonctionnalite` `{id, nom?, etape?, agent_cadrage?, cahier?, methode?, livrable?, catalogue?}`, `message` `{fonctionnalite, auteur, texte, images?}` (remet `attend_reponse` à faux), `decision` `{action: "poser", portee: <id de fonctionnalité> | "projet", genre, texte, ...}` → `{id}` / `{action: "lever", id}`, `tache` (création sans `id`, mise à jour avec : `titre, fonctionnalite, element, role, colonne, agent, etape, modele_depart, montee, journal, bloquee, active`), `file` `{fonctionnalite, elements: [{id, nom, groupe?}]}`, `file-prendre` `{fonctionnalite}` → élément suivant ou nul, `session` `{agent, session}` (inscrit dans la table), `catalogue` `{fonctionnalite}` (catalogue générique : éléments faits du suivi avec leurs captures et passes).
- `suivi.Suivi(chemin)` : fichier JSON réécrit par remplacement atomique, verrou de fichier (`suivi.json.verrou`, 5 s) pour l'orchestrateur et la commande d'actions qui écrivent en même temps.
- `orchestrateur/interface.md` : pour chaque commande, ses arguments, son entrée, sa sortie et ses codes, avec un exemple ; c'est le contrat des adaptateurs d'un projet.

- [ ] **Step 1 : tests** — `test_factory_minimale`, `test_factory_genre_invalide`, `test_factory_flux_vide`, `test_lancer_prefere_la_commande_declaree`, `test_releve_est_un_releve_v4_valide` (passé à `bureau.releve.valider`), `test_actions_fonctionnalite_creee_avec_image` (fichier écrit, chemin au relevé), `test_actions_journal`, `test_demande_traitee`, `test_message_agent_remet_attend_reponse`, `test_decision_poser_lever`, `test_tache_creation_et_montee`, `test_file_prendre_dans_l_ordre`, `test_ecritures_concurrentes` (deux processus, aucune perte), `test_codes_de_sortie` (0, 1, 2).
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Orchestrateur : fichier de factory et suivi générique ».

### Task 11 : la mémoire à trois étages et les leçons

**Files:** Create `orchestrateur/memoire.py`, `orchestrateur/memoire/skill.md`, `orchestrateur/memoire/genres/LISEZMOI.md`, `tests/test_orch_memoire.py` ; Modify `orchestrateur/outil.py`, `orchestrateur/interface.md`

**Interfaces:**
- Format d'un fichier de mémoire : `# <titre>` ; pour un genre, puis `Domaine : …`, `Livrable : …`, `Outils : …` ; puis une section par leçon : `## <id> — <titre court>`, `Rôles : <r1>, <r2> | tous`, `Date : AAAA-MM-JJ`, puis le texte. `skill.md` commence sans leçon ; `genres/` ne contient que `LISEZMOI.md` (le format) : aucun genre n'est livré.
- Produces: `memoire.lire(dossier, genre, role) -> {"skill": [lecon], "genre": [lecon]}` (leçons dont les rôles contiennent `role` ou `tous` ; un genre nul ou absent → `[]` ; jamais un autre genre) ; `memoire.genres(dossier) -> [{id, domaine, livrable, outils}]` ; `memoire.normaliser_mot(texte)` (minuscules, sans accents, tirets et apostrophes en espaces) ; `memoire.mots_trouves(texte, mots_interdits) -> list` ; `memoire.ajouter(dossier, etage, genre, lecon, mots_interdits, git=executer_git) -> (ok, message)` : `git pull --rebase` dans le dépôt de la skill, refus si mot interdit, ajout de la section, `git add`, `git commit -m "Mémoire (<étage>) : <titre>"`, `git push` ; échec à n'importe quel pas → `git rebase --abort` si besoin, fichier remis tel qu'il était, `(False, message)`. `git` est injectable.
- Commandes : `memoire` `{role}` ; `genre` `{action: "lister"}` / `{action: "fixer", genre, description?}` (écrit le genre dans le fichier de factory ; un nouveau genre crée `genres/<id>.md` avec sa description, par `ajouter`) ; `lecon` `{action: "noter", agent, texte, tache?, etage_propose, texte_general?, roles}` (sur la fiche, « à valider ») / `{action: "appliquer", id, verdict, etage?}` (projet → fiche « validée » ; genre ou skill → `memoire.ajouter` avec `texte_general`, la leçon de la fiche passe « validée » seulement si l'ajout réussit) ; `controle` `{texte, origine}` (ligne ajoutée au registre).

- [ ] **Step 1 : tests** (dépôt git temporaire avec un dépôt nu local comme distant) — `test_lire_par_role`, `test_genre_d_un_autre_projet_jamais_lu` (deux genres : un projet du genre A lit la leçon de A et jamais celle de B), `test_genre_nul`, `test_mot_interdit_accents_casse`, `test_ajout_commit_et_push`, `test_conflit_arrete_sans_commit` (deux clones écrivent la même ligne), `test_pull_avant_ecriture` (la leçon d'un autre clone est gardée), `test_lecon_projet_sur_fiche`, `test_appliquer_genre_echec_laisse_a_valider`, `test_genre_fixer_nouveau`, `test_skill_md_sans_projet` (aucun motif d'un fichier de mots tenu hors du dépôt, si la variable `MYIAFACTORY_MOTS` le donne ; sinon le test est sauté).
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Mémoire à trois étages ».

### Task 12 : le départ d'un agent, le choix du modèle, le vérificateur d'interface

**Files:** Create `orchestrateur/depart.py`, `orchestrateur/verifier_interface.py`, `orchestrateur/modeles/fiche-agent.md`, `tests/test_orch_depart.py`, `tests/test_orch_interface.py` ; Modify `orchestrateur/outil.py`, `orchestrateur/interface.md`

**Interfaces:**
- Format d'une fiche (`modeles/fiche-agent.md`) : lignes d'en-tête `Clé :`, `Prénom :`, `Rôle :`, `Service :`, `Modèle :` (`Haiku`, `Sonnet` ou `Opus`), `Lieu :` (`local` ou `cloud`), `Session :` (cloud), `Spécialité :` ; puis le texte libre, puis `## Leçons` avec `- [à valider|validée] <id> : <texte>`.
- Produces: `depart.monter(modele) -> modele` (`Haiku` → `Sonnet` → `Opus` → `Opus` ; tout autre nom → inchangé ; jamais `Fable`) ; `depart.agent_libre(fiches, taches, role, modele=None, lieu=None) -> (cle | None, raison)` (spécialiste du rôle sans tâche active, au modèle et au lieu demandés ; aucun → raison « aucun <rôle> libre » ou « aucun agent cloud <rôle> sur <modèle> : session à créer ») ; `depart.message(factory, fiche, tache, brief, lecons_memoire) -> texte` : projet, fiche entière, leçons de genre et de skill du rôle, brief du rôle (`<fiches>/briefs/<role>.md` s'il existe), tâche, consigne de fin d'étape (résultat, leçons avec étage proposé et texte général, retours sur la factory) ; en cloud il commence par « Tu repars de zéro. ».
- Commandes : `agent-libre` `{role, modele?, lieu?}` → `{agent, raison}` ; `depart` `{agent, tache}` → `{message}`.
- `verifier_interface.py --factory <chemin> [--complet]` : lance chaque commande de l'interface par `lancer` et contrôle sa sortie contre `interface.md` (formes et codes). Sans `--complet`, seulement les commandes qui ne changent rien (`releve`, `etat`, `demandes`, `memoire`, `genre lister`, `agent-libre`, `depart`, `catalogue`) ; avec `--complet`, aussi les autres — **à lancer seulement sur une copie du projet** (il refuse si le dossier du fichier de factory est suivi par git et non marqué par un fichier `.copie-de-verification`). Sortie : une ligne par commande « ok » ou l'écart ; code 0 si tout est ok.

- [ ] **Step 1 : tests** — `test_monter`, `test_jamais_fable`, `test_agent_libre_occupe`, `test_agent_libre_cloud_manquant`, `test_message_contient_tout` (et pas les leçons d'un autre rôle), `test_message_cloud_repart_de_zero`, `test_verificateur_outils_generiques_ok` (sur un projet minimal fabriqué par le test dans un dossier temporaire marqué), `test_verificateur_signale_un_ecart` (une commande déclarée qui oublie un champ), `test_complet_refuse_hors_copie`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Départ d'un agent, choix du modèle, vérificateur d'interface ».

### Task 13 : les consignes génériques et le guide de passage

**Files:** Create `orchestrateur/consignes.md`, `orchestrateur/modeles/brief-role.md`, `orchestrateur/modeles/registre-controles.md`, `orchestrateur/modeles/factory.json`, `docs/orchestrateur.md`, `tests/test_orch_consignes.py`

**Interfaces:**
- `consignes.md` (lu au départ par une conversation orchestratrice sur Opus) : le rôle ; le parcours (§4 de la spec, chaque étape avec les commandes à appeler, les décisions à poser, ce qui fait passer à l'étape suivante, « méthode à revoir » avec le seuil et la règle des deux éléments) ; la boucle de réveil (§7.2, dans l'ordre, discussion d'abord, `reveil` à chaque tour, « En attente de : … ») ; choix de l'agent et du modèle (§4, montée notée, Fable jamais sans demande expresse, session cloud manquante → décision, agent local en attendant) ; relecture croisée (deux relecteurs à contexte neuf, aucun ne voit l'autre avant d'avoir rendu) ; mémoire (lecture au démarrage et à chaque fonctionnalité, tri des leçons, texte général sans nom propre) ; « les outils d'abord » ; commit et push à chaque étape ; **les consignes propres du projet l'emportent, et la contradiction est notée pour l'utilisateur**. Il n'appelle les outils que par `outil.py --factory <f> lancer <commande>`.
- `docs/orchestrateur.md` : le guide de passage d'un projet (fichier de factory, adaptateurs commande par commande, `verifier_interface.py`, consignes propres, liste de compatibilité tenue dans le dépôt du projet, démarrage de la conversation orchestratrice et son message de départ).
- `tests/test_orch_consignes.py` : `test_chaque_commande_documentee` (les commandes de `outil.py` et les titres de `interface.md` sont les mêmes), `test_consignes_n_appellent_que_des_commandes_connues`, `test_consignes_couvrent_le_parcours` (chaque étape de `ETAPES` et chaque genre de décision y sont nommés), `test_modele_factory_lisible` (`factory.lire` l'accepte).

- [ ] **Step 1 :** tests. **Step 2–4 :** échec, écrire, verts. **Step 5 :** relire `consignes.md` contre §4, §5, §7 de la spec, phrase par phrase. **Step 6 :** commit « Consignes de l'orchestrateur générique ».

## Étape 5 — la démo, la relecture, le vrai passage (phases F et G)

### Task 14 : la démo à deux projets, le projet neuf, la documentation, la relecture

**Files:** Create `exemples/bureau.json`, `exemples/demo-b/` (`reglages.json`, `releve.json`, `actions.py`, `images/`), `exemples/demo/catalogue-ville.json`, `exemples/demo/images/` (captures et références inventées, petites PNG faites par un script de la bibliothèque standard, `outils/images_demo.py`), `exemples/projet-neuf/` (`factory.json`, `reglages.json` dont la commande de relevé et la commande d'actions sont `outil.py`, `fiches/` avec un agent par rôle sur Haiku ou Sonnet, `controles.md`, `consignes-projet.md` vide de règles), `tests/test_demo_v4.py` ; Modify `exemples/demo/releve.json` (version 4), `exemples/demo/actions.py`, `exemples/demo/reglages.json` (`catalogues`, `livrables`), `.gitignore`, `docs/releve.md`, `docs/installation.md`, `README.md`, `docs/img/` (captures)

- Démo (§9 de la spec, tout inventé) : projet A en série avec catalogue (deux groupes, six éléments, comparaison à deux angles, un doute, un « à réévaluer », positions et une trace), une montée de modèle, un dernier livrable ; projet B (`demo-b`) avec une fonctionnalité en cadrage (discussion avec une image), un genre à confirmer, une session cloud à créer. Les deux `actions.py` jouent le projet avec des réponses fixes pour chaque demande nouvelle. `py -3.12 lancer.py serveur --bureau exemples/bureau.json`.
- [ ] **Step 1 : tests** — `test_demo_a_et_b_valides` (v4), `test_demo_parcours` (demande `fonctionnalite` → réponse de l'agent → `cahier valider` → … → `serie`, chaque effet relu au relevé), `test_demo_retour_element`, `test_projet_neuf_verificateur` (`verifier_interface.py --complet` sur une copie marquée : tout ok).
- [ ] **Step 2–4 :** échec, coder, tous les tests verts. **Step 5 :** documenter : `docs/releve.md` (version 4, demandes, images jointes, catalogue, livrable), `docs/installation.md` (« Plusieurs projets », « Nouvelle fonctionnalité », « Le catalogue », lien vers `docs/orchestrateur.md`, copier `exemples/projet-neuf/` pour démarrer) ; README (étapes cochées, captures). **Step 6 :** suivre la documentation à la lettre sur une copie de la démo ; captures refaites. **Step 7 :** `git grep` avec les motifs tenus hors du dépôt : rien d'un projet réel (code, mémoires, exemples, historique récent). **Step 8 :** relecteur indépendant (sous-agent sur Opus, jamais Fable) sur tout le projet contre la spec et le Review Focus ; corrections, chacune avec un test vu en échec ; commit « Parcours d'une tâche : démo et documentation » et push.

### Task 15 : le vrai passage de bout en bout

Pas de code prévu : la phase corrige ce que le passage révèle (chaque correction générique avec son test, dans ce dépôt).

- [ ] **Step 1 :** copier `exemples/projet-neuf/` deux fois hors du dépôt (projets P et Q, même genre inventé) et une fois en R (autre genre) ; `git init` dans chacun ; un fichier de bureau hors dépôt qui liste P, Q, R ; lancer le bureau. Pour la mémoire, un clone local du dépôt de la skill pointé par `memoire`, avec un dépôt nu local comme distant : le vrai dépôt n'est pas touché.
- [ ] **Step 2 :** donner à l'utilisateur le message qui ouvre la conversation orchestratrice de P (Opus) : « Tu es l'orchestrateur du projet dont le fichier de factory est <chemin>. Lis <skill>/orchestrateur/consignes.md, puis les consignes propres du projet, et commence la boucle de réveil. » ; l'utilisateur la crée.
- [ ] **Step 3 :** l'utilisateur clique « + Nouvelle fonctionnalité » sur P, joint une image, et mène la fonctionnalité jusqu'à « Série » : maquette, liste d'étapes, validation du cahier, découpage, prototype avec retours, validation de la méthode, série de deux éléments avec relecture croisée, catalogue. Noter chaque écart, le corriger ici.
- [ ] **Step 4 :** valider une leçon à l'étage « genre » ; ouvrir la conversation orchestratrice de Q puis de R : Q lit la leçon, R ne la lit pas (vérifier les messages de départ).
- [ ] **Step 5 :** relevés 1, 2, 3 de la démo historique et `--reglages` seul : comme avant. Tous les tests verts. Commit « Parcours d'une tâche : passage de bout en bout » et push.

## Étape 6 — le projet pilote (phases H, I, J, dans son dépôt privé)

Ces phases se font dans une conversation ouverte sur le **dépôt privé du projet pilote**, qui lit ce plan et `docs/orchestrateur.md` dans le dépôt de la skill. Rien de propre au projet pilote n'est écrit dans ce dépôt public ; une correction générique découverte là-bas est faite ici (test compris), décrite sans nom propre. Les messages de lancement sont dans la passation.

- **H — la liste de compatibilité** : relire les consignes d'orchestration actuelles du projet pilote et ses outils ; écrire dans son dépôt la liste de compatibilité (chaque mécanisme de §7.5 et tout autre comportement trouvé, l'outil qui le porte, comment le vérifier), son fichier de factory (avec ses mots interdits), ses consignes propres (son document actuel) et le plan des adaptateurs.
- **I — les adaptateurs** : un adaptateur par commande de l'interface qui appelle ses outils sans les modifier ; les champs de la version 4 dans son relevé ; les nouvelles demandes dans sa commande d'actions (images rangées et commitées) ; l'étage des leçons ; un catalogue au format de la skill produit depuis ses données, à côté de sa page actuelle. `verifier_interface.py` sans `--complet` sur le projet, avec `--complet` sur une copie marquée : tout ok.
- **J — la bascule** : le projet pilote tourne avec l'orchestrateur générique ; chaque ligne de la liste de compatibilité est cochée ; `git grep` du dépôt public avec ses mots interdits : aucun résultat. Puis, dans le dépôt public, une seule mise à jour générique du `README.md` et de la passation (« projet 3 terminé, vérifié sur le projet pilote »), sans nom.
