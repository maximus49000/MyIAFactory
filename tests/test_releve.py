import copy
import json
import sys
import tempfile
import time
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
               ("champ manquant", lambda r: r.pop("colonnes")),
               # Champs facultatifs de mauvais type : la page s'y casserait.
               ("file pas un objet", lambda r: r.update(file=[])),
               ("file.visibles pas une liste", lambda r: r.update(file={"visibles": 3})),
               ("file.visibles avec null", lambda r: r.update(file={"visibles": [None]})),
               ("file.visibles sans id", lambda r: r.update(file={"visibles": [{"titre": "T"}]})),
               ("file.visibles titre", lambda r: r.update(file={"visibles": [{"id": "q", "titre": 3}]})),
               ("file.reste texte", lambda r: r.update(file={"reste": "beaucoup"})),
               ("file.reste négatif", lambda r: r.update(file={"reste": -1})),
               ("decisions texte", lambda r: r.update(decisions="2")),
               ("decisions booléen", lambda r: r.update(decisions=True)),
               ("postit texte", lambda r: r["taches"][0].update(postit="oui")),
               ("etape nombre", lambda r: r["taches"][0].update(etape=3)),
               ("maj nombre", lambda r: r["taches"][0].update(maj=20261110)),
               ("nom de service", lambda r: r["services"][0].update(nom=None)),
               ("nom de colonne", lambda r: r["colonnes"][0].update(nom=["A"])),
               ("modele", lambda r: r["titulaires"][0].update(modele={"x": 1})),
               ("permanent", lambda r: r["titulaires"][0].update(permanent="oui")),
               ("fraicheur_min", lambda r: r["titulaires"][0].update(fraicheur_min="30")),
               ("factory.depuis", lambda r: r["factory"].update(depuis=3))]
        for nom, casser in cas:
            r = copy.deepcopy(BASE)
            casser(r)
            self.assertTrue(releve.valider(r), nom)

    def test_champs_facultatifs_bien_formes(self):
        r = copy.deepcopy(BASE)
        r["factory"]["depuis"] = "2026-11-10T09:00:00"
        r["file"] = {"visibles": [{"id": "q1", "titre": "Q"}], "reste": 4}
        r["decisions"] = 2
        r["taches"][0].update(postit=False, etape=None, maj=None)
        r["titulaires"][0].update(modele="Sonnet", permanent=True, fraicheur_min=12.5)
        self.assertEqual(releve.valider(r), [])

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

    def _avec_delai_court(self):
        ancien = releve.DELAI_COMMANDE_S
        releve.DELAI_COMMANDE_S = 1
        self.addCleanup(setattr, releve, "DELAI_COMMANDE_S", ancien)

    def test_obtenir_commande_trop_longue(self):
        self._avec_delai_court()
        cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
        debut = time.monotonic()
        r, err = releve.obtenir(self.regl({"commande": cmd}))
        self.assertIsNone(r)
        self.assertIn("dépassé", err)
        self.assertLess(time.monotonic() - debut, 6)

    def test_obtenir_commande_dont_un_descendant_garde_la_sortie(self):
        # La commande lance un sous-processus qui hérite de sa sortie et dort : le délai doit tenir.
        self._avec_delai_court()
        enfant = "import time; time.sleep(30)"
        parent = ("import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', %r]); "
                  "time.sleep(30)") % enfant
        debut = time.monotonic()
        r, err = releve.obtenir(self.regl({"commande": [sys.executable, "-c", parent]}))
        self.assertIsNone(r)
        self.assertIn("dépassé", err)
        self.assertLess(time.monotonic() - debut, 6)

    def test_obtenir_fichier_avec_bom(self):
        (self.tmp / "r.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(BASE).encode("utf-8"))
        r, err = releve.obtenir(self.regl({"fichier": "r.json"}))
        self.assertIsNone(err)
        self.assertEqual(r["projet"], "P")

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
