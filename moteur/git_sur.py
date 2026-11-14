"""Git sans collision dans le dépôt d'un projet.

Cas réels (MyFridgeCleaner, sessions cloud en parallèle) : « cannot lock ref », « Your local changes … would be
overwritten », « Unable to create '.git/index.lock': File exists ». Deux règles :
- `verrou(dossier)` : les opérations git du moteur sur un même dépôt passent une à une (un verrou par dépôt, partagé
  par tous les fils du moteur), y compris les suites de plusieurs commandes (fusion puis envoi) ;
- `executer(...)` : une commande refusée parce qu'un autre git tient `index.lock` (un agent local, le bureau) est
  réessayée ; un verrou abandonné (plus vieux que `VERROU_ABANDONNE_S`, aucun git ne l'ayant repris) est retiré.
"""
import os
import threading
import time
from pathlib import Path

ESSAIS_INDEX = 20
PAUSE_INDEX_S = 1.5
VERROU_ABANDONNE_S = 120
_MARQUES_INDEX = ("index.lock", "Unable to create", "Another git process seems to be running")

_verrous = {}
_garde = threading.Lock()


def verrou(dossier):
    """Le verrou (réentrant) du dépôt `dossier` : `with git_sur.verrou(d): …`."""
    cle = os.path.normcase(os.path.abspath(str(dossier)))
    with _garde:
        return _verrous.setdefault(cle, threading.RLock())


def _texte(sortie):
    if isinstance(sortie, bytes):
        return sortie.decode("utf-8", errors="replace")
    return str(sortie or "")


def index_pris(sortie):
    t = _texte(sortie)
    return "index.lock" in t and any(m in t for m in _MARQUES_INDEX)


def retirer_si_abandonne(dossier, maintenant=None):
    """Retire `.git/index.lock` s'il est plus vieux que `VERROU_ABANDONNE_S` (un git interrompu l'a laissé). Vrai si
    retiré."""
    chemin = Path(dossier) / ".git" / "index.lock"
    try:
        age = (maintenant or time.time()) - chemin.stat().st_mtime
    except OSError:
        return False
    if age < VERROU_ABANDONNE_S:
        return False
    try:
        chemin.unlink()
        return True
    except OSError:
        return False


def executer(lancer, dossier, argv, *, pause=None):
    """`lancer(argv)` → `(code, sortie)`, sous le verrou du dépôt, réessayé tant qu'un autre git tient l'index."""
    pause = PAUSE_INDEX_S if pause is None else pause
    with verrou(dossier):
        for essai in range(ESSAIS_INDEX):
            code, sortie = lancer(argv)
            if code == 0 or not index_pris(sortie) or essai == ESSAIS_INDEX - 1:
                return code, sortie
            retirer_si_abandonne(dossier)
            time.sleep(pause)
    return code, sortie
