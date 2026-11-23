"""Le lanceur de la suite (`outils/tests_paralleles.py`) isole chaque morceau (`MYIAFACTORY_ETAT_TESTS`, un dossier à
lui) et garde pour lui-même le vrai verrou du poste. Aucun processus lancé : morceaux et verrou simulés."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import campagne  # noqa: E402
import tests_paralleles  # noqa: E402

REEL = Path("verrou-reel-du-poste.json")


class Poste:
    """`campagne` simulé : note ce que le lanceur voit de son propre environnement quand il prend et rend le verrou."""

    def __init__(self):
        self.vus = []

    def verrou_par_defaut(self):
        return REEL

    def attentes_par_defaut(self):
        return Path("file-reelle")

    def attendre_son_tour(self, racine, attendre=True, verrou=None, attentes=None):
        self.vus.append(("prendre", verrou, attentes, os.environ.get(campagne.VARIABLE_ETAT)))
        return True

    def liberer(self, verrou=None):
        self.vus.append(("liberer", verrou, None, os.environ.get(campagne.VARIABLE_ETAT)))


class TestIsolationDesMorceaux(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        for p in (mock.patch.object(tests_paralleles, "DUREES", Path(self._t.name) / "durees.json"),
                  mock.patch.object(tests_paralleles, "modules", lambda filtres: ["test_a", "test_b", "test_c"]),
                  mock.patch.dict(os.environ)):
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop(campagne.VARIABLE_ETAT, None)       # le lanceur tel que lancé depuis Git bash
        self.envs, self.echouer = {}, {"test_b"}

    def lancer(self, morceau, env):
        self.assertNotIn(campagne.VARIABLE_ETAT, os.environ)         # jamais dans l'environnement du lanceur
        dossier = env[campagne.VARIABLE_ETAT]
        self.assertTrue(Path(dossier).is_dir())
        # le nom que `campagne` honore : `<temp>/myiafactory-etat-tests-…/<n>`
        self.assertTrue(Path(dossier).parent.name.startswith(campagne.PREFIXE_ETAT))
        self.assertEqual(Path(dossier).parent.parent, Path(tempfile.gettempdir()).resolve())
        self.envs.setdefault(morceau, []).append(dossier)
        code = 1 if morceau in self.echouer else 0
        self.echouer.discard(morceau)                                  # passe à la relance : « instable »
        return morceau, code, 0.01, 1, "Ran 1 test", 0

    def lancer_main(self, argv=("-j", "2", "--lents", "0")):
        poste, sortie = Poste(), io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = tests_paralleles.main(list(argv), lancer_morceau=self.lancer, poste=poste)
        return code, poste, sortie.getvalue()

    def test_chaque_morceau_a_son_dossier_le_lanceur_le_vrai_verrou(self):
        self.assertEqual(tests_paralleles.VARIABLE_ETAT, campagne.VARIABLE_ETAT)
        code, poste, _ = self.lancer_main()
        self.assertEqual(code, 0)
        self.assertEqual(poste.vus, [("prendre", REEL, Path("file-reelle"), None), ("liberer", REEL, None, None)])
        dossiers = [d for v in self.envs.values() for d in v]
        self.assertEqual(len(dossiers), 4)                              # 3 morceaux + la relance de test_b
        self.assertEqual(len(set(dossiers)), 4)                         # un dossier neuf pour chacun
        self.assertEqual(len({str(Path(d).parent) for d in dossiers}), 1)
        parent = Path(dossiers[0]).parent
        self.assertFalse(parent.exists())                               # effacé après la suite
        self.assertNotEqual(parent, campagne.DOSSIER_ETAT)
        self.assertNotIn(campagne.VARIABLE_ETAT, os.environ)

    def test_refus_sans_attendre_ne_lance_rien(self):
        poste = Poste()
        poste.attendre_son_tour = lambda *a, **k: False
        with contextlib.redirect_stdout(io.StringIO()):
            code = tests_paralleles.main(["--sans-attendre"], lancer_morceau=self.lancer, poste=poste)
        self.assertEqual((code, self.envs), (3, {}))

    def test_lance_depuis_un_test_deja_isole(self):
        os.environ[campagne.VARIABLE_ETAT] = str(Path(self._t.name) / "parent")
        with mock.patch.object(self, "lancer", lambda m, env: (m, 0, 0.01, 1, "", 0)):
            code, poste, sortie = self.lancer_main()
        self.assertEqual(code, 0)
        self.assertIn("isolé", sortie)
        self.assertEqual(poste.vus[0][3], str(Path(self._t.name) / "parent"))    # hérité, jamais posé par lui


if __name__ == "__main__":
    unittest.main()
