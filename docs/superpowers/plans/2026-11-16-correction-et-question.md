# « Nouvelle correction » et « Une question » — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** ajouter au bureau, à côté de « + Nouvelle fonctionnalité », un parcours court « Nouvelle correction » et un
panneau « Une question » dont la réponse vient d'un appel court sur les documents, puis, si besoin, d'un agent qui lit le
code.

**Architecture :** une correction est une fonctionnalité `nature: "correction"` avec un workflow construit par le code
(`workflows.de_correction`) : cadrage court qui rend une fiche, puis un seul élément qui suit le flux de série existant.
Une question est un fil stocké dans `.factory/questions.jsonl` (`orchestrateur/questions.py`, commande
`lancer questions`, publié au relevé) ; le moteur y répond par un jugement `repondre_question` (Sonnet), puis, si la
réponse n'est pas sûre ou sur demande, par une action asynchrone `lire` (un `claude -p` Sonnet limité à
Read/Grep/Glob, attendu dans un fil de la boucle).

**Tech Stack :** Python 3.12 sans dépendance (unittest), JavaScript modules sans build (bureau), `claude -p`.

**Spec :** `docs/superpowers/specs/2026-11-16-correction-et-question-design.md` — à lire avant chaque tâche.

## Global Constraints

- Python : `py -3.12`, aucune dépendance ; tests `py -3.12 -m unittest <module> -v` depuis la racine du dépôt.
- Tout le texte visible et les noms de code sont en **français**, comme le reste du dépôt (identifiants sans accents).
- Le bureau n'écrit jamais dans le projet : il dépose des demandes ; c'est le moteur qui agit (`lancer …`).
- Les champs nouveaux du relevé et des demandes sont **facultatifs** : un projet ou un adaptateur ancien ne change pas.
- Une fonctionnalité sans `nature` est une fonctionnalité (`"fonctionnalite"`).
- L'agent lecteur n'a que `Read`, `Grep`, `Glob` ; jamais Fable ; modèle Sonnet.
- Tests rapides et qualitatifs : aucun appel d'IA réel (appels simulés), pas d'attente réelle.
- Fichiers de questions : au plus 200 fils ; 50 au relevé ; textes coupés à `MAX_RETOUR` (3500) côté bureau.
- Chaque tâche se termine par un commit ; à la fin : `git fetch`, rebase si besoin, `git push origin main`.

## Carte des fichiers

| Fichier | Rôle |
|---|---|
| `orchestrateur/questions.py` (nouveau) | stockage des fils de questions |
| `orchestrateur/outil.py` | `cmd_questions`, `TYPES_DEMANDE`, `cmd_actions` (nature, concerne, question), relevé |
| `orchestrateur/suivi.py` | `nouvelle_fonctionnalite` accepte `nature`, `concerne` |
| `orchestrateur/workflows.py` | `de_correction(fac, fid)` |
| `orchestrateur/consignes-correction.md` (nouveau) | consignes des étapes d'une correction |
| `bureau/demandes.py` | vérification de `question`, `question_approfondir`, `nature`, `concerne` |
| `bureau/releve.py` | vérification / normalisation de `questions`, `nature`, `concerne` |
| `moteur/jugement.py` + `moteur/consignes/repondre_question.md` (nouveau) | jugement `repondre_question` |
| `moteur/consignes/lire_pour_repondre.md` (nouveau) | consigne de l'agent lecteur |
| `moteur/regles.py` | `_sur_correction`, cadrage d'une correction, `_sur_question`, `_apres_repondre_question`, `a_lire`, `appliquer_lecture` |
| `moteur/boucle.py` | exécution de l'action `lire` dans un fil |
| `bureau/web/ui/barre.js`, `panneaux.js`, `fonctionnalite.js` | boutons, mode correction, badge |
| `bureau/web/ui/questions.js` (nouveau) | panneau « Questions » |
| `README.md`, `docs/avancement.md`, `docs/releve.md` | documentation |

---

### Task 1 : le stockage des questions

**Files :**
- Create : `orchestrateur/questions.py`
- Modify : `orchestrateur/outil.py` (import en tête près de `anomalies`, `cmd_questions` après `cmd_anomalies`,
  table des commandes ligne ~3774, relevé ligne ~2347)
- Modify : `bureau/releve.py` (vérification près de `_verifier_anomalies` ~ligne 988, normalisation ~ligne 1241)
- Test : `tests/test_questions.py` (nouveau)

**Interfaces :**
- Produces :
  - `questions.lire(f) -> list[dict]` ; `questions.ouvrir(f, e) -> dict` (fil) ; `questions.ajouter(f, ident, message)
    -> dict` ; `questions.marquer(f, ident, etat) -> dict` ; `questions.fil(f, ident) -> dict | None`.
  - Fil : `{id: "q<n>", ouverte, fonctionnalite: str|None, etat: "en_cours"|"repondue"|"en_lecture",
    messages: [{auteur: "utilisateur"|"factory", texte, t, images?, niveau?, sur?, suggestion?, fichiers_lus?}]}`.
  - `lancer questions` : `{"action": "lister"}` → `{"questions": [...]}` ; `ouvrir` (texte, images?, fonctionnalite?)
    → `{"question": fil}` ; `ajouter` (id, auteur, texte, …) → `{"question": fil}` ; `marquer` (id, etat).
  - Relevé v4 : `questions` = les 50 derniers fils.

- [ ] **Step 1 : écrire les tests qui échouent**

```python
"""Les questions sur le projet : un fil par ligne dans `.factory/questions.jsonl`."""
import json
import tempfile
import unittest
from pathlib import Path

from orchestrateur import questions


class TestQuestions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name) / ".factory"
        d.mkdir()
        self.f = {"chemin": str(d / "factory.json"), "nom": "Demo"}

    def test_sans_fichier_aucune_question(self):
        self.assertEqual(questions.lire(self.f), [])

    def test_ouvrir_puis_suivre_un_fil(self):
        q = questions.ouvrir(self.f, {"texte": "Comment est calculé le score ?", "fonctionnalite": "f2"})
        self.assertEqual((q["id"], q["etat"], q["fonctionnalite"]), ("q1", "en_cours", "f2"))
        questions.ajouter(self.f, "q1", {"auteur": "factory", "texte": "Par niveau.", "niveau": "documents",
                                         "sur": True, "suggestion": None})
        questions.marquer(self.f, "q1", "repondue")
        questions.ajouter(self.f, "q1", {"auteur": "utilisateur", "texte": "Et les bonus ?"})
        (fil,) = questions.lire(self.f)
        self.assertEqual([m["auteur"] for m in fil["messages"]], ["utilisateur", "factory", "utilisateur"])
        self.assertEqual(fil["etat"], "en_cours")       # une question de suivi rouvre le fil

    def test_refus(self):
        with self.assertRaises(ValueError):
            questions.ouvrir(self.f, {"texte": "  "})
        with self.assertRaises(ValueError):
            questions.ajouter(self.f, "q9", {"auteur": "factory", "texte": "x"})
        questions.ouvrir(self.f, {"texte": "x"})
        with self.assertRaises(ValueError):
            questions.marquer(self.f, "q1", "perdue")

    def test_limite_et_ligne_illisible(self):
        for i in range(questions.MAX_QUESTIONS + 3):
            questions.ouvrir(self.f, {"texte": f"Q{i}"})
        chemin = questions.chemin(self.f)
        with open(chemin, "a", encoding="utf-8") as fic:
            fic.write("pas du json\n")
        fils = questions.lire(self.f)
        self.assertEqual(len(fils), questions.MAX_QUESTIONS)
        self.assertEqual(fils[0]["messages"][0]["texte"], "Q3")     # les plus anciens partent d'abord
```

- [ ] **Step 2 : lancer, constater l'échec**

Run : `py -3.12 -m unittest tests.test_questions -v`
Expected : ERROR `cannot import name 'questions'`.

- [ ] **Step 3 : écrire `orchestrateur/questions.py`**

```python
"""Les questions sur le projet : ce que l'utilisateur demande au bouton « ? Une question », et les réponses de la
factory (d'après les documents, puis d'après le code).

Un fichier du projet, à côté du fichier de factory (`.factory/questions.jsonl`), un fil par ligne :
`{id, ouverte, fonctionnalite, etat (en_cours | repondue | en_lecture), messages: [{auteur (utilisateur | factory),
texte, t, images?, niveau? (documents | code), sur?, suggestion?, fichiers_lus?}]}`. Il n'est écrit que par
`lancer questions` ; le relevé le publie (`questions`). Une ligne illisible est ignorée.
"""
import json
import os
import re
from pathlib import Path

from orchestrateur import suivi as su

FICHIER = "questions.jsonl"
ETATS = ("en_cours", "repondue", "en_lecture")
AUTEURS = ("utilisateur", "factory")
NIVEAUX = ("documents", "code")
TEXTE_MAX = 6000
MAX_QUESTIONS = 200
MAX_MESSAGES = 40            # un fil trop long : les plus anciens messages partent, la question d'origine reste


def chemin(f):
    return Path(f["chemin"]).parent / FICHIER


def _valide(x):
    return (isinstance(x, dict) and isinstance(x.get("id"), str) and re.fullmatch(r"q[0-9]+", x["id"])
            and x.get("etat") in ETATS and isinstance(x.get("messages"), list) and x["messages"]
            and all(isinstance(m, dict) and m.get("auteur") in AUTEURS and isinstance(m.get("texte"), str)
                    for m in x["messages"]))


def lire(f):
    """Les fils, du plus ancien au plus récent (liste vide sans fichier)."""
    try:
        lignes = chemin(f).read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return []
    rendu = []
    for ligne in lignes:
        try:
            x = json.loads(ligne)
        except ValueError:
            continue
        if _valide(x):
            rendu.append(x)
    return rendu


def fil(f, ident):
    return next((x for x in lire(f) if x["id"] == ident), None)


def _ecrire(f, fils):
    c = chemin(f)
    c.parent.mkdir(parents=True, exist_ok=True)
    tmp = c.with_name(c.name + ".tmp")
    tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in fils), encoding="utf-8")
    os.replace(tmp, c)


def _texte(e):
    v = e.get("texte")
    if not isinstance(v, str) or not v.strip():
        raise ValueError("« texte » est obligatoire.")
    v = v.strip()
    if len(v) > TEXTE_MAX:
        raise ValueError(f"« texte » tient en {TEXTE_MAX} caractères au plus.")
    return v


def _message(e):
    auteur = e.get("auteur", "utilisateur")
    if auteur not in AUTEURS:
        raise ValueError("« auteur » vaut utilisateur ou factory.")
    m = {"auteur": auteur, "texte": _texte(e), "t": su.maintenant()}
    if e.get("images"):
        m["images"] = [str(x) for x in e["images"]][:4]
    if auteur == "factory":
        if e.get("niveau") not in NIVEAUX:
            raise ValueError("« niveau » vaut documents ou code.")
        m["niveau"], m["sur"] = e["niveau"], bool(e.get("sur"))
        m["suggestion"] = e.get("suggestion") if isinstance(e.get("suggestion"), dict) else None
        if isinstance(e.get("fichiers_lus"), list):
            m["fichiers_lus"] = [str(x)[:200] for x in e["fichiers_lus"]][:20]
    return m


def ouvrir(f, e):
    """Un fil nouveau : `texte`, et facultatifs `images`, `fonctionnalite`. Rend le fil."""
    fils = lire(f)
    numero = max([int(x["id"][1:]) for x in fils] or [0]) + 1
    fonc = e.get("fonctionnalite") if isinstance(e.get("fonctionnalite"), str) else None
    x = {"id": f"q{numero}", "ouverte": su.maintenant(), "fonctionnalite": fonc, "etat": "en_cours",
         "messages": [_message({**e, "auteur": "utilisateur"})]}
    fils.append(x)
    del fils[:max(0, len(fils) - MAX_QUESTIONS)]
    _ecrire(f, fils)
    return x


def ajouter(f, ident, e):
    """Un message de plus dans le fil `ident` ; un message de l'utilisateur rouvre le fil (`en_cours`)."""
    fils = lire(f)
    x = next((q for q in fils if q["id"] == ident), None)
    if x is None:
        raise ValueError(f"Question inconnue : {ident}")
    m = _message(e)
    x["messages"].append(m)
    if len(x["messages"]) > MAX_MESSAGES:
        x["messages"] = x["messages"][:1] + x["messages"][-(MAX_MESSAGES - 1):]
    if m["auteur"] == "utilisateur":
        x["etat"] = "en_cours"
    _ecrire(f, fils)
    return x


def marquer(f, ident, etat):
    if etat not in ETATS:
        raise ValueError("« etat » vaut en_cours, repondue ou en_lecture.")
    fils = lire(f)
    x = next((q for q in fils if q["id"] == ident), None)
    if x is None:
        raise ValueError(f"Question inconnue : {ident}")
    x["etat"] = etat
    _ecrire(f, fils)
    return x
```

- [ ] **Step 4 : brancher la commande et le relevé**

Dans `orchestrateur/outil.py` :
- à côté de `from orchestrateur import anomalies as anomalies_logiciel`, ajouter
  `from orchestrateur import questions as questions_projet  # noqa: E402` ;
- après `cmd_anomalies`, ajouter :

```python
QUESTIONS_AU_RELEVE = 50


def cmd_questions(ctx, e):
    """Les questions sur le projet (`.factory/questions.jsonl`, voir `orchestrateur/questions.py`) : `lister` (défaut),
    `ouvrir` (texte, images?, fonctionnalite?), `ajouter` (id, auteur, texte, niveau?, sur?, suggestion?,
    fichiers_lus?), `marquer` (id, etat). Seul écrivain du fichier."""
    action = e.get("action", "lister")
    try:
        if action == "lister":
            return {"questions": questions_projet.lire(ctx.f)}
        if action == "ouvrir":
            if e.get("fonctionnalite") is not None:
                _fonc(ctx.suivi.lire(), e["fonctionnalite"])      # Refus si inconnue
            return {"question": questions_projet.ouvrir(ctx.f, e)}
        if action == "ajouter":
            return {"question": questions_projet.ajouter(ctx.f, e.get("id"), e)}
        if action == "marquer":
            return {"question": questions_projet.marquer(ctx.f, e.get("id"), e.get("etat"))}
    except ValueError as ex:
        raise Refus(str(ex))
    raise Refus("« action » doit valoir lister, ouvrir, ajouter ou marquer.")
```

- dans la table des commandes (là où figure `"anomalies": (cmd_anomalies, "facultative")`), ajouter
  `"questions": (cmd_questions, "facultative")` ;
- dans le relevé (après `"anomalies_logiciel": …`), ajouter
  `"questions": questions_projet.lire(ctx.f)[-QUESTIONS_AU_RELEVE:],`.

Dans `bureau/releve.py`, sur le modèle exact de `anomalies_logiciel` :
- `if r.get("questions") is not None: _verifier_questions(r["questions"], erreurs)` à côté de l'appel à
  `_verifier_anomalies` ;
- la fonction :

```python
ETATS_QUESTION = ("en_cours", "repondue", "en_lecture")


def _verifier_questions(questions, erreurs):
    """`questions` (version 4, facultatif) : `[{id, etat, fonctionnalite?, ouverte?, messages: [{auteur, texte, t?,
    niveau?, sur?, suggestion?, images?, fichiers_lus?}]}]`, les questions posées sur le projet."""
    nom = "« questions »"
    if not isinstance(questions, list):
        erreurs.append(f"{nom} doit être une liste de questions.")
        return
    for k, x in enumerate(questions, 1):
        if (not _est_dict(x) or not _texte_plein(x.get("id")) or x.get("etat") not in ETATS_QUESTION
                or not isinstance(x.get("messages"), list) or not x["messages"]
                or not all(_est_dict(m) and m.get("auteur") in ("utilisateur", "factory")
                           and isinstance(m.get("texte"), str) for m in x["messages"])):
            erreurs.append(f"{nom} : la question {k} a « id », « etat » et des « messages » {{auteur, texte}}.")
```

- dans la normalisation, à côté de `anomalies_logiciel` :
  `if not v4 or not isinstance(n.get("questions"), list): n.pop("questions", None)`.

Ajouter au test un cas commande + relevé (dans `tests/test_questions.py`) :

```python
from tests.test_moteur_regles import Base


class TestCommandeQuestions(Base):
    def test_ouvrir_par_la_commande_et_publier_au_releve(self):
        q = self.ok("questions", entree={"action": "ouvrir", "texte": "À quoi sert l'écran titre ?"})["question"]
        self.assertEqual(q["id"], "q1")
        r = self.ok("releve")
        self.assertEqual([x["id"] for x in r["questions"]], ["q1"])
        self.assertIn("Fonctionnalité inconnue", self.refus("questions", entree={"action": "ouvrir", "texte": "x",
                                                                              "fonctionnalite": "f99"}))
```

(`self.ok` / `self.refus` : les aides de `tests/orch_aide.py` ; si l'aide de refus porte un autre nom, prendre celui
qu'utilisent les tests de `cmd_anomalies`, `grep -n "anomalies" tests/*.py`.)

- [ ] **Step 5 : lancer les tests**

Run : `py -3.12 -m unittest tests.test_questions tests.test_releve -v`
Expected : PASS.

- [ ] **Step 6 : commit**

```bash
git add orchestrateur/questions.py orchestrateur/outil.py bureau/releve.py tests/test_questions.py
git commit -m "Questions : le stockage des fils, la commande et le relevé"
```

---

### Task 2 : les demandes du bureau (nature, concerne, question)

**Files :**
- Modify : `bureau/demandes.py` (`CHAMPS`, `FACULTATIFS`, `DEMANDES_V4`, `_verifier_v4`)
- Modify : `orchestrateur/outil.py` (`TYPES_DEMANDE`, `cmd_actions`, résumé de fonctionnalité au relevé ~ligne 643)
- Modify : `orchestrateur/suivi.py` (`nouvelle_fonctionnalite`)
- Modify : `bureau/releve.py` (fonctionnalité : `nature`, `concerne` facultatifs)
- Test : `tests/test_demandes.py`, `tests/test_questions.py`

**Interfaces :**
- Consumes : `questions.ouvrir`, `questions.ajouter`, `questions.fil` (Task 1).
- Produces :
  - demande `fonctionnalite` : champs facultatifs `nature` (`"fonctionnalite"|"correction"`), `concerne` (fid) ;
    la fonctionnalité créée porte `nature` (toujours) et `concerne` (ou `None`) ; le relevé les publie.
  - demande `question` : `texte`, `images?`, `fichiers?`, `fil?`, `fonctionnalite?` ; `cmd_actions` ouvre le fil (ou y
    ajoute le message) et range son id dans `demande["fil"]`.
  - demande `question_approfondir` : `fil`.

- [ ] **Step 1 : tests qui échouent**

Dans `tests/test_demandes.py`, classe `TestVerifierV4` (qui a déjà `self.ok` / `self.erreur` sur un relevé v4 avec
fonctionnalités) — ajouter :

```python
    def test_correction(self):
        self.ok({"type": "fonctionnalite", "texte": "Le score ne se remet pas à zéro", "nature": "correction"})
        fid = self.r["fonctionnalites"][0]["id"]
        self.ok({"type": "fonctionnalite", "texte": "Bug", "nature": "correction", "concerne": fid})
        self.erreur({"type": "fonctionnalite", "texte": "Bug", "nature": "anomalie"})
        self.erreur({"type": "fonctionnalite", "texte": "Bug", "nature": "correction", "concerne": "f999"})
        self.erreur({"type": "fonctionnalite", "texte": "Écran", "concerne": fid})      # concerne : correction seulement

    def test_question(self):
        self.ok({"type": "question", "texte": "Comment est calculé le score ?"})
        self.ok({"type": "question", "texte": "Et les bonus ?", "fil": "q1"})
        self.ok({"type": "question", "texte": "x", "images": [image()]})
        self.erreur({"type": "question", "texte": "  "})
        self.erreur({"type": "question", "texte": "x", "fil": "q9"})
        self.ok({"type": "question_approfondir", "fil": "q1"})
        self.erreur({"type": "question_approfondir", "fil": "q9"})
```

Adapter le relevé de la classe pour qu'il contienne `"questions": [{"id": "q1", "etat": "repondue", "messages":
[{"auteur": "utilisateur", "texte": "?"}, {"auteur": "factory", "texte": "!", "niveau": "documents", "sur": True}]}]`
(prendre le nom réel de l'attribut de relevé et des aides de la classe en lisant ses premières lignes, ligne 280).

Dans `tests/test_questions.py`, classe `TestCommandeQuestions` :

```python
    def test_demande_question_ouvre_puis_suit_le_fil(self):
        i = self.ok("actions", entree={"type": "question", "texte": "Comment marche la sauvegarde ?"})["id"]
        d = next(x for x in self.ok("demandes")["demandes"] if x["id"] == i)
        self.assertEqual(d["fil"], "q1")
        self.ok("actions", entree={"type": "question", "texte": "Et en cloud ?", "fil": "q1"})
        (fil,) = self.ok("questions")["questions"]
        self.assertEqual(len(fil["messages"]), 2)

    def test_demande_correction_cree_une_fonctionnalite_de_nature_correction(self):
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Le score reste à 12", "nature": "correction"})
        f = self.fonc("f1")
        self.assertEqual((f["nature"], f["concerne"]), ("correction", None))
```

- [ ] **Step 2 : lancer, constater l'échec**

Run : `py -3.12 -m unittest tests.test_demandes tests.test_questions -v`
Expected : FAIL (`Demande inconnue : question`, `nature` absent).

- [ ] **Step 3 : implémenter**

`bureau/demandes.py` :
- `CHAMPS` : `"question": ("texte",), "question_approfondir": ("fil",)` ;
- `FACULTATIFS` : `"fonctionnalite": ("images", "fichiers", "nature", "concerne")` (étendre l'entrée existante) et
  `"question": ("images", "fichiers", "fil", "fonctionnalite")` ;
- `DEMANDES_V4` : ajouter `"question", "question_approfondir"` ;
- `NATURES = ("fonctionnalite", "correction")` ;
- dans `_verifier_v4`, avant la vérification générique du genre `fonctionnalite` :

```python
    if genre == "fonctionnalite":
        nature = demande.get("nature", "fonctionnalite")
        if nature not in NATURES:
            return "« nature » vaut fonctionnalite ou correction."
        if demande.get("concerne") is not None:
            if nature != "correction":
                return "« concerne » ne sert qu'à une correction."
            if _fonctionnalite(r, demande["concerne"]) is None:
                return f"Fonctionnalité inconnue : {demande['concerne']}"
    if genre in ("question", "question_approfondir"):
        fils = {q["id"]: q for q in r.get("questions") or []}
        if demande.get("fil") is not None and demande["fil"] not in fils:
            return f"Question inconnue : {demande['fil']}"
        if genre == "question_approfondir":
            dernier = fils[demande["fil"]]["messages"][-1]
            if dernier.get("auteur") != "factory" or dernier.get("niveau") != "documents":
                return "Cette question n'a pas de réponse d'après les documents à approfondir."
            return None
        if demande.get("fonctionnalite") is not None and _fonctionnalite(r, demande["fonctionnalite"]) is None:
            return f"Fonctionnalité inconnue : {demande['fonctionnalite']}"
        return _texte_libre(demande.get("texte"), "texte") or (
            verifier_images(demande["images"]) if "images" in demande else None)
```

et étendre `if genre in ("fonctionnalite", "message") and "images" in demande` pour inclure `"question"`.

`orchestrateur/suivi.py` :

```python
def nouvelle_fonctionnalite(donnees, nom, etape="cadrage", nature="fonctionnalite", concerne=None):
    f = {"id": f"f{suivant(donnees, 'f')}", "nom": nom, "etape": etape, "genre": None, "workflow": None,
         "nature": nature, "concerne": concerne,
         ...le reste inchangé...}
```

`orchestrateur/outil.py` :
- `TYPES_DEMANDE` : ajouter `"question", "question_approfondir"` ;
- `cmd_actions`, branche `fonctionnalite` :
  `f = su.nouvelle_fonctionnalite(s, texte(e, "texte")[:40], nature=e.get("nature") or "fonctionnalite",
  concerne=e.get("concerne"))` (refuser `nature` hors des deux valeurs, et un `concerne` inconnu via `_fonc(s, …)`) ;
- `cmd_actions`, nouvelle branche :

```python
        elif genre == "question":
            images = _pieces_jointes(ctx, e, "questions")[0]
            if e.get("fil"):
                q = questions_projet.ajouter(ctx.f, e["fil"], {"auteur": "utilisateur", "texte": texte(e, "texte"),
                                                               "images": images})
            else:
                if e.get("fonctionnalite") is not None:
                    _fonc(s, e["fonctionnalite"])
                q = questions_projet.ouvrir(ctx.f, {"texte": texte(e, "texte"), "images": images,
                                                    "fonctionnalite": e.get("fonctionnalite")})
            demande["fil"] = q["id"]
            if images:
                demande["images"] = images
```

  (vérifier la signature de `_pieces_jointes(ctx, e, dossier)` : son troisième argument est le sous-dossier de
  rangement ; `"questions"` range les images à part des fonctionnalités) ;
- le résumé de fonctionnalité au relevé (là où `"attend_reponse": f["attend_reponse"]` est écrit, ~ligne 643 et
  ~2271) : ajouter `"nature": f.get("nature") or "fonctionnalite", "concerne": f.get("concerne")`.

`bureau/releve.py` : dans la vérification d'une fonctionnalité v4, accepter `nature` (absent ou l'une des deux
valeurs) et `concerne` (texte ou nul) ; à la normalisation, `setdefault("nature", "fonctionnalite")` et
`setdefault("concerne", None)`.

- [ ] **Step 4 : lancer les tests**

Run : `py -3.12 -m unittest tests.test_demandes tests.test_questions tests.test_releve tests.test_orch_outil -v`
Expected : PASS (si `tests.test_orch_outil` n'existe pas, lancer `py -3.12 -m unittest discover -s tests -p "test_orch*"`).

- [ ] **Step 5 : commit**

```bash
git add bureau/demandes.py bureau/releve.py orchestrateur/outil.py orchestrateur/suivi.py tests/test_demandes.py tests/test_questions.py
git commit -m "Demandes : nature et fonctionnalité concernée d'une correction, questions et approfondissement"
```

---

### Task 3 : le workflow de correction

**Files :**
- Modify : `orchestrateur/workflows.py`
- Create : `orchestrateur/consignes-correction.md`
- Test : `tests/test_orch_workflows.py`

**Interfaces :**
- Produces : `workflows.de_correction(fac, fid, role_production, role_qa=None) -> dict`
  `{"id": f"w-{fid}", "fonctionnalite": fid, "genre": genre_du_projet, "nature": "correction", "flux": [...]}` avec
  `flux` = `[{id: f"{fid}-correctif", nom: "Correctif", role: role_production, regroupement: "regroupe"},
  ({id: f"{fid}-verification", nom: "Vérification", role: role_qa})?, {id: f"{fid}-validation", nom: "Validation
  de la correction", validation: True}]`.
  Le cadrage n'est pas une étape du flux : c'est l'étape `cadrage` de la fonctionnalité, comme pour toute
  fonctionnalité.
- Produces : `workflows.ETAPES_CORRECTION = ("correctif", "verification", "validation")` ;
  `workflows.CONSIGNES_CORRECTION` : chemin du fichier de consignes.

- [ ] **Step 1 : tests qui échouent**

```python
class TestDeCorrection(unittest.TestCase):
    FAC = {"genre": "jeu", "workflows": [], "flux": []}

    def test_avec_qa(self):
        w = workflows.de_correction(self.FAC, "f4", "dev", "qa")
        self.assertEqual(w["id"], "w-f4")
        self.assertEqual([e["id"] for e in w["flux"]], ["f4-correctif", "f4-verification", "f4-validation"])
        self.assertEqual([e.get("role") for e in w["flux"]], ["dev", "qa", None])
        self.assertTrue(workflows.est_validation(w["flux"][-1]))

    def test_sans_qa_pas_de_verification(self):
        w = workflows.de_correction(self.FAC, "f4", "dev")
        self.assertEqual([e["id"] for e in w["flux"]], ["f4-correctif", "f4-validation"])

    def test_consignes_presentes(self):
        texte = workflows.CONSIGNES_CORRECTION.read_text(encoding="utf-8")
        for titre in ("## Cadrage", "## Correctif", "## Vérification"):
            self.assertIn(titre, texte)
```

- [ ] **Step 2 : lancer, constater l'échec**

Run : `py -3.12 -m unittest tests.test_orch_workflows -v` → AttributeError `de_correction`.

- [ ] **Step 3 : implémenter**

```python
from pathlib import Path

CONSIGNES_CORRECTION = Path(__file__).resolve().parent / "consignes-correction.md"
ETAPES_CORRECTION = ("correctif", "verification", "validation")


def de_correction(f, fid, role_production, role_qa=None):
    """Le workflow d'une correction, construit sans appel d'IA : correctif (rôle de production, un seul agent),
    vérification (rôle QA, s'il existe), validation du Directeur. Étapes préfixées par `<fid>-`."""
    flux = [{"id": f"{fid}-correctif", "nom": "Correctif", "role": role_production,
             "regroupement": REGROUPEMENT_REGROUPE}]
    if role_qa:
        flux.append({"id": f"{fid}-verification", "nom": "Vérification", "role": role_qa})
    flux.append({"id": f"{fid}-validation", "nom": "Validation de la correction", CLE_VALIDATION: True,
                 "raison": "Vérifier la cause, le correctif et la preuve que l'anomalie ne revient pas."})
    return {"id": f"w-{fid}", "fonctionnalite": fid, "genre": f.get("genre"), "nature": "correction", "flux": flux}
```

Vérifier que les étapes d'agent du flux portent bien les champs attendus par `etape_ecrite` (ligne ~51) ; si un champ
`service` est exigé, le recopier depuis le métier du rôle (lire `etape_ecrite` avant d'écrire).

`orchestrateur/consignes-correction.md` :

```markdown
# Consignes d'une correction

Une correction répare un comportement existant du projet. Elle ne change rien d'autre.

## Cadrage
- Lis le signalement (et, s'il y en a une, la fonctionnalité concernée : son cahier, ses éléments).
- Ne pose une question à l'utilisateur **que** si tu ne peux ni reproduire ni comprendre ce qui était attendu ; une
  seule série de questions, courtes, à choix.
- Rends une fiche : `"fiche_correction": {"symptome": "…", "reproduction": ["étape 1", "…"], "attendu": "…",
  "piste": "… ou null"}` et un `nom` court (« Corriger : … »).

## Correctif
- Commence par un test qui reproduit l'anomalie et **échoue**.
- Trouve la cause, corrige au plus près, sans refonte.
- Fais passer ce test et les tests existants ; écris dans ton rapport la cause, les fichiers touchés et la commande
  de test.

## Vérification
- Rejoue le scénario de la fiche et les tests ; joins une capture si le projet a un écran.
- Si l'anomalie revient ou si autre chose casse, dis-le : la tâche repart au correctif.
```

- [ ] **Step 4 : tests** — `py -3.12 -m unittest tests.test_orch_workflows -v` → PASS.

- [ ] **Step 5 : commit**

```bash
git add orchestrateur/workflows.py orchestrateur/consignes-correction.md tests/test_orch_workflows.py
git commit -m "Workflows : le workflow d'une correction, construit sans appel d'IA"
```

---

### Task 4 : le parcours d'une correction dans le moteur

**Files :**
- Modify : `orchestrateur/outil.py` (`cmd_organisation` : action `correction`)
- Modify : `moteur/regles.py` (`_sur_fonctionnalite`, nouvelle `_sur_correction`, `_matiere` étape `cadrage`,
  `_suite_cadrage`, `_appliquer_rapport` ligne ~3554)
- Test : `tests/test_moteur_correction.py` (nouveau)

**Interfaces :**
- Consumes : `workflows.de_correction`, `workflows.CONSIGNES_CORRECTION` (Task 3) ; `f["nature"]`, `f["concerne"]`
  (Task 2).
- Produces :
  - `lancer organisation {"action": "correction", "fonctionnalite": fid}` : écrit le workflow `w-<fid>` (via
    `mise_en_place.ecrire_organisation`, comme `_reprendre_le_workflow_de_creation`) et pose `genre`, `workflow` sur
    la fonctionnalité ; rend `{"ok": True, "workflow": "w-<fid>"}`.
  - rapport de cadrage d'une correction : `fiche_correction` ; à sa réception, la fonctionnalité passe en `serie`
    avec un seul élément `{"id": "correction", "nom": <nom>, "objectif": <attendu>}`.

- [ ] **Step 1 : tests qui échouent**

```python
"""Le parcours court d'une correction : ni genre, ni workflow proposé, ni cahier."""
import unittest

from moteur import regles
from tests.test_moteur_regles import Base


class TestCorrection(Base):
    def corriger(self, **plus):
        return self.traiter(type="fonctionnalite", texte="Le score ne se remet pas à zéro", nature="correction",
                            **plus)

    def test_aucun_jugement_de_genre_ni_de_workflow(self):
        d, actions = self.corriger()
        self.assertFalse(any(a[0] == "juger" for a in actions))
        f = self.fonc()
        self.assertEqual((f["nature"], f["workflow"], f["etape"]), ("correction", "w-f1", "cadrage"))
        self.assertEqual(self.decisions("organisation"), [])
        self.assertEqual(len(self.taches(etape="cadrage")), 1)

    def test_fiche_de_cadrage_lance_la_serie_d_un_seul_element(self):
        self.corriger()
        (t,) = self.taches(etape="cadrage")
        regles._suite_cadrage(self.projet, self.etat, t, {
            "nom": "Corriger : score", "fiche_correction": {"symptome": "reste à 12", "reproduction": ["perdre"],
                                                           "attendu": "revient à 0", "piste": None}})
        f = self.fonc()
        self.assertEqual(f["etape"], "serie")
        self.assertEqual([x["id"] for x in f["file"]], ["correction"])
        self.assertEqual(self.decisions("valider_cahier"), [])

    def test_la_fonctionnalite_concernee_est_dans_la_matiere(self):
        self.fonctionnalite(etape="serie")       # f1 : une fonctionnalité existante
        self.corriger(concerne="f1")
        (t,) = self.taches(etape="cadrage", fonctionnalite="f2")
        matiere = regles._matiere(self.projet, self.etat, t)
        self.assertIn("Fonctionnalité concernée", matiere)
        self.assertIn("fiche_correction", matiere)
        self.assertNotIn("cahier des charges", matiere)
```

(`self.decisions(genre)` : l'aide existe dans `tests/test_moteur_parcours.py` ; si elle est définie dans
`AvecParcours` et pas dans `Base`, la recopier dans la classe de test.)

- [ ] **Step 2 : lancer, constater l'échec**

Run : `py -3.12 -m unittest tests.test_moteur_correction -v` → FAIL (un jugement `classer_genre` est rendu).

- [ ] **Step 3 : implémenter**

`orchestrateur/outil.py`, dans `cmd_organisation`, avant le refus final :

```python
    if e.get("action") == "correction":
        return _workflow_de_correction(ctx, e)
```

```python
def _workflow_de_correction(ctx, e):
    """`{"action": "correction", "fonctionnalite"}` : le workflow d'une correction (`workflows.de_correction`), écrit
    sans service, agent ni brief nouveau, sans décision. Rôles : production et QA tirés des métiers du projet."""
    from installation.dossier import Echec
    from installation import mise_en_place
    fid, production = texte(e, "fonctionnalite"), texte(e, "role_production")
    qa = e.get("role_qa") or None          # les rôles viennent du moteur (`_role_production`, `_role_qa`)
    with ctx.suivi.transaction() as s:
        fonc = su.fonctionnalite(s, fid)
        if fonc is None or fonc.get("nature") != "correction":
            raise Refus(f"{fid} n'est pas une correction.")
        if fonc.get("workflow"):
            raise Refus(f"La fonctionnalité {fid} a déjà un workflow ({fonc['workflow']}).")
        w = wf.de_correction(ctx.f, fid, production, qa)
        try:
            mise_en_place.ecrire_organisation(ctx.f["chemin"], [dict(x) for x in ctx.f["services"]], w["flux"], [], {},
                                              workflow=w)
        except Echec as ex:
            raise Refus(str(ex))
        fonc["genre"], fonc["workflow"], fonc["maj"] = w["genre"], w["id"], su.maintenant()
    return {"ok": True, "workflow": w["id"]}
```

Vérifier que `ecrire_organisation` accepte un workflow qui a la clé `nature` (sinon
la retirer avant l'appel et la garder seulement sur la fonctionnalité).

`moteur/regles.py` :

```python
ROLES_QA = ("qa", "test", "testeur", "recette")


def _role_qa(projet):
    """Le rôle de vérification du projet s'il en a un (son id contient un mot de `ROLES_QA`), sinon None."""
    for m in _metiers_du_projet(_factory(projet)):
        if any(mot in str(m.get("role") or "").lower() for mot in ROLES_QA):
            return m["role"]
    return None


def _sur_correction(projet, demande, etat):
    """Une correction : ni classement de genre, ni workflow proposé ; son workflow est construit par le code, puis le
    cadrage court démarre."""
    fid = demande["fonctionnalite"]
    suite = {"demande": demande["id"], "fonctionnalite": fid}
    _nommer(projet, fid)
    lancer(projet, "organisation", {"action": "correction", "fonctionnalite": fid,
                                    "role_production": _role_production(projet), "role_qa": _role_qa(projet)})
    _dire(projet, fid, "C'est une correction : je cherche à reproduire l'anomalie avant de la corriger.")
    _terminer(projet, suite, "Correction reçue : le cadrage court commence.")
    return _repondre_cadrage(projet, etat, fid)
```

(`_metiers_du_projet(fac)` existe ligne ~1123 ; vérifier la forme des éléments qu'il rend avant d'écrire `_role_qa`.)

En tête de `_sur_fonctionnalite` :

```python
    if _fonc(projet, demande["fonctionnalite"]).get("nature") == "correction":
        return _sur_correction(projet, demande, etat)
```

`_matiere`, branche `etape == "cadrage"` : si `f.get("nature") == "correction"`, remplacer la consigne du cahier par :

```python
        if f.get("nature") == "correction":
            consignes_corr = wf.CONSIGNES_CORRECTION.read_text(encoding="utf-8")
            parties += ["C'est une **correction**, pas une nouvelle fonctionnalité.", consignes_corr,
                        "Discussion avec l'utilisateur :", _texte_discussion(f, projet=projet),
                        "Rends `fiche_correction` dès que tu peux reproduire et comprendre l'attendu ; sinon des "
                        "questions courtes à choix (`message.questions`, `attend: true`)."]
            if f.get("concerne"):
                c = _fonc(projet, f["concerne"])
                parties += [f"Fonctionnalité concernée : {c['nom']} ({c['id']})", "Son cahier : " + str(c.get("cahier")),
                            "Ses éléments : " + ", ".join(x["nom"] for x in c.get("file") or [])]
        else:
            ...la branche actuelle, inchangée...
```

`_appliquer_rapport` (~ligne 3554) : la tâche de cadrage reste ouverte tant qu'il n'y a pas de cahier ; l'élargir :
`if str(t.get("etape")) == "cadrage" and not (r.get("cahier") or r.get("fiche_correction")):`.

`_suite_cadrage` : après le bloc `nom`, avant le bloc `cahier` :

```python
    if r.get("fiche_correction") and _fonc(projet, fid).get("nature") == "correction":
        fiche = r["fiche_correction"]
        f = _fonc(projet, fid)
        lancer(projet, "fonctionnalite", {"id": fid, "cahier": {"maquette": [], "etapes": [
            "Symptôme : " + str(fiche.get("symptome") or ""),
            "Reproduction : " + " ; ".join(map(str, fiche.get("reproduction") or [])),
            "Attendu : " + str(fiche.get("attendu") or "")] + (["Piste : " + fiche["piste"]] if fiche.get("piste") else [])}})
        lancer(projet, "file", {"fonctionnalite": fid, "elements": [
            {"id": "correction", "nom": f["nom"], "objectif": str(fiche.get("attendu") or "")[:300]}]})
        lancer(projet, "fonctionnalite", {"id": fid, "etape": "serie", "methode": {"version": 1,
                                                                                    "validee_le": su.maintenant()}})
        _dire(projet, fid, "Fiche de correction écrite : le correctif commence.")
        return []
```

La fiche est rangée comme `cahier` (maquette vide, étapes = fiche) pour réutiliser l'affichage et le contrôle
existants (`_verifier_cahier` doit accepter une maquette vide : le vérifier, sinon lui permettre la liste vide quand
la fonctionnalité est une correction). La `methode` minimale est ce que `_avancer_serie` attend d'une fonctionnalité
en série (vérifier : si `methode` n'est pas lue, ne pas l'écrire). `su` : `from orchestrateur import suivi as su` est
déjà importé dans `regles.py` ? sinon utiliser l'horodatage déjà employé ligne ~549.

- [ ] **Step 4 : tests**

Run : `py -3.12 -m unittest tests.test_moteur_correction tests.test_moteur_parcours tests.test_moteur_regles -v`
Expected : PASS, et aucun test existant du parcours ne casse.

- [ ] **Step 5 : commit**

```bash
git add moteur/regles.py orchestrateur/outil.py tests/test_moteur_correction.py
git commit -m "Moteur : le parcours court d'une correction (fiche, un seul élément, série)"
```

---

### Task 5 : le jugement `repondre_question`

**Files :**
- Modify : `moteur/jugement.py` (`TYPES`, `LIBELLES`, `_VALIDEURS_AVEC_DOSSIER`, docstring des dossiers)
- Create : `moteur/consignes/repondre_question.md`
- Modify : `moteur/regles.py` (`_sur_question`, `_apres_repondre_question`, `_SUR`, `_APRES`)
- Test : `tests/test_questions.py`

**Interfaces :**
- Consumes : `lancer questions` (Task 1), demande `question` avec `fil` (Task 2).
- Produces :
  - `jugement.TYPES["repondre_question"] = "sonnet"`.
  - Réponse : `{"reponse": str, "sur": bool, "suggestion": null | {"nature": "fonctionnalite"|"correction",
    "texte": str, "concerne"?: fid}}`.
  - `regles._dossier_question(projet, fil) -> dict` (réutilisé par Task 6).
  - `regles._repondre_au_fil(projet, etat, fid_question, o, niveau) -> list` : écrit la réponse, marque le fil, rend
    `[a_lire(...)]` si `niveau == "documents"` et `not o["sur"]`.

- [ ] **Step 1 : tests qui échouent**

```python
from moteur import jugement, regles

REPONSE_SURE = {"reponse": "Le score repart de zéro à chaque niveau.", "sur": True, "suggestion": None}


class TestRepondreQuestion(Base):
    def test_valider(self):
        d = {"fonctionnalites": [{"id": "f1"}]}
        self.assertIsNone(jugement.valider("repondre_question", REPONSE_SURE, d))
        self.assertIsNone(jugement.valider("repondre_question", {**REPONSE_SURE, "suggestion": {
            "nature": "correction", "texte": "Le score…", "concerne": "f1"}}, d))
        for mauvais in ({"reponse": "", "sur": True, "suggestion": None},
                        {"reponse": "x", "sur": "oui", "suggestion": None},
                        {"reponse": "x", "sur": True, "suggestion": {"nature": "idee", "texte": "x"}},
                        {"reponse": "x", "sur": True, "suggestion": {"nature": "correction", "texte": "x",
                                                                    "concerne": "f9"}}):
            self.assertIsNotNone(jugement.valider("repondre_question", mauvais, d), mauvais)

    def test_question_jugee_puis_repondue(self):
        d, actions = self.traiter(type="question", texte="Comment est calculé le score ?")
        ((_, type_, dossier, suite),) = actions
        self.assertEqual(type_, "repondre_question")
        self.assertEqual(dossier["question"]["texte"], "Comment est calculé le score ?")
        self.assertIn("projet", dossier)
        suite_actions = regles.appliquer_jugement(self.projet, type_, jugement.Decision(objet=REPONSE_SURE), suite,
                                                  self.etat)
        self.assertEqual(suite_actions, [])
        (fil,) = self.ok("questions")["questions"]
        self.assertEqual((fil["etat"], fil["messages"][-1]["niveau"]), ("repondue", "documents"))
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_reponse_pas_sure_escalade_vers_la_lecture(self):
        d, ((_, type_, _, suite),) = self.traiter(type="question", texte="Que fait la fonction de sauvegarde ?")
        actions = regles.appliquer_jugement(self.projet, type_, jugement.Decision(objet={**REPONSE_SURE, "sur": False}),
                                            suite, self.etat)
        self.assertEqual([a[0] for a in actions], ["lire"])
        (fil,) = self.ok("questions")["questions"]
        self.assertEqual(fil["etat"], "en_lecture")
```

(Le constructeur réel de `jugement.Decision` : lire sa définition — `Decision(objet=…)` ou `Decision(o=…)` — et
l'utiliser tel quel. `self.statut(i)` vient de `Base`.)

- [ ] **Step 2 : lancer, constater l'échec** — `py -3.12 -m unittest tests.test_questions -v` → KeyError
  `repondre_question`.

- [ ] **Step 3 : implémenter**

`moteur/jugement.py` :

```python
TYPES["repondre_question"] = "sonnet"     # écrire dans le dict littéral, pas après coup
LIBELLES["repondre_question"] = "répondre à votre question"
NATURES_SUGGESTION = ("fonctionnalite", "correction")
LONGUEUR_REPONSE = 3500


def _valider_repondre_question(o, d):
    if not _texte(o.get("reponse")) or len(o["reponse"]) > LONGUEUR_REPONSE:
        return f"« reponse » : un texte non vide de {LONGUEUR_REPONSE} caractères au plus."
    if not isinstance(o.get("sur"), bool):
        return "« sur » doit être true ou false."
    s = o.get("suggestion")
    if s is None:
        return None
    if not isinstance(s, dict) or s.get("nature") not in NATURES_SUGGESTION or not _texte(s.get("texte")):
        return "« suggestion » : null, ou {nature (fonctionnalite | correction), texte, concerne?}."
    if len(s["texte"]) > LONGUEUR_REPONSE:
        return f"« suggestion.texte » tient en {LONGUEUR_REPONSE} caractères au plus."
    connues = {f.get("id") for f in d.get("fonctionnalites") or []}
    if s.get("concerne") is not None and s["concerne"] not in connues:
        return f"« suggestion.concerne » doit être une fonctionnalité du dossier ({', '.join(sorted(connues)) or 'aucune'})."
    return None
```

et l'ajouter à `_VALIDEURS_AVEC_DOSSIER`. Compléter la docstring du module :
`- repondre_question : projet (nom, description), genre, fonctionnalites ([{id, nom, nature, etape, cahier}]),
fonctionnalite (celle visée, cahier et éléments, ou null), regles_projet, fil (messages précédents), question (texte,
images), mots_interdits.`

`moteur/consignes/repondre_question.md` :

```markdown
Tu réponds à une question de l'utilisateur sur **son projet** : ce qu'il fait, comment il fonctionne, pourquoi il se
comporte ainsi. Tu n'as que le dossier (description, fonctionnalités, cahiers des charges, règles, fil de la
question) : tu ne lis pas le code.

Réponds en français clair, en markdown court (quelques phrases, une liste si utile). Ne cite jamais un mot de
`mots_interdits`.

- `sur` : true seulement si le dossier suffit à répondre exactement. Si la réponse dépend de la façon dont c'est
  codé (calcul, cas limite, ordre des opérations, fichier), `sur: false` et dis ce que tu sais déjà.
- `suggestion` : null en général. Si la question révèle un **manque** (« on ne peut pas… ») propose
  `{"nature": "fonctionnalite", "texte": "<la demande, écrite comme l'utilisateur l'écrirait>"}` ; si elle révèle un
  **comportement anormal** par rapport au cahier, `{"nature": "correction", "texte": "<symptôme, reproduction,
  attendu>", "concerne": "<id de la fonctionnalité>"}`.

Rends uniquement l'objet JSON : `{"reponse": "…", "sur": true|false, "suggestion": null|{…}}`.
```

`moteur/regles.py` :

```python
def _dossier_question(projet, fil):
    fac = _factory(projet)
    court = _etat(projet)
    question = fil["messages"][-1]
    dossier = {"projet": {"nom": fac["nom"], "description": fac["description"]}, "genre": _genre_du_projet(fac),
               "fonctionnalites": [{"id": f["id"], "nom": f["nom"], "nature": f.get("nature") or "fonctionnalite",
                                    "etape": f["etape"], "cahier": (_fonc(projet, f["id"]).get("cahier") or {}).get("etapes")}
                                   for f in court["fonctionnalites"]][:40],
               "fonctionnalite": None, "regles_projet": [x["texte"] for x in lancer(projet, "regles", {"action": "lister"}).get("regles", [])],
               "fil": [{"auteur": m["auteur"], "texte": m["texte"][:1500]} for m in fil["messages"][:-1]][-10:],
               "question": {"texte": question["texte"], "images": question.get("images") or []},
               "mots_interdits": fac["mots_interdits"]}
    if fil.get("fonctionnalite"):
        f = _fonc(projet, fil["fonctionnalite"])
        dossier["fonctionnalite"] = {"id": f["id"], "nom": f["nom"], "cahier": f.get("cahier"),
                                     "elements": [x["nom"] for x in f.get("file") or []]}
    return dossier


def _fil(projet, ident):
    return next(q for q in lancer(projet, "questions", {"action": "lister"})["questions"] if q["id"] == ident)


def _sur_question(projet, demande, etat):
    fil = _fil(projet, demande["fil"])
    return [a_juger("repondre_question", _dossier_question(projet, fil),
                    {"demande": demande["id"], "fonctionnalite": None, "fil": fil["id"]})]


def _repondre_au_fil(projet, etat, ctx, o, niveau, fichiers_lus=None):
    lancer(projet, "questions", {"action": "ajouter", "id": ctx["fil"], "auteur": "factory", "texte": o["reponse"],
                                 "niveau": niveau, "sur": o["sur"], "suggestion": o.get("suggestion"),
                                 **({"fichiers_lus": fichiers_lus} if fichiers_lus else {})})
    if niveau == "documents" and not o["sur"]:
        lancer(projet, "questions", {"action": "marquer", "id": ctx["fil"], "etat": "en_lecture"})
        _terminer(projet, ctx, "Première réponse d'après les documents ; je vérifie dans le code.")
        return [a_lire(ctx["fil"], ctx)]
    lancer(projet, "questions", {"action": "marquer", "id": ctx["fil"], "etat": "repondue"})
    _terminer(projet, ctx, "Réponse écrite dans le panneau Questions.")
    return []


def _apres_repondre_question(projet, o, ctx, etat):
    return _repondre_au_fil(projet, etat, ctx, o, "documents")
```

`a_lire` est défini à la Task 6 ; pour que cette tâche passe seule, l'écrire ici :

```python
def a_lire(fil, suite):
    """L'action asynchrone de l'agent lecteur (exécutée par la boucle dans un fil)."""
    return ("lire", fil, suite)
```

Ajouter `"question": _sur_question` à `_SUR` et `"repondre_question": _apres_repondre_question` à `_APRES`.
Une réponse de jugement ratée (question au Directeur) : dans `appliquer_jugement`, le cas `decision.question` d'un
`repondre_question` doit écrire dans le fil « Je n'ai pas pu répondre d'après les documents. » (`niveau: "documents"`,
`sur: false`) et marquer le fil `repondue`, **sans** poser de décision au Directeur : ajouter ce cas en tête
d'`appliquer_jugement` pour `type_ == "repondre_question"`, et un test.

- [ ] **Step 4 : tests** — `py -3.12 -m unittest tests.test_questions tests.test_moteur_jugement -v` → PASS (nom réel
  du test des jugements : `ls tests | grep jugement`).

- [ ] **Step 5 : commit**

```bash
git add moteur/jugement.py moteur/consignes/repondre_question.md moteur/regles.py tests/test_questions.py
git commit -m "Questions : la réponse d'après les documents (jugement repondre_question)"
```

---

### Task 6 : l'agent lecteur

**Files :**
- Create : `moteur/consignes/lire_pour_repondre.md`
- Modify : `moteur/regles.py` (`_sur_question_approfondir`, `appliquer_lecture`, `lecture_interrompue`)
- Modify : `moteur/boucle.py` (traitement de l'action `lire`, fil, file de retour, redémarrage)
- Test : `tests/test_questions.py`, `tests/test_moteur_boucle.py` (nom réel : `ls tests | grep boucle`)

**Interfaces :**
- Consumes : `a_lire`, `_dossier_question`, `_repondre_au_fil`, `_fil` (Task 5) ; `appel.appeler(consigne, dossier,
  modele, couche=, outils=, dossier_travail=)`.
- Produces :
  - `regles.OUTILS_LECTEUR = ("Read", "Grep", "Glob")`, `regles.MODELE_LECTEUR = "sonnet"`.
  - `regles.appliquer_lecture(projet, etat, suite, objet, usages) -> list` : valide `objet` avec
    `jugement.valider("repondre_question", objet, dossier)` + `fichiers_lus` facultatif ; écrit la réponse
    (`niveau: "code"`) ; une réponse invalide écrit « Je n'ai pas pu lire le code jusqu'au bout. ».
  - `regles.lecture_interrompue(projet)` : au démarrage du moteur, tout fil `en_lecture` reçoit « Lecture
    interrompue » et repasse `repondue`.

- [ ] **Step 1 : tests qui échouent**

```python
class TestLecteur(Base):
    def test_approfondir_rend_une_lecture(self):
        self.ok("questions", entree={"action": "ouvrir", "texte": "Q ?"})
        self.ok("questions", entree={"action": "ajouter", "id": "q1", "auteur": "factory", "texte": "R",
                                     "niveau": "documents", "sur": True})
        d, actions = self.traiter(type="question_approfondir", fil="q1")
        self.assertEqual([a[0] for a in actions], ["lire"])

    def test_appliquer_lecture(self):
        self.ok("questions", entree={"action": "ouvrir", "texte": "Q ?"})
        suite = {"demande": None, "fonctionnalite": None, "fil": "q1"}
        regles.appliquer_lecture(self.projet, self.etat, suite,
                                 {**REPONSE_SURE, "fichiers_lus": ["jeu/score.py:12"]}, [])
        dernier = self.ok("questions")["questions"][0]["messages"][-1]
        self.assertEqual((dernier["niveau"], dernier["fichiers_lus"]), ("code", ["jeu/score.py:12"]))

    def test_lecture_interrompue(self):
        self.ok("questions", entree={"action": "ouvrir", "texte": "Q ?"})
        self.ok("questions", entree={"action": "marquer", "id": "q1", "etat": "en_lecture"})
        regles.lecture_interrompue(self.projet)
        fil = self.ok("questions")["questions"][0]
        self.assertEqual(fil["etat"], "repondue")
        self.assertIn("Lecture interrompue", fil["messages"][-1]["texte"])
```

Test de boucle (dans le fichier de tests de la boucle, sur le modèle d'un test qui simule `appeler`) :

```python
    def test_lecture_avec_les_seuls_outils_de_lecture(self):
        vus = []
        def appeler(consigne, dossier, modele, **kw):
            vus.append((modele, kw.get("outils"), kw.get("dossier_travail")))
            return <le résultat simulé au format que rend appel.appeler, réponse JSON REPONSE_SURE>
        # déposer une question, la faire juger « sur: false » (appeler rend d'abord {…, "sur": false}), puis tourner
        # la boucle jusqu'à ce que le fil soit « repondue »
        self.assertEqual(vus[-1][:2], ("sonnet", ["Read", "Grep", "Glob"]))
```

(Écrire ce test en recopiant la mise en place exacte d'un test existant de `boucle.py` qui simule `appeler` pour un
jugement — `grep -n "appeler=" tests/test_moteur_boucle*.py` — sans `sleep` : appeler la méthode de passage et
vider la file des fils comme le fait ce test.)

- [ ] **Step 2 : lancer, constater l'échec.**

- [ ] **Step 3 : implémenter**

`moteur/consignes/lire_pour_repondre.md` :

```markdown
Tu réponds à une question de l'utilisateur sur son projet en **lisant son code**. Tu es dans le dossier du projet ;
tu n'as que Read, Grep et Glob : tu ne modifies rien et tu ne lances rien.

Le message te donne le dossier (description, fonctionnalités, fil) et la première réponse, faite sans le code.
Cherche ce qui répond exactement (Grep d'abord, puis Read des passages utiles). Ne lis pas tout le dépôt.

Rends uniquement l'objet JSON : `{"reponse": "…", "sur": true|false, "suggestion": null|{…},
"fichiers_lus": ["chemin:ligne", …]}`. Même règles de `suggestion` que la première réponse. Français clair, markdown
court ; cite les fichiers en `chemin:ligne`.
```

`moteur/regles.py` :

```python
OUTILS_LECTEUR = ("Read", "Grep", "Glob")
MODELE_LECTEUR = "sonnet"
CONSIGNE_LECTEUR = Path(__file__).resolve().parent / "consignes" / "lire_pour_repondre.md"


def _sur_question_approfondir(projet, demande, etat):
    lancer(projet, "questions", {"action": "marquer", "id": demande["fil"], "etat": "en_lecture"})
    _terminer(projet, {"demande": demande["id"]}, "Je cherche dans le code.")
    return [a_lire(demande["fil"], {"demande": None, "fonctionnalite": None, "fil": demande["fil"]})]


def dossier_de_lecture(projet, fil_id):
    fil = _fil(projet, fil_id)
    return {**_dossier_question(projet, fil),
            "premiere_reponse": next((m["texte"] for m in reversed(fil["messages"]) if m["auteur"] == "factory"), None)}


def appliquer_lecture(projet, etat, suite, objet, usages):
    if not isinstance(objet, dict):
        objet = None
    erreur = jugement.valider("repondre_question", objet, dossier_de_lecture(projet, suite["fil"])) if objet else "vide"
    fichiers = objet.get("fichiers_lus") if objet and isinstance(objet.get("fichiers_lus"), list) else None
    if erreur:
        objet = {"reponse": "Je n'ai pas pu lire le code jusqu'au bout.", "sur": False, "suggestion": None}
    return _repondre_au_fil(projet, etat, suite, objet, "code", fichiers)


def lecture_interrompue(projet):
    for q in lancer(projet, "questions", {"action": "lister"})["questions"]:
        if q["etat"] == "en_lecture":
            lancer(projet, "questions", {"action": "ajouter", "id": q["id"], "auteur": "factory",
                                         "texte": "Lecture interrompue (le moteur a redémarré). « Chercher dans le "
                                                  "code » la relance.", "niveau": "documents", "sur": False})
            lancer(projet, "questions", {"action": "marquer", "id": q["id"], "etat": "repondue"})
```

`_repondre_au_fil` avec `suite["demande"] is None` : `_terminer` ne doit rien faire (vérifier que `_terminer` accepte
`demande: None`, sinon le garder par `if ctx.get("demande")`). Ajouter `"question_approfondir":
_sur_question_approfondir` à `_SUR`.

`moteur/boucle.py` :
- au premier passage d'un projet (là où les tâches orphelines sont relancées), appeler
  `regles.lecture_interrompue(projet)` ;
- dans la distribution des actions (ligne ~566, `elif action[0] == "agent":`), ajouter
  `elif action[0] == "lire": self._lire(projet, action)` ;
- la méthode, sur le modèle de l'attente d'un agent dans un fil (une `queue.Queue` lue au passage suivant) :

```python
    def _lire(self, projet, action):
        _, fil, suite = action
        dossier = regles.dossier_de_lecture(projet, fil)
        consigne = regles.CONSIGNE_LECTEUR.read_text(encoding="utf-8")

        def travail():
            try:
                r = self.appeler(consigne, json.dumps(dossier, ensure_ascii=False), regles.MODELE_LECTEUR,
                                 couche=projet.couche, outils=list(regles.OUTILS_LECTEUR),
                                 dossier_travail=str(projet.factory.parent.parent))
                objet, usages = jugement.extraire_json(r.texte), r.usages
            except Exception as ex:          # noqa: BLE001 — une erreur n'arrête jamais la boucle
                objet, usages = None, []
                self.journal(f"Lecture du code ratée ({fil}) : {ex}")
            self.lectures.put((projet, suite, objet, usages))

        threading.Thread(target=travail, daemon=True).start()
```

  (Lire `appel.appeler` et ce qu'il rend — attribut texte et usages — et le dossier du projet tel que l'agent de
  production le reçoit, `dossier_projet` dans `agents.executer_agent`, et reprendre exactement ces noms.)
- dans `__init__`, `self.lectures = queue.Queue()` ; à chaque passage, à l'étape « retours des agents terminés » :

```python
        while True:
            try:
                projet_l, suite, objet, usages = self.lectures.get_nowait()
            except queue.Empty:
                break
            self._noter_usages(projet_l, usages, AGENT_ORCHESTRATEUR, ETAPE_QUESTIONS)
            file += regles.appliquer_lecture(projet_l, self._etat(projet_l), suite, objet, usages)
```

  avec `ETAPE_QUESTIONS = "questions"` à côté de `ETAPE_ORCHESTRATION` (la facturation montre ainsi une ligne
  « Questions »). Le jugement `repondre_question` est noté de la même façon : dans `_juger`, si `type_ ==
  "repondre_question"`, passer `ETAPE_QUESTIONS` au lieu de `ETAPE_ORCHESTRATION`.

- [ ] **Step 4 : tests** — `py -3.12 -m unittest tests.test_questions <tests de la boucle> -v` → PASS.

- [ ] **Step 5 : commit**

```bash
git add moteur/consignes/lire_pour_repondre.md moteur/regles.py moteur/boucle.py tests/
git commit -m "Questions : l'agent lecteur (Read, Grep, Glob) en escalade ou sur « Chercher dans le code »"
```

---

### Task 7 : les boutons et le mode correction du bureau

**Files :**
- Modify : `bureau/web/ui/barre.js` (ligne ~76), `bureau/web/ui/panneaux.js` (ligne ~328 et `ouvrirPanneau`),
  `bureau/web/ui/fonctionnalite.js` (`contenuFonctionnalite` ~1195, liste des fonctionnalités ~1375),
  `bureau/web/style.css` (badge)
- Test : `tests/test_bureau_ui.py` ou le test JS existant des panneaux (`ls tests | grep -i "ui\|web\|js"`)

**Interfaces :**
- Produces : `barre.boutonCorrection`, `barre.boutonQuestion` ; `ouvrirPanneau("fonctionnalite", null, {nature,
  texte?, concerne?})` ; `ouvrirPanneau("questions", null)` (le contenu vient de la Task 8).

- [ ] **Step 1 : test qui échoue**

Si le dépôt a des tests du bureau en Python qui lisent les modules JS (`grep -rn "barre.js" tests/`), ajouter :

```python
    def test_boutons_correction_et_question(self):
        js = (UI / "barre.js").read_text(encoding="utf-8")
        self.assertIn("+ Nouvelle correction", js)
        self.assertIn("? Une question", js)
        self.assertIn("for (const b of [boutonNouvelle, boutonCorrection, boutonQuestion, boutonFonctions])", js)
```

sinon passer directement à l'essai manuel (Task 9) pour cette partie, et le dire dans le commit.

- [ ] **Step 2 : implémenter**

`barre.js` :

```js
  const boutonNouvelle = el("button", "bouton-barre", "+ Nouvelle fonctionnalité");
  const boutonCorrection = el("button", "bouton-barre", "+ Nouvelle correction");
  const boutonQuestion = el("button", "bouton-barre", "? Une question");
  const boutonFonctions = el("button", "bouton-barre", "Fonctionnalités");
  for (const b of [boutonNouvelle, boutonCorrection, boutonQuestion, boutonFonctions]) { b.type = "button"; b.hidden = true; }
```

ajouter `boutonCorrection, boutonQuestion` après `boutonNouvelle` dans `entete.append(…)`, dans l'objet rendu par la
barre, et partout où `boutonNouvelle.hidden` est mis à jour (`grep -n "boutonNouvelle" bureau/web/ui/*.js`) : même
valeur pour les deux nouveaux.

`panneaux.js` :

```js
  barre.boutonNouvelle.addEventListener("click", () => { nouvelle.envoi = null; nouvelle.nature = "fonctionnalite"; ouvrirPanneau("fonctionnalite", null); });
  barre.boutonCorrection.addEventListener("click", () => { nouvelle.envoi = null; nouvelle.nature = "correction"; ouvrirPanneau("fonctionnalite", null); });
  barre.boutonQuestion.addEventListener("click", () => ouvrirPanneau("questions", null));
```

et exposer `api.nouvelle(nature, texte, concerne)` qui fait `nouvelle.envoi = null; nouvelle.nature = nature;
nouvelle.brouillon = {texte, concerne}; ouvrirPanneau("fonctionnalite", null)` (utilisé par la Task 8). `nouvelle`
est l'objet déjà passé au contexte du panneau (`ctx.nouvelle`).

`fonctionnalite.js`, `contenuFonctionnalite` :

```js
  const correction = f ? f.nature === "correction" : ctx.nouvelle.nature === "correction";
  contenu.append(el("h2", "", f ? f.nom : (correction ? "Nouvelle correction" : "Nouvelle fonctionnalité")));
  if (f && correction) contenu.append(el("span", "badge-correction", "Correction"));
  ...
  } else if (correction) {
    contenu.append(el("p", "note", "Décrivez l'anomalie : ce qui se passe, comment la reproduire, ce que vous attendiez. Joignez une capture si possible."));
  } else {
```

Dans la zone d'envoi d'une discussion neuve : préremplir `zone.value` avec `ctx.nouvelle.brouillon?.texte` (puis
`ctx.nouvelle.brouillon = null`) ; en mode correction, ajouter une liste `<select>` « Fonctionnalité concernée
(facultatif) » alimentée par `e.fonctionnalites` (hors `f.nature === "correction" && f.etape === "terminee"`),
présélectionnée sur `brouillon.concerne` ; la demande envoyée devient
`{type: "fonctionnalite", texte, images, nature: "correction", concerne: select.value || undefined}` (chercher
l'endroit où la demande `{type: "fonctionnalite", …}` est construite : `grep -n 'type: "fonctionnalite"'
bureau/web/ui/*.js`).

Liste des fonctionnalités (~1375) : devant le nom, `el("span", "badge-correction", "Correction")` quand
`f.nature === "correction"`. `style.css` :

```css
.badge-correction { display: inline-block; margin-left: .5em; padding: 0 .5em; border-radius: .6em;
  font-size: .8em; background: var(--alerte-fond, #fde8ec); color: var(--alerte, #b3263e); }
```

(reprendre les variables de couleur déjà définies dans `style.css` pour une alerte, plutôt que ces valeurs de repli).

- [ ] **Step 3 : vérifier** — tests du bureau s'il y en a ; `node --check bureau/web/ui/barre.js` (et les autres
  fichiers touchés) si `node` est présent.

- [ ] **Step 4 : commit**

```bash
git add bureau/web/ui/barre.js bureau/web/ui/panneaux.js bureau/web/ui/fonctionnalite.js bureau/web/style.css tests/
git commit -m "Bureau : boutons « + Nouvelle correction » et « ? Une question », mode correction du panneau"
```

---

### Task 8 : le panneau « Questions »

**Files :**
- Create : `bureau/web/ui/questions.js`
- Modify : `bureau/web/ui/panneaux.js` (type de panneau `questions` dans `ouvrirPanneau` et `signature`)
- Modify : `bureau/web/style.css`

**Interfaces :**
- Consumes : `e.questions` du relevé (Task 1) ; demandes `question`, `question_approfondir` (Task 2) ; `api.nouvelle`
  (Task 7) ; `rendreMarkdown` de `markdown.js` (nom réel : `grep -n "^export" bureau/web/ui/markdown.js`) ;
  `creerAccuses` (accusé de réception, comme dans `fonctionnalite.js`) ; l'estimation de coût d'un appel Sonnet
  (`grep -n "^export" bureau/web/ui/conso.js bureau/web/ui/abonnement.js`).
- Produces : `export function contenuQuestions(ctx, contenu)`.

- [ ] **Step 1 : écrire `questions.js`**

```js
// Le panneau « Questions » : poser une question sur le projet, lire les réponses (d'après les documents, puis
// d'après le code), relancer un fil, ouvrir une correction ou une fonctionnalité préremplie.
import {el} from "./texte.js";              // vérifier le module qui exporte `el`
import {rendreMarkdown} from "./markdown.js";

const NIVEAUX = {documents: "D'après les documents", code: "D'après le code"};

export function contenuQuestions(ctx, contenu) {
  const e = ctx.etat;
  contenu.append(el("h2", "", "Questions sur le projet"));
  contenu.append(saisie(ctx, null));
  const fils = [...(e.questions || [])].reverse();
  if (!fils.length) contenu.append(el("p", "note", "Aucune question pour l'instant."));
  for (const q of fils) contenu.append(fil(ctx, q));
}

function saisie(ctx, q) {
  const bloc = el("form", "question-saisie");
  const zone = el("textarea", "");
  zone.placeholder = q ? "Question de suivi…" : "Votre question sur le projet, son fonctionnement…";
  zone.dataset.saisie = "1";
  bloc.append(zone);
  let apropos = null;
  if (!q) {
    apropos = el("select", "");
    apropos.append(new Option("À propos de : tout le projet", ""));
    for (const f of ctx.etat.fonctionnalites || []) apropos.append(new Option(f.nom, f.id));
    bloc.append(apropos);
  }
  const envoyer = el("button", "bouton", "Envoyer");
  envoyer.type = "submit";
  bloc.append(envoyer);
  bloc.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const texte = zone.value.trim();
    if (!texte) return;
    const demande = {type: "question", texte};
    if (q) demande.fil = q.id;
    else if (apropos.value) demande.fonctionnalite = apropos.value;
    if (await ctx.demander(demande, envoyer)) zone.value = "";
  });
  return bloc;
}

function fil(ctx, q) {
  const bloc = el("section", "question-fil");
  for (const m of q.messages) {
    const p = el("div", "question-message " + m.auteur);
    if (m.auteur === "factory") {
      p.append(el("span", "question-niveau", NIVEAUX[m.niveau] || ""));
      p.append(rendreMarkdown(m.texte));
      if (m.fichiers_lus?.length) p.append(el("p", "note", "Fichiers lus : " + m.fichiers_lus.join(", ")));
    } else {
      p.textContent = m.texte;
    }
    bloc.append(p);
  }
  if (q.etat === "en_cours") bloc.append(el("p", "ecrit actif", "Reçu, en cours de traitement…"));
  if (q.etat === "en_lecture") bloc.append(el("p", "ecrit actif", "Lecture du code en cours…"));
  const dernier = q.messages[q.messages.length - 1];
  if (q.etat === "repondue" && dernier.auteur === "factory") {
    const actions = el("div", "question-actions");
    if (dernier.niveau === "documents") {
      const b = el("button", "bouton", "Chercher dans le code");
      b.title = ctx.coutLecture ? ctx.coutLecture() : "";      // coût estimé et part d'abonnement
      b.addEventListener("click", () => ctx.demander({type: "question_approfondir", fil: q.id}, b));
      actions.append(b);
    }
    const s = dernier.suggestion;
    if (s) {
      const b = el("button", "bouton", s.nature === "correction" ? "Ouvrir une correction" : "Ouvrir une fonctionnalité");
      b.addEventListener("click", () => ctx.nouvelle(s.nature, s.texte, s.concerne));
      actions.append(b);
    }
    const suivi = el("button", "bouton-lien", "Poser une question de suivi");
    suivi.addEventListener("click", () => { suivi.replaceWith(saisie(ctx, q)); });
    actions.append(suivi);
    bloc.append(actions);
  }
  return bloc;
}
```

Corriger les imports et noms (`el`, `rendreMarkdown`, `ctx.demander`) d'après les modules réels : lire l'en-tête
d'import de `fonctionnalite.js` et reprendre exactement ses imports et la façon dont il envoie une demande.

- [ ] **Step 2 : brancher dans `panneaux.js`**

Dans `ouvrirPanneau` (le `switch`/les `if` par type), ajouter le type `questions` qui appelle
`contenuQuestions({...ctxPanneau, nouvelle: api.nouvelle, demander, coutLecture}, contenu)` ; dans `signature(type,
id, e)`, pour `questions` : `JSON.stringify((e.questions || []).map((q) => [q.id, q.etat, q.messages.length]))` pour que
le panneau se redessine à chaque nouvelle réponse (et pas pendant la saisie, déjà géré par `data-saisie`).
`coutLecture` : une phrase « ≈ x € · ≈ y % semaine » calculée avec les fonctions de prix existantes pour un appel
Sonnet moyen (prendre la même estimation que celle affichée pour un jugement, `grep -n "estim" bureau/web/ui/*.js`).

- [ ] **Step 3 : style**

```css
.question-saisie { display: grid; gap: .5em; margin-bottom: 1em; }
.question-fil { border-top: 1px solid var(--trait, #ddd); padding: .75em 0; }
.question-message.utilisateur { font-weight: 600; }
.question-message.factory { margin: .4em 0 .4em 1em; }
.question-niveau { display: block; font-size: .8em; opacity: .7; }
.question-actions { display: flex; flex-wrap: wrap; gap: .5em; }
```

(reprendre les variables de couleur et d'espacement de `style.css`).

- [ ] **Step 4 : vérifier** — `node --check bureau/web/ui/questions.js bureau/web/ui/panneaux.js` si `node` est
  présent ; sinon l'essai de la Task 9 sert de vérification.

- [ ] **Step 5 : commit**

```bash
git add bureau/web/ui/questions.js bureau/web/ui/panneaux.js bureau/web/style.css
git commit -m "Bureau : le panneau « Questions » (fils, suivi, Chercher dans le code, brouillon de correction)"
```

---

### Task 9 : documentation, essai sur la démo, poussée

**Files :**
- Modify : `README.md` (section « Fonctionnalités »), `docs/avancement.md`, `docs/releve.md`
- Modify : `exemples/demo/actions.py` si la démo doit accepter `question` / `question_approfondir` (la démo répond
  par une réponse fixe : `grep -n "fonctionnalite" exemples/demo/actions.py`)

- [ ] **Step 1 : documentation**

`README.md`, après la ligne « Parcours d'une fonctionnalité » :

```markdown
- **Nouvelle correction** : « + Nouvelle correction » signale une anomalie ; parcours court sans genre ni cahier :
  cadrage court (fiche de correction), correctif avec test de non-régression, vérification, validation du Directeur.
- **Une question** : « ? Une question » répond sur le projet et son fonctionnement, d'abord d'après les documents, puis
  en lisant le code si besoin (agent en lecture seule) ; les fils sont gardés, et une réponse peut ouvrir une
  correction ou une fonctionnalité préremplie.
```

`docs/releve.md` : `questions` (forme du fil), `nature` et `concerne` d'une fonctionnalité. `docs/avancement.md` : une
entrée datée 2026-11-16.

- [ ] **Step 2 : toute la suite de tests**

Run : `py -3.12 -m unittest discover -s tests -v`
Expected : PASS (aucun test existant cassé).

- [ ] **Step 3 : essai sur la démo**

Copier `exemples/` dans un dossier temporaire, puis
`py -3.12 lancer.py serveur --bureau <copie>/bureau.json` et ouvrir `http://127.0.0.1:8770/`. Vérifier :
1. les trois boutons apparaissent ensemble dans la barre ;
2. « + Nouvelle correction » ouvre « Nouvelle correction », avec la liste « Fonctionnalité concernée » ; l'envoi crée
   une fonctionnalité au badge « Correction » ;
3. « ? Une question » ouvre le panneau ; une question envoyée montre l'accusé, puis la réponse de la démo ;
4. une réponse avec suggestion ouvre le formulaire de correction prérempli, **sans rien envoyer**.

- [ ] **Step 4 : commit et poussée**

```bash
git add README.md docs/avancement.md docs/releve.md exemples/demo/actions.py
git commit -m "Documentation : Nouvelle correction et Une question"
git fetch origin
git rebase origin/main
git push origin main
```
