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
              "dotnet-framework": "dotnet", "go": "go", "rust": "rust", "godot": "godot", "unity-asmdef": "unity"}


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
        u = analyser("unity-asmdef")
        self.assertEqual(u.outils, {"unity": "6000.6.7f1", "unity_revision": "b22767f04f04"})
        self.assertEqual((u.isolement, u.deps["unity"]["git"], u.ressources["memoire_mo"]), ("licence", ["github.com"], 10240))
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

    def test_ci_compare_majeure_mineure_pour_python(self):
        p = self.copie("python-stdlib")
        (p / ".python-version").write_text("3.9\n", encoding="utf-8")
        wf = p / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "x.yml").write_text("with:\n  python-version: '3.12'\n", encoding="utf-8")
        profil = tp.analyser(str(p), catalogue={})
        self.assertNotEqual(profil.confiance, "haute")
        self.assertTrue(any("CI" in r for r in profil.raisons))
        (wf / "x.yml").write_text("with:\n  python-version: '3.9'\n", encoding="utf-8")
        self.assertEqual(tp.analyser(str(p), catalogue={}).confiance, "haute")

    def test_outils_divergents_entre_familles(self):
        p = self.copie("gradle-android")
        (p / "pom.xml").write_text("<project><maven.compiler.release>11</maven.compiler.release></project>",
                                   encoding="utf-8")
        profil = tp.analyser(str(p), catalogue={})
        self.assertEqual(profil.confiance, "basse")
        self.assertTrue(any("jdk" in r for r in profil.raisons))

    def test_bornes_de_version_jamais_une_version(self):
        p = self.copie("python-stdlib")
        (p / ".python-version").unlink()
        (p / "pyproject.toml").write_text('[project]\nrequires-python = "<3.12"\n', encoding="utf-8")
        profil = tp.analyser(str(p), catalogue={})
        self.assertNotIn("python", profil.outils)
        self.assertEqual(profil.confiance, "moyenne")
        self.assertTrue(profil.raisons)
        (p / "pyproject.toml").write_text('[project]\nrequires-python = "~=3.11"\n', encoding="utf-8")
        self.assertEqual(tp.analyser(str(p), catalogue={}).outils, {"python": "3.11"})
        n = self.copie("node-npm")
        (n / ".nvmrc").unlink()
        (n / "package.json").write_text('{"scripts": {"test": "jest"}, "engines": {"node": ">=18 <22"}}',
                                        encoding="utf-8")
        self.assertNotIn("node", tp.analyser(str(n), catalogue={}).outils)
        (n / "package.json").write_text('{"scripts": {"test": "jest"}, "engines": {"node": "20.1.0"}}',
                                        encoding="utf-8")
        self.assertEqual(tp.analyser(str(n), catalogue={}).outils, {"node": "20.1.0"})

    def test_factory_json_borne_et_sans_lien(self):
        p = self.copie("node-npm")
        (p / ".factory").mkdir()
        fj = p / ".factory" / "factory.json"
        fj.write_text('{"genre": "application-mobile-android"}', encoding="utf-8")
        self.assertEqual(tp.analyser(str(p)).commandes, [["./gradlew", "testDebugUnitTest"]])
        fj.write_text('{"genre": "application-mobile-android", "x": "' + "a" * 70000 + '"}', encoding="utf-8")
        self.assertEqual(tp.analyser(str(p)).commandes, [["npm", "test"]])
        fj.unlink()
        dehors = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, dehors, True)
        (dehors / "f.json").write_text('{"genre": "application-mobile-android"}', encoding="utf-8")
        try:
            os.symlink(dehors / "f.json", fj)
        except (OSError, NotImplementedError):
            self.skipTest("le poste ne crée pas de lien symbolique")
        self.assertEqual(tp.analyser(str(p)).commandes, [["npm", "test"]])

    def test_parcours_en_largeur_et_plafond_dit(self):
        p = self.copie("gradle-android")
        (p / "docs").mkdir()
        for i in range(60):
            (p / "docs" / ("f%03d.txt" % i)).write_text("x", encoding="utf-8")
        with mock.patch.object(tp, "MAX_ENTREES", 50), mock.patch.object(tp, "MAX_PAR_DOSSIER", 20, create=True):
            profil = tp.analyser(str(p), catalogue={})
        self.assertEqual(profil.familles, ("gradle-android",))
        self.assertEqual(profil.confiance, "basse")
        self.assertTrue(any("tronqué" in r for r in profil.raisons))

    def test_plafond_xmx_dit(self):
        g = self.copie("gradle-android")
        (g / "gradle.properties").write_text("org.gradle.jvmargs=-Xmx99999g\n", encoding="utf-8")
        profil = tp.analyser(str(g), catalogue={})
        self.assertEqual(profil.confiance, "moyenne")
        self.assertTrue(any("Gradle" in r for r in profil.raisons))

    def test_commande_posee_sur_la_famille_de_son_executable(self):
        p = self.copie("node-npm")
        (p / "go.mod").write_text("module x\n\ngo 1.23\n", encoding="utf-8")
        profil = tp.analyser(str(p), catalogue={}, commande=["go", "test", "./..."])
        self.assertEqual(profil.familles, ("node", "go"))
        self.assertEqual(profil.commandes, [["npm", "test"], ["go", "test", "./..."]])

    def test_json_aller_retour(self):
        for cas in ("gradle-android", "unity-asmdef", "inconnu"):
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

    def test_famille_de_la_commande_lancee(self):
        # Le choix d'image part de la famille de la COMMANDE : un dépôt Python sans marqueur qui contient un sous-dossier .NET
        # Framework (N1) part au serveur dans myiafactory/tests pour `python3 outils/tests_paralleles.py`.
        import tests_images
        lancee = ["python3", "outils/tests_paralleles.py"]
        p = analyser("python-sans-marqueur-et-dotnet-framework", lancee=lancee)
        self.assertEqual(p.familles, ("python",))
        self.assertIsNone(p.non_deportable)
        choix = tests_images.choisir_image(p)
        self.assertEqual((choix["image"], choix["derivee"]), ("myiafactory/tests", False))
        self.assertIn("dotnet", analyser("python-sans-marqueur-et-dotnet-framework").familles)   # le projet entier, lui
        node = analyser("node-npm", lancee=["npx", "jest"])
        self.assertEqual(node.familles, ("node",))
        vide = tp.analyser(tempfile.mkdtemp(), catalogue={}, lancee=["node", "x.js"])
        self.assertEqual(vide.familles, ("node",))

    def test_le_depot_lui_meme_part_dans_l_image_de_base(self):
        import tests_images
        for lancee in (["python3", "outils/tests_paralleles.py"], ["py", "-3.12", "outils/tests_paralleles.py"]):
            with self.subTest(lancee=lancee):
                p = tp.analyser(str(RACINE), lancee=lancee)
                self.assertEqual(tests_images.choisir_image(p)["image"], "myiafactory/tests")
                self.assertIsNone(p.non_deportable)

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
