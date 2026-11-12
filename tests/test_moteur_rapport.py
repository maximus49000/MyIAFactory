"""Le rapport structuré des agents : lecture du bloc JSON, commandes à passer à `lancer`. Aucun appel réel."""
import json
import unittest

from moteur import rapport
from orchestrateur import depart
from tests.orch_aide import AvecProjet

FAIT = {"statut": "fait",
        "message": {"texte": "Voilà l'écran.", "images": ["pieces/f1/a.png"], "attend": False},
        "fichiers": [{"chemin": "pieces/f1/a.png", "titre": "Écran", "element": "e1", "livrable": True}],
        "lecons": [{"texte": "Nommer comme la maquette.", "roles": ["dev"], "etage_propose": "projet"}],
        "controles": [{"texte": "Le titre fait 24 px.", "origine": "relecture"}],
        "retours_factory": [], "verdicts": []}


def reponse(objet, avant="Fini.\n", apres=""):
    return f"{avant}```json\n{json.dumps(objet, ensure_ascii=False)}\n```\n{apres}"


class Lire(unittest.TestCase):
    def test_lit_le_dernier_bloc_json(self):
        premier = {"statut": "echec"}
        texte = reponse(premier) + "\nPuis ma vraie réponse :\n" + reponse(FAIT)
        r = rapport.lire(texte)
        self.assertEqual(r["statut"], "fait")
        self.assertEqual(r["fichiers"][0]["chemin"], "pieces/f1/a.png")

    def test_comptes_rendus_par_element_facultatifs(self):
        r = rapport.lire(reponse({**FAIT, "comptes_rendus": [{"element": "e1", "texte": "Vert."}, {"texte": "sans élément"},
                                                             "pas un objet", {"element": "e2", "texte": 3}]}))
        self.assertEqual(r["comptes_rendus"], [{"element": "e1", "texte": "Vert."}])   # le reste est écarté, sans refus
        self.assertEqual(rapport.lire(reponse({**FAIT, "comptes_rendus": "non"}))["comptes_rendus"], [])
        self.assertNotIn("comptes_rendus", rapport.lire(reponse(FAIT)))
        lot = depart.COMPTE_RENDU_MOTEUR
        self.assertIn("comptes_rendus", lot)

    def test_ce_que_dit_la_validation(self):
        r = rapport.lire(reponse({**FAIT, "doit_marcher": "  L'apk\ns'ouvre. ", "pas_encore": "", "conclusion": "x" * 201,
                                  "comptes_rendus": [{"element": "e1", "texte": "v", "doit_marcher": 3,
                                                      "pas_encore": "Rien ne répond.", "conclusion": "Validez."}]}))
        self.assertEqual((r["doit_marcher"], r["pas_encore"]), ("L'apk s'ouvre.", ""))
        self.assertNotIn("conclusion", r)                       # trop long : écarté, sans refuser le rapport
        (c,) = r["comptes_rendus"]
        self.assertNotIn("doit_marcher", c)
        self.assertEqual((c["pas_encore"], c["conclusion"]), ("Rien ne répond.", "Validez."))
        self.assertNotIn("doit_marcher", rapport.lire(reponse({**FAIT, "doit_marcher": "  "})))

    def test_nature_et_mode_operatoire(self):
        mode = ["  Installez\nl'apk. ", "Lancez le jeu."]
        r = rapport.lire(reponse({**FAIT, "nature": "en_jeu", "mode_operatoire": mode,
                                  "comptes_rendus": [{"element": "e1", "texte": "v", "nature": "sprites",
                                                      "mode_operatoire": ["une seule étape"]},
                                                     {"element": "e2", "texte": "v", "nature": "visuel"}]}))
        self.assertEqual((r["nature"], r["mode_operatoire"]), ("en_jeu", ["Installez l'apk.", "Lancez le jeu."]))
        c1, c2 = r["comptes_rendus"]
        self.assertNotIn("nature", c1)                          # forme fautive : écartée, sans refuser le rapport
        self.assertNotIn("mode_operatoire", c1)
        self.assertEqual(c2["nature"], "visuel")
        for mauvais in (["a"], ["a"] * 11, ["a", ""], ["a", "x" * 201], "non", [1, 2]):
            self.assertNotIn("mode_operatoire", rapport.lire(reponse({**FAIT, "mode_operatoire": mauvais})))
        self.assertEqual(len(rapport.lire(reponse({**FAIT, "mode_operatoire": ["a"] * 10}))["mode_operatoire"]), 10)

    def test_points_a_verifier_et_acces_facultatifs(self):
        """La fenêtre de validation : une forme fautive est écartée, jamais une raison de refuser le rapport."""
        points = ["Le menu s'ouvre", "  Le son\nse coupe ", "x" * 161, 3, "Le menu s'ouvre"] + [f"p{i}" for i in range(9)]
        r = rapport.lire(reponse({**FAIT, "points_a_verifier": points,
                                  "acces": {"url": "http://127.0.0.1:5173/", "description": "Le site"},
                                  "comptes_rendus": [{"element": "e1", "texte": "Vert.", "points_a_verifier": "non",
                                                      "acces": {"url": "javascript:x"}}]}))
        self.assertEqual(r["points_a_verifier"], ["Le menu s'ouvre", "Le son se coupe"] + [f"p{i}" for i in range(6)])
        self.assertEqual(r["acces"], {"url": "http://127.0.0.1:5173/", "description": "Le site"})
        self.assertEqual(r["comptes_rendus"], [{"element": "e1", "texte": "Vert.", "points_a_verifier": []}])
        self.assertNotIn("acces", rapport.lire(reponse({**FAIT, "acces": "http://127.0.0.1"})))
        self.assertNotIn("points_a_verifier", rapport.lire(reponse(FAIT)))

    def test_rapport_sans_bloc_illisible(self):
        for texte in ("Tout est fait.", "```json\n{pas du json\n```", reponse({"statut": "autre"}), ""):
            with self.subTest(texte=texte), self.assertRaises(rapport.RapportIllisible):
                rapport.lire(texte)

    def test_maquette_legendee_ou_non(self):
        cahier = {"maquette": ["pieces/f1/a.png", {"chemin": "pieces/f1/b.png", "legende": "Le combat"}],
                  "etapes": ["Faire"]}
        r = rapport.lire(reponse(dict(FAIT, cahier=cahier)))
        self.assertEqual(r["cahier"]["maquette"][1], {"chemin": "pieces/f1/b.png", "legende": "Le combat"})
        for mauvaise in ({"legende": "x"}, {"chemin": "", "legende": "x"}, {"chemin": "a.png", "legende": 3}, 3):
            with self.subTest(mauvaise=mauvaise), self.assertRaises(rapport.RapportIllisible):
                rapport.lire(reponse(dict(FAIT, cahier={"maquette": [mauvaise], "etapes": ["Faire"]})))

    def test_message_a_images_legendees_passe_tel_quel(self):
        images = [{"chemin": "pieces/f1/a.png", "legende": "L'écran d'accueil"}, "pieces/f1/b.png"]
        cmds = rapport.commandes(rapport.lire(reponse({"statut": "fait", "message": {"texte": "Voici", "images": images}})),
                                 fonctionnalite="f1", tache="t3", agent="dev-1", etape="dev")
        self.assertEqual(cmds[0][1]["images"], images)

    def test_valeurs_vides_completees(self):
        r = rapport.lire(reponse({"statut": "fait"}))
        self.assertEqual((r["fichiers"], r["lecons"], r["controles"], r["verdicts"], r["retours_factory"]),
                         ([], [], [], [], []))

    def test_lecon_de_genre_demande_le_texte_general(self):
        mauvais = dict(FAIT, lecons=[{"texte": "Un conseil.", "etage_propose": "genre"}])
        with self.assertRaises(rapport.RapportIllisible):
            rapport.lire(reponse(mauvais))

    def test_accord_requis_demande_son_accord(self):
        with self.assertRaises(rapport.RapportIllisible):
            rapport.lire(reponse({"statut": "accord_requis"}))


class Commandes(unittest.TestCase):
    def appel(self, r):
        return rapport.commandes(rapport.lire(reponse(r)), fonctionnalite="f1", tache="t3", agent="dev-1",
                                 etape="dev")

    def test_commandes_dans_l_ordre(self):
        cmds = self.appel(FAIT)
        self.assertEqual([c for c, _ in cmds], ["message", "document", "controle", "lecon"])
        message, document, controle, lecon = (e for _, e in cmds)
        self.assertEqual(message["auteur"], "dev-1")
        self.assertEqual(message["fonctionnalite"], "f1")
        self.assertEqual(message["images"], ["pieces/f1/a.png"])
        self.assertIs(message["attend"], False)
        self.assertEqual((document["agent"], document["tache"], document["etape"], document["element"],
                          document["livrable"]), ("dev-1", "t3", "dev", "e1", True))
        self.assertEqual(controle, {"texte": "Le titre fait 24 px.", "origine": "relecture"})
        self.assertEqual((lecon["action"], lecon["agent"], lecon["tache"], lecon["roles"]),
                         ("noter", "dev-1", "t3", ["dev"]))

    def test_accord_requis_ne_rend_aucune_commande_de_production(self):
        r = dict(FAIT, statut="accord_requis", accord={"quoi": "Générer 5 images", "partenaire": "x", "cout": "2 $"})
        cmds = self.appel(r)
        self.assertEqual([c for c, _ in cmds], ["message"])

    def questions(self, questions):
        cmds = self.appel({"statut": "fait", "message": {"texte": "Alors ?", "attend": True, "questions": questions}})
        return cmds[0][1]["questions"]

    def test_une_question_au_mauvais_nom_est_normalisee(self):
        """Le cas réel : `{"question": ..., "choix": [...]}` au lieu de `texte`."""
        for alias in ("question", "intitule", "libelle"):
            q = self.questions([{alias: "Quel style ?", "choix": ["Pixel", "Vectoriel"], "multiple": False}])
            self.assertEqual(q, [{"texte": "Quel style ?", "choix": ["Pixel", "Vectoriel"], "multiple": False}])

    def test_des_choix_donnes_comme_options_ou_reponses_sont_normalises(self):
        for alias in ("options", "reponses"):
            q = self.questions([{"texte": "Style ?", alias: ["Pixel", "Vectoriel"]}])
            self.assertEqual(q, [{"texte": "Style ?", "choix": ["Pixel", "Vectoriel"]}])

    def test_la_normalisation_n_invente_rien(self):
        bonne = {"texte": "Style ?", "choix": ["a", "b"], "multiple": True}
        self.assertEqual(self.questions([bonne, {"question": "Sans choix"}]),
                         [bonne, {"texte": "Sans choix"}])       # pas de choix inventés : l'outil refusera
        self.assertEqual(self.questions([{"texte": "T", "question": "Autre", "choix": ["a", "b"]}])[0]["texte"], "T")
        self.assertEqual(self.questions(["pas une question", {"question": 3}]), ["pas une question", {"question": 3}])

    def test_sans_fonctionnalite_ni_message_ni_document(self):
        cmds = rapport.commandes(rapport.lire(reponse(FAIT)), fonctionnalite=None, tache="t3", agent="dev-1",
                                 etape="dev")
        self.assertEqual([c for c, _ in cmds], ["controle", "lecon"])


class Consigne(AvecProjet):
    def test_depart_demande_le_bloc_json(self):
        t = self.ok("tache", entree={"titre": "Écran", "role": "dev", "colonne": "dev"})["id"]
        m = self.ok("lancer", "depart", entree={"agent": "dev-1", "tache": t})["message"]
        self.assertIn("bloc ```json", m)
        self.assertIn("accord_requis", m)
        self.assertIn("```json", depart.FIN_D_ETAPE)

    def test_les_consignes_demandent_une_legende_par_image(self):
        from moteur import agents
        self.assertIn('"legende"', depart.FIN_D_ETAPE)
        self.assertIn("légende", depart.FIN_D_ETAPE)
        self.assertIn("légende", agents.CONSIGNE_AGENT)

    def test_les_consignes_demandent_des_questions_a_choix_pour_un_avis(self):
        from moteur import agents, regles
        for texte in (depart.FIN_D_ETAPE, agents.CONSIGNE_AGENT):
            self.assertIn("questions", texte)
            self.assertIn("avis", texte)
        self.assertLess(len(depart.FIN_D_ETAPE), 4200)
        self.assertLess(len(agents.CONSIGNE_AGENT), 1500)
        import inspect
        source = inspect.getsource(regles._matiere)
        self.assertIn("à choix", source.split('elif etape == "prototype"')[1].split("elif etape.startswith")[0])

    def test_les_consignes_font_prevenir_avant_une_fenetre_windows(self):
        """L'utilisateur est prévenu avant qu'une fenêtre (pare-feu, UAC, pilote, débogage USB) s'ouvre sur son poste."""
        from moteur import agents, environnement
        brief = environnement.agent_d_installation([], [], [{"id": "d", "nom": "D", "role": "dev", "service": "d"}],
                                                   [{"id": "d", "nom": "D"}])[1]
        for texte in (depart.FIN_D_ETAPE, agents.CONSIGNE_AGENT, brief):
            self.assertIn("pare-feu", texte)
            self.assertIn("fenêtre", texte)
            self.assertIn("jamais", texte)
        self.assertIn("pare-feu Windows pour adb.exe", depart.FIN_D_ETAPE)
        self.assertIn("attend", depart.FIN_D_ETAPE)
        self.assertIn("bloquée", depart.FIN_D_ETAPE)
        self.assertLess(len(depart.FIN_D_ETAPE), 4200)
        self.assertLess(len(agents.CONSIGNE_AGENT), 1500)

    def test_usage_accepte_orchestrateur(self):
        code, _ = self.outil("usage", entree={"modele": "claude-haiku-5-5", "agent": "orchestrateur",
                                              "etape": "orchestration", "entree": 10, "sortie": 5})
        self.assertEqual(code, 0)
        code, _ = self.outil("usage", entree={"modele": "x", "agent": "inconnu", "entree": 1, "sortie": 1})
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
