"""Le registre des APK construits : une recette reçoit l'APK existant dont les sources correspondent au code testé, sans
construction ni livraison ; sources changées → UNE construction partagée (FM_Stats t294 reconstruisait à chaque passage)."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from moteur import rapport, regles, registre_apk
from tests import test_moteur_serie_reprise as tsr

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import deporter  # noqa: E402

APP = "android_app"
CLIENT = f"{APP}/build/app/outputs/flutter-apk/app-client-release.apk"


class Depot(tsr.AvecValidation):
    def setUp(self):
        super().setUp()
        self.projet_avec_validation(flux=tsr.FLUX, elements=0)
        self.d = self.projet.dossier
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "x@x")
        self.git("config", "user.name", "x")
        self.ecrire(f"{APP}/pubspec.yaml", "name: app\ndependencies:\n  flutter:\n    sdk: flutter\n")
        self.ecrire(f"{APP}/lib/main.dart", "void main() {}\n")
        self.ecrire(f"{APP}/assets/docs/CHANGELOG.md", "v1\n")
        self.ecrire("serveur/app.py", "x = 1\n")
        self.valider("base")

    def git(self, *a):
        return subprocess.run(["git", "-C", str(self.d), *a], capture_output=True, check=True)

    def ecrire(self, chemin, texte):
        (self.d / chemin).parent.mkdir(parents=True, exist_ok=True)
        (self.d / chemin).write_text(texte, encoding="utf-8")

    def valider(self, message, *fichiers):
        self.git("add", "--", *(fichiers or [f"{APP}", "serveur"]))
        self.git("commit", "-q", "-m", message)

    def construire(self, chemin=CLIENT):
        """Un APK construit et rapatrié (le fichier existe au poste), enregistré au registre."""
        self.ecrire(chemin, "APK")
        return registre_apk.enregistrer(str(self.d), chemin)


class Empreinte(Depot):
    def test_seuls_les_fichiers_qui_changent_l_application_changent_l_empreinte(self):
        avant = registre_apk.empreinte(str(self.d))
        self.ecrire("serveur/app.py", "x = 2\n")
        self.ecrire(f"{APP}/assets/docs/CHANGELOG.md", "v2\n")
        self.ecrire(f"{APP}/test/x_test.dart", "t\n")
        self.valider("serveur, docs embarquées, test")
        self.assertEqual(registre_apk.empreinte(str(self.d)), avant)
        self.ecrire(f"{APP}/lib/main.dart", "void main() { run(); }\n")
        self.valider("code")
        self.assertNotEqual(registre_apk.empreinte(str(self.d)), avant)

    def test_projet_sans_flutter_pas_d_empreinte(self):
        (self.d / APP / "pubspec.yaml").write_text("name: x\n", encoding="utf-8")
        self.valider("plus flutter")
        self.assertIsNone(registre_apk.empreinte(str(self.d)))
        self.assertEqual(registre_apk.fournir(str(self.d))["etat"], "inconnu")

    def test_la_variante_vient_du_nom(self):
        self.assertEqual(registre_apk.variante_de(CLIENT), "client")
        self.assertEqual(registre_apk.variante_de("build/app-release.apk"), "defaut")


class Fournir(Depot):
    def test_sources_inchangees_l_apk_existant_est_fourni_sans_construction(self):
        self.construire()
        r = registre_apk.fournir(str(self.d), "client", tache="t294")
        self.assertEqual((r["etat"], r["apk"]["chemin"], r["apk"]["variante"]), ("existant", CLIENT, "client"))
        self.assertFalse((self.d / ".factory" / registre_apk.NOM_DEMANDES).exists())      # aucune construction demandée
        self.ecrire("serveur/app.py", "x = 9\n")
        self.valider("serveur seul")
        self.assertEqual(registre_apk.fournir(str(self.d), "client", tache="t295")["etat"], "existant")

    def test_sources_changees_une_construction_est_demandee(self):
        self.construire()
        self.ecrire(f"{APP}/lib/main.dart", "void main() { nouveau(); }\n")
        self.valider("code")
        r = registre_apk.fournir(str(self.d), "client", tache="t294")
        self.assertEqual((r["etat"], r["raison"], r["construire"]), ("a_construire", "perime", True))

    def test_deux_tests_simultanes_une_seule_construction(self):
        self.construire()
        self.ecrire(f"{APP}/lib/main.dart", "void main() { nouveau(); }\n")
        self.valider("code")
        premier = registre_apk.fournir(str(self.d), "client", tache="t294")
        second = registre_apk.fournir(str(self.d), "client", tache="t295")
        self.assertTrue(premier["construire"])
        self.assertFalse(second["construire"])
        self.assertEqual(second["attend"], "t294")
        self.construire()                                          # la construction arrive : la demande est levée
        self.assertEqual(registre_apk.fournir(str(self.d), "client", tache="t295")["etat"], "existant")

    def test_une_variante_absente_demande_une_construction(self):
        self.construire()
        r = registre_apk.fournir(str(self.d), "maitre", tache="t294")
        self.assertEqual((r["etat"], r["raison"], r["variante"], r["construire"]), ("a_construire", "absent", "maitre", True))

    def test_un_apk_dont_le_fichier_a_disparu_n_est_pas_fourni(self):
        self.construire()
        (self.d / CLIENT).unlink()
        self.assertEqual(registre_apk.fournir(str(self.d), "client", tache="t1")["etat"], "a_construire")

    def test_une_demande_expiree_peut_etre_reprise(self):
        registre_apk.demande_de_construction(str(self.d), "client", "e", "t1", maintenant=1000.0)
        ok, attend = registre_apk.demande_de_construction(str(self.d), "client", "e", "t2",
                                                          maintenant=1000.0 + registre_apk.DELAI_CONSTRUCTION_S + 1)
        self.assertEqual((ok, attend), (True, None))

    def test_ce_qui_n_est_pas_un_apk_n_entre_pas_au_registre(self):
        self.assertIsNone(registre_apk.enregistrer(str(self.d), "build/x.zip"))
        self.assertEqual(registre_apk.lire(str(self.d)), [])


class RecetteSurEmulateur(Depot):
    def appeler(self):
        catalogue = {"recette-emulateur": {"consomme": []}}
        return deporter._apk_de_la_recette({"apk": None, "variante": None}, str(self.d), catalogue, "recette-emulateur", {})

    def test_la_recette_sur_emulateur_trouve_l_apk_existant(self):
        self.construire()
        chemin, erreur = self.appeler()
        self.assertIsNone(erreur)
        self.assertEqual(Path(chemin), (self.d / CLIENT).resolve())

    def test_apres_un_changement_de_code_le_registre_ne_donne_plus_l_ancien_apk(self):
        self.construire()
        self.ecrire(f"{APP}/lib/main.dart", "void main() { nouveau(); }\n")
        self.valider("code")
        self.assertIsNone(deporter._apk_du_registre(str(self.d)))


class RecettePerimee(Depot):
    def test_une_recette_sur_emulateur_ne_recoit_pas_un_apk_perime_elle_le_dit(self):
        self.construire()
        self.ecrire(f"{APP}/lib/main.dart", "void main() { nouveau(); }\n")
        self.valider("code")
        chemin, erreur = deporter._apk_de_la_recette({"apk": None, "variante": None}, str(self.d),
                                                     {"recette-emulateur": {"consomme": []}}, "recette-emulateur", {})
        self.assertIsNone(chemin)
        self.assertIn("ne correspond plus aux sources", erreur)

    def test_sans_registre_le_comportement_d_avant_est_garde(self):
        chemin, erreur = deporter._apk_de_la_recette({"apk": None, "variante": None}, str(self.d),
                                                     {"recette-emulateur": {"consomme": []}}, "recette-emulateur", {})
        self.assertIsNone(chemin)
        self.assertIn("Aucun APK trouvé", erreur)


class ConsigneDuTest(Depot):
    def tache(self, titre="Vérification de l'APK Client"):
        tid = self.ok("tache", entree={"titre": titre, "fonctionnalite": "f1", "role": "testeur", "etape": "flux:essai",
                                       "colonne": "essai", "active": False})["id"]
        return next(t for t in self.suivi()["taches"] if t["id"] == tid)

    def journal(self, t):
        return json.dumps(next(x for x in self.suivi()["taches"] if x["id"] == t["id"])["journal"], ensure_ascii=False)

    def test_un_apk_correspondant_est_donne_et_la_construction_interdite_et_tracee(self):
        self.construire()
        t = self.tache()
        (texte,) = regles._consigne_de_l_apk_existant(self.projet, t)
        self.assertIn(CLIENT, texte)
        self.assertIn("NE construis PAS", texte)
        self.assertIn("apk_utilise", texte)
        self.assertIn("variante client", self.journal(t))

    def test_sources_changees_une_tache_construit_les_autres_attendent(self):
        self.construire()
        self.ecrire(f"{APP}/lib/main.dart", "void main() { nouveau(); }\n")
        self.valider("code")
        (premier,) = regles._consigne_de_l_apk_existant(self.projet, self.tache("Vérification de l'APK Client"))
        (second,) = regles._consigne_de_l_apk_existant(self.projet, self.tache("Recette de l'APK Client, deuxième passe"))
        self.assertIn("Construis-le UNE fois", premier)
        self.assertIn("ne le construis PAS", second)

    def test_hors_projet_flutter_rien_n_est_ajoute(self):
        (self.d / APP / "pubspec.yaml").write_text("name: x\n", encoding="utf-8")
        self.valider("plus flutter")
        self.assertEqual(regles._consigne_de_l_apk_existant(self.projet, self.tache()), [])

    def test_la_consigne_du_testeur_la_contient(self):
        self.construire()
        t = self.tache()
        with mock.patch.object(regles, "_consigne_de_l_apk_existant", return_value=["APK X"]) as f:
            f(self.projet, t)
        f.assert_called_once()


MAITRE = f"{APP}/build/app/outputs/flutter-apk/app-maitre-release.apk"


class BonneVariante(Depot):
    """FM_Stats f35, t313 : la vérification d'une correction « APK Client » a reçu l'APK Maître."""

    def setUp(self):
        super().setUp()
        from datetime import datetime, timezone
        self.construire(CLIENT)
        self.ecrire(MAITRE, "APK")
        registre_apk.enregistrer(str(self.d), MAITRE, maintenant=datetime(2030, 1, 1, tzinfo=timezone.utc))     # le plus récent

    def tache(self, titre, journal=None, fait=False):
        e = {"titre": titre, "fonctionnalite": "f1", "role": "testeur", "etape": "flux:essai", "colonne": "fait" if fait else "essai",
             "active": False}
        if journal:
            e["journal"] = journal
        tid = self.ok("tache", entree=e)["id"]
        return next(t for t in self.suivi()["taches"] if t["id"] == tid)

    def donne(self, t):
        (texte,) = regles._consigne_de_l_apk_existant(self.projet, t)
        return texte

    def test_une_correction_qui_cite_client_recoit_l_apk_client_meme_si_le_maitre_est_plus_recent(self):
        texte = self.donne(self.tache("Vérification : correction « APK Client sans adresse du service »"))
        self.assertIn(CLIENT, texte)
        self.assertNotIn(MAITRE, texte)

    def test_l_apk_rapatrie_par_une_tache_de_la_meme_fonctionnalite_l_emporte(self):
        self.tache("Livraison de la correction", journal=[f"Livrable rapatrié : {CLIENT} (12 Mo)"], fait=True)
        texte = self.donne(self.tache("Vérification de la correction"))           # rien ne nomme la variante
        self.assertIn(CLIENT, texte)
        self.assertNotIn(MAITRE, texte)

    def test_le_rapatrie_l_emporte_meme_sur_le_texte(self):
        self.tache("Livraison", journal=[f"Livrable rapatrié : {CLIENT} (12 Mo)"], fait=True)
        texte = self.donne(self.tache("Vérification de l'APK Maître"))
        self.assertIn(CLIENT, texte)

    def test_aucune_regle_ne_tranche_la_consigne_liste_les_candidats_et_n_en_impose_pas(self):
        texte = self.donne(self.tache("Vérification de la correction"))
        self.assertIn(CLIENT, texte)
        self.assertIn(MAITRE, texte)
        self.assertIn("apk_utilise", texte)
        self.assertNotIn("NE construis PAS d'APK et", texte)
        self.assertFalse((self.d / ".factory" / registre_apk.NOM_DEMANDES).exists())

    def test_une_seule_variante_connue_est_donnee(self):
        (self.d / ".factory" / registre_apk.NOM_REGISTRE).write_text(json.dumps(
            [x for x in registre_apk.lire(str(self.d)) if x["variante"] == "client"]), encoding="utf-8")
        self.assertIn(CLIENT, self.donne(self.tache("Vérification de la correction")))

    def test_deux_variantes_sans_apk_a_jour_et_sans_regle_aucune_construction_imposee(self):
        self.ecrire(f"{APP}/lib/main.dart", "void main() { nouveau(); }\n")
        self.valider("code")
        texte = self.donne(self.tache("Vérification de la correction"))
        self.assertIn("Variantes connues", texte)
        self.assertFalse((self.d / ".factory" / registre_apk.NOM_DEMANDES).exists())

    def test_deux_variantes_nommees_restent_ambigues(self):
        texte = self.donne(self.tache("Vérification client et maitre"))
        self.assertIn(CLIENT, texte)
        self.assertIn(MAITRE, texte)


class Rapport(unittest.TestCase):
    def test_apk_utilise_est_valide_ou_ecarte(self):
        bon = {"variante": "client", "empreinte": "ab12", "date": "2026-11-27T04:00:00Z"}
        self.assertEqual(rapport.lire('```json\n' + json.dumps({"statut": "fait", "apk_utilise": bon}) + '\n```')["apk_utilise"], bon)
        self.assertNotIn("apk_utilise", rapport.lire('```json\n{"statut": "fait", "apk_utilise": {"variante": "x"}}\n```'))
        self.assertNotIn("apk_utilise", rapport.lire('```json\n{"statut": "fait", "apk_utilise": "oui"}\n```'))


if __name__ == "__main__":
    unittest.main()
