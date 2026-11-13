"""Le moteur et les agents polyvalents : n'importe quel agent libre prend la tâche prête, au bon lieu, et aucune tâche dont
l'amont attend une validation du Directeur ne part, par aucun chemin (conception 2026-11-13-agents-polyvalents-design.md).
Aucun appel réel."""
import json

from moteur import regles
from tests.orch_aide import AvecProjet

POLYVALENT = "Clé : {cle}\nPrénom : {prenom}\nLieu : {lieu}\n{session}"
ANCIENNE = ("Clé : {cle}\nPrénom : {prenom}\nRôle : dev\nService : dev\nModèle : {modele}\nLieu : local\n\n"
            "Développe.\n\n## Leçons\n")
FLUX = [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"},
        {"id": "val", "nom": "Essai", "validation": True},
        {"id": "qa", "nom": "Recette", "role": "qa", "service": "dev"},
        {"id": "archi", "nom": "Architecture", "role": "dev", "service": "dev", "modele": "Opus",
         "justification": "Conception difficile."},
        {"id": "livraison", "nom": "Livraison", "role": "dev", "service": "dev"}]
SESSION = "https://claude.ai/code/session_01Abc"


class Base(AvecProjet):
    locaux, cloud = 2, 0

    def setUp(self):
        super().setUp()
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f.update(flux=FLUX, agents_locaux_max=self.locaux, agents_cloud_max=self.cloud)
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        for nom in ("lea.md", "hugo.md"):
            (self.dossier / "fiches" / nom).unlink()
        self.briefs = self.dossier / "fiches" / "briefs"
        self.briefs.mkdir()
        self.brief("dev", "Service : dev\n\nBrief des développeurs.\n")
        self.brief("qa", "Brief des testeurs.\n")
        self.projet = regles.Projet(self.factory, feu_vert=lambda: True, cloud_max=self.cloud, prerequis=lambda: None)
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Des écrans"})
        self.ok("demande-traitee", entree={"id": "r1"})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})

    def brief(self, role, texte):
        (self.briefs / f"{role}.md").write_text(texte, encoding="utf-8")

    def agent(self, cle, prenom="Zoé", lieu="local", session=None):
        (self.dossier / "fiches" / f"{cle}.md").write_text(
            POLYVALENT.format(cle=cle, prenom=prenom, lieu=lieu, session=f"Session : {session}\n" if session else ""),
            encoding="utf-8")

    def tache(self, etape, element="e1", titre="Écran", **extra):
        entree = {"titre": titre, "fonctionnalite": "f1", "colonne": etape.split(":")[-1], "etape": etape,
                  "element": element, "active": False, **extra}
        if not etape.startswith("validation:"):
            entree["role"] = "qa" if etape == "flux:qa" else "dev"
        return self.ok("tache", entree=entree)["id"]

    def commencee(self, tid, agent):
        """Une tâche déjà prise un moment (son début est noté), plus active."""
        self.ok("tache", entree={"id": tid, "agent": agent, "active": True})
        self.ok("tache", entree={"id": tid, "active": False})

    def faite(self, tid):
        self.ok("tache", entree={"id": tid, "colonne": "fait", "active": False})

    def demarrer(self, etat=None):
        etat = etat if etat is not None else regles.nouvel_etat()
        regles._demarrer_en_attente(self.projet, etat, None)
        return etat

    @staticmethod
    def parties(etat):
        """{tâche: agent} de tout ce qui est parti (lots compris)."""
        return {i: d["agent"] for d in etat["departs"].values() for i in d["taches"]}


class Choix(Base):
    def test_un_agent_prend_des_taches_de_metiers_differents(self):
        self.agent("agent-1")
        t_dev = self.tache("flux:dev", element="e1")
        t_qa = self.tache("flux:qa", element="e2")
        etat = self.demarrer()
        parties = self.parties(etat)
        if t_qa not in parties:       # pas dans le même lot : le même agent la prend après la première
            self.faite(t_dev)
            etat["en_cours"].clear()
            parties.update(self.parties(self.demarrer(etat)))
        self.assertEqual(parties, {t_dev: "agent-1", t_qa: "agent-1"})

    def test_reprise_revient_au_meme_agent_libre(self):
        self.agent("agent-1")
        self.agent("agent-2", prenom="Max")
        t = self.tache("flux:dev")
        self.commencee(t, "agent-2")
        etat = regles.nouvel_etat()
        etat["a_lancer"].append(t)
        self.assertEqual(self.parties(self.demarrer(etat)), {t: "agent-2"})

    def test_reprise_par_un_autre_agent_si_l_ancien_est_occupe(self):
        self.agent("agent-1")
        self.agent("agent-2", prenom="Max")
        occupee = self.tache("flux:dev", element="e9", titre="Autre")
        self.ok("tache", entree={"id": occupee, "agent": "agent-2", "active": True})
        t = self.tache("flux:dev")
        self.commencee(t, "agent-1")
        self.ok("tache", entree={"id": t, "agent": "agent-2"})
        etat = regles.nouvel_etat()
        etat["a_lancer"].append(t)
        self.assertEqual(self.parties(self.demarrer(etat)), {t: "agent-1"})


class Lieux(Base):
    locaux, cloud = 1, 1

    def setUp(self):
        super().setUp()
        self.agent("local-1")
        self.agent("cloud-1", prenom="Max", lieu="cloud", session=SESSION)
        occupee = self.tache("flux:dev", element="e9", titre="Autre")
        self.ok("tache", entree={"id": occupee, "agent": "local-1", "active": True})   # la place locale est prise

    def test_metier_local_attend_une_place_locale(self):
        self.brief("qa", "Lieu : local\n\nBrief des testeurs, avec l'émulateur du poste.\n")
        t = self.tache("flux:qa")
        self.assertNotIn(t, self.parties(self.demarrer()))

    def test_cloud_quand_le_local_est_plein(self):
        t = self.tache("flux:qa")
        self.assertEqual(self.parties(self.demarrer()), {t: "cloud-1"})


class Amont(Base):
    """L'élément e1 attend la validation du Directeur (étape « val ») : sa recette (« qa », après la validation) ne part
    par aucun chemin, même avec des places libres ; la barre le dit."""
    locaux, cloud = 2, 1

    def setUp(self):
        super().setUp()
        self.agent("agent-1")
        self.agent("agent-2", prenom="Max")
        self.validation = self.tache("validation:val")
        self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "valider_etape", "fonctionnalite": "f1",
                                    "texte": "L'élément « e1 » attend votre validation.", "element": {"id": "e1", "nom": "e1"},
                                    "etape": "val", "tache": self.validation})
        self.qa = self.tache("flux:qa")

    def bloquee(self, etat):
        self.assertNotIn(self.qa, self.parties(etat))
        regles._noter_les_places_libres(self.projet, etat)
        self.assertIn("attente_validation", etat)
        self.assertIn("Essai", etat["attente_validation"]["texte"])

    def test_amont_en_validation_bloque_lot(self):
        autre = self.tache("flux:dev", element="e2")
        etat = self.demarrer()
        self.assertIn(autre, self.parties(etat))       # l'autre élément part, lui
        self.assertNotIn(self.qa, self.parties(etat))
        # la place qu'il reste ne sert à rien : la barre le dit
        self.faite(autre)
        etat["en_cours"].clear()
        etat["departs"].clear()
        self.bloquee(self.demarrer(etat))

    def test_amont_en_validation_bloque_a_lancer(self):
        self.commencee(self.qa, "agent-1")
        etat = regles.nouvel_etat()
        etat["a_lancer"].append(self.qa)
        self.bloquee(self.demarrer(etat))

    def test_amont_en_validation_bloque_retour(self):
        self.commencee(self.qa, "agent-1")
        self.ok("tache", entree={"id": self.qa, "bloquee": "Une erreur."})
        etat = regles.nouvel_etat()
        regles._reprendre_la_tache(self.projet, etat, self.qa, "f1", "Reprends avec ma consigne.", "Reprise sur retour.")
        self.bloquee(etat)

    def test_amont_en_validation_bloque_reprise_apres_redemarrage(self):
        self.commencee(self.qa, "agent-1")
        etat = regles.nouvel_etat()      # un moteur neuf : il ne sait rien de la tâche
        self.assertEqual(regles.orphelines(self.projet, etat), [])
        self.bloquee(self.demarrer(etat))

    def test_amont_en_validation_bloque_session_cloud(self):
        self.agent("cloud-1", prenom="Léo", lieu="cloud")
        self.commencee(self.qa, "cloud-1")
        self.ok("tache", entree={"id": self.qa, "bloquee": "session cloud : pas de terminal"})
        d = self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "session_cloud", "agent": "cloud-1",
                                        "tache": self.qa, "texte": "Créez la session."})["id"]
        etat = regles.nouvel_etat()
        regles.traiter_demande(self.projet, {"id": "r9", "type": "session_cloud", "decision": d,
                                             "session": "https://claude.ai/code/session_01Manuel"}, etat)
        t = next(x for x in regles._etat(self.projet)["taches"] if x["id"] == self.qa)
        self.assertFalse(t["active"])
        self.assertNotIn(self.qa, etat["en_cours"])
        self.bloquee(self.demarrer(etat))


class NonRepris(AvecProjet):
    """Un projet aux fiches à l'ancienne : mêmes agents, mêmes modèles qu'avant, même avec des briefs à en-tête."""

    def setUp(self):
        super().setUp()
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["flux"] = FLUX
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        (self.dossier / "fiches" / "lea.md").unlink()
        for cle, prenom, modele in (("dev-o", "Max", "Opus"), ("dev-s", "Léa", "Sonnet")):
            (self.dossier / "fiches" / f"{cle}.md").write_text(ANCIENNE.format(cle=cle, prenom=prenom, modele=modele),
                                                               encoding="utf-8")
        (self.dossier / "fiches" / "briefs").mkdir()
        (self.dossier / "fiches" / "briefs" / "dev.md").write_text("Modèle : Haiku\nLieu : cloud\n\nBrief.\n",
                                                                   encoding="utf-8")
        self.projet = regles.Projet(self.factory, feu_vert=lambda: True, cloud_max=0, prerequis=lambda: None)
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Des écrans"})
        self.ok("demande-traitee", entree={"id": "r1"})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})

    def tache(self, etape, element):
        return self.ok("tache", entree={"titre": "Écran", "fonctionnalite": "f1", "role": "dev", "colonne": "dev",
                                        "etape": etape, "element": element, "active": False})["id"]

    def test_projet_non_repris_choisit_comme_avant(self):
        archi, dev = self.tache("flux:archi", "e1"), self.tache("flux:dev", "e2")
        etat = regles.nouvel_etat()
        regles._demarrer_en_attente(self.projet, etat, "f1")
        vu = {d["taches"][0]: (d["agent"], d["modele"]) for d in etat["departs"].values()}
        self.assertEqual(vu, {archi: ("dev-o", "Opus"), dev: ("dev-s", "Sonnet")})
        # la reprise d'une tâche commencée attend son agent, comme avant
        court = regles._etat(self.projet)
        self.assertEqual(regles._modele_de_depart(self.projet, court, "dev-s",
                                                  next(t for t in court["taches"] if t["id"] == dev)), "Sonnet")
