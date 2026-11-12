"""Un partenaire où l'utilisateur est inscrit (hors liaison directe) : l'agent prépare, l'utilisateur fait chez lui.

La demande « À faire chez <partenaire> » au bureau de direction, son retour (fait avec le résultat joint, ou impossible),
la file d'une génération à la fois, l'inscription réglée depuis le bureau. Appels d'IA et agents simulés.
"""
import base64
import os
import unittest
from unittest import mock

from orchestrateur import outil
from partenaires import etat as petat
from tests.test_moteur_regles import Base

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24

CHEZ = {"statut": "a_faire_chez_partenaire", "message": {"texte": "À vous chez Tripo."},
        "chez_partenaire": {"partenaire": "tripo", "quoi": "Le dragon et son œuf",
                            "prompt": "Un dragon vert couché sur son œuf, style cartoon.",
                            "reglages": ["Qualité : ultra", "Texture : oui"],
                            "mode_operatoire": ["Ouvrir le site de Tripo", "Coller le prompt", "Lancer la génération"],
                            "a_rapporter": {"description": "Le modèle 3D en .zip", "nom": "dragon.zip"},
                            "elements": ["dragon", "œuf"]}}


def avec(**champs):
    """Le même rapport, avec des champs de la demande changés."""
    return {**CHEZ, "chez_partenaire": {**CHEZ["chez_partenaire"], **champs}}


class ChezPartenaire(Base):
    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, {"HOME": str(self.dossier / "maison"), "USERPROFILE": str(self.dossier / "maison")})
        p.start()
        self.addCleanup(p.stop)
        (self.dossier / "maison").mkdir()

    def depart(self):
        _, actions = self.cadrer(texte="Un dragon en 3D")
        return actions

    def decisions(self):
        return [d for d in self.suivi()["decisions_projet"] if d["genre"] == "faire_chez_partenaire"]

    def pose(self, rapport=CHEZ):
        suite = self.piloter(self.depart(), rapports=[rapport])
        return suite

    # --- L'agent prépare : une décision au bureau de direction, l'agent ne continue pas.
    def test_la_demande_est_posee_au_bureau_de_direction(self):
        suite = self.pose()
        self.assertEqual([a[0] for a in suite], ["agent"])                # l'agent n'est pas relancé : il attend l'utilisateur
        d, = self.decisions()
        self.assertEqual((d["partenaire"], d["nom_partenaire"], d["agent"]), ("tripo", "Tripo", "metier-1"))
        self.assertEqual(d["texte"], "À faire chez Tripo : Le dragon et son œuf")
        self.assertEqual(d["prompt"], "Un dragon vert couché sur son œuf, style cartoon.")
        self.assertEqual(d["reglages"], ["Qualité : ultra", "Texture : oui"])
        self.assertEqual(len(d["mode_operatoire"]), 3)
        self.assertEqual(d["a_rapporter"], {"description": "Le modèle 3D en .zip", "nom": "dragon.zip"})
        self.assertEqual(d["elements"], ["dragon", "œuf"])
        self.assertTrue(d["site"].startswith("https://"))                  # le site vient du catalogue
        self.assertNotIn("apres", d)
        t = self.taches(etape="cadrage")[0]
        self.assertEqual(d["tache"], t["id"])
        self.assertFalse(t["active"])
        self.assertFalse(t.get("bloquee"))
        self.assertIn("Tripo", self.fonc()["discussion"][-1]["texte"])
        self.assertIn("bureau de direction", self.fonc()["discussion"][-1]["texte"])

    def test_le_site_ne_vient_jamais_de_l_agent(self):
        rapport = avec(site="https://pirate.example")
        self.pose(rapport)
        self.assertNotEqual(self.decisions()[0]["site"], "https://pirate.example")

    # --- Les règles du partenaire sont tenues : l'outil refuse, l'agent corrige une fois, puis la tâche est bloquée.
    def test_prompt_tripo_trop_long_est_refuse_puis_corrige(self):
        trop_long = avec(prompt="x" * 1001)
        suite = self.piloter(self.depart(), rapports=[trop_long, CHEZ])
        self.assertEqual([a[0] for a in suite], ["agent", "agent"])
        self.assertIn("1000 caractères", suite[1][3])                      # la raison est redonnée à l'agent
        self.assertEqual(len(self.decisions()), 1)                         # la seconde réponse, corrigée, est posée
        self.assertEqual(len(self.decisions()[0]["prompt"]), len(CHEZ["chez_partenaire"]["prompt"]))

    def test_deux_refus_bloquent_la_tache(self):
        trop_long = avec(prompt="x" * 1001)
        self.piloter(self.depart(), rapports=[trop_long, trop_long])
        self.assertEqual(self.decisions(), [])
        t = self.taches(etape="cadrage")[0]
        self.assertIn("1000 caractères", t["bloquee"])

    def test_tripo_demande_chaque_reglage(self):
        self.piloter(self.depart(), rapports=[avec(reglages=[]), avec(reglages=[])])
        self.assertEqual(self.decisions(), [])
        self.assertIn("reglages", self.taches(etape="cadrage")[0]["bloquee"])

    def test_partenaire_inconnu_refuse(self):
        self.piloter(self.depart(), rapports=[avec(partenaire="inexistant"), avec(partenaire="inexistant")])
        self.assertEqual(self.decisions(), [])
        self.assertIn("inexistant", self.taches(etape="cadrage")[0]["bloquee"])

    # --- Le retour : « fait » avec le résultat, ou « impossible ».
    def test_fait_avec_le_fichier_rapporte_l_agent_reprend(self):
        self.pose()
        d, = self.decisions()
        fichier = {"nom": "dragon.png", "type": "image/png", "donnees": base64.b64encode(PNG).decode()}
        demande, relance = self.traiter(type="faire_chez_partenaire", decision=d["id"], verdict="fait",
                                        texte="Qualité ultra, 2 essais.", fichiers=[fichier])
        self.assertEqual([a[0] for a in relance], ["agent"])
        self.assertEqual(relance[0][2], [d["tache"]])
        matiere = relance[0][3]
        self.assertIn("a fait ce que tu as préparé chez Tripo", matiere)
        self.assertIn("Qualité ultra, 2 essais.", matiere)
        self.assertIn("dragon.png", matiere)                                # le chemin rangé, compté depuis le projet
        self.assertIn("Le modèle 3D en .zip", matiere)                      # ce qui était attendu
        self.assertEqual(self.decisions(), [])
        self.assertEqual(self.statut(demande["id"])["statut"], "traitée")
        rangees = list((self.dossier / "pieces" / "partenaires" / d["id"]).glob("*dragon.png"))
        self.assertEqual(len(rangees), 1)
        self.assertEqual(rangees[0].read_bytes(), PNG)
        self.assertTrue(self.taches(id=d["tache"])[0]["active"])

    def test_fait_sans_fichier_l_agent_reprend_sur_la_parole(self):
        self.pose()
        d, = self.decisions()
        _, relance = self.traiter(type="faire_chez_partenaire", decision=d["id"], verdict="fait")
        self.assertEqual([a[0] for a in relance], ["agent"])
        self.assertIn("aucun fichier", relance[0][3])
        self.assertEqual(self.decisions(), [])

    def test_impossible_l_agent_reprend_sans(self):
        self.pose()
        d, = self.decisions()
        _, relance = self.traiter(type="faire_chez_partenaire", decision=d["id"], verdict="impossible",
                                  texte="Plus de crédits ce mois-ci.")
        self.assertEqual([a[0] for a in relance], ["agent"])
        self.assertIn("n'a pas pu le faire chez Tripo", relance[0][3])
        self.assertIn("Plus de crédits", relance[0][3])
        self.assertEqual(self.decisions(), [])
        self.assertFalse(self.taches(id=d["tache"])[0].get("bloquee"))

    def test_decision_disparue_refusee(self):
        code, objet = outil.executer(self.factory, ["actions"], {"type": "faire_chez_partenaire", "decision": "d99",
                                                                  "verdict": "fait"})
        self.assertEqual(code, 1, objet)                                    # l'outil refuse déjà une décision inconnue
        self.assertIn("inconnue", str(objet))

    # --- Une génération à la fois chez un partenaire.
    def test_une_generation_a_la_fois(self):
        self.pose()
        premiere, = self.decisions()
        suivante = self.ok("decision", entree={
            "action": "poser", "portee": "projet", "genre": "faire_chez_partenaire", "texte": "x", "agent": "metier-1",
            "tache": premiere["tache"], **CHEZ["chez_partenaire"], "quoi": "Un loup", "prompt": "Un loup gris."})
        d2 = next(d for d in self.decisions() if d["id"] == suivante["id"])
        self.assertEqual(d2["apres"], premiere["id"])
        redite = self.ok("decision", entree={
            "action": "poser", "portee": "projet", "genre": "faire_chez_partenaire", "texte": "x", "agent": "metier-1",
            "tache": premiere["tache"], **CHEZ["chez_partenaire"], "quoi": "Un loup", "prompt": "Un loup gris."})
        self.assertEqual(redite["id"], suivante["id"])                      # la même demande reposée n'en crée pas deux
        self.assertEqual(len(self.decisions()), 2)

    # --- Le cadrage décide d'utiliser (ou non) un partenaire.
    CAHIER = {"statut": "fait", "message": {"texte": "Voici le cahier."}, "nom": "Dragon",
              "cahier": {"maquette": [{"chemin": "pieces/f1/maquette.png", "legende": "L'écran"}], "etapes": ["Modéliser"]}}

    def cahier(self, partenaires):
        return {**self.CAHIER, "cahier": {**self.CAHIER["cahier"], "partenaires": partenaires}}

    def inscrit(self):
        self.ok("partenaires", entree={"action": "inscrire", "partenaire": "tripo", "inscrit": True, "note": "offre Pro"})

    def test_le_cadrage_propose_les_partenaires_disponibles(self):
        self.inscrit()
        matiere = self.depart()[0][3]
        self.assertIn("## Partenaires de l'utilisateur", matiere)
        self.assertIn("- tripo (Tripo, ", matiere)
        self.assertIn("inscrit (l'utilisateur fait la génération sur son site", matiere)
        self.assertIn("Ne pas utiliser de partenaire", matiere)
        self.assertIn('"partenaires": [{"id": "<id>", "mode": "direct" | "inscrit" | "aucun"}]', matiere)

    def test_sans_partenaire_le_cadrage_n_en_parle_pas(self):
        self.assertNotIn("Partenaires de l'utilisateur", self.depart()[0][3])

    def test_la_reponse_du_cadrage_va_dans_le_cahier(self):
        self.inscrit()
        decide = [{"id": "tripo", "mode": "inscrit"}]
        self.piloter(self.depart(), rapports=[self.cahier(decide)])
        self.assertEqual(self.fonc()["cahier"]["partenaires"], decide)
        self.assertEqual(self.fonc()["etape"], "cahier")

    def test_cahier_sans_partenaire_inchange(self):
        self.piloter(self.depart(), rapports=[self.CAHIER])
        self.assertNotIn("partenaires", self.fonc()["cahier"])

    def test_cahier_dont_le_partenaire_ne_convient_pas_est_refuse_puis_corrige(self):
        self.inscrit()                                                          # inscrit, pas connecté : « direct » est faux
        suite = self.piloter(self.depart(), rapports=[self.cahier([{"id": "tripo", "mode": "direct"}]),
                                                      self.cahier([{"id": "tripo", "mode": "inscrit"}])])
        self.assertEqual([a[0] for a in suite], ["agent", "agent"])
        self.assertIn("n'est pas connecté", suite[1][3])
        self.assertEqual(self.fonc()["cahier"]["partenaires"], [{"id": "tripo", "mode": "inscrit"}])
        self.assertEqual([m["texte"] for m in self.fonc()["discussion"]].count("Voici le cahier."), 1)   # pas doublé

    def test_cahier_valide_garde_les_partenaires(self):
        self.inscrit()
        decide = [{"id": "tripo", "mode": "inscrit"}]
        self.piloter(self.depart(), rapports=[self.cahier(decide)])
        self.traiter(type="cahier", fonctionnalite="f1", verdict="valider")
        self.assertEqual(self.fonc()["cahier"]["partenaires"], decide)
        self.assertIn("valide_le", self.fonc()["cahier"])

    # --- L'inscription, réglée depuis le bureau.
    def test_demande_d_inscription_du_bureau(self):
        d, relance = self.traiter(type="partenaire_inscrit", partenaire="tripo", inscrit=True, note="compte gratuit")
        self.assertEqual(relance, [])
        self.assertEqual(self.statut(d["id"])["reponse"], "C'est noté : vous êtes inscrit.")
        self.assertEqual(petat.Etat().lire()["inscriptions"]["tripo"]["note"], "compte gratuit")
        d, _ = self.traiter(type="partenaire_inscrit", partenaire="tripo", inscrit=False)
        self.assertEqual(self.statut(d["id"])["reponse"], "C'est noté : vous n'êtes plus inscrit.")
        self.assertEqual(petat.Etat().lire()["inscriptions"], {})

    def test_inscription_refusee_par_l_outil_est_dite(self):
        d, relance = self.traiter(type="partenaire_inscrit", partenaire="tripo", inscrit=True,
                                  note="mot de passe : hunter2")
        self.assertIn("n'a pas été notée", self.statut(d["id"])["reponse"])
        self.assertNotIn("hunter2", self.statut(d["id"])["reponse"])
        self.assertEqual(petat.Etat().lire()["inscriptions"], {})


if __name__ == "__main__":
    unittest.main()
