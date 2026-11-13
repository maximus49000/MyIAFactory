"""Le métier : un brief `briefs/<role>.md` enrichi (service, modèle, lieu, spécialité, outils, leçons)."""
import tempfile
import unittest
from pathlib import Path

from orchestrateur import metiers


class TestMetiers(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.briefs = Path(self._tmp.name)

    def test_brief_actuel_sans_entete_se_lit(self):
        (self.briefs / "dev.md").write_text("# Brief dev\nFais le développement.\n", encoding="utf-8")
        m = metiers.lire_metier(self.briefs, "dev")
        self.assertEqual(m["role"], "dev")
        self.assertEqual(m["texte"], "# Brief dev\nFais le développement.")
        for champ in ("service", "modele", "specialite", "outils"):
            self.assertIsNone(m[champ])
        self.assertEqual(m["lieu"], "indifférent")
        self.assertEqual(m["lecons"], [])
        self.assertIsNone(metiers.lire_metier(self.briefs, "absent"))

    def test_entete_complete_relue_a_l_identique(self):
        (self.briefs / "qa.md").write_text(
            "Service : qualite\nModèle : Opus\nLieu : local\nSpécialité : tests d'écran\n"
            "Outils : Read, Bash(py:*)\n\nVérifie tout.\n\n## Leçons\n"
            "- [validée] qa:L1 : Relancer après chaque changement.\n"
            "- [à valider] qa:L2 : Nommer les cas.\n", encoding="utf-8")
        m = metiers.lire_metier(self.briefs, "qa")
        self.assertEqual((m["service"], m["modele"], m["lieu"], m["specialite"], m["outils"]),
                         ("qualite", "Opus", "local", "tests d'écran", "Read, Bash(py:*)"))
        self.assertEqual(m["texte"], "Vérifie tout.")
        self.assertEqual(len(m["lecons"]), 2)
        metiers.ecrire_metier(m)
        self.assertEqual(metiers.lire_metier(self.briefs, "qa"), m)
        self.assertEqual(metiers.lire_tous(self.briefs), {"qa": m})

    def test_modele_fable_refuse_dans_un_brief(self):
        (self.briefs / "dev.md").write_text("Modèle : Fable\n\nTexte.\n", encoding="utf-8")
        with self.assertRaises(metiers.MetierInvalide):
            metiers.lire_metier(self.briefs, "dev")

    def test_ajouter_lecon_sans_doublon(self):
        (self.briefs / "dev.md").write_text("Texte.\n", encoding="utf-8")
        m = metiers.lire_metier(self.briefs, "dev")
        self.assertTrue(metiers.ajouter_lecon(m, {"id": "dev:L1", "etat": "validée", "texte": "Tester."}))
        self.assertFalse(metiers.ajouter_lecon(m, {"id": "dev-1:L9", "etat": "à valider", "texte": "Tester."}))
        self.assertEqual(len(m["lecons"]), 1)

    def test_lecons_a_valider_gardees(self):
        (self.briefs / "dev.md").write_text("Texte.\n", encoding="utf-8")
        m = metiers.lire_metier(self.briefs, "dev")
        metiers.ajouter_lecon(m, {"id": "dev:L2", "etat": "à valider", "texte": "Commenter."})
        metiers.ecrire_metier(m)
        relu = metiers.lire_metier(self.briefs, "dev")
        self.assertEqual(relu["lecons"], [{"id": "dev:L2", "etat": "à valider", "texte": "Commenter."}])
        self.assertEqual(relu["texte"], "Texte.")


if __name__ == "__main__":
    unittest.main()
