"""Enveloppe hôte des campagnes de tests (`serveur_ovh/taches/lancer_tests.sh`) et ses aides (`taches/tests_hote.py`).

L'enveloppe tourne avec le bash du poste et un PATH de faux (`docker`, `sudo`, `timeout`, `df`, `id`, `flock`, `python3` qui
renvoie à l'interpréteur des tests), `HOME` temporaire : aucun vrai conteneur, aucun serveur. Le faux `flock` tient un verrou
par fichier (`<fichier>.tenu`, PID du shell qui l'a pris ; libre si ce PID ne vit plus). Les aides se testent en pur Python
(archives piégées, commande, relais)."""
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
TACHES = RACINE / "serveur_ovh" / "taches"
SCRIPT = TACHES / "lancer_tests.sh"
ID = "t20261123-101500-ab12"
ID_B = "t20261123-101501-cd34"
COMMANDE = json.dumps(["python3", "-m", "unittest", "-q"])
FIN = re.compile(r"^#fin (\d+) (\d+) (\d+) (\d+)$")


def _charger_aide():
    spec = importlib.util.spec_from_file_location("tests_hote", TACHES / "tests_hote.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _msys(chemin):
    """C:/x -> /c/x : un HOME sans deux-points (l'enveloppe refuse un chemin de montage qui en porte)."""
    p = Path(chemin).as_posix()
    return "/" + p[0].lower() + p[2:] if re.match(r"^[A-Za-z]:/", p) else p


DOCKER = r'''echo "docker $*" >> "$FAUX_JOURNAL"
case "$1" in
  image) [ -n "${FAUX_SANS_IMAGE:-}" ] && exit 1; exit 0 ;;
  ps) [ -n "${FAUX_PS_NOMS:-}" ] && printf '%s\n' "$FAUX_PS_NOMS"; exit 0 ;;
  kill) touch "$FAUX_ETAT/tue"; exit 0 ;;
  rm) exit 0 ;;
  run)
    nom=""; prec=""
    for a in "$@"; do [ "$prec" = --name ] && nom="$a"; prec="$a"; done
    printf '%s\n' "$@" > "$FAUX_ETAT/run-$nom.txt"
    cp "$HOME/tests/${nom#tests-}/entree/commande.json" "$FAUX_ETAT/commande-$nom.json"
    echo "$nom" >> "$FAUX_ETAT/ordre"
    if [ -n "${FAUX_ATTENDRE:-}" ]; then
      while [ ! -e "$FAUX_ETAT/tue" ]; do sleep 0.05; done
      exit 137
    fi
    [ -n "${FAUX_SORTIE:-}" ] && printf '%s' "$FAUX_SORTIE"
    [ -n "${FAUX_ERREUR:-}" ] && printf '%s' "$FAUX_ERREUR" >&2
    exit "${FAUX_CODE:-0}" ;;
esac
exit 0'''
FLOCK = r'''echo "flock $*" >> "$FAUX_JOURNAL"
case "$1" in -n) mode=prendre ;; -u) mode=rendre ;; *) exit 64 ;; esac
f=$(readlink "/proc/$$/fd/$2") || exit 1
v="$f.tenu"
p=""; [ -f "$v" ] && read -r p < "$v"
if [ "$mode" = rendre ]; then
  [ "$p" = "$PPID" ] && rm -f "$v"
  exit 0
fi
[ "$p" = "$PPID" ] && exit 0
if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then exit 1; fi
[ -n "$p" ] && rm -f "$v"
set -C
echo "$PPID" 2>/dev/null > "$v"'''
FAUX = {
    "docker": DOCKER,
    "flock": FLOCK,
    "sudo": '[ "$1" = -n ] && shift\nexec "$@"',
    "timeout": 'echo "timeout $*" >> "$FAUX_JOURNAL"\nshift\nexec "$@"',
    "df": 'echo "Filesystem 1024-blocks Used Available Capacity Mounted on"\n'
          'echo "/dev/sda1 100000000 1 ${FAUX_DF_KO:-20000000} 1% /"',
    "id": 'echo "${FAUX_UID:-1000}"',
    "python3": f'exec "{Path(sys.executable).as_posix()}" "$@"',
}


def _instantane():
    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        info = tarfile.TarInfo("tests/test_a.py")
        donnees = b"print('a')\n"
        info.size, info.mode = len(donnees), 0o644
        tar.addfile(info, io.BytesIO(donnees))
    return tampon.getvalue()


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEnveloppeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.racine = Path(cls._t.name)
        cls.bin = cls.racine / "bin"
        cls.bin.mkdir()
        for nom, corps in FAUX.items():
            (cls.bin / nom).write_text("#!/bin/sh\n" + corps + "\n", newline="\n")
            (cls.bin / nom).chmod(0o755)
        cls.tar = _instantane()
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def setUp(self):
        type(self).n += 1
        t = self.racine / f"c{self.n}"
        self.home, self.etat = t / "home", t / "etat"
        self.home.mkdir(parents=True)
        self.etat.mkdir()
        self.journal_fichier = t / "appels.txt"
        self.env = dict(os.environ, HOME=_msys(self.home), PATH=self.bin.as_posix() + os.pathsep + os.environ["PATH"],
                        FAUX_JOURNAL=self.journal_fichier.as_posix(), FAUX_ETAT=self.etat.as_posix(),
                        ENVELOPPE_SONDE_S="0.05")
        self.deposer(ID)

    def deposer(self, ident):
        entree = self.home / "tests" / ident / "entree"
        entree.mkdir(parents=True)
        (entree / "entree.tar").write_bytes(self.tar)

    def demarrer(self, *args, ident=ID, env=None):
        corps = list(args) if args else ["2", "4", "8192", "1800", "projet-a", "-"]
        e = dict(self.env, **(env or {}))
        t = self.journal_fichier.parent
        sortie, erreur = open(t / f"{ident}.out", "w+b"), open(t / f"{ident}.err", "w+b")
        p = subprocess.Popen(["bash", SCRIPT.as_posix(), ident, *corps], stdin=subprocess.PIPE, stdout=sortie,
                             stderr=erreur, env=e)
        p.fichiers = (sortie, erreur)
        return p

    def ecrire(self, p, texte=COMMANDE):
        try:
            p.stdin.write(texte.encode("utf-8") + b"\n")
            p.stdin.flush()
        except OSError:
            pass                                                     # déjà parti (refus d'argument)

    def finir(self, p, fermer_apres=True, delai=30):
        """Attend la fin (la laisse reste tenue jusque-là), puis (code, sortie, lignes de la sortie d'erreur)."""
        try:
            code = p.wait(timeout=delai)
        finally:
            if p.poll() is None:
                p.kill()
            if fermer_apres:
                try:
                    p.stdin.close()
                except OSError:
                    pass
        sortie, erreur = p.fichiers
        sortie.seek(0)
        erreur.seek(0)
        out, err = sortie.read(), erreur.read().decode("utf-8", "replace")
        sortie.close()
        erreur.close()
        return code, out, err.splitlines()

    def lancer(self, *args, ident=ID, env=None, commande=COMMANDE):
        p = self.demarrer(*args, ident=ident, env=env)
        self.ecrire(p, commande)
        return self.finir(p)

    def attendre(self, condition, delai=20):
        fin = time.time() + delai
        while time.time() < fin:
            if condition():
                return
            time.sleep(0.05)
        self.fail("condition jamais remplie\n" + self.journal)

    def lire_err(self, ident):
        return (self.journal_fichier.parent / f"{ident}.err").read_text(encoding="utf-8", errors="replace")

    @property
    def journal(self):
        return self.journal_fichier.read_text(encoding="utf-8") if self.journal_fichier.exists() else ""

    def arbre(self):
        racine = self.home / "tests"
        return sorted((p.relative_to(racine).as_posix(), p.stat().st_size) for p in racine.rglob("*"))

    def verrous(self):
        return sorted(p.name for p in (self.home / "taches").glob("*.tenu")) if (self.home / "taches").exists() else []

    def verifier_fin(self, err, code):
        m = FIN.match(err[-1]) if err else None
        self.assertIsNotNone(m, err)
        self.assertEqual(int(m.group(1)), code, err)
        self.assertLessEqual(int(m.group(2)), int(m.group(3)))
        self.assertFalse((self.home / "tests" / ID).exists())          # dossier effacé
        self.assertEqual(self.verrous(), [])                          # place libérée
        self.assertEqual(list((self.home / "tests" / ".file").glob("*")), [])   # ticket retiré

    # ----------------------------------------------------------------- tests

    def test_arguments_refuses_sans_rien_ecrire(self):
        avant = self.arbre()
        refus = [
            (ID, "5", "4", "8192", "1800", "projet-a", "-"),
            (ID, "2", "0", "8192", "1800", "projet-a", "-"),
            (ID, "2", "4", "8192", "1800", "../x", "-"),
            (ID, "2", "4", "8192", "1800", "projet-a", "xyz"),
            (ID, "2", "4", "8192", "3601", "projet-a", "-"),
            ("t2026-x", "2", "4", "8192", "1800", "projet-a", "-"),
        ]
        for args in refus:
            with self.subTest(args=args):
                code, out, err = self.lancer(*args[1:], ident=args[0])
                self.assertEqual(code, 2, err)
                self.assertTrue(FIN.match(err[-1]) and err[-1].startswith("#fin 2 "), err)
        for commande in ('[""]', '["' + "x" * 5000 + '"]'):
            with self.subTest(commande=commande[:20]):
                self.assertEqual(self.lancer(commande=commande)[0], 2)
        (self.home / "tests" / ID / "travail").mkdir()               # identifiant déjà pris : rien effacé
        self.assertEqual(self.lancer()[0], 2)
        (self.home / "tests" / ID / "travail").rmdir()
        self.assertEqual(self.arbre(), avant)
        self.assertNotIn("docker", self.journal)

    def test_drapeaux_du_conteneur(self):
        code, out, err = self.lancer()
        self.assertEqual(code, 0, err)
        args = (self.etat / f"run-tests-{ID}.txt").read_text(encoding="utf-8").splitlines()
        paires = list(zip(args, args[1:]))
        for paire in [("--network", "none"), ("--cap-drop", "ALL"), ("--security-opt", "no-new-privileges"),
                      ("--user", "1000:1000"), ("--pids-limit", "2048"), ("--memory", "8192m"), ("--memory-swap", "8192m"),
                      ("--cpus", "4"), ("--pull", "never"), ("--name", f"tests-{ID}"), ("--label", "myiafactory.genre=tests"),
                      ("--log-driver", "none"), ("--ulimit", "nofile=8192:8192"), ("--tmpfs", "/tmp:size=4g,mode=1777")]:
            self.assertIn(paire, paires)
        for drapeau in ("--read-only", "--rm", "--init"):
            self.assertIn(drapeau, args)
        self.assertEqual(args[-1], "myiafactory/tests")
        montages = [b for a, b in paires if a == "-v"]
        self.assertEqual(len(montages), 2, montages)
        self.assertTrue(montages[0].endswith(f"/tests/{ID}/travail:/work"), montages)
        self.assertTrue(montages[1].endswith(f"/tests/{ID}/entree:/entree:ro"), montages)
        self.assertFalse(any("docker.sock" in a or a == "--privileged" or a.startswith("--network=") for a in args))
        self.assertEqual(sorted(b for a, b in paires if a == "-e"), ["HOME=/tmp", "MYIAFACTORY_TESTS_CONTENEUR=1"])
        self.assertIn(f"timeout 1800 sudo -n docker run", self.journal)
        self.assertEqual(json.loads((self.etat / f"commande-tests-{ID}.json").read_text(encoding="utf-8")),
                         json.loads(COMMANDE))
        self.verifier_fin(err, 0)

    def test_code_et_fin(self):
        code, out, err = self.lancer(env={"FAUX_SORTIE": "bonjour", "FAUX_CODE": "3"})
        self.assertEqual((code, out), (3, b"bonjour"), err)
        self.verifier_fin(err, 3)
        self.assertNotIn("docker kill", self.journal)                # conteneur fini de lui-même : rien à tuer

    def test_sortie_d_erreur_du_conteneur_prefixee(self):
        code, out, err = self.lancer(env={"FAUX_ERREUR": "#fin 0 1 2 0\n#attente 1 1", "FAUX_CODE": "5",
                                          "FAUX_SORTIE": "bonjour" * 10, "ENVELOPPE_SORTIE_MAX_OCTETS": "40"})
        self.assertEqual(code, 5, err)
        self.assertEqual(out, (b"bonjour" * 10)[:40])                 # sortie coupée au maximum
        self.assertIn("| #fin 0 1 2 0", err)
        self.assertIn("| #attente 1 1", err)                          # ligne finale sans retour : close par le relais
        self.assertIn("Sortie coupée à 50 Mo", err)
        self.assertNotIn("Sortie d'erreur coupée à 50 Mo", err)
        self.assertFalse([x for x in err[:-1] if x.startswith("#")], err)
        self.verifier_fin(err, 5)

    def test_laisse_fermee_tue_le_conteneur(self):
        p = self.demarrer(env={"FAUX_ATTENDRE": "1"})
        self.ecrire(p)
        self.attendre(lambda: (self.etat / f"run-tests-{ID}.txt").exists())
        p.stdin.close()                                              # la session SSH s'en va
        code, out, err = self.finir(p, fermer_apres=False)
        self.assertEqual(code, 130, err)
        self.assertIn(f"docker kill tests-{ID}", self.journal)
        self.verifier_fin(err, 130)

    def test_places_et_file(self):
        taches = self.home / "taches"
        taches.mkdir()
        tenu = subprocess.Popen(["bash", "-c", 'exec 9>> "$HOME/taches/.creneau-tests-1"; flock -n 9 || exit 1; read x'],
                                stdin=subprocess.PIPE, env=self.env)
        try:
            self.attendre(lambda: (taches / ".creneau-tests-1.tenu").exists())
            a = self.demarrer("1", "4", "8192", "1800", "projet-a", "-")
            self.ecrire(a)
            self.attendre(lambda: "#attente 1 1" in self.lire_err(ID))
            self.deposer(ID_B)
            b = self.demarrer("1", "4", "8192", "1800", "projet-a", "-", ident=ID_B)
            self.ecrire(b)
            self.attendre(lambda: "#attente 2 2" in self.lire_err(ID_B))
            self.assertFalse((self.etat / "ordre").exists())         # personne ne passe tant que la place est tenue
        finally:
            tenu.stdin.close()
            tenu.wait(timeout=10)
        code_a, _, err_a = self.finir(a)
        code_b, _, err_b = self.finir(b)
        self.assertEqual((code_a, code_b), (0, 0), err_a + err_b)
        self.assertEqual((self.etat / "ordre").read_text(encoding="utf-8").split(), [f"tests-{ID}", f"tests-{ID_B}"])
        self.assertEqual(int(FIN.match(err_b[-1]).group(1)), 0)
        self.assertGreaterEqual(int(FIN.match(err_b[-1]).group(4)), 0)
        self.verifier_fin(err_a, 0)

    def test_disque_et_image(self):
        for env, attendu in (({"FAUX_DF_KO": "1048576"}, 76), ({"FAUX_SANS_IMAGE": "1"}, 77), ({"FAUX_UID": "1001"}, 77)):
            with self.subTest(attendu=attendu, env=env):
                if not (self.home / "tests" / ID).exists():
                    self.deposer(ID)
                code, out, err = self.lancer(env=env)
                self.assertEqual(code, attendu, err)
                self.verifier_fin(err, attendu)
        self.deposer(ID)
        code, out, err = self.lancer("2", "4", "8192", "1800", "projet-a", "0123456789abcdef")
        self.assertEqual(code, 78, err)
        self.verifier_fin(err, 78)
        self.assertNotIn("docker run", self.journal)
        self.deposer(ID)                                              # instantané piégé : refusé par l'hôte avant docker
        tampon = io.BytesIO()
        with tarfile.open(fileobj=tampon, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            lien = tarfile.TarInfo("x")
            lien.type, lien.linkname = tarfile.SYMTYPE, "/home"
            tar.addfile(lien)
        (self.home / "tests" / ID / "entree" / "entree.tar").write_bytes(tampon.getvalue())
        code, out, err = self.lancer()
        self.assertEqual(code, 70, err)
        self.verifier_fin(err, 70)
        self.assertNotIn("docker run", self.journal)

    def test_balayage(self):
        tests = self.home / "tests"
        vieux, recent = tests / "t20260101-000000-abcd", tests / "t20260101-000000-abce"
        for d in (vieux, recent):
            (d / "travail").mkdir(parents=True)
            (d / "travail" / "f").write_text("x")
        sept_heures = time.time() - 7 * 3600
        os.utime(vieux, (sept_heures, sept_heures))
        (tests / ".file").mkdir()
        (tests / ".file" / "1700000000000000000-t20260101-000000-abcd").write_text("999999\n")   # ticket mort
        code, out, err = self.lancer(env={"FAUX_PS_NOMS": "tests-t20260101-000000-abcd\nautre"})
        self.assertEqual(code, 0, err)
        self.assertFalse(vieux.exists())
        self.assertTrue(recent.exists())
        self.assertIn("docker rm -f tests-t20260101-000000-abcd", self.journal)   # conteneur sans enveloppe vivante
        self.assertNotIn("docker rm -f autre", self.journal)
        self.verifier_fin(err, 0)


class TestAidesHote(unittest.TestCase):
    """`tests_hote.py` en pur Python : archives piégées, commande, relais."""

    @classmethod
    def setUpClass(cls):
        cls.aide = _charger_aide()
        cls._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.t = Path(cls._t.name)
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def archive(self, membres=None, octets=None, fmt=tarfile.USTAR_FORMAT):
        type(self).n += 1
        chemin = self.t / f"a{self.n}.tar"
        if octets is None:
            tampon = io.BytesIO()
            with tarfile.open(fileobj=tampon, mode="w", format=fmt) as tar:
                for info, donnees in membres:
                    tar.addfile(info, io.BytesIO(donnees) if donnees is not None else None)
            octets = tampon.getvalue()
        chemin.write_bytes(octets)
        return self.aide.verifier_archive(str(chemin))

    @staticmethod
    def fichier(nom, donnees=b"x", mode=0o644):
        info = tarfile.TarInfo(nom)
        info.size, info.mode = len(donnees), mode
        return info, donnees

    @staticmethod
    def special(nom, genre, lien=""):
        info = tarfile.TarInfo(nom)
        info.type, info.linkname = genre, lien
        return info, None

    def test_archive_admise(self):
        self.assertIsNone(self.archive([self.fichier("a.py"), self.fichier("d/b.py", b"y" * 700, 0o755),
                                        self.fichier("p" * 120 + "/n.txt")]))

    def test_archives_piegees(self):
        cas = {
            "lien symbolique": [self.special("x", tarfile.SYMTYPE, "/home")],
            "lien dur": [self.fichier("a"), self.special("b", tarfile.LNKTYPE, "a")],
            "dossier": [self.special("d", tarfile.DIRTYPE)],
            "périphérique": [self.special("z", tarfile.CHRTYPE)],
            "fifo": [self.special("f", tarfile.FIFOTYPE)],
            "absolu": [self.fichier("/etc/x")],
            "remontée": [self.fichier("a/../../x")],
            "point": [self.fichier("./a")],
            "contre-oblique": [self.fichier("a\\b")],
            "contrôle": [self.fichier("a\nb")],
            "lecteur": [self.fichier("C:x")],
            "setuid": [self.fichier("a", mode=0o4755)],
            "doublon": [self.fichier("a"), self.fichier("a")],
            "fichier et dossier": [self.fichier("a"), self.fichier("a/b")],
        }
        for raison, membres in cas.items():
            with self.subTest(raison):
                self.assertIsNotNone(self.archive(membres))
        info, donnees = self.fichier("n" * 200)                     # nom long : GNU (L) ou pax (x), jamais USTAR
        self.assertIsNotNone(self.archive([(info, donnees)], fmt=tarfile.GNU_FORMAT))
        self.assertIsNotNone(self.archive([(info, donnees)], fmt=tarfile.PAX_FORMAT))
        self.assertIsNotNone(self.archive([self.fichier("a")], fmt=tarfile.GNU_FORMAT))   # magie GNU
        bon = io.BytesIO()
        with tarfile.open(fileobj=bon, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            i, d = self.fichier("a", b"contenu")
            tar.addfile(i, io.BytesIO(d))
        bon = bon.getvalue()
        eparpille = bytearray(bon)
        eparpille[156:157] = b"S"                                     # membre GNU éparpillé
        somme = sum(eparpille[:148]) + 256 + sum(eparpille[156:512])
        eparpille[148:156] = b"%06o\0 " % somme
        base256 = bytearray(bon)
        base256[124:136] = b"\x80" + b"\0" * 10 + b"\x07"            # taille en base 256
        somme = sum(base256[:148]) + 256 + sum(base256[156:512])
        base256[148:156] = b"%06o\0 " % somme
        abime = bytearray(bon)
        abime[0:1] = b"b"                                             # somme de contrôle fausse
        for raison, octets in {"éparpillé": bytes(eparpille), "base 256": bytes(base256), "somme": bytes(abime),
                               "tronquée": bon[:1024], "pas multiple de 512": bon + b"\0",
                               "données après la fin": bon + b"x" * 512, "vide": b""}.items():
            with self.subTest(raison):
                self.assertIsNotNone(self.archive(octets=octets))
        self.assertIsNone(self.archive(octets=bon))

    def test_limites_de_l_archive(self):
        with mock.patch.object(self.aide, "MAX_FICHIERS", 2):
            self.assertIsNone(self.archive([self.fichier("a"), self.fichier("b")]))
            self.assertIn("trop de fichiers", self.archive([self.fichier("a"), self.fichier("b"), self.fichier("c")]))
        with mock.patch.object(self.aide, "MAX_FICHIER", 3):
            self.assertIn("trop gros", self.archive([self.fichier("a", b"1234")]))
        with mock.patch.object(self.aide, "MAX_TOTAL", 5):
            self.assertIn("trop gros", self.archive([self.fichier("a", b"123"), self.fichier("b", b"123")]))
        with mock.patch.object(self.aide, "MAX_ARCHIVE", 1024):
            self.assertIn("archive trop grosse", self.archive([self.fichier("a")]))
        lien = self.t / "lien.tar"
        try:
            os.symlink(self.t / "a1.tar", lien)
        except OSError:
            return                                                    # liens non créables ici (Windows sans droit)
        self.assertIsNotNone(self.aide.verifier_archive(str(lien)))

    def test_commande(self):
        ok = self.aide.commande_valide
        self.assertTrue(ok(b'["python3", "-m", "unittest"]'))
        for brut in (b"[]", b'[""]', b'"x"', b'{"a": 1}', b"[1]", b'["a\\u0000"]', b"\xff", b'["' + b"x" * 4100 + b'"]',
                     ("[" + ",".join(['"a"'] * 65) + "]").encode()):
            self.assertFalse(ok(brut), brut[:30])

    def relayer(self, fonction, entree, maximum):
        src, dst, marque = self.t / "src", self.t / "dst", self.t / "marque"
        for f in (dst, marque):
            if f.exists():
                f.unlink()
        src.write_bytes(entree)
        with open(src, "rb") as i, open(dst, "wb") as o:
            fonction(i.fileno(), o.fileno(), str(marque), maximum)
        return dst.read_bytes(), marque.exists()

    def test_relais(self):
        p = self.aide.prefixer
        self.assertEqual(self.relayer(p, b"a\n#fin 0 1 2 0\nb", 100), (b"| a\n| #fin 0 1 2 0\n| b\n", False))
        self.assertEqual(self.relayer(p, b"", 100), (b"", False))
        self.assertEqual(self.relayer(p, b"\n\n", 100), (b"| \n| \n", False))
        self.assertEqual(self.relayer(p, b"abcdef\nxyz", 4), (b"| abcd\n", True))
        c = self.aide.couper
        self.assertEqual(self.relayer(c, b"bonjour", 100), (b"bonjour", False))
        self.assertEqual(self.relayer(c, b"bonjour", 7), (b"bonjour", False))
        self.assertEqual(self.relayer(c, b"bonjour", 4), (b"bonj", True))


if __name__ == "__main__":
    unittest.main()
