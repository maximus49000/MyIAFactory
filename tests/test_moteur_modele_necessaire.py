"""Le moteur : un agent (local ou cloud) fait tourner la tâche sur son modèle nécessaire, jamais au-dessus du modèle de
sa fiche, qui est son plafond (conception 2026-11-12-modele-par-tache-design.md). Aucun appel réel."""
import json

from moteur import regles
from tests.orch_aide import AvecProjet

FICHE = ("Clé : {cle}\nPrénom : {prenom}\nRôle : dev\nService : dev\nModèle : {modele}\nLieu : {lieu}\n\n"
         "Développe.\n\n## Leçons\n")
FLUX = [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"},
        {"id": "tests", "nom": "Tests", "role": "dev", "service": "dev"},
        {"id": "archi", "nom": "Architecture", "role": "dev", "service": "dev", "modele": "Opus",
         "justification": "Conception difficile."},
        {"id": "relecture", "nom": "Relecture", "role": "relecteur", "service": "dev"}]


class Base(AvecProjet):
    def setUp(self):
        super().setUp()
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["flux"] = FLUX
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        (self.dossier / "fiches" / "lea.md").unlink()
        self.projet = regles.Projet(self.factory, feu_vert=lambda: True, cloud_max=0, prerequis=lambda: None)
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Des écrans"})
        self.ok("demande-traitee", entree={"id": "r1"})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})

    def agent(self, cle, modele, lieu="local", prenom="Léa"):
        (self.dossier / "fiches" / f"{cle}.md").write_text(
            FICHE.format(cle=cle, prenom=prenom, modele=modele, lieu=lieu), encoding="utf-8")

    def tache(self, etape, titre="Écran", **extra):
        return self.ok("tache", entree={"titre": titre, "fonctionnalite": "f1", "role": "dev", "colonne": "dev",
                                        "etape": etape, "element": "e1", "active": False, **extra})["id"]

    def demarrer(self):
        etat = regles.nouvel_etat()
        regles._demarrer_en_attente(self.projet, etat, "f1")
        return etat


class Local(Base):
    def test_agent_opus_fait_tourner_la_tache_sur_son_modele_necessaire(self):
        self.agent("dev-1", "Opus")
        t = self.tache("flux:tests")
        etat = self.demarrer()
        self.assertEqual((etat["departs"][t]["agent"], etat["departs"][t]["modele"]), ("dev-1", "Haiku"))

    def test_plus_petit_plafond_suffisant_d_abord(self):
        self.agent("dev-o", "Opus", prenom="Max")
        self.agent("dev-s", "Sonnet")
        t = self.tache("flux:dev")
        etat = self.demarrer()
        self.assertEqual((etat["departs"][t]["agent"], etat["departs"][t]["modele"]), ("dev-s", "Sonnet"))

    def test_jamais_au_dessus_du_plafond(self):
        """Étape Opus : l'agent Opus la prend ; un agent Sonnet seul la fait en Sonnet (ramené au plafond de l'équipe)."""
        self.agent("dev-s", "Sonnet")
        t = self.tache("flux:archi")
        etat = self.demarrer()
        self.assertEqual((etat["departs"][t]["agent"], etat["departs"][t]["modele"]), ("dev-s", "Sonnet"))

    def test_l_agent_au_plafond_suffisant_est_attendu(self):
        """Un agent Opus existe mais il est occupé : la tâche Opus l'attend, le Sonnet libre ne la prend pas."""
        self.agent("dev-o", "Opus", prenom="Max")
        self.agent("dev-s", "Sonnet")
        occupe = self.tache("flux:dev", titre="Autre")
        self.ok("tache", entree={"id": occupe, "active": True, "agent": "dev-o"})
        t = self.tache("flux:archi")
        etat = self.demarrer()
        self.assertNotIn(t, etat["departs"])

    def test_montee_plafonnee(self):
        self.agent("dev-s", "Sonnet")
        t = self.tache("flux:tests", montee={"de": "Sonnet", "a": "Opus", "raison": "trois échecs"})
        etat = self.demarrer()
        self.assertEqual(etat["departs"][t]["modele"], "Sonnet")

    def test_correction_sur_le_modele_de_l_etape_du_role(self):
        self.agent("dev-1", "Opus")
        t = self.tache("correction")
        etat = self.demarrer()
        self.assertEqual(etat["departs"][t]["modele"], "Sonnet")          # la première étape du rôle dev

    def test_reprise_apres_disparition_garde_le_modele_necessaire(self):
        self.agent("dev-1", "Opus")
        t = self.tache("flux:tests")
        court = regles._etat(self.projet)
        tache = next(x for x in court["taches"] if x["id"] == t)
        self.assertEqual(regles._modele_de_depart(self.projet, court, "dev-1", tache), "Haiku")
