"""Le premier lancement du bureau : un drapeau « vu », pour ne proposer l'animation d'ouverture qu'une seule fois.

Le drapeau vit dans `~/MyIAFactory/lancement.json` (`{"vu": true}`), hors de tout dépôt, et vaut pour tous les
appareils (ordinateur et téléphone associé). Sans chemin, il ne vit qu'en mémoire (les tests). Un fichier absent ou
illisible vaut « pas vu » ; une écriture impossible n'empêche rien (le drapeau reste vrai jusqu'à l'arrêt du serveur).
"""
import json
import os
import tempfile
import threading
from pathlib import Path


class Drapeau:
    def __init__(self, chemin=None):
        self.chemin = Path(chemin) if chemin is not None else None
        self._verrou = threading.Lock()
        self._vu = False

    def vu(self):
        with self._verrou:
            if self._vu or self.chemin is None:
                return self._vu
            try:
                self._vu = json.loads(self.chemin.read_text(encoding="utf-8")).get("vu") is True
            except (OSError, ValueError, AttributeError):
                pass
            return self._vu

    def marquer(self):
        with self._verrou:
            self._vu = True
            if self.chemin is None:
                return
            try:
                self.chemin.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(dir=str(self.chemin.parent), suffix=".tmp")
            except OSError:
                return
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump({"vu": True}, f)
                os.replace(tmp, self.chemin)
            except OSError:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
