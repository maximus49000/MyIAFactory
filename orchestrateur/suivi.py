"""Le suivi générique : un fichier JSON (fonctionnalités, tâches, file, décisions, demandes, leçons).

Il est réécrit par remplacement atomique, sous un verrou de fichier : l'orchestrateur et la commande d'actions
du bureau y écrivent en même temps sans rien perdre.
"""
import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DELAI_VERROU_S = 5
VERROU_PERIME_S = 30      # un verrou plus vieux est celui d'un processus mort


class SuiviOccupe(Exception):
    pass


def maintenant():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def vide():
    return {"version": 1, "factory": {"etat": "en marche", "depuis": None}, "reveil": None, "compteurs": {},
            "fonctionnalites": [], "taches": [], "decisions_projet": [], "demandes": [], "lecons": [],
            "livrable": None}


class Suivi:
    def __init__(self, chemin):
        self.chemin = Path(chemin)
        self.verrou = self.chemin.with_name(self.chemin.name + ".verrou")

    def lire(self):
        """Le suivi tel qu'il est écrit (jamais à moitié : l'écriture remplace le fichier d'un coup)."""
        donnees = vide()
        if self.chemin.exists():
            lu = json.loads(self.chemin.read_text(encoding="utf-8-sig"))
            if isinstance(lu, dict):
                donnees.update(lu)
        return donnees

    def _prendre(self):
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fin = time.monotonic() + DELAI_VERROU_S
        while True:
            try:
                os.close(os.open(self.verrou, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return
            except FileExistsError:
                try:
                    if time.time() - self.verrou.stat().st_mtime > VERROU_PERIME_S:
                        self.verrou.unlink()
                        continue
                except OSError:
                    continue   # le verrou vient de disparaître : on réessaie tout de suite
            except PermissionError:
                pass   # Windows : le verrou est en train d'être effacé par un autre processus ; il est encore pris
            if time.monotonic() > fin:
                raise SuiviOccupe(f"Le suivi est occupé (verrou {self.verrou.name} gardé plus de "
                                  f"{DELAI_VERROU_S} s).")
            time.sleep(0.01)

    @contextmanager
    def transaction(self):
        """Lit le suivi sous verrou, le rend, et le réécrit à la sortie (sauf erreur)."""
        self._prendre()
        try:
            donnees = self.lire()
            yield donnees
            self._ecrire(donnees)
        finally:
            try:
                self.verrou.unlink()
            except OSError:
                pass

    def _ecrire(self, donnees):
        fd, tmp = tempfile.mkstemp(dir=str(self.chemin.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(donnees, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp, self.chemin)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


# --- Aides sur le contenu (fonctions pures sur le dict du suivi).

def suivant(donnees, cle):
    """Le numéro suivant d'un compteur (`f`, `t`, `d`, `m`, `r`, `l`)."""
    n = donnees["compteurs"].get(cle, 0) + 1
    donnees["compteurs"][cle] = n
    return n


def fonctionnalite(donnees, i):
    return next((f for f in donnees["fonctionnalites"] if f["id"] == i), None)


def tache(donnees, i):
    return next((t for t in donnees["taches"] if t["id"] == i), None)


def nouvelle_fonctionnalite(donnees, nom, etape="cadrage"):
    f = {"id": f"f{suivant(donnees, 'f')}", "nom": nom, "etape": etape, "genre": None, "workflow": None,
         "agent_cadrage": None, "discussion": [],
         "attend_reponse": False, "cahier": None, "methode": None, "livrable": None, "catalogue": False,
         "decisions": [], "file": [], "elements": {}, "maj": maintenant()}
    donnees["fonctionnalites"].append(f)
    return f


def ajouter_message(donnees, f, auteur, texte, images=None, t=None):
    m = {"id": f"m{suivant(donnees, 'm')}", "t": t or maintenant(), "auteur": auteur, "texte": texte}
    if images:
        m["images"] = list(images)
    f["discussion"].append(m)
    f["attend_reponse"] = auteur == "utilisateur"
    f["maj"] = maintenant()
    return m
