"""Le modèle d'un agent polyvalent : celui de la tâche, sans plafond ; Fable seulement sur l'accord du Directeur, tâche
par tâche, demandé avant le départ ; refus → Opus (conception 2026-11-13-agents-polyvalents-design.md). Aucun appel réel."""
import json

from installation import estimation
from moteur import boucle, regles
from orchestrateur import fiches
from tests.orch_aide import AvecProjet
from tests.test_moteur_boucle import Agents

POLYVALENT = "Clé : {cle}\nPrénom : {prenom}\nLieu : {lieu}\n"
FLUX = [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"},
        {"id": "archi", "nom": "Architecture", "role": "dev", "service": "dev", "modele": "Opus",
         "justification": "Conception difficile."},
        {"id": "preuve", "nom": "Preuve formelle", "role": "dev", "service": "dev", "modele": "Fable",
         "justification": "Une preuve que seul Fable mène à bien."},
        {"id": "livraison", "nom": "Livraison", "role": "dev", "service": "dev"}]


class Base(AvecProjet):
    def setUp(self):
        super().setUp()
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f.update(flux=FLUX, agents_locaux_max=2)
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        for nom in ("lea.md", "hugo.md"):
            (self.dossier / "fiches" / nom).unlink()
        (self.dossier / "fiches" / "briefs").mkdir()
        (self.dossier / "fiches" / "briefs" / "dev.md").write_text("Modèle : Haiku\n\nBrief des développeurs.\n",
                                                                   encoding="utf-8")
        self.agent("agent-1")
        self.projet = regles.Projet(self.factory, feu_vert=lambda: True, cloud_max=0, prerequis=lambda: None)
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Des écrans"})
        self.ok("demande-traitee", entree={"id": "r1"})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})

    def agent(self, cle, prenom="Zoé", lieu="local"):
        (self.dossier / "fiches" / f"{cle}.md").write_text(POLYVALENT.format(cle=cle, prenom=prenom, lieu=lieu),
                                                           encoding="utf-8")

    def tache(self, etape, role="dev", element="e1", **extra):
        return self.ok("tache", entree={"titre": "Écran", "fonctionnalite": "f1", "role": role, "colonne": "dev",
                                        "etape": etape, "element": element, "active": False, **extra})["id"]

    def demarrer(self, etat=None):
        etat = etat if etat is not None else regles.nouvel_etat()
        regles._demarrer_en_attente(self.projet, etat, None)
        return etat

    def modele(self, etat, tid):
        return (etat["departs"].get(tid) or {}).get("modele")

    def decisions(self, genre="fable_tache"):
        s = json.loads((self.dossier / "suivi.json").read_text(encoding="utf-8"))
        return [d for d in s["decisions_projet"] if d["genre"] == genre]

    def repondre(self, etat, verdict):
        d = self.decisions()[0]
        regles.traiter_demande(self.projet, {"id": "r9", "type": "fable_tache", "decision": d["id"], "verdict": verdict},
                               etat)
        return etat


class Modele(Base):
    def test_modele_de_l_etape_sans_plafond(self):
        t = self.tache("flux:archi")
        self.assertEqual(self.modele(self.demarrer(), t), "Opus")
        self.agent("agent-2", prenom="Max")
        u = self.tache("flux:dev", element="e2", montee={"de": "Sonnet", "a": "Opus", "raison": "deux échecs"})
        self.assertEqual(self.modele(self.demarrer(), u), "Opus")

    def test_tache_sans_etape_prend_le_modele_du_metier(self):
        t = self.tache("prototype")
        self.assertEqual(self.modele(self.demarrer(), t), "Haiku")

    def test_sans_metier_sonnet(self):
        t = self.tache("prototype", role="graphiste")
        self.assertEqual(self.modele(self.demarrer(), t), "Sonnet")


class Fable(Base):
    def test_etape_fable_pose_la_decision_et_attend(self):
        t = self.tache("flux:preuve")
        autre = self.tache("flux:dev", element="e2")
        etat = self.demarrer()
        self.assertNotIn(t, [i for d in etat["departs"].values() for i in d["taches"]])
        self.assertIn(autre, etat["departs"])           # les autres continuent
        d = self.decisions()
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["tache"], t)
        self.assertIn("seul Fable", d[0]["raison"])
        self.demarrer()                                 # reposée une seule fois
        self.assertEqual(len(self.decisions()), 1)

    def test_accord_fable_part_sur_fable(self):
        t = self.tache("flux:preuve")
        etat = self.repondre(self.demarrer(), "autoriser")
        self.assertEqual(self.modele(etat, t), "Fable")
        self.assertTrue(etat["departs"][t]["fable_accorde"])
        self.assertEqual(self.decisions(), [])
        tache = next(x for x in regles._etat(self.projet)["taches"] if x["id"] == t)
        self.assertIs(tache["fable_accordee"], True)

    def test_refus_fable_part_sur_opus(self):
        t = self.tache("flux:preuve")
        etat = self.repondre(self.demarrer(), "refuser")
        self.assertEqual(self.modele(etat, t), "Opus")
        self.assertEqual(self.decisions(), [])

    def test_montee_opus_vers_fable_demande_l_accord(self):
        t = self.tache("flux:archi", montee={"de": "Opus", "a": "Fable", "raison": "trois échecs sur Opus"})
        etat = self.demarrer()
        self.assertNotIn(t, etat["departs"])
        self.assertIn("trois échecs", self.decisions()[0]["raison"])
        # une montée vers Fable ne part que d'Opus
        self.assertEqual(self.outil("tache", entree={"id": t, "montee": {"de": "Sonnet", "a": "Fable", "raison": "x"}})[0], 1)

    def test_fable_jamais_sans_accord(self):
        # le départ ordinaire (lot, a_lancer, reprise) : la décision, pas de départ
        t = self.tache("flux:preuve")
        self.ok("tache", entree={"id": t, "agent": "agent-1", "active": True})
        self.ok("tache", entree={"id": t, "active": False})
        etat = regles.nouvel_etat()
        etat["a_lancer"].append(t)
        self.assertNotIn(t, self.demarrer(etat)["departs"])
        # la reprise après redémarrage d'une tâche active dont l'agent a disparu : Opus, jamais Fable
        self.ok("tache", entree={"id": t, "agent": "agent-1", "active": True})
        etat = regles.nouvel_etat()
        regles.orphelines(self.projet, etat)
        self.assertEqual(self.modele(etat, t), "Opus")
        court = regles._etat(self.projet)
        tache = next(x for x in court["taches"] if x["id"] == t)
        self.assertEqual(regles._modele_de_depart(self.projet, court, "agent-1", tache, "Fable"), "Opus")
        # un outil ne note jamais Fable comme modèle de départ sans accord
        self.assertEqual(self.outil("tache", entree={"id": t, "modele_depart": "Fable"})[0], 1)
        # le dernier garde : l'agent lancé sans accord sur sa tâche n'a pas Fable
        lances = Agents()
        moteur = boucle.Moteur([self.projet], executer_agent=lances, synchrone=True, commit=lambda d, m: None)
        etat = moteur._etat(self.projet)
        etat["departs"][t] = {"agent": "agent-1", "taches": [t], "matiere": "", "modele": "Fable", "lot": None,
                              "suite": None}
        moteur._executer(self.projet, [regles.a_agent("agent-1", [t], "")])
        self.assertFalse(fiches.fable_accorde(lances.lances[0]["fiche"]))

    def test_l_agent_lance_sur_accord_a_fable(self):
        t = self.tache("flux:preuve")
        lances = Agents()
        moteur = boucle.Moteur([self.projet], executer_agent=lances, synchrone=True, commit=lambda d, m: None)
        etat = moteur._etat(self.projet)
        regles._demarrer_en_attente(self.projet, etat, None)
        d = self.decisions()[0]
        actions = regles.traiter_demande(self.projet, {"id": "r9", "type": "fable_tache", "decision": d["id"],
                                                       "verdict": "autoriser"}, etat)
        moteur._executer(self.projet, actions)
        self.assertEqual(lances.lances[0]["modele"], "fable")
        self.assertTrue(fiches.fable_accorde(lances.lances[0]["fiche"]))


class Estimation(AvecProjet):
    def test_estimation_compte_opus(self):
        flux = [{"id": "preuve", "nom": "Preuve", "role": "dev", "service": "dev", "modele": "Fable",
                 "justification": "Seul Fable."}]
        agents = [{"role": "dev", "modele": "Fable"}]
        r = estimation.estimer(flux, agents, [], lambda m: None)
        self.assertEqual([d["modele"] for d in r["detail"]][1:], ["Opus"])
