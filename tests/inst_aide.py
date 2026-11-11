"""Aides communes aux tests de l'installation : un dossier utilisateur temporaire et une proposition valide."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import en_processus


def proposition_valide(dossier_projet, **extra):
    """Une proposition minimale et valide pour le dossier `dossier_projet`."""
    p = {
        "version": 1, "projet": str(Path(dossier_projet).resolve()), "cas": "vide", "nom": "Petit projet",
        "comprehension": "Un petit outil qui range des fichiers.", "genre": None, "mots_interdits": ["Petit projet"],
        "modele_orchestrateur": "Sonnet", "charge_max": 70, "agents_locaux_max": 2, "cloud": False,
        "facturation": True, "supports": ["ordinateur"], "acces": {"tailscale": False, "reseau_local": False},
        "services": [{"id": "dev", "nom": "Dev"}, {"id": "qa", "nom": "QA"}],
        "flux": [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev",
                  "justification": "Il faut écrire le code."},
                 {"id": "relecture", "nom": "Relecture", "role": "relecteur", "service": "qa",
                  "justification": "Une relecture contre la demande évite trois tours de corrections."}],
        "agents": [{"cle": "dev-1", "prenom": "Noé", "role": "dev", "service": "dev", "modele": "Sonnet",
                    "lieu": "local", "texte": "Réalise un élément."},
                   {"cle": "relecteur-1", "role": "relecteur", "service": "qa", "modele": "Haiku",
                    "lieu": "local", "texte": "Relit un élément contre la demande."}],
        "briefs": {"dev": "# Brief du rôle : dev\n\nÉcris le code.", "relecteur": "# Brief du rôle : relecteur\n\nRelis."},
        "consignes": "# Consignes propres du projet\n\nTests avant tout.",
        "controles": ["Le rangement ne perd aucun fichier.", "Un nom en double est signalé."],
        "estimation": {"tokens": [120000, 450000], "euros": None, "source": "defauts", "detail": [],
                       "explication": "Valeurs par défaut."},
    }
    p.update(copy.deepcopy(extra))
    return p


class AvecMaison(unittest.TestCase):
    """HOME et USERPROFILE sur un dossier temporaire (avec espace et accent) ; `self.projet` est un dossier vide."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.maison = self.base / "Zoé Martin"
        self.maison.mkdir()
        anciens = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE")}
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.maison)

        def rendre():
            for k, v in anciens.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.addCleanup(rendre)
        self.projet = self.base / "mes projets" / "Petit projet"
        self.projet.mkdir(parents=True)
        if en_processus.actif():   # la vérification d'interface sans un nouveau Python par commande
            patch = mock.patch("orchestrateur.verifier_interface.lancer", en_processus.lancer_verification)
            patch.start()
            self.addCleanup(patch.stop)


def instantane(dossier):
    """{chemin relatif: contenu} de tous les fichiers d'un dossier (pour vérifier que rien n'a bougé)."""
    dossier = Path(dossier)
    if not dossier.exists():
        return None
    return {str(c.relative_to(dossier)): c.read_bytes() for c in sorted(dossier.rglob("*")) if c.is_file()}
