"""Demande d'agent et paquets Git (`outils/serveur_agent.py`). Faux SSH en mémoire, vrais dépôts Git jetables ; jamais le
vrai ~/MyIAFactory ni un vrai serveur."""
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import serveur_agent as sa  # noqa: E402
import serveur_tache as st  # noqa: E402

CLE_PRIVEE = "C:/cles-privees/id_ed25519_ovh1_SECRET-CHEMIN"
ID1 = "t20261120-101500-aaaa"
PAQUET = b"# v2 git bundle\n" + bytes(range(256)) + b"\r\n\n\r\x00" * 20
APK = b"PK\x03\x04" + bytes(range(256)) + b"\r\n\n\r\x00" * 10
BASE = "a" * 40
CAPS_AGENT = {"agent": "presente", "agent-abonnement": "fait"}
ARGV = ["claude", "-p", "--output-format", "stream-json"]


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git(cwd, *args, entree=None):
    """Sortie standard (octets) d'un git réel ; échec -> exception."""
    r = subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@exemple.net", "-c", "commit.gpgsign=false",
                        *args], cwd=str(cwd), input=entree, capture_output=True, check=True)
    return r.stdout


def declarer(dossier, serveurs=None):
    serveurs = serveurs or [("ovh1", CAPS_AGENT)]
    (Path(dossier) / "serveurs.json").write_text(json.dumps(
        [{"id": sid, "nom": sid, "hote": f"{sid}.exemple.net", "utilisateur": "ubuntu", "cle": CLE_PRIVEE + sid}
         for sid, _c in serveurs]), encoding="utf-8")
    (Path(dossier) / "serveurs-etat.json").write_text(json.dumps(
        {sid: {"capacites": {k: {"statut": v} for k, v in c.items()}, "installation": {"en_cours": False}}
         for sid, c in serveurs}), encoding="utf-8")


def brut(**plus):
    return {"projet": "demo", "tache": "ajout-bouton", "mode": "seul", "modele": "sonnet", "branche": "main",
            "base": BASE, **plus}


class FauxServeur:
    """Serveur factice : reconnaît chaque opération par la première ligne `# tache:<op> ...` du script."""

    def __init__(self):
        self.appels = []
        self.taches = {}
        self.entrees = {}
        self.deposes = None
        self.codes_lancer = []
        self.veilleur, self.enveloppe = "vivant", "absent"   # ce que `etat` voit (enveloppe vivante d'un agent)
        self.pleine = 0              # nombre de réponses 75 (aucune place) avant d'accepter
        self.maintenant = 1_800_000_000

    def executer(self, hote, commande, cle, stdin=None, delai=60, runner=None):
        code, sortie, erreur = self._repondre(commande, stdin.encode("utf-8") if stdin is not None else None, delai)
        return code, sortie.decode("utf-8", "replace"), erreur

    def executer_octets(self, hote, commande, cle, entree=None, delai=60, runner=None):
        if hasattr(entree, "read"):                  # archive des entrées passée en FICHIER (comme au vrai ssh)
            self.entrees_fichier = getattr(self, "entrees_fichier", 0) + 1
            entree = entree.read()
        return self._repondre(commande, entree, delai)

    def ops(self, op=None):
        return [a for a in self.appels if op is None or a[0] == op]

    def tache(self, ident, etat="en_cours", statut=None, fichiers=None, raison=""):
        self.taches[ident] = {"etat": {"id": ident, "etat": etat, "statut": statut, "debut": iso(self.maintenant - 60),
                                       "fin": iso(self.maintenant) if etat != "en_cours" else None, "raison": raison},
                              "fichiers": dict(fichiers or {})}
        return self.taches[ident]

    def _repondre(self, commande, entree, delai):
        script = entree.decode("utf-8", "replace") if commande == "bash -s" else commande
        premiere = script.split("\n", 1)[0]
        assert premiere.startswith("# tache:"), premiere
        mots = premiere[len("# tache:"):].split()
        self.appels.append((mots[0], script, entree, delai))
        return getattr(self, "_" + mots[0])(mots[1:], script, entree)

    def _preparer_agent(self, args, script, entree):
        if args[0] in self.taches:
            return 73, b"", "existe"
        with tarfile.open(fileobj=io.BytesIO(entree)) as tar:
            self.entrees[args[0]] = {m.name: tar.extractfile(m).read() for m in tar}
        self.tache(args[0], etat="en_attente")
        return 0, b"", ""

    def _deposer_agent(self, args, script, entree):
        with tarfile.open(fileobj=io.BytesIO(entree)) as tar:
            self.deposes = {m.name: tar.extractfile(m).read() for m in tar}
        return 0, b"", ""

    def _effacer(self, args, script, entree):
        self.taches.pop(args[0], None)
        return 0, b"", ""

    def _abandon_agent(self, args, script, entree):
        e = self.entrees[args[0]]
        e.pop("entree/projet.bundle", None)
        e.pop("entree/app.apk", None)
        return 0, b"", ""

    def _lancer_agent(self, args, script, entree):
        t = self.taches[args[0]]
        if self.codes_lancer:
            code = self.codes_lancer.pop(0)
            return code, b"", "refusé"
        if self.pleine > 0:
            self.pleine -= 1
            return 75, (json.dumps(t["etat"]) + "\n").encode(), ""
        t["etat"] = {**t["etat"], "etat": "en_cours", "debut": iso(self.maintenant), "raison": "Conteneur démarré."}
        return 0, (json.dumps(t["etat"]) + "\n").encode(), ""

    def _etat(self, args, script, entree):
        t = self.taches.get(args[0])
        if not t:
            return 3, b"", ""
        texte = (f"maintenant={self.maintenant}\nveilleur={self.veilleur}\nenveloppe={self.enveloppe}\n"
                 f"etat={json.dumps(t['etat'])}\n")
        return 0, texte.encode(), ""

    def _fichier(self, args, script, entree):
        t = self.taches[args[0]]
        nom = args[1]
        assert nom in ("flux.jsonl", "fin.json", "resultat.bundle"), nom
        donnees = t["fichiers"].get(nom)
        if donnees is None:
            return 3, b"", ""
        plafond = int(script.split("-size -", 1)[1].split("c", 1)[0])
        if len(donnees) >= plafond:
            return 5, b"", ""
        return 0, donnees, ""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = Path(self.tmp.name) / "config"
        self.dossier.mkdir()
        declarer(self.dossier)
        self.srv = FauxServeur()
        self.pauses = []

    def demande(self, **plus):
        return sa.valider_demande_agent({**brut(), "id": ID1, **plus})

    def lancer(self, demande=None, **k):
        k.setdefault("dormir", self.pauses.append)
        k.setdefault("argv", list(ARGV))
        k.setdefault("consigne", "Consigne de l'équipe.\n")
        k.setdefault("message", "Ajoute un bouton.\n")
        paquet = k.pop("paquet", PAQUET)
        return sa.lancer_agent(demande or self.demande(), paquet, dossier=self.dossier, ssh=self.srv, **k)


class TestDemande(unittest.TestCase):
    def test_demande_valide(self):
        d = sa.valider_demande_agent(brut())
        self.assertEqual((d.projet, d.tache, d.mode, d.modele, d.branche, d.base, d.reprend, d.places),
                         ("demo", "ajout-bouton", "seul", "sonnet", "main", BASE, None, 2))
        self.assertEqual(dict(d.limites), sa.LIMITES_AGENT)
        self.assertRegex(d.id, r"^t\d{8}-\d{6}-[0-9a-f]{4}$")
        d2 = sa.valider_demande_agent(brut(mode="pilote", reprend=ID1, branche="feature/x-1", modele=None, places=4,
                                           id=ID1))
        self.assertEqual((d2.mode, d2.reprend, d2.branche, d2.modele, d2.places, d2.id),
                         ("pilote", ID1, "feature/x-1", None, 4, ID1))
        with self.assertRaises(Exception):
            d.mode = "pilote"                              # dataclass figée
        with self.assertRaises(TypeError):
            d.limites["duree_s"] = 1                       # limites immuables

    def test_limites_agent_jamais_au_dessus(self):
        self.assertEqual(sa.LIMITES_AGENT, {"duree_s": 2400, "tours": 200, "memoire_mo": 4096, "cpus": 2,
                                            "paquet_octets": 524288000, "flux_octets": 20971520})
        for cle, defaut in sa.LIMITES_AGENT.items():
            self.assertEqual(sa.valider_demande_agent(brut(limites={cle: defaut})).limites[cle], defaut)
            self.assertEqual(sa.valider_demande_agent(brut(limites={cle: 1})).limites[cle], 1)
            for mauvais in (defaut + 1, 0, -1, True, "1", 1.5, None):
                with self.assertRaises(ValueError, msg=(cle, mauvais)):
                    sa.valider_demande_agent(brut(limites={cle: mauvais}))
        with self.assertRaises(ValueError):
            sa.valider_demande_agent(brut(limites={"inconnue": 1}))
        with self.assertRaises(ValueError):
            sa.valider_demande_agent(brut(limites=[1]))
        with self.assertRaises(ValueError):
            sa.valider_demande_agent(brut(places=5))
        with self.assertRaises(ValueError):
            sa.valider_demande_agent(brut(places=0))

    def test_tache_branche_base_hostiles_refusees(self):
        for mauvais in ("", "a/b", "../x", "x" * 61, "a b", "a\n", ".x", "x.lock", "a..b", "x.", "é", 5, None):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                sa.valider_demande_agent(brut(tache=mauvais))
        for mauvais in ("", "-x", "a b", "x..y", "@{-1}", "a\n", "x.lock", "a//b", "a/.b", "x/", "x" * 201, "a~1", "a:b",
                        "a^b", "a?b", "a*b", "a[b", "a\\b", 5, None):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                sa.valider_demande_agent(brut(branche=mauvais))
        for mauvais in ("", "A" * 40, "a" * 39, "a" * 41, "g" * 40, "a" * 40 + "\n", 5, None):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                sa.valider_demande_agent(brut(base=mauvais))
        for mauvais in ("t1", "../x", ID1 + "\n", 5, ""):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                sa.valider_demande_agent(brut(reprend=mauvais))
        for mauvais in ("root", "", None, "SEUL"):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                sa.valider_demande_agent(brut(mode=mauvais))
        for plus in ({"projet": 'a"b'}, {"projet": "a\\b"}, {"projet": ""}, {"projet": "a\nb"}, {"projet": "é" * 101},
                     {"modele": "a b"}, {"modele": "-x"}, {"id": "t1"}, {"inconnu": 1}):
            with self.assertRaises(ValueError, msg=repr(plus)):
                sa.valider_demande_agent(brut(**plus))
        with self.assertRaises(ValueError):
            sa.valider_demande_agent([])


def depot(chemin, commits=1):
    chemin.mkdir(parents=True, exist_ok=True)
    git(chemin, "init", "-q", "-b", "main")
    for i in range(commits):
        (chemin / "f.txt").write_bytes(f"ligne {i}\r\n".encode() * 3)
        git(chemin, "add", "f.txt")
        git(chemin, "commit", "-q", "-m", f"commit {i}")
    return git(chemin, "rev-parse", "HEAD").decode().strip()


class TestPaquet(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.projet = Path(self.tmp.name) / "projet"

    def test_paquet_de_head_et_refus_head_detache(self):
        base = depot(self.projet, commits=2)
        (self.projet / "non-commite.txt").write_text("brouillon-NON-COMMITE", encoding="utf-8")
        paquet, branche, tete = sa.preparer_paquet(self.projet)
        self.assertEqual((branche, tete), ("main", base))
        self.assertTrue(paquet.startswith(b"# v2 git bundle\n") or paquet.startswith(b"# v3 git bundle\n"))
        self.assertNotIn(b"brouillon-NON-COMMITE", paquet)
        fichier = Path(self.tmp.name) / "p.bundle"
        fichier.write_bytes(paquet)
        git(self.projet, "bundle", "verify", str(fichier))
        git(self.projet, "checkout", "-q", "--detach", "HEAD")
        with self.assertRaises(st.RefusLancement) as r:
            sa.preparer_paquet(self.projet)
        self.assertIn("détaché", str(r.exception))

    def test_depot_sans_commit_refuse(self):
        self.projet.mkdir()
        git(self.projet, "init", "-q", "-b", "main")
        with self.assertRaises(st.RefusLancement):
            sa.preparer_paquet(self.projet)

    def test_paquet_trop_gros_refuse(self):
        depot(self.projet)
        with mock.patch.dict(sa.LIMITES_AGENT, {"paquet_octets": 100}):
            with self.assertRaises(st.RefusLancement) as r:
                sa.preparer_paquet(self.projet)
        self.assertIn("trop gros", str(r.exception))

    def test_paquet_ecrit_dans_un_fichier_sans_copie_en_memoire(self):
        base = depot(self.projet, commits=2)
        fichier = Path(self.tmp.name) / "projet.bundle"
        paquet, branche, tete = sa.preparer_paquet(self.projet, fichier=fichier)
        self.assertEqual((paquet, branche, tete), (fichier, "main", base))
        git(self.projet, "bundle", "verify", str(fichier))
        with mock.patch.dict(sa.LIMITES_AGENT, {"paquet_octets": 100}):
            with self.assertRaises(st.RefusLancement) as r:
                sa.preparer_paquet(self.projet, fichier=fichier)
        self.assertIn("trop gros", str(r.exception))

    def test_changements_non_commites_git_en_echec_et_sans_verrou(self):
        appels = []

        def faux(projet, args, max_octets=None):
            appels.append(args)
            return 128, b"", "fatal"
        self.assertIsNone(sa.changements_non_commites(self.projet, git=faux))
        self.assertEqual(appels[0][:2], ["--no-optional-locks", "status"])

    def test_changements_non_commites_listes(self):
        depot(self.projet)
        self.assertEqual(sa.changements_non_commites(self.projet), [])
        (self.projet / "f.txt").write_text("modifié")
        (self.projet / "neuf.txt").write_text("neuf")
        lignes = sa.changements_non_commites(self.projet)
        self.assertEqual(sorted(l[3:] for l in lignes), ["f.txt", "neuf.txt"])

    def test_branche_hors_motif_refusee_et_ref_complete(self):
        depot(self.projet)
        git(self.projet, "checkout", "-q", "-b", "fonction/é")
        with self.assertRaises(st.RefusLancement):
            sa.preparer_paquet(self.projet)
        git(self.projet, "checkout", "-q", "-b", "fonction/ok")
        appels = []

        def espion(projet, args, max_octets=None):
            appels.append(args)
            return sa._git(projet, args, max_octets)
        _p, branche, _b = sa.preparer_paquet(self.projet, git=espion)
        self.assertEqual(branche, "fonction/ok")
        self.assertIn(["bundle", "create", "-", "HEAD", "refs/heads/fonction/ok"], appels)


class TestGitRobuste(unittest.TestCase):
    """`_git` ne se fige jamais : stderr vidé en continu, échéance réelle, processus tué puis attendu."""

    def lancer(self, code, delai=None):
        sortie = []
        with mock.patch.object(sa, "_COMMANDE_GIT", [sys.executable, "-c", code, "--"]), \
                mock.patch.object(sa, "DELAI_GIT_S", delai or 60):
            fil = threading.Thread(target=lambda: sortie.append(sa._git(Path("."), ["x"])), daemon=True)
            fil.start()
            fil.join(30)
            self.assertFalse(fil.is_alive(), "_git est figé")
        return sortie[0]

    def test_git_qui_inonde_stderr_ne_fige_pas(self):
        code, sortie, erreur = self.lancer("import sys; sys.stderr.write('e' * 5_000_000); sys.stdout.write('ok')")
        self.assertEqual((code, sortie), (0, b"ok"))
        self.assertLessEqual(len(erreur), 65536)

    def test_git_qui_ne_finit_jamais_est_tue(self):
        debut = time.monotonic()
        code, sortie, erreur = self.lancer("import time; time.sleep(120)", delai=1)
        self.assertEqual(code, 124)
        self.assertLess(time.monotonic() - debut, 25)

    def test_git_muet_apres_une_sortie_partielle_est_tue(self):
        code, _s, _e = self.lancer("import sys, time; sys.stdout.write('x'); sys.stdout.flush(); time.sleep(120)",
                                   delai=1)
        self.assertEqual(code, 124)

    def test_echeance_stricte_meme_si_un_petit_enfant_garde_la_sortie(self):
        """git finit mais un petit-enfant (pack-objects…) garde la sortie ouverte : l'échéance tient quand même."""
        debut = time.monotonic()
        code, _s, _e = self.lancer("import subprocess, sys; subprocess.Popen([sys.executable, '-c', "
                                   "'import time; time.sleep(15)']); sys.stdout.write('x'); sys.stdout.flush()", delai=2)
        self.assertEqual(code, 124)
        self.assertLess(time.monotonic() - debut, 12)

    def test_git_en_langue_c_et_stderr_borne_en_memoire(self):
        code, sortie, erreur = self.lancer("import os, sys; sys.stdout.write(os.environ.get('LC_ALL', '?')); "
                                           "sys.stderr.write('e' * 300_000)")
        self.assertEqual((code, sortie), (0, b"C"))
        self.assertEqual(len(erreur), sa.ERREUR_MAX)

    def test_sortie_vers_un_fichier_sans_la_garder(self):
        sortie = io.BytesIO()
        with mock.patch.object(sa, "_COMMANDE_GIT", [sys.executable, "-c", "import sys; sys.stdout.write('abc' * 1000)",
                                                     "--"]):
            code, garde, _e = sa._git(Path("."), ["x"], max_octets=10_000, vers=sortie)
            self.assertEqual((code, garde, sortie.getvalue()), (0, b"", b"abc" * 1000))
            self.assertEqual(sa._git(Path("."), ["x"], max_octets=100, vers=io.BytesIO())[0], 99)


class TestLancer(Base):
    def test_lancer_envoie_les_entrees_en_octets_intacts(self):
        r = self.lancer()
        self.assertEqual(r, {"id": ID1, "etat": "en_cours", "serveur_id": "ovh1"})
        e = self.srv.entrees[ID1]
        self.assertEqual(sorted(e), sorted("entree/" + n for n in ("projet.bundle", "argv.json", "consigne.md",
                                                                   "message.md", "demande.json")))
        self.assertEqual(e["entree/projet.bundle"], PAQUET)
        self.assertEqual(json.loads(e["entree/argv.json"]), ARGV)
        self.assertEqual(e["entree/consigne.md"], "Consigne de l'équipe.\n".encode())
        self.assertEqual(e["entree/message.md"], b"Ajoute un bouton.\n")
        demande = json.loads(e["entree/demande.json"])
        self.assertEqual((demande["type"], demande["id"], demande["projet"], demande["tache"], demande["mode"],
                          demande["base"], demande["branche"], demande["reprend"]),
                         ("agent", ID1, "demo", "ajout-bouton", "seul", BASE, "main", None))
        # le paquet n'est jamais dans une commande
        self.assertNotIn(b"git bundle", self.srv.ops("preparer_agent")[0][1].encode())
        self.assertEqual(self.srv.deposes, {nom: (RACINE / "serveur_ovh" / nom).read_bytes()
                                            for nom in ("taches/lancer_agent.sh", "taches/commun.sh")})
        # une seule source pour la durée : celle de l'argument de l'enveloppe est celle de demande.json
        commande = self.srv.ops("lancer_agent")[0][1]
        self.assertIn(f'lancer_agent.sh" {ID1} seul {demande["limites"]["duree_s"]} 4096 2 2\n', commande)
        self.assertEqual(demande["limites"]["duree_s"], 2400)
        fiche = st.Index(self.dossier).lire()[ID1]
        self.assertEqual((fiche["type"], fiche["projet"], fiche["tache"], fiche["mode"], fiche["serveur_id"],
                          fiche["session"], fiche["etat"]), ("agent", "demo", "ajout-bouton", "seul", "ovh1", None,
                                                             "en_cours"))

    def test_duree_choisie_est_la_meme_partout(self):
        self.lancer(self.demande(limites={"duree_s": 900, "memoire_mo": 2048, "cpus": 1}, places=3))
        demande = json.loads(self.srv.entrees[ID1]["entree/demande.json"])
        self.assertEqual(demande["limites"]["duree_s"], 900)
        self.assertIn(f'lancer_agent.sh" {ID1} seul 900 2048 1 3\n', self.srv.ops("lancer_agent")[0][1])

    def test_pilote_sans_apk_refuse(self):
        declarer(self.dossier, [("ovh1", {**CAPS_AGENT, "emulateur-image": "fait"})])
        for apk in (None, b"", "texte"):
            with self.assertRaises(st.RefusLancement):
                self.lancer(self.demande(mode="pilote"), apk=apk)
        self.assertEqual(self.srv.appels, [])
        with mock.patch.object(st, "APK_MAX_OCTETS", 10):
            with self.assertRaises(st.RefusLancement):
                self.lancer(self.demande(mode="pilote"), apk=APK)
        r = self.lancer(self.demande(mode="pilote"), apk=APK)
        self.assertEqual(r["etat"], "en_cours")
        self.assertEqual(self.srv.entrees[ID1]["entree/app.apk"], APK)
        self.assertIn(f'lancer_agent.sh" {ID1} pilote ', self.srv.ops("lancer_agent")[0][1])
        # pilote : le pont hôte et l'enveloppe d'émulation qu'il lance sont déposés avec l'enveloppe d'agent
        self.assertEqual(self.srv.deposes, {nom: (RACINE / "serveur_ovh" / nom).read_bytes()
                                            for nom in ("taches/lancer_agent.sh", "taches/commun.sh",
                                                        "taches/lancer_emulation.sh", "taches/pont_hote.py")})

    def test_mode_seul_n_envoie_pas_d_apk(self):
        self.lancer(apk=APK)
        self.assertNotIn("entree/app.apk", self.srv.entrees[ID1])

    def test_lancer_choisit_un_serveur_avec_abonnement(self):
        declarer(self.dossier, serveurs=[("a", {"agent": "presente"}),                       # sans abonnement
                                         ("b", {"agent": "presente", "agent-abonnement": "absente"}),
                                         ("c", {"agent": "inconnue", "agent-abonnement": "inconnue"}),
                                         ("d", CAPS_AGENT), ("e", CAPS_AGENT)])
        self.assertEqual(self.lancer()["serveur_id"], "d")
        # pilote : l'image d'émulation est aussi requise
        declarer(self.dossier, serveurs=[("d", CAPS_AGENT), ("e", {**CAPS_AGENT, "emulateur-image": "presente"})])
        self.srv = FauxServeur()
        self.assertEqual(self.lancer(self.demande(mode="pilote", tache="pil", id="t20261120-101501-bbbb"), apk=APK)["serveur_id"], "e")
        declarer(self.dossier, serveurs=[("a", {"agent": "presente"})])
        with self.assertRaises(st.RefusLancement) as r:
            self.lancer(self.demande(tache="troisieme", id="t20261120-101502-cccc"))
        self.assertIn("agent-abonnement", str(r.exception))
        self.assertIn("a :", str(r.exception))

    def test_lancer_attend_une_place_puis_abandonne(self):
        self.srv.pleine = 2
        r = self.lancer()
        self.assertEqual(r["etat"], "en_cours")
        self.assertEqual(self.pauses, [15, 15])
        self.srv = FauxServeur()
        self.srv.pleine = 99
        r = self.lancer(self.demande(tache="quatrieme", id="t20261120-101503-dddd"), attente_max_s=30)
        self.assertEqual(r["etat"], "en_attente")
        self.assertIn("place", r["erreur"])
        self.assertTrue(st.Index(self.dossier).lire()["t20261120-101503-dddd"]["abandonnee"])

    def test_abandon_efface_paquet_et_apk_sur_le_serveur(self):
        self.srv.pleine = 99
        r = self.lancer(attente_max_s=0)
        self.assertEqual(r["etat"], "en_attente")
        self.assertEqual(len(self.srv.ops("abandon_agent")), 1)
        self.assertNotIn("entree/projet.bundle", self.srv.entrees[ID1])
        self.assertIn("projet.bundle", self.srv.ops("abandon_agent")[0][1])

    def test_lancer_avertit_des_changements_non_commites(self):
        projet = Path(self.tmp.name) / "projet"
        base = depot(projet)
        d = self.demande(base=base)
        self.assertNotIn("avertissement", self.lancer(d, projet=projet))
        (projet / "brouillon.txt").write_text("pas commité")
        r = self.lancer(self.demande(base=base, tache="deux", id="t20261120-101504-1234"), projet=projet)
        self.assertIn("non commit", r["avertissement"])
        self.assertIn("brouillon.txt", r["avertissement"])
        self.assertEqual(r["etat"], "en_cours")

    def test_branche_agent_existante_non_ancetre_renommee_puis_lancement(self):
        projet = Path(self.tmp.name) / "projet"
        base = depot(projet, commits=2)
        git(projet, "checkout", "-q", "-b", "agent/ajout-bouton", "HEAD~1")
        (projet / "x.txt").write_text("x")
        git(projet, "add", "x.txt")
        git(projet, "commit", "-q", "-m", "x")
        ancienne_tete = git(projet, "rev-parse", "agent/ajout-bouton").decode().strip()
        git(projet, "checkout", "-q", "main")
        r = self.lancer(self.demande(base=base), projet=projet)
        self.assertEqual(r["etat"], "en_cours")
        # l'ancienne branche est sauvegardée sous un autre nom, au même commit ; le nom d'origine est libre
        branches = git(projet, "branch", "--list", "--format=%(refname:short)").decode().split()
        sauvegardes = [b for b in branches if b.startswith("agent/ajout-bouton-ancienne-")]
        self.assertEqual(len(sauvegardes), 1)
        self.assertEqual(git(projet, "rev-parse", sauvegardes[0]).decode().strip(), ancienne_tete)
        self.assertNotIn("agent/ajout-bouton", branches)
        # l'action est journalisée dans la fiche de la tâche
        fiche = st.Index(self.dossier).lire()[ID1]
        self.assertIn(sauvegardes[0], fiche["journal"][0])
        self.assertEqual(fiche["branche_sauvegardee"], sauvegardes[0])
        # un ancêtre de la base (reprise d'un travail déjà fusionné) est accepté
        git(projet, "branch", "-f", "agent/ajout-bouton", "HEAD~1")
        self.assertEqual(self.lancer(self.demande(base=base), projet=projet)["etat"], "en_cours")

    def test_paquet_en_fichier_envoye_intact_par_un_fichier(self):
        fichier = Path(self.tmp.name) / "projet.bundle"
        fichier.write_bytes(PAQUET)
        self.assertEqual(self.lancer(paquet=fichier)["etat"], "en_cours")
        self.assertEqual(self.srv.entrees[ID1]["entree/projet.bundle"], PAQUET)
        self.assertEqual(self.srv.entrees_fichier, 1)        # l'archive est passée à ssh en fichier
        with self.assertRaises(st.RefusLancement):
            self.lancer(self.demande(tache="vide", id="t20261120-101510-0001"), paquet=Path(self.tmp.name) / "absent")

    def test_branche_agent_extraite_refusee_avant_envoi(self):
        projet = Path(self.tmp.name) / "projet"
        base = depot(projet)
        git(projet, "worktree", "add", "-q", "-b", "agent/ajout-bouton", str(Path(self.tmp.name) / "wt"), base)
        with self.assertRaises(st.RefusLancement) as r:
            self.lancer(self.demande(base=base), projet=projet)
        self.assertIn("extraite", str(r.exception))
        self.assertEqual(self.srv.appels, [])

    def test_git_status_en_echec_le_dit_dans_l_avertissement(self):
        projet = Path(self.tmp.name) / "projet"
        base = depot(projet)

        def git_(p, args, max_octets=None):
            if "status" in args:
                return 128, b"", "fatal"
            return sa._git(p, args, max_octets)
        r = self.lancer(self.demande(base=base), projet=projet, git=git_)
        self.assertIn("illisible", r["avertissement"])

    def test_tache_abandonnee_faute_de_place_ne_bloque_pas_le_meme_nom(self):
        self.srv.pleine = 99
        self.assertEqual(self.lancer(attente_max_s=0)["etat"], "en_attente")
        self.srv.pleine = 0
        r = self.lancer(self.demande(id="t20261120-101511-0002"))
        self.assertEqual(r["etat"], "en_cours")

    def test_tache_en_double_ou_en_collision_de_casse_refusee(self):
        self.lancer()
        for tache in ("ajout-bouton", "AJOUT-bouton"):
            with self.assertRaises(st.RefusLancement, msg=tache) as r:
                self.lancer(self.demande(tache=tache, id="t20261120-101505-9999"))
            self.assertIn("déjà", str(r.exception))
        self.assertEqual(self.lancer(self.demande(tache="autre", id="t20261120-101506-9998"))["etat"], "en_cours")
        st.Index(self.dossier).fusionner(ID1, {"etat": "terminee"})
        self.assertEqual(self.lancer(self.demande(tache="AJOUT-bouton", id="t20261120-101507-9997"))["etat"],
                         "en_cours")

    def test_noms_reserves_de_windows_refuses(self):
        for tache in ("con", "CON", "nul", "com1", "lpt9", "aux.txt", "Prn"):
            with self.assertRaises(ValueError, msg=tache):
                sa.valider_demande_agent(brut(tache=tache))
        self.assertEqual(sa.valider_demande_agent(brut(tache="console")).tache, "console")

    def test_enveloppe_d_agent_vivante_n_est_pas_nettoyee(self):
        self.lancer()
        self.srv.veilleur, self.srv.enveloppe = "mort", "vivant"
        self.srv.maintenant += 1000
        self.assertEqual(st.etat(ID1, dossier=self.dossier, ssh=self.srv)["etat"], "en_cours")
        self.assertEqual(self.srv.ops("nettoyer"), [])

    def test_lancer_refus_de_l_enveloppe_efface_les_entrees(self):
        self.srv.codes_lancer = [2]
        r = self.lancer()
        self.assertEqual(r["etat"], "echouee")
        self.assertIn("refusé", r["erreur"])
        self.assertEqual(len(self.srv.ops("effacer")), 1)
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["etat"], "echouee")

    def test_entrees_invalides_refusees_avant_tout_envoi(self):
        for k in ({"argv": []}, {"argv": ["claude", 3]}, {"argv": "claude"}, {"consigne": ""}, {"message": 5},
                  {"paquet": b""}, {"paquet": "texte"}, {"attente_max_s": -1}):
            with self.assertRaises(st.RefusLancement, msg=repr(k)):
                self.lancer(**k)
        with mock.patch.dict(sa.LIMITES_AGENT, {"paquet_octets": 10}):
            with self.assertRaises(st.RefusLancement):
                self.lancer(self.demande(limites={"paquet_octets": 10}), paquet=PAQUET)
        with self.assertRaises(st.RefusLancement):
            self.lancer({"tache": "../x"})
        self.assertEqual(self.srv.appels, [])

    def test_genre_reponse_garde_dans_l_index_jamais_dans_demande_json(self):
        """Une réponse aux questions (`genre: reponse`) se distingue de la tâche dans l'index ; l'enveloppe ne la voit pas."""
        self.assertEqual(self.demande().genre, "tache")
        for mauvais in ("autre", "", None, 1):
            with self.assertRaises(ValueError):
                self.demande(genre=mauvais)
        self.lancer(self.demande(genre="reponse"))
        self.assertEqual(st.Index(self.dossier).lire()[ID1]["genre"], "reponse")
        self.assertNotIn("genre", json.loads(self.srv.entrees[ID1]["entree/demande.json"]))

    def test_index_garde_type_agent_et_tranche_a_inchangee(self):
        self.lancer()
        etat = st.etat(ID1, dossier=self.dossier, ssh=self.srv)
        self.assertEqual(etat["etat"], "en_cours")
        fiche = st.Index(self.dossier).lire()[ID1]
        self.assertEqual((fiche["type"], fiche["tache"], fiche["session"]), ("agent", "ajout-bouton", None))
        self.assertEqual([t["id"] for t in sa.taches_agent_actives(self.dossier)], [ID1])
        # une tâche d'émulation de la tranche A n'est pas une tâche d'agent et ne porte pas de type
        autre = "t20261120-101600-eeee"
        st.Index(self.dossier).enregistrer(autre, {"etat": "en_cours", "serveur_id": "ovh1", "mode": "pilote"})
        st.Index(self.dossier).enregistrer("t20261120-101700-ffff", {"etat": "terminee", "type": "agent"})
        self.assertEqual([t["id"] for t in sa.taches_agent_actives(self.dossier)], [ID1])
        self.assertNotIn("type", st.Index(self.dossier).lire()[autre])
        # le choix de serveur de la tranche A garde son défaut
        declarer(self.dossier, [("ovh1", {"android-emulateur": "presente", "emulateur-image": "fait"})])
        self.assertEqual(st.choisir_serveur(self.dossier).id, "ovh1")
        declarer(self.dossier, [("ovh1", CAPS_AGENT)])
        with self.assertRaises(st.RefusLancement) as r:
            st.choisir_serveur(self.dossier)
        self.assertIn("l'émulation", str(r.exception))
        self.assertEqual(st.choisir_serveur(self.dossier, ("agent",)).id, "ovh1")


class TestRecuperer(Base):
    """Vrais dépôts : le projet du poste, un dépôt « du serveur » dont on tire des paquets (bons ou hostiles)."""

    def setUp(self):
        super().setUp()
        self.projet = Path(self.tmp.name) / "projet"
        self.base = depot(self.projet, commits=2)
        self.serveur_depot = Path(self.tmp.name) / "serveur"
        git(self.tmp.name, "clone", "-q", str(self.projet), str(self.serveur_depot))
        self.tache = "ajout-bouton"
        self.ref = f"agent/{self.tache}"
        git(self.serveur_depot, "checkout", "-q", "-b", self.ref)
        (self.serveur_depot / "bouton.txt").write_bytes(b"bouton\r\n\x00\xff")
        git(self.serveur_depot, "add", "bouton.txt")
        git(self.serveur_depot, "commit", "-q", "-m", "ajoute le bouton")
        self.tete = git(self.serveur_depot, "rev-parse", "HEAD").decode().strip()
        st.Index(self.dossier).enregistrer(ID1, {"etat": "en_cours", "type": "agent", "tache": self.tache,
                                                 "base": self.base, "serveur_id": "ovh1", "projet": "demo",
                                                 "session": None, "mode": "seul"})

    def paquet(self, *revs, ref=None):
        return git(self.serveur_depot, "bundle", "create", "-", *revs)

    def bon_paquet(self):
        return self.paquet(self.ref, f"^{self.base}")

    def fin(self, **plus):
        return json.dumps({"code": 0, "commits": 1, "branche": self.ref, "base": self.base, **plus}).encode()

    def servir(self, etat="terminee", fin=None, paquet=None, flux=b'{"type":"result"}\r\n\x00\xff', **plus):
        f = {"flux.jsonl": flux}
        if fin is not False:
            f["fin.json"] = fin if fin is not None else self.fin(**plus)
        if paquet is not False:
            f["resultat.bundle"] = paquet if paquet is not None else self.bon_paquet()
        self.srv.tache(ID1, etat=etat, fichiers=f)

    def recuperer(self):
        return sa.recuperer(ID1, self.projet, dossier=self.dossier, ssh=self.srv)

    def branches(self):
        return git(self.projet, "for-each-ref", "--format=%(refname) %(objectname)").decode().split("\n")

    def test_recuperer_rend_le_flux_la_fin_et_la_branche(self):
        self.servir(echeance=True, extra="ignoré")
        r = self.recuperer()
        self.assertEqual(r["flux"], b'{"type":"result"}\r\n\x00\xff')
        self.assertEqual(r["fin"], {"code": 0, "commits": 1, "branche": self.ref, "base": self.base, "echeance": True})
        self.assertEqual(r["branche"], self.ref)
        self.assertEqual(git(self.projet, "rev-parse", f"refs/heads/{self.ref}").decode().strip(), self.tete)
        self.assertEqual(git(self.projet, "rev-parse", "HEAD").decode().strip(), self.base)     # HEAD jamais bougé
        self.assertEqual(self.srv.ops("etat")[0][0], "etat")
        self.assertEqual([a[0] for a in self.srv.ops("fichier")], ["fichier", "fichier", "fichier"])

    def test_recuperer_efface_le_paquet_temporaire(self):
        self.servir()
        vide = Path(self.tmp.name) / "tmp-vide"
        vide.mkdir()
        with mock.patch.object(tempfile, "tempdir", str(vide)):
            self.recuperer()
        self.assertEqual(list(vide.iterdir()), [])

    def test_paquet_resultat_ecrit_droit_dans_un_fichier(self):
        """ssh réel : `executer_vers_fichier` écrit la sortie dans le fichier temporaire, jamais en mémoire."""
        self.servir()
        vus = []

        def vers_fichier(hote, commande, cle, destination, maximum, entree=None, delai=60):
            code, donnees, erreur = self.srv._repondre(commande, entree, delai)
            Path(destination).write_bytes(donnees)
            vus.append((Path(destination).name, maximum))
            return code, len(donnees), erreur
        self.srv.executer_vers_fichier = vers_fichier
        self.assertEqual(self.recuperer()["branche"], self.ref)
        self.assertEqual(vus, [("resultat.bundle", sa.LIMITES_AGENT["paquet_octets"])])

    def test_refus_transitoires_et_definitifs_marques(self):
        self.servir(paquet=self.bon_paquet()[:-20] + bytes(20))
        with self.assertRaises(sa.RefusRecuperation) as r:
            self.recuperer()
        self.assertTrue(r.exception.transitoire)
        self.servir(fin=self.fin(base="b" * 40))
        with self.assertRaises(sa.RefusRecuperation) as r:
            self.recuperer()
        self.assertFalse(r.exception.transitoire)

    def test_recuperer_seulement_terminee_ou_arretee(self):
        for etat in ("en_cours", "echouee", "en_attente"):
            self.servir(etat=etat)
            r = self.recuperer()
            self.assertEqual((r["flux"], r["fin"], r["branche"], r["etat"]), (b"", {}, None, etat))
        self.assertEqual(self.srv.ops("fichier"), [])
        self.assertFalse(any(self.ref in b for b in self.branches()))
        self.servir(etat="arretee")
        self.assertEqual(self.recuperer()["branche"], self.ref)

    def test_recuperer_refuse_une_autre_reference(self):
        # refs/heads/main seulement, deux têtes, une étiquette, une autre branche agent
        git(self.serveur_depot, "branch", "autre", self.ref)
        git(self.serveur_depot, "tag", "-a", "-m", "m", "v1", self.ref)
        git(self.serveur_depot, "checkout", "-q", "-b", "main2", self.base)
        (self.serveur_depot / "z.txt").write_text("z")
        git(self.serveur_depot, "add", "z.txt")
        git(self.serveur_depot, "commit", "-q", "-m", "z")
        hostiles = {
            "deux têtes": self.paquet(self.ref, "main2", f"^{self.base}"),
            "autre branche": self.paquet("autre", f"^{self.base}"),
            "branche main": self.paquet("main2", f"^{self.base}"),
            "étiquette": self.paquet("v1", f"^{self.base}"),
            "HEAD en plus": self.paquet("HEAD", self.ref, f"^{self.base}"),
        }
        for nom, paquet in hostiles.items():
            self.servir(paquet=paquet)
            with self.assertRaises(sa.RefusRecuperation, msg=nom):
                self.recuperer()
            self.assertFalse(any(" " in b and b.startswith("refs/heads/agent") for b in self.branches()), nom)
            self.assertEqual(git(self.projet, "rev-parse", "HEAD").decode().strip(), self.base)
        self.assertNotIn("refs/heads/main2", "\n".join(self.branches()))

    def test_recuperer_refuse_un_prerequis_qui_n_est_pas_la_base(self):
        git(self.serveur_depot, "checkout", "-q", self.ref)
        paquet_sans = self.paquet(self.ref)                       # aucun prérequis (historique complet)
        autre_base = git(self.serveur_depot, "rev-parse", f"{self.ref}~1").decode().strip()
        for nom, paquet in {"sans prérequis": paquet_sans, "prérequis différent": self.paquet(self.ref, f"^{autre_base}")}.items():
            if nom == "prérequis différent" and autre_base == self.base:
                continue
            self.servir(paquet=paquet)
            with self.assertRaises(sa.RefusRecuperation, msg=nom):
                self.recuperer()

    def test_recuperer_refuse_un_paquet_abime(self):
        bon = self.bon_paquet()
        for nom, paquet in {"coupé": bon[:len(bon) // 2], "texte": b"pas un paquet", "vide d'en-tête": b"# v2 git bundle\n",
                            "octets modifiés": bon[:-20] + bytes(20)}.items():
            self.servir(paquet=paquet)
            with self.assertRaises(sa.RefusRecuperation, msg=nom):
                self.recuperer()
            self.assertFalse(any(b.startswith(f"refs/heads/{self.ref}") for b in self.branches()), nom)

    def test_recuperer_sans_commit_rend_branche_none(self):
        self.servir(fin=json.dumps({"code": 0, "commits": 0, "branche": None, "base": self.base}).encode(), paquet=False)
        r = self.recuperer()
        self.assertEqual((r["branche"], r["fin"]["commits"]), (None, 0))
        self.assertEqual([a[1].split()[3] for a in self.srv.ops("fichier")], ["flux.jsonl", "fin.json"])
        # sans fin.json (agent arrêté avant de conclure) : rien à récupérer
        self.servir(etat="arretee", fin=False, paquet=False)
        r = self.recuperer()
        self.assertEqual((r["fin"], r["branche"]), ({}, None))

    def test_recuperer_ne_reecrit_pas_une_branche_divergente(self):
        git(self.projet, "branch", self.ref, self.base)
        git(self.projet, "checkout", "-q", self.ref)
        (self.projet / "local.txt").write_text("travail local")
        git(self.projet, "add", "local.txt")
        git(self.projet, "commit", "-q", "-m", "travail local")
        git(self.projet, "checkout", "-q", "main")
        avant = git(self.projet, "rev-parse", f"refs/heads/{self.ref}").decode().strip()
        self.servir()
        with self.assertRaises(sa.RefusRecuperation) as r:
            self.recuperer()
        self.assertIn("divergé", str(r.exception))
        self.assertEqual(git(self.projet, "rev-parse", f"refs/heads/{self.ref}").decode().strip(), avant)
        # une branche locale en retard (ancêtre du résultat) est avancée
        git(self.projet, "branch", "-f", self.ref, self.base)
        self.assertEqual(self.recuperer()["branche"], self.ref)
        self.assertEqual(git(self.projet, "rev-parse", f"refs/heads/{self.ref}").decode().strip(), self.tete)

    def test_recuperer_branche_extraite_message_clair(self):
        git(self.projet, "checkout", "-q", "-b", self.ref, self.base)
        self.servir()
        with self.assertRaises(sa.RefusRecuperation) as r:
            self.recuperer()
        self.assertIn("extraite", str(r.exception))
        self.assertNotIn("divergé", str(r.exception))
        self.assertEqual(git(self.projet, "rev-parse", f"refs/heads/{self.ref}").decode().strip(), self.base)

    def test_recuperer_fin_json_hostile_refuse(self):
        hostiles = {"base": self.fin(base="b" * 40), "branche": self.fin(branche="agent/autre"),
                    "branche main": self.fin(branche="main"), "commits texte": self.fin(commits="1"),
                    "commits négatif": self.fin(commits=-1), "code absent": b'{"commits":1}', "liste": b"[]",
                    "pas du JSON": b"\xff\xfe", "code booléen": self.fin(code=True),
                    "branche absente avec commits": self.fin(branche=None)}
        for nom, fin in hostiles.items():
            self.servir(fin=fin)
            with self.assertRaises(sa.RefusRecuperation, msg=nom):
                self.recuperer()
        self.assertFalse(any(b.startswith(f"refs/heads/{self.ref}") for b in self.branches()))

    def test_recuperer_bornes_de_taille(self):
        self.servir()
        with mock.patch.dict(sa.LIMITES_AGENT, {"flux_octets": 5}):
            with self.assertRaises(sa.RefusRecuperation):
                self.recuperer()
        with mock.patch.dict(sa.LIMITES_AGENT, {"paquet_octets": 50}):
            with self.assertRaises(sa.RefusRecuperation):
                self.recuperer()
        # un serveur qui renverrait plus que le plafond demandé est refusé aussi
        with mock.patch.object(self.srv, "_fichier", lambda args, script, entree: (0, b"x" * 10_000, "")):
            with self.assertRaises(sa.RefusRecuperation):
                with mock.patch.dict(sa.LIMITES_AGENT, {"flux_octets": 100}):
                    self.recuperer()
        self.assertFalse(any(b.startswith(f"refs/heads/{self.ref}") for b in self.branches()))

    def test_recuperer_exige_une_fiche_d_agent(self):
        st.Index(self.dossier).enregistrer("t20261120-101800-1111", {"etat": "terminee", "serveur_id": "ovh1"})
        with self.assertRaises(sa.RefusRecuperation):
            sa.recuperer("t20261120-101800-1111", self.projet, dossier=self.dossier, ssh=self.srv)
        with self.assertRaises(sa.RefusRecuperation):
            sa.recuperer("t20261120-101900-2222", self.projet, dossier=self.dossier, ssh=self.srv)
        with self.assertRaises(ValueError):
            sa.recuperer("../x", self.projet, dossier=self.dossier, ssh=self.srv)

    def test_script_de_fichier_borne_par_la_taille_apparente(self):
        self.servir()
        self.recuperer()
        script = self.srv.ops("fichier")[0][1]
        for attendu in ("-type f", "-links 1", "! -L", "-size -", "pwd -P", "head -c"):
            self.assertIn(attendu, script.replace("[ ! -L", "! -L"))
        self.assertNotIn("pont", script)
        self.assertNotIn("travail", script)


if __name__ == "__main__":
    unittest.main()
