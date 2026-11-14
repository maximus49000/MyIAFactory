"""Git sans collision : un verrou par dépôt, l'index pris par un autre git réessayé, un verrou abandonné retiré."""
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from moteur import git_sur


class GitSur(unittest.TestCase):
    def test_un_index_pris_est_reessaye(self):
        appels = []

        def lancer(argv):
            appels.append(argv)
            if len(appels) < 3:
                return 128, b"fatal: Unable to create 'C:/p/.git/index.lock': File exists."
            return 0, b""
        self.assertEqual(git_sur.executer(lancer, tempfile.mkdtemp(), ["git", "merge"], pause=0)[0], 0)
        self.assertEqual(len(appels), 3)

    def test_une_autre_erreur_n_est_pas_reessayee(self):
        appels = []
        git_sur.executer(lambda a: (appels.append(a), (1, b"CONFLICT"))[1], tempfile.mkdtemp(), ["git", "merge"], pause=0)
        self.assertEqual(len(appels), 1)

    def test_un_verrou_abandonne_est_retire_un_recent_garde(self):
        d = Path(tempfile.mkdtemp())
        (d / ".git").mkdir()
        lock = d / ".git" / "index.lock"
        lock.write_text("")
        self.assertFalse(git_sur.retirer_si_abandonne(d))
        vieux = time.time() - git_sur.VERROU_ABANDONNE_S - 5
        os.utime(lock, (vieux, vieux))
        self.assertTrue(git_sur.retirer_si_abandonne(d))
        self.assertFalse(lock.exists())

    def test_les_operations_d_un_meme_depot_passent_une_a_une(self):
        d = tempfile.mkdtemp()
        dedans, maxi = [0], [0]

        def lancer(argv):
            dedans[0] += 1
            maxi[0] = max(maxi[0], dedans[0])
            time.sleep(0.02)
            dedans[0] -= 1
            return 0, b""
        fils = [threading.Thread(target=git_sur.executer, args=(lancer, d, ["git", "x"])) for _ in range(6)]
        for f in fils:
            f.start()
        for f in fils:
            f.join()
        self.assertEqual(maxi[0], 1)

    def test_meme_verrou_pour_le_meme_dossier(self):
        d = tempfile.mkdtemp()
        self.assertIs(git_sur.verrou(d), git_sur.verrou(d + os.sep))
