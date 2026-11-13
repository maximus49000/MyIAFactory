"""Le départ d'un agent polyvalent porte le métier de la tâche : brief, spécialité, outils et leçons ; un lot porte un brief
par métier ; un agent cloud garde une seule session pour tous les métiers (conception
2026-11-13-agents-polyvalents-design.md). Ni git, ni `claude`, ni réseau réels."""
import json

from moteur import boucle, cloud, regles
from tests.orch_aide import AvecProjet
from tests.test_moteur_boucle import Agents
from tests.test_moteur_cloud import RAPPORT_FAIT, FauxCloud

BRIEF_DEV = ("Service : dev\nSpécialité : écrans du jeu\nOutils : Read, Write, Edit, Bash(gradle:*)\n\n"
             "Brief des développeurs.\n\n## Leçons\n- [validée] dev:L1 : Toujours tester.\n"
             "- [à valider] dev:L2 : Pas encore la règle.\n")
BRIEF_QA = "Service : qualite\nSpécialité : recette sur émulateur\n\nBrief des testeurs.\n\n## Leçons\n" \
           "- [validée] qa:L1 : Vérifier les cas limites.\n"
FLUX = [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"},
        {"id": "qa", "nom": "Recette", "role": "qa", "service": "dev"},
        {"id": "livraison", "nom": "Livraison", "role": "dev", "service": "dev"}]


class Base(AvecProjet):
    lieu = "local"

    def setUp(self):
        super().setUp()
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f.update(flux=FLUX, agents_locaux_max=2, agents_cloud_max=2)
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        for nom in ("lea.md", "hugo.md"):
            (self.dossier / "fiches" / nom).unlink()
        briefs = self.dossier / "fiches" / "briefs"
        briefs.mkdir()
        (briefs / "dev.md").write_text(BRIEF_DEV, encoding="utf-8")
        (briefs / "qa.md").write_text(BRIEF_QA, encoding="utf-8")
        (self.dossier / "fiches" / "zoe.md").write_text(f"Clé : agent-1\nPrénom : Zoé\nLieu : {self.lieu}\n",
                                                        encoding="utf-8")
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Des écrans"})
        self.ok("demande-traitee", entree={"id": "r1"})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})

    def tache(self, role, element, titre="Écran"):
        return self.ok("tache", entree={"titre": titre, "fonctionnalite": "f1", "role": role, "colonne": role,
                                        "etape": f"flux:{role}", "element": element, "active": False})["id"]


class Message(Base):
    def test_message_specialiste_du_metier_de_la_tache(self):
        t_dev, t_qa = self.tache("dev", "e1"), self.tache("qa", "e2", "Recette")
        m = self.ok("depart", entree={"agent": "agent-1", "tache": t_dev, "moteur": True})["message"]
        self.assertIn("## Ton métier : dev", m)
        for attendu in ("Brief des développeurs.", "Spécialité : écrans du jeu", "Bash(gradle:*)", "Toujours tester."):
            self.assertIn(attendu, m)
        self.assertNotIn("Pas encore la règle.", m)
        self.assertNotIn("Brief des testeurs.", m)
        m = self.ok("depart", entree={"agent": "agent-1", "tache": t_qa, "moteur": True})["message"]
        for attendu in ("## Ton métier : qa", "Brief des testeurs.", "recette sur émulateur", "Vérifier les cas limites."):
            self.assertIn(attendu, m)
        self.assertNotIn("Toujours tester.", m)

    def test_lot_multi_metiers_porte_chaque_brief(self):
        t_dev, t_qa = self.tache("dev", "e1"), self.tache("qa", "e2", "Recette")
        m = self.ok("depart", entree={"agent": "agent-1", "taches": [t_dev, t_qa], "moteur": True})["message"]
        self.assertIn("## Ton métier : les métiers de ce lot", m)
        for attendu in ("### Métier : dev", "### Métier : qa", "### Rôle : dev", "### Rôle : qa", "Brief des développeurs.",
                        "Brief des testeurs.", "Toujours tester.", "Vérifier les cas limites."):
            self.assertIn(attendu, m)
        self.assertNotIn("## Ta fiche", m)

    def test_outils_du_metier_ouverts_a_l_agent(self):
        t_dev = self.tache("dev", "e1")
        lances = Agents()
        projet = regles.Projet(self.factory, feu_vert=lambda: True, cloud_max=0, prerequis=lambda: None)
        moteur = boucle.Moteur([projet], executer_agent=lances, synchrone=True, commit=lambda d, m: None)
        etat = moteur._etat(projet)
        moteur._executer(projet, regles._demarrer_en_attente(projet, etat, None))
        fiche = lances.lances[0]["fiche"]
        self.assertEqual(lances.lances[0]["tache"], t_dev)
        self.assertIn("Bash(gradle:*)", fiche["outils"])
        self.assertIn("Bash(git:*)", fiche["outils"])        # les outils par défaut restent


class SessionCloud(Base):
    lieu = "cloud"

    def test_meme_session_cloud_pour_deux_metiers(self):
        faux = FauxCloud()
        faux.panne = cloud.SANS_TERMINAL
        temps = [10_000.0]
        projet = regles.Projet(self.factory, feu_vert=lambda: True, cloud_max=2, prerequis=lambda: None)
        moteur = boucle.Moteur([projet], horloge=lambda: temps[0], synchrone=True, session_cloud=faux,
                               commit=lambda d, m: None, executer_agent=lambda *a, **k: self.fail("agent local"))

        def avancer(secondes=5):
            temps[0] += secondes
            moteur.tour()

        t_dev = self.tache("dev", "e1")
        avancer(0)
        avancer()
        suivi = json.loads((self.dossier / "suivi.json").read_text(encoding="utf-8"))
        d = next(x for x in suivi["decisions_projet"] if x["genre"] == "session_cloud")
        self.assertEqual(d["agent"], "agent-1")
        self.assertIn("Ton métier : dev", d["depart"])
        self.assertNotIn("None", d["texte"])
        self.ok("actions", entree={"type": "session_cloud", "decision": d["id"],
                                   "session": "https://claude.ai/code/session_01Manuel"})
        avancer()
        faux.rapports[t_dev] = ("claude/manuel", {**RAPPORT_FAIT, "fichiers": [], "lecons": [], "controles": [],
                                                  "retours_factory": [], "verdicts": []})
        avancer(70)
        # une tâche d'un autre métier : la même session, avec le métier de cette tâche
        t_qa = self.tache("qa", "e2", "Recette")
        avancer()
        self.assertEqual(faux.lancees, [])
        self.assertEqual(len(faux.suites), 1)
        session, texte = faux.suites[0]
        self.assertEqual(session, "session_01Manuel")
        self.assertIn(f".factory/rapports/{t_qa}.json", texte)
        self.assertIn("Ton métier : qa", texte)
