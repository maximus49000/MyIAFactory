"""Ce que le moteur dit au bureau de ce qui retient son travail : deux petits fichiers, écrits par le moteur à chaque
passage et relus par le serveur du bureau (deux processus).

- `installation-prioritaire.json`, à côté du fichier du bureau (valable pour tous les projets) : la pause globale d'une
  installation d'outil, `{"t", "texte", "projet", "outils"}`. Absent quand rien n'est en pause.
- `attente-charge.json`, dans le dossier `.factory` d'un projet : les tâches prêtes que la charge de l'ordinateur retient,
  `{"t", "texte", "taches": [ids], "charge", "plafond"}`. Absent quand rien n'attend la charge.
- `attente-places.json`, dans le dossier `.factory` d'un projet : des places d'agents libres que rien ne peut prendre
  tant que le Directeur n'a pas validé, `{"t", "texte", "places", "validation"}`. Absent sinon.

Un fichier que le moteur n'a pas réécrit depuis `FRAICHEUR_S` secondes est ignoré (le moteur s'est arrêté : le bureau ne
doit pas afficher une pause qui n'existe plus). Aucune donnée de clé ni de chemin n'y est."""
import json
import os
import time
from pathlib import Path

FRAICHEUR_S = 120
FICHIER_PAUSE = "installation-prioritaire.json"
FICHIER_CHARGE = "attente-charge.json"
FICHIER_PLACES = "attente-places.json"


def chemin_places(dossier_factory):
    return Path(dossier_factory) / FICHIER_PLACES


def attente_places(dossier_factory, maintenant=None):
    """Les places libres qui attendent une validation du Directeur (`{texte, places, validation}`), ou `None`."""
    o = lire(chemin_places(dossier_factory), maintenant)
    if o is None:
        return None
    places = o.get("places")
    return {"texte": o["texte"], "places": places if isinstance(places, int) and not isinstance(places, bool) else None,
            "validation": o.get("validation") if isinstance(o.get("validation"), str) else None}


def chemin_pause(fichier_bureau):
    return Path(fichier_bureau).expanduser().parent / FICHIER_PAUSE


def chemin_charge(dossier_factory):
    return Path(dossier_factory) / FICHIER_CHARGE


def ecrire(chemin, objet, maintenant=None):
    """Écrit l'objet (avec l'heure `t`) en remplaçant le fichier d'un coup. Une erreur d'écriture n'arrête rien."""
    chemin = Path(chemin)
    try:
        tmp = chemin.with_name(chemin.name + ".tmp")
        tmp.write_text(json.dumps({**objet, "t": time.time() if maintenant is None else maintenant},
                                  ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, chemin)
    except OSError:
        pass


def effacer(chemin):
    try:
        Path(chemin).unlink()
    except OSError:
        pass


def lire(chemin, maintenant=None):
    """L'objet du fichier, ou `None` : absent, illisible, ou pas réécrit depuis `FRAICHEUR_S`."""
    try:
        objet = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(objet, dict) or not isinstance(objet.get("texte"), str) or not objet["texte"].strip():
        return None
    t = objet.get("t")
    maintenant = time.time() if maintenant is None else maintenant
    if not isinstance(t, (int, float)) or isinstance(t, bool) or maintenant - t > FRAICHEUR_S:
        return None
    return objet


def pause_installation(fichier_bureau, maintenant=None):
    """La pause globale pour le bureau `fichier_bureau` (`{texte, projet, outils}`), ou `None`."""
    if fichier_bureau is None:
        return None
    o = lire(chemin_pause(fichier_bureau), maintenant)
    if o is None:
        return None
    outils = [x for x in o.get("outils") or [] if isinstance(x, str)]
    return {"texte": o["texte"], "projet": o.get("projet") if isinstance(o.get("projet"), str) else None,
            "outils": outils}


def attente_charge(dossier_factory, maintenant=None):
    """Les tâches qu'un projet retient pour sa charge (`{texte, taches, charge, plafond}`), ou `None`."""
    o = lire(chemin_charge(dossier_factory), maintenant)
    if o is None:
        return None
    taches = [x for x in o.get("taches") or [] if isinstance(x, str)]
    entier = lambda v: v if isinstance(v, int) and not isinstance(v, bool) else None  # noqa: E731
    return {"texte": o["texte"], "taches": taches, "charge": entier(o.get("charge")), "plafond": entier(o.get("plafond"))}
