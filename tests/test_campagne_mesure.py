"""Le lanceur mesure chaque campagne, au poste (`campagne.executer`) et sur GitHub (`deporter._noter_le_run`), sans
jamais changer le code de sortie ni bloquer la sortie de la commande. Verrou et attentes en dossier temporaire, horloge
et `noter` injectés ; un seul sous-processus (le test de fumée de `_lancer`)."""
import ast
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
import campagne  # noqa: E402
import deporter  # noqa: E402
from installation import mise_en_place  # noqa: E402
from moteur import cloud  # noqa: E402
from tests.test_campagne import garder_le_poste  # noqa: E402 — jamais la vraie file ni le vrai verrou du poste


class Enregistreur:
    def __init__(self, lever=False):
        self.appels, self.lever = [], lever

    def __call__(self, *a, **k):
        self.appels.append((a, k))
        if self.lever:
            raise ValueError("journal illisible")


class TestExecuterMesure(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.verrou = Path(self._t.name) / "tests-en-cours.json"
        self.attentes = Path(self._t.name) / "tests-en-attente"
        self.temps = [0.0]
        garder_le_poste(self)

    def dormir(self, s):
        self.temps[0] += s

    def executer(self, lancer, noter, horloge=None, attendre=True, commande=("npx", "vitest", "run")):
        return campagne.executer(list(commande), dossier=self._t.name, attendre=attendre, verrou=self.verrou,
                                 lister=lambda: [], dormir=self.dormir, dire=lambda t, **k: None, lancer=lancer,
                                 attentes=self.attentes, horloge=horloge or (lambda: self.temps[0]), noter=noter)

    def test_executer_mesure_l_execution_sans_l_attente(self):
        noter = Enregistreur()
        horloge = iter([0, 35, 35, 447.6]).__next__      # appel, verrou pris, début, fin
        os.environ[campagne.VARIABLE_TACHE] = "t12"
        self.addCleanup(os.environ.pop, campagne.VARIABLE_TACHE, None)
        code = self.executer(lambda c, d: (6, 48211, "Ran 318 tests in 2.0s\n"), noter, horloge=horloge)
        self.assertEqual(code, 6)
        self.assertEqual(len(noter.appels), 1)
        a, k = noter.appels[0]
        self.assertEqual(a, (str(Path(self._t.name).resolve()),))
        self.assertEqual(k["attente_s"], 35)
        self.assertAlmostEqual(k["duree_s"], 412.6)
        self.assertEqual((k["code"], k["octets"], k["fin"], k["commande"], k["tache"]),
                         (6, 48211, "Ran 318 tests in 2.0s\n", "npx vitest run", "t12"))
        self.assertFalse(self.verrou.exists())

    def test_executer_ancien_lancer_entier(self):
        noter = Enregistreur()
        self.assertEqual(self.executer(lambda c, d: 0, noter), 0)
        k = noter.appels[0][1]
        self.assertEqual((k["octets"], k["fin"], k["code"]), (None, "", 0))

    def test_depassement_ne_change_jamais_le_code(self):
        self.assertEqual(self.executer(lambda c, d: 0, Enregistreur(lever=True)), 0)
        self.assertEqual(self.executer(lambda c, d: (1, 10, "x"), Enregistreur(lever=True)), 1)
        self.assertEqual(self.executer(lambda c, d: 1, Enregistreur()), 1)
        self.assertFalse(self.verrou.exists())

    def test_refus_sans_attendre_ne_note_rien(self):
        self.verrou.write_text(json.dumps({"pid": os.getppid(), "debut": "10:00"}), encoding="utf-8")   # pid vivant
        noter, lancees = Enregistreur(), []
        code = self.executer(lambda c, d: lancees.append(c) or 0, noter, attendre=False)
        self.assertEqual((code, lancees, noter.appels), (3, [], []))
        self.assertEqual(json.loads(self.verrou.read_text(encoding="utf-8"))["pid"], os.getppid())    # intact

    def test_interruption_libere_le_verrou_sans_ligne(self):
        def lancer(c, d):
            raise KeyboardInterrupt
        noter = Enregistreur()
        with self.assertRaises(KeyboardInterrupt):
            self.executer(lancer, noter)
        self.assertFalse(self.verrou.exists())
        self.assertEqual(noter.appels, [])


class TestRelayer(unittest.TestCase):
    def test_relayer_borne_la_memoire_et_tolere_l_octet_invalide(self):
        donnees = b"a\xc3\xa9" * (10 * 1024 * 1024 // 3) + b"\xff\xfeRan 3 tests\n"
        sortie = io.BytesIO()
        octets, fin = campagne.relayer(io.BytesIO(donnees), sortie)
        self.assertEqual(octets, len(donnees))
        self.assertLessEqual(len(fin), 4096)
        self.assertTrue(fin.endswith("Ran 3 tests\n"))
        self.assertEqual(sortie.getvalue(), donnees)

    def test_relayer_continue_de_vider_si_la_sortie_casse(self):
        """L'agent qui lit la sortie a fermé son tuyau : la commande ne doit pas rester bloquée sur un tuyau plein."""
        class Cassee:
            def write(self, b):
                raise BrokenPipeError

            def flush(self):
                raise BrokenPipeError
        octets, fin = campagne.relayer(io.BytesIO(b"x" * 200000 + b"Ran 1 test\n"), Cassee(), morceau=1000)
        self.assertEqual(octets, 200011)
        self.assertTrue(fin.endswith("Ran 1 test\n"))

    def test_lancer_reel_relaie_sortie_et_erreurs(self):
        sortie = io.BytesIO()
        code, octets, fin = campagne._lancer(
            [sys.executable, "-c", "import sys; print('Ran 2 tests'); print('x', file=sys.stderr); sys.exit(4)"],
            None, sortie=sortie)
        self.assertEqual(code, 4)
        self.assertIn("Ran 2 tests", fin)
        self.assertIn(b"x", sortie.getvalue())
        self.assertEqual(octets, len(sortie.getvalue()))


class TestGithubEtDepot(unittest.TestCase):
    def test_github_note_le_run_une_fois(self):
        d = tempfile.gettempdir()
        noter = Enregistreur()
        deporter._noter_le_run({"dossier": d, "catalogue": {"tests": {"commande": "npm test"}}, "commande": []},
                               {"id": 7, "duree_s": 312}, True, noter=noter)
        self.assertEqual(len(noter.appels), 1)
        a, k = noter.appels[0]
        self.assertEqual(a, (d,))
        self.assertEqual((k["lieu"], k["run"], k["code"], k["duree_s"], k["attente_s"], k["commande"]),
                         ("github", 7, 0, 312, 0, "npm test"))
        noter = Enregistreur()
        deporter._noter_le_run({"dossier": d, "catalogue": {"tests": {}}, "commande": ["npx", "vitest", "run"]},
                               {"id": 8}, False, noter=noter)
        k = noter.appels[0][1]
        self.assertEqual((k["commande"], k["code"], k["duree_s"]), ("npx vitest run", 1, 0))
        deporter._noter_le_run({"dossier": d, "catalogue": {}}, {"id": 9}, True, noter=Enregistreur(lever=True))

    def test_campagne_et_deporter_compatibles_3_9(self):
        for f in ("campagne.py", "deporter.py"):
            ast.parse((RACINE / "outils" / f).read_text(encoding="utf-8"), feature_version=(3, 9))

    def test_journal_hors_depot(self):
        self.assertIn(".factory/tests-mesures.jsonl", mise_en_place.BLOC_GITIGNORE)
        self.assertTrue(cloud.ETAT_DU_MOTEUR.match(".factory/tests-mesures.jsonl"))


if __name__ == "__main__":
    unittest.main()
