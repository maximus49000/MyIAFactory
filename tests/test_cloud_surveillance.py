"""Le surveillant des commandes figées d'une session cloud (`outils/cloud/surveillance.py`) : des listes de processus
injectées (pas de vrai `/proc` sous Windows), jamais un vrai processus arrêté."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCRIPT = RACINE / "outils" / "cloud" / "surveillance.py"
_spec = importlib.util.spec_from_file_location("surveillance_cloud", SCRIPT)
surveillance = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(surveillance)

T0 = 1_000_000.0
UID = 1000


def proc(pid, parent, nom, cpu, cree, cmd="", uid=UID):
    return {"pid": pid, "parent": parent, "nom": nom, "cpu": cpu, "debut": int(cree * 100), "cree": cree,
            "cmd": cmd, "uid": uid}


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.projet = Path(self._t.name)
        self.maintenant = T0
        self.tues = []
        self.procs = {}

    def ajouter(self, *ps):
        for p in ps:
            self.procs[p["pid"]] = p

    def tuer(self, p, descendants):
        self.tues.append(p["pid"])
        for pid in [p["pid"], *descendants]:
            self.procs.pop(pid, None)
        return True

    def surveillant(self, lister=None):
        return surveillance.Surveillant(self.projet, fige_s=300, tuer=self.tuer, horloge=lambda: self.maintenant,
                                        moi=50, uid=UID,
                                        lister=lister or (lambda: {k: dict(v) for k, v in self.procs.items()}))

    def passer(self, s, apres_s=0):
        self.maintenant += apres_s
        return s.passer()

    def session(self):
        """init (1) → sh du hook → surveillant (50) ; claude (100) → bash (200) → python (300) → godot (400) ;
        claude → node (150, un serveur MCP)."""
        self.ajouter(proc(1, 0, "init", 1.0, T0 - 9000, uid=0),
                     proc(50, 1, "python3", 0.5, T0 - 3000, "python3 .claude/cloud/surveillance.py"),
                     proc(100, 1, "claude", 80.0, T0 - 3000, "claude --print"),
                     proc(150, 100, "node", 1.0, T0 - 2990, "node mcp.js"),
                     proc(200, 100, "bash", 0.1, T0 - 60, "bash -c python tools/lancer_tests.py"),
                     proc(300, 200, "python3", 0.3, T0 - 59, "python3 tools/lancer_tests.py"),
                     proc(400, 300, "godot", 2.0, T0 - 58, "godot --headless --script res://tests/lanceur.gd"))

    def lignes(self):
        f = self.projet / ".factory" / "rapports" / "commandes-figees.jsonl"
        return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


class Surveillant(Base):
    def test_le_programme_fige_est_arrete_et_note(self):
        self.session()
        s = self.surveillant()
        self.assertEqual(self.passer(s), [])
        self.assertEqual(self.passer(s, 200), [])
        arrets = self.passer(s, 101)
        self.assertEqual([a["programme"] for a in arrets], ["godot"])
        self.assertEqual(self.tues, [400])
        (ligne,) = self.lignes()
        self.assertEqual((ligne["programme"], ligne["immobile_min"]), ("godot", 5.0))
        self.assertTrue(ligne["commande"].startswith("godot --headless"))
        self.assertIn("heure", ligne)

    def test_un_programme_actif_est_epargne(self):
        self.session()
        s = self.surveillant()
        for _ in range(10):
            self.procs[400]["cpu"] += 1
            self.assertEqual(self.passer(s, 60), [])
        self.assertEqual((self.tues, self.lignes()), ([], []))

    def test_les_proteges_ne_sont_jamais_touches(self):
        """Ni claude, ni son serveur MCP (pas sous un shell), ni le surveillant, ni un shell sans enfant."""
        self.ajouter(proc(1, 0, "init", 1.0, T0 - 9000, uid=0),
                     proc(50, 100, "python3", 0.5, T0 - 3000, "python3 .claude/cloud/surveillance.py"),
                     proc(100, 1, "node", 80.0, T0 - 3000, "node /usr/lib/node_modules/@anthropic-ai/claude-code/cli.js"),
                     proc(150, 100, "node", 1.0, T0 - 2990, "node mcp.js"),
                     proc(200, 100, "bash", 0.1, T0 - 60, "bash"),
                     proc(600, 1, "dockerd", 1.0, T0 - 8000, "dockerd", uid=0),
                     proc(700, 1, "sleep", 0.0, T0 - 10, "sleep 1000", uid=0))
        s = self.surveillant()
        for _ in range(10):
            self.passer(s, 120)
        self.assertEqual(self.tues, [])

    def test_sans_claude_visible_les_processus_de_l_utilisateur_nes_apres_le_surveillant(self):
        self.ajouter(proc(1, 0, "init", 1.0, T0 - 9000, uid=0),
                     proc(50, 1, "python3", 0.5, T0 - 3000, "python3 surveillance.py"),
                     proc(60, 1, "sleep", 0.0, T0 - 4000, "sleep 99999"),           # avant le surveillant : épargné
                     proc(70, 1, "godot", 2.0, T0 - 100, "godot --headless"),
                     proc(80, 1, "godot", 2.0, T0 - 100, "godot --headless", uid=0))  # un autre utilisateur
        s = self.surveillant()
        self.passer(s)
        self.assertEqual([a["programme"] for a in self.passer(s, 301)], ["godot"])
        self.assertEqual(self.tues, [70])

    def test_une_mesure_impossible_ne_fait_rien(self):
        self.session()
        for lister in (lambda: None, lambda: {}, lambda: (_ for _ in ()).throw(OSError("non"))):
            s = self.surveillant(lister=lister)
            self.assertEqual(self.passer(s), [])
            self.assertEqual(self.passer(s, 1000), [])
        self.assertEqual((self.tues, self.lignes()), ([], []))

    def test_proc_illisible(self):
        self.assertIsNone(surveillance.lister_linux(str(self.projet / "absent")))

    def test_lecture_de_proc(self):
        """Un faux `/proc` : stat (nom entre parenthèses, parent, utime + stime), cmdline, btime."""
        racine = self.projet / "proc"
        (racine / "42").mkdir(parents=True)
        (racine / "stat").write_text("cpu  1 2 3\nbtime 1000000\n", encoding="utf-8")
        champs = ["S", "7"] + ["0"] * 9 + ["150", "50"] + ["0"] * 6 + ["2500"]
        (racine / "42" / "stat").write_text(f"42 (godot (v4)) {' '.join(champs)} 0 0\n", encoding="utf-8")
        (racine / "42" / "cmdline").write_bytes(b"godot\0--headless\0")
        p = surveillance.lister_linux(str(racine))[42]
        self.assertEqual((p["nom"], p["parent"], p["cpu"], p["debut"], p["cmd"]),
                         ("godot (v4)", 7, 200, 2500, "godot --headless"))
        self.assertAlmostEqual(p["cree"], 1000000 + 2500 / surveillance.figes._tic(), places=3)

    def test_hors_linux_le_script_ne_fait_rien(self):
        if Path("/proc/self/stat").exists():
            self.skipTest("Linux : le script surveillerait pour de vrai")
        p = subprocess.run([sys.executable, str(SCRIPT), "--projet", str(self.projet), "--une-fois"],
                           capture_output=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.lignes(), [])

    def test_l_agent_cloud_est_invite_a_dire_les_arrets(self):
        from orchestrateur import depart
        self.assertIn(".factory/rapports/commandes-figees.jsonl", depart.fin_cloud("t1"))

    def test_le_script_trouve_figes_a_cote_de_lui(self):
        """La copie dans un projet : `.claude/cloud/surveillance.py` et `figes.py` côte à côte."""
        d = self.projet / ".claude" / "cloud"
        d.mkdir(parents=True)
        shutil.copy(SCRIPT, d / "surveillance.py")
        shutil.copy(RACINE / "moteur" / "figes.py", d / "figes.py")
        p = subprocess.run([sys.executable, "-c", "import runpy, sys; sys.argv = ['s', '--une-fois']; "
                            f"runpy.run_path({str(d / 'surveillance.py')!r}, run_name='x')"],
                           capture_output=True, timeout=60, cwd=str(self.projet))
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == "__main__":
    unittest.main()
