import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))

import serveur_modele  # noqa: E402
import tests_mesure_places as mp  # noqa: E402
import tests_serveur  # noqa: E402


def _srv(**plus):
    return serveur_modele.valider({"hote": "h.example", "utilisateur": "u", "cle": "k", **plus})


class TestPlaces(unittest.TestCase):
    def test_places_bornees(self):
        self.assertEqual(tests_serveur.places_de(_srv(places_tests=0)), tests_serveur.PLACES_DEFAUT)
        self.assertEqual(tests_serveur.places_de(_srv(places_tests=5)), tests_serveur.PLACES_DEFAUT)
        self.assertEqual(tests_serveur.places_de(_srv(places_tests=True)), tests_serveur.PLACES_DEFAUT)
        self.assertEqual(tests_serveur.places_de(_srv(places_tests=2)), 2)
        self.assertEqual(tests_serveur.places_de(_srv()), tests_serveur.PLACES_DEFAUT)

    def test_non_regle_absent_du_fichier(self):
        self.assertNotIn("places_tests", serveur_modele._en_dict(_srv()))
        self.assertEqual(serveur_modele._en_dict(_srv(places_tests=4))["places_tests"], 4)

    def test_recommander(self):
        m = {1: {"durees": [190], "pics_mo": [3000]}, 2: {"durees": [230, 230], "pics_mo": [3000, 3000]},
             3: {"durees": [320, 320, 320], "pics_mo": [3000] * 3}}
        self.assertEqual(mp.recommander(m, 62 * 1024), 2)

    def test_recommander_memoire(self):
        m = {1: {"durees": [190], "pics_mo": [3000]}, 2: {"durees": [200, 200], "pics_mo": [20000, 20000]}}
        self.assertEqual(mp.recommander(m, 62 * 1024), 1)

    def test_protocole_sans_serveur(self):
        appels = []
        mesures = mp.mesurer([1, 2, 3], lambda: appels.append(1) or 0)
        self.assertEqual(len(appels), 6)
        self.assertEqual([len(mesures[k]["durees"]) for k in (1, 2, 3)], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
