"""Le brouillon de l'échange avec le chef, avant que le projet n'existe.

Un fichier JSON par projet en cours de définition, dans `~/MyIAFactory/creations/`, hors de tout projet et du dépôt. Le
brouillon ne contient jamais de clé : les informations de la première fenêtre, l'échange, la proposition, les usages
(tokens) des appels déjà faits, la dernière erreur. Il vit 30 jours sans changement, puis il est abandonné.

Un tour d'échange dure 30 à 60 secondes : il s'exécute en arrière-plan. Pendant ce temps le brouillon porte
`en_cours` (`{"depuis", "correction"?, "proposer_maintenant"?}`) et ce processus note le brouillon comme vivant
(`_VIVANTS`). Un `en_cours` écrit dans le fichier mais absent de `_VIVANTS` est un tour **interrompu** (le bureau a été
relancé pendant l'appel) : il ne bloque pas, et la demande interrompue est reprise au tour suivant.
"""
import json
import os
import re
import secrets
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from installation import dossier as dos
from installation.dossier import Echec

JOURS_PURGE = 30
MOTIF_ID = re.compile(r"^c[0-9a-f]{12}\Z")     # jamais un chemin
CLES_INFOS = ("parent", "nom", "mots_interdits", "facturation", "github", "description")
_VERROU = threading.RLock()
_VIVANTS = set()      # les brouillons dont un tour tourne dans ce processus


class TourEnCours(Echec):
    """Un tour est déjà en cours pour ce brouillon."""

    def __init__(self, message="Un tour est déjà en cours pour ce projet."):
        super().__init__(message)


def _dossier(d=None):
    return Path(d) if d is not None else dos.racine() / "creations"


def _commun(c=None):
    return Path(c) if c is not None else dos.racine() / "usage-creations.jsonl"


def _verifier_id(id_):
    if not isinstance(id_, str) or not MOTIF_ID.match(id_):
        raise Echec("Ce brouillon n'existe pas.")
    return id_


def _chemin(id_, d):
    return _dossier(d) / f"{_verifier_id(id_)}.json"


def _iso(t):
    return t.isoformat(timespec="seconds")


def _ecrire_fichier(chemin, texte):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texte)
        for essai in range(5):     # Windows refuse parfois de remplacer un fichier qu'un autre fil lit
            try:
                os.replace(tmp, chemin)
                break
            except PermissionError:
                if essai == 4:
                    raise
                time.sleep(0.02)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def creer(infos, *, dossier=None, maintenant=None):
    """Un brouillon neuf, écrit. `infos` : {parent, nom, mots_interdits, facturation, github, description}."""
    if not isinstance(infos, dict) or set(infos) - set(CLES_INFOS):
        raise Echec("Les informations du projet ne portent que : " + ", ".join(CLES_INFOS) + ".")
    t = maintenant or datetime.now()
    b = {"id": "c" + secrets.token_hex(6), "cree": _iso(t), "maj": _iso(t), "infos": json.loads(json.dumps(infos)),
         "echange": [], "tours": 0, "proposition": None, "usages": [], "erreur": None, "en_cours": None}
    _ecrire_fichier(_chemin(b["id"], dossier), json.dumps(b, ensure_ascii=False, indent=1))
    return b


def lire(id_, *, dossier=None):
    chemin = _chemin(id_, dossier)
    try:
        b = json.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Echec("Ce brouillon n'existe pas (ou plus).") from None
    except (OSError, ValueError) as e:
        raise Echec(f"Ce brouillon est illisible : {e}") from None
    if not isinstance(b, dict) or b.get("id") != id_ or not isinstance(b.get("infos"), dict):
        raise Echec("Ce brouillon est illisible.")
    return b


def ecrire(b, *, dossier=None, maintenant=None):
    """Écrit le brouillon (atomiquement) ; `maj` prend l'heure."""
    chemin = _chemin(b.get("id") if isinstance(b, dict) else None, dossier)
    b["maj"] = _iso(maintenant or datetime.now())
    _ecrire_fichier(chemin, json.dumps(b, ensure_ascii=False, indent=1))


def etat_du_tour(b):
    """`libre`, `en_cours` (un tour tourne dans ce processus) ou `interrompu` (`en_cours` écrit, mais rien ne tourne)."""
    if not b.get("en_cours"):
        return "libre"
    return "en_cours" if b["id"] in _VIVANTS else "interrompu"


def lister(*, dossier=None):
    """[{id, nom, maj, etat: questions | proposition, tours, tour: libre | en_cours | interrompu}], le plus récent
    d'abord ; un fichier illisible est ignoré."""
    d = _dossier(dossier)
    sortie = []
    for chemin in (sorted(d.glob("c*.json")) if d.is_dir() else []):
        if not MOTIF_ID.match(chemin.stem):
            continue
        try:
            b = lire(chemin.stem, dossier=d)
        except Echec:
            continue
        sortie.append({"id": b["id"], "nom": str(b["infos"].get("nom") or ""), "maj": b.get("maj") or "",
                       "etat": "proposition" if b.get("proposition") else "questions",
                       "tours": b.get("tours") if isinstance(b.get("tours"), int) else 0, "tour": etat_du_tour(b)})
    return sorted(sortie, key=lambda x: x["maj"], reverse=True)


def commencer_tour(id_, demande, *, dossier=None, maintenant=None):
    """Marque le brouillon « en cours » (écrit) et le note vivant, ou `TourEnCours` si un tour tourne déjà. `demande` :
    {correction?, proposer_maintenant?}. Un tour interrompu ne bloque pas : sans nouvelle demande, c'est la sienne qui
    est reprise. Rend le brouillon écrit."""
    with _VERROU:
        b = lire(id_, dossier=dossier)
        if etat_du_tour(b) == "en_cours":
            raise TourEnCours()
        t = maintenant or datetime.now()
        reprise = {k: v for k, v in (b.get("en_cours") or {}).items() if k != "depuis"} if not demande else {}
        b["en_cours"] = {"depuis": _iso(t), **(demande or reprise)}
        ecrire(b, dossier=dossier, maintenant=t)
        _VIVANTS.add(id_)
        return b


def finir_tour(id_, b=None, *, dossier=None, maintenant=None):
    """Le tour est fini : `b` (le brouillon mis à jour) est écrit sans `en_cours`, puis le brouillon n'est plus vivant.
    Sans `b`, le fichier est seulement libéré. Un brouillon abandonné entre-temps n'est pas recréé."""
    with _VERROU:
        try:
            if b is None:
                try:
                    b = lire(id_, dossier=dossier)
                except Echec:
                    return
            if _chemin(id_, dossier).exists():
                b["en_cours"] = None
                ecrire(b, dossier=dossier, maintenant=maintenant)
        finally:
            _VIVANTS.discard(id_)


def _ajouter_usages(usages, commun):
    if not usages:
        return
    c = _commun(commun)
    c.parent.mkdir(parents=True, exist_ok=True)
    with c.open("a", encoding="utf-8", newline="\n") as f:
        for u in usages:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")


def abandonner(id_, *, dossier=None, commun=None):
    """Le brouillon est supprimé ; ses usages (ils ont coûté) vont au fichier des échanges abandonnés."""
    with _VERROU:
        b = lire(id_, dossier=dossier)
        if etat_du_tour(b) == "en_cours":
            raise TourEnCours("Un tour est en cours : attendez sa fin pour supprimer ce projet.")
        _ajouter_usages([u for u in b.get("usages") or [] if isinstance(u, dict)], commun)
        _chemin(id_, dossier).unlink(missing_ok=True)


def retirer(id_, *, dossier=None):
    """Après une création : les usages sont déjà versés au projet, rien n'est gardé."""
    with _VERROU:
        _chemin(id_, dossier).unlink(missing_ok=True)


def purger(*, maintenant, dossier=None, commun=None):
    """Abandonne les brouillons sans changement depuis plus de 30 jours (sauf un tour en cours). Rend leurs id."""
    limite = _iso(maintenant - timedelta(days=JOURS_PURGE))
    purges = []
    for x in lister(dossier=dossier):
        if x["maj"] and x["maj"] < limite and x["tour"] != "en_cours":
            try:
                abandonner(x["id"], dossier=dossier, commun=commun)
            except Echec:
                continue
            purges.append(x["id"])
    return purges


def usages_abandonnes(*, commun=None):
    c = _commun(commun)
    try:
        lignes = c.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    sortie = []
    for ligne in lignes:
        try:
            u = json.loads(ligne)
        except ValueError:
            continue
        if isinstance(u, dict):
            sortie.append(u)
    return sortie
