import shutil
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "exemples" / "demo"


def copie_demo(destination, source=DEMO):
    """Copie la démo sans ce que le serveur y écrit quand on la lance sur place (historiques, équipe) :
    un test ne doit dépendre ni de l'état de la machine ni de prix lus un jour sur Internet."""
    shutil.copytree(source, destination,
                    ignore=shutil.ignore_patterns("*.jsonl", "*.tmp", "equipe.json", "__pycache__"))
    return destination
