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
        self.assertIs(r["prix_automatiques"], True)

    def test_le_fichier_complete_les_defauts(self):
        (self.tmp / "r.json").write_text('{"charge_max": 60}', encoding="utf-8")
        r = reglages.charger(self.tmp / "r.json")
        self.assertEqual((r["charge_max"], r["port"]), (60, 8770))
        self.assertEqual(r["dossier"], str(self.tmp))

    def test_reglage_couche_valide(self):
        self.assertEqual(reglages.charger(self.tmp / "absent.json")["moteur"], {"couche": "claude"})
        for couche in ("claude", "api"):
            (self.tmp / "r.json").write_text(json.dumps({"moteur": {"couche": couche}}), encoding="utf-8")
            self.assertEqual(reglages.charger(self.tmp / "r.json")["moteur"]["couche"], couche)
        for mauvais in ({"moteur": {"couche": "autre"}}, {"moteur": "api"}, {"moteur": {"couche": 1}}):
            (self.tmp / "r.json").write_text(json.dumps(mauvais), encoding="utf-8")
            with self.assertRaises(reglages.ReglagesInvalides, msg=repr(mauvais)):
                reglages.charger(self.tmp / "r.json")

    def test_agents_cloud_max(self):
        self.assertEqual(reglages.charger(self.tmp / "absent.json")["agents_cloud_max"], 3)
        for v in (0, 17, "3", True, None):
            (self.tmp / "r.json").write_text(json.dumps({"agents_cloud_max": v}), encoding="utf-8")
            with self.assertRaises(reglages.ReglagesInvalides, msg=repr(v)):
                reglages.charger(self.tmp / "r.json")

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

    def bureau(self, **extra):
        (self.tmp / "p").mkdir(exist_ok=True)
        (self.tmp / "p" / "r.json").write_text("{}", encoding="utf-8")
        (self.tmp / "bureau.json").write_text(json.dumps({"projets": ["p/r.json"], **extra}), encoding="utf-8")
        return reglages.lire_bureau(self.tmp / "bureau.json")

    def test_lire_bureau_acces(self):
        self.assertEqual(self.bureau()["acces"], {"tailscale": False, "reseau_local": False})
        self.assertEqual(self.bureau(acces={"tailscale": True})["acces"], {"tailscale": True, "reseau_local": False})

    def test_lire_bureau_acces_invalide(self):
        for v in ([], "tailscale", {"tailscale": 1}, {"wifi": True}, None):
            with self.assertRaises(reglages.ReglagesInvalides, msg=repr(v)):
                self.bureau(acces=v)

    def test_bureau_couche_par_defaut_et_api(self):
        self.assertEqual(self.bureau()["moteur"], {"couche": "claude"})
        self.assertEqual(self.bureau(moteur={"couche": "api"})["moteur"], {"couche": "api"})
        self.assertEqual(self.bureau(moteur={})["moteur"], {"couche": "claude"})

    def test_bureau_couche_invalide(self):
        for v in ([], "api", {"couche": "gpt"}, {"couche": 1}, None):
            with self.assertRaises(reglages.ReglagesInvalides, msg=repr(v)):
                self.bureau(moteur=v)


if __name__ == "__main__":
    unittest.main()
