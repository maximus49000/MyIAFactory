"""`lancer.py deporter` (outils/deporter.py) : faux `gh`, faux lanceur local, dépôts git temporaires avec un origin nu.
Jamais de réseau, jamais de vrai `gh`, jamais de push du vrai dépôt."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
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

    def __init__(self, pret=True, run=None, apres=None, conclusion="success", erreur=None, jobs=None, pause=0.0,
                 surveiller=None):
        self.pret, self.run, self.apres, self.conclusion, self.erreur = pret, run, apres, conclusion, erreur
        self.jobs, self.pause, self.surveiller = jobs, pause, surveiller
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
        if self.surveiller:
            self.surveiller()
        time.sleep(self.pause)
        self.run = {"id": 42, "statut": "queued", "conclusion": None, "duree_s": 0, "url": "http://run/42"}

    def suivre(self, depot, run_id, dormir=None, dire=print, **k):
        self.appels.append(("suivre", run_id))
        dormir(60)
        self.run = dict(self.run, statut="completed", conclusion=self.conclusion)
        if self.jobs is not None:
            self.run["jobs"] = self.jobs
        return self.run

    def jobs_du_run(self, depot, run_id):
        self.appels.append(("jobs_du_run", run_id))
        if self.jobs is None:
            raise self.Gh_indisponible("pas de jobs")
        return self.jobs

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
        self.envs = []
        self.dits = []
        self.artefacts = self.tmp / "artefacts"          # jamais le vrai ~/MyIAFactory
        self.conso = self.tmp / "conso"

    def executer_poste(self, commande, dossier=None, attendre=True, env=None):
        self.poste.append((list(commande), dossier, attendre))
        self.envs.append(env)
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
                                 dormir=lambda s: None, bureau=self.bureau, repertoire_attente=self.attente,
                                 artefacts=self.artefacts, cache_conso=self.conso, **k)
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
        self.assertEqual(noms, ["gh_pret", "execution_du_commit", "declencher", "execution_du_commit", "suivre",
                                "jobs_du_run"])
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
        self.assertIn("pousse ta branche : origin/main n'existe pas", self.sortie)
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


class TestRoutageDeTests(Base):
    """`lancer.py tests` passe par deporter si l'action tourne sur GitHub ou attend une production d'ailleurs."""

    def faut(self, lieux, genre=None):
        d = self.projet(lieux, genre=genre)
        return deporter.faut_deporter("tests", ["--dossier", str(d)], bureau=self.bureau)

    def test_generique_apk_github_tests_poste_passe_par_deporter(self):
        self.assertTrue(self.faut({"apk": "github"}))

    def test_android_apk_github_tests_poste_reste_sur_campagne(self):
        self.assertFalse(self.faut({"apk": "github"}, genre="application-mobile-android"))

    def test_tests_github_passe_par_deporter(self):
        self.assertTrue(self.faut({"tests": "github"}, genre="application-mobile-android"))

    def test_tout_au_poste_reste_sur_campagne(self):
        self.assertFalse(self.faut(None))

    def test_le_defaut_du_bureau_compte(self):
        self.bureau.write_text(json.dumps({"deport": {"lieux": {"apk": "github"}}}), encoding="utf-8")
        self.assertTrue(self.faut(None))

    def test_lieu_non_servi_passe_par_deporter_qui_le_refuse(self):
        self.assertTrue(self.faut({"tests": "serveur"}))

    def test_la_fonction_pure(self):
        from bureau.deport_types import ANDROID, GENERIQUE
        poste = {a: "poste" for a in GENERIQUE}
        self.assertFalse(deporter.doit_passer_par_deporter("tests", poste, GENERIQUE))
        self.assertTrue(deporter.doit_passer_par_deporter("tests", dict(poste, apk="github"), GENERIQUE))
        self.assertFalse(deporter.doit_passer_par_deporter("tests", dict({a: "poste" for a in ANDROID}, apk="github"),
                                                           ANDROID))
        self.assertFalse(deporter.doit_passer_par_deporter("inconnue", poste, GENERIQUE))

    def test_lancer_declare_deporter(self):
        texte = (RACINE / "lancer.py").read_text(encoding="utf-8")
        self.assertIn("lancer.py deporter", texte.split('"""')[1])      # l'usage est dans la docstring

    def test_lancer_tests_au_poste_reste_celui_de_campagne(self):
        r = subprocess.run([sys.executable, str(RACINE / "lancer.py"), "tests", "--dossier", tempfile.gettempdir()],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Usage : lancer.py tests", r.stderr)      # le message de campagne, inchangé


class TestCorrectifs(Base):
    """Relecture de la tâche 9 : run échoué refait, job amont jugé, course verrouillée, « poussé » strict."""
    FAIL = {"id": 5, "statut": "completed", "conclusion": "failure", "duree_s": 1, "url": "http://run/5"}
    ANDROID = "application-mobile-android"

    def declenchements(self, gh):
        return [a for a in gh.appels if isinstance(a, tuple) and a[0] == "declencher"]

    def test_un_run_echoue_du_meme_commit_est_refait_une_seule_fois(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        gh = FauxGh(run=dict(self.FAIL))
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 0)
        self.assertIn("exécution précédente échouée : nouvelle exécution lancée", self.sortie)
        self.assertEqual(len(self.declenchements(gh)), 1)

    def test_run_annule_refait_et_sans_attendre_refuse(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        gh = FauxGh(run=dict(self.FAIL, conclusion="cancelled"))
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--sans-attendre"], gh=gh), 3)
        self.assertEqual(self.declenchements(gh), [])

    def test_le_job_apk_reussi_suffit_meme_si_le_run_entier_echoue(self):
        d = self.projet({"apk": "github"})
        jobs = [{"name": "apk", "conclusion": "success"}, {"name": "lint", "conclusion": "failure"}]
        gh = FauxGh(conclusion="failure", jobs=jobs)
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "x"], gh=gh), 0)
        self.assertEqual(len(self.poste), 1)

    def test_le_job_apk_echoue_donne_5_meme_si_le_run_est_vert(self):
        d = self.projet({"apk": "github"})
        gh = FauxGh(conclusion="success", jobs=[{"name": "apk", "conclusion": "failure"}])
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "x"], gh=gh), 5)
        self.assertEqual(self.poste, [])

    def test_run_reussi_sans_jobs_dans_le_resume_les_jobs_sont_demandes(self):
        d = self.projet({"apk": "github"})
        run = {"id": 5, "statut": "completed", "conclusion": "success", "duree_s": 1, "url": "u"}
        gh = FauxGh(run=run, jobs=[{"name": "apk", "conclusion": "success"}])
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "x"], gh=gh), 0)
        self.assertIn(("jobs_du_run", 5), gh.appels)

    def test_le_job_de_l_action_sur_github_est_juge(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        gh = FauxGh(conclusion="failure", jobs=[{"name": "tests", "conclusion": "success"}])
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 0)

    def test_deux_fils_reels_un_seul_declenchement(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        gh = FauxGh(pause=0.3)
        codes = []

        def appel():
            codes.append(deporter.main(["tests", "--dossier", str(d)], executer_poste=self.executer_poste, gh=gh,
                                       dormir=lambda s: time.sleep(0.02), dire=lambda *a, **k: None,
                                       bureau=self.bureau, repertoire_attente=self.attente,
                                       artefacts=self.artefacts, cache_conso=self.conso))
        fils = [threading.Thread(target=appel) for _ in range(2)]
        for f in fils:
            f.start()
        for f in fils:
            f.join(60)
        self.assertEqual(codes, [0, 0])
        self.assertEqual(len(self.declenchements(gh)), 1)
        self.assertEqual(list(self.attente.glob("*.lock")), [])

    def verrou(self, d):
        commit = git(d, "rev-parse", "HEAD")
        self.attente.mkdir(parents=True, exist_ok=True)
        return self.attente / ("%s-monprojet.lock" % commit)

    def test_verrou_d_un_processus_mort_repris(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        self.verrou(d).write_text(json.dumps({"pid": 999999999, "t": time.time()}), encoding="utf-8")
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)]), 0)

    def test_verrou_perime_repris_meme_si_le_pid_vit(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        self.verrou(d).write_text(json.dumps({"pid": os.getpid(), "t": time.time() - 1000}), encoding="utf-8")
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)]), 0)

    def test_verrou_tenu_et_sans_attendre_refuse(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        self.verrou(d).write_text(json.dumps({"pid": os.getpid(), "t": time.time()}), encoding="utf-8")
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--sans-attendre"], gh=gh), 3)
        self.assertEqual(self.declenchements(gh), [])

    def test_origin_pas_au_commit_code_6_avec_le_message(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        (d / "f.txt").write_text("x", encoding="utf-8")
        git(d, "add", "-A")
        git(d, "commit", "-m", "local")
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 6)
        self.assertIn("pousse ta branche : origin/main n'est pas à ton commit", self.sortie)
        self.assertEqual(self.declenchements(gh), [])

    def test_branche_courante_non_poussee_meme_si_le_commit_est_sur_main(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        git(d, "checkout", "-b", "feat")
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)]), 6)
        self.assertIn("origin/feat n'existe pas", self.sortie)

    def test_branche_poussee_la_ref_est_la_branche_courante(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        git(d, "checkout", "-b", "feat")
        git(d, "push", "-u", "origin", "feat")
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 0)
        self.assertIn(("declencher", "monprojet.yml", "feat"), gh.appels)

    def test_tete_detachee_code_6(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        git(d, "checkout", "--detach")
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)]), 6)
        self.assertIn("Tête détachée", self.sortie)

    def test_le_fichier_d_attente_existe_deja_au_declenchement(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        vus = []
        gh = FauxGh(surveiller=lambda: vus.append(len(list(self.attente.glob("*.json")))))
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 0)
        self.assertEqual(vus, [1])

    def test_lieu_serveur_ou_inconnu_refuse_code_2_jamais_le_poste(self):
        for lieu in ("serveur", "mars"):
            d = self.tmp / ("p-" + lieu)
            (d / ".factory").mkdir(parents=True)
            (d / ".factory" / "reglages.json").write_text(json.dumps({"deport": {"lieux": {"tests": lieu}}}),
                                                          encoding="utf-8")
            self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "x"]), 2)
            self.assertIn("n'est pas disponible", self.sortie)
            self.assertEqual(self.poste, [])

    def test_lieu_serveur_avec_poste_explicite_lance_au_poste(self):
        d = self.projet({"tests": "serveur"}, genre=self.ANDROID)
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--poste", "--", "x"]), 0)
        self.assertEqual(len(self.poste), 1)


class GhQuiTelecharge(FauxGh):
    def telecharger(self, depot, run_id, nom, dossier):
        self.appels.append(("telecharger", run_id, nom, dossier))
        Path(dossier).mkdir(parents=True, exist_ok=True)
        (Path(dossier) / "app-debug.apk").write_bytes(b"APK")
        return str(Path(dossier) / "app-debug.apk")


class TestRelectureFinale(Base):
    """Relecture finale de la branche : I2, I4, I5, I6, I7, I8 et le délai de suivi."""
    ANDROID = "application-mobile-android"

    def declenchements(self, gh):
        return [a for a in gh.appels if isinstance(a, tuple) and a[0] == "declencher"]

    def fini(self, conclusion, id_=5):
        return {"id": id_, "statut": "completed", "conclusion": conclusion, "duree_s": 1, "url": "http://run/%d" % id_}

    # -- I2 : réutilisation jugée sur les jobs nécessaires, une seule relance par (commit, job) --
    def test_un_job_sans_rapport_en_echec_ne_redeclenche_pas(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        gh = FauxGh(run=self.fini("failure"), jobs=[{"name": "tests", "conclusion": "success"},
                                                    {"name": "lint", "conclusion": "failure"}])
        for _ in range(3):
            self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 0)
        self.assertEqual(self.declenchements(gh), [])

    def test_amont_reussi_un_autre_job_en_echec_reutilise(self):
        d = self.projet({"apk": "github", "charge": "github"})
        gh = GhQuiTelecharge(run=self.fini("failure"), jobs=[{"name": "apk", "conclusion": "success"},
                                                             {"name": "charge", "conclusion": "failure"}])
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "x"], gh=gh), 0)
        self.assertEqual(self.declenchements(gh), [])

    def test_job_necessaire_en_echec_relance_une_fois_puis_plus(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        gh = FauxGh(run=self.fini("failure"), conclusion="failure", jobs=[{"name": "tests", "conclusion": "failure"}])
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 1)
        self.assertEqual(len(self.declenchements(gh)), 1)
        for _ in range(2):
            self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 1)
            self.assertIn("déjà relancé une fois pour ce commit : corrige le code", self.sortie)
        self.assertEqual(len(self.declenchements(gh)), 1)

    def test_amont_en_echec_relance_une_fois_puis_code_5(self):
        d = self.projet({"apk": "github"})
        gh = FauxGh(run=self.fini("failure"), conclusion="failure", jobs=[{"name": "apk", "conclusion": "failure"}])
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "x"], gh=gh), 5)
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "x"], gh=gh), 5)
        self.assertIn("déjà relancé une fois", self.sortie)
        self.assertEqual(len(self.declenchements(gh)), 1)
        self.assertEqual(self.poste, [])

    # -- I4 : modifications suivies non commitées --
    def test_modification_suivie_non_commitee_code_6_avec_la_liste(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        (d / ".github" / "workflows" / "monprojet.yml").write_text("name: y\n", encoding="utf-8")
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 6)
        self.assertIn(".github/workflows/monprojet.yml", self.sortie)
        self.assertIn("GitHub teste le commit poussé", self.sortie)
        self.assertEqual(self.declenchements(gh), [])

    def test_la_liste_est_plafonnee(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        for i in range(15):
            (d / ("f%02d.txt" % i)).write_text("a", encoding="utf-8")
        git(d, "add", "-A")
        git(d, "commit", "-m", "fichiers")
        git(d, "push", "origin", "main")
        for i in range(15):
            (d / ("f%02d.txt" % i)).write_text("b", encoding="utf-8")
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)]), 6)
        self.assertIn("(et 5 autres)", self.sortie)

    def test_l_etat_de_la_factory_n_empeche_pas_le_deport(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        (d / ".factory" / "suivi.json").write_text("{}", encoding="utf-8")
        git(d, "add", "-A")
        git(d, "commit", "-m", "suivi")
        git(d, "push", "origin", "main")
        (d / ".factory" / "suivi.json").write_text('{"t": 1}', encoding="utf-8")      # le moteur l'écrit sans cesse
        (d / "nonsuivi.txt").write_text("x", encoding="utf-8")                          # non suivi : ignoré
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)]), 0)

    # -- I5 : un sous-dossier du projet --
    def test_un_sous_dossier_donne_le_projet(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        (d / "app").mkdir()
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d / "app")], gh=gh), 0)
        self.assertIn(("declencher", "monprojet.yml", "main"), gh.appels)
        self.assertEqual(deporter.lieu_de("tests", ["--dossier", str(d / "app")], bureau=self.bureau), "github")
        self.assertTrue(deporter.faut_deporter("tests", ["--dossier", str(d / "app")], bureau=self.bureau))
        self.assertEqual(self.lancer(["lint", "--dossier", str(d / "app"), "--", "x"]), 0)   # catalogue Android

    # -- I6 : la clé de l'agent dans le fichier d'attente --
    def test_la_cle_de_l_agent_est_ecrite(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {"MYIAFACTORY_AGENT": "cle-9"}):
            deporter.ecrire_attente("a-2", "tests", "apk", "github", dossier="/x", repertoire=self.attente)
        self.assertEqual(json.loads((self.attente / "a-2.json").read_text(encoding="utf-8"))["agent"], "cle-9")
        with mock.patch.dict(os.environ, {"MYIAFACTORY_AGENT": ""}):
            deporter.ecrire_attente("a-3", "tests", "apk", "github", dossier="/x", repertoire=self.attente)
        self.assertNotIn("agent", json.loads((self.attente / "a-3.json").read_text(encoding="utf-8")))

    # -- I7 : quota --
    def ecrire_conso(self, d, utilisees):
        self.conso.mkdir(parents=True, exist_ok=True)
        (self.conso / "deport-conso.json").write_text(json.dumps({"depots": {str(d): {
            "lu_a": time.time(), "public": False, "quota": {"utilisees": utilisees, "incluses": 2000},
            "executions": []}}}), encoding="utf-8")

    def test_quota_depasse_code_8_sans_declencher(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        self.ecrire_conso(d, 2000)
        gh = FauxGh()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 8)
        self.assertIn("--poste", self.sortie)
        self.assertIn("Directeur", self.sortie)
        self.assertEqual(self.declenchements(gh), [])
        self.ecrire_conso(d, 100)
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 0)

    def test_quota_depasse_un_run_reussi_reste_reutilisable(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        self.ecrire_conso(d, 5000)
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=FauxGh(run=self.fini("success"))), 0)

    def test_startup_failure_code_8(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=FauxGh(conclusion="startup_failure")), 8)
        self.assertIn("quota probablement épuisé", self.sortie)
        gh = FauxGh(run=self.fini("startup_failure"))
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 8)
        self.assertEqual(self.declenchements(gh), [])

    # -- I8 : artefacts hors du projet, chemin exporté, réutilisés --
    def test_artefact_hors_du_projet_chemin_exporte_et_reutilise(self):
        d = self.projet({"apk": "github"})
        commit = git(d, "rev-parse", "HEAD")
        gh = GhQuiTelecharge()
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "x"], gh=gh), 0)
        apk = self.artefacts / commit / "apk" / "app-debug.apk"
        self.assertTrue(apk.is_file())
        self.assertFalse((d / "artefacts").exists())
        self.assertEqual(self.envs[-1], {"MYIAFACTORY_ARTEFACT_APK": str(apk)})
        self.assertIn(str(apk), self.sortie)
        self.assertEqual(self.lancer(["tests", "--dossier", str(d), "--", "x"], gh=gh), 0)
        self.assertEqual(len([a for a in gh.appels if isinstance(a, tuple) and a[0] == "telecharger"]), 1)
        self.assertEqual(self.envs[-1], {"MYIAFACTORY_ARTEFACT_APK": str(apk)})
        self.assertEqual(list(apk.parent.parent.iterdir()), [apk.parent])     # pas de reste « .partiel »

    def test_nom_de_variable(self):
        self.assertEqual(deporter._nom_variable("apk-release"), "MYIAFACTORY_ARTEFACT_APK_RELEASE")

    # -- (e) délai dépassé : distinct d'un échec --
    def test_delai_depasse_dit_que_l_execution_tourne_peut_etre_encore(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=FauxGh(conclusion="timeout")), 1)
        self.assertIn("délai dépassé, l'exécution tourne peut-être encore", self.sortie)
        self.assertNotIn("échouée", self.sortie)

    def test_code_7_parle_de_la_branche_par_defaut(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID, workflow=False)
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)]), 7)
        self.assertIn("branche par défaut", self.sortie)

    def test_workflow_introuvable_au_declenchement_code_7(self):
        d = self.projet({"tests": "github"}, genre=self.ANDROID)
        gh = FauxGh()

        def declencher(*a):
            raise github_actions.Gh_indisponible("gh workflow run a échoué (1) : HTTP 404: Not Found")
        gh.declencher = declencher
        self.assertEqual(self.lancer(["tests", "--dossier", str(d)], gh=gh), 7)
        self.assertIn("branche par défaut", self.sortie)


class TestCampagneEnv(unittest.TestCase):
    def test_executer_reste_compatible_et_passe_env(self):
        import campagne
        vus = []
        dossier = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(dossier, ignore_errors=True))
        kw = dict(verrou=Path(dossier) / "v.json", lister=lambda: [], dormir=lambda s: None, dire=lambda *a, **k: None)
        self.assertEqual(campagne.executer(["x"], dossier=dossier, lancer=lambda c, d: vus.append((c, d)) or 0, **kw), 0)
        self.assertEqual(campagne.executer(["x"], dossier=dossier, env={"A": "1"},
                                           lancer=lambda c, d, env=None: vus.append((c, d, env)) or 0, **kw), 0)
        self.assertEqual(vus[1][2], {"A": "1"})


if __name__ == "__main__":
    unittest.main()
