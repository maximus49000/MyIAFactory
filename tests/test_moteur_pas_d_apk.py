"""Un APK n'est construit que si l'évolution en a besoin (règle du Directeur, 2026-11-27 ; FM_Stats t296 : une correction
purement serveur construisait un APK Flutter de 8 à 14 minutes)."""
import json
import subprocess
import unittest
from unittest import mock

from moteur import apk_besoin as ab
from moteur import regles
from orchestrateur import factory as fa
from tests import test_moteur_serie_reprise as tsr

APP = "android_app"


class Fichiers(unittest.TestCase):
    def touche(self, *fichiers, app=APP, motifs=ab.IGNORE_PAR_DEFAUT):
        return ab.touche_l_application(app, list(fichiers), motifs)

    def test_le_serveur_la_documentation_et_les_scripts_ne_changent_pas_l_apk(self):
        self.assertFalse(self.touche("serveur/app.py", "serveur/tests/test_x.py", "docs/TECHNIQUE.md", ".factory/x.json",
                                     "scripts/copier_docs_t4.py", "README.md"))

    def test_le_code_et_la_configuration_de_l_application_le_changent(self):
        for f in (f"{APP}/lib/main.dart", f"{APP}/pubspec.yaml", f"{APP}/android/app/build.gradle",
                  f"{APP}/assets/images/logo.png"):
            self.assertTrue(self.touche(f), f)

    def test_les_tests_de_l_application_ne_changent_pas_l_apk(self):
        self.assertFalse(self.touche(f"{APP}/test/synchro_test.dart", f"{APP}/integration_test/x_test.dart"))

    def test_les_copies_de_documents_embarquees_ne_declenchent_pas_un_apk_a_elles_seules(self):
        self.assertFalse(self.touche(f"{APP}/assets/docs/CHANGELOG.md", f"{APP}/assets/docs/release_notes.json"))
        self.assertTrue(self.touche(f"{APP}/assets/docs/CHANGELOG.md", f"{APP}/lib/main.dart"))        # le code, lui, compte

    def test_les_motifs_du_projet_remplacent_le_defaut(self):
        self.assertFalse(self.touche(f"{APP}/lib/generated/x.dart", motifs=[f"{APP}/lib/generated/**"]))
        self.assertTrue(self.touche(f"{APP}/assets/docs/CHANGELOG.json", motifs=[]))      # liste vide : rien d'ignoré

    def test_application_a_la_racine(self):
        self.assertFalse(self.touche("serveur/app.py", "docs/a.txt", "tests/t.py", app="."))
        self.assertTrue(self.touche("lib/main.dart", app="."))
        self.assertFalse(self.touche("assets/docs/x.json", app="."))


class Reglage(tsr.AvecValidation):
    def test_apk_ignore_est_valide_et_rendu_par_la_factory(self):
        chemin = self.factory
        d = json.loads(chemin.read_text(encoding="utf-8"))
        d["apk_ignore"] = ["**/generated/**"]
        chemin.write_text(json.dumps(d), encoding="utf-8")
        self.assertEqual(fa.lire(chemin)["apk_ignore"], ["**/generated/**"])
        d["apk_ignore"] = "pas une liste"
        chemin.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaises(fa.FactoryInvalide):
            fa.lire(chemin)
        del d["apk_ignore"]
        chemin.write_text(json.dumps(d), encoding="utf-8")
        self.assertNotIn("apk_ignore", fa.lire(chemin))      # absent : le défaut du moteur


class Livraison(tsr.AvecValidation):
    def setUp(self):
        super().setUp()
        self.projet_avec_validation(flux=tsr.FLUX, elements=0)
        self.d = self.projet.dossier
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "x@x")
        self.git("config", "user.name", "x")
        (self.d / APP).mkdir()
        (self.d / APP / "pubspec.yaml").write_text("name: app\ndependencies:\n  flutter:\n    sdk: flutter\n", encoding="utf-8")
        self.git("add", f"{APP}/pubspec.yaml")      # jamais les fichiers d'état du projet (suivi…) : ils changent de branche
        self.git("commit", "-q", "-m", "base")
        self.etat = regles.nouvel_etat()
        for patch in (mock.patch.object(regles.service_permanent, "statut_du_serveur", return_value=("sans_service", "")),
                      mock.patch.object(regles.service_permanent, "_commit_du_depot", return_value="a" * 40)):
            patch.start()
            self.addCleanup(patch.stop)

    def git(self, *a):
        return subprocess.run(["git", "-C", str(self.d), *a], capture_output=True, check=True)

    def element(self, eid, *fichiers):
        """Un élément conforme qui attend la livraison, dont la tâche de dev a commité `fichiers` sur agent/<tâche>."""
        tid = self.ok("tache", entree={"titre": f"Dev {eid}", "fonctionnalite": "f1", "role": "dev", "etape": "flux:dev",
                                       "colonne": "fait", "active": False})["id"]
        self.git("checkout", "-q", "-b", f"agent/{tid}")
        for f in fichiers:
            (self.d / f).parent.mkdir(parents=True, exist_ok=True)
            (self.d / f).write_text(f"contenu de {f}\n", encoding="utf-8")
        self.git("add", "--", *fichiers)
        self.git("commit", "-q", "-m", f"travail {eid}")
        self.git("checkout", "-q", "main")
        v = {"fid": "f1", "element": {"id": eid, "nom": f"Élément {eid}"}, "taches": [tid], "phase": regles.A_LIVRER,
             "pas": 4, "corrections": 0, "tour": 0, "rapports": [[]], "points": [], "attendus": 0}
        self.etat["elements"][f"f1/{eid}"] = v
        return v

    def taches_de_livraison(self):
        return [t for t in self.suivi()["taches"] if str(t.get("etape")) == "flux:livraison"]

    def paroles(self):
        return [m["texte"] for m in self.suivi()["fonctionnalites"][0]["discussion"] if m["auteur"] == "chef"]

    def livrer(self, flutter=True):
        with mock.patch.object(regles, "_projet_flutter", return_value=flutter):
            return regles.livrer_si_calme(self.projet, self.etat, force=True)

    def journal(self, v):
        return json.dumps(self.la(v["taches"][-1])["journal"], ensure_ascii=False)

    def la(self, tid):
        return next(t for t in self.suivi()["taches"] if t["id"] == tid)

    def test_un_element_serveur_seul_n_a_pas_de_livraison_d_apk(self):
        v = self.element("e1", "serveur/routes.py", "serveur/tests/test_routes.py")
        self.livrer()
        self.assertEqual(self.taches_de_livraison(), [])
        self.assertEqual(v["phase"], "fait")
        self.assertIn("Aucun APK à livrer : l'élément ne touche pas l'application", self.journal(v))
        self.assertIn("serveur/routes.py", self.journal(v))
        self.assertTrue(any("je ne construis pas d'APK" in p for p in self.paroles()))

    def test_un_element_documentation_seule_n_a_pas_d_apk(self):
        v = self.element("e1", "docs/TECHNIQUE.md", f"{APP}/assets/docs/TECHNIQUE.md")
        self.livrer()
        self.assertEqual((self.taches_de_livraison(), v["phase"]), ([], "fait"))

    def test_un_element_avec_du_code_flutter_est_livre_par_un_apk_comme_avant(self):
        v = self.element("e1", f"{APP}/lib/main.dart")
        self.livrer()
        self.assertEqual(len(self.taches_de_livraison()), 1)
        self.assertEqual(v["phase"], "flux")

    def test_un_lot_mixte_ne_construit_qu_un_apk_pour_l_element_qui_le_touche(self):
        serveur = self.element("e1", "serveur/routes.py")
        appli = self.element("e2", f"{APP}/lib/main.dart")
        self.livrer()
        (livraison,) = self.taches_de_livraison()
        self.assertEqual(serveur["phase"], "fait")
        self.assertEqual(appli["lot_livraison"], ["f1/e2"])
        self.assertIn(appli["element"]["nom"], livraison["titre"])

    def test_un_lot_sans_element_qui_touche_l_application_ne_construit_rien(self):
        self.element("e1", "serveur/routes.py")
        self.element("e2", "docs/a.md")
        self.assertTrue(self.livrer())
        self.assertEqual(self.taches_de_livraison(), [])

    def test_les_motifs_apk_ignore_du_projet_sont_respectes(self):
        v = self.element("e1", f"{APP}/lib/generated/x.dart")
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d["apk_ignore"] = [f"{APP}/lib/generated/**"]
        self.factory.write_text(json.dumps(d), encoding="utf-8")
        self.livrer()
        self.assertEqual((self.taches_de_livraison(), v["phase"]), ([], "fait"))

    def test_un_projet_sans_flutter_est_inchange(self):
        v = self.element("e1", "serveur/routes.py")
        self.livrer(flutter=False)
        self.assertEqual(len(self.taches_de_livraison()), 1)
        self.assertEqual(v["phase"], "flux")

    def test_des_fichiers_inconnus_gardent_l_apk(self):
        v = self.element("e1", "serveur/routes.py")
        v["taches"] = []                                       # le moteur relancé : plus de tâches connues
        self.livrer()
        self.assertEqual(len(self.taches_de_livraison()), 1)

    def test_le_service_est_redeploye_quand_il_n_a_pas_la_version(self):
        v = self.element("e1", "serveur/routes.py")
        with mock.patch.object(regles.service_permanent, "statut_du_serveur", return_value=("attente", "pas encore")), \
                mock.patch.object(regles.service_permanent, "declencher", return_value="lancé") as declencher:
            self.livrer()
        declencher.assert_called_once()
        self.assertEqual(self.taches_de_livraison(), [])

    def test_une_branche_fusionnee_est_lue_par_son_commit_de_fusion(self):
        v = self.element("e1", "serveur/routes.py")
        branche = f"agent/{v['taches'][0]}"
        self.git("merge", "--no-ff", "-q", "-m", f"Factory : fusion de {branche}", branche)
        self.livrer()
        self.assertEqual((self.taches_de_livraison(), v["phase"]), ([], "fait"))
        self.assertIn("serveur/routes.py", self.journal(v))

    def test_l_avis_de_fin_dit_pas_d_apk_et_donne_le_lien_du_service(self):
        self.element("e1", "serveur/routes.py")
        self.livrer()
        with mock.patch.object(regles, "_adresse_du_service", return_value="https://service.exemple"):
            regles._fin_de_fonctionnalite(self.projet, self.etat, "f1")
        fin = self.suivi()["fonctionnalites"][0]["fin"]
        self.assertEqual(fin["livrables"], [])
        self.assertEqual(fin["acces"]["url"], "https://service.exemple")
        self.assertIn("Pas d'APK", fin["acces"]["description"])


if __name__ == "__main__":
    unittest.main()
