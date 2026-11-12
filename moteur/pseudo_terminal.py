"""Le faux terminal : une pseudo-console Windows (ConPTY), pour une commande qui refuse de tourner sans terminal.

Le moteur tourne détaché, sans console ; certaines commandes (`claude --cloud`) exigent pourtant un terminal interactif.
`lancer(argv, …)` crée une pseudo-console invisible (aucune fenêtre : elle n'a pas d'écran, le moteur lit ce qu'elle
affiche), y lance la commande, lit sa sortie (séquences d'échappement retirées par `nettoyer`), envoie si besoin une
entrée, impose un délai et arrête le processus proprement (fin du processus, puis fermeture de la pseudo-console).

Uniquement la bibliothèque standard (`ctypes`). Hors Windows (ou Windows trop ancien, sans `CreatePseudoConsole`) :
`disponible()` rend `False` et `lancer` lève `PseudoTerminalIndisponible`.
"""
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

LARGEUR, HAUTEUR = 200, 50


class PseudoTerminalIndisponible(Exception):
    """Pas de pseudo-console sur ce poste (hors Windows, ou Windows sans ConPTY)."""


@dataclass
class Resultat:
    code: object          # le code de sortie, `None` si le processus a été arrêté
    texte: str            # la sortie, nettoyée
    brut: str             # la sortie telle quelle (séquences d'échappement comprises)
    fini: bool            # le processus s'est terminé seul
    arrete: bool = False  # arrêté parce que `arret(texte)` a rendu vrai


# --- Le nettoyage de la sortie : ce qu'un terminal afficherait, à peu près, en texte simple.

_LIEN = re.compile(r"\x1b\]8;[^;\x07\x1b]*;([^\x07\x1b]*)(?:\x07|\x1b\\)(.*?)\x1b\]8;[^;\x07\x1b]*;(?:\x07|\x1b\\)", re.S)
_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_DROITE = re.compile(r"\x1b\[(\d*)C")
_POSITION = re.compile(r"\x1b\[[\d;]*[Hf]|\x1b\[\d*[BE]")
_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_AUTRES = re.compile(r"\x1b[@-Z\\-_]|\x1b[()][0-9A-Za-z]|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _lien(m):
    adresse, texte = m.group(1), m.group(2)
    return texte if not adresse or adresse == texte else f"{texte} <{adresse}>"


def nettoyer(brut):
    t = _LIEN.sub(_lien, brut)
    t = _OSC.sub("", t)
    t = _DROITE.sub(lambda m: " " * int(m.group(1) or 1), t)
    t = _POSITION.sub("\n", t)
    t = _CSI.sub("", t)
    t = _AUTRES.sub("", t)
    t = t.replace("\r\n", "\n").replace("\r", "")
    lignes = [x.rstrip() for x in t.split("\n")]
    return "\n".join(lignes).lstrip("\n")


# --- La pseudo-console.

def disponible():
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return hasattr(ctypes.windll.kernel32, "CreatePseudoConsole")
    except (ImportError, AttributeError, OSError):
        return False


def _bloc_environnement(env):
    if env is None:
        return None
    texte = "".join(f"{k}={v}\0" for k, v in sorted(env.items(), key=lambda kv: kv[0].upper())) + "\0"
    return texte


def lancer(argv, *, cwd, delai_s, env=None, entree=None, arret=None, repondre=None, largeur=LARGEUR,
           hauteur=HAUTEUR):
    """Lance `argv` dans une pseudo-console invisible, dans `cwd`. `entree` (facultatif) est tapée au départ ;
    `arret(texte)` (facultatif), appelé sur la sortie nettoyée, arrête le processus dès qu'il rend vrai ;
    `repondre(texte)` (facultatif) rend ce qu'il faut taper maintenant (ou rien). Au-delà de `delai_s`, le processus
    est arrêté. Rend un `Resultat`."""
    if not disponible():
        raise PseudoTerminalIndisponible("pas de pseudo-console sur ce poste")
    import ctypes
    from ctypes import wintypes as w

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    HANDLE = w.HANDLE

    class COORD(ctypes.Structure):
        _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [("cb", w.DWORD), ("lpReserved", w.LPWSTR), ("lpDesktop", w.LPWSTR), ("lpTitle", w.LPWSTR),
                    ("dwX", w.DWORD), ("dwY", w.DWORD), ("dwXSize", w.DWORD), ("dwYSize", w.DWORD),
                    ("dwXCountChars", w.DWORD), ("dwYCountChars", w.DWORD), ("dwFillAttribute", w.DWORD),
                    ("dwFlags", w.DWORD), ("wShowWindow", w.WORD), ("cbReserved2", w.WORD),
                    ("lpReserved2", ctypes.c_void_p), ("hStdInput", HANDLE), ("hStdOutput", HANDLE),
                    ("hStdError", HANDLE)]

    class STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", HANDLE), ("hThread", HANDLE), ("dwProcessId", w.DWORD), ("dwThreadId", w.DWORD)]

    k32.CreatePipe.argtypes = [ctypes.POINTER(HANDLE), ctypes.POINTER(HANDLE), ctypes.c_void_p, w.DWORD]
    k32.CreatePseudoConsole.argtypes = [COORD, HANDLE, HANDLE, w.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    k32.CreatePseudoConsole.restype = ctypes.c_long
    k32.ClosePseudoConsole.argtypes = [ctypes.c_void_p]
    k32.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.POINTER(ctypes.c_size_t)]
    k32.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, w.DWORD, ctypes.c_size_t, ctypes.c_void_p,
                                              ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    k32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    k32.CreateProcessW.argtypes = [w.LPCWSTR, w.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, w.BOOL, w.DWORD,
                                   ctypes.c_void_p, w.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p]
    k32.ReadFile.argtypes = [HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
    k32.WriteFile.argtypes = [HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
    k32.WaitForSingleObject.argtypes = [HANDLE, w.DWORD]
    k32.WaitForSingleObject.restype = w.DWORD
    k32.GetExitCodeProcess.argtypes = [HANDLE, ctypes.POINTER(w.DWORD)]
    k32.TerminateProcess.argtypes = [HANDLE, ctypes.c_uint]
    k32.CloseHandle.argtypes = [HANDLE]

    PSEUDOCONSOLE = 0x00020016
    EXTENDED_STARTUPINFO_PRESENT = 0x00080000
    CREATE_UNICODE_ENVIRONMENT = 0x00000400
    STARTF_USESTDHANDLES = 0x00000100
    ATTENTE_FINIE = 0

    def _ouvrir_tube():
        lecture, ecriture = HANDLE(), HANDLE()
        if not k32.CreatePipe(ctypes.byref(lecture), ctypes.byref(ecriture), None, 0):
            raise OSError(ctypes.get_last_error(), "CreatePipe")
        return lecture, ecriture

    a_fermer = []

    def _fermer(h):
        if h and h.value:
            k32.CloseHandle(h)
            h.value = None

    entree_console, entree_moteur = _ouvrir_tube()      # le moteur écrit → la console lit
    sortie_moteur, sortie_console = _ouvrir_tube()      # la console écrit → le moteur lit
    a_fermer += [entree_console, entree_moteur, sortie_moteur, sortie_console]
    console = ctypes.c_void_p()
    hr = k32.CreatePseudoConsole(COORD(largeur, hauteur), entree_console, sortie_console, 0, ctypes.byref(console))
    if hr != 0:
        for h in a_fermer:
            _fermer(h)
        raise PseudoTerminalIndisponible(f"CreatePseudoConsole a échoué (0x{hr & 0xffffffff:08x})")

    taille = ctypes.c_size_t(0)
    k32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(taille))
    attributs = ctypes.create_string_buffer(taille.value)
    info_proc = PROCESS_INFORMATION()
    morceaux, verrou = [], threading.Lock()
    lecteur = None
    try:
        if not k32.InitializeProcThreadAttributeList(attributs, 1, 0, ctypes.byref(taille)):
            raise OSError(ctypes.get_last_error(), "InitializeProcThreadAttributeList")
        if not k32.UpdateProcThreadAttribute(attributs, 0, PSEUDOCONSOLE, console, ctypes.sizeof(ctypes.c_void_p),
                                             None, None):
            raise OSError(ctypes.get_last_error(), "UpdateProcThreadAttribute")
        demarrage = STARTUPINFOEXW()
        demarrage.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        # Aucun flux standard hérité : la commande ne voit que la pseudo-console.
        demarrage.StartupInfo.dwFlags = STARTF_USESTDHANDLES
        demarrage.lpAttributeList = ctypes.cast(attributs, ctypes.c_void_p)
        ligne = ctypes.create_unicode_buffer(subprocess.list2cmdline([str(a) for a in argv]))
        bloc = _bloc_environnement(env)
        bloc_c = ctypes.create_unicode_buffer(bloc, len(bloc)) if bloc is not None else None
        if not k32.CreateProcessW(None, ligne, None, None, False,
                                  EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,
                                  bloc_c, str(cwd) if cwd else None, ctypes.byref(demarrage), ctypes.byref(info_proc)):
            raise OSError(ctypes.get_last_error(), f"CreateProcessW : {argv[0]}")
        # Les bouts de tube passés à la console ne servent plus de ce côté.
        _fermer(entree_console)
        _fermer(sortie_console)

        def lire():
            tampon = ctypes.create_string_buffer(8192)
            lu = w.DWORD(0)
            while k32.ReadFile(sortie_moteur, tampon, 8192, ctypes.byref(lu), None) and lu.value:
                with verrou:
                    morceaux.append(tampon.raw[:lu.value])

        lecteur = threading.Thread(target=lire, name="pseudo-terminal", daemon=True)
        lecteur.start()

        def taper(texte):
            donnees = texte.encode("utf-8")
            ecrit = w.DWORD(0)
            k32.WriteFile(entree_moteur, donnees, len(donnees), ctypes.byref(ecrit), None)

        if entree:
            taper(entree)

        def texte_lu():
            with verrou:
                return b"".join(morceaux).decode("utf-8", "replace")

        fin = time.monotonic() + delai_s
        fini = arrete = False
        while True:
            if k32.WaitForSingleObject(info_proc.hProcess, 100) == ATTENTE_FINIE:
                fini = True
                break
            vu = nettoyer(texte_lu()) if arret is not None or repondre is not None else ""
            if arret is not None and arret(vu):
                arrete = True
                break
            reponse = repondre(vu) if repondre is not None else None
            if reponse:
                taper(reponse)
            if time.monotonic() >= fin:
                break
        code = None
        if fini:
            c = w.DWORD(0)
            k32.GetExitCodeProcess(info_proc.hProcess, ctypes.byref(c))
            code = c.value
            time.sleep(0.2)                 # la dernière sortie a le temps d'arriver
        else:
            k32.TerminateProcess(info_proc.hProcess, 1)
            k32.WaitForSingleObject(info_proc.hProcess, 5000)
    finally:
        # Fermer la pseudo-console termine les programmes qui y restent attachés et casse le tube de sortie.
        k32.ClosePseudoConsole(console)
        if lecteur is not None:
            lecteur.join(5)
        k32.DeleteProcThreadAttributeList(attributs)
        for h in (info_proc.hProcess, info_proc.hThread):
            if h:
                k32.CloseHandle(h)
        for h in a_fermer:
            _fermer(h)
    brut = b"".join(morceaux).decode("utf-8", "replace")
    return Resultat(code=code, texte=nettoyer(brut), brut=brut, fini=fini, arrete=arrete)


def environnement_sans(variable, environ=None):
    """L'environnement du moteur sans `variable` (la clé API : la session reste sur l'abonnement). Si le moteur a été
    lancé depuis une session de Claude Code (`CLAUDECODE`), les variables de cette session hôte (`CLAUDE…`,
    `ANTHROPIC…`) sont retirées aussi : la commande lancée doit se comporter comme dans un terminal de l'utilisateur."""
    environ = os.environ if environ is None else environ
    hote = "CLAUDECODE" in environ
    return {k: v for k, v in environ.items()
            if k != variable and not (hote and k.upper().startswith(("CLAUDE", "ANTHROPIC")))}
