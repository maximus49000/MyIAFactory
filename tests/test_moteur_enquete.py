"""Le mode enquête de Claude autonome : quelques lectures en lecture seule, bornées, avant de répondre."""
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from moteur import jugement, regles
from tests import test_moteur_regles as tmr

REPONSE = {"raison": "Le journal montre la cause.", "verdict": "laisser", "texte": None, "generalisable": False,
           "lecon": None, "amelioration": None}
DOSSIER = {"decision": {"genre": "tache_bloquee"}, "verdicts": ["relancer", "laisser"], "mots_interdits": []}


def reponse(objet):
    return SimpleNamespace(texte="```json\n" + json.dumps(objet) + "\n```", usages=[])


class Juger(unittest.TestCase):
    def appeler(self, *suite):
        envoyes = []

        def f(consigne, texte, modele, couche=None):
            envoyes.append(json.loads(texte))
            return reponse(suite[min(len(envoyes), len(suite)) - 1])
        f.envoyes = envoyes
        return f

    def test_une_lecture_puis_la_reponse_avec_ce_qui_a_ete_lu(self):
        appeler = self.appeler({"lire": {"outil": "journal", "arg": ""}}, REPONSE)
        lecteur = mock.Mock(return_value="FileNotFoundError: /app/docs/style.json")
        d = jugement.juger("decider_autonome", DOSSIER, couche="claude", appeler=appeler, lecteur=lecteur)
        lecteur.assert_called_once_with("journal", "")
        self.assertNotIn("lectures", appeler.envoyes[0])
        self.assertEqual(appeler.envoyes[1]["lectures"][0]["resultat"], "FileNotFoundError: /app/docs/style.json")
        self.assertEqual(d.objet["lectures"][0]["outil"], "journal")
        self.assertEqual(d.objet["verdict"], "laisser")

    def test_au_plus_six_lectures_puis_une_question(self):
        appeler = self.appeler({"lire": {"outil": "commits", "arg": ""}})
        lecteur = mock.Mock(return_value="abc commit")
        d = jugement.juger("decider_autonome", DOSSIER, couche="claude", appeler=appeler, lecteur=lecteur)
        self.assertEqual(lecteur.call_count, jugement.LECTURES_MAX)
        self.assertIsNone(d.objet)
        self.assertIsNotNone(d.question)

    def test_sans_lecteur_ou_pour_un_autre_type_lire_n_est_pas_une_reponse(self):
        appeler = self.appeler({"lire": {"outil": "journal", "arg": ""}})
        d = jugement.juger("decider_autonome", DOSSIER, couche="claude", appeler=appeler)
        self.assertIsNotNone(d.question)
        self.assertEqual(len(appeler.envoyes), 2)

    def test_une_lecture_qui_echoue_est_dite_a_claude(self):
        appeler = self.appeler({"lire": {"outil": "fichier", "arg": "x"}}, REPONSE)
        lecteur = mock.Mock(side_effect=OSError("disque"))
        d = jugement.juger("decider_autonome", DOSSIER, couche="claude", appeler=appeler, lecteur=lecteur)
        self.assertIn("impossible", d.objet["lectures"][0]["resultat"])


class Outils(tmr.Base):
    def setUp(self):
        super().setUp()
        self.projet.claude_autonome = True
        self.racine = self.projet.dossier
        (self.racine / "docs").mkdir(exist_ok=True)
        (self.racine / "docs" / "note.md").write_text("Cause : image sans docs/. jeton: abc123", encoding="utf-8")
        (self.racine / ".env").write_text("API_KEY=zzz", encoding="utf-8")
        (self.racine / "secrets.json").write_text("{}", encoding="utf-8")
        self.lire = regles.lecteur_autonome(self.projet)

    def test_lit_un_fichier_du_depot_secrets_masques(self):
        texte = self.lire("fichier", "docs/note.md")
        self.assertIn("Cause : image sans docs/", texte)
        self.assertNotIn("abc123", texte)

    def test_refuse_les_secrets_les_chemins_hors_du_depot_et_le_git(self):
        for chemin in (".env", "secrets.json", "../autre.txt", "/etc/passwd", ".git/config", "cle.pem", "docs/../.env"):
            self.assertTrue(self.lire("fichier", chemin).startswith("refusé"), chemin)
        self.assertEqual(self.lire("fichier", "docs/absent.md"), "introuvable dans le dépôt")

    def test_outil_inconnu_ou_ecriture_refuses(self):
        for outil in ("ecrire", "bash", "deployer", ""):
            self.assertIn("outil inconnu", self.lire(outil, "x"))

    def test_page_et_journal_passent_par_les_faits_du_service(self):
        faits = {"pages": [{"chemin": "/sante", "code": 503, "ms": 40}], "journal": ["Traceback"]}
        with mock.patch.object(regles.service_permanent, "faits_du_service", return_value=faits) as f:
            self.assertIn("503", self.lire("page", "/sante"))
            self.assertEqual(self.lire("journal", ""), "Traceback")
            self.lire("page", "http://autre.test/")
        self.assertEqual(f.call_args_list[0].args[1], ["/sante"])
        self.assertEqual(f.call_args_list[-1].args[1], [])      # une adresse autre que le service n'est jamais interrogée

    def test_commits(self):
        with mock.patch.object(regles.service_permanent, "_git", return_value=(0, "abc1234 Corrige\n")):
            self.assertIn("abc1234", self.lire("commits", ""))

    def test_desactive_tout_est_refuse(self):
        self.projet.claude_autonome = False
        self.assertIn("désactivé", self.lire("fichier", "docs/note.md"))

    def test_le_dossier_liste_les_outils_et_les_lectures_vont_au_journal(self):
        self.assertEqual(set(regles.OUTILS_ENQUETE), {"fichier", "page", "journal", "commits", "rapport"})
        tid = self.ok("tache", entree={"titre": "T", "role": "dev", "etape": "x", "colonne": "dev"})["id"]
        regles._journal_des_lectures(self.projet, {"tache": tid}, {"lectures": [
            {"outil": "journal", "arg": "", "resultat": "Traceback FileNotFoundError"}]})
        textes = [j["texte"] for j in next(t for t in self.suivi()["taches"] if t["id"] == tid)["journal"]]
        self.assertTrue(any("a lu (journal" in x and "FileNotFoundError" in x for x in textes))


class BranchesAgent(tmr.Base):
    def git(self, *argv):
        import subprocess
        subprocess.run(["git", "-C", str(self.projet.dossier), "-c", "user.email=t@t.test", "-c", "user.name=T", *argv],
                       check=True, capture_output=True)

    def test_les_branches_agent_non_fusionnees_d_abord(self):
        self.git("init", "-q", "-b", "main")
        (self.projet.dossier / "a.txt").write_text("a", encoding="utf-8")
        self.git("add", "a.txt")
        self.git("commit", "-q", "-m", "base")
        self.git("branch", "agent/t1")                       # au même commit : fusionnée
        self.git("checkout", "-q", "-b", "agent/t2")
        (self.projet.dossier / "b.txt").write_text("b", encoding="utf-8")
        self.git("add", "b.txt")
        self.git("commit", "-q", "-m", "Catalogue : route")
        self.git("checkout", "-q", "main")                   # agent/t2 : jamais fusionnée
        b = regles.branches_agent(self.projet)
        self.assertEqual([(x["branche"], x["fusionnee"]) for x in b], [("agent/t2", False), ("agent/t1", True)])
        self.assertEqual(b[0]["sujet"], "Catalogue : route")

    def test_sans_depot_git_rien(self):
        self.assertEqual(regles.branches_agent(self.projet), [])

    def test_les_deux_dossiers_portent_les_branches(self):
        with mock.patch.object(regles, "branches_agent", return_value=[{"branche": "agent/t9", "fusionnee": False, "sujet": "x"}]):
            d = regles._dossier_autonome(self.projet, self.etat, {"id": "d1", "genre": "serie_arretee", "fonctionnalite": "f1",
                                                                  "texte": "x"})
        self.assertEqual(d["branches_agent"][0]["branche"], "agent/t9")


if __name__ == "__main__":
    unittest.main()
