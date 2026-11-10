import tempfile
import unittest
from pathlib import Path

from bureau import equipe


class TestEquipe(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.f = Path(self._t.name) / "equipe.json"

    def test_prenoms_et_couleurs(self):
        self.assertEqual((len(equipe.PRENOMS), len(set(equipe.PRENOMS)), len(set(equipe.COULEURS))), (24, 24, 12))
        for c in equipe.COULEURS:
            self.assertRegex(c, r"^#[0-9a-f]{6}$")

    def test_attribution_stable(self):
        e = equipe.Equipe(self.f)
        a = e.agent("dev:1")
        b = e.agent("dev:2")
        self.assertNotEqual(a["prenom"], b["prenom"])
        self.assertEqual(equipe.Equipe(self.f).agent("dev:1"), a)  # relu depuis le disque

    def test_modification_a_la_main_respectee(self):
        self.f.write_text('{"agents": {"dev:1": {"prenom": "Zoé", "couleur": "#000000", "modele": "Haiku"}}}',
                          encoding="utf-8")
        self.assertEqual(equipe.Equipe(self.f).agent("dev:1"),
                         {"prenom": "Zoé", "couleur": "#000000", "modele": "Haiku"})

    def test_plus_de_24(self):
        e = equipe.Equipe(self.f)
        noms = [e.agent(f"k{i}")["prenom"] for i in range(26)]
        self.assertEqual(len(set(noms)), 26)
        self.assertEqual(noms[24], "Agent 25")

    def test_chef(self):
        self.assertEqual(equipe.Equipe(self.f).agent("chef")["prenom"], "Chef")
        self.assertEqual(equipe.Equipe(self.f).agent("autre", chef=True)["prenom"], "Chef")

    def test_prenom_du_releve_non_ecrit(self):
        e = equipe.Equipe(self.f)
        a = e.agent("k", prenom="Maëlle")
        self.assertEqual(a["prenom"], "Maëlle")
        self.assertRegex(a["couleur"], r"^#[0-9a-f]{6}$")
        self.assertNotIn("Maëlle", self.f.read_text(encoding="utf-8"))
        self.assertEqual(e.agent("k", prenom="Maëlle")["couleur"], a["couleur"])
        self.assertEqual(equipe.Equipe(self.f).agent("k", prenom="Autre")["prenom"], "Autre")
        # aucun prénom tiré : le prochain agent reçoit le premier de la liste
        self.assertEqual(e.agent("z")["prenom"], equipe.PRENOMS[0])

    def test_prenom_du_releve_remplace_celui_du_fichier(self):
        self.f.write_text('{"agents": {"k": {"prenom": "Zoé", "couleur": "#000000"}}}', encoding="utf-8")
        e = equipe.Equipe(self.f)
        self.assertEqual(e.agent("k", prenom="Maëlle")["prenom"], "Maëlle")
        self.assertIn("Zoé", self.f.read_text(encoding="utf-8"))  # le fichier n'est pas réécrit
        self.assertEqual(e.agent("k")["prenom"], "Zoé")  # sans prénom du relevé, celui du fichier revient

    def test_agent_cree_avec_prenom_puis_sans(self):
        e = equipe.Equipe(self.f)
        e.agent("k", prenom="Maëlle")
        self.assertEqual(e.agent("k")["prenom"], equipe.PRENOMS[0])
        self.assertEqual(equipe.Equipe(self.f).agent("k")["prenom"], equipe.PRENOMS[0])

    def test_fichier_illisible_mis_de_cote(self):
        self.f.write_text("{", encoding="utf-8")
        equipe.Equipe(self.f).agent("a")
        self.assertTrue(self.f.with_name(self.f.name + ".illisible").exists())

    def test_prenom_pris_a_la_main_non_reattribue(self):
        self.f.write_text('{"agents": {"x": {"prenom": "%s", "couleur": "#000000"}}}' % equipe.PRENOMS[0],
                          encoding="utf-8")
        self.assertNotEqual(equipe.Equipe(self.f).agent("y")["prenom"], equipe.PRENOMS[0])


if __name__ == "__main__":
    unittest.main()
