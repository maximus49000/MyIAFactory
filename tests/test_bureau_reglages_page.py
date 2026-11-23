"""Essai réel : la page Réglages lit et écrit chaque réglage à son niveau (global, type, projet)."""
import json
import threading
import unittest
from unittest import mock

from bureau import registre, reglages, serveur
from tests.test_serveur import AvecServeur, SourceSimulee

ANDROID = "application-mobile-android"


class AvecFichierDuBureau(AvecServeur):
    """Un bureau lancé sur un fichier du bureau (les niveaux global et type y vivent), un seul projet « demo »."""

    def demarrer(self, source=None):
        self.bureau = self.tmp / "bureau.json"
        if not self.bureau.exists():
            self.bureau.write_text(json.dumps({"projets": ["demo/reglages.json"]}), encoding="utf-8")
        self.source = source or SourceSimulee()
        self.srv = serveur.creer(bureau=self.bureau, port=0, ouvrir=self.source)
        self.port = self.srv.server_address[1]
        self.fil = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.fil.start()
        self.addCleanup(self.arreter, self.srv)

    @property
    def p(self):
        return self.srv.projet()

    def poster(self, niveau, id_, valeur, entetes=None):
        r, data = self.req("POST", "/api/reglages/niveau",
                           json.dumps({"niveau": niveau, "id": id_, "valeur": valeur}), entetes or self.ENT)
        return r, json.loads(data.decode("utf-8"))

    def etat(self):
        self.p._cache_etat = (0.0, self.p._cache_etat[1])
        return self.json("/api/etat")

    def lignes(self):
        return {l["id"]: l for l in self.etat()["reglages_page"]["lignes"]}

    def bureau_brut(self):
        return json.loads(self.bureau.read_text(encoding="utf-8"))

    def projet_brut(self):
        return json.loads(self.regl.read_text(encoding="utf-8"))

    def en_android(self):
        (self.tmp / "demo" / "factory.json").write_text(json.dumps({"genre": ANDROID}), encoding="utf-8")


class TestReglagesPage(AvecFichierDuBureau):
    def test_etat_publie_les_lignes_de_deport_avec_origine(self):
        b = self.bureau_brut()
        b["deport"] = {"lieux": {"apk": "github"}}
        self.bureau.write_text(json.dumps(b), encoding="utf-8")
        page = self.etat()["reglages_page"]
        self.assertEqual((page["genre"], page["type_disponible"]), (None, False))
        lignes = {l["id"]: l for l in page["lignes"]}
        self.assertEqual(list(lignes), ["deport.apk", "deport.tests", "deport.emulateur", "deport.charge",
                                        "deport.recette-emulateur"])
        apk = lignes["deport.apk"]
        self.assertEqual((apk["valeur"], apk["origine"], apk["valeurs"]), ("github", "global", {"global": "github"}))
        self.assertEqual((apk["section"], apk["forme"], apk["applicable"]), ("actions", "lieu", True))
        self.assertEqual(apk["niveaux"], ["global", "type", "projet"])
        self.assertEqual((lignes["deport.tests"]["valeur"], lignes["deport.tests"]["origine"]), ("poste", "defaut"))
        self.assertEqual(lignes["deport.emulateur"]["choix"], ["poste", "serveur"])
        recette = lignes["deport.recette-emulateur"]
        self.assertEqual((recette["niveaux"], recette["valeur"], recette["origine"]), (["projet"], None, "defaut"))
        self.assertEqual((apk["defaut"], recette["defaut"]), ("poste", None))

    def test_poser_global_puis_projet_l_emporte(self):
        r, ligne = self.poster("global", "deport.tests", "github")
        self.assertEqual(r.status, 200, ligne)
        self.assertEqual((ligne["valeur"], ligne["origine"]), ("github", "global"))
        self.assertEqual(self.bureau_brut()["deport"]["lieux"], {"tests": "github"})
        r, ligne = self.poster("projet", "deport.tests", "poste")
        self.assertEqual(r.status, 200, ligne)
        self.assertEqual((ligne["valeur"], ligne["origine"]), ("poste", "projet"))
        self.assertEqual(ligne["valeurs"], {"global": "github", "projet": "poste"})
        self.assertEqual(self.projet_brut()["deport"]["lieux"], {"tests": "poste"})
        self.assertEqual(self.etat()["deport"]["lieux"]["tests"], "poste")
        # un nouveau réglage global ne change pas un projet qui a sa valeur propre
        self.poster("global", "deport.tests", "poste")
        self.poster("global", "deport.tests", "github")
        self.assertEqual(self.lignes()["deport.tests"]["valeur"], "poste")

    def test_effacer_projet_redonne_l_herite(self):
        self.poster("global", "deport.tests", "github")
        self.poster("projet", "deport.tests", "poste")
        r, ligne = self.poster("projet", "deport.tests", None)
        self.assertEqual(r.status, 200, ligne)
        self.assertEqual((ligne["valeur"], ligne["origine"]), ("github", "global"))
        self.assertNotIn("tests", self.projet_brut()["deport"]["lieux"])
        r, ligne = self.poster("global", "deport.tests", None)
        self.assertEqual((ligne["valeur"], ligne["origine"]), ("poste", "defaut"))
        self.assertNotIn("deport", self.bureau_brut())   # objets vidés élagués

    def test_type_sans_genre_refuse_400(self):
        r, rep = self.poster("type", "deport.apk", "github")
        self.assertEqual(r.status, 400)
        self.assertIn("type", rep["erreur"])
        self.assertNotIn("types", self.bureau_brut())

    def test_niveau_global_pour_recette_refuse(self):
        for niveau in ("global", "type"):
            r, rep = self.poster(niveau, "deport.recette-emulateur", "serveur")
            self.assertEqual(r.status, 400, niveau)
        self.assertEqual(self.bureau_brut(), {"projets": ["demo/reglages.json"]})

    def test_lieu_hors_choix_refuse(self):
        for niveau, valeur, id_ in (("projet", "github", "deport.emulateur"), ("global", "nuage", "deport.apk"),
                                    ("global", "serveur", "deport.tests"), ("global", 3, "deport.apk")):
            r, rep = self.poster(niveau, id_, valeur)
            self.assertEqual(r.status, 400, (niveau, valeur))
            self.assertTrue(rep["erreur"])
        reglages.lire_bureau(self.bureau)     # le fichier du bureau reste lisible
        self.assertEqual(self.bureau_brut(), {"projets": ["demo/reglages.json"]})

    def test_niveau_ou_id_inconnu_refuse(self):
        for niveau, id_ in (("monde", "deport.apk"), ("global", "deport.zzz"), ("global", "zzz"), ("global", None)):
            r, rep = self.poster(niveau, id_, "poste")
            self.assertEqual(r.status, 400, (niveau, id_))

    def test_action_inapplicable_refusee_au_projet(self):
        r, rep = self.poster("projet", "deport.lint", "poste")     # projet générique : pas de lint
        self.assertEqual(r.status, 400)
        self.assertIn("lint", rep["erreur"])

    def test_global_inapplicable_accepte_et_ignore(self):
        r, ligne = self.poster("global", "deport.lint", "github")
        self.assertEqual(r.status, 200, ligne)
        self.assertIs(ligne["applicable"], False)
        self.assertEqual(self.bureau_brut()["deport"]["lieux"], {"lint": "github"})
        e = self.etat()
        self.assertNotIn("deport.lint", {l["id"] for l in e["reglages_page"]["lignes"]})
        self.assertNotIn("lint", e["deport"]["lieux"])

    def test_fichier_du_bureau_abime_ne_casse_pas_l_etat(self):
        for contenu in ("{pas du json", json.dumps({"projets": ["demo/reglages.json"], "types": {"x": 3}}),
                        json.dumps({"projets": ["demo/reglages.json"], "reglages": {"inconnu": True}})):
            self.bureau.write_text(contenu, encoding="utf-8")
            r, data = self.req("GET", "/api/etat")
            self.assertEqual(r.status, 200, contenu)
            e = self.etat()
            self.assertTrue("reglages_page" in e or "reglages_page_erreur" in e)
            if "reglages_page" in e:
                origines = {l["origine"] for l in e["reglages_page"]["lignes"]}
                self.assertEqual(origines, {"defaut"}, contenu)

    def test_une_panne_de_la_page_ne_coupe_pas_l_etat(self):
        with mock.patch.object(serveur.Projet, "reglages_page", side_effect=RuntimeError("boum")):
            e = self.etat()
        self.assertNotIn("reglages_page", e)
        self.assertIn("boum", e["reglages_page_erreur"])
        self.assertIn("deport", e)

    def test_en_tetes_requis(self):
        r, _ = self.poster("global", "deport.apk", "github", {"Content-Type": "application/json"})
        self.assertEqual(r.status, 403)
        r, _ = self.poster("global", "deport.apk", "github", {"X-Bureau": "1", "Content-Type": "text/plain"})
        self.assertEqual(r.status, 403)
        r, data = self.req("POST", "/api/reglages/niveau", "x" * 70000, self.ENT)
        self.assertEqual(r.status, 400)
        self.assertNotIn("deport", self.bureau_brut())

    def test_type_agit_sur_le_workflow(self):
        self.en_android()
        self.assertIs(self.etat()["reglages_page"]["type_disponible"], True)
        r, ligne = self.poster("type", "deport.apk", "github")
        self.assertEqual(r.status, 200, ligne)
        self.assertEqual((ligne["valeur"], ligne["origine"]), ("github", "type:" + ANDROID))
        self.assertEqual(self.bureau_brut()["types"][ANDROID]["deport"]["lieux"], {"apk": "github"})
        self.assertEqual(self.p.reglages_deport()["deport"]["lieux"]["apk"], "github")
        self.assertEqual(self.etat()["deport"]["lieux"]["apk"], "github")

    def test_ancienne_route_inchangee(self):
        r, data = self.req("POST", "/api/reglages", json.dumps({"deport": {"lieux": {"apk": "github"}}}), self.ENT)
        self.assertEqual(r.status, 200, data)
        self.assertEqual(self.lignes()["deport.apk"]["origine"], "projet")


class TestReglageBooleenParLaTable(AvecFichierDuBureau):
    """Un réglage booléen déclaré au registre s'écrit par la même table (les déclarations viennent à la tâche 7)."""
    LECONS = registre.Reglage("lecons_auto", "automatisations", "Valider les leçons automatiquement", "",
                              "booleen", registre.NIVEAUX, False, "lecons_auto")

    def setUp(self):
        for module in (registre, reglages):
            p = mock.patch.object(module, "REGISTRE", (self.LECONS,))
            p.start()
            self.addCleanup(p.stop)
        super().setUp()

    def test_booleen_aux_trois_niveaux(self):
        r, ligne = self.poster("global", "lecons_auto", True)
        self.assertEqual(r.status, 200, ligne)
        self.assertEqual((ligne["valeur"], ligne["origine"], ligne["forme"]), (True, "global", "booleen"))
        self.assertEqual(self.bureau_brut()["reglages"], {"lecons_auto": True})
        r, ligne = self.poster("projet", "lecons_auto", False)
        self.assertEqual((ligne["valeur"], ligne["origine"]), (False, "projet"))
        self.assertIs(self.projet_brut()["lecons_auto"], False)
        r, ligne = self.poster("projet", "lecons_auto", None)
        self.assertEqual((ligne["valeur"], ligne["origine"]), (True, "global"))
        self.assertNotIn("lecons_auto", self.projet_brut())
        r, rep = self.poster("global", "lecons_auto", "oui")
        self.assertEqual(r.status, 400)
        self.assertIn("lecons_auto", {l["id"] for l in self.etat()["reglages_page"]["lignes"]})

    def test_la_ligne_booleenne_porte_son_defaut(self):
        ligne = {l["id"]: l for l in self.etat()["reglages_page"]["lignes"]}["lecons_auto"]
        self.assertIs(ligne["defaut"], False)


if __name__ == "__main__":
    unittest.main()
