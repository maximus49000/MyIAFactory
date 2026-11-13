"""L'équipe d'un projet polyvalent = les places de l'onglet Facturation (conception 2026-11-13-agents-polyvalents-design.md) :
monter une place crée un agent, la baisser en retire un libre, jamais un agent au travail (retiré à la fin de sa tâche)."""
import json

from orchestrateur import fiches
from tests.orch_aide import AvecProjet


class Base(AvecProjet):
    locaux = 2

    def setUp(self):
        super().setUp()
        self.fiches = self.dossier / "fiches"
        for nom in ("lea.md", "hugo.md"):
            (self.fiches / nom).unlink()
        f = json.loads(self.factory.read_text(encoding="utf-8"))
        f.update(agents_locaux_max=self.locaux, agents_cloud_max=0)
        self.factory.write_text(json.dumps(f), encoding="utf-8")
        for i in range(self.locaux):
            self.ecrire(f"agent-{i + 1}", f"Agent{i + 1}", "local")

    def ecrire(self, cle, prenom, lieu, session=None, retrait=False):
        lignes = [f"Clé : {cle}", f"Prénom : {prenom}", f"Lieu : {lieu}"]
        if session:
            lignes.append(f"Session : {session}")
        if retrait:
            lignes.append("Retrait : prévu")
        (self.fiches / f"{cle}.md").write_text("\n".join(lignes) + "\n", encoding="utf-8")

    def equipe(self):
        return fiches.lire_toutes(self.fiches)

    def places(self, locaux, cloud):
        return self.ok("parallelisme", entree={"agents_locaux_max": locaux, "agents_cloud_max": cloud})

    def compte(self, lieu):
        return sorted(x["cle"] for x in self.equipe() if x["lieu"] == lieu)

    def tache_active(self, agent):
        return self.ok("tache", entree={"titre": "Travail", "role": "dev", "agent": agent, "active": True})["id"]


class TestEquipePlaces(Base):
    def test_monter_les_places_cree_des_agents(self):
        r = self.places(4, 2)
        self.assertEqual((r["agents_locaux_max"], r["agents_cloud_max"]), (4, 2))
        equipe = self.equipe()
        self.assertEqual(len(self.compte("local")), 4)
        self.assertEqual(len(self.compte("cloud")), 2)
        self.assertTrue(all(fiches.est_polyvalente(x) for x in equipe))
        self.assertEqual(len({x["cle"] for x in equipe}), 6)
        prenoms = [x["prenom"] for x in equipe]
        self.assertEqual(len(set(prenoms)), 6)
        self.assertTrue(all(prenoms))
        self.assertTrue(all(x["session"] is None for x in equipe if x["lieu"] == "cloud"))
        self.assertEqual(len(r["crees"]), 4)
        # rejouer ne change rien
        self.places(4, 2)
        self.assertEqual(len(self.equipe()), 6)

    def test_baisser_retire_un_agent_libre(self):
        self.places(4, 2)
        r = self.places(2, 1)
        self.assertEqual((len(self.compte("local")), len(self.compte("cloud"))), (2, 1))
        self.assertEqual(len(r["retires"]), 3)
        self.assertEqual(r["retraits_prevus"], [])
        # un agent qui a déjà une session cloud est gardé de préférence
        self.places(2, 2)
        cloud = self.compte("cloud")
        self.ecrire(cloud[0], "Zed", "cloud", session="session_abc")
        self.places(2, 1)
        self.assertEqual(self.compte("cloud"), [cloud[0]])

    def test_agent_au_travail_retire_a_la_fin(self):
        self.places(4, 0)
        a1, a2, a3, a4 = self.compte("local")
        t2, t3 = self.tache_active(a2), self.tache_active(a3)
        self.tache_active(a1)
        r = self.places(1, 0)
        # le libre part tout de suite ; les agents au travail restent, marqués, sauf celui que la place garde
        self.assertEqual(r["retires"], [a4])
        self.assertEqual(sorted(r["retraits_prevus"]), [a2, a3])
        self.assertEqual(self.compte("local"), [a1, a2, a3])
        self.assertEqual(sorted(x["cle"] for x in self.equipe() if x["retrait_prevu"]), [a2, a3])
        # a2 finit sa tâche : retiré ; a3 travaille encore : il reste
        self.ok("tache", entree={"id": t2, "colonne": "fait", "active": False})
        self.ok("equipe")
        self.assertEqual(self.compte("local"), [a1, a3])
        self.ok("tache", entree={"id": t3, "colonne": "fait", "active": False})
        r = self.ok("equipe")
        self.assertEqual(r["retires"], [a3])
        self.assertEqual(self.compte("local"), [a1])
        self.assertFalse(any(x["retrait_prevu"] for x in self.equipe()))
        self.assertEqual(self.ok("equipe")["retires"], [])     # rejouée sans effet

    def test_agent_occupe_reste_tant_que_sa_tache_dure(self):
        self.places(3, 0)
        occupe = self.compte("local")[0]
        t = self.tache_active(occupe)
        self.places(1, 0)
        restants = {x["cle"]: x for x in self.equipe()}
        self.assertIn(occupe, restants)
        # des trois agents, un seul compte pour la place : l'occupé est gardé, les deux libres sont partis
        self.assertEqual(list(restants), [occupe])
        self.assertFalse(restants[occupe]["retrait_prevu"])
        self.ok("tache", entree={"id": t, "colonne": "fait", "active": False})
        self.assertEqual(len(self.equipe()), 1)

    def test_retrait_marque_puis_places_remontees(self):
        self.places(3, 0)
        a, b, c = self.compte("local")
        self.tache_active(a)
        self.tache_active(b)
        self.tache_active(c)
        self.places(1, 0)
        marques = sorted(x["cle"] for x in self.equipe() if x["retrait_prevu"])
        self.assertEqual(len(marques), 2)
        self.places(3, 0)     # on remonte : les retraits sont annulés, aucun agent neuf
        self.assertEqual(len(self.equipe()), 3)
        self.assertFalse(any(x["retrait_prevu"] for x in self.equipe()))

    def test_retrait_prevu_jamais_choisi(self):
        self.places(3, 0)
        a1, a2, a3 = self.compte("local")
        self.tache_active(a1)
        t2 = self.tache_active(a2)
        self.places(1, 0)                     # a3 libre : parti ; a2 au travail : marqué
        etat = {x["cle"]: x for x in self.ok("etat")["agents"]}
        self.assertEqual(sorted(etat), [a1, a2])
        self.assertTrue(etat[a2]["retrait_prevu"])
        self.assertFalse(etat[a1].get("retrait_prevu"))
        self.assertFalse(etat[a2]["libre"])
        # sa tâche s'arrête sans que `equipe` passe : il est libre en apparence, mais jamais choisi
        self.ok("tache", entree={"id": t2, "active": False})
        etat = {x["cle"]: x for x in self.ok("etat")["agents"]}
        self.assertFalse(etat[a2]["libre"])
        self.assertIsNone(self.ok("agent-libre", entree={"role": "dev", "lieu": "local"})["agent"])
        self.assertIsNone(self.ok("agent-libre", entree={"role": "dev"})["agent"])

    def test_recruter_refuse_si_polyvalent(self):
        code, objet = self.outil("recruter", entree={"mode": "manuel", "agents": [
            {"role": "dev", "modele": "Sonnet", "lieu": "local"}]})
        self.assertEqual(code, 1)
        self.assertIn("L'équipe suit les places de l'onglet Facturation.", objet["erreur"])
        self.assertEqual(len(self.equipe()), 2)

    def test_projet_ancien_inchange(self):
        (self.fiches / "dev-1.md").write_text("Clé : dev-1\nPrénom : Léa\nRôle : dev\nService : dev\nModèle : Sonnet\n"
                                              "Lieu : local\n\nTexte.\n\n## Leçons\n", encoding="utf-8")
        for x in self.equipe():
            if fiches.est_polyvalente(x):
                x["chemin"].unlink()
        r = self.places(5, 3)
        self.assertEqual(r["crees"], [])
        self.assertEqual([x["cle"] for x in self.equipe()], ["dev-1"])
        self.assertEqual(r["agents_locaux_max"], 5)

    def test_projet_mixte_pas_touche(self):
        (self.fiches / "dev-1.md").write_text("Clé : dev-1\nPrénom : Léa\nRôle : dev\nService : dev\nModèle : Sonnet\n"
                                              "Lieu : local\n\nTexte.\n\n## Leçons\n", encoding="utf-8")
        r = self.places(5, 3)
        self.assertEqual(r["crees"], [])
        self.assertEqual(len(self.equipe()), 3)

    def test_chef_ne_compte_pas(self):
        (self.fiches / "chef.md").write_text("Clé : chef\nPrénom : Marc\nRôle : chef\nService : metier\nModèle : Opus\n"
                                             "Lieu : local\n\nChef.\n\n## Leçons\n", encoding="utf-8")
        self.places(3, 0)
        self.assertEqual(len([x for x in self.equipe() if fiches.est_polyvalente(x)]), 3)
        self.assertIn("chef", [x["cle"] for x in self.equipe()])

    def test_fiche_retrait_relue(self):
        self.ecrire("agent-9", "Neuf", "local", retrait=True)
        f = fiches.trouver(self.equipe(), "agent-9")
        self.assertTrue(f["retrait_prevu"])
        fiches.ecrire_fiche(f)
        self.assertIn("Retrait : prévu", (self.fiches / "agent-9.md").read_text(encoding="utf-8"))
        self.assertFalse(fiches.trouver(self.equipe(), "agent-1")["retrait_prevu"])

    def test_releve_dit_projet_polyvalent(self):
        r = self.ok("releve")
        self.assertIs(r["recrutement"]["polyvalent"], True)
        self.assertEqual(r["recrutement"]["roles"], [])

    def test_releve_valide_avec_agents_polyvalents(self):
        from bureau import releve
        self.places(3, 0)
        a1, a2, a3 = self.compte("local")
        self.tache_active(a1)
        self.tache_active(a2)
        self.places(1, 0)          # a3 libre part, a2 au travail est marqué
        r = self.ok("releve")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        agents = {t["cle"]: t for t in r["titulaires"] if t["cle"] != "chef"}
        self.assertTrue(all(t["polyvalent"] and "service" not in t and "modele" not in t for t in agents.values()))
        self.assertEqual([k for k, t in agents.items() if t.get("retrait_prevu")], [a2])
