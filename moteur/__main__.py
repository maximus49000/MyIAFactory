"""py -3.12 -m moteur [--bureau ~/MyIAFactory/bureau.json | --reglages <fichier>] : le moteur de la factory, un pour tous
les projets du bureau.

Il tourne jusqu'à Ctrl+C. Un seul moteur à la fois (verrou `~/MyIAFactory/moteur.pid`). Rien n'est écrit ailleurs que
dans les projets, par leurs commandes `lancer`, et dans ce verrou."""
import argparse
import sys
import threading
from pathlib import Path

from moteur import boucle, verrou


def main(argv=None):
    p = argparse.ArgumentParser(prog="moteur", description="Le moteur procédural de la factory.")
    cible = p.add_mutually_exclusive_group()
    cible.add_argument("--bureau", help="le fichier du bureau (liste des projets), relu à chaque passage")
    cible.add_argument("--reglages", help="le fichier de réglages d'un seul projet (sans fichier du bureau)")
    p.add_argument("--verrou", default=str(verrou.chemin_par_defaut()), help="le fichier du verrou (essais)")
    a = p.parse_args(argv)
    if a.reglages:
        reglages = Path(a.reglages).expanduser()
        if not reglages.is_file():
            print(f"Réglages introuvables : {reglages}", file=sys.stderr)
            return 2
        moteur = boucle.Moteur([boucle.ouvrir_projet(reglages)])
    else:
        bureau = Path(a.bureau or boucle.BUREAU_PAR_DEFAUT).expanduser()
        if not bureau.is_file():
            print(f"Fichier du bureau introuvable : {bureau}", file=sys.stderr)
            return 2
        moteur = boucle.Moteur([], bureau=bureau)
    if not verrou.prendre(a.verrou):
        print("Un moteur tourne déjà.", file=sys.stderr)
        return 3
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
    finally:
        verrou.liberer(a.verrou)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
