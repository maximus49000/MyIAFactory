"""Enveloppe hôte de l'émulation (`serveur_ovh/taches/lancer_emulation.sh`) : lancée avec le bash du poste, `sudo`, `docker`,
`flock`, `setsid`, `timeout` et `getent` factices dans le PATH (ils journalisent leurs appels). Aucun vrai conteneur."""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent / "serveur_ovh"
SCRIPT = RACINE / "taches" / "lancer_emulation.sh"
ID = "t20261119-101500-ab12"
CLES_ETAT = {"id", "etat", "statut", "debut", "fin", "raison"}

DOCKER = r'''echo "docker $*" >> "$FAUX_JOURNAL"
ET="$FAUX_ETAT"
case "$1" in
  run) [ -n "${FAUX_RUN_ECHEC:-}" ] && { echo "boom" >&2; exit 125; }
       printf '%s\n' "$@" > "$ET/run.txt"; touch "$ET/vivant"; echo cid123 ;;
  ps) n=$(cat "$ET/ps" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$ET/ps"
      if [ -n "${FAUX_MEURT_AU_PS:-}" ] && [ "$n" -ge "$FAUX_MEURT_AU_PS" ]; then rm -f "$ET/vivant"; fi
      [ -e "$ET/vivant" ] && echo cid123
      exit 0 ;;
  stop|kill|rm) [ -n "${FAUX_STOP_ECHEC:-}" ] && exit 1; rm -f "$ET/vivant" ;;
esac
exit 0'''
FAUX = {
    "sudo": 'exec "$@"',
    "docker": DOCKER,
    "flock": 'echo "flock $*" >> "$FAUX_JOURNAL"\n[ -n "${FAUX_FLOCK_OCCUPE:-}" ] && [ "$1" = -n ] && exit 1\nexit 0',
    "setsid": 'echo "setsid $*" >> "$FAUX_JOURNAL"\nexec "$@"',
    "timeout": 'echo "timeout $*" >> "$FAUX_JOURNAL"\nshift\nexec "$@"',
    "getent": '[ -n "${FAUX_SANS_KVM:-}" ] && exit 2\necho "kvm:x:993:"',
}


class Banc:
    def __init__(self, **env):
        self.env = env

    def __enter__(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        t = self.t = Path(self._t.name)
        self.home, self.bin, self.et = t / "home", t / "bin", t / "etat"
        for d in (self.home, self.bin, self.et):
            d.mkdir()
        self.journal_fichier = t / "appels.txt"
        for nom, corps in FAUX.items():
            (self.bin / nom).write_text("#!/bin/sh\n" + corps + "\n", newline="\n")
            (self.bin / nom).chmod(0o755)
        self.dossier = self.home / "taches" / ID
        return self

    def __exit__(self, *a):
        pid = self.dossier / "veilleur.pid"
        if pid.exists():
            subprocess.run(["bash", "-c", 'kill -9 "$(cat "$1")" 2>/dev/null; exit 0', "bash", pid.as_posix()])
        time.sleep(0.3)
        self._t.cleanup()

    def lancer(self, *args, env=None, ident=ID):
        e = dict(os.environ, HOME=self.home.as_posix(), PATH=self.bin.as_posix() + os.pathsep + os.environ["PATH"],
                 FAUX_JOURNAL=self.journal_fichier.as_posix(), FAUX_ETAT=self.et.as_posix(), ENVELOPPE_SONDE_S="0.2")
        e.update(self.env)
        e.update(env or {})
        corps = list(args) if args else ["scenario", "30", "30", "2048", "2"]
        debut = time.time()
        self.derniere = subprocess.run(["bash", SCRIPT.as_posix(), ident, *corps], stdin=subprocess.DEVNULL, capture_output=True,
                                       text=True, encoding="utf-8", env=e, timeout=30)
        self.duree = time.time() - debut
        return self.derniere

    @property
    def journal(self):
        return self.journal_fichier.read_text(encoding="utf-8") if self.journal_fichier.exists() else ""

    def appels(self, prefixe):
        return [x for x in self.journal.splitlines() if x.startswith(prefixe)]

    def etat(self):
        return json.loads((self.dossier / "etat.json").read_text(encoding="utf-8"))

    def attendre_final(self, delai=20):
        """Attend l'état final ET le déverrouillage du créneau (dernier geste de l'enveloppe)."""
        fin = time.time() + delai
        while time.time() < fin:
            if self.appels("flock -u") and (self.dossier / "etat.json").exists() and self.etat()["etat"] not in ("en_cours", "en_attente"):
                return self.etat()
            time.sleep(0.1)
        self.fail_texte = self.journal
        raise AssertionError(f"état final jamais atteint : {(self.dossier / 'etat.json').read_text() if (self.dossier / 'etat.json').exists() else None}\n{self.journal}")

    def arreter(self):
        (self.dossier / "arret").write_text("", newline="\n")

    def run_args(self):
        return (self.et / "run.txt").read_text(encoding="utf-8").splitlines()


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEnveloppe(unittest.TestCase):
    def test_enveloppe_prend_le_creneau_et_ecrit_l_etat(self):
        with Banc() as b:
            r = b.lancer()
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertLess(b.duree, 10)                          # rend la main : le veilleur est détaché
            lignes = [x for x in r.stdout.splitlines() if x.strip()]
            self.assertEqual(len(lignes), 1, r.stdout)
            self.assertEqual(json.loads(lignes[0])["etat"], "en_cours")
            e = b.etat()
            self.assertEqual(set(e), CLES_ETAT)
            self.assertEqual((e["id"], e["etat"]), (ID, "en_cours"))
            self.assertRegex(e["debut"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
            self.assertIsNone(e["fin"])
            self.assertIsNone(e["statut"])
            self.assertTrue((b.dossier / "entree").is_dir() and (b.dossier / "sortie").is_dir())
            self.assertTrue(b.appels("flock -n 8"), b.journal)
            self.assertTrue(b.appels("setsid "), b.journal)
            b.arreter()
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("arretee", "ok"))
            self.assertRegex(f["fin"], r"^\d{4}-")
            self.assertTrue(f["raison"])
            self.assertEqual(sorted(x.name for x in b.dossier.glob("etat.json*")), ["etat.json"])    # écriture atomique : aucun reste
            self.assertTrue(any(x.startswith("docker stop") and f"tache-{ID}" in x for x in b.journal.splitlines()), b.journal)
            self.assertLess(b.journal.index("docker stop"), b.journal.index("flock -u"))

    def test_enveloppe_creneau_occupe_donne_75_et_en_attente(self):
        with Banc(FAUX_FLOCK_OCCUPE="1") as b:
            r = b.lancer()
            self.assertEqual(r.returncode, 75, r.stderr)
            e = b.etat()
            self.assertEqual((e["etat"], e["statut"]), ("en_attente", None))
            self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])["etat"], "en_attente")
            self.assertEqual(b.appels("docker"), [])
            self.assertEqual(b.appels("setsid"), [])

    def test_enveloppe_libere_le_creneau_si_le_conteneur_meurt(self):
        with Banc(FAUX_MEURT_AU_PS="3") as b:
            self.assertEqual(b.lancer().returncode, 0)
            f = b.attendre_final()                                # jamais « en cours » pour toujours
            self.assertEqual((f["etat"], f["statut"]), ("echouee", "erreur"))
            self.assertTrue(b.appels("flock -u"))

    def test_conteneur_mort_apres_un_plantage_releve(self):
        with Banc(FAUX_MEURT_AU_PS="3") as b:
            (b.dossier / "sortie").mkdir(parents=True)
            (b.dossier / "sortie" / "plantage.txt").write_text("FATAL EXCEPTION", newline="\n")
            self.assertEqual(b.lancer().returncode, 0)
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "plantage"))

    def test_enveloppe_arret_par_fichier(self):
        with Banc() as b:
            self.assertEqual(b.lancer().returncode, 0)
            self.assertEqual(b.etat()["etat"], "en_cours")
            time.sleep(0.6)
            self.assertEqual(b.etat()["etat"], "en_cours")        # rien ne l'arrête sans le fichier
            (b.dossier / "sortie" / "plantage.txt").write_text("ANR in com.exemple", newline="\n")
            b.arreter()
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("arretee", "plantage"))
            self.assertIn("arrêt", f["raison"].lower())

    def test_echeance_fait_passer_l_etat_en_limite(self):
        with Banc() as b:
            self.assertEqual(b.lancer("scenario", "1", "30", "2048", "2").returncode, 0)
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))
            self.assertIn("durée", f["raison"].lower())
            self.assertTrue(b.appels("docker stop"), b.journal)
            self.assertTrue(b.appels("flock -u"))

    def test_inactivite_du_pilote_arrete_la_tache_mais_pas_le_scenario(self):
        with Banc() as b:
            self.assertEqual(b.lancer("pilote", "60", "3", "2048", "2").returncode, 0)
            sortie = b.dossier / "sortie"
            sortie.mkdir(parents=True, exist_ok=True)
            for _ in range(8):                                    # l'activité (pont.log) repousse la limite
                (sortie / "pont.log").write_text(f"toucher 1 2 {time.time()}\n", newline="\n")
                time.sleep(0.5)
                self.assertEqual(b.etat()["etat"], "en_cours")
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))
            self.assertIn("inactivité", f["raison"].lower())
        with Banc() as b:
            self.assertEqual(b.lancer("scenario", "60", "1", "2048", "2").returncode, 0)
            time.sleep(2.5)
            self.assertEqual(b.etat()["etat"], "en_cours")        # la limite d'inactivité ne vaut que pour le pilote
            b.arreter()
            self.assertEqual(b.attendre_final()["etat"], "arretee")

    def test_conteneur_sans_reseau_ni_identifiants(self):
        with Banc(SECRET_DU_POSTE="jeton-secret-42", ANTHROPIC_API_KEY="cle-secrete-43") as b:
            self.assertEqual(b.lancer().returncode, 0)
            a = b.run_args()
            texte = "\n".join(a)
            h = subprocess.run(["bash", "-c", 'printf %s "$HOME"'], env=dict(os.environ, HOME=b.home.as_posix()),
                               capture_output=True, text=True).stdout      # HOME tel que bash le voit (/tmp/... sous Git bash)

            def suite(*motif):
                self.assertTrue(any(a[i:i + len(motif)] == list(motif) for i in range(len(a))), f"{motif} absent de {a}")

            self.assertEqual(a[:3], ["run", "--rm", "-d"])
            self.assertIn("--init", a)
            self.assertIn("--read-only", a)
            suite("--network", "none")
            suite("--device", "/dev/kvm")
            suite("--user", "1000:1000")
            suite("--group-add", "993")
            suite("--name", f"tache-{ID}")
            suite("--memory", "2048m")
            suite("--cpus", "2")
            suite("--tmpfs", "/avd:size=4g,mode=1777")
            self.assertTrue(any(x.startswith("/tmp") for i, x in enumerate(a) if i and a[i - 1] == "--tmpfs"), a)
            suite("--cap-drop", "ALL")
            suite("--security-opt", "no-new-privileges")
            volumes = [a[i + 1] for i in range(len(a) - 1) if a[i] == "-v"]
            self.assertEqual(sorted(volumes), sorted([f"{h}/android-sdk:/opt/android-sdk:ro", f"{h}/taches/{ID}/entree:/entree:ro",
                                                      f"{h}/taches/{ID}/sortie:/sortie"]))
            self.assertEqual(a[-1], "myiafactory/emulateur")
            envs = [a[i + 1] for i in range(len(a) - 1) if a[i] == "-e"]
            for attendu in ("ANDROID_AVD_HOME=/avd", "HOME=/tmp", "PONT_SORTIE=/sortie", "PONT_AVD=emul"):
                self.assertIn(attendu, envs)
            self.assertTrue(all("=" in x for x in envs), envs)     # jamais « -e NOM » : ce serait l'environnement de l'appelant
            self.assertNotIn("--env-file", a)
            for secret in ("jeton-secret-42", "cle-secrete-43", ".ssh", ".claude", "credentials", ".credentials", "ANTHROPIC"):
                self.assertNotIn(secret, texte)
            self.assertNotIn("--privileged", a)
            b.arreter()
            b.attendre_final()

    def test_docker_run_en_echec_est_une_erreur_et_libere_le_creneau(self):
        with Banc(FAUX_RUN_ECHEC="1") as b:
            r = b.lancer()
            self.assertEqual(r.returncode, 1, r.stderr)
            e = b.etat()
            self.assertEqual((e["etat"], e["statut"]), ("echouee", "erreur"))
            self.assertTrue(e["fin"])
            self.assertTrue(b.appels("flock -u"))

    def test_groupe_kvm_absent_est_une_erreur_nette(self):
        with Banc(FAUX_SANS_KVM="1") as b:
            r = b.lancer()
            self.assertEqual(r.returncode, 1)
            self.assertEqual(b.etat()["statut"], "erreur")
            self.assertIn("kvm", b.etat()["raison"].lower())
            self.assertEqual(b.appels("docker run"), [])

    def test_une_tache_deja_en_cours_n_est_pas_ecrasee(self):
        with Banc() as b:
            b.dossier.mkdir(parents=True)
            avant = json.dumps({"id": ID, "etat": "en_cours", "statut": None, "debut": "2026-11-19T10:00:00Z", "fin": None, "raison": ""})
            (b.dossier / "etat.json").write_text(avant, newline="\n")
            r = b.lancer()
            self.assertEqual(r.returncode, 3, r.stderr)
            self.assertEqual((b.dossier / "etat.json").read_text(), avant)
            self.assertEqual(b.appels("docker"), [])

    def test_arguments_hostiles_refuses_sans_rien_creer(self):
        mauvais_ids = ["../x", "t20261119-101500-zzzz", f"{ID};ls", f"{ID}\nx", "", "t20261119-101500-ab12/../..", " " + ID]
        mauvais_params = [("autre", "30", "30", "2048", "2"), ("scenario", "0", "30", "2048", "2"), ("scenario", "-1", "30", "2048", "2"),
                          ("scenario", "1e3", "30", "2048", "2"), ("scenario", "99999999", "30", "2048", "2"),
                          ("scenario", "30", "030", "2048", "2"), ("scenario", "30", "30", "1;ls", "2"),
                          ("scenario", "30", "30", "2048", "0"), ("scenario", "30", "30", "2048", "$(id)"),
                          ("scenario", "30", "30", "2048", "2", "en-trop")]
        with Banc() as b:
            for ident in mauvais_ids:
                with self.subTest(ident=ident):
                    self.assertEqual(b.lancer(ident=ident).returncode, 2)
            for p in mauvais_params:
                with self.subTest(p=p):
                    self.assertEqual(b.lancer(*p).returncode, 2)
            self.assertFalse((b.home / "taches").exists())
            self.assertEqual(b.journal, "")

    def test_valeurs_par_defaut_et_arguments_facultatifs(self):
        with Banc() as b:
            self.assertEqual(b.lancer("pilote").returncode, 0)
            self.assertEqual(b.etat()["etat"], "en_cours")
            self.assertIn("--memory", b.run_args())
            b.arreter()
            b.attendre_final()

    def test_script_syntaxe_lf_et_sans_eval(self):
        self.assertEqual(subprocess.run(["bash", "-n", SCRIPT.as_posix()], capture_output=True).returncode, 0)
        octets = SCRIPT.read_bytes()
        self.assertNotIn(b"\r", octets)
        code = "\n".join(x for x in octets.decode("utf-8").splitlines() if not x.lstrip().startswith("#"))
        self.assertNotRegex(code, r"\beval\b")
        self.assertNotRegex(code, r"(^|[^\w.-])bash\s+-c\b")
        self.assertNotRegex(code, r"(?m)^\s*set -[a-z]*e")


if __name__ == "__main__":
    unittest.main()
