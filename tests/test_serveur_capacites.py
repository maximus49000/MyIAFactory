"""Catalogue de capacités du serveur générique (`outils/serveur_capacites.py`) : données et logique pures."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import serveur_capacites as sc  # noqa: E402
from serveur_capacites import Capacite  # noqa: E402

from tests import plateforme_tests  # noqa: E402



def _cap(id_, depend=()):
    return Capacite(id=id_, libelle=id_, depend=tuple(depend), etape="docker", sonde="true", taille_go=0, duree_min=1)


class CatalogueTests(unittest.TestCase):
    def test_catalogue_sans_cycle_ni_dependance_inconnue(self):
        sc.verifier_catalogue()
        for cap in sc.CATALOGUE.values():
            for d in cap.depend:
                self.assertIn(d, sc.CATALOGUE)

    def test_contenu_du_catalogue(self):
        self.assertEqual(set(sc.CATALOGUE), {"base", "durcissement", "android-build", "android-emulateur", "emulateur-image",
                                             "unity-cli", "unity-editeur", "session-graphique", "agent", "agent-abonnement"})
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

    def test_catalogue_et_recette_s_accordent(self):
        cap = sc.CATALOGUE["emulateur-image"]
        self.assertEqual((cap.etape, cap.depend, cap.installable), ("emulateur_image", ("android-emulateur",), True))
        self.assertEqual(cap.sonde, "test -s ~/.myiafactory/emulateur-image.version")
        self.assertGreater(cap.taille_go, 0)
        self.assertEqual(sc.ordre_installation(["emulateur-image"], set()),
                         ["base", "android-build", "android-emulateur", "emulateur-image"])
        script = (Path(__file__).resolve().parent.parent / "serveur_ovh" / "mise_en_place.sh").read_text(encoding="utf-8")
        self.assertIn(f"  {cap.etape}) etape_{cap.etape} ;;", script)          # l'étape nommée par le catalogue existe dans le script
        self.assertIn("emulateur-image.version", script)                       # et écrit le marqueur que la sonde teste
        self.assertEqual(sc.bloquees(["emulateur-image"]), [])
        import serveur_installation as inst
        self.assertEqual(inst.DELAIS_ETAPE_S[cap.etape], 900)

    def test_sonde_emulateur_image_en_lecture_seule(self):
        sonde = sc.CATALOGUE["emulateur-image"].sonde
        self.assertNotRegex(sonde, r"sudo|docker|[<>]")
        with tempfile.TemporaryDirectory() as t:
            def code(creer):
                dossier = Path(t) / ".myiafactory"
                if creer is not None:
                    dossier.mkdir(exist_ok=True)
                    (dossier / "emulateur-image.version").write_text(creer, encoding="utf-8")
                r = subprocess.run(["bash", "-c", f"( {sonde} ) </dev/null >/dev/null 2>&1"], env={"HOME": Path(t).as_posix(), "PATH": os.environ["PATH"]})
                return r.returncode
            self.assertNotEqual(code(None), 0)
            self.assertNotEqual(code(""), 0)
            self.assertEqual(code("ubuntu=ubuntu:24.04"), 0)
            self.assertEqual(sorted(x.name for x in (Path(t) / ".myiafactory").iterdir()), ["emulateur-image.version"])

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

    def test_agent_installable_par_l_etape_agent_image(self):
        agent = sc.CATALOGUE["agent"]
        self.assertEqual((agent.etape, agent.depend, agent.installable), ("agent_image", ("base",), True))
        self.assertEqual(agent.sonde, "test -s ~/.myiafactory/agent-image.version")
        self.assertGreater(agent.taille_go, 0)
        self.assertEqual(sc.ordre_installation(["agent"], set()), ["base", "agent"])
        self.assertEqual(sc.bloquees(["agent", "base"]), [])
        script = (Path(__file__).resolve().parent.parent / "serveur_ovh" / "mise_en_place.sh").read_text(encoding="utf-8")
        self.assertIn(f"  {agent.etape}) etape_{agent.etape} ;;", script)         # l'étape nommée par le catalogue existe dans le script
        self.assertIn("agent-image.version", script)                              # et écrit le marqueur que la sonde teste
        import serveur_installation as inst
        self.assertEqual(inst.DELAIS_ETAPE_S[agent.etape], 900)
        self.assertEqual(inst.MARQUEURS["agent"], ("agent_image", "$HOME/.myiafactory/agent-image.version"))

    def test_agent_abonnement_non_installable_avec_le_geste(self):
        cap = sc.CATALOGUE["agent-abonnement"]
        self.assertEqual(cap.depend, ("agent",))
        self.assertFalse(cap.installable)
        self.assertEqual(sc.ordre_installation(["agent-abonnement"], {"base", "agent"}), ["agent-abonnement"])
        self.assertEqual(sc.bloquees(["agent-abonnement"]), [{"id": "agent-abonnement", "raison": cap.raison_non_installable}])
        raison = cap.raison_non_installable
        self.assertIn("enregistrer_jeton.sh", raison)                              # le geste du Directeur...
        self.assertIn("docs/serveur-agents.md#connexion-a-l-abonnement", raison)  # ... et le renvoi au mode opératoire
        self.assertNotIn("\n", raison)
        self.assertNotIn("sk-", raison)

    def test_besoins_agent_serveur_et_pilote(self):
        self.assertEqual(sc.BESOINS["agent-serveur"], ("agent", "agent-abonnement"))
        self.assertEqual(sc.BESOINS["agent-pilote"], ("agent", "agent-abonnement", "emulateur-image"))
        self.assertEqual(sc.manquantes_pour(["agent-serveur"], {"base"}), ["agent", "agent-abonnement"])
        self.assertEqual(sc.manquantes_pour(["agent-pilote"], set()),
                         ["base", "agent", "agent-abonnement", "android-build", "android-emulateur", "emulateur-image"])
        self.assertEqual([b["id"] for b in sc.bloquees(sc.manquantes_pour(["agent-serveur"], {"base", "agent"}))], ["agent-abonnement"])

    @unittest.skipUnless(shutil.which("bash"), "bash absent")
    @plateforme_tests.pas_encore_linux("sonde lancée sous bash avec faux HOME ou faux stat : échoue au conteneur Linux, cause à préciser")
    def test_sondes_agent_et_abonnement_en_lecture_seule(self):
        agent = sc.CATALOGUE["agent"].sonde
        abo = sc.CATALOGUE["agent-abonnement"].sonde
        self.assertEqual(abo, '[ "$(stat -c %a ~/agent-identifiants)" = 700 ] && [ "$(stat -c %a ~/agent-identifiants/jeton)" = 600 ] '
                              '&& test -s ~/agent-identifiants/jeton')
        for sonde in (agent, abo):
            self.assertNotRegex(sonde, r"sudo|docker|[<>]")
        for mot in ("cat", "head", "tail", "grep", "read", "source", "eval"):    # le contenu du jeton n'est jamais lu
            self.assertIsNone(re.search(r"(?<![\w./-])" + mot + r"(?![\w-])", abo), mot)
        with tempfile.TemporaryDirectory() as t:
            home, faux = Path(t) / "home", Path(t) / "bin"
            (home / ".myiafactory").mkdir(parents=True)
            (home / "agent-identifiants").mkdir()
            faux.mkdir()
            (faux / "stat").write_text('#!/bin/sh\ncase "$3" in */jeton) echo "$MODE_F";; *) echo "$MODE_D";; esac\n', newline="\n")
            (faux / "stat").chmod(0o755)

            def code(sonde, mode_d="700", mode_f="600"):
                env = dict(os.environ, HOME=home.as_posix(), PATH=faux.as_posix() + os.pathsep + os.environ["PATH"], MODE_D=mode_d, MODE_F=mode_f)
                return subprocess.run(["bash", "-c", f"( {sonde} ) </dev/null >/dev/null 2>&1"], env=env, timeout=30).returncode
            self.assertNotEqual(code(agent), 0)
            (home / ".myiafactory" / "agent-image.version").write_text("", encoding="utf-8")
            self.assertNotEqual(code(agent), 0)                                    # marqueur vide
            (home / ".myiafactory" / "agent-image.version").write_text("ubuntu=ubuntu:24.04", encoding="utf-8")
            self.assertEqual(code(agent), 0)
            self.assertNotEqual(code(abo), 0)                                      # pas de jeton
            (home / "agent-identifiants" / "jeton").write_text("", encoding="utf-8")
            self.assertNotEqual(code(abo), 0)                                      # jeton vide
            (home / "agent-identifiants" / "jeton").write_text("x", encoding="utf-8")
            self.assertEqual(code(abo), 0)
            self.assertNotEqual(code(abo, mode_d="755"), 0)                        # dossier trop ouvert
            self.assertNotEqual(code(abo, mode_f="644"), 0)                        # fichier trop ouvert
            self.assertEqual((home / "agent-identifiants" / "jeton").read_text(encoding="utf-8"), "x")   # rien modifié
            self.assertEqual(sorted(x.name for x in (home / "agent-identifiants").iterdir()), ["jeton"])

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

    def test_recette_emulateur_demande_l_image_et_toute_sa_chaine(self):
        self.assertEqual(sc.BESOINS["recette-emulateur"], ("emulateur-image",))
        self.assertEqual(sc.manquantes_pour(["recette-emulateur"], set()),
                         ["base", "android-build", "android-emulateur", "emulateur-image"])
        self.assertEqual(sc.manquantes_pour(["recette-emulateur"], {"base", "android-build", "android-emulateur"}),
                         ["emulateur-image"])
        # toute capacité installable est demandée par au moins une action (sinon le bureau ne peut pas l'installer)
        demandees = set(sc.manquantes_pour(list(sc.BESOINS), set()))
        self.assertEqual({i for i, c in sc.CATALOGUE.items() if c.installable} - demandees, {"durcissement", "unity-cli"})

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

    # --- sonde android-build : le Java peut venir du PATH, d'Ubuntu (JDK 17) ou du JDK livré avec Unity -------------------
    def _android_build(self, sdk=True, java="aucun", glob_vide=False):
        """Lance la VRAIE sonde sous bash, dans un faux HOME et un PATH sans java ; rend le code de sortie."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            home, bin_ = t / "home", t / "bin"
            home.mkdir()
            bin_.mkdir()
            if sdk:
                for rel in ("android-sdk/platform-tools", "android-sdk/platforms/android-36", "android-sdk/build-tools/36.0.0"):
                    (home / rel).mkdir(parents=True)
                adb = home / "android-sdk/platform-tools/adb"
                adb.write_text("#!/bin/sh\n", newline="\n")
                adb.chmod(0o755)
            if java == "unity":
                j = home / "Unity/Hub/Editor/6000.0.1f1/Editor/Data/PlaybackEngines/AndroidPlayer/OpenJDK/bin/java"
            elif java == "path":
                j = bin_ / "java"
            else:
                j = None
            if j is not None:
                j.parent.mkdir(parents=True, exist_ok=True)
                j.write_text("#!/bin/sh\n", newline="\n")
                j.chmod(0o755)
            if java == "unity-non-executable":
                j = home / "Unity/Hub/Editor/6000.0.1f1/Editor/Data/PlaybackEngines/AndroidPlayer/OpenJDK/bin/java"
                j.parent.mkdir(parents=True)
                j.write_text("x", newline="\n")
            env = dict(os.environ, HOME=home.as_posix(), PATH=bin_.as_posix() + os.pathsep + "/usr/bin" + os.pathsep + "/bin")
            return subprocess.run(["bash", "-c", f"( {sc.CATALOGUE['android-build'].sonde} ) </dev/null >/dev/null 2>&1"],
                                  env=env, capture_output=True, timeout=30).returncode

    @unittest.skipUnless(shutil.which("bash"), "bash absent")
    @plateforme_tests.pas_encore_linux("sonde lancée sous bash avec faux HOME ou faux stat : échoue au conteneur Linux, cause à préciser")
    def test_sonde_android_build_accepte_le_jdk_d_unity_seul(self):
        self.assertEqual(self._android_build(java="unity"), 0)

    @unittest.skipUnless(shutil.which("bash"), "bash absent")
    @plateforme_tests.pas_encore_linux("sonde lancée sous bash avec faux HOME ou faux stat : échoue au conteneur Linux, cause à préciser")
    def test_sonde_android_build_accepte_java_du_path(self):
        self.assertEqual(self._android_build(java="path"), 0)

    @unittest.skipUnless(shutil.which("bash") and not list(Path("/usr/lib/jvm").glob("java-17-openjdk-*/bin/java")),
                         "bash absent ou JDK 17 présent sur ce poste")
    def test_sonde_android_build_absente_sans_java_nulle_part(self):
        self.assertNotEqual(self._android_build(java="aucun"), 0)           # aucun glob sans correspondance ne compte
        self.assertNotEqual(self._android_build(java="unity-non-executable"), 0)

    @unittest.skipUnless(shutil.which("bash"), "bash absent")
    def test_sonde_android_build_absente_si_le_sdk_est_incomplet(self):
        self.assertNotEqual(self._android_build(sdk=False, java="unity"), 0)
        self.assertNotEqual(self._android_build(sdk=False, java="path"), 0)

    def test_sonde_android_emulateur_verifie_l_image_epinglee(self):
        # M7 : le dossier de l'image système ÉPINGLÉE (versions.json), pas seulement ~/android-sdk/system-images.
        import json
        versions = json.loads((Path(__file__).resolve().parent.parent / "serveur_ovh" / "versions.json")
                              .read_text(encoding="utf-8"))
        chemin = versions["android_sdk"]["emulator_image"].replace(";", "/")
        sonde = sc.CATALOGUE["android-emulateur"].sonde
        self.assertIn(f"test -d ~/android-sdk/{chemin} ", sonde)

    @unittest.skipUnless(shutil.which("bash"), "bash absent")
    @plateforme_tests.pas_encore_linux("sonde lancée sous bash avec faux HOME ou faux stat : échoue au conteneur Linux, cause à préciser")
    def test_sonde_android_emulateur_absente_sans_l_image_epinglee(self):
        import os
        import tempfile
        sonde = sc.CATALOGUE["android-emulateur"].sonde.split(" && id -nG")[0]      # sans kvm (ce poste n'en a pas)
        with tempfile.TemporaryDirectory() as t:
            home = Path(t)
            emu = home / "android-sdk/emulator/emulator"
            emu.parent.mkdir(parents=True)
            emu.write_text("#!/bin/sh\n", newline="\n")
            emu.chmod(0o755)
            (home / "android-sdk/system-images/android-35/google_apis/x86_64").mkdir(parents=True)

            def code():
                return subprocess.run(["bash", "-c", f"( {sonde} ) </dev/null >/dev/null 2>&1"], timeout=30,
                                      env=dict(os.environ, HOME=home.as_posix())).returncode
            self.assertNotEqual(code(), 0)                                  # une autre image ne compte pas
            (home / "android-sdk/system-images/android-34/google_apis/x86_64").mkdir(parents=True)
            self.assertEqual(code(), 0)

    def test_sondes_et_estimations_du_catalogue(self):
        for cap in sc.CATALOGUE.values():
            self.assertGreaterEqual(cap.taille_go, 0)
            self.assertGreater(cap.duree_min, 0)

    def test_aucune_mention_de_fournisseur_dans_le_module(self):
        source = (Path(__file__).resolve().parent.parent / "outils" / "serveur_capacites.py").read_text(encoding="utf-8")
        self.assertNotIn("ovh", source.lower())


if __name__ == "__main__":
    unittest.main()
