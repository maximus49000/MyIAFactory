import unittest
from datetime import datetime, timedelta, timezone

from bureau import avancement

MAINTENANT = datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc)
DELAI = 2400


def il_y_a(secondes):
    return (MAINTENANT - timedelta(seconds=secondes)).isoformat()


def travail(action_s=20, vie_s=20, depuis_s=600, action="lance py", **plus):
    return {"depuis": il_y_a(depuis_s), "agent": "dev", "action": action,
            "action_t": il_y_a(action_s) if action else None, "vie_t": il_y_a(vie_s), "phase": "tests",
            "avancement": None, **plus}


def tache(**plus):
    return {"id": "t1", "etape": "correction", "debut": il_y_a(900), "active": True, **plus}


def historique(*durees):
    """Les exécutions réelles d'agents (durées notées par le moteur) de tâches de l'étape « correction »."""
    return [{"tache": f"h{i}", "duree_s": d} for i, d in enumerate(durees)]


TACHES_PASSEES = [{"id": f"h{i}", "etape": "correction"} for i in range(8)]


def calculer(t, histo=(), moteur_vivant=True, delai=DELAI):
    return avancement.pour_la_tache(t, TACHES_PASSEES, list(histo), moteur_vivant, MAINTENANT, delai)


class Etats(unittest.TestCase):
    def test_avance(self):
        r = calculer(tache(travail=travail(action_s=20)))
        self.assertEqual((r["etat"], r["etat_texte"]), ("avance", "avance"))
        self.assertEqual(r["passe_s"], 600)
        self.assertEqual(r["cumul_s"], 900)

    def test_commande_longue(self):
        r = calculer(tache(travail=travail(action_s=300, vie_s=10)))
        self.assertEqual(r["etat"], "commande_longue")
        self.assertIn("commande longue en cours depuis 5 min", r["etat_texte"])

    def test_sans_action(self):
        r = calculer(tache(travail=travail(action_s=720, vie_s=720)))
        self.assertEqual(r["etat"], "sans_action")
        self.assertIn("sans action depuis 12 min", r["etat_texte"])
        self.assertIn("arrêt automatique à 40 min", r["etat_texte"])

    def test_termine_non_lu_apres_deux_minutes(self):
        r = calculer(tache(agent_termine={"t": il_y_a(180)}))
        self.assertEqual(r["etat"], "termine_non_lu")
        self.assertIn("résultat en attente de lecture depuis 3 min", r["etat_texte"])
        self.assertIsNone(calculer(tache(agent_termine={"t": il_y_a(60)})))      # trop tôt pour le dire

    def test_moteur_arrete(self):
        r = calculer(tache(travail=travail()), moteur_vivant=False)
        self.assertEqual(r["etat"], "moteur_arrete")
        self.assertIn("moteur arrêté", r["etat_texte"])
        self.assertEqual(calculer(tache(travail=travail()), moteur_vivant=None)["etat"], "avance")

    def test_demarre_sans_flux(self):
        r = calculer(tache(travail=travail(action=None, depuis_s=30)))
        self.assertEqual(r["etat"], "demarre")

    def test_rien_sans_agent(self):
        self.assertIsNone(calculer(tache()))

    def test_demarre_trop_longtemps_est_dit_sans_action(self):
        r = calculer(tache(travail=travail(action=None, depuis_s=39 * 60)))
        self.assertEqual(r["etat"], "sans_action")
        self.assertIn("sans action depuis 39 min", r["etat_texte"])

    def test_commande_longue_rappelle_l_arret_automatique(self):
        r = calculer(tache(travail=travail(action_s=38 * 60, vie_s=10)))
        self.assertEqual(r["etat"], "commande_longue")
        self.assertIn("arrêt automatique à 40 min", r["etat_texte"])

    def test_les_temps_sont_a_la_minute_pour_ne_pas_redessiner_toutes_les_2_s(self):
        r = calculer(tache(travail=travail(depuis_s=601)), historique(600, 600, 900, 1200, 1200))
        self.assertEqual(r["passe_s"] % 60, 0)
        self.assertEqual(r["cumul_s"] % 60, 0)
        self.assertEqual(r["reste"]["min_s"] % 60, 0)
        self.assertEqual(r["reste"]["max_s"] % 60, 0)

    def test_liste_non_mise_a_jour(self):
        av = {"points": [{"texte": "a", "fait": False}], "en_cours": "a", "maj": il_y_a(600)}
        r = calculer(tache(travail=travail(action_s=20, avancement=av)))
        self.assertIn("liste non mise à jour depuis 10 min", r["etat_texte"])
        self.assertEqual(r["points"], av["points"])
        self.assertEqual(r["en_cours"], "a")


class AttenteDeportee(unittest.TestCase):
    """L'agent attend une exécution distante (fichier de `deporter`) : une attente, pas un blocage."""

    def attente(self, depuis_min=12, **plus):
        return {"action": "apk", "attend": "apk", "lieu": "github", "depuis": il_y_a(depuis_min * 60), **plus}

    def test_la_fiche_dit_ce_qui_est_attendu_et_d_ou(self):
        # aucune action depuis 45 min : sans l'attente, ce serait « sans action »
        r = calculer(tache(travail=travail(action_s=2700, vie_s=2700, attente_deportee=self.attente(12))))
        self.assertEqual(r["etat"], "attente_deportee")
        self.assertIn("en attente de l'APK (GitHub, depuis 12 min)", r["etat_texte"])
        self.assertIn("durée habituelle inconnue", r["etat_texte"])

    def test_noms_inconnus_dits_tels_quels(self):
        r = calculer(tache(travail=travail(attente_deportee=self.attente(3, attend="ipa", lieu="gitlab"))))
        self.assertIn("en attente de ipa (gitlab, depuis 3 min)", r["etat_texte"])

    def test_apres_le_seuil_c_est_une_alerte(self):
        r = calculer(tache(travail=travail(attente_deportee=self.attente(35))))
        self.assertEqual(r["etat"], "attente_longue")
        self.assertIn("attente anormalement longue (35 min)", r["etat_texte"])

    def test_le_seuil_se_regle(self):
        t = tache(travail=travail(attente_deportee=self.attente(12)))
        r = avancement.pour_la_tache(t, TACHES_PASSEES, [], True, MAINTENANT, DELAI, attente_longue_s=600)
        self.assertEqual(r["etat"], "attente_longue")

    def test_sans_attente_les_autres_etats_ne_changent_pas(self):
        for plus, etat in (({}, "avance"), ({"action_s": 3000, "vie_s": 3000}, "sans_action"),
                           ({"action_s": 600, "vie_s": 10}, "commande_longue")):
            self.assertEqual(calculer(tache(travail=travail(attente_deportee=None, **plus)))["etat"], etat)

    def test_moteur_arrete_prime(self):
        r = calculer(tache(travail=travail(attente_deportee=self.attente())), moteur_vivant=False)
        self.assertEqual(r["etat"], "moteur_arrete")


class Fourchette(unittest.TestCase):
    def test_inconnue_sous_trois_durees(self):
        self.assertIsNone(avancement.fourchette([600, 900]))
        r = calculer(tache(travail=travail()), historique(600, 900))
        self.assertIsNone(r["reste"])
        self.assertEqual(r["reste_texte"], "inconnu")

    def test_ecarte_les_durees_aberrantes_et_les_autres_etapes(self):
        taches = TACHES_PASSEES + [{"id": "x", "etape": "flux:f1"}]
        execs = historique(0, 600, 600, 900, 1200, 1200, 3 * 86400) + [{"tache": "x", "duree_s": 700}]
        self.assertEqual(sorted(avancement.durees_de_l_etape(taches, execs, "correction")),
                         [600, 600, 900, 1200, 1200])

    def test_reste_deduit_le_temps_passe(self):
        r = calculer(tache(travail=travail(depuis_s=240)), historique(600, 600, 900, 1200, 1200))
        self.assertEqual((r["reste"]["min_s"], r["reste"]["max_s"]), (360, 960))
        self.assertEqual(r["reste_texte"], "6 à 16 min")

    def test_plus_long_que_d_habitude(self):
        r = calculer(tache(travail=travail(depuis_s=1800)), historique(600, 600, 900, 1200, 1200))
        self.assertIsNone(r["reste"])
        self.assertEqual(r["reste_texte"], "plus long que d'habitude")

    def test_l_avancement_reduit_la_borne_haute(self):
        av = {"points": [{"texte": str(i), "fait": i < 3} for i in range(4)], "en_cours": None, "maj": il_y_a(30)}
        r = calculer(tache(travail=travail(depuis_s=240, avancement=av)), historique(600, 600, 900, 1200, 1200))
        self.assertLess(r["reste"]["max_s"], 960)
        self.assertLessEqual(r["reste"]["min_s"], r["reste"]["max_s"])



class Lot(unittest.TestCase):
    """Essai réel du 2026-11-18 (lot L5) : t68 finie disait « En cours : termine » et t69, que la même session faisait,
    ne disait rien ; l'utilisateur croyait l'agent arrêté."""
    TACHES = TACHES_PASSEES + [{"id": "t69", "titre": "Export et réimport Excel"}]

    def calculer(self, t, moteur_vivant=True):
        return avancement.pour_la_tache(t, self.TACHES, [], moteur_vivant, MAINTENANT, DELAI)

    def test_tache_faite_dit_que_l_agent_poursuit_le_lot(self):
        lot = {"etat": "faite", "agent": "agent-1", "courante": "t69", "rang": 1, "total": 2,
               "avancement": {"points": [{"texte": "Modele", "fait": True}], "en_cours": None}}
        r = self.calculer(tache(id="t68", dans_le_lot=lot))
        self.assertEqual(r["etat"], "lot_faite")
        self.assertIn("poursuit le lot dans la même session, sur t69 (Export et réimport Excel)", r["etat_texte"])
        self.assertEqual((r["points"][0]["fait"], r["en_cours"], r["reste"]), (True, None, None))

    def test_tache_a_venir_attend_son_tour_dans_le_lot(self):
        r = self.calculer(tache(id="t70", dans_le_lot={"etat": "a_venir", "courante": "t69", "avancement": None}))
        self.assertEqual(r["etat"], "lot_a_venir")
        self.assertIn("l'agent fait d'abord t69", r["etat_texte"])
        self.assertEqual(self.calculer(tache(dans_le_lot={"etat": "faite", "courante": "t69"}),
                                       moteur_vivant=False)["etat"], "moteur_arrete")

    def test_attente_du_verrou_de_tests(self):
        r = calculer(tache(travail=travail(action_s=900, vie_s=900, attente_tests={
            "depuis": il_y_a(300), "motif": "une campagne tourne déjà"})))
        self.assertEqual(r["etat"], "attente_tests")
        self.assertEqual(r["etat_texte"], "en attente pour lancer les tests (une autre campagne tourne sur le poste) "
                                          "· depuis 5 min")
        self.assertIsNone(r["file_tests"])

    def test_attente_du_verrou_de_tests_avec_sa_position_dans_la_file(self):
        r = calculer(tache(travail=travail(action_s=900, vie_s=900, attente_tests={
            "depuis": il_y_a(300), "motif": "1 campagne attend avant elle", "rang": 2, "total": 3})))
        self.assertEqual(r["etat"], "attente_tests")
        self.assertEqual(r["etat_texte"], "en attente pour lancer les tests · position 2 sur 3 dans la file · depuis 5 min")
        self.assertEqual(r["file_tests"], {"rang": 2, "total": 3})
        r = calculer(tache(travail=travail(action_s=900, vie_s=900, attente_tests={"rang": 1, "total": 1})))
        self.assertIn("position 1 sur 1 dans la file (passe dès que le poste se libère)", r["etat_texte"])


class Historique(unittest.TestCase):
    def test_l_historique_du_travail_est_recopie(self):
        h = [{"t": il_y_a(30), "texte": "lance python"}, {"t": None, "texte": "lit a.py"}]
        r = avancement.pour_la_tache(tache(travail=travail(historique=h)), TACHES_PASSEES, [], True, MAINTENANT, DELAI)
        self.assertEqual(r["historique"], h)

    def test_sans_historique_la_liste_est_vide(self):
        r = avancement.pour_la_tache(tache(travail=travail()), TACHES_PASSEES, [], True, MAINTENANT, DELAI)
        self.assertEqual(r["historique"], [])

    def test_un_element_mal_forme_est_ecarte_et_le_texte_borne(self):
        h = [{"t": None, "texte": "x" * 500}, {"t": 5, "texte": "ok"}, {"texte": 3}, "texte", {"t": None}]
        r = avancement.pour_la_tache(tache(travail=travail(historique=h)), TACHES_PASSEES, [], True, MAINTENANT, DELAI)
        self.assertEqual([x["texte"] for x in r["historique"]], ["x" * avancement.TEXTE_HISTORIQUE_MAX, "ok"])
        self.assertIsNone(r["historique"][1]["t"])

    def test_l_historique_est_borne(self):
        h = [{"t": None, "texte": f"lit f{i}.py"} for i in range(80)]
        r = avancement.pour_la_tache(tache(travail=travail(historique=h)), TACHES_PASSEES, [], True, MAINTENANT, DELAI)
        self.assertEqual(len(r["historique"]), avancement.MAX_HISTORIQUE)


if __name__ == "__main__":
    unittest.main()
