import copy
import unittest
from datetime import datetime, timezone

from bureau import cout

MAINTENANT = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

PRIX = {  # euros par million de tokens
    "sonnet": {"entree": 3.0, "sortie": 15.0, "cache_lecture": 0.3, "cache_ecriture": 3.75},
    "opus": {"entree": 15.0, "sortie": 75.0, "cache_lecture": None, "cache_ecriture": None},
    "haiku": {"entree": 1.0, "sortie": 5.0, "cache_lecture": 0.1, "cache_ecriture": 1.25},
}


def prix_de(modele, date_iso):
    p = PRIX.get(modele)
    return (dict(p) if p else None), ("2026-11-01" if p else None), date_iso < "2026-11-01"


RELEVE = {"version": 3, "taches": [
    {"id": "t1", "titre": "Export CSV", "retours": []},
    {"id": "t2", "titre": "Import", "retours": [{"t": "1", "texte": "a"}, {"t": "2", "texte": "b"}]},
    {"id": "t3", "titre": "Menu", "retours": [{"t": "1", "texte": "a"}]},
]}


def usage(id, **champs):
    u = {"id": id, "tache": "t1", "agent": "d1", "service": "dev", "modele": "sonnet", "etape": "dev",
         "t": "2026-11-09T10:00:00+00:00", "t_prix": "2026-11-09T10:00:00+00:00",
         "entree": 1_000_000, "sortie": 0, "cache_lecture": 0, "cache_ecriture": 0}
    u.update(champs)
    return u


def facturer(usages, periode="7j", releve=None):
    return cout.facturation(usages, prix_de, RELEVE if releve is None else releve, periode, MAINTENANT)


class TestCalcul(unittest.TestCase):
    def test_cout_d_un_usage(self):
        u = usage("u1", entree=200_000, sortie=10_000, cache_lecture=1_000_000, cache_ecriture=40_000)
        f = facturer([u])
        attendu = 0.2 * 3 + 0.01 * 15 + 1 * 0.3 + 0.04 * 3.75   # 0,6 + 0,15 + 0,3 + 0,15
        self.assertAlmostEqual(f["total"], attendu)
        self.assertAlmostEqual(f["services"]["dev"]["usages"][0]["cout"], attendu)
        self.assertEqual(f["services"]["dev"]["usages"][0]["prix_du"], "2026-11-01")

    def test_cache_sans_prix_compte_au_prix_d_entree(self):
        f = facturer([usage("u1", modele="opus", entree=0, cache_lecture=100_000, cache_ecriture=100_000)])
        self.assertAlmostEqual(f["total"], 0.1 * 15 * 2)

    def test_agregats_par_tache_etape_modele_service(self):
        usages = [usage("u1"),                                                   # 3
                  usage("u2", etape="qa", modele="haiku"),                       # 1
                  usage("u3", tache="t2", etape="dev", sortie=1_000_000),        # 18
                  usage("u4", tache=None, etape=None),                           # 3
                  usage("u5", service="qa", agent="q1", modele="opus")]          # 15
        f = facturer(usages)
        dev = f["services"]["dev"]
        self.assertAlmostEqual(dev["total"], 25)
        self.assertAlmostEqual(dev["taches"]["t1"]["total"], 4)
        self.assertEqual(set(dev["taches"]["t1"]["etapes"]), {"dev", "qa"})
        self.assertAlmostEqual(dev["taches"]["t1"]["etapes"]["qa"], 1)
        self.assertAlmostEqual(dev["taches"]["t2"]["total"], 18)
        self.assertAlmostEqual(dev["taches"][""]["total"], 3)          # hors tâche
        self.assertAlmostEqual(dev["taches"][""]["etapes"][""], 3)     # sans étape
        self.assertAlmostEqual(dev["modeles"]["sonnet"], 24)
        self.assertAlmostEqual(dev["modeles"]["haiku"], 1)
        self.assertEqual(len(dev["usages"]), 4)
        self.assertAlmostEqual(f["services"]["qa"]["total"], 15)
        self.assertAlmostEqual(f["total"], 40)
        self.assertEqual(f["gestion"], 0)

    def test_periode_filtre(self):
        usages = [usage("hier", t="2026-11-09T23:00:00+00:00"),
                  usage("matin", t="2026-11-10T08:00:00+00:00"),
                  usage("il_y_a_10_jours", t="2026-10-31T12:00:00+00:00"),
                  usage("il_y_a_40_jours", t="2026-10-01T12:00:00+00:00")]
        ids = {p: sorted(u["id"] for u in facturer(usages, p)["services"].get("dev", {}).get("usages", []))
               for p in cout.PERIODES}
        self.assertEqual(ids["aujourdhui"], ["matin"])
        self.assertEqual(ids["7j"], ["hier", "matin"])
        self.assertEqual(ids["30j"], ["hier", "il_y_a_10_jours", "matin"])
        with self.assertRaises(ValueError):
            facturer(usages, "1an")

    def test_modele_inconnu_exclu_et_signale(self):
        f = facturer([usage("u1"), usage("u2", modele="mystere", entree=500, sortie=20, cache_lecture=5),
                      usage("u3", modele="mystere", entree=100, sortie=0)])
        self.assertAlmostEqual(f["total"], 3)
        self.assertEqual(f["sans_prix"], [{"modele": "mystere", "tokens": 625, "usages": 2}])
        self.assertIn("mystere", f["avertissement"])
        self.assertIn("prix inconnu", f["avertissement"])
        u2 = next(u for u in f["services"]["dev"]["usages"] if u["id"] == "u2")
        self.assertIsNone(u2["cout"])
        self.assertEqual(u2["tokens"], {"entree": 500, "sortie": 20, "cache_lecture": 5, "cache_ecriture": 0})
        self.assertNotIn("mystere", f["services"]["dev"]["modeles"])

    def test_tout_sans_prix_n_est_pas_zero_euro_silencieux(self):
        f = facturer([usage("u1", modele="mystere")])
        self.assertEqual(f["total"], 0)
        self.assertTrue(f["avertissement"])

    def test_prix_ancien_signale(self):
        f = facturer([usage("u1", t="2026-11-09T10:00:00+00:00", t_prix="2026-10-20T10:00:00+00:00")])
        u = f["services"]["dev"]["usages"][0]
        self.assertTrue(u["ancien"])
        self.assertIn("installation", f["avertissement"])

    def test_date_de_prix_figee(self):
        # Le prix est demandé à la date de première apparition, pas à la dernière.
        demandes = []

        def espion(modele, date_iso):
            demandes.append(date_iso)
            return prix_de(modele, date_iso)

        cout.facturation([usage("u1", t="2026-11-10T08:00:00+00:00", t_prix="2026-11-04T08:00:00+00:00")],
                         espion, RELEVE, "7j", MAINTENANT)
        self.assertEqual(demandes, ["2026-11-04T08:00:00+00:00"])

    def test_aucun_usage_total_zero(self):
        f = facturer([])
        self.assertEqual((f["total"], f["gestion"], f["services"], f["sans_prix"], f["sources"]),
                         (0, 0, {}, [], []))
        self.assertIsNone(f["avertissement"])
        self.assertIsNone(f["prix_du"])
        self.assertEqual(f["direction"]["total"], 0)

    def test_chef_dans_direction(self):
        f = facturer([usage("u1", service=None, agent="chef", tache=None),
                      usage("u2", service=None, agent=None, tache=None, modele="haiku")])
        self.assertEqual(f["services"], {})
        self.assertAlmostEqual(f["direction"]["total"], 4)
        self.assertEqual(len(f["direction"]["usages"]), 2)
        self.assertAlmostEqual(f["total"], 4)

    def test_service_nomme_direction_ne_se_melange_pas(self):
        f = facturer([usage("u1", service="direction"), usage("u2", service=None)])
        self.assertAlmostEqual(f["services"]["direction"]["total"], 3)
        self.assertAlmostEqual(f["direction"]["total"], 3)

    def test_prix_du(self):
        self.assertEqual(facturer([usage("u1")])["prix_du"], "2026-11-01")


class TestSources(unittest.TestCase):
    def taches(self, n):
        return {"version": 3, "taches": [{"id": f"t{i}", "titre": f"T{i}", "retours": []} for i in range(n)]}

    def test_source_tache_chere(self):
        usages = [usage(f"u{i}", tache=f"t{i}") for i in range(4)]            # 3 € chacune
        usages.append(usage("cher", tache="t4", entree=4_000_000))              # 12 € > 3 × 3
        usages.append(usage("presque", tache="t5", entree=3_000_000))           # 9 € : pas plus de 3 ×
        f = facturer(usages, releve=self.taches(6))
        cheres = [s for s in f["sources"] if s["genre"] == "tache_chere"]
        self.assertEqual([s["tache"] for s in cheres], ["t4"])
        s = cheres[0]
        self.assertEqual((s["id"], s["service"]), ("source:dev:tache_chere:t4", "dev"))
        self.assertIn("12,00 €", s["texte"])
        self.assertIn("3,00 €", s["texte"])

    def test_source_modele_trop_fort(self):
        usages = [usage("a", tache="t0", modele="haiku"), usage("b", tache="t1", modele="haiku"),
                  usage("c", tache="t2", modele="sonnet"), usage("d", tache="t3", modele="opus"),
                  usage("e", tache="t4", modele="opus", etape="archi")]   # seul à son étape : rien à comparer
        f = facturer(usages, releve=self.taches(5))
        fortes = [s for s in f["sources"] if s["genre"] == "modele_trop_fort"]
        self.assertEqual([s["id"] for s in fortes], ["source:dev:modele_trop_fort:t3"])
        self.assertIn("opus", fortes[0]["texte"])
        self.assertIn("dev", fortes[0]["texte"])

    def test_source_allers_retours(self):
        f = facturer([usage("u1", tache="t1"), usage("u2", tache="t2"), usage("u3", tache="t3")])
        ar = [s for s in f["sources"] if s["genre"] == "allers_retours"]
        self.assertEqual([s["id"] for s in ar], ["source:dev:allers_retours:t2"])
        self.assertIn("2 retours", ar[0]["texte"])
        self.assertIn("33 %", ar[0]["texte"])

    def test_pas_de_source_pour_la_direction_ni_sans_prix(self):
        usages = [usage(f"u{i}", tache=f"t{i}", service=None) for i in range(4)]
        usages.append(usage("x", tache="t4", service=None, entree=40_000_000))
        usages += [usage("m", tache="t5", modele="mystere", entree=10**9)]
        f = facturer(usages, releve=self.taches(6))
        self.assertEqual(f["sources"], [])

    def test_identifiants_deterministes(self):
        usages = [usage(f"u{i}", tache=f"t{i}") for i in range(4)] + [usage("cher", tache="t4", entree=10**8)]
        r = copy.deepcopy(self.taches(5))
        r["taches"][4]["retours"] = [{"t": "1", "texte": "a"}, {"t": "2", "texte": "b"}]
        a = facturer(usages, releve=r)["sources"]
        b = facturer(list(reversed(usages)), releve=r)["sources"]
        self.assertEqual(a, b)
        self.assertEqual([s["id"] for s in a], ["source:dev:allers_retours:t4", "source:dev:tache_chere:t4"])
        for s in a:
            self.assertEqual(s["id"], cout.id_source(s["service"], s["genre"], s["tache"]))

    def test_texte_de_tache_hostile_reste_du_texte(self):
        r = {"version": 3, "taches": [{"id": "t1", "titre": "<img src=x onerror=alert(1)>",
                                       "retours": [{"t": "1", "texte": "a"}, {"t": "2", "texte": "b"}]}]}
        f = facturer([usage("u1")], releve=r)
        self.assertIn("<img src=x onerror=alert(1)>", f["sources"][0]["texte"])


class TestEuros(unittest.TestCase):
    def test_format(self):
        self.assertEqual(cout.euros_en_clair(4.2), "≈ 4,20 €")
        self.assertEqual(cout.euros_en_clair(0.0042), "≈ 0,0042 €")
        self.assertEqual(cout.euros_en_clair(1234.5), "≈ 1 234,50 €")


if __name__ == "__main__":
    unittest.main()
