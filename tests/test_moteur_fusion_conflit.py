"""Claude autonome et le conflit de fusion d'une branche d'agent (FM_Stats f31, agent/t289 : conflit add/add sur un document
de recette, une version fausse et une juste) : documentation seulement, borné, sans push ; du code est renvoyé au dev."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from moteur import cloud, jugement, regles
from tests import test_moteur_serie_reprise as tsr

JUSTE = "# Recette\nLe service répond 200 sur /sante.\n"
FAUSSE = "# Recette\nLe service renvoie 503 en permanence.\n"


class Depot(unittest.TestCase):
    """Un dépôt : la branche principale a docs/recette.md (version juste) ; agent/t289 en a une autre (fausse)."""

    def monter(self, d, avec_code=False, conflit_code=False):
        self.d = Path(d)
        self.git("init", "-q")
        self.git("config", "user.email", "x@x")
        self.git("config", "user.name", "x")
        self.git("config", "commit.gpgsign", "false")
        (self.d / "base.txt").write_text("base\n", encoding="utf-8")
        if conflit_code:
            (self.d / "app.py").write_text("x = 1\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")
        self.principale = self.git("rev-parse", "--abbrev-ref", "HEAD").stdout.decode().strip()
        self.git("checkout", "-q", "-b", "agent/t289")
        (self.d / "docs").mkdir(exist_ok=True)
        (self.d / "docs" / "recette.md").write_text(FAUSSE, encoding="utf-8")
        if avec_code:
            (self.d / "serveur.py").write_text("code = 1\n", encoding="utf-8")
        if conflit_code:
            (self.d / "app.py").write_text("x = 2\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "travail de l'agent")
        self.git("checkout", "-q", self.principale)
        (self.d / "docs").mkdir(exist_ok=True)
        (self.d / "docs" / "recette.md").write_text(JUSTE, encoding="utf-8")
        if conflit_code:
            (self.d / "app.py").write_text("x = 3\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "recette juste")

    def git(self, *a):
        return subprocess.run(["git", *a], cwd=self.d, capture_output=True)

    def lire(self, chemin):
        return (self.d / chemin).read_text(encoding="utf-8")


class Primitives(Depot):
    def setUp(self):
        self.addCleanup(shutil.rmtree, tempfile.mkdtemp(), ignore_errors=True)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        self.monter(d)

    def test_les_fichiers_en_conflit_et_les_deux_versions(self):
        self.assertEqual(cloud.fichiers_en_conflit(str(self.d), "agent/t289"), ["docs/recette.md"])
        self.assertEqual(cloud.fichiers_changes_par_la_branche(str(self.d), "agent/t289"), ["docs/recette.md"])
        self.assertIn("503", cloud.version_du_fichier(str(self.d), "agent/t289", "docs/recette.md"))
        self.assertIn("200", cloud.version_du_fichier(str(self.d), "HEAD", "docs/recette.md"))
        self.assertTrue(cloud.est_documentation("docs/recette.md"))
        self.assertFalse(cloud.est_documentation("serveur/app.py"))
        self.assertEqual(self.git("status", "--porcelain").stdout.decode().strip(), "")      # lecture seule

    def test_garder_le_depot_est_un_merge_ours_sans_push_ni_reecriture(self):
        avant = self.git("rev-parse", "HEAD").stdout.decode().strip()
        self.assertIsNone(cloud.fusion_bornee(str(self.d), "agent/t289", "depot"))
        self.assertEqual(self.lire("docs/recette.md"), JUSTE)
        self.assertEqual(self.git("merge-base", "--is-ancestor", "agent/t289", "HEAD").returncode, 0)
        parents = self.git("rev-list", "--parents", "-n", "1", "HEAD").stdout.decode().split()
        self.assertEqual(len(parents), 3)                                  # un commit de fusion
        self.assertEqual(parents[1], avant)                                # l'historique d'avant est intact
        self.assertEqual(self.git("remote").stdout.decode().strip(), "")  # jamais de push (pas même d'origine)

    def test_garder_la_branche_resout_le_passage_en_conflit_par_la_branche(self):
        self.assertIsNone(cloud.fusion_bornee(str(self.d), "agent/t289", "branche"))
        self.assertEqual(self.lire("docs/recette.md"), FAUSSE)

    def test_index_verrouille_rien_n_est_fait(self):
        (self.d / ".git" / "index.lock").write_text("", encoding="utf-8")
        self.assertIn("index.lock", cloud.fusion_bornee(str(self.d), "agent/t289", "depot"))
        self.assertEqual(self.lire("docs/recette.md"), JUSTE)

    def test_stategie_inconnue_refusee(self):
        self.assertIn("inconnue", cloud.fusion_bornee(str(self.d), "agent/t289", "tout"))


class PasQueDeLaDocumentation(Depot):
    def test_une_branche_qui_change_du_code_n_est_pas_ecartee_par_ours(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        self.monter(d, avec_code=True)
        avant = self.git("rev-parse", "HEAD").stdout.decode().strip()
        self.assertIn("documentation", cloud.fusion_bornee(str(self.d), "agent/t289", "depot"))
        self.assertEqual(self.git("rev-parse", "HEAD").stdout.decode().strip(), avant)
        self.assertFalse((self.d / "serveur.py").exists())

    def test_un_conflit_sur_du_code_n_est_jamais_resolu_seul(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        self.monter(d, conflit_code=True)
        avant = self.git("rev-parse", "HEAD").stdout.decode().strip()
        for strategie in ("depot", "branche"):
            self.assertIn("documentation", cloud.fusion_bornee(str(self.d), "agent/t289", strategie))
        self.assertEqual(self.git("rev-parse", "HEAD").stdout.decode().strip(), avant)


class BaseMoteur(tsr.AvecValidation, Depot):
    CODE = False

    def setUp(self):
        tsr.AvecValidation.setUp(self)
        self.projet_avec_validation(flux=tsr.FLUX, elements=0)
        self.monter(self.projet.dossier, conflit_code=self.CODE)
        self.tid = self.ok("tache", entree={"titre": "Recette du service", "fonctionnalite": "f1", "role": "dev",
                                            "etape": "flux:dev", "colonne": "fait", "active": False})["id"]
        self.etat = regles.nouvel_etat()
        self.projet.claude_autonome = True

    def conflit(self):
        with mock.patch.object(regles, "_analyser_le_blocage", return_value=[]):
            regles.fusion_impossible(self.projet, self.etat, self.tid, "agent-1", "agent/t289", None,
                                     "conflit de fusion : add/add docs/recette.md")

    def paroles(self):
        return [m["texte"] for m in self.suivi()["fonctionnalites"][0]["discussion"] if m["auteur"] == "chef"]

    def appliquer(self, action, o):
        _, type_, _, suite = action
        return regles.appliquer_jugement(self.projet, type_, jugement.Decision(objet=o), suite, self.etat)

    def objet(self, **plus):
        return {"raison": "La version du dépôt est plus complète et exacte.", "verdict": "garder_depot", "texte": None,
                "generalisable": False, "lecon": None, "amelioration": None, **plus}


class DansLeMoteur(BaseMoteur):
    def test_decoche_rien_n_est_fait(self):
        self.projet.claude_autonome = False
        self.conflit()
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])

    def test_claude_lit_les_deux_versions_et_choisit_sans_valider(self):
        self.conflit()
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        dossier = action[2]
        self.assertEqual(dossier["decision"]["genre"], "fusion_conflit")
        (f,) = dossier["fichiers_en_conflit"]
        self.assertEqual((f["chemin"], f["genre"]), ("docs/recette.md", "doc"))
        self.assertIn("200", f["version_du_depot"])
        self.assertIn("503", f["version_de_la_branche"])
        self.assertEqual(sorted(dossier["verdicts"]), ["garder_branche", "garder_depot", "laisser", "renvoyer"])
        self.assertEqual(regles.repondre_en_autonome(self.projet, self.etat), [])      # une seule tentative

    def test_garder_le_depot_fusionne_repond_c_est_regle_et_le_chef_le_dit_une_fois(self):
        self.conflit()
        avant = len(self.paroles())
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.appliquer(action, self.objet())
        (parole,) = self.paroles()[avant:]
        self.assertIn("gardant la version du dépôt", parole)
        (demande,) = [x for x in self.demande_en_attente() if x["type"] == "fusion_conflit"]
        self.assertTrue(demande["claude_autonome"])
        regles.traiter_demande(self.projet, demande, self.etat)
        self.assertEqual(self.lire("docs/recette.md"), JUSTE)
        reponses = [x for x in self.demande_en_attente() if x["type"] == "message"]
        self.assertTrue(any(x["texte"].startswith("C'est réglé, continuez") and x["claude_autonome"] for x in reponses))
        self.assertEqual(len(self.paroles()[avant:]), 1)


class DansLeMoteurCode(BaseMoteur):
    CODE = True

    def test_un_conflit_de_code_ne_propose_que_renvoyer_ou_laisser(self):
        self.conflit()
        (action,) = regles.repondre_en_autonome(self.projet, self.etat)
        self.assertEqual(sorted(action[2]["verdicts"]), ["laisser", "renvoyer"])
        self.assertIn("texte", jugement.valider("decider_autonome", self.objet(verdict="renvoyer"), action[2]))


if __name__ == "__main__":
    unittest.main()
