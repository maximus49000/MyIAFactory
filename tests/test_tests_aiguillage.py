"""L'accord (R10) et l'aiguillage de `lancer.py tests` (conception § 5.1, § 5.7) : `deport_types.refus_route`,
`deporter.lancer_tests`, la porte `serveur-tests`. Bureau et réglages en dossier temporaire ; route, poste et deporter
remplacés par des témoins : aucun sous-processus, aucune connexion."""
import ast
import contextlib
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
import deporter  # noqa: E402
from bureau import deport_types  # noqa: E402
from tests.test_campagne import garder_le_poste  # noqa: E402

# un catalogue dont les tests n'offrent pas le serveur (comme ANDROID avant l'amendement)
SANS_SERVEUR = {"tests": deport_types._entree("Tests", lieux=("poste", "github"))}


class Base(unittest.TestCase):
    def setUp(self):
        garder_le_poste(self)      # jamais la vraie file ni le vrai verrou : tout est remplacé par des témoins
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name).resolve()
        self.bureau = self.tmp / "bureau.json"
        self.p = self.tmp / "p"
        (self.p / ".factory").mkdir(parents=True)
        (self.p / "src").mkdir()
        self.reglages = self.p / ".factory" / "reglages.json"
        self.ecrire_reglages(None)
        self.vus = []

    def ecrire_reglages(self, lieux, fichier=None):
        donnees = {"nom": "p"} if lieux is None else {"deport": {"lieux": lieux}}
        (fichier or self.reglages).write_text(json.dumps(donnees), encoding="utf-8")

    def ecrire_bureau(self, projets=(), lieux=None):
        donnees = {"projets": [{"chemin": str(c)} for c in projets]}
        if lieux is not None:
            donnees["deport"] = {"lieux": lieux}
        self.bureau.write_text(json.dumps(donnees), encoding="utf-8")

    def refus(self, dossier, action="tests"):
        return deport_types.refus_route(str(dossier), action, bureau=str(self.bureau))

    # témoins de `lancer_tests`
    def route(self, commande, dossier, attendre, forcer):
        self.vus.append(("route", list(commande), dossier, attendre, forcer))
        return 7

    def campagne(self, argv):
        self.vus.append(("poste", list(argv)))
        return 0

    def deporter(self, argv):
        self.vus.append(("deporter", list(argv)))
        return 0

    def lancer(self, argv, route=None):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(sortie):
            code = deporter.lancer_tests(argv, bureau=self.bureau, deporter_main=self.deporter,
                                         campagne_main=self.campagne, route=route or self.route)
        self.sortie = sortie.getvalue()
        return code


class TestAccord(Base):
    def test_accord_projet_enregistre_regle_serveur(self):
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_bureau([self.reglages])
        self.assertIsNone(self.refus(self.p / "src"))
        self.assertIsNone(self.refus(self.p))
        self.assertTrue(deport_types.routee_au_serveur("tests", deport_types.GENERIQUE))
        self.assertFalse(deport_types.routee_au_serveur("apk", deport_types.GENERIQUE))
        self.assertFalse(deport_types.routee_au_serveur("tests", SANS_SERVEUR))      # pas de serveur au catalogue

    def test_accord_copie_de_travail_sous_projet_enregistre(self):
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_bureau([self.reglages])
        copie = self.p / ".claude" / "worktrees" / "x"
        copie.mkdir(parents=True)
        self.assertIsNone(self.refus(copie))

    def test_accord_par_defaut_du_bureau(self):
        self.ecrire_bureau([self.reglages], lieux={"tests": "serveur"})
        self.assertIsNone(self.refus(self.p / "src"))
        self.ecrire_reglages({"apk": "poste"})
        self.assertIsNone(self.refus(self.p / "src"))
        self.ecrire_reglages({"tests": "poste"})
        self.assertIn("poste", self.refus(self.p / "src"))
        self.ecrire_reglages({"tests": "github"})
        self.assertIsNotNone(self.refus(self.p / "src"))

    def test_non_regle_refuse(self):
        self.ecrire_bureau([self.reglages])
        self.assertIsNotNone(self.refus(self.p))
        self.ecrire_bureau([self.reglages], lieux={"tests": "poste"})
        self.assertIsNotNone(self.refus(self.p))
        self.bureau.unlink()
        self.assertIsNotNone(self.refus(self.p))                  # bureau absent

    def test_reglages_enregistres_illisibles_ne_prennent_pas_le_defaut(self):
        self.ecrire_bureau([self.reglages], lieux={"tests": "serveur"})
        self.reglages.write_text("{abîmé", encoding="utf-8")
        self.assertIsNotNone(self.refus(self.p))
        self.reglages.unlink()
        self.assertIsNotNone(self.refus(self.p))

    def test_action_non_routee_refusee(self):
        self.ecrire_reglages({"apk": "serveur", "recette-emulateur": "serveur"})
        self.ecrire_bureau([self.reglages])
        self.assertIsNotNone(self.refus(self.p, "apk"))
        self.assertIsNotNone(self.refus(self.p, "recette-emulateur"))

    def test_non_enregistre_jamais_route(self):
        autre = self.tmp / "autre"
        (autre / ".factory").mkdir(parents=True)
        self.ecrire_reglages({"tests": "serveur"}, fichier=autre / ".factory" / "reglages.json")
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_bureau([self.reglages], lieux={"tests": "serveur"})
        self.assertIn("enregistré", self.refus(autre))
        self.assertEqual(self.lancer(["--dossier", str(autre), "--", "x"]), 0)
        self.assertEqual(self.vus, [("poste", ["--dossier", str(autre), "--", "x"])])
        self.assertIn("poste", self.sortie)                        # réglé sur serveur mais sans accord : dit
        # `--reglages` d'un dossier non enregistré, ou d'un autre fichier : jamais d'accord
        self.vus.clear()
        self.lancer(["--dossier", str(autre), "--reglages", str(self.reglages), "--", "x"])
        self.assertNotIn("route", [v[0] for v in self.vus])
        self.assertEqual(self.lancer(["--serveur", "--dossier", str(autre), "--", "x"]), 2)
        self.assertNotIn("route", [v[0] for v in self.vus])

    def test_reglages_d_un_agent_ne_valent_pas_accord(self):
        """Le projet enregistré règle `tests` sur poste ; un fichier écrit par un agent (`--reglages`, `.factory`
        imbriqué) qui dit serveur ne change rien."""
        self.ecrire_reglages({"tests": "poste"})
        self.ecrire_bureau([self.reglages], lieux={"tests": "serveur"})
        plante = self.tmp / "plante.json"
        self.ecrire_reglages({"tests": "serveur"}, fichier=plante)
        (self.p / "src" / ".factory").mkdir()
        self.ecrire_reglages({"tests": "serveur"}, fichier=self.p / "src" / ".factory" / "reglages.json")
        self.assertIsNotNone(self.refus(self.p / "src"))
        self.lancer(["--dossier", str(self.p / "src"), "--reglages", str(plante), "--", "x"])
        self.lancer(["--dossier", str(self.p / "src"), "--", "x"])
        self.assertNotIn("route", [v[0] for v in self.vus])

    @unittest.skipUnless(os.name == "nt", "jonction Windows")
    def test_jonction_vers_un_dossier_non_enregistre_refusee(self):
        import _winapi
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_bureau([self.reglages])
        dehors = self.tmp / "dehors"
        dehors.mkdir()
        lien = self.p / "src" / "lien"
        _winapi.CreateJunction(str(dehors), str(lien))
        self.addCleanup(os.rmdir, str(lien))
        self.assertIsNotNone(self.refus(lien))
        self.lancer(["--serveur", "--dossier", str(lien), "--", "x"])
        self.assertNotIn("route", [v[0] for v in self.vus])


class TestAiguillage(Base):
    def test_sans_aucun_reglage_le_poste_comme_aujourd_hui(self):
        argv = ["--dossier", str(self.p), "--sans-attendre", "--", "x", "--local"]
        self.assertEqual(self.lancer(argv), 0)
        self.assertEqual(self.vus, [("poste", argv)])
        self.assertEqual(self.sortie, "")
        self.ecrire_bureau([self.reglages])
        self.vus.clear()
        self.assertEqual(self.lancer(argv), 0)
        self.assertEqual((self.vus, self.sortie), ([("poste", argv)], ""))

    def test_ordre_d_aiguillage(self):
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_bureau([self.reglages])
        src = str(self.p / "src")
        # 1. --local : le poste, même avec l'accord
        self.assertEqual(self.lancer(["--local", "--dossier", src, "--", "x"]), 0)
        self.assertEqual(self.vus, [("poste", ["--dossier", src, "--", "x"])])
        # 3. l'accord : la route, avec repli permis
        self.vus.clear()
        self.assertEqual(self.lancer(["--dossier", src, "--sans-attendre", "--", "x", "y"]), 7)
        self.assertEqual(self.vus, [("route", ["x", "y"], src, False, False)])
        # --serveur : la route forcée
        self.vus.clear()
        self.assertEqual(self.lancer(["--serveur", "--dossier", src, "--", "x"]), 7)
        self.assertEqual(self.vus, [("route", ["x"], src, True, True)])
        # 2. GitHub : deporter, avant l'accord
        self.ecrire_reglages({"tests": "github"})
        self.vus.clear()
        self.assertEqual(self.lancer(["--dossier", src, "--", "x"]), 0)
        self.assertEqual(self.vus, [("deporter", ["tests", "--dossier", src, "--", "x"])])
        # --serveur sans accord : 2, rien de lancé
        self.vus.clear()
        self.assertEqual(self.lancer(["--serveur", "--dossier", src, "--", "x"]), 2)
        self.assertEqual(self.vus, [])
        self.assertIn("github", self.sortie)
        # 4. sinon le poste
        self.ecrire_reglages({"tests": "poste"})
        self.vus.clear()
        self.assertEqual(self.lancer(["--dossier", src, "--", "x"]), 0)
        self.assertEqual(self.vus, [("poste", ["--dossier", src, "--", "x"])])

    def test_options_retirees_de_la_commande(self):
        self.assertEqual(self.lancer(["--local", "--", "npx", "vitest", "--local"]), 0)
        self.assertEqual(self.vus, [("poste", ["--", "npx", "vitest", "--local"])])
        self.vus.clear()
        self.assertEqual(self.lancer(["--dossier", "--local", "--", "x"]), 0)      # valeur de --dossier, pas l'option
        self.assertEqual(self.vus, [("poste", ["--dossier", "--local", "--", "x"])])

    def test_local_et_serveur_ensemble_refuses(self):
        self.assertEqual(self.lancer(["--local", "--serveur", "--", "x"]), 2)
        self.assertEqual(self.vus, [])

    def test_serveur_usage_faux_refuse(self):
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_bureau([self.reglages])
        self.assertEqual(self.lancer(["--serveur", "--dossier", str(self.p)]), 2)
        self.assertEqual(self.vus, [])

    def test_route_par_defaut_sous_python_ancien(self):
        appels = []
        python = ["C:\\py.exe", "-3.12"]
        code = deporter._route_par_defaut(["x", "y"], "D", False, True, version=(3, 9),
                                          trouver_python=lambda: python,
                                          executer=lambda argv: appels.append(argv) or 5)
        self.assertEqual(code, 5)
        self.assertEqual(appels, [python + deporter.OPTIONS_PYTHON + [str(deporter.LANCEUR), "serveur-tests",
                                                                       "--dossier", "D", "--sans-attendre",
                                                                       "--serveur", "--", "x", "y"]])
        self.assertIsNone(deporter._route_par_defaut(["x"], "D", True, False, version=(3, 9),
                                                     trouver_python=lambda: None, executer=appels.append))

    def test_sans_python_312_le_poste_avec_une_ligne(self):
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_bureau([self.reglages])
        self.assertEqual(self.lancer(["--dossier", str(self.p), "--", "x"], route=lambda *a: None), 0)
        self.assertEqual(self.vus, [("poste", ["--dossier", str(self.p), "--", "x"])])
        self.assertEqual(len(self.sortie.strip().splitlines()), 1)
        self.vus.clear()
        self.assertEqual(self.lancer(["--serveur", "--dossier", str(self.p), "--", "x"], route=lambda *a: None), 4)
        self.assertEqual(self.vus, [])

    def test_porte_serveur_tests(self):
        """`lancer.py serveur-tests` est une autre porte : le même accord, avant tout import de la route."""
        vus = []

        class Route:
            @staticmethod
            def main(argv):
                vus.append(argv)
                return 0

        def porte(argv):
            sortie = io.StringIO()
            with contextlib.redirect_stderr(sortie):
                return deporter.serveur_tests(argv, bureau=self.bureau, importer=lambda: Route)

        argv = ["--dossier", str(self.p), "--serveur", "--", "x"]
        self.assertEqual(porte(argv), 2)
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_bureau([self.reglages])
        self.assertEqual(porte(argv), 0)
        self.assertEqual(vus, [argv])
        self.assertEqual(porte(["--dossier", str(self.tmp), "--", "x"]), 2)      # dossier hors du projet
        self.assertEqual(len(vus), 1)

    def test_lieu_serveur_admis_pour_une_action_routee(self):
        lieux = {a: "poste" for a in deport_types.GENERIQUE}
        self.assertEqual(deporter.lieux_refuses(dict(lieux, tests="serveur"), "tests", deport_types.GENERIQUE), [])
        self.assertTrue(deporter.lieux_refuses(dict(lieux, apk="serveur"), "tests", deport_types.GENERIQUE))
        self.assertTrue(deporter.lieux_refuses({"tests": "serveur"}, "tests", SANS_SERVEUR))
        self.assertFalse(deporter.doit_passer_par_deporter("tests", dict(lieux, tests="serveur"),
                                                           deport_types.GENERIQUE))
        self.assertTrue(deporter.doit_passer_par_deporter("tests", dict(lieux, tests="serveur", apk="github"),
                                                          deport_types.GENERIQUE))


class TestCompatibilite(unittest.TestCase):
    def test_compatible_py39(self):
        for chemin in ("bureau/deport_types.py", "outils/deporter.py", "lancer.py"):
            ast.parse((RACINE / chemin).read_text(encoding="utf-8"), feature_version=(3, 9))

    def test_lancer_annonce_serveur_tests(self):
        texte = (RACINE / "lancer.py").read_text(encoding="utf-8")
        self.assertIn("serveur-tests", texte.split('"""')[1])
        self.assertIn("--local", texte.split('"""')[1])


if __name__ == "__main__":
    unittest.main()
