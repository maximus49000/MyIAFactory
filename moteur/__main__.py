"""py -3.12 -m moteur [--bureau ~/MyIAFactory/bureau.json] : le moteur de la factory, un pour tous les projets du bureau.

Il tourne jusqu'à Ctrl+C. Rien n'est écrit ailleurs que dans les projets, par leurs commandes `lancer`."""
import argparse
import sys
import threading
from pathlib import Path

from moteur import boucle


def main(argv=None):
    p = argparse.ArgumentParser(prog="moteur", description="Le moteur procédural de la factory.")
    p.add_argument("--bureau", default=boucle.BUREAU_PAR_DEFAUT, help="le fichier du bureau (liste des projets)")
    a = p.parse_args(argv)
    bureau = Path(a.bureau).expanduser()
    if not bureau.is_file():
        print(f"Fichier du bureau introuvable : {bureau}", file=sys.stderr)
        return 2
    moteur = boucle.Moteur([], bureau=bureau)
    arret = threading.Event()
    deja = 0
    try:
        while not arret.is_set():
            moteur.tour()
            for ligne in moteur.journal[deja:]:
                print(ligne, flush=True)
            deja = len(moteur.journal)
            arret.wait(boucle.PAS_S)
    except KeyboardInterrupt:
        arret.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
