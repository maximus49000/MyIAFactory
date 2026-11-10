import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bureau import equipe, etat, releve

M = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

BASE = {"version": 1, "projet": "P", "factory": {"etat": "en marche"},
        "services": [{"id": "dev", "nom": "Dev"}, {"id": "qa", "nom": "QA"}],
        "colonnes": [{"id": "a", "nom": "A"}],
        "titulaires": [{"cle": "d1", "service": "dev", "lieu": "local"},
                       {"cle": "c1", "service": "qa", "lieu": "cloud"}],
        "taches": [{"id": "t1", "titre": "T", "colonne": "a", "active": True, "titulaire": "d1"},
                   {"id": "t2", "titre": "U", "colonne": "a", "active": True, "titulaire": "c1"}]}


class TestEtat(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        self.eq = equipe.Equipe(self.tmp / "equipe.json")

    def etat(self, active=True, minutes=5, modif=None, fraicheur=30):
        r = copy.deepcopy(BASE)
        r["taches"][0]["active"] = active
        r["taches"][0]["maj"] = (M - timedelta(minutes=minutes)).isoformat()
        r["taches"][1]["maj"] = (M - timedelta(minutes=1)).isoformat()
        if modif:
            modif(r)
        return etat.construire(releve.normaliser(r), self.eq, M, fraicheur)

    def test_agent_au_travail(self):
        a = self.etat()["agents"]
        d1 = next(x for x in a if x["id"] == "d1")
        self.assertEqual((d1["statut"], d1["bulle"], d1["taches"], d1["service"], d1["lieu"]),
                         ("travail", "T", ["t1"], "dev", "local"))
        self.assertTrue(d1["prenom"])
        self.assertRegex(d1["couleur"], r"^#[0-9a-f]{6}$")

    def test_chef_toujours_la(self):
        chef = next(x for x in self.etat()["agents"] if x["chef"])
        self.assertIsNone(chef["service"])

    def test_agent_parti(self):
        e = self.etat(active=False, minutes=30 * 60)
        self.assertNotIn("d1", [x["id"] for x in e["agents"]])
        self.assertIsNone(next(t for t in e["taches"] if t["id"] == "t1")["agent"])

    def test_tache_a_son_agent(self):
        e = self.etat()
        self.assertEqual(next(t for t in e["taches"] if t["id"] == "t1")["agent"], "d1")

    def test_fraicheur_par_titulaire(self):
        def avec(r):
            r["titulaires"][0]["fraicheur_min"] = 90
        d1 = next(x for x in self.etat(minutes=60, modif=avec)["agents"] if x["id"] == "d1")
        self.assertEqual(d1["statut"], "travail")
        d1 = next(x for x in self.etat(minutes=60)["agents"] if x["id"] == "d1")
        self.assertEqual(d1["statut"], "sans_nouvelles")

    def test_modele(self):
        def releve_dit(r):
            r["titulaires"][0]["modele"] = "Sonnet"
        d1 = next(x for x in self.etat()["agents"] if x["id"] == "d1")
        self.assertEqual(d1["modele"], "?")
        d1 = next(x for x in self.etat(modif=releve_dit)["agents"] if x["id"] == "d1")
        self.assertEqual(d1["modele"], "Sonnet")
        (self.tmp / "equipe.json").write_text(
            '{"agents": {"d1": {"prenom": "Zoé", "couleur": "#000000", "modele": "Haiku"}}}', encoding="utf-8")
        self.eq = equipe.Equipe(self.tmp / "equipe.json")
        d1 = next(x for x in self.etat(modif=releve_dit)["agents"] if x["id"] == "d1")
        self.assertEqual((d1["modele"], d1["prenom"]), ("Haiku", "Zoé"))

    def test_erreur(self):
        e = etat.erreur("x", M)
        self.assertEqual((e["erreur"], e["agents"], e["factory"]["etat"]), ("x", [], "inconnu"))
        json.dumps(e)

    def test_lire_releve_absent_ne_plante_pas(self):
        e = etat.lire({"releve": {"fichier": "absent.json"}, "dossier": str(self.tmp), "fraicheur_min": 30},
                      self.eq, M)
        self.assertTrue(e["erreur"])

    def test_lire_releve_valide(self):
        (self.tmp / "r.json").write_text(json.dumps(BASE), encoding="utf-8")
        e = etat.lire({"releve": {"fichier": "r.json"}, "dossier": str(self.tmp), "fraicheur_min": 30},
                      self.eq, M)
        self.assertIsNone(e["erreur"])
        self.assertEqual(e["projet"], "P")

    def test_agents_locaux(self):
        # d1 local au travail, c1 cloud au travail, chef (local) ne compte pas
        self.assertEqual(etat.agents_locaux_au_travail(self.etat()), 1)

    def test_v1_inchange(self):
        e = self.etat(modif=lambda r: r.update(decisions=2))
        self.assertEqual(e["version"], 1)
        self.assertEqual(e["directeur"], {"lecons": 0, "retours": 0, "bloquees": 0, "total": 2})
        t1 = next(t for t in e["taches"] if t["id"] == "t1")
        for k in ("id", "titre", "colonne", "agent", "etape", "maj", "postit"):
            self.assertIn(k, t1)
        self.assertEqual((t1["colonne"], t1["agent"], t1["etape"], t1["postit"]), ("a", "d1", "", True))
        d1 = next(x for x in e["agents"] if x["id"] == "d1")
        self.assertEqual((d1["statut"], d1["bulle"], d1["taches"], d1["service"], d1["lieu"]),
                         ("travail", "T", ["t1"], "dev", "local"))
        self.assertEqual((d1["specialite"], d1["lecons"]), (None, []))
        self.assertEqual((e["actions"], e["types"], e["lecons"]), ([], [], []))

    def v2(self, modif=None, **kw):
        def m(r):
            r["version"] = 2
            if modif:
                modif(r)
        return self.etat(modif=m, **kw)

    def test_version_2(self):
        self.assertEqual(self.v2()["version"], 2)

    def test_prenom_du_releve(self):
        d1 = next(x for x in self.v2(lambda r: r["titulaires"][0].update(prenom="Maëlle", specialite="Tests"))
                  ["agents"] if x["id"] == "d1")
        self.assertEqual((d1["prenom"], d1["specialite"]), ("Maëlle", "Tests"))

    def test_prenom_utilisateur_prioritaire(self):
        (self.tmp / "equipe.json").write_text(
            '{"agents": {"d1": {"prenom": "Zoé", "couleur": "#000000"}}}', encoding="utf-8")
        self.eq = equipe.Equipe(self.tmp / "equipe.json")
        d1 = next(x for x in self.v2(lambda r: r["titulaires"][0].update(prenom="Maëlle"))["agents"]
                  if x["id"] == "d1")
        self.assertEqual(d1["prenom"], "Zoé")

    def test_prenom_releve_non_ecrit(self):
        self.v2(lambda r: r["titulaires"][0].update(prenom="Maëlle"))
        contenu = (self.tmp / "equipe.json").read_text(encoding="utf-8")
        self.assertNotIn("Maëlle", contenu)
        self.assertIn("d1", contenu)

    def test_lecons_du_titulaire(self):
        lecons = [{"id": "x", "texte": "t", "etat": "à valider"}]
        d1 = next(x for x in self.v2(lambda r: r["titulaires"][0].update(lecons=lecons))["agents"]
                  if x["id"] == "d1")
        self.assertEqual(d1["lecons"], lecons)

    def test_directeur_total(self):
        def m(r):
            r["decisions"] = 2
            r["titulaires"][0]["lecons"] = []
            r["lecons"] = [{"id": "l1", "agent": "d1", "texte": "t"}]
            r["taches"][0]["retours"] = [{"t": "1", "texte": "a"}, {"t": "2", "texte": "b", "reponse": "ok"}]
            r["taches"][1]["retours"] = [{"t": "3", "texte": "c", "reponse": ""}]
            r["taches"][1]["bloquee"] = "attend"
        e = self.v2(m)
        self.assertEqual(e["directeur"], {"lecons": 1, "retours": 2, "bloquees": 1, "total": 6})
        self.assertEqual(len(e["lecons"]), 1)

    def test_directeur_total_exemple_de_la_spec(self):
        def m(r):
            r["decisions"] = 2
            r["lecons"] = [{"id": "l1", "agent": "d1", "texte": "t"}]
            r["taches"][0]["retours"] = [{"t": "1", "texte": "a"}, {"t": "2", "texte": "b", "reponse": "ok"}]
            r["taches"][1]["bloquee"] = "attend"
        self.assertEqual(self.v2(m)["directeur"]["total"], 5)

    def test_journal_trie(self):
        def m(r):
            r["taches"][0]["journal"] = [{"t": "2026-11-10T08:00:00", "texte": "a"},
                                         {"t": "2026-11-10T10:00:00", "texte": "c"},
                                         {"t": "2026-11-10T09:00:00", "texte": "b"}]
            r["taches"][0].update(type="bug", bloquee="x", liens=[{"libelle": "L", "url": "https://x.org"}],
                                  images=[{"chemin": "a.png"}])
        t1 = next(t for t in self.v2(m)["taches"] if t["id"] == "t1")
        self.assertEqual([j["texte"] for j in t1["journal"]], ["c", "b", "a"])
        self.assertEqual((t1["type"], t1["bloquee"], len(t1["liens"]), len(t1["images"])),
                         ("bug", "x", 1, 1))

    def test_tache_active(self):
        e = self.etat(active=False)
        self.assertEqual({t["id"]: t["active"] for t in e["taches"]}, {"t1": False, "t2": True})

    def test_etat_json_serialisable(self):
        json.dumps(self.etat())

    def test_pause_les_perimes_sont_libres(self):
        def pause(r):
            r["factory"]["etat"] = "en pause"
        d1 = next(x for x in self.etat(minutes=120, modif=pause)["agents"] if x["id"] == "d1")
        self.assertEqual(d1["statut"], "libre")


if __name__ == "__main__":
    unittest.main()
