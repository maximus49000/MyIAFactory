"""Instantané de l'arbre de travail envoyé au serveur (`outils/tests_instantane.py`) : ce qui part, ce qui ne part jamais.

Un seul dépôt git réel, construit une fois dans `setUpClass` (git init, add, commit), et une seule liste réelle
(`lister`) ; le reste passe par un faux `git` ou des dossiers temporaires de quelques fichiers."""
import ast
import base64
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
from tests import plateforme_tests  # noqa: E402

EXCLUS_FORCES = [".env", ".env.production", "cle/id_ed25519", "cle/id_rsa.pub", "sous/bureau.json", "x.local.json",
                 ".claude/settings.local.json", "node_modules/p/i.js", "sous/node_modules/q.js", ".factory/r.json",
                 "certs/serveur.pem", "certs/serveur.KEY", "android/app/release.keystore", "tests-sceau.json",
                 ".npmrc", "credentials.json", ".git-credentials", "android/local.properties", "infra/x.tfstate",
                 "config/prod.env", "app-firebase-adminsdk-x1.json", "secrets.properties", ".dev.vars",
                 ".streamlit/secrets.toml", "x.secret", ".mcp.json", ".m2/settings.xml", ".pgpass"]
ADMIS = ["google-services.json", "gradle.properties", "appsettings.Development.json", ".vscode/settings.json"]


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
        cle = "-s" if "-s" in argv else "-d" if "-d" in argv else "ls"
        return sorties.get(cle, (0, ""))
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
        for nom in ADMIS + ["parti.py"]:
            _ecrire(cls.depot, nom, b"{}\n")
        cls.lien = _lien_dossier(os.path.join(cls.depot, "l"), os.path.dirname(dehors) + os.sep + ".ssh")
        try:
            os.link(os.path.join(dehors, "id_secret"), os.path.join(cls.depot, "dur.txt"))
            cls.lien_dur = True
        except (OSError, AttributeError, NotImplementedError):
            cls.lien_dur = False
        _git(["init", "-q"], cls.depot)
        _git(["add", "-f", "--", ".gitignore", "a.py", "parti.py"] + EXCLUS_FORCES, cls.depot)
        _git(["commit", "-q", "-m", "depart"], cls.depot)
        os.remove(os.path.join(cls.depot, "parti.py"))
        cls.retenus, cls.ecartes = ti.lister(cls.depot)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _ecarte(self, nom):
        return any(e == nom or e.startswith(nom + " (") for e in self.ecartes)

    def test_suivis_et_non_suivis_non_ignores(self):
        for nom in ["a.py", "b.py", ".gitignore", "outil.sh"] + ADMIS:
            self.assertIn(nom, self.retenus)
        self.assertNotIn("c.log", self.retenus)
        self.assertEqual(self.retenus, sorted(self.retenus))

    def test_supprime_suivi_ni_retenu_ni_nomme(self):
        self.assertNotIn("parti.py", self.retenus)
        self.assertFalse(self._ecarte("parti.py"), self.ecartes)

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

    def _piege(self, action, autre=None):
        """`open` de remplacement pour ti : le fichier rendu exécute `action(n, chemin)` avant sa n-ième lecture."""
        ouvrir = open

        class Piege:
            def __init__(self, chemin, *a, **k):
                self.chemin, self.f, self.n = chemin, ouvrir(autre or chemin, *a, **k), 0

            def read(self, n=-1):
                self.n += 1
                action(self.n, self.chemin)
                return self.f.read(n)

            def __getattr__(self, attr):
                return getattr(self.f, attr)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.f.close()
        return mock.patch.object(ti, "open", Piege, create=True)

    def _refus_ecriture(self, nom="a.py"):
        with self.assertRaises(ti.HorsLimites) as c:
            ti.ecrire_tar(self.tmp, [nom], io.BytesIO())
        self.assertIn(nom, c.exception.raison)
        return c.exception.raison

    def test_remplace_apres_lstat(self):
        _ecrire(self.tmp, "a.py", b"0123456789")
        autre = _ecrire(self.tmp, "autre.py", b"9876543210")
        with self._piege(lambda n, c: None, autre=str(autre)):
            self.assertIn("remplacé", self._refus_ecriture())
        git = _faux_git({"ls": (0, "a.py\0")})
        with self._piege(lambda n, c: None, autre=str(autre)):
            self.assertEqual(ti.lister(self.tmp, git=git), ([], ["a.py (remplacé pendant la lecture)"]))

    def test_croissance_apres_ouverture(self):
        _ecrire(self.tmp, "a.py", b"0123456789")

        def grossir(n, chemin):
            if n == 1:
                with open(chemin, "ab") as g:
                    g.write(b"PLUS")
        with self._piege(grossir):
            self.assertIn("modifié", self._refus_ecriture())

    def test_date_changee_pendant_la_lecture(self):
        _ecrire(self.tmp, "a.py", b"0123456789")
        with self._piege(lambda n, c: n == 1 and os.utime(c, ns=(10 ** 9, 10 ** 9))):
            self.assertIn("modifié", self._refus_ecriture())

    def test_erreur_de_lecture(self):
        _ecrire(self.tmp, "a.py", b"0123456789")

        def casser(n, chemin):
            if n == 2:
                raise OSError("disque")
        with self._piege(casser):
            self.assertIn("lecture impossible", self._refus_ecriture())

    def test_identite_nulle_refusee(self):
        _ecrire(self.tmp, "a.py")
        reel = os.lstat

        def sans_inode(chemin):
            s = reel(chemin)
            return os.stat_result((s.st_mode, 0, s.st_dev, s.st_nlink, s.st_uid, s.st_gid, s.st_size,
                                   int(s.st_atime), int(s.st_mtime), int(s.st_ctime)))
        with mock.patch.object(ti.os, "lstat", sans_inode):
            with self.assertRaises(ti.HorsLimites) as c:
                ti.lister(self.tmp, git=_faux_git({"ls": (0, "a.py\0")}))
        self.assertIn("identité", c.exception.raison)

    def test_pointeur_git_de_sous_module_jamais(self):
        _ecrire(self.tmp, "sous/.git", b"gitdir: ../../.git/modules/sous\n")
        _ecrire(self.tmp, "sous/a.py")
        retenus, ecartes = ti.lister(self.tmp, git=_faux_git({"ls": (0, "sous/.git\0sous/a.py\0.git/config\0")}))
        self.assertEqual((retenus, ecartes), (["sous/a.py"], []))

    def test_cle_privee_par_le_contenu(self):
        # Fausses clés : un corps base64 tiré au hasard à chaque essai (jamais une vraie clé dans le dépôt).
        def corps(sep=b"\n"):
            return sep.join(base64.b64encode(os.urandom(48)) for _ in range(3)) + sep
        debut, fin = b"-----BEGIN %s PRIVATE KEY-----", b"-----END %s PRIVATE KEY-----"
        _ecrire(self.tmp, "fixtures/cle.txt",
                b"x\n" + debut % b"OPENSSH" + b"\n" + corps() + fin % b"OPENSSH" + b"\n")
        _ecrire(self.tmp, "src/rsa.py", b'CLE = """' + debut % b"RSA" + b"\r\n" + corps(b"\r\n") + b'"""\n')
        compte = (b'{"type": "service_account", "private_key": "-----BEGIN PRIVATE KEY-----\\n' + corps(b"\\n")
                  + b'-----END PRIVATE KEY-----\\n", "client_email": "a@b"}')
        _ecrire(self.tmp, "compte.json", compte)
        _ecrire(self.tmp, "publique.txt", b"-----BEGIN PUBLIC KEY-----\n" + corps())
        _ecrire(self.tmp, "doc.md", b'Le champ "private_key" est lu par ...\n')
        _ecrire(self.tmp, "loin.txt", b"x" * ti.LECTURE_CONTENU + debut % b"RSA" + b"\n" + corps())
        # Mentions dans du code : un motif, une expression régulière, une fixture sans corps, des noms de champs.
        _ecrire(self.tmp, "motif.py", b'MOTIF = re.compile(rb"-----BEGIN[^\\r\\n]{0,100}PRIVATE KEY-----")\n'
                                      b'X = b"-----BEGIN OPENSSH PRIVATE KEY-----\\nAAAA\\n"\n'
                                      b'Y = """-----BEGIN RSA PRIVATE KEY-----\n"""\n-----END RSA PRIVATE KEY-----\n')
        _ecrire(self.tmp, "champs.py", b'CHAMPS = ("private_key", "client_email")\n'
                                       b'J = \'{"private_key": "-----BEGIN PRIVATE KEY-----\\\\nAAAA", '
                                       b'"client_email": "a@b"}\'\n')
        _ecrire(self.tmp, "court.txt", debut % b"EC" + b"\nAAAA\nBBBB\n" + fin % b"EC" + b"\n")
        noms = ["fixtures/cle.txt", "src/rsa.py", "compte.json", "publique.txt", "doc.md", "loin.txt", "motif.py",
                "champs.py", "court.txt"]
        git = _faux_git({"ls": (0, "".join(n + "\0" for n in noms))})
        retenus, ecartes = ti.lister(self.tmp, git=git)
        self.assertEqual(retenus, ["champs.py", "court.txt", "doc.md", "loin.txt", "motif.py", "publique.txt"])
        self.assertEqual(sorted(ecartes), ["compte.json (clé privée)", "fixtures/cle.txt (clé privée)",
                                           "src/rsa.py (clé privée)"])
        self.assertIn("clé privée", self._refus_ecriture("fixtures/cle.txt"))

    def test_le_code_de_l_instantane_part_vers_le_serveur(self):
        # Le module et ses tests citent l'en-tête PEM comme motif : ils ne doivent pas s'écarter eux-mêmes.
        for chemin in (RACINE / "outils" / "tests_instantane.py", Path(__file__)):
            self.assertFalse(ti._contenu_secret(chemin.read_bytes()[:ti.LECTURE_CONTENU]), chemin.name)

    def test_doublons_refuses_par_ecrire_tar(self):
        _ecrire(self.tmp, "a.py")
        with self.assertRaises(ti.HorsLimites) as c:
            ti.ecrire_tar(self.tmp, ["a.py", "A.py" if os.name == "nt" else "./a.py"], io.BytesIO())
        self.assertIn("a.py", c.exception.raison)

    def test_trop_de_fichiers_avant_le_disque(self):
        git = _faux_git({"ls": (0, "a.py\0b.py\0node_modules/x.js\0")})
        with mock.patch.object(ti, "MAX_FICHIERS", 1), mock.patch.object(ti, "_verifier", side_effect=AssertionError):
            with self.assertRaises(ti.HorsLimites) as c:
                ti.lister(self.tmp, git=git)
        self.assertIn("2", c.exception.raison)

    def test_git_durci(self):
        appels = []

        def run(argv, **k):
            appels.append((argv, k))
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        herite = {"GIT_DIR": "x", "GIT_WORK_TREE": "y", "GIT_INDEX_FILE": "z", "GIT_CEILING_DIRECTORIES": "c",
                  "GIT_CONFIG_PARAMETERS": "'core.fsmonitor'='evil'", "GIT_CONFIG_COUNT": "1",
                  "GIT_CONFIG_KEY_0": "core.fsmonitor", "GIT_CONFIG_VALUE_0": "evil", "GIT_CONFIG_NOSYSTEM": "0"}
        with mock.patch.dict(os.environ, herite), mock.patch.object(ti.subprocess, "run", run):
            ti.lister(self.tmp)
            ti.executables(self.tmp)
        self.assertEqual(len(appels), 3)
        for argv, k in appels:
            self.assertEqual(argv[:9], ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
                                        "-c", "core.hooksPath=" + os.devnull, "-c", "core.quotepath=off"])
            env = k["env"]
            self.assertEqual(sorted(c for c in env if c.upper().startswith("GIT_")),
                             ["GIT_CONFIG_NOSYSTEM", "GIT_OPTIONAL_LOCKS", "GIT_TERMINAL_PROMPT"])
            self.assertEqual((env["GIT_CONFIG_NOSYSTEM"], env["GIT_TERMINAL_PROMPT"]), ("1", "0"))

    @plateforme_tests.windows_seulement("noms courts 8.3, flux et périphériques de Windows")
    def test_noms_windows_refuses(self):
        git = _faux_git({"ls": (0, "a.py.\0nul.txt\0src/a.py:flux\0ENV~1\0cle/ID_ED2~1\0b.py \0")})
        retenus, ecartes = ti.lister(self.tmp, git=git)
        self.assertEqual(retenus, [])
        self.assertEqual(sorted(ecartes), sorted(["ENV~1 (nom court 8.3)", "cle/ID_ED2~1 (nom court 8.3)",
                                                  "a.py. (nom refusé sous Windows)",
                                                  "nul.txt (nom refusé sous Windows)",
                                                  "src/a.py:flux (nom refusé sous Windows)",
                                                  "b.py  (nom refusé sous Windows)"]))

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
