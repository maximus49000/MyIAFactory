"""Une seule campagne de tests à la fois sur le poste : deux suites lancées ensemble se disputent la mémoire, le disque
et le processeur, et chacune devient jusqu'à dix fois plus lente (mesure du 2026-11-16 : 1 861 s au lieu de 253 s).

Le verrou est `~/MyIAFactory/tests-en-cours.json` ({pid, debut, racine}) ; celui d'un processus mort est repris. Une
suite lancée sans le lanceur (`python -m unittest …`, `vitest run`, `jest`, `playwright test`) ne prend pas le verrou :
elle est repérée parmi les processus du poste, et la campagne attend aussi qu'elle finisse.

Les agents des projets passent par le même verrou (essai réel du 2026-11-17 : deux agents lançaient chacun la suite
vitest du projet en même temps, et chacun attendait plus de six minutes) :
    python <skill>/lancer.py tests [--dossier <dossier>] [--sans-attendre] -- <commande de test>
attend son tour, lance la commande (sa sortie s'affiche telle quelle), rend son code et libère le verrou.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

VERROU = Path("~/MyIAFactory/tests-en-cours.json").expanduser()
# Les campagnes qui attendent leur tour, une par fichier `<pid>.json` ({pid, depuis, racine, tache, motif}) : le bureau
# dit sur la fiche de la tâche que son agent attend le poste (essai réel du 2026-11-18 : Hugo attendait le verrou, sa
# fiche n'en disait rien et l'utilisateur le croyait bloqué). `tache` : la clé de l'agent (`MYIAFACTORY_TACHE`).
ATTENTES = Path("~/MyIAFactory/tests-en-attente").expanduser()
VARIABLE_TACHE = "MYIAFACTORY_TACHE"
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


# Les suites de tests JavaScript lancées sans le verrou (le serveur `vite` seul n'en est pas une).
SUITES_NODE = ("vitest", "jest", "playwright test", "mocha")


def processus():
    """[(pid, ligne de commande)] des processus Python et Node du poste ; liste vide si on ne sait pas les lire."""
    try:
        if sys.platform == "win32":
            p = subprocess.run(["powershell", "-NoProfile", "-Command",
                                "Get-CimInstance Win32_Process -Filter \"Name like 'python%' or Name='py.exe' or Name='node.exe'\" | "
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


def _suite_directe(commande):
    c = commande.lower()
    if "tests_paralleles" in c or "lancer.py" in c:
        return False      # un lanceur : couvert par le verrou
    return "unittest" in c or "pytest" in c or any(n in c for n in SUITES_NODE)


def suites_sans_verrou(lister=processus, moi=None):
    """Les suites lancées directement (`unittest`, `pytest`, `vitest`…), hors celles des lanceurs (couvertes par le
    verrou)."""
    moi = {os.getpid(), os.getppid()} if moi is None else moi
    return [(pid, c) for pid, c in lister() if pid not in moi and _suite_directe(c)]


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


def _noter_l_attente(attentes, racine, motif, depuis):
    try:
        Path(attentes).mkdir(parents=True, exist_ok=True)
        (Path(attentes) / f"{os.getpid()}.json").write_text(json.dumps(
            {"pid": os.getpid(), "depuis": depuis, "racine": str(racine), "tache": os.environ.get(VARIABLE_TACHE) or None,
             "motif": motif}), encoding="utf-8")
    except OSError:
        pass      # une aide pour le bureau : l'attente continue sans elle


def _oublier_l_attente(attentes):
    try:
        (Path(attentes) / f"{os.getpid()}.json").unlink()
    except OSError:
        pass


def en_attente(attentes=ATTENTES, vivant=pid_vivant):
    """Les campagnes qui attendent leur tour, par clé d'agent : `{tache: {depuis, motif}}` (celles d'un processus mort
    ou sans agent sont ignorées). Lecture seule, ne lève jamais."""
    sortie = {}
    try:
        fichiers = sorted(Path(attentes).glob("*.json"))
    except OSError:
        return sortie
    for f in fichiers:
        x = _lire(f)
        if (isinstance(x, dict) and isinstance(x.get("tache"), str) and x["tache"] and vivant(x.get("pid"))
                and x["tache"] not in sortie):
            sortie[x["tache"]] = {"depuis": x.get("depuis"), "motif": x.get("motif")}
    return sortie


def attendre_son_tour(racine, attendre=True, verrou=VERROU, lister=processus, dormir=time.sleep, dire=print,
                      attentes=ATTENTES):
    """Prend le verrou dès que le poste est libre. Rend vrai quand c'est fait, faux si `attendre` est faux et qu'une
    autre campagne tourne. Pendant qu'elle attend, la campagne est notée dans `attentes` (voir `en_attente`)."""
    deja_dit, depuis = None, None
    try:
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
                depuis = depuis or datetime.now().astimezone().isoformat(timespec="seconds")
                _noter_l_attente(attentes, racine, motif, depuis)
                deja_dit = motif
            dormir(PAS_S)
    finally:
        if deja_dit is not None:
            _oublier_l_attente(attentes)


def _lancer(commande, dossier):
    """Lance la commande de test (sous Windows par l'interpréteur de commandes : `npx`, `npm` sont des `.cmd`)."""
    if sys.platform == "win32":
        return subprocess.run(subprocess.list2cmdline(commande), cwd=dossier, shell=True).returncode
    return subprocess.run(commande, cwd=dossier).returncode


def executer(commande, dossier=None, attendre=True, verrou=VERROU, lister=processus, dormir=time.sleep, dire=print,
             lancer=_lancer, attentes=ATTENTES):
    """Les tests d'un projet, une campagne à la fois sur le poste : attend son tour, lance `commande` dans `dossier`,
    rend son code (3 si refusé sans attendre) et libère toujours le verrou."""
    racine = str(Path(dossier or os.getcwd()).resolve())
    if not attendre_son_tour(racine, attendre=attendre, verrou=verrou, lister=lister, dormir=dormir, dire=dire,
                             attentes=attentes):
        return 3
    try:
        return lancer(list(commande), dossier)
    finally:
        liberer(verrou)


def main(argv=None, executer=executer):
    """`lancer.py tests [--dossier D] [--sans-attendre] -- <commande>`."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" not in argv or argv.index("--") == len(argv) - 1:
        print("Usage : lancer.py tests [--dossier <dossier>] [--sans-attendre] -- <commande de test>", file=sys.stderr)
        return 2
    i = argv.index("--")
    options, commande = argv[:i], argv[i + 1:]
    dossier, attendre = None, True
    while options:
        o = options.pop(0)
        if o == "--dossier" and options:
            dossier = options.pop(0)
        elif o == "--sans-attendre":
            attendre = False
        else:
            print(f"Option inconnue : {o}", file=sys.stderr)
            return 2
    return executer(commande, dossier=dossier, attendre=attendre)
