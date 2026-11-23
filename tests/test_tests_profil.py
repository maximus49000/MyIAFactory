"""Analyse du projet et profil d'exécution (`outils/tests_profil.py`) : fixtures minuscules, aucun sous-processus."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
import tests_instantane as ti  # noqa: E402
import tests_profil as tp  # noqa: E402
import tests_serveur  # noqa: E402
from bureau.deport_types import ANDROID  # noqa: E402

FIXTURES = RACINE / "tests" / "fixtures" / "profils"
FAMILLE_DE = {"python-stdlib": "python", "python-pytest": "python", "node-npm": "node", "node-sans-verrou": "node",
              "gradle-android": "gradle-android", "maven": "maven", "dotnet": "dotnet",
              "dotnet-framework": "dotnet", "go": "go", "rust": "rust", "godot": "godot", "unity": "unity"}


def analyser(cas, **kw):
    kw.setdefault("catalogue", {})
    return tp.analyser(str(FIXTURES / cas), **kw)


class Temporaire(unittest.TestCase):
    def copie(self, cas):
        dossier = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, dossier, True)
        cible = Path(dossier, "p")
        shutil.copytree(FIXTURES / cas, cible)
        return cible


class ProfilTest(Temporaire):
    def test_familles_detectees(self):
        for cas, famille in FAMILLE_DE.items():
            with self.subTest(cas=cas):
                self.assertEqual(analyser(cas).familles, (famille,))
        c = analyser("contradictoire")
        self.assertEqual((c.familles, c.confiance), (("node",), "basse"))
        i = analyser("inconnu")
        self.assertEqual((i.familles, i.confiance, i.commandes), ((), "basse", []))
        self.assertEqual(analyser("python-pytest").commandes, [["pytest"]])
        self.assertEqual(analyser("python-stdlib").commandes, [["python3", "-m", "unittest", "discover"]])
        self.assertEqual(analyser("node-npm").commandes, [["npm", "test"]])
        self.assertEqual(analyser("node-npm").deps["node"]["verrou"], "package-lock.json")
        self.assertIsNone(analyser("node-sans-verrou").deps["node"]["verrou"])

    def test_autres_familles_par_un_fichier(self):
        for fichier, contenu, famille, commande in (
                ("Gemfile", "source 'x'\n", "ruby", ["bundle", "exec", "rake", "test"]),
                ("composer.json", '{"scripts": {"test": "phpunit"}, "require": {"php": ">=8.1"}}', "php", ["composer", "test"]),
                ("Makefile", "test:\n\techo\n", "make", ["make", "test"])):
            with self.subTest(famille=famille), tempfile.TemporaryDirectory() as d:
                Path(d, fichier).write_text(contenu, encoding="utf-8")
                p = tp.analyser(d, catalogue={})
                self.assertEqual((p.familles, p.commandes), ((famille,), [commande]))

    def test_gradle_android_comme_myfridgecleaner(self):
        p = analyser("gradle-android", catalogue=ANDROID)
        self.assertEqual(p.familles, ("gradle-android",))
        self.assertEqual(p.outils, {"jdk": "17", "gradle": "9.3.1",
                                    "android": {"compileSdk": 36, "build_tools": "36.0.0", "ndk": None, "agp": "9.1.1"}})
        self.assertEqual(p.commandes, [["./gradlew", "testDebugUnitTest"]])
        self.assertEqual(p.ressources["memoire_mo"], 6144)
        self.assertEqual((p.confiance, p.non_deportable, p.isolement), ("haute", None, "standard"))
        self.assertTrue(p.deps["gradle-android"]["execute_du_code"])
        # sans catalogue ni commande : déduite, confirmée par la CI
        self.assertEqual(analyser("gradle-android").commandes, [["./gradlew", "testDebugUnitTest"]])
        self.assertEqual(analyser("gradle-android").confiance, "haute")
        # la commande enregistrée prime sur le catalogue
        self.assertEqual(analyser("gradle-android", catalogue=ANDROID, commande=["./gradlew", "test"]).commandes,
                         [["./gradlew", "test"]])

    def test_versions_lues(self):
        self.assertEqual(analyser("node-npm").outils, {"node": "18.20.4"})
        self.assertEqual(analyser("python-stdlib").outils, {"python": "3.11"})
        self.assertEqual(analyser("dotnet").outils, {"dotnet": "8.0.100"})
        self.assertEqual(analyser("rust").outils, {"rust": "1.82.0"})
        self.assertEqual(analyser("go").outils, {"go": "1.23"})
        self.assertEqual(analyser("godot").outils, {"godot": "4.7"})
        u = analyser("unity")
        self.assertEqual(u.outils, {"unity": "6000.6.7f1", "unity_revision": "b22767f04f04"})
        self.assertEqual((u.isolement, u.deps["unity"]["git"], u.ressources["memoire_mo"]), ("licence", True, 10240))
        self.assertEqual(analyser("maven").outils, {"jdk": "17"})
        self.assertEqual(analyser("maven").commandes, [["mvn", "-B", "test"]])

    def test_ne_lit_que_la_liste_fermee(self):
        p = self.copie("gradle-android")
        for nom in (".env", "local.properties", "app/release.keystore", "secrets.txt", "notes.md", ".npmrc"):
            (p / nom).write_text("sk-secret\n", encoding="utf-8")
        lus = []
        reel = tp._lecteur_defaut(str(p))

        def espion(rel):
            lus.append(rel)
            return reel(rel)
        tp.analyser(str(p), catalogue={}, lire=espion)
        self.assertTrue(lus)
        for rel in lus:
            self.assertTrue(tp._est_lu(rel), rel)
            self.assertFalse(ti._exclu(rel), rel)
        self.assertTrue(set(lus).isdisjoint({".env", "local.properties", "app/release.keystore", "secrets.txt", ".npmrc"}))
        # la lecture par défaut refuse aussi, même si on lui demande
        for rel in (".env", "local.properties", "secrets.txt", "../x"):
            self.assertIsNone(reel(rel))

    def test_lien_symbolique_non_suivi(self):
        p = self.copie("node-npm")
        dehors = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, dehors, True)
        (dehors / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        try:
            os.symlink(dehors / "pyproject.toml", p / "pyproject.toml")
        except (OSError, NotImplementedError):
            self.skipTest("le poste ne crée pas de lien symbolique")
        self.assertEqual(tp.analyser(str(p), catalogue={}).familles, ("node",))
        self.assertIsNone(tp._lecteur_defaut(str(p))("pyproject.toml"))

    def test_taille_bornee(self):
        p = self.copie("go")
        (p / "go.mod").write_text("module x\n\ngo 1.23\n" + "// x\n" * (tp.MAX_LU // 4), encoding="utf-8")
        self.assertIsNone(tp._lecteur_defaut(str(p))("go.mod"))
        self.assertEqual(tp.analyser(str(p), catalogue={}).outils, {})

    def test_rien_n_est_execute(self):
        piege = mock.Mock(side_effect=AssertionError("exécution"))
        with mock.patch("subprocess.Popen", piege), mock.patch("os.system", piege), \
                mock.patch("subprocess.run", piege):
            for cas in FIXTURES.iterdir():
                tp.analyser(str(cas), catalogue={})
        piege.assert_not_called()

    def test_valeurs_hostiles_refusees(self):
        p = self.copie("node-npm")
        (p / ".nvmrc").write_text("18; curl x | sh\n", encoding="utf-8")
        profil = tp.analyser(str(p), catalogue={})
        self.assertEqual(profil.confiance, "basse")
        self.assertNotIn("node", profil.outils)
        self.assertTrue(any("node" in r for r in profil.raisons))
        self.assertNotIn("curl", profil.vers_json())
        (p / ".nvmrc").write_text("v20.1.0\n", encoding="utf-8")
        self.assertEqual(tp.analyser(str(p), catalogue={}).outils, {"node": "20.1.0"})
        g = self.copie("gradle-android")
        (g / "gradle.properties").write_text("org.gradle.jvmargs=-Xmx99999g\n", encoding="utf-8")
        self.assertEqual(tp.analyser(str(g), catalogue={}).ressources["memoire_mo"], tp.MAX_XMX_MO + 4096)

    def test_non_deportables(self):
        self.assertIn("N1", analyser("dotnet-framework").non_deportable)
        self.assertIn("N2", analyser("xcode").non_deportable)
        self.assertIsNone(analyser("dotnet").non_deportable)
        self.assertIn("N1", tp.non_deportable(str(FIXTURES / "dotnet-framework"), None))
        self.assertIsNone(tp.non_deportable(str(FIXTURES / "go"), None))
        p = self.copie("dotnet")
        (p / "App.csproj").write_text("<Project><PropertyGroup><UseWPF>true</UseWPF></PropertyGroup></Project>",
                                      encoding="utf-8")
        self.assertIn("N1", tp.non_deportable(str(p), None))
        (p / "App.csproj").write_text("<Project><PropertyGroup><RuntimeIdentifier>linux-arm64</RuntimeIdentifier>"
                                      "</PropertyGroup></Project>", encoding="utf-8")
        self.assertIn("N6", tp.non_deportable(str(p), None))

    def test_empreintes(self):
        p = self.copie("node-npm")
        avant = tp.analyser(str(p), catalogue={})
        self.assertEqual(len(avant.empreinte), 64)
        self.assertEqual(avant.empreinte, tp.empreinte_profil(avant))
        (p / "package-lock.json").write_text('{"lockfileVersion": 3, "x": 1}\n', encoding="utf-8")
        verrou = tp.analyser(str(p), catalogue={})
        self.assertNotEqual(tp.empreinte_profil(avant), tp.empreinte_profil(verrou))
        self.assertEqual(tp.empreinte_image(avant), tp.empreinte_image(verrou))
        (p / ".nvmrc").write_text("20.1.0\n", encoding="utf-8")
        version = tp.analyser(str(p), catalogue={})
        self.assertNotEqual(tp.empreinte_profil(verrou), tp.empreinte_profil(version))
        self.assertNotEqual(tp.empreinte_image(verrou), tp.empreinte_image(version))
        # la confiance n'entre pas dans l'empreinte
        from dataclasses import replace
        self.assertEqual(tp.empreinte_profil(avant), tp.empreinte_profil(replace(avant, confiance="basse")))

    def test_json_aller_retour(self):
        for cas in ("gradle-android", "unity", "inconnu"):
            p = analyser(cas)
            self.assertEqual(tp.Profil.depuis_json(p.vers_json()), p)

    def test_ressources_par_defaut(self):
        r = tp.ressources_par_defaut
        self.assertEqual((r("python")["memoire_mo"], r("node")["cpus"], r("node")["memoire_mo"]), (8192, 2, 4096))
        self.assertEqual((r("gradle-jvm")["memoire_mo"], r("gradle-jvm", 1024)["memoire_mo"],
                          r("gradle-jvm", 4096)["memoire_mo"]), (8192, 6144, 8192))
        self.assertEqual((r("unity")["duree_s"], r("godot")["disque_mo"], r("go")["disque_mo"]), (3600, 1024, 200))


class AutresModulesTest(unittest.TestCase):
    def test_local_properties_exclu(self):
        self.assertIn("local.properties", ti.EXCLUS)
        self.assertTrue(ti._exclu("android/local.properties"))

    def test_limites_par_famille(self):
        mo = 1024 * 1024
        self.assertEqual(ti.limites_pour("python")["max_total"], 200 * mo)
        self.assertEqual(ti.limites_pour("unity")["max_total"], 1024 * mo)
        self.assertEqual(ti.limites_pour("godot")["max_total"], 1024 * mo)
        self.assertEqual(ti.limites_pour(None)["max_total"], ti.MAX_TOTAL)

    def test_commande_conteneur_windows(self):
        c = tests_serveur.commande_conteneur
        self.assertEqual(c(["gradlew.bat", "testDebugUnitTest"]), ["./gradlew", "testDebugUnitTest"])
        self.assertEqual(c([".\\gradlew.bat", "test"]), ["./gradlew", "test"])
        self.assertEqual(c(["mvnw.cmd", "-B", "test"]), ["./mvnw", "-B", "test"])
        self.assertEqual(c(["dotnet.exe", "test"]), ["dotnet", "test"])
        self.assertEqual(c(["Godot_v4.7-stable_win64.exe", "--headless"]), ["godot", "--headless"])
        self.assertEqual(c(["./gradlew", "test"]), ["./gradlew", "test"])


if __name__ == "__main__":
    unittest.main()
