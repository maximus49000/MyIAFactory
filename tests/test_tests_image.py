"""Image des campagnes de tests (`serveur_ovh/images/tests/`) et capacité `tests-image`.

Aucune construction ni aucun `docker` réel : le Dockerfile est lu ; l'étape `tests_image` de `mise_en_place.sh` tourne avec de
faux `sudo`/`docker`/`id` ; l'entrée du conteneur (`entree-tests.sh`) tourne avec le bash du poste, ses chemins `/entree`,
`/work`, `/deps` placés sous ENTREE_TESTS_RACINE (variable réservée aux tests), un faux `tar` et un `python3` qui renvoie à
l'interpréteur des tests."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import serveur_capacites as sc  # noqa: E402
import serveur_installation as inst  # noqa: E402

SERVEUR_OVH = RACINE / "serveur_ovh"
SCRIPT = SERVEUR_OVH / "mise_en_place.sh"
DOCKERFILE = SERVEUR_OVH / "images" / "tests" / "Dockerfile"
ENTREE = SERVEUR_OVH / "images" / "tests" / "entree-tests.sh"
VERSIONS = json.loads((SERVEUR_OVH / "versions.json").read_text(encoding="utf-8"))


def _ecrire_exe(chemin, corps):
    chemin.write_text("#!/bin/sh\n" + corps + "\n", newline="\n")
    chemin.chmod(0o755)


class TestCapaciteTestsImage(unittest.TestCase):
    def test_capacite_et_besoin(self):
        sc.verifier_catalogue()
        self.assertEqual(sc.CATALOGUE["tests-image"], sc.Capacite(
            "tests-image", "Image des campagnes de tests (conteneur sans réseau ni secret)", ("base",), "tests_image",
            "test -s ~/.myiafactory/tests-image.version", 1.0, 6))
        self.assertEqual(sc.BESOINS["tests-serveur"], ("tests-image",))
        self.assertEqual(sc.manquantes_pour(["tests-serveur"], {"base"}), ["tests-image"])
        self.assertEqual(sc.manquantes_pour(["tests-serveur"], set()), ["base", "tests-image"])
        self.assertEqual(inst.FICHIERS_ETAPE["tests_image"], ("images/tests/Dockerfile", "images/tests/entree-tests.sh"))
        self.assertEqual(inst.EMPREINTE_FICHIERS["tests_image"], inst.FICHIERS_ETAPE["tests_image"])
        self.assertEqual(inst.MARQUEURS["tests-image"], ("tests_image", "$HOME/.myiafactory/tests-image.version"))
        self.assertEqual(inst.DELAIS_ETAPE_S["tests_image"], 900)
        texte = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("  tests_image) etape_tests_image ;;", texte)               # l'étape nommée par le catalogue existe
        self.assertIn("tests_image", next(x for x in texte.splitlines() if x.startswith("# Usage")))

    def test_empreinte_tests_image(self):
        avant = inst.empreinte_etape("tests_image")
        self.assertRegex(avant, r"^ubuntu=ubuntu:24\.04;python=3\.12;node=22;fichiers=[0-9a-f]{16}$")
        with tempfile.TemporaryDirectory() as t:
            copie = Path(t) / "serveur_ovh"
            for rel in ("versions.json",) + inst.FICHIERS_ETAPE["tests_image"]:
                (copie / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SERVEUR_OVH / rel, copie / rel)
            with mock.patch.object(inst, "RACINE_SERVEUR", copie):
                self.assertEqual(inst.empreinte_etape("tests_image"), avant)          # mêmes octets, même empreinte
                with open(copie / "images" / "tests" / "entree-tests.sh", "ab") as f:
                    f.write(b"#")
                self.assertNotEqual(inst.empreinte_etape("tests_image"), avant)


class TestDockerfileTests(unittest.TestCase):
    """Le Dockerfile est seulement lu (la construction est un jalon réel, au serveur)."""

    def setUp(self):
        self.texte = DOCKERFILE.read_text(encoding="utf-8")
        self.code = "\n".join(x for x in self.texte.splitlines() if not x.lstrip().startswith("#"))

    def test_base_et_versions_de_versions_json(self):
        self.assertIn(f"ARG UBUNTU_TAG={VERSIONS['base_ubuntu'].split(':')[1]}\n", self.code)
        self.assertIn("FROM ubuntu:${UBUNTU_TAG}\n", self.code)
        self.assertIn(f"ARG NODE_MAJEUR={VERSIONS['node']}\n", self.code)
        self.assertIn("setup_${NODE_MAJEUR}.x", self.code)
        self.assertNotRegex(self.texte.lower(), r"[:=\"' ]latest\b")

    def test_paquets_utilisateur_et_entree(self):
        for paquet in ("python3", "nodejs", "git", "bash", "util-linux", "tar", "build-essential", "ca-certificates"):
            self.assertRegex(self.code, rf"(?<![\w-]){re.escape(paquet)}(?![\w-])", paquet)
        self.assertIn("--no-install-recommends", self.code)
        self.assertIn("\nUSER 1000:1000\n", self.code)
        self.assertIn('\nENTRYPOINT ["/usr/local/bin/entree-tests.sh"]', self.code)
        self.assertIn("COPY entree-tests.sh /usr/local/bin/entree-tests.sh", self.code)
        self.assertIn("chmod 0555 /usr/local/bin/entree-tests.sh", self.code)

    def test_sans_outil_reseau_ni_secret(self):
        self.assertIn("apt-get purge -y curl", self.code)                          # curl ne sert qu'à la construction
        installes = " ".join(re.findall(r"apt-get install ([^&\\]*)", self.code))
        for interdit in ("wget", "sudo", "openssh"):
            self.assertNotIn(interdit, installes, interdit)
            self.assertIn(f"! command -v {interdit.replace('openssh', 'ssh')}", self.code)   # vérifié à la construction
        for interdit in ("claude-code", "TOKEN", "JETON", "ANTHROPIC", "docker.sock"):
            self.assertNotIn(interdit, self.code, interdit)
        self.assertNotRegex(self.code, r"(?m)^\s*(ADD|VOLUME|EXPOSE)\b")


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEtapeTestsImage(unittest.TestCase):
    def _monde(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, t, True)
        faux, home = t / "bin", t / "home"
        faux.mkdir()
        home.mkdir()
        journal = t / "appels.txt"
        _ecrire_exe(faux / "sudo", 'while case "$1" in -n) true;; *) false;; esac; do shift; done\nexec "$@"')
        _ecrire_exe(faux / "id", 'echo ubuntu')
        _ecrire_exe(faux / "docker", (
            f'echo "docker $*" >> "{journal.as_posix()}"\n'
            'case "$1 $2" in\n'
            f'  "image inspect") cat "{t.as_posix()}/etiquette" 2>/dev/null; exit 0 ;;\n'
            '  "build "*) while [ $# -gt 0 ]; do case "$1" in --label) e="${2#versions=}"; shift 2;; *) shift;; esac; done\n'
            f'           printf %s "$e" > "{t.as_posix()}/etiquette"; exit 0 ;;\n'
            'esac\nexit 0'))
        env = dict(os.environ, HOME=home.as_posix(), PATH=faux.as_posix() + os.pathsep + os.environ["PATH"],
                   DISQUE_LIBRE_GO="500", SERVEUR_OVH_DIR=SERVEUR_OVH.as_posix())
        return t, home, journal, env

    def _lancer(self, env, simuler=False):
        r = subprocess.run(["bash", SCRIPT.as_posix(), "--etape", "tests_image"] + (["--simuler"] if simuler else []),
                           capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        lignes = [x for x in r.stdout.splitlines() if x.strip()]
        self.assertEqual(len(lignes), 1, r.stdout)
        return json.loads(lignes[0])

    def test_etape_connue_du_script(self):
        t, home, journal, env = self._monde()
        d = self._lancer(env, simuler=True)
        self.assertEqual((d["etape"], d["statut"]), ("tests_image", "a_faire"))
        self.assertIn("simul", d["detail"].lower())
        self.assertIn("myiafactory/tests", d["detail"])
        self.assertFalse(journal.exists(), journal.read_text() if journal.exists() else "")   # aucun docker appelé
        self.assertEqual(list(home.iterdir()), [])

    def test_etape_construit_avec_l_empreinte_du_poste(self):
        t, home, journal, env = self._monde()
        d = self._lancer(env)
        self.assertEqual(d["statut"], "fait", d["detail"])
        builds = [x for x in journal.read_text().splitlines() if x.startswith("docker build")]
        self.assertEqual(len(builds), 1, journal.read_text())
        self.assertIn("--build-arg UBUNTU_TAG=24.04", builds[0])
        self.assertIn("--build-arg NODE_MAJEUR=22", builds[0])
        self.assertIn("-t myiafactory/tests ", builds[0])
        attendue = inst.empreinte_etape("tests_image")
        self.assertEqual((t / "etiquette").read_text(), attendue)                  # même empreinte côté poste et côté serveur
        self.assertEqual((home / ".myiafactory" / "tests-image.version").read_text().strip(), attendue)
        self.assertNotIn("network", journal.read_text())                           # ni réseau créé ni --network


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEntreeTests(unittest.TestCase):
    def _lancer(self, commande, tar_code=0, brut=None):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, t, True)
        faux = t / "bin"
        faux.mkdir()
        (t / "entree").mkdir()
        (t / "entree" / "entree.tar").write_bytes(b"\0" * 1024)
        (t / "entree" / "commande.json").write_text(brut if brut is not None else json.dumps(commande), encoding="utf-8")
        _ecrire_exe(faux / "tar", f'echo "$*" > "{(t / "tar.args").as_posix()}"\nexit {tar_code}')
        _ecrire_exe(faux / "python3", f'exec "{Path(sys.executable).as_posix()}" "$@"')
        env = dict(os.environ, ENTREE_TESTS_RACINE=t.as_posix(), PATH=faux.as_posix() + os.pathsep + os.environ["PATH"])
        r = subprocess.run(["bash", ENTREE.as_posix()], capture_output=True, text=True, env=env, timeout=30)
        return r, t

    def test_entree_refuse_commande_invalide(self):
        r, t = self._lancer(None, brut=json.dumps("rm -rf /"))
        self.assertEqual(r.returncode, 2, r.stderr)
        r, t = self._lancer(["true"] * 65)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertFalse((t / "tar.args").exists())                                 # rien extrait avant la validation

    def test_entree_execute_le_tableau(self):
        r, t = self._lancer(["sh", "-c", "exit 7"])
        self.assertEqual(r.returncode, 7, r.stderr)
        args = (t / "tar.args").read_text().split()
        for option in ("-x", "--no-same-owner", "--no-same-permissions"):
            self.assertIn(option, args)
        self.assertIn(f"{t.as_posix()}/entree/entree.tar", args)
        self.assertIn(f"{t.as_posix()}/work", args)
        r, t = self._lancer(["printf", "<%s>\\n", "; echo pirate"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), ["<; echo pirate>"])                # un argument, jamais interprété
        r, t = self._lancer(["true"], tar_code=1)
        self.assertEqual(r.returncode, 70, r.stderr)                               # extraction en échec


if __name__ == "__main__":
    unittest.main()
