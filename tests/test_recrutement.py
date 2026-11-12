"""Recruter des agents depuis le bureau (conception 2026-11-12-recrutement-design.md). git et gh sont simulés : aucun
dépôt réel n'est créé, rien n'est poussé."""
import json
import unittest
from pathlib import Path
from unittest import mock

from bureau import demandes, releve
from installation import creation
from moteur import agents, regles
from orchestrateur import factory as fa
from orchestrateur import fiches as fi
from orchestrateur import recrutement as rc
from tests.orch_aide import AvecProjet

FLUX_DA = [{"id": "dessin", "nom": "Dessin", "role": "graphiste", "service": "dev"},
           {"id": "da", "nom": "Validation de la DA", "validation": True},
           {"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"}]


class Executeur:
    """Un git ou un gh simulé : note les appels, répond comme demandé (clé : les deux premiers mots, ou le premier)."""

    def __init__(self, reponses=None, absent=False):
        self.appels, self.reponses, self.absent = [], reponses or {}, absent

    def __call__(self, args, cwd):
        self.appels.append(list(args))
        if self.absent:
            return 1, "n'a pas pu s'exécuter : introuvable"
        return self.reponses.get(" ".join(args[:2]), self.reponses.get(args[0], (0, "")))


def ecrire_origine(dossier, url):
    (Path(dossier) / ".git").mkdir(exist_ok=True)
    corps = "[core]\n\tbare = false\n" + (f'[remote "origin"]\n\turl = {url}\n\tfetch = +refs/heads/*\n' if url else "")
    (Path(dossier) / ".git" / "config").write_text(corps, encoding="utf-8")


class Depot(unittest.TestCase):
    def test_lu_dans_la_config_sans_lancer_git(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(rc.depot(d), {"git": False, "github": False, "origine": None, "url": None})
            self.assertIn("pas un dépôt git", rc.raison_sans_cloud(rc.depot(d)))
            ecrire_origine(d, None)
            self.assertEqual((rc.depot(d)["git"], rc.depot(d)["github"]), (True, False))
            self.assertIn("pas d'origine GitHub", rc.raison_sans_cloud(rc.depot(d)))
            ecrire_origine(d, "git@github.com:moi/jeu.git")
            self.assertEqual(rc.depot(d)["url"], "https://github.com/moi/jeu")
            self.assertIsNone(rc.raison_sans_cloud(rc.depot(d)))
            ecrire_origine(d, "https://gitlab.com/moi/jeu.git")
            self.assertFalse(rc.depot(d)["github"])
            self.assertIn("pas sur GitHub", rc.raison_sans_cloud(rc.depot(d)))

    def test_nom_de_depot(self):
        self.assertEqual(rc.nom_de_depot("Mon jeu d'été"), "Mon-jeu-d-t")
        self.assertEqual(rc.nom_de_depot("  "), "projet")


class Base(AvecProjet):
    def setUp(self):
        super().setUp()
        (self.dossier / "fiches" / "briefs").mkdir()
        for role in ("dev", "relecteur", "graphiste"):
            (self.dossier / "fiches" / "briefs" / f"{role}.md").write_text(f"Brief {role}.\n", encoding="utf-8")

    def releve(self):
        return self.ok("releve")

    def factory_avec(self, **extra):
        brut = json.loads(self.factory.read_text(encoding="utf-8"))
        brut.update(extra)
        self.factory.write_text(json.dumps(brut), encoding="utf-8")

    def fiches(self):
        return {x["cle"]: x for x in fi.lire_toutes(self.dossier / "fiches")}

    def serie(self, elements=3, flux=None):
        if flux is not None:
            self.factory_avec(flux=flux)
        self.ok("actions", entree={"type": "fonctionnalite", "texte": "Des écrans"})
        self.ok("fonctionnalite", entree={"id": "f1", "etape": "serie"})
        self.ok("file", entree={"fonctionnalite": "f1",
                                "elements": [{"id": f"e{i}", "nom": f"E{i}"} for i in range(elements)]})


class Repartition(Base):
    def test_travail_par_role_et_proposition_sans_github(self):
        self.serie(3)
        r = self.releve()["recrutement"]
        self.assertEqual(releve.valider(self.releve()), [])
        roles = {x["role"]: x for x in r["roles"]}
        self.assertEqual(list(roles), ["dev", "relecteur"])
        self.assertEqual((roles["dev"]["travail"], roles["dev"]["agents"], roles["dev"]["modele"]), (3, 1, "Sonnet"))
        # Pas de dépôt : tout en local, dans la limite des places locales (2 − 1 agent local hors chef = 1).
        self.assertEqual(r["places"], {"cloud": 0, "locaux": 0})
        self.assertEqual(r["propositions"], [])
        self.assertTrue(r["notes"])
        self.assertFalse(r["depot"]["github"])
        self.assertTrue(r["depot"]["creable"])
        self.assertIn("pas un dépôt git", r["cloud_impossible"])

    def test_cloud_d_abord_puis_local_jamais_au_dela(self):
        self.serie(5)
        ecrire_origine(self.dossier, "https://github.com/moi/jeu.git")
        self.ok("parallelisme", entree={"agents_locaux_max": 4, "agents_cloud_max": 2})
        r = self.releve()["recrutement"]
        self.assertEqual(r["places"], {"cloud": 2, "locaux": 2})     # 4 − Léa − Hugo
        self.assertEqual([(p["role"], p["lieu"]) for p in r["propositions"]],
                         [("dev", "cloud"), ("dev", "cloud"), ("dev", "local"), ("dev", "local")])
        self.assertIn("5 tâches", r["propositions"][0]["raison"])
        self.assertIn("celui de Léa", r["propositions"][0]["raison"])
        self.assertEqual(r["depot"]["url"], "https://github.com/moi/jeu")

    def test_les_premieres_propositions_ne_dependent_pas_du_nombre(self):
        self.serie(4)
        ecrire_origine(self.dossier, "git@github.com:moi/jeu.git")
        self.ok("parallelisme", entree={"agents_locaux_max": 3, "agents_cloud_max": 3})
        f, s = fa.lire(self.factory), json.loads((self.dossier / "suivi.json").read_text(encoding="utf-8"))
        tout = rc.proposer(f, s, list(self.fiches().values()), 3, True)["propositions"]
        self.assertEqual(rc.proposer(f, s, list(self.fiches().values()), 3, True, maximum=2)["propositions"], tout[:2])

    def test_la_barriere_retient_le_travail_apres_la_validation(self):
        self.serie(2, flux=FLUX_DA)
        (self.dossier / "fiches" / "gael.md").write_text(
            "Clé : graph-1\nPrénom : Gaël\nRôle : graphiste\nService : dev\nModèle : Opus\nLieu : local\n\nDessine.\n",
            encoding="utf-8")
        # Une tâche de développement prête, mais après la validation de la DA que les éléments en file n'ont pas passée.
        self.ok("tache", entree={"titre": "Dev e9", "fonctionnalite": "f1", "element": "e9", "role": "dev",
                                 "etape": "flux:dev", "active": False})
        travail = {x["role"]: x["travail"] for x in self.releve()["recrutement"]["roles"]}
        self.assertEqual(travail, {"graphiste": 2, "dev": 0})


class Outil(Base):
    def test_recrutement_manuel_local(self):
        r = self.ok("recruter", entree={"mode": "manuel", "agents": [{"role": "dev", "modele": "Haiku", "lieu": "local"}]})
        # Hugo et Léa sont déjà dans l'équipe : le prénom libre suivant est Lucas.
        self.assertEqual(r["agents"], [{"cle": "dev-2", "prenom": "Lucas", "role": "dev", "modele": "Haiku",
                                        "lieu": "local"}])
        x = self.fiches()["dev-2"]
        self.assertEqual((x["service"], x["texte"], x["fable"]), ("dev", "Développe les écrans.", None))
        self.assertEqual(self.ok("recruter", entree={"mode": "manuel", "agents": [
            {"role": "relecteur", "modele": "Sonnet", "lieu": "local"}]})["agents"][0]["cle"], "relecteur-1")

    def test_prenom_libre_de_l_equipe(self):
        self.ok("recruter", entree={"mode": "manuel", "agents": [{"role": "dev", "modele": "Sonnet", "lieu": "local"}]})
        r = self.ok("recruter", entree={"mode": "manuel", "agents": [{"role": "dev", "modele": "Sonnet", "lieu": "local"}]})
        self.assertEqual((r["agents"][0]["cle"], r["agents"][0]["prenom"]), ("dev-3", "Emma"))   # Hugo, Léa, Lucas pris

    def test_refus(self):
        cas = [({"mode": "manuel", "agents": [{"role": "inconnu", "modele": "Sonnet", "lieu": "local"}]}, "role"),
               ({"mode": "manuel", "agents": [{"role": "dev", "modele": "Fable", "lieu": "local"}]}, "Fable"),
               ({"mode": "manuel", "agents": [{"role": "dev", "modele": "GPT", "lieu": "local"}]}, "modele"),
               ({"mode": "manuel", "agents": [{"role": "dev", "modele": "Sonnet", "lieu": "cloud"}]}, "dépôt"),
               ({"mode": "manuel", "agents": [{"role": "dev", "modele": "Sonnet", "lieu": "local"}] * 2}, "un agent"),
               ({"mode": "auto", "agents": [{"role": "dev", "modele": "Sonnet", "lieu": "local"}]}, "places"),
               ({"mode": "autre", "agents": []}, "mode")]
        for entree, mot in cas:
            code, sortie = self.outil("recruter", entree=entree)
            self.assertEqual(code, 1, entree)
            self.assertIn(mot, sortie["erreur"], entree)
        self.assertEqual(sorted(self.fiches()), ["dev-1", "metier-1"])      # rien d'écrit

    def test_role_sans_brief_refuse(self):
        (self.dossier / "fiches" / "briefs" / "relecteur.md").unlink()
        code, sortie = self.outil("recruter", entree={"mode": "manuel", "agents": [
            {"role": "relecteur", "modele": "Sonnet", "lieu": "local"}]})
        self.assertEqual(code, 1)
        self.assertIn("brief", sortie["erreur"])

    def test_fable_avec_l_accord_du_directeur(self):
        r = self.ok("recruter", entree={"mode": "manuel", "agents": [
            {"role": "dev", "modele": "Fable", "lieu": "local", "fable": True}]})
        x = self.fiches()[r["agents"][0]["cle"]]
        self.assertTrue(fi.fable_accorde(x))

    def test_cloud_sur_github_dans_les_places(self):
        ecrire_origine(self.dossier, "https://github.com/moi/jeu")
        code, sortie = self.outil("recruter", entree={"mode": "manuel", "agents": [
            {"role": "dev", "modele": "Sonnet", "lieu": "cloud"}]})
        self.assertEqual(code, 1)
        self.assertIn("Agents cloud en même temps", sortie["erreur"])      # 0 place cloud
        self.ok("parallelisme", entree={"agents_locaux_max": 2, "agents_cloud_max": 1})
        r = self.ok("recruter", entree={"mode": "manuel", "agents": [{"role": "dev", "modele": "Sonnet", "lieu": "cloud"}]})
        self.assertEqual(self.fiches()[r["agents"][0]["cle"]]["lieu"], "cloud")
        self.assertEqual(self.outil("recruter", entree={"mode": "manuel", "agents": [
            {"role": "dev", "modele": "Sonnet", "lieu": "cloud"}]})[0], 1)        # la place est tenue
        self.assertEqual(self.releve()["recrutement"]["places"]["cloud"], 0)

    def test_auto_confirme_ecrit_tout(self):
        self.serie(4)
        ecrire_origine(self.dossier, "https://github.com/moi/jeu")
        self.ok("parallelisme", entree={"agents_locaux_max": 3, "agents_cloud_max": 1})
        props = self.releve()["recrutement"]["propositions"]
        self.assertEqual([p["lieu"] for p in props], ["cloud", "local"])
        r = self.ok("recruter", entree={"mode": "auto", "agents": [{k: p[k] for k in ("role", "modele", "lieu")}
                                                                    for p in props]})
        self.assertEqual(len(r["agents"]), 2)
        self.assertEqual(self.releve()["recrutement"]["places"], {"cloud": 0, "locaux": 0})


class Depot_git(Base):
    def creer(self, git, gh):
        with mock.patch("orchestrateur.outil.GIT", git), mock.patch("orchestrateur.outil.GH", gh):
            return self.outil("depot", entree={"action": "creer", "confirme": True})

    def test_sans_clic_rien(self):
        self.assertEqual(self.outil("depot", entree={"action": "creer"})[0], 1)

    def test_projet_sans_git(self):
        git, gh = Executeur({"remote get-url": (0, "https://github.com/moi/projet.git")}), Executeur()
        code, r = self.creer(git, gh)
        self.assertEqual(code, 0, r)
        self.assertTrue(r["fait"])
        self.assertEqual(r["url"], "https://github.com/moi/projet")
        self.assertEqual([a[0] for a in git.appels if a[0] != "config"][:3], ["init", "add", "commit"])
        creer = [a for a in gh.appels if a[:2] == ["repo", "create"]]
        self.assertEqual(len(creer), 1)
        self.assertIn("--private", creer[0])
        self.assertIn("--push", creer[0])
        self.assertIn(".env", (self.dossier / ".gitignore").read_text(encoding="utf-8"))
        essai = self.releve()["recrutement"]["depot"]["essai"]
        self.assertTrue(essai["fait"])

    def test_git_sans_origine_commit_si_besoin(self):
        ecrire_origine(self.dossier, None)
        git = Executeur({"diff --cached": (1, ""), "rev-parse --verify": (0, "abc")})
        code, r = self.creer(git, Executeur())
        self.assertEqual(code, 0, r)
        self.assertNotIn(["init"], git.appels)
        self.assertIn(["commit", "-m", creation.MESSAGE_PREMIER_COMMIT], git.appels)

    def test_gh_non_connecte(self):
        git, gh = Executeur(), Executeur({"auth status": (1, "You are not logged in")})
        code, r = self.creer(git, gh)
        self.assertEqual(code, 0)
        self.assertFalse(r["fait"])
        self.assertIn("gh auth login", r["texte"])
        self.assertEqual(git.appels, [])
        self.assertIn("gh auth login", self.releve()["recrutement"]["depot"]["essai"]["texte"])

    def test_gh_absent(self):
        code, r = self.creer(Executeur(), Executeur(absent=True))
        self.assertFalse(r["fait"])
        self.assertIn("pas installé", r["texte"])

    def test_origine_non_github_jamais_remplacee(self):
        ecrire_origine(self.dossier, "https://gitlab.com/moi/jeu.git")
        git, gh = Executeur({"remote get-url": (0, "https://gitlab.com/moi/jeu.git")}), Executeur()
        code, r = self.creer(git, gh)
        self.assertFalse(r["fait"])
        self.assertEqual(gh.appels, [])

    def test_deja_sur_github(self):
        ecrire_origine(self.dossier, "https://github.com/moi/jeu")
        git, gh = Executeur({"remote get-url": (0, "https://github.com/moi/jeu")}), Executeur()
        code, r = self.creer(git, gh)
        self.assertTrue(r["fait"])
        self.assertEqual(gh.appels, [])


RELEVE = {"version": 4, "recrutement": {
    "roles": [{"role": "dev", "nom": "Dev", "modele": "Sonnet", "agents": 1, "cloud": 0, "travail": 3}],
    "places": {"cloud": 1, "locaux": 1}, "propositions": [], "notes": [],
    "depot": {"git": False, "github": False, "url": None, "creable": True}, "cloud_impossible": "Pas de dépôt."}}


class Bureau(unittest.TestCase):
    def verifier(self, d, r=RELEVE):
        return demandes.verifier(demandes.nettoyer(d), r)

    def test_recruter(self):
        ok = {"type": "recruter", "mode": "manuel", "agents": [{"role": "dev", "modele": "Opus", "lieu": "local"}]}
        self.assertIsNone(self.verifier(ok))
        self.assertIn("dépôt", self.verifier({**ok, "agents": [{"role": "dev", "modele": "Opus", "lieu": "cloud"}]}))
        self.assertIn("Fable", self.verifier({**ok, "agents": [{"role": "dev", "modele": "Fable", "lieu": "local"}]}))
        self.assertIsNone(self.verifier({**ok, "agents": [{"role": "dev", "modele": "Fable", "lieu": "local",
                                                          "fable": True}]}))
        self.assertIn("role", self.verifier({**ok, "agents": [{"role": "x", "modele": "Opus", "lieu": "local"}]}))
        auto = {"type": "recruter", "mode": "auto", "agents": [{"role": "dev", "modele": "Opus", "lieu": "local"}] * 2}
        self.assertIn("places locales", self.verifier(auto))
        sur_github = json.loads(json.dumps(RELEVE))
        sur_github["recrutement"]["depot"]["github"] = True
        nuage = {**ok, "agents": [{"role": "dev", "modele": "Opus", "lieu": "cloud"}]}
        self.assertIsNone(self.verifier(nuage, sur_github))
        sur_github["recrutement"]["places"]["cloud"] = 0
        self.assertIn("places cloud", self.verifier(nuage, sur_github))
        # Le nettoyage ne laisse passer que rôle, modèle, lieu et accord Fable.
        d = demandes.nettoyer({**ok, "agents": [{"role": "dev", "modele": "Opus", "lieu": "local", "cle": "pirate"}]})
        self.assertEqual(d["agents"], [{"role": "dev", "modele": "Opus", "lieu": "local"}])

    def test_depot_git(self):
        self.assertIsNone(self.verifier({"type": "depot_git", "confirme": True}))
        self.assertIn("clic", self.verifier({"type": "depot_git", "confirme": "oui"}))
        deja = json.loads(json.dumps(RELEVE))
        deja["recrutement"]["depot"]["github"] = True
        self.assertIn("déjà", self.verifier({"type": "depot_git", "confirme": True}, deja))
        self.assertIn("recruter", self.verifier({"type": "recruter", "mode": "manuel", "agents": []}, {"version": 4}))

    def test_releve_controle_le_recrutement(self):
        erreurs = []
        releve._verifier_recrutement({"roles": "x", "places": {}, "propositions": [{"lieu": "lune"}],
                                      "depot": {}, "cloud_impossible": 3}, erreurs)
        self.assertEqual(len(erreurs), 5)


class Moteur(Base):
    def setUp(self):
        super().setUp()
        self.projet = regles.Projet(self.factory, feu_vert=lambda: True, prerequis=lambda: None)
        self.etat = regles.nouvel_etat()

    def traiter(self, **champs):
        i = self.ok("actions", entree=champs)["id"]
        d = next(x for x in self.ok("demandes")["demandes"] if x["id"] == i)
        return d, regles.traiter_demande(self.projet, d, self.etat)

    def statut(self, i):
        return next(x for x in json.loads((self.dossier / "suivi.json").read_text(encoding="utf-8"))["demandes"]
                    if x["id"] == i)

    def test_recruter_ecrit_la_fiche_et_repond(self):
        d, _ = self.traiter(type="recruter", mode="manuel", agents=[{"role": "dev", "modele": "Opus", "lieu": "local"}])
        self.assertEqual(self.statut(d["id"])["statut"], "traitée")
        self.assertIn("Lucas (dev, Opus, local)",self.statut(d["id"])["reponse"])
        self.assertIn("dev-2", self.fiches())

    def test_depot_git_par_le_moteur(self):
        git, gh = Executeur({"remote get-url": (0, "git@github.com:moi/p.git")}), Executeur()
        with mock.patch("orchestrateur.outil.GIT", git), mock.patch("orchestrateur.outil.GH", gh):
            d, _ = self.traiter(type="depot_git", confirme=True)
        self.assertIn("https://github.com/moi/p", self.statut(d["id"])["reponse"])

    def test_echec_du_lancement_cloud_pose_la_demarche_puis_c_est_fait_reprend(self):
        ecrire_origine(self.dossier, "https://github.com/moi/jeu")
        self.ok("parallelisme", entree={"agents_locaux_max": 2, "agents_cloud_max": 1})
        cle = self.ok("recruter", entree={"mode": "manuel", "agents": [
            {"role": "dev", "modele": "Sonnet", "lieu": "cloud"}]})["agents"][0]["cle"]
        tid = self.ok("tache", entree={"titre": "Écran", "role": "dev", "agent": cle, "active": True})["id"]
        depart = {"agent": cle, "taches": [tid], "matiere": "m", "modele": "sonnet", "lot": None}
        self.etat["departs"][tid] = depart
        self.etat["relancees"].add(tid)          # le second échec
        e = agents.Execution(tid, cle, None, erreur="session cloud : claude --cloud a rendu le code 1 : not logged in")
        regles._agent_en_echec(self.projet, self.etat, e, depart)
        s = json.loads((self.dossier / "suivi.json").read_text(encoding="utf-8"))
        decision = next(x for x in s["decisions_projet"] if x["genre"] == "session_cloud")
        self.assertEqual(decision["agent"], cle)
        self.assertIn("claude.ai/code", decision["texte"])
        self.assertIn("https://github.com/moi/jeu", decision["texte"])
        self.assertIn("not logged in", decision["texte"])
        regles._agent_en_echec(self.projet, self.etat, e, depart)        # une seule décision par agent
        s = json.loads((self.dossier / "suivi.json").read_text(encoding="utf-8"))
        self.assertEqual(sum(1 for x in s["decisions_projet"] if x["genre"] == "session_cloud"), 1)
        self.assertTrue(next(t for t in s["taches"] if t["id"] == tid)["bloquee"])
        d, _ = self.traiter(type="session_cloud", decision=decision["id"], session="Ma session")
        s = json.loads((self.dossier / "suivi.json").read_text(encoding="utf-8"))
        self.assertIsNone(next(t for t in s["taches"] if t["id"] == tid)["bloquee"])
        self.assertIn("repartent", self.statut(d["id"])["reponse"])
        self.assertNotIn(decision["id"], [x["id"] for x in s["decisions_projet"]])


if __name__ == "__main__":
    unittest.main()
