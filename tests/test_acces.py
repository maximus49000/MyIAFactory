"""Le bureau ouvert au téléphone : écouteurs distants, code d'association, cookie d'accès, révocation.

Un écouteur distant est simulé sur 127.0.0.1 (port libre) : aucune requête ne quitte la machine. Le fichier des
clés est dans un dossier temporaire."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from bureau import acces, serveur
from tests import copie_demo
from tests.test_serveur import SourceSimulee


def jamais():
    raise AssertionError("les adresses ne doivent pas être cherchées")


class Horloge:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class TestCles(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.chemin = Path(self._t.name) / "MyIAFactory" / "acces.json"
        self.horloge = Horloge()
        self.cles = acces.Cles(self.chemin, horloge=self.horloge)

    def test_cle_creee_et_gardee(self):
        c = self.cles.cle()
        self.assertGreaterEqual(len(c), 40)
        self.assertEqual(json.loads(self.chemin.read_text(encoding="utf-8")), {"cle": c})
        self.assertEqual(acces.Cles(self.chemin).cle(), c)
        self.assertTrue(self.cles.valide(c))
        for faux in (None, "", c[:-1], c + "x", 12):
            self.assertFalse(self.cles.valide(faux), faux)

    def test_code_sans_ambiguite(self):
        for _ in range(50):
            code = self.cles.code_association()
            self.assertEqual(len(code), 8)
            self.assertFalse(set(code) & set("0O1IL"), code)

    def test_code_usage_unique(self):
        code = self.cles.code_association()
        self.assertEqual(self.cles.echanger(code), self.cles.cle())
        self.assertIsNone(self.cles.echanger(code))

    def test_code_expire(self):
        code = self.cles.code_association()
        self.horloge.t += acces.DUREE_CODE_S + 1
        self.assertIsNone(self.cles.echanger(code))

    def test_revoquer(self):
        ancienne = self.cles.cle()
        code = self.cles.code_association()
        nouvelle = self.cles.revoquer()
        self.assertNotEqual(nouvelle, ancienne)
        self.assertFalse(self.cles.valide(ancienne))
        self.assertIsNone(self.cles.echanger(code))
        self.assertEqual(acces.Cles(self.chemin).cle(), nouvelle)

    def test_en_attente_ne_consomme_pas(self):
        code = self.cles.code_association()
        self.assertTrue(self.cles.en_attente(code))
        self.assertTrue(self.cles.en_attente(code.lower()))
        self.assertEqual(self.cles.echanger(code), self.cles.cle())
        self.assertFalse(self.cles.en_attente(code))
        code = self.cles.code_association()
        self.horloge.t += acces.DUREE_CODE_S + 1
        self.assertFalse(self.cles.en_attente(code))

    def test_en_attente_compte_les_rates(self):
        """La page du lien dit si un code vaut : elle compte les ratés comme l'échange (pas d'essais à volonté)."""
        code = self.cles.code_association()
        for _ in range(acces.ESSAIS_MAX):
            self.assertFalse(self.cles.en_attente("ZZZZZZZZ"))
        self.assertIsNone(self.cles.echanger(code))

    def test_trop_d_essais_annulent_les_codes(self):
        code = self.cles.code_association()
        for _ in range(acces.ESSAIS_MAX):
            self.assertIsNone(self.cles.echanger("ZZZZZZZZ"))
        self.assertIsNone(self.cles.echanger(code))

    def test_fichier_illisible_recree(self):
        self.chemin.parent.mkdir(parents=True)
        self.chemin.write_text("{pas du json", encoding="utf-8")
        c = acces.Cles(self.chemin).cle()
        self.assertGreaterEqual(len(c), 40)


class AvecBureauOuvert(unittest.TestCase):
    ACCES = {"tailscale": True}
    ENT = {"X-Bureau": "1", "Content-Type": "application/json"}

    def setUp(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        copie_demo(self.tmp / "demo")
        self.fichier = self.tmp / "bureau.json"
        d = {"projets": ["demo/reglages.json"]}
        if self.ACCES is not None:
            d["acces"] = self.ACCES
        self.fichier.write_text(json.dumps(d), encoding="utf-8")
        self.horloge = Horloge()
        self.cles = acces.Cles(self.tmp / "cles" / "acces.json", horloge=self.horloge)
        self.srv = serveur.creer(bureau=self.fichier, port=0, ouvrir=SourceSimulee(), cles=self.cles,
                                 adresses=self.adresses, port_distant=0)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.arreter)
        self.distant = self.srv.ecouteurs[0].server_address[1] if self.srv.ecouteurs else None

    def adresses(self):
        return {"tailscale": "127.0.0.1", "reseau_local": None}

    def arreter(self):
        self.srv.shutdown()
        self.srv.server_close()

    def req(self, methode, chemin, corps=None, entetes=None, port=None):
        port = port or self.distant
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request(methode, chemin, body=corps, headers=entetes or {})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r, data

    def local(self, methode, chemin, corps=None, entetes=None):
        return self.req(methode, chemin, corps, entetes, port=self.port)

    def echanger(self, code, origine=True):
        """Le bouton de la page d'association : un POST du formulaire, depuis la page elle-même."""
        ent = {"Content-Type": "application/x-www-form-urlencoded"}
        if origine:
            ent["Origin"] = f"http://127.0.0.1:{self.distant}"
        return self.req("POST", "/associer", f"code={code}".encode(), ent)

    def associer(self):
        r, _ = self.echanger(self.cles.code_association())
        self.assertEqual(r.status, 303)
        return r.getheader("Set-Cookie").split(";")[0]


class TestSansAcces(AvecBureauOuvert):
    ACCES = None

    def adresses(self):
        jamais()

    def test_sans_acces_un_seul_ecouteur(self):
        self.assertEqual(self.srv.ecouteurs, [])
        r, data = self.local("GET", "/api/acces")
        self.assertEqual(r.status, 200)
        self.assertEqual(json.loads(data)["adresses"], [])


class TestBureauOuvert(AvecBureauOuvert):
    def test_un_ecouteur_distant(self):
        self.assertEqual(len(self.srv.ecouteurs), 1)
        self.assertEqual(self.srv.distants, [{"genre": "tailscale", "url": f"http://127.0.0.1:{self.distant}"}])

    def test_distant_sans_cookie_401(self):
        for chemin in ("/", "/api/projets", "/api/etat", "/main.js"):
            r, data = self.req("GET", chemin)
            self.assertEqual(r.status, 401, chemin)
            self.assertIn("Scannez le QR code affiché sur l'ordinateur", data.decode("utf-8"))
            self.assertNotIn(b"projets", data)
        r, _ = self.req("GET", "/api/projets", entetes={"Cookie": "myiafactory_acces=faux"})
        self.assertEqual(r.status, 401)

    def test_lien_du_qr_ne_consomme_pas_le_code(self):
        """Essai réel : l'aperçu du lien par l'appareil photo ou une redirection depuis une autre appli ne doit pas
        coûter le code. Le lien montre une page avec un bouton ; le bouton (POST) fait l'échange."""
        code = self.cles.code_association()
        for _ in range(2):
            r, data = self.req("GET", f"/associer?code={code}")
            self.assertEqual(r.status, 200)
            self.assertIsNone(r.getheader("Set-Cookie"))
            page = data.decode("utf-8")
            self.assertIn('method="post"', page)
            self.assertIn(f'value="{code}"', page)
        self.assertEqual(self.echanger(code)[0].status, 303)

    def test_page_d_association_n_injecte_rien(self):
        r, data = self.req("GET", "/associer?code=%22%3E%3Cscript%3E")
        self.assertEqual(r.status, 401)
        self.assertNotIn(b"<script>", data)

    def test_echange_exige_l_origine(self):
        code = self.cles.code_association()
        self.assertEqual(self.echanger(code, origine=False)[0].status, 403)
        self.assertEqual(self.echanger(code)[0].status, 303)   # le code n'a pas été consommé par le refus

    def test_associer_pose_le_cookie(self):
        r, _ = self.echanger(self.cles.code_association())
        self.assertEqual(r.status, 303)
        self.assertEqual(r.getheader("Location"), "/")
        cookie = r.getheader("Set-Cookie")
        for attendu in (f"myiafactory_acces={self.cles.cle()}", "HttpOnly", "SameSite=Strict", "Path=/",
                        "Max-Age=31536000"):
            self.assertIn(attendu, cookie)
        r, data = self.req("GET", "/api/projets", entetes={"Cookie": cookie.split(";")[0]})
        self.assertEqual(r.status, 200)
        self.assertTrue(json.loads(data)["projets"])

    def test_code_usage_unique(self):
        code = self.cles.code_association()
        self.assertEqual(self.echanger(code)[0].status, 303)
        r, _ = self.echanger(code)
        self.assertEqual(r.status, 401)
        self.assertIsNone(r.getheader("Set-Cookie"))
        self.assertEqual(self.req("GET", f"/associer?code={code}")[0].status, 401)   # déjà servi : plus de page
        self.assertEqual(self.req("GET", "/associer")[0].status, 401)

    def test_code_expire(self):
        code = self.cles.code_association()
        self.horloge.t += acces.DUREE_CODE_S + 1
        r, _ = self.echanger(code)
        self.assertEqual(r.status, 401)
        self.assertIsNone(r.getheader("Set-Cookie"))

    def test_revoquer_invalide_les_cookies(self):
        cookie = self.associer()
        self.assertEqual(self.req("GET", "/api/projets", entetes={"Cookie": cookie})[0].status, 200)
        self.assertEqual(self.local("POST", "/api/acces/revoquer", b"{}", self.ENT)[0].status, 200)
        self.assertEqual(self.req("GET", "/api/projets", entetes={"Cookie": cookie})[0].status, 401)

    def test_revoquer_exige_l_en_tete(self):
        r, _ = self.local("POST", "/api/acces/revoquer", b"{}", {"Content-Type": "application/json"})
        self.assertEqual(r.status, 403)

    def test_host_inconnu_403(self):
        cookie = self.associer()
        for hote in ("evil.example.com", f"127.0.0.1:{self.port}", f"localhost:{self.distant}"):
            r, data = self.req("GET", "/api/projets", entetes={"Cookie": cookie, "Host": hote})
            self.assertEqual(r.status, 403, hote)
            self.assertNotIn(b"projets", data)

    def test_post_distant_sans_origin_403(self):
        cookie = self.associer()
        corps = json.dumps({"type": "inconnu"}).encode("utf-8")
        for origine in (None, "http://evil.example.com", f"http://127.0.0.1:{self.port}"):
            entetes = {**self.ENT, "Cookie": cookie}
            if origine:
                entetes["Origin"] = origine
            r, _ = self.req("POST", "/api/demande", corps, entetes)
            self.assertEqual(r.status, 403, origine)
        r, _ = self.req("POST", "/api/demande", corps,
                        {**self.ENT, "Cookie": cookie, "Origin": f"http://127.0.0.1:{self.distant}"})
        self.assertNotIn(r.status, (401, 403))
        r, _ = self.req("POST", "/api/demande", corps, {**self.ENT, "Origin": f"http://127.0.0.1:{self.distant}"})
        self.assertEqual(r.status, 401)

    def test_api_acces_jamais_a_distance(self):
        cookie = self.associer()
        r, data = self.req("GET", "/api/acces", entetes={"Cookie": cookie})
        self.assertEqual(r.status, 404)
        self.assertNotIn(b"code", data)
        r, _ = self.req("POST", "/api/acces/revoquer", b"{}",
                        {**self.ENT, "Cookie": cookie, "Origin": f"http://127.0.0.1:{self.distant}"})
        self.assertEqual(r.status, 404)
        self.assertTrue(self.cles.valide(cookie.split("=", 1)[1]))

    def test_api_acces_en_local(self):
        r, data = self.local("GET", "/api/acces")
        self.assertEqual(r.status, 200)
        d = json.loads(data)
        self.assertEqual(d["adresses"], [{"genre": "tailscale", "url": f"http://127.0.0.1:{self.distant}"}])
        self.assertEqual(len(d["code"]), 8)
        self.assertTrue(d["expire"])
        self.assertNotEqual(json.loads(self.local("GET", "/api/acces")[1])["code"], d["code"])
        self.assertEqual(self.echanger(d["code"])[0].status, 303)

    def test_local_sans_cookie_inchange(self):
        self.assertEqual(self.local("GET", "/api/projets")[0].status, 200)
        self.assertEqual(self.local("GET", "/associer?code=x")[0].status, 404)


class TestAdresseIntrouvable(AvecBureauOuvert):
    ACCES = {"tailscale": True, "reseau_local": True}

    def adresses(self):
        return {"tailscale": None, "reseau_local": "127.0.0.1"}

    def test_adresse_introuvable_ignoree(self):
        self.assertEqual([d["genre"] for d in self.srv.distants], ["reseau_local"])
        self.assertTrue(any("Tailscale" in a for a in self.srv.annonces), self.srv.annonces)


class TestUnProjet(unittest.TestCase):
    def test_reglages_un_projet_jamais_distant(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
            copie_demo(Path(t) / "demo")
            srv = serveur.creer(Path(t) / "demo" / "reglages.json", port=0, ouvrir=SourceSimulee(),
                                adresses=jamais, port_distant=0)
            try:
                self.assertEqual(srv.ecouteurs, [])
            finally:
                srv.server_close()


if __name__ == "__main__":
    unittest.main()
