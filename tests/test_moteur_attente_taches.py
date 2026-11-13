"""Pourquoi une tâche prête ne part pas : le moteur le dit au bureau à chaque passage (`etat["attente_taches"]`), en
quatre familles — prérequis, agent, décision, pause. Une tâche qui part, ou un projet où rien n'attend, n'a rien.
Aucun appel réel."""
import json
import time

from moteur import regles
from tests.test_moteur_polyvalents import FLUX, SESSION, Base


class Attentes(Base):
    locaux, cloud = 1, 1

    def setUp(self):
        super().setUp()
        self.agent("local-1", prenom="Léa")
        self.agent("cloud-1", prenom="Max", lieu="cloud", session=SESSION)

    def lieu(self, etape, lieu):
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["flux"] = [dict(e, lieu=lieu) if e["id"] == etape else e for e in f["flux"]]
        self.factory.write_text(json.dumps(f), encoding="utf-8")

    def occuper(self, agent, titre="Autre", element="e9", etape="flux:dev"):
        t = self.tache(etape, element=element, titre=titre)
        self.ok("tache", entree={"id": t, "agent": agent, "active": True})
        return t

    def raisons(self, etat=None):
        """Démarre ce qui peut partir, puis note les raisons ; rend `etat`."""
        etat = self.demarrer(etat)
        regles.noter_les_attentes(self.projet, etat)
        return etat

    def raison(self, etat, tid):
        return etat["attente_taches"]["taches"][tid]


class Agent(Attentes):
    def test_poste_local_occupe(self):
        self.occuper("local-1", titre="Combat")
        self.lieu("qa", "local")
        t = self.tache("flux:qa")
        r = self.raison(self.raisons(), t)
        self.assertEqual((r["genre"], r["motif"]), ("agent", "poste local occupé"))
        self.assertEqual(r["texte"], "poste local occupé")
        tout = " ".join(r["detail"])
        self.assertIn("poste local", tout)
        self.assertIn("1 place locale, occupée par Léa", tout)
        self.assertIn("poste local", r["quand"])

    def test_aucun_agent_cloud_libre(self):
        self.occuper("cloud-1", titre="Carte")
        self.lieu("qa", "cloud")
        t = self.tache("flux:qa")
        r = self.raison(self.raisons(), t)
        self.assertEqual((r["genre"], r["motif"]), ("agent", "aucun agent cloud libre"))
        self.assertIn("Max", " ".join(r["detail"]))
        self.assertIn("cloud", r["quand"])

    def test_aucun_agent_libre_sans_lieu_impose(self):
        self.occuper("local-1")
        self.occuper("cloud-1", element="e8")
        t = self.tache("flux:qa")
        r = self.raison(self.raisons(), t)
        self.assertEqual((r["genre"], r["motif"]), ("agent", "aucun agent libre"))
        self.assertIn("Léa", " ".join(r["detail"]))
        self.assertIn("Max", " ".join(r["detail"]))


class Prerequis(Attentes):
    def test_etape_d_avant_pas_faite_avec_son_agent(self):
        dev = self.occuper("local-1", titre="Écran", element="e1")
        t = self.tache("flux:qa")
        r = self.raison(self.raisons(), t)
        self.assertEqual((r["genre"], r["motif"]), ("prerequis", "prérequis"))
        self.assertEqual(r["texte"], "prérequis — Développement")
        tout = " ".join(r["detail"])
        self.assertIn("Léa", tout)
        self.assertIn("en cours depuis", tout)
        self.assertIn("Développement", r["quand"])
        self.assertNotIn(dev, self.raisons()["attente_taches"]["taches"])     # une tâche active n'attend pas

    def test_dependance_pas_faite(self):
        avant = self.tache("flux:dev", element="e2", titre="Le socle")
        self.ok("tache", entree={"id": avant, "agent": "cloud-1", "active": True})
        t = self.tache("flux:dev", depend_de=[avant])
        r = self.raison(self.raisons(), t)
        self.assertEqual(r["genre"], "prerequis")
        self.assertEqual(r["texte"], "prérequis — « Le socle »")
        self.assertIn("Max", " ".join(r["detail"]))

    def test_barriere_avec_l_element_qui_retient_et_son_agent(self):
        """« 1 élément pas encore validé — « Profil », … par Léa (en cours depuis …) », la barrière « Essai »."""
        self.ok("file", entree={"fonctionnalite": "f1", "elements": [{"id": "e1", "nom": "Accueil", "groupe": "écrans"},
                                                                      {"id": "e2", "nom": "Profil", "groupe": "écrans"}]})
        for e in ("e1", "e2"):
            self.ok("file-prendre", entree={"fonctionnalite": "f1", "element": e})
        self.occuper("local-1", titre="Profil", element="e2")         # e2 n'a pas encore atteint la validation
        t = self.tache("flux:qa", element="e1")                         # e1 est passé : sa recette attend la barrière
        r = self.raison(self.raisons(), t)
        self.assertEqual(r["genre"], "prerequis")
        self.assertEqual(r["texte"], "prérequis — Essai")
        tout = " ".join(r["detail"])
        self.assertIn("1 élément pas encore validé", tout)
        self.assertIn("« Profil »", tout)
        self.assertIn("Léa", tout)
        self.assertIn("en cours depuis", tout)
        self.assertIn("Essai", r["quand"])

    def test_ce_qu_il_lui_faudra_ensuite(self):
        """Retenue par un prérequis, elle dit aussi le lieu qu'elle exigera, et qui l'occupe."""
        self.occuper("local-1", titre="Écran", element="e1")
        self.lieu("qa", "local")
        t = self.tache("flux:qa")
        r = self.raison(self.raisons(), t)
        self.assertEqual(r["genre"], "prerequis")
        self.assertEqual(r["ensuite"], ["elle exige le poste local ; 1 place locale, occupée par Léa"])
        self.assertFalse(any("exige" in x for x in r["detail"]))

    def test_rien_ensuite_sans_lieu_impose(self):
        self.occuper("local-1", titre="Écran", element="e1")
        t = self.tache("flux:qa")
        self.assertEqual(self.raison(self.raisons(), t)["ensuite"], [])


class Decision(Attentes):
    FLUX_FABLE = FLUX + [{"id": "preuve", "nom": "Preuve formelle", "role": "dev", "service": "dev", "modele": "Fable",
                          "justification": "Une preuve que seul Fable mène à bien."}]

    def test_fable_a_autoriser(self):
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f["flux"] = self.FLUX_FABLE
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        t = self.tache("flux:preuve")
        r = self.raison(self.raisons(), t)
        self.assertEqual((r["genre"], r["motif"]), ("decision", "décision à prendre"))
        self.assertIn("Fable", r["texte"])
        self.assertIn("répondu", r["quand"])


class Pause(Attentes):
    def test_charge_du_pc(self):
        self.projet._feu_vert = None
        self.projet._mesure = lambda: {"feu_vert": False, "charge": 90, "plafond": 70}
        self.lieu("dev", "local")
        t = self.tache("flux:dev")
        r = self.raison(self.raisons(), t)
        self.assertEqual((r["genre"], r["motif"]), ("pause", "charge du PC"))
        self.assertIn("90 %", r["texte"])
        self.assertIn("70 %", r["quand"])

    def test_panne_du_service(self):
        t = self.tache("flux:dev")
        etat = regles.nouvel_etat()
        etat["panne"] = {"jusqu_a": time.time() + 300, "texte": "Service Claude indisponible (500) : nouvel essai à 12 h 05.",
                         "n": 1}
        r = self.raison(self.raisons(etat), t)
        self.assertEqual((r["genre"], r["motif"]), ("pause", "service Claude indisponible"))
        self.assertIn("12 h 05", " ".join(r["detail"]))

    def test_projet_en_pause(self):
        t = self.tache("flux:dev")
        self.ok("actions", entree={"type": "bouton", "id": "pause"})
        etat = regles.nouvel_etat()
        regles.avancer(self.projet, etat)
        r = self.raison(etat, t)
        self.assertEqual((r["genre"], r["motif"]), ("pause", "projet en pause"))

    def test_pause_d_une_installation(self):
        t = self.tache("flux:dev")
        self.projet.pause_globale = "Pause : installation de Godot Engine (Jeu)"
        r = self.raison(self.raisons(), t)
        self.assertEqual((r["genre"], r["motif"]), ("pause", "installation en cours"))
        self.assertIn("Godot Engine", " ".join(r["detail"]))


class Resume(Attentes):
    def test_une_tache_qui_part_n_a_pas_de_raison(self):
        t = self.tache("flux:dev")
        etat = self.raisons()
        self.assertIn(t, self.parties(etat))
        self.assertNotIn("attente_taches", etat)

    def test_un_projet_sans_attente_n_a_rien(self):
        self.assertNotIn("attente_taches", self.raisons())

    def test_une_tache_bloquee_reste_a_part(self):
        self.occuper("local-1")
        self.occuper("cloud-1", element="e8")
        t = self.tache("flux:qa", bloquee="Trois échecs.")
        self.assertNotIn(t, (self.raisons().get("attente_taches") or {}).get("taches", {}))

    def test_resume_par_famille(self):
        self.occuper("local-1", titre="Écran", element="e1")
        self.occuper("cloud-1", element="e8")
        a = self.tache("flux:qa")                       # prérequis : l'étape d'avant de e1 n'est pas faite
        b = self.tache("flux:dev", element="e2")        # aucun agent libre
        c = self.tache("flux:dev", element="e3")        # aucun agent libre
        resume = self.raisons()["attente_taches"]
        self.assertEqual(set(resume["taches"]), {a, b, c})
        self.assertEqual(resume["texte"], "3 tâches en attente")
        self.assertEqual(resume["total"], 3)
        self.assertEqual(resume["familles"], [{"genre": "prerequis", "motif": "prérequis", "n": 1, "texte": "1 prérequis"},
                                              {"genre": "agent", "motif": "aucun agent libre", "n": 2,
                                               "texte": "2 attendent un agent libre"}])

    def test_avancer_note_les_attentes_a_chaque_passage(self):
        self.occuper("local-1")
        self.occuper("cloud-1", element="e8")
        t = self.tache("flux:dev", element="e2")
        etat = regles.nouvel_etat()
        regles.avancer(self.projet, etat)
        self.assertIn(t, etat["attente_taches"]["taches"])
        self.ok("tache", entree={"id": t, "bloquee": "Raison."})
        regles.avancer(self.projet, etat)
        self.assertNotIn("attente_taches", etat)
