"""Une seule campagne de tests à la fois sur le poste (`outils/campagne.py`). Verrou dans un dossier temporaire ; la
liste des processus du poste est simulée."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import campagne  # noqa: E402


class TestCampagne(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.verrou = Path(self._t.name) / "tests-en-cours.json"
        self.dits, self.sommes = [], []

    def tour(self, lister=lambda: [], attendre=True, dormir=None):
        return campagne.attendre_son_tour("skill", attendre=attendre, verrou=self.verrou, lister=lister,
                                          dormir=dormir or self.sommes.append,
                                          dire=lambda texte, **k: self.dits.append(texte))

    def test_poste_libre_le_verrou_est_pris_puis_libere(self):
        self.assertTrue(self.tour())
        self.assertEqual(json.loads(self.verrou.read_text(encoding="utf-8"))["pid"], os.getpid())
        campagne.liberer(self.verrou)
        self.assertFalse(self.verrou.exists())

    def test_une_autre_campagne_vivante_fait_refuser_sans_attendre(self):
        self.verrou.write_text(json.dumps({"pid": os.getppid(), "debut": "10:00"}), encoding="utf-8")
        self.assertFalse(self.tour(attendre=False))
        self.assertIn("une campagne tourne déjà", self.dits[0])
        self.assertEqual(json.loads(self.verrou.read_text(encoding="utf-8"))["pid"], os.getppid())   # intact

    def test_le_verrou_d_une_campagne_morte_est_repris(self):
        self.verrou.write_text(json.dumps({"pid": 999999999, "debut": "hier"}), encoding="utf-8")
        self.assertTrue(self.tour())
        self.assertEqual(json.loads(self.verrou.read_text(encoding="utf-8"))["pid"], os.getpid())

    def test_on_attend_la_fin_d_une_suite_lancee_sans_le_lanceur(self):
        listes = [[(4242, "python -m unittest discover -s tests")], []]
        self.assertTrue(self.tour(lister=lambda: listes.pop(0)))
        self.assertEqual(len(self.sommes), 1)                     # une attente, puis le poste est libre
        self.assertIn("sans le lanceur", self.dits[0])
        self.assertTrue(self.verrou.exists())

    def test_les_autres_lanceurs_et_nous_ne_comptent_pas_comme_suites_directes(self):
        lister = lambda: [(1, "py outils/tests_paralleles.py"), (2, "python -m unittest tests.test_x"),  # noqa: E731
                          (3, "python serveur.py")]
        self.assertEqual([p for p, _ in campagne.suites_sans_verrou(lister, moi={2})], [])


if __name__ == "__main__":
    unittest.main()
