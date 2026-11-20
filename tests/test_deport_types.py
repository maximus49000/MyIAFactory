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
        self.assertEqual(list(GENERIQUE), ["apk", "tests", "emulateur", "charge", "recette-emulateur"])
        self.assertEqual(GENERIQUE["tests"]["consomme"], ["apk"])
        self.assertEqual(GENERIQUE["apk"]["produit"], "apk")

    def test_android_valeurs_du_catalogue(self):
        self.assertEqual(list(ANDROID), ["apk", "tests", "lint", "emulateur", "release", "recette-emulateur"])
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
        release = liste[list(ANDROID).index("release")]
        self.assertEqual(set(release), {"id", "libelle", "lieux", "bientot", "servie_au_serveur"})
        self.assertIs(release["servie_au_serveur"], False)
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


class TestRecetteEmulateur(unittest.TestCase):
    """L'action `recette-emulateur` : seulement sur le serveur, accord permanent par projet (jamais le poste par défaut)."""
    RECETTE = "recette-emulateur"

    def test_recette_emulateur_dans_le_catalogue_android_et_generique(self):
        for catalogue in (GENERIQUE, ANDROID):
            e = catalogue[self.RECETTE]
            self.assertEqual(e["libelle"], "Recette sur émulateur")
            self.assertEqual(e["lieux"], ["serveur"])
            self.assertEqual(e["consomme"], ["apk"])
            self.assertIsNone(e["produit"])
        self.assertEqual(ANDROID["emulateur"]["lieux"], ["poste"])           # l'émulateur Gradle ne bouge pas
        self.assertEqual(ANDROID["emulateur"]["commande"], "./gradlew connectedDebugAndroidTest")
        self.assertEqual(GENERIQUE["emulateur"]["lieux"], ["poste", "serveur"])

    def test_exposee_comme_servie_au_serveur(self):
        exposees = {a["id"]: a for a in actions_exposees(ANDROID)}
        self.assertIs(exposees[self.RECETTE]["servie_au_serveur"], True)
        self.assertEqual(exposees[self.RECETTE]["lieux"], ["serveur"])
        self.assertFalse(any(a["servie_au_serveur"] for n, a in exposees.items() if n != self.RECETTE))

    def test_le_serveur_est_accepte_pour_cette_action_seulement(self):
        for catalogue in (GENERIQUE, ANDROID):
            self.assertEqual(deport.valider_lieux({self.RECETTE: "serveur"}, catalogue=catalogue),
                             {self.RECETTE: "serveur"})
            for lieu in ("poste", "github"):
                with self.assertRaises(ValueError):
                    deport.valider_lieux({self.RECETTE: lieu}, catalogue=catalogue)
        with self.assertRaises(ValueError) as c:
            deport.valider_lieux({"tests": "serveur"})
        self.assertIn("pas encore disponible", str(c.exception))

    def test_pas_de_defaut_au_poste(self):
        self.assertNotIn(self.RECETTE, deport.LIEUX_PAR_DEFAUT)
        self.assertEqual(set(deport.LIEUX_PAR_DEFAUT.values()), {"poste"})

    def test_lieu_effectif_reglage_du_projet_seulement_sinon_non_regle(self):
        globaux = {self.RECETTE: "serveur", "apk": "github"}
        self.assertIsNone(deport.lieu_effectif(globaux, {}, self.RECETTE, ANDROID))
        self.assertIsNone(deport.lieu_effectif({}, None, self.RECETTE, ANDROID))
        self.assertEqual(deport.lieu_effectif({}, {self.RECETTE: "serveur"}, self.RECETTE, ANDROID), "serveur")
        self.assertEqual(deport.lieu_effectif(globaux, {}, "apk", ANDROID), "github")      # les autres : inchangé
        self.assertEqual(deport.lieu_effectif({}, {}, "apk", ANDROID), "poste")
        self.assertEqual(deport.lieu_effectif({}, {}, "apk"), "poste")

    def test_pas_d_avertissement_de_chaine_pour_la_recette(self):
        for lieu in (None, "serveur"):
            lieux = {"apk": "github", "tests": "github", "lint": "github", "emulateur": "poste", "release": "poste",
                     self.RECETTE: lieu}
            self.assertEqual(deport.avertissements(lieux, ANDROID), [])
        lieux = {"apk": "github", "tests": "poste", "emulateur": "poste", "charge": "poste", self.RECETTE: "serveur"}
        self.assertFalse(any(self.RECETTE in t for t in deport.avertissements(lieux)))
