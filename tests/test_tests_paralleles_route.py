"""La suite de MyIAFactory par la route serveur (`outils/tests_paralleles.py`) : aiguillage avant le verrou du poste,
`--touches` résolu au poste, `--serveur` / `--local`, et dans le conteneur ni route ni verrou. Rien n'est lancé :
`tests_serveur.executer`, l'accord (`_refus_route`), les morceaux et le poste sont simulés."""
import contextlib
import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import tests_paralleles  # noqa: E402
import tests_serveur  # noqa: E402

MODULES = ["test_a", "test_b", "test_c"]


class Poste:
    """`campagne` simulé : note le verrou pris et rendu."""

    def __init__(self):
        self.vus = []

    def verrou_par_defaut(self):
        return Path("verrou-simule.json")

    def attentes_par_defaut(self):
        return Path("file-simulee")

    def attendre_son_tour(self, racine, attendre=True, verrou=None, attentes=None):
        self.vus.append(("prendre", attendre))
        return True

    def liberer(self, verrou=None):
        self.vus.append(("liberer",))


class TestRoute(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.refus, self.envoyes, self.lances = None, [], []
        self.code_serveur, self.repli = 0, False
        for p in (mock.patch.object(tests_paralleles, "DUREES", Path(self._t.name) / "durees.json"),
                  mock.patch.object(tests_paralleles, "modules", lambda filtres: [
                      m for m in MODULES if not filtres or any(f in m for f in filtres)]),
                  mock.patch.object(tests_paralleles, "_refus_route", lambda racine: self.refus),
                  mock.patch.object(tests_serveur, "executer", self.executer),
                  mock.patch.dict(os.environ)):
            p.start()
            self.addCleanup(p.stop)
        for v in (tests_paralleles.VARIABLE_ETAT, tests_paralleles.CONTENEUR):
            os.environ.pop(v, None)

    def executer(self, commande, dossier=None, attendre=True, forcer=False, executer_poste=None, **k):
        self.envoyes.append({"commande": list(commande), "dossier": dossier, "attendre": attendre, "forcer": forcer})
        if self.repli:
            return executer_poste(commande, dossier=dossier, attendre=attendre)
        return self.code_serveur

    def lancer(self, morceau, env):
        self.lances.append((morceau, env.get(tests_paralleles.VARIABLE_ETAT)))
        return morceau, 0, 0.01, 1, "Ran 1 test", 0

    def main(self, *argv):
        poste, sortie = Poste(), io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = tests_paralleles.main(["--lents", "0", *argv], lancer_morceau=self.lancer, poste=poste)
        return code, poste, sortie.getvalue()

    def test_dans_le_conteneur_ni_route_ni_verrou(self):
        os.environ[tests_paralleles.CONTENEUR] = "1"
        with mock.patch.object(tests_paralleles, "_refus_route", mock.Mock(side_effect=AssertionError("accord lu"))):
            code, poste, _ = self.main("--serveur")
        self.assertEqual(code, 0)
        self.assertEqual((self.envoyes, poste.vus), ([], []))
        self.assertEqual(sorted(m for m, _ in self.lances), MODULES)          # `_campagne` a tourné
        for _, dossier in self.lances:                                        # morceaux toujours isolés
            self.assertTrue(Path(dossier).parent.name.startswith("myiafactory-etat-tests-"))
            self.assertEqual(Path(dossier).parent.parent, Path(tempfile.gettempdir()).resolve())

    def test_touches_resolus_au_poste(self):
        faux = types.SimpleNamespace(
            fichiers_modifies=lambda racine, reference: ["outils/x.py"],
            Graphe=lambda racine: types.SimpleNamespace(touches=lambda modifies: ({"test_a", "test_c"}, "2 touchés")))
        with mock.patch.dict(sys.modules, {"impact_tests": faux}):
            code, poste, sortie = self.main("--touches")
        self.assertEqual(code, 0)
        self.assertIn("Tests touchés : 2 module(s)", sortie)
        (envoi,) = self.envoyes
        self.assertEqual(envoi["commande"], ["python3", "outils/tests_paralleles.py", "-j",
                                             str(tests_serveur.LIMITES["cpus"]), "--lents", "0", "test_a", "test_c"])
        self.assertNotIn("--touches", envoi["commande"])
        self.assertEqual((envoi["dossier"], envoi["attendre"], envoi["forcer"]), (tests_paralleles.RACINE, True, False))
        self.assertEqual((poste.vus, self.lances), ([], []))                   # rien au poste

        faux.Graphe = lambda racine: types.SimpleNamespace(touches=lambda modifies: (set(), "rien"))
        with mock.patch.dict(sys.modules, {"impact_tests": faux}):
            code, _, sortie = self.main("--touches")
        self.assertEqual((code, len(self.envoyes)), (0, 1))                    # « Rien à tester. » : aucune route
        self.assertIn("Rien à tester.", sortie)

    def test_filtres_et_code_du_serveur_relayes(self):
        self.code_serveur = 1
        code, poste, _ = self.main("b", "--sans-attendre")
        self.assertEqual(code, 1)
        self.assertEqual(self.envoyes[0]["commande"][-1:], ["b"])
        self.assertFalse(self.envoyes[0]["attendre"])
        self.assertEqual(poste.vus, [])

    def test_local_et_sans_accord(self):
        code, poste, _ = self.main("--local")
        self.assertEqual(code, 0)
        self.assertEqual(self.envoyes, [])
        self.assertEqual(poste.vus, [("prendre", True), ("liberer",)])
        self.assertEqual(len(self.lances), 3)

        self.refus, self.lances = "pas d'accord", []
        code, poste, _ = self.main()
        self.assertEqual((code, self.envoyes, len(self.lances)), (0, [], 3))
        self.assertEqual(poste.vus, [("prendre", True), ("liberer",)])

    def test_repli_du_serveur_le_chemin_local(self):
        self.repli = True
        code, poste, _ = self.main()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.envoyes), 1)
        self.assertEqual(poste.vus, [("prendre", True), ("liberer",)])
        self.assertEqual(sorted(m for m, _ in self.lances), MODULES)

    def test_serveur_force(self):
        self.refus = "pas d'accord"          # `--serveur` ne lit pas l'accord ici : `executer` le revérifie
        code, poste, _ = self.main("--serveur")
        self.assertEqual(code, 0)
        self.assertTrue(self.envoyes[0]["forcer"])
        self.assertEqual(self.envoyes[0]["commande"][-2:], ["--lents", "0"])   # pas de filtre : toute la suite
        self.assertEqual(poste.vus, [])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.main("--serveur", "--local")


if __name__ == "__main__":
    unittest.main()
