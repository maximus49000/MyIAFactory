"""La capacité Flutter du serveur, sans réseau ni vrai serveur :
- l'étape `flutter_sdk` de `serveur_ovh/mise_en_place.sh` (faux curl, sudo, apt, dpkg-query, id ; vraie archive .tar.xz
  jetable vérifiée par le vrai sha256sum et extraite par le vrai tar ; faux `flutter` dans l'archive) ;
- la capacité `flutter-sdk`, le besoin `agent-flutter`, le marqueur et son empreinte ;
- l'enveloppe `lancer_agent.sh` (SDK monté en lecture seule, verrou propre à la tâche, mêmes durcissements) et l'entrée
  du conteneur (`environnement_flutter`) ;
- la détection d'un projet Flutter sur le poste (`outils/projet_flutter.py`) et la demande d'agent (`serveur_agent`)."""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from tests.test_serveur_agent_script import Banc, ID, charger_entree, suite_dans

RACINE = Path(__file__).resolve().parent.parent
SERVEUR_OVH = RACINE / "serveur_ovh"
SCRIPT = SERVEUR_OVH / "mise_en_place.sh"
sys.path.insert(0, str(RACINE / "outils"))
import projet_flutter  # noqa: E402
import serveur_agent as sa  # noqa: E402
import serveur_capacites as sc  # noqa: E402
import serveur_installation as inst  # noqa: E402
import serveur_tache as st  # noqa: E402
from tests.test_serveur_agent import Base, ID1, declarer, CAPS_AGENT  # noqa: E402

VERSION = json.loads((SERVEUR_OVH / "versions.json").read_text(encoding="utf-8"))["flutter"]["version"]
ARCHIVE = f"stable/linux/flutter_linux_{VERSION}-stable.tar.xz"
URL_ARCHIVE = f"https://storage.googleapis.com/flutter_infra_release/releases/{ARCHIVE}"
CLES = {"etape", "statut", "detail", "versions", "disque_libre_go"}

# Le faux flutter de l'archive : journalise ses appels ; --version --machine lit la version de son SDK (fichier
# `version-fausse` à côté de bin/) ; precache échoue si FAUX_PRECACHE_ECHEC.
FAUX_FLUTTER = r'''#!/bin/sh
echo "flutter $*" >> "$FAUX_JOURNAL"
ici=$(cd "$(dirname "$0")/.." && pwd)
case " $* " in
  *" --version "*) printf '{"frameworkVersion": "%s", "channel": "stable"}\n' "$(cat "$ici/version-fausse")"; exit 0 ;;
  *" precache "*) [ -n "${FAUX_PRECACHE_ECHEC:-}" ] && exit 1; : > "$ici/bin/cache/precache-fait"; exit 0 ;;
esac
exit 0
'''


def archive_flutter(version=VERSION):
    """Une archive .tar.xz « officielle » factice : flutter/bin/flutter, Dart embarqué, version annoncée."""
    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w:xz") as tar:
        for nom, texte, mode in (("flutter/bin/flutter", FAUX_FLUTTER, 0o755),
                                 ("flutter/bin/cache/dart-sdk/bin/dart", "#!/bin/sh\nexit 0\n", 0o755),
                                 ("flutter/version-fausse", version + "\n", 0o644)):
            donnees = texte.encode("utf-8")
            info = tarfile.TarInfo(nom)
            info.size, info.mode, info.mtime = len(donnees), mode, 0
            tar.addfile(info, io.BytesIO(donnees))
    return tampon.getvalue()


def manifeste(sha, archive=ARCHIVE, version=VERSION, doublon=None):
    rel = [{"hash": "b" * 40, "channel": "beta", "version": version, "archive": f"beta/linux/flutter_linux_{version}-beta.tar.xz",
            "sha256": "c" * 64, "dart_sdk_arch": "x64"},
           {"hash": "d" * 40, "channel": "stable", "version": "3.0.0", "archive": "stable/linux/flutter_linux_3.0.0-stable.tar.xz",
            "sha256": "e" * 64},
           {"hash": "a" * 40, "channel": "stable", "version": version, "archive": archive, "sha256": sha, "dart_sdk_arch": "x64"}]
    if doublon:
        rel.append({**rel[-1], "sha256": doublon})
    return json.dumps({"base_url": "https://autre.exemple.net/piege", "current_release": {}, "releases": rel}, indent=2)


class MondeFlutter:
    """HOME jetable avec, au choix, le SDK Android de l'hôte (capacité android-build) ; faux binaires dans le PATH."""

    def __init__(self, android=True, utilisateur="ubuntu", sha=None, archive=ARCHIVE, sans_version=False, doublon=None,
                 sdkmanager=False, version_archive=VERSION):
        self.android, self.utilisateur, self.sdkmanager = android, utilisateur, sdkmanager
        self.donnees = archive_flutter(version_archive)
        sha = sha or hashlib.sha256(self.donnees).hexdigest()
        self.texte_manifeste = manifeste(sha, archive=archive, version="9.9.9" if sans_version else VERSION, doublon=doublon)

    def __enter__(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        t = self.t = Path(self._t.name)
        self.home, self.bin, self.jvm = t / "home", t / "bin", t / "jvm"
        for d in (self.home, self.bin, self.jvm):
            d.mkdir()
        self.journal_fichier = t / "appels.txt"
        (t / "releases_linux.json").write_text(self.texte_manifeste, encoding="utf-8", newline="\n")
        (t / "flutter.tar.xz").write_bytes(self.donnees)
        j, tp = self.journal_fichier.as_posix(), t.as_posix()
        faux = {
            "curl": ('echo "curl $*" >> "' + j + '"\nout=""; url=""\n'
                     'while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; --connect-timeout|--max-time|--max-filesize|--proto) shift 2;; '
                     '-*) shift;; *) url="$1"; shift;; esac; done\n'
                     'case "$url" in\n'
                     f'  https://storage.googleapis.com/flutter_infra_release/releases/releases_linux.json) cp "{tp}/releases_linux.json" "$out";;\n'
                     f'  {URL_ARCHIVE}) cp "{tp}/flutter.tar.xz" "$out";;\n'
                     '  *) exit 22;;\nesac'),
            "sudo": 'echo "sudo $*" >> "' + j + '"\nwhile case "$1" in *=*|-n) true;; *) false;; esac; do shift; done\nexec "$@"',
            "apt-get": 'echo "apt-get $*" >> "' + j + '"\nexit 0',
            "dpkg-query": "echo installed",
            "id": 'case "$1" in -un) echo "${FAUX_UTILISATEUR:-ubuntu}";; -u) echo 1000;; -g) echo 1000;; esac',
        }
        for nom, corps in faux.items():
            (self.bin / nom).write_text("#!/bin/sh\n" + corps + "\n", newline="\n")
            (self.bin / nom).chmod(0o755)
        java = self.jvm / "java-17-openjdk-amd64" / "bin" / "java"
        java.parent.mkdir(parents=True)
        java.write_text("#!/bin/sh\n", newline="\n")
        java.chmod(0o755)
        if self.android:
            sdk = self.home / "android-sdk"
            for rel in ("platform-tools", "platforms/android-36", "build-tools/36.0.0"):
                (sdk / rel).mkdir(parents=True)
            adb = sdk / "platform-tools" / "adb"
            adb.write_text("#!/bin/sh\n", newline="\n")
            adb.chmod(0o755)
            if self.sdkmanager:
                s = sdk / "cmdline-tools" / "latest" / "bin" / "sdkmanager"
                s.parent.mkdir(parents=True)
                s.write_text('#!/bin/sh\necho "sdkmanager $*" >> "' + j + '"\nhead -n 1 > /dev/null\nexit 0\n', newline="\n")
                s.chmod(0o755)
        return self

    def __exit__(self, *a):
        self._t.cleanup()

    def lancer(self, simuler=False, env=None):
        e = dict(os.environ, HOME=self.home.as_posix(), PATH=self.bin.as_posix() + os.pathsep + os.environ["PATH"],
                 DISQUE_LIBRE_GO="500", JVM_RACINE=self.jvm.as_posix(), JAVA_HOME="", FAUX_JOURNAL=self.journal_fichier.as_posix(),
                 FAUX_UTILISATEUR=self.utilisateur, PYTHON_HOTE=Path(sys.executable).as_posix())
        e.update(env or {})
        args = ["bash", SCRIPT.as_posix(), "--etape", "flutter_sdk"] + (["--simuler"] if simuler else [])
        r = self.derniere = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", env=e, timeout=120,
                                           stdin=subprocess.DEVNULL)
        lignes = [x for x in r.stdout.splitlines() if x.strip()]
        assert len(lignes) == 1, (r.stdout, r.stderr)
        return json.loads(lignes[0])

    @property
    def journal(self):
        return self.journal_fichier.read_text(encoding="utf-8") if self.journal_fichier.exists() else ""

    def appels(self, prefixe):
        return [x for x in self.journal.splitlines() if x.startswith(prefixe)]

    @property
    def sdk(self):
        return self.home / "flutter-sdk"

    @property
    def marqueur(self):
        return self.home / ".myiafactory" / "flutter-sdk.version"

    def restes(self):
        return sorted(p.name for p in self.home.iterdir() if p.name.startswith(".flutter-sdk.telechargement"))


@unittest.skipUnless(shutil.which("bash") and shutil.which("tar") and shutil.which("sha256sum"), "bash, tar ou sha256sum absent")
class TestEtapeFlutterSdk(unittest.TestCase):
    def test_simulation_ne_touche_a_rien(self):
        with MondeFlutter() as m:
            avant = sorted(p.name for p in m.home.iterdir())
            d = m.lancer(simuler=True)
            self.assertEqual(set(d), CLES)
            self.assertEqual((d["etape"], d["statut"]), ("flutter_sdk", "a_faire"))
            self.assertIn("simul", d["detail"].lower())
            self.assertIn(VERSION, d["detail"])
            self.assertEqual(m.journal, "")
            self.assertEqual(sorted(p.name for p in m.home.iterdir()), avant)

    def test_installe_verifie_et_ecrit_le_marqueur_en_dernier(self):
        with MondeFlutter() as m:
            d = m.lancer()
            self.assertEqual(d["statut"], "fait", d["detail"] + m.derniere.stderr)
            self.assertEqual(m.marqueur.read_text(encoding="utf-8"), f"flutter={VERSION};canal=stable\n")
            self.assertEqual(m.marqueur.read_text(encoding="utf-8").strip(), inst.empreinte_etape("flutter_sdk"))
            self.assertTrue((m.sdk / "bin" / "cache" / "lockfile").is_file())
            self.assertTrue((m.sdk / "bin" / "cache" / "precache-fait").is_file())
            curl = m.appels("curl ")
            self.assertEqual(len(curl), 2, m.journal)
            self.assertIn("releases_linux.json", curl[0])
            self.assertIn(URL_ARCHIVE, curl[1])                     # le dépôt officiel, jamais la base_url du manifeste
            self.assertNotIn("autre.exemple.net", m.journal)
            for c in curl:
                self.assertIn("--proto =https", c)
            precache = [x for x in m.appels("flutter ") if " precache " in f" {x} "]
            self.assertEqual(len(precache), 1, m.journal)
            for option in ("--android", "--universal", "--no-ios", "--no-web", "--no-linux", "--no-windows", "--no-macos",
                           "--no-fuchsia", "--no-version-check", "--suppress-analytics"):
                self.assertIn(option, precache[0].split())
            self.assertEqual(m.restes(), [])
            self.assertFalse([p for p in m.home.iterdir() if ".ancien." in p.name])

    def test_idempotente_sans_reseau(self):
        with MondeFlutter() as m:
            self.assertEqual(m.lancer()["statut"], "fait")
            m.journal_fichier.unlink()
            d = m.lancer()
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertIn("déjà en place", d["detail"])
            self.assertEqual(m.journal, "")                           # ni curl, ni flutter, ni apt

    def test_empreinte_differente_rien_n_est_extrait(self):
        with MondeFlutter(sha="0" * 64) as m:
            d = m.lancer()
            self.assertEqual(d["statut"], "bloque")
            self.assertIn("SHA-256", d["detail"])
            self.assertFalse(m.sdk.exists())
            self.assertFalse(m.marqueur.exists())
            self.assertEqual(m.appels("flutter "), [])
            self.assertEqual(m.restes(), [])

    def test_manifeste_sans_une_seule_archive_est_bloque(self):
        for monde in (MondeFlutter(sans_version=True), MondeFlutter(doublon="f" * 64)):
            with self.subTest(), monde as m:
                d = m.lancer()
                self.assertEqual(d["statut"], "bloque")
                self.assertIn("UNE archive", d["detail"])
                self.assertEqual(len(m.appels("curl ")), 1)            # l'archive n'est jamais téléchargée
                self.assertFalse(m.sdk.exists())

    def test_nom_d_archive_hostile_refuse_avant_telechargement(self):
        for nom in ("../../../etc/x.tar.xz", f"stable/linux/flutter_linux_{VERSION}-stable.tar.xz.sh",
                    "https://autre.exemple.net/flutter.tar.xz", f"stable/linux/flutter_linux_{VERSION.replace('.', 'x', 1)}-stable.tar.xz"):
            with self.subTest(nom=nom), MondeFlutter(archive=nom) as m:
                d = m.lancer()
                self.assertEqual(d["statut"], "bloque", d["detail"])
                self.assertIn("Nom d'archive inattendu", d["detail"])
                self.assertEqual(len(m.appels("curl ")), 1)

    def test_prerequis_root_android_et_disque(self):
        with MondeFlutter(utilisateur="root") as m:
            d = m.lancer()
            self.assertEqual(d["statut"], "bloque")
            self.assertIn("root", d["detail"])
            self.assertEqual(m.journal, "")
        with MondeFlutter(android=False) as m:
            d = m.lancer()
            self.assertEqual(d["statut"], "a_faire")
            self.assertIn("android-build", d["detail"])
            self.assertEqual(m.appels("curl "), [])
        with MondeFlutter() as m:
            d = m.lancer(env={"DISQUE_LIBRE_GO": "2"})
            self.assertEqual(d["statut"], "bloque")
            self.assertIn("Disque", d["detail"])
            self.assertEqual(m.appels("curl "), [])

    def test_ancienne_version_mise_de_cote_puis_remplacee(self):
        with MondeFlutter() as m:
            ancien = m.sdk
            (ancien / "bin" / "cache").mkdir(parents=True)
            (ancien / "bin" / "flutter").write_text(FAUX_FLUTTER, newline="\n")
            (ancien / "bin" / "flutter").chmod(0o755)
            (ancien / "version-fausse").write_text("3.0.0\n", newline="\n")
            m.marqueur.parent.mkdir()
            m.marqueur.write_text("flutter=3.0.0;canal=stable\n", newline="\n")
            d = m.lancer()
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertIn("mis de côté", d["detail"])
            anciens = [p for p in m.home.iterdir() if p.name.startswith("flutter-sdk.ancien.")]
            self.assertEqual(len(anciens), 1)
            self.assertEqual((anciens[0] / "version-fausse").read_text().strip(), "3.0.0")
            self.assertEqual((m.sdk / "version-fausse").read_text().strip(), VERSION)

    def test_bonne_version_deja_extraite_n_est_pas_retelechargee(self):
        with MondeFlutter() as m:                     # SDK de la bonne version, precache interrompu (pas de marqueur)
            (m.sdk / "bin" / "cache" / "dart-sdk" / "bin").mkdir(parents=True)
            (m.sdk / "bin" / "flutter").write_text(FAUX_FLUTTER, newline="\n")
            (m.sdk / "bin" / "flutter").chmod(0o755)
            (m.sdk / "bin" / "cache" / "dart-sdk" / "bin" / "dart").write_text("#!/bin/sh\n", newline="\n")
            (m.sdk / "bin" / "cache" / "dart-sdk" / "bin" / "dart").chmod(0o755)
            (m.sdk / "version-fausse").write_text(VERSION + "\n", newline="\n")
            d = m.lancer()
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertEqual(m.appels("curl "), [])
            self.assertTrue(m.marqueur.exists())

    def test_precache_en_echec_bloque_sans_marqueur(self):
        with MondeFlutter() as m:
            d = m.lancer(env={"FAUX_PRECACHE_ECHEC": "1"})
            self.assertEqual(d["statut"], "bloque")
            self.assertIn("precache", d["detail"])
            self.assertFalse(m.marqueur.exists())

    def test_licences_android_acceptees_par_sdkmanager(self):
        with MondeFlutter(sdkmanager=True) as m:
            d = m.lancer()
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertTrue([x for x in m.appels("sdkmanager ") if "--licenses" in x], m.journal)
        with MondeFlutter() as m:                     # sans sdkmanager : seulement dit
            d = m.lancer()
            self.assertEqual(d["statut"], "fait", d["detail"])
            self.assertIn("Licences Android non revues", d["detail"])

    def test_lien_symbolique_refuse(self):
        with MondeFlutter() as m:
            cible = m.t / "ailleurs"
            cible.mkdir()
            try:
                os.symlink(cible, m.sdk, target_is_directory=True)
            except OSError:
                self.skipTest("liens symboliques indisponibles")
            if not m.sdk.is_symlink():
                self.skipTest("liens symboliques indisponibles")
            d = m.lancer()
            self.assertEqual(d["statut"], "bloque")
            self.assertIn("lien symbolique", d["detail"])
            self.assertEqual(m.appels("curl "), [])


class TestScriptEtConcordance(unittest.TestCase):
    texte = SCRIPT.read_text(encoding="utf-8")

    def test_version_epinglee_partout_la_meme(self):
        import re
        self.assertRegex(VERSION, r"^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$")
        self.assertEqual(re.search(r'^V_FLUTTER="([^"]*)"', self.texte, re.M).group(1), VERSION)
        self.assertEqual(inst.empreinte_etape("flutter_sdk"), f"flutter={VERSION};canal=stable")
        self.assertEqual(inst.MARQUEURS["flutter-sdk"], ("flutter_sdk", "$HOME/.myiafactory/flutter-sdk.version"))
        self.assertIn("flutter_sdk", inst.DELAIS_ETAPE_S)
        self.assertNotIn("flutter_sdk", inst.FICHIERS_ETAPE)          # rien à déposer : aucune image

    def test_delai_ssh_couvre_les_delais_internes(self):
        import re
        section = self.texte[self.texte.index("# --- Flutter ---"):self.texte.index("# --- Unity CLI ---")]
        curl = [int(x) for x in re.findall(r"--max-time (\d+)", section)]
        version = int(re.search(r"flutter_hote (\d+) --version", section).group(1))
        precache = int(re.search(r'FLUTTER_DELAI_S:-(\d+)', section).group(1))
        licences = int(re.search(r'SDK_DELAI_LICENCE_S:-(\d+)', section).group(1))
        sdkmanager = int(re.search(r'local SDK_DELAI_S="\$\{SDK_DELAI_S:-(\d+)\}"', section).group(1))
        total = sum(curl) + 2 * version + precache + licences + 2 * sdkmanager       # --version avant et après ; repli JDK 21
        self.assertLess(total, inst.DELAIS_ETAPE_S["flutter_sdk"])

    def test_usage_dispatch_et_jamais_de_pipe_vers_un_shell(self):
        usage = next(x for x in self.texte.splitlines() if x.startswith("# Usage"))
        self.assertIn("flutter_sdk", usage)
        self.assertIn("  flutter_sdk) etape_flutter_sdk ;;", self.texte)
        code = "\n".join(x for x in self.texte.splitlines() if not x.lstrip().startswith("#"))
        etape = code[code.index("installer_archive_flutter()"):code.index("etape_flutter_sdk()")]
        self.assertNotRegex(etape, r"\|\s*(sudo\s+)?(ba|z)?sh\b")
        self.assertLess(etape.index("sha256sum"), etape.index("tar -xJf"))       # vérifié AVANT d'extraire
        self.assertIn("--no-same-owner", etape)

    def test_capacite_et_besoin(self):
        cap = sc.CATALOGUE["flutter-sdk"]
        self.assertEqual((cap.etape, cap.depend, cap.installable), ("flutter_sdk", ("android-build",), True))
        self.assertIn("~/.myiafactory/flutter-sdk.version", cap.sonde)
        self.assertEqual(sc.BESOINS["agent-flutter"], ("agent", "agent-abonnement", "flutter-sdk"))
        self.assertEqual(sc.manquantes_pour(["agent-flutter"], set()),
                         ["base", "agent", "agent-abonnement", "android-build", "flutter-sdk"])
        self.assertEqual(sc.manquantes_pour(["agent-flutter"], {"base", "agent", "agent-abonnement", "android-build"}),
                         ["flutter-sdk"])


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEnveloppeFlutter(unittest.TestCase):
    def sdk(self, b, lockfile=True, marqueur=True):
        f = b.home / "flutter-sdk"
        (f / "bin" / "cache").mkdir(parents=True)
        (f / "bin" / "flutter").write_text("#!/bin/sh\n", newline="\n")
        (f / "bin" / "flutter").chmod(0o755)
        if lockfile:
            (f / "bin" / "cache" / "lockfile").write_text("", newline="\n")
        if marqueur:
            (b.home / ".myiafactory").mkdir()
            (b.home / ".myiafactory" / "flutter-sdk.version").write_text(f"flutter={VERSION};canal=stable\n", newline="\n")

    def test_projet_flutter_sdk_en_lecture_seule_et_bin_cache_en_overlay_par_tache(self):
        with Banc() as b:
            self.sdk(b)
            (b.home / "android-sdk").mkdir()
            b.ecrire_entree(flutter=True)
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            h, d, vol = b.h(), f"{b.h()}/taches/{ID}", f"flutter-{ID}"
            creation = [x for x in b.appels("docker volume create") if x.endswith(f" {vol}")]
            self.assertEqual(len(creation), 1, b.journal)
            self.assertIn(f"--driver local --opt type=overlay --opt device=overlay --opt o=lowerdir={h}/flutter-sdk,"
                          f"upperdir={d}/flutter-up,workdir={d}/flutter-work {vol}", creation[0])
            for sous in ("flutter-up", "flutter-work"):
                self.assertTrue((b.dossier / sous).is_dir())
            # validation : un run bref, sans réseau, qui monte le volume, AVANT le conteneur de l'agent
            v = next(x for x in b.appels("docker run") if "verif-flutter-" in x).split()
            self.assertIn("--rm", v)
            suite_dans(self, v, "--network", "none")
            suite_dans(self, v, "--mount", f"type=volume,src={vol},dst=/opt/flutter-sdk")
            self.assertIn("test -x /opt/flutter-sdk/bin/flutter", " ".join(v))
            self.assertIn("/opt/flutter-sdk/bin/cache/lockfile", " ".join(v))
            for x in ("--read-only",):
                self.assertIn(x, v)
            suite_dans(self, v, "--cap-drop", "ALL")
            j = b.journal
            self.assertLess(j.index("docker volume create"), j.index("verif-flutter-"))
            self.assertLess(j.index("verif-flutter-"), j.index("docker run --pull never -d"))
            a = b.run_args()
            suite_dans(self, a, "--mount", f"type=volume,src={vol},dst=/opt/flutter-sdk")       # le SDK entier, en overlay
            self.assertFalse([x for x in a if "src=" + h + "/flutter-sdk" in x])                # jamais le SDK de l'hôte en bind
            # le SDK Android aussi en copie sur écriture par tâche (Gradle et AGP y écrivent), jamais en bind
            asdk = f"asdk-{ID}"
            self.assertTrue([x for x in b.appels("docker volume create") if x.endswith(
                f"o=lowerdir={h}/android-sdk,upperdir={d}/android-up,workdir={d}/android-work {asdk}")], b.journal)
            for sous in ("android-up", "android-work"):
                self.assertTrue((b.dossier / sous).is_dir())
            self.assertLess(j.index("verif-asdk-"), j.index("docker run --pull never -d"))
            suite_dans(self, a, "--mount", f"type=volume,src={asdk},dst=/opt/android-sdk")
            self.assertFalse([x for x in a if "src=" + h + "/android-sdk" in x])
            self.assertNotIn("flutter-verrou", " ".join(a))
            self.assertEqual([a[i + 1] for i in range(len(a) - 1) if a[i] == "-e"],
                             ["HOME=/maison", "AGENT_DUREE_S=30", "AGENT_FLUTTER=1",
                              "PATH=/opt/outils:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"])
            for x in ("--read-only", "--rm", "-d"):                          # mêmes durcissements qu'un agent ordinaire
                self.assertIn(x, a)
            suite_dans(self, a, "--cap-drop", "ALL")
            suite_dans(self, a, "--security-opt", "no-new-privileges")
            suite_dans(self, a, "--pids-limit", "512")
            suite_dans(self, a, "--network", "myiafactory-agents")
            self.assertNotIn("--privileged", a)
            self.assertEqual(a[-2:], ["myiafactory/agent", "entree-agent"])
            self.assertEqual(len([a[i + 1] for i in range(len(a) - 1) if a[i] == "--mount"]), 5)     # + les trois commandes uniques
            self.assertEqual(b.appels("docker volume rm"), [])
            b.arreter()
            b.attendre_final()
            self.assertTrue([x for x in b.appels("docker volume rm") if vol in x], b.journal)   # retiré à la fin
            self.assertTrue([x for x in b.appels("docker volume rm") if asdk in x], b.journal)

    def test_overlay_android_refuse_echec_clair_et_volumes_retires(self):
        with Banc() as b:
            self.sdk(b)
            (b.home / "android-sdk").mkdir()
            b.ecrire_entree(flutter=True)
            (b.bin / "docker").rename(b.bin / "docker-banc")
            (b.bin / "docker").write_text(
                '#!/bin/sh\ncase "$*" in *verif-asdk-*) echo "docker $*" >> "$FAUX_JOURNAL"; exit 125;; esac\n'
                'exec "$(dirname "$0")/docker-banc" "$@"\n', newline="\n")
            (b.bin / "docker").chmod(0o755)
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
            self.assertFalse([x for x in b.appels("docker run") if x.startswith("docker run --pull never -d ")], b.journal)
            self.assertIn("SDK Android : overlay refusé", b.etat()["raison"])
            for vol in (f"flutter-{ID}", f"asdk-{ID}"):
                self.assertTrue([x for x in b.appels("docker volume rm") if vol in x], b.journal)

    def test_overlay_refuse_echec_clair_sans_agent_et_volume_retire(self):
        with Banc(FAUX_VERIF_CODE="125") as b:
            self.sdk(b)
            b.ecrire_entree(flutter=True)
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
            self.assertFalse([x for x in b.appels("docker run") if x.startswith("docker run --pull never -d ")], b.journal)
            e = b.etat()
            self.assertEqual((e["etat"], e["statut"]), ("echouee", "erreur"))
            self.assertIn("flutter : overlay refusé", e["raison"])
            self.assertTrue([x for x in b.appels("docker volume rm") if f"flutter-{ID}" in x], b.journal)
            self.assertNotIn("type=bind,src=", " ".join(b.run_args("verif.txt")))      # le volume seul, aucun dossier de l'hôte

    def test_docker_run_en_echec_retire_le_volume(self):
        with Banc(FAUX_RUN_ECHEC="1") as b:
            self.sdk(b)
            b.ecrire_entree(flutter=True)
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
            self.assertTrue([x for x in b.appels("docker volume rm") if f"flutter-{ID}" in x], b.journal)

    def test_balayage_des_volumes_de_taches_finies(self):
        with Banc() as b:
            self.sdk(b)
            b.ecrire_entree(flutter=True)
            finie, vivante = "t20261120-080000-aaaa", "t20261120-080000-bbbb"
            for ident, etat in ((finie, "terminee"), (vivante, "en_cours")):
                (b.home / "taches" / ident).mkdir(parents=True)
                (b.home / "taches" / ident / "etat.json").write_text(json.dumps({"id": ident, "etat": etat}),
                                                                         newline="\n")
            (b.bin / "docker").rename(b.bin / "docker-banc")
            (b.bin / "docker").write_text(
                '#!/bin/sh\nif [ "$1 $2" = "volume ls" ]; then echo "docker $*" >> "$FAUX_JOURNAL"; '
                f'printf "flutter-{finie}\\nflutter-{vivante}\\nflutter-x;rm\\nasdk-{finie}\\nasdk-{vivante}\\nautre\\n"; exit 0; fi\n'
                'exec "$(dirname "$0")/docker-banc" "$@"\n', newline="\n")
            (b.bin / "docker").chmod(0o755)
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            rm = b.appels("docker volume rm")
            self.assertEqual(rm, [f"docker volume rm flutter-{finie}", f"docker volume rm asdk-{finie}"], b.journal)
            b.arreter()
            b.attendre_final()

    def cle(self, b, lien=False):
        """Une FAUSSE clé de debug (jamais la vraie : aucun test n'en ouvre une) dans ~/android-signature."""
        d = b.home / "android-signature"
        d.mkdir()
        if lien:
            vraie = b.t / "ailleurs.keystore"
            vraie.write_bytes(b"FAUSSE")
            try:
                os.symlink(vraie, d / "debug.keystore")
            except OSError:
                self.skipTest("liens symboliques indisponibles")
            if not (d / "debug.keystore").is_symlink():
                self.skipTest("liens symboliques indisponibles")
        else:
            (d / "debug.keystore").write_bytes(b"FAUSSE")

    def test_cle_de_debug_du_poste_montee_en_lecture_seule(self):
        with Banc() as b:
            self.sdk(b)
            self.cle(b)
            b.ecrire_entree(flutter=True, signature="debug_serveur")     # réglage « Signature des APK » du projet
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            a, h = b.run_args(), b.h()
            suite_dans(self, a, "--mount",
                       f"type=bind,src={h}/android-signature/debug.keystore,dst=/maison/.android/debug.keystore,readonly")
            # la cible est créée AVANT par l'enveloppe (uid de l'hôte), vide : la clé ne s'écrit jamais dans maison/
            self.assertTrue((b.dossier / "maison" / ".android").is_dir())
            self.assertEqual((b.dossier / "maison" / ".android" / "debug.keystore").read_bytes(), b"")
            self.assertNotIn("android-signature", "".join(p.name for p in (b.dossier / "sortie").iterdir()))
            b.arreter()
            b.attendre_final()

    def test_cle_de_debug_presente_non_montee_sans_le_choix_du_projet(self):
        for valeur in (None, "aucune", "poste_signe"):
            with self.subTest(valeur=valeur), Banc() as b:
                self.sdk(b)
                self.cle(b)
                b.ecrire_entree(flutter=True, **({"signature": valeur} if valeur else {}))
                r = b.lancer("seul", "30", "2048", "2", "2")
                self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
                self.assertNotIn("debug.keystore", " ".join(b.run_args()))
                self.assertFalse((b.dossier / "maison" / ".android" / "debug.keystore").exists())
                b.arreter()
                b.attendre_final()

    def test_sans_cle_de_debug_pas_de_montage_ni_d_echec(self):
        with Banc() as b:
            self.sdk(b)
            b.ecrire_entree(flutter=True)
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertNotIn("debug.keystore", " ".join(b.run_args()))
            # ANDROID_USER_HOME : /maison/.android existe AVANT l'agent (créé par l'enveloppe, uid de l'hôte), clé ou non
            self.assertTrue((b.dossier / "maison" / ".android").is_dir())
            b.arreter()
            b.attendre_final()

    def test_cle_de_debug_qui_n_est_pas_un_fichier_ordinaire_refusee(self):
        with Banc() as b:
            self.sdk(b)
            self.cle(b, lien=True)
            b.ecrire_entree(flutter=True, signature="debug_serveur")
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
            self.assertFalse([x for x in b.appels("docker run") if x.startswith("docker run --pull never -d ")], b.journal)
            self.assertIn("clé de debug refusée", b.etat()["raison"].lower())
            # refusée avant toute copie sur écriture : aucun volume créé
            self.assertFalse([x for x in b.appels("docker volume create") if f"flutter-{ID}" in x], b.journal)

    def test_projet_non_flutter_inchange(self):
        for valeur in (None, False):
            with self.subTest(valeur=valeur), Banc() as b:
                self.sdk(b)
                self.cle(b)                                   # la clé est là, mais un projet non Flutter ne la reçoit pas
                if valeur is not None:
                    b.ecrire_entree(flutter=valeur)
                r = b.lancer("seul", "30", "2048", "2", "2")
                self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
                a = b.run_args()
                self.assertNotIn("--mount", a)
                self.assertNotIn("AGENT_FLUTTER=1", a)
                self.assertFalse((b.dossier / "flutter-up").exists())
                self.assertEqual(b.appels("docker volume"), [])
                b.arreter()
                b.attendre_final()

    def test_sdk_absent_ou_incomplet_refuse_sans_conteneur(self):
        for options in ({"creer": False}, {"lockfile": False}, {"marqueur": False}):
            with self.subTest(**options), Banc() as b:
                if options.pop("creer", True):
                    self.sdk(b, **options)
                b.ecrire_entree(flutter=True)
                r = b.lancer("seul", "30", "2048", "2", "2")
                self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
                self.assertEqual(b.appels("docker run"), [])
                e = b.etat()
                self.assertEqual((e["etat"], e["statut"]), ("echouee", "erreur"))
                self.assertIn("flutter-sdk", e["raison"])

    def test_valeur_ou_cle_douteuse_refusee(self):
        for texte in ('"flutter": "true",', '"flutter": 1,', '"flutter": true, "flutter": false,', '"flutter": truex,'):
            with self.subTest(texte=texte), Banc() as b:
                self.sdk(b)
                brut = (b.entree / "demande.json").read_text(encoding="utf-8")
                (b.entree / "demande.json").write_text(brut.replace('"places": 2', texte + ' "places": 2'), newline="\n")
                r = b.lancer("seul", "30", "2048", "2", "2")
                self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
                self.assertEqual(b.appels("docker run"), [])
                self.assertIn("flutter", b.etat()["raison"])


class TestEntreeFlutter(unittest.TestCase):
    def setUp(self):
        self.e = charger_entree()
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.racine = Path(self._t.name)

    def env(self, **plus):
        anciens = {k: os.environ.get(k) for k in ("AGENT_FLUTTER", "AGENT_RACINE")}
        os.environ.update(AGENT_RACINE=self.racine.as_posix(), **plus)
        if "AGENT_FLUTTER" not in plus:
            os.environ.pop("AGENT_FLUTTER", None)
        try:
            return self.e.environnement_flutter({"maison": "/maison"}, "/usr/local/bin:/usr/bin:/bin")
        finally:
            for k, v in anciens.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_jdk_17_dans_l_image_agent(self):
        dockerfile = (RACINE / "serveur_ovh" / "images" / "agent" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("openjdk-17-jdk-headless", dockerfile)
        self.assertEqual(self.e.JAVA_RACINE, "/usr/lib/jvm/java-17-openjdk-amd64")

    def test_image_agent_inchangee_par_l_overlay(self):
        self.assertNotIn("overlay", (RACINE / "serveur_ovh" / "images" / "agent" / "entree-agent.py").read_text(encoding="utf-8"))

    def test_variables_fixes_seulement_pour_un_projet_flutter(self):
        self.assertEqual(self.env(), {})
        for autre in ("0", "true", "1 ", "/opt/x"):
            self.assertEqual(self.env(AGENT_FLUTTER=autre), {}, autre)
        v = self.env(AGENT_FLUTTER="1")
        self.assertEqual(v, {"PATH": "/opt/flutter-sdk/bin:/usr/local/bin:/usr/bin:/bin", "FLUTTER_ROOT": "/opt/flutter-sdk",
                             "PUB_CACHE": os.path.join("/maison", ".pub-cache"), "FLUTTER_SUPPRESS_ANALYTICS": "true",
                             "CI": "true", "JAVA_HOME": "/usr/lib/jvm/java-17-openjdk-amd64",
                             "GRADLE_USER_HOME": os.path.join("/maison", ".gradle"),
                             # la JVM prend user.home dans /etc/passwd (/home/<utilisateur>, en lecture seule) : tout
                             # ce qu'AGP et Java écrivent sous ~/.android va sous /maison
                             "ANDROID_USER_HOME": os.path.join("/maison", ".android"),
                             "ANDROID_EMULATOR_HOME": os.path.join("/maison", ".android"),
                             "ANDROID_AVD_HOME": os.path.join("/maison", ".android", "avd"),
                             "JAVA_TOOL_OPTIONS": "-Duser.home=/maison"})
        (self.racine / "opt" / "android-sdk").mkdir(parents=True)
        v = self.env(AGENT_FLUTTER="1")
        self.assertEqual((v["ANDROID_HOME"], v["ANDROID_SDK_ROOT"]), ("/opt/android-sdk", "/opt/android-sdk"))
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", v)


class TestDetectionPoste(unittest.TestCase):
    PUBSPEC = ("name: fm_stats\nenvironment:\n  sdk: '>=3.4.0 <4.0.0'\n  flutter: \">=3.22.0\"\n"
               "dependencies:\n  flutter:\n    sdk: flutter\n  http: ^1.2.0\n"
               "dev_dependencies:\n  flutter_test:\n    sdk: flutter\nflutter:\n  uses-material-design: true\n")

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.p = Path(self._t.name)

    def ecrire(self, rel, texte):
        f = self.p / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(texte, encoding="utf-8", newline="\n")

    def test_dependance_flutter_dans_dependencies_seulement(self):
        self.assertTrue(projet_flutter.depend_de_flutter(self.PUBSPEC))
        self.assertTrue(projet_flutter.depend_de_flutter("dependencies:  # dépendances\n    flutter:  # sdk\n      sdk: 'flutter'\n"))
        for faux in ("name: x\ndependencies:\n  http: ^1.0.0\nflutter:\n  sdk: flutter\n",          # flutter: de premier niveau
                     "dev_dependencies:\n  flutter:\n    sdk: flutter\n",                               # pas dans dependencies
                     "dependencies:\n  flutter: ^1.0.0\n",                                            # paquet pub, pas le SDK
                     "dependencies:\n  http:\n    flutter:\n      sdk: flutter\n",                    # imbriqué
                     "dependencies:\n  flutter:\n", "", None, 3):
            self.assertFalse(projet_flutter.depend_de_flutter(faux), repr(faux))

    def test_racine_puis_sous_dossier_direct(self):
        self.assertIsNone(projet_flutter.dossier_flutter(self.p))
        self.ecrire("android_app/pubspec.yaml", self.PUBSPEC)                   # FM_Stats
        self.assertEqual(projet_flutter.dossier_flutter(self.p), "android_app")
        self.assertTrue(projet_flutter.est_flutter(self.p))
        self.ecrire("pubspec.yaml", self.PUBSPEC)
        self.assertEqual(projet_flutter.dossier_flutter(self.p), ".")

    def test_dossiers_caches_construction_et_profonds_ignores(self):
        for rel in (".cache/pubspec.yaml", "build/pubspec.yaml", "a/b/pubspec.yaml", "node_modules/pubspec.yaml"):
            self.ecrire(rel, self.PUBSPEC)
        self.ecrire("outil/pubspec.yaml", "name: dart_seul\ndependencies:\n  args: ^2.0.0\n")
        self.assertIsNone(projet_flutter.dossier_flutter(self.p))
        self.assertIsNone(projet_flutter.dossier_flutter(self.p / "absent"))

    def test_version_demandee_bornee(self):
        self.ecrire("pubspec.yaml", self.PUBSPEC)
        self.assertEqual(projet_flutter.version_demandee(self.p), (">=3.22.0", "pubspec.yaml"))
        self.ecrire(".fvmrc", json.dumps({"flutter": VERSION}))
        self.assertEqual(projet_flutter.version_demandee(self.p), (VERSION, ".fvmrc"))
        self.ecrire(".fvmrc", json.dumps({"flutter": "3.47.1; rm -rf /"}))
        self.assertEqual(projet_flutter.version_demandee(self.p), (">=3.22.0", "pubspec.yaml"))
        self.ecrire("pubspec.yaml", "environment:\n  flutter: \"$(id)\"\n")
        self.assertEqual(projet_flutter.version_demandee(self.p), (None, None))

    def test_executeur_dit_flutter_par_un_booleen(self):
        from moteur import executeur_serveur as es
        self.assertIs(es._projet_flutter(self.p), False)
        self.ecrire("android_app/pubspec.yaml", self.PUBSPEC)
        self.assertIs(es._projet_flutter(self.p), True)


class TestDemandeFlutter(Base):
    def test_champ_flutter_booleen_ferme(self):
        self.assertIs(self.demande().flutter, False)
        self.assertIs(self.demande(flutter=True).flutter, True)
        for mauvais in ("true", 1, 0, None, "flutter", [True]):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                self.demande(flutter=mauvais)

    def test_demande_json_et_capacites(self):
        d = self.demande(flutter=True)
        self.assertEqual(sa.capacites_requises(d), ("agent", "agent-abonnement", "flutter-sdk"))
        self.assertEqual(sa.capacites_requises(self.demande(mode="pilote", flutter=True)),
                         ("agent", "agent-abonnement", "emulateur-image", "flutter-sdk"))
        self.assertEqual(sa.capacites_requises(self.demande()), ("agent", "agent-abonnement"))
        with self.assertRaises(st.RefusLancement):                   # le serveur n'a pas flutter-sdk : rien n'est envoyé
            self.lancer(d)
        self.assertEqual(self.srv.ops("preparer_agent"), [])
        declarer(self.dossier, [("ovh1", {**CAPS_AGENT, "flutter-sdk": "presente"})])
        r = self.lancer(d)
        self.assertEqual(r["etat"], "en_cours")
        texte = self.srv.entrees[ID1]["entree/demande.json"].decode("utf-8")
        self.assertIs(json.loads(texte)["flutter"], True)
        self.assertEqual(texte.count('"flutter":'), 1)                # relu par motif strict sur le serveur

    def test_demande_ordinaire_dit_false(self):
        self.lancer()
        self.assertIs(json.loads(self.srv.entrees[ID1]["entree/demande.json"])["flutter"], False)


if __name__ == "__main__":
    unittest.main()
