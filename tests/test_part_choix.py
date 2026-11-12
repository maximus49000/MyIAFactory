"""Le choix d'un partenaire : conseils d'abord, limites sautées, accord selon le tarif, rien ne bloque."""
import datetime
import unittest

from partenaires import choix, etat


def p(i, sc="synthese-vocale", plans=None, niveau=None, statut="actif"):
    return {"id": i, "nom": i.title(), "categorie": "voix-audio", "sous_categorie": sc, "statut": statut,
            "plans": plans if plans is not None else [{"nom": "Gratuit", "tarif": "gratuit"},
                                                     {"nom": "Pro", "tarif": "inclus"},
                                                     {"nom": "À l'usage", "tarif": "usage"}],
            "popularite": {"niveau": niveau} if niveau else None}


CATALOGUE = {"version": 1, "partenaires": [p("a"), p("b"), p("c"), p("d", niveau=5), p("e", niveau=2),
                                           p("f", sc="transcription"), p("g", statut="ferme")]}


def etat_avec(connectes, limites=(), abonnements=None):
    d = etat.vide()
    for i in connectes:
        d["connexions"][i] = {"etat": "connecte", "source": "test", "vu_le": "2026-11-11"}
        if abonnements and i in abonnements:
            d["connexions"][i]["abonnement"] = abonnements[i]
    for i in limites:
        d["limites"][i] = {"depuis": etat.maintenant(), "raison": "quota épuisé"}
    return d


class TestChoix(unittest.TestCase):
    def test_choisir_ordre_conseils_puis_catalogue(self):
        r = choix.ordonner("voix", ["c", "a"], CATALOGUE, etat_avec(["a", "b", "c", "f"]))
        self.assertEqual([x["id"] for x in r["partenaires"]], ["c", "a", "b"])   # f : autre sous-catégorie
        self.assertIsNone(r["meilleur_non_connecte"])

    def test_choisir_saute_limite(self):
        r = choix.ordonner("voix", ["a", "b"], CATALOGUE, etat_avec(["a", "b"], limites=["a"]))
        self.assertEqual([x["id"] for x in r["partenaires"]], ["b"])
        r = choix.ordonner("voix", ["a"], CATALOGUE, etat_avec(["a"], limites=["a"]))
        self.assertEqual(r["partenaires"], [])

    def test_limite_tombe_au_bout_d_un_jour(self):
        e = etat_avec(["a"])
        e["limites"]["a"] = {"depuis": "2020-01-01T00:00:00+00:00", "raison": "vieux"}
        self.assertEqual([x["id"] for x in choix.ordonner("voix", ["a"], CATALOGUE, e)["partenaires"]], ["a"])
        demain = datetime.datetime.now().astimezone() + datetime.timedelta(hours=25)
        self.assertFalse(etat.limite_active({"depuis": etat.maintenant()}, demain))

    def test_accord_requis_si_usage_ou_inconnu(self):
        e = etat_avec(["a", "b", "c"], abonnements={"a": "free", "b": "Pro", "c": "à l'usage"})
        e["connexions"]["d"] = {"etat": "connecte"}
        r = {x["id"]: x for x in choix.ordonner("voix", ["a", "b", "c", "d"], CATALOGUE, e)["partenaires"]}
        self.assertEqual((r["a"]["tarif"], r["a"]["accord_requis"]), ("gratuit", False))
        self.assertEqual((r["b"]["tarif"], r["b"]["accord_requis"]), ("inclus", False))
        self.assertEqual((r["c"]["tarif"], r["c"]["accord_requis"]), ("usage", True))
        self.assertEqual((r["d"]["tarif"], r["d"]["accord_requis"]), ("inconnu", True))   # plan non connu : on demande

    def test_meilleur_non_connecte(self):
        r = choix.ordonner("voix", ["a", "b"], CATALOGUE, etat_avec(["b"]))
        self.assertEqual([x["id"] for x in r["partenaires"]], ["b"])
        self.assertEqual(r["meilleur_non_connecte"], "a")
        # aucun connecté, aucun conseil : liste vide et le plus populaire du besoin, rien ne bloque
        r = choix.ordonner("synthese-vocale", [], CATALOGUE, etat_avec([]))
        self.assertEqual(r, {"partenaires": [], "meilleur_non_connecte": "d"})
        r = choix.ordonner("inconnu", [], CATALOGUE, etat_avec([]))
        self.assertEqual(r, {"partenaires": [], "meilleur_non_connecte": None})

    def test_declare_ou_ferme_jamais_choisi(self):
        e = etat_avec(["g"])
        e["connexions"]["a"] = {"etat": "declare"}
        self.assertEqual(choix.ordonner("voix", ["a", "g"], CATALOGUE, e)["partenaires"], [])

    def test_inscrits_ni_appeles_ni_oublies(self):
        e = etat_avec(["b"])
        etat.inscrire(e, "a", True)                       # un compte chez a : l'utilisateur peut y passer
        etat.inscrire(e, "b", True)                       # connecté aussi : on l'appelle directement
        etat.inscrire(e, "g", True)                       # fermé : jamais proposé
        etat.inscrire(e, "f", True)                       # autre sous-catégorie
        r = choix.ordonner("voix", ["a", "b"], CATALOGUE, e)
        self.assertEqual([x["id"] for x in r["partenaires"]], ["b"])
        self.assertEqual(r["inscrits"], [{"id": "a"}])
        self.assertIsNone(r["meilleur_non_connecte"])     # a est déjà accessible : rien à regretter
        r = choix.ordonner("voix", ["a"], CATALOGUE, etat_avec([]))
        self.assertNotIn("inscrits", r)                   # présent seulement quand il y en a
        e = etat_avec([])
        etat.inscrire(e, "c", True)
        r = choix.ordonner("synthese-vocale", [], CATALOGUE, e)
        self.assertEqual((r["partenaires"], r["inscrits"]), ([], [{"id": "c"}]))
        self.assertEqual(r["meilleur_non_connecte"], "d")  # les autres non connectés restent à regretter

    def test_inscrit_sans_la_section(self):
        e = etat_avec(["a"])
        del e["inscriptions"]                              # un état d'avant : rien ne casse
        self.assertEqual([x["id"] for x in choix.ordonner("voix", ["a"], CATALOGUE, e)["partenaires"]], ["a"])


if __name__ == "__main__":
    unittest.main()
