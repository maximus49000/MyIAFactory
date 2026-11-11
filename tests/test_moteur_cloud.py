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

    def test_prerequis(self):
        github = Executeur({"git remote": (0, b"https://github.com/moi/projet.git\n")})
        self.assertIsNone(cloud.prerequis("/p", executer=github, trouver=CLAUDE))
        self.assertIn("claude", cloud.prerequis("/p", executer=github, trouver=lambda: None))
        ailleurs = Executeur({"git remote": (0, b"https://gitlab.com/moi/projet.git\n")})
        self.assertIn("GitHub", cloud.prerequis("/p", executer=ailleurs, trouver=CLAUDE))
        self.assertIn("GitHub", cloud.prerequis("/p", executer=Executeur({"git remote": (128, b"")}), trouver=CLAUDE))


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

    def envoyer_suite(self, session, texte, **kw):
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
        derniere = self.discussion()[-1]
        self.assertEqual(derniere["questions"][0]["choix"], [regles.ACCEPTE, regles.REFUSE])
        self.assertEqual(self.cloud.fusions, [])                              # une tâche à moitié faite n'est pas fusionnée
        self.ok("actions", entree={"type": "message", "fonctionnalite": "f1", "texte": regles.ACCEPTE})
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
