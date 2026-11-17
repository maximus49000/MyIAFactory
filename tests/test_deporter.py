"""`lancer.py deporter` (outils/deporter.py) : faux `gh`, faux lanceur local, dépôts git temporaires avec un origin nu.
Jamais de réseau, jamais de vrai `gh`, jamais de push du vrai dépôt."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import deporter  # noqa: E402
import github_actions  # noqa: E402


def git(cwd, *argv):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git"] + list(argv), cwd=str(cwd), check=True, capture_output=True, text=True,
                          env=env).stdout.strip()


class FauxGh:
    Gh_indisponible = github_actions.Gh_indisponible

    def __init__(self, pret=True, run=None, apres=None, conclusion="success", erreur=None):
        self.pret, self.run, self.apres, self.conclusion, self.erreur = pret, run, apres, conclusion, erreur
        self.appels = []

    def gh_pret(self):
        self.appels.append("gh_pret")
        return self.pret, "gh n'est pas connecté : lancez `gh auth login`."

    def execution_du_commit(self, depot, workflow, commit):
        self.appels.append(("execution_du_commit", workflow, commit))
        if self.erreur:
            raise self.erreur
        return self.run

    def declencher(self, depot, workflow, ref, entrees):
        self.appels.append(("declencher", workflow, ref))
        self.run = {"id": 42, "statut": "queued", "conclusion": None, "duree_s": 0, "url": "http://run/42"}

    def suivre(self, depot, run_id, dormir=None, dire=print, **k):
        self.appels.append(("suivre", run_id))
        dormir(60)
        self.run = dict(self.run, statut="completed", conclusion=self.conclusion)
        return self.run

    def telecharger(self, depot, run_id, nom, dossier):
        self.appels.append(("telecharger", run_id, nom, dossier))
        return dossier


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name).resolve()
        self.bureau = self.tmp / "bureau.json"
        self.attente = self.tmp / "deport-en-cours"
        self.poste = []
        self.dits = []

    def executer_poste(self, commande, dossier=None, attendre=True):
        self.poste.append((list(commande), dossier, attendre))
        return 0

    def projet(self, lieux=None, genre=None, pousse=True, workflow=True):
        """Un dépôt `monprojet` avec son origin nu ; le workflow est commité (et poussé si `pousse`)."""
        origin = self.tmp / "origin.git"
        if not origin.exists():
            subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
        d = self.tmp / "monprojet"
        d.mkdir(exist_ok=True)
        git(d, "init", "-b", "main")
        git(d, "remote", "add", "origin", str(origin))
        (d / ".factory").mkdir(exist_ok=True)
        if lieux is not None:
            (d / ".factory" / "reglages.json").write_text(json.dumps({"deport": {"lieux": lieux}}), encoding="utf-8")
        if genre:
            (d / ".factory" / "factory.json").write_text(json.dumps({"genre": genre}), encoding="utf-8")
        if workflow:
            (d / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
            (d / ".github" / "workflows" / "monprojet.yml").write_text("name: x\n", encoding="utf-8")
        git(d, "add", "-A")
        git(d, "commit", "-m", "premier")
        if pousse:
            git(d, "push", "origin", "main")
        return d

    def lancer(self, argv, gh=None, **k):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(sortie):
            code = deporter.main(argv, executer_poste=self.executer_poste, gh=gh or FauxGh(),
                                 dormir=lambda s: None, bureau=self.bureau, repertoire_attente=self.attente, **k)
        self.sortie = sortie.getvalue()
        return code


class TestPoste(Base):
    def test_lieu_poste_par_defaut_la_commande_part_par_campagne(self):
        d = self.projet()
        gh = FauxGh()
        code = self.lancer(["tests", "--dossier", str(d), "--", "echo", "ok"], gh=gh)
        self.assertEqual(code, 0)
        self.assertEqual(self.poste, [(["echo", "ok"], str(d), True)])
        self.assertEqual(gh.appels, [])

    def test_poste_force_meme_si_le_lieu_est_github(self):
        d = self.projet({"tests": "github"}, genre="application-mobile-android")
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--poste", "--", "x"], gh=gh), 0)
        self.assertEqual(len(self.poste), 1)
        self.assertEqual(gh.appels, [])

    def test_sans_attendre_est_transmis_et_le_refus_de_campagne_est_rendu(self):
        d = self.projet()
        self.executer_poste = lambda c, dossier=None, attendre=True: (self.poste.append(attendre) or 3)
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--sans-attendre", "--", "x"]), 3)
        self.assertEqual(self.poste, [False])

    def test_usage(self):
        self.assertEqual(self.lancer([]), 2)
        d = self.projet()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)]), 2)         # pas de commande locale
        self.assertEqual(self.lancer(["inconnue", "--dossier", str(d), "--", "x"]), 2)
        self.assertEqual(self.lancer(["tests", "--zut"]), 2)

    def test_le_defaut_global_du_bureau_s_applique_et_le_projet_le_surcharge(self):
        self.bureau.write_text(json.dumps({"deport": {"lieux": {"tests": "github"}}}), encoding="utf-8")
        d = self.projet()
        self.assertEqual(deporter.lieu_de("tests", ["--dossier", str(d)], bureau=self.bureau), "github")
        (d / ".factory" / "reglages.json").write_text(json.dumps({"deport": {"lieux": {"tests": "poste"}}}),
                                                      encoding="utf-8")
        self.assertEqual(deporter.lieu_de("tests", ["--dossier", str(d)], bureau=self.bureau), "poste")

    def test_reglages_donnes_en_option(self):
        d = self.projet()
        r = self.tmp / "autre.json"
        r.write_text(json.dumps({"deport": {"lieux": {"tests": "github"}}}), encoding="utf-8")
        self.assertEqual(deporter.lieu_de("tests", ["--dossier", str(d), "--reglages", str(r)], bureau=self.bureau),
                         "github")


class TestGithub(Base):
    ANDROID = "application-mobile-android"

    def projet_gh(self, **k):
        return self.projet({"tests": "github"}, genre=self.ANDROID, **k)

    def test_declenche_suit_et_rend_0(self):
        d = self.projet_gh()
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 0)
        noms = [a[0] if isinstance(a, tuple) else a for a in gh.appels]
        self.assertEqual(noms, ["gh_pret", "execution_du_commit", "declencher", "execution_du_commit", "suivre"])
        self.assertIn(("declencher", "monprojet.yml", "main"), gh.appels)
        self.assertEqual(self.poste, [])

    def test_exécution_echouee_rend_1(self):
        d = self.projet_gh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=FauxGh(conclusion="failure")), 1)

    def test_gh_indisponible_code_4_avec_le_message(self):
        d = self.projet_gh()
        gh = FauxGh(pret=False)
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 4)
        self.assertIn("gh auth login", self.sortie)
        self.assertIn("relance avec --poste après accord du Directeur", self.sortie)
        self.assertEqual(self.poste, [])

    def test_reseau_absent_code_4_jamais_de_bascule_silencieuse(self):
        d = self.projet_gh()
        gh = FauxGh(erreur=github_actions.Gh_indisponible("pas de réseau"))
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 4)
        self.assertIn("relance avec --poste après accord du Directeur", self.sortie)
        self.assertEqual(self.poste, [])

    def test_travail_non_pousse_code_6_et_rien_n_est_pousse(self):
        d = self.projet_gh(pousse=False)
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 6)
        self.assertIn("pousse d'abord ton travail", self.sortie)
        self.assertNotIn("declencher", [a[0] for a in gh.appels if isinstance(a, tuple)])
        self.assertEqual(git(self.tmp / "origin.git", "branch", "--list"), "")      # rien n'est parti

    def test_commit_local_apres_le_push_est_refuse(self):
        d = self.projet_gh()
        (d / "f.txt").write_text("x", encoding="utf-8")
        git(d, "add", "-A")
        git(d, "commit", "-m", "local")
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)]), 6)

    def test_workflow_absent_de_la_branche_code_7(self):
        d = self.projet_gh(workflow=False)
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 7)
        self.assertIn("fusionne deport/workflow", self.sortie)
        self.assertNotIn("declencher", [a[0] for a in gh.appels if isinstance(a, tuple)])

    def test_sans_attendre_refuse_code_3_sans_declencher(self):
        d = self.projet_gh()
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--sans-attendre"], gh=gh), 3)
        self.assertNotIn("declencher", [a[0] for a in gh.appels if isinstance(a, tuple)])

    def test_une_execution_finie_n_attend_pas_meme_sans_attendre(self):
        d = self.projet_gh()
        gh = FauxGh(run={"id": 5, "statut": "completed", "conclusion": "success", "duree_s": 1, "url": "u"})
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--sans-attendre"], gh=gh), 0)

    def test_deux_appelants_pour_le_meme_commit_une_seule_execution(self):
        d = self.projet_gh()
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 0)
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 0)      # l'exécution existe : réutilisée
        declenchements = [a for a in gh.appels if isinstance(a, tuple) and a[0] == "declencher"]
        self.assertEqual(len(declenchements), 1)

    def test_une_execution_en_cours_d_un_autre_appelant_est_suivie_sans_declencher(self):
        d = self.projet_gh()
        gh = FauxGh(run={"id": 9, "statut": "in_progress", "conclusion": None, "duree_s": 0, "url": "u"})
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 0)
        self.assertIn(("suivre", 9), gh.appels)
        self.assertFalse([a for a in gh.appels if isinstance(a, tuple) and a[0] == "declencher"])


class TestDependances(Base):
    def projet_apk(self, **k):
        return self.projet({"apk": "github"}, **k)      # générique : les tests (au poste) consomment l'apk

    def test_attend_l_apk_telecharge_l_artefact_puis_lance_les_tests(self):
        d = self.projet_apk()
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "echo", "t"], gh=gh), 0)
        telechargements = [a for a in gh.appels if isinstance(a, tuple) and a[0] == "telecharger"]
        self.assertEqual(len(telechargements), 1)
        self.assertEqual(telechargements[0][2], "apk")
        self.assertEqual(self.poste, [(["echo", "t"], str(d), True)])
        noms = [a[0] if isinstance(a, tuple) else a for a in gh.appels]
        self.assertLess(noms.index("suivre"), noms.index("telecharger"))

    def test_apk_echoue_code_5_sans_lancer_les_tests(self):
        d = self.projet_apk()
        gh = FauxGh(conclusion="failure")
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "echo", "t"], gh=gh), 5)
        self.assertEqual(self.poste, [])
        self.assertFalse([a for a in gh.appels if isinstance(a, tuple) and a[0] == "telecharger"])

    def test_dependance_gh_indisponible_code_4(self):
        d = self.projet_apk()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "x"], gh=FauxGh(pret=False)), 4)
        self.assertEqual(self.poste, [])

    def test_sans_dependance_github_les_tests_partent_directement(self):
        d = self.projet({"apk": "poste"})
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "x"], gh=gh), 0)
        self.assertEqual(gh.appels, [])

    def test_android_les_tests_ne_consomment_pas_l_apk(self):
        d = self.projet({"apk": "github"}, genre="application-mobile-android")
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "x"], gh=gh), 0)
        self.assertEqual(gh.appels, [])
        self.assertEqual(len(self.poste), 1)


class TestFichierAttente(Base):
    def test_ecrire_battre_retirer(self):
        deporter.ecrire_attente("a-1", "tests", "apk", "github", dossier="/x", repertoire=self.attente)
        f = self.attente / "a-1.json"
        v = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual({k: v[k] for k in ("action", "attend", "lieu", "dossier")},
                         {"action": "tests", "attend": "apk", "lieu": "github", "dossier": "/x"})
        self.assertTrue(v["depuis"] and v["battement"])
        v["battement"] = "ancien"
        f.write_text(json.dumps(v), encoding="utf-8")
        deporter.battre("a-1", repertoire=self.attente)
        self.assertNotEqual(json.loads(f.read_text(encoding="utf-8"))["battement"], "ancien")
        deporter.retirer_attente("a-1", repertoire=self.attente)
        self.assertFalse(f.exists())
        deporter.retirer_attente("a-1", repertoire=self.attente)      # absent : sans erreur

    def test_le_fichier_existe_pendant_l_attente_avec_le_dossier_de_l_agent_puis_disparait(self):
        d = self.projet({"apk": "github"})
        vus = []
        gh = FauxGh()
        suivre = gh.suivre

        def suivre_qui_regarde(depot, run_id, dormir=None, dire=print, **k):
            vus.extend(json.loads(p.read_text(encoding="utf-8")) for p in self.attente.glob("*.json"))
            r = suivre(depot, run_id, dormir=dormir, dire=dire)
            vus.extend(json.loads(p.read_text(encoding="utf-8")) for p in self.attente.glob("*.json"))
            return r
        gh.suivre = suivre_qui_regarde
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "x"], gh=gh), 0)
        self.assertEqual(len(vus), 2)
        self.assertEqual((vus[0]["action"], vus[0]["attend"], vus[0]["lieu"]), ("tests", "apk", "github"))
        self.assertEqual(vus[0]["dossier"], str(d))
        self.assertTrue(vus[1]["battement"] >= vus[0]["battement"])      # rafraîchi par le pas de suivi
        self.assertEqual(list(self.attente.glob("*.json")), [])

    def test_le_fichier_est_retire_meme_sur_exception(self):
        d = self.projet({"apk": "github"})
        gh = FauxGh()

        def suivre_qui_plante(*a, **k):
            self.assertEqual(len(list(self.attente.glob("*.json"))), 1)
            raise RuntimeError("boum")
        gh.suivre = suivre_qui_plante
        with self.assertRaises(RuntimeError):
            self.lancer(["tests", "--dossier", str(d), "--", "x"], gh=gh)
        self.assertEqual(list(self.attente.glob("*.json")), [])


class TestRoutageDeTests(unittest.TestCase):
    def test_lancer_route_tests_par_deporter_seulement_si_le_lieu_est_github(self):
        texte = (RACINE / "lancer.py").read_text(encoding="utf-8")
        self.assertIn("deporter", texte)
        self.assertIn('lieu_de("tests"', texte)
        self.assertIn("lancer.py deporter", texte.split('"""')[1])      # l'usage est dans la docstring

    def test_lancer_tests_au_poste_reste_celui_de_campagne(self):
        r = subprocess.run([sys.executable, str(RACINE / "lancer.py"), "tests", "--dossier", tempfile.gettempdir()],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Usage : lancer.py tests", r.stderr)      # le message de campagne, inchangé


if __name__ == "__main__":
    unittest.main()
