"""Les leçons par métier : un agent polyvalent note et reçoit les leçons du métier de sa tâche."""
from orchestrateur import factory as fa
from orchestrateur import fiches, metiers
from orchestrateur import suivi as su
from tests.orch_aide import AvecProjet

POLYVALENT = "Clé : agent-1\nPrénom : Zoé\nLieu : local\n"


class TestLeconsMetier(AvecProjet):
    def setUp(self):
        super().setUp()
        self.fiches = self.dossier / "fiches"
        self.briefs = self.fiches / "briefs"
        self.briefs.mkdir()
        (self.briefs / "dev.md").write_text("Service : dev\n\nBrief des développeurs.\n\n## Leçons\n"
                                            "- [validée] dev:L1 : Toujours tester.\n", encoding="utf-8")
        (self.briefs / "qa.md").write_text("Brief des testeurs.\n\n## Leçons\n"
                                           "- [validée] qa:L1 : Vérifier les cas limites.\n", encoding="utf-8")
        (self.fiches / "agent.md").write_text(POLYVALENT, encoding="utf-8")

    def tache(self, role, titre="Une tâche"):
        return self.ok("tache", entree={"titre": titre, "role": role})["id"]

    def noter(self, agent="agent-1", **extra):
        entree = {"action": "noter", "agent": agent, "texte": "Relancer les tests.", "etage_propose": "projet"}
        entree.update(extra)
        return self.ok("lecon", entree=entree)

    def metier(self, role):
        return metiers.lire_metier(self.briefs, role)

    def test_lecon_polyvalent_id_par_role(self):
        t = self.tache("dev")
        i = self.noter(tache=t)["id"]
        self.assertTrue(i.startswith("dev:L"), i)
        self.assertIn({"etat": "à valider", "id": i, "texte": "Relancer les tests."}, self.metier("dev")["lecons"])
        self.assertEqual(self.metier("qa")["lecons"], [{"etat": "validée", "id": "qa:L1", "texte": "Vérifier les cas limites."}])
        self.assertEqual(fiches.lire_fiche(self.fiches / "agent.md")["lecons"], [])   # la fiche de l'agent reste nue
        # sans tâche, un polyvalent ne sait pas à quel métier la leçon appartient : refus lisible
        self.assertEqual(self.outil("lecon", entree={"action": "noter", "agent": "agent-1", "texte": "T"})[0], 1)

    def test_lecon_validee_ecrite_dans_le_metier(self):
        t = self.tache("qa")
        i = self.noter(tache=t)["id"]
        self.assertTrue(i.startswith("qa:L"))
        self.ok("lecon", entree={"action": "appliquer", "id": i, "verdict": "valider"})
        self.assertIn({"etat": "validée", "id": i, "texte": "Relancer les tests."}, self.metier("qa")["lecons"])
        j = self.noter(tache=t, texte="Autre idée.")["id"]
        self.ok("lecon", entree={"action": "appliquer", "id": j, "verdict": "invalider"})
        self.assertNotIn(j, [x["id"] for x in self.metier("qa")["lecons"]])
        self.assertEqual(self.ok("releve")["lecons"], [])

    def test_ancien_id_valide_apres_reprise_va_au_metier(self):
        # une leçon notée à l'ancienne par dev-1 (id <agent>:L<n>), avant que la fiche devienne polyvalente
        t = self.tache("dev")
        i = self.noter(agent="dev-1", tache=t, texte="Leçon ancienne.")["id"]
        self.assertEqual(i, "dev-1:L1")
        (self.fiches / "lea.md").write_text("Clé : dev-1\nPrénom : Léa\nLieu : local\n", encoding="utf-8")   # la reprise
        self.ok("lecon", entree={"action": "appliquer", "id": i, "verdict": "valider"})
        self.assertIn({"etat": "validée", "id": i, "texte": "Leçon ancienne."}, self.metier("dev")["lecons"])
        # l'id de départ est un rôle connu (dev:L31), la fiche a disparu, la leçon ne dit pas son métier
        chemin = fa.lire(self.factory)["suivi"]
        with su.Suivi(chemin).transaction() as s:
            s["lecons"].append({"id": "dev:L31", "agent": "dev", "tache": None, "date": "2026-11-01", "texte": "Vieille.",
                                "etat": "à valider", "etage_propose": "projet", "texte_general": None, "roles": ["tous"]})
        self.ok("lecon", entree={"action": "appliquer", "id": "dev:L31", "verdict": "valider"})
        self.assertIn({"etat": "validée", "id": "dev:L31", "texte": "Vieille."}, self.metier("dev")["lecons"])

    def test_message_porte_les_lecons_du_metier_de_la_tache(self):
        t_dev, t_qa = self.tache("dev", "Écran"), self.tache("qa", "Recette")
        m_dev = self.ok("depart", entree={"agent": "agent-1", "tache": t_dev})["message"]
        m_qa = self.ok("depart", entree={"agent": "agent-1", "tache": t_qa})["message"]
        self.assertIn("## Ton métier", m_dev)
        self.assertNotIn("## Ta fiche", m_dev)
        self.assertIn("Toujours tester.", m_dev)
        self.assertIn("Brief des développeurs.", m_dev)
        self.assertNotIn("Vérifier les cas limites.", m_dev)
        self.assertIn("Vérifier les cas limites.", m_qa)
        self.assertNotIn("Toujours tester.", m_qa)
        self.assertEqual(m_dev.count("Brief des développeurs."), 1)

    def test_lecon_a_valider_absente_du_message(self):
        t = self.tache("dev")
        self.noter(tache=t, texte="Pas encore validée.")
        m = self.ok("depart", entree={"agent": "agent-1", "tache": t})["message"]
        self.assertNotIn("Pas encore validée.", m)

    def test_fiche_ancienne_message_inchange(self):
        t = self.tache("dev")
        m = self.ok("depart", entree={"agent": "dev-1", "tache": t})["message"]
        self.assertIn("## Ta fiche", m)
        self.assertNotIn("## Ton métier", m)
        self.assertIn("Nommer les écrans comme dans la maquette.", m)
        self.assertIn("Brief des développeurs", m)   # le brief du rôle : fichier entier, comme avant
        self.assertIn("Toujours tester.", m)
