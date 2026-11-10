import json
import subprocess
import sys
import textwrap
from pathlib import Path

from bureau import releve
from orchestrateur import suivi
from tests.orch_aide import PNG, RACINE, AvecProjet


class TestSuivi(AvecProjet):
    def releve(self):
        return self.ok("releve")

    def nouvelle(self, texte="Une page d'accueil", images=None):
        demande = {"type": "fonctionnalite", "texte": texte, "t": "2026-11-10T10:00:00+01:00"}
        if images:
            demande["images"] = images
        code, sortie = self.outil("actions", entree=demande)
        self.assertEqual(code, 0, sortie)
        return self.ok("etat")["fonctionnalites"][-1]["id"]

    # --- lancer
    def test_lancer_prefere_la_commande_declaree(self):
        adaptateur = self.dossier / "adaptateur.py"
        adaptateur.write_text("import sys, json\nprint(json.dumps({'adapte': True, 'entree': sys.stdin.read()}))\n"
                              "sys.exit(0)\n", encoding="utf-8")
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d["commandes"] = {"demandes": [sys.executable, "adaptateur.py"]}
        self.factory.write_text(json.dumps(d), encoding="utf-8")
        code, sortie = self.outil("lancer", "demandes", entree={"x": 1})
        self.assertEqual(code, 0)
        self.assertTrue(sortie["adapte"])
        self.assertEqual(json.loads(sortie["entree"]), {"x": 1})   # la même entrée
        code, sortie = self.outil("lancer", "etat")   # non déclarée : la commande générique
        self.assertEqual(code, 0)
        self.assertIn("fonctionnalites", sortie)
        code, sortie = self.outil("lancer", "inconnue")
        self.assertEqual(code, 2)

    def test_la_commande_declaree_garde_son_code_de_sortie(self):
        (self.dossier / "refus.py").write_text("print('{\"erreur\": \"non\"}')\nraise SystemExit(1)\n", encoding="utf-8")
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d["commandes"] = {"etat": [sys.executable, "refus.py"]}
        self.factory.write_text(json.dumps(d), encoding="utf-8")
        code, sortie = self.outil("lancer", "etat")
        self.assertEqual((code, sortie), (1, {"erreur": "non"}))

    # --- relevé
    def test_releve_vide_est_valide(self):
        r = self.releve()
        self.assertEqual(releve.valider(r), [])
        self.assertEqual(r["version"], 4)
        self.assertEqual([c["id"] for c in r["colonnes"]], ["cadrage", "dev", "relecture", "fait"])
        self.assertTrue(r["colonnes"][-1]["terminee"])
        self.assertEqual(sum(1 for t in r["titulaires"] if t.get("chef")), 1)
        self.assertEqual([t["cle"] for t in r["titulaires"] if not t.get("chef")], ["metier-1", "dev-1"])
        self.assertEqual([a["id"] for a in r["actions"]], ["pause"])

    def test_releve_est_un_releve_v4_valide(self):
        f = self.nouvelle("Une page d'accueil", images=[{"nom": "ref.png", "type": "image/png", "donnees": PNG}])
        self.ok("fonctionnalite", entree={"id": f, "agent_cadrage": "metier-1", "catalogue": True,
                                          "cahier": {"maquette": ["pieces/maquette.png"], "etapes": ["Écran", "Menu"]},
                                          "methode": {"version": 1, "chemin": "methode.md"}})
        self.ok("message", entree={"fonctionnalite": f, "auteur": "metier-1", "texte": "Bonjour"})
        self.ok("decision", entree={"action": "poser", "portee": f, "genre": "valider_cahier", "texte": "Cahier prêt"})
        self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "session_cloud",
                                    "texte": "Créer la session", "agent": "dev-1"})
        self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "confirmer_genre",
                                    "texte": "Quel genre ?", "propose": "vitrine", "genres_connus": []})
        self.ok("file", entree={"fonctionnalite": f, "elements": [{"id": "e1", "nom": "Élément 1", "groupe": "g"}]})
        self.ok("file-prendre", entree={"fonctionnalite": f})
        self.ok("tache", entree={"titre": "Développer e1", "fonctionnalite": f, "element": "e1", "role": "dev",
                                 "colonne": "dev", "agent": "dev-1", "montee": {"de": "Haiku", "a": "Sonnet", "raison": "ok"}})
        self.outil("actions", entree={"type": "retour", "tache": "t1", "texte": "Plus haut"})
        r = self.releve()
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        fonc = r["fonctionnalites"][0]
        self.assertEqual(fonc["etape"], "cadrage")
        self.assertTrue(fonc["discussion"][0]["images"][0].startswith("pieces/"))   # relatif aux réglages
        self.assertEqual(fonc["cahier"]["maquette"], ["pieces/maquette.png"])
        self.assertTrue(fonc["catalogue"])
        t1 = next(t for t in r["taches"] if t["id"] == "t1")
        self.assertEqual(t1["titulaire"], "dev-1")
        self.assertEqual(t1["retours"][0]["texte"], "Plus haut")
        self.assertEqual(r["file"]["visibles"], [])   # e1 est prise par la tâche
        self.assertEqual(len(r["decisions_projet"]), 2)

    def test_releve_tache_de_cadrage_et_chef(self):
        f = self.nouvelle()
        self.ok("fonctionnalite", entree={"id": f, "agent_cadrage": "metier-1"})
        r = self.releve()
        cadrage = next(t for t in r["taches"] if t["id"] == f"cadrage:{f}")
        self.assertEqual((cadrage["colonne"], cadrage["titulaire"], cadrage["active"]), ("cadrage", "metier-1", True))
        self.assertTrue(cadrage["titre"].startswith("Cadrage : "))
        orchestration = next(t for t in r["taches"] if t["titulaire"] == "chef")
        self.assertEqual(orchestration["titre"], "Orchestration")
        self.assertIsNone(orchestration["maj"])   # pas encore de réveil
        self.ok("reveil")
        orchestration = next(t for t in self.releve()["taches"] if t["titulaire"] == "chef")
        self.assertIsNotNone(orchestration["maj"])

    def test_pause_par_le_bureau(self):
        self.outil("actions", entree={"type": "bouton", "id": "pause", "t": "2026-11-10T10:00:00+01:00"})
        r = self.releve()
        self.assertEqual(r["factory"]["etat"], "en pause")
        self.assertEqual([a["id"] for a in r["actions"]], ["reprendre"])
        self.outil("actions", entree={"type": "bouton", "id": "reprendre"})
        self.assertEqual(self.releve()["factory"]["etat"], "en marche")

    # --- actions
    def test_actions_fonctionnalite_creee_avec_image(self):
        f = self.nouvelle("Une très longue description de la fonctionnalité voulue par l'utilisateur",
                          images=[{"nom": "ref.png", "type": "image/png", "donnees": PNG}])
        etat = self.ok("etat")
        fonc = etat["fonctionnalites"][0]
        self.assertEqual((fonc["id"], fonc["etape"], fonc["attend_reponse"]), (f, "cadrage", True))
        self.assertEqual(len(fonc["nom"]), 40)
        fichiers = list((self.dossier / "pieces" / f).glob("*-ref.png"))
        self.assertEqual(len(fichiers), 1)
        self.assertTrue(fichiers[0].read_bytes().startswith(b"\x89PNG"))
        message = suivi.Suivi(self.dossier / "suivi.json").lire()["fonctionnalites"][0]["discussion"][0]
        self.assertEqual(message["auteur"], "utilisateur")
        self.assertEqual(message["images"], [f"pieces/{f}/{fichiers[0].name}"])
        r = self.releve()
        self.assertEqual(r["fonctionnalites"][0]["discussion"][0]["images"], [f"pieces/{f}/{fichiers[0].name}"])
        self.assertEqual(releve.valider(r), [])

    def test_actions_message_puis_reponse_de_l_agent(self):
        f = self.nouvelle()
        self.ok("message", entree={"fonctionnalite": f, "auteur": "metier-1", "texte": "Quelle couleur ?"})
        self.assertFalse(self.ok("etat")["fonctionnalites"][0]["attend_reponse"])
        self.outil("actions", entree={"type": "message", "fonctionnalite": f, "texte": "Bleue"})
        self.assertTrue(self.ok("etat")["fonctionnalites"][0]["attend_reponse"])

    def test_message_agent_remet_attend_reponse(self):
        f = self.nouvelle()
        self.assertTrue(self.ok("etat")["fonctionnalites"][0]["attend_reponse"])
        sortie = self.ok("message", entree={"fonctionnalite": f, "auteur": "metier-1", "texte": "Bonjour"})
        self.assertIn("id", sortie)
        fonc = self.ok("etat")["fonctionnalites"][0]
        self.assertFalse(fonc["attend_reponse"])
        r = self.releve()
        self.assertFalse(r["fonctionnalites"][0]["attend_reponse"])
        self.assertEqual(r["fonctionnalites"][0]["discussion"][-1]["auteur"], "metier-1")

    def test_message_auteur_ou_fonctionnalite_inconnus(self):
        f = self.nouvelle()
        self.assertEqual(self.outil("message", entree={"fonctionnalite": f, "auteur": "inconnu", "texte": "x"})[0], 1)
        self.assertEqual(self.outil("message", entree={"fonctionnalite": "f99", "auteur": "metier-1", "texte": "x"})[0], 1)

    def test_actions_journal(self):
        self.outil("actions", entree={"type": "retour", "tache": "t1", "texte": "Un", "t": "2026-11-10T10:00:00+01:00"})
        self.outil("actions", entree={"type": "bouton", "id": "pause", "t": "2026-11-10T10:00:01+01:00"})
        lignes = (self.dossier / "demandes.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(x)["type"] for x in lignes], ["retour", "bouton"])
        self.assertIn("id", json.loads(lignes[0]))

    def test_journal_sans_les_donnees_des_images(self):
        self.nouvelle(images=[{"nom": "ref.png", "type": "image/png", "donnees": PNG}])
        texte = (self.dossier / "demandes.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(PNG, texte)
        self.assertIn("pieces/f1/", texte)

    def test_actions_refuse_une_image_hostile(self):
        for image in ({"nom": "../x.png", "type": "image/png", "donnees": PNG},
                      {"nom": "a.png", "type": "image/png", "donnees": "pas du base64 !"}):
            code, sortie = self.outil("actions", entree={"type": "fonctionnalite", "texte": "x", "images": [image]})
            self.assertEqual(code, 1)
            self.assertIsInstance(sortie, str)   # le bureau montre la première ligne : du texte, pas du JSON
        self.assertEqual(self.ok("etat")["fonctionnalites"], [])

    def test_demandes_et_demande_traitee(self):
        self.outil("actions", entree={"type": "retour", "tache": "t1", "texte": "A"})
        self.outil("actions", entree={"type": "retour", "tache": "t1", "texte": "B"})
        en_attente = self.ok("demandes")["demandes"]
        self.assertEqual([d["texte"] for d in en_attente], ["A", "B"])   # les plus anciennes d'abord
        self.ok("demande-traitee", entree={"id": en_attente[0]["id"], "reponse": "Fait"})
        self.assertEqual([d["texte"] for d in self.ok("demandes")["demandes"]], ["B"])
        self.assertEqual(self.outil("demande-traitee", entree={"id": "d99"})[0], 1)
        self.assertEqual(self.outil("demande-traitee", entree={"id": en_attente[0]["id"]})[0], 1)   # déjà traitée

    def test_reponse_a_un_retour_dans_le_releve(self):
        self.ok("tache", entree={"titre": "T", "colonne": "dev"})
        self.outil("actions", entree={"type": "retour", "tache": "t1", "texte": "Plus haut"})
        d = self.ok("demandes")["demandes"][0]
        self.ok("demande-traitee", entree={"id": d["id"], "reponse": "Corrigé"})
        retour = next(t for t in self.releve()["taches"] if t["id"] == "t1")["retours"][0]
        self.assertEqual((retour["texte"], retour["reponse"]), ("Plus haut", "Corrigé"))

    # --- décisions
    def test_decision_poser_lever(self):
        f = self.nouvelle()
        a = self.ok("decision", entree={"action": "poser", "portee": f, "genre": "valider_cahier", "texte": "Cahier"})
        b = self.ok("decision", entree={"action": "poser", "portee": f, "genre": "valider_cahier", "texte": "Cahier"})
        self.assertEqual(a["id"], b["id"])   # poser deux fois la même décision n'en crée qu'une
        self.assertEqual(len(self.ok("etat")["decisions"]), 1)
        self.ok("decision", entree={"action": "lever", "id": a["id"]})
        self.assertEqual(self.ok("etat")["decisions"], [])
        self.assertEqual(self.outil("decision", entree={"action": "lever", "id": a["id"]})[0], 1)

    def test_decision_refusee(self):
        f = self.nouvelle()
        for entree in ({"action": "poser", "portee": f, "genre": "confirmer_genre", "texte": "x"},   # genre du projet
                       {"action": "poser", "portee": "projet", "genre": "valider_cahier", "texte": "x"},
                       {"action": "poser", "portee": "f99", "genre": "valider_cahier", "texte": "x"},
                       {"action": "poser", "portee": "projet", "genre": "session_cloud", "texte": "x", "agent": "inconnu"},
                       {"action": "poser", "portee": "projet", "genre": "confirmer_genre", "texte": "x"}):
            self.assertEqual(self.outil("decision", entree=entree)[0], 1, entree)

    # --- tâches
    def test_tache_creation_et_montee(self):
        t = self.ok("tache", entree={"titre": "Développer e1", "role": "dev", "colonne": "dev", "agent": "dev-1",
                                     "modele_depart": "Haiku"})
        self.assertEqual(t["id"], "t1")
        self.assertTrue(t["active"])
        self.ok("tache", entree={"id": "t1", "montee": {"de": "Haiku", "a": "Sonnet", "raison": "écran complexe"},
                                 "journal": "Monté d'un cran", "etape": "Mise en page"})
        r = self.releve()
        tache = next(x for x in r["taches"] if x["id"] == "t1")
        self.assertEqual(tache["montee"], {"de": "Haiku", "a": "Sonnet", "raison": "écran complexe"})
        self.assertEqual(tache["modele_depart"], "Haiku")
        self.assertEqual(tache["journal"][-1]["texte"], "Monté d'un cran")
        self.assertEqual(releve.valider(r), [])
        self.assertEqual(self.ok("tache", entree={"id": "t1", "colonne": "fait"})["active"], False)

    def test_tache_refus(self):
        self.ok("tache", entree={"titre": "A", "colonne": "dev", "agent": "dev-1"})
        for entree in ({"titre": "B", "colonne": "dev", "agent": "dev-1"},        # un agent, une tâche
                       {"titre": "B", "colonne": "inconnue"},
                       {"titre": "B", "agent": "inconnu"},
                       {"titre": "B", "fonctionnalite": "f99"},
                       {"id": "t99", "etape": "x"},
                       {"titre": "B", "montee": {"de": "Opus", "a": "Fable", "raison": "x"}},   # jamais Fable
                       {"colonne": "dev"}):
            self.assertEqual(self.outil("tache", entree=entree)[0], 1, entree)

    def test_file_prendre_dans_l_ordre(self):
        f = self.nouvelle()
        self.ok("file", entree={"fonctionnalite": f, "elements": [
            {"id": "e1", "nom": "Un"}, {"id": "e2", "nom": "Deux", "groupe": "g"}, {"id": "e3", "nom": "Trois"}]})
        r = self.releve()
        self.assertEqual([q["titre"] for q in r["file"]["visibles"]], ["Un", "Deux", "Trois"])
        self.assertEqual(releve.valider(r), [])
        self.assertEqual(self.ok("file-prendre", entree={"fonctionnalite": f})["element"]["id"], "e1")
        self.assertEqual(self.ok("file-prendre", entree={"fonctionnalite": f})["element"],
                         {"id": "e2", "nom": "Deux", "groupe": "g"})
        self.assertEqual(self.ok("file-prendre", entree={"fonctionnalite": f})["element"]["id"], "e3")
        self.assertIsNone(self.ok("file-prendre", entree={"fonctionnalite": f})["element"])
        self.assertEqual(self.outil("file", entree={"fonctionnalite": "f99", "elements": []})[0], 1)
        self.assertEqual(self.outil("file", entree={"fonctionnalite": f, "elements": [{"id": "a", "nom": "A"},
                                                                                       {"id": "a", "nom": "B"}]})[0], 1)

    def test_file_longue_garde_le_releve_valide(self):
        f = self.nouvelle()
        self.ok("file", entree={"fonctionnalite": f, "elements": [{"id": f"e{i}", "nom": f"E{i}"} for i in range(700)]})
        r = self.releve()
        self.assertEqual(releve.valider(r), [])
        self.assertEqual(len(r["file"]["visibles"]) + len(r["file"]["suite"]) + 0, 505)   # 5 visibles + 500 en suite
        self.assertEqual(r["file"]["reste"], 695)

    # --- sessions, catalogue
    def test_session(self):
        self.ok("session", entree={"agent": "dev-1", "session": "Session dev 1"})
        self.assertEqual(json.loads((self.dossier / "sessions.json").read_text(encoding="utf-8")),
                         {"dev-1": "Session dev 1"})
        agent = next(a for a in self.ok("etat")["agents"] if a["cle"] == "dev-1")
        self.assertEqual(agent["session"], "Session dev 1")
        self.assertEqual(self.outil("session", entree={"agent": "inconnu", "session": "x"})[0], 1)

    def test_catalogue_generique(self):
        f = self.nouvelle()
        self.ok("file", entree={"fonctionnalite": f, "elements": [{"id": "e1", "nom": "Un", "groupe": "g"},
                                                                  {"id": "e2", "nom": "Deux"}]})
        self.ok("fonctionnalite", entree={"id": f, "methode": {"version": 2, "chemin": "m.md"}})
        e1 = self.ok("file-prendre", entree={"fonctionnalite": f})["element"]
        self.ok("tache", entree={"titre": "E1", "fonctionnalite": f, "element": e1["id"], "colonne": "dev",
                                 "captures": ["pieces/e1.png"]})
        self.ok("tache", entree={"id": "t1", "colonne": "fait"})
        c = self.ok("catalogue", entree={"fonctionnalite": f})
        self.assertEqual({e["id"]: e["etat"] for e in c["elements"]}, {"e1": "fait", "e2": "a_faire"})
        un = next(e for e in c["elements"] if e["id"] == "e1")
        self.assertEqual(un["captures"], [{"chemin": "pieces/e1.png", "passe": 2}])
        self.assertEqual(un["groupe"], "g")
        self.assertEqual(c["groupes"], [{"id": "g", "nom": "g"}])
        from bureau import catalogue
        propre, avertissements = catalogue.valider(c)
        self.assertEqual(avertissements, [])
        code, _ = self.outil("catalogue", entree={"fonctionnalite": "f99"})
        self.assertEqual(code, 1)

    def test_catalogue_retour_d_un_element(self):
        f = self.nouvelle()
        self.ok("file", entree={"fonctionnalite": f, "elements": [{"id": "e1", "nom": "Un"}]})
        self.outil("actions", entree={"type": "retour_element", "fonctionnalite": f, "element": "e1", "texte": "Plus grand"})
        c = self.ok("catalogue", entree={"fonctionnalite": f})
        self.assertEqual(c["elements"][0]["retours"][0]["texte"], "Plus grand")

    # --- charge
    def test_charge_lance_la_commande_de_la_skill(self):
        skill = self.dossier / "skill"
        skill.mkdir()
        (skill / "lancer.py").write_text(textwrap.dedent("""
            import sys
            print("attendre : charge 90 % (max 75 %)" if "--reglages" in sys.argv else "?")
            sys.exit(1)
        """), encoding="utf-8")
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d["skill"] = "skill"
        self.factory.write_text(json.dumps(d), encoding="utf-8")
        self.assertEqual(self.ok("charge"), {"feu_vert": False, "texte": "attendre : charge 90 % (max 75 %)"})
        (skill / "lancer.py").write_text("print('ok : charge 10 %')\n", encoding="utf-8")
        self.assertEqual(self.ok("charge"), {"feu_vert": True, "texte": "ok : charge 10 %"})
        (skill / "lancer.py").write_text("import sys\nprint('Réglages illisibles')\nsys.exit(2)\n", encoding="utf-8")
        self.assertEqual(self.outil("charge")[0], 1)

    # --- écritures concurrentes, codes de sortie
    def test_ecritures_concurrentes(self):
        script = textwrap.dedent("""
            import sys
            sys.path.insert(0, sys.argv[1])
            from orchestrateur import outil
            for i in range(25):
                code, objet = outil.executer(sys.argv[2], ["tache"], {"titre": sys.argv[3] + str(i), "colonne": "dev"})
                assert code == 0, objet
        """)
        procs = [subprocess.Popen([sys.executable, "-c", script, str(RACINE), str(self.factory), nom],
                                  stderr=subprocess.PIPE) for nom in ("a", "b")]
        for p in procs:
            _, erreurs = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, erreurs.decode())
        taches = suivi.Suivi(self.dossier / "suivi.json").lire()["taches"]
        self.assertEqual(len(taches), 50)
        self.assertEqual(len({t["id"] for t in taches}), 50)   # aucun identifiant en double

    def test_verrou_perime_est_repris(self):
        s = suivi.Suivi(self.dossier / "suivi.json")
        s.verrou.write_text("", encoding="utf-8")
        import os
        vieux = s.verrou.stat().st_mtime - 3600
        os.utime(s.verrou, (vieux, vieux))
        with s.transaction() as donnees:
            donnees["reveil"] = "x"
        self.assertEqual(s.lire()["reveil"], "x")

    def test_codes_de_sortie(self):
        code, sortie = self.outil("etat")
        self.assertEqual(code, 0)
        self.assertIsInstance(sortie, dict)
        code, sortie = self.outil("demande-traitee", entree={"id": "d99"})
        self.assertEqual(code, 1)
        self.assertIn("erreur", sortie)
        for commande, entree in (("inconnue", None), ("tache", None)):   # commande inconnue, entrée absente
            code, sortie = self.outil(commande, entree=entree)
            self.assertEqual(code, 2, commande)
            self.assertIn("erreur", sortie)
        p = subprocess.run([sys.executable, str(RACINE / "orchestrateur" / "outil.py"), "--factory", str(self.factory),
                            "tache"], input=b"pas du json", capture_output=True)
        self.assertEqual(p.returncode, 2)
        p = subprocess.run([sys.executable, str(RACINE / "orchestrateur" / "outil.py"), "--factory",
                            str(self.dossier / "absent.json"), "etat"], capture_output=True)
        self.assertEqual(p.returncode, 2)
        p = subprocess.run([sys.executable, str(RACINE / "orchestrateur" / "outil.py"), "etat"], capture_output=True)
        self.assertEqual(p.returncode, 2)
