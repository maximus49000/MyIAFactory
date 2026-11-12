"""La route de création de projet du bureau : `POST /api/projets/creer`. git et gh sont simulés."""
import json
import tempfile
import unittest
from pathlib import Path

from bureau import reglages
from tests.test_acces import AvecBureauOuvert
from tests.test_bureau_multi import AvecBureau, RELEVE
from tests.test_inst_creation import Executeur

DECISION = {"id": "g1", "genre": "genre_fonctionnalite", "texte": "Ce n'est pas un jeu web.", "propose": "jeu-mobile",
            "genres_connus": ["jeu-web", "jeu-mobile"], "incertain": False}


class AvecCreation(AvecBureau):
    def setUp(self):
        super().setUp()
        self.rangement = self.tmp / "rangement"
        self.rangement.mkdir()
        self.git, self.gh = Executeur(), Executeur()
        self.srv.executer_git, self.srv.executer_gh = self.git, self.gh
        self.srv._genres_connus = lambda: {"jeu-web", "jeu-mobile"}

    def corps(self, **extra):
        return {"parent": str(self.rangement), "nom": "Casse-briques", "mots_interdits": ["secretcorp"],
                "facturation": False, "github": False, **extra}

    def releve_avec_decision(self, nom="a"):
        r = dict(RELEVE, projet=f"Projet {nom.upper()}", fonctionnalites=[
            {"id": "f1", "nom": "Casse-briques", "etape": "cadrage", "decisions": [dict(DECISION)]}])
        (self.dossier(nom) / "releve.json").write_text(json.dumps(r), encoding="utf-8")
        self.srv.projets[nom]._cache_etat = (0.0, None)


class TestCreerProjet(AvecCreation):
    def test_creer_projet_route(self):
        statut, corps = self.post("/api/projets/creer", self.corps(origine="a", description="Un casse-briques.",
                                                                    genre="jeu-mobile"))
        self.assertEqual(statut, 200, corps)
        self.assertEqual(corps["ok"], True)
        self.assertEqual(corps["github"], "non demandé")
        self.assertIn("Casse-briques", corps["message"])
        self.assertTrue((self.rangement / "Casse-briques" / ".factory" / "factory.json").is_file())
        # inscrit au bureau commun et visible sans redémarrage
        self.assertEqual(len(reglages.lire_bureau(self.fichier)["projets"]), 3)
        liste = self.json("/api/projets")["projets"]
        self.assertIn(corps["projet"], [p["id"] for p in liste])
        self.assertEqual(self.srv.projet(corps["projet"]).chemin_reglages.resolve(),
                         (self.rangement / "Casse-briques" / ".factory" / "reglages.json").resolve())
        brut = json.loads((self.rangement / "Casse-briques" / ".factory" / "factory.json").read_text(encoding="utf-8"))
        self.assertEqual((brut["genre"], brut["description"]), ("jeu-mobile", "Un casse-briques."))
        self.assertIn("Casse-briques", brut["mots_interdits"])
        self.assertEqual(self.git.appels + self.gh.appels, [])

    def test_genre_inconnu_n_est_pas_ecrit_dans_le_projet(self):
        statut, corps = self.post("/api/projets/creer", self.corps(genre="appli-android",
                                                                    genre_description="Applications Android."))
        self.assertEqual(statut, 200, corps)
        brut = json.loads((self.rangement / "Casse-briques" / ".factory" / "factory.json").read_text(encoding="utf-8"))
        self.assertIsNone(brut["genre"])
        self.assertEqual(brut["description"], "Applications Android.")

    def test_liste_donne_les_parents_et_le_prerempli(self):
        (self.dossier("a") / "factory.json").write_text(json.dumps({
            "nom": "A", "skill": "~/MyIAFactory/skill", "mots_interdits": ["alpha"],
            "services": [{"id": "facturation", "nom": "Facturation"}]}), encoding="utf-8")
        regl = json.loads((self.dossier("a") / "reglages.json").read_text(encoding="utf-8"))
        regl["orchestrateur"] = "factory.json"
        (self.dossier("a") / "reglages.json").write_text(json.dumps(regl), encoding="utf-8")
        j = self.json("/api/projets")
        self.assertEqual(j["parents"], [str(self.tmp.resolve())])
        a = j["projets"][0]
        self.assertEqual((a["mots_interdits"], a["facturation"]), (["alpha"], True))
        self.assertEqual(j["projets"][1]["mots_interdits"], [])

    def test_creer_projet_depuis_une_decision_depose_la_demande(self):
        self.releve_avec_decision()
        statut, corps = self.post("/api/projets/creer", self.corps(origine="a", decision="g1", fonctionnalite="f1",
                                                                    genre="jeu-mobile"))
        self.assertEqual(statut, 200, corps)
        self.assertIs(corps["demande_deposee"], True)
        reglages_cree = (self.rangement / "Casse-briques" / ".factory" / "reglages.json").resolve()
        deposees = [json.loads(x) for x in (self.dossier("a") / "notes.log").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(deposees), 1)
        d = deposees[0]
        self.assertEqual((d["type"], d["choix"], d["decision"], d["fonctionnalite"], d["genre"]),
                         ("genre_fonctionnalite", "nouveau_projet", "g1", "f1", "jeu-mobile"))
        self.assertEqual(Path(d["projet_cree"]).resolve(), reglages_cree)
        self.assertFalse((self.dossier("b") / "notes.log").exists())

    def test_demande_refusee_ne_cree_rien(self):
        self.releve_avec_decision()
        # décision inconnue : le projet n'est pas créé
        statut, corps = self.post("/api/projets/creer", self.corps(origine="a", decision="zzz", fonctionnalite="f1"))
        self.assertEqual(statut, 400)
        self.assertIn("Décision inconnue", corps["erreur"])
        self.assertFalse((self.rangement / "Casse-briques").exists())
        # une création depuis une décision sans projet d'origine
        statut, _ = self.post("/api/projets/creer", self.corps(decision="g1", fonctionnalite="f1"))
        self.assertEqual(statut, 400)
        self.assertFalse((self.rangement / "Casse-briques").exists())

    def test_creer_projet_erreur_lisible(self):
        cas = [({"nom": ""}, 400, "nom"), ({"nom": "CON"}, 400, "Windows"),
               ({"parent": str(self.tmp / "absent")}, 400, "n'existe pas"), ({"origine": "zzz"}, 404, "inconnu"),
               ({"mots_interdits": "x"}, 400, "mots_interdits"), ({"github": "oui"}, 400, "github")]
        for extra, code, mot in cas:
            with self.subTest(extra=extra):
                statut, corps = self.post("/api/projets/creer", self.corps(**extra))
                self.assertEqual(statut, code, corps)
                self.assertIn(mot.lower(), corps["erreur"].lower())
        self.assertEqual(len(reglages.lire_bureau(self.fichier)["projets"]), 2)
        self.post("/api/projets/creer", self.corps())
        statut, corps = self.post("/api/projets/creer", self.corps())   # le nom est pris
        self.assertEqual(statut, 400)
        self.assertIn("existe déjà", corps["erreur"])

    def test_corps_illisible_et_en_tetes(self):
        r, data = self.req("POST", "/api/projets/creer", "{", {"X-Bureau": "1", "Content-Type": "application/json"})
        self.assertEqual(r.status, 400)
        r, _ = self.req("POST", "/api/projets/creer", "{}", {"Content-Type": "application/json"})
        self.assertEqual(r.status, 403)

    def test_github_sans_gh_projet_local(self):
        self.srv.executer_gh = Executeur(absent=True)
        statut, corps = self.post("/api/projets/creer", self.corps(github=True))
        self.assertEqual(statut, 200, corps)
        self.assertIn("gh", corps["message"])
        self.assertEqual(corps["github"], "GitHub n'a pas été fait : gh (l'outil GitHub) n'est pas installé sur ce "
                                          "poste.")
        self.assertTrue((self.rangement / "Casse-briques" / ".factory" / "factory.json").is_file())

    def test_bureau_plein_refuse(self):
        d = json.loads(self.fichier.read_text(encoding="utf-8"))
        for i in range(reglages.MAX_PROJETS - 2):
            r = self.tmp / f"x{i}" / "reglages.json"
            r.parent.mkdir()
            r.write_text("{}", encoding="utf-8")
            d["projets"].append(str(r))
        self.fichier.write_text(json.dumps(d), encoding="utf-8")
        statut, corps = self.post("/api/projets/creer", self.corps())
        self.assertEqual(statut, 400)
        self.assertIn(str(reglages.MAX_PROJETS), corps["erreur"])
        self.assertFalse((self.rangement / "Casse-briques").exists())


class TestCreerExigeLeCode(AvecBureauOuvert):
    def test_creer_exige_le_code_d_acces(self):
        corps = json.dumps({"parent": str(self.tmp), "nom": "Pirate"})
        ent = {"X-Bureau": "1", "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{self.distant}",
               "Host": f"127.0.0.1:{self.distant}"}
        r, _ = self.req("POST", "/api/projets/creer", corps, ent)
        self.assertEqual(r.status, 401)
        self.assertFalse((self.tmp / "Pirate").exists())
        cookie = self.associer()
        r, data = self.req("POST", "/api/projets/creer", json.dumps({"parent": 3, "nom": "x"}), {**ent, "Cookie": cookie})
        self.assertEqual(r.status, 400, data)   # le code est accepté, c'est le corps qui est refusé


if __name__ == "__main__":
    unittest.main()
