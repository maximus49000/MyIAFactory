"""Un agent retiré de l'équipe est gardé, inactif, pour l'historique de ses tâches (`Retrait : fait`) ; sans aucune tâche
au suivi, sa fiche est supprimée comme avant. Ajouter une place crée un nouvel agent : on ne réactive jamais un retiré."""
import json
from datetime import datetime, timezone

from bureau import etat, releve
from orchestrateur import fiches
from orchestrateur import suivi as su
from tests.orch_aide import AvecProjet
from tests.test_orch_equipe_places import Base
from tests.test_orch_reprise_polyvalents import Base as BaseReprise


class TestFiche(Base):
    def test_retrait_fait_lu_et_ecrit(self):
        (self.fiches / "agent-9.md").write_text("Clé : agent-9\nPrénom : Zed\nLieu : local\nRetrait : fait\n", encoding="utf-8")
        f = fiches.trouver(self.equipe(), "agent-9")
        self.assertTrue(f["retire"])
        self.assertFalse(f["retrait_prevu"])
        fiches.ecrire_fiche(f)
        self.assertIn("Retrait : fait", (self.fiches / "agent-9.md").read_text(encoding="utf-8"))
        self.assertTrue(fiches.trouver(self.equipe(), "agent-9")["retire"])

    def test_ancien_format_inchange(self):
        f = fiches.trouver(self.equipe(), "agent-1")
        self.assertFalse(f["retire"])
        self.assertNotIn("Retrait", (self.fiches / "agent-1.md").read_text(encoding="utf-8"))
        self.ecrire("agent-8", "Huit", "local", retrait=True)
        f = fiches.trouver(self.equipe(), "agent-8")
        self.assertTrue(f["retrait_prevu"])
        self.assertFalse(f["retire"])

    def test_valeur_inconnue_refusee(self):
        (self.fiches / "agent-7.md").write_text("Clé : agent-7\nLieu : local\nRetrait : peut-être\n", encoding="utf-8")
        with self.assertRaises(fiches.FicheInvalide):
            fiches.lire_toutes(self.fiches)


class TestEquipe(Base):
    def actifs(self, lieu="local"):
        return sorted(x["cle"] for x in self.equipe() if x["lieu"] == lieu and not x["retire"])

    def retires(self):
        return sorted(x["cle"] for x in self.equipe() if x["retire"])

    def fait(self, tache):
        self.ok("tache", entree={"id": tache, "colonne": "fait", "active": False})

    def test_retire_avec_tache_est_garde(self):
        self.places(3, 0)
        a1, a2, a3 = self.actifs()
        self.fait(self.tache_active(a3))     # a3 et a1 ont réalisé une tâche, a2 aucune
        self.fait(self.tache_active(a1))
        r = self.places(1, 0)
        self.assertEqual(sorted(r["retires"]), [a2, a3])
        self.assertEqual(self.retires(), [a3])                 # a3 gardé inactif
        self.assertFalse((self.fiches / f"{a2}.md").exists())  # a2 n'a jamais travaillé : supprimé
        self.assertIn("Retrait : fait", (self.fiches / f"{a3}.md").read_text(encoding="utf-8"))
        self.assertEqual(self.actifs(), [a1])
        self.assertEqual(self.places(1, 0)["retires"], [])     # rejoué sans effet
        self.assertEqual(self.retires(), [a3])

    def test_retire_jamais_compte_ni_choisi(self):
        self.places(2, 0)
        a1, a2 = self.actifs()
        self.fait(self.tache_active(a2))
        self.fait(self.tache_active(a1))
        self.places(1, 0)
        self.assertEqual(self.retires(), [a2])
        self.assertEqual(self.places(1, 0)["crees"], [])       # une place, un agent actif : rien à créer
        etat_ = {x["cle"]: x for x in self.ok("etat")["agents"]}
        self.assertEqual(sorted(etat_), [a1])
        self.assertEqual(self.ok("agent-libre", entree={"role": "dev", "lieu": "local"})["agent"], a1)
        self.tache_active(a1)
        self.assertIsNone(self.ok("agent-libre", entree={"role": "dev"})["agent"])    # jamais le retiré

    def test_monter_cree_un_nouvel_agent(self):
        self.places(2, 0)
        a1, a2 = self.actifs()
        self.fait(self.tache_active(a2))
        self.fait(self.tache_active(a1))
        self.places(1, 0)
        prenom = fiches.trouver(self.equipe(), a2)["prenom"]
        r = self.places(2, 0)
        self.assertEqual(len(r["crees"]), 1)
        neuf = r["crees"][0]
        self.assertNotIn(neuf, (a1, a2))
        self.assertNotEqual(fiches.trouver(self.equipe(), neuf)["prenom"], prenom)
        self.assertEqual(self.retires(), [a2])                 # a2 reste retiré
        self.assertEqual(self.actifs(), sorted([a1, neuf]))

    def test_on_retire_d_abord_ceux_sans_tache(self):
        self.places(3, 0)
        a1, a2, a3 = self.actifs()
        self.fait(self.tache_active(a3))       # a3 a un historique ; a1 et a2 aucun (a3 est le dernier de la liste
        self.fait(self.tache_active(a1))       # et a1 le premier : sans la règle, a3 puis a2 partiraient)
        r = self.places(1, 0)
        self.assertEqual(sorted(r["retires"]), [a2, a3])
        self.assertEqual(self.actifs(), [a1])
        self.assertEqual(self.retires(), [a3])          # a2 supprimé, a3 gardé
        self.places(3, 0)
        a4, a5 = [c for c in self.actifs() if c != a1]
        self.fait(self.tache_active(a5))
        self.places(2, 0)                               # un seul à retirer : celui sans tâche (a4), pas a5
        self.assertNotIn(a4, [x["cle"] for x in self.equipe()])
        self.assertIn(a5, self.actifs())

    def test_retrait_prevu_devient_fait(self):
        self.places(2, 0)
        a1, a2 = self.actifs()
        t2 = self.tache_active(a2)
        self.tache_active(a1)
        self.places(1, 0)                                      # a2 au travail : retrait prévu
        self.assertTrue(fiches.trouver(self.equipe(), a2)["retrait_prevu"])
        self.fait(t2)
        self.ok("equipe")
        f = fiches.trouver(self.equipe(), a2)
        self.assertTrue(f["retire"])
        self.assertFalse(f["retrait_prevu"])

    def test_releve_et_etat(self):
        self.places(2, 0)
        a1, a2 = self.actifs()
        self.fait(self.tache_active(a2))
        self.fait(self.tache_active(a1))
        self.places(1, 0)
        r = self.ok("releve")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        titulaires = {t["cle"]: t for t in r["titulaires"]}
        self.assertIs(titulaires[a2]["retire"], True)
        self.assertNotIn("retire", titulaires[a1])
        self.assertEqual(next(t for t in r["taches"] if t["titulaire"] == a2)["titulaire"], a2)
        e = etat.construire(releve.normaliser(json.loads(json.dumps(r))), _Equipe(), datetime.now(timezone.utc), 30)
        self.assertNotIn(a2, [a["id"] for a in e["agents"]])
        self.assertEqual([a["id"] for a in e["anciens_agents"]], [a2])
        self.assertEqual(len([t for t in e["taches"] if t["agent"] == a2]), 1)      # sa tâche garde son agent
        self.assertEqual(set(e["anciens_agents"][0]), {"id", "prenom", "couleur", "lieu"})


class _Equipe:
    def agent(self, cle, chef=False, prenom=None):
        return {"prenom": prenom or cle, "couleur": "#123456"}


class TestReprise(BaseReprise):
    def avant(self):
        return self.fiches / "avant-polyvalents"

    def test_agent_en_trop_avec_tache_garde_retire(self):
        t = self.tache_active("graphiste-1")
        self.ok("tache", entree={"id": t, "colonne": "fait", "active": False})
        self.tache_active("designer-1")
        self.tache_active("dev-1")                    # trois locaux, deux places : graphiste-1 en trop, libre
        r = self.reprendre()
        equipe = {x["cle"]: x for x in self.equipe()}
        g = equipe["graphiste-1"]
        self.assertTrue(g["retire"] and fiches.est_polyvalente(g))
        self.assertEqual((g["prenom"], g["lieu"]), ("Graphiste-1", "local"))
        self.assertIn("graphiste-1", r["agents_retires"])
        # sans tâche : supprimé comme avant
        self.assertNotIn("equilibreur-1", equipe)
        self.assertNotIn("metier-1", equipe)
        self.assertEqual([k for k, x in equipe.items() if x["retire"]], ["graphiste-1"])

    def test_on_garde_d_abord_ceux_qui_ont_des_taches(self):
        self.tache_active("designer-1")
        t = self.tache_active("equilibreur-1")
        self.ok("tache", entree={"id": t, "colonne": "fait", "active": False})
        self.reprendre()           # deux places locales : designer-1 (au travail) et equilibreur-1 (historique)
        equipe = {x["cle"]: x for x in self.equipe()}
        self.assertEqual(sorted(k for k, x in equipe.items() if x["lieu"] == "local" and not x["retire"]),
                         ["designer-1", "equilibreur-1"])
        self.assertNotIn("dev-1", equipe)

    def test_rejouer_ne_change_rien(self):
        self.tache_active("graphiste-1")
        self.reprendre()
        avant = self.instantane()
        self.reprendre()
        self.assertEqual(self.instantane(), avant)

    def test_rejouer_restaure_les_retires_avec_taches(self):
        # un projet déjà repris : les agents en trop ont été supprimés par l'ancienne reprise
        for cle in ("designer-2", "release-1"):
            t = self.tache_active(cle)
            self.ok("tache", entree={"id": t, "colonne": "fait", "active": False})
        self.reprendre()
        for cle in ("designer-2", "release-1"):
            (self.fiches / f"{cle}.md").unlink(missing_ok=True)       # l'ancien comportement
        for cle in ("designer-3", "equilibreur-1"):
            (self.fiches / f"{cle}.md").unlink(missing_ok=True)       # sans tâche : ne revient pas
        self.assertTrue((self.avant() / "designer-2.md").is_file())
        r = self.reprendre()
        equipe = {x["cle"]: x for x in self.equipe()}
        for cle in ("designer-2", "release-1"):
            self.assertTrue(equipe[cle]["retire"], cle)
            self.assertTrue(fiches.est_polyvalente(equipe[cle]))
        self.assertEqual(equipe["designer-2"]["prenom"], "Designer-2")
        self.assertEqual(equipe["designer-2"]["lieu"], "cloud")
        self.assertEqual(equipe["designer-2"]["session"], None)
        self.assertNotIn("equilibreur-1", equipe)
        self.assertNotIn("designer-3", equipe)
        self.assertEqual(sorted(r["agents_retires"]), ["designer-2", "release-1"])
        avant = self.instantane()
        self.assertEqual(self.reprendre()["agents_retires"], [])      # puis plus rien à faire
        self.assertEqual(self.instantane(), avant)

    def test_aucune_tache_touchee(self):
        t = self.tache_active("graphiste-1")
        self.ok("tache", entree={"id": t, "colonne": "fait", "active": False})
        avant = su.Suivi(self.suivi_chemin()).lire()["taches"]
        self.reprendre()
        apres = su.Suivi(self.suivi_chemin()).lire()["taches"]
        self.assertEqual(avant, apres)
