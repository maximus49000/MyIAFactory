"""Le surveillant des commandes figées d'une session cloud (Linux), lancé en arrière-plan au début de la session.

Dans le cloud, le moteur ne voit pas les processus : ce script, autonome (bibliothèque standard), tourne dans la session
et applique la règle du moteur (`moteur/figes.py`, dont il reprend la logique) : un programme lancé par une commande de
l'agent dont le temps processeur (`/proc/<pid>/stat` : utime + stime) n'a pas bougé depuis `FIGE_MIN` minutes, alors que
rien d'autre de la commande ne travaille, est arrêté, lui et ses enfants. Visés : les processus sous un shell lancé par le
processus `claude` de la session (une commande de l'agent ; pas un serveur MCP qu'il a lancé lui-même) ; à défaut de
`claude` visible, tout processus de l'utilisateur né après le surveillant. Jamais : un shell, `claude`, le surveillant ni
ses ancêtres, un processus d'un autre utilisateur. Une mesure impossible ne fait rien.

Chaque arrêt est écrit dans `<projet>/.factory/rapports/commandes-figees.jsonl` (une ligne JSON : `heure`, `programme`,
`commande` (80 caractères), `immobile_min`) ; l'agent est invité à le dire dans son rapport.

    python3 .claude/cloud/surveillance.py --projet "$CLAUDE_PROJECT_DIR" &

`figes.py` est cherché à côté de ce script (copie dans le projet : `.claude/cloud/figes.py`), sinon dans
`moteur/figes.py` du dépôt de la skill.
"""
import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ICI = Path(__file__).resolve().parent
PAS_S = 30
FICHIER = Path(".factory") / "rapports" / "commandes-figees.jsonl"


def _charger_figes():
    for chemin in (ICI / "figes.py", ICI.parent.parent / "moteur" / "figes.py"):
        if chemin.is_file():
            spec = importlib.util.spec_from_file_location("figes", chemin)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise ImportError("figes.py introuvable (à copier à côté de surveillance.py)")


figes = _charger_figes()


def lister_linux(racine="/proc"):
    """La liste de `figes` (`/proc/<pid>/stat`), plus `cmd` (la ligne de commande) et `uid` de chaque processus. `None`
    si `/proc` ne se lit pas."""
    try:
        procs = figes._lister_proc(racine)
    except Exception:
        return None
    if not procs:
        return None
    for pid, p in procs.items():
        try:
            p["cmd"] = Path(racine, str(pid), "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8",
                                                                                                "replace").strip()
        except OSError:
            p["cmd"] = ""
        try:
            p["uid"] = os.stat(Path(racine, str(pid))).st_uid
        except OSError:
            p["uid"] = None
    return procs


def est_claude(p):
    """Le processus `claude` de la session : son nom, ou le premier mot (ou le script) de sa ligne de commande."""
    if figes.nom_court(p.get("nom")).lower() == "claude":
        return True
    mots = str(p.get("cmd") or "").split()[:2]
    return any(figes.nom_court(m).lower() == "claude" or "claude-code" in m for m in mots)


def ancetres(procs, pid):
    vus = []
    while pid in procs and pid not in vus:
        vus.append(pid)
        pid = procs[pid].get("parent")
    return vus


def regions(procs, moi, uid):
    """`(racines, interdits, nes_apres)` : les shells lancés sous chaque `claude` (une commande de l'agent) ; à défaut
    de `claude`, les processus de l'utilisateur qui n'ont pas de parent de l'utilisateur, nés après le surveillant."""
    interdits = set(ancetres(procs, moi)) | {1}
    claudes = [p["pid"] for p in procs.values() if est_claude(p) and p["pid"] not in interdits]
    interdits |= set(claudes)
    enfants = figes.enfants_de(procs)
    if claudes:
        racines = []
        for c in claudes:
            for pid in figes.sous_arbre(enfants, c):
                p = procs[pid]
                if figes.protege(p["nom"]) and not est_claude(p) and procs.get(p.get("parent"), {}).get("pid") in claudes:
                    racines.append(pid)
        return racines, interdits, None
    apres = (procs.get(moi) or {}).get("cree")
    if apres is None or uid is None:
        return [], interdits, None
    racines = [p["pid"] for p in procs.values()
               if p.get("uid") == uid and p["pid"] not in interdits and p.get("cree") is not None
               and p["cree"] >= apres and procs.get(p.get("parent"), {}).get("uid") != uid]
    return racines, interdits, apres


class Surveillant:
    """Un passage : `passer()` rend les arrêts écrits. `lister`, `tuer`, `horloge`, `moi`, `uid` : pour les essais."""

    def __init__(self, projet, *, fige_s=figes.FIGE_MIN * 60, lister=lister_linux, tuer=figes.arreter,
                 horloge=time.time, moi=None, uid=None):
        self.fichier = Path(projet) / FICHIER
        self.fige_s, self.lister, self.tuer, self.horloge = fige_s, lister, tuer, horloge
        self.moi = os.getpid() if moi is None else moi
        self.uid = (os.getuid() if hasattr(os, "getuid") else None) if uid is None else uid
        self.suivi = figes.Suivi()

    def passer(self):
        try:
            procs = self.lister()
            if not procs or self.moi not in procs:
                return []
            maintenant = self.horloge()
            self.suivi.observer(procs, maintenant)
            racines, interdits, nes_apres = regions(procs, self.moi, self.uid)
            enfants = figes.enfants_de(procs)
            arrets = []
            for r in racines:
                for q, immobile, dessous in figes.cibles(procs, enfants, [r], self.suivi, maintenant, self.fige_s,
                                                         interdits=interdits, nes_apres=nes_apres):
                    if q["pid"] in interdits or est_claude(q) or not self.tuer(q, dessous):
                        continue
                    arrets.append({"heure": datetime.fromtimestamp(maintenant).astimezone().isoformat(timespec="seconds"),
                                   "programme": figes.nom_court(q["nom"]), "commande": str(q.get("cmd") or "")[:80],
                                   "immobile_min": round(immobile / 60, 1), "pid": q["pid"]})
            if arrets:
                self._ecrire(arrets)
            return arrets
        except Exception:      # une mesure qui échoue ne fait jamais rien
            return []

    def _ecrire(self, arrets):
        try:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            with open(self.fichier, "a", encoding="utf-8") as f:
                for a in arrets:
                    f.write(json.dumps(a, ensure_ascii=False) + "\n")
        except OSError:
            pass


def main(argv=None):
    a = argparse.ArgumentParser(description="Arrête les commandes figées d'une session cloud.")
    a.add_argument("--projet", default=os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    a.add_argument("--fige-min", type=float, default=figes.FIGE_MIN)
    a.add_argument("--pas", type=float, default=PAS_S)
    a.add_argument("--une-fois", action="store_true")
    args = a.parse_args(argv)
    if not Path("/proc/self/stat").exists():
        return 0                 # hors Linux : rien à faire
    s = Surveillant(args.projet, fige_s=args.fige_min * 60)
    while True:
        s.passer()
        if args.une_fois:
            return 0
        time.sleep(args.pas)


if __name__ == "__main__":
    sys.exit(main())
