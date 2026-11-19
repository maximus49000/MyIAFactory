"""Exécuteur SSH et clé dédiée (`outils/plateforme_ssh.py`). Le runner est simulé : aucune connexion réelle."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import plateforme_ssh  # noqa: E402
from plateforme_ovh import ErreurAccord  # noqa: E402

HOTE = "203.0.113.7"


class Runner:
    def __init__(self, codes=None):
        self.codes = list(codes or [])
        self.appels = []

    def __call__(self, args, **kw):
        self.appels.append((list(args), kw))
        code = self.codes.pop(0) if self.codes else 0
        return subprocess.CompletedProcess(args, code, stdout="sortie", stderr="erreur")


class TestExecuter(unittest.TestCase):
    def test_options_sures_presentes_et_jamais_no(self):
        r = Runner()
        code, sortie, erreur = plateforme_ssh.executer(HOTE, "uname -a", Path("cle"), runner=r)
        args = r.appels[0][0]
        self.assertEqual((code, sortie, erreur), (0, "sortie", "erreur"))
        for option in ("BatchMode=yes", "StrictHostKeyChecking=accept-new", "PasswordAuthentication=no"):
            self.assertIn(option, args)
        self.assertNotIn("StrictHostKeyChecking=no", args)
        self.assertEqual(args[args.index("-i") + 1], str(Path("cle")))
        self.assertIn("uname -a", args)

    def test_stdin_transmis_et_pas_dans_la_commande(self):
        r = Runner()
        plateforme_ssh.executer(HOTE, "cat > /tmp/f", Path("cle"), stdin="SECRET-LICENCE", runner=r)
        args, kw = r.appels[0]
        self.assertEqual(kw["input"], "SECRET-LICENCE")
        self.assertFalse(any("SECRET-LICENCE" in a for a in args))

    def test_delai_expire_renvoie_un_echec(self):
        def runner(args, **kw):
            raise subprocess.TimeoutExpired(args, kw["timeout"])
        code, _, erreur = plateforme_ssh.executer(HOTE, "x", Path("cle"), delai=5, runner=runner)
        self.assertNotEqual(code, 0)
        self.assertIn("délai", erreur)


class TestAttendre(unittest.TestCase):
    def test_attendre_ssh_patiente_puis_reussit(self):
        r = Runner([255, 255, 255, 0])
        pauses = []
        self.assertTrue(plateforme_ssh.attendre_ssh(HOTE, Path("cle"), 100, pas=10, runner=r, dormir=pauses.append))
        self.assertEqual(len(pauses), 3)

    def test_attendre_ssh_abandonne_au_delai(self):
        r = Runner([255] * 50)
        pauses = []
        self.assertFalse(plateforme_ssh.attendre_ssh(HOTE, Path("cle"), 30, pas=10, runner=r, dormir=pauses.append))
        self.assertLessEqual(len(pauses), 3)


class TestOublier(unittest.TestCase):
    def test_oublier_hote_sans_accord_refuse(self):
        for accord in (False, None, "oui", 1):
            r = Runner()
            with self.assertRaises(ErreurAccord):
                plateforme_ssh.oublier_hote(HOTE, accord, runner=r)
            self.assertEqual(r.appels, [])

    def test_oublier_hote_avec_accord(self):
        r = Runner()
        plateforme_ssh.oublier_hote(HOTE, True, runner=r)
        self.assertEqual(r.appels[0][0], ["ssh-keygen", "-R", HOTE])


class TestCle(unittest.TestCase):
    def test_generation_appelle_ssh_keygen_ed25519(self):
        with tempfile.TemporaryDirectory() as d:
            appels = []

            def runner(args, **kw):
                appels.append(list(args))
                chemin = Path(args[args.index("-f") + 1])
                chemin.write_text("prive")
                Path(str(chemin) + ".pub").write_text("ssh-ed25519 AAAA test\n")
                return subprocess.CompletedProcess(args, 0, "", "")
            chemin, publique = plateforme_ssh.generer_cle(Path(d), runner=runner)
            self.assertEqual(publique, "ssh-ed25519 AAAA test")
            self.assertIn("ed25519", appels[0])
            self.assertEqual(chemin.parent, Path(d))

    def test_cle_existante_non_ecrasee(self):
        with tempfile.TemporaryDirectory() as d:
            prive = Path(d) / plateforme_ssh.NOM_CLE
            prive.write_text("PRIVEE")
            Path(str(prive) + ".pub").write_text("ssh-ed25519 BBBB existante\n")
            r = Runner()
            chemin, publique = plateforme_ssh.generer_cle(Path(d), runner=r)
            self.assertEqual(r.appels, [])
            self.assertEqual(publique, "ssh-ed25519 BBBB existante")
            self.assertEqual(prive.read_text(), "PRIVEE")


if __name__ == "__main__":
    unittest.main()
