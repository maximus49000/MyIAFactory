"""Déploiement automatique du service permanent après une livraison validée (`moteur/service_permanent.py`) et la
demande « Déployer et installer » qui cite l'outil (`moteur/deploiement.py`). Aucun serveur : le déploiement est un faux."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from moteur import deploiement, regles, service_permanent
from tests import test_moteur_regles as tmr


class FauxModule:
    ACTION = "service"

    def __init__(self, service=True):
        self.service = service
        self.appels = []
        self.lache = threading.Event()

    def a_un_service(self, dossier):
        return self.service

    def deployer(self, dossier):
        self.appels.append(dossier)
        self.lache.wait(5)
        return 0, {"statut": "ok"}


class Declencher(unittest.TestCase):
    def test_sans_service_rien(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(service_permanent.declencher(d))          # pas de .factory/service.json : rien chargé

    def test_sans_accord_dit_pourquoi_et_ne_deploie_pas(self):
        m = FauxModule()
        ligne = service_permanent.declencher("C:/projet", module=m, refus=lambda d, mod: "pas réglé sur serveur")
        self.assertIn("pas réglé sur serveur", ligne)
        self.assertEqual(m.appels, [])

    def test_avec_accord_un_seul_fil_par_projet(self):
        m = FauxModule()
        with tempfile.TemporaryDirectory() as d:
            l1 = service_permanent.declencher(d, module=m, refus=lambda *_: None)
            l2 = service_permanent.declencher(d, module=m, refus=lambda *_: None)
            self.assertIn("lancé", l1)
            self.assertIn("déjà en cours", l2)
            m.lache.set()
            service_permanent._EN_VOL[str(Path(d).resolve())].join(5)
        self.assertEqual(len(m.appels), 1)

    def test_synchrone(self):
        m = FauxModule()
        m.lache.set()
        with tempfile.TemporaryDirectory() as d:
            ligne = service_permanent.declencher(d, synchrone=True, module=m, refus=lambda *_: None)
        self.assertIn("fait", ligne)
        self.assertEqual(len(m.appels), 1)

    def test_l_adresse_est_annoncee_apres_le_deploiement(self):
        m = FauxModule()
        m.lache.set()
        dit = []
        m.deployer = lambda dossier: (0, {"statut": "ok", "adresse": "http://exemple.test:18001", "detail": "Service déployé."})
        with tempfile.TemporaryDirectory() as d:
            service_permanent.declencher(d, synchrone=True, module=m, refus=lambda *_: None, annoncer=dit.append)
        self.assertEqual(len(dit), 1)
        self.assertIn("est en ligne : http://exemple.test:18001", dit[0])
        self.assertIn("zone « Services »", dit[0])

    def test_annonce_retour_arriere_et_echec_sans_jeton(self):
        a = service_permanent.annonce((1, {"statut": "retour_arriere", "adresse": "http://exemple.test:18001",
                                           "detail": "Santé refusée."}))
        self.assertIn("retour automatique", a)
        self.assertIn("Santé refusée.", a)
        b = service_permanent.annonce((1, {"statut": "echec", "detail": "Serveur injoignable."}))
        self.assertIn("n'a pas pu être déployé : Serveur injoignable.", b)
        self.assertIn("résultat lisible", service_permanent.annonce(None))

    def test_une_annonce_qui_echoue_n_arrete_rien(self):
        m = FauxModule()
        m.lache.set()

        def casse(_):
            raise RuntimeError("discussion fermée")
        with tempfile.TemporaryDirectory() as d:
            ligne = service_permanent.declencher(d, synchrone=True, module=m, refus=lambda *_: None, annoncer=casse)
        self.assertIn("fait", ligne)

    def test_une_panne_n_arrete_rien(self):
        def refus(*_):
            raise OSError("disque")
        self.assertIn("impossible", service_permanent.declencher("x", module=FauxModule(), refus=refus))


class DemandeDeDeploiement(unittest.TestCase):
    def test_la_demande_cite_l_outil_et_interdit_le_deploiement_a_la_main(self):
        texte = deploiement.demande({"nom": "Serveur de données"}, [deploiement.LIBELLE_SERVEUR])
        for attendu in (".factory/service.json", "deporter service etat", "docs/serveur-services.md",
                        "Tu ne déploies jamais toi-même", "zone Services"):
            self.assertIn(attendu, texte)


class FinDeLivraison(tmr.Base):
    def test_une_livraison_faite_declenche_le_service(self):
        t = {"id": "t-inexistante", "etape": "flux:f1-livraison", "fonctionnalite": "f1"}
        with mock.patch.object(regles.service_permanent, "declencher", return_value="Service permanent : lancé.") as d:
            regles._deployer_le_service(self.projet, t, {"statut": "fait"})
        d.assert_called_once()
        self.assertEqual(d.call_args.args, (self.projet.dossier,))
        self.assertTrue(callable(d.call_args.kwargs["annoncer"]))      # l'annonce va à la discussion de la fonctionnalité

    def test_une_livraison_en_echec_ou_une_autre_etape_ne_declenche_rien(self):
        with mock.patch.object(regles.service_permanent, "declencher") as d:
            regles._deployer_le_service(self.projet, {"id": "x", "etape": "flux:f1-livraison", "fonctionnalite": "f1"},
                                        {"statut": "echec"})
            regles._deployer_le_service(self.projet, {"id": "x", "etape": "relecture", "fonctionnalite": "f1"},
                                        {"statut": "fait"})
        d.assert_not_called()


if __name__ == "__main__":
    unittest.main()
