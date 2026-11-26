"""Un test (recette) ne part jamais sur un clone qui n'a pas le travail déjà fait : la branche agent/<tâche> d'une tâche
faite de la même fonctionnalité est fusionnée d'abord (essai réel FM_Stats f29 : le testeur concluait « code absent »)."""
import shutil
import subprocess
from unittest import mock

from moteur import regles
from tests import test_moteur_serie_reprise as tsr


class FusionAvantTest(tsr.AvecValidation):
    def setUp(self):
        super().setUp()
        self.projet_avec_validation(flux=tsr.FLUX, elements=0)
        self.git("init", "-q", "-b", "main")
        (self.projet.dossier / "base.txt").write_text("base", encoding="utf-8")
        self.git("add", "base.txt")
        self.git("commit", "-q", "-m", "base")
        self.dev = self.ok("tache", entree={"titre": "Catalogue", "fonctionnalite": "f1", "role": "dev", "etape": "flux:dev",
                                            "colonne": "dev", "active": False})["id"]
        self.ok("tache", entree={"id": self.dev, "colonne": "fait", "journal": ["Livré."]})
        self.git("checkout", "-q", "-b", f"agent/{self.dev}")
        (self.projet.dossier / "catalogue.py").write_text("code", encoding="utf-8")
        self.git("add", "catalogue.py")
        self.git("commit", "-q", "-m", "Catalogue")
        self.git("checkout", "-q", "main")
        self.recette = self.ok("tache", entree={"titre": "Recette", "fonctionnalite": "f1", "role": "testeur",
                                                "etape": "flux:essai", "colonne": "essai", "active": False})["id"]
        self.etat = regles.nouvel_etat()

    def git(self, *argv):
        subprocess.run(["git", "-C", str(self.projet.dossier), "-c", "user.email=t@t.test", "-c", "user.name=T", *argv],
                       check=True, capture_output=True)

    def la(self, tid):
        return next(t for t in self.suivi()["taches"] if t["id"] == tid)

    def paroles(self):
        return [m["texte"] for m in self.suivi()["fonctionnalites"][0]["discussion"] if m["auteur"] == "chef"]

    def fusion_reelle(self, dossier, branche, distante=True):
        self.git("merge", "--no-ff", "-q", "-m", "fusion", branche)
        return None

    def test_le_test_attend_la_branche_non_fusionnee(self):
        self.assertFalse(regles._amont_pret(self.projet, self.etat, self.la(self.recette)))
        self.assertEqual(self.etat["fusions_a_faire"], {self.recette: [f"agent/{self.dev}"]})

    def test_la_branche_est_fusionnee_dite_une_fois_puis_le_test_part(self):
        regles._amont_pret(self.projet, self.etat, self.la(self.recette))
        avant = len(self.paroles())
        with mock.patch.object(regles.cloud, "fusionner", side_effect=self.fusion_reelle) as f:
            regles.fusionner_avant_les_tests(self.projet, self.etat)
        f.assert_called_once()
        self.assertEqual(f.call_args.kwargs["distante"], False)
        self.assertEqual(len(self.paroles()[avant:]), 2)      # « pas fusionnée… » puis « j'ai fusionné… » : deux gestes
        self.assertTrue(any("n'est pas fusionnée" in str(j["texte"]) for j in self.la(self.recette)["journal"]))
        self.etat["branches_cache"] = {}
        self.assertTrue(regles._amont_pret(self.projet, self.etat, self.la(self.recette)))

    def test_une_fusion_qui_echoue_est_dite_comme_toute_fusion_impossible_et_non_retentee(self):
        regles._amont_pret(self.projet, self.etat, self.la(self.recette))
        with mock.patch.object(regles.cloud, "fusionner", return_value="conflit sur catalogue.py") as f, \
                mock.patch.object(regles, "fusion_impossible", return_value=[]) as impossible:
            regles.fusionner_avant_les_tests(self.projet, self.etat)
            self.etat["fusions_a_faire"] = {self.recette: [f"agent/{self.dev}"]}
            regles.fusionner_avant_les_tests(self.projet, self.etat)
        f.assert_called_once()
        impossible.assert_called_once()
        self.etat["branches_cache"] = {}
        self.assertFalse(regles._amont_pret(self.projet, self.etat, self.la(self.recette)))      # le test reste retenu

    def test_un_autre_metier_ou_une_branche_deja_fusionnee_ne_retient_rien(self):
        autre = dict(self.la(self.recette), role="dev")
        self.assertTrue(regles._amont_pret(self.projet, self.etat, autre))
        self.git("merge", "--no-ff", "-q", "-m", "fusion", f"agent/{self.dev}")
        self.etat["branches_cache"] = {}
        self.assertTrue(regles._amont_pret(self.projet, self.etat, self.la(self.recette)))

    # --- Une consigne qui cite une branche absente le dit à l'agent (FM_Stats a14 : agent/t289 jamais rapatriée).

    def test_la_consigne_dit_qu_une_branche_citee_n_existe_pas(self):
        texte = regles._avec_les_branches_verifiees(self.projet, "Reprends le travail de agent/t999 puis celui de agent/" + self.dev)
        self.assertIn("agent/t999 n'existe pas", texte)
        self.assertNotIn(f"agent/{self.dev} n'existe pas", texte)

    def test_branches_toutes_presentes_ou_aucune_citee_le_texte_est_intact(self):
        self.assertEqual(regles._avec_les_branches_verifiees(self.projet, f"Fusionne agent/{self.dev}."), f"Fusionne agent/{self.dev}.")
        self.assertEqual(regles._avec_les_branches_verifiees(self.projet, "Rien à citer."), "Rien à citer.")

    def test_sans_depot_git_le_texte_est_intact(self):
        shutil.rmtree(self.projet.dossier / ".git", ignore_errors=True)
        self.assertEqual(regles._avec_les_branches_verifiees(self.projet, "Voir agent/t1."), "Voir agent/t1.")
