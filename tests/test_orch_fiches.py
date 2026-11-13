"""Les fiches d'agents : l'ancien format (un rôle) et la fiche polyvalente (identité seule)."""
import tempfile
import unittest
from pathlib import Path

from orchestrateur import fiches as fi


class TestFiches(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.d = Path(self._tmp.name)

    def ecrire(self, nom, texte):
        chemin = self.d / nom
        chemin.write_text(texte, encoding="utf-8")
        return chemin

    def test_fiche_polyvalente_minimale(self):
        f = fi.lire_fiche(self.ecrire("lea.md", "Clé : lea\nPrénom : Léa\nLieu : local\n"))
        self.assertEqual((f["cle"], f["prenom"], f["lieu"]), ("lea", "Léa", "local"))
        self.assertIsNone(f["role"])
        self.assertIsNone(f["modele"])
        self.assertIsNone(f["service"])
        self.assertEqual(f["lecons"], [])
        self.assertTrue(fi.est_polyvalente(f))

    def test_fiche_ancienne_inchangee(self):
        f = fi.lire_fiche(self.ecrire("dev-1.md", "Clé : dev-1\nPrénom : Léa\nRôle : dev\nService : dev\nModèle : Sonnet\n"
                                      "Lieu : cloud\n\nTexte.\n\n## Leçons\n- [validée] dev-1:L0 : Tester.\n"))
        self.assertEqual((f["role"], f["service"], f["modele"], f["lieu"]), ("dev", "dev", "Sonnet", "cloud"))
        self.assertEqual(f["lecons"], [{"etat": "validée", "id": "dev-1:L0", "texte": "Tester."}])
        self.assertFalse(fi.est_polyvalente(f))
        with self.assertRaises(fi.FicheInvalide):
            fi.lire_fiche(self.ecrire("x.md", "Clé : x\nRôle : dev\nLieu : local\n"))   # ancien format : Modèle obligatoire

    def test_polyvalente_avec_modele_refusee(self):
        with self.assertRaises(fi.FicheInvalide) as e:
            fi.lire_fiche(self.ecrire("lea.md", "Clé : lea\nModèle : Sonnet\nLieu : local\n"))
        self.assertIn("polyvalent", str(e.exception))

    def test_nouvelle_fiche_ecrite_et_relue(self):
        f = fi.nouvelle_fiche("agent-1", "Zoé", "cloud", session="abc")
        self.assertTrue(fi.est_polyvalente(f))
        f["chemin"] = self.d / "agent-1.md"
        fi.ecrire_fiche(f)
        relue = fi.lire_fiche(f["chemin"])
        self.assertEqual((relue["cle"], relue["prenom"], relue["lieu"], relue["session"]), ("agent-1", "Zoé", "cloud", "abc"))
        self.assertTrue(fi.est_polyvalente(relue))
        self.assertEqual([x["cle"] for x in fi.lire_toutes(self.d)], ["agent-1"])


if __name__ == "__main__":
    unittest.main()
