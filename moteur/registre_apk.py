"""Le registre des APK construits d'un projet : une recette (ou une vérification) reçoit l'APK EXISTANT dont l'empreinte des
sources correspond au code testé, sans livraison ni reconstruction (règle du Directeur, 2026-11-27 : FM_Stats t294
reconstruisait et rapatriait `app-client-release.apk` à chaque passage alors que le code de l'application n'avait pas changé).

- Un fichier `.factory/apk-construits.json` : `[{variante, empreinte, chemin, date}]`, alimenté par chaque APK rapatrié
  (`enregistrer`). La variante vient du nom (`app-<variante>-release.apk`), sinon « defaut ».
- L'empreinte des sources (`empreinte`) : un condensé des fichiers COMMITÉS qui changent l'application (`git ls-tree -r HEAD` du
  dossier Flutter, filtré par `apk_besoin.touche_l_application` : ni tests, ni documentation, ni motifs `apk_ignore`). Deux
  états du dépôt qui ne diffèrent que par un fichier ignoré ont la même empreinte. Approximation assumée : l'empreinte
  enregistrée est celle du dépôt au moment du rapatriement.
- `fournir` : l'APK existant de la variante si l'empreinte correspond ; sinon (`perime`, `absent`) UNE construction est
  demandée (`demande_de_construction`, fichier `.factory/apk-construction-demandee.json`) : une seule par (variante,
  empreinte) pendant `DELAI_CONSTRUCTION_S`, partagée par les tests qui l'attendent en même temps.
Lecture seule sur le dépôt ; rien ne construit : le registre dit ce qui existe, ce qui manque et qui construit.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from moteur import apk_besoin

NOM_REGISTRE = "apk-construits.json"
NOM_DEMANDES = "apk-construction-demandee.json"
PAR_VARIANTE_MAX = 20
DELAI_CONSTRUCTION_S = 3600
MOTIF_VARIANTE = re.compile(r"(?:^|/)app-([A-Za-z][A-Za-z0-9]{0,29})-(?:release|debug)(?:-unsigned)?\.apk$")


def _dossier_flutter(dossier):
    outils = str(Path(__file__).resolve().parent.parent / "outils")
    if outils not in sys.path:
        sys.path.append(outils)
    import projet_flutter
    return projet_flutter.dossier_flutter(dossier)


def variante_de(chemin):
    m = MOTIF_VARIANTE.search(str(chemin).replace("\\", "/"))
    return m.group(1) if m else "defaut"


def empreinte(dossier, motifs=None):
    """L'empreinte des sources de l'application du dépôt `dossier` (voir le module) ; None si le projet n'est pas Flutter
    ou si git ne répond pas."""
    app = _dossier_flutter(dossier)
    if app is None:
        return None
    motifs = apk_besoin.IGNORE_PAR_DEFAUT if motifs is None else motifs
    try:
        r = subprocess.run(["git", "-C", str(dossier), "ls-tree", "-r", "HEAD", "--", "." if app == "." else app],
                           capture_output=True, text=True, timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    retenus = []
    for ligne in r.stdout.splitlines():
        entete, _, chemin = ligne.partition("\t")
        if chemin and apk_besoin.touche_l_application(app, [chemin], motifs):
            retenus.append(f"{entete.split()[-1]} {chemin}")
    return hashlib.sha256("\n".join(sorted(retenus)).encode("utf-8")).hexdigest()[:16]


def _fichier(dossier, nom):
    return Path(dossier) / ".factory" / nom


def _lire(chemin):
    try:
        x = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return x


def _ecrire(chemin, valeur):
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_text(json.dumps(valeur, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, chemin)


def lire(dossier):
    x = _lire(_fichier(dossier, NOM_REGISTRE))
    return [e for e in x if isinstance(e, dict) and e.get("chemin") and e.get("empreinte")] if isinstance(x, list) else []


def enregistrer(dossier, chemin, motifs=None, maintenant=None):
    """Un APK construit et rapatrié (`chemin`, relatif au dépôt) entre au registre avec l'empreinte des sources d'aujourd'hui.
    Rend l'entrée, ou None (projet non Flutter, empreinte illisible, ce n'est pas un .apk). Jamais une exception."""
    try:
        if not str(chemin).lower().endswith(".apk"):
            return None
        e = empreinte(dossier, motifs)
        if e is None:
            return None
        entree = {"variante": variante_de(chemin), "empreinte": e, "chemin": str(chemin).replace("\\", "/"),
                  "date": (maintenant or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")}
        reste = [x for x in lire(dossier) if x["chemin"] != entree["chemin"]]
        meme = [x for x in reste if x.get("variante") == entree["variante"]][-(PAR_VARIANTE_MAX - 1):]
        _ecrire(_fichier(dossier, NOM_REGISTRE), [x for x in reste if x.get("variante") != entree["variante"]] + meme + [entree])
        demandes = _lire(_fichier(dossier, NOM_DEMANDES))
        if isinstance(demandes, dict) and demandes.pop(f"{entree['variante']}:{e}", None) is not None:
            _ecrire(_fichier(dossier, NOM_DEMANDES), demandes)      # la construction attendue est arrivée
        return entree
    except Exception:  # noqa: BLE001 : le registre n'est jamais une raison d'arrêter une livraison
        return None


def demande_de_construction(dossier, variante, e, tache, maintenant=None):
    """`(vrai, None)` si CET appelant doit construire (aucune demande en cours pour cette variante et ces sources) ;
    `(faux, tâche)` si une autre tâche l'a déjà demandée il y a moins de `DELAI_CONSTRUCTION_S` : il attend son APK."""
    maintenant = time.time() if maintenant is None else maintenant
    chemin = _fichier(dossier, NOM_DEMANDES)
    demandes = _lire(chemin)
    demandes = demandes if isinstance(demandes, dict) else {}
    cle = f"{variante}:{e}"
    d = demandes.get(cle)
    if isinstance(d, dict) and maintenant - float(d.get("le") or 0) < DELAI_CONSTRUCTION_S and d.get("tache") != tache:
        return False, d.get("tache")
    demandes[cle] = {"tache": tache, "le": maintenant}
    _ecrire(chemin, {k: v for k, v in demandes.items() if maintenant - float((v or {}).get("le") or 0) < DELAI_CONSTRUCTION_S})
    return True, None


def fournir(dossier, variante=None, tache=None, motifs=None, maintenant=None, demander=True):
    """Ce qu'une tâche de test reçoit : un dict `{etat, ...}`.
    - `etat: "existant"` : l'APK le plus récent de la variante dont l'empreinte correspond aux sources (`apk` : l'entrée) ;
      aucune construction, aucune livraison ;
    - `etat: "a_construire"` : `raison` (« perime » : il en existe mais les sources ont changé, « absent » : aucun pour cette
      variante) ; `construire` : vrai si cette tâche doit lancer l'UNE construction, `attend` : la tâche qui l'a déjà demandée ;
    - `etat: "inconnu"` : projet non Flutter ou empreinte illisible (rien à dire)."""
    e = empreinte(dossier, motifs)
    if e is None:
        return {"etat": "inconnu"}
    connus = [x for x in lire(dossier) if (variante is None or x.get("variante") == variante)]
    bons = [x for x in connus if x["empreinte"] == e and (Path(dossier) / x["chemin"]).is_file()]
    if bons:
        return {"etat": "existant", "apk": max(bons, key=lambda x: x.get("date") or ""), "empreinte": e}
    variante = variante or (connus[-1]["variante"] if connus else "defaut")
    construire, attend = demande_de_construction(dossier, variante, e, tache or "?", maintenant) if demander else (False, None)
    return {"etat": "a_construire", "raison": "perime" if connus else "absent", "variante": variante, "empreinte": e,
            "construire": construire, "attend": attend}
