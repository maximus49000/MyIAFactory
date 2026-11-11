"""Le dossier stable ~/MyIAFactory. Git et le lien sont simulés ; HOME et USERPROFILE sont temporaires."""
import os
import tempfile
import unittest
from pathlib import Path

from installation import dossier


class AvecMaison(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.maison = Path(self._tmp.name) / "Zoé Martin"
        self.maison.mkdir()
        anciens = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE")}
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.maison)

        def rendre():
            for k, v in anciens.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.addCleanup(rendre)
        self.appels = []

    def git(self, code=0, sortie=""):
        def f(args, cwd):
            self.appels.append((list(args), str(cwd)))
            return code, sortie
        return f

    def faire_depot(self, chemin):
        chemin = Path(chemin)
        (chemin / ".git").mkdir(parents=True)
        return chemin


class TestDossier(AvecMaison):
    def test_racine_suit_home(self):
        self.assertEqual(dossier.racine(), self.maison / "MyIAFactory")
        self.assertEqual(dossier.skill(), self.maison / "MyIAFactory" / "skill")
        self.assertEqual(dossier.bureau(), self.maison / "MyIAFactory" / "bureau.json")
        self.assertEqual(dossier.propositions(), self.maison / "MyIAFactory" / "propositions")

    def test_clone_au_premier_usage(self):
        r = dossier.preparer(git=self.git())
        self.assertEqual(r["action"], "clone")
        self.assertEqual(self.appels[0][0], ["clone", dossier.DEPOT, str(dossier.skill())])
        self.assertTrue(dossier.racine().is_dir())

    def test_clone_echoue_message_clair(self):
        with self.assertRaises(dossier.Echec) as c:
            dossier.preparer(git=self.git(1, "pas de réseau"))
        self.assertIn("pas de réseau", str(c.exception))

    def test_pull_aux_suivants(self):
        self.faire_depot(dossier.skill())
        r = dossier.preparer(git=self.git())
        self.assertEqual(r["action"], "mise_a_jour")
        self.assertEqual(self.appels[0][0], ["pull", "--ff-only"])

    def test_pull_echoue_continue(self):
        self.faire_depot(dossier.skill())
        r = dossier.preparer(git=self.git(1, "droits refusés"))
        self.assertEqual(r["action"], "mise_a_jour")
        self.assertIn("droits refusés", r["message"])

    def test_lier_un_clone_existant(self):
        clone = Path(self._tmp.name) / "dev"
        (clone / "orchestrateur").mkdir(parents=True)
        (clone / "orchestrateur" / "outil.py").write_text("", encoding="utf-8")
        liens = []
        r = dossier.preparer(lier=clone, git=self.git(), lien=lambda c, l: liens.append((Path(c), Path(l))))
        self.assertEqual(r["action"], "lien")
        self.assertEqual(liens, [(clone, dossier.skill())])
        self.assertEqual(self.appels, [])

    def test_deja_lie(self):
        clone = Path(self._tmp.name) / "dev"
        (clone / "orchestrateur").mkdir(parents=True)
        (clone / "orchestrateur" / "outil.py").write_text("", encoding="utf-8")
        (clone / ".git").mkdir()
        dossier.racine().mkdir()
        dossier.creer_lien(clone, dossier.skill())
        r = dossier.preparer(lier=clone, git=self.git(), lien=lambda c, l: self.fail("lien refait"))
        self.assertEqual(r["action"], "deja_lie")

    def test_lier_refuse_un_dossier_qui_n_est_pas_la_skill(self):
        autre = Path(self._tmp.name) / "autre"
        autre.mkdir()
        with self.assertRaises(dossier.Echec):
            dossier.preparer(lier=autre, git=self.git(), lien=lambda c, l: self.fail("lien créé"))

    def test_creer_lien_reel(self):
        cible = Path(self._tmp.name) / "cible"
        cible.mkdir()
        (cible / "x.txt").write_text("ok", encoding="utf-8")
        lien = Path(self._tmp.name) / "a b" / "lien"
        dossier.creer_lien(cible, lien)
        self.assertEqual((lien / "x.txt").read_text(encoding="utf-8"), "ok")


if __name__ == "__main__":
    unittest.main()
