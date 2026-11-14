"""« Optimiser la charge » : les programmes qui chargent l'ordinateur, et l'arrêt de l'un d'eux sur demande.

Le relevé des processus n'utilise rien à installer : sous Windows, une seule commande PowerShell lit
`Win32_Process` deux fois à environ 1 s d'écart (le % processeur vient de la différence des temps noyau +
utilisateur, divisée par le nombre de cœurs logiques) ; ailleurs, `ps` deux fois.

`classer` est une fonction pure : elle reçoit les deux relevés et ce qui appartient à MyIAFactory (agents locaux,
moteur, bureau), et rend les programmes les plus lourds, avec leur étiquette et s'ils sont protégés. Le serveur
refuse l'arrêt d'un programme protégé même si on l'appelle directement (`peut_arreter`).
"""
import os
import re
import subprocess
import sys
import time

DUREE_S = 1.0          # l'intervalle de mesure du processeur
NOMBRE = 15            # les programmes montrés

# Jamais arrêtés : le système, l'interface de Windows, Claude Code, Tailscale (le téléphone passe par lui).
NOMS_PROTEGES = frozenset({
    "system", "idle", "system idle process", "registry", "memory compression", "secure system", "smss", "csrss",
    "wininit", "winlogon", "services", "lsass", "lsaiso", "svchost", "dwm", "explorer", "fontdrvhost", "msmpeng",
    "nissrv", "securityhealthservice", "wmiprvse", "trustedinstaller", "taskhostw", "sihost", "ctfmon", "conhost",
    "spoolsv", "audiodg",
    "claude", "tailscale", "tailscaled", "tailscale-ipn",
    # hors Windows
    "init", "systemd", "launchd", "kernel_task", "kthreadd", "windowserver", "loginwindow", "sshd",
})


def nom_court(nom):
    """« Claude.EXE » → « claude » : la forme comparée aux noms protégés."""
    n = str(nom or "").strip().lower()
    return n[:-4] if n.endswith(".exe") else n


# --- Le relevé (le seul endroit qui touche au système).

SCRIPT_WINDOWS = r"""
$ErrorActionPreference = 'SilentlyContinue'
function Releve {
  Get-CimInstance Win32_Process | ForEach-Object {
    $d = 0; if ($_.CreationDate) { $d = $_.CreationDate.ToFileTimeUtc() }
    '{0}|{1}|{2}|{3}|{4}|{5}' -f $_.ProcessId, $_.ParentProcessId, $_.WorkingSetSize,
      ([uint64]$_.KernelModeTime + [uint64]$_.UserModeTime), $d, $_.Name
  }
}
$m = [Diagnostics.Stopwatch]::StartNew()
'#PID ' + $PID
'#A'
Releve
$t = $m.Elapsed.TotalSeconds
Start-Sleep -Milliseconds DUREE_MS
'#B ' + ($m.Elapsed.TotalSeconds - $t).ToString([Globalization.CultureInfo]::InvariantCulture)
Releve
"""


def lire_windows(sortie):
    """La sortie du script PowerShell → `(avant, apres, duree_s, pid_mesure)`. Une ligne illisible est sautée."""
    avant, apres, cible, duree, pid_mesure = {}, {}, None, DUREE_S, None
    for ligne in sortie.splitlines():
        ligne = ligne.strip()
        if ligne.startswith("#PID "):
            try:
                pid_mesure = int(ligne[5:])
            except ValueError:
                pass
            continue
        if ligne == "#A":
            cible = avant
            continue
        if ligne.startswith("#B"):
            cible = apres
            try:
                duree = float(ligne[2:].strip()) or DUREE_S
            except ValueError:
                pass
            continue
        if cible is None:
            continue
        morceaux = ligne.split("|", 5)
        if len(morceaux) != 6:
            continue
        try:
            pid, ppid, memoire, temps, debut = (int(x) for x in morceaux[:5])
        except ValueError:
            continue
        cible[pid] = {"pid": pid, "ppid": ppid, "nom": morceaux[5], "memoire": memoire, "cpu_s": temps / 1e7,
                      "debut": debut or None}
    return avant, apres, duree, pid_mesure


def _secondes(texte):
    """« [jj-][hh:]mm:ss[.cc] » (la colonne `time` de `ps`) → secondes."""
    jours = 0
    if "-" in texte:
        j, texte = texte.split("-", 1)
        jours = int(j)
    parties = [float(x) for x in texte.split(":")]
    s = 0.0
    for p in parties:
        s = s * 60 + p
    return jours * 86400 + s


def lire_ps(sortie):
    """La sortie de `ps -A -o pid=,ppid=,rss=,time=,comm=` → `{pid: processus}`."""
    rendu = {}
    for ligne in sortie.splitlines():
        m = re.match(r"\s*(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(.+)$", ligne)
        if not m:
            continue
        try:
            cpu = _secondes(m.group(4))
        except ValueError:
            continue
        pid = int(m.group(1))
        rendu[pid] = {"pid": pid, "ppid": int(m.group(2)), "nom": os.path.basename(m.group(5).strip()),
                      "memoire": int(m.group(3)) * 1024, "cpu_s": cpu, "debut": None}
    return rendu


def _sans_fenetre():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def releve(duree_s=DUREE_S):
    """Deux relevés à `duree_s` d'écart : `(avant, apres, duree_s)`. Lève `OSError` si le système ne répond pas."""
    if sys.platform == "win32":
        script = SCRIPT_WINDOWS.replace("DUREE_MS", str(int(duree_s * 1000)))
        try:
            fini = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                  capture_output=True, timeout=60, creationflags=_sans_fenetre())
        except (OSError, subprocess.SubprocessError) as e:
            raise OSError(f"PowerShell n'a pas répondu : {e}")
        avant, apres, duree, pid_mesure = lire_windows(fini.stdout.decode("utf-8", "replace"))
        if not apres:
            raise OSError("La liste des programmes est vide.")
        apres.pop(pid_mesure, None)      # la mesure elle-même
        return avant, apres, duree

    def un():
        try:
            fini = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,rss=,time=,comm="], capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as e:
            raise OSError(f"ps n'a pas répondu : {e}")
        return lire_ps(fini.stdout.decode("utf-8", "replace"))
    avant = un()
    t = time.monotonic()
    time.sleep(duree_s)
    apres = un()
    return avant, apres, time.monotonic() - t


def instantane():
    """Un seul relevé (pour vérifier une demande d'arrêt) : `{pid: processus}`."""
    return releve(0)[1]


def arreter(pid, arbre=False):
    """Arrête le processus `pid` (et ce qu'il a lancé si `arbre`). Rend `None` ou le message d'échec."""
    try:
        if sys.platform == "win32":
            argv = ["taskkill", "/F"] + (["/T"] if arbre else []) + ["/PID", str(pid)]
            fini = subprocess.run(argv, capture_output=True, timeout=30, creationflags=_sans_fenetre())
            if fini.returncode != 0:
                return (fini.stderr or fini.stdout).decode("cp850", "replace").strip()[:200] or "taskkill a échoué."
            return None
        import signal
        if arbre:
            try:
                os.killpg(pid, signal.SIGTERM)
                return None
            except OSError:
                pass
        os.kill(pid, signal.SIGTERM)
        return None
    except (OSError, subprocess.SubprocessError) as e:
        return str(e)[:200]


# --- Le classement (pur).

def _enfants(processus):
    """`{ppid: [pid…]}` ; un « parent » plus jeune que l'enfant a repris le numéro d'un mort : pas un lien."""
    enfants = {}
    for p in processus.values():
        parent = processus.get(p["ppid"])
        if parent is None or p["ppid"] == p["pid"]:
            continue
        if parent.get("debut") and p.get("debut") and p["debut"] < parent["debut"]:
            continue
        enfants.setdefault(p["ppid"], []).append(p["pid"])
    return enfants


def descendants(processus, pid, enfants=None):
    enfants = _enfants(processus) if enfants is None else enfants
    vus, pile = set(), list(enfants.get(pid, []))
    while pile:
        x = pile.pop()
        if x in vus or x == pid:
            continue
        vus.add(x)
        pile.extend(enfants.get(x, []))
    return vus


def ancetres(processus, pid):
    """Les parents de `pid`, jusqu'au premier inconnu (un parent plus jeune que l'enfant n'en est pas un)."""
    rendu, x = set(), processus.get(pid)
    while x is not None:
        parent = processus.get(x["ppid"])
        if parent is None or parent["pid"] in rendu or parent["pid"] == pid or parent["pid"] == x["pid"]:
            break
        if parent.get("debut") and x.get("debut") and x["debut"] < parent["debut"]:
            break
        rendu.add(parent["pid"])
        x = parent
    return rendu


def contexte(processus, *, agents=(), moteur=None, bureau=None):
    """Ce qui appartient à MyIAFactory dans ce relevé : `{pid: (etiquette, agent)}` et les pid protégés.
    `agents` : `[{pid, prenom, tache, cle, factory}]` (les agents locaux vivants)."""
    enfants = _enfants(processus)
    etiquettes, proteges = {}, set()
    for nom, pid in (("moteur", moteur), ("bureau", bureau)):
        if isinstance(pid, int) and pid in processus:
            etiquettes[pid] = (nom, None)
            proteges.add(pid)
            proteges |= ancetres(processus, pid)    # ce qui l'a lancé (py.exe, le terminal…) : l'arrêter l'arrêterait
    for a in agents:
        pid = a.get("pid")
        if not isinstance(pid, int) or pid not in processus:
            continue
        for d in descendants(processus, pid, enfants):
            if d not in etiquettes:
                etiquettes[d] = ("lancé par un agent", a)
    for a in agents:      # l'agent lui-même l'emporte sur « lancé par un agent » (un agent lancé par un autre)
        pid = a.get("pid")
        if isinstance(pid, int) and pid in processus:
            tache = f" (tâche {a['tache']})" if a.get("tache") else ""
            etiquettes[pid] = (f"agent {a.get('prenom') or a.get('cle') or '?'}{tache}", a)
    return etiquettes, proteges


def est_protege(p, etiquettes, proteges):
    """Un programme qu'on n'arrête jamais : le système, Claude Code, Tailscale, le bureau, le moteur et ce qui les a
    lancés. Un agent et ce qu'il a lancé ne le sont pas (même `claude.exe` : c'est l'agent)."""
    pid = p["pid"]
    if pid in (0, 4) or pid < 0 or pid in proteges:
        return True
    etiquette = etiquettes.get(pid)
    if etiquette and etiquette[1] is not None:
        return False
    return nom_court(p.get("nom")) in NOMS_PROTEGES


def classer(avant, apres, duree_s, coeurs, *, agents=(), moteur=None, bureau=None, n=NOMBRE):
    """Les `n` programmes qui prennent le plus le processeur (puis la mémoire), du relevé `apres`.
    Chacun : `{pid, nom, cpu (%), memoire_mo, etiquette, protege}`. Le processus inactif du système n'est pas un
    programme : il n'est pas montré."""
    duree_s = duree_s if duree_s and duree_s > 0 else DUREE_S
    coeurs = max(1, int(coeurs or 1))
    etiquettes, proteges = contexte(apres, agents=agents, moteur=moteur, bureau=bureau)
    lignes = []
    for pid, p in apres.items():
        if pid == 0 or nom_court(p.get("nom")) in ("idle", "system idle process"):
            continue
        a = avant.get(pid)
        cpu = 0.0
        if a is not None and a.get("debut") == p.get("debut"):
            cpu = max(0.0, (p["cpu_s"] - a["cpu_s"]) / duree_s / coeurs * 100)
        lignes.append({"pid": pid, "nom": p.get("nom") or "?", "cpu": round(min(cpu, 100.0), 1),
                       "memoire_mo": round(p.get("memoire", 0) / 2 ** 20, 1),
                       "etiquette": (etiquettes.get(pid) or (None,))[0],
                       "protege": est_protege(p, etiquettes, proteges)})
    lignes.sort(key=lambda x: (-x["cpu"], -x["memoire_mo"], x["pid"]))
    return lignes[:n]


def peut_arreter(pid, processus, *, agents=(), moteur=None, bureau=None):
    """Avant un arrêt : `(None, agent_ou_None, processus)` s'il est permis, sinon `(message, None, None)`."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return "Numéro de programme invalide.", None, None
    p = processus.get(pid)
    if p is None:
        return "Ce programme ne tourne plus.", None, None
    etiquettes, proteges = contexte(processus, agents=agents, moteur=moteur, bureau=bureau)
    if est_protege(p, etiquettes, proteges):
        return f"{p.get('nom') or 'Ce programme'} (pid {pid}) est protégé : il n'est jamais arrêté d'ici.", None, None
    etiquette = etiquettes.get(pid)
    agent = etiquette[1] if etiquette and etiquette[1] is not None and etiquette[1].get("pid") == pid else None
    return None, agent, p
