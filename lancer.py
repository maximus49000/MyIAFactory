"""Point d'entrée :
  py -3.12 lancer.py serveur --reglages <réglages d'un projet>
  py -3.12 lancer.py serveur --bureau <fichier du bureau, qui liste plusieurs projets>
  py -3.12 lancer.py charge --reglages <réglages d'un projet>
  python lancer.py tests [--dossier <dossier>] [--sans-attendre] -- <commande de test>
      (les tests d'un projet, une seule campagne à la fois sur le poste : voir `outils/campagne.py`)
  py -3.12 lancer.py plateforme <etat|installer|verifier> [--accord-reinstallation] [--dossier <dossier>]
      (le serveur dédié OVH : voir `outils/plateforme.py`)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bureau import serveur  # noqa: E402

if __name__ == "__main__":
    if sys.argv[1:2] == ["tests"]:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "outils"))
        import campagne  # noqa: E402
        for flux in (sys.stdout, sys.stderr):    # lu par le shell d'un agent : UTF-8, jamais d'arrêt sur un caractère
            try:
                flux.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
        sys.exit(campagne.main(sys.argv[2:]))
    if sys.argv[1:2] == ["plateforme"]:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "outils"))
        import plateforme  # noqa: E402
        for flux in (sys.stdout, sys.stderr):
            try:
                flux.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
        sys.exit(plateforme.main(sys.argv[2:]))
    sys.exit(serveur.main(sys.argv[1:]))
