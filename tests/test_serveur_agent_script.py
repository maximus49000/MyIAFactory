"""Agent sur le serveur, côté hôte et côté conteneur, sans Docker ni serveur :
- `serveur_ovh/taches/lancer_agent.sh` (enveloppe hôte) lancée par le bash du poste avec `sudo`, `docker`, `flock`, `setsid`,
  `timeout`, `git` et `python3` factices dans le PATH (ils journalisent leurs appels) ;
- `serveur_ovh/images/agent/entree-agent.py` (entrée du conteneur) lancée par le Python du poste, avec un faux `claude` et le
  vrai `git` sur des dépôts jetables (`AGENT_RACINE`, `AGENT_CLAUDE` : réservées aux tests).
Les jetons sont des valeurs factices."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.test_serveur_enveloppe import Banc as BancEmulation

RACINE = Path(__file__).resolve().parent.parent / "serveur_ovh"
TACHES = RACINE / "taches"
SCRIPT = TACHES / "lancer_agent.sh"
COMMUN = TACHES / "commun.sh"
EMULATION = TACHES / "lancer_emulation.sh"
ENTREE = RACINE / "images" / "agent" / "entree-agent.py"
ID = "t20261120-101500-ab12"
PREC = "t20261120-090000-cd34"
EMU = "t20261120-101600-ef56"
JETON = "jeton-factice-de-test-0123456789abcdef"
RAISON_SECRET = "secret de l'abonnement trouvé dans la sortie : rien n'est rapatrié"
ARGV = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--model", "claude-opus-5-5",
        "--tools", "Bash,Read,Edit", "--allowedTools", "Bash(git status:*),Read,Edit", "--permission-prompts", "none",
        "--append-system-prompt-file", "/entree/consigne.md", "--strict-mcp-config", "--setting-sources", "",
        "--disable-slash-commands"]

DOCKER = r'''echo "docker $*" >> "$FAUX_JOURNAL"
ET="$FAUX_ETAT"
case "$1" in
  run)
    case " $* " in
      *" -d "*) [ -n "${FAUX_RUN_ECHEC:-}" ] && { echo "boom" >&2; exit 125; }
                printf '%s\n' "$@" > "$ET/run.txt"; touch "$ET/vivant"; echo cid123 ;;
      *) printf '%s\n' "$@" > "$ET/verif.txt"
         [ -n "${FAUX_VERIF_EFFACE:-}" ] && rm -f "$FAUX_VERIF_EFFACE"     # pendant le contrôle : « fin » effacée
         [ -n "${FAUX_VERIF:-}" ] && cat "$FAUX_VERIF"
         [ -n "${FAUX_VERIF_ERR:-}" ] && cat "$FAUX_VERIF_ERR" >&2
         exit "${FAUX_VERIF_CODE:-0}" ;;
    esac ;;
  inspect)
    [ -e "$ET/mort" ] && rm -f "$ET/vivant"
    if [ -e "$ET/vivant" ]; then echo "true 999999"; exit 0; fi
    echo "Error: No such object: tache-x" >&2; exit 1 ;;
  stop)   # FAUX_STOP_ECRIT : l'entrée de l'agent conclut sur SIGTERM (paquet et fin.json) avant de partir
    if [ -n "${FAUX_STOP_ECRIT:-}" ] && [ -e "$ET/vivant" ]; then
      printf 'PAQUET' > "$FAUX_STOP_ECRIT/resultat.bundle"; printf '{"code": 143, "commits": 1}' > "$FAUX_STOP_ECRIT/fin.json"
    fi
    rm -f "$ET/vivant" ;;
  kill|rm) rm -f "$ET/vivant" ;;
esac
exit 0'''
FAUX = {
    "sudo": '[ "$1" = -n ] && shift\nexec "$@"',
    "docker": DOCKER,
    "flock": 'echo "flock $*" >> "$FAUX_JOURNAL"\n'
             'if [ "$1" = -n ]; then\n'
             '  n=$(cat "$FAUX_ETAT/flock" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAUX_ETAT/flock"\n'
             '  [ -n "${FAUX_FLOCK_OCCUPES:-}" ] && [ "$n" -le "$FAUX_FLOCK_OCCUPES" ] && exit 1\n'
             '  case " ${FAUX_FLOCK_PRIS:-} " in *" $n "*) exit 1 ;; esac\n'      # places prises, par numéro d'essai
             'fi\nexit 0',
    "setsid": 'echo "setsid $*" >> "$FAUX_JOURNAL"\nexec "$@"',
    "timeout": 'echo "timeout $*" >> "$FAUX_JOURNAL"\nshift\nexec "$@"',
    "git": 'echo "git $*" >> "$FAUX_JOURNAL"\nexit 0',
    # disque du serveur : 100 Go libres, jamais celui du poste ni du conteneur de tests (un /tmp de 4 Go y est « plein »)
    "df": 'printf "Filesystem 1024-blocks Used Available Capacity Mounted on\\n"\n'
          'printf "/dev/faux 209715200 104857600 %s 50%% /\\n" "${FAUX_DF_LIBRE_KO:-104857600}"',
    # le pont hôte (tâche 7) : un processus qui vit jusqu'à son arrêt et le dit
    "python3": 'echo "python3 $*" >> "$FAUX_JOURNAL"\ntrap \'echo "pont-arrete $*" >> "$FAUX_JOURNAL"; exit 0\' TERM\n'
               'while :; do sleep 0.2; done',
}

def demande(reprend=None, **limites):
    lim = {"duree_s": 2400, "tours": 200, "memoire_mo": 4096, "cpus": 2, "paquet_octets": 524288000, "flux_octets": 20971520}
    lim.update(limites)
    return {"id": ID, "projet": "Demo", "tache": "corriger-le-titre", "mode": "seul", "modele": "opus", "branche": "main",
            "base": "0" * 40, "limites": lim, "reprend": reprend, "places": 2}


class Banc:
    """HOME jetable avec ~/taches/<ID>/entree prête et le jeton factice ; le script lancé est celui du dépôt (où est le vrai
    pont_hote.py ; python3 est factice), ou une copie avec un faux pont_hote.py quand `pont` est vrai, ou une copie SANS
    pont_hote.py quand `pont` vaut "absent"."""

    def __init__(self, pont=False, **env):
        self.env, self.pont = env, pont

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
        self.script = SCRIPT
        if self.pont:
            copie = t / "copie"
            copie.mkdir()
            for f in (SCRIPT, COMMUN, EMULATION):
                shutil.copy(f, copie / f.name)
            if self.pont != "absent":
                (copie / "pont_hote.py").write_text("# faux pont hôte\n", newline="\n")
            self.script = copie / SCRIPT.name
        self.dossier = self.home / "taches" / ID
        self.entree = self.dossier / "entree"
        self.entree.mkdir(parents=True)
        self.ecrire_entree()
        (self.home / "agent-identifiants").mkdir()
        (self.home / "agent-identifiants" / "jeton").write_text(JETON + "\n", newline="\n")
        return self

    def ecrire_entree(self, **d):
        (self.entree / "projet.bundle").write_bytes(b"# v2 git bundle\n")
        (self.entree / "argv.json").write_text(json.dumps(ARGV), newline="\n")
        (self.entree / "consigne.md").write_text("Consigne.\n", newline="\n")
        (self.entree / "message.md").write_text("Message.\n", newline="\n")
        (self.entree / "demande.json").write_text(json.dumps({**demande(), **d}, indent=2), newline="\n")

    def __exit__(self, *a):
        for pid in (self.dossier / "veilleur.pid", self.dossier / "pont-hote.pid"):
            if pid.exists():
                subprocess.run(["bash", "-c", 'kill -9 "$(cat "$1")" 2>/dev/null; exit 0', "bash", pid.as_posix()])
        time.sleep(0.3)
        self._t.cleanup()

    def lancer(self, *args, env=None, ident=ID):
        e = dict(os.environ, HOME=self.home.as_posix(), PATH=self.bin.as_posix() + os.pathsep + os.environ["PATH"],
                 FAUX_JOURNAL=self.journal_fichier.as_posix(), FAUX_ETAT=self.et.as_posix(), ENVELOPPE_SONDE_S="0.2")
        e.update(self.env)
        e.update(env or {})
        corps = list(args) if args else ["seul", "30", "2048", "2", "2"]
        self.derniere = subprocess.run(["bash", self.script.as_posix(), ident, *corps], stdin=subprocess.DEVNULL,
                                       capture_output=True, text=True, encoding="utf-8", env=e, timeout=60)
        return self.derniere

    @property
    def journal(self):
        return self.journal_fichier.read_text(encoding="utf-8") if self.journal_fichier.exists() else ""

    def appels(self, prefixe):
        return [x for x in self.journal.splitlines() if x.startswith(prefixe)]

    def etat(self):
        return json.loads((self.dossier / "etat.json").read_text(encoding="utf-8"))

    def attendre_final(self, delai=30):
        fin = time.time() + delai
        while time.time() < fin:
            if self.appels("flock -u 8") and (self.dossier / "etat.json").exists() and \
                    self.etat()["etat"] not in ("en_cours", "en_attente"):
                return self.etat()
            time.sleep(0.1)
        raise AssertionError(f"état final jamais atteint : {self.etat() if (self.dossier / 'etat.json').exists() else None}"
                             f"\n{self.journal}")

    def arreter(self, motif=""):
        (self.dossier / "arret").write_text(motif, newline="\n")

    def mourir(self):
        (self.et / "mort").write_text("", newline="\n")

    def run_args(self, nom="run.txt"):
        return (self.et / nom).read_text(encoding="utf-8").splitlines()

    def h(self):
        """HOME tel que bash le voit (/tmp/... sous Git bash)."""
        return subprocess.run(["bash", "-c", 'printf %s "$HOME"'], env=dict(os.environ, HOME=self.home.as_posix()),
                              capture_output=True, text=True).stdout


def suite_dans(test, a, *motif):
    test.assertTrue(any(a[i:i + len(motif)] == list(motif) for i in range(len(a))), f"{motif} absent de {a}")


def volumes(a):
    return [a[i + 1] for i in range(len(a) - 1) if a[i] == "-v"]


def code_sans_commentaires(chemin):
    return "\n".join(x for x in chemin.read_text(encoding="utf-8").splitlines() if not x.lstrip().startswith("#"))


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestCommun(unittest.TestCase):
    def test_extraction_commun_sans_changement(self):
        commun = COMMUN.read_text(encoding="utf-8")
        emulation = EMULATION.read_text(encoding="utf-8")
        definies = set(re.findall(r"(?m)^([a-z_]+)\(\) \{", commun))
        for nom in ("ecrire_etat", "echapper_json", "maintenant_iso", "montrer_etat", "debut_ecrit", "liberer_creneau", "dk",
                    "debut_processus", "etat_docker", "etat_docker_sur", "conteneur_vivant", "arreter_conteneur",
                    "processus_vivant", "honorer_final", "occupe", "fin_erreur", "detacher_veilleur"):
            self.assertIn(nom, definies)
            self.assertNotRegex(emulation, rf"(?m)^\s*{nom}\(\) \{{", f"{nom} redéfinie dans lancer_emulation.sh")
        self.assertRegex(emulation, r'(?m)^\. "\$ICI/commun\.sh"')
        for f in (COMMUN, EMULATION):
            self.assertEqual(subprocess.run(["bash", "-n", f.as_posix()], capture_output=True).returncode, 0, f)
            self.assertNotIn(b"\r", f.read_bytes())
        with BancEmulation() as b:                                   # un cycle complet de l'émulation, inchangé
            r = b.lancer()
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertEqual(b.etat()["etat"], "en_cours")
            b.arreter()
            self.assertEqual(b.attendre_final()["etat"], "arretee")

    def test_emulation_ignore_les_conteneurs_d_agent(self):
        # un conteneur tache-* étiqueté myiafactory.genre=agent n'est pas un émulateur ; un conteneur sans étiquette (ancien)
        # ou d'un autre genre en reste un (75)
        for lignes, attendu in (("genre=agent", 0), ("genre=agent\ngenre=agent", 0), ("genre=", 75), ("genre=agent\ngenre=", 75),
                                ("genre=emulateur", 75)):
            with self.subTest(lignes=lignes), BancEmulation() as b:
                (b.bin / "docker").rename(b.bin / "docker-banc")
                (b.bin / "docker").write_text('#!/bin/sh\nif [ "$1" = ps ]; then echo "docker $*" >> "$FAUX_JOURNAL"; '
                                              'printf "%s\\n" "$FAUX_PS_LIGNES"; exit 0; fi\n'
                                              'exec "$(dirname "$0")/docker-banc" "$@"\n', newline="\n")
                (b.bin / "docker").chmod(0o755)
                r = b.lancer(env={"FAUX_PS_LIGNES": lignes})
                self.assertEqual(r.returncode, attendu, r.stderr + r.stdout)
                ps = b.appels("docker ps")
                self.assertTrue(ps and "name=^tache-" in ps[0] and "myiafactory.genre" in ps[0], b.journal)
                if attendu == 0:
                    b.arreter()
                    b.attendre_final()
                else:
                    self.assertEqual(b.appels("docker run"), [])


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEnveloppeAgent(unittest.TestCase):
    def test_agent_prend_le_premier_creneau_libre(self):
        with Banc(FAUX_FLOCK_OCCUPES="1") as b:
            r = b.lancer("seul", "30", "2048", "2", "3")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])["etat"], "en_cours")
            self.assertEqual((b.dossier / "creneau").read_text().strip(), "2")
            self.assertEqual(len(b.appels("flock -n 9")), 4, b.journal)        # les 4 places sont comptées
            noms = sorted(p.name for p in (b.home / "taches").glob(".creneau-agent-*"))
            self.assertEqual(noms, [f".creneau-agent-{i}" for i in (1, 2, 3, 4)])
            b.arreter()
            self.assertEqual(b.attendre_final()["etat"], "arretee")

    def test_agent_places_pleines_donne_75_et_en_attente(self):
        with Banc(FAUX_FLOCK_OCCUPES="2") as b:
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 75, r.stderr + r.stdout)
            e = b.etat()
            self.assertEqual((e["etat"], e["statut"]), ("en_attente", None))
            self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])["etat"], "en_attente")
            self.assertEqual(b.appels("docker"), [])
            self.assertEqual(b.appels("setsid"), [])

    def test_places_abaissees_jamais_depassees(self):
        # places 3 et 4 tenues (lancées quand le serveur en avait 4), puis places ramené à 2 : la place 1 est libre, mais
        # deux agents tournent déjà, un troisième serait de trop
        with Banc(FAUX_FLOCK_PRIS="3 4") as b:
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 75, r.stderr + r.stdout)
            self.assertEqual(b.etat()["etat"], "en_attente")
            self.assertEqual(b.appels("docker"), [])
        with Banc(FAUX_FLOCK_PRIS="4") as b:                      # une seule tenue : la place 1 est prise
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertEqual((b.dossier / "creneau").read_text().strip(), "1")
            b.arreter()
            b.attendre_final()

    def test_ligne_docker_run_agent(self):
        with Banc(SECRET_DU_POSTE="cle-du-poste-42", CLAUDE_CODE_OAUTH_TOKEN="jeton-du-poste-43") as b:
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            a = b.run_args()
            texte = "\n".join(a)
            h = b.h()
            uid = subprocess.run(["bash", "-c", "printf '%s:%s' \"$(id -u)\" \"$(id -g)\""], capture_output=True,
                                 text=True).stdout
            self.assertEqual(a[0], "run")
            for x in ("-d", "--rm", "--read-only"):
                self.assertIn(x, a)
            suite_dans(self, a, "--name", f"tache-{ID}")
            suite_dans(self, a, "--network", "myiafactory-agents")
            suite_dans(self, a, "--user", uid)
            suite_dans(self, a, "--tmpfs", "/tmp:size=1g")
            suite_dans(self, a, "--cap-drop", "ALL")
            suite_dans(self, a, "--security-opt", "no-new-privileges")
            suite_dans(self, a, "--pids-limit", "512")
            suite_dans(self, a, "--memory", "2048m")
            suite_dans(self, a, "--memory-swap", "2048m")
            suite_dans(self, a, "--cpus", "2")
            suite_dans(self, a, "--label", "myiafactory.genre=agent")     # l'émulation ne le compte pas comme un émulateur
            # AGENT_DUREE_S : la durée de l'enveloppe (argument 3) fait foi dans le conteneur, comme pour le veilleur
            self.assertEqual([a[i + 1] for i in range(len(a) - 1) if a[i] == "-e"], ["HOME=/maison", "AGENT_DUREE_S=30"])
            d = f"{h}/taches/{ID}"
            self.assertEqual(sorted(volumes(a)), sorted([f"{d}/entree:/entree:ro", f"{d}/travail:/travail",
                                                          f"{d}/maison:/maison", f"{d}/sortie:/sortie",
                                                          f"{h}/agent-identifiants/jeton:/run/identifiants/jeton:ro"]))
            self.assertEqual(a[-2:], ["myiafactory/agent", "entree-agent"])
            for interdit in ("CLAUDE_CODE_OAUTH_TOKEN", "docker.sock", "--privileged", "--env-file", JETON, "jeton-du-poste-43",
                             "cle-du-poste-42", ".ssh", "--network host", "host"):
                self.assertNotIn(interdit, a if interdit == "host" else texte)
            self.assertNotIn(JETON, b.journal)
            for sous in ("travail", "maison"):
                self.assertTrue((b.dossier / sous).is_dir())
            b.arreter()
            b.attendre_final()

    def test_pilote_monte_le_pont_seul_ne_le_monte_pas(self):
        with Banc(pont="absent") as b:                             # pont_hote.py absent du serveur : refusé, rien créé
            avant = sorted(p.name for p in b.dossier.iterdir())
            r = b.lancer("pilote", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 2, r.stderr + r.stdout)
            self.assertIn("pont", r.stderr)
            self.assertEqual(sorted(p.name for p in b.dossier.iterdir()), avant)
            self.assertEqual(b.journal, "")
        with Banc() as b:                                          # le script du dépôt : pilote accepté (tâche 7)
            self.assertTrue((TACHES / "pont_hote.py").is_file())
            (b.entree / "app.apk").write_bytes(b"PK")
            r = b.lancer("pilote", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertTrue(any(x.startswith("python3 -I ") and x.endswith(f"/pont_hote.py {ID} 30")   # durée de l'agent
                                for x in b.journal.splitlines()), b.journal)
            if os.name == "posix":
                self.assertEqual((b.dossier / "pont").stat().st_mode & 0o777, 0o700)
            b.arreter()
            self.assertEqual(b.attendre_final()["etat"], "arretee")
            self.assertTrue(b.appels("pont-arrete"), b.journal)
        with Banc(pont=True) as b:
            (b.entree / "app.apk").write_bytes(b"PK")
            r = b.lancer("pilote", "30", "2048", "2", "2", EMU)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            h, d = b.h(), f"{b.h()}/taches/{ID}"
            v = volumes(b.run_args())
            self.assertIn(f"{d}/pont:/pont", v)
            self.assertIn(f"{d}/outil:/outil:ro", v)
            self.assertTrue(any(x.startswith("python3 ") and f"pont_hote.py {ID}" in x for x in b.journal.splitlines()), b.journal)
            self.assertNotIn("/outil:/outil\n", "\n".join(v) + "\n")     # jamais en écriture
            b.arreter()
            b.attendre_final()
        with Banc(pont=True) as b:                                 # pilote sans APK : échec net, rien lancé
            r = b.lancer("pilote", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
            self.assertIn("app.apk", b.etat()["raison"])
            self.assertEqual(b.appels("docker run"), [])
        with Banc(pont=True) as b:                                 # seul : ni pont ni outil
            self.assertEqual(b.lancer("seul", "30", "2048", "2", "2").returncode, 0)
            v = "\n".join(volumes(b.run_args()))
            self.assertNotIn("/pont", v)
            self.assertNotIn("/outil", v)
            self.assertEqual(b.appels("python3"), [])
            b.arreter()
            b.attendre_final()

    def prec_finie(self, b, projet="Demo"):
        prec = b.home / "taches" / PREC
        (prec / "travail" / "projet").mkdir(parents=True)
        (prec / "maison").mkdir()
        (prec / "entree").mkdir()
        (prec / "entree" / "demande.json").write_text(json.dumps({**demande(), "id": PREC, "projet": projet}, indent=2),
                                                      newline="\n")
        (prec / "etat.json").write_text(json.dumps({"id": PREC, "etat": "terminee"}), newline="\n")
        b.ecrire_entree(reprend=PREC)

    def test_reprise_d_un_autre_projet_refusee(self):
        with Banc() as b:
            self.prec_finie(b, projet="Autre")
            r = b.lancer()
            self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
            self.assertIn("projet", b.etat()["raison"])
            self.assertEqual(b.appels("docker run"), [])
            self.assertEqual(list((b.dossier / "travail").iterdir()), [])
        with Banc() as b:
            self.prec_finie(b)
            self.assertEqual(b.lancer().returncode, 0)
            b.arreter()
            b.attendre_final()

    def test_reprise_copie_sans_suivre_les_liens(self):
        with Banc() as b:
            prec = b.home / "taches" / PREC
            (prec / "travail" / "projet").mkdir(parents=True)
            (prec / "maison" / ".claude").mkdir(parents=True)
            (prec / "entree").mkdir()
            (prec / "entree" / "demande.json").write_text(json.dumps(demande()), newline="\n")
            (prec / "travail" / "projet" / "a.txt").write_text("travail gardé", newline="\n")
            (prec / "maison" / ".claude" / "session.jsonl").write_text("{}", newline="\n")
            (prec / "etat.json").write_text(json.dumps({"id": PREC, "etat": "terminee", "statut": "ok", "debut": None,
                                                        "fin": None, "raison": "x"}), newline="\n")
            hote = b.home / "fichier-de-l-hote.txt"
            hote.write_text("ne jamais copier", newline="\n")
            try:
                os.symlink(hote, prec / "travail" / "lien")
            except OSError:
                self.skipTest("liens symboliques indisponibles sur ce poste")
            b.ecrire_entree(reprend=PREC)
            r = b.lancer(env={"MSYS": "winsymlinks:nativestrict"})     # Git bash : de vrais liens (sans effet ailleurs)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertEqual((b.dossier / "travail" / "projet" / "a.txt").read_text(), "travail gardé")
            self.assertTrue((b.dossier / "maison" / ".claude" / "session.jsonl").exists())
            self.assertTrue((b.dossier / "travail" / "lien").is_symlink())        # copié comme lien, jamais suivi
            self.assertIn("cp -a", code_sans_commentaires(SCRIPT))
            self.assertNotRegex(code_sans_commentaires(SCRIPT), r"cp\s[^\n]*(-L|--dereference)")
            b.arreter()
            b.attendre_final()
        with Banc() as b:                                          # reprise d'une tâche encore en cours : refusée
            prec = b.home / "taches" / PREC
            (prec / "travail").mkdir(parents=True)
            (prec / "maison").mkdir()
            (prec / "etat.json").write_text(json.dumps({"id": PREC, "etat": "en_cours"}), newline="\n")
            b.ecrire_entree(reprend=PREC)
            self.assertEqual(b.lancer().returncode, 1)
            self.assertEqual(b.appels("docker run"), [])

    def test_secret_dans_le_flux_vide_la_sortie(self):
        with Banc() as b:
            self.assertEqual(b.lancer().returncode, 0)
            sortie = b.dossier / "sortie"
            (sortie / "flux.jsonl").write_text('{"type": "assistant", "texte": "env : CLAUDE_CODE_OAUTH_TOKEN=' + JETON +
                                               '"}\n', newline="\n")
            (sortie / "fin.json").write_text('{"code": 0, "commits": 0, "branche": null, "base": "' + "0" * 40 + '"}', newline="\n")
            b.mourir()
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"], f["raison"]), ("echouee", "erreur", RAISON_SECRET))
            self.assertEqual(list(sortie.iterdir()), [])
            self.assertNotIn(JETON, (b.dossier / "etat.json").read_text(encoding="utf-8"))
        for fichier in ("claude.err", "fin.json"):                 # le jeton ailleurs dans la sortie : de même
            with self.subTest(fichier=fichier), Banc() as b:
                self.assertEqual(b.lancer().returncode, 0)
                (b.dossier / "sortie" / "sous").mkdir()
                (b.dossier / "sortie" / "sous" / fichier).write_text("x " + JETON, newline="\n")
                b.arreter("fin")
                f = b.attendre_final()
                self.assertEqual((f["etat"], f["raison"]), ("echouee", RAISON_SECRET))
                self.assertEqual(list((b.dossier / "sortie").iterdir()), [])

    def test_secret_dans_un_commit_vide_la_sortie(self):
        # le veilleur hérite de l'environnement du lancement : FAUX_VERIF (ce que montre le conteneur de contrôle) dès le départ
        with Banc() as b:
            verif = b.t / "verif.txt"
            verif.write_text("commit abc\n\n+cle = \"" + JETON + "\"\n", newline="\n")
            self.assertEqual(b.lancer(env={"FAUX_VERIF": verif.as_posix()}).returncode, 0)
            (b.dossier / "travail" / "projet" / ".git").mkdir(parents=True)
            sortie = b.dossier / "sortie"
            (sortie / "flux.jsonl").write_text('{"type": "result"}\n', newline="\n")
            (sortie / "resultat.bundle").write_bytes(b"# v2 git bundle\n\x00compresse")
            (sortie / "fin.json").write_text('{"code": 0, "commits": 1}', newline="\n")
            b.mourir()
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"], f["raison"]), ("echouee", "erreur", RAISON_SECRET))
            self.assertEqual(list(sortie.iterdir()), [])
            a = b.run_args("verif.txt")                             # le conteneur de contrôle : sans jeton ni réseau
            h, d = b.h(), f"{b.h()}/taches/{ID}"
            suite_dans(self, a, "--network", "none")
            self.assertIn("--read-only", a)
            suite_dans(self, a, "--cap-drop", "ALL")
            self.assertIn(f"{d}/travail:/travail:ro", volumes(a))
            self.assertTrue(all(v.endswith(":ro") for v in volumes(a)), volumes(a))
            self.assertFalse([v for v in volumes(a) if "jeton" in v or "identifiants" in v], volumes(a))
            self.assertNotIn("myiafactory-agents", a)
            self.assertNotIn("-d", a)
            self.assertEqual(a[-3:], ["myiafactory/agent", "entree-agent", "--verifier"])

    def test_controle_impossible_vide_aussi_la_sortie(self):
        with Banc() as b:                                          # conteneur de contrôle en échec : rien n'est rapatrié
            self.assertEqual(b.lancer(env={"FAUX_VERIF_CODE": "3"}).returncode, 0)
            (b.dossier / "travail" / "projet").mkdir(parents=True)
            (b.dossier / "sortie" / "fin.json").write_text('{"code": 0}', newline="\n")
            b.mourir()
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("echouee", "erreur"))
            self.assertIn("rien n'est rapatrié", f["raison"])
            self.assertEqual(list((b.dossier / "sortie").iterdir()), [])

    def test_fin_normale_sans_secret_garde_la_sortie(self):
        with Banc() as b:
            verif = b.t / "verif.txt"
            verif.write_text("commit abc\n\n+propre\n", newline="\n")
            self.assertEqual(b.lancer(env={"FAUX_VERIF": verif.as_posix()}).returncode, 0)
            (b.dossier / "travail" / "projet").mkdir(parents=True)
            (b.dossier / "sortie" / "flux.jsonl").write_text('{"type": "result"}\n', newline="\n")
            (b.dossier / "sortie" / "fin.json").write_text('{"code": 0}', newline="\n")
            b.mourir()
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "ok"))
            self.assertEqual(sorted(p.name for p in (b.dossier / "sortie").iterdir()), ["fin.json", "flux.jsonl"])
            self.assertTrue((b.et / "verif.txt").exists())
        with Banc() as b:                                          # conteneur disparu sans fin.json : échec
            self.assertEqual(b.lancer().returncode, 0)
            b.mourir()
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("echouee", "erreur"))
            self.assertIn("fin.json", f["raison"])

    def test_aucun_git_hote_sur_travail(self):
        with Banc() as b:
            self.assertEqual(b.lancer().returncode, 0)
            projet = b.dossier / "travail" / "projet"
            (projet / ".git" / "hooks").mkdir(parents=True)
            (projet / ".git" / "config").write_text("[core]\n\tfsmonitor = /bin/sh -c 'touch /tmp/piege'\n", newline="\n")
            (b.dossier / "sortie" / "fin.json").write_text('{"code": 0}', newline="\n")
            b.mourir()
            b.attendre_final()
            self.assertEqual(b.appels("git"), [], b.journal)
            self.assertFalse([x for x in b.journal.splitlines() if "/travail" in x and "docker run" not in x])
        code = code_sans_commentaires(SCRIPT) + "\n" + code_sans_commentaires(COMMUN)
        self.assertNotRegex(code, r"(^|[\s;|&(])git\s")

    def emulation_liee(self, b, emu, agent=ID, genre="emulation"):
        d = b.home / "taches" / emu
        d.mkdir(parents=True)
        (d / "demande.json").write_text(json.dumps({"id": emu, "type": genre, "projet": "Demo"}, indent=2), newline="\n")
        (d / "agent").write_text(agent + "\n", newline="\n")
        return d

    def test_arret_coupe_agent_pont_et_emulation(self):
        with Banc(pont=True) as b:
            (b.entree / "app.apk").write_bytes(b"PK")
            emu = self.emulation_liee(b, EMU)
            self.assertEqual(b.lancer("pilote", "30", "2048", "2", "2", EMU).returncode, 0)
            self.assertTrue((b.dossier / "pont-hote.pid").exists())
            b.arreter()
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("arretee", "ok"))
            self.assertTrue(any(x.startswith("docker stop") and f"tache-{ID}" in x for x in b.journal.splitlines()), b.journal)
            self.assertTrue(b.appels("pont-arrete"), b.journal)
            self.assertEqual((emu / "arret").read_text().strip(), "fin")
            j = b.journal
            self.assertLess(j.index("docker stop"), j.index("flock -u 8"))
            self.assertLess(j.index("pont-arrete"), j.index("flock -u 8"))

    def test_fin_de_l_emulation_reecrite_apres_le_controle(self):
        # « fin » écrite à l'émulation avant le contrôle du secret a pu être effacée (lancement de l'émulation encore en
        # cours) : finir la réécrit APRÈS le contrôle
        with Banc(pont=True) as b:
            (b.entree / "app.apk").write_bytes(b"PK")
            emu = self.emulation_liee(b, EMU)
            r = b.lancer("pilote", "30", "2048", "2", "2", EMU, env={"FAUX_VERIF_EFFACE": (emu / "arret").as_posix()})
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            b.arreter()
            b.attendre_final()
            self.assertTrue((b.et / "verif.txt").exists())                  # le contrôle a eu lieu (et a effacé arret)
            self.assertTrue((emu / "arret").exists(), b.journal)
            self.assertEqual((emu / "arret").read_text().strip(), "fin")

    def test_emulation_liee_seulement_par_l_hote(self):
        # pont/emulation (écrit dans un dossier monté dans le conteneur) n'est jamais lu ; $DOSSIER/emulation (hôte seul) l'est,
        # et seulement pour une tâche d'émulation liée à cet agent
        autre = "t20261120-101700-aa99"
        with Banc(pont=True) as b:
            (b.entree / "app.apk").write_bytes(b"PK")
            victime = self.emulation_liee(b, autre, agent="t20261120-111111-bbbb")
            liee = self.emulation_liee(b, EMU)
            self.assertEqual(b.lancer("pilote", "30", "2048", "2", "2").returncode, 0)
            (b.dossier / "pont" / "emulation").write_text(autre + "\n", newline="\n")
            (b.dossier / "emulation").write_text(EMU + "\n", newline="\n")
            b.arreter()
            b.attendre_final()
            self.assertFalse((victime / "arret").exists())
            self.assertEqual((liee / "arret").read_text().strip(), "fin")
        with Banc(pont=True) as b:                                 # argument 7 non lié à cet agent, ou pas une émulation
            (b.entree / "app.apk").write_bytes(b"PK")
            for genre, agent in (("emulation", "t20261120-111111-bbbb"), ("agent", ID)):
                with self.subTest(genre=genre, agent=agent):
                    shutil.rmtree(b.home / "taches" / EMU, ignore_errors=True)
                    emu = self.emulation_liee(b, EMU, agent=agent, genre=genre)
                    for f in ("etat.json", "veilleur.pid", "enveloppe.pid", "arret", "flock"):
                        (b.dossier / f).unlink(missing_ok=True)
                    (b.et / "flock").unlink(missing_ok=True)
                    self.assertEqual(b.lancer("pilote", "30", "2048", "2", "2", EMU).returncode, 0)
                    b.arreter()
                    b.attendre_final()
                    self.assertFalse((emu / "arret").exists())

    def test_echeance_donne_limite(self):
        with Banc() as b:
            self.assertEqual(b.lancer("seul", "1", "2048", "2", "2").returncode, 0)
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))
            self.assertIn("durée", f["raison"].lower())
            self.assertTrue(b.appels("docker stop"), b.journal)

    def test_echeance_garde_le_travail_de_l_agent(self):
        # docker stop laisse 60 s à l'entrée pour conclure (paquet des commits déjà faits) : rien n'est jeté, état limite
        with Banc() as b:
            sortie = b.dossier / "sortie"
            self.assertEqual(b.lancer("seul", "1", "2048", "2", "2", env={"FAUX_STOP_ECRIT": sortie.as_posix()}).returncode, 0)
            (b.dossier / "travail" / "projet").mkdir(parents=True)
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))
            self.assertEqual(sorted(p.name for p in sortie.iterdir()), ["fin.json", "resultat.bundle"])
            self.assertTrue(any(x.startswith("docker stop -t 60") for x in b.journal.splitlines()), b.journal)
        with Banc() as b:                                          # l'entrée a tenu sa propre échéance (avant le veilleur)
            self.assertEqual(b.lancer().returncode, 0)
            (b.dossier / "sortie" / "fin.json").write_text('{"code": 137, "commits": 1, "echeance": true}', newline="\n")
            b.mourir()
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))
        self.assertIn('stop -t "$DELAI_ARRET"', COMMUN.read_text(encoding="utf-8"))
        self.assertIn("DELAI_ARRET=60", SCRIPT.read_text(encoding="utf-8"))
        self.assertNotIn("DELAI_ARRET=", EMULATION.read_text(encoding="utf-8"))   # l'émulation garde 10 s

    def test_paquet_plante_sans_depot_est_controle(self):
        # l'agent efface travail/projet et dépose un paquet dans sortie/ : le contrôle a lieu quand même et se ferme
        with Banc(FAUX_VERIF_CODE="3") as b:
            self.assertEqual(b.lancer().returncode, 0)
            (b.dossier / "sortie" / "resultat.bundle").write_bytes(b"# v2 git bundle\n-" + b"0" * 40 + b"\n\nPACK")
            (b.dossier / "sortie" / "fin.json").write_text('{"code": 0, "commits": 1}', newline="\n")
            b.mourir()
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("echouee", "erreur"))
            self.assertTrue((b.et / "verif.txt").exists())
            self.assertEqual(list((b.dossier / "sortie").iterdir()), [])

    def test_jeton_encode_en_base64_trouve(self):
        import base64
        for decalage in (0, 1, 2):
            with self.subTest(decalage=decalage), Banc() as b:
                self.assertEqual(b.lancer().returncode, 0)
                code = base64.b64encode(b"x" * decalage + JETON.encode() + b"\n").decode()
                (b.dossier / "sortie" / "flux.jsonl").write_text('{"texte": "' + code + '"}\n', newline="\n")
                (b.dossier / "sortie" / "fin.json").write_text('{"code": 0}', newline="\n")
                b.mourir()
                f = b.attendre_final()
                self.assertEqual((f["etat"], f["raison"]), ("echouee", RAISON_SECRET))

    def test_fichier_jeton_mal_forme_ferme_le_controle(self):
        for contenu in (JETON + "\n\n", JETON + "\nautre-ligne-de-vingt-car\n", "court\n", JETON + " x\n"):
            with self.subTest(contenu=contenu), Banc() as b:
                self.assertEqual(b.lancer().returncode, 0)
                (b.home / "agent-identifiants" / "jeton").write_text(contenu, newline="\n")
                (b.dossier / "sortie" / "fin.json").write_text('{"code": 0}', newline="\n")
                b.mourir()
                f = b.attendre_final()
                self.assertEqual((f["etat"], f["statut"]), ("echouee", "erreur"))
                self.assertEqual(list((b.dossier / "sortie").iterdir()), [])

    def test_controle_log_sans_le_jeton(self):
        with Banc() as b:
            err = b.t / "err.txt"
            err.write_text("fatal: blob contenant " + JETON + "\nautre ligne\n", newline="\n")
            self.assertEqual(b.lancer(env={"FAUX_VERIF_ERR": err.as_posix()}).returncode, 0)
            (b.dossier / "travail" / "projet").mkdir(parents=True)
            (b.dossier / "sortie" / "fin.json").write_text('{"code": 0}', newline="\n")
            b.mourir()
            b.attendre_final()
            for f in b.dossier.rglob("*"):
                if f.is_file():
                    self.assertNotIn(JETON.encode(), f.read_bytes(), f)
            self.assertIn("autre ligne", (b.dossier / "controle.log").read_text(encoding="utf-8"))

    def test_espace_disque_et_taille_du_travail(self):
        with Banc(ENVELOPPE_LIBRE_MIN_KO="999999999999") as b:      # disque presque plein : arrêt en limite
            self.assertEqual(b.lancer().returncode, 0)
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))
            self.assertIn("disque", f["raison"].lower())
        with Banc(ENVELOPPE_TRAVAIL_MAX_KO="100", ENVELOPPE_DU_TRAVAIL_S="1") as b:
            self.assertEqual(b.lancer().returncode, 0)
            (b.dossier / "maison" / "gros.bin").write_bytes(b"x" * 300 * 1024)
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))
            self.assertIn("travail", f["raison"].lower())
        code = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("LIBRE_MIN_KO=5242880", code)
        self.assertIn("TRAVAIL_MAX_KO=8388608", code)
        self.assertIn("--apparent-size", code)

    def test_virgule_ou_deux_points_refuses_sans_rien_creer(self):
        with Banc() as b:
            home = b.t / "ho,me"
            home.mkdir()
            r = b.lancer(env={"HOME": home.as_posix()})
            self.assertEqual(r.returncode, 2, r.stderr + r.stdout)
            self.assertFalse((home / "taches").exists())
            self.assertEqual(b.journal, "")

    def test_entrees_et_jeton_exiges(self):
        for manquant in ("projet.bundle", "argv.json", "consigne.md", "message.md", "demande.json"):
            with self.subTest(manquant=manquant), Banc() as b:
                (b.entree / manquant).unlink()
                r = b.lancer()
                self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
                self.assertEqual((b.etat()["etat"], b.etat()["statut"]), ("echouee", "erreur"))
                self.assertIn(manquant, b.etat()["raison"])
                self.assertEqual(b.appels("docker run"), [])
                self.assertTrue(b.appels("flock -u 8"))
        with Banc() as b:
            (b.home / "agent-identifiants" / "jeton").unlink()
            r = b.lancer()
            self.assertEqual(r.returncode, 1)
            self.assertIn("enregistrer_jeton.sh", b.etat()["raison"])
            self.assertEqual(b.appels("docker run"), [])

    def test_docker_run_en_echec_est_une_erreur(self):
        with Banc(FAUX_RUN_ECHEC="1") as b:
            r = b.lancer()
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertEqual((b.etat()["etat"], b.etat()["statut"]), ("echouee", "erreur"))
            self.assertTrue(b.appels("flock -u 8"))

    def test_ptrace_scope_zero_refuse_inconnu_averti(self):
        with Banc() as b:                                          # 0 : un agent pourrait tracer l'entrée : refusé
            scope = b.t / "ptrace_scope"
            scope.write_text("0\n", newline="\n")
            r = b.lancer(env={"ENVELOPPE_PTRACE_SCOPE": scope.as_posix()})
            self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
            self.assertEqual((b.etat()["etat"], b.etat()["statut"]), ("echouee", "erreur"))
            self.assertIn("ptrace_scope", b.etat()["raison"])
            self.assertEqual(b.appels("docker run"), [])
            self.assertTrue(b.appels("flock -u 8"))
        with Banc() as b:                                          # 1 : démarre, sans avertissement
            scope = b.t / "ptrace_scope"
            scope.write_text("1\n", newline="\n")
            r = b.lancer(env={"ENVELOPPE_PTRACE_SCOPE": scope.as_posix()})
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertNotIn("ptrace_scope", r.stderr)
            b.arreter()
            b.attendre_final()
        with Banc() as b:                                          # illisible (pas de Yama) : démarre, averti
            r = b.lancer(env={"ENVELOPPE_PTRACE_SCOPE": (b.t / "absent").as_posix()})
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertIn("ptrace_scope inconnu", r.stderr)
            self.assertIn("ptrace_scope inconnu", (b.dossier / "veilleur.log").read_text(encoding="utf-8"))
            b.arreter()
            b.attendre_final()
        self.assertIn("PTRACE_SCOPE=/proc/sys/kernel/yama/ptrace_scope", SCRIPT.read_text(encoding="utf-8"))

    def test_identifiant_deja_utilise_et_tache_en_cours(self):
        with Banc() as b:
            (b.dossier / "etat.json").write_text(json.dumps({"id": ID, "etat": "terminee"}), newline="\n")
            self.assertEqual(b.lancer().returncode, 4)
            self.assertEqual(b.journal, "")

    def test_arguments_hostiles_refuses_sans_rien_creer(self):
        mauvais = [("autre", "30", "2048", "2", "2"), ("seul", "0", "2048", "2", "2"), ("seul", "030", "2048", "2", "2"),
                   ("seul", "30", "100", "2", "2"), ("seul", "30", "2048", "0", "2"), ("seul", "30", "2048", "2", "0"),
                   ("seul", "30", "2048", "2", "5"), ("seul", "30", "2048", "2", "02"), ("seul", "30", "2048", "2"),
                   ("seul", "30", "2048", "2", "2", "../x"), ("seul", "30", "2048", "2", "2", EMU, "en-trop"),
                   ("seul", "30", "2048", "2", "2\x1b"), ("seul", "2\x07", "2048", "2", "2"),     # \n final : perdu par Git bash
                   ("seul", "$(id)", "2048", "2", "2")]
        with Banc() as b:
            for ident in ("../x", f"{ID};ls", "t20261120-101500-zzzz", ""):
                with self.subTest(ident=ident):
                    self.assertEqual(b.lancer(ident=ident).returncode, 2)
            for p in mauvais:
                with self.subTest(p=p):
                    self.assertEqual(b.lancer(*p).returncode, 2)
            self.assertEqual(b.journal, "")
            self.assertFalse((b.dossier / "travail").exists())
            self.assertFalse((b.dossier / "etat.json").exists())

    def test_scripts_syntaxe_lf_et_sans_eval(self):
        for f in (SCRIPT, COMMUN):
            with self.subTest(f=f.name):
                self.assertEqual(subprocess.run(["bash", "-n", f.as_posix()], capture_output=True).returncode, 0)
                self.assertNotIn(b"\r", f.read_bytes())
                code = code_sans_commentaires(f)
                self.assertNotRegex(code, r"\beval\b")
                self.assertNotRegex(code, r"(^|[^\w.-])bash\s+-c\b")
                self.assertNotRegex(code, r"(?m)^\s*set -[a-z]*e")


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEmulationLiee(unittest.TestCase):
    """lancer_emulation.sh d'une émulation liée à un agent (~/taches/<emu>/agent, écrit par le pont hôte) : arret jamais
    effacé, refus si l'agent est fini, arrêt de lui-même quand l'agent finit ou que son pont hôte disparaît."""

    def lier(self, b, etat="en_cours"):
        b.dossier.mkdir(parents=True, exist_ok=True)
        (b.dossier / "agent").write_text(ID + "\n", newline="\n")
        agent = b.home / "taches" / ID
        agent.mkdir(parents=True, exist_ok=True)
        (agent / "etat.json").write_text(json.dumps({"id": ID, "etat": etat}), newline="\n")
        return agent

    def pont_vivant(self, agent):
        """Un processus dont la ligne de commande porte « pont_hote.py <ID> », son PID (vu par bash) dans pont-hote.pid."""
        pid = agent / "pont-hote.pid"
        p = subprocess.Popen(["bash", "-c", 'echo $$ > "$F"; while :; do sleep 1; done', "pont_hote.py", ID],
                             env=dict(os.environ, F=pid.as_posix()), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        fin = time.time() + 10
        while not (pid.exists() and pid.read_text().strip()) and time.time() < fin:
            time.sleep(0.05)
        numero = pid.read_text().strip()

        def tuer():
            subprocess.run(["bash", "-c", 'kill -9 "$1" 2>/dev/null; exit 0', "bash", numero])
            p.kill()
            p.wait(timeout=10)
        self.addCleanup(tuer)
        return tuer

    def test_emulation_liee_s_arrete_quand_l_agent_finit_ou_que_le_pont_disparait(self):
        for cas in ("agent fini", "pont parti"):
            with self.subTest(cas=cas), BancEmulation() as b:
                agent = self.lier(b)
                tuer = self.pont_vivant(agent)
                r = b.lancer("pilote", "60", "60", "2048", "2")
                self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
                time.sleep(1)
                self.assertEqual(b.etat()["etat"], "en_cours")             # agent actif : l'émulation continue
                if cas == "agent fini":
                    (agent / "etat.json").write_text(json.dumps({"id": ID, "etat": "terminee"}), newline="\n")
                else:
                    tuer()
                f = b.attendre_final()
                self.assertEqual((f["etat"], f["statut"]), ("terminee", "ok"))
                self.assertIn("Agent lié", f["raison"])
                self.assertTrue(b.appels("docker stop"), b.journal)

    def test_emulation_liee_refusee_si_agent_fini_ou_arret_demande(self):
        with BancEmulation() as b:                                       # agent déjà fini : rien ne démarre
            self.lier(b, etat="arretee")
            r = b.lancer("pilote", "60", "60", "2048", "2")
            self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
            self.assertEqual(b.etat()["etat"], "arretee")
            self.assertEqual(b.appels("docker run"), [])
        with BancEmulation() as b:                                       # « fin » écrite avant le lancement : gardée
            agent = self.lier(b)
            self.pont_vivant(agent)
            (b.dossier / "arret").write_text("fin\n", newline="\n")
            r = b.lancer("pilote", "60", "60", "2048", "2")
            self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
            self.assertEqual((b.dossier / "arret").read_text().strip(), "fin")
            self.assertEqual(b.appels("docker run"), [])
        with BancEmulation() as b:                                       # tranche A (pas d'agent lié) : inchangée
            b.dossier.mkdir(parents=True)
            (b.dossier / "arret").write_text("", newline="\n")
            r = b.lancer("pilote", "60", "60", "2048", "2")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertFalse((b.dossier / "arret").exists())
            b.arreter()
            b.attendre_final()


# ------------------------------------------------------------------------------------------- entrée du conteneur (Python)

FAUX_CLAUDE = r'''import json, os, subprocess, sys, time
cmd = json.loads(sys.stdin.read() or "{}")
with open(os.path.join(os.environ["HOME"], "vu.json"), "w", encoding="utf-8") as f:
    json.dump({"argv": sys.argv[1:], "env": dict(os.environ), "cwd": os.getcwd()}, f)
for nom, texte in cmd.get("fichiers", {}).items():
    with open(nom, "w", encoding="utf-8", newline="\n") as f:
        f.write(texte)
if cmd.get("commit"):
    subprocess.run(["git", "add", "-A"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", cmd["commit"]], check=True)
    for nom, texte in cmd.get("apres", {}).items():
        with open(nom, "w", encoding="utf-8", newline="\n") as f:
            f.write(texte)
for cle, valeur in cmd.get("configurer", []):    # l'agent piège la configuration de son dépôt
    subprocess.run(["git", "config", cle, valeur], check=True)
racine =os.path.dirname(os.environ["HOME"])
if cmd.get("effacer_depot"):                 # l'agent efface son dépôt (après en être sorti)
    import shutil, stat
    os.chdir(os.environ["HOME"])
    def forcer(f, p, e):
        os.chmod(p, stat.S_IWRITE)
        f(p)
    shutil.rmtree(os.path.join(racine, "travail", "projet"), onexc=forcer)
for nom, texte in cmd.get("planter", {}).items():   # l'agent dépose ses propres fichiers dans /sortie
    with open(os.path.join(racine, "sortie", nom), "w", encoding="utf-8") as f:
        f.write(texte)
for ligne in cmd.get("flux", []):
    sys.stdout.write(json.dumps(ligne) + "\n")
sys.stdout.flush()
if cmd.get("attendre_direct"):               # l'agent lit ce que l'entrée publie de lui pendant qu'il tourne
    chemin = os.path.join(racine, "sortie", "direct.json")
    if cmd.get("lien_direct"):
        os.symlink(os.path.join(racine, "maison", "secret.txt"), chemin)
    for _ in range(200):
        if os.path.exists(chemin) and not os.path.islink(chemin):
            break
        time.sleep(0.1)
    ok = os.path.exists(chemin) and not os.path.islink(chemin)
    with open(os.path.join(os.environ["HOME"], "direct-vu.json"), "w", encoding="utf-8") as f:
        json.dump({"lien": os.path.islink(chemin), "texte": open(chemin, encoding="utf-8").read() if ok else None}, f)
if cmd.get("dormir"):
    time.sleep(600)
if cmd.get("bavard"):
    while True:
        sys.stdout.write("x" * 999 + "\n")
        sys.stdout.flush()
sys.stderr.buffer.write(cmd.get("err", "").encode("utf-8"))
sys.stderr.flush()
sys.exit(cmd.get("code", 0))
'''


def charger_entree():
    spec = importlib.util.spec_from_file_location("entree_agent", ENTREE)
    module = importlib.util.module_from_spec(spec)
    avant, sys.dont_write_bytecode = sys.dont_write_bytecode, True     # aucun __pycache__ dans serveur_ovh/images
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = avant
    return module


def effacer(chemin):
    """rmtree qui passe les objets de git en lecture seule (Windows)."""
    def forcer(fonction, p, _e):
        os.chmod(p, 0o700)
        fonction(p)
    if os.path.lexists(chemin):
        shutil.rmtree(chemin, onexc=forcer)


def git(depot, *args):
    return subprocess.run(["git", "-C", str(depot), *args], check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()


@unittest.skipUnless(shutil.which("git"), "git absent")
class TestEntreeAgent(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._t.cleanup)
        t = self.t = Path(self._t.name)
        src = t / "source"
        src.mkdir()
        git(src, "init", "-q", "-b", "main")
        git(src, "config", "user.name", "Poste")
        git(src, "config", "user.email", "poste@exemple.invalid")
        (src / "titre.txt").write_text("Ancien titre\n", newline="\n")
        git(src, "add", "-A")
        git(src, "commit", "-q", "-m", "Départ")
        self.base = git(src, "rev-parse", "HEAD")
        self.racine = t / "racine"
        for d in ("entree", "travail", "sortie", "maison", "run/identifiants"):
            (self.racine / d).mkdir(parents=True)
        git(src, "bundle", "create", "-q", (self.racine / "entree" / "projet.bundle").as_posix(), "HEAD", "main")
        (self.racine / "run" / "identifiants" / "jeton").write_text(JETON + "\n", newline="\n")
        (self.racine / "entree" / "consigne.md").write_text("Consigne.\n", newline="\n")
        self.faux = t / "faux_claude.py"
        self.faux.write_text(FAUX_CLAUDE, encoding="utf-8", newline="\n")
        self.ecrire(ARGV, {})

    def ecrire(self, argv, message, **d):
        dem = {**demande(), "base": self.base, **d}
        (self.racine / "entree" / "demande.json").write_text(json.dumps(dem), newline="\n")
        (self.racine / "entree" / "argv.json").write_text(json.dumps(argv), newline="\n")
        (self.racine / "entree" / "message.md").write_text(json.dumps(message), newline="\n")

    def lancer(self, *args, **plus):
        env = {k: v for k, v in os.environ.items() if k not in ("AGENT_RACINE", "AGENT_CLAUDE", "AGENT_DUREE_S")}
        env.update(AGENT_RACINE=self.racine.as_posix(), AGENT_CLAUDE=json.dumps([sys.executable, self.faux.as_posix()]),
                   **plus)
        return subprocess.run([sys.executable, ENTREE.as_posix(), *args], capture_output=True, env=env, timeout=120,
                              stdin=subprocess.DEVNULL)

    def sortie(self, nom):
        return self.racine / "sortie" / nom

    def fin(self):
        return json.loads(self.sortie("fin.json").read_text(encoding="utf-8"))

    def vu(self):
        p = self.racine / "maison" / "vu.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    @property
    def depot(self):
        return self.racine / "travail" / "projet"

    # --- le suivi en direct : /sortie/direct.json, publié par l'entrée pendant que l'agent travaille
    def ligne_outil(self, nom, entree, modele="claude-opus-5-5", ident="m1", usage=None, t=None):
        d = {"type": "assistant", "message": {"id": ident, "model": modele, "usage": usage or {"input_tokens": 10, "output_tokens": 5},
                                              "content": [{"type": "tool_use", "name": nom, "input": entree}]}}
        if t:
            d["timestamp"] = t
        return json.dumps(d) + "\n"

    def test_resumer_flux_actions_phase_et_usage(self):
        e = charger_entree()
        flux = (self.ligne_outil("Read", {"file_path": "/travail/projet/a.py"}, ident="m1", t="2026-11-26T10:00:00Z")
                + self.ligne_outil("Edit", {"file_path": "/travail/projet/scenes/combat.gd", "old_string": "mot de passe"}, ident="m2")
                + self.ligne_outil("Bash", {"command": "cd x && python -m pytest tests/secret.py"}, ident="m3",
                                   usage={"input_tokens": 7, "output_tokens": 3, "cache_read_input_tokens": 2}))
        r = e.resumer_flux(flux.encode("utf-8"), JETON, "/travail/projet")
        self.assertEqual([a["texte"] for a in r["actions"]], ["lance python", "modifie scenes/combat.gd", "lit a.py"])
        self.assertEqual(r["actions"][2]["t"], "2026-11-26T10:00:00Z")
        self.assertIsNone(r["actions"][0]["t"])
        self.assertEqual((r["v"], r["phase"]), (1, "tests"))
        self.assertEqual(r["usage"], [{"modele": "claude-opus-5-5", "entree": 27, "sortie": 13, "cache_lecture": 2, "cache_ecriture": 0}])
        self.assertNotIn("mot de passe", json.dumps(r))
        self.assertNotIn("secret.py", json.dumps(r))

    def test_resumer_flux_borne_les_actions_et_tolere_le_bruit(self):
        e = charger_entree()
        flux = "pas du json\n" + "".join(self.ligne_outil("Read", {"file_path": f"f{i}.py"}, ident=f"m{i}") for i in range(80))
        flux += '{"type": "assistant", "message": 3}\n[1, 2]\n{"type": "assistant", "message": {"cont'      # ligne coupée
        r = e.resumer_flux(flux.encode("utf-8"), JETON, None)
        self.assertEqual(len(r["actions"]), 50)
        self.assertEqual(r["actions"][0]["texte"], "lit f79.py")
        self.assertEqual(e.resumer_flux(b"", JETON, None)["actions"], [])
        self.assertIsNone(e.resumer_flux(b"", JETON, None)["phase"])

    def test_resumer_flux_ne_publie_jamais_le_jeton(self):
        import base64
        e = charger_entree()
        b64 = [base64.b64encode(b"A" * k + JETON.encode()).decode() for k in range(3)]
        sources = [JETON, *(x[4:-4] for x in b64)]
        flux = "".join(self.ligne_outil("Read", {"file_path": f"/travail/projet/{t}.txt"}, ident=f"m{i}")
                       for i, t in enumerate(sources))
        flux += self.ligne_outil("Read", {"file_path": "ok.txt"}, ident="mok")
        r = e.resumer_flux(flux.encode("utf-8"), JETON, "/travail/projet")
        self.assertEqual([a["texte"] for a in r["actions"]], ["lit ok.txt"])
        for t in sources:
            self.assertNotIn(t[:20], json.dumps(r))

    def test_lire_avancement_agent_borne_et_valide(self):
        e = charger_entree()
        maison = self.racine / "maison"
        chemin = maison / "avancement.json"
        chemin.write_text(json.dumps({"points": [{"texte": "a" * 300, "fait": True}, {"texte": "b", "fait": 1}, {"texte": 3}, "x"],
                                      "en_cours": "c" * 300}), encoding="utf-8")
        a = e.lire_avancement_agent(maison.as_posix())
        self.assertEqual([p["texte"] for p in a["points"]], ["a" * 160, "b"])
        self.assertEqual([p["fait"] for p in a["points"]], [True, False])
        self.assertEqual(a["en_cours"], "c" * 160)
        chemin.write_text(json.dumps({"points": [{"texte": str(i), "fait": False} for i in range(100)]}), encoding="utf-8")
        self.assertEqual(len(e.lire_avancement_agent(maison.as_posix())["points"]), 30)
        chemin.write_text("x" * 70000, encoding="utf-8")
        self.assertIsNone(e.lire_avancement_agent(maison.as_posix()))
        chemin.write_text('{"points": "pas une liste"}', encoding="utf-8")
        self.assertIsNone(e.lire_avancement_agent(maison.as_posix()))
        chemin.unlink()
        self.assertIsNone(e.lire_avancement_agent(maison.as_posix()))

    @unittest.skipUnless(hasattr(os, "pread"), "POSIX seulement")
    def test_direct_json_est_publie_pendant_l_execution_puis_retire(self):
        flux = [json.loads(self.ligne_outil("Edit", {"file_path": "/travail/projet/a.py"}))]
        self.ecrire(ARGV, {"flux": flux, "attendre_direct": True})
        (self.racine / "maison" / "avancement.json").write_text(json.dumps({"points": [{"texte": "un", "fait": False}]}), encoding="utf-8")
        r = self.lancer(AGENT_DIRECT_S="0.1")
        self.assertEqual(r.returncode, 0, r.stderr)
        vu = json.loads((self.racine / "maison" / "direct-vu.json").read_text(encoding="utf-8"))
        self.assertFalse(vu["lien"])
        direct = json.loads(vu["texte"])
        self.assertEqual(direct["actions"][0]["texte"], "modifie a.py")
        self.assertEqual(direct["avancement"]["points"], [{"texte": "un", "fait": False}])
        self.assertFalse(self.sortie("direct.json").exists())              # retiré à la fin
        self.assertFalse(self.sortie("direct.json.tmp").exists())
        self.assertIn("flux.jsonl", os.listdir(self.racine / "sortie"))    # le flux brut reste rapatrié à la fin

    @unittest.skipUnless(hasattr(os, "pread"), "POSIX seulement")
    def test_direct_json_remplace_un_lien_que_l_agent_a_pose(self):
        (self.racine / "maison" / "secret.txt").write_text("secret\n", encoding="utf-8")
        self.ecrire(ARGV, {"flux": [], "attendre_direct": True, "lien_direct": True})
        r = self.lancer(AGENT_DIRECT_S="0.1")
        self.assertEqual(r.returncode, 0, r.stderr)
        vu = json.loads((self.racine / "maison" / "direct-vu.json").read_text(encoding="utf-8"))
        self.assertFalse(vu["lien"])                 # le lien a été remplacé, jamais suivi
        self.assertNotIn("secret", vu["texte"])
        self.assertEqual((self.racine / "maison" / "secret.txt").read_text(encoding="utf-8"), "secret\n")

    def banc_direct(self):
        e = charger_entree()
        c = {"maison": (self.racine / "maison").as_posix(), "sortie": (self.racine / "sortie").as_posix()}
        return e, c, e.Borne(os.path.join(c["sortie"], "flux.jsonl"), 1 << 20)

    def direct_publie(self):
        chemin = self.racine / "sortie" / "direct.json"
        return json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else None

    @unittest.skipUnless(hasattr(os, "pread"), "POSIX seulement")
    def test_publier_direct_ne_publie_jamais_le_jeton_dans_l_avancement(self):
        import base64
        e, c, flux = self.banc_direct()
        flux.ecrire(self.ligne_outil("Read", {"file_path": "a.py"}))
        b64 = base64.b64encode(JETON.encode()).decode()[4:-4]
        (self.racine / "maison" / "avancement.json").write_text(json.dumps(
            {"points": [{"texte": "ok", "fait": False}, {"texte": "voici " + JETON, "fait": True},
                        {"texte": "b64 " + b64, "fait": False}], "en_cours": JETON}), encoding="utf-8")
        e.publier_direct(c, flux, JETON, None)
        brut = (self.racine / "sortie" / "direct.json").read_text(encoding="utf-8")
        self.assertNotIn(JETON, brut)
        self.assertNotIn(b64, brut)
        d = json.loads(brut)
        self.assertEqual([p["texte"] for p in d["avancement"]["points"]], ["ok"])
        self.assertIsNone(d["avancement"]["en_cours"])
        self.assertEqual(d["actions"][0]["texte"], "lit a.py")

    @unittest.skipUnless(hasattr(os, "pread"), "POSIX seulement")
    def test_publier_direct_refuse_tout_si_le_jeton_reste_quelque_part(self):
        e, c, flux = self.banc_direct()
        flux.ecrire(self.ligne_outil("Read", {"file_path": "a.py"}, modele="claude-" + JETON))
        e.publier_direct(c, flux, JETON, None)
        self.assertIsNone(self.direct_publie())             # rien n'est publié plutôt qu'un fichier qui porte le jeton

    def test_le_usage_est_cumule_au_dela_de_la_fenetre_relue(self):
        e = charger_entree()
        cumul = {}
        a = self.ligne_outil("Read", {"file_path": "a"}, ident="m1", usage={"input_tokens": 10, "output_tokens": 1})
        b = self.ligne_outil("Read", {"file_path": "b"}, ident="m2", usage={"input_tokens": 20, "output_tokens": 2})
        e.resumer_flux(a.encode(), JETON, None, cumul)
        r = e.resumer_flux(b.encode(), JETON, None, cumul)          # `a` n'est plus dans la fenêtre relue
        self.assertEqual((r["usage"][0]["entree"], r["usage"][0]["sortie"]), (30, 3))
        c = self.ligne_outil("Read", {"file_path": "b"}, ident="m2", usage={"input_tokens": 25, "output_tokens": 2})
        r = e.resumer_flux(c.encode(), JETON, None, cumul)          # `m2` relu avec une valeur plus récente : jamais compté deux fois
        self.assertEqual(r["usage"][0]["entree"], 35)

    @unittest.skipUnless(hasattr(os, "pread"), "POSIX seulement")
    def test_publier_direct_dit_l_age_du_dernier_octet_du_flux(self):
        import time
        e, c, flux = self.banc_direct()
        flux.ecrire(self.ligne_outil("Read", {"file_path": "a.py"}))
        time.sleep(0.4)
        e.publier_direct(c, flux, JETON, None)
        age = self.direct_publie()["flux_age_s"]
        self.assertTrue(0.3 <= age < 5, age)
        flux.ecrire(self.ligne_outil("Read", {"file_path": "b.py"}))
        e.publier_direct(c, flux, JETON, None)
        self.assertLess(self.direct_publie()["flux_age_s"], 0.3)

    def test_drapeaux_liste_fermee(self):
        self.assertNotIn(b"\r", ENTREE.read_bytes())             # #!/usr/bin/env python3 : un \r casserait l'entrée
        self.assertTrue(ENTREE.read_bytes().startswith(b"#!/usr/bin/env python3\n"))
        e = charger_entree()
        self.assertEqual(set(e.DRAPEAUX), {"-p", "--output-format", "--verbose", "--model", "--tools", "--allowedTools",
                                           "--permission-prompts", "--append-system-prompt-file", "--system-prompt-file",
                                           "--strict-mcp-config", "--setting-sources", "--disable-slash-commands", "--resume",
                                           "--no-session-persistence"})
        self.assertEqual(e.valider_argv(ARGV), ARGV[1:])
        sans_outils = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--model", "claude-haiku-5-5", "--tools", "",
                       "--system-prompt-file", "/entree/consigne.md", "--strict-mcp-config", "--setting-sources", "",
                       "--disable-slash-commands", "--no-session-persistence"]
        self.assertEqual(e.valider_argv(sans_outils), sans_outils[1:])
        reprise = ARGV + ["--resume", "0f8fad5b-d9cb-469f-a165-70867728950e"]
        self.assertEqual(e.valider_argv(reprise), reprise[1:])

    def test_entree_refuse_un_drapeau_hors_liste(self):
        e = charger_entree()
        hostiles = [ARGV + ["--dangerously-skip-permissions"], ARGV + ["--permission-mode", "bypassPermissions"],
                    ARGV + ["--max-turns", "9999"], ARGV + ["texte-libre"], ARGV + ["-p"],
                    ["/bin/sh"] + ARGV[1:], ARGV[:-1] + ["--disable-slash-commands=1"],
                    [x if x != "/entree/consigne.md" else "/run/identifiants/jeton" for x in ARGV],
                    [x if x != "claude-opus-5-5" else "claude-opus-5-5;id" for x in ARGV],
                    ARGV + ["--resume", "../../etc"], ARGV + ["--add-dir", "/run"], ARGV + ["--mcp-config", "{}"],
                    [x if x != "Bash(git status:*),Read,Edit" else "--dangerously-skip-permissions" for x in ARGV],
                    ARGV[:3] + ["json"] + ARGV[4:], ARGV[:-3] + ["--setting-sources", "user", ARGV[-1]],
                    "pas une liste", [ARGV[0], 5], ["claude"]]
        for argv in hostiles:
            with self.subTest(argv=argv), self.assertRaises(e.Refus):
                e.valider_argv(argv)
        self.ecrire(ARGV + ["--dangerously-skip-permissions"], {})
        self.lancer()
        self.assertIsNone(self.vu())                               # claude n'a jamais été lancé
        self.assertNotEqual(self.fin()["code"], 0)
        self.assertIn(b"--dangerously-skip-permissions", self.sortie("claude.err").read_bytes())
        self.assertFalse(self.sortie("resultat.bundle").exists())

    def test_entree_ajoute_max_turns(self):
        r = self.lancer()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.vu()["argv"], ARGV[1:] + ["--max-turns", "200"])
        self.ecrire(ARGV, {}, limites={**demande()["limites"], "tours": 37})
        effacer(self.depot)
        self.lancer()
        self.assertEqual(self.vu()["argv"][-2:], ["--max-turns", "37"])
        for tours in (201, 0, "37", True):                         # jamais au-dessus du défaut, jamais autre chose qu'un entier
            with self.subTest(tours=tours):
                effacer(self.depot)
                (self.racine / "maison" / "vu.json").unlink(missing_ok=True)
                self.ecrire(ARGV, {}, limites={**demande()["limites"], "tours": tours})
                self.lancer()
                self.assertIsNone(self.vu())
                self.assertNotEqual(self.fin()["code"], 0)

    def test_entree_clone_branche_et_cree_agent_tache(self):
        r = self.lancer()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(Path(self.vu()["cwd"]).resolve(), self.depot.resolve())
        self.assertEqual(git(self.depot, "symbolic-ref", "HEAD"), "refs/heads/agent/corriger-le-titre")
        self.assertEqual(git(self.depot, "rev-parse", "HEAD"), self.base)
        self.assertEqual(git(self.depot, "config", "user.name"), "Agent serveur MyIAFactory")
        self.assertEqual(git(self.depot, "config", "user.email"), "agent@myiafactory.invalid")
        self.assertEqual(Path(self.vu()["env"]["HOME"]).resolve(), (self.racine / "maison").resolve())
        # reprise : le dépôt gardé est réutilisé tel quel, jamais recloné
        (self.depot / "garde.txt").write_text("gardé\n", newline="\n")
        self.ecrire(ARGV, {}, reprend=PREC)
        self.lancer()
        self.assertEqual(git(self.depot, "log", "-1", "--format=%s"), "Agent : travail non commité à la fin")
        self.assertIn("garde.txt", git(self.depot, "show", "--name-only", "--format=", "HEAD"))
        effacer(self.depot)                                  # reprise sans dépôt gardé : refusée, claude non lancé
        (self.racine / "maison" / "vu.json").unlink()
        self.lancer()
        self.assertIsNone(self.vu())
        self.assertNotEqual(self.fin()["code"], 0)

    def test_entree_commit_des_restes_et_paquet(self):
        self.ecrire(ARGV, {"fichiers": {"titre.txt": "Nouveau titre\n"}, "commit": "Titre corrigé",
                           "apres": {"note.txt": "pas commité\n"},
                           "flux": [{"type": "result", "subtype": "success", "result": "fait", "session_id": "s1"}]})
        r = self.lancer()
        self.assertEqual(r.returncode, 0, r.stderr)
        fin = self.fin()
        self.assertEqual(fin, {"code": 0, "commits": 2, "branche": "agent/corriger-le-titre", "base": self.base})
        self.assertEqual(git(self.depot, "log", "-1", "--format=%s|%an|%ae"),
                         "Agent : travail non commité à la fin|Agent serveur MyIAFactory|agent@myiafactory.invalid")
        paquet = self.sortie("resultat.bundle")
        self.assertTrue(paquet.is_file())
        tetes = git(self.depot, "bundle", "list-heads", paquet.as_posix()).splitlines()
        self.assertEqual([x.split()[1] for x in tetes], ["refs/heads/agent/corriger-le-titre"])
        self.assertIn(self.base, git(self.depot, "bundle", "verify", paquet.as_posix()) +
                      subprocess.run(["git", "-C", str(self.depot), "bundle", "verify", paquet.as_posix()], capture_output=True,
                                     text=True).stderr)
        self.assertIn(b'"result": "fait"', self.sortie("flux.jsonl").read_bytes())

    def test_entree_sans_commit_pas_de_paquet(self):
        self.ecrire(ARGV, {"code": 0})
        self.lancer()
        self.assertEqual(self.fin(), {"code": 0, "commits": 0, "branche": None, "base": self.base})
        self.assertFalse(self.sortie("resultat.bundle").exists())
        self.ecrire(ARGV, {"code": 3, "err": "échec du faux claude"})
        effacer(self.depot)
        self.lancer()
        self.assertEqual(self.fin()["code"], 3)
        self.assertIn("échec du faux claude".encode("utf-8"), self.sortie("claude.err").read_bytes())

    def test_flux_coupe_a_20_mo(self):
        e = charger_entree()
        self.assertEqual(e.LIMITE_FLUX, 20 * 1024 * 1024)
        self.assertEqual(e.LIMITE_ERREURS, 64 * 1024)
        self.ecrire(ARGV, {"bavard": True}, limites={**demande()["limites"], "flux_octets": 5000})
        debut = time.time()
        r = self.lancer()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(time.time() - debut, 60)
        self.assertEqual(self.sortie("flux.jsonl").stat().st_size, 5000)
        self.assertNotEqual(self.fin()["code"], 0)
        self.assertIn("coup".encode("utf-8"), self.sortie("claude.err").read_bytes())
        effacer(self.depot)                                  # au-dessus de 20 Mo : refusé
        (self.racine / "maison" / "vu.json").unlink()
        self.ecrire(ARGV, {}, limites={**demande()["limites"], "flux_octets": 20 * 1024 * 1024 + 1})
        self.lancer()
        self.assertIsNone(self.vu())
        self.ecrire(ARGV, {"err": "e" * 200000, "code": 1})       # erreurs bornées à 64 Ko
        self.lancer()
        self.assertLessEqual(self.sortie("claude.err").stat().st_size, 64 * 1024)

    def test_jeton_ni_sur_la_ligne_de_commande_ni_dans_fin_json(self):
        self.ecrire(ARGV, {"fichiers": {"a.txt": "a\n"}, "commit": "A", "flux": [{"type": "result", "result": "ok"}]})
        r = self.lancer()
        self.assertEqual(r.returncode, 0, r.stderr)
        vu = self.vu()
        self.assertEqual(vu["env"]["CLAUDE_CODE_OAUTH_TOKEN"], JETON)  # pour ce seul processus
        self.assertNotIn(JETON, json.dumps(vu["argv"]))
        self.assertNotIn(JETON, json.dumps({k: v for k, v in vu["env"].items() if k != "CLAUDE_CODE_OAUTH_TOKEN"}))
        for nom in ("fin.json", "claude.err", "flux.jsonl"):
            if self.sortie(nom).exists():
                self.assertNotIn(JETON.encode(), self.sortie(nom).read_bytes(), nom)
        self.assertNotIn(JETON.encode(), r.stdout + r.stderr)
        self.assertNotIn(JETON, git(self.depot, "log", "-p", "--all"))
        self.assertNotIn(JETON, (self.depot / ".git" / "config").read_text(encoding="utf-8"))
        # jeton absent ou mal formé : claude n'est pas lancé, rien du fichier n'est répété
        effacer(self.depot)
        (self.racine / "maison" / "vu.json").unlink()
        (self.racine / "run" / "identifiants" / "jeton").write_text("court;" + JETON[6:30], newline="\n")
        self.lancer()
        self.assertIsNone(self.vu())
        self.assertNotIn(JETON[6:30].encode(), self.sortie("claude.err").read_bytes())

    def test_verifier_montre_le_secret_d_un_commit(self):
        # un commit qui cache le jeton : fichier marqué binaire (.gitattributes) et message ; --verifier le montre en clair
        self.ecrire(ARGV, {"fichiers": {".gitattributes": "* -diff\n", "cle.bin": "cle=" + JETON + "\n"}, "commit": "Clé"})
        self.lancer()
        (self.racine / "run" / "identifiants" / "jeton").unlink()      # le conteneur de contrôle n'a pas de jeton
        r = self.lancer("--verifier")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(JETON.encode(), r.stdout)
        # sans commit ni paquet : rien à montrer, code 0
        (self.racine / "run" / "identifiants" / "jeton").write_text(JETON + "\n", newline="\n")
        effacer(self.depot)
        self.sortie("resultat.bundle").unlink()
        self.ecrire(ARGV, {})
        self.lancer()
        r = self.lancer("--verifier")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(JETON.encode(), r.stdout)
        # un paquet abîmé : contrôle impossible (code non nul), jamais « propre »
        self.sortie("resultat.bundle").write_bytes(b"# v2 git bundle\nabime\n")
        self.assertNotEqual(self.lancer("--verifier").returncode, 0)

    def test_verifier_ferme_sur_un_paquet_sans_depot(self):
        # paquet mince (prérequis : la base) et dépôt effacé : invérifiable, donc jamais « propre »
        self.ecrire(ARGV, {"fichiers": {"a.txt": "a\n"}, "commit": "A"})
        self.lancer()
        self.assertTrue(self.sortie("resultat.bundle").exists())
        effacer(self.depot)
        self.assertEqual(self.lancer("--verifier").returncode, 3)

    def test_entree_nettoie_la_sortie_de_l_agent(self):
        # l'agent efface son dépôt et dépose un paquet, un fin.json et un autre fichier : il ne reste que nos sorties
        self.ecrire(ARGV, {"effacer_depot": True, "planter": {"resultat.bundle": "faux paquet", "autre.txt": "x",
                                                            "fin.json": '{"code": 0, "commits": 9}'}})
        r = self.lancer()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(p.name for p in (self.racine / "sortie").iterdir()), ["claude.err", "fin.json", "flux.jsonl"])
        self.assertEqual((self.fin()["commits"], self.fin()["branche"]), (0, None))
        # dépôt gardé : notre paquet reste, ce que l'agent a déposé à côté part
        effacer(self.depot)
        self.ecrire(ARGV, {"fichiers": {"a.txt": "a\n"}, "commit": "A", "planter": {"autre.txt": "x", "sous.bundle": "y"}})
        self.lancer()
        self.assertEqual(sorted(p.name for p in (self.racine / "sortie").iterdir()),
                         ["claude.err", "fin.json", "flux.jsonl", "resultat.bundle"])
        self.assertEqual(self.fin()["commits"], 1)

    def test_flux_et_erreurs_jamais_forges_par_l_agent(self):
        """L'agent écrit son propre flux.jsonl et claude.err dans /sortie : seuls les octets que l'entrée a reçus de
        claude (descripteurs sans nom, recopiés à la fin) sont rendus."""
        vrai = {"type": "result", "subtype": "success", "result": "vrai", "session_id": "s1"}
        faux = '{"type": "result", "subtype": "success", "result": "forgé"}\n'
        self.ecrire(ARGV, {"flux": [vrai], "err": "vraie erreur", "code": 0,
                           "planter": {"flux.jsonl": faux, "claude.err": "fausse erreur"}})
        r = self.lancer()
        self.assertEqual(r.returncode, 0, r.stderr)
        flux = self.sortie("flux.jsonl").read_bytes()
        self.assertIn(b'"result": "vrai"', flux)
        self.assertNotIn("forgé".encode("utf-8"), flux)
        erreurs = self.sortie("claude.err").read_bytes()
        self.assertIn(b"vraie erreur", erreurs)
        self.assertNotIn(b"fausse erreur", erreurs)
        self.assertEqual(sorted(p.name for p in (self.racine / "sortie").iterdir()), ["claude.err", "fin.json", "flux.jsonl"])

    def test_sorties_sans_nom_et_vidage_interdit(self):
        e = charger_entree()
        dossier = self.racine / "sortie"
        b = e.Borne((dossier / "flux.jsonl").as_posix(), 10)
        b.ecrire(b"0123456789abc")
        self.assertTrue(b.coupe)
        self.assertFalse((dossier / "flux.jsonl").exists())          # rien sous le nom avant la publication
        (dossier / "flux.jsonl").write_bytes(b"forge")
        b.publier()
        b.fermer()
        self.assertEqual((dossier / "flux.jsonl").read_bytes(), b"0123456789")
        self.assertEqual([p.name for p in dossier.iterdir()], ["flux.jsonl"])
        fait = e.interdire_le_vidage()                               # Linux : prctl ; ailleurs ignoré, jamais d'exception
        self.assertIs(fait, sys.platform.startswith("linux"))

    def test_entree_echeance_interne_garde_les_commits(self):
        e = charger_entree()
        self.assertEqual(e.MARGE_ECHEANCE_S, 120)
        self.assertEqual(e.echeance_interne(2400), 2280)       # 120 s avant le veilleur
        self.assertEqual(e.echeance_interne(4), 2)             # tâche très courte : à mi-chemin
        self.ecrire(ARGV, {"fichiers": {"a.txt": "a\n"}, "commit": "A", "dormir": True},
                    limites={**demande()["limites"], "duree_s": 4})
        debut = time.time()
        r = self.lancer()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(time.time() - debut, 30)
        fin = self.fin()
        self.assertEqual((fin["commits"], fin["branche"], fin.get("echeance")), (1, "agent/corriger-le-titre", True))
        self.assertNotEqual(fin["code"], 0)
        self.assertTrue(self.sortie("resultat.bundle").is_file())

    def test_conclure_ne_lance_rien_du_depot_de_l_agent(self):
        # l'agent piège son dépôt (filtre clean par .gitattributes et info/attributes, signature gpg, fsmonitor) puis laisse
        # du travail non commité : la conclusion le commite brut, sans rien lancer, et rend son info/attributes
        marqueur = (self.t / "marqueur.txt").as_posix()
        piege = f'echo lance >> "{marqueur}"; cat'
        self.ecrire(ARGV, {"fichiers": {"a.txt": "a\n"}, "commit": "A",
                           "apres": {"note.txt": "brut\n", ".gitattributes": "* filter=piege\n",
                                     ".git/info/attributes": "* filter=piege\n"},
                           "configurer": [["filter.piege.clean", piege], ["filter.piege.required", "true"],
                                          ["commit.gpgsign", "true"], ["gpg.program", piege], ["core.fsmonitor", piege],
                                          ["gc.auto", "1"]]})
        r = self.lancer()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(marqueur), self.sortie("claude.err").read_bytes())
        fin = self.fin()
        self.assertEqual((fin["code"], fin["commits"], fin["branche"]), (0, 2, "agent/corriger-le-titre"),
                         self.sortie("claude.err").read_bytes())
        self.assertEqual(git(self.depot, "log", "-1", "--format=%s"), "Agent : travail non commité à la fin")
        self.assertEqual(git(self.depot, "show", "HEAD:note.txt"), "brut")
        self.assertEqual((self.depot / ".git" / "info" / "attributes").read_text(encoding="utf-8"), "* filter=piege\n")
        self.assertTrue(self.sortie("resultat.bundle").is_file())
        # échéance globale de la conclusion : au-delà, rien de plus n'est lancé
        e = charger_entree()
        self.assertLess(e.DELAI_CONCLURE_S, e.MARGE_ECHEANCE_S)
        d = e.valider_demande({**demande(), "base": self.base})
        erreurs = e.Borne((self.t / "err.txt").as_posix(), 4096)
        try:
            with self.assertRaises(subprocess.TimeoutExpired):
                e.conclure(self.depot.as_posix(), d, e.env_git(self.t.as_posix()), (self.racine / "sortie").as_posix(),
                           erreurs, delai=0)
        finally:
            erreurs.fermer()

    def test_duree_de_l_enveloppe_fait_foi(self):
        # demande.json annonce 2400 s, l'enveloppe en passe 4 (AGENT_DUREE_S) : l'échéance interne suit l'enveloppe
        self.ecrire(ARGV, {"fichiers": {"a.txt": "a\n"}, "commit": "A", "dormir": True})
        debut = time.time()
        r = self.lancer(AGENT_DUREE_S="4")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(time.time() - debut, 30)
        self.assertEqual((self.fin()["commits"], self.fin().get("echeance")), (1, True))
        for mauvais in ("0", "086400", "86401", "4s"):          # posée mais hors motif : claude n'est pas lancé
            with self.subTest(mauvais=mauvais):
                effacer(self.depot)
                (self.racine / "maison" / "vu.json").unlink(missing_ok=True)
                self.lancer(AGENT_DUREE_S=mauvais)
                self.assertIsNone(self.vu())
                self.assertNotEqual(self.fin()["code"], 0)
                self.assertIn(b"AGENT_DUREE_S", self.sortie("claude.err").read_bytes())

    def test_signal_ne_tue_que_claude_et_l_entree_conclut(self):
        code = ENTREE.read_text(encoding="utf-8")
        self.assertNotIn("os._exit", code)
        self.assertNotIn("SIG_IGN", code)
        self.assertRegex(code, r"signal\.signal\(signal\.SIGTERM, signal_recu\)")
        self.assertRegex(code, r"signal\.signal\(signal\.SIGINT, signal_recu\)")
        self.assertIn("non fiables", code)                        # fin.json et le paquet restent à vérifier par le poste
        if os.name != "posix":
            self.skipTest("signal POSIX : vérifié sur le serveur (Linux)")
        import signal as sig
        self.ecrire(ARGV, {"fichiers": {"a.txt": "a\n"}, "commit": "A", "dormir": True})
        env = {k: v for k, v in os.environ.items() if k not in ("AGENT_RACINE", "AGENT_CLAUDE")}
        env.update(AGENT_RACINE=self.racine.as_posix(), AGENT_CLAUDE=json.dumps([sys.executable, self.faux.as_posix()]))
        p = subprocess.Popen([sys.executable, ENTREE.as_posix()], env=env, stdin=subprocess.DEVNULL)
        for _ in range(200):
            if self.vu() and self.depot.exists() and "A" in git(self.depot, "log", "-1", "--format=%s"):
                break
            time.sleep(0.1)
        time.sleep(0.5)
        p.send_signal(sig.SIGTERM)
        self.assertEqual(p.wait(timeout=60), 0)
        self.assertEqual(self.fin()["commits"], 1)
        self.assertTrue(self.sortie("resultat.bundle").is_file())

    def test_allowedtools_par_la_grammaire_des_regles(self):
        e = charger_entree()
        bons = ["Read", "Bash(git status:*),Read,Edit", "Bash(npm run test:*) Read", "WebFetch(domain:exemple.org)",
                ",".join(["Read"] * 64)]
        mauvais = ["Bash(a)(b)", "Bash((x))", ",Read", "Read,,Edit", "Read;Edit", ",".join(["Read"] * 65), "Read,", "(x)",
                   "Bash(a\nb)", "Read Edit ", "1Read"]
        for v in bons:
            with self.subTest(bon=v):
                e.valider_argv(ARGV[:10] + [v] + ARGV[11:])
        for v in mauvais:
            with self.subTest(mauvais=v), self.assertRaises(e.Refus):
                e.valider_argv(ARGV[:10] + [v] + ARGV[11:])


if __name__ == "__main__":
    unittest.main()
