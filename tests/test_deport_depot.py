import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))

import deport_depot as dd  # noqa: E402
import workflow_github as wf  # noqa: E402

REGLAGES = {"deport": {"lieux": {"apk": "github", "tests": "github", "charge": "poste", "emulateur": "poste"},
                       "commandes": {"apk": "./gradlew assembleDebug", "tests": "python -m unittest"},
                       "charge_heure": "03:00"}}


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


class AvecDepot(unittest.TestCase):
    def setUp(self):
        t = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(t, ignore_errors=True))
        self.origine = Path(t) / "origine.git"
        self.depot = Path(t) / "Mon Projet"
        subprocess.run(["git", "init", "--bare", "-q", str(self.origine)], check=True)
        self.depot.mkdir()
        git(self.depot, "init", "-q", "-b", "main")
        git(self.depot, "config", "user.email", "t@example.org")
        git(self.depot, "config", "user.name", "Test")
        (self.depot / "lisezmoi.txt").write_text("bonjour\n", encoding="utf-8")
        git(self.depot, "add", ".")
        git(self.depot, "commit", "-q", "-m", "départ")
        git(self.depot, "remote", "add", "origin", str(self.origine))
        git(self.depot, "push", "-q", "origin", "main")

    def chemin(self):
        return self.depot / ".github" / "workflows" / "mon-projet.yml"


class TestApercu(AvecDepot):
    def test_projet_sans_fichier_est_absent_avec_le_diff_complet(self):
        a = dd.apercu(str(self.depot), REGLAGES)
        self.assertEqual(a["etat"], "absent")
        voulu = wf.generer("Mon Projet", ["apk", "tests"], REGLAGES["deport"]["commandes"], "03:00")
        self.assertIn("+jobs:", a["diff"])
        self.assertEqual(a["empreinte"], voulu.split("\n", 1)[0].rsplit("=", 1)[1])
        self.assertTrue(a["chemin"].replace("\\", "/").endswith(".github/workflows/mon-projet.yml"))

    def test_sans_action_sur_github_rien_a_proposer(self):
        regl = {"deport": {"lieux": {}, "commandes": {}, "charge_heure": "03:00"}}
        self.assertEqual(dd.apercu(str(self.depot), regl)["etat"], "aucune_action")

    def test_commande_manquante_leve_un_message_clair(self):
        regl = {"deport": {"lieux": {"apk": "github"}, "commandes": {}, "charge_heure": "03:00"}}
        with self.assertRaises(ValueError):
            dd.apercu(str(self.depot), regl)

    def test_nom_de_fichier_sur(self):
        self.assertEqual(dd.nom_fichier("../Évil Projet!!"), "evil-projet")
        self.assertEqual(dd.nom_fichier("///"), "myiafactory")


class TestAppliquer(AvecDepot):
    def appliquer(self, empreinte=None, reglages=None):
        reglages = reglages or REGLAGES
        if empreinte is None:
            empreinte = dd.apercu(str(self.depot), reglages)["empreinte"]
        return dd.appliquer(str(self.depot), empreinte, reglages)

    def test_ecrit_sur_la_branche_de_travail_et_la_pousse_sans_toucher_la_courante(self):
        tete = git(self.depot, "rev-parse", "HEAD")
        r = self.appliquer()
        self.assertTrue(r["ok"], r)
        self.assertEqual(git(self.depot, "rev-parse", "--abbrev-ref", "HEAD"), "main")
        self.assertEqual(git(self.depot, "rev-parse", "HEAD"), tete)
        self.assertEqual(git(self.depot, "status", "--porcelain"), "")
        self.assertFalse(self.chemin().exists())
        contenu = git(self.origine, "show", "deport/workflow:.github/workflows/mon-projet.yml")
        self.assertIn("jobs:", contenu)
        self.assertEqual(git(self.depot, "branch", "--list", "deport/workflow"), "")   # aucune branche locale
        self.assertTrue(git(self.origine, "log", "-1", "--format=%s", "deport/workflow").startswith(dd.MARQUEUR))
        self.assertEqual(git(self.origine, "rev-parse", "main"), tete)   # la principale n'est jamais poussée
        self.assertEqual(git(self.depot, "worktree", "list").count("\n"), 0)   # aucun dossier temporaire laissé

    def test_ne_touche_pas_aux_modifications_non_commitees(self):
        (self.depot / "lisezmoi.txt").write_text("modifié\n", encoding="utf-8")
        (self.depot / "nouveau.txt").write_text("x", encoding="utf-8")
        self.assertTrue(self.appliquer()["ok"])
        self.assertEqual((self.depot / "lisezmoi.txt").read_text(encoding="utf-8"), "modifié\n")
        self.assertTrue((self.depot / "nouveau.txt").exists())

    def test_empreinte_perimee_refusee_sans_rien_ecrire(self):
        r = self.appliquer("0" * 64)
        self.assertFalse(r["ok"])
        self.assertIn("plus à jour", r["message"])
        self.assertEqual(git(self.depot, "branch", "--list", "deport/workflow"), "")
        self.assertNotIn("deport/workflow", git(self.origine, "branch", "--list"))

    def test_fichier_modifie_a_la_main_refuse(self):
        self.chemin().parent.mkdir(parents=True)
        self.chemin().write_text("name: à moi\n", encoding="utf-8")
        git(self.depot, "add", ".")
        git(self.depot, "commit", "-q", "-m", "workflow à la main")
        r = self.appliquer()
        self.assertFalse(r["ok"])
        self.assertIn("main", r["message"])
        self.assertEqual(git(self.depot, "branch", "--list", "deport/workflow"), "")
        self.assertNotIn("deport/workflow", git(self.origine, "branch", "--list"))

    def test_deja_a_jour_ne_pousse_rien(self):
        self.assertTrue(self.appliquer()["ok"])
        git(self.depot, "fetch", "-q", "origin", "deport/workflow")
        git(self.depot, "merge", "-q", "FETCH_HEAD")
        tete = git(self.depot, "rev-parse", "HEAD")
        r = self.appliquer()
        self.assertTrue(r["ok"])
        self.assertEqual(r["etat"], "a_jour")
        self.assertEqual(git(self.depot, "rev-parse", "HEAD"), tete)

    def test_echec_du_push_est_rapporte(self):
        git(self.depot, "remote", "set-url", "origin", str(self.origine) + "-absent")
        r = self.appliquer()
        self.assertFalse(r["ok"])
        self.assertIn("origin", r["message"])
        self.assertEqual(git(self.depot, "worktree", "list").count("\n"), 0)

    def test_modification_non_commitee_refusee_meme_en_post_direct(self):
        a = dd.apercu(str(self.depot), REGLAGES)
        self.chemin().parent.mkdir(parents=True)
        self.chemin().write_text("name: à moi\n", encoding="utf-8")
        r = dd.appliquer(str(self.depot), a["empreinte"], REGLAGES)
        self.assertFalse(r["ok"])
        self.assertIn("main", r["message"])
        self.assertNotIn("deport/workflow", git(self.origine, "branch", "--list"))

    def test_copie_regeneree_non_commitee_refusee(self):
        self.chemin().parent.mkdir(parents=True)
        self.chemin().write_text(wf.generer("Mon Projet", ["apk", "tests"], {"apk": "autre", "tests": "x"}), encoding="utf-8")
        r = self.appliquer()
        self.assertFalse(r["ok"])
        self.assertIn("non commitée", r["message"])

    def pousser_etrangere(self):
        git(self.depot, "checkout", "-q", "-b", "ailleurs")
        (self.depot / "autre.txt").write_text("a", encoding="utf-8")
        git(self.depot, "add", ".")
        git(self.depot, "commit", "-q", "-m", "travail de quelqu'un d'autre")
        git(self.depot, "push", "-q", "origin", "ailleurs:deport/workflow")
        git(self.depot, "checkout", "-q", "main")
        return git(self.origine, "rev-parse", "deport/workflow")

    def test_branche_distante_etrangere_refusee(self):
        avant = self.pousser_etrangere()
        r = self.appliquer()
        self.assertFalse(r["ok"])
        self.assertIn("pas été créée par MyIAFactory", r["message"])
        self.assertEqual(git(self.origine, "rev-parse", "deport/workflow"), avant)

    def test_branche_distante_a_nous_poussee_avec_lease(self):
        self.assertTrue(self.appliquer()["ok"])
        premier = git(self.origine, "rev-parse", "deport/workflow")
        vus = []

        def executer(argv, cwd, delai):
            vus.append(list(argv))
            return dd._executer(argv, cwd, delai)
        regl = {"deport": {**REGLAGES["deport"], "commandes": {"apk": "./autre", "tests": "x"}}}
        e = dd.apercu(str(self.depot), regl)["empreinte"]
        self.assertTrue(dd.appliquer(str(self.depot), e, regl, executer=executer)["ok"])
        pousse = [v for v in vus if v[:2] == ["git", "push"]][0]
        self.assertIn("--force-with-lease=refs/heads/deport/workflow:" + premier, pousse)
        self.assertNotIn("--force", pousse)
        self.assertNotEqual(git(self.origine, "rev-parse", "deport/workflow"), premier)
        self.assertEqual(git(self.depot, "branch", "--list", "deport/workflow"), "")

    def test_identifiants_retires_des_messages(self):
        git(self.depot, "remote", "set-url", "origin", "https://user:secret@127.0.0.1:1/x.git")
        r = self.appliquer()
        self.assertFalse(r["ok"])
        self.assertNotIn("secret", r["message"])

    def test_aucun_push_de_la_branche_principale(self):
        vus = []

        def executer(argv, cwd, delai):
            vus.append(list(argv))
            return dd._executer(argv, cwd, delai)
        empreinte = dd.apercu(str(self.depot), REGLAGES)["empreinte"]
        self.assertTrue(dd.appliquer(str(self.depot), empreinte, REGLAGES, executer=executer)["ok"])
        pousses = [v for v in vus if v[:2] == ["git", "push"]]
        self.assertEqual(len(pousses), 1)
        self.assertNotIn("main", " ".join(pousses[0]))
        self.assertIn("deport/workflow", " ".join(pousses[0]))


if __name__ == "__main__":
    unittest.main()
