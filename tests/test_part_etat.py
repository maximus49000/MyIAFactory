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

    def test_inscription_le_fait_seulement(self):
        e = etat.Etat(self.chemin)
        self.assertEqual(e.lire()["inscriptions"], {})
        with e.transaction() as d:
            ligne = etat.inscrire(d, "tripo", True, "  compte gratuit,   offre Pro ", quand="2026-11-12T10:00:00+01:00")
        self.assertEqual(ligne, {"depuis": "2026-11-12T10:00:00+01:00", "note": "compte gratuit, offre Pro"})
        self.assertEqual(e.lire()["inscriptions"], {"tripo": ligne})
        with e.transaction() as d:
            etat.inscrire(d, "vox", True)
        self.assertNotIn("note", e.lire()["inscriptions"]["vox"])
        with e.transaction() as d:
            self.assertIsNone(etat.inscrire(d, "tripo", False))
        self.assertEqual(list(e.lire()["inscriptions"]), ["vox"])
        with e.transaction() as d:
            with self.assertRaises(ValueError):
                etat.inscrire(d, "vox", "oui")

    def test_inscription_refuse_un_secret_dans_la_note(self):
        for mauvaise in ("mot de passe : abc", "Password=hunter2", "mdp 1234", "clé API sk-123", "token du compte",
                         "ab" * 13, "x" * 201, 12):
            with self.assertRaises(ValueError, msg=str(mauvaise)):
                etat.note_inscription(mauvaise)
        self.assertEqual(etat.note_inscription("pseudo.studio@exemple.org, offre Pro"), "pseudo.studio@exemple.org, offre Pro")
        self.assertIsNone(etat.note_inscription("   "))
        self.assertIsNone(etat.note_inscription(None))

    def test_est_inscrit_sauf_connecte(self):
        d = etat.vide()
        etat.inscrire(d, "tripo", True)
        etat.inscrire(d, "vox", True)
        d["connexions"]["vox"] = {"etat": "connecte"}
        d["connexions"]["tripo"] = {"etat": "declare"}     # vu dans l'environnement, pas confirmé : le compte compte
        self.assertTrue(etat.est_inscrit(d, "tripo"))
        self.assertFalse(etat.est_inscrit(d, "vox"))       # connecté : on l'appelle directement
        self.assertFalse(etat.est_inscrit(d, "autre"))
        self.assertFalse(etat.est_inscrit({"connexions": {}}, "tripo"))


if __name__ == "__main__":
    unittest.main()
