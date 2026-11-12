"""Les jauges d'abonnement : l'analyse du flux `stream-json`, l'instantané gardé, l'étalonnage de la part estimée.
Aucun appel réel, rien d'écrit dans le vrai dossier commun."""
import json
import tempfile
import unittest
from pathlib import Path

from bureau import abonnement
from moteur import appel

RESULTAT = {"type": "result", "is_error": False, "result": "pong", "session_id": "s1", "total_cost_usd": 0.002,
            "modelUsage": {"claude-haiku-5-5": {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 100,
                                                "cacheCreationInputTokens": 7}}}


def evenement(cinq=0.25, semaine=0.43, remise5=1794485400, remise7=1794639600):
    return {"type": "rate_limit_event", "rate_limit_info": {
        "status": "allowed", "resetsAt": remise5, "rateLimitType": "five_hour", "utilization": cinq,
        "unifiedWindows": {"five_hour": {"utilization": cinq, "resetsAt": remise5, "status": "allowed"},
                           "seven_day": {"utilization": semaine, "resetsAt": remise7, "status": "allowed"}}}}


def flux(*objets):
    return "\n".join(json.dumps(o) for o in objets).encode()


class Analyse(unittest.TestCase):
    def test_les_deux_fenetres_et_le_resultat(self):
        r, evts = appel._lire_flux(flux({"type": "system"}, evenement(), RESULTAT))
        self.assertEqual(r["result"], "pong")
        snap = abonnement.instantane_depuis(evts, 1000)
        self.assertEqual(snap, {"five_hour": {"pourcent": 25.0, "remise": 1794485400},
                                "seven_day": {"pourcent": 43.0, "remise": 1794639600}, "t": 1000})

    def test_a_defaut_de_unified_windows_le_type_et_l_utilisation(self):
        ev = {"type": "rate_limit_event", "rate_limit_info": {"rateLimitType": "seven_day", "utilization": 0.5,
                                                              "resetsAt": 1794639600}}
        self.assertEqual(abonnement.instantane_depuis([ev], 5),
                         {"seven_day": {"pourcent": 50.0, "remise": 1794639600}, "t": 5})

    def test_absent_ou_illisible_rien_d_invente(self):
        self.assertIsNone(abonnement.instantane_depuis([], 1))
        mauvais = [{"rate_limit_info": {"unifiedWindows": {"five_hour": {"utilization": "x", "resetsAt": 5},
                                                           "seven_day": {"utilization": 3, "resetsAt": 5}}}},
                   {"rate_limit_info": "oups"}, "pas un dict", {"rate_limit_info": {"rateLimitType": "autre",
                                                                                   "utilization": 0.2, "resetsAt": 5}}]
        self.assertIsNone(abonnement.instantane_depuis(mauvais, 1))

    def test_sortie_sans_ligne_result_est_une_erreur(self):
        with self.assertRaises(appel.ErreurAppel):
            appel.appeler("c", "d", "haiku", executer=lambda *a: (0, flux(evenement())))

    def test_ancien_format_d_un_seul_objet_reste_compris(self):
        r = appel.appeler("c", "d", "haiku", executer=lambda *a: (0, json.dumps(RESULTAT, indent=2).encode()))
        self.assertEqual(r.texte, "pong")
        self.assertIsNone(r.abonnement)

    def test_l_appel_rend_le_meme_resultat_et_l_instantane(self):
        avec = appel.appeler("c", "d", "haiku", executer=lambda *a: (0, flux(evenement(), RESULTAT)))
        sans = appel.appeler("c", "d", "haiku", executer=lambda *a: (0, flux(RESULTAT)))
        self.assertEqual((avec.texte, avec.session, avec.cout_usd), (sans.texte, sans.session, sans.cout_usd))
        self.assertEqual(sans.usage, {"modele": "claude-haiku-5-5", "entree": 10, "sortie": 5, "cache_lecture": 100,
                                      "cache_ecriture": 7})
        self.assertEqual(avec.abonnement["seven_day"]["pourcent"], 43.0)
        self.assertEqual(avec.usage["abonnement"], avec.abonnement)   # chaque usage garde l'instantané du début
        self.assertNotIn("abonnement", sans.usage)

    def test_un_executeur_injecte_n_ecrit_jamais_dans_le_dossier_commun(self):
        with tempfile.TemporaryDirectory() as tmp:
            abonnement.DOSSIER = Path(tmp)
            try:
                appel.appeler("c", "d", "haiku", executer=lambda *a: (0, flux(evenement(), RESULTAT)))
            finally:
                abonnement.DOSSIER = None
            self.assertEqual(list(Path(tmp).iterdir()), [])


class Dossier(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def snap(self, p, remise=1000, t=1):
        return {"five_hour": {"pourcent": p, "remise": remise}, "t": t}

    def test_noter_garde_le_dernier_et_l_historique(self):
        abonnement.noter(self.snap(10.0, t=1), 0.5, self.d)
        abonnement.noter(self.snap(12.0, t=2), 0.7, self.d)
        self.assertEqual(abonnement.lire(self.d)["five_hour"]["pourcent"], 12.0)
        h = abonnement.lire_historique(self.d)
        self.assertEqual([x["cout_usd"] for x in h], [0.5, 0.7])
        self.assertEqual([p.name for p in self.d.iterdir() if p.suffix == ".tmp"], [])

    def test_rien_d_ecrit_sans_instantane_lisible(self):
        abonnement.noter(None, 1.0, self.d)
        abonnement.noter({"five_hour": {"pourcent": 500, "remise": 5}, "t": 1}, 1.0, self.d)
        self.assertEqual(list(self.d.iterdir()), [])
        self.assertIsNone(abonnement.lire(self.d))

    def test_lecture_du_compte_sans_cout_et_sans_doublon(self):
        abonnement.noter(self.snap(10.0, t=1), 0.5, self.d)
        abonnement.noter(self.snap(10.0, remise=1001, t=2), source="compte", dossier=self.d)   # identique : pas de ligne
        abonnement.noter(self.snap(11.0, t=3), 9.9, source="compte", dossier=self.d)           # le coût donné est ignoré
        h = abonnement.lire_historique(self.d)
        self.assertEqual([(x["cout_usd"], x.get("source")) for x in h], [(0.5, None), (None, "compte")])
        self.assertEqual(abonnement.lire(self.d)["t"], 3)

    def test_fichier_illisible_ignore(self):
        (self.d / abonnement.NOM_INSTANTANE).write_text("{pas du json", encoding="utf-8")
        (self.d / abonnement.NOM_HISTORIQUE).write_text("n'importe quoi\n", encoding="utf-8")
        self.assertIsNone(abonnement.lire(self.d))
        self.assertEqual(abonnement.lire_historique(self.d), [])


def ligne(p, cout, remise=1000, fenetre="five_hour"):
    return {fenetre: {"pourcent": p, "remise": remise}, "t": 1, "cout_usd": cout}


class Etalonnage(unittest.TestCase):
    def test_une_mesure_par_ecart_suffisant(self):
        # 2 points pour 2 $ (1 par dollar), puis 4 points pour 1 $
        h = [ligne(10.0, 1.0), ligne(11.0, 1.0), ligne(12.0, 1.0), ligne(16.0, 1.0)]
        self.assertEqual(abonnement.mesures(h, "five_hour"), [1.0, 4.0])

    def test_une_remise_a_zero_coupe_la_serie(self):
        h = [ligne(10.0, 1.0), ligne(30.0, 1.0, remise=9999), ligne(31.0, 1.0, remise=9999)]
        self.assertEqual(abonnement.mesures(h, "five_hour"), [])

    def test_un_recul_ou_un_cout_inconnu_repart_de_zero(self):
        h = [ligne(10.0, 1.0), ligne(5.0, None), ligne(9.0, 1.0), ligne(10.0, 1.0)]
        self.assertEqual(abonnement.mesures(h, "five_hour"), [])

    def test_sous_le_minimum_de_mesures_en_cours_d_etalonnage(self):
        h = [ligne(0.0, 1.0), ligne(4.0, 1.0), ligne(8.0, 1.0)]
        self.assertEqual(abonnement.points_par_dollar(h, "five_hour"), (None, 2))

    def test_estimation_prudente_mediane_de_la_moitie_basse(self):
        h, p = [], 0.0
        for gain in (10.0, 2.0, 4.0, 3.0, 20.0):   # points gagnés pour 1 $ chacun
            h.append(ligne(p, 1.0))
            p += gain
        h.append(ligne(p, 1.0))
        # mesures triées : 2, 3, 4, 10, 20 -> moitié basse 2, 3, 4 -> médiane 3
        self.assertEqual(abonnement.points_par_dollar(h, "five_hour"), (3.0, 5))

    def test_des_instantanes_sans_cout_ne_perdent_pas_le_cout_des_appels(self):
        # appel (t=1, 1 $, 10 %), lecture du compte (t=2, 10,5 %), appel (t=3, 1 $, 12 %), lecture (t=4, 14 %) :
        # 2 points pour le premier appel (1 $, cumulé à travers la lecture du compte), puis 2 points pour le second
        def compte(p, t):
            return {"five_hour": {"pourcent": p, "remise": 1000}, "t": t, "cout_usd": None, "source": "compte"}
        h = [ligne(10.0, 1.0), compte(10.5, 2), ligne(12.0, 1.0), compte(14.0, 4)]
        for i, x in enumerate(h):
            x["t"] = i + 1
        self.assertEqual(abonnement.mesures(h, "five_hour"), [2.0, 2.0])

    def test_l_ordre_du_fichier_ne_compte_pas_c_est_la_date(self):
        # l'appel est écrit à sa fin (après la lecture du compte) mais daté de son début
        a, c, b = ligne(10.0, 1.0), {"five_hour": {"pourcent": 10.0, "remise": 1000}, "cout_usd": None, "source": "compte"}, \
            {"five_hour": {"pourcent": 13.0, "remise": 1000}, "cout_usd": None, "source": "compte"}
        a["t"], c["t"], b["t"] = 100, 120, 200
        self.assertEqual(abonnement.mesures([c, b, a], "five_hour"), abonnement.mesures([a, c, b], "five_hour"))
        self.assertEqual(abonnement.mesures([c, b, a], "five_hour"), [3.0])

    def test_un_appel_de_cout_inconnu_reste_une_coupure_meme_entre_des_lectures(self):
        c1 = {"five_hour": {"pourcent": 10.0, "remise": 1000}, "t": 1, "cout_usd": None, "source": "compte"}
        inconnu = {"five_hour": {"pourcent": 10.0, "remise": 1000}, "t": 2, "cout_usd": None}
        c2 = {"five_hour": {"pourcent": 20.0, "remise": 1000}, "t": 3, "cout_usd": None, "source": "compte"}
        self.assertEqual(abonnement.mesures([c1, inconnu, c2], "five_hour"), [])

    def test_la_remise_du_compte_a_la_seconde_pres_reste_la_meme_fenetre(self):
        h = [ligne(10.0, 1.0, remise=1000), ligne(14.0, 1.0, remise=1001), ligne(18.0, 1.0, remise=999)]
        self.assertEqual(abonnement.mesures(h, "five_hour"), [4.0, 4.0])

    def test_pour_la_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            p = 0.0
            for i in range(5):
                abonnement.noter({"seven_day": {"pourcent": p, "remise": 5000}, "t": i + 1}, 1.0, d)
                p += 3.0
            abonnement.noter({"seven_day": {"pourcent": p, "remise": 5000}, "t": 9}, 1.0, d)
            page = abonnement.pour_la_page(d, euros_par_dollar=0.5, maintenant=100)
            self.assertEqual(page["instantane"]["seven_day"]["pourcent"], 15.0)
            self.assertAlmostEqual(page["pourcent_par_euro"]["seven_day"], 6.0)   # 3 points par $ = 6 par €
            self.assertIsNone(page["pourcent_par_euro"]["five_hour"])
            self.assertEqual(page["mesures"]["seven_day"], 5)
            self.assertIsNone(abonnement.pour_la_page(d, 0.5, couche="api"))
            self.assertIsNone(abonnement.pour_la_page(d, None)["pourcent_par_euro"]["seven_day"])


if __name__ == "__main__":
    unittest.main()
