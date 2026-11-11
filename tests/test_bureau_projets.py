"""Essai réel : un seul bureau pour tous les projets ; un projet inscrit pendant qu'il tourne apparaît sans redémarrage."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from bureau import serveur
from tests import copie_demo
from tests.test_serveur import SourceSimulee


class TestProjetsSansRedemarrage(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        copie_demo(self.tmp / "a")
        copie_demo(self.tmp / "b")
        self.fichier = self.tmp / "bureau.json"
        self.ecrire(["a/reglages.json"])
        self.srv = serveur.creer(bureau=self.fichier, port=0, ouvrir=SourceSimulee())
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close()))

    def ecrire(self, projets):
        self.fichier.write_text(json.dumps({"projets": projets}), encoding="utf-8")

    def ids(self):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=30)
        c.request("GET", "/api/projets")
        r = json.loads(c.getresponse().read())
        c.close()
        return [p["id"] for p in r["projets"]]

    def test_un_projet_inscrit_apparait(self):
        self.assertEqual(len(self.ids()), 1)
        self.ecrire(["a/reglages.json", "b/reglages.json"])
        self.srv.projets_vus_a = 0   # le fichier a pu changer dans la même seconde que sa première lecture
        ids = self.ids()
        self.assertEqual(len(ids), 2)
        self.assertIsNotNone(self.srv.projet(ids[1]))

    def test_fichier_illisible_garde_les_projets(self):
        self.fichier.write_text("{abîmé", encoding="utf-8")
        self.srv.projets_vus_a = 0
        self.assertEqual(len(self.ids()), 1)


if __name__ == "__main__":
    unittest.main()
