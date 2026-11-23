"""Les commandes uniques des agents serveur d'un projet Flutter (`analyser-flutter`, `tester-flutter`, `construire-apk`) :
le script `serveur_ovh/agent-outils/outil-flutter.sh` (faux `flutter`, arguments hostiles refusés), son dépôt par le poste,
son montage en lecture seule sur /opt/outils par l'enveloppe (faux docker), le dossier Flutter transmis par la demande."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_serveur_agent_script import Banc, ID, suite_dans
from tests import test_serveur_flutter as tsf

RACINE = Path(__file__).resolve().parent.parent
OUTIL = RACINE / "serveur_ovh" / "agent-outils" / "outil-flutter.sh"
NOMS = ("analyser-flutter", "tester-flutter", "construire-apk")
sys.path.insert(0, str(RACINE / "outils"))
import serveur_agent as sa  # noqa: E402
from tests.test_serveur_agent import Base, ID1, declarer, CAPS_AGENT  # noqa: E402

FAUX_FLUTTER = r'''#!/bin/sh
printf 'flutter %s | %s\n' "$*" "$(pwd -P)" >> "$FAUX_JOURNAL"
if [ "$1" = pub ] && [ "$2" = get ]; then mkdir -p .dart_tool && : > .dart_tool/package_config.json; fi
exit "${FAUX_CODE:-0}"
'''


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestOutilFlutter(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        t = self.t = Path(self._t.name)
        self.bin, self.outils, self.projet = t / "bin", t / "outils", t / "projet"
        for d in (self.bin, self.outils, self.projet / "android_app"):
            d.mkdir(parents=True)
        (self.projet / "android_app" / "pubspec.yaml").write_text("name: x\n", newline="\n")
        (self.bin / "flutter").write_text(FAUX_FLUTTER, newline="\n")
        (self.bin / "flutter").chmod(0o755)
        for nom in NOMS + ("autre-nom",):                  # le même fichier sous chaque nom, comme les montages
            shutil.copy(OUTIL, self.outils / nom)
            (self.outils / nom).chmod(0o755)
        self.conf = t / "dossier-flutter"
        self.conf.write_text("android_app\n", newline="\n")
        self.journal_fichier = t / "appels.txt"

    def lancer(self, nom, *args, **env):
        e = dict(os.environ, PATH=self.bin.as_posix() + os.pathsep + os.environ["PATH"],
                 FAUX_JOURNAL=self.journal_fichier.as_posix(), OUTIL_FLUTTER_RACINE=self.projet.as_posix(),
                 OUTIL_FLUTTER_CONF=self.conf.as_posix(), **env)
        return subprocess.run(["bash", (self.outils / nom).as_posix(), *args], capture_output=True, text=True,
                              encoding="utf-8", env=e, timeout=60, stdin=subprocess.DEVNULL)

    @property
    def appels(self):
        return self.journal_fichier.read_text(encoding="utf-8").splitlines() if self.journal_fichier.exists() else []

    def test_syntaxe_et_valeurs_figees(self):
        self.assertEqual(subprocess.run(["bash", "-n", OUTIL.as_posix()], capture_output=True).returncode, 0)
        texte = OUTIL.read_text(encoding="utf-8")
        self.assertTrue(texte.startswith("#!/bin/bash\n"))
        self.assertIn("set -u", texte)
        self.assertNotIn(b"\r", OUTIL.read_bytes())
        self.assertNotIn("eval", texte)

    def test_chaque_commande_fait_son_etape_dans_le_dossier_flutter(self):
        for nom, attendu in (("analyser-flutter", "flutter analyze"), ("tester-flutter", "flutter test"),
                             ("construire-apk", "flutter build apk --release")):
            with self.subTest(nom=nom):
                shutil.rmtree(self.projet / "android_app" / ".dart_tool", ignore_errors=True)
                self.journal_fichier.unlink(missing_ok=True)
                r = self.lancer(nom)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual([x.split(" | ")[0] for x in self.appels], ["flutter pub get", attendu])
                self.assertTrue(all(x.endswith("/android_app") for x in self.appels), self.appels)
        r = self.lancer("construire-apk", "debug")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.appels[-1].split(" | ")[0], "flutter build apk --debug")

    def test_pub_get_seulement_si_necessaire(self):
        self.assertEqual(self.lancer("analyser-flutter").returncode, 0)
        self.journal_fichier.unlink()
        self.assertEqual(self.lancer("tester-flutter").returncode, 0)
        self.assertEqual([x.split(" | ")[0] for x in self.appels], ["flutter test"])

    def test_code_de_flutter_rendu(self):
        r = self.lancer("tester-flutter", FAUX_CODE="1")
        self.assertNotEqual(r.returncode, 0)

    def test_arguments_hostiles_refuses_sans_rien_lancer(self):
        for nom, args in (("analyser-flutter", ["--foo"]), ("tester-flutter", ["x"]), ("tester-flutter", ["test/a_test.dart"]),
                          ("construire-apk", ["profile"]), ("construire-apk", ["release; rm -rf /"]),
                          ("construire-apk", ["release", "debug"]), ("construire-apk", ["--release"]),
                          ("construire-apk", [""]), ("autre-nom", [])):
            with self.subTest(nom=nom, args=args):
                r = self.lancer(nom, *args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(self.appels, [])

    def test_dossier_flutter_hostile_ou_absent_refuse(self):
        for contenu in ("../x\n", "/etc\n", "a b\n", "..\n", "android_app/../..\n", "\n"):
            with self.subTest(contenu=contenu):
                self.conf.write_text(contenu, newline="\n")
                r = self.lancer("analyser-flutter")
                self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
                self.assertEqual(self.appels, [])
        self.conf.unlink()
        self.assertEqual(self.lancer("analyser-flutter").returncode, 3)
        self.conf.write_text("absent\n", newline="\n")
        self.assertEqual(self.lancer("analyser-flutter").returncode, 3)
        self.assertEqual(self.appels, [])

    def test_racine_du_projet_acceptee(self):
        (self.projet / "pubspec.yaml").write_text("name: x\n", newline="\n")
        self.conf.write_text(".\n", newline="\n")
        self.assertEqual(self.lancer("analyser-flutter").returncode, 0)
        self.assertTrue(self.appels[-1].endswith("/projet"), self.appels)


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEnveloppeOutils(unittest.TestCase):
    sdk = tsf.TestEnveloppeFlutter.__dict__["sdk"]

    def test_outils_montes_en_lecture_seule_et_path(self):
        with Banc() as b:
            self.sdk(b)
            b.ecrire_entree(flutter=True, flutter_dossier="android_app")
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            a = b.run_args()
            outil = (RACINE / "serveur_ovh" / "agent-outils" / "outil-flutter.sh").as_posix()
            texte = " ".join(a)
            for nom in NOMS:
                self.assertIn(f"dst=/opt/outils/{nom},readonly", texte)
            self.assertIn(f"type=bind,src={b.h()}/taches/{ID}/dossier-flutter,dst=/opt/outils/dossier-flutter,readonly", texte)
            self.assertEqual((b.dossier / "dossier-flutter").read_text(encoding="utf-8"), "android_app\n")
            env = [a[i + 1] for i in range(len(a) - 1) if a[i] == "-e"]
            self.assertIn("PATH=/opt/outils:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", env)
            self.assertTrue(outil)
            b.arreter()
            b.attendre_final()

    def test_dossier_hostile_refuse(self):
        for valeur in ("../x", "a b", "/etc", ".."):
            with self.subTest(valeur=valeur), Banc() as b:
                self.sdk(b)
                b.ecrire_entree(flutter=True, flutter_dossier=valeur)
                r = b.lancer("seul", "30", "2048", "2", "2")
                self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
                self.assertEqual(b.appels("docker run"), [])
                self.assertIn("flutter_dossier", b.etat()["raison"])

    def test_sans_dossier_pas_de_conf(self):
        with Banc() as b:
            self.sdk(b)
            b.ecrire_entree(flutter=True)
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertNotIn("dossier-flutter", " ".join(b.run_args()))
            b.arreter()
            b.attendre_final()

    def test_projet_non_flutter_sans_outils(self):
        with Banc() as b:
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertNotIn("/opt/outils", " ".join(b.run_args()))
            b.arreter()
            b.attendre_final()


class TestDemandeEtDepot(Base):
    def test_dossier_flutter_motif_strict(self):
        self.assertEqual(self.demande(flutter=True, flutter_dossier="android_app").flutter_dossier, "android_app")
        self.assertEqual(self.demande(flutter=True, flutter_dossier=".").flutter_dossier, ".")
        self.assertIsNone(self.demande(flutter=True).flutter_dossier)
        for mauvais in ("..", "../x", "a/b", "a b", "/etc", "", "x" * 101, 3, ".cache"):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                self.demande(flutter=True, flutter_dossier=mauvais)
        with self.assertRaises(ValueError):                       # sans projet Flutter, aucun dossier Flutter
            self.demande(flutter_dossier="android_app")

    def test_demande_json_et_outils_deposes(self):
        declarer(self.dossier, [("ovh1", {**CAPS_AGENT, "flutter-sdk": "presente"})])
        self.lancer(self.demande(flutter=True, flutter_dossier="android_app"))
        texte = self.srv.entrees[ID1]["entree/demande.json"].decode("utf-8")
        self.assertEqual(json.loads(texte)["flutter_dossier"], "android_app")
        self.assertEqual(texte.count('"flutter_dossier":'), 1)
        # un script depose au serveur est toujours en LF, meme si la copie de travail (Windows) est en CRLF
        self.assertEqual(self.srv.deposes["agent-outils/outil-flutter.sh"],
                         OUTIL.read_bytes().replace(bytes([13, 10]), bytes([10])))
        self.assertNotIn(bytes([13]), self.srv.deposes["agent-outils/outil-flutter.sh"])

    def test_projet_ordinaire_sans_outils_deposes(self):
        self.lancer()
        self.assertNotIn("agent-outils/outil-flutter.sh", self.srv.deposes)

    def test_executeur_transmet_le_dossier(self):
        from moteur import executeur_serveur as es
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            self.assertIsNone(es._dossier_flutter(p))
            (p / "android_app").mkdir()
            (p / "android_app" / "pubspec.yaml").write_text("dependencies:\n  flutter:\n    sdk: flutter\n", encoding="utf-8")
            self.assertEqual(es._dossier_flutter(p), "android_app")
            (p / "mal nommé").mkdir()
            (p / "android_app" / "pubspec.yaml").unlink()
            (p / "mal nommé" / "pubspec.yaml").write_text("dependencies:\n  flutter:\n    sdk: flutter\n", encoding="utf-8")
            self.assertIsNone(es._dossier_flutter(p))              # hors motif : non transmis
            self.assertIs(es._projet_flutter(p), True)


class TestMemoireFlutter(Base):
    """Un build APK (démons Gradle et Kotlin, gen_snapshot, flutter) dépasse 4 Go : 12 Go et 4 processeurs pour un projet
    Flutter, les autres projets gardent 4096 Mo et 2."""

    def test_limites_par_defaut_selon_le_projet(self):
        self.assertEqual((sa.LIMITES_AGENT["memoire_mo"], sa.LIMITES_AGENT["cpus"]), (4096, 2))
        self.assertEqual((sa.LIMITES_AGENT_FLUTTER["memoire_mo"], sa.LIMITES_AGENT_FLUTTER["cpus"]), (12288, 4))
        d = self.demande(flutter=True)
        self.assertEqual((d.limites["memoire_mo"], d.limites["cpus"]), (12288, 4))
        d = self.demande()
        self.assertEqual((d.limites["memoire_mo"], d.limites["cpus"]), (4096, 2))
        with self.assertRaises(ValueError):                           # le plafond Flutter ne vaut que pour Flutter
            self.demande(limites={"memoire_mo": 12288})
        self.assertEqual(self.demande(flutter=True, limites={"memoire_mo": 8192}).limites["memoire_mo"], 8192)
        with self.assertRaises(ValueError):
            self.demande(flutter=True, limites={"memoire_mo": 12289})

    def test_ligne_de_lancement(self):
        declarer(self.dossier, [("ovh1", {**CAPS_AGENT, "flutter-sdk": "presente"})])
        self.lancer(self.demande(flutter=True, flutter_dossier="android_app"))
        self.assertIn(f'lancer_agent.sh" {ID1} seul 2400 12288 4 2\n', self.srv.ops("lancer_agent")[0][1])

    def test_ligne_de_lancement_ordinaire(self):
        self.lancer()
        self.assertIn(f'lancer_agent.sh" {ID1} seul 2400 4096 2 2\n', self.srv.ops("lancer_agent")[0][1])


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestPlafondTravailFlutter(unittest.TestCase):
    sdk = tsf.TestEnveloppeFlutter.__dict__["sdk"]

    def test_docker_run_porte_la_memoire_flutter(self):
        with Banc() as b:
            self.sdk(b)
            b.ecrire_entree(flutter=True)
            r = b.lancer("seul", "30", "12288", "4", "2")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            a = b.run_args()
            suite_dans(self, a, "--memory", "12288m")
            suite_dans(self, a, "--memory-swap", "12288m")
            suite_dans(self, a, "--cpus", "4")
            b.arreter()
            b.attendre_final()

    def test_plafond_travail_releve_pour_flutter(self):
        texte = (RACINE / "serveur_ovh" / "taches" / "lancer_agent.sh").read_text(encoding="utf-8")
        self.assertIn("TRAVAIL_MAX_KO=8388608", texte)                 # 8 Go : projets ordinaires, inchangé
        self.assertIn("TRAVAIL_FLUTTER_MAX_KO=16777216", texte)        # 16 Go : Flutter (Gradle, couches des SDK)
        with Banc(ENVELOPPE_TRAVAIL_MAX_KO="1", ENVELOPPE_DU_TRAVAIL_S="1") as b:
            self.sdk(b)
            b.ecrire_entree(flutter=True)
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            (b.dossier / "maison" / "gros").write_bytes(b"x" * 4096)
            e = b.attendre_final()
            self.assertEqual(e["statut"], "limite")                     # le réglage des tests vaut aussi pour Flutter


class TestConsigne(unittest.TestCase):
    def test_la_consigne_cite_les_commandes_uniques(self):
        from orchestrateur import depart
        c = depart.consigne_serveur("seul", "t7", flutter=True)
        for nom in NOMS:
            self.assertIn(f"`{nom}`", c)
        self.assertIn("`construire-apk debug`", c)


if __name__ == "__main__":
    unittest.main()
