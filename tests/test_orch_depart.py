import json
import unittest
from pathlib import Path

from orchestrateur import depart, factory, fiches, memoire
from tests.orch_aide import AvecProjet


def fiche(cle, role, modele="Sonnet", lieu="local", session=None, prenom=None):
    return {"cle": cle, "prenom": prenom or cle.title(), "role": role, "service": "dev", "modele": modele,
            "lieu": lieu, "session": session, "specialite": None, "texte": f"Texte de {cle}.", "lecons": []}


class TestDepart(unittest.TestCase):
    def test_monter(self):
        self.assertEqual(depart.monter("Haiku"), "Sonnet")
        self.assertEqual(depart.monter("Sonnet"), "Opus")
        self.assertEqual(depart.monter("Opus"), "Opus")   # on ne monte pas plus haut
        self.assertEqual(depart.monter("Inconnu"), "Inconnu")
        self.assertEqual(depart.monter("Fable"), "Fable")   # jamais choisi, jamais atteint par une montée

    def test_jamais_fable(self):
        for modele in ("Haiku", "Sonnet", "Opus", "Fable", "autre", ""):
            self.assertNotEqual(depart.monter(modele), "Fable" if modele != "Fable" else "")
        self.assertNotIn("Fable", depart.ECHELLE)
        # un outil ne choisit jamais Fable, même si une fiche le demandait : la fiche est refusée à la lecture
        with self.assertRaises(fiches.FicheInvalide):
            from tempfile import TemporaryDirectory
            with TemporaryDirectory() as t:
                p = Path(t) / "x.md"
                p.write_text("Clé : x\nRôle : dev\nModèle : Fable\nLieu : local\n", encoding="utf-8")
                fiches.lire_fiche(p)

    def test_agent_libre_occupe(self):
        liste = [fiche("dev-1", "dev"), fiche("dev-2", "dev"), fiche("qa-1", "qa")]
        taches = [{"agent": "dev-1", "active": True}, {"agent": "dev-2", "active": False}]
        self.assertEqual(depart.agent_libre(liste, taches, "dev")[0], "dev-2")   # dev-1 est pris
        cle, raison = depart.agent_libre(liste, taches + [{"agent": "dev-2", "active": True}], "dev")
        self.assertIsNone(cle)
        self.assertEqual(raison, "aucun dev libre")
        self.assertEqual(depart.agent_libre(liste, [], "design")[1], "aucun design libre")
        self.assertEqual(depart.agent_libre(liste, taches, "qa")[0], "qa-1")

    def test_agent_libre_modele_et_lieu(self):
        liste = [fiche("dev-1", "dev", "Sonnet"), fiche("dev-2", "dev", "Opus")]
        self.assertEqual(depart.agent_libre(liste, [], "dev", modele="Opus")[0], "dev-2")
        self.assertEqual(depart.agent_libre(liste, [], "dev", modele="Haiku"), (None, "aucun dev libre sur Haiku"))

    def test_agent_libre_cloud_manquant(self):
        liste = [fiche("prep-1", "preparateur", "Sonnet", "cloud", "Session prep"), fiche("prep-2", "preparateur", "Opus", "cloud")]
        self.assertEqual(depart.agent_libre(liste, [], "preparateur", "Sonnet", "cloud")[0], "prep-1")
        # Aucune fiche de ce rôle et de ce modèle : il faut d'abord en écrire une (pas de session à demander).
        cle, raison = depart.agent_libre(liste, [], "preparateur", "Haiku", "cloud")
        self.assertIsNone(cle)
        self.assertEqual(raison, "aucune fiche cloud preparateur sur Haiku : ajoutez-en une")
        self.assertIsNone(depart.sans_session(liste, "preparateur", "Haiku"))
        # La fiche existe, sans session : c'est elle qui attend sa session (la décision la nomme).
        cle, raison = depart.agent_libre(liste, [], "preparateur", "Opus", "cloud")
        self.assertIsNone(cle)
        self.assertEqual(raison, "aucun agent cloud preparateur sur Opus : session à créer pour prep-2")
        self.assertEqual(depart.sans_session(liste, "preparateur", "Opus"), "prep-2")
        # Occupé n'est pas « sans session » : on attend, on ne redemande pas une session qui existe.
        cle, raison = depart.agent_libre(liste, [{"agent": "prep-1", "active": True}], "preparateur", "Sonnet", "cloud")
        self.assertIsNone(cle)
        self.assertEqual(raison, "aucun agent cloud preparateur libre sur Sonnet")
        self.assertIsNone(depart.sans_session(liste, "preparateur", "Sonnet"))

    def test_agent_libre_local_ignore_le_cloud(self):
        liste = [fiche("prep-1", "preparateur", "Sonnet", "cloud", "S")]
        self.assertIsNone(depart.agent_libre(liste, [], "preparateur", lieu="local")[0])

    def message(self, lieu="local", lecons=None, brief="Brief du rôle dev.", tache=None):
        f = {"nom": "Projet démo", "genre": "vitrine"}
        t = tache or {"id": "t4", "titre": "Développer l'écran", "fonctionnalite": "f1", "element": "e2", "etape": "Mise en page"}
        return depart.message(f, fiche("dev-1", "dev", lieu=lieu), t, brief,
                              lecons or {"skill": [{"id": "S1", "titre": "Relire", "texte": "Relire avant de rendre."}],
                                         "genre": [{"id": "G1", "titre": "Textes", "texte": "Textes courts."}]})

    def test_message_contient_tout(self):
        m = self.message()
        for attendu in ("Projet démo", "vitrine", "Texte de dev-1.", "Relire avant de rendre.", "Textes courts.",
                        "Brief du rôle dev.", "Développer l'écran", "t4", "e2", "Mise en page", "leçons", "étage"):
            self.assertIn(attendu, m)
        self.assertNotIn("Tu repars de zéro.", m)
        self.assertLess(m.index("Texte de dev-1."), m.index("Brief du rôle dev."))   # fiche, puis brief, puis tâche
        self.assertLess(m.index("Brief du rôle dev."), m.index("Développer l'écran"))

    def test_message_sobre(self):
        # Les leçons « à valider » ne sont pas encore la règle : elles restent hors du message de départ ; et le message
        # demande de ne lire que ce que la tâche demande (le coût d'un agent vient surtout de ce qu'il relit).
        f = fiche("dev-1", "dev")
        f["lecons"] = [{"etat": "validée", "id": "dev-1:L1", "texte": "Règle sûre."},
                       {"etat": "à valider", "id": "dev-1:L2", "texte": "Idée pas encore validée."}]
        m = depart.message({"nom": "P", "genre": None}, f, {"id": "t1", "titre": "T"}, None, {"skill": [], "genre": []})
        self.assertIn("Règle sûre.", m)
        self.assertNotIn("Idée pas encore validée.", m)
        self.assertIn("Sobriété", m)
        # Une fiche écrite sur disque : ses lignes « à valider » sont retirées aussi.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "dev.md"
            chemin.write_text("\n".join(["Clé : dev-1", "Rôle : dev", "Modèle : Sonnet", "Lieu : local", "", "Texte.", "",
                                         "## Leçons", "- [validée] dev-1:L1 : Règle sûre.",
                                         "- [à valider] dev-1:L2 : Idée pas encore validée.", ""]), encoding="utf-8")
            m = depart.message({"nom": "P", "genre": None}, {**f, "chemin": str(chemin)}, {"id": "t1", "titre": "T"},
                               None, {"skill": [], "genre": []})
        self.assertIn("Règle sûre.", m)
        self.assertNotIn("Idée pas encore validée.", m)

    def test_message_sans_genre_ni_brief(self):
        m = depart.message({"nom": "P", "genre": None}, fiche("dev-1", "dev"), {"id": "t1", "titre": "T"}, None,
                           {"skill": [], "genre": []})
        self.assertIn("Texte de dev-1.", m)
        self.assertIn("T", m)

    def test_message_cloud_repart_de_zero(self):
        self.assertTrue(self.message("cloud").startswith("Tu repars de zéro."))


class TestDepartCommandes(AvecProjet):
    def preparer(self):
        (self.dossier / "fiches" / "briefs").mkdir()
        (self.dossier / "fiches" / "briefs" / "dev.md").write_text("Brief propre aux développeurs.", encoding="utf-8")
        mem = self.dossier / "memoire"
        (mem / "genres").mkdir(parents=True)
        (mem / "skill.md").write_text("# Mémoire\n\n## S1 — Pour les dev\nRôles : dev\nDate : 2026-11-01\n\nLeçon des dev.\n\n"
                                      "## S2 — Pour les qa\nRôles : qa\nDate : 2026-11-01\n\nLeçon des qa.\n", encoding="utf-8")
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d["genre"] = "vitrine"
        self.factory.write_text(json.dumps(d), encoding="utf-8")
        (mem / "genres" / "vitrine.md").write_text("# Genre : vitrine\nDomaine : d\nLivrable : l\nOutils : o\n\n"
                                                    "## G1 — Général\nRôles : tous\nDate : 2026-11-02\n\nLeçon de genre.\n", encoding="utf-8")

    def test_commande_agent_libre(self):
        self.ok("tache", entree={"titre": "A", "colonne": "dev", "agent": "dev-1"})
        self.assertEqual(self.ok("agent-libre", entree={"role": "dev"}), {"agent": None, "raison": "aucun dev libre"})
        self.assertEqual(self.ok("agent-libre", entree={"role": "cadrage"})["agent"], "metier-1")
        self.assertEqual(self.outil("agent-libre", entree={"modele": "Opus"})[0], 1)   # le rôle est obligatoire

    def test_agent_libre_voit_la_session_de_la_table(self):
        (self.dossier / "fiches" / "prep.md").write_text(
            "Clé : prep-1\nRôle : preparateur\nService : dev\nModèle : Sonnet\nLieu : cloud\n\n## Leçons\n", encoding="utf-8")
        entree = {"role": "preparateur", "modele": "Sonnet", "lieu": "cloud"}
        self.assertIsNone(self.ok("agent-libre", entree=entree)["agent"])
        self.ok("session", entree={"agent": "prep-1", "session": "Session prép"})
        self.assertEqual(self.ok("agent-libre", entree=entree)["agent"], "prep-1")

    def test_commande_depart(self):
        self.preparer()
        t = self.ok("tache", entree={"titre": "Développer l'écran", "role": "dev", "colonne": "dev"})
        m = self.ok("depart", entree={"agent": "dev-1", "tache": t["id"]})["message"]
        for attendu in ("Développer l'écran", "Brief propre aux développeurs.", "Leçon des dev.", "Leçon de genre.",
                        "Développe les écrans.", "Nommer les écrans"):
            self.assertIn(attendu, m)
        self.assertNotIn("Leçon des qa.", m)   # pas les leçons d'un autre rôle
        self.assertEqual(self.outil("depart", entree={"agent": "inconnu", "tache": t["id"]})[0], 1)
        self.assertEqual(self.outil("depart", entree={"agent": "dev-1", "tache": "t99"})[0], 1)

    def test_message_cloud_par_la_commande(self):
        (self.dossier / "fiches" / "prep.md").write_text(
            "Clé : prep-1\nRôle : preparateur\nService : dev\nModèle : Sonnet\nLieu : cloud\nSession : S\n\n## Leçons\n",
            encoding="utf-8")
        t = self.ok("tache", entree={"titre": "Préparer"})
        m = self.ok("depart", entree={"agent": "prep-1", "tache": t["id"]})["message"]
        self.assertTrue(m.startswith("Tu repars de zéro."))

    def test_message_montre_le_modele_de_la_tache_montee(self):
        t = self.ok("tache", entree={"titre": "Écran", "montee": {"de": "Haiku", "a": "Sonnet", "raison": "complexe"}})
        m = self.ok("depart", entree={"agent": "dev-1", "tache": t["id"]})["message"]
        self.assertIn("Sonnet", m)
        self.assertIn("Haiku", m)
