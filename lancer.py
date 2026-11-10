"""Point d'entrée : py -3.12 lancer.py serveur|charge --reglages <chemin>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    try:
        from bureau import serveur
    except ImportError:
        print("Pas encore disponible.")
        sys.exit(2)
    sys.exit(serveur.main(sys.argv[1:]))
