"""Un bureau, plusieurs projets : lecture du fichier du bureau, routes par projet, isolation."""
import http.client
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bureau import charge, reglages, serveur
from tests import copie_demo
from tests.test_serveur import SourceSimulee

ENT = {"X-Bureau": "1", "Content-Type": "application/json"}
SCRIPT_ACTIONS = ("import sys\n"
                  "d = sys.stdin.buffer.read()\n"
                  "open(sys.argv[1], 'ab').write(d + b'\\n')\n")
RELEVE = {"version": 4, "projet": "P", "factory": {"etat": "en marche"},
          "services": [{"id": "dev", "nom": "Dev"}],
          "colonnes": [{"id": "a", "nom": "A"}],
          "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}],
          "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"}],
          "fonctionnalites": [{"id": "f1", "nom": "Ville", "etape": "cadrage",
                               "decisions": [{"id": "dc1", "genre": "valider_cahier", "texte": "?"}]}]}
PNG_A = b"\x89PNG\r\n\x1a\n" + b"A" * 16
PNG_B = b"\x89PNG\r\n\x1a\n" + b"B" * 16


class TestLireBureau(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)

    def ecrire(self, contenu, nom="bureau.json"):
        f = self.tmp / nom
        f.write_text(json.dumps(contenu) if not isinstance(contenu, str) else contenu, encoding="utf-8")
        return f

    def creer(self, *chemins):
        for c in chemins:
            f = Path(c) if Path(c).is_absolute() else self.tmp / c
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("{}", encoding="utf-8")

    def test_lire_bureau(self):
        self.creer("Jeu Été/.factory/reglages.json", "outils/reglages.json", "autre/outils/reglages.json",
                   "x/reglages.json", "y/r.json", self.tmp / "loin" / "mon-id" / "reglages.json")
        # Ids par défaut : dossier des réglages, ou son parent pour `.factory` ; ramenés à [a-z0-9-].
        f = self.ecrire({"projets": ["Jeu Été/.factory/reglages.json", "outils/reglages.json",
                                     {"chemin": "autre/outils/reglages.json"},
                                     {"chemin": "x/reglages.json", "id": "mon-id"}]})
        b = reglages.lire_bureau(f)
        self.assertEqual(b["port"], 8770)
        self.assertEqual([p["id"] for p in b["projets"]], ["jeu-ete", "outils", "outils-2", "mon-id"])
        # Chemins relatifs au fichier du bureau.
        self.assertEqual(b["projets"][0]["chemin"], self.tmp / "Jeu Été" / ".factory" / "reglages.json")
        self.assertEqual(b["projets"][3]["chemin"], self.tmp / "x" / "reglages.json")
        # Un chemin absolu reste tel quel ; un id donné réservé n'est pas repris par un id par défaut.
        absolu = self.tmp / "loin" / "mon-id" / "reglages.json"
        b = reglages.lire_bureau(self.ecrire({"port": 9000, "projets": [str(absolu), {"chemin": "y/r.json",
                                                                                      "id": "mon-id"}]}))
        self.assertEqual(b["port"], 9000)
        self.assertEqual([p["id"] for p in b["projets"]], ["mon-id-2", "mon-id"])
        self.assertEqual(b["projets"][0]["chemin"], absolu)

    def test_lire_bureau_reglages_absents_ou_partages(self):
        # Une faute de frappe dans un chemin ne crée pas de projet fantôme (dossiers, prix lus pour rien).
        for nom in ("a", "b"):
            (self.tmp / nom).mkdir()
            (self.tmp / nom / "reglages.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(reglages.ReglagesInvalides, "introuvable"):
            reglages.lire_bureau(self.ecrire({"projets": ["a/reglages.json", "absent/reglages.json"]}))
        self.assertFalse((self.tmp / "absent").exists())
        # Deux entrées sur le même dossier écriraient les mêmes historiques : refusé.
        (self.tmp / "a" / "autre.json").write_text("{}", encoding="utf-8")
        for projets in (["a/reglages.json", {"chemin": "a/reglages.json", "id": "bis"}],
                        ["a/reglages.json", "a/../a/autre.json"]):
            with self.assertRaisesRegex(reglages.ReglagesInvalides, "même dossier"):
                reglages.lire_bureau(self.ecrire({"projets": projets}))
        self.assertEqual(len(reglages.lire_bureau(self.ecrire({"projets": ["a/reglages.json", "b/reglages.json"]}))
                             ["projets"]), 2)

    def test_lire_bureau_refus(self):
        cas = {
            "illisible": "{",
            "pas un objet": [],
            "projets absent": {},
            "aucun projet": {"projets": []},
            "13 projets": {"projets": [f"p{i}/reglages.json" for i in range(13)]},
            "id invalide": {"projets": [{"chemin": "a/r.json", "id": "../x"}]},
            "id majuscule": {"projets": [{"chemin": "a/r.json", "id": "A"}]},
            "id double": {"projets": [{"chemin": "a/r.json", "id": "a"}, {"chemin": "b/r.json", "id": "a"}]},
            "chemin vide": {"projets": [""]},
            "chemin manquant": {"projets": [{"id": "a"}]},
            "entrée nombre": {"projets": [3]},
            "port texte": {"port": "8770", "projets": ["a/r.json"]},
            "port hors bornes": {"port": 70000, "projets": ["a/r.json"]},
        }
        for nom, contenu in cas.items():
            with self.subTest(nom):
                with self.assertRaises(reglages.ReglagesInvalides):
                    reglages.lire_bureau(self.ecrire(contenu))
        with self.assertRaises(reglages.ReglagesInvalides):
            reglages.lire_bureau(self.tmp / "absent.json")
        # 12 projets : la limite haute est acceptée.
        self.creer(*[f"p{i}/r.json" for i in range(12)])
        self.assertEqual(len(reglages.lire_bureau(self.ecrire({"projets": [f"p{i}/r.json" for i in range(12)]}))
                             ["projets"]), 12)


class AvecBureau(unittest.TestCase):
    """Deux copies de la démo, A et B, chacune avec sa commande d'actions et ses images."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        for nom, png in (("a", PNG_A), ("b", PNG_B)):
            d = copie_demo(self.tmp / nom / ".factory")
            r = dict(RELEVE, projet=f"Projet {nom.upper()}")
            (d / "releve.json").write_text(json.dumps(r), encoding="utf-8")
            (d / "actions.py").write_text(SCRIPT_ACTIONS, encoding="utf-8")
            (d / "img").mkdir()
            (d / "img" / "x.png").write_bytes(png)
            regl = json.loads((d / "reglages.json").read_text(encoding="utf-8"))
            regl["releve"] = {"fichier": "releve.json"}
            regl["actions"] = {"commande": [sys.executable, "actions.py", "notes.log"], "dossier": "."}
            regl["images"] = {"racines": ["img"]}
            regl["prix_automatiques"] = False
            (d / "reglages.json").write_text(json.dumps(regl), encoding="utf-8")
        self.fichier = self.tmp / "bureau.json"
        self.fichier.write_text(json.dumps({"projets": ["a/.factory/reglages.json", "b/.factory/reglages.json"]}),
                                encoding="utf-8")
        self.demarrer()

    def dossier(self, nom):
        return self.tmp / nom / ".factory"

    def demarrer(self):
        self.srv = serveur.creer(bureau=self.fichier, port=0, ouvrir=SourceSimulee(panne=AssertionError("réseau")))
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.arreter, self.srv)

    def arreter(self, srv):
        srv.shutdown()
        srv.server_close()

    def req(self, methode, chemin, corps=None, entetes=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        c.request(methode, chemin, body=corps, headers=entetes or {})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r, data

    def json(self, chemin, code=200):
        r, data = self.req("GET", chemin)
        self.assertEqual(r.status, code, data)
        return json.loads(data.decode("utf-8"))

    def post(self, chemin, objet):
        r, data = self.req("POST", chemin, json.dumps(objet), ENT)
        return r.status, json.loads(data.decode("utf-8"))


class TestBureauMulti(AvecBureau):
    def test_api_projets(self):
        p = self.json("/api/projets")
        self.assertIs(p["multi"], True)
        self.assertEqual([x["id"] for x in p["projets"]], ["a", "b"])
        self.assertEqual([x["nom"] for x in p["projets"]], ["Projet A", "Projet B"])
        # La pastille est le total du Directeur : ici une décision de fonctionnalité.
        self.assertEqual([x["attente"] for x in p["projets"]], [1, 1])
        self.assertEqual([x["erreur"] for x in p["projets"]], [None, None])
        self.assertEqual(p["projets"][0]["attente"], self.json("/api/etat?projet=a")["directeur"]["total"])
        # Relevé invalide (sans nom de projet) : l'id tient lieu de nom, et l'erreur est dite.
        r = dict(RELEVE, projet="")
        (self.dossier("b") / "releve.json").write_text(json.dumps(r), encoding="utf-8")
        self.srv.projets["b"]._cache_etat = (0.0, None)
        b = self.json("/api/projets")["projets"][1]
        self.assertEqual(b["nom"], "b")
        self.assertIn("projet", b["erreur"])

    def test_isolation_des_projets(self):
        avant_a = (self.dossier("a") / "reglages.json").read_bytes()
        # Une demande pour B ne lance que la commande de B.
        statut, corps = self.post("/api/demande?projet=b", {"type": "message", "fonctionnalite": "f1",
                                                            "texte": "Pour B"})
        self.assertEqual((statut, corps), (200, {"ok": True}))
        self.assertTrue((self.dossier("b") / "notes.log").exists())
        self.assertFalse((self.dossier("a") / "notes.log").exists())
        # L'image demandée à B vient de B, celle de A de A (même chemin relatif).
        r, data = self.req("GET", "/api/image?projet=b&chemin=img/x.png")
        self.assertEqual((r.status, data), (200, PNG_B))
        r, data = self.req("GET", "/api/image?projet=a&chemin=img/x.png")
        self.assertEqual((r.status, data), (200, PNG_A))
        # Le réglage de charge envoyé à B ne touche que B.
        statut, corps = self.post("/api/reglages?projet=b", {"charge_max": 40})
        self.assertEqual((statut, corps["charge_max"]), (200, 40))
        self.assertEqual(json.loads((self.dossier("b") / "reglages.json").read_text(encoding="utf-8"))
                         ["charge_max"], 40)
        self.assertEqual((self.dossier("a") / "reglages.json").read_bytes(), avant_a)
        self.assertEqual(self.json("/api/charge?projet=b")["max"], 40)
        self.assertEqual(self.json("/api/charge?projet=a")["max"], 75)
        # Une demande refusée pour B (fonctionnalité inconnue de B) n'atteint pas A non plus.
        r = dict(RELEVE, projet="Projet B", fonctionnalites=[])
        (self.dossier("b") / "releve.json").write_text(json.dumps(r), encoding="utf-8")
        self.srv.projets["b"]._cache_etat = (0.0, None)
        statut, _ = self.post("/api/demande?projet=b", {"type": "message", "fonctionnalite": "f1", "texte": "x"})
        self.assertEqual(statut, 400)
        self.assertFalse((self.dossier("a") / "notes.log").exists())
        # Les fichiers que le bureau écrit restent à côté des réglages de chaque projet.
        self.json("/api/etat?projet=a")
        self.json("/api/etat?projet=b")
        self.assertTrue((self.dossier("a") / "equipe.json").exists())
        self.assertTrue((self.dossier("b") / "equipe.json").exists())
        self.assertFalse((self.tmp / "equipe.json").exists())

    def test_projet_absent_donne_le_premier(self):
        self.assertEqual(self.json("/api/etat")["projet"], "Projet A")
        self.assertEqual(self.json("/api/etat?projet=b")["projet"], "Projet B")

    def test_projet_inconnu_404(self):
        for chemin in ("/api/etat", "/api/charge", "/api/conseil", "/api/facturation", "/api/kpi",
                       "/api/image?chemin=img/x.png&"):
            for q in ("projet=c", "projet=", "projet=a&projet=b"):
                sep = "&" if "?" in chemin else "?"
                with self.subTest(chemin=chemin, q=q):
                    self.assertEqual(self.json(chemin + sep + q, 404), {"erreur": "Projet inconnu."})
        for chemin in ("/api/demande?projet=c", "/api/reglages?projet=c"):
            statut, corps = self.post(chemin, {"type": "pause", "etat": "pause"} if "demande" in chemin
                                      else {"charge_max": 40})
            self.assertEqual((statut, corps), (404, {"erreur": "Projet inconnu."}))
        self.assertFalse((self.dossier("a") / "notes.log").exists())
        self.assertFalse((self.dossier("b") / "notes.log").exists())

    def test_projet_casse_n_arrete_pas_l_autre(self):
        (self.dossier("a") / "reglages.json").write_text("{", encoding="utf-8")
        self.srv.projets["a"]._cache_etat = (0.0, None)
        p = self.json("/api/projets")["projets"]
        self.assertTrue(p[0]["erreur"])
        self.assertEqual(p[0]["nom"], "a")
        self.assertIsNone(p[1]["erreur"])
        self.assertEqual(self.json("/api/etat?projet=b")["projet"], "Projet B")
        statut, _ = self.post("/api/demande?projet=b", {"type": "message", "fonctionnalite": "f1", "texte": "ok"})
        self.assertEqual(statut, 200)

    def test_releve_lent_n_arrete_pas_l_autre(self):
        regl = json.loads((self.dossier("a") / "reglages.json").read_text(encoding="utf-8"))
        regl["releve"] = {"commande": [sys.executable, "-c", "import time; time.sleep(3)"]}
        (self.dossier("a") / "reglages.json").write_text(json.dumps(regl), encoding="utf-8")
        self.srv.projets["a"]._cache_etat = (0.0, None)
        lent = threading.Thread(target=self.srv.projets["a"].etat, daemon=True)
        lent.start()
        time.sleep(0.3)
        debut = time.monotonic()
        self.assertEqual(self.json("/api/etat?projet=b")["projet"], "Projet B")
        self.assertLess(time.monotonic() - debut, 2)
        lent.join(15)

    def test_api_projets_ne_relit_pas_en_serie(self):
        # Un relevé lent (1,5 s) : la liste des projets sert le dernier état connu et relit en arrière-plan.
        regl = json.loads((self.dossier("a") / "reglages.json").read_text(encoding="utf-8"))
        regl["releve"] = {"commande": [sys.executable, "-c",
                                       "import time, sys; time.sleep(1.5); sys.stdout.write(open('releve.json').read())"],
                          "dossier": "."}
        (self.dossier("a") / "reglages.json").write_text(json.dumps(regl), encoding="utf-8")
        self.srv.projets["a"]._cache_etat = (0.0, None)
        self.assertEqual(self.json("/api/projets")["projets"][0]["nom"], "Projet A")  # première fois : on attend
        for _ in range(2):
            for p in self.srv.projets.values():  # états périmés
                p._cache_etat = (0.0, p._cache_etat[1])
            debut = time.monotonic()
            p = self.json("/api/projets")["projets"]
            self.assertLess(time.monotonic() - debut, 0.8)
            self.assertEqual([x["nom"] for x in p], ["Projet A", "Projet B"])
            time.sleep(1.8)  # laisse finir la relecture d'arrière-plan

    def test_une_seule_sonde(self):
        self.assertFalse(any(hasattr(p, "sonde") or hasattr(p, "lisseur") for p in self.srv.projets.values()))
        self.assertIsInstance(self.srv.sonde, charge.Sonde)
        # Chaque mesure rangée va dans l'historique de charge de chaque projet.
        self.srv._ranger_mesure(time.time(), {"cpu": 30.0, "memoire": 40.0}, historique=True)
        for nom in ("a", "b"):
            lignes = (self.dossier(nom) / "charge-historique.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lignes), 1, nom)
        self.assertEqual(self.json("/api/charge?projet=a")["charge"], self.json("/api/charge?projet=b")["charge"])

    def test_une_seule_sonde_creee(self):
        creees = []

        class Compteuse(charge.Sonde):
            def __init__(self):
                creees.append(self)
                super().__init__()

        origine = charge.Sonde
        charge.Sonde = Compteuse
        try:
            srv = serveur.creer(bureau=self.fichier, port=0)
            srv.server_close()
        finally:
            charge.Sonde = origine
        self.assertEqual(len(creees), 1)


class TestReglagesSeul(unittest.TestCase):
    def test_reglages_seul_multi_faux(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
            copie_demo(Path(t) / "demo")
            srv = serveur.creer(Path(t) / "demo" / "reglages.json", port=0, ouvrir=SourceSimulee())
            try:
                self.assertEqual(list(srv.projets), ["projet"])
                self.assertIs(srv.multi, False)
            finally:
                srv.server_close()

    def test_lancer_options_exclusives(self):
        sortie = io.StringIO()
        with redirect_stderr(sortie), self.assertRaises(SystemExit):
            serveur.main(["serveur", "--reglages", "a.json", "--bureau", "b.json"])
        with redirect_stderr(sortie), self.assertRaises(SystemExit):
            serveur.main(["serveur"])

    def test_lancer_bureau_illisible(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "bureau.json"
            f.write_text("{", encoding="utf-8")
            sortie = io.StringIO()
            with redirect_stdout(sortie):
                self.assertEqual(serveur.main(["serveur", "--bureau", str(f)]), 2)
            self.assertIn("illisible", sortie.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
