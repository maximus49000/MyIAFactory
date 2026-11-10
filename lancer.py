"""Point d'entrée : py -3.12 lancer.py serveur|charge --reglages <chemin>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bureau import serveur  # noqa: E402

if __name__ == "__main__":
    sys.exit(serveur.main(sys.argv[1:]))
