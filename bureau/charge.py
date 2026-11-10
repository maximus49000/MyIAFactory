"""Charge de l'ordinateur : mesure, lissage, historique, conseil, feu vert.

Windows seulement pour la mesure (appels système via ctypes, rien à installer).
"""
import json
import math
import os
import statistics
import sys
from collections import deque
from pathlib import Path

WINDOWS = sys.platform == "win32"

if WINDOWS:
    import ctypes
    from ctypes import wintypes

    class _FILETIME(ctypes.Structure):
        _fields_ = [("bas", wintypes.DWORD), ("haut", wintypes.DWORD)]

    class _MEMOIRE(ctypes.Structure):
        _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    def _entier(ft):
        return (ft.haut << 32) | ft.bas

    def _memoire():
        m = _MEMOIRE()
        m.dwLength = ctypes.sizeof(_MEMOIRE)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            raise OSError("GlobalMemoryStatusEx a échoué")
        return m


def machine():
    coeurs = os.cpu_count() or 1
    if not WINDOWS:
        return {"coeurs": coeurs, "memoire_totale_go": 0.0, "disponible": False}
    try:
        total = _memoire().ullTotalPhys / 2 ** 30
    except OSError:
        return {"coeurs": coeurs, "memoire_totale_go": 0.0, "disponible": False}
    return {"coeurs": coeurs, "memoire_totale_go": total, "disponible": True}


class Sonde:
    """Lecture instantanée : CPU par différence entre deux appels, mémoire."""

    def __init__(self):
        self._precedent = None

    def _temps(self):
        repos, noyau, utilisateur = _FILETIME(), _FILETIME(), _FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(repos), ctypes.byref(noyau),
                                                     ctypes.byref(utilisateur)):
            raise OSError("GetSystemTimes a échoué")
        # le temps « noyau » inclut le temps de repos
        return _entier(repos), _entier(noyau) + _entier(utilisateur)

    def lire(self):
        if not WINDOWS:
            return None
        try:
            repos, total = self._temps()
            memoire = float(_memoire().dwMemoryLoad)
        except OSError:
            return None
        cpu = 0.0
        if self._precedent is not None:
            d_repos = repos - self._precedent[0]
            d_total = total - self._precedent[1]
            if d_total > 0:
                cpu = 100.0 * (1 - d_repos / d_total)
        self._precedent = (repos, total)
        return {"cpu": max(0.0, min(100.0, cpu)), "memoire": max(0.0, min(100.0, memoire))}


class Lisseur:
    def __init__(self, fenetre_s=60):
        self.fenetre_s = fenetre_s
        self._echantillons = deque()

    def ajouter(self, t, cpu):
        self._echantillons.append((t, cpu))
        while self._echantillons and self._echantillons[0][0] < t - self.fenetre_s:
            self._echantillons.popleft()

    def moyenne(self):
        # Copie : la sonde ajoute des échantillons depuis un autre fil pendant qu'on lit.
        echantillons = list(self._echantillons)
        if not echantillons:
            return 0.0
        return sum(c for _, c in echantillons) / len(echantillons)


def affichee(cpu_lisse, memoire):
    return max(0, min(100, round(max(cpu_lisse, memoire))))


def feu_vert(valeur, maximum):
    return valeur <= maximum


class Historique:
    CONSERVATION_S = 7 * 86400

    def __init__(self, chemin):
        self.chemin = Path(chemin)

    def _lignes(self):
        if not self.chemin.exists():
            return []
        out = []
        try:
            texte = self.chemin.read_text(encoding="utf-8")
        except OSError:
            return []
        for ligne in texte.splitlines():
            try:
                d = json.loads(ligne)
                if (isinstance(d, dict) and isinstance(d["t"], (int, float))
                        and isinstance(d["charge"], (int, float)) and isinstance(d["agents_locaux"], int)):
                    out.append({"t": d["t"], "charge": d["charge"], "agents_locaux": d["agents_locaux"]})
            except (ValueError, KeyError, TypeError):
                continue
        return out

    def lire(self):
        lignes = self._lignes()
        if not lignes:
            return []
        limite = max(x["t"] for x in lignes) - self.CONSERVATION_S
        return [x for x in lignes if x["t"] >= limite]

    def noter(self, t, charge, agents_locaux):
        nouvelle = {"t": t, "charge": charge, "agents_locaux": agents_locaux}
        existantes = self._lignes()
        limite = max([t] + [x["t"] for x in existantes]) - self.CONSERVATION_S
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        if any(x["t"] < limite for x in existantes):
            gardees = [x for x in existantes if x["t"] >= limite] + [nouvelle]
            tmp = self.chemin.with_name(self.chemin.name + ".tmp")
            tmp.write_text("".join(json.dumps(x) + "\n" for x in gardees), encoding="utf-8")
            os.replace(tmp, self.chemin)
        else:
            with open(self.chemin, "a", encoding="utf-8") as f:
                f.write(json.dumps(nouvelle) + "\n")


def conseiller(historique, mach):
    actifs = [x for x in historique if x["agents_locaux"] >= 1]
    if len(actifs) < 30:
        go, coeurs = mach["memoire_totale_go"], mach["coeurs"]
        if go >= 16 and coeurs >= 8:
            valeur = 70
        elif go >= 8:
            valeur = 60
        else:
            valeur = 50
        return {"valeur": valeur, "source": "machine",
                "explication": ("Pas encore assez de mesures avec des agents au travail. "
                                f"D'après la machine ({coeurs} cœurs, {go:.0f} Go), "
                                f"je conseille {valeur} % par prudence.")}
    au_repos = [x["charge"] for x in historique if x["agents_locaux"] == 0]
    repos = statistics.median(au_repos) if au_repos else min(x["charge"] for x in historique)
    par_agent = max(0.0, statistics.median((x["charge"] - repos) / x["agents_locaux"] for x in actifs))
    brute = 85 - par_agent
    plancher = max(40, math.ceil((repos + 5) / 5) * 5)
    valeur = min(85, max(plancher, math.floor(brute / 5) * 5))
    return {"valeur": int(valeur), "source": "historique",
            "explication": (f"Au repos la machine est à {repos:.0f} %, et chaque agent local ajoute "
                            f"environ {par_agent:.0f} %. Pour rester sous 85 % après un lancement, "
                            f"je conseille {int(valeur)} %.")}
