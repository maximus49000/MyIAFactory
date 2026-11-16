"""Les questions sur le projet : un fil par ligne dans `.factory/questions.jsonl`."""
import json
import tempfile
import unittest
from pathlib import Path

from moteur import jugement, regles
from orchestrateur import questions
from tests.test_moteur_regles import Base


class TestQuestions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name) / ".factory"
        d.mkdir()
        self.f = {"chemin": str(d / "factory.json"), "nom": "Demo"}

    def test_sans_fichier_aucune_question(self):
        self.assertEqual(questions.lire(self.f), [])

    def test_ouvrir_puis_suivre_un_fil(self):
        q = questions.ouvrir(self.f, {"texte": "Comment est calculé le score ?", "fonctionnalite": "f2"})
        self.assertEqual((q["id"], q["etat"], q["fonctionnalite"]), ("q1", "en_cours", "f2"))
        questions.ajouter(self.f, "q1", {"auteur": "factory", "texte": "Par niveau.", "niveau": "documents",
                                         "sur": True, "suggestion": None})
        questions.marquer(self.f, "q1", "repondue")
        questions.ajouter(self.f, "q1", {"auteur": "utilisateur", "texte": "Et les bonus ?"})
        (fil,) = questions.lire(self.f)
        self.assertEqual([m["auteur"] for m in fil["messages"]], ["utilisateur", "factory", "utilisateur"])
        self.assertEqual(fil["etat"], "en_cours")       # une question de suivi rouvre le fil

    def test_refus(self):
        with self.assertRaises(ValueError):
            questions.ouvrir(self.f, {"texte": "  "})
        with self.assertRaises(ValueError):
            questions.ajouter(self.f, "q9", {"auteur": "factory", "texte": "x"})
        questions.ouvrir(self.f, {"texte": "x"})
        with self.assertRaises(ValueError):
            questions.marquer(self.f, "q1", "perdue")

    def test_limite_et_ligne_illisible(self):
        for i in range(questions.MAX_QUESTIONS + 3):
            questions.ouvrir(self.f, {"texte": f"Q{i}"})
        chemin = questions.chemin(self.f)
        with open(chemin, "a", encoding="utf-8") as fic:
            fic.write("pas du json\n")
        fils = questions.lire(self.f)
        self.assertEqual(len(fils), questions.MAX_QUESTIONS)
        self.assertEqual(fils[0]["messages"][0]["texte"], "Q3")     # les plus anciens partent d'abord


class TestCommandeQuestions(Base):
    def test_ouvrir_par_la_commande_et_publier_au_releve(self):
        q = self.ok("lancer", "questions", entree={"action": "ouvrir", "texte": "À quoi sert l'écran titre ?"})["question"]
        self.assertEqual(q["id"], "q1")
        r = self.ok("releve")
        self.assertEqual([x["id"] for x in r["questions"]], ["q1"])
        from bureau import releve as rel_bureau
        self.assertEqual(rel_bureau.valider(r), [])
        self.assertEqual(rel_bureau.normaliser(r)["questions"][0]["id"], "q1")
        code, rep = self.outil("lancer", "questions", entree={"action": "ouvrir", "texte": "x", "fonctionnalite": "f99"})
        self.assertEqual(code, 1, rep)
        self.assertIn("Fonctionnalité inconnue", rep["erreur"])

    def test_demande_question_ouvre_puis_suit_le_fil(self):
        i = self.ok("actions", entree={"type": "question", "texte": "Comment marche la sauvegarde ?"})["id"]
        d = next(x for x in self.ok("demandes")["demandes"] if x["id"] == i)
        self.assertEqual(d["fil"], "q1")
        self.ok("actions", entree={"type": "question", "texte": "Et en cloud ?", "fil": "q1"})
        (fil,) = self.ok("questions")["questions"]
        self.assertEqual(len(fil["messages"]), 2)

    def test_demande_correction_cree_une_fonctionnalite_de_nature_correction(self):
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Le score reste à 12", "nature": "correction"})
        f = self.fonc("f1")
        self.assertEqual((f["nature"], f["concerne"]), ("correction", None))
        r = next(x for x in self.ok("releve")["fonctionnalites"] if x["id"] == "f1")
        self.assertEqual((r["nature"], r["concerne"]), ("correction", None))
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Encore", "nature": "correction", "concerne": "f1"})
        self.assertEqual(self.fonc("f2")["concerne"], "f1")
        code, rep = self.outil("actions", entree={"type": "fonctionnalite", "texte": "x", "nature": "anomalie"})
        self.assertEqual(code, 1, rep)
        code, rep = self.outil("actions", entree={"type": "fonctionnalite", "texte": "x", "concerne": "f99"})
        self.assertEqual(code, 1, rep)


REPONSE_SURE = {"reponse": "Le score repart de zéro à chaque niveau.", "sur": True, "suggestion": None}


class TestRepondreQuestion(Base):
    def fils(self):
        return self.ok("lancer", "questions", entree={"action": "lister"})["questions"]

    def test_valider(self):
        d = {"fonctionnalites": [{"id": "f1"}]}
        self.assertIsNone(jugement.valider("repondre_question", REPONSE_SURE, d))
        self.assertIsNone(jugement.valider("repondre_question", {**REPONSE_SURE, "suggestion": {
            "nature": "correction", "texte": "Le score…", "concerne": "f1"}}, d))
        for mauvais in ({"reponse": "", "sur": True, "suggestion": None},
                        {"reponse": "x", "sur": "oui", "suggestion": None},
                        {"reponse": "x", "sur": True, "suggestion": {"nature": "idee", "texte": "x"}},
                        {"reponse": "x", "sur": True, "suggestion": {"nature": "correction", "texte": "x",
                                                                    "concerne": "f9"}}):
            self.assertIsNotNone(jugement.valider("repondre_question", mauvais, d), mauvais)

    def test_question_jugee_puis_repondue(self):
        d, actions = self.traiter(type="question", texte="Comment est calculé le score ?")
        ((_, type_, dossier, suite),) = actions
        self.assertEqual(type_, "repondre_question")
        self.assertEqual(dossier["question"]["texte"], "Comment est calculé le score ?")
        self.assertIn("projet", dossier)
        suite_actions = regles.appliquer_jugement(self.projet, type_, jugement.Decision(objet=REPONSE_SURE), suite,
                                                  self.etat)
        self.assertEqual(suite_actions, [])
        (fil,) = self.fils()
        self.assertEqual((fil["etat"], fil["messages"][-1]["niveau"]), ("repondue", "documents"))
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_reponse_pas_sure_escalade_vers_la_lecture(self):
        d, ((_, type_, _, suite),) = self.traiter(type="question", texte="Que fait la fonction de sauvegarde ?")
        actions = regles.appliquer_jugement(self.projet, type_, jugement.Decision(objet={**REPONSE_SURE, "sur": False}),
                                            suite, self.etat)
        self.assertEqual([a[0] for a in actions], ["lire"])
        (fil,) = self.fils()
        self.assertEqual(fil["etat"], "en_lecture")

    def test_jugement_rate_ecrit_dans_le_fil_sans_decision(self):
        d, ((_, type_, _, suite),) = self.traiter(type="question", texte="Pourquoi ?")
        avant = len(self.ok("etat")["decisions"])
        actions = regles.appliquer_jugement(self.projet, type_, jugement.Decision(question="Raté."), suite, self.etat)
        self.assertEqual(actions, [])
        (fil,) = self.fils()
        dernier = fil["messages"][-1]
        self.assertEqual((fil["etat"], dernier["texte"], dernier["niveau"], dernier["sur"]),
                         ("repondue", "Je n'ai pas pu répondre d'après les documents.", "documents", False))
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual(len(self.ok("etat")["decisions"]), avant)

    def test_terminer_sans_demande_ne_plante_pas(self):
        regles._terminer(self.projet, {"demande": None, "fil": "q1"}, "ok")
        regles._terminer(self.projet, None, "ok")


class TestLecteur(Base):
    def fils(self):
        return self.ok("lancer", "questions", entree={"action": "lister"})["questions"]

    def test_approfondir_rend_une_lecture(self):
        self.ok("lancer", "questions", entree={"action": "ouvrir", "texte": "Q ?"})
        self.ok("lancer", "questions", entree={"action": "ajouter", "id": "q1", "auteur": "factory", "texte": "R",
                                              "niveau": "documents", "sur": True})
        d, actions = self.traiter(type="question_approfondir", fil="q1")
        self.assertEqual([a[0] for a in actions], ["lire"])
        self.assertEqual(self.fils()[0]["etat"], "en_lecture")
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")

    def test_dossier_de_lecture_garde_la_question_et_la_premiere_reponse(self):
        self.ok("lancer", "questions", entree={"action": "ouvrir", "texte": "Q ?"})
        self.ok("lancer", "questions", entree={"action": "ajouter", "id": "q1", "auteur": "factory", "texte": "R",
                                              "niveau": "documents", "sur": False})
        d = regles.dossier_de_lecture(self.projet, "q1")
        self.assertEqual((d["question"]["texte"], d["premiere_reponse"]), ("Q ?", "R"))

    def test_appliquer_lecture(self):
        self.ok("lancer", "questions", entree={"action": "ouvrir", "texte": "Q ?"})
        suite = {"demande": None, "fonctionnalite": None, "fil": "q1"}
        actions = regles.appliquer_lecture(self.projet, self.etat, suite,
                                           {**REPONSE_SURE, "fichiers_lus": ["jeu/score.py:12"]}, [])
        self.assertEqual(actions, [])
        (fil,) = self.fils()
        dernier = fil["messages"][-1]
        self.assertEqual((fil["etat"], dernier["niveau"], dernier["fichiers_lus"]),
                         ("repondue", "code", ["jeu/score.py:12"]))

    def test_lecture_invalide_ou_vide_repond_quand_meme(self):
        self.ok("lancer", "questions", entree={"action": "ouvrir", "texte": "Q ?"})
        suite = {"demande": None, "fonctionnalite": None, "fil": "q1"}
        for objet in (None, {"reponse": "", "sur": True, "suggestion": None}, "pas un objet"):
            self.ok("lancer", "questions", entree={"action": "marquer", "id": "q1", "etat": "en_lecture"})
            self.assertEqual(regles.appliquer_lecture(self.projet, self.etat, suite, objet, []), [])
            (fil,) = self.fils()
            self.assertEqual((fil["etat"], fil["messages"][-1]["texte"], fil["messages"][-1]["niveau"]),
                             ("repondue", "Je n'ai pas pu lire le code jusqu'au bout.", "documents"))
        d, actions = self.traiter(type="question_approfondir", fil="q1")     # « Chercher dans le code » reste possible
        self.assertEqual([a[0] for a in actions], ["lire"])

    def test_approfondir_pendant_une_lecture_ne_relance_pas(self):
        self.ok("lancer", "questions", entree={"action": "ouvrir", "texte": "Q ?"})
        self.ok("lancer", "questions", entree={"action": "ajouter", "id": "q1", "auteur": "factory", "texte": "R",
                                              "niveau": "documents", "sur": False})
        self.ok("lancer", "questions", entree={"action": "marquer", "id": "q1", "etat": "en_lecture"})
        d, actions = self.traiter(type="question_approfondir", fil="q1")
        self.assertEqual(actions, [])
        self.assertEqual(self.statut(d["id"])["reponse"], "Je cherche déjà dans le code.")
        self.assertEqual(len(self.fils()[0]["messages"]), 2)

    def test_premiere_reponse_est_celle_des_documents(self):
        self.ok("lancer", "questions", entree={"action": "ouvrir", "texte": "Q ?"})
        for texte in ("R", "Lecture interrompue (le moteur a redémarré)."):
            self.ok("lancer", "questions", entree={"action": "ajouter", "id": "q1", "auteur": "factory",
                                                  "texte": texte, "niveau": "documents", "sur": False})
        self.assertEqual(regles.dossier_de_lecture(self.projet, "q1")["premiere_reponse"], "R")

    def test_lecture_interrompue(self):
        self.ok("lancer", "questions", entree={"action": "ouvrir", "texte": "Q ?"})
        self.ok("lancer", "questions", entree={"action": "ouvrir", "texte": "Autre ?"})
        self.ok("lancer", "questions", entree={"action": "marquer", "id": "q1", "etat": "en_lecture"})
        regles.lecture_interrompue(self.projet)
        q1, q2 = self.fils()
        self.assertEqual((q1["etat"], q2["etat"]), ("repondue", "en_cours"))
        self.assertIn("Lecture interrompue", q1["messages"][-1]["texte"])
