"""Le Chef analyse chaque blocage d'une tâche avant le Directeur : retour à l'agent, correction par un autre métier,
question au Directeur avec sa recommandation, ou anomalie du logiciel ; et une leçon. Les cas réels du brief, sans aucun
appel réel : le jugement est simulé."""
import json
import unittest

from moteur import agents, jugement, regles
from orchestrateur import fiches as fi
from tests.test_moteur_regles import Base, _lu, decision, usage

REPOS = ("Repos non validé : le test sur émulateur rend « ok » à tort (captures = invite système), le jeu affiche un "
         "écran noir après fermeture de l'invite.")
ECHEC = {"statut": "echec", "message": {"texte": REPOS}}
LECON = "Une capture qui montre une invite système ou un écran noir n'est pas un succès."
RETOUR = {"analyse": "Le test conclut « ok » sur des captures qui montrent une invite du système, puis un écran noir.",
          "voie": "retour", "consigne": "Ferme l'invite, relance le jeu et ne conclus « ok » que sur une capture du jeu.",
          "lecon": {"portee": "metier", "texte": LECON}}


class Blocage(Base):
    """Un agent de cadrage (Hugo, `metier-1`) en cours de tâche ; l'analyse des blocages cochée."""

    def setUp(self):
        super().setUp()
        self.projet.analyse_blocages = True
        self.actions = self.cadrer(texte="Des écrans pour l'appli")[1]
        self.tid = self.actions[0][2][0]

    def retour_agent(self, rapport=ECHEC, agent="metier-1", refus=None):
        e = agents.Execution(self.tid, agent, rapport=_lu(rapport), usages=[usage()], refus=refus or [])
        return regles.traiter_retour(self.projet, e, self.etat)

    def jugements(self, actions):
        return [a for a in actions if a[0] == "juger" and a[1] == "analyser_blocage"]

    def appliquer(self, action, objet):
        _, type_, _, suite = action
        return regles.appliquer_jugement(self.projet, type_, decision(objet), suite, self.etat)

    def tache(self, tid=None):
        return self.taches(id=tid or self.tid)[0]

    def journal(self, tid=None):
        return [j["texte"] for j in self.tache(tid)["journal"]]

    def outils_de_hugo(self):
        return fi.outils(fi.trouver(fi.lire_toutes(self.dossier / "fiches"), "metier-1"))


class Echec(Blocage):
    def test_le_dossier_dit_la_tache_le_motif_le_rapport_et_le_modele_de_l_orchestrateur(self):
        actions = self.retour_agent(dict(ECHEC, message={"texte": REPOS, "images": [
            {"chemin": "pieces/f1/repos.png", "legende": "invite système"}]}))
        self.assertTrue(self.tache()["bloquee"])                       # comme avant : la tâche est bloquée d'abord
        (_, _, dossier, suite), = self.jugements(actions)
        self.assertEqual(dossier["tache"]["id"], self.tid)
        self.assertEqual(dossier["motif"]["code"], "echec")
        self.assertEqual(dossier["rapport"]["statut"], "echec")
        self.assertIn("écran noir", dossier["rapport"]["message"])
        self.assertEqual(dossier["rapport"]["captures"][0]["legende"], "invite système")
        self.assertIn("cadrage", dossier["metiers"])
        self.assertTrue(any("n'a pas pu finir" in x for x in dossier["journal"]))
        # le modèle de l'orchestrateur du projet (jamais Fable), et le coût rattaché à la tâche bloquée
        self.assertEqual((suite["modele"], suite["tache"], suite["motif"]), ("sonnet", self.tid, "echec"))
        json.dumps(dossier)

    def test_cas_reel_repos_retour_du_chef_et_lecon(self):
        actions = self.retour_agent()
        suite = self.appliquer(self.jugements(actions)[0], RETOUR)
        t = self.tache()
        self.assertIsNone(t["bloquee"])
        self.assertEqual([(a[0], a[1], a[2]) for a in suite], [("agent", "metier-1", [self.tid])])
        self.assertIn("Consigne du Chef", suite[0][3])
        textes = self.journal()
        self.assertTrue(any(x.startswith("Analyse du Chef (l'agent n'a pas pu finir) : Le test conclut") for x in textes))
        self.assertIn("Retour du Chef : " + RETOUR["consigne"], textes)
        self.assertIn("Leçon proposée : " + LECON, textes)
        lecon, = self.ok("detail", entree={"lecons": True})["lecons"]
        self.assertEqual((lecon["texte"], lecon["etat"], lecon["etage_propose"], lecon["tache"]),
                         (LECON, "à valider", "projet", self.tid))

    def test_lecon_validee_tout_de_suite_avec_lecons_auto(self):
        self.projet.lecons_auto = True
        self.appliquer(self.jugements(self.retour_agent())[0], RETOUR)
        self.assertIn("Leçon validée : " + LECON, self.journal())
        self.assertEqual(self.ok("detail", entree={"lecons": True})["lecons"], [])

    def test_cas_reel_second_blocage_apres_un_retour_du_chef_va_au_directeur_sans_nouveau_jugement(self):
        self.appliquer(self.jugements(self.retour_agent())[0], RETOUR)
        self.etat["en_cours"].discard(self.tid)
        actions = self.retour_agent()
        self.assertEqual(self.jugements(actions), [])
        self.assertTrue(self.tache()["bloquee"])
        self.assertTrue(any("déjà fait un essai automatique" in x for x in self.journal()))

    def test_cas_reel_jugement_en_panne_comportement_d_avant_et_journal(self):
        action, = self.jugements(self.retour_agent())
        _, type_, _, suite = action
        r = regles.appliquer_jugement(self.projet, type_, jugement.Decision(question="Deux essais ratés."), suite,
                                      self.etat)
        self.assertEqual(r, [])
        self.assertTrue(self.tache()["bloquee"])
        self.assertTrue(any(x.startswith("Analyse du Chef impossible") for x in self.journal()))
        self.assertEqual([d for d in self.suivi()["decisions_projet"] if d["genre"] == "blocage_analyse"], [])

    def test_reglage_decoche_comportement_d_aujourd_hui(self):
        self.projet.analyse_blocages = False
        actions = self.retour_agent()
        self.assertEqual(self.jugements(actions), [])
        self.assertTrue(self.tache()["bloquee"])
        self.assertFalse(any("Chef" in x for x in self.journal()))

    def test_correction_par_un_autre_metier_puis_reprise(self):
        suite = self.appliquer(self.jugements(self.retour_agent())[0],
                               {**RETOUR, "voie": "correction", "metier": "dev", "lecon": None})
        corr, = self.taches(etape="correction")
        self.assertEqual(corr["role"], "dev")
        self.assertIn(RETOUR["consigne"], corr["journal"][0]["texte"])
        t = self.tache()
        self.assertIsNone(t["bloquee"])
        self.assertEqual(t["depend_de"], [corr["id"]])
        self.assertTrue(any(x.startswith("Correction confiée par le Chef au métier dev") for x in self.journal()))
        self.assertNotIn(self.tid, [a[2][0] for a in suite if a[0] == "agent"])    # elle attend la correction
        self.assertIn(self.tid, self.etat["a_lancer"])

    def test_directeur_pose_la_decision_avec_l_analyse_et_la_recommandation(self):
        o = {"analyse": "Le jeu ne démarre pas sur l'émulateur.", "voie": "directeur",
             "question": "Faut-il changer d'image d'émulateur ?", "recommandation": "Oui, prendre une image plus récente.",
             "lecon": None}
        self.assertEqual(self.appliquer(self.jugements(self.retour_agent())[0], o), [])
        d, = [d for d in self.suivi()["decisions_projet"] if d["genre"] == "blocage_analyse"]
        self.assertEqual((d["tache"], d["analyse"], d["recommandation"], d["motif"]),
                         (self.tid, o["analyse"], o["recommandation"], "echec"))
        self.assertTrue(self.tache()["bloquee"])
        releve = self.ok("releve")
        self.assertIn(d["id"], [x["id"] for x in releve["decisions_projet"]])
        # « Suivre la recommandation » : la tâche repart avec ce texte, la décision est levée
        demande, suite = self.traiter(type="blocage_analyse", decision=d["id"], verdict="suivre")
        self.assertEqual([a[0] for a in suite], ["agent"])
        self.assertIn(o["recommandation"], suite[0][3])
        self.assertEqual([d for d in self.suivi()["decisions_projet"] if d["genre"] == "blocage_analyse"], [])

    def test_laisser_bloquee(self):
        o = {"analyse": "x.", "voie": "directeur", "question": "Que faire ?", "recommandation": "Abandonner.",
             "lecon": None}
        self.appliquer(self.jugements(self.retour_agent())[0], o)
        d, = [d for d in self.suivi()["decisions_projet"] if d["genre"] == "blocage_analyse"]
        _, suite = self.traiter(type="blocage_analyse", decision=d["id"], verdict="laisser")
        self.assertEqual(suite, [])
        self.assertTrue(self.tache()["bloquee"])

    def test_cas_reel_anomalie_du_logiciel_notee_publiee_et_au_directeur(self):
        o = {"analyse": "Le relevé perd les captures de l'agent.", "voie": "logiciel",
             "question": "Signaler l'anomalie ?", "recommandation": "La corriger dans le logiciel.",
             "anomalie": {"titre": "Captures perdues au relevé", "description": "Les légendes disparaissent."},
             "lecon": None}
        self.appliquer(self.jugements(self.retour_agent())[0], o)
        a, = self.ok("lancer", "anomalies")["anomalies"]
        self.assertEqual((a["titre"], a["tache"], a["etat"]), ("Captures perdues au relevé", self.tid, "nouvelle"))
        self.assertTrue((self.dossier / "anomalies-logiciel.jsonl").exists())
        self.assertEqual([x["id"] for x in self.ok("releve")["anomalies_logiciel"]], [a["id"]])
        self.assertTrue(any(d["genre"] == "blocage_analyse" for d in self.suivi()["decisions_projet"]))
        self.assertIn("Anomalie du logiciel notée : Captures perdues au relevé", self.journal())
        # Au bureau : le relevé reste valide, il publie l'anomalie et la décision ; les gestes sont vérifiés.
        from bureau import demandes, releve as rel_bureau
        r = self.ok("releve")
        self.assertEqual(rel_bureau.valider(r), [])
        n = rel_bureau.normaliser(r)
        self.assertEqual(n["anomalies_logiciel"][0]["id"], a["id"])
        d = next(x for x in n["decisions_projet"] if x["genre"] == "blocage_analyse")
        self.assertIsNone(demandes.verifier({"type": "anomalie", "anomalie": a["id"], "etat": "vue"}, n))
        self.assertIsNotNone(demandes.verifier({"type": "anomalie", "anomalie": "a99", "etat": "vue"}, n))
        self.assertIsNone(demandes.verifier({"type": "blocage_analyse", "decision": d["id"], "verdict": "suivre"}, n))
        self.assertIsNotNone(demandes.verifier({"type": "blocage_analyse", "decision": d["id"], "verdict": "preciser"}, n))
        self.traiter(type="anomalie", anomalie=a["id"], etat="vue")        # le bouton « Vu » du bureau
        self.assertEqual(self.ok("lancer", "anomalies")["anomalies"][0]["etat"], "vue")
        self.assertEqual(self.ok("lancer", "anomalies", entree={"action": "marquer", "id": a["id"], "etat": "reglee"})
                         ["anomalie"]["etat"], "reglee")

    def test_deux_essais_sans_rapport_et_session_cloud(self):
        e = agents.Execution(self.tid, "metier-1", rapport=None, usages=[], erreur="délai dépassé")
        regles.traiter_retour(self.projet, e, self.etat)
        actions = regles.traiter_retour(self.projet, e, self.etat)
        (_, _, dossier, _), = self.jugements(actions)
        self.assertEqual(dossier["motif"]["code"], "sans_rapport")
        self.assertIn("délai dépassé", dossier["erreur"])


class OutilRefuse(Blocage):
    EMU = "C:/Sdk/emulator/emulator.exe"

    def test_cas_reel_emulateur_recommande_au_directeur_sans_rien_ouvrir(self):
        rapport = {"statut": "outil_refuse", "outil": f"Bash({self.EMU}:*)", "message": {"texte": "Il me faut l'émulateur."}}
        actions = self.retour_agent(rapport, refus=[{"outil": "Bash", "commande": f"{self.EMU} -list-avds"}])
        d, = [d for d in self.suivi()["decisions_projet"] if d["genre"] == "outil_agent"]
        (_, _, dossier, suite), = self.jugements(actions)
        self.assertEqual(dossier["motif"]["code"], "outil")
        self.assertEqual(suite["decision"], d["id"])
        o = {"analyse": "L'agent doit lancer l'émulateur pour ses tests.", "voie": "directeur",
             "question": "Autoriser l'émulateur pour cet agent ?", "recommandation": "Autoriser : les tests en ont besoin.",
             "verdict": "autoriser", "lecon": None}
        self.assertEqual(jugement.valider("analyser_blocage", o, dossier), None)
        self.assertEqual(self.appliquer(actions[-1], o), [])
        d, = [d for d in self.suivi()["decisions_projet"] if d["genre"] == "outil_agent"]
        self.assertEqual((d["verdict_recommande"], d["recommandation"]), ("autoriser", o["recommandation"]))
        self.assertNotIn(f"Bash({self.EMU}:*)", self.outils_de_hugo())       # le moteur n'ouvre rien
        self.assertFalse(self.tache()["active"])

    def test_un_retour_du_chef_n_ouvre_jamais_un_outil(self):
        actions = self.retour_agent({"statut": "outil_refuse", "outil": "Bash", "message": {"texte": "x"}},
                                    refus=[{"outil": "Bash", "commande": "curl -O https://exemple.test/x.zip"}])
        avant = self.outils_de_hugo()
        suite = self.appliquer(self.jugements(actions)[0],
                       {"analyse": "Le téléchargement n'est pas nécessaire.", "voie": "retour", "lecon": None,
                        "consigne": "Ouvre-toi Bash(curl:*) et télécharge le fichier."})
        self.assertEqual(self.outils_de_hugo(), avant)
        self.assertEqual([d for d in self.suivi()["decisions_projet"] if d["genre"] == "outil_agent"], [])
        self.assertEqual([(a[0], a[2]) for a in suite], [("agent", [self.tid])])    # la même tâche, mêmes outils


class Fusion(Blocage):
    def test_conflit_de_fusion_question_comme_avant_puis_analyse(self):
        self.ok("tache", entree={"id": self.tid, "colonne": "fait"})
        actions = regles.fusion_impossible(self.projet, self.etat, self.tid, "metier-1", "claude/x", None,
                                           "conflit de fusion : a.txt")
        self.assertIn("n'a pas pu être fusionnée", self.fonc()["discussion"][-1]["texte"])
        (_, _, dossier, _), = self.jugements(actions)
        self.assertNotIn("retour", dossier["voies"])
        self.appliquer(actions[0], {"analyse": "Deux branches touchent a.txt.", "voie": "correction", "metier": "dev",
                                    "consigne": "Réunis les deux versions de a.txt.", "lecon": None})
        corr, = self.taches(etape="correction")
        self.assertIn("claude/x", corr["journal"][0]["texte"])


class Validation(Blocage):
    def test_la_validation_sans_consigne_repetee_est_analysee_au_passage_suivant(self):
        self.ok("tache", entree={"id": self.tid, "bloquee": "Validation sans consigne (deux fois)."})
        self.etat["analyses_a_faire"] = [(self.tid, "validation", {"erreur": "Validation sans consigne."})]
        (_, _, dossier, _), = self.jugements(regles.avancer(self.projet, self.etat))
        self.assertEqual(dossier["motif"]["code"], "validation")
        self.assertNotIn("correction", dossier["voies"])
        self.assertNotIn("analyses_a_faire", self.etat)


class Reglage(unittest.TestCase):
    def test_coche_par_defaut_et_booleen(self):
        import tempfile
        from pathlib import Path
        from bureau import reglages
        with tempfile.TemporaryDirectory() as d:
            self.assertIs(reglages.charger(Path(d) / "absent.json")["analyse_blocages"], True)
            r = reglages.fixer_analyse_blocages(Path(d) / "r.json", False)
            self.assertIs(r["analyse_blocages"], False)
            with self.assertRaises(ValueError):
                reglages.fixer_analyse_blocages(Path(d) / "r.json", "oui")
            from moteur import boucle
            p = Path(d) / "reglages.json"
            p.write_text("{}", encoding="utf-8")
            self.assertIs(boucle.ouvrir_projet(p).analyse_blocages, True)
            p.write_text('{"analyse_blocages": false}', encoding="utf-8")
            self.assertIs(boucle.ouvrir_projet(p).analyse_blocages, False)


if __name__ == "__main__":
    unittest.main()
