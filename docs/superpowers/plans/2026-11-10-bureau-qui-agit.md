# Le bureau qui agit — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Le bureau accepte un relevé version 2, transmet les gestes de l'utilisateur au projet par une commande d'actions, montre le détail des tâches (journal, images, liens, retours), une vue liste filtrée, la file, et le bureau du Directeur avec les leçons à valider.

**Architecture:** Côté serveur, `releve.py` valide la version 2, `etat.py` fait passer les nouveaux champs, un nouveau `demandes.py` vérifie et transmet les demandes, `serveur.py` gagne `POST /api/demande` et `GET /api/image`. Côté page, un nouveau `ui/actions.js` (boutons de la barre, envoi des demandes), `ui/panneaux.js` gagne les panneaux tâche / liste / Directeur, `scene/kanban.js` la file et l'estompage des post-its filtrés.

**Tech Stack:** Python 3.12 bibliothèque standard ; JavaScript en modules, three.js déjà copié ; tests `unittest` et `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-10-bureau-qui-agit-design.md` (et, pour le contexte, `2026-11-10-bureau-vivant-design.md`).

## Global Constraints

- Dépôt public, vide de tout projet : aucun nom, chemin ou fichier d'un projet réel ; aucune donnée privée.
- Python : `py -3.12`, bibliothèque standard uniquement. Tests : `py -3.12 -m unittest discover -s tests -v` et `node --test "bureau/web/tests/*.test.js"` (guillemets compris).
- Le serveur n'écoute que `127.0.0.1` et refuse tout `Host` autre que `127.0.0.1:<port>` / `localhost:<port>` (inchangé) ; `POST /api/demande` exige les mêmes en-têtes que `POST /api/reglages` (`X-Bureau: 1`, `Content-Type: application/json`).
- Relevé : `version` 1 ou 2 ; `MAX_SERVICES = 8`. Un relevé version 1 donne exactement le bureau du projet 1.
- Demandes : types exacts `bouton`, `deplacer`, `retour`, `lecon` ; verdicts exacts `valider`, `invalider` ; `retour.texte` 3 500 caractères au plus ; commande sans shell, 10 s au plus, demande JSON en UTF-8 sur l'entrée standard ; une demande à la fois.
- Liens acceptés : schémas `https`, `http`, `claude` uniquement ; ouverts dans un nouvel onglet avec `rel="noopener"`.
- Images : extensions `.png`, `.jpg`, `.jpeg` ; fichier résolu dans une des `images.racines` (relatives au dossier des réglages) ; 40 au plus par tâche.
- La scène ne montre jamais l'effet d'une demande avant le relevé qui le confirme ; après un envoi, seul un message « Demande envoyée » apparaît.
- Textes de la page en français, toujours insérés comme texte (jamais `innerHTML` avec une donnée du relevé).
- Chaque tâche : test d'abord, le voir échouer, coder, le voir passer ; cocher dans le `README.md` ; commit en français terminé par `Co-Authored-By: Claude <noreply@anthropic.com>` ; `git push`.

## Review Focus

1. `GET /api/image?chemin=../../secret.png`, chemin absolu, lien symbolique sortant de la racine, `%00` : refusés (404), rien n'est lu.
2. Une demande dont l'`id`, la colonne, la tâche ou la leçon n'existe pas dans le dernier relevé valide : 400, la commande n'est pas lancée.
3. Commande d'actions absente, qui échoue (code ≠ 0) ou qui dépasse 10 s : la page dit « Demande refusée : <message> » ; le serveur reste disponible.
4. Deux clics rapides (double envoi) : les deux demandes passent l'une après l'autre, aucune n'est perdue ni lancée en parallèle.
5. Un relevé version 2 avec des champs facultatifs de mauvais type (`journal` qui n'est pas une liste, `liens[0].url` en `javascript:`) : bandeau « Relevé invalide » qui nomme le champ, la scène garde sa dernière image.

---

### Task 1 : le relevé version 2

**Files:** Modify `bureau/releve.py`, `tests/test_releve.py`

**Interfaces:**
- `valider(r)` : `version` ∈ {1, 2} ; en version 2, vérifie les champs facultatifs de la spec §4 :
  - `actions` : liste de `{id: texte non vide unique, libelle: texte}`, plus `lien` (lien valide), `confirmer` (texte), `actif` (booléen) ;
  - `types` : `{id, nom}` ;
  - `lecons` : `{id unique, agent: clé connue, texte, tache?: texte, date?: texte, verdict_demande?: "valider"|"invalider"}` ;
  - titulaire : `prenom`, `specialite` (textes), `lecons` (`{id, texte, etat ∈ {"à valider","validée"}}`) ;
  - tâche : `type` (texte, connu de `types` si `types` est donné), `journal` (`{t, texte}`), `images` (`{chemin, legende?}`, 40 au plus), `liens` (`{libelle, url}`), `retours` (`{t, texte, reponse?}`), `bloquee` (texte).
  En version 1, ces champs sont ignorés (ni vérifiés ni gardés).
- Produces: `lien_valide(url) -> bool` (schéma `https`, `http` ou `claude`, sans espace ni caractère de contrôle) ; `normaliser(r)` met les défauts : `actions`, `types`, `lecons` → `[]` ; par tâche `journal`, `images`, `liens`, `retours` → `[]`, `type`, `bloquee` → `None` ; et retire tous ces champs en version 1.

- [ ] **Step 1 : tests** — `test_version_2_minimale_valide` ; `test_version_3_refusee` ; `test_neuf_services_refuses` (8 acceptés) ; `test_lien_javascript_refuse` (`actions[0].lien = "javascript:alert(1)"` → message qui nomme `actions`) ; `test_lien_claude_accepte` ; `test_journal_pas_liste` ; `test_lecon_agent_inconnu` ; `test_quarante_et_une_images` ; `test_type_inconnu` ; `test_version_1_ignore_les_ajouts` (relevé v1 avec `actions` invalide : valide, et `normaliser` ne garde pas `actions`).
- [ ] **Step 2 :** échec. **Step 3 :** coder. **Step 4 :** verts (tous les tests Python). **Step 5 :** commit « Relevé version 2 ».

### Task 2 : l'état version 2

**Files:** Modify `bureau/etat.py`, `bureau/equipe.py`, `tests/test_etat.py`, `tests/test_equipe.py`

**Interfaces:**
- `construire(r, eq, maintenant, fraicheur_min)` rend `"version": r["version"]`, et en plus : `actions`, `types`, `lecons` (copiés) ; chaque agent : `prenom` = celui du titulaire s'il est donné, sinon celui de l'équipe ; `specialite` (ou `None`), `lecons` (liste) ; chaque tâche : `type`, `journal` (trié du plus récent au plus ancien), `images`, `liens`, `retours`, `bloquee` ; `directeur` = `{"lecons": n, "retours": n, "bloquees": n, "total": n}` où `retours` compte les retours sans `reponse` non vide, `bloquees` les tâches dont `bloquee` est un texte non vide, et `total = lecons + retours + bloquees + decisions`.
- `Equipe.agent(cle, chef=False, prenom=None)` : avec `prenom`, ne tire pas de prénom et **n'écrit pas** ce prénom dans `equipe.json` (mais garde la couleur attribuée) ; un prénom saisi par l'utilisateur dans `equipe.json` l'emporte encore sur celui du relevé.

- [ ] **Step 1 : tests** — `test_v1_inchange` (l'état d'un relevé v1 est égal à celui d'avant la tâche, champ par champ, plus `directeur` = `{0,0,0,decisions}`) ; `test_prenom_du_releve` ; `test_prenom_utilisateur_prioritaire` ; `test_prenom_releve_non_ecrit` ; `test_directeur_total` (1 leçon, 2 retours dont 1 répondu, 1 bloquée, `decisions: 2` → `total == 5`) ; `test_journal_trie`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « État version 2 : détail des tâches, Directeur ».

### Task 3 : les demandes

**Files:** Create `bureau/demandes.py`, `tests/test_demandes.py` ; Modify `bureau/releve.py` (`_executer(cmd, cwd, entree: bytes | None = None)` : `stdin=PIPE` et écriture de `entree` quand elle est donnée, `DEVNULL` sinon), `bureau/serveur.py`, `tests/test_serveur.py`

**Interfaces:**
- `demandes.verifier(demande: dict, r: dict) -> str | None` : message d'erreur, ou `None` ; `r` est le dernier relevé **normalisé valide** (le serveur le garde : `Bureau.dernier_releve`, mis à jour par `etat()`).
  - `bouton` : `id` d'une action sans `lien` et `actif` différent de faux ;
  - `deplacer` : `tache` = id de tâche ou de `file.visibles`, `colonne` connue ;
  - `retour` : tâche connue, texte non vide après `strip`, 3 500 caractères au plus ;
  - `lecon` : id de `lecons`, verdict valide.
- `demandes.envoyer(regl: dict, demande: dict) -> tuple[bool, str]` : ajoute `t` (ISO), lance `regl["actions"]["commande"]` dans `regl["actions"].get("dossier", ".")` (relatif au dossier des réglages) avec la demande en JSON UTF-8 sur l'entrée ; `(True, "")` sur code 0 ; `(False, <première ligne de la sortie ou des erreurs, 200 caractères>)` sinon ; `(False, "La commande d'actions a dépassé 10 s.")` ; `(False, "Aucune commande d'actions dans les réglages.")`.
- Serveur : `POST /api/demande` (corps ≤ 8 192 octets) → 200 `{"ok": true}` ; 400 `{"erreur": …}` (vérification) ; 409 `{"erreur": "Relevé indisponible."}` si aucun relevé valide ; 502 `{"erreur": …}` si la commande échoue. Un verrou fait passer les demandes l'une après l'autre ; après une demande prise, le cache d'état est vidé (`_cache_etat = (0.0, e)`) pour que le relevé suivant soit relu tout de suite.
- `GET /api/etat` rend en plus `"agir": true|false` (une commande d'actions est déclarée).

- [ ] **Step 1 : tests** — `verifier` : un test par refus de la liste ci-dessus et un par cas accepté ; `envoyer` avec une commande Python de test qui recopie l'entrée dans un fichier (la demande arrive en JSON avec `t`), une qui sort en code 3 en écrivant « non » (→ `(False, "non")`), une qui dort 15 s (→ dépassement, en moins de 15 s) ; serveur : `test_demande_sans_entete` (403), `test_demande_ok`, `test_demande_inconnue` (400, la commande n'a rien écrit), `test_demandes_successives` (deux fils envoient en même temps : deux lignes dans le fichier, jamais deux commandes à la fois — la commande de test écrit « début »/« fin » et le test vérifie l'alternance).
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Demandes : du bureau au projet ».

### Task 4 : les images

**Files:** Modify `bureau/serveur.py`, `tests/test_serveur.py`

**Interfaces:**
- `GET /api/image?chemin=<chemin relatif au dossier des réglages, tel que donné dans le relevé>` : sert le fichier si son extension est autorisée et si `Path(dossier_reglages, chemin).resolve()` est dans `Path(dossier_reglages, racine).resolve()` pour une des `images.racines` ; type `image/png` ou `image/jpeg` ; en-tête `Cache-Control: max-age=300` (les images ne changent pas de nom quand elles sont refaites : ajouter `?t=` est à la charge de la page, avec la `maj` de la tâche). Sinon 404 `{"erreur": "Introuvable."}`. Sans `images` dans les réglages : 404.

- [ ] **Step 1 : tests** — servie (`.png` dans la racine) ; `../` sortant ; chemin absolu ; `.txt` dans la racine ; lien symbolique vers l'extérieur (sauter le test si la création de lien n'est pas permise sous Windows) ; `%00` ; sans réglage `images`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** commit « Images des tâches ».

### Task 5 : les boutons de la factory et l'envoi des demandes

**Files:** Create `bureau/web/ui/actions.js`, `bureau/web/tests/actions.test.js` ; Modify `bureau/web/ui/barre.js`, `bureau/web/main.js`, `bureau/web/style.css`, `bureau/web/index.html`

**Interfaces:**
- `actions.js` (pur, testé) : `boutons(etat) -> [{id, libelle, lien|null, confirmer|null, actif}]` (vide si `etat.agir` est faux, sauf les liens) ; `lienSur(url) -> bool` (même règle que `lien_valide`) ; `async envoyer(demande, fetchFn = fetch) -> {ok: boolean, message: string}` (POST `/api/demande` avec les en-têtes requis ; `message` = « Demande envoyée » ou « Demande refusée : <erreur> » ; erreur réseau → « Demande refusée : serveur injoignable »).
- `barre.js` : `majActions(etat)` dessine les boutons à droite du voyant (un lien : `<a target="_blank" rel="noopener">`, seulement si `lienSur`) ; un bouton avec `confirmer` ouvre `confirm(texte)` ; un message temporaire (4 s) sous la barre pour le résultat. Une demande en cours grise le bouton cliqué jusqu'à la réponse.

- [ ] **Step 1 : tests JS** — `boutons` sans `agir` (liens seuls) ; `lienSur("javascript:x") === false`, `lienSur("claude://claude.ai/code/x") === true` ; `envoyer` avec un faux `fetch` : en-têtes `X-Bureau: 1` et `Content-Type: application/json`, corps = la demande ; réponse 400 `{erreur:"x"}` → `{ok:false, message:"Demande refusée : x"}`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** vérifier dans le navigateur avec la démo (tâche 8 la rend agissante ; d'ici là, un relevé de démo v2 copié hors dépôt et une commande d'actions qui écrit dans un fichier) : boutons, confirmation, message, lien ouvert dans un onglet. **Step 6 :** commit « Boutons de la factory ».

### Task 6 : le panneau d'une tâche, la file, la vue liste

**Files:** Modify `bureau/web/ui/panneaux.js`, `bureau/web/scene/kanban.js`, `bureau/web/logique/plan.js` (si la file a besoin de places), `bureau/web/ui/texte.js`, `bureau/web/tests/texte.test.js`, `bureau/web/style.css`

**Interfaces:**
- `texte.js` (pur, testé) : `filtrer(taches, {enCours: boolean, type: string|null}) -> Set<id>` (en cours = `active`) ; `imagesUrl(tache) -> [{url, legende}]` (`/api/image?chemin=<encodé>&t=<maj encodée>`).
- Panneau tâche (clic sur post-it, sur un élément de la file ou une ligne de la liste) : titre, colonne, agent (prénom), étape, journal, vignettes (`loading="lazy"`, agrandies au clic dans le panneau), liens (`lienSur`), retours (texte + réponse ou « en attente de réponse »), « Faire un retour » (zone de texte, compteur jusqu'à 3 500, bouton « Envoyer » → demande `retour`), « Déplacer vers… » (liste des colonnes sauf la sienne → demande `deplacer`). Sans `etat.agir`, ni zone de retour ni menu.
- Le panneau ne se reconstruit pas pendant qu'on écrit un retour (même règle que la saisie du réglage de charge) ; le brouillon survit à un rafraîchissement d'état.
- File : les `file.visibles` sont des post-its pâles en tête de la première colonne (« + n » si `reste`) ; clic → panneau réduit (titre, « Déplacer vers… »).
- Vue liste : bouton « Toutes les tâches » dans la barre ; panneau de droite : filtres « En cours / Toutes » et un bouton par `types` ; une ligne par tâche (titre, colonne, prénom, il y a…) ; le filtre estompe sur le Kanban les post-its exclus (opacité 0,25) tant que la vue liste est ouverte.

- [ ] **Step 1 : tests JS** — `filtrer` (en cours, type, les deux) ; `imagesUrl` encode `&`, espaces et `#`.
- [ ] **Step 2–4 :** échec, coder, verts. **Step 5 :** navigateur : chaque élément ci-dessus vu sur la démo, texte hostile (`<img onerror>` dans journal, retour, légende) affiché tel quel, console vide. **Step 6 :** commit « Détail des tâches, file et vue liste ».

### Task 7 : le Directeur et les leçons

**Files:** Modify `bureau/web/ui/panneaux.js`, `bureau/web/style.css`

- La pastille au-dessus du Directeur montre `etat.directeur.total` (cachée à 0).
- Clic sur le Directeur : panneau en trois parties de la spec §3 (Leçons à valider ; Retours sans réponse ; Tâches bloquées), une partie vide est dite (« Aucune leçon à valider »). Leçon : texte, prénom de l'agent, tâche (lien vers son panneau), date, boutons **Valider** / **Invalider** (demande `lecon`) ; si `verdict_demande`, à la place : « Verdict envoyé : <valider|invalider> ».
- Carte d'un agent : spécialité, « n leçons (dont m à valider) » si `lecons` ; panneau d'un agent (clic) : ses leçons avec leur état.

- [ ] **Step 1 :** coder ; **Step 2 :** navigateur sur la démo : valider une leçon → message « Demande envoyée », puis, au relevé suivant, la leçon quitte le panneau et la pastille baisse. **Step 3 :** commit « Le Directeur et les leçons ».

### Task 8 : la démo qui agit, la documentation

**Files:** Create `exemples/demo/actions.py`, `tests/test_demo_actions.py` ; Modify `exemples/demo/releve.json` (version 2), `exemples/demo/reglages.json`, `docs/releve.md`, `docs/installation.md`, `README.md`

**Interfaces:**
- `exemples/demo/actions.py` : lit la demande sur l'entrée, l'applique à `releve.json` de son dossier (remplacement atomique) : `bouton pause|reprendre` → `factory.etat` et libellé du bouton ; `deplacer` → colonne de la tâche (un élément de la file devient une tâche active, `reste` baisse si besoin) et `maj` = maintenant ; `retour` → ajouté avec `reponse: "Bien reçu (démo)."` ; `lecon` → retirée de `lecons`, et dans `lecons` du titulaire concerné `etat: "validée"` (valider) ou retirée (invalider).
- Relevé de démo v2 : 6 services dont `facturation` ; boutons `pause` et un lien (« Documentation », vers la page GitHub du dépôt) ; `types` ; une tâche avec 3 entrées de journal, 2 images (deux petites images de démonstration à créer dans `exemples/demo/images/`, réglage `images.racines: ["images"]`), un lien ; une leçon à valider ; un retour sans réponse ; une tâche bloquée.
- `docs/releve.md` : tous les champs v2, la commande d'actions (types de demandes, codes, entrée UTF-8, recommandation des identifiants qui disent l'état voulu), les images. `docs/installation.md` : « Faire agir le bureau ». README : étapes de ce plan, cochées.

- [ ] **Step 1 : tests** — `test_demo_actions` lance le script sur une copie du dossier de démo : pause, déplacement, retour, verdict ; chaque effet relu dans le relevé ; le relevé reste valide (`releve.valider` vide).
- [ ] **Step 2–4 :** échec, coder, verts ; tous les tests (Python et JS). **Step 5 :** navigateur : suivre « Faire agir le bureau » à la lettre sur une copie de la démo, chaque geste a son effet au relevé suivant ; capture du README refaite si l'aspect a changé. **Step 6 :** vérifier par `git grep` qu'aucun nom, chemin ou fichier propre à un projet réel n'est dans le dépôt (motifs tenus hors de ce dépôt). **Step 7 :** commit « La démo agit ; documentation » et push.
