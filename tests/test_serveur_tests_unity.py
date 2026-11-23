"""Exécuteurs de l'enveloppe et Unity en conteneur (conception § 5.16 option B, tâche 14g). CODE SENSIBLE : une licence Unity
est montée en lecture seule dans un conteneur qui exécute du code du projet.

Aucune vraie licence ici : des valeurs factices (`LICENCE-FACTICE-1`) dans un HOME temporaire. L'enveloppe
(`serveur_ovh/taches/lancer_tests.sh`) tourne avec le banc de `test_serveur_tests_deps` (bash du poste, faux `docker`, `sudo`,
`timeout`, `df`, `flock`) ; l'entrée du conteneur (`entree-tests.sh` puis `entree-unity.sh`) tourne avec le bash du poste, ses
chemins sous ENTREE_TESTS_RACINE et un faux `unity-editor` qui écrit le journal et le XML choisis par le test ; le ramassage
(`construire_image_tests.sh --ramasser`) avec le faux `docker` de `test_tests_images_derivees`."""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import io
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_serveur_tests_deps as D  # noqa: E402
import test_serveur_tests_enveloppe as E  # noqa: E402
import test_tests_images_derivees as TI  # noqa: E402
import tests_images  # noqa: E402
import tests_serveur  # noqa: E402
from tests_profil import Profil  # noqa: E402

ID, ID_B = E.ID, E.ID_B
VERSION = "6000.6.7f1"
IMAGE_UNITY = f"myiafactory/tests-unity-{VERSION}"
DIGEST = "sha256:" + "b" * 64
FACTICE = "LICENCE-FACTICE-1"
# 8e à 14e (14e : budget_unites) pour la famille unity : sans cache de dépendances (deps « - »), échauffement « - ».
UNITY_14 = ("10", IMAGE_UNITY, "unity", "-", "refuse", "40", "16")
NODE_14 = ("10", "myiafactory/tests", "node", "-", "refuse", "40", "16")
COMMANDE_UNITY = ["unity-editor", "-batchmode", "-nographics", "-projectPath", "/work", "-runTests", "-testPlatform",
                  "EditMode", "-testResults", "/tmp/resultats.xml", "-logFile", "/tmp/unity.log"]
INTERDITS = ("unityhub", ".sock", "/run/user")


def machine_id_presente():
    """/etc/machine-id vu par le bash qui fait tourner l'enveloppe (absent de Git Bash et de certains conteneurs)."""
    return subprocess.run(["bash", "-c", "[ -f /etc/machine-id ] && [ ! -L /etc/machine-id ]"]).returncode == 0


def xml_resultats(total, passed, failed, echecs=()):
    cas = "".join(f'<test-case name="{n.rsplit(".", 1)[-1]}" fullname="{n}" result="Failed"/>' for n in echecs)
    return (f'<?xml version="1.0" encoding="utf-8"?><test-run id="2" testcasecount="{total}" result="Failed" '
            f'total="{total}" passed="{passed}" failed="{failed}" skipped="0"><test-suite type="Assembly" name="Tests">'
            f'{cas}</test-suite></test-run>')


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEnveloppeUnity(D.Banc):
    def setUp(self):
        D.Banc.setUp(self)
        self.droits = self.home / ".config" / "unity3d" / "Unity" / "licenses"
        self.droits.mkdir(parents=True)
        (self.droits / "UnityEntitlementLicense.xml").write_text(FACTICE, encoding="utf-8")
        self.ulf = self.home / ".local" / "share" / "unity3d" / "Unity" / "Unity_lic.ulf"
        self.ulf.parent.mkdir(parents=True)
        self.ulf.write_text(FACTICE, encoding="utf-8")
        hub = self.home / ".config" / "unityhub"                     # session du compte : jamais montée
        hub.mkdir(parents=True)
        (hub / "session.json").write_text(FACTICE, encoding="utf-8")
        self.h = E._msys(self.home)

    def unity(self, *apres, ident=ID, **k):
        return self.lancer(*UNITY_14, *apres, ident=ident, deps="-", commande=json.dumps(COMMANDE_UNITY), **k)

    def arbre(self):
        racine = self.home / "tests"
        return sorted(p.relative_to(racine).as_posix() for p in racine.rglob("*")) if racine.exists() else []

    def docker_args(self):
        return [x for x in self.journal.splitlines() if x.startswith("docker ")]

    def test_sans_executeur_comme_avant(self):
        code, err, etat = self.lancer(*NODE_14, deps="-")
        self.assertEqual(code, 0, err)
        avant = self.run_de(etat, f"tests-{ID}")
        appels_avant = [x.replace(ID, "<id>") for x in self.docker_args()]
        self.journal_fichier.unlink()
        code, err, etat_b = self.lancer(*NODE_14, "conteneur", "-", deps="-", ident=ID_B)
        self.assertEqual(code, 0, err)
        apres = self.run_de(etat_b, f"tests-{ID_B}")
        self.assertEqual([x.replace(ID_B, ID) for x in apres], avant)                  # mêmes arguments de docker run
        self.assertEqual([x.replace(ID_B, "<id>") for x in self.docker_args()], appels_avant)
        self.assertEqual([b for a, b in self.paires(avant) if a == "--network"], ["none"])
        self.assertIn(("--tmpfs", "/tmp:size=4g,mode=1777,exec"), self.paires(avant))
        self.assertFalse([a for a in avant if "licence" in a or "unity" in a.lower()], avant)

    def test_executeur_inconnu_refuse(self):
        avant = self.arbre()
        mauvais = [("docker", "-"), ("-x", "-"), ("conteneur;id", "-"), ("conteneur", "B4"), ("conteneur", "b1"),
                   ("conteneur", "$(id)"), ("conteneur", "-", "x"), ("conteneur", "B1", "licence.unity3d.com"),
                   ("conteneur", "B3", "evil;rm -rf"), ("conteneur", "B3", "-h"), ("conteneur", "B3", "a.b,'c'.d"),
                   ("conteneur", "B3", "a.b\nc.d"), ("conteneur", "B3", "a..b"), ("conteneur", "B3", "UPPER.example"),
                   # I2 : hors de la table fermée des suffixes de licence, adresses IP, dernier libellé non alphabétique
                   ("conteneur", "B3", "169.254.169.254"), ("conteneur", "B3", "172.17.0.1"),
                   ("conteneur", "B3", "attaquant.example"), ("conteneur", "B3", "license.unity3d.com,attaquant.example"),
                   ("conteneur", "B3", "unity3d.com.attaquant.example"), ("conteneur", "B3", "fauxunity3d.com"),
                   ("conteneur", "B3", "license.unity3d.c0m"), ("conteneur", "B3", "::1"),
                   ("conteneur", "B3", ",".join(["a" * 60 + ".unity3d.com"] * 8) + ",x.unity.com")]
        for i, plus in enumerate(mauvais):
            with self.subTest(plus=plus):
                ident = E.ident(i)
                code, err, _ = self.unity(*plus, ident=ident)
                self.assertEqual(code, 2, err)
                self.assertEqual(err[-2], "#refus 2", err)
                self.assertTrue((self.home / "tests" / ident / "entree" / "entree.tar").exists())
                self.assertFalse((self.home / "tests" / ident / "travail").exists())   # rien écrit
        self.assertEqual(self.docker_args(), [])
        # Licence hors famille unity, famille unity sans licence, image Unity hors famille unity : refusés aussi.
        for i, args in enumerate([(*NODE_14, "conteneur", "B1"), (*UNITY_14, "conteneur", "-"), (*UNITY_14,),
                                  ("10", IMAGE_UNITY, "python", "-", "refuse", "40", "16", "conteneur", "B1"),
                                  ("10", "myiafactory/tests", "unity", "-", "refuse", "40", "16", "conteneur", "B1")]):
            with self.subTest(args=args):
                code, err, _ = self.lancer(*args, deps="-", ident=E.ident(30 + i))
                self.assertEqual(code, 2, err)
        self.assertEqual(self.docker_args(), [])

    def test_unity_montages_de_licence_en_lecture_seule(self):
        code, err, etat = self.unity("conteneur", "B1")
        self.assertEqual(code, 0, err)
        run = self.run_de(etat, f"tests-{ID}")
        volumes = [b for a, b in self.paires(run) if a == "-v"]
        self.assertIn(f"{self.h}/.config/unity3d/Unity/licenses:/licence/droits:ro", volumes)
        self.assertIn(f"{self.h}/.local/share/unity3d/Unity/Unity_lic.ulf:/licence/ulf:ro", volumes)
        self.assertEqual([v for v in volumes if "/licence/" in v and not v.endswith(":ro")], [])
        self.assertEqual([b for a, b in self.paires(run) if a == "--network"], ["none"])
        self.assertFalse([a for a in run if "machine-id" in a or a.startswith("--hostname")], run)
        self.assertIn(("--tmpfs", "/tmp:size=6g,mode=1777,exec"), self.paires(run))
        for paire in (("--cap-drop", "ALL"), ("--user", "1000:1000"), ("--security-opt", "no-new-privileges")):
            self.assertIn(paire, self.paires(run))
        self.assertIn("--read-only", run)
        env = [b for a, b in self.paires(run) if a == "-e"]
        self.assertEqual(env, ["MYIAFACTORY_TESTS_FAMILLE=unity", "HOME=/tmp", "MYIAFACTORY_TESTS_CONTENEUR=1"])
        self.assertEqual(run[-1], IMAGE_UNITY)
        self.assertNotIn(FACTICE, self.journal + "\n".join(err))                       # jamais lue ni affichée
        # Sans le .ulf (licence de Hub seule) : seuls les droits ; sans rien : 77, aucun conteneur.
        self.ulf.unlink()
        code, err, etat = self.unity("conteneur", "B1", ident=ID_B)
        self.assertEqual(code, 0, err)
        self.assertFalse([b for a, b in self.paires(self.run_de(etat, f"tests-{ID_B}")) if a == "-v" and "/licence/ulf" in b])
        shutil.rmtree(self.droits)
        code, err, etat = self.unity("conteneur", "B1", ident=E.ident(7))
        self.assertEqual(code, 77, err)
        self.assertIsNone(self.run_de(etat, f"tests-{E.ident(7)}"))

    def test_licence_illisible_code_77(self):
        # M1 : une licence que l'uid du conteneur (celui de l'enveloppe, 1000) ne peut pas lire : 77 explicite, aucun conteneur.
        cible = self.droits / "UnityEntitlementLicense.xml"
        cible.chmod(0o000)
        self.addCleanup(cible.chmod, 0o600)
        if os.access(cible, os.R_OK):
            self.skipTest("droits de fichier sans effet ici (Windows ou root)")
        code, err, etat = self.unity("conteneur", "B1")
        self.assertEqual(code, 77, err)
        self.assertTrue(any("illisible" in x for x in err), err)
        self.assertIsNone(self.run_de(etat, f"tests-{ID}"))

    def test_b2_identifiants_de_machine(self):
        code, err, etat = self.unity("conteneur", "B2")
        run = self.run_de(etat, f"tests-{ID}")
        if not machine_id_presente():
            self.assertEqual(code, 77, err)                                            # jamais un dossier créé par docker -v
            self.assertIsNone(run)
            self.skipTest("/etc/machine-id absent ici : seul le refus 77 est vérifié")
        self.assertEqual(code, 0, err)
        self.assertIn(("-v", "/etc/machine-id:/etc/machine-id:ro"), self.paires(run))
        noms = [b for a, b in self.paires(run) if a == "--hostname"]
        self.assertEqual(len(noms), 1)
        self.assertRegex(noms[0], r"^[A-Za-z0-9][A-Za-z0-9.-]{0,62}$")
        self.assertEqual([b for a, b in self.paires(run) if a == "--network"], ["none"])

    def test_b3_refuse_sans_accord(self):
        # Route : B3 sans `tests.adoption.reseau_licence == "accorde"` -> repli, aucune connexion.
        ssh = D.FauxSsh()
        route = D.TestRoute("lancer")
        code = route.lancer(ssh, Profil(familles=("python",)), licence="B3", hotes_licence=["license.unity3d.com"],
                            reseau_licence=lambda racine: False)
        self.assertEqual(code, 0)
        self.assertEqual((ssh.octets, ssh.flux), ([], []))
        self.assertTrue(any("licence" in d and "accord" in d for d in route.dits), route.dits)
        # Enveloppe : B3 sans la liste des hôtes de licence -> 2, rien ne part.
        code, err, etat = self.unity("conteneur", "B3")
        self.assertEqual(code, 2, err)
        self.assertEqual(self.docker_args(), [])
        # Avec la liste (l'accord est vérifié par la route) : réseau interne + mandataire, jamais bridge ni « none ».
        code, err, etat = self.unity("conteneur", "B3", "license.unity3d.com,core.cloud.unity3d.com", ident=ID_B)
        if not machine_id_presente():
            self.assertEqual(code, 77, err)
            self.skipTest("/etc/machine-id absent ici (B3 inclut B2) : seul le refus 77 est vérifié")
        self.assertEqual(code, 0, err)
        run = self.run_de(etat, f"tests-{ID_B}")
        self.assertEqual([b for a, b in self.paires(run) if a == "--network"], [f"deps-{ID_B}"])
        self.assertIn(("--dns", "0.0.0.0"), self.paires(run))
        self.assertIn(("--add-host", f"mandataire:{D.IP_MANDATAIRE}"), self.paires(run))
        mandataire = self.run_de(etat, f"mandataire-{ID_B}")
        self.assertEqual(mandataire[mandataire.index("--mandataire") + 3:], ["license.unity3d.com", "core.cloud.unity3d.com"])
        self.assertIn(f"docker network rm deps-{ID_B}", self.journal)
        self.assertIn(f"docker rm -f mandataire-{ID_B}", self.journal)

    def test_jamais_unityhub_ni_socket_montes(self):
        (self.home / ".config" / "unity3d" / "Unity.Licensing.Client.sock").write_text("", encoding="utf-8")
        for i, plus in enumerate((("B1",), ("B2",), ("B3", "license.unity3d.com"))):
            self.unity("conteneur", *plus, ident=E.ident(40 + i))
        appels = self.docker_args()
        self.assertTrue([x for x in appels if " run " in x and "tests-unity" in x], appels)
        for x in appels:
            for interdit in INTERDITS:
                self.assertNotIn(interdit, x)
        for f in (self.t / "etat").rglob("run-*.txt"):
            for a in f.read_text(encoding="utf-8").splitlines():
                self.assertFalse(any(i in a for i in INTERDITS), a)
                self.assertNotRegex(a, r"unity3d(/Unity)?:|unity3d/Unity/?:")                 # jamais le dossier entier

    def test_hote_non_installe_code_2(self):
        avant = self.arbre()
        code, err, _ = self.unity("hote_bac_a_sable", "B1")
        self.assertEqual(code, 2, err)
        self.assertTrue(any("exécuteur hôte non installé" in x for x in err), err)
        self.assertEqual(self.docker_args(), [])
        self.assertFalse((self.home / "tests" / ID / "travail").exists())
        code, err, _ = self.lancer(*NODE_14, "hote_bac_a_sable", "-", deps="-", ident=ID_B)
        self.assertEqual(code, 2, err)


# --------------------------------------------------------------------------------------- entrée du conteneur (entree-unity.sh)

ENTREE = RACINE / "serveur_ovh" / "images" / "tests" / "entree-tests.sh"
UNITY_EDITOR = r'''log=""; res=""; prec=""
for a in "$@"; do case "$prec" in -logFile) log="$a" ;; -testResults) res="$a" ;; esac; prec="$a"; done
printf '%s\n' "$@" > "$FAUX_UNITY/args.txt"
d="$HOME/.config/unity3d/Unity/licenses/UnityEntitlementLicense.xml"; u="$HOME/.local/share/unity3d/Unity/Unity_lic.ulf"
[ -f "$d" ] && echo "droits $(cat "$d")" >> "$FAUX_UNITY/copies" && echo "droits $(stat -c %a "$d")" >> "$FAUX_UNITY/modes"
[ -f "$u" ] && echo "ulf $(cat "$u")" >> "$FAUX_UNITY/copies" && echo "ulf $(stat -c %a "$u")" >> "$FAUX_UNITY/modes"
[ -f "$FAUX_UNITY/journal" ] && cp "$FAUX_UNITY/journal" "$log"
[ -f "$FAUX_UNITY/resultats.xml" ] && cp "$FAUX_UNITY/resultats.xml" "$res"
[ -f "$FAUX_UNITY/sortie" ] && cat "$FAUX_UNITY/sortie"
exit "${FAUX_UNITY_CODE:-0}"'''


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEntreeUnity(unittest.TestCase):
    def setUp(self):
        t = self.t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, t, True)
        faux = t / "bin"
        faux.mkdir()
        for nom, corps in (("unity-editor", UNITY_EDITOR), ("python3", f'exec "{Path(sys.executable).as_posix()}" "$@"')):
            (faux / nom).write_text("#!/bin/sh\n" + corps + "\n", newline="\n")
            (faux / nom).chmod(0o755)
        (t / "entree").mkdir()
        tampon = io.BytesIO()
        with tarfile.open(fileobj=tampon, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            info = tarfile.TarInfo("Assets/a.cs")
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
        (t / "entree" / "entree.tar").write_bytes(tampon.getvalue())
        (t / "entree" / "commande.json").write_text(json.dumps(COMMANDE_UNITY), encoding="utf-8")
        (t / "licence" / "droits").mkdir(parents=True)
        (t / "licence" / "droits" / "UnityEntitlementLicense.xml").write_text(FACTICE, encoding="utf-8")
        (t / "licence" / "ulf").write_text(FACTICE, encoding="utf-8")
        (t / "tmp").mkdir()
        (t / "home").mkdir()
        self.faux_unity = t / "unity"
        self.faux_unity.mkdir()
        self.env = dict(os.environ, ENTREE_TESTS_RACINE=t.as_posix(), HOME=(t / "home").as_posix(),
                        PATH=faux.as_posix() + os.pathsep + os.environ["PATH"], MYIAFACTORY_TESTS_FAMILLE="unity",
                        FAUX_UNITY=self.faux_unity.as_posix())

    def lancer(self, journal="", xml=None, code=0, sortie=""):
        (self.faux_unity / "journal").write_text(journal, encoding="utf-8")
        if xml is not None:
            (self.faux_unity / "resultats.xml").write_text(xml, encoding="utf-8")
        if sortie:
            (self.faux_unity / "sortie").write_text(sortie, encoding="utf-8")
        r = subprocess.run(["bash", ENTREE.as_posix()], capture_output=True, text=True, env=dict(self.env, FAUX_UNITY_CODE=str(code)),
                           timeout=60)
        return r

    def test_journal_unity_filtre(self):
        journal = ("Compiling scripts\n"
                   f"[Licensing::Module] license serial {FACTICE}\n"
                   f"Entitlement group {FACTICE}\n"
                   f"ULF path {FACTICE}\n"
                   f"Access TOKEN {FACTICE}\n"
                   "blob " + "QUJD" * 20 + "\n"
                   "Test run finished\n")
        r = self.lancer(journal, xml_resultats(2, 2, 0), sortie=f"Serial number {FACTICE}\nsortie ordinaire\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        tout = r.stdout + r.stderr
        self.assertNotIn(FACTICE, tout)
        self.assertNotRegex(tout, r"(?i)licen|entitlement|serial|token|ulf")
        self.assertNotIn("QUJD" * 10, tout)
        self.assertIn("Compiling scripts", tout)
        self.assertIn("Test run finished", tout)
        self.assertIn("sortie ordinaire", tout)
        self.assertIn("total=2 passed=2 failed=0", tout)
        # La licence est copiée sur le tmpfs (HOME), lisible par le seul propriétaire ; le journal et le XML restent sous /tmp.
        self.assertEqual((self.faux_unity / "copies").read_text(encoding="utf-8").split(), ["droits", FACTICE, "ulf", FACTICE])
        if os.name != "nt":
            self.assertEqual((self.faux_unity / "modes").read_text(encoding="utf-8").split(), ["droits", "600", "ulf", "600"])
        args = (self.faux_unity / "args.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(args[args.index("-logFile") + 1], (self.t / "tmp" / "unity.log").as_posix())
        self.assertEqual(args[args.index("-testResults") + 1], (self.t / "tmp" / "resultats.xml").as_posix())
        self.assertEqual(sum(1 for a in args if a.lower() == "-logfile"), 1)

    def test_journal_force_hors_de_la_sortie(self):
        # Une commande qui écrirait le journal sur la sortie (-logFile -) ou ailleurs : le chemin est imposé.
        commande = COMMANDE_UNITY[:-2] + ["-LOGFILE", "-"]
        (self.t / "entree" / "commande.json").write_text(json.dumps(commande), encoding="utf-8")
        r = self.lancer(f"license {FACTICE}\nok\n", xml_resultats(1, 1, 0))
        self.assertEqual(r.returncode, 0, r.stderr)
        args = (self.faux_unity / "args.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual([a for a in args if a.lower() == "-logfile"], ["-logFile"])
        self.assertNotIn("-", args[args.index("-logFile") + 1:args.index("-logFile") + 2])
        self.assertNotIn(FACTICE, r.stdout + r.stderr)

    def test_licence_refusee_code_81(self):
        r = self.lancer(f"No valid Unity Editor license found. {FACTICE}\n", None, code=1)
        self.assertEqual(r.returncode, 81, r.stderr)
        self.assertIn("licence Unity refusée", r.stderr)
        self.assertNotIn(FACTICE, r.stdout + r.stderr)
        self.assertNotIn("No valid", r.stdout + r.stderr)
        shutil.rmtree(self.t / "licence")                                                  # aucune licence montée : 81 aussi
        r = self.lancer("ok\n", xml_resultats(1, 1, 0))
        self.assertEqual(r.returncode, 81, r.stderr)

    def test_zero_test_n_est_pas_un_succes(self):
        r = self.lancer("ok\n", xml_resultats(0, 0, 0), code=0)
        self.assertEqual(r.returncode, 82, r.stderr)
        self.assertIn("aucun test découvert", r.stderr)
        (self.faux_unity / "resultats.xml").unlink()
        r = self.lancer("ok\n", None, code=0)                                            # XML absent
        self.assertEqual(r.returncode, 82, r.stderr)

    def test_bilan_des_resultats(self):
        echecs = ["Tests.Calcul.Addition", "Tests.Calcul.Licence"]                       # un nom « licence » ne sort pas non plus
        r = self.lancer("ok\n", xml_resultats(3, 1, 2, echecs), code=2)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("total=3 passed=1 failed=2", r.stdout)
        self.assertIn("Tests.Calcul.Addition", r.stdout)
        self.assertNotIn("Tests.Calcul.Licence", r.stdout)
        r = self.lancer("ok\n", xml_resultats(3, 2, 1, echecs[:1]), code=0)                # éditeur à 0 mais un échec : 2
        self.assertEqual(r.returncode, 2, r.stderr)
        many = [f"Tests.N.T{i}" for i in range(30)]
        r = self.lancer("ok\n", xml_resultats(30, 0, 30, many), code=2)
        self.assertEqual(len([x for x in r.stdout.splitlines() if "Tests.N.T" in x]), 20)

    def test_relais_borne_et_noms_stricts(self):
        # I1 : noms d'échecs relayés seulement dans [A-Za-z0-9_.()] et 120 caractères ; journal borné, sans ligne > 200.
        echecs = ["Tests.Ok.Cas_1(2)", "Tests.X.Cas avec espace", "Tests.X.Param(1,2)", "Tests.X." + "a" * 130,
                  "Tests.X.Cas&#233;"]
        longue = "LIGNE-LONGUE-" + "x" * 240
        journal = "".join(f"ligne {i:05d} " + "y" * 120 + "\n" for i in range(3000)) + longue + "\nfin du journal\n"
        r = self.lancer(journal, xml_resultats(5, 0, 5, echecs), code=2)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("unity : échec Tests.Ok.Cas_1(2)\n", r.stdout)
        self.assertEqual(r.stdout.count("unity : échec nom filtré\n"), 4, r.stdout[-800:])
        for interdit in ("avec espace", "Param(1,2)", "a" * 121, "Casé", "LIGNE-LONGUE"):
            self.assertNotIn(interdit, r.stdout)
        self.assertIn("fin du journal", r.stdout)
        self.assertTrue(all(len(x) <= 200 for x in r.stdout.splitlines()))
        self.assertLessEqual(len([x for x in r.stdout.splitlines() if x.startswith("ligne ")]), 100)
        self.assertLessEqual(len(r.stdout.encode("utf-8")), 24 * 1024)
        bruts = [p for p in self.t.rglob("unity.*") if p.parent != self.t / "tmp"]
        self.assertEqual(bruts, [])                                                        # journal brut : /tmp seulement
        self.assertTrue((self.t / "tmp" / "unity.log").exists())

    def test_81_seulement_sans_tests_et_codes_ramenes(self):
        # I3 : un motif de refus dans un journal où des tests ont tourné n'est pas un 81 (un vrai échec reste 2) ; un code de
        # l'éditeur hors de {0, 1, 2, 3} devient 1 (81, 82… ne viennent que du script).
        refus = "No valid Unity Editor license found\n"
        r = self.lancer(refus, xml_resultats(3, 2, 1, ["Tests.A.B"]), code=2)
        self.assertEqual(r.returncode, 2, r.stderr)
        r = self.lancer(refus, xml_resultats(3, 3, 0), code=0)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.lancer(refus, xml_resultats(0, 0, 0), code=0)                             # 0 test et refus : 81
        self.assertEqual(r.returncode, 81, r.stderr)
        for code_editeur in (81, 82, 137, 76, 255):
            with self.subTest(code=code_editeur):
                r = self.lancer("ok\n", xml_resultats(2, 2, 0), code=code_editeur)
                self.assertEqual(r.returncode, 1, r.stderr)
        (self.faux_unity / "resultats.xml").unlink()
        r = self.lancer("ok\n", None, code=82)                                             # XML absent, éditeur à 82 : 1
        self.assertEqual(r.returncode, 1, r.stderr)


# --------------------------------------------------------------------------------------- image : gabarit, digest, taille propre

DF_V = """Images space usage:

REPOSITORY                     TAG       IMAGE ID       CREATED        SIZE      SHARED SIZE   UNIQUE SIZE   CONTAINERS
myiafactory/tests-aaaaaaaaaaaa latest    aaaaaaaaaaaa   2 days ago     27.1GB    27.06GB       41.9MB        0
unityci/editor                 ubuntu    cccccccccccc   3 weeks ago    27.06GB   27.06GB       0B            0

Containers space usage:

CONTAINER ID   IMAGE     COMMAND   LOCAL VOLUMES   SIZE      CREATED   STATUS    NAMES
"""


class TestImageUnity(unittest.TestCase):
    def test_rendu_unity_par_digest(self):
        p = Profil(familles=("unity",), outils={"unity": VERSION, "unity_revision": "b22767f04f04"})
        with self.assertRaises(ValueError):
            tests_images.rendre_dockerfile(p)                                          # jamais par étiquette seule
        for mauvais in ("sha256:" + "B" * 64, "sha256:x", "latest", "sha256:" + "b" * 63):
            with self.assertRaises(ValueError):
                tests_images.rendre_dockerfile(p, mauvais)
        texte, sha = tests_images.rendre_dockerfile(p, DIGEST)
        froms = re.findall(r"(?m)^FROM (.+)$", texte)
        self.assertEqual(froms, [f"unityci/editor:ubuntu-{VERSION}-android-{tests_images.UNITY_GAMECI}@{DIGEST}"])
        self.assertIn("COPY entree-unity.sh /usr/local/bin/entree-unity.sh", texte)
        self.assertIn("git --version", texte)
        self.assertIn("USER 1000:1000", texte)
        gabarit = (RACINE / "serveur_ovh" / "images" / "tests-unity" / "Dockerfile.gabarit").read_text(encoding="utf-8")
        self.assertIn("@BASE@", gabarit)
        self.assertIn(gabarit.replace("@BASE@", froms[0]).strip(), texte)
        self.assertEqual(tests_images.rendre_dockerfile(p, DIGEST), (texte, sha))
        # La sonde du digest local : une commande fixe, la réponse lue par motif.
        self.assertEqual(tests_images.lire_digest_unity(json.dumps([f"unityci/editor@{DIGEST}"]).encode()), DIGEST)
        for mauvaise in (b"", b"[]", b'["evil/x@sha256:' + b"b" * 64 + b'"]', b'["unityci/editor@sha256:zz"]', b"pas du json"):
            self.assertIsNone(tests_images.lire_digest_unity(mauvaise))
        self.assertIn(f"unityci/editor:ubuntu-{VERSION}-android-", tests_images.sonde_digest_unity(VERSION))
        with self.assertRaises(ValueError):
            tests_images.sonde_digest_unity("1; id")

    def test_taille_propre_pour_le_budget(self):
        self.assertEqual(tests_images.taille_propre_mo("aaaaaaaaaaaa", DF_V), 40)
        self.assertEqual(tests_images.taille_propre_mo("myiafactory/tests-aaaaaaaaaaaa", DF_V), 40)
        self.assertEqual(tests_images.taille_propre_mo("cccccccccccc", DF_V), 0)
        self.assertIsNone(tests_images.taille_propre_mo("dddddddddddd", DF_V))
        self.assertIsNone(tests_images.taille_propre_mo("aaaaaaaaaaaa", "rien"))

    @unittest.skipUnless(shutil.which("bash"), "bash absent")
    def test_ramassage_compte_la_taille_propre(self):
        # Image dérivée de 27 Go apparents dont 40 Mo propres : sous un budget de 1 Go, elle reste.
        banc = TI.TestEnveloppeConstruction("test_ramassage")
        banc.setUp()
        self.addCleanup(banc.doCleanups)
        docker = banc.monde.parent / "bin" / "docker"
        corps = docker.read_text()
        docker.write_text(corps.replace('case "$1" in', 'case "$1" in\n  system) cat "$MONDE/df_v" 2>/dev/null; exit 0 ;;', 1),
                          newline="\n")
        etiquette = banc._image("a", 27 * 1024, 1)
        (banc.monde / "df_v").write_text(DF_V)
        r = banc.lancer("--ramasser", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertTrue((banc.monde / "images" / etiquette.replace("/", "__")).exists())
        (banc.monde / "df_v").write_text("")                                         # taille propre inconnue : l'apparente
        self.assertEqual(banc.lancer("--ramasser", "1").stdout, f"#ramassee {etiquette}\n")

    @unittest.skipUnless(shutil.which("bash"), "bash absent")
    def test_ramassage_etiquette_unity_retiree_apres_la_cible(self):
        # M2 : l'étiquette tests-unity-* n'est retirée qu'APRÈS un rmi réussi de la cible ; cible refusée : elle reste.
        banc = TI.TestEnveloppeConstruction("test_ramassage")
        banc.setUp()
        self.addCleanup(banc.doCleanups)
        docker = banc.monde.parent / "bin" / "docker"
        docker.write_text(r'''#!/bin/sh
echo "docker $*" >> "$MONDE/appels.txt"
case "$1" in
  image) case "$2" in
           ls) echo aaaaaaaaaaaa; exit 0 ;;
           inspect) case "$*" in
                      *RepoTags*) printf '%s ' "myiafactory/tests-unity-6000.6.7f1:latest" "myiafactory/tests-aaaaaaaaaaaa:latest" ;;
                      *Created*) echo "2020-01-01T00:00:00Z" ;;
                      *) echo 851443712 ;;
                    esac; exit 0 ;;
         esac ;;
  rmi) [ "$2" = "${FAUX_RMI_ECHEC:-}" ] && exit 1; exit 0 ;;
esac
exit 0
''', newline="\n")
        r = banc.lancer("--ramasser", "1", FAUX_RMI_ECHEC="myiafactory/tests-aaaaaaaaaaaa")   # 40 jours et plus : ancienne
        self.assertEqual(r.returncode, 0, r.stderr)
        rmi = [x for x in banc.appels() if x.startswith("docker rmi")]
        self.assertEqual(rmi, ["docker rmi myiafactory/tests-aaaaaaaaaaaa"])               # étiquette Unity laissée
        self.assertEqual(r.stdout, "")
        (banc.monde / "appels.txt").unlink()
        r = banc.lancer("--ramasser", "1")
        rmi = [x for x in banc.appels() if x.startswith("docker rmi")]
        self.assertEqual(rmi, ["docker rmi myiafactory/tests-aaaaaaaaaaaa", "docker rmi myiafactory/tests-unity-6000.6.7f1"])
        self.assertEqual(r.stdout, "#ramassee myiafactory/tests-aaaaaaaaaaaa\n")

    @unittest.skipUnless(shutil.which("bash"), "bash absent")
    def test_construction_unity_base_locale_sans_tirage(self):
        banc = TI.TestEnveloppeConstruction("test_construction_ligne_image")
        banc.setUp()
        self.addCleanup(banc.doCleanups)
        p = Profil(familles=("unity",), outils={"unity": VERSION})
        texte, sha = tests_images.rendre_dockerfile(p, DIGEST)
        etiquette = tests_images.etiquette_derivee(p)
        contexte = banc.home / "tests" / ".construction" / etiquette
        contexte.mkdir(parents=True)
        (contexte / "Dockerfile").write_bytes(texte.encode())
        base = f"unityci/editor:ubuntu-{VERSION}-android-{tests_images.UNITY_GAMECI}@{DIGEST}"
        r = banc.lancer(etiquette, sha)
        self.assertEqual(r.returncode, 2, r.stderr)                                     # base absente du serveur : jamais tirée
        self.assertEqual(banc.builds(), [])
        contexte.mkdir(parents=True, exist_ok=True)
        (contexte / "Dockerfile").write_bytes(texte.encode())
        (banc.monde / "images" / "base_unity").write_text(base)
        r = banc.lancer(etiquette, sha)
        self.assertEqual(r.returncode, 0, r.stderr)
        build = banc.builds()[0]
        self.assertNotIn("--pull", build)
        self.assertIn(f"-t {IMAGE_UNITY} -t {etiquette} ", build)
        self.assertIn("contexte: Dockerfile entree-tests.sh entree-unity.sh ", banc.appels())


class TestRouteUnity(unittest.TestCase):
    def test_arguments_de_l_executeur(self):
        f = tests_serveur._arguments_executeur
        oui, non = (lambda r: True), (lambda r: False)
        self.assertEqual(f(None, None, None, non, "r"), "")
        self.assertEqual(f("conteneur", "B1", None, non, "r"), " conteneur B1")
        self.assertEqual(f(None, "B2", None, non, "r"), " conteneur B2")
        self.assertEqual(f("conteneur", "B3", ["license.unity3d.com", "core.cloud.unity3d.com"], oui, "r"),
                         " conteneur B3 license.unity3d.com,core.cloud.unity3d.com")
        self.assertEqual(f(None, "B3", ["unity.com", "api.unity.com"], oui, "r"), " conteneur B3 unity.com,api.unity.com")
        self.assertEqual(tests_serveur.SUFFIXES_LICENCE, ("unity3d.com", "unity.com"))
        enveloppe = (RACINE / "serveur_ovh" / "taches" / "lancer_tests.sh").read_text(encoding="utf-8")
        self.assertIn('SUFFIXES_LICENCE=" unity3d.com unity.com "', enveloppe)            # la table fermée du serveur
        for mauvais in ((None, "B3", ["license.unity3d.com"], non), (None, "B3", None, oui), (None, "B3", [], oui),
                        (None, "B1", ["a.b"], oui), ("docker", None, None, oui), (None, "b1", None, oui),
                        (None, "B3", ["a.b;id"], oui), (None, "B3", ["-h.b"], oui), (None, "B3", ["x"], oui),
                        (None, "B3", ["license.unity3d.com"] * 9, oui),
                        # I2 et M4 : table fermée des suffixes, IP refusées, 512 caractères au plus (miroir de l'enveloppe)
                        (None, "B3", ["169.254.169.254"], oui), (None, "B3", ["172.17.0.1"], oui),
                        (None, "B3", ["attaquant.example"], oui), (None, "B3", ["unity3d.com.attaquant.example"], oui),
                        (None, "B3", ["fauxunity3d.com"], oui),
                        (None, "B3", ["a" * 60 + f".x{i}.unity3d.com" for i in range(8)], oui)):
            with self.subTest(mauvais=mauvais[:3]):
                with self.assertRaises(tests_serveur.Repli):
                    f(*mauvais, "r")


if __name__ == "__main__":
    unittest.main()
