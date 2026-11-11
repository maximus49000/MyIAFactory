"""Lancer `orchestrateur/outil.py` dans le processus des tests au lieu d'un nouveau Python (0,3 s gagnées par appel).

`outil.main` est appelé tel quel (analyse des arguments, lecture du JSON d'entrée, codes de sortie, écriture JSON) : seules
l'entrée et la sortie standard sont remplacées, sous un verrou. La sortie repasse par JSON, comme à travers un vrai
processus. `MYIAFACTORY_TESTS_CLI=1` remet le vrai lancement en processus séparé partout (contrôle de fond).
"""
import io
import json
import os
import sys
import threading
from contextlib import contextmanager

from orchestrateur import outil

_VERROU = threading.RLock()


def actif():
    return not os.environ.get("MYIAFACTORY_TESTS_CLI")


@contextmanager
def _environnement(extra):
    avant = {k: os.environ.get(k) for k in extra}
    os.environ.update(extra)
    try:
        yield
    finally:
        for k, v in avant.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def lancer(argv, corps=None, env=None):
    """(code, octets de la sortie standard) de `outil.py <argv>` avec `corps` (octets ou None) sur l'entrée standard :
    ce que rendrait `subprocess.run(...)` (`returncode`, `stdout`)."""
    entree = io.TextIOWrapper(io.BytesIO(corps or b""), encoding="utf-8")
    brut = io.BytesIO()
    sortie = io.TextIOWrapper(brut, encoding="utf-8", write_through=True)
    with _VERROU, _environnement(env or {}):
        anciens = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = entree, sortie
        try:
            outil.main([str(a) for a in argv])
            code = 0
        except SystemExit as ex:
            code = ex.code if isinstance(ex.code, int) else (0 if ex.code is None else 1)
        finally:
            sys.stdin, sys.stdout = anciens
    return code, brut.getvalue()


def lancer_verification(chemin, commande, entree=None, args=()):
    """Le remplaçant de `orchestrateur.verifier_interface.lancer` (même contrat), dans le processus des tests."""
    corps = None if entree is None else json.dumps(entree, ensure_ascii=False).encode("utf-8")
    code, brut = lancer(["--factory", str(chemin), "lancer", commande, *args], corps,
                        env={"MYIAFACTORY_VERIFICATION": "1"})
    sortie = brut.decode("utf-8", "replace").strip()
    try:
        objet = json.loads(sortie) if sortie else None
    except ValueError:
        objet = sortie
    return code, objet
