"""Une réponse de l'utilisateur à l'agent du prototype ne se perd jamais : après un redémarrage du moteur (l'élément du
prototype n'est plus en mémoire, la tâche du prototype est faite), la réponse relance l'agent ; si elle est perdue
quand même, le moteur la rejoue une fois, puis le dit. Cas réel : « Cartes évolutives » (ZooRunner), demande r15."""
import json
import unittest

from moteur import detache, regles
from tests.test_moteur_regles import Base

REPONSE = "Les coffres me conviennent. De plus, on ajoutera les légendes, des monstres plus forts qui lâchent des coffres."


class RetourPerdu(Base):
    def prototype_fini(self):
        """Le prototype de « Accueil » est fait, l'agent a posé ses questions, l'utilisateur a répondu ; le moteur a
        redémarré (rien en mémoire)."""
        self.fonctionnalite("prototype")
        self.ok("file", entree={"fonctionnalite": "f1", "elements": [{"id": "e1", "nom": "Accueil", "groupe": "écrans"}]})
        self.ok("file-prendre", entree={"fonctionnalite": "f1", "element": "e1"})
        t = self.ok("tache", entree={"titre": "Prototype : Accueil", "fonctionnalite": "f1", "role": "dev",
                                     "etape": "prototype", "element": "e1", "agent": "dev-1", "colonne": "fait",
                                     "active": False})["id"]
        self.ok("message", entree={"fonctionnalite": "f1", "auteur": "dev-1", "texte": "Les coffres vous conviennent ?",
                                   "attend": True})
        return t

    def repondre(self):
        i = self.ok("actions", entree={"type": "message", "fonctionnalite": "f1", "texte": REPONSE})["id"]
        return next(d for d in self.demande_en_attente() if d["id"] == i)

    def ouvertes(self):
        return [t for t in self.taches(etape="prototype") if t["colonne"] != "fait"]

    def test_la_reponse_relance_l_agent_apres_un_redemarrage(self):
        self.prototype_fini()
        self.assertNotIn("f1", self.etat["prototype"])
        d = self.repondre()
        actions = regles.traiter_demande(self.projet, d, self.etat)
        suite = self.piloter(actions, juges={"traduire_retour": {"validation": False, "consigne": "Ajouter les légendes."}},
                             rapports=[{"statut": "fait", "message": {"texte": "Voici.", "attend": True}}])
        self.assertIn("agent", [a[0] for a in suite])
        nouvelles = [t for t in self.taches(etape="prototype") if t["element"] == "e1"]
        self.assertEqual(len(nouvelles), 2)
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertEqual(self.statut(d["id"])["reponse"], "J'ai transmis votre retour à l'agent du prototype.")

    def test_l_element_du_prototype_vient_aussi_des_taches_faites(self):
        self.prototype_fini()
        f = self.fonc()
        self.assertEqual(regles._element_du_prototype(self.projet, self.etat, f), {"id": "e1", "nom": "Accueil"})

    def test_un_retour_qui_echoue_ne_dit_pas_qu_il_est_transmis(self):
        self.fonctionnalite("prototype")        # aucun élément connu : la relance est refusée
        d = self.repondre()
        actions = regles.traiter_demande(self.projet, d, self.etat)
        (_, type_, _, suite), = actions
        with self.assertRaises(regles.Refus):
            regles.appliquer_jugement(self.projet, type_, regles_decision(
                {"validation": False, "consigne": "Ajouter."}), suite, self.etat)
        self.assertEqual(self.statut(d["id"])["statut"], "en attente")      # le moteur la termine avec la raison

    def test_garde_fou_la_reponse_perdue_est_rejouee_une_fois(self):
        self.prototype_fini()
        d = self.repondre()
        self.ok("demande-traitee", entree={"id": d["id"], "reponse": "J'ai transmis votre retour à l'agent du prototype."})
        self.assertEqual(self.ouvertes(), [])
        actions = regles.avancer(self.projet, self.etat)
        self.assertEqual([a[0] for a in actions], ["agent"])
        t, = self.ouvertes()
        self.assertEqual(t["element"], "e1")
        journal = self.ok("detail", entree={"tache": t["id"]})["journal"]
        self.assertIn(REPONSE, journal[0]["texte"])
        self.assertIn("Reprise du message m", journal[0]["texte"])
        # au passage suivant, la tâche est ouverte : rien de plus
        self.assertEqual(regles.avancer(self.projet, self.etat), [])
        self.assertEqual(len(self.ouvertes()), 1)

    def test_garde_fou_apres_un_redemarrage_la_reponse_n_est_pas_rejouee_deux_fois(self):
        self.prototype_fini()
        d = self.repondre()
        self.ok("demande-traitee", entree={"id": d["id"], "reponse": "ok"})
        regles.avancer(self.projet, self.etat)
        t, = self.ouvertes()
        self.ok("tache", entree={"id": t["id"], "colonne": "fait", "active": False})
        # le moteur redémarre ; l'agent n'a rien écrit dans la discussion : c'est dit, pas rejoué
        self.etat.clear()
        self.etat.update(regles.nouvel_etat())
        self.assertEqual(regles.avancer(self.projet, self.etat), [])
        self.assertEqual(self.ouvertes(), [])
        dernier = self.fonc()["discussion"][-1]
        self.assertNotEqual(dernier["auteur"], "utilisateur")
        self.assertIn("n'a pas répondu", dernier["texte"])
        self.assertEqual(regles.avancer(self.projet, self.etat), [])      # une seule fois
        self.assertEqual(len(self.taches(etape="prototype")), 2)

    def test_garde_fou_rien_pendant_qu_un_agent_travaille(self):
        t = self.prototype_fini()
        d = self.repondre()
        self.ok("demande-traitee", entree={"id": d["id"], "reponse": "ok"})
        self.ok("tache", entree={"id": t, "colonne": "dev", "active": True})
        self.assertEqual(regles.avancer(self.projet, self.etat), [])
        self.assertEqual(len(self.taches(etape="prototype")), 1)

    def test_garde_fou_rien_tant_que_la_demande_est_en_cours(self):
        self.prototype_fini()
        self.repondre()          # la demande attend son jugement : le moteur s'en occupe
        self.assertEqual(regles.avancer(self.projet, self.etat), [])
        self.assertEqual(len(self.taches(etape="prototype")), 1)

    def test_garde_fou_rien_pendant_qu_une_reponse_de_l_agent_est_en_route(self):
        t = self.prototype_fini()
        d = self.repondre()
        self.ok("demande-traitee", entree={"id": d["id"], "reponse": "ok"})
        dossier = detache.dossier(self.dossier)
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / f"{t}.reponse.json").write_text(json.dumps({"genre": "reponse", "tache": t, "fonctionnalite": "f1"}),
                                                   encoding="utf-8")
        self.assertEqual(regles.avancer(self.projet, self.etat), [])
        self.assertEqual(len(self.taches(etape="prototype")), 1)

    def test_garde_fou_sans_element_connu_le_dit_au_lieu_de_se_taire(self):
        self.fonctionnalite("prototype")
        d = self.repondre()
        self.ok("demande-traitee", entree={"id": d["id"], "reponse": "ok"})
        self.assertEqual(regles.avancer(self.projet, self.etat), [])
        dernier = self.fonc()["discussion"][-1]
        self.assertNotEqual(dernier["auteur"], "utilisateur")
        self.assertIn("quel élément", dernier["texte"])


def regles_decision(objet):
    from tests.test_moteur_regles import decision
    return decision(objet)


if __name__ == "__main__":
    unittest.main()
