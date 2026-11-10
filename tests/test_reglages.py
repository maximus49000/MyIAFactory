import json
import tempfile
import unittest
from pathlib import Path

from bureau import reglages


class TestReglages(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)

    def test_fichier_absent_donne_les_defauts(self):
        r = reglages.charger(self.tmp / "absent.json")
        self.assertEqual((r["port"], r["charge_max"], r["fraicheur_min"]), (8770, 75, 30))

    def test_le_fichier_complete_les_defauts(self):
        (self.tmp / "r.json").write_text('{"charge_max": 60}', encoding="utf-8")
        r = reglages.charger(self.tmp / "r.json")
        self.assertEqual((r["charge_max"], r["port"]), (60, 8770))
        self.assertEqual(r["dossier"], str(self.tmp))

    def test_fichier_avec_bom(self):
        # PowerShell 5.1 écrit un BOM avec -Encoding utf8.
        (self.tmp / "r.json").write_bytes(bytes([0xEF, 0xBB, 0xBF]) + b'{"charge_max": 60}')
        self.assertEqual(reglages.charger(self.tmp / "r.json")["charge_max"], 60)

    def test_json_invalide(self):
        (self.tmp / "r.json").write_text("{", encoding="utf-8")
        with self.assertRaises(reglages.ReglagesInvalides):
            reglages.charger(self.tmp / "r.json")

    def test_fixer_charge_max_conserve_le_reste(self):
        (self.tmp / "r.json").write_text('{"port": 9000}', encoding="utf-8")
        reglages.fixer_charge_max(self.tmp / "r.json", 65)
        d = json.loads((self.tmp / "r.json").read_text(encoding="utf-8"))
        self.assertEqual(d, {"port": 9000, "charge_max": 65})

    def test_fixer_charge_max_refuse_hors_bornes(self):
        for v in (29, 96, "70", 70.5):
            with self.assertRaises(ValueError):
                reglages.fixer_charge_max(self.tmp / "r.json", v)


if __name__ == "__main__":
    unittest.main()
