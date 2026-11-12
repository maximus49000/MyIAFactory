"""La fenêtre de validation, côté bureau : le téléchargement d'un livrable (`/api/telecharger`) et le relais vers le site
en cours (`/apercu/<projet>/<décision>/…`). Le « site » est un petit serveur local lancé par le test ; aucune requête ne
quitte la machine."""
import copy
import http.client
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bureau import serveur
from tests import copie_demo
from tests.test_acces import AvecBureauOuvert
from tests.test_bureau_multi import RELEVE
from tests.test_serveur import AvecServeur, TestServeur

VUS = []


class Site(BaseHTTPRequestHandler):
    """Le site en cours de développement : une page, des redirections, un cookie, l'écho de ce qu'il reçoit."""

    def log_message(self, *a):
        pass

    def _repondre(self, code, corps=b"", entetes=()):
        self.send_response(code)
        for k, v in entetes:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corps)

    def do_GET(self):
        VUS.append((self.command, self.path, dict(self.headers)))
        port = self.server.server_address[1]
        if self.path == "/":
            return self._repondre(200, b"<html>Accueil</html>", [("Content-Type", "text/html"),
                                                                 ("Set-Cookie", "session=1"),
                                                                 ("Content-Security-Policy", "default-src 'none'")])
        if self.path == "/redir-racine":
            return self._repondre(302, entetes=[("Location", "/connexion?x=1")])
        if self.path == "/redir-absolue":
            return self._repondre(302, entetes=[("Location", f"http://127.0.0.1:{port}/tableau")])
        if self.path == "/redir-ailleurs":
            return self._repondre(302, entetes=[("Location", "https://exemple.fr/")])
        return self._repondre(200, json.dumps({"chemin": self.path}).encode(), [("Content-Type", "application/json")])

    do_HEAD = do_GET

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        corps = self.rfile.read(n)
        VUS.append((self.command, self.path, dict(self.headers)))
        self._repondre(200, b"recu:" + corps, [("Content-Type", "text/plain")])


def lancer_site(test):
    site = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    test.addCleanup(site.server_close)
    test.addCleanup(site.shutdown)
    return site.server_address[1]


def releve_avec(port, fichiers, documents=(), url=None):
    r = copy.deepcopy(RELEVE)
    r["fonctionnalites"][0]["documents"] = list(documents)
    r["decisions_projet"] = [{"id": "v1", "genre": "valider_etape", "texte": "Valider ?", "fonctionnalite": "f1",
                              "element": {"id": "e1", "nom": "Jeu"}, "etape": "a", "tache": "t1",
                              "compte_rendu": "", "fichiers": list(fichiers),
                              "acces": {"url": url or f"http://127.0.0.1:{port}/", "description": "Le site"}}]
    return r


class TestTelecharger(AvecServeur):
    SCRIPT_ACTIONS = TestServeur.SCRIPT_ACTIONS
    agir = TestServeur.agir

    def setUp(self):
        super().setUp()
        self.dossier = self.tmp / "demo"

    def ecrire(self, chemin, octets=b"PK\x03\x04apk"):
        f = self.dossier / chemin
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(octets)
        return f

    def preparer(self, fichiers=(), documents=(), racines=None, url=None):
        self.agir(releve=releve_avec(1, fichiers, documents, url))
        if racines is not None:
            regl = json.loads(self.regl.read_text(encoding="utf-8"))
            regl["livrables"] = {"racines": list(racines)}
            self.regl.write_text(json.dumps(regl), encoding="utf-8")
            self.p._cache_etat = (0.0, None)

    def url(self, chemin, fonctionnalite="f1"):
        from urllib.parse import quote
        return f"/api/telecharger?fonctionnalite={fonctionnalite}&chemin={quote(chemin)}"

    def test_apk_declare_par_la_decision_en_piece_jointe(self):
        self.ecrire("build/jeu.apk")
        self.preparer(fichiers=[{"chemin": "build/jeu.apk", "titre": "APK"}])
        r, data = self.req("GET", self.url("build/jeu.apk"))
        self.assertEqual((r.status, data), (200, b"PK\x03\x04apk"))
        self.assertEqual(r.getheader("Content-Type"), "application/vnd.android.package-archive")
        self.assertTrue(r.getheader("Content-Disposition").startswith("attachment"))
        self.assertIn('filename="jeu.apk"', r.getheader("Content-Disposition"))
        self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(r.getheader("Content-Length"), "7")
        r, data = self.req("HEAD", self.url("build/jeu.apk"))
        self.assertEqual((r.status, data), (200, b""))
        r, _ = self.req("GET", self.url("build/jeu.apk", "f9"))     # déclaré pour une autre fonctionnalité : non
        self.assertEqual(r.status, 404)

    def test_livrable_de_la_fonctionnalite_et_racines(self):
        self.ecrire("sorties/livre.pdf", b"%PDF")
        self.ecrire("livrables/f1/paquet.zip", b"PK")
        self.ecrire("sorties/pas-declare.zip", b"PK")
        self.preparer(documents=[{"chemin": "sorties/livre.pdf", "titre": "Livre", "livrable": True},
                                 {"chemin": "sorties/pas-declare.zip", "titre": "Pas un livrable"}],
                      racines=["livrables"])
        r, data = self.req("GET", self.url("sorties/livre.pdf"))
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "application/pdf"))
        self.assertTrue(r.getheader("Content-Disposition").startswith("attachment"))
        r, data = self.req("GET", self.url("livrables/f1/paquet.zip"))      # sous une racine de livrables
        self.assertEqual((r.status, data), (200, b"PK"))
        r, _ = self.req("GET", self.url("sorties/pas-declare.zip"))         # un document qui n'est pas un livrable
        self.assertEqual(r.status, 404)

    def test_refus(self):
        """Jamais un fichier quelconque : ni hors des déclarés et des racines, ni hors du projet, ni « .. », ni chemin
        absolu, ni extension non téléchargeable, ni `.git`."""
        (self.tmp / "dehors.apk").write_bytes(b"PK")
        self.ecrire("reglages-copie.json", b"{}")
        self.ecrire(".git/objets.zip", b"PK")
        self.ecrire("build/jeu.apk")
        absolu = str(self.dossier / "build" / "jeu.apk")
        self.preparer(fichiers=[{"chemin": c, "titre": "x"} for c in (
            "../dehors.apk", "build/../build/jeu.apk", "reglages-copie.json", ".git/objets.zip", absolu,
            "build\\..\\..\\dehors.apk", "C:dehors.apk", "build/absent.apk")], racines=["livrables"])
        for chemin in ("../dehors.apk", "build/../build/jeu.apk", "reglages-copie.json", ".git/objets.zip", absolu,
                       "build\\..\\..\\dehors.apk", "C:dehors.apk", "build/absent.apk", "build/jeu.apk", "",
                       "reglages.json", "/etc/passwd", "build/jeu.apk\x00.png"):
            r, _ = self.req("GET", self.url(chemin))
            self.assertEqual(r.status, 404, chemin)
        r, _ = self.req("GET", "/api/telecharger?fonctionnalite=f1")
        self.assertEqual(r.status, 404)

    def test_lien_qui_sort_du_projet(self):
        (self.tmp / "dehors.apk").write_bytes(b"PK")
        lien = self.dossier / "build" / "lien.apk"
        lien.parent.mkdir(parents=True)
        try:
            os.symlink(self.tmp / "dehors.apk", lien)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles sur ce poste")
        self.preparer(fichiers=[{"chemin": "build/lien.apk", "titre": "Lien"}], racines=["build"])
        r, _ = self.req("GET", self.url("build/lien.apk"))
        self.assertEqual(r.status, 404)

    def test_son_lu_dans_la_page_sans_piece_jointe(self):
        """`lecture=1` sert un son déclaré avec son type, sans pièce jointe, par tranches (le téléphone en a besoin) ;
        mêmes gardes que le téléchargement ; un non-son reste une pièce jointe."""
        self.ecrire("sons/coup.mp3", b"0123456789")
        self.ecrire("sons/chant.flac", b"fLaC0123")
        self.ecrire("sons/hors.ogg", b"OggS")
        self.ecrire("build/jeu.apk")
        self.preparer(fichiers=[{"chemin": c, "titre": "x"} for c in ("sons/coup.mp3", "sons/chant.flac", "build/jeu.apk")])
        r, data = self.req("GET", self.url("sons/coup.mp3") + "&lecture=1")
        self.assertEqual((r.status, data, r.getheader("Content-Type")), (200, b"0123456789", "audio/mpeg"))
        self.assertIsNone(r.getheader("Content-Disposition"))
        self.assertEqual((r.getheader("Accept-Ranges"), r.getheader("X-Content-Type-Options")), ("bytes", "nosniff"))
        r, data = self.req("GET", self.url("sons/chant.flac") + "&lecture=1")
        self.assertEqual((r.status, r.getheader("Content-Type"), r.getheader("Content-Disposition")), (200, "audio/flac", None))
        r, _ = self.req("GET", self.url("sons/coup.mp3"))                   # sans lecture : la pièce jointe d'avant
        self.assertTrue(r.getheader("Content-Disposition").startswith("attachment"))
        r, data = self.req("GET", self.url("sons/coup.mp3") + "&lecture=1", entetes={"Range": "bytes=2-4"})
        self.assertEqual((r.status, data, r.getheader("Content-Range")), (206, b"234", "bytes 2-4/10"))
        r, data = self.req("GET", self.url("sons/coup.mp3") + "&lecture=1", entetes={"Range": "bytes=7-"})
        self.assertEqual((r.status, data, r.getheader("Content-Range")), (206, b"789", "bytes 7-9/10"))
        r, data = self.req("GET", self.url("sons/coup.mp3") + "&lecture=1", entetes={"Range": "bytes=-3"})
        self.assertEqual((r.status, data), (206, b"789"))
        r, _ = self.req("GET", self.url("sons/coup.mp3") + "&lecture=1", entetes={"Range": "bytes=50-60"})
        self.assertEqual((r.status, r.getheader("Content-Range")), (416, "bytes */10"))
        r, data = self.req("GET", self.url("sons/coup.mp3") + "&lecture=1", entetes={"Range": "n'importe quoi"})
        self.assertEqual((r.status, data), (200, b"0123456789"))
        r, _ = self.req("GET", self.url("build/jeu.apk") + "&lecture=1")    # pas un son : toujours en pièce jointe
        self.assertTrue(r.getheader("Content-Disposition").startswith("attachment"))
        r, _ = self.req("GET", self.url("sons/hors.ogg") + "&lecture=1")    # non déclaré : mêmes gardes
        self.assertEqual(r.status, 404)
        r, _ = self.req("GET", self.url("../x.mp3") + "&lecture=1")
        self.assertEqual(r.status, 404)

    def reponse(self, decision="v1", verdict="valider"):
        r, data = self.req("POST", "/api/demande", json.dumps({"type": "valider_etape", "decision": decision,
                                                                "verdict": verdict}), TestServeur.ENT)
        return r.status, json.loads(data.decode("utf-8"))

    def test_une_seule_reponse_par_validation(self):
        """Une validation déjà répondue (le moteur la traite encore, ou elle est levée) refuse une deuxième réponse, valider
        ou renvoyer : 409, la commande d'actions n'est lancée qu'une fois."""
        self.ecrire("build/jeu.apk")
        notes = self.agir(releve=releve_avec(1, [{"chemin": "build/jeu.apk", "titre": "APK"}]))
        self.assertEqual(self.reponse(), (200, {"ok": True}))
        statut, corps = self.reponse()                                  # le relevé la montre encore : le moteur n'a pas fini
        self.assertEqual(statut, 409)
        self.assertIn("déjà", corps["erreur"])
        self.assertEqual(self.reponse(verdict="renvoyer")[0], 409)
        r = json.loads((self.dossier / "releve.json").read_text(encoding="utf-8"))
        r["decisions_projet"] = []                                      # le moteur l'a levée : toujours refusée, en 409
        (self.dossier / "releve.json").write_text(json.dumps(r), encoding="utf-8")
        self.p._cache_etat = (0.0, None)
        self.assertEqual(self.reponse()[0], 409)
        self.assertEqual(notes.read_text(encoding="utf-8").count("valider_etape"), 1)

    def test_reponse_refusee_par_la_commande_peut_etre_refaite(self):
        self.agir(code=3, releve=releve_avec(1, []))
        self.assertEqual(self.reponse()[0], 502)
        self.assertEqual(self.reponse()[0], 502)          # rien n'a été pris : pas de 409

    def test_trop_gros(self):
        self.ecrire("build/jeu.apk")
        self.preparer(fichiers=[{"chemin": "build/jeu.apk", "titre": "APK"}])
        avant = serveur.TELECHARGEMENT_MAX_OCTETS
        serveur.TELECHARGEMENT_MAX_OCTETS = 4
        self.addCleanup(setattr, serveur, "TELECHARGEMENT_MAX_OCTETS", avant)
        r, data = self.req("GET", self.url("build/jeu.apk"))
        self.assertEqual(r.status, 413)
        self.assertEqual(avant, 500 * 1024 * 1024)

    def test_reglages_dans_factory_projet_a_la_racine(self):
        """Un vrai projet : les réglages dans `.factory`, l'apk construit à la racine du projet."""
        jeu = self.tmp / "jeu"
        copie_demo(jeu / ".factory")
        self.regl = jeu / ".factory" / "reglages.json"
        self.redemarrer()
        self.dossier = jeu / ".factory"
        (jeu / "build").mkdir()
        (jeu / "build" / "jeu.apk").write_bytes(b"PK")
        (jeu / ".git").mkdir()
        (jeu / ".git" / "x.zip").write_bytes(b"PK")
        r = releve_avec(1, [{"chemin": "build/jeu.apk", "titre": "APK"}, {"chemin": ".git/x.zip", "titre": "x"}])
        (self.dossier / "releve.json").write_text(json.dumps(r), encoding="utf-8")
        self.p._cache_etat = (0.0, None)
        r, data = self.req("GET", self.url("build/jeu.apk"))
        self.assertEqual((r.status, data), (200, b"PK"))
        r, _ = self.req("GET", self.url(".git/x.zip"))
        self.assertEqual(r.status, 404)


class TestApercu(AvecServeur):
    SCRIPT_ACTIONS = TestServeur.SCRIPT_ACTIONS
    agir = TestServeur.agir

    def setUp(self):
        super().setUp()
        VUS.clear()
        self.site = lancer_site(self)
        self.agir(releve=releve_avec(self.site, []))

    def test_page_relayee_sans_cookie_ni_politique(self):
        r, data = self.req("GET", "/apercu/-/v1/", entetes={"Cookie": "myiafactory_acces=secret; autre=1",
                                                           "Origin": "http://x", "X-Bureau": "1",
                                                           "Accept-Encoding": "gzip", "Accept": "text/html"})
        self.assertEqual((r.status, data), (200, b"<html>Accueil</html>"))
        self.assertEqual(r.getheader("Content-Type"), "text/html")
        self.assertIsNone(r.getheader("Set-Cookie"))
        self.assertIsNone(r.getheader("Content-Security-Policy"))
        (_, chemin, recus), = VUS
        self.assertEqual(chemin, "/")
        recus = {k.lower(): v for k, v in recus.items()}
        for absent in ("cookie", "origin", "x-bureau"):
            self.assertNotIn(absent, recus)
        self.assertEqual((recus["accept-encoding"], recus["accept"]), ("identity", "text/html"))
        self.assertEqual(recus["host"], f"127.0.0.1:{self.site}")

    def test_chemin_requete_et_redirections(self):
        r, data = self.req("GET", "/apercu/-/v1/api/scores?n=3")
        self.assertEqual(json.loads(data), {"chemin": "/api/scores?n=3"})
        r, _ = self.req("GET", "/apercu/-/v1/redir-racine")
        self.assertEqual((r.status, r.getheader("Location")), (302, "/apercu/-/v1/connexion?x=1"))
        r, _ = self.req("GET", "/apercu/-/v1/redir-absolue")
        self.assertEqual(r.getheader("Location"), "/apercu/-/v1/tableau")
        r, _ = self.req("GET", "/apercu/-/v1/redir-ailleurs")
        self.assertEqual(r.getheader("Location"), "https://exemple.fr/")
        r, _ = self.req("GET", "/apercu/-/v1")
        self.assertEqual((r.status, r.getheader("Location")), (308, "/apercu/-/v1/"))
        r, data = self.req("HEAD", "/apercu/-/v1/")
        self.assertEqual((r.status, data), (200, b""))

    def test_post_et_methodes(self):
        r, data = self.req("POST", "/apercu/-/v1/formulaire", b"nom=Ana",
                           {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual((r.status, data), (200, b"recu:nom=Ana"))
        for methode in ("PUT", "DELETE"):
            r, _ = self.req(methode, "/apercu/-/v1/")
            self.assertIn(r.status, (405, 501), methode)
        r, data = self.req("GET", "/apercu/-/v1/", entetes={"Upgrade": "websocket", "Connection": "Upgrade"})
        self.assertEqual(r.status, 501)
        self.assertIn("WebSocket", json.loads(data)["erreur"])

    def test_hotes_et_decisions_refuses(self):
        for url in ("http://192.168.1.10:5173/", "http://exemple.fr:80/", "https://127.0.0.1:5173/",
                    "http://127.0.0.1/", f"http://127.0.0.1:{self.port}/"):     # le bureau lui-même : jamais
            self.agir(releve=releve_avec(self.site, [], url=url))
            r, _ = self.req("GET", "/apercu/-/v1/")
            self.assertEqual(r.status, 404, url)
        self.agir(releve=releve_avec(self.site, []))
        for chemin in ("/apercu/-/v9/", "/apercu/autre/v1/", "/apercu/-//", "/apercu/"):
            r, _ = self.req("GET", chemin)
            self.assertEqual(r.status, 404, chemin)
        self.assertEqual(VUS, [])

    def test_site_eteint_502(self):
        r = releve_avec(self.site, [])
        r["decisions_projet"][0]["acces"]["url"] = "http://127.0.0.1:9/"
        self.agir(releve=r)
        reponse, data = self.req("GET", "/apercu/-/v1/")
        self.assertEqual(reponse.status, 502)
        self.assertIn("ne répond pas", json.loads(data)["erreur"])

    def test_hote_refuse_sur_l_ecouteur_local(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", "/apercu/-/v1/", headers={"Host": "evil.example"})
        self.assertEqual(c.getresponse().status, 403)
        c.close()


class TestAuTelephone(AvecBureauOuvert):
    """Sur l'écouteur distant (Tailscale) : le code d'accès garde le téléchargement et le relais comme le reste."""

    def setUp(self):
        super().setUp()
        VUS.clear()
        self.site = lancer_site(self)
        demo = self.tmp / "demo"
        (demo / "build").mkdir()
        (demo / "build" / "jeu.apk").write_bytes(b"PK")
        (demo / "releve.json").write_text(json.dumps(releve_avec(self.site, [{"chemin": "build/jeu.apk",
                                                                              "titre": "APK"}])), encoding="utf-8")
        self.id = next(iter(self.srv.projets))
        self.srv.projets[self.id]._cache_etat = (0.0, None)

    def test_sans_code_401_avec_code_200(self):
        url_apk = f"/api/telecharger?projet={self.id}&fonctionnalite=f1&chemin=build/jeu.apk"
        url_site = f"/apercu/{self.id}/v1/"
        hote = {"Host": f"127.0.0.1:{self.distant}"}
        for url in (url_apk, url_site):
            r, _ = self.req("GET", url, entetes=hote)
            self.assertEqual(r.status, 401, url)
        r, _ = self.req("POST", url_site, b"x", {**hote, "Origin": f"http://127.0.0.1:{self.distant}"})
        self.assertEqual(r.status, 401)
        self.assertEqual(VUS, [])
        cookie = {**hote, "Cookie": self.associer()}
        r, data = self.req("GET", url_apk, entetes=cookie)
        self.assertEqual((r.status, data), (200, b"PK"))
        self.assertTrue(r.getheader("Content-Disposition").startswith("attachment"))
        r, data = self.req("GET", url_site, entetes=cookie)
        self.assertEqual((r.status, data), (200, b"<html>Accueil</html>"))
        self.assertNotIn("cookie", {k.lower() for k in VUS[-1][2]})       # le cookie d'accès ne part pas au site
        r, _ = self.req("POST", url_site, b"x", {**cookie, "Origin": "http://ailleurs"})
        self.assertEqual(r.status, 403)


if __name__ == "__main__":
    unittest.main()
