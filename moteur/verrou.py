"""Un seul moteur à la fois pour tous les projets du bureau : le verrou est `~/MyIAFactory/moteur.pid` (le numéro du
processus du moteur). Un verrou dont le processus n'existe plus est celui d'un moteur mort : il est repris."""
import os
import sys
from pathlib import Path

VERROU_PAR_DEFAUT = "~/MyIAFactory/moteur.pid"


def chemin_par_defaut():
    return Path(VERROU_PAR_DEFAUT).expanduser()


def pid_vivant(pid):
    """Vrai si un processus de ce numéro tourne. (Sous Windows, `os.kill(pid, 0)` tuerait le processus : on interroge
    le système sans rien lui demander d'autre.)"""
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


def lire(chemin):
    try:
        return int(Path(chemin).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def actif(chemin, vivant=pid_vivant):
    """Le numéro du moteur qui tourne, ou `None`."""
    pid = lire(chemin)
    return pid if pid is not None and vivant(pid) else None


def ecrire(chemin, pid):
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(str(pid), encoding="utf-8")


def prendre(chemin, vivant=pid_vivant, pid=None):
    """Pose le verrou pour ce processus. Rend `True`, ou `False` si un autre moteur tourne déjà."""
    pid = os.getpid() if pid is None else pid
    autre = actif(chemin, vivant)
    if autre is not None and autre not in (pid, os.getppid()):
        return False
    ecrire(chemin, pid)
    return True


def liberer(chemin, pid=None):
    pid = os.getpid() if pid is None else pid
    if lire(chemin) == pid:
        try:
            Path(chemin).unlink()
        except OSError:
            pass
