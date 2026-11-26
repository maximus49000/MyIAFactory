"""La zone « Services » du bureau (`bureau/services.py`, routes `/api/services`). Le module du poste est un faux : aucun
serveur, aucun SSH ; le vrai validateur du script hôte sert pour les noms et valeurs."""
import json
import threading
import unittest

from bureau import services as bservices
from tests.test_serveur import AvecServeur
from tests.test_serveur_service_hote import DECLARATION, S

SECRET = "valeur-api-football-de-test-0001"
JETON = "jeton-de-test-" + "x" * 40


class FauxPoste:
    ACTION = "service"
    HOTE = S

    def __init__(self):
        self.appels = []
        self.jeton = ""
        self.cache = {}
        self.auto = {}
        self.lache = threading.Event()
        self.lache.set()

    def a_un_service(self, d):
        return (d / ".factory" / "service.json").is_file()

    def identifiant(self, d):
        return "demo"

    def lire_declaration(self, d):
        return S.valider_declaration((d / ".factory" / "service.json").read_bytes())

    def lire_cache(self, dossier=None):
        return self.cache

    def lire_jeton(self, projet, dossier=None):
        return self.jeton

    def lire_auto(self, dossier=None):
        return dict(self.auto)

    def poser_auto(self, projet, actif, dossier=None):
        self.auto = {projet: True} if actif else {}
        return bool(actif)

    def poser_secrets(self, racine, valeurs, dossier=None):
        self.appels.append(("secrets", dict(valeurs)))
        return 0, {"statut": "ok", "detail": "1 secrets posé(s)."}

    def deployer(self, racine, dossier=None):
        self.lache.wait(5)
        self.appels.append(("deployer",))
        return 0, {"statut": "ok"}

    def gerer(self, racine, commande, dossier=None):
        self.appels.append((commande,))
        return 0, {"statut": "ok"}


class TestZoneServices(AvecServeur):
    def setUp(self):
        super().setUp()
        (self.tmp / "demo" / ".factory").mkdir(exist_ok=True)
        decl = dict(DECLARATION, secrets=["API_FOOTBALL_KEY"])
        (self.tmp / "demo" / ".factory" / "service.json").write_text(json.dumps(decl), "utf-8")
        self.poste = FauxPoste()
        self.srv.travaux_services = bservices.Travaux(module=self.poste)

    def poster(self, chemin, corps, entetes=None):
        return self.req("POST", chemin, json.dumps(corps), self.ENT if entetes is None else entetes)

    def test_liste_sans_secret(self):
        self.poste.jeton = JETON
        self.poste.cache = {"demo": {"etat": {"etat": "actif", "secrets": {"API_FOOTBALL_KEY": True}, "port": 18000},
                                     "adresse": "http://serveur.exemple.test:18000",
                                     "journal": {"lignes": ["démarré"]}}}
        (s,) = self.json("/api/services")["services"]
        self.assertEqual((s["projet"], s["etat"], s["adresse"]), ("demo", "actif", "http://serveur.exemple.test:18000"))
        self.assertEqual(s["secrets"], {"API_FOOTBALL_KEY": True})
        self.assertTrue(s["jeton_present"])
        self.assertNotIn(JETON, json.dumps(s))

    def test_secret_saisi_pose_jamais_rendu(self):
        r, data = self.poster("/api/services/demo/secrets", {"secrets": {"API_FOOTBALL_KEY": SECRET}})
        self.assertEqual(r.status, 202, data)
        self.srv.travaux_services.attendre()
        self.assertEqual(self.poste.appels, [("secrets", {"API_FOOTBALL_KEY": SECRET})])
        texte = json.dumps(self.json("/api/services"))
        self.assertNotIn(SECRET, texte)
        self.assertNotIn(SECRET, data.decode("utf-8"))

    def test_secret_non_declare_ou_hostile_refuse(self):
        for corps in ({"secrets": {"AUTRE": "x"}}, {"secrets": {"API_FOOTBALL_KEY": "a\nb"}}, {"secrets": {}},
                      {"secrets": {"API_FOOTBALL_KEY": 3}}, {"secrets": {"API_FOOTBALL_KEY": "x"}, "plus": 1}):
            with self.subTest(corps=corps):
                self.assertEqual(self.poster("/api/services/demo/secrets", corps)[0].status, 400)
        self.assertEqual(self.poste.appels, [])

    def test_en_tetes_requis(self):
        r, _ = self.poster("/api/services/demo/arreter", {}, {"Content-Type": "application/json"})
        self.assertEqual(r.status, 403)
        self.assertEqual(self.poste.appels, [])

    def test_projet_inconnu_ou_route_hostile(self):
        self.assertEqual(self.poster("/api/services/autre/arreter", {})[0].status, 404)
        for chemin in ("/api/services/..%2Fx/arreter", "/api/services/demo/supprimer", "/api/services/DEMO/etat"):
            with self.subTest(chemin=chemin):
                self.assertEqual(self.poster(chemin, {})[0].status, 404)

    def test_actions_dans_un_fil_une_a_la_fois(self):
        self.poste.lache.clear()
        r1, _ = self.poster("/api/services/demo/deployer", {})
        r2, _ = self.poster("/api/services/demo/redemarrer", {})
        self.assertEqual((r1.status, r2.status), (202, 409))
        self.poste.lache.set()
        self.srv.travaux_services.attendre()
        for action in ("etat", "journal", "arreter", "redemarrer"):
            self.assertEqual(self.poster(f"/api/services/demo/{action}", {})[0].status, 202)
            self.srv.travaux_services.attendre()
        self.assertEqual(self.poste.appels, [("deployer",), ("etat",), ("journal",), ("arreter",), ("redemarrer",)])

    def test_case_deploiement_automatique(self):
        r, data = self.poster("/api/services/demo/auto", {"actif": True})
        self.assertEqual((r.status, json.loads(data)), (200, {"auto": True}))
        r, data = self.req("GET", "/api/services")
        self.assertTrue(json.loads(data)["services"][0]["auto"])
        self.assertEqual(self.poster("/api/services/demo/auto", {"actif": "oui"})[0].status, 400)
        self.assertEqual(self.poster("/api/services/demo/auto", {})[0].status, 400)
        r, data = self.poster("/api/services/demo/auto", {"actif": False})
        self.assertEqual(json.loads(data), {"auto": False})

    def test_jeton_pour_le_bouton_copier(self):
        self.assertEqual(self.poster("/api/services/demo/jeton", {})[0].status, 404)
        self.poste.jeton = JETON
        r, data = self.poster("/api/services/demo/jeton", {})
        self.assertEqual((r.status, json.loads(data)), (200, {"jeton": JETON}))


if __name__ == "__main__":
    unittest.main()


from tests.test_acces import AvecBureauOuvert  # noqa: E402


class TestServicesSurLEcouteurDistant(AvecBureauOuvert):
    """Décision du Directeur (2026-11-25) : la zone « Services » s'ouvre aussi au téléphone (écouteur distant), avec le code
    d'accès ; sans cookie d'accès elle reste fermée."""

    def entetes(self, cookie):
        return {"Cookie": cookie, "Origin": f"http://127.0.0.1:{self.distant}", "X-Bureau": "1"}

    def test_lecture_avec_le_cookie_d_acces(self):
        cookie = self.associer()
        r, data = self.req("GET", "/api/services", None, self.entetes(cookie))
        self.assertEqual(r.status, 200, data)
        self.assertIn("services", json.loads(data))

    def test_sans_cookie_la_zone_reste_fermee(self):
        r, _ = self.req("GET", "/api/services", None, {"Origin": f"http://127.0.0.1:{self.distant}", "X-Bureau": "1"})
        self.assertNotEqual(r.status, 200)

    def test_un_secret_sans_origine_valide_est_refuse(self):
        cookie = self.associer()
        ent = {**self.entetes(cookie), "Origin": "http://exemple.test", "Content-Type": "application/json"}
        r, _ = self.req("POST", "/api/services/demo/secrets", json.dumps({"secrets": {"API_FOOTBALL_KEY": "x"}}), ent)
        self.assertNotEqual(r.status, 200)
