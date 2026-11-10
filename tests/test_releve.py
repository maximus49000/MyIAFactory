import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

from bureau import releve

RACINE = Path(__file__).resolve().parent.parent

BASE = {"version": 1, "projet": "P", "factory": {"etat": "en marche"},
        "services": [{"id": "dev", "nom": "Dev"}], "colonnes": [{"id": "a", "nom": "A"}],
        "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}],
        "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"}]}


class TestValider(unittest.TestCase):
    def test_base_valide(self):
        self.assertEqual(releve.valider(BASE), [])

    def test_erreurs(self):
        cas = [("colonne inconnue", lambda r: r["taches"][0].update(colonne="z")),
               ("titulaire inconnu", lambda r: r["taches"][0].update(titulaire="x")),
               ("etat factory", lambda r: r["factory"].update(etat="arrêt")),
               ("lieu", lambda r: r["titulaires"][0].update(lieu="lune")),
               ("service inconnu", lambda r: r["titulaires"][0].update(service="rh")),
               ("doublon", lambda r: r["taches"].append(dict(r["taches"][0]))),
               ("7 services", lambda r: r.update(services=[{"id": str(i), "nom": "S"} for i in range(7)])),
               ("deux chefs", lambda r: r["titulaires"].extend([{"cle": "c1", "lieu": "local", "chef": True}, {"cle": "c2", "lieu": "local", "chef": True}])),
               ("champ manquant", lambda r: r.pop("colonnes"))]
        for nom, casser in cas:
            r = copy.deepcopy(BASE)
            casser(r)
            self.assertTrue(releve.valider(r), nom)

    def test_valider_ne_plante_pas_sur_n_importe_quoi(self):
        for r in (None, [], "x", {"taches": 3}, {"version": 1, "taches": [None]}):
            self.assertTrue(releve.valider(r))


class TestNormaliser(unittest.TestCase):
    def test_normaliser_ajoute_chef_et_defauts(self):
        n = releve.normaliser(BASE)
        self.assertIn("chef", [t["cle"] for t in n["titulaires"]])
        self.assertEqual((n["taches"][0]["postit"], n["file"], n["decisions"]),
                         (True, {"visibles": [], "reste": 0}, 0))
        self.assertEqual(n["titulaires"][0]["modele"], "?")
        self.assertNotIn("file", BASE)
        self.assertEqual(len(BASE["titulaires"]), 1)


class TestObtenir(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)

    def regl(self, source):
        return {"releve": source, "dossier": str(self.tmp)}

    def test_obtenir_fichier(self):
        (self.tmp / "r.json").write_text(json.dumps(BASE), encoding="utf-8")
        r, err = releve.obtenir(self.regl({"fichier": "r.json"}))
        self.assertIsNone(err)
        self.assertEqual(r["projet"], "P")

    def test_obtenir_fichier_absent(self):
        r, err = releve.obtenir(self.regl({"fichier": "absent.json"}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def test_obtenir_json_tronque(self):
        (self.tmp / "r.json").write_text('{"version": 1, "ta', encoding="utf-8")
        r, err = releve.obtenir(self.regl({"fichier": "r.json"}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def test_obtenir_invalide(self):
        b = copy.deepcopy(BASE)
        b["taches"][0]["colonne"] = "zzz"
        (self.tmp / "r.json").write_text(json.dumps(b), encoding="utf-8")
        r, err = releve.obtenir(self.regl({"fichier": "r.json"}))
        self.assertIsNone(r)
        self.assertIn("zzz", err)

    def test_obtenir_commande(self):
        cmd = [sys.executable, "-c", "import json,sys; print(json.dumps(%r))" % BASE]
        r, err = releve.obtenir(self.regl({"commande": cmd, "dossier": "."}))
        self.assertIsNone(err)
        self.assertEqual(r["projet"], "P")

    def test_obtenir_commande_en_echec(self):
        cmd = [sys.executable, "-c", "import sys; sys.exit(1)"]
        r, err = releve.obtenir(self.regl({"commande": cmd}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def test_obtenir_commande_introuvable(self):
        r, err = releve.obtenir(self.regl({"commande": ["commande-qui-n-existe-pas"]}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def test_obtenir_sans_source(self):
        r, err = releve.obtenir(self.regl({}))
        self.assertIsNone(r)
        self.assertTrue(err)

    def test_exemple_demo_valide(self):
        d = json.loads((RACINE / "exemples" / "demo" / "releve.json").read_text(encoding="utf-8"))
        self.assertEqual(releve.valider(d), [])


if __name__ == "__main__":
    unittest.main()
