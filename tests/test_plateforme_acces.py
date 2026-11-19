"""Accès et secrets de la plateforme (`outils/plateforme_acces.py`). Dossiers temporaires, jamais le vrai."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import plateforme_acces  # noqa: E402

COMPLET = {"point": "ovh-eu", "cle_app": "a", "secret": "s", "consommateur": "c", "serveur": "ns123.ip-1-2-3.eu"}


class AccesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dossier = Path(self._tmp.name)

    def test_ovh_json_absent_donne_mode_operatoire(self):
        with self.assertRaises(plateforme_acces.ErreurAcces) as ctx:
            plateforme_acces.charger_ovh(self.dossier)
        message = str(ctx.exception)
        self.assertIn("ovh.json", message)
        self.assertIn("https://eu.api.ovh.com/createToken/", message)

    def test_ovh_json_complet_est_charge(self):
        (self.dossier / "ovh.json").write_text(json.dumps(COMPLET), encoding="utf-8")
        self.assertEqual(plateforme_acces.charger_ovh(self.dossier), COMPLET)

    def test_champ_manquant_nomme_le_champ(self):
        incomplet = {k: v for k, v in COMPLET.items() if k != "secret"}
        (self.dossier / "ovh.json").write_text(json.dumps(incomplet), encoding="utf-8")
        with self.assertRaises(plateforme_acces.ErreurAcces) as ctx:
            plateforme_acces.charger_ovh(self.dossier)
        self.assertIn("secret", str(ctx.exception))

    def test_json_illisible_ne_fuit_pas_le_contenu(self):
        (self.dossier / "ovh.json").write_text('{"secret": "TOPSECRET" oups', encoding="utf-8")
        with self.assertRaises(plateforme_acces.ErreurAcces) as ctx:
            plateforme_acces.charger_ovh(self.dossier)
        self.assertNotIn("TOPSECRET", str(ctx.exception))

    def test_chemin_licence(self):
        self.assertIsNone(plateforme_acces.chemin_licence(self.dossier))
        (self.dossier / "unity.ulf").write_text("x", encoding="utf-8")
        self.assertEqual(plateforme_acces.chemin_licence(self.dossier), self.dossier / "unity.ulf")

    def test_masquer_remplace_tous_les_secrets_meme_repetes(self):
        texte = "a=abc b=xyz c=abc"
        self.assertEqual(plateforme_acces.masquer(texte, ["abc", "xyz"]), "a=*** b=*** c=***")

    def test_masquer_ignore_secret_vide(self):
        self.assertEqual(plateforme_acces.masquer("bonjour", ["", None]), "bonjour")


if __name__ == "__main__":
    unittest.main()
