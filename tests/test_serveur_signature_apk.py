"""Réglage « signature des APK » par projet (tâche 15e) : registre, demande d'agent, enveloppe (la clé de debug du serveur n'est
montée, en lecture seule, que si le projet le choisit)."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE))
import serveur_agent as sa  # noqa: E402
from bureau import registre, reglages  # noqa: E402
from tests.test_serveur_agent import Base, ID1  # noqa: E402
from tests.test_serveur_agent_script import Banc, suite_dans  # noqa: E402


class TestRegistre(unittest.TestCase):
    def test_choix_ferme_et_defaut_le_plus_sur(self):
        r = next(x for x in registre.REGISTRE if x.id == "signature_apk")
        self.assertEqual((r.forme, r.defaut, r.niveaux), ("choix", "aucune", registre.NIVEAUX))
        self.assertEqual(r.options, ("aucune", "debug_serveur", "poste_signe"))
        self.assertEqual(len(r.libelles_options), 3)
        for v in r.options:
            registre.verifier_valeur(r, v)
        for mauvais in ("debug", True, 1, "", ["aucune"]):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                registre.verifier_valeur(r, mauvais)

    def test_ecriture_par_niveau_et_valeur_effective(self):
        with tempfile.TemporaryDirectory() as d:
            projet, bureau = Path(d, "reglages.json"), Path(d, "bureau.json")
            projet.write_text("{}", encoding="utf-8")
            bureau.write_text(json.dumps({"projets": [{"chemin": str(projet)}]}), encoding="utf-8")
            self.assertEqual(reglages.charger_effectif(projet, bureau)["signature_apk"], "aucune")
            reglages.fixer_niveau_bureau(bureau, ("reglages", "signature_apk"), "poste_signe")
            self.assertEqual(reglages.charger_effectif(projet, bureau)["signature_apk"], "poste_signe")
            reglages.fixer_signature_apk(projet, "debug_serveur")                 # le projet l'emporte
            self.assertEqual(reglages.charger_effectif(projet, bureau)["signature_apk"], "debug_serveur")
            with self.assertRaises(ValueError):
                reglages.fixer_signature_apk(projet, "release")
            with self.assertRaises(ValueError):
                reglages.fixer_niveau_bureau(bureau, ("reglages", "signature_apk"), "release")
            projet.write_text(json.dumps({"signature_apk": "n'importe quoi"}), encoding="utf-8")
            with self.assertRaises(reglages.ReglagesInvalides):
                reglages.charger(projet)


class TestDemande(Base):
    def test_champ_ferme_et_defaut_aucune(self):
        self.assertEqual(self.demande().signature, "aucune")
        self.assertEqual(self.demande(signature="debug_serveur").signature, "debug_serveur")
        for mauvais in ("debug", None, True, "poste", ["aucune"]):
            with self.assertRaises(ValueError, msg=repr(mauvais)):
                self.demande(signature=mauvais)

    def test_demande_json_une_seule_fois_et_absente_par_defaut(self):
        self.lancer()
        self.assertNotIn("signature", json.loads(self.srv.entrees[ID1]["entree/demande.json"]))
        self.assertEqual(sa._demande_dict(self.demande(signature="debug_serveur"))["signature"], "debug_serveur")


@unittest.skipUnless(shutil.which("bash"), "bash absent")
class TestEnveloppe(unittest.TestCase):
    def cle(self, b):
        d = b.home / "android-signature"
        d.mkdir()
        (d / "debug.keystore").write_bytes(b"cle-de-debug")

    def test_cle_de_debug_en_lecture_seule_seulement_avec_ce_choix(self):
        with Banc() as b:
            self.cle(b)
            b.ecrire_entree(signature="debug_serveur")
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            a = b.run_args()
            suite_dans(self, a, "--mount", f"type=bind,src={b.h()}/android-signature/debug.keystore,"
                                           "dst=/opt/android-signature/debug.keystore,readonly")
            self.assertIn("AGENT_DEBUG_KEYSTORE=/opt/android-signature/debug.keystore",
                          [a[i + 1] for i in range(len(a) - 1) if a[i] == "-e"])
            b.arreter()
            b.attendre_final()

    def test_aucun_montage_sans_le_choix(self):
        for valeur in (None, "aucune", "poste_signe"):
            with self.subTest(valeur=valeur), Banc() as b:
                self.cle(b)                                  # la clé est là : elle n'est pourtant pas montée
                if valeur is None:
                    b.ecrire_entree()
                else:
                    b.ecrire_entree(signature=valeur)
                r = b.lancer("seul", "30", "2048", "2", "2")
                self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
                self.assertNotIn("android-signature", " ".join(b.run_args()))
                b.arreter()
                b.attendre_final()

    def test_cle_absente_refusee_avec_le_choix(self):
        with Banc() as b:
            b.ecrire_entree(signature="debug_serveur")
            r = b.lancer("seul", "30", "2048", "2", "2")
            self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
            self.assertIn("Clé de debug absente", b.etat()["raison"])
            self.assertEqual([x for x in b.appels("docker run") if " -d " in f" {x} "], [])

    def test_valeur_mal_formee_ou_en_double_refusee(self):
        for supplement in ('"signature": "release"', '"signature": "aucune", "signature": "debug_serveur"'):
            with self.subTest(supplement=supplement), Banc() as b:
                self.cle(b)
                b.ecrire_entree()
                demande = b.entree / "demande.json"
                texte = demande.read_text(encoding="utf-8").rstrip().rstrip("}").rstrip() + ", " + supplement + "}"
                demande.write_text(texte, newline="\n")
                r = b.lancer("seul", "30", "2048", "2", "2")
                self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
                self.assertRegex(b.etat()["raison"], "signature")


if __name__ == "__main__":
    unittest.main()
