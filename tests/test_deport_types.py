import json
import tempfile
import unittest
from pathlib import Path

from bureau import deport
from bureau.deport_types import CATALOGUES, GENERIQUE, actions_exposees, catalogue_du_projet

ANDROID = CATALOGUES["application-mobile-android"]
CLES = {"libelle", "commande", "produit", "consomme", "artefact", "lieux", "bientot"}


class TestCatalogues(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)

    def test_chaque_entree_a_la_meme_forme(self):
        for catalogue in (GENERIQUE, ANDROID):
            for nom, entree in catalogue.items():
                self.assertEqual(set(entree), CLES, nom)

    def test_le_generique_est_le_catalogue_d_origine(self):
        self.assertEqual(list(GENERIQUE), ["apk", "tests", "emulateur", "charge"])
        self.assertEqual(GENERIQUE["tests"]["consomme"], ["apk"])
        self.assertEqual(GENERIQUE["apk"]["produit"], "apk")

    def test_android_valeurs_du_catalogue(self):
        self.assertEqual(list(ANDROID), ["apk", "tests", "lint", "emulateur", "release"])
        self.assertNotIn("charge", ANDROID)
        self.assertEqual(ANDROID["apk"]["commande"], "./gradlew assembleDebug")
        self.assertEqual(ANDROID["apk"]["artefact"], "app/build/outputs/apk/debug/*.apk")
        self.assertEqual(ANDROID["tests"]["commande"], "./gradlew testDebugUnitTest")
        self.assertEqual(ANDROID["emulateur"]["commande"], "./gradlew connectedDebugAndroidTest")
        self.assertEqual(ANDROID["emulateur"]["lieux"], ["poste"])
        self.assertEqual(ANDROID["release"]["produit"], "apk-release")
        self.assertEqual(ANDROID["release"]["lieux"], ["poste"])
        self.assertIn("clés de signature", ANDROID["release"]["bientot"])
        for nom in ("apk", "tests", "lint", "emulateur", "release"):
            self.assertEqual(ANDROID[nom]["consomme"], [], nom)

    def projet(self, contenu, sous_dossier=".factory"):
        dossier = self.tmp / sous_dossier if sous_dossier else self.tmp
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "factory.json").write_text(contenu, encoding="utf-8")
        return str(self.tmp)

    def test_genre_android_donne_le_catalogue_android(self):
        d = self.projet(json.dumps({"genre": "application-mobile-android"}))
        self.assertEqual(catalogue_du_projet(d), ("application-mobile-android", ANDROID))

    def test_factory_json_a_la_racine_aussi(self):
        d = self.projet(json.dumps({"genre": "application-mobile-android"}), sous_dossier=None)
        self.assertIs(catalogue_du_projet(d)[1], ANDROID)

    def test_sans_fichier_genre_inconnu_ou_illisible_donne_le_generique(self):
        self.assertEqual(catalogue_du_projet(str(self.tmp)), ("generique", GENERIQUE))
        for contenu in (json.dumps({"genre": "jeu-3d"}), json.dumps({}), "pas du json", "[1]",
                        json.dumps({"genre": 3})):
            with self.subTest(contenu=contenu):
                d = self.projet(contenu)
                self.assertEqual(catalogue_du_projet(d), ("generique", GENERIQUE))

    def test_actions_exposees(self):
        liste = actions_exposees(ANDROID)
        self.assertEqual([a["id"] for a in liste], list(ANDROID))
        release = liste[-1]
        self.assertEqual(set(release), {"id", "libelle", "lieux", "bientot"})
        self.assertEqual(release["libelle"], "APK signé (release)")
        self.assertEqual(release["lieux"], ["poste"])
        self.assertIn("clés de signature", release["bientot"])


class TestValidationParCatalogue(unittest.TestCase):
    def test_charge_refusee_pour_android_acceptee_en_generique(self):
        with self.assertRaises(ValueError) as c:
            deport.valider_lieux({"charge": "poste"}, catalogue=ANDROID)
        self.assertIn("n'existe pas pour ce type de projet", str(c.exception))
        self.assertEqual(deport.valider_lieux({"charge": "github"}), {"charge": "github"})

    def test_nom_inconnu_partout_reste_action_inconnue(self):
        with self.assertRaises(ValueError) as c:
            deport.valider_lieux({"bidon": "poste"}, catalogue=ANDROID)
        self.assertIn("Action inconnue", str(c.exception))

    def test_emulateur_github_refuse_pour_android(self):
        with self.assertRaises(ValueError) as c:
            deport.valider_lieux({"emulateur": "github"}, catalogue=ANDROID)
        self.assertIn("peu fiable", str(c.exception))

    def test_release_github_refusee_avec_les_cles_de_signature(self):
        with self.assertRaises(ValueError) as c:
            deport.valider_lieux({"release": "github"}, catalogue=ANDROID)
        self.assertIn("clés de signature", str(c.exception))
        self.assertEqual(deport.valider_lieux({"release": "poste", "lint": "github"}, catalogue=ANDROID),
                         {"release": "poste", "lint": "github"})

    def test_les_tests_unitaires_n_attendent_pas_l_apk(self):
        lieux = {"apk": "github", "tests": "poste"}
        self.assertEqual(deport.a_attendre(lieux, "tests", ANDROID), [])
        self.assertEqual(deport.a_attendre(lieux, "tests"), ["apk"])
        self.assertEqual(deport.avertissements(lieux, ANDROID), [])
        self.assertTrue(deport.avertissements(lieux)[0].startswith("« tests »"))
