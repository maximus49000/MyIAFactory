"""Enveloppe hôte des campagnes de tests (`serveur_ovh/taches/lancer_tests.sh`) et ses aides (`taches/tests_hote.py`).

L'enveloppe tourne avec le bash du poste et un PATH de faux (`docker`, `sudo`, `timeout`, `df`, `du`, `id`, `flock`, `python3`
qui renvoie à l'interpréteur des tests), `HOME` temporaire : aucun vrai conteneur, aucun serveur. Le faux `flock` tient un
verrou par fichier (`<fichier>.tenu`, PID du shell qui l'a pris ; libre si ce PID ne vit plus). Le faux `docker` garde l'état
final du conteneur (`docker inspect`) jusqu'au `docker rm`. Les lancements indépendants tournent en même temps (identifiants
distincts) : le banc reste court. Les aides se testent en pur Python (archives piégées, commande, relais).

Contrat du poste vérifié ici : la sortie d'erreur se coupe sur « \\n » SEULEMENT ; la dernière ligne est `#fin <code> …` ; un
code de l'enveloppe est précédé de `#refus <code>`, un code du conteneur jamais."""
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
DEPS = "0123456789abcdef"


def ident(n):
    return "t20261123-1020%02d-%04x" % (n % 60, n)


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
ET="$FAUX_ETAT"
dernier() { for a in "$@"; do d="$a"; done; printf '%s' "$d"; }
case "$1" in
  image) [ -n "${FAUX_SANS_IMAGE:-}" ] && exit 1; exit 0 ;;
  ps) [ -n "${FAUX_PS_NOMS:-}" ] && printf '%s\n' "$FAUX_PS_NOMS"; exit 0 ;;
  inspect) n=$(dernier "$@")
           [ -n "${FAUX_INSPECT_PANNE:-}" ] && { echo "Cannot connect to the Docker daemon" >&2; exit 1; }
           if [ -f "$ET/etat-$n" ]; then cat "$ET/etat-$n"; exit 0; fi
           echo "Error: No such object: $n" >&2; exit 1 ;;
  kill) if [ -n "${FAUX_CREATION_TARDIVE:-}" ] && [ ! -e "$ET/cree" ]; then echo "Error: No such container" >&2; exit 1; fi
        touch "$ET/tue"; exit 0 ;;
  rm) n=$(dernier "$@"); [ "${FAUX_RM_ECHEC:-}" = "$n" ] && exit 1
      rm -f "$ET/etat-$n"; exit 0 ;;
  run)
    nom=""; prec=""
    for a in "$@"; do [ "$prec" = --name ] && nom="$a"; prec="$a"; done
    printf '%s\n' "$@" > "$ET/run-$nom.txt"
    cp "$HOME/tests/${nom#tests-}/entree/commande.json" "$ET/commande-$nom.json"
    echo "$nom" >> "${FAUX_ORDRE:-$ET/ordre}"
    if [ -n "${FAUX_JAMAIS_DEMARRE:-}" ]; then
      echo "created 0 0001-01-01T00:00:00Z" > "$ET/etat-$nom"; echo "docker: Error response from daemon: boom" >&2; exit 125
    fi
    if [ -n "${FAUX_ETAT_FINAL:-}" ]; then echo "$FAUX_ETAT_FINAL" > "$ET/etat-$nom"; exit "${FAUX_CODE:-0}"; fi
    if [ -n "${FAUX_CREATION_TARDIVE:-}" ]; then
      while [ ! -e "$HOME/tests/${nom#tests-}/laisse-coupee" ]; do sleep 0.05; done
      sleep 0.3; touch "$ET/cree"
    fi
    if [ -n "${FAUX_ATTENDRE:-}" ] || [ -n "${FAUX_CREATION_TARDIVE:-}" ]; then
      while [ ! -e "$ET/tue" ]; do sleep 0.05; done
      echo "exited 137 2026-11-23T10:00:00.1Z" > "$ET/etat-$nom"; exit 137
    fi
    [ -f "$ET/sortie" ] && cat "$ET/sortie"
    [ -f "$ET/erreur" ] && cat "$ET/erreur" >&2
    echo "exited ${FAUX_CODE:-0} 2026-11-23T10:00:00.1Z" > "$ET/etat-$nom"
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
    # FAUX_TIMEOUT : la durée est dépassée (le faux conteneur tourne, puis timeout rend 124)
    "timeout": 'echo "timeout $*" >> "$FAUX_JOURNAL"\nshift\n'
               'if [ -n "${FAUX_TIMEOUT:-}" ] && [ "${4:-}" = run ]; then "$@"; exit 124; fi\nexec "$@"',
    "df": 'if [ "$1" = -Pi ]; then\n  echo "Filesystem Inodes IUsed IFree IUse% Mounted on"\n'
          '  i=900000; [ -f "$FAUX_ETAT/df_ifree" ] && read -r i < "$FAUX_ETAT/df_ifree"; [ -n "${FAUX_DF_IFREE:-}" ] && i=$FAUX_DF_IFREE\n'
          '  echo "/dev/sda1 1000000 1 $i 10% /"; exit 0\nfi\n'
          'echo "Filesystem 1024-blocks Used Available Capacity Mounted on"\n'
          'k=20000000; [ -f "$FAUX_ETAT/df_ko" ] && read -r k < "$FAUX_ETAT/df_ko"; [ -n "${FAUX_DF_KO:-}" ] && k=$FAUX_DF_KO\n'
          'echo "/dev/sda1 100000000 1 $k 1% /"',
    "du": 'k=4; [ -f "$FAUX_ETAT/du_ko" ] && read -r k < "$FAUX_ETAT/du_ko"\nprintf \'%s\\t%s\\n\' "$k" "$3"',
    "id": 'echo "${FAUX_UID:-1000}"',
    "chmod": 'echo "chmod $*" >> "$FAUX_JOURNAL"\nexec /usr/bin/chmod "$@"',
    # FAUX_ARCHIVE_MESSAGE : le vérificateur refuse (3) avec ce message ; FAUX_PYTHON_PLANTE : il plante (1)
    "python3": 'if [ "${3:-}" = --archive ]; then\n'
               '  [ -n "${FAUX_PYTHON_PLANTE:-}" ] && { echo "Traceback (most recent call last):" >&2; exit 1; }\n'
               '  [ -n "${FAUX_ARCHIVE_MESSAGE:-}" ] && { cat "$FAUX_ARCHIVE_MESSAGE" >&2; exit 3; }\n'
               'fi\n'
               f'exec "{Path(sys.executable).as_posix()}" "$@"',
}


def _instantane():
    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        info = tarfile.TarInfo("tests/test_a.py")
        donnees = b"print('a')\n"
        info.size, info.mode = len(donnees), 0o644
        tar.addfile(info, io.BytesIO(donnees))
    return tampon.getvalue()


class Lancement:
    def __init__(self, p, ident, etat, sortie, erreur):
        self.p, self.ident, self.etat, self.sortie, self.erreur = p, ident, etat, sortie, erreur


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
        # Un PATH sans python3 : les faux sauf python3, puis /usr/bin du bash (Git bash : sans python3). Ignoré si python3
        # y est quand même (Linux : /usr/bin/python3).
        sans = cls.racine / "bin-sans-python"
        sans.mkdir()
        for nom, corps in FAUX.items():
            if nom != "python3":
                (sans / nom).write_text("#!/bin/sh\n" + corps + "\n", newline="\n")
                (sans / nom).chmod(0o755)
        r = subprocess.run(["bash", "-c", 'command -v cygpath >/dev/null && cygpath -m /usr/bin || echo /usr/bin:/bin'],
                           capture_output=True, text=True)
        systeme = r.stdout.strip()
        chemin = sans.as_posix() + os.pathsep + systeme
        cls.chemin_sans_python = None if shutil.which("python3", path=systeme) else chemin

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def setUp(self):
        type(self).n += 1
        t = self.t = self.racine / f"c{self.n}"
        self.home = t / "home"
        self.home.mkdir(parents=True)
        self.journal_fichier = t / "appels.txt"
        self.env = dict(os.environ, HOME=_msys(self.home), PATH=self.bin.as_posix() + os.pathsep + os.environ["PATH"],
                        FAUX_JOURNAL=self.journal_fichier.as_posix(), ENVELOPPE_SONDE_S="0.2",
                        FAUX_ORDRE=(t / "ordre").as_posix())
        self.deposer(ID)

    def deposer(self, ident, tar=None):
        entree = self.home / "tests" / ident / "entree"
        entree.mkdir(parents=True)
        (entree / "entree.tar").write_bytes(tar or self.tar)

    def etat(self, ident):
        e = self.t / "etat" / ident
        e.mkdir(parents=True, exist_ok=True)
        return e

    def demarrer(self, *args, ident=ID, env=None, commande=COMMANDE):
        corps = list(args) if args else ["2", "4", "8192", "1800", "projet-a", "-"]
        etat = self.etat(ident)
        e = dict(self.env, FAUX_ETAT=etat.as_posix(), **(env or {}))
        type(self).n += 1                                            # fichiers propres à chaque lancement (même identifiant)
        sortie, erreur = open(etat / f"out-{self.n}", "w+b"), open(etat / f"err-{self.n}", "w+b")
        p = subprocess.Popen(["bash", SCRIPT.as_posix(), ident, *corps], stdin=subprocess.PIPE, stdout=sortie,
                             stderr=erreur, env=e)
        lancement = Lancement(p, ident, etat, sortie, erreur)
        if commande is not None:
            self.ecrire(lancement, commande)
        return lancement

    @staticmethod
    def ecrire(lancement, texte=COMMANDE):
        try:
            lancement.p.stdin.write(texte.encode("utf-8") + b"\n")
            lancement.p.stdin.flush()
        except OSError:
            pass                                                     # déjà parti (refus d'argument)

    def finir(self, lancement, fermer_apres=True, delai=60):
        """Attend la fin (la laisse reste tenue jusque-là), puis (code, sortie, lignes de la sortie d'erreur coupées sur \\n)."""
        p = lancement.p
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
        for f in (lancement.sortie, lancement.erreur):
            f.seek(0)
        out, err = lancement.sortie.read(), lancement.erreur.read().decode("utf-8", "replace")
        lancement.sortie.close()
        lancement.erreur.close()
        lignes = err.split("\n")
        if lignes and lignes[-1] == "":
            lignes.pop()
        # #fin est la toute dernière écriture : rien après (ni avis « Terminated » d'un fils tué), retour final compris
        self.assertTrue(err.endswith("\n") and FIN.match(lignes[-1]), err[-300:])
        return code, out, lignes

    def lancer(self, *args, **kw):
        return self.finir(self.demarrer(*args, **kw))

    def attendre(self, condition, delai=60):
        fin = time.time() + delai
        while time.time() < fin:
            if condition():
                return
            time.sleep(0.05)
        self.fail("condition jamais remplie (fin du journal) : " + self.journal[-800:])

    @staticmethod
    def lire_err(lancement):
        return Path(lancement.erreur.name).read_text(encoding="utf-8", errors="replace")

    @property
    def journal(self):
        return self.journal_fichier.read_text(encoding="utf-8") if self.journal_fichier.exists() else ""

    def arbre(self):
        racine = self.home / "tests"
        return sorted((p.relative_to(racine).as_posix(), p.stat().st_size) for p in racine.rglob("*"))

    def verrous(self):
        return sorted(p.name for p in (self.home / "taches").glob("*.tenu")) if (self.home / "taches").exists() else []

    def verifier_fin(self, err, code, refus, ident=ID, efface=True):
        """Dernière ligne `#fin <code>` ; `#refus <code>` juste avant (lignes vides ignorées, comme le poste) si et
        seulement si le code vient de l'enveloppe."""
        err = [x for x in err if x != ""]
        m = FIN.match(err[-1]) if err else None
        self.assertIsNotNone(m, err)
        self.assertEqual(int(m.group(1)), code, err)
        self.assertLessEqual(int(m.group(2)), int(m.group(3)))
        if refus:
            self.assertEqual(err[-2], f"#refus {code}", err)
        else:
            self.assertFalse(any(x.startswith("#refus") for x in err), err)
        self.assertFalse([x for x in err[:-2] if x.startswith("#") and not x.startswith("#attente")], err)
        if not efface:
            return
        self.assertFalse((self.home / "tests" / ident).exists())       # dossier effacé
        self.assertEqual(self.verrous(), [])                          # place libérée
        self.assertFalse([p for p in (self.home / "tests" / ".file").glob("*") if ident in p.name])   # ticket retiré

    # ----------------------------------------------------------------- tests

    def test_arguments_refuses_sans_rien_ecrire(self):
        self.deposer(ID_B)
        (self.home / "tests" / ID_B / "travail").mkdir()              # identifiant déjà pris : rien effacé
        avant = self.arbre()
        refus = [
            (ID, "5", "4", "8192", "1800", "projet-a", "-"),
            (ID, "2", "0", "8192", "1800", "projet-a", "-"),
            (ID, "2", "4", "8192", "1800", "../x", "-"),
            (ID, "2", "4", "8192", "1800", "projet-a", "xyz"),
            (ID, "2", "4", "8192", "3601", "projet-a", "-"),
            (ID, "2", "4", "8192", "1800", "projet-a", "-", "0"),
            ("t2026-x", "2", "4", "8192", "1800", "projet-a", "-"),
        ]
        lances = [(args, self.demarrer(*args[1:], ident=args[0])) for args in refus]
        for i, commande in enumerate(('[""]', '["' + "x" * 5000 + '"]', '["\\ud800"]')):
            lances.append((commande[:12], self.demarrer(ident=ident(i), commande=commande)))
        lances.append(("pris", self.demarrer(ident=ID_B)))
        for quoi, lancement in lances:
            with self.subTest(quoi=quoi):
                code, out, err = self.finir(lancement)
                self.assertEqual(code, 2, err)
                self.verifier_fin(err, 2, refus=True, efface=False)
        self.assertEqual(self.arbre(), avant)
        self.assertNotIn("docker", self.journal)

    def test_drapeaux_du_conteneur(self):
        (self.home / "tests" / ".deps" / "projet-a" / DEPS).mkdir(parents=True)
        (self.etat(ID) / "sortie").write_bytes(b"bonjour")
        code, out, err = self.lancer("2", "4", "8192", "1800", "projet-a", DEPS, env={"FAUX_CODE": "3"})
        self.assertEqual((code, out), (3, b"bonjour"), err)
        args = (self.etat(ID) / f"run-tests-{ID}.txt").read_text(encoding="utf-8").splitlines()
        paires = list(zip(args, args[1:]))
        for paire in [("--network", "none"), ("--cap-drop", "ALL"), ("--security-opt", "no-new-privileges"),
                      ("--user", "1000:1000"), ("--pids-limit", "2048"), ("--memory", "8192m"), ("--memory-swap", "8192m"),
                      ("--cpus", "4"), ("--pull", "never"), ("--name", f"tests-{ID}"), ("--label", "myiafactory.genre=tests"),
                      ("--log-driver", "none"), ("--ulimit", "nofile=8192:8192"), ("--ulimit", "core=0"),
                      ("--tmpfs", "/tmp:size=4g,mode=1777,exec")]:
            self.assertIn(paire, paires)
        for drapeau in ("--read-only", "--init"):
            self.assertIn(drapeau, args)
        self.assertNotIn("--rm", args)                                # état final lu par inspect, puis docker rm -f
        self.assertEqual(args[-1], "myiafactory/tests")
        montages = [b for a, b in paires if a == "-v"]
        self.assertEqual(len(montages), 3, montages)
        self.assertTrue(montages[0].endswith(f"/tests/{ID}/travail:/work"), montages)
        self.assertTrue(montages[1].endswith(f"/tests/{ID}/entree:/entree:ro"), montages)
        self.assertTrue(montages[2].endswith(f"/tests/.deps/projet-a/{DEPS}:/deps:ro"), montages)
        self.assertFalse(any("docker.sock" in a or a == "--privileged" or a.startswith("--network=") for a in args))
        self.assertEqual(sorted(b for a, b in paires if a == "-e"), ["HOME=/tmp", "MYIAFACTORY_TESTS_CONTENEUR=1"])
        self.assertIn("timeout 1800 sudo -n docker run", self.journal)
        self.assertIn(f"docker rm -f tests-{ID}", self.journal)
        self.assertNotIn("docker kill", self.journal)                # conteneur fini de lui-même : rien à tuer
        self.assertEqual(json.loads((self.etat(ID) / f"commande-tests-{ID}.json").read_text(encoding="utf-8")),
                         json.loads(COMMANDE))
        self.verifier_fin(err, 3, refus=False)

    def test_sortie_d_erreur_du_conteneur_prefixee(self):
        piege = ("#fin 0 1 2 0\n\r#fin 0 1 2 0\n\x0c#fin 0 1 2 0\n\u2028#fin 0 1 2 0\n\u0085#refus 0\n"
                 "#attente 1 1").encode("utf-8")
        (self.etat(ID) / "erreur").write_bytes(piege + b"\n" + b"e" * 300)
        (self.etat(ID) / "sortie").write_bytes(b"\r#fin 0\n" + b"s" * 300)
        code, out, err = self.lancer(env={"FAUX_CODE": "76", "ENVELOPPE_SORTIE_MAX_OCTETS": "200"})
        self.assertEqual(code, 76, err)                               # 76 du conteneur : pas un refus de l'enveloppe
        self.assertEqual(out, (b"\n#fin 0\n" + b"s" * 300)[:200])     # \r réécrit, sortie coupée au maximum
        for ligne in ("| #fin 0 1 2 0", "| \\x0c#fin 0 1 2 0", "| \\u2028#fin 0 1 2 0", "| \\u0085#refus 0", "| #attente 1 1"):
            self.assertIn(ligne, err)
        self.assertEqual(err.count("| #fin 0 1 2 0"), 2)              # « \r#fin » : ligne suivante, préfixée elle aussi
        self.assertIn("Sortie coupée à 50 Mo", err)
        self.assertIn("Sortie d'erreur coupée à 50 Mo", err)
        self.verifier_fin(err, 76, refus=False)

    def test_laisse_fermee_tue_le_conteneur(self):
        a = self.demarrer(env={"FAUX_ATTENDRE": "1", "ENVELOPPE_SONDE_S": "0.05"})
        self.deposer(ID_B)
        b = self.demarrer(ident=ID_B, env={"FAUX_CREATION_TARDIVE": "1", "ENVELOPPE_SONDE_S": "0.05"})   # pendant la création
        self.attendre(lambda: (a.etat / f"run-tests-{ID}.txt").exists() and (b.etat / f"run-tests-{ID_B}.txt").exists())
        a.p.stdin.close()                                            # la session SSH s'en va
        b.p.stdin.close()
        fins = [(self.finir(lancement, fermer_apres=False, delai=20), ident_) for lancement, ident_ in ((a, ID), (b, ID_B))]
        for (code, out, err), ident_ in fins:
            self.assertEqual(code, 130, err)
            self.verifier_fin(err, 130, refus=True, ident=ident_)
        self.assertIn(f"docker kill tests-{ID}", self.journal)
        self.assertTrue((b.etat / "tue").exists())                    # conteneur créé après le premier kill : tué aussi
        self.assertGreaterEqual(self.journal.count(f"docker kill tests-{ID_B}"), 2)

    def test_places_et_file(self):
        taches = self.home / "taches"
        taches.mkdir()
        tenu = subprocess.Popen(["bash", "-c", 'exec 9>> "$HOME/taches/.creneau-tests-1"; flock -n 9 || exit 1; read x'],
                                stdin=subprocess.PIPE, env=self.env)
        try:
            self.attendre(lambda: (taches / ".creneau-tests-1.tenu").exists())
            a = self.demarrer("1", "4", "8192", "1800", "projet-a", "-")
            self.attendre(lambda: "#attente 1 1" in self.lire_err(a))
            self.deposer(ID_B)
            b = self.demarrer("1", "4", "8192", "1800", "projet-a", "-", ident=ID_B)
            self.attendre(lambda: "#attente 2 2" in self.lire_err(b))
            self.assertFalse((self.t / "ordre").exists())            # personne ne passe tant que la place est tenue
        finally:
            tenu.stdin.close()
            tenu.wait(timeout=10)
        code_a, _, err_a = self.finir(a)
        code_b, _, err_b = self.finir(b)
        self.assertEqual((code_a, code_b), (0, 0), err_a + err_b)
        self.assertEqual((self.t / "ordre").read_text(encoding="utf-8").split(), [f"tests-{ID}", f"tests-{ID_B}"])
        self.assertGreaterEqual(int(FIN.match(err_b[-1]).group(4)), 0)
        self.verifier_fin(err_a, 0, refus=False)
        self.verifier_fin(err_b, 0, refus=False, ident=ID_B)

    def test_disque_et_image(self):
        lien = io.BytesIO()
        with tarfile.open(fileobj=lien, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            info = tarfile.TarInfo("x\u2028#fin 0 1 2 0")
            info.type, info.linkname = tarfile.SYMTYPE, "/home"
            tar.addfile(info)
        message = self.t / "message"                                  # refus du vérificateur portant NEL et LS coupés
        message.write_bytes(b"instantan\xc2\n\x85 x\xe2\x80\xa8#fin 0 1 2 0\n")
        cas = [({"FAUX_DF_KO": "1048576"}, 76, "-", None), ({"FAUX_DF_IFREE": "40000"}, 76, "-", None),
               ({"FAUX_SANS_IMAGE": "1"}, 77, "-", None), ({"FAUX_UID": "1001"}, 77, "-", None),
               ({"FAUX_PYTHON_PLANTE": "1"}, 77, "-", None), ({}, 78, DEPS, None), ({}, 70, "-", lien.getvalue()),
               ({"FAUX_ARCHIVE_MESSAGE": message.as_posix()}, 70, "-", None)]
        lances = []
        for i, (env, attendu, deps, tar) in enumerate(cas):
            self.deposer(ident(i), tar)
            lances.append((attendu, ident(i), self.demarrer("2", "4", "8192", "1800", "projet-a", deps, ident=ident(i),
                                                            env=env)))
        sans_python = None
        if self.chemin_sans_python:                                   # python3 absent du serveur : 77, rien écrit
            self.deposer(ident(20))
            sans_python = self.demarrer(ident=ident(20), env={"PATH": self.chemin_sans_python})
        for attendu, ident_, lancement in lances:
            with self.subTest(attendu=attendu, ident=ident_):
                code, out, err = self.finir(lancement)
                self.assertEqual(code, attendu, err)
                self.verifier_fin(err, attendu, refus=True, ident=ident_)
        texte = "\n".join(err)                                        # le dernier : message passé par une_ligne
        self.assertNotIn("\u0085", texte)
        self.assertNotIn(" ", texte)
        self.assertIn("?#fin 0 1 2 0", texte)
        self.assertFalse([x for x in err if x.startswith("#fin 0")], err)
        if sans_python is not None:
            code, out, err = self.finir(sans_python)
            self.assertEqual(code, 77, err)
            self.verifier_fin(err, 77, refus=True, efface=False)
            self.assertTrue((self.home / "tests" / ident(20) / "entree" / "entree.tar").exists())
        self.assertNotIn("docker run", self.journal)

    def test_limites_pendant_la_campagne(self):
        cas = {   # identifiant : (arguments, env, fichier écrit une fois le conteneur parti, code, #refus)
            ident(1): (["4", "4", "8192", "1800", "projet-a", "-"], {"FAUX_TIMEOUT": "1", "FAUX_CODE": "143"}, None, 124, True),
            ident(2): (["4", "4", "8192", "1800", "projet-a", "-"], {"FAUX_CODE": "124"}, None, 124, False),
            ident(3): (["4", "4", "8192", "1800", "projet-a", "-"], {"FAUX_CODE": "130"}, None, 130, False),
            ident(4): (["4", "4", "8192", "1800", "projet-a", "-"], {"FAUX_JAMAIS_DEMARRE": "1"}, None, 125, True),
            ident(5): (["4", "4", "8192", "1800", "projet-a", "-"], {"FAUX_ATTENDRE": "1"}, ("df_ko", "1000"), 74, True),
            ident(6): (["4", "4", "8192", "1800", "projet-a", "-"], {"FAUX_ATTENDRE": "1"}, ("df_ifree", "100"), 74, True),
            ident(7): (["4", "4", "8192", "1800", "projet-a", "-", "1"], {"FAUX_ATTENDRE": "1", "ENVELOPPE_DU_S": "0"},
                       ("du_ko", "2000000"), 74, True),
            ident(8): (["4", "4", "8192", "1", "projet-a", "-"], {"FAUX_ATTENDRE": "1", "ENVELOPPE_MARGE_S": "0"}, None,
                       74, True),
            # état final inattendu après docker run : tué, supprimé, 74 (jamais le code de docker)
            ident(9): (["4", "4", "8192", "1800", "projet-a", "-"], {"FAUX_ETAT_FINAL": "running 0 2026-11-23T10:00:00Z",
                                                                     "FAUX_CODE": "125"}, None, 74, True),
            ident(10): (["4", "4", "8192", "1800", "projet-a", "-"], {"FAUX_ETAT_FINAL": "running 0 2026-11-23T10:00:00Z",
                                                                      "FAUX_RM_ECHEC": f"tests-{ident(10)}"}, None, 74, True),
            ident(11): (["4", "4", "8192", "1800", "projet-a", "-"], {"FAUX_INSPECT_PANNE": "1"}, None, 74, True),
            ident(12): (["4", "4", "8192", "1800", "projet-a", "-"], {"FAUX_ETAT_FINAL": "created 0 2026-11-23T10:00:00Z",
                                                                      "FAUX_CODE": "126"}, None, 74, True),
        }
        lances = {}
        for i, (args, env, fichier, code, refus) in cas.items():
            self.deposer(i)
            lances[i] = self.demarrer(*args, ident=i, env=dict(env, ENVELOPPE_SONDE_S="0.05"))
        for i, (args, env, fichier, code, refus) in cas.items():
            if fichier:
                self.attendre(lambda: (lances[i].etat / f"run-tests-{i}.txt").exists())
                (lances[i].etat / fichier[0]).write_text(fichier[1] + "\n", newline="\n")
        fins = {i: self.finir(lances[i]) for i in cas}
        for i, (args, env, fichier, code, refus) in cas.items():
            with self.subTest(ident=i, env=env):
                c, out, err = fins[i]
                self.assertEqual(c, code, err)
                self.verifier_fin(err, code, refus=refus, ident=i)
        self.assertIn("| docker: Error response from daemon: boom", self.lire_err(lances[ident(4)]))
        chmod = [x for x in self.journal.splitlines() if x.startswith("chmod -R")]
        self.assertTrue([x for x in chmod if f"/{ident(9)}/travail" in x], chmod)        # arrêt confirmé : chmod -R
        for i in (ident(10), ident(11)):                              # arrêt non confirmé (rm en échec, inspect en panne)
            self.assertFalse([x for x in chmod if f"/{i}/travail" in x], chmod)
        self.assertIn(f"docker kill tests-{ident(9)}", self.journal)

    def test_surveillant_tue_si_l_enveloppe_disparait(self):
        a = self.demarrer(env={"FAUX_ATTENDRE": "1", "ENVELOPPE_SONDE_S": "0.05"})
        self.attendre(lambda: (a.etat / f"run-tests-{ID}.txt").exists())
        a.p.kill()                                                    # l'enveloppe meurt sans rien nettoyer
        try:
            self.attendre(lambda: (a.etat / "tue").exists())         # le surveillant tue le conteneur
        finally:
            a.p.wait(timeout=10)
            a.p.stdin.close()
            a.sortie.close()
            a.erreur.close()
        self.assertIn(f"docker kill tests-{ID}", self.journal)

    def test_balayage(self):
        tests = self.home / "tests"
        vieux, recent, vivant, occupe = (tests / "t20260101-000000-abcd", tests / "t20260101-000000-abce",
                                         tests / "t20260101-000000-abcf", tests / "t20260101-000000-abd0")
        # le conteneur de « occupe » tourne encore et refuse docker rm : son dossier n'est pas confirmé libre, il reste
        (self.etat(ID) / f"etat-tests-{occupe.name}").write_text("running 0 2026-01-01T00:00:00Z\n", newline="\n")
        for d in (vieux, recent, vivant, occupe):
            (d / "travail").mkdir(parents=True)
            (d / "travail" / "f").write_text("x")
        tenant = subprocess.Popen(["bash", "-c", 'echo $$ > "$PIDF"; read x', "lancer_tests.sh", vivant.name],
                                  stdin=subprocess.PIPE, env=dict(self.env, PIDF=_msys(vivant / "enveloppe.pid")))
        try:
            self.attendre(lambda: (vivant / "enveloppe.pid").exists() and (vivant / "enveloppe.pid").read_text().strip())
            sept_heures = time.time() - 7 * 3600
            for d in (vieux, vivant, occupe):
                os.utime(d, (sept_heures, sept_heures))
            (tests / ".file").mkdir()
            (tests / ".file" / "1700000000000000000-t20260101-000000-abcd").write_text("999999\n")   # ticket mort
            noms = "\n".join(["tests-" + vieux.name, "tests-" + vivant.name, "tests-" + occupe.name, "autre"])
            code, out, err = self.lancer(env={"FAUX_PS_NOMS": noms, "FAUX_RM_ECHEC": "tests-" + occupe.name})
        finally:
            tenant.stdin.close()
            tenant.wait(timeout=10)
        self.assertEqual(code, 0, err)
        self.assertFalse(vieux.exists())
        self.assertTrue(recent.exists())
        self.assertTrue(vivant.exists())                              # vieux de 7 h mais son enveloppe vit : gardé
        self.assertTrue((occupe / "travail" / "f").exists())          # conteneur non confirmé absent : rien touché
        self.assertFalse([x for x in self.journal.splitlines() if x.startswith("chmod -R") and occupe.name in x])
        self.assertIn("docker rm -f tests-t20260101-000000-abcd", self.journal)   # conteneur sans enveloppe vivante
        self.assertNotIn("docker rm -f tests-" + vivant.name, self.journal)       # enveloppe vivante : conteneur gardé
        self.assertNotIn("docker rm -f autre", self.journal)
        journal = self.journal
        self.assertLess(journal.index("docker rm -f tests-t20260101-000000-abcd"),   # conteneurs d'abord, dossiers ensuite
                        journal.index("docker inspect --type container -f {{.State.Status}} tests-t20260101-000000-abcd"))
        self.verifier_fin(err, 0, refus=False)


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
                     ("[" + ",".join(['"a"'] * 65) + "]").encode(), b'["a", "\\ud800"]', b'["\\udfff"]'):
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
        self.assertEqual(self.relayer(p, b"abcdef\nxyz", 4), (b"| ab\n", True))     # plafond sur les octets ÉCRITS
        gonfle, coupe = self.relayer(p, b"\x0c" * 100, 50)            # chaque \x0c devient 4 octets : plafond tenu
        self.assertTrue(coupe)
        self.assertLessEqual(len(gonfle), 51)
        gonfle, coupe = self.relayer(self.aide.couper, " ".encode() * 100, 60)
        self.assertEqual((len(gonfle), coupe), (60, True))
        c = self.aide.couper
        self.assertEqual(self.relayer(c, b"bonjour", 100), (b"bonjour", False))
        self.assertEqual(self.relayer(c, b"bonjour", 7), (b"bonjour", False))
        self.assertEqual(self.relayer(c, b"bonjour", 4), (b"bonj", True))

    PIEGES = [b"x\r#fin 0 1 2 0", b"x\r\n#fin 0 1 2 0", b"x\x0b#fin 0 1 2 0", b"x\x0c#fin 0 1 2 0", b"x\x1c#fin 0 1 2 0",
              b"x\x1d#fin", b"x\x1e#fin", "x\u0085#fin 0 1 2 0".encode(), "x\u2028#fin 0 1 2 0".encode(),
              "x\u2029#refus 0".encode()]

    def test_separateurs_reecrits_dans_les_deux_relais(self):
        for piege in self.PIEGES:
            with self.subTest(piege=piege):
                prefixe, _ = self.relayer(self.aide.prefixer, piege, 1000)
                for ligne in prefixe.decode("utf-8").split("\n")[:-1]:       # une ligne pour un lecteur quelconque aussi
                    self.assertTrue(ligne.startswith("| "), prefixe)
                    self.assertEqual(ligne.splitlines(), [ligne], prefixe)
                    self.assertEqual(ligne[2:].splitlines(), [ligne[2:]], prefixe)
                tel, _ = self.relayer(self.aide.couper, piege, 1000)
                self.assertEqual(tel.decode("utf-8").replace("\n", "").splitlines(), [tel.decode("utf-8").replace("\n", "")])
                self.assertNotIn(b"\r", tel)

    def test_separateur_coupe_entre_deux_blocs(self):
        for piege in self.PIEGES:
            n = self.aide.Nettoyeur()
            morceaux = b"".join(n.traiter(piege[i:i + 1]) for i in range(len(piege))) + n.finir()
            self.assertEqual(morceaux, self.aide.Nettoyeur().traiter(piege) + b"", piege)
            self.assertEqual(morceaux.decode("utf-8").replace("\n", "").splitlines(),
                             [morceaux.decode("utf-8").replace("\n", "")], piege)
        self.assertEqual(self.aide.Nettoyeur().traiter("a\u2028b".encode()), b"a\\u2028b")
        self.assertEqual(self.aide.Nettoyeur().traiter(b"a\x0cb\r\nc\rd"), b"a\\x0cb\nc\nd")

    def test_codes_de_l_archive(self):
        """3 = refus explicite (l'enveloppe rend 70) ; un plantage de python rend 1 (l'enveloppe rend 77)."""
        mauvais = self.t / "mauvais.tar"
        mauvais.write_bytes(b"x" * 512)
        self.assertEqual(self.aide.principal(["--archive", str(mauvais)]), 3)
        self.assertEqual(self.aide.REFUS_ARCHIVE, 3)

    def test_message_sur_une_ligne(self):
        self.assertEqual(self.aide.texte_sur("nom refusé : x\u2028#fin\n\u0085"), "nom refusé : x\\u2028#fin\\u000a\\u0085")


if __name__ == "__main__":
    unittest.main()
