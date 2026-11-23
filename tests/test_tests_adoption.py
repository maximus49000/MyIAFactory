"""Adoption des tests au serveur par projet (`outils/tests_adoption.py`, tâche 15b) : route, image, réseau et profil simulés."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
import tests_adoption as ta  # noqa: E402
import tests_profil as tp  # noqa: E402
import tests_serveur  # noqa: E402
from bureau.deport_types import ANDROID  # noqa: E402

FIXTURES = RACINE / "tests" / "fixtures" / "profils"
SANS_CHEMIN = ("dotnet-framework", "xcode", "python-sans-marqueur-et-dotnet-framework", "inconnu")


def analyse(racine, **kw):
    kw.setdefault("catalogue", {})
    return tp.analyser(racine, **kw)


class Faux:
    """Une route, un registre d'images et un accord de réseau simulés ; compte ce qui est envoyé."""

    def __init__(self, code=0, sortie="Ran 12 tests in 0.5s\n\nOK\n", messages=()):
        self.appels, self.code, self.sortie, self.messages = [], code, sortie, list(messages)

    def route(self, commande, racine, delai, **kw):
        self.appels.append((commande, racine, delai))
        return {"code": self.code, "sortie": self.sortie, "messages": self.messages}


def evaluer(cas, faux, **kw):
    kw.setdefault("analyse", analyse)
    kw.setdefault("reseau", lambda r: True)
    kw.setdefault("image_connue", lambda s, e: True)
    return ta.evaluer(str(FIXTURES / cas), route=faux.route, **kw)


class AdoptionTest(unittest.TestCase):
    def test_toutes_les_familles_ont_un_chemin(self):
        for cas in sorted(p.name for p in FIXTURES.iterdir()):
            if cas in SANS_CHEMIN:
                continue
            with self.subTest(cas=cas):
                faux = Faux()
                r = evaluer(cas, faux)
                self.assertNotEqual(r["statut"], "non_deportable", r)
                self.assertIn(r["statut"], ta.STATUTS)

    def test_non_deportable_n_envoie_rien_et_dit_la_raison(self):
        for cas, n in (("dotnet-framework", "N1"), ("xcode", "N2")):
            with self.subTest(cas=cas):
                faux = Faux()
                r = evaluer(cas, faux)
                self.assertEqual(r["statut"], "non_deportable")
                self.assertIn(n, r["raison"])
                self.assertEqual(faux.appels, [])

    def test_image_a_construire_ne_construit_rien_sans_reponse(self):
        faux, construites = Faux(), []
        r = evaluer("go", faux, image_connue=lambda s, e: False)
        # Go n'a pas d'image au catalogue : image dérivée, rien n'est construit ni envoyé
        self.assertEqual((r["statut"], r["attend"]), ("image_a_construire", "image"))
        self.assertIn("dockerfile", r["decision"])
        self.assertEqual((faux.appels, construites), ([], []))
        # la réponse « construire » : seul `construire` construit, puis la campagne part
        r = evaluer("go", faux, image_connue=lambda s, e: False, construire=lambda p: construites.append(p) or True)
        self.assertEqual((r["statut"], len(construites), len(faux.appels)), ("passe", 1, 1))

    def test_reseau_code_attend_l_accord(self):
        faux = Faux()
        r = evaluer("gradle-android", faux, reseau=lambda racine: False)
        self.assertEqual((r["statut"], r["attend"]), ("image_a_construire", "reseau"))
        self.assertEqual(faux.appels, [])
        self.assertEqual(evaluer("gradle-android", faux)["statut"], "passe")

    def test_myfridgecleaner_chemin_complet(self):
        faux = Faux(0, "BUILD SUCCESSFUL\n12 tests completed\n")
        r = evaluer("gradle-android", faux, analyse=lambda racine, **kw: analyse(racine, catalogue=ANDROID, **kw))
        self.assertEqual((r["statut"], r["image"]), ("passe", "myiafactory/tests-android"))
        self.assertEqual(faux.appels[0][0], ["./gradlew", "testDebugUnitTest"])
        self.assertEqual(faux.appels[0][2], 2700)

    def test_echoue_classe_et_propose_le_marqueur(self):
        lignes = [f"FAIL: test_{i} (m.C)\nTraceback\nAssertionError\n" for i in range(30)]
        lignes[0] = "FAIL: test_0 (m.C)\nFileNotFoundError: C:\\Users\\x\\f.txt\n"
        faux = Faux(1, "".join(lignes) + "Ran 30 tests\nFAILED (failures=30)\n")
        r = evaluer("python-stdlib", faux)
        self.assertEqual(r["statut"], "echoue")
        self.assertEqual(len(r["echecs"]), 20)
        self.assertEqual(r["echecs"][0]["classe"], "windows")
        self.assertEqual(r["echecs"][1]["classe"], "autre")
        self.assertIn("windows_seulement", r["marqueur"])
        r = evaluer("gradle-android", Faux(1, "Foo > bar FAILED\n"))
        self.assertIn("Assume", r["marqueur"])

    def test_classer_echec(self):
        self.assertEqual(ta.classer_echec("t", "open('C:\\\\Users\\\\a')"), "windows")
        self.assertEqual(ta.classer_echec("t", r"\\serveur\partage"), "windows")
        self.assertEqual(ta.classer_echec("t", "socket.gaierror: Name or service not known"), "reseau")
        self.assertEqual(ta.classer_echec("t", "KeyError: 'OPENAI_API_KEY'"), "secret")
        self.assertEqual(ta.classer_echec("t", "assert 1 == 2"), "autre")
        self.assertEqual(ta.classer_echec("t", "x" * 100000 + "C:\\Users"), "autre")     # 4 Ko au plus lus

    def test_marqueurs(self):
        self.assertIn("windows_seulement", ta.marqueur_pour("python"))
        self.assertIn("skipIf", ta.marqueur_pour("node"))
        self.assertIn("SkippableFact", ta.marqueur_pour("dotnet"))
        self.assertIn("cfg(windows)", ta.marqueur_pour("rust"))
        self.assertIn("t.Skip", ta.marqueur_pour("go"))
        self.assertIn("@EnabledOnOs", ta.marqueur_pour("maven"))

    def test_injoignable_ne_replie_pas_et_ne_reessaie_pas(self):
        faux = Faux(4, "", ["Serveur injoignable (session perdue avant le départ des tests : connexion)."])
        r = evaluer("python-stdlib", faux)
        self.assertEqual(r["statut"], "injoignable")
        self.assertEqual(len(faux.appels), 1)
        self.assertIn("injoignable", r["raison"])

    def test_trop_long_selon_la_famille(self):
        faux = Faux(124)
        r = evaluer("gradle-android", faux)
        self.assertEqual(r["statut"], "trop_long")
        self.assertIn("2700", r["raison"])
        self.assertEqual(evaluer("python-stdlib", Faux(124))["raison"].split()[2], "1800")

    def test_la_route_est_lancee_sans_repli_et_en_evaluation(self):
        vus = {}

        def executer(commande, **kw):
            vus.update(kw)
            kw["sortie"].write(b"Ran 3 tests\nOK\n")
            return 0
        ancien = tests_serveur.executer
        tests_serveur.executer = executer
        try:
            r = ta.route_par_defaut(["x"], "/p", 1800, accord=lambda _r: None)
        finally:
            tests_serveur.executer = ancien
        self.assertEqual((r["code"], vus["forcer"], vus["evaluation"]), (0, True, True))
        self.assertIn("Ran 3 tests", r["sortie"])
        self.assertEqual(vus["ressources_forcees"]("/p"), {"duree_s": 1800})

    def test_etapes(self):
        gradle = analyse(str(FIXTURES / "gradle-android"), catalogue=ANDROID)
        self.assertEqual(ta.etapes("x", gradle, {}), ["image", "sdk_android", "reseau", "echauffement", "evaluation"])
        self.assertEqual(ta.etapes("x", gradle, {"image": True, "reseau": True}), ["sdk_android", "echauffement", "evaluation"])
        py = analyse(str(FIXTURES / "python-stdlib"))
        self.assertEqual(ta.etapes("x", py, {}), ["image", "echauffement", "evaluation"])
        self.assertEqual(ta.etapes("x", analyse(str(FIXTURES / "xcode")), {}), [])

    def test_decision_ne_s_active_jamais_seule(self):
        faux = Faux()
        r = evaluer("python-stdlib", faux)
        self.assertEqual(r["statut"], "passe")
        # le verdict ne touche à aucun réglage : l'activation (`deport.lieux.tests`) reste la réponse du Directeur
        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "reglages.json")
            f.write_text(json.dumps({"deport": {"lieux": {"tests": "poste"}}}), encoding="utf-8")
            ta.noter_adoption(f, r)
            self.assertEqual(json.loads(f.read_text("utf-8"))["deport"], {"lieux": {"tests": "poste"}})

    def test_adoption_ecrite_par_le_bureau_pas_par_l_agent(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "reglages.json")
            f.write_text(json.dumps({"tests": {"profil_force": {"ressources": {"cpus": 6}}}}), encoding="utf-8")
            r = {"statut": "passe", "empreinte_profil": "abc", "image": "myiafactory/tests", "duree_s": 12, "nb_tests": 40}
            e = ta.noter_adoption(f, r, reseau_echauffement="accorde", date="2026-11-23T10:00:00")
            tests = json.loads(f.read_text("utf-8"))["tests"]
            self.assertEqual(tests["adoption"], e)
            self.assertEqual(tests["profil_force"], {"ressources": {"cpus": 6}})       # les autres clés sont gardées
            self.assertEqual(sorted(e), sorted(ta.CLES_ADOPTION))
        # la route ne lit que ce que le bureau enregistre : un fichier hors bureau n'est pas une adoption
        self.assertIsNone(ta.adoption_lue(str(FIXTURES / "go")))

    def test_reevaluation_quand_l_empreinte_change(self):
        p = analyse(str(FIXTURES / "python-stdlib"))
        self.assertFalse(ta.profil_change("x", p, {"empreinte_profil": p.empreinte}))
        self.assertTrue(ta.profil_change("x", p, {"empreinte_profil": "autre"}))
        self.assertFalse(ta.profil_change("x", p, None))
        # la route : empreinte différente -> poste une fois, en le disant ; jamais de campagne au serveur sur un profil non évalué
        signales = []
        with self.assertRaises(tests_serveur.Repli) as c:
            tests_serveur._controler_adoption(p, "x", lambda racine: {"empreinte_profil": "autre"}, signales.append)
        self.assertIn("profil changé", c.exception.raison)
        self.assertEqual(signales, ["x"])          # la décision `tests_profil` est posée (par l'outil du projet)
        tests_serveur._controler_adoption(p, "x", lambda racine: {"empreinte_profil": p.empreinte}, signales.append)
        tests_serveur._controler_adoption(p, "x", lambda racine: None, signales.append)  # jamais évalué : comportement d'avant
        self.assertEqual(signales, ["x"])
        # le signal par défaut ne fait jamais échouer la campagne (dossier sans projet)
        with tempfile.TemporaryDirectory() as d:
            tests_serveur._signaler_profil_par_defaut(d)

    def test_construire_image_seulement_la_somme_approuvee(self):
        p = analyse(str(FIXTURES / "go"))
        texte, sha = ta.tests_images.rendre_dockerfile(p)
        etiquette = ta.tests_images.etiquette_derivee(p)
        serveur = type("S", (), {"id": "ovh-1", "cle": "cle"})()

        class Ssh:
            def __init__(self, sortie=b"", code=0):
                self.appels, self.sortie, self.code = [], sortie, code

            def executer_octets(self, cible, commande, cle, entree=None, delai=60):
                self.appels.append((commande, entree, delai))
                return (0, b"", "") if "cat >" in commande else (self.code, self.sortie, "journal")

        notees, ssh = [], Ssh(f"construit\n#image {etiquette} 812\n".encode())
        orig = ta.tests_serveur.serveur_etat.cible
        ta.tests_serveur.serveur_etat.cible = lambda s: "u@h"
        self.addCleanup(setattr, ta.tests_serveur.serveur_etat, "cible", orig)
        ok = ta.construire_image(p, sha, serveur=serveur, ssh=ssh, noter=lambda *a: notees.append(a),
                                 maintenant="2026-11-23T10:00:00")
        self.assertTrue(ok)
        depot, construction = ssh.appels
        self.assertEqual(depot[1], texte.encode("utf-8"))              # le seul Dockerfile du gabarit, déposé
        self.assertIn(f"\"$HOME/tests/.construction/{etiquette}\"/Dockerfile", depot[0])
        self.assertIn(f"construire_image_tests.sh\" {etiquette} {sha}", construction[0])
        self.assertIsNone(construction[1])
        self.assertEqual(notees, [("ovh-1", etiquette, tp.empreinte_image(p), 812, "2026-11-23T10:00:00")])
        # une autre somme que celle approuvée : rien n'est envoyé
        ssh2, dits = Ssh(), []
        self.assertFalse(ta.construire_image(p, "0" * 64, serveur=serveur, ssh=ssh2, noter=notees.append, dire=dits.append))
        self.assertEqual((ssh2.appels, len(notees)), ([], 1))
        self.assertIn("approuvé", dits[0])
        # construction en échec ou ligne #image absente : rien n'est noté
        for faux in (Ssh(b"#image x 1\n", code=1), Ssh(b"rien\n")):
            self.assertFalse(ta.construire_image(p, sha, serveur=serveur, ssh=faux, noter=notees.append))
        self.assertEqual(len(notees), 1)

    def test_android_tests_lieu_serveur(self):
        self.assertIn("serveur", ANDROID["tests"]["lieux"])
        self.assertNotIn("serveur", ANDROID["emulateur"]["lieux"])


if __name__ == "__main__":
    unittest.main()
