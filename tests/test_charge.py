import sys
import tempfile
import time
import unittest
from pathlib import Path

from bureau import charge

MACH = {"coeurs": 8, "memoire_totale_go": 16}


def lignes(n, ch, agents):
    return [{"t": i, "charge": ch, "agents_locaux": agents} for i in range(n)]


class TestCharge(unittest.TestCase):
    def test_lisseur(self):
        l = charge.Lisseur(60)
        for t, c in ((0, 100), (30, 20), (70, 40)):
            l.ajouter(t, c)
        self.assertEqual(l.moyenne(), 30.0)
        self.assertEqual(charge.Lisseur().moyenne(), 0.0)

    def test_affichee(self):
        self.assertEqual([charge.affichee(*a) for a in ((12.4, 61.6), (120, 5), (-3, -1))], [62, 100, 0])

    def test_feu_vert(self):
        self.assertEqual([charge.feu_vert(75, 75), charge.feu_vert(76, 75)], [True, False])

    def test_conseil_machine(self):
        for mach, attendu in (({"coeurs": 8, "memoire_totale_go": 16}, 70),
                              ({"coeurs": 4, "memoire_totale_go": 16}, 60),
                              ({"coeurs": 4, "memoire_totale_go": 4}, 50)):
            c = charge.conseiller([], mach)
            self.assertEqual((c["valeur"], c["source"]), (attendu, "machine"))
            self.assertIn("%", c["explication"])

    def test_conseil_historique(self):  # repos 30, un agent ajoute 22 -> 85-22=63 -> 60
        h = lignes(20, 30, 0) + lignes(20, 52, 1) + lignes(20, 74, 2)
        c = charge.conseiller(h, MACH)
        self.assertEqual((c["valeur"], c["source"]), (60, "historique"))
        self.assertIn("60 %", c["explication"])

    def test_conseil_borne_basse(self):  # repos 70, par agent 40 -> brute 45, plancher 75
        h = lignes(10, 70, 0) + lignes(30, 110, 1)
        self.assertEqual(charge.conseiller(h, MACH)["valeur"], 75)

    def test_conseil_borne_haute(self):  # par agent 0 -> 85
        h = lignes(10, 30, 0) + lignes(30, 30, 1)
        self.assertEqual(charge.conseiller(h, MACH)["valeur"], 85)

    def test_conseil_sans_repos_utilise_le_minimum(self):
        c = charge.conseiller(lignes(30, 50, 1), MACH)
        self.assertEqual(c["source"], "historique")
        self.assertTrue(40 <= c["valeur"] <= 85)

    def test_conseil_peu_de_mesures(self):
        self.assertEqual(charge.conseiller(lignes(29, 50, 1), MACH)["source"], "machine")

    def test_historique(self):
        with tempfile.TemporaryDirectory() as d:
            h = charge.Historique(Path(d) / "h.jsonl")
            now = 1_800_000_000.0
            h.noter(now - 8 * 86400, 10, 0)
            h.noter(now - 60, 20, 1)
            h.noter(now, 30, 2)
            with open(Path(d) / "h.jsonl", "a", encoding="utf-8") as f:
                f.write("pas du json\n")
            lus = h.lire()
            self.assertEqual([x["charge"] for x in lus], [20, 30])
            self.assertEqual(lus[1], {"t": now, "charge": 30, "agents_locaux": 2})

    def test_historique_absent(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(charge.Historique(Path(d) / "x.jsonl").lire(), [])

    @unittest.skipUnless(sys.platform == "win32", "Windows")
    def test_sonde_reelle(self):
        s = charge.Sonde()
        s.lire()
        time.sleep(0.3)
        m = s.lire()
        self.assertTrue(0 <= m["cpu"] <= 100 and 0 < m["memoire"] <= 100)
        self.assertTrue(charge.machine()["coeurs"] >= 1 and charge.machine()["memoire_totale_go"] > 0.5)


if __name__ == "__main__":
    unittest.main()
