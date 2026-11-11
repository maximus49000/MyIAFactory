"""Le bureau commun lancé par l'installation : en arrière-plan, détaché de la discussion, relancé si besoin.

Le PID du bureau lancé ici est gardé dans `~/MyIAFactory/bureau.pid`, sa sortie dans `~/MyIAFactory/bureau.log`.
Un bureau lancé à la main (sans ce fichier) n'est jamais arrêté : l'utilisateur le fait lui-même.
"""
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from bureau import reglages
from installation import dossier
from installation.dossier import Echec

LANCER = Path(__file__).resolve().parent.parent / "lancer.py"
DELAI = 10   # secondes pour qu'un bureau réponde (ou s'arrête)


def fichier_pid():
    return dossier.racine() / "bureau.pid"


def journal():
    return dossier.racine() / "bureau.log"


def repond(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def drapeaux_windows():
    """Une console cachée, pas de console du tout : sans console, chaque commande lancée par le bureau (relevé,
    mesure de la charge, toutes les quelques secondes) ouvrirait sa propre fenêtre noire."""
    return subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP


def demarrer(bureau_json, journal_):
    """Lance `lancer.py serveur --bureau` détaché : il survit à la commande qui l'a lancé. Rend son PID."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    commande = [sys.executable, str(LANCER), "serveur", "--bureau", str(bureau_json)]
    with open(journal_, "wb") as sortie:
        kw = dict(stdin=subprocess.DEVNULL, stdout=sortie, stderr=subprocess.STDOUT, env=env, close_fds=True)
        if sys.platform != "win32":
            return subprocess.Popen(commande, start_new_session=True, **kw).pid
        base = drapeaux_windows()
        try:   # hors du « job » de la discussion, sinon le bureau meurt avec elle
            return subprocess.Popen(commande, creationflags=base | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kw).pid
        except OSError:
            return subprocess.Popen(commande, creationflags=base, **kw).pid


def arreter(pid):
    try:
        os.kill(pid, signal.SIGTERM)   # Windows : TerminateProcess
    except OSError:
        pass   # déjà arrêté


def _lire_pid():
    try:
        return int(fichier_pid().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _journal_lignes():
    try:
        return [l for l in journal().read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    except OSError:
        return []


def _attendre(condition, attendre, delai):
    fin = time.monotonic() + delai
    while True:
        if condition():
            return True
        if time.monotonic() >= fin:
            return False
        attendre(0.2)


def lancer(relancer=False, bureau_json=None, demarrer=demarrer, arreter=arreter, sonde=repond, attendre=time.sleep,
           delai=DELAI):
    """Rend `{"action": "lance" | "relance" | "deja_lance", "url", "annonces", "journal"}` ; `Echec` sinon."""
    bureau_json = Path(bureau_json or dossier.bureau())
    try:
        port = reglages.lire_bureau(bureau_json)["port"]
    except reglages.ReglagesInvalides as e:
        raise Echec(str(e))
    url = f"http://127.0.0.1:{port}/"
    action = "lance"
    if sonde(port):
        if not relancer:
            return {"action": "deja_lance", "url": url, "annonces": [], "journal": str(journal())}
        pid = _lire_pid()
        if pid is None:
            raise Echec(f"Un bureau lancé à la main tourne déjà sur le port {port} : arrêtez-le (Ctrl+C dans sa "
                        "fenêtre), puis relancez cette commande.")
        arreter(pid)
        if not _attendre(lambda: not sonde(port), attendre, delai):
            raise Echec(f"Le bureau du port {port} ne s'arrête pas : arrêtez-le à la main, puis relancez cette commande.")
        action = "relance"
    fichier_pid().unlink(missing_ok=True)
    pid = demarrer(bureau_json, journal())
    if not _attendre(lambda: sonde(port), attendre, delai):
        arreter(pid)
        raise Echec("Le bureau ne répond pas : " + (" ".join(_journal_lignes()[-5:]) or "aucune sortie")
                    + f" (journal : {journal()})")
    fichier_pid().write_text(str(pid), encoding="utf-8")
    _attendre(lambda: bool(_journal_lignes()), attendre, delai)   # les annonces suivent de peu l'ouverture du port
    annonces = [l.replace(" (Ctrl+C pour arrêter)", "") for l in _journal_lignes()]   # pas de fenêtre ici
    return {"action": action, "url": url, "annonces": annonces, "journal": str(journal())}
