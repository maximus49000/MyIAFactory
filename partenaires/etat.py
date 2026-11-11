"""Les connexions, quotas, limites et règles des partenaires : propres à la machine, communes à tous les projets.

Le fichier vit hors de tout dépôt (`~/MyIAFactory/partenaires.json`). Il ne contient **jamais** une valeur de clé :
seulement l'état de chaque connexion, le dernier quota lu avec sa date, les limites atteintes et les règles d'usage
que l'utilisateur a fixées. Écriture atomique sous verrou (le même mécanisme que le suivi).
"""
import datetime
from pathlib import Path

from orchestrateur import suivi as su

ETATS = ("connecte", "declare", "non_connecte")
SECTIONS = ("connexions", "quotas", "limites", "regles", "lectures")
REGLE_TRIPO = ("Si plusieurs éléments sont nécessaires, les générer au maximum en un seul prompt, "
               "sauf besoin de détail très précis ou d'animation.")
TEXTE_REGLE_MAX = 500
DUREE_LIMITE = datetime.timedelta(hours=24)   # une limite sans nouveau relevé tombe d'elle-même au bout d'un jour


def chemin_par_defaut():
    from installation.dossier import racine
    return racine() / "partenaires.json"


def vide(aujourdhui=None):
    """L'état d'un fichier qui n'existe pas encore : la règle de départ de Tripo est proposée (une seule fois :
    dès que le fichier est écrit, ce qu'il contient fait foi)."""
    jour = aujourdhui or datetime.date.today().isoformat()
    return {"version": 1, "connexions": {}, "quotas": {}, "limites": {}, "lectures": {},
            "regles": {"tripo": [{"id": "r1", "texte": REGLE_TRIPO, "cree_le": jour}]}}


class Etat(su.Suivi):
    """`lire()` et `transaction()` comme le suivi, sur le fichier des partenaires."""

    def __init__(self, chemin=None):
        super().__init__(chemin or chemin_par_defaut())

    def lire(self):
        import json
        if not self.chemin.exists():
            return vide()
        lu = json.loads(self.chemin.read_text(encoding="utf-8-sig"))
        d = {"version": 1}
        for s in SECTIONS:
            v = lu.get(s) if isinstance(lu, dict) else None
            d[s] = v if isinstance(v, dict) else {}
        return d


def maintenant():
    return su.maintenant()


def limite_active(lim, instant=None):
    """Vrai si la limite notée court encore (moins d'un jour, et pas levée par un relevé)."""
    if not isinstance(lim, dict):
        return False
    try:
        depuis = datetime.datetime.fromisoformat(lim.get("depuis"))
    except (TypeError, ValueError):
        return True   # une limite sans date lisible est tenue : on ne dépense pas sur un doute
    instant = instant or datetime.datetime.now().astimezone()
    if depuis.tzinfo is None:
        depuis = depuis.astimezone()
    return instant - depuis < DUREE_LIMITE


def regle(d, partenaire, operation, id_=None, texte=None, quand=None):
    """Ajoute, modifie ou supprime une règle d'usage. Rend la règle touchée. Lève ValueError sur un refus."""
    quand = quand or maintenant()
    regles = d["regles"].setdefault(partenaire, [])
    if operation == "ajouter":
        texte = _texte_regle(texte)
        n = max([int(r["id"][1:]) for r in regles if str(r.get("id", ""))[1:].isdigit()] or [0]) + 1
        r = {"id": f"r{n}", "texte": texte, "cree_le": quand}
        regles.append(r)
        return r
    r = next((x for x in regles if x.get("id") == id_), None)
    if r is None:
        raise ValueError(f"Règle inconnue « {id_} » pour {partenaire}.")
    if operation == "modifier":
        r["texte"], r["modifie_le"] = _texte_regle(texte), quand
    elif operation == "supprimer":
        regles.remove(r)
    else:
        raise ValueError("« operation » doit valoir ajouter, modifier ou supprimer.")
    if not regles:
        d["regles"][partenaire] = []   # garder la clé vide : la règle de départ ne revient pas
    return r


def _texte_regle(texte):
    if not isinstance(texte, str) or not texte.strip():
        raise ValueError("« texte » est obligatoire (la règle, en clair).")
    if len(texte) > TEXTE_REGLE_MAX:
        raise ValueError(f"Une règle tient en {TEXTE_REGLE_MAX} caractères au plus.")
    return texte.strip()


def chemin_conseils(base):
    """Les conseils du projet : `.factory/partenaires.json` (à côté du fichier de factory)."""
    return Path(base) / "partenaires.json"
