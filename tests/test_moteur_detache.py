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
        self.assertAlmostEqual(datetime.fromisoformat(t["vie_t"]).timestamp(), debut + 21 * 60, delta=1)
        # le reste du lot attend son tour dans la même session : confié au même agent, sans activité à lui
        self.assertNotIn("travail", taches[1])
        self.assertEqual((taches[1]["dans_le_lot"]["etat"], taches[1]["agent"]), ("a_venir", "dev-1"))
        self.assertNotIn("travail", taches[2])

    def test_une_commande_en_cours_donne_l_heure_de_l_action_et_le_signe_de_vie(self):
        """Essai réel : « dernière action il y a 4 min » pendant une suite de tests ; l'action garde son heure, les
        signes de vie de la commande en cours sont donnés à part (`vie_t`)."""
        from datetime import datetime, timezone
        debut = time.time() - 10 * 60
        action = datetime.fromtimestamp(debut + 60, timezone.utc).isoformat().replace("+00:00", "Z")
        flux = self.ecrire("t1", {"tache": "t1", "agent": "dev", "pid": os.getpid(), "debut": debut,
                                  "dossier": str(self.dossier)},
                           [{**self.outil("Bash", {"command": "python tools/lancer_tests.py"}), "timestamp": action},
                            {"type": "tool_progress", "heartbeat": True}])
        os.utime(flux, (debut + 9 * 60, debut + 9 * 60))
        taches = [{"id": "t1"}]
        detache.ajouter_au_travail(taches, self.factory_dir)
        t = taches[0]["travail"]
        self.assertEqual(t["action"], "lance python")
        self.assertAlmostEqual(datetime.fromisoformat(t["action_t"]).timestamp(), debut + 60, delta=1)
        self.assertAlmostEqual(datetime.fromisoformat(t["vie_t"]).timestamp(), debut + 9 * 60, delta=1)

    def test_historique_des_actions_du_plus_recent_au_plus_ancien(self):
        lignes = [self.outil("Read", {"file_path": str(self.dossier / "a.py")}),
                  self.outil("Edit", {"file_path": str(self.dossier / "scenes" / "combat.gd"), "old_string": "mot de passe"}),
                  {"type": "assistant", "message": {"content": [{"type": "text", "text": "Je réfléchis"}]}},
                  self.outil("Bash", {"command": "cd x && python -m pytest tests/secret.py"})]
        h = detache.historique_des_actions(lignes, str(self.dossier))
        self.assertEqual([x["texte"] for x in h], ["lance python", "modifie scenes/combat.gd", "lit a.py"])
        self.assertNotIn("mot de passe", json.dumps(h))
        self.assertNotIn("secret.py", json.dumps(h))
        self.assertTrue(all(set(x) == {"t", "texte"} for x in h))

    def test_historique_des_actions_garde_l_heure_de_la_ligne(self):
        ligne = {**self.outil("Read", {"file_path": "a.py"}), "timestamp": "2026-11-26T10:00:00Z"}
        h = detache.historique_des_actions([ligne, self.outil("Read", {"file_path": "b.py"})], None)
        self.assertIsNone(h[0]["t"])
        self.assertTrue(h[1]["t"])

    def test_historique_des_actions_borne_et_vide(self):
        self.assertEqual(detache.historique_des_actions([], None), [])
        lignes = [self.outil("Read", {"file_path": f"f{i}.py"}) for i in range(80)]
        h = detache.historique_des_actions(lignes, None)
        self.assertEqual(len(h), detache.MAX_HISTORIQUE)
        self.assertEqual(h[0]["texte"], "lit f79.py")
        self.assertEqual(len(detache.historique_des_actions(lignes, None, limite=3)), 3)

    def test_ajouter_au_travail_porte_l_historique(self):
        self.ecrire("t1", {"tache": "t1", "agent": "dev", "pid": os.getpid(), "debut": time.time() - 60,
                           "dossier": str(self.dossier)},
                    [self.outil("Read", {"file_path": "a.kt"}), self.outil("Edit", {"file_path": "b.kt"})])
        taches = [{"id": "t1"}]
        detache.ajouter_au_travail(taches, self.factory_dir)
        self.assertEqual([x["texte"] for x in taches[0]["travail"]["historique"]], ["modifie b.kt", "lit a.kt"])

    def test_rien_pour_un_agent_qui_ne_tourne_plus(self):
        self.ecrire("t1", {"tache": "t1", "agent": "dev-1", "pid": 999999999, "debut": time.time()}, [])
        taches = [{"id": "t1"}]
        detache.ajouter_au_travail(taches, self.factory_dir)
        self.assertNotIn("travail", taches[0])

    def avancement(self, cle, contenu):
        (self.dossier_agents() / (cle + ".avancement.json")).write_text(
            contenu if isinstance(contenu, str) else json.dumps(contenu), encoding="utf-8")

    def dossier_agents(self):
        d = detache.dossier(self.factory_dir)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_lire_avancement_valide(self):
        self.avancement("t1", {"points": [{"texte": "APK reconstruit", "fait": True}, {"texte": "Note", "fait": False}],
                               "en_cours": "réécrit la note"})
        a = detache.lire_avancement(self.dossier_agents() / "t1.avancement.json")
        self.assertEqual(a["points"], [{"texte": "APK reconstruit", "fait": True}, {"texte": "Note", "fait": False}])
        self.assertEqual(a["en_cours"], "réécrit la note")
        self.assertTrue(a["maj"])

    def test_lire_avancement_illisible_rend_none(self):
        self.avancement("t1", '{"points": [{"texte": "a", ')              # à moitié écrit
        self.assertIsNone(detache.lire_avancement(self.dossier_agents() / "t1.avancement.json"))
        self.avancement("t2", {"points": "pas une liste"})
        self.assertIsNone(detache.lire_avancement(self.dossier_agents() / "t2.avancement.json"))
        self.assertIsNone(detache.lire_avancement(self.dossier_agents() / "absent.avancement.json"))

    def test_phase_du_flux(self):
        phase = lambda nom, entree: detache.phase_du_flux([self.outil(nom, entree)])
        self.assertEqual(phase("Read", {"file_path": "a.kt"}), "lecture")
        self.assertEqual(phase("Edit", {"file_path": "a.kt"}), "modification")
        self.assertEqual(phase("Bash", {"command": "gradlew assembleRelease"}), "compilation")
        self.assertEqual(phase("Bash", {"command": "py lancer.py tests"}), "tests")
        self.assertEqual(phase("Bash", {"command": "ls"}), "autre")
        self.assertIsNone(detache.phase_du_flux([{"type": "system"}]))

    def test_ajouter_au_travail_porte_avancement_et_phase(self):
        debut = time.time() - 60
        self.ecrire("t1", {"tache": "t1", "agent": "dev", "pid": os.getpid(), "debut": debut,
                           "dossier": str(self.dossier)}, [self.outil("Read", {"file_path": "a.kt"})])
        self.avancement("t1", {"points": [{"texte": "a", "fait": True}], "en_cours": "x"})
        taches = [{"id": "t1"}]
        detache.ajouter_au_travail(taches, self.factory_dir)
        t = taches[0]["travail"]
        self.assertEqual(t["phase"], "lecture")
        self.assertEqual(t["avancement"]["points"], [{"texte": "a", "fait": True}])

    def test_chaque_tache_d_un_lot_a_sa_propre_liste(self):
        self.ecrire("t1", {"tache": "t1", "taches": ["t1", "t2"], "agent": "dev", "pid": os.getpid(),
                           "debut": time.time() - 60, "dossier": str(self.dossier)}, [])
        self.avancement("t1", {"points": [{"texte": "un", "fait": True}]})
        self.avancement("t2", {"points": [{"texte": "deux", "fait": False}]})
        taches = [{"id": "t1"}, {"id": "t2"}]
        detache.ajouter_au_travail(taches, self.factory_dir)
        self.assertEqual(taches[0]["dans_le_lot"]["avancement"]["points"][0]["texte"], "un")
        self.assertEqual(taches[1]["travail"]["avancement"]["points"][0]["texte"], "deux")

    def lot_l5(self, liste_t68, liste_t69=None, attentes_tests=None):
        """Essai réel du 2026-11-18 (RoadmapReborn, lot L5) : t68 puis t69 confiées à Hugo (agent-1) dans une seule
        session, journal `t68.jsonl` ; le suivi ne marque active (avec son agent) que la première."""
        self.ecrire("t68", {"tache": "t68", "taches": ["t68", "t69"], "agent": "agent-1", "pid": os.getpid(),
                            "debut": time.time() - 900, "dossier": str(self.dossier), "lot": "L5"},
                    [self.outil("Edit", {"file_path": str(self.dossier / "backend" / "fiches_saisie.py")})])
        self.avancement("t68", liste_t68)
        if liste_t69 is not None:
            self.avancement("t69", liste_t69)
        taches = [{"id": "t68", "agent": "agent-1", "active": True, "lot": {"id": "L5", "rang": 1}},
                  {"id": "t69", "agent": None, "active": False, "lot": {"id": "L5", "rang": 2}}]
        detache.ajouter_au_travail(taches, self.factory_dir, attentes_tests=attentes_tests)
        return taches

    def test_lot_la_tache_suivante_est_active_avec_l_agent_une_fois_la_premiere_finie(self):
        t68, t69 = self.lot_l5({"points": [{"texte": "Modele", "fait": True}], "en_cours": "termine"},
                               {"points": [{"texte": "Zone texte", "fait": False}], "en_cours": "Ajout de la zone"})
        # t69, que la session fait : active, avec l'agent du lot, son activité et sa propre liste
        self.assertEqual((t69["active"], t69["agent"]), (True, "agent-1"))
        self.assertEqual(t69["travail"]["action"], "modifie backend/fiches_saisie.py")
        self.assertEqual(t69["travail"]["avancement"]["en_cours"], "Ajout de la zone")
        self.assertEqual(t69["travail"]["lot"], {"rang": 2, "total": 2})
        # t68 : finie, la session est passée à t69 ; plus d'activité à son nom ni de « En cours : termine »
        self.assertNotIn("travail", t68)
        self.assertFalse(t68["active"])
        self.assertEqual({k: t68["dans_le_lot"][k] for k in ("etat", "agent", "courante")},
                         {"etat": "faite", "agent": "agent-1", "courante": "t69"})
        self.assertIsNone(t68["dans_le_lot"]["avancement"]["en_cours"])
        self.assertTrue(t68["dans_le_lot"]["avancement"]["points"][0]["fait"])

    def test_lot_la_suivante_sans_liste_encore_est_quand_meme_la_tache_en_cours(self):
        t68, t69 = self.lot_l5({"points": [{"texte": "a", "fait": True}, {"texte": "b", "fait": True}]})
        self.assertEqual((t69["active"], t69["agent"]), (True, "agent-1"))
        self.assertIsNone(t69["travail"]["avancement"])          # pas encore de liste : la fiche dira sa phase
        self.assertEqual(t68["dans_le_lot"]["etat"], "faite")

    def test_lot_la_premiere_en_cours_garde_l_activite(self):
        t68, t69 = self.lot_l5({"points": [{"texte": "a", "fait": True}, {"texte": "b", "fait": False}],
                                "en_cours": "b"})
        self.assertEqual((t68["active"], t68["travail"]["lot"]["rang"]), (True, 1))
        self.assertEqual((t69["active"], t69["agent"], t69["dans_le_lot"]["etat"]), (False, "agent-1", "a_venir"))
        self.assertNotIn("travail", t69)

    def test_lot_tout_fini_la_derniere_reste_en_cours(self):
        """L'agent rédige son compte rendu : la dernière tâche du lot reste celle de la session."""
        self.assertEqual(detache.tache_du_lot_en_cours(["t1", "t2"], {"t1": {"en_cours": "Terminé."},
                                                                       "t2": {"en_cours": "termine"}}), "t2")
        self.assertFalse(detache.liste_finie({"points": [{"fait": True}], "en_cours": "relit le diff"}))
        self.assertFalse(detache.liste_finie(None))

    def test_l_attente_du_verrou_de_tests_va_sur_la_tache_en_cours(self):
        attente = {"depuis": "2026-11-18T14:40:00+01:00", "motif": "une campagne tourne déjà (processus 12)"}
        t68, t69 = self.lot_l5({"en_cours": "termine", "points": []}, {"points": [], "en_cours": "tests"},
                               attentes_tests={"t68": attente})      # la clé de l'agent : celle de son journal
        self.assertEqual(t69["travail"]["attente_tests"], attente)
        self.assertNotIn("travail", t68)

    def test_les_commandes_de_l_agent_connaissent_sa_cle(self):
        """`lancer.py tests` lancé par l'agent dit au bureau pour qui il attend le poste (voir `outils/campagne`)."""
        vu = {}

        class Faux:
            pid = os.getpid()

        def lancer(argv, entree, sortie, erreurs, env, cwd):
            vu["env"] = env
            return Faux()
        reg = detache.Registre(self.factory_dir, lancer=lancer)
        reg._lancer("t68", {"taches": ["t68", "t69"]}, ["claude"], b"", {"PATH": "x"}, str(self.dossier))
        # la clé de l'agent est donnée deux fois : pour `lancer.py tests` (le bureau sait pour qui l'agent attend le poste)
        # et pour `lancer.py deporter` (son fichier d'attente est le sien)
        self.assertEqual(vu["env"], {"PATH": "x", detache.VARIABLE_TACHE: "t68", detache.VARIABLE_AGENT: "t68"})

    def test_effacer_oublie_la_liste_de_chaque_tache_du_lot(self):
        self.ecrire("t1", {"tache": "t1", "taches": ["t1", "t2"], "pid": 1, "debut": 1}, [])
        self.avancement("t1", {"points": []})
        self.avancement("t2", {"points": []})
        detache.Registre(self.factory_dir).effacer("t1")
        self.assertFalse((self.dossier_agents() / "t2.avancement.json").exists())

    def test_phase_powershell_et_faux_amis(self):
        phase = lambda nom, c: detache.phase_du_flux([self.outil(nom, {"command": c})])
        self.assertEqual(phase("PowerShell", "py lancer.py tests --dossier x"), "tests")
        self.assertEqual(phase("PowerShell", "./gradlew assembleRelease"), "compilation")
        self.assertEqual(phase("Bash", "git log latest"), "autre")             # « latest » n'est pas « test »
        self.assertEqual(phase("Bash", "py lancer.py anomalies"), "autre")

    def test_une_liste_enorme_est_ignoree_ou_plafonnee(self):
        self.avancement("t1", {"points": [{"texte": str(i), "fait": False} for i in range(200)]})
        self.assertEqual(len(detache.lire_avancement(self.dossier_agents() / "t1.avancement.json")["points"]), 30)
        self.avancement("t2", '{"points": [], "en_cours": "' + "x" * 100000 + '"}')
        self.assertIsNone(detache.lire_avancement(self.dossier_agents() / "t2.avancement.json"))

    def test_l_avancement_n_est_pas_pris_pour_un_agent(self):
        self.avancement("t9", {"points": [], "en_cours": None})
        taches = [{"id": "t9"}]
        detache.ajouter_au_travail(taches, self.factory_dir)
        self.assertNotIn("travail", taches[0])
        self.assertEqual(detache.Registre(self.factory_dir).entrees(), [])

    def test_agent_mort_avec_resultat_est_dit_termine(self):
        debut = time.time() - 300
        flux = self.ecrire("t1", {"tache": "t1", "agent": "dev", "pid": 999999999, "debut": debut},
                           [{"type": "result", "result": "ok"}])
        os.utime(flux, (debut + 120, debut + 120))
        taches = [{"id": "t1"}]
        detache.ajouter_au_travail(taches, self.factory_dir)
        self.assertNotIn("travail", taches[0])
        from datetime import datetime
        self.assertAlmostEqual(datetime.fromisoformat(taches[0]["agent_termine"]["t"]).timestamp(), debut + 120, delta=1)

    def test_effacer_oublie_avancement(self):
        self.ecrire("t1", {"tache": "t1", "pid": 1, "debut": 1}, [])
        self.avancement("t1", {"points": []})
        detache.Registre(self.factory_dir).effacer("t1")
        self.assertFalse((self.dossier_agents() / "t1.avancement.json").exists())

    def test_une_commande_est_dite_sans_son_contenu(self):
        lignes = [self.outil("Bash", {"command": "python outils/build.py --token=abc123"})]
        self.assertEqual(detache.derniere_action(lignes, None), "lance python")
        cd = [self.outil("Bash", {"command": "cd C:/projet && python tools/lancer_tests.py 2>&1 | tail -40"})]
        self.assertEqual(detache.derniere_action(cd, None), "lance python")       # pas « lance cd »
        chaine = [self.outil("Bash", {"command": "cd C:/p && ls tests && grep -n x a.json && py -3.12 tools/t.py | tail"})]
        self.assertEqual(detache.derniere_action(chaine, None), "lance py")       # le dernier, pas « lance ls »
        self.assertEqual(detache.derniere_action([self.outil("Write", {"file_path": "/ailleurs/x.txt"})], "/projet"),
                         "écrit x.txt")
        self.assertEqual(detache.derniere_action([self.outil("Grep", {"pattern": "secret"})], None),
                         "cherche dans les fichiers")
        texte = {"type": "assistant", "message": {"content": [{"type": "text", "text": "Je pense que…"}]}}
        self.assertEqual(detache.derniere_action([texte], None), "rédige")
        self.assertIsNone(detache.derniere_action([{"type": "system"}], None))


class Durees(Base):
    def test_noter_et_lire_les_durees(self):
        detache.noter_duree(self.factory_dir, {"taches": ["t1", "t2"], "debut": 1000.0}, 1000.0 + 754)
        detache.noter_duree(self.factory_dir, {"tache": "t3", "debut": 1000.0}, 1000.0 + 61)
        detache.noter_duree(self.factory_dir, {"tache": "t4"}, 5.0)                     # sans début : rien
        self.assertEqual([(x["tache"], x["duree_s"]) for x in detache.lire_durees(self.factory_dir)],
                         [("t1", 754), ("t2", 754), ("t3", 61)])

    def test_lire_les_durees_sans_fichier_ou_abime(self):
        self.assertEqual(detache.lire_durees(self.factory_dir), [])
        (self.factory_dir / "durees-agents.jsonl").write_text('pas du json\n{"tache": "t1", "duree_s": 5}\n',
                                                              encoding="utf-8")
        self.assertEqual([x["tache"] for x in detache.lire_durees(self.factory_dir)], ["t1"])


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
        notees = detache.lire_durees(self.factory_dir)
        self.assertEqual([x["tache"] for x in notees], ["t1"])        # la durée réelle de l'agent, notée à sa fin
        self.assertGreaterEqual(notees[0]["duree_s"], 0)


if __name__ == "__main__":
    unittest.main()
