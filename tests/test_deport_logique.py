import unittest

from bureau import deport


class TestDeportLogique(unittest.TestCase):
    def test_defaut_tout_au_poste(self):
        self.assertEqual(deport.lieu_effectif({}, {}, "apk"), "poste")
        self.assertTrue(all(v == "poste" for v in deport.LIEUX_PAR_DEFAUT.values()))

    def test_surcharge_du_projet(self):
        self.assertEqual(deport.lieu_effectif({"tests": "github"}, {"tests": "poste"}, "tests"), "poste")
        self.assertEqual(deport.lieu_effectif({"tests": "github"}, {}, "tests"), "github")

    def test_emulateur_github_refuse(self):
        with self.assertRaises(ValueError) as c:
            deport.valider_lieux({"emulateur": "github"})
        self.assertIn("peu fiable", str(c.exception))

    def test_serveur_refuse_a_l_etape_1(self):
        with self.assertRaises(ValueError):
            deport.valider_lieux({"apk": "serveur"})       # ni servie ni routée au serveur

    def test_serveur_accepte_pour_les_tests_routes(self):
        self.assertEqual(deport.valider_lieux({"tests": "serveur"}), {"tests": "serveur"})

    def test_serveur_accepte_a_l_etape_serveur(self):
        self.assertEqual(deport.valider_lieux({"tests": "serveur"}, etape_serveur=True), {"tests": "serveur"})

    def test_action_inconnue_refusee(self):
        with self.assertRaises(ValueError):
            deport.valider_lieux({"bidon": "poste"})

    def test_lieu_inconnu_refuse(self):
        with self.assertRaises(ValueError):
            deport.valider_lieux({"tests": "lune"}, etape_serveur=True)

    def test_attend_l_apk_d_un_autre_lieu(self):
        self.assertEqual(deport.a_attendre({"apk": "github", "tests": "poste"}, "tests"), ["apk"])

    def test_rien_a_attendre_au_meme_lieu(self):
        self.assertEqual(deport.a_attendre({"apk": "github", "tests": "github"}, "tests"), [])
        self.assertEqual(deport.a_attendre({}, "tests"), [])

    def test_avertissement_dit_la_chaine(self):
        textes = deport.avertissements({"apk": "github", "tests": "poste"})
        # Les actions absentes tournent au poste par défaut : tests, emulateur et charge attendent toutes l'APK.
        self.assertEqual(len(textes), 3)
        texte = [t for t in textes if "« tests »" in t][0]
        for mot in ("tests", "poste", "GitHub", "même lieu"):
            self.assertIn(mot, texte)
        self.assertEqual(deport.avertissements({"apk": "poste", "tests": "poste"}), [])


if __name__ == "__main__":
    unittest.main()


class TestLieuxAbimes(unittest.TestCase):
    def test_avertissements_ne_levent_pas_sur_un_lieu_inconnu(self):
        from bureau.deport import avertissements
        textes = avertissements({"apk": "nuage", "tests": ["x"]})
        self.assertTrue(all(isinstance(t, str) for t in textes))


class TestCatalogueIllisible(unittest.TestCase):
    def test_factory_json_trop_profond_donne_le_generique(self):
        import tempfile
        from pathlib import Path
        from bureau.deport_types import catalogue_du_projet
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "factory.json").write_text("[" * 100000 + "]" * 100000, encoding="utf-8")
            self.assertEqual(catalogue_du_projet(t)[0], "generique")
