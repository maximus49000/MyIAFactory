"""« Release signé » (tâche 15d) : le serveur construit la release NON signée (`construire-apk` quand le projet signe au poste :
script d'init Gradle qui retire la signature de la release, APK renommé `app-release-unsigned.apk`, dans les sorties que
le rapatriement accepte), l'enveloppe transmet le choix de signature en lecture seule, la signature se fait au poste
(`signer-release --dossier`), et l'action « Release signé » du catalogue n'est jamais lancée par `deporter`."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_serveur_agent_script import Banc, ID
from tests import test_serveur_flutter as tsf

RACINE = Path(__file__).resolve().parent.parent
OUTIL = RACINE / "serveur_ovh" / "agent-outils" / "outil-flutter.sh"
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
import serveur_livrables  # noqa: E402
import signature_locale as sl  # noqa: E402
from bureau import deport, deport_types  # noqa: E402

INIT = "init.d/myiafactory-release-non-signee.gradle"
# Un faux `flutter` : `build apk --release` note si le script d'init est présent, puis pose les sorties qu'AGP et le greffon
# Flutter produisent sans signature (`apk/release/app-release-unsigned.apk`, copie `flutter-apk/app-release.apk` + .sha1).
FAUX_FLUTTER = r'''#!/bin/sh
init="$GRADLE_USER_HOME/init.d/myiafactory-release-non-signee.gradle"
if [ -f "$init" ]; then etat=init; else etat=sans-init; fi
printf 'flutter %s | %s\n' "$*" "$etat" >> "$FAUX_JOURNAL"
if [ "$1" = pub ]; then mkdir -p .dart_tool && : > .dart_tool/package_config.json; exit 0; fi
if [ "$1 $2 $3" = "build apk --release" ] && [ -z "${FAUX_SANS_APK:-}" ]; then
  mkdir -p build/app/outputs/apk/release build/app/outputs/flutter-apk
  if [ -f "$init" ]; then n=app-release-unsigned.apk; else n=app-release.apk; fi
  printf 'apk' > "build/app/outputs/apk/release/$n"
  printf 'apk' > build/app/outputs/flutter-apk/app-release.apk
  printf 'sha' > build/app/outputs/flutter-apk/app-release.apk.sha1
fi
exit "${FAUX_CODE:-0}"
'''


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class ConstruireApkNonSigne(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        t = Path(self._t.name)
        self.bin, self.outils, self.projet, self.gradle = t / "bin", t / "outils", t / "projet", t / "gradle"
        for d in (self.bin, self.outils, self.projet / "app", self.gradle):
            d.mkdir(parents=True)
        (self.projet / "app" / "pubspec.yaml").write_text("name: x\n", newline="\n")
        (self.bin / "flutter").write_text(FAUX_FLUTTER, newline="\n")
        (self.bin / "flutter").chmod(0o755)
        shutil.copy(OUTIL, self.outils / "construire-apk")
        (self.outils / "construire-apk").chmod(0o755)
        self.conf = t / "dossier-flutter"
        self.conf.write_text("app\n", newline="\n")
        self.signature = t / "signature"
        self.journal = t / "appels.txt"
        self.sorties = self.projet / "app" / "build" / "app" / "outputs"

    def lancer(self, *args, signature=None, **env):
        if signature is not None:
            self.signature.write_text(signature + "\n", newline="\n")
        e = dict(os.environ, PATH=self.bin.as_posix() + os.pathsep + os.environ["PATH"], FAUX_JOURNAL=self.journal.as_posix(),
                 OUTIL_FLUTTER_RACINE=self.projet.as_posix(), OUTIL_FLUTTER_CONF=self.conf.as_posix(),
                 OUTIL_FLUTTER_SIGNATURE=self.signature.as_posix(), GRADLE_USER_HOME=self.gradle.as_posix(),
                 OUTIL_FLUTTER_NUMERO="777", **env)
        return subprocess.run(["bash", (self.outils / "construire-apk").as_posix(), *args], capture_output=True, text=True,
                              encoding="utf-8", env=e, timeout=60, stdin=subprocess.DEVNULL)

    def appels(self):
        return self.journal.read_text(encoding="utf-8").splitlines() if self.journal.exists() else []

    def test_poste_signe_release_non_signee_dans_les_sorties_rapatriables(self):
        r = self.lancer(signature="poste_signe")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.appels()[-1], "flutter build apk --release --build-number=777 | init")       # la signature retirée par Gradle
        self.assertFalse((self.gradle / INIT).exists())                                  # jamais laissé pour la suite
        apk = self.sorties / "flutter-apk" / "app-release-unsigned.apk"
        self.assertTrue(apk.is_file())
        self.assertFalse((self.sorties / "flutter-apk" / "app-release.apk").exists())   # jamais un nom de release signée
        self.assertFalse((self.sorties / "flutter-apk" / "app-release.apk.sha1").exists())
        self.assertIn("NON signée", r.stdout)
        self.assertIn("signer-release", r.stdout)
        # le livrable déclaré passe la validation du rapatriement (sorties Android, extension .apk)
        chemin = "app/build/app/outputs/flutter-apk/app-release-unsigned.apk"
        self.assertEqual(serveur_livrables.valider_chemin(chemin), (chemin, None))

    def test_sans_choix_poste_signe_rien_ne_change(self):
        for signature in (None, "aucune", "debug_serveur"):
            with self.subTest(signature=signature):
                shutil.rmtree(self.sorties.parent.parent, ignore_errors=True)
                self.signature.unlink(missing_ok=True)
                r = self.lancer(signature=signature)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(self.appels()[-1], "flutter build apk --release --build-number=777 | sans-init")
                self.assertTrue((self.sorties / "flutter-apk" / "app-release.apk").is_file())
                self.assertFalse((self.sorties / "flutter-apk" / "app-release-unsigned.apk").exists())

    def test_debug_jamais_touche(self):
        r = self.lancer("debug", signature="poste_signe")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.appels()[-1], "flutter build apk --debug --build-number=777 | sans-init")

    def test_choix_hostile_refuse_sans_rien_lancer(self):
        for valeur in ("release", "poste_signe; rm -rf /", "../x", ""):
            with self.subTest(valeur=valeur):
                r = self.lancer(signature=valeur)
                self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
                self.assertEqual(self.appels(), [])

    def test_echec_de_flutter_rendu_et_script_retire(self):
        r = self.lancer(signature="poste_signe", FAUX_CODE="1", FAUX_SANS_APK="1")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.gradle / INIT).exists())

    def test_script_d_init_ferme(self):
        texte = OUTIL.read_text(encoding="utf-8")
        self.assertIn("finalizeDsl", texte)
        self.assertIn("signingConfig = null", texte)
        self.assertEqual(subprocess.run(["bash", "-n", OUTIL.as_posix()], capture_output=True).returncode, 0)


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class Enveloppe(unittest.TestCase):
    sdk = tsf.TestEnveloppeFlutter.__dict__["sdk"]

    def test_choix_de_signature_transmis_en_lecture_seule(self):
        for signature, attendu in ((None, "aucune"), ("poste_signe", "poste_signe")):
            with self.subTest(signature=signature), Banc() as b:
                self.sdk(b)
                b.ecrire_entree(flutter=True, flutter_dossier="app", **({"signature": signature} if signature else {}))
                r = b.lancer("seul", "30", "2048", "2", "2")
                self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
                self.assertIn(f"type=bind,src={b.h()}/taches/{ID}/signature,dst=/opt/outils/signature,readonly",
                              " ".join(b.run_args()))
                self.assertEqual((b.dossier / "signature").read_text(encoding="utf-8"), attendu + "\n")


class SignatureAuPoste(unittest.TestCase):
    def test_dossier_au_lieu_de_l_artefact(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            apk = d / "app" / "build" / "app" / "outputs" / "flutter-apk" / "app-release-unsigned.apk"
            apk.parent.mkdir(parents=True)
            apk.write_bytes(b"apk")
            (d / "coffre.jks").write_bytes(b"k")
            appels = []

            def executer(argv, **kw):
                appels.append(argv)
                if "--out" in argv:
                    Path(argv[argv.index("--out") + 1]).write_bytes(b"signe")
                if argv[0].endswith("zipalign"):
                    Path(argv[-1]).write_bytes(b"aligne")
                return subprocess.CompletedProcess(argv, 0, b"", b"")
            code = sl.main(["--dossier", str(d), "--keystore", str(d / "coffre.jks"), "--alias", "cle",
                            "--sortie", str(d / "signe.apk")], saisir=lambda _q: "secret", interactif=True,
                           executer=executer, outils={"zipalign": "zipalign", "apksigner": "apksigner"})
            self.assertEqual(code, 0)
            self.assertIn(str(apk), appels[0])
            self.assertEqual((d / "signe.apk").read_bytes(), b"signe")
            # jamais l'un et l'autre, jamais sans l'un des deux
            for argv in (["--keystore", "k", "--alias", "a", "--sortie", "s"],
                         ["--dossier", str(d), "--artefact", str(apk), "--keystore", "k", "--alias", "a", "--sortie", "s"]):
                self.assertEqual(sl.main(argv, saisir=lambda _q: "x", interactif=True), 2)


class Catalogue(unittest.TestCase):
    def test_action_release_signe_au_serveur(self):
        e = deport_types.ANDROID["release-signe"]
        self.assertEqual(e["libelle"], "Release signé")
        self.assertEqual(e["lieux"], ["serveur"])
        self.assertTrue(deport_types.sans_poste(e))
        self.assertEqual(deport.valider_lieux({"release-signe": "serveur"}, catalogue=deport_types.ANDROID),
                         {"release-signe": "serveur"})
        self.assertIn("release-signe", [x["id"] for x in deport_types.actions_exposees(deport_types.ANDROID)])

    def test_deporter_ne_signe_jamais_et_dit_la_procedure(self):
        import deporter
        with tempfile.TemporaryDirectory() as d:
            Path(d, ".factory").mkdir()
            Path(d, ".factory", "factory.json").write_text('{"genre": "application-mobile-android"}', encoding="utf-8")
            import io
            from contextlib import redirect_stderr
            erreur = io.StringIO()
            with redirect_stderr(erreur):
                code = deporter.main(["release-signe", "--dossier", d], bureau=Path(d) / "bureau.json")
        self.assertEqual(code, 2)
        self.assertIn("signer-release", erreur.getvalue())
        self.assertIn("construire-apk", erreur.getvalue())


if __name__ == "__main__":
    unittest.main()
