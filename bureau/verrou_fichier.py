"""Le verrou d'écriture d'un fichier partagé entre processus (réglages, fichier du bureau, sceau des tests).

Reste compatible Python 3.9 : le lanceur des agents (`outils/campagne.py`, `outils/deporter.py`) l'importe."""
import contextlib
import os
import threading
import time
from pathlib import Path

_VERROU_ECRITURE = threading.Lock()     # lecture-modification-écriture d'un fichier de réglages : une à la fois ici
VERROU_ATTENTE_S = 10                   # attente au plus d'un autre processus qui écrit le même fichier
VERROU_PERIME_S = 60                    # un verrou plus vieux (processus mort) est repris


@contextlib.contextmanager
def verrou_fichier(chemin):
    """Une écriture à la fois sur `chemin` : verrou du processus, plus un fichier `<nom>.verrou` créé en exclusif pour
    les autres processus (le bureau et l'installation écrivent le même fichier du bureau). Attente bornée ; un verrou
    périmé est repris. `TimeoutError` si l'autre écriture ne finit pas.

    Le verrou du processus n'est pas réentrant : ne jamais prendre un second `verrou_fichier` (même sur un autre
    fichier) à l'intérieur d'un premier, dans le même fil."""
    marque = Path(str(chemin) + ".verrou")
    with _VERROU_ECRITURE:
        fin = time.monotonic() + VERROU_ATTENTE_S
        while True:
            try:
                os.close(os.open(str(marque), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                break
            except FileExistsError:
                try:
                    if time.time() - marque.stat().st_mtime > VERROU_PERIME_S:
                        marque.unlink()
                        continue
                except FileNotFoundError:
                    continue            # rendu entre-temps : on retente tout de suite
                except OSError:
                    pass                # impossible à reprendre (un dossier, un fichier protégé) : l'attente reste bornée
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
