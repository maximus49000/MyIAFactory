"""Caches de dépendances et échauffement des campagnes de tests au serveur (conception § 5.13, tâche 14d).

L'enveloppe hôte (`serveur_ovh/taches/lancer_tests.sh`) tourne avec le bash du poste et les faux du banc de l'enveloppe
(`test_serveur_tests_enveloppe`), plus un faux `docker` qui joue l'échauffement (il écrit dans le dossier monté sur /deps) et
l'essai du volume overlay, un faux `curl` (sommes publiées du wrapper Gradle, liste des versions, distribution) et un faux `du`
qui compte les caches : aucun conteneur, aucun réseau. Les aides (`tests_hote.py` : drapeaux hors ligne, mandataire, plan
d'échauffement, gel pip) et la route (`outils/tests_serveur.py`, `outils/tests_profil.py`) se testent en pur Python."""
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
from unittest import mock

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
ZIP = b"PK zip de la distribution"
NPM = ("10", "myiafactory/tests", "node", "npm")
IP_MANDATAIRE = "172.30.0.2"

DOCKER = r'''echo "docker $*" >> "$FAUX_JOURNAL"
ET="$FAUX_ETAT"
dernier() { for a in "$@"; do d="$a"; done; printf '%s' "$d"; }
case "$1" in
  image|volume|ps|network) exit 0 ;;
  inspect) n=$(dernier "$@")
           case "$n" in mandataire-*) echo "''' + IP_MANDATAIRE + r'''"; exit 0 ;; esac
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
      essai-*) [ -n "${FAUX_SANS_OVERLAY:-}" ] && exit 1; exit 0 ;;
      mandataire-*) exit 0 ;;
      deps-*)
        cp "$HOME/tests/${nom#deps-}/deps-entree/commande.json" "$ET/commande-$nom.json"
        find "$deps" -type f > "$ET/deps-vu-$nom.txt"
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
# du : chemin = dernier argument ; --inodes : FAUX_DU_INODES ; ~/tests/.deps : 1 Go par dossier de cache (budget) ;
# <cache>.tmp : FAUX_DU_DEPS_KO (plafond).
DU = r'''for a in "$@"; do p="$a"; done
if [ "$1" = --inodes ]; then printf '%s\t%s\n' "${FAUX_DU_INODES:-10}" "$p"; exit 0; fi
case "$p" in
  */.deps) n=$(ls -d "$p"/*/*-*/ 2>/dev/null | grep -cv '\.tmp/$'); printf '%s\t%s\n' "$((n * 1048576))" "$p"; exit 0 ;;
  *.tmp) printf '%s\t%s\n' "${FAUX_DU_DEPS_KO:-4}" "$p"; exit 0 ;;
esac
printf '%s\t%s\n' 4 "$p"'''
# curl : dernier argument = l'URL ; FAUX_SOMMES « version=somme ... » ; FAUX_REDIRECTION : la distribution renvoie ailleurs.
CURL = r'''echo "curl $*" >> "$FAUX_JOURNAL"
o=""; w=""; prec=""
for a in "$@"; do [ "$prec" = -o ] && o="$a"; [ "$prec" = -w ] && w=1; prec="$a"; u="$a"; done
[ -n "${FAUX_CURL_ECHEC:-}" ] && exit 22
case "$u" in
  */versions/all) printf '%s' "$FAUX_VERSIONS" > "$o" ;;
  *-wrapper.jar.sha256) v="${u##*/gradle-}"; v="${v%-wrapper.jar.sha256}"; s=""
    for x in $FAUX_SOMMES; do [ "${x%%=*}" = "$v" ] && s="${x#*=}"; done
    [ -n "$s" ] || exit 22
    printf '%s\n' "$s" > "$o" ;;
  *.zip.sha256) printf '%s\n' "$FAUX_SOMME_ZIP" > "$o" ;;
  *.zip) if [ -n "${FAUX_REDIRECTION:-}" ]; then : > "$o"; printf '302 %s' "$FAUX_REDIRECTION"; exit 0; fi
         printf '%s' "''' + ZIP.decode() + r'''" > "$o"; [ -n "$w" ] && printf '200 ' ;;
  *) exit 22 ;;
esac
exit 0'''
FAUX = dict(banc.FAUX, docker=DOCKER, du=DU, curl=CURL)


def _tar(fichiers):
    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for nom, donnees in fichiers.items():
            info = tarfile.TarInfo(nom)
            info.size, info.mode = len(donnees), 0o755 if nom == "gradlew" else 0o644
            tar.addfile(info, io.BytesIO(donnees))
    return tampon.getvalue()


def _base36(n):
    chiffres = "0123456789abcdefghijklmnopqrstuvwxyz"
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = chiffres[r] + s
    return s or "0"


PROPS = b"distributionUrl=https\\://services.gradle.org/distributions/gradle-8.7-bin.zip\n"
TAR_NODE = _tar({"package.json": b'{"dependencies": {"a": "1"}}', "package-lock.json": b"{}", "src/a.js": b"1"})
TAR_GRADLE = _tar({"gradlew": b"#!/bin/sh\n", "settings.gradle": b"", "build.gradle": b"",
                   "gradle/wrapper/gradle-wrapper.jar": JAR, "gradle/wrapper/gradle-wrapper.properties": PROPS})
HACHE_DIST = _base36(int.from_bytes(hashlib.md5(
    b"https://services.gradle.org/distributions/gradle-8.7-bin.zip").digest(), "big"))
GRADLE = ("10", "myiafactory/tests-android", "gradle-jvm", "gradle")


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
                        FAUX_SOMMES="8.7=" + hashlib.sha256(JAR).hexdigest(), FAUX_SOMME_ZIP=hashlib.sha256(ZIP).hexdigest(),
                        FAUX_VERSIONS="[]")

    @property
    def journal(self):
        return self.journal_fichier.read_text(encoding="utf-8") if self.journal_fichier.exists() else ""

    def deps_racine(self, projet="projet-a"):
        return self.home / "tests" / ".deps" / projet

    def cache(self, projet="projet-a", nom=f"npm-{DEPS}"):
        return self.deps_racine(projet) / nom

    def preparer_cache(self, projet="projet-a", nom=f"npm-{DEPS}", age_s=0):
        c = self.cache(projet, nom)
        (c / "contenu" / "node_modules").mkdir(parents=True)
        for f in (".pret", ".utilise"):
            (c / f).write_text("x", encoding="utf-8")
        if age_s:
            t = time.time() - age_s
            for f in (".pret", ".utilise"):
                os.utime(c / f, (t, t))
        return c

    def demarrer(self, *supplement, ident=ID, tar=TAR_NODE, env=None, commande=banc.COMMANDE, deps=DEPS):
        entree = self.home / "tests" / ident / "entree"
        entree.mkdir(parents=True)
        (entree / "entree.tar").write_bytes(tar)
        etat = self.t / "etat" / ident
        etat.mkdir(parents=True, exist_ok=True)
        e = dict(self.env, FAUX_ETAT=etat.as_posix(), **(env or {}))
        args = ["bash", banc.SCRIPT.as_posix(), ident, "2", "4", "8192", "1800", "projet-a", deps, *supplement]
        err = open(etat / "err", "w+b")
        p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err, env=e)
        try:
            p.stdin.write((commande + "\n").encode())
            p.stdin.flush()
        except OSError:
            pass
        return p, err, etat

    def finir(self, lance):
        p, err, etat = lance
        try:
            code = p.wait(timeout=90)
        finally:
            if p.poll() is None:
                p.kill()
            p.stdin.close()
        err.seek(0)
        lignes = [x for x in err.read().decode("utf-8", "replace").split("\n") if x]
        err.close()
        self.assertTrue(banc.FIN.match(lignes[-1]), lignes[-5:])
        return code, lignes, etat

    def lancer(self, *supplement, **k):
        """(code, lignes de la sortie d'erreur, dossier d'état du faux docker)."""
        return self.finir(self.demarrer(*supplement, **k))

    def tenir(self, fichier, mode="-s"):
        """Un processus bash qui tient `fichier` (faux flock) jusqu'à ce qu'on ferme son entrée."""
        p = subprocess.Popen(["bash", "-c", f'exec 5>> "$1"; flock {mode} -n 5 || exit 1; read x', "x", banc._msys(fichier)],
                             stdin=subprocess.PIPE, env=self.env)
        fin = time.time() + 20
        while not list(fichier.parent.glob(fichier.name + ".*")) and time.time() < fin:
            time.sleep(0.05)
        return p

    @staticmethod
    def lacher(p):
        p.stdin.close()
        p.wait(timeout=10)

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
        self.assertEqual(json.loads((etat / f"commande-deps-{ID}.json").read_text(encoding="utf-8"))[-3:],
                         ["--echauffer", "npm", "node"])
        c = self.cache()
        self.assertTrue((c / ".pret").exists() and (c / "contenu" / "node_modules" / "a.js").exists())
        self.assertFalse(Path(str(c) + ".tmp").exists())
        ordre = [x for x in (etat / "ordre-runs").read_text(encoding="utf-8").split() if not x.startswith(("essai-", "mandataire-"))]
        self.assertEqual(ordre, [f"deps-{ID}", f"tests-{ID}"])                  # échauffement avant les tests
        code, err, etat_b = self.lancer(*NPM, "refuse", "40", ident=ID_B)
        self.assertEqual(code, 0, err)
        self.assertNotIn(f"deps-{ID_B}", (etat_b / "ordre-runs").read_text(encoding="utf-8").split())   # aucun deps-*

    def test_seul_l_echauffement_a_le_reseau_et_jamais_bridge(self):
        # C1 / I6 : même npm passe par le réseau interne et le mandataire (le verrou npm choisit ses hôtes) ; DNS coupé.
        code, err, etat = self.lancer(*NPM, "refuse", "40")
        self.assertEqual(code, 0, err)
        deps_run, tests_run = self.run_de(etat, f"deps-{ID}"), self.run_de(etat, f"tests-{ID}")
        self.assertEqual([b for a, b in self.paires(tests_run) if a == "--network"], ["none"])
        self.assertEqual([b for a, b in self.paires(deps_run) if a == "--network"], [f"deps-{ID}"])
        self.assertNotIn("bridge", deps_run)
        self.assertIn(("--dns", "0.0.0.0"), self.paires(deps_run))
        self.assertIn(("--add-host", f"mandataire:{IP_MANDATAIRE}"), self.paires(deps_run))
        env = [b for a, b in self.paires(deps_run) if a == "-e"]
        self.assertIn("HTTPS_PROXY=http://mandataire:3128", env)
        self.assertFalse([x for x in env if re.search(r"(?i)token|jeton|cle|key|secret", x)], env)
        mandataire = self.run_de(etat, f"mandataire-{ID}")
        self.assertEqual([b for a, b in self.paires(mandataire) if a == "--network"], [f"deps-{ID}"])   # M4 : interne d'abord
        self.assertIn(f"docker network connect bridge mandataire-{ID}", self.journal)
        self.assertEqual(mandataire[mandataire.index("--mandataire") + 3:], ["registry.npmjs.org"])
        for args in (deps_run, tests_run):
            for paire in (("--cap-drop", "ALL"), ("--user", "1000:1000"), ("--security-opt", "no-new-privileges")):
                self.assertIn(paire, self.paires(args))
            self.assertIn("--read-only", args)
            self.assertFalse(any("docker.sock" in a or a == "--privileged" for a in args))
        self.assertIn(("--label", "myiafactory.genre=tests-deps"), self.paires(deps_run))

    def test_code_du_projet_seulement_avec_accord(self):
        # C1 : dotnet et cargo exécutent du code choisi par le projet : accord exigé, comme Gradle.
        for i, (famille, cle, image) in enumerate((("gradle-jvm", "gradle", "myiafactory/tests-android"),
                                                   ("dotnet", "dotnet", "myiafactory/tests-0123456789ab"),
                                                   ("rust", "cargo", "myiafactory/tests-0123456789ab"))):
            with self.subTest(cle=cle):
                ident = banc.ident(i)
                code, err, etat = self.lancer("10", image, famille, cle, "refuse", "40", tar=TAR_GRADLE, ident=ident)
                self.assertEqual(code, 79, err)
                self.assertIn("#deps-echec reseau-non-accorde", err)
                self.assertIsNone(self.run_de(etat, f"deps-{ident}"))
        code, err, etat = self.lancer(*GRADLE, "accorde", "40", tar=TAR_GRADLE, ident=ID_B)
        self.assertEqual(code, 0, err)
        mandataire = self.run_de(etat, f"mandataire-{ID_B}")
        hotes = mandataire[mandataire.index("--mandataire") + 3:]
        self.assertIn("plugins.gradle.org", hotes)
        self.assertFalse([h for h in hotes if "github" in h or h in ("services.gradle.org", "downloads.gradle.org")], hotes)
        self.assertIn(f"docker network rm deps-{ID_B}", self.journal)
        self.assertIn(f"docker rm -f mandataire-{ID_B}", self.journal)
        self.assertEqual([b for a, b in self.paires(self.run_de(etat, f"tests-{ID_B}")) if a == "--network"], ["none"])
        self.assertIn(f"timeout -k 30 1800 sudo -n docker run", self.journal)    # M3
        self.assertEqual(mandataire[mandataire.index("--entrypoint") + 2], "myiafactory/tests")   # M5 : image de base fixe

    def test_distribution_gradle_par_l_hote(self):
        # I4 : la distribution est téléchargée par l'hôte, vérifiée, déposée dans le cache ; redirection hors liste refusée.
        code, err, etat = self.lancer(*GRADLE, "accorde", "40", tar=TAR_GRADLE, ident=banc.ident(5), deps="2" * 16,
                                      env={"FAUX_REDIRECTION": "https://github.com/gradle/x.zip"})
        self.assertEqual(code, 79, err)
        self.assertIn("#deps-echec distribution-redirection", err)
        code, err, etat = self.lancer(*GRADLE, "accorde", "40", tar=TAR_GRADLE, ident=ID_B, deps="1" * 16,
                                      env=dict(FAUX_SOMME_ZIP="0" * 64))
        self.assertEqual(code, 79, err)
        self.assertIn("#deps-echec distribution-somme", err)
        code, err, etat = self.lancer(*GRADLE, "accorde", "40", tar=TAR_GRADLE)
        self.assertEqual(code, 0, err)
        zip_ = self.cache(nom=f"gradle-{DEPS}") / "contenu" / "gradle" / "wrapper" / "dists" / "gradle-8.7-bin" / HACHE_DIST / \
            "gradle-8.7-bin.zip"
        self.assertEqual(zip_.read_bytes(), ZIP)
        self.assertIn("https://services.gradle.org/distributions/gradle-8.7-bin.zip.sha256", self.journal)
        self.assertNotRegex(self.journal, r"curl [^\n]*-L")
        vu = (etat / f"deps-vu-deps-{ID}.txt").read_text(encoding="utf-8")
        self.assertIn("gradle-8.7-bin.zip", vu)                                   # présente AVANT le conteneur

    def test_wrapper_contre_toutes_les_sommes_publiees(self):
        # I4 : un jar d'une autre version publiée est admis ; un jar inconnu de toutes les versions est refusé.
        versions = json.dumps([{"version": v, "wrapperChecksumUrl":
                                f"https://services.gradle.org/distributions/gradle-{v}-wrapper.jar.sha256"} for v in ("8.7", "8.6")]
                              + [{"version": "9.9", "wrapperChecksumUrl": "https://evil.example/x.sha256"}])
        env = {"FAUX_VERSIONS": versions, "FAUX_SOMMES": "8.7=" + "a" * 64 + " 8.6=" + hashlib.sha256(JAR).hexdigest()}
        code, err, etat = self.lancer(*GRADLE, "accorde", "40", tar=TAR_GRADLE, env=env)
        self.assertEqual(code, 0, err)
        self.assertIn("https://services.gradle.org/versions/all", self.journal)
        self.assertNotIn("evil.example", self.journal)
        env["FAUX_SOMMES"] = "8.7=" + "a" * 64 + " 8.6=" + "b" * 64
        (self.home / "tests" / ".deps" / ".gradle-wrapper" / "8.6.sha256").write_text("b" * 64 + "\n", encoding="utf-8")
        code, err, etat = self.lancer(*GRADLE, "accorde", "40", tar=_tar({"gradlew": b"", "settings.gradle": b"",
                                      "gradle/wrapper/gradle-wrapper.jar": b"autre", "gradle/wrapper/gradle-wrapper.properties": PROPS}),
                                      ident=ID_B, env=env)
        self.assertEqual(code, 79, err)
        self.assertIn("#deps-echec wrapper-modifie", err)
        self.assertNotIn(f"--name deps-{ID_B}", self.journal)                      # rien n'est lancé pour ce jar
        self.assertNotIn(f"--name tests-{ID_B}", self.journal)
        code, err, etat = self.lancer(*GRADLE, "accorde", "40", tar=_tar({"gradlew": b"", "settings.gradle": b""}),
                                      ident=banc.ident(4))
        self.assertEqual(code, 79, err)
        self.assertIn("#deps-echec wrapper-absent", err)

    def test_echec_deps_code_79_rien_de_pret_et_memoire_d_une_heure(self):
        for i, env, raison in ((0, {"FAUX_DEPS_CODE": "1"}, "echauffement"),
                               (1, {"FAUX_DU_DEPS_KO": str(3 * 1048576)}, "plafond"),
                               (2, {"FAUX_DU_INODES": "600000"}, "inodes")):
            with self.subTest(raison=raison):
                ident = banc.ident(i)
                deps = "%016x" % (i + 1)
                code, err, etat = self.lancer(*NPM, "refuse", "40", ident=ident, env=env, deps=deps)
                self.assertEqual(code, 79, err)
                self.assertIn(f"#deps-echec {raison}", err)
                self.assertEqual(err[-2], "#refus 79")
                self.assertIsNone(self.run_de(etat, f"tests-{ident}"))
                self.assertFalse(self.cache(nom=f"npm-{deps}").exists())
                self.assertFalse(Path(str(self.cache(nom=f"npm-{deps}")) + ".tmp").exists())
                self.assertFalse((self.home / "tests" / ident).exists())
                self.assertIn(f"docker rm -f deps-{ident}", self.journal)
        # I5 : l'échec est mémorisé une heure : repli immédiat, sans nouvel échauffement
        code, err, etat = self.lancer(*NPM, "refuse", "40", ident=banc.ident(3), deps="%016x" % 1)
        self.assertEqual(code, 79, err)
        self.assertIn("#deps-echec echauffement", err)
        self.assertIsNone(self.run_de(etat, f"deps-{banc.ident(3)}"))
        marque = self.deps_racine() / ("npm-%016x.echec" % 1)
        marque.write_text("%d echauffement\n" % (time.time() - 3700), encoding="utf-8")   # plus d'une heure : on réessaie
        code, err, etat = self.lancer(*NPM, "refuse", "40", ident=banc.ident(6), deps="%016x" % 1)
        self.assertEqual(code, 0, err)
        self.assertFalse(marque.exists())

    def test_copie_sur_ecriture_essayee(self):
        c = self.preparer_cache()
        code, err, etat = self.lancer(*NPM, "refuse", "40")
        self.assertEqual(code, 0, err)
        self.assertIsNone(self.run_de(etat, f"deps-{ID}"))
        m = re.search(r"docker volume create (.*) tests-deps-" + ID, self.journal)
        self.assertIsNotNone(m, self.journal)
        self.assertIn("--opt type=overlay", m.group(1))
        self.assertRegex(m.group(1), rf"o=lowerdir=\S*/\.deps/projet-a/npm-{DEPS}/contenu,upperdir=\S*/tests/{ID}/deps-haut,"
                                     rf"workdir=\S*/tests/{ID}/deps-ov")
        essai = self.run_de(etat, f"essai-deps-{ID}")                            # I1 : le volume est monté une fois pour voir
        self.assertIsNotNone(essai)
        self.assertIn(("--network", "none"), self.paires(essai))
        self.assertIn("--rm", essai)
        tests_run = self.run_de(etat, f"tests-{ID}")
        self.assertIn(("--mount", f"type=volume,src=tests-deps-{ID},dst=/deps"), self.paires(tests_run))
        self.assertIn(f"docker volume rm -f tests-deps-{ID}", self.journal)
        self.assertRegex(self.journal, r"flock -s \d")
        self.assertFalse((self.home / "tests" / ID).exists())
        self.assertTrue((c / "contenu" / "node_modules").is_dir())
        code, err, etat = self.lancer(*NPM, "refuse", "40", ident=ID_B, env={"FAUX_SANS_OVERLAY": "1"})
        self.assertEqual(code, 79, err)
        self.assertIn("#deps-echec copie-sur-ecriture", err)
        # SDK : overlay refusé à l'essai → lecture seule
        (self.home / "android-sdk").mkdir()
        code, err, etat = self.lancer("10", "myiafactory/tests-android", "gradle-android", ident=banc.ident(7), deps="-",
                                      env={"FAUX_SANS_OVERLAY": "1"})
        self.assertEqual(code, 0, err)
        run = self.run_de(etat, f"tests-{banc.ident(7)}")
        self.assertTrue([a for a in run if a.endswith("/android-sdk:/opt/android-sdk:ro")], run)
        self.assertNotIn("--mount", run)

    def test_drapeaux_hors_ligne(self):
        self.preparer_cache(nom=f"gradle-{DEPS}")
        code, err, etat = self.lancer(*GRADLE, "accorde", "40", tar=TAR_GRADLE, commande=json.dumps(["./gradlew", "test"]))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads((etat / f"commande-tests-{ID}.json").read_text(encoding="utf-8")),
                         ["./gradlew", "--offline", "--no-daemon", "test"])
        env = [b for a, b in self.paires(self.run_de(etat, f"tests-{ID}")) if a == "-e"]
        self.assertIn("GRADLE_USER_HOME=/deps/gradle", env)
        self.preparer_cache(nom=f"cargo-{DEPS}")
        code, err, etat = self.lancer("10", "myiafactory/tests-0123456789ab", "rust", "cargo", "accorde", "40", ident=ID_B,
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
        vieux = time.time() - 8 * 86400
        os.utime(c / ".pret", (vieux, vieux))
        code, err, etat = self.lancer(*NPM, "refuse", "40", ident=ID_B, env={"FAUX_VERROU_PRODUIT": "1"})
        self.assertEqual(code, 0, err)
        self.assertIsNotNone(self.run_de(etat, f"deps-{ID_B}"))
        self.assertGreater((c / ".pret").stat().st_mtime, vieux + 86400)
        code, err, etat = self.lancer(*NPM, "refuse", "40", ident=banc.ident(3))
        self.assertIsNone(self.run_de(etat, f"deps-{banc.ident(3)}"))

    def test_deux_caches_et_budget(self):
        anciens = {("projet-a", "npm-1111111111111111"): 400, ("projet-a", "npm-2222222222222222"): 300,
                   ("projet-b", "pip-3333333333333333"): 200, ("projet-b", "npm-4444444444444444"): 100}
        for (projet, nom), age in anciens.items():
            self.preparer_cache(projet, nom, age)
        code, err, etat = self.lancer(*NPM, "refuse", "2")
        self.assertEqual(code, 0, err)
        restants = sorted(p.parent.name + "/" + p.name for p in (self.home / "tests" / ".deps").glob("*/*")
                          if p.is_dir())
        self.assertEqual(restants, [f"projet-a/npm-{DEPS}", "projet-b/npm-4444444444444444"])   # I2 : ni .supprime-* restant
        self.assertTrue((self.cache() / ".utilise").exists())

    def test_cache_tenu_jamais_efface(self):
        # I2 : le verrou est HORS du dossier du cache (<projet>/.<nom>.verrou)
        self.preparer_cache(nom="npm-1111111111111111", age_s=400)
        self.preparer_cache(nom="npm-2222222222222222", age_s=300)
        p = self.tenir(self.deps_racine() / ".npm-1111111111111111.verrou")
        try:
            code, err, etat = self.lancer(*NPM, "refuse", "1")
            self.assertEqual(code, 0, err)
        finally:
            self.lacher(p)
        self.assertTrue(self.cache(nom="npm-1111111111111111").exists())
        self.assertFalse(self.cache(nom="npm-2222222222222222").exists())
        self.assertTrue((self.deps_racine() / ".npm-2222222222222222.verrou").exists())   # M3 (relecture 2) : jamais effacé
        self.assertTrue(self.cache().exists())
        self.assertFalse((self.cache() / ".verrou").exists())

    def test_echauffements_simultanes_bornes(self):
        # I3 : deux échauffements au plus à la fois ; la troisième campagne attend (#attente) ; /work borné (tmpfs, inodes).
        (self.home / "taches").mkdir()
        tenus = [self.tenir(self.home / "taches" / f".echauffement-{i}", "-x") for i in (1, 2)]
        try:
            lance = self.demarrer(*NPM, "refuse", "40")
            fin = time.time() + 30
            while "#attente" not in (lance[2] / "err").read_text(encoding="utf-8", errors="replace") and time.time() < fin:
                time.sleep(0.1)
            self.assertIsNone(self.run_de(lance[2], f"deps-{ID}"))
        finally:
            for p in tenus:
                self.lacher(p)
        code, err, etat = self.finir(lance)
        self.assertEqual(code, 0, err)
        deps_run = self.run_de(etat, f"deps-{ID}")
        self.assertIn(("--tmpfs", "/work:size=2g,nr_inodes=500000,mode=1777,exec"), self.paires(deps_run))
        self.assertFalse([a for a in deps_run if a.endswith(":/work")])

    def test_distribution_tronquee_et_liste_incomplete(self):
        # I1 (relecture 2) : un zip présent mais tronqué n'est jamais copié tel quel ; fichiers temporaires propres à la
        # campagne ; une liste des versions incomplète ne pose pas `.liste`.
        dist = self.home / "tests" / ".deps" / ".gradle-wrapper" / "dist"
        dist.mkdir(parents=True)
        (dist / "gradle-8.7-bin.zip").write_bytes(ZIP[:5])
        code, err, etat = self.lancer(*GRADLE, "accorde", "40", tar=TAR_GRADLE)
        self.assertEqual(code, 0, err)
        zip_ = self.cache(nom=f"gradle-{DEPS}") / "contenu" / "gradle" / "wrapper" / "dists" / "gradle-8.7-bin" / HACHE_DIST / \
            "gradle-8.7-bin.zip"
        self.assertEqual(zip_.read_bytes(), ZIP)
        self.assertIn(f"gradle-8.7-bin.zip.tmp-{ID}", self.journal)
        versions = json.dumps([{"version": v, "wrapperChecksumUrl":
                                f"https://services.gradle.org/distributions/gradle-{v}-wrapper.jar.sha256"} for v in ("8.7", "8.6")])
        autre = _tar({"gradlew": b"", "settings.gradle": b"", "gradle/wrapper/gradle-wrapper.jar": b"autre",
                      "gradle/wrapper/gradle-wrapper.properties": PROPS})
        code, err, etat = self.lancer(*GRADLE, "accorde", "40", tar=autre, ident=ID_B, env={"FAUX_VERSIONS": versions})
        self.assertEqual(code, 79, err)                                           # 8.6 injoignable : liste incomplète
        self.assertFalse((self.home / "tests" / ".deps" / ".gradle-wrapper" / ".liste").exists())

    def test_panne_memoire_non_retenue(self):
        # I2 (relecture 2) : /work (tmpfs) est ajouté à la mémoire ; un 137 sans marque du surveillant = `memoire`, jamais
        # retenu une heure.
        code, err, etat = self.lancer(*NPM, "refuse", "40", env={"FAUX_DEPS_CODE": "137"})
        self.assertEqual(code, 79, err)
        self.assertIn("#deps-echec memoire", err)
        self.assertFalse(list(self.deps_racine().glob("*.echec")))
        deps_run = self.run_de(etat, f"deps-{ID}")
        self.assertIn(("--memory", f"{8192 + 2 * 1024}m"), self.paires(deps_run))
        self.assertIn(("--memory-swap", f"{8192 + 2 * 1024}m"), self.paires(deps_run))

    def test_pannes_passageres_retenues_cinq_minutes(self):
        # M4 (relecture 2) : mandataire, réseau interne, distribution injoignable : 5 min, pas 1 h.
        self.deps_racine().mkdir(parents=True)
        marque = self.deps_racine() / f"npm-{DEPS}.echec"
        marque.write_text("%d mandataire\n" % (time.time() - 100), encoding="utf-8")
        code, err, etat = self.lancer(*NPM, "refuse", "40")
        self.assertEqual(code, 79, err)
        self.assertIn("#deps-echec mandataire", err)
        marque.write_text("%d mandataire\n" % (time.time() - 400), encoding="utf-8")
        code, err, etat = self.lancer(*NPM, "refuse", "40", ident=ID_B)
        self.assertEqual(code, 0, err)

    def test_balayage_des_restes(self):
        # M2 : <cache>.tmp dont la préparation est morte et .supprime-* effacés (chmod d'abord)
        tmp = self.deps_racine() / f"npm-{'9' * 16}.tmp"
        (tmp / "contenu" / "ro").mkdir(parents=True)
        supprime = self.deps_racine() / ".supprime-123-npm-x"
        supprime.mkdir()
        code, err, etat = self.lancer(*NPM, "refuse", "40", deps="-")
        self.assertEqual(code, 0, err)
        self.assertFalse(tmp.exists())
        self.assertFalse(supprime.exists())
        self.assertRegex(self.journal, r"chmod -R u\+rwX -- \S*npm-9{16}\.tmp")


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
        self.assertEqual(h(["python3", "-m", "pytest"], "gradle"), ["python3", "-m", "pytest"])
        self.assertEqual(h(["npm", "test"], "npm"), ["npm", "test"])
        self.assertEqual(h(["cargo"] + ["x"] * 63, "cargo"), ["cargo"] + ["x"] * 63)

    def test_mandataire_liste_fermee_et_ecoute_interne(self):
        permis = self.aide.hote_permis
        hotes = ("plugins.gradle.org", "repo.maven.apache.org")
        self.assertEqual(permis("CONNECT plugins.gradle.org:443 HTTP/1.1", hotes), "plugins.gradle.org")
        self.assertEqual(permis("CONNECT Plugins.Gradle.org:443 HTTP/1.1", hotes), "plugins.gradle.org")
        for refus in ("CONNECT evil.example:443 HTTP/1.1", "CONNECT plugins.gradle.org:22 HTTP/1.1",
                      "GET http://plugins.gradle.org/ HTTP/1.1", "CONNECT 10.0.0.1:443 HTTP/1.1",
                      "CONNECT plugins.gradle.org.evil.example:443 HTTP/1.1", "CONNECT plugins.gradle.org:443 HTTP/1.1 x"):
            self.assertIsNone(permis(refus, hotes), refus)
        with mock.patch("socket.gethostbyname", return_value="172.30.0.2"):            # M4
            self.assertEqual(self.aide.adresse_interne(), "172.30.0.2")
        with mock.patch("socket.gethostbyname", return_value="127.0.1.1"):
            with self.assertRaises(ValueError):
                self.aide.adresse_interne()

    def test_plan_d_echauffement(self):
        with tempfile.TemporaryDirectory() as t:
            w = Path(t)
            (w / "package.json").write_text("{}", encoding="utf-8")
            (w / "src").mkdir()
            (w / "src" / "a.js").write_text("1", encoding="utf-8")
            plan = self.aide.plan_echauffement("npm", "node", str(w))
            self.assertEqual(plan["etapes"][0]["commande"][:2], ["npm", "install"])
            self.assertIn("--ignore-scripts", plan["etapes"][0]["commande"])
            self.assertEqual((plan["etapes"][0]["env"]["YARN_IGNORE_PATH"],
                              plan["etapes"][0]["env"]["COREPACK_ENABLE_UNSAFE_CUSTOM_URLS"]), ("1", "0"))   # C1
            self.assertEqual(plan["produit"], "package-lock.json")
            self.assertFalse((w / "src" / "a.js").exists())
            (w / "package-lock.json").write_text("{}", encoding="utf-8")
            self.assertEqual(self.aide.plan_echauffement("npm", "node", str(w))["etapes"][0]["commande"][:2], ["npm", "ci"])
            (w / ".yarnrc.yml").write_text("yarnPath: x.cjs\n", encoding="utf-8")
            with self.assertRaises(ValueError):                                              # C1 : yarn berry sans accord
                self.aide.plan_echauffement("yarn", "node", str(w))
            with self.assertRaises(ValueError):
                self.aide.plan_echauffement("unity", "unity", str(w))

    def test_requirements_sans_option_ni_url(self):
        # C2 : seules des exigences nommées et `-r` vers un fichier local du projet
        for refus in ("--index-url https://evil/simple\na==1\n", "--extra-index-url https://x\n", "-f https://x\n",
                      "--find-links /tmp\n", "--trusted-host x\n", "-r ../dehors.txt\n", "a @ https://evil/a.whl\n",
                      "https://evil/a.tar.gz\n", "-e .\n", "./local\n", "-i https://x\n"):
            with self.subTest(refus=refus), tempfile.TemporaryDirectory() as t:
                (Path(t) / "requirements.txt").write_text(refus, encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.aide.plan_echauffement("pip", "python", t)
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "requirements.txt").write_text("-r requirements-base.txt\nb>=2  # commentaire\n", encoding="utf-8")
            (Path(t) / "requirements-base.txt").write_text("a==1 ; python_version >= '3.8'\n", encoding="utf-8")
            plan = self.aide.plan_echauffement("pip", "python", t)
            self.assertIn("--only-binary=:all:", plan["etapes"][1]["commande"])
            self.assertIn("https://pypi.org/simple", plan["etapes"][1]["commande"])
            self.assertFalse(any("freeze" in x for e in plan["etapes"] for x in e["commande"]))   # gel sans le Python du venv

    def test_gel_sans_executer_le_venv(self):
        with tempfile.TemporaryDirectory() as t:
            sp = Path(t) / "venv" / "lib" / "python3.12" / "site-packages"
            (sp / "a-1.0.dist-info").mkdir(parents=True)
            (sp / "a-1.0.dist-info" / "METADATA").write_text("Metadata-Version: 2.1\nName: a\nVersion: 1.0\n", encoding="utf-8")
            (sp / "piege.pth").write_text("import os; open(%r, 'w').write('x')\n" % str(Path(t) / "execute"), encoding="utf-8")
            self.assertEqual(self.aide.geler(str(Path(t) / "venv")), "a==1.0\n")
            self.assertFalse((Path(t) / "execute").exists())

    def test_derniere_distribution_url(self):
        # M1 : la DERNIÈRE distributionUrl fait foi (comme java.util.Properties)
        with tempfile.TemporaryDirectory() as t:
            tar = Path(t) / "e.tar"
            tar.write_bytes(_tar({"gradle/wrapper/gradle-wrapper.jar": JAR, "gradle/wrapper/gradle-wrapper.properties":
                                  PROPS + b"distributionUrl=https\\://evil.example/gradle-8.7-bin.zip\n"}))
            with self.assertRaises(ValueError):
                self.aide.wrapper_gradle(str(tar))
            tar.write_bytes(_tar({"gradle/wrapper/gradle-wrapper.jar": JAR, "gradle/wrapper/gradle-wrapper.properties":
                                  b"distributionUrl=https\\://evil.example/x.zip\n" + PROPS}))
            somme, version, genre, hache = self.aide.wrapper_gradle(str(tar))
            self.assertEqual((somme, version, genre, hache), (hashlib.sha256(JAR).hexdigest(), "8.7", "bin", HACHE_DIST))


class TestProfilEtRoute(unittest.TestCase):
    def test_table_des_echauffements_miroir_de_l_enveloppe(self):
        texte = banc.SCRIPT.read_text(encoding="utf-8")
        for cle, e in tests_profil.ECHAUFFEMENTS.items():
            m = re.search(rf"^ECH\[{re.escape(cle)}\]=\"(\d+) (\d+) ([01])\"", texte, re.M)
            self.assertIsNotNone(m, cle)
            self.assertEqual((int(m.group(1)), int(m.group(2)), m.group(3) == "1"),
                             (e["duree_s"], e["plafond_go"], e["execute_du_code"]), cle)
            if cle != "unity":
                self.assertRegex(texte, rf"(?m)^ECH_HOTES\[{re.escape(cle)}\]=\"[a-z0-9. -]+\"", cle)
        code = {k for k, e in tests_profil.ECHAUFFEMENTS.items() if e["execute_du_code"]}
        self.assertEqual(code, {"gradle", "maven", "pip-sources", "unity", "dotnet", "cargo", "yarn-berry"})   # C1
        self.assertNotRegex(texte, r"(?m)^ECH_HOTES\[[a-z-]+\]=\"[^\"]*github")

    def test_yarn_berry_et_gestionnaires(self):
        with tempfile.TemporaryDirectory() as t:
            r = Path(t)
            (r / "package.json").write_text('{"scripts": {"test": "jest"}, "dependencies": {"a": "1"}}', encoding="utf-8")
            (r / "yarn.lock").write_text("x", encoding="utf-8")
            self.assertEqual(tests_profil.cle_echauffement(tests_profil.analyser(str(r))), "yarn")
            (r / "package.json").write_text('{"packageManager": "yarn@4.1.0", "dependencies": {"a": "1"}}', encoding="utf-8")
            self.assertEqual(tests_profil.cle_echauffement(tests_profil.analyser(str(r))), "yarn-berry")

    def test_empreinte_deps(self):
        with tempfile.TemporaryDirectory() as t:
            r = Path(t)
            (r / "package.json").write_text('{"scripts": {"test": "jest"}, "dependencies": {"a": "1"}}', encoding="utf-8")
            sans = tests_profil.empreinte_deps(tests_profil.analyser(str(r)), str(r))
            self.assertRegex(sans, r"^[0-9a-f]{16}$")
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
            self.assertIsNone(tests_profil.empreinte_deps(tests_profil.analyser(t), t))
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
        self.assertEqual(tests_images.choisir_image(fridge, dict(sdk, licences=[]))["manque"], ["licenses;android-sdk-license"])


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
        self.assertEqual(len(self.poste), 1)
        self.assertTrue(any("échauffement" in d for d in self.dits), self.dits)
        self.assertTrue(ssh.flux[0].endswith(f" projet-a {DEPS} 10 myiafactory/tests node npm refuse 40"), ssh.flux[0])

    def test_code_du_projet_sans_accord_reste_au_poste(self):
        # dotnet et cargo passent d'abord par une image dérivée (pas encore servie par la route) : leur accord est vérifié par
        # la table (test_table_des_echauffements_miroir_de_l_enveloppe) et au serveur (test_code_du_projet_seulement_avec_accord).
        self.assertEqual(tests_profil.cle_echauffement(Profil(familles=("dotnet",))), "dotnet")
        self.assertTrue(tests_profil.ECHAUFFEMENTS["dotnet"]["execute_du_code"])
        for profil in (Profil(familles=("gradle-jvm",), outils={"jdk": "17"}, deps={"gradle-jvm": {"gestionnaire": "gradle"}}),):
            with self.subTest(familles=profil.familles):
                ssh = FauxSsh()
                self.assertEqual(self.lancer(ssh, profil), 0)
                self.assertEqual((ssh.octets, ssh.flux), ([], []))
                self.assertTrue(any("échauffement réseau non accordé" in d for d in self.dits), self.dits)
        jvm = Profil(familles=("gradle-jvm",), outils={"jdk": "17"}, deps={"gradle-jvm": {"gestionnaire": "gradle"}})
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
