"""« Optimiser la charge » : le classement des programmes, les protections, et le serveur qui refuse d'arrêter un
programme protégé. Jamais un vrai relevé ni un vrai arrêt : tout est injecté."""
import json
import unittest

from bureau import processus as pr
from moteur import agents, appel, detache
from tests.test_acces import AvecBureauOuvert


def proc(pid, ppid, nom, cpu_s=0.0, memoire=0, debut=None):
    return {"pid": pid, "ppid": ppid, "nom": nom, "cpu_s": cpu_s, "memoire": memoire, "debut": debut}


def releve(*procs):
    return {p["pid"]: p for p in procs}


# Un ordinateur : le système, l'explorateur qui a lancé un terminal, où tourne le bureau (py → python) ; le moteur ;
# un agent (claude.exe, lancé par le moteur) qui a lancé Godot ; Chrome ; Claude Code ; Tailscale.
AVANT = releve(proc(0, 0, "System Idle Process", 100), proc(4, 0, "System", 10), proc(700, 4, "svchost.exe", 5),
               proc(900, 4, "explorer.exe", 1), proc(1000, 900, "WindowsTerminal.exe", 1),
               proc(1100, 1000, "py.exe", 0), proc(1200, 1100, "python.exe", 2),
               proc(2000, 900, "python.exe", 3), proc(3000, 2000, "claude.exe", 10),
               proc(3100, 3000, "Godot.exe", 20), proc(4000, 900, "chrome.exe", 30),
               proc(5000, 900, "claude.exe", 1), proc(6000, 700, "tailscaled.exe", 1))
APRES = releve(proc(0, 0, "System Idle Process", 104), proc(4, 0, "System", 10.1, 1 << 20),
               proc(700, 4, "svchost.exe", 5.5, 50 << 20), proc(900, 4, "explorer.exe", 1, 100 << 20),
               proc(1000, 900, "WindowsTerminal.exe", 1, 10 << 20), proc(1100, 1000, "py.exe", 0, 1 << 20),
               proc(1200, 1100, "python.exe", 2.2, 80 << 20), proc(2000, 900, "python.exe", 3.1, 60 << 20),
               proc(3000, 2000, "claude.exe", 11, 300 << 20), proc(3100, 3000, "Godot.exe", 22, 900 << 20),
               proc(4000, 900, "chrome.exe", 31.5, 1500 << 20), proc(5000, 900, "claude.exe", 1.2, 400 << 20),
               proc(6000, 700, "tailscaled.exe", 1, 30 << 20))
AGENT = {"pid": 3000, "prenom": "Léa", "tache": "t7", "cle": "t7", "factory": None}
MOI = {"agents": [AGENT], "moteur": 2000, "bureau": 1200}


class Classement(unittest.TestCase):
    def lignes(self, **kw):
        return {x["pid"]: x for x in pr.classer(AVANT, APRES, 1.0, 4, **{**MOI, **kw})}

    def test_trie_par_processeur_divise_par_les_coeurs(self):
        lignes = pr.classer(AVANT, APRES, 1.0, 4, **MOI)
        self.assertEqual([x["pid"] for x in lignes[:3]], [3100, 4000, 3000])
        self.assertEqual(lignes[0]["cpu"], 50.0)            # 2 s de processeur en 1 s sur 4 cœurs
        self.assertEqual(lignes[0]["memoire_mo"], 900.0)
        self.assertNotIn(0, [x["pid"] for x in lignes])      # le processus inactif n'est pas un programme

    def test_quinze_au_plus(self):
        beaucoup = releve(*(proc(10 + i, 4, f"p{i}.exe", i) for i in range(40)))
        self.assertEqual(len(pr.classer(beaucoup, beaucoup, 1.0, 1)), pr.NOMBRE)

    def test_numero_repris_ne_compte_pas_le_temps_d_un_autre(self):
        avant = releve(proc(10, 4, "a.exe", 100, debut=1))
        apres = releve(proc(10, 4, "b.exe", 2, debut=2))
        self.assertEqual(pr.classer(avant, apres, 1.0, 1)[0]["cpu"], 0.0)

    def test_etiquettes(self):
        l = self.lignes()
        self.assertEqual(l[3000]["etiquette"], "agent Léa (tâche t7)")
        self.assertEqual(l[3100]["etiquette"], "lancé par un agent")
        self.assertEqual(l[2000]["etiquette"], "moteur")
        self.assertEqual(l[1200]["etiquette"], "bureau")
        self.assertIsNone(l[4000]["etiquette"])

    def test_protections(self):
        l = self.lignes()
        proteges = {pid for pid, x in l.items() if x["protege"]}
        # le système, l'explorateur, Claude Code, Tailscale, le bureau, le moteur et ce qui a lancé le bureau
        self.assertEqual(proteges, {4, 700, 900, 1000, 1100, 1200, 2000, 5000, 6000})
        # l'agent (un claude.exe) et ce qu'il a lancé, et Chrome : arrêtables
        for pid in (3000, 3100, 4000):
            self.assertFalse(l[pid]["protege"], pid)

    def test_un_parent_plus_jeune_n_est_pas_un_parent(self):
        r = releve(proc(3000, 2000, "claude.exe", debut=10), proc(3100, 3000, "vieux.exe", debut=5))
        etiquettes, _ = pr.contexte(r, agents=[AGENT])
        self.assertNotIn(3100, etiquettes)

    def test_peut_arreter(self):
        refus, agent, p = pr.peut_arreter(3000, APRES, **MOI)
        self.assertEqual((refus, agent["pid"], p["nom"]), (None, 3000, "claude.exe"))
        refus, agent, _ = pr.peut_arreter(3100, APRES, **MOI)
        self.assertEqual((refus, agent), (None, None))       # lancé par un agent : arrêté seul
        for pid in (0, 4, 700, 900, 1100, 1200, 2000, 5000, 6000):
            refus, _, _ = pr.peut_arreter(pid, APRES, **MOI)
            self.assertTrue(refus, pid)
        self.assertIn("ne tourne plus", pr.peut_arreter(99999, APRES, **MOI)[0])
        for pid in ("3000", True, -1, None):
            self.assertTrue(pr.peut_arreter(pid, APRES, **MOI)[0])


class Lecture(unittest.TestCase):
    def test_sortie_powershell(self):
        sortie = ("#PID 77\r\n#A\r\n10|4|2048|50000000|133000000000000000|chrome.exe\r\nillisible\r\n"
                  "#B 1.25\r\n10|4|4096|70000000|133000000000000000|chrome.exe\r\n77|1|1|1|1|powershell.exe\r\n"
                  "11|10|1|1|0|a|b.exe\r\n")
        avant, apres, duree, pid_mesure = pr.lire_windows(sortie)
        self.assertEqual((duree, pid_mesure), (1.25, 77))
        self.assertEqual(avant[10]["cpu_s"], 5.0)
        self.assertEqual(apres[10]["memoire"], 4096)
        self.assertEqual(apres[11]["nom"], "a|b.exe")
        self.assertIsNone(apres[11]["debut"])

    def test_sortie_ps(self):
        r = pr.lire_ps("  1     0  1000 1-02:03:04 /sbin/init\n 42 1 2048 00:01.50 /usr/bin/python3\nbad\n")
        self.assertEqual(r[1]["cpu_s"], 86400 + 2 * 3600 + 3 * 60 + 4)
        self.assertEqual((r[42]["nom"], r[42]["cpu_s"], r[42]["memoire"]), ("python3", 1.5, 2048 * 1024))


class Serveur(AvecBureauOuvert):
    def setUp(self):
        super().setUp()
        self.factory = self.tmp / "demo"
        d = detache.dossier(self.factory)
        d.mkdir(parents=True, exist_ok=True)
        (d / "t7.json").write_text(json.dumps({"pid": 3000, "agent": "d1", "tache": "t7", "genre": "tache"}),
                                   encoding="utf-8")
        self.tues = []
        self.srv.releve_processus = lambda: (AVANT, APRES, 1.0)
        self.srv.instantane_processus = lambda: APRES
        self.srv.tuer_processus = lambda pid, arbre=False: self.tues.append((pid, arbre))
        self.srv.agent_vivant = lambda etat: True
        self.srv.pid_moteur = lambda: 2000
        self.marque = d / "t7.arrete"

    def arreter_pid(self, pid, entetes=None, port=None):
        corps = json.dumps({"pid": pid}).encode()
        r, data = self.req("POST", "/api/processus/arreter", corps, entetes or self.ENT, port=port or self.port)
        return r.status, json.loads(data)

    def test_liste(self):
        import os
        self.srv.pid_moteur = lambda: 2000
        r, data = self.local("GET", "/api/processus")
        self.assertEqual(r.status, 200)
        lignes = {x["pid"]: x for x in json.loads(data)["processus"]}
        self.assertTrue(lignes[3000]["etiquette"].startswith("agent "))
        self.assertIn("(tâche t7)", lignes[3000]["etiquette"])
        self.assertTrue(lignes[2000]["protege"])
        self.assertEqual(lignes[2000]["etiquette"], "moteur")
        self.assertNotEqual(os.getpid(), 1200)    # le vrai bureau n'est pas dans ce faux relevé

    def test_refuse_un_programme_protege_meme_appele_directement(self):
        for pid in (4, 700, 2000, 5000, 6000):
            code, objet = self.arreter_pid(pid)
            self.assertEqual(code, 403, pid)
            self.assertIn("protégé", objet["erreur"])
        self.assertEqual(self.tues, [])

    def test_arrete_un_programme_ordinaire_seul(self):
        code, objet = self.arreter_pid(4000)
        self.assertEqual((code, objet["ok"]), (200, True))
        self.assertIn("chrome.exe (pid 4000)", objet["message"])
        self.assertEqual(self.tues, [(4000, False)])
        self.assertFalse(self.marque.exists())

    def test_arrete_un_agent_avec_ce_qu_il_a_lance_et_le_dit_au_moteur(self):
        code, _ = self.arreter_pid(3000)
        self.assertEqual(code, 200)
        self.assertEqual(self.tues, [(3000, True)])
        self.assertTrue(self.marque.exists())       # le moteur lira la fin de l'agent comme un arrêt voulu

    def test_un_arret_rate_retire_la_marque(self):
        self.srv.tuer_processus = lambda pid, arbre=False: "Accès refusé."
        code, objet = self.arreter_pid(3000)
        self.assertEqual(code, 500)
        self.assertIn("Accès refusé", objet["erreur"])
        self.assertFalse(self.marque.exists())

    def test_programme_disparu_et_corps_invalide(self):
        self.assertEqual(self.arreter_pid(99999)[0], 404)
        r, _ = self.local("POST", "/api/processus/arreter", b"pas du json", self.ENT)
        self.assertEqual(r.status, 400)

    def test_memes_protections_que_les_autres_post(self):
        code, _ = self.arreter_pid(4000, entetes={"Content-Type": "application/json"})
        self.assertEqual(code, 403)                  # sans X-Bureau
        code, _ = self.arreter_pid(4000, entetes={"X-Bureau": "1", "Content-Type": "text/plain"})
        self.assertEqual(code, 403)
        r, _ = self.req("POST", "/api/processus/arreter", json.dumps({"pid": 4000}).encode(), self.ENT)
        self.assertEqual(r.status, 401)              # l'écouteur distant sans code d'accès
        r, _ = self.req("GET", "/api/processus")
        self.assertEqual(r.status, 401)
        self.assertEqual(self.tues, [])


class MoteurVoitUneTacheArretee(unittest.TestCase):
    def test_l_agent_arrete_n_est_ni_reessaye_ni_relance(self):
        appels = []

        def appeler(*a, **kw):
            appels.append(1)
            raise appel.ErreurAppel(detache.ARRET)
        ex = agents.executer_agent("Départ", "", agent={"cle": "d1", "modele": "Sonnet"}, modele="sonnet",
                                   dossier_projet=".", appeler=appeler, tache="t7")
        self.assertEqual(len(appels), 1)             # pas de second essai
        self.assertTrue(ex.arrete)
        self.assertIsNone(ex.rapport)

    def test_registre_lit_la_marque_une_seule_fois(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as t:
            r = detache.Registre(Path(t), vivant=lambda etat: False, noter_abonnement=False, pas_s=0)
            detache._preparer(r.dossier)
            r.chemin("t7", ".json").write_text(json.dumps({"pid": 3000, "tache": "t7"}), encoding="utf-8")
            detache.demander_arret(Path(t), "t7")
            self.assertTrue(r.arret_demande("t7"))
            with self.assertRaises(detache.ArretDemande):
                r.attendre("t7", 60)
            self.assertFalse(r.arret_demande("t7"))
            self.assertEqual(r.attendre("t7", 60)[0], 1)     # sans marque : une fin ordinaire (sans résultat)


if __name__ == "__main__":
    unittest.main()
