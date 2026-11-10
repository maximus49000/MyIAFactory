"""Cas trouvés à la relecture finale des dossiers des services (chacun a d'abord échoué)."""
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bureau import cout, equipe, etat, kpi, prix, releve
from bureau.prix import TablePrix
from bureau.usage import HistoriqueUsage
from tests import copie_demo
from tests.test_cout import facturer, usage
from tests.test_prix import Source, source_avec

MAINTENANT = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


class AvecDossier(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)


class TestPrixAbsurdeResteSignale(AvecDossier):
    """Une valeur absurde rejetée le matin est encore dite l'après-midi, et après un redémarrage."""

    def test_meme_jour_et_redemarrage(self):
        chemin = self.tmp / "prix.jsonl"
        table = TablePrix(chemin)
        prix.actualiser(table, Source(prix_json=source_avec(m=(2e-06, 1e-05))), "2026-11-01")
        res = prix.actualiser(table, Source(prix_json=source_avec(m=(2e-04, 1e-05))), "2026-11-02")
        self.assertIn("absurde", res["message"])

        def interdit(url):
            raise AssertionError("une seule lecture par jour")

        for t in (table, TablePrix(chemin)):
            res = prix.actualiser(t, interdit, "2026-11-02")
            self.assertFalse(res["ok"])
            self.assertIn("absurde", res["message"])
            self.assertIn("m", res["message"])
        # Le lendemain, la source est redevenue normale : plus rien à signaler.
        res = prix.actualiser(table, Source(prix_json=source_avec(m=(2e-06, 1e-05))), "2026-11-03")
        self.assertTrue(res["ok"], res)
        self.assertTrue(prix.actualiser(table, interdit, "2026-11-03")["ok"])


class TestHistoriquesNonUtf8(AvecDossier):
    """Un fichier d'historique réenregistré dans un autre encodage : la ligne abîmée est ignorée."""
    SALE = b'{"service": "d\xe9v"\n'

    def test_prix(self):
        chemin = self.tmp / "prix.jsonl"
        TablePrix(chemin).ajouter("2026-11-01", {"a": {"entree": 1.0, "sortie": 2.0}}, 0.5)
        chemin.write_bytes(self.SALE + chemin.read_bytes())
        self.assertAlmostEqual(TablePrix(chemin).prix_a("a", "2026-11-02")[0]["entree"], 0.5)

    def test_usage(self):
        chemin = self.tmp / "usage.jsonl"
        chemin.write_bytes(self.SALE)
        self.assertEqual(HistoriqueUsage(chemin).lire(), [])

    def test_alertes(self):
        chemin = self.tmp / "alertes.jsonl"
        chemin.write_bytes(self.SALE)
        self.assertEqual(kpi.HistoriqueAlertes(chemin).lire(), {})


class TestModeleTropFortEtTaux(unittest.TestCase):
    def test_le_taux_de_change_ne_cree_pas_de_source(self):
        """Le même modèle, deux jours de suite, à deux taux : ce n'est pas « un modèle plus cher »."""
        def prix_de(modele, date_iso):
            taux = 0.90 if date_iso < "2026-11-09" else 0.93
            return {"entree": 15 * taux, "sortie": 75 * taux, "cache_lecture": None, "cache_ecriture": None}, \
                "2026-11-01", False

        usages = [usage("a", tache="t1", modele="opus", t="2026-11-08T10:00:00+00:00",
                        t_prix="2026-11-08T10:00:00+00:00"),
                  usage("b", tache="t2", modele="opus")]
        f = cout.facturation(usages, prix_de, {"taches": []}, "7j", MAINTENANT)
        self.assertEqual([s for s in f["sources"] if s["genre"] == "modele_trop_fort"], [])


class TestPrixInconnuDitPartout(unittest.TestCase):
    def setUp(self):
        self.f = facturer([usage("u1", tache="t1"), usage("u2", tache="t1", modele="mystere", entree=500),
                           usage("u3", tache="t3", modele="mystere", entree=70),
                           usage("u4", tache="t2", service="qa", agent="q1")])

    def test_par_tache_et_par_service(self):
        dev = self.f["services"]["dev"]
        self.assertEqual(dev["taches"]["t1"]["sans_prix"], 1)
        self.assertAlmostEqual(dev["taches"]["t1"]["total"], 3.0)
        # Une tâche dont aucun usage n'a de prix est là quand même : ni absente, ni comptée.
        self.assertEqual((dev["taches"]["t3"]["total"], dev["taches"]["t3"]["sans_prix"]), (0.0, 1))
        self.assertEqual(dev["sans_prix"], [{"modele": "mystere", "tokens": 570, "usages": 2}])
        self.assertEqual(self.f["services"]["qa"]["sans_prix"], [])
        self.assertEqual(self.f["services"]["qa"]["taches"]["t2"]["sans_prix"], 0)
        self.assertEqual(self.f["direction"]["sans_prix"], [])

    def test_le_constat_d_une_source_le_dit(self):
        usages = [usage(f"u{i}", tache=f"t{i}") for i in range(4)]
        usages += [usage("cher", tache="t4", entree=10**8), usage("x", tache="t4", modele="mystere")]
        f = facturer(usages, releve={"taches": [{"id": f"t{i}", "titre": f"T{i}"} for i in range(5)]})
        (source,) = [s for s in f["sources"] if s["genre"] == "tache_chere"]
        self.assertIn("prix inconnu", source["texte"])
        f = facturer(usages[:-1], releve={"taches": []})
        self.assertNotIn("prix inconnu", [s for s in f["sources"] if s["genre"] == "tache_chere"][0]["texte"])

    def test_le_cout_moyen_le_dit(self):
        r = {"services": [{"id": "dev", "nom": "Dev"}, {"id": "qa", "nom": "QA"}], "colonnes": [],
             "titulaires": [], "taches": []}
        k = {s: {x["id"]: x for x in liste} for s, liste in kpi.calcules(r, self.f, "7j", MAINTENANT).items()}
        self.assertEqual(k["dev"]["cout_moyen"]["valeur"], cout.euros_en_clair(3.0) + " (hors prix inconnus)")
        self.assertEqual(k["qa"]["cout_moyen"]["valeur"], cout.euros_en_clair(3.0))


class TestAlertesNonInscriptibles(AvecDossier):
    def test_l_etat_reste_lisible(self):
        """L'historique des alertes ne peut pas être écrit : la scène reste là (seule la marque manque)."""
        class Casse:
            def noter(self, *a):
                raise PermissionError(13, "Permission denied")

            def lire(self):
                return {}

        r = json.loads((Path(__file__).resolve().parent.parent / "exemples" / "demo" / "releve.json")
                       .read_text(encoding="utf-8"))
        e = etat.construire(releve.normaliser(r), equipe.Equipe(self.tmp / "equipe.json"),
                            datetime.now().astimezone(), 30, Casse())
        self.assertIsNone(e.get("erreur"))
        self.assertTrue(e["agents"])


class TestCopieDeLaDemo(AvecDossier):
    def test_les_fichiers_produits_par_le_serveur_ne_sont_pas_copies(self):
        """Lancer la démo sur place crée des historiques ; les tests ne doivent pas les embarquer."""
        source = self.tmp / "source"
        shutil.copytree(Path(__file__).resolve().parent.parent / "exemples" / "demo", source,
                        ignore=shutil.ignore_patterns("*.jsonl", "equipe.json"))
        for nom in ("usage-historique.jsonl", "prix-historique.jsonl", "alertes-historique.jsonl",
                    "charge-historique.jsonl", "equipe.json", "prix-historique.jsonl.tmp"):
            (source / nom).write_text("{}\n", encoding="utf-8")
        copie_demo(self.tmp / "copie", source)
        self.assertEqual(sorted(p.name for p in (self.tmp / "copie").iterdir()),
                         ["actions.py", "catalogue-magasin.json", "images", "livrables", "methodes", "reglages.json",
                          "releve.json"])


if __name__ == "__main__":
    unittest.main()
