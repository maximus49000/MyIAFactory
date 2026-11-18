"""Le partage des connaissances : chiffrement, anonymisation, donnant-donnant. Dépôts git locaux et jetables seulement."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orchestrateur import anonymat, chiffre, connaissances, memoire

CLE_HEX = "ab" * 32
GENRE = "# Genre : vitrine\nDomaine : un site de présentation\nLivrable : un site\nOutils : html\n"


def git(*args, cwd):
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, check=False)
    if p.returncode != 0:
        raise AssertionError(p.stderr.decode("utf-8", "replace"))
    return p.stdout.decode("utf-8", "replace").strip()


class Chiffrement(unittest.TestCase):
    def test_aller_retour_autre_cle_et_jeton_abime(self):
        k = chiffre.lire_cle(CLE_HEX)
        j = chiffre.chiffrer(k, "Leçon : « relire » ✓")
        self.assertTrue(j.startswith("v1.") and "relire" not in j)
        self.assertEqual(chiffre.dechiffrer(k, j), "Leçon : « relire » ✓")
        self.assertNotEqual(j, chiffre.chiffrer(k, "Leçon : « relire » ✓"))   # un aléa par message
        with self.assertRaises(chiffre.JetonInvalide):
            chiffre.dechiffrer(chiffre.lire_cle("cd" * 32), j)
        abime = j[:-3] + ("A" if j[-3] != "A" else "B") + j[-2:]
        with self.assertRaises(chiffre.JetonInvalide):
            chiffre.dechiffrer(k, abime)
        with self.assertRaises(chiffre.CleInvalide):
            chiffre.lire_cle("1234")


class Anonymisation(unittest.TestCase):
    def test_le_filtre_efface_ce_qui_nomme_le_projet_et_garde_les_concepts(self):
        mots = anonymat.mots_du_projet(["Acme Logistique"], "RoadmapReborn", "roadmap-reborn",
                                       "https://github.com/jdupont/roadmap-reborn.git")
        texte = ("Dans Roadmap Reborn (client ACME logistique), l'export de planning_v2.py vers "
                 "C:\\Users\\jd\\Downloads\\x.xlsx plantait (ticket #482, tâche t64, commit 9f3a2b1c) ; voir "
                 "https://intra.acme.fr/doc ou écrire à jean.dupont@acme.fr depuis 10.0.0.12. Garder package.json "
                 "et la route /api/export/planning. jdupont l'a corrigé.")
        t, sortes = anonymat.filtrer(texte, mots)
        for interdit in ("Roadmap", "ACME", "acme", "planning_v2", "Users", "482", "t64", "9f3a2b1c", "intra",
                         "dupont", "10.0.0.12", "/api/export", "jdupont"):
            self.assertNotIn(interdit, t, t)
        for garde in ("l'export", "package.json", "plantait", "le projet"):
            self.assertIn(garde, t)
        self.assertIn("nom du projet", sortes)
        self.assertEqual(anonymat.reste_identifiant(t, mots), [])

    def test_la_relecture_se_lit_ou_se_refuse(self):
        self.assertEqual(anonymat.lire_relecture('Voici : {"titre": "T", "texte": "Règle générale."}'),
                         {"titre": "T", "texte": "Règle générale."})
        self.assertEqual(anonymat.lire_relecture('{"refus": "trop lié au métier"}'), {"refus": "trop lié au métier"})
        with self.assertRaises(ValueError):
            anonymat.lire_relecture("pas de json")


class Partage(unittest.TestCase):
    """Un dépôt « skill » (clone d'un distant nu), un dépôt privé de clé, et le dossier des connaissances du poste."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="partage-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        distant, self.skill = self.tmp / "distant.git", self.tmp / "skill"
        git("init", "-q", "--bare", "-b", "main", str(distant), cwd=self.tmp)
        git("clone", "-q", str(distant), str(self.skill), cwd=self.tmp)
        for k, v in (("user.name", "t"), ("user.email", "t@t.invalid"), ("commit.gpgsign", "false")):
            git("config", k, v, cwd=self.skill)
        self.memoire = self.skill / "memoire"
        (self.memoire / "genres").mkdir(parents=True)
        (self.memoire / "skill.md").write_text("# Mémoire de la skill\n", encoding="utf-8")
        (self.memoire / "genres" / "vitrine.md").write_text(GENRE, encoding="utf-8")
        git("add", "-A", cwd=self.skill)
        git("commit", "-q", "-m", "init", cwd=self.skill)
        git("push", "-q", "-u", "origin", "main", cwd=self.skill)
        self.distant = distant
        depot_cle = self.tmp / "cle"
        depot_cle.mkdir()
        git("init", "-q", "-b", "main", cwd=depot_cle)
        (depot_cle / "cle.txt").write_text(CLE_HEX + "\n", encoding="utf-8")
        git("-c", "user.name=t", "-c", "user.email=t@t.invalid", "add", "cle.txt", cwd=depot_cle)
        git("-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-q", "-m", "cle", cwd=depot_cle)
        self.poste = self.tmp / "poste"
        env = mock.patch.dict(os.environ, {"MYIAFACTORY_CONNAISSANCES": str(self.poste),
                                           "MYIAFACTORY_DEPOT_CLE": str(depot_cle)})
        env.start()
        self.addCleanup(env.stop)
        self.mots = anonymat.mots_du_projet(["Acme"], "RoadmapReborn", "roadmap-reborn")

    def lecon(self, titre="Relire RoadmapReborn", texte="Dans RoadmapReborn, relire l'export Acme avant livraison."):
        return ("skill", None, {"titre": titre, "texte": texte, "roles": ["tous"]})

    def distant_contient(self, mot):
        return mot in git("--git-dir", str(self.distant), "log", "-p", "--all", cwd=self.tmp)

    def test_refus_rien_ne_part_et_les_lecons_des_autres_sont_illisibles(self):
        # un autre bureau a partagé une leçon chiffrée
        memoire.ecrire_lecons(self.memoire, [("skill", None, {"titre": "Des autres", "texte": "Leçon d'un autre."})],
                              [], cle=chiffre.lire_cle(CLE_HEX))
        connaissances.regler(actif=False)
        avant = git("--git-dir", str(self.distant), "rev-parse", "main", cwd=self.tmp)
        r = connaissances.confier(self.memoire, [self.lecon()], self.mots)
        self.assertTrue(r[0].ok and r[0].publie)
        self.assertEqual(git("--git-dir", str(self.distant), "rev-parse", "main", cwd=self.tmp), avant)
        lues = connaissances.lire(self.memoire, None, "dev")["skill"]
        self.assertEqual([x["titre"] for x in lues], ["Relire RoadmapReborn"])   # la sienne, pas celle des autres
        self.assertFalse((self.poste / "cle").exists())
        self.assertEqual(connaissances.vue()["compte"]["locale"], 1)

    def test_standard_anonymise_chiffre_et_pousse(self):
        ok, _ = connaissances.regler(actif=True, niveau="standard")
        self.assertTrue(ok)
        connaissances.confier(self.memoire, [self.lecon()], self.mots)
        self.assertEqual(connaissances.entrees()[0]["etat"], "envoyee")
        for mot in ("RoadmapReborn", "Acme", "relire l'export"):
            self.assertFalse(self.distant_contient(mot), mot)   # ni en clair, ni dans le message de commit
        lues = memoire.lire(self.memoire, None, "dev", cle=chiffre.lire_cle(CLE_HEX))["skill"]
        self.assertEqual(lues[0]["texte"], "Dans le projet, relire l'export le projet avant livraison.")
        self.assertEqual(memoire.lire(self.memoire, None, "dev")["skill"], [])   # sans clé : rien
        self.assertEqual(len(connaissances.lire(self.memoire, None, "dev")["skill"]), 1)   # pas de doublon

    def test_renforce_relu_par_claude_et_surcout_compte(self):
        connaissances.regler(actif=True, niveau="renforce")
        connaissances.confier(self.memoire, [self.lecon()], self.mots)
        self.assertEqual(connaissances.entrees()[0]["etat"], "a_anonymiser")   # jamais envoyée sans relecture
        self.assertEqual(connaissances.vue()["surcout"]["par_lecon_usd"], connaissances.COUT_ESTIME_RELECTURE_USD)
        vus = []

        def reecrire(titre, texte):
            vus.append(texte)
            return {"titre": "Relire avant de livrer", "texte": "Relire chaque export avant livraison."}, 0.004
        bilan = connaissances.traiter(self.memoire, reecrire=reecrire)
        self.assertNotIn("RoadmapReborn", vus[0])   # Claude ne reçoit que le texte déjà filtré
        self.assertEqual(bilan["envoyees"], 1)
        s = connaissances.vue()["surcout"]
        self.assertEqual((s["relectures"], s["cout_usd"], s["par_lecon_usd"], s["estime"]), (1, 0.004, 0.004, False))

    def test_strict_et_reactivation_attendent_le_directeur(self):
        connaissances.regler(actif=False)
        connaissances.confier(self.memoire, [self.lecon()], self.mots)
        ok, message = connaissances.regler(actif=True, niveau="standard")
        self.assertIn("1 leçon(s) gardée(s)", message)
        connaissances.traiter(self.memoire)
        v = connaissances.vue()
        self.assertEqual(len(v["a_relire"]), 1)   # gardée pendant le refus : jamais envoyée sans validation
        self.assertNotIn("RoadmapReborn", v["a_relire"][0]["texte_partage"])
        i = v["a_relire"][0]["id"]
        ok, message = connaissances.valider(self.memoire, [i], {i: "Relire chaque export avant de livrer."})
        self.assertTrue(ok, message)
        self.assertEqual(connaissances.entrees()[0]["etat"], "envoyee")
        connaissances.regler(niveau="strict")
        connaissances.confier(self.memoire, [self.lecon("Autre", "Tester Acme sur mobile.")], self.mots)
        connaissances.traiter(self.memoire, reecrire=lambda t, x: ({"titre": t, "texte": x}, 0.0))
        self.assertEqual(connaissances.entrees()[1]["etat"], "a_relire")
        connaissances.ecarter([connaissances.entrees()[1]["id"]])
        self.assertEqual(connaissances.entrees()[1]["etat"], "ecartee")

    def test_activation_sans_acces_au_depot_de_cle(self):
        with mock.patch.dict(os.environ, {"MYIAFACTORY_DEPOT_CLE": str(self.tmp / "inexistant")}):
            ok, message = connaissances.regler(actif=True)
        self.assertFalse(ok)
        self.assertIsNone(connaissances.reglage()["actif"])
        self.assertIsNone(connaissances.cle())

    def test_genre_local_pendant_un_refus_puis_publie_avec_sa_lecon(self):
        connaissances.regler(actif=False)
        ok, _ = connaissances.creer_genre(self.memoire, "outil-interne", "Un outil interne d'Acme", self.mots)
        self.assertTrue(ok)
        self.assertFalse((self.memoire / "genres" / "outil-interne.md").exists())
        self.assertIn("outil-interne", [g["id"] for g in connaissances.genres(self.memoire)])
        connaissances.confier(self.memoire, [("genre", "outil-interne", {"titre": "T", "texte": "Garder simple."})],
                              self.mots)
        connaissances.regler(actif=True, niveau="standard")
        connaissances.traiter(self.memoire)
        i = connaissances.vue()["a_relire"][0]["id"]
        connaissances.valider(self.memoire, [i])
        self.assertIn("Domaine : Un outil interne d'le projet",
                      (self.memoire / "genres" / "outil-interne.md").read_text(encoding="utf-8"))
        self.assertFalse(self.distant_contient("Acme"))

    def test_chiffrer_le_depot_existant(self):
        (self.memoire / "skill.md").write_text("# Mémoire de la skill\n\n## S1 — Relire\nRôles : dev\nDate : 2026-11-01"
                                               "\n\nRelire avant de rendre.\n", encoding="utf-8")
        git("commit", "-q", "-am", "clair", cwd=self.skill)
        k = chiffre.lire_cle(CLE_HEX)
        ok, message = connaissances.chiffrer_depot(self.memoire, k)
        self.assertTrue(ok, message)
        texte = (self.memoire / "skill.md").read_text(encoding="utf-8")
        self.assertNotIn("Relire avant", texte)
        self.assertEqual(memoire.lire(self.memoire, None, "dev", cle=k)["skill"][0]["texte"], "Relire avant de rendre.")
        k2 = chiffre.lire_cle("cd" * 32)
        ok, _ = connaissances.chiffrer_depot(self.memoire, k2, ancienne=k)   # changement de clé
        self.assertTrue(ok)
        self.assertEqual(memoire.lire(self.memoire, None, "dev", cle=k)["skill"], [])
        self.assertEqual(len(memoire.lire(self.memoire, None, "dev", cle=k2)["skill"]), 1)


if __name__ == "__main__":
    unittest.main()
