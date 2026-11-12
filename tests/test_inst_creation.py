"""Créer un projet vide depuis le bureau. HOME est temporaire ; git et gh sont simulés (aucun appel réel)."""
import json
from pathlib import Path

from bureau import reglages
from installation import creation, dossier, mise_en_place as mep
from installation.dossier import Echec
from orchestrateur import factory as fa
from tests.inst_aide import AvecMaison, instantane

RACINE = Path(__file__).resolve().parent.parent


class Executeur:
    """Un git ou un gh simulé : note les appels, répond comme demandé."""

    def __init__(self, reponses=None, absent=False):
        self.appels, self.reponses, self.absent = [], reponses or {}, absent

    def __call__(self, args, cwd):
        self.appels.append((list(args), str(cwd)))
        if self.absent:
            return 1, "n'a pas pu s'exécuter : introuvable"
        return self.reponses.get(" ".join(args[:2]), self.reponses.get(args[0], (0, "")))


class Base(AvecMaison):
    def setUp(self):
        super().setUp()
        self.parent = self.base / "mes projets"
        self.bureau = dossier.bureau()
        self.git, self.gh = Executeur(), Executeur()

    def origine(self, **extra):
        """Un projet d'origine : ses réglages (charge, moteur) et ses consignes propres."""
        d = self.base / "origine" / ".factory"
        d.mkdir(parents=True)
        (d / "factory.json").write_text(json.dumps({
            "nom": "Origine", "skill": "~/MyIAFactory/skill", "genre": "jeu-mobile", "mots_interdits": ["secretcorp"],
            "consignes": "consignes-projet.md", "reglages": "reglages.json", "modele_orchestrateur": "Opus",
            "agents_locaux_max": 4, **extra}), encoding="utf-8")
        (d / "consignes-projet.md").write_text("# Consignes de l'origine\n\nTests d'abord.\n", encoding="utf-8")
        (d / "reglages.json").write_text(json.dumps({"orchestrateur": "factory.json", "charge_max": 55,
                                                      "moteur": {"couche": "api"}}), encoding="utf-8")
        return d / "reglages.json"

    def creer(self, nom="Casse-briques", **kw):
        kw.setdefault("origine", None)
        kw.setdefault("mots_interdits", [])
        kw.setdefault("facturation", False)
        kw.setdefault("github", False)
        kw.setdefault("description", None)
        kw.setdefault("genre", None)
        kw.setdefault("git", self.git)
        kw.setdefault("gh", self.gh)
        return creation.creer_projet(self.parent, nom, bureau_json=self.bureau, **kw)

    def factory(self, nom="Casse-briques"):
        return self.parent / nom / ".factory" / "factory.json"


class TestCreation(Base):
    def test_cree_l_arborescence_complete(self):
        r = self.creer()
        base = self.parent / "Casse-briques" / ".factory"
        self.assertEqual(r["reglages"], base / "reglages.json")
        for nom in ("factory.json", "reglages.json", "controles.md", "consignes-projet.md"):
            self.assertTrue((base / nom).is_file(), nom)
        for d in ("pieces", "captures", "livrables", "methodes", "documents", "fiches", "fiches/briefs"):
            self.assertTrue((base / d).is_dir(), d)
        self.assertEqual(list(base.glob("fiches/*.md")), [])   # ni fiche, ni flux
        brut = json.loads(self.factory().read_text(encoding="utf-8"))
        self.assertNotIn("flux", brut)
        self.assertIn(".env", (self.parent / "Casse-briques" / ".gitignore").read_text(encoding="utf-8"))
        self.assertFalse((self.parent / "Casse-briques" / ".factory.tmp").exists())

    def test_lisible_par_la_factory_et_inscrit_au_bureau(self):
        r = self.creer(description="Un casse-briques pour Android.", genre="jeu-mobile")
        f = fa.lire(self.factory())
        self.assertEqual(f["flux"], [])
        self.assertEqual(f["description"], "Un casse-briques pour Android.")
        self.assertEqual(f["genre"], "jeu-mobile")
        self.assertEqual(f["nom"], "Casse-briques")
        b = reglages.lire_bureau(self.bureau)
        self.assertEqual([p["chemin"].resolve() for p in b["projets"]], [r["reglages"].resolve()])
        self.assertEqual(r["id"], b["projets"][0]["id"])

    def test_sans_description_ni_genre(self):
        self.creer()
        f = fa.lire(self.factory())
        self.assertIsNone(f["genre"])
        self.assertIsNone(f["description"])

    def test_reglages_repris_de_l_origine(self):
        self.creer(origine=self.origine())
        f = fa.lire(self.factory())
        self.assertEqual(f["modele_orchestrateur"], "Opus")
        self.assertEqual(f["agents_locaux_max"], 4)
        self.assertIn("Tests d'abord", (self.parent / "Casse-briques" / ".factory" / "consignes-projet.md")
                      .read_text(encoding="utf-8"))
        r = json.loads((self.parent / "Casse-briques" / ".factory" / "reglages.json").read_text(encoding="utf-8"))
        self.assertEqual(r["charge_max"], 55)
        self.assertEqual(r["moteur"], {"couche": "api"})

    def test_origine_illisible_refusee(self):
        o = self.origine()
        o.write_text("pas du json", encoding="utf-8")
        with self.assertRaises(Echec) as c:
            self.creer(origine=o)
        self.assertIn("origine", str(c.exception).lower())
        self.assertFalse((self.parent / "Casse-briques").exists())

    def test_nom_ajoute_aux_mots_interdits(self):
        self.creer(mots_interdits=["secretcorp", "  "])
        f = fa.lire(self.factory())
        self.assertEqual(f["mots_interdits"], ["secretcorp", "Casse-briques"])

    def test_nom_deja_dans_les_mots_interdits_pas_double(self):
        self.creer(mots_interdits=["casse-briques"])
        self.assertEqual(fa.lire(self.factory())["mots_interdits"], ["casse-briques"])

    def test_facturation_ajoute_le_service(self):
        self.creer(facturation=True)
        self.assertEqual([s["id"] for s in fa.lire(self.factory())["services"]], ["facturation"])
        r = json.loads((self.parent / "Casse-briques" / ".factory" / "reglages.json").read_text(encoding="utf-8"))
        self.assertTrue(r["prix_automatiques"])

    def test_nom_refuse(self):
        (self.parent / "Existe").mkdir()
        for nom in ("", "   ", "Existe", "existe", "..", ".", "a/b", "a\\b", "a:b", "CON", "nul", "Com1", "lpt3.txt",
                    "a*b", "a?b", 'a"b', "a<b", "fin.", "x" * 101):
            with self.subTest(nom=nom):
                with self.assertRaises(Echec) as c:
                    self.creer(nom)
                self.assertTrue(str(c.exception))
        self.assertFalse(self.bureau.exists())
        self.assertEqual(sorted(p.name for p in self.parent.iterdir()), ["Existe", "Petit projet"])

    def test_parent_absent_ou_dans_la_skill_refuse(self):
        with self.assertRaises(Echec) as c:
            creation.creer_projet(self.base / "inexistant", "Projet", origine=None, mots_interdits=[],
                                  facturation=False, github=False, description=None, genre=None,
                                  bureau_json=self.bureau)
        self.assertIn("inexistant", str(c.exception))
        fichier = self.base / "fichier.txt"
        fichier.write_text("x", encoding="utf-8")
        with self.assertRaises(Echec):
            creation.creer_projet(fichier, "Projet", origine=None, mots_interdits=[], facturation=False,
                                  github=False, description=None, genre=None, bureau_json=self.bureau)
        with self.assertRaises(Echec) as c:
            creation.creer_projet(RACINE, "Projet-de-test-jamais-cree", origine=None, mots_interdits=[],
                                  facturation=False, github=False, description=None, genre=None,
                                  bureau_json=self.bureau)
        self.assertIn("skill", str(c.exception))
        self.assertFalse((RACINE / "Projet-de-test-jamais-cree").exists())

    def test_echec_ne_laisse_rien(self):
        avant = instantane(self.base)
        self.bureau.parent.mkdir(parents=True, exist_ok=True)
        self.bureau.write_text("illisible", encoding="utf-8")   # l'inscription échoue
        avant = instantane(self.base)
        with self.assertRaises(Echec):
            self.creer()
        self.assertEqual(instantane(self.base), avant)
        self.assertFalse((self.parent / "Casse-briques").exists())

    def test_echec_apres_ecriture_ne_laisse_rien(self):
        avant = instantane(self.base)
        original = mep.inscrire

        def echoue(*a, **k):
            raise Echec("inscription impossible")
        mep.inscrire = echoue
        self.addCleanup(setattr, mep, "inscrire", original)
        with self.assertRaises(Echec):
            self.creer()
        self.assertEqual(instantane(self.base), avant)
        self.assertFalse((self.parent / "Casse-briques").exists())

    def test_bureau_plein_refuse(self):
        self.bureau.parent.mkdir(parents=True)
        entrees = []
        for i in range(reglages.MAX_PROJETS):
            d = self.base / f"p{i}" / ".factory"
            d.mkdir(parents=True)
            (d / "reglages.json").write_text("{}", encoding="utf-8")
            entrees.append({"chemin": str(d / "reglages.json")})
        self.bureau.write_text(json.dumps({"port": 8770, "projets": entrees}), encoding="utf-8")
        octets = self.bureau.read_bytes()
        with self.assertRaises(Echec) as c:
            self.creer()
        self.assertIn(str(reglages.MAX_PROJETS), str(c.exception))
        self.assertEqual(self.bureau.read_bytes(), octets)
        self.assertFalse((self.parent / "Casse-briques").exists())

    def test_sans_github_ni_git_ni_gh_appeles(self):
        r = self.creer()
        self.assertEqual(r["github"], "non demandé")
        self.assertEqual(self.git.appels + self.gh.appels, [])

    def test_github_fait(self):
        r = self.creer(github=True)
        self.assertEqual(r["github"], "fait")
        projet = str(self.parent / "Casse-briques")
        self.assertEqual([a for a, _ in self.git.appels][:2], [["init"], ["add", "."]])
        self.assertEqual(self.git.appels[2][0][:1], ["commit"])
        self.assertTrue(all(c == projet for _, c in self.git.appels + self.gh.appels))
        creer = [a for a, _ in self.gh.appels if a[:2] == ["repo", "create"]]
        self.assertEqual(creer, [["repo", "create", "Casse-briques", "--private", "--source", ".", "--push"]])

    def test_github_sans_gh_projet_local(self):
        r = self.creer(github=True, gh=Executeur(absent=True))
        self.assertIn("gh", r["github"])
        self.assertNotEqual(r["github"], "fait")
        self.assertTrue(self.factory().is_file())   # le projet est créé quand même
        self.assertEqual(len(reglages.lire_bureau(self.bureau)["projets"]), 1)

    def test_github_gh_non_connecte(self):
        r = self.creer(github=True, gh=Executeur({"auth status": (1, "You are not logged in")}))
        self.assertIn("gh auth login", r["github"])
        self.assertTrue(self.factory().is_file())

    def test_github_sans_git_projet_local(self):
        r = self.creer(github=True, git=Executeur(absent=True))
        self.assertIn("git", r["github"])
        self.assertTrue(self.factory().is_file())
        self.assertEqual([a for a, _ in self.gh.appels if a[:2] == ["repo", "create"]], [])

    def test_github_depot_refuse_projet_local(self):
        r = self.creer(github=True, gh=Executeur({"repo create": (1, "name already exists")}))
        self.assertIn("name already exists", r["github"])
        self.assertTrue(self.factory().is_file())

    def test_github_commit_refuse_projet_local(self):
        r = self.creer(github=True, git=Executeur({"commit": (1, "Please tell me who you are")}))
        self.assertIn("who you are", r["github"])
        self.assertEqual([a for a, _ in self.gh.appels if a[:2] == ["repo", "create"]], [])
