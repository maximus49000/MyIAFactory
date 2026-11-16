"""Les questions sur le projet : un fil par ligne dans `.factory/questions.jsonl`."""
import json
import tempfile
import unittest
from pathlib import Path

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
