"""Une fonctionnalité qui demande un déploiement ou une installation n'est pas « terminée » avec son seul développement.
Cas réel (FM_Stats, f14, 2026-11-25) : le Chef disait « La série est terminée. » alors que rien n'était déployé sur le serveur
OVH ni installé. Le moteur ouvre la correction « Déployer et installer » et ne conclut qu'avec elle."""
import unittest

from moteur import deploiement, regles
from tests import test_moteur_regles as tmr


class Detection(unittest.TestCase):
    def test_une_demande_de_mise_en_ligne_est_reconnue(self):
        f = {"nom": "Serveur de données", "genre": "application-mobile-android", "discussion": [
            {"auteur": "utilisateur", "texte": "Je souhaite déporter le serveur de données sur le serveur que l'on a (ovh)."}]}
        self.assertEqual(deploiement.restants(f), [deploiement.LIBELLE_SERVEUR, deploiement.LIBELLE_INSTALLATION])

    def test_sans_mise_en_ligne_rien_ne_reste(self):
        f = {"nom": "Des écrans pour l'appli", "genre": "application-mobile-android",
             "discussion": [{"auteur": "utilisateur", "texte": "Un écran Profil et un écran Accueil."}]}
        self.assertEqual(deploiement.restants(f, ["Accueil", "Profil"]), [])

    def test_un_serveur_livre_propose_toujours_une_mise_en_place(self):
        f = {"nom": "Synchro des données", "genre": "application-mobile-android"}
        self.assertEqual(deploiement.restants(f, ["Serveur de synchro (API REST)"]),
                         [deploiement.LIBELLE_SERVEUR, deploiement.LIBELLE_INSTALLATION])
        self.assertEqual(deploiement.restants({"nom": "Pages web de lecture"})[0], deploiement.LIBELLE_SERVEUR)

    def test_la_demande_de_deploiement_rappelle_la_consigne_d_origine(self):
        f = {"nom": "Serveur distant", "discussion": [{"auteur": "utilisateur",
             "texte": "Crée une instance permanente sur le serveur OVH avec les outils de gestion et d'appel."}]}
        texte = deploiement.demande(f, [deploiement.LIBELLE_SERVEUR])
        self.assertIn("instance permanente sur le serveur OVH", texte)
        self.assertTrue(texte.startswith(deploiement.TITRE))

    def test_ce_que_dit_un_agent_ne_compte_pas(self):
        f = {"nom": "Profil", "discussion": [{"auteur": "chef", "texte": "On pourrait déployer plus tard."}]}
        self.assertEqual(deploiement.restants(f), [])

    def test_une_correction_et_le_deploiement_lui_meme_n_en_demandent_pas(self):
        self.assertEqual(deploiement.restants({"nom": "Corriger le serveur OVH", "nature": "correction"}), [])
        self.assertEqual(deploiement.restants({"nom": deploiement.TITRE + " : serveur OVH"}), [])


class FinDeSerie(tmr.Base):
    def serie_serveur(self):
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Déporter la base sur le serveur OVH"})
        for d in self.demande_en_attente():
            self.ok("demande-traitee", entree={"id": d["id"]})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie", "agent_cadrage": "metier-1",
                                          "methode": {"version": 1, "chemin": "pieces/f1/methode-v1.md"}})
        self.ok("file", entree={"fonctionnalite": "f1", "elements": tmr.DECOUPAGE["elements"][:1]})
        rapports = [{"statut": "fait", "message": {"texte": "Écran fait."}}, tmr.verdict("e1"), tmr.verdict("e1")]
        self.piloter(regles.avancer(self.projet, self.etat), rapports=rapports)
        self.piloter(regles.avancer(self.projet, self.etat))

    def textes(self):
        return [m["texte"] for m in self.fonc()["discussion"]]

    def deploiements(self):
        return [f for f in self.suivi()["fonctionnalites"] if str(f["nom"]).startswith(deploiement.TITRE)]

    def test_le_deploiement_retient_la_fin_et_ouvre_sa_correction(self):
        self.serie_serveur()
        self.assertEqual(self.fonc()["etape"], "serie")
        self.assertFalse(any(t.startswith("La série est terminée") for t in self.textes()))
        self.assertTrue(any("restent à faire" in t for t in self.textes()))
        demandes = [d for d in self.demande_en_attente() if str(d.get("texte", "")).startswith(deploiement.TITRE)]
        self.assertEqual(len(demandes), 1)
        self.assertEqual((demandes[0]["nature"], demandes[0]["concerne"]), ("correction", "f1"))

    def test_la_correction_n_est_ouverte_qu_une_fois(self):
        self.serie_serveur()
        for _ in range(3):
            regles.avancer(self.projet, self.etat)
        demandes = [d for d in self.demande_en_attente() if str(d.get("texte", "")).startswith(deploiement.TITRE)]
        self.assertEqual(len(demandes), 1)

    def test_la_fin_est_dite_quand_le_deploiement_est_fini(self):
        self.serie_serveur()
        (demande,) = [d for d in self.demande_en_attente() if str(d.get("texte", "")).startswith(deploiement.TITRE)]
        self.ok("demande-traitee", entree={"id": demande["id"]})
        (f2,) = self.deploiements()
        self.ok("fonctionnalite", entree={"id": f2["id"], "etape": "terminee"})
        self.piloter(regles.avancer(self.projet, self.etat))
        self.assertEqual(self.fonc()["etape"], "terminee")
        self.assertTrue(any(t.startswith("La série est terminée") for t in self.textes()))


if __name__ == "__main__":
    unittest.main()
