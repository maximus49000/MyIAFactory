import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bureau import cout, kpi, releve

M = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def il_y_a(**d):
    return (M - timedelta(**d)).isoformat()


R = {"version": 3, "projet": "P", "factory": {"etat": "en marche"},
     "services": [{"id": "dev", "nom": "Dev"}, {"id": "qa", "nom": "QA"}],
     "colonnes": [{"id": "a", "nom": "A"}, {"id": "f", "nom": "Fait", "terminee": True}],
     "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}, {"cle": "q1", "service": "qa", "lieu": "local"}],
     "taches": [
         {"id": "t1", "titre": "T1", "colonne": "f", "active": False, "titulaire": "d1", "maj": il_y_a(days=1),
          "retours": [{"t": "1", "texte": "a"}, {"t": "2", "texte": "b"}, {"t": "3", "texte": "c"}],
          "journal": [{"t": il_y_a(days=2), "texte": "début"}, {"t": il_y_a(days=1), "texte": "fin"}]},
         {"id": "t2", "titre": "T2", "colonne": "f", "active": False, "titulaire": "d1", "maj": il_y_a(days=10)},
         {"id": "t3", "titre": "T3", "colonne": "a", "active": True, "titulaire": "d1", "maj": il_y_a(hours=1),
          "retours": [{"t": "1", "texte": "a"}]},
         {"id": "t4", "titre": "T4", "colonne": "f", "active": False, "titulaire": "q1", "maj": il_y_a(hours=2)}]}


def releve_v3(modif=None):
    r = copy.deepcopy(R)
    r["version"] = 3
    if modif:
        modif(r)
    erreurs = releve.valider(r)
    assert erreurs == [], erreurs
    return releve.normaliser(r)


def par_id(liste):
    return {k["id"]: k for k in liste}


def facturation(par_service=None):
    return {"services": {s: {"total": t, "taches": {i: {"total": c, "etapes": {}} for i, c in taches.items()},
                              "modeles": {}, "usages": []}
                         for s, (t, taches) in (par_service or {}).items()}, "direction": {}}


class TestCalcules(unittest.TestCase):
    def test_calcules_taches_terminees(self):
        k = par_id(kpi.calcules(releve_v3(), None, "7j", M)["dev"])
        self.assertEqual(k["taches_terminees"]["valeur"], 1)  # t1 ; t2 est trop ancienne, t3 pas finie
        k = par_id(kpi.calcules(releve_v3(), None, "30j", M)["dev"])
        self.assertEqual(k["taches_terminees"]["valeur"], 2)
        k = par_id(kpi.calcules(releve_v3(), None, "aujourdhui", M)["qa"])
        self.assertEqual(k["taches_terminees"]["valeur"], 1)
        k = par_id(kpi.calcules(releve_v3(), None, "aujourdhui", M)["dev"])
        self.assertEqual(k["taches_terminees"]["valeur"], 0)

    def test_calcules_allers_retours(self):
        k = par_id(kpi.calcules(releve_v3(), None, "7j", M)["dev"])
        self.assertEqual(k["allers_retours"]["valeur"], 2.0)  # (3 + 1) / 2 tâches de la période
        self.assertEqual(k["allers_retours"]["unite"], "par tâche")
        self.assertEqual(par_id(kpi.calcules(releve_v3(), None, "7j", M)["qa"])["allers_retours"]["valeur"], 0.0)

    def test_duree_moyenne(self):
        k = par_id(kpi.calcules(releve_v3(), None, "7j", M)["dev"])
        self.assertEqual(k["duree_tache"]["valeur"], "24 h")  # un seul journal exploitable : 24 h
        self.assertNotIn("duree_tache", par_id(kpi.calcules(releve_v3(), None, "7j", M)["qa"]))  # pas de journal

    def test_cout_moyen(self):
        f = facturation({"dev": (6.0, {"t1": 4.0, "t3": 2.0, "": 0.0}), "qa": (0.0, {})})
        k = par_id(kpi.calcules(releve_v3(), f, "7j", M)["dev"])
        self.assertEqual(k["cout_moyen"]["valeur"], cout.euros_en_clair(3.0))
        self.assertNotIn("cout_moyen", par_id(kpi.calcules(releve_v3(), f, "7j", M)["qa"]))
        self.assertNotIn("cout_moyen", par_id(kpi.calcules(releve_v3(), None, "7j", M)["dev"]))

    def test_forme_d_un_kpi_calcule(self):
        k = par_id(kpi.calcules(releve_v3(), None, "7j", M)["dev"])["taches_terminees"]
        self.assertEqual((k["nom"], k["alerte"], k["calcule"], k["periodes"]),
                         ("Tâches terminées", False, True, {"7j": 1}))

    def test_sans_donnees_ni_plantage(self):
        r = releve_v3(lambda r: r.update(taches=[]))
        self.assertEqual(par_id(kpi.calcules(r, None, "7j", M)["dev"])["taches_terminees"]["valeur"], 0)
        r = releve_v3(lambda r: r["taches"][0].update(maj="pas une date", journal=[{"t": "x", "texte": "y"}]))
        kpi.calcules(r, None, "7j", M)

    def test_le_kpi_du_projet_l_emporte(self):
        def m(r):
            r["services"][0]["kpi"] = [{"id": "cout_moyen", "nom": "Mon coût", "valeur": 9},
                                       {"id": "defauts", "nom": "Défauts", "valeur": 2, "alerte": True}]
        tous = kpi.tous(releve_v3(m), facturation({"dev": (2.0, {"t1": 2.0})}), "7j", M)
        d = par_id(tous["dev"])
        self.assertEqual((d["cout_moyen"]["nom"], d["cout_moyen"]["calcule"]), ("Mon coût", False))
        self.assertTrue(d["defauts"]["alerte"])
        self.assertIn("taches_terminees", d)
        self.assertEqual(tous["dev"][0]["id"], "cout_moyen")  # le projet d'abord

    def test_constats(self):
        c = kpi.constats(releve_v3(), None, "7j", M)
        self.assertEqual(set(c), {"kpi:dev:taches_terminees", "kpi:qa:taches_terminees", "kpi:dev:allers_retours",
                                  "kpi:qa:allers_retours", "kpi:dev:duree_tache"})
        self.assertIn("Tâches terminées", c["kpi:dev:taches_terminees"])
        self.assertIn("7 derniers jours", c["kpi:dev:taches_terminees"])


class TestAlertes(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.chemin = Path(self._t.name) / "alertes-historique.jsonl"

    def test_alerte_date_de_premiere_alerte(self):
        h = kpi.HistoriqueAlertes(self.chemin)
        h.noter("dev", "defauts", False, M)
        self.assertEqual(h.lire(), {})
        h.noter("dev", "defauts", True, M + timedelta(hours=1))
        h.noter("dev", "defauts", True, M + timedelta(hours=5))  # toujours en alerte : la date ne bouge pas
        self.assertEqual(h.lire(), {("dev", "defauts"): (M + timedelta(hours=1)).isoformat()})
        # Survit au redémarrage.
        self.assertEqual(kpi.HistoriqueAlertes(self.chemin).lire(), h.lire())
        # L'alerte cesse puis revient : c'est une nouvelle alerte, avec sa propre date.
        h.noter("dev", "defauts", False, M + timedelta(days=1))
        self.assertEqual(h.lire(), {})
        h.noter("dev", "defauts", True, M + timedelta(days=2))
        self.assertEqual(h.lire(), {("dev", "defauts"): (M + timedelta(days=2)).isoformat()})

    def test_deux_services_meme_id(self):
        h = kpi.HistoriqueAlertes(self.chemin)
        h.noter("dev", "a", True, M)
        h.noter("qa", "a", False, M)
        self.assertEqual(list(h.lire()), [("dev", "a")])

    def test_ligne_illisible_ignoree(self):
        self.chemin.write_text('pas du json\n{"service": 3}\n' + json.dumps(
            {"service": "dev", "kpi": "a", "t": M.isoformat(), "alerte": True}) + "\n", encoding="utf-8")
        self.assertEqual(list(kpi.HistoriqueAlertes(self.chemin).lire()), [("dev", "a")])

    def test_suivre_alertes(self):
        def m(r):
            r["services"][0]["kpi"] = [{"id": "defauts", "nom": "D", "valeur": 2, "alerte": True},
                                       {"id": "ok", "nom": "O", "valeur": 0}]
            r["services"][1]["kpi"] = []
        h = kpi.HistoriqueAlertes(self.chemin)
        depuis = kpi.suivre_alertes(releve_v3(m), h, M)
        self.assertEqual(depuis, {("dev", "defauts"): M.isoformat()})

    def test_probleme_revenu(self):
        apres, avant = (M + timedelta(days=1)).isoformat(), (M - timedelta(days=1)).isoformat()
        self.assertTrue(kpi.probleme_revenu(M.isoformat(), apres))
        self.assertFalse(kpi.probleme_revenu(M.isoformat(), avant))   # l'alerte précède la connaissance
        self.assertFalse(kpi.probleme_revenu(M.isoformat(), None))    # pas en alerte
        self.assertFalse(kpi.probleme_revenu(None, apres))            # connaissance sans date
        self.assertFalse(kpi.probleme_revenu("pas une date", apres))
        # Date sans heure : une alerte le même jour n'est pas « revenue ».
        jour = M.astimezone().date().isoformat()
        self.assertFalse(kpi.probleme_revenu(jour, M.isoformat()))
        self.assertTrue(kpi.probleme_revenu(jour, (M + timedelta(days=2)).isoformat()))

    def test_cible_kpi(self):
        self.assertEqual(kpi.cible_kpi("kpi:dev:defauts", {"dev", "qa"}), ("dev", "defauts"))
        self.assertEqual(kpi.cible_kpi("kpi:a:b:c", {"a:b", "a"}), ("a:b", "c"))
        self.assertIsNone(kpi.cible_kpi("kpi:rh:x", {"dev"}))
        self.assertIsNone(kpi.cible_kpi("source:dev:x:t", {"dev"}))
        self.assertIsNone(kpi.cible_kpi(3, {"dev"}))


if __name__ == "__main__":
    unittest.main()
