"""Le verrou d'écriture d'un fichier partagé entre processus (réglages, fichier du bureau, sceau des tests), et le
remplacement atomique qui réessaie un fichier momentanément occupé.

Reste compatible Python 3.9 : le lanceur des agents (`outils/campagne.py`, `outils/deporter.py`) l'importe."""
import contextlib
import os
import threading
import time
from pathlib import Path

_VERROU_ECRITURE = threading.Lock()     # lecture-modification-écriture d'un fichier de réglages : une à la fois ici
VERROU_ATTENTE_S = 10                   # attente au plus d'un autre processus qui écrit le même fichier
VERROU_PERIME_S = 60                    # un verrou plus vieux (processus mort) est repris
RETENTATIVES_RAPIDES = 5                # une marque reprise ou disparue : retentée sans attendre, 5 fois au plus
REMPLACER_ESSAIS = 5                   # `os.replace` refusé (Windows : un lecteur tient la cible ouverte) : réessayé
REMPLACER_PAUSE_S = 0.02
_dormir = time.sleep                    # remplaçable par les tests (aucun sommeil réel)


def _reprendre_si_perime(marque):
    """Vrai si la marque a disparu ou vient d'être reprise (périmée) : on peut retenter tout de suite. Le constat se
    fait par `lstat` (un lien cassé est une marque comme une autre) ; une marque impossible à enlever (un dossier, un
    fichier protégé) rend faux : on attend, et l'échéance tranche."""
    try:
        if time.time() - os.lstat(str(marque)).st_mtime > VERROU_PERIME_S:
            os.unlink(str(marque))
            return True
        return False
    except FileNotFoundError:
        return True
    except OSError:
        return False


@contextlib.contextmanager
def verrou_fichier(chemin, attente_s=None):
    """Une écriture à la fois sur `chemin` : verrou du processus, plus un fichier `<nom>.verrou` créé en exclusif pour
    les autres processus (le bureau et l'installation écrivent le même fichier du bureau). Attente bornée à `attente_s`
    (par défaut `VERROU_ATTENTE_S`, 10 s ; le lanceur des agents passe une attente courte) ; un verrou périmé est repris.
    `TimeoutError` si l'autre écriture ne finit pas — l'échéance est vérifiée à chaque tour, jamais de boucle sans fin.

    Le verrou du processus n'est pas réentrant : prendre un second `verrou_fichier` (même sur un autre fichier) à
    l'intérieur d'un premier, dans le même fil, lève `TimeoutError` au bout de l'attente (jamais un blocage)."""
    attente = VERROU_ATTENTE_S if attente_s is None else attente_s
    fin = time.monotonic() + max(attente, 0)
    if not _VERROU_ECRITURE.acquire(timeout=max(fin - time.monotonic(), 0)):
        raise TimeoutError(f"Une autre écriture est en cours dans ce programme : {chemin}")
    try:
        marque = Path(str(chemin) + ".verrou")
        rapides = 0                                         # retentatives immédiates (marque reprise ou disparue)
        while True:
            try:
                if os.path.lexists(str(marque)):           # Windows crée la cible d'un lien cassé malgré O_EXCL :
                    raise FileExistsError(str(marque))      # une marque en lien compte comme une marque
                os.close(os.open(str(marque), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                break
            except (FileExistsError, PermissionError):     # Windows : PermissionError pour un dossier ou une marque
                retenter = _reprendre_si_perime(marque)     # en cours de suppression
            if retenter and rapides < RETENTATIVES_RAPIDES:
                rapides += 1                                # bornées : une marque qui « disparaît » sans cesse
                continue                                    # finit par passer par l'échéance
            if time.monotonic() >= fin:
                raise TimeoutError(f"Fichier en cours d'écriture par un autre programme : {chemin}")
            time.sleep(0.05)
        try:
            yield
        finally:
            try:
                marque.unlink()
            except OSError:
                pass
    finally:
        _VERROU_ECRITURE.release()


def remplacer(source, cible):
    """`os.replace(source, cible)`, réessayé `REMPLACER_ESSAIS` fois à `REMPLACER_PAUSE_S` d'intervalle sur
    `PermissionError` (Windows refuse de remplacer un fichier qu'un lecteur tient ouvert). Lève la dernière erreur."""
    for essai in range(REMPLACER_ESSAIS):
        try:
            os.replace(str(source), str(cible))
            return
        except PermissionError:
            if essai == REMPLACER_ESSAIS - 1:
                raise
            _dormir(REMPLACER_PAUSE_S)
