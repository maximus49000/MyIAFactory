"""La consigne des agents et le lieu « Serveur » des tests (conception § 5.10, § 5.1/5.2) : `depart.tests_un_a_la_fois`
(ligne du lieu), `outil._route_du_depart`, la validation des réglages, `actions_exposees`, la proposition d'installation."""
import unittest
import unittest.mock
from types import SimpleNamespace

from bureau import deport, deport_types
from installation import proposition
from orchestrateur import depart, outil

ENVOIE = "Il les envoie au serveur"


class TestConsigne(unittest.TestCase):
    def test_local_route(self):
        t = depart.tests_un_a_la_fois(route=True)
        self.assertIn(ENVOIE, t)
        self.assertIn('lancer.py" tests --', t)
        self.assertNotIn("une seule campagne de tests à la fois sur le poste", t.split("\n")[0])
        self.assertIn("injoignable", t)

    def test_local_sans_route_inchange(self):
        self.assertEqual(depart.tests_un_a_la_fois(route=False), depart.tests_un_a_la_fois())
        self.assertIn("une seule campagne de tests à la fois sur le poste", depart.tests_un_a_la_fois())
        self.assertNotIn(ENVOIE, depart.tests_un_a_la_fois())

    def test_message_passe_la_route(self):
        import inspect
        for f in (depart.message, depart.message_lot):
            self.assertIn("route", inspect.signature(f).parameters)

    def test_plafond(self):
        self.assertLessEqual(len(depart.tests_un_a_la_fois(route=True)), 1450)


class TestRouteDuDepart(unittest.TestCase):
    ctx = SimpleNamespace(f={"base": "/x/p/.factory"})

    def test_accord(self):
        with unittest.mock.patch.object(deport_types, "refus_route", return_value=None):
            self.assertTrue(outil._route_du_depart(self.ctx))

    def test_refus_ou_souci(self):
        with unittest.mock.patch.object(deport_types, "refus_route", return_value="non"):
            self.assertFalse(outil._route_du_depart(self.ctx))
        with unittest.mock.patch.object(deport_types, "refus_route", side_effect=RuntimeError):
            self.assertFalse(outil._route_du_depart(self.ctx))
        self.assertFalse(outil._route_du_depart(SimpleNamespace(f={})))


class TestLieuServeur(unittest.TestCase):
    def test_validation_accepte_serveur_pour_tests(self):
        self.assertEqual(deport.valider_lieux({"tests": "serveur"}, catalogue=deport_types.GENERIQUE),
                         {"tests": "serveur"})

    def test_validation_refuse_serveur_pour_apk(self):
        with self.assertRaises(ValueError):
            deport.valider_lieux({"apk": "serveur"}, catalogue=deport_types.GENERIQUE)

    def test_actions_exposees_routee(self):
        par_id = {a["id"]: a for a in deport_types.actions_exposees(deport_types.GENERIQUE)}
        self.assertTrue(par_id["tests"]["routee_au_serveur"])
        self.assertFalse(par_id["tests"]["servie_au_serveur"])
        self.assertFalse(par_id["apk"]["routee_au_serveur"])
        self.assertIsNone(par_id["tests"]["bientot"])


class TestInstallation(unittest.TestCase):
    def test_proposition_installation_avec_tests_image(self):
        avec = [{"base": "presente", "tests-image": "presente"}]
        self.assertEqual(proposition.lieu_tests_propose(avec), "serveur")
        self.assertEqual(proposition.lieu_tests_propose([{"tests-image": "absente"}]), "poste")
        self.assertEqual(proposition.lieu_tests_propose([{"base": "presente"}, {"tests-image": "fait"}]), "serveur")
        self.assertEqual(proposition.lieu_tests_propose([]), "poste")
        self.assertEqual(proposition.lieu_tests_propose(None), "poste")


if __name__ == "__main__":
    unittest.main()
