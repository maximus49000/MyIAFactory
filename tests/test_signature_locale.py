"""« Release signé » (tâche 15d) : le poste signe avec de faux zipalign, apksigner et jarsigner ; le mot de passe n'est jamais lu d'un
argument ni de l'environnement de l'appelant, jamais sur une ligne de commande, jamais affiché."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import signature_locale as sl  # noqa: E402

SECRET = "motdepasse-tres-secret"


class Faux:
    """Un faux `subprocess.run` : journalise (argv, mot de passe vu dans l'environnement) et copie l'entrée vers la sortie."""

    def __init__(self, echec_sur=None):
        self.appels, self.echec_sur = [], echec_sur

    def __call__(self, argv, env=None, **kw):
        self.appels.append((list(argv), (env or {}).get(sl.VARIABLE_MOT_DE_PASSE), kw))
        nom = Path(argv[0]).stem
        if nom == self.echec_sur:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=("échec " + SECRET).encode())
        if nom == "zipalign":
            Path(argv[-1]).write_bytes(Path(argv[-2]).read_bytes() + b"+aligne")
        elif nom == "apksigner" and argv[1] == "sign":
            Path(argv[argv.index("--out") + 1]).write_bytes(Path(argv[-1]).read_bytes() + b"+signe")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")


class Banc(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)
        self.apk = self.d / "app-release-unsigned.apk"
        self.apk.write_bytes(b"apk")
        self.cle = self.d / "release.jks"
        self.cle.write_bytes(b"coffre")
        self.outils = {"zipalign": "/sdk/zipalign", "apksigner": "/sdk/apksigner"}


class TestSigner(Banc):
    def test_apk_aligne_signe_verifie_et_mot_de_passe_seulement_en_environnement(self):
        faux = Faux()
        sortie = self.d / "app-release.apk"
        sl.signer(self.apk, self.cle, "cle1", sortie, SECRET, outils=self.outils, executer=faux)
        self.assertEqual(sortie.read_bytes(), b"apk+aligne+signe")
        self.assertEqual([Path(a[0][0]).stem + (" " + a[0][1] if a[0][1] in ("sign", "verify") else "") for a in faux.appels],
                         ["zipalign", "apksigner sign", "apksigner verify"])
        for argv, mdp, kw in faux.appels:
            self.assertEqual(mdp, SECRET)
            self.assertNotIn(SECRET, " ".join(argv))                    # jamais sur la ligne de commande
            self.assertIs(kw["stdin"], subprocess.DEVNULL)
        signature = faux.appels[1][0]
        self.assertIn("env:" + sl.VARIABLE_MOT_DE_PASSE, signature)
        self.assertEqual(signature[signature.index("--ks-key-alias") + 1], "cle1")
        self.assertEqual(faux.appels[0][0][:5], ["/sdk/zipalign", "-p", "-f", "4", str(self.apk)])

    def test_aab_signe_par_jarsigner_sur_une_copie(self):
        aab = self.d / "app.aab"
        aab.write_bytes(b"aab")
        faux = Faux()
        sortie = self.d / "app-signe.aab"
        sl.signer(aab, self.cle, "cle1", sortie, SECRET, executer=faux)
        argv = faux.appels[0][0]
        self.assertEqual((argv[0], "-storepass:env" in argv, SECRET in " ".join(argv)), ("jarsigner", True, False))
        self.assertEqual((aab.read_bytes(), sortie.exists()), (b"aab", True))      # l'original n'est pas modifié

    def test_echec_ne_laisse_rien_et_ne_montre_pas_le_mot_de_passe(self):
        sortie = self.d / "app-release.apk"
        with self.assertRaises(sl.RefusSignature) as c:
            sl.signer(self.apk, self.cle, "cle1", sortie, SECRET, outils=self.outils, executer=Faux("apksigner"))
        self.assertNotIn(SECRET, str(c.exception))
        self.assertFalse(sortie.exists())

    def test_refus_alias_sortie_existante_coffre_et_mot_de_passe_vide(self):
        sortie = self.d / "s.apk"
        for kw in ({"alias": "a b; rm"}, {"alias": "a" * 65}, {"mot_de_passe": ""}):
            with self.subTest(kw=kw), self.assertRaises(sl.RefusSignature):
                sl.signer(self.apk, self.cle, kw.get("alias", "cle1"), sortie, kw.get("mot_de_passe", SECRET),
                          outils=self.outils, executer=Faux())
        with self.assertRaises(sl.RefusSignature):
            sl.signer(self.apk, self.d / "absent.jks", "cle1", sortie, SECRET, outils=self.outils, executer=Faux())
        sortie.write_bytes(b"deja")
        with self.assertRaises(sl.RefusSignature):
            sl.signer(self.apk, self.cle, "cle1", sortie, SECRET, outils=self.outils, executer=Faux())
        self.assertEqual(sortie.read_bytes(), b"deja")


class TestDecouverte(Banc):
    def test_chercher_artefact(self):
        (self.d / "sous").mkdir()
        recent = self.d / "sous" / "app-release-unsigned.apk"
        recent.write_bytes(b"x")
        os.utime(self.apk, (1, 1))
        (self.d / "app-debug.apk").write_bytes(b"debug")
        self.assertEqual(sl.chercher_artefact(self.d), recent)
        with tempfile.TemporaryDirectory() as vide, self.assertRaises(sl.RefusSignature):
            sl.chercher_artefact(vide)

    def test_outils_du_sdk(self):
        for v in ("34.0.0", "36.0.0", "9.0.0", "pas-une-version"):
            (self.d / "sdk" / "build-tools" / v).mkdir(parents=True)
        for v in ("36.0.0", "34.0.0"):
            for nom in ("zipalign", "apksigner"):
                (self.d / "sdk" / "build-tools" / v / nom).write_text("")
        o = sl.outils_sdk(self.d / "sdk")
        self.assertTrue(o["zipalign"].replace("\\", "/").endswith("build-tools/36.0.0/zipalign"))
        self.assertTrue(sl.outils_sdk(self.d / "sdk", "34.0.0")["apksigner"].replace("\\", "/").endswith("34.0.0/apksigner"))
        with self.assertRaises(sl.RefusSignature):
            sl.outils_sdk(self.d / "sdk", "35.0.0")
        with self.assertRaises(sl.RefusSignature):
            sl.outils_sdk(self.d / "absent")


class TestMain(Banc):
    def args(self, **plus):
        return ["--artefact", str(self.apk), "--keystore", str(self.cle), "--alias", "cle1",
                "--sortie", str(self.d / "app.apk"), *plus.get("sdk", [])]

    def test_sans_terminal_refus_et_le_mot_de_passe_n_est_pas_demande(self):
        vus = []
        code = sl.main(self.args(), saisir=lambda *_: vus.append(1) or SECRET, interactif=False, executer=Faux(), outils=self.outils)
        self.assertEqual((code, vus), (1, []))

    def test_saisie_au_poste_puis_signature(self):
        faux = Faux()
        code = sl.main(self.args(), saisir=lambda *_: SECRET, interactif=True, executer=faux, outils=self.outils)
        self.assertEqual(code, 0)
        self.assertTrue((self.d / "app.apk").exists())

    def test_mot_de_passe_de_l_environnement_de_l_appelant_ignore(self):
        os.environ[sl.VARIABLE_MOT_DE_PASSE] = "celui-de-l-agent"
        try:
            faux = Faux()
            sl.main(self.args(), saisir=lambda *_: SECRET, interactif=True, executer=faux, outils=self.outils)
        finally:
            del os.environ[sl.VARIABLE_MOT_DE_PASSE]
        self.assertEqual({a[1] for a in faux.appels}, {SECRET})

    def test_appel_invalide(self):
        self.assertEqual(sl.main(["--artefact", "x"], interactif=True), 2)
        self.assertEqual(sl.main(["--mot-de-passe", "x"], interactif=True), 2)


if __name__ == "__main__":
    unittest.main()
