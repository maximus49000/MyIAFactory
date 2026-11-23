import json
import tempfile
import threading
import unittest
from pathlib import Path

from bureau import reglages


class TestNiveauxBureau(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        (self.tmp / "p").mkdir()
        (self.tmp / "p" / "reglages.json").write_text("{}", encoding="utf-8")
        self.bureau = self.tmp / "bureau.json"

    def _ecrire(self, extra=None):
        d = {"port": 8800, "projets": ["p/reglages.json"], "agents_abonnement_max": 4}
        d.update(extra or {})
        self.bureau.write_text(json.dumps(d), encoding="utf-8")
        return d

    def _lire_json(self):
        return json.loads(self.bureau.read_text(encoding="utf-8"))

    def test_lire_bureau_sans_nouvelles_cles(self):
        self._ecrire()
        b = reglages.lire_bureau(self.bureau)
        self.assertEqual(b["reglages"], {})
        self.assertEqual(b["types"], {})
        self.assertEqual(b["deport_lieux_explicites"], {})
        self.assertEqual(b["deport"]["lieux"], reglages.normaliser_deport({}, "x")["lieux"])

    def test_lire_bureau_rend_les_lieux_explicites(self):
        self._ecrire({"deport": {"lieux": {"tests": "github"}}})
        b = reglages.lire_bureau(self.bureau)
        self.assertEqual(b["deport_lieux_explicites"], {"tests": "github"})

    def test_lire_bureau_lit_les_types(self):
        self._ecrire({"types": {"android": {"deport": {"lieux": {"tests": "github"}}}}})
        b = reglages.lire_bureau(self.bureau)
        self.assertEqual(b["types"]["android"]["deport"]["lieux"], {"tests": "github"})

    def test_lire_bureau_refuse_id_inconnu(self):
        self._ecrire({"reglages": {"inconnu_xyz": True}})
        with self.assertRaises(reglages.ReglagesInvalides) as c:
            reglages.lire_bureau(self.bureau)
        self.assertIn("Fichier du bureau", str(c.exception))

    def test_lire_bureau_refuse_formes_invalides(self):
        for extra in ({"reglages": []}, {"types": []}, {"types": {"android": []}},
                      {"types": {"Mauvais Genre": {}}},
                      {"types": {"android": {"reglages": []}}},
                      {"types": {"android": {"deport": {"lieux": {"action_inconnue": "poste"}}}}},
                      {"types": {"android": {"deport": []}}}):
            with self.subTest(extra=extra):
                self._ecrire(extra)
                with self.assertRaises(reglages.ReglagesInvalides) as c:
                    reglages.lire_bureau(self.bureau)
                self.assertIn("Fichier du bureau", str(c.exception))

    def test_fixer_niveau_pose_et_efface_en_elaguant(self):
        avant = self._ecrire()
        for chemin in (("deport", "lieux", "tests"), ("types", "android", "deport", "lieux", "tests")):
            with self.subTest(chemin=chemin):
                self.assertEqual(reglages.fixer_niveau_bureau(self.bureau, chemin, "github"), "github")
                d = self._lire_json()
                for c in chemin:
                    d = d[c]
                self.assertEqual(d, "github")
                self.assertIsNone(reglages.fixer_niveau_bureau(self.bureau, chemin, None))
                self.assertEqual(self._lire_json(), avant)

    def test_fixer_niveau_garde_le_reste(self):
        self._ecrire({"deport": {"lieux": {"tests": "poste"}}})
        reglages.fixer_niveau_bureau(self.bureau, ("types", "android", "deport", "lieux", "tests"), "github")
        d = self._lire_json()
        self.assertEqual((d["port"], d["agents_abonnement_max"], d["projets"]), (8800, 4, ["p/reglages.json"]))
        self.assertEqual(d["deport"]["lieux"], {"tests": "poste"})
        reglages.fixer_niveau_bureau(self.bureau, ("types", "android", "deport", "lieux", "tests"), None)
        self.assertEqual(self._lire_json()["deport"]["lieux"], {"tests": "poste"})

    def test_fixer_niveau_efface_une_cle_absente_sans_rien_creer(self):
        avant = self._ecrire()
        reglages.fixer_niveau_bureau(self.bureau, ("types", "android", "reglages", "x"), None)
        self.assertEqual(self._lire_json(), avant)

    def test_ecritures_concurrentes(self):
        self._ecrire()
        erreurs = []

        def ecrire(chemin):
            try:
                for i in range(20):
                    reglages.fixer_niveau_bureau(self.bureau, chemin, "github" if i % 2 else "poste")
            except BaseException as e:  # noqa: BLE001
                erreurs.append(e)

        a, b = ("deport", "lieux", "tests"), ("types", "android", "deport", "lieux", "tests")
        fils = [threading.Thread(target=ecrire, args=(c,)) for c in (a, b)]
        [f.start() for f in fils]
        [f.join() for f in fils]
        self.assertEqual(erreurs, [])
        d = self._lire_json()
        self.assertEqual(d["deport"]["lieux"]["tests"], "github")
        self.assertEqual(d["types"]["android"]["deport"]["lieux"]["tests"], "github")

    def test_effacer_cle_projet(self):
        p = self.tmp / "p" / "reglages.json"
        p.write_text(json.dumps({"charge_max": 60, "lecons_auto": True}), encoding="utf-8")
        r = reglages.effacer_cle(p, "lecons_auto")
        self.assertIs(r["lecons_auto"], False)  # revient au défaut
        self.assertEqual(json.loads(p.read_text(encoding="utf-8")), {"charge_max": 60})
        self.assertEqual(r["charge_max"], 60)
        reglages.effacer_cle(p, "absente")  # sans effet
        self.assertEqual(json.loads(p.read_text(encoding="utf-8")), {"charge_max": 60})


if __name__ == "__main__":
    unittest.main()
