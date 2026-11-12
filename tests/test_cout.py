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

    def test_facturation_isole_l_orchestration(self):
        f = facturer([usage("u1"), usage("u2", service=None, agent="orchestrateur", tache=None, etape="orchestration",
                                          modele="haiku"),
                      usage("u3", service=None, agent=None, tache="t1", etape="orchestration", modele="haiku"),
                      usage("u4", service=None, agent="chef", tache=None, etape="gestion")])
        self.assertAlmostEqual(f["orchestration"]["total"], 2)           # deux millions de tokens d'entrée Haiku
        self.assertEqual(len(f["orchestration"]["usages"]), 2)
        self.assertAlmostEqual(f["direction"]["total"], 3)               # la gestion du chef reste à la direction
        self.assertAlmostEqual(f["services"]["dev"]["total"], 3)         # la production n'est pas touchée
        self.assertAlmostEqual(f["total"], 8)                            # tout compte dans le total
        self.assertEqual(facturer([])["orchestration"]["total"], 0)

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


class TestCoutsFonctionnalite(unittest.TestCase):
    def test_par_tache_de_la_fonctionnalite_depuis_toujours(self):
        r = {"version": 4, "taches": [
            {"id": "t1", "titre": "Dev : e1", "fonctionnalite": "f1"},
            {"id": "t2", "titre": "Relecture : e1", "fonctionnalite": "f1"},
            {"id": "t3", "titre": "Autre", "fonctionnalite": "f2"}]}
        usages = [usage("u1", tache="t1"),                                            # 3 € (sonnet, 1 M en entrée)
                  usage("u2", tache="t1", t="2025-01-01T10:00:00+00:00"),            # très ancien : compte quand même
                  usage("u3", tache="t2", modele="opus", entree=0, sortie=100_000),  # 7,5 €
                  usage("u4", tache="t2", modele="inconnu"),                          # sans prix : signalé
                  usage("u5", tache="t3"),                                            # autre fonctionnalité
                  usage("u6", tache=None)]
        c = cout.couts_fonctionnalite(usages, prix_de, r, "f1")
        self.assertEqual(c["total"], 13.5)
        self.assertEqual([t["id"] for t in c["taches"]], ["t1", "t2"])
        t1, t2 = c["taches"]
        self.assertEqual((t1["titre"], t1["total"], t1["sans_prix"]), ("Dev : e1", 6.0, 0))
        self.assertEqual((t2["total"], t2["sans_prix"], t2["modeles"]), (7.5, 1, {"opus": 7.5}))
        self.assertEqual(c["sans_prix"], 1)
        self.assertEqual(cout.couts_fonctionnalite([], prix_de, r, "f1"),
                         {"total": 0, "taches": [], "sans_prix": 0, "tokens": 0, "lignes": None})

    def test_echelle_tokens_et_lignes(self):
        r = {"version": 4, "taches": [{"id": "t1", "titre": "Dev", "fonctionnalite": "f1", "lignes": 85},
                                      {"id": "t2", "titre": "Relecture", "fonctionnalite": "f1"}]}
        usages = [usage("u1", tache="t1", entree=1000, sortie=200, cache_lecture=50),
                  usage("u2", tache="t1", entree=300, sortie=0),
                  usage("u3", tache="t2", modele="inconnu", entree=10, sortie=5)]
        c = cout.couts_fonctionnalite(usages, prix_de, r, "f1")
        t1, t2 = c["taches"]
        self.assertEqual((t1["tokens"], t1["lignes"]), (1550, 85))
        self.assertEqual((t2["tokens"], t2["lignes"]), (15, None))      # les tokens comptent même sans prix
        self.assertEqual((c["tokens"], c["lignes"]), (1565, 85))


class TestEmpreinte(unittest.TestCase):
    """L'empreinte estimée à côté des euros : calculée sur les tokens de sortie, jamais inventée."""

    def test_facturation_porte_l_empreinte_a_chaque_niveau(self):
        from bureau import empreinte
        un = empreinte.estimer("sonnet", 1000)
        f = facturer([usage("u1", sortie=1000), usage("u2", sortie=1000, etape="qa", tache="t2")])
        dev = f["services"]["dev"]
        self.assertAlmostEqual(f["co2"]["min"], 2 * un["min"], places=5)
        self.assertAlmostEqual(dev["co2"]["max"], 2 * un["max"], places=5)
        self.assertAlmostEqual(dev["taches"]["t1"]["co2"]["min"], un["min"], places=5)
        self.assertAlmostEqual(dev["taches"]["t2"]["etapes_co2"]["qa"]["wh_max"], un["wh_max"], places=5)
        self.assertAlmostEqual(dev["modeles_co2"]["sonnet"]["min"], 2 * un["min"], places=5)
        self.assertAlmostEqual(dev["usages"][0]["co2"]["min"], un["min"], places=5)

    def test_sans_tokens_de_sortie_rien_a_montrer(self):
        f = facturer([usage("u1", sortie=0)])
        self.assertAlmostEqual(f["co2"]["max"], 0.0)

    def test_modele_sans_famille_connue_pas_de_valeur_et_euros_inchanges(self):
        f = facturer([usage("u1", modele="inconnu", sortie=1000)])
        self.assertNotIn("co2", f)
        self.assertNotIn("co2", f["services"]["dev"])
        self.assertNotIn("co2", f["services"]["dev"]["usages"][0])

    def test_partiel_est_signale_incomplet(self):
        f = facturer([usage("u1", sortie=1000), usage("u2", modele="inconnu", sortie=1000)])
        self.assertTrue(f["co2"]["incomplet"])

    def test_un_modele_sans_prix_a_quand_meme_son_empreinte(self):
        f = cout.facturation([usage("u1", modele="haiku-sans-prix", sortie=1000)], lambda m, d: (None, None, False),
                             RELEVE, "7j", MAINTENANT)
        self.assertGreater(f["co2"]["max"], 0)

    def test_fonctionnalite(self):
        from bureau import empreinte
        r = {"version": 4, "taches": [{"id": "t1", "titre": "Dev", "fonctionnalite": "f1"}]}
        c = cout.couts_fonctionnalite([usage("u1", sortie=1000), usage("u2", sortie=1000)], prix_de, r, "f1")
        un = empreinte.estimer("sonnet", 1000)
        self.assertAlmostEqual(c["co2"]["min"], 2 * un["min"], places=5)
        self.assertAlmostEqual(c["taches"][0]["co2"]["max"], 2 * un["max"], places=5)

    def test_equivalences_pour_la_fonctionnalite_et_le_projet(self):
        r = {"version": 4, "taches": [{"id": "t1", "titre": "Dev", "fonctionnalite": "f1"}]}
        c = cout.couts_fonctionnalite([usage("u1", sortie=20000, tache="t1")], prix_de, r, "f1")
        f = facturer([usage("u1", sortie=20000)])
        for co2 in (c["co2"], f["co2"]):
            self.assertIn(len(co2["equivalences"]), (3, 4))
            self.assertEqual({"cle", "valeur", "unite", "libelle", "min", "max"}, set(co2["equivalences"][0]))
        self.assertNotIn("equivalences", f["services"]["dev"]["co2"])   # seulement le total, pas chaque ligne
