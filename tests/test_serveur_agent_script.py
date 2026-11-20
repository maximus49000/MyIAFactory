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
         [ -n "${FAUX_VERIF:-}" ] && cat "$FAUX_VERIF"
         exit "${FAUX_VERIF_CODE:-0}" ;;
    esac ;;
  inspect)
    [ -e "$ET/mort" ] && rm -f "$ET/vivant"
    if [ -e "$ET/vivant" ]; then echo "true 999999"; exit 0; fi
    echo "Error: No such object: tache-x" >&2; exit 1 ;;
  stop|kill|rm) rm -f "$ET/vivant" ;;
esac
exit 0'''
FAUX = {
    "sudo": '[ "$1" = -n ] && shift\nexec "$@"',
    "docker": DOCKER,
    "flock": 'echo "flock $*" >> "$FAUX_JOURNAL"\n'
             'if [ "$1" = -n ]; then\n'
             '  n=$(cat "$FAUX_ETAT/flock" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAUX_ETAT/flock"\n'
             '  [ -n "${FAUX_FLOCK_OCCUPES:-}" ] && [ "$n" -le "$FAUX_FLOCK_OCCUPES" ] && exit 1\n'
             'fi\nexit 0',
    "setsid": 'echo "setsid $*" >> "$FAUX_JOURNAL"\nexec "$@"',
    "timeout": 'echo "timeout $*" >> "$FAUX_JOURNAL"\nshift\nexec "$@"',
    "git": 'echo "git $*" >> "$FAUX_JOURNAL"\nexit 0',
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
    """HOME jetable avec ~/taches/<ID>/entree prête et le jeton factice ; le script lancé est celui du dépôt, ou une copie
    (avec un faux pont_hote.py) quand `pont` est vrai."""

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
            for f in (SCRIPT, COMMUN):
                shutil.copy(f, copie / f.name)
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
            if self.appels("flock -u") and (self.dossier / "etat.json").exists() and \
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


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEnveloppeAgent(unittest.TestCase):
    def test_agent_prend_le_premier_creneau_libre(self):
        with Banc(FAUX_FLOCK_OCCUPES="1") as b:
            r = b.lancer("seul", "30", "2048", "2", "3")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])["etat"], "en_cours")
            self.assertEqual((b.dossier / "creneau").read_text().strip(), "2")
            self.assertEqual(len(b.appels("flock -n 8")), 2, b.journal)
            noms = sorted(p.name for p in (b.home / "taches").glob(".creneau-agent-*"))
            self.assertEqual(noms, [".creneau-agent-1", ".creneau-agent-2"])
            b.arreter()
            self.assertEqual(b.attendre_final()["etat"], "arretee")

    def test_agent_places_pleines_donne_75_et_en_attente(self):
        with Banc(FAUX_FLOCK_OCCUPES="2") as b:
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 75, r.stderr + r.stdout)
            e = b.etat()
            self.assertEqual((e["etat"], e["statut"]), ("en_attente", None))
            self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])["etat"], "en_attente")
            self.assertEqual(len(b.appels("flock -n 8")), 2, b.journal)
            self.assertEqual(b.appels("docker"), [])
            self.assertEqual(b.appels("setsid"), [])

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
            self.assertEqual([a[i + 1] for i in range(len(a) - 1) if a[i] == "-e"], ["HOME=/maison"])
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
        with Banc() as b:                                          # pont_hote.py absent du dépôt (tâche 7) : refusé
            avant = sorted(p.name for p in b.dossier.iterdir())
            r = b.lancer("pilote", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 2, r.stderr + r.stdout)
            self.assertIn("pont", r.stderr)
            self.assertEqual(sorted(p.name for p in b.dossier.iterdir()), avant)
            self.assertEqual(b.journal, "")
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

    def test_reprise_copie_sans_suivre_les_liens(self):
        with Banc() as b:
            prec = b.home / "taches" / PREC
            (prec / "travail" / "projet").mkdir(parents=True)
            (prec / "maison" / ".claude").mkdir(parents=True)
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

    def test_arret_coupe_agent_pont_et_emulation(self):
        with Banc(pont=True) as b:
            (b.entree / "app.apk").write_bytes(b"PK")
            (b.home / "taches" / EMU).mkdir(parents=True)
            self.assertEqual(b.lancer("pilote", "30", "2048", "2", "2", EMU).returncode, 0)
            self.assertTrue((b.dossier / "pont-hote.pid").exists())
            b.arreter()
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("arretee", "ok"))
            self.assertTrue(any(x.startswith("docker stop") and f"tache-{ID}" in x for x in b.journal.splitlines()), b.journal)
            self.assertTrue(b.appels("pont-arrete"), b.journal)
            self.assertEqual((b.home / "taches" / EMU / "arret").read_text().strip(), "fin")
            j = b.journal
            self.assertLess(j.index("docker stop"), j.index("flock -u"))
            self.assertLess(j.index("pont-arrete"), j.index("flock -u"))

    def test_echeance_donne_limite(self):
        with Banc() as b:
            self.assertEqual(b.lancer("seul", "1", "2048", "2", "2").returncode, 0)
            f = b.attendre_final()
            self.assertEqual((f["etat"], f["statut"]), ("terminee", "limite"))
            self.assertIn("durée", f["raison"].lower())
            self.assertTrue(b.appels("docker stop"), b.journal)

    def test_entrees_et_jeton_exiges(self):
        for manquant in ("projet.bundle", "argv.json", "consigne.md", "message.md", "demande.json"):
            with self.subTest(manquant=manquant), Banc() as b:
                (b.entree / manquant).unlink()
                r = b.lancer()
                self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
                self.assertEqual((b.etat()["etat"], b.etat()["statut"]), ("echouee", "erreur"))
                self.assertIn(manquant, b.etat()["raison"])
                self.assertEqual(b.appels("docker run"), [])
                self.assertTrue(b.appels("flock -u"))
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
            self.assertTrue(b.appels("flock -u"))

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
for ligne in cmd.get("flux", []):
    sys.stdout.write(json.dumps(ligne) + "\n")
sys.stdout.flush()
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
    spec.loader.exec_module(module)
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
        self.faux.write_text(FAUX_CLAUDE, newline="\n")
        self.ecrire(ARGV, {})

    def ecrire(self, argv, message, **d):
        dem = {**demande(), "base": self.base, **d}
        (self.racine / "entree" / "demande.json").write_text(json.dumps(dem), newline="\n")
        (self.racine / "entree" / "argv.json").write_text(json.dumps(argv), newline="\n")
        (self.racine / "entree" / "message.md").write_text(json.dumps(message), newline="\n")

    def lancer(self, *args):
        env = {k: v for k, v in os.environ.items() if k not in ("AGENT_RACINE", "AGENT_CLAUDE")}
        env.update(AGENT_RACINE=self.racine.as_posix(), AGENT_CLAUDE=json.dumps([sys.executable, self.faux.as_posix()]))
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


if __name__ == "__main__":
    unittest.main()
