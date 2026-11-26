"""Claude autonome : les décisions du Directeur reçoivent une réponse automatique, sauf les validations."""
import unittest

from moteur import regles
from tests import test_moteur_regles as tmr
from tests import test_moteur_serie_reprise as tsr

ELEMENTS = tsr.ELEMENTS


class Reponses(unittest.TestCase):
    def test_un_accord_prend_le_premier_choix_les_premieres_reponses_ou_accepte(self):
        r = regles._reponse_autonome
        self.assertEqual(r({"id": "d1", "genre": "accord_agent", "choix": ["A", "B"]}),
                         {"type": "accord_agent", "verdict": "choisir", "choix": "A", "decision": "d1"})
        d = r({"id": "d2", "genre": "accord_agent", "questions": [{"texte": "?", "choix": ["x", "y"]}]})
        self.assertEqual((d["verdict"], d["reponses"]), ("repondre", [["x"]]))
        self.assertEqual(r({"id": "d3", "genre": "accord_agent"})["verdict"], "accepter")

    def test_outil_serie_et_blocage(self):
        r = regles._reponse_autonome
        self.assertEqual(r({"id": "d1", "genre": "outil_agent", "programme": "flutter"})["verdict"], "autoriser")
        self.assertEqual(r({"id": "d1", "genre": "outil_agent"})["verdict"], "relancer")
        self.assertEqual(r({"id": "d2", "genre": "serie_arretee"})["verdict"], "relancer")
        self.assertEqual(r({"id": "d3", "genre": "blocage_analyse", "recommandation": "Refais"})["verdict"], "suivre")
        self.assertIsNone(r({"id": "d3", "genre": "blocage_analyse", "recommandation": ""}))

    def test_jamais_une_validation_ni_une_decision_qui_depense(self):
        for genre in ("valider_etape", "valider_methode", "fable_tache", "decoupage_lieux", "environnement"):
            self.assertIsNone(regles._reponse_autonome({"id": "d1", "genre": genre}), genre)


class Boucle(tsr.AvecValidation):
    def setUp(self):
        super().setUp()
        self.projet_avec_validation(flux=tsr.FLUX, elements=0)

    prendre, tache, serie_arretee = (tsr.Reprise.__dict__[n] for n in ("prendre", "tache", "serie_arretee"))

    def decision_serie(self):
        self.ok("file", entree={"fonctionnalite": "f1", "elements": ELEMENTS[:2]})
        self.prendre("e1", "e2")
        self.tache("e1", "flux:ancienne", journal="Fait.", colonne="dev")
        self.tache("e2", "prototype")
        self.etat = regles.nouvel_etat()
        regles.avancer(self.projet, self.etat)
        (d,) = self.serie_arretee()
        return d

    def test_desactive_rien_n_est_repondu(self):
        self.decision_serie()
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), 0)
        self.assertEqual(len(self.serie_arretee()), 1)

    def test_active_la_serie_est_relancee_et_journalisee(self):
        d = self.decision_serie()
        self.projet.claude_autonome = True
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), 1)
        (demande,) = [x for x in self.demande_en_attente() if x["type"] == "serie_arretee"]
        self.assertEqual((demande["decision"], demande["verdict"], demande["claude_autonome"]), (d["id"], "relancer", True))
        regles.traiter_demande(self.projet, demande, self.etat)
        self.assertEqual(self.serie_arretee(), [])
        (l,) = self.suivi()["lecons"]       # le déblocage est retenu
        self.assertIn("série", l["texte"])
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), 0)      # une seule tentative par décision

    def test_une_serie_qui_se_rebloque_revient_au_directeur_apres_trois_reponses(self):
        self.decision_serie()
        self.projet.claude_autonome = True
        self.etat["autonome_reprises"] = {("serie_arretee", "f1"): regles.AUTONOME_MAX_REPRISES}
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), 0)
        self.assertEqual(len(self.serie_arretee()), 1)


class Memoire(tmr.Arrets):
    """Chaque déblocage devient une leçon validée, notée une seule fois."""

    def lecons(self):
        return self.suivi()["lecons"]

    def test_un_accord_donne_en_autonome_laisse_une_lecon_validee_une_seule_fois(self):
        self.piloter(self.depart_cadrage(), rapports=[self.ACCORD])
        self.projet.claude_autonome = True
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), 1)
        (l,) = self.lecons()
        self.assertIn("Générer 5 images", l["texte"])
        self.assertEqual(l["etat"], "validée")
        self.assertEqual(self.lecons()[0]["tache"], self.taches(etape="cadrage")[0]["id"])
        regles._noter_le_deblocage(self.projet, self.etat, self.decisions_accord()[0])      # même cause : pas de doublon
        self.assertEqual(len(self.lecons()), 1)

    def test_rien_n_est_retenu_quand_l_option_est_decochee(self):
        self.piloter(self.depart_cadrage(), rapports=[self.ACCORD])
        regles.repondre_en_autonome(self.projet, self.etat)
        self.assertEqual(self.lecons(), [])


class Textes(unittest.TestCase):
    def test_la_lecon_dit_la_cause_et_la_conduite(self):
        f = regles._lecon_du_deblocage
        self.assertIn("flutter", f({"genre": "outil_agent", "programme": "flutter"}))
        self.assertIn("recommandation du Chef", f({"genre": "blocage_analyse", "motif": "echec", "recommandation": "Refais."}))
        self.assertIn("série", f({"genre": "serie_arretee", "texte": "La série ne progresse plus."}))
        self.assertIsNone(f({"genre": "valider_etape", "texte": "x"}))


if __name__ == "__main__":
    unittest.main()
