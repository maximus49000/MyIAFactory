"""Essai réel : le bureau lit, écrit et expose les lieux d'exécution déportée (réglage `deport`)."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from bureau import deport_conso, serveur
from tests import copie_demo
from tests.test_serveur import AvecServeur, SourceSimulee


class TestDeportReglage(AvecServeur):
    def poster(self, corps):
        return self.req("POST", "/api/reglages", json.dumps(corps), self.ENT)

    def test_etat_par_defaut_tout_au_poste(self):
        d = self.json("/api/etat")["deport"]
        self.assertEqual(set(d["lieux"].values()), {"poste"})
        self.assertEqual(d["avertissements"], [])
        self.assertIs(d["serveur_disponible"], False)

    def test_post_lieux_partiels_ecrit_et_expose(self):
        r, _ = self.poster({"deport": {"lieux": {"apk": "github"}}})
        self.assertEqual(r.status, 200)
        ecrit = json.loads(self.regl.read_text(encoding="utf-8"))["deport"]
        self.assertEqual(ecrit["lieux"]["apk"], "github")
        self.assertEqual(ecrit["charge_heure"], "03:00")   # les autres clés sont gardées
        etat = self.json("/api/etat")["deport"]
        self.assertEqual(etat["lieux"]["apk"], "github")
        self.assertEqual(etat["lieux"]["tests"], "poste")

    def test_post_fusionne_sur_l_existant(self):
        self.poster({"deport": {"lieux": {"apk": "github"}}})
        r, _ = self.poster({"deport": {"lieux": {"tests": "github"}}})
        self.assertEqual(r.status, 200)
        lieux = self.json("/api/etat")["deport"]["lieux"]
        self.assertEqual((lieux["apk"], lieux["tests"]), ("github", "github"))

    def test_emulateur_sur_github_refuse(self):
        r, data = self.poster({"deport": {"lieux": {"emulateur": "github"}}})
        self.assertEqual(r.status, 400)
        self.assertIn("peu fiable", json.loads(data.decode("utf-8"))["erreur"])
        self.assertEqual(self.json("/api/etat")["deport"]["lieux"]["emulateur"], "poste")

    def test_deport_invalide_refuse(self):
        r, _ = self.poster({"deport": "github"})
        self.assertEqual(r.status, 400)

    def test_chaine_coupee_produit_un_avertissement(self):
        self.poster({"deport": {"lieux": {"apk": "github", "tests": "poste"}}})
        d = self.json("/api/etat")["deport"]
        self.assertTrue(any(a.startswith("« tests »") for a in d["avertissements"]))

    def test_message_d_erreur_mentionne_deport(self):
        r, data = self.req("POST", "/api/reglages", json.dumps({"x": 1}), self.ENT)
        self.assertEqual(r.status, 400)
        self.assertIn("deport", json.loads(data.decode("utf-8"))["erreur"])


class TestDeportGlobalDuBureau(unittest.TestCase):
    def test_le_defaut_du_bureau_s_applique_et_le_projet_l_emporte(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
            tmp = Path(t)
            copie_demo(tmp / "a")
            fichier = tmp / "bureau.json"
            fichier.write_text(json.dumps({"projets": ["a/reglages.json"],
                                           "deport": {"lieux": {"apk": "github", "tests": "github"}}}),
                               encoding="utf-8")
            srv = serveur.creer(bureau=fichier, port=0, ouvrir=SourceSimulee())
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                def lire():
                    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=30)
                    c.request("GET", "/api/etat")
                    r = json.loads(c.getresponse().read())
                    c.close()
                    return r["deport"]["lieux"]
                self.assertEqual(lire()["apk"], "github")
                self.assertEqual(lire()["emulateur"], "poste")
                regl = tmp / "a" / "reglages.json"
                donnees = json.loads(regl.read_text(encoding="utf-8"))
                donnees["deport"] = {"lieux": {"apk": "poste"}}
                regl.write_text(json.dumps(donnees), encoding="utf-8")
                srv.projet()._cache_etat = (0.0, srv.projet()._cache_etat[1])
                self.assertEqual(lire()["apk"], "poste")
            finally:
                srv.shutdown()
                srv.server_close()


    def test_le_projet_ne_fige_que_ses_propres_lieux(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
            tmp = Path(t)
            copie_demo(tmp / "a")
            fichier = tmp / "bureau.json"
            ecrire = lambda lieux: fichier.write_text(json.dumps(
                {"projets": ["a/reglages.json"], "deport": {"lieux": lieux}}), encoding="utf-8")
            ecrire({"apk": "github"})
            srv = serveur.creer(bureau=fichier, port=0, ouvrir=SourceSimulee())
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=30)
                c.request("POST", "/api/reglages", json.dumps({"deport": {"lieux": {"tests": "poste"}}}),
                          {"X-Bureau": "1", "Content-Type": "application/json"})
                r = c.getresponse()
                r.read()
                c.close()
                self.assertEqual(r.status, 200)
                brut = json.loads((tmp / "a" / "reglages.json").read_text(encoding="utf-8"))
                self.assertEqual(brut["deport"]["lieux"], {"tests": "poste"})
                p = srv.projet()
                self.assertEqual(p.lieux_effectifs()["apk"], "github")
                ecrire({"apk": "poste"})
                self.assertEqual(p.lieux_effectifs()["apk"], "poste")
            finally:
                srv.shutdown()
                srv.server_close()


if __name__ == "__main__":
    unittest.main()


class TestDeportDepotRoutes(AvecServeur):
    def setUp(self):
        super().setUp()
        import subprocess
        self.depot = self.tmp / "demo"
        for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@example.org"],
                     ["config", "user.name", "T"], ["add", "."], ["commit", "-q", "-m", "x"]):
            subprocess.run(["git", *args], cwd=str(self.depot), check=True, capture_output=True)
        r, _ = self.req("POST", "/api/reglages", json.dumps(
            {"deport": {"lieux": {"apk": "github"}, "commandes": {"apk": "./gradlew assembleDebug"}}}), self.ENT)
        self.assertEqual(r.status, 200)

    def test_apercu_expose_etat_diff_et_empreinte(self):
        a = self.json("/api/deport/apercu")
        self.assertEqual(a["etat"], "absent")
        self.assertIn("+jobs:", a["diff"])
        self.assertEqual(len(a["empreinte"]), 64)

    def test_appliquer_demande_l_en_tete_et_une_empreinte_a_jour(self):
        r, _ = self.req("POST", "/api/deport/appliquer", json.dumps({"empreinte": "0" * 64}), {"Content-Type": "application/json"})
        self.assertEqual(r.status, 403)
        r, data = self.req("POST", "/api/deport/appliquer", json.dumps({"empreinte": "0" * 64}), self.ENT)
        self.assertEqual(r.status, 409)
        self.assertIn("plus à jour", json.loads(data.decode("utf-8"))["erreur"])

    def test_appliquer_sans_origine_dit_l_echec_du_push(self):
        e = self.json("/api/deport/apercu")["empreinte"]
        r, data = self.req("POST", "/api/deport/appliquer", json.dumps({"empreinte": e}), self.ENT)
        self.assertEqual(r.status, 409)
        self.assertIn("origin", json.loads(data.decode("utf-8"))["erreur"])


class TestDeportParTypeDeProjet(AvecServeur):
    def poster(self, corps):
        return self.req("POST", "/api/reglages", json.dumps(corps), self.ENT)

    def en_android(self):
        (self.tmp / "demo" / "factory.json").write_text(json.dumps({"genre": "application-mobile-android"}),
                                                        encoding="utf-8")
        self.p._cache_etat = (0.0, self.p._cache_etat[1])

    def test_projet_generique_expose_les_quatre_actions(self):
        d = self.json("/api/etat")["deport"]
        self.assertEqual([a["id"] for a in d["actions"]], ["apk", "tests", "emulateur", "charge"])
        self.assertEqual(set(d["lieux"]), {"apk", "tests", "emulateur", "charge"})

    def test_projet_android_expose_ses_actions_avec_libelle_lieux_et_bientot(self):
        self.en_android()
        d = self.json("/api/etat")["deport"]
        actions = {a["id"]: a for a in d["actions"]}
        self.assertEqual(list(actions), ["apk", "tests", "lint", "emulateur", "release"])
        self.assertEqual(actions["tests"]["libelle"], "Tests unitaires")
        self.assertEqual(actions["emulateur"]["lieux"], ["poste"])
        self.assertIn("clés de signature", actions["release"]["bientot"])
        self.assertEqual(set(d["lieux"]), set(actions))

    def test_projet_android_refuse_la_charge_et_ne_signale_pas_d_attente_pour_les_tests(self):
        self.en_android()
        r, data = self.poster({"deport": {"lieux": {"charge": "poste"}}})
        self.assertEqual(r.status, 400)
        self.assertIn("n'existe pas pour ce type de projet", json.loads(data.decode("utf-8"))["erreur"])
        r, _ = self.poster({"deport": {"lieux": {"apk": "github", "tests": "poste"}}})
        self.assertEqual(r.status, 200)
        self.assertEqual(self.json("/api/etat")["deport"]["avertissements"], [])


class TestDeportConsoEtat(AvecServeur):
    """`deport.conso` : présent seulement si une action tourne sur GitHub ; jamais de vrai gh (faux lanceur)."""

    def faux_gh(self):
        appels = []

        def lancer(argv, **kw):
            import subprocess
            appels.append(list(argv))
            sortie = {("run", "list"): json.dumps([{"databaseId": 1, "name": "MyIAFactory", "status": "completed",
                                                    "conclusion": "success", "createdAt": "2026-11-10T10:00:00Z",
                                                    "startedAt": "2026-11-10T10:00:00Z",
                                                    "updatedAt": "2026-11-10T10:04:10Z", "url": "https://x/1"}]),
                      ("run", "view"): json.dumps({"jobs": [{"name": "apk", "conclusion": "success",
                                                     "startedAt": "2026-11-10T10:00:00Z",
                                                     "completedAt": "2026-11-10T10:04:10Z"}]}),
                      ("repo", "view"): json.dumps({"visibility": "PRIVATE"})}.get(tuple(argv[1:3]), "")
            code = 1 if argv[1] == "api" else 0
            return subprocess.CompletedProcess(argv, code, sortie, "")
        return lancer, appels

    def test_sans_action_github_pas_de_conso_et_pas_d_appel_gh(self):
        lancer, appels = self.faux_gh()
        deport_conso.LANCER = lancer
        self.assertNotIn("conso", self.json("/api/etat")["deport"])
        self.assertEqual(appels, [])

    def test_avec_action_github_conso_exposee(self):
        lancer, appels = self.faux_gh()
        deport_conso.LANCER = lancer
        self.addCleanup(deport_conso.arreter)
        r, _ = self.req("POST", "/api/reglages", json.dumps({"deport": {"lieux": {"apk": "github"}}}), self.ENT)
        self.assertEqual(r.status, 200)
        premier = self.json("/api/etat")["deport"]["conso"]   # rendu tout de suite : gh se lit en arrière-plan
        self.assertIn("lecture", premier["texte"])
        deport_conso.attendre()
        c = self.p.etat_deport()["conso"]
        self.assertEqual(set(c), {"niveau", "texte", "mois", "minutes_total", "quota", "restantes", "public",
                                  "par_action", "derniers"})
        self.assertTrue(appels)
        self.assertEqual(c["derniers"][0]["conclusion"], "success")
