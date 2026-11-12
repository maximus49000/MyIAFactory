"""Les agents cloud : sessions Claude Code lancées et relevées par le moteur. Ni git, ni `claude`, ni réseau réels."""
import json
import unittest

from moteur import agents, appel, boucle, cloud, regles
from orchestrateur import depart
from tests.orch_aide import AvecProjet

FICHE_CLOUD = ("Clé : {cle}\nPrénom : Camille\nRôle : dev\nService : dev\nModèle : Sonnet\nLieu : cloud\n\n"
               "Développe en ligne.\n\n## Leçons\n")
FICHE_LOCAL_HAIKU = "Clé : dev-2\nRôle : dev\nService : dev\nModèle : Haiku\nLieu : local\n\nDéveloppe.\n\n## Leçons\n"
ADRESSE = "https://claude.ai/code/session_01AbCdEf"
RAPPORT_FAIT = {"statut": "fait", "message": {"texte": "Écran fait en ligne."}, "usage_estime": 12345}


class Executeur:
    """Un faux `executer(argv, cwd, delai)` qui garde les commandes et répond selon un petit dictionnaire."""

    def __init__(self, reponses=None):
        self.appels, self.reponses = [], reponses or {}

    def __call__(self, argv, cwd, delai_s):
        self.appels.append(argv)
        for debut, rep in self.reponses.items():
            if " ".join(argv).startswith(debut):
                return rep(argv) if callable(rep) else rep
        return 0, b""


CLAUDE = lambda: "claude"    # noqa: E731


class Session(unittest.TestCase):
    def test_lancer_session_pousse_puis_lance(self):
        ex = Executeur({"claude --cloud": (0, ("Session ouverte : " + ADRESSE).encode())})
        cloud.lancer_session("Fais l'écran.", dossier_projet="/p", modele="Sonnet", executer=ex, trouver=CLAUDE)
        self.assertEqual(ex.appels[0], ["git", "push"])
        self.assertEqual(ex.appels[1], ["claude", "--cloud", "Fais l'écran.", "--model", "sonnet"])

    def test_lancer_session_rend_session_et_adresse(self):
        ex = Executeur({"claude --cloud": (0, ("Session ouverte : " + ADRESSE + "\n").encode())})
        r = cloud.lancer_session("x", dossier_projet="/p", modele="haiku", executer=ex, trouver=CLAUDE)
        self.assertEqual(r, {"session": "session_01AbCdEf", "adresse": ADRESSE})

    def test_lancer_session_refus(self):
        ok = Executeur({"claude --cloud": (0, ADRESSE.encode())})
        for depart, modele, ex in (("x" * 30000, "sonnet", ok), ("x", "fable", ok),
                                   ("x", "sonnet", Executeur({"git push": (1, b"rejected")})),
                                   ("x", "sonnet", Executeur({"claude --cloud": (0, b"rien d'utile")})),
                                   ("x", "sonnet", Executeur({"claude --cloud": (1, b"boum")}))):
            with self.assertRaises(cloud.ErreurCloud):
                cloud.lancer_session(depart, dossier_projet="/p", modele=modele, executer=ex, trouver=CLAUDE)
        self.assertNotIn(["claude"], [a[:1] for a in Executeur().appels])
        with self.assertRaises(cloud.ErreurCloud):
            cloud.lancer_session("x", dossier_projet="/p", modele="sonnet", executer=ok, trouver=lambda: None)

    def test_la_cle_api_n_est_pas_transmise(self):
        import os
        from unittest import mock
        vu = {}

        def faux_run(argv, **kw):
            vu.update(kw["env"])
            return mock.Mock(returncode=0, stdout=b"", stderr=b"")

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-secret"}), \
                mock.patch("subprocess.run", side_effect=faux_run):
            cloud._executer(["git", "status"], ".", 5)
        self.assertNotIn("ANTHROPIC_API_KEY", vu)

    def test_envoyer_suite_meme_session(self):
        ex = Executeur()
        cloud.envoyer_suite("session_01", "Accord donné.", executer=ex, trouver=CLAUDE)
        self.assertEqual(ex.appels, [["claude", "-p", "Accord donné.", "--cloud", "session_01"]])

    def test_lire_session_collee(self):
        self.assertEqual(cloud.lire_session(" https://claude.ai/code/session_01AbCdEf?x=1 "),
                         {"session": "session_01AbCdEf", "adresse": ADRESSE})
        self.assertEqual(cloud.lire_session("session_01AbCdEf"), {"session": "session_01AbCdEf", "adresse": ADRESSE})
        uuid = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
        self.assertEqual(cloud.lire_session(uuid)["session"], uuid)
        for mauvais in ("Ma session", "", "https://example.com/code/session_1", "https://claude.ai/code/",
                        "session_", "x" * 300):
            self.assertIsNone(cloud.lire_session(mauvais), mauvais)

    def test_sans_terminal_raison_claire(self):
        refus = (1, b"Error: --cloud requires an interactive terminal. Non-interactive invocations run locally.")
        with self.assertRaises(cloud.ErreurCloud) as e:
            cloud.lancer_session("x", dossier_projet="/p", modele="haiku", executer=Executeur({"claude --cloud": refus}),
                                 trouver=CLAUDE)
        self.assertEqual(e.exception.raison, cloud.SANS_TERMINAL)
        with self.assertRaises(cloud.ErreurCloud) as e:
            cloud.envoyer_suite("session_1", "x", executer=Executeur({"claude -p": refus}), trouver=CLAUDE)
        self.assertEqual(e.exception.raison, cloud.SANS_TERMINAL)

    def test_prerequis(self):
        github = Executeur({"git remote": (0, b"https://github.com/moi/projet.git\n")})
        self.assertIsNone(cloud.prerequis("/p", executer=github, trouver=CLAUDE))
        self.assertIn("claude", cloud.prerequis("/p", executer=github, trouver=lambda: None))
        ailleurs = Executeur({"git remote": (0, b"https://gitlab.com/moi/projet.git\n")})
        self.assertIn("GitHub", cloud.prerequis("/p", executer=ailleurs, trouver=CLAUDE))
        self.assertIn("GitHub", cloud.prerequis("/p", executer=Executeur({"git remote": (128, b"")}), trouver=CLAUDE))


class FauxTerminal:
    """Un faux `pseudo_terminal.lancer` : affiche des écrans l'un après l'autre (chacun ajouté à la sortie), note ce que
    `repondre` tape, s'arrête quand `arret` le dit. Un écran `None` : le processus se termine."""

    def __init__(self, ecrans, code=0):
        self.ecrans, self.code, self.tape = ecrans, code, []

    def __call__(self, argv, *, cwd, delai_s, env=None, arret=None, repondre=None):
        from moteur import pseudo_terminal as pt
        texte = ""
        for ecran in self.ecrans:
            if ecran is None:
                return pt.Resultat(code=self.code, texte=texte, brut=texte, fini=True)
            texte += ecran
            for _ in range(2):       # deux passages de la boucle par écran
                if arret(texte):
                    return pt.Resultat(code=None, texte=texte, brut=texte, fini=False, arrete=True)
                touches = repondre(texte)
                if touches:
                    self.tape.append(touches)
        return pt.Resultat(code=None, texte=texte, brut=texte, fini=False)


THEME = "Let's get started.\nChoose the text style that looks best with your terminal\n❯ ✔ Dark mode\n"
SECURITE = "Security notes:\n2. only use it with code you trust\nPress Enter to continue…\n"
CONFIANCE = ("Accessing workspace:\nQuick safety check: Is this a project you created or one you trust?\n❯ No, exit\n"
             "Yes, I trust this folder\nEnter to confirm · Esc to cancel\n")


class EssaiFauxTerminal(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        patch = mock.patch.object(cloud, "GRACE_APRES_ADRESSE_S", 0)
        patch.start()
        self.addCleanup(patch.stop)

    def test_accueil_repondu_puis_approbation_du_dossier_demandee(self):
        faux = FauxTerminal([THEME, SECURITE, CONFIANCE])
        r = cloud.essai_pseudo_terminal(["claude", "--cloud", "x"], "/p", lancer=faux)
        self.assertEqual(faux.tape, ["\r", "\r"])                  # thème et notes : jamais l'approbation
        self.assertEqual(r["issue"], "demande")
        self.assertIn("approuver le dossier", r["raison"])
        self.assertIn("trust this folder", r["ecran"])

    def test_session_creee(self):
        faux = FauxTerminal([THEME, SECURITE, "Cloud session created: " + ADRESSE + "\n"])
        r = cloud.essai_pseudo_terminal(["claude", "--cloud", "x"], "/p", lancer=faux)
        self.assertEqual((r["issue"], r["session"], r["adresse"]), ("session", "session_01AbCdEf", ADRESSE))

    def test_refus_sans_terminal_ou_delai(self):
        r = cloud.essai_pseudo_terminal(["claude"], "/p", lancer=FauxTerminal(
            ["Error: --cloud requires an interactive terminal.\n", None], code=1))
        self.assertEqual((r["issue"], r["raison"]), ("fini", cloud.SANS_TERMINAL))
        r = cloud.essai_pseudo_terminal(["claude"], "/p", lancer=FauxTerminal(["Chargement…\n"]))
        self.assertEqual(r["issue"], "delai")

    def test_sans_pseudo_console(self):
        from moteur import pseudo_terminal as pt

        def indisponible(*a, **k):
            raise pt.PseudoTerminalIndisponible("hors Windows")
        with self.assertRaises(cloud.ErreurCloud):
            cloud.essai_pseudo_terminal(["claude"], "/p", lancer=indisponible)


CONFIANCE_OUI = "  No, exit\n❯ Yes, I trust this folder\n"
CREEE = ("Created cloud session: Analyse du projet\nView: " + ADRESSE + "?from=cli&m=0\n"
         "Resume with: claude --teleport session_01AbCdEf\n")


class ApprobationDuDossier(unittest.TestCase):
    """L'approbation du dossier (« Is this a project you created or one you trust? ») n'est répondue que si le
    dossier a été accordé par l'utilisateur."""

    def setUp(self):
        from unittest import mock
        for nom, valeur in (("GRACE_APRES_ADRESSE_S", 0), ("PASSES_STABLES", 1)):
            patch = mock.patch.object(cloud, nom, valeur)
            patch.start()
            self.addCleanup(patch.stop)

    def test_dossier_accorde_bas_puis_entree_puis_session(self):
        faux = FauxTerminal([THEME, SECURITE, CONFIANCE, CONFIANCE_OUI, CREEE])
        r = cloud.essai_pseudo_terminal(["claude", "--cloud", "x"], "/p", lancer=faux, approuver_dossier=True)
        self.assertEqual(faux.tape, ["\r", "\r", "\x1b[B", "\r"])
        self.assertEqual((r["issue"], r["session"], r["adresse"]), ("session", "session_01AbCdEf", ADRESSE))

    def test_jamais_entree_si_la_selection_n_est_pas_oui(self):
        faux = FauxTerminal([THEME, SECURITE, CONFIANCE, CONFIANCE])      # la flèche n'a rien changé
        r = cloud.essai_pseudo_terminal(["claude", "--cloud", "x"], "/p", lancer=faux, approuver_dossier=True)
        self.assertEqual(faux.tape, ["\r", "\r", "\x1b[B"])
        self.assertEqual(r["issue"], "delai")

    def test_dossier_non_accorde_rien_n_est_tape(self):
        faux = FauxTerminal([THEME, SECURITE, CONFIANCE])
        r = cloud.essai_pseudo_terminal(["claude", "--cloud", "x"], "/p", lancer=faux)
        self.assertEqual(faux.tape, ["\r", "\r"])
        self.assertEqual(r["issue"], "demande")

    def test_commande_finie_seule_apres_la_session(self):
        faux = FauxTerminal([CREEE, None])
        r = cloud.essai_pseudo_terminal(["claude", "--cloud", "x"], "/p", lancer=faux, approuver_dossier=True)
        self.assertEqual((r["issue"], r["session"]), ("session", "session_01AbCdEf"))

    def test_lancer_session_par_le_faux_terminal(self):
        ex = Executeur()
        faux = FauxTerminal([THEME, CREEE])
        r = cloud.lancer_session("Fais l'écran.", dossier_projet="/p", modele="Haiku", executer=ex, trouver=CLAUDE,
                                 terminal=faux)
        self.assertEqual(r, {"session": "session_01AbCdEf", "adresse": ADRESSE})
        self.assertEqual(ex.appels, [["git", "push"]])                      # la commande claude : dans le faux terminal

    def test_lancer_session_dossier_a_approuver(self):
        ex = Executeur()
        with self.assertRaises(cloud.ErreurDossierAApprouver) as c:
            cloud.lancer_session("x", dossier_projet="/p", modele="haiku", executer=ex, trouver=CLAUDE,
                                 terminal=FauxTerminal([CONFIANCE]))
        self.assertIsInstance(c.exception, cloud.ErreurCloud)
        self.assertIn("approuver", c.exception.raison)

    def test_lancer_session_dossier_accorde(self):
        faux = FauxTerminal([CONFIANCE, CONFIANCE_OUI, CREEE])
        r = cloud.lancer_session("x", dossier_projet="/p", modele="haiku", executer=Executeur(), trouver=CLAUDE,
                                 terminal=faux, approuver_dossier=True)
        self.assertEqual(r["session"], "session_01AbCdEf")
        self.assertEqual(faux.tape, ["\x1b[B", "\r"])

    def test_lancer_session_faux_terminal_sans_session_leve_une_erreur(self):
        with self.assertRaises(cloud.ErreurCloud):
            cloud.lancer_session("x", dossier_projet="/p", modele="haiku", executer=Executeur(), trouver=CLAUDE,
                                 terminal=FauxTerminal(["Error: boom\n", None], code=1))


class Releve(unittest.TestCase):
    def executeur(self, contenus):
        """`contenus` : {(branche, tâche): texte du fichier de rapport}."""
        def show(argv):
            cle = argv[2].split(":", 1)[0].split("/", 1)[1], argv[2].split("/")[-1][:-5]
            return (0, contenus[cle].encode()) if cle in contenus else (128, b"")
        return Executeur({"git for-each-ref": (0, b"origin/claude/aaa\norigin/claude/bbb\n"), "git show": show})

    def test_rapport_trouve_sur_branche_claude(self):
        ex = self.executeur({("claude/bbb", "t1"): json.dumps(RAPPORT_FAIT)})
        trouves = cloud.chercher_rapports("/p", ["t1", "t2"], executer=ex)
        self.assertEqual(list(trouves), ["t1"])
        branche, r = trouves["t1"]
        self.assertEqual((branche, r["statut"], r["usage_estime"]), ("claude/bbb", "fait", 12345))
        self.assertEqual(ex.appels[0], ["git", "fetch", "--prune", "origin"])
        self.assertIn("git show origin/claude/aaa:.factory/rapports/t1.json", [" ".join(a) for a in ex.appels])

    def test_rapport_absent_rien_rendu(self):
        self.assertEqual(cloud.chercher_rapports("/p", ["t1"], executer=self.executeur({})), {})
        self.assertEqual(cloud.chercher_rapports("/p", [], executer=Executeur()), {})

    def test_rapport_illisible_ignore(self):
        ex = self.executeur({("claude/aaa", "t1"): "{pas du json"})
        self.assertEqual(cloud.chercher_rapports("/p", ["t1"], executer=ex), {})

    def test_fusion_conflit_annule_et_rend_raison(self):
        ex = Executeur({"git merge --no-ff": (1, b"CONFLICT (content): Merge conflict in a.py")})
        raison = cloud.fusionner("/p", "claude/bbb", executer=ex)
        self.assertIn("conflit", raison)
        self.assertIn(["git", "merge", "--abort"], ex.appels)
        self.assertNotIn(["git", "push"], ex.appels)

    def test_fusion_reussie_pousse(self):
        ex = Executeur()
        self.assertIsNone(cloud.fusionner("/p", "claude/bbb", executer=ex))
        self.assertEqual(ex.appels[0][:4], ["git", "merge", "--no-ff", "-m"])
        self.assertEqual(ex.appels[0][-1], "origin/claude/bbb")
        self.assertEqual(ex.appels[-1], ["git", "push"])


class FauxCloud:
    """Le module `cloud` des essais : les sessions et le dépôt sont simulés."""
    ErreurCloud = cloud.ErreurCloud

    def __init__(self):
        self.lancees, self.suites, self.fusions, self.rapports, self.conflit = [], [], [], {}, None
        self.panne = None

    def lancer_session(self, depart, *, dossier_projet, modele):
        if self.panne:
            raise cloud.ErreurCloud(self.panne)
        self.lancees.append({"depart": depart, "modele": modele})
        n = len(self.lancees)
        return {"session": f"session_{n}", "adresse": f"https://claude.ai/code/session_{n}"}

    panne_suite = None

    def envoyer_suite(self, session, texte, **kw):
        if self.panne_suite:
            raise cloud.ErreurCloud(self.panne_suite)
        self.suites.append((session, texte))

    def chercher_rapports(self, dossier, taches, **kw):
        return {t: self.rapports[t] for t in taches if t in self.rapports}

    def fusionner(self, dossier, branche, **kw):
        self.fusions.append(branche)
        return self.conflit


class Base(AvecProjet):
    def setUp(self):
        super().setUp()
        (self.dossier / "fiches" / "lea.md").unlink()                       # plus d'agent local pour le rôle dev
        (self.dossier / "fiches" / "cam.md").write_text(FICHE_CLOUD.format(cle="dev-c1"), encoding="utf-8")
        self.temps = 10_000.0
        self.cloud, self.commits, self.lances = FauxCloud(), [], []
        self.projet = regles.Projet(self.factory, feu_vert=lambda: True, cloud_max=3, prerequis=lambda: None)
        self.moteur = boucle.Moteur([self.projet], horloge=lambda: self.temps, synchrone=True, session_cloud=self.cloud,
                                    commit=lambda d, m: self.commits.append(m),
                                    executer_agent=lambda *a, **k: self.fail("agent local lancé"))
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Des écrans"})
        self.ok("demande-traitee", entree={"id": "r1"})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})

    def suivi(self):
        return json.loads((self.dossier / "suivi.json").read_text(encoding="utf-8"))

    def tache(self, titre="Écran", etape="flux:dev", **extra):
        return self.ok("tache", entree={"titre": titre, "fonctionnalite": "f1", "role": "dev", "colonne": "dev",
                                        "etape": etape, "element": "e1", "active": False, **extra})["id"]

    def discussion(self):
        return next(f for f in self.suivi()["fonctionnalites"] if f["id"] == "f1")["discussion"]

    def avancer(self, secondes=0):
        self.temps += secondes
        self.moteur.tour()


class Agents(Base):
    def test_depart_cloud_demande_rapport_commite(self):
        t = self.tache()
        m = self.ok("depart", entree={"agent": "dev-c1", "tache": t})["message"]
        self.assertTrue(m.startswith("Tu repars de zéro."))
        self.assertIn(f".factory/rapports/{t}.json", m)
        self.assertIn("usage_estime", m)
        self.assertIn("branche `claude/", m)
        local = self.ok("depart", entree={"agent": "metier-1", "tache": t})["message"]
        self.assertNotIn(".factory/rapports", local)
        self.assertIn("fin_cloud", dir(depart))

    def test_agent_cloud_d_un_autre_modele_que_le_lot_prend_la_tache(self):
        """Essai réel : des designers cloud recrutés en Opus restaient inemployés parce que le lot était en Sonnet."""
        (self.dossier / "fiches" / "cam.md").write_text(FICHE_CLOUD.format(cle="dev-c1").replace(
            "Modèle : Sonnet", "Modèle : Opus"), encoding="utf-8")
        t = self.tache()
        court = regles._etat(self.projet)
        tache = next(x for x in court["taches"] if x["id"] == t)
        etat = regles.nouvel_etat()
        self.assertEqual(regles._choisir_agent(self.projet, etat, court, tache, "Sonnet",
                                               local_ok=False, cloud_ok=True), "dev-c1")
        # … et sa session tourne sur le modèle de la tâche (Sonnet), pas sur celui de sa fiche (Opus)
        regles._partir(self.projet, etat, court, "dev-c1", [t], None, {t: tache}, modele_voulu="Sonnet")
        self.assertEqual(etat["departs"][t]["modele"], "Sonnet")

    def test_le_modele_de_la_fiche_cloud_est_un_plafond(self):
        """Une fiche Sonnet ne prend pas une tâche Opus ; une montée au-dessus de la fiche est ramenée à la fiche."""
        t = self.tache()                                         # fiche dev-c1 : Sonnet
        court = regles._etat(self.projet)
        tache = next(x for x in court["taches"] if x["id"] == t)
        etat = regles.nouvel_etat()
        self.assertIsNone(regles._choisir_agent(self.projet, etat, court, tache, "Opus", local_ok=False, cloud_ok=True))
        self.assertEqual(regles._choisir_agent(self.projet, etat, court, tache, "Haiku", local_ok=False, cloud_ok=True),
                         "dev-c1")
        regles._partir(self.projet, etat, court, "dev-c1", [t], None, {t: dict(tache, montee={"a": "Opus"})},
                       modele_voulu="Haiku")
        self.assertEqual(etat["departs"][t]["modele"], "Sonnet")

    def test_depart_d_un_lot_cloud_nomme_le_rapport_de_la_premiere_tache(self):
        a, b = self.tache("A"), self.tache("B")
        m = self.ok("depart", entree={"agent": "dev-c1", "taches": [a, b]})["message"]
        self.assertIn(f".factory/rapports/{a}.json", m)

    def test_le_cloud_part_en_session_sans_agent_local(self):
        t = self.tache()
        self.avancer()
        self.assertEqual(len(self.cloud.lancees), 1)
        self.assertEqual(self.cloud.lancees[0]["modele"], "sonnet")
        self.assertIn("Tu repars de zéro.", self.cloud.lancees[0]["depart"])
        tache = next(x for x in self.suivi()["taches"] if x["id"] == t)
        self.assertTrue(tache["active"])
        self.assertEqual(tache["agent"], "dev-c1")
        self.assertTrue(any("Session cloud session_1 (sonnet)" in j["texte"] for j in tache["journal"]))
        self.assertTrue(self.commits)                                          # le dépôt est poussé avant la session
        self.avancer(10)
        self.assertEqual(len(self.cloud.lancees), 1)                          # une session par tâche

    def test_retour_cloud_applique_puis_fusionne(self):
        t = self.tache()
        self.avancer()
        self.cloud.rapports[t] = ("claude/abc", {**RAPPORT_FAIT, "fichiers": [], "lecons": [], "controles": [],
                                                  "retours_factory": [], "verdicts": []})
        self.avancer(30)
        self.assertEqual(self.cloud.fusions, [])                              # relevé toutes les minutes seulement
        self.avancer(40)
        self.assertEqual(self.cloud.fusions, ["claude/abc"])
        tache = next(x for x in self.suivi()["taches"] if x["id"] == t)
        self.assertEqual((tache["colonne"], tache["active"]), ("fait", False))
        self.assertIn("Écran fait en ligne.", [m["texte"] for m in self.discussion()])
        self.avancer(120)
        self.assertEqual(self.cloud.fusions, ["claude/abc"])                  # appliqué une seule fois

    def test_conflit_pose_decision_avec_adresse(self):
        t = self.tache()
        self.avancer()
        self.cloud.conflit = "conflit de fusion : a.py"
        self.cloud.rapports[t] = ("claude/abc", {"statut": "fait", "message": {"texte": "Fini."}, "fichiers": [],
                                                  "lecons": [], "controles": [], "retours_factory": [], "verdicts": []})
        self.avancer(70)
        derniere = self.discussion()[-1]
        self.assertTrue(derniere["attend"])
        self.assertIn("claude/abc", derniere["texte"])
        self.assertIn("https://claude.ai/code/session_1", derniere["texte"])
        self.assertEqual(len(derniere["questions"][0]["choix"]), 2)

    def test_usage_cloud_estime(self):
        t = self.tache()
        self.avancer()
        self.cloud.rapports[t] = ("claude/abc", {**RAPPORT_FAIT, "fichiers": [], "lecons": [], "controles": [],
                                                  "retours_factory": [], "verdicts": []})
        self.avancer(70)
        usages = [u for u in self.suivi()["usage"] if u.get("tache") == t]
        self.assertEqual(len(usages), 1)
        u = usages[0]
        self.assertTrue(u["estime"])
        self.assertEqual((u["agent"], u["modele"], u["entree"]), ("dev-c1", "claude-sonnet-5-5", 12345))

    def test_accord_cloud_envoie_suite_meme_session(self):
        t = self.tache()
        self.avancer()
        self.cloud.rapports[t] = ("claude/abc", {"statut": "accord_requis", "message": {"texte": "Il me faut un accord."},
                                                  "accord": {"quoi": "Générer 5 images", "partenaire": "studio",
                                                             "cout": "2 $"}})
        self.avancer(70)
        accords = [d for d in self.suivi()["decisions_projet"] if d["genre"] == "accord_agent"]
        self.assertEqual([d["quoi"] for d in accords], ["Générer 5 images"])     # la décision est au bureau de direction
        self.assertEqual(self.cloud.fusions, [])                              # une tâche à moitié faite n'est pas fusionnée
        self.ok("actions", entree={"type": "accord_agent", "decision": accords[0]["id"], "verdict": "accepter"})
        self.avancer(5)
        self.assertEqual(len(self.cloud.lancees), 1)                          # pas de seconde session
        self.assertEqual(len(self.cloud.suites), 1)
        session, texte = self.cloud.suites[0]
        self.assertEqual(session, "session_1")
        self.assertIn("accord pour : Générer 5 images", texte)

    def test_limite_agents_cloud(self):
        (self.dossier / "fiches" / "cam2.md").write_text(FICHE_CLOUD.format(cle="dev-c2"), encoding="utf-8")
        self.projet.cloud_max = 1
        self.tache("A", etape="correction")
        self.tache("B", etape="correction")
        self.avancer()
        self.assertEqual(len(self.cloud.lancees), 1)                          # la deuxième attend la fin de la première
        self.projet.cloud_max = 2
        self.avancer()
        self.assertEqual(len(self.cloud.lancees), 2)

    def regler_cloud(self, n):
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["agents_cloud_max"] = n
        self.factory.write_text(json.dumps(f), encoding="utf-8")

    def test_reglage_du_projet_l_emporte_sur_l_ancienne_limite(self):
        (self.dossier / "fiches" / "cam2.md").write_text(FICHE_CLOUD.format(cle="dev-c2"), encoding="utf-8")
        self.regler_cloud(1)                    # l'ancienne limite (3) ne compte plus
        self.tache("A", etape="correction")
        self.tache("B", etape="correction")
        self.avancer()
        self.assertEqual(len(self.cloud.lancees), 1)
        self.regler_cloud(0)
        self.avancer()
        self.assertEqual(len(self.cloud.lancees), 1)

    def test_un_agent_cloud_ne_compte_pas_dans_la_charge(self):
        self.regler_cloud(2)
        self.projet._feu_vert = lambda: False     # le poste est trop chargé : les places locales sont fermées
        self.tache("A", etape="correction")
        self.avancer()
        self.assertEqual(len(self.cloud.lancees), 1)

    def test_session_muette_deux_heures_pose_decision(self):
        t = self.tache()
        self.avancer()
        self.avancer(3600)
        self.assertFalse(any(m["auteur"] == "chef" for m in self.discussion()))
        self.avancer(3700)
        question = self.discussion()[-1]
        self.assertTrue(question["attend"])
        self.assertIn("deux heures", question["texte"])
        self.assertIn("https://claude.ai/code/session_1", question["texte"])
        self.assertEqual(question["questions"][0]["choix"], [regles.ATTENDRE, regles.RELANCER, regles.ABANDONNER])
        nombre = len(self.discussion())
        self.avancer(120)
        self.assertEqual(len(self.discussion()), nombre)                      # la question n'est posée qu'une fois
        # « Attendre encore » : le compte à rebours repart
        self.ok("actions", entree={"type": "message", "fonctionnalite": "f1", "texte": regles.ATTENDRE})
        self.avancer(70)
        self.avancer(3600)
        self.assertEqual(len(self.cloud.lancees), 1)
        # « Relancer l'agent » : une nouvelle session
        self.avancer(4000)
        self.ok("actions", entree={"type": "message", "fonctionnalite": "f1", "texte": regles.RELANCER})
        self.avancer(5)
        self.assertEqual(len(self.cloud.lancees), 2)
        tache = next(x for x in self.suivi()["taches"] if x["id"] == t)
        self.assertTrue(tache["active"])

    def test_abandonner_bloque_la_tache(self):
        t = self.tache()
        self.avancer()
        self.avancer(7300)
        self.ok("actions", entree={"type": "message", "fonctionnalite": "f1", "texte": regles.ABANDONNER})
        self.avancer(5)
        tache = next(x for x in self.suivi()["taches"] if x["id"] == t)
        self.assertTrue(tache["bloquee"])
        self.assertFalse(tache["active"])

    def test_echec_du_lancement_relance_une_fois_puis_bloque(self):
        t = self.tache()
        self.cloud.panne = "le dépôt n'a pas pu être poussé"
        self.avancer()
        self.avancer(5)
        tache = next(x for x in self.suivi()["taches"] if x["id"] == t)
        self.assertIn("deux essais", tache["bloquee"])
        self.assertEqual(self.cloud.lancees, [])

    def decision_session(self):
        return next(x for x in self.suivi()["decisions_projet"] if x["genre"] == "session_cloud")

    def test_secours_manuel_de_bout_en_bout(self):
        t = self.tache()
        self.cloud.panne = cloud.SANS_TERMINAL
        self.avancer()
        self.avancer(5)
        d = self.decision_session()
        self.assertEqual((d["tache"], d["lien"]), (t, "https://claude.ai/code"))
        self.assertIn(f".factory/rapports/{t}.json", d["depart"])
        self.assertIn("terminal interactif", d["texte"])
        # Le Directeur crée la session sur claude.ai/code, colle le message, puis l'adresse de la session.
        self.ok("actions", entree={"type": "session_cloud", "decision": d["id"],
                                   "session": "https://claude.ai/code/session_01Manuel"})
        self.avancer(5)
        self.assertEqual(self.cloud.lancees, [])                               # pas de nouvelle session lancée
        self.assertNotIn(d["id"], [x["id"] for x in self.suivi()["decisions_projet"]])
        tache = next(x for x in self.suivi()["taches"] if x["id"] == t)
        self.assertTrue(tache["active"])
        self.assertIsNone(tache["bloquee"])
        self.cloud.rapports[t] = ("claude/manuel", {**RAPPORT_FAIT, "fichiers": [], "lecons": [], "controles": [],
                                                    "retours_factory": [], "verdicts": []})
        self.avancer(70)
        self.assertEqual(self.cloud.fusions, ["claude/manuel"])
        tache = next(x for x in self.suivi()["taches"] if x["id"] == t)
        self.assertEqual(tache["colonne"], "fait")
        # La tâche suivante de l'agent part dans la session inscrite (le lancement automatique échoue toujours).
        t2 = self.tache("Écran 2", element="e2")
        self.avancer(5)
        self.assertEqual(self.cloud.lancees, [])
        self.assertEqual(len(self.cloud.suites), 1)
        session, texte = self.cloud.suites[0]
        self.assertEqual(session, "session_01Manuel")
        self.assertIn(f".factory/rapports/{t2}.json", texte)
        tache2 = next(x for x in self.suivi()["taches"] if x["id"] == t2)
        self.assertTrue(any("Session cloud session_01Manuel (sonnet)" in j["texte"] for j in tache2["journal"]))
        self.assertEqual(self.moteur.etats[str(self.projet.factory)]["cloud"][t2]["session"], "session_01Manuel")

    def test_secours_la_session_inscrite_refuse_aussi(self):
        etat = self.moteur.etats[str(self.projet.factory)]
        etat["sessions_cloud"] = {"dev-c1": "session_01Manuel"}
        self.cloud.panne, self.cloud.panne_suite = cloud.SANS_TERMINAL, cloud.SANS_TERMINAL
        t = self.tache()
        self.avancer()
        self.avancer(5)
        tache = next(x for x in self.suivi()["taches"] if x["id"] == t)
        self.assertIn("deux essais", tache["bloquee"])
        d = self.decision_session()
        self.assertEqual(d["lien"], "https://claude.ai/code/session_01Manuel")   # la session de l'agent, à reprendre
        self.assertIn(f".factory/rapports/{t}.json", d["depart"])

    def test_sans_github_bascule_en_local_et_le_dit(self):
        (self.dossier / "fiches" / "local.md").write_text(FICHE_LOCAL_HAIKU, encoding="utf-8")
        self.projet._prerequis = lambda: "le projet n'est pas sur GitHub"
        vus = []

        def agent_local(depart_, matiere, *, agent, modele, dossier_projet, tache=None, lot=None, **plus):
            vus.append((agent["cle"], modele))
            return agents.Execution(tache, agent["cle"], lot, usages=[], erreur="x")

        self.moteur.executer_agent = agent_local
        self.tache()
        self.avancer()
        self.assertEqual(self.cloud.lancees, [])
        self.assertEqual(vus, [("dev-2", "haiku")])                           # l'agent local équivalent
        message = next(m["texte"] for m in self.discussion() if m["auteur"] == "chef")
        self.assertIn("le projet n'est pas sur GitHub", message)
        self.assertIn("dev-2", message)

    def test_session_retrouvee_au_redemarrage(self):
        t = self.tache()
        self.avancer()
        nouveau = boucle.Moteur([self.projet], horloge=lambda: self.temps, synchrone=True, session_cloud=self.cloud,
                                commit=lambda d, m: None, executer_agent=lambda *a, **k: self.fail("agent local"))
        nouveau.tour()
        self.assertEqual(len(self.cloud.lancees), 1)                          # pas de seconde session
        self.assertEqual(nouveau.etats[str(self.projet.factory)]["cloud"][t]["session"], "session_1")


class Reglages(unittest.TestCase):
    def test_agents_cloud_max_lu_dans_les_reglages(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "reglages.json").write_text(json.dumps({"agents_cloud_max": 5}), encoding="utf-8")
            self.assertEqual(boucle.ouvrir_projet(Path(d) / "reglages.json", environ={}).cloud_max, 5)
            (Path(d) / "reglages.json").write_text("{}", encoding="utf-8")
            self.assertEqual(boucle.ouvrir_projet(Path(d) / "reglages.json", environ={}).cloud_max, 3)


if __name__ == "__main__":
    unittest.main()
