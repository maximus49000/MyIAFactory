import json
import tempfile
import unittest
from pathlib import Path

from bureau import deport, reglages


class TestDeportReglages(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)

    def _ecrire(self, donnees, nom="r.json"):
        (self.tmp / nom).write_text(json.dumps(donnees), encoding="utf-8")
        return self.tmp / nom

    def test_absent_donne_les_defauts(self):
        d = reglages.charger(self.tmp / "absent.json")["deport"]
        self.assertEqual(d["lieux"], deport.LIEUX_PAR_DEFAUT)
        self.assertEqual(d["lieux"]["apk"], "poste")
        self.assertEqual(d["commandes"], {})
        self.assertEqual(d["charge_heure"], "03:00")

    def test_defauts_non_partages_entre_chargements(self):
        reglages.charger(self.tmp / "absent.json")["deport"]["lieux"]["apk"] = "github"
        self.assertEqual(reglages.charger(self.tmp / "absent.json")["deport"]["lieux"]["apk"], "poste")

    def test_lieux_partiels_completes_par_les_defauts(self):
        d = reglages.charger(self._ecrire({"deport": {"lieux": {"apk": "github"}}}))["deport"]
        self.assertEqual(d["lieux"]["apk"], "github")
        for action in ("tests", "emulateur", "charge"):
            self.assertEqual(d["lieux"][action], "poste")
        self.assertEqual(d["charge_heure"], "03:00")

    def test_lieu_invalide_rejete(self):
        for lieux in ({"emulateur": "github"}, {"apk": "mars"}, {"inconnue": "poste"}, {"apk": "serveur"}):
            with self.assertRaises(reglages.ReglagesInvalides):
                reglages.charger(self._ecrire({"deport": {"lieux": lieux}}))

    def test_charge_heure(self):
        d = reglages.charger(self._ecrire({"deport": {"charge_heure": "23:59"}}))["deport"]
        self.assertEqual(d["charge_heure"], "23:59")
        for h in ("25:00", "3:00", "12:60", "abc", 300, None):
            with self.assertRaises(reglages.ReglagesInvalides):
                reglages.charger(self._ecrire({"deport": {"charge_heure": h}}))

    def test_commandes_chaines_seulement(self):
        d = reglages.charger(self._ecrire({"deport": {"commandes": {"tests": "make t"}}}))["deport"]
        self.assertEqual(d["commandes"], {"tests": "make t"})
        for c in ({"tests": 3}, ["x"], {"inconnue": "x"}):
            with self.assertRaises(reglages.ReglagesInvalides):
                reglages.charger(self._ecrire({"deport": {"commandes": c}}))

    def test_deport_pas_un_dictionnaire_rejete(self):
        with self.assertRaises(reglages.ReglagesInvalides):
            reglages.charger(self._ecrire({"deport": "github"}))

    def test_fixer_deport_ecrit_et_conserve_le_reste(self):
        chemin = self._ecrire({"charge_max": 60})
        r = reglages.fixer_deport(chemin, {"lieux": {"tests": "github"}, "charge_heure": "04:30"})
        self.assertEqual(r["deport"]["lieux"]["tests"], "github")
        self.assertEqual(r["deport"]["lieux"]["apk"], "poste")
        self.assertEqual(r["deport"]["charge_heure"], "04:30")
        self.assertEqual(r["charge_max"], 60)
        self.assertEqual(json.loads(chemin.read_text(encoding="utf-8"))["charge_max"], 60)

    def test_fixer_deport_valide_avant_ecrire(self):
        chemin = self._ecrire({"charge_max": 60})
        avant = chemin.read_text(encoding="utf-8")
        with self.assertRaises(reglages.ReglagesInvalides):
            reglages.fixer_deport(chemin, {"lieux": {"emulateur": "github"}})
        self.assertEqual(chemin.read_text(encoding="utf-8"), avant)

    def _bureau(self, extra):
        (self.tmp / "p").mkdir(exist_ok=True)
        self._ecrire({"charge_max": 70}, "p/r.json")
        return self._ecrire(dict({"projets": ["p/r.json"]}, **extra), "bureau.json")

    def test_lire_bureau_deport_global(self):
        b = reglages.lire_bureau(self._bureau({}))
        self.assertEqual(b["deport"]["lieux"], deport.LIEUX_PAR_DEFAUT)
        b = reglages.lire_bureau(self._bureau({"deport": {"lieux": {"tests": "github"}}}))
        self.assertEqual(b["deport"]["lieux"]["tests"], "github")
        self.assertEqual(b["deport"]["lieux"]["apk"], "poste")

    def test_lire_bureau_rejette_un_lieu_inconnu(self):
        with self.assertRaises(reglages.ReglagesInvalides):
            reglages.lire_bureau(self._bureau({"deport": {"lieux": {"apk": "mars"}}}))


if __name__ == "__main__":
    unittest.main()


class TestDeportReglagesParCatalogue(unittest.TestCase):
    """Les lieux et commandes sont validés contre le catalogue du projet ; le réglage du bureau reste permissif."""

    def test_projet_android_refuse_charge_et_accepte_lint(self):
        from bureau.deport_types import CATALOGUES
        android = CATALOGUES["application-mobile-android"]
        with self.assertRaises(reglages.ReglagesInvalides) as c:
            reglages.normaliser_deport({"lieux": {"charge": "poste"}}, catalogue=android)
        self.assertIn("n'existe pas pour ce type de projet", str(c.exception))
        with self.assertRaises(reglages.ReglagesInvalides) as c:
            reglages.normaliser_deport({"commandes": {"charge": "x"}}, catalogue=android)
        self.assertIn("n'existe pas pour ce type de projet", str(c.exception))
        d = reglages.normaliser_deport({"lieux": {"lint": "github"}, "commandes": {"lint": "./gradlew lint"}},
                                       catalogue=android)
        self.assertEqual(d["lieux"]["lint"], "github")

    def test_sans_catalogue_toute_action_connue_est_admise_mais_pas_les_inconnues(self):
        d = reglages.normaliser_deport({"lieux": {"lint": "github", "charge": "github"},
                                        "commandes": {"release": "./gradlew assembleRelease"}})
        self.assertEqual(d["lieux"]["lint"], "github")
        with self.assertRaises(reglages.ReglagesInvalides):
            reglages.normaliser_deport({"lieux": {"bidon": "poste"}})
        with self.assertRaises(reglages.ReglagesInvalides):
            reglages.normaliser_deport({"commandes": {"bidon": "x"}})

    def test_fixer_deport_valide_contre_le_catalogue(self):
        from bureau.deport_types import CATALOGUES
        android = CATALOGUES["application-mobile-android"]
        with tempfile.TemporaryDirectory() as t:
            chemin = Path(t) / "r.json"
            chemin.write_text("{}", encoding="utf-8")
            with self.assertRaises(reglages.ReglagesInvalides):
                reglages.fixer_deport(chemin, {"lieux": {"charge": "poste"}}, android)
            r = reglages.fixer_deport(chemin, {"lieux": {"lint": "github"}}, android)
            self.assertEqual(r["deport"]["lieux"]["lint"], "github")
            self.assertEqual(json.loads(chemin.read_text(encoding="utf-8"))["deport"]["lieux"], {"lint": "github"})
