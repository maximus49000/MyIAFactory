# Page « Réglages » à trois niveaux — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** une page « Réglages » où chaque réglage du bureau se pose au niveau global, par type de projet ou par projet, avec l'origine de la valeur effective visible ; Direction et « Serveurs de travail » n'ont plus de redites.

**Architecture:** un registre déclaratif (`bureau/registre.py`) et une résolution pure projet > type > global > défaut ; le serveur du bureau publie une liste plate de lignes (`reglages_page`) et reçoit les écritures par un seul point (`POST /api/reglages/niveau`) ; la page (`bureau/web/ui/reglages.js`) est générique. Phase 1 : registre + page + déport. Phase 2 : les autres cases et le moteur.

**Tech Stack:** Python 3.12 (unittest, serveur HTTP du bureau), JavaScript ES modules sans framework (`node --test`, faux DOM `Noeud` comme `bureau/web/tests/deport.test.js`).

**Spec:** `docs/superpowers/specs/2026-11-23-page-reglages-design.md` (6 ter et 6 quater font foi sur les niveaux permis). Maquette validée dans la conversation du 2026-11-23.

## Global Constraints

- Ordre de résolution : **projet > type > global > défaut** ; origine ∈ `defaut | global | type:<genre> | projet`.
- Niveaux permis : tous (global, type, projet) pour `lecons_auto`, `analyse_blocages`, `une_session_moyenne`, `livraison_sur_demande` et les actions de déport ordinaires ; **projet seul** pour `cloud_dossier_approuve`, `livraison_github` et les actions au seul serveur (`recette-emulateur`, règle `deport.sans_poste`).
- Sans genre connu (ou hors catalogue) : le niveau « type » est sauté, le sélecteur Type est grisé, une écriture au niveau type est refusée (400).
- Valeur inapplicable à un projet (action absente de son catalogue) : refusée au niveau projet ; acceptée mais ignorée aux niveaux global et type, la ligne porte `applicable: false`.
- Après migration, chaque projet garde exactement ses valeurs actuelles (les clés à plat de `.factory/reglages.json` restent le niveau projet).
- Fichier du bureau : écriture atomique sous `verrou_fichier`, relue sous verrou (comme `fixer_agents_abonnement_max`).
- Écriture : en-tête `X-Bureau: 1` et `Content-Type: application/json` ; en cas de refus la page redit l'état réel.
- Tout texte venu du serveur passe par `textContent` ; libellés en français, sentence case.
- Tests : jamais `unittest discover`/`pytest` directs. Un module Python : `py -3.12 outils/tests_paralleles.py <module>` ; un fichier de la page : `python lancer.py tests --dossier . -- node --test bureau/web/tests/<fichier>.test.js` ; au quotidien `py -3.12 outils/tests_paralleles.py --touches`. Une seule campagne à la fois.
- Aucun appel d'IA, aucun push sans accord du Directeur.

## Review Focus

1. Fichier du bureau abîmé ou clé `types` / `reglages` mal formée : l'état d'un projet ne casse pas (valeur inconnue = défaut), rien n'est écrasé en silence.
2. Un réglage posé en global ne change **pas** un projet qui a sa valeur propre ; effacer une valeur au niveau projet redonne la valeur héritée.
3. La recette émulateur n'est jamais héritée, même si `types.<genre>.deport.lieux` ou `deport.lieux` du bureau la contient (écrit à la main).
4. Deux écritures presque simultanées sur le fichier du bureau (deux projets) : aucune n'est perdue.
5. Projet sans `factory.json` / sans genre : page utilisable au niveau Global et Projet, niveau Type grisé.

## Structure des fichiers

- Créer `bureau/registre.py` — déclarations + résolution pure (aucune E/S).
- Modifier `bureau/deport.py` — `lieu_effectif` gagne `type_`.
- Modifier `bureau/reglages.py` — lecture des clés `reglages` et `types` du fichier du bureau, écrivains de niveau.
- Modifier `bureau/serveur.py` — `Projet.genre`, `reglages_page`, `poser_reglage`, route `POST /api/reglages/niveau`, `lieux_effectifs` avec le type.
- Créer `bureau/web/ui/reglages.js` — la page. Modifier `bureau/web/ui/panneaux.js`, `directeur.js`, `deport.js`, `serveurs.js`.
- Tests : `tests/test_registre.py`, `tests/test_reglages_niveaux.py`, `tests/test_bureau_reglages_page.py` (style `tests/test_bureau_deport.py`, `AvecServeur`), `bureau/web/tests/reglages-page.test.js`.

---

## PHASE 1 — registre, page, déport

### Task 1: Registre et résolution pure

**Files:** Create `bureau/registre.py`, `tests/test_registre.py` ; Modify `bureau/deport.py:42` (`lieu_effectif`).

**Interfaces:**
- Produces :
  - `NIVEAUX = ("global", "type", "projet")`
  - `@dataclass(frozen=True) class Reglage: id: str; section: str; libelle: str; aide: str; forme: str  # "booleen" | "lieu"; niveaux: tuple[str, ...]; defaut: object; cle: str  # clé à plat du projet (« lecons_auto »)`
  - `REGISTRE: tuple[Reglage, ...]` — vide de booléens en phase 1 ; les lieux ne sont **pas** des `Reglage` mais des lignes dérivées du catalogue (voir Task 3).
  - `valeur_effective(r: Reglage, projet: dict, bureau: dict, genre: str | None) -> tuple[object, str]` — `projet` : JSON brut du projet ; `bureau` : `{"reglages": {id: v}, "types": {genre: {"reglages": {...}, "deport": {"lieux": {...}}}}, "deport": {"lieux": {...}}}` ; rend `(valeur, origine)`.
  - `lieux_effectifs(catalogue: dict, projet: dict, bureau: dict, genre: str | None) -> dict[str, tuple[str | None, str]]` — action → `(lieu, origine)`.
- Consumes : `deport.sans_poste(entree_catalogue)`.

- [ ] **Step 1: tests** dans `tests/test_registre.py` : `test_projet_l_emporte_sur_type_et_global` (projet `lecons_auto: True`, type `False`, global `False` → `(True, "projet")`) ; `test_type_l_emporte_sur_global` → origine `"type:android"` ; `test_global_puis_defaut` → `"global"` puis `(defaut, "defaut")` ; `test_niveau_non_permis_ignore` (réglage `niveaux=("projet",)`, valeur posée dans `bureau["reglages"]` → ignorée, origine `"defaut"`) ; `test_sans_genre_saute_le_type` (genre `None` avec valeur dans `types` → ignorée) ; `test_lieux_cascade` (`tests`: projet absent, type `serveur`, global `github` → `("serveur", "type:android")`) ; `test_recette_emulateur_projet_seul` (valeur au global et au type, rien au projet → `(None, "defaut")` ; au projet `serveur` → `("serveur", "projet")`) ; `test_valeur_inconnue_est_ignoree` (lieu `"mars"` au type → origine suivante).
- [ ] **Step 2:** `py -3.12 outils/tests_paralleles.py test_registre` → échec (module absent).
- [ ] **Step 3:** implémenter `registre.py` ; étendre `deport.lieu_effectif(global_, projet, action, catalogue=None, type_=None)` (le type s'insère entre projet et global ; sans `type_` le comportement est identique) et l'utiliser dans `lieux_effectifs`. Ne rien changer aux résultats existants de `tests/test_bureau_deport.py`.
- [ ] **Step 4:** `py -3.12 outils/tests_paralleles.py test_registre test_bureau_deport` → tout passe.
- [ ] **Step 5: commit** `feat(reglages): registre et résolution à trois niveaux`.

### Task 2: Stockage des niveaux global et type

**Files:** Modify `bureau/reglages.py` (`lire_bureau` l.131, nouveaux écrivains) ; Create `tests/test_reglages_niveaux.py`.

**Interfaces:**
- Consumes : `verrou_fichier`, `_fixer_plafond` (modèle d'écriture atomique).
- Produces :
  - `lire_bureau(...)` rend en plus `"reglages": dict[str, object]` et `"types": dict[str, dict]` (clés absentes → `{}`) ; une forme invalide (`reglages` pas un objet, id inconnu du `REGISTRE`, `types.<genre>` pas un objet, lieu inconnu) lève `ReglagesInvalides("Fichier du bureau : …")`.
  - `fixer_niveau_bureau(chemin_bureau: Path, chemin_cle: tuple[str, ...], valeur: object | None) -> object | None` — pose (ou, pour `None`, supprime et élague les objets vides) la valeur au chemin imbriqué, **relue sous verrou** ; ex. `("deport","lieux","tests")` (global), `("types","android","deport","lieux","tests")`, `("reglages","lecons_auto")`.
  - `effacer_cle(chemin_projet: Path, cle: str) -> dict` — retire une clé à plat du projet (atomique, comme `_ecrire_cle`), rend `charger(...)`.

- [ ] **Step 1: tests** : `test_lire_bureau_sans_nouvelles_cles` (`reglages == {}`, `types == {}`, `deport.lieux` inchangé) ; `test_lire_bureau_refuse_id_inconnu` ; `test_fixer_niveau_pose_et_efface_en_elaguant` (poser puis `None` → le fichier est revenu à l'identique, sans objets vides) ; `test_fixer_niveau_garde_le_reste` (`projets`, `port`, `agents_abonnement_max` intacts) ; `test_ecritures_concurrentes` (deux fils posent deux chemins différents 20 fois : les deux valeurs finales sont présentes) ; `test_effacer_cle_projet`.
- [ ] **Step 2:** lancer `test_reglages_niveaux` → échec.
- [ ] **Step 3:** implémenter ; extraire le corps de `_fixer_plafond` en `_modifier_bureau(chemin, fonction)` réutilisé par les deux (pas de duplication ; `tests/test_reglages.py` reste vert).
- [ ] **Step 4:** `py -3.12 outils/tests_paralleles.py test_reglages_niveaux test_reglages test_bureau_multi` → passe.
- [ ] **Step 5: commit** `feat(reglages): niveaux global et type dans le fichier du bureau`.

### Task 3: Serveur — état de la page et écriture par niveau

**Files:** Modify `bureau/serveur.py` (`Projet.lieux_globaux` l.236, `lieux_effectifs` l.262, `etat` l.318-345, `do_POST` l.2078-2164) ; Create `tests/test_bureau_reglages_page.py`.

**Interfaces:**
- Consumes : Tasks 1 et 2 ; `deport_types.catalogue_du_projet`, `deport_types.actions_exposees`.
- Produces :
  - `Projet.genre() -> str | None` (premier élément de `catalogue_du_projet`, `None` si `"generique"`).
  - `Projet.reglages_page() -> dict` publié dans l'état sous `e["reglages_page"]` (try/except : l'erreur donne `e["reglages_page_erreur"]`, jamais un état cassé) :
    `{"genre": str|None, "type_disponible": bool, "lignes": [{"id": "deport.tests" | "lecons_auto", "section": "actions" | "automatisations", "libelle": str, "aide": str, "forme": "lieu" | "booleen", "choix": ["poste","github","serveur"]?, "niveaux": [...], "valeur": ..., "origine": "defaut|global|type:<g>|projet", "valeurs": {"global"?: ..., "type"?: ..., "projet"?: ...}, "applicable": bool}]}` — une ligne `deport.<action>` par action du **catalogue du projet** ; `choix` = `catalogue[a]["lieux"]`.
  - `Projet.poser_reglage(niveau: str, id_: str, valeur: object | None) -> dict` — rend la ligne rafraîchie ; lève `ValueError` (message français) : niveau inconnu, id inconnu, niveau non permis pour cette ligne, `type` sans genre, valeur invalide (lieu hors des `choix` de l'action), action inapplicable au niveau `projet`. `valeur=None` efface. Niveau projet d'une ligne `deport.*` : réutilise la fusion existante du `POST deport` (extraire en méthode, pas de copie) ; niveau projet d'un booléen : `reglages.fixer_*` / `effacer_cle`.
  - Route `POST /api/reglages/niveau`, corps `{"niveau","id","valeur"}` → 200 avec la ligne, 400 `{"erreur": ...}` ; mêmes garde-fous d'en-têtes et de taille que `/api/reglages`. `lieux_effectifs()` et donc `reglages_deport()` (workflow GitHub) tiennent compte du niveau type.

- [ ] **Step 1: tests** (classe dérivée de `AvecServeur`, copier `poster` de `test_bureau_deport.py`) : `test_etat_publie_les_lignes_de_deport_avec_origine` ; `test_poser_global_puis_projet_l_emporte` ; `test_effacer_projet_redonne_l_herite` ; `test_type_sans_genre_refuse_400` ; `test_niveau_global_pour_recette_refuse` ; `test_lieu_hors_choix_refuse` ; `test_action_inapplicable_refusee_au_projet` ; `test_global_inapplicable_accepte_et_ignore` ; `test_fichier_du_bureau_abime_ne_casse_pas_l_etat` (état 200, `reglages_page_erreur` ou valeurs par défaut) ; `test_en_tetes_requis` (sans `X-Bureau` → 403) ; `test_type_agit_sur_le_workflow` (`reglages_deport()["deport"]["lieux"]` reflète une valeur posée au type).
- [ ] **Step 2:** lancer `test_bureau_reglages_page` → échec.
- [ ] **Step 3:** implémenter ; **ne pas changer** `POST /api/reglages` existant (les anciennes clés restent acceptées).
- [ ] **Step 4:** `py -3.12 outils/tests_paralleles.py test_bureau_reglages_page test_bureau_deport test_bureau_serveurs test_serveur` → passe.
- [ ] **Step 5: commit** `feat(bureau): état et écriture des réglages à trois niveaux`.

### Task 4: La page (module JS)

**Files:** Create `bureau/web/ui/reglages.js`, `bureau/web/tests/reglages-page.test.js`.

**Interfaces:**
- Consumes : `el` de `./dom.js`, `urlProjet` de `./projets.js`, `sectionLieux` de `./lieux.js`, `boutonDemande` de `./decisions.js`, `blocApercu`/`blocConso` de `./deport.js` (à exporter, Task 5), `sectionPartage` de `./partage.js`.
- Produces :
  - `export async function enregistrerNiveau(niveau, id, valeur, fetchFn = fetch) -> {ok, message, ligne?}` (POST `/api/reglages/niveau`, jamais ne lève).
  - `export function contenuReglages(ctx, contenu, fetchFn = fetch)` : sélecteur de niveau (`Global`, `Type : <genre>` grisé si `!type_disponible`, `Projet : <nom>`), puis sections `Où tournent les actions` (radios, + `blocApercu`/`blocConso` si une action est sur GitHub), `Automatisations`, `Agents : local ou cloud` (`sectionLieux`), `Partage des connaissances` (au niveau Global seulement, si `ctx.etat.agir`).
  - Chaque ligne : valeur du niveau édité (sinon la valeur héritée, estompée), pastille d'origine (« propre au projet », « hérité du type Android », « hérité du global », « défaut » ; aux niveaux global/type : « défini ici » / « pas défini ici »), bouton « hérité » (envoie `valeur: null`) seulement si une valeur existe à ce niveau, cadenas « Projet seulement » et contrôles désactivés quand `niveaux` n'inclut pas le niveau édité, ligne grisée « non applicable à ce projet » si `applicable === false`.
  - Un refus remet le contrôle à l'état réel et affiche le message (`aria-live="polite"`).

- [ ] **Step 1: tests** (faux DOM `Noeud`, `fetchFn` simulé) : `enregistrerNiveau_envoie_le_bon_corps_et_les_en_tetes` ; `refus_serveur_remet_l_etat_reel` ; `niveau_type_grise_sans_genre` ; `ligne_projet_seul_desactivee_au_niveau_global` ; `pastille_origine_au_niveau_projet` (trois origines) ; `bouton_herite_envoie_null_et_n_existe_que_si_defini_ici` ; `partage_seulement_au_niveau_global` ; `action_inapplicable_grisee` ; `texte_du_serveur_via_textContent` (libellé contenant `<b>` reste du texte).
- [ ] **Step 2:** `python lancer.py tests --dossier . -- node --test bureau/web/tests/reglages-page.test.js` → échec.
- [ ] **Step 3:** implémenter `reglages.js` (sans état global : l'état courant vient de `ctx.etat.reglages_page`, `ctx.rouvrir()` après un succès).
- [ ] **Step 4:** même commande → passe.
- [ ] **Step 5: commit** `feat(bureau): page Réglages (module)`.

### Task 5: Brancher la page, retirer les doublons de Direction

**Files:** Modify `bureau/web/ui/panneaux.js` (l.50 `signature`, l.222-267 `ouvrirPanneau`, `contexte` l.163), `bureau/web/ui/directeur.js` (l.308-317), `bureau/web/ui/deport.js` (exports), `bureau/web/tests/panneaux.test.js`, `bureau/web/tests/deport.test.js`, `bureau/web/style.css`.

**Interfaces:**
- Consumes : `contenuReglages` (Task 4).
- Produces : type de panneau `"reglages"` (`ouvrirPanneau("reglages", null)`), `ctx.ouvrirReglages()` ; signature = `JSON.stringify([e.reglages_page, e.deport, e.etapes_lieux, e.agir])` ; bouton « Réglages » en tête du panneau Direction ; `blocApercu(fetchFn)` et `blocConso(c)` exportés de `deport.js`.

- [ ] **Step 1: tests** : `panneaux.test.js` (style existant par index de source) vérifie le cas `type === "reglages"` ; test de `directeur.js` : le panneau Direction ne contient plus ni « Où tournent les actions » ni « Où s'exécutent les étapes », et contient un bouton « Réglages » qui appelle `ctx.ouvrirReglages`.
- [ ] **Step 2:** lancer les deux fichiers → échec.
- [ ] **Step 3:** implémenter : retirer `blocDeport(ctx)` et `sectionLieux` de `contenuDirecteur` (les **six cases restent** jusqu'à la phase 2) ; `blocDeport` et ses tests restent exportés tant que `deport.test.js` les couvre, puis sont supprimés avec leurs tests si plus aucun appel (grep avant de supprimer).
- [ ] **Step 4:** `py -3.12 outils/tests_paralleles.py --touches` → passe.
- [ ] **Step 5: commit** `feat(bureau): la page Réglages remplace le déport et les étapes dans Direction`.

### Task 5 bis: Barre du haut : heure, une seule ligne, roue crantée et menu (demande du Directeur, maquette validée le 2026-11-23)

**Files:** Modify `bureau/web/ui/barre.js` (`creerBarre`, `entete.append(...)` l.92), `bureau/web/ui/panneaux.js` (relier `ouvrirReglages`, retirer le bouton « Réglages » de Direction ajouté en Task 5 : `directeur.js:207-210`), `bureau/web/style.css` (`#barre` l.119, `.barre-actions` l.221), `bureau/web/main.js` si la barre y est montée ; Create `bureau/web/tests/barre-roue.test.js`.

**Interfaces:**
- Consumes : `ctx.ouvrirReglages` (Task 5) ; les boutons existants de la barre (`boutonNouvelle`, `boutonCorrection`, `boutonQuestion`, `boutonFonctions`, `boutonListe`, `boutonTelephone`) ; `ouvrirPanneau(type, id)` de `panneaux.js` (types `"reglages"` ; le panneau Serveurs reste monté par la carte Direction : le menu l'ouvre par `ouvrirPanneau("direction", null)` puis fait défiler jusqu'à lui).
- Produces : `export function creerMenuParametres({ouvrirReglages, ouvrirServeurs, associerTelephone, actions}) -> {racine: HTMLElement, fermer(): void}` ; `export function formaterHeure(date: Date) -> {heure: "HH:MM", date: "lun. 23 nov."}` (français, jour abrégé).

Exigences (maquette validée) :
- **Gauche** : l'heure `HH:MM` (mise à jour toutes les 15 s) avec la date en petit **en dessous** (seul bloc sur deux lignes), puis un séparateur, puis le titre et le projet, le voyant, la charge, les boutons existants.
- **Extrémité droite** : une roue crantée (`button`, `aria-label="Paramètres"`, `aria-haspopup="menu"`, `aria-expanded` vrai/faux) qui ouvre un menu `role="menu"` : « Réglages » (ouvre le panneau reglages), « Serveurs de travail », « Associer un téléphone » ; Échap et un clic ailleurs le ferment ; la roue reprend le focus à la fermeture.
- **Une seule ligne à toutes les largeurs** : `#barre` en `flex-wrap: nowrap`, jamais de retour à la ligne ; quand la place manque, dans cet ordre : les libellés des boutons deviennent des icônes avec `title`, la jauge de charge devient son pourcentage, les actions restantes (« Nouvelle fonctionnalité », « Nouvelle correction », « Une question », « Fonctionnalités », « Toutes les tâches ») passent dans un groupe « Actions » du menu. Téléphone : heure, projet, voyant et roue seulement. Le `ResizeObserver` qui pose `--hauteur-barre` reste.
- Le bouton « Réglages » du panneau Direction est retiré (l'accès passe par la roue) ; son test est adapté.

- [ ] **Step 1: tests** (faux DOM comme `bureau/web/tests/barre.test.js`) : `formaterHeure_donne_HH_MM_et_date_courte` (date fixe `new Date(2026, 10, 23, 14, 32)` → `{heure: "14:32", date: "lun. 23 nov."}`) ; `la_roue_a_les_attributs_aria_et_ouvre_le_menu` ; `le_menu_propose_les_trois_entrees_et_ferme_sur_echap` ; `choisir_reglages_appelle_ouvrirReglages_et_ferme` ; `la_barre_est_nowrap` (la feuille `style.css`, lue comme texte, déclare `flex-wrap: nowrap` pour `#barre` et aucun `flex-wrap: wrap` sur `#barre` ni sur `.barre-actions`) ; `les_actions_repliees_sont_dans_le_groupe_Actions_du_menu` ; `le_bouton_Reglages_de_Direction_a_disparu`.
- [ ] **Step 2:** `python lancer.py tests --dossier . -- node --test bureau/web/tests/barre-roue.test.js bureau/web/tests/barre.test.js bureau/web/tests/directeur-reglages.test.js` → échec.
- [ ] **Step 3:** implémenter `creerMenuParametres` et `formaterHeure` dans `bureau/web/ui/barre-parametres.js` (nouveau fichier, un rôle) ; `barre.js` ne fait que l'appeler ; resserrement par CSS (`container-query` ou `@media` sur la largeur de `#barre`) plus le repli des actions dans le menu par un `ResizeObserver` existant ; aucune largeur codée en dur sans variable CSS.
- [ ] **Step 4:** mêmes tests → passe ; puis `py -3.12 outils/tests_paralleles.py --touches` → passe.
- [ ] **Step 5: commit** `feat(bureau): barre du haut : heure, une seule ligne, roue crantée et menu`.

### Task 6: « Serveurs de travail » : aptitude des lieux en lecture seule

**Files:** Modify `bureau/web/ui/serveurs.js` (l.589-641, `choix` l.214), `bureau/web/tests/serveurs.test.js`.

**Interfaces:** Consumes `ctx.ouvrirReglages` (peut être absent : le lien n'est alors pas affiché).

- [ ] **Step 1: tests** : plus aucun `input[type=radio]` dans `.serveurs-lieux` ; titre « Aptitude des lieux » ; `AVERTISSEMENT_CONSEIL` conservé ; pastilles, « Manque : … » et `title` des raisons inchangés ; un lien « Régler dans Réglages » appelle `ctx.ouvrirReglages`.
- [ ] **Step 2:** lancer `serveurs.test.js` → échec.
- [ ] **Step 3:** implémenter (supprimer `choix`, les radios et leur écouteur ; les autres tests du fichier restent verts).
- [ ] **Step 4:** `py -3.12 outils/tests_paralleles.py --touches` → passe.
- [ ] **Step 5: commit** `feat(bureau): Serveurs de travail : aptitude des lieux en lecture seule`.

**Fin de phase 1 :** vérifier la page dans le bureau lancé (`run`), captures des trois niveaux, puis suite complète `py -3.12 outils/tests_paralleles.py`. S'arrêter ici et annoncer la phase 2.

---

## PHASE 2 — les autres réglages et le moteur

### Task 7: Déclarer les réglages à cases dans le registre

**Files:** Modify `bureau/registre.py`, `bureau/serveur.py` (`reglages_page`, `poser_reglage`), `tests/test_registre.py`, `tests/test_bureau_reglages_page.py`.

**Interfaces:** `REGISTRE` reçoit, avec `defaut` et `cle` actuels : `lecons_auto` (False), `analyse_blocages` (True), `une_session_moyenne` (False), `livraison_sur_demande` (False) — niveaux `("global","type","projet")` ; `cloud_dossier_approuve` (False), `livraison_github` (False) — `("projet",)`. Libellés et aides = ceux de `directeur.js` (`AIDE_*`) et du sujet « Livrer automatiquement sur GitHub ». `reglages_page` publie ces lignes (`section: "automatisations"`) ; `poser_reglage` les écrit : projet via les `fixer_*` existants / `effacer_cle`, global/type via `fixer_niveau_bureau(("reglages", id))` / `("types", genre, "reglages", id)`.

- [ ] **Step 1: tests** : un test paramétré par réglage (cascade complète, origine, effacement) ; `cloud_dossier_approuve` et `livraison_github` refusent global et type (400) ; `test_valeurs_actuelles_conservees` (projet avec `lecons_auto: true` à plat → `valeur True, origine "projet"` ; sans clé → défaut) ; `test_projet_garde_sa_valeur_si_global_change`.
- [ ] **Step 2–4:** échec, implémentation, `py -3.12 outils/tests_paralleles.py test_registre test_bureau_reglages_page test_reglages` → passe.
- [ ] **Step 5: commit** `feat(reglages): les réglages à cases rejoignent le registre`.

### Task 8: Le moteur et l'état lisent les valeurs effectives

**Files:** Modify `bureau/registre.py` (nouvelle `charger_effectif`), `moteur/boucle.py` (l.112-142, 557, 1465), `moteur/regles.py` (`_livraison_github` l.6268, `_livraison_sur_demande` l.6290 et les autres lectures de ces six clés — repérer par `grep "reglages_du_bureau.charger\|reglages_bureau.charger" moteur/`), `bureau/serveur.py` (l.334-345), tests `tests/test_moteur_boucle.py`, `tests/test_moteur_regles.py`, `tests/test_moteur_analyse_blocage.py`, `tests/test_publication.py`.

**Interfaces:**
- Produces : `charger_effectif(chemin_projet: Path, fichier_bureau: Path | None) -> dict` = `reglages.charger(chemin_projet)` avec, pour chaque `Reglage` du registre, la valeur effective ; `fichier_bureau=None` → comportement actuel exact. Le projet du moteur porte `projet.fichier_bureau` (renseigné par `ouvrir_projets(bureau)`, `None` pour `ouvrir_projet` seul).
- Consumes : Tasks 1, 2, 7.

- [ ] **Step 1: tests** : `charger_effectif` avec bureau (global `lecons_auto: True`, projet sans clé → `True` ; projet `False` → `False`) ; `test_sans_fichier_du_bureau_comportement_inchange` ; pour chacune des quatre lectures du moteur (`lecons_auto`, `analyse_blocages`, `livraison_sur_demande`, `une_session_moyenne`) un test qu'une valeur globale agit ; `cloud_dossier_approuve` et `livraison_github` posés au global **n'agissent pas** ; fichier du bureau illisible → le moteur retombe sur le projet seul (même repli que `except ReglagesInvalides`) ; l'état du bureau (`e["lecons_auto"]`…) publie la valeur effective.
- [ ] **Step 2:** lancer les quatre modules moteur + `test_publication` → échec.
- [ ] **Step 3:** implémenter ; remplacer chaque `reglages_*.charger(projet.fichier_reglages)[cle]` par un appel unique à `charger_effectif(projet.fichier_reglages, getattr(projet, "fichier_bureau", None))`.
- [ ] **Step 4:** `py -3.12 outils/tests_paralleles.py` (suite complète : le moteur est touché) → passe.
- [ ] **Step 5: commit** `feat(moteur): le moteur lit les réglages effectifs`.

### Task 9: Retirer les six cases de Direction

**Files:** Modify `bureau/web/ui/directeur.js` (l.56-138 : `enregistrer*`, `caseReglage`, `case*` ; l.313-316), `bureau/web/tests/lecons-auto.test.js`, `analyse-blocages.test.js`, `une-session-moyenne.test.js`, `livraison-sur-demande.test.js`, `bureau/web/ui/reglages.js`.

**Interfaces:** `enregistrerCloudDossierApprouve` reste dans `actions.js` (utilisé par `decisions.js:391`). Les constantes `AIDE_*` utilisées par la page sont lues du registre (`aide`), plus de `directeur.js`.

- [ ] **Step 1: tests** : Direction ne contient plus aucune case (« Valider les leçons automatiquement », « Analyse intelligente des blocages », …) ; « Leçons à valider » ne contient que des leçons ; la page affiche les six lignes avec cadenas pour les deux « projet seulement » ; les tests des anciens `enregistrer*` sont supprimés avec leur code **seulement après** `grep` montrant zéro appelant.
- [ ] **Step 2:** lancer `directeur`, `reglages-page` → échec.
- [ ] **Step 3:** implémenter ; mettre à jour `docs/` (`docs/deport.md` : où régler le lieu des actions ; une ligne dans le guide du bureau si présent).
- [ ] **Step 4:** `py -3.12 outils/tests_paralleles.py` (suite complète) → passe ; vérification dans le bureau lancé (`run`), captures des trois niveaux et des onglets Direction / Serveurs.
- [ ] **Step 5: commit** `feat(bureau): les réglages quittent Direction pour la page Réglages`.

---

## Auto-revue

- Couverture du design : §5.1 → T1-T3, T7 ; §5.2 → T4-T5 ; §5.3 → T5, T6, T9 ; §5.4 étapes 1 et 2 → phases 1 et 2 ; 6 bis/6 ter/6 quater → Global Constraints, T3, T7, T8 ; risques → Review Focus et tests.
- Choix de réalisation à signaler au Directeur : la section « Agents : local ou cloud » est déplacée **telle quelle** dans la page (la maquette en montrait un résumé) ; « Partage des connaissances » est seulement affiché au niveau Global (il garde son API) ; le sélecteur de niveau n'écrit jamais sur un autre projet.
