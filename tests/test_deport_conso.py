"""Consommation GitHub du déport : cumul des minutes, état du quota, cache de 5 minutes. Jamais de vrai `gh` ni du vrai
dossier `~/MyIAFactory` : un faux `lancer`, un dossier temporaire et une horloge injectée."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))

from bureau import deport_conso as dc  # noqa: E402

MOIS = "2026-11"


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

    def test_l_action_vient_des_jobs(self):
        ex = [run("2026-11-10T10:00:00Z", "2026-11-10T10:04:00Z", jobs=["apk", "tests"])]
        c = dc.cumuler(ex, MOIS)["p"]
        self.assertEqual(c, {"apk": {"minutes": 2.0, "executions": 1}, "tests": {"minutes": 2.0, "executions": 1}})

    def test_sans_jobs_l_action_est_le_nom_du_run(self):
        ex = [run("2026-11-10T10:00:00Z", "2026-11-10T10:01:00Z", nom="tests")]
        self.assertIn("tests", dc.cumuler(ex, MOIS)["p"])


class Faux:
    """Faux `gh` : route selon la commande ; enregistre les appels."""

    def __init__(self, runs=None, visibilite="PRIVATE", panne=False, facturation=None):
        self.runs, self.vis, self.panne, self.facturation = runs or [], visibilite, panne, facturation
        self.appels = []

    def __call__(self, argv, **kw):
        self.appels.append(list(argv))
        if self.panne:
            raise FileNotFoundError("gh")
        sortie, code = "", 0
        if argv[1:3] == ["run", "list"]:
            sortie = json.dumps(self.runs)
        elif argv[1:3] == ["run", "view"]:
            sortie = json.dumps({"jobs": [{"name": "apk", "conclusion": "success"}]})
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


class TestCoquille(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._t.cleanup)
        self.cache = Path(self._t.name)
        self.t = [1794823200.0]   # 2026-11-17 10:00 UTC

    def horloge(self):
        return self.t[0]

    def lire(self, faux, lieux=None):
        return dc.conso("depot", {"apk": "Générer l'APK"}, lieux or {"apk": "github", "tests": "poste"},
                        maintenant=self.horloge, lancer=faux, cache=self.cache)

    def test_sans_action_github_ni_conso_ni_appel(self):
        faux = Faux()
        self.assertIsNone(self.lire(faux, {"apk": "poste"}))
        self.assertEqual(faux.appels, [])
        self.assertFalse((self.cache / "deport-conso.json").exists())

    def test_conso_complete(self):
        faux = Faux([brut("2026-11-10T10:00:00Z", "2026-11-10T10:04:10Z")], facturation={
            "total_minutes_used": 640, "included_minutes": 2000})
        c = self.lire(faux)
        self.assertEqual((c["niveau"], c["mois"], c["quota"], c["minutes_total"]), ("ok", "2026-11", 2000, 640))
        self.assertEqual(c["par_action"], [{"action": "apk", "libelle": "Générer l'APK", "minutes": 5.0,
                                            "executions": 1}])
        self.assertEqual(c["derniers"][0]["action"], "apk")
        self.assertEqual((c["derniers"][0]["conclusion"], c["derniers"][0]["duree_s"]), ("success", 250))
        self.assertTrue(c["derniers"][0]["url"].startswith("https://"))

    def test_quota_inconnu_estimation_par_les_durees(self):
        c = self.lire(Faux([brut("2026-11-10T10:00:00Z", "2026-11-10T10:04:10Z")]))
        self.assertIsNone(c["quota"])
        self.assertEqual(c["minutes_total"], 5.0)
        self.assertIn("gh auth refresh -h github.com -s user", c["texte"])

    def test_depot_public(self):
        c = self.lire(Faux([], visibilite="PUBLIC"))
        self.assertIs(c["public"], True)
        self.assertIn("illimit", c["texte"])

    def test_cache_reutilise_moins_de_5_minutes_puis_rafraichi(self):
        faux = Faux([brut("2026-11-10T10:00:00Z", "2026-11-10T10:04:10Z")])
        self.lire(faux)
        self.t[0] += 299
        self.lire(faux)
        self.assertEqual(len(faux.lectures_de_runs()), 1)
        self.t[0] += 2
        self.lire(faux)
        self.assertEqual(len(faux.lectures_de_runs()), 2)

    def test_panne_de_gh_rend_la_derniere_valeur(self):
        faux = Faux([brut("2026-11-10T10:00:00Z", "2026-11-10T10:04:10Z")])
        avant = self.lire(faux)
        faux.panne = True
        self.t[0] += 400
        apres = self.lire(faux)
        self.assertEqual(apres["par_action"], avant["par_action"])

    def test_panne_sans_cache_indisponible_sans_exception(self):
        c = self.lire(Faux(panne=True))
        self.assertIn("indisponible", c["texte"])
        self.assertEqual(c["par_action"], [])

    def test_cache_ecrit_dans_le_dossier_injecte(self):
        self.lire(Faux([brut("2026-11-10T10:00:00Z", "2026-11-10T10:04:10Z")]))
        donnees = json.loads((self.cache / "deport-conso.json").read_text(encoding="utf-8"))
        self.assertIn("depot", donnees["depots"])


if __name__ == "__main__":
    unittest.main()
