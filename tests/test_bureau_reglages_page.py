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
                                        "deport.recette-emulateur", "deport.service", "lecons_auto", "analyse_blocages",
                                        "une_session_moyenne", "livraison_sur_demande", "cloud_dossier_approuve",
                                        "livraison_github", "signature_apk", "outils_agents_serveur"])
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
        self.assertEqual(reglages.lire_bureau(self.bureau)["deport_lieux_explicites"], {"lint": "github"})
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

    def test_le_bureau_demarre_sur_un_fichier_aux_cles_inconnues(self):
        """Un `reglages` inconnu (écrit à la main, ou par la phase suivante après un retour arrière) et un `types`
        abîmé : le bureau démarre, l'état répond, le niveau global valide reste lu."""
        android = ANDROID
        self.bureau.write_text(json.dumps({"projets": ["demo/reglages.json"], "reglages": {"lecons_auto": True},
                                           "deport": {"lieux": {"apk": "github"}},
                                           "types": {"Mauvais": {}, android: {"deport": {"lieux": {"zzz": "poste"}}}}}),
                               encoding="utf-8")
        self.demarrer()
        r, data = self.req("GET", "/api/etat")
        self.assertEqual(r.status, 200)
        lignes = self.lignes()
        self.assertEqual((lignes["deport.apk"]["valeur"], lignes["deport.apk"]["origine"]), ("github", "global"))

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


class TestGardeFousDuServeur(AvecFichierDuBureau):
    """Les garde-fous de l'ancien bloc Direction : « Serveur » seulement pour une action que `deporter` y sert, et la
    recette sur serveur seulement quand un serveur est déclaré ; publiés pour la page et vérifiés à l'écriture."""
    RECETTE = "deport.recette-emulateur"

    def setUp(self):
        super().setUp()
        from bureau import serveurs as modserveurs
        self.plateforme = self.tmp / "plateforme"
        self.plateforme.mkdir()
        ancien = modserveurs.DOSSIER
        modserveurs.DOSSIER = self.plateforme          # jamais les serveurs déclarés du vrai poste
        self.addCleanup(setattr, modserveurs, "DOSSIER", ancien)

    def declarer_un_serveur(self):
        (self.plateforme / "serveurs.json").write_text(json.dumps(
            [{"id": "s1", "nom": "S1", "hote": "s1.example.org", "utilisateur": "ubuntu", "cle": "C:/cles/s1"}]),
            encoding="utf-8")

    def test_le_service_permanent_se_regle_sur_serveur(self):
        """Essai réel (FM_Stats, 2026-11-25) : « Serveur (bientôt) » grisé pour « Service permanent »."""
        self.declarer_un_serveur()
        ligne = self.lignes()["deport.service"]
        self.assertTrue(ligne["servie_au_serveur"])
        r, rep = self.poster("projet", "deport.service", "serveur")
        self.assertEqual(r.status, 200, rep)
        self.assertEqual(rep["valeur"], "serveur")

    def test_servie_au_serveur_publiee_par_ligne(self):
        lignes = self.lignes()
        self.assertIs(lignes[self.RECETTE]["servie_au_serveur"], True)
        for a in ("apk", "tests", "emulateur", "charge"):
            self.assertIs(lignes["deport." + a]["servie_au_serveur"], False, a)
        e = self.etat()
        self.assertIs(e["deport"]["serveur_declare"], False)

    def test_serveur_refuse_pour_une_action_non_servie(self):
        for niveau, id_ in (("projet", "deport.apk"), ("global", "deport.charge"), ("projet", "deport.emulateur")):
            r, rep = self.poster(niveau, id_, "serveur")
            self.assertEqual(r.status, 400, (niveau, id_))
            self.assertIn("bientôt", rep["erreur"])
        self.assertEqual(self.bureau_brut(), {"projets": ["demo/reglages.json"]})

    def test_recette_sur_serveur_refusee_sans_serveur_declare(self):
        r, rep = self.poster("projet", self.RECETTE, "serveur")
        self.assertEqual(r.status, 400, rep)
        self.assertIn("déclarez d'abord un serveur", rep["erreur"])
        self.assertNotIn("recette-emulateur", json.dumps(self.projet_brut()))
        self.declarer_un_serveur()
        r, ligne = self.poster("projet", self.RECETTE, "serveur")
        self.assertEqual(r.status, 200, ligne)
        self.assertEqual((ligne["valeur"], ligne["origine"]), ("serveur", "projet"))
        r, ligne = self.poster("projet", self.RECETTE, None)      # le retour à « non réglé » reste permis
        self.assertEqual(r.status, 200, ligne)


class TestRouteEtDisponibilites(AvecFichierDuBureau):
    def test_une_panne_d_ecriture_donne_500_lisible(self):
        with mock.patch.object(reglages, "fixer_niveau_bureau", side_effect=PermissionError("fichier tenu")):
            r, rep = self.poster("global", "deport.apk", "github")
        self.assertEqual(r.status, 500)
        self.assertTrue(rep["erreur"].startswith("Erreur du bureau : "), rep)
        self.assertIn("fichier tenu", rep["erreur"])
        self.assertLessEqual(len(rep["erreur"]), 200)

    def test_global_disponible_avec_le_fichier_du_bureau(self):
        page = self.etat()["reglages_page"]
        self.assertIs(page["global_disponible"], True)
        self.assertEqual(page["ignores"], [])

    def test_les_cles_ignorees_sont_publiees(self):
        self.bureau.write_text(json.dumps({"projets": ["demo/reglages.json"], "reglages": {"inconnu": 1}}),
                               encoding="utf-8")
        ignores = self.etat()["reglages_page"]["ignores"]
        self.assertEqual(len(ignores), 1)
        self.assertIn("inconnu", ignores[0])

    def test_l_etat_publie_les_valeurs_effectives(self):
        """Les cases de la Direction et le compteur des leçons suivent la valeur effective (projet > type > global)."""
        self.en_android()
        tout = {"lecons_auto": True, "analyse_blocages": False, "livraison_sur_demande": True,
                "une_session_moyenne": False, "cloud_dossier_approuve": True, "livraison_github": True}
        self.bureau.write_text(json.dumps({"projets": ["demo/reglages.json"], "reglages": tout,
                                           "types": {ANDROID: {"reglages": {"une_session_moyenne": True}}}}),
                               encoding="utf-8")
        e = self.etat()
        self.assertEqual({k: e[k] for k in tout}, {"lecons_auto": True, "analyse_blocages": False,
                                                   "livraison_sur_demande": True, "une_session_moyenne": True,
                                                   "cloud_dossier_approuve": False, "livraison_github": False})
        b = self.projet_brut()
        b["lecons_auto"] = False
        self.regl.write_text(json.dumps(b), encoding="utf-8")
        self.assertIs(self.etat()["lecons_auto"], False)

    def test_une_valeur_globale_qui_n_est_pas_un_booleen_est_ignoree_et_dite(self):
        self.bureau.write_text(json.dumps({"projets": ["demo/reglages.json"], "reglages": {"lecons_auto": "oui"}}),
                               encoding="utf-8")
        e = self.etat()
        self.assertIs(e["lecons_auto"], False)
        self.assertEqual(len(e["reglages_page"]["ignores"]), 1)
        self.assertIn("lecons_auto", e["reglages_page"]["ignores"][0])
        self.assertEqual(next(l for l in e["reglages_page"]["lignes"] if l["id"] == "lecons_auto")["origine"], "defaut")


class TestBureauDUnSeulProjet(AvecServeur):
    """`creer(chemin_reglages)` sans fichier du bureau : seul le niveau projet existe."""

    def test_global_indisponible(self):
        self.srv.projet()._cache_etat = (0.0, None)
        page = self.json("/api/etat")["reglages_page"]
        self.assertIs(page["global_disponible"], False)
        self.assertIs(page["type_disponible"], False)      # le niveau type vit aussi dans le fichier du bureau
        r, data = self.req("POST", "/api/reglages/niveau",
                           json.dumps({"niveau": "global", "id": "deport.apk", "valeur": "github"}), self.ENT)
        self.assertEqual(r.status, 400)


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


TROIS = ("lecons_auto", "analyse_blocages", "une_session_moyenne", "livraison_sur_demande")
PROJET_SEUL = ("cloud_dossier_approuve", "livraison_github")


class TestReglagesACases(AvecFichierDuBureau):
    """Les six réglages à cases du registre, avec les vraies déclarations."""

    def defaut(self, id_):
        return next(r for r in registre.REGISTRE if r.id == id_).defaut

    def test_le_registre_declare_les_six(self):
        self.assertEqual({r.id for r in registre.REGISTRE if r.forme == "booleen"}, set(TROIS + PROJET_SEUL))
        # les réglages à choix fermé (signature des APK, profil d'outils des agents du serveur) : section serveur, trois niveaux
        self.assertEqual({r.id: (r.section, r.niveaux) for r in registre.REGISTRE if r.forme == "choix"},
                         {"signature_apk": ("serveur", registre.NIVEAUX), "outils_agents_serveur": ("serveur", registre.NIVEAUX)})
        for r in (x for x in registre.REGISTRE if x.forme == "booleen"):
            self.assertEqual((r.cle, r.section, r.forme), (r.id, "automatisations", "booleen"))
            self.assertEqual(r.niveaux, ("projet",) if r.id in PROJET_SEUL else registre.NIVEAUX)

    def test_cascade_complete_par_reglage(self):
        self.en_android()
        for id_ in TROIS:
            with self.subTest(id_):
                d = self.defaut(id_)
                ligne = self.lignes()[id_]
                self.assertEqual((ligne["valeur"], ligne["origine"], ligne["defaut"], ligne["section"]),
                                 (d, "defaut", d, "automatisations"))
                r, ligne = self.poster("global", id_, not d)
                self.assertEqual((r.status, ligne["valeur"], ligne["origine"]), (200, not d, "global"))
                r, ligne = self.poster("type", id_, d)
                self.assertEqual((ligne["valeur"], ligne["origine"]), (d, "type:" + ANDROID))
                r, ligne = self.poster("projet", id_, not d)
                self.assertEqual((ligne["valeur"], ligne["origine"]), (not d, "projet"))
                self.assertEqual(self.projet_brut()[id_], not d)
                r, ligne = self.poster("projet", id_, None)
                self.assertEqual((ligne["valeur"], ligne["origine"]), (d, "type:" + ANDROID))
                self.assertNotIn(id_, self.projet_brut())
                r, ligne = self.poster("type", id_, None)
                self.assertEqual((ligne["valeur"], ligne["origine"]), (not d, "global"))
                r, ligne = self.poster("global", id_, None)
                self.assertEqual((ligne["valeur"], ligne["origine"]), (d, "defaut"))
                self.assertNotIn("reglages", self.bureau_brut())
                self.assertNotIn("types", self.bureau_brut())

    def test_projet_seul_refuse_global_et_type(self):
        self.en_android()
        for id_ in PROJET_SEUL:
            for niveau in ("global", "type"):
                with self.subTest(id_ + niveau):
                    avant = self.bureau.read_text(encoding="utf-8")
                    r, rep = self.poster(niveau, id_, True)
                    self.assertEqual(r.status, 400, rep)
                    self.assertEqual(self.bureau.read_text(encoding="utf-8"), avant)
            r, ligne = self.poster("projet", id_, True)
            self.assertEqual((r.status, ligne["valeur"], ligne["origine"]), (200, True, "projet"))
            self.assertEqual(ligne["niveaux"], ["projet"])

    def test_valeurs_actuelles_conservees(self):
        self.regl.write_text(json.dumps({"lecons_auto": True, "analyse_blocages": False}), encoding="utf-8")
        lignes = self.lignes()
        self.assertEqual((lignes["lecons_auto"]["valeur"], lignes["lecons_auto"]["origine"]), (True, "projet"))
        self.assertEqual((lignes["analyse_blocages"]["valeur"], lignes["analyse_blocages"]["origine"]),
                         (False, "projet"))
        self.assertEqual((lignes["une_session_moyenne"]["valeur"], lignes["une_session_moyenne"]["origine"]),
                         (False, "defaut"))
        self.assertIs(lignes["lecons_auto"]["applicable"], True)
        self.assertEqual(lignes["lecons_auto"]["forme"], "booleen")

    def test_projet_garde_sa_valeur_si_global_change(self):
        self.regl.write_text(json.dumps({"lecons_auto": False}), encoding="utf-8")
        r, ligne = self.poster("global", "lecons_auto", True)
        self.assertEqual((ligne["valeur"], ligne["origine"]), (False, "projet"))
        self.assertIs(self.projet_brut()["lecons_auto"], False)
        self.assertEqual(self.bureau_brut()["reglages"], {"lecons_auto": True})

    def test_valeur_de_mauvaise_forme_refusee(self):
        for valeur in ("oui", 1, [True]):
            r, rep = self.poster("global", "lecons_auto", valeur)
            self.assertEqual(r.status, 400, valeur)
        self.assertNotIn("reglages", self.bureau_brut())


class TestValidationDuBureau(unittest.TestCase):
    """`fixer_niveau_bureau` valide avant d'écrire : un fichier du bureau n'est jamais rendu suspect."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        self.dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self.dossier.cleanup)
        (Path(self.dossier.name) / "p").mkdir()
        (Path(self.dossier.name) / "p" / "reglages.json").write_text("{}", encoding="utf-8")
        self.chemin = Path(self.dossier.name) / "bureau.json"
        self.chemin.write_text(json.dumps({"projets": ["p/reglages.json"]}), encoding="utf-8")

    def refuse(self, chemin_cle, valeur):
        avant = self.chemin.read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            reglages.fixer_niveau_bureau(self.chemin, chemin_cle, valeur)
        self.assertEqual(self.chemin.read_text(encoding="utf-8"), avant)

    def test_refus_avant_ecriture(self):
        self.refuse(("reglages", "inconnu"), True)
        self.refuse(("types", "android", "reglages", "inconnu"), True)
        self.refuse(("reglages", "livraison_github"), True)
        self.refuse(("types", "android", "reglages", "cloud_dossier_approuve"), True)
        self.refuse(("reglages", "lecons_auto"), "oui")
        self.refuse(("types", "android", "reglages", "lecons_auto"), 1)
        self.refuse(("reglages",), True)
        self.refuse(("reglages", "lecons_auto", "x"), True)

    def test_ecriture_valide_et_effacement(self):
        reglages.fixer_niveau_bureau(self.chemin, ("reglages", "lecons_auto"), True)
        reglages.fixer_niveau_bureau(self.chemin, ("types", "android", "reglages", "lecons_auto"), False)
        lu = reglages.lire_bureau(self.chemin)
        self.assertEqual((lu["reglages"], lu["types"]["android"]["reglages"]),
                         ({"lecons_auto": True}, {"lecons_auto": False}))
        reglages.fixer_niveau_bureau(self.chemin, ("reglages", "lecons_auto"), None)
        self.assertEqual(reglages.lire_bureau(self.chemin)["reglages"], {})

    def test_lieux_inchanges(self):
        reglages.fixer_niveau_bureau(self.chemin, ("deport", "lieux", "tests"), "github")
        self.assertEqual(reglages.lire_bureau(self.chemin)["deport_lieux_explicites"], {"tests": "github"})


class TestEcrivainManquant(AvecServeur):
    def test_reglage_sans_fixer_echoue_a_la_construction(self):
        sans = registre.Reglage("zzz", "automatisations", "Zzz", "", "booleen", registre.NIVEAUX, False, "zzz")
        with mock.patch.object(registre, "REGISTRE", (sans,)):
            with self.assertRaises(ValueError) as e:
                serveur.Projet("demo", self.regl)
        self.assertIn("fixer_zzz", str(e.exception))

    def test_forme_inconnue_refusee(self):
        bizarre = registre.Reglage("lecons_auto", "s", "Bizarre", "", "couleur", registre.NIVEAUX, None, "lecons_auto")
        with self.assertRaises(ValueError):
            registre.verifier_valeur(bizarre, "rouge")


if __name__ == "__main__":
    unittest.main()
