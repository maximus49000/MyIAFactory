"""Une tâche d'agent serveur qui ne modifie aucun fichier n'a rien à fusionner : jamais un blocage « conflit de fusion »
(essai réel FM_Stats a12, t284 : « la branche n'a pas pu être lue avant sa fusion », branche absente)."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from moteur import boucle, cloud, regles


class Depot(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        self.git("init", "-q")
        self.git("config", "user.email", "x@x")
        self.git("config", "user.name", "x")
        self.git("config", "commit.gpgsign", "false")
        (self.d / "a.txt").write_text("a\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")
        self.principale = self.git("rev-parse", "--abbrev-ref", "HEAD").stdout.decode().strip()

    def git(self, *a):
        return subprocess.run(["git", *a], cwd=self.d, capture_output=True)

    def tete(self):
        return self.git("rev-parse", "HEAD").stdout.decode().strip()

    def branche_avec_commit(self, nom):
        self.git("checkout", "-q", "-b", nom)
        (self.d / "b.txt").write_text("b\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "travail")
        self.git("checkout", "-q", self.principale)


class EtatDeLaBranche(Depot):
    def test_absente_vide_a_fusionner(self):
        self.assertEqual(cloud.etat_de_la_branche(str(self.d), "agent/t1")[0], "absente")
        self.git("branch", "agent/t2")                        # au même commit : aucun commit à ajouter
        self.assertEqual(cloud.etat_de_la_branche(str(self.d), "agent/t2")[0], "vide")
        self.branche_avec_commit("agent/t3")
        self.assertEqual(cloud.etat_de_la_branche(str(self.d), "agent/t3")[0], "a_fusionner")

    def test_illisible_dit_pourquoi(self):
        def executer(argv, cwd, delai):
            return 128, b"fatal: objet corrompu"
        etat, raison = cloud.etat_de_la_branche(".", "agent/t1", executer=executer)
        self.assertEqual(etat, "illisible")
        self.assertIn("corrompu", raison)


class FusionDUneTacheSansCommit(Depot):
    def test_branche_absente_pas_de_fusion_pas_de_blocage(self):
        avant = self.tete()
        self.assertIsNone(cloud.fusionner(str(self.d), "agent/t1", distante=False))
        self.assertEqual(self.tete(), avant)                  # aucune fusion tentée

    def test_branche_vide_idem(self):
        self.git("branch", "agent/t2")
        avant = self.tete()
        self.assertIsNone(cloud.fusionner(str(self.d), "agent/t2", distante=False))
        self.assertEqual(self.tete(), avant)
        self.assertEqual(self.git("log", "--format=%s").stdout.decode().count("Factory : fusion"), 0)

    def test_avec_commit_la_fusion_se_fait_comme_avant(self):
        self.branche_avec_commit("agent/t3")
        self.assertIsNone(cloud.fusionner(str(self.d), "agent/t3", distante=False))
        self.assertEqual((self.d / "b.txt").read_text(encoding="utf-8"), "b\n")
        self.assertEqual(self.git("log", "-1", "--format=%s").stdout.decode().strip(), "Factory : fusion de agent/t3")

    def test_branche_illisible_le_blocage_dit_precisement_pourquoi(self):
        def executer(argv, cwd, delai):
            return (128, b"fatal: refs/heads/agent/t4 corrompu") if argv[1] == "show-ref" else (0, b"")
        raison = cloud.fusionner(".", "agent/t4", executer=executer, distante=False)
        self.assertIn("illisible", raison)
        self.assertIn("corrompu", raison)
        self.assertNotIn("conflit", raison)


class DansLaBoucle(Depot):
    def moteur(self):
        m = SimpleNamespace(cloud=cloud, executes=[], notes=[])
        m._noter = lambda projet, texte: m.notes.append(texte)
        m._executer = lambda projet, actions: m.executes.append(actions)
        m._dater_les_livrables_rapatries = lambda projet, e: None
        return m

    def test_tache_sans_commit_close_normalement_et_dite_sans_fusion_impossible(self):
        m, e = self.moteur(), SimpleNamespace(serveur=True, branche="agent/t9", tache="t9", agent="a")
        projet = SimpleNamespace(dossier=self.d)
        with mock.patch.object(regles, "_journal") as journal, mock.patch.object(regles, "fusion_impossible") as impossible:
            boucle.Moteur._fusionner(m, projet, {}, e)
        impossible.assert_not_called()
        self.assertEqual(m.executes, [])
        self.assertIn("Rien à fusionner", journal.call_args.args[2])

    def test_tache_avec_commit_fusionnee_comme_avant(self):
        self.branche_avec_commit("agent/t9")
        m, e = self.moteur(), SimpleNamespace(serveur=True, branche="agent/t9", tache="t9", agent="a")
        with mock.patch.object(regles, "fusion_impossible") as impossible:
            boucle.Moteur._fusionner(m, SimpleNamespace(dossier=self.d), {}, e)
        impossible.assert_not_called()
        self.assertTrue((self.d / "b.txt").exists())


if __name__ == "__main__":
    unittest.main()
