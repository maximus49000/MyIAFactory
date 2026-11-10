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

    def test_etat_compact_et_detail_a_la_demande(self):
        # `etat` est relu à chaque réveil (sur le modèle le plus cher) : il reste court ; le détail se demande.
        f = self.nouvelle()
        for k in range(30):
            self.ok("message", entree={"fonctionnalite": f, "auteur": "metier-1", "texte": f"Message {k} " + "x" * 400})
        t = self.ok("tache", entree={"titre": "Dev", "fonctionnalite": f, "agent": "dev-1", "colonne": "dev",
                                     "journal": ["étape %d" % k for k in range(40)]})
        self.ok("tache", entree={"titre": "Ancienne", "colonne": "fait"})
        self.ok("lecon", entree={"action": "noter", "agent": "dev-1", "texte": "Une leçon " + "y" * 500,
                                 "etage_propose": "projet", "roles": ["dev"]})
        e = self.ok("etat")
        self.assertLess(len(json.dumps(e, ensure_ascii=False)), 4000)
        fonc = e["fonctionnalites"][0]
        self.assertNotIn("discussion", fonc)
        self.assertEqual(fonc["messages"], 31)
        self.assertEqual(fonc["dernier_message"]["auteur"], "metier-1")
        self.assertLessEqual(len(fonc["dernier_message"]["texte"]), 300)
        dev = next(x for x in e["taches"] if x["id"] == t["id"])
        self.assertEqual((dev["journal"], dev["dernier_journal"]), (40, "étape 39"))
        self.assertNotIn("Ancienne", [x["titre"] for x in e["taches"]])          # les tâches faites sont comptées
        self.assertEqual(e["taches_faites"], 1)
        self.assertNotIn("texte", e["lecons"][0])
        # Le détail, quand il sert.
        d = self.ok("detail", entree={"fonctionnalite": f})
        self.assertEqual(len(d["discussion"]), 31)
        self.assertEqual(len(self.ok("detail", entree={"tache": t["id"]})["journal"]), 40)
        self.assertTrue(self.ok("detail", entree={"lecons": True})["lecons"][0]["texte"].startswith("Une leçon"))
        for entree in ({}, {"fonctionnalite": "f99"}, {"tache": "t99"}):
            self.assertEqual(self.outil("detail", entree=entree)[0], 1, entree)

    def test_etat_donne_l_empreinte_des_consignes(self):
        # Un orchestrateur lancé avant une mise à jour de la skill voit, dans `etat`, que ses consignes ont changé.
        consignes = self.dossier / "consignes-projet.md"
        consignes.write_text("Règle 1.", encoding="utf-8")
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["consignes"] = "consignes-projet.md"
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        a = self.ok("etat")["consignes"]
        self.assertRegex(a, r"^[0-9a-f]{12}$")
        self.assertEqual(self.ok("etat")["consignes"], a)          # stable
        consignes.write_text("Règle 1. Règle 2.", encoding="utf-8")
        self.assertNotEqual(self.ok("etat")["consignes"], a)       # les consignes propres comptent aussi

    def test_usage_et_facturation(self):
        # L'orchestrateur note les tokens de chaque exécution d'agent ; le relevé les donne au bureau (facturation).
        t = self.ok("tache", entree={"titre": "Dev", "agent": "dev-1", "colonne": "dev"})
        u = self.ok("usage", entree={"agent": "dev-1", "tache": t["id"], "modele": "Sonnet", "etape": "Développement",
                                     "entree": 1000, "sortie": 200})
        # Les compteurs d'un même usage sont des cumuls : on republie le même id avec des nombres plus grands.
        self.ok("usage", entree={"id": u["id"], "agent": "dev-1", "tache": t["id"], "modele": "Sonnet",
                                 "entree": 3000, "sortie": 500, "cache_lecture": 10})
        # Seul un total est connu (sous-agent) : il compte comme des tokens d'entrée (estimation basse).
        v = self.ok("usage", entree={"agent": "metier-1", "modele": "Opus", "total": 4200})
        r = self.releve()
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        us = {x["id"]: x for x in r["usage"]}
        self.assertEqual((us[u["id"]]["entree"], us[u["id"]]["sortie"], us[u["id"]]["cache_lecture"]), (3000, 500, 10))
        self.assertEqual((us[u["id"]]["tache"], us[u["id"]]["agent"], us[u["id"]]["etape"]), (t["id"], "dev-1", "Développement"))
        self.assertEqual((us[v["id"]]["entree"], us[v["id"]]["sortie"], us[v["id"]]["tache"]), (4200, 0, None))
        self.assertTrue(all(x["t"] for x in us.values()))
        for entree in ({"modele": "Sonnet"},                                         # pas de tokens
                       {"modele": "Sonnet", "entree": -1, "sortie": 0},
                       {"modele": "Sonnet", "entree": 1, "sortie": 1, "agent": "inconnu"},
                       {"modele": "Sonnet", "entree": 1, "sortie": 1, "tache": "t99"},
                       {"entree": 1, "sortie": 1},                                    # pas de modèle
                       {"modele": "Sonnet", "total": 5, "entree": 1, "sortie": 1},    # l'un ou l'autre
                       {"id": "u99", "modele": "Sonnet", "entree": 1, "sortie": 1}):  # id inconnu
            self.assertEqual(self.outil("usage", entree=entree)[0], 1, entree)

    def test_message_avec_questions_a_choix(self):
        f = self.nouvelle()
        q = [{"texte": "Quelle taille ?", "choix": ["28 px", "56 px"]},
             {"texte": "Quels fonds ?", "choix": ["Clair", "Sombre"], "multiple": True}]
        self.ok("message", entree={"fonctionnalite": f, "auteur": "metier-1", "texte": "Deux questions", "questions": q})
        r = self.releve()
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        self.assertEqual(r["fonctionnalites"][0]["discussion"][-1]["questions"], q)
        for mauvais in ({"auteur": "metier-1", "questions": [{"texte": "T", "choix": ["seul"]}]},
                        {"auteur": "utilisateur", "questions": q}):              # seul un agent pose des questions
            entree = {"fonctionnalite": f, "texte": "x", **mauvais}
            self.assertEqual(self.outil("message", entree=entree)[0], 1, mauvais)

    def test_document_livrable_d_un_element(self):
        # Le livrable final d'un élément validé : ses fichiers, inscrits avec l'élément et `livrable`.
        f = self.nouvelle()
        self.ok("document", entree={"fonctionnalite": f, "chemin": "livrables/e1-28.png", "titre": "E1, 28 px",
                                    "element": "e1", "livrable": True, "agent": "dev-1"})
        self.ok("document", entree={"fonctionnalite": f, "chemin": "notes.md", "titre": "Notes"})
        docs = {d["chemin"]: d for d in self.releve()["fonctionnalites"][0]["documents"]}
        self.assertIs(docs["livrables/e1-28.png"]["livrable"], True)
        self.assertNotIn("livrable", docs["notes.md"])
        self.assertEqual(self.outil("document", entree={"fonctionnalite": f, "chemin": "a.png", "titre": "A",
                                                        "livrable": "oui"})[0], 1)

    def test_challenger_une_lecon_ouvre_une_tache(self):
        # Le Directeur challenge une leçon : une tâche s'ouvre, la discussion y a lieu (le texte, puis les réponses).
        self.ok("lecon", entree={"action": "noter", "agent": "dev-1", "texte": "Toujours 3 passes.",
                                 "etage_propose": "projet", "roles": ["dev"]})
        lecon = self.releve()["lecons"][0]["id"]
        r = self.ok("actions", entree={"type": "challenge", "cible": {"type": "lecon", "id": lecon},
                                       "texte": "Pourquoi trois ?", "t": "2026-11-10T12:00:00+01:00"})
        rel = self.releve()
        t = next(x for x in rel["taches"] if x["titre"].startswith("Challenge de la leçon"))
        self.assertEqual(t["retours"][0]["texte"], "Pourquoi trois ?")
        self.assertEqual(releve.valider(rel), [], releve.valider(rel))
        self.ok("demande-traitee", entree={"id": r["id"], "reponse": "Parce que le relecteur B trouve encore des erreurs."})
        t = next(x for x in self.releve()["taches"] if x["id"] == t["id"])
        self.assertEqual(t["retours"][0]["reponse"], "Parce que le relecteur B trouve encore des erreurs.")
        self.assertIn(lecon, t["titre"])
        self.assertEqual(next(x for x in self.releve()["lecons"] if x["id"] == lecon)["challenge_tache"], t["id"])
        self.assertEqual(self.outil("actions", entree={"type": "challenge", "cible": {"type": "lecon", "id": "inconnue"},
                                                       "texte": "x"})[0], 1)

    def test_document_qui_en_remplace_un_autre(self):
        f = self.nouvelle()
        self.ok("document", entree={"fonctionnalite": f, "chemin": "pieces/v1.png", "titre": "Maquette"})
        self.ok("document", entree={"fonctionnalite": f, "chemin": "pieces/v2.png", "titre": "Maquette v2",
                                    "remplace": "pieces/v1.png"})
        docs = {d["chemin"]: d for d in self.releve()["fonctionnalites"][0]["documents"]}
        self.assertEqual(docs["pieces/v2.png"]["remplace"], "pieces/v1.png")
        self.assertIn("pieces/v1.png", docs)   # l'ancienne version reste : c'est l'historique
        self.assertEqual(self.outil("document", entree={"fonctionnalite": f, "chemin": "pieces/v3.png", "titre": "M",
                                                        "remplace": "pieces/absent.png"})[0], 1)

    def test_glossaire_de_la_fonctionnalite(self):
        # Les mots définis par les agents sont gardés par la fonctionnalité (une seule fois), écrits dans
        # glossaire.md (rangé dans ses documents), donnés par `etat` et dans le message de départ des agents.
        f = self.nouvelle()
        self.ok("fonctionnalite", entree={"id": f, "agent_cadrage": "metier-1"})
        self.ok("message", entree={"fonctionnalite": f, "auteur": "metier-1", "texte": "Des tesselles.",
                                   "glossaire": [{"mot": "Tesselle", "definition": "Petit cube de mosaïque."},
                                                 {"mot": "Smalt", "definition": "Verre coloré."}]})
        self.ok("message", entree={"fonctionnalite": f, "auteur": "metier-1", "texte": "Précision.",
                                   "glossaire": [{"mot": "tesselle", "definition": "Petit cube de pierre ou de verre."}]})
        self.ok("fonctionnalite", entree={"id": f, "glossaire": [{"mot": "Or byzantin", "definition": "Fond doré."}]})
        r = self.releve()
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        g = r["fonctionnalites"][0]["glossaire"]
        self.assertEqual([x["mot"] for x in g], ["Smalt", "tesselle", "Or byzantin"])
        self.assertEqual(g[1]["definition"], "Petit cube de pierre ou de verre.")
        self.assertEqual(g[1]["ajoute_par"], "metier-1")
        fichier = self.dossier / "pieces" / f / "glossaire.md"
        texte = fichier.read_text(encoding="utf-8")
        self.assertIn("**tesselle**", texte)
        self.assertIn("Petit cube de pierre ou de verre.", texte)
        self.assertNotIn("Petit cube de mosaïque.", texte)
        self.assertIn(f"pieces/{f}/glossaire.md", [d["chemin"] for d in r["fonctionnalites"][0]["documents"]])
        self.assertEqual(self.ok("etat")["fonctionnalites"][0]["glossaire"], 3)   # compté dans etat
        self.assertEqual(len(self.ok("detail", entree={"fonctionnalite": f})["glossaire"]), 3)
        t = self.ok("tache", entree={"titre": "Dev", "fonctionnalite": f, "agent": "dev-1", "colonne": "dev"})
        depart = self.ok("depart", entree={"agent": "dev-1", "tache": t["id"]})["message"]
        self.assertIn("Vocabulaire de la fonctionnalité", depart)
        self.assertIn("Smalt : Verre coloré.", depart)
        for mauvais in ({"auteur": "utilisateur", "glossaire": [{"mot": "a", "definition": "b"}]},
                        {"auteur": "metier-1", "glossaire": [{"mot": "a"}]}):
            self.assertEqual(self.outil("message", entree={"fonctionnalite": f, "texte": "x", **mauvais})[0], 1, mauvais)

    def test_tache_lignes_produites(self):
        t = self.ok("tache", entree={"titre": "Dev", "colonne": "dev", "lignes": 85})
        self.assertEqual(next(x for x in self.releve()["taches"] if x["id"] == t["id"])["lignes"], 85)
        self.ok("tache", entree={"id": t["id"], "lignes": 120})          # le total de la tâche, remplacé
        self.assertEqual(next(x for x in self.releve()["taches"] if x["id"] == t["id"])["lignes"], 120)
        self.assertEqual(self.outil("tache", entree={"id": t["id"], "lignes": -3})[0], 1)

    def test_documents_de_la_fonctionnalite(self):
        # Tout ce qui est produit pour une fonctionnalité est rangé dans ses documents, avec son origine :
        # images de la discussion, maquettes du cahier, captures d'une tâche, et ce que l'orchestrateur y inscrit.
        f = self.nouvelle()
        self.ok("fonctionnalite", entree={"id": f, "agent_cadrage": "metier-1"})
        self.ok("message", entree={"fonctionnalite": f, "auteur": "metier-1", "texte": "Voici", "images": ["pieces/a.png"]})
        self.ok("fonctionnalite", entree={"id": f, "etape": "cahier",
                                          "cahier": {"maquette": ["pieces/m.png"], "etapes": ["x"]}})
        t = self.ok("tache", entree={"titre": "Dev : e1", "fonctionnalite": f, "element": "e1", "agent": "dev-1",
                                     "colonne": "dev", "captures": ["captures/e1.png"]})
        d = self.ok("document", entree={"fonctionnalite": f, "chemin": "methodes/m.md", "titre": "Méthode v1",
                                        "agent": "dev-1", "tache": t["id"], "sous_tache": "rédaction"})
        self.assertTrue(d["id"])
        # Le même chemin n'est rangé qu'une fois (la maquette renvoyée avec valide_le ne se double pas).
        self.ok("fonctionnalite", entree={"id": f, "cahier": {"maquette": ["pieces/m.png"], "etapes": ["x"],
                                                               "valide_le": "2026-11-10T12:00:00+01:00"}})
        r = self.releve()
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        docs = {x["chemin"]: x for x in r["fonctionnalites"][0]["documents"]}
        self.assertEqual(sorted(docs), ["captures/e1.png", "methodes/m.md", "pieces/a.png", "pieces/m.png"])
        self.assertEqual((docs["pieces/a.png"]["agent"], docs["pieces/a.png"]["etape"]), ("metier-1", "cadrage"))
        self.assertEqual((docs["pieces/m.png"]["agent"], docs["pieces/m.png"]["etape"]), ("metier-1", "cahier"))
        c = docs["captures/e1.png"]
        self.assertEqual((c["agent"], c["tache"], c["element"], c["etape"]), ("dev-1", t["id"], "e1", "dev"))
        self.assertEqual((docs["methodes/m.md"]["titre"], docs["methodes/m.md"]["sous_tache"]), ("Méthode v1", "rédaction"))
        self.assertTrue(all(x.get("date") for x in docs.values()))
        # Refus : fonctionnalité inconnue, chemin absent ou absolu.
        for entree in ({"fonctionnalite": "f99", "chemin": "a.md", "titre": "A"}, {"fonctionnalite": f, "titre": "A"},
                       {"fonctionnalite": f, "chemin": "/abs.md", "titre": "A"}):
            self.assertEqual(self.outil("document", entree=entree)[0], 1, entree)

    def test_documents_d_un_suivi_ancien(self):
        # Un suivi écrit avant les documents (sans la clé) : le relevé les retrouve dans la discussion, le cahier et
        # les captures des tâches.
        f = self.nouvelle()
        self.ok("fonctionnalite", entree={"id": f, "agent_cadrage": "metier-1"})
        self.ok("message", entree={"fonctionnalite": f, "auteur": "metier-1", "texte": "Voici", "images": ["pieces/a.png"]})
        self.ok("fonctionnalite", entree={"id": f, "cahier": {"maquette": ["pieces/m.png"], "etapes": ["x"]}})
        t = self.ok("tache", entree={"titre": "Dev", "fonctionnalite": f, "element": "e1", "agent": "dev-1",
                                     "colonne": "dev", "captures": ["captures/e1.png"]})
        chemin = self.dossier / "suivi.json"
        s = json.loads(chemin.read_text(encoding="utf-8"))
        for x in s["fonctionnalites"]:
            x.pop("documents", None)
        chemin.write_text(json.dumps(s), encoding="utf-8")
        docs = {d["chemin"]: d for d in self.releve()["fonctionnalites"][0]["documents"]}
        self.assertEqual(sorted(docs), ["captures/e1.png", "pieces/a.png", "pieces/m.png"])
        self.assertEqual(docs["pieces/a.png"]["etape"], "cadrage")
        # Un cahier validé « le jour même » (date sans heure) : un message de ce jour-là reste du cadrage.
        s = json.loads(chemin.read_text(encoding="utf-8"))
        jour = s["fonctionnalites"][0]["discussion"][-1]["t"][:10]
        s["fonctionnalites"][0]["cahier"]["valide_le"] = jour
        chemin.write_text(json.dumps(s), encoding="utf-8")
        docs = {d["chemin"]: d for d in self.releve()["fonctionnalites"][0]["documents"]}
        self.assertEqual(docs["pieces/a.png"]["etape"], "cadrage")
        self.assertEqual(docs["pieces/a.png"]["agent"], "metier-1")
        self.assertEqual(docs["pieces/m.png"]["etape"], "cahier")
        self.assertEqual((docs["captures/e1.png"]["tache"], docs["captures/e1.png"]["element"]), (t["id"], "e1"))

    def test_images_png_ou_jpeg_seulement(self):
        # Le bureau ne montre que le PNG et le JPEG : une maquette, une image de message ou une capture en SVG est
        # refusée tout de suite, avec la marche à suivre, au lieu d'apparaître cassée chez l'utilisateur.
        f = self.nouvelle()
        for commande, entree in (
                ("fonctionnalite", {"id": f, "cahier": {"maquette": ["pieces/m.svg"], "etapes": ["a"]}}),
                ("message", {"fonctionnalite": f, "auteur": "metier-1", "texte": "x", "images": ["pieces/m.svg"]}),
                ("tache", {"titre": "T", "captures": ["captures/c.webp"]})):
            code, sortie = self.outil(commande, entree=entree)
            self.assertEqual(code, 1, (commande, sortie))
            self.assertIn("PNG", sortie["erreur"])
        self.ok("fonctionnalite", entree={"id": f, "cahier": {"maquette": ["pieces/m.PNG", "pieces/n.jpeg"],
                                                               "etapes": ["a"]}})
        self.ok("message", entree={"fonctionnalite": f, "auteur": "metier-1", "texte": "x", "images": ["pieces/m.jpg"]})

    def test_verrou_en_cours_d_effacement(self):
        # Sous Windows, créer le verrou pendant qu'un autre processus l'efface lève PermissionError : c'est un
        # verrou occupé, on réessaie (et non une erreur).
        from unittest import mock
        s = suivi.Suivi(self.dossier / "suivi-verrou.json")
        vrai_open, essais = suivi.os.open, []

        def open_capricieux(*a, **k):
            if str(a[0]).endswith(".verrou"):
                essais.append(1)
            if len(essais) == 1 and str(a[0]).endswith(".verrou"):
                raise PermissionError(13, "Permission denied")
            return vrai_open(*a, **k)

        with mock.patch.object(suivi.os, "open", open_capricieux):
            with s.transaction() as d:
                d["reveil"] = "x"
        self.assertEqual(len(essais), 2)
        self.assertEqual(s.lire()["reveil"], "x")

    def test_vraie_tache_de_cadrage_remplace_la_synthetique(self):
        # L'orchestrateur crée une vraie tâche de cadrage (il en faut une pour `depart`) : le relevé ne la montre
        # qu'une fois, et `depart` l'accepte.
        f = self.nouvelle()
        self.ok("fonctionnalite", entree={"id": f, "agent_cadrage": "metier-1"})
        t = self.ok("tache", entree={"titre": "Cadrage : essai", "fonctionnalite": f, "colonne": "cadrage",
                                     "agent": "metier-1", "role": "cadrage", "active": True})
        r = self.releve()
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        cadrages = [x for x in r["taches"] if x["colonne"] == "cadrage" and x["titulaire"] == "metier-1"]
        self.assertEqual([x["id"] for x in cadrages], [t["id"]])
        self.assertIn("message", self.ok("depart", entree={"agent": "metier-1", "tache": t["id"]}))

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
                       {"titre": "B", "montee": {"de": "Opus", "a": "fable", "raison": "x"}},   # quelle que soit la casse
                       {"titre": "B", "modele_depart": "Fable"},
                       {"titre": "B", "montee": {"de": "Haiku", "a": "Opus", "raison": "x"}},   # un cran au plus
                       {"titre": "B", "montee": {"de": "Sonnet", "a": "Haiku", "raison": "x"}},  # une montée monte
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

    def test_file_prendre_un_element_precis(self):
        # Un « deplacer » du bureau sur un élément de la file (id « f1/e2 ») : l'orchestrateur prend cet élément-là.
        f = self.nouvelle()
        self.ok("file", entree={"fonctionnalite": f, "elements": [{"id": "e1", "nom": "Un"}, {"id": "e2", "nom": "Deux"}]})
        self.assertEqual(self.ok("file-prendre", entree={"fonctionnalite": f, "element": "e2"})["element"]["id"], "e2")
        self.assertEqual(self.outil("file-prendre", entree={"fonctionnalite": f, "element": "e2"})[0], 1)   # déjà pris
        self.assertEqual([q["titre"] for q in self.releve()["file"]["visibles"]], ["Un"])

    def test_deplacer_une_pseudo_tache_refuse(self):
        f = self.nouvelle()
        self.ok("fonctionnalite", entree={"id": f, "agent_cadrage": "metier-1"})
        for cible in ("orchestration", f"cadrage:{f}"):
            code, sortie = self.outil("actions", entree={"type": "deplacer", "tache": cible, "colonne": "dev"})
            self.assertEqual(code, 1, sortie)
        # Une vraie tâche ou un élément de la file se déplacent (l'orchestrateur s'en charge).
        self.assertEqual(self.outil("actions", entree={"type": "deplacer", "tache": f"{f}/e1", "colonne": "dev"})[0], 0)

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
