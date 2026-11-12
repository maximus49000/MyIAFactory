"""La route de création de projet du bureau : `POST /api/projets/creer`. git et gh sont simulés."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from bureau import reglages
from installation import brouillons
from moteur import appel
from tests.test_acces import AvecBureauOuvert
from tests.test_bureau_multi import AvecBureau, ENT, RELEVE
from tests.test_inst_creation import Executeur
from tests.test_inst_definition import GENRES, QUESTIONS, USAGE, Faux, a_installer, proposition

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


PRIX = {"entree": 3e-6, "sortie": 15e-6, "cache_lecture": 0.3e-6, "cache_ecriture": 3.75e-6}


class Bloque:
    """Un faux `appeler` qui attend qu'on le libère : il garde un tour « en cours »."""

    def __init__(self, reponse):
        self.reponse, self.appels = reponse, 0
        self.entre, self.libere = threading.Event(), threading.Event()

    def __call__(self, consigne, dossier, modele, *, couche="claude", **_):
        self.appels += 1
        self.entre.set()
        self.libere.wait(15)
        return appel.Reponse(json.dumps(self.reponse), [dict(USAGE)])


class Executeur_outil:
    """Un exécuteur de l'outil de l'orchestrateur : note les commandes, répond que tout va bien."""

    def __init__(self):
        self.appels = []

    def __call__(self, factory, argv, entree=None):
        self.appels.append((argv[1], entree))
        return 0, {"ok": True}


class AvecCreations(AvecCreation):
    """Les routes `/api/creations/*` : brouillons, usages, modèle, outil, git et gh sont tous simulés ou temporaires."""

    def setUp(self):
        super().setUp()
        brouillons._VIVANTS.clear()
        self.addCleanup(brouillons._VIVANTS.clear)
        self.creations = self.tmp / "creations"
        self.commun = self.tmp / "usage-creations.jsonl"
        self.srv.dossier_creations, self.srv.commun_creations = self.creations, self.commun
        self.srv.prix_de_modele = lambda m: PRIX
        self.srv.verifier_environnement = a_installer
        self.srv.appeler_jugement = Faux(QUESTIONS)
        self.srv.executer_outil = self.outil = Executeur_outil()
        self.srv._genres_pour_le_chef = lambda: GENRES

    def infos(self, **extra):
        return {"parent": str(self.rangement), "nom": "Casse-briques", "mots_interdits": ["secretcorp"],
                "facturation": False, "github": False, "description": "Un jeu de casse-briques pour téléphone.", **extra}

    def nouveau(self, **extra):
        statut, corps = self.post("/api/creations/infos", self.infos(**extra))
        self.assertEqual(statut, 200, corps)
        return corps["brouillon"]

    def attendre(self, id_):
        for _ in range(300):
            v = self.json(f"/api/creations?id={id_}")["brouillon"]
            if v["tour"] != "en_cours":
                return v
            time.sleep(0.05)
        self.fail("le tour ne finit pas")

    def tour(self, id_, **corps):
        statut, r = self.post("/api/creations/tour", {"id": id_, **corps})
        self.assertEqual(statut, 200, r)
        return r["brouillon"]

    def pret(self, **extra):
        """Un brouillon qui a une proposition."""
        self.srv.appeler_jugement = Faux(proposition(genre="jeu-web", nouveau=None, **extra))
        b = self.nouveau()
        self.tour(b["id"], proposer_maintenant=True)
        v = self.attendre(b["id"])
        self.assertIsNotNone(v["proposition"], v)
        return v


class TestRoutesCreations(AvecCreations):
    def test_infos_controle_et_cree_le_brouillon(self):
        v = self.nouveau()
        self.assertEqual((v["infos"]["nom"], v["tour"], v["tours"], v["echange"]), ("Casse-briques", "libre", 0, []))
        self.assertIsNone(v["proposition"])
        self.assertTrue((self.creations / f"{v['id']}.json").is_file())
        # rien d'autre que le brouillon : ni dossier du projet, ni inscription au bureau commun
        self.assertFalse((self.rangement / "Casse-briques").exists())
        self.assertEqual(len(reglages.lire_bureau(self.fichier)["projets"]), 2)
        # les informations d'un brouillon se changent (le nom est nettoyé)
        statut, r = self.post("/api/creations/infos", self.infos(id=v["id"], nom="  Casse-murs "))
        self.assertEqual(statut, 200, r)
        self.assertEqual((r["brouillon"]["id"], r["brouillon"]["infos"]["nom"]), (v["id"], "Casse-murs"))
        self.assertEqual(len(list(self.creations.glob("c*.json"))), 1)

    def test_infos_refus_lisibles(self):
        cas = [({"nom": ""}, "nom"), ({"nom": "CON"}, "Windows"), ({"parent": str(self.tmp / "absent")}, "n'existe pas"),
               ({"mots_interdits": "x"}, "mots_interdits"), ({"github": "oui"}, "github"),
               ({"description": 3}, "description")]
        for extra, mot in cas:
            with self.subTest(extra=extra):
                statut, corps = self.post("/api/creations/infos", self.infos(**extra))
                self.assertEqual(statut, 400, corps)
                self.assertIn(mot.lower(), corps["erreur"].lower())
        (self.rangement / "Casse-briques").mkdir()
        statut, corps = self.post("/api/creations/infos", self.infos())
        self.assertEqual(statut, 400)
        self.assertIn("existe déjà", corps["erreur"])
        self.assertFalse(self.creations.exists() and list(self.creations.glob("c*.json")))

    def test_infos_description_obligatoire(self):
        for description in ("", "   ", None):
            statut, corps = self.post("/api/creations/infos", self.infos(description=description))
            self.assertEqual(statut, 400, description)
            self.assertIn("description", corps["erreur"].lower())
        corps = self.infos()
        del corps["description"]
        statut, r = self.post("/api/creations/infos", corps)
        self.assertEqual(statut, 400)
        self.assertFalse(self.creations.exists() and list(self.creations.glob("c*.json")))

    def test_infos_ne_laissent_aucune_cle(self):
        v = self.nouveau(cle_api="sk-secret")   # un champ inconnu est ignoré, jamais gardé
        brut = (self.creations / f"{v['id']}.json").read_text(encoding="utf-8")
        self.assertNotIn("sk-secret", brut)
        self.assertNotIn("cle_api", brut)

    def test_bureau_plein_refuse(self):
        d = json.loads(self.fichier.read_text(encoding="utf-8"))
        for i in range(reglages.MAX_PROJETS - 2):
            r = self.tmp / f"x{i}" / "reglages.json"
            r.parent.mkdir()
            r.write_text("{}", encoding="utf-8")
            d["projets"].append(str(r))
        self.fichier.write_text(json.dumps(d), encoding="utf-8")
        statut, corps = self.post("/api/creations/infos", self.infos())
        self.assertEqual(statut, 400)
        self.assertIn(str(reglages.MAX_PROJETS), corps["erreur"])

    def test_tour_rend_les_questions_et_le_cout(self):
        b = self.nouveau()
        v = self.tour(b["id"])
        self.assertIn(v["tour"], ("en_cours", "libre"))
        v = self.attendre(b["id"])
        self.assertEqual((v["tours"], v["tours_max"], v["tour"]), (1, 4, "libre"))
        self.assertEqual([q["id"] for q in v["echange"][-1]["questions"]], ["style", "niveaux"])
        self.assertGreater(v["cout"]["tokens"], 0)
        self.assertGreater(v["cout"]["euros"], 0)
        v = self.attendre(b["id"])
        self.srv.appeler_jugement = Faux(proposition(genre="jeu-web", nouveau=None))
        self.tour(b["id"], reponses=[{"question": "style", "texte": "Néon"}, {"question": "niveaux", "texte": "10"}])
        v = self.attendre(b["id"])
        self.assertIsNotNone(v["proposition"])
        self.assertEqual(v["echange"][1]["auteur"], "utilisateur")
        self.assertEqual(len(self.srv.appeler_jugement.dossiers), 1)
        # la liste des brouillons montre le coût
        liste = self.json("/api/creations")
        self.assertEqual([x["id"] for x in liste["brouillons"]], [b["id"]])
        self.assertGreater(liste["brouillons"][0]["euros"], 0)
        self.assertEqual(liste["brouillons"][0]["etat"], "proposition")

    def test_tour_refus_de_demande(self):
        b = self.nouveau()
        for corps in ({"id": b["id"], "reponses": [{"question": "style", "texte": "x"}]},   # rien n'est posé
                      {"id": b["id"], "correction": "x"},                                    # pas de proposition
                      {"id": b["id"], "reponses": "x"}, {"id": b["id"], "correction": 3},
                      {"id": b["id"], "proposer_maintenant": "oui"}, {"id": "../etc"}, {}):
            with self.subTest(corps=corps):
                statut, r = self.post("/api/creations/tour", corps)
                self.assertEqual(statut, 400, r)
        statut, r = self.post("/api/creations/tour", {"id": "c" + "0" * 12})
        self.assertEqual(statut, 400)
        self.assertEqual(self.srv.appeler_jugement.dossiers, [])

    def test_tour_deja_en_cours_refuse(self):
        bloque = self.srv.appeler_jugement = Bloque(QUESTIONS)
        b = self.nouveau()
        v = self.tour(b["id"])
        self.assertEqual(v["tour"], "en_cours")
        self.assertTrue(bloque.entre.wait(10))
        # la page relit : le tour est en cours, pas d'erreur
        lu = self.json(f"/api/creations?id={b['id']}")["brouillon"]
        self.assertEqual((lu["tour"], lu["erreur"]), ("en_cours", None))
        # un second envoi (autre onglet, autre appareil) est refusé et rien n'est rappelé
        statut, r = self.post("/api/creations/tour", {"id": b["id"]})
        self.assertEqual(statut, 409)
        self.assertEqual(r["erreur"], "Un tour est déjà en cours pour ce projet.")
        # on ne change pas les informations, on ne supprime pas, on ne valide pas pendant le tour
        statut, r = self.post("/api/creations/infos", self.infos(id=b["id"]))
        self.assertEqual(statut, 409)
        statut, r = self.post("/api/creations/supprimer", {"id": b["id"]})
        self.assertEqual(statut, 409)
        bloque.libere.set()
        v = self.attendre(b["id"])
        self.assertEqual((bloque.appels, v["tours"]), (1, 1))
        self.assertEqual(len(v["echange"]), 1)

    def test_tour_rate_se_refait_sans_rien_retaper(self):
        b = self.nouveau()
        self.srv.appeler_jugement = Faux("pas du json", "toujours pas")
        self.tour(b["id"])
        v = self.attendre(b["id"])
        self.assertTrue(v["erreur"])
        self.assertEqual((v["tours"], v["tour"]), (0, "libre"))
        self.srv.appeler_jugement = Faux(QUESTIONS)
        self.tour(b["id"])
        v = self.attendre(b["id"])
        self.assertEqual((v["tours"], v["erreur"]), (1, None))

    def test_valider_cree_et_liste_le_projet(self):
        v = self.pret()
        self.assertFalse((self.rangement / "Casse-briques").exists())
        statut, r = self.post("/api/creations/valider", {"id": v["id"], "installer": True})
        self.assertEqual(statut, 200, r)
        self.assertIs(r["ok"], True)
        self.assertIn("w-jeu-web", r["message"])
        self.assertTrue((self.rangement / "Casse-briques" / ".factory" / "factory.json").is_file())
        self.assertIn(r["projet"], [p["id"] for p in self.json("/api/projets")["projets"]])
        self.assertEqual(len(reglages.lire_bureau(self.fichier)["projets"]), 3)
        # le brouillon est retiré ; les usages vont au relevé du projet créé (par l'outil), pas aux abandonnés
        self.assertEqual(self.json("/api/creations")["brouillons"], [])
        self.assertEqual([c for c, _ in self.outil.appels].count("usage"), 1)
        self.assertEqual(self.json("/api/creations")["abandonnes"]["euros"], 0)
        self.assertEqual(self.git.appels + self.gh.appels, [])

    def test_valider_renvoie_aux_infos(self):
        v = self.pret()
        (self.rangement / "Casse-briques").mkdir()   # un projet de ce nom est né entre-temps
        statut, r = self.post("/api/creations/valider", {"id": v["id"]})
        self.assertEqual(statut, 409, r)
        self.assertEqual(r["retour"], "infos")
        self.assertIn("existe déjà", r["erreur"])
        # le brouillon et l'échange sont gardés, rien n'est inscrit
        garde = self.json(f"/api/creations?id={v['id']}")["brouillon"]
        self.assertEqual(len(garde["echange"]), len(v["echange"]))
        self.assertIsNotNone(garde["proposition"])
        self.assertEqual(len(reglages.lire_bureau(self.fichier)["projets"]), 2)
        # le nom changé, la validation passe
        statut, r = self.post("/api/creations/infos", self.infos(id=v["id"], nom="Casse-murs"))
        self.assertEqual(statut, 200, r)
        statut, r = self.post("/api/creations/valider", {"id": v["id"]})
        self.assertEqual(statut, 200, r)

    def test_valider_refus_lisibles(self):
        b = self.nouveau()
        statut, r = self.post("/api/creations/valider", {"id": b["id"]})
        self.assertEqual(statut, 400, r)       # pas de proposition
        self.assertNotIn("retour", r)
        v = self.pret()
        for corps in ({"id": v["id"], "fable": "x"}, {"id": v["id"], "installer": "oui"},
                      {"id": v["id"], "genre_description": 3}):
            statut, r = self.post("/api/creations/valider", corps)
            self.assertEqual(statut, 400, corps)
        statut, r = self.post("/api/creations/valider", {"id": v["id"], "fable": ["dev-1"]})   # Fable non suggéré
        self.assertEqual(statut, 400, r)
        self.assertFalse((self.rangement / "Casse-briques").exists())

    def test_supprimer_garde_le_cout(self):
        v = self.pret()
        avant = self.json("/api/creations")
        self.assertEqual(avant["abandonnes"]["euros"], 0)
        statut, r = self.post("/api/creations/supprimer", {"id": v["id"]})
        self.assertEqual((statut, r), (200, {"ok": True}))
        apres = self.json("/api/creations")
        self.assertEqual(apres["brouillons"], [])
        self.assertAlmostEqual(apres["abandonnes"]["euros"], avant["brouillons"][0]["euros"], places=4)
        self.assertGreater(apres["abandonnes"]["euros"], 0)
        statut, r = self.post("/api/creations/supprimer", {"id": v["id"]})
        self.assertEqual(statut, 400)

    def test_liste_purge_les_vieux_brouillons(self):
        v = self.nouveau()
        chemin = self.creations / f"{v['id']}.json"
        b = json.loads(chemin.read_text(encoding="utf-8"))
        b["maj"] = "2020-01-01T00:00:00"
        b["usages"] = [dict(USAGE, t="2020-01-01T00:00:00")]
        chemin.write_text(json.dumps(b), encoding="utf-8")
        liste = self.json("/api/creations")
        self.assertEqual(liste["brouillons"], [])
        self.assertGreater(liste["abandonnes"]["euros"], 0)

    def test_aucun_projet_tant_que_rien_n_est_valide(self):
        b = self.nouveau()
        self.tour(b["id"])
        self.attendre(b["id"])
        self.assertEqual(sorted(p.name for p in self.rangement.iterdir()), [])
        self.assertEqual(len(reglages.lire_bureau(self.fichier)["projets"]), 2)
        self.assertEqual(self.outil.appels, [])
        self.assertEqual(self.git.appels + self.gh.appels, [])

    def test_en_tetes_et_corps(self):
        for chemin in ("infos", "tour", "valider", "supprimer"):
            r, _ = self.req("POST", f"/api/creations/{chemin}", "{}", {"Content-Type": "application/json"})
            self.assertEqual(r.status, 403, chemin)
            r, _ = self.req("POST", f"/api/creations/{chemin}", "{", ENT)
            self.assertEqual(r.status, 400, chemin)
            r, _ = self.req("POST", f"/api/creations/{chemin}", "[]", ENT)
            self.assertEqual(r.status, 400, chemin)

    def test_sans_bureau_commun_409(self):
        self.srv.fichier_bureau = None
        statut, r = self.post("/api/creations/infos", self.infos())
        self.assertEqual(statut, 409)
        self.assertEqual(self.get_statut("/api/creations"), 409)

    def get_statut(self, chemin):
        r, _ = self.req("GET", chemin)
        return r.status

    def test_brouillon_inconnu(self):
        self.assertEqual(self.get_statut("/api/creations?id=c" + "0" * 12), 404)
        self.assertEqual(self.get_statut("/api/creations?id=..%2Fx"), 404)


class TestCreationsExigeLeCode(AvecBureauOuvert):
    def test_les_routes_exigent_le_code_d_acces(self):
        ent = {"X-Bureau": "1", "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{self.distant}",
               "Host": f"127.0.0.1:{self.distant}"}
        r, _ = self.req("GET", "/api/creations", None, {"Host": ent["Host"]})
        self.assertEqual(r.status, 401)
        for chemin in ("infos", "tour", "valider", "supprimer"):
            r, _ = self.req("POST", f"/api/creations/{chemin}", json.dumps({"id": "x"}), ent)
            self.assertEqual(r.status, 401, chemin)
        cookie = self.associer()
        r, data = self.req("POST", "/api/creations/infos", json.dumps({"parent": 3, "nom": "x"}), {**ent, "Cookie": cookie})
        self.assertEqual(r.status, 400, data)      # le code est accepté, c'est le corps qui est refusé
        self.assertFalse((self.tmp / "x").exists())


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
