"""Le rapport structuré des agents : lecture du bloc JSON, commandes à passer à `lancer`. Aucun appel réel."""
import json
import unittest

from moteur import rapport
from orchestrateur import depart
from tests.orch_aide import AvecProjet

FAIT = {"statut": "fait",
        "message": {"texte": "Voilà l'écran.", "images": ["pieces/f1/a.png"], "attend": False},
        "fichiers": [{"chemin": "pieces/f1/a.png", "titre": "Écran", "element": "e1", "livrable": True}],
        "lecons": [{"texte": "Nommer comme la maquette.", "roles": ["dev"], "etage_propose": "projet"}],
        "controles": [{"texte": "Le titre fait 24 px.", "origine": "relecture"}],
        "retours_factory": [], "verdicts": []}


def reponse(objet, avant="Fini.\n", apres=""):
    return f"{avant}```json\n{json.dumps(objet, ensure_ascii=False)}\n```\n{apres}"


class Lire(unittest.TestCase):
    def test_lit_le_dernier_bloc_json(self):
        premier = {"statut": "echec"}
        texte = reponse(premier) + "\nPuis ma vraie réponse :\n" + reponse(FAIT)
        r = rapport.lire(texte)
        self.assertEqual(r["statut"], "fait")
        self.assertEqual(r["fichiers"][0]["chemin"], "pieces/f1/a.png")

    def test_rapport_sans_bloc_illisible(self):
        for texte in ("Tout est fait.", "```json\n{pas du json\n```", reponse({"statut": "autre"}), ""):
            with self.subTest(texte=texte), self.assertRaises(rapport.RapportIllisible):
                rapport.lire(texte)

    def test_valeurs_vides_completees(self):
        r = rapport.lire(reponse({"statut": "fait"}))
        self.assertEqual((r["fichiers"], r["lecons"], r["controles"], r["verdicts"], r["retours_factory"]),
                         ([], [], [], [], []))

    def test_lecon_de_genre_demande_le_texte_general(self):
        mauvais = dict(FAIT, lecons=[{"texte": "Un conseil.", "etage_propose": "genre"}])
        with self.assertRaises(rapport.RapportIllisible):
            rapport.lire(reponse(mauvais))

    def test_accord_requis_demande_son_accord(self):
        with self.assertRaises(rapport.RapportIllisible):
            rapport.lire(reponse({"statut": "accord_requis"}))


class Commandes(unittest.TestCase):
    def appel(self, r):
        return rapport.commandes(rapport.lire(reponse(r)), fonctionnalite="f1", tache="t3", agent="dev-1",
                                 etape="dev")

    def test_commandes_dans_l_ordre(self):
        cmds = self.appel(FAIT)
        self.assertEqual([c for c, _ in cmds], ["message", "document", "controle", "lecon"])
        message, document, controle, lecon = (e for _, e in cmds)
        self.assertEqual(message["auteur"], "dev-1")
        self.assertEqual(message["fonctionnalite"], "f1")
        self.assertEqual(message["images"], ["pieces/f1/a.png"])
        self.assertIs(message["attend"], False)
        self.assertEqual((document["agent"], document["tache"], document["etape"], document["element"],
                          document["livrable"]), ("dev-1", "t3", "dev", "e1", True))
        self.assertEqual(controle, {"texte": "Le titre fait 24 px.", "origine": "relecture"})
        self.assertEqual((lecon["action"], lecon["agent"], lecon["tache"], lecon["roles"]),
                         ("noter", "dev-1", "t3", ["dev"]))

    def test_accord_requis_ne_rend_aucune_commande_de_production(self):
        r = dict(FAIT, statut="accord_requis", accord={"quoi": "Générer 5 images", "partenaire": "x", "cout": "2 $"})
        cmds = self.appel(r)
        self.assertEqual([c for c, _ in cmds], ["message"])

    def test_sans_fonctionnalite_ni_message_ni_document(self):
        cmds = rapport.commandes(rapport.lire(reponse(FAIT)), fonctionnalite=None, tache="t3", agent="dev-1",
                                 etape="dev")
        self.assertEqual([c for c, _ in cmds], ["controle", "lecon"])


class Consigne(AvecProjet):
    def test_depart_demande_le_bloc_json(self):
        t = self.ok("tache", entree={"titre": "Écran", "role": "dev", "colonne": "dev"})["id"]
        m = self.ok("lancer", "depart", entree={"agent": "dev-1", "tache": t})["message"]
        self.assertIn("bloc ```json", m)
        self.assertIn("accord_requis", m)
        self.assertIn("```json", depart.FIN_D_ETAPE)

    def test_usage_accepte_orchestrateur(self):
        code, _ = self.outil("usage", entree={"modele": "claude-haiku-5-5", "agent": "orchestrateur",
                                              "etape": "orchestration", "entree": 10, "sortie": 5})
        self.assertEqual(code, 0)
        code, _ = self.outil("usage", entree={"modele": "x", "agent": "inconnu", "entree": 1, "sortie": 1})
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
