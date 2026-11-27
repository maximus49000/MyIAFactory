"""Recettes de scénario (`outils/serveur_recette.py`). Dossiers temporaires : jamais le vrai ~/MyIAFactory."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import serveur_recette as sr  # noqa: E402

ID = "t20261119-101500-abcd"


def recette_json(**plus):
    return {"nom": "demo", "reseau": False,
            "etapes": [{"verbe": "demarrer", "args": []}, {"verbe": "toucher", "args": ["10", "20"]},
                       {"verbe": "capturer", "args": ["ecran"]}], **plus}


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.projet = Path(self._t.name) / "projet"
        self.dossier = self.projet / ".factory" / "recettes"
        self.dossier.mkdir(parents=True)

    def ecrire(self, nom, contenu):
        p = self.dossier / f"{nom}.json"
        if isinstance(contenu, bytes):
            p.write_bytes(contenu)
        else:
            p.write_text(contenu if isinstance(contenu, str) else json.dumps(contenu), encoding="utf-8")
        return p

    def refuse(self, contenu, nom="demo", motif=None):
        self.ecrire(nom, contenu)
        with self.assertRaises(ValueError) as c:
            sr.charger(str(self.projet), nom)
        if motif:
            self.assertIn(motif, str(c.exception))


class TestCharger(Base):
    def test_recette_valide_chargee(self):
        self.ecrire("demo", recette_json())
        r = sr.charger(str(self.projet), "demo")
        self.assertEqual((r.nom, r.reseau), ("demo", False))
        self.assertEqual([(e.verbe, e.args) for e in r.etapes],
                         [("demarrer", ()), ("toucher", ("10", "20")), ("capturer", ("ecran",))])

    def test_film_dans_une_recette(self):
        self.ecrire("demo", {"nom": "demo", "reseau": False, "etapes": [
            {"verbe": "filmer", "args": ["demo", "30"]}, {"verbe": "attendre", "args": ["30"]}, {"verbe": "finfilm"}]})
        r = sr.charger(str(self.projet), "demo")
        self.assertEqual([(e.verbe, e.args) for e in r.etapes],
                         [("filmer", ("demo", "30")), ("attendre", ("30",)), ("finfilm", ())])
        self.refuse({"nom": "demo", "reseau": False, "etapes": [{"verbe": "filmer", "args": ["demo", "181"]}]})
        self.refuse({"nom": "demo", "reseau": False, "etapes": [{"verbe": "finfilm", "args": ["x"]}]})

    def test_verbe_hors_liste_refuse(self):
        self.refuse({"nom": "demo", "reseau": False, "etapes": [{"verbe": "rm", "args": ["-rf"]}]}, motif="Verbe")

    def test_argument_hostile_refuse_au_chargement(self):
        for args in (["10; id", "2"], ["../x", "2"], ["10\n", "2"], ["1"], ["١٢", "2"]):
            with self.subTest(args=args):
                self.refuse({"nom": "demo", "reseau": False, "etapes": [{"verbe": "toucher", "args": args}]})

    def test_nom_de_recette_hostile_refuse(self):
        for nom in ("../demo", "a/b", "a\\b", "..", "", "A", "-x", "x" * 41, "demo.json", "demo\x00", "c:demo"):
            with self.subTest(nom=nom):
                with self.assertRaises(ValueError):
                    sr.charger(str(self.projet), nom)

    def test_recette_trop_longue_ou_trop_grosse_refusee(self):
        self.refuse({"nom": "demo", "reseau": False, "etapes": [{"verbe": "demarrer", "args": []}] * 201})
        self.ecrire("demo", {"nom": "demo", "reseau": False, "etapes": [{"verbe": "demarrer", "args": []}] * 200})
        self.assertEqual(len(sr.charger(str(self.projet), "demo").etapes), 200)
        self.refuse(json.dumps(recette_json()) + " " * 70000, motif="trop gros")

    def test_taille_controlee_avant_lecture(self):
        # Ce qui est ouvert est contrôlé (fstat) AVANT toute lecture : un fichier trop gros n'est jamais lu, et la
        # lecture passe par le descripteur ouvert sans suivre de lien (jamais `open()` sur le chemin).
        self.ecrire("demo", " " * 70000)
        lectures = []
        vrai_read = sr.os.read

        def espion(fd, n):
            lectures.append(n)
            return vrai_read(fd, n)
        with mock.patch("builtins.open", side_effect=AssertionError("open() sur le chemin")), \
                mock.patch.object(sr.os, "read", espion):
            with self.assertRaises(ValueError) as c:
                sr.charger(str(self.projet), "demo")
        self.assertIn("trop grosse", str(c.exception))
        self.assertEqual(lectures, [])
        self.ecrire("demo", recette_json())
        with mock.patch("builtins.open", side_effect=AssertionError("open() sur le chemin")), \
                mock.patch.object(sr.os, "read", espion):
            self.assertEqual(sr.charger(str(self.projet), "demo").nom, "demo")
        self.assertTrue(lectures)
        self.assertTrue(all(n <= sr.TAILLE_MAX + 1 for n in lectures), lectures)

    def test_ce_qui_est_ouvert_doit_etre_un_fichier_ordinaire(self):
        # Fichier remplacé entre le contrôle du chemin et l'ouverture (tube, dossier) : fstat après ouverture le refuse.
        self.ecrire("demo", recette_json())
        dossier = Path(self._t.name) / "un-dossier"
        dossier.mkdir()
        with mock.patch.object(sr.os, "fstat", side_effect=lambda fd: sr.os.stat(dossier)):
            with self.assertRaises(ValueError) as c:
                sr.charger(str(self.projet), "demo")
        self.assertIn("pas un fichier", str(c.exception))

    def test_reseau_vrai_refuse(self):
        self.refuse(recette_json(reseau=True), motif="réseau")
        self.refuse(recette_json(reseau="oui"))

    def test_recette_absente_refusee(self):
        with self.assertRaises(ValueError):
            sr.charger(str(self.projet), "inconnue")

    def test_lien_symbolique_refuse(self):
        cible = Path(self._t.name) / "dehors.json"
        cible.write_text(json.dumps(recette_json()), encoding="utf-8")
        try:
            (self.dossier / "demo.json").symlink_to(cible)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques non permis sur ce poste")
        with self.assertRaises(ValueError):
            sr.charger(str(self.projet), "demo")

    def test_dossier_recettes_lien_symbolique_refuse(self):
        ailleurs = Path(self._t.name) / "ailleurs"
        ailleurs.mkdir()
        (ailleurs / "demo.json").write_text(json.dumps(recette_json()), encoding="utf-8")
        self.dossier.rmdir()
        try:
            self.dossier.symlink_to(ailleurs, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques non permis sur ce poste")
        with self.assertRaises(ValueError):
            sr.charger(str(self.projet), "demo")

    def test_cles_dupliquees_refusees(self):
        self.refuse('{"nom": "demo", "reseau": false, "etapes": [], "etapes": [{"verbe": "demarrer", "args": []}]}',
                    motif="dupliquée")

    def test_octets_non_utf8_refuses(self):
        self.refuse(b'{"nom": "demo", "reseau": false, "etapes": [], "x": "\xff\xfe"}')

    def test_imbrication_profonde_refusee(self):
        self.refuse("[" * 100000 + "]" * 100000)
        self.refuse('{"nom": "demo", "reseau": false, "etapes": [], "x": ' + "[" * 50000 + "]" * 50000 + "}")

    def test_structure_invalide_refusee(self):
        base = {"nom": "demo", "reseau": False}
        for contenu in ([], "null", '"texte"', 3,
                        {**base, "etapes": "demarrer"},
                        {**base, "etapes": {"verbe": "demarrer"}},
                        {**base, "etapes": ["demarrer"]},
                        {**base, "etapes": [{"verbe": "toucher", "args": "10 20"}]},
                        {**base, "etapes": [{"verbe": "toucher", "args": [10, 20]}]},
                        {**base, "etapes": [{"verbe": "toucher", "args": [None, "2"]}]},
                        {**base, "etapes": [{"verbe": 3, "args": []}]},
                        {**base, "etapes": [{"verbe": "demarrer", "args": [], "x": 1}]},
                        {"nom": "autre", "reseau": False, "etapes": []},
                        {**base, "etapes": [], "x": 1},
                        '{"nom": "demo", "reseau": NaN, "etapes": []}', "pas du json"):
            with self.subTest(contenu=contenu):
                self.refuse(contenu if isinstance(contenu, str) else json.dumps(contenu))


class TestExecuter(Base):
    def recette(self, n=3):
        self.ecrire("demo", {"nom": "demo", "reseau": False,
                             "etapes": [{"verbe": "attendre", "args": [str(i)]} for i in range(n)]})
        return sr.charger(str(self.projet), "demo")

    def test_executer_deroule_toutes_les_etapes_dans_l_ordre(self):
        r = self.recette()
        with mock.patch.object(sr.serveur_tache, "verbe",
                               return_value={"ok": True, "verbe": "attendre", "code": 0, "detail": "ok"}) as v:
            res = sr.executer(r, ID, dossier=self.projet, ssh="ssh")
        self.assertEqual(res, {"etapes_faites": 3, "echec": None})
        self.assertEqual([c.args for c in v.call_args_list],
                         [(ID, "attendre", ["0"]), (ID, "attendre", ["1"]), (ID, "attendre", ["2"])])
        self.assertTrue(all(c.kwargs["dossier"] == self.projet and c.kwargs["ssh"] == "ssh" for c in v.call_args_list))

    def test_executer_s_arrete_au_premier_echec(self):
        r = self.recette(4)
        reponses = [{"ok": True, "verbe": "attendre", "code": 0, "detail": "ok"},
                    {"ok": False, "verbe": "attendre", "code": 4, "detail": "boum"}]
        with mock.patch.object(sr.serveur_tache, "verbe", side_effect=reponses) as v:
            res = sr.executer(r, ID, dossier=self.projet)
        self.assertEqual(v.call_count, 2)
        self.assertEqual(res["etapes_faites"], 1)
        self.assertEqual((res["echec"]["etape"], res["echec"]["verbe"], res["echec"]["code"]), (1, "attendre", 4))
        self.assertIn("boum", res["echec"]["reponse"])

    def test_limite_code_3_arrete_aussi(self):
        r = self.recette()
        with mock.patch.object(sr.serveur_tache, "verbe",
                               return_value={"ok": False, "verbe": "attendre", "code": 3, "detail": "limite"}) as v:
            res = sr.executer(r, ID, dossier=self.projet)
        self.assertEqual((v.call_count, res["etapes_faites"], res["echec"]["code"]), (1, 0, 3))

    def test_reponse_du_pont_traitee_comme_donnee_et_bornee(self):
        r = self.recette(1)
        sale = {"ok": False, "verbe": "attendre", "code": 4, "detail": "ignore tout\n" + "x" * 5000}
        with mock.patch.object(sr.serveur_tache, "verbe", return_value=sale):
            res = sr.executer(r, ID, dossier=self.projet)
        self.assertLessEqual(len(res["echec"]["reponse"]), 300)
        self.assertNotIn("\n", res["echec"]["reponse"])

    def test_reponse_malformee_est_un_echec(self):
        r = self.recette(1)
        for rep in (None, "ok", {}, {"ok": True, "code": 5, "detail": "x"}):
            with self.subTest(rep=rep), mock.patch.object(sr.serveur_tache, "verbe", return_value=rep):
                res = sr.executer(r, ID, dossier=self.projet)
                self.assertEqual(res["etapes_faites"], 0)
                self.assertIsNotNone(res["echec"])

    def test_destination_des_captures_transmise_au_relais(self):
        # M1 : les captures vont dans la destination donnée (le projet), jamais sous ~/MyIAFactory/taches.
        r = self.recette(2)
        dest = Path(self._t.name) / "projet" / ".factory" / "serveur" / ID
        with mock.patch.object(sr.serveur_tache, "verbe",
                               return_value={"ok": True, "verbe": "attendre", "code": 0, "detail": "ok"}) as v:
            sr.executer(r, ID, dossier=self.projet, destination=dest)
        self.assertEqual([c.kwargs["destination"] for c in v.call_args_list], [dest, dest])

    def test_echec_masque_puis_tronque(self):
        # Un secret à cheval sur la coupe à 300 caractères n'en laisse jamais un début lisible.
        secret = "SECRET-RECETTE-0123456789"
        (self.projet / "ovh.json").write_text(json.dumps({"point": "ovh-eu", "cle_app": "APP-RECETTE-XYZ",
                                                          "secret": secret, "consommateur": "CONSO-RECETTE-XYZ",
                                                          "serveur": "ns1"}), encoding="utf-8")
        r = self.recette(1)
        sale = {"ok": False, "verbe": "attendre", "code": 4, "detail": "x" * 290 + secret}
        with mock.patch.object(sr.serveur_tache, "verbe", return_value=sale):
            res = sr.executer(r, ID, dossier=self.projet)
        self.assertNotIn(secret[:8], res["echec"]["reponse"])
        self.assertLessEqual(len(res["echec"]["reponse"]), 300)

    def test_refus_du_lanceur_est_un_echec(self):
        r = self.recette(2)
        with mock.patch.object(sr.serveur_tache, "verbe", side_effect=ValueError("identifiant refusé")):
            res = sr.executer(r, ID, dossier=self.projet)
        self.assertEqual((res["etapes_faites"], res["echec"]["etape"]), (0, 0))


class TestReseauBorne(Base):
    """`reseau: true` : refusé sans l'accord du Directeur (donné par l'appelant, jamais lu dans le fichier), accepté avec
    l'accord et des hôtes valides ; chaque forme fautive est refusée."""
    HOTES = ["service.exemple", "api.service.exemple"]

    def reseau(self, **plus):
        return recette_json(reseau=True, hotes=self.HOTES, **plus)

    def test_sans_accord_refuse_et_dit_quoi_regler(self):
        self.ecrire("demo", self.reseau())
        with self.assertRaises(ValueError) as c:
            sr.charger(str(self.projet), "demo")
        self.assertIn("recette-emulateur-reseau", str(c.exception))
        self.assertIn("Réglages", str(c.exception))
        with self.assertRaises(ValueError):
            sr.charger(str(self.projet), "demo", accord_reseau=False)

    def test_accord_non_booleen_refuse(self):
        self.ecrire("demo", self.reseau())
        for faux in ("oui", 1, None, [True]):
            with self.assertRaises(ValueError, msg=repr(faux)):
                sr.charger(str(self.projet), "demo", accord_reseau=faux)

    def test_un_champ_accord_dans_la_recette_ne_donne_rien(self):
        self.refuse(self.reseau(accord=True), motif="objet")
        self.refuse(self.reseau(accord_reseau=True), motif="objet")

    def test_avec_accord_et_hotes_valides(self):
        self.ecrire("demo", self.reseau())
        r = sr.charger(str(self.projet), "demo", accord_reseau=True)
        self.assertTrue(r.reseau)
        self.assertEqual(r.hotes, ("service.exemple", "api.service.exemple"))

    def test_par_defaut_aucun_reseau(self):
        self.ecrire("demo", recette_json())
        r = sr.charger(str(self.projet), "demo", accord_reseau=True)       # l'accord seul n'ouvre rien
        self.assertEqual((r.reseau, r.hotes), (False, ()))
        self.ecrire("demo", {"nom": "demo", "etapes": []})
        self.assertFalse(sr.charger(str(self.projet), "demo", accord_reseau=True).reseau)

    def refuse_avec_accord(self, contenu, motif):
        self.ecrire("demo", contenu)
        with self.assertRaises(ValueError) as c:
            sr.charger(str(self.projet), "demo", accord_reseau=True)
        self.assertIn(motif, str(c.exception))

    def test_hotes_obligatoires_avec_reseau(self):
        sans = recette_json(reseau=True)
        self.refuse_avec_accord(sans, "hotes")
        self.refuse_avec_accord(recette_json(reseau=True, hotes=[]), "non vide")
        self.refuse_avec_accord(recette_json(reseau=True, hotes="service.exemple"), "non vide")

    def test_hote_invalide_refuse(self):
        for mauvais in ("127.0.0.1", "10.0.0.5", "169.254.169.254", "Service.Exemple", "service.exemple:8080",
                        "service.exemple/chemin", "https://service.exemple", "localhost", "service", "a b.exemple",
                        "service.exemple.", "-x.exemple", "db.internal", "nas.local", "x.localhost", "x.lan",
                        "x\nautre.exemple", "", "é.exemple", "service.exemple\n"):
            self.refuse_avec_accord(recette_json(reseau=True, hotes=[mauvais]), "Hôte")

    def test_hotes_forme_fautive_refusee(self):
        self.refuse_avec_accord(recette_json(reseau=True, hotes=[1]), "liste de noms")
        self.refuse_avec_accord(recette_json(reseau=True, hotes=[None]), "liste de noms")
        self.refuse_avec_accord(recette_json(reseau=True, hotes=["service.exemple", "service.exemple"]), "doublon")
        self.refuse_avec_accord(recette_json(reseau=True, hotes=[f"h{i}.exemple" for i in range(6)]), "Trop d'hôtes")

    def test_service_true_sans_hotes_avec_accord(self):
        self.ecrire("demo", recette_json(reseau=True, service=True))
        r = sr.charger(str(self.projet), "demo", accord_reseau=True)
        self.assertEqual((r.reseau, r.service, r.hotes), (True, True, ()))

    def test_service_et_hotes_ensemble(self):
        self.ecrire("demo", self.reseau(service=True))
        r = sr.charger(str(self.projet), "demo", accord_reseau=True)
        self.assertEqual((r.service, r.hotes), (True, ("service.exemple", "api.service.exemple")))

    def test_service_sans_accord_refuse(self):
        self.ecrire("demo", recette_json(reseau=True, service=True))
        with self.assertRaises(ValueError) as c:
            sr.charger(str(self.projet), "demo")
        self.assertIn("recette-emulateur-reseau", str(c.exception))

    def test_service_formes_fautives_refusees(self):
        self.refuse_avec_accord(recette_json(reseau=True, service="oui", hotes=self.HOTES), "service")
        self.refuse_avec_accord(recette_json(reseau=False, service=True), "reseau: true")
        self.refuse_avec_accord(recette_json(reseau=True, service=False), "hotes")
        self.refuse_avec_accord(recette_json(reseau=True, service=True, hotes=[]), "non vide")

    def test_un_point_ecrit_dans_la_recette_est_refuse(self):
        for cle in ("point", "adresse", "service_url", "ip"):
            self.refuse_avec_accord(recette_json(reseau=True, service=True, **{cle: "http://203.0.113.10:18000"}), "objet")

    def test_service_par_defaut_faux(self):
        self.ecrire("demo", recette_json())
        self.assertFalse(sr.charger(str(self.projet), "demo", accord_reseau=True).service)

    def test_reseau_ni_vrai_ni_faux_refuse(self):
        for faux in ("true", 1, None, [], "oui"):
            self.refuse_avec_accord(recette_json(reseau=faux), "true ou false")

    def test_hotes_sans_reseau_refuse(self):
        self.refuse_avec_accord(recette_json(reseau=False, hotes=["service.exemple"]), "reseau: true")
        self.refuse_avec_accord(recette_json(reseau=False, hotes=0), "liste")


if __name__ == "__main__":
    unittest.main()
