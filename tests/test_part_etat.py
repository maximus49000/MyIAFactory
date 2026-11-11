"""Le fichier des partenaires : règles d'usage, règle de départ de Tripo."""
import unittest

from partenaires import etat


class TestEtat(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.chemin = Path(t.name) / "partenaires.json"

    def test_regles_crud(self):
        e = etat.Etat(self.chemin)
        with e.transaction() as d:
            r = etat.regle(d, "vox", "ajouter", texte="  Voix calme.  ")
            self.assertEqual(r["id"], "r1")
            etat.regle(d, "vox", "ajouter", texte="Pas de cri.")
        with e.transaction() as d:
            etat.regle(d, "vox", "modifier", "r2", "Pas de cri, jamais.")
            etat.regle(d, "vox", "supprimer", "r1")
        regles = e.lire()["regles"]["vox"]
        self.assertEqual([(x["id"], x["texte"]) for x in regles], [("r2", "Pas de cri, jamais.")])
        self.assertIn("modifie_le", regles[0])
        with e.transaction() as d:
            for mauvais in (("modifier", "r9", "x"), ("ajouter", None, ""), ("ajouter", None, "x" * 501),
                            ("renommer", "r2", "x")):
                with self.assertRaises(ValueError):
                    etat.regle(d, "vox", *mauvais)

    def test_regle_tripo_proposee_une_fois(self):
        e = etat.Etat(self.chemin)
        self.assertEqual(e.lire()["regles"]["tripo"][0]["texte"], etat.REGLE_TRIPO)
        with e.transaction() as d:
            etat.regle(d, "tripo", "supprimer", "r1")
        self.assertEqual(e.lire()["regles"]["tripo"], [])
        with e.transaction():
            pass
        self.assertEqual(e.lire()["regles"]["tripo"], [])


if __name__ == "__main__":
    unittest.main()
