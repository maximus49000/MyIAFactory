"""Commande d'actions de la démo B : la même que celle de la démo A, jouée sur ce dossier.

Voir `exemples/demo/actions.py` : les deux dossiers vont ensemble (copiez `exemples/` en entier). Compatible
Python 3.9 et plus, bibliothèque standard seulement.
"""
import runpy
from pathlib import Path

ICI = Path(__file__).resolve().parent
runpy.run_path(str(ICI.parent / "demo" / "actions.py"), init_globals={"DOSSIER": ICI}, run_name="__main__")
