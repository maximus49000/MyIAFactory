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
        self.assertEqual(kw["input"], b"SECRET-LICENCE")
        self.assertNotIn("text", kw)
        self.assertFalse(any("SECRET-LICENCE" in a for a in args))

    def test_stdin_en_octets_sans_retour_chariot_et_aller_retour_utf8(self):
        r = Runner()
        texte = "#!/bin/bash\necho é à ü\nfin\n"
        plateforme_ssh.executer(HOTE, "cat > /tmp/f", Path("cle"), stdin=texte, runner=r)
        envoye = r.appels[0][1]["input"]
        self.assertIsInstance(envoye, bytes)
        self.assertNotIn(b"\r", envoye)
        self.assertEqual(envoye.decode("utf-8"), texte)

    def test_sortie_en_octets_decodee_sans_planter(self):
        def runner(args, **kw):
            return subprocess.CompletedProcess(args, 0, stdout="é\n".encode("utf-8"), stderr=b"\xff")
        code, sortie, erreur = plateforme_ssh.executer(HOTE, "x", Path("cle"), runner=runner)
        self.assertEqual((code, sortie), (0, "é\n"))
        self.assertIsInstance(erreur, str)

    def test_delai_expire_renvoie_un_echec(self):
        def runner(args, **kw):
            raise subprocess.TimeoutExpired(args, kw["timeout"])
        code, _, erreur = plateforme_ssh.executer(HOTE, "x", Path("cle"), delai=5, runner=runner)
        self.assertNotEqual(code, 0)
        self.assertIn("délai", erreur)


def _introuvable(args, **kw):
    raise FileNotFoundError(args[0])


def _lent(args, **kw):
    raise subprocess.TimeoutExpired(args, 1)


class TestDurcissement(unittest.TestCase):
    def test_hote_commencant_par_tiret_refuse(self):
        for hote in ("-oProxyCommand=x", "", "  "):
            r = Runner()
            with self.assertRaises(ValueError):
                plateforme_ssh.executer(hote, "true", Path("cle"), runner=r)
            self.assertEqual(r.appels, [])
        with self.assertRaises(ValueError):
            plateforme_ssh.oublier_hote("-oProxyCommand=x", True, runner=Runner())

    def test_double_tiret_avant_l_hote(self):
        r = Runner()
        plateforme_ssh.executer(HOTE, "true", Path("cle"), runner=r)
        args = r.appels[0][0]
        self.assertEqual(args[args.index(HOTE) - 1], "--")
        self.assertIn("IdentitiesOnly=yes", args)

    def test_stdin_ferme_sans_entree(self):
        r = Runner()
        plateforme_ssh.executer(HOTE, "true", Path("cle"), runner=r)
        kw = r.appels[0][1]
        self.assertIs(kw["stdin"], subprocess.DEVNULL)
        self.assertNotIn("input", kw)
        r = Runner()
        plateforme_ssh.executer(HOTE, "true", Path("cle"), stdin="x", runner=r)
        self.assertNotIn("stdin", r.appels[0][1])

    def test_ssh_absent_erreur_lisible(self):
        with self.assertRaises(plateforme_ssh.ErreurSsh) as c:
            plateforme_ssh.executer(HOTE, "true", Path("cle"), runner=_introuvable)
        self.assertIn("OpenSSH", str(c.exception))
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(plateforme_ssh.ErreurSsh):
                plateforme_ssh.generer_cle(Path(d), runner=_introuvable)
        with self.assertRaises(plateforme_ssh.ErreurSsh):
            plateforme_ssh.oublier_hote(HOTE, True, runner=_introuvable)

    def test_attendre_ssh_s_arrete_si_ssh_absent(self):
        pauses = []
        with self.assertRaises(plateforme_ssh.ErreurSsh):
            plateforme_ssh.attendre_ssh(HOTE, Path("cle"), 100, runner=_introuvable, dormir=pauses.append)
        self.assertEqual(pauses, [])

    def test_delai_keygen_et_oubli_erreur_lisible(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(plateforme_ssh.ErreurSsh):
                plateforme_ssh.generer_cle(Path(d), runner=_lent)
        with self.assertRaises(plateforme_ssh.ErreurSsh):
            plateforme_ssh.oublier_hote(HOTE, True, runner=_lent)


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
