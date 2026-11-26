# Voir les actions du serveur — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** un agent serveur en cours se voit dans la fiche de sa tâche comme un agent local (dernière action, phase, liste de points, temps, coût) et la fiche de tout agent, local ou serveur, gagne un historique des appels.

**Architecture :** l'entrée du conteneur (PID 1, de confiance) publie toutes les 5 s un petit fichier `/sortie/direct.json` (actions courtes, phase, consommation, liste de points) ; le moteur le relit à chaque sonde de `_suivre` et en range une copie locale `<cle>.direct.json` dans le dossier des agents de la factory ; `detache.ajouter_au_travail` lit cette copie comme il lit le flux d'un agent local, si bien que `bureau/avancement.py` et la fiche n'ont presque rien à savoir de la différence. L'historique est ajouté une fois, dans `detache`, pour les deux sources.

**Tech Stack :** Python 3.12 (moteur, outils, entrée du conteneur), JavaScript du bureau (`bureau/web/ui`, tests `node:test`), scripts bash du serveur inchangés.

**Spec :** `docs/superpowers/specs/2026-11-26-voir-les-actions-serveur-design.md`

## Global Constraints

- Tout ce que le serveur renvoie est une **donnée non fiable** : tailles bornées, forme revalidée champ par champ, texte rendu en `textContent`, secrets masqués (`bureau/serveurs._masquer`).
- Jamais le contenu d'une commande, d'un fichier ou d'un message : seulement des actions courtes (« modifie scenes/combat.gd », « lance python »), comme `detache.derniere_action`.
- Le jeton de l'agent ne sort jamais du serveur : aucune ligne qui le contient (ni ses trois alignements base64) n'est publiée.
- Une lecture du suivi qui échoue ne change rien : la fiche garde le dernier état connu ; elle ne bloque ni la sonde, ni l'arrêt, ni le rapatriement.
- Aucun identifiant réel dans le dépôt (IP, clés, jetons) : valeurs factices dans les tests.
- Tests : toujours par le lanceur (`py -3.12 outils/tests_paralleles.py <module>`), une campagne à la fois ; les tests JS par `python lancer.py tests --dossier <d> -- node --test bureau/web/tests/<fichier>`.
- Historique : 20 dernières actions affichées par défaut, 50 gardées au plus.

## Review Focus

- Un `direct.json` absent, vide, tronqué ou de forme inattendue : la fiche ne montre rien de neuf, sans erreur ni arrêt du suivi.
- Un agent qui forge `/sortie/direct.json` (lien symbolique, gros fichier, texte énorme, champs de mauvais type) : rien n'est lu au-delà des bornes, rien n'est affiché de travers.
- Un nom de fichier ou une commande contenant le jeton : l'action n'est pas publiée.
- Le moteur qui s'arrête en plein suivi : une copie locale périmée (plus de 3 min) n'est plus montrée comme un agent au travail.
- Un lot (plusieurs tâches, une session) côté serveur : la copie locale désigne les mêmes tâches que `ajouter_au_travail` sait déjà répartir.

---

### Task 1 : Historique des appels d'un agent local

**Files :**
- Modify: `moteur/detache.py` (`derniere_action` ~204, `ajouter_au_travail` ~464)
- Test: `tests/test_moteur_detache.py`

**Interfaces :**
- Produces : `detache.historique_des_actions(lignes, dossier_projet, limite=MAX_HISTORIQUE) -> list[dict]` ; `MAX_HISTORIQUE = 50` ; chaque élément `{"t": str | None, "texte": str}` (heure ISO de la ligne du flux si connue), du plus récent au plus ancien ; `ajouter_au_travail` ajoute `"historique"` (cette liste) au dict `travail` de chaque tâche active.
- Consumes : les `lignes` déjà lues par `_lignes(flux, QUEUE_OCTETS)`.

- [ ] **Step 1 : tests** (`test_historique_des_actions_*`) : trois appels d'outils (Read, Edit, Bash `python -m x`) → `["lance python", "modifie …", "lit …"]` dans cet ordre, plus récent d'abord ; plus de 50 appels → 50 ; flux vide → `[]` ; un message texte seul n'est pas un appel ; une commande `cd x && ls` → « lance ls » (même règle que `derniere_action`) ; aucun texte ne contient le contenu d'un fichier ni la commande entière.
- [ ] **Step 2 : lancer** `py -3.12 outils/tests_paralleles.py test_moteur_detache` → les nouveaux tests échouent.
- [ ] **Step 3 : implémenter** `historique_des_actions` en extrayant de `derniere_action` le calcul du texte court d'un bloc `tool_use` dans `_action_du_bloc(bloc, dossier_projet) -> str | None` (aucun changement de comportement de `derniere_action`) ; l'heure vient de `moment_de_la_derniere_action`-style (champ `timestamp` de la ligne si présent, sinon `None`).
- [ ] **Step 4 : test d'intégration** `test_ajouter_au_travail_porte_historique` : le `travail` d'une tâche locale contient `historique` non vide.
- [ ] **Step 5 : lancer** le module → tout passe, y compris les anciens tests de `derniere_action`.
- [ ] **Step 6 : commit** « L'historique des appels d'un agent local ».

### Task 2 : L'historique dans la fiche du bureau

**Files :**
- Modify: `bureau/avancement.py` (`pour_la_tache`, `base`), `bureau/web/ui/texte.js` (`avancementEnClair`), `bureau/web/ui/detail.js` (`blocAvancement`), `bureau/web/style.css`
- Test: `tests/test_bureau_avancement.py`, `bureau/web/tests/avancement.test.js`

**Interfaces :**
- Consumes : `travail["historique"]` (Task 1).
- Produces : `pour_la_tache(...)["historique"]` : liste d'au plus 50 `{"t", "texte"}` (textes bornés à 120 caractères, éléments mal formés écartés) ; `avancementEnClair(av).historique` : même liste ; `blocAvancement` ajoute une ligne « Historique des appels » (liste, plus récent en haut, 20 visibles, bouton « Voir tout » quand il y en a plus).

- [ ] **Step 1 : tests Python** : `pour_la_tache` recopie `historique` ; un élément sans `texte` ou de mauvais type est écarté ; absent → `[]`.
- [ ] **Step 2 : tests JS** : `avancementEnClair` rend `historique` (tableau, jamais `undefined`) ; le bloc affiche 20 lignes puis, après clic sur « Voir tout », toutes ; texte inséré en `textContent` (un `<b>` dans `texte` reste du texte).
- [ ] **Step 3 : lancer** les deux (Python par le lanceur, JS par le lanceur + `node --test`) → échec.
- [ ] **Step 4 : implémenter** (`avancement.py` : `_historique(travail) -> list[dict]` ; `texte.js` ; `detail.js` ; style des lignes d'historique dans `style.css`).
- [ ] **Step 5 : lancer** → passe. **Step 6 : commit** « Historique des appels dans la fiche de tâche ».

### Task 3 : L'entrée du conteneur publie `direct.json`

**Files :**
- Modify: `serveur_ovh/images/agent/entree-agent.py` (autour de `Borne`, `lancer_claude`, `principal`, `nettoyer_sortie` : `garder`)
- Test: `tests/test_serveur_agent_script.py`

**Interfaces :**
- Produces : `resumer_flux(octets, jeton, dossier_projet=None) -> dict` : `{"v": 1, "actions": [{"t", "texte"}…≤50, plus récent d'abord], "phase": "lecture"|"modification"|"compilation"|"tests"|"autre"|None, "usage": [{"modele","entree","sortie","cache_lecture","cache_ecriture"}], "avancement": dict | None}` (mêmes règles de texte court que `detache._action_du_bloc`, dupliquées ici : l'image est autonome) ; `Borne.relire(maximum) -> bytes` (lit le fichier sans nom avec `os.pread`, sans le modifier) ; `publier_direct(c, flux, jeton)` : écrit `/sortie/direct.json` (temporaire puis `os.replace`, 0600, ≤ 64 Ko, sans suivre de lien), appelé toutes les 5 s par un fil de `lancer_claude` jusqu'à la fin de claude.
- `avancement` : lu de `<maison>/avancement.json` (écrit par l'agent), accepté seulement si ≤ 64 Ko, `points` ≤ 30 éléments `{"texte" ≤ 160, "fait": bool}`, `en_cours` ≤ 160 caractères ; sinon `None`.
- Une action dont le texte contient le jeton ou l'un de ses alignements base64 n'est pas publiée (même motifs que `motifs_jeton` de `lancer_agent.sh`).
- `principal` : `direct.json` est retiré de `/sortie` à la fin (`nettoyer_sortie` ne le garde pas).

- [ ] **Step 1 : tests** (fichier existant, qui charge l'entrée par `importlib`, l.890) : (a) `resumer_flux` sur un flux d'exemple donne actions, phase, usage ; (b) une action dont le chemin contient le jeton est absente, et `json.dumps(résultat)` ne contient pas le jeton ; (c) `avancement` trop gros / mal typé → `None` ; (d) avec le faux `claude` du fichier, `direct.json` existe pendant l'exécution (le faux `claude` attend un signal) et n'existe plus dans `/sortie` après la fin ; (e) un `direct.json` remplacé par un lien symbolique par l'agent n'est pas suivi à la publication suivante.
- [ ] **Step 2 : lancer** `py -3.12 outils/tests_paralleles.py test_serveur_agent_script` → échec.
- [ ] **Step 3 : implémenter** `Borne.relire`, `resumer_flux`, `publier_direct` et le fil dans `lancer_claude` (arrêté et joint avant `SORTIES.append(flux)`).
- [ ] **Step 4 : lancer** → passe. **Step 5 : commit** « L'entrée du conteneur publie l'activité de l'agent ».
- ⚠️ Non vérifiable ici : l'image doit être reconstruite sur le serveur (étape manuelle du Directeur, voir Task 7).

### Task 4 : Consigne d'avancement pour l'agent serveur

**Files :**
- Modify: `orchestrateur/depart.py` (`consigne_serveur`, ~443)
- Test: le test existant de `consigne_serveur` (`grep -n consigne_serveur tests/*.py`)

**Interfaces :**
- Produces : la consigne d'un agent serveur contient `regles.CONSIGNE_AVANCEMENT.format(chemin="/maison/avancement.json")` (le chemin lu par Task 3).

- [ ] **Step 1 : test** : `consigne_serveur("seul", "t1")` contient `/maison/avancement.json` ; une seule fois ; mode `pilote` aussi.
- [ ] **Step 2 : échec → Step 3 : implémenter** (importer `regles.CONSIGNE_AVANCEMENT` sans créer d'import circulaire ; sinon déplacer la constante dans `orchestrateur/depart.py` et la réimporter dans `regles`).
- [ ] **Step 4 : passe. Step 5 : commit** « L'agent serveur tient sa liste d'avancement ».

### Task 5 : Le poste lit `direct.json`

**Files :**
- Modify: `outils/serveur_agent.py` (`FICHIERS_SORTIE` l.507, nouvelle `lire_direct`)
- Test: `tests/test_serveur_agent.py`

**Interfaces :**
- Produces : `serveur_agent.lire_direct(ident, dossier, ssh) -> dict | None` : lit `direct.json` (borné à `DIRECT_MAX_OCTETS = 65536`) par `_fichier_sortie`, revalide tout (version 1 ; `actions` ≤ 50 de `{"t": str ISO ≤ 40 | None, "texte": str ≤ 120}` ; `phase` ∈ phases connues ou `None` ; `usage` ≤ 4 éléments à entiers ≥ 0 ; `avancement` : même forme que `detache.lire_avancement`) ; `None` si absent, trop gros, illisible, de forme inattendue ou si le serveur est muet. Ne lève jamais.

- [ ] **Step 1 : tests** : fichier valide → dict normalisé ; absent (code 3) → `None` ; > 64 Ko → `None` ; JSON invalide → `None` ; 60 actions → 50 ; `texte` de 500 caractères → 120 ; champ de mauvais type → écarté ; exception de ssh → `None`.
- [ ] **Step 2 : échec → Step 3 : implémenter** (ajouter `"direct.json"` à `FICHIERS_SORTIE` ; `lire_direct` n'utilise que `_fichier_sortie`).
- [ ] **Step 4 : passe. Step 5 : commit** « Lire l'activité d'un agent serveur en cours ».

### Task 6 : Le moteur recopie l'activité, `ajouter_au_travail` la montre

**Files :**
- Modify: `moteur/executeur_serveur.py` (`__init__`, `_suivre` ~481, fin de `_appeler`), `moteur/boucle.py` (~1026, `plus_ex`), `moteur/detache.py` (`ajouter_au_travail`, boucles aux l.479 et l.672, nettoyage l.698)
- Test: `tests/test_moteur_executeur_serveur.py`, `tests/test_moteur_detache.py`

**Interfaces :**
- Consumes : `serveur_agent.lire_direct` (Task 5).
- Produces : `ExecuteurServeur(..., dossier_direct=None)` ; pendant `_suivre`, à chaque tour d'état `en_cours`, `_copier_direct(sa, ident)` écrit (écriture atomique) `<dossier_direct>/<cle>.direct.json` = `{"maj": epoch, "debut": epoch, "agent": str, "dossier": str, "taches": [ids], "serveur": True, **direct}` ; un échec de lecture ne change rien ; le fichier est supprimé à la fin de l'appel (succès, échec ou arrêt). `detache.ajouter_au_travail` : pour chaque `*.direct.json` dont `maj` a moins de `DIRECT_PERIME_S = 180` s, produit le même `travail` qu'un agent local (`depuis`, `agent`, `action` = première entrée de `actions`, `action_t`, `vie_t` = `maj`, `conso` = `usage`, `phase`, `avancement`, `historique` = `actions`, plus `"serveur": True`), lots compris ; les suffixes `.direct.json` sont ignorés par les autres boucles de `Registre` et effacés par son nettoyage.

- [ ] **Step 1 : tests `executeur_serveur`** (faux `ssh`, `dormir` factice, comme les tests voisins) : (a) pendant le suivi, `<cle>.direct.json` apparaît avec les actions lues ; (b) `lire_direct` renvoie `None` → le fichier précédent reste, aucun échec ; (c) fin normale, échec et arrêt : fichier supprimé ; (d) `dossier_direct=None` : rien n'est écrit.
- [ ] **Step 2 : tests `detache`** : (a) un `.direct.json` récent donne `travail` avec `serveur: True`, `action`, `historique`, `avancement` ; (b) périmé (`maj` il y a 400 s) → aucun `travail` ; (c) un lot de 2 tâches se répartit comme un lot local (`dans_le_lot`) ; (d) `Registre` ne prend pas un `.direct.json` pour l'état d'un agent (la liste de ses agents ne change pas).
- [ ] **Step 3 : lancer** les deux modules → échec.
- [ ] **Step 4 : implémenter.** `boucle._lancer_serveur` passe `dossier_direct=detache.dossier(projet.factory.resolve().parent)` ; la factorisation de la lecture d'un « état d'agent » dans `ajouter_au_travail` est à faire pour que local et serveur partagent la construction de `info` (une fonction `_info_travail(...)`), sans changer le comportement local.
- [ ] **Step 5 : lancer** les deux modules, puis `py -3.12 outils/tests_paralleles.py --touches` → tout passe. **Step 6 : commit** « La fiche d'un agent serveur se remplit pendant son travail ».

### Task 7 : Documentation et essai réel

**Files :**
- Modify: `docs/serveur-agents.md` (« Limites connues », « Sécurité »), `docs/serveur.md` si la fiche y est décrite

- [ ] **Step 1 :** remplacer la limite « Flux et `claude.err` n'existent qu'à la fin » par la description de `direct.json` (ce qu'il contient, ses bornes, pourquoi rien de brut n'en sort, le filtre du jeton) et noter que le flux brut reste rapatrié à la fin seulement.
- [ ] **Step 2 :** campagne complète `py -3.12 outils/tests_paralleles.py` (environ 4 min) → verte.
- [ ] **Step 3 : essai réel (le Directeur, avec mon aide)** : reconstruire l'image de l'agent sur le serveur, lancer une tâche serveur, constater dans la fiche la dernière action, la liste de points et l'historique qui avancent ; vérifier qu'un `direct.json` n'existe plus dans `sortie/` après la fin. Inscrit « non vérifié sur un vrai serveur » tant que ce n'est pas fait.
- [ ] **Step 4 : commit** « Documentation du suivi en direct des agents serveur ».

---

## Hors de ce plan (à dire au Directeur)

- **Campagnes de tests et builds déportés** (but 3 de la conception) : l'index des tâches serveur ne les connaît pas (`TYPES = ("emulation",)` + agents) ; leur fiche exige d'abord de les y inscrire. À traiter dans un second plan, avec la zone « Serveur » de la scène.
- **Coût en direct d'un agent serveur** : la copie locale porte déjà `conso` (= `usage`) ; si `conso_en_cours` n'est pas lue pour les agents serveur par la fiche de coût, un petit ajout suit après l'essai réel.
