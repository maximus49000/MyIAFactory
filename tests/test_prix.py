"""Les prix : sources inventées, jamais d'Internet."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bureau import prix
from bureau.prix import TablePrix

SOURCE = {
    "sample_spec": {"input_cost_per_token": "prix en dollars", "output_cost_per_token": 0},
    "modele-a": {"input_cost_per_token": 3e-06, "output_cost_per_token": 1.5e-05,
                 "cache_read_input_token_cost": 3e-07, "cache_creation_input_token_cost": 3.75e-06},
    "modele-b": {"input_cost_per_token": 1e-06, "output_cost_per_token": 5e-06},
    "texte": {"input_cost_per_token": "beaucoup", "output_cost_per_token": 1e-06},
    "booleen": {"input_cost_per_token": True, "output_cost_per_token": 1e-06},
    "sans-sortie": {"input_cost_per_token": 1e-06},
    "liste": [1, 2],
}


def taux_xml(date="2026-11-09", usd="1.25"):
    return ("<?xml version='1.0' encoding='UTF-8'?>"
            "<gesmes:Envelope xmlns:gesmes='http://www.gesmes.org/xml/2002-08-01' "
            "xmlns='http://www.ecb.int/vocabulary/2002-08-01/eurofxref'>"
            "<gesmes:subject>Reference rates</gesmes:subject>"
            f"<Cube><Cube time='{date}'><Cube currency='JPY' rate='160.1'/>"
            f"<Cube currency='USD' rate='{usd}'/></Cube></Cube></gesmes:Envelope>")


class Source:
    """Simule les deux adresses ; compte les appels."""

    def __init__(self, prix_json=None, taux=None):
        self.prix_json = json.dumps(SOURCE) if prix_json is None else prix_json
        self.taux = taux_xml() if taux is None else taux
        self.appels = []

    def __call__(self, url):
        self.appels.append(url)
        valeur = self.prix_json if url == prix.URL_PRIX else self.taux if url == prix.URL_TAUX else None
        if valeur is None:
            raise AssertionError(f"adresse inattendue {url}")
        if isinstance(valeur, Exception):
            raise valeur
        return valeur


def source_avec(**modeles):
    return json.dumps({nom: {"input_cost_per_token": e, "output_cost_per_token": s}
                       for nom, (e, s) in modeles.items()})


class TestLire(unittest.TestCase):
    def test_lire_prix_conversion_par_million(self):
        p = prix.lire_prix(json.dumps(SOURCE))
        a = p["modele-a"]
        self.assertAlmostEqual(a["entree"], 3.0)
        self.assertAlmostEqual(a["sortie"], 15.0)
        self.assertAlmostEqual(a["cache_lecture"], 0.3)
        self.assertAlmostEqual(a["cache_ecriture"], 3.75)
        self.assertEqual((p["modele-b"]["cache_lecture"], p["modele-b"]["cache_ecriture"]), (None, None))

    def test_lire_prix_entree_illisible_ignoree(self):
        p = prix.lire_prix(json.dumps(SOURCE))
        self.assertEqual(sorted(p), ["modele-a", "modele-b"])
        for texte in ("pas du json", "[1, 2]", "{}", json.dumps({"x": {"input_cost_per_token": "1"}})):
            with self.assertRaises(ValueError):
                prix.lire_prix(texte)

    def test_lire_taux(self):
        date, eur = prix.lire_taux(taux_xml())
        self.assertEqual(date, "2026-11-09")
        self.assertAlmostEqual(eur, 0.8)
        for texte in ("<a/>", "pas du xml", taux_xml(usd="zéro"), taux_xml(usd="0"), taux_xml(usd="-1"),
                      "<!DOCTYPE a [<!ENTITY x 'y'>]><a>&x;</a>"):
            with self.assertRaises(ValueError):
                prix.lire_taux(texte)


class AvecTable(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.chemin = Path(self.dossier.name) / "prix-historique.jsonl"
        self.table = TablePrix(self.chemin)

    def tearDown(self):
        self.dossier.cleanup()

    def a(self, entree, sortie, **cache):
        return {"entree": entree, "sortie": sortie, "cache_lecture": cache.get("lecture"),
                "cache_ecriture": cache.get("ecriture")}


class TestTablePrix(AvecTable):
    def test_table_vide(self):
        self.assertEqual(self.table.prix_a("modele-a", "2026-11-09"), (None, None, False))
        self.assertIsNone(self.table.derniere_maj())

    def test_prix_a_dernier_avant_la_date(self):
        self.table.ajouter("2026-11-01", {"m": self.a(2.0, 10.0)}, 0.5)
        self.table.ajouter("2026-11-05", {"m": self.a(4.0, 20.0, lecture=1.0)}, 0.8)
        p, date, ancien = self.table.prix_a("m", "2026-11-03T12:00:00")
        self.assertEqual((date, ancien), ("2026-11-01", False))
        self.assertAlmostEqual(p["entree"], 1.0)   # 2 $ × 0,5 €/$
        self.assertAlmostEqual(p["sortie"], 5.0)
        self.assertIsNone(p["cache_lecture"])
        p, date, ancien = self.table.prix_a("m", "2026-11-05")
        self.assertEqual(date, "2026-11-05")
        self.assertAlmostEqual(p["entree"], 3.2)
        self.assertAlmostEqual(p["cache_lecture"], 0.8)
        self.assertEqual(self.table.derniere_maj(), "2026-11-05")

    def test_prix_a_avant_le_premier_prix(self):
        self.table.ajouter("2026-11-05", {"m": self.a(4.0, 20.0)}, 0.8)
        p, date, ancien = self.table.prix_a("m", "2026-10-01")
        self.assertEqual((date, ancien), ("2026-11-05", True))
        self.assertAlmostEqual(p["entree"], 3.2)

    def test_changement_de_prix_ne_bouge_pas_le_passe(self):
        self.table.ajouter("2026-11-01", {"m": self.a(2.0, 10.0)}, 0.5)
        avant = self.table.prix_a("m", "2026-11-02")
        self.table.ajouter("2026-11-03", {"m": self.a(8.0, 40.0)}, 0.9)
        self.assertEqual(TablePrix(self.chemin).prix_a("m", "2026-11-02"), avant)
        self.assertEqual(self.table.prix_a("m", "2026-11-02"), avant)

    def test_modele_inchange_reste_lisible(self):
        # La table ne garde que ce qui change : un modèle stable se lit toujours.
        self.table.ajouter("2026-11-01", {"m": self.a(2.0, 10.0), "n": self.a(1.0, 1.0)}, 0.5)
        self.table.ajouter("2026-11-02", {"m": self.a(2.0, 10.0), "n": self.a(3.0, 3.0)}, 0.5)
        lignes = [json.loads(x) for x in self.chemin.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sorted(lignes[1]["modeles"]), ["n"])
        p, date, _ = self.table.prix_a("m", "2026-11-02")
        self.assertEqual(date, "2026-11-02")
        self.assertAlmostEqual(p["entree"], 1.0)

    def test_modele_inconnu_none(self):
        self.table.ajouter("2026-11-01", {"m": self.a(2.0, 10.0)}, 0.5)
        self.assertEqual(self.table.prix_a("inconnu", "2026-11-02")[0], None)

    def test_ligne_illisible_ignoree(self):
        self.table.ajouter("2026-11-01", {"m": self.a(2.0, 10.0)}, 0.5)
        with open(self.chemin, "a", encoding="utf-8") as f:
            f.write("pas du json\n{\"date\": 3}\n")
        self.assertIsNotNone(TablePrix(self.chemin).prix_a("m", "2026-11-02")[0])


class TestActualiser(AvecTable):
    def test_actualiser_premiere_fois(self):
        src = Source()
        res = prix.actualiser(self.table, src, "2026-11-10")
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.table.derniere_maj(), "2026-11-10")
        p, _, _ = self.table.prix_a("modele-a", "2026-11-10")
        self.assertAlmostEqual(p["entree"], 2.4)   # 3 $ × 0,8 €/$

    def test_actualiser_une_fois_par_jour(self):
        src = Source()
        prix.actualiser(self.table, src, "2026-11-10")
        self.assertEqual(len(src.appels), 2)
        res = prix.actualiser(self.table, src, "2026-11-10")
        self.assertTrue(res["ok"])
        self.assertEqual(len(src.appels), 2)
        prix.actualiser(self.table, src, "2026-11-11")
        self.assertEqual(len(src.appels), 4)

    def test_source_injoignable_garde_l_ancien(self):
        prix.actualiser(self.table, Source(), "2026-11-03")
        avant = self.table.prix_a("modele-a", "2026-11-10")[0]
        for panne in (OSError("réseau coupé"), "pas du json", json.dumps({})):
            res = prix.actualiser(self.table, Source(prix_json=panne), "2026-11-10")
            self.assertFalse(res["ok"])
            self.assertIn("2026-11-03", res["message"])
            self.assertIn("impossible", res["message"])
            self.assertEqual(self.table.prix_a("modele-a", "2026-11-10")[0], avant)
        self.assertEqual(self.table.derniere_maj(), "2026-11-03")

    def test_taux_injoignable_garde_l_ancien_taux(self):
        prix.actualiser(self.table, Source(), "2026-11-03")
        res = prix.actualiser(self.table, Source(prix_json=source_avec(**{"modele-a": (6e-06, 3e-05)}),
                                                 taux=OSError("coupé")), "2026-11-10")
        self.assertFalse(res["ok"])
        self.assertIn("taux", res["message"])
        p, _, _ = self.table.prix_a("modele-a", "2026-11-10")
        self.assertAlmostEqual(p["entree"], 4.8)    # nouveau prix, ancien taux 0,8
        # La mise à jour est retentée (le taux manque encore aujourd'hui).
        src = Source()
        prix.actualiser(self.table, src, "2026-11-10")
        self.assertEqual(len(src.appels), 2)

    def test_premiere_fois_sans_taux_prix_inconnu(self):
        res = prix.actualiser(self.table, Source(taux="illisible"), "2026-11-10")
        self.assertFalse(res["ok"])
        self.assertIsNone(self.table.prix_a("modele-a", "2026-11-10")[0])

    def test_prix_absurde_refuse(self):
        prix.actualiser(self.table, Source(prix_json=source_avec(m=(2e-06, 1e-05), n=(1e-06, 1e-06))),
                        "2026-11-01")
        for jour, valeurs in (("2026-11-02", (-2e-06, 1e-05)), ("2026-11-03", (0, 1e-05)),
                              ("2026-11-04", (2.1e-05, 1e-05)), ("2026-11-05", (2e-06, 9e-07))):
            res = prix.actualiser(self.table, Source(prix_json=source_avec(m=valeurs, n=(1.5e-06, 1e-06))), jour)
            self.assertIn("m", res["message"], jour)
            self.assertIn("absurde", res["message"], jour)
            p, _, _ = self.table.prix_a("m", jour)
            self.assertAlmostEqual(p["entree"], 1.6, msg=jour)   # 2 $ × 0,8 : l'ancien prix
            self.assertAlmostEqual(self.table.prix_a("n", jour)[0]["entree"], 1.2, msg=jour)  # n change
        # ×10 tout juste : accepté.
        prix.actualiser(self.table, Source(prix_json=source_avec(m=(2e-05, 1e-05))), "2026-11-06")
        self.assertAlmostEqual(self.table.prix_a("m", "2026-11-06")[0]["entree"], 16.0)

    def test_taux_absurde_refuse(self):
        prix.actualiser(self.table, Source(), "2026-11-01")
        res = prix.actualiser(self.table, Source(taux=taux_xml(usd="13")), "2026-11-02")
        self.assertFalse(res["ok"])
        self.assertAlmostEqual(self.table.prix_a("modele-a", "2026-11-02")[0]["entree"], 2.4)

    def test_nouveau_modele_gratuit_ignore_sans_bruit(self):
        res = prix.actualiser(self.table, Source(prix_json=source_avec(m=(1e-06, 1e-06), local=(0, 0))),
                              "2026-11-01")
        self.assertTrue(res["ok"], res)
        self.assertIsNone(self.table.prix_a("local", "2026-11-01")[0])

    def test_nom_hostile_reste_du_texte(self):
        prix.actualiser(self.table, Source(prix_json=source_avec(**{"<img onerror=x>": (1e-06, 1e-06)})),
                        "2026-11-01")
        res = prix.actualiser(self.table, Source(prix_json=source_avec(**{"<img onerror=x>": (-1, 1e-06)})),
                              "2026-11-02")
        self.assertIsInstance(res["message"], str)


class TestPrixEffectif(AvecTable):
    def setUp(self):
        super().setUp()
        self.table.ajouter("2026-11-01", {"claude-x": self.a(2.0, 10.0)}, 0.5)

    def test_alias(self):
        regl = {"alias_modeles": {"sonnet": "claude-x"}}
        p, date, ancien = prix.prix_effectif(self.table, regl, "sonnet", "2026-11-02")
        self.assertAlmostEqual(p["entree"], 1.0)
        self.assertEqual(prix.prix_effectif(self.table, {}, "sonnet", "2026-11-02")[0], None)
        self.assertIsNotNone(prix.prix_effectif(self.table, {}, "claude-x", "2026-11-02")[0])
        # Un alias mal formé est ignoré.
        for mauvais in ([1], {"sonnet": 3}, "claude-x"):
            self.assertIsNone(prix.prix_effectif(self.table, {"alias_modeles": mauvais}, "sonnet", "2026-11-02")[0])

    def test_correction_manuelle_prioritaire(self):
        regl = {"alias_modeles": {"sonnet": "claude-x"},
                "prix": {"sonnet": {"entree": 7.0, "sortie": 30.0, "date": "2026-11-05"}}}
        p, date, ancien = prix.prix_effectif(self.table, regl, "sonnet", "2026-11-06T09:00:00")
        self.assertEqual((p["entree"], p["sortie"], date, ancien), (7.0, 30.0, "2026-11-05", False))
        # Avant sa date, la correction ne compte pas : le passé ne bouge pas.
        p, date, _ = prix.prix_effectif(self.table, regl, "sonnet", "2026-11-04")
        self.assertAlmostEqual(p["entree"], 1.0)
        self.assertEqual(date, "2026-11-01")

    def test_correction_sur_un_modele_sans_prix_automatique(self):
        regl = {"prix": {"local": [{"entree": 0.1, "sortie": 0.2, "date": "2026-11-01"},
                                   {"entree": 0.3, "sortie": 0.4, "date": "2026-11-08"}]}}
        self.assertEqual(prix.prix_effectif(self.table, regl, "local", "2026-11-03")[0]["entree"], 0.1)
        self.assertEqual(prix.prix_effectif(self.table, regl, "local", "2026-11-09")[0]["entree"], 0.3)
        self.assertIsNone(prix.prix_effectif(self.table, regl, "local", "2026-10-01")[0])

    def test_correction_mal_formee_ignoree(self):
        for corr in ({"entree": 1, "sortie": 1}, {"entree": "1", "sortie": 1, "date": "2026-11-01"},
                     {"entree": -1, "sortie": 1, "date": "2026-11-01"}, {"entree": 1, "sortie": 1, "date": "hier"},
                     {"entree": True, "sortie": 1, "date": "2026-11-01"}, "7 €"):
            p = prix.prix_effectif(self.table, {"prix": {"claude-x": corr}}, "claude-x", "2026-11-02")[0]
            self.assertAlmostEqual(p["entree"], 1.0, msg=corr)
        self.assertIsNotNone(prix.prix_effectif(self.table, {"prix": 3}, "claude-x", "2026-11-02")[0])


class TestOuvrirUrl(unittest.TestCase):
    def test_adresses_constantes(self):
        self.assertTrue(prix.URL_PRIX.startswith("https://raw.githubusercontent.com/"))
        self.assertTrue(prix.URL_TAUX.startswith("https://www.ecb.europa.eu/"))

    def test_ouvrir_url_refuse_http_et_autres_hotes(self):
        with mock.patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("sortie !")):
            for url in ("http://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
                        "https://exemple.invalid/prix.json", prix.URL_PRIX + "?x=1", "file:///etc/passwd", ""):
                with self.assertRaises(ValueError):
                    prix.ouvrir_url(url)

    def test_ouvrir_url_taille_limitee(self):
        class Reponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                return b"x" * n

        with mock.patch("urllib.request.OpenerDirector.open", return_value=Reponse()) as ouvrir:
            with self.assertRaises(ValueError):
                prix.ouvrir_url(prix.URL_PRIX)
            self.assertEqual(ouvrir.call_args.kwargs.get("timeout"), 10)

    def test_certificat_non_reconnu_message_clair(self):
        import ssl
        import urllib.error
        erreur = urllib.error.URLError(ssl.SSLCertVerificationError("unable to get local issuer certificate"))
        with mock.patch("urllib.request.OpenerDirector.open", side_effect=erreur):
            with self.assertRaises(ValueError) as ctx:
                prix.ouvrir_url(prix.URL_TAUX)
        self.assertIn("www.ecb.europa.eu", str(ctx.exception))
        self.assertIn("certificat", str(ctx.exception))

    def test_redirection_vers_http_refusee(self):
        gestionnaire = prix._RedirectionHttps()
        with self.assertRaises(Exception):
            gestionnaire.redirect_request(None, None, 302, "Found", {}, "http://ailleurs.invalid/")


if __name__ == "__main__":
    unittest.main()
