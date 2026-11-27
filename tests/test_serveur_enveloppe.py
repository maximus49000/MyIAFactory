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
  network) [ -n "${FAUX_RESEAU_ECHEC:-}" ] && [ "$2" = create ] && { echo "network boom" >&2; exit 1; }; exit 0 ;;
  run) case "$*" in *genre=proxy*) [ -n "${FAUX_PROXY_ECHEC:-}" ] && { echo "proxy boom" >&2; exit 125; }; printf '%s\n' "$@" > "$ET/run-proxy.txt"; echo cidproxy; exit 0 ;; esac
       echo "run-vu: pid=$([ -s "$FAUX_DOSSIER/enveloppe.pid" ] && echo oui || echo non) etat=$(cat "$FAUX_DOSSIER/etat.json")" >> "$FAUX_JOURNAL"
       [ -n "${FAUX_RUN_ECHEC:-}" ] && { echo "boom" >&2; exit 125; }
       printf '%s\n' "$@" > "$ET/run.txt"; touch "$ET/vivant"; echo cid123 ;;
  ps|inspect)   # un seul compteur de contrôles : « ps » de l'enveloppe puis « inspect » du veilleur
      n=$(cat "$ET/ps" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$ET/ps"
      if [ -n "${FAUX_MEURT_AU_PS:-}" ] && [ "$n" -ge "$FAUX_MEURT_AU_PS" ]; then rm -f "$ET/vivant"; fi
      [ -n "${FAUX_ARRET_AU_PS:-}" ] && [ "$n" = 1 ] && echo > "$FAUX_ARRET_AU_PS"
      if [ "$1" = inspect ]; then
        [ -n "${FAUX_DOCKER_MUET:-}" ] && { echo "Cannot connect to the Docker daemon" >&2; exit 1; }
        [ -n "${FAUX_INSPECT_AVERTIT:-}" ] && echo "sudo: unable to resolve host serveur: Name or service not known" >&2
        [ -n "${FAUX_INSPECT_ILLISIBLE:-}" ] && { echo "WARNING: something odd"; exit 0; }
        if [ -e "$ET/vivant" ]; then
          p=999999; [ -n "${FAUX_PID_VEILLEUR:-}" ] && p=$(cat "$FAUX_DOSSIER/veilleur.pid")
          echo "true $p"; exit 0
        fi
        if [ -n "${FAUX_INSPECT_MINUSCULE:-}" ]; then echo "error: no such object: tache-x" >&2; exit 1; fi   # le vrai docker
        echo "Error: No such object: tache-x" >&2; exit 1
      fi
      [ -n "${FAUX_CONTENEUR_EXISTE:-}" ] && echo cidautre
      [ -e "$ET/vivant" ] && echo cid123
      exit 0 ;;
  stop|kill|rm) case "$*" in *tache-*) [ -n "${FAUX_STOP_ECHEC:-}" ] && exit 1; rm -f "$ET/vivant" ;; esac ;;
esac
exit 0'''
FAUX = {
    "sudo": '[ "$1" = -n ] && shift\nexec "$@"',
    "docker": DOCKER,
    # FAUX_FLOCK_ARRETEE : un `arreter` du lanceur passe pendant l'attente du créneau (il écrit l'état final arretee)
    "flock": 'echo "flock $*" >> "$FAUX_JOURNAL"\n'
             '[ -n "${FAUX_FLOCK_ARRETEE:-}" ] && [ "$1" = -n ] && printf \'%s\\n\' "$FAUX_FLOCK_ARRETEE" > "$FAUX_DOSSIER/etat.json"\n'
             '[ -n "${FAUX_FLOCK_OCCUPE:-}" ] && [ "$1" = -n ] && exit 1\nexit 0',
    "setsid": 'echo "setsid $*" >> "$FAUX_JOURNAL"\n[ -n "${FAUX_SETSID_DELAI:-}" ] && sleep "$FAUX_SETSID_DELAI"\nexec "$@"',
    # date : note l'état au moment où le veilleur... non : au moment où l'enveloppe écrit en_cours (premier appel après enveloppe.pid)
    "date": 'echo "date: pid=$([ -s "$FAUX_DOSSIER/enveloppe.pid" ] && echo oui || echo non) etat=$(cat "$FAUX_DOSSIER/etat.json" 2>/dev/null)" >> "$FAUX_JOURNAL"\nexec /usr/bin/date "$@"',
    "timeout": 'echo "timeout $*" >> "$FAUX_JOURNAL"\nshift\nexec "$@"',
    "getent": '[ "$1" = ahostsv4 ] && { for ip in ${FAUX_IP_HOTE-93.184.216.34}; do echo "$ip STREAM $2"; done; exit 0; }\n'
              '[ -n "${FAUX_SANS_KVM:-}" ] && exit 2\necho "kvm:x:993:"',
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
                 FAUX_JOURNAL=self.journal_fichier.as_posix(), FAUX_ETAT=self.et.as_posix(), ENVELOPPE_SONDE_S="0.2", FAUX_DOSSIER=self.dossier.as_posix())
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
            self.assertEqual(b.lancer("scenario", "30", "30", "6144", "2").returncode, 0)
            a = b.run_args()
            texte = "\n".join(a)
            h = subprocess.run(["bash", "-c", 'printf %s "$HOME"'], env=dict(os.environ, HOME=b.home.as_posix()),
                               capture_output=True, text=True).stdout      # HOME tel que bash le voit (/tmp/... sous Git bash)

            def suite(*motif):
                self.assertTrue(any(a[i:i + len(motif)] == list(motif) for i in range(len(a))), f"{motif} absent de {a}")

            self.assertEqual(a[0], "run")
            self.assertIn("--rm", a)
            self.assertIn("-d", a)
            self.assertIn("--init", a)
            self.assertIn("--read-only", a)
            suite("--network", "none")
            suite("--device", "/dev/kvm")
            suite("--user", "1000:1000")
            suite("--group-add", "993")
            suite("--name", f"tache-{ID}")
            suite("--memory", "6144m")
            suite("--cpus", "2")
            # 9 Go (plafond tmpfs, non réservé) : l'émulateur copie system.img (4,3 Go) dans l'AVD et exige ~7,4 Go libres
            suite("--tmpfs", "/avd:size=9g,mode=1777")
            self.assertTrue(any(x.startswith("/tmp") for i, x in enumerate(a) if i and a[i - 1] == "--tmpfs"), a)
            suite("--cap-drop", "ALL")
            suite("--security-opt", "no-new-privileges")
            montages = [a[i + 1] for i in range(len(a) - 1) if a[i] == "--mount"]
            self.assertEqual(sorted(montages), sorted([f"type=bind,src={h}/android-sdk,dst=/opt/android-sdk,readonly",
                                                       f"type=bind,src={h}/taches/{ID}/entree,dst=/entree,readonly",
                                                       f"type=bind,src={h}/taches/{ID}/sortie,dst=/sortie"]))
            self.assertNotIn("-v", a)                                # --mount : un chemin absent est une erreur, jamais créé par root
            suite("--pull", "never")                                 # une image locale absente échoue, jamais tirée d'un registre
            suite("--pids-limit", "512")
            suite("--memory-swap", "6144m")
            suite("--ulimit", "nofile=4096:4096")
            self.assertEqual(a[-1], "myiafactory/emulateur")
            envs = [a[i + 1] for i in range(len(a) - 1) if a[i] == "-e"]
            for attendu in ("ANDROID_AVD_HOME=/avd", "HOME=/tmp", "ANDROID_USER_HOME=/tmp/.android", "PONT_SORTIE=/sortie", "PONT_AVD=emul",
                            "TACHE_IMAGE_SYSTEME=system-images;android-34;google_apis;x86_64"):
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

    def _etat_ecrit(self, b, etat, statut=None):
        b.dossier.mkdir(parents=True, exist_ok=True)
        texte = json.dumps({"id": ID, "etat": etat, "statut": statut, "debut": "2026-11-19T10:00:00Z", "fin": None, "raison": "x"})
        (b.dossier / "etat.json").write_text(texte, newline="\n")
        return texte

    def test_une_tache_en_cours_avec_veilleur_vivant_rend_3_sans_rien_modifier(self):
        with Banc() as b:
            avant = self._etat_ecrit(b, "en_cours")
            pidfile = (b.dossier / "veilleur.pid").as_posix()
            # un faux veilleur : sa ligne de commande porte le marqueur et l'identifiant, son PID (celui de bash) est dans le fichier
            p = subprocess.Popen(["bash", "-c", 'echo $$ > "$PIDFILE"; sleep 40; true', "faux", "--veilleur", ID],
                                 env=dict(os.environ, PIDFILE=pidfile), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(50):
                    if (b.dossier / "veilleur.pid").exists() and (b.dossier / "veilleur.pid").read_text().strip():
                        break
                    time.sleep(0.1)
                r = b.lancer()
                self.assertEqual(r.returncode, 3, r.stderr)
                self.assertEqual((b.dossier / "etat.json").read_text(), avant)
                self.assertEqual(b.appels("docker"), [])
            finally:
                p.kill()
                p.wait()

    def _faux_processus(self, b, fichier, *arguments):
        """Un processus vivant dont la ligne de commande porte `arguments` et dont le PID (celui de bash) est dans `fichier`."""
        p = subprocess.Popen(["bash", "-c", 'echo $$ > "$PIDFILE"; sleep 40; true', *arguments],
                             env=dict(os.environ, PIDFILE=(b.dossier / fichier).as_posix()), stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (p.kill(), p.wait()))
        for _ in range(50):
            if (b.dossier / fichier).exists() and (b.dossier / fichier).read_text().strip():
                return p
            time.sleep(0.1)
        self.fail("faux processus non démarré")

    def test_un_demarrage_en_cours_rend_3_tant_que_l_enveloppe_vit_sans_veilleur(self):
        # en_cours est écrit, docker run peut durer 120 s, veilleur.pid vient plus tard : un second lancement n'est jamais « mort »
        with Banc() as b:
            avant = self._etat_ecrit(b, "en_cours")
            self._faux_processus(b, "enveloppe.pid", "lancer_emulation.sh", ID)
            r = b.lancer()
            self.assertEqual(r.returncode, 3, r.stderr)
            self.assertEqual((b.dossier / "etat.json").read_text(), avant)
            self.assertEqual(b.appels("docker"), [])

    def test_enveloppe_et_veilleur_morts_ou_etrangers_rendent_4(self):
        with Banc() as b:
            avant = self._etat_ecrit(b, "en_cours")
            (b.dossier / "veilleur.pid").write_text("999999\n", newline="\n")
            (b.dossier / "enveloppe.pid").write_text("999999\n", newline="\n")
            self.assertEqual(b.lancer().returncode, 4)
            # vivant mais sans la ligne de commande attendue (pid recyclé) : pas une enveloppe
            self._faux_processus(b, "enveloppe.pid", "autre-programme", ID)
            self.assertEqual(b.lancer().returncode, 4)
            self.assertEqual((b.dossier / "etat.json").read_text(), avant)

    def test_enveloppe_pid_ecrit_avant_en_cours_et_veilleur_pid_au_retour(self):
        with Banc() as b:
            self.assertEqual(b.lancer().returncode, 0)
            self.assertIn("pid=oui", "".join(b.appels("run-vu:")))              # présent quand docker run tourne
            self.assertIn('"etat": "en_cours"', "".join(b.appels("run-vu:")))
            self.assertTrue((b.dossier / "enveloppe.pid").read_text().strip().isdigit())
            self.assertTrue((b.dossier / "veilleur.pid").exists())               # l'enveloppe attend le PID du veilleur avant de rendre la main
            b.arreter()
            b.attendre_final()

    def test_enveloppe_pid_existe_avant_que_en_cours_ne_soit_ecrit(self):
        with Banc() as b:
            self.assertEqual(b.lancer().returncode, 0)
            premier = b.appels("date:")[0]                                       # le 1er appel de date : l'horodatage de l'écriture en_cours
            self.assertIn("pid=oui", premier)
            self.assertNotIn('"etat": "en_cours"', premier)                      # en_cours n'est pas encore écrit à ce moment
            b.arreter()
            b.attendre_final()

    def test_l_enveloppe_attend_le_pid_d_un_veilleur_lent(self):
        with Banc(FAUX_SETSID_DELAI="1") as b:                                   # le veilleur ne démarre qu'après ~1 s
            self.assertEqual(b.lancer().returncode, 0)
            self.assertGreaterEqual(b.duree, 0.9)                                # l'enveloppe a attendu
            self.assertTrue((b.dossier / "veilleur.pid").exists())               # et ne rend la main qu'avec veilleur.pid
            b.arreter()
            b.attendre_final()

    def test_avd_pret_compte_comme_activite_du_pilote(self):
        with Banc() as b:
            self.assertEqual(b.lancer("pilote", "60", "3", "2048", "2").returncode, 0)
            for _ in range(8):                                    # l'AVD vient d'être créé : le conteneur travaille, rien d'autre encore
                (b.dossier / "sortie" / ".avd-pret").write_text("", newline="\n")
                time.sleep(0.5)
                self.assertEqual(b.etat()["etat"], "en_cours")
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))

    def test_captures_et_octets_facultatifs_passes_au_conteneur(self):
        with Banc() as b:
            self.assertEqual(b.lancer("scenario", "30", "30", "2048", "2", "20", "5000000").returncode, 0)
            envs = [b.run_args()[i + 1] for i, x in enumerate(b.run_args()[:-1]) if x == "-e"]
            self.assertIn("PONT_CAPTURES=20", envs)
            self.assertIn("PONT_OCTETS=5000000", envs)
            self.assertTrue(all("=" in x for x in envs), envs)
            b.arreter()
            b.attendre_final()
        with Banc() as b:                                                         # captures seul, puis rien : pas de réglage inventé
            self.assertEqual(b.lancer("scenario", "30", "30", "2048", "2", "50").returncode, 0)
            envs = [b.run_args()[i + 1] for i, x in enumerate(b.run_args()[:-1]) if x == "-e"]
            self.assertIn("PONT_CAPTURES=50", envs)
            self.assertFalse([x for x in envs if x.startswith("PONT_OCTETS")])
            b.arreter()
            b.attendre_final()
        with Banc() as b:
            self.assertEqual(b.lancer("scenario", "30", "30", "2048", "2").returncode, 0)
            envs = [b.run_args()[i + 1] for i, x in enumerate(b.run_args()[:-1]) if x == "-e"]
            self.assertFalse([x for x in envs if x.startswith(("PONT_CAPTURES", "PONT_OCTETS"))])
            b.arreter()
            b.attendre_final()

    def test_captures_et_octets_hostiles_refuses(self):
        base = ("scenario", "30", "30", "2048", "2")
        mauvais = [("51",), ("0",), ("-1",), ("020",), ("a",), ("1;ls",), ("", ), ("20", "104857601"), ("20", "0"), ("20", "007"),
                   ("20", "1e6"), ("20", "$(id)"), ("20", "1000", "9")]
        with Banc() as b:
            for extra in mauvais:
                with self.subTest(extra=extra):
                    self.assertEqual(b.lancer(*base, *extra).returncode, 2)
            self.assertFalse((b.home / "taches").exists())
            self.assertEqual(b.journal, "")
            self.assertEqual(b.lancer(*base, "50", "104857600").returncode, 0)    # les bornes elles-mêmes sont admises
            b.arreter()
            b.attendre_final()

    def test_taille_de_sortie_documentee_comme_sondage_et_non_quota(self):
        self.assertIn("sondage", SCRIPT.read_text(encoding="utf-8").lower())

    def test_pid_recycle_ou_mort_n_est_pas_un_veilleur(self):
        with Banc() as b:
            avant = self._etat_ecrit(b, "en_cours")
            for contenu in ("999999", "pas-un-pid", "1"):                   # mort, illisible, vivant mais sans le marqueur
                with self.subTest(pid=contenu):
                    (b.dossier / "veilleur.pid").write_text(contenu, newline="\n")
                    r = b.lancer()
                    self.assertEqual(r.returncode, 4, r.stderr)             # jamais 3 : le lanceur doit nettoyer, pas attendre
                    self.assertEqual((b.dossier / "etat.json").read_text(), avant)
            self.assertEqual(b.appels("docker"), [])

    def test_un_identifiant_deja_utilise_est_refuse_sans_rien_effacer(self):
        for etat, statut in (("terminee", "plantage"), ("arretee", "ok"), ("echouee", "erreur")):
            with self.subTest(etat=etat), Banc() as b:
                avant = self._etat_ecrit(b, etat, statut)
                (b.dossier / "sortie").mkdir(exist_ok=True)
                (b.dossier / "sortie" / "plantage.txt").write_text("FATAL EXCEPTION", newline="\n")
                r = b.lancer()
                self.assertEqual(r.returncode, 4, r.stderr)
                self.assertEqual((b.dossier / "etat.json").read_text(), avant)
                self.assertTrue((b.dossier / "sortie" / "plantage.txt").exists())
                self.assertEqual(b.appels("docker"), [])
                self.assertEqual(b.appels("flock"), [])

    def test_une_tache_en_attente_peut_etre_relancee(self):
        with Banc() as b:
            self._etat_ecrit(b, "en_attente")
            self.assertEqual(b.lancer().returncode, 0)
            self.assertEqual(b.etat()["etat"], "en_cours")
            b.arreter()
            b.attendre_final()

    def test_un_conteneur_tache_existant_donne_75_sans_second_emulateur(self):
        with Banc(FAUX_CONTENEUR_EXISTE="1") as b:
            r = b.lancer()
            self.assertEqual(r.returncode, 75, r.stderr)
            self.assertEqual(b.etat()["etat"], "en_attente")
            self.assertEqual(b.appels("docker run"), [])
            self.assertTrue(b.appels("flock -u"))                           # créneau relâché
            self.assertTrue(any("name=^tache-" in x and x.startswith("docker ps") for x in b.journal.splitlines()), b.journal)

    ARRETEE = json.dumps({"id": ID, "etat": "arretee", "statut": None, "debut": None, "fin": "2026-11-19T10:16:40Z",
                          "raison": "Arrêtée avant son démarrage (créneau occupé) : rien n'a tourné, APK retiré."})

    def test_un_arret_pendant_l_attente_du_creneau_est_honore(self):
        # T4 : `arreter` écrit arretee pendant que l'enveloppe attend le créneau : elle ne démarre rien et ne réécrit
        # jamais l'état final (ni en_cours, ni en_attente), créneau relâché.
        for occupe in ("", "1"):
            with self.subTest(creneau_occupe=bool(occupe)), Banc(FAUX_FLOCK_ARRETEE=self.ARRETEE,
                                                                 **({"FAUX_FLOCK_OCCUPE": "1"} if occupe else {})) as b:
                self._etat_ecrit(b, "en_attente")
                r = b.lancer()
                self.assertEqual(r.returncode, 4, r.stderr + r.stdout)
                self.assertEqual(b.etat()["etat"], "arretee")
                self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])["etat"], "arretee")
                self.assertEqual(b.appels("docker run"), [])
                self.assertEqual(b.appels("setsid"), [])
                self.assertTrue(b.appels("flock -u"), b.journal)
                self.assertFalse((b.dossier / "enveloppe.pid").exists())

    def test_le_veilleur_ne_sonde_plus_docker_ps_toutes_les_2_s(self):
        # M4 : `docker ps` une seule fois (l'enveloppe) ; le veilleur lit l'état par `docker inspect`, et seulement
        # quand le processus du conteneur n'est plus vu dans /proc (auth.log de sudo épargné).
        with Banc(FAUX_PID_VEILLEUR="1") as b:
            self.assertEqual(b.lancer().returncode, 0)
            time.sleep(2.5)                                       # une douzaine de tours à 0,2 s
            self.assertEqual(len(b.appels("docker ps")), 1, b.journal)
            self.assertLessEqual(len(b.appels("docker inspect")), 2, b.journal)
            b.arreter()
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("arretee", "ok"))
        code = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('SONDE="${ENVELOPPE_SONDE_S:-5}"', code)

    def test_un_avertissement_sur_stderr_ne_fait_pas_disparaitre_un_conteneur_vivant(self):
        # `sudo: unable to resolve host` (code 0) : seule la sortie standard est lue ; le conteneur reste vivant.
        with Banc(FAUX_INSPECT_AVERTIT="1") as b:
            self.assertEqual(b.lancer().returncode, 0)
            time.sleep(2)
            self.assertEqual(b.etat()["etat"], "en_cours", b.journal)
            self.assertGreaterEqual(len(b.appels("docker inspect")), 2, b.journal)
            b.arreter()
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("arretee", "ok"))   # « No such » vu sur stderr : arrêt constaté
            self.assertEqual(list(b.dossier.glob(".inspect*")), [])          # le fichier d'erreur privé est retiré

    def test_arret_confirme_seulement_par_une_reponse_nette(self):
        # docker stop échoue, inspect répond « true <pid> » avec un avertissement : jamais pris pour « disparu ».
        with Banc(FAUX_INSPECT_AVERTIT="1", FAUX_STOP_ECHEC="1") as b:
            self.assertEqual(b.lancer().returncode, 0)
            b.arreter()
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("echouee", "erreur"))
            self.assertIn("ne s'arrête pas", f["raison"])

    def test_reponse_illisible_de_docker_n_est_jamais_un_conteneur_disparu(self):
        with Banc(FAUX_INSPECT_ILLISIBLE="1") as b:
            self.assertEqual(b.lancer().returncode, 0)
            f = b.attendre_final(delai=40)
            self.assertEqual((f["etat"], f["statut"]), ("echouee", "erreur"))
            self.assertIn("Docker ne répond plus", f["raison"])
            self.assertNotIn("arrêté de lui-même", f["raison"])

    def test_conteneur_mort_au_demarrage_constate_aussitot_avec_la_raison(self):
        # Le vrai docker écrit « error: no such object » (minuscule) pour un conteneur --rm disparu : c'est « parti »,
        # constaté au premier contrôle (jamais 30 essais puis « Docker ne répond plus »), avec la fin de entree-tache.log.
        journal = ("Démarrage de l'entrée.\nligne 2\nligne 3\nWarning: This version only understands SDK XML versions up to 3\n"
                   "Error: AVD not created\x1b[0m\r\n" + "Création de l'AVD emul impossible (image " + IMAGE_SYSTEME + ").\n")
        for variante in ({"FAUX_INSPECT_MINUSCULE": "1"}, {}):
            with self.subTest(variante=variante), Banc(FAUX_MEURT_AU_PS="2", **variante) as b:
                (b.dossier / "sortie").mkdir(parents=True)
                (b.dossier / "sortie" / "entree-tache.log").write_bytes(journal.encode("utf-8"))
                debut = time.time()
                self.assertEqual(b.lancer().returncode, 0)
                f = b.attendre_final(delai=20)
                self.assertLess(time.time() - debut, 12)
                self.assertEqual((f["etat"], f["statut"]), ("echouee", "erreur"))
                self.assertTrue(f["raison"].startswith("Le conteneur s'est arrêté au démarrage"), f["raison"])
                self.assertIn("Création de l'AVD emul impossible", f["raison"])
                self.assertIn("Error: AVD not created", f["raison"])
                self.assertNotIn("Démarrage de l'entrée", f["raison"])                       # seulement les dernières lignes
                self.assertFalse(any(ord(c) < 32 for c in f["raison"]), f["raison"])
                self.assertLessEqual(len(f["raison"].encode("utf-8")), 400)
                self.assertNotIn("Docker ne répond plus", f["raison"])

    def test_conteneur_mort_apres_l_avd_garde_le_message_habituel(self):
        with Banc(FAUX_MEURT_AU_PS="2", FAUX_INSPECT_MINUSCULE="1") as b:
            (b.dossier / "sortie").mkdir(parents=True)
            (b.dossier / "sortie" / ".avd-pret").write_bytes(b"")
            self.assertEqual(b.lancer().returncode, 0)
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("echouee", "erreur"))
            self.assertIn("s'est arrêté de lui-même", f["raison"])

    def ecrire_image(self, b, octets):
        img = b.home / "android-sdk" / "system-images" / "android-34" / "google_apis" / "x86_64"
        img.mkdir(parents=True, exist_ok=True)
        (img / "system.img").write_bytes(b"\0" * octets)

    def test_image_systeme_trop_grosse_pour_avd_refusee_avant_docker_run(self):
        # L'émulateur copie system.img dans /avd (tmpfs de 9 Go) : une image plus grosse que 9 Go - 2 Go de marge échouerait
        # tard et obscurément (« Not enough space to create userdata partition ») ; elle est refusée tout de suite.
        with Banc(ENVELOPPE_IMAGE_MAX_OCTETS="1000") as b:
            self.ecrire_image(b, 2000)
            r = b.lancer()
            self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
            e = b.etat()
            self.assertEqual((e["etat"], e["statut"]), ("echouee", "erreur"))
            self.assertIn("system.img", e["raison"])
            self.assertIn("/avd", e["raison"])
            self.assertEqual(b.appels("docker run"), [])
            self.assertTrue(b.appels("flock -u"))
        with Banc(ENVELOPPE_IMAGE_MAX_OCTETS="1000") as b:          # dans la limite : le lancement part
            self.ecrire_image(b, 500)
            self.assertEqual(b.lancer().returncode, 0)
            b.arreter()
            b.attendre_final()
        code = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("IMAGE_MAX_OCTETS=$(( (9 - 2) * 1024 * 1024 * 1024 ))", code)

    def test_docker_muet_au_veilleur_finit_en_erreur(self):
        with Banc(FAUX_DOCKER_MUET="1") as b:
            self.assertEqual(b.lancer().returncode, 0)
            f = b.attendre_final(delai=30)
            self.assertEqual((f["etat"], f["statut"]), ("echouee", "erreur"))
            self.assertIn("Docker ne répond plus", f["raison"])

    def test_echeance_tenue_a_la_seconde_malgre_une_sonde_lente(self):
        # M4 : la sonde passe à 5 s, mais le veilleur se réveille à l'échéance (jamais 5 s de retard).
        # Sonde de 15 s : sans réveil à l'échéance, la fin viendrait 15 s après le départ du veilleur ; avec, ~2 s.
        with Banc(ENVELOPPE_SONDE_S="15") as b:
            self.assertEqual(b.lancer("scenario", "2", "30", "2048", "2").returncode, 0)
            debut = time.time()                                     # le veilleur est parti (l'enveloppe a rendu la main)
            f = b.attendre_final(delai=30)
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))
            self.assertLess(time.time() - debut, 10)
        with Banc(ENVELOPPE_SONDE_S="15") as b:                         # inactivité du pilote : de même
            self.assertEqual(b.lancer("pilote", "60", "2", "2048", "2").returncode, 0)
            debut = time.time()
            f = b.attendre_final(delai=30)
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))
            self.assertIn("Inactivité", f["raison"])
            self.assertLess(time.time() - debut, 10)

    def test_hup_ignore_avant_d_ecrire_en_cours(self):
        code = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("trap '' HUP", code)
        self.assertLess(code.index("trap '' HUP"), code.index("ecrire_etat en_cours"))

    def test_docker_run_fige_ou_en_echec_nettoie_le_conteneur_a_demi_cree(self):
        with Banc(FAUX_RUN_ECHEC="1") as b:
            self.assertEqual(b.lancer().returncode, 1)
            self.assertTrue(any(x.startswith("docker rm -f") and f"tache-{ID}" in x for x in b.journal.splitlines()), b.journal)

    def test_arret_fin_est_une_fin_normale_et_tout_autre_motif_un_arret(self):
        with Banc() as b:
            self.assertEqual(b.lancer().returncode, 0)
            (b.dossier / "arret").write_text("fin\n", newline="\n")
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "ok"))
        with Banc() as b:
            self.assertEqual(b.lancer().returncode, 0)
            (b.dossier / "arret").write_text("demande de l'agent\n", newline="\n")
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("arretee", "ok"))

    def test_conteneur_mort_prime_sur_un_arret_present(self):
        with Banc(FAUX_MEURT_AU_PS="2") as b:
            b.env["FAUX_ARRET_AU_PS"] = (b.dossier / "arret").as_posix()    # le fichier arret apparaît pendant le 1er contrôle
            self.assertEqual(b.lancer().returncode, 0)
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("echouee", "erreur"))

    def test_sortie_trop_volumineuse_arrete_la_tache_en_limite(self):
        with Banc(ENVELOPPE_SORTIE_MAX_KO="50") as b:
            self.assertEqual(b.lancer().returncode, 0)
            (b.dossier / "sortie" / "gros.bin").write_bytes(b"x" * 300 * 1024)
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))
            self.assertIn("sortie trop volumineuse", f["raison"])
            self.assertTrue(b.appels("docker stop"))

    def test_l_activite_du_pont_repousse_l_inactivite_du_pilote(self):
        with Banc() as b:
            self.assertEqual(b.lancer("pilote", "60", "3", "2048", "2").returncode, 0)
            for _ in range(8):                                    # seul .activite (verbe en cours, pas encore de pont.log)
                (b.dossier / "sortie" / ".activite").write_text("", newline="\n")
                time.sleep(0.5)
                self.assertEqual(b.etat()["etat"], "en_cours")
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))

    def test_valeurs_par_defaut_du_script(self):
        code = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('INACTIVITE="${4-600}"', code)                 # > PONT_DEMARRAGE_S (300)
        self.assertIn('MEMOIRE="${5-6144}"', code)
        versions = json.loads((RACINE / "versions.json").read_text(encoding="utf-8"))
        self.assertIn(f'IMAGE_SYSTEME="{versions["android_sdk"]["emulator_image"]}"', code)

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



ENTREE = RACINE / "images" / "emulateur" / "entree-tache.sh"
IMAGE_SYSTEME = "system-images;android-34;google_apis;x86_64"
AVDMANAGER = r'''echo "avdmanager $* racine=${ANDROID_SDK_ROOT:-} home=${ANDROID_HOME:-}" >> "$FAUX_JOURNAL"
rep=""; IFS= read -r rep; echo "reponse=$rep" >> "$FAUX_JOURNAL"      # la question du profil matériel personnalisé
echo "user_home=${ANDROID_USER_HOME:-} existe=$([ -d "${ANDROID_USER_HOME:-/nulle}" ] && echo oui || echo non)" >> "$FAUX_JOURNAL"
if [ -n "${AVD_BRUIT:-}" ]; then           # progression à retours chariot et séquences ANSI, puis l'erreur réelle d'avdmanager
  printf '\033[1m[=      ] 10%% Loading local repository...\r[=======] 100%% Fetch remote repository...\033[0m\r\n'
  printf 'Warning: This version only understands SDK XML versions up to 3\nError: AVD not created\n'
  exit 1
fi
[ -n "${AVD_ECHEC:-}" ] && exit 1
nom=""; prec=""; for a in "$@"; do [ "$prec" = --name ] && nom="$a"; prec="$a"; done
[ -n "${AVD_SANS_CONFIG:-}" ] && exit 0
mkdir -p "$ANDROID_AVD_HOME/$nom.avd"
printf 'hw.ramSize=1024\nfoo=bar\ndisk.dataPartition.size=800M\n' > "$ANDROID_AVD_HOME/$nom.avd/config.ini"'''


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestReseauBorne(unittest.TestCase):
    """Réseau borné : l'émulateur n'a un réseau que si des hôtes sont demandés (le lanceur du poste a vérifié l'accord du
    Directeur) ; le réseau est alors interne, le proxy est le seul chemin de sortie, les adresses sont vérifiées publiques."""
    HOTES = "service.exemple,api.service.exemple"
    LIMITES = ("scenario", "30", "30", "2048", "2", "50", "104857600")

    def lancer(self, b, hotes=HOTES, **env):
        return b.lancer(*self.LIMITES, *([hotes] if hotes is not None else []), env=env)

    def appels_docker(self, b, sous_commande):
        return [x for x in b.appels("docker ") if x.split()[1:2] == [sous_commande]]

    def test_sans_hote_aucun_reseau_ni_proxy(self):
        with Banc() as b:
            self.assertEqual(self.lancer(b, None).returncode, 0)
            a = b.run_args()
            self.assertTrue(any(a[i:i + 2] == ["--network", "none"] for i in range(len(a))), a)
            self.assertNotIn("--add-host", a)
            self.assertFalse(any(x.startswith("PONT_PROXY") for x in a), a)
            self.assertEqual(self.appels_docker(b, "network"), [])
            self.assertFalse((b.et / "run-proxy.txt").exists())
            self.assertFalse((b.dossier / "reseau").exists())
            b.arreter()
            b.attendre_final()
            self.assertEqual(self.appels_docker(b, "network"), [])          # rien à retirer non plus

    def test_avec_hotes_reseau_interne_proxy_et_emulateur_sur_ce_reseau_seulement(self):
        with Banc() as b:
            r = self.lancer(b)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            a, p = b.run_args(), (b.et / "run-proxy.txt").read_text(encoding="utf-8").splitlines()

            def suite(args, *motif):
                self.assertTrue(any(args[i:i + len(motif)] == list(motif) for i in range(len(args))), f"{motif} absent de {args}")

            reseau = f"reseau-{ID}"
            # l'émulateur : sur le réseau interne SEUL, jamais « none » remplacé par bridge ou host ; adresses épinglées
            suite(a, "--network", reseau)
            self.assertEqual([a[i + 1] for i in range(len(a) - 1) if a[i] == "--network"], [reseau])
            suite(a, "--add-host", "service.exemple:93.184.216.34")
            suite(a, "--add-host", "api.service.exemple:93.184.216.34")
            suite(a, "-e", "PONT_PROXY=http://proxy-sortant:3128")
            for x in ("--privileged", "host", "--cap-add", "--dns", "docker.sock"):
                self.assertFalse(any(x in y for y in a if y != "--add-host"), f"{x} dans {a}")
            suite(a, "--cap-drop", "ALL")
            # le réseau : interne (aucune passerelle), puis le proxy branché dessus avec son alias
            creer = self.appels_docker(b, "network")
            self.assertIn(f"docker network create --internal --label myiafactory.genre=reseau {reseau}", creer)
            self.assertIn(f"docker network connect --alias proxy-sortant {reseau} {reseau}", creer)
            # le proxy : même durcissement, jamais de DNS à lui, ne se connecte qu'aux adresses résolues par l'hôte
            suite(p, "--network", "bridge")
            suite(p, "--cap-drop", "ALL")
            suite(p, "--security-opt", "no-new-privileges")
            suite(p, "--user", "1000:1000")
            suite(p, "--entrypoint", "java")
            self.assertIn("--read-only", p)
            self.assertNotIn("--privileged", p)
            self.assertTrue(any(x.startswith("type=bind,") and x.endswith(",dst=/proxy,readonly") for x in p), p)
            suite(p, "/proxy/ProxySortant.java", "3128", "service.exemple=93.184.216.34", "api.service.exemple=93.184.216.34")
            # le journal de la tâche dit que le réseau est ouvert, et vers qui
            self.assertIn("réseau ouvert", b.etat()["raison"])
            self.assertIn("service.exemple=93.184.216.34", b.etat()["raison"])
            self.assertIn("service.exemple", (b.dossier / "reseau.txt").read_text(encoding="utf-8"))
            b.arreter()
            b.attendre_final()
            # fin de tâche : le proxy et le réseau sont retirés
            self.assertIn(f"docker rm -f {reseau}", b.appels("docker "))
            self.assertIn(f"docker network rm {reseau}", b.appels("docker "))
            self.assertTrue((b.dossier / "reseau-proxy.log").exists())

    def test_le_script_n_a_aucun_autre_chemin_de_sortie(self):
        code = SCRIPT.read_text(encoding="utf-8")
        lignes = [x for x in code.splitlines() if not x.lstrip().startswith("#")]
        self.assertEqual([x for x in lignes if "--network none" in x], [])     # « none » n'est que la valeur par défaut de RESEAU_EMUL
        self.assertIn("RESEAU_EMUL=none", code)
        self.assertIn('RESEAU_EMUL="$RESEAU_NOM"', code)
        for interdit in ("--network host", "--privileged", "docker.sock", "iptables", "nft "):
            self.assertNotIn(interdit, code)

    def test_adresse_non_publique_refuse_toute_la_demande(self):
        for ip in ("10.0.0.5", "127.0.0.1", "169.254.169.254", "192.168.1.10", "172.16.4.4", "172.31.255.255", "100.64.0.1",
                   "0.0.0.0", "224.0.0.1", "255.255.255.255", "198.18.0.1", "192.0.0.8", "93.184.216.34 10.0.0.5"):
            with self.subTest(ip), Banc(FAUX_IP_HOTE=ip) as b:
                r = self.lancer(b)
                self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
                e = b.etat()
                self.assertEqual((e["etat"], e["statut"]), ("echouee", "erreur"))
                self.assertIn("pas publique", e["raison"])
                self.assertEqual(b.appels("docker run"), [], b.journal)            # ni émulateur ni proxy
                self.assertEqual(self.appels_docker(b, "network"), [])

    def test_adresses_publiques_proches_des_bornes_acceptees(self):
        for ip in ("172.32.0.1", "172.15.255.255", "100.63.255.255", "100.128.0.1", "169.255.0.1", "11.0.0.1", "223.255.255.254",
                   "198.17.0.1", "198.20.0.1"):
            with self.subTest(ip), Banc(FAUX_IP_HOTE=ip) as b:
                self.assertEqual(self.lancer(b).returncode, 0, ip)
                b.arreter()
                b.attendre_final()

    def test_hote_sans_adresse_refuse(self):
        with Banc(FAUX_IP_HOTE="") as b:
            r = self.lancer(b)
            self.assertEqual(r.returncode, 1)
            self.assertIn("aucune adresse", b.etat()["raison"])
            self.assertEqual(b.appels("docker run"), [])

    def test_adresse_ipv6_ou_texte_n_est_jamais_acceptee(self):
        for ip in ("::1", "fe80::1", "pasuneadresse", "1.2.3", "1.2.3.4.5", "999.1.1.1", "01.2.3.4x"):
            with self.subTest(ip), Banc(FAUX_IP_HOTE=ip) as b:
                self.assertEqual(self.lancer(b).returncode, 1, ip)
                self.assertEqual(b.appels("docker run"), [])

    def test_hotes_mal_formes_refuses_avant_tout(self):
        for hotes in ("127.0.0.1", "10.0.0.1,service.exemple", "Service.Exemple", "service.exemple:8080", "localhost",
                      "service.exemple,", ",service.exemple",
                      "service.exemple,a.exemple,b.exemple,c.exemple,d.exemple,e.exemple",
                      "db.internal", "nas.local", "a b.exemple", "x.exemple;touch", "x.exemple\ny.exemple", "", "-x.exemple"):
            with self.subTest(hotes), Banc() as b:
                r = self.lancer(b, hotes)
                self.assertEqual(r.returncode, 2, f"{hotes!r}: {r.stderr}")
                self.assertEqual(b.appels("docker "), [])
                self.assertFalse(b.dossier.exists())

    def test_neuf_arguments_au_plus(self):
        with Banc() as b:
            self.assertEqual(b.lancer("scenario", "30", "30", "2048", "2", "50", "104857600", "a.exemple", "x").returncode, 2)

    def test_reseau_impossible_a_creer_refuse_la_tache_sans_emulateur(self):
        for env in ({"FAUX_RESEAU_ECHEC": "1"}, {"FAUX_PROXY_ECHEC": "1"}):
            with self.subTest(env), Banc(**env) as b:
                r = self.lancer(b)
                self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
                e = b.etat()
                self.assertEqual((e["etat"], e["statut"]), ("echouee", "erreur"))
                self.assertIn("Réseau borné impossible", e["raison"])
                self.assertEqual(b.appels("docker run --pull never --rm -d --init --name tache-"), [], b.journal)
                self.assertIn(f"docker network rm reseau-{ID}", b.appels("docker "))         # rien ne traîne

    def test_echec_de_l_emulateur_retire_le_reseau(self):
        with Banc(FAUX_RUN_ECHEC="1") as b:
            r = self.lancer(b)
            self.assertEqual(r.returncode, 1)
            self.assertIn(f"docker network rm reseau-{ID}", b.appels("docker "))
            self.assertIn(f"docker rm -f reseau-{ID}", b.appels("docker "))

    def test_le_veilleur_retire_le_reseau_aussi_quand_le_conteneur_meurt_seul(self):
        with Banc(FAUX_MEURT_AU_PS="3") as b:
            self.assertEqual(self.lancer(b).returncode, 0)
            b.attendre_final()
            self.assertIn(f"docker network rm reseau-{ID}", b.appels("docker "))

    POINT = "http://203.0.113.10:18000"

    def lancer_point(self, b, point=POINT, hotes="-", **env):
        return b.lancer(*self.LIMITES, hotes, point, env=env)

    def test_point_d_acces_par_adresse_ip_publique(self):
        with Banc(FAUX_IP_HOTE="203.0.113.10") as b:
            r = self.lancer_point(b)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            a, p = b.run_args(), (b.et / "run-proxy.txt").read_text(encoding="utf-8").splitlines()
            reseau = f"reseau-{ID}"
            self.assertEqual([a[i + 1] for i in range(len(a) - 1) if a[i] == "--network"], [reseau])
            self.assertNotIn("--add-host", a)                                # une adresse littérale n'a pas de nom à épingler
            self.assertIn("http://203.0.113.10:18000=203.0.113.10", p)       # le proxy ne reçoit que ce point-là
            e = b.etat()["raison"]
            self.assertIn("point d'accès du service http://203.0.113.10:18000", e)
            self.assertIn("en clair", e)                                       # le journal dit que le trafic sort en clair
            self.assertIn("en clair", (b.dossier / "reseau.txt").read_text(encoding="utf-8"))
            b.arreter()
            b.attendre_final()
            self.assertIn(f"docker network rm {reseau}", b.appels("docker "))

    def test_point_d_acces_par_nom_est_epingle(self):
        with Banc() as b:
            self.assertEqual(self.lancer_point(b, "https://service.exemple:8443").returncode, 0)
            a, p = b.run_args(), (b.et / "run-proxy.txt").read_text(encoding="utf-8").splitlines()
            self.assertIn("service.exemple:93.184.216.34", a)
            self.assertIn("https://service.exemple:8443=93.184.216.34", p)

    def test_point_et_hotes_ensemble(self):
        with Banc(FAUX_IP_HOTE="203.0.113.10") as b:
            self.assertEqual(self.lancer_point(b, hotes="api.exemple.fr").returncode, 0)
            p = (b.et / "run-proxy.txt").read_text(encoding="utf-8").splitlines()
            self.assertIn("api.exemple.fr=203.0.113.10", p)
            self.assertIn("http://203.0.113.10:18000=203.0.113.10", p)

    def test_point_d_acces_non_public_refuse_avant_tout(self):
        for ip in ("10.0.0.5", "127.0.0.1", "169.254.169.254", "192.168.1.10", "172.16.4.4", "100.64.0.1", "0.0.0.1", "224.0.0.1",
                   "198.19.0.1", "192.0.0.8"):
            with self.subTest(ip), Banc() as b:
                r = self.lancer_point(b, f"http://{ip}:18000")
                self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
                self.assertIn("pas publique", b.etat()["raison"])
                self.assertEqual(b.appels("docker run"), [], b.journal)
                self.assertEqual(self.appels_docker(b, "network"), [])
        with Banc(FAUX_IP_HOTE="10.0.0.5") as b:                              # un nom qui se résout vers une adresse privée
            self.assertEqual(self.lancer_point(b, "http://service.exemple:18000").returncode, 1)
            self.assertEqual(b.appels("docker run"), [])

    def test_point_d_acces_mal_forme_refuse(self):
        for point in ("ftp://203.0.113.10:21", "tcp://203.0.113.10:18000", "203.0.113.10:18000", "http://203.0.113.10",
                      "http://203.0.113.10:0", "http://203.0.113.10:65536", "http://203.0.113.10:018000", "http://203.0.113.10:18000/x",
                      "http://u@203.0.113.10:18000", "HTTP://203.0.113.10:18000", "http://Service.Exemple:80", "http://localhost:80",
                      "http://a.internal:80", "http://203.0.113.10:18000;touch", "http://[::1]:80", "http://203.0.113:80", ""):
            with self.subTest(point), Banc() as b:
                r = self.lancer_point(b, point)
                self.assertEqual(r.returncode, 2, f"{point!r}: {r.stderr}")
                self.assertEqual(b.appels("docker "), [])
                self.assertFalse(b.dossier.exists())

    def test_sans_hotes_ni_point_refuse(self):
        with Banc() as b:
            self.assertEqual(b.lancer(*self.LIMITES, "-").returncode, 2)

    def test_un_ancien_proxy_ou_reseau_est_retire_avant(self):
        with Banc() as b:
            self.assertEqual(self.lancer(b).returncode, 0)
            self.assertTrue(any("ps -aq --filter label=myiafactory.genre=proxy" in x for x in b.appels("docker ")), b.journal)
            self.assertTrue(any("network ls -q --filter label=myiafactory.genre=reseau" in x for x in b.appels("docker ")), b.journal)
            b.arreter()
            b.attendre_final()


@unittest.skipUnless(shutil.which("bash") and shutil.which("java") and shutil.which("javac"), "bash ou JDK absent")
class TestProxySortant(unittest.TestCase):
    """Le proxy Java embarqué dans l'enveloppe : CONNECT <hôte>:443 vers des adresses données, rien d'autre. Lancé pour de
    vrai en local ; l'adresse « distante » est le bouclage, le port distant (réservé aux essais, propriété système) un port libre."""

    @classmethod
    def setUpClass(cls):
        import re
        import socket
        import socketserver
        import threading
        texte = SCRIPT.read_text(encoding="utf-8")
        m = re.search(r"<<'FIN_PROXY_JAVA'\n(.*?)\nFIN_PROXY_JAVA\n", texte, re.S)
        assert m, "source Java du proxy introuvable dans l'enveloppe"
        cls._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.dossier = Path(cls._t.name)
        (cls.dossier / "ProxySortant.java").write_text(m.group(1) + "\n", encoding="utf-8", newline="\n")

        class Echo(socketserver.BaseRequestHandler):
            def handle(self):
                try:
                    while True:
                        d = self.request.recv(4096)
                        if not d:
                            return
                        self.request.sendall(b"ECHO:" + d)
                except OSError:
                    return      # le proxy a coupé : fin normale

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        cls.echo = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Echo)
        cls.port_echo = cls.echo.server_address[1]
        threading.Thread(target=cls.echo.serve_forever, daemon=True).start()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        cls.proc = subprocess.Popen(
            ["java", f"-Dproxy.portdistant={cls.port_echo}", (cls.dossier / "ProxySortant.java").as_posix(), str(cls.port),
             "service.exemple=127.0.0.1", "http://203.0.113.10:18000=127.0.0.1", "https://203.0.113.11:8443=127.0.0.1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        fin = time.time() + 60
        while time.time() < fin:
            try:
                socket.create_connection(("127.0.0.1", cls.port), timeout=1).close()
                break
            except OSError:
                if cls.proc.poll() is not None:
                    raise AssertionError("proxy arrêté : " + cls.proc.stderr.read())
                time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.proc.kill()
        cls.proc.wait()
        cls.echo.shutdown()
        cls.echo.server_close()
        cls._t.cleanup()

    def requete(self, texte, apres=None):
        import socket
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as s:
            s.sendall(texte.encode("latin-1"))
            rep = s.recv(4096).decode("latin-1")
            if apres is not None and rep.startswith("HTTP/1.1 200"):
                s.sendall(apres)
                rep += s.recv(4096).decode("latin-1")
            return rep

    def test_connect_vers_un_hote_declare_passe(self):
        rep = self.requete("CONNECT service.exemple:443 HTTP/1.1\r\nHost: service.exemple:443\r\n\r\n", b"salut")
        self.assertTrue(rep.startswith("HTTP/1.1 200"), rep)
        self.assertIn("ECHO:salut", rep)

    def test_connect_par_adresse_declaree_passe_et_ailleurs_non(self):
        self.assertTrue(self.requete("CONNECT 127.0.0.1:443 HTTP/1.1\r\n\r\n").startswith("HTTP/1.1 200"))
        for refus in ("CONNECT 127.0.0.2:443 HTTP/1.1\r\n\r\n", "CONNECT 10.0.0.1:443 HTTP/1.1\r\n\r\n",
                      "CONNECT 169.254.169.254:443 HTTP/1.1\r\n\r\n", "CONNECT autre.exemple:443 HTTP/1.1\r\n\r\n",
                      "CONNECT localhost:443 HTTP/1.1\r\n\r\n"):
            self.assertTrue(self.requete(refus).startswith("HTTP/1.1 403"), refus)

    def test_autre_port_refuse(self):
        for port in ("80", "22", "8443", "0", "", "443x"):
            rep = self.requete(f"CONNECT service.exemple:{port} HTTP/1.1\r\n\r\n")
            self.assertTrue(rep.startswith("HTTP/1.1 403"), f"{port}: {rep}")

    def test_autre_methode_refusee(self):
        for texte in ("PATCH / HTTP/1.1\r\nHost: service.exemple\r\n\r\n", "POST / HTTP/1.1\r\n\r\n",
                      "CONNECT service.exemple:443\r\n\r\n", "connect service.exemple:443 HTTP/1.1\r\n\r\n"):
            self.assertTrue(self.requete(texte).startswith("HTTP/1.1 405"), texte)

    def test_http_en_clair_vers_le_point_d_acces_declare_seulement(self):
        rep = self.requete("GET http://203.0.113.10:18000/api/equipes?x=1 HTTP/1.1\r\nHost: 203.0.113.10:18000\r\n"
                           "Authorization: Bearer jeton-fictif\r\nProxy-Connection: keep-alive\r\nConnection: keep-alive\r\n\r\n",
                           None)
        import socket
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as s:
            s.sendall(b"POST http://203.0.113.10:18000/api/x HTTP/1.1\r\nHost: 203.0.113.10:18000\r\nContent-Length: 2\r\n\r\nok")
            recu = b""
            while not recu.endswith(b"ok"):
                bloc = s.recv(4096)
                if not bloc:
                    break
                recu += bloc
        texte = recu.decode("latin-1")
        self.assertTrue(texte.startswith("ECHO:POST /api/x HTTP/1.1\r\n"), texte)      # URI absolue réécrite en chemin
        self.assertIn("Host: 203.0.113.10:18000", texte)
        self.assertIn("Connection: close", texte)
        self.assertNotIn("keep-alive", texte.lower())
        self.assertTrue(rep.startswith("ECHO:GET /api/equipes?x=1 HTTP/1.1\r\n"), rep)
        self.assertIn("Authorization: Bearer jeton-fictif", rep)                          # le jeton passe, en clair, vers ce seul hôte
        self.assertNotIn("Proxy-Connection", rep)

    def test_http_autre_hote_port_ou_methode_refuse(self):
        for texte, code in (("GET http://203.0.113.10:18001/ HTTP/1.1\r\n\r\n", "403"),
                            ("GET http://203.0.113.10/ HTTP/1.1\r\n\r\n", "403"),
                            ("GET http://203.0.113.12:18000/ HTTP/1.1\r\n\r\n", "403"),
                            ("GET http://127.0.0.1:18000/ HTTP/1.1\r\n\r\n", "403"),
                            ("GET http://169.254.169.254/ HTTP/1.1\r\n\r\n", "403"),
                            ("GET http://service.exemple/ HTTP/1.1\r\n\r\n", "403"),      # cible https : pas de HTTP clair
                            ("GET http://203.0.113.11:8443/ HTTP/1.1\r\n\r\n", "403"),     # idem
                            ("PUT http://203.0.113.10:18000/ HTTP/1.1\r\n\r\n", "405"),
                            ("DELETE http://203.0.113.10:18000/ HTTP/1.1\r\n\r\n", "405"),
                            ("GET https://203.0.113.10:18000/ HTTP/1.1\r\n\r\n", "405"),
                            ("GET /api HTTP/1.1\r\nHost: 203.0.113.10:18000\r\n\r\n", "405")):
            self.assertTrue(self.requete(texte).startswith(f"HTTP/1.1 {code}"), texte)

    def test_connect_vers_le_point_d_acces_et_son_port_seulement(self):
        self.assertTrue(self.requete("CONNECT 203.0.113.10:18000 HTTP/1.1\r\n\r\n").startswith("HTTP/1.1 200"))
        self.assertTrue(self.requete("CONNECT 203.0.113.11:8443 HTTP/1.1\r\n\r\n").startswith("HTTP/1.1 200"))
        for refus in ("CONNECT 203.0.113.10:443 HTTP/1.1\r\n\r\n", "CONNECT 203.0.113.10:22 HTTP/1.1\r\n\r\n",
                      "CONNECT 203.0.113.11:18000 HTTP/1.1\r\n\r\n", "CONNECT service.exemple:18000 HTTP/1.1\r\n\r\n"):
            self.assertTrue(self.requete(refus).startswith("HTTP/1.1 403"), refus)

    def test_hote_en_majuscules_est_le_meme_hote(self):
        self.assertTrue(self.requete("CONNECT SERVICE.EXEMPLE:443 HTTP/1.1\r\n\r\n").startswith("HTTP/1.1 200"))

    def test_entete_trop_gros_refuse_et_le_proxy_survit(self):
        rep = self.requete("CONNECT service.exemple:443 HTTP/1.1\r\n" + "X: " + "a" * 20000 + "\r\n\r\n")
        self.assertTrue(rep.startswith("HTTP/1.1 405"), rep[:40])
        self.assertTrue(self.requete("CONNECT service.exemple:443 HTTP/1.1\r\n\r\n").startswith("HTTP/1.1 200"))


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEntreeTache(unittest.TestCase):
    """entree-tache.sh lancé hors conteneur : SDK (SANS cmdline-tools, comme celui du serveur), outils en ligne de commande de
    l'image, avdmanager et dossiers factices (ENTREE_SDK, ENTREE_OUTILS, ENTREE_SANS_ATTENTE)."""

    def lancer(self, retirer=(), image=IMAGE_SYSTEME, sdk_absent=False, sans_outils=False, **env):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
            t = Path(t)
            sdk, outils = t / "sdk", t / "sdk-tache"
            for rel in ("outils:cmdline-tools/latest/bin/avdmanager", "platform-tools/adb", "emulator/emulator"):
                racine, rel = (outils, rel[7:]) if rel.startswith("outils:") else (sdk, rel)
                if sans_outils and racine == outils:
                    continue
                f = racine / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text("#!/bin/sh\n" + (AVDMANAGER if f.name == "avdmanager" else "exit 0") + "\n", newline="\n")
                f.chmod(0o755)
            (sdk / "system-images/android-34/google_apis/x86_64").mkdir(parents=True)
            for rel in retirer:
                shutil.rmtree(sdk / rel)
            for d in ("sortie", "avd", "home"):
                (t / d).mkdir()
            e = dict(os.environ, ENTREE_SDK=(t / "nulle-part" if sdk_absent else sdk).as_posix(), ENTREE_SANS_ATTENTE="1",
                     ENTREE_OUTILS=outils.as_posix(),
                     PONT_SORTIE=(t / "sortie").as_posix(), ANDROID_AVD_HOME=(t / "avd").as_posix(), HOME=(t / "home").as_posix(),
                     PONT_AVD="emul", FAUX_JOURNAL=(t / "appels.txt").as_posix())
            e.pop("TACHE_IMAGE_SYSTEME", None)
            if image is not None:
                e["TACHE_IMAGE_SYSTEME"] = image
            e.update(env)
            r = subprocess.run(["bash", ENTREE.as_posix()], capture_output=True, text=True, encoding="utf-8", env=e, timeout=30,
                               stdin=subprocess.DEVNULL)
            config = t / "avd" / "emul.avd" / "config.ini"
            r.config = config.read_text(encoding="utf-8") if config.exists() else None
            r.pret = (t / "sortie" / ".avd-pret").exists()
            r.appels = (t / "appels.txt").read_text(encoding="utf-8") if (t / "appels.txt").exists() else ""
            journal = t / "sortie" / "entree-tache.log"
            r.log = journal.read_bytes() if journal.exists() else b""
            return r

    def test_cree_l_avd_depuis_l_image_epinglee_puis_la_dimensionne(self):
        r = self.lancer()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"--package {IMAGE_SYSTEME}", r.appels)
        self.assertIn("--name emul", r.appels)
        # avdmanager de l'image, racine du SDK = celle de l'image (outils + liens vers le SDK monté), le SDK sans cmdline-tools
        self.assertRegex(r.appels, r"racine=\S*/sdk-tache home=\S*/sdk-tache")
        lignes = r.config.splitlines()
        self.assertEqual(lignes.count("hw.ramSize=2048"), 1, lignes)
        self.assertEqual(lignes.count("disk.dataPartition.size=2G"), 1, lignes)
        self.assertIn("foo=bar", lignes)                                      # les autres réglages sont gardés
        self.assertFalse([x for x in lignes if x in ("hw.ramSize=1024", "disk.dataPartition.size=800M")])
        self.assertTrue(r.pret)

    def test_non_repond_a_la_question_du_profil_materiel(self):
        r = self.lancer()
        self.assertIn("reponse=no", r.appels)

    def test_dossier_utilisateur_android_inscriptible(self):
        # Java prend user.home dans /etc/passwd (/home/ubuntu, en lecture seule dans le conteneur), pas dans $HOME :
        # ANDROID_USER_HOME, exporté et créé, est le seul dossier .android qu'avdmanager et l'émulateur utilisent.
        r = self.lancer()
        self.assertRegex(r.appels, r"user_home=\S*/home/\.android existe=oui")
        r = self.lancer(ANDROID_USER_HOME="")
        self.assertRegex(r.appels, r"user_home=\S*/home/\.android existe=oui")

    def test_journal_lisible_sans_progression_ni_sequences_ansi(self):
        # avdmanager affiche sa progression à retours chariot et en couleurs : le journal garde seulement le texte utile.
        r = self.lancer(AVD_BRUIT="1")
        self.assertEqual(r.returncode, 12, r.stderr)
        self.assertNotIn(b"\r", r.log)
        self.assertNotIn(b"\x1b", r.log)
        self.assertNotIn(b"10%", r.log)
        self.assertIn(b"Error: AVD not created", r.log)
        self.assertIn(b"only understands SDK XML versions", r.log)
        self.assertIn("Création de l'AVD emul impossible".encode("utf-8"), r.log)

    def test_erreurs_nettes_et_codes_distincts(self):
        cas = [("sdk absent", dict(sdk_absent=True), 10, "SDK"),
               ("outils de l'image absents", dict(sans_outils=True), 10, "avdmanager"),
               ("image sans correspondance (glob vide)", dict(image="system-images;android-35;google_apis;x86_64"), 11, "introuvable"),
               ("image absente de l'environnement", dict(image=None), 11, "TACHE_IMAGE_SYSTEME"),
               ("image mal formée", dict(image="system-images;../../x;a;x86_64"), 11, "mal formée"),
               ("avdmanager en échec", dict(AVD_ECHEC="1"), 12, "Création de l'AVD"),
               ("config.ini absent", dict(AVD_SANS_CONFIG="1"), 13, "config.ini")]
        for nom, args, code, mot in cas:
            with self.subTest(nom):
                r = self.lancer(**args)
                self.assertEqual(r.returncode, code, r.stderr)
                self.assertIn(mot, r.stderr)
                self.assertFalse(r.pret)


if __name__ == "__main__":
    unittest.main()
