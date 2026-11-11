"""Les lots par modèle : former, répartir le coût, taille conseillée (tâche 17)."""
import unittest

from orchestrateur import lots


def tache(i, modele="Sonnet", lieu="local", role="dev", depend_de=()):
    return {"id": i, "modele": modele, "lieu": lieu, "role": role, "depend_de": list(depend_de)}


def ids(resultat):
    return [l["taches"] for l in resultat]


class TestFormer(unittest.TestCase):
    def test_exemple_de_l_utilisateur(self):
        # a, b, d en Sonnet, c en Opus, sans dépendance : les trois Sonnet ensemble
        base = [tache("a"), tache("b"), tache("c", "Opus"), tache("d")]
        self.assertEqual(ids(lots.former(base)), [["a", "b", "d"], ["c"]])
        # d dépend de c : [a, b], [c], [d]
        avec = [tache("a"), tache("b"), tache("c", "Opus"), tache("d", depend_de=["c"])]
        self.assertEqual(ids(lots.former(avec)), [["a", "b"], ["c"], ["d"]])

    def test_numerotation_et_lots_rendus(self):
        r = lots.former([tache("a"), tache("c", "Opus")])
        self.assertEqual([(l["lot"], l["modele"], l["lieu"]) for l in r],
                         [("L1", "Sonnet", "local"), ("L2", "Opus", "local")])
        self.assertEqual(lots.former([tache("a")], premier=4)[0]["lot"], "L4")

    def test_ordre_garde_sans_dependance_connue_entre_modeles(self):
        base = [tache("t1", "Haiku"), tache("t2"), tache("t3", "Haiku"), tache("t4"), tache("t5", "Haiku")]
        self.assertEqual(ids(lots.former(base)), [["t1", "t3", "t5"], ["t2", "t4"]])   # l'ordre interne suit l'origine

    def test_lieu_separe_les_lots(self):
        base = [tache("a"), tache("b", lieu="cloud"), tache("c")]
        self.assertEqual(ids(lots.former(base)), [["a", "c"], ["b"]])

    def test_relecture_jamais_en_lot(self):
        base = [tache("a"), tache("r", role="relecteur"), tache("b"), tache("r2", role="relecteur")]
        self.assertEqual(ids(lots.former(base)), [["a", "b"], ["r"], ["r2"]])

    def test_relecture_qui_depend_du_travail_relu(self):
        base = [tache("a"), tache("r", role="relecteur", depend_de=["a"]), tache("b")]
        self.assertEqual(ids(lots.former(base)), [["a", "b"], ["r"]])

    def test_chaine_d_un_meme_modele_en_un_lot(self):
        # a -> b -> c, même modèle et même lieu : un lot les enchaîne dans l'ordre, une seule conversation
        base = [tache("a"), tache("b", depend_de=["a"]), tache("c", depend_de=["b"])]
        self.assertEqual(ids(lots.former(base)), [["a", "b", "c"]])
        # la dépendance doit être placée plus tôt dans le lot : c avant b dans l'ordre d'origine reste correct
        base = [tache("c", depend_de=["b"]), tache("a"), tache("b", depend_de=["a"])]
        self.assertEqual(ids(lots.former(base)), [["a", "b", "c"]])
        # une dépendance d'un autre modèle coupe toujours
        base = [tache("a"), tache("o", "Opus", depend_de=["a"]), tache("b", depend_de=["o"])]
        self.assertEqual(ids(lots.former(base)), [["a"], ["o"], ["b"]])

    def test_lot_de_cinq_au_plus(self):
        base = [tache(f"t{i}") for i in range(12)]
        r = lots.former(base)
        self.assertEqual([len(l["taches"]) for l in r], [5, 5, 2])
        self.assertEqual(sum(ids(r), []), [f"t{i}" for i in range(12)])   # l'ordre d'origine est gardé

    def test_former_respecte_la_taille_du_modele(self):
        base = [tache(f"s{i}") for i in range(4)] + [tache(f"h{i}", "Haiku") for i in range(4)]
        r = lots.former(base, {"Sonnet": 2, "Haiku": 3})
        self.assertEqual(ids(r), [["s0", "s1"], ["s2", "s3"], ["h0", "h1", "h2"], ["h3"]])
        self.assertEqual(len(lots.former([tache(f"t{i}") for i in range(8)], {"Sonnet": 99})[0]["taches"]), 5)

    def test_cycle_refuse(self):
        base = [tache("a", depend_de=["b"]), tache("b", depend_de=["a"]), tache("c")]
        with self.assertRaises(ValueError) as e:
            lots.former(base)
        self.assertIn("a", str(e.exception))
        self.assertIn("b", str(e.exception))
        with self.assertRaises(ValueError):
            lots.former([tache("a", depend_de=["a"])])

    def test_dependance_inconnue_refusee(self):
        with self.assertRaises(ValueError) as e:
            lots.former([tache("a", depend_de=["zz"])])
        self.assertIn("zz", str(e.exception))

    def test_sans_tache(self):
        self.assertEqual(lots.former([]), [])


COMPTEURS = ("entree", "sortie", "cache_lecture", "cache_ecriture")


class TestRepartir(unittest.TestCase):
    def test_repartir_somme_exacte(self):
        total = {"entree": 1000003, "sortie": 77, "cache_lecture": 5, "cache_ecriture": 0}
        taches = [{"id": "t1", "debut": "2026-11-11T10:00:00+01:00", "fin": "2026-11-11T10:00:10+01:00"},
                  {"id": "t2", "debut": "2026-11-11T10:00:10+01:00", "fin": "2026-11-11T10:00:30+01:00"},
                  {"id": "t3", "debut": "2026-11-11T10:00:30+01:00", "fin": "2026-11-11T10:01:00+01:00"}]
        parts = lots.repartir(total, taches)
        for c in COMPTEURS:
            self.assertEqual(sum(parts[t][c] for t in parts), total[c], c)
        self.assertEqual(lots.mode_repartition(taches), "temps")
        self.assertGreater(parts["t3"]["entree"], parts["t2"]["entree"])   # au prorata des durées (10, 20, 30 s)
        self.assertGreater(parts["t2"]["entree"], parts["t1"]["entree"])
        self.assertTrue(all(isinstance(v, int) for p in parts.values() for v in p.values()))

    def test_repartir_parts_egales_sans_duree(self):
        total = {"entree": 10, "sortie": 4, "cache_lecture": 0, "cache_ecriture": 1}
        taches = [{"id": "t1", "debut": None, "fin": None}, {"id": "t2"},
                  {"id": "t3", "debut": "2026-11-11T10:00:00+01:00", "fin": "2026-11-11T10:00:00+01:00"}]
        parts = lots.repartir(total, taches)
        self.assertEqual(lots.mode_repartition(taches), "egal")
        for c in COMPTEURS:
            self.assertEqual(sum(p[c] for p in parts.values()), total[c], c)
        self.assertEqual(sorted(p["entree"] for p in parts.values()), [3, 3, 4])

    def test_une_duree_nulle_suffit_pour_des_parts_egales(self):
        taches = [{"id": "a", "debut": "2026-11-11T10:00:00+01:00", "fin": "2026-11-11T10:00:20+01:00"},
                  {"id": "b", "debut": "2026-11-11T10:00:20+01:00", "fin": "2026-11-11T10:00:20+01:00"}]
        self.assertEqual(lots.mode_repartition(taches), "egal")
        parts = lots.repartir({"entree": 100, "sortie": 0}, taches)
        self.assertEqual((parts["a"]["entree"], parts["b"]["entree"]), (50, 50))

    def test_total_nul_et_une_seule_tache(self):
        self.assertEqual(lots.repartir({}, [{"id": "a"}]), {"a": dict.fromkeys(COMPTEURS, 0)})
        self.assertEqual(lots.repartir({"entree": 7}, [{"id": "a"}])["a"]["entree"], 7)


def usage(modele="Sonnet", tokens=100000, tache=None, lot=None, rang=None):
    return {"modele": modele, "entree": tokens, "sortie": 0, "cache_lecture": 0, "cache_ecriture": 0,
            "tache": tache, "lot": lot, "rang": rang}


class TestTailleConseillee(unittest.TestCase):
    def seules(self, n=10, tokens=100000):
        return [usage(tokens=tokens, tache=f"s{i}") for i in range(n)]

    def test_taille_conseillee_sans_mesures_5(self):
        self.assertEqual(lots.taille_conseillee([], "Sonnet"), 5)
        self.assertEqual(lots.taille_conseillee(self.seules(9), "Sonnet"), 5)
        en_lot = [usage(tokens=60000, tache=f"l{i}", lot="L1", rang=i % 3 + 1) for i in range(9)]
        self.assertEqual(lots.taille_conseillee(self.seules() + en_lot, "Sonnet"), 5)   # 9 tâches en lot seulement

    def test_taille_conseillee_coupe_au_rang_trop_cher(self):
        en_lot = []
        for k, tokens in ((1, 60000), (2, 60000), (3, 60000), (4, 130000)):
            en_lot += [usage(tokens=tokens, tache=f"l{k}-{i}", lot=f"L{i}", rang=k) for i in range(3)]
        self.assertEqual(lots.taille_conseillee(self.seules() + en_lot, "Sonnet"), 3)

    def test_taille_conseillee_jamais_plus_de_5(self):
        en_lot = [usage(tokens=10000, tache=f"l{k}-{i}", lot=f"L{i}", rang=k) for k in range(1, 8) for i in range(2)]
        self.assertEqual(lots.taille_conseillee(self.seules() + en_lot, "Sonnet"), 5)

    def test_taille_conseillee_un_seul_si_le_rang_deux_coute_trop(self):
        en_lot = [usage(tokens=60000 if k == 1 else 150000, tache=f"l{k}-{i}", lot=f"L{i}", rang=k)
                  for k in (1, 2) for i in range(6)]
        self.assertEqual(lots.taille_conseillee(self.seules() + en_lot, "Sonnet"), 1)

    def test_taille_conseillee_un_modele_a_la_fois(self):
        en_lot = [usage("Opus", 500000, tache=f"o{k}-{i}", lot=f"L{i}", rang=k) for k in (1, 2) for i in range(6)]
        self.assertEqual(lots.taille_conseillee(self.seules() + en_lot, "Sonnet"), 5)   # Sonnet : rien en lot


if __name__ == "__main__":
    unittest.main()
