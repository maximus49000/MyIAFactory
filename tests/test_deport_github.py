"""L'enveloppe de `gh` (outils/github_actions.py) : jamais de vrai `gh` ni de réseau, un faux `lancer` enregistre les appels."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import github_actions as ga  # noqa: E402


class Faux:
    """Rend, dans l'ordre, les réponses (code, sortie, erreur) ou lève l'exception donnée."""

    def __init__(self, *reponses):
        self.reponses = list(reponses)
        self.appels = []

    def __call__(self, argv, **kw):
        self.appels.append((list(argv), kw))
        r = self.reponses.pop(0) if len(self.reponses) > 1 else self.reponses[0]
        if isinstance(r, Exception):
            raise r
        code, sortie, erreur = r
        return subprocess.CompletedProcess(argv, code, sortie, erreur)


def ok(obj=None):
    return (0, json.dumps(obj) if obj is not None else "", "")


def vue(statut, conclusion=None):
    return ok({"status": statut, "conclusion": conclusion, "createdAt": "2026-11-17T10:00:00Z",
               "updatedAt": "2026-11-17T10:05:30Z", "url": "https://github.com/o/d/actions/runs/7"})


class TestGhPret(unittest.TestCase):
    def test_gh_absent(self):
        pret, msg = ga.gh_pret(lancer=Faux(FileNotFoundError()))
        self.assertFalse(pret)
        self.assertIn("gh auth login", msg)

    def test_non_connecte(self):
        pret, msg = ga.gh_pret(lancer=Faux((1, "", "You are not logged in")))
        self.assertFalse(pret)
        self.assertIn("gh auth login", msg)

    def test_pret(self):
        faux = Faux((0, "Logged in", ""))
        pret, _ = ga.gh_pret(lancer=faux)
        self.assertTrue(pret)
        self.assertEqual(faux.appels[0][0][:3], ["gh", "auth", "status"])


class TestVisibilite(unittest.TestCase):
    def test_public_et_prive(self):
        for brut, attendu in (("PUBLIC", "public"), ("PRIVATE", "prive"), ("INTERNAL", "prive")):
            faux = Faux(ok({"visibility": brut}))
            self.assertEqual(ga.visibilite("d", lancer=faux), attendu)
        self.assertEqual(faux.appels[0][0], ["gh", "repo", "view", "--json", "visibility"])
        self.assertEqual(faux.appels[0][1]["cwd"], "d")

    def test_gh_absent_leve(self):
        with self.assertRaises(ga.Gh_indisponible):
            ga.visibilite("d", lancer=Faux(FileNotFoundError()))

    def test_echec_leve(self):
        with self.assertRaises(ga.Gh_indisponible):
            ga.visibilite("d", lancer=Faux((1, "", "boom")))


class TestDeclencher(unittest.TestCase):
    def test_argv(self):
        faux = Faux(ok())
        ga.declencher("d", "ci.yml", "main", {"cible": "apk", "n": 3}, lancer=faux)
        self.assertEqual(faux.appels[0][0], ["gh", "workflow", "run", "ci.yml", "--ref", "main",
                                             "-f", "cible=apk", "-f", "n=3"])

    def test_echec_leve(self):
        with self.assertRaises(ga.Gh_indisponible):
            ga.declencher("d", "ci.yml", "main", {}, lancer=Faux((1, "", "HTTP 404")))


class TestExecutionDuCommit(unittest.TestCase):
    def test_trouve(self):
        faux = Faux(ok([{"databaseId": 7, "status": "completed", "conclusion": "success",
                         "createdAt": "2026-11-17T10:00:00Z", "updatedAt": "2026-11-17T10:05:30Z",
                         "url": "u"}]))
        r = ga.execution_du_commit("d", "ci.yml", "abc", lancer=faux)
        self.assertEqual(r, {"id": 7, "statut": "completed", "conclusion": "success", "duree_s": 330, "url": "u"})
        argv = faux.appels[0][0]
        self.assertIn("--commit", argv)
        self.assertIn("abc", argv)

    def test_absent(self):
        self.assertIsNone(ga.execution_du_commit("d", "ci.yml", "abc", lancer=Faux(ok([]))))


class TestSuivre(unittest.TestCase):
    def test_s_arrete_sur_completed(self):
        faux = Faux(vue("queued"), vue("in_progress"), vue("completed", "success"))
        pauses, lignes = [], []
        r = ga.suivre("d", 7, dormir=pauses.append, dire=lignes.append, lancer=faux)
        self.assertEqual(r["conclusion"], "success")
        self.assertEqual(r["statut"], "completed")
        self.assertEqual(r["id"], 7)
        self.assertEqual(r["duree_s"], 330)
        self.assertEqual(pauses, [60, 60])
        self.assertEqual(len(lignes), 2)

    def test_timeout(self):
        faux = Faux(vue("in_progress"))
        pauses = []
        r = ga.suivre("d", 7, dormir=pauses.append, dire=lambda _: None, delai_s=180, lancer=faux)
        self.assertEqual(r["conclusion"], "timeout")
        self.assertEqual(sum(pauses), 180)


class TestJobs(unittest.TestCase):
    def test_suivre_rend_les_jobs_quand_gh_les_donne(self):
        v = ok({"status": "completed", "conclusion": "failure", "createdAt": "2026-11-17T10:00:00Z",
                "updatedAt": "2026-11-17T10:05:30Z", "url": "u",
                "jobs": [{"name": "apk", "conclusion": "success", "x": 1}, {"name": "lint", "conclusion": "failure"}]})
        faux = Faux(v)
        r = ga.suivre("d", 7, dormir=lambda s: None, dire=lambda _: None, lancer=faux)
        self.assertEqual(r["jobs"], [{"name": "apk", "conclusion": "success"}, {"name": "lint", "conclusion": "failure"}])
        self.assertIn("jobs", faux.appels[0][0][-1])

    def test_jobs_du_run(self):
        faux = Faux(ok({"jobs": [{"name": "apk", "conclusion": "success"}, {"name": "t", "conclusion": ""}]}))
        self.assertEqual(ga.jobs_du_run("d", 7, lancer=faux),
                         [{"name": "apk", "conclusion": "success"}, {"name": "t", "conclusion": None}])
        self.assertEqual(faux.appels[0][0], ["gh", "run", "view", "7", "--json", "jobs"])

    def test_jobs_du_run_rend_les_dates_du_job(self):
        faux = Faux(ok({"jobs": [{"name": "apk", "conclusion": "success", "startedAt": "2026-11-17T10:00:00Z",
                                  "completedAt": "2026-11-17T10:01:10Z"}, {"name": "t", "conclusion": "skipped"}]}))
        self.assertEqual(ga.jobs_du_run("d", 7, lancer=faux),
                         [{"name": "apk", "conclusion": "success", "debut": "2026-11-17T10:00:00Z",
                           "fin": "2026-11-17T10:01:10Z"}, {"name": "t", "conclusion": "skipped"}])


class TestPannes(unittest.TestCase):
    def test_delai_depasse_leve(self):
        faux = Faux(subprocess.TimeoutExpired("gh", 120))
        with self.assertRaises(ga.Gh_indisponible):
            ga.declencher("d", "ci.yml", "main", {}, lancer=faux)
        self.assertEqual(faux.appels[0][1]["timeout"], ga.DELAI_COMMANDE_S)

    def test_trois_echecs_puis_succes(self):
        faux = Faux((1, "", "x"), (1, "", "x"), (1, "", "x"), vue("completed", "success"))
        lignes = []
        r = ga.suivre("d", 7, dormir=lambda s: None, dire=lignes.append, lancer=faux)
        self.assertEqual(r["conclusion"], "success")
        self.assertEqual(len(lignes), 3)
        self.assertTrue(all("gh ne répond pas, nouvel essai" in l for l in lignes))

    def test_compteur_remis_a_zero(self):
        faux = Faux((1, "", "x"), (1, "", "x"), vue("in_progress"), (1, "", "x"), (1, "", "x"), (1, "", "x"),
                    vue("completed", "success"))
        r = ga.suivre("d", 7, dormir=lambda s: None, dire=lambda _: None, lancer=faux)
        self.assertEqual(r["conclusion"], "success")

    def test_quatre_echecs_leve(self):
        with self.assertRaises(ga.Gh_indisponible):
            ga.suivre("d", 7, dormir=lambda s: None, dire=lambda _: None, lancer=Faux((1, "", "x")))

    def test_booleens_en_minuscules(self):
        faux = Faux(ok())
        ga.declencher("d", "ci.yml", "main", {"a": True, "b": False}, lancer=faux)
        self.assertEqual(faux.appels[0][0][-4:], ["-f", "a=true", "-f", "b=false"])


class TestTelecharger(unittest.TestCase):
    def test_rend_le_fichier(self):
        with tempfile.TemporaryDirectory() as t:
            cible = Path(t) / "sortie"

            def lancer(argv, **kw):
                (cible / "apk").mkdir(parents=True)
                (cible / "apk" / "app.apk").write_bytes(b"x")
                self.assertEqual(argv[:6], ["gh", "run", "download", "7", "-n", "apk"])
                self.assertEqual(argv[6:], ["-D", str(cible)])
                return subprocess.CompletedProcess(argv, 0, "", "")

            chemin = ga.telecharger("d", 7, "apk", str(cible), lancer=lancer)
            self.assertEqual(Path(chemin), cible / "apk" / "app.apk")

    def test_echec_leve(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ga.Gh_indisponible):
                ga.telecharger("d", 7, "apk", t, lancer=Faux((1, "", "no artifact")))


class TestConsommation(unittest.TestCase):
    def test_executions_recentes_demande_la_liste_json(self):
        f = Faux(ok([{"databaseId": 1}]))
        self.assertEqual(ga.executions_recentes("d", 50, lancer=f), [{"databaseId": 1}])
        argv = f.appels[0][0]
        self.assertEqual(argv[:5], ["gh", "run", "list", "-L", "50"])
        self.assertIn("databaseId,name,status,conclusion,createdAt,updatedAt,startedAt,headSha,url", argv)

    def test_quota_inconnu_sans_la_portee_user(self):
        f = Faux((0, "moi\n", ""), (1, "", "Not Found: needs the user scope"))
        self.assertIsNone(ga.quota_actions(lancer=f))

    def test_quota_officiel(self):
        f = Faux((0, "moi\n", ""), ok({"total_minutes_used": 640, "included_minutes": 2000}))
        self.assertEqual(ga.quota_actions(lancer=f), (640.0, 2000))
        self.assertEqual(f.appels[1][0], ["gh", "api", "users/moi/settings/billing/actions"])


if __name__ == "__main__":
    unittest.main()
