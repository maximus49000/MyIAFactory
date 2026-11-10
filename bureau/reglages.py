"""Réglages d'un projet : lecture et écriture."""
import json
import os
import tempfile
from pathlib import Path

DEFAUTS = {"port": 8770, "charge_max": 75, "fraicheur_min": 30, "releve": {}}


class ReglagesInvalides(Exception):
    pass


def charger(chemin):
    chemin = Path(chemin)
    r = json.loads(json.dumps(DEFAUTS))
    if chemin.exists():
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            raise ReglagesInvalides(f"Réglages illisibles ({chemin}) : {e}")
        if not isinstance(donnees, dict):
            raise ReglagesInvalides(f"Réglages illisibles ({chemin}) : un objet JSON est attendu")
        r.update(donnees)
    r["dossier"] = str(chemin.parent)
    return r


def fixer_charge_max(chemin, valeur):
    if type(valeur) is not int or not 30 <= valeur <= 95:
        raise ValueError("La charge maximum doit être un entier entre 30 et 95.")
    chemin = Path(chemin)
    donnees = {}
    if chemin.exists():
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8"))
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
