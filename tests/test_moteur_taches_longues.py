"""Claude autonome revoit les tâches d'agent ACTIVES depuis longtemps sans que rien ne bouge (FM_Stats t323 : une vérification
attendait un service dont l'index se construisait) : `conclure`, `recadrer`, `laisser`, `signaler`, jamais deux fois le même
retour, jamais une validation du Directeur."""
import time
import unittest
from unittest import mock

from moteur import jugement, regles
from tests import test_moteur_serie_reprise as tsr


class Longues(tsr.AvecValidation):
    def setUp(self):
        super().setUp()
        self.projet_avec_validation(flux=tsr.FLUX, elements=0)
        self.projet.claude_autonome = True
        self.etat = regles.nouvel_etat()
        self.tid = self.ok("tache", entree={"titre": "Vérification de l'index", "fonctionnalite": "f1", "role": "testeur",
                                            "etape": "flux:essai", "colonne": "essai", "active": True, "element": "e1"})["id"]
        self.etat["en_cours"].add(self.tid)

    def vieillir(self, minutes):
        """La tâche n'a pas bougé depuis `minutes` minutes : la revue est refaite maintenant."""
        v = self.etat["longues"][self.tid]
        v["depuis"] = time.time() - minutes * 60
        self.etat["longues_le"] = 0

    def revoir(self, minutes=20):
        regles._taches_longues(self.projet, self.etat)                 # première vue : la signature est notée
        self.vieillir(minutes)
        return regles._taches_longues(self.projet, self.etat)

    def appliquer(self, pseudo, **o):
        o = {"raison": "Elle attend un état qui n'arrive pas.", "verdict": "conclure", "texte": None, "generalisable": False,
             "lecon": None, "amelioration": None, **o}
        return regles.appliquer_jugement(self.projet, "decider_autonome", jugement.Decision(objet=o),
                                         {"decision": pseudo["id"], "tache": pseudo["tache"]}, self.etat)

    def paroles(self):
        return [m["texte"] for m in self.suivi()["fonctionnalites"][0]["discussion"] if m["auteur"] == "chef"]

    def test_une_verification_de_20_minutes_sans_changement_est_revue(self):
        (d,) = self.revoir(20)
        self.assertEqual((d["genre"], d["tache"]), ("tache_longue", self.tid))

    def test_avant_le_delai_rien(self):
        self.assertEqual(self.revoir(5), [])

    def test_un_autre_travail_attend_plus_longtemps(self):
        self.ok("tache", entree={"id": self.tid, "role": "dev"})
        self.assertEqual(self.revoir(20), [])
        self.vieillir(50)
        self.assertEqual(len(regles._taches_longues(self.projet, self.etat)), 1)

    def test_une_tache_qui_bouge_est_remise_a_zero(self):
        regles._taches_longues(self.projet, self.etat)
        self.vieillir(30)
        self.ok("tache", entree={"id": self.tid, "journal": ["Route 5 sur 9 contrôlée."]})     # le journal a changé
        self.assertEqual(regles._taches_longues(self.projet, self.etat), [])

    def test_une_validation_du_directeur_n_est_jamais_revue(self):
        self.ok("tache", entree={"id": self.tid, "etape": "validation:f1-validation"})
        self.assertEqual(regles._taches_longues(self.projet, self.etat), [])
        self.assertNotIn(self.tid, self.etat.get("longues", {}))

    def test_le_dossier_donne_les_corrections_en_cours_les_repetitions_et_les_faits_du_service(self):
        for _ in range(3):
            self.ok("tache", entree={"id": self.tid, "journal": ["/equipe/77 : 503 Index en préparation."]})
        self.ok("tache", entree={"titre": "Correction : index", "fonctionnalite": "f1", "role": "dev", "etape": "correction",
                                 "colonne": "dev", "active": False, "element": "e1"})
        (d,) = self.revoir(20)
        faits = {"commit": "ab", "pages": [{"chemin": "/equipe/77", "code": 503}]}
        with mock.patch.object(regles, "_adresse_du_service", return_value="https://service.exemple"), \
                mock.patch.object(regles.service_permanent, "faits_du_service", return_value=faits):
            dossier = regles._dossier_autonome(self.projet, self.etat, d)
        self.assertEqual(dossier["verdicts"], ["conclure", "recadrer", "laisser", "signaler"])
        self.assertEqual([x["etape"] for x in dossier["corrections_en_cours_sur_le_meme_element"]], ["correction"])
        self.assertEqual(dossier["lignes_repetees"], ["/equipe/77 : 503 Index en préparation."])
        self.assertEqual(dossier["faits_du_service"]["pages"][0]["code"], 503)
        self.assertEqual(dossier["minutes_active"], 20)

    def test_conclure_envoie_un_retour_le_dit_et_ne_se_repete_pas(self):
        (d,) = self.revoir(20)
        with mock.patch.object(regles, "_sur_retour", return_value=[]) as retour:
            self.appliquer(d, texte="Conclus maintenant : /sante vérifié ; /equipe/77 en non_verifie : service pas prêt.")
            regles.traiter_demande(self.projet, self.demande_en_attente()[-1], self.etat)
            retour.assert_called_once()
            self.assertIn("conclus maintenant", retour.call_args.args[1]["texte"].lower())
            self.assertTrue(any("conclure maintenant" in p for p in self.paroles()))
            self.assertIn((self.tid, "conclure"), self.etat["longues_envoyees"])
            with self.assertRaises(regles.Refus):                           # le même retour n'est jamais renvoyé
                regles._sur_tache_longue(self.projet, {"id": "r9", "tache": self.tid, "verdict": "conclure", "texte": "x"}, self.etat)

    def test_signaler_ne_envoie_rien_et_note_une_anomalie(self):
        (d,) = self.revoir(20)
        with mock.patch.object(regles, "_sur_retour") as retour:
            self.appliquer(d, verdict="signaler", texte="L'agent est muet depuis 20 minutes et rien ne l'explique.")
            regles.traiter_demande(self.projet, self.demande_en_attente()[-1], self.etat)
            retour.assert_not_called()
        (a,) = [x for x in self.ok("anomalies")["anomalies"] if x["titre"].startswith("Tâche longue")]
        self.assertIn("muet", a["description"])

    def test_laisser_n_envoie_rien(self):
        (d,) = self.revoir(20)
        with mock.patch.object(regles, "_sur_retour") as retour:
            self.appliquer(d, verdict="laisser")
            regles.traiter_demande(self.projet, self.demande_en_attente()[-1], self.etat)
            retour.assert_not_called()
        self.assertTrue(any("la laisse" in p or "je la laisse" in p for p in self.paroles()))

    def test_la_revue_ne_se_fait_que_sous_claude_autonome(self):
        self.revoir(20)
        self.projet.claude_autonome = False
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])

    def test_le_validateur_refuse_un_jeton_un_redeploiement_et_un_retour_vide(self):
        (d,) = self.revoir(20)
        ctx = {"decision": {"genre": "tache_longue"}, "verdicts": ["conclure", "recadrer", "laisser", "signaler"]}
        base = {"raison": "Elle attend.", "verdict": "conclure", "texte": "Conclus.", "generalisable": False,
                "lecon": None, "amelioration": None}
        self.assertIsNone(jugement.valider("decider_autonome", base, ctx))
        for mauvais in ({"texte": None}, {"texte": "Redéploie le service puis conclus."},
                        {"texte": "Utilise le jeton sk-abcdefgh12345678 pour conclure."}):
            self.assertIsNotNone(jugement.valider("decider_autonome", {**base, **mauvais}, ctx), mauvais)
        self.assertIsNone(jugement.valider("decider_autonome", {**base, "texte": "Conclus : aucune nouvelle correction, sans redéploiement."}, ctx))


if __name__ == "__main__":
    unittest.main()
