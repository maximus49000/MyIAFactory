"""Claude autonome : Claude réfléchit aux décisions du Directeur (jamais aux validations), le moteur en tire des leçons,
des améliorations et des réponses qu'il donnera seul ensuite."""
import json
import unittest

from moteur import jugement, regles
from tests import test_moteur_regles as tmr
from tests import test_moteur_serie_reprise as tsr

ELEMENTS = tsr.ELEMENTS


def objet(**champs):
    return {"raison": "Débloque la tâche sans sortir de la demande.", "verdict": "accepter", "texte": None,
            "generalisable": False, "lecon": None, "amelioration": None, **champs}


class Reponses(unittest.TestCase):
    """La réponse mécanique de repli."""

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
            self.assertNotIn(genre, regles.VERDICTS_AUTONOMES)


class Validation(unittest.TestCase):
    D = {"verdicts": ["accepter", "choisir", "repondre", "refuser"], "choix": ["A", "B"],
         "questions": [{"texte": "?", "choix": ["x", "y"]}], "mots_interdits": ["Secret"]}

    def erreur(self, **champs):
        return jugement.valider("decider_autonome", objet(**champs), self.D)

    def test_une_reponse_valable(self):
        self.assertIsNone(self.erreur())
        self.assertIsNone(self.erreur(verdict="choisir", choix="B"))
        self.assertIsNone(self.erreur(verdict="repondre", reponses=[["y"]]))
        self.assertIsNone(self.erreur(lecon={"portee": "metier", "texte": "Demande l'outil avant."},
                                      amelioration={"titre": "Ouvrir flutter d'office", "description": "Le profil."}))

    def test_refus_des_reponses_inventees(self):
        self.assertIn("verdict", self.erreur(verdict="valider"))
        self.assertIn("choix", self.erreur(verdict="choisir", choix="Z"))
        self.assertIn("reponses", self.erreur(verdict="repondre", reponses=[["z"]]))
        self.assertIn("texte", self.erreur(verdict="refuser"))
        self.assertIn("Fable", self.erreur(texte="Passe sur Fable."))
        self.assertIn("raison", self.erreur(raison=""))
        self.assertIn("généraux", self.erreur(lecon={"portee": "genre", "texte": "Le Secret du projet."}))
        self.assertIn("generalisable", self.erreur(generalisable="oui"))


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

    def appliquer(self, action, o=None, question=None):
        _, type_, _, suite = action
        decision = jugement.Decision(question=question) if question else jugement.Decision(objet=o)
        return regles.appliquer_jugement(self.projet, type_, decision, suite, self.etat)

    def test_desactive_rien_n_est_fait(self):
        self.decision_serie()
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])

    def test_active_claude_recoit_un_dossier_sur_la_decision_et_les_etapes_de_validation(self):
        d = self.decision_serie()
        self.projet.claude_autonome = True
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        _, type_, dossier, suite = action
        self.assertEqual((type_, suite["decision"]), ("decider_autonome", d["id"]))
        self.assertEqual(dossier["decision"]["genre"], "serie_arretee")
        self.assertEqual(dossier["verdicts"], ["relancer"])
        self.assertTrue(any(x["validation"] for x in dossier["fonctionnalite"]["flux"]))       # le but : la validation
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])        # une seule tentative

    def test_la_reponse_reflechie_est_deposee_avec_sa_raison_sa_lecon_et_son_amelioration(self):
        d = self.decision_serie()
        self.projet.claude_autonome = True
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.appliquer(action, objet(verdict="relancer", raison="Une étape retirée du flux bloquait la série.",
                                     lecon={"portee": "metier", "texte": "Garde des étapes du workflow actuel."},
                                     amelioration={"titre": "Étape retirée", "description": "Migrer les tâches."}))
        (demande,) = [x for x in self.demande_en_attente() if x["type"] == "serie_arretee"]
        self.assertEqual((demande["decision"], demande["verdict"], demande["claude_autonome"]), (d["id"], "relancer", True))
        self.assertIn("étape retirée", demande["raison"])
        regles.traiter_demande(self.projet, demande, self.etat)
        self.assertEqual(self.serie_arretee(), [])
        (lecon,) = self.suivi()["lecons"]
        self.assertEqual((lecon["texte"], lecon["etat"]), ("Garde des étapes du workflow actuel.", "validée"))
        titres = [a["titre"] for a in self.ok("anomalies")["anomalies"]]
        self.assertEqual(titres, ["Amélioration : Étape retirée"])

    def test_si_claude_ne_peut_pas_reflechir_la_reponse_mecanique_debloque_quand_meme(self):
        self.decision_serie()
        self.projet.claude_autonome = True
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.appliquer(action, question="Deux essais sans réponse utilisable.")
        (demande,) = [x for x in self.demande_en_attente() if x["type"] == "serie_arretee"]
        self.assertEqual(demande["verdict"], "relancer")
        self.assertIn("pas pu réfléchir", demande["raison"])
        self.assertEqual(len(self.suivi()["lecons"]), 1)      # la leçon mécanique

    def test_une_serie_qui_se_rebloque_revient_au_directeur_apres_trois_reponses(self):
        self.decision_serie()
        self.projet.claude_autonome = True
        self.etat["autonome_reprises"] = {("serie_arretee", "f1"): regles.AUTONOME_MAX_REPRISES}
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])
        self.assertEqual(len(self.serie_arretee()), 1)


class Apprentissage(tmr.Arrets):
    """Une réponse généralisable est apprise : la fois d'après, le moteur répond seul, sans appel à Claude."""

    def appliquer(self, action, o):
        _, type_, _, suite = action
        return regles.appliquer_jugement(self.projet, type_, jugement.Decision(objet=o), suite, self.etat)

    def ouvrir_un_accord(self):
        self.piloter(self.depart_cadrage(), rapports=[self.ACCORD])
        self.projet.claude_autonome = True
        return self.decisions_accord()[0]

    def test_claude_accepte_puis_le_moteur_repond_seul(self):
        d = self.ouvrir_un_accord()
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.assertEqual(action[2]["decision"]["quoi"], "Générer 5 images")
        self.appliquer(action, objet(generalisable=True, lecon={"portee": "metier", "texte": "Génère sans demander."}))
        fichier = regles._fichier_appris(self.projet)
        appris = json.loads(fichier.read_text(encoding="utf-8"))
        self.assertEqual(list(appris), ["accord_agent|générer 5 images"])
        # même demande plus tard : aucun jugement, la réponse apprise est déposée et comptée
        self.etat["autonome_faites"].discard(d["id"])
        self.etat["autonome_reprises"].clear()
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])
        reponses = [x for x in self.demande_en_attente() if x["type"] == "accord_agent"]
        self.assertTrue(any(x["raison"].startswith("Réponse apprise") for x in reponses))
        self.assertEqual(json.loads(fichier.read_text(encoding="utf-8"))["accord_agent|générer 5 images"]["emplois"], 1)

    def test_une_reponse_non_generalisable_n_est_pas_apprise(self):
        self.ouvrir_un_accord()
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.appliquer(action, objet(generalisable=False))
        self.assertFalse(regles._fichier_appris(self.projet).exists())

    def test_la_decision_levee_pendant_la_reflexion_ne_fait_rien(self):
        d = self.ouvrir_un_accord()
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.traiter(type="accord_agent", decision=d["id"], verdict="accepter")      # le Directeur a répondu
        self.assertEqual(self.appliquer(action, objet()), [])


if __name__ == "__main__":
    unittest.main()
