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


class FauxAuto(FauxModule):
    def __init__(self, auto=True, cache=None):
        super().__init__()
        self.auto, self.cache = auto, cache or {}

    def identifiant(self, dossier):
        return "demo"

    def lire_auto(self):
        return {"demo": True} if self.auto else {}

    def lire_cache(self):
        return self.cache


class DeploiementAutomatique(unittest.TestCase):
    """La case « Déployer automatiquement à chaque modification » : un commit neuf part sans demander."""
    COMMIT, AUTRE = "a" * 40, "b" * 40

    def projet(self):
        d = tempfile.mkdtemp()
        (Path(d) / ".factory").mkdir()
        (Path(d) / ".factory" / "service.json").write_text("{}", "utf-8")
        service_permanent._DERNIERE.clear()
        service_permanent.ESSAIS.clear()
        return d

    def lancer(self, d, m, commit, t=1000, appels=None):
        faits = [] if appels is None else appels
        return service_permanent.deployer_si_modifie(
            d, t, module=m, commit_du_depot=lambda _: commit, declencher_=lambda dossier, annoncer=None: faits.append(dossier) or "lancé"), faits

    def test_case_decochee_rien(self):
        d = self.projet()
        ligne, faits = self.lancer(d, FauxAuto(auto=False), self.COMMIT)
        self.assertEqual((ligne, faits), (None, []))

    def test_commit_neuf_deploye_puis_pas_deux_fois(self):
        d = self.projet()
        m = FauxAuto(cache={"demo": {"etat": {"commit": self.AUTRE, "etat": "actif"}}})
        ligne, faits = self.lancer(d, m, self.COMMIT)
        self.assertIn("Déploiement automatique", ligne)
        self.assertEqual(len(faits), 1)
        ligne, faits = self.lancer(d, m, self.COMMIT, t=1000 + 500, appels=faits)       # même commit, déjà essayé
        self.assertEqual((ligne, len(faits)), (None, 1))
        ligne, faits = self.lancer(d, m, self.AUTRE[::-1].replace("b", "c"), t=1000 + 1000, appels=faits)   # un nouveau commit relance
        self.assertEqual(len(faits), 2)

    def test_deja_au_commit_du_serveur_ou_en_cours_rien(self):
        d = self.projet()
        a_jour = FauxAuto(cache={"demo": {"etat": {"commit": self.COMMIT, "etat": "actif"}}})
        self.assertEqual(self.lancer(d, a_jour, self.COMMIT)[1], [])
        d = self.projet()
        en_cours = FauxAuto(cache={"demo": {"deploiement": {"statut": "en_cours"}, "etat": {"commit": self.AUTRE}}})
        self.assertEqual(self.lancer(d, en_cours, self.COMMIT)[1], [])

    def test_un_en_cours_abandonne_ne_bloque_plus_les_deploiements(self):
        """Le moteur redémarré pendant un déploiement laisse « en_cours » : passé la durée maximale, un nouveau commit repart."""
        from datetime import datetime, timezone
        epoch = lambda iso: datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        cache = {"demo": {"deploiement": {"statut": "en_cours", "debut": "2026-11-26T09:24:39Z", "commit": "x"},
                          "etat": {"commit": self.AUTRE, "etat": "actif"}}}
        d = self.projet()
        recent = self.lancer(d, FauxAuto(cache=cache), self.COMMIT, t=epoch("2026-11-26T09:40:00Z"))
        self.assertEqual(recent[1], [])                                            # 15 minutes : il tourne peut-être encore
        d = self.projet()
        perime = self.lancer(d, FauxAuto(cache=cache), self.COMMIT, t=epoch("2026-11-26T10:50:00Z"))
        self.assertEqual(len(perime[1]), 1)                                        # 1 h 25 : abandonné

    def test_au_plus_une_verification_toutes_les_deux_minutes(self):
        d = self.projet()
        m = FauxAuto()
        self.assertEqual(len(self.lancer(d, m, None, t=1000)[1]), 0)                    # pas de commit lisible
        self.assertIsNone(service_permanent.deployer_si_modifie(d, 1050, module=m, commit_du_depot=lambda _: self.COMMIT,
                                                                declencher_=lambda *a, **k: "x"))


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
