"""Réglages d'un projet : lecture et écriture."""
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

from .releve import MOTIF_GENRE  # un id de projet suit le même motif qu'un genre

DEFAUTS = {"port": 8770, "charge_max": 75, "fraicheur_min": 30, "releve": {}, "prix_automatiques": True}


class ReglagesInvalides(Exception):
    pass


def charger(chemin):
    chemin = Path(chemin)
    r = json.loads(json.dumps(DEFAUTS))
    if chemin.exists():
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as e:
            raise ReglagesInvalides(f"Réglages illisibles ({chemin}) : {e}")
        if not isinstance(donnees, dict):
            raise ReglagesInvalides(f"Réglages illisibles ({chemin}) : un objet JSON est attendu")
        r.update(donnees)
    r["dossier"] = str(chemin.parent)
    return r


MAX_PROJETS = 12


def _id_par_defaut(chemin):
    """Le nom du dossier des réglages (son parent pour `.factory`), ramené à `[a-z0-9-]`."""
    dossier = chemin.parent
    if dossier.name == ".factory":
        dossier = dossier.parent
    texte = unicodedata.normalize("NFKD", dossier.name).encode("ascii", "ignore").decode("ascii").lower()
    texte = re.sub(r"[^a-z0-9]+", "-", texte).strip("-")
    return texte[:40].rstrip("-") or "projet"


def lire_bureau(chemin):
    """Le fichier du bureau : `{"port"?: 8770, "projets": [chemin | {"chemin", "id"?}]}` (1 à 12 projets,
    chemins relatifs à ce fichier). Rend `{"port": int, "projets": [{"id", "chemin": Path}]}`."""
    chemin = Path(chemin)
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as e:
        raise ReglagesInvalides(f"Fichier du bureau illisible ({chemin}) : {e}")
    if not isinstance(donnees, dict):
        raise ReglagesInvalides(f"Fichier du bureau illisible ({chemin}) : un objet JSON est attendu")
    port = donnees.get("port", DEFAUTS["port"])
    if type(port) is not int or not 0 <= port <= 65535:
        raise ReglagesInvalides("Fichier du bureau : « port » doit être un entier entre 0 et 65535.")
    projets = donnees.get("projets")
    if not isinstance(projets, list) or not 1 <= len(projets) <= MAX_PROJETS:
        raise ReglagesInvalides(f"Fichier du bureau : « projets » doit lister de 1 à {MAX_PROJETS} "
                                "fichiers de réglages.")
    entrees = []
    for i, p in enumerate(projets):
        id_ = None
        if isinstance(p, dict):
            id_ = p.get("id")
            p = p.get("chemin")
            if id_ is not None and (not isinstance(id_, str) or not MOTIF_GENRE.match(id_)):
                raise ReglagesInvalides(f"Fichier du bureau : projets[{i}].id invalide (lettres minuscules, "
                                        "chiffres et tirets, 40 caractères au plus).")
        if not isinstance(p, str) or not p.strip() or "\x00" in p:
            raise ReglagesInvalides(f"Fichier du bureau : projets[{i}] doit donner le chemin d'un fichier "
                                    "de réglages.")
        c = chemin.parent / p
        if not c.is_file():  # une faute de frappe ne doit pas créer un projet fantôme
            raise ReglagesInvalides(f"Fichier du bureau : projets[{i}] : fichier de réglages introuvable ({c}).")
        entrees.append((id_, c))
    dossiers = [c.resolve().parent for _, c in entrees]
    if len(dossiers) != len(set(dossiers)):  # le bureau écrit ses historiques à côté des réglages
        raise ReglagesInvalides("Fichier du bureau : deux projets ont leurs réglages dans le même dossier.")
    donnes = [i for i, _ in entrees if i is not None]
    if len(donnes) != len(set(donnes)):
        raise ReglagesInvalides("Fichier du bureau : deux projets portent le même id.")
    pris = set(donnes)
    sortie = []
    for id_, c in entrees:
        if id_ is None:
            base = _id_par_defaut(c)
            id_, n = base, 1
            while id_ in pris:
                n += 1
                suffixe = f"-{n}"
                id_ = base[:40 - len(suffixe)].rstrip("-") + suffixe
            pris.add(id_)
        sortie.append({"id": id_, "chemin": c})
    return {"port": port, "projets": sortie}


def fixer_charge_max(chemin, valeur):
    if type(valeur) is not int or not 30 <= valeur <= 95:
        raise ValueError("La charge maximum doit être un entier entre 30 et 95.")
    chemin = Path(chemin)
    donnees = {}
    if chemin.exists():
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as e:
            raise ReglagesInvalides(f"Réglages illisibles ({chemin}) : {e}")
    donnees["charge_max"] = valeur
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=2)
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return charger(chemin)
