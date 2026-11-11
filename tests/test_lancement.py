import json
import tempfile
import unittest
from pathlib import Path

from bureau.lancement import Drapeau
from tests.test_acces import AvecBureauOuvert


class TestDrapeau(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)

    def test_en_memoire(self):
        d = Drapeau(None)
        self.assertFalse(d.vu())
        d.marquer()
        self.assertTrue(d.vu())

    def test_fichier(self):
        chemin = self.tmp / "x" / "lancement.json"
        d = Drapeau(chemin)
        self.assertFalse(d.vu())
        d.marquer()
        self.assertTrue(d.vu())
        self.assertEqual(json.loads(chemin.read_text(encoding="utf-8")), {"vu": True})
        self.assertTrue(Drapeau(chemin).vu())

    def test_fichier_illisible_vaut_pas_vu(self):
        chemin = self.tmp / "lancement.json"
        for contenu in ("{", "[]", '{"vu": "oui"}', ""):
            with self.subTest(contenu):
                chemin.write_text(contenu, encoding="utf-8")
                self.assertFalse(Drapeau(chemin).vu())

    def test_marquer_ne_leve_pas_si_ecriture_impossible(self):
        bloque = self.tmp / "fichier"
        bloque.write_text("", encoding="utf-8")
        d = Drapeau(bloque / "lancement.json")   # le parent est un fichier : écriture impossible
        d.marquer()
        self.assertTrue(d.vu())   # retenu au moins en mémoire jusqu'à l'arrêt du serveur


class TestLancementADistance(AvecBureauOuvert):
    """Le premier lancement vaut aussi pour le téléphone associé, avec les gardes habituelles (cookie, origine)."""

    def test_gardes(self):
        self.assertEqual(self.req("GET", "/api/lancement")[0].status, 401)
        cookie = f"myiafactory_acces={self.cles.cle()}"
        r, data = self.req("GET", "/api/lancement", entetes={"Cookie": cookie})
        self.assertEqual((r.status, json.loads(data)), (200, {"vu": False}))
        r, _ = self.req("POST", "/api/lancement", b"{}", {**self.ENT, "Cookie": cookie, "Origin": "http://evil.example.com"})
        self.assertEqual(r.status, 403)
        self.assertFalse(self.srv.lancement.vu())
        r, _ = self.req("POST", "/api/lancement", b"{}",
                        {**self.ENT, "Cookie": cookie, "Origin": f"http://127.0.0.1:{self.distant}"})
        self.assertEqual(r.status, 200)
        self.assertTrue(self.srv.lancement.vu())


if __name__ == "__main__":
    unittest.main()
