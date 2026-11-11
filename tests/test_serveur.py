import base64
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
from datetime import datetime, timedelta
from pathlib import Path

from bureau import prix, serveur
from tests import copie_demo

RACINE = Path(__file__).resolve().parent.parent

PRIX_INVENTES = json.dumps({"modele-a": {"input_cost_per_token": 3e-06, "output_cost_per_token": 1.5e-05}})
TAUX_INVENTE = ("<Envelope><Cube><Cube time='2026-11-09'><Cube currency='USD' rate='1.25'/>"
                "</Cube></Cube></Envelope>")


class SourceSimulee:
    """Remplace Internet : jamais de requête sortante dans les tests."""

    def __init__(self, panne=None):
        self.panne = panne
        self.appels = []

    def __call__(self, url):
        self.appels.append(url)
        if self.panne:
            raise self.panne
        return {prix.URL_PRIX: PRIX_INVENTES, prix.URL_TAUX: TAUX_INVENTE}[url]


class AvecServeur(unittest.TestCase):
    ENT = {"X-Bureau": "1", "Content-Type": "application/json"}

    def setUp(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # Windows garde parfois un fichier ouvert un instant
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        copie_demo(self.tmp / "demo")
        self.regl = self.tmp / "demo" / "reglages.json"
        self.demarrer()

    def demarrer(self, source=None):
        self.source = source or SourceSimulee()
        self.srv = serveur.creer(self.regl, port=0, ouvrir=self.source)
        self.port = self.srv.server_address[1]
        self.fil = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.fil.start()
        self.addCleanup(self.arreter, self.srv)

    @property
    def p(self):
        """Le projet unique du bureau lancé avec `--reglages`."""
        return self.srv.projets["projet"]

    def arreter(self, srv):
        srv.shutdown()
        srv.server_close()

    def redemarrer(self, source=None):
        self.arreter(self.srv)
        self.demarrer(source)

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


class TestServeur(AvecServeur):
    def test_ecoute_seulement_en_local(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")

    def test_reglages_seul_inchange(self):
        # Lancé sur un fichier de réglages : un projet, pas de sélecteur, toutes les routes sans `projet`.
        self.assertEqual(self.json("/api/projets"), {"multi": False, "projets": [
            {"id": "projet", "nom": self.json("/api/etat")["projet"] or "projet",
             "attente": self.json("/api/etat")["directeur"]["total"], "erreur": None}]})
        for chemin in ("/api/etat", "/api/charge", "/api/conseil", "/api/facturation", "/api/kpi"):
            with self.subTest(chemin):
                self.assertIsInstance(self.json(chemin), (dict, list))
                sep = "&" if "?" in chemin else "?"
                self.assertEqual(self.json(chemin + sep + "projet=projet").keys(), self.json(chemin).keys())
        r, _ = self.req("GET", "/api/image?chemin=" + "images/inconnue.png")
        self.assertEqual(r.status, 404)
        r, data = self.req("GET", "/api/etat?projet=autre")
        self.assertEqual((r.status, json.loads(data)), (404, {"erreur": "Projet inconnu."}))

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
        self.p._cache_etat = (0.0, self.p._cache_etat[1])  # état périmé : la prochaine demande relit
        lent = threading.Thread(target=self.p.etat, daemon=True)
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

    def test_page_installable_sur_le_telephone(self):
        """Le manifeste et l'icône sont servis avec le bon type, et la page les annonce (tâche 16)."""
        r, page = self.req("GET", "/")
        html = page.decode("utf-8")
        self.assertIn('rel="manifest"', html)
        self.assertIn("manifest.webmanifest", html)
        self.assertIn("width=device-width", html)
        r, corps = self.req("GET", "/manifest.webmanifest")
        self.assertEqual(r.status, 200)
        self.assertTrue(r.getheader("Content-Type").startswith("application/manifest+json"))
        m = json.loads(corps.decode("utf-8"))
        self.assertEqual((m["name"], m["display"]), ("MyIAFactory", "standalone"))
        r, icone = self.req("GET", "/" + m["icons"][0]["src"].lstrip("./"))
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "image/png"))
        self.assertTrue(icone.startswith(b"\x89PNG"))

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

    def test_image_lien_vers_non_image(self):
        self.images()
        try:
            os.symlink(self.tmp / "demo" / "images" / "notes.txt", self.tmp / "demo" / "images" / "faux.png")
        except (OSError, NotImplementedError):
            self.skipTest("création de lien symbolique non permise")
        r, data = self.image("images/faux.png")
        self.assertEqual(r.status, 404)
        self.assertNotIn(b"secret", data)

    def test_etat_images_ok(self):
        self.assertIs(self.json("/api/etat")["images_ok"], True)  # la démonstration déclare des racines d'images
        for valeur in ({}, {"racines": []}, {"racines": [""]}, None):
            regl = json.loads(self.regl.read_text(encoding="utf-8"))
            if valeur is None:
                del regl["images"]
            else:
                regl["images"] = valeur
            self.regl.write_text(json.dumps(regl), encoding="utf-8")
            self.p._cache_etat = (0.0, None)
            self.assertIs(self.json("/api/etat")["images_ok"], False, valeur)

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
        self.p._cache_etat = (0.0, None)
        return dossier / "notes.log"

    def demande(self, d):
        r, data = self.req("POST", "/api/demande", json.dumps(d), self.ENT)
        return r.status, json.loads(data.decode("utf-8"))

    def test_etat_agir(self):
        self.assertIs(self.json("/api/etat")["agir"], True)  # la démonstration déclare une commande d'actions
        regl = json.loads(self.regl.read_text(encoding="utf-8"))
        del regl["actions"]
        self.regl.write_text(json.dumps(regl), encoding="utf-8")
        self.p._cache_etat = (0.0, None)
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

    def test_demande_retour_long_en_octets(self):
        # 3 500 caractères de 4 octets (14 000 octets) restent acceptés : seule la longueur en caractères compte.
        notes = self.agir()
        self.json("/api/etat")
        brut = json.dumps({"type": "retour", "tache": "t1", "texte": "😀" * 3500},
                          ensure_ascii=False).encode("utf-8")  # comme le navigateur : UTF-8 brut
        r, data = self.req("POST", "/api/demande", brut, self.ENT)
        self.assertEqual((r.status, json.loads(data.decode("utf-8"))), (200, {"ok": True}))
        self.assertTrue(notes.exists())
        statut, _ = self.demande({"type": "retour", "tache": "t1", "texte": "x" * 3501})
        self.assertEqual(statut, 400)

    def test_json_tres_imbrique(self):
        self.agir()
        self.json("/api/etat")
        profond = "[" * 7000 + "]" * 7000  # 14 000 octets : sous la limite de taille, mais trop profond
        for chemin in ("/api/demande", "/api/reglages"):
            r, _ = self.req("POST", chemin, profond, self.ENT)
            self.assertEqual(r.status, 400, chemin)
        self.assertEqual(self.json("/api/etat")["projet"], "P")  # le serveur répond encore

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
        self.assertEqual(self.p._cache_etat[0], 0.0)

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


class TestFacturation(AvecServeur):
    RELEVE_V3 = {
        "version": 3, "projet": "P", "factory": {"etat": "en marche"},
        "services": [{"id": "dev", "nom": "Dev"}],
        "colonnes": [{"id": "a", "nom": "A"}],
        "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}],
        "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"}]}

    def usage(self, id="u1", modele="sonnet", entree=1_000_000):
        t = (datetime.now().astimezone() - timedelta(hours=1)).isoformat(timespec="seconds")
        return {"id": id, "tache": "t1", "agent": "d1", "modele": modele, "etape": "dev", "t": t,
                "entree": entree, "sortie": 0}

    def v3(self, *usages, reglages=None):
        dossier = self.tmp / "demo"
        r = json.loads(json.dumps(self.RELEVE_V3))
        r["usage"] = list(usages)
        (dossier / "releve.json").write_text(json.dumps(r), encoding="utf-8")
        regl = json.loads(self.regl.read_text(encoding="utf-8"))
        regl["alias_modeles"] = {"sonnet": "modele-a"}
        regl.update(reglages or {})
        self.regl.write_text(json.dumps(regl), encoding="utf-8")
        self.p._cache_etat = (0.0, None)

    def test_api_facturation(self):
        self.v3(self.usage(), self.usage("u2", modele="mystere", entree=10))
        f = self.json("/api/facturation?periode=7j")
        self.assertIs(f["disponible"], True)
        self.assertEqual(f["periode"], "7j")
        self.assertAlmostEqual(f["total"], 2.4)   # 1 M de tokens × 3 $ × 0,8 €/$
        self.assertAlmostEqual(f["services"]["dev"]["total"], 2.4)
        self.assertEqual(f["sans_prix"], [{"modele": "mystere", "tokens": 10, "usages": 1}])
        self.assertEqual(f["maj"], datetime.now().astimezone().date().isoformat())
        self.assertIsNone(f["message"])
        self.assertEqual(sorted(self.source.appels), sorted([prix.URL_PRIX, prix.URL_TAUX]))
        self.assertEqual(self.json("/api/facturation")["periode"], "7j")   # période par défaut
        e = self.json("/api/etat")
        self.assertEqual(e["dossier"], {"facturation": True, "kpi": True, "connaissances": False})

    def test_periode_inconnue_400(self):
        self.v3(self.usage())
        for requete in ("?periode=1an", "?periode=7j&periode=30j", "?periode="):
            r, data = self.req("GET", "/api/facturation" + requete)
            self.assertEqual(r.status, 400, requete)
            self.assertIn("erreur", json.loads(data.decode("utf-8")))

    def test_v2_facturation_indisponible(self):
        # La démo, redescendue en version 2 : ses champs de la version 3 (usage, kpi…) sont alors ignorés.
        fichier = self.tmp / "demo" / "releve.json"
        r = json.loads(fichier.read_text(encoding="utf-8"))
        self.assertTrue(r["usage"])
        fichier.write_text(json.dumps({**r, "version": 2}), encoding="utf-8")
        self.p._cache_etat = (0.0, None)
        self.assertEqual(self.json("/api/facturation"), {"disponible": False})
        self.assertEqual(self.json("/api/kpi"), {"disponible": False})
        self.assertEqual(self.json("/api/etat")["dossier"],
                         {"facturation": False, "kpi": False, "connaissances": False})
        self.v3()  # version 3 sans aucun usage
        self.assertEqual(self.json("/api/facturation"), {"disponible": False})

    def test_releve_illisible_facturation_indisponible(self):
        (self.tmp / "demo" / "releve.json").write_text("{", encoding="utf-8")
        self.p._cache_etat = (0.0, None)
        self.assertEqual(self.json("/api/facturation"), {"disponible": False})

    def test_prix_automatiques_faux_aucune_requete(self):
        regl = json.loads(self.regl.read_text(encoding="utf-8"))
        regl["prix_automatiques"] = False
        self.regl.write_text(json.dumps(regl), encoding="utf-8")
        self.redemarrer(SourceSimulee(panne=AssertionError("requête sortante interdite")))
        self.v3(self.usage(), reglages={"prix_automatiques": False,
                                        "prix": {"sonnet": {"entree": 2.0, "sortie": 10.0, "date": "2020-01-01"}}})
        self.assertIsNone(self.p._fil_prix)
        f = self.json("/api/facturation")
        self.assertAlmostEqual(f["total"], 2.0)   # la correction à la main suffit
        self.assertIn("prix_automatiques", f["message"])
        self.assertEqual(self.source.appels, [])

    def test_reglages_illisibles_aucune_requete(self):
        self.regl.write_text("{", encoding="utf-8")
        self.redemarrer(SourceSimulee(panne=AssertionError("requête sortante interdite")))
        self.assertIsNone(self.p._fil_prix)
        self.assertEqual(self.source.appels, [])

    def test_source_en_panne_serveur_ok_et_message(self):
        self.arreter(self.srv)
        (self.tmp / "demo" / "prix-historique.jsonl").unlink()  # aucun prix encore enregistré
        self.demarrer(SourceSimulee(panne=OSError("réseau coupé")))
        self.v3(self.usage())
        f = self.json("/api/facturation?periode=30j")
        self.assertIs(f["disponible"], True)
        self.assertEqual(f["total"], 0)
        self.assertEqual(f["sans_prix"][0]["modele"], "sonnet")
        self.assertIn("impossible", f["message"])
        self.assertIn("réseau coupé", f["message"])
        self.assertIsNone(f["maj"])
        self.assertIsNone(self.json("/api/etat")["erreur"])

    def test_usage_integre_au_releve_valide(self):
        self.v3(self.usage())
        self.json("/api/etat")
        historique = self.tmp / "demo" / "usage-historique.jsonl"
        lignes = historique.read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(x)["id"] for x in lignes], ["u1"])
        # Un relevé invalide n'est pas intégré.
        mauvais = dict(self.usage("u2"), entree=-1)
        self.v3(mauvais)
        self.assertIsNotNone(self.json("/api/etat")["erreur"])
        self.assertNotIn("u2", historique.read_text(encoding="utf-8"))
        # Le projet retire l'usage du relevé : il reste compté.
        self.v3(self.usage("u3"))
        self.json("/api/etat")
        f = self.json("/api/facturation")
        self.assertEqual(sorted(u["id"] for u in f["services"]["dev"]["usages"]), ["u1", "u3"])

    def test_hote_refuse_403(self):
        self.v3(self.usage())
        r, _ = self.req("GET", "/api/facturation", entetes={"Host": "evil.example.com"})
        self.assertEqual(r.status, 403)


class TestChallenges(AvecServeur):
    SOURCE = "source:dev:allers_retours:t1"
    RELEVE_V2, SCRIPT_ACTIONS, agir, demande = (TestServeur.RELEVE_V2, TestServeur.SCRIPT_ACTIONS,
                                                TestServeur.agir, TestServeur.demande)
    RELEVE_V3, usage = TestFacturation.RELEVE_V3, TestFacturation.usage

    def installer(self, challenges=None, duree=0.0):
        """Relevé v3 (une connaissance, une tâche à deux retours qui coûte) et commande d'actions."""
        r = json.loads(json.dumps(self.RELEVE_V3))
        r["titulaires"][0]["connaissances"] = [{"id": "k1", "texte": "Relire"}]
        r["taches"][0]["retours"] = [{"t": "1", "texte": "a"}, {"t": "2", "texte": "b"}]
        r["usage"] = [self.usage()]
        if challenges is not None:
            r["challenges"] = challenges
        notes = self.agir(duree=duree, releve=r)
        regl = json.loads(self.regl.read_text(encoding="utf-8"))
        regl["alias_modeles"] = {"sonnet": "modele-a"}
        self.regl.write_text(json.dumps(regl), encoding="utf-8")
        self.p._cache_etat = (0.0, None)
        return notes

    def recues(self, notes):
        if not notes.exists():
            return []
        return [json.loads(x) for x in notes.read_text(encoding="utf-8").splitlines() if x.startswith("{")]

    def test_commande_non_lancee_si_refus(self):
        notes = self.installer(challenges=[{"id": "ch1", "cible": {"type": "connaissance", "id": "k1"},
                                            "texte": "c", "solutions": [{"id": "s1", "texte": "x",
                                                                         "auteur": "service"}]}])
        for d in ({"type": "challenge", "cible": {"type": "connaissance", "id": "k9"}},
                  {"type": "challenge", "cible": {"type": "connaissance", "id": "k1"}},  # déjà ouvert
                  {"type": "challenge", "cible": {"type": "source", "id": "source:dev:tache_chere:t1"}},
                  {"type": "solution", "challenge": "ch9", "texte": "x"},
                  {"type": "verdict_solution", "challenge": "ch1", "solution": "s9", "verdict": "valider"}):
            statut, corps = self.demande(d)
            self.assertEqual(statut, 400, d)
            self.assertIn("erreur", corps)
        self.assertEqual(self.recues(notes), [])

    def test_solution_dans_le_meme_geste(self):
        notes = self.installer()
        statut, _ = self.demande({"type": "challenge", "cible": {"type": "connaissance", "id": "k1"},
                                  "solution": "Relire deux fois", "pirate": 1})
        self.assertEqual(statut, 200)
        recue = self.recues(notes)[0]
        self.assertEqual((recue["type"], recue["cible"], recue["solution"]),
                         ("challenge", {"type": "connaissance", "id": "k1"}, "Relire deux fois"))
        self.assertNotIn("pirate", recue)
        self.assertIn("t", recue)

    def test_challenge_sur_source_calculee(self):
        # Le bureau recalcule la source et écrit lui-même le constat pour le projet.
        notes = self.installer()
        statut, corps = self.demande({"type": "challenge", "cible": {"type": "source", "id": self.SOURCE},
                                      "texte": "trop cher"})
        self.assertEqual(statut, 200, corps)
        recue = self.recues(notes)[0]
        self.assertIn("2 retours", recue["texte"])
        self.assertIn("≈", recue["texte"])
        self.assertIn("trop cher", recue["texte"])

    def test_double_clic_un_seul_challenge(self):
        # Le projet n'a pas encore inscrit le challenge : un second envoi sur la même cible est refusé.
        notes = self.installer()
        d = {"type": "challenge", "cible": {"type": "connaissance", "id": "k1"}}
        self.assertEqual(self.demande(d)[0], 200)
        statut, corps = self.demande(d)
        self.assertEqual(statut, 400)
        self.assertIn("déjà", corps["erreur"])
        self.assertEqual(len(self.recues(notes)), 1)

    def test_double_clic_simultane(self):
        notes = self.installer(duree=0.3)
        self.json("/api/etat")
        d = {"type": "challenge", "cible": {"type": "connaissance", "id": "k1"}}
        resultats = []
        fils = [threading.Thread(target=lambda: resultats.append(self.demande(d)[0])) for _ in range(2)]
        for f in fils:
            f.start()
        for f in fils:
            f.join(20)
        self.assertEqual(sorted(resultats), [200, 400])
        self.assertEqual(len(self.recues(notes)), 1)

    def test_trois_demandes_en_alternance(self):
        notes = self.installer(challenges=[{"id": "ch1", "cible": {"type": "connaissance", "id": "k1"},
                                            "texte": "c", "solutions": [{"id": "s1", "texte": "x",
                                                                         "auteur": "directeur"},
                                                                        {"id": "s2", "texte": "y",
                                                                         "auteur": "service"}]}])
        envoyees = [{"type": "solution", "challenge": "ch1", "texte": "Ma solution"},
                    {"type": "verdict_solution", "challenge": "ch1", "solution": "s1", "verdict": "valider"},
                    {"type": "challenge", "cible": {"type": "source", "id": self.SOURCE}},
                    {"type": "verdict_solution", "challenge": "ch1", "solution": "s2", "verdict": "ecarter"}]
        for d in envoyees:
            self.assertEqual(self.demande(d)[0], 200, d)
        recues = self.recues(notes)
        self.assertEqual([x["type"] for x in recues], [d["type"] for d in envoyees])
        self.assertEqual(recues[3]["verdict"], "ecarter")

    def test_challenge_sur_connaissance_sans_calcul_de_facturation(self):
        # Une cible « connaissance » n'a rien à recalculer : pas d'attente des prix dans le verrou.
        notes = self.installer()

        def interdit(*a, **k):
            raise AssertionError("calcul inutile")
        self.p._calculer = interdit
        statut, corps = self.demande({"type": "challenge", "cible": {"type": "connaissance", "id": "k1"}})
        self.assertEqual(statut, 200, corps)
        self.assertEqual(len(self.recues(notes)), 1)

    def test_demande_relit_le_releve_meme_si_une_lecture_est_en_cours(self):
        # Une autre lecture tient le verrou de l'état : la demande attend le relevé frais au lieu
        # d'être vérifiée contre l'ancien.
        self.installer()
        self.json("/api/etat")
        r = json.loads((self.tmp / "demo" / "releve.json").read_text(encoding="utf-8"))
        r["challenges"] = [{"id": "ch9", "cible": {"type": "connaissance", "id": "k1"}, "texte": "c"}]
        (self.tmp / "demo" / "releve.json").write_text(json.dumps(r), encoding="utf-8")
        self.p._cache_etat = (0.0, self.p._cache_etat[1])
        self.p._verrou.acquire()
        threading.Timer(0.3, self.p._verrou.release).start()
        statut, corps = self.demande({"type": "solution", "challenge": "ch9", "texte": "x"})
        self.assertEqual(statut, 200, corps)

    def test_type_de_demande_non_texte_400(self):
        self.installer()
        for d in ({"type": ["challenge"]}, {"type": {"a": 1}}):
            statut, corps = self.demande(d)
            self.assertEqual(statut, 400, d)
            self.assertIn("erreur", corps)


class TestKpi(AvecServeur):
    RELEVE_V2, SCRIPT_ACTIONS, agir, demande = (TestServeur.RELEVE_V2, TestServeur.SCRIPT_ACTIONS,
                                                TestServeur.agir, TestServeur.demande)
    RELEVE_V3, usage = TestFacturation.RELEVE_V3, TestFacturation.usage
    recues = TestChallenges.recues

    def installer(self, kpi=None, usage=True, duree=0.0):
        r = json.loads(json.dumps(self.RELEVE_V3))
        r["colonnes"].append({"id": "f", "nom": "Fait", "terminee": True})
        r["taches"].append({"id": "t2", "titre": "Fini", "colonne": "f", "active": False, "titulaire": "d1",
                            "maj": datetime.now().astimezone().isoformat(timespec="seconds")})
        if kpi is not None:
            r["services"][0]["kpi"] = kpi
        if usage:
            r["usage"] = [self.usage()]
        notes = self.agir(duree=duree, releve=r)
        regl = json.loads(self.regl.read_text(encoding="utf-8"))
        regl["alias_modeles"] = {"sonnet": "modele-a"}
        self.regl.write_text(json.dumps(regl), encoding="utf-8")
        self.p._cache_etat = (0.0, None)
        return notes

    def test_api_kpi(self):
        self.installer(kpi=[{"id": "defauts", "nom": "Défauts", "valeur": 2, "alerte": True, "texte": "deux fois"}])
        k = self.json("/api/kpi?periode=7j")
        self.assertIs(k["disponible"], True)
        self.assertEqual(k["periode"], "7j")
        dev = {x["id"]: x for x in k["services"]["dev"]}
        self.assertEqual(dev["defauts"]["valeur"], 2)
        self.assertEqual(dev["taches_terminees"]["valeur"], 1)
        self.assertIn("cout_moyen", dev)
        self.assertEqual(self.json("/api/kpi?periode=30j")["periode"], "30j")

    def test_api_kpi_periode_inconnue_ou_absente(self):
        self.installer()
        for q in ("?periode=1an", "?periode=7j&periode=30j"):
            r, _ = self.req("GET", "/api/kpi" + q)
            self.assertEqual(r.status, 400, q)
        self.assertEqual(self.json("/api/kpi")["periode"], "7j")

    def test_api_kpi_indisponible_en_v2(self):
        self.agir(releve=self.RELEVE_V2)
        self.p._cache_etat = (0.0, None)
        self.assertEqual(self.json("/api/kpi?periode=7j"), {"disponible": False})

    def test_challenge_sur_kpi_calcule_accepte(self):
        notes = self.installer()
        statut, corps = self.demande({"type": "challenge", "cible": {"type": "kpi", "id": "kpi:dev:taches_terminees"},
                                      "texte": "trop peu"})
        self.assertEqual(statut, 200, corps)
        texte = self.recues(notes)[0]["texte"]
        self.assertIn("Tâches terminées", texte)   # le constat est écrit par le bureau
        self.assertIn("trop peu", texte)

    def test_challenge_sur_kpi_du_projet_accepte(self):
        notes = self.installer(kpi=[{"id": "defauts", "nom": "Défauts", "valeur": 2, "alerte": True}])
        statut, _ = self.demande({"type": "challenge", "cible": {"type": "kpi", "id": "kpi:dev:defauts"}})
        self.assertEqual(statut, 200)
        self.assertEqual(self.recues(notes)[0]["cible"]["id"], "kpi:dev:defauts")

    def test_challenge_sur_kpi_inconnu_refuse(self):
        notes = self.installer()
        for i in ("kpi:dev:inconnu", "kpi:rh:taches_terminees", "taches_terminees"):
            statut, _ = self.demande({"type": "challenge", "cible": {"type": "kpi", "id": i}})
            self.assertEqual(statut, 400, i)
        self.assertEqual(self.recues(notes), [])

    def test_probleme_revenu_servi(self):
        # La première alerte est notée à la lecture du relevé ; une connaissance plus ancienne est marquée.
        r = json.loads(json.dumps(self.RELEVE_V3))
        r["services"][0]["kpi"] = [{"id": "defauts", "nom": "D", "valeur": 2, "alerte": True}]
        r["titulaires"][0]["connaissances"] = [{"id": "k1", "texte": "a", "date": "2020-01-01", "origine": "ch1"}]
        r["challenges"] = [{"id": "ch1", "cible": {"type": "kpi", "id": "kpi:dev:defauts"}, "texte": "c"}]
        self.agir(releve=r)
        self.p._cache_etat = (0.0, None)
        e = self.json("/api/etat")
        self.assertTrue(e["agents"][0]["connaissances"][0]["probleme_revenu"])
        self.assertTrue((self.tmp / "demo" / "alertes-historique.jsonl").exists())
        self.assertTrue(e["dossier"]["kpi"])

    def test_onglet_kpi_avec_usage_seul(self):
        self.installer(usage=True)
        self.assertTrue(self.json("/api/etat")["dossier"]["kpi"])


class TestDemandesV4(AvecServeur):
    RELEVE_V4 = {
        "version": 4, "projet": "P", "factory": {"etat": "en marche"},
        "services": [{"id": "dev", "nom": "Dev"}],
        "colonnes": [{"id": "a", "nom": "A"}],
        "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}],
        "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"}],
        "fonctionnalites": [{"id": "f1", "nom": "Ville", "etape": "cadrage"}]}
    SCRIPT_ACTIONS = TestServeur.SCRIPT_ACTIONS
    agir, demande = TestServeur.agir, TestServeur.demande

    def preparer(self):
        notes = self.agir(releve=self.RELEVE_V4)
        self.json("/api/etat")
        return notes

    def lignes(self, notes):
        if not notes.exists():
            return []
        return [json.loads(x) for x in notes.read_text(encoding="utf-8").splitlines()
                if x.startswith("{")]

    def test_commande_recoit_les_images(self):
        notes = self.preparer()
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + bytes(range(256))).decode("ascii")
        images = [{"nom": "a.png", "type": "image/png", "donnees": png}]
        statut, corps = self.demande({"type": "message", "fonctionnalite": "f1", "texte": "Voir", "images": images})
        self.assertEqual((statut, corps), (200, {"ok": True}))
        recu = self.lignes(notes)
        self.assertEqual(len(recu), 1)
        self.assertEqual(recu[0]["images"], images)  # base64 intact
        self.assertEqual((recu[0]["type"], recu[0]["fonctionnalite"]), ("message", "f1"))

    def test_images_refusees(self):
        notes = self.preparer()
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8).decode("ascii")
        gros = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * (6 * 1024 * 1024)).decode("ascii")
        gif = base64.b64encode(b"GIF89a" + b"\x00" * 8).decode("ascii")
        cas = [[{"nom": f"{i}.png", "type": "image/png", "donnees": png} for i in range(5)],
               [{"nom": "gros.png", "type": "image/png", "donnees": gros}],
               [{"nom": "a.png", "type": "image/png", "donnees": gif}],
               [{"nom": "a.png", "type": "image/png", "donnees": "pas du base64 !"}],
               [{"nom": "../x.png", "type": "image/png", "donnees": png}]]
        for images in cas:
            statut, corps = self.demande({"type": "fonctionnalite", "texte": "Une ville", "images": images})
            self.assertEqual(statut, 400, [i["nom"] for i in images])
            self.assertTrue(corps["erreur"])
        self.assertEqual(self.lignes(notes), [])  # la commande n'est jamais lancée
        self.assertFalse(notes.exists())

    def test_corps_28_mo(self):
        notes = self.preparer()
        limite = 28 * 1024 * 1024
        base = json.dumps({"type": "message", "fonctionnalite": "f1", "texte": "Gros"}).encode("utf-8")
        juste = base + b" " * (limite - len(base))  # du blanc JSON : valide, et pile à la limite
        self.assertEqual(len(juste), limite)
        r, data = self.req("POST", "/api/demande", juste, self.ENT)
        self.assertEqual((r.status, json.loads(data.decode("utf-8"))), (200, {"ok": True}))
        self.assertEqual(len(self.lignes(notes)), 1)
        # Au-dessus : refusé d'après l'en-tête, sans lire le corps.
        r, data = self.req("POST", "/api/demande", b"{}", {**self.ENT, "Content-Length": str(limite + 1)})
        self.assertEqual(r.status, 400)
        self.assertEqual(len(self.lignes(notes)), 1)

    def test_corps_reglages_toujours_petit(self):
        r, _ = self.req("POST", "/api/reglages", b" " * 5000 + b"{}", self.ENT)
        self.assertEqual(r.status, 400)

    def test_doublon_message_ignore(self):
        notes = self.preparer()
        d = {"type": "message", "fonctionnalite": "f1", "texte": "Un seul clic"}
        self.assertEqual(self.demande(d), (200, {"ok": True}))
        self.assertEqual(self.demande(d), (200, {"ok": True, "doublon": True}))
        self.assertEqual(len(self.lignes(notes)), 1)
        autre = {**d, "texte": "Un autre"}
        self.assertEqual(self.demande(autre), (200, {"ok": True}))
        self.assertEqual(len(self.lignes(notes)), 2)

    def test_doublon_fonctionnalite_ignore(self):
        notes = self.preparer()
        d = {"type": "fonctionnalite", "texte": "Une ville"}
        self.assertEqual(self.demande(d)[0], 200)
        self.assertEqual(self.demande(d), (200, {"ok": True, "doublon": True}))
        self.assertEqual(len(self.lignes(notes)), 1)

    def test_doublon_oublie_apres_la_garde(self):
        notes = self.preparer()
        d = {"type": "message", "fonctionnalite": "f1", "texte": "Encore"}
        self.assertEqual(self.demande(d), (200, {"ok": True}))
        self.p._derniere_creation = (self.p._derniere_creation[0],
                                       time.monotonic() - serveur.GARDE_DOUBLON_S - 1)
        self.assertEqual(self.demande(d), (200, {"ok": True}))
        self.assertEqual(len(self.lignes(notes)), 2)

    def test_echec_de_la_commande_ne_fait_pas_doublon(self):
        notes = self.agir(code=1, releve=self.RELEVE_V4)
        self.json("/api/etat")
        d = {"type": "message", "fonctionnalite": "f1", "texte": "Raté"}
        self.assertEqual(self.demande(d)[0], 502)
        self.assertEqual(self.demande(d)[0], 502)  # pas pris pour un doublon : on peut réessayer
        self.assertEqual(len(self.lignes(notes)), 2)

    def test_demande_v4_refusee_sur_releve_v2(self):
        notes = self.agir(releve={**self.RELEVE_V4, "version": 2, "fonctionnalites": []})  # pas de v4
        self.json("/api/etat")
        statut, _ = self.demande({"type": "fonctionnalite", "texte": "x"})
        self.assertEqual(statut, 400)
        self.assertFalse(notes.exists())


class TestLancement(AvecServeur):
    """Le premier lancement : un drapeau « vu », global (sans `?projet=`), en mémoire dans les tests."""

    def lu(self):
        return self.json("/api/lancement")

    def test_pas_vu_puis_marque(self):
        self.assertEqual(self.lu(), {"vu": False})
        r, _ = self.req("POST", "/api/lancement", "{}", {"Content-Type": "application/json"})
        self.assertEqual(r.status, 403)
        self.assertEqual(self.lu(), {"vu": False})
        r, _ = self.req("POST", "/api/lancement", "{}", {**self.ENT, "Host": "evil.example.com"})
        self.assertEqual(r.status, 403)
        self.assertEqual(self.lu(), {"vu": False})
        r, data = self.req("POST", "/api/lancement", "{}", self.ENT)
        self.assertEqual((r.status, json.loads(data)), (200, {"vu": True}))
        self.assertEqual(self.lu(), {"vu": True})

    def test_route_globale(self):
        r, _ = self.req("GET", "/api/lancement?projet=inconnu")
        self.assertEqual(r.status, 200)

    def test_get_hote_refuse(self):
        r, _ = self.req("GET", "/api/lancement", entetes={"Host": "evil.example.com"})
        self.assertEqual(r.status, 403)


if __name__ == "__main__":
    unittest.main()
