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
        self.assertEqual(mesures[1]["pics_mo"], [])

    def test_memoire_utilisee(self):
        texte = "MemTotal:       65731000 kB\nMemFree:  100 kB\nMemAvailable:   58388000 kB\n"
        self.assertEqual(mp.memoire_utilisee_mo(texte), (65731000 - 58388000) // 1024)
        self.assertIsNone(mp.memoire_utilisee_mo("rien"))

    def test_sonde_pic_au_dessus_du_depart(self):
        lectures = iter([1000, 1500, 4000, 2500, None, 1200])
        s = mp.Sonde(lambda: next(lectures, 1200), pas=0)
        s.depart()
        for _ in range(5):
            s.relever()
        self.assertEqual(s.pic_au_dessus(), 3000)        # 4000 - 1000 ; une lecture ratée (None) est ignorée

    def test_mesurer_avec_sonde(self):
        sondes = []

        class FausseSonde:
            def __init__(self):
                self.arretee = False
                sondes.append(self)

            def demarrer(self):
                pass

            def arreter(self):
                self.arretee = True
                return 2048

        mesures = mp.mesurer([1, 2], lambda: 0, sonde=FausseSonde)
        self.assertEqual(mesures[2]["pics_mo"], [2048])  # mémoire cumulée de tout le palier : une valeur
        self.assertEqual(len(sondes), 2)
        self.assertTrue(all(s.arretee for s in sondes))

    def test_emulation_en_fond(self):
        appels = []

        def lanceur(args):
            appels.append(args)
            if args[:2] == ["serveur-tache", "lancer"]:
                return 0, '{\n  "id": "t20261124-010203-abcd",\n  "etat": "en_cours"\n}'
            return 0, "{}"

        ident = mp.demarrer_emulation("x.apk", "C:/p", lanceur=lanceur)
        self.assertEqual(ident, "t20261124-010203-abcd")
        self.assertEqual(appels[0], ["serveur-tache", "lancer", "--apk", "x.apk", "--mode", "pilote", "--projet", "C:/p"])
        self.assertEqual(appels[1], ["serveur-outil", ident, "demarrer", "--projet", "C:/p"])
        mp.arreter_emulation(ident, lanceur=lanceur)
        self.assertEqual(appels[2], ["serveur-tache", "arreter", ident])

    def test_emulation_refusee(self):
        with self.assertRaises(RuntimeError):
            mp.demarrer_emulation("x.apk", "C:/p", lanceur=lambda a: (2, "refus"))


if __name__ == "__main__":
    unittest.main()
