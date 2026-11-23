"""Profil d'outils par type de projet (tâche 15g) : un agent créé au serveur reçoit les programmes du profil réglé dans la page
Réglages ; le défaut n'ouvre rien ; seuls des programmes de la liste fermée du profil s'ouvrent, en `Bash(<programme>:*)`."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bureau import deport_types, registre, reglages
from orchestrateur import fiches
from tests.test_orch_equipe_places import Base


class TestRegistre(unittest.TestCase):
    def test_choix_ferme_defaut_aucun(self):
        r = next(x for x in registre.REGISTRE if x.id == "outils_agents_serveur")
        self.assertEqual((r.forme, r.defaut, r.niveaux), ("choix", "aucun", registre.NIVEAUX))
        self.assertEqual(r.options, ("aucun", "flutter"))
        self.assertEqual(registre.PROFILS_OUTILS["aucun"], ())
        self.assertEqual(registre.PROFILS_OUTILS["flutter"], ("analyser-flutter", "tester-flutter", "construire-apk", "flutter"))
        for programme in registre.PROFILS_OUTILS["flutter"]:
            self.assertTrue(fiches.est_programme(programme), programme)
        with self.assertRaises(ValueError):
            registre.verifier_valeur(r, "tout")

    def test_niveau_type_du_bureau(self):
        with tempfile.TemporaryDirectory() as d:
            projet, bureau = Path(d, "reglages.json"), Path(d, "bureau.json")
            projet.write_text("{}", encoding="utf-8")
            bureau.write_text(json.dumps({"projets": [{"chemin": str(projet)}]}), encoding="utf-8")
            reglages.fixer_niveau_bureau(bureau, ("types", "application-mobile-android", "reglages", "outils_agents_serveur"), "flutter")
            with mock.patch("bureau.reglages._genre_du_projet", return_value="application-mobile-android"):
                self.assertEqual(reglages.charger_effectif(projet, bureau)["outils_agents_serveur"], "flutter")
            with mock.patch("bureau.reglages._genre_du_projet", return_value="autre-genre"):
                self.assertEqual(reglages.charger_effectif(projet, bureau)["outils_agents_serveur"], "aucun")


class TestAgentsDuServeur(Base):
    def serveur(self, profil=None):
        reglage = self.dossier / "reglages.json"
        donnees = json.loads(reglage.read_text(encoding="utf-8"))
        if profil is not None:
            donnees["outils_agents_serveur"] = profil
        reglage.write_text(json.dumps(donnees), encoding="utf-8")
        with mock.patch.object(deport_types, "BUREAU", str(self.dossier / "pas-de-bureau.json")):
            self.ok("parallelisme", entree={"agents_locaux_max": self.locaux, "agents_cloud_max": 0, "agents_serveur_max": 2})
        return [x for x in self.equipe() if x["lieu"] == "serveur"]

    def test_defaut_n_ouvre_rien(self):
        for profil in (None, "aucun"):
            with self.subTest(profil=profil):
                for x in self.equipe():
                    if x["lieu"] == "serveur":
                        (self.fiches / f"{x['cle']}.md").unlink()
                crees = self.serveur(profil)
                self.assertEqual(len(crees), 2)
                for x in crees:
                    self.assertFalse([o for o in fiches.outils(x) if "flutter" in o or "construire-apk" in o], x["outils"])

    def test_profil_flutter_ouvre_les_programmes_du_profil_a_chaque_agent_serveur(self):
        crees = self.serveur("flutter")
        self.assertEqual(len(crees), 2)
        for x in crees:
            outils = fiches.outils(x)
            for programme in ("analyser-flutter", "tester-flutter", "construire-apk", "flutter"):
                self.assertIn(f"Bash({programme}:*)", outils)
            self.assertNotIn("Bash", outils)                       # jamais le shell entier
        # les agents locaux n'en reçoivent pas
        for x in self.equipe():
            if x["lieu"] == "local":
                self.assertFalse([o for o in fiches.outils(x) if "flutter" in o])

    def test_reglage_illisible_n_ouvre_rien(self):
        (self.dossier / "reglages.json").write_text("pas du json", encoding="utf-8")
        with mock.patch.object(deport_types, "BUREAU", str(self.dossier / "pas-de-bureau.json")):
            self.ok("parallelisme", entree={"agents_locaux_max": self.locaux, "agents_cloud_max": 0, "agents_serveur_max": 1})
        for x in self.equipe():
            if x["lieu"] == "serveur":
                self.assertFalse([o for o in fiches.outils(x) if "flutter" in o])


if __name__ == "__main__":
    unittest.main()
