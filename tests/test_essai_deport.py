"""Outil d'essai de l'exécution déportée : échantillonneur, mesure locale, mesure GitHub, rapport, CLI.
Jamais de vrai `gh`, de vrai Gradle ni du vrai `~/MyIAFactory` : tout est injecté (faux exécuteur, faux gh, faux git,
horloge et dormir factices, dossier de rapports temporaire)."""
import io
import json
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))

import essai_deport as ed  # noqa: E402


class Horloge:
    """Horloge factice : chaque appel avance de `pas` secondes."""

    def __init__(self, pas=1.0):
        self.t = 0.0
        self.pas = pas

    def __call__(self):
        self.t += self.pas
        return self.t


def sonde(*valeurs):
    """Une mesure factice qui rend les `(cpu, ram)` donnés, puis le dernier en boucle."""
    restantes = list(valeurs)

    def mesurer():
        v = restantes.pop(0) if len(restantes) > 1 else restantes[0]
        return {"cpu": v[0], "memoire": v[1]}
    return mesurer


class TestEchantillonneur(unittest.TestCase):
    def test_resume_min_moyenne_max_p95_et_duree(self):
        ech = [(0, 10.0, 40.0), (5, 20.0, 50.0), (10, 30.0, 60.0), (15, 40.0, 70.0)]
        r = ed.resume(ech)
        self.assertEqual(r["cpu"], {"min": 10.0, "moyenne": 25.0, "max": 40.0, "p95": 40.0})
        self.assertEqual(r["ram"], {"min": 40.0, "moyenne": 55.0, "max": 70.0, "p95": 70.0})
        self.assertEqual((r["duree_s"], r["nb"]), (15, 4))

    def test_p95_au_rang_le_plus_proche(self):
        ech = [(i, float(i + 1), 0.0) for i in range(20)]      # cpu 1..20
        self.assertEqual(ed.resume(ech)["cpu"]["p95"], 19.0)    # ceil(0,95 * 20) = 19e valeur

    def test_resume_vide(self):
        r = ed.resume([])
        self.assertEqual((r["nb"], r["duree_s"], r["cpu"]["max"]), (0, 0, 0.0))

    def test_enregistre_un_echantillon_au_depart_et_un_a_l_arret(self):
        e = ed.Echantillonneur(intervalle_s=3600, mesurer=sonde((12.0, 34.0)), horloge=Horloge(2.0))
        e.demarrer()
        e.arreter()
        self.assertEqual(len(e.echantillons), 2)
        self.assertEqual(e.echantillons[0][1:], (12.0, 34.0))

    def test_le_fil_echantillonne_puis_s_arrete(self):
        vus = threading.Event()
        compte = []

        def mesurer():
            compte.append(1)
            if len(compte) >= 4:
                vus.set()
            return {"cpu": 50.0, "memoire": 60.0}
        e = ed.Echantillonneur(intervalle_s=0.001, mesurer=mesurer, horloge=Horloge())
        e.demarrer()
        try:
            self.assertTrue(vus.wait(5), "le fil n'a pas échantillonné (garde contre la boucle infinie)")
        finally:
            e.arreter()
        self.assertFalse(e.fil.is_alive())
        n = len(e.echantillons)
        self.assertGreaterEqual(n, 4)

    def test_une_mesure_indisponible_est_ignoree(self):
        e = ed.Echantillonneur(intervalle_s=3600, mesurer=lambda: None, horloge=Horloge())
        e.demarrer()
        e.arreter()
        self.assertEqual(e.echantillons, [])

    def test_le_contexte_arrete_le_fil_meme_sur_exception(self):
        e = ed.Echantillonneur(intervalle_s=3600, mesurer=sonde((1.0, 1.0)), horloge=Horloge())
        with self.assertRaises(ValueError):
            with e:
                raise ValueError("boum")
        self.assertFalse(e.fil.is_alive())


class TestTraduction(unittest.TestCase):
    def test_gradlew_devient_gradlew_bat_sous_windows(self):
        self.assertEqual(ed.traduire("./gradlew assembleDebug", True), ["gradlew.bat", "assembleDebug"])

    def test_inchange_hors_windows(self):
        self.assertEqual(ed.traduire("./gradlew testDebugUnitTest", False), ["./gradlew", "testDebugUnitTest"])

    def test_autre_commande_inchangee_sous_windows(self):
        self.assertEqual(ed.traduire("npm test", True), ["npm", "test"])


class FauxExecuteur:
    def __init__(self, codes=None, pendant=None):
        self.appels = []
        self.codes = codes or {}
        self.pendant = pendant

    def __call__(self, argv, dossier):
        self.appels.append(list(argv))
        if self.pendant:
            self.pendant()
        return self.codes.get(argv[-1], 0)


COMMANDES = {"apk": "./gradlew assembleDebug", "tests": "./gradlew testDebugUnitTest"}


def fabrique(*valeurs):
    return lambda: ed.Echantillonneur(intervalle_s=3600, mesurer=sonde(*valeurs), horloge=Horloge())


class TestMesureLocale(unittest.TestCase):
    def test_lance_les_commandes_dans_l_ordre_avec_duree_code_et_charge(self):
        ex = FauxExecuteur()
        arrets = []
        r = ed.mesurer_local("D", COMMANDES, ex, fabrique((30.0, 40.0), (70.0, 60.0)), horloge=Horloge(10.0),
                             arreter=lambda d: arrets.append(d), windows=True)
        self.assertEqual([a[-1] for a in ex.appels], ["assembleDebug", "testDebugUnitTest"])
        self.assertEqual(ex.appels[0][0], "gradlew.bat")
        self.assertEqual([c["nom"] for c in r["commandes"]], ["apk", "tests"])
        self.assertEqual(r["commandes"][0]["code"], 0)
        self.assertEqual(r["commandes"][0]["duree_s"], 10.0)
        self.assertEqual(r["commandes"][0]["charge"]["cpu"]["max"], 70.0)
        self.assertEqual(r["total_s"], 50.0)   # 5 lectures de l'horloge de 10 s : du premier au dernier appel
        self.assertEqual(r["charge"]["cpu"]["max"], 70.0)
        self.assertEqual(arrets, ["D"])

    def test_les_demons_sont_arretes_meme_sur_echec_de_la_commande(self):
        arrets = []
        ex = FauxExecuteur(codes={"assembleDebug": 1})
        r = ed.mesurer_local("D", COMMANDES, ex, fabrique((1.0, 1.0)), horloge=Horloge(),
                             arreter=lambda d: arrets.append(d), windows=True)
        self.assertEqual(r["commandes"][0]["code"], 1)
        self.assertEqual(arrets, ["D"])

    def test_les_demons_sont_arretes_meme_sur_exception_de_l_executeur(self):
        arrets = []

        def explose(argv, dossier):
            raise OSError("pas de gradle")
        with self.assertRaises(OSError):
            ed.mesurer_local("D", COMMANDES, explose, fabrique((1.0, 1.0)), horloge=Horloge(),
                             arreter=lambda d: arrets.append(d), windows=True)
        self.assertEqual(arrets, ["D"])

    def test_un_echec_arrete_la_suite_des_commandes(self):
        ex = FauxExecuteur(codes={"assembleDebug": 1})
        r = ed.mesurer_local("D", COMMANDES, ex, fabrique((1.0, 1.0)), horloge=Horloge(),
                             arreter=lambda d: None, windows=True)
        self.assertEqual(len(ex.appels), 2)      # les tests tournent quand même : on mesure les deux
        self.assertEqual([c["code"] for c in r["commandes"]], [1, 0])


class TestChargeInitiale(unittest.TestCase):
    def test_moyenne_sur_la_duree(self):
        dormis = []
        moy = ed.charge_initiale(sonde((20.0, 0.0), (40.0, 0.0), (60.0, 0.0)), duree_s=4, dormir=dormis.append)
        self.assertEqual(moy, 55.0)         # 20, 40, 60, 60, 60 : une mesure par seconde, la première amorce (écartée)
        self.assertEqual(sum(dormis), 4)

    def test_mesure_indisponible_vaut_zero(self):
        self.assertEqual(ed.charge_initiale(lambda: None, duree_s=3, dormir=lambda s: None), 0.0)


class FauxGit:
    def __init__(self, tete="abc123456789", distant="abc123456789", modifs="", workflow=True, branche="master"):
        self.tete, self.distant, self.modifs, self.workflow, self.branche = tete, distant, modifs, workflow, branche
        self.appels = []

    def __call__(self, argv, cwd):
        self.appels.append(list(argv))
        a = list(argv)
        if a == ["rev-parse", "HEAD"]:
            return 0, self.tete + "\n"
        if a == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return 0, self.branche + "\n"
        if a[:3] == ["rev-parse", "--abbrev-ref", "--symbolic-full-name"]:
            return 0, "origin/" + self.branche + "\n"
        if a[:2] == ["rev-parse", "--verify"]:
            return (0, self.distant + "\n") if self.distant else (1, "")
        if a[:2] == ["cat-file", "-e"]:
            return (0, "") if self.workflow else (128, "")
        if a[0] == "status":
            return 0, self.modifs
        raise AssertionError("commande git inattendue : %r" % a)


class FauxGh:
    Gh_indisponible = Exception

    def __init__(self, pret=True, jobs_par_run=None, conclusion="success"):
        self.pret = pret
        self.declenchements = []
        self.runs = []
        self.conclusion = conclusion
        self.jobs_par_run = jobs_par_run or {}
        self.suivis = []

    def gh_pret(self, *a, **k):
        return (self.pret, "gh est prêt." if self.pret else "gh absent")

    def declencher(self, dossier, workflow, ref, entrees, *a, **k):
        self.declenchements.append((workflow, ref, dict(entrees)))
        self.runs.append(100 + len(self.runs))

    def execution_du_commit(self, dossier, workflow, commit, *a, **k):
        if not self.runs:
            return None
        return {"id": self.runs[-1], "statut": "in_progress", "conclusion": None, "duree_s": 0, "url": "u"}

    def suivre(self, dossier, run_id, dormir=None, dire=None, delai_s=0, lancer=None):
        self.suivis.append(run_id)
        return {"id": run_id, "statut": "completed", "conclusion": self.conclusion, "duree_s": 400,
                "url": "https://github.com/o/d/actions/runs/%d" % run_id}

    def jobs_du_run(self, dossier, run_id, *a, **k):
        return self.jobs_par_run.get(run_id) or [
            {"name": "apk", "conclusion": "success", "debut": "2026-11-17T10:00:30Z", "fin": "2026-11-17T10:05:01Z"},
            {"name": "tests", "conclusion": "success", "debut": "2026-11-17T10:00:40Z",
             "fin": "2026-11-17T10:03:00Z"}]


def projet_android(parent):
    d = Path(parent) / "MyFridgeCleaner"
    (d / ".factory").mkdir(parents=True)
    (d / ".factory" / "factory.json").write_text(json.dumps({"genre": "application-mobile-android"}), encoding="utf-8")
    return str(d)


MAINTENANT = datetime(2026, 11, 17, 10, 0, 0, tzinfo=timezone.utc)


class TestPreconditionsGithub(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = projet_android(self.tmp.name)

    def verifier(self, gh=None, git=None):
        return ed.verifier_preconditions(self.dossier, gh or FauxGh(), git or FauxGit())

    def test_tout_est_en_ordre(self):
        racine, commit, branche, workflow = self.verifier()
        self.assertEqual((commit, branche, workflow), ("abc123456789", "master", "myfilecleaner.yml".replace(
            "myfilecleaner", "myfridgecleaner")))

    def test_gh_pas_pret(self):
        with self.assertRaises(ed.Refus) as c:
            self.verifier(gh=FauxGh(pret=False))
        self.assertEqual(c.exception.code, ed.CODE_GH)
        self.assertIn("gh", c.exception.message)

    def test_tete_non_poussee(self):
        with self.assertRaises(ed.Refus) as c:
            self.verifier(git=FauxGit(distant="zzz"))
        self.assertEqual(c.exception.code, ed.CODE_NON_POUSSE)
        self.assertIn("pousse", c.exception.message)

    def test_branche_distante_absente(self):
        with self.assertRaises(ed.Refus) as c:
            self.verifier(git=FauxGit(distant=""))
        self.assertEqual(c.exception.code, ed.CODE_NON_POUSSE)

    def test_modifications_suivies_hors_factory(self):
        with self.assertRaises(ed.Refus) as c:
            self.verifier(git=FauxGit(modifs=" M app/src/Main.kt\n M .factory/x.json\n"))
        self.assertEqual(c.exception.code, ed.CODE_MODIFS)
        self.assertIn("app/src/Main.kt", c.exception.message)

    def test_modifications_dans_factory_seulement_tolerees(self):
        self.verifier(git=FauxGit(modifs=" M .factory/reglages.json\n"))

    def test_workflow_absent(self):
        with self.assertRaises(ed.Refus) as c:
            self.verifier(git=FauxGit(workflow=False))
        self.assertEqual(c.exception.code, ed.CODE_WORKFLOW)
        self.assertIn("deport/workflow", c.exception.message)
        self.assertIn("Directeur", c.exception.message)

    def test_codes_distincts(self):
        codes = [ed.CODE_GH, ed.CODE_NON_POUSSE, ed.CODE_MODIFS, ed.CODE_WORKFLOW, ed.CODE_CHARGE]
        self.assertEqual(len(set(codes)), 5)
        self.assertNotIn(0, codes)


class TestMinutesFacturees(unittest.TestCase):
    def test_arrondi_a_la_minute_superieure_par_job(self):
        jobs = [{"name": "apk", "debut": "2026-11-17T10:00:00Z", "fin": "2026-11-17T10:04:01Z"},      # 4 min 1 s -> 5
                {"name": "tests", "debut": "2026-11-17T10:00:00Z", "fin": "2026-11-17T10:02:00Z"},    # 2 min -> 2
                {"name": "x", "debut": "2026-11-17T10:00:00Z", "fin": "2026-11-17T10:00:05Z"}]        # 5 s -> 1
        self.assertEqual(ed.minutes_facturees(jobs), 8)

    def test_job_sans_dates_ignore(self):
        self.assertEqual(ed.minutes_facturees([{"name": "apk"}]), 0)


class TestMesureGithub(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = projet_android(self.tmp.name)

    def mesurer(self, gh, runs=2):
        return ed.mesurer_github(self.dossier, runs, gh, FauxGit(), fabrique((10.0, 30.0), (20.0, 35.0)),
                                 dormir=lambda s: None, horloge=Horloge(5.0),
                                 maintenant=lambda: MAINTENANT, dire=lambda t: None)

    def test_deux_runs_distincts_froid_puis_chaud(self):
        gh = FauxGh()
        r = self.mesurer(gh)
        self.assertEqual(len(gh.declenchements), 2)
        self.assertEqual(gh.declenchements[0], ("myfridgecleaner.yml", "master", {}))
        self.assertEqual([x["etat"] for x in r], ["froid", "chaud"])
        self.assertEqual([x["id"] for x in r], [100, 101])
        self.assertEqual(gh.suivis, [100, 101])

    def test_contenu_d_un_run(self):
        r = self.mesurer(FauxGh(), runs=1)[0]
        self.assertEqual(r["jobs"]["apk"]["duree_s"], 271)       # 4 min 31 s
        self.assertEqual(r["jobs"]["tests"]["duree_s"], 140)
        self.assertEqual(r["conclusion"], "success")
        self.assertEqual(r["minutes_facturees"], 5 + 3)           # ceil(271/60) + ceil(140/60)
        self.assertEqual(r["attente_demarrage_s"], 30.0)          # dispatch à 10:00:00, premier job à 10:00:30
        self.assertEqual(r["duree_run_s"], 400)
        self.assertGreater(r["total_s"], 0)
        self.assertEqual(r["charge_locale"]["cpu"]["max"], 20.0)

    def test_un_run_echoue_est_reporte_tel_quel(self):
        r = self.mesurer(FauxGh(conclusion="failure"), runs=1)[0]
        self.assertEqual(r["conclusion"], "failure")

    def test_le_fil_de_mesure_est_arrete(self):
        fabriques = []

        def f():
            e = ed.Echantillonneur(intervalle_s=3600, mesurer=sonde((1.0, 1.0)), horloge=Horloge())
            fabriques.append(e)
            return e
        ed.mesurer_github(self.dossier, 1, FauxGh(), FauxGit(), f, dormir=lambda s: None, horloge=Horloge(),
                          maintenant=lambda: MAINTENANT, dire=lambda t: None)
        self.assertTrue(fabriques and all(not e.fil.is_alive() for e in fabriques))


def rapport_exemple():
    local = {"commandes": [{"nom": "apk", "duree_s": 300.0, "code": 0, "charge": ed.resume([(0, 50.0, 70.0)])},
                           {"nom": "tests", "duree_s": 120.0, "code": 0, "charge": ed.resume([(0, 60.0, 75.0)])}],
             "total_s": 420.0, "charge": ed.resume([(0, 50.0, 70.0), (5, 90.0, 80.0)])}
    runs = [{"numero": 1, "etat": "froid", "id": 1, "conclusion": "success", "total_s": 500.0, "duree_run_s": 480,
             "attente_demarrage_s": 12.0, "jobs": {"apk": {"duree_s": 400, "conclusion": "success"},
                                                    "tests": {"duree_s": 200, "conclusion": "success"}},
             "minutes_facturees": 11, "charge_locale": ed.resume([(0, 5.0, 40.0), (5, 9.0, 41.0)])},
            {"numero": 2, "etat": "chaud", "id": 2, "conclusion": "success", "total_s": 250.0, "duree_run_s": 230,
             "attente_demarrage_s": 8.0, "jobs": {"apk": {"duree_s": 150, "conclusion": "success"},
                                                    "tests": {"duree_s": 90, "conclusion": "success"}},
             "minutes_facturees": 5, "charge_locale": ed.resume([(0, 4.0, 40.0), (5, 6.0, 41.0)])}]
    return ed.construire_rapport("MyFridgeCleaner", "abc12345", "master", local, runs, MAINTENANT)


class TestRapport(unittest.TestCase):
    def test_gain_temps_charge_quota(self):
        g = rapport_exemple()["gain"]
        self.assertEqual(g["temps"][0], {"etat": "froid", "local_s": 420.0, "github_s": 500.0, "gain_s": -80.0})
        self.assertEqual(g["temps"][1]["gain_s"], 170.0)
        self.assertEqual(g["charge"][1]["cpu_max_local"], 90.0)
        self.assertEqual(g["charge"][1]["cpu_max_attente"], 6.0)
        self.assertEqual(g["quota_minutes"], 16)

    def test_gain_sans_local_ou_sans_github(self):
        r = ed.construire_rapport("p", "c", "b", None, [], MAINTENANT)
        self.assertEqual(r["gain"], {"temps": [], "charge": [], "quota_minutes": 0})

    def test_ecriture_atomique_dans_le_dossier_injecte(self):
        with tempfile.TemporaryDirectory() as t:
            dossier = Path(t) / "essais-deport"
            chemin = ed.ecrire_rapport(rapport_exemple(), dossier, datetime(2026, 11, 17, 14, 5, 9))
            self.assertEqual(Path(chemin).name, "2026-11-17-140509.json")
            lu = json.loads(Path(chemin).read_text(encoding="utf-8"))
            self.assertEqual(lu["projet"], "MyFridgeCleaner")
            self.assertEqual(lu["github"][1]["etat"], "chaud")
            self.assertEqual([p.name for p in dossier.iterdir()], ["2026-11-17-140509.json"])   # pas de .tmp

    def test_resume_lisible_en_francais(self):
        texte = ed.resumer(rapport_exemple())
        for attendu in ("Local", "apk", "tests", "froid", "chaud", "minutes facturées", "Gain", "au repos",
                        "CPU", "RAM"):
            self.assertIn(attendu, texte)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = projet_android(self.tmp.name)
        self.rapports = str(Path(self.tmp.name) / "rapports")

    def lancer(self, *args, **deps):
        sortie = io.StringIO()
        with redirect_stdout(sortie), redirect_stderr(io.StringIO()):
            code = ed.main(list(args), **deps)
        return code, sortie.getvalue()

    def test_sans_confirme_affiche_le_plan_et_ne_fait_rien(self):
        ex = FauxExecuteur()
        gh = FauxGh()
        git = FauxGit()
        code, sortie = self.lancer("--dossier", self.dossier, "--rapports", self.rapports,
                                   executer=ex, gh=gh, git=git)
        self.assertEqual(code, 0)
        self.assertEqual(ex.appels, [])
        self.assertEqual(gh.declenchements, [])
        self.assertEqual(git.appels, [])
        self.assertFalse(Path(self.rapports).exists())
        self.assertIn("--confirme", sortie)
        self.assertIn("assembleDebug", sortie)

    def test_charge_trop_haute_refuse_puis_forcer(self):
        ex = FauxExecuteur()
        deps = dict(executer=ex, gh=FauxGh(), git=FauxGit(), mesurer=sonde((75.0, 50.0)), dormir=lambda s: None,
                    arreter=lambda d: None, horloge=Horloge(), maintenant=lambda: MAINTENANT)
        code, sortie = self.lancer("--dossier", self.dossier, "--mode", "local", "--confirme",
                                   "--rapports", self.rapports, **deps)
        self.assertEqual(code, ed.CODE_CHARGE)
        self.assertEqual(ex.appels, [])
        self.assertIn("60", sortie)
        code, sortie = self.lancer("--dossier", self.dossier, "--mode", "local", "--confirme", "--forcer",
                                   "--rapports", self.rapports, **deps)
        self.assertEqual(code, 0)
        self.assertEqual(len(ex.appels), 2)

    def test_precondition_github_refusee_avant_toute_mesure_locale(self):
        ex = FauxExecuteur()
        code, sortie = self.lancer("--dossier", self.dossier, "--confirme", "--rapports", self.rapports,
                                   executer=ex, gh=FauxGh(), git=FauxGit(distant="zzz"), mesurer=sonde((5.0, 5.0)),
                                   dormir=lambda s: None, arreter=lambda d: None, horloge=Horloge(),
                                   maintenant=lambda: MAINTENANT)
        self.assertEqual(code, ed.CODE_NON_POUSSE)
        self.assertEqual(ex.appels, [])

    def test_les_deux_modes_local_d_abord_puis_github_et_rapport_ecrit(self):
        ordre = []
        ex = FauxExecuteur(pendant=lambda: ordre.append("local"))
        gh = FauxGh()
        declencher = gh.declencher

        def declencher_note(*a, **k):
            ordre.append("github")
            declencher(*a, **k)
        gh.declencher = declencher_note
        code, sortie = self.lancer("--dossier", self.dossier, "--confirme", "--runs", "2",
                                   "--rapports", self.rapports, executer=ex, gh=gh, git=FauxGit(),
                                   mesurer=sonde((5.0, 5.0)), dormir=lambda s: None, arreter=lambda d: None,
                                   horloge=Horloge(), maintenant=lambda: MAINTENANT)
        self.assertEqual(code, 0)
        self.assertEqual(ordre, ["local", "local", "github", "github"])
        fichiers = list(Path(self.rapports).glob("*.json"))
        self.assertEqual(len(fichiers), 1)
        self.assertIn("valable que si", sortie)

    def test_mode_invalide(self):
        code, _ = self.lancer("--dossier", self.dossier, "--mode", "nimporte")
        self.assertEqual(code, 2)

    def test_projet_non_android_refuse(self):
        autre = Path(self.tmp.name) / "autre"
        autre.mkdir()
        code, _ = self.lancer("--dossier", str(autre), "--confirme")
        self.assertEqual(code, 2)

    def test_simuler_de_bout_en_bout_sans_rien_toucher(self):
        code, sortie = self.lancer("--dossier", self.dossier, "--simuler")
        self.assertEqual(code, 0)
        for attendu in ("Local", "froid", "chaud", "Gain", "simulation"):
            self.assertIn(attendu, sortie)
        self.assertFalse(Path(self.rapports).exists())


if __name__ == "__main__":
    unittest.main()
