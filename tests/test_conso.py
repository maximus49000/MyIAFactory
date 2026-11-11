"""La consommation du forfait Claude Code. Aucun appel réseau réel : le téléchargement est injecté."""
import json
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path

from bureau import conso

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


if __name__ == "__main__":
    unittest.main()
