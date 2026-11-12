"""La mémoire à trois étages. Seuls des dépôts git temporaires et locaux sont utilisés (jamais un distant réel)."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bureau import releve
from orchestrateur import fiches, memoire
from tests.orch_aide import AvecProjet, RACINE

SKILL = """# Mémoire de la skill

## S1 — Relire avant de rendre
Rôles : dev
Date : 2026-11-01

Relire le travail avant de le rendre.

## S2 — Noter les décisions
Rôles : tous
Date : 2026-11-02

Noter chaque décision dans le suivi.

## S3 — Vérifier les captures
Rôles : qa, relecteur
Date : 2026-11-03

Comparer chaque capture à la maquette.
"""
GENRE_A = """# Genre : vitrine
Domaine : un site de présentation
Livrable : un site
Outils : html

## G1 — Textes courts
Rôles : tous
Date : 2026-11-04

Garder les textes d'accueil courts (leçon du genre A).
"""
GENRE_B = """# Genre : jeu-web
Domaine : un jeu dans le navigateur
Livrable : un jeu
Outils : canvas

## G1 — Boucle de jeu
Rôles : dev
Date : 2026-11-05

Séparer la boucle de jeu du dessin (leçon du genre B).
"""


def git(*args, cwd, entree=None):
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, input=entree, check=False)
    if p.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} : {(p.stdout + p.stderr).decode('utf-8', 'replace')}")
    return p.stdout.decode("utf-8", "replace").strip()


class AvecDepots(unittest.TestCase):
    """Un dépôt nu local et deux clones, comme deux orchestrateurs qui écrivent dans la mémoire."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        self.distant = self.tmp / "distant.git"
        git("init", "-q", "--bare", "-b", "main", str(self.distant), cwd=self.tmp)
        self.a = self.tmp / "a"
        git("init", "-q", "-b", "main", str(self.a), cwd=self.tmp)
        self.configurer(self.a)
        (self.a / "memoire" / "genres").mkdir(parents=True)
        (self.a / "memoire" / "skill.md").write_text(SKILL, encoding="utf-8")
        (self.a / "memoire" / "genres" / "vitrine.md").write_text(GENRE_A, encoding="utf-8")
        (self.a / "memoire" / "genres" / "jeu-web.md").write_text(GENRE_B, encoding="utf-8")
        git("add", "-A", cwd=self.a)
        git("commit", "-q", "-m", "départ", cwd=self.a)
        git("remote", "add", "origin", str(self.distant), cwd=self.a)
        git("push", "-q", "-u", "origin", "main", cwd=self.a)
        self.b = self.tmp / "b"
        git("clone", "-q", str(self.distant), str(self.b), cwd=self.tmp)
        self.configurer(self.b)
        self.ma, self.mb = self.a / "memoire", self.b / "memoire"

    @staticmethod
    def configurer(depot):
        git("config", "user.email", "test@example.org", cwd=depot)
        git("config", "user.name", "Test", cwd=depot)
        git("config", "pull.rebase", "true", cwd=depot)

    def nb_commits(self, depot):
        return int(git("rev-list", "--count", "HEAD", cwd=depot))

    def lecon(self, titre="Une leçon", texte="Un texte général.", roles=("tous",)):
        return {"titre": titre, "texte": texte, "roles": list(roles), "date": "2026-11-10"}


class TestMemoire(AvecDepots):
    def test_lire_par_role(self):
        ids = lambda m: [x["id"] for x in m]  # noqa: E731
        self.assertEqual(ids(memoire.lire(self.ma, None, "dev")["skill"]), ["S1", "S2"])
        self.assertEqual(ids(memoire.lire(self.ma, None, "qa")["skill"]), ["S2", "S3"])
        self.assertEqual(ids(memoire.lire(self.ma, None, "cadrage")["skill"]), ["S2"])
        s2 = memoire.lire(self.ma, None, "dev")["skill"][1]
        self.assertEqual((s2["titre"], s2["roles"], s2["date"]), ("Noter les décisions", ["tous"], "2026-11-02"))
        self.assertEqual(s2["texte"], "Noter chaque décision dans le suivi.")

    def test_genre_d_un_autre_projet_jamais_lu(self):
        a = memoire.lire(self.ma, "vitrine", "dev")["genre"]
        b = memoire.lire(self.ma, "jeu-web", "dev")["genre"]
        self.assertEqual([x["texte"] for x in a], ["Garder les textes d'accueil courts (leçon du genre A)."])
        self.assertEqual([x["texte"] for x in b], ["Séparer la boucle de jeu du dessin (leçon du genre B)."])
        self.assertEqual(memoire.lire(self.ma, "vitrine", "qa")["genre"][0]["id"], "G1")   # roles: tous
        self.assertEqual(memoire.lire(self.ma, "jeu-web", "qa")["genre"], [])   # roles: dev seulement

    def test_genre_nul(self):
        for genre in (None, "inconnu", "../skill", "", "A", 3):
            self.assertEqual(memoire.lire(self.ma, genre, "dev")["genre"], [], repr(genre))
        self.assertEqual(memoire.lire(self.tmp / "vide", None, "dev"), {"skill": [], "genre": []})

    def test_genres(self):
        (self.ma / "genres" / "LISEZMOI.md").write_text("# Le format\n", encoding="utf-8")
        self.assertEqual(memoire.genres(self.ma), [
            {"id": "jeu-web", "domaine": "un jeu dans le navigateur", "livrable": "un jeu", "outils": "canvas"},
            {"id": "vitrine", "domaine": "un site de présentation", "livrable": "un site", "outils": "html"}])

    def test_mot_interdit_accents_casse(self):
        self.assertEqual(memoire.normaliser_mot("Ville-Lumière  d'Été"), "ville lumiere d ete")
        self.assertEqual(memoire.mots_trouves("Les rues de VILLE LUMIERE", ["Ville-Lumière", "Autre"]), ["Ville-Lumière"])
        self.assertEqual(memoire.mots_trouves("la ville-lumière", ["ville lumiere"]), ["ville lumiere"])
        self.assertEqual(memoire.mots_trouves("rien à signaler", ["Ville-Lumière"]), [])
        avant = (self.ma / "skill.md").read_text(encoding="utf-8")
        n = self.nb_commits(self.a)
        ok, message = memoire.ajouter(self.ma, "skill", None, self.lecon(texte="Les rues de ville lumiere."),
                                      ["Ville-Lumière"])
        self.assertFalse(ok)
        self.assertIn("mot interdit", message)
        self.assertEqual((self.ma / "skill.md").read_text(encoding="utf-8"), avant)
        self.assertEqual(self.nb_commits(self.a), n)
        ok, _ = memoire.ajouter(self.ma, "skill", None, self.lecon(titre="Ville-Lumière"), ["ville lumiere"])
        self.assertFalse(ok)   # le titre est contrôlé aussi

    def test_ajout_commit_et_push(self):
        ok, message = memoire.ajouter(self.ma, "skill", None, self.lecon("Titre court", "Le texte."), [])
        self.assertTrue(ok, message)
        self.assertIn("## S4 — Titre court", (self.ma / "skill.md").read_text(encoding="utf-8"))
        self.assertEqual(git("log", "-1", "--format=%s", cwd=self.a), "Mémoire (skill) : Titre court")
        self.assertEqual(git("log", "-1", "--format=%s", cwd=self.distant), "Mémoire (skill) : Titre court")   # poussé
        ok, _ = memoire.ajouter(self.ma, "genre", "vitrine", self.lecon("Autre", "Autre texte.", ["dev"]), [])
        self.assertTrue(ok)
        lecons = memoire.lire(self.ma, "vitrine", "dev")["genre"]
        self.assertEqual([x["id"] for x in lecons], ["G1", "G2"])
        self.assertEqual(lecons[1]["roles"], ["dev"])
        self.assertEqual(git("status", "--porcelain", cwd=self.a), "")

    def test_ajout_refuse_sans_genre_ou_etage_projet(self):
        for etage, genre in (("projet", None), ("genre", None), ("genre", "inconnu"), ("skill-x", None)):
            ok, message = memoire.ajouter(self.ma, etage, genre, self.lecon(), [])
            self.assertFalse(ok, (etage, genre))
            self.assertTrue(message)
        self.assertEqual(git("status", "--porcelain", cwd=self.a), "")

    def test_conflit_arrete_sans_commit(self):
        # A change la ligne de S1 et pousse ; B change la même ligne dans un commit local jamais poussé.
        ligne = "Relire le travail avant de le rendre."
        (self.ma / "skill.md").write_text(SKILL.replace(ligne, "Version de A."), encoding="utf-8")
        git("commit", "-q", "-am", "A change S1", cwd=self.a)
        git("push", "-q", cwd=self.a)
        (self.mb / "skill.md").write_text(SKILL.replace(ligne, "Version de B."), encoding="utf-8")
        git("commit", "-q", "-am", "B change S1", cwd=self.b)
        avant = (self.mb / "skill.md").read_text(encoding="utf-8")
        n = self.nb_commits(self.b)
        ok, message = memoire.ajouter(self.mb, "skill", None, self.lecon(), [])
        self.assertFalse(ok)
        self.assertIn("pull --rebase", message)
        self.assertEqual((self.mb / "skill.md").read_text(encoding="utf-8"), avant)   # fichier inchangé
        self.assertEqual(self.nb_commits(self.b), n)   # aucun commit
        self.assertFalse((self.b / ".git" / "rebase-merge").exists())   # le rebase est abandonné
        self.assertFalse((self.b / ".git" / "rebase-apply").exists())
        self.assertEqual(git("status", "--porcelain", cwd=self.b), "")

    def test_pull_avant_ecriture(self):
        ok, _ = memoire.ajouter(self.ma, "skill", None, self.lecon("Leçon de A", "Texte de A."), [])
        self.assertTrue(ok)
        ok, message = memoire.ajouter(self.mb, "skill", None, self.lecon("Leçon de B", "Texte de B."), [])
        self.assertTrue(ok, message)
        texte = (self.mb / "skill.md").read_text(encoding="utf-8")
        self.assertIn("Leçon de A", texte)   # la leçon de l'autre clone est gardée
        self.assertIn("Leçon de B", texte)
        self.assertLess(texte.index("Leçon de A"), texte.index("Leçon de B"))
        self.assertIn("## S5 — Leçon de B", texte)   # S4 est celle de A : pas de doublon d'identifiant
        git("pull", "-q", cwd=self.a)
        self.assertEqual((self.ma / "skill.md").read_text(encoding="utf-8"), texte)

    def test_push_refuse_garde_le_commit_local(self):
        appels = []

        def git_qui_echoue_au_push(args, cwd):
            appels.append(args[0])
            if args[0] == "push":
                return 1, "rejeté (droits)"
            return memoire.executer_git(args, cwd)

        n = self.nb_commits(self.a)
        ok, message = memoire.ajouter(self.ma, "skill", None, self.lecon(), [], git=git_qui_echoue_au_push)
        self.assertTrue(ok, message)
        self.assertIn("n'est pas publiée", message)
        self.assertIn("rejeté (droits)", message)
        self.assertLessEqual(len(message), 400)
        self.assertNotIn("reset", appels)   # rien n'est défait
        self.assertIn("## S", (self.ma / "skill.md").read_text(encoding="utf-8").split("Relire le travail")[-1])
        self.assertEqual(self.nb_commits(self.a), n + 1)   # le commit local reste
        self.assertEqual(git("status", "--porcelain", cwd=self.a), "")

    def test_echec_du_commit_defait_tout(self):
        avant = (self.ma / "skill.md").read_text(encoding="utf-8")
        tete = git("rev-parse", "HEAD", cwd=self.a)

        def git_qui_echoue_au_commit(args, cwd):
            if args[0] == "commit":
                return 1, "refusé"
            return memoire.executer_git(args, cwd)

        ok, message = memoire.ajouter(self.ma, "skill", None, self.lecon(), [], git=git_qui_echoue_au_commit)
        self.assertFalse(ok)
        self.assertIn("git commit", message)
        self.assertEqual((self.ma / "skill.md").read_text(encoding="utf-8"), avant)
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.a), tete)
        self.assertEqual(git("status", "--porcelain", cwd=self.a), "")

    def test_depot_absent(self):
        ok, message = memoire.ajouter(self.tmp / "pas-un-depot", "skill", None, self.lecon(), [])
        self.assertFalse(ok)
        self.assertFalse((self.tmp / "pas-un-depot" / "skill.md").exists())

    def test_creer_genre(self):
        ok, message = memoire.creer_genre(self.ma, "jeu-3d", "Un jeu en trois dimensions", [])
        self.assertTrue(ok, message)
        g = {x["id"]: x for x in memoire.genres(self.ma)}["jeu-3d"]
        self.assertEqual(g["domaine"], "Un jeu en trois dimensions")
        self.assertEqual(git("log", "-1", "--format=%s", cwd=self.distant), "Mémoire (genre) : nouveau genre jeu-3d")
        self.assertFalse(memoire.creer_genre(self.ma, "jeu-3d", "Encore", [])[0])
        self.assertFalse(memoire.creer_genre(self.ma, "../x", "Un genre", [])[0])
        self.assertFalse(memoire.creer_genre(self.ma, "autre", "  ", [])[0])
        self.assertFalse(memoire.creer_genre(self.ma, "autre", "Ville-Lumière", ["ville lumiere"])[0])

    def test_decrire_genre_remplace_le_domaine(self):
        ok, message = memoire.decrire_genre(self.ma, "vitrine", "un site de présentation, et aussi des blogs", [])
        self.assertTrue(ok, message)
        g = {x["id"]: x for x in memoire.genres(self.ma)}["vitrine"]
        self.assertEqual(g["domaine"], "un site de présentation, et aussi des blogs")
        self.assertEqual(g["livrable"], "un site")
        self.assertIn("Garder les textes d'accueil courts", (self.ma / "genres" / "vitrine.md").read_text(encoding="utf-8"))
        self.assertFalse(memoire.decrire_genre(self.ma, "inconnu", "Un genre", [])[0])
        self.assertFalse(memoire.decrire_genre(self.ma, "vitrine", "  ", [])[0])
        self.assertFalse(memoire.decrire_genre(self.ma, "vitrine", "Ville-Lumière", ["ville lumiere"])[0])

    def test_creer_genre_identifiant_interdit(self):
        # L'identifiant devient un nom de fichier, un titre et un message de commit publics : il est contrôlé aussi.
        n = self.nb_commits(self.a)
        ok, message = memoire.creer_genre(self.ma, "secret-ville", "Une description sans rien", ["Secret Ville"])
        self.assertFalse(ok)
        self.assertIn("mot interdit", message)
        self.assertFalse((self.ma / "genres" / "secret-ville.md").exists())
        self.assertEqual(self.nb_commits(self.a), n)

    def test_mots_ligatures_et_chemins(self):
        self.assertEqual(memoire.mots_trouves("Le Cœur du projet", ["Coeur"]), ["Coeur"])
        self.assertEqual(memoire.mots_trouves("ex æquo", ["ex aequo"]), ["ex aequo"])
        self.assertEqual(memoire.mots_trouves(r"voir C:\Projets\Truc", ["C:/Projets/Truc"]), ["C:/Projets/Truc"])

    def test_skill_md_sans_projet(self):
        """Aucun motif d'un fichier de mots tenu hors du dépôt (variable MYIAFACTORY_MOTS) ne figure dans la mémoire."""
        chemin = os.environ.get("MYIAFACTORY_MOTS")
        if not chemin or not Path(chemin).is_file():
            self.skipTest("MYIAFACTORY_MOTS n'est pas défini")
        mots = [m.strip() for m in Path(chemin).read_text(encoding="utf-8-sig").splitlines() if m.strip()]
        reel = RACINE / "orchestrateur" / "memoire"
        for fichier in [reel / "skill.md", *sorted((reel / "genres").glob("*.md"))]:
            self.assertEqual(memoire.mots_trouves(fichier.read_text(encoding="utf-8"), mots), [], fichier.name)


def espion(appels, echecs=None):
    """Un `git` qui note chaque commande (`appels`), et en fait échouer certaines : {commande: sortie}."""
    echecs = echecs or {}

    def git_espion(args, cwd):
        appels.append(list(args))
        if args[0] in echecs:
            return 1, echecs[args[0]]
        return memoire.executer_git(args, cwd)

    return git_espion


class AvecArbreModifie(AvecDepots):
    """Le dépôt de la skill est celui où l'on développe : des fichiers modifiés n'empêchent jamais d'écrire une leçon."""

    def setUp(self):
        super().setUp()
        (self.a / "autre.txt").write_text("v1\n", encoding="utf-8")
        (self.a / "deux.txt").write_text("v1\n", encoding="utf-8")
        git("add", "-A", cwd=self.a)
        git("commit", "-q", "-m", "autres fichiers", cwd=self.a)
        git("push", "-q", cwd=self.a)
        git("pull", "-q", cwd=self.b)

    def salir(self):
        """Une modification non commitée, une autre déjà indexée, un fichier neuf : le travail d'un autre agent."""
        (self.a / "autre.txt").write_text("v2\n", encoding="utf-8")
        (self.a / "deux.txt").write_text("v2\n", encoding="utf-8")
        git("add", "deux.txt", cwd=self.a)
        (self.a / "neuf.txt").write_text("neuf\n", encoding="utf-8")

    def etat_du_travail(self):
        return git("status", "--porcelain", cwd=self.a)


class TestMemoireArbreModifie(AvecArbreModifie):
    def test_arbre_modifie_ecrit_sans_toucher_aux_autres_fichiers(self):
        self.salir()
        avant = self.etat_du_travail()
        n = self.nb_commits(self.a)
        appels = []
        ok, message = memoire.ajouter(self.ma, "skill", None, self.lecon(), [], git=espion(appels))
        self.assertTrue(ok, message)
        self.assertIn("poussée", message)
        self.assertEqual(self.nb_commits(self.a), n + 1)
        self.assertEqual(git("show", "--name-only", "--format=", "HEAD", cwd=self.a), "memoire/skill.md")
        self.assertEqual(self.etat_du_travail(), avant)   # autre.txt, deux.txt (indexé) et neuf.txt : intacts
        self.assertEqual((self.a / "autre.txt").read_text(encoding="utf-8"), "v2\n")
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.a), git("rev-parse", "HEAD", cwd=self.distant))
        self.assertFalse({"stash", "reset", "checkout", "restore"} & {c[0] for c in appels}, appels)
        self.assertNotIn(["add", "-A"], appels)
        self.assertEqual(git("stash", "list", cwd=self.a), "")

    def test_distant_sans_nouveau_pas_de_pull(self):
        self.salir()
        appels = []
        ok, message = memoire.ajouter(self.ma, "skill", None, self.lecon(), [], git=espion(appels))
        self.assertTrue(ok, message)
        verbes = [c[0] for c in appels]
        self.assertEqual(verbes.count("fetch"), 1)
        self.assertNotIn("pull", verbes)
        self.assertNotIn("rebase", verbes)

    def test_distant_en_avance_arbre_modifie_garde_le_commit_local(self):
        ok, _ = memoire.ajouter(self.mb, "skill", None, self.lecon("Leçon de B", "Texte de B."), [])
        self.assertTrue(ok)
        self.salir()
        avant = self.etat_du_travail()
        tete = git("rev-parse", "HEAD", cwd=self.a)
        appels = []
        ok, message = memoire.ajouter(self.ma, "skill", None, self.lecon("Leçon de A", "Texte de A."), [],
                                      git=espion(appels))
        self.assertTrue(ok, message)
        self.assertIn("n'est pas publiée", message)
        self.assertIn("nouveau", message)
        self.assertNotIn("pull", [c[0] for c in appels])   # pas de rebase : les autres modifications ne sont pas touchées
        self.assertEqual(git("rev-parse", "HEAD~1", cwd=self.a), tete)   # le commit local est posé sur l'ancien
        self.assertEqual(self.etat_du_travail(), avant)
        self.assertNotEqual(git("rev-parse", "HEAD", cwd=self.a), git("rev-parse", "HEAD", cwd=self.distant))

class TestMemoireRepublication(AvecArbreModifie):
    def test_republier_attend_que_l_arbre_soit_propre(self):
        memoire.ajouter(self.mb, "skill", None, self.lecon("Leçon de B", "Texte de B."), [])
        self.salir()
        memoire.ajouter(self.ma, "genre", "vitrine", self.lecon("Leçon de A", "Texte de A."), [])
        r = memoire.republier(self.ma)   # l'arbre a toujours des modifications : on réessaie plus tard
        self.assertTrue(r.ok)
        self.assertFalse(r.publie)
        self.assertIn("nouveau", r.message)
        git("add", "-A", cwd=self.a)   # l'autre agent a fini : il commite
        git("commit", "-q", "-m", "travail de l'autre agent", cwd=self.a)
        r = memoire.republier(self.ma)
        self.assertTrue(r.publie, r.message)
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.a), git("rev-parse", "HEAD", cwd=self.distant))
        self.assertIn("Leçon de A", (self.ma / "genres" / "vitrine.md").read_text(encoding="utf-8"))
        self.assertIn("Leçon de B", (self.ma / "skill.md").read_text(encoding="utf-8"))

    def test_republier_conflit_abandonne_le_rebase(self):
        memoire.ajouter(self.mb, "skill", None, self.lecon("Leçon de B", "Texte de B."), [])
        self.salir()
        memoire.ajouter(self.ma, "skill", None, self.lecon("Leçon de A", "Texte de A."), [])   # même fin de fichier
        git("add", "-A", cwd=self.a)
        git("commit", "-q", "-m", "travail de l'autre agent", cwd=self.a)
        r = memoire.republier(self.ma)
        self.assertFalse(r.publie)
        self.assertTrue(r.transitoire)
        self.assertIn("pull --rebase", r.message)
        self.assertFalse((self.a / ".git" / "rebase-merge").exists())
        self.assertFalse((self.a / ".git" / "rebase-apply").exists())
        self.assertEqual(git("status", "--porcelain", cwd=self.a), "")

    def test_republier_sans_rien_a_publier(self):
        r = memoire.republier(self.ma)
        self.assertTrue(r.ok and r.publie, r.message)

    def test_republier_push_refuse(self):
        memoire.ajouter(self.ma, "skill", None, self.lecon(), [], git=espion([], {"push": "rejeté (droits)"}))
        r = memoire.republier(self.ma, git=espion([], {"push": "rejeté (droits)"}))
        self.assertTrue(r.ok)
        self.assertFalse(r.publie)
        self.assertIn("rejeté (droits)", r.message)
        r = memoire.republier(self.ma)
        self.assertTrue(r.publie, r.message)

class TestMemoireLot(AvecArbreModifie):
    def test_fichier_de_memoire_modifie_refuse(self):
        (self.ma / "skill.md").write_text(SKILL + "\nUne retouche à la main.\n", encoding="utf-8")
        n = self.nb_commits(self.a)
        ok, message = memoire.ajouter(self.ma, "skill", None, self.lecon(), [])
        self.assertFalse(ok)
        self.assertIn("modifications non commitées", message)
        self.assertIn("skill.md", message)
        self.assertEqual(self.nb_commits(self.a), n)
        self.assertTrue((self.ma / "skill.md").read_text(encoding="utf-8").endswith("Une retouche à la main.\n"))
        r = memoire.ecrire_lecons(self.ma, [("skill", None, self.lecon())], [])[0]
        self.assertFalse(r.ok)
        self.assertFalse(r.transitoire)   # pas de réessai tout seul : il faut une main

    def test_fichier_de_memoire_indexe_refuse(self):
        (self.ma / "skill.md").write_text(SKILL + "\nIndexé.\n", encoding="utf-8")
        git("add", "memoire/skill.md", cwd=self.a)
        ok, message = memoire.ajouter(self.ma, "skill", None, self.lecon(), [])
        self.assertFalse(ok)
        self.assertIn("modifications non commitées", message)

    def test_lot_une_seule_synchronisation(self):
        memoire.ajouter(self.mb, "skill", None, self.lecon("Leçon de B", "Texte de B."), [])
        git("pull", "-q", cwd=self.a)
        n = self.nb_commits(self.a)
        appels = []
        lecons = [("skill", None, self.lecon(f"Leçon {i}", f"Texte {i}.")) for i in range(3)]
        lecons.append(("genre", "vitrine", self.lecon("Leçon de genre", "Texte de genre.")))
        resultats = memoire.ecrire_lecons(self.ma, lecons, [], git=espion(appels))
        self.assertEqual([r.ok for r in resultats], [True] * 4, [r.message for r in resultats])
        self.assertEqual([r.publie for r in resultats], [True] * 4)
        verbes = [c[0] for c in appels]
        self.assertEqual(verbes.count("fetch"), 1)
        self.assertLessEqual(verbes.count("pull"), 1)
        self.assertEqual(verbes.count("push"), 1)
        self.assertEqual(self.nb_commits(self.a), n + 4)
        ids = [x["id"] for x in memoire.lire(self.ma, None, "dev")["skill"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.a), git("rev-parse", "HEAD", cwd=self.distant))

    def test_lot_distant_en_avance_arbre_propre_un_seul_pull(self):
        memoire.ajouter(self.mb, "skill", None, self.lecon("Leçon de B", "Texte de B."), [])
        appels = []
        lecons = [("skill", None, self.lecon(f"Leçon {i}", f"Texte {i}.")) for i in range(3)]
        resultats = memoire.ecrire_lecons(self.ma, lecons, [], git=espion(appels))
        self.assertTrue(all(r.ok and r.publie for r in resultats))
        self.assertEqual([c[0] for c in appels].count("pull"), 1)
        self.assertIn("Leçon de B", (self.ma / "skill.md").read_text(encoding="utf-8"))

    def test_lot_chaque_lecon_garde_son_resultat(self):
        lecons = [("skill", None, self.lecon("Bonne", "Un texte général.")),
                  ("skill", None, self.lecon("Interdite", "Les rues de ville lumiere.")),
                  ("genre", "inconnu", self.lecon("Sans genre", "Texte.")),
                  ("skill", None, self.lecon("Autre bonne", "Un autre texte."))]
        r = memoire.ecrire_lecons(self.ma, lecons, ["ville lumiere"])
        self.assertEqual([x.ok for x in r], [True, False, False, True])
        self.assertIn("mot interdit", r[1].message)
        self.assertIn("Genre inconnu", r[2].message)
        self.assertFalse(r[1].transitoire)
        self.assertTrue(r[3].publie)

    def test_lot_push_refuse_toutes_les_lecons_ecrites_sont_en_attente(self):
        lecons = [("skill", None, self.lecon(f"Leçon {i}", f"Texte {i}.")) for i in range(2)]
        appels = []
        r = memoire.ecrire_lecons(self.ma, lecons, [], git=espion(appels, {"push": "rejeté (droits)"}))
        self.assertEqual([(x.ok, x.commite, x.publie) for x in r], [(True, True, False)] * 2)
        self.assertEqual([c[0] for c in appels].count("push"), 1)
        self.assertIn("rejeté (droits)", r[0].message)

    def test_fetch_impossible_ecrit_en_local(self):
        ok, message = memoire.ajouter(self.ma, "skill", None, self.lecon(), [],
                                      git=espion([], {"fetch": "réseau coupé", "push": "réseau coupé"}))
        self.assertTrue(ok, message)
        self.assertIn("n'est pas publiée", message)
        self.assertEqual(git("status", "--porcelain", cwd=self.a), "")

    def test_pull_en_echec_rien_n_est_ecrit_et_se_reessaie(self):
        memoire.ajouter(self.mb, "skill", None, self.lecon("Leçon de B", "Texte de B."), [])
        n = self.nb_commits(self.a)
        r = memoire.ecrire_lecons(self.ma, [("skill", None, self.lecon())], [],
                                  git=espion([], {"pull": "conflit"}))[0]
        self.assertFalse(r.ok)
        self.assertTrue(r.transitoire)
        self.assertIn("pull --rebase", r.message)
        self.assertEqual(self.nb_commits(self.a), n)


class TestMemoireCommandes(AvecProjet, AvecDepots):
    """Les commandes `memoire`, `genre`, `lecon`, `controle` de l'outil."""

    def setUp(self):
        AvecDepots.setUp(self)
        self._t2 = tempfile.TemporaryDirectory()
        self.addCleanup(self._t2.cleanup)
        self.dossier = Path(self._t2.name)
        from tests.orch_aide import factory_minimale
        self.factory = factory_minimale(self.dossier, memoire=str(self.ma), genre="vitrine",
                                        mots_interdits=["Ville-Lumière"])

    def fiche_lea(self):
        return fiches.lire_fiche(self.dossier / "fiches" / "lea.md")

    def noter(self, **extra):
        entree = {"action": "noter", "agent": "dev-1", "texte": "Relancer les tests.", "etage_propose": "projet"}
        entree.update(extra)
        return self.ok("lecon", entree=entree)

    def test_commande_memoire(self):
        m = self.ok("memoire", entree={"role": "dev"})
        self.assertEqual([x["id"] for x in m["skill"]], ["S1", "S2"])
        self.assertEqual([x["id"] for x in m["genre"]], ["G1"])
        self.assertEqual(self.outil("memoire", entree={})[0], 1)   # le rôle est obligatoire

    def test_lecon_projet_sur_fiche(self):
        i = self.noter()["id"]
        self.assertEqual(i, "dev-1:L1")
        self.assertEqual(self.fiche_lea()["lecons"][-1], {"etat": "à valider", "id": i, "texte": "Relancer les tests."})
        r = self.ok("releve")
        self.assertEqual(releve.valider(r), [], releve.valider(r))
        self.assertEqual([x["id"] for x in r["lecons"]], [i])
        self.assertEqual(r["lecons"][0]["etage_propose"], "projet")
        self.assertEqual([x["id"] for x in self.ok("etat")["lecons"]], [i])
        self.ok("lecon", entree={"action": "appliquer", "id": i, "verdict": "valider"})
        self.assertEqual(self.fiche_lea()["lecons"][-1]["etat"], "validée")
        r = self.ok("releve")
        self.assertEqual(r["lecons"], [])
        self.assertEqual(releve.valider(r), [])
        lea = next(t for t in r["titulaires"] if t["cle"] == "dev-1")
        self.assertEqual([x["etat"] for x in lea["lecons"]], ["validée", "validée"])
        self.assertEqual(self.outil("lecon", entree={"action": "appliquer", "id": i, "verdict": "valider"})[0], 1)

    def test_lecon_invalidee_disparait(self):
        i = self.noter()["id"]
        self.ok("lecon", entree={"action": "appliquer", "id": i, "verdict": "invalider"})
        self.assertEqual([x["id"] for x in self.fiche_lea()["lecons"]], ["dev-1:L0"])
        self.assertEqual(self.ok("etat")["lecons"], [])

    def test_noter_refuse(self):
        for extra in ({"etage_propose": "genre"},   # sans texte général
                      {"etage_propose": "inconnu"}, {"agent": "inconnu"}, {"roles": []}, {"texte": ""}):
            self.assertEqual(self.outil("lecon", entree={"action": "noter", "agent": "dev-1", "texte": "T",
                                                         "etage_propose": "projet", **extra})[0], 1, extra)
        self.assertEqual(self.outil("lecon", entree={"action": "autre"})[0], 1)

    def test_appliquer_genre_ok(self):
        i = self.noter(etage_propose="genre", texte_general="Toujours relancer les tests après un changement.",
                       roles=["dev"])["id"]
        self.ok("lecon", entree={"action": "appliquer", "id": i, "verdict": "valider"})
        self.assertEqual(self.fiche_lea()["lecons"][-1]["etat"], "validée")
        textes = [x["texte"] for x in memoire.lire(self.ma, "vitrine", "dev")["genre"]]
        self.assertIn("Toujours relancer les tests après un changement.", textes)
        self.assertEqual(git("log", "-1", "--format=%s", cwd=self.distant)[:15], "Mémoire (genre)")

    def test_etage_change_au_verdict(self):
        i = self.noter(etage_propose="genre", texte_general="Un conseil général.")["id"]
        self.ok("lecon", entree={"action": "appliquer", "id": i, "verdict": "valider", "etage": "skill"})
        self.assertIn("Un conseil général.", [x["texte"] for x in memoire.lire(self.ma, None, "dev")["skill"]])
        j = self.noter(texte="Locale")["id"]   # étage projet : jamais écrit dans le dépôt de la skill
        n = self.nb_commits(self.a)
        self.ok("lecon", entree={"action": "appliquer", "id": j, "verdict": "valider"})
        self.assertEqual(self.nb_commits(self.a), n)
        k = self.noter(texte="Locale 2")["id"]   # une leçon de projet ne peut pas viser un étage sans texte général
        self.assertEqual(self.outil("lecon", entree={"action": "appliquer", "id": k, "verdict": "valider",
                                                     "etage": "genre"})[0], 1)

    def test_appliquer_genre_echec_laisse_a_valider(self):
        i = self.noter(etage_propose="genre", texte_general="Les rues de la ville lumiere sont étroites.")["id"]
        n = self.nb_commits(self.a)
        code, sortie = self.outil("lecon", entree={"action": "appliquer", "id": i, "verdict": "valider"})
        self.assertEqual(code, 1)
        self.assertIn("mot interdit", sortie["erreur"])
        self.assertEqual(self.fiche_lea()["lecons"][-1]["etat"], "à valider")
        self.assertEqual([x["id"] for x in self.ok("etat")["lecons"]], [i])
        self.assertEqual(self.nb_commits(self.a), n)

    def test_appliquer_genre_sans_genre_au_projet(self):
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d["genre"] = None
        self.factory.write_text(json.dumps(d), encoding="utf-8")
        i = self.noter(etage_propose="genre", texte_general="Un conseil général.")["id"]
        code, sortie = self.outil("lecon", entree={"action": "appliquer", "id": i, "verdict": "valider"})
        self.assertEqual(code, 1)
        self.assertIn("genre", sortie["erreur"])

    # --- Le dépôt de la skill est un dépôt de développement : valider une leçon ne dépend pas de son état.

    def depot_en_travail(self):
        """Un fichier suivi, puis modifié sans commit : le travail d'un autre agent dans le dépôt de la skill."""
        (self.a / "autre.txt").write_text("v1\n", encoding="utf-8")
        git("add", "-A", cwd=self.a)
        git("commit", "-q", "-m", "autre", cwd=self.a)
        git("push", "-q", cwd=self.a)
        git("pull", "-q", cwd=self.b)
        (self.a / "autre.txt").write_text("v2\n", encoding="utf-8")

    def generale(self, texte="Un conseil général.", etage="skill", **extra):
        return self.noter(etage_propose=etage, texte_general=texte, **extra)["id"]

    def verdict(self, i, verdict="valider", **extra):
        return self.outil("lecon", entree={"action": "appliquer", "id": i, "verdict": verdict, **extra})

    def commiter_tout(self):
        git("add", "-A", cwd=self.a)
        git("commit", "-q", "-m", "travail de l'autre agent", cwd=self.a)

    def test_valider_avec_un_depot_en_travail(self):
        self.depot_en_travail()
        i = self.generale()
        code, r = self.verdict(i)
        self.assertEqual(code, 0, r)
        self.assertNotIn("en_attente", r)
        self.assertIn("Un conseil général.", [x["texte"] for x in memoire.lire(self.ma, None, "dev")["skill"]])
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.a), git("rev-parse", "HEAD", cwd=self.distant))
        self.assertEqual((self.a / "autre.txt").read_text(encoding="utf-8"), "v2\n")
        self.assertEqual(self.fiche_lea()["lecons"][-1]["etat"], "validée")
        releve_ = self.ok("releve")
        self.assertEqual(releve_["lecons"], [])
        self.assertEqual(releve_["lecons_en_attente"], [])
        self.assertEqual(releve.valider(releve_), [], releve.valider(releve_))

    def test_distant_en_avance_arbre_modifie_attend_puis_s_ecrit_seule(self):
        self.depot_en_travail()
        memoire.ajouter(self.mb, "skill", None, self.lecon("Leçon de B", "Texte de B."), [])
        i = self.generale("Un conseil du genre.", etage="genre")
        code, r = self.verdict(i)
        self.assertEqual(code, 0, r)
        self.assertTrue(r["en_attente"])
        self.assertIn("nouveau", r["raison"])
        releve_ = self.ok("releve")
        self.assertEqual(releve_["lecons"], [])   # elle a quitté la liste « à valider »
        self.assertEqual([(x["id"], x["etage"]) for x in releve_["lecons_en_attente"]], [(i, "genre")])
        self.assertIn("nouveau", releve_["lecons_en_attente"][0]["raison"])
        self.assertEqual(releve.valider(releve_), [], releve.valider(releve_))
        self.assertEqual([x["id"] for x in self.ok("etat")["lecons"]], [])
        self.assertEqual(self.verdict(i)[0], 1)   # elle n'est plus à valider
        # Tant que l'arbre a d'autres modifications, le réessai ne change rien et garde la raison.
        r = self.ok("lecon", entree={"action": "reessayer"})
        self.assertEqual((r["ecrites"], r["en_attente"]), (0, 1))
        self.assertEqual(len(self.ok("releve")["lecons_en_attente"]), 1)
        self.commiter_tout()
        r = self.ok("lecon", entree={"action": "reessayer"})
        self.assertEqual((r["ecrites"], r["en_attente"]), (1, 0))
        self.assertEqual(self.ok("releve")["lecons_en_attente"], [])
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.a), git("rev-parse", "HEAD", cwd=self.distant))
        self.assertIn("Un conseil du genre.", [x["texte"] for x in memoire.lire(self.ma, "vitrine", "dev")["genre"]])
        self.assertIn("Texte de B.", [x["texte"] for x in memoire.lire(self.ma, None, "dev")["skill"]])
        self.assertEqual(self.ok("lecon", entree={"action": "reessayer"})["en_attente"], 0)

    def test_push_refuse_met_la_lecon_en_attente_et_elle_s_ecrit_au_reessai(self):
        i = self.generale()
        with mock.patch("orchestrateur.outil.GIT", espion([], {"push": "rejeté (droits)"})):
            code, r = self.verdict(i)
        self.assertEqual(code, 0, r)
        self.assertTrue(r["en_attente"])
        self.assertIn("rejeté (droits)", r["raison"])
        self.assertEqual(self.fiche_lea()["lecons"][-1]["etat"], "validée")
        en_attente = self.ok("releve")["lecons_en_attente"]
        self.assertEqual([x["id"] for x in en_attente], [i])
        self.assertIn("rejeté (droits)", en_attente[0]["raison"])
        nb = self.nb_commits(self.a)
        r = self.ok("lecon", entree={"action": "reessayer"})   # le dépôt a déjà la leçon : il ne reste qu'à pousser
        self.assertEqual((r["ecrites"], r["en_attente"]), (1, 0))
        self.assertEqual(self.nb_commits(self.a), nb)   # pas de second commit de la même leçon
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.a), git("rev-parse", "HEAD", cwd=self.distant))

    def test_fichier_de_memoire_modifie_la_lecon_reste_a_valider_avec_la_raison(self):
        (self.ma / "skill.md").write_text(SKILL + "\nUne retouche.\n", encoding="utf-8")
        i = self.generale()
        code, r = self.verdict(i)
        self.assertEqual(code, 1)
        self.assertIn("modifications non commitées", r["erreur"])
        releve_ = self.ok("releve")
        self.assertEqual([x["id"] for x in releve_["lecons"]], [i])
        self.assertIn("modifications non commitées", releve_["lecons"][0]["refus"])
        self.assertEqual(releve_["lecons_en_attente"], [])
        self.assertEqual(releve.valider(releve_), [], releve.valider(releve_))
        git("checkout", "--", "memoire/skill.md", cwd=self.a)   # la main extérieure a fini : la leçon passe
        self.assertEqual(self.verdict(i)[0], 0)
        self.assertNotIn("refus", json.dumps(self.ok("releve")["lecons"]))

    def test_lot_une_synchronisation_et_un_resultat_par_lecon(self):
        self.depot_en_travail()
        a = self.generale("Premier conseil.")
        b = self.generale("Deuxième conseil.", etage="genre")
        c = self.generale("Les rues de la ville lumiere sont étroites.")
        d = self.noter(texte="Locale")["id"]
        e = self.generale("Cinquième conseil.")
        appels = []
        lot = [{"id": x, "verdict": "valider"} for x in (a, b, c, d, e)] + [{"id": "inconnue:L9", "verdict": "valider"}]
        with mock.patch("orchestrateur.outil.GIT", espion(appels)):
            r = self.ok("lecon", entree={"action": "appliquer", "lot": lot})
        par_id = {x["id"]: x for x in r["resultats"]}
        self.assertEqual([x["id"] for x in r["resultats"]], [x["id"] for x in lot])
        self.assertTrue(all(par_id[x]["ok"] for x in (a, b, d, e)), r)
        self.assertFalse(par_id[c]["ok"])
        self.assertIn("mot interdit", par_id[c]["refus"])
        self.assertFalse(par_id["inconnue:L9"]["ok"])
        verbes = [x[0] for x in appels]
        self.assertEqual((verbes.count("fetch"), verbes.count("pull"), verbes.count("push")), (1, 0, 1))
        self.assertEqual([x["id"] for x in self.ok("releve")["lecons"]], [c])   # la refusée reste, avec sa raison
        self.assertIn("mot interdit", self.ok("releve")["lecons"][0]["refus"])
        textes = [x["texte"] for x in memoire.lire(self.ma, None, "dev")["skill"]]
        self.assertIn("Premier conseil.", textes)
        self.assertIn("Cinquième conseil.", textes)
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.a), git("rev-parse", "HEAD", cwd=self.distant))

    def test_lot_deux_fois_la_meme_lecon(self):
        a = self.generale()
        r = self.ok("lecon", entree={"action": "appliquer", "lot": [{"id": a, "verdict": "valider"},
                                                                     {"id": a, "verdict": "valider"}]})
        self.assertEqual([x["ok"] for x in r["resultats"]], [True, False])
        self.assertEqual(sum(1 for x in memoire.lire(self.ma, None, "dev")["skill"] if x["texte"] == "Un conseil général."), 1)

    def test_reessayer_sans_attente_ne_touche_pas_au_depot(self):
        appels = []
        with mock.patch("orchestrateur.outil.GIT", espion(appels)):
            r = self.ok("lecon", entree={"action": "reessayer"})
        self.assertEqual((r["ecrites"], r["en_attente"]), (0, 0))
        self.assertEqual(appels, [])

    def test_genre_lister_et_fixer(self):
        self.ok("genre", entree={"action": "fixer", "genre": "jeu-web"})   # un genre connu, sans description
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        self.assertEqual(d["genre"], "jeu-web")
        self.assertEqual(d["mots_interdits"], ["Ville-Lumière"])   # le reste est gardé
        lister = self.ok("genre", entree={"action": "lister"})
        self.assertEqual(lister["genre"], "jeu-web")
        self.assertEqual([g["id"] for g in lister["genres"]], ["jeu-web", "vitrine"])

    def test_genre_fixer_nouveau(self):
        code, sortie = self.outil("genre", entree={"action": "fixer", "genre": "jeu-3d"})   # sans description
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(self.factory.read_text(encoding="utf-8"))["genre"], "vitrine")
        self.ok("genre", entree={"action": "fixer", "genre": "jeu-3d", "description": "Un jeu en trois dimensions"})
        self.assertEqual(json.loads(self.factory.read_text(encoding="utf-8"))["genre"], "jeu-3d")
        self.assertTrue((self.ma / "genres" / "jeu-3d.md").is_file())
        self.assertEqual(git("log", "-1", "--format=%s", cwd=self.distant), "Mémoire (genre) : nouveau genre jeu-3d")
        self.assertEqual(self.outil("genre", entree={"action": "fixer", "genre": "../x", "description": "d"})[0], 1)

    def test_genre_fixer_nouveau_echec_laisse_le_genre(self):
        d = json.loads(self.factory.read_text(encoding="utf-8"))
        d["mots_interdits"] = ["trois dimensions"]
        self.factory.write_text(json.dumps(d), encoding="utf-8")
        code, _ = self.outil("genre", entree={"action": "fixer", "genre": "jeu-3d", "description": "Un jeu en 3 dimensions et trois dimensions"})
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(self.factory.read_text(encoding="utf-8"))["genre"], "vitrine")

    def test_decision_confirmer_genre_connait_les_genres(self):
        self.ok("decision", entree={"action": "poser", "portee": "projet", "genre": "confirmer_genre",
                                    "texte": "Quel genre ?", "propose": "vitrine"})
        d = self.ok("etat")["decisions"][0]
        self.assertEqual(d["genres_connus"], ["jeu-web", "vitrine"])

    def test_controle(self):
        self.assertEqual(self.ok("controle", entree={"texte": "Vérifier les marges", "origine": "t1"})["numero"], 1)
        self.assertEqual(self.ok("controle", entree={"texte": "Vérifier les couleurs", "origine": "relecture"})["numero"], 2)
        registre = (self.dossier / "controles.md").read_text(encoding="utf-8")
        self.assertIn("Vérifier les marges", registre)
        self.assertIn("relecture", registre)
        self.assertEqual(self.outil("controle", entree={"texte": "x"})[0], 1)


if __name__ == "__main__":
    unittest.main()
