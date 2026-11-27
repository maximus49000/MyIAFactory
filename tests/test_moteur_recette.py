"""Une recette qui déclare son échec ne clôt pas la tâche ni n'ouvre la livraison (essai réel FM_Stats, t237 : « Recette NON
réussie » acceptée avec le statut `fait`, la livraison était lancée)."""
import json
from unittest import mock

from moteur import agents, rapport, regles
from tests import test_moteur_regles as tmr
from tests import test_moteur_serie_reprise as tsr

_lu, usage = tmr._lu, tmr.usage


class Recette(tsr.AvecValidation):
    def setUp(self):
        super().setUp()
        self.projet_avec_validation(flux=tsr.FLUX, elements=0)
        self.recette = self.ok("tache", entree={"titre": "Recette du service", "fonctionnalite": "f1", "role": "testeur",
                                                "etape": "flux:essai", "colonne": "essai", "active": True})["id"]

    def rendre(self, **plus):
        self.etat["departs"][self.recette] = {"agent": "rel-1", "taches": [self.recette], "matiere": "", "lot": None}
        self.etat["en_cours"].add(self.recette)
        e = agents.Execution(self.recette, "rel-1", rapport=_lu({"statut": "fait", **plus}), usages=[usage()])
        regles.traiter_retour(self.projet, e, self.etat)

    def tache(self, tid):
        return next(t for t in self.suivi()["taches"] if t["id"] == tid)

    def corrections(self):
        return [t for t in self.suivi()["taches"] if t["titre"].startswith("Correction : ")]

    def test_recette_reussie_faux_rouvre_une_correction_sans_ouvrir_la_suite(self):
        self.rendre(recette_reussie=False, message={"texte": "Défauts constatés : /sante muet."})
        self.assertNotEqual(self.tache(self.recette)["colonne"], "fait")
        (corr,) = self.corrections()
        self.assertEqual((corr["role"], corr["etape"]), ("dev", "correction"))
        self.assertIn("/sante muet", json.dumps(corr["journal"], ensure_ascii=False))
        self.assertIn(corr["id"], self.tache(self.recette)["depend_de"])      # la recette attend la correction
        self.assertEqual([t for t in self.suivi()["taches"] if t["etape"] == "flux:livraison"], [])

    def test_sans_le_champ_le_texte_non_reussie_vaut_faux(self):
        self.rendre(message={"texte": "Recette NON réussie. Défauts constatés : page vide."})
        self.assertNotEqual(self.tache(self.recette)["colonne"], "fait")
        self.assertEqual(len(self.corrections()), 1)

    def test_le_champ_prime_sur_le_texte(self):
        self.rendre(recette_reussie=True, message={"texte": "La recette n'était pas réussie hier, mais tout passe."})
        self.assertEqual(self.corrections(), [])

    def test_recette_reussie_ou_champ_absent_sans_mot_d_echec_comme_avant(self):
        self.rendre(recette_reussie=True, message={"texte": "Tout passe."})
        self.assertEqual(self.corrections(), [])
        self.assertNotIn("Recette non réussie", json.dumps(self.tache(self.recette)["journal"], ensure_ascii=False))

    def test_champ_absent_sans_mot_d_echec(self):
        self.rendre(message={"texte": "Tout passe."})
        self.assertEqual(self.corrections(), [])
        self.assertNotIn("Recette non réussie", json.dumps(self.tache(self.recette)["journal"], ensure_ascii=False))

    def test_un_autre_metier_n_est_pas_concerne(self):
        autre = self.ok("tache", entree={"titre": "Dev", "fonctionnalite": "f1", "role": "dev", "etape": "flux:dev",
                                         "colonne": "dev", "active": True})["id"]
        self.etat["departs"][autre] = {"agent": "rel-1", "taches": [autre], "matiere": "", "lot": None}
        e = agents.Execution(autre, "rel-1", rapport=_lu({"statut": "fait", "recette_reussie": False,
                                                          "message": {"texte": "Recette non réussie."}}), usages=[usage()])
        regles.traiter_retour(self.projet, e, self.etat)
        self.assertEqual(self.corrections(), [])

    def test_trois_recettes_ratees_bloquent_la_tache(self):
        for _ in range(regles.RECETTES_RATEES_MAX):
            self.rendre(recette_reussie=False, message={"texte": "Défaut."})
        self.assertTrue(self.tache(self.recette).get("bloquee"))

    # --- Les échecs préexistants : une tâche dédiée chacun, jamais une correction de la fonctionnalité (FM_Stats a22).

    def dediees(self):
        return [t for t in self.suivi()["taches"] if t["titre"].startswith("Échec préexistant : ")]

    def test_un_echec_preexistant_ouvre_une_tache_dediee_et_la_recette_reussit(self):
        self.rendre(recette_reussie=True, echecs_preexistants=["serveur_url_edition_test"],
                    message={"texte": "Tout le périmètre passe ; un test échouait déjà sur la base."})
        (dediee,) = self.dediees()
        self.assertEqual(dediee["role"], "dev")
        self.assertIn("serveur_url_edition_test", json.dumps(dediee["journal"], ensure_ascii=False))
        self.assertIsNone(dediee.get("fonctionnalite"))                  # hors série : elle ne bloque rien
        self.assertEqual(self.corrections(), [])                          # aucune correction de la fonctionnalité
        self.assertNotIn("Recette non réussie", json.dumps(self.tache(self.recette)["journal"], ensure_ascii=False))
        self.assertTrue(any("tâche à part" in m["texte"] for m in self.suivi()["fonctionnalites"][0]["discussion"]
                            if m["auteur"] == "chef"))

    def test_une_seule_tache_par_test_pas_de_doublon(self):
        for _ in range(3):
            self.rendre(recette_reussie=True, echecs_preexistants=["serveur_url_edition_test"])
        self.assertEqual(len(self.dediees()), 1)

    def test_un_preexistant_ne_compte_pas_comme_un_echec_de_recette(self):
        for _ in range(regles.RECETTES_RATEES_MAX + 1):
            self.rendre(recette_reussie=True, echecs_preexistants=["t_a"])
        self.assertFalse(self.tache(self.recette).get("bloquee"))
        self.assertEqual(self.corrections(), [])

    def test_un_defaut_nouveau_avec_un_preexistant_rouvre_quand_meme_la_correction(self):
        self.rendre(recette_reussie=False, echecs_preexistants=["t_a"], message={"texte": "Défaut nouveau : page vide."})
        self.assertEqual(len(self.corrections()), 1)
        self.assertEqual(len(self.dediees()), 1)

    def test_le_contrat_ecarte_les_valeurs_mal_formees(self):
        self.assertNotIn("echecs_preexistants", _lu({"statut": "fait", "echecs_preexistants": "t_a"}))
        self.assertEqual(_lu({"statut": "fait", "echecs_preexistants": ["t_a", "", 3, " t_b "]})["echecs_preexistants"], ["t_a", "t_b"])

    def test_la_consigne_demande_de_rejouer_sur_la_base_et_de_classer(self):
        self.assertIn("echecs_preexistants", regles.CONSIGNE_RECETTE)
        self.assertIn("sur la base", regles.CONSIGNE_RECETTE)

    def test_le_contrat_ecarte_une_valeur_qui_n_est_pas_vrai_faux(self):
        self.assertNotIn("recette_reussie", _lu({"statut": "fait", "recette_reussie": "non"}))
        self.assertIs(_lu({"statut": "fait", "recette_reussie": False})["recette_reussie"], False)

    def test_la_consigne_du_testeur_demande_le_champ(self):
        self.assertIn("recette_reussie", regles.CONSIGNE_RECETTE)
        self.assertIn("recette_reussie", rapport.__doc__)

    def test_la_consigne_ne_traite_pas_une_verification_impossible_en_echec(self):
        """FM_Stats (2026-11-26) : « import réel absent du clone » rendu `recette_reussie: false` rouvrait une correction à
        chaque tour (le dev répondait « aucun code modifié »). Le non-vérifié est dit, il n'est pas un défaut."""
        c = regles.CONSIGNE_RECETTE
        self.assertIn("Non vérifié", c)
        self.assertIn("pas un défaut", c)
        self.assertIn("service en ligne", c)


if __name__ == "__main__":
    import unittest
    unittest.main()


class MotifDuRefus(tsr.AvecValidation):
    def setUp(self):
        super().setUp()
        self.projet_avec_validation(flux=tsr.FLUX, elements=0)
        self.etat = regles.nouvel_etat()

    def corriger(self, points, consigne="Agrandis le titre."):
        self.etat["elements"]["f1/e1"] = {"fid": "f1", "element": {"id": "e1", "nom": "Accueil"}, "taches": [],
                                          "phase": "relecture", "points": points}
        regles._apres_apres_refus(self.projet, {"suite": "corriger", "consigne": consigne, "raison": "r"},
                                  {"fonctionnalite": "f1", "element": "e1"}, self.etat)
        (corr,) = [t for t in self.suivi()["taches"] if t["titre"].startswith("Correction : ")]
        return json.dumps(corr["journal"], ensure_ascii=False)

    def test_la_correction_recoit_le_motif_du_refus_meme_si_la_consigne_l_oublie(self):
        journal = self.corriger(["Le titre fait 12 px", "Le bouton est coupé"])
        self.assertIn("Agrandis le titre.", journal)
        self.assertIn("Motif du refus : Le titre fait 12 px ; Le bouton est coupé", journal)

    def test_sans_point_pas_de_motif_inventé(self):
        self.assertNotIn("Motif du refus", self.corriger([]))

    def test_une_branche_citee_absente_est_dite_a_l_agent(self):
        with mock.patch.object(regles, "_avec_les_branches_verifiees", side_effect=lambda p, t: t + " [vérifiée]"):
            self.assertIn("[vérifiée]", self.corriger(["x"], consigne="Reprends agent/t289."))
