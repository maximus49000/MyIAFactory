"""Un genre et un workflow par fonctionnalité : les données (factory, suivi) et leur lecture par le relevé."""
import json
import tempfile
import unittest
from pathlib import Path

from bureau import releve
from orchestrateur import factory as fa
from orchestrateur import memoire
from orchestrateur import workflows as wf
from tests.orch_aide import AvecProjet, factory_minimale
from tests.test_orch_memoire import AvecDepots

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


class TestRelevePourChaqueFonctionnalite(AvecWorkflows):
    def deux_fonctionnalites(self):
        self.deux_workflows()
        f1, f2 = self.nouvelle("Des badges"), self.nouvelle("Un casse-briques")
        self.ok("fonctionnalite", entree={"id": f1, "genre": "badges", "workflow": "w-f1"})
        self.ok("fonctionnalite", entree={"id": f2, "genre": "jeu-android", "workflow": "w-f2"})
        return f1, f2

    def test_releve_inchange_sans_workflows(self):
        r = self.ok("releve")
        self.assertEqual(r["colonnes"], [{"id": "cadrage", "nom": "Cadrage"}, {"id": "dev", "nom": "Développement"},
                                         {"id": "relecture", "nom": "Relecture"},
                                         {"id": "fait", "nom": "Fait", "terminee": True}])
        t = self.ok("tache", entree={"titre": "Une tâche"})
        self.assertEqual(self.ok("detail", entree={"tache": t["id"]})["colonne"], "dev")
        self.assertEqual(releve.valider(self.ok("releve")), [])
        # Avec un genre au projet, chaque colonne le dit ; l'identifiant du workflow, lui, n'apparaît pas.
        self.reecrire(genre="badges")
        self.assertEqual(self.ok("releve")["colonnes"][1], {"id": "dev", "nom": "Développement", "genre": "badges"})

    def test_deux_controles_deux_colonnes(self):
        f1, f2 = self.deux_fonctionnalites()
        r = self.ok("releve")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        self.assertEqual([c["id"] for c in r["colonnes"]],
                         ["cadrage", "dev", "relecture", "f1-dev", "f1-controle", "f2-dev", "f2-controle",
                          "f2-livraison", "fait"])
        par_id = {c["id"]: c for c in r["colonnes"]}
        self.assertEqual((par_id["f1-controle"]["genre"], par_id["f1-controle"]["workflow"]), ("badges", "w-f1"))
        self.assertEqual((par_id["f2-controle"]["genre"], par_id["f2-controle"]["workflow"]), ("jeu-android", "w-f2"))
        self.assertEqual(par_id["f1-controle"]["nom"], par_id["f2-controle"]["nom"])   # même nom, deux colonnes
        fonc = {x["id"]: x for x in r["fonctionnalites"]}
        self.assertEqual((fonc[f2]["genre"], fonc[f2]["workflow"]), ("jeu-android", "w-f2"))
        self.assertEqual([x["id"] for x in fonc[f2]["workflow_etapes"]], ["f2-dev", "f2-controle", "f2-livraison"])
        t1 = self.ok("tache", entree={"titre": "Badge", "fonctionnalite": f1})
        t2 = self.ok("tache", entree={"titre": "Niveau", "fonctionnalite": f2})
        t3 = self.ok("tache", entree={"titre": "Hors fonctionnalité"})
        colonnes = {t["id"]: t["colonne"] for t in self.ok("releve")["taches"]}
        self.assertEqual((colonnes[t1["id"]], colonnes[t2["id"]], colonnes[t3["id"]]), ("f1-dev", "f2-dev", "dev"))
        self.ok("tache", entree={"id": t2["id"], "colonne": "f2-controle"})   # une colonne de n'importe quel workflow
        self.assertEqual(self.outil("tache", entree={"id": t2["id"], "colonne": "f9-controle"})[0], 1)

    def test_colonnes_d_une_fonctionnalite_finie_cachees(self):
        f1, f2 = self.deux_fonctionnalites()
        t = self.ok("tache", entree={"titre": "Niveau", "fonctionnalite": f2, "active": True})
        for etape in ("terminee", "deplacee"):
            self.ok("fonctionnalite", entree={"id": f2, "etape": etape})
            r = self.ok("releve")
            self.assertEqual(releve.valider(r), [], releve.valider(r))
            self.assertEqual([c["id"] for c in r["colonnes"]],
                             ["cadrage", "dev", "relecture", "f1-dev", "f1-controle", "fait"], etape)
            # sa tâche ne reste pas dans une colonne qui n'existe plus
            self.assertEqual(next(x for x in r["taches"] if x["id"] == t["id"])["colonne"], "fait")
            self.ok("fonctionnalite", entree={"id": f2, "etape": "serie"})
        r = self.ok("releve")
        self.assertIn("f2-controle", [c["id"] for c in r["colonnes"]])
        self.ok("tache", entree={"id": t["id"], "colonne": "f2-livraison"})
        self.ok("fonctionnalite", entree={"id": f2, "etape": "terminee"})
        self.ok("fonctionnalite", entree={"id": f1, "etape": "terminee"})
        # le workflow principal reste toujours là
        self.assertEqual([c["id"] for c in self.ok("releve")["colonnes"]], ["cadrage", "dev", "relecture", "fait"])

    def test_deplacee_ne_reclame_plus_le_directeur(self):
        from datetime import datetime, timezone
        from bureau import equipe, etat
        i = self.nouvelle()
        self.ok("decision", entree={"action": "poser", "portee": i, "genre": "valider_cahier", "texte": "Cahier prêt"})
        eq = equipe.Equipe(self.dossier / "equipe.json")
        maintenant = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

        def a_traiter():
            return etat.construire(releve.normaliser(self.ok("releve")), eq, maintenant, 30)["directeur"]["fonctionnalites"]
        self.assertEqual(a_traiter(), 1)
        self.ok("fonctionnalite", entree={"id": i, "etape": "deplacee", "deplacee_vers": "Autre projet"})
        self.assertEqual(a_traiter(), 0)


class TestParFonctionnaliteMemoire(AvecDepots, AvecWorkflows):
    """Le départ, les leçons et l'usage suivent le genre de la fonctionnalité de la tâche."""

    def setUp(self):
        AvecDepots.setUp(self)
        self._t2 = tempfile.TemporaryDirectory()
        self.addCleanup(self._t2.cleanup)
        self.dossier = Path(self._t2.name)
        self.factory = factory_minimale(self.dossier, memoire=str(self.ma), genre="vitrine", workflows=[
            {"id": "w-f2", "fonctionnalite": "f2", "genre": "jeu-web", "flux": [etape("f2-dev")]}])
        self.f1, self.f2 = self.nouvelle("Un site"), self.nouvelle("Un jeu")
        self.ok("fonctionnalite", entree={"id": self.f2, "genre": "jeu-web", "workflow": "w-f2"})
        self.t_site = self.ok("tache", entree={"titre": "Page", "fonctionnalite": self.f1, "role": "dev"})["id"]
        self.t_jeu = self.ok("tache", entree={"titre": "Boucle", "fonctionnalite": self.f2, "role": "dev"})["id"]
        self.t_libre = self.ok("tache", entree={"titre": "Libre", "role": "dev"})["id"]

    def message(self, tache):
        return self.ok("depart", entree={"agent": "dev-1", "tache": tache})["message"]

    def test_depart_donne_les_lecons_du_genre_de_la_fonctionnalite(self):
        jeu = self.message(self.t_jeu)
        self.assertIn("Séparer la boucle de jeu du dessin", jeu)
        self.assertNotIn("textes d'accueil courts", jeu)
        self.assertIn("(genre : jeu-web)", jeu)
        for tache in (self.t_site, self.t_libre):   # sans genre de fonctionnalité : le genre du projet
            site = self.message(tache)
            self.assertIn("textes d'accueil courts", site)
            self.assertNotIn("boucle de jeu", site)
            self.assertIn("(genre : vitrine)", site)
        # un lot mêlant les deux : les leçons des deux genres, une fois chacune
        lot = self.ok("depart", entree={"agent": "dev-1", "taches": [self.t_site, self.t_jeu]})["message"]
        self.assertEqual(lot.count("textes d'accueil courts"), 1)
        self.assertEqual(lot.count("Séparer la boucle de jeu"), 1)
        seul = self.ok("depart", entree={"agent": "dev-1", "taches": [self.t_jeu]})["message"]
        self.assertNotIn("textes d'accueil courts", seul)

    def noter(self, tache):
        return self.ok("lecon", entree={"action": "noter", "agent": "dev-1", "texte": "Relancer les tests.",
                                        "etage_propose": "genre", "texte_general": "Toujours relancer les tests.",
                                        "roles": ["dev"], "tache": tache})["id"]

    def test_lecon_de_genre_va_au_genre_de_sa_fonctionnalite(self):
        self.ok("lecon", entree={"action": "appliquer", "id": self.noter(self.t_jeu), "verdict": "valider"})
        textes = lambda genre: [x["texte"] for x in memoire.lire(self.ma, genre, "dev")["genre"]]
        self.assertIn("Toujours relancer les tests.", textes("jeu-web"))
        self.assertNotIn("Toujours relancer les tests.", textes("vitrine"))
        self.ok("lecon", entree={"action": "appliquer", "id": self.noter(self.t_libre), "verdict": "valider"})
        self.assertIn("Toujours relancer les tests.", textes("vitrine"))   # sans fonctionnalité : le genre du projet

    def test_usage_porte_le_genre(self):
        mesure = {"agent": "dev-1", "modele": "Sonnet", "entree": 100, "sortie": 20}
        u_jeu = self.ok("usage", entree={**mesure, "tache": self.t_jeu})["id"]
        u_site = self.ok("usage", entree={**mesure, "tache": self.t_site})["id"]
        u_libre = self.ok("usage", entree={**mesure, "tache": self.t_libre})["id"]
        u_sans = self.ok("usage", entree={**mesure})["id"]
        self.ok("usage", entree={**mesure, "id": u_jeu, "tache": self.t_jeu, "entree": 200})   # un cumul garde son genre
        r = self.ok("releve")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        genres = {u["id"]: u.get("genre_fonctionnalite") for u in r["usage"]}
        self.assertEqual(genres, {u_jeu: "jeu-web", u_site: "vitrine", u_libre: "vitrine", u_sans: "vitrine"})
        # le champ « genre » d'un usage reste réservé aux partenaires
        self.assertTrue(all("genre" not in u for u in r["usage"]))


class TestFonctionnaliteDeplacee(unittest.TestCase):
    def test_deplacee_ni_livree_ni_comptee(self):
        from bureau import cout, kpi
        from datetime import datetime, timezone
        maintenant = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
        t = "2026-11-10T10:00:00+00:00"
        r = {"version": 4, "projet": "P", "factory": {"etat": "en marche"},
             "services": [{"id": "dev", "nom": "Dev"}],
             "colonnes": [{"id": "a", "nom": "A"}, {"id": "f", "nom": "Fait", "terminee": True}],
             "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"}],
             "taches": [{"id": "t1", "titre": "Gardée", "colonne": "f", "active": False, "titulaire": "d1", "maj": t,
                         "fonctionnalite": "f1"},
                        {"id": "t2", "titre": "Partie", "colonne": "f", "active": False, "titulaire": "d1", "maj": t,
                         "fonctionnalite": "f2"}],
             "fonctionnalites": [{"id": "f1", "nom": "Une", "etape": "serie"},
                                 {"id": "f2", "nom": "Deux", "etape": "deplacee", "deplacee_vers": "Autre projet"}]}
        propres = kpi.calcules(r, None, "aujourdhui", maintenant)["dev"]
        self.assertEqual(next(k for k in propres if k["id"] == "taches_terminees")["valeur"], 1)
        us = [{"id": "u1", "tache": "t1", "modele": "sonnet", "entree": 1000, "sortie": 0, "t": t, "t_prix": t},
              {"id": "u2", "tache": "t2", "modele": "sonnet", "entree": 1000, "sortie": 0, "t": t, "t_prix": t}]
        prix = lambda m, d: ({"entree": 3.0, "sortie": 15.0, "cache_lecture": 0.3, "cache_ecriture": 3.75}, "2026-11-01", False)
        self.assertEqual(cout.couts_fonctionnalite(us, prix, r, "f2")["taches"], [])
        self.assertEqual(cout.couts_fonctionnalite(us, prix, r, "f2")["total"], 0)
        self.assertEqual([x["id"] for x in cout.couts_fonctionnalite(us, prix, r, "f1")["taches"]], ["t1"])


if __name__ == "__main__":
    unittest.main()
