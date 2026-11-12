"""L'archive des semaines du forfait Claude : la courbe « % utilisé » de chaque fenêtre `seven_day`, gardée pour toujours.

Le fichier d'historique de l'abonnement est rogné ; ici chaque semaine (identifiée par son heure de remise à zéro, à
`TOLERANCE` secondes près) a son propre fichier `<racine>/abonnement-semaines/<AAAA-MM-JJ>.json` (la date UTC de la remise
à zéro ; `-2`, `-3`… si deux semaines tombaient le même jour) :

    {"version": 1, "fenetre": "seven_day", "debut": <remise − 7 j>, "remise": <epoch>, "vu": <dernier instant lu>,
     "points": [{"t": <epoch>, "pourcent": <0..100, utilisé>, "source": "compte" | "moteur"}, …]}

Un point n'est gardé que si le pourcentage change (les points sont donc des paliers : la valeur tient jusqu'au point
suivant) ; `vu` dit jusqu'où la dernière valeur a été observée. Les pourcentages sont ceux du compte entier.
Écriture atomique ; rien ne lève (le disque ne doit pas faire échouer un appel). Le dossier est celui de
`abonnement.racine()` : les tests injectent le leur.
"""
import json
import math
import os
import re
import threading
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path

NOM_DOSSIER = "abonnement-semaines"
DUREE = 7 * 86400
TOLERANCE = 120
MAX_POINTS = 20000
MOTIF_ID = re.compile(r"^\d{4}-\d{2}-\d{2}(-\d{1,2})?$")
_VERROU = threading.Lock()


def dossier(racine):
    return Path(racine) / NOM_DOSSIER


def _nombre(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _nom(remise, k):
    jour = datetime.fromtimestamp(remise, timezone.utc).strftime("%Y-%m-%d")
    return jour if k == 0 else f"{jour}-{k + 1}"


def _valide(d):
    if not isinstance(d, dict) or not _nombre(d.get("remise")) or not isinstance(d.get("points"), list):
        return None
    points = [{"t": int(p["t"]), "pourcent": float(p["pourcent"]), "source": p.get("source") if p.get("source") in
               ("compte", "moteur") else "moteur"}
              for p in d["points"] if isinstance(p, dict) and _nombre(p.get("t")) and _nombre(p.get("pourcent"))
              and 0 <= p["pourcent"] <= 100]
    points.sort(key=lambda p: p["t"])
    remise = int(d["remise"])
    return {"version": 1, "fenetre": "seven_day", "debut": remise - DUREE, "remise": remise,
            "vu": int(d["vu"]) if _nombre(d.get("vu")) else (points[-1]["t"] if points else None), "points": points}


def _lire_fichier(chemin):
    try:
        return _valide(json.loads(chemin.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def _ecrire(chemin, texte):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(f"{chemin.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(texte, encoding="utf-8")
    os.replace(tmp, chemin)


def _trouver(d, remise):
    """(chemin, semaine | None) : le fichier de la semaine qui finit à `remise`, ou le premier nom libre."""
    for k in range(20):
        chemin = d / f"{_nom(remise, k)}.json"
        if not chemin.exists():
            return chemin, None
        s = _lire_fichier(chemin)
        if s is not None and abs(s["remise"] - remise) <= TOLERANCE:
            return chemin, s
    return None, None


def noter(instantane, source, racine):
    """Verse l'instantané (`abonnement.valider`) à la semaine qu'il décrit. `source` : "compte" ou "moteur"."""
    f = (instantane or {}).get("seven_day")
    t = (instantane or {}).get("t")
    if not f or not _nombre(t):
        return
    remise = int(f["remise"])
    if not remise - DUREE - TOLERANCE <= t <= remise + TOLERANCE:
        return
    try:
        with _VERROU:
            chemin, s = _trouver(dossier(racine), remise)
            if chemin is None:
                return
            s = s or {"version": 1, "fenetre": "seven_day", "debut": remise - DUREE, "remise": remise, "vu": None,
                      "points": []}
            t = int(t)
            instants = [p["t"] for p in s["points"]]
            i = bisect_right(instants, t)
            avant = s["points"][i - 1] if i else None
            change = False
            if avant is None or avant["pourcent"] != f["pourcent"]:
                if not (i and instants[i - 1] == t) and len(s["points"]) < MAX_POINTS:
                    s["points"].insert(i, {"t": t, "pourcent": float(f["pourcent"]),
                                           "source": "compte" if source == "compte" else "moteur"})
                    change = True
            if s["vu"] is None or t > s["vu"]:
                s["vu"], change = t, True
            if change:
                _ecrire(chemin, json.dumps(s, ensure_ascii=False))
    except OSError:
        pass


def importer(historique, racine):
    """Verse les lignes de l'historique d'abonnement (`abonnement.lire_historique`) : sert une fois, au premier usage."""
    for ligne in sorted(historique, key=lambda x: x.get("t") or 0):
        noter(ligne, ligne.get("source") or "moteur", racine)


def lister(racine, maintenant):
    """Les semaines archivées, la plus récente d'abord : `[{id, debut, remise, courante, max, n}]`."""
    d = dossier(racine)
    sortie = []
    for chemin in (d.glob("*.json") if d.is_dir() else []):
        s = _lire_fichier(chemin)
        if s is None or not MOTIF_ID.match(chemin.stem):
            continue
        sortie.append({"id": chemin.stem, "debut": s["debut"], "remise": s["remise"],
                       "courante": s["debut"] <= maintenant < s["remise"],
                       "max": max((p["pourcent"] for p in s["points"]), default=None), "n": len(s["points"])})
    sortie.sort(key=lambda x: -x["remise"])
    return sortie


def lire(racine, identifiant, maintenant=None):
    """La semaine `identifiant` (`{id, debut, remise, vu, points, courante}`), ou None."""
    if not isinstance(identifiant, str) or not MOTIF_ID.match(identifiant):
        return None
    s = _lire_fichier(dossier(racine) / f"{identifiant}.json")
    if s is None:
        return None
    s["id"] = identifiant
    if maintenant is not None:
        s["courante"] = s["debut"] <= maintenant < s["remise"]
    return s


def existe(racine):
    return dossier(racine).is_dir()
