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
  run) echo "run-vu: pid=$([ -s "$FAUX_DOSSIER/enveloppe.pid" ] && echo oui || echo non) etat=$(cat "$FAUX_DOSSIER/etat.json")" >> "$FAUX_JOURNAL"
       [ -n "${FAUX_RUN_ECHEC:-}" ] && { echo "boom" >&2; exit 125; }
       printf '%s\n' "$@" > "$ET/run.txt"; touch "$ET/vivant"; echo cid123 ;;
  ps|inspect)   # un seul compteur de contrôles : « ps » de l'enveloppe puis « inspect » du veilleur
      n=$(cat "$ET/ps" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$ET/ps"
      if [ -n "${FAUX_MEURT_AU_PS:-}" ] && [ "$n" -ge "$FAUX_MEURT_AU_PS" ]; then rm -f "$ET/vivant"; fi
      [ -n "${FAUX_ARRET_AU_PS:-}" ] && [ "$n" = 1 ] && echo > "$FAUX_ARRET_AU_PS"
      if [ "$1" = inspect ]; then
        [ -n "${FAUX_DOCKER_MUET:-}" ] && { echo "Cannot connect to the Docker daemon" >&2; exit 1; }
        if [ -e "$ET/vivant" ]; then
          p=999999; [ -n "${FAUX_PID_VEILLEUR:-}" ] && p=$(cat "$FAUX_DOSSIER/veilleur.pid")
          echo "true $p"; exit 0
        fi
        echo "Error: No such object: tache-x" >&2; exit 1
      fi
      [ -n "${FAUX_CONTENEUR_EXISTE:-}" ] && echo cidautre
      [ -e "$ET/vivant" ] && echo cid123
      exit 0 ;;
  stop|kill|rm) [ -n "${FAUX_STOP_ECHEC:-}" ] && exit 1; rm -f "$ET/vivant" ;;
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
            suite("--tmpfs", "/avd:size=4g,mode=1777")
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
            for attendu in ("ANDROID_AVD_HOME=/avd", "HOME=/tmp", "PONT_SORTIE=/sortie", "PONT_AVD=emul",
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

    def test_docker_muet_au_veilleur_finit_en_erreur(self):
        with Banc(FAUX_DOCKER_MUET="1") as b:
            self.assertEqual(b.lancer().returncode, 0)
            f = b.attendre_final(delai=30)
            self.assertEqual((f["etat"], f["statut"]), ("echouee", "erreur"))
            self.assertIn("Docker ne répond plus", f["raison"])

    def test_echeance_tenue_a_la_seconde_malgre_une_sonde_lente(self):
        # M4 : la sonde passe à 5 s, mais le veilleur se réveille à l'échéance (jamais 5 s de retard).
        with Banc(ENVELOPPE_SONDE_S="8") as b:
            debut = time.time()
            self.assertEqual(b.lancer("scenario", "2", "30", "2048", "2").returncode, 0)
            f = b.attendre_final(delai=20)
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))
            self.assertLess(time.time() - debut, 6.5)                # et non 8 s (une sonde entière)
        with Banc(ENVELOPPE_SONDE_S="8") as b:                          # inactivité du pilote : de même
            debut = time.time()
            self.assertEqual(b.lancer("pilote", "60", "2", "2048", "2").returncode, 0)
            f = b.attendre_final(delai=20)
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))
            self.assertIn("Inactivité", f["raison"])
            self.assertLess(time.time() - debut, 6.5)

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
AVDMANAGER = r'''echo "avdmanager $*" >> "$FAUX_JOURNAL"
[ -n "${AVD_ECHEC:-}" ] && exit 1
nom=""; prec=""; for a in "$@"; do [ "$prec" = --name ] && nom="$a"; prec="$a"; done
[ -n "${AVD_SANS_CONFIG:-}" ] && exit 0
mkdir -p "$ANDROID_AVD_HOME/$nom.avd"
printf 'hw.ramSize=1024\nfoo=bar\ndisk.dataPartition.size=800M\n' > "$ANDROID_AVD_HOME/$nom.avd/config.ini"'''


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEntreeTache(unittest.TestCase):
    """entree-tache.sh lancé hors conteneur : SDK, avdmanager et dossiers factices (ENTREE_SDK, ENTREE_SANS_ATTENTE)."""

    def lancer(self, retirer=(), image=IMAGE_SYSTEME, sdk_absent=False, **env):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
            t = Path(t)
            sdk = t / "sdk"
            for rel in ("cmdline-tools/latest/bin/avdmanager", "platform-tools/adb", "emulator/emulator"):
                f = sdk / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text("#!/bin/sh\n" + (AVDMANAGER if f.name == "avdmanager" else "exit 0") + "\n", newline="\n")
                f.chmod(0o755)
            (sdk / "system-images/android-34/google_apis/x86_64").mkdir(parents=True)
            for rel in retirer:
                shutil.rmtree(sdk / rel)
            for d in ("sortie", "avd", "home"):
                (t / d).mkdir()
            e = dict(os.environ, ENTREE_SDK=(t / "nulle-part" if sdk_absent else sdk).as_posix(), ENTREE_SANS_ATTENTE="1",
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
            return r

    def test_cree_l_avd_depuis_l_image_epinglee_puis_la_dimensionne(self):
        r = self.lancer()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"--package {IMAGE_SYSTEME}", r.appels)
        self.assertIn("--name emul", r.appels)
        lignes = r.config.splitlines()
        self.assertEqual(lignes.count("hw.ramSize=2048"), 1, lignes)
        self.assertEqual(lignes.count("disk.dataPartition.size=2G"), 1, lignes)
        self.assertIn("foo=bar", lignes)                                      # les autres réglages sont gardés
        self.assertFalse([x for x in lignes if x in ("hw.ramSize=1024", "disk.dataPartition.size=800M")])
        self.assertTrue(r.pret)

    def test_erreurs_nettes_et_codes_distincts(self):
        cas = [("sdk absent", dict(sdk_absent=True), 10, "SDK"),
               ("outil absent", dict(retirer=("cmdline-tools",)), 10, "avdmanager"),
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
