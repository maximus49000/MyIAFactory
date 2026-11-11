"""Les lecteurs de quota : adresse fixe du partenaire, en-tête attendu, `None` à la moindre erreur."""
import unittest

from partenaires import catalogue, quota

CLE = "CLE-SECRETE-RECONNAISSABLE-1234"


def faux(reponse):
    appels = []

    def ouvrir(url, entetes):
        appels.append((url, entetes))
        if isinstance(reponse, Exception):
            raise reponse
        return reponse
    return ouvrir, appels


class TestQuota(unittest.TestCase):
    def test_lecteurs_du_catalogue(self):
        lecteurs = {p["lecteur"] for p in catalogue.lire()["partenaires"] if p.get("lecteur")}
        self.assertEqual(lecteurs, set(quota.LECTEURS))

    def test_lecteur_attache_a_son_partenaire(self):
        cat = catalogue.lire()
        for p in cat["partenaires"]:
            if p.get("lecteur"):
                self.assertEqual(quota.LIENS[p["lecteur"]][0], p["id"])
                variables = {v for c in p["connexions"] for v in c.get("variables") or []}
                self.assertTrue(set(quota.LIENS[p["lecteur"]][1]) <= variables, p["id"])
        # une fiche réécrite ne peut pas détourner un lecteur vers un autre partenaire
        fiche = next(p for p in cat["partenaires"] if p["id"] == "tripo")
        fiche.update(lecteur="elevenlabs", quota_lisible="oui")
        self.assertTrue(any("lecteur" in e for e in catalogue.verifier(cat)))

    def test_solde_negatif_borne(self):
        o, _ = faux({"credits": -3})
        self.assertEqual(quota.lire("bfl", CLE, o)["reste"], 0)

    def test_redirection_refusee(self):
        h = quota._SansRedirection()
        self.assertIsNone(h.redirect_request(None, None, 302, "Found", {}, "http://ailleurs.example/"))

    def test_lecteur_deepl_illimite(self):
        o, appels = faux({"character_count": 5, "character_limit": 1_000_000_000_000})
        self.assertEqual(quota.lire("deepl", "abc:fx", o), {"illimite": True, "unite": "caractères"})
        self.assertTrue(appels[0][0].startswith("https://api-free.deepl.com/"))
        self.assertEqual(appels[0][1]["Authorization"], "DeepL-Auth-Key abc:fx")
        o, appels = faux({"character_count": 400, "character_limit": 500_000})
        self.assertEqual(quota.lire("deepl", "pro", o), {"reste": 499_600, "unite": "caractères"})
        self.assertTrue(appels[0][0].startswith("https://api.deepl.com/"))

    def test_lecteur_erreur_none(self):
        for lecteur in quota.LECTEURS:
            o, _ = faux(OSError("réseau"))
            self.assertIsNone(quota.lire(lecteur, CLE, o), lecteur)
            o, _ = faux({"inattendu": True})
            self.assertIsNone(quota.lire(lecteur, CLE, o), lecteur)
        self.assertIsNone(quota.lire("inconnu", CLE, faux({})[0]))
        self.assertIsNone(quota.lire("deepl", None, faux({})[0]))

    def test_lecteurs_rendent_le_reste(self):
        cas = {
            "elevenlabs": ({"character_count": 100, "character_limit": 1000, "tier": "starter"},
                           {"reste": 900, "unite": "caractères", "abonnement": "starter"}),
            "bfl": ({"credits": 42.5}, {"reste": 42.5, "unite": "crédits"}),
            "stability": ({"credits": 25}, {"reste": 25, "unite": "crédits"}),
            "leonardo": ({"user_details": [{"apiSubscriptionTokens": 100, "apiPaidTokens": 50}]},
                         {"reste": 150, "unite": "jetons d'API"}),
            "meshy": ({"balance": 300}, {"reste": 300, "unite": "crédits"}),
            "removebg": ({"data": {"attributes": {"credits": {"total": 12}, "api": {"free_calls": 50}}}},
                         {"reste": 12, "unite": "crédits (et 50 appels gratuits)"}),
            "kiri": ({"code": 0, "ok": True, "data": {"balance": 20}}, {"reste": 20, "unite": "crédits"}),
        }
        for lecteur, (reponse, attendu) in cas.items():
            o, appels = faux(reponse)
            self.assertEqual(quota.lire(lecteur, CLE, o), attendu, lecteur)
            url, entetes = appels[0]
            self.assertTrue(url.startswith("https://"), lecteur)
            self.assertTrue(any(CLE in v for v in entetes.values()), lecteur)   # la clé ne part que dans l'en-tête
            self.assertNotIn(CLE, url)


if __name__ == "__main__":
    unittest.main()
