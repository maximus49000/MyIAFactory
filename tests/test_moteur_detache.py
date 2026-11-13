"""Les agents locaux détachés du moteur : un faux `claude` (un petit script Python), jamais le vrai."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from moteur import agents, appel, detache

RACINE = Path(__file__).resolve().parent.parent
RAPPORT = '```json\n{"statut": "fait", "message": {"texte": "Fini.", "attend": false}}\n```'
FAUX_CLAUDE = r'''
import json, pathlib, sys, time
entree = sys.stdin.read()
go = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] != "-" else None
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s-1"}), flush=True)
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit",
      "input": {"file_path": "scenes/combat.gd", "old_string": "secret"}}]}}), flush=True)
if go is not None:
    while not go.exists():
        time.sleep(0.05)
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "session_id": "s-1",
      "result": "Lu : " + entree.strip()[:20] + "\n" + sys.argv[2].replace("\\n", "\n"),
      "modelUsage": {"claude-sonnet-5-5": {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 0,
                                           "cacheCreationInputTokens": 0}}}), flush=True)
'''


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dossier = Path(self._t.name)
        self.factory_dir = self.dossier / ".factory"
        self.factory_dir.mkdir()
        self.script = self.dossier / "faux_claude.py"
        self.script.write_text(FAUX_CLAUDE, encoding="utf-8")
        self.go = self.dossier / "go"
        self.lances = []

    def lancer(self, argv, entree, sortie, erreurs, env, cwd):
        """Le faux `claude`, lancé détaché comme le vrai (le même `lancer_processus`)."""
        self.lances.append(list(argv))
        return detache.lancer_processus([sys.executable, str(self.script), str(self.go), RAPPORT.replace("\n", "\\n")],
                                        entree, sortie, erreurs, None, cwd)

    def registre(self, **kw):
        return detache.Registre(self.factory_dir, lancer=self.lancer, noter_abonnement=False, pas_s=0.05, **kw)

    def finir(self):
        self.go.write_text("go", encoding="utf-8")

    def attendre(self, condition, delai=20):
        fin = time.time() + delai
        while time.time() < fin:
            if condition():
                return True
            time.sleep(0.05)
        return False


class Registre(Base):
    def test_un_agent_ecrit_son_flux_et_son_etat_dans_le_projet(self):
        self.finir()
        r = self.registre()
        code, sortie = r.executeur("t1", {"agent": "dev-1", "taches": ["t1"], "modele": "sonnet", "lot": None,
                                          "matiere": "M"})(["claude", "-p"], b"Bonjour l'agent", None,
                                                            str(self.dossier), 60)
        self.assertEqual(code, 0)
        resultat, _ = appel._lire_flux(sortie)
        self.assertIn("Lu : Bonjour l'agent", resultat["result"])
        d = self.factory_dir / "agents-en-cours"
        self.assertTrue((d / "t1.jsonl").is_file())
        etat = json.loads((d / "t1.json").read_text(encoding="utf-8"))
        self.assertEqual((etat["tache"], etat["agent"], etat["modele"], etat["taches"]), ("t1", "dev-1", "sonnet", ["t1"]))
        self.assertIsInstance(etat["pid"], int)
        self.assertIsInstance(etat["debut"], (int, float))
        self.assertEqual((d / ".gitignore").read_text(encoding="utf-8"), "*\n")    # jamais dans le dépôt du projet

    def test_un_moteur_qui_redemarre_se_rattache_a_l_agent_vivant_sans_le_relancer(self):
        premier = self.registre()
        lancement = premier.executeur("t1", {"agent": "dev-1", "taches": ["t1"]})
        import threading
        fil = threading.Thread(target=lambda: lancement(["claude"], b"x", None, str(self.dossier), 60), daemon=True)
        fil.start()
        self.assertTrue(self.attendre(lambda: premier.lire_etat("t1") is not None))
        second = self.registre()      # le moteur relancé : un autre registre sur le même dossier
        self.assertEqual(second.issue("t1"), "vivant")
        rendu = []
        fil2 = threading.Thread(target=lambda: rendu.append(
            second.executeur("t1", {"agent": "dev-1"}, rattacher=True)(["claude"], b"y", None, str(self.dossier), 60)),
            daemon=True)
        fil2.start()
        time.sleep(0.3)
        self.assertEqual(rendu, [])           # il attend
        self.finir()
        fil2.join(20)
        fil.join(20)
        self.assertEqual(len(self.lances), 1)  # un seul lancement en tout
        self.assertEqual(rendu[0][0], 0)
        self.assertIn('"type": "result"', rendu[0][1].decode("utf-8"))

    def test_jamais_deux_agents_sur_la_meme_tache(self):
        r = self.registre()
        import threading
        premier = threading.Thread(target=lambda: r.executeur("t1", {})(["claude"], b"x", None, str(self.dossier), 60),
                                   daemon=True)
        premier.start()
        self.addCleanup(premier.join, 20)
        self.assertTrue(self.attendre(lambda: r.lire_etat("t1") is not None))
        rendu = []
        fil = threading.Thread(target=lambda: rendu.append(r.executeur("t1", {})(["claude"], b"x", None,
                                                                                str(self.dossier), 60)), daemon=True)
        fil.start()
        self.finir()
        fil.join(20)
        self.assertEqual(len(self.lances), 1)
        self.assertEqual(rendu[0][0], 0)

    def test_agent_mort_avec_son_resultat_est_lu_sans_relance(self):
        self.finir()
        r = self.registre()
        r.executeur("t1", {})(["claude"], b"x", None, str(self.dossier), 60)
        second = self.registre()
        self.assertEqual(second.issue("t1"), "resultat")
        code, sortie = second.executeur("t1", {}, rattacher=True)(["claude"], b"x", None, str(self.dossier), 60)
        self.assertEqual((code, len(self.lances)), (0, 1))
        self.assertIsNotNone(appel._lire_flux(sortie)[0])

    def test_agent_mort_sans_resultat(self):
        d = self.factory_dir / "agents-en-cours"
        d.mkdir()
        (d / "t1.json").write_text(json.dumps({"tache": "t1", "pid": 999999999, "debut": time.time()}), encoding="utf-8")
        (d / "t1.jsonl").write_text('{"type": "system"}\n', encoding="utf-8")
        r = self.registre()
        self.assertEqual(r.issue("t1"), "mort")
        self.assertEqual([e["cle"] for e in r.entrees()], ["t1"])
        r.effacer("t1")
        self.assertEqual(r.entrees(), [])
        self.assertFalse((d / "t1.jsonl").exists())

    def test_delai_depasse_l_agent_est_arrete(self):
        r = self.registre()
        with self.assertRaises(TimeoutError):
            r.executeur("t1", {})(["claude"], b"x", None, str(self.dossier), 0.5)
        self.assertTrue(self.attendre(lambda: r.issue("t1") != "vivant", 10))

    def test_un_agent_actif_n_est_pas_arrete(self):
        """Essai réel : une tâche avec de longues suites de tests était tuée à 30 min et relancée de zéro, sans fin.
        L'agent n'est arrêté que s'il est bloqué : tant qu'il agit, le délai repart."""
        import threading
        r = self.registre()
        flux = self.factory_dir / "agents-en-cours" / "t1.jsonl"

        def agir():      # une action toutes les 0,1 s pendant 1,2 s (bien plus que le délai), puis le résultat
            fin = time.time() + 1.2
            while time.time() < fin:
                if flux.exists():
                    with open(flux, "a", encoding="utf-8") as f:
                        f.write('{"type": "user", "message": {"content": [{"type": "tool_result"}]}}\n')
                time.sleep(0.1)
            self.finir()
        fil = threading.Thread(target=agir, daemon=True)
        fil.start()
        code, _ = r.executeur("t1", {})(["claude"], b"x", None, str(self.dossier), 0.5)
        fil.join(5)
        self.assertEqual(code, 0)

    def test_une_commande_figee_est_un_blocage(self):
        """Une commande qui ne finit jamais : `claude` n'écrit plus que des signes de vie, qui ne comptent pas."""
        import threading
        r = self.registre()
        flux = self.factory_dir / "agents-en-cours" / "t1.jsonl"
        arret = threading.Event()

        def battre():
            while not arret.is_set():
                if flux.exists():
                    with open(flux, "a", encoding="utf-8") as f:
                        f.write('{"type": "tool_progress", "heartbeat": true}\n')
                time.sleep(0.1)
        fil = threading.Thread(target=battre, daemon=True)
        fil.start()
        self.addCleanup(arret.set)
        with self.assertRaises(TimeoutError):
            r.executeur("t1", {})(["claude"], b"x", None, str(self.dossier), 0.5)

    def test_la_consigne_est_copiee_dans_le_dossier_de_l_agent(self):
        self.finir()
        consigne = self.dossier / "tmp-consigne.md"
        consigne.write_text("Consigne", encoding="utf-8")
        r = self.registre()
        r.executeur("t1", {})(["claude", "--append-system-prompt-file", str(consigne)], b"x", None,
                              str(self.dossier), 60)
        argv = self.lances[0]
        copie = Path(argv[argv.index("--append-system-prompt-file") + 1])
        self.assertEqual(copie.parent, self.factory_dir / "agents-en-cours")
        self.assertEqual(copie.read_text(encoding="utf-8"), "Consigne")

    def test_l_agent_survit_au_processus_qui_l_a_lance(self):
        """Le moteur s'arrête (son processus se termine) : l'agent continue et écrit son résultat dans son fichier."""
        d = self.factory_dir / "agents-en-cours"
        d.mkdir()
        entree, sortie, err = d / "t1.entree", d / "t1.jsonl", d / "t1.err"
        entree.write_bytes(b"Bonjour")
        code = ("import sys; from moteur import detache; "
                f"p = detache.lancer_processus([sys.executable, {str(self.script)!r}, {str(self.go)!r}, 'fin'], "
                f"{str(entree)!r}, {str(sortie)!r}, {str(err)!r}, None, {str(self.dossier)!r}); print(p.pid)")
        moteur = subprocess.run([sys.executable, "-c", code], cwd=str(RACINE), capture_output=True, timeout=60)
        self.assertEqual(moteur.returncode, 0, moteur.stderr)
        pid = int(moteur.stdout.decode().strip())
        self.finir()
        self.assertTrue(self.attendre(lambda: '"type": "result"' in sortie.read_text(encoding="utf-8")), pid)
        self.assertTrue(self.attendre(lambda: not detache.verrou.pid_vivant(pid)))   # avant d'effacer le dossier


class Questions(Base):
    def test_les_questions_attendent_la_fin_de_la_tache(self):
        detache.ajouter_question(self.factory_dir, "t1", "Où en es-tu ?")
        detache.ajouter_question(self.factory_dir, "t1", "Et le menu ?")
        self.assertEqual(detache.questions(self.factory_dir, "t1"), ["Où en es-tu ?", "Et le menu ?"])
        self.assertEqual(detache.prendre_questions(self.factory_dir, "t1"), ["Où en es-tu ?", "Et le menu ?"])
        self.assertEqual(detache.prendre_questions(self.factory_dir, "t1"), [])

    def test_effacer_l_agent_garde_ses_questions(self):
        detache.ajouter_question(self.factory_dir, "t1", "Où en es-tu ?")
        self.registre().effacer("t1")
        self.assertEqual(detache.questions(self.factory_dir, "t1"), ["Où en es-tu ?"])


class AuTravail(Base):
    def ecrire(self, cle, etat, lignes):
        d = self.factory_dir / "agents-en-cours"
        d.mkdir(exist_ok=True)
        (d / f"{cle}.json").write_text(json.dumps(etat), encoding="utf-8")
        (d / f"{cle}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lignes), encoding="utf-8")
        return d / f"{cle}.jsonl"

    def outil(self, nom, entree):
        return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": nom, "input": entree}]}}

    def test_debut_et_derniere_action_servis_pour_la_tache(self):
        debut = time.time() - 23 * 60
        flux = self.ecrire("t1", {"tache": "t1", "taches": ["t1", "t2"], "agent": "dev-1", "pid": os.getpid(),
                                  "debut": debut, "dossier": str(self.dossier)},
                           [self.outil("Read", {"file_path": str(self.dossier / "a.py")}),
                            self.outil("Edit", {"file_path": str(self.dossier / "scenes" / "combat.gd"),
                                                "old_string": "mot de passe"})])
        os.utime(flux, (debut + 21 * 60, debut + 21 * 60))
        taches = [{"id": "t1"}, {"id": "t2"}, {"id": "t3"}]
        detache.ajouter_au_travail(taches, self.factory_dir)
        t = taches[0]["travail"]
        self.assertEqual((t["agent"], t["action"]), ("dev-1", "modifie scenes/combat.gd"))
        from datetime import datetime
        self.assertAlmostEqual(datetime.fromisoformat(t["depuis"]).timestamp(), debut, delta=1)
        self.assertAlmostEqual(datetime.fromisoformat(t["action_t"]).timestamp(), debut + 21 * 60, delta=1)
        self.assertNotIn("mot de passe", json.dumps(t))
        self.assertEqual(taches[1]["travail"]["agent"], "dev-1")     # le reste du lot aussi
        self.assertNotIn("travail", taches[2])

    def test_rien_pour_un_agent_qui_ne_tourne_plus(self):
        self.ecrire("t1", {"tache": "t1", "agent": "dev-1", "pid": 999999999, "debut": time.time()}, [])
        taches = [{"id": "t1"}]
        detache.ajouter_au_travail(taches, self.factory_dir)
        self.assertNotIn("travail", taches[0])

    def test_une_commande_est_dite_sans_son_contenu(self):
        lignes = [self.outil("Bash", {"command": "python outils/build.py --token=abc123"})]
        self.assertEqual(detache.derniere_action(lignes, None), "lance python")
        cd = [self.outil("Bash", {"command": "cd C:/projet && python tools/lancer_tests.py 2>&1 | tail -40"})]
        self.assertEqual(detache.derniere_action(cd, None), "lance python")       # pas « lance cd »
        self.assertEqual(detache.derniere_action([self.outil("Write", {"file_path": "/ailleurs/x.txt"})], "/projet"),
                         "écrit x.txt")
        self.assertEqual(detache.derniere_action([self.outil("Grep", {"pattern": "secret"})], None),
                         "cherche dans les fichiers")
        texte = {"type": "assistant", "message": {"content": [{"type": "text", "text": "Je pense que…"}]}}
        self.assertEqual(detache.derniere_action([texte], None), "rédige")
        self.assertIsNone(detache.derniere_action([{"type": "system"}], None))


class AvecExecuterAgent(Base):
    def test_executer_agent_passe_par_le_registre_et_rend_la_session(self):
        self.finir()
        r = self.registre()
        fiche = {"cle": "dev-1", "role": "dev", "modele": "Sonnet", "lieu": "local", "outils": None}
        e = agents.executer_agent("DEPART", "MATIERE", agent=fiche, modele="sonnet", dossier_projet=str(self.dossier),
                                  tache="t1", executeur=r.executeur("t1", {"agent": "dev-1"}))
        self.assertIsNone(e.erreur, e.erreur)
        self.assertEqual(e.rapport["message"]["texte"], "Fini.")
        self.assertEqual(e.session, "s-1")
        self.assertEqual(e.usage["entree"], 10)
        self.assertEqual(len(self.lances), 1)
        self.assertEqual(self.lances[0][1:3], ["-p", "--output-format"])


if __name__ == "__main__":
    unittest.main()
