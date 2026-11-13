"""Les anomalies du logiciel : ce que le Chef, en analysant un blocage, attribue au logiciel lui-même (son moteur, ses
outils, son bureau) et pas au projet.

Un fichier du projet, à côté du fichier de factory (`.factory/anomalies-logiciel.jsonl`), une anomalie par ligne :
`{id, t, projet, tache, titre_tache, titre, description, etat (nouvelle | vue | reglee), maj?}`. Il n'est écrit que par
`lancer anomalies` ; le relevé le publie (`anomalies_logiciel`) et Claude Code le lit en début de session
(`lancer anomalies`, sans entrée). Une ligne illisible est ignorée.
"""
import json
import os
import re
from pathlib import Path

from orchestrateur import suivi as su

FICHIER = "anomalies-logiciel.jsonl"
ETATS = ("nouvelle", "vue", "reglee")
TITRE_MAX, DESCRIPTION_MAX = 120, 900
MAX_ANOMALIES = 200          # les plus anciennes réglées partent d'abord au-delà


def chemin(f):
    return Path(f["chemin"]).parent / FICHIER


def _valide(x):
    return (isinstance(x, dict) and isinstance(x.get("id"), str) and re.fullmatch(r"a[0-9]+", x["id"])
            and isinstance(x.get("titre"), str) and x["titre"].strip() and isinstance(x.get("description"), str)
            and x.get("etat") in ETATS)


def lire(f):
    """Les anomalies, de la plus ancienne à la plus récente (liste vide sans fichier)."""
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


def _ecrire(f, anomalies):
    c = chemin(f)
    c.parent.mkdir(parents=True, exist_ok=True)
    tmp = c.with_name(c.name + ".tmp")
    tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in anomalies), encoding="utf-8")
    os.replace(tmp, c)


def _texte(e, cle, maximum, ligne=False):
    v = e.get(cle)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"« {cle} » est obligatoire.")
    v = " ".join(v.split()) if ligne else v.strip()
    if len(v) > maximum:
        raise ValueError(f"« {cle} » tient en {maximum} caractères au plus.")
    return v


def ajouter(f, e):
    """Une anomalie nouvelle : `titre`, `description`, et facultatifs `tache`, `titre_tache`. Rend l'anomalie."""
    anomalies = lire(f)
    numero = max([int(x["id"][1:]) for x in anomalies] or [0]) + 1
    x = {"id": f"a{numero}", "t": su.maintenant(), "projet": f.get("nom") or "",
         "tache": e.get("tache") if isinstance(e.get("tache"), str) else None,
         "titre_tache": (e.get("titre_tache") or "")[:200] if isinstance(e.get("titre_tache"), str) else "",
         "titre": _texte(e, "titre", TITRE_MAX, ligne=True), "description": _texte(e, "description", DESCRIPTION_MAX),
         "etat": "nouvelle"}
    anomalies.append(x)
    while len(anomalies) > MAX_ANOMALIES:
        reglee = next((a for a in anomalies if a["etat"] == "reglee"), anomalies[0])
        anomalies.remove(reglee)
    _ecrire(f, anomalies)
    return x


def marquer(f, ident, etat):
    """« Vu » ou « Réglée » : l'état d'une anomalie connue."""
    if etat not in ("vue", "reglee"):
        raise ValueError("« etat » vaut vue ou reglee.")
    anomalies = lire(f)
    x = next((a for a in anomalies if a["id"] == ident), None)
    if x is None:
        raise ValueError(f"Anomalie inconnue : {ident}")
    x["etat"], x["maj"] = etat, su.maintenant()
    _ecrire(f, anomalies)
    return x
