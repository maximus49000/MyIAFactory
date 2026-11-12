"""Un partenaire où l'utilisateur est inscrit : le départ de l'agent, le cadrage qui décide d'utiliser (ou non) un partenaire,
les partenaires disponibles. Aucun appel à un vrai partenaire."""
import unittest

from bureau import releve
from orchestrateur import outil
from partenaires import etat as petat
from tests.test_part_outil import AvecPartenaires


class TestDepartInscrit(AvecPartenaires):
    def test_depart_d_un_partenaire_inscrit_ne_l_appelle_pas(self):
        self.p({"action": "inscrire", "partenaire": "tripo", "inscrit": True, "note": "compte gratuit"})
        self.p({"action": "confirmer", "ids": ["elevenlabs"]})
        t = self.tache(role="dev", partenaires=["elevenlabs", "tripo"])
        m = self.run_outil("depart", entree={"agent": "dev-1", "tache": t})["message"]
        regles, inscrit = m.split("## Partenaires où l'utilisateur est inscrit")
        self.assertIn("### ElevenLabs", regles)                              # connecté : ses règles, appelé directement
        self.assertNotIn("Tripo", regles.split("## Règles de tes partenaires")[1])
        inscrit = inscrit.split("## Sobriété")[0]
        self.assertIn("### Tripo (https://", inscrit)
        self.assertIn("compte : compte gratuit", inscrit)
        self.assertIn("1000 caractères au plus", inscrit)
        self.assertIn("chacun des réglages", inscrit)
        self.assertIn(petat.REGLE_TRIPO, inscrit)                           # ses règles suivent, mot pour mot
        self.assertIn("n'appelle ni leur API ni leur MCP", inscrit)
        self.assertIn("a_faire_chez_partenaire", m)
        lot = self.run_outil("depart", entree={"agent": "dev-1", "taches": [t]})["message"]
        self.assertIn("## Partenaires où l'utilisateur est inscrit", lot)

    def test_sans_inscription_rien_ne_change(self):
        t = self.tache(role="dev", partenaires=["tripo"])
        m = self.run_outil("depart", entree={"agent": "dev-1", "tache": t})["message"]
        self.assertIn("### Tripo\n- " + petat.REGLE_TRIPO, m)
        self.assertNotIn("Partenaires où l'utilisateur est inscrit", m)
        self.assertNotIn("écartés", m)

    def test_connecte_et_inscrit_reste_appele_directement(self):
        self.p({"action": "confirmer", "ids": ["elevenlabs"]})
        self.p({"action": "inscrire", "partenaire": "elevenlabs", "inscrit": True})
        t = self.tache(role="dev", partenaires=["elevenlabs"])
        m = self.run_outil("depart", entree={"agent": "dev-1", "tache": t})["message"]
        self.assertIn("### ElevenLabs", m)
        self.assertNotIn("Partenaires où l'utilisateur est inscrit", m)

    def test_depart_suit_les_partenaires_decides_au_cadrage(self):
        self.p({"action": "inscrire", "partenaire": "tripo", "inscrit": True})
        self.p({"action": "confirmer", "ids": ["elevenlabs"]})
        self.run_outil("actions", entree={"type": "fonctionnalite", "texte": "Des personnages en 3D"})
        cahier = {"maquette": [], "etapes": ["Modéliser"],
                  "partenaires": [{"id": "tripo", "mode": "inscrit"}, {"id": "elevenlabs", "mode": "aucun"}]}
        self.run_outil("fonctionnalite", entree={"id": "f1", "agent_cadrage": "dev-1", "cahier": cahier})
        t = self.tache(role="dev", fonctionnalite="f1")
        m = self.run_outil("depart", entree={"agent": "dev-1", "tache": t})["message"]
        self.assertIn("## Partenaires où l'utilisateur est inscrit", m)      # Tripo, sans que la tâche le porte
        self.assertIn("## Partenaires écartés au cadrage", m)
        self.assertIn("de ne pas utiliser : ElevenLabs.", m)
        self.assertNotIn("Règles de tes partenaires", m)                      # personne n'est appelé

    def test_un_partenaire_ecarte_n_est_pas_prepare_meme_porte_par_la_tache(self):
        self.p({"action": "inscrire", "partenaire": "tripo", "inscrit": True})
        self.run_outil("actions", entree={"type": "fonctionnalite", "texte": "Des personnages en 3D"})
        self.run_outil("fonctionnalite", entree={"id": "f1", "agent_cadrage": "dev-1", "cahier": {
            "maquette": [], "etapes": ["x"], "partenaires": [{"id": "tripo", "mode": "aucun"}]}})
        t = self.tache(role="dev", fonctionnalite="f1", partenaires=["tripo"])
        m = self.run_outil("depart", entree={"agent": "dev-1", "tache": t})["message"]
        self.assertNotIn("### Tripo", m)
        self.assertIn("de ne pas utiliser : Tripo.", m)


class TestCadragePartenaires(AvecPartenaires):
    def test_cadrage_controle_les_partenaires_decides(self):
        self.p({"action": "inscrire", "partenaire": "tripo", "inscrit": True})
        self.p({"action": "confirmer", "ids": ["elevenlabs"]})
        ok = [{"id": "tripo", "mode": "inscrit"}, {"id": "elevenlabs", "mode": "direct"}]
        self.assertEqual(self.p({"action": "verifier_cadrage", "partenaires": ok}), {"ok": True})
        self.assertEqual(self.p({"action": "verifier_cadrage", "partenaires": [{"id": "cartesia", "mode": "aucun"}]}),
                         {"ok": True})                                       # écarter n'exige rien
        cas = (([{"id": "tripo", "mode": "direct"}], "pas connecté"),
               ([{"id": "elevenlabs", "mode": "inscrit"}], "pas dit être inscrit"),
               ([{"id": "inexistant", "mode": "aucun"}], "inconnu"),
               ([{"id": "tripo", "mode": "bientôt"}], "liste de"),
               ([{"id": "tripo", "mode": "aucun"}, {"id": "tripo", "mode": "aucun"}], "liste de"),
               ([{"id": "tripo", "mode": "aucun", "x": 1}], "liste de"),
               ("tripo", "liste de"))
        for mauvais, mot in cas:
            self.assertIn(mot, self.refus({"action": "verifier_cadrage", "partenaires": mauvais}))

    def test_le_cahier_garde_les_partenaires_decides(self):
        self.p({"action": "inscrire", "partenaire": "tripo", "inscrit": True})
        self.p({"action": "confirmer", "ids": ["elevenlabs"]})
        self.run_outil("actions", entree={"type": "fonctionnalite", "texte": "Des personnages en 3D"})
        code, objet = outil.executer(self.factory, ["fonctionnalite"], {"id": "f1", "cahier": {
            "maquette": [], "etapes": ["x"], "partenaires": [{"id": "tripo", "mode": "direct"}]}})
        self.assertEqual(code, 1, objet)                                      # le cahier lui-même est contrôlé
        ok = [{"id": "tripo", "mode": "inscrit"}, {"id": "elevenlabs", "mode": "direct"}]
        self.run_outil("fonctionnalite", entree={"id": "f1", "agent_cadrage": "dev-1", "cahier": {
            "maquette": [], "etapes": ["x"], "partenaires": ok}})
        r = outil.construire_releve(outil.Contexte(self.factory))
        self.assertEqual(releve.valider(r), [])
        self.assertEqual(r["fonctionnalites"][0]["cahier"]["partenaires"], ok)
        self.assertTrue(releve.partenaires_cahier_ok(ok))
        for mauvais in ([{"id": "a", "mode": "x"}], [{"id": "a", "mode": "aucun"}] * 2, [{"id": "a"}], "a", [{"id": "", "mode": "aucun"}]):
            self.assertFalse(releve.partenaires_cahier_ok(mauvais), mauvais)

    def test_disponibles_pour_le_cadrage(self):
        self.assertEqual(self.p({"action": "disponibles"}), {"partenaires": []})
        self.p({"action": "inscrire", "partenaire": "tripo", "inscrit": True})
        self.p({"action": "confirmer", "ids": ["elevenlabs"]})
        self.p({"action": "inscrire", "partenaire": "elevenlabs", "inscrit": True})
        par = {x["id"]: x for x in self.p({"action": "disponibles"})["partenaires"]}
        self.assertEqual(par["tripo"]["modes"], ["inscrit"])
        self.assertEqual(par["elevenlabs"]["modes"], ["direct", "inscrit"])
        self.assertTrue(par["tripo"]["description"])
        self.p({"action": "inscrire", "partenaire": "tripo", "inscrit": False})
        self.assertNotIn("tripo", [x["id"] for x in self.p({"action": "disponibles"})["partenaires"]])


if __name__ == "__main__":
    unittest.main()
