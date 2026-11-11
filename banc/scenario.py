"""Le scénario du banc d'essai : la discussion d'un essai, rejouable.

Format (`version: 1`) :
    {"version": 1,
     "projet": {"factory": {...}, "fiches": {"nom.md": texte}, "briefs": {rôle: texte}, "reglages": {...}},
     "gestes": [{"apres": "attente_utilisateur" | "immediat", "demande": {...}}],
     "rapports": [{"etape", "role", "rang", "texte", "fichiers": [{"chemin", "contenu_base64"}], "usage": Usage,
                   "rapport"?: {rapport structuré}}],
     "attendu": [textes]}

- `projet` : une factory minimale, matérialisée dans un dossier du banc (`Scenario.materialiser`).
- `gestes` : ce que fait l'utilisateur, dans l'ordre. Un geste « attente_utilisateur » n'est donné que quand le moteur
  n'a plus rien à faire seul (aucune tâche active ni en attente de départ) ; « immediat » dès que le précédent est donné.
- `rapports` : les rapports réels des agents de l'essai, rangés par (étape, rôle, rang de l'élément dans la file). Une
  étape : `cadrage`, `prototype`, `flux:<id>`, `relecture` ou `correction`. Plusieurs rapports de même clé sont rendus
  dans l'ordre (trois réponses de cadrage, deux relecteurs…). `usage` : l'usage réel de l'agent
  (`modele, entree, sortie, cache_lecture, cache_ecriture`) ; sans `rapport`, le rapport rendu est `{"statut": "fait",
  "message": {"texte": texte}}`.
- `attendu` : le résultat attendu, pour le rapport du banc (cocher ce que le passage a produit).

Un scénario d'un essai réel se construit par `banc.construire` et se range **hors du dépôt**. Seul le scénario
synthétique (`banc/exemples/synthetique.json`) est dans le dépôt.
"""
import json
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
GESTES = ("attente_utilisateur", "immediat")
COMPTEURS = ("entree", "sortie", "cache_lecture", "cache_ecriture")
_ETAPE = re.compile(r"^(cadrage|prototype|relecture|correction|retour|demande|flux:[a-z0-9-]+)\Z")
_FICHE = re.compile(r"^[A-Za-z0-9_.-]+\.md\Z")


class ScenarioInvalide(Exception):
    """Le fichier de scénario n'est pas lisible ou ne suit pas le format."""


def _texte(v):
    return isinstance(v, str) and v.strip() != ""


def _entier(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def verifier(d):
    """Les erreurs du scénario `d` (une liste de textes) ; vide s'il est valide."""
    if not isinstance(d, dict):
        return ["Le scénario doit être un objet JSON."]
    e = []
    if d.get("version") != 1:
        e.append("« version » doit valoir 1.")
    p = d.get("projet")
    if not (isinstance(p, dict) and isinstance(p.get("factory"), dict) and isinstance(p.get("fiches"), dict)
            and p["fiches"] and all(_FICHE.match(k) and _texte(v) for k, v in p["fiches"].items())):
        e.append("« projet » demande « factory » (objet) et « fiches » ({nom.md: texte}).")
    elif not (isinstance(p.get("briefs", {}), dict) and isinstance(p.get("reglages", {}), dict)):
        e.append("« projet.briefs » et « projet.reglages » sont des objets.")
    gestes = d.get("gestes")
    if not isinstance(gestes, list):
        e.append("« gestes » doit être une liste.")
    else:
        for k, g in enumerate(gestes, 1):
            if not (isinstance(g, dict) and g.get("apres") in GESTES and isinstance(g.get("demande"), dict)
                    and _texte(g["demande"].get("type"))):
                e.append(f"Geste {k} : « apres » ({', '.join(GESTES)}) et « demande » (avec un « type ») sont obligatoires.")
    rapports = d.get("rapports")
    if not isinstance(rapports, list):
        e.append("« rapports » doit être une liste.")
    else:
        for k, r in enumerate(rapports, 1):
            if not (isinstance(r, dict) and _texte(r.get("etape")) and _ETAPE.match(r["etape"]) and _texte(r.get("role"))
                    and _entier(r.get("rang")) and isinstance(r.get("texte"), str)):
                e.append(f"Rapport {k} : « etape », « role », « rang » (entier) et « texte » sont obligatoires.")
                continue
            if not (isinstance(r.get("fichiers", []), list)
                    and all(isinstance(f, dict) and _texte(f.get("chemin")) and isinstance(f.get("contenu_base64"), str)
                            for f in r.get("fichiers", []))):
                e.append(f"Rapport {k} : « fichiers » est une liste de {{chemin, contenu_base64}}.")
            u = r.get("usage")
            if not (isinstance(u, dict) and _texte(u.get("modele")) and all(_entier(u.get(c)) for c in COMPTEURS)):
                e.append(f"Rapport {k} : « usage » demande « modele » et les compteurs {', '.join(COMPTEURS)}.")
            if r.get("rapport") is not None and not isinstance(r["rapport"], dict):
                e.append(f"Rapport {k} : « rapport » est un objet.")
    attendu = d.get("attendu")
    if not (isinstance(attendu, list) and all(_texte(x) for x in attendu)):
        e.append("« attendu » doit être une liste de textes.")
    return e


class Scenario:
    def __init__(self, donnees):
        erreurs = verifier(donnees)
        if erreurs:
            raise ScenarioInvalide(" ".join(erreurs))
        self.donnees = donnees
        self.projet = donnees["projet"]
        self.gestes = list(donnees["gestes"])
        self.rapports = list(donnees["rapports"])
        self.attendu = list(donnees["attendu"])
        self.suivant = 0       # le prochain geste à donner

    @property
    def restants(self):
        return len(self.gestes) - self.suivant

    def prochain_geste(self, etat):
        """Le geste suivant s'il est donnable (rendu une seule fois), sinon `None`. `etat` : le résultat de `etat`."""
        if self.suivant >= len(self.gestes):
            return None
        g = self.gestes[self.suivant]
        if g["apres"] == "attente_utilisateur" and not attend_l_utilisateur(etat):
            return None
        self.suivant += 1
        return json.loads(json.dumps(g["demande"]))

    def materialiser(self, dossier):
        """Écrit la factory minimale du scénario dans `dossier` (celui du banc, pas un projet) et rend le chemin du
        fichier de factory."""
        dossier = Path(dossier)
        (dossier / "fiches" / "briefs").mkdir(parents=True, exist_ok=True)
        for nom, texte in self.projet["fiches"].items():
            (dossier / "fiches" / nom).write_text(texte, encoding="utf-8")
        for role, texte in (self.projet.get("briefs") or {}).items():
            (dossier / "fiches" / "briefs" / f"{role}.md").write_text(texte, encoding="utf-8")
        reglages = {"images": {"racines": ["pieces"]}, **(self.projet.get("reglages") or {})}
        (dossier / "reglages.json").write_text(json.dumps(reglages, ensure_ascii=False), encoding="utf-8")
        factory = {"skill": str(RACINE), "genre": None, "mots_interdits": [], "reglages": "reglages.json",
                   "memoire": "memoire", **self.projet["factory"]}
        chemin = dossier / "factory.json"
        chemin.write_text(json.dumps(factory, ensure_ascii=False), encoding="utf-8")
        return chemin


def attend_l_utilisateur(etat):
    """Vrai quand le moteur n'a plus rien à faire seul : aucune tâche active ni en attente de départ (jamais prise, pas
    faite, pas bloquée)."""
    for t in etat.get("taches") or []:
        if t.get("active"):
            return False
        if t.get("colonne") != "fait" and not t.get("bloquee") and not t.get("debut") and not isinstance(t.get("lot"), dict):
            return False
    return True


def charger(chemin):
    chemin = Path(chemin)
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise ScenarioInvalide(f"Scénario illisible ({chemin}) : {e}")
    return Scenario(donnees)
