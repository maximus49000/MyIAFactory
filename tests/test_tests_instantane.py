"""Instantané de l'arbre de travail envoyé au serveur (`outils/tests_instantane.py`) : ce qui part, ce qui ne part jamais.

Un seul dépôt git réel, construit une fois dans `setUpClass` (git init, add, commit), et une seule liste réelle
(`lister`) ; le reste passe par un faux `git` ou des dossiers temporaires de quelques fichiers."""
import ast
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import tests_instantane as ti  # noqa: E402

EXCLUS_FORCES = [".env", ".env.production", "cle/id_ed25519", "cle/id_rsa.pub", "sous/bureau.json", "x.local.json",
                 ".claude/settings.local.json", "node_modules/p/i.js", "sous/node_modules/q.js", ".factory/r.json",
                 "certs/serveur.pem", "certs/serveur.KEY", "android/app/release.keystore", "tests-sceau.json",
                 ".npmrc", "credentials.json", ".git-credentials", "android/local.properties", "infra/x.tfstate"]


def _git(argv, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                    "-c", "core.autocrlf=false"] + argv, cwd=cwd, check=True, capture_output=True,
                   stdin=subprocess.DEVNULL)


def _ecrire(racine, nom, contenu=b"x\n"):
    chemin = Path(racine, *nom.split("/"))
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)
    return chemin


def _lien_dossier(lien, cible):
    """Lien symbolique, sinon jonction (Windows sans privilège) ; False si le poste ne sait créer ni l'un ni l'autre."""
    try:
        os.symlink(cible, lien, target_is_directory=True)
        return True
    except (OSError, NotImplementedError, AttributeError):
        pass
    try:
        import _winapi
        _winapi.CreateJunction(str(cible), str(lien))
        return True
    except (ImportError, AttributeError, OSError):
        return False


def _faux_git(sorties):
    """`git` injectable : la sortie dépend du premier argument utile (`ls-files` avec ou sans `-s`)."""
    appels = []

    def git(argv, cwd):
        appels.append(list(argv))
        return sorties["-s" if "-s" in argv else "ls"]
    git.appels = appels
    return git


class TestDepotReel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="instantane-")
        cls.depot = os.path.join(cls.tmp, "depot")
        dehors = os.path.join(cls.tmp, "dehors", ".ssh")
        os.makedirs(cls.depot)
        _ecrire(dehors, "id_secret", b"CLE PRIVEE\n")
        _ecrire(cls.depot, ".gitignore", b"*.log\n.durees-tests.json\n")
        _ecrire(cls.depot, "a.py", b"print('a')\n")
        _ecrire(cls.depot, "b.py", b"print('b')\n")
        _ecrire(cls.depot, "c.log", b"journal\n")
        _ecrire(cls.depot, ".durees-tests.json", b"{}\n")
        _ecrire(cls.depot, "outil.sh", b"#!/bin/sh\necho ok\n")
        for nom in EXCLUS_FORCES:
            _ecrire(cls.depot, nom, b"SECRET\n")
        cls.lien = _lien_dossier(os.path.join(cls.depot, "l"), os.path.dirname(dehors) + os.sep + ".ssh")
        try:
            os.link(os.path.join(dehors, "id_secret"), os.path.join(cls.depot, "dur.txt"))
            cls.lien_dur = True
        except (OSError, AttributeError, NotImplementedError):
            cls.lien_dur = False
        _git(["init", "-q"], cls.depot)
        _git(["add", "-f", "--", ".gitignore", "a.py"] + EXCLUS_FORCES, cls.depot)
        _git(["commit", "-q", "-m", "depart"], cls.depot)
        cls.retenus, cls.ecartes = ti.lister(cls.depot)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _ecarte(self, nom):
        return any(e == nom or e.startswith(nom + " (") for e in self.ecartes)

    def test_suivis_et_non_suivis_non_ignores(self):
        for nom in ("a.py", "b.py", ".gitignore", "outil.sh"):
            self.assertIn(nom, self.retenus)
        self.assertNotIn("c.log", self.retenus)
        self.assertEqual(self.retenus, sorted(self.retenus))

    def test_exclus_meme_suivis(self):
        for nom in EXCLUS_FORCES:
            self.assertNotIn(nom, self.retenus)
        self.assertFalse([n for n in self.retenus if n == ".git" or n.startswith(".git/") or "/.git/" in n])
        self.assertFalse([e for e in self.ecartes if "SECRET" in e])

    def test_ajout_durees(self):
        self.assertIn(".durees-tests.json", self.retenus)

    def test_liens_ecartes_et_nommes(self):
        if not self.lien:
            self.skipTest("le poste ne sait créer ni lien symbolique ni jonction")
        self.assertFalse([n for n in self.retenus if n == "l" or n.startswith("l/")])
        self.assertTrue(any(e == "l (lien)" or e.startswith("l/") for e in self.ecartes), self.ecartes)
        tampon = io.BytesIO()
        ti.ecrire_tar(self.depot, self.retenus, tampon)
        self.assertNotIn(b"CLE PRIVEE", tampon.getvalue())

    def test_lien_dur_ecarte(self):
        if not self.lien_dur:
            self.skipTest("le poste ne sait pas créer de lien dur")
        self.assertNotIn("dur.txt", self.retenus)
        self.assertTrue(self._ecarte("dur.txt"), self.ecartes)

    def test_archive_sans_secret(self):
        tampon = io.BytesIO()
        nombre, octets = ti.ecrire_tar(self.depot, self.retenus, tampon)
        self.assertEqual(nombre, len(self.retenus))
        self.assertNotIn(b"SECRET", tampon.getvalue())
        self.assertNotIn(b"CLE PRIVEE", tampon.getvalue())


class TestSansGit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="instantane-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_nom_dangereux_refuse(self):
        for nom in ("../x", "a/../../x", "/etc/x", "a\\b", "C:x", "c:/x", "", "a//b", "a/./b", "a/", "x\0y",
                    "a/" * 200 + "b", "é" * 120):
            self.assertFalse(ti.nom_sur(nom), repr(nom))
        self.assertTrue(ti.nom_sur("src/a.py"))
        self.assertTrue(ti.nom_sur("d" * 150 + "/" + "f" * 99))
        _ecrire(self.tmp, "a.py")
        git = _faux_git({"ls": (0, "../x\0a.py\0/etc/passwd\0a\\b\0"), "-s": (0, "")})
        retenus, ecartes = ti.lister(self.tmp, git=git)
        self.assertEqual(retenus, ["a.py"])
        self.assertEqual(len(ecartes), 3)
        self.assertTrue(all("nom refusé" in e for e in ecartes), ecartes)
        self.assertIn(["ls-files", "-co", "--exclude-standard", "-z"], git.appels)

    def test_hors_depot_et_git_absent(self):
        with self.assertRaises(ti.HorsLimites) as c:
            ti.lister(self.tmp, git=lambda argv, cwd: (128, "fatal: not a git repository (or any of the parent directories): .git"))
        self.assertEqual(c.exception.raison, "le projet n'est pas un dépôt git")
        with self.assertRaises(ti.HorsLimites) as c:
            ti.lister(self.tmp, git=lambda argv, cwd: (127, "[WinError 2] introuvable"))
        self.assertIn("git", c.exception.raison)

    def test_sous_module_et_absent_ecartes(self):
        os.makedirs(os.path.join(self.tmp, "sous"))
        git = _faux_git({"ls": (0, "sous\0parti.py\0imbrique/\0"), "-s": (0, "")})
        retenus, ecartes = ti.lister(self.tmp, git=git)
        self.assertEqual(retenus, [])
        self.assertEqual(len(ecartes), 3, ecartes)

    def test_tar_reproductible_et_relisible(self):
        _ecrire(self.tmp, "src/a.py", b"print(1)\n")
        _ecrire(self.tmp, "run.sh", b"#!/bin/bash\necho\n")
        _ecrire(self.tmp, "bin/outil", b"\x7fELF...")
        _ecrire(self.tmp, "vide.txt", b"")
        fichiers = ["bin/outil", "run.sh", "src/a.py", "vide.txt"]
        un, deux = io.BytesIO(), io.BytesIO()
        self.assertEqual(ti.ecrire_tar(self.tmp, fichiers, un, executables={"bin/outil"}), (4, 9 + 17 + 7))
        os.utime(os.path.join(self.tmp, "src", "a.py"), (1, 1))
        ti.ecrire_tar(self.tmp, fichiers, deux, executables={"bin/outil"})
        self.assertEqual(un.getvalue(), deux.getvalue())
        with tarfile.open(fileobj=io.BytesIO(un.getvalue()), mode="r:") as tar:
            membres = {m.name: m for m in tar.getmembers()}
            self.assertEqual(sorted(membres), fichiers)
            for m in membres.values():
                self.assertTrue(m.isreg())
                self.assertEqual((m.uid, m.gid, m.mtime, m.uname, m.gname), (0, 0, 0, "", ""))
            self.assertEqual(membres["run.sh"].mode, 0o755)
            self.assertEqual(membres["bin/outil"].mode, 0o755)
            self.assertEqual(membres["src/a.py"].mode, 0o644)
            self.assertEqual(tar.extractfile(membres["src/a.py"]).read(), b"print(1)\n")
        self.assertEqual(un.getvalue()[257:263], b"ustar\0")

    def test_executables_lus_par_git(self):
        git = _faux_git({"ls": (0, ""), "-s": (0, "100755 " + "0" * 40 + " 0\tbin/run\0"
                                                  "100644 " + "1" * 40 + " 0\tsrc/a.py\0"
                                                  "120000 " + "2" * 40 + " 0\tlien\0")})
        self.assertEqual(ti.executables(self.tmp, git=git), {"bin/run"})

    def test_ecrire_tar_revérifie(self):
        _ecrire(self.tmp, "a.py")
        for nom in ("../a.py", ".env", "absent.py"):
            with self.assertRaises(ti.HorsLimites):
                ti.ecrire_tar(self.tmp, [nom], io.BytesIO())

    def test_limites(self):
        _ecrire(self.tmp, "petit.py", b"123")
        _ecrire(self.tmp, "src/gros.bin", b"0123456789A")
        with mock.patch.object(ti, "MAX_FICHIER", 10):
            with self.assertRaises(ti.HorsLimites) as c:
                ti.ecrire_tar(self.tmp, ["petit.py", "src/gros.bin"], io.BytesIO())
            self.assertIn("src/gros.bin", c.exception.raison)
        with mock.patch.object(ti, "MAX_TOTAL", 12):
            with self.assertRaises(ti.HorsLimites) as c:
                ti.ecrire_tar(self.tmp, ["petit.py", "src/gros.bin"], io.BytesIO())
            self.assertIn("Mo", c.exception.raison)
        with mock.patch.object(ti, "MAX_FICHIERS", 1):
            with self.assertRaises(ti.HorsLimites) as c:
                ti.ecrire_tar(self.tmp, ["petit.py", "src/gros.bin"], io.BytesIO())
            self.assertIn("fichiers", c.exception.raison)

    def test_fichier_modifie_pendant_la_lecture(self):
        _ecrire(self.tmp, "a.py", b"0123456789")
        ouvrir = open

        def ouvrir_puis_tronquer(chemin, *a, **k):
            f = ouvrir(chemin, *a, **k)
            with ouvrir(chemin, "r+b") as g:
                g.truncate(3)
            return f
        with mock.patch.object(ti, "open", ouvrir_puis_tronquer, create=True):
            with self.assertRaises(ti.HorsLimites) as c:
                ti.ecrire_tar(self.tmp, ["a.py"], io.BytesIO())
        self.assertIn("a.py", c.exception.raison)

    def test_empreinte_verrou_node(self):
        self.assertIsNone(ti.empreinte_verrou_node(self.tmp))
        _ecrire(self.tmp, "package-lock.json", b'{"lockfileVersion": 3}\n')
        attendu = hashlib.sha256(b'{"lockfileVersion": 3}\n').hexdigest()[:16]
        self.assertEqual(ti.empreinte_verrou_node(self.tmp), attendu)
        self.assertEqual(ti.empreinte_verrou_node(self.tmp), attendu)

    def test_compatible_py39(self):
        source = (RACINE / "outils" / "tests_instantane.py").read_text(encoding="utf-8")
        ast.parse(source, feature_version=(3, 9))


if __name__ == "__main__":
    unittest.main()
