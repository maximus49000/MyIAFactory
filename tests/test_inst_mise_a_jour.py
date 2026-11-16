"""La mise à jour automatique de la skill. De vrais dépôts git locaux : un distant nu, un poste A qui fait évoluer la
skill, un poste B qui doit la recevoir (jamais un distant réel)."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from installation import mise_a_jour


def git(*args, cwd):
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, check=False)
    if p.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} : {(p.stdout + p.stderr).decode('utf-8', 'replace')}")
    return p.stdout.decode("utf-8", "replace").strip()


class DeuxPostes(unittest.TestCase):
    """Les dépôts sont construits une fois pour la classe ; chaque test en reçoit une copie."""

    @classmethod
    def setUpClass(cls):
        cls._modele = tempfile.TemporaryDirectory()
        m = Path(cls._modele.name)
        git("init", "-q", "--bare", "-b", "main", str(m / "distant.git"), cwd=m)
        git("init", "-q", "-b", "main", str(m / "a"), cwd=m)
        cls.identite(m / "a")
        (m / "a" / "orchestrateur" / "memoire").mkdir(parents=True)
        (m / "a" / "moteur.py").write_text("version = 1\n", encoding="utf-8")
        (m / "a" / "orchestrateur" / "memoire" / "skill.md").write_text("# Mémoire\n", encoding="utf-8")
        git("add", "-A", cwd=m / "a")
        git("commit", "-q", "-m", "départ", cwd=m / "a")
        git("remote", "add", "origin", str(m / "distant.git"), cwd=m / "a")
        git("push", "-q", "-u", "origin", "main", cwd=m / "a")
        git("clone", "-q", str(m / "distant.git"), str(m / "b"), cwd=m)
        cls.identite(m / "b")

    @classmethod
    def tearDownClass(cls):
        cls._modele.cleanup()

    @staticmethod
    def identite(depot):
        git("config", "user.email", "test@exemple.invalid", cwd=depot)
        git("config", "user.name", "Test", cwd=depot)

    def setUp(self):
        import shutil
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        t = Path(self._t.name)
        shutil.copytree(self._modele.name, t, dirs_exist_ok=True)
        self.a, self.b = t / "a", t / "b"
        for poste in (self.a, self.b):
            git("remote", "set-url", "origin", str(t / "distant.git"), cwd=poste)

    def evoluer_sur_a(self, texte="version = 2\n", message="Évolution sur A"):
        (self.a / "moteur.py").write_text(texte, encoding="utf-8")
        git("commit", "-q", "-am", message, cwd=self.a)
        git("push", "-q", cwd=self.a)

    def lu_sur_b(self):
        return (self.b / "moteur.py").read_text(encoding="utf-8")


class TestVerifier(DeuxPostes):
    def test_rien_de_neuf(self):
        r = mise_a_jour.verifier(self.b)
        self.assertEqual(r["etat"], "a_jour")
        self.assertEqual(r["version"], git("rev-parse", "--short", "HEAD", cwd=self.b))

    def test_a_pousse_b_se_met_a_jour(self):
        self.evoluer_sur_a()
        r = mise_a_jour.verifier(self.b)
        self.assertEqual(r["etat"], "mise_a_jour", r)
        self.assertEqual(self.lu_sur_b(), "version = 2\n")
        self.assertEqual(len(r["commits"]), 1)
        self.assertIn("Évolution sur A", r["commits"][0])
        self.assertEqual(mise_a_jour.verifier(self.b)["etat"], "a_jour")   # rien de plus ensuite

    def test_fichier_modifie_sur_b_rien_n_est_ecrase(self):
        self.evoluer_sur_a()
        (self.b / "moteur.py").write_text("version = travail local\n", encoding="utf-8")
        tete = git("rev-parse", "HEAD", cwd=self.b)
        r = mise_a_jour.verifier(self.b)
        self.assertEqual(r["etat"], "bloquee")
        self.assertIn("moteur.py", r["fichiers"])
        self.assertEqual(self.lu_sur_b(), "version = travail local\n")   # intact
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.b), tete)
        self.assertEqual(git("stash", "list", cwd=self.b), "")           # jamais de pile

    def test_fichier_non_suivi_ne_bloque_pas(self):
        self.evoluer_sur_a()
        (self.b / "brouillon.txt").write_text("à moi\n", encoding="utf-8")
        r = mise_a_jour.verifier(self.b)
        self.assertEqual(r["etat"], "mise_a_jour", r)
        self.assertTrue((self.b / "brouillon.txt").is_file())

    def test_lecon_locale_rebasee(self):
        lecon = self.b / "orchestrateur" / "memoire" / "skill.md"
        lecon.write_text("# Mémoire\n\n## S1 — Une leçon\n", encoding="utf-8")
        git("commit", "-q", "-am", "Mémoire (skill) : Une leçon", cwd=self.b)
        self.evoluer_sur_a()
        r = mise_a_jour.verifier(self.b)
        self.assertEqual(r["etat"], "mise_a_jour", r)
        self.assertEqual(self.lu_sur_b(), "version = 2\n")
        self.assertIn("S1", lecon.read_text(encoding="utf-8"))   # la leçon locale est gardée, au-dessus
        self.assertEqual(git("rev-list", "--count", "@{u}..HEAD", cwd=self.b), "1")

    def test_developpement_non_pousse_attend(self):
        (self.b / "nouveau.py").write_text("x = 1\n", encoding="utf-8")
        git("add", "nouveau.py", cwd=self.b)
        git("commit", "-q", "-m", "Développement sur B", cwd=self.b)
        self.evoluer_sur_a()
        tete = git("rev-parse", "HEAD", cwd=self.b)
        r = mise_a_jour.verifier(self.b)
        self.assertEqual(r["etat"], "bloquee")
        self.assertIn("nouveau.py", r["fichiers"])
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.b), tete)

    def test_conflit_de_lecon_defait(self):
        lecon_b = self.b / "orchestrateur" / "memoire" / "skill.md"
        lecon_b.write_text("# Mémoire de B\n", encoding="utf-8")
        git("commit", "-q", "-am", "Mémoire (skill) : de B", cwd=self.b)
        (self.a / "orchestrateur" / "memoire" / "skill.md").write_text("# Mémoire de A\n", encoding="utf-8")
        git("commit", "-q", "-am", "Mémoire (skill) : de A", cwd=self.a)
        git("push", "-q", cwd=self.a)
        tete = git("rev-parse", "HEAD", cwd=self.b)
        r = mise_a_jour.verifier(self.b)
        self.assertEqual(r["etat"], "bloquee", r)
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.b), tete)
        self.assertEqual(lecon_b.read_text(encoding="utf-8"), "# Mémoire de B\n")
        self.assertFalse((self.b / ".git" / "rebase-merge").exists())   # jamais laissé au milieu d'un rebase

    def test_distant_injoignable(self):
        git("remote", "set-url", "origin", str(Path(self._t.name) / "absent.git"), cwd=self.b)
        r = mise_a_jour.verifier(self.b)
        self.assertEqual(r["etat"], "injoignable")

    def test_sans_branche_suivie(self):
        git("checkout", "-q", "--detach", cwd=self.b)
        self.assertEqual(mise_a_jour.verifier(self.b)["etat"], "sans_suivi")


class TestSuivre(DeuxPostes):
    def etat(self):
        return Path(self._t.name) / "mise-a-jour.json"

    def test_le_moteur_voit_une_mise_a_jour_faite_par_un_autre(self):
        suivre = mise_a_jour.suivre(self.b, chemin=self.etat())      # le moteur démarre sur la version d'origine
        self.assertEqual(suivre()["etat"], "a_jour")
        self.evoluer_sur_a()
        self.assertEqual(mise_a_jour.verifier(self.b)["etat"], "mise_a_jour")   # le lancement du bureau la prend
        r = suivre()                                                 # le moteur, lui, tourne encore sur l'ancien code
        self.assertEqual(r["etat"], "mise_a_jour")
        self.assertIn("a changé sur ce poste", r["message"])
        self.assertEqual(json.loads(self.etat().read_text(encoding="utf-8"))["etat"], "a_jour")   # le dépôt l'est

    def test_suivre_note_l_etat(self):
        self.evoluer_sur_a()
        mise_a_jour.suivre(self.b, chemin=self.etat())()
        self.assertEqual(json.loads(self.etat().read_text(encoding="utf-8"))["etat"], "mise_a_jour")


class TestBureau(unittest.TestCase):
    def lancer(self, maj, relancer=False):
        from types import SimpleNamespace
        from unittest import mock
        from installation import outil
        appels = []
        with mock.patch.object(outil.lanceur, "lancer", lambda relancer=False: appels.append(relancer) or {"url": "u"}):
            r = outil.cmd_bureau(SimpleNamespace(relancer=relancer), verifier=lambda: maj)
        return r, appels

    def test_mise_a_jour_faite_le_bureau_est_relance(self):
        r, appels = self.lancer({"etat": "mise_a_jour", "message": "Skill mise à jour."})
        self.assertEqual(appels, [True])
        self.assertEqual(r["mise_a_jour"], "Skill mise à jour.")

    def test_a_jour_le_bureau_n_est_pas_relance(self):
        _, appels = self.lancer({"etat": "a_jour", "message": "ok"})
        self.assertEqual(appels, [False])

    def test_une_verification_ratee_n_empeche_pas_le_bureau(self):
        from types import SimpleNamespace
        from unittest import mock
        from installation import outil

        def casse():
            raise OSError("réseau")
        with mock.patch.object(outil.lanceur, "lancer", lambda relancer=False: {"url": "u"}):
            r = outil.cmd_bureau(SimpleNamespace(relancer=False), verifier=casse)
        self.assertIn("réseau", r["mise_a_jour"])


class TestEtat(unittest.TestCase):
    def test_ecrire_etat(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "mise-a-jour.json"
            mise_a_jour.ecrire_etat({"etat": "a_jour", "message": "ok"}, chemin, t="2026-11-16T10:00:00+01:00")
            lu = json.loads(chemin.read_text(encoding="utf-8"))
            self.assertEqual((lu["etat"], lu["t"]), ("a_jour", "2026-11-16T10:00:00+01:00"))


if __name__ == "__main__":
    unittest.main()
