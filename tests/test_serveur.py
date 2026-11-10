import http.client
import io
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from bureau import serveur

RACINE = Path(__file__).resolve().parent.parent


class TestServeur(unittest.TestCase):
    ENT = {"X-Bureau": "1", "Content-Type": "application/json"}

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        shutil.copytree(RACINE / "exemples" / "demo", self.tmp / "demo")
        self.regl = self.tmp / "demo" / "reglages.json"
        self.srv = serveur.creer(self.regl, port=0)
        self.port = self.srv.server_address[1]
        self.fil = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.fil.start()
        self.addCleanup(self.arreter)

    def arreter(self):
        self.srv.shutdown()
        self.srv.server_close()

    def req(self, methode, chemin, corps=None, entetes=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(methode, chemin, body=corps, headers=entetes or {})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r, data

    def json(self, chemin):
        r, data = self.req("GET", chemin)
        self.assertEqual(r.status, 200)
        return json.loads(data.decode("utf-8"))

    def test_ecoute_seulement_en_local(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")

    def test_etat(self):
        e = self.json("/api/etat")
        self.assertEqual(e["projet"], "Démo")
        self.assertIsNone(e["erreur"])

    def test_etat_releve_casse(self):
        self.json("/api/etat")
        (self.tmp / "demo" / "releve.json").write_text("{", encoding="utf-8")
        time.sleep(2.1)
        e = self.json("/api/etat")
        self.assertTrue(e["erreur"])

    def test_etat_servi_pendant_une_lecture_lente(self):
        # Pendant qu'une commande de relevé lente tourne, /api/etat rend le dernier état sans attendre.
        self.json("/api/etat")
        regl = json.loads(self.regl.read_text(encoding="utf-8"))
        regl["releve"] = {"commande": [sys.executable, "-c", "import time; time.sleep(4)"]}
        self.regl.write_text(json.dumps(regl), encoding="utf-8")
        self.srv._cache_etat = (0.0, self.srv._cache_etat[1])  # état périmé : la prochaine demande relit
        lent = threading.Thread(target=self.srv.etat, daemon=True)
        lent.start()
        time.sleep(0.5)
        debut = time.monotonic()
        e = self.json("/api/etat")
        self.assertLess(time.monotonic() - debut, 1.5)
        self.assertEqual(e["projet"], "Démo")
        lent.join(10)

    def test_charge(self):
        c = self.json("/api/charge")
        for cle in ("disponible", "cpu", "memoire", "charge", "max", "feu_vert", "coeurs", "memoire_totale_go"):
            self.assertIn(cle, c)
        self.assertEqual(c["max"], 75)

    def test_conseil(self):
        c = self.json("/api/conseil")
        self.assertTrue(40 <= c["valeur"] <= 85)

    def test_reglage(self):
        r, data = self.req("POST", "/api/reglages", json.dumps({"charge_max": 60}), self.ENT)
        self.assertEqual(r.status, 200)
        self.assertEqual(json.loads(data.decode("utf-8"))["charge_max"], 60)
        self.assertEqual(self.json("/api/charge")["max"], 60)
        d = json.loads(self.regl.read_text(encoding="utf-8"))
        self.assertEqual(d["charge_max"], 60)
        self.assertIn("releve", d)

    def test_reglage_sans_entete(self):
        avant = self.regl.read_text(encoding="utf-8")
        corps = json.dumps({"charge_max": 60})
        r, _ = self.req("POST", "/api/reglages", corps, {"Content-Type": "application/json"})
        self.assertEqual(r.status, 403)
        r, _ = self.req("POST", "/api/reglages", corps, {"X-Bureau": "1"})
        self.assertEqual(r.status, 403)
        self.assertEqual(self.regl.read_text(encoding="utf-8"), avant)

    def test_reglage_invalide(self):
        for corps in ('{"charge_max": 200}', '{"charge_max": "70"}', "pas du json", "[]"):
            r, data = self.req("POST", "/api/reglages", corps, self.ENT)
            self.assertEqual(r.status, 400, corps)
            self.assertIn("erreur", json.loads(data.decode("utf-8")))

    def test_hote_etranger_refuse(self):
        r, _ = self.req("GET", "/api/etat", entetes={"Host": "evil.example.com"})
        self.assertEqual(r.status, 403)

    def test_page(self):
        r, _ = self.req("GET", "/")
        self.assertEqual(r.status, 200)
        self.assertTrue(r.getheader("Content-Type").startswith("text/html"))
        self.assertEqual(r.getheader("Cache-Control"), "no-store")

    def test_pas_de_sortie_du_dossier(self):
        for chemin in ("/../reglages.py", "/%2e%2e/lancer.py", "/..%5c..%5clancer.py", "/../../lancer.py",
                       "/%2e%2e/%2e%2e/lancer.py"):
            r, _ = self.req("GET", chemin)
            self.assertEqual(r.status, 404, chemin)

    def test_inconnu(self):
        r, _ = self.req("GET", "/nexiste/pas.js")
        self.assertEqual(r.status, 404)

    def test_commande_charge(self):
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            code = serveur.main(["charge", "--reglages", str(self.regl)])
        self.assertIn(code, (0, 1))
        self.assertIn("charge", sortie.getvalue())


if __name__ == "__main__":
    unittest.main()
