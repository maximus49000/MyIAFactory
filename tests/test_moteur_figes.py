"""Les commandes figées des agents locaux : un programme lancé par un agent dont le temps processeur ne bouge plus est
arrêté (lui et ses enfants, jamais l'agent ni un processus étranger). Listes de processus injectées, puis de vrais faux
processus (de petits scripts Python qui dorment ou qui calculent), jamais un vrai programme du poste."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from moteur import figes


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


def ligne_commande(t, ident="u1", outil="Bash"):
    return {"type": "assistant", "timestamp": iso(t), "message": {"content": [
        {"type": "tool_use", "id": ident, "name": outil, "input": {"command": "python tools/lancer_tests.py"}}]}}


def ligne_resultat(ident="u1"):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": ident, "content": "ok"}]}}


def proc(pid, parent, nom, cpu, cree):
    return {"pid": pid, "parent": parent, "nom": nom, "cpu": cpu, "debut": int(cree * 1000), "cree": cree}


class Base(unittest.TestCase):
    T0 = 1_000_000.0

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.agents = Path(self._t.name) / "agents-en-cours"
        self.agents.mkdir()
        self.maintenant = self.T0
        self.tues = []
        self.procs = {}

    def agent(self, cle="t1", pid=100, cree=T0 - 600, lignes=(), tache=None):
        (self.agents / f"{cle}.json").write_text(json.dumps(
            {"genre": "tache", "tache": tache or cle, "agent": "dev-1", "pid": pid, "debut_processus": int(cree * 1000),
             "debut": cree}), encoding="utf-8")
        (self.agents / f"{cle}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lignes), encoding="utf-8")

    def ajouter(self, *ps):
        for p in ps:
            self.procs[p["pid"]] = p

    def tuer(self, p, descendants):
        self.tues.append((p["pid"], sorted(descendants)))
        for pid in [p["pid"], *descendants]:
            self.procs.pop(pid, None)
        return True

    def surveillance(self, **kw):
        return figes.Surveillance(fige_s=300, lister=lambda: {k: dict(v) for k, v in self.procs.items()},
                                  tuer=self.tuer, horloge=lambda: self.maintenant, moi=1, **kw)

    def passer(self, s, apres_s=0):
        self.maintenant += apres_s
        return s.passer(self.agents)

    def arbre_godot(self, cpu_godot=5.0):
        """claude (100) → bash (200) → python lanceur (300) → godot (400) ; la commande lancée à T0 - 60."""
        self.agent(lignes=[ligne_commande(self.T0 - 60)])
        self.ajouter(proc(100, 1, "claude", 50.0, self.T0 - 600), proc(200, 100, "bash", 0.1, self.T0 - 59),
                     proc(300, 200, "python", 0.3, self.T0 - 58), proc(400, 300, "godot", cpu_godot, self.T0 - 57),
                     proc(150, 100, "node", 1.0, self.T0 - 590))       # un serveur MCP de l'agent, lancé avant la commande


class Figes(Base):
    def test_le_programme_fige_sous_un_agent_qui_attend_sa_commande_est_arrete(self):
        self.arbre_godot()
        s = self.surveillance()
        self.assertEqual(self.passer(s), [])
        self.assertEqual(self.passer(s, 200), [])            # 200 s d'immobilité : pas encore
        arrets = self.passer(s, 101)
        self.assertEqual([(a["tache"], a["nom"], a["pid"]) for a in arrets], [("t1", "godot", 400)])
        self.assertEqual(self.tues, [(400, [])])               # godot seul : ni le lanceur, ni le shell, ni l'agent
        self.assertEqual(figes.texte_journal(arrets[0]),
                         "Commande figée arrêtée : godot (aucune activité du processeur depuis 5 min).")

    def test_un_programme_qui_calcule_n_est_pas_arrete(self):
        self.arbre_godot()
        s = self.surveillance()
        for _ in range(10):
            self.procs[400]["cpu"] += 1.0
            self.assertEqual(self.passer(s, 60), [])
        self.assertEqual(self.tues, [])

    def test_rien_tant_qu_une_partie_de_la_commande_travaille(self):
        """Un lanceur qui calcule pendant que son programme attend : la commande n'est pas figée."""
        self.arbre_godot()
        s = self.surveillance()
        for _ in range(10):
            self.procs[300]["cpu"] += 1.0
            self.assertEqual(self.passer(s, 60), [])
        self.assertEqual(self.tues, [])

    def test_rien_si_l_agent_n_attend_pas_de_commande(self):
        self.arbre_godot()
        self.agent(lignes=[ligne_commande(self.T0 - 60), ligne_resultat()])
        s = self.surveillance()
        self.passer(s)
        self.assertEqual(self.passer(s, 900), [])
        self.assertEqual(self.tues, [])

    def test_le_lanceur_fige_sans_enfant_est_arrete(self):
        self.agent(lignes=[ligne_commande(self.T0 - 60)])
        self.ajouter(proc(100, 1, "claude.exe", 50.0, self.T0 - 600), proc(200, 100, "bash.exe", 0.1, self.T0 - 59),
                     proc(300, 200, "python.exe", 0.3, self.T0 - 58))
        s = self.surveillance()
        self.passer(s)
        self.assertEqual([a["nom"] for a in self.passer(s, 301)], ["python"])

    def test_un_processus_etranger_n_est_jamais_touche(self):
        self.arbre_godot(cpu_godot=None)       # godot non mesurable : jamais figé
        self.ajouter(proc(900, 1, "godot", 1.0, self.T0 - 30), proc(901, 900, "python", 1.0, self.T0 - 20),
                     proc(902, 100_000, "godot", 1.0, self.T0 - 20))     # parent inconnu
        s = self.surveillance()
        for _ in range(10):
            self.passer(s, 120)
        self.assertEqual(self.tues, [])

    def test_le_numero_d_un_agent_repris_par_un_autre_processus_ne_trompe_pas(self):
        """Le processus qui porte le numéro de l'agent n'est pas l'agent (autre heure de création) : rien."""
        self.agent(lignes=[ligne_commande(self.T0 - 60)])
        self.ajouter(proc(100, 1, "explorer", 50.0, self.T0 - 10), proc(400, 100, "godot", 1.0, self.T0 - 5))
        s = self.surveillance()
        for _ in range(10):
            self.passer(s, 120)
        self.assertEqual(self.tues, [])

    def test_une_mesure_impossible_ne_fait_rien(self):
        self.arbre_godot()
        for lister in (lambda: None, lambda: (_ for _ in ()).throw(OSError("refusé"))):
            s = figes.Surveillance(fige_s=1, lister=lister, tuer=self.tuer, horloge=lambda: self.maintenant, moi=1)
            self.assertEqual(self.passer(s), [])
            self.assertEqual(self.passer(s, 1000), [])
        self.assertEqual(self.tues, [])

    def test_un_dossier_sans_agent_ne_fait_rien(self):
        self.ajouter(proc(400, 1, "godot", 1.0, self.T0 - 5000))
        s = self.surveillance()
        self.assertEqual(s.passer(Path(self._t.name) / "absent"), [])
        self.passer(s)
        self.assertEqual(self.passer(s, 1000), [])
        self.assertEqual(self.tues, [])

    def test_jamais_l_agent_ni_le_moteur(self):
        self.agent(lignes=[ligne_commande(self.T0 - 60)])
        self.ajouter(proc(100, 1, "claude", 50.0, self.T0 - 600), proc(1, 100, "python", 1.0, self.T0 - 30))
        s = self.surveillance()        # le moteur (moi=1) figurerait sous l'agent : jamais touché
        self.passer(s)
        self.assertEqual(self.passer(s, 1000), [])
        self.assertEqual(self.tues, [])


class Orphelins(Base):
    def test_un_programme_laisse_par_un_agent_fini_est_arrete(self):
        self.arbre_godot()
        s = self.surveillance()
        self.passer(s)
        for pid in (100, 150, 200, 300):       # l'agent a fini (délai dépassé) : godot reste, son parent n'est plus là
            del self.procs[pid]
        (self.agents / "t1.json").unlink()        # le moteur a oublié l'agent
        self.ajouter(proc(4, 0, "System", None, self.T0 - 9999))     # une liste vide serait une mesure ratée
        self.assertEqual(self.passer(s, 100), [])
        arrets = self.passer(s, 201)
        self.assertEqual([(a["tache"], a["nom"], a["orphelin"]) for a in arrets], [("t1", "godot", True)])
        self.assertEqual(figes.texte_journal(arrets[0]),
                         "Commande figée arrêtée : godot (aucune activité du processeur depuis 5 min).")
        self.assertEqual(self.passer(s, 30), [])
        self.assertFalse((self.agents / figes.FICHIER_FAMILLES).exists())     # plus rien à surveiller pour lui

    def test_l_orphelin_d_un_agent_jamais_vu_vivant_est_reconnu_a_son_parent(self):
        """Le moteur redémarre : l'agent est mort, son enfant (parent = l'agent, né après lui) est encore là."""
        self.agent(lignes=[ligne_commande(self.T0 - 60)])
        self.ajouter(proc(400, 100, "godot", 1.0, self.T0 - 50),
                     proc(500, 100, "godot", 1.0, self.T0 - 700))     # né avant l'agent : pas le sien
        s = self.surveillance()
        self.passer(s)
        arrets = self.passer(s, 301)
        self.assertEqual([a["pid"] for a in arrets], [400])
        self.assertEqual(self.tues, [(400, [])])

    def test_un_orphelin_detache_d_un_agent_vivant_est_arrete_s_il_est_fige(self):
        """Un essai précédent du même agent : le shell a été coupé, godot reste ; l'agent travaille à autre chose."""
        self.arbre_godot()
        s = self.surveillance()
        self.passer(s)
        del self.procs[200], self.procs[300]
        self.agent(lignes=[ligne_commande(self.T0 - 60), ligne_resultat()])
        arrets = self.passer(s, 301)
        self.assertEqual([(a["nom"], a["orphelin"]) for a in arrets], [("godot", True)])

    def test_un_orphelin_qui_calcule_reste(self):
        self.arbre_godot()
        s = self.surveillance()
        self.passer(s)
        for pid in (100, 150, 200, 300):
            del self.procs[pid]
        for _ in range(10):
            self.procs[400]["cpu"] += 1
            self.assertEqual(self.passer(s, 120), [])


class Flux(unittest.TestCase):
    def test_commande_en_attente(self):
        t = 1_000_000.0
        self.assertEqual(figes.commandes_en_attente([ligne_commande(t)]), {"u1": t})
        self.assertEqual(figes.commandes_en_attente([ligne_commande(t), ligne_resultat()]), {})
        self.assertEqual(figes.commandes_en_attente([ligne_commande(t, outil="Edit")]), {})
        sans_heure = ligne_commande(t)
        del sans_heure["timestamp"]
        self.assertEqual(figes.commandes_en_attente([sans_heure]), {"u1": None})

    def test_noms(self):
        self.assertEqual(figes.nom_court("C:\\Godot\\Godot_v4.3-stable_win64.exe"), "Godot_v4.3-stable_win64")
        self.assertTrue(figes.protege("bash.exe") and figes.protege("claude") and figes.protege("pwsh"))
        self.assertFalse(figes.protege("godot"))
        self.assertTrue(figes.lanceur("python3.12") and figes.lanceur("py"))


class FausseSurveillance:
    def __init__(self, arrets):
        self.arrets, self.passages, self.listes = arrets, [], 0

    def lister(self):
        self.listes += 1
        return {4: proc(4, 0, "System", None, 0)}

    def passer(self, dossier, procs=None):
        self.passages.append((Path(dossier), procs))
        rendu, self.arrets = self.arrets, []
        return rendu


class DansLeMoteur(unittest.TestCase):
    """Le moteur passe la surveillance à chaque projet (au plus toutes les 30 s) et écrit chaque arrêt au journal."""

    def setUp(self):
        from tests.test_moteur_boucle import Base as BaseBoucle

        class Aide(BaseBoucle):
            def runTest(self):
                pass
        self.aide = Aide()
        self.aide.setUp()
        self.addCleanup(self.aide.doCleanups)

    def test_l_arret_est_ecrit_au_journal_de_la_tache(self):
        from moteur import boucle, detache, regles
        a = self.aide
        tid = a.ok("tache", entree={"titre": "Tests", "role": "dev", "colonne": "dev"})["id"]
        faux = FausseSurveillance([{"tache": tid, "agent": "dev-1", "nom": "godot", "pid": 400, "immobile_s": 301,
                                    "orphelin": False}])
        m = a.fabriquer([a.projet], surveillance=faux)
        m.tour()                                                 # le projet démarre ; aucun agent : rien
        self.assertEqual((faux.listes, faux.passages), (0, []))
        d = detache.dossier(a.projet.factory.parent)
        d.mkdir(exist_ok=True)
        (d / figes.FICHIER_FAMILLES).write_text("{}", encoding="utf-8")   # la surveillance a de quoi faire
        m.tour()
        journal = [j["texte"] for j in regles.lancer(a.projet, "detail", {"tache": tid})["journal"]]
        self.assertIn("Commande figée arrêtée : godot (aucune activité du processeur depuis 5 min).", journal, m.journal)
        self.assertEqual([x[0] for x in faux.passages], [d])
        m.tour()                                                 # moins de 30 s après : pas de nouveau passage
        self.assertEqual(len(faux.passages), 1)
        with mock.patch.object(boucle.time, "monotonic", return_value=time.monotonic() + 31):
            m.tour()
        self.assertEqual(len(faux.passages), 2)

    def test_au_demarrage_les_agents_morts_sont_vus_avant_d_etre_oublies(self):
        from moteur import detache
        d = detache.dossier(self.aide.projet.factory.parent)
        d.mkdir()
        (d / "t9.json").write_text(json.dumps({"tache": "t9", "pid": 999999999, "debut": time.time()}), encoding="utf-8")
        vus = []
        faux = FausseSurveillance([])
        faux.passer = lambda dossier, procs=None: vus.append((Path(dossier) / "t9.json").exists()) or []
        self.aide.fabriquer([self.aide.projet], surveillance=faux).tour()
        self.assertEqual(vus, [True])
        self.assertFalse((d / "t9.json").exists())      # puis oublié par le moteur, comme avant

    def test_sans_agent_aucune_liste_des_processus(self):
        faux = FausseSurveillance([])
        m = self.aide.fabriquer([self.aide.projet], surveillance=faux)
        m.tour()
        self.assertEqual((faux.listes, faux.passages), (0, []))


# --- De vrais faux processus.

FAUX_AGENT = r'''
import subprocess, sys, time
enfant = subprocess.Popen([sys.executable, "-c", sys.argv[1]])
print(enfant.pid, flush=True)
time.sleep(120)
'''
DORT = "import time; time.sleep(120)"
CALCULE = "import time\nfin = time.time() + 120\nwhile time.time() < fin: pass"


@unittest.skipUnless(sys.platform == "win32" or Path("/proc/self/stat").exists(), "mesure des processus indisponible")
class VraisProcessus(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.agents = Path(self._t.name) / "agents-en-cours"
        self.agents.mkdir()
        self.script = Path(self._t.name) / "faux_agent.py"
        self.script.write_text(FAUX_AGENT, encoding="utf-8")

    def lancer(self, argv, **kw):
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, **kw)
        self.addCleanup(self._finir, p)
        return p

    @staticmethod
    def _finir(p):
        try:
            p.kill()
            p.wait(10)
        except OSError:
            pass

    def faux_agent(self, code):
        """Le faux agent (un script Python qui lance son enfant puis dort) et son état, qui attend sa commande."""
        debut = time.time()
        p = self.lancer([sys.executable, str(self.script), code])
        enfant = int(p.stdout.readline())
        self.addCleanup(self._tuer_pid, enfant)
        from moteur import detache
        (self.agents / "t1.json").write_text(json.dumps(
            {"genre": "tache", "tache": "t1", "agent": "dev-1", "pid": p.pid,
             "debut_processus": detache.debut_processus(p.pid), "debut": debut}), encoding="utf-8")
        (self.agents / "t1.jsonl").write_text(json.dumps(ligne_commande(debut - 5)) + "\n", encoding="utf-8")
        return p, enfant

    @staticmethod
    def _tuer_pid(pid):
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=30)
            else:
                os.kill(pid, 9)
        except (OSError, subprocess.SubprocessError):
            pass

    @staticmethod
    def vivant(pid):
        procs = figes.lister_processus()
        return procs is not None and pid in procs

    def tourner(self, s, duree):
        arrets, fin = [], time.time() + duree
        while time.time() < fin:
            arrets += s.passer(self.agents)
            time.sleep(0.3)
        return arrets

    def test_le_programme_qui_dort_est_arrete_l_etranger_et_l_agent_restent(self):
        etranger = self.lancer([sys.executable, "-c", DORT])
        agent, enfant = self.faux_agent(DORT)
        self.assertIsNotNone(figes.lister_processus())
        s = figes.Surveillance(fige_s=1.5)
        arrets = self.tourner(s, 5)
        self.assertIn(("t1", enfant), [(a["tache"], a["pid"]) for a in arrets])
        self.assertTrue(figes.texte_journal(arrets[0]).startswith("Commande figée arrêtée : python"))
        fin = time.time() + 10
        while self.vivant(enfant) and time.time() < fin:
            time.sleep(0.2)
        self.assertFalse(self.vivant(enfant))
        self.assertIsNone(agent.poll())              # l'agent vit toujours
        self.assertIsNone(etranger.poll())           # l'étranger aussi

    def test_le_programme_qui_calcule_reste(self):
        agent, enfant = self.faux_agent(CALCULE)
        s = figes.Surveillance(fige_s=1.5)
        self.assertEqual(self.tourner(s, 4), [])
        self.assertTrue(self.vivant(enfant))
        self.assertIsNone(agent.poll())


if __name__ == "__main__":
    unittest.main()
