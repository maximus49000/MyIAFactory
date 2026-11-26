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
