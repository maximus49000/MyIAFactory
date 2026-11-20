"""Ligne de commande générique des serveurs (`outils/serveur_cli.py`). SSH, ssh-keygen et installeur factices : aucun réseau,
jamais le vrai dossier personnel."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import plateforme  # noqa: E402
import plateforme_ssh  # noqa: E402
import serveur_cli  # noqa: E402
import serveur_modele  # noqa: E402
from serveur_capacites import CATALOGUE  # noqa: E402

LIGNE = "ssh-ed25519 AAAAPUBLIQUE myiafactory"
SECRET_OVH = "SECRET-OVH-CLI-XYZ"
PRIVEE = "PRIVATE-KEY-CONTENT-ABC"


class FauxSsh:
    ErreurSsh = plateforme_ssh.ErreurSsh
    CHANGEMENT_CLE = plateforme_ssh.CHANGEMENT_CLE

    def __init__(self, presentes=()):
        self.presentes, self.appels = set(presentes), []

    def executer(self, hote, commande, cle, stdin=None, delai=60, runner=None):
        self.appels.append(commande)
        if commande == "bash -s" and "sudo=" in (stdin or ""):
            return 0, "user=factory\nsudo=0\n", ""
        if commande == "bash -s":
            return 0, "\n".join(f"{i}={0 if i in self.presentes else 1}" for i in CATALOGUE) + "\n", ""
        return 0, "", ""


class FauxKeygen:
    """Écrit la paire de clés comme `ssh-keygen -f <chemin>`."""

    def __init__(self):
        self.appels = 0

    def __call__(self, args, **kw):
        self.appels += 1
        chemin = Path(args[args.index("-f") + 1])
        chemin.write_text(PRIVEE, encoding="utf-8")
        Path(str(chemin) + ".pub").write_text(LIGNE + "\n", encoding="utf-8")
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.d = Path(self._tmp.name)
        self.ssh, self.keygen, self.installations = FauxSsh(), FauxKeygen(), []

    def installeur(self, serveur, actions, accord, **kw):
        self.installations.append(accord)
        return {"ok": True, "erreur": None, "capacites": {}}

    def lancer(self, *args, installer=None):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            code = serveur_cli.main([*args, "--dossier", str(self.d)], ssh=self.ssh, runner=self.keygen,
                                    installer=installer or self.installeur)
        return code, sortie.getvalue(), erreur.getvalue()

    def declarer(self, nom="Mon serveur"):
        return self.lancer("declarer", nom, "203.0.113.7", "factory")


class TestServeursCli(Base):
    def test_declarer_puis_lister(self):
        code, sortie, _ = self.declarer()
        self.assertEqual(code, 0)
        fiche = json.loads(sortie)["serveur"]
        self.assertEqual((fiche["id"], fiche["hote"], fiche["utilisateur"]), ("mon-serveur", "203.0.113.7", "factory"))
        self.assertEqual(fiche["ligne_cle_publique"], LIGNE)
        self.assertEqual(serveur_modele.lire(self.d)[0].cle, str(self.d / "id_ed25519_mon-serveur"))
        code, sortie, _ = self.lancer("lister")
        self.assertEqual(code, 0)
        liste = json.loads(sortie)["serveurs"]
        self.assertEqual([s["id"] for s in liste], ["mon-serveur"])
        self.assertTrue(all(v == "inconnue" for v in liste[0]["capacites"].values()))
        self.assertEqual(self.lancer("declarer", "Mon serveur", "h2", "factory")[0], 1)    # identifiant déjà pris

    def test_cle_affiche_la_ligne_publique_seulement(self):
        self.declarer()
        code, sortie, erreur = self.lancer("cle", "mon-serveur")
        self.assertEqual(code, 0)
        self.assertEqual(sortie.strip(), LIGNE)
        self.assertNotIn(PRIVEE, sortie + erreur)
        self.assertNotIn("id_ed25519", sortie + erreur)

    def test_apercu_ne_modifie_rien(self):
        self.declarer()
        avant = sorted(p.name for p in self.d.iterdir())
        contenu = (self.d / "serveurs.json").read_text(encoding="utf-8")
        code, sortie, _ = self.lancer("apercu", "mon-serveur", "apk")
        self.assertEqual(code, 0)
        self.assertIn("manquantes", json.loads(sortie))
        self.assertEqual(sorted(p.name for p in self.d.iterdir()), avant)
        self.assertEqual((self.d / "serveurs.json").read_text(encoding="utf-8"), contenu)
        self.assertEqual(self.installations, [])
        self.assertFalse([c for c in self.ssh.appels if c != "bash -s"])

    def test_installer_sans_accord_affiche_l_apercu_et_n_installe_pas(self):
        self.declarer()
        code, sortie, _ = self.lancer("installer", "mon-serveur", "apk")
        self.assertEqual(code, 1)
        donnees = json.loads(sortie)
        self.assertIn("manquantes", donnees["apercu"])
        self.assertIs(donnees["installe"], False)
        self.assertEqual(self.installations, [])
        code, _, _ = self.lancer("installer", "mon-serveur", "apk", "--accord")
        self.assertEqual((code, self.installations), (0, [True]))

    def test_recette_emulateur_apercu_puis_installation(self):
        self.declarer()
        self.ssh.presentes = {"base"}
        code, sortie, _ = self.lancer("apercu", "mon-serveur", "recette-emulateur")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(sortie)["manquantes"], ["android-build", "android-emulateur", "emulateur-image"])
        code, _, _ = self.lancer("installer", "mon-serveur", "recette-emulateur", "--accord")
        self.assertEqual((code, self.installations), (0, [True]))

    def test_sonder_enregistre_l_etat(self):
        self.declarer()
        self.ssh.presentes = {"base"} if "base" in CATALOGUE else set()
        code, sortie, _ = self.lancer("sonder", "mon-serveur")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(sortie)["joignable"])
        self.assertTrue((self.d / "serveurs-etat.json").exists())

    def test_usage_et_codes_de_sortie(self):
        self.declarer()
        for args, attendu in [((), 2), (("inconnue",), 2), (("declarer", "a", "b"), 2), (("lister", "x"), 2),
                              (("cle",), 2), (("apercu", "mon-serveur"), 2), (("cle", "../x"), 2),
                              (("apercu", "mon-serveur", "a/b"), 2), (("apercu", "mon-serveur", "a\\b"), 2),
                              (("cle", "mon-serveur", "--inconnu"), 2), (("apercu", "mon-serveur", "--accord", "apk"), 2),
                              (("apercu", "mon-serveur", "action_inexistante"), 2),
                              (("cle", "absent"), 1), (("sonder", "absent"), 1)]:
            with self.subTest(args=args):
                code, sortie, erreur = self.lancer(*args)
                self.assertEqual(code, attendu)
                self.assertNotIn("Traceback", sortie + erreur)
                self.assertTrue(erreur.strip())

    def test_aucune_sortie_ne_contient_un_secret(self):
        (self.d / "ovh.json").write_text(json.dumps({"point": "ovh-eu", "cle_app": "APP-KEY-CLI-XYZ", "secret": SECRET_OVH,
                                                     "consommateur": "CONSO-CLI-XYZ", "serveur": "ns1"}), encoding="utf-8")
        self.declarer(f"Nom {SECRET_OVH}")
        tout = []
        for args in [("lister",), ("cle", "nom-secret-ovh-cli-xyz"), ("sonder", "nom-secret-ovh-cli-xyz"),
                     ("apercu", "nom-secret-ovh-cli-xyz", "apk"), ("installer", "nom-secret-ovh-cli-xyz", "apk"),
                     ("cle", "absent-" + "x" * 5)]:
            _, sortie, erreur = self.lancer(*args)
            tout.append(sortie + erreur)
        _, sortie, erreur = self.lancer("lister")
        tout = "\n".join(tout) + sortie + erreur
        for secret in (SECRET_OVH, "APP-KEY-CLI-XYZ", "CONSO-CLI-XYZ", PRIVEE, "id_ed25519"):
            self.assertNotIn(secret, tout)

    def test_plateforme_main_delegue_aux_serveurs(self):
        erreur = io.StringIO()
        with contextlib.redirect_stderr(erreur):
            self.assertEqual(plateforme.main(["serveurs"]), 2)
        self.assertIn("serveurs", erreur.getvalue())


if __name__ == "__main__":
    unittest.main()
