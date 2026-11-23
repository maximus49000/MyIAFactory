"""Créer un projet vide depuis le bureau. HOME est temporaire ; git et gh sont simulés (aucun appel réel)."""
import json
from pathlib import Path

from bureau import reglages
from installation import creation, dossier, mise_en_place as mep
from installation.dossier import Echec
from orchestrateur import factory as fa
from tests.inst_aide import AvecMaison, instantane

RACINE = Path(__file__).resolve().parent.parent

from tests import plateforme_tests  # noqa: E402



class Executeur:
    """Un git ou un gh simulé : note les appels, répond comme demandé."""

    def __init__(self, reponses=None, absent=False):
        self.appels, self.reponses, self.absent = [], reponses or {}, absent

    def __call__(self, args, cwd):
        self.appels.append((list(args), str(cwd)))
        if self.absent:
            return 1, "n'a pas pu s'exécuter : introuvable"
        return self.reponses.get(" ".join(args[:2]), self.reponses.get(args[0], (0, "")))


class Identite(AvecMaison):
    """Sans identité git sur le poste, le premier commit échouait : elle est réglée dans le dépôt seul, d'après gh."""

    def test_identite_reglee_dans_le_depot_depuis_le_compte_github(self):
        git = Executeur({"config user.email": (1, "")})
        gh = Executeur({"api user": (0, json.dumps({"login": "auteur", "id": 42, "name": "Un Auteur"}))})
        creation.regler_identite(self.base, git, gh)
        self.assertIn(["config", "user.name", "Un Auteur"], [a for a, _ in git.appels])
        self.assertIn(["config", "user.email", "42+auteur@users.noreply.github.com"], [a for a, _ in git.appels])
        self.assertFalse(any("--global" in a for a, _ in git.appels))

    def test_identite_existante_ou_gh_muet_rien_n_est_change(self):
        git = Executeur({"config user.email": (0, "deja@exemple.fr\n")})
        gh = Executeur()
        creation.regler_identite(self.base, git, gh)
        self.assertEqual(gh.appels, [])
        git = Executeur({"config user.email": (1, "")})
        creation.regler_identite(self.base, git, Executeur({"api user": (1, "pas connecté")}))
        self.assertEqual([a for a, _ in git.appels], [["config", "user.email"]])


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


class TestAdoption(Base):
    """Un dossier de code existant devient le projet, sur place : seul `.factory` s'y ajoute."""

    def code(self):
        d = self.base / "mon code"
        d.mkdir(parents=True)
        (d / "main.py").write_text("print('x')\n", encoding="utf-8")
        (d / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
        return d

    def adopter(self, d, **kw):
        kw.setdefault("git", self.git)
        kw.setdefault("gh", self.gh)
        return creation.creer_projet(None, "Casse-briques", adopter=str(d), bureau_json=self.bureau, **kw)

    def test_le_dossier_devient_le_projet_et_le_code_est_intact(self):
        d = self.code()
        r = self.adopter(d)
        self.assertEqual(Path(r["projet"]).resolve(), d.resolve())
        self.assertTrue((d / ".factory" / "factory.json").is_file())
        self.assertEqual((d / "main.py").read_text(encoding="utf-8"), "print('x')\n")
        self.assertIn("*.pyc", (d / ".gitignore").read_text(encoding="utf-8"))
        self.assertIn(".env", (d / ".gitignore").read_text(encoding="utf-8"))
        self.assertFalse((d / ".factory.tmp").exists())
        self.assertEqual(len(reglages.lire_bureau(self.bureau)["projets"]), 1)

    def test_un_dossier_deja_installe_est_refuse(self):
        d = self.code()
        (d / ".factory").mkdir()
        with self.assertRaises(Echec):
            self.adopter(d)

    def test_dossier_absent_ou_dans_la_skill_refuse(self):
        with self.assertRaises(Echec):
            self.adopter(self.base / "absent")

    def test_un_echec_rend_le_dossier_tel_qu_il_etait(self):
        d = self.code()
        avant = instantane(self.base)
        original = mep.inscrire

        def echoue(*a, **k):
            raise Echec("inscription impossible")
        mep.inscrire = echoue
        self.addCleanup(setattr, mep, "inscrire", original)
        with self.assertRaises(Echec):
            self.adopter(d)
        self.assertEqual(instantane(self.base), avant)
        self.assertEqual((d / ".gitignore").read_text(encoding="utf-8"), "*.pyc\n")
        self.assertTrue((d / "main.py").is_file())


class TestPoids(Base):
    """GitHub : un dossier trop lourd n'est jamais ajouté à l'aveugle ; le bureau propose des exclusions, appliquées
    seulement à l'accord de l'utilisateur."""

    def dossier_avec(self, **tailles):
        d = self.base / "lourd"
        d.mkdir(exist_ok=True)
        for nom, ko in tailles.items():
            chemin = d / nom
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_bytes(b"x" * (ko * 1024))
        return d

    def git_listant(self, d):
        fichiers = sorted(str(p.relative_to(d)).replace("\\", "/") for p in d.rglob("*") if p.is_file())
        return Executeur({"-c core.quotepath=off": (0, chr(10).join(fichiers))})

    def test_un_dossier_leger_passe(self):
        d = self.dossier_avec(**{"a.py": 10, "b.py": 20})
        self.assertIsNone(creation.proposer_allegement(d, self.git_listant(d)))

    def test_les_gros_fichiers_donnent_des_exclusions_proposees(self):
        d = self.dossier_avec(**{"a.py": 10, "build/lib/x.so": 60 * 1024, "Livrables/v1.apk": 60 * 1024,
                                 "seed.db.bak-1": 60 * 1024, "base.db": 60 * 1024})
        p = creation.proposer_allegement(d, self.git_listant(d))
        self.assertEqual(sorted(p["regles"]), sorted(["/build/", "*.apk", "*.bak*", "/base.db"]))
        self.assertGreater(p["avant_mo"], 200)
        self.assertEqual(p["apres_mo"], 0)
        self.assertIn("Rien n'a été ajouté", p["texte"])

    def test_le_total_trop_gros_ajoute_les_plus_gros_dossiers(self):
        d = self.base / "total"
        d.mkdir()
        original = creation.DEPOT_MAX
        creation.DEPOT_MAX = 100 * 1024
        self.addCleanup(setattr, creation, "DEPOT_MAX", original)
        for n in ("gros/a.bin", "gros/b.bin", "petit/c.txt"):
            (d / n).parent.mkdir(exist_ok=True)
            (d / n).write_bytes(b"x" * (60 * 1024 if n.startswith("gros") else 1024))
        p = creation.proposer_allegement(d, self.git_listant(d))
        self.assertEqual(p["regles"], ["/gros/"])

    def test_github_ne_fait_pas_git_add_sur_un_dossier_trop_lourd(self):
        d = self.dossier_avec(**{"base.db": 60 * 1024})
        git = self.git_listant(d)
        r = creation.github(d, "FM_Stats", git, Executeur())
        self.assertIn("propose cet allègement", r)
        self.assertNotIn(["add", "."], [a for a, _ in git.appels])
        self.assertNotIn("commit", [a[0] for a, _ in git.appels])

    def test_depot_github_propose_sans_rien_ajouter(self):
        d = self.dossier_avec(**{"base.db": 60 * 1024})
        (d / ".git").mkdir()
        git = self.git_listant(d)
        r = creation.depot_github(d, "FM_Stats", git, Executeur())
        self.assertFalse(r["fait"])
        self.assertEqual(r["allegement"]["regles"], ["/base.db"])
        self.assertNotIn(["add", "."], [a for a, _ in git.appels])
        self.assertNotIn("/base.db", (d / ".gitignore").read_text(encoding="utf-8"))

    def test_l_accord_ecrit_les_exclusions_puis_cree_le_depot(self):
        d = self.dossier_avec(**{"a.py": 1, "base.db": 60 * 1024})
        (d / ".git").mkdir()
        (d / ".gitignore").write_text("*.pyc" + chr(10), encoding="utf-8")
        git = Executeur()

        def avec_filtre(args, cwd):
            if args[:3] == ["-c", "core.quotepath=off", "ls-files"]:
                ignore = (d / ".gitignore").read_text(encoding="utf-8")
                fichiers = [p.name for p in d.iterdir() if p.is_file() and p.name != ".gitignore"
                            and ("/" + p.name) not in ignore.split()]
                git.appels.append((list(args), str(cwd)))
                return 0, chr(10).join(fichiers)
            return git(args, cwd)
        r = creation.depot_github(d, "FM_Stats", avec_filtre, Executeur(), allegement=True)
        texte = (d / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.pyc", texte)
        self.assertIn("/base.db", texte)
        self.assertIn(["add", "."], [a for a, _ in git.appels])
        self.assertTrue(r["fait"], r["texte"])

    def test_git_muet_ne_bloque_pas(self):
        d = self.dossier_avec(**{"a.py": 1})
        self.assertIsNone(creation.proposer_allegement(d, Executeur({"-c core.quotepath=off": (1, "erreur")})))


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

    def reglages_du_projet(self, nom="Casse-briques"):
        return json.loads((self.parent / nom / ".factory" / "reglages.json").read_text(encoding="utf-8"))

    def test_charge_max_vient_du_calibrage_du_poste_et_non_d_un_70_fixe(self):
        vus = []
        self.creer(calibrer=lambda bureau: vus.append(bureau) or 45)
        self.assertEqual(self.reglages_du_projet()["charge_max"], 45)
        self.assertEqual(vus, [self.bureau])

    def test_charge_max_de_l_origine_prime_sur_le_calibrage(self):
        self.creer(origine=self.origine(), calibrer=lambda bureau: 45)
        self.assertEqual(self.reglages_du_projet()["charge_max"], 55)

    def test_calibrage_du_poste_par_defaut_est_celui_de_la_skill(self):
        """Sans calibrage donné : `calibrage.calibrer` sur la machine et l'historique de charge du bureau (30 à 95)."""
        self.creer()
        self.assertTrue(30 <= self.reglages_du_projet()["charge_max"] <= 95)
        from installation import calibrage
        from unittest import mock
        with mock.patch.object(calibrage, "calibrer", return_value={"charge_max": 50}) as c:
            self.assertEqual(creation.calibrer_le_poste(self.bureau), 50)
        c.assert_called_once()
        with mock.patch.object(calibrage, "calibrer", side_effect=OSError("mesure")):
            self.assertEqual(creation.calibrer_le_poste(self.bureau), creation.CHARGE_MAX_DEFAUT)

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
        """Les règles de noms de Windows (CON, nul, « fin. »…) valent partout : le projet peut être ouvert d'un poste
        Windows."""
        (self.parent / "Existe").mkdir()
        for nom in ("", "   ", "Existe", "..", ".", "a/b", "a\\b", "a:b", "CON", "nul", "Com1", "lpt3.txt",
                    "a*b", "a?b", 'a"b', "a<b", "fin.", "x" * 101):
            with self.subTest(nom=nom):
                with self.assertRaises(Echec) as c:
                    self.creer(nom)
                self.assertTrue(str(c.exception))
        self.assertFalse(self.bureau.exists())
        self.assertEqual(sorted(p.name for p in self.parent.iterdir()), ["Existe", "Petit projet"])

    @plateforme_tests.windows_seulement("système de fichiers insensible à la casse : « existe » y désigne « Existe »")
    def test_nom_existant_a_la_casse_pres_refuse(self):
        (self.parent / "Existe").mkdir()
        with self.assertRaises(Echec):
            self.creer("existe")
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
        self.assertEqual([a for a, _ in self.git.appels if a[0] != "-c"][:2], [["init"], ["add", "."]])
        sans_identite = [a for a in self.git.appels if a[0][0] not in ("config", "-c")]    # l'identité git est réglée avant
        self.assertEqual(sans_identite[2][0][:1], ["commit"])
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
