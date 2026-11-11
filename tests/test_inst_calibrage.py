"""Le calibrage de la machine : combien d'agents locaux en parallèle."""
import unittest

from installation import calibrage


def historique(repos, par_agent, n_actifs=30, n_repos=5):
    h = [{"t": i, "charge": repos, "agents_locaux": 0} for i in range(n_repos)]
    h += [{"t": 100 + i, "charge": repos + 2 * par_agent, "agents_locaux": 2} for i in range(n_actifs)]
    return h


class TestCalibrage(unittest.TestCase):
    def test_tableau_sans_historique(self):
        for coeurs, go, attendu in ((4, 8, 1), (16, 32, 4), (8, 16, 2), (64, 128, 4), (2, 2, 1)):
            with self.subTest(coeurs=coeurs, go=go):
                r = calibrage.calibrer({"coeurs": coeurs, "memoire_totale_go": go, "disponible": True}, [])
                self.assertEqual(r["agents_locaux_max"], attendu)
                self.assertEqual(r["source"], "machine")
                self.assertTrue(30 <= r["charge_max"] <= 95)

    def test_indisponible(self):
        r = calibrage.calibrer({"coeurs": 16, "memoire_totale_go": 0.0, "disponible": False}, [])
        self.assertEqual(r["agents_locaux_max"], 1)
        self.assertEqual(r["source"], "indisponible")
        self.assertEqual(r["explication"], "Mesure indisponible sur cette machine : 1 agent local, par prudence.")

    def test_historique(self):
        mach = {"coeurs": 8, "memoire_totale_go": 16, "disponible": True}
        r = calibrage.calibrer(mach, historique(20, 15))
        self.assertEqual(r["source"], "historique")
        self.assertEqual(r["agents_locaux_max"], 4)

    def test_historique_borne_a_6_et_1(self):
        mach = {"coeurs": 8, "memoire_totale_go": 16, "disponible": True}
        self.assertEqual(calibrage.calibrer(mach, historique(10, 1))["agents_locaux_max"], 6)
        self.assertEqual(calibrage.calibrer(mach, historique(20, 80))["agents_locaux_max"], 1)

    def test_historique_insuffisant_retombe_sur_la_machine(self):
        mach = {"coeurs": 16, "memoire_totale_go": 32, "disponible": True}
        r = calibrage.calibrer(mach, historique(20, 15, n_actifs=5))
        self.assertEqual(r["source"], "machine")


if __name__ == "__main__":
    unittest.main()
