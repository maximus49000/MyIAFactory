"""« Lancer l'orchestrateur » : le seul geste du bureau qui agit lui-même, et seulement sur un clic.

Il démarre le moteur de la factory (`python -m moteur`, sans fenêtre) s'il ne tourne pas déjà : un seul moteur sert tous
les projets du bureau (verrou `~/MyIAFactory/moteur.pid`), locaux comme cloud. Sans la commande `claude`, rien ne
démarre : la réponse dit comment l'installer.
"""
import subprocess
import sys
from pathlib import Path

from moteur import appel, verrou

INSTALLER_CLAUDE = "npm install -g @anthropic-ai/claude-code"
RACINE = Path(__file__).resolve().parent.parent
BUREAU_PAR_DEFAUT = "~/MyIAFactory/bureau.json"


def lancer_moteur(argv, dossier):
    """Un processus détaché et sans fenêtre. Rend son numéro."""
    drapeaux = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    p = subprocess.Popen(argv, cwd=str(dossier), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=drapeaux, close_fds=True)
    return p.pid


def commande(reglages, bureau=None):
    """La ligne de commande du moteur : le fichier du bureau s'il existe (tous ses projets), sinon ce seul projet."""
    bureau = Path(bureau or BUREAU_PAR_DEFAUT).expanduser()
    suite = ["--bureau", str(bureau)] if bureau.is_file() else ["--reglages", str(Path(reglages).resolve())]
    return [sys.executable, "-m", "moteur", *suite]


def demarrer(reglages, trouver=appel.trouver_claude, lancer=lancer_moteur, fichier_verrou=None, vivant=verrou.pid_vivant,
             bureau=None):
    """Rend `{"ok", "message"}`."""
    chemin = Path(fichier_verrou) if fichier_verrou else verrou.chemin_par_defaut()
    if verrou.actif(chemin, vivant) is not None:
        return {"ok": True, "message": "L'orchestrateur tourne déjà."}
    if not trouver():
        return {"ok": False, "message": "La commande claude n'est pas installée (" + INSTALLER_CLAUDE + ") : le moteur "
                                        "en a besoin pour appeler les agents."}
    pid = lancer(commande(reglages, bureau), RACINE)
    verrou.ecrire(chemin, pid)
    return {"ok": True, "message": "L'orchestrateur démarre."}
