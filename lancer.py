"""Point d'entrée :
  py -3.12 lancer.py serveur --reglages <réglages d'un projet>
  py -3.12 lancer.py serveur --bureau <fichier du bureau, qui liste plusieurs projets>
  py -3.12 lancer.py charge --reglages <réglages d'un projet>
  python lancer.py tests [--dossier <dossier>] [--sans-attendre] -- <commande de test>
      (les tests d'un projet, une seule campagne à la fois sur le poste : voir `outils/campagne.py` ; si les tests du
      projet sont réglés sur GitHub, ils passent par `deporter`)
  python lancer.py deporter <type> [--dossier <dossier>] [--reglages <fichier>] [--sans-attendre] [--poste] [-- <commande>]
      (une action là où le Directeur l'a réglée : poste ou GitHub Actions, avec attente des dépendances ; voir
      `outils/deporter.py`)
  py -3.12 lancer.py plateforme <etat|installer|verifier|bureau-distant> [--accord-reinstallation] [--bureau-distant] [--dossier <dossier>]
      (le serveur dédié OVH : voir `outils/plateforme.py`)
  py -3.12 lancer.py plateforme serveurs <declarer <nom> <hote> <utilisateur> [--fournisseur ovh]|lister|cle <id>|sonder <id>|apercu <id> <action>...|installer <id> <action>... [--accord]>
      (les serveurs distants génériques : voir `outils/serveur_cli.py`)
  py -3.12 lancer.py serveur-tache <lancer --apk <fichier> --mode scenario|pilote [--scenario <nom>] [--projet <dossier>] [--attendre]|etat <id>|arreter <id>|rapatrier <id> [--destination <dossier>] [--projet <dossier>]|lister> [--dossier <dossier>]
  py -3.12 lancer.py serveur-outil <id> <verbe> [arguments] [--projet <dossier>] [--dossier <dossier>]
      (les tâches d'émulation sur le serveur : voir `outils/serveur_tache_cli.py`)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bureau import serveur  # noqa: E402

if __name__ == "__main__":
    if sys.argv[1:2] in (["tests"], ["deporter"]):
        sys.path.insert(0, str(Path(__file__).resolve().parent / "outils"))
        import campagne  # noqa: E402
        import deporter  # noqa: E402
        for flux in (sys.stdout, sys.stderr):    # lu par le shell d'un agent : UTF-8, jamais d'arrêt sur un caractère
            try:
                flux.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
        if sys.argv[1] == "deporter":
            sys.exit(deporter.main(sys.argv[2:]))
        # sur GitHub, ou en attente d'une production d'ailleurs : par `deporter` ; sinon les tests au poste (campagne)
        sys.exit(deporter.lancer_tests(sys.argv[2:]))
    if sys.argv[1:2] == ["plateforme"]:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "outils"))
        import plateforme  # noqa: E402
        for flux in (sys.stdout, sys.stderr):
            try:
                flux.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
        sys.exit(plateforme.main(sys.argv[2:]))
    if sys.argv[1:2] in (["serveur-tache"], ["serveur-outil"]):
        sys.path.insert(0, str(Path(__file__).resolve().parent / "outils"))
        import serveur_tache_cli  # noqa: E402
        for flux in (sys.stdout, sys.stderr):
            try:
                flux.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
        sys.exit(serveur_tache_cli.main(sys.argv[1:]))
    sys.exit(serveur.main(sys.argv[1:]))
