"""Le coût de chaque tâche (historique d'un agent, fiche d'une tâche) et celui d'une tâche en cours."""
import json
import tempfile
import unittest
from pathlib import Path

from bureau import cout
from moteur import detache

PRIX = {"entree": 3.0, "sortie": 15.0, "cache_lecture": 0.3, "cache_ecriture": 3.75}


def prix_de(modele, date_iso):
    return (PRIX if modele == "claude-sonnet-5-5" else None), date_iso, False


def usage(tache, entree=1_000_000, sortie=0, modele="claude-sonnet-5-5", **plus):
    return {"tache": tache, "modele": modele, "entree": entree, "sortie": sortie, "cache_lecture": 0,
            "cache_ecriture": 0, "t": "2026-11-13T10:00:00+01:00", **plus}


class CoutsTaches(unittest.TestCase):
    def test_cout_de_chaque_tache(self):
        r = {"taches": [{"id": "t1"}, {"id": "t2"}, {"id": "t3"}]}
        c = cout.couts_taches([usage("t1"), usage("t1", 0, 1_000_000), usage("t2", modele="inconnu"),
                               usage("t9"), usage("t3", genre="partenaire")], prix_de, r)
        self.assertEqual(c["t1"], {"total": 18.0, "sans_prix": 0, "tokens": 2_000_000})
        self.assertEqual(c["t2"]["sans_prix"], 1)
        self.assertNotIn("t9", c)        # une tâche inconnue du relevé
        self.assertNotIn("t3", c)        # les tokens d'un partenaire ne sont pas des euros ici


class ConsoEnCours(unittest.TestCase):
    def test_un_message_compte_une_fois_et_le_flux_n_est_relu_que_pour_la_suite(self):
        with tempfile.TemporaryDirectory() as d:
            flux = Path(d) / "t1.jsonl"

            def message(i, sortie):
                return json.dumps({"type": "assistant", "message": {"id": f"m{i}", "model": "claude-sonnet-5-5",
                                   "usage": {"input_tokens": 10, "output_tokens": sortie,
                                             "cache_read_input_tokens": 100, "cache_creation_input_tokens": 5}}})
            flux.write_text("\n".join([message(1, 3), message(1, 3), '{"type": "tool_progress"}']) + "\n",
                            encoding="utf-8")
            self.assertEqual(detache.conso_en_cours(flux), [{"modele": "claude-sonnet-5-5", "entree": 10, "sortie": 3,
                                                             "cache_lecture": 100, "cache_ecriture": 5}])
            with open(flux, "a", encoding="utf-8") as f:
                f.write(message(2, 7) + "\n")
            self.assertEqual(detache.conso_en_cours(flux)[0]["sortie"], 10)       # le coût évolue
            synth = json.dumps({"type": "assistant", "message": {"id": "s", "model": "<synthetic>",
                                                                 "usage": {"output_tokens": 999}}})
            with open(flux, "a", encoding="utf-8") as f:
                f.write(synth + "\n")
            self.assertEqual(detache.conso_en_cours(flux)[0]["sortie"], 10)       # un message synthétique ne compte pas


if __name__ == "__main__":
    unittest.main()
