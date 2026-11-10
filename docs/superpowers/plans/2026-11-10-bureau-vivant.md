# Le bureau vivant — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** une page web locale qui montre une factory d'agents IA comme un open space 3D isométrique vivant, alimentée par un relevé que n'importe quel projet peut fournir, avec la charge de l'ordinateur.

**Architecture:** un projet fournit un *relevé* (faits bruts, JSON). Le serveur Python du bureau le lit, y ajoute prénoms, statuts (au travail / sans nouvelles / libre) et charge machine, et sert un *état* à la page. La page (three.js) compare les états successifs, en déduit les déplacements, et les joue. La logique est en fonctions pures, testées sans navigateur ; le rendu 3D ne fait qu'afficher.

**Tech Stack:** Python 3.12, bibliothèque standard uniquement (`http.server`, `ctypes`, `unittest`). JavaScript en modules ES sans étape de build, three.js 0.170.0 copié en local, tests avec `node --test` (Node 24).

**Spec:** `docs/superpowers/specs/2026-11-10-bureau-vivant-design.md`

## Global Constraints

- Ce dépôt est public et **vide de tout projet** : aucun nom de fichier, chemin, adaptateur ou réglage d'un projet réel ; aucune clé, jeton ou adresse de session. Les exemples sont inventés.
- Python : lancer avec `py -3.12` (le `py` par défaut de la machine est un 3.9). Aucun paquet à installer, ni Python ni npm.
- Le serveur n'écoute que sur `127.0.0.1`. Port par défaut : `8770`.
- Tout texte visible par l'utilisateur est en français. Les textes venus du relevé sont affichés comme du texte (`textContent`), jamais comme du HTML.
- Noms de code en français sans accents (`charger`, `releve`, `titulaire`).
- Rien n'est simulé : aucune donnée inventée par le bureau n'est affichée comme un fait. L'exemple de démonstration est un relevé-fichier, clairement nommé « Démo ».
- Tests Python : `py -3.12 -m unittest discover -s tests -v` depuis la racine. Tests JS : `node --test bureau/web/tests/`.
- Après chaque tâche : cocher la ligne correspondante dans la section « Avancement » du `README.md`, commit, `git push`. Message de commit en français, terminé par `Co-Authored-By: Claude <noreply@anthropic.com>`.
- Tripo : prompt ≤ 1000 caractères espaces compris, toujours accompagné de tous les réglages ; une génération à la fois ; c'est l'utilisateur qui génère.
- Téléchargement de three.js : demander l'accord de l'utilisateur avant (tâche 8).

## Review Focus

1. **Relevé illisible** (fichier absent, JSON tronqué en cours d'écriture, commande qui échoue ou dépasse 10 s) : le serveur répond quand même, avec `erreur` renseigné ; la page garde la dernière scène et affiche un bandeau. Test en tâche 5 et tâche 7.
2. **Dates hétérogènes** (`maj` sans fuseau, avec `+00:00`, absente, ou illisible) : jamais de plantage ; une date sans fuseau est une heure locale ; une date absente ou illisible vaut « très ancienne ». Test en tâche 3.
3. **Rafale de changements** (20 tâches changent de colonne entre deux lectures, par exemple après une mise en veille) : six missions au plus en file, les autres post-its sont posés directement. Test en tâche 7.
4. **Plus d'agents que de postes** dans un service (9 agents cloud dans un bureau de 4 postes) : chacun reçoit une place distincte, personne ne se superpose. Test en tâche 7.
5. **Textes hostiles ou longs** venus du relevé (`<img onerror=…>`, titre de 300 caractères) : affichés tels quels comme texte, tronqués avec « … ». Test en tâche 9.

## Les fichiers

```
lancer.py                       point d'entrée : py -3.12 lancer.py serveur|charge --reglages <chemin>
bureau/
  reglages.py                   lire / écrire les réglages d'un projet
  releve.py                     valider un relevé, l'obtenir (fichier ou commande)
  equipe.py                     clé de titulaire -> prénom, couleur ; persistance
  statuts.py                    dates, fraîcheur, pause, départ, bulles
  etat.py                       relevé + équipe + horloge -> état servi à la page
  charge.py                     mesure, lissage, historique, conseil, feu vert
  serveur.py                    HTTP : page, /api/etat, /api/charge, /api/conseil, /api/reglages
  web/
    index.html  style.css  main.js
    logique/diff.js             changements de colonne entre deux états
    logique/plan.js             plan de l'open space, places, chemins
    logique/regie.js            qui va où, file au Kanban, avance dans le temps
    scene/scene.js              three.js : caméra, lumière, pièces
    scene/personnages.js        personnages et animations
    scene/kanban.js             tableau et post-its
    scene/modeles.js            chargement GLB avec repli sur volumes simples
    ui/barre.js                 voyant + barre de charge
    ui/panneaux.js              cartes, panneau de service, réglage de charge
    modeles/manifeste.json      quel GLB pour quel objet
    vendor/                     three.js 0.170.0
    tests/*.test.js
tests/test_*.py
exemples/demo/                  reglages.json + releve.json inventés
docs/installation.md  docs/releve.md
```

## Les deux formats

**Le relevé** (fourni par le projet ; documenté dans `docs/releve.md`, tâche 2) :

```json
{
  "version": 1,
  "projet": "Démo",
  "factory": {"etat": "en marche", "depuis": "2026-11-10T09:00:00"},
  "services": [{"id": "dev", "nom": "Dev"}],
  "colonnes": [{"id": "afaire", "nom": "À faire"}],
  "titulaires": [{"cle": "dev:1", "service": "dev", "lieu": "local",
                  "modele": "Sonnet", "permanent": false, "chef": false, "fraicheur_min": 30}],
  "taches": [{"id": "t1", "titre": "…", "colonne": "afaire", "active": true,
              "titulaire": "dev:1", "etape": "…", "maj": "2026-11-10T09:12:00", "postit": true}],
  "file": {"visibles": [{"id": "q1", "titre": "…"}], "reste": 0},
  "decisions": 0
}
```

Obligatoires : `version`, `projet`, `factory.etat` (`"en marche"` ou `"en pause"`), `services`, `colonnes`, `titulaires` (`cle`, `lieu` parmi `local`/`cloud`, et `service` sauf pour le chef), `taches` (`id`, `titre`, `colonne`, `active`). Le reste est facultatif : `titulaire` nul, `postit` vrai par défaut, `file` vide, `decisions` 0, `modele` `"?"`. Un seul titulaire peut avoir `chef: true` ; s'il n'y en a aucun, le bureau en ajoute un de clé `"chef"`. Au plus 6 services.

**L'état** (servi par `/api/etat`) : le relevé, où `titulaires` est remplacé par `agents` et complété :

```json
{
  "version": 1, "horodatage": "…", "projet": "Démo", "erreur": null,
  "factory": {"etat": "en marche", "depuis": "…", "derniere_activite": "…", "inactive": false},
  "services": [], "colonnes": [], "file": {"visibles": [], "reste": 0}, "decisions": 0,
  "agents": [{"id": "dev:1", "prenom": "Hugo", "service": "dev", "lieu": "local", "modele": "Sonnet",
              "couleur": "#2f6fd0", "chef": false, "statut": "travail",
              "bulle": "Écran d'accueil", "taches": ["t1"]}],
  "taches": [{"id": "t1", "titre": "…", "colonne": "afaire", "agent": "dev:1",
              "etape": "…", "maj": "…", "postit": true}]
}
```

`statut` vaut `travail`, `sans_nouvelles` ou `libre`. Les agents partis (§5.3 de la spec) ne figurent pas dans `agents` ; une tâche dont l'agent est parti a `agent: null`.

---

### Task 1: Socle et réglages

**Files:**
- Create: `lancer.py`, `bureau/__init__.py`, `bureau/reglages.py`, `tests/__init__.py`, `tests/test_reglages.py`
- Modify: `README.md`, `.gitignore`

**Interfaces:**
- Produces:
  - `reglages.DEFAUTS: dict` = `{"port": 8770, "charge_max": 75, "fraicheur_min": 30, "releve": {}}`
  - `reglages.charger(chemin: Path) -> dict` — défauts complétés par le fichier ; fichier absent → défauts ; JSON invalide → `reglages.ReglagesInvalides(str)`. Ajoute la clé `"dossier"` = dossier du fichier (chaîne), non enregistrée.
  - `reglages.fixer_charge_max(chemin: Path, valeur: int) -> dict` — accepte 30 à 95 inclus, sinon `ValueError` ; écrit le fichier par fichier temporaire puis `os.replace` ; conserve les autres clés.
  - `releve` dans les réglages : `{"fichier": "chemin"}` ou `{"commande": ["…"], "dossier": "chemin"}` ; chemins relatifs résolus depuis le dossier du fichier de réglages.
  - `lancer.py` : ajoute son dossier à `sys.path` puis appelle `bureau.serveur.main(argv)` ; sous-commandes `serveur` et `charge`, option `--reglages <chemin>` obligatoire.

- [ ] **Step 1: Écrire les tests**

```python
class TestReglages(unittest.TestCase):
    def test_fichier_absent_donne_les_defauts(self):
        r = reglages.charger(self.tmp / "absent.json")
        self.assertEqual((r["port"], r["charge_max"], r["fraicheur_min"]), (8770, 75, 30))
    def test_le_fichier_complete_les_defauts(self):
        (self.tmp / "r.json").write_text('{"charge_max": 60}', encoding="utf-8")
        r = reglages.charger(self.tmp / "r.json")
        self.assertEqual((r["charge_max"], r["port"]), (60, 8770))
        self.assertEqual(r["dossier"], str(self.tmp))
    def test_json_invalide(self):
        (self.tmp / "r.json").write_text("{", encoding="utf-8")
        with self.assertRaises(reglages.ReglagesInvalides): reglages.charger(self.tmp / "r.json")
    def test_fixer_charge_max_conserve_le_reste(self):
        (self.tmp / "r.json").write_text('{"port": 9000}', encoding="utf-8")
        reglages.fixer_charge_max(self.tmp / "r.json", 65)
        d = json.loads((self.tmp / "r.json").read_text(encoding="utf-8"))
        self.assertEqual(d, {"port": 9000, "charge_max": 65})
    def test_fixer_charge_max_refuse_hors_bornes(self):
        for v in (29, 96, "70", 70.5):
            with self.assertRaises(ValueError): reglages.fixer_charge_max(self.tmp / "r.json", v)
```

- [ ] **Step 2: Lancer, vérifier l'échec** — `py -3.12 -m unittest discover -s tests -v` → erreur d'import de `bureau.reglages`.
- [ ] **Step 3: Écrire `bureau/reglages.py` et `lancer.py`** (`lancer.py` peut répondre « pas encore disponible » pour les sous-commandes tant que le serveur n'existe pas).
- [ ] **Step 4: Relancer** → 5 tests passent.
- [ ] **Step 5: README et .gitignore** — ajouter au `.gitignore` : `.factory/`, `node_modules/`. Remplacer le `README.md` par : ce qu'est MyIAFactory (3 phrases), « Comment ça marche » (le schéma relevé → serveur → page, 6 lignes), « Avancement » avec une case par tâche de ce plan (toutes vides sauf la 1), « Ce qu'il reste à faire » (les projets 2, 3, 4 de la spec, une ligne chacun), liens vers la spec, ce plan, `docs/installation.md` et `docs/releve.md` (à venir).
- [ ] **Step 6: Commit et push.**

### Task 2: Le relevé

**Files:**
- Create: `bureau/releve.py`, `tests/test_releve.py`, `docs/releve.md`, `exemples/demo/releve.json`, `exemples/demo/reglages.json`

**Interfaces:**
- Consumes: `reglages.charger`.
- Produces:
  - `releve.valider(r: dict) -> list[str]` — liste de messages en français, vide si valide. Vérifie la section « Les deux formats » : champs obligatoires, valeurs permises, au plus 6 services, identifiants uniques (services, colonnes, titulaires, tâches), `colonne` de chaque tâche connue, `titulaire` connu ou nul, `service` de chaque titulaire connu (sauf chef), au plus un chef.
  - `releve.normaliser(r: dict) -> dict` — applique les valeurs par défaut des champs facultatifs et ajoute le chef `{"cle": "chef", "lieu": "local", "chef": True, "permanent": True}` s'il manque. Ne modifie pas son argument.
  - `releve.obtenir(regl: dict) -> tuple[dict | None, str | None]` — `(relevé normalisé, None)` ou `(None, message)`. Source `fichier` : lecture UTF-8. Source `commande` : `subprocess.run` dans `dossier`, sortie standard en UTF-8, délai 10 s, sans shell. Aucune source configurée → `(None, "Aucun relevé configuré…")`. Jamais d'exception.
- `docs/releve.md` : le contrat pour un projet — les deux façons de fournir le relevé, chaque champ (obligatoire ou non, valeurs), ce que le bureau en déduit, un exemple complet, et la règle « n'écrivez le fichier que par remplacement atomique ».
- `exemples/demo/releve.json` : projet « Démo », 5 services (`metier`, `dev`, `qa`, `integration`, `facturation`), 5 colonnes (`afaire` À faire, `encours` En cours, `revue` Relecture, `fait` Fait, `bloque` Bloqué), 7 titulaires dont le chef, 2 cloud, 1 permanent, 9 tâches dont 4 actives et 1 sans post-it, une file de 3 + reste 5, 2 décisions. Les `maj` de la démo sont fixes : la démo montre donc honnêtement « sans nouvelles » tant qu'on n'édite pas le fichier (le dire dans `docs/installation.md`, tâche 10).
- `exemples/demo/reglages.json` : `{"releve": {"fichier": "releve.json"}}`.

- [ ] **Step 1: Écrire les tests**

```python
BASE = {"version": 1, "projet": "P", "factory": {"etat": "en marche"},
        "services": [{"id": "dev", "nom": "Dev"}], "colonnes": [{"id": "a", "nom": "A"}],
        "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}],
        "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"}]}

def test_base_valide(self): self.assertEqual(releve.valider(BASE), [])
def test_erreurs(self):
    cas = [("colonne inconnue", lambda r: r["taches"][0].update(colonne="z")),
           ("titulaire inconnu", lambda r: r["taches"][0].update(titulaire="x")),
           ("etat factory", lambda r: r["factory"].update(etat="arrêt")),
           ("lieu", lambda r: r["titulaires"][0].update(lieu="lune")),
           ("service inconnu", lambda r: r["titulaires"][0].update(service="rh")),
           ("doublon", lambda r: r["taches"].append(dict(r["taches"][0]))),
           ("7 services", lambda r: r.update(services=[{"id": str(i), "nom": "S"} for i in range(7)])),
           ("deux chefs", lambda r: r["titulaires"].extend([{"cle": "c1", "lieu": "local", "chef": True}, {"cle": "c2", "lieu": "local", "chef": True}])),
           ("champ manquant", lambda r: r.pop("colonnes"))]
    for nom, casser in cas:
        r = copy.deepcopy(BASE); casser(r)
        self.assertTrue(releve.valider(r), nom)
def test_valider_ne_plante_pas_sur_n_importe_quoi(self):
    for r in (None, [], "x", {"taches": 3}, {"version": 1, "taches": [None]}):
        self.assertTrue(releve.valider(r))
def test_normaliser_ajoute_chef_et_defauts(self):
    n = releve.normaliser(BASE)
    self.assertIn("chef", [t["cle"] for t in n["titulaires"]])
    self.assertEqual((n["taches"][0]["postit"], n["file"], n["decisions"]), (True, {"visibles": [], "reste": 0}, 0))
    self.assertNotIn("file", BASE)
def test_obtenir_fichier(self):        # relevé valide écrit dans tmp -> (dict, None)
def test_obtenir_fichier_absent(self): # -> (None, message non vide)
def test_obtenir_json_tronque(self):   # fichier '{"version": 1, "ta' -> (None, message)
def test_obtenir_invalide(self):       # JSON correct mais colonne inconnue -> (None, message citant l'erreur)
def test_obtenir_commande(self):       # commande [sys.executable, "-c", "print(<json>)"] -> (dict, None)
def test_obtenir_commande_en_echec(self):  # code de retour 1 -> (None, message)
def test_obtenir_sans_source(self):    # releve {} -> (None, message)
def test_exemple_demo_valide(self):    # exemples/demo/releve.json passe valider() sans erreur
```

- [ ] **Step 2: Lancer, vérifier l'échec.**
- [ ] **Step 3: Écrire `bureau/releve.py`, l'exemple de démonstration et `docs/releve.md`.**
- [ ] **Step 4: Relancer** → tout passe.
- [ ] **Step 5: Commit et push.**

### Task 3: Statuts — dates, fraîcheur, pause, départ

**Files:**
- Create: `bureau/statuts.py`, `tests/test_statuts.py`

**Interfaces:**
- Produces (tous les `datetime` sont avec fuseau) :
  - `statuts.lire_date(texte) -> datetime` — ISO 8601 ; sans fuseau = heure locale ; `None`, vide ou illisible → `statuts.TRES_ANCIEN` (`datetime(1970, 1, 1, tzinfo=timezone.utc)`).
  - `statuts.duree_en_clair(minutes: float) -> str` — `"45 min"` sous 60 min, `"2 h"` sous 48 h, `"3 j"` au-delà (arrondi inférieur).
  - `statuts.statut(taches: list[dict], maintenant, fraicheur_min: int, en_pause: bool) -> dict` — `taches` = celles du titulaire. Retourne `{"statut", "bulle"}`.
    - une tâche active et fraîche → `travail`, bulle = titre de la plus récemment mise à jour, tronqué à 40 caractères avec « … », suivi de ` (+N)` s'il y a N autres tâches actives ;
    - tâches actives mais toutes périmées, factory en marche → `sans_nouvelles`, bulle `"sans nouvelles depuis " + duree_en_clair(...)` (depuis la plus récente) ; si la date est `TRES_ANCIEN`, bulle `"sans nouvelles"` ;
    - tâches actives toutes périmées, factory en pause → `libre`, bulle `""` ;
    - aucune tâche active → `libre`, bulle `""`.
  - `statuts.present(titulaire: dict, taches: list[dict], maintenant) -> bool` — vrai si permanent, ou chef, ou au moins une tâche active, ou dernière `maj` de ses tâches à moins de 24 h.
  - `statuts.factory(releve_factory: dict, taches: list[dict], maintenant, fraicheur_min: int) -> dict` — `{"etat", "depuis", "derniere_activite", "inactive"}` ; `derniere_activite` = `maj` la plus récente en ISO ou `None` ; `inactive` vrai si en marche et dernière activité plus vieille que `fraicheur_min`.

- [ ] **Step 1: Écrire les tests**

```python
M = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
def t(minutes, active=True, titre="Tâche"):   # tâche mise à jour il y a `minutes`
    return {"id": titre, "titre": titre, "active": active, "maj": (M - timedelta(minutes=minutes)).isoformat()}

def test_lire_date(self):
    self.assertEqual(statuts.lire_date("2026-11-10T12:00:00+00:00"), M)
    self.assertEqual(statuts.lire_date("2026-11-10T12:00:00"), datetime(2026, 11, 10, 12, 0).astimezone())
    for mauvais in (None, "", "hier", 12): self.assertEqual(statuts.lire_date(mauvais), statuts.TRES_ANCIEN)
def test_duree(self):
    self.assertEqual([statuts.duree_en_clair(m) for m in (45, 60, 125, 47 * 60, 48 * 60, 5000)],
                     ["45 min", "1 h", "2 h", "47 h", "2 j", "3 j"])
def test_travail(self):
    s = statuts.statut([t(5, titre="A"), t(2, titre="B"), t(1, active=False, titre="C")], M, 30, False)
    self.assertEqual(s, {"statut": "travail", "bulle": "B (+1)"})
def test_titre_tronque(self):
    self.assertEqual(statuts.statut([t(1, titre="x" * 60)], M, 30, False)["bulle"], "x" * 40 + "…")
def test_sans_nouvelles(self):
    self.assertEqual(statuts.statut([t(125)], M, 30, False), {"statut": "sans_nouvelles", "bulle": "sans nouvelles depuis 2 h"})
def test_limite_de_fraicheur(self):
    self.assertEqual(statuts.statut([t(30)], M, 30, False)["statut"], "travail")
    self.assertEqual(statuts.statut([t(31)], M, 30, False)["statut"], "sans_nouvelles")
def test_pause(self):
    self.assertEqual(statuts.statut([t(125)], M, 30, True), {"statut": "libre", "bulle": ""})
    self.assertEqual(statuts.statut([t(5)], M, 30, True)["statut"], "travail")
def test_date_illisible(self):
    self.assertEqual(statuts.statut([{"id": "a", "titre": "A", "active": True, "maj": "?"}], M, 30, False),
                     {"statut": "sans_nouvelles", "bulle": "sans nouvelles"})
def test_libre(self): self.assertEqual(statuts.statut([t(1, active=False)], M, 30, False), {"statut": "libre", "bulle": ""})
def test_present(self):
    self.assertTrue(statuts.present({"cle": "a"}, [t(23 * 60, active=False)], M))
    self.assertFalse(statuts.present({"cle": "a"}, [t(25 * 60, active=False)], M))
    self.assertFalse(statuts.present({"cle": "a"}, [], M))
    self.assertTrue(statuts.present({"cle": "a", "permanent": True}, [], M))
    self.assertTrue(statuts.present({"cle": "a", "chef": True}, [], M))
    self.assertTrue(statuts.present({"cle": "a"}, [t(9999)], M))
def test_factory_inactive(self):
    f = statuts.factory({"etat": "en marche"}, [t(45)], M, 30); self.assertTrue(f["inactive"])
    f = statuts.factory({"etat": "en pause"}, [t(45)], M, 30); self.assertFalse(f["inactive"])
    f = statuts.factory({"etat": "en marche"}, [], M, 30); self.assertEqual((f["inactive"], f["derniere_activite"]), (True, None))
```

- [ ] **Step 2: Lancer, vérifier l'échec.**
- [ ] **Step 3: Écrire `bureau/statuts.py`.**
- [ ] **Step 4: Relancer** → tout passe.
- [ ] **Step 5: Commit et push.**

### Task 4: L'équipe — prénoms et couleurs

**Files:**
- Create: `bureau/equipe.py`, `tests/test_equipe.py`

**Interfaces:**
- Produces:
  - `equipe.PRENOMS: list[str]` — 24 prénoms français courants, mixtes, tous distincts. `equipe.COULEURS: list[str]` — 12 couleurs `#rrggbb` distinctes et lisibles sur fond clair.
  - `class equipe.Equipe(chemin: Path)` — fichier JSON `{"agents": {cle: {"prenom", "couleur", "modele"?}}}` ; absent ou illisible → équipe vide (le fichier illisible n'est pas écrasé avant la première attribution réussie : il est renommé `<nom>.illisible`).
  - `Equipe.agent(cle: str) -> dict` — `{"prenom", "couleur"}` et `"modele"` si l'utilisateur en a fixé un. Clé inconnue : premier prénom de `PRENOMS` non utilisé (au-delà de 24 : `"Agent 25"`, `"Agent 26"`…), couleur suivante en tournant ; enregistré tout de suite, par remplacement atomique. Le chef (`cle == "chef"` ou appelé avec `chef=True`) reçoit le prénom `"Chef"` s'il est inconnu.
  - Les valeurs modifiées à la main dans le fichier sont respectées et jamais réécrites.

- [ ] **Step 1: Écrire les tests**

```python
def test_prenoms_et_couleurs(self):
    self.assertEqual((len(equipe.PRENOMS), len(set(equipe.PRENOMS)), len(set(equipe.COULEURS))), (24, 24, 12))
def test_attribution_stable(self):
    e = equipe.Equipe(self.f); a = e.agent("dev:1"); b = e.agent("dev:2")
    self.assertNotEqual(a["prenom"], b["prenom"])
    self.assertEqual(equipe.Equipe(self.f).agent("dev:1"), a)          # relu depuis le disque
def test_modification_a_la_main_respectee(self):
    self.f.write_text('{"agents": {"dev:1": {"prenom": "Zoé", "couleur": "#000000", "modele": "Haiku"}}}', encoding="utf-8")
    self.assertEqual(equipe.Equipe(self.f).agent("dev:1"), {"prenom": "Zoé", "couleur": "#000000", "modele": "Haiku"})
def test_plus_de_24(self):
    e = equipe.Equipe(self.f); noms = [e.agent(f"k{i}")["prenom"] for i in range(26)]
    self.assertEqual(len(set(noms)), 26); self.assertEqual(noms[24], "Agent 25")
def test_chef(self): self.assertEqual(equipe.Equipe(self.f).agent("chef")["prenom"], "Chef")
def test_fichier_illisible_mis_de_cote(self):
    self.f.write_text("{", encoding="utf-8"); equipe.Equipe(self.f).agent("a")
    self.assertTrue(self.f.with_name(self.f.name + ".illisible").exists())
```

- [ ] **Step 2: Lancer, vérifier l'échec.**
- [ ] **Step 3: Écrire `bureau/equipe.py`.**
- [ ] **Step 4: Relancer** → tout passe.
- [ ] **Step 5: Commit et push.**

### Task 5: L'état servi à la page

**Files:**
- Create: `bureau/etat.py`, `tests/test_etat.py`

**Interfaces:**
- Consumes: `releve.obtenir`, `statuts.statut/present/factory`, `Equipe.agent`.
- Produces:
  - `etat.construire(r: dict, eq: Equipe, maintenant: datetime, fraicheur_min: int) -> dict` — `r` est un relevé normalisé ; retourne l'état de la section « Les deux formats ». Fraîcheur d'un titulaire : son `fraicheur_min` s'il en a un, sinon l'argument. Modèle : celui du fichier d'équipe s'il existe, sinon celui du relevé, sinon `"?"`. Les titulaires non `present` sont retirés et leurs tâches passent à `agent: None`. Le chef est toujours dans `agents`, avec `service: None`.
  - `etat.erreur(message: str, maintenant) -> dict` — état vide valide (`agents`, `taches`, `services`, `colonnes` vides, `factory.etat` `"inconnu"`) avec `erreur` renseigné.
  - `etat.agents_locaux_au_travail(e: dict) -> int` — agents `lieu == "local"`, `statut == "travail"`, hors chef.
  - `etat.lire(regl: dict, eq: Equipe, maintenant) -> dict` — `releve.obtenir` puis `construire`, ou `erreur`.

- [ ] **Step 1: Écrire les tests** (relevé de base : celui de la tâche 2 normalisé, `maj` de `t1` = maintenant − 5 min)

```python
def test_agent_au_travail(self):
    a = self.etat()["agents"]; d1 = next(x for x in a if x["id"] == "d1")
    self.assertEqual((d1["statut"], d1["bulle"], d1["taches"], d1["service"], d1["lieu"]), ("travail", "T", ["t1"], "dev", "local"))
    self.assertTrue(d1["prenom"]); self.assertRegex(d1["couleur"], r"^#[0-9a-f]{6}$")
def test_chef_toujours_la(self):
    chef = next(x for x in self.etat()["agents"] if x["chef"]); self.assertIsNone(chef["service"])
def test_agent_parti(self):            # tâche inactive, maj il y a 30 h
    e = self.etat(active=False, minutes=30 * 60)
    self.assertNotIn("d1", [x["id"] for x in e["agents"]]); self.assertIsNone(e["taches"][0]["agent"])
def test_fraicheur_par_titulaire(self): # titulaire fraicheur_min=90, maj il y a 60 min -> travail ; sans -> sans_nouvelles
def test_modele(self):                  # équipe > relevé > "?"
def test_erreur(self):
    e = etat.erreur("x", M); self.assertEqual((e["erreur"], e["agents"], e["factory"]["etat"]), ("x", [], "inconnu"))
def test_lire_releve_absent_ne_plante_pas(self):
    e = etat.lire({"releve": {"fichier": "absent.json"}, "dossier": str(self.tmp), "fraicheur_min": 30}, self.eq, M)
    self.assertTrue(e["erreur"])
def test_agents_locaux(self):           # 1 local au travail, 1 cloud au travail, chef -> 1
def test_etat_json_serialisable(self): json.dumps(self.etat())
```

- [ ] **Step 2: Lancer, vérifier l'échec.**
- [ ] **Step 3: Écrire `bureau/etat.py`.**
- [ ] **Step 4: Relancer** → tout passe.
- [ ] **Step 5: Commit et push.**

### Task 6: La charge de l'ordinateur et le serveur

**Files:**
- Create: `bureau/charge.py`, `bureau/serveur.py`, `tests/test_charge.py`, `tests/test_serveur.py`
- Modify: `lancer.py`

**Interfaces:**
- Consumes: `reglages.charger/fixer_charge_max`, `etat.lire/agents_locaux_au_travail`, `Equipe`.
- Produces — `bureau/charge.py` :
  - `charge.machine() -> dict` — `{"coeurs": int, "memoire_totale_go": float, "disponible": bool}` ; `disponible` faux hors Windows.
  - `class charge.Sonde` — `lire() -> dict | None` : `{"cpu": float, "memoire": float}` en pourcentages 0–100, `None` hors Windows. CPU par différence de `GetSystemTimes` entre deux appels (premier appel : 0.0) ; mémoire par `GlobalMemoryStatusEx`.
  - `class charge.Lisseur(fenetre_s=60)` — `ajouter(t: float, cpu: float)`, `moyenne() -> float` (moyenne des échantillons des `fenetre_s` dernières secondes ; 0.0 si vide).
  - `charge.affichee(cpu_lisse: float, memoire: float) -> int` — `round(max(...))`, bornée 0–100.
  - `charge.feu_vert(valeur: int, maximum: int) -> bool` — `valeur <= maximum`.
  - `class charge.Historique(chemin: Path)` — fichier `.jsonl`, une ligne `{"t", "charge", "agents_locaux"}` par appel à `noter(t, charge, agents_locaux)` ; `lire() -> list[dict]` (lignes illisibles ignorées) ; au-delà de 7 jours les lignes sont retirées à l'écriture.
  - `charge.conseiller(historique: list[dict], mach: dict) -> dict` — `{"valeur": int, "explication": str, "source": "historique" | "machine"}`, algorithme ci-dessous.
- Produces — `bureau/serveur.py` :
  - `serveur.creer(chemin_reglages: Path, port: int | None = None) -> ThreadingHTTPServer` — lié à `127.0.0.1` ; `port=0` permis pour les tests. Fichier d'équipe : `equipe.json` et historique : `charge-historique.jsonl`, dans le dossier du fichier de réglages.
  - Un fil d'arrière-plan lit la sonde toutes les 5 s et note l'historique toutes les 60 s.
  - `GET /api/etat` → état (HTTP 200 même en erreur de relevé ; résultat gardé 2 s).
  - `GET /api/charge` → `{"disponible", "cpu", "memoire", "charge", "max", "feu_vert", "coeurs", "memoire_totale_go"}`.
  - `GET /api/conseil` → résultat de `conseiller`.
  - `POST /api/reglages` corps `{"charge_max": int}` → 200 et les réglages ; exige l'en-tête `X-Bureau: 1` et `Content-Type: application/json`, sinon 403 ; valeur refusée → 400 avec `{"erreur": "…"}`.
  - `GET /` et fichiers statiques depuis `bureau/web/` ; toute tentative de sortir de ce dossier → 404. En-tête `Cache-Control: no-store`.
  - `serveur.main(argv) -> int` : `serveur --reglages <chemin>` lance le serveur et affiche l'adresse ; `charge --reglages <chemin>` mesure pendant 5 s (deux lectures de sonde), affiche `ok : charge 42 % (max 75 %)` et retourne 0, ou `attendre : charge 83 % (max 75 %)` et retourne 1 ; hors Windows : `mesure indisponible, on laisse passer` et 0.

**Le conseil** (à implémenter tel quel) :

```
actifs = lignes de l'historique avec agents_locaux >= 1
si len(actifs) < 30 :
    valeur = 70 si memoire_totale_go >= 16 et coeurs >= 8 ; 60 si memoire_totale_go >= 8 ; sinon 50
    source = "machine"
    explication = "Pas encore assez de mesures avec des agents au travail. D'après la machine
                   ({coeurs} cœurs, {memoire_totale_go:.0f} Go), je conseille {valeur} % par prudence."
sinon :
    repos     = médiane des charges où agents_locaux == 0   (si aucune : la plus petite charge de l'historique)
    par_agent = médiane sur les lignes actives de (charge - repos) / agents_locaux, minimum 0
    brute     = 85 - par_agent
    valeur    = brute arrondie au multiple de 5 inférieur, bornée entre max(40, repos + 5 arrondi au multiple de 5 supérieur) et 85
    source    = "historique"
    explication = "Au repos la machine est à {repos:.0f} %, et chaque agent local ajoute environ {par_agent:.0f} %.
                   Pour rester sous 85 % après un lancement, je conseille {valeur} %."
```

- [ ] **Step 1: Écrire les tests de la charge**

```python
def test_lisseur(self):
    l = charge.Lisseur(60); [l.ajouter(t, c) for t, c in ((0, 100), (30, 20), (70, 40))]
    self.assertEqual(l.moyenne(), 30.0); self.assertEqual(charge.Lisseur().moyenne(), 0.0)
def test_affichee(self): self.assertEqual([charge.affichee(*a) for a in ((12.4, 61.6), (120, 5), (-3, -1))], [62, 100, 0])
def test_feu_vert(self): self.assertEqual([charge.feu_vert(75, 75), charge.feu_vert(76, 75)], [True, False])
def test_conseil_machine(self):
    for mach, attendu in (({"coeurs": 8, "memoire_totale_go": 16}, 70), ({"coeurs": 4, "memoire_totale_go": 16}, 60),
                          ({"coeurs": 4, "memoire_totale_go": 4}, 50)):
        c = charge.conseiller([], mach); self.assertEqual((c["valeur"], c["source"]), (attendu, "machine"))
def test_conseil_historique(self):   # repos 30, un agent ajoute 22 -> 85-22=63 -> 60
    h = [{"t": i, "charge": 30, "agents_locaux": 0} for i in range(20)] + [{"t": i, "charge": 52, "agents_locaux": 1} for i in range(20)] \
        + [{"t": i, "charge": 74, "agents_locaux": 2} for i in range(20)]
    c = charge.conseiller(h, {"coeurs": 8, "memoire_totale_go": 16})
    self.assertEqual((c["valeur"], c["source"]), (60, "historique")); self.assertIn("60 %", c["explication"])
def test_conseil_borne_basse(self):  # repos 70, par agent 40 -> brute 45, plancher max(40, 75) = 75
def test_conseil_borne_haute(self):  # par agent 0 -> 85
def test_historique(self):           # noter 3 lignes dont une vieille de 8 jours -> lire() en rend 2 ; ligne corrompue ignorée
@unittest.skipUnless(sys.platform == "win32", "Windows")
def test_sonde_reelle(self):
    s = charge.Sonde(); s.lire(); time.sleep(0.3); m = s.lire()
    self.assertTrue(0 <= m["cpu"] <= 100 and 0 < m["memoire"] <= 100)
    self.assertTrue(charge.machine()["coeurs"] >= 1 and charge.machine()["memoire_totale_go"] > 0.5)
```

- [ ] **Step 2: Écrire les tests du serveur** (serveur démarré sur le port 0 dans un fil, réglages pointant sur une copie de `exemples/demo` dans un dossier temporaire)

```python
def test_etat(self):          # GET /api/etat -> 200, JSON, projet == "Démo", erreur is None
def test_etat_releve_casse(self):  # on écrit "{" dans le relevé, on attend 2,1 s -> 200, erreur non vide
def test_charge(self):        # GET /api/charge -> clés attendues, max == 75
def test_conseil(self):       # GET /api/conseil -> "valeur" entre 40 et 85
def test_reglage(self):       # POST avec en-têtes -> 200 ; puis /api/charge donne max == 60 ; fichier reglages mis à jour
def test_reglage_sans_entete(self):  # POST sans X-Bureau -> 403 et fichier inchangé
def test_reglage_invalide(self):     # {"charge_max": 200} -> 400
def test_page(self):          # GET / -> 200 text/html (créer un bureau/web/index.html minimal si absent)
def test_pas_de_sortie_du_dossier(self):  # GET /../reglages.py et /%2e%2e/lancer.py -> 404
def test_commande_charge(self):      # serveur.main(["charge", "--reglages", …]) retourne 0 ou 1 et imprime "charge"
```

- [ ] **Step 3: Lancer, vérifier l'échec.**
- [ ] **Step 4: Écrire `bureau/charge.py`, `bureau/serveur.py`, brancher `lancer.py`.**
- [ ] **Step 5: Relancer** → tout passe.
- [ ] **Step 6: Vérifier à la main** — `py -3.12 lancer.py serveur --reglages exemples/demo/reglages.json`, puis ouvrir `http://127.0.0.1:8770/api/etat` et `/api/charge` : l'état de la démo et une charge plausible comparée au Gestionnaire des tâches (écart de moins de 10 points).
- [ ] **Step 7: Commit et push.**

### Task 7: La logique de la page — changements, plan, régie

**Files:**
- Create: `bureau/web/logique/diff.js`, `bureau/web/logique/plan.js`, `bureau/web/logique/regie.js`, `bureau/web/tests/diff.test.js`, `bureau/web/tests/plan.test.js`, `bureau/web/tests/regie.test.js`

Fonctions pures, sans three.js ni DOM. Repère : `x` vers la droite, `z` vers le bas du plan, unités en mètres.

**Interfaces:**
- Produces — `diff.js` :
  - `changements(avant, apres) -> Array<{tache, de, vers, porteur}>` — `avant` nul → `[]`. Pour chaque tâche `postit` de `apres` : absente d'`avant` → `{de: null, vers, porteur: idChef}` ; colonne différente → `porteur` = `agent` de la tâche dans `avant` s'il existe encore dans `apres.agents`, sinon l'id du chef. Tâches disparues : rien. `idChef` = l'agent `chef: true` d'`apres`.
  - `etatUtilisable(etat) -> boolean` — faux si `etat.erreur` est renseigné.
- Produces — `plan.js` :
  - `creerPlan(services, colonnes) -> plan` avec :
    - `plan.pieces: Array<{id, nom, type, x, z, largeur, profondeur}>` — une par service (`type: "service"`), plus `direction`, `cafe` ; aucune ne se chevauche ; l'open space au centre contient le Kanban.
    - `plan.poste(serviceId, i) -> {x, z}` — place n° `i` du service ; 4 postes avec bureau, puis des places debout distinctes dans la pièce pour `i >= 4`. Deux indices différents ne donnent jamais la même position (écart ≥ 0,6).
    - `plan.cafe(i) -> {x, z}` — places distinctes, sans limite.
    - `plan.chef -> {x, z}`, `plan.directeur -> {x, z}`.
    - `plan.kanban -> {x, z, devant: {x, z}, attente(i) -> {x, z}}` et `plan.postit(colonneIndex, rang) -> {u, v}` (position sur le tableau, `rang` au-delà de la hauteur → même case avec un compteur géré par l'affichage).
    - `plan.chemin(a, b) -> Array<{x, z}>` — suite de points de `a` à `b` passant par les portes ; premier point `a`, dernier `b`.
- Produces — `regie.js` :
  - `class Regie { constructor(plan) }`
  - `regie.appliquer(etat, changements)` — met à jour les acteurs (ajout, retrait, cible) et empile les missions ; au plus 6 missions en attente, les suivantes déplacent le post-it tout de suite.
  - `regie.avancer(dt)` — avance le temps de `dt` secondes : marche à 1,5 m/s le long du chemin, 1,2 s d'arrêt devant le tableau pour poser le post-it, un seul agent à la fois devant le tableau, les autres sur `kanban.attente(i)`.
  - `regie.acteurs: Map<id, {x, z, cap, action, agent}>` — `action` parmi `"assis"`, `"debout"`, `"marche"`, `"cafe"`, `"postit"` ; `cap` en radians ; `agent` = l'objet agent de l'état.
  - `regie.postits: Map<tacheId, {colonne, rang}>` — ce que le tableau montre en ce moment (en retard sur l'état tant que la mission n'est pas faite).
  - Règle de destination hors mission : `travail` ou `sans_nouvelles` → son poste (`assis` ; `debout` pour une place sans bureau) ; `libre` → café ; chef → `plan.chef` (`debout`). Premier `appliquer` : chacun est posé directement à sa destination, post-its en place.
  - Un agent retiré de l'état pendant sa mission : la mission est finie par le chef.

- [ ] **Step 1: Écrire les tests**

```js
// diff.test.js
test("premier état : aucun changement", () => assert.deepEqual(changements(null, E1), []));
test("changement de colonne : c'est l'ancien titulaire qui porte", () => {
  const apres = modifier(E1, "t1", {colonne: "revue", agent: "qa1"});
  assert.deepEqual(changements(E1, apres), [{tache: "t1", de: "encours", vers: "revue", porteur: "dev1"}]);
});
test("ancien titulaire parti : le chef porte", /* dev1 retiré de apres.agents -> porteur "chef" */);
test("ancien titulaire nul : le chef porte");
test("nouvelle tâche : posée par le chef", /* {de: null, vers: "afaire", porteur: "chef"} */);
test("tâche sans post-it ignorée");
test("tâche disparue : rien");
test("même colonne, autre agent : rien");

// plan.test.js
test("pièces sans chevauchement, 1 à 6 services");
test("9 agents dans un service : 9 places distinctes", () => {
  const p = creerPlan([{id: "dev", nom: "Dev"}], COLS);
  const pts = Array.from({length: 9}, (_, i) => p.poste("dev", i));
  for (let i = 0; i < 9; i++) for (let j = i + 1; j < 9; j++) assert.ok(Math.hypot(pts[i].x - pts[j].x, pts[i].z - pts[j].z) >= 0.6);
});
test("20 places de café distinctes");
test("chemin : part de a, arrive à b, aucun point hors du bâtiment");
test("les places sont dans leur pièce");

// regie.test.js
test("premier appliquer : au travail au poste, libre au café, chef à sa place");
test("mission : l'agent marche, pose, et le post-it ne change qu'à la pose", () => {
  const r = new Regie(plan); r.appliquer(E1, []);
  r.appliquer(E2, changements(E1, E2));
  assert.equal(r.postits.get("t1").colonne, "encours"); assert.equal(r.acteurs.get("dev1").action, "marche");
  avancerJusqua(r, () => r.acteurs.get("dev1").action === "postit", 60);
  avancerJusqua(r, () => r.postits.get("t1").colonne === "revue", 5);
  avancerJusqua(r, () => r.acteurs.get("dev1").action === "cafe", 60);   // plus de tâche active -> café
});
test("deux missions : un seul agent devant le tableau à la fois");
test("rafale de 20 changements : 6 missions, 14 post-its déplacés tout de suite", () => {
  /* après appliquer : 14 post-its déjà dans la nouvelle colonne, 6 encore dans l'ancienne */ });
test("agent retiré pendant sa mission : le chef la termine");
test("un agent libre à qui on confie une tâche quitte le café pour son poste");
test("avancer(0) et avancer(3600) ne plantent pas et laissent tout le monde à une position finie");
```

- [ ] **Step 2: Lancer, vérifier l'échec** — `node --test bureau/web/tests/`.
- [ ] **Step 3: Écrire `diff.js`, `plan.js`, `regie.js`.** Disposition conseillée du plan : services sur le pourtour, open space et Kanban au centre, café et direction en bas ; portes de chaque pièce vers l'open space ; `chemin` = poste → porte de la pièce → open space → porte → arrivée.
- [ ] **Step 4: Relancer** → tout passe.
- [ ] **Step 5: Commit et push.**

### Task 8: La scène 3D en volumes simples

**Files:**
- Create: `bureau/web/index.html`, `bureau/web/style.css`, `bureau/web/main.js`, `bureau/web/scene/scene.js`, `bureau/web/scene/personnages.js`, `bureau/web/scene/kanban.js`, `bureau/web/scene/modeles.js`, `bureau/web/modeles/manifeste.json`, `bureau/web/vendor/*`, `bureau/web/vendor/LICENCE-three.txt`

**Interfaces:**
- Consumes: `changements`, `creerPlan`, `Regie` ; `/api/etat`.
- Produces:
  - `scene.js` : `creerScene(conteneur, plan) -> {scene, camera, rendu(), redimensionner(), pointer(evenement) -> {type: "agent"|"postit"|"service"|"direction"|null, id}}`. Caméra orthographique, angles isométriques (rotation 45° autour de la verticale, inclinaison 35,264°), cadrée sur tout le bâtiment avec une marge, recadrée au redimensionnement. Pas de contrôle de caméra dans cette tâche. `scene.assombrir(vrai|faux)` baisse la lumière (pause).
  - `modeles.js` : `async charger(manifesteUrl) -> {creer(nom) -> Object3D}` — rend le GLB déclaré pour `nom` s'il s'est chargé, sinon un volume simple de même encombrement. Noms : `bureau`, `chaise`, `ecran`, `armoire`, `etagere`, `plante`, `machine_cafe`, `canape`, `table_basse`, `tableau`, `bureau_direction`, `personnage`. `manifeste.json` est `{}` dans cette tâche.
  - `personnages.js` : `class Personnages { constructor(scene, modeles) ; synchroniser(acteurs: Map) ; animer(dt) }` — un personnage par acteur, teinté par `agent.couleur`, orienté selon `cap`, pose selon `action`. Étiquette HTML au-dessus (prénom, nuage ☁ si `lieu == "cloud"`) et bulle (texte `agent.bulle` ; grisée si `sans_nouvelles` ; absente si vide), via `CSS2DRenderer`, remplies par `textContent`.
  - `kanban.js` : `class Kanban { constructor(scene, plan, modeles) ; synchroniser(colonnes, postits: Map, taches, file) }` — titres de colonnes, un post-it par tâche de couleur stable par tâche ; quand une colonne déborde, les derniers post-its sont remplacés par « +N » ; la file d'attente apparaît dans la première colonne en post-its pâles suivis de « +reste ».
  - `main.js` : toutes les 3 s `GET /api/etat` ; si utilisable : `changements` puis `regie.appliquer` ; sinon garder la scène et signaler (`document.body.dataset.erreur`). Boucle `requestAnimationFrame` : `regie.avancer(dt)` avec `dt` plafonné à 0,1 s, synchronisation, rendu. Onglet masqué : la boucle s'arrête, et au retour la régie est remise à plat sur le dernier état (pas d'animation de rattrapage).

- [ ] **Step 1: Demander l'accord de l'utilisateur pour télécharger three.js**, en annonçant les fichiers, la source et la taille (environ 1,5 Mo au total) : depuis `https://cdn.jsdelivr.net/npm/three@0.170.0/` → `build/three.module.js`, `examples/jsm/loaders/GLTFLoader.js`, `examples/jsm/utils/BufferGeometryUtils.js`, `examples/jsm/utils/SkeletonUtils.js`, `examples/jsm/renderers/CSS2DRenderer.js`, et `LICENSE` (enregistré sous `LICENCE-three.txt`). Les ranger dans `bureau/web/vendor/` en conservant l'arborescence `build/` et `examples/jsm/`. Ne pas continuer sans réponse.
- [ ] **Step 2: `index.html`** avec une carte d'import : `"three"` → `./vendor/build/three.module.js`, `"three/addons/"` → `./vendor/examples/jsm/`. Aucune ressource chargée depuis internet.
- [ ] **Step 3: Écrire la scène, les personnages (capsule + sphère), le Kanban, `main.js`.**
- [ ] **Step 4: Vérifier dans le navigateur** — lancer le serveur sur la démo, ouvrir la page (outil de prévisualisation), capture d'écran. Attendu : bâtiment entier visible en isométrique, une pièce par service avec son nom, agents à leur poste ou au café avec prénom, Kanban au centre avec les post-its dans les bonnes colonnes, aucune erreur dans la console.
- [ ] **Step 5: Vérifier le mouvement** — modifier `exemples/demo/releve.json` dans une copie temporaire servie à la place (changer la `colonne` d'une tâche et sa `maj`) : dans les 6 s, le bon agent marche jusqu'au tableau et le post-it change de colonne à son arrivée. Passer `factory.etat` à `"en pause"` : la lumière baisse.
- [ ] **Step 6: Vérifier la légèreté** — page ouverte 2 minutes sur la démo : processeur du navigateur sous 15 % d'un cœur au repos (Gestionnaire des tâches), pas de croissance mémoire continue. Si c'est au-dessus : limiter le rendu à 30 images par seconde et ne redessiner que lorsqu'un acteur bouge.
- [ ] **Step 7: Commit et push.**

### Task 9: L'interface — voyant, charge, cartes, panneaux

**Files:**
- Create: `bureau/web/ui/barre.js`, `bureau/web/ui/panneaux.js`, `bureau/web/ui/texte.js`, `bureau/web/tests/texte.test.js`
- Modify: `bureau/web/index.html`, `bureau/web/style.css`, `bureau/web/main.js`

**Interfaces:**
- Consumes: `scene.pointer`, `/api/charge`, `/api/conseil`, `POST /api/reglages`.
- Produces:
  - `texte.js` (pur) : `tronquer(texte, n) -> string` (ajoute « … » au-delà de `n`, accepte `null`) ; `voyant(factory, erreur, maintenant = new Date()) -> {libelle, ton}` — `"En marche"`/`ok`, `"En pause"`/`pause`, `"En marche, sans activité depuis 2 h"`/`alerte` (durée depuis `derniere_activite`, même format que côté serveur), `"Relevé indisponible"`/`alerte` si `erreur` ; `libelleCharge(c) -> string` — `"Charge 62 % · processeur 12 %, mémoire 62 %"` ou `"Mesure indisponible"`.
  - `barre.js` : bandeau du haut — nom du projet, voyant, barre de charge avec trait au maximum, rouge au-dessus du maximum, détail au survol ; rafraîchie toutes les 5 s. Bandeau d'erreur sous la barre quand le relevé est indisponible, avec le message du serveur.
  - `panneaux.js` : survol d'un agent → carte (prénom, service, modèle, « local » ou « cloud », titres de ses tâches) ; clic sur un post-it → carte (titre, colonne, agent, étape, dernière mise à jour) ; clic sur un service → panneau à droite (nom, agents et leur statut, mention « Les documents de ce service arriveront avec le projet 2 ») ; clic sur la direction → panneau avec le nombre de décisions en attente. Pastille rouge au-dessus du bureau du Directeur quand `decisions > 0`. Échap ou clic ailleurs ferme.
  - Panneau du service dont l'id est `facturation` (et, s'il n'existe pas, panneau de la direction) : réglage « Charge maximum pour lancer une nouvelle étape » — curseur 30–95 par pas de 5, valeur affichée, enregistrement à la validation ; bouton « Me conseiller » qui affiche la valeur et l'explication de `/api/conseil` avec un bouton « Appliquer ». Phrase fixe : « Les sessions cloud ne comptent pas : seule la charge de cet ordinateur est mesurée. »
  - Tout texte venu du serveur passe par `textContent`.

- [ ] **Step 1: Écrire les tests de `texte.js`**

```js
test("tronquer", () => { assert.equal(tronquer("x".repeat(300), 40), "x".repeat(40) + "…"); assert.equal(tronquer(null, 5), ""); assert.equal(tronquer("abc", 5), "abc"); });
test("voyant", () => {
  assert.deepEqual(voyant({etat: "en marche", inactive: false}, null), {libelle: "En marche", ton: "ok"});
  assert.deepEqual(voyant({etat: "en pause"}, null), {libelle: "En pause", ton: "pause"});
  assert.equal(voyant({etat: "en marche", inactive: true, derniere_activite: ilYA(125)}, null, MAINTENANT).libelle, "En marche, sans activité depuis 2 h");
  assert.equal(voyant({etat: "inconnu"}, "fichier absent").ton, "alerte");
});
test("libelleCharge", () => { assert.equal(libelleCharge({disponible: true, charge: 62, cpu: 12.4, memoire: 61.6}), "Charge 62 % · processeur 12 %, mémoire 62 %"); assert.equal(libelleCharge({disponible: false}), "Mesure indisponible"); });
```

- [ ] **Step 2: Lancer, vérifier l'échec ; écrire `texte.js` ; relancer.**
- [ ] **Step 3: Écrire `barre.js`, `panneaux.js`, le style.** Le panneau de droite ne recouvre pas le Kanban sur un écran de 1280 px de large : la scène se recadre dans l'espace restant.
- [ ] **Step 4: Vérifier dans le navigateur** (démo) — captures : bandeau avec voyant et barre ; carte d'un agent ; panneau Facturation ; « Me conseiller » puis « Appliquer » → le trait de la barre se déplace et `reglages.json` contient la valeur.
- [ ] **Step 5: Vérifier les textes hostiles** — dans une copie du relevé, donner à une tâche le titre `<img src=x onerror=alert(1)>` suivi de 300 caractères : le titre s'affiche littéralement, tronqué, aucune alerte, aucune erreur de console.
- [ ] **Step 6: Vérifier le relevé cassé** — écrire `{` dans la copie du relevé : la scène reste, le bandeau « Relevé indisponible » apparaît ; remettre le fichier : le bandeau disparaît.
- [ ] **Step 7: Commit et push.**

### Task 10: Le mode d'emploi

**Files:**
- Create: `docs/installation.md`
- Modify: `README.md`, `docs/releve.md`

Demandé par l'utilisateur : le dépôt explique comment il fonctionne, ce qui est réalisé, ce qu'il reste à faire, et fournit un manuel d'installation et de configuration.

- [ ] **Step 1: `docs/installation.md`** — sections, dans cet ordre : « Ce qu'il faut » (Windows, Python 3.12, un navigateur ; rien à installer d'autre) ; « Essayer avec la démo » (la commande, l'adresse, ce qu'on doit voir, et pourquoi les agents de la démo sont « sans nouvelles » tant qu'on ne touche pas au fichier) ; « Brancher son projet » (créer un dossier `.factory/` dans le projet et l'ajouter à son `.gitignore`, y écrire `reglages.json`, fournir le relevé par fichier ou par commande, renvoi à `docs/releve.md`) ; « Les réglages » (tableau : `port`, `charge_max`, `fraicheur_min`, `releve.fichier`, `releve.commande`, `releve.dossier`, avec défaut et effet) ; « L'équipe » (le fichier `equipe.json`, comment changer un prénom, une couleur, un modèle) ; « La charge » (ce qui est mesuré, « Me conseiller », la commande `charge` et ses codes de retour, la ligne type à ajouter aux consignes d'un orchestrateur) ; « En cas de problème » (port occupé, relevé indisponible, mesure indisponible, page blanche). Une note en tête : l'installation en tant que skill Claude arrivera avec le projet 4, ce manuel sera alors complété.
- [ ] **Step 2: Vérifier le manuel en le suivant** — exécuter à la lettre « Essayer avec la démo » puis « Brancher son projet » sur un dossier temporaire vide : chaque commande fonctionne telle qu'écrite.
- [ ] **Step 3: `README.md`** — mettre à jour « Comment ça marche » avec une capture d'écran du bureau (`docs/img/bureau.png`), « Avancement » et « Ce qu'il reste à faire ».
- [ ] **Step 4: Relire le dépôt entier à la recherche de tout ce qui est propre à un projet ou privé** — vérifier par `git grep` qu'aucun nom, chemin ou fichier propre à un projet réel n'est dans le dépôt (motifs tenus hors de ce dépôt).
- [ ] **Step 5: Commit et push.**

### Task 11: Le mobilier Tripo

**Files:**
- Create: `outils/decouper_glb.py`, `bureau/web/modeles/*.glb`
- Modify: `bureau/web/modeles/manifeste.json`, `bureau/web/scene/modeles.js`

**Interfaces:**
- Consumes: `modeles.creer(nom)`.
- Produces: `manifeste.json` de la forme `{"bureau": {"fichier": "bureau.glb", "hauteur": 0.75}, …}` — `modeles.js` met chaque GLB à l'échelle pour que sa hauteur soit celle indiquée, pose sa base au sol et le centre.

Hauteurs (m) : `bureau` 0,75 ; `chaise` 0,9 ; `ecran` 0,45 ; `armoire` 0,7 ; `etagere` 1,6 ; `plante` 0,9 ; `machine_cafe` 1,3 ; `canape` 0,8 ; `table_basse` 0,4 ; `tableau` 1,8 ; `bureau_direction` 0,78.

- [ ] **Step 1: Vérifier que Blender est disponible** (`blender --version`, ou le chercher dans `C:\Program Files\Blender Foundation`). S'il manque, le dire à l'utilisateur et lui demander comment il préfère séparer les objets avant de continuer.
- [ ] **Step 2: Donner à l'utilisateur la génération 1** (vérifier le nombre de caractères avant d'envoyer) :

> A set of six separate stylized office furniture props arranged in a row, side by side, not touching, on a plain empty background, three-quarter view: 1) a light wooden office desk with rounded corners, 2) a small swivel office chair with a teal fabric seat, 3) a flat computer monitor on a stand with a keyboard, 4) a two-drawer metal filing cabinet in soft blue, 5) an open wooden bookshelf with a few colored binders, 6) a potted green plant in a terracotta pot. Cozy hand-painted gouache look, soft matte colors, gentle shading, slightly chunky toy-like proportions, clean simple shapes, low detail, no text, no people, no floor.

Réglages Tripo Studio : onglet **HD Model** ; « Pose en T » **désactivée** ; qualité de maillage Ultra **désactivée** ; Texture **activée**, qualité **2K** ; « Supprimer l'éclairage » **activé** ; PBR **désactivé** ; topologie **Triangle** ; nombre de polygones **9000** ; « générer par parties » **désactivé** ; texture 8K **désactivée**. Ensuite : pas de Retopo, pas de Rig, pas d'animation. Export **GLB**. À vérifier avant d'exporter : six objets bien séparés, aucun ne touche son voisin, pas de sol ni de socle commun, pas de texte. Demander d'abord une capture de l'aperçu, puis le fichier.
- [ ] **Step 3: Écrire `outils/decouper_glb.py`** — script Blender (`blender -b -P outils/decouper_glb.py -- <entrée.glb> <dossier_sortie> <nom1,nom2,…>`) : importe, sépare par parties non reliées, regroupe les morceaux qui se touchent en un objet, trie les objets de gauche à droite, les nomme dans l'ordre donné, recentre chacun (base au sol), exporte un GLB par objet. S'arrête avec un message clair si le nombre d'objets trouvés n'est pas celui attendu.
- [ ] **Step 4: Découper, compléter `manifeste.json`, vérifier dans le navigateur** (capture : les six meubles à la bonne taille, bien posés, bien orientés face aux agents).
- [ ] **Step 5: Commit et push.**
- [ ] **Step 6: Donner la génération 2**, seulement après le Step 5 :

> A set of five separate stylized office props arranged in a row, side by side, not touching, on a plain empty background, three-quarter view: 1) a red espresso coffee machine on a small wooden counter, 2) a cosy two-seat sofa in mustard yellow fabric, 3) a low round wooden coffee table with two mugs, 4) a large blank whiteboard on a wheeled metal stand, completely empty white surface, 5) a wide executive desk in dark walnut wood with a green desk lamp. Cozy hand-painted gouache look, soft matte colors, gentle shading, slightly chunky toy-like proportions, clean simple shapes, low detail, no text, no people, no floor.

Mêmes réglages que la génération 1, nombre de polygones **9000**. À vérifier : cinq objets séparés, surface du tableau blanche et vide (les colonnes et post-its sont dessinés par la page).
- [ ] **Step 7: Découper, compléter le manifeste, vérifier** — le Kanban de la page se dessine sur la surface du modèle `tableau` : ajuster dans `kanban.js` le rectangle utile du tableau.
- [ ] **Step 8: Commit et push.**

### Task 12: Le personnage Tripo

**Files:**
- Create: `bureau/web/modeles/personnage.glb`
- Modify: `bureau/web/modeles/manifeste.json`, `bureau/web/scene/personnages.js`

- [ ] **Step 1: Donner à l'utilisateur la génération 3** :

> A single stylized office worker character, full body, standing in a neutral T-pose, arms straight out, legs slightly apart, facing forward. Friendly young adult, androgynous, simple round head, short plain light-grey hair, small dot eyes, light smile. Plain light-grey long-sleeve sweater, plain light-grey trousers, simple white sneakers. Chunky toy-like proportions: big head, short body, like a cozy management-game figurine. Hand-painted gouache look, soft matte colors, gentle shading, very simple shapes, no accessories, no bag, no glasses, no text, no logo, empty background.

Le personnage est gris clair exprès : la page le teinte à la couleur de chaque agent. Réglages : onglet **HD Model** ; « Pose en T » **activée** ; Ultra **désactivé** ; Texture **activée**, **2K** ; « Supprimer l'éclairage » **activé** ; PBR **désactivé** ; **Triangle** ; **5000** polygones ; « générer par parties » **désactivé**. Ensuite : **Rig** de type bipède/humanoïde ; **Animation** : la marche (« Walk ») ; noter et rapporter la liste des autres animations proposées (assis, attente, taper, boire). Export **GLB avec animation**. À vérifier : bras bien écartés du corps, doigts non fusionnés au corps, pieds au sol, la marche ne déforme pas les épaules.
- [ ] **Step 2: Intégrer** — `personnages.js` clone le modèle par agent (`SkeletonUtils.clone`), teinte ses matériaux par `agent.couleur` (multiplication), joue l'animation de marche pendant `"marche"`. Pour `"assis"`, `"debout"`, `"cafe"`, `"postit"` : poses fabriquées dans la page en tournant les os (hanches et genoux pliés pour assis ; avant-bras qui oscillent pour taper au clavier quand `statut == "travail"`, immobiles quand `sans_nouvelles` ; un bras levé avec une tasse au café ; un bras tendu vers le tableau). Si Tripo a fourni d'autres animations utilisables, les prendre à la place.
- [ ] **Step 3: Vérifier dans le navigateur** — captures : agent assis qui tape, agent qui marche, agent au café, agent devant le tableau ; deux agents de couleurs nettement différentes ; les pieds touchent le sol ; pas de glissement visible pendant la marche (vitesse d'animation accordée à 1,5 m/s).
- [ ] **Step 4: Si le personnage n'est pas exploitable** (pas de squelette, marche inutilisable) : garder les volumes simples, le dire à l'utilisateur avec les captures, et lui proposer l'outil autosprite. Ne pas l'utiliser sans son accord.
- [ ] **Step 5: Mettre à jour la capture du README, commit et push.**

---

## Après ce plan

Le branchement d'un projet réel se fait dans le dépôt de ce projet, avec son propre plan : un script qui produit le relevé, un dossier `.factory/` avec ses réglages, et la ligne de consigne qui appelle la commande `charge` avant une étape locale.
