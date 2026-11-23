"""Les décisions de l'adoption des tests au serveur et leurs réponses (`orchestrateur/adoption_tests.py`, tâche 15b)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from orchestrateur import adoption_tests as at  # noqa: E402


IMAGE = {"sha256": "a" * 64, "etiquette": "myiafactory/tests-0123456789ab"}


class AdoptionTestsTest(unittest.TestCase):
    def test_decision_selon_le_verdict(self):
        self.assertEqual(at.decision_pour({"statut": "passe"})["genre"], "tests_serveur_adoption")
        self.assertEqual(at.decision_pour({"statut": "image_a_construire", "attend": "reseau"})["genre"],
                         "tests_reseau_echauffement")
        d = at.decision_pour({"statut": "image_a_construire", "attend": "image",
                              "decision": {"dockerfile": "FROM x", "sha256": "s", "etiquette": "e"}})
        self.assertEqual((d["genre"], d["charge"]["dockerfile"]), ("tests_image_derivee", "FROM x"))
        self.assertEqual(at.decision_pour({"statut": "image_a_construire", "attend": "serveur"}), {})
        e = at.decision_pour({"statut": "echoue", "echecs": [{"nom": "t", "classe": "windows"}], "marqueur": "m"})
        self.assertEqual(e["charge"]["echecs"][0]["classe"], "windows")
        self.assertEqual(at.reponses_de("tests_serveur_adoption", e["charge"]), ("marquer", "garder_poste", "plus_tard"))
        self.assertEqual(at.reponses_de("tests_serveur_adoption", {"statut": "non_deportable"}), ("garder_poste",))

    def test_charge_bornee(self):
        self.assertIsNone(at.verifier_charge("tests_profil", "t", {"a": 1}))
        self.assertIsNotNone(at.verifier_charge("tests_profil", "t", "x"))
        self.assertIsNotNone(at.verifier_charge("tests_profil", "t", {"a": "x" * 30000}))
        self.assertIsNotNone(at.verifier_charge("inconnu", "t", {}))

    def test_seul_activer_regle_le_lieu_des_tests(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "reglages.json")
            f.write_text(json.dumps({"tests": {"adoption": {"statut": "passe"}}}), encoding="utf-8")
            for verdict, genre in (("plus_tard", "tests_serveur_adoption"), ("garder_poste", "tests_serveur_adoption"),
                                   ("construire", "tests_image_derivee")):
                at.reponse(genre, verdict, IMAGE, f, d)
                self.assertNotIn("deport", json.loads(f.read_text("utf-8")))
            r = at.reponse("tests_serveur_adoption", "marquer", {"marqueur": "m"}, f, d)
            self.assertEqual(r["suite"], "marquer")
            self.assertNotIn("deport", json.loads(f.read_text("utf-8")))
            with self.assertRaises(ValueError):
                at.reponse("tests_serveur_adoption", "nimporte", {}, f, d)

    def test_reponse_reseau_ecrite_et_suite(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "reglages.json")
            f.write_text("{}", encoding="utf-8")
            self.assertEqual(at.reponse("tests_reseau_echauffement", "accorder", {}, f, d)["suite"], "evaluer")
            self.assertEqual(json.loads(f.read_text("utf-8"))["tests"]["adoption"]["reseau_echauffement"], "accorde")
            self.assertIsNone(at.reponse("tests_reseau_echauffement", "refuser", {}, f, d)["suite"])
            self.assertEqual(json.loads(f.read_text("utf-8"))["tests"]["adoption"]["reseau_echauffement"], "refuse")

    def test_decision_du_profil_change(self):
        d = at.decision_profil_change("neuve", "ancienne")
        self.assertEqual(d["genre"], "tests_profil")
        self.assertEqual((d["charge"]["empreinte_profil"], d["charge"]["precedente"]), ("neuve", "ancienne"))
        self.assertIsNone(at.verifier_charge(d["genre"], d["texte"], d["charge"]))
        self.assertIn("serveur", d["texte"])
        self.assertEqual(at.reponses_de("tests_profil", d["charge"]), ("reevaluer", "plus_tard"))

    def test_construire_note_la_somme_approuvee(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "reglages.json")
            f.write_text(json.dumps({"tests": {"adoption": {"statut": "image_a_construire"}}, "autre": 1}), encoding="utf-8")
            self.assertIsNone(at.image_approuvee(f))
            r = at.reponse("tests_image_derivee", "construire", {**IMAGE, "dockerfile": "FROM x"}, f, d)
            self.assertEqual(r["suite"], "construire")
            self.assertEqual(at.image_approuvee(f), IMAGE)
            donnees = json.loads(f.read_text("utf-8"))
            self.assertEqual((donnees["autre"], donnees["tests"]["adoption"]["statut"]), (1, "image_a_construire"))
            # une charge sans somme valide n'approuve rien
            for mauvaise in ({}, {**IMAGE, "sha256": "x"}, {**IMAGE, "etiquette": "autre/image"}):
                with self.assertRaises(ValueError):
                    at.reponse("tests_image_derivee", "construire", mauvaise, f, d)


if __name__ == "__main__":
    unittest.main()
