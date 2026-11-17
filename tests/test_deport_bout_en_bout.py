"""Exécution déportée, de bout en bout : les vrais modules (deport_depot, github_actions, deporter, moteur.detache,
deport_conso, orchestrateur.depart) face à un faux `gh` (injecté par `lancer`), un dépôt git temporaire avec un origin
nu et des dossiers `~/MyIAFactory` temporaires. Jamais le vrai dossier personnel, jamais le réseau, jamais le vrai `gh`,
jamais un push ailleurs que vers l'origin temporaire. Aucune attente réelle : l'horloge et `dormir` sont fictifs, et
chaque boucle a un plafond dur (une régression échoue au lieu de tourner sans fin)."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "outils"))
import deport_depot  # noqa: E402
import deporter  # noqa: E402
import github_actions  # noqa: E402
from bureau import deport_conso, reglages  # noqa: E402
from bureau.deport_types import catalogue_du_projet  # noqa: E402
from moteur import detache  # noqa: E402
from orchestrateur import depart  # noqa: E402

ANDROID = "application-mobile-android"
PLAFOND_APPELS = 500        # appels à `dormir` / à `gh` au-delà desquels on déclare une boucle folle


def git(cwd, *argv):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git"] + list(argv), cwd=str(cwd), check=True, capture_output=True, text=True,
                          env=env).stdout.strip()


class Reponse:
    def __init__(self, sortie="", code=0, erreur=""):
        self.stdout, self.returncode, self.stderr = sortie, code, erreur


class FauxGitHub:
    """Un faux `gh` compatible `subprocess.run`, avec l'état minimal d'un dépôt : au plus une exécution du workflow."""

    def __init__(self, workflow, jobs=("apk",)):
        self.workflow, self.jobs = workflow, list(jobs)
        self.appels = []
        self.run = None              # {"id", "commit", "vues_restantes"} ; None tant que rien n'est déclenché
        self.declenchements = 0
        self.vues = 0

    # -- l'état du run -----------------------------------------------------------------------------------------
    def fini(self):
        return self.run is not None and self.run["vues_restantes"] <= 0

    def en_cours_encore(self, vues):
        """Simule une exécution encore en route (lancée par un autre appelant) : `vues` lectures avant la fin."""
        self.run["vues_restantes"] = vues

    def _statut(self):
        return "completed" if self.fini() else "in_progress"

    def _jobs(self):
        return [{"name": n, "conclusion": "success", "startedAt": "2026-11-17T10:00:10Z",
                 "completedAt": "2026-11-17T10:05:30Z"} for n in self.jobs]

    def _vue(self):
        return {"status": self._statut(), "conclusion": "success" if self.fini() else None,
                "createdAt": "2026-11-17T10:00:00Z", "updatedAt": "2026-11-17T10:06:00Z",
                "startedAt": "2026-11-17T10:00:10Z", "headSha": self.run["commit"], "name": "monprojet",
                "databaseId": self.run["id"], "url": "https://github.com/x/y/actions/runs/77",
                "jobs": self._jobs() if self.fini() else []}

    # -- subprocess.run ----------------------------------------------------------------------------------------
    def __call__(self, argv, cwd=None, **k):
        self.appels.append(list(argv))
        if len(self.appels) > PLAFOND_APPELS:
            raise AssertionError("plus de %d appels à gh : boucle folle" % PLAFOND_APPELS)
        assert argv[0] == "gh", argv
        a = argv[1:]
        if a[:2] == ["auth", "status"]:
            return Reponse("ok")
        if a[:2] == ["workflow", "run"]:
            assert a[2] == self.workflow and a[3] == "--ref", a
            self.declenchements += 1
            commit = git(cwd, "rev-parse", "origin/" + a[4])
            self.run = {"id": 77, "commit": commit, "vues_restantes": 2}
            return Reponse("")
        if a[:2] == ["run", "list"]:
            if "--commit" in a:
                assert a[a.index("--workflow") + 1] == self.workflow
                if self.run is None or self.run["commit"] != a[a.index("--commit") + 1]:
                    return Reponse("[]")
                v = self._vue()
                v.pop("jobs")
                return Reponse(json.dumps([v]))
            return Reponse(json.dumps([self._vue()] if self.run else []))
        if a[:2] == ["run", "view"]:
            self.vues += 1
            vue = self._vue()
            if a[-1] == "jobs":
                return Reponse(json.dumps({"jobs": vue["jobs"]}))
            self.run["vues_restantes"] -= 1
            return Reponse(json.dumps(self._vue()))
        if a[:2] == ["run", "download"]:
            dossier = Path(a[a.index("-D") + 1])
            dossier.mkdir(parents=True, exist_ok=True)
            (dossier / "app-debug.apk").write_bytes(b"APK")
            return Reponse("")
        if a[:2] == ["repo", "view"]:
            return Reponse(json.dumps({"visibility": "PRIVATE"}))
        if a[:2] == ["api", "user"]:
            return Reponse("", 1, "HTTP 404")         # pas la portée `user` : estimation par les durées
        raise AssertionError("appel gh inattendu : %s" % a)


class GhBranche:
    """Le module `github_actions` réel, branché sur le faux `gh` (ce que `deporter.main` attend de `gh=`)."""
    Gh_indisponible = github_actions.Gh_indisponible

    def __init__(self, lancer):
        self.l = lancer

    def gh_pret(self):
        return github_actions.gh_pret(self.l)

    def execution_du_commit(self, depot, workflow, commit):
        return github_actions.execution_du_commit(depot, workflow, commit, self.l)

    def declencher(self, depot, workflow, ref, entrees):
        return github_actions.declencher(depot, workflow, ref, entrees, self.l)

    def suivre(self, depot, run_id, dormir=None, dire=print, **k):
        return github_actions.suivre(depot, run_id, dormir=dormir, dire=dire, lancer=self.l)

    def jobs_du_run(self, depot, run_id):
        return github_actions.jobs_du_run(depot, run_id, self.l)

    def telecharger(self, depot, run_id, nom, dossier):
        return github_actions.telecharger(depot, run_id, nom, dossier, self.l)


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        # `deport_depot.appliquer` commite avec l'identité de la machine : on en fournit une, sans toucher à la config
        env = mock.patch.dict(os.environ, {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = Path(self._t.name).resolve()
        self.maison = self.tmp / "maison" / "MyIAFactory"        # le faux ~/MyIAFactory
        self.bureau = self.maison / "bureau.json"
        self.attente = self.maison / "deport-en-cours"
        self.cache = self.maison
        self.poste = []
        self.envs = []
        self.artefacts = self.maison / "artefacts"
        self.dormis = 0
        self.vu_pendant_attente = []

    def projet(self, lieux, genre=None, commandes=None):
        """Dépôt `monprojet` sur `main`, un commit poussé vers l'origin nu temporaire ; réglages écrits à la main."""
        origin = self.tmp / "origin.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
        d = self.tmp / "monprojet"
        (d / ".factory").mkdir(parents=True)
        git(d, "init", "-b", "main")
        git(d, "remote", "add", "origin", str(origin))
        deport = {"lieux": lieux}
        if commandes:
            deport["commandes"] = commandes
        self.reglages = d / ".factory" / "reglages.json"
        self.reglages.write_text(json.dumps({"deport": deport}), encoding="utf-8")
        if genre:
            (d / ".factory" / "factory.json").write_text(json.dumps({"genre": genre}), encoding="utf-8")
        (d / "LISEZMOI.md").write_text("projet\n", encoding="utf-8")
        git(d, "add", "LISEZMOI.md")
        git(d, "commit", "-m", "premier")
        git(d, "push", "origin", "main")
        self.origin = origin
        return d

    def executer_poste(self, commande, dossier=None, attendre=True, env=None):
        self.poste.append((list(commande), dossier, attendre))
        self.envs.append(env)
        return 0

    def dormir(self, secondes):
        """Horloge fictive : ne dort jamais ; note ce que l'attente a laissé sur le disque ; plafond dur."""
        self.dormis += 1
        if self.dormis > PLAFOND_APPELS:
            raise AssertionError("plus de %d pauses : boucle folle" % PLAFOND_APPELS)
        for f in sorted(self.attente.glob("*.json")):
            self.vu_pendant_attente.append(json.loads(f.read_text(encoding="utf-8")))

    def deporter(self, argv, gh):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(sortie):
            code = deporter.main(argv, executer_poste=self.executer_poste, gh=gh, dormir=self.dormir,
                                 bureau=self.bureau, repertoire_attente=self.attente, artefacts=self.artefacts,
                                 cache_conso=self.cache)
        self.sortie = sortie.getvalue()
        return code


class TestCatalogueGenerique(Base):
    """Scénario A : `apk: github`, `tests: poste` (catalogue générique : les tests consomment l'APK)."""

    def test_du_workflow_a_la_consommation(self):
        d = self.projet({"apk": "github", "tests": "poste"}, commandes={"apk": "echo construire"})
        reg = json.loads(self.reglages.read_text(encoding="utf-8"))
        main_avant = git(d, "rev-parse", "HEAD")
        statut_avant = git(d, "status", "--porcelain")

        # (i) l'aperçu est proposé : aucun workflow n'existe encore
        apercu = deport_depot.apercu(str(d), reg)
        self.assertEqual(apercu["etat"], "absent")
        self.assertIn("apk:", apercu["diff"])
        self.assertTrue(apercu["empreinte"])
        self.assertFalse((d / ".github").exists())                 # un aperçu n'écrit rien
        refs = git(self.origin, "for-each-ref", "--format=%(refname)")
        self.assertNotIn("deport/workflow", refs)                  # et ne pousse rien

        # (ii) « Valider et pousser » : seulement la branche de travail, la branche courante intacte
        r = deport_depot.appliquer(str(d), apercu["empreinte"], reg)
        self.assertTrue(r["ok"], r)
        refs = git(self.origin, "for-each-ref", "--format=%(refname)").split()
        self.assertEqual(sorted(refs), ["refs/heads/deport/workflow", "refs/heads/main"])
        self.assertEqual(git(self.origin, "rev-parse", "main"), main_avant)       # main distante inchangée
        self.assertEqual(git(d, "rev-parse", "HEAD"), main_avant)                 # HEAD local inchangé
        self.assertEqual(git(d, "rev-parse", "--abbrev-ref", "HEAD"), "main")
        self.assertEqual(git(d, "status", "--porcelain"), statut_avant)           # rien d'écrit dans le dossier
        self.assertFalse((d / ".github").exists())
        wf = git(self.origin, "show", "deport/workflow:.github/workflows/monprojet.yml")
        self.assertIn("echo construire", wf)

        # sans la fusion de la branche de travail, `deporter apk` s'arrête : code 7
        gh = FauxGitHub("monprojet.yml")
        branche = GhBranche(gh)
        self.assertEqual(self.deporter(["apk", "--dossier", str(d)], branche), 7)
        self.assertIn("fusionne deport/workflow", self.sortie)
        self.assertEqual(gh.declenchements, 0)

        # le Directeur fusionne `deport/workflow` dans la branche de travail et la pousse
        git(d, "fetch", "origin", "deport/workflow")
        git(d, "merge", "--no-edit", "FETCH_HEAD")
        git(d, "push", "origin", "main")
        tete = git(d, "rev-parse", "HEAD")

        # (iii) `deporter apk` : HEAD est poussé, le run est déclenché puis suivi jusqu'au succès
        self.vu_pendant_attente.clear()
        self.assertEqual(self.deporter(["apk", "--dossier", str(d)], branche), 0, self.sortie)
        self.assertEqual(gh.declenchements, 1)
        self.assertEqual(gh.run["commit"], tete)
        self.assertIn(["gh", "workflow", "run", "monprojet.yml", "--ref", "main"], gh.appels)
        self.assertIn("réussie", self.sortie)
        # (v) le fichier d'attente existait pendant l'attente, et a disparu ensuite (verrou compris)
        self.assertTrue(self.vu_pendant_attente)
        self.assertEqual(self.vu_pendant_attente[0]["action"], "apk")
        self.assertEqual(self.vu_pendant_attente[0]["lieu"], "github")
        self.assertEqual(list(self.attente.glob("*")), [])
        self.assertEqual(self.poste, [])

        # (iv) `deporter tests` (au poste) attend l'APK : le run de ce commit est encore en route (réutilisé, pas
        # relancé), puis l'artefact est téléchargé et la commande locale part par l'exécuteur du poste
        gh.en_cours_encore(2)
        self.vu_pendant_attente.clear()
        code = self.deporter(["tests", "--dossier", str(d), "--", "echo", "tests"], branche)
        self.assertEqual(code, 0, self.sortie)
        self.assertEqual(gh.declenchements, 1)                      # même commit : le run est réutilisé
        # ruling 15 : l'artefact va hors du projet, dans <artefacts>/<commit>/apk, et son chemin est passé à la commande
        telecharge = [a for a in gh.appels if a[1:3] == ["run", "download"]]
        self.assertEqual(len(telecharge), 1)
        apk = self.artefacts / tete / "apk" / "app-debug.apk"
        self.assertTrue(apk.is_file())
        self.assertFalse((d / "artefacts").exists())
        self.assertEqual(self.poste, [(["echo", "tests"], str(d), True)])
        self.assertEqual(self.envs[-1], {"MYIAFACTORY_ARTEFACT_APK": str(apk)})
        self.assertTrue(self.vu_pendant_attente)
        attente = self.vu_pendant_attente[0]
        self.assertEqual((attente["action"], attente["attend"], attente["lieu"], attente["dossier"]),
                         ("tests", "apk", "github", str(d)))
        self.assertEqual(list(self.attente.glob("*")), [])           # (v) disparu

        # l'attente est reconnue par le moteur (garde-fou) tant que le fichier existe, pas après
        deporter.ecrire_attente("x-1", "tests", "apk", "github", str(d), self.attente)
        try:
            self.assertIsNotNone(detache.attente_deportee(str(self.attente), datetime.now().astimezone(), cwd=str(d)))
        finally:
            deporter.retirer_attente("x-1", self.attente)
        self.assertIsNone(detache.attente_deportee(str(self.attente), datetime.now().astimezone(), cwd=str(d)))

        # (vi) la consommation du mois est cumulée (6 min : 5 min 20 s de job, minute entamée facturée)
        instant = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc).timestamp()
        lieux = {"apk": "github", "tests": "poste", "charge": "poste", "emulateur": "poste"}
        libelles = {a: e["libelle"] for a, e in catalogue_du_projet(str(d))[1].items()}
        self.addCleanup(deport_conso.arreter)
        deport_conso.conso(str(d), libelles, lieux, maintenant=lambda: instant, lancer=gh, cache=self.cache)
        deport_conso.attendre(10)
        vue = deport_conso.conso(str(d), libelles, lieux, maintenant=lambda: instant, lancer=gh, cache=self.cache)
        self.assertEqual(vue["mois"], "2026-11")
        self.assertEqual([(a["action"], a["minutes"], a["executions"]) for a in vue["par_action"]],
                         [("apk", 6.0, 1)])
        self.assertEqual(vue["minutes_total"], 6.0)
        self.assertIsNone(vue["quota"])                              # pas d'autorisation `user` : estimation
        self.assertIn("gh auth refresh -h github.com -s user", vue["texte"])
        self.assertTrue((self.cache / "deport-conso.json").is_file())    # le faux dossier, pas le vrai

        # la consigne des agents renvoie l'APK vers le lanceur, pas les tests au poste
        consigne = depart.deport_consigne({"apk": "github", "tests": "poste"}, catalogue_du_projet(str(d))[1],
                                          {"apk": "echo construire"}, str(d))
        self.assertIn("deporter apk", consigne)
        self.assertNotIn("- Tests : ", consigne)                    # les tests ne sont pas déportés…
        self.assertIn("deporter tests", consigne)                  # …mais attendent l'APK : par `deporter` aussi

    def test_un_deuxieme_appel_apres_succes_reutilise_le_run_sans_attendre(self):
        d = self.projet({"apk": "github", "tests": "poste"}, commandes={"apk": "echo construire"})
        reg = json.loads(self.reglages.read_text(encoding="utf-8"))
        a = deport_depot.apercu(str(d), reg)
        self.assertTrue(deport_depot.appliquer(str(d), a["empreinte"], reg)["ok"])
        git(d, "fetch", "origin", "deport/workflow")
        git(d, "merge", "--no-edit", "FETCH_HEAD")
        git(d, "push", "origin", "main")
        gh = FauxGitHub("monprojet.yml")
        self.assertEqual(self.deporter(["apk", "--dossier", str(d)], GhBranche(gh)), 0, self.sortie)
        self.assertEqual(self.deporter(["apk", "--dossier", str(d)], GhBranche(gh)), 0, self.sortie)
        self.assertEqual(gh.declenchements, 1)


class TestCatalogueAndroid(Base):
    """Scénario B : catalogue `application-mobile-android`, lu dans `.factory/factory.json`."""

    def test_les_tests_unitaires_n_attendent_pas_l_apk(self):
        d = self.projet({"apk": "github", "tests": "poste"}, genre=ANDROID)
        gh = FauxGitHub("monprojet.yml")
        self.assertFalse(deporter.faut_deporter("tests", ["--dossier", str(d)], bureau=self.bureau))
        self.assertEqual(self.deporter(["tests", "--dossier", str(d), "--", "echo", "unitaires"], GhBranche(gh)), 0)
        self.assertEqual(self.poste, [(["echo", "unitaires"], str(d), True)])
        self.assertEqual(gh.appels, [])                             # pas un seul appel à gh : rien à attendre
        self.assertEqual(self.dormis, 0)
        self.assertEqual(list(self.attente.glob("*")) if self.attente.exists() else [], [])

    def test_charge_n_existe_pas_pour_ce_type_de_projet(self):
        d = self.projet({"apk": "github"}, genre=ANDROID)
        catalogue = catalogue_du_projet(str(d))[1]
        self.assertNotIn("charge", catalogue)
        with self.assertRaises(reglages.ReglagesInvalides) as e:
            reglages.fixer_deport(self.reglages, {"lieux": {"charge": "github"}}, catalogue)
        self.assertIn("n'existe pas pour ce type de projet", str(e.exception))
        gh = FauxGitHub("monprojet.yml")
        self.assertEqual(self.deporter(["charge", "--dossier", str(d), "--", "x"], GhBranche(gh)), 2)
        self.assertEqual(gh.appels, [])
        self.assertEqual(self.poste, [])

    def test_release_et_emulateur_restent_au_poste(self):
        d = self.projet({}, genre=ANDROID)
        catalogue = catalogue_du_projet(str(d))[1]
        for action in ("release", "emulateur"):
            with self.assertRaises(reglages.ReglagesInvalides):
                reglages.fixer_deport(self.reglages, {"lieux": {action: "github"}}, catalogue)


class TestToutAuPoste(Base):
    """Scénario C : rien n'est déporté (le défaut) : le flux local est inchangé, gh n'est jamais appelé."""

    def test_rien_ne_change_pour_un_projet_au_poste(self):
        d = self.projet({})
        catalogue = catalogue_du_projet(str(d))[1]
        lieux = {a: "poste" for a in catalogue}
        self.assertEqual(depart.deport_consigne(lieux, catalogue, {}, str(d)), "")
        self.assertEqual(depart.deport_consigne({}, catalogue, {}, str(d)), "")

        def gh_interdit(*a, **k):
            raise AssertionError("gh ne doit jamais être appelé : %s" % (a,))

        for action in catalogue:
            self.assertFalse(deporter.faut_deporter(action, ["--dossier", str(d)], bureau=self.bureau), action)
        self.assertEqual(self.deporter(["tests", "--dossier", str(d), "--", "echo", "ok"], GhBranche(gh_interdit)), 0)
        self.assertEqual(self.poste, [(["echo", "ok"], str(d), True)])
        self.assertIsNone(deport_conso.conso(str(d), {}, lieux, lancer=gh_interdit, cache=self.cache))
        self.assertFalse(self.attente.exists() and list(self.attente.glob("*")))
        self.assertFalse((self.cache / "deport-conso.json").exists())

    def test_lancer_tests_passe_par_deporter_seulement_si_necessaire(self):
        """`lancer.py tests` route par `deporter.lancer_tests` : `deporter` seulement si `faut_deporter` le dit,
        sinon la campagne du poste (vérifié en exécutant le vrai `lancer.py`, routage remplacé par un témoin)."""
        import runpy
        poste = self.projet({})
        vus = []
        vrai = deporter.lancer_tests

        def lancer_tests(argv, **k):      # le vrai routage, mais vers des témoins et le faux bureau
            return vrai(argv, bureau=self.bureau,
                                         deporter_main=lambda a: vus.append(("deporter", a)) or 0,
                                         campagne_main=lambda a: vus.append(("campagne", a)) or 0)
        with mock.patch.object(deporter, "lancer_tests", lancer_tests),                 mock.patch.object(sys, "argv", ["lancer.py", "tests", "--dossier", str(poste), "--", "x"]):
            with self.assertRaises(SystemExit) as fin:
                runpy.run_path(str(RACINE / "lancer.py"), run_name="__main__")
        self.assertEqual(fin.exception.code, 0)
        self.assertEqual(vus, [("campagne", ["--dossier", str(poste), "--", "x"])])
        reg = json.loads(self.reglages.read_text(encoding="utf-8"))
        reg["deport"]["lieux"] = {"tests": "github"}
        self.reglages.write_text(json.dumps(reg), encoding="utf-8")
        vus.clear()
        self.assertEqual(lancer_tests(["--dossier", str(poste), "--", "x"]), 0)
        self.assertEqual(vus, [("deporter", ["tests", "--dossier", str(poste), "--", "x"])])


if __name__ == "__main__":
    unittest.main()
