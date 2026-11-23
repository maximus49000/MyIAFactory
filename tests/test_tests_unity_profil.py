"""Profil Unity et exclusions de licence (tâche 14f) : aucune licence ni session Unity ne part dans l'instantané.

Un seul vrai `git init` (dans `setUpClass`), pour l'exclusion ; le reste lit des fixtures minuscules, sans sous-processus."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
import tests_instantane as ti  # noqa: E402
import tests_profil as tp  # noqa: E402

FIXTURES = RACINE / "tests" / "fixtures" / "profils"
LICENCES = ["Unity_lic.ulf", "Unity_lic.ulf.bak", "Unity_lic", "a/Unity-LicenseClient-x.log", "x/UnityEntitlementLicense.xml", ".config/unity3d/Unity/licenses/a.xml",
            ".config/unityhub/session.json", ".local/share/unity3d/Unity/Unity_lic.ulf", "Unity.Licensing.Client.log"]
COMMANDE_UNITY = ["unity-editor", "-batchmode", "-nographics", "-projectPath", "/work", "-runTests", "-testPlatform",
                  "EditMode", "-testResults", "/tmp/resultats.xml", "-logFile", "/tmp/unity.log"]


def _git(argv, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                    "-c", "core.autocrlf=false"] + argv, cwd=cwd, check=True, capture_output=True,
                   stdin=subprocess.DEVNULL)


def _ecrire(racine, nom, contenu="x\n"):
    chemin = Path(racine, *nom.split("/"))
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")


def analyser(cas, **kw):
    kw.setdefault("catalogue", {})
    return tp.analyser(str(FIXTURES / cas), **kw)


class ExclusionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dossier = tempfile.mkdtemp()
        cls.racine = str(Path(cls.dossier, "p"))
        Path(cls.racine).mkdir()
        _git(["init", "-q"], cls.racine)
        cls.admis = ["Assets/Unity3D/a.cs", "Assets/Library/x.cs", "Assets/Editor/b.cs",
                     "ProjectSettings/ProjectVersion.txt"]
        cls.famille = ["Library/a.asset", "Temp/t.txt", "Logs/l.txt", "UserSettings/s.json", "obj/o.dll", "Build/b.bin",
                       "Builds/c.bin"]
        for nom in LICENCES + cls.admis + cls.famille:
            _ecrire(cls.racine, nom)
        _git(["add", "-f", "-A"], cls.racine)
        cls.sans, _ = ti.lister(cls.racine)
        cls.avec, _ = ti.lister(cls.racine, famille="unity")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dossier, True)

    def test_licence_unity_exclue(self):
        for nom in LICENCES:
            with self.subTest(nom=nom):
                self.assertNotIn(nom, self.sans)
                self.assertNotIn(nom, self.avec)
        self.assertIn("Assets/Unity3D/a.cs", self.sans)

    def test_exclus_de_famille_unity(self):
        self.assertEqual(ti.exclus_de_famille("unity"), ("Library/", "Temp/", "Logs/", "UserSettings/", "obj/", "Build/",
                                                         "Builds/"))
        self.assertEqual(ti.exclus_de_famille("python"), ())
        for nom in self.famille:
            self.assertNotIn(nom, self.avec)
            self.assertIn(nom, self.sans)         # famille python ou inconnue : rien d'écarté de plus
        for nom in self.admis:
            self.assertIn(nom, self.avec)          # `Assets/Library/x.cs` reste : seule la racine est visée
        self.assertEqual(ti.limites_pour("unity")["max_total"], 1024 * 1024 * 1024)

    def test_segments_sans_casse_et_a_tout_niveau(self):
        self.assertTrue(ti._exclu("h/.Config/Unity3D/x"))
        self.assertTrue(ti._exclu("a/b/.local/share/unity3d/x"))
        self.assertFalse(ti._exclu(".config/autre/unity3d/x"))
        self.assertFalse(ti._exclu("Assets/Unity3D/a.cs"))

    def test_archive_refuse_la_famille(self):
        import io
        with self.assertRaises(ti.HorsLimites):
            ti.ecrire_tar(self.racine, ["Library/a.asset"], io.BytesIO(), famille="unity")


class ProfilUnityTest(unittest.TestCase):
    def copie(self, cas):
        dossier = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, dossier, True)
        cible = Path(dossier, "p")
        shutil.copytree(FIXTURES / cas, cible)
        return cible

    def test_profil_sur_la_route(self):
        p = analyser("unity-sans-asmdef")
        self.assertEqual(p.familles, ("python", "unity"))
        self.assertEqual((p.outils["unity"], p.outils["unity_revision"]), ("6000.6.7f1", "b22767f04f04"))
        self.assertEqual(p.deps["unity"]["git"], ["github.com"])
        self.assertEqual((p.deps["unity"]["gestionnaire"], p.deps["unity"]["verrou"], p.deps["unity"]["reseau"],
                          p.deps["unity"]["execute_du_code"]), ("upm", "Packages/packages-lock.json", True, True))
        self.assertEqual(len(p.commandes), 2)
        self.assertIn(COMMANDE_UNITY, p.commandes)
        self.assertEqual((p.confiance, p.isolement), ("moyenne", "licence"))
        r = p.ressources
        self.assertEqual((r["cpus"], r["memoire_mo"], r["duree_s"], r["tmp_mo"]), (4, 10240, 3600, 6144))
        self.assertEqual(tp.tests_unity(str(FIXTURES / "unity-sans-asmdef"), None)["confiance"], "moyenne")

    def test_asmdef_confiance_haute(self):
        t = tp.tests_unity(str(FIXTURES / "unity-asmdef"), None)
        self.assertEqual((t["asmdef"], t["confiance"], t["dossiers"]), (True, "haute", ["Assets/Editor/Tests"]))
        self.assertEqual(analyser("unity-asmdef").confiance, "haute")
        self.assertEqual(tp.ressources_par_defaut("unity")["tmp_mo"], 6144)

    def test_aucun_test_repere_basse(self):
        d = self.copie("unity-sans-asmdef")
        shutil.rmtree(d / "Assets")
        t = tp.tests_unity(str(d), None)
        self.assertEqual((t["asmdef"], t["dossiers"], t["confiance"]), (False, [], "basse"))
        p = tp.analyser(str(d), catalogue={})
        self.assertEqual(p.confiance, "basse")
        self.assertTrue(any("aucun test EditMode" in r for r in p.raisons))

    def test_playmode_n3(self):
        d = self.copie("unity-asmdef")
        (d / "Assets/Editor/Tests/Tests.asmdef").write_text(json.dumps(
            {"name": "T", "includePlatforms": [], "defineConstraints": ["UNITY_INCLUDE_TESTS"]}), encoding="utf-8")
        p = tp.analyser(str(d), catalogue={}, lancee=COMMANDE_UNITY)
        self.assertTrue(p.non_deportable.startswith("N3") and "PlayMode" in p.non_deportable)
        sans = tp.analyser(str(d), catalogue={})        # sans commande lancée : le projet entier
        self.assertTrue(sans.non_deportable.startswith("N3"))
        self.assertEqual(sans.commandes, [])
        python = tp.analyser(str(d), catalogue={}, lancee=["python3", "-m", "unittest"])
        self.assertIsNone(python.non_deportable)
        self.assertFalse(any("PlayMode" in " ".join(c) for c in p.commandes))
        # EditMode et PlayMode ensemble : la commande EditMode part, PlayMode n'est pas proposée
        _ecrire(d, "Assets/Editor/Tests/E.asmdef", json.dumps({"name": "E", "includePlatforms": ["Editor"],
                                                                 "precompiledReferences": ["nunit.framework.dll"]}))
        q = tp.analyser(str(d), catalogue={}, lancee=COMMANDE_UNITY)
        self.assertIsNone(q.non_deportable)
        self.assertEqual(q.commandes, [COMMANDE_UNITY])

    def test_version_unity_hostile_refusee(self):
        for hostile in ("6000.6.7f1; rm -rf /", "6000.6.7f1$(id)", "6000.6.7"):
            d = self.copie("unity-sans-asmdef")
            _ecrire(d, "ProjectSettings/ProjectVersion.txt", "m_EditorVersion: %s\n" % hostile)
            p = tp.analyser(str(d), catalogue={})
            with self.subTest(hostile=hostile):
                self.assertNotIn("unity", p.outils)
                self.assertEqual(p.confiance, "basse")
                self.assertIn("version unity illisible (ProjectVersion.txt)", p.raisons)
                self.assertNotIn("rm -rf", p.vers_json())
        d = self.copie("unity-sans-asmdef")
        _ecrire(d, "ProjectSettings/ProjectVersion.txt",
                "m_EditorVersion: 6000.6.7f1\nm_EditorVersionWithRevision: 6000.6.7f1 (b2276; id)\n")
        p = tp.analyser(str(d), catalogue={})
        self.assertNotIn("unity_revision", p.outils)
        self.assertIn("version unity_revision illisible (ProjectVersion.txt)", p.raisons)

    def test_hote_git_hostile_refuse(self):
        d = self.copie("unity-sans-asmdef")
        _ecrire(d, "Packages/manifest.json", json.dumps({"dependencies": {
            "a": "https://github.com/x/y.git", "b": "git@gitlab.com:x/y.git", "c": "git+ssh://git@h.example:22/x.git",
            "d": "https://evil.com;rm -rf/x.git"}}))
        p = tp.analyser(str(d), catalogue={})
        self.assertEqual(p.deps["unity"]["git"], ["github.com", "gitlab.com", "h.example"])
        self.assertEqual(p.confiance, "basse")
        self.assertNotIn("evil", p.vers_json())

    def test_hotes_git_internes_ou_trompeurs_refuses(self):
        for mauvais in ("https://169.254.169.254/x.git", "https://10.0.0.5/x.git", "git@10.0.0.5:x/y.git",
                        "https://[::1]/x.git", "https://localhost/x.git", "https://hote/x.git", "https://a.internal/x.git",
                        "https://a.local/x.git", "https://evil.com#@github.com/x.git", "https://evil.com?@github.com/x.git",
                        "https://evil.com\\@github.com/x.git", "https://x:y@192.168.1.1/x.git"):
            with self.subTest(mauvais=mauvais):
                self.assertIsNone(tp._hote_git(mauvais))
        self.assertEqual(tp._hote_git("https://u:p@GitHub.com:443/x.git"), "github.com")
        d = self.copie("unity-sans-asmdef")
        _ecrire(d, "Packages/manifest.json", json.dumps({"dependencies": {"a": "https://evil.com#@github.com/x.git"}}))
        p = tp.analyser(str(d), catalogue={})
        self.assertEqual((p.deps["unity"]["git"], p.confiance), ([], "basse"))
        self.assertIn("hôte git d'une dépendance illisible (manifest.json)", p.raisons)

    def test_trop_d_hotes_git_dit(self):
        d = self.copie("unity-sans-asmdef")
        deps = {"p%d" % i: "https://h%d.example.com/x.git" % i for i in range(21)}
        _ecrire(d, "Packages/manifest.json", json.dumps({"dependencies": deps}))
        p = tp.analyser(str(d), catalogue={})
        self.assertEqual(len(p.deps["unity"]["git"]), 20)
        self.assertTrue(any("plus de 20 hôtes git" in r for r in p.raisons))

    def test_famille_d_exclusion_selon_le_projet(self):
        import tests_serveur
        d = self.copie("unity-sans-asmdef")
        self.assertEqual(tests_serveur._famille_exclusion(str(d)), "unity")
        shutil.rmtree(d / "ProjectSettings")
        self.assertIsNone(tests_serveur._famille_exclusion(str(d)))

    def test_python_du_projet_sans_licence(self):
        p = analyser("unity-sans-asmdef", lancee=["python3", "-m", "unittest", "discover", "-s", "Tools/factory/tests"])
        self.assertEqual((p.familles, p.isolement), (("python",), "standard"))
        self.assertNotIn("unity", p.outils)
        self.assertNotIn("unity", p.deps)
        self.assertIsNone(p.non_deportable)
        self.assertNotIn("licence", p.vers_json())

    def test_asmdef_lus_comme_json_borne(self):
        self.assertTrue(tp._est_lu("Assets/Editor/Tests/Tests.asmdef"))
        d = self.copie("unity-asmdef")
        (d / "Assets/Editor/Tests/Tests.asmdef").write_text("{ pas du json", encoding="utf-8")
        t = tp.tests_unity(str(d), None)
        self.assertEqual((t["asmdef"], t["confiance"]), (False, "moyenne"))


if __name__ == "__main__":
    unittest.main()
