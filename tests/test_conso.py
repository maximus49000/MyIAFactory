"""La consommation du forfait Claude Code. Aucun appel réseau réel : le téléchargement est injecté."""
import json
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path

from bureau import abonnement, conso

BRUT = {
    "five_hour": {"utilization": 37.0, "resets_at": "2026-11-12T15:00:00+00:00"},
    "seven_day": {"utilization": 91.5, "resets_at": "2026-11-15T09:00:00+00:00"},
    "seven_day_fable": {"utilization": 12, "resets_at": None},
    "extra_usage": {"utilization": 0.0, "resets_at": None},
    "seven_day_opus": {"utilization": "x"},
}


def identifiants(dossier, jeton="secret", expire_dans=3600):
    p = Path(dossier) / "c.json"
    p.write_text(json.dumps({"claudeAiOauth": {"accessToken": jeton, "expiresAt": (time.time() + expire_dans) * 1000}}),
                 encoding="utf-8")
    return p


class MettreEnForme(unittest.TestCase):
    def test_fenetres_ordonnees_et_pire(self):
        r = conso.mettre_en_forme(BRUT)
        self.assertTrue(r["disponible"])
        self.assertEqual([f["cle"] for f in r["fenetres"]], ["five_hour", "seven_day", "seven_day_fable"])
        self.assertEqual([f["libelle"] for f in r["fenetres"]], ["5 heures", "Semaine", "Semaine · Fable"])
        self.assertEqual(r["fenetres"][0]["reste"], 63.0)
        self.assertEqual((r["pire"], r["reste"]), ("seven_day", 8.5))

    def test_valeurs_illisibles_ignorees(self):
        self.assertFalse(conso.mettre_en_forme({"five_hour": {"utilization": True}, "x": 3})["disponible"])
        self.assertFalse(conso.mettre_en_forme(None)["disponible"])
        r = conso.mettre_en_forme({"five_hour": {"utilization": 140}})
        self.assertEqual(r["fenetres"][0]["reste"], 0.0)


class Lire(unittest.TestCase):
    def test_lit_et_met_en_cache(self):
        with tempfile.TemporaryDirectory() as t:
            appels, heure = [], [0.0]

            def telecharger(jeton):
                appels.append(jeton)
                return BRUT

            c = conso.Conso(identifiants(t), telecharger, horloge=lambda: heure[0])
            self.assertTrue(c.lire()["disponible"])
            c.lire()
            self.assertEqual(appels, ["secret"])
            heure[0] = conso.DUREE_CACHE + 1
            c.lire()
            self.assertEqual(len(appels), 2)

    def test_le_jeton_ne_sort_pas(self):
        with tempfile.TemporaryDirectory() as t:
            r = conso.Conso(identifiants(t), lambda j: BRUT).lire()
            self.assertNotIn("secret", json.dumps(r))

    def test_jeton_absent_ou_perime(self):
        with tempfile.TemporaryDirectory() as t:
            r = conso.Conso(Path(t) / "absent.json", lambda j: self.fail("pas d'appel")).lire()
            self.assertFalse(r["disponible"])
            r = conso.Conso(identifiants(t, expire_dans=-60), lambda j: self.fail("pas d'appel")).lire()
            self.assertIn("renouveler", r["raison"])

    def test_pannes_reseau_et_refus(self):
        with tempfile.TemporaryDirectory() as t:
            def refuse(jeton):
                raise urllib.error.HTTPError("u", 401, "x", {}, None)

            def coupe(jeton):
                raise OSError("réseau")

            self.assertIn("renouveler", conso.Conso(identifiants(t), refuse).lire()["raison"])
            self.assertIn("réseau", conso.Conso(identifiants(t), coupe).lire()["raison"])


MAINTENANT = 1794480000   # 2026-11-12 environ ; les remises du compte sont tirées de là
RAZ5 = "2026-11-12T11:30:00.400000+00:00"
RAZ7 = "2026-11-15T09:00:00+00:00"


def brut(cinq=37.0, semaine=91.5):
    return {"five_hour": {"utilization": cinq, "resets_at": RAZ5}, "seven_day": {"utilization": semaine, "resets_at": RAZ7},
            "seven_day_fable": {"utilization": 12, "resets_at": RAZ7}}


class Memoire(unittest.TestCase):
    """Le rond dans le bureau : repli sur le dernier appel du moteur, versement à l'historique, part estimée.
    Rien n'est écrit hors d'un dossier temporaire, aucun réseau."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        abonnement.DOSSIER = self.d / "commun"
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(setattr, abonnement, "DOSSIER", None)

    def conso(self, telecharger, ident=True, part=None):
        i = identifiants(self.d) if ident else self.d / "absent.json"
        return conso.Conso(i, telecharger, memoire=True, part=part, maintenant=lambda: MAINTENANT)

    def test_une_lecture_reussie_est_versee_a_l_historique_en_utilise_sans_cout(self):
        r = self.conso(lambda j: brut()).lire()
        self.assertEqual((r["source"], r["mesure"]), ("compte", MAINTENANT))
        h = abonnement.lire_historique()
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["five_hour"]["pourcent"], 37.0)     # « utilisé », pas le « reste » (63) du rond
        self.assertEqual(h[0]["seven_day"]["pourcent"], 91.5)
        self.assertEqual(h[0]["five_hour"]["remise"], round(1794483000.4))
        self.assertEqual((h[0]["cout_usd"], h[0]["source"]), (None, "compte"))
        self.assertNotIn("seven_day_fable", json.dumps(h))        # seules les deux fenêtres du forfait
        self.assertEqual(abonnement.lire()["t"], MAINTENANT)

    def test_une_mesure_inchangee_n_ajoute_pas_de_ligne(self):
        heure = [0.0]
        c = conso.Conso(identifiants(self.d), lambda j: brut(), horloge=lambda: heure[0], memoire=True,
                        maintenant=lambda: MAINTENANT)
        c.lire()
        heure[0] = 100
        c.lire()
        self.assertEqual(len(abonnement.lire_historique()), 1)
        c2 = conso.Conso(identifiants(self.d), lambda j: brut(cinq=40.0), memoire=True, maintenant=lambda: MAINTENANT + 100)
        c2.lire()
        self.assertEqual(len(abonnement.lire_historique()), 2)

    def test_sans_memoire_rien_n_est_ecrit(self):
        conso.Conso(identifiants(self.d), lambda j: brut()).lire()
        self.assertEqual(abonnement.lire_historique(), [])

    def test_repli_sur_le_dernier_appel_du_moteur(self):
        abonnement.noter({"five_hour": {"pourcent": 30.0, "remise": MAINTENANT + 600},
                          "seven_day": {"pourcent": 95.0, "remise": MAINTENANT + 9000}, "t": MAINTENANT - 300}, 0.1)
        r = self.conso(lambda j: self.fail("pas de jeton"), ident=False).lire()
        self.assertTrue(r["disponible"])
        self.assertEqual((r["source"], r["mesure"], r["raison"]), ("moteur", MAINTENANT - 300, "Connexion Claude Code introuvable."))
        self.assertEqual([(f["cle"], f["utilise"], f["reste"]) for f in r["fenetres"]],
                         [("five_hour", 30.0, 70.0), ("seven_day", 95.0, 5.0)])
        self.assertEqual((r["pire"], r["reste"]), ("seven_day", 5.0))
        self.assertEqual(conso._epoch(r["fenetres"][0]["remise"]), MAINTENANT + 600)
        self.assertEqual(len(abonnement.lire_historique()), 1)    # le repli n'écrit rien

    def test_repli_ecarte_une_fenetre_deja_remise_a_zero(self):
        abonnement.noter({"five_hour": {"pourcent": 99.0, "remise": MAINTENANT - 10},
                          "seven_day": {"pourcent": 50.0, "remise": MAINTENANT + 9000}, "t": MAINTENANT - 7200}, 0.1)
        r = self.conso(lambda j: (_ for _ in ()).throw(OSError("réseau"))).lire()
        self.assertEqual(r["source"], "moteur")
        self.assertEqual([f["cle"] for f in r["fenetres"]], ["seven_day"])

    def test_sans_instantane_ou_tout_remis_a_zero_toujours_indisponible(self):
        r = self.conso(lambda j: self.fail("pas de jeton"), ident=False).lire()
        self.assertEqual(r, {"disponible": False, "raison": "Connexion Claude Code introuvable.", "part": None})

    def test_la_part_estimee_suit_la_fonction_donnee(self):
        page = {"pourcent_par_euro": {"five_hour": None, "seven_day": 2.5}, "mesures": {"five_hour": 0, "seven_day": 4},
                "minimum": 3}
        r = self.conso(lambda j: brut(), part=lambda: page).lire()
        self.assertEqual(r["part"], {"pourcent_par_euro": 2.5, "mesures": 4, "minimum": 3})
        self.assertIsNone(self.conso(lambda j: brut(), part=lambda: None).lire()["part"])     # couche API
        def casse():
            raise RuntimeError("x")
        self.assertIsNone(self.conso(lambda j: brut(), part=casse).lire()["part"])

    def test_le_jeton_ne_sort_pas_meme_avec_la_memoire(self):
        r = self.conso(lambda j: brut()).lire()
        self.assertNotIn("secret", json.dumps(r) + "".join(p.read_text() for p in (self.d / "commun").rglob("*") if p.is_file()))


if __name__ == "__main__":
    unittest.main()
