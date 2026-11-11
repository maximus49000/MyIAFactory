"""Les lots par modèle dans l'outil de l'orchestrateur : `tache`, `lots`, `depart`, `usage`, relevé, facturation."""
import json
import unittest
from datetime import datetime, timezone

from bureau import cout, releve
from tests.orch_aide import AvecProjet

FICHE_SON = ("Clé : son-1\nPrénom : Mia\nRôle : son\nService : dev\nModèle : Sonnet\nLieu : local\n\n"
             "Compose les sons.\n\n## Leçons\n")
FICHE_RELECTEUR = ("Clé : relecteur-1\nPrénom : Rémi\nRôle : relecteur\nService : dev\nModèle : Sonnet\n"
                   "Lieu : local\n\nRelit.\n\n## Leçons\n")


class AvecTaches(AvecProjet):
    def setUp(self):
        super().setUp()
        (self.dossier / "fiches" / "mia.md").write_text(FICHE_SON, encoding="utf-8")
        (self.dossier / "fiches" / "remi.md").write_text(FICHE_RELECTEUR, encoding="utf-8")
        briefs = self.dossier / "fiches" / "briefs"
        briefs.mkdir()
        (briefs / "dev.md").write_text("Brief du dev : écris le code.", encoding="utf-8")
        (briefs / "son.md").write_text("Brief du son : compose.", encoding="utf-8")

    def nt(self, titre, role="dev", **extra):
        """Une tâche pas encore partie (inactive)."""
        entree = {"titre": titre, "role": role, "colonne": "dev", "active": False, **extra}
        return self.ok("tache", entree=entree)["id"]

    def suivi(self):
        return json.loads((self.dossier / "suivi.json").read_text(encoding="utf-8"))

    def ecrire_suivi(self, suivi):
        (self.dossier / "suivi.json").write_text(json.dumps(suivi), encoding="utf-8")

    def lots_(self, entree=None):
        return self.ok("lancer", "lots", entree=entree or {})


class TestTacheLots(AvecTaches):
    def test_depend_de_note_et_refuse(self):
        a = self.nt("A")
        b = self.nt("B", depend_de=[a])
        self.assertEqual(self.suivi()["taches"][1]["depend_de"], [a])
        self.assertEqual(self.outil("tache", entree={"titre": "C", "depend_de": ["t99"]})[0], 1)
        self.assertEqual(self.outil("tache", entree={"id": a, "depend_de": [a]})[0], 1)      # sur elle-même
        self.assertEqual(self.outil("tache", entree={"id": a, "depend_de": [b]})[0], 1)      # cycle a -> b -> a
        self.assertEqual(self.outil("tache", entree={"id": a, "depend_de": "t2"})[0], 1)     # pas une liste
        self.assertEqual(self.suivi()["taches"][0].get("depend_de"), [])

    def test_lot_note_et_refuse(self):
        a = self.nt("A", lot={"id": "L1", "rang": 2})
        self.assertEqual(self.suivi()["taches"][0]["lot"], {"id": "L1", "rang": 2})
        for mauvais in ({"id": "L1", "rang": 0}, {"id": "", "rang": 1}, {"id": "L1"}, "L1", {"id": "L1", "rang": True}):
            self.assertEqual(self.outil("tache", entree={"id": a, "lot": mauvais})[0], 1, mauvais)
        self.ok("tache", entree={"id": a, "lot": None})
        self.assertIsNone(self.suivi()["taches"][0]["lot"])

    def test_debut_et_fin_notes_aux_passages(self):
        a = self.nt("A")
        self.assertIsNone(self.suivi()["taches"][0].get("debut"))
        self.ok("tache", entree={"id": a, "active": True})
        t = self.suivi()["taches"][0]
        self.assertTrue(t["debut"])
        self.assertIsNone(t.get("fin"))
        self.ok("tache", entree={"id": a, "active": False})
        self.assertTrue(self.suivi()["taches"][0]["fin"])
        self.ok("tache", entree={"titre": "B", "role": "dev"})   # créée active : le début est noté tout de suite
        self.assertTrue(self.suivi()["taches"][1]["debut"])

    def test_tache_lot_releve_v4(self):
        self.nt("A", lot={"id": "L2", "rang": 3})
        self.nt("B")
        r = self.ok("releve")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        par_id = {t["id"]: t for t in r["taches"]}
        self.assertEqual(par_id["t1"]["lot"], {"id": "L2", "rang": 3})
        self.assertIsNone(par_id["t2"]["lot"])
        for mauvais in ({"id": "L2", "rang": 0}, {"id": 3, "rang": 1}, "L2"):
            r["taches"][-1]["lot"] = mauvais
            self.assertTrue(any("lot" in e for e in releve.valider(r)), mauvais)


class TestLots(AvecTaches):
    def test_exemple_de_l_utilisateur(self):
        a, b = self.nt("A"), self.nt("B")
        c = self.nt("C", "cadrage")
        d = self.nt("D", depend_de=[c])
        self.assertEqual([l["taches"] for l in self.lots_()["lots"]], [[a, b], [c], [d]])
        self.ok("tache", entree={"id": d, "depend_de": []})
        r = self.lots_()["lots"]
        self.assertEqual([(l["lot"], l["modele"], l["lieu"], l["taches"]) for l in r],
                         [("L1", "Sonnet", "local", [a, b, d]), ("L2", "Opus", "local", [c])])

    def test_lots_toutes_fonctionnalites(self):
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Première"})
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Seconde"})
        etat = self.ok("etat")["fonctionnalites"]
        a = self.nt("A", fonctionnalite=etat[0]["id"])
        b = self.nt("B", fonctionnalite=etat[1]["id"])
        c = self.nt("C", "cadrage", fonctionnalite=etat[0]["id"])
        lots_ = self.lots_()["lots"]
        self.assertEqual(lots_[0]["taches"], [a, b])   # deux fonctionnalités, un même lot
        self.assertEqual(lots_[1]["taches"], [c])

    def test_tache_partie_jamais_remise_en_lot(self):
        a, b, c = self.nt("A"), self.nt("B"), self.nt("C")
        self.ok("tache", entree={"id": a, "active": True, "agent": "dev-1"})        # partie : active
        self.ok("tache", entree={"id": b, "colonne": "fait"})                       # faite
        self.assertEqual([l["taches"] for l in self.lots_()["lots"]], [[c]])
        for i in (a, b):
            code, sortie = self.outil("lancer", "lots", entree={"taches": [i]})
            self.assertEqual(code, 1, sortie)
        self.ok("tache", entree={"id": a, "active": False})                         # mise en pause : déjà partie
        self.assertEqual([l["taches"] for l in self.lots_()["lots"]], [[c]])

    def test_taches_choisies_et_inconnues(self):
        a, b = self.nt("A"), self.nt("B")
        self.assertEqual([l["taches"] for l in self.lots_({"taches": [b]})["lots"]], [[b]])
        self.assertEqual(self.outil("lancer", "lots", entree={"taches": ["t99"]})[0], 1)
        self.assertEqual(self.outil("lancer", "lots", entree={"taches": a})[0], 1)

    def test_cycle_et_dependance_inconnue_refuses(self):
        a, b = self.nt("A"), self.nt("B")
        s = self.suivi()
        s["taches"][0]["depend_de"], s["taches"][1]["depend_de"] = [b], [a]
        self.ecrire_suivi(s)
        code, sortie = self.outil("lancer", "lots", entree={})
        self.assertEqual(code, 1, sortie)
        self.assertIn(a, json.dumps(sortie))
        s["taches"][0]["depend_de"], s["taches"][1]["depend_de"] = ["t99"], []
        self.ecrire_suivi(s)
        self.assertEqual(self.outil("lancer", "lots", entree={})[0], 1)

    def test_dependance_a_une_tache_deja_faite(self):
        a = self.nt("A")
        b = self.nt("B", depend_de=[a])
        self.ok("tache", entree={"id": a, "colonne": "fait"})
        self.assertEqual([l["taches"] for l in self.lots_()["lots"]], [[b]])

    def test_dependance_en_cours_garde_la_tache_hors_des_lots(self):
        # a est partie mais pas finie : b qui l'attend ne part pas, et ce qui attend b non plus
        a = self.nt("A")
        b = self.nt("B", depend_de=[a])
        c = self.nt("C", depend_de=[b])
        d = self.nt("D")
        self.ok("tache", entree={"id": a, "active": True, "agent": "dev-1"})
        sortie = self.lots_()
        self.assertEqual([l["taches"] for l in sortie["lots"]], [[d]])
        self.assertEqual(sorted(x["tache"] for x in sortie["ecartees"]), sorted([b, c]))
        self.assertIn(a, next(x["raison"] for x in sortie["ecartees"] if x["tache"] == b))

    def test_lot_parti_jamais_refait(self):
        # t1, t2, t3 notés dans L1 (le lot est parti) : refaire les lots ne les reprend pas
        t1, t2, t3 = self.nt("T1"), self.nt("T2"), self.nt("T3")
        for rang, i in enumerate((t1, t2, t3), 1):
            self.ok("tache", entree={"id": i, "lot": {"id": "L1", "rang": rang}})
        self.ok("tache", entree={"id": t1, "active": True, "agent": "dev-1"})
        t4 = self.nt("T4")
        self.assertEqual([l["taches"] for l in self.lots_()["lots"]], [[t4]])
        self.assertEqual(self.outil("lancer", "lots", entree={"taches": [t2]})[0], 1)

    def test_relecture_seule(self):
        a, r, b = self.nt("A"), self.nt("R", "relecteur"), self.nt("B")
        self.assertEqual([l["taches"] for l in self.lots_()["lots"]], [[a, b], [r]])

    def test_numerotation_apres_les_lots_existants(self):
        a = self.nt("A", lot={"id": "L7", "rang": 1})
        self.ok("tache", entree={"id": a, "active": True, "agent": "dev-1"})
        b = self.nt("B")
        sortie = self.lots_()["lots"]
        self.assertEqual((sortie[0]["lot"], sortie[0]["taches"]), ("L8", [b]))

    def test_tache_sans_role_ecartee(self):
        a = self.ok("tache", entree={"titre": "Sans rôle", "active": False})["id"]
        b = self.nt("B")
        sortie = self.lots_()
        self.assertEqual([l["taches"] for l in sortie["lots"]], [[b]])
        self.assertEqual([x["tache"] for x in sortie["ecartees"]], [a])

    def test_taille_du_modele_d_apres_les_mesures(self):
        # 10 tâches seules à 100 k, 6 lots dont le rang 2 coûte plus que seul : Sonnet est coupé à 1
        a, b, c = self.nt("A"), self.nt("B"), self.nt("C")
        s = self.suivi()
        base = {"t": "2026-11-11T10:00:00+01:00", "agent": None, "sortie": 0, "cache_lecture": 0, "cache_ecriture": 0,
                "estime": False, "modele": "Sonnet"}
        s["usage"] = [{**base, "id": f"u{i}", "tache": f"x{i}", "entree": 100000} for i in range(10)]
        for k in (1, 2):
            for i in range(6):
                nom = f"y{k}{i}"
                s["taches"].append({"id": nom, "titre": nom, "fonctionnalite": None, "element": None, "role": "dev",
                                    "colonne": "fait", "agent": None, "etape": "", "modele_depart": None,
                                    "montee": None, "journal": [], "bloquee": None, "active": False, "captures": [],
                                    "maj": None, "lot": {"id": f"L{i}", "rang": k}, "depend_de": []})
                s["usage"].append({**base, "id": f"v{nom}", "tache": nom, "lot": f"L{i}",
                                   "entree": 60000 if k == 1 else 150000})
        self.ecrire_suivi(s)
        sortie = self.lots_()
        self.assertEqual(sortie["tailles"]["Sonnet"], 1)
        self.assertEqual([l["taches"] for l in sortie["lots"]], [[a], [b], [c]])


class TestDepartDUnLot(AvecTaches):
    def test_depart_d_un_lot(self):
        a, b = self.nt("Écrire le menu"), self.nt("Composer le son du menu", "son")
        m = self.ok("lancer", "depart", entree={"agent": "dev-1", "taches": [a, b]})["message"]
        self.assertEqual(m.count("# Projet :"), 1)                       # un seul message de départ
        self.assertIn("Brief du dev", m)
        self.assertIn("Brief du son", m)                                 # le brief de chaque rôle présent
        self.assertLess(m.index("Écrire le menu"), m.index("Composer le son du menu"))   # dans l'ordre du lot
        self.assertIn("lancer tache", m)                                 # compte rendu à la fin de chaque tâche
        self.assertIn("avant de passer à la suivante", m)
        self.assertIn("## À la fin", m)
        # chaque tâche est marquée active à son début (sa durée sert à répartir le coût du lot)
        self.assertIn('"agent": "dev-1", "active": true', m)

    def test_depart_d_un_lot_pour_le_moteur(self):
        """Le moteur tient le suivi d'après le rapport : l'agent d'un lot ne lance aucune commande de la factory (à
        l'essai réel, il cherchait `lancer tache` et le disait indisponible)."""
        a, b = self.nt("Écrire le menu"), self.nt("Composer le son du menu", "son")
        m = self.ok("lancer", "depart", entree={"agent": "dev-1", "taches": [a, b], "moteur": True})["message"]
        self.assertNotIn("lancer tache", m)
        self.assertNotIn('"active": true', m)
        self.assertIn("un seul rapport", m)
        self.assertLess(m.index("Écrire le menu"), m.index("Composer le son du menu"))
        self.assertIn("## À la fin de ton lot", m)
        with self.assertRaises(AssertionError):     # `moteur` est un booléen
            self.ok("lancer", "depart", entree={"agent": "dev-1", "taches": [a], "moteur": "oui"})

    def test_lot_enchaine_les_durees(self):
        # le geste demandé par le message : active au début, inactive à la fin, tâche après tâche
        a, b = self.nt("A"), self.nt("B")
        for i in (a, b):
            self.ok("tache", entree={"id": i, "agent": "dev-1", "active": True})
            self.ok("tache", entree={"id": i, "active": False})
        s = {x["id"]: x for x in self.suivi()["taches"]}
        self.assertTrue(all(s[i]["debut"] and s[i]["fin"] for i in (a, b)))

    def test_depart_d_une_seule_tache_inchange(self):
        a = self.nt("Écrire le menu")
        seul = self.ok("lancer", "depart", entree={"agent": "dev-1", "tache": a})["message"]
        self.assertNotIn("avant de passer à la suivante", seul)

    def test_depart_refus(self):
        a = self.nt("A")
        for entree in ({"agent": "dev-1"}, {"agent": "dev-1", "taches": []}, {"agent": "dev-1", "taches": ["t99"]},
                       {"agent": "dev-1", "taches": [a], "tache": a}, {"agent": "inconnu", "taches": [a]},
                       {"agent": "dev-1", "taches": "t1"}):
            self.assertEqual(self.outil("lancer", "depart", entree=entree)[0], 1, entree)


TOTAL = {"entree": 1000003, "sortie": 77, "cache_lecture": 5, "cache_ecriture": 0}


class TestUsageDUnLot(AvecTaches):
    def lot_de_trois(self):
        ids = [self.nt(nom, lot={"id": "L1", "rang": k + 1}) for k, nom in enumerate("ABC")]
        s = self.suivi()
        heures = [("10:00:00", "10:00:10"), ("10:00:10", "10:00:30"), ("10:00:30", "10:01:00")]
        for t, (d, f) in zip(s["taches"], heures):
            t["debut"], t["fin"] = f"2026-11-11T{d}+01:00", f"2026-11-11T{f}+01:00"
        self.ecrire_suivi(s)
        return ids

    def test_usage_d_un_lot_une_ligne_par_tache(self):
        ids = self.lot_de_trois()
        r = self.ok("usage", entree={"lot": "L1", "modele": "Sonnet", **TOTAL})
        self.assertEqual(len(r["ids"]), 3)
        lignes = self.suivi()["usage"]
        self.assertEqual([u["tache"] for u in lignes], ids)
        for u in lignes:
            self.assertEqual((u["lot"], u["reparti"]), ("L1", "temps"))
        for c in TOTAL:
            self.assertEqual(sum(u[c] for u in lignes), TOTAL[c], c)   # la somme vaut exactement le total
        self.assertGreater(lignes[2]["entree"], lignes[0]["entree"])
        self.assertEqual(self.outil("usage", entree={"lot": "L1", "modele": "Sonnet", **TOTAL})[0], 1)   # une seule fois

    def test_usage_d_un_lot_parts_egales_sans_duree(self):
        for k, nom in enumerate("AB"):
            self.nt(nom, lot={"id": "L1", "rang": k + 1})
        self.ok("usage", entree={"lot": "L1", "modele": "Sonnet", "total": 101})
        lignes = self.suivi()["usage"]
        self.assertEqual([u["reparti"] for u in lignes], ["egal", "egal"])
        self.assertEqual(sum(u["entree"] for u in lignes), 101)
        self.assertTrue(all(u["estime"] for u in lignes))

    def test_usage_lot_inconnu_et_champs(self):
        self.nt("A", lot={"id": "L1", "rang": 1})
        for entree in ({"lot": "L9", "modele": "Sonnet", "total": 5}, {"lot": "L1", "total": 5},
                       {"lot": "L1", "modele": "Sonnet", "total": 5, "tache": "t99"},
                       {"lot": "L1", "modele": "Sonnet"}):
            self.assertEqual(self.outil("usage", entree=entree)[0], 1, entree)

    def test_usage_cumulatif_ecarts_exacts(self):
        ids = [self.nt(nom, lot={"id": "L1", "rang": k + 1}) for k, nom in enumerate("AB")]
        base = {"modele": "Sonnet", "lot": "L1", "id": "cumul-1", "sortie": 0}
        self.ok("usage", entree={**base, "tache": ids[0], "entree": 100})
        self.ok("usage", entree={**base, "tache": ids[1], "entree": 250})
        lignes = self.suivi()["usage"]
        self.assertEqual([(u["tache"], u["entree"]) for u in lignes], [(ids[0], 100), (ids[1], 150)])
        self.assertTrue(all(u.get("reparti") is None for u in lignes))
        self.assertEqual(self.outil("usage", entree={**base, "tache": ids[1], "entree": 200})[0], 1)   # un cumul qui recule
        self.assertEqual(self.outil("usage", entree={**base, "tache": "t99", "entree": 300})[0], 1)

    def test_releve_porte_lot_et_reparti(self):
        self.lot_de_trois()
        self.ok("usage", entree={"lot": "L1", "modele": "Sonnet", **TOTAL})
        r = self.ok("releve")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        self.assertEqual({(u["lot"], u["reparti"]) for u in r["usage"]}, {("L1", "temps")})
        r["usage"][0]["reparti"] = "au-hasard"
        self.assertTrue(any("reparti" in e for e in releve.valider(r)))


PRIX = {"sonnet": {"entree": 3.0, "sortie": 15.0, "cache_lecture": 0.3, "cache_ecriture": 3.75}}


def prix_de(modele, date_iso):
    return dict(PRIX[modele]), "2026-11-01", False


class TestFacturationLots(unittest.TestCase):
    def ligne(self, id_, tache, entree, **extra):
        return {"id": id_, "tache": tache, "agent": "d1", "service": "dev", "modele": "sonnet", "etape": "dev",
                "t": "2026-11-09T10:00:00+00:00", "t_prix": "2026-11-09T10:00:00+00:00", "entree": entree,
                "sortie": 0, "cache_lecture": 0, "cache_ecriture": 0, **extra}

    def facturer(self, usages):
        r = {"version": 3, "taches": [{"id": "t1", "titre": "A"}, {"id": "t2", "titre": "B"}]}
        return cout.facturation(usages, prix_de, r, "7j", datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc))

    def test_facturation_totaux_inchanges_avec_lot(self):
        seul = self.facturer([self.ligne("u1", "t1", 1_000_000), self.ligne("u2", "t2", 1_000_000)])
        en_lot = self.facturer([self.ligne("u1", "t1", 400_000, lot="L1", reparti="temps"),
                                self.ligne("u2", "t2", 1_600_000, lot="L1", reparti="temps")])
        autre = self.facturer([self.ligne("u1", "t1", 1_000_000, lot="L1", reparti="egal"),
                               self.ligne("u2", "t2", 1_000_000, lot="L1", reparti="egal")])
        self.assertEqual(seul["total"], en_lot["total"])
        self.assertEqual(seul["total"], autre["total"])
        self.assertEqual(seul["services"]["dev"]["modeles"], en_lot["services"]["dev"]["modeles"])
        self.assertAlmostEqual(en_lot["services"]["dev"]["taches"]["t1"]["total"], 1.2)   # la part, pas la moyenne
        # la tâche aux parts réparties est marquée ; une tâche seule ne l'est pas
        self.assertTrue(en_lot["services"]["dev"]["taches"]["t1"]["reparti"])
        self.assertNotIn("reparti", seul["services"]["dev"]["taches"]["t1"])
        self.assertEqual({u["reparti"] for u in en_lot["services"]["dev"]["usages"]}, {"temps"})

    def test_usage_cumulatif_d_un_lot_n_est_pas_marque_estime(self):
        f = self.facturer([self.ligne("u1", "t1", 100, lot="L1"), self.ligne("u2", "t2", 150, lot="L1")])
        self.assertNotIn("reparti", f["services"]["dev"]["taches"]["t1"])


if __name__ == "__main__":
    unittest.main()
