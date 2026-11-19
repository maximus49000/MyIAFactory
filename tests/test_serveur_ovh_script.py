"""Script de mise en place du serveur (`serveur_ovh/mise_en_place.sh`) : lancé avec le bash du poste, en `--simuler`."""
import json
import os
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
