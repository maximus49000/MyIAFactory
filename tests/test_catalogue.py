"""Le catalogue d'une fonctionnalité et le dernier livrable, servis par le bureau."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from bureau import catalogue
from tests.test_bureau_multi import AvecBureau, RELEVE
from tests import test_serveur
from tests.test_serveur import AvecServeur

ELEMENT_COMPLET = {
    "id": "e1", "nom": "Élément un", "groupe": "g1", "etat": "fait", "note": "<b>texte</b>",
    "caracteristiques": [{"libelle": "Couleur", "valeur": "#aa3300"}, {"libelle": "Hauteur", "valeur": 12}],
    "captures": [{"chemin": "images/e1.png", "passe": 2}],
    "comparaisons": [{"angle": "face", "reel": "images/r1.jpg", "produit": "images/p1.png",
                      "credit": "Photo libre", "lien": "https://exemple.org/photo"}],
    "liens": [{"libelle": "Réf", "url": "https://exemple.org"}],
    "kit": ["k1"], "evenement": "fête", "lecons_appliquees": ["l1"], "a_reevaluer": ["l2"],
    "doute": {"date": "2026-11-01", "raison": "hauteur", "leve_par": "une photo"},
    "retours": [{"t": "2026-11-02T10:00:00+01:00", "texte": "plus haut", "etat": "fait", "reponse": "ok"}],
    "position": {"x": 1.5, "y": -2}, "passes": [1, 2]}
CATALOGUE = {"groupes": [{"id": "g1", "nom": "Groupe un"}], "elements": [ELEMENT_COMPLET],
             "passes": [{"numero": 1, "date": "2026-10-01", "titre": "Première"}],
             "lecons": [{"id": "l1", "titre": "T", "texte": "x", "portee": "groupe", "passe": 1}],
             "kit": [{"id": "k1", "nom": "Kit", "description": "d"}],
             "trace": [{"nom": "rue", "points": [[0, 0], [1, 2.5]]}]}


class TestCatalogueModule(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        catalogue.vider_cache()

    def regl(self, **extra):
        return {"dossier": str(self.tmp), **extra}

    def ecrire(self, nom, objet):
        f = self.tmp / nom
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(objet if isinstance(objet, str) else json.dumps(objet), encoding="utf-8")
        return f

    def test_declaration_par_reglages(self):
        regl = self.regl(catalogues={"f1": {"fichier": "cat.json"}})
        d = catalogue.declaration(regl, "f1")
        self.assertEqual(d["fichier"], "cat.json")
        self.assertEqual(Path(d["base"]), self.tmp)
        self.assertIsNone(catalogue.declaration(regl, "f2"))
        self.assertIsNone(catalogue.declaration(self.regl(), "f1"))
        # Une déclaration mal formée n'est pas une déclaration.
        for mauvaise in ({}, {"fichier": 3}, {"commande": "pas une liste"}, {"commande": []},
                         {"fichier": "a.json", "commande": ["x"]}, "cat.json"):
            self.assertIsNone(catalogue.declaration(self.regl(catalogues={"f1": mauvaise}), "f1"), mauvaise)

    def test_declaration_par_fichier_de_factory(self):
        self.ecrire("depot/factory.json", {"catalogues": {"f1": {"commande": ["x"], "dossier": "outils"}}})
        regl = self.regl(orchestrateur="depot/factory.json")
        d = catalogue.declaration(regl, "f1")
        self.assertEqual(d["commande"], ["x"])
        self.assertEqual(Path(d["base"]), self.tmp / "depot")  # chemins relatifs au fichier de factory
        # Les réglages l'emportent sur le fichier de factory.
        regl["catalogues"] = {"f1": {"fichier": "cat.json"}}
        self.assertEqual(catalogue.declaration(regl, "f1")["fichier"], "cat.json")
        # Fichier de factory absent ou illisible : pas de déclaration, sans erreur.
        self.assertIsNone(catalogue.declaration(self.regl(orchestrateur="absent.json"), "f1"))
        self.ecrire("casse.json", "{")
        self.assertIsNone(catalogue.declaration(self.regl(orchestrateur="casse.json"), "f1"))

    def test_declaration_generique(self):
        # « * » vaut pour toute fonctionnalité ; {fonctionnalite} y est remplacé par son identifiant.
        self.ecrire("depot/factory.json", {"catalogues": {
            "*": {"commande": ["outil", "catalogue", "{fonctionnalite}"]},
            "f9": {"fichier": "f9.json"}}})
        regl = self.regl(orchestrateur="depot/factory.json")
        d = catalogue.declaration(regl, "f3")
        self.assertEqual(d["commande"], ["outil", "catalogue", "f3"])
        self.assertEqual(Path(d["base"]), self.tmp / "depot")
        self.assertEqual(catalogue.declaration(regl, "f9")["fichier"], "f9.json")   # l'exacte l'emporte
        # Une déclaration exacte des réglages l'emporte aussi sur « * » ; « * » des réglages sur celui de la factory.
        regl["catalogues"] = {"f3": {"fichier": "f3.json"}}
        self.assertEqual(catalogue.declaration(regl, "f3")["fichier"], "f3.json")
        regl["catalogues"] = {"*": {"fichier": "cat-{fonctionnalite}.json"}}
        self.assertEqual(catalogue.declaration(regl, "f4")["fichier"], "cat-f4.json")
        # Un identifiant qui pourrait sortir du dossier ou passer pour une option n'a pas de catalogue générique.
        for mauvais in ("../x", "a/b", "a\\b", "-x", "", "é", "x" * 65, "a b"):
            self.assertIsNone(catalogue.declaration(regl, mauvais), mauvais)

    def test_fichier_cache_puis_relu(self):
        f = self.ecrire("cat.json", CATALOGUE)
        regl = self.regl(catalogues={"f1": {"fichier": "cat.json"}})
        code, objet = catalogue.lire(regl, "f1")
        self.assertEqual(code, 200)
        self.assertEqual(objet["catalogue"]["elements"][0]["nom"], "Élément un")
        lus = []
        origine = catalogue._analyser
        catalogue._analyser = lambda octets: lus.append(1) or origine(octets)
        try:
            self.assertEqual(catalogue.lire(regl, "f1"), (code, objet))
            self.assertEqual(lus, [])  # même date, même taille : rien n'est relu
            nouveau = dict(CATALOGUE, elements=[dict(ELEMENT_COMPLET, nom="Renommé, plus long")])
            f.write_text(json.dumps(nouveau), encoding="utf-8")
            st = f.stat()
            os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
            code, objet = catalogue.lire(regl, "f1")
            self.assertEqual(lus, [1])
            self.assertEqual(objet["catalogue"]["elements"][0]["nom"], "Renommé, plus long")
        finally:
            catalogue._analyser = origine

    def test_commande_cache_30_s(self):
        compteur = self.tmp / "compte.txt"
        script = ("import json, pathlib, sys\n"
                  "p = pathlib.Path(sys.argv[1]); p.write_text(p.read_text() + 'x' if p.exists() else 'x')\n"
                  "print(json.dumps({'elements': [{'id': 'a', 'nom': 'A'}]}))\n")
        self.ecrire("outils/cat.py", script)
        regl = self.regl(catalogues={"f1": {"commande": [sys.executable, "cat.py", str(compteur)],
                                            "dossier": "outils"}})
        self.assertEqual(catalogue.lire(regl, "f1")[0], 200)
        self.assertEqual(catalogue.lire(regl, "f1")[0], 200)
        self.assertEqual(compteur.read_text(), "x")  # lancée une seule fois
        catalogue._cache_commandes = {k: (t - catalogue.CACHE_COMMANDE_S - 1, v)
                                      for k, (t, v) in catalogue._cache_commandes.items()}
        self.assertEqual(catalogue.lire(regl, "f1")[0], 200)
        self.assertEqual(compteur.read_text(), "xx")

    def test_commande_en_echec_502(self):
        for cmd in ([sys.executable, "-c", "import sys; sys.stderr.write('panne'); sys.exit(3)"],
                    [str(self.tmp / "absente.exe")]):
            catalogue.vider_cache()
            code, objet = catalogue.lire(self.regl(catalogues={"f1": {"commande": cmd}}), "f1")
            self.assertEqual(code, 502, objet)
            self.assertTrue(objet["erreur"])

    def test_elements_absents_422(self):
        cas = {"illisible": "{", "pas un objet": [], "sans elements": {"groupes": []},
               "elements pas liste": {"elements": {}}, "id manquant": {"elements": [{"nom": "a"}]},
               "nom non texte": {"elements": [{"id": "a", "nom": 3}]},
               "ids doubles": {"elements": [{"id": "a", "nom": "A"}, {"id": "a", "nom": "B"}]},
               "élément non objet": {"elements": ["a"]},
               "trop d'éléments": {"elements": [{"id": str(i), "nom": "n"}
                                                for i in range(catalogue.MAX_ELEMENTS + 1)]}}
        for nom, contenu in cas.items():
            with self.subTest(nom):
                catalogue.vider_cache()
                self.ecrire("cat.json", contenu)
                code, objet = catalogue.lire(self.regl(catalogues={"f1": {"fichier": "cat.json"}}), "f1")
                self.assertEqual(code, 422, objet)
                self.assertTrue(objet["erreur"])
        catalogue.vider_cache()
        code, _ = catalogue.lire(self.regl(catalogues={"f1": {"fichier": "absent.json"}}), "f1")
        self.assertEqual(code, 422)
        self.assertEqual(catalogue.lire(self.regl(), "f1")[0], 404)

    def test_trop_gros_422(self):
        f = self.tmp / "cat.json"
        with open(f, "wb") as sortie:
            sortie.truncate(catalogue.MAX_OCTETS + 1)
        code, objet = catalogue.lire(self.regl(catalogues={"f1": {"fichier": "cat.json"}}), "f1")
        self.assertEqual(code, 422)

    def test_catalogue_complet_inchange(self):
        propre, avertissements = catalogue.valider(json.loads(json.dumps(CATALOGUE)))
        self.assertEqual(avertissements, [])
        self.assertEqual(propre, CATALOGUE)

    def test_champ_facultatif_faux_retire_et_signale(self):
        mauvais = {"groupe": 3, "caracteristiques": "rouge", "captures": [{"chemin": 3}], "position": {"x": "a"},
                   "passes": ["un"], "doute": "oui", "kit": [1], "retours": [{"etat": "fait"}],
                   "inconnu": "gardé ? non"}
        c = {"elements": [dict({"id": "e1", "nom": "E"}, **mauvais)], "groupes": "g", "passes": [{"titre": "x"}]}
        propre, avertissements = catalogue.valider(c)
        e = propre["elements"][0]
        self.assertEqual(e, {"id": "e1", "nom": "E"})
        self.assertNotIn("groupes", propre)
        self.assertNotIn("passes", propre)
        texte = " ".join(avertissements)
        for champ in ("groupe", "caracteristiques", "captures", "position", "passes", "doute", "kit", "retours",
                      "groupes"):
            self.assertIn(champ, texte)
        self.assertIn("elements[0]", texte)

    def test_reel_adresse_retiree(self):
        el = {"id": "e1", "nom": "E",
              "comparaisons": [{"angle": "face", "reel": "https://exemple.org/r.jpg", "produit": "images/p.png"},
                               {"angle": "dos", "reel": "C:/photos/r.jpg", "produit": "/etc/p.png"}],
              "captures": [{"chemin": "data:image/png;base64,AAAA"}, {"chemin": "images/ok.png"}],
              "liens": [{"libelle": "x", "url": "javascript:alert(1)"}, {"libelle": "y", "url": "https://ok.org"}]}
        propre, avertissements = catalogue.valider({"elements": [el]})
        e = propre["elements"][0]
        self.assertEqual(e["comparaisons"], [{"angle": "face", "produit": "images/p.png"}, {"angle": "dos"}])
        self.assertEqual(e["captures"], [{"chemin": "images/ok.png"}])
        self.assertEqual(e["liens"], [{"libelle": "y", "url": "https://ok.org"}])
        texte = " ".join(avertissements)
        self.assertIn("comparaisons[0].reel", texte)
        self.assertIn("captures[0]", texte)
        self.assertIn("liens[0]", texte)

    def test_avertissements_bornes(self):
        c = {"elements": [{"id": str(i), "nom": "n", "groupe": 1} for i in range(5000)]}
        propre, avertissements = catalogue.valider(c)
        self.assertLessEqual(len(avertissements), catalogue.MAX_AVERTISSEMENTS + 1)
        self.assertIn("4", avertissements[-1])  # « … et 4 900 autres »


class TestCatalogueServi(AvecServeur):
    SCRIPT_ACTIONS = test_serveur.TestServeur.SCRIPT_ACTIONS
    agir, demande = test_serveur.TestServeur.agir, test_serveur.TestServeur.demande

    def setUp(self):
        catalogue.vider_cache()
        super().setUp()
        self.dossier = self.tmp / "demo"

    def declarer(self, contenu, **reglages_en_plus):
        (self.dossier / "cat.json").write_text(json.dumps(contenu), encoding="utf-8")
        regl = json.loads(self.regl.read_text(encoding="utf-8"))
        regl["catalogues"] = {"f1": {"fichier": "cat.json"}}
        regl.update(reglages_en_plus)
        self.regl.write_text(json.dumps(regl), encoding="utf-8")
        self.p._cache_etat = (0.0, None)

    def test_catalogue_servi(self):
        self.declarer(CATALOGUE)
        c = self.json("/api/catalogue?fonctionnalite=f1")
        self.assertEqual(c, {"catalogue": CATALOGUE, "avertissements": []})
        r, _ = self.req("GET", "/api/catalogue?fonctionnalite=f2")
        self.assertEqual(r.status, 404)
        r, _ = self.req("GET", "/api/catalogue")
        self.assertEqual(r.status, 404)
        r, _ = self.req("GET", "/api/catalogue?fonctionnalite=f1&projet=autre")
        self.assertEqual(r.status, 404)

    def test_catalogue_5000(self):
        elements = [dict(ELEMENT_COMPLET, id=f"e{i}", nom=f"Élément {i}", position={"x": i % 70, "y": i // 70})
                    for i in range(5000)]
        self.declarer(dict(CATALOGUE, elements=elements))
        debut = time.monotonic()
        c = self.json("/api/catalogue?fonctionnalite=f1")
        self.assertLess(time.monotonic() - debut, 2)
        self.assertEqual(len(c["catalogue"]["elements"]), 5000)
        self.assertEqual(c["avertissements"], [])

    def test_retour_element_inconnu_400(self):
        r = json.loads(json.dumps(RELEVE))
        r["fonctionnalites"][0]["catalogue"] = True
        notes = self.agir(releve=r)
        self.declarer({"elements": [{"id": "e1", "nom": "E"}]})
        statut, corps = self.demande({"type": "retour_element", "fonctionnalite": "f1", "element": "e9",
                                      "texte": "x"})
        self.assertEqual(statut, 400, corps)
        self.assertFalse(notes.exists())
        statut, corps = self.demande({"type": "retour_element", "fonctionnalite": "f1", "element": "e1",
                                      "texte": "plus haut"})
        self.assertEqual((statut, corps), (200, {"ok": True}))
        self.assertTrue(notes.exists())
        # Catalogue illisible : refusé, la commande n'est pas lancée.
        (self.dossier / "cat.json").write_text("{", encoding="utf-8")
        catalogue.vider_cache()
        statut, corps = self.demande({"type": "retour_element", "fonctionnalite": "f1", "element": "e1",
                                      "texte": "encore"})
        self.assertEqual(statut, 400)
        self.assertIn("Catalogue indisponible", corps["erreur"])

    def livrable(self, chemin, contenu=b"x", racines=("livrables",), sur_fonctionnalite=False):
        f = self.dossier / chemin
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(contenu)
        r = json.loads(json.dumps(RELEVE))
        liv = {"libelle": "Dernier", "chemin": chemin, "date": "2026-11-10"}
        if sur_fonctionnalite:
            r["fonctionnalites"][0]["livrable"] = liv
        else:
            r["livrable"] = liv
        self.agir(releve=r)
        regl = json.loads(self.regl.read_text(encoding="utf-8"))
        regl["livrables"] = {"racines": list(racines)}
        self.regl.write_text(json.dumps(regl), encoding="utf-8")
        self.p._cache_etat = (0.0, None)

    def test_livrable_html_bac_a_sable(self):
        page = b"<html><script>alert(1)</script></html>"
        self.livrable("livrables/page.html", page)
        r, data = self.req("GET", "/api/livrable")
        self.assertEqual(r.status, 200)
        self.assertEqual(data, page)
        self.assertEqual(r.getheader("Content-Type"), "text/html; charset=utf-8")
        self.assertEqual(r.getheader("Content-Security-Policy"), "sandbox")
        self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")
        self.assertIsNone(r.getheader("Content-Disposition"))

    def test_livrable_txt_bac_a_sable(self):
        self.livrable("livrables/notes.txt", b"bonjour")
        r, data = self.req("GET", "/api/livrable")
        self.assertEqual((r.status, data), (200, b"bonjour"))
        self.assertEqual(r.getheader("Content-Type"), "text/plain; charset=utf-8")
        self.assertEqual(r.getheader("Content-Security-Policy"), "sandbox")
        self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")

    def test_livrable_zip_en_piece_jointe(self):
        self.livrable("livrables/paquet.zip", b"PK\x03\x04")
        r, data = self.req("GET", "/api/livrable")
        self.assertEqual((r.status, data), (200, b"PK\x03\x04"))
        self.assertEqual(r.getheader("Content-Type"), "application/zip")
        self.assertTrue(r.getheader("Content-Disposition").startswith("attachment"))
        self.assertIn("paquet.zip", r.getheader("Content-Disposition"))

    def test_livrable_de_la_fonctionnalite(self):
        self.livrable("livrables/f.pdf", b"%PDF-1.4", sur_fonctionnalite=True)
        r, data = self.req("GET", "/api/livrable?fonctionnalite=f1")
        self.assertEqual((r.status, data, r.getheader("Content-Type")), (200, b"%PDF-1.4", "application/pdf"))
        r, _ = self.req("GET", "/api/livrable")  # le projet n'a pas de livrable à lui
        self.assertEqual(r.status, 404)
        r, _ = self.req("GET", "/api/livrable?fonctionnalite=f9")
        self.assertEqual(r.status, 404)

    def document(self, chemin, contenu=b"x", racines=("pieces",), liste=None):
        f = self.dossier / chemin
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(contenu)
        r = json.loads(json.dumps(RELEVE))
        r["fonctionnalites"][0]["documents"] = [{"chemin": c, "titre": "Doc"} for c in (liste or [chemin])]
        self.agir(releve=r)
        regl = json.loads(self.regl.read_text(encoding="utf-8"))
        regl["documents"] = {"racines": list(racines)}
        self.regl.write_text(json.dumps(regl), encoding="utf-8")
        self.p._cache_etat = (0.0, None)

    def test_document_servi(self):
        # Un document de la fonctionnalité : servi s'il est listé par le relevé et dans une racine `documents`.
        self.document("pieces/f1/methode.md", b"# M <script>x</script>")
        r, data = self.req("GET", "/api/document?fonctionnalite=f1&chemin=pieces/f1/methode.md")
        self.assertEqual((r.status, data), (200, b"# M <script>x</script>"))
        self.assertEqual(r.getheader("Content-Type"), "text/plain; charset=utf-8")
        self.assertEqual(r.getheader("Content-Security-Policy"), "sandbox")
        self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")
        self.document("pieces/f1/m.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>x</script></svg>")
        r, _ = self.req("GET", "/api/document?fonctionnalite=f1&chemin=pieces/f1/m.svg")
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "image/svg+xml"))
        self.assertEqual(r.getheader("Content-Security-Policy"), "sandbox")
        self.document("pieces/f1/m.png", bytes.fromhex("89504e470d0a1a0a"))
        r, _ = self.req("GET", "/api/document?fonctionnalite=f1&chemin=pieces/f1/m.png")
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "image/png"))

    def test_couts_d_une_fonctionnalite(self):
        r = json.loads(json.dumps(RELEVE))
        r["taches"][0]["fonctionnalite"] = "f1"
        r["usage"] = [{"id": "u1", "tache": r["taches"][0]["id"], "agent": None, "modele": "modele-sans-prix",
                       "t": "2026-11-10T10:00:00+01:00", "entree": 10, "sortie": 1}]
        self.agir(releve=r)
        self.p._cache_etat = (0.0, None)
        c = self.json("/api/couts?fonctionnalite=f1")
        self.assertTrue(c["disponible"])
        self.assertEqual([t["id"] for t in c["taches"]], [r["taches"][0]["id"]])
        self.assertEqual(c["sans_prix"], 1)   # un modèle sans prix n'est jamais compté à zéro sans le dire
        for requete in ("", "?fonctionnalite=f1&fonctionnalite=f2"):
            resp, _ = self.req("GET", "/api/couts" + requete)
            self.assertEqual(resp.status, 404)

    def test_document_refuse(self):
        self.document("pieces/f1/a.md", liste=["pieces/f1/a.md"])
        (self.dossier / "pieces" / "f1" / "b.md").write_bytes(b"secret")
        (self.dossier / "ailleurs").mkdir()
        (self.dossier / "ailleurs" / "c.md").write_bytes(b"x")
        for requete in ("fonctionnalite=f1&chemin=pieces/f1/b.md",     # pas dans la liste du relevé
                        "fonctionnalite=f9&chemin=pieces/f1/a.md",     # fonctionnalité inconnue
                        "chemin=pieces/f1/a.md",                       # sans fonctionnalité
                        "fonctionnalite=f1"):                          # sans chemin
            with self.subTest(requete):
                r, _ = self.req("GET", "/api/document?" + requete)
                self.assertEqual(r.status, 404)
        for chemin, racines in (("ailleurs/c.md", ("pieces",)), ("pieces/f1/x.exe", ("pieces",)),
                                ("pieces/f1/a.md", ()), ("pieces/../reglages.json", ("pieces",))):
            with self.subTest(chemin):
                self.document("pieces/f1/a.md", racines=racines, liste=[chemin])
                if chemin == "pieces/f1/x.exe":
                    (self.dossier / chemin).write_bytes(b"MZ")
                r, _ = self.req("GET", "/api/document?fonctionnalite=f1&chemin=" + chemin)
                self.assertEqual(r.status, 404)

    def test_livrable_hors_racine_404(self):
        cas = [("ailleurs/x.png", ("livrables",)),         # hors racine
               ("livrables/x.exe", ("livrables",)),        # extension refusée
               ("livrables/x.png", ()),                   # aucune racine
               ("livrables/../reglages.json", ("livrables",))]
        for chemin, racines in cas:
            with self.subTest(chemin):
                if chemin.endswith("reglages.json"):
                    self.livrable("livrables/y.png", racines=racines)
                    r = json.loads(json.dumps(RELEVE))
                    r["livrable"] = {"libelle": "x", "chemin": chemin, "date": "d"}
                    (self.dossier / "releve.json").write_text(json.dumps(r), encoding="utf-8")
                    self.p._cache_etat = (0.0, None)
                else:
                    self.livrable(chemin, racines=racines)
                r, _ = self.req("GET", "/api/livrable")
                self.assertEqual(r.status, 404)
        # Un livrable donné par un lien n'est pas servi par le bureau.
        r = json.loads(json.dumps(RELEVE))
        r["livrable"] = {"libelle": "x", "lien": "https://exemple.org", "date": "d"}
        (self.dossier / "releve.json").write_text(json.dumps(r), encoding="utf-8")
        self.p._cache_etat = (0.0, None)
        resp, _ = self.req("GET", "/api/livrable")
        self.assertEqual(resp.status, 404)


class TestCatalogueMulti(AvecBureau):
    def setUp(self):
        catalogue.vider_cache()
        super().setUp()

    def test_catalogue_autre_projet(self):
        # A déclare un catalogue pour f1 ; B n'en déclare pas : B ne lit jamais celui de A.
        d = self.dossier("a")
        (d / "cat.json").write_text(json.dumps({"elements": [{"id": "a1", "nom": "De A"}]}), encoding="utf-8")
        regl = json.loads((d / "reglages.json").read_text(encoding="utf-8"))
        regl["catalogues"] = {"f1": {"fichier": "cat.json"}}
        (d / "reglages.json").write_text(json.dumps(regl), encoding="utf-8")
        self.assertEqual(self.json("/api/catalogue?projet=a&fonctionnalite=f1")["catalogue"]["elements"][0]["id"],
                         "a1")
        r, _ = self.req("GET", "/api/catalogue?projet=b&fonctionnalite=f1")
        self.assertEqual(r.status, 404)
        # B déclare le même nom de fichier : il lit le sien, pas celui de A (ni son cache).
        d = self.dossier("b")
        (d / "cat.json").write_text(json.dumps({"elements": [{"id": "b1", "nom": "De B"}]}), encoding="utf-8")
        regl = json.loads((d / "reglages.json").read_text(encoding="utf-8"))
        regl["catalogues"] = {"f1": {"fichier": "cat.json"}}
        (d / "reglages.json").write_text(json.dumps(regl), encoding="utf-8")
        self.assertEqual(self.json("/api/catalogue?projet=b&fonctionnalite=f1")["catalogue"]["elements"][0]["id"],
                         "b1")
        # Un retour d'élément de B est vérifié contre le catalogue de B.
        r = dict(RELEVE, projet="Projet B")
        r["fonctionnalites"] = [dict(RELEVE["fonctionnalites"][0], catalogue=True)]
        (d / "releve.json").write_text(json.dumps(r), encoding="utf-8")
        self.srv.projets["b"]._cache_etat = (0.0, None)
        statut, _ = self.post("/api/demande?projet=b", {"type": "retour_element", "fonctionnalite": "f1",
                                                        "element": "a1", "texte": "x"})
        self.assertEqual(statut, 400)
        statut, _ = self.post("/api/demande?projet=b", {"type": "retour_element", "fonctionnalite": "f1",
                                                        "element": "b1", "texte": "x"})
        self.assertEqual(statut, 200)
        self.assertFalse((self.dossier("a") / "notes.log").exists())


if __name__ == "__main__":
    unittest.main()
