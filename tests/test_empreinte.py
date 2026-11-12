"""L'empreinte carbone estimée (méthode EcoLogits) : le calcul, la résolution des modèles, les cumuls."""
import unittest

from bureau import empreinte


class TestControle(unittest.TestCase):
    def test_mille_tokens_de_sortie_sonnet_5_5(self):
        r = empreinte.estimer("claude-sonnet-5-5", 1000)
        self.assertAlmostEqual(r["wh_min"], 1.13, places=2)
        self.assertAlmostEqual(r["wh_max"], 1.80, places=2)
        self.assertAlmostEqual(r["usage_min"], 0.43, places=2)
        self.assertAlmostEqual(r["usage_max"], 0.69, places=2)
        self.assertAlmostEqual(r["fabrication"], 0.031, places=3)
        self.assertAlmostEqual(r["min"], r["usage_min"] + r["fabrication"])
        self.assertAlmostEqual(r["max"], r["usage_max"] + r["fabrication"])
        self.assertFalse(r.get("assimile"))
        self.assertEqual(r["modele"], "claude-sonnet-5-5")

    def test_plus_de_tokens_plus_d_empreinte(self):
        a, b = empreinte.estimer("claude-opus-5-5", 1000), empreinte.estimer("claude-opus-5-5", 5000)
        self.assertGreater(b["min"], a["min"])
        self.assertGreater(b["wh_max"], a["wh_max"])

    def test_zero_token_zero_empreinte(self):
        r = empreinte.estimer("claude-sonnet-5-5", 0)
        self.assertEqual((r["min"], r["max"], r["wh_min"], r["wh_max"]), (0, 0, 0, 0))

    def test_haiku_dense_a_deux_gpu_au_plus(self):
        r = empreinte.estimer("claude-haiku-5-5", 1000)
        self.assertLess(r["max"], empreinte.estimer("claude-sonnet-5-5", 1000)["max"])

    def test_valeurs_invalides_sans_chiffre(self):
        for v in (None, -5, "12", float("nan"), True):
            self.assertIsNone(empreinte.estimer("claude-sonnet-5-5", v))


class TestModeles(unittest.TestCase):
    def test_nom_exact_non_assimile(self):
        self.assertEqual(empreinte.resoudre("claude-opus-4-8"), ("claude-opus-4-8", False))

    def test_famille_seule_prend_la_plus_recente_sans_signal(self):
        self.assertEqual(empreinte.resoudre("Sonnet"), ("claude-sonnet-5-5", False))
        self.assertEqual(empreinte.resoudre("opus"), ("claude-opus-5-5", False))
        self.assertEqual(empreinte.resoudre("HAIKU"), ("claude-haiku-5-5", False))

    def test_suffixe_de_date_et_points(self):
        self.assertEqual(empreinte.resoudre("claude-sonnet-5-5-20260301"), ("claude-sonnet-5-5", False))
        self.assertEqual(empreinte.resoudre("Sonnet 5.5"), ("claude-sonnet-5-5", False))

    def test_version_inconnue_la_plus_proche_de_la_famille_signalee(self):
        self.assertEqual(empreinte.resoudre("claude-sonnet-4-9"), ("claude-sonnet-5", True))
        self.assertEqual(empreinte.resoudre("claude-opus-6"), ("claude-opus-5-5", True))
        self.assertEqual(empreinte.resoudre("claude-haiku-3-5"), ("claude-haiku-4-5", True))

    def test_estimation_signale_l_assimilation(self):
        self.assertTrue(empreinte.estimer("claude-opus-6", 1000)["assimile"])

    def test_famille_inconnue_ou_sans_donnees_pas_de_valeur(self):
        for m in ("gpt-5", "", None, 3, "Fable", "claude-fable-5-1"):
            self.assertIsNone(empreinte.estimer(m, 1000), m)


class TestCumul(unittest.TestCase):
    def test_somme_et_vue(self):
        c = empreinte.Cumul()
        c.ajouter("claude-sonnet-5-5", 1000)
        c.ajouter("claude-sonnet-5-5", 1000)
        v = c.vue()
        un = empreinte.estimer("claude-sonnet-5-5", 1000)
        self.assertAlmostEqual(v["min"], 2 * un["min"], places=5)
        self.assertAlmostEqual(v["wh_max"], 2 * un["wh_max"], places=5)
        self.assertNotIn("incomplet", v)

    def test_rien_de_mesurable_pas_de_vue(self):
        c = empreinte.Cumul()
        c.ajouter("Fable", 1000)
        self.assertIsNone(c.vue())
        self.assertIsNone(empreinte.Cumul().vue())

    def test_partiel_signale_incomplet(self):
        c = empreinte.Cumul()
        c.ajouter("Sonnet", 1000)
        c.ajouter("Fable", 1000)
        self.assertTrue(c.vue()["incomplet"])

    def test_zero_token_inconnu_n_est_pas_incomplet(self):
        c = empreinte.Cumul()
        c.ajouter("Sonnet", 1000)
        c.ajouter("Fable", 0)
        self.assertNotIn("incomplet", c.vue())

    def test_assimile_se_propage_et_fusion(self):
        a, b = empreinte.Cumul(), empreinte.Cumul()
        a.ajouter("claude-opus-6", 1000)
        b.ajouter("Sonnet", 1000)
        b.ajouter(a)
        self.assertTrue(b.vue()["assimile"])


class TestPlage(unittest.TestCase):
    def test_plage_depuis_des_tokens_et_des_modeles(self):
        r = empreinte.plage([40_000, 150_000], ["Sonnet", "Haiku"])
        self.assertLess(r["min"], r["max"])
        self.assertGreater(r["min"], 0)

    def test_modele_sans_valeur_pas_de_plage(self):
        self.assertIsNone(empreinte.plage([40_000, 150_000], ["Sonnet", "Fable"]))
        self.assertIsNone(empreinte.plage([40_000, 150_000], []))

    def test_texte_en_clair(self):
        self.assertEqual(empreinte.texte({"min": 0.456, "max": 0.724}), "≈ 0,46 à 0,72 g CO₂e")
        self.assertEqual(empreinte.texte({"min": 1200, "max": 3400}), "≈ 1,2 à 3,4 kg CO₂e")
        self.assertEqual(empreinte.texte(None), "")


if __name__ == "__main__":
    unittest.main()
