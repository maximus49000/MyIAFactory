"""Le sceau du budget des tests (`bureau/tests_sceau.py`) : lecture tolérante, écriture sous verrou, jamais à l'aveugle.

Tests économes : un dossier temporaire par classe, `maintenant` fixe, aucun `sleep`, aucun sous-processus."""
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from bureau import tests_sceau

T = "2026-11-23T10:00:00+01:00"


def maintenant():
    return T


class TestSceau(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def sceau(self, contenu=None):
        """Un chemin de sceau propre à ce test ; `contenu` (texte ou octets) l'écrit."""
        type(self).n += 1
        chemin = self.tmp / ("sceau-%d" % self.n) / "tests-sceau.json"
        chemin.parent.mkdir()
        if isinstance(contenu, str):
            chemin.write_text(contenu, encoding="utf-8")
        elif contenu is not None:
            chemin.write_bytes(contenu)
        return chemin

    def test_valeurs_du_spec(self):
        self.assertEqual(tests_sceau.SCEAU, Path("~/MyIAFactory/tests-sceau.json").expanduser())
        self.assertEqual((tests_sceau.BUDGET_DEFAUT_S, tests_sceau.BUDGET_MIN_S, tests_sceau.BUDGET_MAX_S),
                         (300, 60, 3600))
        self.assertEqual(tests_sceau.ENTREE_VIDE, {
            "budget_s": 300, "commande_complete": None, "reference_s": None, "campagnes": 0, "cumul_s": 0.0,
            "derniers_nb_tests": None, "tache_auto": False, "commande_refusee": None, "alertes": {}, "maj": None})

    def test_lire_sceau_absent_ou_illisible_rend_les_defauts(self):
        cas = [None, "{pas du json", "[1, 2]", '"texte"', '{"p": [1]}', '{"p": {"campagnes": NaN}}',
               b"\xff\xfe\x00garbage", "[" * 100000 + "]" * 100000,
               '{"p": {"budget_s": "beaucoup", "campagnes": -3, "cumul_s": true, "tache_auto": 1, "alertes": []}}']
        for contenu in cas:
            lu = tests_sceau.lire("p", sceau=self.sceau(contenu))
            self.assertEqual(lu, tests_sceau.ENTREE_VIDE, msg=repr(contenu)[:60])
            lu["alertes"]["x"] = 1                                   # une copie : le défaut n'est jamais modifié
            self.assertEqual(tests_sceau.ENTREE_VIDE["alertes"], {})
        dossier = self.sceau()
        dossier.mkdir()                                              # un dossier à la place du fichier
        self.assertEqual(tests_sceau.lire("p", sceau=dossier), tests_sceau.ENTREE_VIDE)
        trop_gros = self.sceau(b'{"p": {"campagnes": 4}, "x": "' + b"a" * (2 * 1024 * 1024) + b'"}')
        self.assertEqual(tests_sceau.lire("p", sceau=trop_gros), tests_sceau.ENTREE_VIDE)
        bon = self.sceau('﻿{"p": {"campagnes": 4, "budget_s": 600, "autre": "garde"}}')
        lu = tests_sceau.lire("p", sceau=bon)
        self.assertEqual((lu["campagnes"], lu["budget_s"], lu["cumul_s"], lu["autre"]), (4, 600, 0.0, "garde"))

    def test_sceau_illisible_n_est_pas_ecrase(self):
        for contenu in (b"{pas du json", b"[1, 2]", b'{"p": {"campagnes": Infinity}}',
                        b'{"p": {}, "x": "' + b"a" * (2 * 1024 * 1024) + b'"}'):
            chemin = self.sceau(contenu)
            with self.assertRaises(tests_sceau.SceauIllisible):
                tests_sceau.modifier("p", lambda e: e.update(campagnes=e["campagnes"] + 1), sceau=chemin,
                                     maintenant=maintenant)
            self.assertEqual(chemin.read_bytes(), contenu)                       # octet pour octet
            self.assertEqual(sorted(p.name for p in chemin.parent.iterdir()), [chemin.name])   # ni temporaire ni verrou
        dossier = self.sceau()
        dossier.mkdir()
        with self.assertRaises(tests_sceau.SceauIllisible):
            tests_sceau.modifier("p", lambda e: None, sceau=dossier, maintenant=maintenant)
        self.assertTrue(dossier.is_dir())

    def test_modifier_garde_les_autres_projets(self):
        chemin = self.sceau(json.dumps({"autre": {"budget_s": 900, "campagnes": 7, "inconnu": [1]}}))
        entree = tests_sceau.modifier("p", lambda e: e.update(campagnes=e["campagnes"] + 1, cumul_s=12.5),
                                      sceau=chemin, maintenant=maintenant)
        self.assertEqual(entree, {**tests_sceau.ENTREE_VIDE, "campagnes": 1, "cumul_s": 12.5, "maj": T})
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        self.assertEqual(donnees["autre"], {"budget_s": 900, "campagnes": 7, "inconnu": [1]})
        self.assertEqual(donnees["p"], entree)
        self.assertEqual(tests_sceau.lire("p", sceau=chemin), entree)
        self.assertEqual(sorted(p.name for p in chemin.parent.iterdir()), [chemin.name])

        def casse(e):
            e["campagnes"] = 99
            raise RuntimeError("en route")
        avant = chemin.read_bytes()
        with self.assertRaises(RuntimeError):                     # `changer` échoue : rien n'est écrit
            tests_sceau.modifier("p", casse, sceau=chemin, maintenant=maintenant)
        with self.assertRaises(ValueError):                       # une valeur non JSON (NaN) n'est jamais écrite
            tests_sceau.modifier("p", lambda e: e.update(cumul_s=float("nan")), sceau=chemin, maintenant=maintenant)
        self.assertEqual(chemin.read_bytes(), avant)
        self.assertEqual(sorted(p.name for p in chemin.parent.iterdir()), [chemin.name])

    def test_modifier_cree_le_sceau_et_son_dossier(self):
        chemin = self.sceau().parent / "sous" / "tests-sceau.json"
        tests_sceau.modifier("p", lambda e: e.update(budget_s=600), sceau=chemin, maintenant=maintenant)
        self.assertEqual(tests_sceau.lire("p", sceau=chemin)["budget_s"], 600)

    def test_modifier_sous_verrou_ne_perd_aucune_incrementation(self):
        chemin = self.sceau()
        erreurs = []

        def fil():
            try:
                for _ in range(5):
                    tests_sceau.modifier("p", lambda e: e.update(campagnes=e["campagnes"] + 1,
                                                                 cumul_s=e["cumul_s"] + 1.5),
                                         sceau=chemin, maintenant=maintenant)
            except Exception as e:  # noqa: BLE001 — remonté au test
                erreurs.append(e)
        fils = [threading.Thread(target=fil) for _ in range(8)]
        for f in fils:
            f.start()
        for f in fils:
            f.join()
        self.assertEqual(erreurs, [])
        lu = tests_sceau.lire("p", sceau=chemin)
        self.assertEqual((lu["campagnes"], lu["cumul_s"]), (40, 60.0))


if __name__ == "__main__":
    unittest.main()
