"""Pont hôte (`serveur_ovh/taches/pont_hote.py`) et commande `pont` de l'agent (`serveur_ovh/images/agent/pont`).

Le cœur du pont hôte est une fonction pure, `traiter_requete(ligne, contexte) -> bytes` : ces tests l'exercent directement,
avec un faux exécuteur (il joue `sudo -n docker exec` et `lancer_emulation.sh`, écrit ce que l'émulation écrirait dans
`~/taches/<emu>/sortie`) et un HOME jetable ; ils tournent donc aussi sous Windows. Seuls les tests de la vraie socket Unix
(boucle `servir`, processus réel arrêté par SIGTERM) exigent `AF_UNIX` : ignorés sous Windows (le Python de Windows n'a pas
`socket.AF_UNIX`), ils tournent sur Linux, par exemple sur le serveur ou dans WSL."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import serveur_tache as st  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent / "serveur_ovh"
TACHES = RACINE / "taches"
PONT_HOTE = TACHES / "pont_hote.py"
CLIENT = RACINE / "images" / "agent" / "pont"
ID = "t20261120-101500-ab12"
APK = b"PK\x03\x04apk-de-l-agent"
PNG = b"\x89PNG\r\n\x1a\n" + b"image" * 20
MOTIF_ID = re.compile(r"t[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", re.ASCII)
CLES = {"ok", "verbe", "code", "detail"}
SANS_PONT = "pas de pont : tâche en mode seul"


def charger(chemin, nom):
    """Module chargé depuis un fichier (le client n'a pas d'extension), sans __pycache__ dans serveur_ovh."""
    chargeur = importlib.machinery.SourceFileLoader(nom, str(chemin))
    spec = importlib.util.spec_from_loader(nom, chargeur)
    module = importlib.util.module_from_spec(spec)
    avant, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        chargeur.exec_module(module)
    finally:
        sys.dont_write_bytecode = avant
    return module


PH = charger(PONT_HOTE, "pont_hote")


def ligne_pont(verbe, detail, ok=True):
    """La ligne JSON que rend pont.sh dans le conteneur d'émulation."""
    return (json.dumps({"ok": ok, "verbe": verbe, "detail": detail}, ensure_ascii=False) + "\n").encode("utf-8")


class FauxExecuteur:
    """Joue `bash lancer_emulation.sh <emu> pilote` (état et .avd-pret écrits comme l'enveloppe et le conteneur) et
    `sudo -n docker exec tache-<emu> /usr/local/bin/pont <verbe> ...` (actions par verbe, sinon « fait »)."""

    def __init__(self, banc):
        self.b = banc
        self.appels = []
        self.codes_lancer = []
        self.actions = {}

    def __call__(self, argv, delai, env, nouvelle_session=False):
        self.appels.append({"argv": list(argv), "delai": delai, "env": dict(env), "session": nouvelle_session})
        if argv[0] == "bash":
            emu = argv[2]
            d = self.b.taches / emu
            code = self.codes_lancer.pop(0) if self.codes_lancer else 0
            code, etat = code if isinstance(code, tuple) else (code, {0: "en_cours", 75: "en_attente"}.get(code, "echouee"))
            (d / "sortie").mkdir(parents=True, exist_ok=True)
            texte = json.dumps({"id": emu, "etat": etat, "statut": None, "debut": None, "fin": None, "raison": "r"})
            (d / "etat.json").write_text(texte + "\n", encoding="utf-8")
            if code == 0:
                (d / "sortie" / ".avd-pret").write_text("", encoding="utf-8")
            return code, (texte + "\n").encode("utf-8")
        assert argv[:4] == ["sudo", "-n", "docker", "exec"], argv
        emu, verbe, args = argv[4][len("tache-"):], argv[6], argv[7:]
        action = self.actions.get(verbe)
        if action:
            return action(self.b.taches / emu / "sortie", args)
        return 0, ligne_pont(verbe, f"{verbe} fait.")

    def lancements(self):
        return [a for a in self.appels if a["argv"][0] == "bash"]

    def execs(self):
        return [a for a in self.appels if a["argv"][0] == "sudo"]


class Banc:
    """HOME jetable : ~/taches/<ID>/{entree/app.apk, pont/, outil/} comme les laisse lancer_agent.sh en mode pilote."""

    def __enter__(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.t = Path(self._t.name)
        self.home = self.t / "home"
        self.taches = self.home / "taches"
        self.dossier = self.taches / ID
        (self.dossier / "entree").mkdir(parents=True)
        (self.dossier / "entree" / "app.apk").write_bytes(APK)
        (self.dossier / "pont").mkdir()
        (self.dossier / "outil").mkdir()
        self.faux = FauxExecuteur(self)
        self.ctx = PH.Contexte(ID, str(self.home), str(TACHES), executer=self.faux, dormir=lambda s: None)
        return self

    def __exit__(self, *a):
        self._t.cleanup()

    def requete(self, requete):
        ligne = requete if isinstance(requete, bytes) else json.dumps(requete, ensure_ascii=False).encode("utf-8")
        r = PH.traiter_requete(ligne, self.ctx)
        assert isinstance(r, bytes) and r.endswith(b"\n") and r.count(b"\n") == 1, r
        d = json.loads(r)
        assert set(d) == CLES, d
        assert isinstance(d["code"], int) and isinstance(d["detail"], str) and isinstance(d["verbe"], str), d
        assert d["ok"] is (d["code"] == 0), d
        return d["code"], d

    def appel(self, verbe, *args):
        return self.requete({"verbe": verbe, "args": list(args)})

    def emulations(self):
        return sorted(p.name for p in self.taches.iterdir() if p.name != ID and not p.name.startswith("."))

    def outil(self):
        return sorted(p.relative_to(self.dossier / "outil").as_posix() for p in (self.dossier / "outil").rglob("*")
                      if p.is_file())

    def journal(self):
        f = self.dossier / "pont-hote.log"
        return f.read_text(encoding="utf-8") if f.exists() else ""


class TestRequetes(unittest.TestCase):
    def test_requete_hostile_refusee_sans_rien_executer(self):
        hostiles = [
            {"verbe": ";", "args": []},
            {"verbe": "toucher", "args": ["$(x)", "1"]},
            {"verbe": "toucher", "args": ["1;reboot", "2"]},
            {"verbe": "texte", "args": ["a\nb"]},
            {"verbe": "capturer", "args": [".."]},
            {"verbe": "capturer", "args": ["../x"]},
            {"verbe": "capturer", "args": ["con"]},
            {"verbe": "toucher", "args": "1 2"},                 # args non liste
            {"verbe": "toucher", "args": [1, 2]},                # types faux
            {"verbe": ["toucher"], "args": []},
            {"verbe": "toucher"},
            {"args": []},
            {"verbe": "toucher", "args": ["1", "2"], "env": {"PONT_SORTIE": "/"}},
            {"verbe": "sh", "args": ["-c", "id"]},
            {"verbe": "demarrer", "args": ["-1"]},
            {"verbe": "filmer", "args": ["demo", "181"]},
            {"verbe": "finfilm", "args": ["x"]},
            b'{"verbe": "texte", "args": ["' + b"a" * 5000 + b'"]}',              # 5 Ko
            b'{"verbe": "toucher", "verbe": "rm", "args": ["1", "2"]}',            # clé dupliquée
            b'{"verbe": "toucher", "args": ["1", "2"], "args": ["3", "4"]}',
            b'["toucher", "1", "2"]',
            b"pas du json",
            b"\xff\xfe",
            b"",
            b'{"verbe": "toucher", "args": ["1", "2"]}\n{"verbe": "arreter", "args": []}',
        ]
        with Banc() as b:
            self.assertEqual(b.appel("demarrer")[0], 0)          # une émulation existe : rien ne doit l'atteindre
            emus = b.emulations()
            b.faux.appels.clear()
            for h in hostiles:
                with self.subTest(requete=h if isinstance(h, dict) else h[:80]):
                    code, d = b.requete(h)
                    self.assertEqual(code, 2, d)
                    self.assertIn(d["verbe"], ("", *PH.VERBES))      # jamais le texte reçu renvoyé tel quel
            self.assertEqual(b.faux.appels, [])
            self.assertEqual(b.emulations(), emus)
            self.assertEqual(b.outil(), [])
            j = b.journal()
            for interdit in ("$(x)", "reboot", "PONT_SORTIE", "aaaaaaaaaa", " rm ", " sh ", "../x", "demo"):
                self.assertNotIn(interdit, j)
            self.assertEqual(len([x for x in j.splitlines() if x.strip()]), len(hostiles) + 1)   # une ligne par appel

    def test_premier_demarrer_cree_l_emulation(self):
        with Banc() as b:
            code, d = b.appel("toucher", "1", "2")              # avant demarrer : rien à piloter, rien lancé
            self.assertEqual(code, 4, d)
            self.assertIn("demarrer", d["detail"])
            self.assertEqual((b.faux.appels, b.emulations()), ([], []))
            code, d = b.appel("demarrer")
            self.assertEqual(code, 0, d)
            emus = b.emulations()
            self.assertEqual(len(emus), 1, emus)
            emu = emus[0]
            self.assertRegex(emu, MOTIF_ID)
            de = b.taches / emu
            brut = (de / "demande.json").read_text(encoding="utf-8")
            self.assertRegex(brut, r'"type"\s*:\s*"emulation"')               # MOTIF_TYPE_EMULATION de lancer_agent.sh
            demande = json.loads(brut)
            self.assertEqual((demande["id"], demande["type"], demande["agent"]), (emu, "emulation", ID))
            self.assertEqual((de / "agent").read_text(encoding="utf-8").splitlines()[0], ID)
            self.assertEqual((de / "entree" / "app.apk").read_bytes(), APK)
            self.assertEqual((b.dossier / "emulation").read_text(encoding="utf-8").strip(), emu)   # hôte seul
            self.assertFalse((b.dossier / "pont" / "emulation").exists())                         # jamais sous pont/
            lance = b.faux.lancements()
            self.assertEqual([a["argv"] for a in lance], [["bash", os.path.join(str(TACHES), "lancer_emulation.sh"), emu,
                                                           "pilote"]])
            self.assertTrue(lance[0]["session"])                   # hors du groupe du pont : jamais tué à demi par lui
            self.assertEqual([a["argv"] for a in b.faux.execs()],
                             [["sudo", "-n", "docker", "exec", f"tache-{emu}", "/usr/local/bin/pont", "demarrer"]])
            self.assertEqual(b.faux.appels.index(lance[0]), 0)      # l'émulation lancée avant le premier verbe
            self.assertEqual(b.appel("toucher", "10", "20")[0], 0)
            self.assertEqual(b.faux.execs()[-1]["argv"][4:], [f"tache-{emu}", "/usr/local/bin/pont", "toucher", "10", "20"])
            self.assertEqual(b.appel("demarrer")[0], 0)             # second demarrer : même émulation, relayé au pont
            self.assertEqual(b.emulations(), [emu])
            self.assertEqual(len(b.faux.lancements()), 1)

    def test_creneau_emulation_occupe_donne_4(self):
        with Banc() as b:
            b.faux.codes_lancer = [75]
            code, d = b.appel("demarrer")
            self.assertEqual(code, 4, d)
            self.assertEqual(d["detail"], "créneau d'émulation occupé, réessaie plus tard")
            self.assertEqual(PH.MESSAGE_OCCUPE, d["detail"])
            self.assertEqual(b.faux.execs(), [])
            emus = b.emulations()
            self.assertEqual(len(emus), 1)
            code, d = b.appel("demarrer")                           # créneau libre : la même tâche d'émulation relancée
            self.assertEqual(code, 0, d)
            self.assertEqual(b.emulations(), emus)
            self.assertEqual([a["argv"][2] for a in b.faux.lancements()], emus * 2)
        with Banc() as b:                                            # autre échec du lancement : 4 avec sa raison
            b.faux.codes_lancer = [1]
            code, d = b.appel("demarrer")
            self.assertEqual(code, 4, d)
            self.assertEqual(b.faux.execs(), [])

    def test_docker_exec_en_tableau_sans_shell_ni_env(self):
        self.assertEqual(dict(PH.DELAIS_VERBE_S), dict(st.DELAIS_VERBE_S))
        self.assertEqual(PH.DELAI_VERBE_S, st.DELAI_VERBE_S)
        with mock.patch.dict(os.environ, {"SECRET_DU_POSTE": "cle-42", "PONT_SORTIE": "/"}), Banc() as b:
            self.assertEqual(b.appel("demarrer")[0], 0)
            for verbe, args in (("toucher", ["1", "2"]), ("texte", ["un deux"]), ("attendre", ["3"]), ("finfilm", []),
                                ("capturer", ["a"]), ("journal", []), ("arreter", [])):
                self.assertIn(b.appel(verbe, *args)[0], (0, 4))
            for a in b.faux.execs():
                with self.subTest(argv=a["argv"]):
                    self.assertTrue(all(isinstance(x, str) for x in a["argv"]))
                    self.assertNotIn("-e", a["argv"])
                    self.assertEqual(a["env"], dict(PH.ENV_FIXE))
                    self.assertEqual(a["delai"], st.DELAIS_VERBE_S.get(a["argv"][6], st.DELAI_VERBE_S))
            self.assertEqual(b.faux.lancements()[0]["env"], {**PH.ENV_FIXE, "HOME": str(b.home)})
        self.assertEqual(set(PH.ENV_FIXE), {"PATH", "LC_ALL"})
        # l'exécuteur réel : Popen avec un tableau, sans shell, l'environnement donné et rien d'autre
        vus = []

        class FauxPopen:
            def __init__(self, args, **kw):
                vus.append((args, kw))
                self.returncode = 0
                self.pid = 4242
                self.stdout = io.BytesIO(ligne_pont("toucher", "ok"))

            def communicate(self, timeout=None):
                return ligne_pont("toucher", "ok"), b""

            def kill(self):
                pass

            def wait(self, timeout=None):
                return 0

        argv = ["sudo", "-n", "docker", "exec", "tache-x", "/usr/local/bin/pont", "toucher", "1", "2"]
        with mock.patch.object(PH.subprocess, "Popen", FauxPopen):
            code, sortie = PH.executer(argv, 90, dict(PH.ENV_FIXE))
        self.assertEqual((code, json.loads(sortie)["detail"]), (0, "ok"))
        (args, kw), = vus
        self.assertEqual(args, argv)
        self.assertFalse(kw.get("shell", False))
        self.assertEqual(kw["env"], dict(PH.ENV_FIXE))
        self.assertEqual(kw.get("stdin"), subprocess.DEVNULL)
        source = PONT_HOTE.read_text(encoding="utf-8")
        for interdit in ("shell=True", "os.system", "os.popen", "eval(", "exec("):
            self.assertNotIn(interdit, source)

    def test_capture_copiee_sans_suivre_un_lien(self):
        def capture(sortie, args):
            f = sortie / "captures" / f"{args[0]}.png"
            if not os.path.lexists(f):
                f.parent.mkdir(exist_ok=True)
                f.write_bytes(PNG)
            return 0, ligne_pont("capturer", f"captures/{args[0]}.png ({len(PNG)} octets).")

        with Banc() as b:
            b.faux.actions["capturer"] = capture
            self.assertEqual(b.appel("demarrer")[0], 0)
            sortie = b.taches / b.emulations()[0] / "sortie"
            code, d = b.appel("capturer", "a")
            self.assertEqual(code, 0, d)
            self.assertEqual((b.dossier / "outil" / "captures" / "a.png").read_bytes(), PNG)
            self.assertIn("/outil/captures/a.png", d["detail"])
            secret = b.home / "secret.txt"
            secret.write_bytes(b"SECRET-DE-L-HOTE")
            (sortie / "captures").mkdir(exist_ok=True)
            os.link(secret, sortie / "captures" / "c.png")                 # lien dur : jamais copié
            code, d = b.appel("capturer", "c")
            self.assertEqual(code, 0, d)
            self.assertNotIn("/outil/captures/c.png", d["detail"])
            self.assertIn("non copiée", d["detail"])
            try:
                os.symlink(secret, sortie / "captures" / "b.png")
            except OSError:
                self.skipTest("liens symboliques indisponibles sur ce poste")
            code, d = b.appel("capturer", "b")
            self.assertEqual(code, 0, d)                                    # le verbe a eu lieu ; la copie, non
            self.assertNotIn("/outil/captures/b.png", d["detail"])
            self.assertEqual(b.outil(), ["captures/a.png"])
            for f in (b.dossier / "outil").rglob("*"):
                if f.is_file():
                    self.assertNotIn(b"SECRET", f.read_bytes())
        source = PONT_HOTE.read_text(encoding="utf-8")
        for attendu in ("O_NOFOLLOW", "O_EXCL", "O_CREAT"):
            self.assertIn(attendu, source)

    def test_journal_et_film_copies_et_bornes(self):
        def journal(sortie, args):
            with open(sortie / "logcat.txt", "ab") as f:
                f.write(b"# journal - 2026\nI Test: ligne\n")
            return 0, ligne_pont("journal", "I Test: ligne")

        def finfilm(sortie, args):
            v = sortie / "videos"
            (v / "demo-img").mkdir(parents=True, exist_ok=True)
            (v / "demo.mp4").write_bytes(b"\0\0\0\x18ftypisom" + b"\0" * 50)
            for i in (1, 2):
                (v / "demo-img" / f"demo-00{i}.png").write_bytes(PNG)
            (v / "demo-img" / "intrus.sh").write_bytes(b"#!/bin/sh\n")
            return 0, ligne_pont("finfilm", "videos/demo.mp4 (62 octets, 3 s, 2 images).")

        with Banc() as b:
            b.faux.actions.update(journal=journal, finfilm=finfilm)
            self.assertEqual(b.appel("demarrer")[0], 0)
            code, d = b.appel("journal")
            self.assertEqual(code, 0, d)
            self.assertTrue(d["detail"].startswith("I Test: ligne"))
            self.assertIn("/outil/logcat.txt", d["detail"])
            self.assertEqual(b.appel("journal", "Test")[0], 0)                # remplacé, jamais refusé comme déjà pris
            self.assertEqual((b.dossier / "outil" / "logcat.txt").read_bytes().count(b"# journal"), 2)
            code, d = b.appel("finfilm")
            self.assertEqual(code, 0, d)
            self.assertIn("/outil/videos/demo.mp4", d["detail"])
            self.assertEqual(b.outil(), ["logcat.txt", "videos/demo-img/demo-001.png", "videos/demo-img/demo-002.png",
                                         "videos/demo.mp4"])
        with Banc() as b, mock.patch.object(PH, "MEDIA_MAX_OCTETS", 10):  # au-delà de la borne : jamais copié
            b.faux.actions["finfilm"] = finfilm
            self.assertEqual(b.appel("demarrer")[0], 0)
            self.assertEqual(b.appel("finfilm")[0], 0)
            self.assertEqual(b.outil(), [])

    def test_limite_d_appels(self):
        self.assertEqual(PH.APPELS_MAX, 2000)
        with Banc() as b:
            self.assertEqual(b.appel("demarrer")[0], 0)
            for _ in range(PH.APPELS_MAX - 1):                               # les refus comptent aussi
                PH.traiter_requete(b"x", b.ctx)
            n = len(b.faux.appels)
            code, d = b.appel("toucher", "1", "2")
            self.assertEqual(code, 3, d)
            self.assertIn("2000", d["detail"])
            self.assertEqual(len(b.faux.appels), n)                           # rien exécuté

    def test_fin_du_pont_arrete_l_emulation(self):
        with Banc() as b:
            self.assertEqual(b.appel("demarrer")[0], 0)
            emu = b.emulations()[0]
            b.ctx.fin()
            self.assertEqual((b.taches / emu / "arret").read_text(encoding="utf-8").strip(), "fin")
        with Banc() as b:                                                    # aucune émulation : rien créé
            b.ctx.fin()
            self.assertEqual(b.emulations(), [])
        with Banc() as b:                                                    # arreter : pont puis « arret : fin »
            self.assertEqual(b.appel("demarrer")[0], 0)
            premiere = b.emulations()[0]
            self.assertEqual(b.appel("arreter")[0], 0)
            self.assertEqual(b.faux.execs()[-1]["argv"][-1], "arreter")
            self.assertEqual((b.taches / premiere / "arret").read_text(encoding="utf-8").strip(), "fin")
            self.assertEqual(b.appel("toucher", "1", "2")[0], 4)              # plus d'émulation à piloter
            self.assertEqual(b.appel("demarrer")[0], 0)                       # une nouvelle, à la demande
            self.assertEqual(len(b.emulations()), 2)
            self.assertEqual((b.dossier / "emulation").read_text(encoding="utf-8").strip(),
                             [e for e in b.emulations() if e != premiere][0])


class TestCorrectifs(unittest.TestCase):
    """Revue de la tâche 7 (tour 1) : disque borné (I1), arrêts sûrs, réponses et lectures bornées."""

    def test_limite_d_emulations_et_apk_precedent_retire(self):
        self.assertEqual(PH.EMULATIONS_MAX, 5)
        with Banc() as b:
            vues = []
            for i in range(5):
                code, d = b.appel("demarrer")
                self.assertEqual(code, 0, d)
                emu = (b.dossier / "emulation").read_text(encoding="utf-8").strip()
                vues.append(emu)
                for ancienne in vues[:-1]:                                  # disque rendu : APK des précédentes retiré
                    self.assertFalse((b.taches / ancienne / "entree" / "app.apk").exists(), ancienne)
                self.assertTrue((b.taches / emu / "entree" / "app.apk").exists())
                self.assertEqual(b.appel("arreter")[0], 0)
            code, d = b.appel("demarrer")
            self.assertEqual(code, 4, d)
            self.assertIn("limite d'émulations", d["detail"].lower())
            self.assertEqual(len(b.emulations()), 5)
            self.assertEqual(len(b.faux.lancements()), 5)

    def test_lancement_refuse_sans_nouveau_dossier(self):
        # refus définitifs : argument refusé (2) ; émulation liée refusée, agent fini ou arrêt demandé (1, « arretee »)
        for code_lancer in (2, (1, "arretee")):
            with self.subTest(code=code_lancer), Banc() as b:
                b.faux.codes_lancer = [code_lancer]
                self.assertEqual(b.appel("demarrer")[0], 4)
                emus = b.emulations()
                self.assertEqual(len(emus), 1)
                self.assertEqual((b.taches / emus[0] / "arret").read_text(encoding="utf-8").strip(), "fin")
                for _ in range(3):                                        # une boucle d'essais ne crée rien
                    code, d = b.appel("demarrer")
                    self.assertEqual(code, 4, d)
                self.assertEqual(b.emulations(), emus)
                self.assertEqual(len(b.faux.lancements()), 1)

    def test_dossier_d_emulation_a_demi_ecrit_retire_et_compte(self):
        vrai = PH._ecrire_atomique

        def casse(chemin, donnees, mode=0o600):
            if os.path.basename(chemin) == "demande.json":
                raise OSError("disque plein")
            return vrai(chemin, donnees, mode)

        with Banc() as b:
            with mock.patch.object(PH, "_ecrire_atomique", casse):
                code, d = b.appel("demarrer")
            self.assertEqual(code, 4, d)
            self.assertEqual(b.emulations(), [])                         # rien de laissé à demi sur le disque
            self.assertEqual(b.ctx.emulations, 1)                        # mais compté dans la limite
            self.assertFalse((b.dossier / "emulation").exists())
            self.assertEqual(b.faux.lancements(), [])
            self.assertEqual(b.appel("demarrer")[0], 0)                  # passager : la suivante est créée
            self.assertEqual((b.ctx.emulations, len(b.emulations())), (2, 1))

    def test_echec_inattendu_arrete_puis_une_neuve(self):
        # code 1 « echouee » (docker run en échec, créneau inaccessible) : passager, jamais définitif
        for code_lancer in (9, None, 1):
            with self.subTest(code=code_lancer), Banc() as b:
                b.faux.codes_lancer = [code_lancer]
                self.assertEqual(b.appel("demarrer")[0], 4)
                premiere = b.emulations()[0]
                self.assertEqual((b.taches / premiere / "arret").read_text(encoding="utf-8").strip(), "fin")
                self.assertEqual(b.appel("demarrer")[0], 0)
                self.assertEqual(len(b.emulations()), 2)

    def test_requete_rembourree_et_cle_verbe_doublee(self):
        with Banc() as b:
            valide = b'{"verbe": "toucher", "args": ["1", "2"]}'
            self.assertEqual(b.requete(valide)[0], 4)                     # valide (pas d'émulation : 4, pas 2)
            code, d = b.requete(valide + b" " * (PH.REQUETE_MAX - len(valide) + 1))   # JSON valide, mais 4097 octets
            self.assertEqual(code, 2, d)
            code, d = b.requete(b'{"verbe": "toucher", "verbe": "toucher", "args": ["1", "2"]}')
            self.assertEqual(code, 2, d)
            self.assertEqual(b.faux.appels, [])

    def test_reponse_bornee_en_octets(self):
        ligne = PH.reponse(0, "journal", "\x01" * 300000)                # 6 octets par caractère une fois échappé
        self.assertLessEqual(len(ligne), PH.REPONSE_OCTETS_MAX)
        self.assertEqual(json.loads(ligne)["code"], 0)

        ajout = "\n(copie : /outil/logcat.txt)"                        # détail énorme : l'ajout du pont hôte reste en fin
        ligne = PH.reponse(0, "journal", "\x01" * 300000, ajout)
        self.assertLessEqual(len(ligne), PH.REPONSE_OCTETS_MAX)
        self.assertTrue(json.loads(ligne)["detail"].endswith("\x01" + ajout))

        def surrogat(sortie, args):                                    # demi-paire UTF-16 venue du pont : jamais fatale
            return 0, b'{"ok": true, "verbe": "toucher", "detail": "a\\ud800b"}\n'

        with Banc() as b:
            b.faux.actions["toucher"] = surrogat
            self.assertEqual(b.appel("demarrer")[0], 0)
            code, d = b.appel("toucher", "1", "2")
            self.assertEqual((code, d["detail"]), (0, "a?b"))
            self.assertEqual(b.appel("attendre", "1")[0], 0)
        client = charger(CLIENT, "pont_client")
        self.assertLessEqual(PH.REPONSE_OCTETS_MAX, client.REPONSE_MAX)

    def test_exception_inattendue_code_4_et_le_pont_continue(self):
        def casse(sortie, args):
            raise RuntimeError("réponse inattendue")

        with Banc() as b:
            self.assertEqual(b.appel("demarrer")[0], 0)
            b.faux.actions["toucher"] = casse
            try:
                code, d = b.appel("toucher", "1", "2")
            except RuntimeError:
                self.fail("une réponse inattendue a fait tomber le pont")
            self.assertEqual(code, 4, d)
            self.assertEqual(b.appel("attendre", "1")[0], 0)

    def test_executer_borne_la_sortie_et_arrete_en_deux_temps(self):
        gestes = []

        class FauxPopen:
            sortie = b"x" * (5 * 1024 * 1024)
            bloque = False

            def __init__(self, args, **kw):
                self.returncode = None
                self.stdout = io.BytesIO(FauxPopen.sortie)

            def communicate(self, timeout=None):
                if FauxPopen.bloque:
                    raise subprocess.TimeoutExpired("x", timeout)
                self.returncode = 0
                return FauxPopen.sortie, b""

            def wait(self, timeout=None):
                gestes.append(("wait", timeout))
                if FauxPopen.bloque and timeout is not None:              # ne part qu'au SIGKILL
                    raise subprocess.TimeoutExpired("x", timeout)
                self.returncode = -9 if FauxPopen.bloque else 0
                return self.returncode

            def terminate(self):
                gestes.append(("terminate", None))

            def kill(self):
                gestes.append(("kill", None))

        with mock.patch.object(PH.subprocess, "Popen", FauxPopen):
            code, sortie = PH.executer(["sudo", "x"], 90, dict(PH.ENV_FIXE))
            self.assertEqual(code, 0)
            self.assertLessEqual(len(sortie), PH.SORTIE_MAX_OCTETS)
            FauxPopen.bloque = True
            gestes.clear()
            code, _s = PH.executer(["sudo", "x"], 90, dict(PH.ENV_FIXE))
        self.assertIsNone(code)
        noms = [g[0] for g in gestes]
        self.assertIn("terminate", noms)                                    # SIGTERM d'abord
        self.assertLess(noms.index("terminate"), noms.index("kill"))       # puis SIGKILL
        self.assertEqual(noms[-1], "wait")                                 # toujours attendu

    def test_lecture_d_une_requete_bornee_dans_le_temps(self):
        horloge = [0.0]

        class GoutteAGoutte:
            appels = 0

            def settimeout(self, t):
                pass

            def recv(self, n):
                GoutteAGoutte.appels += 1
                horloge[0] += 1.0                                          # une seconde par octet
                return b"a"

        try:
            ligne = PH._lire_ligne(GoutteAGoutte(), horloge=lambda: horloge[0])
        except TypeError:
            self.fail("lecture sans échéance globale")
        self.assertLessEqual(GoutteAGoutte.appels, PH.LECTURE_S + 1)
        with Banc() as b:
            self.assertEqual(b.requete(ligne)[0], 2)                      # incomplète : refusée

    def test_fin_jamais_interrompue_par_un_signal(self):
        source = PONT_HOTE.read_text(encoding="utf-8")
        fin = source[source.index("def main("):]
        bloc = fin[fin.index("finally:"):]
        for s in ("SIGTERM", "SIGINT", "SIGHUP"):
            self.assertIn(s, bloc[:bloc.index("ctx.fin()")])
        self.assertIn("SIG_IGN", bloc[:bloc.index("ctx.fin()")])


@unittest.skipUnless(hasattr(socket, "AF_UNIX") and os.name == "posix", "socket Unix : Linux seulement (ignoré sous Windows)")
class TestSocket(unittest.TestCase):
    def test_socket_droits_et_un_appel(self):
        client = charger(CLIENT, "pont_client")
        with Banc() as b:
            os.chmod(b.dossier / "pont", 0o700)
            arret = threading.Event()
            fil = threading.Thread(target=PH.servir, args=(b.ctx,), kwargs={"continuer": lambda: not arret.is_set(),
                                                                          "attente_s": 0.2}, daemon=True)
            fil.start()
            sock = b.dossier / "pont" / "pont.sock"
            fin = time.time() + 10
            while not sock.exists() and time.time() < fin:
                time.sleep(0.05)
            self.assertEqual(os.stat(sock).st_mode & 0o777, 0o600)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = client.appeler(["toucher", "1", "2"], chemin=str(sock))
            self.assertEqual(code, 4)                                         # aucune émulation encore
            self.assertEqual(json.loads(out.getvalue())["code"], 4)
            arret.set()
            fil.join(timeout=10)

    def test_processus_reel_arrete_par_sigterm(self):
        with Banc() as b:
            os.chmod(b.dossier / "pont", 0o700)
            emu = "t20261120-101600-ef56"
            (b.taches / emu).mkdir()
            env = dict(os.environ, HOME=str(b.home))
            p = subprocess.Popen([sys.executable, "-I", str(PONT_HOTE), ID], env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            sock = b.dossier / "pont" / "pont.sock"
            fin = time.time() + 10
            while not sock.exists() and time.time() < fin:
                time.sleep(0.05)
            self.assertTrue(sock.exists())
            p.send_signal(signal.SIGTERM)
            self.assertEqual(p.wait(timeout=10), 0)
            self.assertFalse(sock.exists())


class TestClient(unittest.TestCase):
    def test_client_sans_socket_code_4(self):
        self.assertTrue(CLIENT.read_bytes().startswith(b"#!/usr/bin/env python3\n"))
        self.assertNotIn(b"\r", CLIENT.read_bytes())
        with tempfile.TemporaryDirectory() as t:
            # dossier du pont absent : mode seul ; dossier présent sans socket : pont pas encore prêt
            for chemin, attendu in ((Path(t) / "pas-de-pont" / "pont.sock", SANS_PONT),
                                    (Path(t) / "absente.sock", "pont pas encore prêt : réessaie dans quelques secondes")):
                with self.subTest(chemin=chemin.name):
                    env = dict(os.environ, PONT_SOCKET=str(chemin))
                    r = subprocess.run([sys.executable, str(CLIENT), "toucher", "1", "2"], env=env, capture_output=True,
                                       text=True, encoding="utf-8", timeout=60, stdin=subprocess.DEVNULL)
                    self.assertEqual(r.returncode, 4, r.stderr)
                    lignes = [x for x in r.stdout.splitlines() if x.strip()]
                    self.assertEqual(len(lignes), 1, r.stdout)
                    d = json.loads(lignes[0])
                    self.assertEqual(set(d), CLES)
                    self.assertEqual((d["ok"], d["code"], d["detail"]), (False, 4, attendu))

    def test_client_argument_non_encodable_code_2(self):
        client = charger(CLIENT, "pont_client")
        connexions = []
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                rc = client.appeler(["texte", "a\ud800b"], connecter=lambda: connexions.append(1))
            except UnicodeEncodeError:
                self.fail("UnicodeEncodeError non rattrapée")
        self.assertEqual(rc, 2)
        self.assertEqual(connexions, [])
        self.assertEqual(json.loads(out.getvalue())["code"], 2)

    def test_client_rend_le_code_du_pont(self):
        client = charger(CLIENT, "pont_client")
        for code, reponse in ((0, None), (2, None), (3, None), (4, None), (4, b"pas du json\n"),
                              (4, b'{"ok": true, "verbe": "capturer", "code": 99, "detail": "x"}\n')):
            with self.subTest(code=code, reponse=reponse):
                a, b = socket.socketpair()
                recu = []

                def servir():
                    donnees = b""
                    while not donnees.endswith(b"\n"):
                        morceau = b.recv(4096)
                        if not morceau:
                            break
                        donnees += morceau
                    recu.append(donnees)
                    b.sendall(reponse or (json.dumps({"ok": code == 0, "verbe": "capturer", "code": code,
                                                      "detail": "d"}) + "\n").encode())
                    b.close()

                fil = threading.Thread(target=servir, daemon=True)
                fil.start()
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = client.appeler(["capturer", "a"], connecter=lambda: a)
                fil.join(timeout=10)
                self.assertEqual(rc, code)
                self.assertEqual(json.loads(recu[0]), {"verbe": "capturer", "args": ["a"]})
                d = json.loads(out.getvalue())
                self.assertEqual(set(d), CLES)
                self.assertEqual((d["code"], d["ok"]), (code, code == 0))


if __name__ == "__main__":
    unittest.main()
