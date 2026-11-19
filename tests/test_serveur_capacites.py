"""Catalogue de capacités du serveur générique (`outils/serveur_capacites.py`) : données et logique pures."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import serveur_capacites as sc  # noqa: E402
from serveur_capacites import Capacite  # noqa: E402


def _cap(id_, depend=()):
    return Capacite(id=id_, libelle=id_, depend=tuple(depend), etape="docker", sonde="true", taille_go=0, duree_min=1)


class CatalogueTests(unittest.TestCase):
    def test_catalogue_sans_cycle_ni_dependance_inconnue(self):
        sc.verifier_catalogue()
        for cap in sc.CATALOGUE.values():
            for d in cap.depend:
                self.assertIn(d, sc.CATALOGUE)

    def test_contenu_du_catalogue(self):
        self.assertEqual(set(sc.CATALOGUE), {"base", "durcissement", "android-build", "android-emulateur", "unity",
                                             "session-graphique", "agent"})
        self.assertEqual(sc.CATALOGUE["durcissement"].depend, ("base",))
        self.assertEqual(sc.CATALOGUE["android-emulateur"].depend, ("android-build",))
        self.assertEqual(sc.CATALOGUE["base"].etape, "docker")
        self.assertEqual(sc.CATALOGUE["unity"].etape, "unity_cli")

    def test_ordre_respecte_les_dependances(self):
        self.assertEqual(sc.ordre_installation(["android-emulateur"], set()),
                         ["base", "android-build", "android-emulateur"])

    def test_ordre_stable_sans_doublon(self):
        self.assertEqual(sc.ordre_installation(["android-emulateur", "android-build", "unity"], set()),
                         ["base", "android-build", "android-emulateur", "unity"])

    def test_ordre_ignore_ce_qui_est_installe(self):
        self.assertEqual(sc.ordre_installation(["android-emulateur"], {"base"}), ["android-build", "android-emulateur"])
        self.assertEqual(sc.ordre_installation(["android-build"], {"base", "android-build"}), [])

    def test_capacite_inconnue_leve_une_erreur_claire(self):
        with self.assertRaises(ValueError) as c:
            sc.ordre_installation(["magie"], set())
        self.assertIn("magie", str(c.exception))

    def test_cycle_detecte(self):
        cat = {"a": _cap("a", ["b"]), "b": _cap("b", ["a"])}
        with self.assertRaises(ValueError):
            sc.verifier_catalogue(cat)
        with self.assertRaises(ValueError):
            sc.ordre_installation(["a"], set(), catalogue=cat)

    def test_dependance_inconnue_detectee(self):
        with self.assertRaises(ValueError):
            sc.verifier_catalogue({"a": _cap("a", ["fantome"])})

    def test_agent_non_installable_avec_sa_raison(self):
        agent = sc.CATALOGUE["agent"]
        self.assertFalse(agent.installable)
        self.assertEqual(agent.raison_non_installable, "non installable avant le morceau 3")
        self.assertEqual(sc.ordre_installation(["agent"], set()), ["agent"])
        self.assertEqual(sc.bloquees(["agent", "base"]),
                         [{"id": "agent", "raison": "non installable avant le morceau 3"}])

    def test_session_graphique_non_installable_par_le_moteur_generique(self):
        cap = sc.CATALOGUE["session-graphique"]
        self.assertFalse(cap.installable)
        self.assertIn("lancer.py plateforme installer --bureau-distant", cap.raison_non_installable)
        self.assertEqual(cap.etape, "bureau_distant")

    def test_bloquees_inclut_les_dependances(self):
        # une capacité installable dont une dépendance est bloquée : la dépendance est signalée
        cat = {"a": _cap("a", ["b"]), "b": Capacite("b", "b", (), "docker", "true", 0, 1, False, "pas encore")}
        self.assertEqual(sc.bloquees(["a"], catalogue=cat), [{"id": "b", "raison": "pas encore"}])

    def test_manquantes_pour_actions(self):
        self.assertEqual(sc.manquantes_pour(["emulateur"], {"android-build"}), ["android-emulateur"])
        self.assertEqual(sc.manquantes_pour(["apk", "tests", "lint", "release"], set()), ["base", "android-build"])
        self.assertEqual(sc.manquantes_pour(["charge"], set()), [])

    def test_besoins(self):
        for a in ("apk", "tests", "lint", "release"):
            self.assertEqual(sc.BESOINS[a], ("android-build",))
        self.assertEqual(sc.BESOINS["emulateur"], ("android-emulateur",))
        self.assertEqual(sc.BESOINS["charge"], ())

    def test_action_inconnue_leve_une_erreur(self):
        with self.assertRaises(ValueError):
            sc.manquantes_pour(["voler"], set())

    def test_sondes_sont_en_lecture_seule(self):
        for cap in sc.CATALOGUE.values():
            sonde = cap.sonde
            self.assertTrue(sonde.strip(), cap.id)
            neutre = sonde.replace("2>&1", "").replace(">/dev/null", "")
            self.assertNotIn(">", neutre, cap.id)
            for mot in ("install", "apt", "apt-get", "rm", "mv", "cp", "tee", "chmod", "sudo", "curl", "wget"):
                self.assertIsNone(re.search(r"(?<![\w./-])" + re.escape(mot) + r"(?![\w-])", sonde),
                                  f"{cap.id} : « {mot} » interdit dans une sonde")

    def test_sondes_et_estimations_du_catalogue(self):
        for cap in sc.CATALOGUE.values():
            self.assertGreaterEqual(cap.taille_go, 0)
            self.assertGreater(cap.duree_min, 0)
        self.assertEqual(sc.CATALOGUE["durcissement"].sonde, "test -f /etc/ssh/sshd_config.d/00-myiafactory.conf")

    def test_aucune_mention_de_fournisseur_dans_le_module(self):
        source = (Path(__file__).resolve().parent.parent / "outils" / "serveur_capacites.py").read_text(encoding="utf-8")
        self.assertNotIn("ovh", source.lower())


if __name__ == "__main__":
    unittest.main()
