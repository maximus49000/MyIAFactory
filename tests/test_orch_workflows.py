"""Un genre et un workflow par fonctionnalité : les données (factory, suivi) et leur lecture par le relevé."""
import json
import unittest

from bureau import releve
from orchestrateur import factory as fa
from orchestrateur import workflows as wf
from tests.orch_aide import AvecProjet

PRINCIPAL = [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"},
             {"id": "relecture", "nom": "Relecture", "role": "relecteur", "service": "dev"}]


def etape(i, nom=None, role="dev", service="dev"):
    return {"id": i, "nom": nom or i.capitalize(), "role": role, "service": service}


class AvecWorkflows(AvecProjet):
    def reecrire(self, **champs):
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d.update(champs)
        self.factory.write_text(json.dumps(d), encoding="utf-8")

    def lire(self):
        return fa.lire(self.factory)

    def nouvelle(self, texte="Une demande"):
        code, sortie = self.outil("actions", entree={"type": "fonctionnalite", "texte": texte,
                                                     "t": "2026-11-10T10:00:00+01:00"})
        self.assertEqual(code, 0, sortie)
        return self.ok("etat")["fonctionnalites"][-1]["id"]

    def deux_workflows(self):
        self.reecrire(genre="badges", workflows=[
            {"id": "w-f1", "fonctionnalite": "f1", "genre": "badges",
             "flux": [etape("f1-dev"), etape("f1-controle", "Contrôle", "controleur")]},
            {"id": "w-f2", "fonctionnalite": "f2", "genre": "jeu-android",
             "flux": [etape("f2-dev"), etape("f2-controle", "Contrôle", "controleur"), etape("f2-livraison", "Livraison")]}])


class TestWorkflows(AvecWorkflows):
    def test_projet_sans_workflows_lu_comme_avant(self):
        self.reecrire(genre="badges")
        f = self.lire()
        ws = wf.tous(f)
        self.assertEqual(ws, [{"id": "principal", "fonctionnalite": None, "genre": "badges", "flux": PRINCIPAL}])
        self.assertEqual(wf.ids_etapes(f), ["dev", "relecture"])
        self.assertEqual(wf.colonnes(f, []), [
            {"id": "cadrage", "nom": "Cadrage"},
            {"id": "dev", "nom": "Développement", "genre": "badges", "workflow": "principal"},
            {"id": "relecture", "nom": "Relecture", "genre": "badges", "workflow": "principal"},
            {"id": "fait", "nom": "Fait", "terminee": True}])
        self.assertEqual(wf.genre_de(f, None), "badges")
        self.assertEqual(wf.genre_de(f, {"genre": None}), "badges")
        self.assertEqual(wf.de_la_fonctionnalite(f, {"workflow": None})["id"], "principal")

    def test_workflow_de_la_fonctionnalite(self):
        self.deux_workflows()
        f = self.lire()
        self.assertEqual([w["id"] for w in wf.tous(f)], ["principal", "w-f1", "w-f2"])
        f2 = {"id": "f2", "workflow": "w-f2", "genre": "jeu-android"}
        self.assertEqual(wf.de_la_fonctionnalite(f, f2)["id"], "w-f2")
        self.assertEqual(wf.genre_de(f, f2), "jeu-android")
        sans = {"id": "f3", "workflow": None, "genre": None}
        self.assertEqual(wf.de_la_fonctionnalite(f, sans)["id"], "principal")
        self.assertEqual(wf.de_la_fonctionnalite(f, {"workflow": "disparu"})["id"], "principal")
        self.assertEqual(wf.de_la_fonctionnalite(f, None)["id"], "principal")
        self.assertEqual(wf.ids_etapes(f), ["dev", "relecture", "f1-dev", "f1-controle", "f2-dev", "f2-controle",
                                            "f2-livraison"])

    def test_identifiant_en_double_entre_workflows_refuse(self):
        for workflows in (
                [{"id": "a", "flux": [etape("dev")]}],   # déjà pris par le flux du projet
                [{"id": "a", "flux": [etape("x")]}, {"id": "b", "flux": [etape("x")]}],
                [{"id": "a", "flux": [etape("x")]}, {"id": "a", "flux": [etape("y")]}],   # workflow en double
                [{"id": "principal", "flux": [etape("x")]}],   # identifiant réservé
                [{"id": "a", "flux": [etape("cadrage")]}], [{"id": "a", "flux": [etape("x", service="inconnu")]}],
                [{"id": "a", "genre": "Pas Valide", "flux": [etape("x")]}], [{"id": "a"}], ["a"]):
            self.reecrire(workflows=workflows)
            with self.assertRaises(fa.FactoryInvalide, msg=str(workflows)):
                self.lire()

    def test_projet_sans_flux_valide(self):
        self.reecrire(flux=[], description="Des badges pour une chaîne")
        f = self.lire()
        self.assertEqual(f["flux"], [])
        self.assertEqual(f["description"], "Des badges pour une chaîne")
        self.assertEqual(wf.tous(f), [])
        self.assertEqual(wf.colonnes(f, []), [{"id": "cadrage", "nom": "Cadrage"},
                                              {"id": "fait", "nom": "Fait", "terminee": True}])
        self.assertIsNone(wf.de_la_fonctionnalite(f, None))
        self.assertEqual(self.ok("releve")["colonnes"], wf.colonnes(f, []))
        self.reecrire(description="")
        with self.assertRaises(fa.FactoryInvalide):
            self.lire()

    def test_fonctionnalite_porte_genre_et_workflow(self):
        self.deux_workflows()
        i = self.nouvelle()
        f = self.ok("etat")["fonctionnalites"][-1]
        self.assertEqual((f["genre"], f["workflow"]), (None, None))   # pas encore classée
        self.ok("fonctionnalite", entree={"id": i, "genre": "jeu-android", "workflow": "w-f2"})
        f = self.ok("etat")["fonctionnalites"][-1]
        self.assertEqual((f["genre"], f["workflow"]), ("jeu-android", "w-f2"))
        r = self.ok("releve")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        self.ok("fonctionnalite", entree={"id": i, "genre": None, "workflow": None})
        f = self.ok("etat")["fonctionnalites"][-1]
        self.assertEqual((f["genre"], f["workflow"]), (None, None))
        for refus in ({"genre": "Pas Valide"}, {"genre": 3}, {"workflow": "inconnu"}, {"workflow": 3}):
            self.assertEqual(self.outil("fonctionnalite", entree={"id": i, **refus})[0], 1, refus)

    def test_etape_deplacee(self):
        i = self.nouvelle()
        self.ok("fonctionnalite", entree={"id": i, "etape": "deplacee", "deplacee_vers": "Casse-briques"})
        f = self.ok("etat")["fonctionnalites"][-1]
        self.assertEqual((f["etape"], f["deplacee_vers"]), ("deplacee", "Casse-briques"))
        r = self.ok("releve")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        self.assertEqual(r["fonctionnalites"][-1]["etape"], "deplacee")
        self.assertEqual(r["fonctionnalites"][-1]["deplacee_vers"], "Casse-briques")
        for refus in ({"deplacee_vers": ""}, {"deplacee_vers": 3}):
            self.assertEqual(self.outil("fonctionnalite", entree={"id": i, **refus})[0], 1, refus)


if __name__ == "__main__":
    unittest.main()
