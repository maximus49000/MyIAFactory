"""py -3.12 -m moteur [--bureau ~/MyIAFactory/bureau.json | --reglages <fichier>] : le moteur de la factory, un pour tous
les projets du bureau.

Il tourne jusqu'à Ctrl+C. Un seul moteur à la fois (verrou `~/MyIAFactory/moteur.pid`). Rien n'est écrit ailleurs que
dans les projets, par leurs commandes `lancer`, dans ce verrou et dans l'état de la mise à jour de la skill.

Il suit les mises à jour de la skill (`installation.mise_a_jour`, toutes les 15 minutes ; `--sans-mise-a-jour` pour
ne pas les suivre) : une mise à jour faite, il relance le bureau puis se relance lui-même au premier passage où aucun
agent ne travaille."""
import argparse
import sys
import threading
from pathlib import Path

from bureau import demarrage
from installation import mise_a_jour
from moteur import boucle, verrou


def sortie_sure(flux):
    """Un journal redirigé vers un fichier sous Windows s'écrit en cp1252 : un « → » y faisait planter le moteur
    (UnicodeEncodeError, 2026-11-16 et 2026-11-17), et toute la factory s'arrêtait. Hors console, la sortie passe en
    UTF-8 ; un caractère qu'elle ne sait pas écrire est remplacé, jamais une raison de s'arrêter."""
    try:
        if not flux.isatty():
            flux.reconfigure(encoding="utf-8", errors="replace")
        else:
            flux.reconfigure(errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


def main(argv=None, lancer=demarrage.lancer_moteur):
    p = argparse.ArgumentParser(prog="moteur", description="Le moteur procédural de la factory.")
    cible = p.add_mutually_exclusive_group()
    cible.add_argument("--bureau", help="le fichier du bureau (liste des projets), relu à chaque passage")
    cible.add_argument("--reglages", help="le fichier de réglages d'un seul projet (sans fichier du bureau)")
    p.add_argument("--verrou", default=str(verrou.chemin_par_defaut()), help="le fichier du verrou (essais)")
    p.add_argument("--sans-mise-a-jour", action="store_true", help="ne pas suivre les mises à jour de la skill")
    a = p.parse_args(argv)
    suivi = {} if a.sans_mise_a_jour else {"mise_a_jour": mise_a_jour.suivre(),
                                           "relancer_bureau": mise_a_jour.relancer_le_bureau}
    if a.reglages:
        reglages = Path(a.reglages).expanduser()
        if not reglages.is_file():
            print(f"Réglages introuvables : {reglages}", file=sys.stderr)
            return 2
        moteur = boucle.Moteur([boucle.ouvrir_projet(reglages)], **suivi)
    else:
        bureau = Path(a.bureau or boucle.BUREAU_PAR_DEFAUT).expanduser()
        if not bureau.is_file():
            print(f"Fichier du bureau introuvable : {bureau}", file=sys.stderr)
            return 2
        moteur = boucle.Moteur([], bureau=bureau, **suivi)
    if not verrou.prendre(a.verrou):
        print("Un moteur tourne déjà.", file=sys.stderr)
        return 3
    arret = threading.Event()
    deja = 0

    def dire():
        nonlocal deja
        for ligne in moteur.journal[deja:]:
            print(ligne, flush=True)
        deja = len(moteur.journal)

    relancer = False
    try:
        while not arret.is_set():
            moteur.tour()
            dire()
            if moteur.relance_demandee:     # la skill a été mise à jour et rien ne travaille : place au nouveau code
                relancer = True
                break
            moteur.attendre(arret)      # une demande posée par le bureau réveille le moteur, qui la traite aussitôt
            dire()
    except KeyboardInterrupt:
        arret.set()
    finally:
        verrou.liberer(a.verrou)
    if relancer:
        # Le verrou est libéré d'abord : le nouveau moteur le prend (un autre lancé entre-temps le garde, et le nouveau
        # s'efface, code 3). Les agents détachés continuent ; le nouveau moteur les retrouve.
        lancer([sys.executable, "-m", "moteur", *(sys.argv[1:] if argv is None else argv)], demarrage.RACINE)
    return 0


if __name__ == "__main__":
    for _flux in (sys.stdout, sys.stderr):
        sortie_sure(_flux)
    raise SystemExit(main())
