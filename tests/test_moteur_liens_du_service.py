"""Une validation d'un élément qui concerne le SERVICE (pages, graphiques, catalogue) donne des adresses cliquables du service en
ligne, jamais un APK (FM_Stats d128, f33 : « ce n'est pas l'APK qui permettra de vérifier »)."""
import json
import unittest
from unittest import mock

from moteur import regles
from orchestrateur import factory as fa
from tests import test_moteur_registre_apk as reg

BASE = "https://service.exemple"
FAITS = {"commit": "2b0ad4a" + "0" * 33, "etat": "actif", "sante_ok": True, "secrets": {}, "journal": [],
         "pages": [{"chemin": "/sante", "code": 200, "ms": 12}, {"chemin": "/equipe/77", "code": 200, "ms": 20},
                   {"chemin": "/catalogue.json", "code": 200, "ms": 9}], "erreur": None}


class Fiche(reg.Depot):
    def setUp(self):
        super().setUp()
        self.etat = regles.nouvel_etat()
        self.statut = mock.patch.object(regles.service_permanent, "statut_du_serveur", return_value=("a_jour", "ok")).start()
        self.addCleanup(mock.patch.stopall)
        for p in (mock.patch.object(regles, "_adresse_du_service", return_value=BASE),
                  mock.patch.object(regles.service_permanent, "faits_du_service", return_value=dict(FAITS)),
                  mock.patch.object(regles.service_permanent, "_commit_du_depot", return_value="a" * 40)):
            p.start()
            self.addCleanup(p.stop)

    def element(self, eid, nom, *fichiers):
        tid = self.ok("tache", entree={"titre": f"Dev {eid}", "fonctionnalite": "f1", "role": "dev", "etape": "flux:dev",
                                       "colonne": "fait", "active": False, "element": eid})["id"]
        self.git("checkout", "-q", "-b", f"agent/{tid}")
        for f in fichiers:
            self.ecrire(f, f"contenu {f}\n")
        self.git("add", "--", *fichiers)
        self.git("commit", "-q", "-m", f"travail {eid}")
        self.git("checkout", "-q", "main")
        self.ecrire("docs/rapport.md", "Rapport.\n")
        v = {"fid": "f1", "element": {"id": eid, "nom": nom}, "taches": [tid], "phase": "flux", "pas": 2, "corrections": 0,
             "tour": 0, "rapports": [[]], "points": [], "attendus": 0,
             "dernier_rapport": {"compte_rendu": "Fait.", "doit_marcher": "La page équipe 77 répond sur /equipe/77.",
                                 "fichiers": [{"chemin": "docs/rapport.md", "titre": "Le rapport"},
                                              {"chemin": f"{reg.APP}/build/app-maitre-release.apk", "titre": "L'APK Maître"}],
                                 "points": ["La page équipe 77 s'ouvre", "Le graphique SVG s'affiche"]}}
        self.etat["elements"][f"f1/{eid}"] = v
        return v

    def poser(self, v):
        self.ecrire(f"{reg.APP}/build/app-maitre-release.apk", "APK")
        s = {"id": "valider", "nom": "Validation du Directeur", "validation": True}
        with mock.patch.object(regles, "_projet_flutter", return_value=True):
            regles._attendre_le_directeur(self.projet, self.etat, v, s)
        (d,) = [x for x in self.ok("etat")["decisions"] if x["genre"] == "valider_etape"]
        return d

    def chemins(self, d):
        return [f["chemin"] for f in d.get("fichiers") or []]

    def test_un_element_du_service_a_des_liens_cliquables_et_pas_d_apk(self):
        d = self.poser(self.element("e1", "Pages et graphiques publics", "serveur/pages.py", "serveur/graphiques.py"))
        adresses = [x["adresse"] for x in d["liens"]]
        self.assertEqual(adresses[:2], [BASE + "/", BASE + "/sante"])
        self.assertIn(BASE + "/equipe/77", adresses)                       # la page citée par l'élément
        self.assertTrue(all(a.startswith("https://") for a in adresses))
        self.assertEqual(self.chemins(d), ["docs/rapport.md"])           # plus d'APK à valider
        self.assertEqual((d["service"]["pret"], d["service"]["commit"][:7]), (True, "2b0ad4a"))
        self.assertEqual(d["acces"]["url"], BASE + "/")

    def test_un_element_application_est_valide_comme_avant(self):
        d = self.poser(self.element("e1", "Écran des équipes", f"{reg.APP}/lib/equipes.dart"))
        self.assertNotIn("liens", d)
        self.assertNotIn("service", d)
        self.assertIn(f"{reg.APP}/build/app-maitre-release.apk", self.chemins(d))      # l'APK reste à valider

    def test_les_chemins_d_exemple_du_projet_s_ajoutent_aux_liens(self):
        chemin = self.factory
        f = json.loads(chemin.read_text(encoding="utf-8"))
        f["liens_publics"] = [{"libelle": "Catalogue public", "chemin": "/catalogue.json"}]
        chemin.write_text(json.dumps(f), encoding="utf-8")
        d = self.poser(self.element("e1", "Pages publiques", "serveur/pages.py"))
        self.assertIn({"libelle": "Catalogue public", "adresse": BASE + "/catalogue.json"}, d["liens"])

    def test_liens_publics_est_valide(self):
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        for mauvais in ("x", [{"libelle": "a", "chemin": "https://x.exemple/y"}], [{"libelle": "a", "chemin": "/../x"}],
                        [{"libelle": "", "chemin": "/x"}], [{"libelle": "a", "chemin": "/x"}] * 9):
            f["liens_publics"] = mauvais
            self.factory.write_text(json.dumps(f), encoding="utf-8")
            with self.assertRaises(fa.FactoryInvalide):
                fa.lire(self.factory)

    def test_sans_adresse_du_service_rien_n_est_invente(self):
        with mock.patch.object(regles, "_adresse_du_service", return_value=None):
            d = self.poser(self.element("e1", "Pages publiques", "serveur/pages.py"))
        self.assertNotIn("liens", d)

    def test_jamais_de_jeton_dans_les_liens(self):
        d = self.poser(self.element("e1", "Pages publiques", "serveur/pages.py"))
        self.assertNotIn("jeton", json.dumps(d["liens"]).lower())


class ValidationPossible(Fiche):
    """Une validation n'est demandée que lorsqu'elle est possible : service chargé, prêt, liens donnés (décision du Directeur)."""

    def decisions(self):
        return [x for x in self.ok("etat")["decisions"] if x["genre"] == "valider_etape"]

    def paroles(self):
        return [m["texte"] for m in self.suivi()["fonctionnalites"][0]["discussion"] if m["auteur"] == "chef"]

    def poser_sans_fiche(self, v):
        self.ecrire(f"{reg.APP}/build/app-maitre-release.apk", "APK")
        with mock.patch.object(regles, "_projet_flutter", return_value=True):
            regles._attendre_le_directeur(self.projet, self.etat, v, {"id": "valider", "nom": "Validation", "validation": True})

    def test_le_commit_deploye_ancien_aucune_validation_et_le_deploiement_est_demande(self):
        self.statut.return_value = ("attente", "le service n'a pas encore cette version")
        v = self.element("e1", "Pages publiques", "serveur/pages.py")
        with mock.patch.object(regles.service_permanent, "declencher", return_value="Service permanent : lancé.") as declencher:
            self.poser_sans_fiche(v)
            self.poser_sans_fiche(v)
        self.assertEqual(self.decisions(), [])
        self.assertEqual(v["phase"], "attente_service")
        declencher.assert_called_once()                                   # une seule demande de déploiement
        self.assertEqual(len([p for p in self.paroles() if "n'est pas demandée tout de suite" in p]), 1)

    def test_service_503_aucune_validation(self):
        faits = dict(FAITS, pages=[{"chemin": "/sante", "code": 200}, {"chemin": "/equipe/77", "code": 503}])
        v = self.element("e1", "Pages publiques", "serveur/pages.py")
        with mock.patch.object(regles.service_permanent, "faits_du_service", return_value=faits):
            self.poser_sans_fiche(v)
        self.assertEqual((self.decisions(), v["phase"]), ([], "attente_service"))
        self.assertIn("index en préparation", v["attente_service"]["manque"])

    def test_tout_pret_la_validation_est_posee_avec_les_liens(self):
        v = self.element("e1", "Pages publiques", "serveur/pages.py")
        self.poser_sans_fiche(v)
        (d,) = self.decisions()
        self.assertTrue(d["liens"])

    def test_apres_un_redemarrage_une_validation_deja_posee_est_aussi_retiree(self):
        v = self.element("e1", "Pages publiques", "serveur/pages.py")
        self.poser_sans_fiche(v)
        self.etat = regles.nouvel_etat()                                      # le moteur relancé : plus rien en mémoire
        faits503 = dict(FAITS, pages=[{"chemin": "/sante", "code": 503}, {"chemin": "/equipe/77", "code": 503}])
        with mock.patch.object(regles.service_permanent, "faits_du_service", return_value=faits503),                 mock.patch.object(regles, "_projet_flutter", return_value=True):
            regles.attendre_le_service(self.projet, self.etat)
        self.assertEqual(self.decisions(), [])

    def test_un_element_application_n_attend_pas_le_service(self):
        self.statut.return_value = ("attente", "x")
        v = self.element("e1", "Écran des équipes", f"{reg.APP}/lib/equipes.dart")
        self.poser_sans_fiche(v)
        self.assertEqual(len(self.decisions()), 1)

    def test_apres_l_attente_la_validation_est_posee_une_fois_le_service_pret(self):
        self.statut.return_value = ("attente", "x")
        v = self.element("e1", "Pages publiques", "serveur/pages.py")
        with mock.patch.object(regles.service_permanent, "declencher", return_value=None):
            self.poser_sans_fiche(v)
        self.assertEqual(self.decisions(), [])
        self.statut.return_value = ("a_jour", "ok")                        # le service est chargé
        v["attente_service"]["dernier"] = 0
        regles.attendre_le_service(self.projet, self.etat)
        self.assertEqual(len(self.decisions()), 1)
        self.assertEqual(v["phase"], "validation")

    def test_un_service_toujours_pas_pret_apres_le_delai_ouvre_une_anomalie_qui_dit_laquelle_manque(self):
        self.statut.return_value = ("attente", "x")
        v = self.element("e1", "Pages publiques", "serveur/pages.py")
        with mock.patch.object(regles.service_permanent, "declencher", return_value=None):
            self.poser_sans_fiche(v)
            v["attente_service"].update(dernier=0, depuis=0)
            regles.attendre_le_service(self.projet, self.etat)
            v["attente_service"]["dernier"] = 0
            regles.attendre_le_service(self.projet, self.etat)
        (a,) = self.ok("anomalies")["anomalies"]
        self.assertIn("Validation en attente du service", a["titre"])
        self.assertIn("n'a pas encore la version", a["description"])
        self.assertEqual(self.decisions(), [])                                # jamais une validation vide

    def test_une_validation_deja_posee_devenue_impossible_est_retiree_puis_rouverte(self):
        v = self.element("e1", "Pages publiques", "serveur/pages.py")
        self.poser_sans_fiche(v)
        (d,) = self.decisions()
        faits503 = dict(FAITS, pages=[{"chemin": "/sante", "code": 200}, {"chemin": "/equipe/77", "code": 503}])
        with mock.patch.object(regles.service_permanent, "faits_du_service", return_value=faits503):
            regles.attendre_le_service(self.projet, self.etat)
        self.assertEqual(self.decisions(), [])                                # retirée
        self.assertEqual(v["phase"], "attente_service")
        self.assertEqual(v["tache_retiree"], d["tache"])                       # sa tâche est gardée, pas doublée
        v["attente_service"]["dernier"] = 0
        regles.attendre_le_service(self.projet, self.etat)                    # le service répond de nouveau
        (rouverte,) = self.decisions()
        self.assertEqual(rouverte["tache"], d["tache"])
        validations = [t for t in self.suivi()["taches"] if str(t.get("etape")).startswith("validation")]
        self.assertEqual(len(validations), 1)


class BriefDeLaVerification(reg.Depot):
    def tache(self, titre):
        tid = self.ok("tache", entree={"titre": titre, "fonctionnalite": "f1", "role": "testeur", "etape": "flux:essai",
                                       "colonne": "essai", "active": False})["id"]
        return next(t for t in self.suivi()["taches"] if t["id"] == tid)

    def test_le_testeur_recoit_l_adresse_du_service_et_les_pages_sans_jeton(self):
        etat = regles.nouvel_etat()
        tid = self.ok("tache", entree={"titre": "Dev pages", "fonctionnalite": "f1", "role": "dev", "etape": "flux:dev",
                                       "colonne": "fait", "active": False})["id"]
        self.git("checkout", "-q", "-b", f"agent/{tid}")
        self.ecrire("serveur/pages.py", "x\n")
        self.git("add", "--", "serveur/pages.py")
        self.git("commit", "-q", "-m", "pages")
        self.git("checkout", "-q", "main")
        t = self.tache("Vérification des pages publiques (/equipe/77)")
        etat["elements"]["f1/e1"] = {"fid": "f1", "element": {"id": "e1", "nom": "Pages publiques"}, "taches": [tid]}
        t["element"] = "e1"
        with mock.patch.object(regles, "_projet_flutter", return_value=True), \
                mock.patch.object(regles, "_adresse_du_service", return_value=BASE), \
                mock.patch.object(regles.service_permanent, "faits_du_service", return_value=dict(FAITS)):
            (texte,) = regles._consigne_du_service_en_ligne(self.projet, etat, t)
        self.assertIn(BASE + "/sante", texte)
        self.assertIn("EN LIGNE", texte)
        self.assertIn("jamais de jeton", texte)
        self.assertIn("Commit déployé : 2b0ad4a", texte)

    def test_hors_service_rien_n_est_ajoute(self):
        with mock.patch.object(regles, "_adresse_du_service", return_value=BASE):
            self.assertEqual(regles._consigne_du_service_en_ligne(self.projet, regles.nouvel_etat(),
                                                                  self.tache("Vérification de l'écran")), [])


if __name__ == "__main__":
    unittest.main()
