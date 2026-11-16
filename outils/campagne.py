"""Une seule campagne de tests à la fois sur le poste : deux suites lancées ensemble se disputent la mémoire, le disque
et le processeur, et chacune devient jusqu'à dix fois plus lente (mesure du 2026-11-16 : 1 861 s au lieu de 253 s).

Le verrou est `~/MyIAFactory/tests-en-cours.json` ({pid, debut, racine}) ; celui d'un processus mort est repris. Une
suite lancée sans le lanceur (`python -m unittest …`) ne prend pas le verrou : elle est repérée parmi les processus
du poste, et la campagne attend aussi qu'elle finisse.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

VERROU = Path("~/MyIAFactory/tests-en-cours.json").expanduser()
PAS_S = 10


def pid_vivant(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)    # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259    # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def processus():
    """[(pid, ligne de commande)] des processus Python du poste ; liste vide si on ne sait pas les lire."""
    try:
        if sys.platform == "win32":
            p = subprocess.run(["powershell", "-NoProfile", "-Command",
                                "Get-CimInstance Win32_Process -Filter \"Name like 'python%' or Name='py.exe'\" | "
                                "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
                               capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            p = subprocess.run(["ps", "-eo", "pid=,args="], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return []
    sortie = []
    for ligne in p.stdout.decode("utf-8", "replace").splitlines():
        pid, _, commande = ligne.strip().replace("\t", " ", 1).partition(" ")
        if pid.isdigit():
            sortie.append((int(pid), commande))
    return sortie


def suites_sans_verrou(lister=processus, moi=None):
    """Les suites lancées directement (`unittest`, `pytest`), hors celles du lanceur (couvertes par le verrou)."""
    moi = {os.getpid(), os.getppid()} if moi is None else moi
    return [(pid, c) for pid, c in lister() if pid not in moi and "tests_paralleles" not in c
            and ("unittest" in c or "pytest" in c)]


def _lire(verrou):
    try:
        return json.loads(Path(verrou).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def prendre(verrou=VERROU, racine="", vivant=pid_vivant):
    """Pose le verrou pour ce processus. `None` si c'est fait, sinon ce que dit le verrou d'une autre campagne."""
    verrou = Path(verrou)
    verrou.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            fd = os.open(verrou, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            autre = _lire(verrou)
            if autre and vivant(autre.get("pid")) and autre.get("pid") != os.getpid():
                return autre
            try:
                verrou.unlink()       # le verrou d'une campagne morte : repris
            except OSError:
                pass
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "debut": datetime.now().astimezone().isoformat(timespec="seconds"),
                       "racine": str(racine)}, f)
        return None
    return _lire(verrou) or {"pid": None}


def liberer(verrou=VERROU):
    autre = _lire(verrou)
    if autre and autre.get("pid") == os.getpid():
        try:
            Path(verrou).unlink()
        except OSError:
            pass


def attendre_son_tour(racine, attendre=True, verrou=VERROU, lister=processus, dormir=time.sleep, dire=print):
    """Prend le verrou dès que le poste est libre. Rend vrai quand c'est fait, faux si `attendre` est faux et qu'une
    autre campagne tourne."""
    deja_dit = None
    while True:
        autre = prendre(verrou, racine)
        directes = [] if autre else suites_sans_verrou(lister)
        if not autre and not directes:
            return True
        if not autre:
            liberer(verrou)      # une suite lancée sans le lanceur tourne : on lui laisse le poste
        motif = (f"une campagne tourne déjà (processus {autre.get('pid')}, depuis {autre.get('debut')})" if autre
                 else f"une suite lancée sans le lanceur tourne (processus {', '.join(str(p) for p, _ in directes[:3])})")
        if not attendre:
            dire(f"Refusé : {motif}. Une seule campagne de tests à la fois sur le poste.")
            return False
        if motif != deja_dit:
            dire(f"En attente : {motif}. Une seule campagne de tests à la fois sur le poste.", flush=True)
            deja_dit = motif
        dormir(PAS_S)
