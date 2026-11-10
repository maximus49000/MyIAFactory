"""L'équipe : clé de titulaire -> prénom et couleur, avec persistance."""
import json
import os
import tempfile
import threading
from pathlib import Path

PRENOMS = ["Hugo", "Léa", "Lucas", "Emma", "Louis", "Chloé", "Jules", "Manon", "Arthur", "Camille",
           "Nathan", "Inès", "Théo", "Sarah", "Maxime", "Clara", "Paul", "Julie", "Antoine", "Zoé",
           "Gabriel", "Alice", "Raphaël", "Louise"]
COULEURS = ["#2f6fd0", "#d0572f", "#2fa05a", "#a02fd0", "#d0a52f", "#2fb5b5",
            "#d02f6f", "#6f7a2f", "#5a4fd0", "#b5622f", "#2f8fd0", "#8a5a3c"]


class Equipe:
    def __init__(self, chemin):
        self.chemin = Path(chemin)
        self._verrou = threading.Lock()
        self._agents = {}
        self._charger()

    def _charger(self):
        if not self.chemin.exists():
            return
        try:
            donnees = json.loads(self.chemin.read_text(encoding="utf-8-sig"))
            agents = donnees["agents"]
            if not isinstance(agents, dict):
                raise ValueError
            self._agents = {k: v for k, v in agents.items() if isinstance(v, dict)}
        except (ValueError, KeyError, TypeError, OSError):
            try:
                os.replace(self.chemin, self.chemin.with_name(self.chemin.name + ".illisible"))
            except OSError:
                pass
            self._agents = {}

    def _enregistrer(self):
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.chemin.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"agents": self._agents}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.chemin)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def _prenom_libre(self):
        pris = {a.get("prenom") for a in self._agents.values()}
        for p in PRENOMS:
            if p not in pris:
                return p
        n = len(PRENOMS) + 1
        while f"Agent {n}" in pris:
            n += 1
        return f"Agent {n}"

    def agent(self, cle, chef=False):
        with self._verrou:
            a = self._agents.get(cle)
            if a is None:
                if chef or cle == "chef":
                    prenom = "Chef"
                else:
                    prenom = self._prenom_libre()
                a = {"prenom": prenom, "couleur": COULEURS[len(self._agents) % len(COULEURS)]}
                self._agents[cle] = a
                self._enregistrer()
            r = dict(a)
            r.setdefault("prenom", str(cle))
            r.setdefault("couleur", COULEURS[0])
            return r
