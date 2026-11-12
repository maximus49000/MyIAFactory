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
        self.assertIn("Sonnet : code courant de 5 éléments", r["propositions"][0]["raison"])
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


FLUX_TRIPLE = [{"id": "concept", "nom": "Conception du niveau", "role": "architecte", "service": "dev"},
               {"id": "dev", "nom": "Développement", "role": "dev", "service": "dev"},
               {"id": "tests", "nom": "Tests", "role": "testeur", "service": "dev"},
               {"id": "etape", "nom": "Étape", "role": "inconnu", "service": "dev"}]


def tache(i, role, etape, **extra):
    return {"id": f"t{i}", "titre": f"Tâche {i}", "fonctionnalite": "f1", "element": f"e{i}", "role": role,
            "colonne": "a_faire", "active": False, "bloquee": None, "etape": f"flux:{etape}", "journal": [],
            "montee": None, **extra}


class ModeleLogique(unittest.TestCase):
    """Le modèle de chaque recrue vient du travail qu'elle va prendre ; jamais Fable ; la raison dit pourquoi."""

    def setUp(self):
        self.f = {"flux": FLUX_TRIPLE, "agents_locaux_max": 16}
        self.fiches = [{"cle": "x-1", "role": "dev", "lieu": "local", "modele": "Opus", "prenom": "Léa"},
                       {"cle": "x-2", "role": "inconnu", "lieu": "local", "modele": "Haiku", "prenom": "Hugo"}]

    def etat(self, taches):
        return {"fonctionnalites": [{"id": "f1", "etape": "serie", "file": [], "elements": {}}], "taches": taches}

    def proposer(self, taches, **kw):
        return rc.proposer(self.f, self.etat(taches), self.fiches, 0, False, **kw)["propositions"]

    def test_nature_du_travail(self):
        props = self.proposer([tache(i, "testeur", "tests") for i in range(6)]
                              + [tache(7, "architecte", "concept"), tache(8, "architecte", "concept")]
                              + [tache(i, "dev", "dev") for i in range(10, 13)])
        par_role = {p["role"]: {**p, "modele": p["modele_necessaire"]} for p in props}
        self.assertEqual({p["modele"] for p in props}, {"Opus"})     # chaque recrue a le plafond Opus
        self.assertEqual(par_role["testeur"]["modele"], "Haiku")      # … et ses tâches tournent sur leur modèle
        self.assertIn("plafond Opus, tâches en Haiku : tests et vérifications mécaniques de 6 éléments",
                      par_role["testeur"]["raison"])
        self.assertEqual(par_role["architecte"]["modele"], "Opus")
        self.assertIn("conception et architecture", par_role["architecte"]["raison"])
        self.assertEqual(par_role["dev"]["modele"], "Sonnet")       # Léa est sur Opus : le travail décide, pas la fiche
        self.assertNotIn("Fable", {p["modele_necessaire"] for p in props})

    def test_modele_pose_sur_l_etape_d_abord(self):
        self.f = {"flux": [dict(FLUX_TRIPLE[2], modele="Sonnet", justification="Tests d'intégration lourds.")],
                  "agents_locaux_max": 16}
        props = self.proposer([tache(i, "testeur", "tests") for i in range(2)])
        self.assertEqual(props[0]["modele_necessaire"], "Sonnet")
        self.assertIn("modèle posé avec le workflow", props[0]["raison"])

    def test_echec_ou_a_revoir_monte_d_un_cran_pas_au_dela_d_opus(self):
        relancee = tache(1, "testeur", "tests", journal=[{"t": "x", "texte": "Échec : relancée"}])
        revue = tache(2, "dev", "dev", journal=[{"t": "x", "texte": "À revoir"}, {"t": "y", "texte": "Renvoyée à revoir"}])
        autre = tache(5, "dev", "dev")
        une_fois = tache(3, "architecte", "concept", journal=[{"t": "x", "texte": "À revoir"}])
        par_role = {p["role"]: {**p, "modele": p["modele_necessaire"]}
                    for p in self.proposer([relancee, revue, autre, une_fois])}
        self.assertEqual(par_role["testeur"]["modele"], "Sonnet")
        self.assertIn("monté d'un cran", par_role["testeur"]["raison"])
        self.assertEqual(par_role["dev"]["modele"], "Opus")
        self.assertEqual(par_role["architecte"]["modele"], "Opus")
        self.assertNotIn("monté", par_role["architecte"]["raison"])       # une seule fois « à revoir » ne suffit pas
        montee = tache(4, "testeur", "tests", montee={"de": "Haiku", "a": "Sonnet", "raison": "r"})
        self.assertEqual(self.proposer([montee])[0]["modele_necessaire"], "Sonnet")
        # Opus ne monte pas : jamais Fable.
        self.assertEqual(rc.modeles_du_travail([{"texte": "Conception", "difficile": True}], "", "x")[0]["modele"], "Opus")
        self.assertEqual(rc.modeles_du_travail([{"texte": "Tests", "difficile": False}], "", "x")[0]["modele"], "Haiku")

    def test_nature_inconnue_garde_le_modele_du_role(self):
        props = self.proposer([tache(1, "inconnu", "etape"), tache(2, "inconnu", "etape")])
        self.assertEqual((props[0]["modele"], props[0]["modele_necessaire"]), ("Opus", "Haiku"))
        self.assertIn("celui de Hugo, du même rôle", props[0]["raison"])

    def test_deterministe(self):
        taches = [tache(i, "testeur", "tests") for i in range(4)] + [tache(9, "dev", "dev")]
        self.assertEqual(self.proposer(taches), self.proposer(list(taches)))

    def test_lieu_cloud_et_local(self):
        s = self.etat([tache(i, "testeur", "tests") for i in range(6)])
        cloud = rc.proposer(self.f, s, self.fiches, 2, True, lieu="cloud")
        self.assertEqual([p["lieu"] for p in cloud["propositions"]], ["cloud", "cloud"])
        self.assertTrue(any("Plus de place cloud libre" in n for n in cloud["notes"]))
        sans = rc.proposer(self.f, s, self.fiches, 2, False, lieu="cloud")
        self.assertEqual(sans["propositions"], [])
        self.assertIn("pas sur GitHub", sans["notes"][0])
        local = rc.proposer(self.f, s, self.fiches, 2, True, lieu="local")
        self.assertEqual({p["lieu"] for p in local["propositions"]}, {"local"})
        self.assertEqual(len(local["propositions"]), 6)
        mieux = rc.proposer(self.f, s, self.fiches, 2, True)
        self.assertEqual([p["lieu"] for p in mieux["propositions"]][:3], ["cloud", "cloud", "local"])
        with self.assertRaises(rc.RecrutementRefuse):
            rc.proposer(self.f, s, self.fiches, 2, True, lieu="lune")


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

    def test_releve_par_lieu_et_refus_du_mauvais_lieu(self):
        self.serie(5)
        ecrire_origine(self.dossier, "https://github.com/moi/jeu")
        self.ok("parallelisme", entree={"agents_locaux_max": 4, "agents_cloud_max": 2})
        r = self.releve()
        self.assertEqual(releve.valider(r), [])
        par_lieu = r["recrutement"]["propositions_par_lieu"]
        self.assertEqual([p["lieu"] for p in par_lieu["cloud"]], ["cloud", "cloud"])
        self.assertEqual([p["lieu"] for p in par_lieu["local"]], ["local", "local"])
        self.assertEqual(par_lieu["mieux"], r["recrutement"]["propositions"])
        self.assertTrue(r["recrutement"]["notes_par_lieu"]["cloud"])
        agents = [{k: p[k] for k in ("role", "modele", "lieu")} for p in par_lieu["cloud"]]
        # Lieu « cloud » demandé : un agent local est refusé par l'outil, rien n'est écrit.
        code, sortie = self.outil("recruter", entree={"mode": "auto", "lieu": "cloud", "agents": [
            agents[0], {**agents[1], "lieu": "local"}]})
        self.assertEqual(code, 1)
        self.assertIn("uniquement des agents cloud", sortie["erreur"])
        self.assertEqual(self.outil("recruter", entree={"mode": "manuel", "lieu": "cloud", "agents": agents[:1]})[0], 1)
        ecrits = self.ok("recruter", entree={"mode": "auto", "lieu": "cloud", "agents": agents})
        self.assertEqual({a["lieu"] for a in ecrits["agents"]}, {"cloud"})

    def test_sans_github_le_cloud_demande_est_vide_et_refuse(self):
        self.serie(3)
        r = self.releve()["recrutement"]
        self.assertEqual(r["propositions_par_lieu"]["cloud"], [])
        self.assertTrue(r["notes_par_lieu"]["cloud"])
        code, sortie = self.outil("recruter", entree={"mode": "auto", "lieu": "cloud", "agents": [
            {"role": "dev", "modele": "Sonnet", "lieu": "cloud"}]})
        self.assertEqual(code, 1)
        self.assertIn("Créez d'abord le dépôt", sortie["erreur"])


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
        # Le lieu demandé à la répartition : tous les agents y vont, et seulement en automatique.
        mixte = {**auto, "lieu": "cloud", "agents": [{"role": "dev", "modele": "Opus", "lieu": "local"}]}
        self.assertIn("uniquement des agents cloud", self.verifier(mixte, sur_github))
        self.assertIsNone(self.verifier({**auto, "lieu": "local", "agents": auto["agents"][:1]}, sur_github))
        self.assertIn("lieu", self.verifier({**auto, "lieu": "lune"}))
        self.assertIn("lieu", self.verifier({**ok, "lieu": "local"}))
        self.assertEqual(demandes.nettoyer({**auto, "lieu": "local", "x": 1})["lieu"], "local")
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

    def bloquer_un_depart_cloud(self):
        ecrire_origine(self.dossier, "https://github.com/moi/jeu")
        self.ok("parallelisme", entree={"agents_locaux_max": 2, "agents_cloud_max": 1})
        cle = self.ok("recruter", entree={"mode": "manuel", "agents": [
            {"role": "dev", "modele": "Sonnet", "lieu": "cloud"}]})["agents"][0]["cle"]
        tid = self.ok("tache", entree={"titre": "Écran", "role": "dev", "agent": cle, "active": True})["id"]
        depart = {"agent": cle, "taches": [tid], "matiere": "m", "modele": "sonnet", "lot": None}
        self.etat["departs"][tid] = depart
        self.etat["relancees"].add(tid)
        e = agents.Execution(tid, cle, None, erreur="session cloud : --cloud requires an interactive terminal")
        regles._agent_en_echec(self.projet, self.etat, e, depart)
        s = json.loads((self.dossier / "suivi.json").read_text(encoding="utf-8"))
        return cle, tid, next(x for x in s["decisions_projet"] if x["genre"] == "session_cloud")

    def test_la_decision_porte_le_lien_le_depot_et_le_message_de_depart(self):
        cle, tid, decision = self.bloquer_un_depart_cloud()
        self.assertEqual(decision["lien"], "https://claude.ai/code")
        self.assertEqual(decision["depot"], "https://github.com/moi/jeu")
        self.assertEqual((decision["tache"], decision["modele"]), (tid, "Sonnet"))
        self.assertTrue(decision["depart"].startswith("Tu repars de zéro."))
        self.assertIn(f".factory/rapports/{tid}.json", decision["depart"])
        self.assertIn("interactive terminal", decision["texte"])

    def test_c_est_fait_avec_la_session_la_releve_sans_relancer(self):
        cle, tid, decision = self.bloquer_un_depart_cloud()
        d, actions = self.traiter(type="session_cloud", decision=decision["id"],
                                  session="https://claude.ai/code/session_01AbC")
        self.assertEqual([a for a in actions if a[0] == "agent" and tid in a[2]], [])   # pas de nouveau lancement
        s = json.loads((self.dossier / "suivi.json").read_text(encoding="utf-8"))
        t = next(t for t in s["taches"] if t["id"] == tid)
        self.assertIsNone(t["bloquee"])
        self.assertTrue(t["active"])
        self.assertTrue(any(j["texte"].startswith("Session cloud session_01AbC (sonnet)") for j in t["journal"]))
        info = self.etat["cloud"][tid]
        self.assertEqual((info["session"], info["adresse"], info["agent"]),
                         ("session_01AbC", "https://claude.ai/code/session_01AbC", cle))
        self.assertIn(tid, self.etat["en_cours"])
        self.assertEqual(self.etat["departs"][tid]["agent"], cle)
        self.assertEqual(self.etat["sessions_cloud"][cle], "session_01AbC")
        self.assertIn("relevée", self.statut(d["id"])["reponse"])
        self.assertNotIn(decision["id"], [x["id"] for x in s["decisions_projet"]])


if __name__ == "__main__":
    unittest.main()
