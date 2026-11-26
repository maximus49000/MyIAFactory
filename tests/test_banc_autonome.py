"""Le banc de cas rejoués de Claude autonome (`tests/banc_autonome/`) : chargeur, dossiers valides, réponses simulées
acceptées par le moteur, notation qui distingue le juste du faux. Aucun appel réel."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from moteur import jugement, regles
from tests import banc_autonome as banc

CAS = banc.charger()
DE_JUGEMENT = [c for c in CAS if c["type"] == "jugement"]


class Chargeur(unittest.TestCase):
    def test_les_dix_cas_reels_et_les_negatifs(self):
        self.assertEqual(len([c for c in CAS if not c["negatif"]]), 11)
        self.assertGreaterEqual(len([c for c in CAS if c["negatif"]]), 2)
        self.assertEqual(len({c["id"] for c in CAS}), len(CAS))

    def test_aucun_identifiant_reel(self):
        texte = " ".join(f.read_text(encoding="utf-8") for f in banc.DOSSIER_CAS.glob("*.json"))
        self.assertIsNone(re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", texte))
        self.assertNotIn("sk-", texte)
        self.assertNotIn("ghp_", texte)

    def test_un_cas_mal_forme_est_refuse(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "x.json").write_text(json.dumps({"id": "y"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                banc.charger(d)


class Rejeu(unittest.TestCase):
    def test_le_dossier_a_la_forme_que_construit_le_moteur(self):
        cles = {"decision", "verdicts", "choix", "questions", "tache", "fonctionnalite", "lecons_du_metier", "deja_appris",
                "recentes", "mots_interdits", "anomalies", "service"}
        for c in DE_JUGEMENT:
            with self.subTest(c["id"]):
                genre = c["dossier"]["decision"]["genre"]
                self.assertTrue(cles <= set(c["dossier"]))
                self.assertIn(genre, regles.VERDICTS_AUTONOMES)
                self.assertTrue(set(c["dossier"]["verdicts"]) <= set(regles.VERDICTS_AUTONOMES[genre]))
                self.assertTrue(set(c["attendu"]["verdicts"]) <= set(c["dossier"]["verdicts"]), "l'attendu doit être permis")

    def test_la_reponse_simulee_est_valide_notee_juste_et_appliquee(self):
        for c in DE_JUGEMENT:
            with self.subTest(c["id"]):
                self.assertIsNone(jugement.valider("decider_autonome", c["simule"], c["dossier"]))
                self.assertEqual(banc.noter(c, c["simule"]), (True, []))
                d = banc.decision_du_dossier(c)
                demande = regles._demande_autonome(d, c["simule"])
                self.assertEqual((demande["type"], demande["verdict"]), (d["genre"], c["simule"]["verdict"]))
                if c["simule"]["verdict"] == "renvoyer":
                    self.assertEqual(demande["tache_dev"], c["attendu"]["tache_dev"])

    def test_rejouer_toute_la_serie_simulee_est_juste(self):
        resultats = [banc.rejouer(c, lambda _d, c=c: c["simule"]) for c in CAS]
        self.assertEqual(banc.score(resultats), (len(CAS), len(CAS)), [r for r in resultats if not r["juste"]])

    def test_les_cas_hors_jugement_et_regle_du_moteur_tournent_sans_simule(self):
        for c in CAS:
            if c["type"] != "jugement":
                self.assertTrue(banc.rejouer(c, None)["juste"], c["id"])

    def test_la_regle_de_l_impasse_echoue_sans_la_decision_organisation(self):
        c = next(x for x in CAS if x["type"] == "moteur_impasse")
        sans = {**c, "dossier": {**c["dossier"], "etat_court": {**c["dossier"]["etat_court"], "decisions": []}}}
        self.assertFalse(banc.rejouer(sans, None)["juste"])


class Notation(unittest.TestCase):
    def cas(self, i):
        return next(c for c in CAS if c["id"].startswith(i))

    def test_les_mauvaises_reponses_sont_fausses(self):
        faux = {"02": {"verdict": "accepter", "texte": None},
                "03": {"verdict": "preciser", "texte": "Demande la base au Directeur."},
                "04": {"verdict": "laisser", "texte": None},
                "05": {"verdict": "renvoyer", "tache_dev": "t15", "texte": "Corrige."},
                "06": {"verdict": "renvoyer", "tache_dev": "t99", "texte": "style_graphiques : Dockerfile, test"},
                "09": {"verdict": "renvoyer", "tache_dev": "t15", "texte": "Corrige l'équipe 999."},
                "10": {"verdict": "preciser", "texte": "Relance.", "amelioration": None},
                "11": {"verdict": "accepter", "texte": None},
                "12": {"verdict": "choisir", "choix": "Souscrire"},
                "15": {"verdict": "relancer", "texte": "Réessaie."}}
        for i, o in faux.items():
            with self.subTest(i):
                self.assertFalse(banc.noter(self.cas(i), o)[0])

    def test_une_reponse_equivalente_est_juste(self):
        self.assertTrue(banc.noter(self.cas("02"), {"verdict": "choisir", "choix": "Non, ne pas déployer"})[0])
        self.assertTrue(banc.noter(self.cas("10"), {"verdict": "suivre", "amelioration": {"titre": "x", "description": "y"}})[0])

    def test_un_appel_qui_echoue_compte_faux(self):
        def casse(_d):
            raise RuntimeError("pas de réseau")
        self.assertFalse(banc.rejouer(DE_JUGEMENT[0], casse)["juste"])


if __name__ == "__main__":
    unittest.main()
