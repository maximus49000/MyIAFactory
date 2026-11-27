"""Claude autonome revoit les anomalies du logiciel « nouvelles » depuis plus de 5 minutes (FM_Stats a27 : corrigée par la PR 112,
restée « nouvelle » : rien ne la désignait) : « Réglée » avec la PR si elle est fusionnée ET que le moteur tourne avec ; « Vue »
sinon ; rien si le moteur est plus ancien que la fusion."""
import time
import unittest
from datetime import datetime, timedelta
from unittest import mock

from moteur import regles
from tests import test_moteur_serie_reprise as tsr

PR112 = {"numero": 112, "titre": "Validation du service : pages du cahier ; brief serveur Python + commandes dédiées",
         "corps": "Anomalie a27 : le brief serveur impose Python (urllib, 20 s) pour FM_Stats.", "fusionne_le": 0.0}


class Revue(tsr.AvecValidation):
    def setUp(self):
        super().setUp()
        self.projet_avec_validation(flux=tsr.FLUX, elements=0)
        self.projet.claude_autonome = True
        self.etat = regles.nouvel_etat()
        self.maintenant = time.time()

    def anomalie(self, titre="Brief du testeur : Python et commandes dédiées", age_min=20):
        a = self.ok("anomalies", entree={"action": "ajouter", "titre": titre, "description": "Le brief devrait le dire."})["anomalie"]
        self.reecrire_date(a["id"], age_min)
        self.ident = a["id"]
        return a["id"]

    def reecrire_date(self, ident, age_min):
        import json
        chemin = self.dossier / "anomalies-logiciel.jsonl"
        lignes = [json.loads(x) for x in chemin.read_text(encoding="utf-8").splitlines() if x.strip()]
        for x in lignes:
            if x["id"] == ident:
                x["t"] = (datetime.now().astimezone() - timedelta(minutes=age_min)).isoformat(timespec="seconds")
        chemin.write_text("\n".join(json.dumps(x) for x in lignes) + "\n", encoding="utf-8")

    def revoir(self, prs, demarre_apres=True):
        pr = [dict(p, fusionne_le=self.maintenant - 600, corps=p["corps"].replace("a27", self.ident)) for p in prs]
        demarre = self.maintenant - 300 if demarre_apres else self.maintenant - 900     # moteur démarré après / avant la fusion
        self.etat.pop("revue_anomalies_le", None)
        self.etat.pop("prs_fusionnees", None)
        with mock.patch.object(regles, "_prs_fusionnees", return_value=pr), mock.patch.object(regles, "DEMARRE_LE", demarre):
            regles.repondre_en_autonome(self.projet, self.etat)

    def demandes(self):
        return [d for d in self.demande_en_attente() if d["type"] == "anomalie"]

    def test_pr_fusionnee_et_moteur_a_jour_reglee_avec_la_pr(self):
        a = self.anomalie()
        self.revoir([PR112])
        (d,) = self.demandes()
        self.assertEqual((d["anomalie"], d["etat"], d["claude_autonome"]), (a, "reglee", True))
        self.assertIn("PR 112", d["raison"])

    def test_pr_fusionnee_mais_moteur_plus_ancien_rien_n_est_fait(self):
        self.anomalie()
        self.revoir([PR112], demarre_apres=False)
        self.assertEqual(self.demandes(), [])

    def test_aucune_pr_vue_avec_la_raison_et_jamais_reglee(self):
        self.anomalie()
        self.revoir([])
        (d,) = self.demandes()
        self.assertEqual(d["etat"], "vue")
        self.assertIn("aucune PR fusionnée", d["raison"])

    def test_une_pr_qui_cite_un_autre_numero_ne_regle_pas(self):
        self.anomalie()
        self.revoir([dict(PR112, corps="a270 et a2 : autre chose pour FM_Stats.", titre="Autre")])
        (d,) = self.demandes()
        self.assertEqual(d["etat"], "vue")

    def test_une_anomalie_recente_n_est_pas_revue(self):
        self.anomalie(age_min=1)
        self.revoir([PR112])
        self.assertEqual(self.demandes(), [])

    def test_sans_claude_autonome_rien(self):
        self.anomalie()
        self.projet.claude_autonome = False
        self.revoir([PR112])
        self.assertEqual(self.demandes(), [])

    def test_une_anomalie_vue_n_est_pas_redemandee_et_reglee_quand_la_pr_arrive(self):
        a = self.anomalie()
        self.revoir([])
        self.revoir([])
        self.assertEqual(len(self.demandes()), 1)                    # « Vue » une seule fois par la revue
        regles.traiter_demande(self.projet, self.demandes()[0], self.etat)   # l'état passe à « vue » : plus « nouvelle »
        self.assertEqual(next(x for x in self.ok("anomalies")["anomalies"] if x["id"] == a)["etat"], "vue")

    def test_pr_citee_trouvee_dans_le_depot_par_pr_qui_corrige(self):
        a = {"id": "a27", "t": "2026-11-27T08:00:00+01:00", "projet": "FM_Stats"}
        ancien = dict(PR112, fusionne_le=datetime.fromisoformat("2026-11-26T08:00:00+01:00").timestamp())
        self.assertIsNone(regles._pr_qui_corrige(a, [ancien]))        # fusionnée avant la création de l'anomalie
        recent = dict(PR112, fusionne_le=datetime.fromisoformat("2026-11-27T09:00:00+01:00").timestamp())
        self.assertEqual(regles._pr_qui_corrige(a, [recent, ancien])["numero"], 112)


if __name__ == "__main__":
    unittest.main()
