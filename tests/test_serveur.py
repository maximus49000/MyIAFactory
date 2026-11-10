import http.client
import io
import json
import os
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

    # -- les images --------------------------------------------------------
    PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489")

    def images(self, racines=("images",)):
        dossier = self.tmp / "demo"
        (dossier / "images").mkdir(exist_ok=True)
        (dossier / "images" / "a b&c#d.png").write_bytes(self.PNG)
        (dossier / "images" / "photo.JPG").write_bytes(bytes.fromhex("ffd8ffe0") + b"jpeg")
        (dossier / "images" / "notes.txt").write_text("secret", encoding="utf-8")
        (self.tmp / "secret.png").write_bytes(b"secret")
        (dossier / "secret.png").write_bytes(b"secret")
        regl = json.loads(self.regl.read_text(encoding="utf-8"))
        regl["images"] = {"racines": list(racines)}
        self.regl.write_text(json.dumps(regl), encoding="utf-8")

    def image(self, chemin):
        return self.req("GET", "/api/image?chemin=" + chemin)

    def test_image_servie(self):
        self.images()
        r, data = self.image("images/a%20b%26c%23d.png")
        self.assertEqual((r.status, data), (200, self.PNG))
        self.assertEqual(r.getheader("Content-Type"), "image/png")
        self.assertEqual(r.getheader("Cache-Control"), "max-age=300")
        r, data = self.image("images/photo.JPG")
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "image/jpeg"))

    def test_image_hors_racine_refusee(self):
        self.images()
        absolu = str(self.tmp / "demo" / "secret.png").replace("\\", "/")
        for chemin in ("../secret.png", "images/../../secret.png", "..%2Fsecret.png", "images/..%5C..%5Csecret.png",
                       "secret.png", absolu, "/etc/passwd", "images/notes.txt", "images", "images/inconnue.png",
                       "images/a.png%00.txt", "images/a%00.png", "", "images/%2e%2e/%2e%2e/secret.png"):
            r, data = self.image(chemin)
            self.assertEqual(r.status, 404, chemin)
            self.assertNotIn(b"secret", data, chemin)

    def test_image_lien_symbolique_sortant(self):
        self.images()
        try:
            os.symlink(self.tmp / "secret.png", self.tmp / "demo" / "images" / "lien.png")
        except (OSError, NotImplementedError):
            self.skipTest("création de lien symbolique non permise")
        r, data = self.image("images/lien.png")
        self.assertEqual(r.status, 404)
        self.assertNotIn(b"secret", data)

    def test_image_sans_reglage(self):
        self.images()
        regl = json.loads(self.regl.read_text(encoding="utf-8"))
        del regl["images"]
        self.regl.write_text(json.dumps(regl), encoding="utf-8")
        r, _ = self.image("images/photo.JPG")
        self.assertEqual(r.status, 404)

    def test_image_hote_etranger(self):
        self.images()
        r, _ = self.req("GET", "/api/image?chemin=images/photo.JPG", entetes={"Host": "evil.example.com"})
        self.assertEqual(r.status, 403)

    # -- les demandes ------------------------------------------------------
    RELEVE_V2 = {
        "version": 2, "projet": "P", "factory": {"etat": "en marche"},
        "services": [{"id": "dev", "nom": "Dev"}],
        "colonnes": [{"id": "a", "nom": "A"}, {"id": "b", "nom": "B"}],
        "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}],
        "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"}],
        "actions": [{"id": "pause", "libelle": "Pause"}],
        "lecons": [{"id": "d1:L1", "agent": "d1", "texte": "t"}]}

    SCRIPT_ACTIONS = (
        "import sys, time\n"
        "d = sys.stdin.buffer.read()\n"
        "f = open(sys.argv[1], 'ab')\n"
        "f.write(b'debut\\n'); f.flush()\n"
        "time.sleep(float(sys.argv[2]))\n"
        "f.write(d + b'\\nfin\\n'); f.flush()\n"
        "sys.exit(int(sys.argv[3]))\n")

    def agir(self, duree=0.0, code=0, releve=None):
        """Installe un relevé v2 et une commande d'actions qui note ses demandes dans `notes.log`."""
        dossier = self.tmp / "demo"
        (dossier / "releve.json").write_text(json.dumps(releve or self.RELEVE_V2), encoding="utf-8")
        (dossier / "actions.py").write_text(self.SCRIPT_ACTIONS, encoding="utf-8")
        regl = json.loads(self.regl.read_text(encoding="utf-8"))
        regl["actions"] = {"commande": [sys.executable, "actions.py", "notes.log", str(duree), str(code)],
                           "dossier": "."}
        self.regl.write_text(json.dumps(regl), encoding="utf-8")
        self.srv._cache_etat = (0.0, None)
        return dossier / "notes.log"

    def demande(self, d):
        r, data = self.req("POST", "/api/demande", json.dumps(d), self.ENT)
        return r.status, json.loads(data.decode("utf-8"))

    def test_etat_agir(self):
        self.assertIs(self.json("/api/etat")["agir"], True)  # la démonstration déclare une commande d'actions
        regl = json.loads(self.regl.read_text(encoding="utf-8"))
        del regl["actions"]
        self.regl.write_text(json.dumps(regl), encoding="utf-8")
        self.srv._cache_etat = (0.0, None)
        self.assertIs(self.json("/api/etat")["agir"], False)
        self.agir()
        e = self.json("/api/etat")
        self.assertIs(e["agir"], True)
        self.assertEqual(e["version"], 2)

    def test_demande_sans_entete(self):
        notes = self.agir()
        self.json("/api/etat")
        corps = json.dumps({"type": "bouton", "id": "pause"})
        for entetes in ({"Content-Type": "application/json"}, {"X-Bureau": "1"},
                        {"X-Bureau": "1", "Content-Type": "text/plain"}):
            r, _ = self.req("POST", "/api/demande", corps, entetes)
            self.assertEqual(r.status, 403)
        r, _ = self.req("POST", "/api/demande", corps, {**self.ENT, "Host": "evil.example.com"})
        self.assertEqual(r.status, 403)
        self.assertFalse(notes.exists())

    def test_demande_ok(self):
        notes = self.agir()
        self.json("/api/etat")
        statut, corps = self.demande({"type": "bouton", "id": "pause"})
        self.assertEqual((statut, corps), (200, {"ok": True}))
        lignes = notes.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lignes[0], "debut")
        self.assertEqual(json.loads(lignes[1])["id"], "pause")

    def test_demande_nettoyee(self):
        notes = self.agir()
        self.json("/api/etat")
        self.demande({"type": "bouton", "id": "pause", "mauvais": "champ"})
        self.assertNotIn("mauvais", notes.read_text(encoding="utf-8"))

    def test_demande_inconnue(self):
        notes = self.agir()
        self.json("/api/etat")
        for d in ({"type": "bouton", "id": "inconnu"}, {"type": "deplacer", "tache": "zz", "colonne": "a"},
                  {"type": "deplacer", "tache": "t1", "colonne": "zz"},
                  {"type": "retour", "tache": "t1", "texte": " "}, {"type": "lecon", "id": "x", "verdict": "valider"},
                  {"type": "inconnu"}, [], "x"):
            statut, corps = self.demande(d)
            self.assertEqual(statut, 400, d)
            self.assertTrue(corps["erreur"])
        for brut in ("pas du json", ""):
            r, _ = self.req("POST", "/api/demande", brut, self.ENT)
            self.assertEqual(r.status, 400)
        r, _ = self.req("POST", "/api/demande", "x" * 9000, self.ENT)
        self.assertEqual(r.status, 400)
        self.assertFalse(notes.exists())

    def test_demande_sans_releve_valide(self):
        self.agir()
        (self.tmp / "demo" / "releve.json").write_text("{", encoding="utf-8")
        statut, corps = self.demande({"type": "bouton", "id": "pause"})
        self.assertEqual((statut, corps), (409, {"erreur": "Relevé indisponible."}))

    def test_demande_commande_en_echec(self):
        notes = self.agir(code=3)
        self.json("/api/etat")
        statut, corps = self.demande({"type": "bouton", "id": "pause"})
        self.assertEqual(statut, 502)
        self.assertTrue(corps["erreur"])
        self.assertTrue(notes.exists())
        self.assertEqual(self.json("/api/etat")["projet"], "P")  # le serveur reste disponible

    def test_demande_sans_commande(self):
        self.agir()
        regl = json.loads(self.regl.read_text(encoding="utf-8"))
        del regl["actions"]
        self.regl.write_text(json.dumps(regl), encoding="utf-8")
        self.json("/api/etat")
        statut, corps = self.demande({"type": "bouton", "id": "pause"})
        self.assertEqual(statut, 502)
        self.assertIn("Aucune commande", corps["erreur"])

    def test_demande_vide_le_cache_d_etat(self):
        self.agir()
        self.json("/api/etat")
        self.demande({"type": "bouton", "id": "pause"})
        self.assertEqual(self.srv._cache_etat[0], 0.0)

    def test_demandes_successives(self):
        notes = self.agir(duree=0.3)
        self.json("/api/etat")
        resultats = []

        def envoyer(i):
            resultats.append(self.demande({"type": "retour", "tache": "t1", "texte": f"n{i}"})[0])

        fils = [threading.Thread(target=envoyer, args=(i,)) for i in range(2)]
        for f in fils:
            f.start()
        for f in fils:
            f.join(20)
        self.assertEqual(resultats, [200, 200])
        lignes = notes.read_text(encoding="utf-8").splitlines()
        self.assertEqual([x for x in lignes if x in ("debut", "fin")], ["debut", "fin", "debut", "fin"])
        self.assertEqual(sum(1 for x in lignes if x.startswith("{")), 2)


if __name__ == "__main__":
    unittest.main()
