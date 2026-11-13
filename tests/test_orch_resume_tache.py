"""Le résumé d'une tâche au relevé : ce qu'elle doit produire, pour le Directeur (sans appel d'IA)."""
import unittest

from orchestrateur import outil

FONCS = [{"id": "f1", "elements": {"socle": {"nom": "Socle Godot 4", "objectif": "Un projet Godot 4 en paysage.\n"}}}]


def journal(*textes):
    return [{"t": "2026-11-13T10:00:00+01:00", "texte": x} for x in textes]


class ResumeDeTache(unittest.TestCase):
    def test_objectif_de_l_element(self):
        t = {"fonctionnalite": "f1", "element": "socle", "journal": journal("Terminé.")}
        self.assertEqual(outil.resume_de_tache(t, FONCS), "Un projet Godot 4 en paysage.")

    def test_derniere_consigne_du_directeur_ajoutee(self):
        t = {"fonctionnalite": "f1", "element": "socle",
             "journal": journal("Remarque du Directeur : trop lent.", "Remarque du Directeur : écran trop chargé.")}
        self.assertEqual(outil.resume_de_tache(t, FONCS),
                         "Un projet Godot 4 en paysage. Dernière consigne : Remarque du Directeur : écran trop chargé.")

    def test_une_relance_n_est_pas_une_consigne(self):
        t = {"fonctionnalite": "f1", "element": "socle",
             "journal": journal("Remarque du Directeur : trop lent.",
                                "Reprise sur votre retour : Relance demandée par le Directeur (même consigne).")}
        self.assertEqual(outil.resume_de_tache(t, FONCS),
                         "Un projet Godot 4 en paysage. Dernière consigne : Remarque du Directeur : trop lent.")

    def test_tache_a_part_prend_la_consigne_qui_l_a_ouverte(self):
        t = {"fonctionnalite": None, "element": None, "journal": journal("Retour de l'utilisateur : le menu déborde.")}
        self.assertEqual(outil.resume_de_tache(t, FONCS), "Retour de l'utilisateur : le menu déborde.")

    def test_rien_a_dire(self):
        self.assertIsNone(outil.resume_de_tache({"fonctionnalite": None, "journal": []}, FONCS))
        self.assertIsNone(outil.resume_de_tache({"fonctionnalite": None, "journal": journal("Terminé.")}, FONCS))

    def test_tronque_au_plafond(self):
        t = {"fonctionnalite": None, "journal": journal("x" * 900)}
        r = outil.resume_de_tache(t, FONCS)
        self.assertEqual(len(r), outil.MAX_RESUME_TACHE)
        self.assertTrue(r.endswith("…"))


if __name__ == "__main__":
    unittest.main()
