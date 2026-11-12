"""L'estimation du coût d'un élément : mesures du genre, sinon valeurs par défaut."""
import json
import tempfile
import unittest
from pathlib import Path

from installation import estimation

PRIX = {"Haiku": {"entree": 1e-6, "sortie": 5e-6}, "Sonnet": {"entree": 3e-6, "sortie": 15e-6},
        "Opus": {"entree": 5e-6, "sortie": 25e-6}}
FLUX = [{"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"},
        {"id": "relecture", "nom": "Relecture", "role": "relecteur", "service": "dev"}]
AGENTS = [{"cle": "dev-1", "role": "dev", "modele": "Sonnet"},
          {"cle": "rel-1", "role": "relecteur", "modele": "Haiku"}]


def usage(modele, total, i=0):
    return {"id": f"u{modele}{total}{i}", "modele": modele, "entree": total // 2, "sortie": total // 2 - 1,
            "cache_lecture": 0, "cache_ecriture": 1}


class TestEstimation(unittest.TestCase):
    def test_defauts_sans_mesure(self):
        r = estimation.estimer(FLUX, AGENTS, [], PRIX.get)
        self.assertEqual(r["source"], "defauts")
        self.assertEqual(len(r["detail"]), 3)  # cadrage + deux étapes
        self.assertEqual(r["detail"][0]["etape"], "cadrage")
        self.assertEqual(r["detail"][0]["modele"], "Sonnet")
        mini = sum(d["tokens"][0] for d in r["detail"])
        self.assertEqual(r["tokens"][0], mini)
        self.assertEqual(estimation.DEFAUTS_TOKENS["Haiku"], (40_000, 150_000))
        self.assertIsNotNone(r["euros"])

    def test_mesures_si_cinq_usages(self):
        us = [usage("Sonnet", t, i) for i, t in enumerate((1000, 2000, 3000, 4000, 5000))]
        r = estimation.estimer(FLUX, AGENTS, us, PRIX.get)
        dev = next(d for d in r["detail"] if d["etape"] == "dev")
        self.assertEqual(dev["source"], "mesures")
        self.assertEqual(dev["tokens"], [2000, 4000])
        self.assertEqual(r["source"], "mixte")

    def test_quatre_usages_ne_suffisent_pas(self):
        us = [usage("Sonnet", 1000 * (i + 1), i) for i in range(4)]
        r = estimation.estimer(FLUX, AGENTS, us, PRIX.get)
        self.assertEqual(r["source"], "defauts")

    def test_mesures_partout(self):
        us = [usage(m, 1000 * (i + 1), i) for m in ("Sonnet", "Haiku") for i in range(5)]
        r = estimation.estimer(FLUX, AGENTS, us, PRIX.get)
        self.assertEqual(r["source"], "mesures")

    def test_euros_sans_prix_none(self):
        r = estimation.estimer(FLUX, AGENTS, [], lambda m: None)
        self.assertIsNone(r["euros"])
        self.assertIn("prix inconnu", r["explication"])

    def test_fourchette_ordonnee(self):
        for us in ([], [usage("Sonnet", t, i) for i, t in enumerate((9, 1, 5, 3, 7))]):
            r = estimation.estimer(FLUX, AGENTS, us, PRIX.get)
            self.assertLessEqual(r["tokens"][0], r["tokens"][1])
            self.assertLessEqual(r["euros"][0], r["euros"][1])
            for d in r["detail"]:
                self.assertLessEqual(d["tokens"][0], d["tokens"][1])

    def test_mesures_chiffrees_compteur_par_compteur(self):
        # une session d'agent est surtout faite de lectures en cache : elles ne coûtent pas le prix d'entrée
        us = [{"id": f"c{i}", "modele": m, "entree": 10_000, "sortie": 5_000, "cache_lecture": 1_000_000,
               "cache_ecriture": 20_000} for m in ("Sonnet", "Haiku") for i in range(5)]
        r = estimation.estimer(FLUX, AGENTS, us, PRIX.get)
        self.assertEqual(r["source"], "mesures")
        attendu = 0
        for m in ("Sonnet", "Sonnet", "Haiku"):   # cadrage, dev, relecture
            p = PRIX[m]
            attendu += (10_000 * p["entree"] + 5_000 * p["sortie"] + 1_000_000 * p["entree"] * 0.1
                        + 20_000 * p["entree"] * 1.25)
        self.assertAlmostEqual(r["euros"][1], round(attendu, 2), places=2)
        # un prix de cache donné par la source l'emporte
        avec = {m: {**p, "cache_lecture": 0} for m, p in PRIX.items()}
        self.assertLess(estimation.estimer(FLUX, AGENTS, us, avec.get)["euros"][1], r["euros"][1])

    def test_role_sans_agent_refuse(self):
        with self.assertRaises(ValueError):
            estimation.estimer(FLUX, AGENTS[:1], [], PRIX.get)


class TestUsagesDuGenre(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def projet(self, nom, genre, usages):
        d = self.base / nom / ".factory"
        d.mkdir(parents=True)
        (d / "factory.json").write_text(json.dumps({"genre": genre}), encoding="utf-8")
        (d / "reglages.json").write_text(json.dumps({"orchestrateur": "factory.json"}), encoding="utf-8")
        ligne = {"id": "", "tache": None, "agent": None, "service": None, "etape": None, "t": "2026-01-01",
                 "t_prix": "2026-01-01", "entree": 1, "sortie": 1, "cache_lecture": 0, "cache_ecriture": 0}
        (d / "usage-historique.jsonl").write_text(
            "".join(json.dumps({**ligne, "id": f"{nom}{i}", "modele": m}) + "\n" for i, m in enumerate(usages)),
            encoding="utf-8")
        return f"{nom}/.factory/reglages.json"

    def test_mesures_du_genre_seulement(self):
        a = self.projet("a", "jeu", ["Sonnet", "Haiku"])
        b = self.projet("b", "web", ["Opus"])
        c = self.projet("c", "jeu", ["Sonnet"])
        bureau = self.base / "bureau.json"
        bureau.write_text(json.dumps({"projets": [a, b, c]}), encoding="utf-8")
        self.assertEqual(sorted(u["modele"] for u in estimation.usages_du_genre(bureau, "jeu")),
                         ["Haiku", "Sonnet", "Sonnet"])
        self.assertEqual([u["modele"] for u in estimation.usages_du_genre(bureau, "web")], ["Opus"])

    def test_estimation_par_genre_de_fonctionnalite(self):
        # Un projet « jeu » dont une fonctionnalité est du genre « web » : ses usages se rangent par genre de
        # fonctionnalité ; un usage ancien, sans genre, compte pour le genre du projet.
        a = self.projet("a", "jeu", ["Sonnet", "Haiku", "Opus"])
        d = self.base / "a" / ".factory"
        (d / "factory.json").write_text(json.dumps({"genre": "jeu", "workflows": [
            {"id": "w-f2", "fonctionnalite": "f2", "genre": "web", "flux": []}]}), encoding="utf-8")
        lignes = [json.loads(x) for x in (d / "usage-historique.jsonl").read_text(encoding="utf-8").splitlines()]
        lignes[0]["genre_fonctionnalite"] = "web"   # Sonnet : une fonctionnalité web
        lignes[1]["genre_fonctionnalite"] = "jeu"   # Haiku : une fonctionnalité du genre du projet
        (d / "usage-historique.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lignes), encoding="utf-8")
        bureau = self.base / "bureau.json"
        bureau.write_text(json.dumps({"projets": [a]}), encoding="utf-8")
        self.assertEqual([u["modele"] for u in estimation.usages_du_genre(bureau, "web")], ["Sonnet"])
        self.assertEqual(sorted(u["modele"] for u in estimation.usages_du_genre(bureau, "jeu")), ["Haiku", "Opus"])

    def test_genre_nul_ou_bureau_absent(self):
        a = self.projet("a", "jeu", ["Sonnet"])
        bureau = self.base / "bureau.json"
        bureau.write_text(json.dumps({"projets": [a]}), encoding="utf-8")
        self.assertEqual(estimation.usages_du_genre(bureau, None), [])
        self.assertEqual(estimation.usages_du_genre(self.base / "absent.json", "jeu"), [])

    def test_bureau_illisible(self):
        bureau = self.base / "bureau.json"
        bureau.write_text("pas du json", encoding="utf-8")
        self.assertEqual(estimation.usages_du_genre(bureau, "jeu"), [])


if __name__ == "__main__":
    unittest.main()


class TestPrixDesModeles(unittest.TestCase):
    """La source des prix d'un modèle est partagée par l'installation et le moteur (`estimation.prix_de_modele`)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        d = self.base / "p" / ".factory"
        d.mkdir(parents=True)
        (d / "reglages.json").write_text(json.dumps({"prix": {
            "Sonnet": {"entree": 3, "sortie": 15, "date": "2026-01-01"}}}), encoding="utf-8")
        self.bureau = self.base / "bureau.json"
        self.bureau.write_text(json.dumps({"projets": ["p/.factory/reglages.json"]}), encoding="utf-8")

    def test_prix_par_token_d_apres_le_premier_projet_qui_le_connait(self):
        p = estimation.prix_de_modele(self.bureau, "Sonnet")
        self.assertAlmostEqual(p["entree"], 3e-6)
        self.assertAlmostEqual(p["sortie"], 15e-6)
        self.assertIsNone(estimation.prix_de_modele(self.bureau, "Inconnu"))

    def test_bureau_absent_ou_illisible_aucun_prix(self):
        self.assertIsNone(estimation.prix_de_modele(self.base / "absent.json", "Sonnet"))
        self.assertIsNone(estimation.prix_de_modele(None, "Sonnet"))
        self.bureau.write_text("pas du json", encoding="utf-8")
        self.assertIsNone(estimation.prix_de_modele(self.bureau, "Sonnet"))

    def test_le_cout_d_un_workflow_propose_est_chiffre_en_euros(self):
        from moteur import regles
        projet = type("P", (), {"bureau": self.bureau})()
        agents = [dict(a, modele="Sonnet") for a in AGENTS]
        c = regles._cout(projet, FLUX, agents, "jeu")
        self.assertEqual(len(c["euros"]), 2)
        self.assertGreater(c["euros"][1], 0)
        # aucun prix connu : le comportement d'avant (tokens seulement, pas d'échec)
        projet.bureau = self.base / "absent.json"
        c = regles._cout(projet, FLUX, agents, "jeu")
        self.assertIsNone(c["euros"])
        self.assertEqual(len(c["tokens"]), 2)
