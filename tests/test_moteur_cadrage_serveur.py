"""Le cadrage d'une fonctionnalité cherche son agent aux lieux du projet, dans leur ordre, comme tout départ.

Essai réel (FM_Stats, 2026-11-26, f26) : tous les agents du projet étaient au serveur ; le moteur ne cherchait l'agent de
cadrage qu'au poste, n'en trouvait aucun, réessayait sans fin et ne disait rien : la demande de l'utilisateur restait
bloquée à l'étape « cadrage ». La règle vaut pour tout projet, quel que soit le lieu de ses agents. Aucun appel réel.
"""
import json
from unittest import mock

from moteur import regles
from tests.test_moteur_polyvalents import Base


class CadrageAuServeur(Base):
    locaux, cloud = 1, 0

    def setUp(self):
        super().setUp()
        from orchestrateur import outil
        avant = outil.BUREAU_DEPORT      # aucun plafond d'abonnement : jamais le bureau réel
        outil.BUREAU_DEPORT = str(self.dossier / "absent" / "bureau.json")
        self.addCleanup(setattr, outil, "BUREAU_DEPORT", avant)
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "cadrage"})

    def serveur_seul(self):
        """Tous les agents du projet sont au serveur (un seul agent, une place serveur) : aucun agent au poste."""
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["agents_serveur_max"] = 1
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        self.agent("serveur-1", prenom="Ana", lieu="serveur")

    def fonc(self):
        return next(f for f in self.ok("etat")["fonctionnalites"] if f["id"] == "f1")

    def test_le_cadrage_prend_un_agent_du_serveur_quand_aucun_n_est_au_poste(self):
        self.serveur_seul()
        with mock.patch("orchestrateur.outil.serveur_hors_ligne", return_value=False):
            regles._repondre_cadrage(self.projet, regles.nouvel_etat(), "f1")
        self.assertEqual(self.fonc()["agent_cadrage"], "serveur-1")
        (cadrage,) = [t for t in self.ok("etat")["taches"] if t.get("etape") == "cadrage"]
        self.assertEqual(cadrage["agent"], "serveur-1")

    def test_un_projet_sans_serveur_cadre_toujours_au_poste(self):
        """Le choix d'avant, à l'identique : un projet sans place serveur cherche son agent au poste."""
        self.agent("local-1", prenom="Léa")
        regles._repondre_cadrage(self.projet, regles.nouvel_etat(), "f1")
        self.assertEqual(self.fonc()["agent_cadrage"], "local-1")

    def test_le_serveur_cadre_en_priorite_quand_le_projet_a_des_places_serveur(self):
        """L'ordre des lieux du projet (`depart.ordre_du_metier` : serveur, local, cloud, le serveur travaille en
        priorité) : le cadrage va au serveur même quand un agent du poste est libre, comme toute autre tâche."""
        self.serveur_seul()
        self.agent("local-1", prenom="Léa")
        with mock.patch("orchestrateur.outil.serveur_hors_ligne", return_value=False):
            regles._repondre_cadrage(self.projet, regles.nouvel_etat(), "f1")
        self.assertEqual(self.fonc()["agent_cadrage"], "serveur-1")

    def test_un_ordre_local_d_abord_est_respecte(self):
        """Un projet qui règle `ordre_lieux` avec le poste en premier garde son choix pour le cadrage aussi."""
        self.serveur_seul()
        self.agent("local-1", prenom="Léa")
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["ordre_lieux"] = ["local", "serveur"]
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        with mock.patch("orchestrateur.outil.serveur_hors_ligne", return_value=False):
            regles._repondre_cadrage(self.projet, regles.nouvel_etat(), "f1")
        self.assertEqual(self.fonc()["agent_cadrage"], "local-1")


class CadrageEpingleAUnAgentPris(Base):
    """Un cadrage épinglé à un agent polyvalent occupé ne l'attend pas : un autre agent libre le prend."""
    locaux, cloud = 2, 0

    def test_le_cadrage_d_un_agent_pris_part_chez_un_autre(self):
        from orchestrateur import outil
        avant = outil.BUREAU_DEPORT
        outil.BUREAU_DEPORT = str(self.dossier / "absent" / "bureau.json")
        self.addCleanup(setattr, outil, "BUREAU_DEPORT", avant)
        self.agent("local-1", prenom="Hugo")
        self.agent("local-2", prenom="Léa")
        occupe = self.tache("flux:dev", element="e9", titre="Autre")
        self.ok("tache", entree={"id": occupe, "agent": "local-1", "active": True})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "cadrage"})
        t = self.tache("cadrage", titre="Cadrage")
        self.ok("tache", entree={"id": t, "agent": "local-1", "colonne": "cadrage", "etape": "cadrage",
                                 "fonctionnalite": "f1", "active": False})
        self.demarrer(None)
        tache = next(x for x in self.ok("etat")["taches"] if x["id"] == t)
        self.assertEqual(tache["agent"], "local-2")


class SuiteDuPrototypeSansMethodePrete(Base):
    """Un prototype rendu sans « méthode prête » ni question n'arrête pas la série en silence (FM_Stats f27)."""
    locaux, cloud = 1, 0

    def setUp(self):
        super().setUp()
        self.agent("local-1", prenom="Hugo")
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "prototype"})
        self.t = {"id": "t1", "fonctionnalite": "f1", "etape": "prototype"}
        vrai = regles._fonc      # la fonctionnalité n'attend plus de réponse : le prototype est rendu
        patch = mock.patch.object(regles, "_fonc", side_effect=lambda p, i: dict(vrai(p, i), attend_reponse=False))
        patch.start()
        self.addCleanup(patch.stop)

    def test_sans_methode_prete_le_prototype_reprend(self):
        with mock.patch.object(regles, "_retoucher_prototype", return_value=["reprise"]) as r:
            self.assertEqual(regles._suite_prototype(self.projet, regles.nouvel_etat(), self.t, {}), ["reprise"])
        self.assertIn("Suite du prototype", r.call_args.args[3])

    def test_une_question_posee_n_est_pas_relancee(self):
        with mock.patch.object(regles, "_retoucher_prototype") as r:
            regles._suite_prototype(self.projet, regles.nouvel_etat(), self.t, {"message": {"attend": True}})
        r.assert_not_called()


class SerieEnAttenteDeLivraison(Base):
    """Une série dont les éléments attendent la livraison groupée n'est pas « arrêtée » (FM_Stats f28)."""
    locaux, cloud = 1, 0

    def test_pas_de_serie_arretee_quand_tout_attend_la_livraison(self):
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})
        etat = regles.nouvel_etat()
        regles._m(etat, "elements")["f1/e1"] = {"fid": "f1", "element": {"id": "e1", "nom": "Client"},
                                                "phase": regles.A_LIVRER, "taches": [], "pas": 0}
        with mock.patch.object(regles, "_en_attente_de_deploiement", return_value=False):
            regles._signaler_une_serie_muette(self.projet, etat, "f1")
        self.assertEqual([d for d in self.ok("etat")["decisions"] if d["genre"] == regles.SERIE_ARRETEE], [])

    def test_sans_element_pret_la_serie_muette_est_dite(self):
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})
        etat = regles.nouvel_etat()
        with mock.patch.object(regles, "_en_attente_de_deploiement", return_value=False):
            regles._signaler_une_serie_muette(self.projet, etat, "f1")
        self.assertEqual(len([d for d in self.ok("etat")["decisions"] if d["genre"] == regles.SERIE_ARRETEE]), 1)


class ImpasseEtOrganisationAttendue(Base):
    """Un cadrage qui attend la réponse à la proposition de workflow n'est pas une impasse (FM_Stats f29)."""
    locaux, cloud = 1, 0

    def test_la_proposition_de_workflow_attendue_n_est_pas_une_impasse(self):
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "cadrage"})
        court = {"taches": [], "fonctionnalites": [{"id": "f1", "etape": "cadrage", "attend_reponse": False}],
                 "decisions": [{"id": "d1", "genre": "organisation", "portee": "projet",
                                "organisation": {"fonctionnalite": "f1", "workflow": {}}}]}
        detail = {"maj": "2020-01-01T00:00:00+00:00", "decisions": [], "discussion": []}
        with mock.patch.object(regles, "_etat", return_value=court), \
                mock.patch.object(regles, "_fonc", return_value=detail):
            self.assertEqual(regles.impasses(self.projet, regles.nouvel_etat(), delai=0), [])
            court["decisions"] = []
            self.assertEqual(regles.impasses(self.projet, regles.nouvel_etat(), delai=0), [("f1", "cadrage")])
