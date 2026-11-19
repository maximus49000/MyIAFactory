"""Catalogue de capacités du serveur générique (`outils/serveur_capacites.py`) : données et logique pures."""
import re
import shutil
import subprocess
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
        self.assertEqual(set(sc.CATALOGUE), {"base", "durcissement", "android-build", "android-emulateur", "unity-cli",
                                             "unity-editeur", "session-graphique", "agent"})
        self.assertEqual(sc.CATALOGUE["durcissement"].depend, ("base",))
        self.assertEqual(sc.CATALOGUE["android-emulateur"].depend, ("android-build",))
        self.assertEqual(sc.CATALOGUE["base"].etape, "docker")
        cli, ed = sc.CATALOGUE["unity-cli"], sc.CATALOGUE["unity-editeur"]
        self.assertEqual((cli.etape, cli.depend, cli.installable), ("unity_cli", ("base",), True))
        self.assertEqual((cli.taille_go, cli.duree_min), (0.1, 2))
        self.assertTrue(cli.sonde.startswith("test -x ~/.local/bin/unity"))
        self.assertIn("~/.local/bin/unity --version", cli.sonde)
        self.assertEqual(ed.depend, ("unity-cli",))
        self.assertFalse(ed.installable)
        self.assertIn("Unity Hub", ed.raison_non_installable)
        self.assertIn("unity install <version>", ed.raison_non_installable)
        self.assertEqual((ed.taille_go, ed.duree_min), (24.0, 25))
        self.assertEqual(ed.sonde, "ls ~/Unity/Hub/Editor/*/Editor/Unity >/dev/null 2>&1")
        self.assertEqual([b["id"] for b in sc.bloquees(sc.ordre_installation(["unity-editeur"], set()))], ["unity-editeur"])

    def test_ordre_respecte_les_dependances(self):
        self.assertEqual(sc.ordre_installation(["android-emulateur"], set()),
                         ["base", "android-build", "android-emulateur"])

    def test_ordre_stable_sans_doublon(self):
        self.assertEqual(sc.ordre_installation(["android-emulateur", "android-build", "unity-cli"], set()),
                         ["base", "android-build", "android-emulateur", "unity-cli"])

    def test_ordre_ignore_ce_qui_est_installe(self):
        self.assertEqual(sc.ordre_installation(["android-emulateur"], {"base"}), ["android-build", "android-emulateur"])
        # seule la liste fournie fait foi : aucune dépendance n'est déduite d'une capacité installée
        self.assertEqual(sc.ordre_installation(["android-emulateur"], {"android-build"}), ["base", "android-emulateur"])
        self.assertEqual(sc.ordre_installation(["android-build"], {"durcissement"}), ["base", "android-build"])
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
        self.assertEqual(sc.manquantes_pour(["emulateur"], {"base", "android-build"}), ["android-emulateur"])
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
            self.assertNotIn("<", neutre, cap.id)
            for mot in ("install", "apt", "apt-get", "rm", "mv", "cp", "tee", "chmod", "sudo", "curl", "wget",
                        "exit", "set", "read"):
                self.assertIsNone(re.search(r"(?<![\w./-])" + re.escape(mot) + r"(?![\w-])", sonde),
                                  f"{cap.id} : « {mot} » interdit dans une sonde")

    def test_bloquees_recoit_la_liste_des_manquantes(self):
        self.assertEqual(sc.bloquees(sc.ordre_installation(["agent"], {"base", "agent"})), [])

    def test_installable_faux_exige_une_raison(self):
        with self.assertRaises(ValueError):
            Capacite("x", "x", (), "docker", "true", 0.0, 1, installable=False)

    def test_catalogue_et_besoins_en_lecture_seule(self):
        with self.assertRaises(TypeError):
            sc.CATALOGUE["x"] = _cap("x")
        with self.assertRaises(TypeError):
            sc.BESOINS["x"] = ()

    def test_dependance_inconnue_via_ordre_installation(self):
        with self.assertRaises(ValueError):
            sc.ordre_installation(["a"], set(), catalogue={"a": _cap("a", ["fantome"])})

    def test_taille_go_toujours_flottante(self):
        for cap in sc.CATALOGUE.values():
            self.assertIsInstance(cap.taille_go, float, cap.id)

    def test_sonde_durcissement_verifie_la_directive(self):
        sonde = sc.CATALOGUE["durcissement"].sonde
        self.assertIn("grep -qi '^PasswordAuthentication no' /etc/ssh/sshd_config.d/00-myiafactory.conf", sonde)
        self.assertNotIn("sudo", sonde)

    def test_sonde_session_graphique_ne_confond_pas_les_ports(self):
        sonde = sc.CATALOGUE["session-graphique"].sonde
        self.assertIn("ss -ltn 2>/dev/null", sonde)
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash absent")
        grep = re.search(r"\| (grep -qE '[^']+')", sonde).group(1)
        def code(texte):
            return subprocess.run([bash, "-c", f"printf '%s\n' \"$0\" | {grep}", texte]).returncode
        self.assertEqual(code("LISTEN 0 128 127.0.0.1:3389 0.0.0.0:*"), 0)
        self.assertNotEqual(code("LISTEN 0 128 127.0.0.1:33890 0.0.0.0:*"), 0)
        self.assertNotEqual(code("LISTEN 0 128 127x0x0x1:3389 0.0.0.0:*"), 0)

    def test_sondes_et_estimations_du_catalogue(self):
        for cap in sc.CATALOGUE.values():
            self.assertGreaterEqual(cap.taille_go, 0)
            self.assertGreater(cap.duree_min, 0)

    def test_aucune_mention_de_fournisseur_dans_le_module(self):
        source = (Path(__file__).resolve().parent.parent / "outils" / "serveur_capacites.py").read_text(encoding="utf-8")
        self.assertNotIn("ovh", source.lower())


if __name__ == "__main__":
    unittest.main()
