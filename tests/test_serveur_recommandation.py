"""Recommandation des lieux (`outils/serveur_recommandation.py`) : logique pure, conseil seulement."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import serveur_recommandation as sr  # noqa: E402
from serveur_recommandation import Mesures, recommander  # noqa: E402

TOUS = {"poste": True, "github": True, "serveur": True}


def m(**kw):
    base = dict(duree_min={}, charge_poste=None, charge_serveur=None, quota_github_restant=None, serveur_joignable=True)
    base.update(kw)
    return Mesures(**base)


def niveaux(r):
    return {k: v["niveau"] for k, v in r.items()}


class RecommandationTests(unittest.TestCase):
    def test_lieu_non_permis_est_indisponible(self):
        r = recommander("apk", {"poste": True, "github": False, "serveur": True}, m(charge_poste=0.1, charge_serveur=0.1))
        self.assertEqual(r["github"]["niveau"], "indisponible")
        self.assertTrue(r["github"]["raison"])

    def test_serveur_injoignable_est_indisponible_et_pas_deconseille(self):
        r = recommander("apk", TOUS, m(serveur_joignable=False, charge_serveur=0.99))
        self.assertEqual(r["serveur"]["niveau"], "indisponible")

    def test_le_plus_rapide_est_recommande_si_ecart_net(self):
        r = recommander("apk", TOUS, m(duree_min={"poste": 10, "github": 20, "serveur": 5}, charge_serveur=0.2, charge_poste=0.2,
                                       quota_github_restant=0.9))
        self.assertEqual(niveaux(r), {"poste": "possible", "github": "possible", "serveur": "recommande"})
        self.assertEqual(r["serveur"]["fondee_sur"], "mesures")

    def test_ecart_faible_donne_possible_pour_tous(self):
        r = recommander("apk", TOUS, m(duree_min={"poste": 10, "github": 12, "serveur": 10.5}, charge_serveur=0.2, charge_poste=0.2,
                                       quota_github_restant=0.9))
        self.assertEqual(set(niveaux(r).values()), {"possible"})

    def test_poste_surcharge_est_deconseille_et_serveur_recommande(self):
        r = recommander("apk", {"poste": True, "github": False, "serveur": True}, m(charge_poste=0.9, charge_serveur=0.2))
        self.assertEqual(niveaux(r), {"poste": "deconseille", "github": "indisponible", "serveur": "recommande"})
        self.assertEqual(r["serveur"]["fondee_sur"], "regles")

    def test_quota_github_bas_deconseille_github(self):
        r = recommander("apk", TOUS, m(quota_github_restant=0.1, charge_poste=0.3, charge_serveur=0.5))
        self.assertEqual(r["github"]["niveau"], "deconseille")

    def test_sans_mesure_repli_sur_les_regles_et_le_dit(self):
        r = recommander("apk", TOUS, m(charge_poste=0.2, charge_serveur=0.6))
        self.assertEqual(r["poste"]["niveau"], "recommande")
        self.assertTrue(all(v["fondee_sur"] == "regles" for v in r.values()))

    def test_au_plus_un_recommande(self):
        cas = [m(duree_min={"poste": 5, "github": 5, "serveur": 5}, charge_poste=0.1, charge_serveur=0.1, quota_github_restant=1),
               m(charge_poste=0.2, charge_serveur=0.2), m(), m(duree_min={"poste": 5, "serveur": 20}, charge_poste=0.1, charge_serveur=0.1)]
        for mes in cas:
            r = recommander("apk", TOUS, mes)
            self.assertLessEqual(sum(v["niveau"] == "recommande" for v in r.values()), 1)

    def test_raison_ne_contient_aucun_secret_ni_chemin(self):
        cas = [m(), m(serveur_joignable=False), m(charge_poste=0.95, quota_github_restant=0.05, charge_serveur=0.2),
               m(duree_min={"poste": 10, "serveur": 2}, charge_serveur=0.1, charge_poste=0.1)]
        for mes in cas:
            for permis in (TOUS, {"poste": False, "github": False, "serveur": False}):
                for v in recommander("apk", permis, mes).values():
                    self.assertTrue(v["raison"])
                    self.assertNotRegex(v["raison"], r"[\\/]|\.[a-z]{2,}\b|\d+\.\d+\.\d+\.\d+|@")

    def test_charge_serveur_inconnue_ne_donne_jamais_recommande(self):
        r = recommander("apk", {"poste": False, "github": False, "serveur": True}, m(charge_serveur=None))
        self.assertEqual(r["serveur"]["niveau"], "possible")
        r = recommander("apk", TOUS, m(duree_min={"poste": 20, "github": 20, "serveur": 2}, charge_poste=0.2, quota_github_restant=0.9))
        self.assertNotEqual(r["serveur"]["niveau"], "recommande")

    def test_regles_charge_connue_haute_et_autres_inconnues_donne_possible(self):
        r = recommander("apk", TOUS, m(charge_serveur=0.8))
        self.assertEqual(r["serveur"]["niveau"], "possible")
        self.assertIn("inconnues", r["serveur"]["raison"])
        r = recommander("apk", TOUS, m(charge_serveur=0.3))
        self.assertEqual(r["serveur"]["niveau"], "recommande")

    def test_regles_tout_connu_exige_l_ecart(self):
        r = recommander("apk", {"poste": True, "github": False, "serveur": True}, m(charge_poste=0.3, charge_serveur=0.35))
        self.assertEqual(set(niveaux(r).values()) - {"indisponible"}, {"possible"})

    def test_mesures_est_fige(self):
        with self.assertRaises(Exception):
            m().charge_poste = 1.0


if __name__ == "__main__":
    unittest.main()
