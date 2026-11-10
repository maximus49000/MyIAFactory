import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bureau import demandes, releve
from tests import copie_demo

RACINE = Path(__file__).resolve().parent.parent


class TestDemoActions(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dossier = Path(self._t.name) / "demo"
        copie_demo(self.dossier)
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

    def test_le_relevé_de_la_démo_est_v4_et_riche(self):
        r = self.lire()
        self.assertEqual(r["version"], 4)
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

    def test_la_démo_remplit_les_quatre_onglets(self):
        r = releve.normaliser(self.lire())
        regl = json.loads((self.dossier / "reglages.json").read_text(encoding="utf-8"))
        service_de = {t["cle"]: t.get("service") for t in r["titulaires"]}
        self.assertGreaterEqual(len({u["modele"] for u in r["usage"]}), 3)
        self.assertTrue(any(u["agent"] == "chef" and u["tache"] is None for u in r["usage"]), "un usage de la direction")
        # Chaque modèle de l'usage a un alias, sauf un, laissé exprès à « prix inconnu ».
        sans_alias = {u["modele"] for u in r["usage"]} - set(regl["alias_modeles"])
        self.assertEqual(len(sans_alias), 1)
        self.assertTrue(any(c.get("terminee") for c in r["colonnes"]))
        kpi = {s["id"]: s["kpi"] for s in r["services"] if s.get("kpi")}
        self.assertTrue(any(k["alerte"] for k in kpi["dev"]))
        self.assertTrue(any(k["periodes"] for liste in kpi.values() for k in liste))
        self.assertTrue(any(not k["periodes"] for liste in kpi.values() for k in liste), "un KPI « toutes périodes »")
        autre_service = [(t["cle"], a["agent"]) for t in r["titulaires"] for c in t.get("connaissances") or []
                         for a in c["appris_de"] if service_de[a["agent"]] != t.get("service")]
        self.assertTrue(autre_service, "une connaissance apprise d'un autre service")
        (ch,) = r["challenges"]
        self.assertEqual(sorted(s["auteur"] for s in ch["solutions"]), ["directeur", "service", "utilisateur"])
        self.assertIn(ch["cible"]["id"], demandes.kpi_du_releve(r))

    def test_la_démo_a_des_sources_d_amélioration(self):
        from datetime import datetime
        from bureau import cout, usage
        r = releve.normaliser(self.lire())
        h = usage.HistoriqueUsage(Path(self._t.name) / "usage.jsonl")
        h.integrer(r)
        prix = {"entree": 3.0, "sortie": 15.0, "cache_lecture": None, "cache_ecriture": None}
        cher = {"entree": 5.0, "sortie": 25.0, "cache_lecture": None, "cache_ecriture": None}

        def prix_de(modele, date):
            return ({"Opus": cher, "Sonnet": prix, "Haiku": prix}.get(modele), "2026-11-01", False)

        maintenant = max(datetime.fromisoformat(u["t"]) for u in r["usage"]).astimezone()
        f = cout.facturation(h.lire(), prix_de, r, "7j", maintenant)
        self.assertEqual({s["genre"] for s in f["sources"] if s["service"] == "dev"},
                         {"tache_chere", "modele_trop_fort", "allers_retours"})
        self.assertEqual(len(f["sans_prix"]), 1)
        self.assertGreater(f["direction"]["total"], 0)

    def test_demo_challenge(self):
        """Challenge → solutions → validation : chaque effet se relit au relevé, qui reste valide."""
        avant = self.lire()
        cible = {"type": "connaissance", "id": "k-dev1-1"}
        demande = {"type": "challenge", "cible": cible, "solution": "Ma solution d'utilisateur."}
        self.assertIsNone(demandes.verifier(demande, releve.normaliser(avant)))
        r, _ = self.lancer(demande)
        self.assertEqual(len(r["challenges"]), len(avant["challenges"]) + 1)
        ch = r["challenges"][-1]
        self.assertEqual(ch["cible"], cible)
        self.assertTrue(ch["date"])
        # La demande ne porte pas de texte pour une connaissance : la démo retrouve elle-même le problème.
        self.assertIn(dict((c["id"], c["texte"]) for t in avant["titulaires"]
                           for c in t.get("connaissances", []))["k-dev1-1"], ch["texte"])
        # Le « projet » de la démo répond : le Directeur et le service proposent, la solution de l'utilisateur est là.
        self.assertEqual(sorted(s["auteur"] for s in ch["solutions"]), ["directeur", "service", "utilisateur"])
        self.assertEqual(next(s for s in ch["solutions"] if s["auteur"] == "utilisateur")["texte"],
                         "Ma solution d'utilisateur.")
        # Un second challenge sur la même cible : le bureau le refuse (et la démo aussi).
        self.assertIn("existe déjà", demandes.verifier(demande, releve.normaliser(r)))
        self.lancer(demande, attendu=1)

        demande = {"type": "solution", "challenge": ch["id"], "texte": "Une autre idée."}
        self.assertIsNone(demandes.verifier(demande, releve.normaliser(r)))
        r, _ = self.lancer(demande)
        ch = next(c for c in r["challenges"] if c["id"] == ch["id"])
        self.assertEqual(len(ch["solutions"]), 4)
        self.assertEqual((ch["solutions"][-1]["texte"], ch["solutions"][-1]["auteur"]), ("Une autre idée.", "utilisateur"))

        validee, ecartee = ch["solutions"][0], ch["solutions"][1]
        for sol, verdict in ((validee, "valider"), (ecartee, "ecarter")):
            demande = {"type": "verdict_solution", "challenge": ch["id"], "solution": sol["id"], "verdict": verdict}
            self.assertIsNone(demandes.verifier(demande, releve.normaliser(r)))
            r, _ = self.lancer(demande)
        ch = next(c for c in r["challenges"] if c["id"] == ch["id"])
        self.assertEqual([s["etat"] for s in ch["solutions"]], ["validée", "écartée", "proposée", "proposée"])
        # La solution validée est inscrite dans les connaissances de l'agent concerné, avec son origine.
        dev1 = next(t for t in r["titulaires"] if t["cle"] == "dev:1")
        nouvelles = [c for c in dev1["connaissances"] if c.get("origine") == ch["id"]]
        self.assertEqual([c["texte"] for c in nouvelles], [validee["texte"]])
        self.assertTrue(nouvelles[0]["date"])
        autres = [c for t in r["titulaires"] if t["cle"] != "dev:1" for c in t.get("connaissances") or []
                  if c.get("origine") == ch["id"]]
        self.assertEqual(autres, [])
        # Valider deux fois n'inscrit pas deux fois.
        r, _ = self.lancer({"type": "verdict_solution", "challenge": ch["id"], "solution": validee["id"],
                            "verdict": "valider"})
        dev1 = next(t for t in r["titulaires"] if t["cle"] == "dev:1")
        self.assertEqual(len([c for c in dev1["connaissances"] if c.get("origine") == ch["id"]]), 1)

    def test_demo_verdict_sur_un_kpi_touche_tout_le_service(self):
        ch = self.lire()["challenges"][0]
        self.assertEqual(ch["cible"], {"type": "kpi", "id": "kpi:dev:defauts"})
        sol = ch["solutions"][0]
        r, _ = self.lancer({"type": "verdict_solution", "challenge": ch["id"], "solution": sol["id"],
                            "verdict": "valider"})
        recus = sorted(t["cle"] for t in r["titulaires"]
                       if any(c.get("origine") == ch["id"] for c in t.get("connaissances") or []))
        self.assertEqual(recus, ["dev:1", "dev:2"])

    def test_demo_challenge_sur_une_source(self):
        cible = {"type": "source", "id": "source:dev:tache_chere:t1"}
        r, _ = self.lancer({"type": "challenge", "cible": cible, "texte": "Constat écrit par le bureau."})
        ch = r["challenges"][-1]
        self.assertEqual((ch["cible"], ch["texte"]), (cible, "Constat écrit par le bureau."))
        self.assertEqual(sorted(s["auteur"] for s in ch["solutions"]), ["directeur", "service"])
        r, _ = self.lancer({"type": "verdict_solution", "challenge": ch["id"], "solution": ch["solutions"][0]["id"],
                            "verdict": "valider"})
        self.assertTrue(any(c.get("origine") == ch["id"] for t in r["titulaires"] if t.get("service") == "dev"
                            for c in t.get("connaissances") or []))

    def test_demo_challenge_refus(self):
        avant = self.fichier.read_bytes()
        ch = self.lire()["challenges"][0]
        for d in ({"type": "challenge"}, {"type": "challenge", "cible": {"type": "autre", "id": "x"}},
                  {"type": "challenge", "cible": ch["cible"]},
                  {"type": "solution", "challenge": "zz", "texte": "x"},
                  {"type": "verdict_solution", "challenge": ch["id"], "solution": "zz", "verdict": "valider"},
                  {"type": "verdict_solution", "challenge": ch["id"], "solution": ch["solutions"][0]["id"],
                   "verdict": "autre"}):
            _, sortie = self.lancer(d, attendu=1)
            self.assertTrue(sortie.strip(), d)
        self.assertEqual(self.fichier.read_bytes(), avant)

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

    def _avec_suite(self):
        r = self.lire()
        r["file"] = {"visibles": [{"id": "v1", "titre": "V1"}], "reste": 3,
                     "suite": [{"id": "s1", "titre": "S1"}, {"id": "s2", "titre": "S2"}]}
        self.fichier.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")

    def test_deplacement_d_un_element_de_la_suite(self):
        self._avec_suite()
        r, _ = self.lancer({"type": "deplacer", "tache": "s2", "colonne": "encours"})
        self.assertEqual(next(t for t in r["taches"] if t["id"] == "s2")["colonne"], "encours")
        self.assertEqual([q["id"] for q in r["file"]["suite"]], ["s1"])
        self.assertEqual([q["id"] for q in r["file"]["visibles"]], ["v1"])
        self.assertEqual(r["file"]["reste"], 2)

    def test_deplacement_d_un_element_visible_fait_monter_la_suite(self):
        self._avec_suite()
        r, _ = self.lancer({"type": "deplacer", "tache": "v1", "colonne": "encours"})
        self.assertEqual([q["id"] for q in r["file"]["visibles"]], ["s1"])
        self.assertEqual([q["id"] for q in r["file"]["suite"]], ["s2"])
        self.assertEqual(r["file"]["reste"], 2)

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
