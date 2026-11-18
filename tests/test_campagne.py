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
        self.attentes = Path(self._t.name) / "tests-en-attente"
        self.dits, self.sommes = [], []

    def tour(self, lister=lambda: [], attendre=True, dormir=None):
        return campagne.attendre_son_tour("skill", attendre=attendre, verrou=self.verrou, lister=lister,
                                          dormir=dormir or self.sommes.append,
                                          dire=lambda texte, **k: self.dits.append(texte), attentes=self.attentes)

    def test_une_campagne_qui_attend_est_notee_pour_le_bureau_puis_oubliee(self):
        """Essai réel (2026-11-18) : Hugo attendait le verrou de tests, sa fiche n'en disait rien. Pendant l'attente,
        la campagne est notée avec la clé de l'agent (`MYIAFACTORY_TACHE`) ; une fois son tour venu, elle est oubliée."""
        vu = []
        listes = [[(4242, "node node_modules/vitest/vitest.mjs run")], []]

        def dormir(_):
            vu.append(campagne.en_attente(self.attentes))
        os.environ[campagne.VARIABLE_TACHE] = "t68"
        self.addCleanup(os.environ.pop, campagne.VARIABLE_TACHE, None)
        self.assertTrue(self.tour(lister=lambda: listes.pop(0), dormir=dormir))
        self.assertEqual(list(vu[0]), ["t68"])
        self.assertIn("sans le lanceur", vu[0]["t68"]["motif"])
        self.assertTrue(vu[0]["t68"]["depuis"])
        self.assertEqual(campagne.en_attente(self.attentes), {})        # son tour venu : plus en attente
        self.assertEqual(list(self.attentes.glob("*.json")), [])

    def test_en_attente_ignore_un_processus_mort_ou_sans_agent(self):
        self.attentes.mkdir()
        (self.attentes / "1.json").write_text(json.dumps({"pid": 999999999, "tache": "t1"}), encoding="utf-8")
        (self.attentes / "2.json").write_text(json.dumps({"pid": os.getpid(), "tache": None}), encoding="utf-8")
        (self.attentes / "3.json").write_text("{pas du json", encoding="utf-8")
        self.assertEqual(campagne.en_attente(self.attentes), {})
        self.assertEqual(campagne.en_attente(self.attentes / "absent"), {})

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


    # --- Les tests d'un projet, lancés par un agent (`lancer.py tests -- <commande>`).
    def test_les_suites_node_d_un_agent_comptent_comme_suites_directes(self):
        """Essai réel (2026-11-17) : deux agents lançaient chacun `vitest run` en même temps, chacun beaucoup plus lent."""
        lister = lambda: [(5, "node C:/p/frontend/node_modules/vitest/vitest.mjs run"),  # noqa: E731
                          (6, "node node_modules/jest/bin/jest.js"), (7, "npx playwright test"),
                          (8, "node C:/p/frontend/node_modules/vite/bin/vite.js"),
                          (9, "node C:/npm/node_modules/@playwright/mcp/cli.js")]
        self.assertEqual([p for p, _ in campagne.suites_sans_verrou(lister, moi=set())], [5, 6, 7])

    def test_executer_prend_le_verrou_lance_la_commande_et_le_libere(self):
        vu = {}

        def lancer(commande, dossier):
            vu["verrou"] = json.loads(self.verrou.read_text(encoding="utf-8"))["pid"]
            vu["commande"], vu["dossier"] = commande, dossier
            return 7
        code = campagne.executer(["npx", "vitest", "run", "src/a.test.tsx"], dossier="C:/p/frontend", verrou=self.verrou,
                                 lister=lambda: [], dormir=self.sommes.append, dire=lambda t, **k: self.dits.append(t),
                                 lancer=lancer, attentes=self.attentes)
        self.assertEqual(code, 7)                                  # le code de la commande
        self.assertEqual(vu, {"verrou": os.getpid(), "commande": ["npx", "vitest", "run", "src/a.test.tsx"],
                              "dossier": "C:/p/frontend"})
        self.assertFalse(self.verrou.exists())                    # libéré après

    def test_executer_attend_la_campagne_d_un_autre_agent(self):
        listes = [[(5, "node node_modules/vitest/vitest.mjs run")], []]
        lancees = []
        code = campagne.executer(["npm", "test"], verrou=self.verrou, lister=lambda: listes.pop(0),
                                 dormir=self.sommes.append, dire=lambda t, **k: self.dits.append(t),
                                 lancer=lambda c, d: lancees.append(c) or 0, attentes=self.attentes)
        self.assertEqual((code, lancees, len(self.sommes)), (0, [["npm", "test"]], 1))
        self.assertIn("Une seule campagne", self.dits[0])

    def test_executer_libere_meme_si_la_commande_echoue(self):
        def lancer(c, d):
            raise OSError("introuvable")
        with self.assertRaises(OSError):
            campagne.executer(["x"], verrou=self.verrou, lister=lambda: [], dormir=self.sommes.append,
                              dire=lambda t, **k: None, lancer=lancer)
        self.assertFalse(self.verrou.exists())

    def test_la_ligne_de_commande_exige_une_commande_apres_les_tirets(self):
        self.assertEqual(campagne.main([], executer=lambda *a, **k: 0), 2)
        vu = []
        self.assertEqual(campagne.main(["--dossier", "front", "--", "npx", "vitest", "run"],
                                       executer=lambda c, dossier=None, attendre=True: vu.append((c, dossier)) or 4), 4)
        self.assertEqual(vu, [(["npx", "vitest", "run"], "front")])

if __name__ == "__main__":
    unittest.main()
