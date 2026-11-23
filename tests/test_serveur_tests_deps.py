"""Caches de dépendances et échauffement des campagnes de tests au serveur (conception § 5.13, tâche 14d).

L'enveloppe hôte (`serveur_ovh/taches/lancer_tests.sh`) tourne avec le bash du poste et les faux du banc de l'enveloppe
(`test_serveur_tests_enveloppe`), plus un faux `docker` qui joue l'échauffement (il écrit dans le dossier monté sur /deps), un
faux `curl` (somme publiée du wrapper Gradle) et un faux `du` qui compte les caches : aucun conteneur, aucun réseau. Les aides
(`tests_hote.py` : drapeaux hors ligne, mandataire, plan d'échauffement) et la route (`outils/tests_serveur.py`,
`outils/tests_profil.py`) se testent en pur Python."""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_serveur_tests_enveloppe as banc  # noqa: E402
import tests_images  # noqa: E402
import tests_profil  # noqa: E402
import tests_serveur  # noqa: E402
from tests_profil import Profil  # noqa: E402

ID, ID_B = banc.ID, banc.ID_B
DEPS = "0123456789abcdef"
JAR = b"PK\x03\x04 faux wrapper officiel"
NPM = ("10", "myiafactory/tests", "node", "npm")

DOCKER = r'''echo "docker $*" >> "$FAUX_JOURNAL"
ET="$FAUX_ETAT"
dernier() { for a in "$@"; do d="$a"; done; printf '%s' "$d"; }
case "$1" in
  image) exit 0 ;;
  volume) [ "${2:-}" = create ] && [ -n "${FAUX_SANS_OVERLAY:-}" ] && exit 1; exit 0 ;;
  ps|network) exit 0 ;;
  inspect) n=$(dernier "$@")
           if [ -f "$ET/etat-$n" ]; then cat "$ET/etat-$n"; exit 0; fi
           echo "Error: No such object: $n" >&2; exit 1 ;;
  kill) touch "$ET/tue"; exit 0 ;;
  rm) n=$(dernier "$@"); rm -f "$ET/etat-$n"; exit 0 ;;
  run)
    nom=""; prec=""; deps=""; meta=""
    for a in "$@"; do
      [ "$prec" = --name ] && nom="$a"
      if [ "$prec" = -v ]; then case "$a" in *:/deps) deps="${a%:/deps}" ;; *:/deps-meta) meta="${a%:/deps-meta}" ;; esac; fi
      prec="$a"
    done
    printf '%s\n' "$@" > "$ET/run-$nom.txt"
    echo "$nom" >> "$ET/ordre-runs"
    case "$nom" in
      mandataire-*) exit 0 ;;
      deps-*)
        cp "$HOME/tests/${nom#deps-}/deps-entree/commande.json" "$ET/commande-$nom.json"
        [ -n "${FAUX_DEPS_CODE:-}" ] && exit "$FAUX_DEPS_CODE"
        mkdir -p "$deps/node_modules" && echo x > "$deps/node_modules/a.js"
        if [ -n "${FAUX_VERROU_PRODUIT:-}" ]; then echo '{"verrou": 1}' > "$meta/verrou-produit"; : > "$meta/non-verrouille"; fi
        : > "$meta/ok"
        exit 0 ;;
    esac
    cp "$HOME/tests/${nom#tests-}/entree/commande.json" "$ET/commande-$nom.json"
    echo "exited ${FAUX_CODE:-0} 2026-11-23T10:00:00.1Z" > "$ET/etat-$nom"
    exit "${FAUX_CODE:-0}" ;;
esac
exit 0'''
# du : les caches comptés 1 Go chacun pour ~/tests/.deps (budget), FAUX_DU_DEPS_KO pour un cache en préparation (plafond).
DU = r'''p="$3"
case "$p" in
  */.deps) n=$(ls -d "$p"/*/*-* 2>/dev/null | grep -cv '\.tmp$'); printf '%s\t%s\n' "$((n * 1048576))" "$p"; exit 0 ;;
  *.tmp) printf '%s\t%s\n' "${FAUX_DU_DEPS_KO:-4}" "$p"; exit 0 ;;
esac
printf '%s\t%s\n' 4 "$p"'''
CURL = r'''echo "curl $*" >> "$FAUX_JOURNAL"
o=""; prec=""
for a in "$@"; do [ "$prec" = -o ] && o="$a"; prec="$a"; done
[ -n "${FAUX_CURL_ECHEC:-}" ] && exit 22
printf '%s\n' "$FAUX_SOMME_GRADLE" > "$o"'''
FAUX = dict(banc.FAUX, docker=DOCKER, du=DU, curl=CURL)


def _tar(fichiers):
    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for nom, donnees in fichiers.items():
            info = tarfile.TarInfo(nom)
            info.size, info.mode = len(donnees), 0o755 if nom == "gradlew" else 0o644
            tar.addfile(info, io.BytesIO(donnees))
    return tampon.getvalue()


TAR_NODE = _tar({"package.json": b'{"dependencies": {"a": "1"}}', "package-lock.json": b"{}", "src/a.js": b"1"})
TAR_GRADLE = _tar({"gradlew": b"#!/bin/sh\n", "settings.gradle": b"", "build.gradle": b"",
                   "gradle/wrapper/gradle-wrapper.jar": JAR,
                   "gradle/wrapper/gradle-wrapper.properties":
                       b"distributionUrl=https\\://services.gradle.org/distributions/gradle-8.7-bin.zip\n"})


class Banc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.racine = Path(cls._t.name)
        cls.bin = cls.racine / "bin"
        cls.bin.mkdir()
        for nom, corps in FAUX.items():
            (cls.bin / nom).write_text("#!/bin/sh\n" + corps + "\n", newline="\n")
            (cls.bin / nom).chmod(0o755)
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def setUp(self):
        type(self).n += 1
        t = self.t = self.racine / f"c{self.n}"
        self.home = t / "home"
        self.home.mkdir(parents=True)
        self.journal_fichier = t / "appels.txt"
        self.env = dict(os.environ, HOME=banc._msys(self.home), PATH=self.bin.as_posix() + os.pathsep + os.environ["PATH"],
                        FAUX_JOURNAL=self.journal_fichier.as_posix(), ENVELOPPE_SONDE_S="0.1",
                        FAUX_SOMME_GRADLE=hashlib.sha256(JAR).hexdigest())

    @property
    def journal(self):
        return self.journal_fichier.read_text(encoding="utf-8") if self.journal_fichier.exists() else ""

    def cache(self, projet="projet-a", nom=f"npm-{DEPS}"):
        return self.home / "tests" / ".deps" / projet / nom

    def preparer_cache(self, projet="projet-a", nom=f"npm-{DEPS}", age_s=0):
        c = self.cache(projet, nom)
        (c / "contenu" / "node_modules").mkdir(parents=True)
        for f in (".pret", ".utilise", ".verrou"):
            (c / f).write_text("x", encoding="utf-8")
        if age_s:
            t = time.time() - age_s
            for f in (".pret", ".utilise"):
                os.utime(c / f, (t, t))
        return c

    def lancer(self, *supplement, ident=ID, tar=TAR_NODE, env=None, commande=banc.COMMANDE, deps=DEPS):
        """(code, lignes de la sortie d'erreur, dossier d'état du faux docker)."""
        entree = self.home / "tests" / ident / "entree"
        entree.mkdir(parents=True)
        (entree / "entree.tar").write_bytes(tar)
        etat = self.t / "etat" / ident
        etat.mkdir(parents=True, exist_ok=True)
        e = dict(self.env, FAUX_ETAT=etat.as_posix(), **(env or {}))
        args = ["bash", banc.SCRIPT.as_posix(), ident, "2", "4", "8192", "1800", "projet-a", deps, *supplement]
        with open(etat / "err", "w+b") as err:
            p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err, env=e)
            try:
                p.stdin.write((commande + "\n").encode())
                p.stdin.flush()
            except OSError:
                pass
            try:
                code = p.wait(timeout=90)
            finally:
                if p.poll() is None:
                    p.kill()
                p.stdin.close()
            err.seek(0)
            lignes = [x for x in err.read().decode("utf-8", "replace").split("\n") if x]
        self.assertTrue(banc.FIN.match(lignes[-1]), lignes[-5:])
        return code, lignes, etat

    @staticmethod
    def run_de(etat, nom):
        f = etat / f"run-{nom}.txt"
        return f.read_text(encoding="utf-8").splitlines() if f.exists() else None

    @staticmethod
    def paires(args):
        return list(zip(args, args[1:]))


@unittest.skipUnless(banc.shutil.which("bash"), "bash absent")
class TestEchauffement(Banc):
    def test_cache_prepare_une_fois(self):
        code, err, etat = self.lancer(*NPM, "refuse", "40")
        self.assertEqual(code, 0, err)
        deps_run = self.run_de(etat, f"deps-{ID}")
        self.assertIsNotNone(deps_run)
        self.assertEqual(json.loads((etat / f"commande-deps-{ID}.json").read_text(encoding="utf-8"))[-3:],
                         ["--echauffer", "npm", "node"])
        c = self.cache()
        self.assertTrue((c / ".pret").exists() and (c / "contenu" / "node_modules" / "a.js").exists())
        self.assertFalse(Path(str(c) + ".tmp").exists())
        ordre = (etat / "ordre-runs").read_text(encoding="utf-8").split()
        self.assertEqual(ordre, [f"deps-{ID}", f"tests-{ID}"])                  # échauffement avant les tests
        code, err, etat_b = self.lancer(*NPM, "refuse", "40", ident=ID_B)
        self.assertEqual(code, 0, err)
        self.assertEqual((etat_b / "ordre-runs").read_text(encoding="utf-8").split(), [f"tests-{ID_B}"])   # aucun deps-*

    def test_seul_l_echauffement_a_le_reseau(self):
        code, err, etat = self.lancer(*NPM, "refuse", "40")
        self.assertEqual(code, 0, err)
        deps_run, tests_run = self.run_de(etat, f"deps-{ID}"), self.run_de(etat, f"tests-{ID}")
        self.assertEqual([b for a, b in self.paires(tests_run) if a == "--network"], ["none"])
        self.assertEqual([b for a, b in self.paires(deps_run) if a == "--network"], ["bridge"])   # Q2 : npm sans code
        for args in (deps_run, tests_run):
            for paire in (("--cap-drop", "ALL"), ("--user", "1000:1000"), ("--security-opt", "no-new-privileges")):
                self.assertIn(paire, self.paires(args))
            self.assertIn("--read-only", args)
            self.assertFalse(any("docker.sock" in a or a == "--privileged" for a in args))
        env = [b for a, b in self.paires(deps_run) if a == "-e"]
        self.assertFalse([x for x in env if re.search(r"(?i)token|jeton|cle|key|secret|proxy", x)], env)
        self.assertIn(("--label", "myiafactory.genre=tests-deps"), self.paires(deps_run))

    def test_code_du_projet_jamais_en_bridge(self):
        gradle = ("10", "myiafactory/tests-android", "gradle-jvm", "gradle")
        code, err, etat = self.lancer(*gradle, "refuse", "40", tar=TAR_GRADLE)
        self.assertEqual(code, 79, err)
        self.assertIn("#deps-echec reseau-non-accorde", err)
        self.assertEqual(err[-2], "#refus 79")
        self.assertNotIn("docker run", self.journal)
        self.assertNotIn("network create", self.journal)
        code, err, etat = self.lancer(*gradle, "accorde", "40", tar=TAR_GRADLE, ident=ID_B)
        self.assertEqual(code, 0, err)
        deps_run = self.run_de(etat, f"deps-{ID_B}")
        self.assertEqual([b for a, b in self.paires(deps_run) if a == "--network"], [f"deps-{ID_B}"])
        self.assertNotIn("bridge", deps_run)
        env = [b for a, b in self.paires(deps_run) if a == "-e"]
        self.assertIn(f"HTTPS_PROXY=http://mandataire-{ID_B}:3128", env)
        self.assertTrue(any(x.startswith("JAVA_TOOL_OPTIONS=") and f"-Dhttps.proxyHost=mandataire-{ID_B}" in x for x in env))
        self.assertRegex(self.journal, rf"docker network create --internal .*deps-{ID_B}")
        mandataire = self.run_de(etat, f"mandataire-{ID_B}")
        self.assertIn(("--network", "bridge"), self.paires(mandataire))
        self.assertIn("--mandataire", mandataire)
        self.assertIn("services.gradle.org", mandataire)
        self.assertNotIn("github.com", mandataire)
        self.assertIn(f"docker network connect deps-{ID_B} mandataire-{ID_B}", self.journal)
        self.assertIn(f"docker rm -f mandataire-{ID_B}", self.journal)
        self.assertIn(f"docker network rm deps-{ID_B}", self.journal)
        self.assertEqual([b for a, b in self.paires(self.run_de(etat, f"tests-{ID_B}")) if a == "--network"], ["none"])

    def test_wrapper_modifie_refuse(self):
        gradle = ("10", "myiafactory/tests-android", "gradle-jvm", "gradle", "accorde", "40")
        code, err, etat = self.lancer(*gradle, tar=TAR_GRADLE, env={"FAUX_SOMME_GRADLE": "0" * 64})
        self.assertEqual(code, 79, err)
        self.assertIn("#deps-echec wrapper-modifie", err)
        self.assertNotIn("docker run", self.journal)
        self.assertIn("https://services.gradle.org/distributions/gradle-8.7-wrapper.jar.sha256", self.journal)
        sans_jar = _tar({"gradlew": b"", "settings.gradle": b""})
        code, err, etat = self.lancer(*gradle, tar=sans_jar, ident=ID_B)
        self.assertEqual(code, 79, err)
        self.assertIn("#deps-echec wrapper-absent", err)

    def test_echec_deps_code_79_et_rien_de_pret(self):
        for i, env, raison in ((0, {"FAUX_DEPS_CODE": "1"}, "echauffement"), (1, {"FAUX_DU_DEPS_KO": str(3 * 1048576)}, "plafond")):
            with self.subTest(raison=raison):
                ident = banc.ident(i)
                code, err, etat = self.lancer(*NPM, "refuse", "40", ident=ident, env=env)
                self.assertEqual(code, 79, err)
                self.assertIn(f"#deps-echec {raison}", err)
                self.assertEqual(err[-2], "#refus 79")
                self.assertIsNone(self.run_de(etat, f"tests-{ident}"))
                self.assertFalse(self.cache().exists())
                self.assertFalse(Path(str(self.cache()) + ".tmp").exists())
                self.assertFalse((self.home / "tests" / ident).exists())
                self.assertIn(f"docker rm -f deps-{ident}", self.journal)

    def test_copie_sur_ecriture(self):
        c = self.preparer_cache()
        code, err, etat = self.lancer(*NPM, "refuse", "40")
        self.assertEqual(code, 0, err)
        self.assertIsNone(self.run_de(etat, f"deps-{ID}"))
        m = re.search(r"docker volume create (.*) tests-deps-" + ID, self.journal)
        self.assertIsNotNone(m, self.journal)
        self.assertIn("--opt type=overlay", m.group(1))
        self.assertRegex(m.group(1), rf"o=lowerdir=\S*/\.deps/projet-a/npm-{DEPS}/contenu,upperdir=\S*/tests/{ID}/deps-haut,"
                                     rf"workdir=\S*/tests/{ID}/deps-ov")
        tests_run = self.run_de(etat, f"tests-{ID}")
        self.assertIn(("--mount", f"type=volume,src=tests-deps-{ID},dst=/deps"), self.paires(tests_run))
        self.assertFalse([a for a in tests_run if a.endswith(":/deps") or a.endswith(":/deps:ro")])
        self.assertIn(f"docker volume rm -f tests-deps-{ID}", self.journal)
        self.assertRegex(self.journal, r"flock -s \d")                          # cache tenu pendant la campagne
        self.assertFalse((self.home / "tests" / ID).exists())                   # couche haute effacée avec le dossier
        self.assertTrue((c / "contenu" / "node_modules").is_dir())              # la couche basse est intacte
        code, err, etat = self.lancer(*NPM, "refuse", "40", ident=ID_B, env={"FAUX_SANS_OVERLAY": "1"})
        self.assertEqual(code, 79, err)
        self.assertIn("#deps-echec copie-sur-ecriture", err)

    def test_drapeaux_hors_ligne(self):
        self.preparer_cache(nom=f"gradle-{DEPS}")
        code, err, etat = self.lancer("10", "myiafactory/tests-android", "gradle-jvm", "gradle", "accorde", "40",
                                      tar=TAR_GRADLE, commande=json.dumps(["./gradlew", "test"]))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads((etat / f"commande-tests-{ID}.json").read_text(encoding="utf-8")),
                         ["./gradlew", "--offline", "--no-daemon", "test"])
        env = [b for a, b in self.paires(self.run_de(etat, f"tests-{ID}")) if a == "-e"]
        self.assertIn("GRADLE_USER_HOME=/deps/gradle", env)
        self.preparer_cache(nom=f"cargo-{DEPS}")
        code, err, etat = self.lancer("10", "myiafactory/tests-0123456789ab", "rust", "cargo", "refuse", "40", ident=ID_B,
                                      commande=json.dumps(["cargo", "test"]))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads((etat / f"commande-tests-{ID_B}.json").read_text(encoding="utf-8")),
                         ["cargo", "--offline", "test"])

    def test_sans_verrou_garde_le_verrou_produit(self):
        code, err, etat = self.lancer(*NPM, "refuse", "40", env={"FAUX_VERROU_PRODUIT": "1"})
        self.assertEqual(code, 0, err)
        c = self.cache()
        self.assertEqual((c / ".verrou-produit").read_text(encoding="utf-8").strip(), '{"verrou": 1}')
        self.assertTrue((c / ".non-verrouille").exists())
        vieux = time.time() - 8 * 86400                                          # plus de 7 jours : refait
        os.utime(c / ".pret", (vieux, vieux))
        code, err, etat = self.lancer(*NPM, "refuse", "40", ident=ID_B, env={"FAUX_VERROU_PRODUIT": "1"})
        self.assertEqual(code, 0, err)
        self.assertIsNotNone(self.run_de(etat, f"deps-{ID_B}"))
        self.assertGreater((c / ".pret").stat().st_mtime, vieux + 86400)
        code, err, etat = self.lancer(*NPM, "refuse", "40", ident=banc.ident(3))  # récent : gardé
        self.assertIsNone(self.run_de(etat, f"deps-{banc.ident(3)}"))

    def test_deux_caches_et_budget(self):
        anciens = {("projet-a", "npm-1111111111111111"): 400, ("projet-a", "npm-2222222222222222"): 300,
                   ("projet-b", "pip-3333333333333333"): 200, ("projet-b", "npm-4444444444444444"): 100}
        for (projet, nom), age in anciens.items():
            self.preparer_cache(projet, nom, age)
        code, err, etat = self.lancer(*NPM, "refuse", "2")
        self.assertEqual(code, 0, err)
        restants = sorted(p.parent.name + "/" + p.name for p in (self.home / "tests" / ".deps").glob("*/*-*")
                          if not p.name.startswith("."))
        self.assertEqual(restants, [f"projet-a/npm-{DEPS}", "projet-b/npm-4444444444444444"])
        self.assertTrue((self.cache() / ".utilise").exists())

    def test_cache_tenu_jamais_efface(self):
        tenu = self.preparer_cache(nom="npm-1111111111111111", age_s=400)
        self.preparer_cache(nom="npm-2222222222222222", age_s=300)
        p = subprocess.Popen(["bash", "-c", 'exec 5>> "$1/.verrou"; flock -s 5 || exit 1; read x', "x", banc._msys(tenu)],
                             stdin=subprocess.PIPE, env=self.env)
        try:
            fin = time.time() + 20
            while not list(tenu.glob(".verrou.partage-*")) and time.time() < fin:
                time.sleep(0.05)
            code, err, etat = self.lancer(*NPM, "refuse", "1")                   # budget dépassé lui aussi
            self.assertEqual(code, 0, err)
        finally:
            p.stdin.close()
            p.wait(timeout=10)
        self.assertTrue(tenu.exists())
        self.assertFalse(self.cache(nom="npm-2222222222222222").exists())
        self.assertTrue(self.cache().exists())                                    # jamais celui de la campagne


class TestAides(unittest.TestCase):
    def setUp(self):
        self.aide = banc._charger_aide()

    def test_drapeaux_hors_ligne_par_famille(self):
        h = self.aide.hors_ligne
        self.assertEqual(h(["./gradlew", "test"], "gradle"), ["./gradlew", "--offline", "--no-daemon", "test"])
        self.assertEqual(h(["./gradlew", "--offline", "test"], "gradle"), ["./gradlew", "--offline", "--no-daemon", "test"])
        self.assertEqual(h(["mvn", "-B", "test"], "maven"), ["mvn", "-o", "-B", "test"])
        self.assertEqual(h(["cargo", "test"], "cargo"), ["cargo", "--offline", "test"])
        self.assertEqual(h(["dotnet", "test"], "dotnet"), ["dotnet", "test", "--no-restore"])
        self.assertEqual(h(["python3", "-m", "pytest"], "gradle"), ["python3", "-m", "pytest"])   # autre exécutable
        self.assertEqual(h(["npm", "test"], "npm"), ["npm", "test"])
        self.assertEqual(h(["cargo"] + ["x"] * 63, "cargo"), ["cargo"] + ["x"] * 63)              # 64 au plus : inchangée

    def test_mandataire_liste_fermee(self):
        permis = self.aide.hote_permis
        hotes = ("services.gradle.org", "repo.maven.apache.org")
        self.assertEqual(permis("CONNECT services.gradle.org:443 HTTP/1.1", hotes), "services.gradle.org")
        self.assertEqual(permis("CONNECT Services.Gradle.org:443 HTTP/1.1", hotes), "services.gradle.org")
        for refus in ("CONNECT evil.example:443 HTTP/1.1", "CONNECT services.gradle.org:22 HTTP/1.1",
                      "GET http://services.gradle.org/ HTTP/1.1", "CONNECT 10.0.0.1:443 HTTP/1.1",
                      "CONNECT services.gradle.org.evil.example:443 HTTP/1.1", "CONNECT services.gradle.org:443 HTTP/1.1 x"):
            self.assertIsNone(permis(refus, hotes), refus)

    def test_plan_d_echauffement(self):
        with tempfile.TemporaryDirectory() as t:
            w = Path(t)
            (w / "package.json").write_text("{}", encoding="utf-8")
            (w / "src").mkdir()
            (w / "src" / "a.js").write_text("1", encoding="utf-8")
            plan = self.aide.plan_echauffement("npm", "node", str(w))
            self.assertEqual(plan["etapes"][0]["commande"][:2], ["npm", "install"])         # sans verrou : il est produit
            self.assertIn("--ignore-scripts", plan["etapes"][0]["commande"])
            self.assertEqual(plan["produit"], "package-lock.json")
            self.assertFalse((w / "src" / "a.js").exists())                                  # seuls les manifestes restent
            (w / "package-lock.json").write_text("{}", encoding="utf-8")
            self.assertEqual(self.aide.plan_echauffement("npm", "node", str(w))["etapes"][0]["commande"][:2], ["npm", "ci"])
            (w / "requirements.txt").write_text("a==1\n", encoding="utf-8")
            pip = self.aide.plan_echauffement("pip", "python", str(w))
            self.assertIn("--only-binary=:all:", pip["etapes"][1]["commande"])
            with self.assertRaises(ValueError):
                self.aide.plan_echauffement("unity", "unity", str(w))


class TestProfilEtRoute(unittest.TestCase):
    def test_table_des_echauffements_miroir_de_l_enveloppe(self):
        texte = banc.SCRIPT.read_text(encoding="utf-8")
        for cle, e in tests_profil.ECHAUFFEMENTS.items():
            m = re.search(rf"^ECH\[{re.escape(cle)}\]=\"(\d+) (\d+) ([01])\"", texte, re.M)
            self.assertIsNotNone(m, cle)
            self.assertEqual((int(m.group(1)), int(m.group(2)), m.group(3) == "1"),
                             (e["duree_s"], e["plafond_go"], e["execute_du_code"]), cle)
        code = {k for k, e in tests_profil.ECHAUFFEMENTS.items() if e["execute_du_code"]}
        self.assertEqual(code, {"gradle", "maven", "pip-sources", "unity"})

    def test_empreinte_deps(self):
        with tempfile.TemporaryDirectory() as t:
            r = Path(t)
            (r / "package.json").write_text('{"scripts": {"test": "jest"}, "dependencies": {"a": "1"}}', encoding="utf-8")
            sans = tests_profil.empreinte_deps(tests_profil.analyser(str(r)), str(r))
            self.assertRegex(sans, r"^[0-9a-f]{16}$")                                        # sans verrou : le manifeste
            (r / "package-lock.json").write_text('{"v": 1}', encoding="utf-8")
            p = tests_profil.analyser(str(r))
            a = tests_profil.empreinte_deps(p, str(r))
            self.assertNotEqual(a, sans)
            (r / "package-lock.json").write_text('{"v": 2}', encoding="utf-8")
            self.assertNotEqual(tests_profil.empreinte_deps(tests_profil.analyser(str(r)), str(r)), a)
            autre_image = tests_profil.replace(p, outils={"node": "18"})
            self.assertNotEqual(tests_profil.empreinte_deps(autre_image, str(r)), a)
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "setup.cfg").write_text("[metadata]\n", encoding="utf-8")
            self.assertIsNone(tests_profil.empreinte_deps(tests_profil.analyser(t), t))         # aucune dépendance
        self.assertIsNone(tests_profil.empreinte_deps(Profil(), "."))

    def test_sonde_sdk_et_cache_gradle(self):
        self.assertTrue(tests_images.CACHE_GRADLE_PRET)
        sortie = ("#platforms\nandroid-36\nandroid-35;rm\n#build-tools\n36.0.0\n#ndk\n#licenses\nandroid-sdk-license\n"
                  "x$(id)\n").encode()
        sdk = tests_serveur.lire_sonde_sdk(sortie)
        self.assertEqual(sdk, {"platforms": ["android-36"], "build_tools": ["36.0.0"], "ndk": [],
                               "licences": ["android-sdk-license"]})
        fridge = Profil(familles=("gradle-android",), outils={"jdk": "17", "android": {"compileSdk": 36, "build_tools": "36.0.0"}})
        self.assertEqual(tests_images.choisir_image(fridge, sdk)["manque"], [])
        sans_licence = dict(sdk, licences=[])
        self.assertEqual(tests_images.choisir_image(fridge, sans_licence)["manque"], ["licenses;android-sdk-license"])


class FauxSsh:
    def __init__(self, refus=None, sonde=b""):
        self.refus, self.sonde, self.flux, self.octets = refus, sonde, [], []

    def executer_octets(self, hote, commande, cle, entree=None, delai=60, _plus=()):
        self.octets.append(commande)
        if entree is None:
            return 0, self.sonde, ""
        entree.read()
        return 0, b"", ""

    def executer_en_flux(self, hote, commande, cle, premiere_ligne, sortie, **k):
        self.flux.append(commande)
        if self.refus:
            return {"code": self.refus, "octets": 0, "fin": "", "fin_serveur": (self.refus, 1, 2, 0), "erreur": "",
                    "code_ssh": self.refus, "raison": "refus", "refus": self.refus}
        return {"code": 0, "octets": 0, "fin": "", "fin_serveur": (0, 1, 2, 0), "erreur": "", "code_ssh": 0,
                "raison": "fin", "refus": None}


class FauxInstantane:
    HorsLimites = tests_serveur.tests_instantane.HorsLimites

    def lister(self, racine, git=None):
        return ["a"], []

    def executables(self, racine, git=None):
        return set()

    def ecrire_tar(self, racine, fichiers, destination, executables=None):
        destination.write(b"x")

    def empreinte_verrou_node(self, racine):
        return None


class TestRoute(unittest.TestCase):
    SERVEUR = SimpleNamespace(id="ovh-1", nom="OVH", hote="203.0.113.7", utilisateur="ubuntu", cle="C:/k")

    def lancer(self, ssh, profil, reseau=False, **k):
        self.poste, self.dits = [], []
        with tempfile.TemporaryDirectory() as t:
            options = dict(dossier=t, ssh=ssh, executer_poste=lambda c, dossier=None, attendre=True: self.poste.append(c) or 0,
                           noter=lambda *a, **kw: None, horloge=lambda: 1.0, maintenant=lambda: 1000.0,
                           dire=lambda *a, **kw: self.dits.append(" ".join(a)), choisir=lambda d, requises: self.SERVEUR,
                           instantane=FauxInstantane(), projet_de=lambda d: ("projet-a", Path(d)),
                           injoignable=Path(t) / "inj.json", attentes=Path(t) / "att", sortie=io.BytesIO(),
                           sortie_erreur=io.BytesIO(), nouvel_id=lambda: ID, dormir=lambda s: None, accord=lambda r: None,
                           analyse=lambda racine, **kw: profil, empreinte=lambda p, r, famille=None: DEPS,
                           reseau_code=lambda racine: reseau)
            options.update(k)
            return tests_serveur.executer(["npm", "test"], **options)

    def test_route_code_79_replie(self):
        node = Profil(familles=("node",), deps={"node": {"gestionnaire": "npm"}})
        ssh = FauxSsh(refus=79)
        self.assertEqual(self.lancer(ssh, node), 0)
        self.assertEqual(len(self.poste), 1)                                       # repli au poste (R3 étendue)
        self.assertTrue(any("échauffement" in d for d in self.dits), self.dits)
        self.assertTrue(ssh.flux[0].endswith(f" projet-a {DEPS} 10 myiafactory/tests node npm refuse 40"), ssh.flux[0])

    def test_code_du_projet_sans_accord_reste_au_poste(self):
        jvm = Profil(familles=("gradle-jvm",), outils={"jdk": "17"}, deps={"gradle-jvm": {"gestionnaire": "gradle"}})
        ssh = FauxSsh()
        self.assertEqual(self.lancer(ssh, jvm), 0)
        self.assertEqual((ssh.octets, ssh.flux), ([], []))                         # R5 : rien n'est envoyé
        self.assertTrue(any("échauffement réseau non accordé" in d for d in self.dits), self.dits)
        ssh = FauxSsh()
        self.assertEqual(self.lancer(ssh, jvm, reseau=True), 0)
        self.assertTrue(ssh.flux[0].endswith(f" projet-a {DEPS} 10 myiafactory/tests-android gradle-jvm gradle accorde 40"),
                        ssh.flux[0])

    def test_sonde_du_sdk_par_ssh(self):
        android = Profil(familles=("gradle-android",), outils={"jdk": "17", "android": {"compileSdk": 36}},
                         deps={"gradle-android": {"gestionnaire": "gradle"}})
        ssh = FauxSsh(sonde=b"#platforms\nandroid-34\n#build-tools\n#ndk\n#licenses\nandroid-sdk-license\n")
        self.assertEqual(self.lancer(ssh, android, reseau=True), 0)
        self.assertEqual(ssh.flux, [])
        self.assertTrue(any("platforms;android-36" in d for d in self.dits), self.dits)
        self.assertIn("android-sdk", ssh.octets[0])
        self.assertNotRegex(ssh.octets[0], r"(?i)token|cle|key")


if __name__ == "__main__":
    unittest.main()
