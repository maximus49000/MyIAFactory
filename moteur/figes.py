"""Les commandes figées : un programme lancé par un agent dont le temps processeur ne bouge plus est arrêté.

Essai réel : un agent local avait lancé des tests Godot (`godot --headless --script …`) ; un fichier de tests avait une
erreur de syntaxe, Godot ne s'est pas arrêté (0 % de processeur, aucune sortie) et l'agent a attendu 25 minutes ; un autre
Godot d'un essai précédent est resté ouvert une heure. Les signes de vie de l'agent continuaient : la règle « bloqué =
aucune action réelle depuis 40 min » ne le voyait pas.

Le moteur regarde donc, toutes les `SURVEILLER_TOUS_LES_S`, les processus lancés par chaque agent local de chaque projet :
- **la commande en cours** d'un agent vivant qui attend une commande (`Bash`/`PowerShell` sans résultat dans son flux) :
  ses processus nés après cette commande (pas un serveur lancé plus tôt, ni un serveur MCP de l'agent). Si tous sont
  immobiles (temps processeur inchangé) depuis `FIGE_MIN` minutes, le programme qui attend vraiment est arrêté, lui et
  ses enfants : pas un shell ni l'agent (`protege`), et un lanceur (`python`, `node`…) seulement s'il n'a pas d'enfant
  (sinon c'est son enfant qui est visé). La commande de l'agent rend la main et il lit l'erreur ;
- **les programmes laissés** par un agent (son shell coupé, ou l'agent fini) : reconnus à leur ancêtre noté (le moteur
  garde dans `FICHIER_FAMILLES` les processus vus sous chaque agent, avec leur heure de création) ou à leur parent (sous
  Windows le numéro du parent reste, même mort) né avant eux ; immobiles depuis `FIGE_MIN` minutes, ils sont arrêtés.
Chaque arrêt est rendu (`Surveillance.passer`) : le moteur l'écrit au journal de la tâche (`texte_journal`).

Jamais : l'agent lui-même, le moteur, un processus qui n'est ni un descendant d'un agent du projet ni un orphelin reconnu
(un numéro de processus repris par un autre est reconnu à son heure de création). Une mesure qui échoue ne fait rien.

Ce fichier ne dépend que de la bibliothèque standard (pas du reste du moteur) : la surveillance des sessions cloud
(`outils/cloud/surveillance.py`) en reprend la logique.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

FIGE_MIN = 5                     # un programme dont le temps processeur ne bouge plus depuis 5 min est figé
SURVEILLER_TOUS_LES_S = 30       # la liste des processus est relue au plus toutes les 30 s
MARGE_S = 5                      # l'heure de la commande lue dans le flux, à quelques secondes près
FICHIER_FAMILLES = "familles.surveillance"     # pas en `.json` : le registre des agents lit tous les `*.json`
MAX_CONNUS = 500
OUTILS_COMMANDE = ("Bash", "PowerShell")

_PROTEGES = re.compile(r"^(claude|bash|sh|dash|zsh|fish|ksh|tcsh|csh|cmd|powershell|pwsh|conhost|openconsole|"
                       r"mintty|winpty|winpty-agent|wsl|wslhost|git-bash|sudo|login|sshd|init|systemd)$")
_LANCEURS = re.compile(r"^(python[\d.]*w?|py|pyw|node|npm|npx|uv|uvx|pipx|timeout|env|nohup|xargs|make|time|"
                       r"cmd-wrapper)$")


def nom_court(nom):
    """« C:\\Godot\\Godot.exe » → « Godot » : le nom du programme, sans dossier ni `.exe`."""
    n = str(nom or "").replace("\\", "/").rsplit("/", 1)[-1]
    return n[:-4] if n.lower().endswith(".exe") else n


def protege(nom):
    """Un shell, l'agent, la console : jamais arrêté (son enfant l'est)."""
    return bool(_PROTEGES.match(nom_court(nom).lower()))


def lanceur(nom):
    """Un programme qui en lance un autre (`python` d'un script de tests, `node`, `timeout`…) : visé seulement s'il n'a
    pas d'enfant."""
    return bool(_LANCEURS.match(nom_court(nom).lower()))


# --- La liste des processus : {pid: {pid, parent, nom, cpu, debut, cree}}. `None` si on ne sait pas la lire.
#  `cpu` : un temps processeur (unité propre à la plateforme : seule son immobilité compte) ; `debut` : l'heure de
#  création dans l'unité de `detache.debut_processus` (identité du processus) ; `cree` : la même en secondes epoch.

def lister_processus():
    try:
        if sys.platform == "win32":
            return _lister_windows()
        if Path("/proc/self/stat").exists():
            return _lister_proc()
    except Exception:       # une mesure qui échoue ne fait jamais rien
        return None
    return None


def _lister_windows():
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)

    class Entree(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k.Process32FirstW.argtypes = k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entree)]
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(ctypes.c_ulonglong)] * 4
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    instantane = k.CreateToolhelp32Snapshot(0x2, 0)          # TH32CS_SNAPPROCESS
    if not instantane or instantane == wintypes.HANDLE(-1).value:
        return None
    vus = []
    try:
        e = Entree()
        e.dwSize = ctypes.sizeof(Entree)
        ok = k.Process32FirstW(instantane, ctypes.byref(e))
        while ok:
            vus.append((int(e.th32ProcessID), int(e.th32ParentProcessID), e.szExeFile))
            ok = k.Process32NextW(instantane, ctypes.byref(e))
    finally:
        k.CloseHandle(instantane)
    if not vus:
        return None
    rendu = {}
    for pid, parent, nom in vus:
        cpu = debut = cree = None
        h = k.OpenProcess(0x1000, False, pid) if pid else None     # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            try:
                t = [ctypes.c_ulonglong() for _ in range(4)]
                if k.GetProcessTimes(h, *(ctypes.byref(x) for x in t)):
                    debut, cpu = int(t[0].value), int(t[2].value + t[3].value)
                    cree = debut / 1e7 - 11644473600 if debut else None
            finally:
                k.CloseHandle(h)
        rendu[pid] = {"pid": pid, "parent": parent, "nom": nom_court(nom), "cpu": cpu, "debut": debut, "cree": cree}
    return rendu


def _tic():
    """Les tops d'horloge par seconde des temps de `/proc` (100 hors Linux)."""
    try:
        return os.sysconf("SC_CLK_TCK")
    except (AttributeError, ValueError, OSError):
        return 100


def _lister_proc(racine="/proc"):
    tic = _tic()
    demarrage = None
    try:
        for ligne in Path(racine, "stat").read_text().splitlines():
            if ligne.startswith("btime "):
                demarrage = int(ligne.split()[1])
    except (OSError, ValueError):
        pass
    rendu = {}
    for d in Path(racine).iterdir():
        if not d.name.isdigit():
            continue
        try:
            brut = (d / "stat").read_text()
        except OSError:
            continue
        p = lire_stat(int(d.name), brut, tic, demarrage)
        if p is not None:
            rendu[p["pid"]] = p
    return rendu or None


def lire_stat(pid, brut, tic=100, demarrage=None):
    """Une ligne de `/proc/<pid>/stat` lue : le nom (entre parenthèses), le parent, `utime + stime`, la création."""
    try:
        nom = brut[brut.index("(") + 1:brut.rindex(")")]
        champs = brut.rsplit(")", 1)[1].split()
        debut = int(champs[19])
        return {"pid": pid, "parent": int(champs[1]), "nom": nom_court(nom), "cpu": int(champs[11]) + int(champs[12]),
                "debut": debut, "cree": demarrage + debut / tic if demarrage is not None else None}
    except (ValueError, IndexError):
        return None


def identite_actuelle(pid):
    """L'heure de création (`debut`) du processus qui porte ce numéro maintenant, `None` s'il n'est plus là."""
    procs = lister_processus()
    p = (procs or {}).get(pid)
    return p.get("debut") if p else None


def arreter(p, descendants):
    """Arrête le processus `p` et ses enfants (vérifié juste avant : le même processus, pas un numéro repris). Rend
    vrai si l'arrêt a été demandé."""
    if p.get("debut") is None or identite_actuelle(p["pid"]) != p["debut"]:
        return False
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p["pid"])], capture_output=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            import signal
            for pid in [*reversed(descendants), p["pid"]]:     # les enfants d'abord ; jamais un groupe entier
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        return True
    except (OSError, subprocess.SubprocessError):
        return False


# --- La logique pure (listes injectables).

def enfants_de(procs):
    """{parent: [enfants]} ; un enfant né avant le processus qui porte le numéro de son parent n'en est pas l'enfant
    (numéro repris)."""
    rendu = {}
    for p in procs.values():
        pere = procs.get(p.get("parent"))
        if pere is None or pere["pid"] == p["pid"]:
            continue
        if pere.get("cree") is not None and p.get("cree") is not None and pere["cree"] > p["cree"] + 1:
            continue
        rendu.setdefault(pere["pid"], []).append(p["pid"])
    return rendu


def sous_arbre(enfants, racine):
    """Les numéros sous `racine` (elle exclue), en largeur."""
    vus, file = [], list(enfants.get(racine, []))
    while file:
        pid = file.pop(0)
        if pid in vus:
            continue
        vus.append(pid)
        file += enfants.get(pid, [])
    return vus


class Suivi:
    """Depuis quand le temps processeur de chaque processus (pid, debut) n'a pas bougé."""

    def __init__(self):
        self.vus = {}

    def observer(self, procs, maintenant):
        garde = {}
        for p in procs.values():
            cle = (p["pid"], p.get("debut"))
            avant = self.vus.get(cle)
            if p.get("cpu") is None:
                continue
            garde[cle] = avant if avant is not None and avant[0] == p["cpu"] else (p["cpu"], maintenant)
        self.vus = garde

    def immobile_depuis(self, p, maintenant):
        """Secondes d'immobilité, `None` si on ne mesure pas son temps processeur."""
        v = self.vus.get((p["pid"], p.get("debut"))) if p.get("cpu") is not None else None
        return None if v is None else maintenant - v[1]


def cibles(procs, enfants, racines, suivi, maintenant, fige_s, *, interdits=(), nes_apres=None):
    """Les processus à arrêter dans la région des `racines` (comprises) : `[(processus, immobile_s, descendants)]`.
    Rien si un processus non protégé de la région n'est pas immobile depuis `fige_s` (la commande travaille encore, ou
    se mesure mal). `nes_apres` : seuls les processus nés après (la commande en cours ; un processus sans heure de
    création n'est jamais pris). Un shell (`protege`) n'est jamais visé ; un lanceur ne l'est que sans enfant."""
    def dans_la_region(p):
        if p["pid"] in interdits:
            return False
        return nes_apres is None or (p.get("cree") is not None and p["cree"] >= nes_apres)

    region, file = [], [r for r in racines if r in procs]
    while file:
        pid = file.pop(0)
        if pid in region or (pid not in racines and not dans_la_region(procs[pid])):
            continue
        region.append(pid)
        file += enfants.get(pid, [])
    region = [x for x in region if x not in interdits or x in racines]
    utiles = [procs[x] for x in region if not protege(procs[x]["nom"]) and x not in interdits]
    if not utiles:
        return []
    immobiles = {p["pid"]: suivi.immobile_depuis(p, maintenant) for p in utiles}
    if any(v is None or v < fige_s for v in immobiles.values()):
        return []
    rendu, file = [], [r for r in racines if r in region]
    while file:
        pid = file.pop(0)
        p = procs[pid]
        dessous = [x for x in sous_arbre(enfants, pid) if x in region]
        if pid in interdits or protege(p["nom"]) or any(x in interdits for x in sous_arbre(enfants, pid)) or (
                lanceur(p["nom"]) and any(not protege(procs[x]["nom"]) for x in dessous)):
            file += [x for x in enfants.get(pid, []) if x in region]
            continue
        rendu.append((p, immobiles[pid], dessous))
    return rendu


def _heure(texte):
    try:
        return datetime.fromisoformat(str(texte).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def commandes_en_attente(lignes, en_attente=None):
    """{id: heure (epoch) ou None} des commandes (`Bash`, `PowerShell`) lancées par l'agent et sans résultat encore."""
    en_attente = dict(en_attente or {})
    for d in lignes:
        if not isinstance(d, dict):
            continue
        contenu = (d.get("message") or {}).get("content") if isinstance(d.get("message"), dict) else None
        if not isinstance(contenu, list):
            continue
        for bloc in contenu:
            if not isinstance(bloc, dict):
                continue
            if d.get("type") == "assistant" and bloc.get("type") == "tool_use" and bloc.get("name") in OUTILS_COMMANDE:
                if isinstance(bloc.get("id"), str):
                    en_attente[bloc["id"]] = _heure(d["timestamp"]) if isinstance(d.get("timestamp"), str) else None
            elif d.get("type") == "user" and bloc.get("type") == "tool_result":
                en_attente.pop(bloc.get("tool_use_id"), None)
    return en_attente


def texte_journal(arret):
    minutes = max(1, int(arret["immobile_s"] // 60))
    return f"Commande figée arrêtée : {arret['nom']} (aucune activité du processeur depuis {minutes} min)."


# --- La surveillance d'un dossier d'agents (`<factory>/agents-en-cours`).

class Surveillance:
    """`passer(dossier_agents, procs=None)` : un passage ; rend les arrêts `[{tache, agent, nom, pid, immobile_s,
    orphelin}]`. `lister`, `tuer`, `horloge`, `moi` (le numéro du moteur) sont là pour les essais."""

    def __init__(self, *, fige_s=FIGE_MIN * 60, lister=lister_processus, tuer=arreter, horloge=time.time, moi=None):
        self.fige_s, self.lister, self.tuer, self.horloge = fige_s, lister, tuer, horloge
        self.moi = os.getpid() if moi is None else moi
        self.suivi = Suivi()
        self.flux = {}           # chemin du flux -> (octets lus, commandes en attente)
        self.vues = {}           # id de commande -> heure où le moteur l'a vue en attente (si le flux ne la date pas)

    def passer(self, dossier_agents, procs=None):
        try:
            if procs is None:
                procs = self.lister()
            if not procs:
                return []
            return self._passer(Path(dossier_agents), procs)
        except Exception:        # une mesure qui échoue ne fait jamais rien
            return []

    def _attente(self, flux):
        cle = str(flux)
        lu, en_attente = self.flux.get(cle, (0, {}))
        try:
            if flux.stat().st_size < lu:
                lu, en_attente = 0, {}
            with open(flux, "rb") as f:
                f.seek(lu)
                bloc = f.read()
        except OSError:
            return {}
        fin = bloc.rfind(b"\n")
        if fin >= 0:
            lignes = []
            for brute in bloc[:fin].split(b"\n"):
                if b"tool_use" not in brute and b"tool_result" not in brute:
                    continue
                try:
                    lignes.append(json.loads(brute))
                except ValueError:
                    continue
            en_attente = commandes_en_attente(lignes, en_attente)
            lu += fin + 1
        self.flux[cle] = (lu, en_attente)
        return en_attente

    def _passer(self, dossier, procs):
        if not dossier.is_dir():
            return []
        maintenant = self.horloge()
        self.suivi.observer(procs, maintenant)
        enfants = enfants_de(procs)
        familles = self._lire_familles(dossier)
        for f in sorted(dossier.glob("*.json")):
            if f.name.endswith(".questions.json"):
                continue
            try:
                etat = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            pid = etat.get("pid") if isinstance(etat, dict) else None
            if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
                continue
            ident = f"{pid}:{etat.get('debut_processus')}"
            debut = etat.get("debut")      # l'heure du lancement, juste après la création du processus
            fam = familles.setdefault(ident, {"pid": pid, "debut": etat.get("debut_processus"), "connus": {}, "vu": None,
                                              "cree": debut - MARGE_S if isinstance(debut, (int, float))
                                              and not isinstance(debut, bool) else None})
            fam.update({"tache": etat.get("tache") or f.stem, "agent": etat.get("agent"),
                        "flux": str(f.with_suffix(".jsonl"))})
            try:
                fam["vu"] = max(fam.get("vu") or 0, f.with_suffix(".jsonl").stat().st_mtime)
            except OSError:
                pass
        arrets, vivants = [], {}
        for ident, fam in familles.items():
            p = procs.get(fam["pid"])
            if p is not None and (fam.get("debut") is None or p.get("debut") in (None, fam["debut"])):
                vivants[ident] = p
                fam["cree"], fam["vu"] = p.get("cree") if p.get("cree") is not None else fam.get("cree"), maintenant
        sous_agents = {ident: set(sous_arbre(enfants, p["pid"])) for ident, p in vivants.items()}
        tous_sous_agents = set().union(*sous_agents.values()) if sous_agents else set()
        interdits = {self.moi} | {p["pid"] for p in vivants.values()}
        for ident, fam in list(familles.items()):
            connus = fam.setdefault("connus", {})
            for pid in sous_agents.get(ident, ()):
                q = procs[pid]
                connus[str(pid)] = {"debut": q.get("debut"), "cree": q.get("cree"), "vu": maintenant}
            # la commande en cours d'un agent vivant qui l'attend
            if ident in vivants:
                en_attente = self._attente(Path(fam["flux"])) if fam.get("flux") else {}
                heures = []
                if len(self.vues) > 1000:
                    self.vues.clear()
                for cid, t in en_attente.items():
                    self.vues.setdefault(cid, maintenant)
                    heures.append(t if t is not None else self.vues[cid])
                if heures:
                    for q, immobile, dessous in cibles(procs, enfants, [vivants[ident]["pid"]], self.suivi, maintenant,
                                                       self.fige_s, interdits=interdits,
                                                       nes_apres=min(heures) - MARGE_S):
                        if q["pid"] not in interdits and self.tuer(q, dessous):
                            arrets.append(self._arret(fam, q, immobile, False))
            # les programmes laissés : ni sous un agent vivant, mais d'un ancêtre de la famille
            laisses = self._laisses(fam, procs, tous_sous_agents | interdits, vivants.get(ident))
            racines = [pid for pid in laisses if procs[pid].get("parent") not in laisses]
            for r in racines:
                for q, immobile, dessous in cibles(procs, enfants, [r], self.suivi, maintenant, self.fige_s,
                                                   interdits=interdits | tous_sous_agents):
                    if self.tuer(q, dessous):
                        arrets.append(self._arret(fam, q, immobile, True))
            if ident not in vivants and not laisses:
                del familles[ident]          # l'agent est fini et n'a rien laissé : plus rien à surveiller
            elif len(connus) > MAX_CONNUS:
                for cle in sorted(connus, key=lambda c: connus[c].get("vu") or 0)[:len(connus) - MAX_CONNUS]:
                    del connus[cle]
        self._ecrire_familles(dossier, familles)
        return arrets

    @staticmethod
    def _laisses(fam, procs, exclus, agent_vivant):
        """Les processus laissés par la famille : notés (même numéro, même création), ou dont le parent noté n'est plus
        là (ou porte maintenant un autre processus, né après eux) et qui sont nés de son vivant."""
        ancetres = {str(fam["pid"]): {"debut": fam.get("debut"), "cree": fam.get("cree"), "vu": fam.get("vu")},
                    **fam.get("connus", {})}
        laisses = set()
        for p in procs.values():
            if p["pid"] in exclus or p.get("debut") is None:
                continue
            note = fam.get("connus", {}).get(str(p["pid"]))
            if note is not None and note.get("debut") == p["debut"]:
                laisses.add(p["pid"])
                continue
            a = ancetres.get(str(p.get("parent")))
            if a is None or p.get("cree") is None or a.get("cree") is None:
                continue
            pere = procs.get(p["parent"])
            if pere is not None and (pere.get("debut") == a.get("debut") or pere.get("cree") is None
                                     or pere["cree"] <= p["cree"] + 1):
                continue            # son parent vit (sous l'agent, ou c'est un autre processus : le sien)
            if p["cree"] + 1 < a["cree"]:
                continue            # né avant l'ancêtre noté : pas le sien
            if a.get("vu") is not None and p["cree"] > a["vu"] + SURVEILLER_TOUS_LES_S * 2 + MARGE_S:
                continue            # né bien après la dernière fois que l'ancêtre a été vu : numéro repris
            laisses.add(p["pid"])
        # leurs enfants vivants en font partie
        enfants = enfants_de(procs)
        for pid in list(laisses):
            laisses.update(x for x in sous_arbre(enfants, pid) if x not in exclus)
        return laisses

    @staticmethod
    def _arret(fam, q, immobile, orphelin):
        return {"tache": fam.get("tache"), "agent": fam.get("agent"), "nom": nom_court(q["nom"]), "pid": q["pid"],
                "immobile_s": immobile, "orphelin": orphelin}

    @staticmethod
    def _lire_familles(dossier):
        try:
            d = json.loads((dossier / FICHIER_FAMILLES).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {k: v for k, v in d.items() if isinstance(v, dict) and isinstance(v.get("pid"), int)} \
            if isinstance(d, dict) else {}

    @staticmethod
    def _ecrire_familles(dossier, familles):
        chemin = dossier / FICHIER_FAMILLES
        try:
            if not familles:
                if chemin.exists():
                    chemin.unlink()
                return
            tmp = chemin.with_name(chemin.name + ".tmp")
            tmp.write_text(json.dumps(familles, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, chemin)
        except OSError:
            pass
