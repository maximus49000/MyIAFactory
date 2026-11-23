"""Images du catalogue des tests au serveur et image `tests-android` (conception § 5.12, tâche 14b) : capacité, choix d'après
le profil, arguments `<image> <famille>` de l'enveloppe hôte (faux `docker`, rien n'est construit) et étape simulée."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import serveur_capacites as sc  # noqa: E402
import test_serveur_tests_enveloppe as banc  # noqa: E402
import tests_images  # noqa: E402
import tests_profil  # noqa: E402
import tests_serveur  # noqa: E402
from tests_profil import Profil  # noqa: E402

FRIDGE = {"gradle": "9.3.1", "jdk": "17",
          "android": {"compileSdk": 36, "build_tools": "36.0.0", "ndk": None, "agp": "9.1.1"}}


def profil(familles, **outils):
    return Profil(familles=tuple(familles), outils=dict(outils))


class TestCatalogue(unittest.TestCase):
    def test_capacite_tests_android(self):
        sc.verifier_catalogue()
        cap = sc.CATALOGUE["tests-android"]
        self.assertEqual((cap.depend, cap.etape, cap.taille_go, cap.duree_min), (("tests-image", "android-build"), "tests_android_image", 0.5, 4))
        self.assertEqual(cap.sonde, "test -s ~/.myiafactory/tests-android-image.version")
        self.assertEqual(sc.BESOINS["tests-serveur-android"], ("tests-android",))
        self.assertEqual(sc.manquantes_pour(["tests-serveur-android"], {"base", "tests-image"}), ["android-build", "tests-android"])

    def test_choix_catalogue(self):
        python = tests_images.choisir_image(profil(["python"], python="3.12"))
        self.assertEqual((python["image"], python["capacites"], python["derivee"], python["manque"]),
                         ("myiafactory/tests", ["tests-image"], False, []))
        self.assertEqual(tests_images.choisir_image(profil(["node", "python"], node="22.11.0", python="3.12.4"))["image"],
                         "myiafactory/tests")
        self.assertEqual(tests_images.choisir_image(profil([]))["image"], "myiafactory/tests")      # pile inconnue : l'image par défaut
        ancien = tests_images.choisir_image(profil(["node"], node="18.19.0"))
        self.assertEqual((ancien["derivee"], ancien["image"]), (True, None))
        self.assertTrue(tests_images.choisir_image(profil(["python"], python="3.11"))["derivee"])
        self.assertTrue(tests_images.choisir_image(profil(["dotnet"], dotnet="8.0"))["derivee"])
        sdk = {"platforms": ["android-35", "android-36"], "build_tools": ["34.0.0", "36.0.0"]}
        android = tests_images.choisir_image(profil(["gradle-android"], **FRIDGE), sdk)
        self.assertEqual((android["image"], android["capacites"], android["derivee"], android["manque"]),
                         ("myiafactory/tests-android", ["tests-android"], False, []))
        jvm = tests_images.choisir_image(profil(["gradle-jvm"], jdk="21", gradle="8.7"))
        self.assertEqual(jvm["image"], "myiafactory/tests-android")
        self.assertTrue(tests_images.choisir_image(profil(["gradle-jvm"], jdk="11"))["derivee"])
        court = tests_images.choisir_image(profil(["gradle-android"], **FRIDGE), {"platforms": ["android-34"], "build_tools": ["34.0.0"]})
        self.assertEqual((court["image"], court["manque"]),
                         ("myiafactory/tests-android", ["platforms;android-36", "build-tools;36.0.0"]))
        self.assertEqual(tests_images.choisir_image(profil(["gradle-android"], **FRIDGE))["manque"], [])   # SDK non relevé
        self.assertNotIn("myiafactory/android", tests_images.CATALOGUE_IMAGES)
        self.assertEqual(set(tests_images.CATALOGUE_IMAGES), {"myiafactory/tests", "myiafactory/tests-android"})

    def test_non_deportable_de_la_commande_seulement(self):
        with tempfile.TemporaryDirectory() as t:
            r = Path(t)
            (r / "package.json").write_text('{"scripts": {"test": "jest"}}', encoding="utf-8")
            (r / "ios").mkdir()
            (r / "ios" / "Podfile").write_text("platform :ios\n", encoding="utf-8")
            (r / "ios" / "App.xcodeproj").mkdir()
            tout = tests_profil.analyser(str(r))
            self.assertTrue(tout.non_deportable.startswith("N2"))                    # le projet, lui, reste signalé
            self.assertIsNone(tests_profil.analyser(str(r), lancee=["npx", "jest"]).non_deportable)
            self.assertIsNone(tests_profil.analyser(str(r), lancee=["npm.cmd", "test"]).non_deportable)
            self.assertTrue(tests_profil.analyser(str(r), lancee=["./run.sh"]).non_deportable.startswith("N2"))   # famille inconnue
            self.assertTrue(tests_profil.analyser(str(r), lancee=["xcodebuild", "test"]).non_deportable.startswith("N2"))
        with tempfile.TemporaryDirectory() as t:
            r = Path(t)
            (r / "App.csproj").write_text("<Project><PropertyGroup><UseWPF>true</UseWPF></PropertyGroup></Project>", encoding="utf-8")
            (r / "package.json").write_text("{}", encoding="utf-8")
            self.assertTrue(tests_profil.analyser(str(r), lancee=["dotnet", "test"]).non_deportable.startswith("N1"))
            self.assertIsNone(tests_profil.analyser(str(r), lancee=["npm", "test"]).non_deportable)

    def test_choix_de_la_route(self):
        self.assertEqual(tests_serveur._image_de_la_campagne(profil(["python"], python="3.12"), None),
                         (None, None, ("tests-image",)))                           # ligne de commande d'avant
        tests_images.CACHE_GRADLE_PRET = True
        try:
            self.assertEqual(tests_serveur._image_de_la_campagne(profil(["gradle-android"], **FRIDGE), None),
                             ("myiafactory/tests-android", "gradle-android", ("tests-android",)))
            for p, sdk in ((profil(["node"], node="18"), None),
                           (profil(["gradle-android"], **FRIDGE), {"platforms": ["android-34"], "build_tools": ["34.0.0"]})):
                with self.assertRaises(tests_serveur.Repli):
                    tests_serveur._image_de_la_campagne(p, sdk)
        finally:
            tests_images.CACHE_GRADLE_PRET = False

    def test_gradle_se_replie_tant_que_le_cache_n_existe_pas(self):
        self.assertFalse(tests_images.CACHE_GRADLE_PRET)                              # 14d le passera à vrai
        for p in (profil(["gradle-android"], **FRIDGE), profil(["gradle-jvm"], jdk="17")):
            with self.assertRaises(tests_serveur.Repli) as e:
                tests_serveur._image_de_la_campagne(p, None)
            self.assertIn("cache Gradle du serveur pas encore préparé : 14d", e.exception.raison)
        self.assertEqual(tests_images.choisir_image(profil(["gradle-android"], **FRIDGE))["image"], "myiafactory/tests-android")
        tests_images.CACHE_GRADLE_PRET = True
        try:
            self.assertEqual(tests_serveur._image_de_la_campagne(profil(["gradle-jvm"], jdk="17"), None)[1], "gradle-jvm")
        finally:
            tests_images.CACHE_GRADLE_PRET = False

    def test_route_refuse_seulement_la_commande_concernee(self):
        refus = "N2 : macOS ou iOS (Xcode)"
        for commande, attendu in ((["npx", "jest"], None), (["xcodebuild", "test"], refus)):
            vu = {}

            def analyse(racine, **kw):
                vu.update(kw)
                return tests_profil.Profil(familles=("node",), non_deportable=refus if kw["lancee"][0] == "xcodebuild" else None)
            try:
                tests_serveur._profil_de_la_campagne(analyse, "/x", commande)
                resultat = None
            except tests_serveur.Repli as e:
                resultat = e.raison
            self.assertEqual(vu["lancee"], commande)
            self.assertEqual(resultat is None, attendu is None)


class TestEnveloppe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.racine = Path(cls._t.name)
        cls.bin = cls.racine / "bin"
        cls.bin.mkdir()
        for nom, corps in banc.FAUX.items():
            (cls.bin / nom).write_text("#!/bin/sh\n" + corps + "\n", newline="\n")
            (cls.bin / nom).chmod(0o755)
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def lancer(self, *supplement, sdk=True, deps="-"):
        """(code, lignes de la sortie d'erreur, arguments de `docker run` ou None)."""
        type(self).n += 1
        t = self.racine / f"c{self.n}"
        home = t / "home"
        entree = home / "tests" / banc.ID / "entree"
        entree.mkdir(parents=True)
        (entree / "entree.tar").write_bytes(banc._instantane())
        if sdk:
            (home / "android-sdk").mkdir()
        if deps != "-":
            (home / "tests" / ".deps" / "projet-a" / deps).mkdir(parents=True)
        etat = t / "etat" / banc.ID
        etat.mkdir(parents=True)
        env = dict(os.environ, HOME=banc._msys(home), PATH=self.bin.as_posix() + os.pathsep + os.environ["PATH"],
                   FAUX_JOURNAL=(t / "appels.txt").as_posix(), ENVELOPPE_SONDE_S="0.2", FAUX_ORDRE=(t / "ordre").as_posix(),
                   FAUX_ETAT=etat.as_posix())
        args = ["bash", banc.SCRIPT.as_posix(), banc.ID, "2", "4", "8192", "1800", "projet-a", deps, *supplement]
        with open(t / "err", "w+b") as err:
            p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err, env=env)
            try:
                p.stdin.write((banc.COMMANDE + "\n").encode())
                p.stdin.flush()
            except OSError:
                pass
            try:
                code = p.wait(timeout=60)
            finally:
                if p.poll() is None:
                    p.kill()
                p.stdin.close()
            err.seek(0)
            lignes = err.read().decode("utf-8", "replace").split("\n")
        fichier = etat / f"run-tests-{banc.ID}.txt"
        run = fichier.read_text(encoding="utf-8").replace(banc._msys(home), "$H").split("\n") if fichier.exists() else None
        return code, lignes, run, t

    def test_enveloppe_image_et_famille(self):
        for refus in (("myiafactory/android",), ("myiafactory/tests-" + "a" * 25,), ("myiafactory/tests;id",),
                      ("myiafactory/tests", "python;id"), ("myiafactory/tests", "python node"),
                      ("myiafactory/tests", "inconnue"), ("myiafactory/tests", "python", "extra")):
            code, lignes, run, t = self.lancer("10", *refus)
            self.assertEqual(code, 2, refus)
            self.assertIn("#refus 2", lignes, refus)
            self.assertIsNone(run)
            self.assertTrue((t / "home" / "tests" / banc.ID / "entree" / "entree.tar").exists())      # rien n'a été effacé
        # sans les deux arguments : celui d'avant ; avec les valeurs par défaut : le même conteneur
        code, _l, ancien, _t = self.lancer()
        self.assertEqual(code, 0)
        code, _l, defaut, _t = self.lancer("10", "myiafactory/tests", "python")
        self.assertEqual(code, 0)
        self.assertEqual(ancien, defaut)
        self.assertEqual(ancien[-2], "myiafactory/tests")                          # l image est le dernier argument (puis le vide final)
        self.assertNotIn("/opt/android-sdk", " ".join(ancien))
        # gradle-android : SDK de l'hôte en lecture seule, variables fermées ; durcissements gardés
        code, _l, run, t = self.lancer("10", "myiafactory/tests-android", "gradle-android")
        self.assertEqual(code, 0)
        self.assertIn("$H/android-sdk:/opt/android-sdk:ro", run)
        self.assertEqual(run[-2], "myiafactory/tests-android")
        self.assertIn("ANDROID_HOME=/opt/android-sdk", run)
        self.assertTrue(any(a.startswith("GRADLE_OPTS=") for a in run))
        self.assertIn("GRADLE_USER_HOME=/tmp/gradle", run)                           # inscriptible (tmpfs), jamais /deps
        self.assertFalse(any(a.startswith("GRADLE_RO_DEP_CACHE") for a in run))      # pas de cache monté
        for garde in ("--network", "none", "--read-only", "--cap-drop", "ALL", "--user", "1000:1000", "no-new-privileges"):
            self.assertIn(garde, run)
        code, lignes, run, _t = self.lancer("10", "myiafactory/tests-android", "gradle-android", sdk=False)      # SDK absent
        self.assertEqual((code, run), (77, None))
        self.assertIn("#refus 77", lignes)
        code, _l, run, _t = self.lancer("10", "myiafactory/tests-android", "gradle-jvm")
        self.assertEqual(code, 0)
        self.assertNotIn("/opt/android-sdk", " ".join(run))
        self.assertTrue(any(a.startswith("GRADLE_OPTS=") for a in run))
        code, _l, run, _t = self.lancer("10", "myiafactory/tests-android", "gradle-jvm", deps=banc.DEPS)   # cache monté en :ro
        self.assertEqual(code, 0)
        self.assertIn("GRADLE_RO_DEP_CACHE=/deps", run)
        self.assertIn("GRADLE_USER_HOME=/tmp/gradle", run)
        self.assertTrue(any(a.endswith("/.deps/projet-a/%s:/deps:ro" % banc.DEPS) for a in run))

    @unittest.skipUnless(shutil.which("bash"), "bash absent")
    def test_etape_simulee(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "bin").mkdir()
            (t / "bin" / "docker").write_text('#!/bin/sh\necho "docker $*" >> "%s"\nexit 0\n' % (t / "appels").as_posix(), newline="\n")
            (t / "bin" / "docker").chmod(0o755)
            sortie = subprocess.run(
                ["bash", (RACINE / "serveur_ovh" / "mise_en_place.sh").as_posix(), "--etape", "tests_android_image", "--simuler"],
                capture_output=True, text=True, env=dict(os.environ, HOME=banc._msys(t), PATH=(t / "bin").as_posix() + os.pathsep + os.environ["PATH"]),
                timeout=60)
            d = json.loads(sortie.stdout)
            self.assertEqual((d["etape"], d["statut"]), ("tests_android_image", "a_faire"))
            self.assertIn("simul", d["detail"].lower())
            self.assertIn("myiafactory/tests-android", d["detail"])
            self.assertFalse((t / "appels").exists())


if __name__ == "__main__":
    unittest.main()
