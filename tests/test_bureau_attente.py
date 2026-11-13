"""Ce que le moteur dit au bureau de ce qui retient le travail : la pause d'une installation, l'attente de charge."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from bureau import attente, serveur
from tests.test_serveur import AvecServeur


class Fichiers(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._t.cleanup)
        self.dossier = Path(self._t.name)
        self.bureau = self.dossier / "bureau.json"

    def test_pause_ecrite_puis_lue_pour_le_bureau(self):
        attente.ecrire(attente.chemin_pause(self.bureau), {"texte": "Pause : installation de Godot Engine (Jeu)",
                                                           "projet": "Jeu", "outils": ["Godot Engine"]})
        self.assertEqual(attente.pause_installation(self.bureau),
                         {"texte": "Pause : installation de Godot Engine (Jeu)", "projet": "Jeu", "outils": ["Godot Engine"]})
        attente.effacer(attente.chemin_pause(self.bureau))
        self.assertIsNone(attente.pause_installation(self.bureau))

    def test_un_fichier_que_le_moteur_n_a_pas_reecrit_est_ignore(self):
        chemin = attente.chemin_pause(self.bureau)
        attente.ecrire(chemin, {"texte": "Pause : installation de X (Y)"}, maintenant=time.time() - attente.FRAICHEUR_S - 5)
        self.assertIsNone(attente.pause_installation(self.bureau))
        attente.ecrire(chemin, {"texte": "Pause : installation de X (Y)"})
        self.assertIsNotNone(attente.pause_installation(self.bureau))

    def test_fichier_illisible_ou_sans_texte_ignore(self):
        chemin = attente.chemin_pause(self.bureau)
        chemin.write_text("pas du json", encoding="utf-8")
        self.assertIsNone(attente.pause_installation(self.bureau))
        chemin.write_text(json.dumps({"t": time.time(), "texte": "  "}), encoding="utf-8")
        self.assertIsNone(attente.pause_installation(self.bureau))
        self.assertIsNone(attente.pause_installation(None))

    def test_raisons_des_taches_lues_et_nettoyees(self):
        chemin = attente.chemin_taches(self.dossier)
        self.assertEqual(chemin.name, "attente-taches.json")
        self.assertIsNone(attente.attente_taches(self.dossier))
        attente.ecrire(chemin, {"texte": "2 tâches en attente", "total": 2,
                                "familles": [{"genre": "prerequis", "motif": "prérequis", "n": 1, "texte": "1 prérequis"},
                                             {"genre": "inconnu", "motif": "x", "n": 1, "texte": "1 x"},
                                             "pas un objet"],
                                "taches": {"t1": {"genre": "prerequis", "motif": "prérequis",
                                                  "texte": "prérequis — Essai", "detail": ["une ligne", 3],
                                                  "ensuite": ["elle exige le poste local", None],
                                                  "quand": "quand vous aurez validé « Essai »", "en_trop": 1},
                                           "t2": {"genre": "bizarre", "texte": "x"},
                                           "t3": "pas un objet"}})
        lu = attente.attente_taches(self.dossier)
        self.assertEqual(lu["texte"], "2 tâches en attente")
        self.assertEqual(lu["familles"], [{"genre": "prerequis", "motif": "prérequis", "n": 1, "texte": "1 prérequis"}])
        self.assertEqual(lu["taches"], {"t1": {"genre": "prerequis", "motif": "prérequis", "texte": "prérequis — Essai",
                                               "detail": ["une ligne"], "ensuite": ["elle exige le poste local"],
                                               "quand": "quand vous aurez validé « Essai »"}})
        attente.ecrire(chemin, {"texte": "1 tâche en attente", "taches": {}}, maintenant=0)      # le moteur s'est arrêté
        self.assertIsNone(attente.attente_taches(self.dossier))

    def test_etat_du_bureau_porte_la_pause_pour_tous_les_projets(self):
        class Projet:
            def etat(self):
                return {"projet": "B", "taches": []}
        faux = SimpleNamespace(fichier_bureau=self.bureau)
        self.assertIsNone(serveur.Bureau.etat_du_projet(faux, Projet())["pause_installation"])
        attente.ecrire(attente.chemin_pause(self.bureau), {"texte": "Pause : installation de Godot Engine (Jeu)",
                                                           "projet": "Jeu", "outils": ["Godot Engine"]})
        e = serveur.Bureau.etat_du_projet(faux, Projet())
        self.assertEqual((e["projet"], e["pause_installation"]["texte"]), ("B", "Pause : installation de Godot Engine (Jeu)"))


class TestEtatServi(AvecServeur):
    def etat(self):
        self.p._cache_etat = (0.0, None)
        r, data = self.req("GET", "/api/etat")
        self.assertEqual(r.status, 200)
        return json.loads(data.decode("utf-8"))

    def test_la_tache_retenue_par_la_charge_porte_son_attente(self):
        dossier = self.tmp / "demo"
        sans = self.etat()
        self.assertIsNone(sans["attente_charge"])
        self.assertIsNone(sans["pause_installation"])
        self.assertTrue(all("attente" not in t for t in sans["taches"]))
        tid = sans["taches"][0]["id"]
        attente.ecrire(attente.chemin_charge(dossier), {"texte": "En attente : charge 90 % (plafond 70 %)",
                                                        "taches": [tid], "charge": 90, "plafond": 70})
        e = self.etat()
        self.assertEqual(e["attente_charge"], {"texte": "En attente : charge 90 % (plafond 70 %)", "taches": [tid],
                                               "charge": 90, "plafond": 70})
        self.assertEqual([t["attente"] for t in e["taches"] if "attente" in t], ["En attente : charge 90 % (plafond 70 %)"])
        self.assertEqual(next(t for t in e["taches"] if t["id"] == tid)["attente"], "En attente : charge 90 % (plafond 70 %)")
        attente.effacer(attente.chemin_charge(dossier))
        self.assertIsNone(self.etat()["attente_charge"])

    def test_les_places_libres_qui_attendent_une_validation(self):
        dossier = self.tmp / "demo"
        self.assertIsNone(self.etat()["attente_validation"])
        texte = "2 places libres : en attente de votre validation « Validation de la direction artistique »"
        attente.ecrire(attente.chemin_places(dossier), {"texte": texte, "places": 2,
                                                        "validation": "Validation de la direction artistique"})
        self.assertEqual(self.etat()["attente_validation"], {"texte": texte, "places": 2,
                                                             "validation": "Validation de la direction artistique"})
        attente.ecrire(attente.chemin_places(dossier), {"texte": texte}, maintenant=0)     # le moteur s'est arrêté
        self.assertIsNone(self.etat()["attente_validation"])

    def test_chaque_tache_en_attente_porte_sa_raison(self):
        dossier = self.tmp / "demo"
        sans = self.etat()
        self.assertIsNone(sans["attentes"])
        self.assertTrue(all("attente_raison" not in t for t in sans["taches"]))
        tid = sans["taches"][0]["id"]
        raison = {"genre": "agent", "motif": "poste local occupé", "texte": "poste local occupé",
                  "detail": ["elle exige le poste local ; 1 place locale, occupée par Léa"], "ensuite": [],
                  "quand": "quand le poste local se libérera"}
        familles = [{"genre": "agent", "motif": "poste local occupé", "n": 1, "texte": "1 poste local occupé"}]
        attente.ecrire(attente.chemin_taches(dossier), {"texte": "1 tâche en attente", "total": 1, "familles": familles,
                                                        "taches": {tid: raison, "t-inconnue": raison}})
        e = self.etat()
        self.assertEqual(e["attentes"], {"texte": "1 tâche en attente", "total": 1, "familles": familles})
        self.assertEqual(next(t for t in e["taches"] if t["id"] == tid)["attente_raison"], raison)
        self.assertEqual(sum(1 for t in e["taches"] if "attente_raison" in t), 1)

    def test_l_agent_au_travail_dit_depuis_quand_et_sa_derniere_action(self):
        import os
        from moteur import detache
        sans = self.etat()
        self.assertTrue(all("travail" not in t for t in sans["taches"]))
        tid = sans["taches"][0]["id"]
        d = detache.dossier(self.tmp / "demo")
        d.mkdir()
        (d / f"{tid}.json").write_text(json.dumps({"tache": tid, "taches": [tid], "agent": "dev-1", "pid": os.getpid(),
                                                   "debut": time.time() - 600}), encoding="utf-8")
        (d / f"{tid}.jsonl").write_text(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": "scenes/combat.gd", "content": "x"}}]}}) + "\n",
            encoding="utf-8")
        t = next(t for t in self.etat()["taches"] if t["id"] == tid)
        self.assertEqual((t["travail"]["agent"], t["travail"]["action"]), ("dev-1", "écrit scenes/combat.gd"))
        self.assertIn("depuis", t["travail"])


if __name__ == "__main__":
    unittest.main()
