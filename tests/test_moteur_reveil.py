"""Le réveil du moteur (une demande posée par le bureau est traitée tout de suite) et une seule mesure de charge par tour.
Aucun appel réel, aucune vraie mesure de charge."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from bureau import attente
from moteur import boucle, regles
from tests.orch_aide import factory_minimale
from tests.test_moteur_boucle import Agents, Appels, Base


class Reveil(Base):
    def test_un_reveil_fait_traiter_la_demande_pendant_l_attente(self):
        self.moteur.tour()                                   # le projet est démarré
        i = self.demande(type="bouton", id="exporter")
        self.assertEqual(self.statut(i)["statut"], "en attente")
        attente.reveiller(self.dossier)                      # ce que fait le bureau après avoir posé la demande
        debut = time.monotonic()
        self.moteur.attendre(threading.Event(), 0.6)
        self.assertEqual(self.statut(i)["statut"], "traitée")
        self.assertLess(self.moteur.duree_dernier_tour_s, 5)
        self.assertGreaterEqual(time.monotonic() - debut, 0.5)      # l'attente a tenu sa durée

    def test_sans_reveil_la_demande_attend_le_tour_suivant(self):
        self.moteur.tour()
        i = self.demande(type="bouton", id="exporter")
        self.moteur.attendre(threading.Event(), 0.5)
        self.assertEqual(self.statut(i)["statut"], "en attente")
        self.moteur.tour()
        self.assertEqual(self.statut(i)["statut"], "traitée")

    def test_pas_de_double_traitement(self):
        self.moteur.tour()
        self.demande(type="bouton", id="exporter")
        attente.reveiller(self.dossier)
        vrai = regles.traiter_demande
        with mock.patch.object(regles, "traiter_demande", side_effect=vrai) as m:
            self.moteur.attendre(threading.Event(), 0.5)
            self.moteur.tour()
            attente.reveiller(self.dossier)                  # un second réveil sans nouvelle demande ne rejoue rien
            self.moteur.attendre(threading.Event(), 0.5)
            self.moteur.tour()
        self.assertEqual(m.call_count, 1)

    def test_un_reveil_ne_traite_que_les_demandes_du_projet_signale(self):
        with tempfile.TemporaryDirectory() as autre_dossier:
            autre = Path(autre_dossier)
            factory_b = factory_minimale(autre)
            projet_b = regles.Projet(factory_b, feu_vert=lambda: True)
            moteur = self.fabriquer([self.projet, projet_b])
            moteur.tour()
            a = self.demande(type="bouton", id="exporter")
            b = self.demande(factory=factory_b, type="bouton", id="exporter")
            attente.reveiller(autre)                         # seul B est signalé
            moteur.attendre(threading.Event(), 0.5)
            self.assertEqual(self.statut(b, autre)["statut"], "traitée")
            self.assertEqual(self.statut(a)["statut"], "en attente")
            moteur.tour()
            self.assertEqual(self.statut(a)["statut"], "traitée")

    def test_un_reveil_pendant_le_tour_passe_avant_les_autres_etapes(self):
        """Pendant le tour du projet A, le bureau pose une demande pour B : elle est traitée avant que le tour de B ne commence."""
        with tempfile.TemporaryDirectory() as autre_dossier:
            autre = Path(autre_dossier)
            factory_b = factory_minimale(autre)
            projet_b = regles.Projet(factory_b, feu_vert=lambda: True)
            moteur = self.fabriquer([self.projet, projet_b])
            moteur.tour()                                    # les deux sont démarrés
            b = self.demande(factory=factory_b, type="bouton", id="exporter")
            journal = []
            vrai_avancer, vrai_tour = regles.avancer, moteur._tour_projet

            def avancer(projet, etat):
                if projet is self.projet:
                    attente.reveiller(autre)                 # posé pendant le tour de A
                    journal.append("avancer A")
                return vrai_avancer(projet, etat)

            def tour_projet(projet):
                journal.append("début " + ("A" if projet is self.projet else "B"))
                return vrai_tour(projet)

            vrai_traiter = regles.traiter_demande

            def traiter(projet, d, etat):
                journal.append("demande " + ("A" if projet is self.projet else "B"))
                return vrai_traiter(projet, d, etat)

            with mock.patch.object(regles, "avancer", side_effect=avancer), \
                    mock.patch.object(moteur, "_tour_projet", side_effect=tour_projet), \
                    mock.patch.object(regles, "traiter_demande", side_effect=traiter):
                moteur.tour()
            self.assertEqual(self.statut(b, autre)["statut"], "traitée")
            self.assertEqual(journal, ["début A", "avancer A", "demande B", "début B"])

    def test_le_reveil_attend_le_demarrage_du_projet(self):
        i = self.demande(type="bouton", id="exporter")
        attente.reveiller(self.dossier)
        self.moteur._traiter_les_reveils()                   # pas encore démarré : rien ne part avant son premier passage
        self.assertEqual(self.statut(i)["statut"], "en attente")
        self.moteur.tour()
        self.assertEqual(self.statut(i)["statut"], "traitée")

    def test_arret_pendant_l_attente(self):
        arret = threading.Event()
        arret.set()
        debut = time.monotonic()
        self.moteur.attendre(arret, 5)
        self.assertLess(time.monotonic() - debut, 1)


class UneSeuleMesure(unittest.TestCase):
    N = 5
    PAUSE_S = 0.1          # la vraie mesure dure ≈ 5 s ; ici une pause fixe, sans dépendre de la charge réelle

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.projets = []
        for k in range(self.N):
            dossier = Path(self._t.name) / f"p{k}"
            self.projets.append(regles.Projet(factory_minimale(dossier)))     # sans feu_vert : la vraie voie de mesure
        self.plafonds = {str(p.factory): 30 if k == 0 else 70 for k, p in enumerate(self.projets)}
        self.mesures = 0

        def mesurer(projet):
            self.mesures += 1
            time.sleep(self.PAUSE_S)
            return {"feu_vert": False, "charge": 50, "plafond": self.plafonds[str(projet.factory)]}

        for patch in (mock.patch.object(regles.Projet, "mesurer", mesurer),
                      mock.patch.object(regles.Projet, "plafond_charge", lambda p: self.plafonds[str(p.factory)])):
            patch.start()
            self.addCleanup(patch.stop)

    def moteur(self):
        return boucle.Moteur(self.projets, appeler=Appels(), executer_agent=Agents(), synchrone=True,
                             commit=lambda d, m: None)

    def demander_a_tous(self, moteur):
        """Un tour où chaque projet demande la charge (comme `avancer` quand une tâche est prête)."""
        mesures = {}

        def tour_projet(projet):
            mesures[str(projet.factory)] = projet.charge()

        with mock.patch.object(moteur, "_tour_projet", side_effect=tour_projet):
            debut = time.perf_counter()
            moteur.tour()
            duree = time.perf_counter() - debut
        return mesures, duree

    def test_une_mesure_par_tour_chaque_projet_compare_a_son_plafond(self):
        moteur = self.moteur()
        mesures, apres = self.demander_a_tous(moteur)
        self.assertEqual(self.mesures, 1)
        self.assertEqual(moteur.mesures_de_charge, 1)
        feux = [mesures[str(p.factory)]["feu_vert"] for p in self.projets]
        self.assertEqual(feux, [False, True, True, True, True])           # 50 % : plafond 30 retient, plafond 70 laisse
        self.assertTrue(all(m["charge"] == 50 for m in mesures.values()))
        self.assertEqual([m["plafond"] for m in mesures.values()], [30, 70, 70, 70, 70])
        self.demander_a_tous(moteur)
        self.assertEqual(self.mesures, 2)                                  # chaque tour mesure à nouveau, une fois

    def test_un_tour_sans_tache_prete_ne_mesure_rien(self):
        moteur = self.moteur()
        moteur.tour()
        self.assertEqual(self.mesures, 0)

    def test_temps_du_tour_avant_apres(self):
        """Avant : une mesure par projet (N × la mesure). Après : une seule."""
        avant_moteur = self.moteur()
        for p in self.projets:
            p.mesure_commune = lambda projet: projet.mesurer()             # l'ancien comportement
        _, avant = self.demander_a_tous(avant_moteur)
        self.assertEqual(self.mesures, self.N)
        self.mesures = 0
        for p in self.projets:
            p.mesure_commune = None
        apres_moteur = self.moteur()
        _, apres = self.demander_a_tous(apres_moteur)
        self.assertEqual(self.mesures, 1)
        self.assertGreaterEqual(avant, self.N * self.PAUSE_S * 0.9)
        self.assertLess(apres, avant / 2)
        print(f"\ntour avec {self.N} projets, mesure de {self.PAUSE_S} s : avant {avant:.2f} s, après {apres:.2f} s")

    def test_mesure_indisponible_vaut_pour_tous(self):
        moteur = self.moteur()
        with mock.patch.object(regles.Projet, "mesurer", lambda p: {"feu_vert": True, "charge": None, "plafond": None}):
            mesures, _ = self.demander_a_tous(moteur)
        self.assertTrue(all(m["feu_vert"] and m["charge"] is None for m in mesures.values()))


if __name__ == "__main__":
    unittest.main()
