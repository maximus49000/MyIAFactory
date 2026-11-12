import copy
import tempfile
import unittest
from pathlib import Path

from bureau import releve
from bureau.usage import HistoriqueUsage

RELEVE = {"version": 3, "projet": "P", "factory": {"etat": "en marche"},
          "services": [{"id": "dev", "nom": "Dev"}, {"id": "qa", "nom": "QA"}],
          "colonnes": [{"id": "a", "nom": "A"}],
          "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"},
                         {"cle": "dir", "lieu": "local", "chef": True}],
          "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"}]}


def releve_avec(*usages, titulaires=None):
    r = copy.deepcopy(RELEVE)
    if titulaires is not None:
        r["titulaires"] = titulaires
        r["taches"][0]["titulaire"] = titulaires[0]["cle"]
    r["usage"] = list(usages)
    assert releve.valider(r) == [], releve.valider(r)
    return releve.normaliser(r)


def usage(**champs):
    u = {"id": "u1", "tache": "t1", "agent": "d1", "modele": "sonnet", "etape": "dev",
         "t": "2026-11-09T10:00:00", "entree": 1000, "sortie": 200}
    u.update(champs)
    return u


class TestHistoriqueUsage(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.chemin = Path(self.dossier.name) / "usage-historique.jsonl"
        self.h = HistoriqueUsage(self.chemin)

    def tearDown(self):
        self.dossier.cleanup()

    def test_vide_au_depart(self):
        self.assertEqual(self.h.lire(), [])

    def test_premiere_apparition(self):
        self.h.integrer(releve_avec(usage(cache_lecture=30)))
        [ligne] = self.h.lire()
        self.assertEqual(ligne, {"id": "u1", "tache": "t1", "agent": "d1", "service": "dev",
                                 "modele": "sonnet", "etape": "dev", "t": "2026-11-09T10:00:00",
                                 "t_prix": "2026-11-09T10:00:00", "entree": 1000, "sortie": 200,
                                 "cache_lecture": 30, "cache_ecriture": 0})

    def test_le_genre_de_la_fonctionnalite_est_gardé(self):
        self.h.integrer(releve_avec(usage(genre_fonctionnalite="jeu-web"), usage(id="u2")))
        lignes = {x["id"]: x for x in self.h.lire()}
        self.assertEqual(lignes["u1"]["genre_fonctionnalite"], "jeu-web")
        self.assertNotIn("genre_fonctionnalite", lignes["u2"])   # un usage ancien n'en a pas

    def test_l_instantane_d_abonnement_du_debut_de_l_appel_est_garde(self):
        premier = {"five_hour": {"pourcent": 25.0, "remise": 1794485400}, "t": 1794480000}
        plus_tard = {"five_hour": {"pourcent": 30.0, "remise": 1794485400}, "t": 1794481000}
        self.h.integrer(releve_avec(usage(abonnement=premier), usage(id="u2", abonnement={"bizarre": 1})))
        self.h.integrer(releve_avec(usage(abonnement=plus_tard, entree=2000)))
        lignes = {x["id"]: x for x in self.h.lire()}
        self.assertEqual(lignes["u1"]["abonnement"], premier)    # figé à la première apparition
        self.assertEqual(lignes["u1"]["entree"], 2000)
        self.assertNotIn("abonnement", lignes["u2"])             # mal formé : ignoré, le relevé reste valide

    def test_compteurs_mis_a_jour_date_inchangee(self):
        self.h.integrer(releve_avec(usage()))
        self.h.integrer(releve_avec(usage(t="2026-11-10T09:00:00", entree=5000, sortie=900)))
        [ligne] = self.h.lire()
        self.assertEqual((ligne["entree"], ligne["sortie"]), (5000, 900))
        self.assertEqual(ligne["t_prix"], "2026-11-09T10:00:00")
        self.assertEqual(ligne["t"], "2026-11-10T09:00:00")

    def test_service_fige_quand_l_agent_change(self):
        self.h.integrer(releve_avec(usage()))
        autre = [{"cle": "d1", "service": "qa", "lieu": "local"}]
        self.h.integrer(releve_avec(usage(entree=2000), usage(id="u2"), titulaires=autre))
        lignes = {x["id"]: x for x in self.h.lire()}
        self.assertEqual(lignes["u1"]["service"], "dev")
        self.assertEqual(lignes["u1"]["entree"], 2000)
        self.assertEqual(lignes["u2"]["service"], "qa")

    def test_agent_parti_garde_son_usage(self):
        self.h.integrer(releve_avec(usage()))
        self.h.integrer(releve_avec(titulaires=[{"cle": "d2", "service": "dev", "lieu": "local"}]))
        [ligne] = self.h.lire()
        self.assertEqual((ligne["id"], ligne["agent"], ligne["service"]), ("u1", "d1", "dev"))

    def test_chef_sans_service(self):
        self.h.integrer(releve_avec(usage(agent="dir", tache=None), usage(id="u2", agent=None, tache=None)))
        lignes = {x["id"]: x for x in self.h.lire()}
        self.assertIsNone(lignes["u1"]["service"])
        self.assertIsNone(lignes["u2"]["service"])
        self.assertIsNone(lignes["u1"]["tache"])

    def test_ligne_illisible_ignoree(self):
        self.h.integrer(releve_avec(usage()))
        with open(self.chemin, "a", encoding="utf-8") as f:
            f.write("pas du json\n[1, 2]\n{\"id\": 3}\n{\"id\": \"x\", \"entree\": \"beaucoup\"}\n")
        self.assertEqual([x["id"] for x in self.h.lire()], ["u1"])
        self.h.integrer(releve_avec(usage(id="u2")))
        self.assertEqual(sorted(x["id"] for x in self.h.lire()), ["u1", "u2"])

    def test_survit_au_redemarrage(self):
        self.h.integrer(releve_avec(usage(), usage(id="u2")))
        relu = HistoriqueUsage(self.chemin)
        self.assertEqual(sorted(x["id"] for x in relu.lire()), ["u1", "u2"])
        relu.integrer(releve_avec(usage(t="2026-11-12T00:00:00", entree=1)))
        self.assertEqual({x["id"]: x["t_prix"] for x in HistoriqueUsage(self.chemin).lire()},
                         {"u1": "2026-11-09T10:00:00", "u2": "2026-11-09T10:00:00"})

    def test_releve_sans_usage_ne_touche_rien(self):
        self.h.integrer(releve_avec(usage()))
        avant = self.chemin.read_bytes()
        v2 = releve.normaliser({**copy.deepcopy(RELEVE), "version": 2})
        self.h.integrer(v2)
        self.h.integrer(releve_avec(usage()))  # rien de neuf : fichier inchangé
        self.assertEqual(self.chemin.read_bytes(), avant)
        self.assertEqual(len(self.h.lire()), 1)

    def test_dossier_absent_cree(self):
        h = HistoriqueUsage(Path(self.dossier.name) / "sous" / "usage-historique.jsonl")
        h.integrer(releve_avec(usage()))
        self.assertEqual(len(h.lire()), 1)


if __name__ == "__main__":
    unittest.main()
