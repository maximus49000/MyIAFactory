"""Une seule campagne de tests à la fois sur le poste : deux suites lancées ensemble se disputent la mémoire, le disque
et le processeur, et chacune devient jusqu'à dix fois plus lente (mesure du 2026-11-16 : 1 861 s au lieu de 253 s).

Le verrou est `~/MyIAFactory/tests-en-cours.json` ({pid, demarre, debut, racine}) ; celui d'un processus mort, ou d'un
pid repris par un autre programme (date de création différente, `vivant_et_meme`), est repris. Une
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
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, List, Optional, Tuple  # noqa: F401 — annotations en commentaires (Python 3.9)

# Le vrai dossier d'état du poste. `VERROU` et `ATTENTES` restent ses vrais chemins (la garde des tests les refuse) ;
# les fonctions les résolvent à l'appel par `dossier_etat()`, jamais par une valeur par défaut figée à l'import.
DOSSIER_ETAT = Path("~/MyIAFactory").expanduser()
VERROU = DOSSIER_ETAT / "tests-en-cours.json"
# Les campagnes qui attendent leur tour, une par fichier `<pid>.json` ({pid, demarre, depuis, racine, tache, motif}) :
# le bureau dit sur la fiche de la tâche que son agent attend le poste (essai réel du 2026-11-18 : Hugo attendait le
# verrou, sa fiche n'en disait rien et l'utilisateur le croyait bloqué). `tache` : la clé de l'agent
# (`MYIAFACTORY_TACHE`). `demarre` : la date de création du processus ; `empreinte` (Linux) : boot et starttime en
# tops (voir `vivant_et_meme`). Champs facultatifs : une note qui ne les a pas suit l'ancienne règle.
ATTENTES = DOSSIER_ETAT / "tests-en-attente"
VARIABLE_TACHE = "MYIAFACTORY_TACHE"
# Posée par le lanceur de la suite (`outils/tests_paralleles.py`) pour chaque processus de test, jamais pour lui-même :
# un test qui appelle `executer` ou `attendre_son_tour` sans chemins n'atteint plus le vrai verrou ni la vraie file
# (blocages du 2026-11-23 : un test attendait derrière une campagne qui attendait le verrou tenu par son propre parent).
VARIABLE_ETAT = "MYIAFACTORY_ETAT_TESTS"
# Le nom du dossier que crée le lanceur sous le dossier temporaire ; une autre valeur de la variable est ignorée.
PREFIXE_ETAT = "myiafactory-etat-tests-"
PAS_S = 10
# Ancienne note (sans date de création) : écart toléré avec la date écrite dans la note (arrondie à la seconde).
TOLERANCE_S = 2.0
# Note récente sous Windows : la date de création (FILETIME, fixée par le noyau) relue doit être la même.
TOLERANCE_DEMARRE_S = 0.05


def _etat_isole():
    """Le dossier de `VARIABLE_ETAT` s'il est honoré : il existe, sous le dossier temporaire, et son premier dossier
    sous celui-ci commence par `PREFIXE_ETAT` (ce que crée `tests_paralleles`). Sinon `None` : le vrai poste."""
    v = os.environ.get(VARIABLE_ETAT, "").strip()
    if not v:
        return None
    try:
        import tempfile
        p = Path(v).resolve()
        racines = {os.path.normcase(str(Path(t).resolve())) for t in (tempfile.gettempdir(), os.environ.get("TEMP"))
                   if t}
        chemin = os.path.normcase(str(p))
        for r in racines:
            if chemin.startswith(r.rstrip("\\/") + os.sep):
                premier = chemin[len(r.rstrip("\\/")) + 1:].split(os.sep)[0]
                if premier.startswith(PREFIXE_ETAT) and p.is_dir():
                    return p
    except (OSError, ValueError, RuntimeError):
        pass
    return None


def isole():
    """Vrai dans un processus de test lancé par le lanceur de la suite (`VARIABLE_ETAT` posée et honorée)."""
    return _etat_isole() is not None


def dossier_etat():
    """Le dossier où vivent le verrou et la file : celui de `VARIABLE_ETAT` dans un processus de test, sinon le vrai
    `~/MyIAFactory`. Résolu à chaque appel (`tests_serveur.ATTENTES_SERVEUR` pourra s'y ranger)."""
    return _etat_isole() or DOSSIER_ETAT


def _dire_isole():
    if isole():
        print(f"campagne isolée (test) : {dossier_etat()}", file=sys.stderr, flush=True)


def verrou_par_defaut():
    return VERROU if not isole() else dossier_etat() / VERROU.name


def attentes_par_defaut():
    return ATTENTES if not isole() else dossier_etat() / ATTENTES.name


def pid_vivant(pid):
    """Le pid tourne-t-il ? Sous Windows, un processus qu'on ne peut pas ouvrir (accès refusé : processus protégé)
    compte pour mort, comme depuis le début : son verrou serait repris. Un processus fini dont le code de sortie vaut
    259 (STILL_ACTIVE) passerait pour vivant. POSIX : un zombie répond encore à `kill(pid, 0)` (voir `_lire_proc`)."""
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


_EPOQUE_WINDOWS_S = 11644473600      # du 1601-01-01 (FILETIME) au 1970-01-01


def _demarrage_windows(pid):
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)    # une instance à nous : les prototypes ne débordent pas
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k.GetProcessTimes.restype = wintypes.BOOL
    k.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    k.GetExitCodeProcess.restype = wintypes.BOOL
    k.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    k.CloseHandle.argtypes = (wintypes.HANDLE,)
    h = k.OpenProcess(0x1000, False, pid)    # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False, None
    try:
        code = wintypes.DWORD()
        if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:    # STILL_ACTIVE
            return False, None
        t = [wintypes.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(h, *(ctypes.byref(x) for x in t)):
            return True, None
        cent_ns = (t[0].dwHighDateTime << 32) | t[0].dwLowDateTime
        return True, cent_ns / 1e7 - _EPOQUE_WINDOWS_S
    finally:
        k.CloseHandle(h)


def _lire_texte(chemin):
    return Path(chemin).read_text()


def _lire_proc(pid, lire=_lire_texte, tops_par_s=None):
    """Linux : `(etat, epoch, empreinte)` du processus, `None` si `/proc/<pid>/stat` est illisible. `empreinte` :
    `<boot_id>:<starttime>` (22e champ, en tops depuis le démarrage), comparée telle quelle : elle ne bouge pas quand
    l'horloge murale saute (NTP). `epoch` (`btime` + starttime) ne sert qu'à la règle des anciennes notes. `etat` : la
    lettre d'état (`Z` : zombie, fini mais pas encore récolté)."""
    try:
        stat = lire(f"/proc/{pid}/stat")
        champs = stat[stat.rindex(")") + 2:].split()      # le nom du programme peut contenir espaces et parenthèses
        etat, tops = champs[0], int(champs[19])
    except (OSError, ValueError, IndexError):
        return None
    try:
        boot = lire("/proc/sys/kernel/random/boot_id").strip()
    except OSError:
        boot = "?"
    epoch = None
    try:
        for ligne in lire("/proc/stat").splitlines():
            if ligne.startswith("btime "):
                epoch = int(ligne.split()[1]) + tops / (tops_par_s or os.sysconf("SC_CLK_TCK"))
    except (OSError, ValueError, AttributeError):
        pass
    return etat, epoch, f"{boot}:{tops}"


def _etat_reel(pid):
    """`(vivant, demarre, empreinte)` : le processus `pid` existe-t-il, sa date de création (secondes depuis 1970,
    `None` si on ne sait pas la lire) et, sous Linux, son empreinte exacte (`_lire_proc`). Ne lève jamais."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False, None, None
    try:
        if sys.platform == "win32":
            vivant, demarre = _demarrage_windows(pid)
            return vivant, demarre, None
        if not pid_vivant(pid):
            return False, None, None
        lu = _lire_proc(pid)
        if lu is None:
            return True, None, None
        if lu[0] == "Z":
            return False, None, None      # zombie : la campagne est finie
        return True, lu[1], lu[2]
    except Exception:  # noqa: BLE001 — repli : la seule existence du pid, comme avant
        return pid_vivant(pid), None, None


etat_processus = _etat_reel      # remplacé dans les tests ; `mon_identite` lit toujours le vrai
_MON_IDENTITE = {}


def mon_identite():
    """`(demarre, empreinte)` de ce processus (gardés par pid : un fils né d'un `fork` relit les siens), notés dans le
    verrou et la file."""
    pid = os.getpid()
    if pid not in _MON_IDENTITE:
        _MON_IDENTITE[pid] = tuple(_etat_reel(pid)[1:3])
    return _MON_IDENTITE[pid]


def mon_demarrage():
    return mon_identite()[0]


def _ma_note():
    demarre, empreinte = mon_identite()
    note = {"pid": os.getpid(), "demarre": demarre}
    if empreinte:
        note["empreinte"] = empreinte
    return note


def _nombre(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _epoque(texte):
    """Une date ISO (`depuis`, `debut`) en secondes depuis 1970 ; `None` si elle est absente, illisible ou sans fuseau."""
    if not isinstance(texte, str):
        return None
    try:
        d = datetime.fromisoformat(texte)
    except ValueError:
        return None
    return d.timestamp() if d.tzinfo is not None else None


def vivant_et_meme(pid, demarre_epoch=None, note_epoch=None, etat=None, empreinte=None):
    """Le processus d'une note (file ou verrou) tourne-t-il encore, et est-ce bien LE MÊME ? Un pid repris par un autre
    programme (essai réel du 2026-11-23 : la note `23232.json` d'une campagne morte, son pid repris par un `conhost.exe`,
    retenait la file sans fin) n'est plus pris pour la campagne :
    - Linux, `empreinte` notée : boot et starttime en tops, égaux exactement (aucune horloge murale en jeu) ;
    - Windows, `demarre_epoch` noté : la date de création (FILETIME) à `TOLERANCE_DEMARRE_S` près ;
    - sinon (ancienne note) `note_epoch`, la date écrite dans la note : un processus créé après elle, à `TOLERANCE_S`
      près, n'est pas le sien ;
    - identité illisible : la seule existence du pid, comme avant.
    `etat(pid)` : `etat_processus` par défaut (remplacé dans les tests), `(vivant, demarre[, empreinte])`."""
    lu = tuple((etat or etat_processus)(pid))
    vivant, reel = lu[0], lu[1]
    empreinte_reelle = lu[2] if len(lu) > 2 else None
    if not vivant:
        return False
    if isinstance(empreinte, str) and empreinte and empreinte_reelle:
        return empreinte == empreinte_reelle
    demarre = _nombre(demarre_epoch)
    if demarre is not None and reel is not None and not empreinte_reelle:
        return abs(reel - demarre) <= TOLERANCE_DEMARRE_S
    note = _nombre(note_epoch)
    if note is not None and reel is not None:
        return reel <= note + TOLERANCE_S
    return True


def _note_vivante(note, vivant, date="depuis"):
    """Une note de la file ou du verrou est-elle celle d'une campagne en vie ? `vivant` : `None` (défaut, identité
    complète par `vivant_et_meme`) ou un prédicat sur le pid (tests anciens)."""
    pid = note.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool):
        return False
    if vivant is not None:
        return bool(vivant(pid))
    return vivant_et_meme(pid, note.get("demarre"), _epoque(note.get(date)), empreinte=note.get("empreinte"))


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
    if "tests_paralleles" in c or "lancer.py" in c or re.search(r"(^|[\s\\/\"'])tests_serveur\.py", c):
        return False      # un lanceur (ou la route serveur, qui ne lance rien au poste) : couvert par le verrou
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


def _age_s(chemin):
    """L'âge du fichier ; une date dans le futur (horloge reculée) compte pour vieille."""
    try:
        age = time.time() - Path(chemin).stat().st_mtime
    except OSError:
        return float("inf")
    return age if age >= 0 else float("inf")


def _lire_verrou(verrou):
    """`(statut, contenu)` : `absent` (disparu entre-temps), `illisible` (partage refusé, accès refusé…), `invalide`
    (vide, pas du JSON, pas un objet) ou `ok`."""
    try:
        brut = Path(verrou).read_text(encoding="utf-8")
    except FileNotFoundError:
        return "absent", None
    except UnicodeDecodeError:
        return "invalide", None
    except OSError:
        return "illisible", None
    try:
        x = json.loads(brut)
    except ValueError:
        return "invalide", None
    return ("ok", x) if isinstance(x, dict) else ("invalide", None)


def prendre(verrou=None, racine="", vivant=None):
    """Pose le verrou pour ce processus. `None` si c'est fait, sinon ce que dit le verrou d'une autre campagne. Le
    verrou d'une campagne morte, ou dont le pid a été repris par un autre processus (`vivant_et_meme`, date `debut`),
    est repris. Un verrou qu'on ne peut pas lire (partage ou accès refusé) n'est jamais effacé : on attend. Un verrou
    vide ou invalide n'est repris qu'au-delà de `TOLERANCE_S` (une autre campagne vient peut-être de le créer). `vivant` :
    prédicat sur le pid (tests) ; par défaut l'identité complète."""
    verrou = Path(verrou_par_defaut() if verrou is None else verrou)
    verrou.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            fd = os.open(verrou, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            statut, autre = _lire_verrou(verrou)
            if statut == "absent":
                continue              # libéré entre-temps : on retente
            if statut == "illisible":
                return {"pid": None}
            if statut == "ok" and autre.get("pid") != os.getpid() and _note_vivante(autre, vivant, "debut"):
                return autre
            if statut == "invalide" and _age_s(verrou) < TOLERANCE_S:
                return {"pid": None}      # créé à l'instant par une autre campagne, pas encore écrit : pas repris
            try:
                verrou.unlink()       # le verrou d'une campagne morte : repris
            except OSError:
                return {"pid": None}
            continue
        except OSError:
            return {"pid": None}      # Windows : verrou en cours d'effacement (accès refusé) ; on attend
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({**_ma_note(), "debut": datetime.now().astimezone().isoformat(timespec="seconds"),
                       "racine": str(racine)}, f)
        return None
    return _lire(verrou) or {"pid": None}


def liberer(verrou=None):
    verrou = verrou_par_defaut() if verrou is None else verrou
    autre = _lire(verrou)
    if isinstance(autre, dict) and autre.get("pid") == os.getpid():
        try:
            Path(verrou).unlink()
        except OSError:
            pass


def _noter_l_attente(attentes, racine, motif, depuis, arrivee):
    try:
        Path(attentes).mkdir(parents=True, exist_ok=True)
        (Path(attentes) / f"{os.getpid()}.json").write_text(json.dumps(
            {**_ma_note(), "depuis": depuis, "arrivee": arrivee,
             "racine": str(racine), "tache": os.environ.get(VARIABLE_TACHE) or None, "motif": motif}),
            encoding="utf-8")
    except OSError:
        pass      # une aide pour le bureau : l'attente continue sans elle


def _oublier_l_attente(attentes):
    try:
        (Path(attentes) / f"{os.getpid()}.json").unlink()
    except OSError:
        pass


def _file(attentes, vivant=None):
    """Les campagnes vivantes qui attendent, dans leur ordre d'arrivée : `[(arrivee, pid, note)]`. Une note sans
    `arrivee` (ancienne version) prend la date du fichier. Une note dont le pid tourne encore mais n'est plus le même
    processus (`vivant_et_meme`) est ignorée. Lecture seule, ne lève jamais."""
    try:
        fichiers = list(Path(attentes).glob("*.json"))
    except OSError:
        return []
    file = []
    for f in fichiers:
        x = _lire(f)
        if not isinstance(x, dict) or not _note_vivante(x, vivant):
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


def _devant(attentes, arrivee, vivant=None):
    """Les campagnes qui attendent avant nous (toutes, tant que nous ne sommes pas encore dans la file)."""
    moi = os.getpid()
    return [e for e in _file(attentes, vivant)
            if e[1] != moi and (arrivee is None or (e[0], e[1]) < (arrivee, moi))]


def en_attente(attentes=None, vivant=None):
    """Les campagnes qui attendent leur tour, par clé d'agent : `{tache: {depuis, motif, rang, total}}` ; `rang` est la
    position dans la file (1 : la prochaine à passer), `total` le nombre de campagnes qui attendent (celles sans agent
    comptent dans la file ; celles d'un processus mort sont ignorées). Lecture seule, ne lève jamais."""
    sortie = {}
    file = _file(attentes_par_defaut() if attentes is None else attentes, vivant)
    for rang, (_, _, x) in enumerate(file, 1):
        if isinstance(x.get("tache"), str) and x["tache"] and x["tache"] not in sortie:
            sortie[x["tache"]] = {"depuis": x.get("depuis"), "motif": x.get("motif"), "rang": rang, "total": len(file)}
    return sortie


def _lister_par_defaut():
    """Les processus du poste, sauf dans un processus de test isolé (`VARIABLE_ETAT`) : ses voisins `unittest` de la
    même suite y passeraient pour des suites sans verrou, et deux tests s'attendraient l'un l'autre sans fin."""
    return (lambda: []) if isole() else processus


def attendre_son_tour(racine, attendre=True, verrou=None, lister=None, dormir=time.sleep, dire=print,
                      attentes=None):
    """Prend le verrou dès que le poste est libre et que personne n'attend avant nous (premier arrivé, premier servi :
    le bureau affiche la position dans la file, elle doit dire vrai). Rend vrai quand c'est fait, faux si `attendre`
    est faux et que le poste est pris. Pendant qu'elle attend, la campagne est notée dans `attentes` (voir
    `en_attente`). Sans `verrou`, `attentes`, `lister` : ceux du poste, résolus à l'appel (`dossier_etat`)."""
    verrou = verrou_par_defaut() if verrou is None else verrou
    attentes = attentes_par_defaut() if attentes is None else attentes
    lister = _lister_par_defaut() if lister is None else lister
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


def _env_de_la_commande(env=None, base=None):
    """L'environnement hérité (`base`, défaut `os.environ`) plus `env`, sans `VARIABLE_ETAT` ; `None` (hériter tel
    quel) quand il n'y a rien à changer."""
    base = os.environ if base is None else base
    if not env and VARIABLE_ETAT not in base:
        return None
    complet = {k: v for k, v in base.items() if k != VARIABLE_ETAT}
    complet.update({k: v for k, v in (env or {}).items() if k != VARIABLE_ETAT})
    return complet


def _lancer(commande, dossier, env=None, sortie=None):
    # type: (List[str], Optional[str], Optional[dict], Optional[BinaryIO]) -> Tuple[int, int, str]
    """Lance la commande de test (sous Windows par l'interpréteur de commandes : `npx`, `npm` sont des `.cmd`), sa
    sortie et ses erreurs relayées vers `sortie` (par défaut celle du lanceur) par `relayer`, qui compte les octets et
    garde la fin. Rend `(code, octets, fin)`. `env` : des variables ajoutées à l'environnement hérité (ex. le chemin
    d'un artefact téléchargé). Une interruption tue la commande et remonte (comme `subprocess.run`). `VARIABLE_ETAT`
    n'est jamais transmise : les tests d'un projet prennent le vrai verrou, même lancés depuis un test isolé."""
    complet = _env_de_la_commande(env)
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
    if isole():     # un test : jamais le vrai bureau ni le vrai sceau (aucun projet enregistré là : rien n'est noté)
        mesure.setdefault("bureau", dossier_etat() / "bureau.json")
        mesure.setdefault("sceau", dossier_etat() / "tests-sceau.json")
    return tests_mesures.noter_campagne(racine, **mesure)


def executer(commande, dossier=None, attendre=True, verrou=None, lister=None, dormir=time.sleep, dire=print,
             lancer=_lancer, attentes=None, env=None, horloge=time.monotonic, noter=None):
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
    _dire_isole()
    verrou = verrou_par_defaut() if verrou is None else verrou      # résolu une fois : pris et libéré au même endroit
    attentes = attentes_par_defaut() if attentes is None else attentes
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
