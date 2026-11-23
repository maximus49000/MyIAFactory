"""« Évaluer les tests sur le serveur » (tâche 15b) : la commande `evaluer-tests-serveur` (profil changé, construction approuvée)
et le moteur, qui lance l'évaluation et la construction détachées, sur le clic ou la réponse du Directeur (jamais un agent)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.orch_aide import AvecProjet, factory_minimale

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import tests_profil  # noqa: E402

FIXTURE = RACINE / "tests" / "fixtures" / "profils" / "python-stdlib"


class Commande(AvecProjet):
    def setUp(self):
        super().setUp()
        shutil.copytree(FIXTURE, self.dossier, dirs_exist_ok=True)
        self.factory = factory_minimale(self.dossier / ".factory")      # la racine du projet : self.dossier
        self.reglages = self.dossier / ".factory" / "reglages.json"

    def adoption(self, **adoption):
        self.reglages.write_text(json.dumps({"tests": {"adoption": adoption}}), encoding="utf-8")

    def evaluer(self, entree):
        return self.outil("lancer", "evaluer-tests-serveur", entree=entree)

    def test_profil_change_pose_tests_profil_une_fois(self):
        self.adoption(statut="passe", empreinte_profil="ancienne")
        code, r = self.evaluer({"profil_change": True})
        self.assertEqual(code, 0, r)
        self.assertTrue(r["decision"])
        self.assertEqual(self.evaluer({"profil_change": True})[1]["decision"], r["decision"])   # une seule décision
        etat = self.ok("etat")
        d = next(x for x in etat["decisions"] if x["id"] == r["decision"])
        self.assertEqual(d["genre"], "tests_profil")
        self.assertEqual(d["charge"]["precedente"], "ancienne")
        self.assertEqual(d["reponses"], ["reevaluer", "plus_tard"])

    def test_profil_inchange_ou_jamais_evalue_rien_a_decider(self):
        self.assertIsNone(self.evaluer({"profil_change": True})[1]["decision"])
        empreinte = tests_profil.analyser(str(self.dossier)).empreinte
        self.adoption(statut="passe", empreinte_profil=empreinte)
        self.assertIsNone(self.evaluer({"profil_change": True})[1]["decision"])

    def test_sans_confirme_ou_sans_image_approuvee_rien_ne_part(self):
        self.adoption(statut="image_a_construire")
        with mock.patch.dict(sys.modules, {"tests_adoption": None}):   # l'évaluation n'est jamais importée
            code, r = self.evaluer({})
            self.assertEqual(code, 1)
            self.assertIn("confirme", r["erreur"])
        code, r = self.evaluer({"confirme": True, "construire": True})
        self.assertEqual(code, 1)
        self.assertIn("approuvée", r["erreur"])


class Moteur(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        factory = Path(self._t.name) / ".factory" / "factory.json"
        factory.parent.mkdir()
        factory.write_text("{}", encoding="utf-8")
        self.projet = mock.Mock(factory=factory, ligne_a_dire=None)
        self.lances = []

    def lancer_processus(self, pid):
        def faux(argv, entree, sortie, erreurs, env, cwd):
            self.lances.append((argv, json.loads(Path(entree).read_text(encoding="utf-8"))))
            return mock.Mock(pid=pid)
        return faux

    def test_clic_evaluer_lance_une_evaluation_detachee_une_seule_fois(self):
        from moteur import detache, regles
        demande = {"id": "q1", "type": "evaluer_tests_serveur", "confirme": True}
        with mock.patch.object(regles, "lancer") as lancer, \
                mock.patch.object(detache, "lancer_processus", self.lancer_processus(os.getpid())):
            self.assertEqual(regles.traiter_demande(self.projet, demande, regles.nouvel_etat()), [])
            regles.traiter_demande(self.projet, {**demande, "id": "q2"}, regles.nouvel_etat())   # déjà en cours
        self.assertEqual(len(self.lances), 1)
        argv, entree = self.lances[0]
        self.assertEqual(argv[-2:], ["lancer", "evaluer-tests-serveur"])
        self.assertEqual(entree, {"confirme": True})
        reponses = [c.args[2]["reponse"] for c in lancer.call_args_list if c.args[1] == "demande-traitee"]
        self.assertIn("code du projet", reponses[0])
        self.assertIn("déjà en cours", reponses[1])

    def test_sans_confirme_rien_ne_part(self):
        from moteur import detache, regles
        with mock.patch.object(regles, "lancer"), \
                mock.patch.object(detache, "lancer_processus", self.lancer_processus(1)):
            regles.traiter_demande(self.projet, {"id": "q1", "type": "evaluer_tests_serveur"}, regles.nouvel_etat())
        self.assertEqual(self.lances, [])

    def test_reponse_construire_puis_evaluer(self):
        from moteur import detache, regles

        def lancer(projet, nom, entree=None):
            if nom == "evaluer-tests-serveur":
                return {"construire": {"fait": "Approuvée.", "suite": "construire"},
                        "plus_tard": {"fait": "Rien ne change.", "suite": None}}[entree["verdict"]]
            return {}
        with mock.patch.object(regles, "lancer", side_effect=lancer), \
                mock.patch.object(detache, "lancer_processus", self.lancer_processus(999999999)):
            regles.traiter_demande(self.projet, {"id": "q1", "type": "tests_serveur", "decision": "d1",
                                                 "verdict": "plus_tard"}, regles.nouvel_etat())
            self.assertEqual(self.lances, [])
            regles.traiter_demande(self.projet, {"id": "q2", "type": "tests_serveur", "decision": "d1",
                                                 "verdict": "construire"}, regles.nouvel_etat())
        self.assertEqual([e for _a, e in self.lances], [{"confirme": True, "construire": True}])


if __name__ == "__main__":
    unittest.main()
