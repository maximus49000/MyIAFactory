"""Ce que le moteur dit au bureau de ce qui retient son travail : de petits fichiers, écrits par le moteur à chaque
passage et relus par le serveur du bureau (deux processus).

- `installation-prioritaire.json`, à côté du fichier du bureau (valable pour tous les projets) : la pause globale d'une
  installation d'outil, `{"t", "texte", "projet", "outils"}`. Absent quand rien n'est en pause.
- `attente-charge.json`, dans le dossier `.factory` d'un projet : les tâches prêtes que la charge de l'ordinateur retient,
  `{"t", "texte", "taches": [ids], "charge", "plafond"}`. Absent quand rien n'attend la charge.
- `attente-places.json`, dans le dossier `.factory` d'un projet : des places d'agents libres que rien ne peut prendre
  tant que le Directeur n'a pas validé, `{"t", "texte", "places", "validation"}`. Absent sinon.
- `attente-taches.json`, dans le dossier `.factory` d'un projet : pourquoi chaque tâche prête ne part pas (prérequis,
  agent, décision, pause), `{"t", "texte", "total", "familles", "taches": {id: {genre, motif, texte, detail, ensuite,
  quand}}}`. Absent quand rien n'attend.

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


FICHIER_TACHES = "attente-taches.json"
GENRES = ("prerequis", "agent", "decision", "pause")


def chemin_taches(dossier_factory):
    return Path(dossier_factory) / FICHIER_TACHES


def _texte(v):
    return v if isinstance(v, str) and v.strip() else None


def attente_taches(dossier_factory, maintenant=None):
    """Pourquoi chaque tâche prête ne part pas (`{texte, total, familles: [{genre, motif, n, texte}], taches: {id:
    {genre, motif, texte, detail, ensuite, quand}}}`), ou `None`. Une raison ou une famille mal formée est écartée."""
    o = lire(chemin_taches(dossier_factory), maintenant)
    if o is None:
        return None
    taches = {}
    for tid, r in (o.get("taches") or {}).items() if isinstance(o.get("taches"), dict) else ():
        if not isinstance(r, dict) or r.get("genre") not in GENRES or not _texte(r.get("texte")):
            continue
        lignes = lambda v: [x for x in v if _texte(x)] if isinstance(v, list) else []  # noqa: E731
        taches[str(tid)] = {"genre": r["genre"], "motif": _texte(r.get("motif")) or r["texte"], "texte": r["texte"],
                            "detail": lignes(r.get("detail")), "ensuite": lignes(r.get("ensuite")),
                            "quand": _texte(r.get("quand"))}
    familles = [{"genre": f["genre"], "motif": f.get("motif") if isinstance(f.get("motif"), str) else "",
                 "n": f["n"], "texte": f["texte"]}
                for f in o.get("familles") or [] if isinstance(f, dict) and f.get("genre") in GENRES
                and isinstance(f.get("n"), int) and not isinstance(f.get("n"), bool) and _texte(f.get("texte"))] \
        if isinstance(o.get("familles"), list) else []
    total = o.get("total")
    return {"texte": o["texte"], "total": total if isinstance(total, int) and not isinstance(total, bool) else len(taches),
            "familles": familles, "taches": taches}


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


# --- Le réveil du moteur : une demande posée par le bureau est traitée tout de suite.

FICHIER_REVEIL = "moteur-reveil"


def chemin_reveil(dossier_reglages):
    """Le fichier de réveil d'un projet, à côté de son fichier de réglages (là où le bureau et le moteur se retrouvent)."""
    return Path(dossier_reglages) / FICHIER_REVEIL


def reveiller(dossier_reglages):
    """Le bureau vient de poser une demande : touche le fichier de réveil du projet (le moteur compare son horodatage).
    Le contenu change à chaque appel ; une erreur d'écriture n'arrête rien (le moteur lira la demande à son prochain tour)."""
    try:
        Path(chemin_reveil(dossier_reglages)).write_text(str(time.time_ns()), encoding="utf-8")
    except OSError:
        pass


def date_du_reveil(dossier_reglages):
    """L'horodatage (ns) du dernier réveil du projet, ou `None` s'il n'y en a jamais eu."""
    try:
        return Path(chemin_reveil(dossier_reglages)).stat().st_mtime_ns
    except OSError:
        return None
