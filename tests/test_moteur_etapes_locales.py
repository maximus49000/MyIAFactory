"""Le lieu d'une étape (conception 2026-11-13-etapes-locales-design.md) : une étape `local` attend le poste, une étape
`indifférent` part où une place se libère (cloud compris, même si son métier est réservé au local) ; sans `lieu`, le
`Lieu :` du métier vaut, comme avant. Aucun appel réel."""
import json
import tempfile
import unittest
from pathlib import Path

from moteur import jugement, regles
from orchestrateur import depart, factory
from orchestrateur import modele_necessaire as mn
from orchestrateur import workflows as wf
from tests.orch_aide import RACINE
from tests.test_moteur_jugement import DOSSIERS, VALIDES
from tests.test_moteur_polyvalents import FLUX, SESSION, Base


class AvecDeuxPlaces(Base):
    """Une place locale (prise par une autre tâche) et une place cloud libre."""
    locaux, cloud = 1, 1

    def setUp(self):
        super().setUp()
        self.agent("local-1")
        self.agent("cloud-1", prenom="Max", lieu="cloud", session=SESSION)
        self.occupee = self.tache("flux:dev", element="e9", titre="Autre")
        self.ok("tache", entree={"id": self.occupee, "agent": "local-1", "active": True})

    def lieu(self, etape, lieu):
        """Écrit le `lieu` de l'étape `etape` du flux du projet."""
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["flux"] = [dict(e, lieu=lieu) if e["id"] == etape else e for e in f["flux"]]
        self.factory.write_text(json.dumps(f), encoding="utf-8")


class LieuDeLEtape(AvecDeuxPlaces):
    def test_etape_locale_attend_le_poste(self):
        self.lieu("qa", "local")
        t = self.tache("flux:qa")
        self.assertNotIn(t, self.parties(self.demarrer()))

    def test_etape_indifferente_part_dans_le_cloud_meme_si_metier_local(self):
        self.brief("qa", "Lieu : local\n\nBrief des testeurs, avec l'émulateur du poste.\n")
        self.lieu("qa", "indifférent")
        t = self.tache("flux:qa")
        self.assertEqual(self.parties(self.demarrer()), {t: "cloud-1"})

    def test_sans_lieu_repli_sur_le_metier(self):
        self.brief("qa", "Lieu : local\n\nBrief des testeurs, avec l'émulateur du poste.\n")
        t = self.tache("flux:qa")
        self.assertNotIn(t, self.parties(self.demarrer()))

    def test_sans_lieu_ni_metier_local_part_dans_le_cloud(self):
        """Non-régression : un projet sans `lieu` sur ses étapes choisit comme avant."""
        t = self.tache("flux:qa")
        self.assertEqual(self.parties(self.demarrer()), {t: "cloud-1"})

    def test_attente_dit_le_poste_local(self):
        self.lieu("qa", "local")
        t = self.tache("flux:qa")
        etat = self.demarrer()
        self.assertIn("attend le poste local", etat["attente_charge"]["texte"])
        self.assertEqual(etat["attente_charge"]["taches"], [t])

    def test_rien_n_attend_le_poste_sans_etape_locale(self):
        self.tache("flux:qa")
        self.assertNotIn("attente_charge", self.demarrer())

    def test_etape_locale_part_quand_le_poste_se_libere(self):
        self.lieu("qa", "local")
        t = self.tache("flux:qa")
        self.faite(self.occupee)
        self.assertEqual(self.parties(self.demarrer()), {t: "local-1"})

    def test_la_commande_agent_libre_lit_l_etape_de_la_tache(self):
        self.lieu("qa", "local")
        t = self.tache("flux:qa")
        r = self.ok("agent-libre", entree={"role": "qa", "lieu": "cloud", "tache": t})
        self.assertIsNone(r["agent"])
        self.assertIn("poste local", r["raison"])
        self.assertEqual(self.ok("agent-libre", entree={"role": "qa", "lieu": "cloud"})["agent"], "cloud-1")


class Choix(unittest.TestCase):
    FICHES = [{"cle": "a-local", "lieu": "local", "role": None},
              {"cle": "a-cloud", "lieu": "cloud", "role": None, "session": SESSION}]

    def test_agent_libre_lieu_d_etape_avant_le_metier(self):
        occupe = [{"agent": "a-local", "active": True}]
        cle, raison = depart.agent_libre(self.FICHES, occupe, "qa", lieu_etape="local")
        self.assertIsNone(cle)
        self.assertIn("poste local", raison)
        self.assertEqual(depart.agent_libre(self.FICHES, occupe, "qa", lieu_reserve="local",
                                            lieu_etape="indifférent")[0], "a-cloud")
        self.assertIsNone(depart.agent_libre(self.FICHES, occupe, "qa", lieu_reserve="local")[0])

    def test_lieu_impose(self):
        self.assertEqual(mn.lieu_impose("local", None), "local")
        self.assertEqual(mn.lieu_impose("local", "cloud"), "local")
        self.assertIsNone(mn.lieu_impose("indifférent", "local"))
        self.assertEqual(mn.lieu_impose(None, "local"), "local")
        self.assertIsNone(mn.lieu_impose(None, None))

    def test_lieu_de_la_tache(self):
        f = {"flux": [dict(FLUX[0], lieu="local"), *FLUX[1:]], "workflows": []}
        self.assertEqual(mn.lieu_de_la_tache(f, {"etape": "flux:dev", "role": "dev"}), "local")
        self.assertIsNone(mn.lieu_de_la_tache(f, {"etape": "flux:qa", "role": "qa"}))
        self.assertIsNone(mn.lieu_de_la_tache(f, {"etape": "cadrage", "role": "dev"}))


class Ecriture(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dossier = Path(self._t.name)

    def lire(self, flux):
        chemin = self.dossier / "factory.json"
        chemin.write_text(json.dumps({"skill": str(RACINE), "services": [{"id": "dev", "nom": "Dev"}],
                                      "flux": flux}), encoding="utf-8")
        return factory.lire(chemin)

    def test_factory_lit_le_lieu(self):
        f = self.lire([{"id": "dev", "nom": "Dev", "role": "dev", "service": "dev", "lieu": "local"},
                       {"id": "qa", "nom": "Recette", "role": "dev", "service": "dev", "lieu": "indifférent"}])
        self.assertEqual([e["lieu"] for e in f["flux"]], ["local", "indifférent"])

    def test_lieu_inconnu_refuse(self):
        with self.assertRaises(factory.FactoryInvalide):
            self.lire([{"id": "dev", "nom": "Dev", "role": "dev", "service": "dev", "lieu": "cloud"}])

    def test_validation_refuse_un_lieu(self):
        with self.assertRaises(factory.FactoryInvalide):
            self.lire([{"id": "dev", "nom": "Dev", "role": "dev", "service": "dev"},
                       {"id": "val", "nom": "Essai", "validation": True, "lieu": "local"},
                       {"id": "fin", "nom": "Fin", "role": "dev", "service": "dev"}])
        self.assertNotIn("lieu", wf.etape_ecrite({"id": "val", "nom": "Essai", "validation": True, "lieu": "local"}))

    def test_etape_ecrite_garde_le_lieu(self):
        e = {"id": "dev", "nom": "Dev", "role": "dev", "service": "dev"}
        self.assertEqual(wf.etape_ecrite({**e, "lieu": "local"}), {**e, "lieu": "local"})
        self.assertEqual(wf.etape_ecrite({**e, "lieu": "indifférent"}), {**e, "lieu": "indifférent"})
        self.assertEqual(wf.etape_ecrite({**e, "lieu": "ailleurs"}), e)


class Jugement(unittest.TestCase):
    def varie(self, type_, etape, **champs):
        o = json.loads(json.dumps(VALIDES[type_]))
        o["flux"] = [dict(x, **champs) if x["etape"] == etape else x for x in o["flux"]]
        return jugement.valider(type_, o, DOSSIERS[type_])

    def test_definir_workflow_et_organisation_acceptent_le_lieu(self):
        for type_ in ("definir_workflow", "proposer_organisation"):
            with self.subTest(type_=type_):
                self.assertIsNone(self.varie(type_, "qualite", lieu="local"))
                self.assertIsNone(self.varie(type_, "dev", lieu="indifférent"))
                self.assertIsNotNone(self.varie(type_, "dev", lieu="cloud"))

    def test_validation_refuse_un_lieu_au_jugement(self):
        self.assertIsNotNone(self.varie("definir_workflow", "validation", lieu="local"))


if __name__ == "__main__":
    unittest.main()
