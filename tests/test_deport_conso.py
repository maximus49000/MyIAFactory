"""Consommation GitHub du déport : cumul des minutes par job, état du quota, cache de 5 minutes, rafraîchissement en
arrière-plan. Jamais de vrai `gh` ni du vrai dossier `~/MyIAFactory` : un faux `lancer`, un dossier temporaire et une
horloge injectée."""
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))

from bureau import deport_conso as dc  # noqa: E402

MOIS = "2026-11"


def job(nom, debut, fin):
    return {"name": nom, "conclusion": "success", "debut": debut, "fin": fin}


def run(debut, fin, statut="completed", conclusion="success", nom="MyIAFactory", jobs=None, id_=1, projet="p"):
    r = {"databaseId": id_, "name": nom, "status": statut, "conclusion": conclusion, "createdAt": debut,
         "startedAt": debut, "updatedAt": fin, "url": "https://github.com/o/d/actions/runs/%d" % id_, "projet": projet}
    if jobs is not None:
        r["jobs"] = jobs
    return r


class TestEtatQuota(unittest.TestCase):
    def test_79_pour_cent_ok(self):
        q = dc.etat_quota(1580, 2000, False)
        self.assertEqual((q["niveau"], q["restantes"]), ("ok", 420))

    def test_80_pour_cent_alerte(self):
        q = dc.etat_quota(1600, 2000, False)
        self.assertEqual((q["niveau"], q["restantes"]), ("alerte", 400))

    def test_100_pour_cent_depasse_propose_le_poste(self):
        q = dc.etat_quota(2000, 2000, False)
        self.assertEqual((q["niveau"], q["restantes"]), ("depasse", 0))
        self.assertIn("passer au poste, avec votre accord", q["texte"])

    def test_public_illimite(self):
        q = dc.etat_quota(99999, None, True)
        self.assertEqual((q["niveau"], q["restantes"]), ("ok", None))
        self.assertIn("illimit", q["texte"])

    def test_quota_inconnu_dit_l_estimation(self):
        q = dc.etat_quota(640, None, False)
        self.assertEqual((q["niveau"], q["restantes"]), ("ok", None))
        self.assertIn("estimation par les durées ; `gh auth refresh -h github.com -s user` pour le quota officiel",
                      q["texte"])

    def test_texte_chiffre(self):
        self.assertIn("640 / 2 000 min", dc.etat_quota(640, 2000, False)["texte"])


class TestCumuler(unittest.TestCase):
    def test_deux_executions_de_4_min_10_comptent_5_chacune(self):
        ex = [run("2026-11-10T10:00:00Z", "2026-11-10T10:04:10Z", id_=1),
              run("2026-11-11T10:00:00Z", "2026-11-11T10:04:10Z", id_=2)]
        self.assertEqual(dc.cumuler(ex, MOIS), {"p": {"MyIAFactory": {"minutes": 10.0, "executions": 2}}})

    def test_un_autre_mois_n_est_pas_cumule(self):
        ex = [run("2026-10-31T10:00:00Z", "2026-10-31T10:03:00Z")]
        self.assertEqual(dc.cumuler(ex, MOIS), {})

    def test_une_execution_non_terminee_est_ignoree(self):
        ex = [run("2026-11-10T10:00:00Z", "2026-11-10T10:03:00Z", statut="in_progress", conclusion=None)]
        self.assertEqual(dc.cumuler(ex, MOIS), {})

    def test_trois_jobs_paralleles_de_1_min_10_font_6_minutes(self):
        t = ("2026-11-10T10:00:00Z", "2026-11-10T10:01:10Z")
        ex = [run(t[0], t[1], jobs=[job("apk", *t), job("tests", *t), job("lint", *t)])]
        c = dc.cumuler(ex, MOIS)["p"]
        self.assertEqual(c, {a: {"minutes": 2.0, "executions": 1} for a in ("apk", "tests", "lint")})
        self.assertEqual(sum(x["minutes"] for x in c.values()), 6.0)

    def test_le_ceil_est_par_job_et_l_action_est_le_nom_du_job(self):
        ex = [run("2026-11-10T10:00:00Z", "2026-11-10T10:05:00Z",
                  jobs=[job("apk", "2026-11-10T10:00:00Z", "2026-11-10T10:04:10Z"),
                        job("tests", "2026-11-10T10:00:00Z", "2026-11-10T10:00:20Z")])]
        self.assertEqual(dc.cumuler(ex, MOIS)["p"], {"apk": {"minutes": 5.0, "executions": 1},
                                                      "tests": {"minutes": 1.0, "executions": 1}})

    def test_un_job_ignore_sans_dates_ne_compte_pas(self):
        ex = [run("2026-11-10T10:00:00Z", "2026-11-10T10:05:00Z",
                  jobs=[job("apk", "2026-11-10T10:00:00Z", "2026-11-10T10:02:00Z"),
                        {"name": "lint", "conclusion": "skipped"}])]
        self.assertEqual(dc.cumuler(ex, MOIS)["p"], {"apk": {"minutes": 2.0, "executions": 1}})

    def test_sans_jobs_repli_sur_la_duree_du_run_nommee_par_le_run(self):
        ex = [run("2026-11-10T10:00:00Z", "2026-11-10T10:01:00Z", nom="tests")]
        self.assertEqual(dc.cumuler(ex, MOIS)["p"], {"tests": {"minutes": 1.0, "executions": 1}})


class Faux:
    """Faux `gh` : route selon la commande ; enregistre les appels ; peut bloquer (événement) ou tomber en panne."""

    def __init__(self, runs=None, visibilite="PRIVATE", panne=False, facturation=None, bloque=None, jobs="un"):
        self.runs, self.vis, self.panne, self.facturation = runs or [], visibilite, panne, facturation
        self.bloque, self.jobs = bloque, jobs
        self.appels = []

    def __call__(self, argv, **kw):
        self.appels.append(list(argv))
        if self.bloque is not None:
            self.bloque.wait(10)
        if self.panne:
            raise FileNotFoundError("gh")
        sortie, code = "", 0
        t = ("2026-11-10T10:00:00Z", "2026-11-10T10:04:10Z")
        if argv[1:3] == ["run", "list"]:
            sortie = json.dumps(self.runs)
        elif argv[1:3] == ["run", "view"]:
            if self.jobs == "aucun":
                liste = []
            elif self.jobs == "deux":
                u = ("2026-11-10T10:00:00Z", "2026-11-10T10:01:00Z")
                liste = [{"name": "apk", "conclusion": "success", "startedAt": u[0], "completedAt": u[1]},
                         {"name": "tests", "conclusion": "failure", "startedAt": u[0], "completedAt": u[1]}]
            else:
                liste = [{"name": "apk", "conclusion": "success", "startedAt": t[0], "completedAt": t[1]}]
            sortie = json.dumps({"jobs": liste})
        elif argv[1:3] == ["repo", "view"]:
            sortie = json.dumps({"visibility": self.vis})
        elif argv[1] == "api" and argv[2] == "user":
            sortie = "moi\n"
        elif argv[1] == "api":
            if self.facturation is None:
                code, sortie = 1, "Not Found (needs the user scope)"
            else:
                sortie = json.dumps(self.facturation)
        return subprocess.CompletedProcess(argv, code, sortie, "")

    def lectures_de_runs(self):
        return [a for a in self.appels if a[1:3] == ["run", "list"]]


def brut(debut, fin, id_=1):
    return {"databaseId": id_, "name": "MyIAFactory", "status": "completed", "conclusion": "success",
            "createdAt": debut, "startedAt": debut, "updatedAt": fin, "headSha": "abc",
            "url": "https://github.com/o/d/actions/runs/%d" % id_}


BRUT = brut("2026-11-10T10:00:00Z", "2026-11-10T10:04:10Z")


class TestCoquille(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._t.cleanup)
        self.addCleanup(dc.arreter)   # aucun fil de rafraîchissement ne survit au test
        self.cache = Path(self._t.name)
        self.t = [1794823200.0]   # 2026-11-17 10:00 UTC

    def horloge(self):
        return self.t[0]

    def appeler(self, faux, lieux=None):
        return dc.conso("depot", {"apk": "Générer l'APK"}, lieux or {"apk": "github", "tests": "poste"},
                        maintenant=self.horloge, lancer=faux, cache=self.cache)

    def lire(self, faux, lieux=None):
        """Un appel, on attend le rafraîchissement en arrière-plan qu'il a lancé, puis la valeur à jour."""
        self.appeler(faux, lieux)
        dc.attendre()
        return self.appeler(faux, lieux)

    def test_sans_action_github_ni_conso_ni_appel(self):
        faux = Faux()
        self.assertIsNone(self.appeler(faux, {"apk": "poste"}))
        dc.attendre()
        self.assertEqual(faux.appels, [])
        self.assertFalse((self.cache / "deport-conso.json").exists())

    def test_conso_complete(self):
        faux = Faux([BRUT], facturation={"total_minutes_used": 640, "included_minutes": 2000})
        c = self.lire(faux)
        self.assertEqual((c["niveau"], c["mois"], c["quota"], c["minutes_total"]), ("ok", "2026-11", 2000, 640))
        self.assertEqual(c["par_action"], [{"action": "apk", "libelle": "Générer l'APK", "minutes": 5.0,
                                            "executions": 1}])
        self.assertEqual(c["derniers"][0]["action"], "apk")
        self.assertEqual((c["derniers"][0]["conclusion"], c["derniers"][0]["duree_s"]), ("success", 250))
        self.assertTrue(c["derniers"][0]["url"].startswith("https://"))

    def test_derniers_une_ligne_par_job(self):
        c = self.lire(Faux([BRUT], jobs="deux"))
        self.assertEqual([(d["action"], d["conclusion"], d["duree_s"]) for d in c["derniers"]],
                         [("apk", "success", 60), ("tests", "failure", 60)])

    def test_quota_inconnu_estimation_par_les_durees(self):
        c = self.lire(Faux([BRUT]))
        self.assertIsNone(c["quota"])
        self.assertEqual(c["minutes_total"], 5.0)
        self.assertIn("gh auth refresh -h github.com -s user", c["texte"])

    def test_sans_detail_des_jobs_estimation_basse(self):
        c = self.lire(Faux([BRUT], jobs="aucun"))
        self.assertEqual(c["par_action"][0]["action"], "MyIAFactory")
        self.assertIn("estimation basse", c["texte"])

    def test_depot_public(self):
        c = self.lire(Faux([], visibilite="PUBLIC"))
        self.assertIs(c["public"], True)
        self.assertIn("illimit", c["texte"])

    def test_gh_bloque_conso_repond_tout_de_suite(self):
        porte = threading.Event()
        self.addCleanup(porte.set)
        faux = Faux([BRUT], bloque=porte)
        c = self.appeler(faux)
        self.assertIn("lecture", c["texte"])
        self.assertEqual(c["par_action"], [])
        porte.set()
        dc.attendre()
        self.assertEqual(self.appeler(faux)["par_action"][0]["action"], "apk")

    def test_deux_appels_rapproches_un_seul_rafraichissement(self):
        porte = threading.Event()
        self.addCleanup(porte.set)
        faux = Faux([BRUT], bloque=porte)
        self.appeler(faux)
        self.appeler(faux)
        porte.set()
        dc.attendre()
        self.assertEqual(len(faux.lectures_de_runs()), 1)

    def test_cache_reutilise_moins_de_5_minutes_puis_rafraichi(self):
        faux = Faux([BRUT])
        self.lire(faux)
        self.t[0] += 299
        self.lire(faux)
        self.assertEqual(len(faux.lectures_de_runs()), 1)
        self.t[0] += 2
        self.lire(faux)
        self.assertEqual(len(faux.lectures_de_runs()), 2)

    def test_panne_de_gh_rend_la_derniere_valeur(self):
        faux = Faux([BRUT])
        avant = self.lire(faux)
        faux.panne = True
        self.t[0] += 400
        apres = self.lire(faux)
        self.assertEqual(apres["par_action"], avant["par_action"])
        self.assertIn("conservée", apres["texte"])

    def test_panne_sans_cache_indisponible_sans_exception(self):
        c = self.lire(Faux(panne=True))
        self.assertIn("indisponible", c["texte"])
        self.assertEqual(c["par_action"], [])

    def test_un_echec_n_est_pas_relance_avant_5_minutes(self):
        faux = Faux(panne=True)
        self.lire(faux)
        n = len(faux.appels)
        self.t[0] += 299
        self.lire(faux)
        self.assertEqual(len(faux.appels), n)
        self.t[0] += 2
        self.lire(faux)
        self.assertGreater(len(faux.appels), n)

    def test_cache_ecrit_dans_le_dossier_injecte(self):
        self.lire(Faux([BRUT]))
        donnees = json.loads((self.cache / "deport-conso.json").read_text(encoding="utf-8"))
        self.assertIn("depot", donnees["depots"])


if __name__ == "__main__":
    unittest.main()


class TestNiveauEnCache(unittest.TestCase):
    """Pour `deporter` (code 8) : le niveau lu dans le cache, sans gh."""

    def test_niveau(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertIsNone(dc.niveau_en_cache(["/p"], cache=t))
            (Path(t) / dc.NOM_CACHE).write_text(json.dumps({"depots": {"/p/.factory": {
                "lu_a": 1, "public": False, "quota": {"utilisees": 2500, "incluses": 2000}, "executions": []}}}),
                encoding="utf-8")
            self.assertEqual(dc.niveau_en_cache(["/p", "/p/.factory"], cache=t), "depasse")
            self.assertIsNone(dc.niveau_en_cache(["/autre"], cache=t))
            (Path(t) / dc.NOM_CACHE).write_text("{abîmé", encoding="utf-8")
            self.assertIsNone(dc.niveau_en_cache(["/p"], cache=t))
