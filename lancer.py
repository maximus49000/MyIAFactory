"""Point d'entrée :
  py -3.12 lancer.py serveur --reglages <réglages d'un projet>
  py -3.12 lancer.py serveur --bureau <fichier du bureau, qui liste plusieurs projets>
  py -3.12 lancer.py charge --reglages <réglages d'un projet>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bureau import serveur  # noqa: E402

if __name__ == "__main__":
    sys.exit(serveur.main(sys.argv[1:]))
