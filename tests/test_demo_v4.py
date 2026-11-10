"""La démo à deux projets (version 4) et le projet neuf."""
import base64
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bureau import catalogue, demandes, releve, reglages
from tests import copie_demo

RACINE = Path(__file__).resolve().parent.parent
EXEMPLES = RACINE / "exemples"
PNG = base64.b64encode((EXEMPLES / "demo" / "images" / "accueil-maquette.png").read_bytes()).decode()


def lire(chemin):
    return json.loads(Path(chemin).read_text(encoding="utf-8-sig"))


class AvecCopie(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        catalogue.vider_cache()

    def copie(self, nom):
        return copie_demo(self.tmp / nom, EXEMPLES / nom)

    def demander(self, dossier, d, elements=None):
        """Comme le bureau : la demande est vérifiée contre le relevé, puis remise à la commande d'actions."""
        r = lire(dossier / "releve.json")
        d = {**d, "t": "2026-11-10T12:00:00+01:00"}
        self.assertIsNone(demandes.verifier(d, r, frozenset(), elements), d)
        p = subprocess.run([sys.executable, "actions.py"], cwd=dossier, capture_output=True, timeout=30,
                           input=json.dumps(d).encode("utf-8"))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        r = lire(dossier / "releve.json")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        return r


class TestDemo(AvecCopie):
    def test_demo_a_et_b_valides(self):
        bureau = reglages.lire_bureau(EXEMPLES / "bureau.json")
        self.assertEqual([p["id"] for p in bureau["projets"]], ["demo", "demo-b"])
        a, b = lire(EXEMPLES / "demo" / "releve.json"), lire(EXEMPLES / "demo-b" / "releve.json")
        for r in (a, b):
            self.assertEqual(r["version"], 4)
            self.assertEqual(releve.valider(r), [], releve.valider(r))
        # A : une fonctionnalité en série avec son catalogue, une montée de modèle, un dernier livrable.
        serie = next(f for f in a["fonctionnalites"] if f["etape"] == "serie")
        self.assertTrue(serie["catalogue"])
        self.assertTrue(any(t.get("montee") for t in a["taches"]))
        self.assertTrue(a["livrable"]["chemin"])
        regl_a = reglages.charger(EXEMPLES / "demo" / "reglages.json")
        self.assertTrue((EXEMPLES / "demo" / a["livrable"]["chemin"]).is_file())
        code, objet = catalogue.lire(regl_a, serie["id"])
        self.assertEqual(code, 200, objet)
        self.assertEqual(objet["avertissements"], [])
        cat = objet["catalogue"]
        self.assertEqual(len(cat["groupes"]), 2)
        self.assertEqual(len(cat["elements"]), 6)
        self.assertTrue(any(len(e.get("comparaisons", [])) >= 2 for e in cat["elements"]))
        self.assertTrue(any(e.get("doute") for e in cat["elements"]))
        self.assertTrue(any(e.get("a_reevaluer") for e in cat["elements"]))
        self.assertTrue(all("position" in e for e in cat["elements"]))
        self.assertTrue(cat["trace"])
        for e in cat["elements"]:   # chaque image citée existe
            chemins = [c["chemin"] for c in e.get("captures", [])]
            chemins += [x for c in e.get("comparaisons", []) for x in (c.get("reel"), c.get("produit")) if x]
            for c in chemins:
                self.assertTrue((EXEMPLES / "demo" / c).is_file(), c)
        # B : une fonctionnalité en cadrage avec une image dans la discussion, un genre à confirmer, une session.
        cadrage = next(f for f in b["fonctionnalites"] if f["etape"] == "cadrage")
        images = [i for m in cadrage["discussion"] for i in m.get("images", [])]
        self.assertTrue(images and all((EXEMPLES / "demo-b" / i).is_file() for i in images))
        self.assertEqual({d["genre"] for d in b["decisions_projet"]}, {"confirmer_genre", "session_cloud"})
        self.assertIsNone(b["genre"])

    def test_demo_parcours(self):
        self.copie("demo")              # la démo B joue la commande d'actions de la démo A
        dossier = self.copie("demo-b")
        avant = {f["id"] for f in lire(dossier / "releve.json")["fonctionnalites"]}
        image = {"nom": "croquis.png", "type": "image/png", "donnees": PNG}
        r = self.demander(dossier, {"type": "fonctionnalite", "texte": "Un rappel par SMS la veille.",
                                    "images": [image]})
        f = next(x for x in r["fonctionnalites"] if x["id"] not in avant)
        self.assertEqual(f["etape"], "cadrage")
        self.assertEqual(f["discussion"][0]["texte"], "Un rappel par SMS la veille.")
        self.assertTrue((dossier / f["discussion"][0]["images"][0]).is_file())   # rangée par le projet
        self.assertNotEqual(f["discussion"][-1]["auteur"], "utilisateur")      # l'agent a répondu
        r = self.demander(dossier, {"type": "message", "fonctionnalite": f["id"], "texte": "Oui, à 18 h."})
        f = next(x for x in r["fonctionnalites"] if x["id"] == f["id"])
        self.assertEqual(f["etape"], "cahier")
        self.assertTrue(f["cahier"]["maquette"] and f["cahier"]["etapes"])
        self.assertEqual([d["genre"] for d in f["decisions"]], ["valider_cahier"])
        r = self.demander(dossier, {"type": "cahier", "fonctionnalite": f["id"], "verdict": "valider"})
        f = next(x for x in r["fonctionnalites"] if x["id"] == f["id"])
        self.assertEqual(f["etape"], "prototype")
        self.assertTrue(f["cahier"]["valide_le"])
        self.assertEqual([d["genre"] for d in f["decisions"]], ["valider_methode"])
        r = self.demander(dossier, {"type": "methode", "fonctionnalite": f["id"], "verdict": "valider"})
        f = next(x for x in r["fonctionnalites"] if x["id"] == f["id"])
        self.assertEqual(f["etape"], "serie")
        self.assertEqual(f["methode"]["version"], 1)
        self.assertEqual(f["decisions"], [])
        # Les décisions du projet : le genre, puis la session cloud.
        dg = next(d for d in r["decisions_projet"] if d["genre"] == "confirmer_genre")
        r = self.demander(dossier, {"type": "genre", "decision": dg["id"], "genre": "prise-de-rendez-vous",
                                    "description": "Applications de prise de rendez-vous"})
        self.assertEqual(r["genre"], "prise-de-rendez-vous")
        ds = next(d for d in r["decisions_projet"] if d["genre"] == "session_cloud")
        r = self.demander(dossier, {"type": "session_cloud", "decision": ds["id"], "session": "Dev Opus (cloud)"})
        self.assertEqual(r["decisions_projet"], [])

    def test_demo_retour_element(self):
        dossier = self.copie("demo")
        regl = reglages.charger(dossier / "reglages.json")
        r = lire(dossier / "releve.json")
        f = next(x for x in r["fonctionnalites"] if x.get("catalogue"))
        elements = catalogue.ids(regl, f["id"])
        e = sorted(elements)[0]
        self.demander(dossier, {"type": "retour_element", "fonctionnalite": f["id"], "element": e,
                                "texte": "La vitrine est trop sombre."}, elements)
        catalogue.vider_cache()
        code, objet = catalogue.lire(regl, f["id"])
        retours = next(x for x in objet["catalogue"]["elements"] if x["id"] == e)["retours"]
        self.assertEqual(retours[-1]["texte"], "La vitrine est trop sombre.")
        self.assertTrue(retours[-1]["reponse"])


class TestProjetNeuf(AvecCopie):
    def test_projet_neuf_verificateur(self):
        dossier = self.tmp / "projet"
        shutil.copytree(EXEMPLES / "projet-neuf", dossier)
        f = lire(dossier / "factory.json")
        self.assertIsNone(f["genre"])
        f["skill"] = str(RACINE)        # ce que le guide demande de faire après la copie
        (dossier / "factory.json").write_text(json.dumps(f), encoding="utf-8")
        (dossier / ".copie-de-verification").write_text("", encoding="utf-8")
        p = subprocess.run([sys.executable, str(RACINE / "orchestrateur" / "verifier_interface.py"),
                            "--factory", str(dossier / "factory.json"), "--complet"],
                           capture_output=True, timeout=300)
        sortie = p.stdout.decode("utf-8", "replace")
        self.assertEqual(p.returncode, 0, sortie + p.stderr.decode("utf-8", "replace"))
        self.assertNotIn("ÉCART", sortie)
        # Les réglages appellent outil.py : le relevé du projet neuf se lit comme le bureau le lirait.
        regl = lire(dossier / "reglages.json")
        cmd = [sys.executable if a == "python" else a for a in regl["releve"]["commande"]]
        cmd = [str(RACINE / "orchestrateur" / "outil.py") if a.endswith("orchestrateur/outil.py") else a for a in cmd]
        p = subprocess.run(cmd, cwd=dossier, capture_output=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(releve.valider(json.loads(p.stdout)), [])
        # Le catalogue générique « * » : le bureau le trouve pour une fonctionnalité créée au fil du temps.
        outil = str(RACINE / "orchestrateur" / "outil.py")
        p = subprocess.run([sys.executable, outil, "--factory", "factory.json", "lancer", "actions"], cwd=dossier,
                           input=json.dumps({"type": "fonctionnalite", "texte": "Un essai", "t": "2026-11-10T12:00:00+01:00"}).encode(),
                           capture_output=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        f["catalogues"]["*"]["commande"] = [sys.executable, outil] + f["catalogues"]["*"]["commande"][2:]
        (dossier / "factory.json").write_text(json.dumps(f), encoding="utf-8")
        regl = reglages.charger(dossier / "reglages.json")
        code, objet = catalogue.lire(regl, "f1")
        self.assertEqual(code, 200, objet)
        self.assertIsInstance(objet["catalogue"]["elements"], list)   # f1 vient du scénario du vérificateur


if __name__ == "__main__":
    unittest.main()
