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
    return [{"id": f"h{i}", "etape": "correction", "debut": il_y_a(10000 + d), "fin": il_y_a(10000)}
            for i, d in enumerate(durees)]


def calculer(t, histo=(), battement=None, delai=DELAI):
    return avancement.pour_la_tache(t, list(histo), battement if battement is not None else MAINTENANT.timestamp() - 10,
                                    MAINTENANT, delai)


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

    def test_moteur_muet(self):
        r = calculer(tache(travail=travail()), battement=MAINTENANT.timestamp() - 240)
        self.assertEqual(r["etat"], "moteur_muet")
        self.assertIn("moteur muet depuis 4 min", r["etat_texte"])

    def test_demarre_sans_flux(self):
        r = calculer(tache(travail=travail(action=None)))
        self.assertEqual(r["etat"], "demarre")

    def test_rien_sans_agent(self):
        self.assertIsNone(calculer(tache()))

    def test_liste_non_mise_a_jour(self):
        av = {"points": [{"texte": "a", "fait": False}], "en_cours": "a", "maj": il_y_a(600)}
        r = calculer(tache(travail=travail(action_s=20, avancement=av)))
        self.assertIn("liste non mise à jour depuis 10 min", r["etat_texte"])
        self.assertEqual(r["points"], av["points"])
        self.assertEqual(r["en_cours"], "a")


class Fourchette(unittest.TestCase):
    def test_inconnue_sous_trois_durees(self):
        self.assertIsNone(avancement.fourchette([600, 900]))
        r = calculer(tache(travail=travail()), historique(600, 900))
        self.assertIsNone(r["reste"])
        self.assertEqual(r["reste_texte"], "inconnu")

    def test_ecarte_les_durees_aberrantes(self):
        h = historique(0, 600, 600, 900, 1200, 1200) + [
            {"id": "x", "etape": "correction", "debut": il_y_a(3 * 86400 + 10), "fin": il_y_a(10)},
            {"id": "autre", "etape": "flux:f1", "debut": il_y_a(900), "fin": il_y_a(10)}]
        self.assertEqual(sorted(avancement.durees_de_l_etape(h, "correction")), [600, 600, 900, 1200, 1200])

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


if __name__ == "__main__":
    unittest.main()
