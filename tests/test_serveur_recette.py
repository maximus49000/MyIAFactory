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
        self.ecrire("demo", " " * 70000)
        with mock.patch.object(Path, "read_text", side_effect=AssertionError), \
                mock.patch.object(Path, "read_bytes", side_effect=AssertionError):
            with self.assertRaises(ValueError):
                sr.charger(str(self.projet), "demo")

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

    def test_refus_du_lanceur_est_un_echec(self):
        r = self.recette(2)
        with mock.patch.object(sr.serveur_tache, "verbe", side_effect=ValueError("identifiant refusé")):
            res = sr.executer(r, ID, dossier=self.projet)
        self.assertEqual((res["etapes_faites"], res["echec"]["etape"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
