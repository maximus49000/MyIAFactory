"""Essai réel : la facturation lit les tokens exacts dans les transcriptions locales de Claude Code (sous-agents et
conversation orchestratrice), au lieu d'estimations ; l'orchestrateur n'était pas compté du tout."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from orchestrateur import transcriptions as tr
from tests.orch_aide import AvecProjet


def ligne(mid, modele, entree, sortie, lu, ecrit, type_="assistant"):
    return json.dumps({"type": type_, "message": {"id": mid, "model": modele, "usage": {
        "input_tokens": entree, "output_tokens": sortie, "cache_read_input_tokens": lu,
        "cache_creation_input_tokens": ecrit}}})


class TestCompter(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)

    def test_un_message_n_est_compte_qu_une_fois(self):
        f = self.d / "a.jsonl"
        f.write_text("\n".join([ligne("m1", "claude-sonnet-5-5", 10, 100, 1000, 50),
                                ligne("m1", "claude-sonnet-5-5", 10, 100, 1000, 50),   # le même message, rejoué
                                ligne("m2", "claude-haiku-5-5", 1, 2, 3, 4),
                                json.dumps({"type": "user", "message": {"content": "x"}}), "pas du json"]),
                     encoding="utf-8")
        self.assertEqual(tr.compter(f), {
            "claude-sonnet-5-5": {"entree": 10, "sortie": 100, "cache_lecture": 1000, "cache_ecriture": 50},
            "claude-haiku-5-5": {"entree": 1, "sortie": 2, "cache_lecture": 3, "cache_ecriture": 4}})

    def test_dossier_d_un_projet(self):
        self.assertEqual(tr.nom_dossier(r"C:\Users\zoe\Mes essais\vide"), "C--Users-zoe-Mes-essais-vide")

    def test_sous_agent_retrouve_par_son_identifiant(self):
        f = self.d / "C--p" / "sess" / "subagents" / "agent-a1b2c3.jsonl"
        f.parent.mkdir(parents=True)
        f.write_text(ligne("m1", "claude-haiku-5-5", 1, 2, 3, 4), encoding="utf-8")
        self.assertEqual(tr.sous_agent("a1b2c3", racine=self.d), f)
        self.assertIsNone(tr.sous_agent("inconnu", racine=self.d))
        self.assertIsNone(tr.sous_agent("../x", racine=self.d))   # jamais un chemin


class TestDansLOutil(AvecProjet):
    """`lancer usage` avec `agent_id`, et la gestion notée à chaque réveil."""

    def setUp(self):
        super().setUp()
        self.maison = self.dossier / "maison"
        self.racine = self.maison / ".claude" / "projects"
        anciens = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE")}
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.maison)
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None)
                                 for k, v in anciens.items()])

    def releve(self):
        return self.ok("releve")

    def test_usage_exact_d_un_sous_agent(self):
        f = self.racine / "C--p" / "s1" / "subagents" / "agent-abc123.jsonl"
        f.parent.mkdir(parents=True)
        f.write_text("\n".join([ligne("m1", "claude-haiku-5-5", 5, 700, 40000, 3000),
                                ligne("m2", "claude-haiku-5-5", 1, 300, 50000, 0)]), encoding="utf-8")
        t = self.ok("tache", entree={"titre": "Contrôle", "role": "dev", "colonne": "dev", "agent": "dev-1"})
        r = self.ok("usage", entree={"agent": "dev-1", "tache": t["id"], "agent_id": "abc123", "etape": "controle"})
        u = next(x for x in self.releve()["usage"] if x["id"] == r["id"])
        self.assertEqual((u["modele"], u["entree"], u["sortie"], u["cache_lecture"], u["cache_ecriture"]),
                         ("claude-haiku-5-5", 6, 1000, 90000, 3000))
        self.assertFalse(u.get("estime"))

    def test_sous_agent_introuvable(self):
        code, r = self.outil("usage", entree={"agent": "dev-1", "agent_id": "zzz999"})
        self.assertEqual(code, 1)
        self.assertIn("total", r["erreur"])   # dit quoi faire à la place

    def test_le_reveil_note_la_gestion(self):
        projet = self.dossier.parent if self.dossier.name == ".factory" else self.dossier
        d = self.racine / tr.nom_dossier(projet)
        d.mkdir(parents=True)
        debut = json.dumps({"type": "user", "message": {"content": "Tu es l'orchestrateur du projet dont le "
                            f"fichier de factory est `{self.factory}`. Lis…"}})
        (d / "orch.jsonl").write_text("\n".join([debut, ligne("m1", "claude-sonnet-5-5", 2, 400, 100000, 9000)]),
                                      encoding="utf-8")
        (d / "autre.jsonl").write_text(ligne("m9", "claude-sonnet-5-5", 1, 1, 1, 1), encoding="utf-8")  # pas lui
        self.ok("lancer", "reveil")
        self.ok("lancer", "reveil")   # cumul : la même ligne, mise à jour
        gestion = [u for u in self.releve()["usage"] if u.get("etape") == "gestion"]
        self.assertEqual(len(gestion), 1)
        self.assertEqual((gestion[0]["sortie"], gestion[0]["cache_lecture"]), (400, 100000))
        self.assertIsNone(gestion[0].get("tache"))


if __name__ == "__main__":
    unittest.main()
