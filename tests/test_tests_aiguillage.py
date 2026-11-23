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
import unittest.mock
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

    def test_le_niveau_type_du_bureau_envoie_sur_github(self):
        """`types.<genre>.deport.lieux.tests = github` (page Réglages, niveau type) : `lancer.py tests` passe par
        deporter, comme pour un réglage du projet ; le projet l'emporte toujours."""
        android = "application-mobile-android"
        (self.p / ".factory" / "factory.json").write_text(json.dumps({"genre": android}), encoding="utf-8")
        self.ecrire_bureau([self.reglages])
        b = json.loads(self.bureau.read_text(encoding="utf-8"))
        b["types"] = {android: {"deport": {"lieux": {"tests": "github"}}}}
        self.bureau.write_text(json.dumps(b), encoding="utf-8")
        src = str(self.p / "src")
        self.assertEqual(self.lancer(["--dossier", src, "--", "x"]), 0)
        self.assertEqual(self.vus, [("deporter", ["tests", "--dossier", src, "--", "x"])])
        self.ecrire_reglages({"tests": "poste"})
        self.vus.clear()
        self.assertEqual(self.lancer(["--dossier", src, "--", "x"]), 0)
        self.assertEqual(self.vus, [("poste", ["--dossier", src, "--", "x"])])

    def test_options_retirees_de_la_commande(self):
        ici = os.getcwd()
        os.chdir(str(self.tmp))      # jamais la racine du dépôt : le dossier courant est le dossier temporaire
        self.addCleanup(os.chdir, ici)
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
        with self.assertRaises(deporter.RouteIndisponible) as e:
            deporter._route_par_defaut(["x"], "D", True, False, version=(3, 9), trouver_python=lambda: None,
                                       executer=appels.append)
        self.assertIn("Python 3.12 introuvable", e.exception.raison)
        self.assertEqual(len(appels), 1)

    def test_sans_python_312_le_poste_avec_une_ligne(self):
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_bureau([self.reglages])

        def indisponible(*a):
            raise deporter.RouteIndisponible("Raison X")
        self.assertEqual(self.lancer(["--dossier", str(self.p), "--", "x"], route=indisponible), 0)
        self.assertEqual(self.vus, [("poste", ["--dossier", str(self.p), "--", "x"])])
        self.assertEqual(len(self.sortie.strip().splitlines()), 1)
        self.assertIn("Raison X", self.sortie)
        self.vus.clear()
        self.assertEqual(self.lancer(["--serveur", "--dossier", str(self.p), "--", "x"], route=indisponible), 4)
        self.assertEqual(self.vus, [])
        self.assertIn("Raison X", self.sortie)

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
                return deporter.serveur_tests(argv, bureau=self.bureau, importer=lambda: Route, version=(3, 12))

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


class TestAccordChemins(Base):
    """Relecture de la tâche 7 : chemins voisins, projets emboîtés, entrées écartées, racines trop larges."""

    def test_prefixe_frere_jamais_le_projet(self):
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_bureau([self.reglages])
        frere = self.tmp / "p-evil"
        (frere / ".factory").mkdir(parents=True)
        self.ecrire_reglages({"tests": "serveur"}, fichier=frere / ".factory" / "reglages.json")
        self.assertIn("enregistré", self.refus(frere))
        self.lancer(["--dossier", str(frere), "--", "x"])
        self.assertNotIn("route", [v[0] for v in self.vus])

    def emboite(self, dehors, dedans):
        sous = self.p / "sub"
        (sous / ".factory").mkdir(parents=True)
        (sous / "x").mkdir()
        self.ecrire_reglages({"tests": dehors})
        self.ecrire_reglages({"tests": dedans}, fichier=sous / ".factory" / "reglages.json")
        self.ecrire_bureau([self.reglages, sous / ".factory" / "reglages.json"])
        return sous

    def test_projets_emboites_le_plus_long_decide(self):
        sous = self.emboite("serveur", "poste")
        self.assertIsNotNone(self.refus(sous / "x"))
        self.assertIsNone(self.refus(self.p / "src"))

    def test_projets_emboites_le_plus_long_decide_a_l_inverse(self):
        sous = self.emboite("poste", "serveur")
        self.assertIsNone(self.refus(sous / "x"))
        self.assertIsNotNone(self.refus(self.p / "src"))

    def test_fichiers_enregistres_en_desaccord(self):
        autre = self.p / "reglages.json"             # même projet : le dossier du fichier
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_reglages({"tests": "poste"}, fichier=autre)
        self.ecrire_bureau([self.reglages, autre])
        self.assertIn("poste", self.refus(self.p))
        self.ecrire_reglages({"tests": "serveur"}, fichier=autre)
        self.assertIsNone(self.refus(self.p))

    @unittest.skipUnless(os.name == "nt", "casse et préfixe \\\\?\\ : Windows")
    def test_casse_et_prefixe_long(self):
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_bureau([self.reglages])
        self.assertIsNone(self.refus(str(self.p / "src").upper()))
        long = "\\\\?\\" + str(self.p / "src")
        self.assertIsNone(self.refus(long))
        self.assertEqual(self.lancer(["--dossier", long, "--", "x"]), 7)
        self.assertEqual([v[0] for v in self.vus], ["route"])

    @unittest.skipUnless(os.name == "nt", "jonction Windows")
    def test_entree_plus_longue_ecartee_refuse(self):
        """Une entrée du bureau plus longue dont le `.factory` est une jonction vers ailleurs est écartée par
        `projet_enregistre` : le projet parent (réglé serveur) ne doit pas donner l'accord à sa place."""
        import _winapi
        self.ecrire_reglages({"tests": "serveur"})
        ailleurs = self.tmp / "ailleurs" / ".factory"
        ailleurs.mkdir(parents=True)
        self.ecrire_reglages({"tests": "serveur"}, fichier=ailleurs / "reglages.json")
        sous = self.p / "sub"
        (sous / "x").mkdir(parents=True)
        _winapi.CreateJunction(str(ailleurs), str(sous / ".factory"))
        self.addCleanup(os.rmdir, str(sous / ".factory"))
        self.ecrire_bureau([self.reglages, sous / ".factory" / "reglages.json"])
        self.assertIn("mènent ailleurs", self.refus(sous / "x"))
        self.assertIsNone(self.refus(self.p / "src"))

    def test_racine_trop_large_refusee(self):
        maison = Path(os.path.expanduser("~"))
        self.ecrire_bureau([maison / ".factory" / "reglages.json"], lieux={"tests": "serveur"})
        self.assertIn("personnel", self.refus(maison / "un-projet-qui-n-existe-pas"))
        racine = Path(self.tmp.anchor)
        self.ecrire_bureau([racine / ".factory" / "reglages.json"], lieux={"tests": "serveur"})
        self.assertIn("racine de lecteur", self.refus(self.p))


class TestCheminDeLAccord(Base):
    """L'accord est bien jugé par `refus_route` (témoin) : un refus coupe la route, `--reglages` compris."""

    def espion(self, reponse):
        appels = []

        def refus_route(dossier, action, bureau=None):
            appels.append((dossier, action, bureau))
            if isinstance(reponse, BaseException):
                raise reponse
            return reponse
        patch = unittest.mock.patch.object(deporter, "refus_route", refus_route)
        patch.start()
        self.addCleanup(patch.stop)
        return appels

    def test_refus_coupe_la_route(self):
        src = str(self.p / "src")
        appels = self.espion("non")
        self.lancer(["--dossier", src, "--", "x"])
        self.assertEqual(appels, [(src, "tests", str(self.bureau))])
        self.assertEqual(self.vus, [("poste", ["--dossier", src, "--", "x"])])

    def test_reglages_jamais_routes_meme_avec_l_accord(self):
        """`--reglages` n'est pas une option de la campagne : même si l'accord était donné (témoin à None), la route
        n'est jamais prise (la campagne dit l'usage), ni par `--serveur`, ni par la porte `serveur-tests`."""
        src = str(self.p / "src")
        self.espion(None)
        argv = ["--dossier", src, "--reglages", str(self.reglages), "--", "x"]
        self.lancer(argv)
        self.assertEqual(self.vus, [("poste", argv)])
        self.vus.clear()
        self.assertEqual(self.lancer(["--serveur"] + argv), 2)
        self.assertEqual(self.vus, [])
        sortie = io.StringIO()
        with contextlib.redirect_stderr(sortie):
            self.assertEqual(deporter.serveur_tests(argv, bureau=self.bureau, importer=lambda: self.fail("importée"),
                                                    version=(3, 12)), 2)

    def test_accord_ouvre_la_route(self):
        appels = self.espion(None)
        src = str(self.p / "src")
        self.assertEqual(self.lancer(["--dossier", src, "--", "x"]), 7)
        self.assertEqual(appels, [(src, "tests", str(self.bureau))])
        self.assertEqual(self.vus, [("route", ["x"], src, True, False)])

    def test_ctrl_c_pendant_le_jugement(self):
        self.espion(KeyboardInterrupt())
        self.assertEqual(self.lancer(["--dossier", str(self.p), "--", "x"]), 130)
        self.assertEqual(self.vus, [])
        self.assertEqual(deporter.serveur_tests(["--dossier", str(self.p), "--", "x"], bureau=self.bureau,
                                                importer=lambda: self.fail("importée"), version=(3, 12)), 130)

    def test_porte_refuse_sans_importer(self):
        self.espion("non")
        sortie = io.StringIO()
        with contextlib.redirect_stderr(sortie):
            code = deporter.serveur_tests(["--dossier", str(self.p), "--", "x"], bureau=self.bureau,
                                          importer=lambda: self.fail("importée"), version=(3, 12))
        self.assertEqual(code, 2)
        self.assertIn("non", sortie.getvalue())


class TestAmontGitHub(Base):
    """`tests: serveur` avec une production attendue de GitHub (`apk: github`) : jamais en silence."""

    def setUp(self):
        Base.setUp(self)
        self.ecrire_reglages({"tests": "serveur", "apk": "github"})
        self.ecrire_bureau([self.reglages])

    def test_lancer_tests_passe_par_deporter_jamais_la_route(self):
        self.assertEqual(self.lancer(["--dossier", str(self.p), "--", "x"]), 0)
        self.assertEqual(self.vus, [("deporter", ["tests", "--dossier", str(self.p), "--", "x"])])

    def test_deporter_dit_puis_lance_au_poste_avec_l_artefact(self):
        postes = []

        def sur_github(c):           # l'exécution GitHub simulée : l'artefact téléchargé, puis la suite de deporter
            return c["lancer_au_poste"]({"MYIAFACTORY_ARTEFACT_APK": "a.apk"})
        patch = unittest.mock.patch.object(deporter, "_sur_github", sur_github)
        patch.start()
        self.addCleanup(patch.stop)
        dits = []
        code = deporter.main(["tests", "--dossier", str(self.p), "--", "x"], bureau=self.bureau,
                             executer_poste=lambda c, dossier=None, attendre=True, env=None:
                             postes.append((c, env)) or 0,
                             dire=lambda texte, **k: dits.append(texte), repertoire_attente=self.tmp / "attente")
        self.assertEqual(code, 0)
        self.assertEqual(postes, [(["x"], {"MYIAFACTORY_ARTEFACT_APK": "a.apk"})])
        self.assertEqual(dits, [deporter.MSG_AMONT_GITHUB])

    def test_serveur_force_refuse_sans_l_artefact(self):
        self.assertEqual(self.lancer(["--serveur", "--dossier", str(self.p), "--", "x"]), 2)
        self.assertEqual(self.vus, [])
        self.assertIn("GitHub", self.sortie)


class TestIndisponible(Base):
    """M8 : lancement, import, version, Ctrl-C de la route."""

    def test_executer_route_ctrl_c_et_oserror(self):
        def ctrl_c(*a, **k):
            raise KeyboardInterrupt

        def absent(*a, **k):
            raise FileNotFoundError("py.exe")
        self.assertEqual(deporter._executer_route(["py"], run=ctrl_c), 130)
        with self.assertRaises(deporter.RouteIndisponible) as e:
            deporter._executer_route(["py"], run=absent)
        self.assertIn("Lancement de Python 3.12 impossible", e.exception.raison)
        self.assertNotIn("introuvable", e.exception.raison)

    def test_import_en_echec(self):
        def casse():
            raise ImportError("tests_serveur abîmé")
        with self.assertRaises(deporter.RouteIndisponible) as e:
            deporter._route_par_defaut(["x"], "D", True, False, version=(3, 12), importer=casse)
        self.assertIn("ImportError", e.exception.raison)
        self.assertEqual(deporter._route_par_defaut(["x"], "D", True, False, version=(3, 12),
                                                    importer=lambda: unittest.mock.Mock(
                                                        executer=unittest.mock.Mock(side_effect=KeyboardInterrupt))),
                         130)
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_bureau([self.reglages])
        sortie = io.StringIO()
        with contextlib.redirect_stderr(sortie):
            code = deporter.serveur_tests(["--dossier", str(self.p), "--", "x"], bureau=self.bureau, importer=casse,
                                          version=(3, 12))
        self.assertEqual(code, 4)
        self.assertIn("ImportError", sortie.getvalue())

    def test_porte_exige_312(self):
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_bureau([self.reglages])
        sortie = io.StringIO()
        with contextlib.redirect_stderr(sortie):
            code = deporter.serveur_tests(["--dossier", str(self.p), "--", "x"], bureau=self.bureau,
                                          importer=lambda: self.fail("importée"), version=(3, 9))
        self.assertEqual(code, 4)

    def test_porte_transmet_sans_attendre(self):
        self.ecrire_reglages({"tests": "serveur"})
        self.ecrire_bureau([self.reglages])
        vus = []
        route = unittest.mock.Mock(main=lambda argv: vus.append(argv) or 0)
        deporter.serveur_tests(["--sans-attendre", "--dossier", str(self.p), "--", "x"], bureau=self.bureau,
                               importer=lambda: route, version=(3, 12))
        self.assertEqual(vus, [["--dossier", str(self.p), "--sans-attendre", "--", "x"]])


class TestVerrouDuRun(Base):
    """Le verrou de la course de `deporter` reconnaît un pid repris par un autre programme (`vivant_et_meme`)."""

    def test_pid_repris_perime(self):
        import time
        chemin = self.tmp / "v.lock"
        t = time.time()
        chemin.write_text(json.dumps({"pid": 4242, "demarre": 1000.0, "t": t}), encoding="utf-8")
        self.assertFalse(deporter._verrou_perime(chemin, t, etat=lambda pid: (True, 1000.0)))     # le même
        self.assertTrue(deporter._verrou_perime(chemin, t, etat=lambda pid: (True, 9000.0)))      # pid repris
        self.assertTrue(deporter._verrou_perime(chemin, t, etat=lambda pid: (False, None)))       # mort
        self.assertTrue(deporter._verrou_perime(chemin, t + 1000, etat=lambda pid: (True, 1000.0)))  # trop vieux
        chemin.write_text(json.dumps({"pid": 4242, "t": t}), encoding="utf-8")                   # ancienne note
        self.assertTrue(deporter._verrou_perime(chemin, t, etat=lambda pid: (True, t + 60)))      # né après elle
        self.assertFalse(deporter._verrou_perime(chemin, t, etat=lambda pid: (True, t - 60)))
        chemin.write_text(json.dumps({"pid": True, "t": t}), encoding="utf-8")
        self.assertTrue(deporter._verrou_perime(chemin, t, etat=lambda pid: (True, None)))

    def test_verrou_note_sa_date_de_creation(self):
        chemin = self.tmp / "w.lock"
        with deporter._verrou_du_run(chemin, True, lambda s: None, lambda *a, **k: None):
            note = json.loads(chemin.read_text(encoding="utf-8"))
        self.assertEqual(note["pid"], os.getpid())
        self.assertIn("demarre", note)
        self.assertFalse(chemin.exists())


class TestCompatibilite(unittest.TestCase):
    def test_compatible_py39(self):
        # tout ce que le lanceur importe sous un Python ancien (`lancer.py tests` / `deporter`)
        for chemin in ("bureau/deport_types.py", "outils/deporter.py", "lancer.py", "bureau/tests_mesures.py",
                       "bureau/tests_sceau.py", "bureau/verrou_fichier.py", "bureau/deport.py", "bureau/deport_conso.py",
                       "bureau/serveur.py", "bureau/__init__.py", "outils/campagne.py", "outils/deport_depot.py",
                       "outils/github_actions.py"):
            ast.parse((RACINE / chemin).read_text(encoding="utf-8"), feature_version=(3, 9))

    def test_lancer_annonce_serveur_tests(self):
        texte = (RACINE / "lancer.py").read_text(encoding="utf-8")
        self.assertIn("serveur-tests", texte.split('"""')[1])
        self.assertIn("--local", texte.split('"""')[1])


if __name__ == "__main__":
    unittest.main()
