"""Dossiers que le projet déclare ne pas envoyer au serveur (`tests.exclus_instantane`) : l'instantané d'un projet dont le
service est petit et l'application lourde (FM_Stats : `android_app/` 426 Mo, limite 200 Mo) peut partir.

Un dépôt git réel jetable, construit une fois ; le réglage est lu comme `unity_version_hote` : dans les réglages
ENREGISTRÉS au bureau seulement (faux bureau)."""
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import tests_instantane as ti  # noqa: E402
import tests_serveur  # noqa: E402


def _git(args, cwd):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _ecrire(racine, nom, contenu=b"x"):
    chemin = Path(racine, nom)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)


class ExclusValidesTest(unittest.TestCase):
    def test_entrees_valides_normalisees(self):
        self.assertEqual(ti.exclus_valides(["android_app", " build/ ", "a//b", "ANDROID_APP/"]),
                         ("android_app/", "build/", "a/b/"))

    def test_entrees_invalides_ignorees(self):
        invalides = ["", "   ", "/abs", "../x", "a/../b", "./x", "c:/x", "a" + chr(92) + "b", "a" + chr(0) + "b", 12, None,
                     ["x"], "x" * 201]
        self.assertEqual(ti.exclus_valides(invalides), ())

    def test_pas_une_liste(self):
        for v in (None, "android_app/", {"a": 1}, 3):
            self.assertEqual(ti.exclus_valides(v), ())

    def test_au_plus_seize(self):
        self.assertEqual(len(ti.exclus_valides(["d%d" % i for i in range(40)])), ti.MAX_EXCLUS)


class InstantaneAvecExclusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dossier = tempfile.mkdtemp()
        cls.racine = str(Path(cls.dossier, "p"))
        Path(cls.racine).mkdir()
        _git(["init", "-q"], cls.racine)
        for nom in ("serveur/app.py", "serveur/tests/test_a.py", "docs/api.md", "android_app/lib/main.dart",
                    "android_app/assets/gros.bin", "sous/android_app/ok.txt"):
            _ecrire(cls.racine, nom)
        _git(["add", "-A"], cls.racine)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dossier, True)

    def test_sans_exclusion_tout_part(self):
        fichiers, _ = ti.lister(self.racine)
        self.assertIn("android_app/assets/gros.bin", fichiers)

    def test_dossier_exclu_a_la_racine_seulement(self):
        fichiers, ecartes = ti.lister(self.racine, exclus=("android_app/",))
        self.assertFalse([f for f in fichiers if f.startswith("android_app/")])
        self.assertIn("serveur/app.py", fichiers)
        self.assertIn("docs/api.md", fichiers)
        self.assertIn("sous/android_app/ok.txt", fichiers)      # seule la racine est visée, comme une famille
        self.assertEqual(ecartes, [])                           # écarté en silence : c'est voulu par le projet

    def test_sans_casse(self):
        fichiers, _ = ti.lister(self.racine, exclus=("Android_App/",))
        self.assertFalse([f for f in fichiers if f.startswith("android_app/")])

    def test_l_archive_refuse_un_fichier_exclu(self):
        with self.assertRaises(ti.HorsLimites):
            ti.ecrire_tar(self.racine, ["android_app/lib/main.dart"], io.BytesIO(), exclus=("android_app/",))
        self.assertEqual(ti.ecrire_tar(self.racine, ["serveur/app.py"], io.BytesIO(), exclus=("android_app/",))[0], 1)

    def test_limite_totale_respectee_grace_a_l_exclusion(self):
        _ecrire(self.racine, "android_app/assets/enorme.bin", b"0" * 3000)
        try:
            with mock.patch.object(ti, "MAX_TOTAL", 1000):
                tous, _ = ti.lister(self.racine)
                with self.assertRaises(ti.HorsLimites):
                    ti.ecrire_tar(self.racine, tous, io.BytesIO())
                gardes, _ = ti.lister(self.racine, exclus=("android_app/",))
                self.assertGreater(ti.ecrire_tar(self.racine, gardes, io.BytesIO(), exclus=("android_app/",))[0], 0)
        finally:
            os.remove(os.path.join(self.racine, "android_app", "assets", "enorme.bin"))

    def test_le_tar_ne_contient_pas_le_dossier_exclu(self):
        gardes, _ = ti.lister(self.racine, exclus=("android_app/",))
        flux = io.BytesIO()
        ti.ecrire_tar(self.racine, gardes, flux, exclus=("android_app/",))
        flux.seek(0)
        with tarfile.open(fileobj=flux) as t:
            noms = t.getnames()
        self.assertIn("serveur/app.py", noms)
        self.assertFalse([n for n in noms if n.startswith("android_app/")])


class ExclusDuProjetTest(unittest.TestCase):
    """`tests_serveur._exclus_du_projet` : lu dans les réglages enregistrés, jamais ailleurs."""

    def faux_bureau(self, reglages_par_fichier):
        class FauxBureau:
            @staticmethod
            def reglages_enregistres(racine):
                return list(reglages_par_fichier)

            @staticmethod
            def _lire_json_sur(fichier):
                return reglages_par_fichier[fichier]
        return mock.patch.object(tests_serveur, "_bureau", lambda nom: FauxBureau)

    def test_lit_le_reglage_enregistre(self):
        with self.faux_bureau({"r1": {"tests": {"exclus_instantane": ["android_app/", "../x"]}}}):
            self.assertEqual(tests_serveur._exclus_du_projet("p"), ("android_app/",))

    def test_aucun_reglage_ou_pas_enregistre(self):
        with self.faux_bureau({}):
            self.assertEqual(tests_serveur._exclus_du_projet("p"), ())
        with self.faux_bureau({"r1": {"deport": {}}}):
            self.assertEqual(tests_serveur._exclus_du_projet("p"), ())
        with self.faux_bureau({"r1": {"tests": "pas un objet"}}):
            self.assertEqual(tests_serveur._exclus_du_projet("p"), ())

    def test_reglages_qui_divergent_aucune_exclusion(self):
        with self.faux_bureau({"r1": {"tests": {"exclus_instantane": ["a/"]}},
                               "r2": {"tests": {"exclus_instantane": ["b/"]}}}):
            self.assertEqual(tests_serveur._exclus_du_projet("p"), ())

    def test_erreur_de_lecture_aucune_exclusion(self):
        def casse(nom):
            raise RuntimeError("bureau illisible")
        with mock.patch.object(tests_serveur, "_bureau", casse):
            self.assertEqual(tests_serveur._exclus_du_projet("p"), ())

    def test_l_instantane_les_dit_et_les_applique(self):
        dossier = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, dossier, True)
        racine = str(Path(dossier, "p"))
        Path(racine).mkdir()
        _git(["init", "-q"], racine)
        for nom in ("serveur/app.py", "android_app/gros.bin"):
            _ecrire(racine, nom)
        _git(["add", "-A"], racine)
        dits = []
        archive = str(Path(dossier, "a.tar"))
        tests_serveur._instantane(ti, racine, archive, dits.append, None, ("android_app/",))
        self.assertTrue(any("android_app/" in d for d in dits))
        with tarfile.open(archive) as t:
            noms = t.getnames()
        self.assertEqual(noms, ["serveur/app.py"])


if __name__ == "__main__":
    unittest.main()
