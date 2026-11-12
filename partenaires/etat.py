"""Les connexions, quotas, limites et règles des partenaires : propres à la machine, communes à tous les projets.

Le fichier vit hors de tout dépôt (`~/MyIAFactory/partenaires.json`). Il ne contient **jamais** une valeur de clé :
seulement l'état de chaque connexion, le dernier quota lu avec sa date, les limites atteintes et les règles d'usage
que l'utilisateur a fixées. Écriture atomique sous verrou (le même mécanisme que le suivi).
"""
import datetime
import re
from pathlib import Path

from orchestrateur import suivi as su

ETATS = ("connecte", "declare", "non_connecte")
SECTIONS = ("connexions", "quotas", "limites", "regles", "lectures", "inscriptions")
REGLE_TRIPO = ("Si plusieurs éléments sont nécessaires, les générer au maximum en un seul prompt, "
               "sauf besoin de détail très précis ou d'animation.")
TEXTE_REGLE_MAX = 500
NOTE_INSCRIPTION_MAX = 200
# Le prompt qu'un partenaire accepte au plus (en caractères), quand on le sait : l'agent le respecte en préparant ce que
# l'utilisateur fait chez lui. Tripo : 1 000 caractères.
PROMPT_MAX = {"tripo": 1000}
# Les partenaires dont chaque réglage doit être donné avec le prompt (l'utilisateur les saisit à la main, sur le site).
REGLAGES_OBLIGATOIRES = ("tripo",)
DUREE_LIMITE = datetime.timedelta(hours=24)   # une limite sans nouveau relevé tombe d'elle-même au bout d'un jour


def chemin_par_defaut():
    from installation.dossier import racine
    return racine() / "partenaires.json"


def vide(aujourdhui=None):
    """L'état d'un fichier qui n'existe pas encore : la règle de départ de Tripo est proposée (une seule fois :
    dès que le fichier est écrit, ce qu'il contient fait foi)."""
    jour = aujourdhui or datetime.date.today().isoformat()
    return {"version": 1, "connexions": {}, "quotas": {}, "limites": {}, "lectures": {}, "inscriptions": {},
            "regles": {"tripo": [{"id": "r1", "texte": REGLE_TRIPO, "cree_le": jour}]}}


class EtatIllisible(ValueError):
    """Le fichier des partenaires n'est pas du JSON lisible."""


class Etat(su.Suivi):
    """`lire()` et `transaction()` comme le suivi, sur le fichier des partenaires."""

    def __init__(self, chemin=None):
        super().__init__(chemin or chemin_par_defaut())

    def lire(self):
        import json
        if not self.chemin.exists():
            return vide()
        try:
            lu = json.loads(self.chemin.read_text(encoding="utf-8-sig"))
        except ValueError as e:
            raise EtatIllisible(f"Fichier des partenaires illisible ({self.chemin}) : {e}. Corrigez-le, ou "
                                "renommez-le pour repartir d'un fichier neuf (connexions et règles seront à refaire).")
        d = {"version": 1}
        for s in SECTIONS:
            v = lu.get(s) if isinstance(lu, dict) else None
            v = v if isinstance(v, dict) else {}
            if s == "regles":   # une entrée abîmée est ignorée, jamais une raison de tout refuser
                d[s] = {i: [r for r in x if isinstance(r, dict)] for i, x in v.items() if isinstance(x, list)}
            elif s == "lectures":
                d[s] = {i: x for i, x in v.items() if isinstance(x, str)}
            else:
                d[s] = {i: x for i, x in v.items() if isinstance(x, dict)}
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


_SECRET = re.compile(r"(mot\s*[-_ ]?de\s*[-_ ]?passe|passw(or)?d|\bmdp\b|\bpwd\b|passphrase|secret|token|api[-_ ]?key|"
                     r"cl[ée]\s*(d['’ ]?)?api|\bcl[ée]\s*[:=])", re.IGNORECASE)
_JETON = re.compile(r"[A-Za-z0-9_\-]{24,}")


def note_inscription(note):
    """La note libre facultative d'une inscription (le nom du compte, l'offre) : un texte d'une ligne de 200 caractères
    au plus, **jamais un mot de passe ni une clé** : un texte qui en parle ou qui ressemble à un jeton est refusé.
    Rend la note nettoyée, ou `None`. Lève ValueError."""
    if note is None:
        return None
    if not isinstance(note, str):
        raise ValueError("« note » doit être un texte.")
    note = " ".join(note.split())
    if not note:
        return None
    if len(note) > NOTE_INSCRIPTION_MAX:
        raise ValueError(f"La note tient en {NOTE_INSCRIPTION_MAX} caractères au plus.")
    if _SECRET.search(note) or _JETON.search(note):
        raise ValueError("La note ne garde jamais un mot de passe, une clé ni un jeton : seulement le nom du compte "
                         "ou l'offre.")
    return note


def inscrire(d, partenaire, inscrit, note=None, quand=None):
    """Note que l'utilisateur a (ou n'a plus) un compte chez `partenaire`, sans liaison directe : seulement le fait, la
    date et une note facultative. Rend l'inscription (ou `None` si elle est retirée). Lève ValueError sur un refus."""
    if not isinstance(inscrit, bool):
        raise ValueError("« inscrit » doit être vrai ou faux.")
    inscriptions = d.setdefault("inscriptions", {})
    if not inscrit:
        inscriptions.pop(partenaire, None)
        return None
    note = note_inscription(note)
    ligne = {"depuis": quand or maintenant()}
    if note:
        ligne["note"] = note
    inscriptions[partenaire] = ligne
    return ligne


def est_inscrit(d, partenaire):
    """Vrai si l'utilisateur a un compte chez ce partenaire **et** n'y est pas connecté en direct (un partenaire connecté
    s'appelle directement : l'inscription ne sert pas)."""
    return (partenaire in (d.get("inscriptions") or {})
            and (d.get("connexions", {}).get(partenaire) or {}).get("etat") != "connecte")
