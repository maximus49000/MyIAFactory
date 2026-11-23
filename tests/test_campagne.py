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


def garder_le_poste(test, autres=()):
    """Aucun test ne touche la vraie file ni le vrai verrou du poste (un test qui oubliait `attentes=` attendait derrière
    les vraies campagnes, sans fin) : les fonctions de `campagne` qui les lisent ou les écrivent refusent ces chemins.
    Depuis le 2026-11-23, le lanceur isole aussi chaque processus de test (`campagne.VARIABLE_ETAT`) : la garde reste,
    pour un test lancé hors du lanceur et contre une isolation cassée. Un chemin omis est résolu comme par `campagne`."""
    reels = {Path(p).resolve() for p in (campagne.ATTENTES, campagne.VERROU, *autres)}
    for nom, cle in (("_file", "attentes"), ("_noter_l_attente", "attentes"), ("_oublier_l_attente", "attentes"),
                     ("prendre", "verrou"), ("liberer", "verrou")):
        vrai = getattr(campagne, nom)

        def garde(*a, _vrai=vrai, _nom=nom, _cle=cle, **k):
            chemin = a[0] if a else k.get(_cle)
            if chemin is None:
                chemin = campagne.verrou_par_defaut() if _cle == "verrou" else campagne.attentes_par_defaut()
            if Path(chemin).resolve() in reels:
                raise AssertionError(f"campagne.{_nom} touche le vrai {chemin}")
            return _vrai(*a, **k)
        setattr(campagne, nom, garde)
        test.addCleanup(setattr, campagne, nom, vrai)


class TestCampagne(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.verrou = Path(self._t.name) / "tests-en-cours.json"
        self.attentes = Path(self._t.name) / "tests-en-attente"
        self.dits, self.sommes = [], []
        garder_le_poste(self)

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

    def test_la_file_donne_le_rang_de_chaque_agent_dans_l_ordre_d_arrivee(self):
        self.attentes.mkdir()
        vivant = lambda pid: pid in (11, 12, 13)      # noqa: E731
        for pid, arrivee, tache in ((12, 200.0, "t2"), (11, 100.0, "t1"), (13, 300.0, None), (14, 50.0, "mort")):
            (self.attentes / f"{pid}.json").write_text(json.dumps(
                {"pid": pid, "arrivee": arrivee, "depuis": "10:00", "motif": "m", "tache": tache}), encoding="utf-8")
        f = campagne.en_attente(self.attentes, vivant=vivant)
        self.assertEqual({k: (v["rang"], v["total"]) for k, v in f.items()}, {"t1": (1, 3), "t2": (2, 3)})

    def test_premier_arrive_premier_servi_meme_poste_libre(self):
        """Le bureau affiche la position dans la file : une campagne arrivée après une autre qui attend ne lui passe
        pas devant, même si le verrou est libre à cet instant."""
        self.attentes.mkdir()
        avant = self.attentes / "autre.json"
        avant.write_text(json.dumps({"pid": os.getppid(), "arrivee": 1.0, "tache": "t1"}), encoding="utf-8")
        vu = []

        def dormir(_):
            vu.append(campagne.en_attente(self.attentes))
            avant.unlink()        # l'autre a eu son tour : elle quitte la file
        os.environ[campagne.VARIABLE_TACHE] = "t2"
        self.addCleanup(os.environ.pop, campagne.VARIABLE_TACHE, None)
        self.assertTrue(self.tour(dormir=dormir))
        self.assertIn("1 campagne attend avant elle", self.dits[0])
        self.assertEqual({k: (v["rang"], v["total"]) for k, v in vu[0].items()}, {"t1": (1, 2), "t2": (2, 2)})
        self.assertEqual(json.loads(self.verrou.read_text(encoding="utf-8"))["pid"], os.getpid())

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
                              dire=lambda t, **k: None, lancer=lancer, attentes=self.attentes)
        self.assertFalse(self.verrou.exists())

    def test_la_ligne_de_commande_exige_une_commande_apres_les_tirets(self):
        self.assertEqual(campagne.main([], executer=lambda *a, **k: 0), 2)
        vu = []
        self.assertEqual(campagne.main(["--dossier", "front", "--", "npx", "vitest", "run"],
                                       executer=lambda c, dossier=None, attendre=True: vu.append((c, dossier)) or 4), 4)
        self.assertEqual(vu, [(["npx", "vitest", "run"], "front")])

    def test_garde_la_vraie_file_et_le_vrai_verrou(self):
        """Hors de l'isolation du lanceur (variable ôtée le temps du test), la garde refuse les vrais chemins."""
        ancien = os.environ.pop(campagne.VARIABLE_ETAT, None)
        if ancien is not None:
            self.addCleanup(os.environ.__setitem__, campagne.VARIABLE_ETAT, ancien)
        with self.assertRaises(AssertionError):
            campagne.executer(["x"], verrou=self.verrou, lister=lambda: [], dormir=self.sommes.append,
                              dire=lambda t, **k: None, lancer=lambda c, d: 0)          # sans attentes= : la vraie file
        with self.assertRaises(AssertionError):
            campagne.attendre_son_tour("skill", lister=lambda: [], dormir=self.sommes.append, attentes=self.attentes)


if __name__ == "__main__":
    unittest.main()
