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

    def test_colonne_terminee_servie(self):
        def avec(r):
            r["version"] = 2
            r["colonnes"] = [{"id": "a", "nom": "A"}, {"id": "f", "nom": "Fait", "terminee": True}]
        e = self.etat(modif=avec)
        self.assertEqual([c["terminee"] for c in e["colonnes"]], [False, True])
        self.assertNotIn("terminee", self.etat()["colonnes"][0])  # version 1 : rien de nouveau

    def test_suite_de_file_servie(self):
        def avec(r):
            r["version"] = 2
            r["file"] = {"visibles": [{"id": "q1", "titre": "Q"}], "suite": [{"id": "q2", "titre": "Q2"}], "reste": 4}
        self.assertEqual(self.etat(modif=avec)["file"]["suite"], [{"id": "q2", "titre": "Q2"}])
        self.assertEqual(self.etat(modif=lambda r: r.update(version=2))["file"]["suite"], [])
        self.assertNotIn("suite", self.etat()["file"])  # version 1 : rien de nouveau

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

    def test_dossier_ce_que_le_releve_fournit(self):
        rien = {"facturation": False, "kpi": False, "connaissances": False}
        self.assertEqual(self.etat()["dossier"], rien)
        self.assertEqual(self.v2()["dossier"], rien)
        self.assertEqual(etat.erreur("x", M)["dossier"], rien)

        def v3(modif=None):
            def m(r):
                r["version"] = 3
                if modif:
                    modif(r)
            return self.etat(modif=m)["dossier"]

        self.assertEqual(v3(), rien)
        usage = {"id": "u1", "tache": "t1", "agent": "d1", "modele": "m", "t": M.isoformat(),
                 "entree": 1, "sortie": 1}
        self.assertEqual(v3(lambda r: r.update(usage=[usage])), {**rien, "facturation": True})
        self.assertEqual(v3(lambda r: r["services"][0].update(kpi=[]))["kpi"], True)
        self.assertEqual(v3(lambda r: r["titulaires"][0].update(connaissances=[]))["connaissances"], True)
        self.assertEqual(v3(lambda r: r.update(challenges=[]))["connaissances"], True)

    def v3(self, modif=None, **kw):
        def m(r):
            r["version"] = 3
            if modif:
                modif(r)
        return self.etat(modif=m, **kw)

    def test_etat_fusionne_lecons_validees(self):
        def m(r):
            r["titulaires"][0]["lecons"] = [{"id": "l1", "texte": "Leçon validée", "etat": "validée"},
                                            {"id": "l2", "texte": "En attente", "etat": "à valider"},
                                            {"id": "k1", "texte": "Ancienne version", "etat": "validée"}]
            r["titulaires"][0]["connaissances"] = [{"id": "k1", "texte": "Connaissance", "date": "2026-11-08"}]
        e = self.v3(m)
        d1 = next(x for x in e["agents"] if x["id"] == "d1")
        par_id = {c["id"]: c for c in d1["connaissances"]}
        self.assertEqual(set(par_id), {"k1", "l1"})
        self.assertEqual(par_id["k1"]["texte"], "Connaissance")  # la connaissance l'emporte
        self.assertEqual((par_id["l1"]["texte"], par_id["l1"]["lecon"]), ("Leçon validée", True))
        self.assertFalse(par_id["k1"]["lecon"])
        self.assertTrue(e["dossier"]["connaissances"])

    def test_lecon_validee_seule_ouvre_l_onglet_en_v3(self):
        def m(r):
            r["titulaires"][0]["lecons"] = [{"id": "l1", "texte": "a", "etat": "validée"}]
        self.assertTrue(self.v3(m)["dossier"]["connaissances"])
        self.assertFalse(self.v2(m)["dossier"]["connaissances"])

    def test_etat_marque_partagee(self):
        def m(r):
            r["titulaires"][1]["prenom"] = "Hugo"
            r["titulaires"][0]["connaissances"] = [
                {"id": "k1", "texte": "a", "appris_de": [{"agent": "c1", "tache": "t2", "retour": "2026-11-07"}]},
                {"id": "k2", "texte": "b"}]
        d1 = next(x for x in self.v3(m)["agents"] if x["id"] == "d1")
        par_id = {c["id"]: c for c in d1["connaissances"]}
        self.assertTrue(par_id["k1"]["partagee"])
        self.assertFalse(par_id["k2"]["partagee"])
        source = par_id["k1"]["appris_de"][0]
        self.assertEqual((source["prenom"], source["service"], source["titre"]), ("Hugo", "qa", "U"))

    def test_probleme_revenu(self):
        from bureau import kpi
        alertes = kpi.HistoriqueAlertes(self.tmp / "alertes.jsonl")

        def m(r):
            r["services"][0]["kpi"] = [{"id": "defauts", "nom": "D", "valeur": 2, "alerte": True}]
            r["titulaires"][0]["connaissances"] = [
                {"id": "k1", "texte": "a", "date": "2026-11-01", "origine": "ch1"},
                {"id": "k2", "texte": "b", "date": "2026-11-20", "origine": "ch1"},   # plus récente que l'alerte
                {"id": "k3", "texte": "c", "date": "2026-11-01", "origine": "ch2"},   # challenge sur autre chose
                {"id": "k4", "texte": "d", "date": "2026-11-01", "origine": "texte libre"}]
            r["challenges"] = [{"id": "ch1", "cible": {"type": "kpi", "id": "kpi:dev:defauts"}, "texte": "c"},
                               {"id": "ch2", "cible": {"type": "connaissance", "id": "k1"}, "texte": "c"}]

        def lire(avec):
            r = copy.deepcopy(BASE)
            r["version"] = 3
            m(r)
            e = etat.construire(releve.normaliser(r), self.eq, M, 30, alertes=avec)
            return {c["id"]: c["probleme_revenu"] for c in e["agents"][0]["connaissances"]}, e

        sans, _ = lire(None)
        self.assertEqual(set(sans.values()), {False})  # sans historique : jamais « revenu »
        marques, e = lire(alertes)
        self.assertEqual(marques, {"k1": True, "k2": False, "k3": False, "k4": False})
        # La page lit la même information dans `savoir`.
        self.assertTrue(next(c for c in e["savoir"][0]["connaissances"] if c["id"] == "k1")["probleme_revenu"])

    def test_challenges_servis(self):
        ch = {"id": "ch1", "cible": {"type": "connaissance", "id": "k1"}, "texte": "c",
              "solutions": [{"id": "s1", "texte": "x", "auteur": "directeur"}]}
        e = self.v3(lambda r: r.update(challenges=[ch]))
        self.assertEqual(e["challenges"][0]["solutions"][0]["id"], "s1")
        self.assertEqual(self.v2()["challenges"], [])
        self.assertEqual(etat.erreur("x", M)["challenges"], [])
        self.assertEqual(etat.erreur("x", M)["savoir"], [])

    def test_savoir_garde_les_agents_partis(self):
        # Un agent parti du bureau (non permanent, sans tâche récente) garde ses connaissances dans le dossier.
        def m(r):
            r["taches"] = [r["taches"][1]]
            r["titulaires"][0]["connaissances"] = [{"id": "k1", "texte": "a"}]
        e = self.v3(m)
        self.assertNotIn("d1", [a["id"] for a in e["agents"]])
        d1 = next(s for s in e["savoir"] if s["agent"] == "d1")
        self.assertEqual((d1["service"], d1["present"], [c["id"] for c in d1["connaissances"]]),
                         ("dev", False, ["k1"]))
        c1 = next(s for s in e["savoir"] if s["agent"] == "c1")
        self.assertEqual((c1["present"], c1["connaissances"]), (True, []))

    def test_prenom_du_releve(self):
        d1 = next(x for x in self.v2(lambda r: r["titulaires"][0].update(prenom="Maëlle", specialite="Tests"))
                  ["agents"] if x["id"] == "d1")
        self.assertEqual((d1["prenom"], d1["specialite"]), ("Maëlle", "Tests"))

    def test_prenom_du_releve_remplace_celui_du_fichier(self):
        (self.tmp / "equipe.json").write_text(
            '{"agents": {"d1": {"prenom": "Zoé", "couleur": "#000000"}}}', encoding="utf-8")
        self.eq = equipe.Equipe(self.tmp / "equipe.json")
        d1 = next(x for x in self.v2(lambda r: r["titulaires"][0].update(prenom="Maëlle"))["agents"]
                  if x["id"] == "d1")
        self.assertEqual(d1["prenom"], "Maëlle")

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

    def test_notes_et_etat_des_retours_servis(self):
        def m(r):
            r["taches"][0]["notes"] = [{"libelle": "À savoir", "texte": "ligne 1\nligne 2"}]
            r["taches"][0]["retours"] = [{"t": "1", "texte": "a", "etat": "nouveau"}]
        e = self.v2(m)
        t1 = next(t for t in e["taches"] if t["id"] == "t1")
        self.assertEqual(t1["notes"], [{"libelle": "À savoir", "texte": "ligne 1\nligne 2"}])
        self.assertEqual(t1["retours"][0]["etat"], "nouveau")
        t2 = next(t for t in e["taches"] if t["id"] == "t2")
        self.assertEqual(t2["notes"], [])

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
