"""Les outils du banc : construire, référence, agent seul, rapport. Transcriptions et suivi fabriqués dans un dossier
temporaire, aucun appel réel."""
import json
import tempfile
import unittest
from pathlib import Path

from banc import __main__ as banc_main
from banc import agent_seul, construire, mesures, rapport, reference, scenario
from moteur import appel
from tests.orch_aide import AvecProjet

SYNTHETIQUE = Path(__file__).resolve().parent.parent / "banc" / "exemples" / "synthetique.json"
PRIX = {"claude-sonnet-5-5": {"entree": 3.0, "sortie": 15.0, "cache_lecture": 0.3, "cache_ecriture": 3.75},
        "claude-haiku-5-5": {"entree": 1.0, "sortie": 5.0, "cache_lecture": 0.1, "cache_ecriture": 1.25}}


def prix_de(modele, date_iso):
    p = PRIX.get(modele)
    return (dict(p) if p else None), "2026-11-01", False


def message(i, model, entree, sortie, lecture=0, ecriture=0, texte="Réponse.", cote=False):
    d = {"type": "assistant", "message": {"id": i, "model": model, "content": [{"type": "text", "text": texte}],
                                          "usage": {"input_tokens": entree, "output_tokens": sortie,
                                                    "cache_read_input_tokens": lecture,
                                                    "cache_creation_input_tokens": ecriture}}}
    if cote:
        d["isSidechain"] = True
    return d


def ecrire_jsonl(chemin, lignes):
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lignes) + "\n", encoding="utf-8")


class Reference(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dossier = Path(self._t.name)

    def test_reference_compte_un_appel_par_message(self):
        # un message répété (même identifiant) ne compte qu'une fois ; une ligne sans usage n'est pas un appel
        ecrire_jsonl(self.dossier / "orch.jsonl", [
            {"type": "user", "message": {"role": "user", "content": "Bonjour"}},
            message("m1", "claude-sonnet-5-5", 10, 5, 1000, 100), message("m1", "claude-sonnet-5-5", 10, 5, 1000, 100),
            message("m2", "claude-sonnet-5-5", 20, 8, 2000, 0), message("m3", "claude-haiku-5-5", 4, 2, 0, 0),
            {"type": "assistant", "message": {"id": "m4", "model": "x", "content": []}}])
        r = reference.reference(self.dossier / "orch.jsonl")
        self.assertEqual(r["appels"], 3)
        self.assertEqual(r["par_modele"]["claude-sonnet-5-5"],
                         {"modele": "claude-sonnet-5-5", "entree": 30, "sortie": 13, "cache_lecture": 3000, "cache_ecriture": 100})
        self.assertEqual(r["tokens"], 30 + 13 + 3000 + 100 + 6)
        self.assertIsNone(r["euros"])

    def test_reference_exclut_les_sous_agents(self):
        ecrire_jsonl(self.dossier / "orch.jsonl", [
            message("m1", "claude-sonnet-5-5", 10, 5), message("s1", "claude-sonnet-5-5", 99999, 99999, cote=True)])
        ecrire_jsonl(self.dossier / "orch" / "subagents" / "agent-a1.jsonl", [message("s2", "claude-sonnet-5-5", 77777, 1)])
        r = reference.reference(self.dossier / "orch.jsonl")
        self.assertEqual((r["appels"], r["tokens"]), (1, 15))

    def test_reference_coute_en_euros(self):
        ecrire_jsonl(self.dossier / "orch.jsonl", [message("m1", "claude-sonnet-5-5", 1_000_000, 0),
                                                   message("m2", "inconnu", 5, 5)])
        r = reference.reference(self.dossier / "orch.jsonl", prix_de, "2026-11-10")
        self.assertAlmostEqual(r["euros"], 3.0)
        self.assertEqual(r["sans_prix"], ["inconnu"])      # un coût incomplet le dit


class Construire(AvecProjet):
    def setUp(self):
        super().setUp()
        self.transcriptions = self.dossier / "transcriptions"
        self.bancs = self.dossier / "bancs"

    def essai(self):
        """Un petit essai fabriqué : une fonctionnalité, quatre tâches, trois sous-agents."""
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Des écrans"})
        self.ok("actions", entree={"type": "message", "fonctionnalite": "f1", "texte": "Deux écrans"})
        self.ok("actions", entree={"type": "cahier", "fonctionnalite": "f1", "verdict": "valider"})
        self.ok("actions", entree={"type": "bouton", "id": "pause"})            # pas rejouable
        self.ok("message", entree={"fonctionnalite": "f1", "auteur": "metier-1", "texte": "Quel genre ?", "attend": True})
        taches = {}
        for cle, titre, role, colonne, element in (
                ("cad", "Cadrage : Des écrans", "cadrage", "cadrage", None),
                ("proto", "Développement : Accueil", "dev", "dev", "e1"),
                ("dev", "Développement : Profil", "dev", "dev", "e2"),
                ("rel", "Relecture : Profil", "relecteur", "relecture", "e2")):
            e = {"titre": titre, "fonctionnalite": "f1", "role": role, "colonne": colonne, "active": False}
            if element:
                e["element"] = element
            taches[cle] = self.ok("tache", entree=e)["id"]
            self.ok("tache", entree={"id": taches[cle], "colonne": "fait"})
        corps = "# Projet : Essai\n\n## Ta tâche\n- Tâche : {titre} ({id})\n"
        for cle, final, m in (("cad", "Voici ma question.", "m10"), ("dev", "Écran fait.", "m11"),
                              ("rel", "J'ai trouvé un défaut :\n- Le titre est trop petit\n- Le bouton est cassé", "m12")):
            t = self.ok("detail", entree={"tache": taches[cle]})
            ecrire_jsonl(self.transcriptions / "session" / "subagents" / f"agent-{cle}.jsonl", [
                {"type": "user", "message": {"role": "user", "content": corps.format(titre=t["titre"], id=t["id"])}},
                message(m, "claude-sonnet-5-5", 100, 50, 1000, 10, texte=final)])
        return taches

    def test_construire_ecrit_un_scenario_valide_hors_du_depot(self):
        self.essai()
        chemin = construire.construire(self.dossier, self.transcriptions, self.bancs / "essai" / "scenario.json")
        s = scenario.charger(chemin)
        self.assertEqual([g["demande"]["type"] for g in s.gestes], ["fonctionnalite", "message", "cahier"])
        self.assertEqual([g["apres"] for g in s.gestes], ["immediat", "attente_utilisateur", "attente_utilisateur"])
        self.assertEqual(s.gestes[1]["demande"]["fonctionnalite"], "f1")
        self.assertNotIn("id", s.gestes[0]["demande"])
        cles = [(r["etape"], r["role"], r["rang"]) for r in s.rapports]
        self.assertEqual(cles, [("cadrage", "cadrage", 0), ("flux:dev", "dev", 1), ("relecture", "relecteur", 1)])
        self.assertEqual(s.rapports[0]["usage"]["entree"], 100)
        self.assertEqual(s.rapports[0]["usage"]["cache_lecture"], 1000)
        verdict = s.rapports[2]["rapport"]["verdicts"][0]
        self.assertEqual((verdict["element"], verdict["conforme"]), ("e2", False))
        self.assertEqual(verdict["points"], ["Le titre est trop petit", "Le bouton est cassé"])
        self.assertTrue(s.rapports[0]["rapport"]["message"]["attend"])
        self.assertEqual(s.donnees["essai"]["questions"], 1)
        self.assertEqual(s.projet["factory"]["flux"][0]["id"], "dev")
        self.assertIn("lea.md", s.projet["fiches"])

    def essai_reel(self):
        """Les formes de l'orchestrateur actuel : réponse finale rendue par `SubagentHandback`, tâche nommée
        « tâche t2 », départ d'un lot dans un fichier `depart_*.md`, cadrage sans identifiant de tâche."""
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Des badges"})
        self.ok("actions", entree={"type": "cahier", "fonctionnalite": "f1", "verdict": "valider"})
        self.ok("actions", entree={"type": "message", "fonctionnalite": "f1",
                                   "texte": "Que fait-on de la méthode ? → Valider la méthode et lancer la série"})
        flux = [{"id": "creation", "nom": "Création", "role": "graphiste", "service": "dev"},
                {"id": "controle", "nom": "Contrôle", "role": "controleur", "service": "dev"}]
        f = json.loads((self.dossier / "factory.json").read_text(encoding="utf-8"))
        f["flux"] = flux
        (self.dossier / "factory.json").write_text(json.dumps(f, ensure_ascii=False), encoding="utf-8")
        ids = {}
        for cle, titre, role, element in (("cad", "Cadrage : Des badges", "graphiste", None),
                                          ("proto", "Prototype : Abo 1", "graphiste", "a1"),
                                          ("c1", "Contrôle : Abo 1", "controleur", "a1"),
                                          ("b3", "Création : Abo 3", "controleur", "a3"),
                                          ("b6", "Création : Abo 6", "controleur", "a6"),
                                          ("cor", "Correction : Abo 6", "graphiste", "a6")):
            e = {"titre": titre, "fonctionnalite": "f1", "role": role, "colonne": "creation", "active": False}
            if element:
                e["element"] = element
            ids[cle] = self.ok("tache", entree=e)["id"]
            self.ok("tache", entree={"id": ids[cle], "colonne": "fait"})
        pieces = self.dossier / "pieces"
        pieces.mkdir(exist_ok=True)
        (pieces / "depart_lot1.md").write_text(
            f"# Projet\n\n## Ta fiche\nClé : graphiste\nRôle : graphiste\n\n## Tes 2 tâches\n- {ids['b3']}\n- {ids['b6']}\n",
            encoding="utf-8")
        (pieces / "depart_lot2.md").write_text(
            f"# Projet\n\n## Ta fiche\nClé : ctrl\nRôle : controleur\n\n## Tes 2 tâches\n- {ids['b3']}\n- {ids['b6']}\n",
            encoding="utf-8")

        def rendu(texte):
            return {"type": "assistant", "message": {"id": "h", "model": "claude-sonnet-5-5", "content": [
                {"type": "tool_use", "id": "x", "name": "SubagentHandback", "input": {"message": texte}}],
                "usage": {"input_tokens": 1, "output_tokens": 1}}}

        cahier = json.dumps({"texte": "Voici la maquette.", "etapes": ["Abo 1", "Abo 3"],
                             "maquette": ["pieces/f1/maquette.png"], "lecons": []}, ensure_ascii=False)
        questions = json.dumps({"texte": "Quelques questions.", "questions": [{"texte": "Combien ?",
                                                                               "choix": ["3", "5"]}]})
        departs = (
            ("1", "Tu es l'agent de CADRAGE pour cette fonctionnalité.", questions),
            ("2", "Tu es l'agent de cadrage (graphiste) du projet. Écris le cahier.", cahier),
            ("3", f"Tu es le graphiste du projet (tâche {ids['proto']}, élément a1). C'est le PROTOTYPE.", "Fait."),
            ("4", f"Tu es le contrôleur du projet (tâche {ids['c1']}, élément a1).", "Tout passe."),
            ("5", f"Tu repars de zéro. Lis {pieces / 'depart_lot1.md'} et suis-le.", "Lot fait."),
            ("6", f"Tu repars de zéro. Lis {pieces / 'depart_lot2.md'} et suis-le.",
             "Badge | C1 | Global\na3 ({b3}) | PASS | PASS\na6 ({b6}) | PASS | FAIL (boîte décalée)\nLot contrôlé.".format(
                 **ids)),
            ("7", f"Lis {pieces / 'depart_t9.md'} (tâche {ids['cor']}, élément a6, correction).", "Corrigé."))
        for n, depart, final in departs:
            # noms dans le désordre : l'ordre est celui de l'heure du départ
            ecrire_jsonl(self.transcriptions / "session" / "subagents" / f"agent-{8 - int(n)}.jsonl", [
                {"type": "user", "timestamp": f"2026-11-11T10:0{n}:00Z", "message": {"role": "user", "content": depart}},
                message("m" + n, "claude-sonnet-5-5", 100, 50, texte="Je rends compte."), rendu(final)])
        self.ok("actions", entree={"type": "retour", "tache": ids["proto"], "texte": "La limite est levée"})
        return ids

    def test_construire_lit_les_formes_de_l_orchestrateur_actuel(self):
        ids = self.essai_reel()
        s = scenario.charger(construire.construire(self.dossier, self.transcriptions, self.bancs / "reel.json"))
        # la réponse à une question sur la méthode devient le geste du bureau ; un retour sur une tâche de l'essai
        # (son identifiant ne désigne rien dans le moteur) est écarté
        self.assertEqual([g["demande"] for g in s.gestes[1:]], [
            {"type": "cahier", "fonctionnalite": "f1", "verdict": "valider"},
            {"type": "methode", "fonctionnalite": "f1", "verdict": "valider"}])
        cles = [(r["etape"], r["role"], r["rang"]) for r in s.rapports]
        self.assertEqual(cles, [("cadrage", "cadrage", 0), ("cadrage", "cadrage", 0), ("prototype", "graphiste", 0),
                                ("flux:controle", "controleur", 0), ("flux:creation", "graphiste", 1),
                                ("flux:controle", "controleur", 1), ("correction", "graphiste", 2)])
        premier = s.rapports[0]["rapport"]["message"]
        self.assertEqual(premier["texte"], "Quelques questions.")
        self.assertEqual(premier["questions"][0]["choix"], ["3", "5"])
        self.assertEqual(s.rapports[1]["rapport"]["cahier"], {"maquette": ["pieces/f1/maquette.png"],
                                                              "etapes": ["Abo 1", "Abo 3"]})
        self.assertEqual(s.rapports[2]["texte"], "Fait.")
        # la dernière étape du flux, sans relecteur dans l'essai, rend des verdicts par élément du lot
        self.assertEqual(s.rapports[5]["rapport"]["verdicts"], [
            {"element": "a3", "conforme": True, "points": [], "rang": 1},
            {"element": "a6", "conforme": False, "points": ["a6 ({b6}) | PASS | FAIL (boîte décalée)".format(**ids)],
             "rang": 2}])
        self.assertNotIn("verdicts", s.rapports[4]["rapport"])
        self.assertEqual(s.rapports[0]["usage"]["entree"], 101)

    def test_construire_refuse_une_sortie_dans_le_depot(self):
        self.essai()
        dedans = Path(construire.RACINE) / "banc" / "essai-prive" / "scenario.json"
        with self.assertRaises(construire.ErreurBanc):
            construire.construire(self.dossier, self.transcriptions, dedans)
        with self.assertRaises(construire.ErreurBanc):
            construire.construire(self.dossier, self.transcriptions, construire.RACINE)
        self.assertFalse(dedans.parent.exists())
        with self.assertRaises(construire.ErreurBanc):
            banc_main.dossier_du_banc("essai", racine=construire.RACINE / "bancs")

    def test_commandes_du_banc(self):
        import contextlib
        import io
        self.essai()
        ecrire_jsonl(self.dossier / "orch.jsonl", [message("m1", "claude-sonnet-5-5", 10, 5)])
        vide = self.dossier / "vide-prix.jsonl"     # pas de table de prix : les euros sont « non mesurés »
        base = ["--nom", "essai", "--bancs", str(self.bancs), "--prix", str(vide)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(banc_main.main(["construire", "--factory", str(self.dossier), "--transcriptions",
                                             str(self.transcriptions), *base]), 0)
            self.assertEqual(banc_main.main(["reference", "--transcription", str(self.dossier / "orch.jsonl"), *base]), 0)
            self.assertEqual(banc_main.main(["rapport", *base]), 0)
        texte = (self.bancs / "essai" / "rapport.md").read_text(encoding="utf-8")
        self.assertIn("## L'orchestrateur actuel", texte)
        self.assertIn("Non joué.", texte)             # le moteur et l'agent seul ne sont pas joués par cette commande
        self.assertEqual(json.loads((self.bancs / "essai" / "reference.json").read_text(encoding="utf-8"))["appels"], 1)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(banc_main.main(["construire", "--factory", str(self.dossier), "--transcriptions",
                                             str(self.transcriptions), "--nom", "x", "--bancs",
                                             str(construire.RACINE / "bancs")]), 1)

    def test_construire_refuse_un_essai_sans_demandes(self):
        with self.assertRaises(construire.ErreurBanc):
            construire.construire(self.dossier, self.transcriptions, self.bancs / "x.json")

    def test_nom_de_banc(self):
        for mauvais in ("", "a/b", "..", "a b"):
            with self.assertRaises(construire.ErreurBanc, msg=mauvais):
                banc_main.dossier_du_banc(mauvais, racine=self.bancs)
        self.assertTrue(banc_main.dossier_du_banc("essai-1", racine=self.bancs).is_dir())


class FauxAppel:
    def __init__(self, *reponses, texte_par_defaut="Fait."):
        self.reponses, self.recus = list(reponses), []

    def __call__(self, consigne, dossier, modele, **options):
        self.recus.append({"consigne": consigne, "dossier": dossier, "modele": modele, **options})
        t = self.reponses.pop(0) if self.reponses else "Fait."
        if isinstance(t, Exception):
            raise t
        return appel.Reponse(t, [{"modele": "claude-sonnet-5-5", "entree": 100, "sortie": 50, "cache_lecture": 10,
                                  "cache_ecriture": 5}], session="s-seul")


class AgentSeul(unittest.TestCase):
    def test_agent_seul_compte_les_questions(self):
        s = scenario.charger(SYNTHETIQUE)
        faux = FauxAppel("Combien d'écrans voulez-vous ?", "Voici un cahier.\nQue pensez-vous du titre ?",
                         "C'est corrigé.", "Le cahier est validé.", "Fait, tout est livré.")
        with tempfile.TemporaryDirectory() as d:
            r = agent_seul.agent_seul(s, d, appeler=faux)
        self.assertEqual(r["appels"], 5)                 # un appel par geste de l'essai, tous ont un sens pour lui
        self.assertEqual(r["questions"], 2)
        self.assertEqual(r["usages"][0]["entree"], 500)
        self.assertEqual(len(r["reponses"]), 5)
        self.assertIsNone(r["erreur"])
        premier, second = faux.recus[0], faux.recus[1]
        self.assertEqual(premier["modele"], "sonnet")
        self.assertIsNone(premier["reprendre"])
        self.assertEqual(second["reprendre"], "s-seul")        # la même conversation, reprise
        self.assertEqual(premier["dossier_travail"], d)
        self.assertIn("Read", premier["outils"])                # les outils par défaut de Claude Code
        self.assertNotIn("dangerously", json.dumps({k: str(v) for k, v in premier.items()}).lower())

    def test_texte_du_geste(self):
        self.assertEqual(agent_seul.texte_du_geste({"type": "message", "texte": "Bonjour"}), "Bonjour")
        self.assertEqual(agent_seul.texte_du_geste({"type": "cahier", "verdict": "corriger", "texte": "Plus court"}),
                         "Plus court")
        self.assertEqual(agent_seul.texte_du_geste({"type": "cahier", "verdict": "valider"}),
                         agent_seul.VALIDER_LE_CAHIER)
        self.assertIsNone(agent_seul.texte_du_geste({"type": "bouton", "id": "pause"}))

    def test_pose_une_question(self):
        self.assertTrue(agent_seul.pose_une_question("Voici.\nUn titre bleu ?"))
        self.assertTrue(agent_seul.pose_une_question("Voici.\n**Un titre bleu ?**\n"))
        self.assertFalse(agent_seul.pose_une_question("Un titre bleu ? Oui, c'est fait."))
        self.assertFalse(agent_seul.pose_une_question(""))

    def test_un_appel_rate_arrete_le_passage_et_garde_ce_qu_il_a_coute(self):
        s = scenario.charger(SYNTHETIQUE)
        usage = {"modele": "claude-sonnet-5-5", "entree": 7, "sortie": 1, "cache_lecture": 0, "cache_ecriture": 0}
        faux = FauxAppel("Bonjour.", appel.ErreurAppel("délai dépassé", [usage]))
        with tempfile.TemporaryDirectory() as d:
            r = agent_seul.agent_seul(s, d, appeler=faux)
        self.assertEqual((r["appels"], r["erreur"]), (1, "délai dépassé"))
        self.assertEqual(r["usages"][0]["entree"], 107)


class Rapport(unittest.TestCase):
    ATTENDU = ["Le cahier est validé", "La méthode est écrite", "Les éléments sont faits"]

    def resultats(self, **moteur):
        m = {"appels": 6, "tokens": 40000, "euros_orchestration": 0.06, "euros_production": 1.4, "euros_total": 1.46,
             "questions": 4, "attendu": [True, True, True], "ecarts": []}
        m.update(moteur)
        return {"moteur": m,
                "orchestrateur_actuel": {"appels": 97, "tokens": 13_500_000, "euros_orchestration": 1.76,
                                         "euros_production": 1.56, "euros_total": 3.32, "questions": 5,
                                         "attendu": [True, True, True], "ecarts": []},
                "agent_seul": {"appels": 20, "tokens": 900_000, "euros_orchestration": 0.0, "euros_production": 2.9,
                               "euros_total": 2.9, "questions": 9, "attendu": None, "ecarts": []}}

    def etats(self, **moteur):
        return {texte.split(" ")[0] + texte.split(" ")[1]: etat for texte, etat, _ in
                rapport.objectifs(self.resultats(**moteur), self.ATTENDU)}

    def test_rapport_marque_les_objectifs(self):
        r = rapport.rapport(self.resultats(), self.ATTENDU)
        self.assertIn("# Rapport du banc d'essai", r)
        for nom in ("Le moteur", "L'orchestrateur actuel", "Un agent seul"):
            self.assertIn(f"## {nom}", r)
        self.assertIn("97", r)
        self.assertIn("13 500 000", r)
        self.assertIn("4 % orchestration / 96 % production", r)
        self.assertIn("- [x] Le cahier est validé", r)
        etats = [etat for _, etat, _ in rapport.objectifs(self.resultats(), self.ATTENDU)]
        self.assertEqual(etats, ["tenu", "tenu", "tenu"])
        self.assertEqual(r.count("**Tenu**"), 3)

    def test_objectifs_non_tenus(self):
        etats = lambda **m: [e for _, e, _ in rapport.objectifs(self.resultats(**m), self.ATTENDU)]   # noqa: E731
        self.assertEqual(etats(euros_orchestration=0.25)[0], "non tenu")
        self.assertEqual(etats(euros_total=3.5)[1], "non tenu")
        self.assertEqual(etats(attendu=[True, False, True])[2], "non tenu")
        self.assertEqual(etats(questions=6)[2], "non tenu")                  # plus de questions que dans l'essai (5)
        self.assertEqual(etats(euros_orchestration=0.10)[0], "tenu")         # ≤ 0,10 €

    def test_chiffres_absents_ne_passent_pas_pour_zero(self):
        res = self.resultats(euros_orchestration=None, euros_total=None, attendu=None)
        r = rapport.rapport(res, self.ATTENDU)
        self.assertIn("non mesuré", r)
        self.assertEqual([e for _, e, _ in rapport.objectifs(res, self.ATTENDU)], ["non mesuré"] * 3)
        self.assertIn("Non joué.", rapport.rapport({}, self.ATTENDU))

    def test_ecarts_listes(self):
        r = rapport.rapport(self.resultats(ecarts=["Aucun rapport à rejouer pour relecture / relecteur / rang 3"]),
                            self.ATTENDU)
        self.assertIn("Écarts avec l'essai (1)", r)
        self.assertIn("rang 3", r)


class Mesures(unittest.TestCase):
    def test_mesure_du_moteur_joue(self):
        from banc import jouer
        from tests.test_banc_scenario import Jugements
        s = scenario.charger(SYNTHETIQUE)
        with tempfile.TemporaryDirectory() as d:
            r = jouer.jouer_moteur(s, d, Jugements())
        m = mesures.mesure_moteur(r, s, prix_de, "2026-11-10")
        self.assertEqual(m["appels"], 3)
        self.assertGreater(m["euros_production"], m["euros_orchestration"])
        self.assertAlmostEqual(m["euros_total"], m["euros_orchestration"] + m["euros_production"], places=6)
        self.assertEqual(m["questions"], 4)       # quatre messages d'agents attendent l'utilisateur
        self.assertEqual(m["ecarts"], [])
        sans_prix = mesures.mesure_moteur(r, s)
        self.assertIsNone(sans_prix["euros_total"])
        ref = {"appels": 97, "tokens": 1000, "euros": 1.76}
        o = mesures.mesure_orchestrateur_actuel(ref, s, prix_de, "2026-11-10")
        self.assertEqual((o["appels"], o["euros_orchestration"]), (97, 1.76))
        self.assertGreater(o["euros_production"], 0)


if __name__ == "__main__":
    unittest.main()
