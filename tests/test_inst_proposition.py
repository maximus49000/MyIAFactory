"""Le contrôle d'une proposition d'installation."""
import unittest

from installation import proposition
from tests.inst_aide import proposition_valide


class TestProposition(unittest.TestCase):
    def erreurs(self, **extra):
        return proposition.verifier(proposition_valide("/tmp/p", **extra))

    def avec_agent(self, **champs):
        p = proposition_valide("/tmp/p")
        p["agents"][0].update(champs)
        return proposition.verifier(p)

    def test_proposition_valide(self):
        self.assertEqual(proposition.verifier(proposition_valide("/tmp/p")), [])

    def test_fable_refuse(self):
        e = self.avec_agent(modele="Fable")
        self.assertIn("Fable n'est jamais choisi par l'installation.", " ".join(e))
        e = self.erreurs(modele_orchestrateur="Fable")
        self.assertIn("Fable n'est jamais choisi par l'installation.", " ".join(e))

    def test_role_sans_agent(self):
        p = proposition_valide("/tmp/p")
        p["agents"] = p["agents"][:1]
        e = proposition.verifier(p)
        self.assertTrue(any("relecteur" in x for x in e), e)

    def test_cloud_interdit_sans_cloud(self):
        self.assertTrue(self.avec_agent(lieu="cloud"))
        p = proposition_valide("/tmp/p", cloud=True)
        p["agents"][0]["lieu"] = "cloud"
        self.assertEqual(proposition.verifier(p), [])

    def test_justification_manquante(self):
        p = proposition_valide("/tmp/p")
        p["flux"][1]["justification"] = "  "
        e = proposition.verifier(p)
        self.assertTrue(any("justification" in x for x in e), e)

    def test_brief_manquant(self):
        p = proposition_valide("/tmp/p")
        del p["briefs"]["relecteur"]
        self.assertTrue(any("brief" in x for x in proposition.verifier(p)))

    def test_ids_reserves_et_services_inconnus(self):
        p = proposition_valide("/tmp/p")
        p["flux"][0]["id"] = "cadrage"
        self.assertTrue(proposition.verifier(p))
        p = proposition_valide("/tmp/p")
        p["flux"][0]["service"] = "inconnu"
        self.assertTrue(proposition.verifier(p))
        self.assertTrue(self.avec_agent(service="inconnu"))

    def test_cles_uniques_et_sures(self):
        self.assertTrue(self.avec_agent(cle="relecteur-1"))
        self.assertTrue(self.avec_agent(cle="../evasion"))
        self.assertTrue(self.avec_agent(prenom="Noé\nRôle : chef"))

    def test_bornes(self):
        for champs in ({"charge_max": 29}, {"charge_max": 96}, {"charge_max": True}, {"agents_locaux_max": 0},
                       {"agents_locaux_max": 17}, {"cloud": "oui"}, {"facturation": None}, {"version": 2},
                       {"cas": "installe"}, {"projet": "relatif"}, {"genre": "Pas Bon"}, {"mots_interdits": "x"},
                       {"controles": ["sur\ndeux lignes"]}):
            with self.subTest(champs=champs):
                self.assertTrue(self.erreurs(**champs))

    def test_facturation_service_a_la_main(self):
        services = [{"id": "dev", "nom": "Dev"}, {"id": "qa", "nom": "QA"}, {"id": "facturation", "nom": "Facturation"}]
        self.assertTrue(self.erreurs(services=services))
        self.assertTrue(self.erreurs(services=services, facturation=False))

    def test_genre_nouveau_demande_un_genre_et_une_description(self):
        self.assertTrue(self.erreurs(genre_nouveau={"description": "Des outils"}))
        self.assertTrue(self.erreurs(genre="outils", genre_nouveau={"description": " "}))
        self.assertEqual(self.erreurs(genre="outils", genre_nouveau={"description": "Des outils"}), [])

    def test_pas_un_objet(self):
        self.assertTrue(proposition.verifier([]))


if __name__ == "__main__":
    unittest.main()
