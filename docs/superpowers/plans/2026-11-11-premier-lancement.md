# Premier lancement du bureau — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** à la première ouverture du bureau après l'installation, proposer discrètement « Voir le lancement » / « Masquer » ; « Voir » joue la fausse fenêtre sombre dont les lettres tombent puis la fenêtre chute et laisse le bureau 3D.

**Architecture :** le serveur garde un drapeau « vu » (`~/MyIAFactory/lancement.json`) servi par `GET/POST /api/lancement`. La page interroge cette route en parallèle du démarrage ; seulement si elle n'est pas « vue », elle importe à la demande `ui/lancement.js` (DOM + canvas 2D), qui s'appuie sur les fonctions pures de `logique/lancement.js`.

**Tech Stack :** Python 3.12 stdlib (serveur, unittest), JS modules natifs sans dépendance (node:test), canvas 2D, CSS.

**Spec :** `docs/superpowers/specs/2026-11-11-premier-lancement-design.md`

## Global Constraints

- Une seule fois en tout : vu sur un appareil = plus jamais proposé ailleurs ; « Masquer » compte comme vu.
- Ouverture normale (vu) : aucun code de l'effet chargé (import dynamique seulement si `vu === false`), aucune attente ajoutée à `demarrer()`.
- Une erreur de lecture de `/api/lancement` vaut « vu ».
- Contenu inventé, rien de personnel ; pas de logo ni de marque ; pas de voile vert : ce sont les lettres de la fenêtre qui tombent.
- Durées : réflexion ≈ 2,2 s, frappe ≈ 2 s, pause ≈ 0,9 s, chute des lettres puis de la fenêtre ; plafond d'attente du bureau 10 s depuis « Voir ».
- Les tests n'écrivent jamais dans le dossier personnel (`creer(..., lancement=None)` → drapeau en mémoire).
- Textes en français, styles préfixés `.lancement-`.

## Review Focus

- Bureau jamais prêt (erreur de démarrage) : l'effet s'efface au plafond de 10 s, la page reste utilisable → test `phase` avec `pret=false` au-delà du plafond.
- Clic/toucher/touche pendant l'animation : passe à la fin, le DOM de l'effet est retiré → vérifié au navigateur (tâche 4).
- Fichier `lancement.json` corrompu ou illisible : traité comme « pas vu », sans exception → test Python.
- POST depuis un hôte refusé / sans `X-Bureau` : 403, drapeau inchangé → test Python.
- Téléphone (classe `mobile`) : forme étroite, colonnes gauche et droite masquées → vérifié au navigateur en 375 px.

---

### Task 1 : le drapeau côté serveur

**Files :**
- Create : `bureau/lancement.py`, `tests/test_lancement.py`
- Modify : `bureau/serveur.py` (`Bureau.__init__`, `creer`, `main`, `do_GET`, `do_POST`), `tests/test_serveur.py`

**Interfaces :**
- Produces : `lancement.Drapeau(chemin: Path | None)` avec `.vu() -> bool` et `.marquer() -> None` (écriture atomique `{"vu": true}`, comme `acces.Cles._ecrire`, verrou de thread). `Bureau.lancement : Drapeau`. `creer(..., lancement: Path | None = None)`. Routes : `GET /api/lancement` → `200 {"vu": bool}` ; `POST /api/lancement` (en-tête `X-Bureau: 1` requis, corps ignoré et vidé) → `200 {"vu": true}`, sinon `403`.

- [ ] **Step 1 : tests du drapeau** (`tests/test_lancement.py`) : `Drapeau(None)` pas vu puis vu après `marquer()` ; `Drapeau(tmp/"x"/"lancement.json")` absent → pas vu, `marquer()` crée le dossier et le fichier, un second `Drapeau` sur le même chemin → vu ; fichier contenant `{` ou `[]` ou `{"vu": "oui"}` → pas vu, sans exception.
- [ ] **Step 2 : tests serveur** (classe `TestLancement(AvecServeur)` dans `tests/test_serveur.py`) : `GET /api/lancement` → `{"vu": False}` ; `POST` sans `X-Bureau` → 403 et toujours `{"vu": False}` ; `POST` avec `self.ENT` et corps `{}` → `{"vu": True}` puis `GET` → `{"vu": True}` ; avec `Host: evil:1` → 403.
- [ ] **Step 3 : lancer, voir échouer** : `py -3.12 -m unittest tests.test_lancement tests.test_serveur -v` → erreurs d'import / 404.
- [ ] **Step 4 : écrire `bureau/lancement.py`, brancher `serveur.py`** (`Bureau.__init__(..., lancement=None)` ; `creer` le transmet dans les deux branches ; `main` passe `Path("~/MyIAFactory/lancement.json").expanduser()`). Les routes sont globales (avant la résolution de `?projet=`), permises aux écouteurs distants (la garde distante existante s'applique).
- [ ] **Step 5 : vert** : même commande → OK.

### Task 2 : la logique pure de l'effet

**Files :**
- Create : `bureau/web/logique/lancement.js`, `bureau/web/tests/lancement.test.js`

**Interfaces :**
- Produces :
  - `doitProposer(reponse) -> boolean` : vrai seulement si `reponse` est un objet avec `vu === false`.
  - `DUREES = {reflexion: 2.2, frappe: 2.0, pause: 0.9, lettres: 2.6, fenetre: 1.2, plafond: 10}` (secondes).
  - `phase(t, pret) -> {nom, avance}` : `nom` ∈ `"reflexion" | "frappe" | "pause" | "lettres" | "attente" | "fenetre" | "fin"`, `avance` ∈ [0, 1] dans la phase. Après `lettres`, `"attente"` tant que `pret` est faux et `t < plafond` ; la chute de la fenêtre démarre à `max(fin des lettres, instant où pret devient vrai)` — l'appelant passe `pret` comme l'instant (s) où le bureau est devenu prêt, ou `null`.
  - `departs(lettres, largeur, hauteur, alea) -> number[]` : un délai (s) par lettre `{x, y}` = `0.6·x/largeur + 1.2·alea() + 0.3·(1 − y/hauteur)`, borné à [0, 2.1].
  - `tomber(lettre, dt) -> lettre` : vitesse += 1400·dt (px/s²), y += vitesse·dt ; renvoie un nouvel objet.
  - `signeDeCode(alea) -> string` : un caractère de `"abcdefghijklmnopqrstuvwxyz0123456789{}[]()<>=;:"`.
  - `texteTape(message, avance) -> string` : préfixe de `message` de longueur `round(avance·longueur)`.

- [ ] **Step 1 : tests** (`node:test`) : `doitProposer({vu:false})` vrai ; `{vu:true}`, `null`, `{erreur:"x"}`, `{vu:"false"}` faux. `phase(0, null).nom === "reflexion"` ; `phase(2.3, null).nom === "frappe"` ; `phase(4.5, null).nom === "pause"` ; `phase(6, null).nom === "lettres"` ; `phase(8, null).nom === "attente"` ; `phase(8, 1).nom === "fenetre"` ; `phase(9.5, 9).nom === "fenetre"` (prêt à 9 s : la fenêtre tombe depuis 9) ; `phase(10.1, null).nom === "fenetre"` (plafond) ; `phase(20, null).nom === "fin"` ; `phase(20, 1).nom === "fin"`. `departs` : lettre en haut à gauche avec `alea=()=>0` → 0.3 ; bornes respectées avec `alea=()=>1`. `tomber({y:0,v:0}, 0.1)` → `v ≈ 140`, `y ≈ 14`. `texteTape("abcd", 0.5) === "ab"`, avance 0 → `""`, 1 → `"abcd"`. `signeDeCode(()=>0) === "a"`.
- [ ] **Step 2 : rouge** : `node --test "bureau/web/tests/lancement.test.js"` → module introuvable.
- [ ] **Step 3 : écrire `logique/lancement.js`.**
- [ ] **Step 4 : vert** : `node --test "bureau/web/tests/*.test.js"` → tout passe.

### Task 3 : la fenêtre factice, la chute, et le branchement

**Files :**
- Create : `bureau/web/ui/lancement.js`
- Modify : `bureau/web/main.js`, `bureau/web/style.css`

**Interfaces :**
- Consumes : tâche 2 (toutes les fonctions), tâche 1 (routes).
- Produces : `export function lancer({pret: Promise<void>, marquer: () => Promise<unknown>}) -> void` dans `ui/lancement.js`.

- [ ] **Step 1 : `main.js`** : `demarrer()` résout une promesse `pret` après le premier `relancer()` suivi d'une image dessinée (résolution dans `image()` au premier passage) et la rejette dans le `catch`. En parallèle, sans `await` dans le chemin de `demarrer` : `fetch("/api/lancement", {cache:"no-store"})` → `json` → si `doitProposer(r)`, `import("./ui/lancement.js").then(m => m.lancer({pret, marquer}))` ; toute erreur ignorée. `marquer = () => fetch("/api/lancement", {method:"POST", headers:{"X-Bureau":"1","Content-Type":"application/json"}, body:"{}"}).catch(()=>{})`. (Le site utilise déjà `urlProjet` pour les routes de projet ; celle-ci est globale.) `logique/lancement.js` importé statiquement : il est minuscule, seul `ui/lancement.js` est à la demande.
- [ ] **Step 2 : `ui/lancement.js`, la question** : voile `.lancement` (`position:fixed; inset:0; z-index` au-dessus de tout, fond `#141414`), deux boutons texte gris discrets « Voir le lancement » · « Masquer », focus sur le premier. « Masquer » : `marquer()`, fondu 0,3 s, retrait du DOM. « Voir » : `marquer()` sans attendre, puis la fenêtre.
- [ ] **Step 3 : la fenêtre factice** (DOM + CSS, d'après la capture décrite dans la conception) : barre de titre fine « Installer MyIAFactory sur mon projet » ; colonne gauche ≈ 215 px (Créer, Rechercher, Artéfacts, Personnalisation, Plus ; groupes « Mon atelier » / « Brouillons » de titres inventés avec pastilles bleues, l'actif surligné) ; conversation centrée ≤ 700 px (bulle « Installe MyIAFactory sur mon projet et prépare l'équipe. », réponse inventée avec gras, bulle « Ouvre le bureau. », ligne « Réflexion… », réponse tapée « Je l'ouvre. Ton monde va se construire sous tes yeux. ») ; zone de saisie arrondie en bas ; panneau droit ≈ 310 px (Environnement / MyIAFactory, Contexte / 9 %, Connecteurs / Connectés : 1). Icônes : SVG en traits simples. En `.mobile`, colonnes gauche et droite cachées. Tout `pointer-events:none` sauf le voile qui capte clic/toucher/touche pour passer.
- [ ] **Step 4 : l'animation** : boucle `requestAnimationFrame` pilotée par `phase(t, instantPret)`. `reflexion` : points animés ; `frappe` : `texteTape` ; à l'entrée de `lettres`, relever chaque caractère visible (TreeWalker sur les nœuds texte + `Range.getBoundingClientRect` par caractère, police et couleur calculées), le dessiner sur un `<canvas>` plein écran (à l'échelle `devicePixelRatio`), rendre le texte DOM transparent, et faire tomber avec `departs`/`tomber`, signes changés au hasard (`signeDeCode`, ~4 %/image) et traînée à 25 % d'opacité. `attente` : rien ne bouge. `fenetre` : la fenêtre (fond) tombe en `translateY` avec pesanteur et bascule ≤ 3° ; le voile devient transparent pour laisser voir le bureau. `fin` : tout retiré du DOM. Clic/toucher/touche : fondu 0,3 s puis retrait. `prefers-reduced-motion` : après `pause`, fondu direct.
- [ ] **Step 5 : tests node** toujours verts : `node --test "bureau/web/tests/*.test.js"`.

### Task 4 : vérification et livraison

- [ ] **Step 1 : tous les tests** : `node --test "bureau/web/tests/*.test.js"` et `py -3.12 -m unittest discover -s tests -v` → tout vert.
- [ ] **Step 2 : navigateur** (demander d'abord à l'utilisateur s'il est devant l'ordinateur) : lancer le bureau de démonstration sur un drapeau temporaire, vérifier « Masquer », « Voir » jusqu'au bureau, le passage par clic, la vue 375 px, la console sans erreur, et qu'une seconde ouverture n'affiche rien.
- [ ] **Step 3 : commit et push** : `git pull --rebase` puis `git add` des seuls fichiers de cet effet, commit, `git push` sur `main`.
