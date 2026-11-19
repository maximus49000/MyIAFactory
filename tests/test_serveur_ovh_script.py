"""Script de mise en place du serveur (`serveur_ovh/mise_en_place.sh`) : lancé avec le bash du poste, en `--simuler`."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent / "serveur_ovh"
SCRIPT = RACINE / "mise_en_place.sh"
ETAPES = ("durcissement", "docker", "images", "licence", "etat")
CLES = {"etape", "statut", "detail", "versions", "disque_libre_go"}


def lancer(etape, simuler=True, entree="", env=None):
    args = ["bash", SCRIPT.as_posix(), "--etape", etape] + (["--simuler"] if simuler else [])
    e = dict(os.environ, **(env or {}))
    return subprocess.run(args, input=entree, capture_output=True, text=True, env=e, timeout=60)


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestScriptSimule(unittest.TestCase):
    def test_chaque_etape_rend_un_json_valide(self):
        for etape in ETAPES:
            with self.subTest(etape=etape):
                r = lancer(etape, env={"DISQUE_LIBRE_GO": "500"})
                self.assertEqual(r.returncode, 0, r.stderr)
                lignes = [x for x in r.stdout.splitlines() if x.strip()]
                self.assertEqual(len(lignes), 1, r.stdout)
                d = json.loads(lignes[0])
                self.assertEqual(set(d), CLES)
                self.assertEqual(d["etape"], etape)
                self.assertIn(d["statut"], ("fait", "a_faire", "bloque"))
                self.assertIsInstance(d["detail"], str)
                self.assertIsInstance(d["versions"], dict)
                self.assertEqual(d["disque_libre_go"], 500)

    def test_simuler_ne_modifie_rien(self):
        # De faux apt/docker/ufw/systemctl... dans le PATH enregistrent tout appel : il ne doit y en avoir aucun.
        with tempfile.TemporaryDirectory() as t:
            journal = Path(t) / "appels.txt"
            for nom in ("apt-get", "apt", "docker", "ufw", "systemctl", "sshd", "curl", "sudo"):
                f = Path(t) / nom
                f.write_text(f'#!/bin/sh\necho "{nom} $@" >> "{journal.as_posix()}"\n', newline="\n")
                f.chmod(0o755)
            for etape in ETAPES:
                r = lancer(etape, env={"DISQUE_LIBRE_GO": "500", "PATH": Path(t).as_posix() + os.pathsep + os.environ["PATH"]})
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("simul", json.loads(r.stdout.strip().splitlines()[-1])["detail"].lower())
            self.assertFalse(journal.exists(), journal.read_text() if journal.exists() else "")

    def test_images_refuse_si_disque_presque_plein(self):
        r = lancer("images", env={"DISQUE_LIBRE_GO": "5"})
        d = json.loads(r.stdout)
        self.assertEqual(d["statut"], "bloque")
        self.assertIn("disque", d["detail"].lower())
        self.assertEqual(d["disque_libre_go"], 5)

    def test_licence_absente_n_est_pas_une_erreur(self):
        r = lancer("licence", simuler=True, entree="", env={"DISQUE_LIBRE_GO": "500"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["statut"], "a_faire")

    def test_licence_jamais_reaffichee(self):
        secret = "SECRET-ULF-<xml>-12345"
        r = lancer("licence", simuler=True, entree=secret, env={"DISQUE_LIBRE_GO": "500"})
        self.assertNotIn(secret, r.stdout + r.stderr)

    def test_autres_etapes_tournent_stdin_ferme(self):
        for etape in ("durcissement", "docker", "images", "etat"):
            with self.subTest(etape=etape):
                args = ["bash", SCRIPT.as_posix(), "--etape", etape, "--simuler"]
                r = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   env=dict(os.environ, DISQUE_LIBRE_GO="500"), timeout=60)
                self.assertEqual(r.returncode, 0, r.stderr)
                json.loads(r.stdout)

    def _durcir_avec_faux(self, cles, ssh_ok):
        """Lance l'étape durcissement (réelle) avec de faux binaires ; rend (JSON, journal des appels)."""
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            journal = t / "appels.txt"
            faux = t / "bin"
            faux.mkdir()
            corps = {
                "sudo": 'exec "$@"',
                "ssh": "exit 0" if ssh_ok else "exit 255",
                "ssh-keygen": 'while [ $# -gt 0 ]; do [ "$1" = -f ] && f="$2"; shift; done; echo cle > "$f"; echo pub > "$f.pub"',
            }
            for nom in ("apt-get", "dpkg-reconfigure", "ufw", "sshd", "systemctl", "tee", "ssh", "ssh-keygen", "sudo"):
                texte = f'#!/bin/sh\necho "{nom} $@" >> "{journal.as_posix()}"\n' + corps.get(nom, "") + "\n"
                if nom == "sudo":
                    texte = '#!/bin/sh\nwhile case "$1" in *=*) true;; *) false;; esac; do shift; done\nexec "$@"\n'
                (faux / nom).write_text(texte, newline="\n")
                (faux / nom).chmod(0o755)
            home = t / "home"
            (home / ".ssh").mkdir(parents=True)
            (home / ".ssh" / "authorized_keys").write_text(cles, newline="\n")
            r = subprocess.run(["bash", SCRIPT.as_posix(), "--etape", "durcissement"], stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, encoding="utf-8", timeout=60,
                               env=dict(os.environ, HOME=home.as_posix(), PATH=faux.as_posix() + os.pathsep + os.environ["PATH"]))
            appels = journal.read_text() if journal.exists() else ""
            return json.loads(r.stdout), appels

    def _aucun_appel_sensible(self, appels):
        for interdit in ("ufw ", "sshd ", "systemctl", "tee"):
            # `sshd -T` et `ufw status` sont des lectures du constat initial, pas des modifications.
            self.assertFalse([x for x in appels.splitlines()
                              if x.startswith(interdit) and not x.startswith(("sshd -T", "ufw status"))], appels)

    def test_durcissement_bloque_sans_autre_cle(self):
        d, appels = self._durcir_avec_faux("", ssh_ok=True)
        self.assertEqual(d["statut"], "bloque")
        self.assertIn("clé dédiée", d["detail"])
        self._aucun_appel_sensible(appels)

    def test_durcissement_bloque_si_seconde_session_echoue(self):
        d, appels = self._durcir_avec_faux("ssh-ed25519 AAAAautre directeur\n", ssh_ok=False)
        self.assertEqual(d["statut"], "bloque")
        self._aucun_appel_sensible(appels)

    def test_etape_inconnue_refusee(self):
        r = lancer("nimportequoi")
        self.assertNotEqual(r.returncode, 0)


class TestTexteDuScript(unittest.TestCase):
    def setUp(self):
        self.texte = SCRIPT.read_text(encoding="utf-8")

    def test_durcissement_verifie_seconde_session_avant_pare_feu(self):
        code = "\n".join(x for x in self.texte.splitlines() if not x.lstrip().startswith("#"))
        debut = code.index("etape_durcissement()")
        appel = code.index("verifier_seconde_session", debut)
        self.assertLess(appel, code.index("ufw --force enable", debut))
        self.assertLess(appel, code.index("PasswordAuthentication no", debut))
        self.assertIn("ufw limit 22", code)
        self.assertIn("unattended-upgrades", code)

    def test_ufw_regle_puis_verifiee_puis_activee_sans_ignorer_l_echec(self):
        code = self.texte[self.texte.index("etape_durcissement()"):]
        regle = code.index("sudo ufw limit 22")
        verif = code.index("sudo ufw show added")
        activer = code.index("sudo ufw --force enable")
        self.assertLess(regle, verif)
        self.assertLess(verif, activer)
        self.assertIn("|| repondre bloque", code[regle:verif])
        self.assertIn("|| repondre bloque", code[verif:activer])

    def test_stdin_lu_uniquement_par_la_licence(self):
        self.assertIn('if [ "$ETAPE" != "licence" ]; then\n  exec </dev/null', self.texte)
        self.assertIn("ssh -n ", self.texte)
        self.assertEqual(self.texte.count("$(cat)"), 1)
        self.assertLess(self.texte.index("etape_licence()"), self.texte.index("$(cat)"))

    def test_licence_exige_une_preuve_et_ne_fait_pas_confiance_au_code_de_sortie(self):
        licence = self.texte[self.texte.index("etape_licence()"):self.texte.index("etape_etat()")]
        self.assertIn("-logFile -", licence)
        self.assertIn("|| true", licence)
        self.assertIn("grep -qiE", licence)
        self.assertIn("Unity_lic.ulf", licence)

    def test_unity_epingle_sur_la_version_du_projet_avec_module_android(self):
        versions = json.loads((RACINE / "versions.json").read_text(encoding="utf-8"))
        self.assertEqual(versions["unity_gameci"], "unityci/editor:ubuntu-6000.6.7f1-android-4.0.0")

    def test_images_reconstruites_si_les_versions_changent(self):
        self.assertIn('--label "versions=$empreinte"', self.texte)
        self.assertIn('"$actuelle" != "$empreinte"', self.texte)
        self.assertEqual(self.texte.count("--build-arg"), 8)

    def test_dockerfile_script_et_versions_json_concordent(self):
        versions = json.loads((RACINE / "versions.json").read_text(encoding="utf-8"))

        def script(nom):
            m = re.search(rf'^{nom}="([^"]*)"', self.texte, re.M)
            self.assertIsNotNone(m, nom)
            return m.group(1)

        def arg(dockerfile, nom):
            m = re.search(rf"^ARG {nom}=(\S+)", (RACINE / "images" / dockerfile / "Dockerfile").read_text(encoding="utf-8"), re.M)
            self.assertIsNotNone(m, f"{dockerfile} {nom}")
            return m.group(1)

        self.assertEqual(script("V_UBUNTU"), versions["base_ubuntu"])
        self.assertEqual(script("V_BUILD_TOOLS"), versions["android_build_tools"])
        self.assertEqual(script("V_PLATEFORME"), versions["android_plateforme"])
        self.assertEqual(script("V_CMDLINE_TOOLS"), versions["android_cmdline_tools"])
        self.assertEqual(script("V_GRADLE"), versions["gradle"])
        self.assertEqual(script("V_NODE"), versions["node"])
        self.assertEqual(script("V_CLAUDE_CODE"), versions["claude_code"])
        tag = versions["base_ubuntu"].split(":")[1]
        for image in ("android", "agent"):
            self.assertEqual(arg(image, "UBUNTU_TAG"), tag)
        self.assertEqual(arg("android", "BUILD_TOOLS"), versions["android_build_tools"])
        self.assertEqual(arg("android", "PLATEFORME"), versions["android_plateforme"])
        self.assertEqual(arg("android", "CMDLINE_TOOLS"), versions["android_cmdline_tools"])
        self.assertEqual(arg("android", "GRADLE"), versions["gradle"])
        self.assertEqual(arg("agent", "NODE_MAJEUR"), versions["node"])
        self.assertEqual(arg("agent", "CLAUDE_CODE"), versions["claude_code"])

    def test_licence_non_lue_dans_argv(self):
        self.assertNotIn("--licence", self.texte)
        self.assertIn("cat", self.texte)
        self.assertIn("stdin", self.texte)

    def test_versions_epinglees(self):
        versions = json.loads((RACINE / "versions.json").read_text(encoding="utf-8"))
        dockerfiles = [RACINE / "images/android/Dockerfile", RACINE / "images/agent/Dockerfile"]
        for f in [RACINE / "versions.json", SCRIPT] + dockerfiles:
            # Aucune étiquette flottante ; le nom de fichier du téléchargement Google (`..._latest.zip`) n'est pas une étiquette.
            self.assertNotRegex(f.read_text(encoding="utf-8").lower(), r"[:=\"' ]latest\b(?!\.zip)", f.name)
        for d in dockerfiles:
            origines = [x for x in d.read_text(encoding="utf-8").splitlines() if x.startswith("FROM")]
            self.assertTrue(origines, d)
            for ligne in origines:
                self.assertRegex(ligne, r"FROM \S+:\S+", ligne)
        self.assertIn(versions["unity_gameci"], self.texte)

    def test_fins_de_ligne_lf(self):
        self.assertNotIn(b"\r", SCRIPT.read_bytes())


if __name__ == "__main__":
    unittest.main()
