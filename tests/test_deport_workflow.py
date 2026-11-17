import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))

import workflow_github as wf  # noqa: E402

COMMANDES = {
    "apk": "./gradlew assembleDebug",
    "tests": "python -m unittest",
    "charge": "python charge.py",
}


class TestDeportWorkflow(unittest.TestCase):
    def ecrire(self, texte, binaire=None):
        dossier = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(dossier, ignore_errors=True))
        chemin = Path(dossier) / "myiafactory.yml"
        if binaire is not None:
            chemin.write_bytes(binaire)
        else:
            chemin.write_text(texte, encoding="utf-8", newline="")
        return chemin

    def test_sans_charge_pas_de_schedule(self):
        texte = wf.generer("Mon projet", ["apk", "tests"], COMMANDES)
        self.assertNotIn("schedule", texte)
        self.assertIn("workflow_dispatch", texte)
        self.assertIn("push:", texte)

    def test_charge_donne_le_cron(self):
        texte = wf.generer("Mon projet", ["apk", "charge"], COMMANDES, charge_heure="03:00")
        self.assertIn("cron: '0 3 * * *'", texte)
        self.assertIn("UTC", texte)
        self.assertIn("cron: '30 14 * * *'", wf.generer("p", ["apk", "charge"], COMMANDES, charge_heure="14:30"))

    def test_une_tache_par_action_et_upload_apk(self):
        texte = wf.generer("Mon projet", ["apk", "tests"], COMMANDES)
        self.assertIn("  apk:\n", texte)
        self.assertIn("  tests:\n", texte)
        self.assertEqual(texte.count("actions/upload-artifact@v4"), 1)
        self.assertIn("actions/download-artifact@v4", texte)
        self.assertIn("actions/checkout@v4", texte)
        self.assertIn("needs: [apk]", texte)
        self.assertIn("path: '**/build/outputs/apk/**/*.apk'", texte)    # un * non guillemeté serait un alias YAML

    def test_pas_de_needs_si_apk_n_est_pas_deporte(self):
        texte = wf.generer("Mon projet", ["tests"], COMMANDES)
        self.assertNotIn("needs:", texte)
        self.assertNotIn("download-artifact", texte)

    def test_uniquement_ubuntu_latest(self):
        texte = wf.generer("Mon projet", ["apk", "tests", "charge"], COMMANDES)
        lignes = [l for l in texte.splitlines() if "runs-on" in l]
        self.assertEqual(len(lignes), 3)
        self.assertTrue(all(l.strip() == "runs-on: ubuntu-latest" for l in lignes))

    def test_deterministe_et_fins_de_ligne(self):
        a = wf.generer("Mon projet", ["apk", "tests"], COMMANDES)
        self.assertEqual(a, wf.generer("Mon projet", ["apk", "tests"], COMMANDES))
        self.assertNotIn("\r", a)
        self.assertTrue(a.startswith("# généré par MyIAFactory empreinte="))

    def test_commande_vide_refusee(self):
        for vide in ("", "   ", None):
            with self.assertRaises(ValueError) as c:
                wf.generer("p", ["apk", "tests"], {"apk": "x", "tests": vide})
            self.assertIn("commande", str(c.exception))
        with self.assertRaises(ValueError):
            wf.generer("p", ["apk", "tests"], {"apk": "x"})

    def test_action_inconnue_refusee(self):
        with self.assertRaises(ValueError):
            wf.generer("p", ["bidon"], {"bidon": "x"})

    def test_commande_dans_un_bloc_litteral(self):
        texte = wf.generer("p", ["apk"], {"apk": "echo \"a\" && echo 'b'\nls"})
        self.assertIn("        run: |\n          echo \"a\" && echo 'b'\n          ls\n", texte)

    def test_premiere_ligne_indentee_reste_un_yaml_valide(self):
        texte = wf.generer("p", ["apk"], {"apk": "  ./gradlew assembleDebug\nls\n  sous-ligne"})
        self.assertIn("        run: |\n          ./gradlew assembleDebug\n          ls\n            sous-ligne\n", texte)
        texte = wf.generer("p", ["apk"], {"apk": "\n\n    a\n      b\n\n"})
        self.assertIn("        run: |\n          a\n            b\n", texte)
        with self.assertRaises(ValueError) as c:
            wf.generer("p", ["apk"], {"apk": "\n  \n"})
        self.assertIn("commande", str(c.exception))

    def test_nom_avec_caracteres_speciaux_reste_entre_guillemets(self):
        texte = wf.generer("a: b # c $d", ["apk"], COMMANDES)
        self.assertIn('name: "a: b # c $d"\n', texte)

    def test_heure_invalide_refusee(self):
        for h in ("25:00", "3h", "12:60", ""):
            with self.assertRaises(ValueError):
                wf.generer("p", ["apk", "charge"], COMMANDES, charge_heure=h)

    def test_nom_injecte_neutralise(self):
        texte = wf.generer("p\nevil: 1", ["apk"], COMMANDES)
        self.assertNotIn("\nevil: 1", texte)

    def test_etat_absent(self):
        self.assertEqual(wf.etat_du_fichier(Path(tempfile.gettempdir()) / "nexiste-pas-wf.yml", "x"), "absent")

    def test_etat_a_jour_meme_en_crlf(self):
        voulu = wf.generer("p", ["apk", "tests"], COMMANDES)
        chemin = self.ecrire(voulu)
        self.assertEqual(wf.etat_du_fichier(chemin, voulu), "a_jour")
        chemin = self.ecrire(None, binaire=voulu.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(wf.etat_du_fichier(chemin, voulu), "a_jour")

    def test_changement_de_cadence_a_valider(self):
        ancien = wf.generer("p", ["apk", "charge"], COMMANDES, charge_heure="03:00")
        nouveau = wf.generer("p", ["apk", "charge"], COMMANDES, charge_heure="04:00")
        self.assertEqual(wf.etat_du_fichier(self.ecrire(ancien), nouveau), "a_valider")

    def test_modifie_a_la_main(self):
        voulu = wf.generer("p", ["apk", "tests"], COMMANDES)
        chemin = self.ecrire(voulu.replace("python -m unittest", "python -m unittest -v"))
        self.assertEqual(wf.etat_du_fichier(chemin, voulu), "modifie_a_la_main")

    def test_sans_marqueur_modifie_a_la_main(self):
        chemin = self.ecrire("name: a la main\non: push\n")
        self.assertEqual(wf.etat_du_fichier(chemin, wf.generer("p", ["apk"], COMMANDES)), "modifie_a_la_main")

    def test_diff_unifie(self):
        d = wf.diff("a\nb\n", "a\nc\n")
        self.assertIn("-b", d)
        self.assertIn("+c", d)
        self.assertEqual(wf.diff("a\n", "a\n"), "")


if __name__ == "__main__":
    unittest.main()
