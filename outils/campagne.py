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
import codecs
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, List, Optional, Tuple  # noqa: F401 — annotations en commentaires (Python 3.9)

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


def _noter_l_attente(attentes, racine, motif, depuis, arrivee):
    try:
        Path(attentes).mkdir(parents=True, exist_ok=True)
        (Path(attentes) / f"{os.getpid()}.json").write_text(json.dumps(
            {"pid": os.getpid(), "depuis": depuis, "arrivee": arrivee, "racine": str(racine),
             "tache": os.environ.get(VARIABLE_TACHE) or None, "motif": motif}), encoding="utf-8")
    except OSError:
        pass      # une aide pour le bureau : l'attente continue sans elle


def _oublier_l_attente(attentes):
    try:
        (Path(attentes) / f"{os.getpid()}.json").unlink()
    except OSError:
        pass


def _file(attentes, vivant=pid_vivant):
    """Les campagnes vivantes qui attendent, dans leur ordre d'arrivée : `[(arrivee, pid, note)]`. Une note sans
    `arrivee` (ancienne version) prend la date du fichier. Lecture seule, ne lève jamais."""
    try:
        fichiers = list(Path(attentes).glob("*.json"))
    except OSError:
        return []
    file = []
    for f in fichiers:
        x = _lire(f)
        if not isinstance(x, dict) or not isinstance(x.get("pid"), int) or not vivant(x["pid"]):
            continue
        arrivee = x.get("arrivee")
        if not isinstance(arrivee, (int, float)) or isinstance(arrivee, bool):
            try:
                arrivee = f.stat().st_mtime
            except OSError:
                continue
        file.append((float(arrivee), x["pid"], x))
    file.sort(key=lambda e: (e[0], e[1]))
    return file


def _devant(attentes, arrivee, vivant=pid_vivant):
    """Les campagnes qui attendent avant nous (toutes, tant que nous ne sommes pas encore dans la file)."""
    moi = os.getpid()
    return [e for e in _file(attentes, vivant)
            if e[1] != moi and (arrivee is None or (e[0], e[1]) < (arrivee, moi))]


def en_attente(attentes=ATTENTES, vivant=pid_vivant):
    """Les campagnes qui attendent leur tour, par clé d'agent : `{tache: {depuis, motif, rang, total}}` ; `rang` est la
    position dans la file (1 : la prochaine à passer), `total` le nombre de campagnes qui attendent (celles sans agent
    comptent dans la file ; celles d'un processus mort sont ignorées). Lecture seule, ne lève jamais."""
    sortie = {}
    file = _file(attentes, vivant)
    for rang, (_, _, x) in enumerate(file, 1):
        if isinstance(x.get("tache"), str) and x["tache"] and x["tache"] not in sortie:
            sortie[x["tache"]] = {"depuis": x.get("depuis"), "motif": x.get("motif"), "rang": rang, "total": len(file)}
    return sortie


def attendre_son_tour(racine, attendre=True, verrou=VERROU, lister=processus, dormir=time.sleep, dire=print,
                      attentes=ATTENTES):
    """Prend le verrou dès que le poste est libre et que personne n'attend avant nous (premier arrivé, premier servi :
    le bureau affiche la position dans la file, elle doit dire vrai). Rend vrai quand c'est fait, faux si `attendre`
    est faux et que le poste est pris. Pendant qu'elle attend, la campagne est notée dans `attentes` (voir
    `en_attente`)."""
    deja_dit, depuis, arrivee = None, None, None
    try:
        while True:
            devant = _devant(attentes, arrivee)
            autre = None if devant else prendre(verrou, racine)
            directes = [] if (autre or devant) else suites_sans_verrou(lister)
            if not autre and not directes and not devant:
                return True
            if not autre and not devant:
                liberer(verrou)      # une suite lancée sans le lanceur tourne : on lui laisse le poste
            if autre:
                motif = f"une campagne tourne déjà (processus {autre.get('pid')}, depuis {autre.get('debut')})"
            elif devant:
                motif = (f"{len(devant)} campagne{'s' if len(devant) > 1 else ''} attend"
                         f"{'ent' if len(devant) > 1 else ''} avant elle")
            else:
                motif = f"une suite lancée sans le lanceur tourne (processus {', '.join(str(p) for p, _ in directes[:3])})"
            if not attendre:
                dire(f"Refusé : {motif}. Une seule campagne de tests à la fois sur le poste.")
                return False
            if motif != deja_dit:
                dire(f"En attente : {motif}. Une seule campagne de tests à la fois sur le poste.", flush=True)
                depuis = depuis or datetime.now().astimezone().isoformat(timespec="seconds")
                arrivee = arrivee or time.time()
                _noter_l_attente(attentes, racine, motif, depuis, arrivee)
                deja_dit = motif
            dormir(PAS_S)
    finally:
        if deja_dit is not None:
            _oublier_l_attente(attentes)


def relayer(entree, sortie, garder=4096, morceau=65536):
    # type: (BinaryIO, Optional[BinaryIO], int, int) -> Tuple[int, str]
    """Copie `entree` vers `sortie` morceau par morceau, telle quelle et dans l'ordre (`flush` après chaque morceau,
    `read1` quand le flux l'a : on rend ce qui est arrivé sans attendre un morceau plein). Rend `(octets, fin)` : le
    nombre d'octets lus et le décodage `utf-8`/`replace` des `garder` derniers (seuls gardés en mémoire ; jamais
    d'erreur de décodage). Une `sortie` nulle ou qui casse (l'agent a fermé son tuyau) n'arrête pas la lecture :
    l'entrée est vidée jusqu'au bout, la commande n'est jamais bloquée sur un tuyau plein."""
    lire = getattr(entree, "read1", None) or entree.read
    octets, fin = 0, b""
    while True:
        b = lire(morceau)
        if not b:
            break
        octets += len(b)
        fin = b[-garder:] if len(b) >= garder else (fin + b)[-garder:]
        if sortie is not None:
            try:
                sortie.write(b)
                sortie.flush()
            except (OSError, ValueError):
                sortie = None      # sortie fermée : on continue de vider l'entrée sans rien écrire
    return octets, bytes(fin).decode("utf-8", "replace")


class _VersTexte:
    """Une sortie binaire posée sur un flux texte sans `buffer` (`sys.stdout` remplacé) : décodage incrémental."""

    def __init__(self, flux):
        self.flux = flux
        self.decodeur = codecs.getincrementaldecoder("utf-8")("replace")

    def write(self, b):
        self.flux.write(self.decodeur.decode(b))

    def flush(self):
        self.flux.flush()


def _sortie_du_poste():
    flux = sys.stdout
    if flux is None:
        return None
    try:
        flux.flush()      # ce que le lanceur a déjà dit passe avant la sortie de la commande
    except (OSError, ValueError):
        pass
    tampon = getattr(flux, "buffer", None)
    return tampon if tampon is not None else _VersTexte(flux)


def _lancer(commande, dossier, env=None, sortie=None):
    # type: (List[str], Optional[str], Optional[dict], Optional[BinaryIO]) -> Tuple[int, int, str]
    """Lance la commande de test (sous Windows par l'interpréteur de commandes : `npx`, `npm` sont des `.cmd`), sa
    sortie et ses erreurs relayées vers `sortie` (par défaut celle du lanceur) par `relayer`, qui compte les octets et
    garde la fin. Rend `(code, octets, fin)`. `env` : des variables ajoutées à l'environnement hérité (ex. le chemin
    d'un artefact téléchargé). Une interruption tue la commande et remonte (comme `subprocess.run`)."""
    complet = dict(os.environ, **env) if env else None
    if sortie is None:
        sortie = _sortie_du_poste()
    if sys.platform == "win32":
        p = subprocess.Popen(subprocess.list2cmdline(commande), cwd=dossier, shell=True, env=complet,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    else:
        p = subprocess.Popen(commande, cwd=dossier, env=complet, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    with p:
        try:
            octets, fin = relayer(p.stdout, sortie)
            code = p.wait()
        except BaseException:
            p.kill()
            raise
    return code, octets, fin


def _noter_par_defaut(racine, **mesure):
    """`bureau.tests_mesures.noter_campagne`, importé seulement au moment de noter (le dossier de la skill est ajouté
    au chemin d'import s'il n'y est pas)."""
    try:
        from bureau import tests_mesures
    except ImportError:
        sys.path.append(str(Path(__file__).resolve().parent.parent))
        from bureau import tests_mesures
    return tests_mesures.noter_campagne(racine, **mesure)


def executer(commande, dossier=None, attendre=True, verrou=VERROU, lister=processus, dormir=time.sleep, dire=print,
             lancer=_lancer, attentes=ATTENTES, env=None, horloge=time.monotonic, noter=None):
    """Les tests d'un projet, une campagne à la fois sur le poste : attend son tour, lance `commande` dans `dossier`,
    rend son code (3 si refusé sans attendre) et libère toujours le verrou. `env` : variables ajoutées à
    l'environnement de la commande (sans `env`, `lancer` est appelé comme avant, à deux arguments).

    Mesure passive : `attente_s` va de l'appel à la prise du verrou, `duree_s` de la prise du verrou à la fin de la
    commande ; `lancer` rend un code (anciens appelants) ou `(code, octets, fin)`. Après la commande, verrou libéré,
    la campagne est notée par `noter` (défaut : `bureau.tests_mesures.noter_campagne`) ; une mesure qui échoue est tue
    et ne change jamais le code rendu. Refus ou interruption : rien n'est noté."""
    appel = horloge()
    commande = list(commande)
    racine = str(Path(dossier or os.getcwd()).resolve())
    if not attendre_son_tour(racine, attendre=attendre, verrou=verrou, lister=lister, dormir=dormir, dire=dire,
                             attentes=attentes):
        return 3
    try:
        pris = horloge()
        horloge()      # début de la commande
        if env:
            rendu = lancer(list(commande), dossier, env=env)
        else:
            rendu = lancer(list(commande), dossier)
        fini = horloge()
    finally:
        liberer(verrou)
    if isinstance(rendu, tuple) and rendu:
        code = rendu[0]
        octets = rendu[1] if len(rendu) > 1 else None
        fin = rendu[2] if len(rendu) > 2 else ""
    else:
        code, octets, fin = rendu, None, ""
    try:
        (noter or _noter_par_defaut)(racine, commande=" ".join(str(x) for x in commande), duree_s=fini - pris,
                                     attente_s=pris - appel, code=code, fin=fin, octets=octets,
                                     tache=os.environ.get(VARIABLE_TACHE) or None)
    except Exception:  # noqa: BLE001 — la mesure ne casse jamais une campagne
        pass
    return code


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
