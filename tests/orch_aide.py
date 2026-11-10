"""Aides communes aux tests de l'orchestrateur : un projet minimal fabriqué dans un dossier temporaire."""
import base64
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
OUTIL = RACINE / "orchestrateur" / "outil.py"
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16).decode()

FICHE_LEA = """Clé : dev-1
Prénom : Léa
Rôle : dev
Service : dev
Modèle : Sonnet
Lieu : local
Spécialité : écrans

Développe les écrans.

## Leçons
- [validée] dev-1:L0 : Nommer les écrans comme dans la maquette.
"""
FICHE_HUGO = """Clé : metier-1
Prénom : Hugo
Rôle : cadrage
Service : metier
Modèle : Opus
Lieu : local

Pose les questions de cadrage.

## Leçons
"""


def factory_minimale(dossier, **extra):
    """Un projet minimal : fichier de factory, deux fiches, réglages. Rend le chemin du fichier de factory."""
    dossier = Path(dossier)
    (dossier / "fiches").mkdir(parents=True, exist_ok=True)
    (dossier / "fiches" / "lea.md").write_text(FICHE_LEA, encoding="utf-8")
    (dossier / "fiches" / "hugo.md").write_text(FICHE_HUGO, encoding="utf-8")
    (dossier / "reglages.json").write_text(json.dumps({"images": {"racines": ["pieces"]}}), encoding="utf-8")
    f = {"skill": str(RACINE), "genre": None, "mots_interdits": [],
         "services": [{"id": "metier", "nom": "Métier"}, {"id": "dev", "nom": "Dev"}],
         "flux": [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"},
                  {"id": "relecture", "nom": "Relecture", "role": "relecteur", "service": "dev"}],
         "reglages": "reglages.json", "memoire": "memoire"}
    f.update(extra)
    chemin = dossier / "factory.json"
    chemin.write_text(json.dumps(f), encoding="utf-8")
    return chemin


class AvecProjet(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dossier = Path(self._t.name)
        self.factory = factory_minimale(self.dossier)

    def outil(self, *commande, entree=None, factory=None):
        """(code, objet) en lançant vraiment `outil.py`, comme un orchestrateur."""
        corps = None if entree is None else json.dumps(entree).encode("utf-8")
        p = subprocess.run([sys.executable, str(OUTIL), "--factory", str(factory or self.factory), *commande],
                           input=corps, stdin=None if corps else subprocess.DEVNULL,
                           capture_output=True, timeout=60)
        sortie = p.stdout.decode("utf-8")
        try:
            return p.returncode, json.loads(sortie)
        except ValueError:
            return p.returncode, sortie

    def ok(self, *commande, entree=None):
        code, objet = self.outil(*commande, entree=entree)
        self.assertEqual(code, 0, objet)
        return objet
