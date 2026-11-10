import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bureau import demandes, releve

RACINE = Path(__file__).resolve().parent.parent


class TestDemoActions(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dossier = Path(self._t.name) / "demo"
        shutil.copytree(RACINE / "exemples" / "demo", self.dossier)
        self.fichier = self.dossier / "releve.json"

    def lire(self):
        return json.loads(self.fichier.read_text(encoding="utf-8"))

    def lancer(self, demande, attendu=0):
        p = subprocess.run([sys.executable, "actions.py"], cwd=self.dossier, capture_output=True,
                           input=json.dumps({**demande, "t": "2026-11-10T12:00:00+01:00"}).encode("utf-8"),
                           timeout=20)
        self.assertEqual(p.returncode, attendu, p.stdout + p.stderr)
        r = self.lire()
        self.assertEqual(releve.valider(r), [], "le relevé doit rester valide")
        return r, p.stdout.decode("utf-8")

    def test_le_relevé_de_la_démo_est_v2_et_riche(self):
        r = self.lire()
        self.assertEqual(r["version"], 2)
        self.assertEqual(releve.valider(r), [])
        self.assertEqual(len(r["services"]), 6)
        self.assertIn("facturation", [s["id"] for s in r["services"]])
        self.assertTrue(any(a.get("lien") for a in r["actions"]))
        self.assertTrue(any(a["id"] == "pause" for a in r["actions"]))
        self.assertTrue(r["types"] and r["lecons"])
        riche = [t for t in r["taches"] if len(t.get("journal", [])) == 3 and len(t.get("images", [])) == 2
                 and t.get("liens")]
        self.assertTrue(riche)
        self.assertTrue(any(not x.get("reponse") for t in r["taches"] for x in t.get("retours", [])))
        self.assertTrue(any(t.get("bloquee") for t in r["taches"]))
        for t in r["taches"]:
            for i in t.get("images", []):
                self.assertTrue((self.dossier / i["chemin"]).is_file(), i["chemin"])
        regl = json.loads((self.dossier / "reglages.json").read_text(encoding="utf-8"))
        self.assertEqual(regl["images"]["racines"], ["images"])
        self.assertTrue(demandes.commande_declaree(regl))

    def test_pause_et_reprise(self):
        r, _ = self.lancer({"type": "bouton", "id": "pause"})
        self.assertEqual(r["factory"]["etat"], "en pause")
        self.assertEqual([a["id"] for a in r["actions"] if a.get("libelle") == "Reprendre"], ["reprendre"])
        self.assertFalse(any(a["id"] == "pause" for a in r["actions"]))
        r, _ = self.lancer({"type": "bouton", "id": "reprendre"})
        self.assertEqual(r["factory"]["etat"], "en marche")
        self.assertTrue(any(a["id"] == "pause" and a["libelle"] == "Pause" for a in r["actions"]))

    def test_deplacement(self):
        r, _ = self.lancer({"type": "deplacer", "tache": "t1", "colonne": "revue"})
        t1 = next(t for t in r["taches"] if t["id"] == "t1")
        self.assertEqual(t1["colonne"], "revue")
        self.assertNotEqual(t1["maj"], next(t for t in self.dossier_avant()["taches"] if t["id"] == "t1")["maj"])

    def dossier_avant(self):
        return json.loads((RACINE / "exemples" / "demo" / "releve.json").read_text(encoding="utf-8"))

    def test_deplacement_d_un_element_de_la_file(self):
        avant = self.lire()
        q = avant["file"]["visibles"][0]
        r, _ = self.lancer({"type": "deplacer", "tache": q["id"], "colonne": "encours"})
        t = next(t for t in r["taches"] if t["id"] == q["id"])
        self.assertEqual((t["colonne"], t["active"], t["titre"]), ("encours", True, q["titre"]))
        self.assertNotIn(q["id"], [x["id"] for x in r["file"]["visibles"]])
        self.assertEqual(len(r["file"]["visibles"]) + r["file"]["reste"],
                         len(avant["file"]["visibles"]) + avant["file"]["reste"] - 1)

    def test_deplacement_d_un_element_de_la_file_sans_titre(self):
        r = self.lire()
        q = r["file"]["visibles"][0]
        del q["titre"]  # le titre d'un élément de file est facultatif
        self.fichier.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        r, _ = self.lancer({"type": "deplacer", "tache": q["id"], "colonne": "encours"})
        t = next(t for t in r["taches"] if t["id"] == q["id"])
        self.assertEqual(t["titre"], q["id"])

    def test_retour(self):
        r, _ = self.lancer({"type": "retour", "tache": "t2", "texte": "Peux-tu préciser ?"})
        retours = next(t for t in r["taches"] if t["id"] == "t2")["retours"]
        self.assertEqual(retours[-1]["texte"], "Peux-tu préciser ?")
        self.assertEqual(retours[-1]["reponse"], "Bien reçu (démo).")

    def test_verdict_valider(self):
        avant = self.lire()
        lecon = avant["lecons"][0]
        r, _ = self.lancer({"type": "lecon", "id": lecon["id"], "verdict": "valider"})
        self.assertNotIn(lecon["id"], [x["id"] for x in r["lecons"]])
        titulaire = next(t for t in r["titulaires"] if t["cle"] == lecon["agent"])
        self.assertEqual(next(x for x in titulaire["lecons"] if x["id"] == lecon["id"])["etat"], "validée")

    def test_verdict_invalider(self):
        lecon = self.lire()["lecons"][0]
        r, _ = self.lancer({"type": "lecon", "id": lecon["id"], "verdict": "invalider"})
        self.assertNotIn(lecon["id"], [x["id"] for x in r["lecons"]])
        titulaire = next(t for t in r["titulaires"] if t["cle"] == lecon["agent"])
        self.assertNotIn(lecon["id"], [x["id"] for x in titulaire.get("lecons", [])])

    def test_demande_inconnue_refusee(self):
        avant = self.fichier.read_bytes()
        for d in ({"type": "bouton", "id": "inconnu"}, {"type": "deplacer", "tache": "zz", "colonne": "revue"},
                  {"type": "lecon", "id": "zz", "verdict": "valider"}, {"type": "autre"}):
            _, sortie = self.lancer(d, attendu=1)
            self.assertTrue(sortie.strip())
        self.assertEqual(self.fichier.read_bytes(), avant)

    def test_entree_illisible(self):
        p = subprocess.run([sys.executable, "actions.py"], cwd=self.dossier, capture_output=True,
                           input=b"pas du json", timeout=20)
        self.assertEqual(p.returncode, 1)


if __name__ == "__main__":
    unittest.main()
